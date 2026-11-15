# Follow-up from the student back-translation review

Research prototype. Follow local officials and call 911 in an emergency.

**All 90 pairs reviewed: 45 consistent English evidence, 36 discrepancy, 9 uncertain.** These are student-reported open-label English evidence decisions. They are not 180 independent answer grades, a translation-accuracy estimate, native-language gold or evidence that either AI judge failed.

The agent has now [investigated all 45 flagged pairs](LANGUAGE_INVESTIGATION.md):
18 have source-supported MT changes, 14 have proposed draft/explanation revisions,
and 13 remain unresolved. Review the separate [14-pair r2 proposal worksheet](revision-r2/REVIEW.md)
for the proposed changes and their fresh or explicitly reused MT evidence. These
findings do not replace the student decisions recorded here.

The r2 review is now complete: all 14 designs accepted for their correction
reasons; English evidence 6 consistent, 6 discrepancy and 2 uncertain. Those
subset reviews do not add 14 new independent pairs to the original 90 or establish
native-language verification. Original decisions below are preserved.

| Language | Consistent English evidence | Discrepancy | Uncertain | Flagged for follow-up |
| --- | ---: | ---: | ---: | ---: |
| es | 19 | 9 | 2 | 11 |
| vi | 18 | 9 | 3 | 12 |
| zh | 8 | 18 | 4 | 22 |

The 45 consistent pairs cover 90 constructed answers: 19 pairs in Spanish, 18 in Vietnamese and 8 in Chinese. They remain candidates with consistent English evidence, not automatically accepted examples. The original one-pair design revision still awaits re-review. All 180 answers, their proposed labels, the two raw MT outputs and original student notes are unchanged.

## Next work

1. Investigate the 45 flagged pairs using the official same-language passage, question, original answer and both saved translations. Determine whether the issue is in the constructed answer, the AI-written English gloss, the MT output, or unresolved source alignment. Do not assume a flagged back-translation proves the original answer is wrong.

2. Prioritize lost/reversed instructions and changed numerical constraints. Then inspect terminology, scope and tense differences in context. Exact English wording is not required when meaning is preserved. The categories below are agent triage suggestions, not new student decisions or human gold.

3. Keep raw translations intact. Any correction belongs in a separately identified draft revision with its reason and fresh evidence; do not edit the old MT output, select only the favorable translator, or repeatedly rephrase until the two systems agree. Unresolved cases stay visible.

4. Resolve the intended design and evidence before connecting this draft to the judge runs. Keep all 90 pairs and their exclusion/revision history in reports. Using only the 45 consistent pairs changes coverage and can bias conclusions; report that explicitly rather than implying all 180 passed. Later grader evaluation still needs untouched actual-model answers and separate evidence.

The original 115-case baseline and English student action ratings remain unchanged. No new model inference, TACC jobs, grader tuning, case acceptance or final-test evaluation occurred.

## Follow-up groups

| Issue group | Flagged pairs |
| --- | ---: |
| Distance constraints | 5 |
| Instruction coverage or polarity | 5 |
| Closed/enclosed versus locked attic | 4 |
| Warm/hot and animals/pets scope | 9 |
| Cooling terminology | 4 |
| Overpass terminology | 3 |
| Return-home tense and permission | 4 |
| Barrier context | 5 |
| Evacuation condition | 1 |
| Doors/windows scope | 2 |
| Emergency-help route or tense | 2 |
| Exterior-wall qualifier | 1 |

## Distance constraints

Check the original distance wording against the official inequality. Retain changed comparisons such as within/no-more-than as MT discrepancies; do not replace the raw output.

