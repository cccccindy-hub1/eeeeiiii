"""Emit the 80-cell external-validation PRE-EXPERIMENT package (zero API).

This never calls a model and never fabricates results. It writes:
  experiment80/experiment80_config.json   - frozen scope, cells, budget caps
  experiment80/PRE_CALL_GATES.md          - mandatory gates before any paid call
  experiment80/RESULTS_PLACEHOLDER.json   - explicit empty-results marker

Run: -m paper_sprint.scripts.ps_make_experiment80
"""
from paper_sprint.scripts import ps_common as K

G3C1_FREEZE = "evidence_store_g3c1/freeze/g3c1_freeze_manifest.json"
G3C11_FREEZE = "evidence_store_g3c11/freeze/g3c11_freeze_manifest.json"

CONDITIONS = ["T2D-T", "T3D-Strict", "T3D-Escalate", "T2A-T", "T3A-T"]
MODELS = ["deepseek-flash", "gpt-4.1-mini"]
ISSUES = [
    ("sympy__sympy-19346", "natural", "ACCEPT"),
    ("sympy__sympy-22914", "natural", "ACCEPT"),
    ("sympy__sympy-19495", "natural", "ACCEPT"),
    ("sympy__sympy-15875", "natural", "REJECT"),
    ("sympy__sympy-19040", "enriched", "ACCEPT"),
    ("sympy__sympy-14248", "enriched", "REJECT"),
    ("sympy__sympy-19637", "enriched", "ACCEPT"),
    ("sympy__sympy-16886", "enriched", "ACCEPT"),
]


def main():
    cells = []
    for iid, cohort, og in ISSUES:
        for m in MODELS:
            for c in CONDITIONS:
                cells.append({"issue": iid, "cohort": cohort,
                              "oracle_gold": og, "model": m, "condition": c})
    n_reject = sum(1 for _, _, g in ISSUES if g == "REJECT")
    pins = {}
    for rel in (G3C1_FREEZE, G3C11_FREEZE):
        p = K.ROOT / rel
        pins[rel] = {"exists": p.exists(),
                     "sha256": K.sha256_file(p) if p.exists() else None}
    cfg = {
        "package": "G3-C.1 external validation - 80 real cells (PRE-AUTHORIZATION)",
        "status": "NOT_AUTHORIZED_NO_API",
        "api_calls_emitted_by_this_package": 0,
        "scope": {
            "issues": len(ISSUES), "conditions": len(CONDITIONS),
            "models": len(MODELS),
            "cells": len(ISSUES) * len(CONDITIONS) * len(MODELS),
            "issue_list": [{"issue": i, "cohort": q, "oracle_gold": g}
                           for i, q, g in ISSUES],
            "conditions": CONDITIONS, "models": MODELS,
            "n_oracle_reject": n_reject,
        },
        "no_expansion_rules": [
            "no new issues (exactly these 8)",
            "no new models (exactly these 2 served ids)",
            "no duplicate/re-run cells to improve results",
            "natural and enriched cohorts reported separately",
        ],
        "budget_hard_caps_usd": {
            "total": 2.00, "per_model": 1.00,
            "reference_mean_per_cell": 0.003035,
            "reference_source": "G3-B.3 observed live mean (budget planning only)",
            "enforcement": "pre-call CompositeGuard accumulator; abort before a "
                           "call that would exceed cap; failures before HTTP = $0",
        },
        "pre_call_gates_required": [
            "G3-C.0 v2 evidence protocol and P1/P2 definitions fixed and frozen",
            "80/80 offline mock cells pass (research-excluded; plumbing only)",
            "tool permission + non-interference scan clean incl. REMOVAL of the "
            "pre-patch pass_to_pass_baseline field from tier-D projection",
            "freshness 8/8; served model ids verified; wire no-fallback",
            "budget guard armed at $2.00/$1.00; resume gate skips completed cells",
            "prompt+protocol fingerprints match a pre-paid freeze",
            "independent human gold DONE, OR a fresh written authorization to run "
            "as a PROVISIONAL-GOLD EXPLORATORY PILOT",
        ],
        "research_questions": {
            "P1_primary": "restricted (T2D-T,T3D-Strict) unsupported commitment: "
                          "report P1a ACCEPT / P1b REJECT / P1c NEED per issue",
            "P2_secondary_exploratory": "sufficient-condition unsupported "
                          "acceptance on the 2 oracle-REJECT issues; n=2, "
                          "interval/case only, NOT a rate",
            "unit": "issue; cells are within-issue repeated measures",
        },
        "frozen_parent_pins": pins,
        "stopping": "hard stop at cap, at 80 cells, or on any guard/error; no "
                    "automatic continuation",
    }
    K.write_json(K.PS / "experiment80" / "experiment80_config.json", cfg)

    placeholder = {
        "status": "NO_RESULTS",
        "cells_planned": len(cells), "cells_run": 0,
        "rows": [],
        "note": "No Reviewer/Gemini/R2 API has been called for these 80 cells. "
                "Do not populate this file from predictions or mocks. It is "
                "filled only by a real, separately authorized live run.",
    }
    K.write_json(K.PS / "experiment80" / "RESULTS_PLACEHOLDER.json", placeholder)

    gates = """# G3-C.1 80-cell external validation - pre-call gates (DO NOT CALL YET)

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
"""
    K.write_text(K.PS / "experiment80" / "PRE_CALL_GATES.md", gates)
    print("config cells:", len(cells), "reject:", n_reject,
          "-> experiment80/ (config, gates, placeholder); api calls = 0")


if __name__ == "__main__":
    main()
