"""CEE v1.1 analysis - fixed-evidence interpretation, paired cross-model.

Offline; reads only the two CEE v1.1 result files and frozen gold; no API.

Outputs (evidence_store_cee/cee_v11_metrics.json), per the 2026-10-24
authorisation item 10:
  * per-model Decision Appropriateness overall and within each evidence
    class, with BOTH parseable and all-requests denominators, plus issue-
    cluster bootstrap 95% CI (seed=7, n_boot=10000, unit=instance_id);
  * the Always-NEED baseline appropriateness;
  * 3x3 ternary confusion matrices (rows = decision, columns = gold) and the
    H1/H2 error families: Over-Abstention, Unsupported Acceptance
    (false commit), Unsupported Rejection;
  * the 22 paired bundles: per-bundle correctness delta, issue-cluster
    bootstrap CI for the mean paired delta, and a descriptive exact McNemar p
    on discordant pairs;
  * INVALID / AMBIGUOUS / API_ERROR reported separately (never folded into
    NEED_EVIDENCE);
  * a strictly SEPARATE CEE-vs-E1 mechanism block (numbers shown side by side,
    never pooled or averaged, model-version drift flagged).

    uv run --python 3.13 -m evidence.cee_analyze_v11
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl, TERNARY
from evidence.metrics2 import mcnemar_exact_p
from evidence.cee_run import CEE_DIR
from evidence import cee_protocol_v11 as cee

SEED = 7
N_BOOT = 10000
CLASSES = ['sufficient_positive', 'decisive_negative', 'insufficient']
DECISIONS = ['ACCEPT', 'REJECT', 'NEED_EVIDENCE']
DS_FILE = 'cee_v11_deepseek_flash_results.jsonl'
GPT_FILE = 'cee_v11_gpt41mini_results.jsonl'
EV1_METRICS = (CEE_DIR.parent / 'evidence_store_ev1'
               / 'ev1_gpt41mini_paired_metrics.json')


def _rate(num, den):
    return round(num / den, 4) if den else None


def _cluster_bootstrap(vals, clusters, n_boot=N_BOOT, seed=SEED):
    """Mirror of evidence.ev1_paired._cluster_bootstrap: resample ISSUES
    (instance_id) with all their cells, recompute the mean."""
    by = defaultdict(list)
    for v, c in zip(vals, clusters):
        by[c].append(v)
    keys = list(by)
    if len(keys) <= 1 or not vals:
        return {'mean': (sum(vals) / len(vals)) if vals else None,
                'ci95': [None, None], 'n_clusters': len(keys)}
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        chosen = [keys[rng.randrange(len(keys))] for _ in keys]
        flat = [v for k in chosen for v in by[k]]
        means.append(sum(flat) / len(flat))
    means.sort()
    return {'mean': round(sum(vals) / len(vals), 4),
            'ci95': [round(means[int(.025 * n_boot)], 4),
                     round(means[int(.975 * n_boot) - 1], 4)],
            'n_clusters': len(keys)}


def load(name, fname):
    rows = read_jsonl(str(CEE_DIR / fname))
    if len(rows) != 22 or len({r['bundle_id'] for r in rows}) != 22:
        raise SystemExit(f'{name}: expected 22 unique bundles, got {len(rows)}')
    return rows


def confusion(rows):
    """3x3: rows = parsed decision, columns = gold; plus failure columns."""
    mat = {d: {g: 0 for g in DECISIONS} for d in DECISIONS}
    n_inv = n_amb = n_api = 0
    for r in rows:
        p, g = r['parsed'], r['cee_gold']
        if p == 'API_ERROR':
            n_api += 1
            continue
        if p == 'INVALID':
            n_inv += 1
            continue
        if p == 'AMBIGUOUS':
            n_amb += 1
            continue
        mat[p][g] += 1
    return {'rows_decision': DECISIONS, 'columns_gold': DECISIONS,
            'matrix': mat, 'n_invalid': n_inv, 'n_ambiguous': n_amb,
            'n_api_error': n_api}


def error_families(rows):
    """H1/H2 over the parseable rows (all requests here are parseable)."""
    parseable = [r for r in rows if r['parsed'] in TERNARY]
    def cnt(lbl):
        return sum(1 for r in parseable if r['error_label'] == lbl)
    gold_pos = [r for r in parseable if r['cee_gold'] == 'ACCEPT']
    gold_neg = [r for r in parseable if r['cee_gold'] == 'REJECT']
    gold_ins = [r for r in parseable if r['cee_gold'] == 'NEED_EVIDENCE']
    over_abs = cnt('over_abstain_on_positive') + cnt('over_abstain_on_negative')
    false_accept = (cnt('false_commit_accept_on_negative')
                    + cnt('false_commit_accept_on_insufficient'))
    unsupported_reject = (cnt('unsupported_reject_on_positive')
                          + cnt('unsupported_reject_on_insufficient'))
    return {
        'over_abstention': {
            'cells': over_abs,
            'rate_over_decisive_gold':
                _rate(over_abs, len(gold_pos) + len(gold_neg)),
            'on_sufficient_positive': cnt('over_abstain_on_positive'),
            'on_decisive_negative': cnt('over_abstain_on_negative'),
            'definition': 'gold ACCEPT/REJECT but decision NEED_EVIDENCE'},
        'unsupported_acceptance_false_commit': {
            'cells': false_accept,
            'rate_over_non_accept_gold':
                _rate(false_accept, len(gold_neg) + len(gold_ins)),
            'on_decisive_negative': cnt('false_commit_accept_on_negative'),
            'on_insufficient': cnt('false_commit_accept_on_insufficient'),
            'definition': 'gold REJECT/NEED_EVIDENCE but decision ACCEPT'},
        'unsupported_rejection': {
            'cells': unsupported_reject,
            'rate_over_non_reject_gold':
                _rate(unsupported_reject, len(gold_pos) + len(gold_ins)),
            'on_sufficient_positive': cnt('unsupported_reject_on_positive'),
            'on_insufficient': cnt('unsupported_reject_on_insufficient'),
            'definition': 'gold ACCEPT/NEED_EVIDENCE but decision REJECT'},
    }


def model_block(name, rows):
    parseable = [r for r in rows if r['parsed'] in TERNARY]
    n_all, n_par = len(rows), len(parseable)
    ok = [int(r['appropriate']) for r in parseable]
    clusters = [r['instance_id'] for r in parseable]
    overall_ci = _cluster_bootstrap(ok, clusters)

    by_class = {}
    for cls in CLASSES:
        cr = [r for r in parseable if r['evidence_class'] == cls]
        cok = [int(r['appropriate']) for r in cr]
        ci = _cluster_bootstrap(cok, [r['instance_id'] for r in cr])
        by_class[cls] = {
            'n_cells': len(cr),
            'n_issues': len({r['instance_id'] for r in cr}),
            'n_correct': sum(cok),
            'decision_appropriateness': _rate(sum(cok), len(cr)),
            'ci95_issue_cluster_seed7_n10000': ci['ci95'],
            'parsed_distribution': {d: sum(r['parsed'] == d for r in cr)
                                    for d in DECISIONS},
        }
    # Always-NEED baseline: a policy that answers NEED_EVIDENCE to every cell
    # is appropriate exactly on gold == NEED_EVIDENCE (the insufficient class).
    n_need_gold = sum(1 for r in rows if r['cee_gold'] == 'NEED_EVIDENCE')
    return {
        'model_profile': name,
        'model_requested': rows[0]['model_requested'],
        'model_served': sorted({r['model_served'] for r in rows}),
        'e1_served_model_id': rows[0]['e1_served_model_id'],
        'served_id_string_matches_e1':
            all(r['served_matches_e1_model'] for r in rows),
        'n_requests': n_all, 'n_parseable': n_par,
        'n_invalid': sum(r['parsed'] == 'INVALID' for r in rows),
        'n_ambiguous': sum(r['parsed'] == 'AMBIGUOUS' for r in rows),
        'n_api_error': sum(r['parsed'] == 'API_ERROR' for r in rows),
        'decision_appropriateness': {
            'parseable_denominator': {
                'rate': _rate(sum(ok), n_par), 'n_correct': sum(ok),
                'n': n_par,
                'ci95_issue_cluster_seed7_n10000': overall_ci['ci95'],
                'n_clusters': overall_ci['n_clusters']},
            'all_requests_denominator': {
                'rate': _rate(sum(ok), n_all), 'n_correct': sum(ok),
                'n': n_all,
                'note': 'INVALID/AMBIGUOUS/API_ERROR count as not appropriate'},
        },
        'always_need_baseline': {
            'rate': _rate(n_need_gold, n_all), 'n_correct': n_need_gold,
            'n': n_all,
            'definition': 'a constant NEED_EVIDENCE policy is appropriate '
                          'only on the 9 insufficient-evidence gold cells'},
        'by_evidence_class': by_class,
        'confusion_matrix': confusion(rows),
        'error_families': error_families(rows),
        'cost': {
            'tokens_in': sum(r['tokens_in'] for r in rows),
            'tokens_out': sum(r['tokens_out'] for r in rows),
            'usd_total': round(sum(r['cost_usd'] for r in rows), 6),
            'wall_s_total': round(sum(r['wall_s'] for r in rows), 2)},
        'wire_audit': {
            'response_format_modes': sorted({r['response_format_mode']
                                             for r in rows}),
            'server_schema_enforced_any': any(r['server_schema_enforced']
                                              for r in rows),
            'schema_downgraded_any': any(r['schema_downgraded'] for r in rows),
            'plain_text_fallback_any': any(r['plain_text_fallback']
                                           for r in rows),
            'tools_sent_total': sum(r['tools_sent'] for r in rows)},
    }


def paired(ds, gpt):
    ib = {r['bundle_id']: r for r in ds}
    ic = {r['bundle_id']: r for r in gpt}
    keys = sorted(set(ib) & set(ic))
    pairs, deltas, clusters = [], [], []
    ds_only = gpt_only = 0
    for k in keys:
        a, b = ib[k], ic[k]
        ca, cb = int(a['appropriate']), int(b['appropriate'])
        d = ca - cb  # +1 DS correct & GPT wrong
        deltas.append(d)
        clusters.append(a['instance_id'])
        if ca and not cb:
            ds_only += 1
        if cb and not ca:
            gpt_only += 1
        pairs.append({
            'bundle_id': k, 'instance_id': a['instance_id'],
            'scenario': a['scenario'], 'evidence_class': a['evidence_class'],
            'gold': a['cee_gold'],
            'deepseek_parsed': a['parsed'], 'gpt_parsed': b['parsed'],
            'deepseek_appropriate': bool(ca), 'gpt_appropriate': bool(cb),
            'delta_deepseek_minus_gpt': d})
    ci = _cluster_bootstrap(deltas, clusters)
    n = len(keys)
    return {
        'shared_bundles': n, 'shared_issues': len(set(clusters)),
        'paired_set_complete': n == 22
        and set(ib) == set(ic) == set(keys),
        'deepseek_rate': _rate(sum(p['deepseek_appropriate'] for p in pairs),
                               n),
        'gpt_rate': _rate(sum(p['gpt_appropriate'] for p in pairs), n),
        'mean_paired_delta_deepseek_minus_gpt': ci['mean'],
        'delta_ci95_issue_cluster_seed7_n10000': ci['ci95'],
        'delta_ci_n_clusters': ci['n_clusters'],
        'deepseek_correct_gpt_wrong': ds_only,
        'gpt_correct_deepseek_wrong': gpt_only,
        'mcnemar_exact_two_sided_p_descriptive':
            round(mcnemar_exact_p(gpt_only, ds_only), 4),
        'mcnemar_note': 'descriptive only; discordant n is small and issue '
                        'clustering makes cells non-independent',
        'changed_pairs': [p for p in pairs if p['delta_deepseek_minus_gpt']],
        'all_pairs': pairs,
    }


def e1_mechanism_block():
    """Side-by-side E1 numbers for a MECHANISM-ONLY discussion. Never pooled
    with CEE; version drift is flagged."""
    if not EV1_METRICS.exists():
        return {'available': False, 'path': str(EV1_METRICS)}
    m = json.loads(EV1_METRICS.read_text(encoding='utf-8'))
    pick = {}
    for name, blk in m.get('models', {}).items():
        pooled = blk['pooled']
        pick[name] = {
            'e1_oracle_DA': pooled['oracle']['decision_appropriateness']['rate'],
            'e1_condition_DA':
                pooled['condition']['decision_appropriateness']['rate'],
            'e1_over_abstention_oracle_rate':
                pooled['oracle']['over_abstention_rate'],
            'e1_false_commit_accept_oracle_cells':
                pooled['oracle']['false_commit_accept_cells'],
        }
        # T3A-T is the closest E1 condition (full evidence, tools available).
        t3at = blk['conditions'].get('T3A-T')
        if t3at:
            pick[name]['e1_T3AT_oracle_DA'] = \
                t3at['oracle']['decision_appropriateness']['rate']
            pick[name]['e1_T3AT_condition_DA'] = \
                t3at['condition']['decision_appropriateness']['rate']
            pick[name]['e1_T3AT_oracle_DA_ci95'] = \
                t3at['oracle']['decision_appropriateness'][
                    'ci95_issue_cluster_seed7_n10000']
    cmp_ = {}
    for c in m.get('paired_comparisons', []):
        cmp_[c['candidate']] = {
            'e1_oracle_delta_vs_baseline':
                c['oracle']['paired_delta_candidate_minus_baseline'],
            'e1_oracle_delta_ci95':
                c['oracle']['delta_ci95_issue_cluster_seed7_n10000'],
            'e1_T3AT_oracle_delta':
                c['per_condition'].get('T3A-T', {}).get('oracle', {})
                .get('paired_delta_candidate_minus_baseline')}
    return {
        'available': True, 'path': str(EV1_METRICS),
        'per_model': pick, 'paired': cmp_,
        'discipline': 'CEE and E1 are DIFFERENT protocols: E1 bundles '
                      'evidence acquisition/tool policy with interpretation; '
                      'CEE removes acquisition. Report side by side only; do '
                      'NOT pool, subtract into a causal effect, or relabel. '
                      'E1 DeepSeek served model id is the historical '
                      'deepseek-flash backend; the 2026 endpoint, though it '
                      'returns the same id string, is documented as '
                      'DeepSeek-V4.1-Flash-1017, so weights are not proven '
                      'identical across E1 and CEE.',
    }


def build_report(metrics):
    audit_p = CEE_DIR / 'cee_v11_run_audit.json'
    freeze_p = CEE_DIR / 'cee_v1_1_freeze_manifest.json'
    compat_p = CEE_DIR / cee.COMPATIBILITY_REPORT
    audit = json.loads(audit_p.read_text(encoding='utf-8')) \
        if audit_p.exists() else {}
    freeze = json.loads(freeze_p.read_text(encoding='utf-8')) \
        if freeze_p.exists() else {}

    def _h(p):
        b = (CEE_DIR / p).read_bytes() if (CEE_DIR / p).exists() else None
        import hashlib
        return hashlib.sha256(b).hexdigest() if b is not None else None

    ds = metrics['models']['deepseek-flash']
    gp = metrics['models']['gpt-4.1-mini']
    recorded = round(ds['cost']['usd_total'] + gp['cost']['usd_total'], 6)
    return {
        'document': 'GroundedReview CEE v1.1 final report - Unified JSON Mode',
        'protocol': cee.CEE_PROTOCOL_VERSION,
        'predecessor': cee.PREDECESSOR_VERSION,
        'status': '44 authorised cells executed and scored; stopped per '
                  'authorisation (no Gemini, no new issues, no extra paid '
                  'experiment, no git commit)',
        'headline': {
            'deepseek_DA': ds['decision_appropriateness'][
                'parseable_denominator']['rate'],
            'gpt_DA': gp['decision_appropriateness'][
                'parseable_denominator']['rate'],
            'always_NEED_baseline': ds['always_need_baseline']['rate'],
            'paired_delta_DS_minus_GPT': metrics['paired_comparison'][
                'mean_paired_delta_deepseek_minus_gpt'],
            'delta_ci95': metrics['paired_comparison'][
                'delta_ci95_issue_cluster_seed7_n10000'],
            'mcnemar_p_descriptive': metrics['paired_comparison'][
                'mcnemar_exact_two_sided_p_descriptive'],
            'all_errors_are_over_abstention': ds['error_families'][
                'over_abstention']['cells'] + gp['error_families'][
                'over_abstention']['cells'],
            'zero_unsupported_acceptance': ds['error_families'][
                'unsupported_acceptance_false_commit']['cells']
                + gp['error_families']['unsupported_acceptance_false_commit'][
                    'cells'],
            'zero_unsupported_rejection': ds['error_families'][
                'unsupported_rejection']['cells']
                + gp['error_families']['unsupported_rejection']['cells'],
            'zero_invalid_ambiguous_apierror':
                ds['n_invalid'] + ds['n_ambiguous'] + ds['n_api_error']
                + gp['n_invalid'] + gp['n_ambiguous'] + gp['n_api_error'],
        },
        'schema_compatibility_audit': {
            'mode_requested_both_arms': 'response_format=json_object',
            'deepseek_accepted': True, 'openai_accepted': True,
            'json_schema_requested_any_cell': False,
            'plain_text_fallback_used_any_cell': bool(
                ds['wire_audit']['plain_text_fallback_any']
                or gp['wire_audit']['plain_text_fallback_any']),
            'server_side_schema_enforced': bool(
                ds['wire_audit']['server_schema_enforced_any']
                or gp['wire_audit']['server_schema_enforced_any']),
            'local_five_property_validation':
                'cee_protocol_v11.validate_decision_object; every response '
                'validated; no field completion/coercion/repair',
            'predecessor_block': 'cee-fixed-v1 could not run: DeepSeek '
                                 'rejected json_schema for all current models '
                                 '(HTTP 400); see compatibility stop report',
            'compatibility_stop_report': cee.COMPATIBILITY_REPORT,
            'compatibility_stop_report_sha256': _h(cee.COMPATIBILITY_REPORT),
        },
        'zero_tools_audit': {
            'tools_sent_total': ds['wire_audit']['tools_sent_total']
            + gp['wire_audit']['tools_sent_total'],
            'turns_per_cell': 1, 'escalation': 'none',
        },
        'model_identity_audit': {
            'deepseek': {
                'requested': ds['model_requested'],
                'served_id_string': ds['model_served'],
                'e1_served_id_string': ds['e1_served_model_id'],
                'id_string_equal_to_e1': ds['served_id_string_matches_e1'],
                'version_drift_disclosure': 'The 2026 DeepSeek endpoint '
                    'returns the id string "deepseek-flash" but official docs '
                    '(accessed 2026-10-23/24) state the current backend is '
                    'DeepSeek-V4.1-Flash-1017 (legacy deepseek-v4-flash '
                    'aliases retired 2026-07-24). Identical id string does '
                    'NOT prove identical weights to the E1 DeepSeek arm; CEE '
                    'is therefore not a same-version reproduction of the E1 '
                    'DeepSeek model and E1-vs-CEE DeepSeek differences may '
                    'mix model-version change with protocol change.'},
            'gpt': {
                'requested': gp['model_requested'],
                'served_id_string': gp['model_served'],
                'e1_served_id_string': gp['e1_served_model_id'],
                'id_string_equal_to_e1': gp['served_id_string_matches_e1'],
                'version_drift_disclosure': 'served id '
                    'gpt-4.1-mini-2025-04-14 matches the E1 served id.'},
        },
        'budget_audit': {
            'recorded_scored_spend_usd': recorded,
            'recorded_by_model': {
                'deepseek-flash': ds['cost']['usd_total'],
                'gpt-4.1-mini': gp['cost']['usd_total']},
            'hard_cap_usd': 1.00, 'within_cap': recorded <= 1.0,
            'guard': 'pre-call BudgetGuard, peak prices, per-model $0.50',
            'unscored_faulted_calls': {
                'count': 2, 'provider': 'deepseek',
                'nature': 'two live attempts on the FIRST bundle failed in '
                          'the LOCAL client (SDK ChatCompletion.content '
                          'attribute bug) AFTER an HTTP 200 was returned and '
                          'BEFORE any row was written; they were never scored '
                          'or counted as a cell decision and are not in the '
                          '44. Fixed before the successful run; resume logic '
                          'gave every bundle exactly one scored response.',
                'realistic_cost_usd_approx': 0.0015,
                'conservative_upper_bound_usd': 0.0111,
                'total_including_faulted_upper_bound_usd':
                    round(recorded + 0.0111, 4),
                'still_within_hard_cap': recorded + 0.0111 <= 1.0},
            'raw_paid_completions_issued': 46,
            'scored_cells': 44,
        },
        'hash_audit': {
            'prompt_fingerprint_v11': cee.cee_prompt_fingerprint(),
            'prompt_fingerprint_v1_text_unchanged':
                freeze.get('prompt', {}).get('fingerprint_v1'),
            'cee_gold_sha256':
                metrics['models']['deepseek-flash'] and audit.get(
                    'version', {}).get('cee_gold_sha256'),
            'build_manifest_sha256':
                audit.get('version', {}).get('cee_build_manifest_sha256'),
            'cee_plan_sha256':
                audit.get('version', {}).get('cee_plan_sha256'),
            'bundles_byte_identical_to_v1':
                freeze.get('reused_assets', {})
                .get('bundles_byte_identical_to_v1'),
            'code_sha256': freeze.get('code_sha256', {}),
            'result_files': {
                'deepseek': _h(DS_FILE), 'gpt': _h(GPT_FILE)},
        },
        'mechanism_interpretation_data_only': {
            'what_CEE_shows': [
                'On byte-identical complete bundles both models accepted all '
                '7 sufficient-positive cases and abstained on all 9 '
                'insufficient cases; neither produced an unsupported ACCEPT '
                'or unsupported REJECT (0 each).',
                'The only CEE errors were over-abstention on decisive-negative'
                ' (REJECT-gold) bundles: DeepSeek 2/6, GPT 4/6.',
                'Cross-model CEE difference is small (DA 0.909 vs 0.818, '
                'paired delta +0.091, cluster CI [0,0.217] crossing 0, exact '
                'McNemar p=0.625, 4 discordant pairs); at this sample size '
                'interpretation quality on fixed evidence is broadly similar '
                'and the edge runs in the same direction.'],
            'CEE_vs_E1_side_by_side': {
                'deepseek': {'e1_oracle_DA': 0.5909,
                             'e1_over_abstention_rate': 0.6308,
                             'e1_T3AT_oracle_DA': 0.8636,
                             'cee_DA': ds['decision_appropriateness'][
                                 'parseable_denominator']['rate'],
                             'cee_over_abstention_cells': ds['error_families'][
                                 'over_abstention']['cells']},
                'gpt': {'e1_oracle_DA': 0.6727,
                        'e1_false_commit_accept_cells': 7,
                        'e1_T3AT_oracle_DA': 0.8636,
                        'cee_DA': gp['decision_appropriateness'][
                            'parseable_denominator']['rate'],
                        'cee_false_commit_accept_cells': 0}},
            'bounds_on_claims': [
                'Mechanism discussion only; CEE and E1 DA were NOT pooled or '
                'averaged and no causal effect size is computed.',
                'The GPT E1->CEE disappearance of unsupported acceptance '
                '(7 -> 0) is consistent with complete, pre-adjudicated '
                'evidence removing under-acquisition, but T3A-T (full active '
                'evidence) already had GPT DA 0.8636; multiple mechanisms '
                '(acquisition, single-turn framing, model-version for '
                'DeepSeek) differ across protocols, so the shift cannot be '
                'attributed causally to a single factor.',
                'DeepSeek E1 over-abstention (63.1% pooled oracle) is much '
                'lower in CEE (2 cells), consistent with acquisition/policy '
                'contributing, but the DeepSeek model-version drift means a '
                'version contribution cannot be excluded.',
                'n=22 / 10 issue clusters, class sizes 7/6/9; all CIs are '
                'wide and findings are exploratory.'],
        },
        'metrics_file': 'cee_v11_metrics.json',
        'result_files': [DS_FILE, GPT_FILE],
    }


def main():
    ds = load('deepseek-flash', DS_FILE)
    gpt = load('gpt-4.1-mini', GPT_FILE)
    # shared bundle identity sanity
    if [r['bundle_id'] for r in ds] != [r['bundle_id'] for r in gpt]:
        raise SystemExit('bundle ordering/identity differs across models')
    out = {
        'metric': 'groundedreview_cee_v11_fixed_evidence',
        'protocol': cee.CEE_PROTOCOL_VERSION,
        'predecessor_protocol': cee.PREDECESSOR_VERSION,
        'condition': cee.CEE_CONDITION,
        'prompt_fingerprint_v11': cee.cee_prompt_fingerprint(),
        'output_mode': cee.OUTPUT_MODE,
        'bootstrap': {'unit': 'issue cluster (instance_id)', 'seed': SEED,
                      'n_boot': N_BOOT},
        'denominator_discipline': 'DA shown on parseable and all-requests '
                                  'denominators; INVALID/AMBIGUOUS/API_ERROR '
                                  'are separate, never mapped to NEED_EVIDENCE',
        'models': {'deepseek-flash': model_block('deepseek-flash', ds),
                   'gpt-4.1-mini': model_block('gpt-4.1-mini', gpt)},
        'paired_comparison': paired(ds, gpt),
        'e1_mechanism_comparison_no_pooling': e1_mechanism_block(),
    }
    p = CEE_DIR / 'cee_v11_metrics.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                 encoding='utf-8')
    report = build_report(out)
    rp = CEE_DIR / 'cee_v11_final_report.json'
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                  encoding='utf-8')
    ba = report['budget_audit']
    print(f"budget: scored=${ba['recorded_scored_spend_usd']} "
          f"incl_faulted_upper=${ba['unscored_faulted_calls']['total_including_faulted_upper_bound_usd']} "
          f"(cap $1.00) raw_completions={ba['raw_paid_completions_issued']} "
          f"scored_cells={ba['scored_cells']}")
    for nm in ('deepseek-flash', 'gpt-4.1-mini'):
        b = out['models'][nm]
        da = b['decision_appropriateness']['parseable_denominator']
        ef = b['error_families']
        print(f"{nm}: DA={da['rate']} CI={da['ci95_issue_cluster_seed7_n10000']} "
              f"alwaysNEED={b['always_need_baseline']['rate']} "
              f"overAbst={ef['over_abstention']['cells']} "
              f"falseAccept={ef['unsupported_acceptance_false_commit']['cells']} "
              f"unsupReject={ef['unsupported_rejection']['cells']} "
              f"${b['cost']['usd_total']}")
    pc = out['paired_comparison']
    print(f"paired DS-GPT delta={pc['mean_paired_delta_deepseek_minus_gpt']} "
          f"CI={pc['delta_ci95_issue_cluster_seed7_n10000']} "
          f"discord(DSonly/GPTonly)={pc['deepseek_correct_gpt_wrong']}/"
          f"{pc['gpt_correct_deepseek_wrong']} "
          f"mcnemar_p={pc['mcnemar_exact_two_sided_p_descriptive']}")
    print(f'wrote {p.name}')


if __name__ == '__main__':
    main()
