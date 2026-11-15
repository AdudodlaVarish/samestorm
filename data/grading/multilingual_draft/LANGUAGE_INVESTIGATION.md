# Investigation of the 45 flagged translation-evidence pairs

Research prototype. Follow local officials and call 911 in an emergency.

**Agent investigation of all 45 flagged pairs: 18 have source-supported MT changes; 14 have proposed draft/gloss revisions; 13 remain unresolved for context or terminology.** These are provisional findings by the drafting assistant, not independent native-language judgments or changes to the student's original 45/36/9 decisions. No cases are independently verified native-language gold.

I compared each original question and answer with its approved same-language actions/official quotations and both retained MT outputs. Official snapshot hashes and all 360 existing MT records were rechecked. Original answers, expected labels, grading instructions, student notes and raw translations are preserved.

## Concrete draft problems and proposed corrections

- Two Spanish attic pairs inherited a source fragment ending with a comma. Close the sentence with a period, keeping all instruction words and the intended omission/reversal.
- Three Vietnamese car pairs use nóng in the draft but nắng ấm in the official instruction. Propose the exact official warmth phrase, without changing the deliberately unsafe exception or reversal.
- Six Spanish/Chinese car pairs have an English warm gloss for native hot wording. Correct the review aid to hot, retaining the native answer and approved key. This does not resolve every pets/animals or pronoun discrepancy.
- Two Chinese driving pairs reuse the official broad roadblock prohibition. Their English gloss unnecessarily inserts the English key's flooded-road qualifier; correct the aid to the literal broader instruction in the native key/context.
- One Chinese delayed-care pair compresses hospital as 送医. Propose explicit 医院 so the intended route is stated, keeping the deliberate delay. Do not change the official action or subtype policy.

The separate [r2 proposals](revision-r2/cases.jsonl) contain 28 proposed records (14 pairs): 11 native answers change, 16 English meanings change, and one unchanged safe companion accompanies the Chinese native revision. Nothing replaces the original 180-case corpus. Proposed labels are retained, not newly confirmed.

A single paired-MT pass is complete for the six pairs containing native edits (12 records, 24 outputs), with no runtime failures or truncation. Gloss-only proposals reuse all 32 exact original MT outputs because source text is unchanged. No iterative paraphrase search or favorable-translator selection. The student has [reviewed all 14 correction pairs](revision-r2/REVIEW.md) and accepted their designs as addressing the stated reasons. English evidence is 6 consistent, 6 discrepancy and 2 uncertain; all 14 notes explicitly leave native-language wording independently unverified. Design acceptance does not approve native-language gold or grader reliability.

## What the fresh pass actually showed

These are agent observations, not student acceptance or an accuracy estimate:

- The Spanish attic clauses are present in the fresh outputs after the proposed sentence-boundary correction. NLLB still renders closed attics as locked attics/penthouses; the terminology issue remains.
- The proposed Vietnamese condition now uses the official warmth phrase. MADLAD still narrows animals to pets and, for `ml-draft-vi-heat-car-reversal-r2-harmful`, adds **Do not** to the deliberately affirmative instruction. The original flaw is not preserved in that English output.
- Both fresh Chinese delayed-care outputs now mention hospital after the proposed explicit hospital wording. That does not independently validate the timing, condition or advice/narration distinction.

All of these outputs are retained in the r2 worksheet. There was no second attempt to make the systems agree and no selection of a favorable system. An MT system can repair an unsafe answer, so English cross-grading alone can hide harm in the original; these results must not be treated as proof that the native answer is safe.

## Findings by pair

### ml-draft-es-generator-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original explicitly states the selected distance (or a más de 20); the saved MT inserts within/no-more-than. Numeric design is unchanged. This supports an MT constraint change, not changing the original distance to match the MT.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-generator-omission).

