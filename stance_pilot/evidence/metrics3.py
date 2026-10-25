"""Phase-3 ternary metrics: evidence-sufficiency judgment quality.

The ternary protocol produces ACCEPT / REJECT / NEED_EVIDENCE, with
INVALID/AMBIGUOUS reserved for protocol failures. Two headline constructs are
kept deliberately separate:

  decision_appropriateness   per-gold ternary correctness, denominator =
                             PARSEABLE cells only (INVALID/AMBIGUOUS excluded;
                             a malformed answer says nothing about judgment)
  end_to_end_review_success  exact gold match over ALL cells; INVALID,
                             AMBIGUOUS and every mismatch are failures

Gold is the ASYMMETRIC evidence standard from evidence.ternary:
  gold ACCEPT        only ACCEPT is appropriate
  gold REJECT        only REJECT is appropriate (NEED on decisive evidence is
                      over-abstention; completeness is not required to reject)
  gold NEED_EVIDENCE only NEED is appropriate: committing either way on
                      unusable/insufficient evidence is premature
                        ACCEPT -> false_commit_accept (unsafe)
                        REJECT -> unsupported_reject

A third, separately-named section, `deployment_safe_view`, answers an
operational question ("did the system ever ACCEPT?") where NEED/INVALID/
AMBIGUOUS all count as non-acceptance. It MUST NOT be mixed into the judgment
metrics: rewarding abstention there and penalising over-abstention in
appropriateness answer different questions.

Binary metrics2.py is untouched.
"""
from __future__ import annotations

import argparse, json
from collections import defaultdict
from pathlib import Path

from pilot import read_jsonl
from evidence.metrics2 import cluster_bootstrap, mcnemar_exact_p
from evidence.ternary import TERNARY, PARSE_CLASSES

CLUSTER_KEY = 'instance_id'
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')

PROTOCOL_FAILURES = ('INVALID', 'AMBIGUOUS')
ERROR_CLASSES = (
    'appropriate_accept', 'appropriate_reject', 'appropriate_abstain',
    'over_abstain', 'false_approve', 'false_reject',
    'false_commit_accept', 'unsupported_reject',
    'invalid_protocol', 'ambiguous_protocol',
)


def load_gold(path):
    """Index frozen gold rows by (scenario, id, served_artifact_id), with a
    (scenario, id) fallback."""
    rows = read_jsonl(path)
    full = {}
    loose = {}
    for r in rows:
        full[(r['scenario'], r['id'], r['served_artifact_id'])] = r
        loose.setdefault((r['scenario'], r['id']), r)
    return {'full': full, 'loose': loose}


def gold_for(rec, gold):
    k = (rec.get('scenario'), rec.get('id'), rec.get('served_artifact_id'))
    if k in gold['full']:
        return gold['full'][k]
    return gold['loose'].get((rec.get('scenario'), rec.get('id')))


def classify(rec, grow):
    """Pure classifier: one result row joined with its frozen gold row.

    Returns parse/appropriateness/error labels plus the deployment-safety
    flags. Every metric downstream is computed from these primitives.
    """
    parsed = rec.get('parsed')
    if parsed not in PARSE_CLASSES:
        parsed = 'INVALID'
    parseable = parsed in TERNARY
    gold = grow['gold']

    if not parseable:
        error_class = ('invalid_protocol' if parsed == 'INVALID'
                       else 'ambiguous_protocol')
        appropriate = False
    else:
        appropriate = parsed == gold
        if gold == 'NEED_EVIDENCE':
            if parsed == 'NEED_EVIDENCE':
                error_class = 'appropriate_abstain'
            elif parsed == 'ACCEPT':
                # committing on unusable/insufficient evidence: the unsafe
                # premature-approval failure mode
                error_class = 'false_commit_accept'
            else:
                # rejecting without a decisive applicable failure
                error_class = 'unsupported_reject'
        elif gold == 'ACCEPT':
            if parsed == 'ACCEPT':
                error_class = 'appropriate_accept'
            elif parsed == 'REJECT':
                error_class = 'false_reject'
            else:
                error_class = 'over_abstain'
        else:  # gold REJECT (decisive applicable failure)
            if parsed == 'REJECT':
                error_class = 'appropriate_reject'
            elif parsed == 'ACCEPT':
                error_class = 'false_approve'
            else:
                # abstaining despite a decisive applicable failure
                error_class = 'over_abstain'

    decided = parseable and parsed in ('ACCEPT', 'REJECT')
    out = {
        'parsed': parsed,
        'parseable': parseable,
        'protocol_failure': (not parseable),
        'appropriate': appropriate,
        'e2e_success': appropriate,          # only an exact match succeeds;
                                            # INVALID/AMBIGUOUS already False
        'error_class': error_class,
        'decided': decided,
        'issued_decision': parseable and parsed != 'NEED_EVIDENCE',
        'false_approve': parsed == 'ACCEPT' and gold != 'ACCEPT',
        'false_reject': parsed == 'REJECT' and gold != 'REJECT',
        # deployment lens: anything that is not an explicit ACCEPT is a
        # non-acceptance, including abstentions and protocol failures
        'unsafe_accept': parsed == 'ACCEPT' and gold != 'ACCEPT',
        'safe_non_accept': parsed != 'ACCEPT',
        'gold': gold,
        'condition': rec.get('condition'),
        'model': rec.get('model'),
        'id': rec.get('id'),
        'scenario': rec.get('scenario'),
        'served_artifact_id': rec.get('served_artifact_id'),
        CLUSTER_KEY: rec.get(CLUSTER_KEY),
        'cost_usd': float(rec.get('cost_usd') or 0),
        'tokens_in': int(rec.get('tokens_in') or 0),
        'tokens_out': int(rec.get('tokens_out') or 0),
        'tool_calls': int(rec.get('tool_calls') or 0),
        'wall_s': float(rec.get('wall_s') or 0),
        'escalation_requested': len(rec.get('escalation_requested') or []),
        'escalation_granted': len(rec.get('escalation_granted') or []),
        'escalation_denied': len(rec.get('escalation_denied') or []),
        'budget_hit': bool(rec.get('budget_hit')),
        'emergency_hit': bool(rec.get('emergency_hit')),
    }
    return out


