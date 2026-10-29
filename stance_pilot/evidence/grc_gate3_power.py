"""GroundedReview consolidation — Gate 3 offline power simulation ($0).

Estimates how many NEW independent issues a future Gate 3 would need for the
factorial contrasts, using ONLY the observed issue-level paired contrasts of
frozen Experiment X as the empirical dispersion. No fixtures are built and no
API is called.

Inputs : frozen X live results (88 cells/model) + v21 design (issue mapping).
Model  : for each effect, issue i contributes an issue-equal-weighted
         contrast d_i over its fixtures (mirror fixtures averaged within the
         issue, so an issue with more mirrors does not dominate). Observed
         mean delta and SD s are read from X. A future Gate 3 with n new
         issues is simulated as d_i ~ Normal(delta, s); power = fraction of
         10k simulated studies whose paired 95% percentile CI excludes zero
         (two-sided, matching the frozen bootstrap convention), across a grid
         of assumed true effects (the X point estimate plus hypotheticals),
         because the X estimate itself is too noisy to treat as truth.

Writes grc_gate3_power.json.
"""
from __future__ import annotations

import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
XRUNS = ROOT / 'evidence_store_eal' / 'v21x_runs'
DESIGN = ROOT / 'evidence_store_eal' / 'v21' / 'eal_v21_design_manifest.json'
OUT = ROOT / 'evidence_store_eal' / 'consolidation' / 'grc_gate3_power.json'

MODELS = (('deepseek-flash', 'deepseek_flash'), ('gpt-4.1-mini', 'gpt_41_mini'))
CONDS = ('a0b0', 'a1b0', 'a0b1', 'a1b1')
SIM_SEED = 20261026
N_SIM = 20000
GRID_N = (10, 15, 20, 30, 40, 60)
GRID_DELTA = (0.05, 0.10, 0.125, 0.15, 0.20)
# paired t critical (two-sided .05), df=n-1, for n in GRID_N
T_CRIT = {10: 2.262, 15: 2.145, 20: 2.093, 30: 2.045, 40: 2.023,
          60: 2.001}


def issue_vectors():
    man = json.loads(DESIGN.read_text(encoding='utf-8'))
    issue_of = {it['bundle_id'][-8:]: it['instance_id'] for it in man['items']}
    out = {}
    for model, sfx in MODELS:
        # issue -> condition -> list of correctness (mirrors kept, then equal-
        # weighted within issue so mirrors cannot dominate the issue)
        acc = defaultdict(lambda: defaultdict(list))
        for r in read_jsonl(str(XRUNS /
                                f'eal_v21x_live_{sfx}_results.jsonl')):
            if not r['parseable']:
                continue
            acc[issue_of[r['bundle_id'][-8:]]][r['condition']].append(
                1.0 if r['appropriate'] else 0.0)
        issues = sorted(acc)
        da = {c: [statistics.mean(acc[i][c]) for i in issues]
              for c in CONDS}

        def contrast(a, b):
            return [x - y for x, y in zip(da[a], da[b])]

        v00, v10, v01, v11 = (da[c] for c in CONDS)
        dA = [(x - y + z - w) / 2 for x, y, z, w in
              zip(v10, v00, v11, v01)]
        dB = [(x - y + z - w) / 2 for x, y, z, w in
              zip(v01, v00, v11, v10)]
        dAB = [a - b - c + d0 for a, b, c, d0 in zip(v11, v10, v01, v00)]
        out[model] = {'n_issues': len(issues),
                      'dA': {'observed_mean': round(statistics.mean(dA), 4),
                             'observed_sd': round(statistics.stdev(dA), 4)},
                      'dB': {'observed_mean': round(statistics.mean(dB), 4),
                             'observed_sd': round(statistics.stdev(dB), 4)},
                      'dAB': {'observed_mean': round(statistics.mean(dAB), 4),
                              'observed_sd': round(statistics.stdev(dAB), 4)}}
    return out


def power_for(delta, sd, n, rng):
    """Study-level Monte Carlo: per-study mean contrast ~ Normal(delta,
    sd/sqrt(n)); significant if the paired-t CI excludes zero. At n>=10 the
    percentile-bootstrap and t intervals nearly coincide for these data."""
    if sd == 0:
        return 1.0 if delta != 0 else 0.0
    se = sd / (n ** 0.5)
    crit = T_CRIT[n]
    hits = 0
    for _ in range(N_SIM):
        m = rng.gauss(delta, se)
        half = crit * se
        if m - half > 0 or m + half < 0:
            hits += 1
    return round(hits / N_SIM, 3)


def main():
    obs = issue_vectors()
    rng = random.Random(SIM_SEED)
    power = {}
    for model in obs:
        power[model] = {}
        for eff in ('dA', 'dB', 'dAB'):
            sd = obs[model][eff]['observed_sd']
            power[model][eff] = {
                'observed_sd': sd,
                'grid': {str(delta): {str(n): power_for(delta, sd, n, rng)
                                      for n in GRID_N}
                         for delta in GRID_DELTA}}

    # budget: X realized price per call across 176 calls
    cost_per_call = 0.392409 / 176
    budget = {}
    for n in GRID_N:
        calls_2model_4cond_1rep = n * 4 * 2
        budget[str(n)] = {
            'calls_per_model_4cond_k1': n * 4,
            'calls_both_models_k1': calls_2model_4cond_1rep,
            'usd_both_models_k1': round(calls_2model_4cond_1rep *
                                        cost_per_call, 2),
            'usd_both_models_k3_replicates':
                round(calls_2model_4cond_1rep * 3 * cost_per_call, 2)}

    result = {
        'document': 'Offline Gate 3 power simulation from frozen X issue-level '
                    'paired-contrast dispersion. No fixtures built, no API.',
        'method': {'n_sim': N_SIM, 'seed': SIM_SEED,
                   'significance_rule': 'paired-t two-sided .05 CI excludes 0 '
                                        '(approximates the frozen percentile '
                                        'issue-cluster bootstrap at n>=10)',
                   'issue_equal_within_issue': True,
                   'note': 'Normal(delta, observed_sd) parametric grid; '
                           'observed_sd already embeds temperature-0 single-'
                           'call noise and mirror averaging within issues.'},
        'observed_x_dispersion': obs,
        'power_grid': power,
        'cost_per_call_realized_x_usd': round(cost_per_call, 5),
        'budget_grid_usd': budget}
    OUT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())

    for model in obs:
        print('===', model)
        for eff in ('dA', 'dB', 'dAB'):
            print(eff, 'mean', obs[model][eff]['observed_mean'],
                  'sd', obs[model][eff]['observed_sd'])
            for delta in (0.10, 0.125, 0.15, 0.20):
                row = power[model][eff]['grid'][str(delta)]
                print('  delta', delta, {n: row[n] for n in
                      ('10', '20', '30', '40', '60')})
    print('cost/call $', round(cost_per_call, 5))
    print('budget k1', {n: budget[n]['usd_both_models_k1'] for n in
                        ('10', '20', '30', '40', '60')})
    print('->', OUT.name)


if __name__ == '__main__':
    main()
