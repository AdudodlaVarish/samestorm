# Multilingual judge development stress test v1

Research prototype. Follow local officials and call 911 in an emergency.

`cases.jsonl` has all 180 constructed answers: 90 safe/flawed pairs, 30 designed
safe and 30 designed harmful answers per Spanish, Vietnamese and Chinese. It keeps
152 original records and replaces 28 records with the 14 design-accepted r2 pairs.
The original 180-case draft, separate r2 records and 115-case baseline are preserved.
`selection_manifest.json` pins the parent/review inputs and assembled output hash.
Rebuild into a fresh directory with `scripts/prepare_grading_stress.py --output PATH`;
existing outputs are never overwritten.

All 90 pairs remain in the test, including those with unresolved evidence. Their
latest English pair reviews are 51 consistent, 31 discrepancy and 8 uncertain.
These are versioned pair reviews, not independent observations or action ratings.
No native-language wording is independently verified. Expected labels describe
AI-authored error design; this set is for development diagnostics, not human gold,
grader approval, a frozen final split or headline findings.

The nested `review` metadata records each original case/pair, selected version and
English evidence flag. Preparation withholds this metadata and expected labels
from the judge messages. Both judges receive only the question, constructed answer,
required actions and same-language official passages. Comparison preserves flags,
missing/failed cases and coverage; it never marks validation complete. The old
English student worksheet is not automatically reused with this case file.

## Local preparation and checks

Use fresh run IDs if any of these directories already exist:

```sh
.venv/bin/python scripts/validate_grading.py \
  --cases data/grading/multilingual_stress_v1/cases.jsonl \
  --run-id multilingual-stress-inputs-NEW

.venv/bin/python scripts/scale_judge.py check \
  --cases data/grading/multilingual_stress_v1/cases.jsonl \
  --input results/raw/multilingual-stress-inputs-NEW/judge_validation_tasks.jsonl \
  --judge-role primary --run-id multilingual-stress-primary-check-NEW
```

Repeat the worker check with `--judge-role secondary` and another fresh run ID.
These checks do not load a judge, verify compute hardware or produce verdicts.
The local no-verdict comparison is a pending-state receipt, not observed accuracy.

All three CLIs default to `data/grading/cases.jsonl` for the original baseline.
Custom `--cases` paths are repository-relative and must stay inside the repository.
Worker and comparison receipts record the selected path and file hash; mismatched
cases or changed inputs are rejected. Explicit `--student-review` remains available
for a matching English action sheet, with its original strict content checks.

## Next TACC job — prepared instructions, not submitted

Update the repository on LS6 with the code and this data directory first. Existing
judge weights and the pinned judge environment can be reused. Regenerate the packet
on LS6 rather than assuming ignored local `results/raw` files transferred with Git:

```sh
source "$SCRATCH/samestorm2-env.sh"
cd "$SAMESTORM_REPO"
export SAMESTORM_PYTHON="$SAMESTORM_REPO/.venv-judges/bin/python"
export SAMESTORM_CASES=data/grading/multilingual_stress_v1/cases.jsonl

"$SAMESTORM_PYTHON" scripts/validate_grading.py \
  --cases "$SAMESTORM_CASES" --run-id multilingual-stress-ls6-inputs-001

export SAMESTORM_TASKS="$PWD/results/raw/multilingual-stress-ls6-inputs-001/judge_validation_tasks.jsonl"
export SAMESTORM_PRIMARY_JUDGE_DIR="$PWD/models/judges/primary"
export SAMESTORM_SECONDARY_JUDGE_DIR="$PWD/models/judges/secondary"
export SAMESTORM_TASK_KIND=validation
export SAMESTORM_OFFSET=0
export SAMESTORM_LIMIT=0

sbatch -A CCR23028 -p gpu-a100,gpu-a100-dev --time=02:00:00 \
  scripts/jobs/judges.sbatch validate
```

This is one allocation: 180 primary verdicts, 180 secondary verdicts, then one
comparison. Both workers probe the allocated hardware/runtime before loading.
The two-hour request is a planning allowance based on the smaller completed runs;
180-case runtime has not been measured. Check current LS6 queue limits before
submission. Save the numeric job ID printed by TACC's submission wrapper.

Comparison uses the same `SAMESTORM_CASES`; new multilingual records have zero
matching English student action ratings by default. Keep original human-agreement
results in their separate baseline report. Unset `SAMESTORM_CASES` when returning
to response cross-grading, which has its own source/provenance checks.

## When actual model responses begin

After inspecting this development judge run, prepare a small actual-response dev
pilot with one target model, an F16 reference and one quantized format. Generating
fresh responses is part of testing the graders; perfect MT agreement is not a
prerequisite. The generation worker still requires recorded student input review
and exact frozen input hashes, verified target GGUF/preparation receipts, and the
pinned compute runtime. That input freeze is distinct from claiming the graders
are validated. This task creates no freeze or generation authorization record.

Then the student grades an English sample without seeing AI verdicts, while judges
grade the native answers and translation evidence remains separate. Resolve grader
problems on dev, retain failures and uncertain cases, and use fresh checks after
changes. The full model/precision campaign follows the pilot and remaining planned
validation/budget/input checks; headline eligibility stays false until satisfied.
