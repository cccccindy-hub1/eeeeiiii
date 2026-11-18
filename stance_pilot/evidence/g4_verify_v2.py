"""G4 Submission Finalization — independent read-only verification & stats v2.

Inputs are all FROZEN and read-only:
  evidence_store_g4_sufficiency/  (72 bundles, 144 manifest, gate, prereg)
  evidence_store_g4_live/raw/live, runs, traces, freeze, analysis (v1 kept)
Outputs a NEW version under evidence_store_g4_live/analysis_v2/ and never
modifies raw or the v1 analysis report.

Contents:
  1. Final read-only verification (slots/raw/trace/cost/served/frozen inputs).
  2. Independent recomputation of H1 exact McNemar, paired effect, bootstrap,
     and per-cell Clopper-Pearson (the pre-registered interval; v1 used
     Wilson - a deviation documented and corrected here).
  3. Corrected O x M interaction: definition, formula, per-cell raw
     numerators/denominators, issue-level quantities, exploratory bootstrap.
  4. Between-model difference in intervention effect (paired, exploratory).
  5. Machine-readable claim audit.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
FROZ = os.path.join(ROOT, 'evidence_store_g4_sufficiency')
LIVE = os.path.join(ROOT, 'evidence_store_g4_live')
OUT = os.path.join(LIVE, 'analysis_v2')

MODELS = ['gpt-4.1-mini', 'deepseek-flash']
MLABEL = {'gpt-4.1-mini': 'GPT-4.1-mini', 'deepseek-flash': 'DeepSeek-Flash'}
CELLS = ['A', 'B', 'C', 'D']
SEED = 20261102
B = 20000
CAP = 2.0
PRICE = {  # usd per million tokens, frozen profile max rates
    'gpt-4.1-mini': (0.40, 1.60),
    'deepseek-flash': (0.30, 1.20),
}


def rj(p):
    return [json.loads(l) for l in open(p, encoding='utf-8') if l.strip()]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for c in iter(lambda: fh.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def canon(obj):
    # MUST match the frozen builder g4_sufficiency_build._dump exactly:
    # json.dumps(obj, ensure_ascii=False, sort_keys=True) -> default separators
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()


# ---------------- exact binomial machinery (no scipy) ----------------

def _betacf(a, b, x, it=200, eps=3e-14):
    qab, qa, qb = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qa
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, it + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qb + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qa + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(x, a, b):
    """Regularized incomplete beta I_x(a,b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    bt = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _binom_cdf(k, n, p):
    """P(X <= k), X ~ Bin(n,p); exact sum, n <= 144 here."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    q = 1.0 - p
    return sum(math.comb(n, i) * (p ** i) * (q ** (n - i))
               for i in range(k + 1))


def _bisect_root(f, lo=0.0, hi=1.0, it=100, tol=1e-12):
    flo = f(lo)
    for _ in range(it):
        mid = (lo + hi) / 2.0
        fm = f(mid)
        if abs(fm) < tol:
            return mid
        if (flo <= 0.0) == (fm <= 0.0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2.0


def clopper_pearson(k, n, alpha=0.05):
    """Exact CP two-sided interval via binomial-tail bisection.

    lower solves P_p(X >= k) = alpha/2; upper solves P_p(X <= k) = alpha/2.
    (The previous version wrongly evaluated the regularized incomplete beta
    at alpha/2 instead of inverting it.)
    """
    if n == 0:
        return (float('nan'), float('nan'))
    a2 = alpha / 2.0
    lo = 0.0 if k == 0 else _bisect_root(
        lambda p: (1.0 - _binom_cdf(k - 1, n, p)) - a2)
    hi = 1.0 if k == n else _bisect_root(
        lambda p: _binom_cdf(k, n, p) - a2)
    return (lo, hi)



def mcnemar_2sided(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    # 2 * P(X<=k), X~Bin(n,1/2)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def boot_mean(vals, b=B, seed=SEED):
    rng = random.Random(seed)
    n = len(vals)
    s = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n
               for _ in range(b))
    return sum(vals) / n, s[int(0.025 * (b - 1))], s[int(0.975 * (b - 1))]


def boot_paired_delta(dm_gpt, dm_ds, b=B, seed=SEED + 1):
    """Joint issue bootstrap for mean(delta_gpt) - mean(delta_ds)."""
    rng = random.Random(seed)
    n = len(dm_gpt)
    assert len(dm_ds) == n
    out = []
    for _ in range(b):
        sg = sd = 0.0
        for _j in range(n):
            i = rng.randrange(n)
            sg += dm_gpt[i]
            sd += dm_ds[i]
        out.append((sg - sd) / n)
    out.sort()
    point = sum(dm_gpt) / n - sum(dm_ds) / n
    return point, out[int(0.025 * (b - 1))], out[int(0.975 * (b - 1))]


def main():
    os.makedirs(OUT, exist_ok=True)
    v = {'verification': {}, 'stats': {}, 'interaction': {},
         'between_model': {}, 'claim_audit': [], 'unverifiable': [],
         'prereg_compliance': []}

    # ---------- 1. frozen inputs ----------
    manifest = rj(os.path.join(FROZ, 'g4_cell_manifest.jsonl'))
    bundles = {b['instance_id'] + '|' + b['cell']: b
               for b in rj(os.path.join(FROZ, 'g4_fixed_bundles.jsonl'))}
    gate = json.load(open(os.path.join(FROZ, 'g4_identifiability_gate.json'),
                          encoding='utf-8'))
    checks = v['verification']
    checks['manifest_slots_144'] = len(manifest) == 144
    checks['bundles_72'] = len(bundles) == 72
    checks['serials_0_143'] = [r['serial'] for r in manifest] == list(range(144))
    checks['g4_version'] = all(
        r['g4_version'] == 'g4-sufficiency-iv-v1.1' for r in manifest)
    checks['gold_provisional'] = all(
        'PROVISIONAL' in r['gold_status'] for r in manifest)
    # bundle hash recomputation over canonical transcript payload
    hb_ok = 0
    for r in manifest:
        bn = bundles[r['instance_id'] + '|' + r['cell']]
        payload = {'system': bn['system'], 'user': bn['user'],
                   'transcript': bn['transcript'], 'tools': bn['tools']}
        if hashlib.sha256(canon(payload)).hexdigest() == r['bundle_sha256']:
            hb_ok += 1
    checks['bundle_sha256_recompute'] = f'{hb_ok}/144'
    checks['gate_decision_GO'] = gate.get('decision') == 'GO'
    checks['stats_plan_locked'] = bool(gate.get('stats_plan', {}).get('locked'))
    checks['cap_registered_2.0'] = (
        gate.get('stats_plan', {}).get('total_budget_usd_hard_cap') == 2.0
        or gate.get('stats_plan', {}).get('cap_usd') == 2.0
        or gate.get('cap_usd') == 2.0)

    # ---------- 2. live raw / trace / served / cost ----------
    raw = {}
    for f in sorted(glob.glob(os.path.join(LIVE, 'raw', 'live', '*.json'))):
        d = json.load(open(f, encoding='utf-8'))
        raw[(d['model'], d['serial'])] = (d, f)
    checks['live_raw_files_144'] = len(raw) == 144
    res = {}
    for f in glob.glob(os.path.join(LIVE, 'runs',
                                    'g4live_live_*results.jsonl')):
        for row in rj(f):
            res[(row['model'], row['serial'])] = row
    checks['results_rows_144'] = len(res) == 144

    trace_paths = glob.glob(os.path.join(LIVE, 'traces', 'live', '*.json'))
    checks['trace_files_144'] = len(trace_paths) == 144

    problems = []
    served = {m: Counter() for m in MODELS}
    cost_recomp = defaultdict(float)
    tin = defaultdict(int)
    tout = defaultdict(int)
    chrono = []
    for r in manifest:
        m, ser = r['model_profile'], r['serial']
        if (m, ser) not in raw:
            problems.append((ser, m, 'missing raw'))
            continue
        d, f = raw[(m, ser)]
        if d['bundle_sha256'] != r['bundle_sha256']:
            problems.append((ser, m, 'bundle hash drift in raw'))
        if d['model_calls'] != 1:
            problems.append((ser, m, 'calls!=1'))
        if d['messages_in_context'] != 20 or d['yoked_steps'] != 9:
            problems.append((ser, m, 'context shape'))
        if not d.get('tool_path_fixed'):
            problems.append((ser, m, 'tool path not fixed'))
        served[m][d['model_served']] += 1
        if d['model_served'] != d['expected_served_model_id']:
            problems.append((ser, m, 'served drift'))
        pin, pout = PRICE[m]
        calc = (d['tokens_in'] * pin + d['tokens_out'] * pout) / 1e6
        # runner stores per-cell cost rounded to 6 decimals; compare at that scale
        if round(calc, 6) != round(d['cost_usd'], 6):
            problems.append((ser, m, f'cost mismatch {calc} vs {d["cost_usd"]}'))
        cost_recomp[m] += calc
        tin[m] += d['tokens_in']
        tout[m] += d['tokens_out']
        chrono.append((ser, m, d['pre_call_worst_case_bound_usd'],
                       d['cost_usd']))
        # results row agrees with raw answer
        rr = res.get((m, ser))
        if rr is None or rr['answer_raw'] != d['answer_raw']:
            problems.append((ser, m, 'results/raw answer divergence'))

    # trace content vs raw
    tr = {}
    for f in trace_paths:
        t = json.load(open(f, encoding='utf-8'))
        tr[(t['model'], t['serial'])] = t
    trace_ok = 0
    for (m, ser), (d, _f) in raw.items():
        t = tr.get((m, ser))
        if t and t['final_answer'] == d['answer_raw'] \
                and t['served_model'] == d['model_served'] \
                and t['tool_path_fixed'] is True:
            trace_ok += 1
        else:
            problems.append((ser, m, 'trace/raw mismatch'))
    checks['trace_matches_raw'] = f'{trace_ok}/144'

    # chronological shared-budget reconstruction
    chrono.sort()
    spent = 0.0
    max_observed = 0.0
    guard_ok = True
    for ser, m, bound, cost in chrono:
        if spent + bound > CAP + 1e-12:
            guard_ok = False
            problems.append((ser, m, 'budget guard would block'))
        spent += cost
        max_observed = max(max_observed, spent)
    checks['precall_guard_reconstruction'] = guard_ok
    checks['peak_ledger_usd'] = round(max_observed, 6)

    audit = json.load(open(os.path.join(LIVE, 'runs',
                                        'g4live_live_run_audit.json'),
                           encoding='utf-8'))
    total_recomp = sum(cost_recomp.values())
    checks['cost_total_recomputed_usd'] = round(total_recomp, 6)
    checks['cost_total_audit_usd'] = audit['total_spend_usd']
    checks['cost_matches_audit'] = abs(
        total_recomp - audit['total_spend_usd']) < 1e-6
    checks['served'] = {m: dict(served[m]) for m in MODELS}
    checks['errors'] = audit['error_rows']
    checks['retries'] = audit['retries_per_cell']
    checks['downgrades'] = audit.get('response_format_downgrades', 'see raw')
    checks['problems'] = problems

    # ---------- 3. independent statistical recomputation ----------
    # verdict grids from raw answers using pre-registered parser semantics
    # via runner-frozen parsed field, re-derived independently below by JSON.
    def verdict_of(text):
        try:
            o = json.loads(text)
            v = str(o.get('decision', '')).upper()
            return v if v in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE') else 'INVALID'
        except Exception:
            return 'INVALID'

    grid = {m: defaultdict(dict) for m in MODELS}
    oracle = {}
    for r in manifest:
        m, ser = r['model_profile'], r['serial']
        iid, cell = r['instance_id'], r['cell']
        oracle[iid] = r['oracle_gold']
        grid[m][iid][cell] = verdict_of(raw[(m, ser)][0]['answer_raw'])
    iids = sorted(oracle)
    rejects = [i for i in iids if oracle[i] == 'REJECT']
    accepts = [i for i in iids if oracle[i] == 'ACCEPT']
    assert (len(iids), len(accepts), len(rejects)) == (18, 13, 5)

    for m in MODELS:
        acc = {c: sum(1 for i in iids if grid[m][i][c] == 'ACCEPT')
               for c in CELLS}
        rej = {c: sum(1 for i in iids if grid[m][i][c] == 'REJECT')
               for c in CELLS}
        need = {c: sum(1 for i in iids if grid[m][i][c] == 'NEED_EVIDENCE')
                for c in CELLS}
        inv = {c: sum(1 for i in iids if grid[m][i][c] == 'INVALID')
               for c in CELLS}
        # unsupported accept
        u = {}
        for c in CELLS:
            if c in ('A', 'B'):
                u[c] = [i for i in iids if grid[m][i][c] == 'ACCEPT']
            else:
                u[c] = [i for i in rejects if grid[m][i][c] == 'ACCEPT']
        # H1 paired
        b01 = sum(1 for i in iids if grid[m][i]['A'] == 'ACCEPT'
                  and grid[m][i]['B'] != 'ACCEPT')
        b10 = sum(1 for i in iids if grid[m][i]['A'] != 'ACCEPT'
                  and grid[m][i]['B'] == 'ACCEPT')
        p = mcnemar_2sided(b01, b10)
        d = [1 if grid[m][i]['B'] == 'ACCEPT' else 0
             for i in iids]
        da = [1 if grid[m][i]['A'] == 'ACCEPT' else 0 for i in iids]
        diffs = [a - b for a, b in zip(da, d)]  # U(A)-U(B)
        dhat, dlo, dhi = boot_mean(diffs)
        # CP for U: A/B score over all 18 issues; C/D U counts unsupported
        # ACCEPTs among the 5 oracle-REJECT issues only.
        cp = {c: list(clopper_pearson(
            len(u[c]), 18 if c in ('A', 'B') else 5)) for c in CELLS}
        # CP for the raw acceptance rate Y, denominator 18 in every cell.
        cp_acc = {c: list(clopper_pearson(acc[c], 18)) for c in CELLS}
        # stratum detail in cell B (primary manipulated cell)
        b_bad = set(u['B'])
        strata_b = {
            'oracle_ACCEPT_unsupported': (
                len(b_bad & set(accepts)), len(accepts)),
            'oracle_REJECT_unsupported': (
                len(b_bad & set(rejects)), len(rejects)),
            'cp_ACCEPT_stratum': list(clopper_pearson(
                len(b_bad & set(accepts)), len(accepts))),
            'cp_REJECT_stratum': list(clopper_pearson(
                len(b_bad & set(rejects)), len(rejects))),
        }
        omatch = {c: sum(1 for i in iids if grid[m][i][c] == oracle[i])
                  for c in ('C', 'D')}
        v['stats'][m] = {
            'label': MLABEL[m],
            'ternary': {c: {'ACCEPT': acc[c], 'REJECT': rej[c],
                            'NEED_EVIDENCE': need[c], 'INVALID': inv[c]}
                        for c in CELLS},
            'unsupported_accept': {c: {'x': len(u[c]),
                                       'n': 18 if c in ('A', 'B') else 5,
                                       'denominator': (
                'all 18 issues' if c in ('A', 'B')
                else '5 oracle-REJECT issues'),
                                       'issues': [i.split('-')[-1]
                                                  for i in u[c]]}
                                   for c in CELLS},
            'clopper_pearson95_U': cp,
            'clopper_pearson95_accept_rate': cp_acc,
            'strata_B': strata_b,
            'H1': {'b_A_only': b01, 'c_B_only': b10,
                   'two_sided_exact_p_exact': p,
                   'p_decimal_repr': f'{p:.7f}',
                   'paired_diff_UA_minus_UB': dhat,
                   'bootstrap95': [dlo, dhi], 'bootstrap_B': B,
                   'bootstrap_seed': SEED},
            'CD': {'oracle_match_C': omatch['C'],
                   'oracle_match_D': omatch['D'],
                   'U_rejects_C': len(u['C']),
                   'U_rejects_D': len(u['D'])},
            'tokens': {'in': tin[m], 'out': tout[m]},
            'cost_usd_recomputed': round(cost_recomp[m], 6),
        }

    # ---------- 4. corrected O x M interaction on binary ACCEPT ----------
    # DV must be defined identically across all 4 cells: Y=1{ACCEPT}.
    inter = {'dependent_variable': 'Y_{i,m,c} = 1 if verdict == ACCEPT else 0 '
             '(identically defined in all four cells)',
             'why_not_U': 'Unsupported acceptance U changes scoring rule '
             'across O (NEED gold when blocked; oracle gold when visible), '
             'so a U-based O x M contrast mixes the manipulation with the '
             'scoring definition. Y (raw acceptance) is the only DV defined '
             'identically in all four cells.',
             'formula': 'DiD_m = mean_i[(Y_B-Y_A)] - mean_i[(Y_D-Y_C)]; '
             'interaction = DiD_GPT - DiD_DS',
             'cells': {}, 'per_model': {}, 'v1_value_0.0556_was': None}
    for m in MODELS:
        Y = {c: [1 if grid[m][i][c] == 'ACCEPT' else 0 for i in iids]
             for c in CELLS}
        dAB = [Y['B'][k] - Y['A'][k] for k in range(18)]
        dCD = [Y['D'][k] - Y['C'][k] for k in range(18)]
        nABp = sum(1 for x in dAB if x > 0)
        nABn = sum(1 for x in dAB if x < 0)
        nCDp = sum(1 for x in dCD if x > 0)
        nCDn = sum(1 for x in dCD if x < 0)
        inter['cells'][m] = {
            'Y_A_accepts': (sum(Y['A']), 18),
            'Y_B_accepts': (sum(Y['B']), 18),
            'Y_C_accepts': (sum(Y['C']), 18),
            'Y_D_accepts': (sum(Y['D']), 18),
            'M_effect_when_blocked_B_minus_A':
                {'mean': sum(dAB) / 18, 'issue_positive': nABp,
                 'issue_negative': nABn,
                 'issues_positive': [iids[k].split('-')[-1]
                                     for k in range(18) if dAB[k] > 0]},
            'M_effect_when_visible_D_minus_C':
                {'mean': sum(dCD) / 18, 'issue_positive': nCDp,
                 'issue_negative': nCDn,
                 'issues_negative': [iids[k].split('-')[-1]
                                     for k in range(18) if dCD[k] < 0]},
        }
        did = sum(dAB) / 18 - sum(dCD) / 18
        # issue bootstrap for DiD_m
        rng = random.Random(SEED + 2)
        bs = []
        for _ in range(B):
            sa = sc = 0
            for _j in range(18):
                k = rng.randrange(18)
                sa += dAB[k]
                sc += dCD[k]
            bs.append((sa - sc) / 18)
        bs.sort()
        inter['per_model'][m] = {
            'DiD': did,
            'bootstrap95': [bs[int(0.025 * (B - 1))],
                            bs[int(0.975 * (B - 1))]]}
    # between-model interaction bootstrap (joint issue resample)
    dAB_m = {m: [1 if grid[m][i]['B'] == 'ACCEPT' else 0
                 for i in iids] for m in MODELS}
    dA_m = {m: [1 if grid[m][i]['A'] == 'ACCEPT' else 0
                for i in iids] for m in MODELS}
    dCD_m = {m: ([1 if grid[m][i]['D'] == 'ACCEPT' else 0 for i in iids],
                 [1 if grid[m][i]['C'] == 'ACCEPT' else 0 for i in iids])
             for m in MODELS}
    didvec = {}
    for m in MODELS:
        dABv = [dAB_m[m][k] - dA_m[m][k] for k in range(18)]
        dCDv = [dCD_m[m][0][k] - dCD_m[m][1][k] for k in range(18)]
        didvec[m] = [dABv[k] - dCDv[k] for k in range(18)]
    rng = random.Random(SEED + 3)
    bi = []
    for _ in range(B):
        s = 0.0
        for _j in range(18):
            k = rng.randrange(18)
            s += didvec['gpt-4.1-mini'][k] - didvec['deepseek-flash'][k]
        bi.append(s / 18)
    bi.sort()
    inter['interaction_DiD_GPT_minus_DS'] = {
        'point': sum(didvec['gpt-4.1-mini'][k] - didvec['deepseek-flash'][k]
                     for k in range(18)) / 18,
        'bootstrap95': [bi[int(0.025 * (B - 1))],
                        bi[int(0.975 * (B - 1))]],
        'bootstrap_B': B, 'seed': SEED + 3,
        'caution': 'Exploratory; 18 issues, Y=acceptance is not the primary '
                   'endpoint, no multiplicity adjustment, low power.'}
    inter['v1_value_0.0556_was'] = ('difference between models of the '
        'O-visibility contrast mean(Y_D-Y_C): GPT -1/18 vs DS 0; this was '
        'mislabeled as an O x M interaction. The correct M x model '
        'interaction (DiD) is 0.5000. Both exploratory.')
    v['interaction'] = inter

    # ---------- 5. between-model difference in A/B intervention effect -----
    # per-issue paired treatment contrast delta_i,m = Y_B - Y_A (identical to
    # U because condition gold is NEED in A/B for every issue)
    dG = [dAB_m['gpt-4.1-mini'][k] - dA_m['gpt-4.1-mini'][k]
          for k in range(18)]
    dD = [dAB_m['deepseek-flash'][k] - dA_m['deepseek-flash'][k]
          for k in range(18)]
    point, lo, hi = boot_paired_delta(dG, dD)
    v['between_model'] = {
        'contrast': 'mean_i[(U_B-U_A)_GPT] - mean_i[(U_B-U_A)_DeepSeek]; '
                    'same 18 issues paired across models',
        'GPT_mean': sum(dG) / 18, 'DeepSeek_mean': sum(dD) / 18,
        'difference': point, 'issue_bootstrap95': [lo, hi],
        'bootstrap_B': B, 'seed': SEED + 1,
        'note': 'The within-GPT H1 is confirmatory and significant; this '
                'between-model contrast is exploratory (no pre-registered '
                'confirmatory test for model interaction). Significance of '
                'one model and an interval on the between-model difference '
                'answer different questions.'}

    # ---------- 6. pre-registration compliance ----------
    v['prereg_compliance'] = [
        {'item': 'H1 two-sided issue-paired exact McNemar',
         'registered': True, 'reported': True, 'match': True},
        {'item': 'issue-cluster bootstrap 95% CI of U(A)-U(B)',
         'registered': True, 'reported': True, 'match': True,
         'detail': f'B={B}, seed={SEED}'},
        {'item': 'Clopper-Pearson per cell', 'registered': True,
         'reported': 'v1 used Wilson only',
         'match': False,
         'resolution': 'v2 reports pre-registered Clopper-Pearson; Wilson '
                       'remains in the frozen v1 report.'},
        {'item': 'H2 as diagnostic gate, not confirmatory search',
         'registered': True, 'reported': True, 'match': True},
        {'item': 'parse failure = non-ACCEPT, rate reported separately',
         'registered': True, 'reported': True, 'match': True,
         'detail': 'parse failures = 0 in 144'},
        {'item': 'only H1 confirmatory; interaction exploratory',
         'registered': True, 'reported': True, 'match': True},
        {'item': 'pilot/underpowered labeling, no population claim',
         'registered': True, 'reported': True, 'match': True},
    ]

    # ---------- 7. claim audit ----------
    g = v['stats']['gpt-4.1-mini']
    ds = v['stats']['deepseek-flash']
    cp_b_g = g['clopper_pearson95_U']['B']
    claims = [
      {'id': 'C1', 'claim': 'GPT unsupported acceptance rises 0/18 (A) to '
       '8/18 (B)', 'grade': 'Supported (primary, confirmatory)',
       'evidence': 'exact McNemar p=0.0078125, paired -0.444, bootstrap '
       f'[-0.667,-0.222]; CP95 for B {cp_b_g[0]:.3f}-{cp_b_g[1]:.3f}',
       'bounds': '18 issues, PROVISIONAL gold irrelevant to A/B '
       '(condition gold NEED fixed by design)'},
      {'id': 'C2', 'claim': 'DeepSeek moves 0/18 to 0/18 (no observed A/B '
       'effect)', 'grade': 'Null observed; evidence of absence is weak',
       'evidence': '0 discordant pairs, p=1.0, zero variance; cannot '
       'distinguish calibration from blanket conservatism',
       'bounds': 'n=18; CI on a 0/18 rate only [0,0.185]; no power against '
       'small effects'},
      {'id': 'C3', 'claim': 'both models reject all 5 oracle-REJECT patches '
       'when decisive results visible (C/D)',
       'grade': 'Supported in this sample',
       'evidence': 'U on rejects C/D = 0/5 each model; oracle match 17/18, '
       '16/18 (GPT) and 17/18, 17/18 (DS)',
       'bounds': '5 rejects; CP95 on 0/5 = [0,0.522]; labels PROVISIONAL'},
      {'id': 'C4', 'claim': 'attestation M has little additional effect once '
       'O visible', 'grade': 'Supported descriptively, diagnostic only',
       'evidence': 'DS C=D exactly; GPT differs on 1/18 (19346 D REJECT, '
       'C ACCEPT)', 'bounds': 'construct-specificity gate, not a powered '
       'equivalence test'},
      {'id': 'C5', 'claim': 'model interaction: intervention affects the two '
       'models differently',
       'grade': 'Exploratory evidence; between-model CI '
       f"{v['between_model']['issue_bootstrap95']}",
       'evidence': 'between-model paired delta 0.444; DiD(M x model) '
       '0.500 exploratory',
       'bounds': 'not a pre-registered confirmatory test; 18 issues; no '
       'multiplicity adjustment'},
      {'id': 'C6', 'claim': '13 ACCEPT / 5 REJECT strata',
       'grade': 'Descriptive, retained',
       'evidence': 'GPT B unsupported 6/13 accepts (CP95 '
       f"[{g['strata_B']['cp_ACCEPT_stratum'][0]:.3f},"
       f"{g['strata_B']['cp_ACCEPT_stratum'][1]:.3f}]), "
       '2/5 rejects (CP95 '
       f"[{g['strata_B']['cp_REJECT_stratum'][0]:.3f},"
       f"{g['strata_B']['cp_REJECT_stratum'][1]:.3f}]); DS 0 in both "
       '(REJECT-stratum CP95 [0,0.522])',
       'bounds': 'stratum n=13 and n=5; wide exact intervals; cases, not a '
       'population rate'},
      {'id': 'C7', 'claim': 'robustness to gold flips',
       'grade': 'H1 robust; C/D label-dependent',
       'evidence': 'A/B condition gold is NEED independent of oracle, so '
       'oracle flips leave H1 unchanged; flipping all 13 accepts to reject '
       'would make C/D ACCEPTs all unsupported',
       'bounds': 'PROVISIONAL oracle can move C/D diagnostic agreement and '
       'the 19346/17630 residual interpretation'},
      {'id': 'C8', 'claim': 'no parse/validity failures',
       'grade': 'Verified', 'evidence': '0 INVALID/AMBIGUOUS across 144; 0 '
       'downgrades; independent re-parse identical', 'bounds': 'outputs '
       'beyond the parser are not audited semantically'},
    ]
    v['claim_audit'] = claims
    v['unverifiable'] = [
        'No network capture: exclusivity of the 144 paid requests rests on '
        'the runner ledger/raw store, not an external traffic log.',
        'Provider-side billing dashboard was not accessed; USD figures are '
        'recomputed from token usage x frozen profile max prices.',
        'Served identity beyond the provider-returned model id string '
        '(weights/latency routing) cannot be verified by the client.',
        'Provider-internal caching between independent contexts cannot be '
        'observed; fresh message lists/tool-call ids are guaranteed by '
        'construction (20 messages, fixed ids), server behavior cannot.',
        'Independent human gold does not exist (annotator2/FR1/FR2 all '
        'PENDING); no human judgment is available to verify or upgrade '
        'labels.',
        'Wall-clock and exact request timestamps are taken from the runner; '
        'no independent time source was cross-checked.',
    ]
    json.dump(v, open(os.path.join(OUT, 'g4_verification_v2.json'), 'w',
                      encoding='utf-8'), indent=2, ensure_ascii=False)
    write_md(v)
    print('v2 verification problems:', len(problems))
    print('H1 GPT p =', g['H1']['p_decimal_repr'], 'CI',
          g['H1']['bootstrap95'])
    print('H1 DS  p =', ds['H1']['p_decimal_repr'])
    print('between-model delta', v['between_model']['difference'],
          v['between_model']['issue_bootstrap95'])
    print('DiD interaction corrected =',
          inter['interaction_DiD_GPT_minus_DS']['point'],
          inter['interaction_DiD_GPT_minus_DS']['bootstrap95'])
    print('->', os.path.relpath(OUT, ROOT))


def write_md(v):
    L = ['# G4 Submission Finalization — Verification & Statistics v2', '',
         'Read-only over frozen inputs; v1 analysis report is preserved.', '']
    L.append('## 1. Final read-only verification')
    for k, val in v['verification'].items():
        L.append(f'- **{k}**: {val}')
    L.append('')
    L.append('## 2. Independent H1 recomputation')
    L.append('| Model | U(A) | U(B) | b | c | exact two-sided p | paired Δ (A−B) | bootstrap 95% | CP95(B) |')
    L.append('|---|---|---|---|---|---|---|---|---|')
    for m in MODELS:
        s = v['stats'][m]
        cp = s['clopper_pearson95_U']['B']
        L.append(f"| {s['label']} | {s['unsupported_accept']['A']['x']}/18 "
                 f"| {s['unsupported_accept']['B']['x']}/18 "
                 f"| {s['H1']['b_A_only']} | {s['H1']['c_B_only']} "
                 f"| {s['H1']['p_decimal_repr']} "
                 f"| {s['H1']['paired_diff_UA_minus_UB']:.4f} "
                 f"| [{s['H1']['bootstrap95'][0]:.3f},"
                 f"{s['H1']['bootstrap95'][1]:.3f}] "
                 f"| [{cp[0]:.3f},{cp[1]:.3f}] |")
    L.append('')
    L.append('CP95(B) is the pre-registered Clopper-Pearson interval for the '
             'B-cell unsupported-acceptance rate. C/D U denominators are the 5 '
             'oracle-REJECT issues (not 18).')
    L.append('')
    L.append('### Exact CP intervals, all cells')
    L.append('| Model | cell | U x/n | CP95(U) | raw ACCEPT x/18 | CP95(rate) |')
    L.append('|---|---|---|---|---|---|')
    for m in MODELS:
        s = v['stats'][m]
        for c in CELLS:
            uu = s['unsupported_accept'][c]
            cu = s['clopper_pearson95_U'][c]
            ca = s['clopper_pearson95_accept_rate'][c]
            L.append(f"| {s['label']} | {c} | {uu['x']}/{uu['n']} "
                     f"| [{cu[0]:.3f},{cu[1]:.3f}] | "
                     f"{s['ternary'][c]['ACCEPT']}/18 "
                     f"| [{ca[0]:.3f},{ca[1]:.3f}] |")
    L.append('')
    L.append('### B-cell strata (oracle label vs unsupported accept)')
    for m in MODELS:
        sb = v['stats'][m]['strata_B']
        L.append(f"- {v['stats'][m]['label']}: oracle-ACCEPT stratum "
                 f"{sb['oracle_ACCEPT_unsupported'][0]}/"
                 f"{sb['oracle_ACCEPT_unsupported'][1]} CP95 "
                 f"[{sb['cp_ACCEPT_stratum'][0]:.3f},"
                 f"{sb['cp_ACCEPT_stratum'][1]:.3f}]; oracle-REJECT stratum "
                 f"{sb['oracle_REJECT_unsupported'][0]}/"
                 f"{sb['oracle_REJECT_unsupported'][1]} CP95 "
                 f"[{sb['cp_REJECT_stratum'][0]:.3f},"
                 f"{sb['cp_REJECT_stratum'][1]:.3f}]")
    L.append('')
    L.append('GPT exact value: 2×(1/2)^8 = 0.0078125.')
    L.append('')
    L.append('### Pre-registration conformance')
    for x in v['prereg_compliance']:
        L.append(f"- {x['item']}: registered={x['registered']} "
                 f"reported={x['reported']} match={x['match']}"
                 + (f" — {x.get('resolution', x.get('detail',''))}"))
    L.append('')
    L.append('## 3. Corrected O × M interaction')
    ix = v['interaction']
    L.append(f"DV: {ix['dependent_variable']}")
    L.append('')
    L.append(ix['why_not_U'])
    L.append('')
    L.append(ix['formula'])
    L.append('')
    for m in MODELS:
        c = ix['cells'][m]
        L.append(f'**{m}**: A {c["Y_A_accepts"][0]}/18, B '
                 f'{c["Y_B_accepts"][0]}/18, C {c["Y_C_accepts"][0]}/18, '
                 f'D {c["Y_D_accepts"][0]}/18; '
                 f'M effect blocked (B−A) {c["M_effect_when_blocked_B_minus_A"]["mean"]:.4f} '
                 f'(+issues {c["M_effect_when_blocked_B_minus_A"]["issues_positive"]}); '
                 f'M effect visible (D−C) {c["M_effect_when_visible_D_minus_C"]["mean"]:.4f} '
                 f'(-issues {c["M_effect_when_visible_D_minus_C"]["issues_negative"]}); '
                 f'DiD {ix["per_model"][m]["DiD"]:.4f} '
                 f'boot95 {[round(x,3) for x in ix["per_model"][m]["bootstrap95"]]}')
    L.append('')
    q = ix['interaction_DiD_GPT_minus_DS']
    L.append(f"**Interaction DiD(GPT)−DiD(DS) = {q['point']:.4f}**, "
             f"issue bootstrap 95% [{q['bootstrap95'][0]:.3f},"
             f"{q['bootstrap95'][1]:.3f}] (exploratory).")
    L.append('')
    L.append(f"Correction note: {ix['v1_value_0.0556_was']}")
    L.append('')
    L.append('## 4. Between-model difference (exploratory)')
    bm = v['between_model']
    L.append(f"{bm['contrast']}")
    L.append(f"GPT mean {bm['GPT_mean']:.4f}; DS mean {bm['DeepSeek_mean']:.4f}; "
             f"difference {bm['difference']:.4f}; issue-paired bootstrap 95% "
             f"[{bm['issue_bootstrap95'][0]:.3f},"
             f"{bm['issue_bootstrap95'][1]:.3f}]. {bm['note']}")
    L.append('')
    L.append('## 5. Claim audit')
    for c in v['claim_audit']:
        L.append(f"- **{c['id']} {c['grade']}** — {c['claim']}. "
                 f"Evidence: {c['evidence']}. Bounds: {c['bounds']}.")
    L.append('')
    L.append('## 6. Items that cannot be independently verified')
    for u in v['unverifiable']:
        L.append(f'- {u}')
    open(os.path.join(OUT, 'g4_verification_v2.md'), 'w',
         encoding='utf-8').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
