import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(run_id, stage, inputs, **details):
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True)
    row = dict(run_id=run_id, timestamp=datetime.now(timezone.utc).isoformat(), stage=stage,
               git_commit=commit.stdout.strip() if commit.returncode == 0 else None,
               git_dirty=bool(dirty.stdout), llama_cpp_commit=json.loads((ROOT / 'configs/toolchain.json').read_text())['llama_cpp_commit'],
               device=platform.platform(), python_version=platform.python_version(), model_id=None,
               gguf_sha256=None, quantization_type=None, importance_matrix=None,
               calibration_recipe_id=None, retrieval_mode=None, drafting=False,
               cache_state=None, prompt_version=None, decoding_settings=None,
               seed=20261107, item_set_version=None, split=None,
               inputs={str(p): sha256(p) for p in inputs})
    row.update(details)
    return row


def new_run_dir(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', run_id):
        raise ValueError('Run ID must be a simple name without path separators.')
    path = ROOT / 'results/raw' / run_id
    path.mkdir(parents=True, exist_ok=False)
    return path
