"""GroundedReview consolidation — per-issue error distribution ($0, offline).

Reads ONLY frozen X live results + the frozen v21 design manifest and reports,
for each of the 10 independent issues and each model:
  * cells in the issue, per-condition error-family counts
    (unsupported_acceptance / unsupported_rejection / over_abstention)
  * unsupported-acceptance concentration (raw share and issue-equal-weighted)
  * mirror groups: fixtures sharing a served-artifact base hash (e.g. a stale
    variant and its valid counterpart) -> whether errors concentrate inside
    mirrored fixtures
  * the cell-weighted vs issue-equal-weighted unsupported-accept rate gap

Writes grc_issue_distribution.json. Does not modify frozen artifacts.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'evidence_store_eal'
XRUNS = STORE / 'v21x_runs'
DESIGN = STORE / 'v21' / 'eal_v21_design_manifest.json'
OUT = STORE / 'consolidation' / 'grc_issue_distribution.json'

MODELS = (('deepseek-flash', 'deepseek_flash'), ('gpt-4.1-mini', 'gpt_41_mini'))
CONDS = ('a0b0', 'a1b0', 'a0b1', 'a1b1')
HASH_TAIL = re.compile(r'([0-9a-f]{16})$')


def family(parsed, gold):
    if parsed == 'ACCEPT' and gold in ('REJECT', 'NEED_EVIDENCE'):
        return 'unsupported_acceptance'
    if parsed == 'REJECT' and gold in ('ACCEPT', 'NEED_EVIDENCE'):
        return 'unsupported_rejection'
    if parsed == 'NEED_EVIDENCE' and gold in ('ACCEPT', 'REJECT'):
        return 'over_abstention'
    return None


def main():
    man = json.loads(DESIGN.read_text(encoding='utf-8'))
    items = {it['bundle_id'][-8:]: it for it in man['items']}

    # mirror groups = shared 16-hex artifact base within an issue
    mirror = defaultdict(list)
    for it in man['items']:
        m = HASH_TAIL.search(it.get('served_artifact_id', ''))
        tail = m.group(1) if m else it['bundle_id'][-8:]
        mirror[(it['instance_id'], tail)].append(it['bundle_id'][-8:])
    bundle_mirror = {}
    gid = 0
    for (issue, tail), bs in sorted(mirror.items()):
        if len(bs) > 1:
            gid += 1
            for b in bs:
                bundle_mirror[b] = f'M{gid}:{issue.split("-")[-1]}'

    per_model = {}
    for model, sfx in MODELS:
        rows = list(read_jsonl(str(XRUNS /
                                   f'eal_v21x_live_{sfx}_results.jsonl')))
        issue_cells = defaultdict(list)
        for r in rows:
            if not r['parseable']:
                continue
            b8 = r['bundle_id'][-8:]
            it = items[b8]
            fam = family(r['parsed'], r['cee_gold'])
            issue_cells[it['instance_id']].append({
                'bundle8': b8, 'condition': r['condition'],
                'decision': r['parsed'], 'gold': r['cee_gold'],
                'scenario': it['scenario_internal'],
                'mirror_group': bundle_mirror.get(b8),
                'family': fam})

        issues_out = {}
        tot = defaultdict(int)
        ua_mirror = ua_nonmirror = 0
        for issue, cells in sorted(issue_cells.items()):
            by_fam = defaultdict(int)
            by_cond = {c: defaultdict(int) for c in CONDS}
            ua_bundles = defaultdict(int)
            for c in cells:
                if c['family']:
                    by_fam[c['family']] += 1
                    by_cond[c['condition']][c['family']] += 1
                    tot[c['family']] += 1
                if c['family'] == 'unsupported_acceptance':
                    ua_bundles[c['bundle8']] += 1
                    if c['mirror_group']:
                        ua_mirror += 1
                    else:
                        ua_nonmirror += 1
            n = len(cells)
            issues_out[issue] = {
                'n_cells': n,
                'n_fixtures': len({c['bundle8'] for c in cells}),
                'unsupported_acceptance': by_fam['unsupported_acceptance'],
                'unsupported_rejection': by_fam['unsupported_rejection'],
                'over_abstention': by_fam['over_abstention'],
                'ua_rate_cells': round(by_fam['unsupported_acceptance'] / n,
                                       4),
                'ua_by_fixture': dict(ua_bundles),
                'mirror_fixtures': sorted({c['bundle8'] for c in cells
                                           if c['mirror_group']}),
                'cells': cells}

        n_parse = sum(len(v) for v in issue_cells.values())
        # only cells where ACCEPT is wrong can commit unsupported acceptance
        ua_eligible = sum(1 for cells in issue_cells.values() for c in cells
                          if c['gold'] in ('REJECT', 'NEED_EVIDENCE'))
        # issue-equal-weighted: mean over issues of the issue's UA cell rate
        rates = [v['ua_rate_cells'] for v in issues_out.values()]
        # restrict UA rate to eligible cells for a fair per-issue measure
        elig_rates = []
        for cells in issue_cells.values():
            elig = [c for c in cells if c['gold'] in
                    ('REJECT', 'NEED_EVIDENCE')]
            ua = sum(c['family'] == 'unsupported_acceptance' for c in elig)
            if elig:
                elig_rates.append(ua / len(elig))
        # concentration: top issue share of all UA
        ua_counts = sorted(((v['unsupported_acceptance'], k) for k, v in
                            issues_out.items()), reverse=True)
        total_ua = sum(x for x, _ in ua_counts)
        top_share = round(ua_counts[0][0] / total_ua, 4) if total_ua else None
        per_model[model] = {
            'n_parseable_cells': n_parse,
            'families': {k: {'count': tot[k],
                             'rate_per_cell': round(tot[k] / n_parse, 4)}
                         for k in ('unsupported_acceptance',
                                   'unsupported_rejection',
                                   'over_abstention')},
            'ua_eligible_cells': ua_eligible,
            'ua_rate_over_eligible_cells': round(
                tot['unsupported_acceptance'] / ua_eligible, 4)
                if ua_eligible else None,
            'ua_issue_equal_weighted_all_cells': round(
                sum(rates) / len(rates), 4),
            'ua_issue_equal_weighted_eligible': round(
                sum(elig_rates) / len(elig_rates), 4),
            'ua_top_issue': ua_counts[0][1] if total_ua else None,
            'ua_top_issue_count': ua_counts[0][0] if total_ua else 0,
            'ua_top_issue_share': top_share,
            'ua_in_mirrored_fixtures': ua_mirror,
            'ua_in_nonmirrored_fixtures': ua_nonmirror,
            'issues': issues_out}

    result = {
        'document': 'Per-issue X error distribution and mirror-fixture '
                    'concentration. Frozen inputs only; no model calls.',
        'n_independent_issues': len({it['instance_id'] for it in
                                     man['items']}),
        'mirror_definition': 'fixtures in the same issue sharing a 16-hex '
                             'served-artifact base (valid + stale/wrong '
                             'counterpart built from the same artifact)',
        'models': per_model}
    OUT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())

    for model, v in per_model.items():
        print('===', model)
        print('families', v['families'])
        print('UA eligible-rate', v['ua_rate_over_eligible_cells'],
              'issue-equal(eligible)', v['ua_issue_equal_weighted_eligible'],
              'issue-equal(all)', v['ua_issue_equal_weighted_all_cells'])
        print('top issue', v['ua_top_issue'], v['ua_top_issue_count'],
              'share', v['ua_top_issue_share'])
        print('UA mirror/nonmirror', v['ua_in_mirrored_fixtures'],
              v['ua_in_nonmirrored_fixtures'])
        for issue, d in sorted(v['issues'].items()):
            if d['unsupported_acceptance']:
                print('  ', issue.split('-')[-1], 'UA',
                      d['unsupported_acceptance'], '/', d['n_cells'],
                      d['ua_by_fixture'])
    print('->', OUT.name)


if __name__ == '__main__':
    main()
