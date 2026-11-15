# Grading validation

Research prototype. Follow local officials and call 911 in an emergency.

The completed 115-case baseline remains unchanged. The separate
[multilingual draft](multilingual_draft/REVIEW.md) contains 180 AI-authored answers,
with 30 proposed acceptable and 30 deliberately flawed answers in each of Spanish,
Vietnamese and Chinese. It covers 10 existing development families; related cases
are not independent trials. Its labels are proposed test expectations; language
and design issues remain unresolved. It is not yet connected to the job scripts
and must not be pooled with baseline results. The first 24 draft cases remain unchanged; that earlier
revision is also preserved locally under
`results/raw/multilingual-draft-v1-preserved-20261114/`.

Both back-translations are now available for all 180 draft answers in
[the English evidence worksheet](multilingual_draft/LANGUAGE_REVIEW.md), with a
[CSV alternative](multilingual_draft/LANGUAGE_REVIEW.csv). All 360 outputs were
generated locally using the existing pinned MT systems. The student reviewed all
90 pairs: 45 consistent English evidence, 36 discrepancy and 9 uncertain. See the
[follow-up list](multilingual_draft/LANGUAGE_REVIEW_FOLLOWUP.md) for all 45 flagged
pairs. The CSV mirrors pair-level decisions on both answer rows, using explicitly
named pair-review columns; this is not 180 separate answer ratings. No pair is
accepted automatically, and English consistency does not establish native-language
accuracy.

The [source investigation](multilingual_draft/LANGUAGE_INVESTIGATION.md) covers all
45 flagged pairs. A separate [r2 worksheet](multilingual_draft/revision-r2/REVIEW.md)
contains 14 proposed correction pairs, with 24 fresh and 32 explicitly reused MT
outputs. The original 180 answers and student decisions remain unchanged. Several
MT discrepancies persist, including a translator adding a prohibition to a
deliberately unsafe answer. The student accepted all 14 designs as addressing
their correction reasons. English evidence is 6 consistent, 6 discrepancy and
2 uncertain; all native-language wording remains independently unverified.

The [assembled development stress input](multilingual_stress_v1/README.md) retains
all 180 answers, including 28 r2 replacements, with all unresolved flags visible.
Preparation, judging and comparison now accept the same repository-relative
`--cases` path; the combined job takes it from `SAMESTORM_CASES`. The default remains
the original 115-case baseline. The stress directory documents local checks and
the combined TACC command. The [first stress results](multilingual_stress_v1/RESULTS.md)
have been reproduced from the imported original runs; neither judge meets both
recorded per-language targets under conservative counting. The completed
[case-level audit](multilingual_stress_v1/VERDICT_AUDIT.md) separates quote failures,
distance and polarity mistakes, subtype overlap and ambiguous omission designs.
The [prospective v2 prompt](JUDGE_V2.md) addresses these findings through an
explicit version selection; v1 and its results are preserved. The v2 packet is
prepared and checked locally, but its development GPU rerun has not been submitted.

Student design decisions are recorded for all 90 pairs: 89 need language review
and one needs revision. The Chinese electrical-equipment pair has a proposed
wording revision awaiting student re-review. The subsequent English evidence
review is complete; native-language accuracy and design acceptance remain
unresolved. These decisions do not add blind human action ratings.

`cases.jsonl` contains 115 controlled examples: 92 faithful-action examples across
English, Spanish, Vietnamese and Chinese, plus 23 English examples containing
critical omissions, a supporting omission, reversals, wrong quantities or wrong
conditions. Expected annotations and labels describe the synthetic injection
design. They are not independent human judgments or model-generated responses.

## validation thresholds

| Check | Threshold |
| --- | --- |
| Critical-error recall | At least 90% |
| False-alarm rate | At most 10% |
| Agreement with student action judgments | At least 85% |

Report counts, coverage and uncertainty alongside percentages. Recall and false
alarms must be checked per language; English-only harmful cases cannot establish
non-English recall. Student agreement covers the student's English action ratings.
This records student acceptance;

The 27 numerical cases remain in `tests/fixtures/numeric_cases.jsonl`.
`configs/prompts/judge_v1.txt` contains the judge's grading instructions.
This prompt is separate from the instructions used to generate benchmark answers.

Run the software checks and prepare judge inputs locally:

