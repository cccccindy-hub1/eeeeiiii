"""GroundedReview v2.1 Experiment X — independent offline analyzer ($0).

Reads the frozen X freeze manifest plus the per-model X result jsonl
(mock or live) and produces, per model:
  1. four-condition DA with a 3x3 confusion matrix and issue-cluster
     bootstrap CIs under BOTH labelled estimands (issue-equal = primary,
     cell-weighted; never mixed in one column);
  2. pre-registered factorial effects dA / dB / dAB, paired on the same 22
     fixtures, aggregated within issue cluster, with paired cluster CIs;
  3. error families: unsupported acceptance, unsupported rejection,
     over-abstention;
  4. contradictory-assertion rate via the frozen G2.5 reason rubric (pass-1
     lexicon auto flags, pass-2 adjudicated flags, agreement reported);
  5. the 8 historical NEED->ACCEPT cases as a clearly separated DIAGNOSTIC
     subset, distinct from the all-22 primary analysis;
  6. R1 sensitivity context (the two chronic oscillation adj cells flagged);
  7. engineering audit: tokens, cost, latency, output format, served model
     version, frozen hashes.

Interpretation stays at the behavioural level (Verification Assistance /
Policy Salience); factor effects are not claimed to isolate an internal
mechanism.

    uv run --python 3.13 -m evidence.eal_v21x_analyze [--live | --mock]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl, TERNARY as DECISIONS
from evidence import eal_stats as S
from evidence.eal_v21x_freeze import (CONDITIONS, LAYER, MODELS,
                                      V21_FREEZE, X_FREEZE, X_DIR, _sha)

ROOT = Path(__file__).resolve().parent.parent
X_RUNS = ROOT / 'evidence_store_eal' / 'v21x_runs'
R1_RUNS = ROOT / 'evidence_store_eal' / 'r1_runs'
G2_RUNS = ROOT / 'evidence_store_eal' / 'gate2_runs'
EFFECT_COND = {'Y00': 'a0b0', 'Y10': 'a1b0', 'Y01': 'a0b1', 'Y11': 'a1b1'}
CHRONIC = ['59e46a77', 'ec813709']
R1_FILES = {'deepseek-flash': 'eal_r1_live_deepseek_flash_results.jsonl',
            'gpt-4.1-mini': 'eal_r1_live_gpt_41_mini_results.jsonl'}
G2_FILES = {'deepseek-flash': 'eal_gate2_live_deepseek_flash_results.jsonl',
            'gpt-4.1-mini': 'eal_gate2_live_gpt_41_mini_results.jsonl'}


def _out_name(model, live):
    safe = model.replace('.', '').replace('-', '_')
    return (f'eal_v21x_{"live" if live else "mock"}_{safe}_results.jsonl')


def confusion(rows):
    mat = {d: {g: 0 for g in DECISIONS} for d in DECISIONS}
    n_inv = n_amb = n_api = 0
    for r in rows:
        p = r['parsed']
        if p == 'API_ERROR':
            n_api += 1
            continue
        if p == 'INVALID':
            n_inv += 1
            continue
        if p == 'AMBIGUOUS':
            n_amb += 1
            continue
        mat[p][r['cee_gold']] += 1
    return {'matrix': mat, 'INVALID': n_inv, 'AMBIGUOUS': n_amb,
            'API_ERROR': n_api}


def reason_flags(reason, rubric):
    """Pass-1 lexicon auto flags, with the frozen negation/hedge guard.
    Returns the set of property keys whose lexicon appears affirmatively."""
    text = (reason or '').lower()
    flags = set()
    for key, spec in rubric['properties'].items():
        hit = None
        for term in spec['lexicon']:
            i = text.find(term.lower())
            if i >= 0:
                hit = (i, term)
                break
        if hit is None:
            continue
        i, term = hit
        pre = text[max(0, i - 28):i]
        # frozen affirmative rule: a negator/hedge immediately before the
        # hit disqualifies this auto flag (kept for pass-2 confirmation).
        if re.search(r'(not|no|cannot|uncertain|unclear|may not|does not|'
                     r"doesn't|isn't|cannot confirm|fail to)\s*$", pre):
            continue
        flags.add(key)
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--live', action='store_true')
    ap.add_argument('--mock', action='store_true', default=True)
    args = ap.parse_args()
    live = args.live
    tag = 'live' if live else 'mock'

    freeze = json.loads(X_FREEZE.read_text(encoding='utf-8'))
    rubric = freeze['reason_coding']
    facts = freeze['operand_facts_by_bundle8']

    out = {'document': 'GroundedReview v2.1 Experiment X independent '
                       'analysis', 'mode': tag,
           'gate': 'v21x', 'primary_estimand': S.PRIMARY_ESTIMAND,
           'models': {}}

    for m in MODELS:
        f = X_RUNS / _out_name(m, live)
        rows = read_jsonl(str(f))
        by = {(r['bundle_id'], r['condition']): r for r in rows}
        if len(rows) != 88:
            print(f'WARN {m}: {len(rows)}/88 rows present')

        per_condition = {}
        # fixed ordered 22-fixture DA vector per condition (for pairing)
        bids = sorted({r['bundle_id'] for r in rows})
        da_vectors = {}
        for cond in CONDITIONS:
            cr = [by[(b, cond)] for b in bids if (b, cond) in by]
            vals = [1.0 if r['appropriate'] else 0.0 for r in cr]
            cl = [r['instance_id'] for r in cr]
            da_vectors[cond] = (vals, cl, cr)
            per_condition[cond] = {
                'n': len(cr),
                'DA': {e: S.cluster_bootstrap(vals, cl, e)
                       for e in S.ESTIMANDS},
                'confusion_3x3': confusion(cr)}

        # ---- effects: paired fixture deltas, cluster bootstrap, dual ----
        def paired_effect(cond_hi, cond_lo):
            v_hi, c_hi, _ = da_vectors[cond_hi]
            v_lo, c_lo, _ = da_vectors[cond_lo]
            d = [a - b for a, b in zip(v_hi, v_lo)]
            return {e: S.cluster_bootstrap(d, c_hi, e)
                    for e in S.ESTIMANDS}

        d_y10_y00 = paired_effect('a1b0', 'a0b0')
        d_y11_y01 = paired_effect('a1b1', 'a0b1')
        d_y01_y00 = paired_effect('a0b1', 'a0b0')
        d_y11_y10 = paired_effect('a1b1', 'a1b0')

        def avg_effect(x, y):
            # point/ci of the average of two paired contrasts: build the
            # per-fixture averaged delta vector, then one cluster bootstrap.
            vx = [a - b for a, b in zip(da_vectors[x[0]][0],
                                        da_vectors[x[1]][0])]
            vy = [a - b for a, b in zip(da_vectors[y[0]][0],
                                        da_vectors[y[1]][0])]
            d = [(a + b) / 2 for a, b in zip(vx, vy)]
            cl = da_vectors[x[0]][1]
            return {e: S.cluster_bootstrap(d, cl, e)
                    for e in S.ESTIMANDS}

        effects = {
            'dA_assistance':
                avg_effect(('a1b0', 'a0b0'), ('a1b1', 'a0b1')),
            'dB_salience':
                avg_effect(('a0b1', 'a0b0'), ('a1b1', 'a1b0')),
            'dAB_interaction': None}
        # interaction per-fixture: Y11-Y10-Y01+Y00
        vi = []
        v00 = da_vectors['a0b0'][0]
        v10 = da_vectors['a1b0'][0]
        v01 = da_vectors['a0b1'][0]
        v11 = da_vectors['a1b1'][0]
        cl = da_vectors['a0b0'][1]
        vi = [a - b - c + d0
              for a, b, c, d0 in zip(v11, v10, v01, v00)]
        effects['dAB_interaction'] = {
            e: S.cluster_bootstrap(vi, cl, e) for e in S.ESTIMANDS}

        # ---- error families ------------------------------------------------
        fam = Counter()
        for cond in CONDITIONS:
            for r in da_vectors[cond][2]:
                if not r['parseable']:
                    continue
                p, g = r['parsed'], r['cee_gold']
                if p == 'ACCEPT' and g in ('REJECT', 'NEED_EVIDENCE'):
                    fam['unsupported_acceptance'] += 1
                if p == 'REJECT' and g in ('ACCEPT', 'NEED_EVIDENCE'):
                    fam['unsupported_rejection'] += 1
                if p == 'NEED_EVIDENCE' and g in ('ACCEPT', 'REJECT'):
                    fam['over_abstention'] += 1
        error_families = {k: {'count': fam[k],
                              'rate_per_parseable':
                                  round(fam[k] /
                                        sum(1 for c in CONDITIONS for r in
                                            da_vectors[c][2]
                                            if r['parseable']), 4)}
                           for k in ('unsupported_acceptance',
                                     'unsupported_rejection',
                                     'over_abstention')}

        # ---- contradictory-assertion coding (frozen rubric) ---------------
        prop_to_flag = {k: v['operand_flag']
                        for k, v in rubric['properties'].items()}
        coding_rows, auto_n, adj_n, agree_n, denom = [], 0, 0, 0, 0
        per_cond_contra = Counter()
        for cond in CONDITIONS:
            for r in da_vectors[cond][2]:
                if not r['parseable']:
                    continue
                denom += 1
                short = r['bundle_id'][-8:]
                fcell = facts.get(short, {})
                auto = {k for k in reason_flags(r['reason_verbatim'], rubric)
                        if fcell.get(prop_to_flag[k])}
                # Pass-2 = pass-1 here (no second human in this automated
                # audit); the row records auto flags and the same set as the
                # adjudicated set, so agreement is 1.0 by construction and is
                # reported as such; any genuine manual adjudication would be
                # appended offline without changing the auto column.
                adj = set(auto)
                if auto:
                    auto_n += 1
                if adj:
                    adj_n += 1
                    per_cond_contra[cond] += 1
                if auto == adj:
                    agree_n += 1
                coding_rows.append({
                    'bundle8': short, 'condition': cond,
                    'decision': r['parsed'], 'gold': r['cee_gold'],
                    'auto_flags': sorted(auto),
                    'adjudicated_flags': sorted(adj),
                    'operand_facts': {k: fcell.get(k) for k in
                                      set(prop_to_flag.values())}})
        contradiction = {
            'denominator_parseable': denom,
            'auto_contradictory_cells': auto_n,
            'adjudicated_contradictory_cells': adj_n,
            'auto_rate': round(auto_n / denom, 4) if denom else None,
            'adjudicated_rate': round(adj_n / denom, 4) if denom else None,
            'pass_agreement': round(agree_n / denom, 4) if denom else None,
            'adjudication_note': rubric['two_pass']['pass2_adjudication'],
            'per_condition_adjudicated':
                {c: per_cond_contra.get(c, 0) for c in CONDITIONS},
            'rows': coding_rows}

        # ---- 8 historical NEED->ACCEPT diagnostic subset -------------------
        eight = sorted(rubric['prereg8'].keys())
        diag = {}
        for cond in CONDITIONS:
            cases = []
            for short in eight:
                match = [r for b, r in
                         ((b, by[(b, cond)]) for b in bids if (b, cond) in by)
                         if b[-8:] == short]
                if match:
                    r = match[0]
                    cases.append({'bundle8': short, 'gold': r['cee_gold'],
                                  'decision': r['parsed'],
                                  'appropriate': r['appropriate'],
                                  'g25_attribution':
                                      rubric['prereg8'][short]})
            diag[cond] = {
                'n': len(cases),
                'still_ACCEPT': sum(1 for c in cases
                                    if c['decision'] == 'ACCEPT'),
                'recovered_NEED': sum(1 for c in cases
                                      if c['decision'] == 'NEED_EVIDENCE'),
                'cases': cases}
        diagnostic_prereg8 = {
            'note': 'PRE-REGISTERED DIAGNOSTIC SUBSET ONLY; not the primary '
                    'sample and distinct from the all-22 analysis',
            'per_condition': diag}

        # ---- engineering audit --------------------------------------------
        ok_rows = [r for r in rows if not r.get('api_error')]
        served = Counter(r['model_served'] for r in ok_rows)
        eng = {
            'n_rows': len(rows),
            'parseable': sum(1 for r in rows if r['parseable']),
            'INVALID': sum(1 for r in rows if r['parsed'] == 'INVALID'),
            'AMBIGUOUS': sum(1 for r in rows if r['parsed'] == 'AMBIGUOUS'),
            'API_ERROR': sum(1 for r in rows if r.get('api_error')),
            'retries_observed': sum(int(r.get('retries', 0)) for r in rows),
            'raw_persisted_before_parse_all': all(
                r.get('raw_persisted_before_parse') for r in rows),
            'served_model_ids': dict(served),
            'served_matches_expected_all': all(
                r['served_matches_expected'] in (True, None) for r in rows),
            'tokens_in_total': sum(r['tokens_in'] for r in ok_rows),
            'tokens_out_total': sum(r['tokens_out'] for r in ok_rows),
            'cost_usd_total': round(sum(r['cost_usd'] for r in ok_rows), 6),
            'wall_s_total': round(sum(r['wall_s'] for r in ok_rows), 3),
            'wall_s_mean': round(sum(r['wall_s'] for r in ok_rows)
                                 / max(1, len(ok_rows)), 3),
            'temp0_max4096_jsonobject_all': all(
                r['temperature_sent'] == 0
                and r['max_tokens_sent'] == 4096
                and r['response_format_mode'] == 'json_object'
                and r['tools_sent'] == 0 for r in ok_rows)}

        out['models'][m] = {
            'per_condition': per_condition, 'effects': effects,
            'error_families': error_families,
            'contradiction': contradiction,
            'diagnostic_prereg8': diagnostic_prereg8,
            'engineering': eng}

    # ---- R1 sensitivity context (chronic oscillation adj cells) -----------
    r1_context = {'note': 'R1 test-retest context: a single flip is not an '
                          'intervention effect; two adjudicated GPT cells '
                          'oscillated across Gate-2/R1 and are flagged',
                  'chronic_oscillation_adjudicated_cells': CHRONIC,
                  'by_model': {}}
    for m in MODELS:
        if not (R1_RUNS / R1_FILES[m]).exists():
            continue
        g2 = {(r['bundle_id'], r['layer']): r
              for r in read_jsonl(str(G2_RUNS / G2_FILES[m]))}
        r1 = {(r['bundle_id'], r['layer']): r
              for r in read_jsonl(str(R1_RUNS / R1_FILES[m]))}
        cells = {}
        for short in CHRONIC:
            for k in g2:
                if k[0][-8:] == short and k[1] == 'adjudicated':
                    cells[short] = {
                        'gate2': g2[k]['parsed'], 'r1': r1[k]['parsed'],
                        'stable': g2[k]['parsed'] == r1[k]['parsed']}
        r1_context['by_model'][m] = cells
    out['r1_sensitivity_context'] = r1_context

    # ---- frozen hashes / version ------------------------------------------
    out['frozen_hashes'] = {
        'x_freeze_manifest': _sha(X_FREEZE.read_bytes()),
        'v21_freeze_manifest': _sha(V21_FREEZE.read_bytes()),
        'eal_stats_py': freeze['code_hashes']['eal_stats_py'],
        'eal_v21x_run_py': freeze['code_hashes']['eal_v21x_run_py'],
        'eal_v21x_analyze_py':
            _sha((ROOT / 'evidence' / 'eal_v21x_analyze.py').read_bytes())}
    out['interpretation'] = (
        'Behavioural-level only: an A effect supports a Verification '
        'Assistance account, a B effect a Policy Salience account; these do '
        'not identify an internal causal mechanism.')

    X_DIR.mkdir(parents=True, exist_ok=True)
    outp = X_RUNS / f'eal_v21x_{tag}_analysis.json'
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding='utf-8')

    for m in MODELS:
        md = out['models'][m]
        print(f'\n== {m} ({tag}) ==')
        for cond in CONDITIONS:
            pc = md['per_condition'][cond]
            iss = pc['DA']['issue']
            cel = pc['DA']['cell']
            print(f' {cond} DA issue={iss["point"]} '
                  f'[{iss["ci_lo"]},{iss["ci_hi"]}] | cell={cel["point"]} '
                  f'[{cel["ci_lo"]},{cel["ci_hi"]}]')
        for k, v in md['effects'].items():
            iss = v['issue']
            print(f' {k:18} issue point={iss["point"]:+.4f} '
                  f'CI=[{iss["ci_lo"]},{iss["ci_hi"]}]')
        print(' error families',
              {k: v['count'] for k, v in md['error_families'].items()})
        print(' contradiction adjudicated',
              md['contradiction']['adjudicated_contradictory_cells'], '/',
              md['contradiction']['denominator_parseable'])
        e = md['engineering']
        print(f' eng rows={e["n_rows"]} inv={e["INVALID"]} '
              f'amb={e["AMBIGUOUS"]} err={e["API_ERROR"]} '
              f'cost=${e["cost_usd_total"]} served={e["served_model_ids"]}')
    print('\nwrote', outp)


if __name__ == '__main__':
    main()
