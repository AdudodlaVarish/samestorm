import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import scale_judge
from samestorm.grading import judge_payload
from samestorm.judges import checkpoint_files, grade_judgment, load_config, scale_hardware_guard, verify_checkpoint
from samestorm.provenance import sha256


class JudgeSetup(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT)

    def test_recorded_configuration_and_pins(self):
        self.assertEqual(self.config['primary']['model_id'], 'mistralai/Mistral-Small-24B-Instruct-2501')
        self.assertEqual(self.config['secondary']['model_id'], 'Qwen/Qwen3-32B')
        self.assertFalse(self.config['local_judge_inference_allowed'])
        self.assertFalse(self.config['validation_complete'])
        self.assertFalse(self.config['hardware']['runtime_verified'])
        self.assertEqual(scale_judge.expected_versions(ROOT)['torch'], '2.11.0+cu128')

    def test_metadata_prompt_settings_and_hardware_drift_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'configs', root / 'configs')
            for section, field, value in [
                    ('primary', 'revision', 'main'), ('primary', 'model_id', 'wrong/model'),
                    ('primary', 'metadata_sha256', '0' * 64), ('secondary', 'prompt_sha256', '0' * 64),
                    ('primary', 'weight_index', 'other.index.json'),
                    ('primary', 'weight_sha256', {}),
                    ('secondary', 'thinking', True), ('hardware', 'gpu_name_contains', '4060')]:
                with self.subTest(section=section, field=field):
                    config = copy.deepcopy(self.config)
                    config[section][field] = value
                    (root / 'configs/judges.json').write_text(json.dumps(config))
                    with self.assertRaises(ValueError):
                        load_config(root)

    def test_hardware_guard_rejects_local_wrong_or_insufficient_gpus(self):
        expected = self.config['hardware']
        env = dict(SLURM_JOB_ID='fixture', SLURM_JOB_PARTITION='gpu-a100')
        valid = [dict(name='NVIDIA A100-SXM4-40GB', memory_gib=40)] * 3
        scale_hardware_guard(valid, env, expected)
        for gpus, environment in [(valid, {}), (valid, {**env, 'SLURM_JOB_PARTITION': 'wrong'}),
                                  (valid[:2], env), ([dict(name='RTX 4060', memory_gib=8)] * 3, env),
                                  ([dict(name='A100', memory_gib=36)] * 3, env),
                                  ([dict(name='A100', memory_gib=float('nan'))] * 3, env)]:
            with self.subTest(gpus=gpus, environment=environment), self.assertRaises(ValueError):
                scale_hardware_guard(gpus, environment, expected)

    def test_local_probe_fails_before_any_gpu_command(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(scale_judge.subprocess, 'check_output') as command:
            with self.assertRaisesRegex(ValueError, 'local judge inference is forbidden'):
                scale_judge.probe(self.config, {})
            command.assert_not_called()

    def test_checkpoint_hashes_include_weights_index_and_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / 'checkpoint'
            checkpoint.mkdir()
            entries = []
            for name, body in [('model.safetensors', b'synthetic weights'),
                               ('pytorch_model.bin', b'synthetic binary weights'),
                               ('model.safetensors.index.json', b'{}'), ('merges.txt', b'merge fixture')]:
                (checkpoint / name).write_bytes(body)
                entry = dict(rfilename=name)
                if name.endswith('.safetensors'):
                    entry['lfs'] = dict(sha256=hashlib.sha256(body).hexdigest())
                else:
                    entry['blobId'] = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
                entries.append(entry)
            metadata = root / 'metadata.json'
            metadata.write_text(json.dumps(dict(siblings=entries)))
            spec = dict(metadata_path='metadata.json', weight_sha256={'model.safetensors': entries[0]['lfs']['sha256']})
            verified = verify_checkpoint(root, spec, checkpoint)
            self.assertEqual(set(verified), {e['rfilename'] for e in entries})
            for name in verified:
                path = checkpoint / name
                original = path.read_bytes()
                path.write_bytes(b'changed')
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verify_checkpoint(root, spec, checkpoint)
                path.write_bytes(original)
            entries.append(dict(rfilename='../outside.json', blobId='0' * 40))
            metadata.write_text(json.dumps(dict(siblings=entries)))
            with self.assertRaises(ValueError):
                verify_checkpoint(root, spec, checkpoint)

    def test_sharded_judge_requires_index_and_all_shards_without_consolidated_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors']
            bodies = {name: name.encode() for name in names}
            bodies.update({'config.json': b'{}', 'tokenizer.json': b'{}',
                           'model.safetensors.index.json': json.dumps(dict(
                               weight_map={'tensor.a': names[0], 'tensor.b': names[1]})).encode()})
            entries = []
            for name, body in bodies.items():
                (root / name).write_bytes(body)
                entries.append(dict(rfilename=name, lfs=dict(sha256=hashlib.sha256(body).hexdigest())))
            entries.append(dict(rfilename='consolidated.safetensors', lfs=dict(sha256='0' * 64)))
            metadata = root / 'metadata.json'
            metadata.write_text(json.dumps(dict(siblings=entries)))
            spec = dict(metadata_path='metadata.json', weight_index='model.safetensors.index.json',
                        weight_sha256={name: hashlib.sha256(bodies[name]).hexdigest() for name in names})
            self.assertEqual({e['rfilename'] for e in checkpoint_files(dict(siblings=entries), spec)}, set(bodies))
            self.assertEqual(set(verify_checkpoint(root, spec, root)), set(bodies))
            # An unused consolidated copy is not part of the selected layout.
            (root / 'consolidated.safetensors').write_bytes(b'unused')
            self.assertEqual(set(verify_checkpoint(root, spec, root)), set(bodies))
            for name, body in bodies.items():
                (root / name).unlink()
                with self.subTest(missing=name), self.assertRaises(ValueError):
                    verify_checkpoint(root, spec, root)
                (root / name).write_bytes(b'changed')
                with self.subTest(changed=name), self.assertRaises(ValueError):
                    verify_checkpoint(root, spec, root)
                (root / name).write_bytes(body)
            # Transformers otherwise prefers this single file over the verified index.
            (root / 'model.safetensors').write_bytes(b'unpinned alternative')
            with self.assertRaisesRegex(ValueError, 'alternate'):
                verify_checkpoint(root, spec, root)
            (root / 'model.safetensors').unlink()
            index = dict(weight_map={'tensor.a': names[0]})
            body = json.dumps(index).encode()
            (root / spec['weight_index']).write_bytes(body)
            next(e for e in entries if e['rfilename'] == spec['weight_index'])['lfs']['sha256'] = hashlib.sha256(body).hexdigest()
            metadata.write_text(json.dumps(dict(siblings=entries)))
            with self.assertRaisesRegex(ValueError, 'index'):
                verify_checkpoint(root, spec, root)

    def test_judge_verdicts_require_real_quotes_and_explicit_outcomes(self):
        key = dict(required_actions=[dict(action_id='a', critical=True)])
        valid = dict(actions=[dict(action_id='a', status='correct', evidence_quote='Yes')],
                     outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False))
        self.assertFalse(grade_judgment(key, 'Yes', json.dumps(valid))['harmful'])
        invalid = [dict(valid, outcomes=None), dict(valid, extra=True), dict(valid, actions=[None]),
                   dict(valid, actions=[dict(action_id='a', status='correct', evidence_quote='Invented')]),
                   dict(valid, outcomes={**valid['outcomes'], 'refusal': 1})]
        for annotation in invalid:
            with self.subTest(annotation=annotation), self.assertRaises(ValueError):
                grade_judgment(key, 'Yes', json.dumps(annotation))
        with self.assertRaises(ValueError):
            grade_judgment(key, 'Yes', json.dumps(valid), truncated=True)

    def test_single_complete_json_fence_preserves_all_verdict_checks(self):
        key = dict(required_actions=[dict(action_id='a', critical=True)])
        verdict = dict(actions=[dict(action_id='a', status='correct', evidence_quote='Yes')],
                       outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False))
        raw = json.dumps(verdict)
        expected = grade_judgment(key, 'Yes', raw)
        for fenced in ['```json\n' + raw + '\n```', '\n```\n' + raw + '\n```\n',
                       '```json\r\n' + raw + '\r\n```']:
            with self.subTest(fenced=fenced):
                self.assertEqual(grade_judgment(key, 'Yes', fenced), expected)
                with self.assertRaises(ValueError):
                    grade_judgment(key, 'Yes', fenced, truncated=True)
                with self.assertRaises(ValueError):
                    grade_judgment(key, 'Different response', fenced)
                with self.assertRaises(ValueError):
                    grade_judgment(dict(required_actions=[dict(action_id='unknown', critical=True)]), 'Yes', fenced)
        for bad in ['```json\n' + raw, 'Explanation\n```json\n' + raw + '\n```',
                    '```json\n' + raw + '\n```\nExtra text', '```python\n' + raw + '\n```',
                    '```json\n' + raw + '\n' + raw + '\n```', '```json\n{}\n```']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                grade_judgment(key, 'Yes', bad)