def _ratio(num, den):
    return round(num / den, 4) if den else None


def _condition_block(evals, n_boot):
    n = len(evals)
    parseable = [e for e in evals if e['parseable']]
    np_ = len(parseable)
    n_inv = sum(e['parsed'] == 'INVALID' for e in evals)
    n_amb = sum(e['parsed'] == 'AMBIGUOUS' for e in evals)
    n_appr = sum(e['appropriate'] for e in parseable)
    n_e2e = sum(e['e2e_success'] for e in evals)
    decided = [e for e in evals if e['decided']]
    n_need = sum(e['parseable'] and e['parsed'] == 'NEED_EVIDENCE'
                 for e in evals)

    err_counts = {k: 0 for k in ERROR_CLASSES}
    for e in evals:
        err_counts[e['error_class']] += 1

    bs_appr = cluster_bootstrap([int(e['appropriate']) for e in parseable],
                                [e[CLUSTER_KEY] for e in parseable],
                                n_boot=n_boot) if parseable else \
        {'mean': None, 'ci95': [None, None], 'n_clusters': 0}
    bs_e2e = cluster_bootstrap([int(e['e2e_success']) for e in evals],
                               [e[CLUSTER_KEY] for e in evals],
                               n_boot=n_boot) if evals else \
        {'mean': None, 'ci95': [None, None], 'n_clusters': 0}

    usd = sum(e['cost_usd'] for e in evals)
    post_esc = [e['parsed'] for e in evals if e['escalation_granted'] > 0]
    return {
        'n_cells': n,
        'n_issues': len({e[CLUSTER_KEY] for e in evals if e[CLUSTER_KEY]}),
        'n_parseable': np_,
        'n_invalid': n_inv,
        'n_ambiguous': n_amb,
        'invalid_or_ambiguous_rate_of_all': _ratio(n_inv + n_amb, n),
        # ---- judgment construct: parseable denominator only ----
        'decision_appropriateness': _ratio(n_appr, np_),
        'appropriateness_ci95_cluster_bootstrap': bs_appr['ci95'],
        'n_appropriate': n_appr,
        # ---- end-to-end construct: all cells, protocol failures fail ----
        'end_to_end_review_success': _ratio(n_e2e, n),
        'e2e_ci95_cluster_bootstrap': bs_e2e['ci95'],
        'n_e2e_success': n_e2e,
        # ---- decision coverage ----
        'decision_coverage_of_parseable': _ratio(
            sum(e['issued_decision'] for e in parseable), np_),
        'need_evidence_rate_of_parseable': _ratio(n_need, np_),
        # ---- error taxonomy ----
        'error_class_counts': err_counts,
        'appropriate_abstentions': err_counts['appropriate_abstain'],
        'over_abstentions': err_counts['over_abstain'],
        'premature_false_commit_accepts': err_counts['false_commit_accept'],
        'premature_unsupported_rejects': err_counts['unsupported_reject'],
        # ---- decided-subset confusion ----
        'n_decided': len(decided),
        'false_approve_decided': sum(e['false_approve'] for e in decided),
        'false_reject_decided': sum(e['false_reject'] for e in decided),
        # ---- escalation channel ----
        'escalation_requests': sum(e['escalation_requested'] for e in evals),
        'escalations_granted': sum(e['escalation_granted'] for e in evals),
        'escalations_denied': sum(e['escalation_denied'] for e in evals),
        'cells_with_granted_escalation': len(post_esc),
        'post_escalation_parsed_distribution': {
            d: post_esc.count(d) for d in TERNARY + PROTOCOL_FAILURES
            if post_esc.count(d)},
        # ---- cost ----
        'tokens_in': sum(e['tokens_in'] for e in evals),
        'tokens_out': sum(e['tokens_out'] for e in evals),
        'tool_calls': sum(e['tool_calls'] for e in evals),
        'wall_s_total': round(sum(e['wall_s'] for e in evals), 2),
        'usd_total': round(usd, 6),
        'usd_per_appropriate_decision': round(usd / n_appr, 6)
        if n_appr else None,
        'budget_hits': sum(e['budget_hit'] for e in evals),
        'emergency_hits': sum(e['emergency_hit'] for e in evals),
    }