- [ml-draft-es-generator-omission](LANGUAGE_REVIEW.md#ml-draft-es-generator-omission) — **discrepancy**.
- [ml-draft-es-generator-quantity](LANGUAGE_REVIEW.md#ml-draft-es-generator-quantity) — **discrepancy**.
- [ml-draft-zh-generator-distance-5](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-5) — **discrepancy**.
- [ml-draft-zh-generator-distance-20](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-20) — **discrepancy**.
- [ml-draft-zh-generator-distance-1](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-1) — **discrepancy**.

## Instruction coverage or polarity

Inspect the complete original instruction and both MT outputs for a lost action, changed target, added negation or reversed recommendation. Preserve the deliberately flawed action.

- [ml-draft-es-flood-attic-omission](LANGUAGE_REVIEW.md#ml-draft-es-flood-attic-omission) — **discrepancy**.
- [ml-draft-es-flood-attic-reversal](LANGUAGE_REVIEW.md#ml-draft-es-flood-attic-reversal) — **discrepancy**.
- [ml-draft-vi-tornado-shelter-omission](LANGUAGE_REVIEW.md#ml-draft-vi-tornado-shelter-omission) — **discrepancy**.
- [ml-draft-zh-flood-wet-electrical-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-flood-wet-electrical-reversal) — **discrepancy**.
- [ml-draft-zh-tornado-mouth-omission](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-mouth-omission) — **discrepancy**.

## Closed/enclosed versus locked attic

Check the same-language source and answer meaning; locked is narrower than enclosed. Do not settle this by choosing whichever translator matches the expected label.

- [ml-draft-es-flood-higher-ground-omission](LANGUAGE_REVIEW.md#ml-draft-es-flood-higher-ground-omission) — **discrepancy**.
- [ml-draft-vi-flood-higher-ground-omission](LANGUAGE_REVIEW.md#ml-draft-vi-flood-higher-ground-omission) — **discrepancy**.
- [ml-draft-zh-flood-higher-ground-omission](LANGUAGE_REVIEW.md#ml-draft-zh-flood-higher-ground-omission) — **discrepancy**.
- [ml-draft-zh-flood-attic-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-flood-attic-reversal) — **discrepancy**.

## Warm/hot and animals/pets scope

Revisit the official same-language key and hot-weather question before treating the AI-written English gloss as authoritative. Determine whether the difference affects this scenario; do not change the approved key to force English lexical agreement.

- [ml-draft-es-heat-car-window-exception](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-window-exception) — **discrepancy**.
- [ml-draft-es-heat-car-short-stop](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-short-stop) — **discrepancy**.
- [ml-draft-es-heat-car-reversal](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-reversal) — **discrepancy**.
- [ml-draft-vi-heat-car-window-exception](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-window-exception) — **discrepancy**.
- [ml-draft-vi-heat-car-short-stop](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-short-stop) — **discrepancy**.
- [ml-draft-vi-heat-car-reversal](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-reversal) — **discrepancy**.
- [ml-draft-zh-heat-car-window-exception](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-window-exception) — **discrepancy**.
- [ml-draft-zh-heat-car-short-stop](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-short-stop) — **uncertain**.
- [ml-draft-zh-heat-car-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-reversal) — **discrepancy**.

## Cooling terminology

Check what the original cooling instruction says. English refresh/refrigerate may be MT wording errors; a fluent rewrite by the drafting assistant would not be independent evidence.

- [ml-draft-es-heat-stroke-emergency-omission](LANGUAGE_REVIEW.md#ml-draft-es-heat-stroke-emergency-omission) — **uncertain**.
- [ml-draft-es-heat-stroke-delayed-help](LANGUAGE_REVIEW.md#ml-draft-es-heat-stroke-delayed-help) — **uncertain**.
- [ml-draft-vi-heat-stroke-emergency-omission](LANGUAGE_REVIEW.md#ml-draft-vi-heat-stroke-emergency-omission) — **discrepancy**.
- [ml-draft-vi-heat-stroke-delayed-help](LANGUAGE_REVIEW.md#ml-draft-vi-heat-stroke-delayed-help) — **discrepancy**.

## Overpass terminology

Use the approved overpass-only grading scope and official same-language source. Broad bridge or unrelated elevator/high-step translations leave the specific evidence unresolved.

- [ml-draft-es-tornado-overpass-reversal](LANGUAGE_REVIEW.md#ml-draft-es-tornado-overpass-reversal) — **discrepancy**.
- [ml-draft-vi-tornado-overpass-reversal](LANGUAGE_REVIEW.md#ml-draft-vi-tornado-overpass-reversal) — **uncertain**.
- [ml-draft-zh-tornado-overpass-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-overpass-reversal) — **uncertain**.

## Return-home tense and permission

Compare the full context for advice/permission versus a past event and whether official clearance is still required. Surface tense differences alone need contextual adjudication.

- [ml-draft-vi-flood-condition](LANGUAGE_REVIEW.md#ml-draft-vi-flood-condition) — **discrepancy**.
- [ml-draft-zh-flood-condition](LANGUAGE_REVIEW.md#ml-draft-zh-flood-condition) — **discrepancy**.
- [ml-draft-zh-flood-return-neighbor](LANGUAGE_REVIEW.md#ml-draft-zh-flood-return-neighbor) — **discrepancy**.
- [ml-draft-zh-flood-return-electricity](LANGUAGE_REVIEW.md#ml-draft-zh-flood-return-electricity) — **discrepancy**.

## Barrier context

Read the entire flooded-road question with the source action. Decide whether roadblock/flood-barrier wording preserves the needed meaning in context; do not require verbatim English wording.

- [ml-draft-vi-flood-driving-omission](LANGUAGE_REVIEW.md#ml-draft-vi-flood-driving-omission) — **uncertain**.
- [ml-draft-vi-flood-driving-reversal](LANGUAGE_REVIEW.md#ml-draft-vi-flood-driving-reversal) — **uncertain**.
- [ml-draft-zh-flood-driving-omission](LANGUAGE_REVIEW.md#ml-draft-zh-flood-driving-omission) — **uncertain**.
- [ml-draft-zh-flood-barrier-omission](LANGUAGE_REVIEW.md#ml-draft-zh-flood-barrier-omission) — **discrepancy**.
- [ml-draft-zh-flood-driving-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-flood-driving-reversal) — **uncertain**.

## Evacuation condition

Check the difference between water entering and filling the house; preserve the immediate-order versus delayed-evacuation distinction.

- [ml-draft-vi-flood-evacuation-delay](LANGUAGE_REVIEW.md#ml-draft-vi-flood-evacuation-delay) — **discrepancy**.

## Doors/windows scope

Compare both open-door and open-window conditions with the official same-language instruction. Establish whether a condition was lost in MT or the source answer.

- [ml-draft-zh-generator-omission](LANGUAGE_REVIEW.md#ml-draft-zh-generator-omission) — **discrepancy**.
- [ml-draft-zh-generator-quantity](LANGUAGE_REVIEW.md#ml-draft-zh-generator-quantity) — **discrepancy**.

## Emergency-help route or tense

Inspect the immediate hospital-care instruction and the deliberate delay. Determine whether the route or timing changed in MT rather than silently replacing it with the intended English text.

- [ml-draft-zh-heat-stroke-emergency-omission](LANGUAGE_REVIEW.md#ml-draft-zh-heat-stroke-emergency-omission) — **discrepancy**.
- [ml-draft-zh-heat-stroke-delayed-help](LANGUAGE_REVIEW.md#ml-draft-zh-heat-stroke-delayed-help) — **discrepancy**.

## Exterior-wall qualifier

Check whether losing exterior changes the intended instruction in the given scenario; retain the original and both translations while unresolved.

- [ml-draft-zh-tornado-window-reversal](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-window-reversal) — **discrepancy**.

## Review provenance

Reviewed Markdown preserved without edits. A pre-sync package and the exact originally generated worksheets are retained in `results/raw/draft-language-review-audit-20261114-001`. The original blank worksheets were recovered from commit `e62320f18671c621ccfebd9e2fe2a72a8837bbf8` and verified against the original MT evidence receipt.

The CSV mirrors each pair decision and note onto its two answer rows, using explicit `student_pair_backtranslation_decision` and `student_pair_notes` columns. Those repeated cells are one pair-level review, not two answer-level ratings. The Markdown remains the source of the student decisions.
