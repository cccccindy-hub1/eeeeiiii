"""G3-A.1 task 11 — Gate 3-B cost & BudgetGuard plan (zero API, no calls).

All numbers derive from FROZEN Experiment X telemetry
(evidence_store_eal/v21x freeze + per-call jsonl) and the G3-B cell count
10 issues x 5 conditions x 2 models = 100 calls. Nothing here calls an API.

Outputs g3a1_gate3b_budget.json: point estimate, observed-bounded worst case,
planning worst case, and the pre-call BudgetGuard hard caps to reuse
(phase3_run.BudgetGuard). Prices are X-frozen; they MUST be re-pinned at
execution and a list-price ceiling guards against drift.
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
G3A1 = HERE / 'evidence_store_g3a1'
OUT = G3A1 / 'gate3b' / 'g3a1_gate3b_budget.json'

# FROZEN X telemetry (eal_v21x_freeze_manifest.json + live audit/jsonl).
X_PRICES = {  # USD per 1,000,000 tokens
    'gpt-4.1-mini': {'in': 0.40, 'out': 1.60,
                     'served_in_x': 'gpt-4.1-mini-2025-04-14'},
    'deepseek-flash': {'in': 0.30, 'out': 1.20, 'served_in_x': 'deepseek-flash'},
}
X_OBSERVED = {  # from 176 X calls
    'gpt-4.1-mini': {'calls': 88, 'avg_in': 454332/88, 'avg_out': 17874/88,
                     'max_in': 8066, 'max_out': 403, 'spend_usd': 0.210331},
    'deepseek-flash': {'calls': 88, 'avg_in': 478112/88, 'avg_out': 32204/88,
                       'max_in': 8382, 'max_out': 532, 'spend_usd': 0.182078},
}
N_ISSUES = 10
N_CONDITIONS = 5
CALLS_PER_MODEL = N_ISSUES * N_CONDITIONS  # 50
COMPLETION_CAP = 4096
# planning input ceiling: ~2x the largest prompt ever observed in X, chosen
# BEFORE execution; the live pre-call guard uses the ACTUAL estimated prompt so
# the real ceiling is enforced regardless of this planning assumption.
PLAN_MAX_IN = 16000
# refuse to run if execution-time list price exceeds this multiple of X price
PRICE_DRIFT_LIMIT = 1.5


def per_call(pr, tin, tout):
    return (tin * pr['in'] + tout * pr['out']) / 1_000_000


def main():
    models = {}
    point_total = obs_worst_total = plan_worst_total = 0.0
    for name, pr in X_PRICES.items():
        o = X_OBSERVED[name]
        point = per_call(pr, o['avg_in'], o['avg_out']) * CALLS_PER_MODEL
        # observed-bounded: every call uses X max input + FULL completion cap
        obs_worst = per_call(pr, o['max_in'], COMPLETION_CAP) * CALLS_PER_MODEL
        # planning worst: every call uses PLAN_MAX_IN + full cap
        plan_worst = per_call(pr, PLAN_MAX_IN, COMPLETION_CAP) * CALLS_PER_MODEL
        models[name] = {
            'calls': CALLS_PER_MODEL,
            'x_frozen_price_in_per_mtok': pr['in'],
            'x_frozen_price_out_per_mtok': pr['out'],
            'x_served_model_id': pr['served_in_x'],
            'point_estimate_usd': round(point, 4),
            'point_per_call_usd': round(point / CALLS_PER_MODEL, 6),
            'observed_bounded_worst_usd': round(obs_worst, 4),
            'observed_bounded_worst_assumption':
                f"every call: X max input {o['max_in']} + full {COMPLETION_CAP} "
                "output tokens",
            'planning_worst_usd_16k_in': round(plan_worst, 4),
            'planning_worst_assumption':
                f'every call: {PLAN_MAX_IN} input + {COMPLETION_CAP} output',
            'proposed_hard_cap_usd': 2.50,
        }
        point_total += point
        obs_worst_total += obs_worst
        plan_worst_total += plan_worst

    doc = {
        'version': 'g3a1-gate3b-budget-v1',
        'zero_api_true_at_freeze': True,
        'sampling': {
            'temperature': 0, 'max_tokens': COMPLETION_CAP,
            'response_format': 'json_object', 'tools': 0, 'turns': 1,
            'retries_per_cell': 0, 'max_model_calls_per_cell': 1,
        },
        'cell_count': {
            'issues': N_ISSUES, 'conditions': N_CONDITIONS, 'models': 2,
            'calls_total': N_ISSUES * N_CONDITIONS * 2,
            'calls_per_model': CALLS_PER_MODEL,
            'independent_unit': 'issue (conditions are repeated measures)',
        },
        'price_source': 'frozen Experiment X (eal_v21x); re-pin at execution',
        'price_drift_guard': f'hard stop + require re-approval if execution '
                             f'list price > {PRICE_DRIFT_LIMIT}x X-frozen price',
        'served_id_drift_guard': 'hard stop if served model id != requested',
        'envelope_usd': {
            'point_estimate_total': round(point_total, 4),
            'observed_bounded_worst_total': round(obs_worst_total, 4),
            'planning_worst_total_16k_in_full_output':
                round(plan_worst_total, 4),
        },
        'per_model': models,
        'budgetguard': {
            'implementation': 'reuse evidence.phase3_run.BudgetGuard '
                              '(pre-call bound_usd = actual est input + full '
                              'completion cap; raises BudgetGuardStop)',
            'per_model_hard_cap_usd': 2.50,
            'global_hard_cap_usd': 5.00,
            'global_is_across_both_models': True,
            'check_timing': 'before every send; resume restores cumulative spend',
            'how_envelope_relates_to_cap':
                'planning worst (~$1.13 both models) is < global $5.00 and '
                'each model planning worst (<$0.65) is < $2.50; caps bind '
                'before overspend even under adversarial output length',
            'approval_note': 'caps are PROPOSED; only set after written Gate '
                             '3-B approval; no call is made in A.1',
        },
        'no_paid_ci_or_data_cost': True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(doc['envelope_usd'], indent=2))
    print('per-model caps:', {m: v['proposed_hard_cap_usd']
                              for m, v in models.items()})
    print('wrote', OUT)


if __name__ == '__main__':
    main()
