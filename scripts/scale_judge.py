import argparse
import importlib.metadata
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.grading import judge_payload
from samestorm.judges import grade_judgment, load_config, scale_hardware_guard, verify_checkpoint
from samestorm.provenance import manifest, new_run_dir, sha256
from validate_dataset import COUNTS, load_items


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def append(path, row):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')


def validation_tasks(root, path, spec, offset=0, limit=0):
    if min(offset, limit) < 0:
        raise ValueError('Task offset and limit must be nonnegative.')
    tasks = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    ids = [t['case_id'] for t in tasks]
    if not tasks or len(set(ids)) != len(ids):
        raise ValueError('Validation tasks must be nonempty and have unique case IDs.')
    tasks = tasks[offset:offset + limit] if limit else tasks[offset:]
    if not tasks:
        raise ValueError('No validation tasks selected.')
    cases = {c['case_id']: c for c in (json.loads(line) for line in
             (root / 'data/grading/cases.jsonl').read_text(encoding='utf-8').splitlines() if line.strip())}
    questions = {lang: load_items(root / f'questions/questions.{lang}.jsonl') for lang in COUNTS}
    keys = {lang: load_items(root / f'answers/answers.{lang}.jsonl') for lang in COUNTS}
    prompt = (root / spec['prompt_path']).read_text(encoding='utf-8')
    for task in tasks:
        if set(task) != {'case_id', 'synthetic', 'messages'} or task['synthetic'] is not True:
            raise ValueError('This worker accepts prepared synthetic validation only.')
        case = cases[task['case_id']]
        lang, item_id = case['lang'], case['item_id']
        payload = judge_payload(questions[lang][item_id], keys[lang][item_id], case['answer'], lang)
        messages = task['messages']
        if (not isinstance(messages, list) or len(messages) != 2
                or messages[0] != dict(role='system', content=prompt)
                or set(messages[1]) != {'role', 'content'} or messages[1]['role'] != 'user'
                or json.loads(messages[1]['content']) != payload):
            raise ValueError('Validation task differs from the pinned prompt or current question/key/case.')
        task['key'] = keys[lang][item_id]
        task['answer'] = case['answer']
    return tasks


def expected_versions(root):
    versions = {}
    for line in (root / 'requirements-judges.lock.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split('==')
        versions[name] = version
    return versions


def probe(config, record):
    # Reject laptop execution before importing torch or inspecting judge checkpoints.
    if (not os.environ.get('SLURM_JOB_ID') or
            os.environ.get('SLURM_JOB_PARTITION') != config['hardware']['partition']):
        raise ValueError('A configured Slurm GPU allocation is required; local judge inference is forbidden.')
    output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total',
                                      '--format=csv,noheader,nounits'], text=True)
    gpus = [dict(name=line.rsplit(',', 1)[0].strip(), memory_gib=float(line.rsplit(',', 1)[1]) / 1024)
            for line in output.splitlines() if line.strip()]
    scale_hardware_guard(gpus, os.environ, config['hardware'])
    hardware = dict(hostname=socket.gethostname(), gpus=gpus, job_id=os.environ['SLURM_JOB_ID'],
                    partition=os.environ['SLURM_JOB_PARTITION'],
                    cluster=os.environ.get('SLURM_CLUSTER_NAME'))
    record['hardware'] = hardware
    installed = {name: importlib.metadata.version(name) for name in expected_versions(ROOT)}
    record['runtime_versions'] = installed
    if installed != expected_versions(ROOT):
        raise ValueError('Judge environment differs from the inherited package pins.')
    import torch
    if not torch.cuda.is_available() or torch.version.cuda != '12.8':
        raise ValueError('Pinned CUDA-enabled torch runtime is unavailable.')
    torch_gpus = [dict(name=torch.cuda.get_device_properties(n).name,
                       memory_gib=torch.cuda.get_device_properties(n).total_memory / 1024**3)
                  for n in range(torch.cuda.device_count())]
    scale_hardware_guard(torch_gpus, os.environ, config['hardware'])
    hardware.update(torch_cuda=torch.version.cuda, torch_gpus=torch_gpus)
    record['environment'] = sorted(f'{d.metadata["Name"]}=={d.version}'
                                   for d in importlib.metadata.distributions())
    return torch


