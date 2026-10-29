"""G3-C.1 task 4 — REAL local maintainer/candidate patch replay with pytest,
zero API. Self-contained orchestration for the <=8 brand-new pilot issues.

This deliberately does NOT reuse evidence.builder.build_one, because that
function hard-codes its temp patch directory to the FROZEN evidence_store tree;
Gate G3-C.1 may write only evidence_store_g3c1/. The pure, frozen builder
helpers (git/checkout probing, pytest execution, node-log parsing, name->file
mapping) are imported and reused unchanged; only the orchestration and output
paths are G3-C.1-local.

Per issue (identical protocol to the frozen G3-A build):
  1. clean checkout of base_commit (git checkout -f + clean -fdq);
  2. human symptom probe at BASELINE -> must FAIL (symptom exists);
  3. baseline scoped PASS_TO_PASS pytest pass (environment truth, no patches);
  4. apply ONLY the candidate model_patch (patches written under g3c1/patches);
  5. symptom probe AFTER candidate -> must PASS (issue addressed);
  6. reset test_patch files to base, apply the maintainer test_patch
     (--reject fallback recorded honestly, never silently dropped);
  7. run every FAIL_TO_PASS plus scoped PASS_TO_PASS (3 files/batch, -v);
  8. signed artifact + raw logs -> evidence_store_g3c1/store;
  9. independently restage base+candidate+test_patch and capture a signed
     git write-tree attestation (freshness authority); truth gets canon tree.

A candidate that no longer applies, or a baseline probe that does not fail, is
a pre-registered STOP condition: record g3c1_failures.jsonl and halt (no
replacement, no skipping ahead). The vendored repo is restored to its prior
HEAD in the finally block.

  set GIT_NO_LAZY_FETCH=1
  uv run --offline --python 3.9 --with mpmath --with "pytest==8.4.2" \
      -m evidence.g3c1_build [--ids sympy__sympy-16886,...] [--force]
"""
from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

from evidence import g3c1_common as C
from evidence.builder import (git, now, changed_files, scope_test_files,
                              build_test_name_index, map_names_to_files,
                              run_pytest_files, parse_node_logs,
                              name_outcomes, fails, passes, run_probe, BAD)
from evidence.schemas import (SCHEMA_VERSION, classify, make_artifact_id,
                              sha256_text)
from evidence.store import ArtifactStore

ROWS = C.OUT_RAW / 'g3c1_target_rows.jsonl'
RUNLOG = C.OUT_RUNS / 'g3c1_build.log'
BATCH = 3


def _log(msg, fh):
    print(msg, flush=True)
    fh.write(msg + '\n')
    fh.flush()


def _git_retry(*args, tries=4, delay=2.0):
    last = None
    for k in range(tries):
        p = git(*args, check=False)
        if p.returncode == 0:
            return p
        last = p
        time.sleep(delay * (k + 1))
    raise RuntimeError(f'git {args} failed after {tries} tries:\n'
                       f'{last.stdout}\n{last.stderr}')


def _write_tree():
    git('add', '-A')
    return git('write-tree').stdout.strip()


def _write_patch(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


def _apply_candidate(raw):
    p = C.OUT_PATCHES / (raw['id'].replace(':', '__') + '.patch')
    _write_patch(p, raw['model_patch'])
    r = git('apply', '--whitespace=nowarn', str(p.resolve()), check=False)
    return r.returncode == 0, (r.stdout + r.stderr)


def _apply_test_patch(raw):
    p = C.OUT_PATCHES / (raw['instance_id'] + '.test_patch.patch')
    _write_patch(p, raw['test_patch'])
    tp_files = [l[6:] for l in raw['test_patch'].splitlines()
                if l.startswith('+++ b/')]
    if tp_files:
        git('checkout', raw['base_commit'], '--', *tp_files)
    r = git('apply', '--whitespace=nowarn', str(p.resolve()), check=False)
    clean = r.returncode == 0
    if not clean:
        git('apply', '--reject', '--whitespace=nowarn', str(p.resolve()),
            check=False)
    return clean


def _batched(run_files):
    logs = []
    for i in range(0, len(run_files), BATCH):
        log, _ = run_pytest_files(run_files[i:i + BATCH], 'tests')
        logs.append(log)
    return logs


def restage_attestation(store, raw):
    """Independent canonical run tree = base + candidate + maintainer test_patch."""
    _git_retry('checkout', '-f', raw['base_commit'])
    git('clean', '-fdq')
    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    idx = build_test_name_index(scope_files)
    p2p_names = [n for n in raw['PASS_TO_PASS'] if n in idx]
    applied, err = _apply_candidate(raw)
    if not applied:
        raise RuntimeError('restage candidate apply failed: ' + err[:300])
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
        'batch': 'G3-C.1'})
    return tree


