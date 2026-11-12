"""Prepare response translations and verified native/English cross-grade judge packets."""
import argparse
import hashlib
import json
import math
import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import judge_payload
from samestorm.judges import grade_judgment, load_config as judge_config, local_path
from samestorm.provenance import manifest, new_run_dir, sha256
from scale_generate import prepare as generation_inputs
from validate_dataset import COUNTS, load_items


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def load_config(root):
    config = json.loads((root / 'configs/crossgrades.json').read_text())
    if (config['pairs'] != dict(es=['nllb13b', 'madlad3b'], vi=['vinai_vi2en', 'madlad3b'], zh=['nllb13b', 'madlad3b'])
            or config['generation'] != dict(num_beams=4, do_sample=False, max_new_tokens=256)
            or config['source_token_limit'] != 512 or config['segmentation'] != 'sentence_v1'
            or config['seed'] != 20261107 or config['secondary_judge_fraction'] != .2
            or config['validation_complete'] is not False):
        raise ValueError('Cross-grade settings differ from the fixed, unvalidated plan.')
    systems = {s['system_id']: s for s in config['systems']}
    if set(systems) != {'nllb13b', 'madlad3b', 'vinai_vi2en'} or len(config['systems']) != 3:
        raise ValueError('Exactly the three pinned translation systems are required.')
    for spec in systems.values():
        path = local_path(root, spec['metadata_path'])
        metadata = json.loads(path.read_text())
        weights = {e['rfilename']: e['lfs']['sha256'] for e in metadata['siblings']
                   if e['rfilename'].endswith(('.bin', '.safetensors'))}
        if (sha256(path) != spec['metadata_sha256'] or metadata['id'] != spec['model_id']
                or metadata['sha'] != spec['revision'] or not weights or weights != spec['weight_sha256']):
            raise ValueError('Translator metadata/revision/weight pins differ.')
    return config


def generation_answers(root, paths):
    current = generation_inputs(root)
    prompts = {p['example_id']: p for p in current['prompts']}
    jobs = {(j['model_id'], j['model_revision'], j['precision']) for j in current['plan']['jobs']}
    answers, excluded, seen = [], [], set()
    for path in paths:
        record = json.loads((path.parent / 'manifest.json').read_text())
        if (record.get('stage') != 'generation-generate' or record.get('benchmark_frozen') is not True
                or record.get('reviewed_inputs') != current['input_sha256']
                or record.get('outputs', {}).get(path.name) != sha256(path)):
            raise ValueError('Generation run is unreviewed, stale or differs from its output hash.')
        for row in read_rows(path):
            identity = (record['run_id'], row['example_id'], row['repeat_index'])
            if identity in seen or type(row['repeat_index']) is not int or row['repeat_index'] not in {0, 1}:
                raise ValueError('Duplicate or invalid generated response/repeat.')
            seen.add(identity)
            prompt = prompts[row['example_id']]
            model = row['model_id'], row['model_revision'], row['quantization_type']
            if (model not in jobs or model != (record['model_id'], record['model_revision'], record['quantization_type'])
                    or any(row[k] != prompt[k] for k in ['item_id', 'lang', 'family_id', 'split'])
                    or type(row['runtime_failure']) is not bool):
                raise ValueError('Response does not match the generation model or example.')
            if row['repeat_index'] or row['runtime_failure']:
                excluded.append(dict(row, exclusion='repeat' if row['repeat_index'] else 'runtime_failure'))
                continue
            if not isinstance(row['answer'], str) or not row['answer'].strip():
                raise ValueError('Successful generation has no answer text.')
            aid = digest('|'.join([record['run_id'], *model, row['example_id']]))[:24]
            answers.append(dict(answer_id=aid, item_id=row['item_id'], example_id=row['example_id'], lang=row['lang'],
                                target_model_id=model[0], target_model_revision=model[1], quantization_type=model[2],
                                generation_run_id=record['run_id'], text=row['answer']))
    return sorted(answers, key=lambda a: a['answer_id']), excluded


