"""GroundedReview v2 — G2.5 offline error/construct audit ($0 API).

Read-only over FROZEN artifacts; writes only to evidence_store_eal/gate25/.
Covers the 2026-10-25 G2.5 authorisation items 1-8 (case audit, paired
control, wording audit, CEE cell-level comparison, decisive-negative
audit, denominator/CI recheck). No model API, no issue addition, no frozen
file modification.

    uv run --python 3.13 -m evidence.eal_gate25_audit
"""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

from evidence.ternary import read_jsonl
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_render import (DEFAULT_STORE, ArtifactStore, _bundle_id,
                                 load_index, load_materials,
                                 recoverable_facts)

ROOT = Path(__file__).resolve().parent.parent
G2R = ROOT / 'evidence_store_eal' / 'gate2_runs'
CEEDIR = ROOT / 'evidence_store_cee'
OUT = ROOT / 'evidence_store_eal' / 'gate25'
F_GPT = G2R / 'eal_gate2_live_gpt_41_mini_results.jsonl'
F_DS = G2R / 'eal_gate2_live_deepseek_flash_results.jsonl'
MAN = ROOT / 'evidence_store_eal' / 'gate2' / 'eal_gate2_materials_manifest.json'
DECISIONS = ['ACCEPT', 'REJECT', 'NEED_EVIDENCE']

# Case-level classification (item 3) of the 8 NEED-gold -> ACCEPT errors on
# GPT structured. Each label is supported by (a) model output verbatim and
# (b) oracle facts recovered from the SAME primary materials, both joined
# below. Categories: linkage / freshness / coverage / symptom /
# derived_summary / other. A case is tagged with every supported failure,
# ordered by the dominant one. The "sufficiency_illusion" flag marks cases
# whose reason explicitly asserts a property the materials contradict.
CASE_CLASSIFICATION = {
    '62dfb1c6': dict(dominant='freshness', all_=('freshness',),
                     illusion=True,
                     note='reason asserts "fresh"; run tree != attested '
                          'expected tree (def06.. vs 0ffe..)'),
    'ec813709': dict(dominant='coverage', all_=('coverage',),
                     illusion=True,
                     note='claims "acceptance set coverage adequate"; only '
                          '1 f2p of 2 declared f2p + 67 declared p2p '
                          'executed (all p2p absent), no baseline map'),
    'a25d0cf5': dict(dominant='coverage', all_=('coverage',),
                     illusion=True,
                     note='declares "no acceptance/regression failures '
                          'reported"; 89 declared p2p absent, only 1 f2p '
                          'ran; complete=false'),
    'c637f604': dict(dominant='freshness',
                     all_=('freshness', 'coverage'),
                     illusion=True,
                     note='asserts tests "pass fully/no regressions"; tree '
                          'mismatch AND f2p test_latex_basic FAILED '
                          '(0/1 f2p, 101/102 p2p)'),
    '2c11095a': dict(dominant='freshness', all_=('freshness',),
                     illusion=True,
                     note='claims "linked to current tree"; tree mismatch '
                          '(8dee.. vs 4b19..)'),
    'c59a8ceb': dict(dominant='linkage', all_=('linkage', 'freshness'),
                     illusion=True,
                     note='claims "identity operands match"; record patch '
                          'sha 235a.. != TARGET 172a.. (linked=false); '
                          'tree mismatch too'),
    'e4e8b26c': dict(dominant='freshness', all_=('freshness',),
                     illusion=True,
                     note='calls run "fresh"; tree mismatch '
                          '(3aa3.. vs 37e0..)'),
    '403163cb': dict(dominant='coverage', all_=('coverage',),
                     illusion=True,
                     note='says "no scoped regressions/acceptance failures"; '
                          '84 declared p2p all absent (p2p 0/0)'),
}


def oracle_facts_by_bid():
    fixtures, _, _ = load_index(DEFAULT_STORE)
    store = ArtifactStore(str(DEFAULT_STORE))
    out = {}
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        bid = _bundle_id(*key)
        mat = load_materials(store, fx)
        rf = recoverable_facts(mat)
        out[bid] = {'instance_id': fx['instance_id'],
                    'values': rf['values'], 'channels': rf['channels']}
    return out


