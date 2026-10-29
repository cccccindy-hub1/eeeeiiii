"""Gate 3-B.2 (task 11) — DeepSeek 9 historical NEED issues: old vs repaired
evidence surface diff. OFFLINE DIAGNOSTIC ONLY.

The nine G3-B issues on which DeepSeek answered NEED_EVIDENCE (all except
sympy-17318) are compared across the FROZEN G3-B protocol (as the live model
actually experienced it, per the frozen result rows + frozen endpoint/prompt
behaviour) and the REPAIRED g3b2 protocol.

This is NOT a prompt-tuning input: the historical decisions are not used to
choose or optimise any new text, and no re-decision is inferred. The table only
documents which part of the evidence the model SAW changed for construct-validity
reasons:

  * T2A-T  : the institutional LINKAGE/FRESHNESS/COVERAGE premise the Gold rule
             assumed is now actually communicated (old static block literally
             said "linkage not yet verified").
  * T3A-T / T3D-Escalate : the live freshness endpoint returned fresh=false for
             every cell because the canonical record had no run_tree field
             (None == expected_tree -> False). The repaired authoritative
             adjudicator returns TRUE from independent git restage for 10/10.
  * T3D-Strict / T2D-T : genuinely restricted diagnostic conditions whose
             condition gold is NEED for all ten; no protocol defect, DS NEED is
             consistent with gold and is NOT a reproduced over-abstention.

sympy-17630/T3A is flagged separately per the user: a cell where failure
evidence was reached, which remains worth independent study but is still
confounded by the spurious fresh=false in the old tool response.
"""
from __future__ import annotations

import json

from evidence import g3b2_common as C
from evidence import g3b2_freeze as GZ

DS_LIVE = C.G3B / 'runs' / 'g3b_live_deepseek_flash_results.jsonl'
NINE_NUMS = (13615, 13974, 15349, 17630, 19783, 20590, 21847, 24213, 24443)
NINE = [f'sympy__sympy-{n}' for n in NINE_NUMS]

ACTIVE = {'T3D-Strict', 'T3D-Escalate', 'T3A-T'}


def _confound(cond, old_row):
    """Protocol defect that confounded the old cell, per condition."""
    if cond == 'T2A-T':
        return {
            'confound_class': 'institutional_trust_not_communicated',
            'old_surface': ('static block said "linkage not yet verified"; no '
                            'LINKAGE/FRESHNESS/COVERAGE premise granted, yet '
                            'the gold rule assumed institutional trust'),
            'new_surface': ('INSTITUTIONAL TRUST MANDATE grants L/F/C provenance '
                            '+ completeness; outcomes still rendered; verdict '
                            'not disclosed'),
            'old_gold_interpretation_now': ('model demanding more linkage/'
                                            'coverage evidence was a reasonable '
                                            'reaction, not a trust-rule breach'),
        }
    if cond in ACTIVE:
        return {
            'confound_class': 'structural_freshness_false_negative',
            'old_surface': (f"live /freshness returned fresh=false "
                            f"(saw_fresh_false={old_row.get('saw_fresh_false')}) "
                            f"because record.run_tree was absent and "
                            f"None==expected_tree was treated as a mismatch"),
            'new_surface': ('adjudicator uses independent git restage tree -> '
                            'fresh_state=TRUE, fresh=true; missing field would '
                            'be UNKNOWN/schema_error, never false'),
            'old_gold_interpretation_now': ('abstention citing staleness/'
                                            'freshness was a reaction to a '
                                            'factually wrong tool conclusion'),
        }
    # genuinely restricted diagnostic conditions
    return {
        'confound_class': 'none_restricted_condition',
        'old_surface': 'acceptance outcomes genuinely withheld (static tier D '
                       'or strict 403)',
        'new_surface': 'unchanged restriction; repaired protocol does not open '
                       'these surfaces',
        'old_gold_interpretation_now': 'condition gold is NEED for all ten; '
                                       'NEED is gold-consistent, not a '
                                       'reproduced over-abstention',
    }


