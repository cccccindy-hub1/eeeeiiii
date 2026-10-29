# GroundedReview — Gate 3-B.4 zero-API strict audit

audit version: `groundedreview-gate3b4-zero-api-strict-audit-v1`  
budget: **$0** · model calls by this audit: **0** · issues added: 0 · gold changed: **no** · git commits: **0**

> Gold is **PROVISIONAL** throughout: one annotator, n=1, `annotator2 = NOT_OBTAINED`. AI self-review is never independent human arbitration. Cross-version contrasts are **ASSOCIATIONAL**.

## 1. Result integrity (tasks 1 & 10)
100/100 real cells (2 models x 10 issues x 5 conditions) re-verified against the frozen result pins; all 100 raw responses and 100 live traces match; raw-first persistence holds; **208 real model calls** (DeepSeek 114, GPT 94); retries = errors = resume-skips = 0; wire shows no fallback; served model ids match; mock run ($0) and live run are fully isolated; the analyser/report are post-collected and their hashes match the post-collection freeze; prompt/protocol fingerprints match the pre-paid freeze. Live spend: guard-accumulated **$0.303539** (DeepSeek 0.189045 / GPT 0.114494); row-rounded sum $0.303537 (the ~1e-6 gap is rounding only).

## 2. DeepSeek 9/10 -> 1/10 independent recomputation (task 2)
Independent third implementation (own Clopper-Pearson bisection and issue-cluster bootstrap, seed 417313, B=10000): need-any **None -> None**; 8 need->non-need reversals, 0 reverse; the single residual is **SymPy-13974**. CP95 need-any intervals: G3-B (0.555, 0.997), G3-B.3 (0.003, 0.445); paired-difference cluster bootstrap 95% CI **0.5-1.0**. Full per-condition transition matrices are in `g3b4_deepseek_recompute.json`.

## 3. GPT T3D-Strict per-issue audit (task 3)
Condition gold is NEED_EVIDENCE for all 10 cells. Result: **7 unsupported ACCEPT** (13615, 13974, 15349, 17318, 17630, 21847, 24443), **0 unsupported REJECT**, **3 correct NEED** (19783, 20590, 24213). ACCEPT and REJECT error families are counted separately — nothing is auto-bucketed as unsupported acceptance. Under strict the post-patch acceptance verdict is unreachable (no f2p/p2p log granted; consistency adjudicates symptom only); all 7 ACCEPTs therefore **structurally upgrade non-decisive evidence** (linkage=true + fresh=true + coverage-complete + symptom-gone) into sufficient acceptance. Full gold/final verdict/reason/every tool request-and-response is in `g3b4_gpt_strict_audit.json`.

## 4. Partially-blinded reason coding (task 4)
Codebook frozen **before** coding (`blind_coding/g3b4_blind_codebook.json`, sha 82dc5fe09287dc2f…); masked packets D01-D07 (seed 417997), coded before unblinding. This is a **single AI, rule-based coder with NO independent human coder and NO independent review** — it is not independent arbitration. All 7 units received primary code **C3** (absence-of-failure-evidence treated as evidence of absence) and all co-fired C1 (symptom resolution) + C2 (coverage completeness) + C5 (provenance/freshness); **C4 never fired** — the model never acknowledged the withholding before accepting. Blind is partial: symptom prose can identify an issue.

## 5. T2D vs Strict (task 5)
Both models abstain 10/10 on static **T2D-T** in both gates. DeepSeek Strict abstains 10/10 in both gates (it fetched the tier-D artifact in 8/10 G3-B.3 cells and still abstained). GPT Strict moved 10/10 abstain (G3-B) -> 3/10 (G3-B.3), committing on the same 7 issues, none of which fetched the artifact. This supports — but does not prove — **active-evidence-induced over-commitment**; the cross-version contrast is confounded because freshness and trust rules changed together with activeness.

