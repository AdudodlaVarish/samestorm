import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.analysis import error_value, paired_analysis
from samestorm.grading import mechanical_grade
from samestorm.judges import local_path
from samestorm.provenance import manifest, new_run_dir, sha256
from crossgrades import generation_answers, verified_judgments
from scale_generate import prepare, read_rows, save
from validate_dataset import COUNTS, load_items


UNITS = ['answer_any_harmful', 'critical_action_error']


def physical_records(root, collected, metadata):
    record = json.loads((collected / 'manifest.json').read_text())
    prepared = local_path(root, record['prepared_run'])
    source = json.loads((prepared / 'manifest.json').read_text())
    paths = [local_path(root, p) for p in source['answer_files']]
    # Recheck every generation source, including excluded repeats and runtime failures.
    generation_answers(root, paths)
    rows, seen = [], set()
    for path in paths:
        source_record = json.loads((path.parent / 'manifest.json').read_text())
        for row in read_rows(path):
            if row.get('synthetic') or row.get('cross_grade'):
                raise ValueError('Synthetic or translated grading cases are not native experiment responses.')
            identity = row['model_id'], row['model_revision'], row['quantization_type'], row['example_id'], row['repeat_index']
            if identity in seen:
                raise ValueError('Duplicate model/precision/example/repeat across runs; select one declared cohort.')
            seen.add(identity)
            item = metadata[row['item_id']]
            if item['split'] != 'dev' or row['lang'] not in item['languages_available']:
                raise ValueError('Only included dev examples may enter pilot analysis.')
            rows.append(dict(row, family_id=item['family_id'], hazard=item['hazard'],
                             source_generation_run_id=source_record['run_id'],
                             generation_output_sha256=source_record['outputs'][path.name]))
    return rows


def streams(records, packets, judgments):
    native = {(p['target_model_id'], p['target_model_revision'], p['quantization_type'], p['example_id']): p
              for p in packets if not p['cross_grade']}
    if len(native) != sum(not p['cross_grade'] for p in packets):
        raise ValueError('Duplicate native judge packet for a target response.')
    result = dict(primary=[], secondary=[])
    for row in records:
        if row['repeat_index'] != 0:
            continue
        identity = row['model_id'], row['model_revision'], row['quantization_type'], row['example_id']
        task = native.get(identity)
        if not row['runtime_failure'] and task is None:
            raise ValueError('Generated primary response has no verified native packet.')
        for role in result:
            normalized = {k: row[k] for k in ['model_id', 'model_revision', 'quantization_type', 'item_id',
                                               'family_id', 'hazard', 'lang', 'example_id']}
            normalized.update(repeat_index=0, cross_grade=False, synthetic=False, judge_role=role)
            normalized.update(source_generation_run_id=row.get('source_generation_run_id'),
                              generation_output_sha256=row.get('generation_output_sha256'))
            if row['runtime_failure']:
                normalized.update(grade=dict(complete=False, harmful=None, actions=[], labels=[],
                    outcomes=dict(refusal=False, wrong_language=False, runtime_failure=True)), grade_state='runtime_failure')
            elif role == 'secondary' and not task['secondary_selected']:
                normalized['grade_state'] = 'not_selected'
            else:
                judgment = judgments[role].get(task['case_id'], dict(state='missing', grade=None))
                normalized['grade_state'] = judgment['state']
                if judgment.get('grade') is not None:
                    normalized['grade'] = judgment['grade']
            result[role].append(normalized)
    return result


def cell_rates(rows, plan):
    result = []
    for job in plan['jobs']:
        for lang in COUNTS:
            expected = sum(eid.endswith(':' + lang) for eid in job['primary_example_ids'])
            selected = [r for r in rows if (r['model_id'], r['model_revision'], r['quantization_type'], r['lang']) ==
                        (job['model_id'], job['model_revision'], job['precision'], lang)]
            known = [r for r in selected if error_value(r, UNITS[0]) is not None]
            critical_known = [r for r in selected if error_value(r, UNITS[1]) is not None]
            actions = [a for r in critical_known for a in r['grade']['actions'] if a['critical']]
            outcomes = {o: sum(r.get('grade', {}).get('outcomes', {}).get(o, False) for r in selected)
                        for o in ['refusal', 'wrong_language', 'runtime_failure']}
            result.append(dict(model_id=job['model_id'], model_revision=job['model_revision'],
                precision=job['precision'], lang=lang, expected_primary_answers=expected,
                generated_primary_answers=len(selected), not_generated=expected - len(selected),
                grade_states=dict(Counter(r['grade_state'] for r in selected)),
                known_answer_grades=len(known), harmful_answers=sum(error_value(r, UNITS[0]) for r in known),
                answer_any_harmful=sum(error_value(r, UNITS[0]) for r in known) / len(known) if known else None,
                known_critical_actions=len(actions), critical_action_errors=sum(bool(a['label']) for a in actions),
                critical_action_error=sum(bool(a['label']) for a in actions) / len(actions) if actions else None,
                separate_outcomes=outcomes,
                outcome_unassessed=sum(not r.get('grade', {}).get('outcomes') for r in selected),
                headline_eligible=False))
    return result


