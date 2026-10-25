# Phase 2 — Answer-Leakage Audit (T2/T3 Artifacts)

Scope: audit every path by which a Phase-1 T2 (static artifact) or T3 (agentic
tools) cell could expose the *acceptance verdict* (the ground-truth label) rather
than merely *diagnostic evidence*. No paid API calls were made for this audit; it
is a static review of the Phase-1 code plus an offline projection check in
`evidence.selfcheck`.

## 1. What the reviewer is supposed to decide

Three labels per patch:

1. `issue_addressed` — does the patch fix the reported symptom?
2. `regression_free_scoped` — do in-scope pass-to-pass tests stay green?
3. `merge_acceptable` — conjunction of (1) and (2).

The experiment must measure whether evidence is *sufficient* for those decisions.
If the evidence itself prints the answer, condition differences measure literacy,
not verification.

## 2. Leakage paths found in the Phase-1 design

### L1 — The static T2 block printed the acceptance answer directly

The Phase-1 `evidence_block` rendering included, for every artifact:

- `FAIL_TO_PASS: passed X/Y` plus the list of **failing acceptance-test ids**;
- `PASS_TO_PASS (scoped): ...` plus the list of **regressed test ids** and
  pre-existing-bad ids;
- a summary line containing `f2p_failed_ids` / `p2p_regressed_ids`.

The ground-truth label is computed in
[builder.py L266](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/builder.py#L266)
as exactly:

```python
merge_acceptable = not f2p_failed and not p2p_regressed
```

Therefore a reviewer shown the failing/regressed id lists (or even their
cardinality together with the declared set size) can emit the correct
`merge_acceptable` verdict **without inspecting patch, issue, symptom, or any
tool output**. This is direct answer leakage. Phase-1 results (T2 merge accuracy
.833, T3 .917 at n=12) are consistent with this: the task largely reduced to
reading pre-computed verdicts.

### L2 — T3 tools returned the same verdicts

`get_test_artifact` served the same record (L1 fields included).
`get_run_log("f2p"|"p2p")` served full pytest logs from which PASSED/FAILED
columns for the acceptance nodes are trivially readable. The Phase-1 T3 gain
(T2→T3 +.083) therefore cannot be cleanly attributed to *active verification*.

### L3 — Mismatch condition was trivially solvable

In the Phase-1 mismatch study the served artifact's `patch_sha256`/`base_commit`
did not match the patch under review, and `verify_artifact_linkage` returned
`linked:false`. EVSR was 1.0 (12/12), but linkage mismatch is an obvious,
flag-like signal — it does not test whether agents can detect subtler evidence
failure (stale, partial, contradictory). This motivates the Phase-2 scenarios.

### L4 — Scenario labels must never be served

Phase-2 fixtures carry a `phase2_scenario` tag. Any payload echoing it would
disclose the intended answer surface.

## 3. Controls implemented in Phase 2

Two evidence tiers, projected server-side in
[views.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/views.py):

| Content | Tier D — diagnostic | Tier A — acceptance (explicit baseline) |
|---|---|---|
| Symptom probe (pre/post patch) | yes | yes |
| Declared test sets, counts (`f2p_total`, `p2p_total`) | yes | yes |
| Per-node PASSED/FAILED outcomes, failing/regressed id lists | **withheld** | shown (Phase-1 behaviour) |
| `outcomes_withheld: true` marker | yes | no |
| Raw f2p/p2p logs via tool | served **with banner**, audited as `acceptance_log_reveal`, response header `X-Evidence-Tier-Escalation: 1` | served normally |

Additional controls:

- `views.log_allowed`: at tier D only the `symptom` log is a first-class log;
  f2p/p2p requests take the serve-and-audit escalation path, so metrics can
  distinguish verification-by-diagnostic-surface from reading the answer.
- The server **always** strips `phase2_scenario` and projects through the
  session tier before serving ([server.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/server.py));
  the tier is bound to the session, not client-supplied per request.
- Freshness/coverage/consistency tools return **booleans and counts only**:
  coverage never emits PASSED/FAILED strings; consistency returns failure
  counts, never failing test ids, at tier D.
- Tier A is retained deliberately: T2A/T3A cells are the explicit "answer
  visible" baseline that quantifies how much of the Phase-1 gain was leakage.

## 4. Offline verification

`evidence.selfcheck` (run with zero API spend) asserts:

1. a tier-D projected artifact contains none of `fail_to_pass`, per-node
   outcomes, `f2p_failed_ids`, `p2p_regressed_ids`, nor the tokens
   `FAILED`/test-id outcome strings;
2. a tier-A projection retains the verdicts (projection is not accidentally
   over-aggressive);
3. T2/T3 prompts built at tier D contain no outcome text;
4. for each Phase-2 fixture, the served payload contains neither
   `phase2_scenario` nor any outcome field;
5. tier-D f2p log responses carry the escalation header and are audit-logged.

Result: **all checks pass** (see fixture_validity.md for the run record).

## 5. Residual leakage considerations

- The symptom probe at tier D is diagnostic, but for class A patches the
  symptom passing post-patch correlates with `issue_addressed`. This is
  legitimate evidence (the reviewer could reproduce it), not a precomputed
  verdict; the contradictory fixture exists precisely because symptom-pass
  does not imply acceptance.
- Declared set sizes plus withheld outcomes do not determine verdicts.
- Model priors over issue ids are possible but the patches are real,
  unlabelled, and presented without maintainer outcomes.
