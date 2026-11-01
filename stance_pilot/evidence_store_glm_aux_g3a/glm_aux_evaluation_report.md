# GLM auxiliary pre-annotation — evaluation report (NOT a research result)

**Status:** exploratory, decision-support only. GLM-4.6 is an AI, **not** independent annotator #2. These labels are excluded from the GPT/DeepSeek 80-cell research results (`research_excluded=true`), are **not pooled**, and do **not** upgrade Gold, which stays **PROVISIONAL**. The three right-most columns of the CSV are for the human reviewer to fill.

- Model served: `glm-4.6` (OpenAI-compatible bigmodel endpoint)
- Mode: blind static packet annotation (same 9-file packet + same human rubric), thinking disabled, temperature 0.2, JSON mode
- Cohort: G3-A packets P01–P10 (10/10)
- Annotation tokens: in=109,878 out=3,535
- Estimated cost: **RMB 0.2480** (conservative upper-bound list price ¥2.0/M in, ¥8.0/M out; vendor console bill authoritative)
- Hard pre-call budget guard: RMB 20.0 (never approached)

## Headline

- GLM agrees with PROVISIONAL oracle gold on **10/10** packets.

## Label table

| Packet | Instance (unblinded) | GLM | Gold (PROV.) | Agree | Conf. | Decisive failing test ids |
|---|---|---|---|---|---|---|
| P01 | sympy__sympy-24443 | ACCEPT | ACCEPT | YES | high | — |
| P02 | sympy__sympy-13615 | ACCEPT | ACCEPT | YES | high | — |
| P03 | sympy__sympy-19783 | REJECT | REJECT | YES | high | sympy/physics/quantum/tests/test_operator.py::test_identity |
| P04 | sympy__sympy-20590 | ACCEPT | ACCEPT | YES | high | — |
| P05 | sympy__sympy-17630 | REJECT | REJECT | YES | high | test_zero_matrix_add |
| P06 | sympy__sympy-21847 | ACCEPT | ACCEPT | YES | high | — |
| P07 | sympy__sympy-15349 | ACCEPT | ACCEPT | YES | high | — |
| P08 | sympy__sympy-24213 | ACCEPT | ACCEPT | YES | high | — |
| P09 | sympy__sympy-17318 | REJECT | REJECT | YES | high | test_issue_12420 |
| P10 | sympy__sympy-13974 | ACCEPT | ACCEPT | YES | high | — |

## Artifacts

- Raw responses: `raw/P0x_response.json` (verbatim model JSON, usage, finish reason)
- Per-packet records: `records/P0x.json` (with packet file sha256 provenance)
- Human correction worksheet: `glm_prelabels_for_human_correction.csv`
- Token/cost ledger: `glm_cost_ledger.json`
- Runner: `stance_pilot/evidence/g3c1_glm_aux_preann.py` (imports no frozen modules)

> Boundary reminder: fill `human_corrected_label` / `human_agrees_with_glm` / `human_notes` yourself. Only an independent human + arbiter can populate annotator2 and move Gold off PROVISIONAL.
