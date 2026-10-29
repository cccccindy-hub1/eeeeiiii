"""G3-A task 11 — independent recomputation of the three UA denominators.

Reads the frozen Experiment X gpt results only; writes the exact numerator/
denominator accounting behind 34/88 (0.3864), 34/60 (0.5667), and the
issue-equal-weighted 0.6625. $0, frozen artifacts read-only.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
XRUNS = ROOT / 'evidence_store_eal' / 'v21x_runs'
DESIGN = ROOT / 'evidence_store_eal' / 'v21' / 'eal_v21_design_manifest.json'
OUTDIR = ROOT / 'evidence_store_g3a' / 'audit'
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = OUTDIR / 'g3a_ua_denominators.json'


def main():
    rows = list(read_jsonl(str(XRUNS /
                               'eal_v21x_live_gpt_41_mini_results.jsonl')))
    man = json.loads(DESIGN.read_text(encoding='utf-8'))
    iss = {it['bundle_id'][-8:]: it['instance_id'] for it in man['items']}

    n = len(rows)
    elig = [r for r in rows if r['cee_gold'] in ('REJECT', 'NEED_EVIDENCE')]
    ua = [r for r in elig if r['parsed'] == 'ACCEPT']

    per_issue = {}
    by_elig = defaultdict(lambda: [0, 0])   # [ua, eligible]
    by_all = defaultdict(lambda: [0, 0])    # [ua, all cells]
    for r in rows:
        i = iss[r['bundle_id'][-8:]].split('sympy-')[-1]
        by_all[i][1] += 1
        if r['cee_gold'] in ('REJECT', 'NEED_EVIDENCE'):
            by_elig[i][1] += 1
            if r['parsed'] == 'ACCEPT':
                by_elig[i][0] += 1
                by_all[i][0] += 1
    for i in sorted(by_all):
        a, e = by_elig[i]
        ua_all, tot = by_all[i]
        per_issue[i] = {
            'ua': ua_all, 'eligible_cells': e, 'all_cells': tot,
            'ua_rate_over_eligible': round(a / e, 4) if e else None,
            'ua_rate_over_all_cells': round(ua_all / tot, 4)}

    elig_rates = [v['ua_rate_over_eligible'] for v in per_issue.values()
                  if v['ua_rate_over_eligible'] is not None]
    all_rates = [v['ua_rate_over_all_cells'] for v in per_issue.values()]

    result = {
        'document': 'Exact denominator accounting for the three GroundedReview'
                    ' X unsupported-acceptance proportions (gpt-4.1-mini).',
        'error_family_rate_per_cell': {
            'numerator_ua': len(ua), 'denominator_all_parseable_cells': n,
            'value_34_over_88': round(len(ua) / n, 4),
            'population': 'all 88 parseable cells incl. 28 ACCEPT-gold cells '
                          'where UA is structurally impossible'},
        'conditional_ua_rate_cell_weighted': {
            'numerator_ua': len(ua),
            'denominator_acceptance_eligible_cells': len(elig),
            'eligible_gold_mix': {'REJECT': sum(r['cee_gold'] == 'REJECT'
                                                for r in elig),
                                  'NEED_EVIDENCE':
                                      sum(r['cee_gold'] == 'NEED_EVIDENCE'
                                          for r in elig)},
            'value_34_over_60': round(len(ua) / len(elig), 4),
            'population': 'cells whose gold is REJECT or NEED_EVIDENCE; '
                          'mirror fixtures x 4 conditions are counted '
                          'separately (cell-weighted)'},
        'issue_equal_weighted_conditional_rate': {
            'value': round(sum(elig_rates) / len(elig_rates), 4),
            'denominator_n_issues_with_eligible_cells': len(elig_rates),
            'population': 'one equal vote per independent issue over the 9 '
                          'issues with >=1 eligible cell; within-issue '
                          'mirrors/conditions averaged first'},
        'issue_equal_weighted_per_cell_rate': {
            'value': round(sum(all_rates) / len(all_rates), 4),
            'denominator_n_issues': len(all_rates),
            'population': 'one equal vote per independent issue across all 10 '
                          'issues; includes the pure-ACCEPT issue 16450 at 0'},
        'events_are_not_independent': {
            'distinct_fixtures_with_ua': len({r['bundle_id'][-8:] for r in
                                              ua}),
            'note': '34 UA events come from 9 fixtures, 24 inside mirrored '
                    'negative fixtures; issue-equal weighting does not turn '
                    'them into 34 independent failures.'},
        'per_issue': per_issue}
    OUT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())
    print('34/88 =', round(len(ua) / n, 4))
    print('34/60 =', round(len(ua) / len(elig), 4))
    print('issue-equal eligible =', round(sum(elig_rates) /
                                          len(elig_rates), 4))
    print('issue-equal all =', round(sum(all_rates) / len(all_rates), 4))
    print('->', OUT)


if __name__ == '__main__':
    main()
