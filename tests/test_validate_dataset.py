import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from validate_dataset import COUNTS, ROLES, validate


class DatasetValidation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for lang, count in COUNTS.items():
            folder = self.root / 'sources' / lang
            folder.mkdir(parents=True)
            (folder / 'source.txt').write_text('Synthetic source fixture.')
            checksum = hashlib.sha256((folder / 'source.txt').read_bytes()).hexdigest()
            questions, answers = [], []
            for n in range(count // 4):
                for role in ['base', 'p1', 'p2', 'cf1']:
                    iid = f'fixture{n:02}-{role}'
                    english = f'Synthetic question {iid}?'
                    questions.append(dict(item_id=iid, question=english) if lang == 'en' else
                                     dict(item_id=iid, lang=lang, translated_question='Synthetic translation.', english_original=english))
                    answers.append(dict(item_id=iid, lang=lang, forbidden_claims=[], required_actions=[dict(
                        action_id=iid + '--action', text='Synthetic action.', critical=True,
                        negation_sensitive=True, condition='', quantity=None, source_refs=['fixture--' + lang])],
                        sources=[dict(source_id='fixture--' + lang, lang=lang, official_quote='Synthetic action.',
                            document_group_id='fixture', passage_ref='Fixture only', extraction='Fixture only',
                            url='https://example.gov/fixture', retrieved='2026-11-10T00:00:00Z', published=None,
                            translation_provenance='original' if lang == 'en' else 'agency-published',
                            snapshot_path=f'sources/{lang}/source.txt', derived_text_path=f'sources/{lang}/source.txt',
                            sha256=checksum)]))
            self.write('questions', lang, questions)
            self.write('answers', lang, answers)
        self.write_metadata([dict(item_id=q['item_id'], family_id=q['item_id'].rsplit('-', 1)[0],
            role=ROLES[q['item_id'].rsplit('-', 1)[1]], split='dev',
            hazard=['flood', 'heat', 'winter_power_co', 'tornado'][n // 12],
            languages_available=['en', 'es', 'vi'] + (['zh'] if n < 40 else []))
            for n, q in enumerate(self.read('questions', 'en'))])

    def write_metadata(self, rows):
        folder = self.root / 'data'
        folder.mkdir(exist_ok=True)
        (folder / 'item_metadata.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def read_metadata(self):
        return [json.loads(line) for line in (self.root / 'data/item_metadata.jsonl').read_text().splitlines()]

    def write(self, kind, lang, rows):
        path = self.root / kind / f'{kind}.{lang}.jsonl'
        path.parent.mkdir(exist_ok=True)
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def read(self, kind, lang):
        return [json.loads(line) for line in (self.root / kind / f'{kind}.{lang}.jsonl').read_text().splitlines()]

    def test_valid_dataset(self):
        self.assertEqual(validate(self.root), [])

    def test_missing_metadata_file_fails(self):
        (self.root / 'data/item_metadata.jsonl').unlink()
        self.assertTrue(any('item_metadata.jsonl' in error for error in validate(self.root)))

    def test_missing_extra_and_duplicate_metadata_ids_fail(self):
        original = self.read_metadata()
        for rows, message in [(original[1:], 'IDs must match'),
                              (original + [dict(original[0], item_id='fixture12-base')], 'IDs must match'),
                              (original + original[:1], 'duplicate item_id')]:
            with self.subTest(message=message, count=len(rows)):
                self.write_metadata(rows)
                self.assertTrue(any(message in error for error in validate(self.root)))

    def test_metadata_family_role_and_test_split_fail(self):
        rows = self.read_metadata()
        rows[0]['family_id'] = 'another-family'
        rows[1]['role'] = 'base'
        rows[2]['split'] = 'test'
        self.write_metadata(rows)
        errors = validate(self.root)
        for message in ['family_id does not match', 'role does not match', 'pilot split must be dev']:
            self.assertTrue(any(message in error for error in errors), message)

    def test_metadata_language_duplicates_and_missing_coverage_fail(self):
        rows = self.read_metadata()
        rows[0]['languages_available'].append('vi')
        rows[1]['languages_available'].remove('zh')
        self.write_metadata(rows)
        errors = validate(self.root)
        self.assertTrue(any('unique list of known codes' in error for error in errors))
        self.assertTrue(any('languages do not match' in error for error in errors))

    def test_metadata_hazard_and_family_distribution_fail(self):
        original = self.read_metadata()
        for affected, hazard, message in [([0], 'unknown', 'invalid hazard'),
                                          ([0], 'heat', 'inconsistent hazard'),
                                          (range(4), 'heat', 'three families per hazard')]:
            with self.subTest(message=message):
                rows = json.loads(json.dumps(original))
                for n in affected:
                    rows[n]['hazard'] = hazard
                self.write_metadata(rows)
                self.assertTrue(any(message in error for error in validate(self.root)))

    def test_missing_answer_and_duplicate_question_fail(self):
        self.write('answers', 'es', self.read('answers', 'es')[1:])
        questions = self.read('questions', 'zh')
        self.write('questions', 'zh', questions + questions[:1])
        errors = validate(self.root)
        self.assertTrue(any('IDs do not match' in e for e in errors))
        self.assertTrue(any('duplicate item_id' in e for e in errors))

    def test_changed_source_and_escaped_path_fail(self):
        (self.root / 'sources/en/source.txt').write_text('Changed source.')
        answers = self.read('answers', 'es')
        answers[0]['sources'][0]['snapshot_path'] = '../outside.txt'
        self.write('answers', 'es', answers)
        errors = validate(self.root)
        self.assertTrue(any('checksum mismatch' in e for e in errors))
        self.assertTrue(any('escapes dataset' in e for e in errors))

    def test_missing_condition_and_dangling_citation_fail(self):
        answers = self.read('answers', 'vi')
        del answers[0]['required_actions'][0]['condition']
        answers[0]['required_actions'][0]['source_refs'] = ['missing-source']
        self.write('answers', 'vi', answers)
        errors = validate(self.root)
        self.assertTrue(any('condition must' in e for e in errors))
        self.assertTrue(any('invalid source references' in e for e in errors))

    def test_changed_critical_flag_and_english_original_fail(self):
        answers = self.read('answers', 'es')
        answers[0]['required_actions'][0]['critical'] = False
        self.write('answers', 'es', answers)
        questions = self.read('questions', 'vi')
        questions[0]['english_original'] = 'A different question.'
        self.write('questions', 'vi', questions)
        errors = validate(self.root)
        self.assertTrue(any('critical differs' in e for e in errors))
        self.assertTrue(any('English original does not match' in e for e in errors))

    def test_invalid_quantity_and_machine_translated_key_fail(self):
        answers = self.read('answers', 'zh')
        answers[0]['required_actions'][0]['quantity'] = dict(value='twenty', tolerance=-1, unit='feet', source_comparison='nearby')
        answers[0]['sources'][0]['translation_provenance'] = 'machine-translated'
        self.write('answers', 'zh', answers)
        errors = validate(self.root)
        for message in ['invalid value', 'invalid tolerance', 'invalid source comparison', 'incorrect source provenance']:
            self.assertTrue(any(message in e for e in errors), message)

    def test_incomplete_chinese_family_fails(self):
        questions = self.read('questions', 'zh')
        questions[0]['item_id'] = 'fixture10-base'
        self.write('questions', 'zh', questions)
        self.assertTrue(any('complete four-question families' in e for e in validate(self.root)))


if __name__ == '__main__':
    unittest.main()
