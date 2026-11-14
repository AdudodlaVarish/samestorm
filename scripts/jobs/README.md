# Scale jobs on TACC

This migration supports
synthetic grading cases and verified response cross-grades. Compare synthetic
verdicts with `scripts/validate_judges.py`; see `data/grading/README.md`.

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

### Both validation judges in one allocation

Use `validate` to run both judges sequentially and then compare their verdicts
with the student worksheet. Each worker performs its hardware/runtime probe before
loading, so this route does not require a separately submitted probe job. Only one
judge model is loaded at a time; its process exits before the next starts.
Prepare the pinned environment, both checkpoint directories and the validation
packet before submitting. From the repository directory on LS6:

```sh
mkdir -p results/raw
export SAMESTORM_REPO="$PWD"
export SAMESTORM_PYTHON="$PWD/.venv-judges/bin/python"
export SAMESTORM_PRIMARY_JUDGE_DIR=/path/to/pinned/primary/checkpoint
export SAMESTORM_SECONDARY_JUDGE_DIR=/path/to/pinned/secondary/checkpoint
export SAMESTORM_TASKS="$PWD/results/raw/grading-scope-fix-20261113/judge_validation_tasks.jsonl"
export SAMESTORM_TASK_KIND=validation
export SAMESTORM_LIMIT=10
sbatch -A YOUR_ALLOCATION scripts/jobs/judges.sbatch validate
```

This example checks the same ten practice cases with each judge. Set
`SAMESTORM_LIMIT=0` for all cases; `SAMESTORM_OFFSET` defaults to zero.
The subset is a formatting/timing check, not complete validation. For either mode,
the 30-minute limit covers both judges, including checkpoint verification/loading
and comparison. Actual runtime is unknown; choose a measured wall-time request
before a full validation run. Override it with `sbatch --time=HH:MM:SS` if needed.

Outputs retain separate run directories:

- `results/raw/judge-JOBID-judge-primary/`
- `results/raw/judge-JOBID-judge-secondary/`
- `results/raw/judge-JOBID-comparison/`

Both judge runs must succeed before comparison starts. A failure stops later
stages and preserves existing receipts and partial outputs. The combined mode
accepts synthetic validation packets; response cross-grades still use the separate
role-specific commands above/below. All validation and headline flags stay pending.

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

## Response translation and grading cross-checks

`configs/crossgrades.json` preserves the original prospective pairs: Spanish and
Chinese use NLLB-1.3B plus MADLAD-3B; Vietnamese uses VinAI plus MADLAD-3B.
Only answers are translated. Native responses use official same-language keys;
English response translations use official English keys. No translated key is
created. Translation quality and grader accuracy remain unvalidated.

Prepare tasks from actual generation outputs, repeating `--answers` for more runs:

```sh
.venv/bin/python scripts/crossgrades.py prepare --run-id response-mt-inputs \
  --answers results/raw/GENERATION_RUN/answers.jsonl
```

Generation hashes, frozen review inputs, model IDs and example IDs must match.
Repeats and runtime failures are retained in `excluded_answers.jsonl` and excluded
from primary grading. Non-English successful primary responses get two fixed
translation tasks. The output includes a combined task list and one task file
per translator. Omitting `--answers` produces an empty pending preparation report;
it does not invent responses or translations.

Provision the official translator checkpoint directories at the exact revisions
in the configuration. Their upstream metadata and file hashes are saved locally;
no model cards or duplicate tokenizer/config snapshots are needed in Git. The
worker verifies actual checkpoint files, including original `.bin` weights,
before local-only loading with `weights_only=True` and remote code disabled.
Use the separate pinned scale environment from judge setup. Its actual runtime
remains untested on LS6. Run one translator per job after submission is authorized:

```sh
export SAMESTORM_TASKS="$PWD/results/raw/response-mt-inputs/translation_tasks-nllb13b.jsonl"
export SAMESTORM_TRANSLATOR_DIR=/path/to/pinned/nllb13b/checkpoint
sbatch -A YOUR_ALLOCATION scripts/jobs/translate.sbatch nllb13b
```

Repeat with the MADLAD and VinAI task files and their own checkpoint directories.
The worker runs on scale, translates every sentence separately, and preserves
all source segments, outputs, output token IDs and failures. Beam count, token
limits, seed and dtypes are fixed. Oversized input is rejected without truncation;
failed or output-limit translations stay unresolved. No favorable translator is
selected per response. Each 30-minute template uses the inherited three-GPU node;
total translation cost still needs measurement before a campaign is submitted.

