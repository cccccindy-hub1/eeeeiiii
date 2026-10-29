"""Gate G3-C.0 task 2 — NEW versioned restricted-evidence projection v2 that
removes the pass_to_pass_baseline Tier-2 redundancy. ZERO API. The frozen
views.py/server.py are imported and demonstrated against but NEVER edited; v2
is shown as an out-of-tree wrapper only.

Produces:
  * a field-by-field v1(frozen G3-B.3 diagnostic) vs v2(no-baseline-map)
    difference matrix over all 10 frozen served artifacts;
  * a machine non-interference scan (reusing the FROZEN g3b4 scanner, read
    only) proving v2 removes the tier-2 baseline map while tier-1 stays clean;
  * a channel-invariance proof (v2 == v1 minus exactly one top-level key; the
    static diagnostic block is byte-identical; the freshness/coverage/
    consistency/log endpoints never read that field);
  * a construct-impact note and the versioning/migration plan.

    uv run --python 3.13 -m evidence.g3c0_projection_v2
"""
from __future__ import annotations

import json

from evidence import g3c0_common as C
from evidence import g3b4_strict_audit as SCAN  # frozen scanner, read-only
from evidence.store import ArtifactStore
from evidence.views import display_for_tier, evidence_block, project_artifact

ORDERED = [f'sympy__sympy-{n}' for n in
           ('13615', '13974', '15349', '17318', '17630', '19783',
            '20590', '21847', '24213', '24443')]

# The single structural change proposed for Gate 3-C (documented, NOT applied
# to the frozen file). v2 = frozen neutralisation + frozen tier-D projection,
# then additionally drop the pre-patch base-commit per-test P2P map.
V2_ADDITIONALLY_REMOVED = ('pass_to_pass_baseline',)


def project_diagnostic_v2(v1_projected: dict) -> dict:
    """Out-of-tree demonstration of the proposed projection. It is EXACTLY the
    frozen v1 tier-D output with the redundant pre-patch baseline map removed;
    no other transformation is added, so any difference is attributable to
    that one field."""
    out = json.loads(json.dumps(v1_projected))  # deep copy, no shared refs
    for k in V2_ADDITIONALLY_REMOVED:
        out.pop(k, None)
    out['projection_version'] = C.PROJECTION_V2_VERSION
    return out