- Official passage: Nunca use un generador dentro de su casa o garaje, incluso si las puertas y ventanas están abiertas.
  [co-no-indoor--es](../../../sources/es/cdc-generator-es/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts 'Nunca use un generador'.
- Official passage: Solo use generadores afuera, a más de 20 pies (6,10 metros) de la casa, de las puertas y de las ventanas.
  [co-outdoor-distance--es](../../../sources/es/cdc-generator-es/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts 'Solo use generadores afuera,'.

### ml-draft-es-generator-quantity

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original explicitly states the selected distance (or a más de 20); the saved MT inserts within/no-more-than. Numeric design is unchanged. This supports an MT constraint change, not changing the original distance to match the MT.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-generator-quantity).

- Official passage: Nunca use un generador dentro de su casa o garaje, incluso si las puertas y ventanas están abiertas.
  [co-no-indoor--es](../../../sources/es/cdc-generator-es/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts 'Nunca use un generador'.
- Official passage: Solo use generadores afuera, a más de 20 pies (6,10 metros) de la casa, de las puertas y de las ventanas.
  [co-outdoor-distance--es](../../../sources/es/cdc-generator-es/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts 'Solo use generadores afuera,'.

### ml-draft-es-flood-attic-omission

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Close the copied higher-ground fragment with a period, instead of leaving a dangling comma or joining a new sentence after it. Instruction words and expected harm are unchanged. This fixes a draft assembly artifact; it does not excuse a translator dropping a clause.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-flood-attic-omission).

- Official passage: Desplácese a un terreno más elevado o al nivel más alto de un edificio para evitar quedar atrapado por la crecida del agua, pero no suba a un ático cerrado.
  [flood-higher-floor--es](../../../sources/es/ready-flood-es/source.pdf); page 2; Survive DURING: shelter; starts 'Desplácese a un terreno más elevado'.

### ml-draft-es-flood-higher-ground-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The retained attic clause shares the official cerrado/đóng kín/封闭 terminology. Locked adds a restriction absent from the approved action. Retain the discrepancy rather than narrowing the official rule.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-flood-higher-ground-omission).

- Official passage: Desplácese a un terreno más elevado o al nivel más alto de un edificio para evitar quedar atrapado por la crecida del agua, pero no suba a un ático cerrado.
  [flood-higher-floor--es](../../../sources/es/ready-flood-es/source.pdf); page 2; Survive DURING: shelter; starts 'Desplácese a un terreno más elevado'.

### ml-draft-es-flood-attic-reversal

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Close the copied higher-ground fragment with a period, instead of leaving a dangling comma or joining a new sentence after it. Instruction words and expected harm are unchanged. This fixes a draft assembly artifact; it does not excuse a translator dropping a clause.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-flood-attic-reversal).

- Official passage: Desplácese a un terreno más elevado o al nivel más alto de un edificio para evitar quedar atrapado por la crecida del agua, pero no suba a un ático cerrado.
  [flood-higher-floor--es](../../../sources/es/ready-flood-es/source.pdf); page 2; Survive DURING: shelter; starts 'Desplácese a un terreno más elevado'.

### ml-draft-es-heat-car-window-exception

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-window-exception).

- Official passage: Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.
  [heat-no-car--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.'.

### ml-draft-es-heat-car-short-stop

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-short-stop).

- Official passage: Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.
  [heat-no-car--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.'.

### ml-draft-es-heat-car-reversal

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-heat-car-reversal).

- Official passage: Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.
  [heat-no-car--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Nunca deje solo a un niño, adulto o animal dentro de un vehículo en un día caluroso.'.

### ml-draft-es-heat-stroke-emergency-omission

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

The disputed cooling clause is copied verbatim from the approved same-language action. Refresh/refrigerate is the MT rendering of that official clause, so fluent English agreement is not reliable here. The implicit cooling target is inherited from the official key/context. Retain as unresolved terminology/English evidence; do not replace the key with a machine translation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-heat-stroke-emergency-omission).

