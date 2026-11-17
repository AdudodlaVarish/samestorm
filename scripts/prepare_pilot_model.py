"""Prepare pinned pilot F16/Q4 files; optionally generate the reviewed English pilot on A100."""
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
import scale_generate as generation
from samestorm.provenance import manifest,new_run_dir,sha256
from scale_generate import verified_artifact

MODEL = 'LiquidAI/LFM3-1.7B'


def gcc_cmake_args(build,cuda=False):
    compilers = [('C',shutil.which('gcc')),('CXX',shutil.which('g++'))]
    if cuda:compilers.append(('CUDA_HOST',shutil.which('g++')))
    cache = (build/'CMakeCache.txt').read_text() if (build/'CMakeCache.txt').exists() else ''
    for language,path in compilers:
        if path is None:raise ValueError('Load a GCC module providing gcc and g++ before building.')
        cached = re.search(r'^CMAKE_'+language+r'_COMPILER:[A-Z_]+=(.+)$',cache,re.M)
        if cached and Path(cached[1]).resolve()!=Path(path).resolve():
            raise ValueError('Cached compiler differs in '+str(build)+': '+cached[1]+
                             '. Preserve that build directory under another name before rebuilding with '+path+'.')
    return ['-DCMAKE_'+language+'_COMPILER='+path for language,path in compilers]


def check_compiler(run,record,environment):
    gcc_cmake_args(run/'compiler-probe-build')
    compiler = shutil.which('g++')
    source,binary = run/'compiler-check.cpp',run/'compiler-check'
    source.write_text('''#include <filesystem>
int main() {
    namespace fs = std::filesystem;
    const auto current = fs::current_path();
    const auto relative = fs::relative(current, current.parent_path());
    return !fs::is_directory(fs::status(current)) || relative.empty();
}
''')
    record['compiler_paths'] = dict(c=shutil.which('gcc'),cxx=compiler)
    record['compiler'] = subprocess.check_output([compiler,'--version'],text=True).splitlines()[0]
    run_command([compiler,'-std=c++17',source,'-o',binary],run,record,environment)
    run_command([binary],run,record,environment)
    record['compiler_check_sha256'] = sha256(binary)


def generation_preflight(run,record):
    record['hardware'] = generation.hardware_probe(ROOT,development_pilot=True)
    for binary in ['nvcc','gcc','g++']:
        if not shutil.which(binary):
            raise ValueError('Missing '+binary+'; load compatible GCC/CUDA modules before submission.')
    packet = generation.prepare(ROOT,pilot=True,english_only=True)
    review = ROOT/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json'
    generation.assert_reviewed_inputs(ROOT,json.loads(review.read_text()),packet['input_sha256'],
                                      [p['example_id'] for p in packet['prompts']])
    shutil.copy2(review,run/'review_manifest.json')
    generation.save(run/'generation_packet.json',packet)
    record['inputs']['generation_review_manifest'] = sha256(run/'review_manifest.json')
    return packet


