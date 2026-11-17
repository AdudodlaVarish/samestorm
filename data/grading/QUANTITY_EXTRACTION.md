# Separate distance extraction and arithmetic

Research prototype. Follow local officials and call 911 in an emergency.

This development path addresses the repeated inequality errors in the
[v2 audit](multilingual_stress_v1/VERDICT_AUDIT_V2.md). The AI copies a relevant
numerical expression and identifies whether the answer affirmatively recommends
it in context. Code parses that literal expression and compares its value with
the source inequality using Decimal arithmetic and exact unit conversion.

The original v1/v2 judge decisions and headline metrics remain separate. A
quantity result is conditional on the AI's semantic extraction being correct;
neither quote validation nor correct arithmetic proves relevance, polarity or
native-language accuracy. No extraction model has been run for this protocol yet.

Local preflight on 2026-11-16 passed all 154 software tests, including fresh
arithmetic values/thresholds, exact quotes, ambiguous forms, extraction provenance,
generated-answer inputs and pilot review-scope isolation. Prepared all 36 existing
distance cases and checked both role configurations. Current local receipts use
`quantity-extraction-{inputs,primary-check,secondary-check,pending}-20261116-002`.
The pending report contains no model verdicts. Both original v1/v2 comparisons
were replayed unchanged, with all 255 original recorded hashes preserved.

## Scope and evidence contract

The separately pinned `quantity_v1` prompt uses the same two judge models and
existing runtime/decoding pins. It returns exactly one record per supported
distance action, with `state`, an exact answer clause and an exact quantity quote.
It does not produce a safe/harmful grade or normalize a number itself.

- An affirmative, unambiguous literal quantity can yield supported or violated
  **for the numerical requirement only**. The source threshold comes from the
  official key; it is not hardcoded to 20.
- Missing/uncertain extraction yields needs_review, never an inferred omission.
- Changed quotes, duplicate IDs, malformed JSON and truncation fail validation.
- Multiple quantities, fractions, ranges, ambiguous separators and unsupported
  literal forms require review; the code does not choose a favorable number.
- The literal vocabulary covers common feet/metre forms in the included
  languages and a limited set of comparator phrases. Unrecognized expressions
  abstain. This is not a general multilingual quantity-understanding claim.
- Only physical distance with a strict source lower bound is supported. Medical
  time conditions, telephone identifiers and all other actions retain their
  existing handling. The original English-only mechanical checker is unchanged
  apart from sharing its existing strict-bound arithmetic helper.

The output has `semantic_extraction_validated: false`, `semantic_complete: false`
and `headline_eligible: false`. It never overwrites a saved judge grade.

## First development job on LS6

Regenerate the packet after migrating the committed changes. All 36 applicable
distance cases are selected from the 180-case stress set, including omissions;
selection is by key capability, not by whether a previous verdict passed.
This is development regression, not fresh evaluation or independent gold.

```bash
source "$SCRATCH/samestorm2-env.sh"
cd "$SAMESTORM_REPO"
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-judges/bin/python"
export SAMESTORM_CASES=data/grading/multilingual_stress_v1/cases.jsonl

"$SAMESTORM_PYTHON" scripts/validate_quantities.py prepare \
  --cases "$SAMESTORM_CASES" --run-id quantity-inputs-ls6-001

export SAMESTORM_TASKS="$PWD/results/raw/quantity-inputs-ls6-001/quantity_tasks.jsonl"
export SAMESTORM_PRIMARY_JUDGE_DIR="$PWD/models/judges/primary"
export SAMESTORM_SECONDARY_JUDGE_DIR="$PWD/models/judges/secondary"
export SAMESTORM_OFFSET=0
export SAMESTORM_LIMIT=0
unset SAMESTORM_REFERENCE_ANSWERS SAMESTORM_QUANTIZED_ANSWERS

"$SAMESTORM_PYTHON" scripts/scale_judge.py check \
  --task-kind quantity --cases "$SAMESTORM_CASES" \
  --input "$SAMESTORM_TASKS" --judge-role primary --run-id quantity-primary-check-ls6-001

"$SAMESTORM_PYTHON" scripts/scale_judge.py check \
  --task-kind quantity --cases "$SAMESTORM_CASES" \
  --input "$SAMESTORM_TASKS" --judge-role secondary --run-id quantity-secondary-check-ls6-001

sbatch -A CCR23028 -p gpu-a100,gpu-a100-dev --time=02:00:00 \
  scripts/jobs/judges.sbatch quantity
```

The quantity mode selects its own prompt, attempts both roles, then writes
`results/raw/quantity-JOBID-comparison/quantity_extraction_report.json`. If a
worker rejects outputs, failures remain in the report and the job exits nonzero.
A provenance/hardware/input failure may prevent a complete report. Use fresh run
IDs if a path already exists. The two-hour request is a maximum planning allowance;
actual runtime is unmeasured.

Manual reports use `scripts/validate_quantities.py report --cases ... --primary ...
--secondary ... --run-id ...`. This revalidates original raw extractions and keeps
failed/missing cases visible. It performs no inference or retrospective repair.
Do not pass extraction outputs to `validate_judges.py`; their manifest stage and
prompt are deliberately distinct from full semantic judgments.

## Fresh actual-response evidence

The [small response pilot](real_response_pilot/README.md) prepares actual target
responses once input review, model artifacts and runtime checks are satisfied.
Its English responses should be student-graded before seeing judge results.
Fresh arithmetic unit tests with other thresholds test software only; they do
not substitute for running this extractor on actual responses.

After generation, prepare quantity tasks from verified answer files:

```bash
"$SAMESTORM_PYTHON" scripts/validate_quantities.py prepare \
  --answers results/raw/YOUR_F16_RUN/answers.jsonl \
  --answers results/raw/YOUR_Q4_RUN/answers.jsonl \
  --run-id quantity-actual-inputs-001
```

These tasks are marked `synthetic: false`; no expected labels are invented.
The pipeline checks generation receipts, reviewed input hashes, original answer
hashes, identities and repeats/failures using the existing provenance reader.
Only primary nonfailed responses with supported distance actions are included.

For `scale_judge.py`, use `--task-kind quantity` and repeat `--answer-file` for
the same source runs. For batch quantity mode, set `SAMESTORM_TASKS` to the new
packet, `SAMESTORM_REFERENCE_ANSWERS`/`SAMESTORM_QUANTIZED_ANSWERS` to those two
answer files, and unset `SAMESTORM_CASES`. The batch passes both sources to the
workers and report. A manual actual-response report repeats the same `--answers`
arguments instead of `--cases`. Mixing constructed-case and generated-answer
sources is rejected. Full response cross-grading remains on its existing v1
path; this extraction evidence supplements it without replacing decisions.
