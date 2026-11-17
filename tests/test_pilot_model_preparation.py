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
        (self.root/'scripts').mkdir()
        for name in ['prepare_model.py','scale_generate.py']:
            (self.root/'scripts'/name).write_bytes((ROOT/'scripts'/name).read_bytes())
        (self.root/'configs').mkdir()
        for name in ['models','toolchain','experiment']:
            (self.root/f'configs/{name}.json').write_bytes((ROOT/f'configs/{name}.json').read_bytes())
        self.model=next(m for m in json.loads((self.root/'configs/models.json').read_text())['models']
                        if m['id']==pilot.MODEL)
        metadata=self.root/self.model['metadata_path'];metadata.parent.mkdir(parents=True)
        metadata.write_bytes((ROOT/self.model['metadata_path']).read_bytes())
        self.toolchain=self.root/'vendor/llama.cpp';self.toolchain.mkdir(parents=True)
        self.run=self.root/'results/raw/bundle';self.run.mkdir(parents=True)
        self.commands=[]
        self.patches=[patch.object(pilot,'ROOT',self.root),
            patch.dict(os.environ,{'SLURM_JOB_ID':'fixture'},clear=True),
            patch.object(pilot.prep,'verify_toolchain',return_value=self.toolchain),
            patch.object(pilot.shutil,'which',return_value='/synthetic/tool'),
            patch.object(pilot.importlib.metadata,'version',return_value='synthetic-version'),
            patch.object(pilot.subprocess,'check_output',return_value='Synthetic compiler/tool\n'),
            patch.object(pilot,'run_command',side_effect=self.command)]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def command(self,command,run,record,environment):
        values=[str(x) for x in command];self.commands.append(values)
        if 'prepare_model.py' not in values[1]:return
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


if __name__=='__main__':unittest.main()
