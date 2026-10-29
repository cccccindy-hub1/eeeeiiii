# GroundedReview — Gate G3-C.1.1 Independent Audit Report

- Design version: `groundedreview-gate3c11-zero-api-audit-freeze-v1`
- Protocol: `g3c11-protocol-v1`
- Scope: zero-API offline audit; $0 added, 0 new issues, no model, no historical-gold change, no frozen-test rewrite, no R2, no Git commit.

## 1. Headline conclusions

1. Integrity PASS: all 185 frozen files hash-match, all parent pins match, truth/artifact/oracle are mutually consistent, freshness 8/8, 40 certificates (24 sufficient/16 NEED), 456/456 HTTP assertions pass, 40 mock cells are plumbing-only (research excluded), projection v2 non-interference holds on all 144 restricted tier-D surfaces.
2. Funnel replay is byte-identical: 75 ->(24 mutually-exclusive exclusions)-> 51 ->(4 changed-file dedup, natural queue only)-> 47; natural and enriched queues do not overlap (union=8) and are kept as separate denominators; no double counting.
3. Enrichment priority TRAP>P2P>F2P is a PILOT-STAGE PRE-DATA operational refinement, fixed 28 minutes before the first outcome, NOT verbatim pre-registered in G3-C.0; the counterfactual F2P-first order moves 29 strata and would pick 4 different issues, so it is disclosed and must not be claimed as fully pre-registered.
4. Both REJECTs independently reproduce from raw pytest logs: 14248 = one declared F2P genuinely still failing (test_MatrixSymbol_printing PARTIAL_FAIL) plus two true regressions (test_haramard, test_matMul), with test_latex_Float correctly treated as pre-existing; 15875 = a single decisive declared F2P failure (test_Add_is_zero 'assert True is None'), independent of P2P/environment.
5. Instrument blind spot disclosed: 15875 has TWO undeclared candidate-era collateral failures in an executed scope file (test_nfloat, test_subs_in_derivative; PASSED at baseline) that the declared-id scorer does not count; 19346 has one baseline-unmapped undeclared collateral (test_set). These do not change frozen gold but bound coverage claims.
6. The six ACCEPTs support only SCOPED acceptability: all declared F2P transition, zero declared scoped-P2P regressions, symptom gone; full-dataset P2P, distant modules, performance/style and alt-patch equivalence are not validated.
7. sympy-19495 probe revision is construct-valid: the original instrument was too weak (passed at both base and post); the frozen strengthened probe is derived only from the public report, maintainer test_patch never consulted, no gold changed, no issue replaced, and post-revision all 8 probes flip. Frozen probe sha matches the manifest and was not modified.
8. Human adjudication NOT obtained: all 18 blind packets (10 G3-A + 8 G3-C.1) are PENDING; 18/18 gold remain PROVISIONAL with annotator2 NOT_OBTAINED and zero AI labels; no Gold Adjudication Version is produced. Two approver-mandated focused reviews are also left PENDING for the human: FR1 sympy-19495 probe instrument-only-fix vs post-hoc oracle redefinition, and FR2 whether 14248/15875 use one uniform disjunctive REJECT standard.
9. Recommendation for G3-C.2: NO-GO until (PC1) independent human gold adjudication, (PC2) written amendment/disclosure of the stratum connection order, and (PC3) the R-TRAP sampling shortfall (2 available vs floor 6) are resolved.

## 2. Frozen-artifact integrity (tasks 1 & 8)

| Check | Result |
| --- | --- |
| verification overall | PASS |
| frozen files checked | 185 |
| file hash mismatches | 0 |
| freshness | 8/8 match |
| certificates (sufficient / NEED) | 40 (24/16) |
| HTTP assertions | 456/456 |
| mock cells (plumbing, research-excluded) | 40 |
| restricted tier-D surfaces with findings | 0 |
| determinism (3/3 byte-identical) | PASS |

100% plumbing match is EXPECTED and research-EXCLUDED; not a model-performance number.

## 3. Selection funnel & dual queues (tasks 2 & 4)

S0 **75** → 24 mutually-exclusive exclusions → **51** eligible → 4 changed-file de-duplications (natural queue only) → **47** stratum base. No double counting: exclusions are if/elif-disjoint and dedup is applied once.

