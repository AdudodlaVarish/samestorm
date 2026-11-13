import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import analyze_results as analysis
from samestorm.analysis import paired_analysis
from samestorm.grading import mechanical_grade


class AnalysisPipeline(unittest.TestCase):
    def setUp(self):
        self.row = dict(model_id='fixture', model_revision='a' * 40, quantization_type='F16',
                        item_id='family-base', family_id='family', hazard='fixture', lang='en',
                        example_id='family-base:en', repeat_index=0, runtime_failure=False, answer='Fixture answer.')
        self.task = dict(target_model_id='fixture', target_model_revision='a' * 40,
                         quantization_type='F16', example_id='family-base:en', case_id='native',
                         cross_grade=False, secondary_selected=False)
        self.grade = dict(complete=True, harmful=False, actions=[dict(action_id='a', critical=True,
                          status='correct', label=None)], outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False))
        self.plan = dict(jobs=[dict(job_index=0, model_id='fixture', model_revision='a' * 40, precision='F16',
                                   primary_example_ids=['family-base:en'], repeat_example_ids=['family-base:en'])])

    def test_primary_secondary_and_runtime_failures_stay_separate(self):
        judgments = dict(primary={'native': dict(state='valid', grade=self.grade)}, secondary={})
        streams = analysis.streams([self.row, dict(self.row, repeat_index=1)], [self.task], judgments)
        self.assertEqual(len(streams['primary']), 1)
        self.assertEqual(streams['primary'][0]['grade'], self.grade)
        self.assertEqual(streams['secondary'][0]['grade_state'], 'not_selected')
        self.assertNotIn('grade', streams['secondary'][0])
        failed = analysis.streams([dict(self.row, runtime_failure=True)], [], dict(primary={}, secondary={}))
        grade = failed['primary'][0]['grade']
        self.assertIsNone(grade['harmful'])
        self.assertTrue(grade['outcomes']['runtime_failure'])

    def test_cell_rates_do_not_turn_ungraded_or_unobserved_into_correct(self):
        rows = analysis.streams([self.row], [self.task], dict(primary={}, secondary={}))['primary']
        en = next(r for r in analysis.cell_rates(rows, self.plan) if r['lang'] == 'en')
        self.assertEqual(en['generated_primary_answers'], 1)
        self.assertEqual(en['known_answer_grades'], 0)
        self.assertEqual(en['outcome_unassessed'], 1)
        self.assertIsNone(en['answer_any_harmful'])
        self.assertIsNone(en['critical_action_error'])
        en = next(r for r in analysis.cell_rates([], self.plan) if r['lang'] == 'en')
        self.assertEqual(en['not_generated'], 1)

    def test_missing_reference_blocks_estimate_and_never_promotes_q8(self):
        row = dict(self.row, grade=self.grade, quantization_type='Q8_0')
        report = analysis.analyze_stream([row], [], 'answer_any_harmful', 100)
        self.assertEqual(report['results'], [])
        self.assertEqual(report['models_missing_reference'], ['fixture'])

    def test_repeat_checks_compare_exact_text_and_keep_missing_pairs_unresolved(self):
        repeat = dict(self.row, repeat_index=1, answer='Changed answer.')
        check = analysis.determinism([self.row, repeat], self.plan)[0]
        self.assertEqual(check['state'], 'comparable')
        self.assertFalse(check['exact_text_match'])
        check = analysis.determinism([self.row], self.plan)[0]
        self.assertEqual(check['state'], 'missing_partner')
        self.assertIsNone(check['exact_text_match'])

    def test_family_coverage_names_the_missing_pair_cell(self):
        items = [dict(item_id='family-base', family_id='family', languages_available=['en', 'es'])]
        quant = dict(self.plan['jobs'][0], precision='Q4_K_M', job_index=1)
        plan = dict(jobs=self.plan['jobs'] + [quant], settings=dict(reference_precision='F16'))
        rows = [dict(self.row, lang=lang, quantization_type=precision, grade=self.grade)
                for precision in ['F16', 'Q4_K_M'] for lang in ['en', 'es']]
        coverage = analysis.paired_coverage(rows, items, plan, 'answer_any_harmful')
        self.assertEqual(next(c for c in coverage if c['lang'] == 'es')['complete_families'], ['family'])
        coverage = analysis.paired_coverage(rows[:-1], items, plan, 'answer_any_harmful')
        missing = next(c for c in coverage if c['lang'] == 'es')['incomplete_families']
        self.assertEqual(missing['family']['es/Q4_K_M'], ['family-base'])

    def test_physical_records_reject_duplicate_cohorts_and_synthetic_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['collected', 'prepared', 'generation1', 'generation2']:
                (root / name).mkdir()
            (root / 'collected/manifest.json').write_text(json.dumps(dict(prepared_run='prepared')))
            paths = ['generation1/answers.jsonl', 'generation2/answers.jsonl']
            for n in [1, 2]:
                path = root / f'generation{n}/answers.jsonl'
                path.write_text(json.dumps(self.row) + '\n')
                (path.parent / 'manifest.json').write_text(json.dumps(dict(run_id=f'g{n}', outputs={'answers.jsonl': 'fixture-hash'})))
            metadata = {'family-base': dict(family_id='family', hazard='fixture', split='dev', languages_available=['en'])}
            (root / 'prepared/manifest.json').write_text(json.dumps(dict(answer_files=paths[:1])))
            with patch.object(analysis, 'generation_answers'):
                records = analysis.physical_records(root, root / 'collected', metadata)
                self.assertEqual(records[0]['source_generation_run_id'], 'g1')
                (root / 'prepared/manifest.json').write_text(json.dumps(dict(answer_files=paths)))
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    analysis.physical_records(root, root / 'collected', metadata)
                (root / 'prepared/manifest.json').write_text(json.dumps(dict(answer_files=paths[:1])))
                (root / paths[0]).write_text(json.dumps(dict(self.row, synthetic=True)) + '\n')
                with self.assertRaisesRegex(ValueError, 'Synthetic'):
                    analysis.physical_records(root, root / 'collected', metadata)

    def test_mechanical_evidence_is_partial_and_nonenglish_abstains(self):
        key = dict(required_actions=[dict(action_id='a', critical=True,
                   quantity=dict(value=20, unit='feet', source_comparison='greater_than'))])
        evidence = mechanical_grade(key, 'Place it 5 feet away.', 'en')
        self.assertEqual(evidence['labels'], ['quantity_error'])
        self.assertFalse(evidence['semantic_complete'])
        self.assertFalse(evidence['headline_eligible'])
        other = mechanical_grade(key, 'Place it 5 feet away.', 'vi')
        self.assertEqual(other['labels'], [])
        self.assertEqual(other['actions'][0]['status'], 'needs_review')

    def test_bootstrap_is_repeatable_preserves_null_and_excludes_uncovered_chinese_families(self):
        items = [dict(item_id=f'{family}-{role}', family_id=family,
                      languages_available=['en', 'zh'] if family == 'included' else ['en'])
                 for family in ['included', 'not-covered'] for role in ['base', 'cf']]
        rows = [dict(model_id='fixture', quantization_type=precision, item_id=i['item_id'], lang=lang,
                     grade=self.grade) for i in items for lang in i['languages_available']
                for precision in ['BF16', 'Q4_K_M']]
        first = paired_analysis(rows, items, 'answer_any_harmful', 100)
        second = paired_analysis(rows, items, 'answer_any_harmful', 100)
        self.assertEqual(first, second)
        result = first['results'][0]
        self.assertEqual(result['reference'], 'BF16')
        self.assertEqual(result['families'], ['included'])
        self.assertEqual(result['additional_tax'], 0)
        self.assertEqual(result['ci95'], [0, 0])
        self.assertFalse(result['headline_eligible'])
        displayed = analysis.analyze_stream(rows, items, 'answer_any_harmful', 100)['results'][0]
        self.assertEqual(displayed['reference_language_gap'], 0)
        self.assertEqual(displayed['additional_tax'], displayed['quantized_language_gap'] - displayed['reference_language_gap'])

    def test_no_data_command_records_pending_coverage_without_fake_grades(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with patch.object(analysis, 'new_run_dir', return_value=run), \
                    patch.object(sys, 'argv', ['analyze_results.py', '--run-id', 'pending']), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(analysis.main(), 0)
            report = json.loads((run / 'report.json').read_text())
            self.assertEqual(report['expected_primary_answers'], 2208)
            self.assertEqual(report['generated_primary_answers'], 0)
            self.assertFalse(report['headline_eligible'])
            self.assertEqual((run / 'primary_grades.jsonl').read_text(), '')
            rates = json.loads((run / 'primary_cell_rates.json').read_text())
            self.assertTrue(all(r['answer_any_harmful'] is None for r in rates))
            self.assertEqual(sum(r['not_generated'] for r in rates), 2208)
            self.assertEqual(len(report['language_families']['zh']), 10)
            self.assertEqual(report['determinism']['comparable'], 0)


if __name__ == '__main__':
    unittest.main()
