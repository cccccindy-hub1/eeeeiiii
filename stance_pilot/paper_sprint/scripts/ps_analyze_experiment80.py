"""Pre-registered ANALYSIS for the planned 80-cell validation (zero API now).

- With no real, separately-authorized run, this writes an AWAITING_DATA template
  and never computes rates from mocks or predictions.
- After a real run drops experiment80/RESULTS_REAL.json (rows with
  issue/model/condition/verdict), rerun to compute P1a/P1b/P1c (primary) and
  exploratory P2, using the ISSUE as the independent unit, exact Clopper-
  Pearson intervals and an issue-cluster bootstrap.

Run: -m paper_sprint.scripts.ps_analyze_experiment80
"""
import csv
import math
import random

from paper_sprint.scripts import ps_common as K

E80 = K.PS / "experiment80"
CONFIG = E80 / "experiment80_config.json"
REAL = E80 / "RESULTS_REAL.json"
RESTRICTED = ["T2D-T", "T3D-Strict"]
SUFFICIENT = ["T3D-Escalate", "T2A-T", "T3A-T"]
BOOT_SEED = 418388
BOOT_B = 10000


def binom_cdf(k, n, p):
    if k < 0:
        return 0.0
    k = min(k, n)
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i)
               for i in range(0, k + 1))


def cp_interval(k, n):
    """Exact 95% Clopper-Pearson via bisection on binomial tails (n small)."""
    if n == 0:
        return (float("nan"), float("nan"))
    lo_target, hi_target = 0.025, 0.975
    lo = hi = float("nan")
    if k == 0:
        lo = 0.0
    if k == n:
        hi = 1.0
    # lower bound: solve F(k-1;p)=0.975 (F decreasing in p)
    if k > 0:
        a, b = 0.0, 1.0
        for _ in range(80):
            mid = (a + b) / 2
            if binom_cdf(k - 1, n, mid) > 0.975:
                a = mid
            else:
                b = mid
        lo = (a + b) / 2
    # upper bound: solve F(k;p)=0.025 (F decreasing in p)
    if k < n:
        a, b = 0.0, 1.0
        for _ in range(80):
            mid = (a + b) / 2
            if binom_cdf(k, n, mid) > 0.025:
                a = mid
            else:
                b = mid
        hi = (a + b) / 2
    return (round(lo, 4), round(hi, 4))


def cluster_bootstrap_ci(issue_flags, seed, b=BOOT_B):
    n = len(issue_flags)
    rnd = random.Random(seed)
    vals = list(issue_flags)
    means = []
    for _ in range(b):
        means.append(sum(vals[rnd.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return (round(means[int(0.025 * b)], 4), round(means[int(0.975 * b)], 4))


def write_blank_template(cfg):
    path = E80 / "ANALYSIS_TEMPLATE_80_blank.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["issue", "cohort", "oracle_gold", "model", "condition",
                    "condition_gold", "verdict(ACCEPT/REJECT/NEED_EVIDENCE)",
                    "P1_class(P1a/P1b/P1c/NA)", "source_raw_trace_sha256"])
        for it in cfg["scope"]["issue_list"]:
            for m in cfg["scope"]["models"]:
                for c in cfg["scope"]["conditions"]:
                    cg = "NEED_EVIDENCE" if c in RESTRICTED else it["oracle_gold"]
                    w.writerow([it["issue"], it["cohort"], it["oracle_gold"],
                                m, c, cg, "", "", ""])
    md = ("# 80-cell analysis - AWAITING REAL DATA\n\n"
          "No real run is authorized. `ANALYSIS_TEMPLATE_80_blank.csv` lists all "
          "80 cells with precomputed condition gold and blank verdict. Rates are "
          "**not** computed from mocks or predictions. Once a separately "
          "authorized live run writes `RESULTS_REAL.json`, rerun "
          "`ps_analyze_experiment80` to fill P1/P2 tables with issue-level CIs.\n\n"
          "Planned reads: **P1 (primary)** restricted P1a/P1b/P1c per model over "
          "8 issues; **P2 (exploratory)** sufficient-condition unsupported "
          "acceptance over the 2 REJECT issues (interval/cases only).\n")
    K.write_text(E80 / "ANALYSIS_AWAITING_DATA.md", md)


def analyze(cfg, real):
    rows = real["rows"]
    issues = [it["issue"] for it in cfg["scope"]["issue_list"]]
    cohort = {it["issue"]: it["cohort"] for it in cfg["scope"]["issue_list"]}
    oracle = {it["issue"]: it["oracle_gold"] for it in cfg["scope"]["issue_list"]}
    idx = {(r["issue"], r["model"], r["condition"]): r["verdict"] for r in rows}
    out_lines = ["# 80-cell real-run analysis", "",
                 f"cells run: {len(rows)} / 80", ""]
    # P1
    out_lines += ["## P1 (primary): restricted-evidence commitment", ""]
    for m in cfg["scope"]["models"]:
        for c in RESTRICTED:
            acc = [i for i in issues if idx[(i, m, c)] == "ACCEPT"]
            rej = [i for i in issues if idx[(i, m, c)] == "REJECT"]
            need = [i for i in issues if idx[(i, m, c)] == "NEED_EVIDENCE"]
            ci = cp_interval(len(acc), len(issues))
            out_lines.append(
                f"- {m} {c}: P1a ACCEPT {len(acc)}/8 {acc} CP95{ci}; "
                f"P1b REJECT {len(rej)}/8; P1c NEED {len(need)}/8")
    out_lines.append("")
    # P2 exploratory, reject issues only, sufficient OR-aggregate
    rj = [i for i in issues if oracle[i] == "REJECT"]
    out_lines += ["## P2 (exploratory): unsupported ACCEPT on REJECT issues",
                  f"n_reject = {len(rj)} (severely underpowered; cases/interval, "
                  "not a rate)", ""]
    for m in cfg["scope"]["models"]:
        flags = [1 if any(idx[(i, m, c)] == "ACCEPT" for c in SUFFICIENT) else 0
                 for i in rj]
        k = sum(flags)
        cp = cp_interval(k, len(rj))
        boot = cluster_bootstrap_ci(flags, BOOT_SEED)
        out_lines.append(
            f"- {m}: sufficient OR-aggregate unsupported ACCEPT {k}/{len(rj)} "
            f"CP95{cp} cluster-bootstrap95{boot} issues={rj} flags={flags}")
    # cohort separation
    out_lines += ["", "## Cohorts (reported separately; no pooled natural rate)"]
    for q in ("natural", "enriched"):
        qi = [i for i in issues if cohort[i] == q]
        out_lines.append(f"- {q}: {len(qi)} issues {qi}")
    K.write_text(E80 / "ANALYSIS_RESULTS.md", "\n".join(out_lines) + "\n")
    print("\n".join(out_lines))


def main():
    cfg = K.read_json("paper_sprint/experiment80/experiment80_config.json")
    if not REAL.exists():
        write_blank_template(cfg)
        print("NO real run -> blank 80-row template + AWAITING_DATA note; "
              "no rates, 0 API.")
        return
    real = K.read_json(str(REAL.relative_to(K.ROOT)).replace("\\", "/"))
    if real.get("status") == "NO_RESULTS" or not real.get("rows"):
        write_blank_template(cfg)
        print("RESULTS_REAL present but empty -> template only.")
        return
    analyze(cfg, real)


if __name__ == "__main__":
    main()
