# Gate 3-B.1 — Gold Sensitivity Changelog (construct-validity, zero API)

Status: **analytical versions only.** Nothing in this file relabels an issue,
rewrites gold, or touches the frozen Gate 3-B artifacts. The on-disk frozen
gold remains **V1**. V2/V3 are hypothetical re-projections used solely to
quantify how the finding changes if the T3 instrument's literal
`fresh = false` were treated as ground truth by the gold rule.

Frozen sources (read-only):
- Oracle gold: `evidence_store_g3a/gold/g3a_gold.jsonl` (10 rows)
- Condition gold: `evidence_store_g3a/gold/g3a1_condition_gold.jsonl` (10 rows)
- Frozen rule: `evidence/gold_w2.py` (oracle requires `linked AND fresh` for
  both ACCEPT success and REJECT acceptance-failure; symptom persistence is a
  separate REJECT channel).

Machine-readable tables:
`evidence_store_g3b1/audit/g3b1_independent_audit.json` →
`task4_gold_sensitivity.versions` and `.rescore_EscT3A`.

## 1. The construct conflict that motivates the sensitivity versions

Two components that the sufficient-condition gold depends on adjudicate
channel F (freshness) differently, for a structural rather than evidential
reason:

- **Gold side.** `fresh = att_ok and linked`. Tree identity is established by
  an independent `git write-tree` restage; all 10 issues are `fresh = true`.
  Independent recomputation (`g3a_freshness_recompute.json`) shows the restaged
  tree equals the attested expected tree for all 10, signatures authenticate,
  and the runs executed 2026-10-25 (started 18:40 / finished 18:43).
- **Live T3 tool endpoint.** `tree_match = rec.run_tree == att.expected_run_tree`.
  The canonical record **structurally has no `run_tree` field**
  (`'run_tree' in rec == False` on 17318, and all 10), so the comparison is
  `null == <hash> → false`, and the endpoint returns
  `fresh=false / record_run_tree=null` on **all 60 active cells**.

Therefore `fresh=false` is neither a stale timestamp nor a genuine tree
mismatch; it is a contradiction between the gold rule (which does not read
`record.run_tree`) and the live instrument (which does, against a missing
field). This is why a sensitivity analysis is required before any
"over-abstention under sufficient evidence" claim can be interpreted.

## 2. Versions

Identical across versions: T2A-T (static; channel F is never adjudicated) and
the two restricted conditions (T2D-T, T3D-Strict) are held equal to V1.
Only T3D-Escalate and T3A-T are re-projected, because only they expose the
freshness tool that emits the structural false.

- **V1 (frozen).** Freshness as attested/restaged → all 10 issues fresh.
  Esc/T3A condition gold = oracle: 7 ACCEPT, 3 REJECT.
- **V2 (tool-literal fresh=false; frozen rule).** Feed the instrument's
  `fresh=false` into the unchanged frozen rule. A non-fresh run supports
  neither ACCEPT success nor a REJECT acceptance-failure. All 10 issues'
  symptom is *gone* (the 3 REJECT issues are rejected on acceptance failures,
  not a persisted symptom), so **all 10 Esc and all 10 T3A cells collapse to
  NEED_EVIDENCE**.
- **V3 (decisive linked failure survives staleness).** Same as V2 except a
  linked, decisive acceptance failure still justifies REJECT even if stale.
  The **3 REJECT issues stay REJECT**; the **7 ACCEPT issues become
  NEED_EVIDENCE** (Esc and T3A alike).

Condition-gold counts (Esc; T3A identical):

| Version | ACCEPT | REJECT | NEED_EVIDENCE |
|---|---|---|---|
| V1 frozen | 7 | 3 | 0 |
| V2 tool-literal | 0 | 0 | 10 |
| V3 failure-survives | 0 | 3 | 7 |

## 3. Re-scoring the two phenomena under each version (Esc + T3A only)

| Model | V1 over-abstain cells | V2 | V3 | V1 unsupported ACCEPT | V2 | V3 |
|---|---|---|---|---|---|---|
| deepseek-flash | 13 | 0 | 0 | 0 | 0 | 0 |
| gpt-4.1-mini | 14 | 0 | 0 | 0 | 0 | 0 |

Interpretation:
- Under V2 the Esc/T3A gold is *itself* NEED_EVIDENCE, so abstention is gold-
  correct and "over-abstention under sufficient evidence" vanishes by
  construction. The C2 result would then be wholly a T2A phenomenon.
- Under V3 the 3 REJECT issues retain a decisive-failure REJECT. DeepSeek's
  abstention on 17630 (T3A) — where it obtained `contradicted` and read the
  failing f2p log but abstained citing the stale-run rule — would re-emerge as
  a genuine error under V3, because V3 keeps that failure decisive. The 7
  ACCEPT issues still yield NEED_EVIDENCE, so the bulk of the abstention
  remains instrument-explained.
- No version introduces an unsupported ACCEPT in Esc/T3A; the single C1 event
  (GPT on 17318) occurs only under T2A-T, which all versions hold fixed.

## 4. Decision on the frozen gold

V1 is **not modified**. The audit does not claim V2 or V3 is the "correct"
gold; they bracket the construct. The substantive recommendation (report
task 11) is to repair the F channel before Gate 3-C — make the canonical
record carry the true `run_tree`, or make the endpoint use the restaged tree —
so that a future frozen gold and the live instrument adjudicate freshness
identically, eliminating the need for these sensitivity versions.
