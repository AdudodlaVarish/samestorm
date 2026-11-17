# Pilot input review recorded — 2026-11-16

Research prototype. Follow local officials and call 911 in an emergency.

The student completed all 40 decisions in [INPUT_REVIEW.md](INPUT_REVIEW.md).
The submitted file, decisions and notes are preserved verbatim. Compared with
the prepared packet, only the two decision fields and Notes changed; the
questions, quotations and saved translation evidence match the reviewed originals.
All original input/evidence hashes still match the preparation manifest.

| Review | Consistent | Discrepancy | Uncertain |
| --- | ---: | ---: | ---: |
| Questions | 15 | 4 | 1 |
| Keys | 15 | 3 | 2 |

Seven prompt sections contain at least one concern. The other 13 have consistent
question and key decisions. This is English-evidence review, not independent
native-language verification or model-response grading.

## Findings requiring investigation

| Prompt | Question | Key | Student's concern |
| --- | --- | --- | --- |
| flood-001-base:vi | consistent | uncertain | Both outputs say flooded roadblocks; the scope of the barrier prohibition is unclear. |
| heat-001-base:es | discrepancy | discrepancy | Son versus child; hot day versus the English source's warm day. |
| heat-001-base:vi | consistent | discrepancy | Both key outputs add sunny to the warm-day condition. |
| heat-001-base:zh | discrepancy | discrepancy | Kids versus child; hot weather versus warm day. |
| tornado-001-base:es | discrepancy | consistent | Have to stay versus should stay changes the advice/obligation phrasing. |
| tornado-001-base:vi | discrepancy | uncertain | Cyclone versus tornado warning; garbled heading in one key translation. |
| winter-003-base:es | uncertain | consistent | Abandon him leaves the car referent unclear in one output. |

The student accepted the longer Chinese flood passage evidence: its final
sentence explicitly prohibits going around roadblocks, within flood/traffic
context. That note is preserved with its consistent decision.

These observations identify issues in the English evidence, not confirmed defects
in every native question or official translation. Follow-up must distinguish
machine-translation artifacts, official-source differences and changes that
actually affect the required action in the stated scenario. For example, all
current hot-car questions explicitly say hot and sunny, which may make the
broader warm-day source difference inapplicable within this narrow scenario;
that does not erase the student's recorded discrepancy or establish general
source equivalence. No question, source text, key or reviewer decision was edited
to resolve these issues in this step. No additional review is requested now.

## English-first collection stage

All five English sections have consistent question and key decisions. An
English-only first stage lets the project collect actual model responses while
the multilingual evidence is investigated:

- Five unchanged English base questions: generator, flooded driving, hot car,
  tornado shelter and stranded car in winter.
- The same pinned LiquidAI/LFM3-1.7B in F16 and Q4_K_M.
- Ten main responses and two repeats, with the existing fixed decoding settings.

[ENGLISH_FIRST_FREEZE.json](ENGLISH_FIRST_FREEZE.json) binds those five reviewed
IDs, the current input hashes, submitted review hash and saved evidence hash.
The earlier request to proceed with a small response pilot and the completed
English review supply the authorization/approval record. No new student judgment
is invented. Translation review is explicitly not applicable to this English-only
stage; native-input approval remains false. The guard rejects using this freeze
for the 20-input multilingual pilot or full matrix.

Prepare on LS6 with `scale_generate.py check --pilot --english-only --run-id ID`.
Generation uses both flags and this freeze record, plus the matching verified
F16/Q4 model-preparation receipts. The batch equivalent sets
`SAMESTORM_DEVELOPMENT_PILOT=1` and `SAMESTORM_ENGLISH_ONLY=1`.
The local packet is `results/raw/fresh-response-english-first-20261116-001/`.
Both required GGUFs are still missing locally; remote artifact readiness remains
to be checked. No model generation or submission was performed here.

This first stage develops the response/grading workflow. It cannot estimate a
multilingual language tax or establish a precision effect from five scenarios.
The complete 20-input pilot remains unfrozen, and the original full experiment,
v1/v2 results, all flags and native-verification limitations are preserved.

Audit receipt: `results/raw/real-response-pilot-review-audit-20261116-001/`.
It contains the submitted review, initial preparation manifest, all decisions,
counts and the recording script.
