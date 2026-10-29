# 80-cell analysis - AWAITING REAL DATA

No real run is authorized. `ANALYSIS_TEMPLATE_80_blank.csv` lists all 80 cells with precomputed condition gold and blank verdict. Rates are **not** computed from mocks or predictions. Once a separately authorized live run writes `RESULTS_REAL.json`, rerun `ps_analyze_experiment80` to fill P1/P2 tables with issue-level CIs.

Planned reads: **P1 (primary)** restricted P1a/P1b/P1c per model over 8 issues; **P2 (exploratory)** sufficient-condition unsupported acceptance over the 2 REJECT issues (interval/cases only).
