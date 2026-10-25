"""Build Phase-2 evidence-integrity fixtures with REAL git/pytest executions.

Five scenarios per review target (a served candidate patch):

  valid         canonical run; linked, fresh, complete, claim consistent
  wrong_patch   a DIFFERENT patch's signed artifact is re-identified as the served
                patch -> linked=false (detectable by linkage only)
  stale         linked=true (same patch hash) but executed against a different
                commit TREE -> fresh=false. The tree delta is an inert, comment-only
                documentation blob so Python execution is unaffected, but the run is
                genuinely about another tree and its logs are produced on that tree.
  incomplete    only a SUBSET of declared acceptance tests is executed and NO scoped
                regression check is run; the omitted acceptance test is the failing
                one, so the record looks green while coverage is incomplete.
  contradictory linked/fresh/complete, but the positive author claim contradicts the
                real logs (a failing acceptance check) -> consistency=false.

Ground-truth expectations are captured from real artefacts (git write-tree, declared
test sets) and stored in attestations; scenario labels live only in the plan file /
fixtures_meta.json and never enter a prompt. Phase-1 artifacts and results are never
modified: generated fixtures use a separate `fix_*` id namespace via put_fixture().

Only stale/incomplete perform new pytest runs. valid/contradictory reuse the genuine
canonical Phase-1 artifact (zero extra test execution); wrong_patch re-identifies an
existing canonical artifact. Every entry still gets a real canonical-tree attestation.

Run (choose interpreter per instance vintage, like evidence.builder):
  uv run --python 3.11 --with mpmath --with pytest python -m evidence.phase2_build \
      --plan evidence_store/phase2_plan.json
"""
from __future__ import annotations

import argparse, copy, json, os, sys
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.builder import (REPO, WORK, git, now, write_patch, changed_files,
                              scope_test_files, build_test_name_index,
                              map_names_to_files, run_pytest_files, parse_node_logs,
                              name_outcomes, fails, passes, run_probe)
from evidence.probes import probe_source
from evidence.schemas import (SCHEMA_VERSION, make_artifact_id, sha256_text)
from evidence.store import ArtifactStore

# probe/pytest subprocesses must not litter the repo with __pycache__ (which would
# otherwise be staged into captured run trees).
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

# Inert documentation comment: changes `git write-tree` without any possibility of
# affecting Python test execution.
STALE_MARKER_FILE = 'README.rst'
STALE_MARKER_LINE = '.. phase2-stale-run-tree-marker (inert comment; do not edit)'

POSITIVE_CLAIM = ('Author statement: I changed the code shown in the patch. This fix '
                  'is fully correct and all relevant tests pass.')

EXPECTED = {
    'valid':         dict(linked=True,  fresh=True,  complete=True,  consistent=True),
    'wrong_patch':   dict(linked=False, fresh=False, complete=True,  consistent=True),
    'stale':         dict(linked=True,  fresh=False, complete=True,  consistent=True),
    'incomplete':    dict(linked=True,  fresh=True,  complete=False, consistent=True),
    'contradictory': dict(linked=True,  fresh=True,  complete=True,  consistent=False),
}

DEFAULT_PLAN = [
    {'scenario': 'valid',         'sample': 'glm5_500:sympy__sympy-16450'},
    {'scenario': 'contradictory', 'sample': 'glm5_500:sympy__sympy-18199'},
    {'scenario': 'incomplete',    'sample': 'qwen3_30b_instruct2507_500:sympy__sympy-17139'},
    {'scenario': 'stale',         'sample': 'glm5_500:sympy__sympy-18211'},
    {'scenario': 'wrong_patch',   'sample': 'qwen3_30b_instruct2507_500:sympy__sympy-18211',
     'source': 'glm5_500:sympy__sympy-18211'},
]