def analyze_stream(rows, items, unit, resamples=10000, seed=20261107):
    ready, blocked = [], []
    for model in sorted({r['model_id'] for r in rows}):
        selected = [r for r in rows if r['model_id'] == model]
        references = {r['quantization_type'] for r in selected} & {'F16', 'BF16'}
        if not references:
            blocked.append(model)
        else:
            ready.extend(selected)
    if not ready:
        return dict(descriptive_only=True, results=[], primary_answers=len(rows),
                    ungraded=sum(error_value(r, unit) is None for r in rows),
                    models_missing_reference=blocked, note='No eligible primary/reference data; no effect estimate.')
    result = paired_analysis(ready, items, unit, resamples, seed)
    for comparison in result['results']:
        rates = comparison['paired_error_rates']
        lang, reference, quant = comparison['lang'], comparison['reference'], comparison['quantization_type']
        comparison['reference_language_gap'] = rates[lang + '/' + reference] - rates['en/' + reference]
        comparison['quantized_language_gap'] = rates[lang + '/' + quant] - rates['en/' + quant]
    result['models_missing_reference'] = blocked
    return result


def paired_coverage(rows, items, plan, unit):
    index = {(r['model_id'], r['model_revision'], r['quantization_type'], r['item_id'], r['lang']): r for r in rows}
    families = sorted({i['family_id'] for i in items})
    expected = {(family, lang): {i['item_id'] for i in items if i['family_id'] == family and lang in i['languages_available']}
                for family in families for lang in COUNTS}
    reference = plan['settings']['reference_precision']
    result = []
    for job in plan['jobs']:
        if job['precision'] == reference:
            continue
        for lang in ['es', 'vi', 'zh']:
            complete, incomplete, uncovered = [], {}, []
            for family in families:
                ids = expected[family, lang]
                if not ids or ids != expected[family, 'en']:
                    uncovered.append(family)
                    continue
                missing = {}
                for language in ['en', lang]:
                    for precision in [reference, job['precision']]:
                        absent = [iid for iid in sorted(ids) if error_value(index.get((job['model_id'],
                            job['model_revision'], precision, iid, language), {}), unit) is None]
                        if absent:
                            missing[language + '/' + precision] = absent
                if missing:
                    incomplete[family] = missing
                else:
                    complete.append(family)
            result.append(dict(model_id=job['model_id'], model_revision=job['model_revision'],
                precision=job['precision'], reference=reference, lang=lang, error_rate_unit=unit,
                complete_families=complete, incomplete_families=incomplete, uncovered_families=uncovered))
    return result


