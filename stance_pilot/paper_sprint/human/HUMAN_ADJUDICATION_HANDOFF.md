# Human adjudication handoff (18 packets + FR1/FR2)

**Status: NOT OBTAINED.** This package prepares and tracks delivery; it enters no labels. Until a real annotator-2 independently submits, all 18 gold stay **PROVISIONAL/PENDING**. AI self-review never counts.

## Delivery set
- G3-C.1: 8 blind packets (P01-P08); G3-A: 10 (P01-P10) = 18 total.
- blind seed: (see plan); 9 files/packet; rubric labels ACCEPT/REJECT/NEEDS_REVIEW.
- third senior human arbitrates any ACCEPT<->REJECT disagreement (never an LLM or the pipeline author).
- priority order requested: 8 G3-C.1 first, then 10 G3-A.

## Packet identity (revealed only after sealing; blinding PARTIAL)
G3-C.1: P01->14248, P02->19495, P03->19346, P04->19040, P05->16886, P06->19637, P07->22914, P08->15875
G3-A:   P01->24443, P02->13615, P03->19783, P04->20590, P05->17630, P06->21847, P07->15349, P08->24213, P09->17318, P10->13974

12/18 packets self-reference the issue number in symptom/probe/patch text -> identity blinding is PARTIAL; record de-blinding risk.

## Focused reviews (mandatory, separate blank worksheet)
- **FR1_probe_19495_instrument_vs_oracle_redefinition**: Was the probe strengthening a correction of the TEST INSTRUMENT only, or did observing the candidate patch succeed lead to a selective post-hoc redefinition of the acceptability oracle?  (ai_determination=null, human_decision=PENDING)
- **FR2_two_rejects_same_acceptability_standard**: Do 14248 and 15875 apply the SAME acceptability standard, or do the different failure modes imply different oracle rules that should be pre-registered separately before expansion?  (ai_determination=null, human_decision=PENDING)

## Annotator requirements (frozen in plan)
- Python/SymPy competence; able to read pytest output and diffs;
- blind to all model outputs and prior labels;
- independent time commitment recorded per packet;
- disagreement -> senior arbiter; leave-one-issue-out sensitivity recomputed under annotator1 / annotator2 / adjudicated labels.

## Source artifacts (read-only, sha256)
- `evidence_store_g3c11/human_annotation/g3c11_second_annotator_plan.json`  `13972fb564f847f22d4477dfbb50754888978cc50751eeaf3a4d5966bb9c6ae8`
- `evidence_store_g3c11/human_annotation/g3c11_human_focused_review_items.json`  `22389ee201f6ad86e0294b50c883d37abed234791ae41b7b9e3fc16b2112d8da`
- `evidence_store_g3c11/human_annotation/g3c11_annotator2_blank_labels.csv`  `0d6de772c66ed7a7d62cb58e4b6e947a3d195c6415340abadd3bec5d09cdd6e5`
- `evidence_store_g3c11/human_annotation/g3c11_human_focused_review_worksheet.csv`  `463adeec63527a8d916b56fe8f9fa3c34dd2fb0a0aed0255d881798aec115b1c`

Blank labels file: `evidence_store_g3c11/human_annotation/g3c11_annotator2_blank_labels.csv`; focused worksheet: `..._g3c11_human_focused_review_worksheet.csv`.
