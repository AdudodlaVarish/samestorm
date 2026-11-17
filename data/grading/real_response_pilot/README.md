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

Local checks currently find neither required target GGUF. On LS6, check for
existing artifacts/receipts before preparing anything again. Use the existing
pinned `scripts/prepare_model.py` download and F16-conversion steps. Quantization
now accepts `--precision Q4_K_M`, so this pilot need not prepare all five formats:

```bash
"$SAMESTORM_PYTHON" scripts/prepare_model.py quantize \
  --model-id LiquidAI/LFM3-1.7B --precision Q4_K_M --run-id pilot-q4-preparation-001
```

Conversion/quantization needs the verified reference/checkpoint and pinned
llama.cpp build. Execute preparation on suitable compute resources; no target
downloads, conversions or inference were performed by the local preflight.

## Generation after readiness checks

Regenerate with `scale_generate.py check --pilot` on LS6. Use that packet and the
completed pilot review manifest. Both generation jobs require matching successful
model-preparation receipts, verified GGUF hashes, full GPU offload and the pinned
runtime. Use job index 0 for F16 and 1 for Q4_K_M. The batch script accepts
`SAMESTORM_DEVELOPMENT_PILOT=1`; direct CLI generation requires `--pilot`.
Its existing hardware guard currently requires the gpu-a100 partition.

For the accepted English-first stage, add `--english-only` to preparation and
generation, and use `ENGLISH_FIRST_FREEZE.json`. Set `SAMESTORM_ENGLISH_ONLY=1`
alongside `SAMESTORM_DEVELOPMENT_PILOT=1` for the batch script. The multilingual
20-input review is complete but still has unresolved findings, so its generated
blank freeze template is not ready to approve.

After responses exist, prepare a blind English grading worksheet before showing
AI verdicts. Native answers, English translation evidence and separate numerical
extraction remain distinct. This pilot develops the graders; its results do not
make the full multilingual experiment or headline findings validated.
