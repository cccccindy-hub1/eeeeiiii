"""G3-C.1 task 5 (part 1) — independent freshness/tree re-derivation, $0.

For every built G3-C.1 pilot issue, independently re-stage the canonical triple
(base_commit + candidate model_patch + maintainer test_patch) FROM SCRATCH in
the vendored repo, capture ``git write-tree``, and compare it to the tree held
by the signed attestation captured at build time. This is a mechanical
re-derivation of run-tree identity; it never reads a label or a model output.

Output (canonical JSON) -> audit/g3c1_freshness_recompute.json, with the same
shape as the frozen G3-A recomputation so it can be fed straight into the
frozen three-state ``g3b2_freshness.adjudicate_freshness``:

    {all_match, issues: [{instance_id, recomputed_run_tree, attested_run_tree,
                          attestation_authentic, tree_matches, f2p_n,
                          p2p_scoped_n, p2p_full_dataset_n}]}

Must NOT run concurrently with g3c1_build (both drive the vendored git tree).

  set GIT_NO_LAZY_FETCH=1
  uv run --offline --python 3.9 -m evidence.g3c1_freshness
"""
from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

from evidence import g3c1_common as C
from evidence.builder import git, changed_files, scope_test_files, build_test_name_index
from evidence.schemas import sha256_text
from evidence.store import ArtifactStore
from evidence.g3c1_build import (_git_retry, _write_tree, _apply_candidate,
                                 _apply_test_patch)

OUT = C.OUT_AUDIT / 'g3c1_freshness_recompute.json'


def restage_tree(raw) -> str:
    _git_retry('checkout', '-f', raw['base_commit'])
    _git_retry('clean', '-fdq')
    applied, err = _apply_candidate(raw)
    if not applied:
        raise RuntimeError('restage candidate apply failed: ' + err[:300])
    _apply_test_patch(raw)
    return _write_tree()


def load_restage_cache(path=None) -> dict:
    """{instance_id: issue_dict} from the G3-C.1 independent recomputation."""
    path = path or OUT
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    return {x['instance_id']: x for x in payload.get('issues', [])}


def main():
    C.ensure_out_dirs()
    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')
    raws = {r['instance_id']: r for r in C.read_jsonl(
        C.OUT_RAW / 'g3c1_target_rows.jsonl')}
    prior = _git_retry('rev-parse', 'HEAD').stdout.strip()
    issues = []
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
            issues.append({
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

    ok = all(x['tree_matches'] and x['attestation_authentic'] for x in issues)
    payload = {
        'document': 'G3-C.1 independent git write-tree recomputation of the '
                    'canonical run triple (base + candidate + maintainer '
                    'test_patch) per pilot issue.',
        'design_version': C.G3C1_DESIGN_VERSION,
        'all_match': ok,
        'n_issues': len(issues),
        'issues': issues,
    }
    C.write_canonical(OUT, payload)
    for x in issues:
        print(f"  {x['instance_id']}: tree_match={x['tree_matches']} "
              f"att_auth={x['attestation_authentic']} "
              f"f2p={x['f2p_n']} p2p_scoped={x['p2p_scoped_n']}/"
              f"{x['p2p_full_dataset_n']}")
    print('all_match =', ok, '->', OUT)


if __name__ == '__main__':
    main()
