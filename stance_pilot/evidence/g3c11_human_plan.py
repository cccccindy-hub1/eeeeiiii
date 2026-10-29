"""GroundedReview Gate G3-C.1.1 - tasks 9 + 10: consolidate the G3-A (10) and
G3-C.1 (8) blind packets into one executable second-independent-human-annotator
plan, and open an EMPTY annotation registry.

Zero API, zero AI labels. This stage obtained no second human, so every packet
stays PENDING and every gold stays PROVISIONAL; annotator2 = NOT_OBTAINED.

Outputs (all under evidence_store_g3c11/human_annotation/):
  g3c11_second_annotator_plan.json      - plan + 18-row study-team status table
  g3c11_annotator2_registry_study_team.csv - study-team-only, carries sealed id
  g3c11_annotator2_blank_labels.csv     - blinded hand-out ledger (no ids)

Run:  uv run --offline --python 3.9 -m evidence.g3c11_human_plan
"""
from __future__ import annotations

import csv

from evidence import g3c11_common as K

C1_PKG = K.read_json(K.G3C1_HUMAN_PKG)
C0_PKG = K.read_json(K.G3C0_HUMAN_PKG)
C1_MAP = K.read_json(K.G3C1 / "human_annotation" / "SEALED_packet_mapping.json")
C0_MAP = K.read_json(K.G3C0 / "human_annotation" / "SEALED_packet_mapping.json")


def rows():
    out = []
    sources = [
        ("G3-A", C0_PKG, C0_MAP["mapping_packet_to_instance"]),
        ("G3-C.1", C1_PKG, C1_MAP["mapping_packet_to_instance"]),
    ]
    for cohort, pkg, mapping in sources:
        for p in pkg["packet_manifest"]:
            pid = p["packet_id"]
            selfrefs = p.get("files_self_referencing_this_issue_number", [])
            out.append({
                "cohort": cohort,
                "packet_id": pid,
                "sealed_instance_id": mapping[pid],   # study team only
                "artifact_id_used_for_logs": p["artifact_id_used_for_logs"],
                "n_files_in_packet": p["n_files"],
                "packet_sha256": p[
                    "packet_sha256_of_concatenated_filenames_and_bytes"],
                "files_self_referencing_issue_number": selfrefs,
                "identity_blinding": "PARTIAL",
                "annotator2_status": "NOT_OBTAINED",
                "adjudication_status": "PENDING",
                "gold_tier": "PROVISIONAL",
            })
    out.sort(key=lambda r: (r["cohort"], r["packet_id"]))
    return out


COMPETENCY = [
    "Reads modern pytest verbose node lines AND terminal summaries, and "
    "understands that old SymPy raised sympy.utilities.pytest.XFail/Skipped "
    "which modern pytest prints as FAILED (must recover via the terminal "
    "summary, not count as a regression).",
    "Understands FAIL_TO_PASS vs in-scope PASS_TO_PASS, scoped vs full-suite "
    "acceptability, and pre-existing-bad (fails at clean baseline) vs "
    "candidate-induced regression.",
    "Can read unified diffs of candidate and maintainer test patches and spot "
    "self-added-test / tautological-test traps.",
    "Comfortable with SymPy idioms (ConditionSet/ImageSet, printing backends, "
    "core arithmetic) well enough to judge whether an exception is a genuine "
    "wrong-answer vs an environment/NumPy/recursion-limit artifact.",
    "INDEPENDENT of the pipeline author and of the models that generated the "
    "patches; has never seen annotator-1 gold, model verdicts, or the analysis "
    "outputs.",
]

WORKLOAD = [
    "18 packets x 9 files each; pytest logs up to ~100 KB per run (3 logs per "
    "issue: f2p, scoped p2p after, scoped p2p clean baseline), plus problem "
    "statement, candidate patch, maintainer test patch and symptom-probe log.",
    "Estimated ~25-40 minutes per packet for a careful reader; budget roughly "
    "9-12 person-hours total including a short calibration pass.",
    "Calibration: label 2 non-cohort practice packets first (not counted), "
    "resolve rubric questions, then label all 18 independently without "
    "feedback and without unsealing.",
]

