"""G3-A task 12 — freeze manifest: sha256 every G3-A product, plus the
selection/gold/construct summary and the natural (unbalanced) label tally.
Read-only over evidence_store_g3a; never touches the frozen w21 store.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
OUT = G3A / 'g3a_freeze_manifest.json'

SKIP_DIRS = {'store'}  # hashed separately via provenance; exclude bulk blobs


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    files = []
    for p in sorted(G3A.rglob('*')):
        if not p.is_file():
            continue
        rel = p.relative_to(G3A).as_posix()
        if rel.split('/')[0] in SKIP_DIRS:
            continue
        # The manifest contains its own listing; exclude itself to avoid a
        # self-referential hash. Its identity is the freeze_id + file set.
        if p == OUT:
            continue
        files.append({'path': rel, 'bytes': p.stat().st_size,
                      'sha256': sha256_file(p)})

    golds = list(read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl')))
    oracle_dist = Counter(g['oracle_gold'] for g in golds)
    truth = list(read_jsonl(str(G3A / 'g3a_truth.jsonl')))
    acceptable_dist = Counter(
        ('acceptable' if t['merge_acceptable'] else 'not_acceptable')
        for t in truth)
    human = Counter(g['human_adjudication']['status'] for g in golds)

    manifest = {
        'freeze_id': 'groundedreview-gate3a-offline-frozen-2026-10-26',
        'gate': 'G3-A (independent issue construction & offline audit)',
        'api_budget_used_usd': 0.0,
        'paid_model_calls': 0,
        'n_independent_issues': len(golds),
        'issues': [g['instance_id'] for g in golds],
        'oracle_gold_distribution': dict(oracle_dist),
        'oracle_distribution_note':
            'Natural, unforced distribution: 7 ACCEPT / 3 REJECT / 0 NEED at '
            'the FULL-EVIDENCE oracle layer. NEED is not manufactured: with '
            'all channels linked/fresh/complete and symptoms resolved or '
            'acceptance failures present, no full-evidence cell is '
            'under-determined. NEED_EVIDENCE is expected to arise only as a '
            'CONDITION projection under restricted-evidence regimes in G3-B.',
        'acceptability_distribution': dict(acceptable_dist),
        'human_adjudication_distribution': dict(human),
        'human_adjudication_note':
            'All 10 are pending: only one independent annotator is '
            'available. Mechanical oracle consistency is reported separately '
            'and is NOT human inter-rater agreement.',
        'mirror_fixtures': 0,
        'targets_per_issue': 1,
        'label_balancing': 'none; labels were not forced into a 3-way balance',
        'file_count': len(files),
        'files': files,
    }
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    print('files:', len(files))
    print('oracle:', dict(oracle_dist))
    print('acceptability:', dict(acceptable_dist))
    print('human:', dict(human))
    print('->', OUT)


if __name__ == '__main__':
    main()
