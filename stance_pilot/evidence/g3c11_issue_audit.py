"""GroundedReview Gate G3-C.1.1 - tasks 5, 6, 7: independent test-evidence
review of the two REJECT issues, the sympy-19495 probe construct, and the six
ACCEPT issues' scoped-acceptability sufficiency / blind spots.

Read-only. It RE-DERIVES bare-test-name outcomes straight from the frozen raw
pytest logs (f2p / p2p / p2p_baseline) using the FROZEN parser semantics in
evidence.builder (parse_node_logs / name_outcomes / BAD) rather than trusting
the stored artifact outcome dicts, and then compares. It also scans the batched
run files for COLLATERAL failing nodes that are not declared F2P/P2P names (an
instrument coverage blind spot), and pulls the actual exception lines as
independent evidence. No pytest, patch or probe is executed or modified.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_issue_audit
"""
from __future__ import annotations

import re

from evidence.builder import parse_node_logs, BAD
from evidence import g3c11_common as K

LOGD = K.G3C1 / "store" / "logs"
ARTD = K.G3C1 / "store" / "artifacts"
PROBED = K.G3C1 / "probes"

NAME_NODE_RE = re.compile(r"^([\w\\/.]+\.py)::([A-Za-z_][\w]*)(?:\[[^\]]*\])?")


def _read(name):
    return (LOGD / name).read_text(encoding="utf-8", errors="replace")


def node_status(log_text):
    return parse_node_logs([log_text])


def name_files_from_log(names, status):
    """Independently derive bare-name -> [node files] from the parsed log
    itself (every file::name node actually reported)."""
    out = {n: set() for n in names}
    for node in status:
        for n in names:
            if node.endswith("::" + n):
                out[n].add(node.split("::", 1)[0])
    return {n: sorted(f) for n, f in out.items()}


def aggregate(names, name_files, status):
    res = {}
    for n in names:
        files = name_files.get(n, [])
        if not files:
            res[n] = "unmapped"
            continue
        sts = [status.get(f + "::" + n) for f in files]
        sts = [s for s in sts if s]
        if not sts:
            res[n] = "missing"
        elif all(s in ("FAILED", "ERROR") for s in sts):
            res[n] = "FAILED"
        elif any(s in ("FAILED", "ERROR") for s in sts):
            res[n] = "PARTIAL_FAIL"
        elif all(s in ("PASSED", "XFAIL", "SKIPPED") for s in sts):
            res[n] = "PASSED"
        else:
            res[n] = sts[0]
    return res


def collateral_failures(declared, status_after, status_base):
    """Batched scope files run whole; report failing nodes whose bare name is
    NOT a declared F2P/P2P id, with their baseline status (regression vs env)."""
    declared = set(declared)
    seen = {}
    for node, st in status_after.items():
        if st not in ("FAILED", "ERROR"):
            continue
        fname, name = node.split("::", 1)
        if name in declared:
            continue
        # collapse multiple files: keep worst after + baseline per bare name
        prev = seen.get(name)
        base_st = status_base.get(node)
        item = {"name": name, "file": fname.replace("\\", "/"),
                "after": st, "baseline_same_node": base_st}
        if prev is None or st == "ERROR":
            seen[name] = item
    return sorted(seen.values(), key=lambda x: x["name"])


def exception_lines(log, names, limit=6):
    out = []
    pat = re.compile(r"^(?:FAILED|ERROR)\s+\S*::(\w+)\s+-\s+(.+)$")
    for line in log.splitlines():
        m = pat.match(line.strip())
        if m and m.group(1) in names:
            out.append(line.strip())
    return out[:limit]


