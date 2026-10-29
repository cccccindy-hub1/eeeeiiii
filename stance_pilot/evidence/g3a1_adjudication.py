"""G3-A.1 tasks 3/6/9 — adjudication status ledger. Zero API.

Emits a coordinator-side ledger marking all 10 labels as PROVISIONAL
(mechanically adjudicated; human-agreement pending, n_annotators=1). This file
is NOT handed to Annotator 2 (it references real instance ids and provisional
labels). A separate sealed map (g3a1_blind_code_map.json) links blind codes.

Nothing here recomputes or alters gold; it only records status and the frozen
oracle/condition distribution for the audit trail.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
ADJ = G3A1 / 'adjudication'


def main():
    ADJ.mkdir(parents=True, exist_ok=True)
    golds = {g['instance_id']: g
             for g in read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl'))}
    conds = {c['instance_id']: c
             for c in read_jsonl(str(G3A / 'gold' / 'g3a1_condition_gold.jsonl'))}

    rows = []
    for iid in sorted(golds):
        g, c = golds[iid], conds[iid]
        rows.append({
            'instance_id': iid,
            'patch_sha256': g['patch_sha256'],
            'oracle_gold_provisional': g['oracle_gold'],
            'oracle_gold_tier': 'PROVISIONAL (mechanically adjudicated; '
                                'human-agreement pending)',
            'n_independent_annotators': 1,
            'annotator2_status': 'NOT_OBTAINED',
            'symptom_polarity': g['facts']['symptom_polarity'],
            'f2p_total': None,  # filled below from frozen run record
            'f2p_failed_ids': None,
            'condition_gold_provisional': c['condition_gold'],
            'condition_gold_tier': 'PROVISIONAL (institutional projection of '
                                   'frozen facts; human agreement pending on '
                                   'the underlying oracle)',
            'oracle_condition_divergence_count':
                len(c['oracle_condition_divergences']),
            'open_human_questions': [
                'F2P applicability / false-failure screening',
            ] + (['probe criterion A-vs-B (no-throw vs dimensional fix)']
                 if iid.endswith('24213') else []),
        })

    # attach f2p totals from frozen run records
    layers = G3A / 'layers'
    for r in rows:
        recp = layers / r['instance_id'] / 'structured' / 'run_record.json'
        rec = json.load(open(recp, encoding='utf-8'))
        r['f2p_total'] = rec['summary']['f2p_total']
        r['f2p_failed_ids'] = rec['summary']['f2p_failed_ids']
        r['p2p_preexisting_bad_ids'] = rec['summary']['p2p_preexisting_bad_ids']

    out = ADJ / 'g3a1_adjudication_status.jsonl'
    with open(out, 'w', encoding='utf-8', newline='') as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')

    dist = Counter(r['oracle_gold_provisional'] for r in rows)
    cond_dist = {k: Counter(r['condition_gold_provisional'][k] for r in rows)
                 for k in ('T2D-T', 'T3D-Strict', 'T3D-Escalate',
                           'T2A-T', 'T3A-T')}
    summary = {
        'ledger': str(out.name),
        'n_issues': len(rows),
        'all_tiers': 'PROVISIONAL until Annotator 2 completes',
        'oracle_provisional_distribution': dict(dist),
        'natural_distribution_frozen': '7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE; '
            'no mirror fixtures; no relabelling to balance classes',
        'condition_provisional_distribution':
            {k: dict(v) for k, v in cond_dist.items()},
        'total_oracle_condition_divergences':
            sum(r['oracle_condition_divergence_count'] for r in rows),
        'annotator2_status_counts':
            dict(Counter(r['annotator2_status'] for r in rows)),
    }
    (ADJ / 'g3a1_adjudication_status_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
