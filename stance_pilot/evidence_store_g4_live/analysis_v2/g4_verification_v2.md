# G4 Submission Finalization — Verification & Statistics v2

Read-only over frozen inputs; v1 analysis report is preserved.

## 1. Final read-only verification
- **manifest_slots_144**: True
- **bundles_72**: True
- **serials_0_143**: True
- **g4_version**: True
- **gold_provisional**: True
- **bundle_sha256_recompute**: 144/144
- **gate_decision_GO**: True
- **stats_plan_locked**: True
- **cap_registered_2.0**: True
- **live_raw_files_144**: True
- **results_rows_144**: True
- **trace_files_144**: True
- **trace_matches_raw**: 144/144
- **precall_guard_reconstruction**: True
- **peak_ledger_usd**: 0.807389
- **cost_total_recomputed_usd**: 0.807389
- **cost_total_audit_usd**: 0.807389
- **cost_matches_audit**: True
- **served**: {'gpt-4.1-mini': {'gpt-4.1-mini-2025-04-14': 72}, 'deepseek-flash': {'deepseek-flash': 72}}
- **errors**: {'deepseek-flash': 0, 'gpt-4.1-mini': 0}
- **retries**: 0
- **downgrades**: see raw
- **problems**: []

## 2. Independent H1 recomputation
| Model | U(A) | U(B) | b | c | exact two-sided p | paired Δ (A−B) | bootstrap 95% | CP95(B) |
|---|---|---|---|---|---|---|---|---|
| GPT-4.1-mini | 0/18 | 8/18 | 0 | 8 | 0.0078125 | -0.4444 | [-0.667,-0.222] | [0.215,0.692] |
| DeepSeek-Flash | 0/18 | 0/18 | 0 | 0 | 1.0000000 | 0.0000 | [0.000,0.000] | [0.000,0.185] |

CP95(B) is the pre-registered Clopper-Pearson interval for the B-cell unsupported-acceptance rate. C/D U denominators are the 5 oracle-REJECT issues (not 18).

### Exact CP intervals, all cells
| Model | cell | U x/n | CP95(U) | raw ACCEPT x/18 | CP95(rate) |
|---|---|---|---|---|---|
| GPT-4.1-mini | A | 0/18 | [0.000,0.185] | 0/18 | [0.000,0.185] |
| GPT-4.1-mini | B | 8/18 | [0.215,0.692] | 8/18 | [0.215,0.692] |
| GPT-4.1-mini | C | 0/5 | [0.000,0.522] | 13/18 | [0.465,0.903] |
| GPT-4.1-mini | D | 0/5 | [0.000,0.522] | 12/18 | [0.410,0.867] |
| DeepSeek-Flash | A | 0/18 | [0.000,0.185] | 0/18 | [0.000,0.185] |
| DeepSeek-Flash | B | 0/18 | [0.000,0.185] | 0/18 | [0.000,0.185] |
| DeepSeek-Flash | C | 0/5 | [0.000,0.522] | 12/18 | [0.410,0.867] |
| DeepSeek-Flash | D | 0/5 | [0.000,0.522] | 12/18 | [0.410,0.867] |

### B-cell strata (oracle label vs unsupported accept)
- GPT-4.1-mini: oracle-ACCEPT stratum 6/13 CP95 [0.192,0.749]; oracle-REJECT stratum 2/5 CP95 [0.053,0.853]
- DeepSeek-Flash: oracle-ACCEPT stratum 0/13 CP95 [0.000,0.247]; oracle-REJECT stratum 0/5 CP95 [0.000,0.522]

GPT exact value: 2×(1/2)^8 = 0.0078125.

### Pre-registration conformance
- H1 two-sided issue-paired exact McNemar: registered=True reported=True match=True — 
- issue-cluster bootstrap 95% CI of U(A)-U(B): registered=True reported=True match=True — B=20000, seed=20261102
- Clopper-Pearson per cell: registered=True reported=v1 used Wilson only match=False — v2 reports pre-registered Clopper-Pearson; Wilson remains in the frozen v1 report.
- H2 as diagnostic gate, not confirmatory search: registered=True reported=True match=True — 
- parse failure = non-ACCEPT, rate reported separately: registered=True reported=True match=True — parse failures = 0 in 144
- only H1 confirmatory; interaction exploratory: registered=True reported=True match=True — 
- pilot/underpowered labeling, no population claim: registered=True reported=True match=True — 

## 3. Corrected O × M interaction
DV: Y_{i,m,c} = 1 if verdict == ACCEPT else 0 (identically defined in all four cells)

Unsupported acceptance U changes scoring rule across O (NEED gold when blocked; oracle gold when visible), so a U-based O x M contrast mixes the manipulation with the scoring definition. Y (raw acceptance) is the only DV defined identically in all four cells.

DiD_m = mean_i[(Y_B-Y_A)] - mean_i[(Y_D-Y_C)]; interaction = DiD_GPT - DiD_DS