DECISION_STANDARD = [
    "Use the frozen 3-label rubric exactly: ACCEPT (all declared F2P "
    "transition and no declared scoped P2P regression; record SCOPED "
    "acceptability), REJECT (at least one decisive APPLICABLE failure: a "
    "declared F2P still failing OR a scoped P2P regression, after separating "
    "environment/pre-existing/xfail/flaky/self-added-test cases), "
    "NEEDS_REVIEW (genuinely undecidable). Do not force ACCEPT/REJECT.",
    "Record the decisive failing test node id(s), a 1-4 sentence applicability "
    "reason, any xfail/flaky/self-added-test concern, and confidence "
    "(high/medium/low) in the blinded CSV.",
    "Judgement is based ONLY on the packet contents; the issue number, model "
    "verdict, annotator-1 gold and freshness/coverage analyses are withheld.",
]

ARBITRATION_PATH = [
    "On annotator1 vs annotator2 disagreement (label differs, or ACCEPT/"
    "REJECT vs NEEDS_REVIEW), a THIRD senior human arbitrates independently.",
    "The third arbitrator must not be an LLM and must not be the pipeline "
    "author or either annotator; receives the same blinded packet plus both "
    "labels and reasons, with no identity reveal.",
    "The arbitrator issues one of the three labels with a reason; all three "
    "labels and reasons are retained verbatim (no silent overwrite).",
    "Only after real annotator2 labels + required adjudication are returned "
    "may a new Gold Adjudication Version be produced and gold be raised above "
    "PROVISIONAL. No AI self-assessment may substitute at any step.",
]

DEBLIND_RISKS = [
    "Identity blinding is PARTIAL: folder names and the mapping are blinded, "
    "but verbatim patch/problem/probe text may quote the upstream issue "
    "number.",
    "G3-C.1: all 8 packets self-reference the issue number in "
    "08_issue_symptom_probe.log; P02(=19495) additionally in "
    "02_candidate_patch.diff.",
    "G3-A: only P04/P05/P06/P10 self-reference in 02_candidate_patch.diff; "
    "P01/P02/P03/P07/P08/P09 contain no self-reference.",
    "Mitigations available WITHOUT rewriting evidence (which would corrupt "
    "the adjudication target): (a) instruct annotator2 not to look up issue "
    "numbers and treat any seen number as non-informative; (b) future "
    "hardening - a copied-verbatim hash-only-id appendix; (c) record the "
    "partial-blinding limitation as a known bias in the adjudication report.",
    "Risk if an annotator recognises an issue or searches it upstream: "
    "label could be anchored to the upstream merged/closed status; such "
    "packets must be flagged and adjudicated rather than silently trusted.",
]

STOP_RULES_FOR_THIS_STAGE = [
    "No second human was obtained within Gate G3-C.1.1, therefore 18/18 "
    "remain PENDING and PROVISIONAL; no Gold Adjudication Version is created.",
    "AI-generated labels are forbidden and none are written.",
    "Two approver-mandated FOCUSED reviews are also left for the human and "
    "must be resolved before G3-C.2: FR1 sympy-19495 probe instrument-fix vs "
    "post-hoc oracle redefinition (Risk B); FR2 whether 14248 and 15875 "
    "apply one uniform disjunctive REJECT standard (section II.1).",
]


