# Grading validation

Research prototype. Follow local officials and call 911 in an emergency.

`cases.jsonl` contains 115 controlled examples: 92 faithful-action examples across
English, Spanish, Vietnamese and Chinese, plus 23 English examples containing
critical omissions, a supporting omission, reversals, wrong quantities or wrong
conditions. Expected annotations and labels describe the synthetic injection
design. They are not independent human judgments or model-generated responses.

`student_review.csv` contains 92 shuffled English action rows, with rating fields
blank. Only the student fills them in. Review the question, response and required
action; enter `correct`, `missing`, `reversal`, `quantity_error`, `condition_error`
or `uncertain` in `status`. Quote exact response text in `evidence_quote` for a
positive finding; a missing action must have an empty quote. Record uncertainty
in `comment`. Do not copy the designed labels as student judgments. The approved
plan calls for at least 60 usable student judgments.

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
configured scale hardware; English student ratings, two-judge checks, existing
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
non-English harmful cases, translation cross-grades and confirmed acceptance
thresholds remain outstanding. No model inference or jobs run from this command.

The 2026-11-13 scope fix preserves approved `grading_scope` and
`numeric_identifier` metadata in judge inputs and updates the pinned prompt to
apply them. Regenerated inputs are in
`results/raw/grading-scope-fix-20261113/judge_validation_tasks.jsonl`; all 115
passed the local setup check in `results/raw/judge-scope-fix-20261113/`.
Older prepared packets must be regenerated with a fresh run ID before use.
Original packets and receipts remain preserved. Actual judge adherence is untested.
