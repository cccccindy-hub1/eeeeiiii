"""Phase-2 metrics: integrity detection, merge accuracy, clustered CIs, cost.

Outputs:
  scenario matrix   per model x condition x scenario:
                      n, merge_acc, integrity detection via the INTENDED surface,
                      detection+action (bad evidence caught AND REJECT),
                      false-evidence-alarm rate
  valid controls    false-reject rate and false-alarm rate on valid fixtures
  merge accuracy    per model x condition, with issue-cluster bootstrap 95% CI
                    (resampled by instance_id, since 19 patches share 8 issues)
  cost              tokens in/out, tool calls, wall s, USD total and per CORRECT
                    merge decision; acceptance-log escalations (tier-D answer peeking)

Read-only with respect to Phase-1 metrics.py / result files.
"""
from __future__ import annotations

import argparse, json, random
from collections import defaultdict

from pilot import read_jsonl

INVALID_SCENARIOS = ('wrong_patch', 'stale', 'incomplete', 'contradictory')
# intended verification surface for each scenario
SURFACE = {
    'wrong_patch': ('called_linkage', 'saw_linked_false'),
    'stale': ('called_freshness', 'saw_fresh_false'),
    'incomplete': ('called_coverage', 'saw_coverage_incomplete'),
    'contradictory': ('called_consistency', 'saw_contradicted'),
}
CLUSTER_KEY = 'instance_id'


def _decision_accept(parsed):
    if isinstance(parsed, dict):
        return str(parsed.get('decision', '')).upper() == 'ACCEPT'
    if isinstance(parsed, str):
        return parsed.strip().upper() == 'ACCEPT'
    return False


def evaluate_row(r):
    truth_accept = bool(r.get('merge_acceptable'))
    decided_accept = _decision_accept(r.get('parsed'))
    scen = r.get('scenario')
    exp = r.get('expected_integrity') or {}
    out = {
        'merge_correct': decided_accept == truth_accept,
        'false_approve': (not truth_accept) and decided_accept,
        'false_reject': truth_accept and (not decided_accept),
        'scenario': scen, 'condition': r['condition'], 'model': r.get('model'),
        'id': r.get('id'),
        CLUSTER_KEY: r.get(CLUSTER_KEY),
        'flag': bool(r.get('evidence_mismatch_flag')),
        'escalated_to_acceptance_log': (r.get('acceptance_log_reveals') or 0) > 0,
        'cost_usd': r.get('cost_usd') or 0,
        'tokens_in': r.get('tokens_in') or 0, 'tokens_out': r.get('tokens_out') or 0,
        'tool_calls': r.get('tool_calls') or 0, 'wall_s': r.get('wall_s') or 0,
    }
    if scen in SURFACE:
        called, saw = SURFACE[scen]
        out['surface_queried'] = bool(r.get(called))
        out['surface_detected'] = bool(r.get(called) and r.get(saw))
        out['detected_and_acted'] = bool(out['surface_detected']
                                         and out['flag'] and not decided_accept)
        # weaker alternative: detected but decided via the acceptance-answer log
        out['detected_via_log_escalation'] = bool(
            out['surface_queried'] is not None and out['flag']
            and out['escalated_to_acceptance_log'] and not decided_accept)
    elif scen == 'valid':
        out['false_alarm'] = out['flag']          # flags valid evidence as bad
        out['correctly_trusted'] = (not out['flag']) and decided_accept == truth_accept
    return out


def cluster_bootstrap(values, clusters, n_boot=10000, seed=7):
    """Bootstrap the mean, resampling ISSUES (clusters) with replacement."""
    by = defaultdict(list)
    for v, c in zip(values, clusters):
        by[c].append(v)
    keys = list(by)
    if len(keys) <= 1:
        m = sum(values) / len(values) if values else None
        return {'mean': m, 'ci95': [None, None], 'n_clusters': len(keys)}
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        chosen = [keys[rng.randrange(len(keys))] for _ in keys]
        vals = [v for k in chosen for v in by[k]]
        means.append(sum(vals) / len(vals))
    means.sort()
    return {'mean': sum(values) / len(values),
            'ci95': [round(means[int(.025 * n_boot)], 4),
                     round(means[int(.975 * n_boot) - 1], 4)],
            'n_clusters': len(keys)}


