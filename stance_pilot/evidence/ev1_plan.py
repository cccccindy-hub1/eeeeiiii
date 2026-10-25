"""Generate the frozen E1 external-validation PLAN document (offline).

Assembles evidence_store_ev1/ev1_external_validation_plan.json from:
  - ev1_protocol_freeze.json   (what is frozen)
  - ev1_model_profiles.json    (vendor capability/pricing survey)
  - the authoritative Wave-2.1 corrected 110-row token totals (cost basis)
  - recorded offline test results (adapter selfcheck / mock run / adapter check)
Nothing here performs or authorises any paid API call.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pilot import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
EV1 = ROOT / 'evidence_store_ev1'
W21 = ROOT / 'evidence_store_w21'

CELLS = 110
FIXTURES = 22
CONDITIONS = ['T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T']
ISSUES = 10

# reasoning-token multiplier envelope for hidden-reasoning models
REASON_OUT_MULT = (1.0, 4.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(EV1 / 'ev1_external_validation_plan.json'))
    a = ap.parse_args()

    freeze = json.loads((EV1 / 'ev1_protocol_freeze.json').read_text('utf-8'))
    profiles = json.loads((ROOT / 'evidence' / 'ev1_model_profiles.json')
                          .read_text('utf-8'))

    rows = [r for r in read_jsonl(W21 / 'wave21_corrected_all110_results.jsonl')
            if not r.get('error') and not r.get('mock')]
    assert len(rows) == CELLS, f'expected {CELLS} corrected rows, got {len(rows)}'
    tin = sum(r.get('tokens_in', 0) for r in rows)
    tout = sum(r.get('tokens_out', 0) for r in rows)
    usd_w21 = round(sum(r.get('cost_usd', 0) for r in rows), 4)

    def cost(pin, pout, out_mult=1.0):
        return round(tin * pin / 1e6 + tout * pout * out_mult / 1e6, 4)

    candidates = {}
    for name, p in profiles.items():
        if name.startswith('_'):
            continue
        est = cost(p['price_in_per_1m'], p['price_out_per_1m'])
        entry = {
            'provider': p['provider'], 'model': p['model'],
            'recommendation': p['recommendation'], 'status': p['status'],
            'base_url': p['base_url'], 'key_env': p['key_env'],
            'pricing_usd_per_1m': {'input': p['price_in_per_1m'],
                                   'output': p['price_out_per_1m']},
            'context_window_tokens': p['context_window_tokens'],
            'max_output_tokens': p['max_output_tokens'],
            'temperature_supported': p['temperature_supported'],
            'completion_param': p['completion_param'],
            'reasoning_effort': p.get('reasoning_effort'),
            'response_format_mode': p['response_format'],
            'tool_calling': p['tool_calling'],
            'estimated_cost_110_usd_point': est,
            'selection_rationale': p['selection_rationale'],
        }
        if p.get('reasoning_effort') or 'thinking' in str(p.get('reasoning', '')):
            lo = cost(p['price_in_per_1m'], p['price_out_per_1m'],
                      REASON_OUT_MULT[0])
            hi = cost(p['price_in_per_1m'], p['price_out_per_1m'],
                      REASON_OUT_MULT[1])
            entry['estimated_cost_110_usd_reasoning_envelope'] = [lo, hi]
            entry['reasoning_cost_note'] = (
                f'reasoning tokens billed as output; envelope output x'
                f'{REASON_OUT_MULT[0]}-{REASON_OUT_MULT[1]} on the wave21 '
                'token mix; BudgetGuard pre-call cap bounds the high side')
        if p.get('known_risks'):
            entry['known_risks'] = p['known_risks']
        candidates[name] = entry

    plan = {
        'artifact': 'groundedreview_ev1_external_validation_plan',
        'status': 'OFFLINE PLAN ONLY - no paid cross-model API call is '
                  'authorised until written approval',
        'stage': 'E1 (cross-model replication on the frozen design); E2 '
                 '(new issues/tasks) is explicitly out of scope here',
        'approval_gate': {
            'approved_now': [
                'protocol freeze, adapter implementation, offline mock '
                'testing, metrics/paired-analysis code, preregistration, '
                'symptom audit, this plan'],
            'not_approved_now': [
                'any paid cross-model API call',
                'adding or changing fixtures, gold, prompts, tool '
                'permissions, conditions or scoring code',
                'starting E2 issue expansion'],
            'resume_after_approval':
                'evidence.ev1_run --profile openai_gpt41_mini (live path), '
                'resume-capable; then evidence.ev1_paired with name=path for '
                'baseline and candidate',
        },

        'frozen_design': {
            'freeze_id': freeze.get('freeze_id'),
            'fixtures': FIXTURES, 'conditions': 5, 'issues': ISSUES,
            'cells_per_model': CELLS,
            'conditions_list': CONDITIONS,
            'prompt_id_fingerprinted': 'p3-ternary-v2',
            'gold_file': 'evidence_store_w21/wave2_gold.jsonl',
            'gold_sha256': (freeze.get('files', {}).get('gold', {})
                            .get('sha256_newline_normalized')),
            'raw_rows_primary': 'evidence_store_w21/wave2_pilot_raw_rows.jsonl',
            'baseline_results_reused_read_only':
                'evidence_store_w21/wave21_corrected_all110_results.jsonl',
            'permission_matrix_errors':
                (freeze.get('tool_permission_matrix') or {}).get('n_errors'),
            'permission_matrix_passed':
                (freeze.get('tool_permission_matrix') or {}).get('passed'),
            'immutability': 'frozen code modules are not modified; all new '
                            'logic is ev1_*-prefixed and writes only under '
                            'evidence_store_ev1',
        },

        'baseline_observed': {
            'model': 'deepseek-flash',
            'oracle_decision_appropriateness':
                {'rate': 0.5909, 'ci95_cluster': [0.525, 0.675]},
            'condition_decision_appropriateness':
                {'rate': 0.7364, 'ci95_cluster': [0.6667, 0.7818]},
            'tokens_110_cells': {'input': tin, 'output': tout},
            'cost_usd_recorded_110_cells': usd_w21,
            'max_single_cell_tokens': {
                'input': max(r.get('tokens_in', 0) for r in rows),
                'output': max(r.get('tokens_out', 0) for r in rows)},
            'note': 'two standards measure different constructs and are '
                    'never averaged',
        },

        'candidate_models': candidates,
        'pricing_survey': {
            'checked_date': profiles['_meta']['pricing_checked_date'],
            'sources': profiles['_meta']['pricing_sources'],
            'excluded': profiles['_meta']['excluded'],
            'recommend_run_order':
                ['openai_gpt41_mini', 'google_gemini3_flash',
                 'openai_gpt51_codex_mini'],
        },

        'interface_compatibility_matrix': {
            'wire_features_needed': [
                'chat.completions multi-turn native tool calls',
                'strict structured decision JSON on the final tool-free turn',
                'temperature=0 (or documented deterministic setting)',
                'hard output cap (max_tokens / max_completion_tokens)',
                'context >= largest single cell (~73k input incl. tool '
                'history); 128k+ recommended, 1M offered by primary',
                'per-request vendor body passthrough; no DeepSeek thinking '
                'field sent to other vendors'],
            'primary_alignment':
                'gpt-4.1-mini supports all five natively; it is the '
                'controlled replication (minimum interface delta)',
            'gemini_mitigations':
                'adapter pre-downgrades strict->json_object; 2-cell live '
                'fixture smoke (one static, one active condition) is '
                'MANDATORY and separately approved before all 110',
            'codex_mitigations':
                'adapter swaps to max_completion_tokens, drops temperature, '
                'sets reasoning_effort=minimal',
        },

        'cost_envelope_and_budget_guard': {
            'primary_point_estimate_usd':
                candidates['openai_gpt41_mini']['estimated_cost_110_usd_point'],
            'recommended_hard_spend_cap_usd_per_model_110_cells': 2.00,
            'recommended_smoke_cells_before_full_run': 2,
            'smoke_estimated_usd_primary': round(
                candidates['openai_gpt41_mini']['estimated_cost_110_usd_point']
                * 2 / CELLS, 4),
            'budgetguard': 'ev1 live path performs a BudgetGuard pre-call '
                           'check; a 4xx/5xx or cap breach is recorded, not '
                           'retried blindly; runs are resumable',
            'total_program_ceiling_request_for_approval_usd':
                {'primary_only': 2.0, 'primary_plus_secondary': 5.0,
                 'all_three_with_reasoning_envelope': 9.0},
        },

        'metrics_preregistered_per_condition': [
            'Oracle Decision Appropriateness (+ issue-cluster bootstrap 95% '
            'CI, seed=7, n=10000)',
            'Condition Decision Appropriateness (same bootstrap)',
            'Appropriate Abstention', 'Over-Abstention (H1)',
            'Unsupported Rejection (H2)', 'false-commit-accept',
            'tool success: 200/total, 403 strict_denied, 400 '
            'missing_reason, escalation granted, any-5xx cells',
            'tokens, USD total, USD per appropriate decision, wall time',
            'INVALID/AMBIGUOUS protocol-failure rate',
            'Always-NEED sanity baseline on every block'],
        'paired_analysis': {
            'unit': 'cell = (scenario, id, served_artifact_id, condition); '
                    'both models run the identical 110 cells',
            'cluster': 'issue (instance_id), 10 clusters',
            'delta_ci': 'issue-cluster bootstrap of per-cell correctness '
                        'difference, seed=7, n=10000',
            'mcnemar': 'exact two-sided, descriptive only (discordant n is '
                       'small and cells are clustered)',
            'forbidden_comparison':
                'never compare marginal accuracies across different '
                'patch/fixture sets; E1 keeps the set identical by design',
            'code': 'evidence/ev1_paired.py (self-check reproduces wave2.1 '
                    '59.1% / 73.6% with delta 0 vs itself)',
        },
        'case_level_preregistration': {
            'file': 'evidence_store_ev1/ev1_preregistration.json',
            'groups': {'wrong_patch': 2, 'partial_but_decisive': 3,
                       'incomplete_good': 2},
            'locked_cells': 35,
            'rule': 'membership anchored by exact artifact id; expectations '
                    'asserted against frozen gold; no post-hoc case picking',
        },
        'symptom_probe_audit': {
            'file': 'evidence_store_ev1/ev1_symptom_probe_audit.json',
            'checks_passed': '14/14',
            'conclusion': 'trusted decisive failure => REJECT within the '
                          'benchmark operationalisation; acceptance-artifact '
                          'channel is structurally independent under strict '
                          'policy',
            'reported_limitations': [
                'issue-derived local probe, not the maintainer test suite',
                'symptom persistence is not a full merge-acceptability '
                'verdict', 'single decisive instance; small issue cluster'],
        },

        'offline_test_evidence': {
            'adapter_kwargs_selfcheck': 'evidence/ev1_adapters.py __main__: '
                                        '18/18 assertions PASS, zero network',
            'mock_full_run': 'evidence.ev1_run --mock --spawn-server: '
                             'cells=110 failed=0, '
                             'evidence_store_ev1/ev1_mock_results.jsonl',
            'adapter_wire_check': 'evidence.ev1_run --adapter-check '
                                  '--spawn-server: 3 profiles x 5 conditions, '
                                  '261 assertions, 0 failures, zero network '
                                  '(run_ternary_cell exercised with mock=False '
                                  'wrapped by RecordingCompletions)',
            'metrics_selfcheck':
                'ev1_paired on wave21 vs wave21 reproduces frozen rates '
                'exactly; paired delta 0.0 CI [0,0] McNemar p=1.0',
        },

        'risks': [
            {'risk': 'preview/vendor model id churn',
             'mitigation': 'gpt-4.1-mini (current, non-preview) is primary; '
                           'gemini preview is secondary and id/version is '
                           'recorded at run time; gpt-5-mini already excluded '
                           'for deprecation'},
            {'risk': 'Gemini OpenAI-compat strict schema / multi-turn tool '
                     'history defects',
             'mitigation': 'json_object pre-downgrade + mandatory 2-cell '
                           'smoke before the paid run'},
            {'risk': 'reasoning-token cost blowout (gpt-5.1-codex-mini)',
             'mitigation': 'reasoning_effort=minimal, output-multiplier '
                           'envelope, hard BudgetGuard cap'},
            {'risk': 'interface differences masquerading as model '
                     'differences',
             'mitigation': 'primary chosen for maximal wire parity; adapter '
                           'is the ONLY vendor-difference point; prompts, '
                           'tools, JSON keys, permissions unchanged'},
            {'risk': 'post-hoc adjustment temptation',
             'mitigation': 'gold/prompt/fixture freeze, preregistration with '
                           'id anchors, locked analysis code before any '
                           'candidate output exists'},
            {'risk': 'small cluster count (10 issues) limits power',
             'mitigation': 'E1 is a stability/replication check, effect CIs '
                           'reported honestly; generalisation deferred to '
                           'approved E2'},
        ],
    }

    Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(f'tokens basis in={tin} out={tout} rows={len(rows)}')
    for n, e in candidates.items():
        print(n, 'point=$', e['estimated_cost_110_usd_point'],
              e.get('estimated_cost_110_usd_reasoning_envelope', ''))
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
