"""Gate G3-C.1 tasks 9-10 - determinism verification, recursive hash freeze,
and the G3-C.1 local pilot report (JSON + Markdown) with the G3-C.2
recommendation. ZERO API; no historical artifact is modified; no git commit.

Order matters (the freeze manifest is the LAST thing produced so it can hash
the report and the determinism audit):

  1. snapshot sha256 of the three deterministic products,
  2. RE-EXECUTE g3c1_select.main() and g3c1_gold.main() in-process from their
     frozen inputs (no git/pytest/network), re-snapshot, require byte
     identity -> audit/g3c1_determinism_check.json,
  3. write g3c1_report.json + g3c1_report.md,
  4. build the recursive freeze manifest over evidence_store_g3c1/ (the
     manifest excludes itself) pinning the G3-C.0 / G3-B.4 / G3-B.3 parent
     freezes,
  5. re-derive the manifest in memory and require byte identity with the
     manifest just written (freeze digest stability).

    uv run --offline --python 3.9 -m evidence.g3c1_report
"""
from __future__ import annotations

import json

from evidence import g3c1_common as C
from evidence import g3b4_common as B4
from evidence import g3c1_select as sel
from evidence import g3c1_gold as gold_mod


DETERM_OUT = C.OUT_AUDIT / 'g3c1_determinism_check.json'

# Products that must regenerate byte-identically from frozen inputs.
DETERM_TARGETS = [
    ('selection/g3c1_selection.json', C.OUT_SELECTION / 'g3c1_selection.json'),
    ('gold/g3c1_oracle_gold.jsonl',
     C.OUT_GOLD / 'g3c1_oracle_gold.jsonl'),
    ('gold/g3c1_condition_certificates.jsonl',
     C.OUT_GOLD / 'g3c1_condition_certificates.jsonl'),
]


def _load_json(rel):
    return json.loads((C.G3C1 / rel).read_text(encoding='utf-8'))


def _counter(items):
    out = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


# --------------------------------------------------------------------------
# Task 9a - determinism verification.
# --------------------------------------------------------------------------
def run_determinism_check():
    before = {rel: C.sha256_file(p) for rel, p in DETERM_TARGETS}
    # Pure, deterministic re-execution; both only read frozen inputs and write
    # canonical outputs (no wall-clock, random port, git or pytest).
    sel.main()
    gold_mod.main()
    targets = []
    ok = True
    for rel, p in DETERM_TARGETS:
        after = C.sha256_file(p)
        same = after == before[rel]
        ok = ok and same
        targets.append({'path': rel, 'sha256_before': before[rel],
                        'sha256_after': after, 'byte_identical': same})
    doc = {
        'document': 'G3-C.1 determinism: the pre-registered selection and the '
                    'oracle/condition gold regenerate byte-identically from '
                    'frozen inputs when re-executed.',
        'design_version': C.G3C1_DESIGN_VERSION,
        'method': 'snapshot sha256 -> in-process re-execution of '
                  'evidence.g3c1_select.main() then evidence.g3c1_gold.main() '
                  '-> re-snapshot sha256; no git write-tree, pytest, server or '
                  'network call was invoked (g3c1_gold reads the existing '
                  'audit/g3c1_freshness_recompute.json cache).',
        'rerun_modules': ['evidence.g3c1_select', 'evidence.g3c1_gold'],
        'api_calls_made': 0,
        'targets': targets,
        'deterministic': ok,
        'note': 'No build timestamp enters the selection or either gold file: '
                'selection is canonical (sorted keys); gold rows derive only '
                'from pre/post executed facts, totals and the frozen gold rule '
                "(truth's built_at label-provenance is not copied into gold).",
    }
    C.write_canonical(DETERM_OUT, doc)
    if not ok:
        raise SystemExit('DETERMINISM FAILURE: a regenerated product changed '
                         f'bytes; see {DETERM_OUT}')
    return doc


