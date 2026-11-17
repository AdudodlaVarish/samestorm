# Small actual-response development pilot

Research prototype. Follow local officials and call 911 in an emergency.

This pilot selects five existing development scenarios across four recorded
hazard groups: generator use, flood driving, hot car, tornado shelter and a
stranded car in winter. It keeps all four languages: 20 prompts. One pinned
target, LiquidAI/LFM3-1.7B, runs in F16 and Q4_K_M, producing 40 main responses
and 8 fixed-seed repeats. The full 184-prompt matrix remains the default.

Preparation is implemented as `scripts/scale_generate.py check --pilot --run-id ID`.
Its packet retains the original question/system messages, model revision and
decoding settings. It only selects a documented subset of scenarios/jobs; it does
not drop the generator case or change a source requirement. No original key or
expected label has been edited.

## Your input review

Use [INPUT_REVIEW.md](INPUT_REVIEW.md), generated from the pilot packet. For each
of the 20 prompt sections, replace both pending decisions with `consistent`,
`discrepancy` or `uncertain`, and explain concerns in Notes. Existing question
back-translations and two saved official-passage translation systems are shown
where applicable; matching-segment versus whole-passage context is explicitly
identified. These are English review aids, not translated keys or native gold.
The student completed all 40 decisions on 2026-11-16: questions 15 consistent,
4 discrepancy, 1 uncertain; keys 15 consistent, 3 discrepancy, 2 uncertain.
See the [recorded review summary](REVIEW_SUMMARY.md). Seven sections retain
concerns; all five English sections are consistent. The instructions here remain
available for a later amendment; the submitted review has been preserved.

For the question decision, compare the English original with both saved English
back-translations: do they preserve the situation and what is being asked? For
the key decision, compare both saved English passage translations with the
official English action, including prohibitions, conditions and numbers. Mark
consistent only when the relevant meanings agree; mark discrepancy for a meaning
change and uncertain when you cannot tell. In English sections, check the
question and required actions directly against their official English sources.
You are reviewing inputs here; there are no new model answers to grade yet.

The operating rule in `../samestorm/AGENTS.md` says: “Do not freeze until all keys
and alignment evidence receive student review.” The complete multilingual pilot
remains unfrozen while the seven sections are investigated. The five accepted
English inputs have a separately scoped [freeze record](ENGLISH_FIRST_FREEZE.json).
Use `--pilot --english-only` for that first collection stage: ten main answers and
two repeats. Translation review is explicitly not applicable to its English-only
scope. That freeze cannot authorize the multilingual pilot or full matrix.

## Model and runtime preparation

To prepare the models and generate the English-first answers in one allocation,
use [`scripts/jobs/pilot.sbatch`](../../../scripts/jobs/pilot.sbatch) and the
[combined-job instructions](../../../scripts/MODEL_PREPARATION.md#prepare-and-generate-in-one-a100-job).
It verifies the reviewed English scope, prepares F16/Q4, builds CUDA llama-server,
then runs both precisions sequentially: ten main answers and two repeats. It does
not run judges. GCC, CMake and the CUDA compiler must be available when submitted.

Use the [single-job LS6 model preparation instructions](../../../scripts/MODEL_PREPARATION.md#english-first-pilot-on-ls6).
The CPU batch job fetches the pinned checkpoint and llama.cpp revision, converts
F16, builds a CPU quantizer, and prepares only Q4_K_M. It reuses existing artifacts
only when their successful preparation receipts and hashes match. It preserves
unverified or partial files and stops for inspection. Weights remain ignored.
No actual model preparation or inference was performed by the local checks.

## Generation after readiness checks

After preparation, build and verify the pinned CUDA inference runtime; the CPU
quantizer does not provide it. Regenerate with `scale_generate.py check --pilot` on LS6. Use that packet and the
completed pilot review manifest. Both generation jobs require matching successful
model-preparation receipts, verified GGUF hashes, full GPU offload and the pinned
runtime. Use job index 0 for F16 and 1 for Q4_K_M. The batch script accepts
`SAMESTORM_DEVELOPMENT_PILOT=1`; direct CLI generation requires `--pilot`.
The development pilot accepts gpu-a100 or gpu-a100-dev with the same three-A100
hardware checks; full-matrix generation and measurement retain gpu-a100.

For the accepted English-first stage, add `--english-only` to preparation and
generation, and use `ENGLISH_FIRST_FREEZE.json`. Set `SAMESTORM_ENGLISH_ONLY=1`
alongside `SAMESTORM_DEVELOPMENT_PILOT=1` for the batch script. The multilingual
20-input review is complete but still has unresolved findings, so its generated
blank freeze template is not ready to approve.

After responses exist, prepare a blind English grading worksheet before showing
AI verdicts. Native answers, English translation evidence and separate numerical
extraction remain distinct. This pilot develops the graders; its results do not
make the full multilingual experiment or headline findings validated.

## Blind worksheet after the combined job succeeds

The exporter is ready while generation runs; it cannot create a real worksheet
until the completed answer files are available. Once the new script has been
committed/pushed and pulled on LS6, use your actual combined job ID:

```bash
"$SAMESTORM_PYTHON" scripts/prepare_pilot_review.py \
  --pilot-run "results/raw/pilot-${SAMESTORM_PILOT_JOB_ID}" \
  --run-id "pilot-review-${SAMESTORM_PILOT_JOB_ID}-001"
```

This lightweight export makes no model calls and needs no additional allocation.
It verifies the complete parent bundle, both generation-run hashes, frozen input
hashes, exact prompt/repeat coverage and successful model/scope records. It then
reuses the existing generated-answer reader, excludes the two fixed-seed repeats,
shuffles all ten main answers, and assigns anonymous IDs. Identical answers stay
separate; nothing is selected for being interesting or incorrect.

Only copy/open the resulting `review/` folder for grading. It contains:

- `student_review.csv`: 16 blank required-action ratings, with exact questions,
  answers, action text, conditions, numerical requirements and grading scope.
- `answer_outcomes.csv`: 10 blank refusal/language outcome rows.
- `README.md`: short label definitions, exact-quotation rules and instructions.

Make a working copy before editing, preserving the original export and hashes.
Fill only the rating, evidence and comment fields specified in its instructions.
The parent folder contains `private_mapping.json`, linking anonymous IDs to
source runs/model versions; leave it closed while grading. Model metadata and
AI-expected labels are absent from the review files. Runtime failures are checked
from generation records rather than guessed from answers.

Return both completed CSV files before looking at judge verdicts. These are new
actual-response ratings, separate from the old synthetic fixture worksheet and
its 90 usable ratings. Sixteen action ratings from five English scenarios cannot
establish full judge validation or multilingual precision effects. Original
answers, keys and previous student ratings are not edited by this export.
