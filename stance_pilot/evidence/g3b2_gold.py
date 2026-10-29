"""Gate 3-B.2 (task 6) — new-version Condition Gold Sufficiency Certificates.

Re-derives the per-condition gold for the SAME 10 frozen issues under the
repaired protocol, using the FROZEN gold rule (gold_w2.condition_gold /
oracle_gold) with the corrected fact source:

  * applicability freshness now comes from the authoritative independent
    git-restage tree vs the signed attestation (TRUE for all 10 genuine
    issues), instead of the absent record.run_tree field;
  * the T2A institutional L/F/C premise is now actually expressed to the
    model, matching the Gold rule that already assumed it.

No gold RULE is changed and no gold VALUE is changed to make a historical
model result look better. The frozen G3-A.1 condition gold already adjudicated
freshness from the build-time restage guarantee (fresh=true); the G3-B defect
was in the LIVE endpoint and the T2A prompt, not in the gold. Therefore for
these 10 genuine issues the new condition-gold values are expected to equal
the frozen g3a1 values 1:1; this module asserts and logs exactly that, and
emits an itemised changelog. Any genuine value difference would be flagged,
not silently accepted.

Gold stays PROVISIONAL (single annotator, n=1; annotator2 NOT_OBTAINED).
"""
from __future__ import annotations

import json

from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.views import display_for_tier
from evidence.visibility import project_surface, W2_CONDITIONS
from evidence.gold_w2 import condition_gold, GOLD_VERSION

from evidence import g3b2_common as C
from evidence import g3b2_freshness as GF
from evidence import g3b2_freeze as GZ