def cluster_bootstrap(vals, clusters, n_boot=10000, seed=7):
    groups = {}
    for v, c in zip(vals, clusters):
        groups.setdefault(c, []).append(v)
    keys = list(groups)
    rng = random.Random(seed)
    bs = []
    for _ in range(n_boot):
        idx = rng.choices(range(len(keys)), k=len(keys))
        xs = [x for i in idx for x in groups[keys[i]]]
        bs.append(sum(xs) / len(xs))
    bs.sort()
    return {'mean': round(sum(vals) / len(vals), 4),
            'ci95': [round(bs[250], 4), round(bs[9750], 4)],
            'n_clusters': len(keys)}


def confusion(rows):
    mat = {d: {g: 0 for g in DECISIONS} for d in DECISIONS}
    for r in rows:
        if r['parsed'] in DECISIONS:
            mat[r['parsed']][r['cee_gold']] += 1
    return mat


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    man = json.loads(MAN.read_text(encoding='utf-8'))
    items = {i['bundle_id']: i for i in man['items']}
    gpt = {(r['bundle_id'], r['layer']): r for r in read_jsonl(str(F_GPT))}
    ds = {(r['bundle_id'], r['layer']): r for r in read_jsonl(str(F_DS))}
    oracle = oracle_facts_by_bid()

    # ---- item 1-4: case audit + paired DeepSeek control -----------------
    cases = []
    bids8 = [b for b in sorted(items)
             if items[b]['cee_gold'] == 'NEED_EVIDENCE'
             and gpt[(b, 'structured')]['parsed'] == 'ACCEPT']
    for b in bids8:
        r = gpt[(b, 'structured')]
        cls = CASE_CLASSIFICATION[b[-8:]]
        cases.append({
            'bundle_id': b, 'short': b[-8:],
            'instance_id': items[b]['instance_id'],
            'gold': 'NEED_EVIDENCE',
            'gpt_decisions': {'raw': gpt[(b, 'raw')]['parsed'],
                              'structured': 'ACCEPT',
                              'adjudicated': gpt[(b, 'adjudicated')]['parsed']},
            'ds_structured_decision': ds[(b, 'structured')]['parsed'],
            'ds_structured_gap': ds[(b, 'structured')]['evidence_gap_verbatim'],
            'oracle_facts': oracle[b]['values'],
            'missing_channels': {k: v for k, v
                                 in oracle[b]['channels'].items() if not v},
            'reason_verbatim': r['reason_verbatim'],
            'missing_evidence_verbatim': r['missing_evidence_verbatim'],
            'evidence_gap_verbatim': r['evidence_gap_verbatim'],
            'classification': cls})
    # 9th NEED-gold structured error (pred REJECT) and the REJECT->ACCEPT
    extra = []
    for b in sorted(items):
        r = gpt[(b, 'structured')]
        if items[b]['cee_gold'] == 'NEED_EVIDENCE' \
                and r['parsed'] not in ('NEED_EVIDENCE', 'ACCEPT'):
            extra.append({'short': b[-8:], 'predicted': r['parsed'],
                          'gold': 'NEED_EVIDENCE', 'gap': r['evidence_gap_verbatim'],
                          'ds_structured_decision':
                              ds[(b, 'structured')]['parsed'],
                          'reason_excerpt': r['reason_verbatim'][:300]})
        if items[b]['cee_gold'] == 'REJECT' and r['parsed'] == 'ACCEPT':
            extra.append({'short': b[-8:], 'predicted': 'ACCEPT',
                          'gold': 'REJECT', 'gap': r['evidence_gap_verbatim'],
                          'oracle_facts': oracle[b]['values'],
                          'reason_excerpt': r['reason_verbatim'][:300]})

    # ---- item 6: CEE v1.1 cell-level comparison --------------------------
    cee_cmp = {}
    for name, f in (('deepseek-flash', 'cee_v11_deepseek_flash_results.jsonl'),
                    ('gpt-4.1-mini', 'cee_v11_gpt41mini_results.jsonl')):
        crows = {r['bundle_id']: r
                 for r in read_jsonl(str(CEEDIR / f))}
        src = ds if name == 'deepseek-flash' else gpt
        flips = []
        wire = []
        for b, cr in crows.items():
            er = src[(b, 'adjudicated')]
            if cr['parsed'] != er['parsed']:
                flips.append({'bundle_id': b, 'instance_id':
                              items[b]['instance_id'],
                              'evidence_class': cr['evidence_class'],
                              'gold': cr['cee_gold'],
                              'cee_decision': cr['parsed'],
                              'eal_adjudicated_decision': er['parsed'],
                              'cee_appropriate': cr['appropriate'],
                              'eal_appropriate': er['appropriate']})
            wire.append({'bundle_id': b,
                         'bundle_bytes_equal':
                             cr['bundle_sha256'] == er['payload_sha256'],
                         'served_equal':
                             cr['model_served'] == er['model_served']})
        c0 = list(crows.values())[0]
        e0 = src[(list(crows)[0], 'adjudicated')]
        cee_cmp[name] = {
            'n_flips': len(flips), 'flips': flips,
            'prompt_system_identical':
                cee.SYSTEM_MESSAGE == eal.SYSTEM_MESSAGE,
            'all_bundle_bytes_equal': all(w['bundle_bytes_equal'] for w in wire),
            'all_served_ids_equal': all(w['served_equal'] for w in wire),
            'cee_served': c0['model_served'],
            'eal_served': e0['model_served'],
            'temperature': {'cee': c0['temperature_sent'],
                            'eal': e0['temperature_sent']},
            'max_tokens': {'cee': c0['max_tokens_sent'],
                           'eal': e0['max_tokens_sent']},
            'response_format': {'cee': c0['response_format_mode'],
                                'eal': e0['response_format_mode']},
            'tools': {'cee': c0['tools_sent'], 'eal': e0['tools_sent']},
            'plain_text_fallback':
                {'cee': c0['plain_text_fallback'],
                 'eal': e0['plain_text_fallback']},
            'residual_explanation_when_wire_identical':
                'API nondeterminism at temperature=0 (no weight pinning)',
        }

    # ---- item 7: decisive-negative audit (6) ------------------------------
    neg = []
    for b in sorted(items):
        if items[b]['cee_gold'] != 'REJECT':
            continue
        neg.append({'bundle_id': b, 'short': b[-8:],
                    'instance_id': items[b]['instance_id'],
                    'oracle_facts': oracle[b]['values'],
                    'missing_channels': {k: v for k, v
                                         in oracle[b]['channels'].items()
                                         if not v},
                    'decisions': {m: {l: {'decision': src[(b, l)]['parsed'],
                                          'gap': src[(b, l)]['evidence_gap_verbatim'],
                                          'appropriate':
                                              src[(b, l)]['appropriate']}
                                      for l in ('raw', 'structured',
                                                'adjudicated')}
                                  for m, src in (('DS', ds), ('GPT', gpt))}})

    # ---- item 8: independent recheck --------------------------------------
    recheck = {'models': {}}
    for name, src in (('deepseek-flash', ds), ('gpt-4.1-mini', gpt)):
        lb = {}
        for l in ('raw', 'structured', 'adjudicated'):
            L = [src[(b, l)] for b in sorted(items)]
            ok = [1.0 if r['appropriate'] is True else 0.0 for r in L]
            cl = [r['instance_id'] for r in L]
            lb[l] = {'da_n': sum(ok), 'n': len(L),
                     'da_rate': round(sum(ok) / len(L), 4),
                     'ci95': cluster_bootstrap(ok, cl)['ci95'],
                     'confusion': confusion(L),
                     'class_da': {c: (sum(1 for r in L
                                          if r['evidence_class'] == c
                                          and r['appropriate'] is True),
                                     sum(1 for r in L
                                         if r['evidence_class'] == c))
                                  for c in ('sufficient_positive',
                                            'decisive_negative',
                                            'insufficient')}}
        recheck['models'][name] = lb
    recheck['always_need_baseline'] = \
        sum(1 for b in items if items[b]['cee_gold'] == 'NEED_EVIDENCE') / 22

    report = {'audit': 'groundedreview_eal_gate25_offline',
              'api_calls': 0,
              'gpt_structured_need_accept_cases': cases,
              'gpt_structured_other_errors': extra,
              'cee_v11_cell_level_comparison': cee_cmp,
              'decisive_negative_audit': neg,
              'independent_recheck': recheck}
    (OUT / 'eal_gate25_audit.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    cat = Counter(c['classification']['dominant'] for c in cases)
    print('cases:', len(cases), 'dominant categories:', dict(cat))
    print('illusion (reason asserts contradicted property):',
          sum(c['classification']['illusion'] for c in cases))
    print('DS correct on same 8:',
          sum(c['ds_structured_decision'] == 'NEED_EVIDENCE' for c in cases),
          '/8')
    print('CEE flips DS/GPT:',
          cee_cmp['deepseek-flash']['n_flips'],
          cee_cmp['gpt-4.1-mini']['n_flips'])
    print('wrote', OUT / 'eal_gate25_audit.json')


if __name__ == '__main__':
    main()
