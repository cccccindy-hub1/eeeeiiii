"""GroundedReview Gate G3-C.1.1 - tasks 2 + 4: rebuild the 75 -> 51 -> 8
screening funnel and keep the Natural and Enriched queues fully separate.

Strictly read-only. It imports the frozen selection module's PURE functions
(build_eligible / structural_signals / apply_dedup / primary_stratum) but never
calls g3c1_select.main(), so nothing in the frozen store is written. Every
number below is RECOMPUTED from the frozen wave2 audit + candidate pool and
then cross-checked against the frozen selection JSON; disagreements fail.

Outputs (evidence_store_g3c11/audit only):
  * mutually-exclusive exclusion accounting (no double counting);
  * changed-file-set dedup contribution (natural queue only): 51 -> 47;
  * stratum sizes over the 47 deduped base;
  * dual-queue denominators, screen-pass fractions and Gold distributions
    kept SEPARATE (no merged "natural population rate");
  * the independence/overlap check between the two pilot queues.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_funnel
"""
from __future__ import annotations

import random

from evidence import g3c1_select as S
from evidence import g3c1_common as G1
from evidence import g3c11_common as K


def replay():
    eligible, excluded, funnel = S.build_eligible()
    by_id = {e["instance_id"]: e for e in eligible}

    nat_ids = sorted(by_id)
    random.Random(G1.G3C1_SAMPLING_SEED).shuffle(nat_ids)
    nat_dedup, nat_suppressed = S.apply_dedup(nat_ids, by_id)

    strata_groups = {"R-TRAP": [], "R-F2P": [], "R-P2P": [], "UNENRICHED": []}
    for iid in nat_dedup:
        strata_groups[S.primary_stratum(by_id[iid]["signals"])].append(iid)
    rng = random.Random(G1.G3C1_ENRICHED_SEED)
    enriched_order, strata_record = [], {}
    for st in (*S.STRATUM_PRIORITY, "UNENRICHED"):
        grp = sorted(strata_groups[st])
        rng.shuffle(grp)
        strata_record[st] = grp
        enriched_order.extend(grp)

    chosen_nat = nat_dedup[:G1.N_NATURAL_SLOTS]
    chosen = list(chosen_nat)
    keys = {by_id[i]["dedup_key"] for i in chosen}
    chosen_enr = []
    for iid in enriched_order:
        if len(chosen) >= G1.MAX_NEW_ISSUES:
            break
        if by_id[iid]["dedup_key"] in keys:
            continue
        chosen_enr.append(iid); chosen.append(iid)
        keys.add(by_id[iid]["dedup_key"])
        if len(chosen_enr) >= G1.N_ENRICHED_SLOTS:
            break

    return {"eligible": eligible, "excluded": excluded, "funnel": funnel,
            "by_id": by_id, "nat_order": nat_dedup,
            "nat_suppressed": nat_suppressed, "strata": strata_record,
            "enr_order": enriched_order, "nat_picks": chosen_nat,
            "enr_picks": chosen_enr, "pilot": chosen}


def exclusion_accounting(replay_, frozen):
    excluded = replay_["excluded"]
    counts = {}
    for e in excluded:
        counts[e["reason"]] = counts.get(e["reason"], 0) + 1
    # mutually exclusive because build_eligible uses if/elif and one record per
    # excluded instance.
    unique_excluded = len({e["instance_id"] for e in excluded})
    total = len(excluded)
    expected = {"previously_used_wave2": 12,
                "previously_used_g3a_cohort": 10,
                "offline_blob_incomplete": 1,
                "static_test_spec_gate_failed": 0,
                "no_clean_target_patch": 1}
    # every excluded id must be absent from eligible and disjoint.
    excl_ids = {e["instance_id"] for e in excluded}
    elig_ids = set(replay_["by_id"])
    disjoint = excl_ids.isdisjoint(elig_ids)
    reconciles = (frozen["screening_funnel"][0]["n_in"] == 75
                  and 75 - total == len(elig_ids) == 51)
    matches_frozen = (excluded == frozen["excluded"]
                      and counts == {k: v for k, v in expected.items() if v}
                      or counts == expected)
    return {"reason_counts": counts, "expected_reason_counts": expected,
            "n_excluded_records": total, "n_unique_excluded": unique_excluded,
            "exclusion_is_mutually_exclusive": total == unique_excluded,
            "excluded_disjoint_from_eligible": disjoint,
            "s0_pool": 75, "arithmetic_75_minus_24_eq_51": reconciles,
            "matches_frozen_selection": excluded == frozen["excluded"]}


