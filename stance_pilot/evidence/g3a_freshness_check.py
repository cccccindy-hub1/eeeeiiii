"""G3-A — independent freshness/tree re-derivation (no pytest, $0).

For every built issue, re-stage the canonical (base_commit + candidate patch +
maintainer test_patch) triple FROM SCRATCH in the vendored repo, capture
`git write-tree`, and compare it to the tree stored in the signed attestation
at build time. This is an independent mechanical recomputation of the run-tree
identity that the freshness channel rests on; it does not look at any label.

Note (disclosed): the canonical artifact record produced by evidence.builder
carries outcomes but not a run_tree field; the run tree is attested via
git write-tree. This script verifies that the attested tree is the unique,
deterministic tree of the exact triple pytest executed against.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.phase2_build import (changed_files, scope_test_files,
                                   build_test_name_index, _write_tree,
                                   _git_retry, _apply_candidate,
                                   _apply_test_patch)
from evidence.schemas import sha256_text
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
STORE_ROOT = G3A / 'store'
RAW = G3A / 'raw' / 'g3a_target_rows.jsonl'
OUT = G3A / 'audit' / 'g3a_freshness_recompute.json'


def restage_tree(raw):
    _git_retry('checkout', '-f', raw['base_commit'])
    _git_retry('clean', '-fdq')
    _apply_candidate(raw)
    _apply_test_patch(raw)
    return _write_tree()


def main():
    store = ArtifactStore(str(STORE_ROOT),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    raws = {r['instance_id']: r for r in read_jsonl(str(RAW))}
    prior = _git_retry('rev-parse', 'HEAD').stdout.strip()
    out = []
    try:
        for iid in sorted(raws):
            raw = raws[iid]
            tree = restage_tree(raw)
            att = store.get_attestation(iid, sha256_text(raw['model_patch']))
            att_tree = att['expected_run_tree'] if att else None
            code_files = changed_files(raw['model_patch'], code_only=True)
            scope = scope_test_files(raw, code_files)
            idx = build_test_name_index(scope)
            p2p = [n for n in raw['PASS_TO_PASS'] if n in idx]
            out.append({
                'instance_id': iid,
                'recomputed_run_tree': tree,
                'attested_run_tree': att_tree,
                'attestation_authentic': bool(
                    att and att.get('_attestation_authentic')),
                'tree_matches': tree == att_tree,
                'f2p_n': len(raw['FAIL_TO_PASS']),
                'p2p_scoped_n': len(p2p),
                'p2p_full_dataset_n': len(raw['PASS_TO_PASS']),
            })
    finally:
        _git_retry('checkout', '-f', prior)
        _git_retry('clean', '-fdq')
    ok = all(x['tree_matches'] and x['attestation_authentic'] for x in out)
    payload = {'document': 'Independent git write-tree recomputation of the '
                           'canonical run triple per G3-A issue.',
               'all_match': ok, 'issues': out}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    for x in out:
        print(f"  {x['instance_id']}: tree_match={x['tree_matches']} "
              f"att_auth={x['attestation_authentic']} "
              f"f2p={x['f2p_n']} p2p_scoped={x['p2p_scoped_n']}/"
              f"{x['p2p_full_dataset_n']}")
    print('all_match =', ok, '->', OUT)


if __name__ == '__main__':
    main()
