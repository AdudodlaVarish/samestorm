import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from samestorm.provenance import manifest, new_run_dir, sha256
from validate_experiment import validate


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def checkpoint_files(metadata):
    return [entry for entry in metadata['siblings'] if entry['rfilename'].endswith(
        ('.safetensors', '.json', '.model', '.tiktoken', '.jinja', '.py')) or entry['rfilename'] == 'merges.txt']


def verify_checkpoint(model, directory):
    metadata_path = ROOT / model['metadata_path']
    if sha256(metadata_path) != model['metadata_sha256']:
        raise ValueError('Pinned checkpoint metadata changed.')
    metadata = json.loads(metadata_path.read_text())
    if metadata['id'] != model['id'] or metadata['sha'] != model['revision']:
        raise ValueError('Checkpoint metadata does not match the selected model/revision.')
    verified = {}
    for entry in checkpoint_files(metadata):
        name = entry['rfilename']
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError('Missing checkpoint file or invalid path: ' + name)
        if 'lfs' in entry:
            actual, expected = sha256(path), entry['lfs']['sha256']
        else:
            body = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            expected = entry['blobId']
        if actual != expected:
            raise ValueError('Checkpoint file hash mismatch: ' + name)
        verified[name] = actual if 'lfs' in entry else sha256(path)
    if not any(name.endswith('.safetensors') for name in verified):
        raise ValueError('No pinned model weights were verified.')
    return verified


def verify_toolchain():
    toolchain = json.loads((ROOT / 'configs/toolchain.json').read_text())
    folder = ROOT / 'vendor/llama.cpp'
    actual = subprocess.check_output(['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(folder), 'status', '--porcelain'], text=True).strip()
    if actual != toolchain['llama_cpp_commit'] or dirty:
        raise ValueError('llama.cpp must be clean and at the pinned commit.')
    return folder


def require_absent(paths):
    existing = [str(path) for path in paths if path.exists() or path.is_symlink()]
    if existing:
        raise ValueError('Existing outputs will not be overwritten: ' + ', '.join(existing))


def require_uncompressed(reference, toolchain):
    sys.path.insert(0, str(toolchain / 'gguf-py'))
    from gguf import GGUFReader, LlamaFileType
    reader = GGUFReader(reference)
    kind = reader.fields['general.file_type'].contents()
    del reader
    if kind not in (LlamaFileType.MOSTLY_F16, LlamaFileType.MOSTLY_BF16):
        raise ValueError('Reference must be F16/BF16; never requantize a compressed file.')


def verify_reference_receipt(model, reference, receipt):
    saved = json.loads(receipt.read_text())
    if (saved.get('model_id') != model['id'] or saved.get('model_revision') != model['revision']
            or saved.get('sha256') != sha256(reference)):
        raise ValueError('Reference differs from its pinned conversion receipt.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=['download', 'convert', 'quantize'])
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    models = json.loads((ROOT / 'configs/models.json').read_text())['models']
    model = next((m for m in models if m['id'] == args.model_id), None)
    if model is None:
        parser.error('Unknown model ID; select a pinned entry from configs/models.json.')
    settings = json.loads((ROOT / 'configs/experiment.json').read_text())
    errors = validate(settings)
    if errors:
        parser.error('; '.join(errors))
    if model['reference'] != settings['reference_precision']:
        parser.error('Selected model reference does not match the experiment reference precision.')
    run = new_run_dir(args.run_id)
    inputs = [Path(__file__), ROOT / 'configs/models.json', ROOT / 'configs/toolchain.json',
              ROOT / 'configs/experiment.json', ROOT / model['metadata_path'],
              ROOT / 'src/samestorm/provenance.py']
    record = manifest(args.run_id, 'model-preparation-' + args.step, inputs, status='running',
                      model_id=model['id'], model_revision=model['revision'], seed=settings['seed'], outputs=[])
    save(run / 'manifest.json', record)
    reference = ROOT / model['reference_path']
    checkpoint = ROOT / model['checkpoint_path']
    receipt = reference.with_suffix('.gguf.json')
    try:
        if args.step == 'download':
            require_absent([checkpoint])
            metadata = json.loads((ROOT / model['metadata_path']).read_text())
            if sha256(ROOT / model['metadata_path']) != model['metadata_sha256']:
                raise ValueError('Pinned checkpoint metadata changed.')
            if metadata['sha'] != model['revision'] or metadata['id'] != model['id']:
                raise ValueError('Pinned checkpoint metadata/revision mismatch.')
            from huggingface_hub import snapshot_download
            snapshot_download(repo_id=model['id'], revision=model['revision'], local_dir=checkpoint,
                              allow_patterns=[e['rfilename'] for e in checkpoint_files(metadata)])
            record['checkpoint_sha256'] = verify_checkpoint(model, checkpoint)
        else:
            toolchain = verify_toolchain()
            if args.step == 'convert':
                require_absent([reference, receipt])
                record['checkpoint_sha256'] = verify_checkpoint(model, checkpoint)
                reference.parent.mkdir(parents=True, exist_ok=True)
                command = [sys.executable, str(toolchain / 'convert_hf_to_gguf.py'), str(checkpoint),
                           '--outfile', str(reference), '--outtype', 'f16']
                record['command'] = command
                save(run / 'manifest.json', record)
                with (run / 'conversion.log').open('w') as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                require_uncompressed(reference, toolchain)
                result = dict(model_id=model['id'], model_revision=model['revision'],
                              path=model['reference_path'], sha256=sha256(reference),
                              quantization_type='F16', conversion_run_id=args.run_id)
                save(receipt, result)
                record['outputs'].append(result)
            else:
                outputs = {q: reference.with_name('model-' + q + '.gguf')
                           for q in settings['precisions'] if q != settings['reference_precision']}
                require_absent(outputs.values())
                verify_reference_receipt(model, reference, receipt)
                require_uncompressed(reference, toolchain)
                binary = toolchain / 'build/bin/llama-quantize'
                record.update(reference_sha256=sha256(reference), binary_sha256=sha256(binary),
                              calibration_recipe_id='no-imatrix')
                for quant, output in outputs.items():
                    command = [str(binary), str(reference), str(output), quant, '4']
                    record['current_command'] = command
                    save(run / 'manifest.json', record)
                    with (run / (quant + '.log')).open('w') as log:
                        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
                    record['outputs'].append(dict(path=str(output.relative_to(ROOT)),
                        quantization_type=quant, sha256=sha256(output), bytes=output.stat().st_size, command=command))
                    save(run / 'manifest.json', record)
        record['status'] = 'complete'
    except Exception as exc:
        record.update(status='failed', error=str(exc))
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    finally:
        if record['status'] == 'running':
            record['status'] = 'interrupted'
        save(run / 'manifest.json', record)
    print(run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
