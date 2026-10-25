"""CEE budget + execution plan (offline, zero paid calls).

Produces evidence_store_cee/cee_plan.json: pre-registered sample, call count,
three-tier token/cost estimates, the pre-call hard budget guard, and the
statistics/reporting template. Nothing here performs a network call.

Run:
    uv run --python 3.13 -m evidence.cee_plan
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.cee_build import (build_all, DEFAULT_STORE, DEFAULT_OUT)

PLAN_VERSION = 'cee-plan-v1'
N_FIXTURES = 22
N_MODELS = 2
N_CALLS = N_FIXTURES * N_MODELS  # 44 single-turn requests, no retries on 200

# Completion hard cap sent to both providers (max_tokens). E1 observed output
# maxima over 110 cells were 284 (deepseek, T2A) and 231 (gpt-4.1-mini, T2D);
# 4096 is >14x headroom while bounding the conservative pre-call cost.
COMPLETION_CAP = 4096

# Input-token bounds. CEE turns = frozen T2A-equivalent user content (issue +
# patch + acceptance block) PLUS the item-invariant CEE head and two short
# fixed sections (symptom probe + integrity verdicts, ~600 chars).
#   point estimate : E1 T2A observed mean + 250 tokens for the added sections
#   empirical bound: E1 T2A observed max  + 700 tokens
#   hard bound     : chars/3 over the LARGEST on-disk bundle (tokenizer-
#                    independent crude upper envelope; diffs tokenize denser)
IN_ADD_MEAN = 250
IN_ADD_MAX = 700

# Frozen / frozen-profile pricing (USD per 1M tokens).
PRICES = {
    'deepseek-flash': {'in': 0.30, 'out': 1.20,
                       'source': 'frozen phase3_run DEFAULT_PROFILES'},
    'gpt-4.1-mini': {'in': 0.40, 'out': 1.60,
                     'source': 'frozen ev1_model_profiles.json '
                               'openai_gpt41_mini'},
}

# E1 T2A observed tokens (22 cells/model), read here from frozen results.
_E1_T2A = {
    'deepseek-flash':
        'evidence_store_w21/wave21_corrected_all110_results.jsonl',
    'gpt-4.1-mini':
        'evidence_store_ev1/ev1_gpt41mini_results.jsonl',
}

HARD_CAP_TOTAL_USD = 1.00
HARD_CAP_PER_MODEL_USD = 0.50


def _t2a_observed(store_root: Path):
    root = store_root.parent
    out = {}
    for model, rel in _E1_T2A.items():
        rows = [json.loads(l) for l in (root / rel).read_text(
            encoding='utf-8').splitlines() if l.strip()]
        t2a = [r for r in rows if r['condition'] == 'T2A-T']
        ins = sorted(int(r['tokens_in']) for r in t2a)
        outs_ = sorted(int(r['tokens_out']) for r in t2a)
        out[model] = {
            'n': len(t2a),
            'in_mean': round(sum(ins) / len(ins), 1),
            'in_max': ins[-1],
            'out_mean': round(sum(outs_) / len(outs_), 1),
            'out_max': outs_[-1],
        }
    return out


def _cost(in_tok, out_tok, price):
    return (in_tok * price['in'] + out_tok * price['out']) / 1_000_000


def build_plan():
    bundles, _, _, _ = build_all(DEFAULT_STORE)
    bundles_dir = DEFAULT_OUT / 'bundles'
    largest_chars = max((bundles_dir / f"{b['bundle_id']}.txt").stat().st_size
                        for b in bundles)
    t2a = _t2a_observed(DEFAULT_STORE)
    hard_in_bound = int(-(-largest_chars // 3))  # ceil(chars/3)

    models = {}
    totals = {'point_estimate_usd': 0.0, 'empirical_envelope_usd': 0.0,
              'hard_envelope_usd': 0.0}
    for model, price in PRICES.items():
        obs = t2a[model]
        point_in = obs['in_mean'] + IN_ADD_MEAN
        point_out = obs['out_mean']
        emp_in = obs['in_max'] + IN_ADD_MAX
        emp_out = max(obs['out_max'] * 3, 1024)
        point = N_FIXTURES * _cost(point_in, point_out, price)
        emp = N_FIXTURES * _cost(emp_in, emp_out, price)
        hard = N_FIXTURES * _cost(hard_in_bound, COMPLETION_CAP, price)
        per_call_precall_guard = _cost(hard_in_bound, COMPLETION_CAP, price)
        models[model] = {
            'n_calls': N_FIXTURES,
            'pricing_usd_per_1m': {'in': price['in'], 'out': price['out']},
            'pricing_source': price['source'],
            'e1_t2a_observed': obs,
            'input_tokens_per_call': {
                'point_estimate_mean': round(point_in, 1),
                'empirical_bound_max': emp_in,
                'hard_bound_chars_over_3': hard_in_bound,
            },
            'output_tokens_per_call': {
                'point_estimate_mean': round(point_out, 1),
                'empirical_planning': emp_out,
                'api_hard_cap_max_tokens': COMPLETION_CAP,
            },
            'cost_usd_22_calls': {
                'point_estimate': round(point, 4),
                'empirical_envelope': round(emp, 4),
                'hard_envelope_pre_call_guard': round(hard, 4),
            },
            'per_call_pre_call_guard_upper_bound_usd':
                round(per_call_precall_guard, 6),
            'hard_cap_per_model_usd': HARD_CAP_PER_MODEL_USD,
        }
        totals['point_estimate_usd'] += point
        totals['empirical_envelope_usd'] += emp
        totals['hard_envelope_usd'] += hard
    totals = {k: round(v, 4) for k, v in totals.items()}
    totals['hard_cap_total_usd'] = HARD_CAP_TOTAL_USD
    totals['headroom_under_hard_cap_usd'] = round(
        HARD_CAP_TOTAL_USD - totals['hard_envelope_usd'], 4)

    return {
        'plan_version': PLAN_VERSION,
        'protocol_version': 'cee-fixed-v1',
        'status': 'OFFLINE PLAN - no paid call made; execution requires '
                  'explicit written approval of this budget',
        'sample': {
            'fixtures': N_FIXTURES,
            'unique_issues': 10,
            'models': N_MODELS,
            'total_calls': N_CALLS,
            'turns_per_cell': 1,
            'retries': 'none on HTTP 200; INVALID/AMBIGUOUS is scored, not '
                       'retried; only a transport/5xx error may be retried '
                       'once and is logged',
            'selection': 'full frozen 22-fixture set, fixed before any CEE '
                         'result; no post-hoc filtering',
        },
        'request_contract': {
            'temperature': 0,
            'max_tokens': COMPLETION_CAP,
            'response_format': 'identical cee_review_decision_v1 strict '
                               'json_schema for both providers',
            'tools': 'none',
        },
        'largest_bundle_bytes_on_disk': largest_chars,
        'models': models,
        'totals_44_calls': totals,
        'budget_guard': {
            'mechanism': 'pre-call upper bound (conservative input hard '
                         'bound + max_tokens completion cap), checked before '
                         'every request; the run aborts BEFORE a call if it '
                         'would cross the cap, so realised spend can never '
                         'overshoot',
            'per_model_cap_usd': HARD_CAP_PER_MODEL_USD,
            'total_hard_cap_usd': HARD_CAP_TOTAL_USD,
            'runner_gate': 'future live runner must refuse by default and '
                          'require an explicit --allow-paid-run flag plus an '
                          'approved plan hash; no live runner is created in '
                          'this offline phase',
        },
        'statistics_plan': {
            'clustering_unit': 'instance_id (10 independent issues)',
            'per_model': 'DA overall and per evidence class (parseable '
                         'denominator), always-NEED baseline, error-type '
                         'counts; all-requests denominator also shown',
            'paired_contrast': 'per-bundle paired appropriateness; between-'
                               'model Delta issue-cluster bootstrap CI '
                               '(seed=7, n_boot=10000) mirroring '
                               'ev1_paired._cluster_bootstrap; descriptive '
                               'exact McNemar flagged low-power',
            'interpretation': 'convergence on fixed bundles vs E1 divergence '
                              '=> acquisition/policy; persistent divergence '
                              '=> interpretation; CEE and E1 scores are '
                              'never pooled',
            'language': 'preliminary/exploratory; wide CIs expected at '
                        '22 cells / 10 clusters / class sizes 7-6-9',
        },
        'reporting_tables': [
            'table_1_overall_da_by_model_with_cluster_ci',
            'table_2_da_stratified_by_evidence_class_7_6_9',
            'table_3_error_confusion_false_commit_accept_over_abstain_'
            'unsupported_reject_invalid',
            'table_4_paired_delta_and_mcnemar',
            'table_5_ceE_vs_e1_mechanism_contrast_no_pooled_scores',
        ],
    }


def main():
    plan = build_plan()
    out = DEFAULT_OUT / 'cee_plan.json'
    out.write_text(json.dumps(plan, indent=2, sort_keys=True,
                              ensure_ascii=False), encoding='utf-8')
    t = plan['totals_44_calls']
    print(f'CEE plan -> {out}')
    print(f"calls={plan['sample']['total_calls']} (22 fixtures x 2 models, "
          f"single turn)")
    for m, d in plan['models'].items():
        c = d['cost_usd_22_calls']
        print(f"  {m}: point=${c['point_estimate']:.4f} "
              f"empirical=${c['empirical_envelope']:.4f} "
              f"hard=${c['hard_envelope_pre_call_guard']:.4f}")
    print(f"TOTAL point=${t['point_estimate_usd']:.4f} "
          f"empirical=${t['empirical_envelope_usd']:.4f} "
          f"hard=${t['hard_envelope_usd']:.4f} "
          f"hard_cap=${t['hard_cap_total_usd']:.2f}")
    print('offline only: zero network / zero paid calls')


if __name__ == '__main__':
    main()
