import argparse
import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import judge_payload, score_annotations
from samestorm.numerical import numerical_evidence
from samestorm.provenance import manifest, new_run_dir, sha256
from validate_dataset import COUNTS, load_items, validate as validate_dataset


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def check_cases(cases, questions, keys):
    """Check designed annotations and build judge tasks with the expected labels withheld."""
    ids = [case.get('case_id') for case in cases]
    if (not ids or not all(isinstance(i, str) and i for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Synthetic case IDs must be nonempty and unique.')
    checks, tasks = [], []
    for case in cases:
        check = dict(case_id=case['case_id'], passed=False)
        try:
            if case.get('synthetic') is not True or case.get('independent_human_labels') is not False:
                raise ValueError('Designed cases must be marked synthetic, without independent human labels.')
            lang, item_id = case['lang'], case['item_id']
            key = keys[lang][item_id]
            grade = score_annotations(key, case['answer'], case['expected_annotations'])
            check.update(actual_labels=grade['labels'], expected_labels=case['expected_labels'],
                         passed=grade['labels'] == case['expected_labels'])
            if not check['passed']:
                raise ValueError('Annotation-to-label mapping differs from the designed labels.')
            tasks.append(dict(case_id=case['case_id'], synthetic=True,
                              payload=judge_payload(questions[lang][item_id], key, case['answer'], lang)))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            check.update(passed=False, error=str(exc))
        checks.append(check)
    return checks, tasks


def check_numbers(cases):
    checks = []
    for case in cases:
        check = dict(case, passed=False)
        try:
            evidence = numerical_evidence(case['text'], case['quantity'])
            check.update(actual=evidence['status'], evidence=evidence,
                         passed=evidence['status'] == case['expected'])
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            check['error'] = str(exc)
        checks.append(check)
    return checks


def build_messages(payload, prompt):
    """Keep the model response inside the untrusted user data, outside the grading instructions."""
    return [dict(role='system', content=prompt),
            dict(role='user', content=json.dumps(payload, ensure_ascii=False))]


def main():
    parser = argparse.ArgumentParser(description='Check grading software and prepare synthetic judge tasks; no inference.')
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    inputs = [Path(__file__), ROOT / 'scripts/validate_dataset.py',
              ROOT / 'src/samestorm/grading.py', ROOT / 'src/samestorm/numerical.py',
              ROOT / 'src/samestorm/provenance.py', ROOT / 'configs/grading.json',
              ROOT / 'configs/toolchain.json', ROOT / 'configs/prompts/judge_v1.txt',
              ROOT / 'data/grading/cases.jsonl', ROOT / 'data/grading/student_review.csv',
              ROOT / 'tests/fixtures/numeric_cases.jsonl', ROOT / 'data/item_metadata.jsonl']
    inputs += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
    record = manifest(args.run_id, 'grading-software-validation', [], status='running',
                      semantic_judge_accuracy_validated=False, headline_eligible=False)
    manifest_path = run / 'manifest.json'
    manifest_path.write_text(json.dumps(record, indent=2) + '\n')
    try:
        # Preserve the actual inputs used, even if a later check fails.
        for source in inputs:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        errors = validate_dataset(ROOT)
        if errors:
            raise ValueError('; '.join(errors))
        cases = read_rows(ROOT / 'data/grading/cases.jsonl')
        questions = {lang: load_items(ROOT / f'questions/questions.{lang}.jsonl') for lang in COUNTS}
        keys = {lang: load_items(ROOT / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
        annotation_checks, tasks = check_cases(cases, questions, keys)
        numeric_checks = check_numbers(read_rows(ROOT / 'tests/fixtures/numeric_cases.jsonl'))
        prompt_path = ROOT / 'configs/prompts/judge_v1.txt'
        prompt = prompt_path.read_text(encoding='utf-8')
        for task in tasks:
            task['messages'] = build_messages(task.pop('payload'), prompt)
        with (ROOT / 'data/grading/student_review.csv').open(newline='', encoding='utf-8') as stream:
            student_rows = list(csv.DictReader(stream))
        passed = bool(numeric_checks) and all(c['passed'] for c in annotation_checks + numeric_checks)
        report = dict(software_checks_passed=passed,
                      annotation_mapping_cases=len(annotation_checks),
                      annotation_mapping_passed=sum(c['passed'] for c in annotation_checks),
                      numerical_cases=len(numeric_checks), numerical_passed=sum(c['passed'] for c in numeric_checks),
                      judge_tasks=len(tasks), cases_by_language=dict(Counter(c['lang'] for c in cases)),
                      cases_by_category=dict(Counter(c['category'] for c in cases)),
                      student_review_rows=len(student_rows),
                      student_rows_with_status=sum(bool(r['status'].strip()) for r in student_rows),
                      semantic_judge_accuracy_validated=False, headline_eligible=False,
                      limitations=[
                          'Expected labels describe synthetic injection design, not independent human gold.',
                          'Mapping checks consume supplied annotations; they do not judge answer meaning.',
                          'Harmful injected examples are English only; translated harmful-case coverage is incomplete.',
                          'Student judgments, two-judge validation, existing human labels and translation cross-grades remain pending.',
                          'No forbidden-claim rules are populated; no judge inference has run.'])
        write_rows(run / 'annotation_checks.jsonl', annotation_checks)
        write_rows(run / 'numeric_checks.jsonl', numeric_checks)
        write_rows(run / 'judge_validation_tasks.jsonl', tasks)
        (run / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        outputs = [run / name for name in ['annotation_checks.jsonl', 'numeric_checks.jsonl',
                                          'judge_validation_tasks.jsonl', 'report.json']]
        record.update(status='complete' if passed else 'failed',
                      prompt_sha256=sha256(prompt_path), software_checks_passed=passed,
                      outputs={str(p.relative_to(run)): sha256(p) for p in outputs})
        print(f"{'PASS' if passed else 'FAIL'}: {report['annotation_mapping_passed']}/{len(annotation_checks)} annotation cases; "
              f"{report['numerical_passed']}/{len(numeric_checks)} numerical cases; {len(tasks)} judge inputs prepared.")
        print(run / 'report.json')
        return 0 if passed else 1
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        manifest_path.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
