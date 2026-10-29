"""GroundedReview Gate G3-C.1.1 - task 11: per-issue gold-flip sensitivity.

Read-only. For each of the 8 pilot issues it tabulates the effect on the
pre-registered endpoint DENOMINATORS / eligibility if a future independent human
adjudication were to flip the gold in either of two orthogonal ways:

  (A) oracle ACCEPT <-> REJECT (the merge-acceptability verdict)
  (B) sufficient <-> NEED on any of the 5 condition certificates.

It does NOT touch gold, does NOT use any model prediction (no Reviewer model has
been run on these 8 issues in the zero-API pilot), and does not impute model
verdicts. Consequently P1/P2 model NUMERATORS are explicitly unavailable; this
file bounds only the GOLD-SIDE counts and strata that the numerators would be
divided by once G3-C.2 is separately approved and executed.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_sensitivity
"""
from __future__ import annotations

from evidence import g3c11_common as K

# sufficient-evidence conditions where oracle outcome is rendered
SUFFICIENT_CONDITIONS = ("T3D-Escalate", "T2A-T", "T3A-T")
RESTRICTED_CONDITIONS = ("T2D-T", "T3D-Strict")


def load():
    oracle = {r["instance_id"]: r for r in K.read_jsonl(K.G3C1_ORACLE)}
    certs = {}
    for c in K.read_jsonl(K.G3C1_CERTS):
        certs.setdefault(c["instance_id"], {})[c["condition"]] = c
    return oracle, certs


def counts(oracle):
    n_acc = sum(1 for r in oracle.values() if r["oracle_gold"] == "ACCEPT")
    n_rej = sum(1 for r in oracle.values() if r["oracle_gold"] == "REJECT")
    return {"oracle_ACCEPT": n_acc, "oracle_REJECT": n_rej, "total": len(oracle)}


def by_group(oracle, key):
    out = {}
    for r in oracle.values():
        g = r.get(key)
        d = out.setdefault(g, {"ACCEPT": 0, "REJECT": 0})
        d[r["oracle_gold"]] += 1
    return out


def flipped(oracle, iid, to):
    m = {k: v for k, v in oracle.items()}
    row = dict(m[iid])
    row["oracle_gold"] = to
    m[iid] = row
    return m


def endpoint_gold_bounds(oracle, certs):
    """Gold-side eligibility only. P2 pool = oracle-REJECT issues that have at
    least one SUFFICIENT visible-outcome condition. P1 NEED pool per restricted
    condition is structural (all issues), independent of oracle flip."""
    reject = [i for i, r in oracle.items() if r["oracle_gold"] == "REJECT"]
    p2_pool = [i for i in reject
               if any(certs[i][c]["sufficient_for_decision"]
                      for c in SUFFICIENT_CONDITIONS)]
    need_restricted = {c: [i for i in oracle
                           if not certs[i][c]["sufficient_for_decision"]]
                       for c in RESTRICTED_CONDITIONS}
    return {
        "P2_oracle_REJECT_with_a_sufficient_condition_n": len(p2_pool),
        "P2_pool_issues": p2_pool,
        "P1_condition_gold_NEED_pool_n_per_restricted_condition":
            {c: len(v) for c, v in need_restricted.items()},
        "note": ("P1 NEED denominator in tier-D is STRUCTURAL (all 8 issues are "
                 "NEED in T2D-T/T3D-Strict regardless of oracle gold); an oracle "
                 "ACCEPT<->REJECT flip does not move it. A sufficient<->NEED "
                 "cert flip would."),
    }


