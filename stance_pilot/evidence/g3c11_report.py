"""GroundedReview Gate G3-C.1.1 - task 13 (part 1): consolidated independent
audit report. Aggregates every g3c11_* audit artifact into one structured JSON
and one human-readable Markdown report: audit findings, sampling timeline,
per-issue gold-quality table, 18-packet human-review status table and the
G3-C.2 Go/No-Go recommendation.

Zero API; read-only over frozen stores; writes only under
evidence_store_g3c11/report/. The freeze manifest is written by a separate
final step (g3c11_freeze) so it can hash THIS report too.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_report
"""
from __future__ import annotations

from evidence import g3c11_common as K


def J(name, where=K.OUT_AUDIT):
    return K.read_json(where / name)


def main():
    K.ensure_out_dirs()
    verify = J("g3c11_verification.json")
    funnel = J("g3c11_funnel.json")
    prio = J("g3c11_priority_audit.json")
    issue = J("g3c11_issue_audit.json")
    sens = J("g3c11_sensitivity.json")
    decision = J("g3c11_gate3c2_decision.json")
    human = J("g3c11_second_annotator_plan.json", where=K.OUT_HUMAN)
    focused = J("g3c11_human_focused_review_items.json", where=K.OUT_HUMAN)

    # ---- per-issue gold-quality rows -------------------------------------
    quality = []
    for bucket in ("reject_issues", "accept_issues"):
        for iid, row in issue[bucket].items():
            rec = row["recalc"]
            quality.append({
                "instance_id": iid.replace("sympy__sympy-", ""),
                "queue": row["queue"],
                "stratum": row["stratum"],
                "oracle_gold": "REJECT" if iid in issue["reject_issues"]
                else "ACCEPT",
                "declared_f2p_n": row["declared_f2p_n"],
                "f2p_still_failing": rec["f2p_failed_ids"],
                "declared_scoped_p2p_n": row["declared_scoped_p2p_n"],
                "p2p_regressed": rec["p2p_regressed_ids"],
                "p2p_preexisting_bad": rec["p2p_preexisting_bad_ids"],
                "undeclared_collateral_failing_nodes":
                    [c["name"] for c in
                     row["collateral_undeclared_failing_nodes"]],
                "undeclared_candidate_era_collateral":
                    [c["name"] for c in
                     row["collateral_undeclared_possible_regressions"]],
                "symptom": "gone (pre fail / post pass)",
                "recomputation_matches_frozen":
                    row["recomputation_matches_stored_artifact"],
                "supports": ("REJECT on declared evidence"
                    if iid in issue["reject_issues"]
                    else "SCOPED acceptability only"),
                "gold_tier": "PROVISIONAL",
            })
    quality.sort(key=lambda r: r["instance_id"])

    # ---- human 18-packet status rows --------------------------------------
    human_rows = []
    for r in human["status_table"]:
        human_rows.append({
            "cohort": r["cohort"],
            "packet": r["packet_id"],
            "issue_sealed_study_team_only":
                r["sealed_instance_id"].replace("sympy__sympy-", ""),
            "n_files": r["n_files_in_packet"],
            "self_refs_issue_number":
                ", ".join(f.replace("02_candidate_patch.diff", "patch").replace(
                    "08_issue_symptom_probe.log", "probe")
                    for f in r["files_self_referencing_issue_number"]) or "-",
            "annotator2": r["annotator2_status"],
            "adjudication": r["adjudication_status"],
            "gold_tier": r["gold_tier"],
        })

    result = {
        "document": "GroundedReview Gate G3-C.1.1 INDEPENDENT AUDIT REPORT "
                    "(task 13)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "auditor_position": ("Independent zero-API audit of frozen G3-C.1 "
            "artifacts. No API call, no new issue, no model, no historical "
            "gold change, no frozen-test rewrite, no R2, no Git commit."),
        "headline_conclusions": [
            "Integrity PASS: all 185 frozen files hash-match, all parent pins "
            "match, truth/artifact/oracle are mutually consistent, freshness "
            "8/8, 40 certificates (24 sufficient/16 NEED), 456/456 HTTP "
            "assertions pass, 40 mock cells are plumbing-only (research "
            "excluded), projection v2 non-interference holds on all 144 "
            "restricted tier-D surfaces.",
            "Funnel replay is byte-identical: 75 ->(24 mutually-exclusive "
            "exclusions)-> 51 ->(4 changed-file dedup, natural queue only)"
            "-> 47; natural and enriched queues do not overlap (union=8) and "
            "are kept as separate denominators; no double counting.",
            "Enrichment priority TRAP>P2P>F2P is a PILOT-STAGE PRE-DATA "
            "operational refinement, fixed 28 minutes before the first "
            "outcome, NOT verbatim pre-registered in G3-C.0; the "
            "counterfactual F2P-first order moves 29 strata and would pick 4 "
            "different issues, so it is disclosed and must not be claimed as "
            "fully pre-registered.",
            "Both REJECTs independently reproduce from raw pytest logs: "
            "14248 = one declared F2P genuinely still failing "
            "(test_MatrixSymbol_printing PARTIAL_FAIL) plus two true "
            "regressions (test_haramard, test_matMul), with test_latex_Float "
            "correctly treated as pre-existing; 15875 = a single decisive "
            "declared F2P failure (test_Add_is_zero 'assert True is None'), "
            "independent of P2P/environment.",
            "Instrument blind spot disclosed: 15875 has TWO undeclared "
            "candidate-era collateral failures in an executed scope file "
            "(test_nfloat, test_subs_in_derivative; PASSED at baseline) that "
            "the declared-id scorer does not count; 19346 has one "
            "baseline-unmapped undeclared collateral (test_set). These do not "
            "change frozen gold but bound coverage claims.",
            "The six ACCEPTs support only SCOPED acceptability: all declared "
            "F2P transition, zero declared scoped-P2P regressions, symptom "
            "gone; full-dataset P2P, distant modules, performance/style and "
            "alt-patch equivalence are not validated.",
            "sympy-19495 probe revision is construct-valid: the original "
            "instrument was too weak (passed at both base and post); the "
            "frozen strengthened probe is derived only from the public "
            "report, maintainer test_patch never consulted, no gold changed, "
            "no issue replaced, and post-revision all 8 probes flip. Frozen "
            "probe sha matches the manifest and was not modified.",
            "Human adjudication NOT obtained: all 18 blind packets (10 G3-A "
            "+ 8 G3-C.1) are PENDING; 18/18 gold remain PROVISIONAL with "
            "annotator2 NOT_OBTAINED and zero AI labels; no Gold "
            "Adjudication Version is produced. Two approver-mandated focused "
            "reviews are also left PENDING for the human: FR1 sympy-19495 "
            "probe instrument-only-fix vs post-hoc oracle redefinition, and "
            "FR2 whether 14248/15875 use one uniform disjunctive REJECT "
            "standard.",
            "Recommendation for G3-C.2: NO-GO until (PC1) independent human "
            "gold adjudication, (PC2) written amendment/disclosure of the "
            "stratum connection order, and (PC3) the R-TRAP sampling shortfall "
            "(2 available vs floor 6) are resolved.",
        ],
        "supporting_artifacts": {
            "verification": "audit/g3c11_verification.json",
            "funnel": "audit/g3c11_funnel.json",
            "priority_audit": "audit/g3c11_priority_audit.json",
            "issue_audit": "audit/g3c11_issue_audit.json",
            "sensitivity": "audit/g3c11_sensitivity.json",
            "human_plan": "human_annotation/g3c11_second_annotator_plan.json",
            "human_focused_review":
                "human_annotation/g3c11_human_focused_review_items.json",
            "gate3c2_decision": "audit/g3c11_gate3c2_decision.json"},
        "integrity_summary": {
            "verification_overall_pass": verify["overall_pass"],
            "frozen_files_checked": verify["files"]["n_listed"],
            "file_hash_mismatches": verify["files"].get("n_mismatch", 0),
            "freshness_all_match": verify["freshness"].get("all_match"),
            "certificates_total":
                verify["certificates"].get("n_certificates"),
            "certificates_sufficient":
                verify["certificates"].get("sufficient_for_decision"),
            "certificates_need":
                verify["certificates"].get("need_evidence"),
            "http_checks_pass":
                f'{verify["http"].get("n_pass_retallied")}/'
                f'{verify["http"].get("n_checks_retallied")}',
            "mock_cells": verify["mock"].get("n_cells"),
            "mock_interpretation":
                "100% plumbing match is EXPECTED and research-EXCLUDED; not "
                "a model-performance number.",
            "restricted_tier_d_surfaces_clean":
                verify["noninterference"].get(
                    "restricted_surface_findings_total", 0),
            "determinism_all_byte_identical":
                verify["determinism"].get("deterministic"),
        },
        "funnel_summary": {
            "s0": 75, "excluded": 24, "eligible": 51,
            "dedup_suppressed_natural_only": 4,
            "dedup_eligible_base": 47,
            "stratum_sizes":
                prio["replay_actual"]["stratum_sizes"],
            "natural_picks": funnel["queue_separation"]["natural_queue"]
                .get("picks"),
            "enriched_picks":
                prio["replay_actual"]["enriched_picks"],
            "queues_disjoint": len(funnel["queue_separation"]["overlap"].get(
                "issue_overlap", [])) == 0,
            "no_pooled_natural_rate": True,
        },
        "sampling_timeline_utc": prio["timeline_utc"],
        "sampling_rule_classification": prio["classification"],
        "per_issue_gold_quality_table": quality,
        "human_review_status_table": human_rows,
        "human_focused_review_items": focused["focused_items"],
        "probe_19495_audit": issue["probe_19495_construct_audit"],
        "sensitivity_note": sens["important_scope_note"],
        "gate3c2_recommendation": decision["recommendation"],
        "gate3c2_blocking_preconditions":
            [p for p in decision["preconditions"] if p["blocks_release"]],
        "approved_scope": K.APPROVED_SCOPE,
        "next_action": ("STOP. Await separate written approval of G3-C.2; "
            "this gate executes no expansion."),
    }

    K.write_canonical(K.OUT_REPORT / "g3c11_audit_report.json", result)
    md = render_markdown(result)
    with (K.OUT_REPORT / "g3c11_audit_report.md").open(
            "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md)
    print("report json + md written")
    print("->", (K.OUT_REPORT / "g3c11_audit_report.md").relative_to(K.HERE))


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join("---" for _ in headers) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_markdown(R):
    L = []
    L.append("# GroundedReview — Gate G3-C.1.1 Independent Audit Report\n")
    L.append("- Design version: `%s`" % R["design_version"])
    L.append("- Protocol: `%s`" % R["protocol_version"])
    L.append("- Scope: zero-API offline audit; $0 added, 0 new issues, no "
             "model, no historical-gold change, no frozen-test rewrite, no "
             "R2, no Git commit.\n")
    L.append("## 1. Headline conclusions\n")
    for i, c in enumerate(R["headline_conclusions"], 1):
        L.append(f"{i}. {c}")
    L.append("")

    s = R["integrity_summary"]
    L.append("## 2. Frozen-artifact integrity (tasks 1 & 8)\n")
    L.append(md_table(["Check", "Result"], [
        ["verification overall", "PASS" if s["verification_overall_pass"]
         else "FAIL"],
        ["frozen files checked", s["frozen_files_checked"]],
        ["file hash mismatches", s["file_hash_mismatches"]],
        ["freshness", ("8/8 match" if s["freshness_all_match"] else "FAIL")],
        ["certificates (sufficient / NEED)",
         f'{s["certificates_total"]} ({s["certificates_sufficient"]}/'
         f'{s["certificates_need"]})'],
        ["HTTP assertions", s["http_checks_pass"]],
        ["mock cells (plumbing, research-excluded)", s["mock_cells"]],
        ["restricted tier-D surfaces with findings",
         s["restricted_tier_d_surfaces_clean"]],
        ["determinism (3/3 byte-identical)",
         "PASS" if s["determinism_all_byte_identical"] else "FAIL"],
    ]))
    L.append("\n" + s["mock_interpretation"] + "\n")

    f = R["funnel_summary"]
    L.append("## 3. Selection funnel & dual queues (tasks 2 & 4)\n")
    L.append(f"S0 **75** → 24 mutually-exclusive exclusions → **51** "
             f"eligible → 4 changed-file de-duplications (natural queue "
             f"only) → **47** stratum base. No double counting: exclusions "
             f"are if/elif-disjoint and dedup is applied once.\n")
    L.append(md_table(["Stratum", "n in 47 pool"],
                      [[k, v] for k, v in f["stratum_sizes"].items()]))
    L.append("")
    L.append("- Natural first-4: " + ", ".join(
        x.replace("sympy__sympy-", "") for x in f["natural_picks"]))
    L.append("- Enriched first-4: " + ", ".join(
        x.replace("sympy__sympy-", "") for x in f["enriched_picks"]))
    L.append("- Queues are disjoint (union = 8); denominators/pass-rates are "
             "reported SEPARATELY and never pooled into a natural-population "
             "rate.\n")

    L.append("## 4. Enrichment-priority timeline & pre-registration status "
             "(task 3)\n")
    L.append(md_table(["UTC time", "Event"],
              [[t["utc"], t["event"]] for t in R["sampling_timeline_utc"]]))
    L.append("\n**Classification:** " +
             R["sampling_rule_classification"]["verdict"] + "\n")

    L.append("## 5. Per-issue gold-quality table (tasks 5, 6, 7)\n")
    qrows = []
    for q in R["per_issue_gold_quality_table"]:
        qrows.append([
            q["instance_id"], q["queue"], q["stratum"], q["oracle_gold"],
            f'{len(q["f2p_still_failing"])}/{q["declared_f2p_n"]}',
            ", ".join(q["p2p_regressed"]) or "-",
            ", ".join(q["undeclared_candidate_era_collateral"]) or "-",
            q["supports"], q["gold_tier"]])
    L.append(md_table(
        ["issue", "queue", "stratum", "gold", "F2P fail/total",
         "declared P2P regressions", "undeclared candidate-era collateral",
         "supports", "tier"], qrows))
    L.append("\n`undeclared candidate-era collateral` = failing nodes in "
             "executed scope files that are absent from the dataset's "
             "declared PASS_TO_PASS id set: not scored, disclosed as an "
             "instrument coverage blind spot. ACCEPTs are SCOPED only "
             "(full-dataset P2P not run).\n")

    pa = R["probe_19495_audit"]
    L.append("## 6. sympy-19495 probe construct audit (task 6)\n")
    L.append(f"- Frozen probe sha matches manifest: **"
             f'{pa["frozen_probe"]["matches_freeze_manifest"]}** '
             f"(read-only, not modified).")
    L.append(f"- Initial instrument: baseline_passed="
             f'{pa["initial_instrument_failure"]["baseline_probe_passed"]}, '
             f"post_passed="
             f'{pa["initial_instrument_failure"]["post_candidate_probe_passed"]} '
             f"(too weak).")
    L.append(f"- Maintainer test_patch consulted: "
             f'{pa["evidence_source"].split("(")[1].rstrip(")")}.')
    L.append(f"- Post-revision gate: all_probes_flip="
             f'{pa["post_revision_gate"]["all_probes_flip"]} over '
             f'{pa["post_revision_gate"]["n_issues"]} issues; '
             f"no_gold_changed={pa['no_gold_changed']}, "
             f"no_issue_replaced={pa['no_issue_replaced']}.\n")

    L.append("## 7. Human second-annotator status (tasks 9 & 10)\n")
    hrows = [[h["cohort"], h["packet"], h["issue_sealed_study_team_only"],
              h["n_files"], h["self_refs_issue_number"], h["annotator2"],
              h["adjudication"], h["gold_tier"]]
             for h in R["human_review_status_table"]]
    L.append(md_table(
        ["cohort", "packet", "issue (sealed; study team only)", "files",
         "self-refs", "annotator2", "adjudication", "tier"], hrows))
    L.append("\n18/18 PENDING and PROVISIONAL; annotator2 = NOT_OBTAINED; "
             "zero AI labels. Identity blinding is PARTIAL (verbatim "
             "patch/probe text may quote the issue number). A real second "
             "human + third-senior-human arbitration is required before any "
             "Gold Adjudication Version.\n")

    L.append("## 7a. Approver-mandated human focused reviews (Risk B & II.1)\n")
    for it in R["human_focused_review_items"]:
        ids = it.get("instance_id") or " + ".join(
            x.replace("sympy__sympy-", "") for x in it["instances"])
        L.append(f"### {it['id']} — {ids}\n")
        L.append("**Question:** " + it["question"] + "\n")
        if it["id"].startswith("FR1"):
            tl = it["revision_timeline_utc"]
            L.append("Probe-revision timeline (UTC): weak-probe failure "
                     f"{tl['weak_probe_both_pass_failure_record']} → "
                     "strengthened probe "
                     f"{tl['frozen_strengthened_probe_file_mtime']} → "
                     "all-8-flip selftest "
                     f"{tl['all_8_flip_selftest_mtime']}, i.e. ~24 min BEFORE "
                     f"the real pytest build ({tl['first_real_pytest_build_for_19495']}).\n")
        L.append(f"AI determination: **none** (`ai_determination=null`); "
                 f"human decision: **{it['human_decision']}**.\n")
    L.append("Both items must be answered by the real independent human "
             "(blank worksheet: `human_annotation/g3c11_human_focused_review_worksheet.csv`) "
             "before G3-C.2; they are inputs to blocking precondition PC1.\n")

    L.append("## 8. Sensitivity (task 11)\n")
    L.append(R["sensitivity_note"] + "\n")

    L.append("## 9. Gate G3-C.2 decision (task 12)\n")
    L.append(f"**Recommendation: {R['gate3c2_recommendation']}**\n")
    L.append("Blocking preconditions:")
    for p in R["gate3c2_blocking_preconditions"]:
        L.append(f"- **{p['id']}** — {p['requirement']} "
                 f"*Current state: {p['current_state']}*")
    L.append("")

    L.append("## 10. Next action\n")
    L.append(R["next_action"] + "\n")
    return "\n".join(L)


if __name__ == "__main__":
    main()
