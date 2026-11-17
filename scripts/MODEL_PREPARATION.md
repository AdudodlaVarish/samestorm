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
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-judges/bin/python"
"$SAMESTORM_PYTHON" --version
command -v git
command -v cmake
command -v c++
```

If a build tool is missing, inspect `module spider gcc` and `module spider cmake`,
then load the available compiler/CMake modules before submission. Preserve this
working Python environment: do not install all upstream llama.cpp requirements
over its pinned judge dependencies. The job checks converter imports before
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