| Stratum | n in 47 pool |
| --- | --- |
| R-F2P | 16 |
| R-P2P | 29 |
| R-TRAP | 2 |
| UNENRICHED | 0 |

- Natural first-4: 19346, 22914, 19495, 15875
- Enriched first-4: 19040, 14248, 19637, 16886
- Queues are disjoint (union = 8); denominators/pass-rates are reported SEPARATELY and never pooled into a natural-population rate.

## 4. Enrichment-priority timeline & pre-registration status (task 3)

| UTC time | Event |
| --- | --- |
| 2026-10-27T08:04:23.590449+00:00 | G3-C.0 preregistration design JSON written |
| 2026-10-27T08:24:44.758246+00:00 | G3-C.0 design freeze manifest written |
| 2026-10-28T09:08:46.683717+00:00 | g3c1_common.py (eligibility constants/seeds) written |
| 2026-10-28T09:20:33.924078+00:00 | g3c1_select.py STRATUM_PRIORITY source fixed |
| 2026-10-28T09:48:33.791305+00:00 | first executed outcome: sympy-19495 probe-flip stop record |
| 2026-10-28T10:16:07.927376+00:00 | real pytest build session ends (last truth) |
| 2026-10-28T10:50:12.541521+00:00 | selection JSON mtime (determinism re-run regeneration; byte-identical sha f3284c75...) |
| 2026-10-28T10:50:12.573852+00:00 | oracle gold + freeze manifests written |

**Classification:** PILOT-STAGE PRE-DATA operational refinement: within the G3-C.0 expressly permitted 'pre-specified stratified/negative-enrichment screen', the concrete multi-membership connection priority R-TRAP>R-P2P>R-F2P was fixed in g3c1_select.py at 09:20:33Z from static pool structure alone, 28 minutes before the first executed outcome (09:48:33Z) and before any build. It was not literally pre-registered in G3-C.0 and must be disclosed as such; it must NOT be retrospectively claimed as fully pre-registered, and it is not outcome-dependent adaptation.

## 5. Per-issue gold-quality table (tasks 5, 6, 7)

| issue | queue | stratum | gold | F2P fail/total | declared P2P regressions | undeclared candidate-era collateral | supports | tier |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 14248 | enriched | R-P2P | REJECT | 1/2 | test_haramard, test_matMul | - | REJECT on declared evidence | PROVISIONAL |
| 15875 | natural | R-P2P | REJECT | 1/1 | - | test_nfloat, test_subs_in_derivative | REJECT on declared evidence | PROVISIONAL |
| 16886 | enriched | R-P2P | ACCEPT | 0/1 | - | - | SCOPED acceptability only | PROVISIONAL |
| 19040 | enriched | R-TRAP | ACCEPT | 0/1 | - | - | SCOPED acceptability only | PROVISIONAL |
| 19346 | natural | R-P2P | ACCEPT | 0/1 | - | test_set | SCOPED acceptability only | PROVISIONAL |
| 19495 | natural | R-TRAP | ACCEPT | 0/1 | - | - | SCOPED acceptability only | PROVISIONAL |
| 19637 | enriched | R-P2P | ACCEPT | 0/1 | - | - | SCOPED acceptability only | PROVISIONAL |
| 22914 | natural | R-F2P | ACCEPT | 0/1 | - | - | SCOPED acceptability only | PROVISIONAL |

`undeclared candidate-era collateral` = failing nodes in executed scope files that are absent from the dataset's declared PASS_TO_PASS id set: not scored, disclosed as an instrument coverage blind spot. ACCEPTs are SCOPED only (full-dataset P2P not run).

## 6. sympy-19495 probe construct audit (task 6)

- Frozen probe sha matches manifest: **True** (read-only, not modified).
- Initial instrument: baseline_passed=True, post_passed=True (too weak).
- Maintainer test_patch consulted: maintainer_test_patch_consulted=False.
- Post-revision gate: all_probes_flip=True over 8 issues; no_gold_changed=True, no_issue_replaced=True.

## 7. Human second-annotator status (tasks 9 & 10)

