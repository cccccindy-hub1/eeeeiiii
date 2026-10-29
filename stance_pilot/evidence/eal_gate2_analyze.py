"""GroundedReview v2 — EAL Gate-2 analysis (offline; reads live results).

Produces evidence_store_eal/gate2_runs/eal_gate2_metrics.json and
eal_gate2_report.json covering the eight items in the 2026-10-25 Gate-2
authorisation:

  1. per model x layer Decision Appropriateness: n, rate (parseable AND
     all-requests), issue-cluster bootstrap 95% CI (seed=7, n=10000,
     unit=instance_id);
  2. the three PRE-REGISTERED paired contrasts with cluster CIs:
     Adjudicated-Raw, Structured-Raw, Adjudicated-Structured (any sign);
  3. per-layer 3x3 confusion, Always-NEED baseline, and the three error
     families (over-abstention / unsupported accept / unsupported reject);
  4. same-fixture cross-layer decision transition matrices;
  5. stratification by decisive-negative / sufficient-positive /
     insufficient-evidence;
  6. verbatim reason / missing_evidence / evidence_gap mechanism audit with
     flags for misuse of stale / unlinked / incomplete information;
  7. sensitivity/limits: raw length, decisive-evidence position, derived
     summaries, missing probe source;
  8. engineering audit: served model, output format, cost, tokens, latency,
     frozen hashes, api errors, budget status.

    uv run --python 3.13 -m evidence.eal_gate2_analyze
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl, TERNARY
from evidence.cee_analyze_v11 import _cluster_bootstrap, mcnemar_exact_p
from evidence import eal_protocol as eal

ROOT = Path(__file__).resolve().parent.parent
G2_DIR = ROOT / 'evidence_store_eal' / 'gate2'
RUN_DIR = ROOT / 'evidence_store_eal' / 'gate2_runs'
MANIFEST = G2_DIR / 'eal_gate2_materials_manifest.json'
FREEZE = G2_DIR / 'eal_gate2_freeze_manifest.json'
SEED, N_BOOT = 7, 10000
LAYERS = list(eal.LAYERS)
MODELS = ['deepseek-flash', 'gpt-4.1-mini']
DECISIONS = ['ACCEPT', 'REJECT', 'NEED_EVIDENCE']
CLASSES = ['sufficient_positive', 'decisive_negative', 'insufficient']
CONTRASTS = [('adjudicated', 'raw', 'Adjudicated_minus_Raw'),
             ('structured', 'raw', 'Structured_minus_Raw'),
             ('adjudicated', 'structured', 'Adjudicated_minus_Structured')]

STALE_RE = re.compile(r'stale|fresh|not.{0,12}(current|new)|old commit', re.I)
LINK_RE = re.compile(r'unlink|un-linked|linkage|linked|different (patch|base|'
                     r'commit)|does not apply', re.I)
INCOMPLETE_RE = re.compile(r'incomplete|coverage|not (all )?(covered|run)|'
                           r'partial|only \d+ of', re.I)
SYMPTOM_RE = re.compile(r'symptom|probe|reproduce|still (fails|errors)|'
                        r'persists', re.I)


def _rate(n, d):
    return round(n / d, 4) if d else None


def _fname(m, live=True):
    kind = 'live' if live else 'mock'
    return f'eal_gate2_{kind}_{m.replace(".", "").replace("-", "_")}_results.jsonl'


def load_results(live=True):
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    by_bid = {i['bundle_id']: i for i in man['items']}
    out = {}
    for m in MODELS:
        p = RUN_DIR / _fname(m, live)
        rows = read_jsonl(str(p))
        if len(rows) != 66 or len({(r['bundle_id'], r['layer'])
                                   for r in rows}) != 66:
            raise SystemExit(f'{m}: expected 66 unique cells, got {len(rows)}')
        out[m] = {(r['bundle_id'], r['layer']): r for r in rows}
    return man, by_bid, out


def _correct(r):
    return bool(r['appropriate']) if r['parseable'] else None


def da_block(rows):
    """rows: 22 cells for one model x layer."""
    par = [r for r in rows if r['parseable']]
    alln = len(rows)
    ok_all = [1 if r['appropriate'] is True else 0 for r in rows]
    ok_par = [1 if r['appropriate'] is True else 0 for r in par]
    ci_all = _cluster_bootstrap(ok_all, [r['instance_id'] for r in rows])
    ci_par = _cluster_bootstrap(ok_par, [r['instance_id'] for r in par])
    need_gold = sum(1 for r in rows if r['cee_gold'] == 'NEED_EVIDENCE')
    return {
        'n_requests': alln, 'n_parseable': len(par),
        'n_invalid': sum(r['parsed'] == 'INVALID' for r in rows),
        'n_ambiguous': sum(r['parsed'] == 'AMBIGUOUS' for r in rows),
        'n_api_error': sum(r['parsed'] == 'API_ERROR' for r in rows),
        'n_correct': sum(ok_par),
        'da_parseable': {
            'rate': _rate(sum(ok_par), len(par)),
            'n_correct': sum(ok_par), 'n': len(par),
            'ci95_issue_cluster_seed7_n10000': ci_par['ci95'],
            'n_clusters': ci_par['n_clusters']},
        'da_all_requests': {
            'rate': _rate(sum(ok_all), alln),
            'n_correct': sum(ok_all), 'n': alln,
            'ci95_issue_cluster_seed7_n10000': ci_all['ci95'],
            'n_clusters': ci_all['n_clusters'],
            'note': 'INVALID/AMBIGUOUS/API_ERROR count as not appropriate'},
        'always_need_baseline': {
            'rate': _rate(need_gold, alln), 'n_correct': need_gold,
            'n': alln},
    }


def confusion(rows):
    mat = {d: {g: 0 for g in DECISIONS} for d in DECISIONS}
    ni = na = ne = 0
    for r in rows:
        p = r['parsed']
        if p == 'INVALID':
            ni += 1
        elif p == 'AMBIGUOUS':
            na += 1
        elif p == 'API_ERROR':
            ne += 1
        else:
            mat[p][r['cee_gold']] += 1
    return {'rows_decision': DECISIONS, 'columns_gold': DECISIONS,
            'matrix': mat, 'n_invalid': ni, 'n_ambiguous': na,
            'n_api_error': ne}


def error_families(rows):
    par = [r for r in rows if r['parseable']]
    def cnt(lbl):
        return sum(1 for r in par if r['error_label'] == lbl)
    gp = [r for r in par if r['cee_gold'] == 'ACCEPT']
    gn = [r for r in par if r['cee_gold'] == 'REJECT']
    gi = [r for r in par if r['cee_gold'] == 'NEED_EVIDENCE']
    oa = cnt('over_abstain_on_positive') + cnt('over_abstain_on_negative')
    fa = (cnt('false_commit_accept_on_negative')
          + cnt('false_commit_accept_on_insufficient'))
    ur = (cnt('unsupported_reject_on_positive')
          + cnt('unsupported_reject_on_insufficient'))
    return {
        'over_abstention': {'cells': oa,
                            'rate_over_decisive_gold':
                                _rate(oa, len(gp) + len(gn)),
                            'on_sufficient_positive':
                                cnt('over_abstain_on_positive'),
                            'on_decisive_negative':
                                cnt('over_abstain_on_negative')},
        'unsupported_acceptance_false_commit': {
            'cells': fa, 'rate_over_non_accept_gold':
                _rate(fa, len(gn) + len(gi)),
            'on_decisive_negative':
                cnt('false_commit_accept_on_negative'),
            'on_insufficient':
                cnt('false_commit_accept_on_insufficient')},
        'unsupported_rejection': {
            'cells': ur, 'rate_over_non_reject_gold':
                _rate(ur, len(gp) + len(gi)),
            'on_sufficient_positive':
                cnt('unsupported_reject_on_positive'),
            'on_insufficient':
                cnt('unsupported_reject_on_insufficient')},
    }


def by_class(rows):
    out = {}
    for cls in CLASSES:
        cr = [r for r in rows if r['evidence_class'] == cls]
        ok = [1 if r['appropriate'] is True else 0 for r in cr]
        ci = _cluster_bootstrap(ok, [r['instance_id'] for r in cr])
        out[cls] = {'n_cells': len(cr),
                    'n_issues': len({r['instance_id'] for r in cr}),
                    'n_correct': sum(ok),
                    'da': _rate(sum(ok), len(cr)),
                    'ci95_issue_cluster_seed7_n10000': ci['ci95'],
                    'parsed_distribution':
                        {d: sum(r['parsed'] == d for r in cr)
                         for d in DECISIONS}}
    return out


def contrasts_for(model_res):
    """model_res: {(bid,layer): row}."""
    bids = sorted({b for (b, _l) in model_res})
    res = []
    for hi, lo, name in CONTRASTS:
        deltas, clusters, details = [], [], []
        n_hi_ok = n_lo_ok = 0
        for b in bids:
            rh, rl = model_res[(b, hi)], model_res[(b, lo)]
            ch, cl = _correct(rh), _correct(rl)
            if ch is None or cl is None:
                continue  # only matched parseable pairs feed the contrast
            d = ch - cl
            deltas.append(d)
            clusters.append(rh['instance_id'])
            n_hi_ok += ch
            n_lo_ok += cl
            details.append({'bundle_id': b,
                            'instance_id': rh['instance_id'],
                            'evidence_class': rh['evidence_class'],
                            'gold': rh['cee_gold'],
                            f'{hi}_decision': rh['parsed'],
                            f'{lo}_decision': rl['parsed'],
                            f'{hi}_correct': bool(ch),
                            f'{lo}_correct': bool(cl),
                            'delta': d})
        ci = _cluster_bootstrap(deltas, clusters)
        hi_only = sum(1 for x in details if x['delta'] == 1)
        lo_only = sum(1 for x in details if x['delta'] == -1)
        res.append({
            'contrast': name, 'high_abstraction': hi,
            'low_abstraction': lo, 'n_matched_parseable_pairs': len(deltas),
            'n_issues': len(set(clusters)),
            'high_da': _rate(n_hi_ok, len(deltas)),
            'low_da': _rate(n_lo_ok, len(deltas)),
            'mean_paired_delta': ci['mean'],
            'delta_ci95_issue_cluster_seed7_n10000': ci['ci95'],
            'high_correct_low_wrong': hi_only,
            'low_correct_high_wrong': lo_only,
            'mcnemar_exact_two_sided_p_descriptive':
                round(mcnemar_exact_p(lo_only, hi_only), 4),
            'changed_pairs': [x for x in details if x['delta']],
            'sign_note': 'delta may be negative; no monotonic abstraction '
                         'effect is assumed'})
    return res


def transitions(model_res):
    bids = sorted({b for (b, _l) in model_res})
    out = {}
    for a, b, name in [('raw', 'structured', 'raw_to_structured'),
                       ('structured', 'adjudicated',
                        'structured_to_adjudicated'),
                       ('raw', 'adjudicated', 'raw_to_adjudicated')]:
        mat = {x: {y: 0 for y in DECISIONS} for x in DECISIONS}
        skipped = 0
        for bid in bids:
            ra, rb = model_res[(bid, a)], model_res[(bid, b)]
            if ra['parsed'] not in TERNARY or rb['parsed'] not in TERNARY:
                skipped += 1
                continue
            mat[ra['parsed']][rb['parsed']] += 1
        out[name] = {'rows_' + a: DECISIONS, 'columns_' + b: DECISIONS,
                     'matrix': mat, 'cells_skipped_nonparseable': skipped}
    return out


def mechanism_audit(rows):
    """Data-only audit of verbatim free-text fields. Lists every error with
    its reason/gap and keyword flags, plus keyword prevalence. No mental
    state is inferred without quoted text."""
    errors, kw = [], defaultdict(int)
    for r in rows:
        reason = r.get('reason_verbatim') or ''
        missing = r.get('missing_evidence_verbatim') or ''
        blob = f'{reason} {missing}'
        flags = []
        for label, rx in (('stale/fresh', STALE_RE), ('linkage', LINK_RE),
                          ('coverage/incomplete', INCOMPLETE_RE),
                          ('symptom/probe', SYMPTOM_RE)):
            if rx.search(blob):
                flags.append(label)
                kw[label] += 1
        if r['parseable'] and not r['appropriate']:
            errors.append({
                'model': r['model_profile'], 'layer': r['layer'],
                'bundle_id': r['bundle_id'],
                'instance_id': r['instance_id'],
                'evidence_class': r['evidence_class'],
                'gold': r['cee_gold'], 'decision': r['parsed'],
                'error_label': r['error_label'],
                'evidence_gap_verbatim': r.get('evidence_gap_verbatim'),
                'reason_verbatim': reason,
                'missing_evidence_verbatim': missing,
                'keyword_flags': flags})
    # specific misuse checks requested: stale/unlinked/incomplete
    misuse = []
    for e in errors:
        blob = (e['reason_verbatim'] or '') + ' ' \
            + (e['missing_evidence_verbatim'] or '')
        if e['gold'] == 'REJECT' and e['decision'] == 'NEED_EVIDENCE' \
                and INCOMPLETE_RE.search(blob):
            misuse.append({'bundle_id': e['bundle_id'], 'layer': e['layer'],
                           'pattern': 'REJECT-gold withheld via coverage/'
                                      'incomplete claim',
                           'reason_excerpt': e['reason_verbatim'][:280]})
        if e['gold'] == 'ACCEPT' and STALE_RE.search(blob):
            misuse.append({'bundle_id': e['bundle_id'], 'layer': e['layer'],
                           'pattern': 'ACCEPT-gold but reason invokes '
                                      'stale/fresh concern',
                           'reason_excerpt': e['reason_verbatim'][:280]})
    return {'n_errors_parseable': len(errors),
            'keyword_mentions_across_all_rows': dict(kw),
            'flagged_potential_misuse': misuse,
            'errors': errors}


def sensitivity_block(man):
    rows = []
    for it in man['items']:
        ch = it['channels']
        rows.append({
            'bundle_id': it['bundle_id'],
            'instance_id': it['instance_id'],
            'p2p_per_test_map': ch['p2p_map'],
            'p2p_baseline_per_test_map': ch['p2p_baseline_map'],
            'probe_source_archived': ch['probe_source_archived'],
            'raw_bytes': it['layers']['raw']['bytes'],
            'structured_bytes': it['layers']['structured']['bytes'],
            'adjudicated_bytes': it['layers']['adjudicated']['bytes']})
    n = len(rows)
    return {
        'n': n,
        'derived_summary_disclosure': 'present in all 44 raw/structured '
                                      'Gate-2 payloads; runner summary is '
                                      'explicitly labelled pre-classified',
        'fixtures_without_p2p_per_test_map':
            sum(not r['p2p_per_test_map'] for r in rows),
        'fixtures_without_baseline_per_test_map':
            sum(not r['p2p_baseline_per_test_map'] for r in rows),
        'fixtures_without_probe_source':
            sum(not r['probe_source_archived'] for r in rows),
        'length_discipline': 'length is condition-determined; reported and '
                             'discussed, not used as a regression control',
        'per_fixture': rows,
    }


def engineering_block(by_bid, results):
    ap_path = RUN_DIR / 'eal_gate2_run_audit.json'
    audit = json.loads(ap_path.read_text(encoding='utf-8')) \
        if ap_path.exists() else {}
    freeze = json.loads(FREEZE.read_text(encoding='utf-8'))
    out = {'models': {}, 'audit_summary': {
        'total_spend_usd': audit.get('total_spend_usd'),
        'hard_cap_usd': audit.get('hard_cap_usd'),
        'within_total_cap': audit.get('within_total_cap'),
        'budget_status': audit.get('budget_status'),
        'cross_model_payload_byte_identity':
            audit.get('cross_model_payload_byte_identity')},
        'freeze_manifest_sha256':
            hashlib.sha256(FREEZE.read_bytes()).hexdigest()}
    for m in MODELS:
        rows = list(results[m].values())
        out['models'][m] = {
            'model_requested': sorted({r['model_requested'] for r in rows}),
            'model_served': sorted({r['model_served'] for r in rows}),
            'e1_served_model_id': rows[0]['e1_served_model_id'],
            'served_id_equals_e1_all_rows':
                all(r['served_matches_e1_model'] for r in rows
                    if r['served_matches_e1_model'] is not None),
            'response_format_modes':
                sorted({r['response_format_mode'] for r in rows}),
            'server_schema_enforced_any':
                any(r['server_schema_enforced'] for r in rows),
            'plain_text_fallback_any':
                any(r['plain_text_fallback'] for r in rows),
            'tools_sent_total': sum(r['tools_sent'] for r in rows),
            'tokens_in': sum(r['tokens_in_est'] for r in rows),
            'tokens_out': sum(r['tokens_out_est'] for r in rows),
            'cost_usd': round(sum(r['cost_usd'] for r in rows), 6),
            'wall_s_total': round(sum(r['wall_s'] for r in rows), 2),
            'n_api_error': sum(r['parsed'] == 'API_ERROR' for r in rows),
            'n_invalid': sum(r['parsed'] == 'INVALID' for r in rows),
            'n_ambiguous': sum(r['parsed'] == 'AMBIGUOUS' for r in rows),
            'raw_persisted_before_parse_all':
                all(r['raw_persisted_before_parse'] for r in rows),
            'payload_hashes_match_freeze_all':
                all(r['payload_sha256']
                    == freeze['payload_sha256'][r['payload_id']]['sha256']
                    for r in rows)}
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock-input', action='store_true',
                    help='analyse offline mock rows instead of live rows')
    args = ap.parse_args()
    live = not args.mock_input
    man, by_bid, results = load_results(live=live)
    report = {'metric': 'groundedreview_eal_gate2_abstraction_pilot',
              'protocol': eal.EAL_PROTOCOL_VERSION,
              'gate2_condition':
                  'eal-v0-draft1+gate2-derived-summary-disclosure',
              'bootstrap': {'unit': 'issue cluster (instance_id)',
                            'seed': SEED, 'n_boot': N_BOOT},
              'n_independent_issues':
                  len({i['instance_id'] for i in man['items']}),
              'models': {}, 'sensitivity': sensitivity_block(man)}
    all_errors = []
    for m in MODELS:
        layer_blocks, mech_rows = {}, []
        for l in LAYERS:
            rows = [results[m][(b, l)] for b in
                    sorted({bb for (bb, ll) in results[m] if ll == l})]
            layer_blocks[l] = {
                **da_block(rows), 'confusion_matrix': confusion(rows),
                'error_families': error_families(rows),
                'by_evidence_class': by_class(rows)}
            mech_rows.extend(rows)
        report['models'][m] = {
            'layers': layer_blocks,
            'paired_contrasts': contrasts_for(results[m]),
            'cross_layer_transitions': transitions(results[m]),
            'mechanism_audit': mechanism_audit(mech_rows)}
        all_errors.extend(report['models'][m]['mechanism_audit']['errors'])
    report['engineering_audit'] = engineering_block(by_bid, results)

    out_name = ('eal_gate2_metrics_mock.json' if args.mock_input
                else 'eal_gate2_metrics.json')
    (RUN_DIR / out_name).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # compact console summary
    for m in MODELS:
        for l in LAYERS:
            b = report['models'][m]['layers'][l]
            print(f"{m:<15} {l:<12} DA(par)={b['da_parseable']['rate']} "
                  f"CI={b['da_parseable']['ci95_issue_cluster_seed7_n10000']} "
                  f"DA(all)={b['da_all_requests']['rate']} "
                  f"inv/amb/api={b['n_invalid']}/{b['n_ambiguous']}/"
                  f"{b['n_api_error']}")
        for c in report['models'][m]['paired_contrasts']:
            print(f"   {c['contrast']:<32} d={c['mean_paired_delta']} "
                  f"CI={c['delta_ci95_issue_cluster_seed7_n10000']} "
                  f"flip(hi/lo)={c['high_correct_low_wrong']}/"
                  f"{c['low_correct_high_wrong']}")
    eng = report['engineering_audit']
    print('spend:', {m: eng['models'][m]['cost_usd'] for m in MODELS},
          'total=', eng['audit_summary']['total_spend_usd'],
          'status=', eng['audit_summary']['budget_status'])
    print('parseable errors total:', len(all_errors))
    print(f'wrote {out_name}')


if __name__ == '__main__':
    main()