def build():
    old_rows = {}
    for line in DS_LIVE.read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        old_rows[(r['instance_id'], r['condition'])] = r

    new_items = {(it['instance_id'], it['condition']): it
                 for it in GZ.build_items()}

    table = []
    for iid in NINE:
        for cond in ('T2D-T', 'T2A-T', 'T3D-Strict', 'T3D-Escalate', 'T3A-T'):
            old = old_rows[(iid, cond)]
            new = new_items[(iid, cond)]
            fr = new['_freshness_repaired']
            gc = old.get('gap_classification') or {}
            row = {
                'instance_id': iid,
                'condition': cond,
                'historical_deepseek_decision': old.get('parsed'),
                'historical_evidence_gap': old.get('evidence_gap'),
                'historical_gap_category': gc.get('category'),
                'historical_saw_fresh_false': old.get('saw_fresh_false'),
                'condition_gold': new['_condition_gold_old'],
                'repaired_fresh_state': fr['fresh_state'],
                'repaired_fresh_bool': fr['fresh'],
                'repaired_run_tree_match': fr.get('run_tree_match'),
                'repaired_authoritative_tree_source':
                    fr.get('authoritative_tree_source'),
                'evidence_surface_changed': cond != 'T2D-T' and (
                    cond == 'T2A-T' or cond in ACTIVE),
                **_confound(cond, old),
            }
            if iid.endswith('17630') and cond == 'T3A-T':
                row['special_flag'] = (
                    'user-flagged: failure evidence had been reached yet the '
                    'cell abstained/decided under the spurious fresh=false; '
                    'candidate Decision-Policy study, still confounded, keep '
                    'separate from freshness-driven abstention')
            table.append(row)
    return table


def summarise(table):
    by = {}
    for r in table:
        d = by.setdefault(r['condition'], {
            'historical_NEED': 0, 'historical_other': 0,
            'confound_class': r['confound_class'],
            'evidence_surface_changed': r['evidence_surface_changed'],
            'condition_gold_set': set()})
        if r['historical_deepseek_decision'] == 'NEED_EVIDENCE':
            d['historical_NEED'] += 1
        else:
            d['historical_other'] += 1
        d['condition_gold_set'].add(r['condition_gold'])
    for cond, d in by.items():
        d['condition_gold_set'] = sorted(d['condition_gold_set'])
    return by


def main():
    table = build()
    out = {
        'document': ('Gate 3-B.2 task 11: offline diagnostic diff of the '
                     'evidence surface for the 9 DeepSeek historical-NEED '
                     'issues between the frozen G3-B protocol and the repaired '
                     'g3b2 protocol. Historical decisions are NOT used to tune '
                     'prompts and no model re-decision is claimed.'),
        'protocol_version': C.PROTOCOL_VERSION,
        'historical_source': str(DS_LIVE.relative_to(C.HERE)),
        'nine_issues': NINE,
        'excluded_issue': 'sympy__sympy-17318',
        'n_rows': len(table),
        'summary_by_condition': summarise(table),
        'rows': table,
        'research_handling': {
            't2a': 're-examine under G3-B.3: if NEED rate falls, original C2 '
                   'finding was largely protocol-induced; persistent NEED on '
                   'visible sufficient outcomes would evidence calibration/'
                   'decision-policy defect',
            't3a_escalate': 'freshness now TRUE via authoritative restage; '
                            'stale-cited abstention can no longer occur',
            'strict_t2d': 'NEED is gold-consistent by design; excluded from '
                          'over-abstention counts',
            '17630_t3a': 'retain as a separately tagged Decision-Policy probe; '
                         'do not pool with freshness-driven abstention',
        },
        'gold_tier': 'PROVISIONAL', 'annotators': 1,
        'annotator2': 'NOT_OBTAINED',
    }
    C.OUT_DS9_DIFF.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_DS9_DIFF.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print('rows =', len(table))
    for cond, d in out['summary_by_condition'].items():
        print(f"  {cond:14s} NEED={d['historical_NEED']} "
              f"other={d['historical_other']} confound={d['confound_class']}")


if __name__ == '__main__':
    main()
