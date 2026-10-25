#!/usr/bin/env python3
"""Dump full records for every patch whose decision changed between arms."""
import argparse, json
from pilot import read_jsonl, parse_decision

ap = argparse.ArgumentParser()
ap.add_argument('--results', default='results_all.jsonl')
ap.add_argument('--patches', default='conditions.jsonl')
ap.add_argument('--out', default='flips.md')
a = ap.parse_args()

truth, stmt, issue, patch = {}, {}, {}, {}
for r in read_jsonl(a.patches):
    truth[r['id']] = 'GOOD' if r['resolved'] else 'BAD'
    stmt.setdefault(r['id'], {})[r['condition'].split('_')[0]] = r['statement']
    issue[r['id']], patch[r['id']] = r['issue'], r['patch']

dec, reason = {}, {}
for r in read_jsonl(a.results):
    if r.get('error'): continue
    arm = r['condition'].split('_')[0]
    dec[(r['id'], arm)] = r.get('parsed') or parse_decision(r.get('answer', ''))
    try:
        reason[(r['id'], arm)] = json.loads(r['answer']).get('reason', '')
    except Exception:
        reason[(r['id'], arm)] = r['answer']

arms = ('neutral', 'positive', 'negative')
flipped = [p for p in truth if len({dec.get((p, x)) for x in arms}) > 1]

print('== acceptance tendency (ACCEPT rate, ignoring ground truth) ==')
for arm in arms:
    for gt in ('BAD', 'GOOD'):
        vals = [dec[(p, arm)] for p in truth if truth[p] == gt and dec.get((p, arm)) in ('ACCEPT', 'REJECT')]
        acc = sum(v == 'ACCEPT' for v in vals)
        rate = acc / max(1, len(vals))
        print(f'  {arm:9s} {gt:4s} n={len(vals)} ACCEPT={acc} rate={rate:.3f}')

L = ['# Flipped patches: full records', '', '| patch | GT | neutral | positive | negative |', '|---|---|---|---|---|']
for p in flipped:
    L.append(f'| {p} | {truth[p]} | ' + ' | '.join(str(dec.get((p, x))) for x in arms) + ' |')

NL = chr(10)
for p in flipped:
    L.append(NL + '---' + NL)
    L.append('## ' + p + '  (GT=' + truth[p] + ')')
    L.append('### Issue')
    L.append('```' + NL + issue[p][:1500] + NL + '```')
    L.append('### Patch')
    L.append('```diff' + NL + patch[p][:4000] + NL + '```')
    L.append('### Statements (identical except conclusion clause)')
    for arm in arms:
        L.append('- **' + arm + '**: ' + stmt[p][arm])
    for arm in arms:
        L.append('### ' + arm.upper() + ' -> ' + str(dec.get((p, arm))))
        L.append('> ' + reason[(p, arm)].replace(NL, NL + '> ')[:1200])

open(a.out, 'w', encoding='utf-8').write(NL.join(L))
print('flipped patches: ' + str(len(flipped)))
for p in flipped:
    print(' ', p, truth[p], [dec.get((p, x)) for x in arms])
print('wrote ' + a.out)