Collect the actual translation run directories (repeat `--translation-run`):

```sh
.venv/bin/python scripts/crossgrades.py collect --run-id response-crossgrades \
  --prepared results/raw/response-mt-inputs \
  --translation-run results/raw/NLLB_RUN \
  --translation-run results/raw/MADLAD_RUN \
  --translation-run results/raw/VINAI_RUN
```

This verifies revisions, file/input/output hashes, task identities and complete
sentence coverage. `translation_coverage.jsonl` keeps missing/failed partners
visible; available translations are preserved without claiming pair agreement.
Native and English-translated packets go into `primary_judge_tasks.jsonl`.
The secondary file uses the original fixed-seed 20% stratified sample of source
answers and includes each selected answer's native and available translated
versions, so comparisons stay paired. A complete generation campaign would
select 442 native answers for the secondary judge.

Use the corresponding pinned judge checkpoint and role-specific packet file:

```sh
export SAMESTORM_TASK_KIND=crossgrade
export SAMESTORM_TASKS="$PWD/results/raw/response-crossgrades/primary_judge_tasks.jsonl"
sbatch -A YOUR_ALLOCATION scripts/jobs/judges.sbatch judge primary
```

Set `SAMESTORM_TASK_KIND=validation` for synthetic practice cases. Keep upstream
run directories available at their repository-relative paths on scale: the judge
worker re-verifies source responses and translations before accepting packets.
The target model identity and precision remain outside the judge messages.

After actual judge runs, compare native and translated verdicts:

```sh
.venv/bin/python scripts/crossgrades.py compare --run-id response-crossgrade-report \
  --collected results/raw/response-crossgrades \
  --judge-run results/raw/PRIMARY_JUDGE_RUN \
  --judge-run results/raw/SECONDARY_JUDGE_RUN
```

The report and `grade_comparisons.jsonl` show harmful-verdict and complete-action
agreement, disagreements and unresolved comparisons. Missing, failed or uncertain
judgments do not count as agreement. Matching verdicts can share translation or
judge mistakes; reports keep validation and headline eligibility false. There
are no automatic submissions, retries, new student ratings or benchmark edits.

## Tokenizer, throughput and runtime measurements

The migrated measurement tools use the selected LFM3-1.7B and Qwen3-4B revisions.
Old Qwen1.7/Llama measurements are not substituted. Check what is missing locally:

```sh
.venv/bin/python scripts/fertility.py check --run-id tokenizer-readiness-001
.venv/bin/python scripts/throughput.py check --run-id throughput-readiness-001
.venv/bin/python scripts/estimate_runtime.py --run-id runtime-readiness-001
```

These checks import no ML packages, run no inference and create no measurements.
Without supplied measurements, runtime estimates remain null. Fresh run IDs,
source/input hashes and failed-run receipts are retained.

`fertility.py measure` loads only a tokenizer from a local pinned checkpoint
directory. Model weights are not required. The tokenizer/config/template files
must match upstream hashes; use the prepared scale Python environment, or an
environment with the same pinned Transformers/tokenizers packages:

```sh
"$SAMESTORM_PYTHON" scripts/fertility.py measure --run-id lfm3-token-counts \
  --model-id LiquidAI/LFM3-1.7B --tokenizer-dir models/LFM3-1.7B/checkpoint
```

Repeat for Qwen/Qwen3-4B-Instruct-2507 and its own directory. A tokenizer-only
directory containing the pinned files also works. Results contain plain-question
tokens, full chat-prompt tokens with thinking disabled, character/whitespace-unit
counts and context-overflow checks for all 184 prompts. Each language is compared
with its matching English item IDs: Chinese uses its corresponding 40 English
questions. Whitespace units are not Vietnamese/Chinese linguistic word counts.
These are pilot-question counts, not a migrated FLORES experiment. HF chat counts
still need verification against the converted GGUF/llama.cpp prompt formatting.

For throughput, build `llama-bench` alongside the CUDA server at the pinned commit:

```sh
cmake --build vendor/llama.cpp/build --target llama-bench -j 4
export SAMESTORM_MODEL_MANIFEST=/path/to/matching-preparation/manifest.json
sbatch -A YOUR_ALLOCATION --array=0 scripts/jobs/measure.sbatch
```

Set the scale environment/repository variables as above. Each job selects one
current model/precision cell and verifies its preparation receipt, GGUF hash/type,
toolchain and allocated A100 hardware. It runs synthetic prefill512 and decode128
with five repetitions, four CPU threads, complete GPU layer offload and built-in
warm-up enabled. These are synthetic tokens, not benchmark answer generation.
No dataset freeze is performed or required for that synthetic workload.

