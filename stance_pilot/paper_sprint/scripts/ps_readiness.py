"""Final experimental readiness for the planned 80-cell validation (ZERO API).

Reuses the FROZEN production code paths unchanged and exercises them offline:
  * real g3c1 HTTP server (projection v2) on a tempdir COPY of the frozen store;
  * every restricted tool path for all 8 issues, full bodies scanned with the
    frozen g3b4 scanner (tier-1 forbidden + tier-2 pass_to_pass_baseline);
  * strict 403 / escalate 400->reason->200 / ungated tier A;
  * 40-cell frozen scripted mock (issue x condition; model-agnostic plumbing);
  * CompositeGuard + BudgetGuard at the NEW caps $2.00 total / $1.00 model;
  * resume gate (_prior_spent_and_done) and served-model-id hard-stop.

Writes ONLY into paper_sprint/experiment80/. Calls NO model and NO external
network (127.0.0.1 only). Does not modify any frozen artifact.

Run: -m paper_sprint.scripts.ps_readiness
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from paper_sprint.scripts import ps_common as K
from evidence import g3c1_common as C
from evidence import g3c1_server as GS
from evidence import g3c1_mock as MOCK
from evidence import g3b4_strict_audit as SCAN
from evidence.store import ArtifactStore
from evidence.schemas import make_artifact_id
from evidence.views import display_for_tier, evidence_block
from evidence.g3c0_projection_v2 import project_diagnostic_v2
from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.g3b3_run import CompositeGuard, assert_served_model, \
    _prior_spent_and_done

OUT_JSON = K.PS / "experiment80" / "READINESS.json"

TOTAL_CAP = 2.00
MODEL_CAP = 1.00


def http(base, method, path, obj=None):
    data = json.dumps(obj).encode("utf-8") if obj is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode("utf-8"), dict(he.headers)


def truth_fixtures():
    fxs = []
    for t in C.read_jsonl(C.TRUTH):
        lp = t.get("label_provenance", {})
        fxs.append({
            "instance_id": t["instance_id"], "base_commit": t["base_commit"],
            "patch_sha256": t["patch_sha256"],
            "served_artifact_id": make_artifact_id(t["instance_id"],
                                                   t["patch_sha256"]),
            "symptom": {"pre_patch_passed": lp.get("symptom_pre_patch_passed"),
                        "post_patch_passed": lp.get("symptom_post_patch_passed")}})
    fxs.sort(key=lambda x: x["instance_id"])
    return fxs


def open_session(base, fx, tier, policy):
    st, body, _ = http(base, "POST", "/sessions", {
        "instance_id": fx["instance_id"], "base_commit": fx["base_commit"],
        "patch_sha256": fx["patch_sha256"],
        "cell": f'readiness:{fx["instance_id"]}:{tier}:{policy}',
        "served_artifact_id": fx["served_artifact_id"],
        "evidence_tier": tier, "policy": policy,
        "claim": "This fix is correct and all relevant tests pass.",
        "symptom": fx["symptom"]})
    assert st == 201, (st, body)
    return json.loads(body)["session_id"]


def probe_surfaces(base, fxs):
    """Full-body scan of every restricted tool path + static render."""
    surfaces = []
    for fx in fxs:
        iid = fx["instance_id"]
        # strict tier D: artifact + denied f2p body
        sid = open_session(base, fx, "D", "strict")
        st, body, _ = http(base, "GET", f"/sessions/{sid}/artifact")
        surfaces.append((f"{iid}:D-strict:artifact:{st}", "D", True, body))
        s403, b403, _ = http(base, "GET", f"/sessions/{sid}/log/f2p")
        surfaces.append((f"{iid}:D-strict:logf2p:{s403}", "D", True, b403))
        # escalate tier D: reason-LESS 400 body (in scope); then granted 200
        sid2 = open_session(base, fx, "D", "escalate")
        s400, b400, _ = http(base, "GET", f"/sessions/{sid2}/log/f2p")
        surfaces.append((f"{iid}:D-esc:logf2p_noreason:{s400}", "D", True, b400))
        s200, b200, h200 = http(
            base, "GET", f"/sessions/{sid2}/log/f2p?reason=readiness%20probe")
        surfaces.append((f"{iid}:D-esc:logf2p_reason:{s200}", "D", False, b200))
        # tier A (institutional; outcomes allowed, hidden gold not)
        sid3 = open_session(base, fx, "A", "escalate")
        stA, bodyA, _ = http(base, "GET", f"/sessions/{sid3}/artifact")
        surfaces.append((f"{iid}:A:artifact:{stA}", "A", False, bodyA))
    # static renders straight from the frozen store
    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name="g3c1_fixtures_meta.json")
    for fx in fxs:
        t = next(x for x in C.read_jsonl(C.TRUTH)
                 if x["instance_id"] == fx["instance_id"])
        rec, authentic = store.get(fx["served_artifact_id"])
        assert authentic, fx["instance_id"]
        v2 = project_diagnostic_v2(
            display_for_tier(store, rec, fx["instance_id"],
                             fx["patch_sha256"], "D"))
        surfaces.append((f'{fx["instance_id"]}:static:T2D-block', "D", True,
                         evidence_block(v2, "D", symptom=fx["symptom"])))
        surfaces.append((f'{fx["instance_id"]}:static:v2-json', "D", True,
                         json.dumps(v2, ensure_ascii=False)))
    return surfaces


def evaluate_surfaces(surfaces):
    GOLD_KEYS = ("oracle_gold", "condition_gold", "ground_truth_verdict",
                 "_oracle_gold", "label_class")
    rows = []
    violations = []
    nD = t1 = t2 = basehits = 0
    for name, tier, restricted, text in surfaces:
        a, b, _ = SCAN._scan_text(text)
        bmap = "pass_to_pass_baseline" in text
        gold = [k for k in GOLD_KEYS if k in text.lower()]
        if restricted:
            nD += 1
            t1 += len(a)
            t2 += len(b)
            if bmap:
                basehits += 1
        if restricted and (a or b or bmap):
            violations.append({"surface": name, "tier1": a[:3], "tier2": b[:3],
                               "baseline_field_present": bmap})
        if gold:
            violations.append({"surface": name, "hidden_gold_keys": gold})
        rows.append({"name": name, "tier": tier, "restricted_scannable":
                     restricted, "tier1": len(a), "tier2": len(b),
                     "baseline_field_present": bmap if restricted else None,
                     "gold_key_hits": gold, "http_or_static": name})
    return rows, violations, {"n_restricted": nD, "tier1": t1, "tier2": t2,
                              "baseline_field_hits": basehits}


def gate_codes_from_mock(rows):
    strict = [r for r in rows if r["condition"] == "T3D-Strict"]
    esc = [r for r in rows if r["condition"] == "T3D-Escalate"]
    t3a = [r for r in rows if r["condition"] == "T3A-T"]
    return {
        "n_strict": len(strict),
        "strict_all_403": all(r["strict_denied_403"] for r in strict),
        "n_escalate": len(esc),
        "escalate_all_400_then_reason_200": all(
            any(seq.startswith("f2p_no_reason:400") for seq in r["escalation_sequence"])
            and any(seq.startswith("f2p_reason:200") for seq in r["escalation_sequence"])
            for r in esc),
        "n_t3a": len(t3a),
        "active_diag_all_v2_tag": all(
            r["saw_projection_v2_tag"]
            for r in rows if r["condition"] in ("T3D-Strict", "T3D-Escalate")),
        "tier_d_baseline_leak_cells": sum(
            1 for r in rows if r["saw_baseline_map_at_tier_d"] is True),
    }


def budget_tests():
    # Frozen prices for the two approved models.
    prices = {"deepseek-flash": (0.30, 1.20), "gpt-4.1-mini": (0.40, 1.60)}
    checks = []
    for model, (pin, pout) in prices.items():
        total = BudgetGuard(TOTAL_CAP, pin, pout, completion_cap_tokens=8192,
                            max_model_calls_per_cell=12)
        mg = CompositeGuard(MODEL_CAP, total, pin, pout,
                            completion_cap_tokens=8192,
                            max_model_calls_per_cell=12)
        # a normal small call is allowed under both caps
        b = mg.check(2000, 0)
        ok_allow = b > 0
        # per-cell model-call hard cap
        cap_raised = False
        try:
            mg.check(2000, 12)
        except BudgetGuardStop:
            cap_raised = True
        # force the per-model cap to be reached and confirm it blocks even
        # though the shared TOTAL cap would still have room
        mg.spent = MODEL_CAP - 0.0001
        model_blocks = False
        try:
            mg.check(4000, 1)
        except BudgetGuardStop:
            model_blocks = True
        # independent total-only guard blocks at $2
        t2g = BudgetGuard(TOTAL_CAP, pin, pout)
        t2g.spent = TOTAL_CAP - 0.0001
        total_blocks = False
        try:
            t2g.check(4000, 0)
        except BudgetGuardStop:
            total_blocks = True
        checks.append({"model": model, "normal_call_allowed": ok_allow,
                       "per_cell_call_cap_blocks": cap_raised,
                       "per_model_1usd_blocks_with_total_room": model_blocks,
                       "total_2usd_blocks": total_blocks})
    return checks


def model_id_tests():
    out = []
    # exact approved ids pass
    assert_served_model("deepseek-flash", "deepseek-flash", "c")
    assert_served_model("gpt-4.1-mini-2025-04-14", "gpt-4.1-mini-2025-04-14", "c")
    out.append({"case": "exact_match_passes", "ok": True})
    drift = False
    try:
        assert_served_model("gpt-4.1-mini-2099-01-01",
                            "gpt-4.1-mini-2025-04-14", "c")
    except SystemExit:
        drift = True
    out.append({"case": "id_drift_hard_stops", "ok": drift})
    none_ok = True
    assert_served_model(None, "gpt-4.1-mini-2025-04-14", "c")  # must not raise
    out.append({"case": "none_does_not_trip", "ok": none_ok})
    return out


def resume_tests():
    d = tempfile.mkdtemp(prefix="ps_resume_")
    p = K.Path(d) / "rows.jsonl"
    rows = [
        {"cell": "a", "cost_usd": 0.01, "mock": False},
        {"cell": "b", "cost_usd": 0.02, "mock": False},
        {"cell": "m", "cost_usd": 0.0, "mock": True},  # mock never counted
        {"cell": "e", "cost_usd": 0.0, "mock": False,
         "error": "TransportError"},  # resume-eligible
        {"cell": "s", "cost_usd": 0.03, "mock": False,
         "error": "ScoringError:x"},  # terminal (paid raw landed)
    ]
    with p.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    spent, done = _prior_spent_and_done(p)
    shutil.rmtree(d, ignore_errors=True)
    return {"restored_spent_usd": round(spent, 6),
            "spent_expect": 0.06,
            "spent_ok": abs(spent - 0.06) < 1e-9,
            "terminal_done": sorted(done),
            "done_ok": sorted(done) == ["a", "b", "s"],
            "transport_error_resume_eligible": "e" not in done}


def main():
    fxs = truth_fixtures()
    assert len(fxs) == 8, len(fxs)
    tmp = tempfile.mkdtemp(prefix="ps_readiness_store_")
    shutil.copytree(str(C.OUT_STORE), tmp, dirs_exist_ok=True)
    httpd = GS.build_g3c1_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        surfaces = probe_surfaces(base, fxs)
        surf_rows, violations, counts = evaluate_surfaces(surfaces)
        mock_rows = MOCK.run()  # tempdir-isolated, writes nothing itself
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    mock_agree = sum(1 for r in mock_rows
                     if r["mock_matches_condition_gold"])
    gating = gate_codes_from_mock(mock_rows)
    budget = budget_tests()
    modelids = model_id_tests()
    resume = resume_tests()

    # raw-first is structural in the frozen runner (cannot execute live here):
    # cite the exact lines rather than claim a runtime test.
    raw_first = {
        "verified_by": "code inspection only (no live call permitted)",
        "raw_persisted_before_scoring": "evidence/g3b3_run.py L703-715",
        "scoring_error_terminal_no_second_paid_call":
            "evidence/g3b3_run.py L716-734",
        "pre_call_guard_before_http": "evidence/g3b3_run.py L249-251, L270",
    }

    checks = {
        "n_issues": 8, "n_surfaces_probed": len(surf_rows),
        "surface_counts": counts,
        "surface_violations": violations,
        "noninterference_clean": counts["tier1"] == 0 and counts["tier2"] == 0
        and counts["baseline_field_hits"] == 0 and not violations,
        "mock": {"n_cells_issue_x_condition": len(mock_rows),
                 "mock_matches_condition_gold": mock_agree,
                 "mock_is_research_excluded": True, **gating},
        "budget_caps_usd": {"total": TOTAL_CAP, "per_model": MODEL_CAP},
        "budget_checks": budget,
        "model_id_checks": modelids,
        "resume_check": resume,
        "raw_first_persistence": raw_first,
        "freshness_via_http": "mock exercised GET /freshness over real server; "
                              "applicable cells require linked+fresh (8 issues "
                              "freshness 8/8 already frozen in g3c1 audit)",
        "api_calls_made": 0, "external_network": "none (127.0.0.1 only)",
    }

    # overall READY only on engineering gates; authorization/gold tracked apart
    eng_ready = (
        checks["noninterference_clean"]
        and mock_agree == len(mock_rows)
        and gating["strict_all_403"]
        and gating["escalate_all_400_then_reason_200"]
        and gating["active_diag_all_v2_tag"]
        and gating["tier_d_baseline_leak_cells"] == 0
        and all(all(v for kk, v in c.items() if kk.endswith(("allowed", "blocks")))
                for c in budget)
        and all(c["ok"] for c in modelids)
        and resume["spent_ok"] and resume["done_ok"]
    )
    blockers = []
    # engineering blockers
    if not eng_ready:
        blockers.append("one or more offline engineering checks failed "
                        "(see READY flags)")
    # non-engineering blockers that remain regardless of engineering
    blockers.append("AUTHORIZATION: no live API call approved; separate written "
                    "go required (80 cells, $2.00/$1.00).")
    blockers.append("GOLD AUTHORITY: annotator2 NOT_OBTAINED; any run is a "
                    "PROVISIONAL-GOLD EXPLORATORY pilot, not human-adjudicated "
                    "benchmark validation.")
    # runner binding note: frozen g3b3 runner caps are $3.0/$1.5; the 80-cell
    # live entrypoint must be parameterized to $2.0/$1.0 before execution.
    blockers.append("RUNNER BINDING: instantiate the live runner for the 8 g3c1 "
                    "issues with caps $2.00/$1.00 (the frozen g3b3 entrypoint "
                    "defaults to $3.00/$1.50 and the g3a store); guards "
                    "themselves are verified here at the new caps.")

    report = {
        "document": "Paper Sprint P1 final experimental readiness (zero API)",
        "engineering_ready_offline": eng_ready,
        "live_run_authorized": False,
        "verdict": "ENGINEERING_READY__BLOCKED_ON_AUTHORIZATION_AND_GOLD"
                   if eng_ready else "BLOCKED_ENGINEERING",
        "checks": checks,
        "remaining_blockers": blockers,
        "scope": "8 issues x 5 conditions x 2 models = 80 real cells; "
                 "no new issues/models/conditions; no re-runs to improve results",
        "source_code_reused": [
            "evidence/g3c1_server.py", "evidence/g3c0_projection_v2.py",
            "evidence/g3c1_mock.py", "evidence/g3b4_strict_audit.py",
            "evidence/views.py", "evidence/g3b3_run.py",
            "evidence/phase3_run.py"],
    }
    K.write_json(OUT_JSON, report)

    md = ["# 80-cell final readiness (zero API)", "",
          f"**Verdict: {report['verdict']}**", "",
          "## Offline engineering checks (real v2 HTTP server, tempdir store)",
          f"- surfaces probed: {len(surf_rows)}; restricted tier-D: "
          f"{counts['n_restricted']}",
          f"- tier-1 forbidden findings: **{counts['tier1']}**",
          f"- tier-2 pass_to_pass_baseline findings: **{counts['tier2']}**",
          f"- baseline field present on any restricted surface: "
          f"**{counts['baseline_field_hits']}**",
          f"- hidden-gold-key findings: "
          f"{sum(len(r['gold_key_hits']) for r in surf_rows)}",
          f"- non-interference clean: **{checks['noninterference_clean']}**",
          "", "## Full mock over the real server (research-excluded plumbing)",
          f"- cells (8 issues x 5 cond): {len(mock_rows)}; gold alignment "
          f"{mock_agree}/{len(mock_rows)}",
          f"- strict 403 on all {gating['n_strict']} strict cells: "
          f"**{gating['strict_all_403']}**",
          f"- escalate 400->reason->200 on all {gating['n_escalate']}: "
          f"**{gating['escalate_all_400_then_reason_200']}**",
          f"- active diagnostic cells carry v2 tag: "
          f"**{gating['active_diag_all_v2_tag']}**",
          f"- tier-D baseline leak cells: "
          f"**{gating['tier_d_baseline_leak_cells']}**",
          "", "## Guards / resume / model id at the NEW caps",
          f"- budget caps total/per-model: $ {TOTAL_CAP} / $ {MODEL_CAP}",
    ]
    for c in budget:
        md.append(f"  - {c['model']}: allow={c['normal_call_allowed']}, "
                  f"cell-cap={c['per_cell_call_cap_blocks']}, "
                  f"$1-model-blocks={c['per_model_1usd_blocks_with_total_room']}, "
                  f"$2-total-blocks={c['total_2usd_blocks']}")
    md += [f"- served-model-id checks: {modelids}",
           f"- resume: {resume}",
           "- raw-first persistence verified by code inspection only "
           "(live call not permitted): g3b3_run L703-734.",
           "", "## Remaining blockers (cannot be cleared offline)",
    ]
    for b in blockers:
        md.append(f"- {b}")
    md += ["", "**No model API was called; nothing frozen was modified; "
               "127.0.0.1 only.**"]
    K.write_text(K.PS / "experiment80" / "READINESS.md", "\n".join(md) + "\n")

    print("verdict:", report["verdict"])
    print("noninterference clean:", checks["noninterference_clean"],
          "tier1/t2/baseline:", counts["tier1"], counts["tier2"],
          counts["baseline_field_hits"])
    print("mock:", mock_agree, "/", len(mock_rows), "strict403:",
          gating["strict_all_403"], "esc400->200:",
          gating["escalate_all_400_then_reason_200"], "v2:",
          gating["active_diag_all_v2_tag"], "leak:",
          gating["tier_d_baseline_leak_cells"])
    print("budget/model/resume:",
          all(x for c in budget for k, x in c.items()
              if k.endswith(("allowed", "blocks"))),
          all(c["ok"] for c in modelids), resume["spent_ok"], resume["done_ok"])


if __name__ == "__main__":
    main()
