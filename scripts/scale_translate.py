"""Translate generated responses on scale with fixed MT systems; never produce keys."""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.judges import load_config as judge_config, verify_checkpoint
from samestorm.provenance import manifest, new_run_dir, sha256
from samestorm.translation import split_sentences
from crossgrades import digest, load_config, read_rows
from scale_judge import probe


def translated_rows(tasks, spec, config, tokenizer, model, torch):
    for task in tasks:
        pieces = []
        row = dict(task, system_id=spec['system_id'], model_id=spec['model_id'],
                   model_revision=spec['revision'], input_text_sha256=digest(task['text']),
                   translation_failure=False, truncated=False)
        try:
            kind = spec['model_kind']
            if kind != 'madlad':
                tokenizer.src_lang = spec['language_codes'][task['lang']]
            for part in split_sentences(task['text']):
                encoded = tokenizer([('<2en> ' if kind == 'madlad' else '') + part],
                                    return_tensors='pt', padding=True, truncation=False)
                if encoded['input_ids'].shape[1] > config['source_token_limit']:
                    raise ValueError('Source segment exceeds token limit; silent truncation is forbidden.')
                language_args = ({'forced_bos_token_id': tokenizer.convert_tokens_to_ids(spec['language_codes']['en'])}
                                 if kind == 'nllb' else {'decoder_start_token_id': tokenizer.lang_code_to_id['en_XX']}
                                 if kind == 'mbart' else {})
                with torch.inference_mode():
                    output = model.generate(**encoded.to('cuda:0'), **language_args, **config['generation'])
                ids = output[0].tolist()
                text = tokenizer.batch_decode(output, skip_special_tokens=True)[0]
                piece = dict(source=part, translation_en=text, output_token_ids=ids,
                             hit_generation_limit=len(ids) >= config['generation']['max_new_tokens'])
                pieces.append(piece)
                if not text.strip():
                    raise ValueError('Empty translation segment.')
        except Exception as exc:
            row.update(translation_failure=True, error=str(exc))
        row.update(segments=pieces, translation_en=' '.join(p['translation_en'] for p in pieces),
                   truncated=any(p['hit_generation_limit'] for p in pieces))
        row['output_text_sha256'] = digest(row['translation_en'])
        yield row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--system', required=True)
    parser.add_argument('--tasks', required=True, type=Path)
    parser.add_argument('--model-dir', required=True, type=Path)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'answer-translation', [], status='running', validation_complete=False)
    output = run / 'manifest.json'
    output.write_text(json.dumps(record, indent=2) + '\n')
    try:
        shutil.copy2(args.tasks, run / 'tasks.input.jsonl')
        record['inputs']['tasks.input.jsonl'] = sha256(run / 'tasks.input.jsonl')
        config = load_config(ROOT)
        spec = next((s for s in config['systems'] if s['system_id'] == args.system), None)
        if spec is None:
            raise ValueError('Unknown translator system.')
        for source in [Path(__file__), ROOT / 'scripts/crossgrades.py', ROOT / 'scripts/scale_judge.py',
                       ROOT / 'src/samestorm/translation.py', ROOT / 'src/samestorm/judges.py',
                       ROOT / 'src/samestorm/provenance.py', ROOT / 'src/samestorm/grading.py',
                       ROOT / 'configs/crossgrades.json', ROOT / 'configs/judges.json',
                       ROOT / 'configs/toolchain.json', ROOT / 'requirements-judges.lock.txt',
                       ROOT / spec['metadata_path']]:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        tasks = read_rows(run / 'tasks.input.jsonl')
        if not tasks or len({t['task_id'] for t in tasks}) != len(tasks):
            raise ValueError('Translation tasks must be nonempty and unique.')
        for task in tasks:
            if (task['kind'] != 'answer_crossgrade' or task['lang'] not in config['pairs']
                    or task['expected_systems'] != config['pairs'][task['lang']]
                    or args.system not in task['expected_systems'] or not task['text'].strip()):
                raise ValueError('Only the selected system\'s declared response tasks may enter this worker.')
        torch = probe(judge_config(ROOT), record)
        record.update(system_id=args.system, model_id=spec['model_id'], model_revision=spec['revision'],
                      segmentation=config['segmentation'], decoding_settings=config['generation'],
                      seed=config['seed'], precision=spec['runtime_dtype'],
                      weight_sha256=verify_checkpoint(ROOT, spec, args.model_dir),
                      completed_tasks=0, failed_tasks=0, truncated_tasks=0)
        output.write_text(json.dumps(record, indent=2) + '\n')
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        torch.manual_seed(config['seed'])
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        torch.use_deterministic_algorithms(True)
        dtype = torch.bfloat16 if spec['runtime_dtype'] == 'bfloat16' else torch.float32
        tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True,
                        trust_remote_code=False, use_fast=spec['model_kind'] != 'mbart')
        model = AutoModelForSeq2SeqLM.from_pretrained(args.model_dir, local_files_only=True,
                    trust_remote_code=False, weights_only=True, torch_dtype=dtype).to('cuda:0').eval()
        with (run / 'translations.jsonl').open('w', encoding='utf-8') as stream:
            for row in translated_rows(tasks, spec, config, tokenizer, model, torch):
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                stream.flush()
                record['completed_tasks'] += 1
                record['failed_tasks'] += row['translation_failure']
                record['truncated_tasks'] += row['truncated']
                output.write_text(json.dumps(record, indent=2) + '\n')
        record['status'] = 'failed' if record['failed_tasks'] or record['truncated_tasks'] else 'complete'
        return 0 if record['status'] == 'complete' else 1
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        record['outputs'] = {str(p.relative_to(run)): sha256(p) for p in run.iterdir() if p.is_file() and p != output}
        output.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    sys.exit(main())
