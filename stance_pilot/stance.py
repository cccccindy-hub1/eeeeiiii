#!/usr/bin/env python3
"""Paired patch-level stance analysis. No filtering of the sample by outcome."""
import argparse, collections, json, math, random, sys
from pilot import read_jsonl, parse_decision

T, F = 'ACCEPT', 'REJECT'          # T = reviewer accepts, F = reviewer rejects
ARMS = ('neutral', 'positive', 'negative')

def arm_of(condition): return condition.split('_')[0]

def exact_mcnemar(b, c):
    """Two-sided exact McNemar (binomial) p-value for discordant counts b and c."""
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)

def bootstrap_ci(values, clusters, n_boot=10000, alpha=0.05, seed=0):
    """Cluster bootstrap over issues. values and clusters are aligned per patch."""
    rng = random.Random(seed)
    groups = collections.defaultdict(list)
    for v, c in zip(values, clusters): groups[c].append(v)
    keys = list(groups)
    if not keys: return (float('nan'), float('nan'))
    stats = []
    for _ in range(n_boot):
        sample = []
        for _ in range(len(keys)):
            sample.extend(groups[keys[rng.randrange(len(keys))]])
        stats.append(sum(sample) / len(sample))
    stats.sort()
    lo = stats[int(alpha / 2 * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)

def load(path):
    rows = {}
    errors = []
    for r in read_jsonl(path):
        if r.get('error'):
            errors.append(r); continue
        d = r.get('parsed') or parse_decision(r.get('answer', ''))
        rows[(r['id'], arm_of(r['condition']), r['repeat'])] = d
    return rows, errors

def collapse(rows, patch_ids):
    """Majority vote across repeats (ties -> None). R=1 keeps the single vote."""
    out = {}
    for pid in patch_ids:
        for arm in ARMS:
            votes = [rows.get((pid, arm, rep)) for rep in range(0, 100)
                     if (pid, arm, rep) in rows]
            valid = [v for v in votes if v in (T, F)]
            if not valid: out[(pid, arm)] = None; continue
            cnt = collections.Counter(valid)
            top = cnt.most_common()
            out[(pid, arm)] = None if len(top) > 1 and top[0][1] == top[1][1] else top[0][0]
    return out

def contrast(dec, patches, truth_of, a_arm, b_arm, gt, harmful_for_bad=True):
    """Return the paired 2x2 for patches of one ground-truth class."""
    cells = collections.Counter()
    per_patch = []
    for pid in patches:
        if truth_of[pid] != gt: continue
        a, b = dec[(pid, a_arm)], dec[(pid, b_arm)]
        if a is None or b is None:
            per_patch.append((pid, a, b, 'UNRESOLVED')); continue
        if gt == 'BAD':
            bad_a, bad_b = a == T, b == T                    # accepting a bad patch is an error
        else:
            bad_a, bad_b = a == F, b == F                    # rejecting a good patch is an error
        cells[(bad_a, bad_b)] += 1
        per_patch.append((pid, a, b, classify(gt, a, b)))
    return cells, per_patch

def classify(gt, a, b):
    """Sign of the stance-induced change, from the decision-quality perspective."""
    if a is None or b is None: return 'UNRESOLVED'
    correct_a = (a == T) if gt == 'GOOD' else (a == F)
    correct_b = (b == T) if gt == 'GOOD' else (b == F)
    if correct_a and not correct_b: return 'HARMFUL'
    if not correct_a and correct_b: return 'BENEFICIAL'
    return 'UNCHANGED'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='results_all.jsonl')
    ap.add_argument('--patches', default='conditions.jsonl', help='source of ground truth')
    ap.add_argument('--boot', type=int, default=10000)
    a = ap.parse_args()

    truth = {}
    for r in read_jsonl(a.patches):
        truth[r['id']] = ('GOOD' if r['resolved'] else 'BAD')
    patches = sorted(truth)
    rows, errors = load(a.input)
    print(f'patches={len(patches)} calls={len(rows)} errors={len(errors)}')
    if errors:
        print(f'  {len(errors)} errored calls excluded: e.g. {errors[0]["error"][:100]}')
    dec = collapse(rows, patches)
    missing = [k for k, v in dec.items() if v is None]
    if missing:
        print(f'  {len(missing)} patch-arm cells unresolved (invalid/ambiguous/missing)')

    print('\n== patch-level decision table ==')
    hdr = 'patch'.ljust(42) + 'GT   neutral  positive  negative   pos-vs-neu   neg-vs-neu'
    print(hdr)
    for pid in patches:
        d = [dec[(pid, arm)] for arm in ARMS]
        short = lambda x: '?' if x is None else x[0]
        n, p, g = d
        cls_p = classify(truth[pid], n, p) if n and p else '-'
        cls_g = classify(truth[pid], n, g) if n and g else '-'
        print(f'{pid[:41].ljust(42)}{truth[pid]:5s}'
              f'{short(n):^10s}{short(p):^10s}{short(g):^10s}'
              f'{cls_p:^13s}{cls_g:^12s}')

    report = {}
    for gt in ('BAD', 'GOOD'):
        print(f'\n== {"BAD" if gt=="BAD" else "GOOD"} patches ==')
        for b_arm in ('positive', 'negative'):
            cells, per_patch = contrast(dec, patches, truth, 'neutral', b_arm, gt)
            n11, n10, n01, n00 = cells[(True, True)], cells[(True, False)], cells[(False, True)], cells[(False, False)]
            # b = neutral error -> condition not error; c = neutral correct -> condition error
            b_cnt, c_cnt = n10, n01
            pval = exact_mcnemar(b_cnt, c_cnt)
            err_neu = (n11 + n10) / max(1, n11 + n10 + n01 + n00)
            err_arm = (n11 + n01) / max(1, n11 + n10 + n01 + n00)
            diffs = []
            for pid in patches:
                if truth[pid] != gt: continue
                x, y = dec[(pid, 'neutral')], dec[(pid, b_arm)]
                if x is None or y is None: continue
                ex = (x == T) if gt == 'BAD' else (x == F)
                ey = (y == T) if gt == 'BAD' else (y == F)
                diffs.append((int(ey) - int(ex), pid))
            vals = [d for d, _ in diffs]; clusters = [pid for _, pid in diffs]
            lo, hi = bootstrap_ci(vals, clusters, n_boot=a.boot)
            kinds = collections.Counter(x[3] for x in per_patch)
            label = 'err_accept' if gt == 'BAD' else 'err_reject'
            print(f'  neutral -> {b_arm:9s} n={n11+n10+n01+n00} '
                  f'{label}: neutral={err_neu:.3f} {b_arm}={err_arm:.3f} '
                  f'delta={err_arm-err_neu:+.3f} CI[{lo:+.3f},{hi:+.3f}]')
            print(f'    cells (neu_err, arm_err): {dict(cells)}   '
                  f'b={b_cnt} c={c_cnt} exact McNemar p={pval:.4f}')
            print(f'    classification: {dict(kinds)}')
            report[f'{gt}:neutral->{b_arm}'] = dict(delta=err_arm-err_neu, ci=(lo, hi), p=pval,
                                                     cells={str(k): v for k, v in cells.items()})
    print('\n== stance polarities, both ground-truth classes pooled ==')
    for b_arm in ('positive', 'negative'):
        kinds = collections.Counter()
        for pid in patches:
            n, y = dec[(pid, 'neutral')], dec[(pid, b_arm)]
            if n and y: kinds[classify(truth[pid], n, y)] += 1
        print(f'  neutral -> {b_arm:9s} {dict(kinds)}')
    print('\nNote: no outcome-based filtering. All patches enter every contrast.')
    json.dump(report, open('stance_report.json', 'w'), indent=2)
    print('wrote stance_report.json')

if __name__ == '__main__':
    main()
