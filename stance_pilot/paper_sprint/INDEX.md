# GroundedReview Paper Sprint - package index

Zero-API draft package. History (G3-A..G3-C.1.1) untouched. Gold **PROVISIONAL**; 80-cell run **not authorized**.

## Read in this order
1. `paper/paper_draft.md` - full 11-section draft.
1b. `latex/main.tex` - submission LaTeX project (pdflatex + bibtex; native TikZ figures; `references.bib`).
2. `tables/result_inventory.md` - every finding tagged corrective/exploratory/pilot with source sha.
3. `tables/results_summary.json` - all headline counts + provenance.
4. `figures/` - fig1 concept, fig2 DeepSeek 9->1, fig3 GPT strict, fig4 focal 17318.
5. `experiment80/PRE_CALL_GATES.md` + `experiment80_config.json` - capped 80-cell pre-experiment (no calls).
6. `checklists/` - claim_audit, missing_evidence, submission_readiness.
7. `human/HUMAN_ADJUDICATION_HANDOFF.md` - 18 packets + FR1/FR2.

## Regenerate (offline, $0)
`-m paper_sprint.scripts.ps_build_tables`; `...ps_inventory`; `...ps_build_figures`; `...ps_make_experiment80`; `...ps_analyze_experiment80`; `...ps_make_human_and_checklists`; then `...ps_freeze`.

## Contents
### scripts/
- ps_analyze_experiment80.py
- ps_build_figures.py
- ps_build_tables.py
- ps_common.py
- ps_freeze.py
- ps_inventory.py
- ps_make_experiment80.py
- ps_make_human_and_checklists.py
- ps_readiness.py

### tables/
- T1_per_issue_condition_grid_g3b3.csv
- T2_restricted_commitment_P1.csv
- T3_sufficient_appropriateness.csv
- result_inventory.csv
- result_inventory.md
- results_summary.json

### figures/
- fig1_concept.svg
- fig2_deepseek_transition.svg
- fig3_gpt_strict_distribution.svg
- fig4_focal_17318.svg

### paper/
- paper_draft.md

### latex/
- figures/fig1_concept.tex
- figures/fig2_deepseek.tex
- figures/fig3_gpt_strict.tex
- figures/fig4_focal.tex
- main.aux
- main.bbl
- main.blg
- main.log
- main.out
- main.pdf
- main.tex
- main_v1_frozen_g3b3.pdf
- references.bib
- sections/01_introduction.tex
- sections/02_related_work.tex
- sections/03_benchmark.tex
- sections/04_conditions.tex
- sections/05_dataset.tex
- sections/06_setup.tex
- sections/07_results.tex
- sections/08_ablations.tex
- sections/09_threats.tex
- sections/10_conclusion.tex
- sections/abstract.tex
- sections/appendix.tex

### experiment80/
- ANALYSIS_AWAITING_DATA.md
- ANALYSIS_RESULTS.md
- ANALYSIS_TEMPLATE_80_blank.csv
- PRE_CALL_GATES.md
- READINESS.json
- READINESS.md
- RESULTS_PLACEHOLDER.json
- RESULTS_REAL.json
- TERNARY_MATRIX_AND_ISSUES.json
- experiment80_config.json

### human/
- HUMAN_ADJUDICATION_HANDOFF.md
- human_review_tracking.csv

### checklists/
- claim_audit.csv
- claim_audit.md
- missing_evidence.csv
- missing_evidence.md
- submission_readiness.csv
- submission_readiness.md

Manifest: `paper_sprint/freeze/paper_sprint_manifest.json` (sha256 4983162089828483f1b306e420323f34e6d04d2e7b7d19e7948595842cdfe62f); 63 hashed deliverable files.
