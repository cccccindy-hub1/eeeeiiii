"""Gate 3-B.4 (task 2) — independent THIRD recomputation of the DeepSeek
sufficient-evidence paired change.

ZERO API. This is a deliberately independent implementation: it imports
neither g3b_analyze, g3b3_analyze nor g3b1_audit. It reads the two frozen
row sets directly, pairs by the frozen g3b_pair_cell_key discipline (same
instance_id + condition + model; only protocol version/run time differs),
and re-derives:

  * the full 10-issue x 3-sufficient-condition verdict transition matrix;
  * the pre-registered need-any endpoint (issue NEEDS in >=1 of T2A-T,
    T3D-Escalate, T3A-T) for G3-B vs G3-B.3;
  * paired reversals in BOTH directions;
  * exact integer-binomial Clopper-Pearson intervals (own bisection);
  * issue-cluster bootstrap intervals for each rate and the PAIRED
    difference (issues are the independent units; the ten cells of one
    issue are never resampled as independent rows);
  * a cross-check run with the g3b3 seed 313 alongside our own seed 417313.

All G3-B -> G3-B.3 figures remain ASSOCIATIONAL.

    uv run --python 3.13 -m evidence.g3b4_recompute
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter

from evidence import g3b4_common as C

SUF = C.SUFFICIENT_CONDITIONS
SHORT = {'sympy__sympy-13615': '13615', 'sympy__sympy-13974': '13974',
         'sympy__sympy-15349': '15349', 'sympy__sympy-17318': '17318',
         'sympy__sympy-17630': '17630', 'sympy__sympy-19783': '19783',
         'sympy__sympy-20590': '20590', 'sympy__sympy-21847': '21847',
         'sympy__sympy-24213': '24213', 'sympy__sympy-24443': '24443'}
ORDERED = [f'sympy__{i}' for i in C.ISSUES]


# --------------------------------------------------------------------------- #
# Independent exact Clopper-Pearson via integer binomial coefficients.
# --------------------------------------------------------------------------- #
def _binom_tail_ge(k, n, p):
    """P(X >= k), X ~ Bin(n,p), integer-combination terms."""
    if k <= 0:
        return 1.0
    return sum(math.comb(n, i) * p ** i * (1.0 - p) ** (n - i)
               for i in range(k, n + 1))


def _binom_cdf(k, n, p):
    """P(X <= k)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(math.comb(n, i) * p ** i * (1.0 - p) ** (n - i)
               for i in range(0, k + 1))


def cp_interval(k, n, alpha=0.05, iters=120):
    """Two-sided exact CP, independent bisection, rounded only at output."""
    if n == 0:
        return (None, None)
    lo = 0.0 if k == 0 else _solve(
        lambda p: _binom_tail_ge(k, n, p), alpha / 2, increasing=True,
        iters=iters)
    hi = 1.0 if k == n else _solve(
        lambda p: _binom_cdf(k, n, p), alpha / 2, increasing=False,
        iters=iters)
    return (round(lo, 4), round(hi, 4))


def _solve(f, target, *, increasing, iters):
    lo, hi = 0.0, 1.0
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        v = f(mid)
        if increasing:
            if v > target:
                hi = mid
            else:
                lo = mid
        else:
            if v > target:
                lo = mid
            else:
                hi = mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------- #
# Issue-cluster bootstrap; one issue draw resamples BOTH version readings so
# the paired difference uses matched resamples.
# --------------------------------------------------------------------------- #
def cluster_bootstrap_pairs(pairs, seed, B=10000):
    """pairs: list of (g3b_value, g3b3_value) per issue in fixed order.
    Returns percentile intervals for mean(b), mean(b3), mean(b-b3)."""
    n = len(pairs)
    rng = random.Random(seed)
    pb, p3, pd = [], [], []
    for _ in range(B):
        sb = s3 = 0
        for _ in range(n):
            b, x = pairs[rng.randrange(n)]
            sb += b
            s3 += x
        mb, m3 = sb / n, s3 / n
        pb.append(mb)
        p3.append(m3)
        pd.append(mb - m3)
    return {'B': B, 'seed': seed, 'n_clusters': n,
            'g3b_rate': _pct(pb), 'g3b3_rate': _pct(p3),
            'paired_diff_g3b_minus_g3b3': _pct(pd)}