```sh
.venv/bin/python scripts/validate_grading.py --run-id grading-check-001
.venv/bin/python -m unittest discover -s tests
```

Use a fresh run ID each time. Outputs go into `results/raw/<run-id>/`:

- `annotation_checks.jsonl`: designed action annotations mapped to error labels.
- `numeric_checks.jsonl`: numerical checker results, including failures.
- `judge_validation_tasks.jsonl`: grading messages with same-language official
  passages, without expected annotations/labels or target model/precision metadata.
- `report.json`: software results and remaining validation gaps.
- `manifest.json` and `inputs/`: input hashes, source snapshots and run status.

Existing runs and the student review sheet are never overwritten. Failed runs
retain their inputs and available diagnostics. The command does not load a model,
submit jobs, freeze the dataset or mark grading as validated. Judges still require
configured scale hardware; comparisons with English student ratings, two-judge checks, existing
human-label checks and translation cross-grades remain pending. Harmful injected
examples are English only. Forbidden-claim rules are not populated.

## Compare recorded judge verdicts

After the scale runs produce verdicts, compare them with the designed cases and
your independently completed English worksheet:

```sh
.venv/bin/python scripts/validate_judges.py --run-id judge-comparison-001 \
  --primary results/raw/PRIMARY_RUN/judgments.jsonl \
  --secondary results/raw/SECONDARY_RUN/judgments.jsonl
```

Use `--student-review PATH` for a separate copy of your worksheet. Grade before
looking at expected labels or judge verdicts. Blank rows remain unrated; uncertain
rows are recorded but excluded from the 60 usable student judgments.

Each judge output needs its original adjacent `manifest.json`. The command checks
the output hash, pinned model/role/prompt and matching case/question/key inputs.
It rechecks raw verdicts and exact evidence quotes, rather than trusting saved
grade fields. Partial failed runs can contribute their valid records; missing,
failed and uncertain cases stay visible.

The fresh run directory contains `judge_validation_report.json`, per-case and
per-action comparison JSONL files, input copies and a manifest. The report shows
provisional synthetic error-detection/false-alarm bounds, judge agreement and
agreement with your ratings. Missing/failed/unresolved cases stay in the original
bound denominators. Student agreement uses all usable student ratings; judge
agreement uses comparable actions and reports their count. Inspect coverage with
every agreement value.

You can omit either judge path to inspect what is still pending. With no verdicts,
`results_present` is false; worst-case bounds from entirely missing data are not
observed judge performance. Neither 60 student ratings nor high agreement alone
sets `validated` or `headline_eligible` true. Existing human-label checks,
non-English harmful cases, translation cross-grades and recorded PI confirmation
of the student-accepted thresholds remain outstanding. No model inference or jobs
run from this command.

The 2026-11-13 scope fix preserves approved `grading_scope` and
`numeric_identifier` metadata in judge inputs and updates the pinned prompt to
apply them. Regenerated inputs are in
`results/raw/grading-scope-fix-20261113/judge_validation_tasks.jsonl`; all 115
passed the local setup check in `results/raw/judge-scope-fix-20261113/`.
Older prepared packets must be regenerated with a fresh run ID before use.
Original packets and receipts remain preserved. Actual judge adherence is untested.

## Recheck saved format failures without inference

The verdict parser accepts a plain JSON object or one complete outer Markdown
fence (with a `json` tag or no tag). It still rejects extra prose, multiple JSON
objects, incomplete fences, truncation, invalid action IDs and fabricated evidence.
Raw outputs are retained exactly as generated.

Use this explicit option to recheck complete raw verdicts from an earlier failed
run under the updated parser:

```sh
"$SAMESTORM_PYTHON" scripts/validate_judges.py \
  --run-id judge-format-recheck-001 \
  --primary results/raw/FAILED_PRIMARY_RUN/judgments.jsonl \
  --recheck-failed-verdicts
```

This checks the original run/input/output hashes and all verdict rules, then writes
a fresh comparison receipt. It does not run models or alter the original failed
manifest or verdict file. Recovery requires an explicitly false generation-limit
flag and no recorded runtime failure. The report records recovered counts and
original run statuses; per-case details retain the original rejection reason.
An absent secondary remains absent, and untested cases remain in the report's
missing/abstention counts. Rechecking formatting does not repair original
tokenization, establish semantic accuracy or complete grading validation.
