# Scale jobs on TACC

Research prototype. Follow local officials and call 911 in an emergency.

Prepared only: no jobs have been submitted, no judge checkpoint has been downloaded,
and the LS6 environment and hardware have not been tested. This migration supports
the synthetic grading cases only. Compare recorded verdicts using
`scripts/validate_judges.py`; see `data/grading/README.md`.

`configs/judges.json` retains the original judge choices:

| Role | Model | Exact revision |
| --- | --- | --- |
| Primary | mistralai/Mistral-Small-24B-Instruct-2501 | 9527884be6e5616bdd54de542f9ae13384489724 |
| Secondary | Qwen/Qwen3-32B | 9216db5781bf21249d130ec9da846c4624c16137 |

Both use BF16, the pinned grading prompt, greedy decoding, a 4096-token context,
1024 output tokens, seed 20261107, the model chat template and thinking disabled.
The Qwen judge shares a family with the Qwen target; agreement can share correlated
errors and must not be treated as independent proof of correctness.

Check the configuration locally without importing ML packages or loading weights:

```sh
.venv/bin/python scripts/scale_judge.py check --run-id judge-setup-001
```

You can add `--input results/raw/YOUR_GRADING_CHECK/judge_validation_tasks.jsonl`
to validate prepared packets against the current keys, questions, synthetic cases
and pinned rubric. This check does not verify checkpoint availability, CUDA or
grader accuracy. All runs use fresh IDs and retain manifests and input snapshots.

## Separate scale environment

Use a separate environment on the allocated scale system. All judge dependency
pins are in `requirements-judges.lock.txt`. The laptop environment is unchanged.

```sh
python3 -m venv .venv-judges
.venv-judges/bin/python -m pip install --index-url https://download.pytorch.org/whl/cu128 'torch==2.11.0+cu128'
.venv-judges/bin/python -m pip install -r requirements-judges.lock.txt
```

These installation commands have not been run on LS6. Python/wheel/driver
compatibility and resolution of the inherited package list remain unverified.
The worker checks the recorded package versions and CUDA runtime, then records
the full installed package list. CUDA-wheel dependencies are not independently
hash-locked by these inherited files. Preserve installation failures rather than
silently substituting package versions.

Provision exact checkpoint snapshots on scale into separate local directories
using the revisions above. Preserve all recorded weight files and tokenizer/config
files. The worker verifies their upstream LFS SHA256 or Git blob hashes, including
the shard index, before loading; no automatic downloads or checkpoint fallback.
The primary pin includes both consolidated weights and sharded weights, so a full
snapshot requires substantial disk space. Weights stay outside Git.

## Prepared job template

The inherited hardware expectation is one `gpu-a100` node with three A100 GPUs,
each at least 37 GiB. This is historical preparation, not a verified allocation.
The worker checks Slurm partition, GPU count/name/memory, CUDA visibility and the
pinned runtime before loading either judge. CPU/disk offload is rejected. A failed
probe requires resolving the allocation/configuration; it does not enable a
laptop fallback. The job requests 30 minutes, at most 1.5 A100-hours at three GPUs;
larger campaigns still need timing estimates and any required approval.

After access and submission are authorized, set real paths and your real account.
Create `results/raw` before submission so Slurm can open its output file:

```sh
mkdir -p results/raw
export SAMESTORM_REPO="$PWD"
export SAMESTORM_PYTHON="$PWD/.venv-judges/bin/python"
sbatch -A YOUR_ALLOCATION scripts/jobs/judges.sbatch probe
```

After a successful probe, point `SAMESTORM_TASKS` at prepared validation packets and
`SAMESTORM_JUDGE_DIR` at the primary pinned snapshot. Set `SAMESTORM_LIMIT=10` for a
formatting check; zero means all selected cases. Run each role with its own snapshot:

```sh
sbatch -A YOUR_ALLOCATION scripts/jobs/judges.sbatch judge primary
sbatch -A YOUR_ALLOCATION scripts/jobs/judges.sbatch judge secondary
```

