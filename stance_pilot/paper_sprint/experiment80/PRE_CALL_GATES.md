# G3-C.1 80-cell external validation - pre-call gates (DO NOT CALL YET)

**Status: NOT AUTHORIZED.** This package issues **zero** API calls. A live run
needs an explicit, separate written authorization after every gate below passes.

Scope (immutable once authorized): 8 issues x 5 conditions x 2 models =
**80 real cells**. 6 scoped ACCEPT / **2 REJECT** (15875 natural, 14248
enriched). Hard budget cap **$2.00 total / $1.00 per model**; pre-call guard
aborts before any over-cap request.

## Mandatory gates (all must be GREEN)
1. Protocol/definitions: G3-C.0 v2 evidence protocol and the P1/P2 definitions
   are fixed and frozen; prompt+protocol fingerprints match a pre-paid freeze.
2. Mock: 80/80 offline mock cells pass. Mock is plumbing only and is
   research-excluded; it is never reported as model performance.
3. Non-interference: restricted-surface scan is clean, AND the known residual
   **pre-patch `pass_to_pass_baseline` map is removed** from the tier-D
   projection (G3-B.4 section 6 / paper section 8.5) before any live call.
4. Freshness 8/8; served model IDs verified on the wire; no fallback.
5. Budget + resume: CompositeGuard armed at $2.00/$1.00; resume gate skips
   completed cells; any guard raise before HTTP costs $0 and is discarded.
6. Gold authority: independent human adjudication of the 18 packets (and
   FR1/FR2) is complete, OR a fresh written authorization explicitly accepts a
   **PROVISIONAL-GOLD exploratory pilot**. AI self-review never satisfies this.

## Hard rules during a (future) run
- exactly these 8 issues, these 2 models; no added issues/models/cells;
- no re-running cells to improve outcomes; first valid response is frozen;
- stop at 80 cells, at the cap, or on first unresolved guard/error;
- natural and enriched cohorts are reported separately (no pooled natural rate);
- P2 uses n=2 reject issues: report interval/cases, never a population rate.

## Primary read-out
P1 (primary): on T2D-T and T3D-Strict (condition gold NEED_EVIDENCE) report
P1a unsupported ACCEPT, P1b unsupported REJECT, P1c correct NEED per issue.
P2 (secondary, exploratory): sufficient-condition unsupported acceptance on the
two REJECT issues, with exact/Clopper-Pearson and issue-cluster intervals and an
explicit small-n caveat. Independent unit = issue.
