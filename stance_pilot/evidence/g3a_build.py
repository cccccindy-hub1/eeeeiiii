"""G3-A empirical build — replay the 10 newly selected issues with REAL local
pytest (no API, no external paid service; fully offline in the vendored repo).

Mirrors evidence/wave2_truth.py but isolates EVERYTHING G3-A:
  * artifacts/logs/signatures/attestations -> evidence_store_g3a/store/
  * probes read from evidence_store_g3a/probes (human-written)
  * truth -> evidence_store_g3a/g3a_truth.jsonl
The frozen evidence_store_w21 snapshot is never opened for writing.

Each selected issue has exactly ONE target patch (no mirrors); labels derive
solely from executed probe/pytest outcomes and are frozen before any model
prediction.

Run (offline):
  set GIT_NO_LAZY_FETCH=1
  uv run --python 3.9 --with mpmath --with "pytest==8.4.2" \
      --offline python -m evidence.g3a_build [--ids sympy__sympy-24443,...]
"""
from __future__ import annotations

import argparse
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.builder import build_one, git as builder_git
from evidence.phase2_build import (changed_files, scope_test_files,
                                   build_test_name_index, _write_tree,
                                   _git_retry, _apply_candidate,
                                   _apply_test_patch)
from evidence.builder import now
from evidence.schemas import sha256_text
from evidence.store import ArtifactStore

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
STORE_ROOT = G3A / 'store'
PROBE_DIR = G3A / 'probes'
RAW = G3A / 'raw' / 'g3a_target_rows.jsonl'
TRUTH = G3A / 'g3a_truth.jsonl'


def restage_attestation(store, raw):
    """Recreate canonical run tree (base + candidate + maintainer test_patch)
    deterministically and store a signed git write-tree attestation."""
    _git_retry('checkout', '-f', raw['base_commit'])
    _git_retry('clean', '-fdq')
    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    idx = build_test_name_index(scope_files)
    p2p_names = [n for n in raw['PASS_TO_PASS'] if n in idx]
    _apply_candidate(raw)
    _apply_test_patch(raw)
    tree = _write_tree()
    store.put_attestation({
        'instance_id': raw['instance_id'],
        'patch_sha256': sha256_text(raw['model_patch']),
        'base_commit': raw['base_commit'],
        'expected_run_tree': tree,
        'declared_fail_to_pass': list(raw['FAIL_TO_PASS']),
        'declared_p2p_scoped': list(p2p_names),
        'declared_scope_files': scope_files,
        'built_at': now(),
        'batch': 'G3-A'})
    return tree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', default='')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    store = ArtifactStore(str(STORE_ROOT),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    PROBE_DIR.mkdir(parents=True, exist_ok=True)

    def probe_lookup(iid):
        return (PROBE_DIR / f'{iid}.py').read_text(encoding='utf-8')

    prior = builder_git('rev-parse', 'HEAD').stdout.strip()
    rows = list(read_jsonl(str(RAW)))
    if a.ids:
        want = {i.strip() for i in a.ids.split(',') if i.strip()}
        rows = [r for r in rows if r['instance_id'] in want]

    truths = list(read_jsonl(str(TRUTH))) if TRUTH.exists() else []
    done = {t['id'] for t in truths}
    skipped = []
    try:
        for raw in rows:
            if raw['id'] in done and not a.force:
                continue
            truth, meta = build_one(raw, store, None, PROBE_DIR, probe_lookup)
            if truth is None:
                skipped.append({'id': raw['id'], **meta})
                continue
            truth['canon_run_tree'] = restage_attestation(store, raw)
            truths = [t for t in truths if t['id'] != truth['id']]
            truths.append(truth)
    finally:
        try:
            _git_retry('checkout', '-f', prior)
        except Exception:
            pass
        try:
            _git_retry('clean', '-fdq')
        except Exception:
            pass
        write_jsonl(str(TRUTH), truths)

    print(f'\nG3-A truth records: {len(truths)} -> {TRUTH}')
    for t in sorted(truths, key=lambda x: x['instance_id']):
        print(f"  {t['instance_id']}: class={t['label_class']} "
              f"addressed={t['issue_addressed']} "
              f"acceptable={t['merge_acceptable']} tree={t.get('canon_run_tree','')[:10]}")
    for s in skipped:
        print('SKIPPED', s)


if __name__ == '__main__':
    main()
