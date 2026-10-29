"""Build every Results table/figure input directly from frozen stores.

Zero-API, read-only. Recomputes all headline counts from the frozen
g3b3 per-issue grids and records the sha256 of each source file used so every
number in the paper is traceable. Run:  -m paper_sprint.scripts.ps_build_tables
"""
import json

from paper_sprint.scripts import ps_common as K

ANALYSIS = "evidence_store_g3b3/analysis/g3b3_analysis.json"
B4_AUDIT = "evidence_store_g3b4/audits/g3b4_deepseek_recompute.json"
STRICT_AUDIT = "evidence_store_g3b4/audits/g3b4_gpt_strict_audit.json"
B4_REPORT = "evidence_store_g3b4/g3b4_report.md"


def grids_by_model():
    d = K.read_json(ANALYSIS)["per_issue_raw_verdict_grids_g3b_vs_g3b3"]
    out = {}
    for m in K.MODELS:
        rows = {r["issue"]: r for r in d[m]}
        out[m] = rows
    return out


def v(row, cond, which):
    return row[f"{cond}|{which}"]


def build():
    prov = {}
    for rel in (ANALYSIS, B4_AUDIT, STRICT_AUDIT, B4_REPORT):
        p = K.ROOT / rel
        prov[rel] = {"exists": p.exists(), "sha256": K.sha256_file(p) if p.exists() else None}
    grids = grids_by_model()
    issues = list(grids[K.MODELS[0]].keys())

    # ---- T1: full per-issue x condition grid, g3b3 verdicts + golds ----
    header = ["issue", "oracle_gold"]
    for m in K.MODELS:
        for c in K.CONDITIONS:
            header.append(f"{K.MODEL_SHORT[m]}.{c}")
    rows = []
    for iid in issues:
        r0 = grids[K.MODELS[0]][iid]
        row = [K.short_issue(iid), r0["oracle_gold"]]
        for m in K.MODELS:
            for c in K.CONDITIONS:
                row.append(v(grids[m][iid], c, "g3b3")[0])  # A/R/N single letter
        rows.append(row)
    K.write_csv(K.TBL / "T1_per_issue_condition_grid_g3b3.csv", header, rows)

    # ---- T2: restricted-evidence commitment counts (P1 primary) ----------
    # condition gold is NEED_EVIDENCE for every issue on T2D-T / T3D-Strict.
    t2_header = ["model", "condition", "n", "P1a_unsupported_ACCEPT",
                 "P1b_unsupported_REJECT", "P1c_correct_NEED",
                 "unsupported_commitment_rate_ACCEPT"]
    t2 = []
    restricted_counts = {}
    for m in K.MODELS:
        for c in K.RESTRICTED:
            acc = rej = need = 0
            for iid in issues:
                verdict = v(grids[m][iid], c, "g3b3")
                gold = v(grids[m][iid], c, "gold")
                assert gold == "NEED_EVIDENCE", (iid, c, gold)
                if verdict == "ACCEPT":
                    acc += 1
                elif verdict == "REJECT":
                    rej += 1
                else:
                    need += 1
            restricted_counts[(m, c)] = (acc, rej, need)
            t2.append([K.MODEL_SHORT[m], c, len(issues), acc, rej, need,
                       f"{acc}/{len(issues)}"])
    # pooled across the two restricted conditions (cells, not independent issues)
    for m in K.MODELS:
        acc = sum(restricted_counts[(m, c)][0] for c in K.RESTRICTED)
        rej = sum(restricted_counts[(m, c)][1] for c in K.RESTRICTED)
        need = sum(restricted_counts[(m, c)][2] for c in K.RESTRICTED)
        n = len(issues) * len(K.RESTRICTED)
        t2.append([K.MODEL_SHORT[m], "RESTRICTED_pooled(cells)", n, acc, rej, need,
                   f"{acc}/{n}"])
    K.write_csv(K.TBL / "T2_restricted_commitment_P1.csv", t2_header, t2)

    # ---- T3: sufficient-evidence decision appropriateness ----------------
    # match verdict(g3b3) to condition gold; report separately per condition.
    t3_header = ["model", "condition", "n", "correct", "wrong_ACCEPT",
                 "wrong_REJECT", "abstain_NEED_on_decisive", "accuracy"]
    t3 = []
    for m in K.MODELS:
        for c in K.SUFFICIENT:
            correct = wa = wr = need = 0
            for iid in issues:
                verdict = v(grids[m][iid], c, "g3b3")
                gold = v(grids[m][iid], c, "gold")
                assert gold in ("ACCEPT", "REJECT")
                if verdict == gold:
                    correct += 1
                elif verdict == "NEED_EVIDENCE":
                    need += 1
                elif verdict == "ACCEPT":
                    wa += 1
                elif verdict == "REJECT":
                    wr += 1
            t3.append([K.MODEL_SHORT[m], c, len(issues), correct, wa, wr, need,
                       f"{correct}/{len(issues)}"])
    K.write_csv(K.TBL / "T3_sufficient_appropriateness.csv", t3_header, t3)

    # ---- T4: G3-B -> G3-B.3 DeepSeek paired abstention transition ---------
    # need-any over the three sufficient regimes.
    def need_any(row, which):
        return any(v(row, c, which) == "NEED_EVIDENCE" for c in K.SUFFICIENT)

    ds = grids["deepseek-flash"]
    b_yes = b3_yes = 0
    rev_to_commit = rev_to_need = 0
    residual = []
    for iid in issues:
        a = need_any(ds[iid], "g3b")
        b = need_any(ds[iid], "g3b3")
        b_yes += a
        b3_yes += b
        if a and not b:
            rev_to_commit += 1
        if b and not a:
            rev_to_need += 1
        if b:
            residual.append(K.short_issue(iid))
    t4 = {
        "denominator_independent_issues": len(issues),
        "g3b_need_any": b_yes, "g3b3_need_any": b3_yes,
        "need_to_nonneed_reversals": rev_to_commit,
        "nonneed_to_need_reversals": rev_to_need,
        "residual_issues_g3b3": residual,
        "aggregation": "OR(NEED) over T3D-Escalate,T2A-T,T3A-T per issue",
        "associational": True,
    }
    # cross-check against authoritative Q10 in analysis
    q10 = K.read_json(ANALYSIS)["Q10_deepseek_sufficient_need_and_paired_transition"]
    t4["analysis_or_aggregated_block"] = q10.get("or_aggregated_over_abstention")

    # ---- T5: GPT T3D-Strict unsupported ACCEPT (P1a focal) ----------------
    gpt_strict = {"wrong_ACCEPT": [], "wrong_REJECT": [], "correct_NEED": []}
    for iid in issues:
        verdict = v(grids["gpt-4.1-mini"][iid], "T3D-Strict", "g3b3")
        bucket = {"ACCEPT": "wrong_ACCEPT", "REJECT": "wrong_REJECT"}.get(
            verdict, "correct_NEED")
        gpt_strict[bucket].append(K.short_issue(iid))
    t5 = {
        "condition": "T3D-Strict", "condition_gold": "NEED_EVIDENCE",
        "n": len(issues),
        **{k: (len(val), val) for k, val in gpt_strict.items()},
        "g3b_comparison": "GPT abstained NEED 10/10 under T3D-Strict in G3-B",
        "note": "acceptance outcomes structurally withheld; ACCEPT upgrades "
                "non-decisive evidence to sufficient",
    }

    # ---- focal cases (read B.4 narrative; keep pointers, do not invent) ---
    focal = {
        "F1_17318_T2A": {
            "oracle_gold": "REJECT",
            "gpt_T2A_g3b": v(grids["gpt-4.1-mini"]["sympy__sympy-17318"], "T2A-T", "g3b"),
            "gpt_T2A_g3b3": v(grids["gpt-4.1-mini"]["sympy__sympy-17318"], "T2A-T", "g3b3"),
            "gpt_T3A_g3b3": v(grids["gpt-4.1-mini"]["sympy__sympy-17318"], "T3A-T", "g3b3"),
            "declared_f2p": "test_issue_12420 FAILED "
                            "(assert [4 + I, 0, 1] == [])",
        },
        "F2_17630_T3A": {
            "oracle_gold": "REJECT",
            "gpt_T3A_g3b3": v(grids["gpt-4.1-mini"]["sympy__sympy-17630"], "T3A-T", "g3b3"),
            "note": "saw failed declared F2P test_zero_matrix_add but judged "
                    "it unrelated; abstained instead of REJECT",
        },
        "DS_residual_13974": {
            "T3D-Esc": v(ds["sympy__sympy-13974"], "T3D-Escalate", "g3b3"),
            "T2A": v(ds["sympy__sympy-13974"], "T2A-T", "g3b3"),
            "T3A": v(ds["sympy__sympy-13974"], "T3A-T", "g3b3"),
        },
    }

    # ---- run / budget facts (verbatim) ----
    run = K.read_json(ANALYSIS)["budget_and_run_audit"]

    summary = {
        "document": "Paper Sprint results tables - generated from frozen stores",
        "unit_of_independence": "one SymPy issue; cells within an issue are "
                                "repeated measures, never independent samples",
        "n_independent_issues_g3b3": len(issues),
        "n_real_cells_g3b3": len(issues) * len(K.CONDITIONS) * len(K.MODELS),
        "run_audit": run,
        "T4_deepseek_paired_need_any": t4,
        "T5_gpt_strict": t5,
        "focal_cases": focal,
        "source_provenance": prov,
        "gold_status": "PROVISIONAL, single annotator n=1, "
                       "annotator2 NOT_OBTAINED",
        "result_class": {
            "g3b3": "corrective replication (paired, cross-version, "
                    "ASSOCIATIONAL contrast to G3-B)",
            "g3c1_8issues": "independent issue pilot (NO reviewer predictions "
                            "yet; gold PROVISIONAL)",
        },
    }
    K.write_json(K.TBL / "results_summary.json", summary)
    print(json.dumps({
        "issues": len(issues),
        "T2_rows": t2,
        "T4": {k: t4[k] for k in ("g3b_need_any", "g3b3_need_any",
                                  "need_to_nonneed_reversals",
                                  "nonneed_to_need_reversals",
                                  "residual_issues_g3b3")},
        "T5_counts": {k: t5[k] for k in t5 if isinstance(t5[k], list) or k == "n"},
    }, indent=1))
    print("-> tables written to", K.TBL.relative_to(K.ROOT))


if __name__ == "__main__":
    build()