def run_judge(args, run, record, config, torch):
    if args.input is None or args.model_dir is None:
        raise ValueError('Judge execution requires prepared tasks and an exact local checkpoint directory.')
    spec = config[args.judge_role]
    if getattr(args, 'task_kind', 'validation') == 'crossgrade':
        from crossgrades import judge_tasks
        if sha256(args.input) != record['inputs']['tasks.input.jsonl']:
            raise ValueError('Cross-grade tasks changed after the run input copy.')
        tasks = judge_tasks(ROOT, args.input, args.judge_role, args.offset, args.limit)
    else:
        tasks = validation_tasks(ROOT, args.input, spec, args.offset, args.limit)
    record.update(model_id=spec['model_id'], model_revision=spec['revision'], judge_role=args.judge_role,
                  precision='BF16', prompt_sha256=spec['prompt_sha256'],
                  decoding_settings=spec['generation'], seed=spec['seed'], expected_tasks=len(tasks),
                  completed_tasks=0, invalid_judgments=0,
                  weight_sha256=verify_checkpoint(ROOT, spec, args.model_dir))
    save(run / 'manifest.json', record)
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.manual_seed(spec['seed'])
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False)
    model = AutoModelForCausalLM.from_pretrained(args.model_dir, local_files_only=True, trust_remote_code=False,
              torch_dtype=torch.bfloat16, device_map='auto', max_memory={**{
                  n: int(torch.cuda.get_device_properties(n).total_memory * .85)
                  for n in range(torch.cuda.device_count())}, 'cpu': 0})
    if any(str(v) in {'cpu', 'disk'} for v in model.hf_device_map.values()):
        raise ValueError('CPU/disk judge offload is forbidden.')
    model.eval()
    device = model.get_input_embeddings().weight.device
    eos = model.generation_config.eos_token_id
    eos_ids = set(eos if isinstance(eos, list) else [eos])
    for task in tasks:
        record['current_case_id'] = task['case_id']
        save(run / 'manifest.json', record)
        row = dict(case_id=task['case_id'], synthetic=task['synthetic'], judge_role=args.judge_role,
                   model_id=spec['model_id'], model_revision=spec['revision'],
                   judge_failure=True)
        row.update({k: task[k] for k in ['answer_id', 'original_lang', 'cross_grade', 'target_model_id',
                    'target_model_revision', 'quantization_type', 'example_id', 'translation_system_id',
                    'translation_run_id', 'translation_input_sha256', 'translation_output_sha256'] if k in task})
        try:
            tokens = tokenizer.apply_chat_template(task['messages'], add_generation_prompt=True,
                       tokenize=True, return_tensors='pt', enable_thinking=False).to(device)
            if tokens.shape[-1] + spec['generation']['max_new_tokens'] > spec['context_tokens']:
                raise ValueError('Judge input exceeds fixed context; truncation is forbidden.')
            with torch.inference_mode():
                output = model.generate(tokens, attention_mask=torch.ones_like(tokens),
                                        pad_token_id=tokenizer.eos_token_id, **spec['generation'])
            generated = output[0, tokens.shape[-1]:]
            row['raw_output_token_ids'] = generated.tolist()
            row['raw_judgment'] = tokenizer.decode(generated, skip_special_tokens=True)
            row['hit_generation_limit'] = (len(generated) >= spec['generation']['max_new_tokens']
                                            and generated[-1].item() not in eos_ids)
        except Exception as exc:
            row.update(judge_runtime_failure=True, error=str(exc))
            append(run / 'judgments.jsonl', row)
            raise
        try:
            row['grade'] = grade_judgment(task['key'], task['answer'], row['raw_judgment'], row['hit_generation_limit'])
            row['judge_failure'] = False
        except (ValueError, KeyError, TypeError) as exc:
            row['error'] = str(exc)
            record['invalid_judgments'] += 1
        append(run / 'judgments.jsonl', row)
        record['completed_tasks'] += 1
        save(run / 'manifest.json', record)
    record['max_allocated_bytes_per_gpu'] = [torch.cuda.max_memory_allocated(n)
                                             for n in range(torch.cuda.device_count())]
    if record['invalid_judgments']:
        raise ValueError('Invalid judge verdicts retained in judgments.jsonl; this run is not a complete usable result.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'probe', 'judge'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--judge-role', choices=['primary', 'secondary'], default='primary')
    parser.add_argument('--task-kind', choices=['validation', 'crossgrade'], default='validation')
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'judge-' + args.mode, [], status='running',
                      task_kind=args.task_kind, judge_validation_complete=False, headline_eligible=False)
    save(run / 'manifest.json', record)
    try:
        if min(args.offset, args.limit) < 0:
            raise ValueError('Offset and limit must be nonnegative.')
        paths = [Path(__file__), ROOT / 'src/samestorm/judges.py', ROOT / 'src/samestorm/grading.py',
                 ROOT / 'src/samestorm/provenance.py', ROOT / 'scripts/validate_dataset.py',
                 ROOT / 'configs/judges.json', ROOT / 'configs/prompts/judge_v1.txt',
                 ROOT / 'configs/toolchain.json', ROOT / 'configs/grading.json',
                 ROOT / 'requirements-judges.lock.txt',
                 ROOT / 'data/grading/cases.jsonl']
        paths += sorted((ROOT / 'configs/evidence/judges').rglob('*'))
        if args.task_kind == 'crossgrade':
            paths += [ROOT / 'scripts/crossgrades.py', ROOT / 'scripts/scale_generate.py',
                      ROOT / 'scripts/plan_runs.py', ROOT / 'scripts/prepare_model.py',
                      ROOT / 'scripts/validate_experiment.py', ROOT / 'configs/crossgrades.json']
        paths += [ROOT / kind / f'{kind}.{lang}.jsonl' for kind in ['questions', 'answers'] for lang in COUNTS]
        for path in paths:
            if path.is_dir():
                continue
            target = run / 'inputs' / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            record['inputs'][str(path.relative_to(ROOT))] = sha256(target)
        if args.input is not None:
            shutil.copy2(args.input, run / 'tasks.input.jsonl')
            record['inputs']['tasks.input.jsonl'] = sha256(run / 'tasks.input.jsonl')
            if args.task_kind == 'validation':
                args.input = run / 'tasks.input.jsonl'
        config = load_config(ROOT)
        if args.mode == 'check':
            report = dict(configuration_valid=True, runtime_verified=False, checkpoints_verified=False,
                          judge_validation_complete=False, submission_performed=False,
                          judges={role: dict(model_id=config[role]['model_id'], revision=config[role]['revision'])
                                  for role in ['primary', 'secondary']}, hardware=config['hardware'])
            if args.input is not None:
                if args.task_kind == 'crossgrade':
                    from crossgrades import judge_tasks
                    tasks = judge_tasks(ROOT, args.input, args.judge_role, args.offset, args.limit)
                else:
                    tasks = validation_tasks(ROOT, args.input, config[args.judge_role], args.offset, args.limit)
                report['valid_tasks'] = len(tasks)
            save(run / 'setup_report.json', report)
            print('PASS: pinned judge configuration. Hardware, environment and checkpoint execution remain unverified.')
        else:
            torch = probe(config, record)
            save(run / 'hardware.json', record['hardware'])
            if args.mode == 'judge':
                run_judge(args, run, record, config, torch)
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
