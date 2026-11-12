"""Prepare multilingual generation inputs or run one pinned model/precision job on scale."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.judges import local_path, scale_hardware_guard
from samestorm.provenance import manifest, new_run_dir, sha256
from plan_runs import build_plan
from prepare_model import verify_toolchain
from validate_dataset import COUNTS, load_items, validate as validate_dataset


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def append(path, row):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def input_files(root):
    paths = ['configs/experiment.json', 'configs/models.json', 'configs/toolchain.json',
             'configs/prompts/system_v1.txt', 'data/item_metadata.jsonl']
    paths += [f'{kind}/{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
    for lang in COUNTS:
        for key in load_items(root / f'answers/answers.{lang}.jsonl').values():
            paths.extend(s['snapshot_path'] for s in key['sources'])
    return sorted(set(paths))


def prepare(root):
    errors = validate_dataset(root)
    if errors:
        raise ValueError('; '.join(errors))
    settings = json.loads((root / 'configs/experiment.json').read_text())
    models = json.loads((root / 'configs/models.json').read_text())['models']
    metadata = load_items(root / 'data/item_metadata.jsonl')
    plan = build_plan(root, settings, models, list(metadata.values()))
    questions = {lang: load_items(root / f'questions/questions.{lang}.jsonl') for lang in COUNTS}
    system = (root / 'configs/prompts/system_v1.txt').read_text(encoding='utf-8').strip()
    if not system:
        raise ValueError('The fixed English system prompt is required.')
    prompts = []
    for example in plan['examples']:
        lang, iid = example['lang'], example['item_id']
        if metadata[iid]['split'] != 'dev':
            raise ValueError('Only dev items are allowed; final-test access is not part of this migration.')
        text = questions[lang][iid]['question' if lang == 'en' else 'translated_question']
        prompts.append(dict(example, split='dev', paired_english_id=iid + ':en',
                            messages=[dict(role='system', content=system), dict(role='user', content=text)]))
    return dict(plan=plan, prompts=prompts,
                input_sha256={p: sha256(local_path(root, p)) for p in input_files(root)})


def assert_reviewed_inputs(root, review, expected):
    if (review.get('frozen') is not True or review.get('approved_by') != 'student'
            or not isinstance(review.get('approved_at'), str) or not review['approved_at'].strip()
            or review.get('keys_and_alignment_evidence_reviewed') is not True
            or review.get('question_translations_reviewed') is not True):
        raise ValueError('Generation requires a frozen input manifest with recorded student evidence review.')
    if review.get('artifacts') != expected:
        raise ValueError('Frozen input hashes do not match the prepared generation packet.')
    for relative, digest in expected.items():
        if sha256(local_path(root, relative)) != digest:
            raise ValueError('Reviewed input changed: ' + relative)


def verified_artifact(root, job, receipt):
    pin = json.loads((root / 'configs/toolchain.json').read_text())['llama_cpp_commit']
    stage = 'model-preparation-convert' if job['precision'] in {'F16', 'BF16'} else 'model-preparation-quantize'
    if (receipt.get('status') != 'complete' or receipt.get('stage') != stage
            or receipt.get('model_id') != job['model_id'] or receipt.get('model_revision') != job['model_revision']
            or receipt.get('llama_cpp_commit') != pin):
        raise ValueError('GGUF preparation receipt does not match the pinned model/revision/toolchain.')
    matches = [r for r in receipt['outputs'] if r['path'] == job['model_path']
               and r['quantization_type'] == job['precision']]
    if len(matches) != 1:
        raise ValueError('Exactly one matching GGUF preparation output is required.')
    path = local_path(root, job['model_path'])
    if not path.is_file() or path.stat().st_size == 0 or sha256(path) != matches[0]['sha256']:
        raise ValueError('GGUF file is missing, empty or differs from its preparation hash.')
    return path


def generation_cases(packet, job):
    prompts = {p['example_id']: p for p in packet['prompts']}
    return [(prompts[eid], 0) for eid in job['primary_example_ids']] + [
            (prompts[eid], 1) for eid in job['repeat_example_ids']]


def response_record(raw):
    choice = raw['choices'][0]
    content = choice['message']['content']
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Empty or invalid target answer.')
    if choice['message'].get('reasoning_content'):
        raise ValueError('Thinking content detected despite thinking-off settings.')
    if choice.get('finish_reason') not in {'stop', 'length'}:
        raise ValueError('Unexpected or absent generation finish reason.')
    timings = raw.get('timings', {})
    if timings.get('cache_n') != 0 or timings.get('prompt_n', 0) <= 0 or timings.get('predicted_n', 0) <= 0:
        raise ValueError('Missing token/cache evidence or prompt-cache reuse detected.')
    return dict(answer=content, generation_truncated=choice['finish_reason'] == 'length', runtime_failure=False)


def collect_answers(cases, job, request, run, record):
    for prompt, repeat in cases:
        row = {k: v for k, v in prompt.items() if k != 'messages'}
        row.update(repeat_index=repeat, model_id=job['model_id'], model_revision=job['model_revision'],
                   quantization_type=job['precision'])
        record['current_example_id'] = prompt['example_id']
        record['current_repeat_index'] = repeat
        save(run / 'manifest.json', record)
        started = time.monotonic()
        try:
            raw = request(prompt['messages'], 320)
            row['response'] = raw
            row.update(response_record(raw))
        except Exception as exc:
            row.update(answer='', runtime_failure=True, error=str(exc))
            record['runtime_failures'] += 1
        row['elapsed_seconds'] = time.monotonic() - started
        append(run / 'answers.jsonl', row)
        record['completed_answers'] += 1
        save(run / 'manifest.json', record)


def hardware_probe(root):
    expected = json.loads((root / 'configs/judges.json').read_text())['hardware']
    if not os.environ.get('SLURM_JOB_ID') or os.environ.get('SLURM_JOB_PARTITION') != expected['partition']:
        raise ValueError('Generation requires the configured Slurm GPU allocation; no laptop fallback.')
    output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total',
                                      '--format=csv,noheader,nounits'], text=True)
    gpus = [dict(name=line.rsplit(',', 1)[0].strip(), memory_gib=float(line.rsplit(',', 1)[1]) / 1024)
            for line in output.splitlines() if line.strip()]
    scale_hardware_guard(gpus, os.environ, expected)
    return dict(hostname=socket.gethostname(), gpus=gpus, job_id=os.environ['SLURM_JOB_ID'],
                partition=os.environ['SLURM_JOB_PARTITION'])


def run_server(args, packet, job, model_path, run, record):
    toolchain = verify_toolchain()
    if 'GGML_CUDA:BOOL=ON' not in (toolchain / 'build/CMakeCache.txt').read_text():
        raise ValueError('The llama.cpp inference build must enable CUDA.')
    sys.path.insert(0, str(toolchain / 'gguf-py'))
    from gguf import GGUFReader, LlamaFileType
    reader = GGUFReader(model_path)
    kind = LlamaFileType(reader.fields['general.file_type'].contents()).name.removeprefix('MOSTLY_')
    if kind != job['precision']:
        raise ValueError('GGUF file type differs from the declared job precision.')
    template = reader.fields['tokenizer.chat_template'].contents()
    if not isinstance(template, str) or not template.strip():
        raise ValueError('Model GGUF has no usable chat template.')
    record['chat_template_sha256'] = hashlib.sha256(template.encode()).hexdigest()
    record['runtime_versions'] = {name: importlib.metadata.version(name)
                                  for name in ['numpy', 'tqdm', 'PyYAML', 'requests']}
    del reader
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    settings = packet['plan']['settings']
    binary = toolchain / 'build/bin/llama-server'
    command = [str(binary), '--model', str(model_path), '--host', '127.0.0.1', '--port', str(port),
               '--ctx-size', str(settings['context_tokens']), '--parallel', '1', '--n-gpu-layers', '99',
               '--threads', '4', '--reasoning', 'off', '--jinja', '--no-webui', '--no-cache-prompt',
               '--no-context-shift', '--fit', 'off', '--alias', args.run_id]
    record.update(binary_sha256=sha256(binary), command=command, decoding_settings=settings['decoding'],
                  seed=settings['seed'], cache_state='prompt cache disabled', retrieval_mode='closed_book',
                  prompt_version='system_v1', expected_answers=len(generation_cases(packet, job)),
                  completed_answers=0, runtime_failures=0)
    save(run / 'manifest.json', record)
    base = f'http://127.0.0.1:{port}'
    processes = []
    with (run / 'server.log').open('w') as log, (run / 'gpu.csv').open('w') as gpu:
        try:
            server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            processes.append(server)
            processes.append(subprocess.Popen(['nvidia-smi',
                '--query-gpu=timestamp,name,clocks.sm,temperature.gpu,power.draw,memory.used',
                '--format=csv', '-l', '1'], stdout=gpu, stderr=log))
            deadline = time.monotonic() + 120
            while True:
                if server.poll() is not None:
                    raise RuntimeError('Target server exited; server.log is preserved.')
                try:
                    with urlopen(base + '/health', timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError('Target startup timed out.')
                time.sleep(.2)
            log.flush()
            if processes[1].poll() is not None:
                raise RuntimeError('GPU telemetry logger exited; preserve gpu.csv and server.log.')
            offload = re.search(r'offloaded (\d+)/(\d+) layers to GPU', (run / 'server.log').read_text())
            if not offload or int(offload[1]) != int(offload[2]) or int(offload[2]) <= 0:
                raise ValueError('Server did not confirm complete GPU layer offload.')

            def request(messages, limit):
                if server.poll() is not None:
                    raise RuntimeError('Target server died; no automatic retry or fallback.')
                body = dict(model=args.run_id, messages=messages, **settings['decoding'],
                            seed=settings['seed'], cache_prompt=False, stream=False,
                            chat_template_kwargs={'enable_thinking': False})
                body['max_tokens'] = limit
                req = Request(base + '/v1/chat/completions', json.dumps(body).encode(),
                              headers={'Content-Type': 'application/json'})
                try:
                    with urlopen(req, timeout=300) as response:
                        text = response.read().decode('utf-8')
                except HTTPError as exc:
                    raise ValueError(f'HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")}') from exc
                try:
                    return json.loads(text)
                except ValueError as exc:
                    raise ValueError('Invalid JSON HTTP response: ' + text) from exc

            save(run / 'warmup.json', request([dict(role='user', content='Reply with READY.')], 16))
            collect_answers(generation_cases(packet, job), job, request, run, record)
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    if record['runtime_failures']:
        raise ValueError('Runtime failures retained; this run is not a complete usable generation result.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'generate'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--packet', type=Path)
    parser.add_argument('--review-manifest', type=Path)
    parser.add_argument('--model-manifest', type=Path)
    parser.add_argument('--job-index', type=int, default=int(os.environ.get('SLURM_ARRAY_TASK_ID', 0)))
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'generation-' + args.mode, [], status='running', benchmark_frozen=False)
    save(run / 'manifest.json', record)
    try:
        paths = [Path(__file__), ROOT / 'scripts/plan_runs.py', ROOT / 'scripts/prepare_model.py',
                 ROOT / 'scripts/validate_dataset.py', ROOT / 'scripts/validate_experiment.py',
                 ROOT / 'src/samestorm/judges.py', ROOT / 'src/samestorm/provenance.py',
                 ROOT / 'src/samestorm/grading.py', ROOT / 'configs/judges.json']
        paths += [local_path(ROOT, p) for p in input_files(ROOT) if not p.startswith('sources/')]
        for source in paths:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        for name, source in [('packet.json', args.packet), ('review_manifest.json', args.review_manifest),
                             ('model_manifest.json', args.model_manifest)]:
            if source is not None:
                shutil.copy2(source, run / name)
                record['inputs'][name] = sha256(run / name)
        current = prepare(ROOT)
        if args.mode == 'check':
            save(run / 'generation_packet.json', current)
            save(run / 'review_template.json', dict(frozen=False, approved_by=None, approved_at=None,
                 keys_and_alignment_evidence_reviewed=False, question_translations_reviewed=False,
                 artifacts=current['input_sha256']))
            save(run / 'readiness.json', dict(benchmark_frozen=False, execution_authorized=False,
                 hardware_verified=False, gguf_hashes_verified=False,
                 missing_model_files=current['plan']['missing_model_files'],
                 primary_answers=current['plan']['primary_answers'], repeat_answers=current['plan']['repeat_answers'],
                 blockers=['Recorded student review and frozen input hashes are required before generation.',
                           'Matching model-preparation receipts and GGUFs are required for each job.',
                           'Allocated TACC hardware and a pinned CUDA llama.cpp build must pass runtime checks.']))
            print(f"PREPARED: {len(current['prompts'])} prompts, {len(current['plan']['jobs'])} jobs; generation remains blocked.")
        else:
            if args.packet is None or args.review_manifest is None or args.model_manifest is None:
                raise ValueError('Generation requires explicit packet, reviewed freeze manifest and model-preparation manifest.')
            packet = json.loads((run / 'packet.json').read_text())
            if packet['input_sha256'] != current['input_sha256'] or packet['prompts'] != current['prompts']:
                raise ValueError('Generation packet differs from current pinned inputs.')
            # Model file presence can change after planning; executable job identities/settings cannot.
            for a, b in zip(packet['plan']['jobs'], current['plan']['jobs'], strict=True):
                if {k: v for k, v in a.items() if k != 'artifact_status'} != {k: v for k, v in b.items() if k != 'artifact_status'}:
                    raise ValueError('Generation job matrix differs from the current experiment.')
            if packet['plan']['settings'] != current['plan']['settings']:
                raise ValueError('Generation settings differ from the fixed experiment.')
            review = json.loads((run / 'review_manifest.json').read_text())
            assert_reviewed_inputs(ROOT, review, current['input_sha256'])
            if not 0 <= args.job_index < len(current['plan']['jobs']):
                raise ValueError('Job index is outside the model/precision matrix.')
            job = current['plan']['jobs'][args.job_index]
            record.update(model_id=job['model_id'], model_revision=job['model_revision'],
                          quantization_type=job['precision'], benchmark_frozen=True,
                          reviewed_inputs=current['input_sha256'])
            record['hardware'] = hardware_probe(ROOT)
            model_path = verified_artifact(ROOT, job, json.loads((run / 'model_manifest.json').read_text()))
            record['gguf_sha256'] = sha256(model_path)
            run_server(args, current, job, model_path, run, record)
        record['status'] = 'complete'
        return 0
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        record['outputs'] = {str(p.relative_to(run)): sha256(p) for p in run.rglob('*')
                             if p.is_file() and p.name != 'manifest.json'}
        save(run / 'manifest.json', record)


if __name__ == '__main__':
    sys.exit(main())