def write_csvs(rows18):
    reg = K.OUT_HUMAN / "g3c11_annotator2_registry_study_team.csv"
    with reg.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["cohort", "packet_id", "sealed_instance_id_STUDY_TEAM_ONLY",
                    "artifact_id", "n_files", "packet_sha256",
                    "files_self_referencing_issue_number",
                    "identity_blinding", "annotator2_status",
                    "adjudication_status", "gold_tier"])
        for r in rows18:
            w.writerow([r["cohort"], r["packet_id"], r["sealed_instance_id"],
                        r["artifact_id_used_for_logs"], r["n_files_in_packet"],
                        r["packet_sha256"],
                        ";".join(r["files_self_referencing_issue_number"]),
                        r["identity_blinding"], r["annotator2_status"],
                        r["adjudication_status"], r["gold_tier"]])

    blank = K.OUT_HUMAN / "g3c11_annotator2_blank_labels.csv"
    with blank.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["cohort", "packet_id",
                    "label (ACCEPT/REJECT/NEEDS_REVIEW)",
                    "decisive_failing_test_ids (semicolon; or NONE)",
                    "applicability_reason (1-4 sentences)",
                    "any_xfail_flaky_self_added_concern (yes/no + note)",
                    "confidence (high/medium/low)", "annotator_id", "date"])
        for r in rows18:
            w.writerow([r["cohort"], r["packet_id"], "", "", "", "", "", "", ""])
    return reg, blank


def main():
    K.ensure_out_dirs()
    rows18 = rows()
    assert len(rows18) == 18, len(rows18)
    n_self = sum(1 for r in rows18 if r["files_self_referencing_issue_number"])
    reg, blank = write_csvs(rows18)

    result = {
        "document": "G3-C.1.1 second-independent-human-annotator plan and "
                    "status (tasks 9+10)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "packets_total": 18,
        "packets_by_cohort": {"G3-A": 10, "G3-C.1": 8},
        "rubric_three_labels_same": ["ACCEPT", "REJECT", "NEEDS_REVIEW"],
        "rubric_byte_identical_across_cohorts":
            C0_PKG["rubric"] == C1_PKG["rubric"],
        "rubric_note": ("Same three labels and same decision structure "
            "(F2P transition + scoped P2P no-regression; separate "
            "environment/preexisting/xfail/flaky/self-added-test; scoped "
            "acceptability). Wording differs slightly (G3-C.1 adds 'the full "
            "dataset P2P suite was not run for this pilot'); semantic "
            "criteria are aligned, so one annotator can use one rubric."),
        "arbitration_rule_frozen": C0_PKG["arbitration"],
        "required_competency": COMPETENCY,
        "workload_estimate": WORKLOAD,
        "decision_standard": DECISION_STANDARD,
        "third_person_arbitration_path": ARBITRATION_PATH,
        "deblinding_risks_partial_blinding": DEBLIND_RISKS,
        "n_packets_with_issue_number_self_reference": n_self,
        "focused_review_items": {
            "n": 2,
            "FR1": ("sympy-19495 probe: instrument-only fix vs post-hoc "
                    "oracle redefinition after observing patch success "
                    "(approver Risk B)"),
            "FR2": ("14248 vs 15875: confirm one uniform disjunctive REJECT "
                    "standard across the two failure modes (approver "
                    "section II.1)"),
            "worksheet": "human_annotation/g3c11_human_focused_review_worksheet.csv",
            "items_json": "human_annotation/g3c11_human_focused_review_items.json",
            "all_pending_no_ai_verdict": True},
        "status_table": rows18,
        "annotator2_obtained": False,
        "labels_produced_by_ai": 0,
        "gold_adjudication_version_produced": False,
        "all_gold_tier": "PROVISIONAL (18/18)",
        "stage_stop_rules": STOP_RULES_FOR_THIS_STAGE,
        "registry_csv_study_team_only": str(
            reg.relative_to(K.HERE)).replace("\\", "/"),
        "blank_labels_csv_handout": str(
            blank.relative_to(K.HERE)).replace("\\", "/"),
        "approved_scope": K.APPROVED_SCOPE,
    }
    K.write_canonical(K.OUT_HUMAN / "g3c11_second_annotator_plan.json", result)
    print("packets:", len(rows18), "self-referencing:", n_self)
    print("annotator2 obtained: False ; AI labels: 0 ; gold: PROVISIONAL 18/18")
    print("->", (K.OUT_HUMAN / "g3c11_second_annotator_plan.json")
          .relative_to(K.HERE))


if __name__ == "__main__":
    main()
