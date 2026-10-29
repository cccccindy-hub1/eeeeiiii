"""Gate 3-B.4 task 5: G3-B vs G3-B.3 paired comparison under the two
RESTRICTED conditions T2D-T (static, no tool) and T3D-Strict (active evidence
query with post-patch acceptance outcomes withheld).

Question: why does T2D abstain correctly while Strict's ACTIVE evidence query
appears to induce over-commitment in GPT?

All G3-B -> G3-B.3 contrasts are ASSOCIATIONAL: between the two runs more than
freshness changed (the G3-B.3 protocol also changed the trust/Coverage rules),
so a causal attribution to active querying is NOT identifiable here. This
module only documents the paired pattern and the candidate mechanism.
"""
from __future__ import annotations

import json
from collections import Counter

from evidence import g3b4_common as C

RESTRICTED = ('T2D-T', 'T3D-Strict')
ORDERED = tuple(f'sympy__sympy-{x}' for x in
                ('13615', '13974', '15349', '17318', '17630', '19783',
                 '20590', '21847', '24213', '24443'))
SHORT = {iid: iid.split('-')[-1] for iid in ORDERED}
ROW_FILES = {
    'deepseek-flash': (C.G3B_LIVE_DEEPSEEK, C.G3B3_LIVE_DEEPSEEK),
    'gpt-4.1-mini': (C.G3B_LIVE_GPT, C.G3B3_LIVE_GPT)}


def verdict_map(path):
    return {(r['instance_id'], r['condition']): r['parsed']
            for r in C.read_jsonl(path)}