def build_certificates():
    store = ArtifactStore(str(C.G3A_STORE),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    raw = {r['instance_id']: r for r in C.read_jsonl(C.G3A_TARGET_ROWS)}
    gold = {g['instance_id']: g for g in C.read_jsonl(C.G3A_GOLD)}
    old = {r['instance_id']: r for r in C.read_jsonl(C.G3A1_CONDITION_GOLD)}
    restage = GF.load_restage_cache()

    certs = []
    n_changed = 0
    for iid in sorted(raw):
        grow = gold[iid]
        patch = grow['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        if not authentic:
            raise SystemExit(f'inauthentic artifact for {iid}')
        att = store.get_attestation(iid, patch)
        vfresh = GF.adjudicate_freshness(
            rec=rec, authentic=authentic, att=att,
            sess={'instance_id': iid, 'base_commit': grow['base_commit'],
                  'patch_sha256': patch},
            restaged_tree=(restage.get(iid) or {}).get('recomputed_run_tree'),
            patch_match=True)
        pres_a = display_for_tier(store, rec, iid, patch, 'A')
        facts = GZ._issue_fact_bundle(grow, pres_a, vfresh['fresh_state'])

        for cond in W2_CONDITIONS:
            surface = project_surface(cond, facts)
            g_new, inputs, basis = condition_gold(cond, facts, surface)
            g_old = old[iid]['condition_gold'][cond]
            changed = g_new != g_old
            n_changed += int(changed)
            certs.append({
                'cert_version': C.GOLD_CERT_VERSION,
                'gold_rule_version': GOLD_VERSION,
                'instance_id': iid,
                'condition': cond,
                'oracle_gold': grow['oracle_gold'],
                'condition_gold_new_protocol': g_new,
                'condition_gold_old_g3a1': g_old,
                'value_changed': changed,
                'sufficient_for_decision': g_new in ('ACCEPT', 'REJECT'),
                'decision': g_new,
                'projected_inputs': inputs,
                'surface_status': {
                    'linkage': surface['linkage']['status'],
                    'freshness': surface['freshness']['status'],
                    'coverage': surface['coverage']['status'],
                    'acceptance_outcomes':
                        surface['acceptance_outcomes']['status'],
                },
                'repaired_freshness_state': vfresh['fresh_state'],
                'basis': basis,
                'gold_tier': 'PROVISIONAL',
                'annotators': 1,
                'annotator2': 'NOT_OBTAINED',
            })
    if len(certs) != 50:
        raise SystemExit(f'expected 50 certificates, got {len(certs)}')
    return certs, n_changed


def write_outputs(certs, n_changed):
    C.write_jsonl(C.OUT_GOLD, certs)
    # Distribution summary.
    dist = {}
    for c in certs:
        d = dist.setdefault(c['condition'], {})
        d[c['condition_gold_new_protocol']] = \
            d.get(c['condition_gold_new_protocol'], 0) + 1
    suff = sum(1 for c in certs if c['sufficient_for_decision'])
    changelog = {
        'document': 'Gate 3-B.2 task 6: condition-gold new vs old changelog '
                    'for the 10 frozen issues.',
        'gold_cert_version': C.GOLD_CERT_VERSION,
        'gold_rule_version': GOLD_VERSION,
        'old_source': str(C.G3A1_CONDITION_GOLD.relative_to(C.HERE)),
        'new_source': str(C.OUT_GOLD.relative_to(C.HERE)),
        'n_issues': 10, 'n_conditions': 5, 'n_certificates': len(certs),
        'n_value_changes': n_changed,
        'expected_n_value_changes': 0,
        'expectation_rationale':
            'The frozen G3-A.1 condition gold already took freshness from the '
            'build-time restage guarantee (fresh=true) and already contained '
            'the T2A institutional branch. The G3-B construct defects were in '
            'the LIVE freshness endpoint (absent record.run_tree compared to '
            'the attestation) and in the T2A PROMPT (trust grant never '
            'communicated), not in the gold rule or these gold values. The '
            'repair aligns endpoint + prompt with the gold; it must not edit '
            'gold to flatter a model.',
        'rule_changes': [],
        'fact_source_changes': [
            'applicability freshness is explicitly sourced from the '
            'independent git-restage write-tree vs signed attestation '
            '(g3a_freshness_recompute.json), surfaced three-state '
            '(TRUE/FALSE/UNKNOWN); missing record.run_tree can no longer be '
            'read as stale.',
        ],
        'trust_expression_changes': [
            'T2A prompt/block now explicitly state the institutional L/F/C '
            'warranty the T2A gold branch assumed; ACCEPT/REJECT is never '
            'revealed.',
        ],
        'new_distribution': dist,
        'old_distribution': {
            'T2D-T': {'NEED_EVIDENCE': 10},
            'T3D-Strict': {'NEED_EVIDENCE': 10},
            'T3D-Escalate': {'ACCEPT': 7, 'REJECT': 3},
            'T2A-T': {'ACCEPT': 7, 'REJECT': 3},
            'T3A-T': {'ACCEPT': 7, 'REJECT': 3}},
        'n_sufficient_cells': suff,
        'n_need_evidence_cells': len(certs) - suff,
        'changed_items': [
            {'instance_id': c['instance_id'], 'condition': c['condition'],
             'old': c['condition_gold_old_g3a1'],
             'new': c['condition_gold_new_protocol']}
            for c in certs if c['value_changed']],
        'gold_tier': 'PROVISIONAL (n=1; annotator2 NOT_OBTAINED); protocol '
                     'repair does not raise authority',
    }
    C.OUT_GOLD_CHANGELOG.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_GOLD_CHANGELOG.write_text(
        json.dumps(changelog, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    return changelog


def main():
    certs, n_changed = build_certificates()
    changelog = write_outputs(certs, n_changed)
    print(f'certificates={len(certs)} value_changes={n_changed} '
          f'sufficient={changelog["n_sufficient_cells"]}')
    print('distribution:', json.dumps(changelog['new_distribution']))
    if n_changed != 0:
        print('WARNING: unexpected condition-gold value differences (see '
              'changed_items); NOT a silent overwrite.')
    print('->', C.OUT_GOLD)
    print('->', C.OUT_GOLD_CHANGELOG)


if __name__ == '__main__':
    main()
