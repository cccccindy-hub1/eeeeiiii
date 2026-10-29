"""GroundedReview — FROZEN shared statistics for EAL gates (Gate2 / R1 / X).

Single source of truth so no gate silently changes the estimand. Two
estimands are provided and ALWAYS labelled; a point estimate and its CI use
the SAME statistic.

Estimands
---------
CELL-WEIGHTED ('cell'):
    mean over every scored cell. Mirrors / layers with more cells get more
    weight. This is the statistic the Gate-2 analyzer bootstrapped (it
    resampled issue clusters but then POOLED all cells), so Gate-2 CIs are
    cell-weighted CIs whose resampling respects cluster dependence.

ISSUE-EQUAL-WEIGHTED ('issue') [PRIMARY from X onward]:
    within each instance_id cluster, average its member cells; then average
    the 10 cluster means with equal weight. Each independent issue counts
    once regardless of how many mirror fixtures/layers it contributes.

The bootstrap in BOTH cases resamples whole issue clusters (unit =
instance_id, 10 clusters, seed=7, n=10000) to preserve within-issue
dependence; the only difference is the statistic applied to the resampled
clusters. Repeats of a fixture across rounds/conditions are never treated as
independent new issues.
"""
from __future__ import annotations

import random
from collections import defaultdict

SEED = 7
N_BOOT = 10000
CLUSTER_KEY = 'instance_id'
N_ISSUES = 10

ESTIMANDS = ('cell', 'issue')
PRIMARY_ESTIMAND = 'issue'


def _groups(values, clusters):
    by = defaultdict(list)
    for v, c in zip(values, clusters):
        by[c].append(v)
    return by


def cell_weighted(values):
    return sum(values) / len(values) if values else float('nan')


def issue_equal(values, clusters):
    by = _groups(values, clusters)
    means = [sum(vs) / len(vs) for vs in by.values()]
    return sum(means) / len(means) if means else float('nan')


def point(values, clusters, estimand):
    if estimand == 'cell':
        return cell_weighted(values)
    if estimand == 'issue':
        return issue_equal(values, clusters)
    raise ValueError(estimand)


def cluster_bootstrap(values, clusters, estimand, *, n_boot=N_BOOT,
                      seed=SEED):
    """Resample whole issue clusters; recompute the SAME labelled statistic.
    Returns point + percentile 2.5/97.5 CI + counts."""
    by = _groups(values, clusters)
    keys = sorted(by)
    n_clusters = len(keys)
    n_cells = sum(len(by[k]) for k in keys)
    if n_clusters <= 1 or not values:
        return {'estimand': estimand,
                'point': round(point(values, clusters, estimand), 4),
                'ci_lo': None, 'ci_hi': None,
                'n_clusters': n_clusters, 'n_cells': n_cells}

    def stat_on(draw_keys):
        if estimand == 'cell':
            flat = [v for k in draw_keys for v in by[k]]
            return sum(flat) / len(flat)
        cmeans = [sum(by[k]) / len(by[k]) for k in draw_keys]
        return sum(cmeans) / len(cmeans)

    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        draw = [keys[rng.randrange(n_clusters)] for _ in keys]
        stats.append(stat_on(draw))
    stats.sort()
    return {'estimand': estimand,
            'point': round(point(values, clusters, estimand), 4),
            'ci_lo': round(stats[int(.025 * n_boot)], 4),
            'ci_hi': round(stats[int(.975 * n_boot) - 1], 4),
            'n_clusters': n_clusters, 'n_cells': n_cells}


def paired_deltas(base, other):
    """Per-cell paired difference other-base on matched index lists. Caller
    supplies aligned (value, cluster) sequences for the SAME fixtures."""
    return [o - b for b, o in zip(base, other)]


def both_estimands(values, clusters, **kw):
    return {e: cluster_bootstrap(values, clusters, e, **kw)
            for e in ESTIMANDS}
