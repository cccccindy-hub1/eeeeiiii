"""G3-A task 1+2 — frozen mechanical selection of 10 NEW independent issues.

Pre-registered, model-behavior-independent selection from the locally cached
Lego-X/SWE-Review-Bench SymPy pool. No API, no network, no model output is
consulted; eligibility is decided solely from dataset test specs and the
vendored git repository state.

Primary-cohort rule (this differs deliberately from the mirror-based v21
build): each selected issue contributes exactly ONE target patch; mirror
fixtures are forbidden, and three-way label balance is NOT forced.

Inclusion gates (all must hold):
  G1 not previously used: not in the 10 frozen v21 issues nor the two issues
     with prior canonical executions (16597, 20428).
  G2 base_commit object present in the vendored offline sympy git repo.
  G3 maintainer test_patch applies cleanly at base; every declared
     FAIL_TO_PASS test name is defined in a test_patch file; declared F2P and
     P2P sets are non-empty (reuses the frozen wave2 audit's measured gates).
  G4 >=1 generator model_patch applies cleanly at base (one reviewable
     target). The target generator is chosen deterministically: among
     clean-apply rows prefer resolved==True, then a fixed generator priority,
     then the lexicographically smallest row id.
  G5 offline-buildable without network: issue is not the known blob-incomplete
     sympy-11618; final offline checkout is re-verified at build time.

Selection: eligible instance ids are sorted, shuffled with a pre-registered
seed (G3A_SELECT_SEED = 20261026A), and the first 10 are the cohort.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / 'evidence_store'
AUDIT = STORE / 'wave2_selection_audit.json'
POOL = STORE / 'wave2_candidate_pool.jsonl'
OUTDIR = ROOT / 'evidence_store_g3a' / 'selection'
OUTDIR.mkdir(parents=True, exist_ok=True)
OUT = OUTDIR / 'g3a_selection.json'

SEED = '20261026A'
N_COHORT = 10
# all issues ever consumed in prior waves (10 frozen + 2 with canon builds)
PREVIOUSLY_USED = {
    'sympy__sympy-12419', 'sympy__sympy-12481', 'sympy__sympy-12489',
    'sympy__sympy-13091', 'sympy__sympy-13798', 'sympy__sympy-14531',
    'sympy__sympy-16450', 'sympy__sympy-17139', 'sympy__sympy-18199',
    'sympy__sympy-18211', 'sympy__sympy-16597', 'sympy__sympy-20428'}
# known issue whose base tree blobs are not fully cached offline
OFFLINE_INCOMPLETE = {'sympy__sympy-11618'}
# fixed generator priority (dataset split prefixes), deterministic
GEN_PRIORITY = {'GLM-5-FP8': 0,
                'Qwen/Qwen3-Coder-30B-A3B-Instruct': 1,
                'Qwen/Qwen3-30B-A3B-Instruct-2507': 2}
GATE_KEYS = ('base_present', 'test_patch_clean', 'declared_nonempty',
             'all_test_files_exist_after_apply', 'test_patch_real_apply_ok',
             'f2p_all_mapped')


def main():
    audit = json.loads(AUDIT.read_text(encoding='utf-8'))
    pool = [json.loads(l) for l in POOL.read_text(encoding='utf-8').splitlines()
            if l.strip()]
    pool_by = {}
    for r in pool:
        pool_by.setdefault(r['instance_id'], []).append(r)

    eligible, excluded = [], []
    for c in audit['candidates']:
        iid = c['instance_id']
        g = c.get('gates', {})
        reason = None
        if iid in PREVIOUSLY_USED:
            reason = 'previously_used'
        elif iid in OFFLINE_INCOMPLETE:
            reason = 'offline_blob_incomplete'
        elif not all(g.get(k) for k in GATE_KEYS):
            reason = 'static_test_spec_gate_failed'
        else:
            clean = [rc for rc in c.get('row_checks', [])
                     if rc.get('model_patch_clean')]
            if not clean:
                reason = 'no_clean_target_patch'
        if reason:
            excluded.append({'instance_id': iid, 'reason': reason})
            continue
        # deterministic target generator
        clean = [rc for rc in c['row_checks'] if rc.get('model_patch_clean')]
        clean.sort(key=lambda rc: (0 if rc.get('resolved') else 1,
                                   GEN_PRIORITY.get(rc['generator_model'], 9),
                                   rc['id']))
        target = clean[0]
        prow = next((r for r in pool_by.get(iid, [])
                     if r.get('generator_model') == target['generator_model']
                     or r.get('model') == target['generator_model']), None)
        eligible.append({
            'instance_id': iid,
            'n_generators': c.get('n_rows'),
            'n_clean_targets': len(clean),
            'target_generator': target['generator_model'],
            'target_row_id': target['id'],
            'target_resolved_harness': bool(target.get('resolved')),
            'f2p_declared_n': g.get('f2p_declared_n'),
            'p2p_declared_n': g.get('p2p_declared_n'),
            'base_commit': (prow or {}).get('base_commit')})

    eligible.sort(key=lambda e: e['instance_id'])
    rng = random.Random(SEED)
    shuffled = list(eligible)
    rng.shuffle(shuffled)
    cohort = sorted(shuffled[:N_COHORT], key=lambda e: e['instance_id'])
    cohort_ids = [e['instance_id'] for e in cohort]

    result = {
        'document': 'G3-A pre-registered mechanical selection; frozen before '
                    'any model prediction; no API/network/model-behavior input.',
        'selection_seed': SEED, 'n_cohort': N_COHORT,
        'previously_used_excluded': sorted(PREVIOUSLY_USED),
        'n_eligible': len(eligible), 'n_excluded': len(excluded),
        'cohort_instance_ids': cohort_ids,
        'cohort': cohort,
        'eligible_instance_ids': [e['instance_id'] for e in eligible],
        'excluded': excluded}
    OUT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())

    print('eligible', len(eligible), 'excluded', len(excluded))
    print('cohort:')
    for e in cohort:
        print(' ', e['instance_id'], '| target', e['target_generator'],
              '| resolved', e['target_resolved_harness'],
              '| f2p', e['f2p_declared_n'], 'p2p', e['p2p_declared_n'],
              '| base', (e['base_commit'] or '')[:10])
    print('->', OUT)


if __name__ == '__main__':
    main()