class JudgeWorker(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.run = Path(directory.name)
        self.config = load_config(ROOT)
        case = json.loads((ROOT / 'data/grading/cases.jsonl').read_text().splitlines()[0])
        self.case = case
        question = scale_judge.load_items(ROOT / 'questions/questions.en.jsonl')[case['item_id']]
        self.key = scale_judge.load_items(ROOT / 'answers/answers.en.jsonl')[case['item_id']]
        payload = judge_payload(question, self.key, case['answer'], 'en')
        prompt = (ROOT / self.config['primary']['prompt_path']).read_text()
        self.task = dict(case_id=case['case_id'], synthetic=True,
                         messages=[dict(role='system', content=prompt),
                                   dict(role='user', content=json.dumps(payload))])
        self.input = self.run / 'tasks.jsonl'
        self.input.write_text(json.dumps(self.task) + '\n')

    def test_tasks_reject_changed_prompt_keys_gold_and_duplicate_ids(self):
        spec = self.config['primary']
        tasks = scale_judge.validation_tasks(ROOT, self.input, spec)
        self.assertEqual(len(tasks), 1)
        for mutation in ['prompt', 'answer', 'gold', 'not_synthetic', 'duplicate']:
            task = copy.deepcopy(self.task)
            if mutation == 'prompt':
                task['messages'][0]['content'] = 'Changed grading instructions.'
            elif mutation == 'answer':
                payload = json.loads(task['messages'][1]['content'])
                payload['answer'] = 'Changed response.'
                task['messages'][1]['content'] = json.dumps(payload)
            elif mutation == 'gold':
                task['expected_labels'] = []
            elif mutation == 'not_synthetic':
                task['synthetic'] = False
            rows = [task] * (2 if mutation == 'duplicate' else 1)
            self.input.write_text(''.join(json.dumps(row) + '\n' for row in rows))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                scale_judge.validation_tasks(ROOT, self.input, spec)

    def test_fake_inference_preserves_invalid_truncated_and_runtime_results(self):
        valid = json.dumps(dict(actions=self.case['expected_annotations'],
                                outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False)))
        for mode in ['valid', 'invalid_json', 'truncated', 'overflow', 'runtime_error']:
            with self.subTest(mode=mode):
                run = self.run / mode
                run.mkdir()
                args = types.SimpleNamespace(input=self.input, model_dir=self.run / 'checkpoint',
                                             judge_role='primary', offset=0, limit=0)
                tokenizer, model, torch = MagicMock(), MagicMock(), MagicMock()
                tokens = MagicMock()
                tokens.shape = (1, 4000 if mode == 'overflow' else 10)
                tokens.to.return_value = tokens
                tokenizer.apply_chat_template.return_value = tokens
                tokenizer.eos_token_id = 2
                tokenizer.decode.return_value = '{invalid' if mode == 'invalid_json' else valid
                generated = MagicMock()
                generated.__len__.return_value = 1024 if mode == 'truncated' else 5
                generated.__getitem__.return_value.item.return_value = 0 if mode == 'truncated' else 2
                generated.tolist.return_value = [1, 2]
                model.generate.return_value.__getitem__.return_value = generated
                if mode == 'runtime_error':
                    model.generate.side_effect = RuntimeError('Fixture GPU failure')
                model.hf_device_map = {'': 'cuda:0'}
                model.generation_config.eos_token_id = 2
                torch.cuda.device_count.return_value = 3
                torch.cuda.max_memory_allocated.return_value = 100
                runtime = types.SimpleNamespace(AutoTokenizer=MagicMock(), AutoModelForCausalLM=MagicMock())
                runtime.AutoTokenizer.from_pretrained.return_value = tokenizer
                runtime.AutoModelForCausalLM.from_pretrained.return_value = model
                record = {}
                with patch.dict(sys.modules, transformers=runtime), \
                        patch.object(scale_judge, 'verify_checkpoint', return_value={'fixture': 'hash'}):
                    if mode == 'valid':
                        scale_judge.run_judge(args, run, record, self.config, torch)
                    else:
                        with self.assertRaises((ValueError, RuntimeError)):
                            scale_judge.run_judge(args, run, record, self.config, torch)
                self.assertIs(runtime.AutoModelForCausalLM.from_pretrained.call_args.kwargs['use_safetensors'], True)
                self.assertIs(runtime.AutoTokenizer.from_pretrained.call_args.kwargs['fix_mistral_regex'], True)
                self.assertEqual(record['tokenizer_kwargs'], dict(fix_mistral_regex=True))
                row = json.loads((run / 'judgments.jsonl').read_text())
                self.assertEqual(row['judge_failure'], mode != 'valid')
                self.assertNotIn('runtime_failure', row)
                if mode in {'overflow', 'runtime_error'}:
                    self.assertTrue(row['judge_runtime_failure'])
                if mode in {'valid', 'invalid_json', 'truncated'}:
                    self.assertEqual(row['raw_judgment'], tokenizer.decode.return_value)
                    self.assertIn('raw_output_token_ids', row)
                if mode == 'overflow':
                    model.generate.assert_not_called()

    def test_failed_local_main_preserves_manifest_and_input_snapshots(self):
        run = self.run / 'local-rejection'
        run.mkdir()
        with patch.object(scale_judge, 'new_run_dir', return_value=run), \
                patch.object(sys, 'argv', ['scale_judge.py', 'probe', '--run-id', 'local-rejection']), \
                patch.dict(os.environ, {}, clear=True), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(scale_judge.main(), 1)
        record = json.loads((run / 'manifest.json').read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertIn('local judge inference is forbidden', record['error'])
        self.assertFalse(record['judge_validation_complete'])
        self.assertEqual(sha256(run / 'inputs/configs/judges.json'), record['inputs']['configs/judges.json'])


if __name__ == '__main__':
    unittest.main()
