#!/usr/bin/env python3
"""Offline sanity test of analyze(): synthesizes results.jsonl from conditions.jsonl.

Not an experiment. Used to verify that stability metrics are computed correctly
(pairwise agreement must give 1/3 for ACCEPT,ACCEPT,REJECT).
"""
import argparse, json, random
from pilot import read_jsonl, write_jsonl

ap = argparse.ArgumentParser()
ap.add_argument('--conditions', default='variance_subset.jsonl')
ap.add_argument('--output', default='sim_results.jsonl')
ap.add_argument('--model', default='SIM')
ap.add_argument('--repeats', type=int, default=3)
ap.add_argument('--accuracy', type=float, default=0.7)
ap.add_argument('--noise', type=float, default=0.25, help='P(flip) per repeat')
ap.add_argument('--ambiguous-prob', type=float, default=0.05)
ap.add_argument('--seed', type=int, default=7)
a = ap.parse_args()
rng = random.Random(a.seed)

conds = list(read_jsonl(a.conditions))
rows = []
for c in conds:
    truth = 'ACCEPT' if c['resolved'] else 'REJECT'
    for rep in range(a.repeats):
        if rng.random() < a.ambiguous_prob:
            ans = '{"decision":"ACCEPT"}\n\nActually:\n{"decision":"REJECT"}'
            parsed = 'AMBIGUOUS'
        else:
            d = truth if rng.random() < a.accuracy else ('REJECT' if truth == 'ACCEPT' else 'ACCEPT')
            if rng.random() < a.noise:
                d = 'ACCEPT' if d == 'REJECT' else 'REJECT'
            ans = json.dumps({'decision': d, 'reason': 'simulated', 'evidence_mismatch': False})
            parsed = d
        rows.append({'id': c['id'], 'condition': c['condition'], 'repeat': rep, 'model': a.model,
                     'resolved': c['resolved'], 'patch_sha256': c['patch_sha256'],
                     'parsed': parsed, 'answer': ans, 'usage': None})
write_jsonl(a.output, rows)
print(f'wrote {len(rows)} simulated records -> {a.output}')
