import argparse
import json
import math
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.judges import scale_hardware_guard
from samestorm.provenance import manifest, new_run_dir, sha256
from scale_generate import generation_cases, prepare, read_rows, save
from throughput import check_results


def verified_output(directory, stage, name):
    record = json.loads((directory / 'manifest.json').read_text())
    if record['stage'] != stage or record['status'] != 'complete' or record['outputs'][name] != sha256(directory / name):
        raise ValueError('Measurement stage/status/output hash mismatch: ' + str(directory))
    return record


def estimate(packet, token_counts, rates):
    jobs = []
    for job in packet['plan']['jobs']:
        model = job['model_id'], job['model_revision']
        cell = (*model, job['precision'])
        missing = []
        if model not in token_counts:
            missing.append('tokenizer_counts')
        if cell not in rates:
            missing.append('throughput')
        row = dict(job_index=job['job_index'], model_id=model[0], model_revision=model[1],
                   precision=job['precision'], missing=missing, estimated_seconds=None, allocated_a100_hours=None)
        if not missing:
            cases = generation_cases(packet, job)
            counts = token_counts[model]
            if any(counts[p['example_id']]['context_overflow'] for p, _ in cases):
                row['missing'] = ['context_overflow_requires_resolution']
            else:
                prompt_tokens = sum(counts[p['example_id']]['chat_prompt_tokens'] for p, _ in cases)
                output_tokens = len(cases) * packet['plan']['settings']['decoding']['max_tokens']
                rate = rates[cell]
                seconds = prompt_tokens / rate['prefill_tokens_per_second'] + output_tokens / rate['decode_tokens_per_second']
                row.update(prompt_tokens=prompt_tokens, output_token_cap=output_tokens, estimated_seconds=seconds,
                           allocated_a100_hours=seconds * rate['allocated_gpus'] / 3600)
                row['throughput_run_id'] = rate.get('run_id')
                row['measured_gguf_sha256'] = rate.get('gguf_sha256')
        jobs.append(row)
    available = [j for j in jobs if j['estimated_seconds'] is not None]
    complete = len(available) == len(jobs)
    return dict(jobs=jobs, measured_cells=len(available), total_cells=len(jobs), generation_estimate_complete=complete,
                generation_only_total_seconds=sum(j['estimated_seconds'] for j in jobs) if complete else None,
                generation_only_allocated_a100_hours=sum(j['allocated_a100_hours'] for j in jobs) if complete else None,
                full_campaign_estimate_available=False, full_campaign_a100_hours=None,
                formula='sum(chat prompt tokens)/prefill rate + response count * 320/decode rate, including repeat checks',
                limitations=['Output-cap scenario, not a measured wall time or guaranteed upper bound.',
                             'HF chat counts need GGUF runtime verification; synthetic 512/128 rates may not scale linearly.',
                             'Model loading, warm-up, HTTP overhead, failures, queue time, judges and translations are excluded.',
                             'Memory samples do not establish 4096-context fit. No phone latency or energy claims.',
                             'A campaign estimate and required approval are still needed before jobs exceeding 20 A100-hours.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--tokenization-run', type=Path, action='append', default=[])
    parser.add_argument('--throughput-run', type=Path, action='append', default=[])
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'generation-runtime-estimate', [], status='running')
    save(run / 'manifest.json', record)
    try:
        packet = prepare(ROOT)
        record['generation_input_sha256'] = packet['input_sha256']
        for source in [Path(__file__), ROOT / 'scripts/throughput.py', ROOT / 'scripts/scale_generate.py',
                       ROOT / 'configs/models.json', ROOT / 'configs/experiment.json', ROOT / 'configs/toolchain.json',
                       ROOT / 'configs/judges.json', ROOT / 'src/samestorm/provenance.py']:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        for n, directory in enumerate(args.tokenization_run + args.throughput_run):
            for source in directory.iterdir():
                if source.is_file():
                    target = run / 'inputs' / f'measurement-{n}' / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    record['inputs'][f'measurement-{n}/{source.name}'] = sha256(target)
        models = {(j['model_id'], j['model_revision']) for j in packet['plan']['jobs']}
        cells = {(j['model_id'], j['model_revision'], j['precision']) for j in packet['plan']['jobs']}
        token_counts, rates = {}, {}
        for directory in args.tokenization_run:
            saved = verified_output(directory, 'tokenizer-measure', 'token_counts.jsonl')
            model = saved['model_id'], saved['model_revision']
            if model not in models or model in token_counts or saved['generation_input_sha256'] != packet['input_sha256']:
                raise ValueError('Duplicate, retired or stale tokenizer measurement.')
            rows = read_rows(directory / 'token_counts.jsonl')
            index = {r['example_id']: r for r in rows}
            if len(index) != len(rows) or set(index) != {p['example_id'] for p in packet['prompts']}:
                raise ValueError('Tokenizer measurement must cover each current prompt exactly once.')
            if any(type(r['chat_prompt_tokens']) is not int or r['chat_prompt_tokens'] <= 0
                   or type(r['context_overflow']) is not bool
                   or r['context_overflow'] != (r['chat_prompt_tokens'] + 320 > 4096) for r in rows):
                raise ValueError('Invalid measured prompt token count.')
            token_counts[model] = index
        hardware = json.loads((ROOT / 'configs/judges.json').read_text())['hardware']
        pin = json.loads((ROOT / 'configs/toolchain.json').read_text())['llama_cpp_commit']
        for directory in args.throughput_run:
            saved = verified_output(directory, 'throughput-measure', 'measurement.json')
            cell = saved['model_id'], saved['model_revision'], saved['quantization_type']
            if cell not in cells or cell in rates or saved['llama_cpp_commit'] != pin:
                raise ValueError('Duplicate, retired or wrong-toolchain throughput measurement.')
            verified_output(directory, 'throughput-measure', 'bench.jsonl')
            measured = check_results(read_rows(directory / 'bench.jsonl'))
            summary = json.loads((directory / 'measurement.json').read_text())
            if any(summary[key] != value for key, value in measured.items()):
                raise ValueError('Saved rates differ from the raw benchmark output.')
            observed = saved['hardware']
            scale_hardware_guard(observed['gpus'], dict(SLURM_JOB_ID=observed['job_id'],
                                 SLURM_JOB_PARTITION=observed['partition']), hardware)
            if not all(math.isfinite(value) and value > 0 for value in measured.values()):
                raise ValueError('Invalid measured rate.')
            rates[cell] = dict(measured, allocated_gpus=len(observed['gpus']),
                               run_id=saved['run_id'], gguf_sha256=saved['gguf_sha256'])
        report = estimate(packet, token_counts, rates)
        save(run / 'runtime_estimate.json', report)
        record.update(status='complete', generation_estimate_complete=report['generation_estimate_complete'])
        print(f"ESTIMATE: {report['measured_cells']}/{report['total_cells']} cells have both measurements; full campaign cost remains pending.")
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