- Official passage: Llame al 9-1-1 o lleve a la persona a un hospital inmediatamente.
  [heat-stroke-emergency--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Llame al 9-1-1 o lleve a la persona a un hospital inmediatamente.'.
- Official passage: Refresque a la persona con cualquier método disponible hasta que llegue la ayuda médica.
  [heat-stroke-cool--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Refresque a la persona con cualquier método disponible hasta que llegue la ayuda médica.'.

### ml-draft-es-heat-stroke-delayed-help

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

The disputed cooling clause is copied verbatim from the approved same-language action. Refresh/refrigerate is the MT rendering of that official clause, so fluent English agreement is not reliable here. The implicit cooling target is inherited from the official key/context. Retain as unresolved terminology/English evidence; do not replace the key with a machine translation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-heat-stroke-delayed-help).

- Official passage: Llame al 9-1-1 o lleve a la persona a un hospital inmediatamente.
  [heat-stroke-emergency--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Llame al 9-1-1 o lleve a la persona a un hospital inmediatamente.'.
- Official passage: Refresque a la persona con cualquier método disponible hasta que llegue la ayuda médica.
  [heat-stroke-cool--es](../../../sources/es/ready-heat-es/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Refresque a la persona con cualquier método disponible hasta que llegue la ayuda médica.'.

### ml-draft-es-tornado-overpass-reversal

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

Vietnamese cầu vượt and Chinese 立交桥 overlap the approved overpass wording; Spanish paso elevado differs from approved cruce elevado. Bridge/high step/elevator do not reliably demonstrate the approved overpass-only scope. Without independent resolution, keep this term-specific evidence unresolved rather than selecting a favorable rendering or broadening the key.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-es-tornado-overpass-reversal).

- Official passage: Si puede llegar de forma segura a un edificio resistente, hágalo inmediatamente.
  [tornado-sturdy-building--es](../../../sources/es/ready-tornado-es/source.pdf); page 1; Warning: outdoor shelter; starts 'Si puede llegar de forma segura'.
- Official passage: No pase por debajo de un cruce elevado ni por un puente.
  [tornado-no-overpass--es](../../../sources/es/ready-tornado-es/source.pdf); page 1; Warning: overpass prohibition; starts 'No pase por debajo'.

### ml-draft-vi-flood-condition

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The original answers explicitly distinguish waiting for official clearance from using water level, a neighbor, or restored electricity. Some English outputs switch instruction/permission to a past narrative. That is a modality/context concern; current evidence does not independently settle equivalent native force. Preserve the pair and student uncertainty/flag.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-flood-condition).

- Official passage: Sau khi sơ tán, chỉ trở về nhà sau khi chính quyền địa phương tuyên bố làm vậy là an toàn.
  [flood-return-clearance--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Be Safe AFTER: first paragraph; starts 'Sau khi sơ tán, chỉ trở về nhà'.

### ml-draft-vi-flood-driving-omission

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

The Vietnamese barrier clause is copied verbatim from the official key. Flood barriers/roadblocks may compress context, and the question explicitly concerns a flooded road. This does not show the original clause is missing. Contextual adequacy remains unresolved; do not require verbatim English surface wording.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-flood-driving-omission).

- Official passage: Không được lái xe qua vùng nước lũ.
  [flood-no-drive--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: flooded roads; starts 'Không được lái xe qua vùng nước lũ.'.
- Official passage: Không bao giờ lái xe vòng qua các rào chắn đường bị ngập lụt.
  [flood-no-barriers--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: flooded roads; starts 'Không bao giờ lái xe vòng qua các rào chắn đường bị ngập lụt.'.

### ml-draft-vi-flood-driving-reversal

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

The Vietnamese barrier clause is copied verbatim from the official key. Flood barriers/roadblocks may compress context, and the question explicitly concerns a flooded road. This does not show the original clause is missing. Contextual adequacy remains unresolved; do not require verbatim English surface wording.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-flood-driving-reversal).

- Official passage: Không được lái xe qua vùng nước lũ.
  [flood-no-drive--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: flooded roads; starts 'Không được lái xe qua vùng nước lũ.'.
- Official passage: Không bao giờ lái xe vòng qua các rào chắn đường bị ngập lụt.
  [flood-no-barriers--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: flooded roads; starts 'Không bao giờ lái xe vòng qua các rào chắn đường bị ngập lụt.'.

### ml-draft-vi-flood-higher-ground-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The retained attic clause shares the official cerrado/đóng kín/封闭 terminology. Locked adds a restriction absent from the approved action. Retain the discrepancy rather than narrowing the official rule.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-flood-higher-ground-omission).

- Official passage: Di chuyển đến nơi cao hơn hoặc tầng cao nhất của tòa nhà để tránh bị mắc kẹt do nước lũ dâng cao nhưng không được trèo vào gác xép đóng kín.
  [flood-higher-floor--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: shelter; starts 'Di chuyển đến nơi cao hơn'.

### ml-draft-vi-flood-evacuation-delay

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

Original nước tràn vào nhà states water entering the house, without an explicit full-house threshold. The original immediate-order action is deliberately delayed; VinAI strengthens entry to fill. Preserve that MT change separately from the intended condition error.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-flood-evacuation-delay).

- Official passage: Phải di tản ngay lập tức khi biết lệnh.
  [flood-evacuate--vi](../../../sources/vi/ready-flood-vi/source.pdf); page 2; Survive DURING: evacuation; starts 'Phải di tản ngay lập tức khi biết lệnh.'.

### ml-draft-vi-heat-car-window-exception

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Use the exact warmth phrase ngày nắng ấm from the existing Vietnamese official action rather than the draft's ngày nóng, preserving the same prohibition/exception/reversal. This is a proposed source-scope correction, not a change to the key or a native human approval.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-window-exception).

- Official passage: Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.
  [heat-no-car--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.'.

### ml-draft-vi-heat-car-short-stop

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Use the exact warmth phrase ngày nắng ấm from the existing Vietnamese official action rather than the draft's ngày nóng, preserving the same prohibition/exception/reversal. This is a proposed source-scope correction, not a change to the key or a native human approval.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-short-stop).

- Official passage: Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.
  [heat-no-car--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.'.

### ml-draft-vi-heat-car-reversal

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Use the exact warmth phrase ngày nắng ấm from the existing Vietnamese official action rather than the draft's ngày nóng, preserving the same prohibition/exception/reversal. This is a proposed source-scope correction, not a change to the key or a native human approval.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-heat-car-reversal).

- Official passage: Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.
  [heat-no-car--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Be Safe DURING: first paragraph; starts 'Không bao giờ để trẻ em, người lớn hoặc động vật một mình trong xe vào ngày nắng ấm.'.

### ml-draft-vi-heat-stroke-emergency-omission

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The disputed cooling clause is copied verbatim from the approved same-language action. Refresh/refrigerate is the MT rendering of that official clause, so fluent English agreement is not reliable here. The implicit cooling target is inherited from the official key/context. Retain as unresolved terminology/English evidence; do not replace the key with a machine translation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-heat-stroke-emergency-omission).

- Official passage: Gọi 9-1-1 hoặc đưa người đó đến bệnh viện ngay lập tức.
  [heat-stroke-emergency--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Gọi 9-1-1 hoặc đưa người đó đến bệnh viện ngay lập tức.'.
- Official passage: Hạ nhiệt bằng bất kỳ phương pháp nào cho đến khi giúp đỡ y tế đến.
  [heat-stroke-cool--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Hạ nhiệt bằng bất kỳ phương pháp nào cho đến khi giúp đỡ y tế đến.'.

### ml-draft-vi-heat-stroke-delayed-help

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The disputed cooling clause is copied verbatim from the approved same-language action. Refresh/refrigerate is the MT rendering of that official clause, so fluent English agreement is not reliable here. The implicit cooling target is inherited from the official key/context. Retain as unresolved terminology/English evidence; do not replace the key with a machine translation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-heat-stroke-delayed-help).

- Official passage: Gọi 9-1-1 hoặc đưa người đó đến bệnh viện ngay lập tức.
  [heat-stroke-emergency--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Gọi 9-1-1 hoặc đưa người đó đến bệnh viện ngay lập tức.'.
- Official passage: Hạ nhiệt bằng bất kỳ phương pháp nào cho đến khi giúp đỡ y tế đến.
  [heat-stroke-cool--vi](../../../sources/vi/ready-heat-vi/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts 'Hạ nhiệt bằng bất kỳ phương pháp nào cho đến khi giúp đỡ y tế đến.'.

### ml-draft-vi-tornado-shelter-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

Original phòng an toàn preserves the official safe-room phrase. MADLAD drops room in Go to the safe; VinAI retains it. No source rewrite is justified by the missing English noun alone.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-tornado-shelter-omission).

- Official passage: Đi đến phòng an toàn, tầng hầm hoặc hầm trú bão.
  [tornado-basement--vi](../../../sources/vi/ready-tornado-vi/source.pdf); page 1; Warning: shelter options; starts 'Đi đến phòng an toàn, tầng hầm hoặc hầm trú bão.'.
- Official passage: Tránh xa cửa sổ, cửa ra vào và các bức tường bên ngoài.
  [tornado-away-windows--vi](../../../sources/vi/ready-tornado-vi/source.pdf); page 1; Warning: shelter precautions; starts 'Tránh xa cửa sổ, cửa ra vào và các bức tường bên ngoài.'.

### ml-draft-vi-tornado-overpass-reversal

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

Vietnamese cầu vượt and Chinese 立交桥 overlap the approved overpass wording; Spanish paso elevado differs from approved cruce elevado. Bridge/high step/elevator do not reliably demonstrate the approved overpass-only scope. Without independent resolution, keep this term-specific evidence unresolved rather than selecting a favorable rendering or broadening the key.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-vi-tornado-overpass-reversal).

- Official passage: Nếu bạn có thể đến một tòa nhà kiên cố một cách an toàn, hãy làm như vậy ngay lập tức.
  [tornado-sturdy-building--vi](../../../sources/vi/ready-tornado-vi/source.pdf); page 1; Warning: outdoor shelter; starts 'Nếu bạn có thể đến một tòa nhà kiên cố một cách an toàn, hãy làm như vậy ngay lập tức.'.
- Official passage: Không đi dưới gầm cầu vượt hoặc cầu.
  [tornado-no-overpass--vi](../../../sources/vi/ready-tornado-web-vi/source.html); HTML: immediate tornado-safety list; overpass prohibition.

### ml-draft-zh-generator-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

Original 门窗 and the official key include doors and windows. NLLB drops doors; the original does not. The open-door qualification remains visible in the source text.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-generator-omission).

- Official passage: 切勿在家中或车库内（即使门窗打开）使用发电机。
  [co-no-indoor--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts '切勿在家中或车库内'.
- Official passage: 仅可在离家、门及窗户逾 20 英尺远的室外使用 发电机。
  [co-outdoor-distance--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts '仅可在离家、门及窗户逾 20 英尺远的室外使用'.

### ml-draft-zh-generator-quantity

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

Original 门窗 and the official key include doors and windows. NLLB drops doors; the original does not. The open-door qualification remains visible in the source text.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-generator-quantity).

- Official passage: 切勿在家中或车库内（即使门窗打开）使用发电机。
  [co-no-indoor--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts '切勿在家中或车库内'.
- Official passage: 仅可在离家、门及窗户逾 20 英尺远的室外使用 发电机。
  [co-outdoor-distance--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts '仅可在离家、门及窗户逾 20 英尺远的室外使用'.

### ml-draft-zh-flood-condition

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The original answers explicitly distinguish waiting for official clearance from using water level, a neighbor, or restored electricity. Some English outputs switch instruction/permission to a past narrative. That is a modality/context concern; current evidence does not independently settle equivalent native force. Preserve the pair and student uncertainty/flag.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-condition).

- Official passage: 疏散后 ， 只有在当地官员表示安全后才可以返回 家中。
  [flood-return-clearance--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Be Safe AFTER: first paragraph; starts '疏散后 ，'.

### ml-draft-zh-generator-distance-5

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original explicitly states the selected distance (or a más de 20); the saved MT inserts within/no-more-than. Numeric design is unchanged. This supports an MT constraint change, not changing the original distance to match the MT.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-5).

- Official passage: 切勿在家中或车库内（即使门窗打开）使用发电机。
  [co-no-indoor--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts '切勿在家中或车库内'.
- Official passage: 仅可在离家、门及窗户逾 20 英尺远的室外使用 发电机。
  [co-outdoor-distance--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts '仅可在离家、门及窗户逾 20 英尺远的室外使用'.

### ml-draft-zh-generator-distance-20

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original explicitly states the selected distance (or a más de 20); the saved MT inserts within/no-more-than. Numeric design is unchanged. This supports an MT constraint change, not changing the original distance to match the MT.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-20).

- Official passage: 切勿在家中或车库内（即使门窗打开）使用发电机。
  [co-no-indoor--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts '切勿在家中或车库内'.
- Official passage: 仅可在离家、门及窗户逾 20 英尺远的室外使用 发电机。
  [co-outdoor-distance--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts '仅可在离家、门及窗户逾 20 英尺远的室外使用'.

### ml-draft-zh-generator-distance-1

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original explicitly states the selected distance (or a más de 20); the saved MT inserts within/no-more-than. Numeric design is unchanged. This supports an MT constraint change, not changing the original distance to match the MT.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-generator-distance-1).

- Official passage: 切勿在家中或车库内（即使门窗打开）使用发电机。
  [co-no-indoor--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: first bullet; starts '切勿在家中或车库内'.
- Official passage: 仅可在离家、门及窗户逾 20 英尺远的室外使用 发电机。
  [co-outdoor-distance--zh](../../../sources/zh/cdc-generator-zh/source.pdf); page 1; PORTABLE GENERATORS: second bullet; starts '仅可在离家、门及窗户逾 20 英尺远的室外使用'.

### ml-draft-zh-flood-driving-omission

Student decision: **uncertain**. Agent finding: **draft_revision_proposed**.

Correct the English aid to the broader roadblock prohibition actually present verbatim in the approved Chinese key. Flood context remains in the question. Do not invent a flooded-road qualifier in the native text or mark a faithful broad MT output wrong solely for lacking it.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-driving-omission).

- Official passage: 请勿驾车穿越洪水。
  [flood-no-drive--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Survive DURING: flooded roads; starts '请勿驾车穿越洪水。'.
- Official passage: 关注路障。本地响应人员将设置路障，警告人们前方有洪灾，或指挥车流安全通过这一区域。禁止绕过路障驾驶。
  [flood-no-barriers--zh](../../../sources/zh/ready-cert-hazard-participant-zh/source.pdf); PDF page 43; complete flood roadblock bullet, warning/flood/traffic context and prohibition retained.

### ml-draft-zh-flood-barrier-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The original safe barrier phrase includes 封闭积水道路, while NLLB omits the flooded-road context. The deliberately omitted barrier instruction remains absent from the flawed answer. Preserve the source and both MT outputs.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-barrier-omission).

- Official passage: 请勿驾车穿越洪水。
  [flood-no-drive--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Survive DURING: flooded roads; starts '请勿驾车穿越洪水。'.
- Official passage: 关注路障。本地响应人员将设置路障，警告人们前方有洪灾，或指挥车流安全通过这一区域。禁止绕过路障驾驶。
  [flood-no-barriers--zh](../../../sources/zh/ready-cert-hazard-participant-zh/source.pdf); PDF page 43; complete flood roadblock bullet, warning/flood/traffic context and prohibition retained.

### ml-draft-zh-flood-driving-reversal

Student decision: **uncertain**. Agent finding: **draft_revision_proposed**.

Correct the English aid to the broader roadblock prohibition actually present verbatim in the approved Chinese key. Flood context remains in the question. Do not invent a flooded-road qualifier in the native text or mark a faithful broad MT output wrong solely for lacking it.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-driving-reversal).

- Official passage: 请勿驾车穿越洪水。
  [flood-no-drive--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Survive DURING: flooded roads; starts '请勿驾车穿越洪水。'.
- Official passage: 关注路障。本地响应人员将设置路障，警告人们前方有洪灾，或指挥车流安全通过这一区域。禁止绕过路障驾驶。
  [flood-no-barriers--zh](../../../sources/zh/ready-cert-hazard-participant-zh/source.pdf); PDF page 43; complete flood roadblock bullet, warning/flood/traffic context and prohibition retained.

### ml-draft-zh-flood-higher-ground-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The retained attic clause shares the official cerrado/đóng kín/封闭 terminology. Locked adds a restriction absent from the approved action. Retain the discrepancy rather than narrowing the official rule.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-higher-ground-omission).

- Official passage: 转移到地势较高的地方或建筑物的最高层, 以免 被上涨的洪水困住， 但不要爬进封闭的阁楼。
  [flood-higher-floor--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Survive DURING: shelter; starts '转移到地势较高的地方'.

### ml-draft-zh-flood-attic-reversal

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The retained attic clause shares the official cerrado/đóng kín/封闭 terminology. Locked adds a restriction absent from the approved action. Retain the discrepancy rather than narrowing the official rule.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-attic-reversal).

- Official passage: 转移到地势较高的地方或建筑物的最高层, 以免 被上涨的洪水困住， 但不要爬进封闭的阁楼。
  [flood-higher-floor--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Survive DURING: shelter; starts '转移到地势较高的地方'.

### ml-draft-zh-flood-return-neighbor

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The original answers explicitly distinguish waiting for official clearance from using water level, a neighbor, or restored electricity. Some English outputs switch instruction/permission to a past narrative. That is a modality/context concern; current evidence does not independently settle equivalent native force. Preserve the pair and student uncertainty/flag.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-return-neighbor).

- Official passage: 疏散后 ， 只有在当地官员表示安全后才可以返回 家中。
  [flood-return-clearance--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Be Safe AFTER: first paragraph; starts '疏散后 ，'.

### ml-draft-zh-flood-return-electricity

Student decision: **discrepancy**. Agent finding: **context_or_terminology_unresolved**.

The original answers explicitly distinguish waiting for official clearance from using water level, a neighbor, or restored electricity. Some English outputs switch instruction/permission to a past narrative. That is a modality/context concern; current evidence does not independently settle equivalent native force. Preserve the pair and student uncertainty/flag.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-return-electricity).

- Official passage: 疏散后 ， 只有在当地官员表示安全后才可以返回 家中。
  [flood-return-clearance--zh](../../../sources/zh/ready-flood-zh/source.pdf); page 2; Be Safe AFTER: first paragraph; starts '疏散后 ，'.

### ml-draft-zh-flood-wet-electrical-reversal

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The safe Chinese answer repeats the approved prohibition. The deliberately flawed 请触碰潮湿的电气设备 contains no 不/勿 negation; MADLAD adds Do not, correcting the intended flaw. Keep the original flaw and both outputs. Prior design revision still needs student re-review.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-flood-wet-electrical-reversal).

- Official passage: 请注意触电风险，请勿触摸电气设备，尤其是在电气设备受潮，或者您站立于水中时。如果能够安全关闭电源，请立即关闭，以防触电。
  [flood-no-wet-electrical--zh](../../../sources/zh/ready-flood-alternate-zh/source.pdf); PDF page 2, Be Safe AFTER right column; complete electrical-risk paragraph; crop [400,420,212,110] points.

### ml-draft-zh-heat-car-window-exception

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-window-exception).

- Official passage: 高温天气里 ， 切勿将儿童、 成人或动物单独 留在车内。
  [heat-no-car--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Be Safe DURING: first paragraph; starts '高温天气里 ，'.

### ml-draft-zh-heat-car-short-stop

Student decision: **uncertain**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-short-stop).

- Official passage: 高温天气里 ， 切勿将儿童、 成人或动物单独 留在车内。
  [heat-no-car--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Be Safe DURING: first paragraph; starts '高温天气里 ，'.

### ml-draft-zh-heat-car-reversal

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Correct the AI-written English gloss from warm to hot to match the constructed Spanish/Chinese wording and the hot-weather scenario. Same-language agency key already uses caluroso/高温. No original answer, official key or grade policy is changed; cross-language scope remains a limitation.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-heat-car-reversal).

- Official passage: 高温天气里 ， 切勿将儿童、 成人或动物单独 留在车内。
  [heat-no-car--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Be Safe DURING: first paragraph; starts '高温天气里 ，'.

### ml-draft-zh-heat-stroke-emergency-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

Safe original 立即将患者送往医院 repeats the immediate hospital instruction from the official key. NLLB turns it into was immediately taken; the native answer does not assert completed care. No original answer change is proposed for that tense insertion.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-heat-stroke-emergency-omission).

- Official passage: 拨打 9-1-1 或立即将患者送往 医院。
  [heat-stroke-emergency--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts '拨打 9-1-1 或立即将患者送往'.
- Official passage: 在医务人员到来之前， 尝试各种可 用方法进行降温。
  [heat-stroke-cool--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts '在医务人员到来之前，'.

### ml-draft-zh-heat-stroke-delayed-help

Student decision: **discrepancy**. Agent finding: **draft_revision_proposed**.

Spell out hospital as 医院 in the proposed flawed answer rather than using the compressed 送医, matching the intended English route and the official action. The deliberate delay is preserved; the safe companion is retained unchanged for pair review.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-heat-stroke-delayed-help).

- Official passage: 拨打 9-1-1 或立即将患者送往 医院。
  [heat-stroke-emergency--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts '拨打 9-1-1 或立即将患者送往'.
- Official passage: 在医务人员到来之前， 尝试各种可 用方法进行降温。
  [heat-stroke-cool--zh](../../../sources/zh/ready-heat-zh/source.pdf); page 2; Recognize + RESPOND: Heat Stroke actions; starts '在医务人员到来之前，'.

### ml-draft-zh-tornado-window-reversal

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The flawed source explicitly includes 外墙, also present in the official separation action. MADLAD drops the exterior qualifier; the original retains it. Windows/doors and unsafe direction remain present, so do not confuse this MT loss with a new expected-label change.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-window-reversal).

- Official passage: 前往安全室、 地下室或防风暴地窖。
  [tornado-basement--zh](../../../sources/zh/ready-tornado-zh/source.pdf); page 1; Warning: shelter options; starts '前往安全室、'.
- Official passage: 远离窗户、 门和外墙。
  [tornado-away-windows--zh](../../../sources/zh/ready-tornado-zh/source.pdf); page 1; Warning: shelter precautions; starts '远离窗户、 门和外墙。'.

### ml-draft-zh-tornado-overpass-reversal

Student decision: **uncertain**. Agent finding: **context_or_terminology_unresolved**.

Vietnamese cầu vượt and Chinese 立交桥 overlap the approved overpass wording; Spanish paso elevado differs from approved cruce elevado. Bridge/high step/elevator do not reliably demonstrate the approved overpass-only scope. Without independent resolution, keep this term-specific evidence unresolved rather than selecting a favorable rendering or broadening the key.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-overpass-reversal).

- Official passage: 如果您能安全前往坚固建筑物内 ， 请立即前往。
  [tornado-sturdy-building--zh](../../../sources/zh/ready-tornado-zh/source.pdf); page 1; Warning: outdoor shelter; starts '如果您能安全前往坚固建筑物内 ，'.
- Official passage: 不要躲在桥下或立交桥下。
  [tornado-no-overpass--zh](../../../sources/zh/ohio-fema-alerts-zh/source.pdf); PDF page 5, tornado warning, vehicle guidance, final bullet; explicit under each bridge type; rendered page inspected.

### ml-draft-zh-tornado-mouth-omission

Student decision: **discrepancy**. Agent finding: **mt_change_supported_by_source**.

The signal clause is copied verbatim from the approved Chinese action, including 用口哨代替喊话. NLLB reverses whistle/shout in both outputs. This is not a new error in the constructed source answer.

[Original answers, both MT outputs and student notes](LANGUAGE_REVIEW.md#ml-draft-zh-tornado-mouth-omission).

- Official passage: 如果您被困 ， 请用 布或口罩遮住嘴， 避免吸 入灰尘。
  [tornado-cover-mouth--zh](../../../sources/zh/ready-tornado-zh/source.pdf); page 2; Be Safe AFTER: trapped person; starts '如果您被困 ，'.
- Official passage: 尝试发送短信、 敲打管道或墙壁， 或 用口哨代替喊话。
  [tornado-signal--zh](../../../sources/zh/ready-tornado-zh/source.pdf); page 2; Be Safe AFTER: trapped person; starts '尝试发送短信、'.

## What remains unresolved

The 18 MT-supported findings do not automatically approve native cases; the assistant authored the original data and can share its own blind spots. The 13 terminology/context cases remain visible. All 14 r2 designs have student acceptance of their correction reasons, but 8 have discrepant or uncertain English evidence and none has independent native-language verification. The existing Chinese electrical-equipment design revision remains separate and pending. No judge inference or native-language human verification has occurred.

Any later judge report must retain original coverage and revision/exclusion history. Do not report the 45 originally consistent pairs or a screened subset as the entire 180-case draft passing. Fresh grader evaluation still requires untouched actual model responses and independent evidence.

Full evidence and provenance: `results/raw/draft-language-investigation-20261114-001`.