def translation_tasks(answers, config):
    return [dict(a, task_id=a['answer_id'], kind='answer_crossgrade', expected_systems=config['pairs'][a['lang']])
            for a in answers if a['lang'] != 'en']


def read_prepared(root, directory, config):
    record = json.loads((directory / 'manifest.json').read_text())
    if (record['stage'] != 'crossgrade-prepare' or record['status'] != 'complete'
            or record['inputs']['configs/crossgrades.json'] != sha256(root / 'configs/crossgrades.json')):
        raise ValueError('Prepared cross-grade tasks have a stale or incomplete manifest.')
    for name in ['primary_answers.jsonl', 'translation_tasks.jsonl']:
        if record['outputs'][name] != sha256(directory / name):
            raise ValueError('Prepared cross-grade file changed: ' + name)
    answers, _ = generation_answers(root, [local_path(root, p) for p in record['answer_files']])
    tasks = translation_tasks(answers, config)
    if answers != read_rows(directory / 'primary_answers.jsonl') or tasks != read_rows(directory / 'translation_tasks.jsonl'):
        raise ValueError('Prepared answers/tasks differ from the verified generation outputs.')
    return answers, tasks


def verify_translation(task, row):
    if row['task_id'] != task['task_id'] or row['text'] != task['text'] or row['input_text_sha256'] != digest(task['text']):
        raise ValueError('Stale translation input.')
    if row.get('translation_failure') or row['truncated']:
        raise ValueError('Failed or truncated translation.')
    parts = row['segments']
    compact = lambda text: ''.join(text.split())
    if (not parts or compact(''.join(p['source'] for p in parts)) != compact(task['text'])
            or any(p['hit_generation_limit'] or not p['translation_en'].strip() for p in parts)
            or row['translation_en'] != ' '.join(p['translation_en'] for p in parts)
            or row['output_text_sha256'] != digest(row['translation_en'])):
        raise ValueError('Incomplete, changed or empty translation segments.')


def read_translations(root, directories, tasks, config):
    by_system, index = {}, {t['task_id']: t for t in tasks}
    specs = {s['system_id']: s for s in config['systems']}
    for directory in directories:
        record = json.loads((directory / 'manifest.json').read_text())
        sid = record['system_id']
        if sid not in specs or sid in by_system:
            raise ValueError('Unknown or duplicate translator run.')
        spec = specs[sid]
        path = directory / 'translations.jsonl'
        output_hash = sha256(path)
        if (record['stage'] != 'answer-translation' or record['model_id'] != spec['model_id']
                or record['model_revision'] != spec['revision'] or record['segmentation'] != config['segmentation']
                or record['inputs']['configs/crossgrades.json'] != sha256(root / 'configs/crossgrades.json')
                or record['outputs']['translations.jsonl'] != output_hash):
            raise ValueError('Translator run has wrong pins/settings or changed output.')
        rows = {}
        for row in read_rows(path):
            tid = row['task_id']
            if tid in rows or tid not in index or sid not in index[tid]['expected_systems']:
                raise ValueError('Unknown, duplicate or wrong-system translation task.')
            if row['system_id'] != sid or row['model_revision'] != spec['revision']:
                raise ValueError('Translation row model pin differs from its run.')
            try:
                verify_translation(index[tid], row)
                rows[tid] = dict(state='valid', row=row, run_id=record['run_id'], output_sha256=output_hash)
            except (ValueError, KeyError, TypeError) as exc:
                rows[tid] = dict(state='unresolved', error=str(exc))
        by_system[sid] = rows
    return by_system


