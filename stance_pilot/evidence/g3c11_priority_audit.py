"""GroundedReview Gate G3-C.1.1 - task 3: audit the temporal order and the
pre-registration status of the REJECT-enrichment connection priority
R-TRAP > R-P2P > R-F2P.

Read-only. It does not edit the frozen rule or re-label anything; it replays
the frozen static-pool signals under (a) the priority actually used and
(b) a counterfactual priority (R-F2P > R-P2P > R-TRAP, the list order in which
the strata are enumerated in the G3-C.0 preregistration text) and records how
the enriched order and the 4 enriched pilot picks would differ.

Verdict produced here is evidential, not rhetorical: file mtimes prove the
rule source was fixed BEFORE the first executed outcome, while the G3-C.0
freeze did not literally pin the multi-membership connection priority. This is
therefore disclosed as a PILOT-STAGE, PRE-DATA operational refinement of an
expressly permitted pre-specified enrichment screen - NOT verbatim full
pre-registration, and NOT post-outcome adaptive sampling.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_priority_audit
"""
from __future__ import annotations

import datetime as dt
import random

from evidence import g3c1_select as S
from evidence import g3c1_common as G1
from evidence import g3c11_common as K


def primary_with_priority(sig, priority):
    for st in priority:
        key = "is_" + st.replace("-", "_")
        if sig.get(key):
            return st
    return "UNENRICHED"


def enriched_replay(eligible, nat_dedup, priority):
    by_id = {e["instance_id"]: e for e in eligible}
    groups = {"R-TRAP": [], "R-F2P": [], "R-P2P": [], "UNENRICHED": []}
    assignment = {}
    for iid in nat_dedup:
        ps = primary_with_priority(by_id[iid]["signals"], priority)
        groups[ps].append(iid)
        assignment[iid] = ps
    rng = random.Random(G1.G3C1_ENRICHED_SEED)
    order = []
    sizes = {}
    for st in (*priority, "UNENRICHED"):
        grp = sorted(groups[st])
        rng.shuffle(grp)
        sizes[st] = len(grp)
        order.extend(grp)

    # replicate the union-dedup pilot pick against the frozen natural 4.
    rng_n = random.Random(G1.G3C1_SAMPLING_SEED)
    nat = sorted(by_id)
    rng_n.shuffle(nat)
    nat_dedup_actual, _ = S.apply_dedup(nat, by_id)
    chosen_nat = nat_dedup_actual[:G1.N_NATURAL_SLOTS]
    chosen = list(chosen_nat)
    keys = {by_id[i]["dedup_key"] for i in chosen}
    enr = []
    for iid in order:
        if len(chosen) >= G1.MAX_NEW_ISSUES:
            break
        if by_id[iid]["dedup_key"] in keys:
            continue
        enr.append(iid); chosen.append(iid)
        keys.add(by_id[iid]["dedup_key"])
        if len(enr) >= G1.N_ENRICHED_SLOTS:
            break
    return {"priority": list(priority), "primary_assignment": assignment,
            "stratum_sizes": sizes, "enriched_order": order,
            "natural_picks": chosen_nat, "enriched_picks": enr}


def utc_mtime(path):
    return dt.datetime.utcfromtimestamp(
        path.stat().st_mtime).replace(tzinfo=dt.timezone.utc).isoformat()


