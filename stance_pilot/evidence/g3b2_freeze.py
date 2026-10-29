"""Gate 3-B.2 (task 1/6) — independent freeze manifest for the repaired protocol.

This is a NEW experimental version; it does NOT overwrite the frozen G3-B
manifest, prompts, gold, runner, the 100 result rows, tool logs, or analyses.
It re-derives the SAME 10 issues x 5 conditions (50 items; x2 mock models =
100 mock cells) and pins the repaired, g3b2-versioned served content:

  * prompt_version p3-ternary-g3b2-v1 with the g3b2 per-condition fingerprints
    (T2A institutional L/F/C grant; active three-state freshness note);
  * the repaired freshness facts (authoritative independent restage tree vs
    signed attestation; three-state TRUE/FALSE/UNKNOWN);
  * condition gold recomputed by the SAME frozen gold rule semantics but with
    the corrected fact source / trust expression (values must equal the frozen
    g3a1 condition gold for these 10 genuine issues — the repair fixes premises
    and the endpoint, not verdicts to make any model look better).

API budget is $0: no profile price/key and no real-call allow-list are frozen
here; the only executable this version admits is the deterministic mock. Gold
remains PROVISIONAL (n=1; annotator2 NOT_OBTAINED).
"""
from __future__ import annotations

import hashlib
import json

from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.views import display_for_tier
from evidence.visibility import W2_CONDITIONS, project_surface
from evidence.ternary import _executed_counts
from evidence.prompts import CLAIM_POSITIVE, ternary_tools
from evidence.phase3_run import ternary_condition_tier_policy

from evidence import g3b2_common as C
from evidence import g3b2_prompts as GP
from evidence import g3b2_freshness as GF

CONDITIONS = tuple(W2_CONDITIONS)
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')
MOCK_MODELS = ('mock-model-alpha', 'mock-model-beta')
ORDER_SEED = 7


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _issue_fact_bundle(gold_row, pres_a, fresh_repaired):
    f = gold_row['facts']
    pf, pe = _executed_counts(pres_a)
    bundle = {
        'linked': f['linked'],
        # Repaired authoritative freshness: the independent restage tree
        # matches the attestation for all 10 genuine issues -> True.
        'fresh': fresh_repaired == GF.FRESH_TRUE,
        'fresh_state_repaired': fresh_repaired,
        'complete': f['complete'],
        'executed_failure_count': f['executed_failure_count'],
        'executed_check_count': f['executed_check_count'],
        'symptom_polarity': f['symptom_polarity'],
        'presented_a_record': pres_a,
        'presented_failure_count': pf, 'presented_check_count': pe,
    }
    return bundle


