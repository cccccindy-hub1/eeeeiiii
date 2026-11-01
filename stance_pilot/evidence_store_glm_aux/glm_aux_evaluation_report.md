# GLM auxiliary pre-annotation — evaluation report (NOT a research result)

**Status:** exploratory, decision-support only. GLM-4.6 is an AI, **not** independent annotator #2. These labels are excluded from the GPT/DeepSeek 80-cell research results (`research_excluded=true`), are **not pooled**, and do **not** upgrade Gold, which stays **PROVISIONAL**. The three right-most columns of the CSV are for the human reviewer to fill.

- Model served: `glm-4.6` (OpenAI-compatible bigmodel endpoint)
- Mode: blind static packet annotation (same 9-file packet + same human rubric), thinking disabled, temperature 0.2, JSON mode
- Packets: G3-C.1 P01–P08 (8/8)
- Annotation tokens: in=320,171 out=3,148
- Estimated cost: **RMB 0.9757** (conservative upper-bound list price ¥2.0/M in, ¥8.0/M out; vendor console bill authoritative)
- Hard pre-call budget guard: RMB 20.0 (never approached)

## Headline

- GLM agrees with PROVISIONAL oracle gold on **7/8** packets.
- **1 disagreement(s), flagged for human adjudication:**
  - P03 (unsealed sympy__sympy-19346): GLM **REJECT** vs oracle gold **ACCEPT**

## Label table

| Packet | Instance (unblinded) | GLM | Gold (PROV.) | Agree | Conf. | Decisive failing test ids |
|---|---|---|---|---|---|---|
| P01 | sympy__sympy-14248 | REJECT | REJECT | YES | high | sympy/printing/tests/test_latex.py::test_matMul;sympy/printing/tests/test_julia.py::test_haramard;sympy/printing/tests/test_octave.py::test_haramard |
| P02 | sympy__sympy-19495 | ACCEPT | ACCEPT | YES | high | — |
| P03 | sympy__sympy-19346 | REJECT | ACCEPT | NO | high | sympy/printing/tests/test_repr.py::test_set |
| P04 | sympy__sympy-19040 | ACCEPT | ACCEPT | YES | high | — |
| P05 | sympy__sympy-16886 | ACCEPT | ACCEPT | YES | high | — |
| P06 | sympy__sympy-19637 | ACCEPT | ACCEPT | YES | high | — |
| P07 | sympy__sympy-22914 | ACCEPT | ACCEPT | YES | high | — |
| P08 | sympy__sympy-15875 | REJECT | REJECT | YES | high | test_subs_in_derivative;test_nfloat |

## Disagreement detail (read carefully before correcting)

### P03 — sympy__sympy-19346
- GLM: **REJECT**; oracle gold: **ACCEPT**
- GLM reason: The test_set failure is a decisive regression introduced by the candidate patch. The maintainer test patch expects srepr(set()) to return 'set()', but the candidate's _print_set implementation returns '{}' for an empty set. This test passed at the base commit (where test_set did not exist) and fails after the patch, making it an applicable PASS_TO_PASS regression.
- GLM trap concern: yes; test_set and test_dict are self-added tests by the candidate patch, and test_set fails due to a bug in the candidate's own implementation for the empty set edge case.
- GLM notes: The candidate patch introduces a bug where srepr(set()) returns '{}' instead of 'set()'. The maintainer test patch explicitly checks for 'set()' on empty sets. The other failures (test_Add, test_Mul, test_issue_8470, test_issue_13559) are pre-existing environment issues unrelated to this patch.
- **Why gold says ACCEPT:** the oracle counts only the *declared* check set in `04_declared_test_ids.json` (F2P=`test_dict`, which passes). The failing `test_set` is introduced by the maintainer gold test patch, is NOT in the declared F2P list, and therefore is not counted as a declared failure (41 checks / 0 failures).
- **Why a careful human might still reject:** the maintainer test patch adds an authoritative `test_set` asserting `srepr(set()) == 'set()'`, which fails because the candidate's new `_print_set` emits `'{}'` for an empty set — a real behaviour defect against the merged upstream acceptance test. This is the classic declared-set vs maintainer-acceptance / self-added-test boundary the protocol warns about. GLM mislabels it as a 'P2P regression that passed at base' (the test did not exist at base); the correct framing is an undeclared-but-authoritative acceptance failure.

## Focused review (post-unblind AI opinion; not a human answer)

| Item | GLM choice | Conf. | Rubric amendment |
|---|---|---|---|
| FR1 (19495) instrument vs oracle | instrument_fix | high | no |
| FR2 (14248+15875) standard | same_standard | high | no |

- **FR1 reason:** The FAIL_TO_PASS change in `test_subs_CondSet` is an instrument fix: the old test oracle `== S.EmptySet` was incorrect for the post-subs state (the interval `(-oo, 0)` is not empty just because `n < x` is unresolvable), and the patch corrects it to `== Interval(-oo, 0)`. The underlying target behavior—ConditionSet substitution not over-substituting the bound variable—remains stable and is what the issue symptom probe validates. The maintainer test patch adds a new probe for the exact issue (ImageSet substitution) without redefining what correctness means for ConditionSet substitution itself.
- **FR2 reason:** Both REJECTs apply the same standard: the patch introduces decisive P2P regressions (previously passing tests now fail) due to type-incompatibility in conditional logic. In P01, `c < 0` raises TypeError for symbolic `c` (e.g., `2*x`), breaking `test_matMul` and `test_haramard`. In P08, `self.simplify()` inside `_eval_is_zero` causes RecursionError and ZeroDivisionError, breaking `test_subs_in_derivative` and `test_nfloat`. Both are rejected because the patch's new code path fails on valid inputs that the base handled correctly.

## Artifacts

- Raw responses: `raw/P0x_response.json` (verbatim model JSON, usage, finish reason)
- Per-packet records: `records/P0x.json` (with packet file sha256 provenance)
- Human correction worksheet: `glm_prelabels_for_human_correction.csv`
- Token/cost ledger: `glm_cost_ledger.json`
- FR1/FR2: `glm_focused_review_fr1_fr2.json`
- Runner: `stance_pilot/evidence/g3c1_glm_aux_preann.py` (imports no frozen modules)

> Boundary reminder: fill `human_corrected_label` / `human_agrees_with_glm` / `human_notes` yourself. Only an independent human + arbiter can populate annotator2 and move Gold off PROVISIONAL.
