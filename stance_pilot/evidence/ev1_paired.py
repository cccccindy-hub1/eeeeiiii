"""E1 paired cross-model metrics (External Validation, offline preparation).

Scores one or MORE model result files against the SAME frozen Wave-2.1 gold
(evidence.metrics_w2 dual-standard classifier is reused unchanged) and then
computes the paired cross-model comparison E1 is designed for:

  * every model sees the identical 22-fixture x 5-condition cell set, so the
    paired subset is the FULL 110 cells (paired difference is legitimate here;
    it would NOT be on unequal sets);
  * per-condition pre-registered metrics:
      - Oracle Decision Appropriateness + issue-cluster 95% CI
      - Condition Decision Appropriateness + issue-cluster 95% CI
      - Appropriate Abstention (gold NEED -> NEED), Over-Abstention
        (gold decisive/accept -> NEED), Unsupported Rejection
        (gold non-REJECT -> REJECT), false-commit-accept (gold NEED -> ACCEPT)
      - tool success: 200 / total tool calls, 403 strict_denied,
        400 missing_reason, escalation granted, cells with any 5xx
      - tokens, USD, USD per appropriate decision, INVALID/AMBIGUOUS rate
  * paired candidate-vs-baseline deltas on the shared cells, with an
    issue-cluster bootstrap CI over per-cell correctness differences
    (seed=7, n=10000) and an exact two-sided McNemar p (descriptive; the
    discordant count is small);
  * the Always-NEED sanity baseline on every block (Wave-2 convention).

Oracle and condition standards are ALWAYS reported separately and are never
averaged into one score. Offline; reads result files, performs no API calls.

Example (after a future approved run writes ev1_<profile>_results.jsonl):
  uv run --python 3.13 -m evidence.ev1_paired \
    --results deepseek-flash=evidence_store_w21/wave21_corrected_all110_results.jsonl \
    --results gpt-4.1-mini=evidence_store_ev1/ev1_openai_gpt41_mini_results.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from pilot import read_jsonl
from evidence.metrics2 import mcnemar_exact_p
from evidence.metrics_w2 import (
    ALL_CONDITIONS, CLUSTER_KEY, STATIC_CONDITIONS, classify_cell,
    load_w2_gold,
)
from evidence.ternary import TERNARY

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLD = ROOT / 'evidence_store_w21' / 'wave2_gold.jsonl'
DEFAULT_OUT = ROOT / 'evidence_store_ev1' / 'ev1_paired_metrics.json'
SEED = 7
N_BOOT = 10000


# ---------------------------------------------------------------------------
# Loading / classification (reuse the frozen metrics_w2 classifier)
# ---------------------------------------------------------------------------

def load_model_cells(spec, gold):
    """spec: 'name=path'. Returns (name, [classified cells])."""
    if '=' not in spec:
        raise SystemExit(f'--results must be name=path, got {spec!r}')
    name, path = spec.split('=', 1)
    rows = [r for r in read_jsonl(path)
            if not r.get('error') and not r.get('mock')]
    cells = []
    for r in rows:
        grow_k = (r.get('scenario'), r.get('id'),
                  r.get('served_artifact_id'))
        grow = gold['full'].get(grow_k) or gold['loose'].get(
            (r.get('scenario'), r.get('id')))
        if grow is None:
            raise SystemExit(
                f'{name}: no frozen gold row for {grow_k}')
        e = classify_cell(r, grow)
        e['cell_key'] = r.get('cell')
        cells.append(e)
    return name.strip(), cells


# ---------------------------------------------------------------------------
# Tool success accounting (from the frozen runner's tool_trace)
# ---------------------------------------------------------------------------

def tool_stats(rows_raw):
    n_calls = n_200 = n_403 = n_400 = n_5xx = 0
    cells_5xx = set()
    cells_granted = 0
    for r in rows_raw:
        if r.get('error') or r.get('mock'):
            continue
        granted = False
        for t in (r.get('tool_trace') or []):
            n_calls += 1
            st = t.get('http_status', 200)
            if st == 200:
                n_200 += 1
            elif st == 403:
                n_403 += 1
            elif st == 400:
                n_400 += 1
            elif st >= 500:
                n_5xx += 1
                cells_5xx.add(r.get('cell'))
        if r.get('escalation_granted'):
            cells_granted += 1
            granted = True
    return {
        'tool_calls_total': n_calls,
        'tool_calls_200': n_200,
        'tool_calls_403_strict_denied': n_403,
        'tool_calls_400_missing_reason': n_400,
        'tool_calls_5xx': n_5xx,
        'tool_success_rate_200_over_all_calls':
            round(n_200 / n_calls, 4) if n_calls else None,
        'cells_with_any_5xx': len(cells_5xx),
        'cells_with_escalation_granted': cells_granted,
        'note': '403 strict_denied and 400 missing_reason are CORRECT '
                'permission behaviour, not failures; 5xx/transport errors '
                'are operational failures.',
    }


# ---------------------------------------------------------------------------
# Per-condition pre-registered block
# ---------------------------------------------------------------------------

def _rate(num, den):
    return round(num / den, 4) if den else None


def _cluster_bootstrap(vals, clusters, n_boot=N_BOOT, seed=SEED):
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


def _confusion_rates(cells, standard):
    """Rates of the pre-registered H1/H2 failure mechanisms."""
    parseable = [e for e in cells if e['parseable']]
    n = len(cells)
    gold_need = [e for e in parseable
                 if e['standards'][standard]['gold'] == 'NEED_EVIDENCE']
    gold_decisive = [e for e in parseable
                     if e['standards'][standard]['gold']
                     in ('ACCEPT', 'REJECT')]
    gold_non_reject = [e for e in parseable
                       if e['standards'][standard]['gold']
                       in ('ACCEPT', 'NEED_EVIDENCE')]
    appropriate_abstain = sum(1 for e in gold_need if e['parsed'] == 'NEED_EVIDENCE')
    over_abstain = sum(1 for e in gold_decisive
                       if e['parsed'] == 'NEED_EVIDENCE')
    unsupported_reject = sum(1 for e in gold_non_reject
                             if e['parsed'] == 'REJECT')
    false_commit_accept = sum(1 for e in gold_need if e['parsed'] == 'ACCEPT')
    return {
        'n_gold_need_evidence': len(gold_need),
        'appropriate_abstention_rate':
            _rate(appropriate_abstain, len(gold_need)),
        'appropriate_abstention_cells': appropriate_abstain,
        'n_gold_decisive_or_accept': len(gold_decisive),
        'over_abstention_rate': _rate(over_abstain, len(gold_decisive)),
        'over_abstention_cells': over_abstain,
        'n_gold_non_reject': len(gold_non_reject),
        'unsupported_rejection_rate':
            _rate(unsupported_reject, len(gold_non_reject)),
        'unsupported_rejection_cells': unsupported_reject,
        'false_commit_accept_rate':
            _rate(false_commit_accept, len(gold_need)),
        'false_commit_accept_cells': false_commit_accept,
    }


def condition_block(cells, raw_by_cell, cond, standard):
    rows = [e for e in cells if e['condition'] == cond]
    parseable = [e for e in rows if e['parseable']]
    ok = [int(e['standards'][standard]['appropriate']) for e in parseable]
    ci = _cluster_bootstrap(ok, [e[CLUSTER_KEY] for e in parseable])
    n_ok = sum(ok)
    n_inv = sum(e['parsed'] == 'INVALID' for e in rows)
    n_amb = sum(e['parsed'] == 'AMBIGUOUS' for e in rows)
    usd = sum(e['cost_usd'] for e in rows)
    raw = [raw_by_cell[e['cell_key']]
           for e in rows if e['cell_key'] in raw_by_cell] \
        if raw_by_cell else []
    out = {
        'n_cells': len(rows),
        'n_parseable': len(parseable),
        'n_issues': len({e[CLUSTER_KEY] for e in rows}),
        'decision_appropriateness': {
            'rate': _rate(n_ok, len(parseable)),
            'n_correct': n_ok,
            'ci95_issue_cluster_seed7_n10000': ci['ci95'],
            'denominator': 'parseable cells (INVALID/AMBIGUOUS excluded)',
        },
        'protocol_failure': {
            'n_invalid': n_inv, 'n_ambiguous': n_amb,
            'invalid_or_ambiguous_rate_of_all_cells':
                _rate(n_inv + n_amb, len(rows)),
        },
        **_confusion_rates(rows, standard),
    }
    if raw:
        out['tool_success'] = tool_stats(raw)
        out['cost'] = {
            'tokens_in': sum(e['tokens_in'] for e in rows),
            'tokens_out': sum(e['tokens_out'] for e in rows),
            'usd_total': round(usd, 6),
            'usd_per_appropriate_decision':
                round(usd / n_ok, 6) if n_ok else None,
            'wall_s_total': round(sum(e['wall_s'] for e in rows), 2),
        }
    else:
        out['cost'] = {'usd_total': round(usd, 6),
                       'usd_per_appropriate_decision':
                           round(usd / n_ok, 6) if n_ok else None}
    return out


def always_need_block(cells, cond, standard):
    rows = [e for e in cells if e['condition'] == cond and e['parseable']]
    ok = sum(1 for e in rows
             if e['standards'][standard]['gold'] == 'NEED_EVIDENCE')
    return {'rate': _rate(ok, len(rows)), 'n_correct': ok,
            'n_parseable': len(rows)}


# ---------------------------------------------------------------------------
# Paired cross-model comparison
# ---------------------------------------------------------------------------

def paired_compare(base, cand, standard):
    """Join on the full frozen cell identity; both models ran all 110."""
    def idx(cells):
        return {(e['scenario'], e['id'], e['served_artifact_id'],
                 e['condition']): e for e in cells}
    ib, ic = idx(base), idx(cand)
    keys = sorted(set(ib) & set(ic))
    only_b = sorted(set(ib) - set(ic))
    only_c = sorted(set(ic) - set(ib))
    pairs = []
    deltas = []
    clusters = []
    b_only_correct = c_only_correct = 0
    for k in keys:
        eb, ec = ib[k], ic[k]
        cb = int(eb['standards'][standard]['appropriate'])
        cc = int(ec['standards'][standard]['appropriate'])
        d = cc - cb
        deltas.append(d)
        clusters.append(eb[CLUSTER_KEY])
        if cb and not cc:
            b_only_correct += 1
        if cc and not cb:
            c_only_correct += 1
        pairs.append({
            'scenario': k[0], 'id': k[1], 'served_artifact_id': k[2],
            'condition': k[3], 'instance_id': eb[CLUSTER_KEY],
            'baseline_correct': bool(cb), 'candidate_correct': bool(cc),
            'baseline_parsed': eb['parsed'], 'candidate_parsed': ec['parsed'],
            'gold': eb['standards'][standard]['gold'],
            'delta': d,
        })
    n = len(keys)
    acc_b = sum(p['baseline_correct'] for p in pairs) / n if n else None
    acc_c = sum(p['candidate_correct'] for p in pairs) / n if n else None
    bs = _cluster_bootstrap(deltas, clusters)
    return {
        'standard': standard,
        'shared_cells': n,
        'shared_issues': len(set(clusters)),
        'baseline_only_cells': len(only_b),
        'candidate_only_cells': len(only_c),
        'paired_set_complete': not only_b and not only_c,
        'baseline_rate': round(acc_b, 4) if acc_b is not None else None,
        'candidate_rate': round(acc_c, 4) if acc_c is not None else None,
        'paired_delta_candidate_minus_baseline':
            round(acc_c - acc_b, 4) if n else None,
        'delta_ci95_issue_cluster_seed7_n10000': bs['ci95'],
        'delta_ci_n_clusters': bs['n_clusters'],
        'candidate_correct_baseline_wrong': c_only_correct,
        'baseline_correct_candidate_wrong': b_only_correct,
        'mcnemar_exact_two_sided_p_descriptive':
            round(mcnemar_exact_p(b_only_correct, c_only_correct), 4),
        'mcnemar_note': 'exact test is descriptive only; discordant n is '
                        'small and clustering makes cells non-independent',
        'changed_pairs': [p for p in pairs if p['delta'] != 0],
    }


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', default=str(DEFAULT_GOLD))
    ap.add_argument('--results', action='append', default=[],
                    help='name=path; repeatable. The first is treated as '
                         'the frozen baseline; others as E1 candidates.')
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--bootstrap', type=int, default=N_BOOT)
    a = ap.parse_args()
    if len(a.results) < 1:
        raise SystemExit('at least one --results name=path is required')

    gold = load_w2_gold(a.gold)
    loaded = [load_model_cells(spec, gold) for spec in a.results]
    # raw rows needed for tool_trace accounting
    raw_maps = {}
    for spec in a.results:
        name, path = spec.split('=', 1)
        raw_maps[name.strip()] = {
            r.get('cell'): r for r in read_jsonl(path)
            if not r.get('error') and not r.get('mock')}

    base_name = loaded[0][0]
    per_model = {}
    for name, cells in loaded:
        by_cond = {}
        for cond in ALL_CONDITIONS:
            by_cond[cond] = {
                'oracle': condition_block(cells, raw_maps.get(name, {}),
                                          cond, 'oracle'),
                'condition': condition_block(cells, raw_maps.get(name, {}),
                                              cond, 'condition'),
                'always_need_baseline': {
                    'oracle': always_need_block(cells, cond, 'oracle'),
                    'condition': always_need_block(cells, cond, 'condition'),
                },
            }
        # pooled H1/H2/DA across all conditions (shared set, still clustered)
        pooled = {}
        for standard in ('oracle', 'condition'):
            parseable = [e for e in cells if e['parseable']]
            ok = [int(e['standards'][standard]['appropriate'])
                  for e in parseable]
            pooled[standard] = {
                'decision_appropriateness': {
                    'rate': _rate(sum(ok), len(ok)),
                    'n_correct': sum(ok), 'n_parseable': len(ok),
                    'ci95_issue_cluster_seed7_n10000':
                        _cluster_bootstrap(ok, [e[CLUSTER_KEY]
                                                for e in parseable])['ci95'],
                },
                **_confusion_rates(cells, standard),
            }
        per_model[name] = {
            'n_cells': len(cells),
            'n_issues': len({e[CLUSTER_KEY] for e in cells}),
            'conditions': by_cond,
            'pooled': pooled,
            'tool_success_all_active_cells':
                tool_stats(list(raw_maps.get(name, {}).values())),
        }

    comparisons = []
    for name, cells in loaded[1:]:
        base_cells = loaded[0][1]
        comparisons.append({
            'baseline': base_name, 'candidate': name,
            'oracle': paired_compare(base_cells, cells, 'oracle'),
            'condition': paired_compare(base_cells, cells, 'condition'),
            'per_condition': {
                cond: {
                    'oracle': paired_compare(
                        [e for e in base_cells if e['condition'] == cond],
                        [e for e in cells if e['condition'] == cond],
                        'oracle'),
                    'condition': paired_compare(
                        [e for e in base_cells if e['condition'] == cond],
                        [e for e in cells if e['condition'] == cond],
                        'condition'),
                } for cond in ALL_CONDITIONS},
        })

    out = {
        'metric': 'groundedreview_ev1_paired_cross_model',
        'gold_sha256': gold['sha256'],
        'gold_version': gold['version'],
        'bootstrap': {'unit': 'issue cluster (instance_id)',
                      'seed': SEED, 'n_boot': a.bootstrap},
        'standards_separation': 'oracle_gold and condition_gold are reported '
                                'separately everywhere; never averaged',
        'baseline_model': base_name,
        'models': per_model,
        'paired_comparisons': comparisons,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(f'baseline={base_name}')
    for name, blk in per_model.items():
        po, pc = blk['pooled']['oracle']['decision_appropriateness'], \
                 blk['pooled']['condition']['decision_appropriateness']
        print(f'{name}: cells={blk["n_cells"]} oracleDA={po["rate"]} '
              f'{po["ci95_issue_cluster_seed7_n10000"]} '
              f'conditionDA={pc["rate"]} '
              f'{pc["ci95_issue_cluster_seed7_n10000"]}')
    for cmp_ in comparisons:
        for std in ('oracle', 'condition'):
            p = cmp_[std]
            print(f'{cmp_["candidate"]} vs baseline [{std}] '
                  f'delta={p["paired_delta_candidate_minus_baseline"]} '
                  f'CI={p["delta_ci95_issue_cluster_seed7_n10000"]} '
                  f'mcnemar_p={p["mcnemar_exact_two_sided_p_descriptive"]} '
                  f'shared={p["shared_cells"]}')
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
