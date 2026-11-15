# First multilingual judge stress results

Research prototype. Follow local officials and call 911 in an emergency.

Source: original LS6 runs `judge-3584082-judge-primary` and
`judge-3584209-judge-secondary`, imported locally on 2026-11-15 with their
`multilingual-stress-comparison-001` report and Slurm logs. Both processed 180
cases. All 125 recorded input/output hashes passed verification; offline replay
of all 360 verdicts reproduced the saved comparison and every case/action row.
The run case SHA256 matches this repository's 180-case input. See the
[case-level audit](VERDICT_AUDIT.md) for the diagnosed failure patterns.

These are provisional comparisons with AI-authored design labels, not native
human gold. The recorded development targets are at least 90% error detection
and at most 10% false alarms per language. Neither judge meets both targets in
any language under the current conservative counting.

| Judge | Language | Harm detected /30 designed harmful | False flags /30 designed safe | Failed harmful /safe | False-alarm upper bound |
| --- | --- | ---: | ---: | ---: | ---: |
| Primary | Spanish | 29 (96.7%) | 5 | 0 /1 | 20.0% |
| Secondary | Spanish | 28 (93.3%) | 4 | 0 /0 | 13.3% |
| Primary | Vietnamese | 24 (80.0%) | 1 | 3 /7 | 26.7% |
| Secondary | Vietnamese | 26 (86.7%) | 1 | 2 /4 | 16.7% |
| Primary | Chinese | 26 (86.7%) | 3 | 2 /1 | 13.3% |
| Secondary | Chinese | 26 (86.7%) | 4 | 1 /4 | 26.7% |

Detection lower bounds count failed harmful cases as undetected; false-alarm
upper bounds count failed safe cases as possible false alarms. These are
missing-data bounds, not statistical confidence intervals. The upper bounds are
not the number of observed false flags. Even without quote failures, Spanish
already has 5/30 primary and 4/30 secondary false flags against the proposed labels.

Primary has 14 rejected verdicts, secondary 11, all reported as failed exact
nonempty evidence-quote checks. That is 25 verdict records, not necessarily 25
different examples. Valid output structure does not establish correct grading.
Retain these failures; do not silently edit evidence quotes or retry only rejected
cases to improve the result.

The judges agree on 263/271 comparable action positions (97.0%). The case/key
input has 306 action positions; 35 do not enter that agreement calculation.
Comparable coverage is 88.6%. This is agreement between the judges, not agreement
with gold: they can agree with each other while disagreeing with our intended
labels, which may themselves be wrong or ambiguous. There are no student native
action ratings. Earlier English human-agreement results stay in their own baseline.

## Completed investigation and next step

The source-based audit found repeated distance-inequality mistakes, changed
quotes, missed affirmative unsafe advice, and overlap between condition errors
and reversals. Four flood-omission disagreements also need a clearer rule about
whether one instruction satisfies two related checklist items. The original
results above remain unchanged. Specify a prospective grader revision addressing
these findings, then test it on fresh development examples; this set has now
informed development and cannot serve as an untouched evaluation.

Target-model preparation and a small fresh-response development pilot can still
be prepared in parallel. This diagnostic result does not authorize treating these
judges as reliable ground truth for the full multilingual experiment. Perfect MT
agreement is not a requirement for collecting development responses; input review,
verified model artifacts and the generation runtime remain required.