def audit_issue(iid, trow):
    aid = trow["artifact_id"]
    art = K.read_json(ARTD / f"{aid}.json")
    f2p_log = _read(f"{aid}.f2p.log")
    p2p_log = _read(f"{aid}.p2p.log")
    base_log = _read(f"{aid}.p2p_baseline.log")

    st_after = node_status(f2p_log)          # f2p/p2p share the same accept log
    st_p2p = node_status(p2p_log)
    st_base = node_status(base_log)

    f2p_names = list(art["fail_to_pass"].keys())
    p2p_names = list(art["pass_to_pass_scoped"].keys())
    f2p_map = name_files_from_log(f2p_names, st_after)
    p2p_map = name_files_from_log(p2p_names, st_p2p)
    base_map = name_files_from_log(p2p_names, st_base)

    f2p_recalc = aggregate(f2p_names, f2p_map, st_after)
    p2p_recalc = aggregate(p2p_names, p2p_map, st_p2p)
    p2p_base_recalc = aggregate(p2p_names, base_map, st_base)

    f2p_failed_recalc = sorted(n for n, s in f2p_recalc.items() if s in BAD)
    reg_recalc = sorted(
        n for n, s in p2p_recalc.items()
        if s in BAD and p2p_base_recalc.get(n) in ("PASSED", "XFAIL", "SKIPPED")
        and p2p_base_recalc.get(n) not in BAD)
    pre_recalc = sorted(
        n for n, s in p2p_recalc.items() if s in BAD and n not in reg_recalc)

    stored = art["summary"]
    recomputation_matches = (
        f2p_recalc == art["fail_to_pass"]
        and p2p_recalc == art["pass_to_pass_scoped"]
        and f2p_failed_recalc == stored["f2p_failed_ids"]
        and reg_recalc == stored["p2p_regressed_ids"]
        and pre_recalc == stored["p2p_preexisting_bad_ids"]
        and stored["f2p_total"] == trow["label_provenance"]["f2p_total"]
        and stored["p2p_total"] == trow["label_provenance"]["p2p_scoped_total"])

    collateral = collateral_failures(f2p_names + p2p_names, st_p2p, st_base)
    collateral_regressions = [c for c in collateral
                              if c["baseline_same_node"] in ("PASSED", None)]

    lp = trow["label_provenance"]
    return {
        "instance_id": iid, "artifact_id": aid,
        "queue": trow.get("pilot_queue_label"),
        "stratum": trow.get("primary_stratum"),
        "declared_f2p_n": len(f2p_names), "declared_scoped_p2p_n": len(p2p_names),
        "p2p_full_dataset_n": art["scope"]["p2p_total_in_dataset"],
        "recalc": {
            "f2p_outcomes": f2p_recalc,
            "f2p_failed_ids": f2p_failed_recalc,
            "p2p_regressed_ids": reg_recalc,
            "p2p_preexisting_bad_ids": pre_recalc,
            "f2p_failure_exception_lines":
                exception_lines(f2p_log, set(f2p_failed_recalc)),
        },
        "stored_summary": {
            "f2p_failed_ids": stored["f2p_failed_ids"],
            "p2p_regressed_ids": stored["p2p_regressed_ids"],
            "p2p_preexisting_bad_ids": stored["p2p_preexisting_bad_ids"]},
        "recomputation_matches_stored_artifact": recomputation_matches,
        "collateral_undeclared_failing_nodes": collateral,
        "collateral_undeclared_possible_regressions": collateral_regressions,
        "symptom_pre_passed": lp["symptom_pre_patch_passed"],
        "symptom_post_passed": lp["symptom_post_patch_passed"],
        "test_patch_clean": lp["test_patch_applied_cleanly"],
        "merge_acceptable": trow["merge_acceptable"],
        "resolved_in_dataset": trow["resolved_in_dataset"],
    }


REJECT_INTERPRETATION = {
    "sympy__sympy-14248": {
        "decisive_basis": ("REJECT is jointly supported by (1) a declared "
            "FAIL_TO_PASS that genuinely still fails and (2) two fresh scoped "
            "regressions."),
        "real_f2p_failure": ("test_MatrixSymbol_printing is PARTIAL_FAIL: it "
            "raises a real AssertionError in test_pretty.py "
            "(\"'-A*B - B*C + A*B*C' == '-A*B -B*C + A*B*C'\") while PASSED "
            "in test_str.py/test_latex.py; test_MatrixElement_printing passes "
            "everywhere. It is NOT an old-SymPy XFail/Skipped override."),
        "p2p_regressions": ("test_haramard and test_matMul were PASSED at the "
            "clean baseline (test_julia/test_octave/test_latex) and FAILED/"
            "TypeError 'cannot determine truth value of Relational' after the "
            "candidate: genuine candidate-induced scoped regressions."),
        "environment_separation": ("test_latex_Float was already FAILED "
            "('inf' != '\\\\infty') at baseline, so it is classified "
            "preexisting-bad and correctly NOT counted as a regression."),
        "scoped_relationship": ("Scope = 28 printing test files, 433 declared "
            "scoped P2P (= full-dataset P2P n for this issue). The verdict is "
            "a LOCAL execution fact and is label-independent of "
            "resolved_in_dataset=False."),
    },
    "sympy__sympy-15875": {
        "decisive_basis": ("REJECT is supported by a SINGLE decisive fact: the "
            "only declared FAIL_TO_PASS test genuinely still fails. It is "
            "independent of P2P and of environment factors."),
        "real_f2p_failure": ("test_Add_is_zero raises a real "
            "'assert True is None' (test_arit.py:1991) after the candidate; it "
            "is not an XFail/Skipped override. That one persistent F2P failure "
            "is decisive on its own."),
        "p2p_regressions": ("Among the 80 DECLARED scoped P2P names there are "
            "0 regressions and 0 pre-existing-bad names; the five baseline "
            "XFail nodes (Recursion/ZeroDivision-type elsewhere) are recovered "
            "by terminal-summary overrides."),
        "environment_separation": ("No declared-P2P environment failure drives "
            "the verdict."),
        "scoped_relationship": ("Scope = 4 core test files, 80 declared scoped "
            "P2P (= full-dataset n). REJECT does NOT depend on "
            "resolved_in_dataset=False."),
        "instrument_blind_spot_disclosed": ("Two COLLATERAL, UNDECLARED nodes "
            "in the batched core file (test_subs_in_derivative: RecursionError; "
            "test_nfloat: ZeroDivisionError) PASSED at baseline but FAILED "
            "after. They are not in the dataset's declared PASS_TO_PASS id set, "
            "so the SWE-bench-style scoped scorer (which judges declared ids "
            "only) does not count them; they are nonetheless candidate-era "
            "failures in executed scope files and are an honest instrument "
            "coverage blind spot. They do not change the REJECT (already "
            "decided by the F2P failure) but must not be hidden."),
    },
}