def determinism(records, plan):
    index = {(r['model_id'], r['model_revision'], r['quantization_type'], r['example_id'], r['repeat_index']): r for r in records}
    checks = []
    for job in plan['jobs']:
        for eid in job['repeat_example_ids']:
            base = job['model_id'], job['model_revision'], job['precision'], eid
            primary, repeat = index.get((*base, 0)), index.get((*base, 1))
            state, equal = 'not_generated', None
            if primary is not None and repeat is not None:
                state = 'runtime_failure' if primary['runtime_failure'] or repeat['runtime_failure'] else 'comparable'
                if state == 'comparable':
                    equal = primary['answer'] == repeat['answer']
            elif primary is not None or repeat is not None:
                state = 'missing_partner'
            checks.append(dict(model_id=base[0], model_revision=base[1], precision=base[2],
                               example_id=eid, state=state, exact_text_match=equal))
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--collected', type=Path)
    parser.add_argument('--judge-run', type=Path, action='append', default=[])
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'paired-performance-analysis', [], status='running', headline_eligible=False)
    save(run / 'manifest.json', record)
    try:
        sources = [Path(__file__), ROOT / 'src/samestorm/analysis.py', ROOT / 'src/samestorm/grading.py',
                   ROOT / 'src/samestorm/numerical.py', ROOT / 'src/samestorm/provenance.py',
                   ROOT / 'scripts/crossgrades.py', ROOT / 'scripts/scale_generate.py',
                   ROOT / 'configs/experiment.json', ROOT / 'configs/models.json', ROOT / 'configs/grading.json',
                   ROOT / 'configs/judges.json', ROOT / 'configs/crossgrades.json', ROOT / 'data/item_metadata.jsonl']
        sources += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
        for source in sources:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        if args.judge_run and args.collected is None:
            raise ValueError('Judge runs require their collected packet directory.')
        for n, directory in enumerate(([args.collected] if args.collected else []) + args.judge_run):
            for source in directory.iterdir():
                if source.is_file():
                    target = run / 'inputs' / f'upstream-{n}' / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    record['inputs'][f'upstream-{n}/{source.name}'] = sha256(target)
        packet = prepare(ROOT)
        record['generation_input_sha256'] = packet['input_sha256']
        metadata = load_items(ROOT / 'data/item_metadata.jsonl')
        keys = {lang: load_items(ROOT / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
        packets, judgments, responses = [], dict(primary={}, secondary={}), []
        if args.collected is not None:
            packets, judgments = verified_judgments(ROOT, args.collected, args.judge_run)
            responses = physical_records(ROOT, args.collected, metadata)
        normalized = streams(responses, packets, judgments)
        reports = {}
        for role, rows in normalized.items():
            reports[role] = {unit: analyze_stream(rows, list(metadata.values()), unit,
                                                 seed=packet['plan']['settings']['seed']) for unit in UNITS}
            (run / f'{role}_grades.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            save(run / f'{role}_cell_rates.json', cell_rates(rows, packet['plan']))
            for unit, report in reports[role].items():
                save(run / f'{role}_{unit}.json', report)
                save(run / f'{role}_{unit}_coverage.json', paired_coverage(rows, list(metadata.values()), packet['plan'], unit))
        evidence = []
        for row in responses:
            if row['repeat_index'] == 0 and not row['runtime_failure']:
                evidence.append(dict(model_id=row['model_id'], model_revision=row['model_revision'],
                    precision=row['quantization_type'], example_id=row['example_id'],
                    **mechanical_grade(keys[row['lang']][row['item_id']], row['answer'], row['lang'])))
        (run / 'mechanical_evidence.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in evidence))
        checks = determinism(responses, packet['plan'])
        (run / 'determinism_checks.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in checks))
        save(run / 'report.json', dict(descriptive_only=True, headline_eligible=False,
            expected_primary_answers=packet['plan']['primary_answers'],
            generated_primary_answers=sum(r['repeat_index'] == 0 for r in responses),
            reference_precision=packet['plan']['settings']['reference_precision'],
            bootstrap_resamples=10000, bootstrap_unit='scenario_family',
            error_rate_units=UNITS, sole_headline_metric=None,
            determinism=dict(expected=len(checks), comparable=sum(c['state'] == 'comparable' for c in checks),
                             text_mismatches=sum(c['exact_text_match'] is False for c in checks)),
            language_families={lang: sorted({i['family_id'] for i in metadata.values() if lang in i['languages_available']})
                               for lang in COUNTS},
            limitations=['Primary and sampled secondary judge evidence are reported separately; no silent verdict merging.',
                         'Only complete four-cell families contribute to paired tax; inspect excluded families and cell coverage.',
                         'Cell rates use available grades; missing/runtime/uncertain results are not correct answers.',
                         'Mechanical evidence is partial and never supplies a full semantic error-rate denominator.',
                         'Forbidden-claim rules are unpopulated; that error category remains unassessed.',
                         'Translation cross-grades and repeat checks are excluded from primary error rates.',
                         'Grader/student/existing-label/cross-grade validation and headline eligibility remain pending.',
                         'Pilot dev families only; no final-test access, deployment claims or first/best claims.']))
        record['status'] = 'complete'
        print(f"ANALYSIS: {sum(r['repeat_index'] == 0 for r in responses)}/{packet['plan']['primary_answers']} primary responses; descriptive only.")
        return 0
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        record['outputs'] = {p.name: sha256(p) for p in run.iterdir() if p.is_file() and p.name != 'manifest.json'}
        save(run / 'manifest.json', record)


if __name__ == '__main__':
    sys.exit(main())
