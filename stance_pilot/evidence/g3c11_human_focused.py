"""GroundedReview Gate G3-C.1.1 - human focused-review addendum (raised by the
approver's Risk B and section II.1). Zero API, zero AI verdicts.

Two items MUST be decided by the real second annotator / third arbitrator -
they are deliberately left UNRESOLVED here:

  FR1 (Risk B): sympy-19495 probe revision - did the strengthened probe fix
      only the INSTRUMENT (derived solely from the public issue report) or did
      it, after observing the candidate patch succeed, selectively redefine the
      acceptability oracle? (instrument-fix vs post-hoc-oracle-redefinition)

  FR2 (section II.1): do sympy-14248 and sympy-15875 instantiate the SAME
      acceptability standard despite different failure modes (14248 = declared
      F2P still failing AND two scoped regressions; 15875 = single decisive
      declared F2P failure, zero regressions)?

This module only assembles the evidence pointers and timeline for a human and
opens an EMPTY worksheet; it makes no determination. Outputs under
evidence_store_g3c11/human_annotation/.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_human_focused
"""
from __future__ import annotations

import csv

from evidence import g3c11_common as K

PROBE_MTIME_UTC = "2026-10-28T09:51:02Z"
SELFTEST_MTIME_UTC = "2026-10-28T09:54:50Z"
FAIL_RECORD_UTC = "2026-10-28T09:48:33Z"
BUILD_19495_BUILT_AT = "2026-10-28T10:15:07Z"
BUILD_SESSION_END_UTC = "2026-10-28T10:16:07Z"


