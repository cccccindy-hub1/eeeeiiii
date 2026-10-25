"""Wave-2 empirical truth: build canonical signed artifacts for the 4 new issues.

Reuses evidence.builder.build_one unchanged (real 3.9+pytest8.4.2 executions),
pointing its probe lookup at evidence_store/probes_wave2 and writing truth to
the separate wave2_truth.jsonl. Canonical artifacts land in the shared store
under content-addressed art_* ids (new issues => no id can collide with the
frozen Wave-1 artifacts); every built target also gets a run-tree/coverage
attestation so Task-5 freshness/coverage mirrors stay server-checkable.

Labels derive solely from executed probe/pytest outcomes; no model output is
read anywhere.

Run:
  uv run --python 3.9 --with mpmath --with "pytest==8.4.2" \
      python -m evidence.wave2_truth
"""
from __future__ import annotations

import argparse, json
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.builder import build_one, git as builder_git
from evidence.phase2_build import (changed_files, scope_test_files,
                                   build_test_name_index, _write_tree,
                                   _git_retry)
from evidence.store import ArtifactStore
from evidence.builder import WORK

HERE = Path(__file__).resolve().parent.parent


def restage_attestation(store, raw):
    """Recreate the canonical run tree deterministically (base + candidate +
    maintainer test_patch) and store its signed attestation. Tree hash only,
    no pytest."""
    from evidence.phase2_build import _apply_candidate, _apply_test_patch
    from evidence.builder import now
    from evidence.schemas import sha256_text
    _git_retry('checkout', '-f', raw['base_commit'])
    _git_retry('clean', '-fdq')
    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    idx = build_test_name_index(scope_files)
    p2p_names = [n for n in raw['PASS_TO_PASS'] if n in idx]
    _apply_candidate(raw)
    _apply_test_patch(raw)
    canon_tree = _write_tree()
    store.put_attestation({
        'instance_id': raw['instance_id'],
        'patch_sha256': sha256_text(raw['model_patch']),
        'base_commit': raw['base_commit'],
        'expected_run_tree': canon_tree,
        'declared_fail_to_pass': list(raw['FAIL_TO_PASS']),
        'declared_p2p_scoped': list(p2p_names),
        'declared_scope_files': scope_files,
        'built_at': now(),
    })
    return canon_tree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='evidence_store/wave2_raw_rows.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--out', default='evidence_store/wave2_truth.jsonl')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    store = ArtifactStore(a.store)
    probe_dir = WORK / 'probes_wave2'
    probe_dir.mkdir(parents=True, exist_ok=True)

    def probe_lookup(iid):
        return (probe_dir / f'{iid}.py').read_text(encoding='utf-8')

    out_path = WORK / 'wave2_truth.jsonl'
    truths = list(read_jsonl(out_path)) if out_path.exists() else []
    done = {t['id'] for t in truths}
    rows = list(read_jsonl(a.raw))
    skipped = []

    try:
        for raw in rows:
            if raw['id'] in done and not a.force:
                continue
            truth, meta = build_one(raw, store, None, probe_dir, probe_lookup)
            if truth is None:
                skipped.append({'id': raw['id'], **meta})
                continue
            # restore the signed run-tree attestation build_one does not emit
            tree = restage_attestation(store, raw)
            truth['canon_run_tree'] = tree
            truths = [t for t in truths if t['id'] != truth['id']]
            truths.append(truth)
    finally:
        try:
            _git_retry('checkout', '-f',
                       '7121bdf1facdd90d05b6994b4c2e5b2865a4638a')
        except Exception:
            pass
        try:
            _git_retry('clean', '-fdq')
        except Exception:
            pass
        write_jsonl(str(out_path), truths)

    print(f'\nwave2 truth records: {len(truths)} -> {out_path}')
    by_inst = {}
    for t in truths:
        by_inst.setdefault(t['instance_id'], []).append(t)
    for iid, ts in sorted(by_inst.items()):
        goods = sum(1 for t in ts if t['merge_acceptable'])
        print(f"  {iid}: n={len(ts)} GOOD={goods} BAD={len(ts)-goods} "
              f"addressed={sum(1 for t in ts if t['issue_addressed'])}")
    for s in skipped:
        print('SKIPPED', s)
    print('skipped_n:', len(skipped))


if __name__ == '__main__':
    main()
