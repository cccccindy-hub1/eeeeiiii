"""Result-class inventory: keep exploratory / corrective-replication /
independent-pilot findings strictly separate, each with frozen provenance.

Zero-API, read-only. Run: -m paper_sprint.scripts.ps_inventory
"""
from paper_sprint.scripts import ps_common as K

SOURCES = {
    "g3b3_analysis": "evidence_store_g3b3/analysis/g3b3_analysis.json",
    "g3b4_report": "evidence_store_g3b4/g3b4_report.md",
    "g3b4_ds": "evidence_store_g3b4/audits/g3b4_deepseek_recompute.json",
    "g3b4_strict": "evidence_store_g3b4/audits/g3b4_gpt_strict_audit.json",
    "g3b4_focal": "evidence_store_g3b4/audits/g3b4_gpt_focal_families.json",
    "g3b4_13974": "evidence_store_g3b4/audits/g3b4_sympy_13974_audit.json",
    "g3c11_report": "evidence_store_g3c11/report/g3c11_audit_report.json",
    "g3c11_verify": "evidence_store_g3c11/audit/g3c11_verification.json",
}

# class, finding, value, unit/denominator, source_key, caution
ROWS = [
    ("corrective_replication",
     "DeepSeek sufficient-evidence over-abstention drops after protocol repair",
     "9/10 -> 1/10 (NEED_ANY over T3D-Esc/T2A/T3A)",
     "10 independent issues, paired", "g3b4_ds",
     "ASSOCIATIONAL cross-version contrast; freshness/trust/activeness changed "
     "together; not a single-fix causal claim"),
    ("corrective_replication",
     "DeepSeek paired reversals",
     "8 need->commit, 0 commit->need; residual SymPy-13974",
     "10 issues", "g3b4_ds",
     "issue-cluster bootstrap 95% CI of paired difference 0.5-1.0, seed 417313"),
    ("corrective_replication",
     "Residual DeepSeek over-abstention",
     "SymPy-13974 NEED on T2A & T3D-Esc but ACCEPT on T3A; 2 wrong readings",
     "n=1 case", "g3b4_13974",
     "residual model policy/interpretation error; gold PROVISIONAL"),
    ("corrective_replication",
     "GPT T3D-Strict unsupported ACCEPT (P1a)",
     "7/10 ACCEPT, 0 REJECT, 3 correct NEED",
     "10 issues (condition gold NEED)", "g3b4_strict",
     "G3-B was 0/10; cross-version contrast confounded -> candidate mechanism"),
    ("corrective_replication",
     "GPT restricted-evidence abstention on static T2D-T",
     "10/10 correct NEED, both models, both gates",
     "10 issues", "g3b3_analysis",
     "static surface; no acceptance outcomes available"),
    ("corrective_replication",
     "GPT false acceptance ignoring visible F2P failure (P2 case)",
     "SymPy-17318/T2A ACCEPT though test_issue_12420 FAILED; T3A REJECT",
     "case (REJECT n=3 overall)", "g3b4_focal",
     "report as case, NOT a population false-accept rate"),
    ("corrective_replication",
     "GPT decision-policy over-abstention on a REJECT",
     "SymPy-17630/T3A REJECT->NEED (judged failed declared test 'unrelated')",
     "case", "g3b4_focal",
     "opposite error direction; never pool with false acceptance"),
    ("exploratory",
     "GPT unsupported acceptance on oracle-REJECT issues",
     "4/15 cells; sufficient OR-aggregate 2/3 issues",
     "3 REJECT issues x 5 cond", "g3b3_analysis",
     "CP95 [0.094,0.992], cluster bootstrap [0,1]; severely underpowered"),
    ("exploratory",
     "Active-evidence-induced over-commitment mechanism",
     "GPT Strict 0/10 (G3-B) -> 7/10 (G3-B.3); DeepSeek 0 in both",
     "10 issues", "g3b4_report",
     "NEW CANDIDATE MECHANISM only; needs activeness-only controlled arm"),
    ("exploratory",
     "Blind reason coding of the 7 over-commitments",
     "7/7 primary C3, co-fired C1+C2+C5; C4 never fired",
     "7 units", "g3b4_report",
     "single AI rule-based coder; NOT independent human coding"),
    ("independent_issue_pilot",
     "8 newly built independent SymPy issues (G3-C.1)",
     "6 scoped ACCEPT / 2 REJECT oracle gold",
     "8 issues", "g3c11_report",
     "gold 8/8 PROVISIONAL/PENDING; NO reviewer predictions run"),
    ("independent_issue_pilot",
     "Gold certificates across 5 conditions",
     "40 total: 24 sufficient / 16 NEED_EVIDENCE",
     "8 issues x 5", "g3c11_verify",
     "instrument plumbing; not model performance"),
    ("independent_issue_pilot",
     "Restricted-surface non-interference",
     "144 restricted surfaces, 0 forbidden hits; 456/456 HTTP; 40/40 mock",
     "8 issues", "g3c11_verify",
     "mock 40/40 is engineering only, research-excluded; not a model metric"),
    ("independent_issue_pilot",
     "Natural vs REJECT-enriched cohorts",
     "4 natural + 4 enriched, zero issue overlap",
     "75->51->8 funnel", "g3c11_report",
     "pilot-stage adaptive priority (TRAP>P2P>F2P); do NOT pool natural rates"),
    ("not_yet_run",
     "G3-C.1 external validation 80 cells",
     "8 issues x 5 conditions x 2 models",
     "planned only", "g3c11_report",
     "0 reviewer predictions exist; never fill Results with hypothetical cells"),
]


def main():
    shas = {k: K.sha256_file(K.ROOT / p) for k, p in SOURCES.items()}
    header = ["result_class", "finding", "value", "unit_denominator",
              "source_file", "source_sha256", "caution"]
    out = []
    for cls, finding, value, unit, skey, caution in ROWS:
        out.append([cls, finding, value, unit, SOURCES[skey],
                    shas[skey], caution])
    K.write_csv(K.TBL / "result_inventory.csv", header, out)
    md = ["# Result-class inventory (Paper Sprint)\n",
          "Each empirical finding is tagged with exactly one class; classes "
          "are never pooled as one independent test set.\n",
          "- **corrective_replication** = G3-B.3 paired re-run on the same 10 "
          "issues over the repaired protocol (cross-version, associational).",
          "- **exploratory** = underpowered / mechanism-generating analyses.",
          "- **independent_issue_pilot** = G3-C.1 eight NEW issues; gold "
          "PROVISIONAL, no model predictions yet.",
          "- **not_yet_run** = planned 80-cell validation; no data exist.\n",
          "| class | finding | value | unit | source | caution |",
          "|---|---|---|---|---|---|"]
    for cls, finding, value, unit, sfile, sha, caution in out:
        md.append("| {} | {} | {} | {} | `{}` | {} |".format(
            cls, finding, value, unit, sfile, caution))
    K.write_text(K.TBL / "result_inventory.md", "\n".join(md) + "\n")
    print("rows:", len(out), "-> result_inventory.csv/.md")


if __name__ == "__main__":
    main()
