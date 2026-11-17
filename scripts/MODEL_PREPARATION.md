# Model preparation

Research prototype. Follow local officials and call 911 in an emergency.

The selected models are LiquidAI/LFM3-1.7B and Qwen/Qwen3-4B-Instruct-2507.
Exact revisions, checkpoint metadata hashes and output paths are in
`configs/models.json`. This commit contains preparation tools and public metadata;
weights and llama.cpp have not been installed in this repository.

Install conversion dependencies in the local environment when ready:

```sh
.venv/bin/python -m pip install -r requirements-model-prep.txt
git clone https://github.com/ggml-org/llama.cpp vendor/llama.cpp
git -C vendor/llama.cpp checkout f7591a6a01f9273de03331732bdc0b39721168be
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DGGML_CUDA=OFF
cmake --build vendor/llama.cpp/build --target llama-quantize -j 4
```

The CPU build above is for preparing quantized files. CUDA inference builds need
the actual device architecture and a separate hardware check.

Run each step with a unique run ID; repeat for the other selected model:

```sh
.venv/bin/python scripts/prepare_model.py download --model-id LiquidAI/LFM3-1.7B --run-id lfm3-download
.venv/bin/python scripts/prepare_model.py convert --model-id LiquidAI/LFM3-1.7B --run-id lfm3-f16
.venv/bin/python scripts/prepare_model.py quantize --model-id LiquidAI/LFM3-1.7B --run-id lfm3-quants
```

Checkpoint files are verified against pinned upstream hashes before conversion.
Conversion uses the pinned llama.cpp converter and produces an F16 reference plus
a hash receipt. Quantization verifies that receipt and uses the uncompressed
reference directly for Q8_0, Q6_K, Q4_K_M, Q3_K_M and Q2_K. Existing outputs are
never overwritten. Failures, partial files and per-run manifests are retained.
Inspect a failed attempt before making a new run; there are no automatic retries.

Weights stay in ignored `models/`; receipts/logs stay in ignored `results/raw/`.
No model answering, judges, TACC submission or calibration is performed here.
Full conversion and all six formats still need runtime testing. Qwen4 F16 weights
alone exceed the local 7 GiB inference budget; conversion does not prove GPU fit.

## Conversion environment on LS6