def mcnemar_exact_p(b, c):
    """Two-sided exact McNemar p for b (correct->wrong) and c (wrong->correct)
    discordant pairs. n is tiny here (<=5), so this is descriptive, not decisive."""
    import math
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1))
    return min(1.0, 2 * (0.5 ** n) * tail)


def paired_table(evals_by_cond, cond_a, cond_b, *, fixture_only):
    """Join the two conditions ONLY on shared review targets.

    The 58-cell design is NOT fully paired: T0/T1 run on 19 patches while
    T2/T3 run on 5 fixtures. Therefore aggregate marginal accuracies must never
    be compared as a paired experiment; a paired delta is valid only on targets
    both conditions actually share (here: the 5 fixture patch ids)."""
    def key(e):
        return (e['model'], e['id'])
    a_rows = {key(e): e for e in evals_by_cond.get(cond_a, [])}
    b_rows = {key(e): e for e in evals_by_cond.get(cond_b, [])}
    shared = sorted(set(a_rows) & set(b_rows))
    pairs = []
    corrected = broken = 0
    accept_to_reject = reject_to_accept = 0
    for k in shared:
        ea, eb = a_rows[k], b_rows[k]
        ca, cb = bool(ea['merge_correct']), bool(eb['merge_correct'])
        pa, pb = ea.get('_accept'), eb.get('_accept')
        if (not ca) and cb:
            corrected += 1
        if ca and (not cb):
            broken += 1
        if pa is True and pb is False:
            accept_to_reject += 1
        if pa is False and pb is True:
            reject_to_accept += 1
        pairs.append({'id': k[1], 'model': k[0],
                      'scenario': eb.get('scenario') or ea.get('scenario'),
                      f'{cond_a}_correct': ca, f'{cond_b}_correct': cb,
                      f'{cond_a}_decision': 'ACCEPT' if pa else 'REJECT',
                      f'{cond_b}_decision': 'ACCEPT' if pb else 'REJECT'})
    n = len(shared)
    acc_a = sum(1 for k in shared if a_rows[k]['merge_correct']) / n if n else None
    acc_b = sum(1 for k in shared if b_rows[k]['merge_correct']) / n if n else None
    return {
        'comparison': f'{cond_a} -> {cond_b}',
        'shared_targets': n,
        'fixture_only': fixture_only,
        f'acc_{cond_a}': round(acc_a, 4) if acc_a is not None else None,
        f'acc_{cond_b}': round(acc_b, 4) if acc_b is not None else None,
        'paired_accuracy_delta': round(acc_b - acc_a, 4) if n else None,
        'corrected_wrong_to_right': corrected,
        'broken_right_to_wrong': broken,
        'decision_flips_ACCEPT_to_REJECT': accept_to_reject,
        'decision_flips_REJECT_to_ACCEPT': reject_to_accept,
        'mcnemar_exact_p': round(mcnemar_exact_p(broken, corrected), 4),
        'note': ('paired on shared targets only; n is small and the exact test is '
                 'descriptive'),
        'pairs': pairs,
    }


