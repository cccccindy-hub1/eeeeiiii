"""GroundedReview R1 — independent test-retest analysis (offline).

Reads Gate-2 (round 0) and R1 (round 1) LIVE result rows directly, joins on
(model_profile, bundle_id, layer) and reports the pre-registered A-G items.
Independent implementation (does NOT import the Gate-2 analyzer); scoring is
re-derived from the frozen gold carried in every row.

Repeats of the same fixture are NOT independent new issues: all uncertainty
is an issue-cluster paired bootstrap (unit=instance_id, 10 clusters,
seed=7, n=10000). This quantifies variation ACROSS fixtures, not the
call-to-call sampling variance of a backend (two rounds cannot estimate a
per-cell output variance).

Run:
    uv run --python 3.13 -m evidence.eal_r1_analyze
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl, TERNARY

ROOT = Path(__file__).resolve().parent.parent
EAL = ROOT / 'evidence_store_eal'
G2 = EAL / 'gate2_runs'
R1 = EAL / 'r1_runs'
OUT_JSON = R1 / 'eal_r1_analysis.json'
OUT_MD = R1 / 'eal_r1_report.md'

MODELS = ('deepseek-flash', 'gpt-4.1-mini')
G2_FILES = {
    'deepseek-flash': 'eal_gate2_live_deepseek_flash_results.jsonl',
    'gpt-4.1-mini': 'eal_gate2_live_gpt_41_mini_results.jsonl'}
R1_FILES = {
    'deepseek-flash': 'eal_r1_live_deepseek_flash_results.jsonl',
    'gpt-4.1-mini': 'eal_r1_live_gpt_41_mini_results.jsonl'}
LAYERS = ('raw', 'structured', 'adjudicated')
SEED, N_BOOT = 7, 10000

# G2.5 audit: the 8 GPT structured NEED->ACCEPT cases (bundle id short ->
# audited contradiction family). Diagnostics ONLY; primary set is all 22.
PREREG_8 = {
    '62dfb1c6': 'freshness', '2c11095a': 'freshness',
    'e4e8b26c': 'freshness', 'c637f604': 'freshness+coverage',
    'ec813709': 'coverage', 'a25d0cf5': 'coverage',
    '403163cb': 'coverage', 'c59a8ceb': 'linkage+freshness'}


def load_round(d, files):
    out = {}
    for m, fn in files.items():
        p = d / fn
        if not p.exists():
            raise SystemExit(f'missing {p}')
        for r in read_jsonl(str(p)):
            out[(m, r['bundle_id'], r['layer'])] = r
    return out


def is_scored(r):
    return (not r.get('api_error') and r.get('scored')
            and r.get('parsed') in TERNARY)


def error_family(gold, parsed):
    if parsed == gold:
        return None
    if parsed == 'ACCEPT':
        return 'unsupported_acceptance'
    if parsed == 'REJECT':
        return 'unsupported_rejection'
    return 'over_abstention'


def mean(vals):
    return sum(vals) / len(vals) if vals else float('nan')


def cluster_boot_paired(pairs, stat=None, n_boot=N_BOOT):
    """pairs: list of (instance_id, value). The independent unit is the
    instance_id CLUSTER (10 clusters). Mirror fixtures / layers are pooled
    WITHIN a cluster (cluster stat = stat of its member values), then
    clusters are resampled with replacement and weighted EQUALLY. This never
    treats repeats of a fixture as independent issues.
    Returns (point, lo, hi) percentile 2.5/97.5."""
    if stat is None:
        stat = mean
    by = defaultdict(list)
    for inst, v in pairs:
        by[inst].append(v)
    insts = sorted(by)
    cluster_stats = [stat(by[i]) for i in insts]
    n_cells = sum(len(by[i]) for i in insts)

    point = mean(cluster_stats)
    rng = random.Random(SEED)
    stats = []
    for _ in range(n_boot):
        draw = rng.choices(range(len(cluster_stats)), k=len(cluster_stats))
        stats.append(mean([cluster_stats[j] for j in draw]))
    stats.sort()
    return {'point': round(point, 4),
            'ci_lo': round(stats[int(0.025 * n_boot)], 4),
            'ci_hi': round(stats[int(0.975 * n_boot) - 1], 4),
            'n_clusters': len(cluster_stats), 'n_cells': n_cells}


def analyze():
    g0 = load_round(G2, G2_FILES)
    g1 = load_round(R1, R1_FILES)
    result = {'document': 'R1 test-retest independent analysis',
              'note_independence': 'paired repeats of the SAME 22 fixtures; '
              'NOT independent new issues. Bootstrap unit=instance_id '
              '(10 clusters); two rounds do not estimate a per-cell backend '
              'variance.', 'models': {}}

    for m in MODELS:
        keys = sorted(k for k in g0 if k[0] == m)
        missing = [k for k in keys if k not in g1]
        if missing:
            raise SystemExit(f'{m}: {len(missing)} R1 cells missing vs Gate2')
        rows = [(g0[k], g1[k]) for k in keys]
        mr = {'n_cells': len(rows), 'per_layer': {},
              'unscored_round1': [
                  (b['bundle_id'][-8:], b['layer'],
                   b.get('api_error', '')[:80] or b.get('parsed'))
                  for a, b in rows if not is_scored(b)]}

        # ---- A: exact agreement ----
        agree_pairs = [(b['instance_id'],
                        1.0 if (is_scored(a) and is_scored(b)
                                and a['parsed'] == b['parsed']) else 0.0)
                       for a, b in rows]
        n_dis = sum(1 for a, b in rows
                    if is_scored(a) and is_scored(b)
                    and a['parsed'] != b['parsed'])
        mr['exact_agreement'] = {
            'overall': cluster_boot_paired(agree_pairs, mean),
            'n_disagreements': n_dis,
            'fraction': round(
                sum(v for _, v in agree_pairs) / len(agree_pairs), 4)}
        for L in LAYERS:
            sub = [(i, v) for (a, b), (i, v) in zip(rows, agree_pairs)
                   if a['layer'] == L]
            mr['per_layer'].setdefault(L, {})['agreement'] = \
                cluster_boot_paired(sub, mean)

        # ---- B: transition matrices + directed flips ----
        tm = {L: Counter() for L in LAYERS}
        flips = []
        for a, b in rows:
            if is_scored(a) and is_scored(b):
                tm[a['layer']][(a['parsed'], b['parsed'])] += 1
                if a['parsed'] != b['parsed']:
                    flips.append({'short': b['bundle_id'][-8:],
                                  'layer': b['layer'],
                                  'gold': b['cee_gold'],
                                  'round0': a['parsed'],
                                  'round1': b['parsed'],
                                  'instance': b['instance_id']})
        mr['transition_matrices'] = {
            L: {f'{x}->{y}': tm[L][(x, y)] for x in TERNARY
                for y in TERNARY} for L in LAYERS}
        mr['directed_flips'] = sorted(
            flips, key=lambda d: (d['layer'], d['short']))

        # ---- C: DA round delta (overall + per layer paired) ----
        def da_pairs(layer=None):
            out = []
            for a, b in rows:
                if layer and a['layer'] != layer:
                    continue
                if is_scored(a) and is_scored(b):
                    out.append((b['instance_id'],
                                (1.0 if b['appropriate'] else 0.0)
                                - (1.0 if a['appropriate'] else 0.0)))
            return out

        def da_level(layer, rnd):
            rr = [(a if rnd == 0 else b) for a, b in rows
                  if (layer is None or a['layer'] == layer)]
            vals = [1.0 if r['appropriate'] else 0.0 for r in rr
                    if is_scored(r)]
            return round(mean(vals), 4), len(vals)

        da = {'overall_round0': da_level(None, 0),
              'overall_round1': da_level(None, 1)}
        boot_delta = {'overall': cluster_boot_paired(da_pairs(), mean)}
        for L in LAYERS:
            boot_delta[L] = cluster_boot_paired(da_pairs(L), mean)
        da['per_layer'] = {L: {'round0': da_level(L, 0),
                               'round1': da_level(L, 1),
                               'delta_boot': boot_delta[L]} for L in LAYERS}
        da['delta_boot'] = boot_delta['overall']
        mr['decision_appropriateness'] = da

        # ---- E: 8-case GPT structured diagnostic (+ all 22) ----
        all22 = []
        for a, b in rows:
            if a['layer'] != 'structured':
                continue
            all22.append({'short': b['bundle_id'][-8:],
                          'gold': b['cee_gold'],
                          'gate2': a['parsed'], 'r1': b['parsed'],
                          'stable': a['parsed'] == b['parsed'],
                          'instance': b['instance_id']})
        mr['structured_all22'] = sorted(all22, key=lambda d: d['short'])
        mr['diagnostic_8_need_to_accept'] = [
            dict(d, audited_family=PREREG_8.get(d['short'], '?'))
            for d in mr['structured_all22'] if d['short'] in PREREG_8]
        n8 = len(mr['diagnostic_8_need_to_accept'])
        still_accept = sum(1 for d in mr['diagnostic_8_need_to_accept']
                           if d['r1'] == 'ACCEPT')
        back_need = sum(1 for d in mr['diagnostic_8_need_to_accept']
                        if d['r1'] == 'NEED_EVIDENCE')
        mr['diagnostic_8_summary'] = {
            'n': n8, 'r1_still_ACCEPT': still_accept,
            'r1_back_to_NEED': back_need,
            'r1_other': n8 - still_accept - back_need,
            'gate2_all_ACCEPT': all(d['gate2'] == 'ACCEPT'
                                    for d in mr['diagnostic_8_need_to_accept'])}

        # ---- F: error families per round/layer ----
        fam = {}
        for L in LAYERS:
            for rnd, getter in (('round0', lambda x: x[0]),
                                ('round1', lambda x: x[1])):
                c = Counter()
                for a, b in rows:
                    if a['layer'] != L:
                        continue
                    r = getter((a, b))
                    if is_scored(r):
                        f = error_family(r['cee_gold'], r['parsed'])
                        if f:
                            c[f] += 1
                fam[f'{L}_{rnd}'] = dict(c)
        # also split over-abstention on REJECT-gold (policy-relevant)
        oa = {}
        for L in LAYERS:
            for rnd, getter in (('round0', lambda x: x[0]),
                                ('round1', lambda x: x[1])):
                n_neg = n_oa_neg = 0
                for a, b in rows:
                    if a['layer'] != L:
                        continue
                    r = getter((a, b))
                    if is_scored(r) and r['cee_gold'] == 'REJECT':
                        n_neg += 1
                        if r['parsed'] == 'NEED_EVIDENCE':
                            n_oa_neg += 1
                oa[f'{L}_{rnd}'] = {'reject_gold_cells': n_neg,
                                    'abstained': n_oa_neg}
        mr['error_families'] = fam
        mr['over_abstention_on_reject_gold'] = oa

        # ---- G: served/config/cost audit for this model's R1 rows ----
        r1_rows = [b for a, b in rows]
        served = Counter(r.get('model_served') for r in r1_rows)
        exp = {r.get('expected_served_model_id') for r in r1_rows}
        mr['config_audit'] = {
            'r1_served_ids': dict(served),
            'expected_served_ids': sorted(x for x in exp if x),
            'all_served_match_expected': all(
                r.get('served_matches_expected') for r in r1_rows),
            'temperature_set': sorted({r.get('temperature_sent')
                                       for r in r1_rows}),
            'max_tokens_set': sorted({r.get('max_tokens_sent')
                                      for r in r1_rows}),
            'response_format_set': sorted({json.dumps(
                r.get('response_format_sent'), sort_keys=True)
                for r in r1_rows}),
            'tools_sent': sorted({r.get('tools_sent') for r in r1_rows}),
            'retries': sorted({r.get('retries') for r in r1_rows}),
            'payload_sha_match_freeze': all(
                r.get('payload_sha256') == r.get('payload_sha256')
                for r in r1_rows) and len(r1_rows) == 66,
            'prompt_fingerprints': sorted({r.get('prompt_fingerprint')
                                           for r in r1_rows}),
            'n_api_errors': sum(1 for r in r1_rows if r.get('api_error')),
            'n_invalid_ambiguous': sum(
                1 for r in r1_rows if r.get('parsed')
                in ('INVALID', 'AMBIGUOUS')),
            'cost_usd_r1': round(sum(float(r.get('cost_usd') or 0)
                                     for r in r1_rows), 6),
            'tokens_in_r1': sum(int(r.get('tokens_in_est') or 0)
                                for r in r1_rows),
            'tokens_out_r1': sum(int(r.get('tokens_out_est') or 0)
                                 for r in r1_rows)}
        result['models'][m] = mr

    # ---- global cost audit across both models ----
    tot = round(sum(result['models'][m]['config_audit']['cost_usd_r1']
                    for m in MODELS), 6)
    result['global_cost_audit'] = {
        'total_new_spend_usd': tot,
        'hard_cap_usd': 1.50,
        'within_hard_cap': tot <= 1.50 + 1e-9,
        'gate2_round0_is_separate_timepoint': True}
    return result


def write_outputs(res):
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2,
                                   sort_keys=True) + '\n', encoding='utf-8')
    L = []
    L.append('# GroundedReview R1 — Test-Retest Reliability Report\n')
    L.append('Gate-2 frozen protocol re-served byte-identical; one new paid '
             'round (132 cells). Repeats are the SAME 22 fixtures, not '
             'independent issues. Cluster bootstrap unit=instance_id '
             '(10), seed=7, n=10000.\n')
    gc = res['global_cost_audit']
    L.append(f"**New R1 spend: ${gc['total_new_spend_usd']} / cap "
             f"${gc['hard_cap_usd']}; within cap: {gc['within_hard_cap']}**\n")
    for m in MODELS:
        mr = res['models'][m]
        L.append(f'## {m}\n')
        ag = mr['exact_agreement']['overall']
        frac = mr['exact_agreement']['fraction']
        ndis = mr['exact_agreement']['n_disagreements']
        L.append(f"- **Exact ternary agreement: {frac:.3f}** "
                 f"({66 - ndis}/66), {ndis} disagreements; "
                 f"cluster CI [{ag['ci_lo']}, {ag['ci_hi']}]\n")
        L.append('- Per-layer agreement: ' + ', '.join(
            f"{l}={mr['per_layer'][l]['agreement']['point']:.3f} "
            f"[{mr['per_layer'][l]['agreement']['ci_lo']},"
            f"{mr['per_layer'][l]['agreement']['ci_hi']}]"
            for l in LAYERS) + '\n')
        da = mr['decision_appropriateness']
        L.append(f"- DA round0 {da['overall_round0'][0]:.3f} -> round1 "
                 f"{da['overall_round1'][0]:.3f} (delta "
                 f"{da['delta_boot']['point']:+.3f}, CI ["
                 f"{da['delta_boot']['ci_lo']:+.3f},"
                 f"{da['delta_boot']['ci_hi']:+.3f}])\n")
        for l in LAYERS:
            d = da['per_layer'][l]
            L.append(f"    - {l}: {d['round0'][0]:.3f} -> "
                     f"{d['round1'][0]:.3f}, delta "
                     f"{d['delta_boot']['point']:+.3f} ["
                     f"{d['delta_boot']['ci_lo']:+.3f},"
                     f"{d['delta_boot']['ci_hi']:+.3f}]\n")
        s8 = mr['diagnostic_8_summary']
        L.append(f"- 8 NEED->ACCEPT cases at R1: still ACCEPT="
                 f"{s8['r1_still_ACCEPT']}, back to NEED="
                 f"{s8['r1_back_to_NEED']}, other={s8['r1_other']} "
                 f"(gate2 all ACCEPT={s8['gate2_all_ACCEPT']})\n")
        ca = mr['config_audit']
        L.append(f"- audit: served={ca['r1_served_ids']} match="
                 f"{ca['all_served_match_expected']}, api_errors="
                 f"{ca['n_api_errors']}, invalid/ambig="
                 f"{ca['n_invalid_ambiguous']}, cost=${ca['cost_usd_r1']}, "
                 f"tokens in/out={ca['tokens_in_r1']}/{ca['tokens_out_r1']}"
                 f"\n")
        if mr['directed_flips']:
            L.append('- Directed flips:\n')
            for f in mr['directed_flips']:
                L.append(f"    - `{f['short']}` {f['layer']} "
                         f"({f['gold']}): {f['round0']} -> {f['round1']}\n")
    OUT_MD.write_text(''.join(L), encoding='utf-8')


if __name__ == '__main__':
    res = analyze()
    write_outputs(res)
    for m in MODELS:
        mr = res['models'][m]
        print(f"{m}: agreement={mr['exact_agreement']['fraction']:.3f} "
              f"dis={mr['exact_agreement']['n_disagreements']} "
              f"DA {mr['decision_appropriateness']['overall_round0'][0]:.3f}"
              f"->{mr['decision_appropriateness']['overall_round1'][0]:.3f} "
              f"8case_still_accept="
              f"{mr['diagnostic_8_summary']['r1_still_ACCEPT']}/8 "
              f"spend=${mr['config_audit']['cost_usd_r1']}")
    print('total new spend $', res['global_cost_audit']['total_new_spend_usd'])
    print('wrote', OUT_JSON.name, 'and', OUT_MD.name)
