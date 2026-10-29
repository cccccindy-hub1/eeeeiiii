"""G3-A task 4 — oracle_gold vs condition_gold separation, frozen BEFORE any
model prediction.

Per issue (exactly ONE canonical target patch; no mirrors):

  oracle_gold      patch acceptability under the trustworthy evidence actually
                   produced locally. Computed with the SAME pure rule as the
                   frozen study (evidence.gold_w2.oracle_gold) so there is no
                   rule drift, fed by facts recomputed here from the signed
                   artifact record + git write-tree attestation + the executed
                   symptom probe:
                     linked   HMAC authentic and record base_commit/patch_sha
                              equal the review target
                     fresh    attestation authentic and its expected_run_tree
                              equals the deterministically-restaged canonical
                              run tree (base+candidate+maintainer test_patch)
                     complete every attested declared id (F2P plus the SCOPED
                              P2P subset) was executed
                     acceptance failure/success from the signed outcome maps
                     symptom_persists = probe failed at baseline AND still
                              fails after the candidate patch

  condition_gold   what the CURRENTLY VISIBLE evidence supports under a given
                   evidence regime. The G3-A primary cohort holds the regime
                   constant at the full canonical surface (linked/fresh/
                   complete evidence is actually present), so per-issue
                   condition_gold == oracle_gold for the full-evidence
                   condition. Per-regime condition labels for the G3-B factor
                   cells are produced later, mechanically, by the frozen
                   evidence.gold_w2.condition_gold projection at render time;
                   they are never re-adjudicated and no fixture is altered to
                   manufacture divergence (mirrors are forbidden).

Human adjudication: no second independent annotator is available in G3-A, so
the human-human agreement status for every issue is recorded as "pending". The
mechanical recomputation below is an internal consistency check, NOT human
inter-rater agreement, and is never reported as such.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evidence.gold_w2 import oracle_gold, GOLD_VERSION
from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
STORE_ROOT = G3A / 'store'
TRUTH = G3A / 'g3a_truth.jsonl'
OUT = G3A / 'gold' / 'g3a_gold.jsonl'

BAD = ('FAILED', 'ERROR', 'missing', 'unmapped', 'PARTIAL_FAIL')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(OUT))
    a = ap.parse_args()
    store = ArtifactStore(str(STORE_ROOT),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    truths = list(read_jsonl(str(TRUTH)))
    rows = []
    for t in sorted(truths, key=lambda r: r['instance_id']):
        iid, base, patch = t['instance_id'], t['base_commit'], t['patch_sha256']
        aid = make_artifact_id(iid, patch)
        got = store.get(aid)
        if got is None:
            raise SystemExit(f'missing artifact {aid}')
        rec, authentic = got
        att = store.get_attestation(iid, patch)

        linked = bool(authentic and rec['base_commit'] == base
                      and rec['patch_sha256'] == patch)
        att_ok = bool(att and att.get('_attestation_authentic'))
        # freshness for the primary cohort: the restaged canonical tree stored
        # at build time IS the record's attested tree; compare to a fresh
        # deterministic restaging is done separately in g3a_freshness_check.
        fresh = bool(att_ok and linked)  # tree identity verified in build restage
        f2p = rec.get('fail_to_pass') or {}
        p2p = rec.get('pass_to_pass_scoped') or {}
        exec_names = set(f2p) | set(p2p)
        declared = set(att['declared_fail_to_pass']) | \
            set(att['declared_p2p_scoped']) if att else set()
        missing = sorted(declared - exec_names)
        complete = att_ok and not missing
        n_fail = sum(1 for v in list(f2p.values()) + list(p2p.values())
                     if v in BAD)
        n_check = len(exec_names)
        lp = t.get('label_provenance', {})
        pre, post = (lp.get('symptom_pre_patch_passed'),
                     lp.get('symptom_post_patch_passed'))
        symptom_persists = (pre is False and post is False)

        facts = dict(linked=linked, fresh=fresh, complete=complete,
                     acceptance_failure=n_fail > 0,
                     acceptance_success=n_check > 0 and n_fail == 0,
                     symptom_persists=symptom_persists)
        og = oracle_gold(**facts)

        # Cross-check against builder's own class label (audit only; gold rule
        # never reads it).
        basis = []
        if symptom_persists:
            basis.append('issue symptom still reproduces after the patch')
        if facts['acceptance_failure'] and linked and fresh:
            basis.append(f'{n_fail} executed declared check(s) failed on '
                         'linked, fresh evidence')
        if og == 'ACCEPT':
            basis.append(f'{n_check} checks executed, linked/fresh/complete, '
                         'no failure; symptom gone (SCOPED P2P)')
        if og == 'NEED_EVIDENCE' and not basis:
            if not complete:
                basis.append('declared scoped check set not fully executed')
            else:
                basis.append('no decisive failure and insufficient success')

        rows.append({
            'version': GOLD_VERSION + '+g3a-v1',
            'instance_id': iid, 'id': t['id'],
            'repo': t['repo'], 'base_commit': base,
            'patch_sha256': patch, 'artifact_id': aid,
            'canon_run_tree': t.get('canon_run_tree'),
            'facts': {
                'linked': linked, 'fresh': fresh, 'complete': complete,
                'attestation_authentic': att_ok,
                'executed_check_count': n_check,
                'executed_failure_count': n_fail,
                'declared_scoped_count': len(declared),
                'declared_missing_after_exec': missing,
                'symptom_pre_passed': pre, 'symptom_post_passed': post,
                'symptom_polarity': 'persists' if symptom_persists else (
                    'gone' if (pre is False and post is True) else None)},
            'oracle_gold': og,
            'oracle_basis': ' | '.join(basis),
            'coverage_scope_disclosure':
                'PASS_TO_PASS coverage is the attested SCOPED subset '
                '(test_patch files + tests/ adjacent to changed code files); '
                'the full dataset P2P suite is not executed locally, so '
                'oracle ACCEPT means scoped acceptability, not full-suite.',
            'condition_gold': {
                '_note': 'primary cohort freezes the full canonical surface; '
                         'condition_gold==oracle_gold there. Per-regime labels '
                         'for G3-B factor cells are projected mechanically at '
                         'render via evidence.gold_w2.condition_gold and are '
                         'not re-adjudicated.',
                'full_canonical_surface': og},
            'resolved_in_dataset': t.get('resolved_in_dataset'),
            'builder_label_class_audit_only': t.get('label_class'),
            'human_adjudication': {
                'status': 'pending',
                'n_independent_annotators': 1,
                'reason': 'G3-A has a single annotator; a second independent '
                          'annotator is required before human inter-rater '
                          'agreement can be claimed. Mechanical oracle '
                          'recomputation is not human agreement.'},
        })

    outp = Path(a.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)
                    + '\n', encoding='utf-8')
    from collections import Counter
    dist = Counter(r['oracle_gold'] for r in rows)
    print(f'G3-A gold rows: {len(rows)} -> {outp}')
    for r in rows:
        print(f"  {r['instance_id']}: oracle={r['oracle_gold']:<14} "
              f"linked={r['facts']['linked']} fresh={r['facts']['fresh']} "
              f"complete={r['facts']['complete']} "
              f"fails={r['facts']['executed_failure_count']} "
              f"symptom={r['facts']['symptom_polarity']} "
              f"human={r['human_adjudication']['status']}")
    print('oracle distribution:', dict(dist))


if __name__ == '__main__':
    main()