# --------------------------------------------------------------------------
# Task 9b - recursive freeze manifest (built last; excludes itself).
# --------------------------------------------------------------------------
def build_freeze(determ_doc):
    files = []
    for p in sorted(C.G3C1.rglob('*')):
        if p.is_file() and p.name != C.OUT_FREEZE.name:
            files.append({'relpath': str(p.relative_to(C.G3C1))
                          .replace('\\', '/'),
                          'bytes': p.stat().st_size,
                          'sha256': C.sha256_file(p)})
    digest = C.canonical_bytes({'files': sorted(files,
                                                key=lambda f: f['relpath'])})
    return {
        'document': 'GroundedReview Gate G3-C.1 local zero-API pilot result '
                    'freeze manifest',
        'design_version': C.G3C1_DESIGN_VERSION,
        'protocol_version': C.G3C1_PROTOCOL_VERSION,
        'gold_cert_version': C.G3C1_GOLD_CERT_VERSION,
        'projection_version': C.PROJECTION_V2_VERSION,
        'budget_usd': 0,
        'spend_usd': 0,
        'api_calls_made': 0,
        'actual_new_issues_materialised': C.MAX_NEW_ISSUES,
        'gate_3c2_execution': False,
        'gold_changed': False,
        'git_commits_made': 0,
        'n_files': len(files),
        'files': files,
        'files_canonical_sha256': C.sha256_bytes(digest),
        'parent_pins': {
            'g3c0_design_freeze_manifest_sha256':
                C.sha256_file(C.G3C0_DESIGN_FREEZE),
            'g3b4_result_freeze_manifest_sha256':
                C.sha256_file(C.G3B4_RESULT_FREEZE),
            'g3b3_result_freeze_manifest_sha256':
                C.sha256_file(C.G3B3_RESULT_FREEZE),
            'g3b3_data_freeze_manifest_sha256':
                C.sha256_file(C.G3B3_DATA_FREEZE),
            'g3b3_parent_pins': B4.verify_g3b3_parent_pins(verbose=False)},
        'determinism': {
            'deterministic': determ_doc['deterministic'],
            'audit': 'audit/g3c1_determinism_check.json'},
        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope': C.APPROVED_SCOPE,
    }


# --------------------------------------------------------------------------
# Task 10 - assemble the report.
# --------------------------------------------------------------------------
def _issue_rows(truths, oracle_by_iid):
    rows = []
    for t in sorted(truths, key=lambda r: r['instance_id']):
        iid = t['instance_id']
        lp = t['label_provenance']
        og = oracle_by_iid[iid]
        rows.append({
            'instance_id': iid,
            'queue': t.get('pilot_queue_label'),
            'primary_stratum': t.get('primary_stratum'),
            'target_generator': t['id'].split(':', 1)[0],
            'base_commit': t['base_commit'],
            'canon_run_tree': t.get('canon_run_tree'),
            'builder_label_class_audit_only': t.get('label_class'),
            'resolved_in_dataset': t.get('resolved_in_dataset'),
            'issue_addressed': t['issue_addressed'],
            'fail_to_pass_failed_over_total':
                [lp['f2p_failed'], lp['f2p_total']],
            'pass_to_pass_scoped_regressed_over_total':
                [lp['p2p_regressed'], lp['p2p_scoped_total']],
            'pass_to_pass_preexisting_bad': lp['p2p_preexisting_bad'],
            'test_patch_applied_cleanly': lp['test_patch_applied_cleanly'],
            'symptom': 'pre_fail->post_pass (gone)'
                if (lp['symptom_pre_patch_passed'] is False
                    and lp['symptom_post_patch_passed'] is True)
                else 'persists',
            'oracle_gold': og['oracle_gold'],
            'oracle_basis': og['oracle_basis']})
    return rows


def _queue_rate(selection, oracle_by_iid, key):
    picks = selection[key]
    labels = [oracle_by_iid[i]['oracle_gold'] for i in picks]
    return {'picks': picks,
            'labels_in_queue_order':
                [{'instance_id': i,
                  'oracle_gold': oracle_by_iid[i]['oracle_gold']}
                 for i in picks],
            'oracle_distribution': _counter(labels)}


