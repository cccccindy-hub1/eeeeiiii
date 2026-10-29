"""GroundedReview Research Consolidation Gate — INDEPENDENT statistical
recomputation of Experiment X ($0, fully offline, read-only on frozen gates).

This module deliberately does NOT import the X analyzer (eal_v21x_analyze)
or the shared stats module (eal_stats). It re-derives every number from the
two frozen LIVE result jsonl files + the frozen freeze manifest, using an
independently written cluster bootstrap that follows the same pre-registered
specification (unit=instance_id, 10 clusters, seed=7, n=10000, paired
percentile). Exact agreement with eal_v21x_live_analysis.json is then checked
by grc cross-validation; disagreement aborts.

Writes only evidence_store_eal/consolidation/.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'evidence_store_eal'
XRUNS = STORE / 'v21x_runs'
FREEZE = STORE / 'v21x' / 'eal_v21x_freeze_manifest.json'
OUTDIR = STORE / 'consolidation'

MODELS = ('deepseek-flash', 'gpt-4.1-mini')
CONDS = ('a0b0', 'a1b0', 'a0b1', 'a1b1')
SFX = {'deepseek-flash': 'deepseek_flash', 'gpt-4.1-mini': 'gpt_41_mini'}
SEED = 7
N_BOOT = 10000
DECISIONS = ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')


def _cluster_groups(pairs):
    """pairs: list of (value_or_list, cluster)."""
    g = defaultdict(list)
    for v, c in pairs:
        g[c].append(v)
    return g


def cell_stat(groups, keys):
    flat = [v for k in keys for v in groups[k]]
    return sum(flat) / len(flat)


def issue_stat(groups, keys):
    means = [sum(groups[k]) / len(groups[k]) for k in keys]
    return sum(means) / len(means)


def boot(pairs, estimand, *, n_boot=N_BOOT, seed=SEED):
    """Independently written whole-cluster paired percentile bootstrap.
    pairs: [(0/1 or per-fixture delta, instance_id), ...]."""
    g = _cluster_groups(pairs)
    keys = sorted(g)
    K = len(keys)
    stat = cell_stat if estimand == 'cell' else issue_stat
    point = stat(g, keys)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        pick = [keys[rng.randrange(K)] for _ in range(K)]
        draws.append(stat(g, pick))
    draws.sort()
    return {'estimand': estimand, 'point': round(point, 4),
            'ci_lo': round(draws[int(.025 * n_boot)], 4),
            'ci_hi': round(draws[int(.975 * n_boot) - 1], 4),
            'n_clusters': K,
            'n_cells': sum(len(g[k]) for k in keys)}


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    fz = json.loads(FREEZE.read_text(encoding='utf-8'))
    out = {'document': 'GroundedReview consolidation: independent X '
                       'recomputation', 'spec': {'seed': SEED,
                                                  'n_boot': N_BOOT,
                                                  'unit': 'instance_id',
                                                  'primary': 'issue'},
           'models': {}}

    for m in MODELS:
        rows = read_jsonl(str(XRUNS /
                              f'eal_v21x_live_{SFX[m]}_results.jsonl'))
        assert len(rows) == 88, (m, len(rows))
        by = {(r['bundle_id'], r['condition']): r for r in rows}
        bids = sorted({r['bundle_id'] for r in rows})
        # fixed aligned per-condition vectors
        vec = {}
        for c in CONDS:
            cr = [by[(b, c)] for b in bids]
            vec[c] = ([1.0 if r['appropriate'] else 0.0 for r in cr],
                      [r['instance_id'] for r in cr], cr)

        per_cond = {}
        for c in CONDS:
            vals, cl, cr = vec[c]
            per_cond[c] = {
                'n': len(cr),
                'DA': {e: boot(list(zip(vals, cl)), e) for e in
                       ('issue', 'cell')},
                'confusion': _confusion(cr)}

        def delta_vec(hi, lo):
            vh, ch, _ = vec[hi]
            vl, _, _ = vec[lo]
            return list(zip([a - b for a, b in zip(vh, vl)], ch))

        d10_00 = delta_vec('a1b0', 'a0b0')
        d11_01 = delta_vec('a1b1', 'a0b1')
        d01_00 = delta_vec('a0b1', 'a0b0')
        d11_10 = delta_vec('a1b1', 'a1b0')
        cl0 = vec['a0b0'][1]
        v00, v10, v01, v11 = (vec['a0b0'][0], vec['a1b0'][0],
                              vec['a0b1'][0], vec['a1b1'][0])
        dAB = list(zip([a - b - c + dd for a, b, c, dd in
                        zip(v11, v10, v01, v00)], cl0))

        def avg_two(d1, d2):
            # average of two paired contrasts, aligned on same clusters
            g1 = _cluster_groups(d1)
            g2 = _cluster_groups(d2)
            keys = sorted(g1)
            merged = []
            for k in keys:
                for a, b in zip(g1[k], g2[k]):
                    merged.append(((a + b) / 2.0, k))
            return merged

        dA = avg_two(d10_00, d11_01)
        dB = avg_two(d01_00, d11_10)

        effects = {name: {e: boot(d, e) for e in ('issue', 'cell')}
                   for name, d in (('dA_assistance', dA),
                                   ('dB_salience', dB),
                                   ('dAB_interaction', dAB))}

        fam = _error_families([vec[c][2] for c in CONDS])
        out['models'][m] = {'per_condition': per_cond, 'effects': effects,
                            'error_families': fam}

    # cross-validate against the shipped X analysis
    shipped = json.loads((XRUNS /
                          'eal_v21x_live_analysis.json').read_text(
        encoding='utf-8'))
    diffs = _cross_validate(out, shipped)
    out['cross_validation'] = {
        'against': 'eal_v21x_live_analysis.json',
        'exact_match_all': not diffs, 'mismatches': diffs[:50]}
    p = OUTDIR / 'grc_x_recompute.json'
    p.write_bytes((json.dumps(out, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n').encode('utf-8'))
    print('exact_match_all =', not diffs, '| mismatches:', len(diffs))
    for m in MODELS:
        for c in CONDS:
            i = out['models'][m]['per_condition'][c]['DA']['issue']
            print(f'{m:16s} {c} issue DA {i["point"]} '
                  f'[{i["ci_lo"]},{i["ci_hi"]}]')
    print('->', p)


def _confusion(cr):
    M = {p: {g: 0 for g in DECISIONS} for p in DECISIONS}
    bad = {'INVALID': 0, 'AMBIGUOUS': 0, 'API_ERROR': 0}
    for r in cr:
        p = r['parsed']
        if p in bad:
            bad[p] += 1
            continue
        M[p][r['cee_gold']] += 1
    return {'matrix': M, **bad}


def _error_families(cond_rows):
    fam = defaultdict(int)
    n = 0
    for cr in cond_rows:
        for r in cr:
            if not r['parseable']:
                continue
            n += 1
            p, g = r['parsed'], r['cee_gold']
            if p == 'ACCEPT' and g in ('REJECT', 'NEED_EVIDENCE'):
                fam['unsupported_acceptance'] += 1
            if p == 'REJECT' and g in ('ACCEPT', 'NEED_EVIDENCE'):
                fam['unsupported_rejection'] += 1
            if p == 'NEED_EVIDENCE' and g in ('ACCEPT', 'REJECT'):
                fam['over_abstention'] += 1
    return {k: {'count': fam[k], 'rate': round(fam[k] / n, 4)}
            for k in ('unsupported_acceptance', 'unsupported_rejection',
                      'over_abstention')}


def _cross_validate(mine, shipped):
    diffs = []
    for m in MODELS:
        sm = shipped['models'][m]
        mm = mine['models'][m]
        for c in CONDS:
            for e in ('issue', 'cell'):
                a = mm['per_condition'][c]['DA'][e]
                b = sm['per_condition'][c]['DA'][e]
                for k in ('point', 'ci_lo', 'ci_hi'):
                    if a[k] != b[k]:
                        diffs.append(f'{m} {c} DA.{e}.{k} {a[k]}!={b[k]}')
            if mm['per_condition'][c]['confusion']['matrix'] != \
                    sm['per_condition'][c]['confusion_3x3']['matrix']:
                diffs.append(f'{m} {c} confusion mismatch')
        name_map = {'dA_assistance': 'dA_assistance',
                    'dB_salience': 'dB_salience',
                    'dAB_interaction': 'dAB_interaction'}
        for nk, sk in name_map.items():
            for e in ('issue', 'cell'):
                a = mm['effects'][nk][e]
                b = sm['effects'][sk][e]
                for k in ('point', 'ci_lo', 'ci_hi'):
                    if a[k] != b[k]:
                        diffs.append(f'{m} {nk}.{e}.{k} {a[k]}!={b[k]}')
        if mm['error_families'] != {
                k: {'count': v['count'], 'rate': v['rate_per_parseable']}
                for k, v in sm['error_families'].items()}:
            diffs.append(f'{m} error_families mismatch')
    return diffs


if __name__ == '__main__':
    main()