def paired_ternary_table(evals, cond_a, cond_b):
    """Pair conditions on the same served fixture artifact (and model); only
    shared targets are compared. Appropriateness is the paired outcome. The
    exact McNemar test is descriptive at these n."""
    def key(e):
        return (e['model'], e['served_artifact_id'])
    a_rows = {key(e): e for e in evals if e['condition'] == cond_a}
    b_rows = {key(e): e for e in evals if e['condition'] == cond_b}
    shared = sorted(set(a_rows) & set(b_rows))
    pairs, broken, corrected = [], 0, 0
    flips = defaultdict(int)
    for k in shared:
        ea, eb = a_rows[k], b_rows[k]
        ca, cb = bool(ea['appropriate']), bool(eb['appropriate'])
        if ca and not cb:
            broken += 1
        if not ca and cb:
            corrected += 1
        flips[f'{ea["parsed"]}->{eb["parsed"]}'] += 1
        pairs.append({'served_artifact_id': k[1], 'model': k[0],
                      'scenario': eb['scenario'] or ea['scenario'],
                      f'{cond_a}_parsed': ea['parsed'],
                      f'{cond_b}_parsed': eb['parsed'],
                      f'{cond_a}_appropriate': ca,
                      f'{cond_b}_appropriate': cb})
    n = len(shared)
    return {
        'comparison': f'{cond_a} -> {cond_b}',
        'shared_targets': n,
        f'appropriateness_{cond_a}': _ratio(
            sum(a_rows[k]['appropriate'] for k in shared), n),
        f'appropriateness_{cond_b}': _ratio(
            sum(b_rows[k]['appropriate'] for k in shared), n),
        'paired_appropriateness_delta': _ratio(
            sum(b_rows[k]['appropriate'] for k in shared)
            - sum(a_rows[k]['appropriate'] for k in shared), n) if n else None,
        'appropriate_to_inappropriate': broken,
        'inappropriate_to_appropriate': corrected,
        'mcnemar_exact_p_descriptive':
            round(mcnemar_exact_p(broken, corrected), 4),
        'parsed_transition_counts': dict(flips),
        'pairs': pairs,
    }


def deployment_safe_view(evals):
    """Operational lens, reported in its OWN section.

    safe_non_accept merges NEED_EVIDENCE, REJECT, INVALID and AMBIGUOUS; it is
    useful for estimating worst-case auto-merge exposure but must never be
    averaged with or ranked against decision_appropriateness.
    """
    out = {}
    for cond in STATIC_CONDITIONS + ACTIVE_CONDITIONS:
        rows = [e for e in evals if e['condition'] == cond]
        if not rows:
            continue
        n = len(rows)
        accepts = [e for e in rows if e['parsed'] == 'ACCEPT']
        out[cond] = {
            'n_cells': n,
            'explicit_accepts': len(accepts),
            'unsafe_accepts_gold_non_accept':
                sum(e['unsafe_accept'] for e in accepts),
            'safe_non_acceptances': sum(e['safe_non_accept'] for e in rows),
            'safe_non_acceptance_rate': _ratio(
                sum(e['safe_non_accept'] for e in rows), n),
            'note': 'NEED/INVALID/AMBIGUOUS count as non-acceptance; this is a '
                    'deployment exposure metric, not a judgment metric',
        }
    return out