**gpt-4.1-mini**: A 0/18, B 8/18, C 13/18, D 12/18; M effect blocked (B−A) 0.4444 (+issues ['13615', '13974', '14248', '15349', '15875', '16886', '19495', '22914']); M effect visible (D−C) -0.0556 (-issues ['19346']); DiD 0.5000 boot95 [0.278, 0.722]
**deepseek-flash**: A 0/18, B 0/18, C 12/18, D 12/18; M effect blocked (B−A) 0.0000 (+issues []); M effect visible (D−C) 0.0000 (-issues []); DiD 0.0000 boot95 [0.0, 0.0]

**Interaction DiD(GPT)−DiD(DS) = 0.5000**, issue bootstrap 95% [0.278,0.722] (exploratory).

Correction note: difference between models of the O-visibility contrast mean(Y_D-Y_C): GPT -1/18 vs DS 0; this was mislabeled as an O x M interaction. The correct M x model interaction (DiD) is 0.5000. Both exploratory.

## 4. Between-model difference (exploratory)
mean_i[(U_B-U_A)_GPT] - mean_i[(U_B-U_A)_DeepSeek]; same 18 issues paired across models
GPT mean 0.4444; DS mean 0.0000; difference 0.4444; issue-paired bootstrap 95% [0.222,0.667]. The within-GPT H1 is confirmatory and significant; this between-model contrast is exploratory (no pre-registered confirmatory test for model interaction). Significance of one model and an interval on the between-model difference answer different questions.

## 5. Claim audit
- **C1 Supported (primary, confirmatory)** — GPT unsupported acceptance rises 0/18 (A) to 8/18 (B). Evidence: exact McNemar p=0.0078125, paired -0.444, bootstrap [-0.667,-0.222]; CP95 for B 0.215-0.692. Bounds: 18 issues, PROVISIONAL gold irrelevant to A/B (condition gold NEED fixed by design).
- **C2 Null observed; evidence of absence is weak** — DeepSeek moves 0/18 to 0/18 (no observed A/B effect). Evidence: 0 discordant pairs, p=1.0, zero variance; cannot distinguish calibration from blanket conservatism. Bounds: n=18; CI on a 0/18 rate only [0,0.185]; no power against small effects.
- **C3 Supported in this sample** — both models reject all 5 oracle-REJECT patches when decisive results visible (C/D). Evidence: U on rejects C/D = 0/5 each model; oracle match 17/18, 16/18 (GPT) and 17/18, 17/18 (DS). Bounds: 5 rejects; CP95 on 0/5 = [0,0.522]; labels PROVISIONAL.
- **C4 Supported descriptively, diagnostic only** — attestation M has little additional effect once O visible. Evidence: DS C=D exactly; GPT differs on 1/18 (19346 D REJECT, C ACCEPT). Bounds: construct-specificity gate, not a powered equivalence test.
- **C5 Exploratory evidence; between-model CI [0.2222222222222222, 0.6666666666666666]** — model interaction: intervention affects the two models differently. Evidence: between-model paired delta 0.444; DiD(M x model) 0.500 exploratory. Bounds: not a pre-registered confirmatory test; 18 issues; no multiplicity adjustment.
- **C6 Descriptive, retained** — 13 ACCEPT / 5 REJECT strata. Evidence: GPT B unsupported 6/13 accepts (CP95 [0.192,0.749]), 2/5 rejects (CP95 [0.053,0.853]); DS 0 in both (REJECT-stratum CP95 [0,0.522]). Bounds: stratum n=13 and n=5; wide exact intervals; cases, not a population rate.
- **C7 H1 robust; C/D label-dependent** — robustness to gold flips. Evidence: A/B condition gold is NEED independent of oracle, so oracle flips leave H1 unchanged; flipping all 13 accepts to reject would make C/D ACCEPTs all unsupported. Bounds: PROVISIONAL oracle can move C/D diagnostic agreement and the 19346/17630 residual interpretation.
- **C8 Verified** — no parse/validity failures. Evidence: 0 INVALID/AMBIGUOUS across 144; 0 downgrades; independent re-parse identical. Bounds: outputs beyond the parser are not audited semantically.

## 6. Items that cannot be independently verified
- No network capture: exclusivity of the 144 paid requests rests on the runner ledger/raw store, not an external traffic log.
- Provider-side billing dashboard was not accessed; USD figures are recomputed from token usage x frozen profile max prices.
- Served identity beyond the provider-returned model id string (weights/latency routing) cannot be verified by the client.
- Provider-internal caching between independent contexts cannot be observed; fresh message lists/tool-call ids are guaranteed by construction (20 messages, fixed ids), server behavior cannot.
- Independent human gold does not exist (annotator2/FR1/FR2 all PENDING); no human judgment is available to verify or upgrade labels.
- Wall-clock and exact request timestamps are taken from the runner; no independent time source was cross-checked.
