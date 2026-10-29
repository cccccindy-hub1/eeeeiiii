"""GroundedReview Gate G3-C.1.1 - task 12: updated Go / No-Go decision package
for the (separately approvable) Gate G3-C.2 real expansion.

Zero API. It only RECOMMENDS; it does not execute, fetch, call a model, write
R2 or commit. The recommendation is NO-GO pending the listed preconditions, the
hardest of which is a sampling-capability shortfall in R-TRAP (2 available vs
the pre-registered >=6) and 18/18 gold still PROVISIONAL with no second human.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_gate3c2_decision
"""
from __future__ import annotations

from evidence import g3c11_common as K

# pre-registered floor per R-stratum (G3-C.0 sampling plan)
PREREG_FLOOR = {"R-F2P": 7, "R-P2P": 7, "R-TRAP": 6}
# actually sampleable counts in the 47-issue de-duplicated eligible pool
POOL_AVAILABLE = {"R-TRAP": 2, "R-P2P": 29, "R-F2P": 16, "UNENRICHED": 0}


def load_evidence():
    verify = K.read_json(K.OUT_AUDIT / "g3c11_verification.json")
    funnel = K.read_json(K.OUT_AUDIT / "g3c11_funnel.json")
    prio = K.read_json(K.OUT_AUDIT / "g3c11_priority_audit.json")
    issue = K.read_json(K.OUT_AUDIT / "g3c11_issue_audit.json")
    human = K.read_json(K.OUT_HUMAN / "g3c11_second_annotator_plan.json")
    sens = K.read_json(K.OUT_AUDIT / "g3c11_sensitivity.json")
    budget = K.read_json(K.G3C0_BUDGET)
    prereg = K.read_json(K.G3C0_PREREG)
    return locals()


def stratum_feasibility():
    rows = []
    for s, floor in PREREG_FLOOR.items():
        avail = POOL_AVAILABLE.get(s, 0)
        rows.append({
            "stratum": s,
            "preregistered_floor": floor,
            "sampleable_in_dedup_pool_n": avail,
            "shortfall": max(0, floor - avail),
            "meets_floor_from_current_pool": avail >= floor,
        })
    rows.append({"stratum": "UNENRICHED", "preregistered_floor": 0,
                 "sampleable_in_dedup_pool_n": 0, "shortfall": 0,
                 "meets_floor_from_current_pool": True,
                 "note": "no unenriched member beyond natural first-4"})
    return rows