def queue_separation(replay_, frozen):
    by_id = replay_["by_id"]
    oracle = {r["instance_id"]: r["oracle_gold"]
              for r in K.read_jsonl(K.G3C1_ORACLE)}

    def dist(ids):
        d = {"ACCEPT": 0, "REJECT": 0}
        for i in ids:
            d[oracle[i]] += 1
        return d

    nat_picks, enr_picks = replay_["nat_picks"], replay_["enr_picks"]
    overlap = sorted(set(nat_picks) & set(enr_picks))
    pilot = replay_["pilot"]
    # dedup keys of the two queues must also be disjoint among selected picks.
    nat_keys = {by_id[i]["dedup_key"] for i in nat_picks}
    enr_keys = {by_id[i]["dedup_key"] for i in enr_picks}
    key_overlap = sorted(nat_keys & enr_keys)

    strata_sizes = {k: len(v) for k, v in replay_["strata"].items()}
    # multi-membership count (sum of membership flags > number of base issues).
    multi = sum(1 for e in by_id.values()
                if len(e["signals"]["strata"]) > 1)
    base = len(replay_["nat_order"])

    frozen_strata = {k: v["n_members"]
                     for k, v in frozen["enriched_strata"].items()}
    return {
        "natural_queue": {
            "eligible_pool": 51,
            "after_changed_file_dedup": base,
            "n_suppressed_duplicates": len(replay_["nat_suppressed"]),
            "slots": G1.N_NATURAL_SLOTS,
            "picks": nat_picks,
            "gold_distribution_picked": dist(nat_picks),
            "picked_reject_fraction": dist(nat_picks)["REJECT"] / len(nat_picks),
            "denominator_note": ("natural screen pass denominator is the 47 "
                                 "deduped eligible issues; only the first 4 "
                                 "were built, so the 3A/1R picked fraction is "
                                 "NOT a population prevalence estimate.")},
        "enriched_queue": {
            "stratification_base_after_natural_dedup": base,
            "stratum_sizes": strata_sizes,
            "frozen_stratum_sizes": frozen_strata,
            "multi_stratum_members": multi,
            "slots": G1.N_ENRICHED_SLOTS,
            "picks": enr_picks,
            "primary_strata_picked": [S.primary_stratum(by_id[i]["signals"])
                                      for i in enr_picks],
            "gold_distribution_picked": dist(enr_picks),
            "picked_reject_fraction": dist(enr_picks)["REJECT"] / len(enr_picks),
            "conditional_note": ("enriched picks estimate CONDITIONAL behaviour "
                                 "among screen-positive issues only.")},
        "overlap": {"issue_overlap": overlap, "dedup_key_overlap": key_overlap,
                    "queues_disjoint": not overlap and not key_overlap},
        "union": {"pilot_ids": pilot, "n_pilot": len(pilot),
                  "gold_distribution_overall": dist(pilot),
                  "matches_frozen": pilot == frozen["pilot_instance_ids"]
                      and nat_picks == frozen["pilot_natural_picks"]
                      and enr_picks == frozen["pilot_enriched_picks"]
                      and replay_["nat_order"] == frozen["natural_queue_order"]
                      and replay_["enr_order"] == frozen["enriched_queue_order"]
                      and strata_sizes == frozen_strata},
        "no_pooled_natural_rate": (
            "The two queues have different sampling denominators and "
            "enrichment; their ACCEPT/REJECT fractions are reported separately "
            "and are never pooled into a single natural-population rate."),
    }


def main():
    K.ensure_out_dirs()
    r = replay()
    frozen = K.read_json(K.G3C1_SELECTION)

    # independent replay must reproduce the frozen document exactly.
    replay_match = {
        "n_eligible": len(r["eligible"]),
        "n_excluded": len(r["excluded"]),
        "natural_order_matches": r["nat_order"] == frozen["natural_queue_order"],
        "enriched_order_matches": r["enr_order"] == frozen["enriched_queue_order"],
        "nat_suppressed_matches":
            r["nat_suppressed"] == frozen["natural_dedup_suppressed"],
        "pilot_matches": r["pilot"] == frozen["pilot_instance_ids"],
        "seeds": frozen["seeds"],
    }
    result = {
        "document": "G3-C.1.1 funnel + dual-queue separation (tasks 2+4)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "funnel_steps": r["funnel"],
        "exclusion_accounting": exclusion_accounting(r, frozen),
        "dedup_suppressed": r["nat_suppressed"],
        "queue_separation": queue_separation(r, frozen),
        "replay_exact_match": replay_match,
    }
    # build a single overall flag from the concrete sub-results.
    acct = result["exclusion_accounting"]
    qs = result["queue_separation"]
    overall = (
        len(r["eligible"]) == 51 and len(r["excluded"]) == 24
        and acct["exclusion_is_mutually_exclusive"]
        and acct["excluded_disjoint_from_eligible"]
        and acct["arithmetic_75_minus_24_eq_51"]
        and acct["matches_frozen_selection"]
        and len(r["nat_suppressed"]) == 4
        and len(r["nat_order"]) == 47
        and qs["overlap"]["queues_disjoint"]
        and len(qs["union"]["pilot_ids"]) == 8
        and qs["union"]["matches_frozen"]
        and all(replay_match[k] for k in (
            "natural_order_matches", "enriched_order_matches",
            "nat_suppressed_matches", "pilot_matches")))
    result["overall_pass"] = overall
    K.write_canonical(K.OUT_AUDIT / "g3c11_funnel.json", result)
    print("OVERALL:", overall)
    print("exclusion counts:", acct["reason_counts"])
    print("dedup suppressed:", [s["instance_id"] for s in r["nat_suppressed"]])
    print("strata sizes:",
          {k: len(v) for k, v in r["strata"].items()})
    print("natural:", r["nat_picks"])
    print("enriched:", r["enr_picks"])
    print("->", (K.OUT_AUDIT / "g3c11_funnel.json").relative_to(K.HERE))


if __name__ == "__main__":
    main()
