import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from validate_experiment import validate


class ExperimentValidation(unittest.TestCase):
    def setUp(self):
        self.settings = json.loads((ROOT / 'configs/experiment.json').read_text())

    def test_valid_reference_modes(self):
        self.assertEqual(validate(self.settings), [])
        self.settings['reference_precision'] = 'BF16'
        self.settings['precisions'][0] = 'BF16'
        self.assertEqual(validate(self.settings), [])

    def test_quantized_reference_is_rejected(self):
        self.settings['reference_precision'] = 'Q8_0'
        self.assertTrue(any('never a quantized' in error for error in validate(self.settings)))

    def test_incomplete_duplicate_and_nonstring_precisions_are_rejected(self):
        for precisions in [['F16'], ['F16'] * 6, ['F16', 'BF16', 'Q6_K', 'Q4_K_M', 'Q3_K_M', 'Q2_K'],
                           ['F16', 'Q8_0', 'Q6_K', 'Q4_K_M', 'Q3_K_M', []]]:
            with self.subTest(precisions=precisions):
                self.settings['precisions'] = precisions
                self.assertTrue(validate(self.settings))

    def test_decoding_drift_and_boolean_numbers_are_rejected(self):
        for field, value in [('temperature', 0.7), ('temperature', False), ('top_k', True),
                             ('repeat_penalty', 1.2), ('max_tokens', 640)]:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(self.settings)
                changed['decoding'][field] = value
                self.assertTrue(validate(changed))

    def test_context_modes_seed_and_repeat_drift_are_rejected(self):
        for field, value in [('context_tokens', 8192), ('thinking', True), ('thinking', 0),
                             ('retrieval', 'oracle'), ('use_model_chat_template', False),
                             ('seed', -1), ('seed', True), ('determinism_repeat_fraction', 0.2)]:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(self.settings)
                changed[field] = value
                self.assertTrue(validate(changed))

    def test_missing_and_malformed_objects_are_rejected(self):
        for value in [None, [], {}, dict(self.settings, decoding=[]), dict(self.settings, reference_precision=[])]:
            with self.subTest(value=value):
                self.assertTrue(validate(value))


if __name__ == '__main__':
    unittest.main()