| cohort | packet | issue (sealed; study team only) | files | self-refs | annotator2 | adjudication | tier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G3-A | P01 | 24443 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P02 | 13615 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P03 | 19783 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P04 | 20590 | 9 | patch | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P05 | 17630 | 9 | patch | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P06 | 21847 | 9 | patch | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P07 | 15349 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P08 | 24213 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P09 | 17318 | 9 | - | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-A | P10 | 13974 | 9 | patch | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P01 | 14248 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P02 | 19495 | 9 | patch, probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P03 | 19346 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P04 | 19040 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P05 | 16886 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P06 | 19637 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P07 | 22914 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |
| G3-C.1 | P08 | 15875 | 9 | probe | NOT_OBTAINED | PENDING | PROVISIONAL |

18/18 PENDING and PROVISIONAL; annotator2 = NOT_OBTAINED; zero AI labels. Identity blinding is PARTIAL (verbatim patch/probe text may quote the issue number). A real second human + third-senior-human arbitration is required before any Gold Adjudication Version.

## 7a. Approver-mandated human focused reviews (Risk B & II.1)

### FR1_probe_19495_instrument_vs_oracle_redefinition — sympy__sympy-19495

**Question:** Was the probe strengthening a correction of the TEST INSTRUMENT only, or did observing the candidate patch succeed lead to a selective post-hoc redefinition of the acceptability oracle?

Probe-revision timeline (UTC): weak-probe failure 2026-10-28T09:48:33Z → strengthened probe 2026-10-28T09:51:02Z → all-8-flip selftest 2026-10-28T09:54:50Z, i.e. ~24 min BEFORE the real pytest build (2026-10-28T10:15:07Z).

AI determination: **none** (`ai_determination=null`); human decision: **PENDING**.

### FR2_two_rejects_same_acceptability_standard — 14248 + 15875

**Question:** Do 14248 and 15875 apply the SAME acceptability standard, or do the different failure modes imply different oracle rules that should be pre-registered separately before expansion?

AI determination: **none** (`ai_determination=null`); human decision: **PENDING**.

Both items must be answered by the real independent human (blank worksheet: `human_annotation/g3c11_human_focused_review_worksheet.csv`) before G3-C.2; they are inputs to blocking precondition PC1.

## 8. Sensitivity (task 11)

The zero-API pilot ran NO Reviewer model on these 8 issues, so P1/P2 model numerators DO NOT EXIST yet. This analysis bounds only GOLD-SIDE denominators/eligibility; no rate is estimable and none is claimed. Gold must never be changed to match a model prediction.

## 9. Gate G3-C.2 decision (task 12)

**Recommendation: NO-GO (do not release G3-C.2 real expansion yet)**

Blocking preconditions:
- **PC1_independent_gold_review** — A real, independent annotator-2 labels all 18 blind packets (10 G3-A + 8 G3-C.1) and a third senior human adjudicates disagreements; only then is a new Gold Adjudication Version produced and gold raised above PROVISIONAL. The same independent human must also answer the two approver-mandated focused reviews: FR1 sympy-19495 probe (instrument-only fix vs post-hoc oracle redefinition) and FR2 (14248 vs 15875 share one uniform disjunctive REJECT standard). *Current state: NOT MET - annotator2 NOT_OBTAINED, 18/18 PROVISIONAL/PENDING, FR1/FR2 PENDING, zero AI labels allowed.*
- **PC2_sampling_rule_trustworthiness** — Either (a) amend the pre-registration in writing to lock the TRAP>P2P>F2P multi-member tie/connection order as the operative rule, disclosing it is a pilot-stage pre-data operational refinement rather than verbatim G3-C.0 text; or (b) re-run the design under the literal G3-C.0 enumeration. *Current state: PARTIALLY MET - rule predates first outcome by ~28 min (pre-data, not post-outcome adaptive) and replay is byte-identical, but the order was not fixed verbatim in G3-C.0; counterfactual F2P-first would move 29 strata and pick 4 different issues.*
- **PC3_R_TRAP_sampleability** — Secure >=6 R-TRAP independent negatives per the pre-registered floor (the 17318/17630/19783 anchors are held-out and do not count toward NEW issues). *Current state: NOT MET - de-duplicated 47-issue pool contains only 2 R-TRAP; shortfall 4. Requires additional eligible candidate material, which needs data collection this gate does not authorise.*

## 10. Next action

STOP. Await separate written approval of G3-C.2; this gate executes no expansion.
