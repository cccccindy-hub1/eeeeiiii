"""G3-C.1 task-3 gate (zero API) — validate every human-written symptom probe
FLIPS before the expensive real pytest build is allowed to start:

  * at the clean base_commit the probe MUST fail (exit != 0): the reported
    symptom genuinely exists in the unpatched tree;
  * after applying ONLY the candidate model_patch (the maintainer test_patch is
    deliberately not involved — the probes were authored from the public issue
    report alone) the probe MUST pass (exit == 0): the candidate removes the
    reported symptom.

A probe that does not flip is a pre-registered STOP condition: the failure is
recorded in g3c1_failures.jsonl and construction halts. The problematic issue
is NOT replaced and construction does not continue to the next issue.

The vendored repo is always restored to its prior HEAD in the finally block.

  set GIT_NO_LAZY_FETCH=1
  uv run --offline --python 3.9 --with mpmath -m evidence.g3c1_probe_selftest
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

from evidence import g3c1_common as C
from evidence.builder import git, run_probe
from evidence.schemas import sha256_text

ROWS = C.OUT_RAW / 'g3c1_target_rows.jsonl'
OUT = C.OUT_AUDIT / 'g3c1_probe_selftest.json'
RUNLOG = C.OUT_RUNS / 'g3c1_probe_selftest.log'

LOG_TAIL = 4000


def _log(msg, fh):
    print(msg)
    fh.write(msg + '\n')
    fh.flush()


def _apply_candidate(raw):
    """Apply the candidate model_patch from the G3-C.1 patch dir (never the
    frozen evidence_store/patches tree)."""
    C.OUT_PATCHES.mkdir(parents=True, exist_ok=True)
    p = C.OUT_PATCHES / (raw['id'].replace(':', '__') + '.patch')
    with open(p, 'w', encoding='utf-8', newline='') as fh:
        fh.write(raw['model_patch'])
    r = git('apply', '--whitespace=nowarn', str(p.resolve()), check=False)
    return r.returncode == 0, r.stdout + r.stderr


def main():
    C.ensure_out_dirs()
    rows = C.read_jsonl(ROWS)
    if len(rows) != C.MAX_NEW_ISSUES:
        raise SystemExit(f'expected {C.MAX_NEW_ISSUES} target rows, got {len(rows)}')

    prior = git('rev-parse', 'HEAD').stdout.strip()
    results = []
    fh = open(RUNLOG, 'w', encoding='utf-8')
    try:
        for raw in sorted(rows, key=lambda r: r['instance_id']):
            iid = raw['instance_id']
            patch_sha = sha256_text(raw['model_patch'])
            _log(f'== {iid} base={raw["base_commit"][:10]} patch={patch_sha[:10]}', fh)

            git('checkout', '-f', raw['base_commit'])
            git('clean', '-fdq')
            probe = C.OUT_PROBES / f'{iid}.py'
            if not probe.exists():
                C.record_failure('probe_flip_gate', iid,
                                 {'reason': 'probe_file_missing', 'path': str(probe)})
                raise SystemExit(f'STOP: probe missing for {iid}')

            pre_ok, pre_log = run_probe(iid + '-baseline', probe)
            applied, ap_err = _apply_candidate(raw)
            if applied:
                post_ok, post_log = run_probe(iid + '-post-candidate', probe)
            else:
                post_ok, post_log = None, ('candidate patch did not apply\n'
                                           + ap_err[-LOG_TAIL:])

            flip = (pre_ok is False and post_ok is True and applied)
            rec = {
                'instance_id': iid,
                'base_commit': raw['base_commit'],
                'patch_sha256': patch_sha,
                'probe_file': str(probe.relative_to(C.HERE)).replace('\\', '/'),
                'probe_sha256': C.sha256_file(probe),
                'candidate_applied_cleanly': applied,
                'baseline_probe_passed': pre_ok,
                'post_candidate_probe_passed': post_ok,
                'flip_baseline_fail_to_post_pass': flip,
                'baseline_log': pre_log,
                'post_log': post_log,
            }
            results.append(rec)
            _log(f'   baseline_passed={pre_ok} applied={applied} '
                 f'post_passed={post_ok} flip={flip}', fh)

            if not flip:
                C.record_failure('probe_flip_gate', iid, {
                    'reason': 'probe did not fail-at-base -> pass-after-candidate',
                    'candidate_applied_cleanly': applied,
                    'baseline_probe_passed': pre_ok,
                    'post_candidate_probe_passed': post_ok,
                    'apply_error_tail': ap_err[-LOG_TAIL:] if not applied else '',
                    'baseline_log_tail': pre_log[-LOG_TAIL:],
                    'post_log_tail': post_log[-LOG_TAIL:]})
                raise SystemExit(
                    f'STOP: probe flip gate failed for {iid}; failure recorded, '
                    f'issue not replaced, construction halted.')

        out = {
            'gate': 'g3c1_probe_flip',
            'design_version': C.G3C1_DESIGN_VERSION,
            'n_issues': len(results),
            'all_probes_flip': all(r['flip_baseline_fail_to_post_pass']
                                   for r in results),
            'issues': results,
        }
        C.write_canonical(OUT, out)
        _log(f'\nall {len(results)} probes flip -> {OUT}', fh)
    finally:
        try:
            git('checkout', '-f', prior, check=False)
        except Exception as ex:  # pragma: no cover - best-effort restore
            print('restore checkout failed:', ex, file=sys.stderr)
        git('clean', '-fdq', check=False)
        fh.close()


if __name__ == '__main__':
    main()
