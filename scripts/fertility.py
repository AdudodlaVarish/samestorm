import argparse
import hashlib
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.judges import local_path
from samestorm.provenance import manifest, new_run_dir, sha256
from scale_generate import prepare, save


def tokenizer_files(metadata):
    names = {'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json',
             'added_tokens.json', 'vocab.json', 'merges.txt'}
    return [e for e in metadata['siblings'] if e['rfilename'] in names
            or e['rfilename'].endswith(('.model', '.jinja', '.tiktoken'))]


def verify_tokenizer(root, model, directory):
    path = local_path(root, model['metadata_path'])
    metadata = json.loads(path.read_text())
    if (sha256(path) != model['metadata_sha256'] or metadata['id'] != model['id']
            or metadata['sha'] != model['revision']):
        raise ValueError('Tokenizer checkpoint metadata differs from the model pin.')
    verified = {}
    for entry in tokenizer_files(metadata):
        name = entry['rfilename']
        path = (directory / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError('Tokenizer file missing or escaping directory: ' + name)
        if 'lfs' in entry:
            actual, expected = sha256(path), entry['lfs']['sha256']
        else:
            body = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            expected = entry['blobId']
        if actual != expected:
            raise ValueError('Tokenizer file hash mismatch: ' + name)
        verified[name] = sha256(path)
    if 'tokenizer.json' not in verified:
        raise ValueError('The selected models require their pinned tokenizer.json.')
    return verified


def measure(tokenizer, prompts):
    rows = []
    for prompt in prompts:
        text = prompt['messages'][1]['content']
        plain = tokenizer.encode(text, add_special_tokens=False, truncation=False)
        chat = tokenizer.apply_chat_template(prompt['messages'], tokenize=True, add_generation_prompt=True,
                                             enable_thinking=False, truncation=False)
        if not plain or not chat or not text.strip():
            raise ValueError('Empty question or tokenizer result.')
        rows.append(dict(example_id=prompt['example_id'], item_id=prompt['item_id'], lang=prompt['lang'],
                         question_tokens=len(plain), chat_prompt_tokens=len(chat), characters=len(text),
                         whitespace_units=len(text.split()), context_overflow=len(chat) + 320 > 4096))
    english = {r['item_id']: r for r in rows if r['lang'] == 'en'}
    summaries = []
    for lang in sorted({r['lang'] for r in rows}):
        selected = [r for r in rows if r['lang'] == lang]
        paired = [english[r['item_id']] for r in selected]
        tokens = sum(r['question_tokens'] for r in selected)
        chars = sum(r['characters'] for r in selected)
        en_tokens = sum(r['question_tokens'] for r in paired)
        en_chars = sum(r['characters'] for r in paired)
        summaries.append(dict(lang=lang, questions=len(selected), tokens=tokens, characters=chars,
            whitespace_units=sum(r['whitespace_units'] for r in selected),
            paired_english_tokens=en_tokens, total_tokens_relative_to_en=tokens / en_tokens,
            tokens_per_character=tokens / chars,
            tokens_per_character_relative_to_en=(tokens / chars) / (en_tokens / en_chars),
            context_overflows=sum(r['context_overflow'] for r in selected)))
    return rows, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['check', 'measure'])
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--model-id')
    parser.add_argument('--tokenizer-dir', type=Path)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id, 'tokenizer-' + args.mode, [], status='running')
    save(run / 'manifest.json', record)
    try:
        models = json.loads((ROOT / 'configs/models.json').read_text())['models']
        packet = prepare(ROOT)
        record['generation_input_sha256'] = packet['input_sha256']
        for source in [Path(__file__), ROOT / 'configs/models.json', ROOT / 'configs/experiment.json',
                       ROOT / 'configs/prompts/system_v1.txt', ROOT / 'scripts/scale_generate.py',
                       ROOT / 'scripts/plan_runs.py', ROOT / 'scripts/validate_dataset.py',
                       ROOT / 'scripts/validate_experiment.py', ROOT / 'src/samestorm/provenance.py']:
            target = run / 'inputs' / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            record['inputs'][str(source.relative_to(ROOT))] = sha256(target)
        if args.mode == 'check':
            save(run / 'readiness.json', dict(measurements_present=False, models=[dict(model_id=m['id'],
                 revision=m['revision'], tokenizer_directory=m['checkpoint_path'],
                 directory_present=(ROOT / m['checkpoint_path']).is_dir()) for m in models],
                 note='Token counts are pending; model weights are not required for tokenization.'))
        else:
            model = next((m for m in models if m['id'] == args.model_id), None)
            if model is None or args.tokenizer_dir is None:
                raise ValueError('Select a configured model ID and explicit pinned tokenizer directory.')
            hashes = verify_tokenizer(ROOT, model, args.tokenizer_dir)
            for name, expected in hashes.items():
                target = run / 'tokenizer' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(args.tokenizer_dir / name, target)
                if sha256(target) != expected:
                    raise ValueError('Tokenizer changed while being copied: ' + name)
                record['inputs']['tokenizer/' + name] = expected
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(run / 'tokenizer', local_files_only=True, trust_remote_code=False)
            rows, summaries = measure(tokenizer, packet['prompts'])
            (run / 'token_counts.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
            save(run / 'summary.json', summaries)
            record.update(model_id=model['id'], model_revision=model['revision'],
                          chat_template_sha256=hashlib.sha256(tokenizer.get_chat_template().encode()).hexdigest(),
                          runtime_versions={p: importlib.metadata.version(p) for p in ['tokenizers', 'transformers']},
                          token_count_method='Pinned Hugging Face tokenizer; plain question and thinking-off chat prompt.',
                          word_count_status='Whitespace units are a proxy, not Vietnamese/Chinese word counts.',
                          interpretation='Pilot question tokenization; verify HF chat counts against the GGUF runtime before final budgets.')
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
