import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import shutil

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import crossgrades as cross
from scale_translate import translated_rows
from samestorm.provenance import sha256
from samestorm.translation import split_sentences


class CrossGradePipeline(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(ROOT / 'configs', self.root / 'configs')
        for relative in ['scripts/crossgrades.py', 'src/samestorm/grading.py',
                         'src/samestorm/translation.py', 'src/samestorm/provenance.py']:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.config = cross.load_config(self.root)
        self.specs = {s['system_id']: s for s in self.config['systems']}
        self.prompts = []
        rows = []
        for lang in ['en', 'es', 'vi', 'zh']:
            key = dict(item_id='fixture-base', lang=lang, required_actions=[dict(
                action_id='a', critical=True, text=f'Official {lang} instruction.', condition='', quantity=None)],
                sources=[dict(source_id='source-' + lang, lang=lang, official_quote=f'Official {lang} passage.')])
            question = dict(item_id='fixture-base', question='English question?') if lang == 'en' else dict(
                item_id='fixture-base', lang=lang, translated_question=f'Question {lang}?')
            for kind, value in [('questions', question), ('answers', key)]:
                path = self.root / f'{kind}/{kind}.{lang}.jsonl'
                path.parent.mkdir(parents=True, exist_ok=True)
                cross.write_rows(path, [value])
            prompt = dict(item_id='fixture-base', example_id='fixture-base:' + lang,
                          lang=lang, family_id='fixture', split='dev')
            self.prompts.append(prompt)
            rows.append(dict(prompt, model_id='fixture/model', model_revision='a' * 40,
                             quantization_type='F16', repeat_index=0, runtime_failure=False, answer=f'Response {lang}.'))
        self.current = dict(prompts=self.prompts, input_sha256={'fixture': 'fixed-fixture-hash'},
                            plan=dict(jobs=[dict(model_id='fixture/model', model_revision='a' * 40, precision='F16')]))
        p = patch.object(cross, 'generation_inputs', return_value=self.current)
        p.start()
        self.addCleanup(p.stop)
        self.generation = self.root / 'results/raw/generation'
        self.generation.mkdir(parents=True)
        cross.write_rows(self.generation / 'answers.jsonl', rows)
        self.generation_record = dict(stage='generation-generate', status='complete', run_id='fixture-generation',
             benchmark_frozen=True, reviewed_inputs=self.current['input_sha256'],
             model_id='fixture/model', model_revision='a' * 40, quantization_type='F16',
             outputs={'answers.jsonl': sha256(self.generation / 'answers.jsonl')})
        self.save(self.generation / 'manifest.json', self.generation_record)

    def save(self, path, value):
        path.write_text(json.dumps(value) + '\n')

    def command(self, mode, name, *args):
        run = self.root / 'results/raw' / name
        run.mkdir()
        with patch.object(cross, 'ROOT', self.root), \
                patch.object(cross, '__file__', str(self.root / 'scripts/crossgrades.py')), \
                patch.object(cross, 'new_run_dir', return_value=run), \
                patch.object(sys, 'argv', ['crossgrades.py', mode, '--run-id', name, *map(str, args)]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cross.main(), 0)
        return run

    def prepared(self):
        return self.command('prepare', 'prepared', '--answers', self.generation / 'answers.jsonl')

    def translator_runs(self, prepared):
        tasks = cross.read_rows(prepared / 'translation_tasks.jsonl')
        directories = []
        for sid, spec in self.specs.items():
            directory = self.root / 'results/raw' / sid
            directory.mkdir()
            rows = []
            for task in tasks:
                if sid not in task['expected_systems']:
                    continue
                text = f'Translated by {sid}.'
                rows.append(dict(task, system_id=sid, model_revision=spec['revision'],
                    input_text_sha256=cross.digest(task['text']), translation_failure=False, truncated=False,
                    translation_en=text, output_text_sha256=cross.digest(text),
                    segments=[dict(source=task['text'], translation_en=text, hit_generation_limit=False)]))
            cross.write_rows(directory / 'translations.jsonl', rows)
            self.save(directory / 'manifest.json', dict(stage='answer-translation', status='complete', run_id=sid,
                system_id=sid, model_id=spec['model_id'], model_revision=spec['revision'], segmentation='sentence_v1',
                inputs={'configs/crossgrades.json': sha256(self.root / 'configs/crossgrades.json')},
                outputs={'translations.jsonl': sha256(directory / 'translations.jsonl')}))
            directories.append(directory)
        return directories

    def test_end_to_end_packets_use_official_keys_and_reach_judge_loader(self):
        prepared = self.prepared()
        dirs = self.translator_runs(prepared)
        args = [item for d in dirs for item in ['--translation-run', d]]
        collected = self.command('collect', 'collected', '--prepared', prepared, *args)
        packets = cross.read_collected(self.root, collected)
        self.assertEqual(len(packets), 10)  # Four native answers and two versions of three non-English answers.
        tasks = cross.judge_tasks(self.root, collected / 'primary_judge_tasks.jsonl', 'primary')
        self.assertEqual(len(tasks), 10)
        for task in tasks:
            payload = json.loads(task['messages'][1]['content'])
            self.assertNotIn('target_model_id', payload)
            self.assertNotIn('quantization_type', payload)
            if task['cross_grade']:
                self.assertEqual(payload['language'], 'en')
                self.assertEqual(payload['required_actions'][0]['text'], 'Official en instruction.')
                self.assertEqual(payload['official_sources'][0]['official_quote'], 'Official en passage.')
        second = cross.judge_tasks(self.root, collected / 'secondary_judge_tasks.jsonl', 'secondary')
        selected = {p['answer_id'] for p in packets if p['secondary_selected']}
        self.assertEqual({p['answer_id'] for p in second}, selected)
        judge_dirs = []
        judges = json.loads((self.root / 'configs/judges.json').read_text())
        for role in ['primary', 'secondary']:
            directory = self.root / 'results/raw' / ('judge-' + role)
            directory.mkdir()
            spec = judges[role]
            rows = []
            for task in cross.read_rows(collected / f'{role}_judge_tasks.jsonl'):
                payload = json.loads(task['messages'][1]['content'])
                status = 'reversal' if task.get('translation_system_id') == 'nllb13b' else 'correct'
                rows.append(dict(case_id=task['case_id'], synthetic=False, judge_role=role,
                    model_id=spec['model_id'], model_revision=spec['revision'], judge_failure=False,
                    raw_judgment=json.dumps(dict(actions=[dict(action_id='a', status=status,
                        evidence_quote=payload['answer'])], outcomes=dict(refusal=False, wrong_language=False, runtime_failure=False)))))
            cross.write_rows(directory / 'judgments.jsonl', rows)
            self.save(directory / 'manifest.json', dict(stage='judge-judge', task_kind='crossgrade',
                judge_role=role, model_id=spec['model_id'], model_revision=spec['revision'],
                prompt_sha256=spec['prompt_sha256'], inputs={'tasks.input.jsonl': sha256(collected / f'{role}_judge_tasks.jsonl')},
                outputs={'judgments.jsonl': sha256(directory / 'judgments.jsonl')}))
            judge_dirs.append(directory)
        comparisons, report = cross.compare_judges(self.root, collected, judge_dirs)
        self.assertGreaterEqual(report['comparable'], 6)
        self.assertGreaterEqual(report['harmful_disagreed'], 2)
        self.assertFalse(report['validation_complete'])
        self.assertFalse(report['headline_eligible'])
        with (judge_dirs[0] / 'judgments.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaises(ValueError):
            cross.compare_judges(self.root, collected, judge_dirs)

    def test_repeats_failures_and_stale_generation_are_not_translation_inputs(self):
        path = self.generation / 'answers.jsonl'
        rows = cross.read_rows(path)
        rows[0]['repeat_index'] = 1
        rows[1]['runtime_failure'] = True
        cross.write_rows(path, rows)
        record = dict(self.generation_record, outputs={'answers.jsonl': sha256(path)})
        self.save(self.generation / 'manifest.json', record)
        answers, excluded = cross.generation_answers(self.root, [path])
        self.assertEqual(len(answers), 2)
        self.assertEqual({r['exclusion'] for r in excluded}, {'repeat', 'runtime_failure'})
        self.save(self.generation / 'manifest.json', dict(record, benchmark_frozen=False))
        with self.assertRaises(ValueError):
            cross.generation_answers(self.root, [path])

    def test_missing_or_truncated_partner_is_unresolved_and_not_replaced(self):
        prepared = self.prepared()
        dirs = self.translator_runs(prepared)
        path = dirs[0] / 'translations.jsonl'
        rows = cross.read_rows(path)
        rows[0]['truncated'] = True
        cross.write_rows(path, rows)
        record = json.loads((dirs[0] / 'manifest.json').read_text())
        record['outputs']['translations.jsonl'] = sha256(path)
        self.save(dirs[0] / 'manifest.json', record)
        packets, coverage = cross.collect(self.root, prepared, dirs[:1])
        self.assertFalse(any(c['pair_complete'] for c in coverage))
        self.assertEqual(sum(c['systems']['madlad3b']['state'] == 'missing' for c in coverage), 3)
        self.assertTrue(any(s['state'] == 'unresolved' for c in coverage for s in c['systems'].values()))
        self.assertTrue(any(not p['cross_grade'] for p in packets))

    def test_changed_translation_hash_or_dropped_sentence_is_rejected(self):
        prepared = self.prepared()
        dirs = self.translator_runs(prepared)
        tasks = cross.read_rows(prepared / 'translation_tasks.jsonl')
        rows = cross.read_rows(dirs[0] / 'translations.jsonl')
        task = next(t for t in tasks if t['task_id'] == rows[0]['task_id'])
        for changes in [dict(input_text_sha256='stale'), dict(segments=[]), dict(translation_en='changed')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cross.verify_translation(task, dict(rows[0], **changes))
        with (dirs[0] / 'translations.jsonl').open('a') as stream:
            stream.write('\n')
        with self.assertRaises(ValueError):
            cross.read_translations(self.root, dirs, tasks, self.config)

    def test_packet_tampering_and_wrong_role_are_rejected(self):
        prepared = self.prepared()
        collected = self.command('collect', 'collected', '--prepared', prepared)
        with self.assertRaises(ValueError):
            cross.judge_tasks(self.root, collected / 'primary_judge_tasks.jsonl', 'secondary')
        path = collected / 'primary_judge_tasks.jsonl'
        with path.open('a') as stream:
            stream.write('\n')
        with self.assertRaises(ValueError):
            cross.read_collected(self.root, collected)

    def test_comparison_distinguishes_disagreement_and_missing_judge_results(self):
        packet = dict(case_id='id:native', answer_id='id', original_lang='es', cross_grade=False, secondary_selected=True)
        good = dict(harmful=False, complete=True, actions=[dict(action_id='a', status='correct')])
        bad = dict(harmful=True, complete=True, actions=[dict(action_id='a', status='reversal')])
        results = dict(primary={'id:native': dict(state='valid', grade=good),
                                'id:nllb13b': dict(state='valid', grade=bad)}, secondary={})
        rows = cross.grade_comparisons([packet], results, self.config)
        self.assertEqual(len(rows), 4)
        self.assertEqual(sum(r['harmful_agreement'] is False for r in rows), 1)
        self.assertEqual(sum(r['state'] == 'unresolved' for r in rows), 3)
        self.assertTrue(all(r['harmful_agreement'] is None for r in rows if r['state'] == 'unresolved'))

    def test_secondary_sample_is_exact_and_repeatable(self):
        answers = [dict(answer_id=str(i), target_model_id='m', quantization_type='F16', lang=lang)
                   for i, lang in enumerate(['en'] * 48 + ['es'] * 48 + ['vi'] * 48 + ['zh'] * 40)]
        selected = cross.secondary_ids(answers, self.config)
        self.assertEqual(len(selected), 37)
        self.assertEqual(selected, cross.secondary_ids(answers, self.config))


class TranslationWorker(unittest.TestCase):
    def test_sentence_split_preserves_chinese_vietnamese_and_decimal_text(self):
        for text in ['Giữ khoảng cách 6.10 m. Gọi trợ giúp!', '第一句。第二句！第三句？', 'A\nB.']:
            parts = split_sentences(text)
            self.assertEqual(''.join(''.join(p.split()) for p in parts), ''.join(text.split()))
        self.assertEqual(split_sentences('6.10 m.'), ['6.10 m.'])

    def test_translator_retains_partial_failures_and_disables_input_truncation(self):
        config = cross.load_config(ROOT)
        spec = next(s for s in config['systems'] if s['system_id'] == 'madlad3b')
        task = dict(task_id='fixture', text='Primera frase. Segunda frase.', lang='es')
        tokenizer, model, torch = MagicMock(), MagicMock(), MagicMock()
        class Encoding(dict):
            def to(self, device):
                return self
        tokens = MagicMock()
        tokens.shape = (1, 10)
        tokenizer.return_value = Encoding(input_ids=tokens)
        tokenizer.batch_decode.return_value = ['First translated sentence.']
        output = MagicMock()
        output.__getitem__.return_value.tolist.return_value = [1, 2, 3]
        model.generate.side_effect = [output, RuntimeError('Fixture translation failure')]
        row = list(translated_rows([task], spec, config, tokenizer, model, torch))[0]
        self.assertTrue(row['translation_failure'])
        self.assertEqual(len(row['segments']), 1)
        self.assertEqual(row['translation_en'], 'First translated sentence.')
        self.assertIn('Fixture translation failure', row['error'])
        self.assertFalse(tokenizer.call_args.kwargs['truncation'])
        self.assertTrue(tokenizer.call_args.args[0][0].startswith('<2en> '))


if __name__ == '__main__':
    unittest.main()
