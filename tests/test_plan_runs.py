import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from plan_runs import build_plan


class RunPlanning(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.settings = json.loads((ROOT / 'configs/experiment.json').read_text())
        self.models = [dict(id=name, revision='a' * 40, reference='F16',
                            reference_path=f'models/{name}/model-F16.gguf') for name in ['small', 'large']]
        self.metadata = [dict(item_id=f'family{n:02}-{role}', family_id=f'family{n:02}', role=role,
                              hazard='fixture', languages_available=['en', 'es', 'vi'] + (['zh'] if n < 10 else []))
                         for n in range(12) for role in ['base', 'p1', 'p2', 'cf1']]

    def test_complete_matrix_and_repeat_counts(self):
        plan = build_plan(self.root, self.settings, self.models, self.metadata)
        self.assertEqual(len(plan['jobs']), 12)
        self.assertEqual((plan['primary_answers'], plan['repeat_answers'], plan['total_answers']), (2208, 228, 2436))
        self.assertEqual(plan['repeat_counts_by_language'], dict(en=5, es=5, vi=5, zh=4))
        self.assertTrue(all(len(job['primary_example_ids']) == 184 for job in plan['jobs']))
        self.assertTrue(all(job['repeat_example_ids'] == plan['repeat_example_ids'] for job in plan['jobs']))
        self.assertFalse(plan['execution_authorized'])

    def test_repeat_selection_is_stable_and_always_uses_real_examples(self):
        first = build_plan(self.root, self.settings, self.models, self.metadata)
        reordered = build_plan(self.root, self.settings, self.models, list(reversed(self.metadata)))
        self.assertEqual(first, reordered)
        ids = {row['example_id'] for row in first['examples']}
        self.assertEqual(len(first['repeat_example_ids']), len(set(first['repeat_example_ids'])))
        self.assertTrue(set(first['repeat_example_ids']) <= ids)

    def test_missing_empty_and_unverified_models_are_distinguished(self):
        folder = self.root / 'models/small'
        folder.mkdir(parents=True)
        (folder / 'model-F16.gguf').write_bytes(b'')
        (folder / 'model-Q8_0.gguf').write_bytes(b'synthetic, not a valid model')
        plan = build_plan(self.root, self.settings, self.models, self.metadata)
        self.assertEqual([job['artifact_status'] for job in plan['jobs'][:3]], ['empty', 'present_unverified', 'missing'])
        self.assertEqual(len(plan['missing_model_files']), 10)
        self.assertFalse(plan['execution_authorized'])

    def test_empty_duplicate_or_unpinned_models_are_rejected(self):
        for models in [[], self.models + self.models[:1], [dict(self.models[0], revision='main')],
                       [dict(self.models[0], reference='Q8_0')],
                       [dict(self.models[0], reference_path='../escape.gguf')]]:
            with self.subTest(models=models), self.assertRaises(ValueError):
                build_plan(self.root, self.settings, models, self.metadata)

    def test_duplicate_examples_and_invalid_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            build_plan(self.root, self.settings, self.models, self.metadata + self.metadata[:1])
        changed = copy.deepcopy(self.settings)
        changed['decoding']['temperature'] = 1
        with self.assertRaises(ValueError):
            build_plan(self.root, changed, self.models, self.metadata)


if __name__ == '__main__':
    unittest.main()
