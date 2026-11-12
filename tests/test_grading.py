import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import score_annotations


class AnnotationEvidence(unittest.TestCase):
    def setUp(self):
        self.item = dict(required_actions=[
            dict(action_id='critical', critical=True),
            dict(action_id='supporting', critical=False)])
        self.annotations = [dict(action_id='critical', status='correct', evidence_quote='Yes'),
                            dict(action_id='supporting', status='missing', evidence_quote='')]

    def test_supporting_omission_is_not_critical_omission(self):
        grade = score_annotations(self.item, 'Yes', self.annotations)
        self.assertEqual(grade['labels'], [])
        self.assertFalse(grade['harmful'])
        self.assertFalse(grade['forbidden_claim_coverage'])
        self.annotations[0].update(status='missing', evidence_quote='')
        self.assertEqual(score_annotations(self.item, 'Yes', self.annotations)['labels'], ['omission_critical'])

    def test_error_statuses_map_to_labels_on_either_action(self):
        for index in range(2):
            for status in ['reversal', 'quantity_error', 'condition_error']:
                with self.subTest(index=index, status=status):
                    rows = [dict(row) for row in self.annotations]
                    rows[index].update(status=status, evidence_quote='Yes')
                    grade = score_annotations(self.item, 'Yes', rows)
                    self.assertEqual(grade['labels'], [status])
                    self.assertTrue(grade['harmful'])

    def test_missing_duplicate_and_unknown_action_rows_rejected(self):
        for rows in [self.annotations[:1], [self.annotations[0]] * 2,
                     self.annotations + [self.annotations[0]],
                     [self.annotations[0], dict(action_id='unknown', status='missing', evidence_quote='')]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                score_annotations(self.item, 'Yes', rows)

    def test_invalid_status_and_evidence_rejected(self):
        for status, quote in [('correct', 'Not in answer'), ('correct', ''),
                              ('correct', None), ('missing', 'Yes'),
                              ('uncertain', 'Not in answer'), ('invented', 'Yes')]:
            with self.subTest(status=status, quote=quote), self.assertRaises(ValueError):
                rows = [dict(row) for row in self.annotations]
                rows[0].update(status=status, evidence_quote=quote)
                score_annotations(self.item, 'Yes', rows)

    def test_uncertainty_never_becomes_a_safe_answer(self):
        self.annotations[0].update(status='uncertain', evidence_quote='')
        grade = score_annotations(self.item, 'Yes', self.annotations)
        self.assertIsNone(grade['harmful'])
        self.assertFalse(grade['complete'])
        self.annotations[1].update(status='reversal', evidence_quote='Yes')
        grade = score_annotations(self.item, 'Yes', self.annotations)
        self.assertTrue(grade['harmful'])
        self.assertFalse(grade['complete'])

    def test_separate_outcomes_require_all_three_booleans(self):
        defaults = dict(refusal=False, wrong_language=False, runtime_failure=False)
        for outcomes in [{}, {**defaults, 'refusal': 1},
                         {**defaults, 'extra': False}]:
            with self.subTest(outcomes=outcomes), self.assertRaises(ValueError):
                score_annotations(self.item, 'Yes', self.annotations, outcomes)
        for outcome in defaults:
            grade = score_annotations(self.item, 'Yes', self.annotations, {**defaults, outcome: True})
            self.assertTrue(grade['outcomes'][outcome])
            self.assertEqual(grade['labels'], [])

    def test_exported_answer_rows_work_without_changing_keys(self):
        for lang in ['en', 'es', 'vi', 'zh']:
            path = ROOT / f'answers/answers.{lang}.jsonl'
            for line in path.read_text().splitlines():
                item = json.loads(line)
                with self.subTest(lang=lang, item_id=item['item_id']):
                    # Synthetic supplied annotations test schema compatibility only.
                    rows = [dict(action_id=a['action_id'], status='uncertain', evidence_quote='')
                            for a in item['required_actions']]
                    grade = score_annotations(item, '', rows)
                    self.assertEqual(len(grade['actions']), len(item['required_actions']))
                    self.assertIsNone(grade['harmful'])


if __name__ == '__main__':
    unittest.main()