def main():
    K.ensure_out_dirs()
    issue = K.read_json(K.OUT_AUDIT / "g3c11_issue_audit.json")
    note = K.read_json(K.G3C1_PROBE_NOTE)

    fr1 = {
        "id": "FR1_probe_19495_instrument_vs_oracle_redefinition",
        "triggered_by": "Approver Risk B (Gate G3-C.1 acceptance memo)",
        "instance_id": "sympy__sympy-19495",
        "blind_packet": "G3-C.1 packet P02 (identity sealed from annotator2)",
        "question": ("Was the probe strengthening a correction of the TEST "
            "INSTRUMENT only, or did observing the candidate patch succeed "
            "lead to a selective post-hoc redefinition of the acceptability "
            "oracle?"),
        "what_the_human_must_verify": [
            "The three strengthened assertions are independently derivable "
            "from the PUBLIC issue report alone (bound ConditionSet dummy "
            "must remain a Symbol; plain .subs must equal the report's "
            "xreplace / simultaneous=True references; no free substituted "
            "symbol remains).",
            "No assertion was chosen because it happens to pass on the "
            "candidate while excluding the baseline; the assertion must "
            "distinguish the two on the report-stated semantics.",
            "The maintainer test_patch/test_subs_CondSet was not consulted "
            "(recorded maintainer_test_patch_consulted=%r)."
            % note["maintainer_test_patch_consulted"],
            "The original failure record was retained unaltered and the "
            "issue was kept rather than swapped to an easier one.",
        ],
        "revision_timeline_utc": {
            "weak_probe_both_pass_failure_record": FAIL_RECORD_UTC,
            "frozen_strengthened_probe_file_mtime": PROBE_MTIME_UTC,
            "all_8_flip_selftest_mtime": SELFTEST_MTIME_UTC,
            "first_real_pytest_build_for_19495": BUILD_19495_BUILT_AT,
            "build_session_end": BUILD_SESSION_END_UTC,
            "ordering_finding": ("probe strengthened ~2m29s after the "
                "flip-gate stop and ~24 minutes BEFORE the real pytest "
                "build that accepted the issue; the revision therefore "
                "predates formal build/patch-success evidence."),
        },
        "before_after_assertion_evidence": {
            "weak_probe_observed_output": note["initial_stop_record"],
            "weak_assertion_behavior": ("printed 'OK: ConditionSet.subs "
                "returns a well-formed set' at BOTH baseline (malformed "
                "ConditionSet(1/3,...)) and post-candidate (correct "
                "ImageSet), so it could not distinguish them and exited 0 "
                "twice."),
            "strengthened_frozen_probe": "probes/sympy__sympy-19495.py",
            "three_strengthened_assertions": issue[
                "probe_19495_construct_audit"]["strengthened_probe_assertions"],
        },
        "frozen_probe_not_modified_by_this_gate": issue[
            "probe_19495_construct_audit"]["frozen_probe"][
            "read_only_not_modified"],
        "ai_determination": None,
        "human_required": True,
        "human_decision": "PENDING",
    }

    r14248 = issue["reject_issues"]["sympy__sympy-14248"]["recalc"]
    r15875 = issue["reject_issues"]["sympy__sympy-15875"]["recalc"]
    fr2 = {
        "id": "FR2_two_rejects_same_acceptability_standard",
        "triggered_by": "Approver section II.1 (Gate G3-C.1 acceptance memo)",
        "instances": ["sympy__sympy-14248", "sympy__sympy-15875"],
        "blind_packets": {"14248": "G3-C.1 P01", "15875": "G3-C.1 P08"},
        "question": ("Do 14248 and 15875 apply the SAME acceptability "
            "standard, or do the different failure modes imply different "
            "oracle rules that should be pre-registered separately before "
            "expansion?"),
        "evidence_summary": {
            "14248": {
                "declared_f2p_still_failing": r14248["f2p_failed_ids"],
                "scoped_p2p_regressions": r14248["p2p_regressed_ids"],
                "preexisting_bad_excluded": r14248["p2p_preexisting_bad_ids"],
                "failure_mode": "declared F2P still fails AND two fresh "
                                "scoped P2P regressions (jointly decisive)"},
            "15875": {
                "declared_f2p_still_failing": r15875["f2p_failed_ids"],
                "scoped_p2p_regressions": r15875["p2p_regressed_ids"],
                "preexisting_bad_excluded": r15875["p2p_preexisting_bad_ids"],
                "failure_mode": "single decisive declared F2P failure; 0 "
                                "declared scoped regressions",
                "undeclared_collateral_disclosed": [
                    c["name"] for c in issue["reject_issues"][
                        "sympy__sympy-15875"][
                        "collateral_undeclared_possible_regressions"]]},
        },
        "rubric_hypothesis_to_confirm": ("The frozen rubric REJECTS if there "
            "is AT LEAST ONE decisive applicable failure (persistent declared "
            "F2P OR scoped P2P regression); under that single disjunctive "
            "rule both cases are REJECT for the same reason. The human must "
            "confirm the disjunction is intended uniformly and not "
            "retrofit to the cases."),
        "ai_determination": None,
        "human_required": True,
        "human_decision": "PENDING",
    }

    result = {
        "document": "G3-C.1.1 human focused-review addendum (approver Risk B "
                    "+ section II.1)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "ai_verdicts_provided": False,
        "note": ("The AI assembles evidence only; FR1/FR2 are left PENDING "
            "for the real annotator2 and, on disagreement, the third senior "
            "human. These items are in addition to the 18-packet three-label "
            "review and must be answered before G3-C.2."),
        "focused_items": [fr1, fr2],
        "approved_scope": K.APPROVED_SCOPE,
    }
    out = K.OUT_HUMAN / "g3c11_human_focused_review_items.json"
    K.write_canonical(out, result)

    # blank worksheet for the human (no AI answers)
    csv_path = K.OUT_HUMAN / "g3c11_human_focused_review_worksheet.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["focused_item", "instance(s)", "blind_packet(s)",
                    "human_finding (instrument_fix/oracle_redefinition ; "
                    "same_standard/different_standard/undecidable)",
                    "reason (3-6 sentences)", "any_rubric_amendment_needed "
                    "(yes/no + wording)", "confidence (high/medium/low)",
                    "annotator_id", "date"])
        w.writerow(["FR1", "sympy__sympy-19495", "G3-C.1 P02", "", "", "",
                    "", "", ""])
        w.writerow(["FR2", "14248 + 15875", "G3-C.1 P01 + P08", "", "", "",
                    "", "", ""])

    print("focused items written (both PENDING, no AI verdict):", out.name)
    print("->", out.relative_to(K.HERE))


if __name__ == "__main__":
    main()
