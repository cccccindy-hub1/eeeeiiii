#!/usr/bin/env python3
"""Build the 5-patch variance subset: neutral condition only, N patches, repeats handled by run."""
import argparse, collections, json, random
from pilot import read_jsonl, write_jsonl

ap = argparse.ArgumentParser()
ap.add_argument('--input', default='conditions.jsonl')
ap.add_argument('--output', default='variance_subset.jsonl')
ap.add_argument('--n', type=int, default=5)
ap.add_argument('--condition', default='neutral_no_evidence')
ap.add_argument('--balanced', action='store_true', help='take n/2 resolved=True and n/2 False')
ap.add_argument('--seed', type=int, default=42)
a = ap.parse_args()

rows = [r for r in read_jsonl(a.input) if r['condition'] == a.condition]
rng = random.Random(a.seed)
if a.balanced:
    picked = []
    for label in (True, False):
        pool = [r for r in rows if r['resolved'] is label]
        rng.shuffle(pool)
        picked += pool[: (a.n + 1) // 2]
else:
    rng.shuffle(rows)
    picked = rows[: a.n]

write_jsonl(a.output, picked)
print(f'{len(picked)} patches -> {a.output} '
      f'(resolved: {collections.Counter(r["resolved"] for r in picked)})')
print('patch ids:', [r['id'] for r in picked])
