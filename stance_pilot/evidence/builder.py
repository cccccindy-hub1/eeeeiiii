"""Build immutable test artifacts + three-label truth for candidate patches.

Pipeline per candidate:
  1. git checkout -f <base_commit> in the vendored repo
  2. symptom probe at BASELINE (must fail -> the symptom really exists)
  3. apply candidate patch; symptom probe AFTER (must pass -> issue_addressed)
  4. apply maintainer test_patch (rejects recorded, never silently dropped)
  5. run all FAIL_TO_PASS node ids (batched per file), per-id outcomes
  6. run SCOPED PASS_TO_PASS: ids in test_patch files or the tests/ package of each
     changed code file (declared scope; full P2P is infeasible locally)
  7. emit signed artifact + logs, append truth record (class A/B/C/D)

Run under: uv run --python 3.11 --with mpmath --with pytest python -m evidence.builder
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, time
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.probes import probe_source
from evidence.schemas import (SCHEMA_VERSION, classify, canonical_dumps,
                              make_artifact_id, sha256_bytes, sha256_text)
from evidence.store import ArtifactStore

HERE = Path(__file__).resolve().parent.parent          # stance_pilot/
REPO = HERE / 'repro' / 'sympy_src'
WORK = HERE / 'evidence_store'
PYTEST_TIMEOUT_S = 1800

NODE_RE = re.compile(r'^([\w\\/.]+\.py)::([A-Za-z_][\w]*)(?:\[[^\]]*\])?\s+'
                     r'(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b')

def build_test_name_index(files):
    """Read each scope file once -> {test_function_name: [files defining it]}."""
    idx = {}
    for f in files:
        text = (REPO / f).read_text(encoding='utf-8', errors='replace')
        for l in text.splitlines():
            m = re.match(r'^\s*def\s+([A-Za-z_]\w*)\s*\(', l)
            if m:
                idx.setdefault(m.group(1), set()).add(f)
    return idx

def map_names_to_files(names, files, index=None):
    """sympy lists bare test function names; find the scope file defining each."""
    idx = index or build_test_name_index(files)
    return {name: sorted(idx[name]) for name in names if name in idx}

def git(*args, check=True):
    p = subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError(f'git {args} failed:\n{p.stdout}\n{p.stderr}')
    return p

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')

def write_patch(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)

def changed_files(patch: str, code_only=False):
    out = []
    for l in patch.splitlines():
        if l.startswith('+++ b/'):
            p = l[6:]
            if code_only and ('/tests/' in p or p.startswith('tests/')):
                continue
            out.append(p)
    return out

def scope_test_files(raw, code_files):
    """Declared scope files: every file the maintainer test_patch touches plus the
    tests/ package adjacent to each changed code file
    (sympy/core/foo.py -> sympy/core/tests/*.py). Files must exist at base_commit."""
    files = set(l[6:] for l in raw['test_patch'].splitlines() if l.startswith('+++ b/'))
    for cf in code_files:
        pkg = (os.path.dirname(cf) + '/tests/').replace('\\', '/')
        td = REPO / pkg
        if td.is_dir():
            files.update(pkg + p.name for p in td.glob('test_*.py'))
    return sorted(f for f in files if (REPO / f).exists())

def run_probe(name, probe_path: Path):
    env = dict(os.environ)
    env['PYTHONPATH'] = str(REPO)
    # Resolve to absolute: cwd is REPO, which is NOT the store root, so a
    # relative probe path (as the Phase-2 builder passes) would be looked up
    # inside the vendored repo and fail with Errno 2.
    p = subprocess.run([sys.executable, str(Path(probe_path).resolve())],
                       cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=300,
                       encoding='utf-8', errors='replace')
    log = (f'$ python {name}.py  (exit {p.returncode})\n'
           f'--- stdout ---\n{p.stdout}\n--- stderr ---\n{p.stderr}')
    return p.returncode == 0, log

def run_pytest_files(files, label):
    if not files:
        return '', 0
    cmd = [sys.executable, '-m', 'pytest', *sorted(files),
           '-v', '--tb=short', '-p', 'no:cacheprovider']
    t0 = time.time()
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True,
                       timeout=PYTEST_TIMEOUT_S, encoding='utf-8', errors='replace')
    dur = time.time() - t0
    log = (f'$ {" ".join(cmd)}  (exit {p.returncode}, {dur:.0f}s)\n'
           f'--- stdout ---\n{p.stdout[-60000:]}\n--- stderr ---\n{p.stderr[-20000:]}')
    return log, p.returncode

# pytest terminal summary lines, e.g.:
#   FAILED path/test.py::name - sympy.utilities.pytest.XFail: name
#   FAILED path/test.py::name - sympy.utilities.pytest.Skipped: NumPy not installed
SUMMARY_RE = re.compile(r'^(?:FAILED|ERROR)\s+(\S+)\s+-\s+'
                        r'(?:sympy\.utilities\.pytest\.)?(XFail|Skipped)\b')
SUMMARY_STATUS = {'XFail': 'XFAIL', 'Skipped': 'SKIPPED'}

def parse_node_logs(logs):
    """file::name -> worst status seen (ERROR > FAILED > PASSED ...).

    Old sympy (2017-2020) raised its own Skipped/XFail exceptions which modern
    pytest reports as FAILED in the verbose column; recover their true status
    from the terminal summary lines.
    """
    rank = {'PASSED': 0, 'XFAIL': 0, 'SKIPPED': 1, 'XPASS': 2, 'FAILED': 3, 'ERROR': 4}
    status = {}
    overrides = {}
    for log in logs:
        for line in log.splitlines():
            s = line.strip()
            ms = SUMMARY_RE.match(s)
            if ms:
                node = ms.group(1).replace('\\', '/')
                overrides[node] = SUMMARY_STATUS[ms.group(2)]
                continue
            m = NODE_RE.match(s)
            if not m:
                continue
            node = (m.group(1).replace('\\', '/') + '::' + m.group(2))
            st = m.group(3)
            if rank.get(st, 0) > rank.get(status.get(node), -1):
                status[node] = st
    status.update(overrides)
    return status

def name_outcomes(names, name_files, node_status):
    """Aggregate pytest node results back to bare test names; a name fails if every
    located node failed/errored or no node was reported."""
    res = {}
    for name in names:
        files = name_files.get(name)
        if not files:
            res[name] = 'unmapped'
            continue
        sts = [node_status.get(f + '::' + name) for f in files]
        sts = [s for s in sts if s]
        if not sts:
            res[name] = 'missing'
        elif all(s in ('FAILED', 'ERROR') for s in sts):
            res[name] = 'FAILED'
        elif any(s in ('FAILED', 'ERROR') for s in sts):
            res[name] = 'PARTIAL_FAIL'
        elif all(s in ('PASSED', 'XFAIL', 'SKIPPED') for s in sts):
            res[name] = 'PASSED'
        else:
            res[name] = sts[0]
    return res

BAD = ('FAILED', 'ERROR', 'missing', 'unmapped', 'PARTIAL_FAIL')

def fails(outcomes):
    return sorted(n for n, s in outcomes.items() if s in BAD)

def passes(outcomes):
    return sorted(n for n, s in outcomes.items() if s in ('PASSED', 'XFAIL', 'SKIPPED'))

def build_one(raw, store, selected_hash, probe_dir, probe_lookup=None):
    iid = raw['instance_id']
    patch_sha = sha256_text(raw['model_patch'])
    if selected_hash and patch_sha != selected_hash:
        raise ValueError(f"patch hash mismatch for {raw['id']}")
    test_patch_sha = sha256_text(raw['test_patch'])
    print(f'== {raw["id"]}  patch={patch_sha[:10]}')

    # clean checkout
    git('checkout', '-f', raw['base_commit'])
    git('clean', '-fdq')  # remove untracked leftovers (new files, .rej, .orig)

    # scope is determined by the patches, but the existing P2P tests already exist
    # at base_commit, so compute it before touching the tree.
    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    name_index = build_test_name_index(scope_files)
    p2p_in_scope = [n for n in raw['PASS_TO_PASS'] if n in name_index]
    p2p_map = map_names_to_files(p2p_in_scope, scope_files, name_index)

    # baseline symptom probe
    probe_path = probe_dir / f'{iid}.py'
    if probe_lookup is None:
        probe_src = probe_source(iid)
    else:
        probe_src = probe_lookup(iid)
    with open(probe_path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(probe_src)
    pre_ok, pre_log = run_probe('probe', probe_path)

    # baseline scoped P2P run (no candidate patch, no maintainer test patch):
    # establishes which existing tests genuinely pass in this environment, so an
    # environment failure (missing NumPy, modern-pytest XFail noise) is never
    # mistaken for a candidate-induced regression.
    started = now()
    base_logs = []
    base_run_files = sorted(set(sum(p2p_map.values(), [])))
    for i in range(0, len(base_run_files), 3):
        log, _ = run_pytest_files(base_run_files[i:i+3], 'tests')
        base_logs.append(log)
    base_status = parse_node_logs(base_logs)
    p2p_baseline_outcomes = name_outcomes(p2p_in_scope, p2p_map, base_status)
    p2p_baseline_log = '\n\n'.join(base_logs)

    # apply candidate patch
    cand_patch = WORK / 'patches' / f"{raw['id'].replace(':', '__')}.patch"
    write_patch(cand_patch, raw['model_patch'])
    ap = git('apply', '--whitespace=nowarn', str(cand_patch.resolve()), check=False)
    if ap.returncode != 0:
        print('  candidate patch did not apply; skipping as non-evaluable')
        return None, {'apply': False, 'detail': ap.stderr[:500]}

    post_ok, post_log = run_probe('probe', probe_path)
    issue_addressed = (not pre_ok) and post_ok

    # apply maintainer test_patch. Replicate SWE-bench eval: reset every file the
    # test_patch touches back to base_commit first (candidate patches may contain
    # their own edits to those test files), then apply the official version.
    tp_path = WORK / 'patches' / f"{iid}.test_patch.patch"
    write_patch(tp_path, raw['test_patch'])
    tp_files = [l[6:] for l in raw['test_patch'].splitlines() if l.startswith('+++ b/')]
    if tp_files:
        git('checkout', raw['base_commit'], '--', *tp_files)
    tp = git('apply', '--whitespace=nowarn', str(tp_path.resolve()), check=False)
    tp_clean = tp.returncode == 0
    if not tp_clean:
        # retry with rejects so evaluable hunks still run; record honestly
        git('apply', '--reject', '--whitespace=nowarn', str(tp_path.resolve()), check=False)

    # rebuild the name index after applying the test patch (F2P tests now exist);
    # one verbose pytest pass per batched scope file drives both F2P and P2P.
    name_index = build_test_name_index(scope_files)
    f2p_map = map_names_to_files(raw['FAIL_TO_PASS'], scope_files, name_index)
    p2p_map = map_names_to_files(p2p_in_scope, scope_files, name_index)
    run_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    logs = []
    for i in range(0, len(run_files), 3):
        log, _ = run_pytest_files(run_files[i:i+3], 'tests')
        logs.append(log)
    node_status = parse_node_logs(logs)
    f2p_outcomes = name_outcomes(raw['FAIL_TO_PASS'], f2p_map, node_status)
    p2p_outcomes = name_outcomes(p2p_in_scope, p2p_map, node_status)
    f2p_log_all = p2p_log_all = '\n\n'.join(logs)
    finished = now()

    f2p_failed = fails(f2p_outcomes)
    # regression = passed at baseline AND bad after patch (SWE-bench P2P semantics);
    # tests already failing in the environment are reported separately, not blamed.
    p2p_regressed = sorted(
        n for n, s in p2p_outcomes.items()
        if s in BAD and p2p_baseline_outcomes.get(n) in ('PASSED', 'XFAIL', 'SKIPPED')
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
        'runner': f'pytest/vendored-git  py={sys.version.split()[0]}  host=windows-local',
        'started_at': started, 'finished_at': finished,
        'scope': {
            'rule': 'F2P all; P2P scoped to test_patch files and tests/ adjacent to '
                    'each changed code file',
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
            # bad in the environment both before and after the patch (not a regression)
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
    print(f"  class={label} issue_addressed={issue_addressed} "
          f"F2P {len(f2p_outcomes)-len(f2p_failed)}/{len(f2p_outcomes)} "
          f"P2P-regressed {len(p2p_regressed)} "
          f"(preexisting-bad {len(p2p_preexisting_bad)}) "
          f"test_patch_clean={tp_clean}")
    return truth, {'apply': True}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--selected', default='selected.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--ids', default='')     # restrict raw-row ids
    ap.add_argument('--all', action='store_true', help='all raw rows, not just selected')
    ap.add_argument('--force', action='store_true',
                    help='rebuild ids already present in truth.jsonl (overwrite)')
    a = ap.parse_args()

    sel_hash = {r['id']: r['patch_sha256'] for r in read_jsonl(a.selected)}
    rows = read_jsonl(a.raw)
    if a.ids:
        want = set(a.ids.split(','))
        rows = [r for r in rows if r['id'] in want]
    elif not a.all:
        rows = [r for r in rows if r['id'] in sel_hash]

    store = ArtifactStore(a.store)
    probe_dir = WORK / 'probes'
    probe_dir.mkdir(parents=True, exist_ok=True)
    truth_path = WORK / 'truth.jsonl'
    truths = list(read_jsonl(truth_path)) if truth_path.exists() else []
    done = {t['id'] for t in truths}
    skipped = []
    try:
        for raw in rows:
            if raw['id'] in done and not a.force:
                continue
            truth, meta = build_one(raw, store, sel_hash.get(raw['id']), probe_dir)
            if truth is None:
                skipped.append((raw['id'], meta))
                continue
            truths = [t for t in truths if t['id'] != truth['id']]
            truths.append(truth)
    finally:
        git('checkout', '-f', 'HEAD', check=False)
        # remove reject leftovers / untracked probe artifacts inside repo
        git('clean', '-fdq', check=False)
        write_jsonl(truth_path, truths)
    print(f'\ntruth records: {len(truths)} -> {truth_path}')
    for s, m in skipped:
        print('SKIPPED', s, m)

if __name__ == '__main__':
    main()