def main():
    K.ensure_out_dirs()
    E = load_evidence()
    feas = stratum_feasibility()
    trap = next(r for r in feas if r["stratum"] == "R-TRAP")

    preconditions = [
        {
            "id": "PC1_independent_gold_review",
            "requirement": ("A real, independent annotator-2 labels all 18 "
                "blind packets (10 G3-A + 8 G3-C.1) and a third senior human "
                "adjudicates disagreements; only then is a new Gold "
                "Adjudication Version produced and gold raised above "
                "PROVISIONAL. The same independent human must also answer the "
                "two approver-mandated focused reviews: FR1 sympy-19495 probe "
                "(instrument-only fix vs post-hoc oracle redefinition) and "
                "FR2 (14248 vs 15875 share one uniform disjunctive REJECT "
                "standard)."),
            "current_state": "NOT MET - annotator2 NOT_OBTAINED, 18/18 "
                             "PROVISIONAL/PENDING, FR1/FR2 PENDING, zero AI "
                             "labels allowed.",
            "blocks_release": True,
        },
        {
            "id": "PC2_sampling_rule_trustworthiness",
            "requirement": ("Either (a) amend the pre-registration in writing "
                "to lock the TRAP>P2P>F2P multi-member tie/connection order as "
                "the operative rule, disclosing it is a pilot-stage pre-data "
                "operational refinement rather than verbatim G3-C.0 text; or "
                "(b) re-run the design under the literal G3-C.0 enumeration."),
            "current_state": ("PARTIALLY MET - rule predates first outcome by "
                "~28 min (pre-data, not post-outcome adaptive) and replay is "
                "byte-identical, but the order was not fixed verbatim in "
                "G3-C.0; counterfactual F2P-first would move 29 strata and "
                "pick 4 different issues."),
            "blocks_release": True,
        },
        {
            "id": "PC3_R_TRAP_sampleability",
            "requirement": ("Secure >=6 R-TRAP independent negatives per the "
                "pre-registered floor (the 17318/17630/19783 anchors are "
                "held-out and do not count toward NEW issues)."),
            "current_state": ("NOT MET - de-duplicated 47-issue pool contains "
                "only %d R-TRAP; shortfall %d. Requires additional eligible "
                "candidate material, which needs data collection this gate "
                "does not authorise." % (trap["sampleable_in_dedup_pool_n"],
                                         trap["shortfall"])),
            "blocks_release": True,
        },
        {
            "id": "PC4_restricted_evidence_samples",
            "requirement": ("Decide whether additional REAL restricted "
                "(tier-D) evidence samples are needed for P1 beyond what the "
                "current pool can supply, and pre-register the fraction/"
                "filter/stratum sizes before any call."),
            "current_state": ("OPEN - pilot provides 8 structural NEED cells "
                "per restricted condition with no model numerators; P1 is not "
                "estimable yet."),
            "blocks_release": False,
        },
        {
            "id": "PC5_budget_and_stop_rules",
            "requirement": ("Recompute mean/max cell cost from the pilot "
                "before B1, re-approve hard pre-call caps, and keep the frozen "
                "stopping rules (budget guard, drift, non-interference, "
                "abort-investigate, no expansion without written approval)."),
            "current_state": ("FROZEN FROM G3-C.0 - figures are planning "
                "estimates only and must be refreshed from real pilot spend."),
            "blocks_release": False,
        },
        {
            "id": "PC6_instrument_blind_spots",
            "requirement": ("Resolve/record the undeclared collateral failing "
                "nodes found in executed scope files (15875: 2 candidate-era "
                "undeclared; 19346: 1 baseline-unmapped) so scoped P2P "
                "coverage claims are explicit, and keep full-dataset P2P "
                "non-execution disclosed."),
            "current_state": ("DISCLOSED IN AUDIT - does not alter frozen "
                "gold but must be carried into the G3-C.2 coverage "
                "disclosure."),
            "blocks_release": False,
        },
    ]

    plan = E["budget"]["task9_execution_and_budget_plan"]
    phases = {p["phase"]: {
        "issues": p["issues"], "estimated_cells": p["estimated_cells"],
        "expected_cost_usd": p["expected_cost_at_observed_mean_usd"],
        "worst_case_usd":
            p["worst_case_cost_if_every_cell_hits_observed_max_usd"],
        "hard_pre_call_cap_usd": p["hard_pre_call_cap_usd"]}
        for p in plan["phases"]}

    blocking = [p["id"] for p in preconditions if p["blocks_release"]
                and p["current_state"].startswith(("NOT MET",))]

    result = {
        "document": "G3-C.1.1 updated Gate G3-C.2 Go/No-Go decision package "
                    "(task 12)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "recommendation": "NO-GO (do not release G3-C.2 real expansion yet)",
        "recommendation_basis": ("Three blocking preconditions are unmet: "
            "no independent gold adjudication (18/18 PROVISIONAL), the "
            "stratum connection order is a disclosed pilot-stage refinement "
            "not verbatim pre-registered, and the pool supplies only 2 of "
            "the required >=6 R-TRAP issues. The zero-API integrity checks "
            "themselves pass (185-file verify, byte-identical funnel replay, "
            "log re-parse match), so the blocks are about human authority and "
            "sampling capability, not data corruption."),
        "blocking_precondition_ids": ["PC1", "PC2", "PC3"],
        "evidence_integrity_inputs": {
            "verification_overall": E["verify"].get("overall_pass"),
            "funnel_matches_frozen_selection":
                E["funnel"]["replay_exact_match"].get("pilot_matches"),
            "priority_rule_predates_first_outcome":
                E["prio"].get("rule_predates_first_outcome"),
            "priority_classification_verdict": E["prio"].get("verdict"),
            "issue_recomputation_all_match":
                E["issue"].get("all_independent_recomputations_match"),
        },
        "preconditions": preconditions,
        "stratum_sampleability": {
            "dedup_eligible_pool_n": 47,
            "rows": feas,
            "hard_gap": "R-TRAP 2 < floor 6",
            "other_strata": "R-P2P 29 and R-F2P 16 exceed their floors (>=7)",
        },
        "independent_gold_status": {
            "packets": E["human"]["packets_total"],
            "annotator2_obtained": E["human"]["annotator2_obtained"],
            "ai_labels_produced": E["human"]["labels_produced_by_ai"],
            "all_gold_tier": E["human"]["all_gold_tier"],
        },
        "additional_real_restricted_evidence_needed": (
            "Undecided (PC4); cannot be answered without the approved "
            "sampling amendment and the R-TRAP sourcing decision."),
        "projected_scale_if_approved": {
            "phases_planning_only": phases,
            "totals": {
                "estimated_cells": plan["totals_estimated_cells"],
                "expected_cost_usd": plan["totals_expected_cost_usd"],
                "worst_case_usd":
                    plan["totals_worst_case_observed_max_usd"]},
            "new_reject_floor": plan["planning_assumptions"]["new_reject_floor"],
            "preferred_n": E["prereg"]["task5_analysis_plan"][
                "precision_and_power"]["preferred_n"],
            "minimum_usable_n": E["prereg"]["task5_analysis_plan"][
                "precision_and_power"]["minimum_usable_n"],
            "caveat": "planning figures, not commitments; recompute pre-B1",
        },
        "stopping_rules_carried_from_g3c0": plan["stopping_rules"],
        "expected_outcome_if_all_pcs_met": (
            "A later, SEPARATELY written approval may release G3-C.2; nothing "
            "in this gate executes it."),
        "approved_scope": K.APPROVED_SCOPE,
    }
    K.write_canonical(K.OUT_AUDIT / "g3c11_gate3c2_decision.json", result)
    print("recommendation:", result["recommendation"])
    print("blocking:", result["blocking_precondition_ids"])
    print("R-TRAP:", trap["sampleable_in_dedup_pool_n"], "< floor",
          trap["preregistered_floor"])
    print("->", (K.OUT_AUDIT / "g3c11_gate3c2_decision.json")
          .relative_to(K.HERE))


if __name__ == "__main__":
    main()