## 6. Non-interference masking (task 6)
Tier-1 scan (real post-patch f2p/p2p verdict, hidden gold, acceptance digests, reconstructing keys): **61/61 surfaces clean**. One **tier-2 minimisation gap**: the *pre-patch* base-commit `pass_to_pass_baseline` per-test map survives the tier-D projection (10/10 issues carry it, all-PASSED with 0 FAILED). It cannot reconstruct gold (the post-patch P2P map is removed; zero ACCEPT/REJECT discrimination), is reachable only via an explicit artifact fetch, was seen by **none** of the 7 error cells (the one GPT cell that saw it, 20590, abstained; DeepSeek saw it in 8 cells and abstained 10/10), and has no causal link to the over-commitments. It must be stripped (add the field to `views._ACCEPTANCE_RECORD_FIELDS`) before Gate 3-C; frozen G3-B.3 code is not modified here.

## 7. SymPy-13974 dedicated audit (task 7)
DeepSeek NEED under T2A and T3D-Escalate but ACCEPT under T3A; Strict correctly NEED. Fact-checking against the frozen store: the declared F2P test is **['test_tensor_product_simp']** and it **is present and PASSED**; the test DeepSeek believed missing (`test_tensor_product_power`) is a test the candidate patch itself adds, not a maintainer-declared test. f2p and p2p post-patch logs are byte-identical (one combined test-file run) but the baseline differs — so the model’s "all three logs identical / declared acceptance test absent" claims are wrong. Classification: **residual model evidence-interpretation / policy error (over-abstention), n=1**, not a legitimate evidential-standard difference and not a new protocol inconsistency. The identical-file presentation is a hardening candidate.

## 8. GPT focal error families (task 8, kept separate)
- **Family F1 — SymPy-17318 / T2A false ACCEPT** (evidence-verification failure): the declared F2P `test_issue_12420` actually FAILED (`assert [4 + I, 0, 1] == []`), yet GPT accepted from the static tier-A surface in both G3-B and G3-B.3; the active T3A control on the same issue correctly REJECTed.
- **Family F2 — SymPy-17630 / T3A REJECT -> NEED**: GPT saw the failed declared F2P `test_zero_matrix_add` (other FAILED tokens are xfail markers, p2p regressed/bad ids empty) but judged it "unrelated to the patch" and abstained instead of REJECT — a decision-policy over-abstention that relitigates declared-test relevance.
These are opposite error directions and are not pooled. The independent-REJECT set is only n=3, so report cases, not a rate.

## 9. First-run failure and repair timeline (task 9)
`CompositeGuard.check` ended without a return, giving `None`; the runner then ran `float(None)` at g3b3_run.py L251, **before** `driver.chat.completions.create` at L270, so the first live attempt raised before any HTTP request — **zero API spend**. The mock gate had passed because the mock path skips the guard. Repair: added `return bound` (current L148-153); the $0 error products were discarded; the executed freeze + preflight were regenerated; the corrected run produced the final 100/100 (0 error rows, no on-disk residue; run audit new=50/model, skipped=0). The live-gate artifact (mtime 02:04) is the pre-paid, zero-API local g3b2 HTTP integration gate, which explains its earlier timestamp. Deleted $0 products cannot now be hashed; this is disclosed rather than presenting only the final 100/100.

## Per-issue audit table
| issue | gold* | DS T2A g3b/g3b3 | DS T3D-Esc g3b/g3b3 | DS T3A g3b/g3b3 | GPT Strict g3b/g3b3 | GPT Strict family | blind | focus |
|---|---|---|---|---|---|---|---|---|
| 13615 | ACCEPT | NEED/ACCE | ACCE/ACCE | NEED/ACCE | NEED/ACCE(A) | unsup ACCEPT | C3 | - |
| 13974 | ACCEPT | NEED/NEED | NEED/NEED | NEED/ACCE | NEED/ACCE(A) | unsup ACCEPT | C3 | DS residual |
| 15349 | ACCEPT | NEED/ACCE | NEED/ACCE | NEED/ACCE | NEED/ACCE(A) | unsup ACCEPT | C3 | - |
| 17318 | REJECT | REJE/REJE | REJE/REJE | REJE/REJE | NEED/ACCE(A) | unsup ACCEPT | C3 | F1 false-accept |
| 17630 | REJECT | NEED/REJE | REJE/REJE | NEED/REJE | NEED/ACCE(A) | unsup ACCEPT | C3 | F2 reject->need |
| 19783 | REJECT | NEED/REJE | REJE/REJE | REJE/REJE | NEED/NEED | correct NEED | - | - |
| 20590 | ACCEPT | NEED/ACCE | NEED/ACCE | NEED/ACCE | NEED/NEED | correct NEED | - | - |
| 21847 | ACCEPT | NEED/ACCE | NEED/ACCE | NEED/ACCE | NEED/ACCE(A) | unsup ACCEPT | C3 | - |
| 24213 | ACCEPT | NEED/ACCE | NEED/ACCE | NEED/ACCE | NEED/NEED | correct NEED | - | - |
| 24443 | ACCEPT | NEED/ACCE | NEED/ACCE | NEED/ACCE | NEED/ACCE(A) | unsup ACCEPT | C3 | - |

