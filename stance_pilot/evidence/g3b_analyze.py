"""GroundedReview Gate 3-B — analysis (offline; reads frozen result rows).

Produces, against PROVISIONAL singly-adjudicated gold ONLY:
  * Oracle Decision Appropriateness and Condition Decision Appropriateness,
    reported SEPARATELY per model per condition (never pooled with E1's 22
    fixtures; the 100 cells are repeated measures on 10 independent issues);
  * C1 (confirmatory, directional): gpt-4.1-mini unsupported ACCEPT on the 3
    gold-REJECT issues, OR-aggregated within issue across the three SUFFICIENT
    regimes, k/3 with an exact Clopper-Pearson interval and an issue-cluster
    bootstrap 95% CI;
  * C2 (confirmatory, directional): deepseek-flash over-abstention
    (NEED_EVIDENCE) under the three sufficient regimes over all 10 issues,
    OR-aggregated within issue, k/10 stratified by oracle gold, with CIs;
  * the two RESTRICTED regimes (T2D-T, T3D-Strict, 10/10 gold=NEED) reported
    separately as correct-abstention rates, NOT interpreted as reasoning
    ability;
  * per-issue raw verdict table, error families, source-verification
    failures, verbatim reasons;
  * paired contrasts and issue-cluster bootstrap CIs (B>=10000);
  * gold sensitivity in three views: provisional all-10, the 3 REJECT issues
    removed, and any issue carrying a recorded adjudication dispute.

Parse/transport failures count as non-ACCEPT for the UA numerator and are
reported separately as a failure rate. Nothing here edits gold.

Offline:
    uv run --python 3.13 -m evidence.g3b_analyze --live
    uv run --python 3.13 -m evidence.g3b_analyze --mock   # pipeline smoke
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from evidence.g3b_freeze import G3B, MODELS
from evidence.ternary import TERNARY, read_jsonl

ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = G3B / 'runs'
OUT_DIR = G3B / 'analysis'

RESTRICTED = ('T2D-T', 'T3D-Strict')
SUFFICIENT = ('T3D-Escalate', 'T2A-T', 'T3A-T')
ALL_COND = RESTRICTED + SUFFICIENT
GPT, DS = 'gpt-4.1-mini', 'deepseek-flash'
BOOT_B = 10000
BOOT_SEED = 7

NONVERDICT = {'INVALID', 'AMBIGUOUS', None}


# ---------------------------------------------------------------------------
# Exact / bootstrap statistics (stdlib only; n<=10 so grid CP is cheap)
# ---------------------------------------------------------------------------

def _betacf(a, b, x, itmax=300, eps=3e-14):
    """Lentz continued fraction for the incomplete beta function
    (Numerical Recipes betacf)."""
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
    """Regularized incomplete beta I_x(a,b) for 0<=x<=1 (Numerical Recipes
    betai, symmetry in the upper tail)."""
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
    """Inverse regularized incomplete beta via bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc_reg(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided Clopper-Pearson interval via Beta quantiles:
    low  = B^{-1}_{alpha/2}(k, n-k+1), high = B^{-1}_{1-alpha/2}(k+1, n-k).
    """
    if n == 0:
        return None
    lo = 0.0 if k == 0 else _ibeta_inv(k, n - k + 1, alpha / 2)
    hi = 1.0 if k == n else _ibeta_inv(k + 1, n - k, 1 - alpha / 2)
    return {'k': k, 'n': n, 'point': k / n,
            'ci95_low': round(lo, 4), 'ci95_high': round(hi, 4),
            'method': 'exact Clopper-Pearson (Beta quantile, bisection)'}


def boot_ci(per_issue_values, n_boot=BOOT_B, seed=BOOT_SEED):
    vals = list(per_issue_values)
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

def load_rows(tag):
    rows = []
    for m in MODELS:
        safe = m.replace('.', '').replace('-', '_')
        p = RUN_DIR / f'g3b_{tag}_{safe}_results.jsonl'
        if not p.exists():
            raise SystemExit(f'missing result file {p}')
        for r in read_jsonl(str(p)):
            r['_model'] = m
            rows.append(r)
    return rows


def index_rows(rows):
    """[(model, iid, cond)] -> terminal row (last if duplicates)."""
    idx = {}
    for r in rows:
        idx[(r['_model'], r['instance_id'], r['condition'])] = r
    return idx


def issue_gold(idx_rows_by_model):
    """oracle/condition gold per issue from freeze audit columns."""
    gold = {}
    for (_m, iid, cond), r in idx_rows_by_model.items():
        gold.setdefault(iid, {'oracle': r.get('audit_oracle_gold')
                              or _freeze_oracle(iid)})
    return gold


def _freeze_oracle(iid):
    man = json.loads((G3B / 'freeze' / 'g3b_freeze_manifest.json')
                     .read_text(encoding='utf-8'))
    for c in man['cells']:
        if c['instance_id'] == iid:
            return c['audit_oracle_gold']
    return None


def is_accept(r):
    return r.get('parsed') == 'ACCEPT'


def is_need(r):
    return r.get('parsed') == 'NEED_EVIDENCE'


def verdict(r):
    p = r.get('parsed')
    if r.get('error') and p is None:
        return 'ERROR'
    return p if p in TERNARY else (p or 'ERROR')


def decision_appropriateness(idx, issues, model):
    """Condition DA and Oracle DA per condition over the given issues."""
    out = {}
    for cond in ALL_COND:
        c_ok = o_ok = scored = fail = 0
        for iid in issues:
            r = idx[(model, iid, cond)]
            p = r.get('parsed')
            cg = r.get('audit_condition_gold') or _cond_gold(iid, cond)
            og = r.get('audit_oracle_gold') or _freeze_oracle(iid)
            if p not in TERNARY:
                fail += 1
                continue
            scored += 1
            c_ok += int(p == cg)
            o_ok += int(p == og)
        n = len(issues)
        out[cond] = {
            'n_issues': n, 'scored': scored,
            'parse_or_error': fail,
            'condition_DA_correct': c_ok,
            'condition_DA_rate': round(c_ok / n, 4),
            'oracle_DA_correct': o_ok,
            'oracle_DA_rate': round(o_ok / n, 4),
            'condition_gold_distribution': dict(Counter(
                (idx[(model, i, cond)].get('audit_condition_gold')
                 or _cond_gold(i, cond)) for i in issues)),
        }
    return out


def _cond_gold(iid, cond):
    man = json.loads((G3B / 'freeze' / 'g3b_freeze_manifest.json')
                     .read_text(encoding='utf-8'))
    for c in man['cells']:
        if c['instance_id'] == iid and c['condition'] == cond:
            return c['audit_condition_gold']
    return None


def per_issue_indicator(idx, issues, model, predicate):
    return {iid: int(any(predicate(idx[(model, iid, c)]) for c in SUFFICIENT))
            for iid in issues}


def c1_unsupported_accept(idx, reject_issues):
    """GPT ACCEPT in >=1 sufficient regime on gold-REJECT issues."""
    per = {}
    per_cond = {}
    for iid in reject_issues:
        flags = {c: is_accept(idx[(GPT, iid, c)]) for c in SUFFICIENT}
        per[iid] = int(any(flags.values()))
        for c in SUFFICIENT:
            per_cond.setdefault(c, []).append(int(flags[c]))
    k = sum(per.values())
    breakdown = {c: {'k': sum(v), 'n': len(v)} for c, v in per_cond.items()}
    return {'model': GPT, 'denominator_issues': len(reject_issues),
            'issues': reject_issues, 'ua_per_issue': per,
            'k': k, 'exact': clopper_pearson(k, len(reject_issues)),
            'issue_cluster_bootstrap': boot_ci(list(per.values())),
            'per_condition_exploratory': breakdown,
            'directional_reproduced': k > 0}


def c2_over_abstention(idx, issues):
    """DeepSeek NEED in >=1 sufficient regime, stratified by oracle gold."""
    per = {}
    strata = defaultdict(dict)
    per_cond = {}
    for iid in issues:
        og = _freeze_oracle(iid)
        flags = {c: is_need(idx[(DS, iid, c)]) for c in SUFFICIENT}
        v = int(any(flags.values()))
        per[iid] = v
        strata[og][iid] = v
        for c in SUFFICIENT:
            per_cond.setdefault(c, {})[iid] = int(flags[c])
    k = sum(per.values())
    strat = {}
    for og, d in strata.items():
        kk = sum(d.values())
        strat[og] = {'k': kk, 'n': len(d),
                     'rate': round(kk / len(d), 4) if d else None}
    breakdown = {c: {'k': sum(d.values()), 'n': len(d)}
                 for c, d in per_cond.items()}
    return {'model': DS, 'denominator_issues': len(issues), 'k': k,
            'over_abstain_per_issue': per,
            'exact': clopper_pearson(k, len(issues)),
            'issue_cluster_bootstrap': boot_ci(list(per.values())),
            'stratified_by_oracle_gold': strat,
            'per_condition_exploratory': breakdown,
            'directional_reproduced': k > 0}


def restricted_abstention(idx, issues, model):
    out = {}
    for cond in RESTRICTED:
        ok = sum(int(is_need(idx[(model, iid, cond)])) for iid in issues)
        improper = []
        for iid in issues:
            if not is_need(idx[(model, iid, cond)]):
                improper.append({'issue': iid,
                                 'verdict': verdict(idx[(model, iid, cond)])})
        out[cond] = {'correct_NEED': ok, 'n': len(issues),
                     'rate': round(ok / len(issues), 4),
                     'inappropriate_commitments': improper}
    return out


def parse_failure_rate(idx, issues, model):
    tot = fails = 0
    detail = []
    for iid in issues:
        for cond in ALL_COND:
            r = idx[(model, iid, cond)]
            tot += 1
            if r.get('parsed') not in TERNARY:
                fails += 1
                detail.append({'issue': iid, 'condition': cond,
                               'parsed': r.get('parsed'),
                               'error': (r.get('error') or '')[:200]})
    return {'non_verdict_cells': fails, 'cells': tot,
            'rate': round(fails / tot, 4), 'detail': detail}


def error_families(idx, issues, model):
    fam = Counter()
    cases = []
    for iid in issues:
        for cond in ALL_COND:
            r = idx[(model, iid, cond)]
            p = r.get('parsed')
            cg = r.get('audit_condition_gold') or _cond_gold(iid, cond)
            og = r.get('audit_oracle_gold') or _freeze_oracle(iid)
            if p not in TERNARY:
                fam['parse_or_transport_failure'] += 1
                continue
            if p == 'ACCEPT' and cg in ('REJECT', 'NEED_EVIDENCE'):
                fam['unsupported_acceptance'] += 1
            if p == 'REJECT' and cg in ('ACCEPT', 'NEED_EVIDENCE'):
                fam['unsupported_rejection'] += 1
            if p == 'NEED_EVIDENCE' and cg in ('ACCEPT', 'REJECT'):
                fam['over_abstention_under_sufficient_evidence'] += 1
            if p in ('ACCEPT', 'REJECT') and cg == 'NEED_EVIDENCE':
                fam['inappropriate_commitment_under_restricted'] += 1
            if p in TERNARY and p != og:
                cases.append({'issue': iid, 'condition': cond,
                              'verdict': p, 'condition_gold': cg,
                              'oracle_gold': og})
    return dict(fam), cases


def source_verification_failures(idx, issues, model):
    """Cells where a source/tool verification actually returned a negative or
    was denied, with the model's verdict and verbatim reason."""
    out = []
    for iid in issues:
        for cond in ALL_COND:
            r = idx[(model, iid, cond)]
            flags = []
            if r.get('saw_linked_false'):
                flags.append('linked_false')
            if r.get('saw_fresh_false'):
                flags.append('fresh_false')
            if r.get('saw_coverage_incomplete'):
                flags.append('coverage_incomplete')
            if r.get('saw_contradicted'):
                flags.append('claim_contradicted')
            if r.get('strict_denied_403'):
                flags.append('strict_403_denial')
            if not flags:
                continue
            out.append({'issue': iid, 'condition': cond,
                        'verdict': verdict(r),
                        'source_flags': flags,
                        'escalation_requested': r.get('escalation_requested'),
                        'escalation_granted': r.get('escalation_granted'),
                        'escalation_denied': r.get('escalation_denied'),
                        'reason_verbatim': _reason(r)})
    return out


def _reason(r):
    ans = r.get('answer') or ''
    try:
        return str(json.loads(ans).get('reason', ''))
    except Exception:
        return (r.get('reason_verbatim') or ans)[:500]


def paired_contrasts(idx, issues):
    """Within-issue model agreement per condition, and restricted-vs-
    sufficient NEED contrast, reported descriptively with bootstrap on the
    matched sufficient-vs-restricted commitment difference."""
    per_cond = {}
    for cond in ALL_COND:
        agree = sum(int(verdict(idx[(GPT, i, cond)])
                        == verdict(idx[(DS, i, cond)])) for i in issues)
        per_cond[cond] = {'agree': agree, 'n': len(issues),
                          'rate': round(agree / len(issues), 4)}
    # matched: each model commits (non-NEED verdict) more under sufficient vs
    # restricted, per issue
    diffs = {}
    for m in MODELS:
        d = []
        for i in issues:
            rest_commit = sum(verdict(idx[(m, i, c)]) in ('ACCEPT', 'REJECT')
                              for c in RESTRICTED) / 2
            suff_commit = sum(verdict(idx[(m, i, c)]) in ('ACCEPT', 'REJECT')
                              for c in SUFFICIENT) / 3
            d.append(round(suff_commit - rest_commit, 4))
        diffs[m] = boot_ci(d)
        diffs[m]['note'] = 'per-issue commit-rate(sufficient)-commit-rate(' \
                           'restricted); positive = more commitment when ' \
                           'more evidence is available'
    return {'gpt_vs_deepseek_verdict_agreement': per_cond,
            'sufficient_minus_restricted_commitment': diffs}


def raw_table(idx, issues):
    table = []
    for iid in issues:
        row = {'issue': iid, 'oracle_gold': _freeze_oracle(iid)}
        for m in MODELS:
            for cond in ALL_COND:
                r = idx[(m, iid, cond)]
                row[f'{m}|{cond}'] = verdict(r)
        table.append(row)
    return table


def sensitivity(idx, all_issues, disputed):
    views = {}
    views['provisional_all_10'] = analyze_core(idx, all_issues,
                                               label='provisional all 10')
    drop_rej = [i for i in all_issues if _freeze_oracle(i) != 'REJECT']
    views['drop_3_reject_issues'] = analyze_core(
        idx, drop_rej, label='7 ACCEPT issues only; C1 not estimable',
        c1_issues=[])
    keep = [i for i in all_issues if i not in disputed]
    views['drop_recorded_disputes'] = analyze_core(
        idx, keep, label=f'disputed removed (n_disputed={len(disputed)})',
        disputed=disputed)
    return views


def analyze_core(idx, issues, label='', c1_issues=None, disputed=None):
    reject_issues = [i for i in issues if _freeze_oracle(i) == 'REJECT']
    core = {'label': label, 'n_issues': len(issues),
            'per_model': {}}
    for m in MODELS:
        core['per_model'][m] = {
            'decision_appropriateness': decision_appropriateness(
                idx, issues, m),
            'restricted_abstention': restricted_abstention(
                idx, issues, m),
            'parse_or_transport_failure': parse_failure_rate(
                idx, issues, m),
            'error_families': error_families(idx, issues, m)[0],
        }
    if c1_issues is None:
        c1_issues = reject_issues
    core['C1_gpt_unsupported_accept'] = (
        c1_unsupported_accept(idx, c1_issues) if c1_issues
        else {'estimable': False, 'reason': 'no REJECT issues in this view'})
    core['C2_deepseek_over_abstention'] = c2_over_abstention(idx, issues)
    return core


def run(tag):
    rows = load_rows(tag)
    idx = index_rows(rows)
    issues = sorted({iid for (_m, iid, _c) in idx})
    expected = set()
    for m in MODELS:
        for iid in issues:
            pass
    # completeness: 100 cells
    missing = [(m, i, c) for m in MODELS for i in issues for c in ALL_COND
               if (m, i, c) not in idx]
    man = json.loads((G3B / 'freeze' / 'g3b_freeze_manifest.json')
                     .read_text(encoding='utf-8'))
    all_issues = sorted({c['instance_id'] for c in man['cells']})
    if set(issues) != set(all_issues):
        print(f'WARNING: {len(issues)} issues present vs 10 frozen; '
              f'missing cells={len(missing)}')

    # recorded adjudication disputes (annotator2 not obtained -> likely none)
    disputed = _recorded_disputes()

    reject_issues = [i for i in all_issues if _freeze_oracle(i) == 'REJECT']
    primary = analyze_core(idx, all_issues, 'PRIMARY: provisional gold n=10')
    primary['C1_gpt_unsupported_accept'] = c1_unsupported_accept(
        idx, reject_issues)
    primary['C2_deepseek_over_abstention'] = c2_over_abstention(
        idx, all_issues)
    primary['paired_contrasts'] = paired_contrasts(idx, all_issues)
    primary['gpt_source_verification_failures'] = source_verification_failures(
        idx, all_issues, GPT)
    primary['deepseek_source_verification_failures'] = \
        source_verification_failures(idx, all_issues, DS)

    result = {
        'document': 'Gate 3-B External Feasibility Pilot analysis',
        'gold_tier': man['gold_tier'],
        'basis': 'against PROVISIONAL, singly-adjudicated gold; NOT an '
                 'independent human-adjudicated validation; n independent '
                 'units = 10 issues, cells are repeated measures',
        'result_tag': tag,
        'n_independent_issues': len(all_issues),
        'n_cells': len(rows),
        'missing_cells': missing,
        'confirmatory_directional': {
            'C1': primary['C1_gpt_unsupported_accept'],
            'C2': primary['C2_deepseek_over_abstention'],
            'rule': 'directional reproduction iff point>0 AND issue-cluster '
                    'bootstrap 95% CI lower bound > 0; no p-value'},
        'primary': primary,
        'per_issue_raw_verdicts': raw_table(idx, all_issues),
        'gold_sensitivity_three_views': sensitivity(
            idx, all_issues, disputed),
        'disputed_issues': disputed,
        'do_not': ['do not pool with the E1 22 fixtures',
                   'do not interpret restricted-regime NEED as reasoning '
                   'calibration',
                   'do not extrapolate k/3 or k/10 to a population rate'],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outp = OUT_DIR / f'g3b_{tag}_analysis.json'
    outp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')
    print(f'G3-B analysis ({tag}) -> {outp}')
    c1 = result['confirmatory_directional']['C1']
    c2 = result['confirmatory_directional']['C2']
    print(f"C1 GPT unsupported-ACCEPT {c1['k']}/{c1['denominator_issues']} "
          f"CP={c1['exact']['ci95_low']}..{c1['exact']['ci95_high']} "
          f"boot={c1['issue_cluster_bootstrap']['ci95_low']}.."
          f"{c1['issue_cluster_bootstrap']['ci95_high']} "
          f"directional={c1['directional_reproduced']}")
    print(f"C2 DS over-abstain {c2['k']}/{c2['denominator_issues']} "
          f"CP={c2['exact']['ci95_low']}..{c2['exact']['ci95_high']} "
          f"boot={c2['issue_cluster_bootstrap']['ci95_low']}.."
          f"{c2['issue_cluster_bootstrap']['ci95_high']} "
          f"directional={c2['directional_reproduced']}")
    return result


def _recorded_disputes():
    p = (ROOT / 'evidence_store_g3a1/adjudication'
         / 'g3a1_adjudication_status.jsonl')
    disputed = []
    if p.exists():
        for r in read_jsonl(str(p)):
            status = (r.get('annotator2') or r.get('status') or '')
            if isinstance(status, str) and any(w in status.lower() for w in
                                               ('disagree', 'dispute',
                                                'conflict')):
                disputed.append(r.get('instance_id') or r.get('blind_code'))
    return [d for d in disputed if d]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--live', action='store_true')
    g.add_argument('--mock', action='store_true')
    a = ap.parse_args()
    run('live' if a.live else 'mock')


if __name__ == '__main__':
    main()
