#!/usr/bin/env python3
"""Offline pipeline check: no API calls. Verifies the invariants the README says are non-negotiable."""
import argparse, collections, json
from pilot import read_jsonl, prompt, STANCE_SENTENCES, tokens_proxy

ap = argparse.ArgumentParser()
ap.add_argument('--selected', default='selected.jsonl')
ap.add_argument('--conditions', default='conditions.jsonl')
a = ap.parse_args()

sel = list(read_jsonl(a.selected)); cond = list(read_jsonl(a.conditions))
problems = []

# 1. patch bytes identical across conditions of the same patch
by_id = collections.defaultdict(list)
for c in cond: by_id[c['id']].append(c)
for pid, cs in by_id.items():
    shas = {c['patch_sha256'] for c in cs}
    if len(shas) != 1: problems.append(f'patch drift in {pid}: {shas}')

# 2. issue text identical: prompt must contain issue verbatim for every condition
for c in cond:
    if c['issue'] not in prompt(c): problems.append(f'issue not verbatim: {c["id"]} {c["condition"]}')

# 3. stance sentences: identical prefix/suffix except the conclusion clause
sent = list(STANCE_SENTENCES.values())
prefix = sent[0].split('. ', 1)[0]
for s in sent:
    if s.split('. ', 1)[0] != prefix: problems.append('stance prefix mismatch')
toks = {k: tokens_proxy(v) for k, v in STANCE_SENTENCES.items()}
if max(toks.values()) - min(toks.values()) > 2:
    problems.append(f'stance token spread too wide: {toks}')

# 4. no fabricated evidence: evidence conditions only exist when artifact present
for c in cond:
    if c['condition'].endswith('_evidence') and not c['condition'].endswith('_no_evidence') and not c.get('evidence_artifact'):
        problems.append(f'evidence condition without artifact: {c["id"]}')

# 5. ground truth never leaks into the prompt
for c in cond:
    p = prompt(c)
    for leak in ('resolved', 'ground_truth', 'patch_sha256', 'instance_id'):
        if leak in p: problems.append(f'{leak} leaked into prompt: {c["id"]}')

# 5b. no evidence-related wording may appear when no artifact is attached
for c in cond:
    if not c.get('evidence_artifact'):
        p = prompt(c)
        for cue in ('CI evidence', 'commit hashes', 'test names', 'EVIDENCE ARTIFACT'):
            if cue in p: problems.append(f'evidence cue {cue!r} without artifact: {c["id"]}')

# 6. issue-level dedup: no two selected rows may share normalized issue text
import hashlib
sig = collections.Counter(hashlib.sha256(r['issue'].strip().encode()).hexdigest() for r in sel)
dupes = [k for k, v in sig.items() if v > 1]
if dupes: problems.append(f'{len(dupes)} duplicate issues across selected patches')

# 7. parser regression: conflicting decisions must never silently pick one
import pilot as _p
cases = {
  '{"decision":"ACCEPT"} then {"decision":"ACCEPT"}': 'ACCEPT',
  'Example: {"decision":"ACCEPT"}\n\nMy actual decision:\n{"decision":"REJECT"}': 'AMBIGUOUS',
  'no json here': 'INVALID',
}
for text, want in cases.items():
    got = _p.parse_decision(text)
    if got != want: problems.append(f'parse_decision({text[:30]!r}) -> {got}, want {want}')

print(f'patches={len(sel)} conditions={len(cond)} stance_tokens={toks}')
if problems:
    print(f'FAIL ({len(problems)} problems)')
    for x in problems[:20]: print(' -', x)
else:
    print('OK: all invariants hold')