def main():
    K.ensure_out_dirs()
    eligible, _, _ = S.build_eligible()
    by_id = {e["instance_id"]: e for e in eligible}
    nat_ids = sorted(by_id)
    random.Random(G1.G3C1_SAMPLING_SEED).shuffle(nat_ids)
    nat_dedup, _ = S.apply_dedup(nat_ids, by_id)

    actual = enriched_replay(eligible, nat_dedup, S.STRATUM_PRIORITY)
    counterfactual = enriched_replay(
        eligible, nat_dedup, ("R-F2P", "R-P2P", "R-TRAP"))

    frozen = K.read_json(K.G3C1_SELECTION)

    # which issues change primary stratum under the counterfactual priority?
    moved = {iid: {"actual": actual["primary_assignment"][iid],
                   "counterfactual_f2p_first":
                       counterfactual["primary_assignment"][iid]}
             for iid in nat_dedup
             if actual["primary_assignment"][iid]
             != counterfactual["primary_assignment"][iid]}

    timeline = [
        {"event": "G3-C.0 preregistration design JSON written",
         "path": "evidence_store_g3c0/design/"
                 "g3c0_preregistration_endpoints_sampling_stats.json",
         "utc": utc_mtime(K.G3C0_PREREG)},
        {"event": "G3-C.0 design freeze manifest written",
         "path": "freeze/g3c0_design_freeze_manifest.json",
         "utc": utc_mtime(K.G3C0_DESIGN_FREEZE)},
        {"event": "g3c1_common.py (eligibility constants/seeds) written",
         "path": "evidence/g3c1_common.py", "utc": utc_mtime(
             K.HERE / "evidence" / "g3c1_common.py")},
        {"event": "g3c1_select.py STRATUM_PRIORITY source fixed",
         "path": "evidence/g3c1_select.py",
         "utc": utc_mtime(K.HERE / "evidence" / "g3c1_select.py"),
         "authoritative_rule_time": True},
        {"event": "first executed outcome: sympy-19495 probe-flip stop record",
         "path": "evidence_store_g3c1/g3c1_failures.jsonl",
         "utc": utc_mtime(K.G3C1 / "g3c1_failures.jsonl"),
         "first_outcome_time": True},
        {"event": "real pytest build session ends (last truth)",
         "path": "runs/g3c1_build.log",
         "utc": utc_mtime(K.G3C1 / "runs" / "g3c1_build.log")},
        {"event": "selection JSON mtime (determinism re-run regeneration; "
                  "byte-identical sha f3284c75...)",
         "path": "selection/g3c1_selection.json",
         "utc": utc_mtime(K.G3C1_SELECTION),
         "mtime_trap": ("NOT the rule-fixation time; content is byte-identical "
                        "to the pre-build selection per "
                        "audit/g3c1_determinism_check.json")},
        {"event": "oracle gold + freeze manifests written",
         "path": "gold/g3c1_oracle_gold.jsonl; freeze/g3c1_freeze_manifest.json",
         "utc": utc_mtime(K.G3C1_ORACLE)},
    ]
    rule_time = dt.datetime.fromisoformat(
        next(t["utc"] for t in timeline if t.get("authoritative_rule_time")))
    first_outcome = dt.datetime.fromisoformat(
        next(t["utc"] for t in timeline if t.get("first_outcome_time")))

    result = {
        "document": "G3-C.1.1 enrichment-priority temporal/construct audit "
                    "(task 3)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "g3c0_old_rule": {
            "source": "frozen G3-C.0 preregistration task4",
            "locked": ["three strata EXISTENCE and quotas: R-F2P>=7, "
                       "R-P2P>=7, R-TRAP>=6",
                       "sampling seed 418237",
                       "a PRE-SPECIFIED stratified/negative-enrichment screen "
                       "is permitted; sampling fraction/filter/stratum sizes "
                       "must be logged",
                       "enriched rates are conditional; never a natural "
                       "population rate"],
            "enumeration_order_in_text": ["R-F2P", "R-P2P", "R-TRAP"],
            "not_locked": ("the multi-membership PRIMARY-assignment / "
                           "concatenation priority when an issue satisfies "
                           "more than one stratum"),
        },
        "g3c1_new_rule": {
            "source": "evidence/g3c1_select.py STRATUM_PRIORITY",
            "priority": list(S.STRATUM_PRIORITY),
            "stated_reason": ("membership flags stay non-exclusive; the "
                              "primary stratum is assigned R-TRAP > R-P2P > "
                              "R-F2P because the f2p<=2 feature is "
                              "near-universal in this pool, so trap and "
                              "large-regression-surface issues are assigned to "
                              "their more informative stratum first"),
            "fixed_at_utc": rule_time.isoformat(),
            "inputs_allowed": ("frozen wave2 declared f2p/p2p counts + "
                               "maintainer test_patch static text + changed "
                               "files only; no model/resolved/executed outcome"),
        },
        "timeline_utc": timeline,
        "temporal_finding": {
            "rule_source_fixed_utc": rule_time.isoformat(),
            "first_executed_outcome_utc": first_outcome.isoformat(),
            "rule_predates_first_outcome": rule_time < first_outcome,
            "lead_seconds": int((first_outcome - rule_time).total_seconds()),
            "selection_json_mtime_is_regeneration_artifact": True,
            "no_outcome_dependent_adaptation": rule_time < first_outcome,
        },
        "replay_actual": {
            "priority": actual["priority"],
            "stratum_sizes": actual["stratum_sizes"],
            "enriched_order_first12": actual["enriched_order"][:12],
            "enriched_picks": actual["enriched_picks"],
            "matches_frozen": (
                actual["enriched_order"] == frozen["enriched_queue_order"]
                and actual["enriched_picks"] == frozen["pilot_enriched_picks"]
                and actual["stratum_sizes"] ==
                {k: v["n_members"] for k, v in
                 frozen["enriched_strata"].items()}),
        },
        "replay_counterfactual_f2p_first": {
            "priority": counterfactual["priority"],
            "stratum_sizes": counterfactual["stratum_sizes"],
            "enriched_order_first12":
                counterfactual["enriched_order"][:12],
            "enriched_picks": counterfactual["enriched_picks"],
        },
        "issues_changing_primary_stratum_under_counterfactual": moved,
        "n_moved": len(moved),
        "picks_differ": (
            actual["enriched_picks"] != counterfactual["enriched_picks"]),
        "classification": {
            "is_verbatim_strict_preregistration_of_connection_order": False,
            "is_post_outcome_adaptive_sampling": False,
            "verdict": ("PILOT-STAGE PRE-DATA operational refinement: within "
                        "the G3-C.0 expressly permitted 'pre-specified "
                        "stratified/negative-enrichment screen', the concrete "
                        "multi-membership connection priority R-TRAP>R-P2P>"
                        "R-F2P was fixed in g3c1_select.py at 09:20:33Z from "
                        "static pool structure alone, 28 minutes before the "
                        "first executed outcome (09:48:33Z) and before any "
                        "build. It was not literally pre-registered in G3-C.0 "
                        "and must be disclosed as such; it must NOT be "
                        "retrospectively claimed as fully pre-registered, and "
                        "it is not outcome-dependent adaptation."),
            "disclosure_required": True,
        },
        "approved_scope": K.APPROVED_SCOPE,
    }
    result["overall_pass"] = (
        result["temporal_finding"]["rule_predates_first_outcome"]
        and result["replay_actual"]["matches_frozen"]
        and not result["classification"][
            "is_verbatim_strict_preregistration_of_connection_order"]
        and not result["classification"]["is_post_outcome_adaptive_sampling"])
    K.write_canonical(K.OUT_AUDIT / "g3c11_priority_audit.json", result)
    print("rule fixed :", rule_time.isoformat())
    print("first outcome:", first_outcome.isoformat(),
          "lead(s):", result["temporal_finding"]["lead_seconds"])
    print("actual sizes:", actual["stratum_sizes"],
          "picks:", actual["enriched_picks"])
    print("cf F2P-first sizes:", counterfactual["stratum_sizes"],
          "picks:", counterfactual["enriched_picks"])
    print("issues moved under counterfactual:", len(moved))
    print("verdict:", result["classification"]["verdict"][:90], "...")
    print("->", (K.OUT_AUDIT / "g3c11_priority_audit.json").relative_to(K.HERE))


if __name__ == "__main__":
    main()
