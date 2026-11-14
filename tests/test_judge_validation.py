import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import validate_judges as validation
from samestorm.provenance import sha256


class JudgeComparison(unittest.TestCase):
    def setUp(self):
        self.cases, self.keys, self.questions = {}, {'en': {}, 'es': {}}, {'en': {}, 'es': {}}
        for cid, lang, harmful in [('safe', 'en', False), ('harm', 'en', True), ('es-safe', 'es', False)]:
            action = dict(action_id=cid + '-a', critical=True, text='Required action.')
            status = 'reversal' if harmful else 'correct'
            self.keys[lang][cid] = dict(required_actions=[action])
            self.questions[lang][cid] = dict(question='Fixture question?')
            self.cases[cid] = dict(case_id=cid, item_id=cid, lang=lang, category='fixture',
                                   answer='Response text.', expected_labels=['reversal'] if harmful else [],
                                   expected_annotations=[dict(action_id=action['action_id'], status=status,
                                                              evidence_quote='Response text.')])
        self.spec = dict(model_id='fixture/model', revision='a' * 40,
                         prompt_sha256='b' * 64, prompt_path='configs/prompts/judge_v1.txt')

    def verdict(self, cid, status='correct', role='primary', **changes):
        row = dict(case_id=cid, synthetic=True, judge_role=role, model_id=self.spec['model_id'],
                   model_revision=self.spec['revision'], judge_failure=False,
                   raw_judgment=json.dumps(dict(actions=[dict(action_id=cid + '-a', status=status,
                                                              evidence_quote='' if status in {'missing', 'uncertain'} else 'Response text.')],
                       outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False))))
        return dict(row, **changes)

    def checked(self, rows, role='primary'):
        return validation.checked_judgments(rows, role, self.spec, self.cases, self.keys)

    def student_row(self, cid='safe', status='correct', **changes):
        row = dict(case_id=cid, item_id=cid, action_id=cid + '-a', question='Fixture question?',
                   answer='Response text.', required_action='Required action.', critical='True',
                   status=status, evidence_quote='Response text.' if status == 'correct' else '', comment='')
        return dict(row, **changes)

    def test_raw_verdict_is_rechecked_and_failed_or_uncertain_results_stay_visible(self):
        checked = self.checked([self.verdict('safe'), self.verdict('harm', 'uncertain'),
                                self.verdict('es-safe', judge_failure=True, error='Fixture failure')])
        self.assertFalse(checked['safe']['grade']['harmful'])
        self.assertIsNone(checked['harm']['grade']['harmful'])
        self.assertEqual(checked['es-safe']['state'], 'failed')
        for row in [self.verdict('safe', raw_judgment='{invalid'),
                    self.verdict('safe', grade={'harmful': True}),
                    self.verdict('safe', hit_generation_limit=True)]:
            with self.subTest(row=row):
                result = self.checked([row])['safe']
                self.assertEqual(result['state'], 'failed')
                self.assertIsNone(result['grade'])

    def test_duplicate_unknown_or_wrong_model_records_are_rejected(self):
        for rows in [[self.verdict('safe')] * 2, [self.verdict('unknown')],
                     [self.verdict('safe', role='secondary')], [self.verdict('safe', model_revision='main')]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.checked(rows)

    def test_missing_failed_and_uncertain_cases_remain_in_original_bound_denominators(self):
        primary = self.checked([self.verdict('harm', 'reversal'), self.verdict('safe', 'reversal')])
        # Supply role-consistent secondary records; uncertainty and failure are distinct.
        secondary = self.checked([self.verdict('harm', 'uncertain', role='secondary'),
                                  self.verdict('safe', role='secondary', judge_failure=True)], 'secondary')
        report, details, _ = validation.compare(self.cases, self.keys, dict(primary=primary, secondary=secondary), {})
        en = report['judges']['primary']['provisional_synthetic_metrics']['en']
        self.assertEqual((en['tp'], en['fp']), (1, 1))
        self.assertEqual((en['recall_lower_bound'], en['false_alarm_upper_bound']), (1, 1))
        en = report['judges']['secondary']['provisional_synthetic_metrics']['en']
        self.assertEqual((en['abstain_harm'], en['abstain_safe'], en['failed'], en['uncertain']), (1, 1, 1, 1))
        self.assertEqual((en['recall_lower_bound'], en['false_alarm_upper_bound']), (0, 1))
        es = report['judges']['primary']['provisional_synthetic_metrics']['es']
        self.assertEqual(es['missing'], 1)
        self.assertIsNone(es['recall_lower_bound'])
        self.assertEqual(len(details), 3)

    def test_student_and_judge_agreement_show_their_coverage(self):
        primary = self.checked([self.verdict('safe')])
        secondary = self.checked([self.verdict('safe', role='secondary')], 'secondary')
        students = {('safe', 'safe-a'): 'correct', ('harm', 'harm-a'): 'reversal'}
        report, _, _ = validation.compare(self.cases, self.keys, dict(primary=primary, secondary=secondary), students)
        self.assertEqual(report['judge_action_comparable'], 1)
        self.assertEqual(report['judge_action_agreement'], 1)
        self.assertEqual(report['judges']['primary']['student_action_comparable'], 1)
        self.assertEqual(report['judges']['primary']['student_action_agreement'], .5)
        self.assertFalse(report['validated'])
        self.assertFalse(report['headline_eligible'])

    def test_blank_or_uncertain_student_rows_do_not_become_usable_ratings(self):
        ratings = validation.student_ratings([self.student_row(status=''), self.student_row('harm', 'uncertain')],
                                             self.cases, self.questions, self.keys)
        self.assertEqual(ratings, {('harm', 'harm-a'): 'uncertain'})
        report, _, _ = validation.compare(self.cases, self.keys, dict(primary={}, secondary={}), ratings)
        self.assertEqual(report['usable_student_ratings'], 0)
        self.assertIsNone(report['judge_action_agreement'])
        self.assertIsNone(report['judges']['primary']['student_action_agreement'])

    def test_student_quotes_ids_language_and_worksheet_content_are_checked(self):
        invalid = [[self.student_row()] * 2, [self.student_row(evidence_quote='Invented')],
                   [self.student_row(status='missing', evidence_quote='Response text.')],
                   [self.student_row(status='approved')], [self.student_row('es-safe')],
                   [self.student_row(action_id='unknown')], [self.student_row(answer='Changed response')]]
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                validation.student_ratings(rows, self.cases, self.questions, self.keys)

    def test_run_manifest_rejects_changed_verdicts_or_stale_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'run'
            run.mkdir()
            path = run / 'judgments.jsonl'
            path.write_text(json.dumps(self.verdict('safe')) + '\n')
            relative = ['data/grading/cases.jsonl', 'configs/judges.json', self.spec['prompt_path']]
            relative += [f'{kind}/{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in validation.COUNTS]
            for name in relative:
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('Fixture input')
            record = dict(stage='judge-judge', status='failed', judge_role='primary',
                          model_id=self.spec['model_id'], model_revision=self.spec['revision'],
                          prompt_sha256=self.spec['prompt_sha256'], outputs={'judgments.jsonl': sha256(path)},
                          inputs={name: sha256(root / name) for name in relative})
            (run / 'manifest.json').write_text(json.dumps(record))
            checked, status = validation.read_judge_run(path, 'primary', self.spec, self.cases, self.keys, root)
            self.assertEqual(status, 'failed')  # Partial failed runs still supply their valid records.
            self.assertEqual(len(checked), 1)
            original = path.read_text()
            path.write_text(original + '\n')
            with self.assertRaises(ValueError):
                validation.read_judge_run(path, 'primary', self.spec, self.cases, self.keys, root)
            path.write_text(original)
            (root / 'data/grading/cases.jsonl').write_text('Changed cases')
            with self.assertRaises(ValueError):
                validation.read_judge_run(path, 'primary', self.spec, self.cases, self.keys, root)


class JudgeComparisonCommand(unittest.TestCase):
    def test_no_results_report_preserves_pending_state_and_student_sheet(self):
        original = (ROOT / 'data/grading/student_review.csv').read_bytes()
        usable_rows = sum(row['status'].strip() not in {'', 'uncertain'}
                          for row in csv.DictReader(io.StringIO(original.decode('utf-8'))))
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with patch.object(validation, 'new_run_dir', return_value=run), \
                    patch.object(sys, 'argv', ['validate_judges.py', '--run-id', 'pending']), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(validation.main(), 0)
            report = json.loads((run / 'judge_validation_report.json').read_text())
            self.assertFalse(report['results_present'])
            self.assertFalse(report['validated'])
            self.assertFalse(report['headline_eligible'])
            self.assertEqual(report['usable_student_ratings'], usable_rows)
            self.assertEqual(report['input_run_status'], dict(primary='not_supplied', secondary='not_supplied'))
            self.assertEqual(len(validation.read_rows(run / 'case_comparisons.jsonl')), 115)
            self.assertEqual((run / 'student_review.csv').read_bytes(), original)
        self.assertEqual((ROOT / 'data/grading/student_review.csv').read_bytes(), original)

    def test_bad_student_file_is_preserved_in_failed_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'failed'
            run.mkdir()
            with (ROOT / 'data/grading/student_review.csv').open(newline='') as stream:
                rows = list(csv.DictReader(stream))
            rows[0]['status'] = 'invented'
            sheet = root / 'bad.csv'
            with sheet.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with patch.object(validation, 'new_run_dir', return_value=run), \
                    patch.object(sys, 'argv', ['validate_judges.py', '--run-id', 'failed', '--student-review', str(sheet)]), \
                    contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(validation.main(), 1)
            self.assertEqual((run / 'student_review.csv').read_bytes(), sheet.read_bytes())
            record = json.loads((run / 'manifest.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertIn('Invalid student action status', record['error'])


if __name__ == '__main__':
    unittest.main()
