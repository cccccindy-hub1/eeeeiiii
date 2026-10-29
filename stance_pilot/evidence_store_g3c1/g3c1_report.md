# GroundedReview Gate G3-C.1 - Local Zero-API Pilot Freeze

**Scope.** Under the prior written approval, **8 brand-new independent SymPy issues** were built with real local data extraction, patch replay and pytest execution, signed gold, a real local HTTP cross-check and an offline mock. Model API budget **$0**; no real Reviewer call, Gemini, R2, G3-C.2 or git commit. G3-C.0 was not re-run and every historical frozen artifact stayed read-only.

## 1. Eight new issues (real executed evidence)

| issue | queue | stratum | generator | class | resolved | F2P fail/tot | P2P reg/tot (pre-bad) | oracle |
|---|---|---|---|---|---|---|---|---|
| sympy-14248 | enriched | R-P2P | glm5_500 | A | False | 1/2 | 2/433 (1) | **REJECT** |
| sympy-15875 | natural | R-P2P | qwen3_30b_instruct2507_500 | A | False | 1/1 | 0/80 (0) | **REJECT** |
| sympy-16886 | enriched | R-P2P | glm5_500 | B | True | 0/1 | 0/42 (0) | **ACCEPT** |
| sympy-19040 | enriched | R-TRAP | glm5_500 | B | True | 0/1 | 0/148 (0) | **ACCEPT** |
| sympy-19346 | natural | R-P2P | glm5_500 | B | True | 0/1 | 0/40 (0) | **ACCEPT** |
| sympy-19495 | natural | R-TRAP | glm5_500 | B | True | 0/1 | 0/8 (0) | **ACCEPT** |
| sympy-19637 | enriched | R-P2P | glm5_500 | B | True | 0/1 | 0/40 (0) | **ACCEPT** |
| sympy-22914 | natural | R-F2P | glm5_500 | B | True | 0/1 | 0/17 (0) | **ACCEPT** |

Oracle distribution: **2 REJECT / 6 ACCEPT** (NEED_EVIDENCE 0). Both REJECTs (sympy-14248, sympy-15875) are `resolved_in_dataset=False` candidates that fail a declared check; they were kept and honestly labelled, never swapped to manufacture an ACCEPT.

## 2. Frozen dual-queue screening funnel

- S0_pool_instances — locally cached wave2 candidate pool (frozen audit) (in=75, out=75, removed=)
- S1_exclude_wave2_consumed — 12 pre-G3A issues (in=, out=, removed=12)
- S2_exclude_g3a_cohort — 10 G3-A materialised issues (in=, out=, removed=10)
- S3_exclude_offline_incomplete — sympy-11618 blobs (in=, out=, removed=1)
- S4_static_test_spec_gates — all six frozen wave2 gates must pass (in=, out=, removed=0)
- S5_no_clean_target_patch — >=1 clean-apply generator row required (in=, out=, removed=1)
- S6_eligible — G3-C.1 eligible pool (expect 51) (in=, out=51, removed=)

Eligible pool: **51** (excluded 24: {'offline_blob_incomplete': 1, 'no_clean_target_patch': 1, 'previously_used_wave2': 12, 'previously_used_g3a_cohort': 10}). Natural shuffle seed 418237; enriched strata seed 418241. Independence = one issue per repo+sha256(sorted changed-file set); 4 duplicate-cluster members were suppressed in the natural queue.

- **Natural queue (first 4):** 1 REJECT / 3 ACCEPT (descriptive only; n=4, no population-rate claim).
- **REJECT-enriched queue (first 4):** 1 REJECT / 3 ACCEPT. This is a **screen-positive, conditional** sample and its rate **must not** be presented as the natural-population prevalence.
- Enriched stratum sizes across the 51 eligible: {'R-F2P': 16, 'R-P2P': 29, 'R-TRAP': 2, 'UNENRICHED': 0}.

## 3. Freshness, coverage and gold quality