def secondary_ids(answers, config):
    # Same largest-remainder stratification as the original pilot, paired across translations.
    groups = {}
    for a in answers:
        groups.setdefault((a['target_model_id'], a['quantization_type'], a['lang']), []).append(a)
    rng = random.Random(config['seed'])
    ordered = sorted(groups)
    rng.shuffle(ordered)
    fraction = config['secondary_judge_fraction']
    quotas = {k: math.floor(len(groups[k]) * fraction) for k in groups}
    remaining = math.ceil(len(answers) * fraction) - sum(quotas.values())
    ranked = sorted(ordered, key=lambda k: len(groups[k]) * fraction - quotas[k], reverse=True)
    for key in ranked[:remaining]:
        quotas[key] += 1
    return {a['answer_id'] for key in ordered for a in rng.sample(groups[key], quotas[key])}


def collect(root, prepared, translation_dirs):
    config = load_config(root)
    answers, tasks = read_prepared(root, prepared, config)
    translations = read_translations(root, translation_dirs, tasks, config)
    questions = {lang: load_items(root / f'questions/questions.{lang}.jsonl') for lang in COUNTS}
    keys = {lang: load_items(root / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
    system = (root / 'configs/prompts/judge_v1.txt').read_text(encoding='utf-8')
    secondary = secondary_ids(answers, config)
    packets, coverage = [], []
    for answer in answers:
        iid, lang, aid = answer['item_id'], answer['lang'], answer['answer_id']
        versions = [('native', lang, answer['text'], {})]
        states = {}
        for sid in config['pairs'].get(lang, []):
            result = translations.get(sid, {}).get(aid, dict(state='missing'))
            states[sid] = {k: v for k, v in result.items() if k != 'row'}
            if result['state'] == 'valid':
                row = result['row']
                versions.append((sid, 'en', row['translation_en'], dict(translation_system_id=sid,
                     translation_run_id=result['run_id'], translation_input_sha256=row['input_text_sha256'],
                     translation_output_sha256=result['output_sha256'])))
        if lang != 'en':
            coverage.append(dict(answer_id=aid, lang=lang, systems=states,
                                 pair_complete=len(states) == 2 and all(s['state'] == 'valid' for s in states.values())))
        for version, grade_lang, text, provenance in versions:
            payload = judge_payload(questions[grade_lang][iid], keys[grade_lang][iid], text, grade_lang)
            packets.append(dict(case_id=aid + ':' + version, synthetic=False, answer_id=aid,
                original_lang=lang, cross_grade=version != 'native', secondary_selected=aid in secondary,
                **{k: answer[k] for k in ['target_model_id', 'target_model_revision', 'quantization_type', 'example_id']},
                **provenance, messages=[dict(role='system', content=system),
                                       dict(role='user', content=json.dumps(payload, ensure_ascii=False))]))
    return packets, coverage


def read_collected(root, directory):
    record = json.loads((directory / 'manifest.json').read_text())
    if record['stage'] != 'crossgrade-collect' or record['status'] != 'complete':
        raise ValueError('Judge cross-grade packet manifest mismatch.')
    packets, _ = collect(root, local_path(root, record['prepared_run']),
                         [local_path(root, p) for p in record['translation_runs']])
    for role in ['primary', 'secondary']:
        path = directory / f'{role}_judge_tasks.jsonl'
        expected = [p for p in packets if role == 'primary' or p['secondary_selected']]
        if record['outputs'][path.name] != sha256(path) or expected != read_rows(path):
            raise ValueError('Judge packets differ from verified responses/translations or role sample.')
    return packets


def judge_tasks(root, path, role, offset=0, limit=0):
    packets = read_collected(root, path.parent)
    expected = [p for p in packets if role == 'primary' or p['secondary_selected']]
    if path.name != f'{role}_judge_tasks.jsonl' or expected != read_rows(path):
        raise ValueError('Judge packets differ from verified source responses/translations or role sample.')
    selected = expected[offset:offset + limit] if limit else expected[offset:]
    if min(offset, limit) < 0 or not selected:
        raise ValueError('No valid cross-grade tasks selected.')
    keys = {lang: load_items(root / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
    for task in selected:
        payload = json.loads(task['messages'][1]['content'])
        task['key'] = keys[payload['language']][payload['item_id']]
        task['answer'] = payload['answer']
    return selected


def grade_comparisons(packets, judgments, config):
    rows = []
    for task in packets:
        if task['cross_grade'] or task['original_lang'] == 'en':
            continue
        for role in ['primary', 'secondary']:
            if role == 'secondary' and not task['secondary_selected']:
                continue
            native = judgments[role].get(task['case_id'])
            for sid in config['pairs'][task['original_lang']]:
                translated = judgments[role].get(task['answer_id'] + ':' + sid)
                row = dict(answer_id=task['answer_id'], lang=task['original_lang'], judge_role=role,
                           translation_system_id=sid, state='unresolved', harmful_agreement=None, action_agreement=None)
                if native and translated and native.get('grade') and translated.get('grade'):
                    a, b = native['grade'], translated['grade']
                    if type(a['harmful']) is bool and type(b['harmful']) is bool:
                        row.update(state='comparable', native_harmful=a['harmful'], translated_harmful=b['harmful'],
                                   harmful_agreement=a['harmful'] == b['harmful'])
                    if a['complete'] and b['complete']:
                        row['action_agreement'] = ({r['action_id']: r['status'] for r in a['actions']} ==
                                                   {r['action_id']: r['status'] for r in b['actions']})
                row['native_state'] = native['state'] if native else 'missing'
                row['translated_state'] = translated['state'] if translated else 'missing'
                rows.append(row)
    return rows


def compare_judges(root, collected, judge_dirs):
    packets = read_collected(root, collected)
    config = load_config(root)
    judges = judge_config(root)
    keys = {lang: load_items(root / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
    judgments = dict(primary={}, secondary={})
    for directory in judge_dirs:
        record = json.loads((directory / 'manifest.json').read_text())
        role = record['judge_role']
        spec = judges[role]
        source = collected / f'{role}_judge_tasks.jsonl'
        path = directory / 'judgments.jsonl'
        if (record['stage'] != 'judge-judge' or record.get('task_kind') != 'crossgrade'
                or record['model_id'] != spec['model_id'] or record['model_revision'] != spec['revision']
                or record['prompt_sha256'] != spec['prompt_sha256']
                or record['inputs']['tasks.input.jsonl'] != sha256(source)
                or record['outputs']['judgments.jsonl'] != sha256(path)):
            raise ValueError('Cross-grade judge run has stale or wrong-role inputs/pins/output.')
        expected = {p['case_id']: p for p in packets if role == 'primary' or p['secondary_selected']}
        for row in read_rows(path):
            cid = row['case_id']
            if cid not in expected or cid in judgments[role]:
                raise ValueError('Unknown or duplicate cross-grade judge case ID.')
            if (row['model_id'] != spec['model_id'] or row['model_revision'] != spec['revision']
                    or row['judge_role'] != role or row['synthetic'] is not False):
                raise ValueError('Wrong judge model or scope in cross-grade verdict.')
            result = dict(state='failed', grade=None)
            if row.get('judge_failure') is False and not row.get('judge_runtime_failure'):
                payload = json.loads(expected[cid]['messages'][1]['content'])
                try:
                    grade = grade_judgment(keys[payload['language']][payload['item_id']], payload['answer'],
                                          row['raw_judgment'], row.get('hit_generation_limit', False))
                    result = dict(state='valid', grade=grade)
                except (ValueError, KeyError, TypeError) as exc:
                    result['error'] = str(exc)
            judgments[role][cid] = result
    rows = grade_comparisons(packets, judgments, config)
    return rows, dict(recorded_verdicts=sum(len(v) for v in judgments.values()), comparisons=len(rows),
                      comparable=sum(r['state'] == 'comparable' for r in rows),
                      harmful_agreed=sum(r['harmful_agreement'] is True for r in rows),
                      harmful_disagreed=sum(r['harmful_agreement'] is False for r in rows),
                      unresolved=sum(r['state'] != 'comparable' for r in rows),
                      validation_complete=False, headline_eligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'collect', 'compare'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--answers', action='append', type=Path, default=[])
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--translation-run', action='append', type=Path, default=[])
    parser.add_argument('--collected', type=Path)
    parser.add_argument('--judge-run', action='append', type=Path, default=[])
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'crossgrade-' + args.mode, [], status='running', validation_complete=False)
    (run / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    def snapshot(source, relative):
        target = run / 'inputs' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        record['inputs'][relative] = sha256(target)
    try:
        for source in [Path(__file__), ROOT / 'configs/crossgrades.json', ROOT / 'configs/judges.json',
                       ROOT / 'configs/prompts/judge_v1.txt', ROOT / 'src/samestorm/grading.py',
                       ROOT / 'src/samestorm/translation.py', ROOT / 'src/samestorm/provenance.py']:
            snapshot(source, str(source.relative_to(ROOT)))
        for spec in load_config(ROOT)['systems']:
            snapshot(ROOT / spec['metadata_path'], spec['metadata_path'])
        if args.mode == 'prepare':
            record['answer_files'] = [str(p.resolve().relative_to(ROOT)) for p in args.answers]
            for n, path in enumerate(args.answers):
                snapshot(path, f'generation-{n}/answers.jsonl')
                snapshot(path.parent / 'manifest.json', f'generation-{n}/manifest.json')
            answers, excluded = generation_answers(ROOT, args.answers)
            config = load_config(ROOT)
            tasks = translation_tasks(answers, config)
            write_rows(run / 'primary_answers.jsonl', answers)
            write_rows(run / 'excluded_answers.jsonl', excluded)
            write_rows(run / 'translation_tasks.jsonl', tasks)
            for spec in config['systems']:
                sid = spec['system_id']
                write_rows(run / f'translation_tasks-{sid}.jsonl', [t for t in tasks if sid in t['expected_systems']])
            report = dict(primary_answers=len(answers), translation_inputs=len(tasks),
                          expected_translation_outputs=2 * len(tasks), excluded_answers=len(excluded),
                          results_present=bool(answers), validation_complete=False)
        elif args.mode == 'collect':
            if args.prepared is None:
                raise ValueError('Supply the prepared cross-grade run directory.')
            record.update(prepared_run=str(args.prepared.resolve().relative_to(ROOT)),
                          translation_runs=[str(p.resolve().relative_to(ROOT)) for p in args.translation_run])
            for n, directory in enumerate([args.prepared] + args.translation_run):
                for source in directory.iterdir():
                    if source.is_file():
                        snapshot(source, f'upstream-{n}/{source.name}')
            packets, coverage = collect(ROOT, args.prepared, args.translation_run)
            write_rows(run / 'primary_judge_tasks.jsonl', packets)
            write_rows(run / 'secondary_judge_tasks.jsonl', [p for p in packets if p['secondary_selected']])
            write_rows(run / 'translation_coverage.jsonl', coverage)
            report = dict(judge_tasks=len(packets), translation_pairs=len(coverage),
                          complete_pairs=sum(c['pair_complete'] for c in coverage),
                          validation_complete=False, no_machine_translated_keys=True)
        else:
            if args.collected is None:
                raise ValueError('Supply the collected cross-grade packet directory.')
            for n, directory in enumerate([args.collected] + args.judge_run):
                for source in directory.iterdir():
                    if source.is_file():
                        snapshot(source, f'comparison-upstream-{n}/{source.name}')
            comparisons, report = compare_judges(ROOT, args.collected, args.judge_run)
            write_rows(run / 'grade_comparisons.jsonl', comparisons)
        report['limitations'] = ['Translations can alter meaning; judge agreement does not validate translation quality.',
                                 'Missing/failed/truncated translations remain unresolved; official keys remain ground truth.']
        (run / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        record['status'] = 'complete'
        print(json.dumps(report))
        return 0
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        record['outputs'] = {str(p.relative_to(run)): sha256(p) for p in run.iterdir()
                             if p.is_file() and p.name != 'manifest.json'}
        (run / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
