import argparse
import json
import math
import random
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.provenance import manifest, new_run_dir, sha256
from validate_dataset import COUNTS, load_items, validate as validate_dataset
from validate_experiment import validate as validate_experiment


def build_plan(root, settings, models, metadata):
    errors = validate_experiment(settings)
    if errors:
        raise ValueError('; '.join(errors))
    if not isinstance(models, list) or not models:
        raise ValueError('At least one pinned model is required.')
    ids = [m.get('id') for m in models]
    if not all(isinstance(mid, str) and mid for mid in ids) or len(set(ids)) != len(ids):
        raise ValueError('Model IDs must be nonempty and unique.')
    examples = [dict(example_id=row['item_id'] + ':' + lang, lang=lang,
                     **{key: row[key] for key in ['item_id', 'family_id', 'role', 'hazard']})
                for row in metadata for lang in row['languages_available']]
    examples.sort(key=lambda row: row['example_id'])
    example_ids = [row['example_id'] for row in examples]
    if not examples or len(set(example_ids)) != len(example_ids):
        raise ValueError('Examples must be nonempty and unique.')
    rng = random.Random(settings['seed'])
    repeats = []
    for lang in sorted({row['lang'] for row in examples}):
        language_ids = [row['example_id'] for row in examples if row['lang'] == lang]
        repeats.extend(rng.sample(language_ids, math.ceil(len(language_ids) * settings['determinism_repeat_fraction'])))
    repeats.sort()
    jobs = []
    for model in models:
        if not isinstance(model.get('revision'), str) or not re.fullmatch(r'[0-9a-f]{40}', model['revision']):
            raise ValueError('Each model requires an exact revision pin.')
        if model.get('reference') != settings['reference_precision']:
            raise ValueError('Model reference does not match experiment reference precision.')
        if not isinstance(model.get('reference_path'), str) or not model['reference_path'].strip():
            raise ValueError('Each model requires a reference file path.')
        reference = Path(model['reference_path'])
        if reference.is_absolute() or '..' in reference.parts:
            raise ValueError('Model paths must stay inside the repository.')
        for precision in settings['precisions']:
            relative = reference if precision == model['reference'] else reference.with_name('model-' + precision + '.gguf')
            path = Path(root) / relative
            status = 'missing' if not path.is_file() else ('empty' if path.stat().st_size == 0 else 'present_unverified')
            jobs.append(dict(job_index=len(jobs), model_id=model['id'], model_revision=model['revision'],
                             precision=precision, model_path=str(relative), artifact_status=status,
                             primary_example_ids=example_ids, repeat_example_ids=repeats))
    return dict(planning_only=True, execution_authorized=False,
                artifact_check='Presence only; present files still need GGUF/hash and hardware validation.',
                settings=settings, examples=examples, jobs=jobs,
                repeat_sampling='ceil(10% per language), fixed seed; same sample across models and precisions',
                repeat_example_ids=repeats,
                repeat_counts_by_language=dict(Counter(e.rsplit(':', 1)[1] for e in repeats)),
                primary_examples_per_job=len(examples), repeat_examples_per_job=len(repeats),
                primary_answers=len(jobs) * len(examples), repeat_answers=len(jobs) * len(repeats),
                total_answers=len(jobs) * (len(examples) + len(repeats)),
                missing_model_files=[job['model_path'] for job in jobs if job['artifact_status'] == 'missing'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    paths = [ROOT / 'configs/experiment.json', ROOT / 'configs/models.json', ROOT / 'data/item_metadata.jsonl',
             Path(__file__), ROOT / 'scripts/validate_dataset.py', ROOT / 'scripts/validate_experiment.py',
             ROOT / 'src/samestorm/provenance.py']
    paths += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
    record = manifest(args.run_id, 'pilot-run-plan', [p for p in paths if p.is_file()], status='running')
    output = run / 'manifest.json'
    output.write_text(json.dumps(record, indent=2) + '\n')
    try:
        errors = validate_dataset(ROOT)
        if errors:
            raise ValueError('; '.join(errors))
        settings = json.loads((ROOT / 'configs/experiment.json').read_text())
        models = json.loads((ROOT / 'configs/models.json').read_text())['models']
        metadata = list(load_items(ROOT / 'data/item_metadata.jsonl').values())
        plan = build_plan(ROOT, settings, models, metadata)
        plan_path = run / 'run_plan.json'
        plan_path.write_text(json.dumps(plan, indent=2) + '\n')
        record.update(status='complete', seed=settings['seed'], planning_only=True,
                      primary_answers=plan['primary_answers'], repeat_answers=plan['repeat_answers'],
                      outputs={str(plan_path.relative_to(ROOT)): sha256(plan_path)})
        print(f"PLAN: {len(plan['jobs'])} jobs; {plan['primary_answers']} main answers + {plan['repeat_answers']} repeats.")
        print(f"Missing model files: {len(plan['missing_model_files'])}. No execution or submission.")
        print(plan_path)
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        output.write_text(json.dumps(record, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
