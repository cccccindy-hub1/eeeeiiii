"""GroundedReview consolidation — chronic-8 case linkage across G2.5/R1/X ($0).

Joins, for the 8 pre-registered historical bundles, each model's decision at:
  * G2.5 structured layer (gate2 live results, layer=structured)
  * R1 live (r1_runs)
  * Experiment X four conditions a0b0/a1b0/a0b1/a1b1 (v21x_runs)
Reads frozen stores only; writes grc_chronic8_linkage.json.

Also classifies each (model, bundle) trajectory as:
  stable_wrong_accept  : ACCEPT at every observed timepoint despite non-ACCEPT gold
  intervention_moved   : recovered to a non-ACCEPT verdict only in some X cell
  chronic_oscillation  : verdict flips across timepoints without a monotone
                         intervention pattern
  stable_correct       : correct at all observed timepoints
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'evidence_store_eal'
OUT = STORE / 'consolidation' / 'grc_chronic8_linkage.json'

MODELS = (('deepseek-flash', 'deepseek_flash'), ('gpt-4.1-mini', 'gpt_41_mini'))
CONDS = ('a0b0', 'a1b0', 'a0b1', 'a1b1')
CHRONIC8 = ('62dfb1c6', '2c11095a', 'e4e8b26c', 'c637f604',
            'ec813709', 'a25d0cf5', '403163cb', 'c59a8ceb')


def load(prefix_dir, fname):
    return list(read_jsonl(str(STORE / prefix_dir / fname)))


def main():
    out = {'document': 'Pre-registered chronic-8 linkage across G2.5 '
                       '(structured), R1, and X four conditions. Frozen '
                       'stores only; diagnostic subset, not the primary 22.',
           'models': {}}

    for model, sfx in MODELS:
        g2 = load('gate2_runs', f'eal_gate2_live_{sfx}_results.jsonl')
        r1 = load('r1_runs', f'eal_r1_live_{sfx}_results.jsonl')
        xrows = load('v21x_runs', f'eal_v21x_live_{sfx}_results.jsonl')

        # discover layer/condition key names
        def key_layer(r):
            return r.get('layer') or r.get('presentation') or r.get('variant')

        # Three-timepoint comparison uses the structured layer at G2.5 and R1
        # (R1 re-ran the same three presentations); X a0b0 is its successor.
        g2_struct = {r['bundle_id'][-8:]: r for r in g2
                     if (key_layer(r) or '').lower() == 'structured'}
        r1_map = {r['bundle_id'][-8:]: r for r in r1
                  if (key_layer(r) or '').lower() == 'structured'}
        x_map = {}
        for r in xrows:
            x_map.setdefault(r['bundle_id'][-8:], {})[r['condition']] = r

        cases = []
        for b in CHRONIC8:
            g = g2_struct.get(b)
            r = r1_map.get(b)
            xc = x_map.get(b, {})
            gold = None
            for src in (g, r, xc.get('a0b0')):
                if src is not None:
                    gold = src.get('cee_gold') or src.get('gold')
                    if gold:
                        break
            traj = {
                'bundle8': b,
                'gold': gold,
                'g25_structured': (g or {}).get('parsed', g.get('decision'))
                    if g else None,
                'r1': (r or {}).get('parsed', r.get('decision'))
                    if r else None,
                'x_a0b0': (xc.get('a0b0') or {}).get('parsed'),
                'x_a1b0': (xc.get('a1b0') or {}).get('parsed'),
                'x_a0b1': (xc.get('a0b1') or {}).get('parsed'),
                'x_a1b1': (xc.get('a1b1') or {}).get('parsed')}
            seq = [traj['g25_structured'], traj['r1'], traj['x_a0b0'],
                   traj['x_a1b0'], traj['x_a0b1'], traj['x_a1b1']]
            seq = [s for s in seq if s]
            xseq = [traj[k] for k in ('x_a0b0', 'x_a1b0', 'x_a0b1', 'x_a1b1')]
            if gold in ('REJECT', 'NEED_EVIDENCE'):
                if all(s == 'ACCEPT' for s in seq):
                    tag = 'stable_wrong_accept'
                elif any(s == 'ACCEPT' for s in xseq) and \
                        any(s != 'ACCEPT' for s in xseq):
                    tag = 'intervention_moved'
                elif len(set(seq)) > 1:
                    tag = 'chronic_oscillation'
                else:
                    tag = 'stable_correct'
            else:
                tag = 'stable_correct' if len(set(seq)) == 1 else \
                    'chronic_oscillation'
            traj['classification'] = tag
            cases.append(traj)

        summ = Counter(c['classification'] for c in cases)
        out['models'][model] = {
            'classification_summary': dict(summ), 'cases': cases}

    OUT.write_bytes((json.dumps(out, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())
    for model, v in out['models'].items():
        print('===', model, v['classification_summary'])
        for c in v['cases']:
            print(c['bundle8'], c['gold'],
                  'G2.5', c['g25_structured'], 'R1', c['r1'],
                  '| X', c['x_a0b0'], c['x_a1b0'], c['x_a0b1'], c['x_a1b1'],
                  '->', c['classification'])
    print('->', OUT.name)


if __name__ == '__main__':
    main()
