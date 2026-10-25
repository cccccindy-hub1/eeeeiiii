#!/usr/bin/env python3
"""Build the 12-patch flip-replication subset: 4 flipped + 8 non-flipped controls."""
import argparse, collections, json, random
from pilot import read_jsonl, write_jsonl

ap = argparse.ArgumentParser()
ap.add_argument('--conditions', default='conditions.jsonl')
ap.add_argument('--results', default='results_all.jsonl')
ap.add_argument('--out', default='replication_subset.jsonl')
ap.add_argument('--meta', default='replication_meta.json')
ap.add_argument('--seed', type=int, default=11)
a = ap.parse_args()

conds = list(read_jsonl(a.conditions))
truth, patch = {}, {}
for c in conds:
    truth[c['id']] = 'GOOD' if c['resolved'] else 'BAD'
    patch[c['id']] = c['patch_sha256']
res = {}
for r in read_jsonl(a.results):
    if r.get('error'): continue
    res[(r['id'], r['condition'].split('_')[0])] = r['parsed']

arms = (neutral := "neutral", "positive", "negative")
flipped = [p for p in truth if len({res.get((p, x)) for x in arms}) > 1]
print("flipped:", len(flipped))

# controls: 2x2 on (ground truth) x (neutral correctness), take 2 each
buckets = collections.defaultdict(list)
for p in truth:
    if p in flipped: continue
    n = res.get((p, 'neutral'))
    ok = (n == "ACCEPT") == (truth[p] == "GOOD")
    buckets[(truth[p], 'neu_ok' if ok else 'neu_err')].append(p)
rng = random.Random(a.seed)
controls = []
for k in sorted(buckets): controls.extend(rng.sample(buckets[k], min(2, len(buckets[k]))))
print("controls:", [(k, len(v)) for k, v in sorted(buckets.items())])

pick = set(flipped) | set(controls)
rows = [c for c in conds if c["id"] in pick]
write_jsonl(a.out, rows)
meta = {p: {"ground_truth": truth[p],
             "neutral_decision": res.get((p, "neutral")),
             "pilot": {x: res.get((p, x)) for x in arms},
             "role": "flipped" if p in flipped else "control"} for p in sorted(pick)}
json.dump(meta, open(a.meta, "w"), indent=2)
print(f"{len(pick)} patches x 3 arms = {len(rows)} conditions -> {a.out}")
for p in sorted(pick): print(" ", meta[p]["role"], meta[p]["ground_truth"], meta[p]["pilot"], p)
