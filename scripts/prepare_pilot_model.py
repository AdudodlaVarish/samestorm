"""Prepare the pinned pilot F16/Q4 artifacts on one allocated CPU node; no inference."""
import argparse
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts')]
import prepare_model as prep
from samestorm.provenance import manifest,new_run_dir,sha256
from scale_generate import verified_artifact

MODEL = 'LiquidAI/LFM3-1.7B'


def run_command(command,run,record,environment):
    record['current_command'] = [str(x) for x in command]
    (run/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    with (run/'preparation.log').open('a') as log:
        log.write('\nCOMMAND: '+repr(record['current_command'])+'\n')
        log.flush()
        subprocess.run([str(x) for x in command],cwd=ROOT,env=environment,
                       stdout=log,stderr=subprocess.STDOUT,check=True)


def existing_receipt(root,model,precision):
    relative = model['reference_path'] if precision=='F16' else str(
        Path(model['reference_path']).with_name('model-'+precision+'.gguf'))
    artifact = root/relative
    if not artifact.exists() and not artifact.is_symlink():
        return None
    job = dict(model_id=model['id'],model_revision=model['revision'],precision=precision,model_path=relative)
    for path in sorted((root/'results/raw').glob('*/manifest.json')):
        try:
            record = json.loads(path.read_text())
        except (OSError,json.JSONDecodeError):
            continue
        if (record.get('status')!='complete' or record.get('model_id')!=model['id']
                or record.get('model_revision')!=model['revision']
                or not isinstance(record.get('outputs'),list)):
            continue
        if not any(r.get('path')==relative and r.get('quantization_type')==precision for r in record['outputs']):
            continue
        try:
            verified_artifact(root,job,record)
        except (ValueError,KeyError):
            continue
        return path
    raise ValueError('Existing '+precision+' artifact has no matching complete pinned preparation receipt; preserving it.')


def prepare(run,record):
    if not os.environ.get('SLURM_JOB_ID'):
        raise ValueError('Run model preparation in the supplied Slurm batch job, not on a login node.')
    for binary in ['git','cmake','c++']:
        if not shutil.which(binary):
            raise ValueError('Missing '+binary+'; load compiler/CMake modules before submission.')
    model = next(m for m in json.loads((ROOT/'configs/models.json').read_text())['models'] if m['id']==MODEL)
    pin = json.loads((ROOT/'configs/toolchain.json').read_text())
    if not re.fullmatch(r'[0-9a-f]{40}',pin['llama_cpp_commit']):
        raise ValueError('An exact llama.cpp revision is required.')
    environment = dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                       OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',CUDA_VISIBLE_DEVICES='')
    toolchain = ROOT/'vendor/llama.cpp'
    if not toolchain.exists():
        toolchain.parent.mkdir(parents=True,exist_ok=True)
        run_command(['git','init',toolchain],run,record,environment)
        run_command(['git','-C',toolchain,'remote','add','origin',pin['llama_cpp_repository']],run,record,environment)
        run_command(['git','-C',toolchain,'fetch','--depth','1','origin',pin['llama_cpp_commit']],run,record,environment)
        run_command(['git','-C',toolchain,'checkout','--detach',pin['llama_cpp_commit']],run,record,environment)
    prep.verify_toolchain()  # Never reset or change a pre-existing checkout.
    run_command([sys.executable,toolchain/'convert_hf_to_gguf.py','--help'],run,record,environment)
    record['runtime_versions'] = {p:importlib.metadata.version(p) for p in
        ['torch','transformers','numpy','sentencepiece','safetensors','huggingface_hub','PyYAML','tqdm','requests']}
    record['compiler'] = subprocess.check_output(['c++','--version'],text=True).splitlines()[0]
    record['cmake'] = subprocess.check_output(['cmake','--version'],text=True).splitlines()[0]

    reference = existing_receipt(ROOT,model,'F16')
    quantized = existing_receipt(ROOT,model,'Q4_K_M')
    checkpoint = ROOT/model['checkpoint_path']
    if reference is None:
        if checkpoint.exists():
            record['checkpoint_sha256'] = prep.verify_checkpoint(model,checkpoint)
        else:
            run_command([sys.executable,ROOT/'scripts/prepare_model.py','download','--model-id',MODEL,
                         '--run-id',run.name+'-download'],run,record,
                        dict(environment,HF_HUB_OFFLINE='0',TRANSFORMERS_OFFLINE='0'))
        run_command([sys.executable,ROOT/'scripts/prepare_model.py','convert','--model-id',MODEL,
                     '--run-id',run.name+'-f16'],run,record,environment)
        reference = ROOT/'results/raw'/(run.name+'-f16')/'manifest.json'

    if quantized is None:
        build = toolchain/'build-prep'
        run_command(['cmake','-S',toolchain,'-B',build,'-DCMAKE_BUILD_TYPE=Release',
                     '-DGGML_CUDA=OFF','-DGGML_NATIVE=OFF','-DLLAMA_OPENSSL=OFF',
                     '-DLLAMA_BUILD_SERVER=OFF','-DLLAMA_BUILD_TESTS=OFF',
                     '-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_APP=OFF'],run,record,environment)
        run_command(['cmake','--build',build,'--target','llama-quantize','-j','4'],run,record,environment)
        run_command([sys.executable,ROOT/'scripts/prepare_model.py','quantize','--model-id',MODEL,
                     '--precision','Q4_K_M','--quantizer',build/'bin/llama-quantize',
                     '--run-id',run.name+'-q4'],run,record,environment)
        quantized = ROOT/'results/raw'/(run.name+'-q4')/'manifest.json'

    artifacts = []
    for precision,path in [('F16',reference),('Q4_K_M',quantized)]:
        relative = model['reference_path'] if precision=='F16' else str(
            Path(model['reference_path']).with_name('model-'+precision+'.gguf'))
        job = dict(model_id=MODEL,model_revision=model['revision'],precision=precision,model_path=relative)
        artifact = verified_artifact(ROOT,job,json.loads(path.read_text()))
        artifacts.append(dict(precision=precision,path=relative,sha256=sha256(artifact),
                              preparation_manifest=str(path.relative_to(ROOT)),manifest_sha256=sha256(path)))
    return dict(model_id=MODEL,model_revision=model['revision'],artifacts=artifacts,
                inference_performed=False,cuda_inference_build_verified=False,
                note='build-prep is CPU-only. The CUDA llama-server build is a separate next step.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    model = next(m for m in json.loads((ROOT/'configs/models.json').read_text())['models'] if m['id']==MODEL)
    paths = [Path(__file__),ROOT/'scripts/prepare_model.py',ROOT/'scripts/scale_generate.py',
             ROOT/'configs/models.json',ROOT/'configs/toolchain.json',ROOT/'configs/experiment.json',
             ROOT/model['metadata_path']]
    record = manifest(args.run_id,'pilot-model-preparation-bundle',paths,status='running',
                      model_id=MODEL,inference_performed=False,headline_eligible=False)
    output = run/'manifest.json'
    output.write_text(json.dumps(record,indent=2)+'\n')
    try:
        bundle = prepare(run,record)
        (run/'model_bundle.json').write_text(json.dumps(bundle,indent=2)+'\n')
        record['status'] = 'complete'
        print('PREPARED: verified F16 and Q4_K_M. No inference performed.')
        print(run/'model_bundle.json')
        return 0
    except Exception as error:
        record.update(status='failed',error=str(error))
        print('FAIL: '+str(error)+'; inspect '+str(run/'preparation.log'),file=sys.stderr)
        return 1
    finally:
        if record['status']=='running':record['status']='interrupted'
        record['outputs'] = {p.name:sha256(p) for p in run.iterdir() if p.is_file() and p!=output}
        output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    sys.exit(main())
