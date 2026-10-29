# GroundedReview Gate G3-C.0 — Zero-API Design Freeze

**Decision:** G3-B.4 accepted; Gate 3-C paid expansion NOT approved. G3-C.0 covers design freeze and data-quality preparation only. API budget **$0**; no issue materialised; no model call; no git commit.

## 1. G3-B.4 freeze (task 1)
All 16 G3-B.4 files re-hash to their frozen pins and the canonical digest matches (all_ok=True); G3-B.3 parent pins pass. No historical artifact was rewritten.

## 2. Restricted-evidence projection v2 (task 2)
New **versioned** diagnostic projection removes exactly one extra field, `pass_to_pass_baseline` (the all-PASSED pre-patch base-commit map that was the G3-B.4 tier-2 gap). Offline demonstration over the 10 frozen served artifacts:
- v1 tier-1/tier-2 findings: 0 / 10; **v2: 0 / 0**
- v2 JSON equals v1 minus that field (+ version tag) for all 10
- static diagnostic block is byte-identical v1 vs v2
- freshness/coverage/consistency/log/linkage channels never read the field; tier A untouched. Frozen views.py/server.py are NOT edited; v2 is an out-of-tree, separately versioned path.

## 3. Pre-registered endpoints (task 3)
- **P1 Unsupported Commitment** (restricted tier-D, condition-gold NEED): commitment = ACCEPT or REJECT; reported as P1a unsupported ACCEPT / P1b unsupported REJECT / P1c correct NEED, never merged.
- **P2 Unsupported Acceptance** (sufficient evidence, oracle-REJECT, decisive failure visible): ACCEPT / REJECT-gold. Distinct denominator and mechanism from P1; no pooled "hallucination rate".
- ACCEPT / REJECT / NEED_EVIDENCE kept separate throughout.

## 4. Sampling (task 4)
Independent issue = one upstream id/base commit (multi-arm is one unit). Target **>=20 NEW independent REJECT issues** (existing 3 held as anchors), balanced across R-F2P / R-P2P / R-TRAP strata, plus ~20 ACCEPT/need controls. Natural prevalence is measured before enrichment; enrichment sampling fractions are logged and enriched rates are never presented as natural-population rates.

## 5. Analysis (task 5)
Issue is the only independent unit (no pseudo-replication across conditions/turns/repeats). Wilson/exact CIs per rate, exact McNemar for paired binary contrasts, and issue-cluster bootstrap (10000 replicates, seed 418231); Holm correction across the two co-primary endpoints. Worked provisional P1a 7/10 Wilson95 ~[0.40,0.89]; with n=20 new negatives the P2 half-width is ~0.17 near p=0.2 (preliminary precision).

## 6. Evidence-availability comparison (task 6)
Pre-registered active tier-D vs static tier-D paired contrast for P1a. Tool access, information content and interaction turns are separated only by an orthogonal 2x2 (freshness/trust held fixed) plus a same-content stubbed-active control and a reminder arm. Until that is run, every G3-B->G3-B.3/static->active contrast is **ASSOCIATIONAL**; active-query over-commitment stays a candidate mechanism.

## 7. Non-interference protocol (task 7)
Deny list (post-patch F2P/P2P outcomes, gold/gold-reconstructing fields, f2p/p2p log digests, and now the baseline map); explicit allow list of legal pre-patch/structural information; hard rule that HTTP success/freshness TRUE/coverage complete/symptom-gone never auto-grant acceptance sufficiency. A machine gate (frozen G3-B.4 scanner) must report tier1=0 and tier2=0 on every rendered surface before any paid cell unlocks.

## 8. Second-human-annotator package (task 8)
Built **10 blind packets** (problem, candidate patch, maintainer test_patch, declared ids, f2p/p2p/baseline/symptom logs) with a written rubric, a blank labels CSV, a sealed mapping and third-human arbitration + gold-flip sensitivity rules. Status **PENDING** — no independent human labels exist. Identity blinding is partial: 4/10 verbatim patches self-quote the upstream issue number; the evidence is not rewritten and the limitation is logged.

## 9. Execution & budget plan, estimates only (task 9)
Basis is the frozen REAL G3-B.3 mean $0.003035/cell (not mock).

- **P0 quality pilot (mock + zero-API live g**: ~112 cells; expected $0.34; observed-max worst case $1.76; hard pre-call cap $2.02.
- **B1 first external validation (>=20 new i**: ~240 cells; expected $0.73; observed-max worst case $3.76; hard pre-call cap $4.32.
- **B2 expansion to balanced 40-issue design**: ~200 cells; expected $0.61; observed-max worst case $3.14; hard pre-call cap $3.61.

Each phase has pre-call hard caps, drift/protocol-failure halts, a clean non-interference gate, harm-only interim stops and no expansion without a new written approval.

## 10. Engineering standards (task 10)
Unified checks for served-model id drift, prompt-length/truncation, tool capability and strict-403 behaviour, fixed seeds/repeats-within-issue, pre-defined UNPARSEABLE/missing-reason handling, finish_reason=length detection, and a None/NaN-tested pre-call budget guard plus mock + zero-API live gates and raw-first persistence (the G3-B.3 discipline).

## 11. Paper claim boundaries (task 11)
- Old DeepSeek 9/10: substantially protocol-construct driven, reported associational — not a stable intrinsic defect.
- GPT Strict 7/10: an operationally defined observation on n=10 (PROVISIONAL gold, single-AI partial-blind coding) — causal mechanism NOT proven.
- GPT sufficient-evidence false ACCEPT: specific cases only (n=3 REJECT issues) — no rate; P1 and P2 never pooled.
- Residual abstention: SymPy-13974 only (n=1), not generalised.
- Central question ("evidence integrity vs sufficiency") is a hypothesis pending independent generalisation.

## Deliverables
- design/g3c0_preregistration_endpoints_sampling_stats.json
- projection/g3c0_projection_v2_spec_and_test.json
- projection/g3c0_noninterference_audit_protocol.json
- human_annotation/ (protocol, CSV template, 10 blind packets, sealed mapping)
- budget/g3c0_execution_budget_and_engineering.json
- freeze/g3c0_task1_g3b4_freeze_reverification.json
- g3c0_design_report.{json,md}
- freeze/g3c0_design_freeze_manifest.json

---
**STOPPING.** G3-C.0 is complete; awaiting separate written approval (G3-C.1) before any issue materialisation, real model call, Gemini/R2 or other paid experiment. No git commit made.