def main():
    store = ArtifactStore(str(C.G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    fz = json.loads(C.G3B3_DATA_FREEZE.read_text(encoding='utf-8'))
    aid_by_issue = {}
    for c in fz['cells']:
        aid_by_issue.setdefault(c['instance_id'], c['served_artifact_id'])

    per_issue = []
    top_level_matrix = {}
    v1_scan_tot = {'tier1': 0, 'tier2': 0}
    v2_scan_tot = {'tier1': 0, 'tier2': 0}

    for iid in ORDERED:
        rec, authentic = store.get(aid_by_issue[iid])
        assert authentic
        sha = rec.get('patch_sha256')
        v1 = display_for_tier(store, rec, iid, sha, 'D')
        v2 = project_diagnostic_v2(v1)

        # Field matrix from the FULL acceptance record (tier A) downwards.
        full = project_artifact(rec, 'A')
        for k in full.keys():
            top_level_matrix.setdefault(
                k, {'in_full_tier_A': True,
                    'removed_by_v1_tier_D': k not in v1,
                    'additionally_removed_by_v2': k in v1 and k not in v2,
                    'retained_structural_in_v2': k in v2})

        # Static diagnostic block must be identical (baseline never rendered).
        block_v1 = evidence_block(v1, 'D', symptom={'pre_patch_passed': False,
                                                    'post_patch_passed': True})
        block_v2 = evidence_block(v2, 'D', symptom={'pre_patch_passed': False,
                                                    'post_patch_passed': True})

        t1a, t2a, _ = SCAN._scan_text(json.dumps(v1, ensure_ascii=False))
        t1b, t2b, _ = SCAN._scan_text(json.dumps(v2, ensure_ascii=False))
        v1_scan_tot['tier1'] += len(t1a)
        v1_scan_tot['tier2'] += len(t2a)
        v2_scan_tot['tier1'] += len(t1b)
        v2_scan_tot['tier2'] += len(t2b)

        v1_minus = v1.copy()
        v1_minus.pop('pass_to_pass_baseline', None)
        v2_minus_tag = v2.copy()
        v2_minus_tag.pop('projection_version', None)
        equal_aside_from_field = (v1_minus == v2_minus_tag)

        per_issue.append({
            'issue': iid.split('-')[-1],
            'v1_baseline_map_present':
                isinstance(v1.get('pass_to_pass_baseline'), dict),
            'v1_baseline_n_tests':
                len(v1.get('pass_to_pass_baseline') or {}),
            'v2_baseline_map_present':
                'pass_to_pass_baseline' in v2,
            'v1_scan_tier1_forbidden': len(t1a),
            'v1_scan_tier2_baseline_gap': len(t2a),
            'v2_scan_tier1_forbidden': len(t1b),
            'v2_scan_tier2_baseline_gap': len(t2b),
            'static_diagnostic_block_byte_identical_v1_v2':
                block_v1 == block_v2,
            'v2_equals_v1_minus_baseline_field_plus_tag':
                equal_aside_from_field,
        })

    field_matrix = [
        {'field': k,
         'present_in_full_tier_A_record': v['in_full_tier_A'],
         'removed_by_frozen_v1_tier_D': v['removed_by_v1_tier_D'],
         'additionally_removed_by_proposed_v2':
             v['additionally_removed_by_v2'],
         'retained_as_structural_in_v2': v['retained_structural_in_v2']}
        for k, v in sorted(top_level_matrix.items())]
    v2_only_change = [f['field'] for f in field_matrix
                      if f['additionally_removed_by_proposed_v2']]

    channel_invariance = {
        'artifact_json': 'v2 differs from v1 ONLY in removing '
                         'pass_to_pass_baseline and adding a '
                         'projection_version tag (all 10 issues: '
                         f"{all(p['v2_equals_v1_minus_baseline_field_plus_tag'] for p in per_issue)})",
        'static_diagnostic_block':
            'byte-identical v1 vs v2 for all 10 issues (the baseline map was '
            'never rendered into the static block): '
            f"{all(p['static_diagnostic_block_byte_identical_v1_v2'] for p in per_issue)}",
        'freshness_endpoint':
            'server._freshness reads run_tree/attestation, never '
            'pass_to_pass_baseline (evidence/server.py L200-208)',
        'coverage_endpoint':
            'server._coverage reads fail_to_pass / pass_to_pass_scoped keys + '
            'attestation declared sets, never the baseline map '
            '(evidence/server.py L210-245)',
        'consistency_strict_endpoint':
            'under policy=strict,tier=D it adjudicates ONLY the registered '
            'symptom probe; the acceptance branch reads summary f2p/p2p '
            'counts, never pass_to_pass_baseline (evidence/server.py '
            'L413-462)',
        'log_endpoint':
            "the p2p_baseline RAW LOG is already denied at tier D via "
            "views.log_allowed/_ACCEPTANCE_LOGS and strict returns 403 "
            "before body read (views.py L38,L154-158; server.py L266-273); "
            "v2 removes only the embedded JSON map, not a log that was ever "
            "served",
        'linkage_endpoint': 'hashes/attestation based; does not surface the '
                            'baseline per-test map',
        'tier_A_unchanged': 'proposed change is scoped to the diagnostic '
                            'tier only; acceptance tier A output is untouched',
    }

    noninterference = {
        'scanner': 'frozen evidence.g3b4_strict_audit._scan_text (reused, not '
                   'modified)',
        'surfaces': 'canonical JSON of the projected active artifact for each'
                    ' of the 10 frozen served issues',
        'v1_total_tier1_forbidden_findings': v1_scan_tot['tier1'],
        'v1_total_tier2_baseline_gap_findings': v1_scan_tot['tier2'],
        'v2_total_tier1_forbidden_findings': v2_scan_tot['tier1'],
        'v2_total_tier2_baseline_gap_findings': v2_scan_tot['tier2'],
        'v2_tier1_clean': v2_scan_tot['tier1'] == 0,
        'v2_tier2_clean': v2_scan_tot['tier2'] == 0,
        'expected': 'v1 reproduces 10 tier-2 baseline-map findings (one per '
                    'issue); v2 removes all 10 while introducing zero tier-1 '
                    'findings and removing nothing else',
    }

    construct_impact = {
        'construct_affected': 'restricted-evidence (tier-D) information '
                              'MINIMISATION, not the evidence-availability '
                              'construct itself',
        'what_is_removed': 'a PRE-patch base-commit scoped P2P per-test '
                           'status map that is all-PASSED for all 10 issues '
                           '(zero ACCEPT/REJECT discrimination), reachable '
                           'only via an explicit get_test_artifact call',
        'what_is_preserved': 'symptom probe, linkage/provenance, freshness, '
                             'coverage declared/executed counts and missing '
                             'ids, declared scheduled counts, scope file '
                             'list, identity metadata, and the withholding '
                             'notes — i.e. every legitimate diagnostic '
                             'signal needed for P1',
        'could_v2_change_any_g3b3_verdict':
            'NO for the observed runs: none of the 7 GPT unsupported-ACCEPT '
            'cells fetched the artifact, and the only GPT cell that fetched '
            'it (20590) abstained; DeepSeek fetched in 8/10 and abstained '
            '10/10. The field had zero causal role (G3-B.4 finding); v2 is a'
            ' hygiene/minimisation tightening, not a re-interpretation of any'
            ' model behaviour.',
        'historical_reproducibility':
            'G3-B/G3-B.3 keep projection v1 byte-for-byte; Gate 3-C serves '
            'v2 and tags every record with projection_version so the two are'
            ' never conflated',
    }

    proposed_change = {
        'frozen_file_not_modified': 'evidence/views.py L32 stays as-is',
        'one_line_intent_for_new_code_path':
            "_ACCEPTANCE_RECORD_FIELDS_V2 = ('fail_to_pass', "
            "'pass_to_pass_scoped', 'pass_to_pass_baseline')  # Gate 3-C v2 "
            "tier-D only",
        'implementation_options': [
            'option A (preferred): a versioned project_artifact_v2 used only '
            'by Gate 3-C sessions, leaving project_artifact/v1 frozen',
            'option B: add the field to a v2 allow/deny table keyed by a '
            'session projection_version; deny-by-default deny list derived '
            'from this matrix'],
        'regression_tests_required_before_3c': [
            'assert pass_to_pass_baseline not in project_artifact_v2(rec,"D")',
            'assert project_artifact_v2(rec,"A") == project_artifact(rec,"A")',
            'assert evidence_block output identical v1/v2 at tier D',
            'assert frozen g3b3 artifacts re-project identically under v1',
            'run the g3b4 three-tier scanner over every v2 surface in the '
            'Gate 3-C mock gate and require tier1==tier2==0'],
    }

    versioning = {
        'v1': 'diagnostic-v1-g3b (frozen; G3-A..G3-B.3; baseline map retained)',
        'v2': C.PROJECTION_V2_VERSION + ' (Gate 3-C restricted tier)',
        'tagging': 'every served artifact/static block/tool payload carries '
                   'projection_version; the run row records it; analyses '
                   'stratify on it',
        'no_silent_swap': 'the version is shown in prompts/metadata and '
                          'recorded; historical gates are never re-projected',
    }

    out = {
        'document': 'Gate G3-C.0 task 2: versioned restricted-evidence '
                    'projection v2 (pass_to_pass_baseline removed), field '
                    'diff, non-interference test, channel invariance',
        'design_version': C.G3C0_DESIGN_VERSION,
        'projection_v2_version': C.PROJECTION_V2_VERSION,
        'api_calls_made': 0,
        'frozen_code_modified': False,
        'v2_single_additional_removed_field': v2_only_change,
        'top_level_field_matrix': field_matrix,
        'per_issue_offline_demonstration': per_issue,
        'non_interference_test': noninterference,
        'other_channels_unchanged_evidence': channel_invariance,
        'construct_impact': construct_impact,
        'proposed_change_and_migration': proposed_change,
        'versioning_plan': versioning,
    }
    C.OUT_PROJECTION.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_PROJECTION / 'g3c0_projection_v2_spec_and_test.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('v2 additionally removed:', v2_only_change)
    print('v1 tier1/tier2 findings:', v1_scan_tot)
    print('v2 tier1/tier2 findings:', v2_scan_tot)
    print('block identical all issues:',
          all(p['static_diagnostic_block_byte_identical_v1_v2']
              for p in per_issue))
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
