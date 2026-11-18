# G4 GroundedReview — Reproduction Notes

Frozen experiment: 18 issues × 4 cells (A/B/C/D) × 2 models = 144 live cells.
Version `g4-sufficiency-iv-v1.1`; runner `g4live-runner-v1`; analysis
`g4-independent-analysis-v1`. All commands run from the `stance_pilot/`
directory with `$env:PYTHONPATH='.'`.

## Inputs (frozen, never modified) — `evidence_store_g4_sufficiency/`
- `g4_fixed_bundles.jsonl` — 72 fixed bundles (system/user, fixed 9-step
  yoked transcript, tools inventory, payload hashes).
- `g4_cell_manifest.jsonl` — 144 slots; paired Latin order, seed
  `G4_ORDER_SEED=20261102`; per-slot `bundle_sha256`; gold PROVISIONAL.
- `g4_payload_hashes.jsonl`, `g4_identifiability_gate.json/.md` (G1–G6 GO),
  `G4_PREREGISTRATION_v1.md`, `G4_PREREGISTRATION_ADDENDUM_v1.1.md` (addendum
  governs).

## Offline preflight ($0)
```
uv run --offline --python 3.11 -m evidence.g4_live_run --verify      # frozen hashes/order/parent pins
uv run --offline --python 3.11 -m evidence.g4_live_run --selftest    # 13 budget-guard checks
uv run --offline --python 3.11 -m evidence.g4_live_run --fingerprint # pre-run freeze fingerprint
uv run --offline --python 3.11 -m evidence.g4_live_run --mock-gate   # full 144-cell yoked path at $0
```
Observed: verification OK (72 bundles / 144 slots / G1–G6 GO / 13-5 strata /
$2 cap); self-test 13/13; mock gate n=144, balanced, zero cost/errors,
fixed 9-step 20-message contexts, all three parse classes, 144 mock raws.

## Live run (authorized; single shared US$2.00 hard cap)
```
uv run --python 3.11 --with openai -m evidence.g4_live_run \
  --allow-paid-run --i-acknowledge-g4live-144cells-2usd-approved
```
- Strict manifest serial order; one paid call per cell; independent 20-message
  context per cell; temperature 0; strict JSON schema; no tools on final call.
- Pre-call conservative bound against the shared ledger before every request;
  hard stop instead of overshooting; resume-safe (terminal scoring errors are
  not retried; transport errors are resume-eligible; mock rows excluded).
- Result: 144/144 new cells, 0 retries, 0 errors, 0 protocol downgrades;
  served ids exactly `gpt-4.1-mini-2025-04-14` and `deepseek-flash`;
  spend US$0.807389 (GPT 0.436378, DeepSeek 0.371011).
- Raw-first: `raw/live/*.json` persisted before scoring (request/response,
  served id, token usage, yoked content, bound, cost, finish reason);
  per-model `runs/g4live_live_*_results.jsonl` and
  `runs/g4live_live_run_audit.json`.

## Independent analysis (read-only over raw)
```
uv run --offline --python 3.11 -m evidence.g4_analysis
```
Re-parses every frozen `answer_raw` with the pre-registered ternary parser and
re-scores unsupported acceptance from frozen gold; zero re-parse mismatches vs
the runner. Outputs `analysis/g4_analysis_report.{json,md}`,
`analysis/tables/*.tex`, `analysis/figures/*.tikz`. Primary H1 per model:
two-sided exact McNemar by combinatorial binomial summation (no scipy);
issue-clustered nonparametric bootstrap B=20000, seed 20261102; Wilson
intervals. Models are never pooled.

## Primary result
- GPT-4.1-mini: U(A)=0/18, U(B)=8/18; discordants b=0, c=8; exact
  two-sided p=0.0078; paired Δ=-0.444, bootstrap 95% CI [-0.667,-0.222].
- DeepSeek-Flash: U(A)=U(B)=0/18; p=1.0 (null, reported as such).
- C/D diagnostic: both models 0 unsupported accepts on the 5 oracle-REJECT
  issues; oracle agreement GPT 17/18 (C) / 16/18 (D), DeepSeek 17/18 both.

## Paper
`paper_sprint/latex_g4/` is a copy of the frozen v2 LaTeX tree; the v1 frozen
PDF is untouched. Build with the single-file `tools/tectonic/tectonic.exe`:
```
cd paper_sprint/latex_g4
..\..\tools\tectonic\tectonic.exe -X compile main.tex
```
Output `main.pdf` (22 pages), also versioned as `main_v3_g4_controlled.pdf`.

## Gold and freeze
Gold is PROVISIONAL (`annotator2 = NOT_OBTAINED`); no AI output is used as
human gold. `freeze/g4live_freeze_manifest.json` hashes all raw, trace, run,
analysis, code, frozen-parent, and G4 paper artifacts (483 files). No git
commit was made; no frozen prompt/evidence/manifest/gold or G3 historical
experiment was modified.