def _git_retry(*args, tries=4, delay=2.0):
    """Windows occasionally fails `git checkout` with EPERM 'unable to unlink old'
    when an indexer/AV briefly holds a file; retry the identical command."""
    import time as _t
    last = None
    for k in range(tries):
        p = git(*args, check=False)
        if p.returncode == 0:
            return p
        last = p
        _t.sleep(delay * (k + 1))
    raise RuntimeError(f'git {args} failed after {tries} tries:\n'
                       f'{p.stdout}\n{p.stderr}')


def _write_tree() -> str:
    git('add', '-A')
    return git('write-tree').stdout.strip()


def _apply_candidate(raw):
    cand = WORK / 'patches' / f"{raw['id'].replace(':', '__')}.patch"
    write_patch(cand, raw['model_patch'])
    ap = git('apply', '--whitespace=nowarn', str(cand.resolve()), check=False)
    if ap.returncode != 0:
        raise RuntimeError('candidate patch failed: ' + ap.stderr[:300])


def _apply_test_patch(raw):
    """Reset test_patch files to base (candidate may have edited them), then apply
    the maintainer version. Mirrors evidence.builder."""
    tp = WORK / 'patches' / f"{raw['instance_id']}.test_patch.patch"
    write_patch(tp, raw['test_patch'])
    tp_files = [l[6:] for l in raw['test_patch'].splitlines() if l.startswith('+++ b/')]
    if tp_files:
        git('checkout', raw['base_commit'], '--', *tp_files)
    r = git('apply', '--whitespace=nowarn', str(tp.resolve()), check=False)
    return r.returncode == 0


