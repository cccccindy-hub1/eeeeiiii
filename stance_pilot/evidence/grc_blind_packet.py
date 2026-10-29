"""GroundedReview consolidation — BLINDED pass-3 review packet builder ($0).

Takes the 48 pass-1 lexicon candidates (14 DS + 34 GPT) and emits a blinded
coding packet plus a SEPARATED sealed key. The packet for each randomly
renumbered candidate contains ONLY:
  * the mechanically pre-adjudicated evidence operands for that fixture
    (identity / run-tree / declared-vs-present coverage / executed f2p
    failures), rendered as facts;
  * the model's full reason_verbatim;
  * the pass-1 auto-flagged property code(s) P1..P4 the coder must judge.

It does NOT contain: model name, experimental condition, gold, the model
decision, correctness, or the prior pass-2 verdict. The sealed key mapping
(blind_id -> model/bundle/condition/decision/gold/pass2) is written to a
different file and is NOT opened during blind coding.

Known partial-blindness limits (disclosed in the report): assisted-cell
reasons may themselves discuss the provided counts/table, so the condition
can sometimes be inferred from the text; the coder is the same agent that
produced pass-2, so residual recall bias is possible and agreement is
quantified rather than assumed away.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'evidence_store_eal'
XRUNS = STORE / 'v21x_runs'
FREEZE = STORE / 'v21x' / 'eal_v21x_freeze_manifest.json'
DESIGN = STORE / 'v21' / 'eal_v21_design_manifest.json'
ADJ = XRUNS / 'eal_v21x_live_reason_adjudication.json'
OUTDIR = STORE / 'consolidation'
OUTDIR.mkdir(parents=True, exist_ok=True)

MODELS = ('deepseek-flash', 'gpt-4.1-mini')
SFX = {'deepseek-flash': 'deepseek_flash', 'gpt-4.1-mini': 'gpt_41_mini'}
SHUFFLE_SEED = 20261026

NEG = re.compile(r'(not|no|cannot|uncertain|unclear|may not|does not|'
                 r"doesn't|isn't|cannot confirm|fail to)\s*$")


def pass1_flags(reason, rubric_props):
    """Independent re-implementation of the frozen pass-1 lexicon scan with
    the same immediate-negator/hedge guard. Returns property keys hit."""
    text = (reason or '').lower()
    flags = set()
    for key, spec in rubric_props.items():
        for term in spec['lexicon']:
            i = text.find(term.lower())
            if i >= 0:
                pre = text[max(0, i - 28):i]
                if NEG.search(pre):
                    break
                flags.add(key)
                break
    return flags


def operand_brief(item):
    oc = item.get('operand_counts', {})
    f2p = oc.get('f2p', {})
    p2p = oc.get('p2p', {})
    return {
        'identity_pairs_compared': oc.get('identity_pairs_compared'),
        'identity_equal': oc.get('identity_equal'),
        'identity_differing': oc.get('identity_differing'),
        'identity_differing_fields': oc.get('identity_differing_fields'),
        'runtree_pair_compared': oc.get('runtree_pair_compared'),
        'runtree_equal': oc.get('runtree_equal'),
        'runtree_differing': oc.get('runtree_differing'),
        'declared_f2p': f2p.get('declared'),
        'f2p_present_post': f2p.get('present_post'),
        'f2p_absent_post': f2p.get('absent_post'),
        'f2p_absent_ids': f2p.get('absent_ids'),
        'declared_p2p': p2p.get('declared'),
        'p2p_present_post': p2p.get('present_post'),
        'p2p_absent_post': p2p.get('absent_post'),
        'p2p_absent_ids': p2p.get('absent_ids'),
        'executed_f2p_failed_post_ids': oc.get('f2p_failed_post_ids'),
        'n_executed_f2p_failed': oc.get('n_f2p_failed_post')}


def main():
    fz = json.loads(FREEZE.read_text(encoding='utf-8'))
    props = fz['reason_coding']['properties']
    prop_to_flag = {k: v['operand_flag'] for k, v in props.items()}
    facts = fz['operand_facts_by_bundle8']
    man = json.loads(DESIGN.read_text(encoding='utf-8'))
    items = {it['bundle_id']: it for it in man['items']}

    cands = []
    for m in MODELS:
        for r in read_jsonl(str(XRUNS /
                                f'eal_v21x_live_{SFX[m]}_results.jsonl')):
            if not r['parseable']:
                continue
            fcell = facts.get(r['bundle_id'][-8:], {})
            # pass-1 = lexicon hit AND that property is operand-contradictable
            fl = sorted(k for k in
                        pass1_flags(r['reason_verbatim'], props)
                        if fcell.get(prop_to_flag[k]))
            if fl:
                cands.append({'model': m, 'bundle_id': r['bundle_id'],
                              'condition': r['condition'],
                              'decision': r['parsed'],
                              'gold': r['cee_gold'],
                              'reason': r['reason_verbatim'],
                              'auto_flags': fl})
    assert len(cands) == 48, len(cands)

    # validate we regenerated the SAME candidate set as the shipped pass-1
    adj = json.loads(ADJ.read_text(encoding='utf-8'))
    shipped = set()
    pass2_map = {}
    for m in MODELS:
        for row in adj['models'][m]['rows']:
            shipped.add((m, row['bundle8'], row['condition']))
            pass2_map[(m, row['bundle8'], row['condition'])] = {
                'confirmed': row['pass2_confirmed'],
                'operative': row['operative_on_accept']}
    mine = {(c['model'], c['bundle_id'][-8:], c['condition'])
            for c in cands}
    assert mine == shipped, ('candidate set drift', mine ^ shipped)

    rng = random.Random(SHUFFLE_SEED)
    order = list(range(len(cands)))
    rng.shuffle(order)

    packet, key = [], []
    for new_i, idx in enumerate(order):
        c = cands[idx]
        bid = f'B{new_i + 1:03d}'
        item = items[c['bundle_id']]
        packet.append({
            'blind_id': bid,
            'auto_flagged_properties': c['auto_flags'],
            'evidence_operands': operand_brief(item),
            'reason_verbatim': c['reason'],
            'coding_question': 'For EACH flagged property, decide whether '
                'the reason AFFIRMATIVELY asserts that property about THIS '
                'run, given the operands. Answer CONFIRMED only if the '
                'assertion is explicit, affirmative (not negated/hedged), '
                'and the operands directly contradict it. If the lexicon '
                'word merely describes/acknowledges a failure, qualifies '
                'evidence rather than asserting a match, or disputes '
                'relevance after admitting the fact, answer NOT_CONFIRMED.'})
        k = pass2_map[(c['model'], c['bundle_id'][-8:], c['condition'])]
        key.append({'blind_id': bid, 'model': c['model'],
                    'bundle8': c['bundle_id'][-8:],
                    'condition': c['condition'], 'decision': c['decision'],
                    'gold': c['gold'], 'auto_flags': c['auto_flags'],
                    'pass2_confirmed': k['confirmed'],
                    'pass2_operative_on_accept': k['operative']})

    pp = OUTDIR / 'grc_blind_packet.json'
    kp = OUTDIR / 'grc_blind_key_SEALED.json'
    pp.write_bytes((json.dumps({'document': 'BLINDED pass-3 packet; no '
                                'model/condition/gold/decision/pass2 labels',
                                'n': len(packet), 'candidates': packet},
                               ensure_ascii=False, indent=2) + '\n').encode())
    kp.write_bytes((json.dumps({'document': 'SEALED KEY - do not open until '
                                'blind coding is complete', 'key': key},
                               ensure_ascii=False, indent=2) + '\n').encode())
    print(f'packet {len(packet)} candidates -> {pp.name}')
    print('sealed key ->', kp.name)
    print('DS/GPT:', sum(c["model"] == "deepseek-flash" for c in cands),
          sum(c["model"] == "gpt-4.1-mini" for c in cands))


if __name__ == '__main__':
    main()
