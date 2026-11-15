import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import scale_judge as worker
import validate_grading as preparation
import validate_judges as comparison
from samestorm.judges import config_paths, load_config
from samestorm.provenance import sha256

CASES = 'data/grading/multilingual_stress_v1/cases.jsonl'


class JudgePromptVersion(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def command(self, module, name, *args, expected=0):
        run = self.directory / name
        run.mkdir()
        with patch.object(module, 'new_run_dir', return_value=run), \
                patch.object(sys, 'argv', [module.__name__, '--run-id', name, *args]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), expected)
        return run

    def test_v1_default_unchanged_and_v2_changes_only_prompt_selection(self):
        original = json.loads((ROOT / 'configs/judges.json').read_text())
        self.assertEqual(load_config(ROOT), original)
        updated = load_config(ROOT, 'v2')
        for role in ['primary', 'secondary']:
            spec = dict(updated[role])
            self.assertNotEqual(spec['prompt_sha256'], original[role]['prompt_sha256'])
            for field in ['prompt_path', 'prompt_sha256']:
                spec[field] = original[role][field]
            self.assertEqual(spec.pop('prompt_revision_path'), 'configs/judge_prompt_v2.json')
            self.assertEqual(spec, original[role])
        with self.assertRaises(ValueError):
            load_config(ROOT, 'unknown')

    def test_changed_v2_prompt_is_rejected(self):
        root = self.directory / 'repo'
        for path in config_paths(ROOT, load_config(ROOT, 'v2')):
            target = root / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        (root / 'configs/prompts/judge_v2.txt').write_text('Unpinned instructions.')
        with self.assertRaisesRegex(ValueError, 'prompt differs from its pin'):
            load_config(root, 'v2')

    def test_v2_preparation_worker_checks_and_version_isolation(self):
        prepared = self.command(preparation, 'prepare', '--cases', CASES, '--prompt-version', 'v2')
        tasks = prepared / 'judge_validation_tasks.jsonl'
        config = load_config(ROOT, 'v2')
        for role in ['primary', 'secondary']:
            loaded = worker.validation_tasks(ROOT, tasks, config[role], cases_path=CASES)
            self.assertEqual(len(loaded), 180)
            run = self.command(worker, role, 'check', '--cases', CASES, '--prompt-version', 'v2',
                               '--input', str(tasks), '--judge-role', role)
            record = json.loads((run / 'manifest.json').read_text())
            self.assertEqual(record['prompt_version'], 'judge_v2')
            for path in config_paths(ROOT, config):
                relative = str(path.relative_to(ROOT))
                self.assertEqual(record['inputs'][relative], sha256(path))
                self.assertEqual(sha256(run / 'inputs' / relative), sha256(path))
            self.assertEqual(json.loads((run / 'setup_report.json').read_text())['valid_tasks'], 180)
        with self.assertRaisesRegex(ValueError, 'pinned prompt'):
            worker.validation_tasks(ROOT, tasks, load_config(ROOT)['primary'], cases_path=CASES)
        for row in preparation.read_rows(tasks):
            self.assertEqual(set(row), {'case_id', 'synthetic', 'messages'})
            payload = json.loads(row['messages'][1]['content'])
            self.assertEqual(set(payload), {'item_id', 'language', 'question', 'answer',
                                           'required_actions', 'official_sources'})

    def test_comparison_preserves_version_and_rejects_mixed_or_unrecorded_protocol(self):
        config = load_config(ROOT, 'v2')
        spec = config['primary']
        case = preparation.read_rows(ROOT / CASES)[0]
        source = self.directory / 'fixture-v2'
        source.mkdir()
        path = source / 'judgments.jsonl'
        raw = json.dumps(dict(actions=case['expected_annotations'], outcomes=dict(
            refusal=False, wrong_language=False, runtime_failure=False)))
        preparation.write_rows(path, [dict(case_id=case['case_id'], synthetic=True, judge_role='primary',
            model_id=spec['model_id'], model_revision=spec['revision'], judge_failure=False,
            hit_generation_limit=False, raw_judgment=raw)])
        paths = [ROOT / CASES, *config_paths(ROOT, config)]
        paths += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers']
                  for lang in preparation.COUNTS]
        record = dict(stage='judge-judge', status='complete', cases_path=CASES,
            prompt_version='judge_v2', judge_role='primary', model_id=spec['model_id'],
            model_revision=spec['revision'], prompt_sha256=spec['prompt_sha256'],
            inputs={str(p.relative_to(ROOT)):sha256(p) for p in paths},
            outputs={path.name:sha256(path)})
        manifest_path = source / 'manifest.json'
        manifest_path.write_text(json.dumps(record))
        before = path.read_bytes()
        run = self.command(comparison, 'compare', '--cases', CASES, '--prompt-version', 'v2',
                           '--primary', str(path))
        report = json.loads((run / 'judge_validation_report.json').read_text())
        self.assertEqual(report['prompt_version'], 'judge_v2')
        self.assertEqual(report['judges']['primary']['recorded_cases'], 1)
        self.assertTrue(any('development regression' in x for x in report['limitations']))
        self.assertFalse(report['validated'])
        self.command(comparison, 'wrong-version', '--cases', CASES, '--primary', str(path), expected=1)
        del record['inputs'][spec['prompt_revision_path']]
        manifest_path.write_text(json.dumps(record))
        self.command(comparison, 'missing-protocol', '--cases', CASES, '--prompt-version', 'v2',
                     '--primary', str(path), expected=1)
        self.assertEqual(path.read_bytes(), before)

    def test_v2_response_crossgrading_rejected_before_runtime_probe(self):
        with patch.object(worker, 'probe') as probe:
            run = self.command(worker, 'unsupported', 'judge', '--task-kind', 'crossgrade',
                               '--prompt-version', 'v2', expected=1)
        probe.assert_not_called()
        self.assertIn('only the v1 prompt', json.loads((run / 'manifest.json').read_text())['error'])


if __name__ == '__main__':
    unittest.main()
