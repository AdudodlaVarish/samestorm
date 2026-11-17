import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
import prepare_pilot_model as pilot
from samestorm.provenance import sha256


class PilotModelPreparation(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        (self.root/'requirements-model-prep.txt').write_bytes((ROOT/'requirements-model-prep.txt').read_bytes())
        (self.root/'scripts').mkdir()
        for name in ['prepare_model.py','scale_generate.py']:
            (self.root/'scripts'/name).write_bytes((ROOT/'scripts'/name).read_bytes())
        (self.root/'configs').mkdir()
        for name in ['models','toolchain','experiment','judges']:
            (self.root/f'configs/{name}.json').write_bytes((ROOT/f'configs/{name}.json').read_bytes())
        self.model=next(m for m in json.loads((self.root/'configs/models.json').read_text())['models']
                        if m['id']==pilot.MODEL)
        metadata=self.root/self.model['metadata_path'];metadata.parent.mkdir(parents=True)
        metadata.write_bytes((ROOT/self.model['metadata_path']).read_bytes())
        source=self.root/'src/samestorm/judges.py';source.parent.mkdir(parents=True)
        source.write_bytes((ROOT/'src/samestorm/judges.py').read_bytes())
        self.toolchain=self.root/'vendor/llama.cpp';self.toolchain.mkdir(parents=True)
        self.run=self.root/'results/raw/bundle';self.run.mkdir(parents=True)
        self.commands=[]
        self.patches=[patch.object(pilot,'ROOT',self.root),
            patch.dict(os.environ,{'SLURM_JOB_ID':'fixture'},clear=True),
            patch.object(pilot.prep,'verify_toolchain',return_value=self.toolchain),
            patch.object(pilot.shutil,'which',side_effect=lambda name:'/synthetic/'+name),
            patch.object(pilot.importlib.metadata,'version',return_value='synthetic-version'),
            patch.object(pilot.subprocess,'check_output',return_value='Synthetic compiler/tool\n'),
            patch.object(pilot,'run_command',side_effect=self.command)]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def command(self,command,run,record,environment):
        values=[str(x) for x in command];self.commands.append(values)
        if '-std=c++17' in values:
            Path(values[values.index('-o')+1]).write_bytes(b'Synthetic compiler executable')
            return
        if len(values)<2 or 'prepare_model.py' not in values[1]:return
        step=values[2]
        self.assertEqual(environment['CUDA_VISIBLE_DEVICES'],'')
        if step=='download':
            self.assertEqual(environment['HF_HUB_OFFLINE'],'0')
            (self.root/self.model['checkpoint_path']).mkdir(parents=True)
            return
        self.assertEqual(environment['HF_HUB_OFFLINE'],'1')
        precision='F16' if step=='convert' else 'Q4_K_M'
        relative=self.model['reference_path'] if precision=='F16' else str(
            Path(self.model['reference_path']).with_name('model-Q4_K_M.gguf'))
        target=self.root/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(b'Synthetic artifact, not a real GGUF '+precision.encode())
        child=values[values.index('--run-id')+1]
        folder=self.root/'results/raw'/child;folder.mkdir()
        pin=json.loads((self.root/'configs/toolchain.json').read_text())['llama_cpp_commit']
        (folder/'manifest.json').write_text(json.dumps(dict(status='complete',
            stage='model-preparation-convert' if precision=='F16' else 'model-preparation-quantize',
            model_id=self.model['id'],model_revision=self.model['revision'],llama_cpp_commit=pin,
            outputs=[dict(path=relative,quantization_type=precision,sha256=sha256(target))])))

    def test_one_workflow_downloads_converts_builds_cpu_quantizer_and_quantizes_only_q4(self):
        bundle=pilot.prepare(self.run,{})
        self.assertEqual([a['precision'] for a in bundle['artifacts']],['F16','Q4_K_M'])
        self.assertFalse(bundle['inference_performed'])
        steps=[r[2] for r in self.commands if len(r)>2 and 'prepare_model.py' in r[1]]
        self.assertEqual(steps,['download','convert','quantize'])
        configure=next(r for r in self.commands if r[0]=='cmake' and '-S' in r)
        self.assertIn('-DGGML_CUDA=OFF',configure)
        self.assertIn('-DCMAKE_C_COMPILER=/synthetic/gcc',configure)
        self.assertIn('-DCMAKE_CXX_COMPILER=/synthetic/g++',configure)
        quantize=next(r for r in self.commands if '--precision' in r)
        self.assertEqual(quantize[quantize.index('--precision')+1],'Q4_K_M')
        self.assertEqual(quantize[quantize.index('--quantizer')+1],str(self.toolchain/'build-prep/bin/llama-quantize'))

    def test_verified_existing_outputs_are_reused_and_changed_artifact_is_preserved(self):
        first=pilot.prepare(self.run,{})
        self.commands.clear()
        self.assertEqual(pilot.prepare(self.run,{}),first)
        self.assertFalse(any(len(r)>1 and 'prepare_model.py' in r[1] for r in self.commands))
        path=self.root/first['artifacts'][1]['path'];path.write_bytes(b'Changed artifact')
        with self.assertRaisesRegex(ValueError,'no matching complete pinned'):
            pilot.prepare(self.run,{})
        self.assertEqual(path.read_bytes(),b'Changed artifact')

    def test_local_execution_and_dirty_checkout_stop_before_downloading(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaisesRegex(ValueError,'Slurm'):
            pilot.prepare(self.run,{})
        self.assertEqual(self.commands,[])
        with patch.object(pilot.prep,'verify_toolchain',side_effect=ValueError('Dirty checkout')):
            with self.assertRaisesRegex(ValueError,'Dirty checkout'):pilot.prepare(self.run,{})
        self.assertEqual(self.commands,[])

    def test_partial_checkpoint_fails_without_overwriting_or_redownloading(self):
        checkpoint=self.root/self.model['checkpoint_path'];checkpoint.mkdir(parents=True)
        (checkpoint/'keep.txt').write_text('Preserve partial download')
        with patch.object(pilot.prep,'verify_checkpoint',side_effect=ValueError('Missing pinned file')):
            with self.assertRaisesRegex(ValueError,'Missing pinned'):pilot.prepare(self.run,{})
        self.assertEqual((checkpoint/'keep.txt').read_text(),'Preserve partial download')
        self.assertFalse(any(len(r)>1 and 'prepare_model.py' in r[1] for r in self.commands))

    def test_main_preserves_failure_manifest(self):
        with patch.object(pilot,'new_run_dir',return_value=self.run),\
             patch.object(pilot,'prepare',side_effect=RuntimeError('Synthetic conversion failure')),\
             patch.object(sys,'argv',['prepare_pilot_model.py','--run-id','bundle']),\
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pilot.main(),1)
        record=json.loads((self.run/'manifest.json').read_text())
        self.assertEqual(record['status'],'failed')
        self.assertEqual(record['error'],'Synthetic conversion failure')
        self.assertFalse(record['inference_performed'])

    def test_combined_job_rejects_unapproved_inputs_before_model_preparation(self):
        packet=pilot.generation.prepare(ROOT,pilot=True,english_only=True)
        review=self.root/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json'
        review.parent.mkdir(parents=True)
        saved=json.loads((ROOT/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json').read_text())
        saved['frozen']=False;review.write_text(json.dumps(saved))
        with patch.object(pilot,'new_run_dir',return_value=self.run),\
             patch.object(pilot.generation,'hardware_probe',return_value={'partition':'gpu-a100-dev'}),\
             patch.object(pilot.generation,'prepare',return_value=packet),\
             patch.object(pilot,'prepare') as prepare,\
             patch.object(sys,'argv',['prepare_pilot_model.py','--run-id','bundle','--generate-english-pilot']),\
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pilot.main(),1)
        prepare.assert_not_called()
        record=json.loads((self.run/'manifest.json').read_text())
        self.assertEqual(record['status'],'failed')
        self.assertIn('frozen input manifest',record['error'])

    def test_combined_generation_builds_cuda_and_uses_each_matching_receipt(self):
        bundle=pilot.prepare(self.run,{})
        packet=pilot.generation.prepare(ROOT,pilot=True,english_only=True)
        record={'inference_performed':False}
        self.commands.clear()

        def generate(command,run,record,environment):
            values=[str(x) for x in command];self.commands.append(values)
            self.assertNotIn('CUDA_VISIBLE_DEVICES',environment)
            if len(values)<2 or 'scale_generate.py' not in values[1]:return
            child=values[values.index('--run-id')+1]
            index=int(values[values.index('--job-index')+1])
            precision=packet['plan']['jobs'][index]['precision']
            artifact=next(a for a in bundle['artifacts'] if a['precision']==precision)
            self.assertEqual(values[values.index('--model-manifest')+1],
                             str(self.root/artifact['preparation_manifest']))
            self.assertIn('--pilot',values);self.assertIn('--english-only',values)
            folder=self.root/'results/raw'/child;folder.mkdir()
            (folder/'manifest.json').write_text(json.dumps(dict(status='complete',
                completed_answers=6,expected_answers=6,runtime_failures=0)))
            (folder/'answers.jsonl').write_text('Synthetic response\n'*6)

        with patch.object(pilot,'run_command',side_effect=generate):
            pilot.generate_pilot(self.run,record,bundle,packet)
        self.assertTrue(record['inference_performed'])
        configure=next(r for r in self.commands if '-S' in r)
        self.assertIn('-DGGML_CUDA=ON',configure)
        self.assertIn('-DCMAKE_CUDA_ARCHITECTURES=80',configure)
        self.assertIn('-DCMAKE_CXX_COMPILER=/synthetic/g++',configure)
        self.assertIn('-DCMAKE_CUDA_HOST_COMPILER=/synthetic/g++',configure)
        result=json.loads((self.run/'generation_bundle.json').read_text())
        self.assertEqual((result['main_answers'],result['repeat_answers']),(10,2))
        self.assertEqual([o['precision'] for o in result['outputs']],['F16','Q4_K_M'])
        self.assertFalse(result['judges_run'])

    def test_failed_generation_preserves_first_run_and_stops_before_second(self):
        bundle=pilot.prepare(self.run,{})
        packet=pilot.generation.prepare(ROOT,pilot=True,english_only=True)
        record={'inference_performed':False}
        commands=[]

        def fail(command,run,record,environment):
            values=[str(x) for x in command];commands.append(values)
            if len(values)<2 or 'scale_generate.py' not in values[1]:return
            child=self.root/'results/raw'/values[values.index('--run-id')+1]
            child.mkdir();(child/'answers.jsonl').write_text('Preserved partial output\n')
            raise RuntimeError('Synthetic failed generation')

        with patch.object(pilot,'run_command',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'failed generation'):
                pilot.generate_pilot(self.run,record,bundle,packet)
        self.assertTrue(record['inference_performed'])
        self.assertEqual(len(record['generation_runs']),1)
        self.assertEqual((self.root/record['generation_runs'][0]/'answers.jsonl').read_text(),
                         'Preserved partial output\n')
        self.assertFalse((self.run/'generation_bundle.json').exists())

    def test_wrong_cached_compiler_is_preserved_and_rejected_before_model_work(self):
        build=self.toolchain/'build-prep';build.mkdir()
        cache=build/'CMakeCache.txt';cache.write_text('CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\n')
        with self.assertRaisesRegex(ValueError,'Cached compiler differs'):
            pilot.prepare(self.run,{})
        self.assertEqual(cache.read_text(),'CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++\n')
        self.assertEqual(self.commands,[])

    def test_compiler_only_mode_needs_no_slurm_or_model_work(self):
        with patch.object(pilot,'new_run_dir',return_value=self.run),\
             patch.dict(os.environ,{},clear=True),patch.object(pilot,'prepare') as prepare,\
             patch.object(sys,'argv',['prepare_pilot_model.py','--run-id','bundle','--check-compiler']),\
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pilot.main(),0)
        prepare.assert_not_called()
        record=json.loads((self.run/'manifest.json').read_text())
        self.assertEqual(record['stage'],'compiler-link-check')
        self.assertFalse(record['inference_performed'])
        self.assertEqual(record['compiler_paths']['cxx'],'/synthetic/g++')
        self.assertTrue(record['compiler_check_sha256'])

    def test_failed_compiler_check_stops_before_checkpoint_download(self):
        def fail(command,run,record,environment):
            if '-std=c++17' in [str(x) for x in command]:raise RuntimeError('Synthetic linker failure')
            self.command(command,run,record,environment)
        with patch.object(pilot,'run_command',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'linker failure'):pilot.prepare(self.run,{})
        self.assertFalse(any(len(r)>1 and 'prepare_model.py' in r[1] for r in self.commands))


if __name__=='__main__':unittest.main()