def per_issue(oracle, certs):
    base = counts(oracle)
    base_queue = by_group(oracle, "pilot_queue_label")
    base_strat = by_group(oracle, "primary_stratum")
    base_bounds = endpoint_gold_bounds(oracle, certs)
    rows = []
    for iid in K.PILOT_ISSUES:
        cur = oracle[iid]["oracle_gold"]
        opp = "REJECT" if cur == "ACCEPT" else "ACCEPT"
        m2 = flipped(oracle, iid, opp)
        cert_now = {c: certs[iid][c]["sufficient_for_decision"]
                    for c in K.CONDITIONS}
        rows.append({
            "instance_id": iid,
            "queue": oracle[iid]["pilot_queue_label"],
            "stratum": oracle[iid]["primary_stratum"],
            "current_oracle_gold": cur,
            "current_cert_sufficient_by_condition": cert_now,
            "flip_A_verdict_to": opp,
            "flip_A_effect_on_pilot_gold_counts": counts(m2),
            "flip_A_effect_on_P2_REJECT_pool_n":
                endpoint_gold_bounds(m2, certs)[
                    "P2_oracle_REJECT_with_a_sufficient_condition_n"],
            "flip_A_P1_NEED_pool_unchanged": True,
            "flip_B_sufficient_to_NEED_conditions":
                [c for c in SUFFICIENT_CONDITIONS if cert_now[c]],
            "flip_B_NEED_to_sufficient_conditions":
                [c for c in K.CONDITIONS if not cert_now[c]],
            "flip_B_effect": ("toggling one sufficient condition to NEED would "
                "remove this issue from that condition's visible-outcome "
                "(P2-eligible) set; toggling a restricted NEED to sufficient "
                "would add it. Such a flip changes the per-condition "
                "ACCEPT/REJECT/NEED table but not the frozen oracle row."),
            "current_gold_tier": oracle[iid]["gold_tier"],
        })
    return rows, base, base_queue, base_strat, base_bounds


def main():
    K.ensure_out_dirs()
    oracle, certs = load()
    rows, base, base_queue, base_strat, base_bounds = per_issue(oracle, certs)

    # certificate 8x5 matrix (sufficient boolean), current state
    matrix = {iid: {c: certs[iid][c]["sufficient_for_decision"]
                    for c in K.CONDITIONS} for iid in K.PILOT_ISSUES}
    suff_totals = {c: sum(1 for iid in K.PILOT_ISSUES if matrix[iid][c])
                   for c in K.CONDITIONS}

    result = {
        "document": "G3-C.1.1 per-issue gold-flip sensitivity (task 11)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "read_only": True,
        "gold_modified": False,
        "model_predictions_used": False,
        "important_scope_note": ("The zero-API pilot ran NO Reviewer model on "
            "these 8 issues, so P1/P2 model numerators DO NOT EXIST yet. This "
            "analysis bounds only GOLD-SIDE denominators/eligibility; no rate "
            "is estimable and none is claimed. Gold must never be changed to "
            "match a model prediction."),
        "baseline_pilot_gold_counts": base,
        "baseline_gold_counts_by_queue_never_pooled": base_queue,
        "baseline_gold_counts_by_stratum": base_strat,
        "baseline_endpoint_gold_bounds": base_bounds,
        "cert_sufficiency_matrix_issue_by_condition": matrix,
        "sufficient_totals_per_condition": suff_totals,
        "per_issue_flips": rows,
        "natural_queue_rate_rule": ("natural n=4 (3 ACCEPT/1 REJECT) and "
            "enriched n=4 (3 ACCEPT/1 REJECT) are separate denominators; the "
            "natural first-4 are a sampling draw, NOT a natural-population "
            "prevalence estimate, and queues are never merged for a rate."),
        "approved_scope": K.APPROVED_SCOPE,
    }
    K.write_canonical(K.OUT_AUDIT / "g3c11_sensitivity.json", result)
    print("baseline gold:", base)
    print("P2 REJECT-with-sufficient pool n:",
          base_bounds["P2_oracle_REJECT_with_a_sufficient_condition_n"])
    print("P1 restricted NEED pool n:",
          base_bounds["P1_condition_gold_NEED_pool_n_per_restricted_condition"])
    print("sufficient totals:", suff_totals)
    print("->", (K.OUT_AUDIT / "g3c11_sensitivity.json").relative_to(K.HERE))


if __name__ == "__main__":
    main()
