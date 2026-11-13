import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.analysis import paired_analysis


class PairedAnalysis(unittest.TestCase):
    def test_empty_or_repeat_only_input_is_not_a_result(self):
        for rows in [[], [dict(repeat_index=1)]]:
            with self.assertRaises(ValueError):
                paired_analysis(rows, [], 'answer_any_harmful')

    def setUp(self):
        self.items = [dict(item_id='f-' + role, family_id='f', languages_available=['en', 'vi'])
                      for role in ['base', 'cf']]
        self.rows = []
        for language in ['en', 'vi']:
            for precision in ['F16', 'Q4_K_M']:
                for role, count in [('base', 1), ('cf', 3)]:
                    bad = language == 'vi' and precision == 'Q4_K_M' and role == 'base'
                    actions = [dict(critical=True, status='reversal' if bad else 'correct',
                                    label='reversal' if bad else None) for _ in range(count)]
                    self.rows.append(dict(model_id='fixture', quantization_type=precision,
                                          item_id='f-' + role, family_id='f', lang=language,
                                          grade=dict(complete=True, harmful=bad, actions=actions)))

    def test_tax_uses_language_english_difference_and_true_action_denominator(self):
        answers = paired_analysis(self.rows, self.items, 'answer_any_harmful', 100)
        actions = paired_analysis(self.rows, self.items, 'critical_action_error', 100)
        self.assertEqual(answers['results'][0]['additional_tax'], .5)
        self.assertEqual(actions['results'][0]['additional_tax'], .25)
        self.assertEqual(actions['results'][0]['bootstrap_unit'], 'scenario_family')

    def test_missing_paired_grade_never_becomes_correct(self):
        result = paired_analysis(self.rows[:-1], self.items, 'answer_any_harmful', 100)
        self.assertEqual(result['results'], [])

    def test_q8_is_never_reference_and_synthetic_data_never_becomes_results(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            if r['quantization_type'] == 'F16':
                r['quantization_type'] = 'Q8_0'
        with self.assertRaises(ValueError):
            paired_analysis(rows, self.items, 'answer_any_harmful', 100)
        self.rows[0]['synthetic'] = True
        with self.assertRaises(ValueError):
            paired_analysis(self.rows, self.items, 'answer_any_harmful', 100)


if __name__ == '__main__':
    unittest.main()
