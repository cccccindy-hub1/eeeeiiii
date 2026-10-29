"""GroundedReview Gate 3-B.3 — Corrective Replication analysis (offline, $0).

INDEPENDENT analyzer: it does NOT import g3b_analyze. The exact-CI / issue-
cluster bootstrap machinery is reimplemented here (same Numerical Recipes /
beta-quantile math), with the pre-registered G3-B.3 seed 313 and B=10000.

Reads:
  * the 100 NEW real g3b3 live rows (evidence_store_g3b3/runs/*), and
  * the frozen G3-B live rows READ-ONLY (evidence_store_g3b/runs/*), paired to
    each g3b3 row STRICTLY by same instance_id + condition + model via the
    g3b3 row's `g3b_pair_cell_key` (== the g3b row's `cell`).

Pre-registered questions answered against PROVISIONAL single-annotator gold
ONLY (annotator2 NOT_OBTAINED; no kappa; never "human-adjudicated"):
  #10 DeepSeek NEED_EVIDENCE under the three SUFFICIENT regimes (issue x
      condition grid), and the strict paired G3-B -> G3-B.3 transition table.
  #11 GPT unsupported ACCEPTANCE on the 3 gold-REJECT issues over the FULL
      15-cell sample; sympy-17318/T2A called out, sympy-17630/T3A reported as
      the separately-tagged Decision-Policy probe (never pooled).
  #12 Correct-abstention / improper-commitment under the two RESTRICTED
      regimes, per model.
  #14 Gold sensitivity: all-10 / drop-3-REJECT / trust-grant counterfactual
      boundary.
  #15 Per-issue evidence package (rendered g3b2 prompt, tool responses, model
      reasoning) with a deterministic heuristic distinguishing evidence-
      utilization improvement from a pure policy/trust change vs remaining
      error; the raw evidence is bundled so a human can override the tag.

The G3-B -> G3-B.3 contrast is CROSS-VERSION / CROSS-RUN-TIME and therefore
ASSOCIATIONAL: the repair changed freshness handling AND T2A policy trust in
the same release, so their separate causal effects are NOT identified. A big
fall in DeepSeek NEED says the original C2 result was largely protocol-
induced (weakening the model-defect claim); persistent NEED under visible
sufficient outcomes is what would support a calibration defect. Nothing here
generalises a benchmark audit into a universal claim.

Offline:
    uv run --python 3.13 -m evidence.g3b3_analyze
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

from evidence.ternary import TERNARY, read_jsonl
from evidence import g3b2_prompts as GP
from evidence import g3b3_common as C
from evidence import g3b3_freeze as FZ

DS, GPT = 'deepseek-flash', 'gpt-4.1-mini'
BOOT_B = 10000
BOOT_SEED = 313
REJECT_SHORT = C.REJECT_ISSUES


# ---------------------------------------------------------------------------
# Exact / bootstrap statistics (stdlib only; reimplemented for independence;
# n<=10 so beta bisection is cheap).
# ---------------------------------------------------------------------------

def _betacf(a, b, x, itmax=300, eps=3e-14):
    """Lentz continued fraction for the incomplete beta function."""
    import math
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
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


def _betainc_reg(a, b, x):
    """Regularized incomplete beta I_x(a,b), 0<=x<=1."""
    import math
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def _ibeta_inv(a, b, p):
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc_reg(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    if n == 0:
        return None
    lo = 0.0 if k == 0 else _ibeta_inv(k, n - k + 1, alpha / 2)
    hi = 1.0 if k == n else _ibeta_inv(k + 1, n - k, 1 - alpha / 2)
    return {'k': k, 'n': n, 'point': round(k / n, 4),
            'ci95_low': round(lo, 4), 'ci95_high': round(hi, 4),
            'method': 'exact Clopper-Pearson (Beta quantile, bisection)'}


def boot_ci(values, n_boot=BOOT_B, seed=BOOT_SEED):
    vals = list(values)
    n = len(vals)
    if n == 0:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(n_boot):
        sel = [vals[rng.randrange(n)] for _ in range(n)]
        stats.append(sum(sel) / n)
    stats.sort()
    point = sum(vals) / n
    return {'point': round(point, 4),
            'ci95_low': round(stats[int(0.025 * (n_boot - 1))], 4),
            'ci95_high': round(stats[int(0.975 * (n_boot - 1))], 4),
            'method': f'issue-cluster non-parametric bootstrap B={n_boot} '
                      f'seed={seed}', 'n_issues': n}


# ---------------------------------------------------------------------------
# Loading + STRICT pairing
# ---------------------------------------------------------------------------

def _read(p):
    return list(read_jsonl(str(p)))


def load_data():
    man = json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))
    issues = sorted({c['instance_id'] for c in man['cells']})
    gold_c, gold_o = {}, {}
    for c in man['cells']:
        gold_c[(c['instance_id'], c['condition'])] = c['audit_condition_gold']
        gold_o[c['instance_id']] = c['audit_oracle_gold']

    new = {}  # (model, iid, cond) -> g3b3 row
    new_by_pair = {}  # g3b pair cell key -> row (per model implicit)
    for fn in ('g3b3_live_deepseek_flash_results.jsonl',
               'g3b3_live_gpt_41_mini_results.jsonl'):
        for r in _read(C.OUT_LIVE_DIR / fn):
            m = r.get('model_profile') or r['model']
            new[(m, r['instance_id'], r['condition'])] = r
            new_by_pair[(m, r['g3b_pair_cell_key'])] = r

    old = {}  # (model, iid, cond) -> frozen G3-B row
    for p in (C.G3B_LIVE_DEEPSEEK, C.G3B_LIVE_GPT):
        for r in _read(p):
            old[(r['model'], r['instance_id'], r['condition'])] = r

    # STRICT pairing: every new row must find its same-model G3-B row through
    # g3b_pair_cell_key == g3b cell, on the same issue+condition.
    pairs = {}
    for (m, iid, cond), r in new.items():
        anchor = r['g3b_pair_cell_key']
        ro = old.get((m, iid, cond))
        if ro is None or ro.get('cell') != anchor:
            raise SystemExit(
                f'strict pairing broken for {m}/{iid}/{cond}: '
                f'anchor={anchor} g3b_cell={None if ro is None else ro.get("cell")}')
        pairs[(m, iid, cond)] = (ro, r)
    if len(new) != 100 or len(pairs) != 100:
        raise SystemExit(f'expected 100 paired cells, got {len(pairs)}')
    return {'manifest': man, 'issues': issues, 'gold_c': gold_c,
            'gold_o': gold_o, 'new': new, 'old': old, 'pairs': pairs}


# ---------------------------------------------------------------------------
# Verdict helpers
# ---------------------------------------------------------------------------

def verdict(r):
    p = r.get('parsed')
    if p in TERNARY:
        return p
    if r.get('error') and p is None:
        return 'ERROR'
    return p or 'ERROR'


def is_need(r):
    return r.get('parsed') == 'NEED_EVIDENCE'


def is_accept(r):
    return r.get('parsed') == 'ACCEPT'


def _reason(r):
    if r.get('reason'):
        return str(r['reason'])
    ans = r.get('answer') or r.get('answer_raw') or ''
    try:
        return str(json.loads(ans).get('reason', ''))[:600]
    except Exception:
        return str(ans)[:600]


def _tool_facts(r):
    return {
        'tool_calls': r.get('tool_calls', 0),
        'model_calls': r.get('model_calls', 0),
        'called_artifact': r.get('called_artifact'),
        'called_linkage': r.get('called_linkage'),
        'saw_linked_false': r.get('saw_linked_false'),
        'called_freshness': r.get('called_freshness'),
        'fresh_state_served': r.get('fresh_state_served'),
        'saw_fresh_true': r.get('saw_fresh_true'),
        'saw_fresh_false': r.get('saw_fresh_false'),
        'saw_fresh_unknown': r.get('saw_fresh_unknown'),
        'called_coverage': r.get('called_coverage'),
        'saw_coverage_incomplete': r.get('saw_coverage_incomplete'),
        'called_consistency': r.get('called_consistency'),
        'saw_contradicted': r.get('saw_contradicted'),
        'strict_denied_403': r.get('strict_denied_403'),
        'escalation_requested': r.get('escalation_requested'),
        'escalation_granted': r.get('escalation_granted'),
        'escalation_denied': r.get('escalation_denied'),
        'tool_verdicts': r.get('tool_verdicts'),
    }


# ---------------------------------------------------------------------------
# #10 DeepSeek NEED under sufficient regimes + strict paired transitions
# ---------------------------------------------------------------------------

def q10_deepseek_need(D):
    issues, gold_c = D['issues'], D['gold_c']
    suff = C.SUFFICIENT_CONDITIONS
    grid = []
    per_cond = {}
    for cond in suff:
        flags = {}
        for iid in issues:
            r = D['new'][(DS, iid, cond)]
            flags[iid] = int(is_need(r))
            grid.append({
                'issue': iid, 'condition': cond,
                'condition_gold': gold_c[(iid, cond)],
                'g3b3_verdict': verdict(r), 'need': flags[iid],
                'tool_facts': _tool_facts(r)})
        k = sum(flags.values())
        per_cond[cond] = {
            'need_k': k, 'n': len(issues),
            'rate': clopper_pearson(k, len(issues)),
            'issue_cluster_bootstrap': boot_ci(list(flags.values()))}

    # OR-aggregated C2-style over-abstention indicator (>=1 NEED among the 3
    # sufficient regimes), stratified by oracle gold, as in frozen G3-B.
    or_per, strata = [], defaultdict(list)
    for iid in issues:
        v = int(any(is_need(D['new'][(DS, iid, c)]) for c in suff))
        or_per.append(v)
        strata[D['gold_o'][iid]].append(v)
    strat = {g: {'k': sum(v), 'n': len(v),
                 'rate': round(sum(v) / len(v), 4) if v else None}
             for g, v in sorted(strata.items())}
    or_agg = {'k': sum(or_per), 'n': len(issues),
              'exact': clopper_pearson(sum(or_per), len(issues)),
              'issue_cluster_bootstrap': boot_ci(or_per),
              'stratified_by_oracle_gold': strat,
              'per_issue': dict(zip(issues, or_per))}

    # ---- strict paired G3-B -> G3-B.3 transitions ----------------------
    trans_counts = Counter()
    per_cell = []
    old_any, new_any = [], []
    per_cond_pair = {}
    for cond in suff:
        cc = Counter()
        old_f, new_f = [], []
        for iid in issues:
            ro, rn = D['pairs'][(DS, iid, cond)]
            vo, vn = verdict(ro), verdict(rn)
            trans_counts[(vo, vn)] += 1
            cc[(vo, vn)] += 1
            old_f.append(int(vo == 'NEED_EVIDENCE'))
            new_f.append(int(vn == 'NEED_EVIDENCE'))
            per_cell.append({'issue': iid, 'condition': cond,
                             'g3b_verdict': vo, 'g3b3_verdict': vn,
                             'g3b_reason': _reason(ro),
                             'g3b3_reason': _reason(rn),
                             'transition': f'{vo}->{vn}'})
        per_cond_pair[cond] = {
            'transitions': {f'{a}->{b}': n for (a, b), n in
                            sorted(cc.items())},
            'g3b_need_rate': round(sum(old_f) / len(old_f), 4),
            'g3b3_need_rate': round(sum(new_f) / len(new_f), 4),
            'matched_rate_delta': round(
                sum(new_f) / len(new_f) - sum(old_f) / len(old_f), 4)}
    for iid in issues:
        old_any.append(int(any(verdict(D['pairs'][(DS, iid, c)][0])
                               == 'NEED_EVIDENCE' for c in suff)))
        new_any.append(int(any(verdict(D['pairs'][(DS, iid, c)][1])
                               == 'NEED_EVIDENCE' for c in suff)))
    issue_deltas = [round(nn - oo, 4) for nn, oo in zip(new_any, old_any)]
    # discordant pairs (McNemar b/c reported descriptively only; no p-value).
    b_need_to_other = sum(1 for oo, nn in zip(old_any, new_any)
                          if oo == 1 and nn == 0)
    c_other_to_need = sum(1 for oo, nn in zip(old_any, new_any)
                          if oo == 0 and nn == 1)
    paired = {
        'pairing_rule': 'SAME model=deepseek-flash, instance_id, condition; '
                        'g3b3.g3b_pair_cell_key == g3b.cell; only protocol '
                        'version/run-time differs',
        'n_paired_cells': len(per_cell),
        'pooled_cell_transition_counts':
            {f'{a}->{b}': n for (a, b), n in sorted(trans_counts.items())},
        'per_condition': per_cond_pair,
        'or_aggregated_need_any': {
            'g3b': {'k': sum(old_any), 'n': len(old_any),
                    'exact': clopper_pearson(sum(old_any), len(old_any)),
                    'bootstrap': boot_ci(old_any)},
            'g3b3': {'k': sum(new_any), 'n': len(new_any),
                     'exact': clopper_pearson(sum(new_any), len(new_any)),
                     'bootstrap': boot_ci(new_any)}},
        'per_issue_needany_delta': dict(zip(issues, issue_deltas)),
        'matched_issue_delta_bootstrap': boot_ci(issue_deltas),
        'discordant_needany_need_to_other': b_need_to_other,
        'discordant_needany_other_to_need': c_other_to_need,
        'comparison_kind': 'cross-version cross-run-time ASSOCIATIONAL; '
                           'freshness repair and T2A trust repair shipped '
                           'together and are NOT causally separable'}
    return {'issue_condition_grid': grid, 'per_condition_need': per_cond,
            'or_aggregated_over_abstention': or_agg,
            'strict_paired_g3b_transition': paired,
            'per_cell_pairs': per_cell}


# ---------------------------------------------------------------------------
# #11 GPT unsupported acceptance on the 3 gold-REJECT issues (full sample)
# ---------------------------------------------------------------------------

def q11_gpt_unsupported(D):
    issues = [i for i in D['issues']
              if any(i.endswith(s) for s in REJECT_SHORT)]
    full = []
    full_flags = []
    per_issue_or = {}
    for iid in issues:
        flags = []
        for cond in C.CONDITIONS:
            r = D['new'][(GPT, iid, cond)]
            v = verdict(r)
            cg = D['gold_c'][(iid, cond)]
            unsupported = (v == 'ACCEPT' and cg != 'ACCEPT')
            ro = D['old'][(GPT, iid, cond)]
            flags.append(int(unsupported))
            full_flags.append(int(unsupported))
            full.append({
                'issue': iid, 'condition': cond,
                'condition_gold': cg, 'oracle_gold': D['gold_o'][iid],
                'g3b3_verdict': v,
                'unsupported_acceptance': bool(unsupported),
                'g3b_verdict': verdict(ro),
                'g3b_unsupported_acceptance':
                    verdict(ro) == 'ACCEPT' and cg != 'ACCEPT',
                'g3b3_reason': _reason(r),
                'tool_facts': _tool_facts(r)})
        per_issue_or[iid] = int(any(flags))

    # primary confirmatory denominator: 3 issues, sufficient regimes only
    suff_flags = []
    per_cond = {}
    for cond in C.SUFFICIENT_CONDITIONS:
        vv = []
        for iid in issues:
            r = D['new'][(GPT, iid, cond)]
            vv.append(int(is_accept(r)
                          and D['gold_c'][(iid, cond)] != 'ACCEPT'))
        per_cond[cond] = {'unsupported_accept_k': sum(vv), 'n': len(vv)}
        suff_flags.extend(vv)
    k_or = sum(per_issue_or.values())
    out = {
        'denominator': '3 oracle-REJECT issues; FULL sample = 15 cells '
                       '(3 issues x 5 conditions); confirmatory OR-aggregate '
                       'uses the 9 sufficient-regime cells exactly as frozen '
                       'G3-B C1',
        'full_sample': {'n_cells': len(full),
                        'unsupported_acceptance_cells': sum(full_flags),
                        'cell_rate': round(sum(full_flags) / len(full), 4)},
        'confirmatory_sufficient_or_aggregate': {
            'k_issues': k_or, 'n_issues': len(issues),
            'exact': clopper_pearson(k_or, len(issues)),
            'issue_cluster_bootstrap': boot_ci(
                [per_issue_or[i] for i in issues]),
            'per_condition_exploratory': per_cond,
            'sufficient_cells_unsupported': sum(suff_flags),
            'sufficient_cells_total': len(suff_flags),
            'per_issue': per_issue_or},
        'cells': full}

    # mandated focal cells
    def focal(iid_short, cond, tag, note):
        iid = next(i for i in issues if i.endswith(iid_short))
        r = D['new'][(GPT, iid, cond)]
        ro = D['old'][(GPT, iid, cond)]
        return {'tag': tag, 'issue': iid, 'condition': cond,
                'condition_gold': D['gold_c'][(iid, cond)],
                'g3b_verdict': verdict(ro), 'g3b3_verdict': verdict(r),
                'g3b3_unsupported_acceptance':
                    verdict(r) == 'ACCEPT'
                    and D['gold_c'][(iid, cond)] != 'ACCEPT',
                'g3b3_reason': _reason(r),
                'tool_facts': _tool_facts(r), 'note': note}

    out['focal_sympy_17318_T2A'] = focal(
        '17318', 'T2A-T', 'sympy-17318/T2A focal',
        'Primary evidence-verification defect cell from G3-B: gold REJECT, '
        'the patch visibly fails FAIL_TO_PASS 0/1. A G3-B.3 ACCEPT here is an '
        'unsupported acceptance despite sufficient, correctly-trusted '
        'evidence (not a freshness artefact; T2A is static).')
    out['decision_policy_probe_sympy_17630_T3A'] = focal(
        '17630', 'T3A-T', 'sympy-17630/T3A Decision-Policy probe',
        'User-flagged, SEPARATELY TAGGED Decision-Policy probe: failure '
        'evidence had been reached under the spurious structural fresh=FALSE '
        'in G3-B. Reported on its own and NEVER pooled with freshness-driven '
        'abstention; under the repaired TRUE freshness this cell isolates, '
        'descriptively, whether the decision policy still errs.')
    return out


# ---------------------------------------------------------------------------
# #12 restricted-regime abstention
# ---------------------------------------------------------------------------

def q12_restricted(D):
    out = {}
    for m in C.MODELS:
        out[m] = {}
        for cond in C.RESTRICTED_CONDITIONS:
            ok, improper = 0, []
            for iid in D['issues']:
                r = D['new'][(m, iid, cond)]
                v = verdict(r)
                if v == 'NEED_EVIDENCE':
                    ok += 1
                else:
                    improper.append({
                        'issue': iid, 'verdict': v,
                        'condition_gold': D['gold_c'][(iid, cond)],
                        'reason': _reason(r),
                        'tool_facts': _tool_facts(r)})
            out[m][cond] = {
                'correct_abstain_k': ok, 'n': len(D['issues']),
                'rate': clopper_pearson(ok, len(D['issues'])),
                'issue_cluster_bootstrap': boot_ci(
                    [int(is_need(D['new'][(m, i, cond)]))
                     for i in D['issues']]),
                'improper_commitment_rate': round(
                    (len(D['issues']) - ok) / len(D['issues']), 4),
                'improper_commitments': improper}
    return out


# ---------------------------------------------------------------------------
# Decision appropriateness + parse failures (both models, all conditions)
# ---------------------------------------------------------------------------

def appropriateness(D):
    out = {}
    for m in C.MODELS:
        out[m] = {}
        for cond in C.CONDITIONS:
            c_ok = o_ok = scored = fail = 0
            for iid in D['issues']:
                r = D['new'][(m, iid, cond)]
                p = r.get('parsed')
                if p not in TERNARY:
                    fail += 1
                    continue
                scored += 1
                c_ok += int(p == D['gold_c'][(iid, cond)])
                o_ok += int(p == D['gold_o'][iid])
            n = len(D['issues'])
            out[m][cond] = {
                'n': n, 'scored': scored, 'parse_or_error': fail,
                'condition_DA_correct': c_ok,
                'condition_DA_rate': round(c_ok / n, 4),
                'oracle_DA_correct': o_ok,
                'oracle_DA_rate': round(o_ok / n, 4)}
    return out


def parse_failures(D):
    out = {}
    for m in C.MODELS:
        bad = []
        for iid in D['issues']:
            for cond in C.CONDITIONS:
                r = D['new'][(m, iid, cond)]
                if r.get('parsed') not in TERNARY:
                    bad.append({'issue': iid, 'condition': cond,
                                'parsed': r.get('parsed'),
                                'error': (r.get('error') or '')[:200]})
        out[m] = {'non_verdict_cells': len(bad), 'cells': 50,
                  'rate': round(len(bad) / 50, 4), 'detail': bad}
    return out


def raw_grids(D):
    grids = {}
    for m in C.MODELS:
        rows = []
        for iid in D['issues']:
            row = {'issue': iid, 'oracle_gold': D['gold_o'][iid]}
            for cond in C.CONDITIONS:
                ro, rn = D['pairs'][(m, iid, cond)]
                row[f'{cond}|g3b'] = verdict(ro)
                row[f'{cond}|g3b3'] = verdict(rn)
                row[f'{cond}|gold'] = D['gold_c'][(iid, cond)]
            rows.append(row)
        grids[m] = rows
    return grids


# ---------------------------------------------------------------------------
# #14 gold sensitivity (all-10 / drop-3-REJECT / trust-grant counterfactual)
# ---------------------------------------------------------------------------

def _ds_need_views(D, issues, conds):
    """Per-cell NEED rate + OR-aggregate over issues for DS under conds."""
    cell_flags = []
    or_flags = []
    for iid in issues:
        fs = [int(is_need(D['new'][(DS, iid, c)])) for c in conds]
        cell_flags.extend(fs)
        or_flags.append(int(any(fs)))
    return {'conditions': list(conds), 'n_issues': len(issues),
            'n_cells': len(cell_flags),
            'need_cells': sum(cell_flags),
            'cell_need_rate': clopper_pearson(sum(cell_flags),
                                              len(cell_flags)),
            'needany_k_issues': sum(or_flags),
            'needany_exact': clopper_pearson(sum(or_flags), len(or_flags)),
            'needany_bootstrap': boot_ci(or_flags)}


def _gpt_ua_view(D, issues, conds):
    cell_flags, or_flags = [], []
    for iid in issues:
        fs = [int(is_accept(D['new'][(GPT, iid, c)])
                  and D['gold_c'][(iid, c)] != 'ACCEPT') for c in conds]
        cell_flags.extend(fs)
        or_flags.append(int(any(fs)))
    return {'conditions': list(conds), 'n_issues': len(issues),
            'n_cells': len(cell_flags),
            'unsupported_accept_cells': sum(cell_flags),
            'cell_ua_rate': clopper_pearson(sum(cell_flags),
                                            len(cell_flags)),
            'ua_any_k_issues': sum(or_flags)}


def q14_sensitivity(D):
    issues = D['issues']
    accept7 = [i for i in issues if D['gold_o'][i] != 'REJECT']
    reject3 = [i for i in issues if D['gold_o'][i] == 'REJECT']
    suff = list(C.SUFFICIENT_CONDITIONS)
    active_suff = ['T3D-Escalate', 'T3A-T']      # freshness-affected active
    t2a = ['T2A-T']                              # static trust-grant block

    views = {
        'provisional_all_10': {
            'issues': issues,
            'DS_need_sufficient': _ds_need_views(D, issues, suff),
            'GPT_unsupported_accept_sufficient':
                _gpt_ua_view(D, issues, suff)},
        'drop_3_reject_issues__accept7_only': {
            'issues': accept7,
            'note': 'C1 (GPT unsupported ACCEPT) is NOT estimable without the '
                    '3 oracle-REJECT issues.',
            'DS_need_sufficient': _ds_need_views(D, accept7, suff),
            'GPT_C1_estimable': False},
        'reject3_only': {
            'issues': reject3,
            'DS_need_sufficient': _ds_need_views(D, reject3, suff),
            'GPT_unsupported_accept_sufficient':
                _gpt_ua_view(D, reject3, suff)}}

    # Trust-grant counterfactual BOUNDARY. The G3-B.2 release repaired T2A
    # policy trust (static block; no tools) and active freshness together, so
    # no causal split is identified. We bound how much of the DS sufficient
    # NEED signal is attributable, in the associational accounting, to the 10
    # T2A cells: observed active-only vs T2A-only rates, plus an explicit
    # worst-case envelope in which revoked trust would make every T2A cell a
    # NEED (upper) or none (lower).
    obs = _ds_need_views(D, issues, suff)
    actv = _ds_need_views(D, issues, active_suff)
    t2av = _ds_need_views(D, issues, t2a)
    k_active = actv['need_cells']
    n_active = actv['n_cells']
    n_suff = obs['n_cells']
    envelope = {
        'observed_sufficient_cell_need_rate':
            obs['cell_need_rate']['point'],
        'active_sufficient_only_T3DEsc_T3A':
            {'k': k_active, 'n': n_active,
             'rate': clopper_pearson(k_active, n_active)},
        'T2A_only_static_trust_block':
            {'k': t2av['need_cells'], 'n': t2av['n_cells'],
             'rate': clopper_pearson(t2av['need_cells'], t2av['n_cells'])},
        'counterfactual_envelope_if_T2A_trust_revoked': {
            'lower_bound_assume_all_T2A_accept': round(
                k_active / n_suff, 4),
            'upper_bound_assume_all_T2A_need': round(
                (k_active + len(issues)) / n_suff, 4),
            'interpretation': 'Envelope over the 30 sufficient cells holding '
                              'the 20 active-condition verdicts fixed and '
                              'letting the 10 static T2A verdicts range; it '
                              'is an ASSOCIATIONAL accounting boundary, NOT a '
                              'causal effect of trust vs freshness.'},
        'paired_g3b_to_g3b3_T2A_DS_need_transition': (
            D['q10_t2a_transition'] if 'q10_t2a_transition' in D else None)}
    views['trust_grant_counterfactual_boundary'] = envelope
    return views


# ---------------------------------------------------------------------------
# #15 per-issue evidence package
# ---------------------------------------------------------------------------

# Deterministic, auditable tag rules (raw evidence is bundled alongside so a
# human reviewer can override any tag):
#   evidence_utilization_improvement : newly gold-correct on an ACTIVE regime,
#       model called tools and obtained positive verification (fresh TRUE
#       and/or linkage holding / coverage complete) that the structurally-
#       false G3-B freshness path could not provide.
#   policy_trust_change              : newly gold-correct on a STATIC /
#       denial regime (T2A-T, T2D-T) or T3D-Strict under a 403 denial, where
#       no positive tool result is available -> only the repaired served
#       block / policy wording can explain the change.
#   remaining_error                  : G3-B.3 verdict still != condition gold.
#   unchanged_correct / unchanged_incorrect : auxiliary, no transition.
def _tag(cond, old_v, new_v, cg, rn):
    if new_v not in TERNARY:
        return 'remaining_error', 'non-verdict row'
    if new_v != cg:
        return 'remaining_error', 'G3-B.3 verdict still != condition gold'
    if old_v == cg:
        return 'unchanged_correct', 'gold-correct under both protocols'
    positive_tool = (
        rn.get('tool_calls', 0) > 0 and (
            rn.get('saw_fresh_true')
            or (rn.get('called_linkage') and not rn.get('saw_linked_false'))
            or (rn.get('called_coverage')
                and not rn.get('saw_coverage_incomplete'))))
    if cond in ('T2A-T', 'T2D-T'):
        return 'policy_trust_change', \
               'static regime: only the repaired served block/policy changed'
    if cond == 'T3D-Strict' and rn.get('strict_denied_403'):
        return 'policy_trust_change', \
               'strict tier-D 403 denial path; policy-enforced abstention'
    if positive_tool:
        return 'evidence_utilization_improvement', (
            'newly correct after calling tools and receiving positive '
            'verification unavailable under the G3-B structural fresh=FALSE')
    return 'remaining_error', \
           'newly gold-correct verdict but no positive tool verification ' \
           'captured; conservatively not labelled evidence-utilization'


def build_issue_evidence(D):
    items = {(it['instance_id'], it['condition']): it
             for it in FZ.build_items()}
    packages = []
    tag_counter = Counter()
    for iid in D['issues']:
        pkg = {'issue': iid, 'oracle_gold': D['gold_o'][iid], 'models': {}}
        for m in C.MODELS:
            cells = []
            for cond in C.CONDITIONS:
                it = items[(iid, cond)]
                ro, rn = D['pairs'][(m, iid, cond)]
                vo, vn = verdict(ro), verdict(rn)
                cg = D['gold_c'][(iid, cond)]
                tag, why = _tag(cond, vo, vn, cg, rn)
                tag_counter[f'{m}|{tag}'] += 1
                messages = GP.build_g3b2_messages(
                    it, artifact=it.get('artifact_record'))
                tool_responses = [
                    {'turn': t.get('turn'), 'tool': t.get('tool'),
                     'args': t.get('args'), 'http_status': t.get('http_status'),
                     'result_preview': t.get('result_preview')}
                    for t in (rn.get('tool_trace') or [])]
                cells.append({
                    'condition': cond, 'condition_gold': cg,
                    'g3b_verdict': vo, 'g3b3_verdict': vn,
                    'classification_tag': tag,
                    'classification_reason': why,
                    'g3b3_model_reasoning': _reason(rn),
                    'g3b3_final_raw_answer': rn.get('answer_raw'),
                    'g3b_model_reasoning': _reason(ro),
                    'tool_facts': _tool_facts(rn),
                    'tool_responses': tool_responses,
                    'rendered_g3b2_prompt': messages,
                    'tokens_in': rn.get('tokens_in'),
                    'tokens_out': rn.get('tokens_out'),
                    'cost_usd': rn.get('cost_usd'),
                    'model_served': rn.get('model_served')})
            pkg['models'][m] = cells
        packages.append(pkg)
    return packages, dict(tag_counter)


# ---------------------------------------------------------------------------

def run():
    D = load_data()
    q10 = q10_deepseek_need(D)
    # expose T2A transition for the #14 trust boundary section
    D['q10_t2a_transition'] = q10['strict_paired_g3b_transition'][
        'per_condition'].get('T2A-T')
    q11 = q11_gpt_unsupported(D)
    q12 = q12_restricted(D)
    da = appropriateness(D)
    pf = parse_failures(D)
    sens = q14_sensitivity(D)
    packages, tag_counts = build_issue_evidence(D)

    audit = json.loads(C.OUT_LIVE_AUDIT.read_text(encoding='utf-8'))
    result = {
        'document': 'Gate 3-B.3 Corrective Replication analysis',
        'gate': C.GATE,
        'gold_authority': C.GOLD_AUTHORITY,
        'basis': '100 NEW real cells (10 independent issues x 5 regimes x 2 '
                 'models) over the accepted G3-B.2 repaired protocol, paired '
                 'strictly to the frozen G3-B cells; independent unit = the '
                 'issue, cells are repeated measures.',
        'associational_caution': (
            'G3-B -> G3-B.3 differences are cross-version, cross-run-time '
            'and ASSOCIATIONAL. The release changed three-state freshness '
            'handling AND T2A policy trust together; their separate causal '
            'effects are NOT identified. Temperature=0 does not make two '
            'runs at different times identical. Do not generalise beyond '
            'these 10 SymPy issues.'),
        'interpretation_rule_q10': (
            'A large drop in DeepSeek sufficient-regime NEED vs G3-B implies '
            'the original C2 over-abstention was largely PROTOCOL-INDUCED '
            '(the model-defect claim is weakened). Persistent NEED on visible '
            'sufficient outcomes is what would evidence a calibration/'
            'decision-policy defect.'),
        'budget_and_run_audit': {
            'total_spend_usd': audit['total_spend_usd'],
            'per_model_spend_usd': audit['per_model_spend_usd'],
            'total_hard_cap_usd': audit['total_hard_cap_usd'],
            'per_model_cap_usd': audit['per_model_cap_usd'],
            'within_total_cap': audit['within_total_cap'],
            'new_rows': audit['new_rows'], 'error_rows': audit['error_rows'],
            'retries_per_cell': audit['retries_per_cell'],
            'runner_version': audit['runner_version'],
            'executed_protocol_version': audit['executed_protocol_version'],
            'executed_prompt_version': audit['executed_prompt_version']},
        'n_independent_issues': len(D['issues']),
        'n_new_cells': 100, 'n_strict_pairs': 100,
        'Q10_deepseek_sufficient_need_and_paired_transition': q10,
        'Q11_gpt_unsupported_acceptance_reject_issues': q11,
        'Q12_restricted_regime_abstention': q12,
        'decision_appropriateness': da,
        'parse_or_transport_failures': pf,
        'per_issue_raw_verdict_grids_g3b_vs_g3b3': raw_grids(D),
        'Q14_gold_sensitivity': sens,
        'Q15_evidence_package_index': {
            'path': str(C.OUT_ISSUE_EVIDENCE.relative_to(C.HERE)),
            'classification_tag_counts': tag_counts,
            'tag_rule': ('deterministic auditable heuristic; every cell '
                         'bundles rendered prompt, tool responses and model '
                         'reasoning so a human can override the tag')},
        'do_not': [
            'do not pool with the E1 22 fixtures or the G3-B cells as '
            'independent observations (paired repeated measures)',
            'do not call gold human-adjudicated (PROVISIONAL, n=1, '
            'annotator2 NOT_OBTAINED; no kappa)',
            'do not report a Cohen kappa',
            'do not interpret restricted-regime NEED as reasoning calibration',
            'do not separate freshness vs trust causal effects (not '
            'identified); do not extrapolate beyond the 10 issues',
            'do not pool the sympy-17630/T3A Decision-Policy probe with '
            'freshness-driven abstention'],
    }

    C.OUT_ANALYSIS.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_ANALYSIS.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    C.OUT_ISSUE_EVIDENCE.write_text(
        json.dumps({'document': 'Gate 3-B.3 per-issue evidence package (#15)',
                    'gold_authority': C.GOLD_AUTHORITY,
                    'classification_tag_counts': tag_counts,
                    'issues': packages},
                   ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'analysis -> {C.OUT_ANALYSIS}')
    print(f'issue evidence -> {C.OUT_ISSUE_EVIDENCE}')

    ornew = q10['or_aggregated_over_abstention']
    orold = q10['strict_paired_g3b_transition'][
        'or_aggregated_need_any']['g3b']
    print(f"#10 DS NEED-any sufficient: G3-B k={orold['k']}/10 "
          f"boot {orold['bootstrap']['ci95_low']}..{orold['bootstrap']['ci95_high']}"
          f" -> G3-B.3 k={ornew['k']}/10 CP {ornew['exact']['ci95_low']}.."
          f"{ornew['exact']['ci95_high']} boot "
          f"{ornew['issue_cluster_bootstrap']['ci95_low']}.."
          f"{ornew['issue_cluster_bootstrap']['ci95_high']}")
    md = q10['strict_paired_g3b_transition'][
        'matched_issue_delta_bootstrap']
    print(f"#10 matched per-issue NEED-any delta boot "
          f"{md['ci95_low']}..{md['ci95_high']} (point {md['point']})")
    c1 = q11['confirmatory_sufficient_or_aggregate']
    print(f"#11 GPT UA sufficient-OR {c1['k_issues']}/3 CP "
          f"{c1['exact']['ci95_low']}..{c1['exact']['ci95_high']}; "
          f"full 15-cell unsupported={q11['full_sample']['unsupported_acceptance_cells']}; "
          f"17318/T2A unsupported="
          f"{q11['focal_sympy_17318_T2A']['g3b3_unsupported_acceptance']}; "
          f"17630/T3A verdict={q11['decision_policy_probe_sympy_17630_T3A']['g3b3_verdict']}")
    for m in C.MODELS:
        for cond in C.RESTRICTED_CONDITIONS:
            s = q12[m][cond]
            print(f"#12 {m[:3]} {cond} correct-abstain "
                  f"{s['correct_abstain_k']}/10 improper={len(s['improper_commitments'])}")
    print('tag counts:', json.dumps(tag_counts, ensure_ascii=False))
    return result


if __name__ == '__main__':
    run()