def stage(raw, store, probe_dir, attest: bool = True):
    """Clean checkout -> probes (before/after candidate) -> maintainer test_patch ->
    canonical write-tree + scope maps. No acceptance pytest is executed here."""
    iid = raw['instance_id']
    _git_retry('checkout', '-f', raw['base_commit'])
    git('clean', '-fdq')

    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)

    probe_path = probe_dir / f'{iid}.py'
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    with open(probe_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(probe_source(iid))
    pre_ok, pre_log = run_probe('probe', probe_path)

    _apply_candidate(raw)
    post_ok, post_log = run_probe('probe', probe_path)
    _apply_test_patch(raw)

    idx = build_test_name_index(scope_files)
    p2p_names = [n for n in raw['PASS_TO_PASS'] if n in idx]
    canon_tree = _write_tree()
    patch_sha = sha256_text(raw['model_patch'])
    if attest:
        store.put_attestation({
            'instance_id': iid,
            'patch_sha256': patch_sha,
            'base_commit': raw['base_commit'],
            'expected_run_tree': canon_tree,
            'declared_fail_to_pass': list(raw['FAIL_TO_PASS']),
            'declared_p2p_scoped': list(p2p_names),
            'declared_scope_files': scope_files,
            'built_at': now(),
        })
    symptom_log = ('### BASELINE (pre-patch)\n' + pre_log +
                   '\n\n### POST candidate patch\n' + post_log)
    return {
        'scope_files': scope_files, 'idx': idx, 'p2p_names': p2p_names,
        'canon_tree': canon_tree, 'patch_sha': patch_sha,
        'tp_sha': sha256_text(raw['test_patch']),
        'pre_ok': pre_ok, 'post_ok': post_ok, 'symptom_log': symptom_log,
    }


def _execute_batched(run_files, label):
    logs = []
    for i in range(0, len(run_files), 3):
        log, _ = run_pytest_files(run_files[i:i + 3], label)
        logs.append(log)
    return '\n\n'.join(logs), parse_node_logs(logs)


def fixture_id(scenario, instance_id, patch_sha):
    return 'fix_' + scenario + '_' + make_artifact_id(instance_id, patch_sha)[4:]


def make_record(*, scenario, raw, patch_sha, test_patch_sha, started, scope_files,
                f2p_outcomes, p2p_outcomes, f2p_log, p2p_log, symptom_log, run_tree):
    return {
        'artifact_id': fixture_id(scenario, raw['instance_id'], patch_sha),
        'schema_version': SCHEMA_VERSION,
        'phase2_scenario': scenario,
        'instance_id': raw['instance_id'], 'repo': raw['repo'],
        'base_commit': raw['base_commit'], 'patch_sha256': patch_sha,
        'test_patch_sha256': test_patch_sha,
        # runner/rule are deliberately scenario-neutral: the scenario must be
        # discoverable only via its integrity surface, never from record strings.
        # (The display layer sanitises older records too; this keeps new builds
        # clean at rest. f2p/p2p executed counts still truthfully describe THIS
        # run; tier D substitutes the attested DECLARED counts at serve time.)
        'runner': f'pytest/vendored-git py={sys.version.split()[0]} host=windows-local',
        'started_at': started, 'finished_at': now(), 'run_tree': run_tree,
        'scope': {
            'rule': 'F2P all; P2P scoped to test_patch files and tests/ adjacent '
                    'to each changed code file',
            'p2p_scoped_files': scope_files,
            'p2p_total_in_dataset': len(raw['PASS_TO_PASS']),
            'test_patch_applied_cleanly': True,
        },
        'fail_to_pass': f2p_outcomes,
        'pass_to_pass_scoped': p2p_outcomes,
        'summary': {
            'f2p_total': len(f2p_outcomes),
            'f2p_passed': len(passes(f2p_outcomes)),
            'f2p_failed_ids': fails(f2p_outcomes),
            'p2p_total': len(p2p_outcomes),
            'p2p_passed': len(passes(p2p_outcomes)),
            'p2p_regressed_ids': [],
            'p2p_preexisting_bad_ids': [],
        },
        'log_digests': {
            'f2p': sha256_text(f2p_log),
            'p2p': sha256_text(p2p_log),
            'symptom': sha256_text(symptom_log),
        },
    }


def build_stale(store, raw, ctx):
    """Full declared F2P+P2P execution on a tree that differs from canonical by one
    inert documentation comment -> complete & consistent, but NOT fresh."""
    p = REPO / STALE_MARKER_FILE
    if not p.exists():
        raise RuntimeError(f'{STALE_MARKER_FILE} missing at {raw["base_commit"]}')
    with open(p, 'a', encoding='utf-8', newline='') as fh:
        fh.write('\n' + STALE_MARKER_LINE + '\n')
    run_tree = _write_tree()
    assert run_tree != ctx['canon_tree']

    f2p_map = map_names_to_files(list(raw['FAIL_TO_PASS']), ctx['scope_files'], ctx['idx'])
    p2p_map = map_names_to_files(ctx['p2p_names'], ctx['scope_files'], ctx['idx'])
    run_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    started = now()
    log, node_status = _execute_batched(run_files, 'stale')
    f2p = name_outcomes(list(raw['FAIL_TO_PASS']), f2p_map, node_status)
    p2p = name_outcomes(ctx['p2p_names'], p2p_map, node_status)
    rec = make_record(scenario='stale', raw=raw, patch_sha=ctx['patch_sha'],
                      test_patch_sha=ctx['tp_sha'], started=started,
                      scope_files=ctx['scope_files'], f2p_outcomes=f2p,
                      p2p_outcomes=p2p, f2p_log=log, p2p_log=log,
                      symptom_log=ctx['symptom_log'], run_tree=run_tree)
    store.put_fixture(rec, logs={'f2p': log, 'p2p': log,
                                  'symptom': ctx['symptom_log']},
                      meta={'scenario': 'stale', 'canon_tree': ctx['canon_tree'],
                            'run_tree': run_tree,
                            'tree_delta': f'inert comment appended to {STALE_MARKER_FILE}'})
    return rec


def build_incomplete(store, raw, ctx):
    """Read the genuine canonical outcomes, keep only PASSING declared F2P tests, and
    re-execute JUST their defining files on the canonical tree. The failing declared
    acceptance test is omitted and no P2P check is run -> fresh & linked, incomplete."""
    canon_aid = make_artifact_id(raw['instance_id'], ctx['patch_sha'])
    got = ArtifactStore(str(WORK)).get(canon_aid)
    if got is None:
        raise RuntimeError(f'canonical artifact missing: {canon_aid}; run builder first')
    canon, _ = got
    kept = [n for n, s in canon['fail_to_pass'].items()
            if s in ('PASSED', 'XFAIL', 'SKIPPED')]
    omitted = [n for n in raw['FAIL_TO_PASS'] if n not in kept]
    if not kept or not omitted:
        raise RuntimeError('incomplete fixture needs >=1 passing AND >=1 failing '
                           f'declared F2P test; kept={kept} omitted={omitted}')
    keep_map = map_names_to_files(kept, ctx['scope_files'], ctx['idx'])
    keep_files = sorted(set(sum(keep_map.values(), [])))
    started = now()
    log, node_status = _execute_batched(keep_files, 'incomplete')
    f2p = name_outcomes(kept, keep_map, node_status)
    empty = '(no scoped regression checks were executed for this run)'
    rec = make_record(scenario='incomplete', raw=raw, patch_sha=ctx['patch_sha'],
                      test_patch_sha=ctx['tp_sha'], started=started,
                      scope_files=keep_files, f2p_outcomes=f2p, p2p_outcomes={},
                      f2p_log=log, p2p_log=empty,
                      symptom_log=ctx['symptom_log'], run_tree=ctx['canon_tree'])
    store.put_fixture(rec, logs={'f2p': log, 'p2p': empty,
                                  'symptom': ctx['symptom_log']},
                      meta={'scenario': 'incomplete', 'executed_f2p': kept,
                            'omitted_f2p': omitted, 'executed_p2p': []})
    return rec


def copy_canonical_fixture(store, scenario, raw, ctx, extra_meta=None):
    """Copy the genuine canonical Phase-1 artifact into the fix_ namespace, stamping
    the REAL canonical run tree (captured here via git write-tree) so freshness is
    server-checkable. Outcomes/logs are untouched."""
    canon_aid = make_artifact_id(raw['instance_id'], ctx['patch_sha'])
    src_store = ArtifactStore(str(WORK))
    got = src_store.get(canon_aid)
    if got is None:
        raise RuntimeError(f'canonical artifact missing: {canon_aid}')
    rec = copy.deepcopy(got[0])
    rec['artifact_id'] = fixture_id(scenario, raw['instance_id'], ctx['patch_sha'])
    rec['phase2_scenario'] = scenario
    rec['run_tree'] = ctx['canon_tree']
    logs = {}
    for name in rec['log_digests']:
        lp = src_store.root / 'logs' / f'{canon_aid}.{name}.log'
        if lp.exists():
            logs[name] = lp.read_text(encoding='utf-8')
    meta = {'scenario': scenario, 'source_artifact_id': canon_aid}
    if extra_meta:
        meta.update(extra_meta)
    store.put_fixture(rec, logs=logs, meta=meta)
    return rec


def build_wrong_patch(store, raw_served, ctx_served, raw_source, ctx_source):
    """Serve the SOURCE patch's genuine canonical artifact under a fix_ id for the
    served patch. The record keeps the source base/hash/run_tree, so linkage against
    the served patch fails; everything else (coverage/consistency) is genuine."""
    src_sha = ctx_source['patch_sha']
    src_aid = make_artifact_id(raw_source['instance_id'], src_sha)
    src_store = ArtifactStore(str(WORK))
    got = src_store.get(src_aid)
    if got is None:
        raise RuntimeError(f'source canonical artifact missing: {src_aid}')
    rec = copy.deepcopy(got[0])
    rec['artifact_id'] = fixture_id('wrong_patch', raw_served['instance_id'],
                                    ctx_served['patch_sha'])
    rec['phase2_scenario'] = 'wrong_patch'
    rec['run_tree'] = ctx_source['canon_tree']
    logs = {}
    for name in rec['log_digests']:
        lp = src_store.root / 'logs' / f'{src_aid}.{name}.log'
        if lp.exists():
            logs[name] = lp.read_text(encoding='utf-8')
    store.put_fixture(rec, logs=logs,
                      meta={'scenario': 'wrong_patch',
                            'served_id': raw_served['id'],
                            'source_artifact_id': src_aid,
                            'source_id': raw_source['id'],
                            'source_patch_sha256': src_sha})
    return rec


def build_entry(store, raw_by_id, truth_by_id, probe_dir, e):
    scenario = e['scenario']
    served = raw_by_id[e['sample']]
    print(f'== {scenario:13s} served={e["sample"]}')

    ctx_served = stage(served, store, probe_dir)
    ctx_source = None
    served_aid = None
    if scenario in ('valid', 'contradictory'):
        served_aid = copy_canonical_fixture(store, scenario, served, ctx_served)['artifact_id']
    elif scenario == 'stale':
        served_aid = build_stale(store, served, ctx_served)['artifact_id']
    elif scenario == 'incomplete':
        served_aid = build_incomplete(store, served, ctx_served)['artifact_id']
    elif scenario == 'wrong_patch':
        source = raw_by_id[e['source']]
        ctx_source = stage(source, store, probe_dir, attest=False)
        served_aid = build_wrong_patch(store, served, ctx_served, source, ctx_source)['artifact_id']
    else:
        raise ValueError(scenario)

    tr = truth_by_id.get(served['id'], {})
    lp = tr.get('label_provenance', {})
    row = {
        'scenario': scenario,
        'id': served['id'], 'instance_id': served['instance_id'],
        'repo': served['repo'], 'base_commit': served['base_commit'],
        'patch_sha256': ctx_served['patch_sha'], 'served_artifact_id': served_aid,
        'label_class': tr.get('label_class'),
        'merge_acceptable': tr.get('merge_acceptable'),
        'symptom': {
            'pre_patch_passed': lp.get('symptom_pre_patch_passed', ctx_served['pre_ok']),
            'post_patch_passed': lp.get('symptom_post_patch_passed', ctx_served['post_ok']),
        },
        'claim': POSITIVE_CLAIM,
        'expected': EXPECTED[scenario],
        'canon_tree': ctx_served['canon_tree'],
    }
    if scenario == 'wrong_patch':
        row['source'] = e['source']
    _git_retry('checkout', '-f', 'HEAD')
    git('clean', '-fdq', check=False)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--truth', default='evidence_store/truth.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--plan', default='evidence_store/phase2_plan.json')
    ap.add_argument('--plan-json', default='')
    a = ap.parse_args()

    global WORK
    WORK = Path(a.store)
    entries = (json.loads(a.plan_json) if a.plan_json
               else (list(read_jsonl(a.plan)) if Path(a.plan).exists() else DEFAULT_PLAN))
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    truth_by_id = {r['id']: r for r in read_jsonl(a.truth)}
    store = ArtifactStore(a.store)
    probe_dir = WORK / 'probes_phase2'
    rows = []
    try:
        for e in entries:
            rows.append(build_entry(store, raw_by_id, truth_by_id, probe_dir, dict(e)))
    finally:
        try:
            _git_retry('checkout', '-f', 'HEAD')
        except Exception:
            pass
        git('clean', '-fdq', check=False)
    out = WORK / 'phase2_fixtures.jsonl'
    write_jsonl(out, rows)
    print(f'\nwrote {len(rows)} fixture rows -> {out}')
    for r in rows:
        print(f"  {r['scenario']:13s} {r['id']:48s} aid={r['served_artifact_id']}")


if __name__ == '__main__':
    main()
