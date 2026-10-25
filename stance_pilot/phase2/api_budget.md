# Phase 2 — API Budget (pre-spend estimate, awaiting approval)

No paid calls have been made for Phase 2. Everything so far (builds,
selfcheck, smoke tests, metrics checks) ran offline. This report prices the
proposed run so it can be approved before any spend.

## 1. Cell counts per model

Full pass (`--conditions T0,T1,T2D,T3D,T2A,T3A`):

| condition | cells | basis |
|---|---|---|
| T0 | 19 | all labelled patches |
| T1 | 19 | all labelled patches |
| T2D / T2A | 5 + 5 | five fixtures × two tiers |
| T3D / T3A | 5 + 5 | five fixtures × two tiers |
| **total** | **58** | of which 10 are agentic T3 |

Budget-limited variant (T3D, 5 fixtures, `--max-tool-turns 3
--token-budget 20000`): **+5 cells**.

Grand total per model: **63 cells**. For three models: **189 cells**.

## 2. Token anchors (measured, Phase-1 authentic n=12)

| cond | mean input | mean output | max input (conservative) | max output |
|---|---|---|---|---|
| T0 | 1,263 | 159 | 2,717 | 233 |
| T1 | 1,290 | 162 | 2,744 | 264 |
| T2 | 1,818 | 132 | 3,519 | 227 |
| T3 | 36,965 | 1,161 | 56,299 | 1,511 |

Phase-2 T2 cells are larger than Phase-1 (tier block + author claim on the
contradictory cell); the conservative column uses observed maxima and gives
headroom for that.

## 3. Estimated cost — full pass, per model

Expected (mean anchors): ≈ **437k input + 19k output tokens**.

| price scenario | in/out per 1M | USD per model |
|---|---|---|
| DeepSeek-chat (configured) | $0.27 / $1.10 | **≈ $0.14** |
| illustrative mid-price model | $1.00 / $5.00 | ≈ $0.53 |
| illustrative frontier model | $3.00 / $15.00 | ≈ $1.60 |

Conservative (all cells hit observed-max tokens): ≈ 704k + 30k →
DeepSeek ≈ **$0.22**, frontier ≈ **$2.56** per model.

Budget-limited T3 variant (5 cells capped at ~15k in / 0.5k out each):
DeepSeek ≈ **$0.03**, frontier ≈ **$0.26**.

### Totals for 3 models (DeepSeek + 2 chosen)

- expected: ≈ **$0.4–4.8** for all three full passes, depending on the two
  selected models' published prices (prices are entered explicitly in
  `model_profiles.json`, not guessed at billing time);
- realistic planning ceiling using conservative anchors: **under ≈ $8 total**
  even if both extras are frontier-priced;
- plus ≈ $0.3–0.8 for the budget variants.

The dominant cost is T3 input tokens (tool loops resend growing histories);
T0–T2 across 38 cells cost only a few cents even at frontier prices.

## 4. Cost accounting built into the runner

Every result row records `tokens_in`, `tokens_out`, `tool_calls`, `wall_s`,
`cost_usd` (profile price × measured usage), and `budget_hit`. Metrics emit
USD total and **USD per correct decision** per model×condition, and separate
correct decisions that required an `acceptance_log_reveal` (answer-tier read),
so cost efficiency is reported for diagnostic verification specifically.

## 5. Risk controls

- `--dry-run` enumerates cells with zero spend (already verified: 58 cells).
- Runs are resumable by `cell_key`: approve one model first (DeepSeek ≈ $0.14),
  inspect outputs, then add the other two models.
- Hard caps available: `--max-tool-turns`, `--token-budget`.
- A single configured key (`DEEPSEEK_API_KEY`); extra models need their key env
  and prices added to `evidence_store/model_profiles.json` — no code changes.
- Phase-1 outputs (`results_*_12.*`, `metrics_*_12.*`) are never opened for
  writing.

## 6. Decision requested

1. Approve the DeepSeek full pass + budget variant (≈ $0.15–0.25).
2. Choose the **two additional models** (provider/model id, endpoint, prices,
   key env). Nothing else is blocking; after approval the run starts
   model-by-model and metrics are regenerated offline.