\* gold is PROVISIONAL: single annotator, n=1, annotator2 NOT_OBTAINED. Verdicts abbreviated (ACCE/REJE/NEED).

## 11. Second independent annotator plan (task 11)
See `g3b4_planning_and_revisions.json` -> `task11_second_annotator_plan`: a human annotator2 blind to all model output and prior labels, randomised sealed packets, a third senior human arbiter for any ACCEPT/REJECT disagreement (never an LLM or the pipeline author), and recomputation of every rate under annotator1 / annotator2 / adjudicated labels with leave-one-issue-out sensitivity. Proposed only; not executed.

## 12. Revised Gate 3-C design (task 12) — NOT executed
Priority 1 is expanding independent REJECT issues (target >=20 in total) to enable a false-accept rate; priority 2 is a genuinely restricted-evidence stratum kept separate from sufficient-evidence trials. An activeness-only controlled arm (freshness/trust held fixed) is specified to identify the candidate over-commitment mechanism. Primary endpoint, paired issue-clustered analysis, sample size/Wilson-width rationale, hard pre-call budget caps and explicit stopping rules are pre-registered. Planning uses the observed mean $0.003035/live cell. **No expansion is run in Gate 3-B.4; budget remains $0.**

## 13. Paper Results / Discussion revisions (task 13)
- **DeepSeek earlier 9/10 sufficient-evidence abstention** — The originally observed 9/10 over-abstention was substantially driven by PROTOCOL-CONSTRUCT problems in the G3-B instrument (structural fresh=FALSE and the coverage/trust handling), not by a stable model property. After the G3-B.3 corrective replication the paired need-any rate moved 9/10 -> 1/10 (8 need->non-need reversals, 0 reverse; issue-cluster bootstrap 95% CI for the paired difference 0.5-1.0). Report as an ASSOCIATIONAL before/after contrast.
- **residual DeepSeek over-abstention** — After repair the only residual sufficient-evidence over-abstention is SymPy-13974 (NEED under T2A and T3D-Escalate while ACCEPT under T3A). Fact-checking shows the abstention rests on two wrong readings (a declared acceptance test believed missing that is actually present and passing; three logs believed identical when the baseline differs); classify as a residual model evidence-interpretation/policy error, n=1, gold PROVISIONAL pending annotator2.
- **GPT erroneous acceptance** — GPT false acceptance PERSISTS after the protocol repair (e.g., SymPy-17318 T2A accepts although the declared F2P test failed; active T3A on the same issue rejects). However the independent REJECT sample is only n=3, so report specific cases, not a population rate, and flag the estimate as underpowered pending Gate 3-C.
- **strict over-commitment** — Under T3D-Strict, GPT returned unsupported ACCEPT on 7/10 gold-NEED cells in G3-B.3 vs 0/10 in G3-B, while both models abstain 10/10 on the static T2D surface and DeepSeek abstains 10/10 even when actively querying. Describe active-evidence-induced over-commitment strictly as a NEW CANDIDATE MECHANISM: the cross-version comparison is confounded (freshness and trust rules changed with activeness), so it must NOT be called demonstrated until the activeness-only controlled experiment is run.

Discussion additions and the explicit "claims not to make" list are in `g3b4_planning_and_revisions.json`.

---
**Stopping here as instructed. Gate 3-C expansion, Gemini, R2 and any new paid-model experiment remain un-approved and un-executed; awaiting the next written approval.**