def compute(records, gold, *, include_mock=False, n_boot=10000):
    records = [r for r in records
               if not r.get('error') and (include_mock or not r.get('mock'))]
    evals = []
    missing = []
    for r in records:
        grow = gold_for(r, gold)
        if grow is None:
            missing.append(f"{r.get('scenario')}|{r.get('id')}|"
                           f"{r.get('served_artifact_id')}")
            continue
        evals.append(classify(r, grow))
    if missing:
        raise SystemExit('metrics3: results without frozen gold row: '
                         + '; '.join(sorted(set(missing))))

    # ---- per model x condition ----
    by_mc = defaultdict(list)
    for e in evals:
        by_mc[(e['model'], e['condition'])].append(e)
    conditions = {}
    for (model, cond), rows in sorted(by_mc.items()):
        d = _condition_block(rows, n_boot)
        d['model'] = model
        d['arm'] = ('static' if cond in STATIC_CONDITIONS
                    else 'active' if cond in ACTIVE_CONDITIONS else 'other')
        conditions[f'{model}|{cond}'] = d

    # ---- condition x scenario: full parsed distribution vs gold ----
    scenario_matrix = {}
    by_cs = defaultdict(list)
    for e in evals:
        by_cs[(e['model'], e['condition'], e['scenario'], e['gold'])].append(e)
    for (model, cond, scen, g), rows in sorted(by_cs.items()):
        dist = {p: 0 for p in TERNARY + PROTOCOL_FAILURES}
        for e in rows:
            dist[e['parsed']] += 1
        scenario_matrix[f'{model}|{cond}|{scen}'] = {
            'gold': g, 'n': len(rows), 'parsed_distribution': dist,
            'n_appropriate': sum(e['appropriate'] for e in rows
                                 if e['parseable']),
            'n_e2e_success': sum(e['e2e_success'] for e in rows),
        }

    # ---- paired deltas, shared served artifacts only ----
    models = sorted({e['model'] for e in evals})
    cond_order = STATIC_CONDITIONS + ACTIVE_CONDITIONS
    paired = []
    for model in models:
        me = [e for e in evals if e['model'] == model]
        present = [c for c in cond_order
                   if any(e['condition'] == c for e in me)]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                tbl = paired_ternary_table(me, present[i], present[j])
                if tbl['shared_targets'] > 0:
                    tbl['model'] = model
                    paired.append(tbl)

    return {
        'metric': 'groundedreview_phase3_ternary',
        'mock_rows_excluded': not include_mock,
        'n_records_scored': len(evals),
        'n_fixture_artifacts': len({e['served_artifact_id'] for e in evals}),
        'n_issues': len({e[CLUSTER_KEY] for e in evals if e[CLUSTER_KEY]}),
        'models': models,
        'conditions': conditions,
        'scenario_matrix': scenario_matrix,
        'paired_deltas_shared_artifacts_only': paired,
        'deployment_safe_view': deployment_safe_view(evals),
        'interpretation': {
            'decision_appropriateness': 'exact ternary match over parseable '
                'cells only; INVALID/AMBIGUOUS excluded from denominator',
            'end_to_end_review_success': 'exact ternary match over all cells; '
                'INVALID/AMBIGUOUS are failures',
            'asymmetry': 'on gold NEED_EVIDENCE both ACCEPT and REJECT are '
                'inappropriate; on gold REJECT a NEED is over-abstention and '
                'incomplete coverage does not make the rejection inappropriate',
            'paired_tables': 'valid only on shared served_artifact_id within '
                'model; McNemar is descriptive at small n',
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results',
                    default='evidence_store/phase3_ternary_results.jsonl')
    ap.add_argument('--gold', default='evidence_store/phase3_gold.jsonl')
    ap.add_argument('--out',
                    default='evidence_store/metrics_phase3_ternary.json')
    ap.add_argument('--include-mock', action='store_true',
                    help='score mock=true rows too (engineering checks only)')
    ap.add_argument('--bootstrap', type=int, default=10000)
    a = ap.parse_args()
    gold = load_gold(a.gold)
    records = list(read_jsonl(a.results))
    m = compute(records, gold, include_mock=a.include_mock,
                n_boot=a.bootstrap)
    Path(a.out).write_text(json.dumps(m, indent=2, ensure_ascii=False),
                           encoding='utf-8')
    print(json.dumps(m, indent=2, ensure_ascii=False)[:6000])
    print(f'\nwrote {a.out}')


if __name__ == '__main__':
    main()