ACCEPT_BLIND_SPOTS = [
    "Only the ATTESTED SCOPED P2P subset was executed (test_patch files + "
    "tests/ adjacent to changed code files); the full dataset P2P suite was "
    "not run, so ACCEPT == scoped acceptability, not full-suite acceptance.",
    "Regressions in NON-adjacent / distant modules are not exercised.",
    "Old-SymPy XFail/Skipped tests are recovered via terminal-summary "
    "overrides; genuine flake/xfail interactions in a single re-run cannot be "
    "fully separated without repetition.",
    "Batched whole scope files can contain UNDECLARED collateral failing "
    "nodes that are not scored (see per-issue collateral list).",
    "Performance, style, non-functional behaviour and alternative-patch / "
    "other-generator equivalence are not validated.",
    "Symptom-gone is demonstrated by a hand-written probe derived from the "
    "public report, not by an independent maintainer oracle.",
]


def audit_probe_19495():
    note = K.read_json(K.G3C1_PROBE_NOTE)
    failures = K.read_jsonl(K.G3C1 / "g3c1_failures.jsonl")
    selftest = K.read_json(K.G3C1 / "audit" / "g3c1_probe_selftest.json")
    probe_path = PROBED / "sympy__sympy-19495.py"
    probe_bytes = probe_path.read_bytes()
    probe_sha = K.sha256_bytes(probe_bytes)
    frozen_sha = next(e["sha256"] for e in K.read_json(K.G3C1_FREEZE)["files"]
                      if e["relpath"] == "probes/sympy__sympy-19495.py")
    strengthened_assertions = [
        "(1) if a ConditionSet survives, its bound dummy args[0] must remain a "
        "Symbol (rejects the observed ConditionSet(1/3, ...)).",
        "(2) plain cs.subs(y,1/3) must equal the report's own correct "
        "reference via xreplace and simultaneous=True.",
        "(3) no free substituted symbol y may remain in the result.",
    ]
    weak_assertions = [
        "checked only that a free symbol y was present/absent and that the "
        "result did not collapse to the singleton {1/3}; neither distinguishes "
        "the malformed ConditionSet(1/3,...) from the correct ImageSet, so the "
        "weak probe exited 0 at BOTH baseline and post-candidate.",
    ]
    return {
        "instance_id": "sympy__sympy-19495",
        "original_problem": ("Plain ConditionSet.subs over-substitutes the "
            "ConditionSet's own bound dummy x to 1/3, producing the malformed "
            "ConditionSet(1/3, Contains(1/3, ImageSet(...)), ImageSet(...)) "
            "reported publicly; the candidate fixes it to "
            "ImageSet(Lambda(n, 2*pi*n+asin(1/3)), Integers)."),
        "initial_instrument_failure": {
            "recorded_at": failures[0]["recorded_at"],
            "stage": failures[0]["stage"],
            "baseline_probe_passed": failures[0]["baseline_probe_passed"],
            "post_candidate_probe_passed":
                failures[0]["post_candidate_probe_passed"]},
        "weak_probe_assertions": weak_assertions,
        "strengthened_probe_assertions": strengthened_assertions,
        "evidence_source": ("assertions derived ONLY from the public issue "
            "report; maintainer test_patch/test_subs_CondSet never consulted "
            "(maintainer_test_patch_consulted=%s)"
            % note["maintainer_test_patch_consulted"]),
        "baseline_vs_post_evidence": ("At the clean base plain subs produced "
            "the malformed ConditionSet(1/3,...); after the candidate it became "
            "the correct ImageSet and xreplace/simultaneous references matched. "
            "The issue genuinely reproduces and the candidate genuinely fixes "
            "it - a probe-authoring defect, not a non-evaluable issue."),
        "post_revision_gate": {"n_issues": selftest["n_issues"],
                               "all_probes_flip": selftest["all_probes_flip"]},
        "no_gold_changed": note["no_gold_changed"],
        "no_issue_replaced": note["no_issue_replaced"],
        "frozen_probe": {"path": "probes/sympy__sympy-19495.py",
                         "bytes": len(probe_bytes),
                         "sha256": probe_sha,
                         "matches_freeze_manifest": probe_sha == frozen_sha,
                         "read_only_not_modified": probe_sha == frozen_sha},
    }


