"""G3-C.1 task 6 — oracle gold + per-condition gold + Sufficiency Certificates,
frozen BEFORE any model prediction. Model API budget $0.

Two outputs, both under evidence_store_g3c1/gold/:

  g3c1_oracle_gold.jsonl
      One oracle row per pilot issue. Facts are recomputed mechanically here
      from the AUTHENTIC signed artifact + signed write-tree attestation +
      independent restage recomputation + executed symptom probe, using the
      FROZEN rule evidence.gold_w2.oracle_gold (no rule drift):
        linked    HMAC authentic + record base/patch equal the target
        fresh     attestation authentic AND the independent git-restage
                  write-tree (audit/g3c1_freshness_recompute.json) equals the
                  attested expected_run_tree  [G3-B.2 three-state semantics;
                  a missing tree can never be silently read as stale]
        complete  every attested declared id (F2P + scoped P2P) executed
        acceptance failure/success from the signed outcome maps
        symptom_persists = probe failed at baseline AND still fails post

  g3c1_condition_certificates.jsonl
      8 issues x 5 frozen conditions = 40 Sufficiency Certificates. Each
      condition gold is produced by the FROZEN evidence.gold_w2.condition_gold
      over evidence.visibility.project_surface with the G3-C.0 projection v2
      diagnostic surface. No gold is edited to hit a category quota.

All gold is PROVISIONAL (single annotator, n=1; annotator2 NOT_OBTAINED) until
the sealed blind packet is labelled by a real second human adjudicator.

  uv run --offline --python 3.9 -m evidence.g3c1_gold
"""
from __future__ import annotations

import json

from evidence import g3c1_common as C
from evidence.gold_w2 import oracle_gold, condition_gold, GOLD_VERSION
from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.views import display_for_tier
from evidence.visibility import project_surface
from evidence.ternary import _executed_counts
from evidence.g3c1_freshness import load_restage_cache

BAD = ('FAILED', 'ERROR', 'missing', 'unmapped', 'PARTIAL_FAIL')
ORACLE_OUT = C.OUT_GOLD / 'g3c1_oracle_gold.jsonl'
CERT_OUT = C.OUT_GOLD / 'g3c1_condition_certificates.jsonl'


def _issue_facts(store, truth, restage_by_iid):
    iid = truth['instance_id']
    base, patch = truth['base_commit'], truth['patch_sha256']
    aid = make_artifact_id(iid, patch)
    got = store.get(aid)
    if got is None:
        raise SystemExit(f'missing authenticatable artifact {aid}')
    rec, authentic = got
    if not authentic:
        raise SystemExit(f'inauthentic artifact signature for {iid}')
    att = store.get_attestation(iid, patch)
    if not att or not att.get('_attestation_authentic'):
        raise SystemExit(f'missing/inauthentic attestation for {iid}')

    linked = bool(rec['base_commit'] == base and rec['patch_sha256'] == patch)
    hit = restage_by_iid.get(iid) or {}
    tree_match = bool(hit.get('tree_matches'))
    if not hit:
        raise SystemExit(f'no independent restage entry for {iid}; run '
                         'g3c1_freshness before gold')
    # G3-B.2 authoritative three-state freshness, applied to genuine issues.
    fresh = bool(linked and att.get('_attestation_authentic') and tree_match)
    fresh_state = 'TRUE' if fresh else ('FALSE' if linked else 'UNKNOWN')

    f2p = rec.get('fail_to_pass') or {}
    p2p = rec.get('pass_to_pass_scoped') or {}
    exec_names = set(f2p) | set(p2p)
    declared = set(att['declared_fail_to_pass']) | \
        set(att['declared_p2p_scoped'])
    missing = sorted(declared - exec_names)
    complete = not missing
    n_fail = sum(1 for v in list(f2p.values()) + list(p2p.values())
                 if v in BAD)
    n_check = len(exec_names)

    lp = truth.get('label_provenance', {})
    pre, post = (lp.get('symptom_pre_patch_passed'),
                 lp.get('symptom_post_patch_passed'))
    symptom_persists = (pre is False and post is False)
    polarity = 'persists' if symptom_persists else (
        'gone' if (pre is False and post is True) else None)

    facts = dict(linked=linked, fresh=fresh, complete=complete,
                 acceptance_failure=n_fail > 0,
                 acceptance_success=n_check > 0 and n_fail == 0,
                 symptom_persists=symptom_persists)
    meta = {
        'iid': iid, 'id': truth['id'], 'repo': truth['repo'], 'base': base,
        'patch': patch, 'aid': aid, 'rec': rec, 'att': att, 'linked': linked,
        'fresh': fresh, 'fresh_state': fresh_state, 'tree_match': tree_match,
        'complete': complete, 'missing': missing, 'n_fail': n_fail,
        'n_check': n_check, 'pre': pre, 'post': post, 'polarity': polarity,
        'facts': facts,
        'restage_authentic': bool(hit.get('attestation_authentic'))}
    return meta