def build_items():
    store = ArtifactStore(str(C.G3A_STORE),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    raw = {r['instance_id']: r for r in C.read_jsonl(C.G3A_TARGET_ROWS)}
    gold = {g['instance_id']: g for g in C.read_jsonl(C.G3A_GOLD)}
    cond_gold_old = {r['instance_id']: r
                     for r in C.read_jsonl(C.G3A1_CONDITION_GOLD)}
    restage = GF.load_restage_cache()

    items = []
    for iid in sorted(raw):
        r, grow = raw[iid], gold[iid]
        patch = grow['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        if not authentic:
            raise SystemExit(f'inauthentic artifact for {iid}')
        att = store.get_attestation(iid, patch)
        sess = {'instance_id': iid, 'base_commit': grow['base_commit'],
                'patch_sha256': patch}
        vfresh = GF.adjudicate_freshness(
            rec=rec, authentic=authentic, att=att, sess=sess,
            restaged_tree=(restage.get(iid) or {}).get('recomputed_run_tree'),
            patch_match=True)
        symptom = {'pre_patch_passed': grow['facts']['symptom_pre_passed'],
                   'post_patch_passed': grow['facts']['symptom_post_passed']}
        facts_bundle = None
        for cond in CONDITIONS:
            _, tier, _ = ternary_condition_tier_policy(cond)
            artifact_record = display_for_tier(store, rec, iid, patch, tier)
            if facts_bundle is None:
                facts_bundle = _issue_fact_bundle(
                    grow, display_for_tier(store, rec, iid, patch, 'A'),
                    vfresh['fresh_state'])
            item = {
                'id': r['id'], 'instance_id': iid, 'repo': r.get('repo'),
                'base_commit': grow['base_commit'], 'patch_sha256': patch,
                'issue': r['problem_statement'], 'patch': r['model_patch'],
                'condition': cond, 'served_artifact_id': aid,
                'claim': CLAIM_POSITIVE, 'with_claim': True,
                'symptom': symptom, 'evidence_tier': tier,
                'cell_key': f'g3b2:{iid}:{cond}',
                'artifact_record': artifact_record,
                '_presented_facts': project_surface(cond, facts_bundle),
                '_freshness_repaired': {
                    'fresh_state': vfresh['fresh_state'],
                    'fresh': vfresh['fresh'],
                    'run_tree_match': vfresh['run_tree_match'],
                    'status_reason': vfresh['status_reason'],
                    'authoritative_tree_source':
                        vfresh['authoritative_tree_source'],
                    'record_run_tree_present':
                        vfresh['record_run_tree_present'],
                },
                '_oracle_gold': grow['oracle_gold'],
                '_condition_gold_old': cond_gold_old[iid]['condition_gold'][cond],
            }
            items.append(item)
    if len(items) != 50:
        raise SystemExit(f'expected 50 g3b2 items, got {len(items)}')
    return items


def interleaved_order(items):
    """Same deterministic cyclic Latin-shift discipline as G3-B (seed 7), but
    over the two MOCK models; 100 balanced cells."""
    base = []
    for cond in CONDITIONS:
        base.append((MOCK_MODELS[0], cond))
        base.append((MOCK_MODELS[1], cond))
    issues = sorted({it['instance_id'] for it in items})
    by = {(it['instance_id'], it['condition']): it for it in items}
    order = []
    for b, iid in enumerate(issues):
        block = base[b % len(base):] + base[:b % len(base)]
        for model, cond in block:
            it = by[(iid, cond)]
            order.append({'serial': len(order), 'mock_model': model,
                          'instance_id': iid, 'condition': cond,
                          'cell_key': it['cell_key'],
                          'served_artifact_id': it['served_artifact_id']})
    from collections import Counter
    cnt = Counter((o['mock_model'], o['condition']) for o in order)
    if len(order) != 100 or len(cnt) != 10 or set(cnt.values()) != {10}:
        raise SystemExit(f'g3b2 order balance broken: {dict(cnt)}')
    return order


def _rendered_block(item):
    return GP.g3b2_evidence_block(item['artifact_record'],
                                  tier=item['evidence_tier'],
                                  symptom=item.get('symptom'))


def build_freeze():
    parent = C.verify_frozen_parents()
    items = build_items()
    order = interleaved_order(items)

    prompt_fp = {c: GP.g3b2_prompt_fingerprint(c) for c in CONDITIONS}

    cells, served = [], []
    for o in order:
        it = next(x for x in items
                  if x['instance_id'] == o['instance_id']
                  and x['condition'] == o['condition'])
        active = o['condition'] in ACTIVE_CONDITIONS
        cells.append({
            'serial': o['serial'], 'mock_model': o['mock_model'],
            'instance_id': it['instance_id'], 'id': it['id'],
            'condition': it['condition'], 'cell_key': it['cell_key'],
            'served_artifact_id': it['served_artifact_id'],
            'evidence_tier': it['evidence_tier'], 'active_tools': active,
            'n_static_turns': 1 if not active else None,
            'prompt_version': C.PROMPT_VERSION,
            'protocol_version': C.PROTOCOL_VERSION,
            'prompt_fingerprint': prompt_fp[it['condition']],
            'tools_fingerprint': _sha(json.dumps(
                ternary_tools(it['condition']) or [],
                sort_keys=True, ensure_ascii=False).encode()),
            'audit_oracle_gold': it['_oracle_gold'],
            'audit_condition_gold_old_protocol': it['_condition_gold_old'],
            'fresh_state_repaired': it['_freshness_repaired']['fresh_state'],
        })
        payload = {
            'id': it['id'], 'instance_id': it['instance_id'],
            'base_commit': it['base_commit'], 'patch_sha256': it['patch_sha256'],
            'issue': it['issue'], 'patch': it['patch'],
            'claim': it['claim'], 'symptom': it['symptom'],
            'condition': it['condition'], 'evidence_tier': it['evidence_tier'],
            'rendered_static_block': _rendered_block(it),
            'artifact_record': it['artifact_record'],
        }
        served.append({'cell_key': it['cell_key'],
                       'instance_id': it['instance_id'],
                       'condition': it['condition'],
                       'served_payload_sha256': _sha(json.dumps(
                           payload, sort_keys=True, ensure_ascii=False).encode())})

    # Repaired freshness must be TRUE for all 10 genuine issues.
    fresh_states = {}
    for it in items:
        fresh_states.setdefault(it['instance_id'],
                                it['_freshness_repaired']['fresh_state'])
    n_true = sum(1 for s in fresh_states.values() if s == GF.FRESH_TRUE)

    freeze = {
        'freeze_id': 'groundedreview-gate3b2-zero-api-protocol-repair-v1',
        'gate': C.GATE,
        'approval': ('Gate 3-B.1 construct audit ACCEPTED; Gate 3-B.2 '
                     'authorised as a ZERO-API independent protocol repair. '
                     'No real model call, no new issue, no Gate 3-C, no '
                     'Gemini/R2, no git commit. This version does not '
                     'overwrite any frozen G3-B artifact.'),
        'gold_tier': ('PROVISIONAL (mechanically adjudicated, single '
                      'annotator n=1; annotator2 NOT_OBTAINED). Protocol '
                      'repair does NOT raise gold authority.'),
        'protocol_version': C.PROTOCOL_VERSION,
        'prompt_version': C.PROMPT_VERSION,
        'gold_cert_version': C.GOLD_CERT_VERSION,
        'conditions': list(CONDITIONS),
        'static_conditions': list(STATIC_CONDITIONS),
        'active_tool_conditions': list(ACTIVE_CONDITIONS),
        'mock_models': list(MOCK_MODELS),
        'real_models': [],
        'api_budget_usd': 0.0,
        'n_independent_issues': 10,
        'n_items': 50,
        'n_mock_cells': 100,
        'repaired_freshness_distribution': {
            'n_true': n_true, 'n_total_issues': len(fresh_states),
            'per_issue': fresh_states,
            'authoritative_source':
                'evidence_store_g3a/audit/g3a_freshness_recompute.json '
                '(independent git restage write-tree vs signed attestation)',
        },
        'prompt_fingerprints': prompt_fp,
        'call_order_seed': ORDER_SEED,
        'parent_freeze_verification': parent,
        'cells': cells,
        'served_payloads': served,
        'call_order': order,
        'g3b2_code_hashes': _g3b2_code_hashes(),
        'repair_scope': {
            'freshness_three_state': True,
            't2a_institutional_trust_grant': True,
            'gold_rules_modified': False,
            'gold_values_changed_for_these_10_issues': False,
            'frozen_artifacts_modified': False,
            'real_model_calls': False,
            'git_commit': False,
        },
    }
    return freeze


def _g3b2_code_hashes():
    names = ['g3b2_common.py', 'g3b2_freshness.py', 'g3b2_server.py',
             'g3b2_freshness_test.py', 'g3b2_prompts.py',
             'g3b2_freeze.py']
    return {n: (C.sha256_file(C.EVID / n) if (C.EVID / n).exists() else None)
            for n in names}


def canonical_bytes(freeze):
    return (json.dumps(freeze, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def main():
    freeze = build_freeze()
    C.OUT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_FREEZE.write_bytes(canonical_bytes(freeze))
    print(f'g3b2 freeze -> {C.OUT_FREEZE}')
    print(f"items={freeze['n_items']} mock_cells={freeze['n_mock_cells']} "
          f"freshness TRUE {freeze['repaired_freshness_distribution']['n_true']}"
          f"/{freeze['repaired_freshness_distribution']['n_total_issues']}")
    print('parent frozen files verified:',
          {k: v.get('files_verified') for k, v in
           freeze['parent_freeze_verification'].items()
           if isinstance(v, dict) and 'files_verified' in v})


if __name__ == '__main__':
    main()