def _pct(xs):
    xs = sorted(xs)
    B = len(xs)
    return {'point_2_5': xs[int(0.025 * B)],
            'point_97_5': xs[min(int(0.975 * B), B - 1)],
            'percentile_method': '2.5/97.5 of sorted bootstrap replicates'}


def main():
    # --- load frozen rows and pair by (instance, condition) ----------------
    g3b = C.read_jsonl(C.G3B_LIVE_DEEPSEEK)
    g3b3 = C.read_jsonl(C.G3B3_LIVE_DEEPSEEK)
    b3_by = {(r['instance_id'], r['condition']): r['parsed'] for r in g3b3}
    b_by = {(r['instance_id'], r['condition']): r['parsed'] for r in g3b}
    # The frozen pair anchor on every g3b3 row must resolve to a g3b cell.
    # Every G3-B.3 row must carry a pairing anchor that resolves to an actual
    # G3-B cell (same instance + condition; the g3b cell prefix is g3b:).
    anchors = [(r['cell'], r['g3b_pair_cell_key']) for r in g3b3]
    g3b_cellset = {f"g3b:{iid}:{cond}" for iid in ORDERED
                   for cond in C.CONDITIONS}
    assert len(anchors) == 50
    assert all(a in g3b_cellset for _, a in anchors), 'dangling pair anchor'
    assert len(b_by) == 50 and len(b3_by) == 50

    # --- full 10 x 3 transition matrices, one block per condition ----------
    per_condition = {}
    for cond in SUF:
        matrix = Counter()
        rows = []
        for iid in ORDERED:
            old, new = b_by[(iid, cond)], b3_by[(iid, cond)]
            matrix[(old, new)] += 1
            rows.append({'issue': SHORT[iid], 'g3b': old, 'g3b3': new,
                         'transition': f'{old} -> {new}'})
        per_condition[cond] = {
            'note': 'condition gold for all 7 accept-issue cells is ACCEPT '
                    'and for the 3 reject issues is REJECT; NEED_EVIDENCE is '
                    'the model abstaining under a SUFFICIENT regime',
            'transition_counts': {f'{o} -> {n}': matrix[(o, n)]
                                  for o in ('ACCEPT', 'REJECT',
                                            'NEED_EVIDENCE')
                                  for n in ('ACCEPT', 'REJECT',
                                            'NEED_EVIDENCE')
                                  if matrix[(o, n)]},
            'g3b_need_n': sum(v for (o, n), v in matrix.items()
                              if o == 'NEED_EVIDENCE'),
            'g3b3_need_n': sum(v for (o, n), v in matrix.items()
                               if n == 'NEED_EVIDENCE'),
            'need_to_nonneed_reversals':
                sum(v for (o, n), v in matrix.items()
                    if o == 'NEED_EVIDENCE' and n != 'NEED_EVIDENCE'),
            'nonneed_to_need_reversals':
                sum(v for (o, n), v in matrix.items()
                    if o != 'NEED_EVIDENCE' and n == 'NEED_EVIDENCE'),
            'per_issue': rows}

    # --- pre-registered need-any primary endpoint --------------------------
    pairs = []
    need_any_rows = []
    for iid in ORDERED:
        old_any = int(any(b_by[(iid, c)] == 'NEED_EVIDENCE' for c in SUF))
        new_any = int(any(b3_by[(iid, c)] == 'NEED_EVIDENCE' for c in SUF))
        pairs.append((old_any, new_any))
        olds = {c: b_by[(iid, c)] for c in SUF}
        news = {c: b3_by[(iid, c)] for c in SUF}
        need_any_rows.append(
            {'issue': SHORT[iid],
             'g3b_verdicts': olds, 'g3b3_verdicts': news,
             'g3b_need_any': bool(old_any),
             'g3b3_need_any': bool(new_any),
             'transition': f'{old_any} -> {new_any}'})
    old_n = sum(p[0] for p in pairs)
    new_n = sum(p[1] for p in pairs)
    n_to_y = sum(1 for o, n in pairs if o == 1 and n == 0)
    y_to_n = sum(1 for o, n in pairs if o == 0 and n == 1)
    point = {
        'endpoint': 'per-issue indicator: model returns NEED_EVIDENCE in at '
                    'least one of the three sufficient-evidence conditions '
                    '(T2A-T, T3D-Escalate, T3A-T)',
        'g3b_need_any_issues': f'{old_n}/10',
        'g3b3_need_any_issues': f'{new_n}/10',
        'rate_change': round(new_n / 10 - old_n / 10, 4),
        'reversals_need_to_nonneed': n_to_y,
        'reversals_nonneed_to_need': y_to_n,
        'the_single_residual_issue': [SHORT[ORDERED[i]] for i in range(10)
                                      if pairs[i] == (1, 1)],
        'issues_fixed_need_to_nonneed': [SHORT[ORDERED[i]] for i in range(10)
                                         if pairs[i] == (1, 0)]}

    # --- exact CP + two bootstrap seeds (ours + cross-check seed 313) -------
    intervals = {
        'g3b_need_any_rate_cp95': cp_interval(old_n, 10),
        'g3b3_need_any_rate_cp95': cp_interval(new_n, 10),
        'cp_method': 'exact integer-binomial Clopper-Pearson, independent '
                     'bisection (third implementation; no scipy/beta)',
        'issue_cluster_bootstrap_seed_417313':
            cluster_bootstrap_pairs(pairs, C.G3B4_BOOTSTRAP_SEED,
                                    C.G3B4_BOOTSTRAP_REPLICATES),
        'issue_cluster_bootstrap_crosscheck_seed_313':
            cluster_bootstrap_pairs(pairs, 313, 10000)}

    # --- exact McNemar-style paired discordance statement (descriptive) ----
    # With only 10 issue clusters and 8:0 discordance, report the exact
    # two-sided binomial sign p over discordant pairs for transparency; this
    # is descriptive (n clusters is tiny), not a population claim.
    d = n_to_y + y_to_n
    sign_p = (2 * sum(math.comb(d, i) for i in range(0, min(n_to_y, y_to_n)
                                                      + 1)) / 2 ** d
              if d else 1.0)
    sign_p = min(1.0, sign_p)

    out = {
        'document': 'Gate 3-B.4 independent third recomputation of the '
                    'DeepSeek sufficient-evidence paired change (task 2)',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'model': 'deepseek-flash',
        'pairing': 'same instance_id + condition; G3-B rows paired to '
                   'G3-B.3 rows via the frozen g3b_pair_cell_key; '
                   'cross-version, cross-run-time ASSOCIATIONAL only',
        'api_calls_made_by_this_audit': 0,
        'primary_endpoint_need_any': point,
        'exact_intervals': intervals,
        'descriptive_paired_discordance': {
            'discordant_pairs': d,
            'exact_two_sided_sign_p_on_discordants': round(sign_p, 5),
            'caution': 'only 10 independent issue clusters; treat as '
                       'descriptive, not a population-level test'},
        'per_sufficient_condition_transition': per_condition,
        'per_issue_need_any_detail': need_any_rows,
        'g3b3_residual_issue_condition_detail': _residual_detail(
            b_by, b3_by),
        'gold_authority': C.GOLD_AUTHORITY}

    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_deepseek_recompute.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('DeepSeek need-any: G3-B %d/10 -> G3-B.3 %d/10 (delta %.1f), '
          'reversals %d need->nonneed, %d nonneed->need'
          % (old_n, new_n, new_n / 10 - old_n / 10, n_to_y, y_to_n))
    print('residual issue:', point['the_single_residual_issue'])
    print('CP95 g3b:', intervals['g3b_need_any_rate_cp95'],
          ' g3b3:', intervals['g3b3_need_any_rate_cp95'])
    bs = intervals['issue_cluster_bootstrap_seed_417313']
    print('cluster boot paired-diff CI:',
          bs['paired_diff_g3b_minus_g3b3']['point_2_5'],
          bs['paired_diff_g3b_minus_g3b3']['point_97_5'])
    print('->', dest.relative_to(C.HERE))


def _residual_detail(b_by, b3_by):
    """Which sufficient condition keeps the single residual abstention."""
    out = {}
    for iid in ORDERED:
        if any(b3_by[(iid, c)] == 'NEED_EVIDENCE' for c in SUF):
            out[SHORT[iid]] = {
                'g3b3': {c: b3_by[(iid, c)] for c in SUF},
                'g3b': {c: b_by[(iid, c)] for c in SUF}}
    return out


if __name__ == '__main__':
    main()
