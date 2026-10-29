"""Assemble the human-adjudication handoff and the three paper checklists,
all derived from frozen artifacts. Zero-API. Does NOT register any human label.

Run: -m paper_sprint.scripts.ps_make_human_and_checklists
"""
import csv

from paper_sprint.scripts import ps_common as K

HUMAN = K.PS / "human"
CHK = K.PS / "checklists"

PLAN = "evidence_store_g3c11/human_annotation/g3c11_second_annotator_plan.json"
FOCUSED = "evidence_store_g3c11/human_annotation/g3c11_human_focused_review_items.json"
WORKSHEET = "evidence_store_g3c11/human_annotation/g3c11_annotator2_blank_labels.csv"
FOCUSED_CSV = "evidence_store_g3c11/human_annotation/g3c11_human_focused_review_worksheet.csv"

# blind packet mapping from frozen g3c11 plan (P-id -> issue)
G3C1_MAP = {"P01": "14248", "P02": "19495", "P03": "19346", "P04": "19040",
            "P05": "16886", "P06": "19637", "P07": "22914", "P08": "15875"}
G3A_MAP = {"P01": "24443", "P02": "13615", "P03": "19783", "P04": "20590",
           "P05": "17630", "P06": "21847", "P07": "15349", "P08": "24213",
           "P09": "17318", "P10": "13974"}


def human_handoff():
    plan = K.read_json(PLAN)
    focused = K.read_json(FOCUSED)
    shas = {p: K.sha256_file(K.ROOT / p) for p in
            (PLAN, FOCUSED, WORKSHEET, FOCUSED_CSV)}
    md = ["# Human adjudication handoff (18 packets + FR1/FR2)", "",
          "**Status: NOT OBTAINED.** This package prepares and tracks delivery; "
          "it enters no labels. Until a real annotator-2 independently submits, "
          "all 18 gold stay **PROVISIONAL/PENDING**. AI self-review never counts.",
          "",
          "## Delivery set",
          f"- G3-C.1: 8 blind packets (P01-P08); G3-A: 10 (P01-P10) = 18 total.",
          f"- blind seed: {plan.get('blind_seed','(see plan)')}; 9 files/packet; "
          "rubric labels ACCEPT/REJECT/NEEDS_REVIEW.",
          "- third senior human arbitrates any ACCEPT<->REJECT disagreement "
          "(never an LLM or the pipeline author).",
          "- priority order requested: 8 G3-C.1 first, then 10 G3-A.",
          "",
          "## Packet identity (revealed only after sealing; blinding PARTIAL)",
          "G3-C.1: " + ", ".join(f"{k}->{v}" for k, v in G3C1_MAP.items()),
          "G3-A:   " + ", ".join(f"{k}->{v}" for k, v in G3A_MAP.items()),
          "",
          "12/18 packets self-reference the issue number in symptom/probe/patch "
          "text -> identity blinding is PARTIAL; record de-blinding risk.",
          "",
          "## Focused reviews (mandatory, separate blank worksheet)",
    ]
    for it in focused["focused_items"]:
        md.append(f"- **{it['id']}**: {it['question']}  "
                  f"(ai_determination=null, human_decision=PENDING)")
    md += ["", "## Annotator requirements (frozen in plan)",
           "- Python/SymPy competence; able to read pytest output and diffs;",
           "- blind to all model outputs and prior labels;",
           "- independent time commitment recorded per packet;",
           "- disagreement -> senior arbiter; leave-one-issue-out sensitivity "
           "recomputed under annotator1 / annotator2 / adjudicated labels.",
           "",
           "## Source artifacts (read-only, sha256)",
    ]
    for p, s in shas.items():
        md.append(f"- `{p}`  `{s}`")
    md += ["", "Blank labels file: "
           "`evidence_store_g3c11/human_annotation/g3c11_annotator2_blank_labels.csv`; "
           "focused worksheet: `..._g3c11_human_focused_review_worksheet.csv`."]
    K.write_text(HUMAN / "HUMAN_ADJUDICATION_HANDOFF.md", "\n".join(md) + "\n")

    # tracking CSV (all PENDING)
    with (HUMAN / "human_review_tracking.csv").open("w", encoding="utf-8",
                                                    newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["set", "packet", "issue_revealed_after_unblind",
                    "oracle_gold_provisional", "annotator2_verdict",
                    "adjudicated", "arbiter_verdict", "date"])
        g = {}
        for pid, iss in G3C1_MAP.items():
            g[("G3-C.1", pid)] = iss
        for pid, iss in G3A_MAP.items():
            g[("G3-A", pid)] = iss
        goldmap = {"17318": "REJECT", "17630": "REJECT", "19783": "REJECT",
                   "14248": "REJECT", "15875": "REJECT"}
        for (s, pid), iss in g.items():
            w.writerow([s, pid, iss, goldmap.get(iss, "ACCEPT"),
                        "PENDING", "NO", "", ""])
    print("handoff + tracking written; labels entered: 0")