def generate_pilot(run,record,bundle,packet):
    environment = dict(os.environ,HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
                       OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
    toolchain = prep.verify_toolchain()
    build = toolchain/'build'
    record['nvcc'] = subprocess.check_output(['nvcc','--version'],text=True).strip()
    run_command(['cmake','-S',toolchain,'-B',build,'-DCMAKE_BUILD_TYPE=Release',
                 '-DGGML_CUDA=ON','-DCMAKE_CUDA_ARCHITECTURES=80','-DGGML_NATIVE=OFF',
                 *gcc_cmake_args(build,cuda=True),
                 '-DLLAMA_OPENSSL=OFF','-DLLAMA_BUILD_COMMON=ON','-DLLAMA_BUILD_TOOLS=ON',
                 '-DLLAMA_BUILD_SERVER=ON','-DLLAMA_BUILD_TESTS=OFF',
                 '-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_APP=OFF','-DLLAMA_BUILD_UI=OFF'],
                run,record,environment)
    run_command(['cmake','--build',build,'--target','llama-server','-j','4'],run,record,environment)
    record['generation_runs'] = []
    outputs = []
    for job in packet['plan']['jobs']:
        artifact = next(a for a in bundle['artifacts'] if a['precision']==job['precision'])
        receipt = ROOT/artifact['preparation_manifest']
        if sha256(receipt)!=artifact['manifest_sha256']:
            raise ValueError('Model preparation manifest changed before generation.')
        child_id = run.name+'-generate-'+job['precision'].lower()
        child = ROOT/'results/raw'/child_id
        record['generation_runs'].append(str(child.relative_to(ROOT)))
        try:
            run_command([sys.executable,ROOT/'scripts/scale_generate.py','generate','--pilot','--english-only',
                         '--run-id',child_id,'--packet',run/'generation_packet.json',
                         '--review-manifest',run/'review_manifest.json','--model-manifest',receipt,
                         '--job-index',str(job['job_index'])],run,record,environment)
        finally:
            record['inference_performed'] = bool(record['inference_performed']
                or (child/'warmup.json').exists() or (child/'answers.jsonl').exists())
        result = json.loads((child/'manifest.json').read_text())
        expected = len(generation.generation_cases(packet,job))
        if (result.get('status')!='complete' or result.get('completed_answers')!=expected
                or result.get('expected_answers')!=expected or result.get('runtime_failures')!=0):
            raise ValueError('Generation did not produce a complete usable result: '+child_id)
        outputs.append(dict(precision=job['precision'],answers=str((child/'answers.jsonl').relative_to(ROOT)),
                            answers_sha256=sha256(child/'answers.jsonl'),
                            manifest=str((child/'manifest.json').relative_to(ROOT)),
                            manifest_sha256=sha256(child/'manifest.json'),completed_answers=expected))
    generation.save(run/'generation_bundle.json',dict(scope='english_first_development_pilot',
        outputs=outputs,main_answers=packet['plan']['primary_answers'],
        repeat_answers=packet['plan']['repeat_answers'],judges_run=False,headline_eligible=False))


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
    for binary in ['git','cmake','gcc','g++']:
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
    compiler_args = gcc_cmake_args(toolchain/'build-prep')
    check_compiler(run,record,environment)
    run_command([sys.executable,toolchain/'convert_hf_to_gguf.py','--help'],run,record,environment)
    record['runtime_versions'] = {p:importlib.metadata.version(p) for p in
        ['torch','transformers','tokenizers','numpy','sentencepiece','safetensors','huggingface_hub','PyYAML','tqdm','requests']}
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
                     *compiler_args,
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--generate-english-pilot',action='store_true',
                        help='On A100, also build CUDA llama-server and generate the reviewed 12-answer pilot.')
    modes.add_argument('--check-compiler',action='store_true',
                       help='Only compile/link/run a tiny C++17 filesystem check; no allocation or model work.')
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    model = next(m for m in json.loads((ROOT/'configs/models.json').read_text())['models'] if m['id']==MODEL)
    paths = [Path(__file__),ROOT/'scripts/prepare_model.py',ROOT/'scripts/scale_generate.py',
             ROOT/'configs/models.json',ROOT/'configs/toolchain.json',ROOT/'configs/experiment.json',
             ROOT/model['metadata_path'],ROOT/'requirements-model-prep.txt']
    if args.generate_english_pilot:
        paths += [ROOT/'configs/judges.json',ROOT/'src/samestorm/judges.py']
    stage = 'pilot-preparation-and-generation' if args.generate_english_pilot else 'pilot-model-preparation-bundle'
    if args.check_compiler:stage = 'compiler-link-check'
    record = manifest(args.run_id,stage,paths,status='running',
                      model_id=MODEL,inference_performed=False,headline_eligible=False)
    output = run/'manifest.json'
    output.write_text(json.dumps(record,indent=2)+'\n')
    try:
        if args.check_compiler:
            check_compiler(run,record,dict(os.environ))
            for build in ['build-prep','build']:
                gcc_cmake_args(ROOT/'vendor/llama.cpp'/build,cuda=build=='build')
        else:
            packet = generation_preflight(run,record) if args.generate_english_pilot else None
            bundle = prepare(run,record)
            (run/'model_bundle.json').write_text(json.dumps(bundle,indent=2)+'\n')
            if args.generate_english_pilot:
                generate_pilot(run,record,bundle,packet)
        record['status'] = 'complete'
        print('PASS: GCC C++17 filesystem compile, link and runtime check.' if args.check_compiler
              else 'COMPLETE: 12 English pilot answers; no judges run.' if args.generate_english_pilot
              else 'PREPARED: verified F16 and Q4_K_M. No inference performed.')
        print(output if args.check_compiler else
              run/('generation_bundle.json' if args.generate_english_pilot else 'model_bundle.json'))
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
