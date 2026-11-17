# Multilingual judge v2 development results — 2026-11-16

Research prototype. Follow local officials and call 911 in an emergency.

Source: original LS6 runs for primary 3584671 and secondary 3584941, imported on
2026-11-16 with `multilingual-stress-v2-comparison-001` and both Slurm logs. Both
processed all 180 cases using `judge_v2`. All 130 recorded hashes passed, all 360
verdicts were revalidated, and the complete report and every detail row reproduced
exactly. Case SHA def78c35... and prompt SHA31bafb2b... match local files. The
[paired case-level audit](VERDICT_AUDIT_V2.md) records the remaining causes and
v1/v2 decision changes. The earlier student-report summary is retained separately.

V2 reduces rejected outputs, but its grading results are mixed. Only secondary
Vietnamese meets both recorded point targets (detection >=90%, false-alarm bound
<=10%). This is a development result against AI-authored design expectations,
not independent native human gold or validation of that language/judge choice.
The stress audit informed v2, so this reused set cannot be its untouched evaluation.

| Judge | Language | Detection lower bound v1 -> v2 | False-alarm upper bound v1 -> v2 | Failed verdicts v1 -> v2 |
| --- | --- | ---: | ---: | ---: |
| Primary | Spanish | 96.7% -> 90.0% | 20.0% -> 16.7% | 1 -> 1 |
| Primary | Vietnamese | 80.0% -> 90.0% | 26.7% -> 23.3% | 10 -> 3 |
| Primary | Chinese | 86.7% -> 96.7% | 13.3% -> 13.3% | 3 -> 0 |
| Secondary | Spanish | 93.3% -> 76.7% | 13.3% -> 16.7% | 0 -> 7 |
| Secondary | Vietnamese | 86.7% -> 93.3% | 16.7% -> 6.7% | 6 -> 2 |
| Secondary | Chinese | 86.7% -> 96.7% | 26.7% -> 16.7% | 5 -> 0 |

Each language has 30 designed harmful and 30 designed safe cases. Failed harmful
verdicts count as undetected in the detection lower bound; failed safe verdicts
count as possible false alarms in the upper bound. These are missing-data bounds,
not confidence intervals. Differences combine semantic decisions and output
validation coverage, and the cases are correlated within scenario families.

## What improved and what remains

Rejected verdicts decreased from 25/360 to 13/360: primary 14 -> 4, secondary
11 -> 9. V2 primary failures are four quote errors. Secondary has five malformed
JSON outputs, two action-cardinality errors and two quote errors. Passing output
validation does not establish a correct decision. Preserve all original failures.

Primary detects 27/30 Spanish, 27/30 Vietnamese and 29/30 Chinese designed harmful
answers. However, it explicitly flags 5/30 Spanish, 5/30 Vietnamese and 4/30 Chinese
designed-safe answers. Those observed false flags already exceed the 10% target
in every language, independently of failed-output penalties. Fixing quotes alone
cannot resolve these disagreements with the design labels.

Secondary Spanish detects 23/30, misses one, and has six failed harmful verdicts.
Its low detection bound therefore includes substantial output failures; it is
not evidence of seven valid decisions calling harmful answers safe. It also
explicitly flags four designed-safe Spanish answers. Secondary Chinese has no
invalid outputs but still flags five designed-safe answers, showing that output
formatting is not its only remaining problem. Native fixture ambiguity remains
possible until individual answers are checked against the saved official sources.

Judge agreement is 274/285 comparable actions (96.1%), with 285/306 positions
covered (93.1%). V1 had 263/271 agreement (97.0%) and 88.6% coverage. These are
different comparable subsets; shared decisions do not establish correctness.
No native student action ratings were supplied. Earlier blind English ratings
remain in the separate original baseline. All native wording remains independently
unverified, and validated/headline_eligible remain false.

## Completed audit and next development decision

The completed audit attributes 23 of 24 observed false flags to the distance
inequality and one to a Chinese tornado negation/scope error. Five valid misses
still accept exactly 20 feet; three concern overlapping flood omissions. Every
valid condition-error judgment still uses reversal. Across records valid in both
versions, six move toward the design label and three away. The full audit keeps
coverage changes separate from those decision changes and accounts for all 13
failures. No original result is repaired or rescored.

Next develop a concrete quantity-handling proposal that separates semantic
extraction from arithmetic, retaining original judge and mechanical evidence
separately and testing any extension on fresh examples. No multilingual
mechanical extension or new metric has been implemented by this audit.

Target artifact/input preparation for a small fresh-response development pilot
can proceed alongside that audit. Full multilingual scoring still needs the
planned validation. Selecting a judge by its best score here would itself be
development tuning and would need fresh evaluation evidence.
