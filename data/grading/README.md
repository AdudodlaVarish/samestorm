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
