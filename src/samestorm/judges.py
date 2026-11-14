"""Pinned judge setup and scale hardware checks; no model imports at module load."""
import hashlib
import json
import math
import re
from pathlib import Path

from samestorm.grading import score_annotations
from samestorm.provenance import sha256


def local_path(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError('Pinned paths must be relative to the repository.')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Pinned path escapes the repository.')
    return path


def load_config(root):
    config = json.loads((Path(root) / 'configs/judges.json').read_text())
    if config['local_judge_inference_allowed'] is not False or config['serve_precision'] != 'BF16':
        raise ValueError('Judges require scale hardware and BF16.')
    if config['validation_complete'] is not False or config['cross_grade_validation_complete'] is not False:
        raise ValueError('Migrated judge validation is still pending.')
    hardware = config['hardware']
    prepared = dict(site='TACC LS6', partition='gpu-a100', gpu_count=3,
                    gpu_name_contains='A100', minimum_memory_per_gpu_gib=37)
    if any(hardware[k] != value for k, value in prepared.items()):
        raise ValueError('Hardware configuration differs from the prepared scale protocol.')
    for role in ['primary', 'secondary']:
        spec = config[role]
        if not re.fullmatch(r'[0-9a-f]{40}', spec['revision']):
            raise ValueError('Judge requires an exact model revision.')
        path = local_path(root, spec['metadata_path'])
        if sha256(path) != spec['metadata_sha256']:
            raise ValueError('Pinned judge metadata changed.')
        metadata = json.loads(path.read_text())
        if metadata['id'] != spec['model_id'] or metadata['sha'] != spec['revision']:
            raise ValueError('Judge metadata does not match model/revision.')
        if (spec.get('weight_index') != 'model.safetensors.index.json'
                or spec['weight_index'] not in {e['rfilename'] for e in metadata['siblings']}):
            raise ValueError('Judges require the pinned Hugging Face shard index.')
        weights = {e['rfilename']: e['lfs']['sha256'] for e in metadata['siblings']
                   if re.fullmatch(r'model-\d{5}-of-\d{5}\.safetensors', e['rfilename'])}
        if not weights or weights != spec['weight_sha256']:
            raise ValueError('Judge weight pins differ from the recorded checkpoint metadata.')
        if sha256(local_path(root, spec['prompt_path'])) != spec['prompt_sha256']:
            raise ValueError('Judge prompt differs from its pin.')
        if (spec['runtime_dtype'] != 'bfloat16' or spec['thinking'] is not False
                or spec['use_model_chat_template'] is not True or spec['context_tokens'] != 4096
                or type(spec['seed']) is not int or spec['seed'] != 20261107
                or spec['generation'] != dict(do_sample=False, num_beams=1,
                                             max_new_tokens=1024, repetition_penalty=1.0)):
            raise ValueError('Judge settings differ from the prepared protocol.')
    if config['primary']['model_id'] == config['secondary']['model_id']:
        raise ValueError('Two distinct judge models are required.')
    return config


def scale_hardware_guard(gpus, environment, expected):
    if not environment.get('SLURM_JOB_ID') or environment.get('SLURM_JOB_PARTITION') != expected['partition']:
        raise ValueError('Scale inference requires the configured Slurm compute partition.')
    if len(gpus) != expected['gpu_count']:
        raise ValueError('Runtime GPU count differs from the prepared hardware configuration.')
    for gpu in gpus:
        if (expected['gpu_name_contains'] not in gpu['name'] or not math.isfinite(gpu['memory_gib'])
                or gpu['memory_gib'] < expected['minimum_memory_per_gpu_gib']):
            raise ValueError('Unapproved GPU model or memory; laptop judge inference is forbidden.')


def checkpoint_files(metadata, spec):
    """Select pinned judge shards, retaining existing translator file requirements."""
    return [e for e in metadata['siblings']
            if (e['rfilename'].endswith(('.safetensors', '.bin', '.json', '.model', '.tiktoken', '.jinja'))
                or e['rfilename'] == 'merges.txt')
            and (not spec.get('weight_index')
                 or not e['rfilename'].endswith(('.safetensors', '.bin'))
                 or e['rfilename'] in spec['weight_sha256'])]


def verify_checkpoint(root, spec, directory):
    metadata = json.loads(local_path(root, spec['metadata_path']).read_text())
    directory = Path(directory).resolve()
    verified = {}
    if spec.get('weight_index'):
        # Transformers prefers a single-file checkpoint over the shard index.
        for name in ['model.safetensors', 'pytorch_model.bin']:
            if (directory / name).exists() or (directory / name).is_symlink():
                raise ValueError('Unexpected alternate weight layout: ' + name)
    for entry in checkpoint_files(metadata, spec):
        name = entry['rfilename']
        path = (directory / name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(directory) or not path.is_file():
            raise ValueError('Missing checkpoint file or escaping path: ' + name)
        if 'lfs' in entry:
            actual, expected = sha256(path), entry['lfs']['sha256']
        else:
            body = path.read_bytes()
            actual = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            expected = entry['blobId']
        if actual != expected:
            raise ValueError('Pinned judge checkpoint file changed: ' + name)
        verified[name] = actual if 'lfs' in entry else sha256(path)
    if any(verified.get(name) != digest for name, digest in spec['weight_sha256'].items()):
        raise ValueError('Not all pinned judge weights were verified.')
    if spec.get('weight_index'):
        if spec['weight_index'] not in verified:
            raise ValueError('Missing verified judge shard index.')
        index = json.loads((directory / spec['weight_index']).read_text())
        mapping = index.get('weight_map') if isinstance(index, dict) else None
        if (not isinstance(mapping, dict) or not mapping
                or not all(isinstance(name, str) for name in mapping.values())
                or set(mapping.values()) != set(spec['weight_sha256'])):
            raise ValueError('Judge shard index must reference exactly the pinned shards.')
    return verified


def grade_judgment(key, answer, raw, truncated=False):
    if truncated:
        raise ValueError('Judge hit its generation limit.')
    fence = re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*', raw, flags=re.DOTALL)
    annotation = json.loads(fence.group(1) if fence else raw)
    if not isinstance(annotation, dict) or set(annotation) != {'actions', 'outcomes'}:
        raise ValueError('Judge must return exactly actions and outcomes.')
    actions, outcomes = annotation['actions'], annotation['outcomes']
    if not isinstance(actions, list) or not isinstance(outcomes, dict):
        raise ValueError('Judge actions must be a list and outcomes an explicit object.')
    for row in actions:
        if (not isinstance(row, dict) or set(row) != {'action_id', 'status', 'evidence_quote'}
                or not all(isinstance(row[k], str) for k in row)):
            raise ValueError('Malformed judge action record.')
    return score_annotations(key, answer, actions, outcomes)
