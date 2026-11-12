import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import ACTION_STATUSES, score_annotations
from samestorm.judges import grade_judgment, load_config
from samestorm.provenance import manifest, new_run_dir, sha256
from validate_dataset import COUNTS, load_items


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def checked_judgments(rows, role, spec, cases, keys):
    checked = {}
    for row in rows:
        cid = row['case_id']
        if cid not in cases or cid in checked:
            raise ValueError('Unknown or duplicate judge case ID: ' + cid)
        if (row.get('judge_role') != role or row.get('model_id') != spec['model_id']
                or row.get('model_revision') != spec['revision'] or row.get('synthetic') is not True):
            raise ValueError('Judge role/model/revision or synthetic scope does not match.')
        result = dict(state='failed', grade=None, error=row.get('error'))
        if row.get('judge_failure') is False and not row.get('judge_runtime_failure'):
            case = cases[cid]
            try:
                grade = grade_judgment(keys[case['lang']][case['item_id']], case['answer'],
                                      row['raw_judgment'], row.get('hit_generation_limit', False))
                if 'grade' in row and row['grade'] != grade:
                    raise ValueError('Saved grade differs from the checked raw verdict.')
                result = dict(state='valid', grade=grade)
            except (KeyError, TypeError, ValueError) as exc:
                result['error'] = str(exc)
        checked[cid] = result
    return checked