def compute(records, n_boot=10000):
    records = list(records)
    evals = [evaluate_row(r) for r in records]
    # carry the raw accept decision onto the eval for paired flip counting
    for e, r in zip(evals, records):
        e['_accept'] = _decision_accept(r.get('parsed'))

    # ---- merge accuracy: model x condition (clustered CI) ----
    groups = defaultdict(list)
    for e in evals:
        if e['scenario'] in (None, 'valid') and e['condition'] in ('T0', 'T1'):
            groups[(e['model'], e['condition'])].append(e)
        elif e['condition'] in ('T2D', 'T3D', 'T2A', 'T3A'):
            # one cell per scenario row; all count toward merge accuracy
            groups[(e['model'], e['condition'])].append(e)
    merge_acc = {}
    for (model, cond), rows in sorted(groups.items()):
        bs = cluster_bootstrap([int(x['merge_correct']) for x in rows],
                               [x[CLUSTER_KEY] for x in rows], n_boot=n_boot)
        merge_acc[f'{model}|{cond}'] = {
            'n_patches': len(rows),
            'n_issues': len({x[CLUSTER_KEY] for x in rows}),
            'merge_accuracy': round(bs['mean'], 4) if bs['mean'] is not None else None,
            'ci95_cluster_bootstrap': bs['ci95'],
            'false_approve': sum(x['false_approve'] for x in rows),
            'false_reject': sum(x['false_reject'] for x in rows),
        }

    # ---- scenario integrity matrix: model x condition x scenario ----
    scen_groups = defaultdict(list)
    for e, r in zip(evals, records):
        if e['scenario']:
            scen_groups[(e['model'], e['condition'], e['scenario'])].append((e, r))
    scenario_matrix = {}
    for (model, cond, scen), pairs in sorted(scen_groups.items()):
        es = [e for e, _ in pairs]
        d = {'n': len(es),
             'merge_correct': sum(e['merge_correct'] for e in es)}
        if scen in INVALID_SCENARIOS:
            d.update({
                'surface_queried': sum(e.get('surface_queried', False) for e in es),
                'detected_via_intended_surface':
                    sum(e.get('surface_detected', False) for e in es),
                'detected_and_rejected':
                    sum(e.get('detected_and_acted', False) for e in es),
                'mismatch_flag': sum(e['flag'] for e in es),
                'rejected': sum(not _decision_accept(rr.get('parsed'))
                                for _, rr in pairs),
                'caught_via_acceptance_log_escalation':
                    sum(e.get('detected_via_log_escalation', False) for e in es),
            })
        elif scen == 'valid':
            d.update({
                'false_reject': sum(e['false_reject'] for e in es),
                'false_evidence_alarm': sum(e.get('false_alarm', False) for e in es),
                'correctly_trusted': sum(e.get('correctly_trusted', False) for e in es),
            })
        scenario_matrix[f'{model}|{cond}|{scen}'] = d

    # ---- cost: model x condition ----
    cost = {}
    for (model, cond), rows in sorted(groups.items()):
        ncorr = sum(x['merge_correct'] for x in rows)
        usd = sum(x['cost_usd'] for x in rows)
        cost[f'{model}|{cond}'] = {
            'n_cells': len(rows),
            'tokens_in': sum(x['tokens_in'] for x in rows),
            'tokens_out': sum(x['tokens_out'] for x in rows),
            'tool_calls': sum(x['tool_calls'] for x in rows),
            'wall_s_total': round(sum(x['wall_s'] for x in rows), 1),
            'usd_total': round(usd, 4),
            'usd_per_correct_decision': round(usd / ncorr, 4) if ncorr else None,
            'acceptance_log_escalations':
                sum(x['escalated_to_acceptance_log'] for x in rows),
        }

    # ---- PAIRED deltas on SHARED targets only (pre-registered) ----
    # The design is not fully paired (T0/T1 on 19 patches; T2/T3 on 5 fixtures),
    # so marginal accuracies across conditions must not be treated as a paired
    # comparison. Every table below joins two conditions on the same
    # (model, review target) and reports its own n; interpret only rows whose
    # shared targets match the intended paired subset (T2D/T3D, T2A/T3A, and
    # T0/T1-vs-fixture comparisons share exactly the 5 fixture patches).
    evals_by_cond = defaultdict(list)
    for e in evals:
        if e.get('error'):
            continue
        evals_by_cond[e['condition']].append(e)
    paired = []
    cond_order = ('T0', 'T1', 'T2D', 'T3D', 'T2A', 'T3A')
    present = [c for c in cond_order if evals_by_cond.get(c)]
    for i in range(len(present)):
        for j in range(i + 1, len(present)):
            ca, cb = present[i], present[j]
            tbl = paired_table(evals_by_cond, ca, cb, fixture_only=True)
            if tbl['shared_targets'] > 0:
                paired.append(tbl)

    return {
        'n_records': len(records),
        'n_patches': len({r['id'] for r in records if r.get('id')}),
        'n_issues': len({r.get(CLUSTER_KEY) for r in records if r.get(CLUSTER_KEY)}),
        'models': sorted({r.get('model') for r in records if r.get('model')}),
        'merge_accuracy': merge_acc,
        'scenario_matrix': scenario_matrix,
        'paired_deltas_shared_targets_only': paired,
        'cost': cost,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', default='evidence_store/phase2_results.jsonl')
    ap.add_argument('--out', default='evidence_store/metrics_phase2.json')
    ap.add_argument('--bootstrap', type=int, default=10000)
    a = ap.parse_args()
    from pathlib import Path
    m = compute(list(read_jsonl(a.results)), n_boot=a.bootstrap)
    Path(a.out).write_text(json.dumps(m, indent=2, ensure_ascii=False),
                           encoding='utf-8')
    print(json.dumps(m, indent=2, ensure_ascii=False)[:6000])
    print(f'\nwrote {a.out}')


if __name__ == '__main__':
    main()