def main():
    K.ensure_out_dirs()
    truth = {r["instance_id"]: r for r in K.read_jsonl(K.G3C1_TRUTH)}
    issues = {}
    for iid in K.PILOT_ISSUES:
        issues[iid] = audit_issue(iid, truth[iid])

    rejects = {iid: {**issues[iid], "interpretation":
                     REJECT_INTERPRETATION[iid]}
               for iid in K.REJECT_ISSUES}
    accepts = {}
    for iid in K.ACCEPT_ISSUES:
        a = issues[iid]
        sufficiency = (
            not a["recalc"]["f2p_failed_ids"]
            and not a["recalc"]["p2p_regressed_ids"]
            and not a["symptom_pre_passed"] and a["symptom_post_passed"]
            and a["test_patch_clean"]
            and a["recomputation_matches_stored_artifact"])
        accepts[iid] = {
            **a,
            "supports_scoped_acceptability": sufficiency,
            "scoped_basis": ("all declared F2P transition fail(base)->pass, "
                "0 declared scoped P2P regressions, symptom gone, test_patch "
                "clean; this supports SCOPED acceptability only."),
            "blind_spots": ACCEPT_BLIND_SPOTS,
            "behaviours_not_validated": ("full-dataset P2P, distant-module "
                "regressions, performance/style, alt-patch equivalence"),
        }

    all_recalc_match = all(v["recomputation_matches_stored_artifact"]
                           for v in issues.values())
    result = {
        "document": "G3-C.1.1 independent issue-level evidence review "
                    "(tasks 5+6+7)",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "parser_semantics": ("frozen evidence.builder.parse_node_logs + "
            "name_outcomes; bare name fails only if EVERY located node is "
            "FAILED/ERROR; old-SymPy XFail/Skipped recovered from terminal "
            "summary; name->file maps independently re-derived from raw logs."),
        "reject_issues": rejects,
        "accept_issues": accepts,
        "probe_19495_construct_audit": audit_probe_19495(),
        "all_independent_recomputations_match": all_recalc_match,
        "overall_pass": (
            all_recalc_match
            and all(not rejects[i]["recalc"]["f2p_failed_ids"] is None
                    for i in rejects)
            and all(accepts[i]["supports_scoped_acceptability"]
                    for i in accepts)
            and rejects["sympy__sympy-14248"]["recalc"]["p2p_regressed_ids"]
            and rejects["sympy__sympy-15875"]["recalc"]["f2p_failed_ids"]
            == ["test_Add_is_zero"]),
        "approved_scope": K.APPROVED_SCOPE,
    }
    K.write_canonical(K.OUT_AUDIT / "g3c11_issue_audit.json", result)
    print("all independent recomputations match stored:", all_recalc_match)
    for iid in K.REJECT_ISSUES:
        r = rejects[iid]["recalc"]
        print("REJECT", iid, "f2p_fail", r["f2p_failed_ids"],
              "reg", r["p2p_regressed_ids"],
              "pre", r["p2p_preexisting_bad_ids"],
              "collateral",
              len(rejects[iid]["collateral_undeclared_failing_nodes"]))
    for iid in K.ACCEPT_ISSUES:
        a = accepts[iid]
        print("ACCEPT", iid, "scoped_ok",
              a["supports_scoped_acceptability"], "collateral",
              len(a["collateral_undeclared_failing_nodes"]))
    print("19495 probe sha matches freeze:",
          result["probe_19495_construct_audit"]["frozen_probe"][
              "matches_freeze_manifest"])
    print("->", (K.OUT_AUDIT / "g3c11_issue_audit.json").relative_to(K.HERE))


if __name__ == "__main__":
    main()