Use a separate `.venv-model-prep` environment for the pilot. Job 3587860 downloaded
the pinned checkpoint successfully but failed because Transformers 4.57.6 in the
judge environment cannot load the checkpoint's `TokenizersBackend` class. That
class belongs to the
[Transformers v5 tokenizer backend](https://github.com/huggingface/transformers/blob/main/MIGRATION_GUIDE_V5.md).
The preparation requirements now pin Transformers 5.23.0, Tokenizers 0.23.3 and
Hugging Face Hub 2.4.0, with CPU PyTorch 2.11.0. The judge environment retains its
original versions. CUDA answer generation runs through llama-server rather than
PyTorch, so CPU PyTorch is sufficient in this new environment.

After pulling the fix, create and install this environment once on the login node:

```bash
cd "$SAMESTORM_REPO"
"$SAMESTORM_REPO/.venv-judges/bin/python" -m venv "$SAMESTORM_REPO/.venv-model-prep"
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-model-prep/bin/python"
"$SAMESTORM_PYTHON" -m pip install --no-compile -r requirements-model-prep.txt
"$SAMESTORM_PYTHON" -m pip check
```

Use this Python path again after reconnecting. Do not install these requirements
over `.venv-judges`, or install the upstream converter's requirements over this
environment: its pinned Transformers 4.57.6 would recreate the incompatibility.
Model/checkpoint/toolchain pins and the downloaded files remain unchanged.

Each F16 conversion now first runs the exact pinned converter with `--vocab-only`.
Its `tokenizer-check.log` and hashed `tokenizer-check.gguf` stay in the conversion
run directory; full tensor conversion starts only after this check succeeds.
These tokenizer-only GGUFs are metadata checks, not inference references.

The reported v4 failure was reproduced locally using hash-verified tokenizer and
configuration files from the exact model revision. Version 5.23.0 passed a token
round trip and the pinned converter's actual vocabulary-only export. Receipts are
in `results/raw/tokenizer-compatibility-20261117-001/`. No model weights, full F16
conversion or GPU inference were used in that local check.

For retrying job 3587860, the checkpoint can be reused after its hashes pass.
The reported directory contained no F16 file, so no cleanup is needed. Submit a
fresh `pilot.sbatch` job after setting this new Python path and loading CUDA;
the new job ID gives it fresh run directories and preserves the failed run.

## Compiler recovery after job 3589077

The next job completed the tokenizer check and F16 conversion (287 tensors,
approximately 3.5 GB), then failed linking llama-quantize with unresolved C++17
filesystem functions. Its link command used `/usr/bin/c++`, while the available
GCC toolchain was under `/opt/apps/gcc/9.4.0` and the Intel module remained loaded.
The CPU CMake command had not explicitly selected gcc/g++. Both CPU and CUDA
builds now select them explicitly and reject caches naming other compilers.
No `-lstdc++fs` workaround is applied: GCC 9 and later integrate this functionality
into libstdc++ ([GCC release notes](https://gcc.gnu.org/gcc-9/changes.html#libstdcxx)).

On LS6, use the available GCC 12.2.0 module followed by CUDA 12.8. GCC 12 is in
[CUDA 12.8's supported host compiler range](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-installation-guide-linux/#host-compiler-support-policy).
After committing/pushing this fix and pulling it on LS6:

```bash
source "$SCRATCH/samestorm2-env.sh"
cd "$SAMESTORM_REPO"
git pull --ff-only
module load gcc/12.2.0
module load cuda/12.8
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-model-prep/bin/python"
g++ --version
```

Preserve old build trees so the new compiler starts with fresh objects and cache.
This moves build files only; model weights and run receipts stay in place:

```bash
for build in build-prep build; do
    if [ -d "vendor/llama.cpp/$build" ]; then
        mv -T -n "vendor/llama.cpp/$build" \
          "vendor/llama.cpp/${build}-before-gcc12-3589077"
    fi
done
```

Run the small compile/link/runtime check before another allocation, using a fresh
run ID. It compiles and runs a tiny filesystem program; it loads no models and
does not require Slurm, CUDA or GPU access:

```bash
"$SAMESTORM_PYTHON" scripts/prepare_pilot_model.py \
  --check-compiler --run-id compiler-check-3589077-001
```

Continue only after it prints `PASS`. A failure preserves the compiler command,
source, logs and manifest under that run directory; inspect `preparation.log`.
The full job repeats this check before model work. The check also rejects stale
CPU/CUDA compiler caches; it does not verify a CUDA build or GPU execution.

```bash
sbatch -A CCR23028 scripts/jobs/pilot.sbatch
```

The retry verifies and reuses the successful F16 receipt from job 3589077, then
builds the quantizer, creates Q4 and proceeds to CUDA generation. It does not
repeat a valid download or F16 conversion. No Python dependency reinstall is
needed. Keep the GCC/CUDA modules loaded when submitting and using these binaries.

## Prepare and generate in one A100 job

`scripts/jobs/pilot.sbatch` combines preparation and the accepted English-first
generation in one allocation. It requests either `gpu-a100` or `gpu-a100-dev`;
Slurm chooses one. Both retain checks for three A100 GPUs and at least 37 GiB
per GPU. The job has a two-hour ceiling, matching the
[LS6 development queue limit](https://docs.tacc.utexas.edu/hpc/lonestar6/#running-jobs).
GPU allocation time includes download, conversion and compilation, even before
answer generation starts. The CPU-only alternative remains documented below.

After committing/pushing these changes locally, in the LS6 login session:

```bash
source "$SCRATCH/samestorm2-env.sh"
cd "$SAMESTORM_REPO"
git pull --ff-only
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-model-prep/bin/python"
module load gcc/12.2.0
module load cuda/12.8
command -v git
command -v cmake
command -v gcc
command -v g++
command -v nvcc
```

Each check must print a path. If tools are missing, inspect `module spider gcc`,
`module spider cmake` and `module spider cuda`, then load compatible modules
available on LS6. In particular, CUDA-enabled PyTorch does not supply the `nvcc`
compiler required to build llama.cpp. The job inherits the submitted module
environment and records compiler/CUDA versions; it does not install packages.
Create the conversion environment above first if this Python path does not exist.
If compiler caches already exist from a different compiler, follow the recovery
section above. Run `--check-compiler` with a fresh run ID before submission.

```bash
mkdir -p results/raw
sbatch -A CCR23028 scripts/jobs/pilot.sbatch
```

Only this one submission is needed for the combined path. The script invokes
`prepare_pilot_model.py --generate-english-pilot`. It first validates the frozen
five-input English scope and hardware, then prepares/reuses verified F16/Q4
files, builds CUDA llama-server for A100, and calls the existing generation
worker once per precision. The worker preserves the fixed messages, seed,
decoding, thinking-off setting, prompt-cache policy and full GPU-offload checks.
No AI judges or automatic retries run. A failed stage stops the pipeline while
preserving model files, manifests, logs and any answers already generated.

Using `1234567` as an example job ID, inspect:

```bash
export SAMESTORM_PILOT_JOB_ID=1234567
sacct -j "$SAMESTORM_PILOT_JOB_ID" --format=JobID,State,Elapsed,ExitCode
tail -n 60 "results/raw/pilot-${SAMESTORM_PILOT_JOB_ID}/preparation.log"
cat "results/raw/pilot-${SAMESTORM_PILOT_JOB_ID}/generation_bundle.json"
```

The bundle appears only after both generation runs succeed. It records hashes
and paths to:

- `results/raw/pilot-JOBID-generate-f16/answers.jsonl`: five main answers plus one repeat.
- `results/raw/pilot-JOBID-generate-q4_k_m/answers.jsonl`: the same five prompts plus one repeat.

Each child run preserves its own preparation receipt, generation manifest,
server log and GPU telemetry. The parent `model_bundle.json` describes the
preparation stage; `generation_bundle.json` describes the completed answer runs.
Next, prepare the blind English worksheet and obtain student ratings before
showing AI verdicts. Local tests use synthetic files and simulated subprocesses;
the actual CUDA build and generation must still be verified on LS6.

## English-first pilot on LS6

`scripts/jobs/prepare_pilot_model.sbatch` combines the pinned LFM3 download,
F16 conversion and Q4_K_M quantization into one CPU `development` allocation.
It does not prepare Qwen or the other quantization formats. The two-hour limit
is a ceiling, not a runtime estimate. This stage does not generate answers.
Use compute nodes for the conversion and quantization, following the
[LS6 guide](https://docs.tacc.utexas.edu/hpc/lonestar6/).

Commit and push the local changes first. In the existing LS6 login session:

```bash
source "$SCRATCH/samestorm2-env.sh"
cd "$SAMESTORM_REPO"
git pull --ff-only
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-model-prep/bin/python"
"$SAMESTORM_PYTHON" --version
command -v git
command -v cmake
command -v c++
```

If a build tool is missing, inspect `module spider gcc` and `module spider cmake`,
then load the available compiler/CMake modules before submission. Preserve this
working environments: use the separate conversion environment above, and do not
install all upstream llama.cpp requirements over it or the judge environment.
The job checks converter imports before
downloading weights; missing dependencies are recorded as a failure.

```bash
mkdir -p results/raw
sbatch -A CCR23028 scripts/jobs/prepare_pilot_model.sbatch
```

Use the numeric ID printed by `sbatch` below, replacing `1234567`:

```bash
export SAMESTORM_MODEL_JOB_ID=1234567
squeue -j "$SAMESTORM_MODEL_JOB_ID"
tail -n 60 "results/raw/pilot-model-${SAMESTORM_MODEL_JOB_ID}/preparation.log"
sacct -j "$SAMESTORM_MODEL_JOB_ID" --format=JobID,State,Elapsed,ExitCode
```

The detailed log appears after the job starts. The Slurm summary is
`results/raw/slurm-model-JOBID.out`. Conversion and quantization also have their
own child-run logs under `results/raw/pilot-model-JOBID-f16/` and `-q4/`.
After a successful job:

```bash
cat "results/raw/pilot-model-${SAMESTORM_MODEL_JOB_ID}/model_bundle.json"
```

The bundle identifies both GGUFs, their hashes and the corresponding preparation
manifests for the later generation job. New files are:

- `models/LFM3-1.7B/checkpoint/`: the pinned original checkpoint.
- `models/LFM3-1.7B/model-F16.gguf`: uncompressed reference.
- `models/LFM3-1.7B/model-Q4_K_M.gguf`: quantized directly from that reference.

Existing verified GGUFs are reused. Existing partial checkpoints, changed GGUFs
or files without matching receipts are preserved and cause the job to stop;
inspect the manifest and logs before any retry. The CPU quantizer is built in
`vendor/llama.cpp/build-prep`, leaving the separate inference build untouched.
The pinned converter includes
[LFM3 support](https://github.com/ggml-org/llama.cpp/blob/f7591a6a01f9273de03331732bdc0b39721168be/conversion/lfm3.py).

Next, build and verify the pinned CUDA `llama-server` runtime, then generate the
accepted English-first pilot: ten main answers and two repeats. Local workflow
tests use synthetic files; actual conversion, quantization, GPU fit and inference
remain unverified until the LS6 jobs run.