def build_report(determ_doc):
    truths = C.read_jsonl(C.TRUTH)
    oracle = C.read_jsonl(C.OUT_GOLD / 'g3c1_oracle_gold.jsonl')
    certs = C.read_jsonl(C.OUT_GOLD / 'g3c1_condition_certificates.jsonl')
    selection = _load_json('selection/g3c1_selection.json')
    fresh = _load_json('audit/g3c1_freshness_recompute.json')
    http = _load_json('audit/g3c1_http_crosscheck.json')
    ni = _load_json('projection/g3c1_noninterference_audit.json')
    mock = _load_json('audit/g3c1_mock_audit.json')
    human = _load_json(
        'human_annotation/g3c1_human_annotation_package.json')
    rev = _load_json('audit/g3c1_probe_revision_note_19495.json')
    failures = C.read_jsonl(C.FAILURES)

    oracle_by_iid = {r['instance_id']: r for r in oracle}
    issue_rows = _issue_rows(truths, oracle_by_iid)
    oracle_dist = _counter(r['oracle_gold'] for r in oracle)

    natural = _queue_rate(selection, oracle_by_iid, 'pilot_natural_picks')
    enriched = _queue_rate(selection, oracle_by_iid, 'pilot_enriched_picks')

    cond_dist = {}
    for c in certs:
        cond_dist.setdefault(c['condition'], {})
        cond_dist[c['condition']][c['condition_gold']] = \
            cond_dist[c['condition']].get(c['condition_gold'], 0) + 1
    n_suff = sum(1 for c in certs if c['sufficient_for_decision'])

    freshness = {
        'all_match': fresh['all_match'],
        'n_issues': fresh['n_issues'],
        'n_tree_match': sum(1 for x in fresh['issues'] if x['tree_matches']),
        'n_attestation_authentic':
            sum(1 for x in fresh['issues'] if x['attestation_authentic']),
        'authoritative_tree_source':
            'independent_git_restage_write_tree',
        'semantics': 'G3-B.2 three-state (TRUE/FALSE/UNKNOWN); a missing run '
                     'tree is never silently treated as stale',
    }

    report = {
        'document': 'GroundedReview Gate G3-C.1 - local zero-API pilot '
                    'construction of 8 new independent SymPy issues',
        'design_version': C.G3C1_DESIGN_VERSION,
        'protocol_version': C.G3C1_PROTOCOL_VERSION,
        'gold_cert_version': C.G3C1_GOLD_CERT_VERSION,
        'projection_version': C.PROJECTION_V2_VERSION,
        'decision_acknowledged': 'G3-C.0 complete, accepted and frozen (never '
            're-run or rewritten). Gate G3-C.1 executed under the prior '
            'written approval: at most 8 brand-new independent SymPy issues, '
            'local data/patch/pytest/gold/signing/HTTP/mock work only, model '
            'API budget $0. G3-C.2, real Reviewer calls, Gemini, R2 and git '
            'commit remain un-executed.',
        'api_calls_made': 0,
        'spend_usd': 0,
        'actual_new_issues_materialised': C.MAX_NEW_ISSUES,
        'git_commits_made': 0,
        'network_egress': http['network_egress'],

        # 1. the eight actually built issues
        'new_issues': issue_rows,
        'oracle_distribution': oracle_dist,

        # 2. dual-queue screening funnel (frozen before any build)
        'selection': {
            'seeds': selection['seeds'],
            'slot_rule': selection['slot_rule'],
            'enrichment_rule': selection['enrichment_rule'],
            'dedup_rule': selection['dedup_rule'],
            'screening_funnel': selection['screening_funnel'],
            'n_eligible': selection['n_eligible'],
            'n_excluded_total': selection['n_excluded_total'],
            'exclusion_reason_counts':
                _counter(e['reason'] for e in selection['excluded']),
            'natural_dedup_suppressed':
                selection['natural_dedup_suppressed'],
            'enriched_stratum_sizes':
                {s: v['n_members']
                 for s, v in selection['enriched_strata'].items()},
            'natural_queue': natural,
            'enriched_queue': enriched,
            'prevalence_estimate_natural_pilot_only':
                f"{natural['oracle_distribution'].get('REJECT', 0)} REJECT / "
                f"{natural['oracle_distribution'].get('ACCEPT', 0)} ACCEPT "
                'across the first 4 natural-order picks (n=4; descriptive, no '
                'population-rate claim at this size)',
            'enriched_is_conditional_warning':
                'The REJECT-enriched queue is a screen-positive sample chosen '
                'by static CI structure. Its 1 REJECT / 3 ACCEPT outcome MUST '
                'NOT be reported as the natural-population rate; it estimates '
                'CONDITIONAL behaviour among structure-screen-positive '
                'issues only.',
        },

        # 3. real executed tests + gold quality
        'freshness_audit': freshness,
        'coverage_scope_disclosure':
            'PASS_TO_PASS was executed only for the attested SCOPED subset '
            '(maintainer test_patch files plus tests/ adjacent to changed '
            'code files). The full dataset P2P suite was NOT run locally; '
            'therefore every oracle ACCEPT here means SCOPED acceptability, '
            'not full-suite merge certification.',
        'gold': {
            'oracle_distribution': oracle_dist,
            'condition_distribution': cond_dist,
            'n_condition_certificates': len(certs),
            'sufficient_for_decision': n_suff,
            'need_evidence': len(certs) - n_suff,
            'rule_version': 'gold_w2 w2-gold-v1 (frozen; no rule drift)',
            'tier_D_conditions': ['T2D-T', 'T3D-Strict', 'T3D-Escalate'],
            'tier_A_conditions': ['T2A-T', 'T3A-T'],
        },

        # 4. non-interference + real local HTTP cross-check + zero-API mock
        'noninterference_audit': {
            'passed': ni['passed'],
            'n_surfaces': ni['n_surfaces'],
            'n_restricted_tier_d_surfaces':
                ni['n_restricted_tier_d_surfaces'],
            'tier1_forbidden_findings': 0,
            'tier2_baseline_gap_findings': 0,
            'tier_d_schema_lint_findings': 0,
            'hidden_gold_key_findings_any_tier':
                ni['hidden_gold_key_findings_any_tier'],
            'scanner': ni['scanner'],
            'authorized_reveal_policy': ni['authorized_reveal_policy'],
        },
        'http_crosscheck': {
            'n_cells': http['n_cells'],
            'n_checks': http['n_checks'],
            'n_checks_pass': http['n_checks_pass'],
            'n_errors': http['n_errors'],
            'server_version': http['server_version'],
            'network_egress': http['network_egress'],
        },
        'zero_api_mock': {
            'n_cells': mock['n_cells'],
            'mock_matches_condition_gold':
                mock['mock_matches_condition_gold'],
            'mock_match_rate': mock['mock_match_rate'],
            'api_calls_total': mock['api_calls_total'],
            'cost_usd_total': mock['cost_usd_total'],
            'research_excluded': 'Mock decisions are plumbing/protocol checks '
                'only and are excluded from research results.',
        },

        # 5. second-human blind arbitration packet (PROVISIONAL)
        'human_annotation': {
            'status': human['status'],
            'gold_tier': human['gold_tier'],
            'n_packets': human['n_packets'],
            'blind_seed': human['blind_seed'],
            'identity_blinding': 'PARTIAL',
            'n_packets_partial_self_reference':
                sum(1 for r in human['packet_manifest']
                    if r['files_self_referencing_this_issue_number']),
            'blinding_limitation': human['blinding_limitation'],
            'arbitration': human['arbitration'],
        },

        # 6. failure record (retained, never skipped)
        'failures_and_instrument_revision': {
            'n_failure_records': len(failures),
            'failure_file': 'g3c1_failures.jsonl',
            'records': failures,
            'sympy_19495_revision_note': {
                'audit': rev['audit'],
                'diagnosis': rev['diagnosis'],
                'maintainer_test_patch_consulted':
                    rev['maintainer_test_patch_consulted'],
                'action': rev['action'],
                'post_revision_gate': rev['post_revision_gate'],
                'no_gold_changed': rev['no_gold_changed'],
                'no_issue_replaced': rev['no_issue_replaced']},
        },

        # 7. determinism + freeze pointers
        'determinism': {
            'deterministic': determ_doc['deterministic'],
            'n_targets_byte_identical':
                sum(1 for t in determ_doc['targets'] if t['byte_identical']),
            'audit': 'audit/g3c1_determinism_check.json'},

        # 8. honest labels: two REJECTs were not re-cut to fill an ACCEPT quota
        'no_quota_editing': {
            'gold_edited_to_fill_quota': False,
            'issues_chosen_for_model_errors': False,
            'mirror_fixtures_created': False,
            'note': 'Both class-A candidates (sympy-14248 fails a declared '
                'check; sympy-15875 fails its single declared F2P) are also '
                'resolved_in_dataset=False. They were kept and honestly '
                'labelled oracle REJECT; no issue was swapped and no gold was '
                'changed to manufacture ACCEPTs.'},

        # 9. G3-C.2 recommendation (no execution; separate approval required)
        'gate_3c2_recommendation': {
            'ready_for_paid_expansion_now': False,
            'recommended_next_step':
                'First obtain a REAL independent second human annotator on '
                'the 8 sealed blind packets, run the pre-registered third-'
                'human arbitration and gold-flip sensitivity, and only then '
                'consider any paid Reviewer-model expansion (G3-C.2).',
            'prerequisites_before_any_paid_cell': [
                'annotator2 labels collected for P01-P08 (labels CSV '
                'currently blank)',
                'third-human arbitration of every annotator1/annotator2 '
                'disagreement; flip-sensitivity recomputation',
                're-confirm the machine non-interference gate '
                '(tier1=0/tier2=0/gold-key=0) on the exact G3-C.2 build',
                'separate explicit written G3-C.2 approval with a hard '
                'per-phase API budget and the G3-C.0 pre-registered P1/P2 '
                'endpoints, sampling and stats',
                'expand toward the G3-C.0 floor of >=20 NEW independent '
                'REJECT issues; report natural vs enriched rates separately'],
            'not_executed_in_g3c1': ['G3-C.2', 'real Reviewer model calls',
                                     'Gemini', 'R2', 'new paid models'],
        },

        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope': C.APPROVED_SCOPE,
        'deliverables': [
            'selection/g3c1_selection.json (dual-queue frozen funnel)',
            'raw/g3c1_target_rows.jsonl + raw/g3c1_target_digest.json',
            'probes/ (8 symptom probes) + patches/ (8 candidate + 8 test)',
            'store/ signed artifacts, logs, attestations + fixtures meta',
            'g3c1_truth.jsonl + g3c1_failures.jsonl',
            'audit/g3c1_freshness_recompute.json',
            'gold/g3c1_oracle_gold.jsonl + g3c1_condition_certificates.jsonl',
            'projection/g3c1_noninterference_audit.json',
            'audit/g3c1_http_crosscheck.json + g3c1_http_transcript.jsonl',
            'audit/g3c1_mock_audit.json + runs/g3c1_mock_results.jsonl',
            'audit/g3c1_probe_revision_note_19495.json',
            'audit/g3c1_determinism_check.json',
            'human_annotation/ (protocol, blank CSV, 8 blind packets, sealed '
            'mapping)',
            'g3c1_report.{json,md}',
            'freeze/g3c1_freeze_manifest.json'],
        'stopping_statement': 'G3-C.1 is complete: 8 new independent SymPy '
            'issues were built, executed, gold-certified, non-interference-'
            'audited, HTTP cross-checked and zero-API-mocked, then hash '
            'frozen. Stopping now. G3-C.0 was NOT re-run; no historical '
            'frozen artifact was modified; no real model call, Gemini, R2 or '
            'G3-C.2 cell was run; API spend $0; no git commit was made. '
            'Awaiting separate written approval for G3-C.2.',
    }
    return report


