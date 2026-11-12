import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.provenance import manifest, new_run_dir, sha256
from prepare_model import verify_toolchain
from scale_generate import hardware_probe, prepare, read_rows, save, verified_artifact


def bench_command(binary, model):
    return [str(binary), '-m', str(model), '-p', '512', '-n', '128', '-r', '5',
            '-t', '4', '-ngl', '99', '-o', 'jsonl', '-v']


def check_results(rows):
    if len(rows) != 2 or {(r['n_prompt'], r['n_gen']) for r in rows} != {(512, 0), (0, 128)}:
        raise ValueError('Expected exactly prefill512 and decode128 measurements.')
    for row in rows:
        if (row['n_gpu_layers'] != 99 or len(row['samples_ts']) != 5
                or not all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in row['samples_ts'])
                or not math.isfinite(row['avg_ts']) or row['avg_ts'] <= 0):
            raise ValueError('Invalid rate, repetition count or GPU-offload settings in benchmark output.')
    return dict(prefill_tokens_per_second=next(r['avg_ts'] for r in rows if r['n_prompt']),
                decode_tokens_per_second=next(r['avg_ts'] for r in rows if r['n_gen']))


def telemetry_summary(path):
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream, skipinitialspace=True))
    if not rows:
        raise ValueError('No GPU telemetry samples were captured.')
    peaks = {}
    for name in ['memory.used [MiB]', 'temperature.gpu', 'power.draw [W]', 'clocks.current.sm [MHz]']:
        values = []
        for row in rows:
            try:
                value = float(row[name])
                if math.isfinite(value):
                    values.append(value)
            except (KeyError, TypeError, ValueError):
                pass
        peaks[name] = max(values) if values else None
    if any(value is None for value in peaks.values()):
        raise ValueError('Missing temperature/clock/power/memory telemetry fields.')
    return dict(samples=len(rows), observed_peaks=peaks,
                limitation='One-second sampling can miss peaks; these synthetic contexts do not prove 4096-token memory fit.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'measure'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--job-index', type=int, default=0)
    parser.add_argument('--model-manifest', type=Path)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'throughput-' + args.mode, [], status='running')
    save(run / 'manifest.json', record)
    try:
        packet = prepare(ROOT)
        for source in [Path(__file__), ROOT / 'configs/models.json', ROOT / 'configs/toolchain.json',
                       ROOT / 'configs/experiment.json', ROOT / 'configs/judges.json',
                       ROOT / 'scripts/scale_generate.py', ROOT / 'scripts/prepare_model.py',
                       ROOT / 'src/samestorm/provenance.py']:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        if args.mode == 'check':
            save(run / 'readiness.json', dict(measurements_present=False, jobs=len(packet['plan']['jobs']),
                 missing_model_files=packet['plan']['missing_model_files'],
                 binary_present=(ROOT / 'vendor/llama.cpp/build/bin/llama-bench').is_file(), hardware_verified=False))
        else:
            if args.model_manifest is None or not 0 <= args.job_index < len(packet['plan']['jobs']):
                raise ValueError('Select a valid job index and matching model-preparation manifest.')
            shutil.copy2(args.model_manifest, run / 'model_manifest.json')
            record['inputs']['model_manifest.json'] = sha256(run / 'model_manifest.json')
            job = packet['plan']['jobs'][args.job_index]
            record['hardware'] = hardware_probe(ROOT)
            model = verified_artifact(ROOT, job, json.loads((run / 'model_manifest.json').read_text()))
            toolchain = verify_toolchain()
            if 'GGML_CUDA:BOOL=ON' not in (toolchain / 'build/CMakeCache.txt').read_text():
                raise ValueError('Throughput requires a pinned CUDA build.')
            sys.path.insert(0, str(toolchain / 'gguf-py'))
            from gguf import GGUFReader, LlamaFileType
            reader = GGUFReader(model)
            if LlamaFileType(reader.fields['general.file_type'].contents()).name.removeprefix('MOSTLY_') != job['precision']:
                raise ValueError('GGUF file type differs from the measurement precision.')
            del reader
            binary = toolchain / 'build/bin/llama-bench'
            command = bench_command(binary, model)
            record.update(model_id=job['model_id'], model_revision=job['model_revision'],
                          quantization_type=job['precision'], gguf_sha256=sha256(model), binary_sha256=sha256(binary),
                          command=command, repetitions=5, warmup='llama-bench built-in warm-up enabled',
                          latency_environment_confirmed=False,
                          interpretation='Synthetic scale GPU microbenchmark. Not phone latency/energy or 4096-context memory validation.')
            save(run / 'manifest.json', record)
            with (run / 'gpu.csv').open('w') as gpu, (run / 'bench.jsonl').open('w') as out, (run / 'stderr.log').open('w') as err:
                telemetry = subprocess.Popen(['nvidia-smi', '--query-gpu=timestamp,name,clocks.sm,temperature.gpu,power.draw,memory.used',
                                              '--format=csv', '-l', '1'], stdout=gpu, stderr=err)
                try:
                    completed = subprocess.run(command, stdout=out, stderr=err)
                    record['returncode'] = completed.returncode
                    if telemetry.poll() is not None:
                        raise ValueError('GPU telemetry process exited early.')
                finally:
                    telemetry.terminate()
                    try:
                        telemetry.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        telemetry.kill()
                        telemetry.wait()
            if record['returncode'] != 0:
                raise ValueError('Benchmark failed; partial output and logs retained.')
            offloads = re.findall(r'offloaded (\d+)/(\d+) layers to GPU', (run / 'stderr.log').read_text())
            if not offloads or any(int(a) != int(b) or int(b) <= 0 for a, b in offloads):
                raise ValueError('Benchmark did not confirm complete GPU offload.')
            rates = check_results(read_rows(run / 'bench.jsonl'))
            save(run / 'measurement.json', dict(**rates, telemetry=telemetry_summary(run / 'gpu.csv'),
                 model_bytes=model.stat().st_size, prompt_tokens=512, generated_tokens=128))
        record['status'] = 'complete'
        print(run)
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