These commands are instructions only. The template does not submit itself.
Each run records the configuration, hardware/runtime details, checkpoint hashes,
raw verdicts and token IDs, checked grade records, failures and per-run input
snapshots. Context overflow is rejected without truncation. Invalid or truncated
verdicts are retained and make the run fail; partial outputs remain available.
Passing a setup check or finishing inference never sets judge validation complete.

## Answer generation

Prepare the current prompts and model/precision matrix locally:

```sh
.venv/bin/python scripts/scale_generate.py check --run-id generation-inputs-001
```

This writes `generation_packet.json`, `readiness.json`, and a pending
`review_template.json` into a fresh ignored run directory. It does not freeze the
dataset or run models. The packet has 184 prompts (48 English, 48 Spanish,
48 Vietnamese, 40 Chinese), 12 jobs and the same 19 repeat checks per job:
2,208 primary responses plus 228 repeats. Only dev items are accepted. Answer
keys are used for validation and review hashes; model messages contain only the
fixed English system prompt and the question in its language.

Generation requires a separate frozen review manifest containing the packet's
exact `input_sha256` map as `artifacts`, `frozen: true`, `approved_by: "student"`,
an actual `approved_at` record, and true flags for
`keys_and_alignment_evidence_reviewed` and `question_translations_reviewed`.
The generated template leaves all approval fields pending. Record approval only
after the required student evidence review; the template itself is no approval.
Keep a reviewed copy without overwriting old receipts. Changed questions, keys,
official source snapshots, model selections or protocol settings block execution
until a corresponding reviewed packet exists.

Use the model-preparation tools to create the GGUFs first. Each job needs the
matching successful conversion or quantization `manifest.json`, with its exact
model/revision/toolchain, output path, precision and GGUF hash. A conversion receipt
covers its reference job; a quantization receipt covers that model's five quantized
jobs. A single receipt cannot cover the whole 12-job matrix.

On scale, build a clean checkout at the commit in `configs/toolchain.json` with
CUDA enabled for A100. The CPU quantization build is not the inference build:

```sh
cmake -S vendor/llama.cpp -B vendor/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=80
cmake --build vendor/llama.cpp/build --target llama-server -j 4
```

The generation worker uses the GGUF reader from that pinned checkout. Its Python
dependencies are already present in the prepared scale judge environment; it can
reuse that environment without loading judge models. It records reader dependency
versions, the server hash, chat-template hash, hardware, decoding settings and
inputs in the run manifest. Hardware checks reuse the prepared LS6 expectation
in `configs/judges.json`. Actual builds and scale execution remain untested.

After execution is authorized and reviewed inputs, matching GGUFs and hardware
are ready, configure a single job first:

```sh
export SAMESTORM_PACKET="$PWD/results/raw/generation-inputs-001/generation_packet.json"
export SAMESTORM_REVIEW_MANIFEST=/path/to/recorded-approved-review.json
export SAMESTORM_MODEL_MANIFEST=/path/to/matching-preparation/manifest.json
sbatch -A YOUR_ALLOCATION --array=0 scripts/jobs/generate.sbatch
```

Set `SAMESTORM_REPO` and `SAMESTORM_PYTHON` as described above, and create
`results/raw` before submission. Select the actual matrix index and corresponding
model receipt. The template requests 30 minutes on the prepared three-GPU node;
full campaign timing/cost estimates remain pending. No submission is performed
by preparation or by this migration.

Each run preserves `answers.jsonl`, raw server responses, warm-up output,
`server.log`, temperature/clock/power/memory telemetry in `gpu.csv`, input copies
and a manifest. `repeat_index: 0` is a primary answer; `1` is a determinism check
and stays out of primary error rates. Truncated responses retain their text and
are flagged separately. Empty/malformed responses, unexpected thinking, missing
token/cache evidence and request failures are recorded as runtime failures.
Failures are never silently retried or discarded. Startup requires complete GPU
layer offload; server and telemetry processes are cleaned up on exit. These
elapsed times are run diagnostics; controlled throughput measurements are stage 5.