def read_judge_run(path, role, spec, cases, keys, root):
    record = json.loads((path.parent / 'manifest.json').read_text())
    if (record.get('stage') != 'judge-judge' or record.get('judge_role') != role
            or record.get('model_id') != spec['model_id'] or record.get('model_revision') != spec['revision']
            or record.get('prompt_sha256') != spec['prompt_sha256']):
        raise ValueError('Judge run manifest does not match the pinned role/model/prompt.')
    if record.get('outputs', {}).get(path.name) != sha256(path):
        raise ValueError('Judge output differs from its manifest hash.')
    inputs = ['data/grading/cases.jsonl', 'configs/judges.json', spec['prompt_path']]
    inputs += [f'{kind}/{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
    for relative in inputs:
        if record.get('inputs', {}).get(relative) != sha256(root / relative):
            raise ValueError('Judge run used different or unrecorded inputs: ' + relative)
    return checked_judgments(read_rows(path), role, spec, cases, keys), record['status']


def student_ratings(rows, cases, questions, keys):
    ratings, seen = {}, set()
    for row in rows:
        cid, aid = row['case_id'], row['action_id']
        if cid not in cases or (cid, aid) in seen:
            raise ValueError('Unknown or duplicate student case/action ID.')
        seen.add((cid, aid))
        case = cases[cid]
        if case['lang'] != 'en' or row['item_id'] != case['item_id']:
            raise ValueError('Student ratings must refer to matching English cases.')
        key = keys['en'][case['item_id']]
        actions = {a['action_id']: a for a in key['required_actions']}
        if aid not in actions:
            raise ValueError('Unknown student action ID.')
        action = actions[aid]
        if (row['question'] != questions['en'][case['item_id']]['question']
                or row['answer'] != case['answer'] or row['required_action'] != action['text']
                or row['critical'] != str(action['critical'])):
            raise ValueError('Student worksheet content differs from the current case/key.')
        status = row['status'].strip()
        if not status:
            continue
        if status not in ACTION_STATUSES:
            raise ValueError('Invalid student action status.')
        annotations = [dict(action_id=a['action_id'], status=status if a['action_id'] == aid else 'uncertain',
                            evidence_quote=row['evidence_quote'] if a['action_id'] == aid else '')
                       for a in key['required_actions']]
        score_annotations(key, case['answer'], annotations)
        ratings[cid, aid] = status
    return ratings


def compare(cases, keys, judgments, students):
    reports, details, action_rows = {}, [], []
    for role in ['primary', 'secondary']:
        per_language = {}
        for lang in COUNTS:
            counts = Counter({k: 0 for k in ['tp', 'fn', 'fp', 'tn', 'abstain_harm', 'abstain_safe',
                                             'missing', 'failed', 'uncertain']})
            for case in cases.values():
                if case['lang'] != lang:
                    continue
                result = judgments[role].get(case['case_id'], dict(state='missing', grade=None))
                grade = result['grade']
                actual = grade['harmful'] if grade else None
                expected = bool(case['expected_labels'])
                if result['state'] != 'valid':
                    counts[result['state']] += 1
                elif actual is None:
                    counts['uncertain'] += 1
                if type(actual) is not bool:
                    counts['abstain_harm' if expected else 'abstain_safe'] += 1
                else:
                    counts[('tp' if actual else 'fn') if expected else ('fp' if actual else 'tn')] += 1
            positives = counts['tp'] + counts['fn'] + counts['abstain_harm']
            negatives = counts['fp'] + counts['tn'] + counts['abstain_safe']
            per_language[lang] = dict(counts, expected_harmful_cases=positives, expected_safe_cases=negatives,
                recall_lower_bound=counts['tp'] / positives if positives else None,
                false_alarm_upper_bound=(counts['fp'] + counts['abstain_safe']) / negatives if negatives else None)
        reports[role] = dict(recorded_cases=len(judgments[role]), provisional_synthetic_metrics=per_language)
    for cid, case in cases.items():
        detail = dict(case_id=cid, item_id=case['item_id'], lang=case['lang'], category=case['category'],
                      expected_labels=case['expected_labels'])
        statuses = {}
        for role in ['primary', 'secondary']:
            result = judgments[role].get(cid, dict(state='missing', grade=None))
            detail[role] = result
            statuses[role] = {a['action_id']: a['status'] for a in result['grade']['actions']} if result['grade'] else {}
        details.append(detail)
        expected = {a['action_id']: a['status'] for a in case['expected_annotations']}
        for action in keys[case['lang']][case['item_id']]['required_actions']:
            aid = action['action_id']
            action_rows.append(dict(case_id=cid, lang=case['lang'], action_id=aid, expected_status=expected[aid],
                                    primary_status=statuses['primary'].get(aid),
                                    secondary_status=statuses['secondary'].get(aid), student_status=students.get((cid, aid))))
    usable = {k: v for k, v in students.items() if v != 'uncertain'}
    for role in ['primary', 'secondary']:
        rated = [r for r in action_rows if (r['case_id'], r['action_id']) in usable]
        agreed = sum(r[role + '_status'] == r['student_status'] for r in rated)
        comparable = sum(r[role + '_status'] not in {None, 'uncertain'} for r in rated)
        reports[role].update(student_action_labels=len(rated), student_action_comparable=comparable,
                             student_action_agreed=agreed,
                             student_action_agreement=agreed / len(rated) if rated else None)
    paired = [r for r in action_rows if all(r[role + '_status'] not in {None, 'uncertain'}
                                           for role in ['primary', 'secondary'])]
    agreed = sum(r['primary_status'] == r['secondary_status'] for r in paired)
    report = dict(judges=reports, student_ratings=len(students), usable_student_ratings=len(usable),
                  student_minimum_60_met=len(usable) >= 60,
                  judge_action_comparable=len(paired), judge_action_agreed=agreed,
                  judge_action_agreement=agreed / len(paired) if paired else None,
                  validated=False, headline_eligible=False,
                  limitations=[
                      'Expected labels describe synthetic injection design, not independent human gold.',
                      'Recall/false-alarm bounds include missing, failed and unresolved cases as abstentions.',
                      'Student agreement uses all usable student ratings; unavailable judge actions do not count as agreement.',
                      'Judge-to-judge agreement uses comparable actions only; inspect its coverage.',
                      'Harmful injected cases are English only; non-English validation is incomplete.',
                      'Existing human-label checks and translation cross-grades remain pending.',
                      'Thresholds remain PI-unconfirmed; this report cannot mark judges validated.',
                      'The Qwen judge shares a model family with the Qwen target.'])
    return report, details, action_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--primary', type=Path)
    parser.add_argument('--secondary', type=Path)
    parser.add_argument('--student-review', type=Path, default=ROOT / 'data/grading/student_review.csv')
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'judge-validation-comparison', [], status='running', validated=False)
    output = run / 'manifest.json'
    output.write_text(json.dumps(record, indent=2) + '\n')
    try:
        paths = [Path(__file__), ROOT / 'scripts/validate_dataset.py', ROOT / 'src/samestorm/grading.py',
                 ROOT / 'src/samestorm/judges.py', ROOT / 'src/samestorm/provenance.py',
                 ROOT / 'data/grading/cases.jsonl', ROOT / 'configs/judges.json', ROOT / 'configs/prompts/judge_v1.txt',
                 ROOT / 'configs/toolchain.json', ROOT / 'configs/grading.json']
        paths += [ROOT / f'configs/evidence/judges/{role}/hub_metadata.json' for role in ['primary', 'secondary']]
        paths += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
        for source in paths:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        for name, source in [('student_review.csv', args.student_review),
                             ('primary.jsonl', args.primary), ('secondary.jsonl', args.secondary)]:
            if source is not None:
                shutil.copy2(source, run / name)
                record['inputs'][name] = sha256(run / name)
                if name.endswith('.jsonl'):
                    shutil.copy2(source.parent / 'manifest.json', run / (name + '.manifest.json'))
                    record['inputs'][name + '.manifest.json'] = sha256(run / (name + '.manifest.json'))
        config = load_config(ROOT)
        rows = read_rows(ROOT / 'data/grading/cases.jsonl')
        cases = {c['case_id']: c for c in rows}
        if not cases or len(cases) != len(rows):
            raise ValueError('Synthetic case IDs must be nonempty and unique.')
        keys = {lang: load_items(ROOT / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
        questions = {lang: load_items(ROOT / f'questions/questions.{lang}.jsonl') for lang in COUNTS}
        judgments, statuses = {}, {}
        for role in ['primary', 'secondary']:
            path = getattr(args, role)
            judgments[role], statuses[role] = (read_judge_run(path, role, config[role], cases, keys, ROOT)
                                               if path is not None else ({}, 'not_supplied'))
        with (run / 'student_review.csv').open(newline='', encoding='utf-8') as stream:
            students = student_ratings(list(csv.DictReader(stream)), cases, questions, keys)
        report, details, actions = compare(cases, keys, judgments, students)
        report['input_run_status'] = statuses
        report['results_present'] = any(judgments.values())
        (run / 'judge_validation_report.json').write_text(json.dumps(report, indent=2) + '\n')
        for name, values in [('case_comparisons.jsonl', details), ('action_comparisons.jsonl', actions)]:
            (run / name).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in values), encoding='utf-8')
        record.update(status='complete', results_present=report['results_present'])
        print(f"REPORT: {sum(len(j) for j in judgments.values())} judge records; {len(students)} student ratings. Grading remains unvalidated.")
        print(run / 'judge_validation_report.json')
        return 0
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        record['outputs'] = {str(p.relative_to(run)): sha256(p) for p in run.iterdir()
                             if p.is_file() and p != output}
        output.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