def _oracle_basis(m):
    og = m['oracle']
    basis = []
    if m['facts']['symptom_persists']:
        basis.append('issue symptom still reproduces after the patch')
    if m['facts']['acceptance_failure'] and m['linked'] and m['fresh']:
        basis.append(f"{m['n_fail']} executed declared check(s) failed on "
                     'linked, fresh evidence')
    if og == 'ACCEPT':
        basis.append(f"{m['n_check']} checks executed, linked/fresh/complete, "
                     'no failure; symptom gone (SCOPED P2P)')
    if og == 'REJECT' and not basis:
        basis.append('decisive rejection on linked/fresh acceptance failure')
    if og == 'NEED_EVIDENCE' and not basis:
        if not m['complete']:
            basis.append('declared scoped check set not fully executed')
        elif not m['fresh']:
            basis.append('freshness not adjudicated TRUE')
        else:
            basis.append('no decisive failure and insufficient success')
    return ' | '.join(basis)


def main():
    C.ensure_out_dirs()
    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')
    truths = C.read_jsonl(C.TRUTH)
    if len(truths) != C.MAX_NEW_ISSUES:
        raise SystemExit(f'expected {C.MAX_NEW_ISSUES} truth records, got '
                         f'{len(truths)}; finish g3c1_build first')
    restage = load_restage_cache()

    oracle_rows, metas = [], {}
    for t in sorted(truths, key=lambda r: r['instance_id']):
        m = _issue_facts(store, t, restage)
        m['oracle'] = oracle_gold(**m['facts'])
        metas[m['iid']] = m
        oracle_rows.append({
            'version': GOLD_VERSION + '+g3c1-v1',
            'instance_id': m['iid'], 'id': m['id'], 'repo': m['repo'],
            'base_commit': m['base'], 'patch_sha256': m['patch'],
            'artifact_id': m['aid'],
            'canon_run_tree': t.get('canon_run_tree'),
            'facts': {
                'linked': m['linked'], 'fresh': m['fresh'],
                'fresh_state_authoritative': m['fresh_state'],
                'restage_tree_matches_attestation': m['tree_match'],
                'restage_attestation_authentic': m['restage_authentic'],
                'complete': m['complete'],
                'attestation_authentic': True,
                'executed_check_count': m['n_check'],
                'executed_failure_count': m['n_fail'],
                'declared_missing_after_exec': m['missing'],
                'symptom_pre_passed': m['pre'],
                'symptom_post_passed': m['post'],
                'symptom_polarity': m['polarity']},
            'oracle_gold': m['oracle'],
            'oracle_basis': _oracle_basis(m),
            'coverage_scope_disclosure':
                'PASS_TO_PASS coverage is the attested SCOPED subset '
                '(test_patch files + tests/ adjacent to changed code files); '
                'the full dataset P2P suite is not executed locally, so '
                'oracle ACCEPT means scoped acceptability, not full-suite.',
            'resolved_in_dataset': t.get('resolved_in_dataset'),
            'pilot_queue_label': t.get('pilot_queue_label'),
            'primary_stratum': t.get('primary_stratum'),
            'builder_label_class_audit_only': t.get('label_class'),
            **C.GOLD_AUTHORITY,
        })
    C.write_jsonl(ORACLE_OUT, oracle_rows)

    # --- 40 condition Sufficiency Certificates -----------------------------
    certs = []
    for iid in sorted(metas):
        m = metas[iid]
        rec = m['rec']
        patch = m['patch']
        pres_a = display_for_tier(store, rec, iid, patch, 'A')
        pf, pe = _executed_counts(pres_a)
        bundle = {
            'linked': m['linked'],
            'fresh': m['fresh'],
            'fresh_state_repaired': m['fresh_state'],
            'complete': m['complete'],
            'executed_failure_count': m['n_fail'],
            'executed_check_count': m['n_check'],
            'symptom_polarity': m['polarity'],
            'presented_a_record': pres_a,
            'presented_failure_count': pf,
            'presented_check_count': pe,
        }
        for cond in C.CONDITIONS:
            surface = project_surface(cond, bundle)
            g, inputs, basis = condition_gold(cond, bundle, surface)
            certs.append({
                'cert_version': C.G3C1_GOLD_CERT_VERSION,
                'gold_rule_version': GOLD_VERSION,
                'design_version': C.G3C1_DESIGN_VERSION,
                'instance_id': iid,
                'condition': cond,
                'oracle_gold': m['oracle'],
                'condition_gold': g,
                'condition_equals_oracle': g == m['oracle'],
                'sufficient_for_decision': g in ('ACCEPT', 'REJECT'),
                'decision': g,
                'projected_inputs': inputs,
                'surface_status': {
                    'linkage': surface['linkage']['status'],
                    'freshness': surface['freshness']['status'],
                    'coverage': surface['coverage']['status'],
                    'acceptance_outcomes':
                        surface['acceptance_outcomes']['status']},
                'projection_version': C.PROJECTION_V2_VERSION,
                'freshness_state': m['fresh_state'],
                'basis': basis,
                'gold_tier': C.GOLD_AUTHORITY['gold_tier'],
                'annotators': C.GOLD_AUTHORITY['annotators'],
                'annotator2': C.GOLD_AUTHORITY['annotator2'],
            })
    if len(certs) != C.MAX_NEW_ISSUES * len(C.CONDITIONS):
        raise SystemExit(f'expected {C.MAX_NEW_ISSUES*len(C.CONDITIONS)} '
                         f'certificates, got {len(certs)}')
    C.write_jsonl(CERT_OUT, certs)

    from collections import Counter
    od = Counter(r['oracle_gold'] for r in oracle_rows)
    cd = {}
    for c in certs:
        cd.setdefault(c['condition'], Counter())[c['condition_gold']] += 1
    cd = {k: dict(v) for k, v in cd.items()}
    suff = sum(1 for c in certs if c['sufficient_for_decision'])
    print(f'oracle rows: {len(oracle_rows)} -> {ORACLE_OUT.name}')
    for r in oracle_rows:
        print(f"  {r['instance_id']}: oracle={r['oracle_gold']:<14} "
              f"L={r['facts']['linked']} F={r['facts']['fresh']} "
              f"C={r['facts']['complete']} fails="
              f"{r['facts']['executed_failure_count']} "
              f"symptom={r['facts']['symptom_polarity']}")
    print('oracle distribution:', dict(od))
    print(f'certificates: {len(certs)} sufficient={suff} '
          f'need={len(certs)-suff} -> {CERT_OUT.name}')
    print('condition distribution:', json.dumps(cd))


if __name__ == '__main__':
    main()