The run retains raw `bench.jsonl`, `stderr.log`, GPU clock/temperature/power/memory
samples, a checked `measurement.json` and a manifest. Failed outputs remain
available. One-second telemetry can miss memory peaks. The synthetic 512/128
contexts do not prove memory fit at 4096 tokens, and clock/thermal stability is
not automatically confirmed. These are measurements on the recorded scale
hardware, not phone latency or energy measurements.

Estimate generation resource time after collecting real measurements:

```sh
.venv/bin/python scripts/estimate_runtime.py --run-id generation-budget-001 \
  --tokenization-run results/raw/LFM_TOKEN_COUNTS \
  --tokenization-run results/raw/QWEN_TOKEN_COUNTS \
  --throughput-run results/raw/ONE_THROUGHPUT_RUN
```

Repeat `--throughput-run` for each of the 12 cells. The estimator checks hashes,
current model revisions, input coverage, toolchain and recorded hardware. It sums
chat input tokens divided by measured prefill rate plus the 320-token response
cap divided by decode rate, including the 19 repeats per job. Allocated A100-hours
count all GPUs reserved by the node, regardless of utilization. Context-overflow
cases block a complete estimate; missing measurements never become zero cost.

The result is a provisional output-cap scenario. Synthetic rates may not scale
linearly; model loading, warm-up, HTTP overhead, failures and queue time are
excluded. Judge and translation costs remain separate unknowns, so this tool
does not claim a complete campaign budget. Measure those stages and obtain any
required approval before launching jobs expected to exceed 20 A100-hours.

## Paired performance analysis

`scripts/analyze_results.py` reads the collected cross-grade packet directory and
actual judge run directories. It re-verifies their generation, translation and
raw-verdict provenance before using native primary responses. It never runs a
model, opens the final test split or freezes the dataset.

```sh
.venv/bin/python scripts/analyze_results.py --run-id pilot-analysis-001 \
  --collected results/raw/RESPONSE_CROSSGRADES \
  --judge-run results/raw/PRIMARY_JUDGE_RUN \
  --judge-run results/raw/SECONDARY_JUDGE_RUN
```

Repeat `--judge-run` for nonoverlapping partial batches. Preserve upstream run
directories at their original repository-relative locations. Duplicate target
model/precision/example cohorts are rejected; the tool never chooses a favorable
rerun. Missing/failed judgments and target runtime failures remain visible. Run
without inputs to inspect the pending expected grid without inventing answers.

The two authorized error rates are unchanged:

- `answer_any_harmful`: harmful answers divided by answers with a known harmful
  verdict. Unknown answers are excluded from the denominator and reported.
- `critical_action_error`: erroneous critical actions divided by eligible critical
  actions. An answer with any uncertain critical action is unavailable for this
  rate. Counts are pooled over actions, not averaged over unequal answer sizes.

Both are reported; neither is silently selected as the sole headline metric.
Primary and sampled-secondary judge streams have separate files. Cell-rate files
show expected/generated/graded counts, missingness, refusals, wrong-language
outcomes and runtime failures. A missing grade is never a correct answer.

Paired analysis uses the unchanged formula:

```text
(E_language_quant - E_language_F16/BF16) -
(E_English_quant - E_English_F16/BF16)
```

Only complete four-cell scenario families contribute. Q8 is a quantized condition,
never the reference. Ten thousand fixed-seed scenario-family bootstrap samples
produce descriptive 95% intervals; all item/language/precision pairs stay together
within each sampled family. Coverage files list missing item IDs by family/cell,
including comparisons with no usable families. Chinese covers ten families;
the two unsupported families never enter its tax calculation. Null estimates
remain visible. Baseline and quantized language gaps are displayed alongside tax.
Small pilot family counts limit interpretation of intervals.

Outputs also include `mechanical_evidence.jsonl` and `determinism_checks.jsonl`.
Mechanical numerical/phone checks are partial evidence, kept outside full semantic
error-rate calculations; unvalidated non-English mechanical rules abstain.
Determinism checks compare primary and repeat answer text exactly, record missing
or failed partners, and never enter primary error rates. English translation
cross-grades remain in the separate migration-4 comparison reports.

All files go into a fresh ignored run directory with input/source snapshots and
hashes. Reports remain descriptive and headline-ineligible: student/existing-label/
judge/translation validation and the original mechanical-or-agreement requirement
must be resolved before headline findings. No validation flag is automatically
approved by this analysis command.