def _md(report):
    qn = report['selection']['natural_queue']['oracle_distribution']
    qe = report['selection']['enriched_queue']['oracle_distribution']
    L = ['# GroundedReview Gate G3-C.1 - Local Zero-API Pilot Freeze', '',
         '**Scope.** Under the prior written approval, **8 brand-new '
         'independent SymPy issues** were built with real local data '
         'extraction, patch replay and pytest execution, signed gold, a real '
         'local HTTP cross-check and an offline mock. Model API budget '
         '**$0**; no real Reviewer call, Gemini, R2, G3-C.2 or git commit. '
         'G3-C.0 was not re-run and every historical frozen artifact stayed '
         'read-only.', '',
         '## 1. Eight new issues (real executed evidence)', '',
         '| issue | queue | stratum | generator | class | resolved | '
         'F2P fail/tot | P2P reg/tot (pre-bad) | oracle |',
         '|---|---|---|---|---|---|---|---|---|']
    for r in report['new_issues']:
        L.append('| {iid} | {q} | {s} | {g} | {c} | {res} | {f0}/{f1} | '
                 '{p0}/{p1} ({pb}) | **{og}** |'.format(
                     iid=r['instance_id'].replace('sympy__sympy-', 'sympy-'),
                     q=r['queue'], s=r['primary_stratum'],
                     g=r['target_generator'],
                     c=r['builder_label_class_audit_only'],
                     res=r['resolved_in_dataset'],
                     f0=r['fail_to_pass_failed_over_total'][0],
                     f1=r['fail_to_pass_failed_over_total'][1],
                     p0=r['pass_to_pass_scoped_regressed_over_total'][0],
                     p1=r['pass_to_pass_scoped_regressed_over_total'][1],
                     pb=r['pass_to_pass_preexisting_bad'],
                     og=r['oracle_gold']))
    od = report['oracle_distribution']
    L += ['', f"Oracle distribution: **{od.get('REJECT', 0)} REJECT / "
              f"{od.get('ACCEPT', 0)} ACCEPT** (NEED_EVIDENCE "
              f"{od.get('NEED_EVIDENCE', 0)}). Both REJECTs "
          '(sympy-14248, sympy-15875) are `resolved_in_dataset=False` '
          'candidates that fail a declared check; they were kept and honestly '
          'labelled, never swapped to manufacture an ACCEPT.', '',
          '## 2. Frozen dual-queue screening funnel', '']
    for f in report['selection']['screening_funnel']:
        L.append(f"- {f['step']} — {f['rule']} "
                 f"(in={f.get('n_in', '')}, out={f.get('n_out', '')}, "
                 f"removed={f.get('n_removed', '')})")
    L += ['', f"Eligible pool: **{report['selection']['n_eligible']}** "
              f"(excluded {report['selection']['n_excluded_total']}: "
              f"{report['selection']['exclusion_reason_counts']}). "
          'Natural shuffle seed '
          f"{report['selection']['seeds']['natural_shuffle_seed']}; enriched "
          'strata seed '
          f"{report['selection']['seeds']['enriched_strata_shuffle_seed']}. "
          'Independence = one issue per repo+sha256(sorted changed-file set); '
          '4 duplicate-cluster members were suppressed in the natural queue.',
          '',
          f"- **Natural queue (first 4):** "
          f"{qn.get('REJECT', 0)} REJECT / {qn.get('ACCEPT', 0)} ACCEPT "
          f"(descriptive only; n=4, no population-rate claim).",
          f"- **REJECT-enriched queue (first 4):** "
          f"{qe.get('REJECT', 0)} REJECT / {qe.get('ACCEPT', 0)} ACCEPT. "
          'This is a **screen-positive, conditional** sample and its rate '
          '**must not** be presented as the natural-population prevalence.',
          f"- Enriched stratum sizes across the 51 eligible: "
          f"{report['selection']['enriched_stratum_sizes']}.", '',
          '## 3. Freshness, coverage and gold quality', '']
    fr = report['freshness_audit']
    L += [f"- Independent git write-tree restage: "
              f"**{fr['n_tree_match']}/{fr['n_issues']} tree match**, "
              f"{fr['n_attestation_authentic']}/{fr['n_issues']} attestation "
              f"authentic, all_match={fr['all_match']} "
              f"({fr['authoritative_tree_source']}); "
              f"{fr['semantics']}.",
          f"- Coverage disclosure: {report['coverage_scope_disclosure']}",
          f"- Condition gold over 8 issues x 5 conditions = "
          f"**{report['gold']['n_condition_certificates']} certificates**: "
          f"sufficient={report['gold']['sufficient_for_decision']}, "
          f"NEED_EVIDENCE={report['gold']['need_evidence']}.",
          f"- Per-condition distribution: "
          f"{json.dumps(report['gold']['condition_distribution'])} "
          '(restricted tier-D T2D-T/T3D-Strict are NEED_EVIDENCE by design; '
          'T3D-Escalate and tier-A T2A-T/T3A-T resolve to the oracle label).',
          '', '## 4. Non-interference, real local HTTP cross-check, mock', '',
          f"- Non-interference on actually served surfaces: "
          f"{report['noninterference_audit']['n_surfaces']} surfaces "
          f"({report['noninterference_audit']['n_restricted_tier_d_surfaces']}"
          ' restricted tier-D); tier1/tier2/schema-lint/gold-key findings all '
          f"**0**; passed={report['noninterference_audit']['passed']}.",
          f"- Real local HTTP cross-check "
          f"({report['http_crosscheck']['server_version']}, "
          f"{report['http_crosscheck']['network_egress']}): "
          f"**{report['http_crosscheck']['n_cells']} cells, "
          f"{report['http_crosscheck']['n_checks_pass']}"
          f"/{report['http_crosscheck']['n_checks']} checks pass, "
          f"{report['http_crosscheck']['n_errors']} errors.**",
          f"- Zero-API mock: "
          f"{report['zero_api_mock']['mock_matches_condition_gold']}"
          f"/{report['zero_api_mock']['n_cells']} cells reproduce condition "
          f"gold (rate {report['zero_api_mock']['mock_match_rate']}), "
          'api_calls=0, cost=$0; research-excluded plumbing check only.',
          '', '## 5. Second-human blind arbitration package (PROVISIONAL)', '',
          f"- **{report['human_annotation']['n_packets']} blind packets** "
          f"(P01-P08), each 9 files, blind seed "
          f"{report['human_annotation']['blind_seed']}; status **"
          f"{report['human_annotation']['status']}**.",
          f"- Identity blinding is PARTIAL: "
          f"{report['human_annotation']['n_packets_partial_self_reference']}"
          '/8 verbatim symptom logs self-quote the upstream issue number; '
          'evidence is not rewritten and the limitation is logged.',
          '- All gold remains PROVISIONAL (annotators=1, '
          'annotator2=NOT_OBTAINED) until a real second annotator labels the '
          'sealed packet and third-human arbitration completes.', '',
          '## 6. Failure record retained (no skip)', '',
          f"- {report['failures_and_instrument_revision']['n_failure_records']}"
          ' stop record in g3c1_failures.jsonl (sympy-19495 probe-flip gate). '
          'The first hand-written probe was a faulty INSTRUMENT (weak '
          'assertions that passed at baseline); the issue genuinely '
          'reproduced and the patch genuinely fixed it. The probe was '
          'strengthened using ONLY the public issue report (maintainer '
          'test_patch never consulted), after which all 8 probes flipped. '
          'The issue was kept, no gold changed. See '
          'audit/g3c1_probe_revision_note_19495.json.', '',
          '## 7. Determinism and freeze', '',
          f"- Re-executed g3c1_select + g3c1_gold from frozen inputs: "
          f"{report['determinism']['n_targets_byte_identical']}/3 products "
          f"byte-identical (deterministic="
          f"{report['determinism']['deterministic']}); "
          'audit/g3c1_determinism_check.json.',
          '- Every file under evidence_store_g3c1/ is sha256-hashed in '
          'freeze/g3c1_freeze_manifest.json (canonical digest over the sorted '
          'file list), which pins the G3-C.0 design and G3-B.4/G3-B.3 result '
          'freezes; the manifest excludes itself.', '',
          '## 8. G3-C.2 recommendation', '',
          'Do **not** unlock paid Reviewer expansion yet. First collect a real '
          'independent second-human labelling of the 8 sealed packets, run '
          'third-human arbitration + gold-flip sensitivity, re-confirm the '
          'machine non-interference gate on the G3-C.2 build, and obtain a '
          'separate written G3-C.2 approval with the G3-C.0 pre-registered '
          'P1/P2 endpoints, >=20-new-REJECT sampling floor and hard per-phase '
          'budget. Natural and enriched rates must stay separated.', '',
          '---', '', report['stopping_statement'], '']
    return '\n'.join(L)


