"""Wave-2 deterministic issue selection (offline data plane; no LLM calls).

Pipeline (TR-3.1..TR-3.3, DW2-4):
  1. group cached HF pool rows (Lego-X/SWE-Review-Bench, sympy) by instance;
  2. exclude the 8 Wave-1 instances and require >=2 distinct generator rows;
  3. walk instance_id ascending and preflight each candidate in the vendored
     sympy git:
       a. base_commit fetchable (git cat-file; fetch origin on demand),
       b. maintainer test_patch applies cleanly (git apply --check, then real
          apply for name mapping, reset afterwards),
       c. every declared FAIL_TO_PASS bare name maps to a def in a test_patch
          file (static collectibility proxy for 3.9+pytest8.4.2),
       d. declared F2P/P2P sets non-empty,
       e. >=2 generator rows whose model_patch itself applies cleanly at the
          base commit (GOOD/BAD material for Task 4 mirror builds);
  4. take the first 4 that pass every gate; write their rows to
     wave2_raw_rows.jsonl and a full audit with per-step reasons.

No criterion is ever relaxed. Fewer than 4 -> blocked audit, exit code 2.
Run: uv run --python 3.13 python -m evidence.wave2_select
"""
from __future__ import annotations

import argparse, json, re, subprocess, tempfile
from pathlib import Path

from pilot import write_jsonl
from evidence.schemas import sha256_text

HERE = Path(__file__).resolve().parent.parent        # stance_pilot/
REPO = HERE / 'repro' / 'sympy_src'
STORE = HERE / 'evidence_store'
POOL = STORE / 'wave2_candidate_pool.jsonl'

OLD_INSTANCES = {
    'sympy__sympy-13798', 'sympy__sympy-14531', 'sympy__sympy-16450',
    'sympy__sympy-16597', 'sympy__sympy-17139', 'sympy__sympy-18199',
    'sympy__sympy-18211', 'sympy__sympy-20428',
}
TARGET_N = 4

DEF_RE = re.compile(r'^\s*def\s+([A-Za-z_]\w*)\s*\(')


def git(*args, check=True):
    p = subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if check and p.returncode != 0:
        raise RuntimeError(f'git {args} failed:\n{p.stdout}\n{p.stderr}')
    return p


def commit_present(sha):
    p = git('cat-file', '-e', f'{sha}^{{commit}}', check=False)
    return p.returncode == 0


def write_patch(text):
    """Materialise a patch in a temp file; return its Path."""
    fd = tempfile.NamedTemporaryFile('w', suffix='.patch', delete=False,
                                     encoding='utf-8', newline='')
    fd.write(text)
    fd.close()
    return Path(fd.name)


def test_patch_files(raw):
    return sorted({l[6:] for l in raw['test_patch'].splitlines()
                   if l.startswith('+++ b/')})


def apply_check(text):
    """git apply --check at the current tree. Returns (ok, stderr-snippet).

    Retried once: on Windows a transient antivirus lock on the temp patch file
    can make git fail to read it; a second attempt distinguishes that from a
    real patch/tree conflict. Both attempts are recorded on failure.
    """
    pth = write_patch(text)
    errs = []
    try:
        for attempt in (1, 2):
            p = git('apply', '--check', '--whitespace=nowarn', str(pth),
                    check=False)
            if p.returncode == 0:
                return True, None
            errs.append(f'attempt{attempt}: ' + p.stderr[:300])
        return False, ' | '.join(errs)
    finally:
        pth.unlink(missing_ok=True)


def build_name_index(files):
    idx = {}
    for f in files:
        p = REPO / f
        if not p.exists():
            continue
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            m = DEF_RE.match(line)
            if m:
                idx.setdefault(m.group(1), set()).add(f)
    return idx


def preflight(raw):
    """Return dict of gate results; mutates the worktree, caller resets."""
    res = {}
    # (a) base commit
    res['base_present'] = commit_present(raw['base_commit'])
    if not res['base_present']:
        f = git('fetch', '--depth=1', 'origin', raw['base_commit'], check=False)
        res['fetch_ok'] = f.returncode == 0
        res['fetch_stderr'] = f.stderr[:300]
        res['base_present'] = commit_present(raw['base_commit'])
    if not res['base_present']:
        res['fatal'] = 'base_commit unavailable even after fetch'
        return res
    git('checkout', '-f', raw['base_commit'])
    git('clean', '-fdq')
    # (b) test_patch clean apply
    tp_ok, tp_err = apply_check(raw['test_patch'])
    res['test_patch_clean'] = tp_ok
    if not tp_ok:
        res['test_patch_stderr'] = tp_err
    # (d) declared sets non-empty
    res['f2p_declared_n'] = len(raw['FAIL_TO_PASS'])
    res['p2p_declared_n'] = len(raw['PASS_TO_PASS'])
    res['declared_nonempty'] = bool(raw['FAIL_TO_PASS']) and bool(raw['PASS_TO_PASS'])
    # (c) name mapping needs the test_patch applied for real
    tp_files = test_patch_files(raw)
    res['test_patch_files'] = tp_files
    res['all_test_files_exist_after_apply'] = False
    res['f2p_unmapped'] = sorted(raw['FAIL_TO_PASS'])
    if tp_ok:
        pth = write_patch(raw['test_patch'])
        try:
            ap = git('apply', '--whitespace=nowarn', str(pth), check=False)
            res['test_patch_real_apply_ok'] = ap.returncode == 0
            if ap.returncode == 0:
                res['all_test_files_exist_after_apply'] = all(
                    (REPO / f).exists() for f in tp_files)
                idx = build_name_index(tp_files)
                res['f2p_unmapped'] = sorted(
                    n for n in raw['FAIL_TO_PASS'] if n not in idx)
        finally:
            pth.unlink(missing_ok=True)
    res['f2p_all_mapped'] = (tp_ok and not res['f2p_unmapped']
                             and res.get('all_test_files_exist_after_apply', False))
    return res