def build_one(raw, store, fh):
    iid = raw['instance_id']
    patch_sha = sha256_text(raw['model_patch'])
    test_patch_sha = sha256_text(raw['test_patch'])
    _log(f'== {iid}  base={raw["base_commit"][:10]} patch={patch_sha[:10]}', fh)

    _git_retry('checkout', '-f', raw['base_commit'])
    git('clean', '-fdq')

    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    name_index = build_test_name_index(scope_files)
    p2p_in_scope = [n for n in raw['PASS_TO_PASS'] if n in name_index]
    p2p_map = map_names_to_files(p2p_in_scope, scope_files, name_index)

    probe = C.OUT_PROBES / f'{iid}.py'
    if not probe.exists():
        C.record_failure('build', iid, {'reason': 'probe_file_missing'})
        raise SystemExit(f'STOP: probe missing for {iid}')

    pre_ok, pre_log = run_probe(iid + '-baseline', probe)
    if pre_ok:
        C.record_failure('build', iid, {
            'reason': 'baseline symptom probe passed (symptom absent)',
            'baseline_log_tail': pre_log[-2000:]})
        raise SystemExit(f'STOP: baseline probe passed for {iid}')

    started = now()
    base_run_files = sorted(set(sum(p2p_map.values(), [])))
    _log(f'   baseline scoped P2P files={len(base_run_files)} '
         f'names={len(p2p_in_scope)}', fh)
    base_logs = _batched(base_run_files)
    base_status = parse_node_logs(base_logs)
    p2p_baseline_outcomes = name_outcomes(p2p_in_scope, p2p_map, base_status)
    p2p_baseline_log = '\n\n'.join(base_logs)

    applied, ap_err = _apply_candidate(raw)
    if not applied:
        C.record_failure('build', iid, {
            'reason': 'candidate patch did not apply',
            'apply_error_tail': ap_err[-2000:]})
        raise SystemExit(f'STOP: candidate apply failed for {iid}')

    post_ok, post_log = run_probe(iid + '-post-candidate', probe)
    issue_addressed = (not pre_ok) and post_ok
    if not issue_addressed:
        C.record_failure('build', iid, {
            'reason': 'candidate did not remove symptom (post probe failed)',
            'post_log_tail': post_log[-2000:]})
        raise SystemExit(f'STOP: post-candidate probe failed for {iid}')

    tp_clean = _apply_test_patch(raw)

    name_index = build_test_name_index(scope_files)
    f2p_map = map_names_to_files(raw['FAIL_TO_PASS'], scope_files, name_index)
    p2p_map = map_names_to_files(p2p_in_scope, scope_files, name_index)
    run_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    _log(f'   acceptance run files={len(run_files)} f2p={len(f2p_map)} '
         f'p2p={len(p2p_map)} test_patch_clean={tp_clean}', fh)
    logs = _batched(run_files)
    node_status = parse_node_logs(logs)
    f2p_outcomes = name_outcomes(raw['FAIL_TO_PASS'], f2p_map, node_status)
    p2p_outcomes = name_outcomes(p2p_in_scope, p2p_map, node_status)
    f2p_log_all = p2p_log_all = '\n\n'.join(logs)
    finished = now()

    f2p_failed = fails(f2p_outcomes)
    p2p_regressed = sorted(
        n for n, s in p2p_outcomes.items()
        if s in BAD and p2p_baseline_outcomes.get(n)
        in ('PASSED', 'XFAIL', 'SKIPPED')
        and p2p_baseline_outcomes.get(n) not in BAD)
    p2p_preexisting_bad = sorted(
        n for n, s in p2p_outcomes.items()
        if s in BAD and n not in p2p_regressed)
    merge_acceptable = not f2p_failed and not p2p_regressed
    regression_free = not p2p_regressed
    label = classify(issue_addressed, merge_acceptable)

    symptom_log = ('### BASELINE (pre-patch)\n' + pre_log +
                   '\n\n### POST candidate patch\n' + post_log)

    aid = make_artifact_id(iid, patch_sha)
    rec = {
        'artifact_id': aid, 'schema_version': SCHEMA_VERSION,
        'instance_id': iid, 'repo': raw['repo'],
        'base_commit': raw['base_commit'], 'patch_sha256': patch_sha,
        'test_patch_sha256': test_patch_sha,
        'runner': f'pytest/vendored-git  py={sys.version.split()[0]}  '
                  f'host=windows-local  gate=G3-C.1',
        'started_at': started, 'finished_at': finished,
        'scope': {
            'rule': 'F2P all; P2P scoped to test_patch files and tests/ '
                    'adjacent to each changed code file',
            'p2p_scoped_files': scope_files,
            'p2p_total_in_dataset': len(raw['PASS_TO_PASS']),
            'test_patch_applied_cleanly': tp_clean,
        },
        'fail_to_pass': f2p_outcomes,
        'pass_to_pass_scoped': p2p_outcomes,
        'pass_to_pass_baseline': p2p_baseline_outcomes,
        'summary': {
            'f2p_total': len(f2p_outcomes),
            'f2p_passed': len(passes(f2p_outcomes)),
            'f2p_failed_ids': f2p_failed,
            'p2p_total': len(p2p_outcomes),
            'p2p_passed': len(passes(p2p_outcomes)),
            'p2p_regressed_ids': p2p_regressed,
            'p2p_preexisting_bad_ids': p2p_preexisting_bad,
        },
        'log_digests': {
            'f2p': sha256_text(f2p_log_all),
            'p2p': sha256_text(p2p_log_all),
            'p2p_baseline': sha256_text(p2p_baseline_log),
            'symptom': sha256_text(symptom_log),
        },
    }
    store.put(rec, logs={'f2p': f2p_log_all, 'p2p': p2p_log_all,
                        'p2p_baseline': p2p_baseline_log,
                        'symptom': symptom_log})

    truth = {
        'id': raw['id'], 'instance_id': iid, 'repo': raw['repo'],
        'base_commit': raw['base_commit'], 'patch_sha256': patch_sha,
        'artifact_id': aid,
        'issue_addressed': issue_addressed,
        'regression_free_scoped': regression_free,
        'merge_acceptable': merge_acceptable,
        'label_class': label,
        'resolved_in_dataset': raw['resolved'],
        'label_provenance': {
            'symptom_pre_patch_passed': pre_ok,
            'symptom_post_patch_passed': post_ok,
            'f2p_total': len(f2p_outcomes), 'f2p_failed': len(f2p_failed),
            'p2p_scoped_total': len(p2p_outcomes),
            'p2p_regressed': len(p2p_regressed),
            'p2p_preexisting_bad': len(p2p_preexisting_bad),
            'test_patch_applied_cleanly': tp_clean,
            'built_at': now(),
        },
    }
    _log(f"   class={label} addressed={issue_addressed} "
         f"F2P {len(f2p_outcomes)-len(f2p_failed)}/{len(f2p_outcomes)} "
         f"P2P-regressed {len(p2p_regressed)} "
         f"(preexisting-bad {len(p2p_preexisting_bad)}) "
         f"test_patch_clean={tp_clean}", fh)
    return truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ids', default='')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    C.ensure_out_dirs()
    import json
    target_digest = json.loads(
        (C.OUT_RAW / 'g3c1_target_digest.json').read_text(encoding='utf-8'))

    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')
    rows = C.read_jsonl(ROWS)
    if a.ids:
        want = {i.strip() for i in a.ids.split(',') if i.strip()}
        rows = [r for r in rows if r['instance_id'] in want]
    rows = sorted(rows, key=lambda r: r['instance_id'])

    truths = C.read_jsonl(C.TRUTH)
    done = {t['id'] for t in truths}

    prior = git('rev-parse', 'HEAD').stdout.strip()
    fh = open(RUNLOG, 'a', encoding='utf-8')
    _log(f'### g3c1_build session start {now()} prior_head={prior}', fh)
    try:
        for raw in rows:
            if raw['id'] in done and not a.force:
                _log(f'== {raw["instance_id"]} already built; skip', fh)
                continue
            truth = build_one(raw, store, fh)
            truth['canon_run_tree'] = restage_attestation(store, raw)
            truth['pilot_queue_label'] = target_digest[
                raw['instance_id']]['pilot_queue_label']
            truth['primary_stratum'] = target_digest[
                raw['instance_id']]['primary_stratum']
            truths = [t for t in truths if t['id'] != truth['id']]
            truths.append(truth)
            C.write_jsonl(C.TRUTH, sorted(truths, key=lambda t: t['id']))
            # leave the working tree neutral between issues
            _git_retry('checkout', '-f', prior)
            git('clean', '-fdq', check=False)
    finally:
        try:
            _git_retry('checkout', '-f', prior)
        except Exception as ex:  # pragma: no cover
            _log(f'restore checkout failed: {ex}', fh)
        git('clean', '-fdq', check=False)
        _log(f'### g3c1_build session end {now()}', fh)
        fh.close()

    final = C.read_jsonl(C.TRUTH)
    print(f'\nG3-C.1 truth records: {len(final)} -> {C.TRUTH}')
    for t in sorted(final, key=lambda x: x['instance_id']):
        print(f"  {t['instance_id']}: class={t['label_class']} "
              f"addressed={t['issue_addressed']} "
              f"acceptable={t['merge_acceptable']} "
              f"tree={t.get('canon_run_tree','')[:10]}")


if __name__ == '__main__':
    main()