- Independent git write-tree restage: **8/8 tree match**, 8/8 attestation authentic, all_match=True (independent_git_restage_write_tree); G3-B.2 three-state (TRUE/FALSE/UNKNOWN); a missing run tree is never silently treated as stale.
- Coverage disclosure: PASS_TO_PASS was executed only for the attested SCOPED subset (maintainer test_patch files plus tests/ adjacent to changed code files). The full dataset P2P suite was NOT run locally; therefore every oracle ACCEPT here means SCOPED acceptability, not full-suite merge certification.
- Condition gold over 8 issues x 5 conditions = **40 certificates**: sufficient=24, NEED_EVIDENCE=16.
- Per-condition distribution: {"T2D-T": {"NEED_EVIDENCE": 8}, "T3D-Strict": {"NEED_EVIDENCE": 8}, "T3D-Escalate": {"REJECT": 2, "ACCEPT": 6}, "T2A-T": {"REJECT": 2, "ACCEPT": 6}, "T3A-T": {"REJECT": 2, "ACCEPT": 6}} (restricted tier-D T2D-T/T3D-Strict are NEED_EVIDENCE by design; T3D-Escalate and tier-A T2A-T/T3A-T resolve to the oracle label).

## 4. Non-interference, real local HTTP cross-check, mock

- Non-interference on actually served surfaces: 224 surfaces (144 restricted tier-D); tier1/tier2/schema-lint/gold-key findings all **0**; passed=True.
- Real local HTTP cross-check (EvidenceAPI/g3c1-v1, 127.0.0.1 only): **40 cells, 456/456 checks pass, 0 errors.**
- Zero-API mock: 40/40 cells reproduce condition gold (rate 1.0), api_calls=0, cost=$0; research-excluded plumbing check only.

## 5. Second-human blind arbitration package (PROVISIONAL)

- **8 blind packets** (P01-P08), each 9 files, blind seed 418307; status **PENDING — no independent human labels obtained**.
- Identity blinding is PARTIAL: 8/8 verbatim symptom logs self-quote the upstream issue number; evidence is not rewritten and the limitation is logged.
- All gold remains PROVISIONAL (annotators=1, annotator2=NOT_OBTAINED) until a real second annotator labels the sealed packet and third-human arbitration completes.

## 6. Failure record retained (no skip)

- 1 stop record in g3c1_failures.jsonl (sympy-19495 probe-flip gate). The first hand-written probe was a faulty INSTRUMENT (weak assertions that passed at baseline); the issue genuinely reproduced and the patch genuinely fixed it. The probe was strengthened using ONLY the public issue report (maintainer test_patch never consulted), after which all 8 probes flipped. The issue was kept, no gold changed. See audit/g3c1_probe_revision_note_19495.json.

## 7. Determinism and freeze

- Re-executed g3c1_select + g3c1_gold from frozen inputs: 3/3 products byte-identical (deterministic=True); audit/g3c1_determinism_check.json.
- Every file under evidence_store_g3c1/ is sha256-hashed in freeze/g3c1_freeze_manifest.json (canonical digest over the sorted file list), which pins the G3-C.0 design and G3-B.4/G3-B.3 result freezes; the manifest excludes itself.

## 8. G3-C.2 recommendation

Do **not** unlock paid Reviewer expansion yet. First collect a real independent second-human labelling of the 8 sealed packets, run third-human arbitration + gold-flip sensitivity, re-confirm the machine non-interference gate on the G3-C.2 build, and obtain a separate written G3-C.2 approval with the G3-C.0 pre-registered P1/P2 endpoints, >=20-new-REJECT sampling floor and hard per-phase budget. Natural and enriched rates must stay separated.

---

G3-C.1 is complete: 8 new independent SymPy issues were built, executed, gold-certified, non-interference-audited, HTTP cross-checked and zero-API-mocked, then hash frozen. Stopping now. G3-C.0 was NOT re-run; no historical frozen artifact was modified; no real model call, Gemini, R2 or G3-C.2 cell was run; API spend $0; no git commit was made. Awaiting separate written approval for G3-C.2.