def row_gate(row):
    """Per-generator-row model_patch applicability (information for Task 4)."""
    ok, err = apply_check(row['model_patch'])
    return {'id': row['id'], 'generator_model': row['generator_model'],
            'resolved': row['resolved'], 'model_patch_clean': ok,
            'model_patch_stderr': None if ok else err}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pool', default=str(POOL))
    ap.add_argument('--raw-out', default=str(STORE / 'wave2_raw_rows.jsonl'))
    ap.add_argument('--audit-out',
                    default=str(STORE / 'wave2_selection_audit.json'))
    a = ap.parse_args()

    rows = [json.loads(l)
            for l in Path(a.pool).read_text(encoding='utf-8').splitlines() if l]
    by_inst = {}
    for r in rows:
        by_inst.setdefault(r['instance_id'], []).append(r)

    candidates = []
    for iid in sorted(by_inst):
        rs = by_inst[iid]
        gens = sorted({r['generator_model'] for r in rs})
        entry = {'instance_id': iid, 'n_rows': len(rs),
                 'generators': gens, 'excluded_old': iid in OLD_INSTANCES,
                 'gates': {}, 'selected': False}
        if iid in OLD_INSTANCES:
            entry['exclude_reason'] = 'wave1 instance (frozen set)'
        elif len(gens) < 2:
            entry['exclude_reason'] = f'only {len(gens)} generator(s)'
        candidates.append(entry)

    head_before = git('rev-parse', 'HEAD').stdout.strip()
    picks = []
    try:
        for entry in candidates:
            if 'exclude_reason' in entry:
                continue
            iid = entry['instance_id']
            rs = sorted(by_inst[iid], key=lambda r: r['id'])
            raw0 = rs[0]
            try:
                gates = preflight(raw0)
            except Exception as e:  # checkout/network failures are audited, not fatal
                gates = {'fatal': f'preflight exception: {type(e).__name__}: {e}'}
            entry['gates'] = gates
            # per-row model_patch checks (only when tree is usable)
            row_results = []
            if 'fatal' not in gates:
                # real test_patch may still be applied from name-mapping step;
                # reset to pristine base before checking model patches.
                git('checkout', '-f', raw0['base_commit'])
                git('clean', '-fdq')
                for r in rs:
                    row_results.append(row_gate(r))
            entry['row_checks'] = row_results
            clean_rows = [x for x in row_results if x['model_patch_clean']]
            clean_gens = {x['generator_model'] for x in clean_rows}

            reasons = []
            if gates.get('fatal'):
                reasons.append('preflight_fatal')
            if not gates.get('base_present'):
                reasons.append('base_commit_unavailable')
            if not gates.get('test_patch_clean'):
                reasons.append('test_patch_not_clean')
            if not gates.get('declared_nonempty'):
                reasons.append('empty_f2p_or_p2p')
            if not gates.get('f2p_all_mapped'):
                reasons.append('f2p_node_unmapped')
            if len(clean_gens) < 2:
                reasons.append(
                    f'only {len(clean_gens)} generator(s) with clean model_patch')
            entry['gate_failed'] = reasons
            if not reasons and len(picks) < TARGET_N:
                entry['selected'] = True
                picks.append(iid)
    finally:
        git('checkout', '-f', head_before, check=False)
        git('clean', '-fdq', check=False)

    selected_rows = [r for iid in picks for r in
                     sorted(by_inst[iid], key=lambda r: r['id'])]
    raw_sha = None
    if len(picks) == TARGET_N:
        write_jsonl(a.raw_out, selected_rows)
        raw_sha = sha256_text(Path(a.raw_out).read_text(encoding='utf-8'))

    audit = {
        'rule': 'instance_id ascending; first 4 passing every static gate',
        'pool_file': str(Path(a.pool).name),
        'pool_rows': len(rows), 'pool_instances': len(by_inst),
        'old_instances_excluded': sorted(OLD_INSTANCES),
        'gates': [
            'not in frozen wave1 set', '>=2 distinct generator rows',
            'base_commit fetchable in vendored git',
            'maintainer test_patch applies cleanly',
            'declared FAIL_TO_PASS and PASS_TO_PASS non-empty',
            'every FAIL_TO_PASS name defined in a test_patch file',
            '>=2 generators with a model_patch that applies cleanly at base',
        ],
        'candidates': candidates,
        'selected_instance_ids': picks,
        'selected_n': len(picks),
        'raw_out_rows': len(selected_rows),
        'raw_out_sha256': raw_sha,
        'blocked': len(picks) < TARGET_N,
    }
    Path(a.audit_out).write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                                 encoding='utf-8')

    print(f'pool: {len(rows)} rows / {len(by_inst)} instances')
    print('selected:', picks)
    for c in candidates:
        if c.get('selected') or c.get('gate_failed'):
            tag = 'PICK' if c['selected'] else 'fail'
            print(f"  {tag} {c['instance_id']} {c.get('gate_failed', '')}")
    print('audit ->', a.audit_out)
    if len(picks) < TARGET_N:
        print(f'BLOCKED: only {len(picks)} eligible instances')
        raise SystemExit(2)


if __name__ == '__main__':
    main()