def main():
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    by_issue = {i['issue']: i for i in pe['issues']}

    blocks = {}
    for model, (old_p, new_p) in ROW_FILES.items():
        old, new = verdict_map(old_p), verdict_map(new_p)
        per_cond = {}
        for cond in RESTRICTED:
            rows, trans = [], Counter()
            for iid in ORDERED:
                o, n = old[(iid, cond)], new[(iid, cond)]
                trans[(o, n)] += 1
                # active-query behaviour under g3b3 strict
                n_tools = n_fetches = None
                if cond == 'T3D-Strict':
                    cell = next(c for c in by_issue[iid]['models'][model]
                                if c['condition'] == cond)
                    n_tools = len(cell['tool_responses'])
                    n_fetches = sum(1 for t in cell['tool_responses']
                                    if t['tool'] == 'get_test_artifact')
                rows.append({'issue': SHORT[iid], 'g3b': o, 'g3b3': n,
                             'transition': f'{o} -> {n}',
                             'g3b3_tool_calls': n_tools,
                             'g3b3_artifact_fetches': n_fetches})
            per_cond[cond] = {
                'transition_counts': {f'{a} -> {b}': trans[(a, b)]
                                      for a in ('ACCEPT', 'REJECT',
                                                'NEED_EVIDENCE')
                                      for b in ('ACCEPT', 'REJECT',
                                                'NEED_EVIDENCE')
                                      if trans[(a, b)]},
                'g3b_need_n': sum(v for (a, b), v in trans.items()
                                  if a == 'NEED_EVIDENCE'),
                'g3b3_need_n': sum(v for (a, b), v in trans.items()
                                   if b == 'NEED_EVIDENCE'),
                'per_issue': rows}
        blocks[model] = per_cond

    # Headline paired facts.
    def need_set(model, gate, cond):
        mp = (verdict_map(ROW_FILES[model][0]) if gate == 'g3b'
              else verdict_map(ROW_FILES[model][1]))
        return {SHORT[i] for i in ORDERED if mp[(i, cond)] == 'NEED_EVIDENCE'}

    headline = {}
    for model in ROW_FILES:
        headline[model] = {
            'T2D-T_g3b_need': sorted(need_set(model, 'g3b', 'T2D-T')),
            'T2D-T_g3b3_need': sorted(need_set(model, 'g3b3', 'T2D-T')),
            'Strict_g3b_need': sorted(need_set(model, 'g3b', 'T3D-Strict')),
            'Strict_g3b3_need': sorted(need_set(model, 'g3b3',
                                                'T3D-Strict'))}
        h = headline[model]
        h['T2D_10of10_abstain_both_gates'] = (
            len(h['T2D-T_g3b_need']) == 10
            and len(h['T2D-T_g3b3_need']) == 10)
        h['strict_g3b_to_g3b3_new_accepts'] = sorted(
            set(h['Strict_g3b_need']) - set(h['Strict_g3b3_need']))
        h['strict_g3b_to_g3b3_new_need'] = sorted(
            set(h['Strict_g3b3_need']) - set(h['Strict_g3b_need']))

    out = {
        'document': 'Gate 3-B.4 task 5 T2D-T vs T3D-Strict G3-B vs G3-B.3 '
                    'paired comparison (both models, restricted conditions)',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'api_calls_made_by_this_audit': 0,
        'headline': headline,
        'per_model_per_condition': blocks,
        'mechanism_analysis': {
            'observation_static_T2D': [
                'T2D-T serves a static tier-D surface with NO tools and NO '
                'freshness signal. Both models abstain NEED_EVIDENCE on all '
                '10/10 issues in BOTH G3-B and G3-B.3 — static restricted '
                'evidence never licenses a commitment for either model.'],
            'observation_active_Strict_DeepSeek': [
                'DeepSeek Strict abstains 10/10 in both gates. In G3-B.3 it '
                'actively queried the tools (and fetched the tier-D artifact '
                'in 8/10 cells, seeing the all-PASSED pre-patch baseline map) '
                'yet still abstained — active querying alone did not move it.'],
            'observation_active_Strict_GPT': [
                'GPT Strict abstained 10/10 in G3-B but committed ACCEPT on '
                '7/10 in G3-B.3 (the other 3 still abstain). All 7 committed '
                'cells did NOT fetch the artifact; they committed from the '
                'linkage=true + fresh=true + coverage-complete + symptom-gone'
                ' tool sequence (see g3b4_gpt_strict_audit).'],
            'candidate_mechanism': 'ACTIVE-EVIDENCE-INDUCED OVERCOMMITMENT '
                '(candidate, not proven): under G3-B.3 the active Strict '
                'tools return a coherent set of POSITIVE-LOOKING but non-'
                'decisive signals (authentic linkage, fresh restage, complete '
                'coverage, symptom non-reproduction). GPT appears to convert '
                'that affirmative diagnostic bundle into failure-free '
                'acceptability, whereas the silent static T2D surface gives '
                'no such positive evidence and always yields abstention.',
            'why_not_causally_identified': [
                'This is a cross-version, ASSOCIATIONAL contrast. Between '
                'G3-B and G3-B.3 more than activeness changed: the G3-B '
                'structural freshness defect served fresh_state=FALSE, while '
                'G3-B.3 serves fresh_state=TRUE, and the Coverage/trust '
                'rules were corrected at the same time.',
                'Therefore the 10/10 -> 3/10 GPT Strict abstention shift '
                'cannot be attributed to active querying separately from the '
                'freshness/trust repair. A design that holds freshness and '
                'trust fixed while toggling only tool availability is needed '
                '(proposed for Gate 3-C, not executed).'],
            'supporting_pattern': 'The within-G3-B.3 contrast is suggestive: '
                'T2D (no tools) 10/10 abstain for both models; DeepSeek '
                '(uses tools, high scepticism) 10/10 abstain; GPT (uses tools)'
                ' 3/10 abstain. Activeness is associated with movement only '
                'for the less sceptical model, consistent with — but not '
                'demonstrating — the candidate mechanism.'},
        'gold_authority': C.GOLD_AUTHORITY}
    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_t2d_vs_strict.json'
    dest.write_bytes(C.canonical_bytes(out))
    for model in ROW_FILES:
        h = headline[model]
        print(model)
        print('  T2D  g3b/g3b3 need:', len(h['T2D-T_g3b_need']),
              len(h['T2D-T_g3b3_need']))
        print('  Strict g3b/g3b3 need:', len(h['Strict_g3b_need']),
              len(h['Strict_g3b3_need']),
              'new accepts:', h['strict_g3b_to_g3b3_new_accepts'])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
