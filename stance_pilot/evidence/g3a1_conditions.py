"""G3-A.1 task 6 — project the FIVE frozen evidence-regime condition_gold
labels for the 10 G3-A issues, as a NEW VERSION, without modifying the G3-A
frozen gold (which froze only the full-canonical surface).

Zero API. Reuses the frozen pure rules evidence.gold_w2.condition_gold and
evidence.visibility.project_surface UNCHANGED (no rule drift). The only
G3-A-specific adaptation is that canonical artifact records carry outcomes
but not a run_tree field, so the oracle fact bundle is constructed from the
already-frozen G3-A gold facts (linked/fresh/complete/executed counts/symptom)
plus the tier-A rendered record (display_for_tier, the same chokepoint the
real server uses). This reproduces exactly what load_fixture_facts would
derive for a fixture whose attested tree equals its run tree.

Outputs evidence_store_g3a1/gold/g3a1_condition_gold.jsonl:
  oracle_gold (re-read from frozen G3-A gold; not recomputed differently),
  condition_gold per 5 regimes, projected inputs, basis, and an explicit
  oracle<->condition divergence ledger. Nothing here is a re-adjudication and
  no fixture/patch is altered to manufacture divergence.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.gold_w2 import condition_gold
from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl, _executed_counts
from evidence.views import display_for_tier
from evidence.visibility import W2_CONDITIONS, project_surface

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a'
OUT = G3A1 / 'gold' / 'g3a1_condition_gold.jsonl'

COND_VER = 'w2-gold-v1+g3a-v1+g3a1-condition-v1'


def main():
    store = ArtifactStore(str(G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    frozen = list(read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl')))
    rows = []
    for g in sorted(frozen, key=lambda r: r['instance_id']):
        iid = g['instance_id']
        patch = g['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        if not authentic:
            raise SystemExit(f'inauthentic artifact for {iid}')
        f = g['facts']
        polarity = f['symptom_polarity']  # 'gone' / 'persists' / None
        pres_a = display_for_tier(store, rec, iid, patch, 'A')
        pf, pe = _executed_counts(pres_a)

        # Oracle-side fact bundle, identical semantics to
        # visibility.load_fixture_facts but fed from frozen G3-A facts.
        facts = {
            'linked': f['linked'], 'fresh': f['fresh'],
            'complete': f['complete'],
            'executed_failure_count': f['executed_failure_count'],
            'executed_check_count': f['executed_check_count'],
            'symptom_polarity': polarity,
            'presented_a_record': pres_a,
            'presented_failure_count': pf,
            'presented_check_count': pe,
        }
        oracle = g['oracle_gold']
        cond, inputs, basis, diverge = {}, {}, {}, []
        for c in W2_CONDITIONS:
            surf = project_surface(c, facts)
            cg, cin, cb = condition_gold(c, facts, surf)
            cond[c] = cg
            inputs[c] = cin
            basis[c] = cb
            if cg != oracle:
                diverge.append({'condition': c, 'oracle_gold': oracle,
                                'condition_gold': cg, 'basis': cb})
        rows.append({
            'version': COND_VER,
            'instance_id': iid, 'patch_sha256': patch,
            'artifact_id': aid,
            'oracle_gold': oracle,
            'oracle_source': 'frozen G3-A g3a_gold.jsonl (not recomputed)',
            'symptom_polarity': polarity,
            'condition_gold': cond,
            'condition_inputs': inputs,
            'condition_basis': basis,
            'oracle_condition_divergences': diverge,
            'comparable_conditions': [c for c in W2_CONDITIONS
                                      if cond[c] == oracle],
            'human_adjudication_status': g['human_adjudication']['status'],
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                             for r in rows) + '\n', encoding='utf-8')

    # Tally
    from collections import Counter
    print(f'G3-A.1 condition-gold rows: {len(rows)} -> {OUT}')
    print(f"{'issue':<22}{'oracle':<9}" + ''.join(f'{c:<14}' for c
                                                  in W2_CONDITIONS))
    cond_dist = {c: Counter() for c in W2_CONDITIONS}
    for r in rows:
        print(f"{r['instance_id'].split('-')[-1]:<22}{r['oracle_gold']:<9}"
              + ''.join(f"{r['condition_gold'][c]:<14}" for c in W2_CONDITIONS))
        for c in W2_CONDITIONS:
            cond_dist[c][r['condition_gold'][c]] += 1
    print('oracle dist:', dict(Counter(r['oracle_gold'] for r in rows)))
    for c in W2_CONDITIONS:
        print(f'  {c}: {dict(cond_dist[c])}')
    ndiv = sum(len(r['oracle_condition_divergences']) for r in rows)
    print('total oracle<->condition divergences:', ndiv)


if __name__ == '__main__':
    main()