CLAIM_CHECKS = [
    ("do not", "Attribute G3-B -> G3-B.3 change to a single fix/cause",
     "Reported as associational cross-version contrast; freshness/trust/"
     "activeness changed together", "paper sec 7.2, 9.3", True),
    ("do not", "Treat AI coding/self-review as independent human arbitration",
     "annotator2 NOT_OBTAINED; gold PROVISIONAL; C3 coding labelled single-AI",
     "abstract, sec 8.1, 9.1", True),
    ("do not", "Claim 6 scoped ACCEPT passed whole SymPy suite",
     "Termed Scoped Oracle Acceptability; declared F2P/scoped P2P only",
     "sec 3.2, 9.5", True),
    ("do not", "Pool natural + REJECT-enriched cohorts for a natural rate",
     "Reported separately; sampling disclosed pilot-stage adaptive",
     "sec 5.2, 9.4", True),
    ("do not", "Present mock results as model performance",
     "40/40 (pilot) and mock cells research-excluded plumbing",
     "sec 5.3, 7.5", True),
    ("do not", "Fill Results from unrun G3-C.1 reviewer predictions",
     "80 cells NOT run; RESULTS_PLACEHOLDER NO_RESULTS; sec 7.5 states none",
     "sec 7.5, experiment80/", True),
    ("do not", "Quote a false-acceptance population rate from n=3 / n=2",
     "P2 case+interval only: 2/3 issues CP95[0.094,0.992], new n=2 exploratory",
     "sec 7.4, 9.2", True),
    ("do not", "Count cells within an issue as independent samples",
     "Independent unit = issue; pooled cell counts labelled repeated measures",
     "sec 3.1, 6, 7.1", True),
    ("do not", "Call active-evidence mechanism demonstrated",
     "Labelled candidate mechanism; confounded; needs activeness-only arm",
     "sec 8.1, 9.3", True),
    ("do not", "Hide the baseline-P2P projection residual",
     "Disclosed instrument gap; mandated removal before live run",
     "sec 8.5, gate 3", True),
]

MISSING_EVIDENCE = [
    ("Independent human gold for 18 packets + FR1/FR2", "blocks gold upgrade",
     "human annotator-2 + senior arbiter", "all rates currently PROVISIONAL"),
    ("Authorized 80-cell real run (8x5x2)", "only source of new P1 data on new "
     "issues", "written authorization after gates; $2.00 cap",
     "0/80 run; Results placeholder empty"),
    ("Activeness-only controlled arm", "needed to identify over-commitment "
     "mechanism causally", "future work (freshness/trust fixed)",
     "currently candidate mechanism only"),
    ("Larger independent REJECT sample", "stable P2 false-accept rate",
     "post-submission expansion (>=20 target)", "n=3 now / n=2 in pilot"),
    ("Removal of baseline pass_to_pass_baseline from tier-D view",
     "non-interference hardening before any live call",
     "code change + rescan (not done; frozen G3-B code untouched)",
     "gap disclosed, not yet fixed"),
    ("Cross-project / >2 model evidence", "external validity",
     "future work", "SymPy-only, 2 served models"),
]

SUBMISSION = [
    ("Abstract + title finalized", "draft present", "tighten to venue format"),
    ("All figures render (SVG -> PDF/PNG export)", "4 SVG generated", "export"),
    ("Numbers tie to tables/results_summary shas", "all via scripts", "final re-run"),
    ("Statistical denominators & CIs spot-checked", "CP validated vs frozen",
     "second reviewer check"),
    ("Gold PROVISIONAL banners consistent", "yes", "keep until adjudication"),
    ("References + related work completed", "skeleton", "add citations"),
    ("Reproduction appendix / artifact", "scripts provided", "package + README"),
    ("Ethics/budget statement", "$0.30 spent; caps disclosed", "venue forms"),
    ("Limitations + threats", "9 items", "polish"),
    ("Venue formatting + anonymization", "not started", "at submission"),
]


def write_checklist(name, title, header, rows):
    with (CHK / name).open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    md = [f"# {title}", ""]
    md.append("| " + " | ".join(header) + " |")
    md.append("|" + "---|" * len(header))
    for r in rows:
        md.append("| " + " | ".join(str(x) for x in r) + " |")
    K.write_text(CHK / name.replace(".csv", ".md"), "\n".join(md) + "\n")


def checklists():
    write_checklist("claim_audit.csv", "Claim audit (statements we must NOT make)",
                    ["rule", "must_not_claim", "how_draft_handles_it",
                     "location", "passes_in_draft"], CLAIM_CHECKS)
    write_checklist("missing_evidence.csv", "Outstanding evidence gaps",
                    ["gap", "why_it_matters", "path_to_resolve", "current_state"],
                    MISSING_EVIDENCE)
    write_checklist("submission_readiness.csv", "Submission readiness",
                    ["item", "current", "remaining"], SUBMISSION)
    print("3 checklists written")


def main():
    human_handoff()
    checklists()


if __name__ == "__main__":
    main()
