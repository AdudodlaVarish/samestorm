import contextlib
import io
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import prepare_grading_stress as assembly
import scale_judge as worker
import validate_grading as preparation
import validate_judges as comparison
from samestorm.judges import load_config
from samestorm.provenance import sha256

CASES = 'data/grading/multilingual_stress_v1/cases.jsonl'


class MultilingualStress(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.cases = preparation.read_rows(ROOT / CASES)
        self.config = load_config(ROOT)
        self.keys = {l: preparation.load_items(ROOT / f'answers/answers.{l}.jsonl') for l in preparation.COUNTS}

    def command(self, module, name, *args, expected=0):
        run = self.directory / name
        run.mkdir()
        with patch.object(module, 'new_run_dir', return_value=run), \
                patch.object(sys, 'argv', [module.__name__, '--run-id', name, *args]), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), expected)
        return run

    def test_assembly_keeps_all_pairs_replaces_only_accepted_designs_and_keeps_flags(self):
        actual = assembly.assemble(ROOT)
        self.assertEqual(actual, self.cases)
        self.assertEqual(len(actual), 180)
        self.assertEqual(len({c['review']['original_case_id'] for c in actual}), 180)
        self.assertEqual(len({c['review']['original_pair_id'] for c in actual}), 90)
        self.assertEqual(Counter(c['review']['source_revision'] for c in actual), {'r2': 28, 'original': 152})
        for lang in ['es', 'vi', 'zh']:
            subset = [c for c in actual if c['lang'] == lang]
            self.assertEqual(len(subset), 60)
            self.assertEqual(sum(bool(c['expected_labels']) for c in subset), 30)
        self.assertEqual(sum(c['review']['english_evidence'] != 'consistent English evidence' for c in actual), 78)
        self.assertTrue(all(c['independent_human_labels'] is False and not c['review']['native_language_verified'] for c in actual))
        selection = json.loads((ROOT / CASES).with_name('selection_manifest.json').read_text())
        self.assertEqual(selection['outputs']['cases.jsonl'], sha256(ROOT / CASES))
        for relative, digest in selection['inputs'].items():
            self.assertEqual(sha256(ROOT / relative), digest)

    def test_prepare_and_both_worker_roles_use_custom_cases_without_labels_or_review_leakage(self):
        run = self.command(preparation, 'prepared', '--cases', CASES)
        tasks = run / 'judge_validation_tasks.jsonl'
        manifest = json.loads((run / 'manifest.json').read_text())
        self.assertEqual(manifest['cases_path'], CASES)
        self.assertEqual(manifest['inputs'][CASES], sha256(ROOT / CASES))
        self.assertEqual(sha256(run / 'inputs' / CASES), sha256(ROOT / CASES))
        report = json.loads((run / 'report.json').read_text())
        self.assertEqual(report['judge_tasks'], 180)
        self.assertEqual(report['student_review_rows'], 0)
        for role in ['primary', 'secondary']:
            loaded = worker.validation_tasks(ROOT, tasks, self.config[role], cases_path=CASES)
            self.assertEqual(len(loaded), 180)
            self.assertEqual(len(worker.validation_tasks(ROOT, tasks, self.config[role], 2, 10, CASES)), 10)
        for row in preparation.read_rows(tasks):
            payload = json.loads(row['messages'][1]['content'])
            self.assertEqual(set(payload), {'item_id', 'language', 'question', 'answer', 'required_actions', 'official_sources'})
            self.assertEqual(set(row), {'case_id', 'synthetic', 'messages'})
        with self.assertRaisesRegex(ValueError, 'case ID'):
            worker.validation_tasks(ROOT, tasks, self.config['primary'])

    def verdict_run(self):
        run = self.directory / 'fixture-judge'
        run.mkdir()
        spec = self.config['primary']
        case = self.cases[0]
        raw = json.dumps(dict(actions=case['expected_annotations'], outcomes=dict(
            refusal=False, wrong_language=False, runtime_failure=False)))
        preparation.write_rows(run / 'judgments.jsonl', [dict(case_id=case['case_id'], synthetic=True,
            judge_role='primary', model_id=spec['model_id'], model_revision=spec['revision'],
            judge_failure=False, hit_generation_limit=False, raw_judgment=raw)])
        paths = [CASES, 'configs/judges.json', spec['prompt_path']]
        paths += [f'{kind}/{kind}.{l}.jsonl' for kind in ['questions', 'answers'] for l in preparation.COUNTS]
        manifest = dict(stage='judge-judge', status='complete', cases_path=CASES, judge_role='primary',
            model_id=spec['model_id'], model_revision=spec['revision'], prompt_sha256=spec['prompt_sha256'],
            inputs={p: sha256(ROOT / p) for p in paths}, outputs={'judgments.jsonl': sha256(run / 'judgments.jsonl')})
        (run / 'manifest.json').write_text(json.dumps(manifest))
        return run / 'judgments.jsonl'

    def test_comparison_keeps_missing_and_flagged_cases_and_does_not_reuse_english_ratings(self):
        path = self.verdict_run()  # Constructed test verdict, never model inference.
        run = self.command(comparison, 'comparison', '--cases', CASES, '--primary', str(path))
        report = json.loads((run / 'judge_validation_report.json').read_text())
        self.assertEqual(report['cases_path'], CASES)
        self.assertEqual(report['cases_sha256'], sha256(ROOT / CASES))
        self.assertEqual(report['student_ratings'], 0)
        self.assertFalse(report['student_review_supplied'])
        self.assertIsNone(report['judges']['primary']['student_action_agreement'])
        self.assertEqual(report['judges']['primary']['recorded_cases'], 1)
        self.assertEqual(report['development_review_coverage']['pairs'], 90)
        self.assertEqual(report['development_review_coverage']['english_evidence_pair_counts'],
                         {'consistent English evidence': 51, 'discrepancy': 31, 'uncertain': 8})
        self.assertEqual(report['development_review_coverage']['flagged_cases'], 78)
        self.assertEqual(report['development_review_coverage']['native_language_verified_cases'], 0)
        self.assertEqual(len(preparation.read_rows(run / 'case_comparisons.jsonl')), 180)
        self.assertIn('review', preparation.read_rows(run / 'case_comparisons.jsonl')[0])
        self.assertFalse(report['validated'])
        self.assertFalse(report['headline_eligible'])
        self.assertFalse((run / 'student_review.csv').exists())
        self.assertFalse(any('Harmful injected cases are English only' in x for x in report['limitations']))

    def test_run_provenance_rejects_wrong_case_path_and_hash(self):
        path = self.verdict_run()
        cases = {c['case_id']: c for c in self.cases}
        with self.assertRaisesRegex(ValueError, 'different case file'):
            comparison.read_judge_run(path, 'primary', self.config['primary'], cases, self.keys, ROOT)
        checked, _ = comparison.read_judge_run(path, 'primary', self.config['primary'], cases, self.keys, ROOT, cases_path=CASES)
        self.assertEqual(len(checked), 1)
        meta = path.parent / 'manifest.json'
        record = json.loads(meta.read_text())
        record['inputs'][CASES] = '0' * 64
        meta.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'different or unrecorded inputs'):
            comparison.read_judge_run(path, 'primary', self.config['primary'], cases, self.keys, ROOT, cases_path=CASES)

    def test_explicit_unrelated_student_sheet_fails_instead_of_creating_fake_agreement(self):
        run = self.command(comparison, 'bad-sheet', '--cases', CASES, '--student-review',
                           str(ROOT / 'data/grading/student_review.csv'), expected=1)
        self.assertEqual(json.loads((run / 'manifest.json').read_text())['status'], 'failed')
        self.assertTrue((run / 'student_review.csv').exists())

    def test_case_path_escape_rejected(self):
        run = self.command(preparation, 'escape', '--cases', '../samestorm/data/grading/cases.jsonl', expected=1)
        self.assertEqual(json.loads((run / 'manifest.json').read_text())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