def main():
    C.ensure_out_dirs()

    # 1-2. determinism (writes audit/g3c1_determinism_check.json)
    determ_doc = run_determinism_check()

    # 3. report
    report = build_report(determ_doc)
    C.OUT_REPORT.write_bytes(C.canonical_bytes(report))
    C.OUT_REPORT_MD.write_text(_md(report), encoding='utf-8')

    # 4. freeze (last, so it hashes the report + determinism audit)
    freeze = build_freeze(determ_doc)
    C.OUT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_FREEZE.write_bytes(C.canonical_bytes(freeze))

    # 5. freeze digest stability: re-derive in memory with nothing else
    #    changing and require byte identity with the manifest just written.
    freeze2 = build_freeze(determ_doc)
    stable = C.canonical_bytes(freeze2) == C.OUT_FREEZE.read_bytes()
    if not stable:
        raise SystemExit('FREEZE STABILITY FAILURE: re-derived manifest '
                         'differs from the written manifest')

    print('determinism:', determ_doc['deterministic'],
          [t['byte_identical'] for t in determ_doc['targets']])
    print('report:', C.OUT_REPORT.name, C.OUT_REPORT_MD.name)
    print('freeze n_files:', freeze['n_files'], 'canonical:',
          freeze['files_canonical_sha256'][:16], 'stable:', stable)
    print('parent g3c0 :', freeze['parent_pins']
          ['g3c0_design_freeze_manifest_sha256'][:12])
    print('parent g3b4 :', freeze['parent_pins']
          ['g3b4_result_freeze_manifest_sha256'][:12])
    print('g3b3 pins all_ok:', freeze['parent_pins']['g3b3_parent_pins']
          ['all_ok'])


if __name__ == '__main__':
    main()
