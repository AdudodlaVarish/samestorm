import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import judge_payload


def rows(path):
    return {row['item_id']: row for row in map(json.loads, path.read_text().splitlines())}


class JudgePayload(unittest.TestCase):
    def setUp(self):
        self.question = dict(item_id='fixture-base', question='Fixture question?')
        self.key = dict(item_id='fixture-base', lang='en', required_actions=[
            dict(action_id='fixture-action', critical=True, text='Required instruction.',
                 condition='Applicable condition.', quantity=None)], sources=[
            dict(source_id='fixture-en', lang='en', official_quote='Official English passage.'),
            dict(source_id='fixture-es', lang='es', official_quote='Pasaje en español.')])

    def test_only_same_language_sources_and_explicit_fields_are_included(self):
        self.question.update(model_id='PRIVATE_TARGET', quantization_type='Q2_K')
        self.key.update(model_id='PRIVATE_TARGET', quantization_type='Q2_K')
        payload = judge_payload(self.question, self.key, 'Response text.', 'en')
        self.assertEqual(set(payload), {'item_id', 'language', 'question', 'answer',
                                       'required_actions', 'official_sources'})
        self.assertEqual(payload['answer'], 'Response text.')
        self.assertEqual(payload['official_sources'], [dict(source_id='fixture-en',
                                                          official_quote='Official English passage.')])
        self.assertNotIn('PRIVATE_TARGET', json.dumps(payload))
        self.assertNotIn('Q2_K', json.dumps(payload))

    def test_mismatched_items_and_languages_are_rejected(self):
        for question, key, lang in [
                ({**self.question, 'item_id': 'other-base'}, self.key, 'en'),
                (self.question, self.key, 'es'),
                (self.question, self.key, 'fr'),
                ({**self.question, 'lang': 'vi'}, {**self.key, 'lang': 'es'}, 'es')]:
            with self.subTest(lang=lang, question=question), self.assertRaises(ValueError):
                judge_payload(question, key, 'Response text.', lang)

    def test_missing_same_language_sources_are_rejected(self):
        self.key['sources'] = [self.key['sources'][1]]
        with self.assertRaises(ValueError):
            judge_payload(self.question, self.key, 'Response text.', 'en')

    def test_all_exported_question_key_pairs_preserve_judge_content(self):
        for lang in ['en', 'es', 'vi', 'zh']:
            questions = rows(ROOT / f'questions/questions.{lang}.jsonl')
            keys = rows(ROOT / f'answers/answers.{lang}.jsonl')
            for item_id, key in keys.items():
                with self.subTest(lang=lang, item_id=item_id):
                    question = questions[item_id]
                    payload = judge_payload(question, key, 'Synthetic response.', lang)
                    self.assertEqual(payload['question'], question[
                        'question' if lang == 'en' else 'translated_question'])
                    self.assertEqual(payload['required_actions'], [
                        {field: a[field] for field in ['action_id', 'critical', 'text', 'condition', 'quantity']}
                        for a in key['required_actions']])
                    self.assertEqual(payload['official_sources'], [
                        {field: s[field] for field in ['source_id', 'official_quote']}
                        for s in key['sources'] if s['lang'] == lang])
                    json.dumps(payload, ensure_ascii=False)


if __name__ == '__main__':
    unittest.main()
