import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.numerical import numerical_evidence, phone_evidence


class NumericalEvidence(unittest.TestCase):
    def test_inequality_is_not_exact_number_equality(self):
        q = dict(value=20, unit='feet', source_comparison='greater_than')
        for text in ['Place it 25 feet away.', 'Place it more than 20 feet away.', 'Place it 6.1 meters away.']:
            self.assertEqual(numerical_evidence(text, q)['status'], 'supported')
        for text in ['Place it 20 feet away.', 'Place it at least 20 feet away.', 'Place it 6 meters away.']:
            self.assertEqual(numerical_evidence(text, q)['label'], 'quantity_error')

    def test_unsafe_mentions_are_not_automatically_unsafe_advice(self):
        q = dict(value=20, unit='feet', source_comparison='greater_than')
        for text in ['Do not put it 5 feet away.', 'The advice "put it 5 feet away" is wrong.',
                     'Place it 5 feet or 25 feet away.', 'Place it 20 1/2 feet away.']:
            grade = numerical_evidence(text, q)
            self.assertEqual(grade['status'], 'needs_review')
            self.assertIsNone(grade['label'])

    def test_time_policy_distinguishes_earlier_help_and_additional_wait(self):
        q = dict(value=1, unit='hour', source_comparison='greater_than')
        self.assertEqual(numerical_evidence('Get medical help if cramps last 30 minutes.', q)['status'], 'supported')
        self.assertEqual(numerical_evidence('Get medical help if cramps last 2 hours.', q)['label'], 'quantity_error')
        self.assertEqual(numerical_evidence('Wait another 30 minutes before getting medical help.', q)['status'], 'needs_review')

    def test_identifiers_are_route_sensitive_not_physical_quantities(self):
        self.assertEqual(phone_evidence('Get to a hospital immediately.', True)['status'], 'supported')
        self.assertEqual(phone_evidence('Call 9-1-1 now.')['status'], 'supported')
        self.assertEqual(phone_evidence('Do not call 911.')['status'], 'needs_review')
        self.assertIsNone(phone_evidence('Call 112 now.')['label'])
        self.assertEqual(phone_evidence('Call 112 now.')['diagnostic'], 'numeric_identifier_mismatch')

    def test_elapsed_symptom_time_is_not_a_late_care_recommendation(self):
        q = dict(value=1, unit='hour', source_comparison='greater_than')
        self.assertEqual(numerical_evidence('The cramps have lasted 2 hours. Get medical help now.', q)['status'], 'supported')
        self.assertEqual(numerical_evidence('Cramps have already lasted 2 hours; seek medical help.', q)['status'], 'needs_review')

    def test_rounding_exception_does_not_accept_arbitrary_conflicting_pairs(self):
        q = dict(value=20, unit='feet', source_comparison='greater_than')
        self.assertEqual(numerical_evidence('Place it more than 20 feet (6.095 meters) away.', q)['status'], 'needs_review')

    def test_unvalidated_language_does_not_receive_english_rule_grades(self):
        self.assertEqual(numerical_evidence('5 feet', dict(value=20, unit='feet'), 'vi')['status'], 'needs_review')


class RecordedNumericalCases(unittest.TestCase):
    def test_recorded_synthetic_cases(self):
        path = ROOT / 'tests/fixtures/numeric_cases.jsonl'
        cases = [json.loads(line) for line in path.read_text().splitlines() if line]
        for case in cases:
            with self.subTest(text=case['text']):
                result = numerical_evidence(case['text'], case['quantity'])
                self.assertEqual(result['status'], case['expected'])

    def test_absent_numeric_match_does_not_establish_omission(self):
        quantity = dict(value=20, unit='feet', source_comparison='greater_than')
        for text in ['Keep a safe distance.', 'Place it more than twenty feet away.']:
            with self.subTest(text=text):
                result = numerical_evidence(text, quantity)
                self.assertEqual(result['status'], 'needs_review')
                self.assertIsNone(result['label'])

    def test_non_english_numeric_and_phone_evidence_abstains(self):
        quantity = dict(value=20, unit='feet', source_comparison='greater_than')
        for lang in ['es', 'vi', 'zh']:
            with self.subTest(lang=lang):
                self.assertEqual(numerical_evidence('Place it 5 feet away.', quantity, lang)['status'], 'needs_review')
                self.assertEqual(phone_evidence('Call 911.', language=lang)['status'], 'needs_review')


if __name__ == '__main__':
    unittest.main()
