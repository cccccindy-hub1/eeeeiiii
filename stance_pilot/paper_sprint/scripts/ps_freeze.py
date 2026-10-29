"""Write paper_sprint/INDEX.md and a self-contained freeze manifest (sha256).

Read-only over all frozen history; writes only inside paper_sprint/. Does NOT
modify any G3-A..G3-C.1.1 artifact. Zero API.
Run: -m paper_sprint.scripts.ps_freeze
"""
import hashlib

from paper_sprint.scripts import ps_common as K

INCLUDE_DIRS = ["scripts", "tables", "figures", "paper", "latex",
                "experiment80", "human", "checklists"]
SELF = "paper_sprint/freeze/paper_sprint_manifest.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    entries = []
    for d in INCLUDE_DIRS:
        base = K.PS / d
        for p in sorted(base.rglob("*")):
            if not p.is_file() or "__pycache__" in p.parts or \
                    p.suffix in (".pyc",):
                continue
            rel = p.relative_to(K.ROOT).as_posix()
            entries.append({"relpath": rel, "sha256": sha(p),
                            "bytes": p.stat().st_size})
    # source pins actually consumed
    pins = {}
    for rel in [
        "evidence_store_g3b3/analysis/g3b3_analysis.json",
        "evidence_store_g3b4/g3b4_report.md",
        "evidence_store_g3b4/audits/g3b4_deepseek_recompute.json",
        "evidence_store_g3b4/audits/g3b4_gpt_strict_audit.json",
        "evidence_store_g3b4/audits/g3b4_gpt_focal_families.json",
        "evidence_store_g3b4/audits/g3b4_sympy_13974_audit.json",
        "evidence_store_g3c11/freeze/g3c11_freeze_manifest.json",
    ]:
        p = K.ROOT / rel
        pins[rel] = {"exists": p.exists(),
                     "sha256": sha(p) if p.exists() else None}
    manifest = {
        "package": "GroundedReview Paper Sprint v2 (adds G3-C.1 80-cell live "
                   "exploratory validation; v1 zero-API draft PDF preserved)",
        "api_calls": 162, "issues_added": 8, "git_commits": 0,
        "history_frozen_artifacts_modified": False,
        "gold_status": "18/18 PROVISIONAL/PENDING, annotator2 NOT_OBTAINED",
        "experiment80_status": (
            "COMPLETE_80: 8 G3-C.1 issues x 2 models x 5 conditions = 80 real "
            "cells, 162 calls (DeepSeek 88 / GPT 74), guard-ledger spend "
            "$0.258198 (exact token-by-price $0.2581976; per-cell-rounded "
            "ledger sum $0.258199, a $0.000001 rounding accumulation) under "
            "$2.00 total / $1.00 per-model hard caps; 0 retries, terminal "
            "errors, response-format downgrades, resume-skips; raw-first, "
            "sha-verified; PROVISIONAL gold, Exploratory Independent-Issue "
            "Validation, not human-arbitrated benchmark. "
            "See experiment80/RESULTS_REAL.json, ANALYSIS_RESULTS.md, "
            "TERNARY_MATRIX_AND_ISSUES.json and evidence_store_g3c1_live/."),
        "files": sorted(entries, key=lambda e: e["relpath"]),
        "frozen_source_pins": pins,
    }
    mpath = K.ROOT / SELF
    mpath.parent.mkdir(parents=True, exist_ok=True)
    K.write_json(mpath, manifest)
    digest = hashlib.sha256(mpath.read_bytes()).hexdigest()

    # index
    by = {}
    for e in manifest["files"]:
        top = e["relpath"].split("/")[1]
        by.setdefault(top, []).append(e["relpath"].split("/", 2)[-1])
    idx = ["# GroundedReview Paper Sprint - package index", "",
           "Zero-API draft package. History (G3-A..G3-C.1.1) untouched. "
           "Gold **PROVISIONAL**; 80-cell run **not authorized**.", "",
           "## Read in this order",
           "1. `paper/paper_draft.md` - full 11-section draft.",
           "1b. `latex/main.tex` - submission LaTeX project (pdflatex + "
           "bibtex; native TikZ figures; `references.bib`).",
           "2. `tables/result_inventory.md` - every finding tagged "
           "corrective/exploratory/pilot with source sha.",
           "3. `tables/results_summary.json` - all headline counts + provenance.",
           "4. `figures/` - fig1 concept, fig2 DeepSeek 9->1, fig3 GPT strict, "
           "fig4 focal 17318.",
           "5. `experiment80/PRE_CALL_GATES.md` + `experiment80_config.json` - "
           "capped 80-cell pre-experiment (no calls).",
           "6. `checklists/` - claim_audit, missing_evidence, submission_readiness.",
           "7. `human/HUMAN_ADJUDICATION_HANDOFF.md` - 18 packets + FR1/FR2.",
           "", "## Regenerate (offline, $0)",
           "`-m paper_sprint.scripts.ps_build_tables`; "
           "`...ps_inventory`; `...ps_build_figures`; "
           "`...ps_make_experiment80`; `...ps_analyze_experiment80`; "
           "`...ps_make_human_and_checklists`; then `...ps_freeze`.", "",
           "## Contents"]
    for top in INCLUDE_DIRS:
        idx.append(f"### {top}/")
        for f in by.get(top, []):
            idx.append(f"- {f}")
        idx.append("")
    idx += [f"Manifest: `{SELF}` (sha256 {digest}); "
            f"{len(entries)} hashed deliverable files.", ""]
    K.write_text(K.PS / "INDEX.md", "\n".join(idx))
    print("files:", len(entries), "manifest sha:", digest[:16],
          "pins:", len(pins))


if __name__ == "__main__":
    main()
