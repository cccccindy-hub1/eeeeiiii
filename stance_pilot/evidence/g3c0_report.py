"""Gate G3-C.0 task 11-12 — assemble the design report (JSON + Markdown),
state the paper claim boundaries, and write the G3-C.0 design freeze manifest
(recursive sha256 over evidence_store_g3c0 plus the G3-B.4/G3-B.3 parent
pins). ZERO API; nothing historical is modified; no git commit.

    uv run --python 3.13 -m evidence.g3c0_report
"""
from __future__ import annotations

import json

from evidence import g3c0_common as C
from evidence import g3b4_common as B4


def _load(rel):
    return json.loads((C.G3C0 / rel).read_text(encoding='utf-8'))


def claim_boundaries():
    """Task 11 — the research-claim perimeter for the paper."""
    return {
        'central_research_question': 'Can code-review agents distinguish '
            'evidence INTEGRITY (trusted provenance, complete execution) from'
            ' evidence SUFFICIENCY (enough to accept the patch)? This is the'
            ' organising question; it remains a hypothesis under external '
            'validation, not a conclusion.',
        'results_claims': [
            {'boundary': 'DeepSeek earlier 9/10 over-abstention',
             'allowed_wording': 'the originally observed 9/10 sufficient-'
                 'evidence abstention was substantially driven by protocol/'
                 'instrument construct problems (G3-B stale freshness and '
                 'coverage/trust handling); after the G3-B.3 corrective '
                 'replication the paired need-any rate moved 9/10 -> 1/10 '
                 '(issue-cluster bootstrap 95% CI for the paired difference '
                 '0.5-1.0). Report ONLY as an associational before/after '
                 'contrast.',
             'forbidden_wording': 'do NOT call the old 9/10 robust evidence '
                 'of a stable DeepSeek intrinsic over-abstention defect.'},
            {'boundary': 'GPT T3D-Strict 7/10 unsupported ACCEPT',
             'allowed_wording': 'an operationally defined OBSERVATION: under '
                 'a condition gold of NEED_EVIDENCE, GPT returned ACCEPT on '
                 '7/10 cells with 0 unsupported REJECT and 3 correct '
                 'abstentions; all 7 structurally upgraded non-decisive '
                 'linked/fresh/coverage/symptom evidence into acceptance; a '
                 'single AI, rule-based partial-blind coding labelled 7/7 '
                 'C3. n=10, PROVISIONAL gold, Wilson95 ~[0.40,0.89].',
             'forbidden_wording': 'do NOT claim the active-query -> over-'
                 'commitment mechanism is demonstrated/causal (freshness and'
                 ' trust changed with activeness across versions); do NOT '
                 'present AI coding as independent human adjudication.'},
            {'boundary': 'GPT sufficient-evidence false ACCEPT (P2)',
             'allowed_wording': 'the failure to use a visible decisive '
                 'failure persists as specific cases (SymPy-17318 T2A) but '
                 'only n=3 independent REJECT issues exist, so report cases, '
                 'not a population rate.',
             'forbidden_wording': 'do NOT report a GPT false-accept RATE from'
                 ' n=3 negatives, nor pool P1 and P2 into one hallucination '
                 'rate.'},
            {'boundary': 'residual DeepSeek abstention',
             'allowed_wording': 'post-repair the only sufficient-evidence '
                 'over-abstention is SymPy-13974 (n=1), a concrete evidence-'
                 'mis-read/policy error, not generalisable.',
             'forbidden_wording': 'do NOT generalise from the single 13974 '
                 'case to a model-wide tendency.'},
        ],
        'cross_cutting_constraints': [
            'all gold-dependent statements are PROVISIONAL until the second '
            'human annotator + third-human arbitration + flip sensitivity '
            'are complete',
            'every G3-B -> G3-B.3 and static -> active availability contrast '
            'is labelled ASSOCIATIONAL unless the orthogonal 2x2 is run',
            'disclose the tier-2 minimisation gap and that projection v2 '
            'removes it without affecting any other channel',
            'report the CompositeGuard first-run $0 failure and re-freeze, '
            'not only the final 100/100',
            'state the central question as a hypothesis pending independent '
            'generalisation in Gate 3-C'],
    }


def build_freeze(extra_parent):
    files = []
    for p in sorted(C.G3C0.rglob('*')):
        if p.is_file() and p.name != C.OUT_FREEZE.name:
            files.append({'relpath': str(p.relative_to(C.G3C0))
                          .replace('\\', '/'),
                          'bytes': p.stat().st_size,
                          'sha256': C.sha256_file(p)})
    digest = C.canonical_bytes({'files': sorted(files,
                                                key=lambda f: f['relpath'])})
    return {
        'document': 'GroundedReview Gate G3-C.0 zero-API design-freeze '
                    'manifest',
        'design_version': C.G3C0_DESIGN_VERSION,
        'projection_version_specified_for_gate3c':
            C.PROJECTION_V2_VERSION,
        'budget_usd': 0,
        'api_calls_made': 0,
        'actual_new_issues_materialised': 0,
        'gate3c_execution': False,
        'gold_changed': False,
        'git_commits_made': 0,
        'n_files': len(files),
        'files': files,
        'files_canonical_sha256': C.sha256_bytes(digest),
        'parent_pins': {
            'g3b4_freeze_reverification': extra_parent,
            'g3b4_result_freeze_manifest_sha256':
                C.sha256_file(C.G3B4_RESULT_FREEZE),
            'g3b3_parent_pins': B4.verify_g3b3_parent_pins(verbose=False)},
        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope': C.APPROVED_SCOPE,
    }


def main():
    task1 = _load('freeze/g3c0_task1_g3b4_freeze_reverification.json')
    proj = _load('projection/g3c0_projection_v2_spec_and_test.json')
    ni = _load('projection/g3c0_noninterference_audit_protocol.json')
    pre = _load('design/g3c0_preregistration_endpoints_sampling_stats.json')
    human = _load('human_annotation/g3c0_human_annotation_package.json')
    exe = _load('budget/g3c0_execution_budget_and_engineering.json')

    report = {
        'document': 'GroundedReview Gate G3-C.0 — zero-API study-design '
                    'freeze and protocol-quality preparation',
        'design_version': C.G3C0_DESIGN_VERSION,
        'decision_acknowledged': 'G3-B.4 audit accepted; Gate 3-C paid '
            'expansion NOT approved; only G3-C.0 design freeze and data-'
            'quality preparation approved. New API budget $0.',
        'api_calls_made': 0,
        'spend_usd': 0,
        'actual_new_issues_materialised': 0,
        'git_commits_made': 0,
        'task_index': {
            '1_freeze_g3b4': task1['all_ok'],
            '2_projection_v2': proj['v2_single_additional_removed_field'],
            '3_endpoints_P1_P2': ['P1', 'P2'],
            '4_sampling': '>=20 NEW independent REJECT; natural rate + '
                          'enrichment reported',
            '5_stats': 'issue-level Wilson/exact + McNemar + issue-cluster '
                       'bootstrap; no pseudo-replication',
            '6_availability': 'paired; orthogonal 2x2 required for causal; '
                              'otherwise ASSOCIATIONAL',
            '7_noninterference': 'deny/allow lists + no-auto-sufficiency + '
                                 'machine gate (v2 tier1=0/tier2=0)',
            '8_human_packet': human['status'],
            '9_execution_budget': 'P0/B1/B2 estimates; not executed',
            '10_engineering': 'unified drift/length/capability/randomness/'
                              'reason/truncation/budget checks'},
        'task1_freeze_reverification': {
            'all_ok': task1['all_ok'],
            'g3b4_n_files_reverified': task1['g3b4_freeze_reverification']
            ['n_files_reverified'],
            'g3b4_canonical_digest_matches': task1['g3b4_freeze_reverification']
            ['canonical_digest_matches']},
        'projection_v2_summary': {
            'single_additional_removed_field':
                proj['v2_single_additional_removed_field'],
            'v1_tier1_tier2': {'tier1': proj['non_interference_test']
                               ['v1_total_tier1_forbidden_findings'],
                               'tier2': proj['non_interference_test']
                               ['v1_total_tier2_baseline_gap_findings']},
            'v2_tier1_tier2': {'tier1': proj['non_interference_test']
                               ['v2_total_tier1_forbidden_findings'],
                               'tier2': proj['non_interference_test']
                               ['v2_total_tier2_baseline_gap_findings']},
            'static_block_identical_all_issues':
                all(p['static_diagnostic_block_byte_identical_v1_v2']
                    for p in proj['per_issue_offline_demonstration']),
            'frozen_code_modified': proj['frozen_code_modified']},
        'endpoints_locked': {
            'P1': pre['task3_endpoints']['P1']['estimand'],
            'P2': pre['task3_endpoints']['P2']['estimand'],
            'labels_kept_separate': True},
        'sampling_locked': {'new_reject_floor': 20,
                            'sampling_seed': C.G3C0_SAMPLING_SEED},
        'analysis_locked': {'bootstrap_seed': C.G3C0_BOOTSTRAP_SEED,
                            'bootstrap_replicates':
                                C.G3C0_BOOTSTRAP_REPLICATES,
                            'multiplicity': 'Holm across 2 co-primary'},
        'availability_contrast_locked': {
            'associational_until_orthogonal_2x2':
                pre['task6_evidence_availability']
                ['associational_only_until_run']},
        'human_annotation': {
            'status': human['status'],
            'n_packets': human['n_packets'],
            'n_packets_with_partial_identity_self_reference':
                sum(1 for r in human['packet_manifest']
                    if r['files_self_referencing_this_issue_number'])},
        'budget_estimates_only': {
            'observed_real_mean_per_cell_usd':
                exe['task9_execution_and_budget_plan']['planning_assumptions']
                ['observed_mean_cell_usd'],
            'three_phases': [
                {'phase': p['phase'][:40], 'cells': p['estimated_cells'],
                 'expected_usd': p['expected_cost_at_observed_mean_usd'],
                 'worst_case_usd': p['worst_case_cost_if_every_cell_hits_'
                                     'observed_max_usd'],
                 'hard_cap_usd': p['hard_pre_call_cap_usd']}
                for p in exe['task9_execution_and_budget_plan']['phases']],
            'executed': False},
        'task11_paper_claim_boundaries': claim_boundaries(),
        'deliverables': [
            'design/g3c0_preregistration_endpoints_sampling_stats.json',
            'projection/g3c0_projection_v2_spec_and_test.json',
            'projection/g3c0_noninterference_audit_protocol.json',
            'human_annotation/ (protocol, CSV template, 10 blind packets, '
            'sealed mapping)',
            'budget/g3c0_execution_budget_and_engineering.json',
            'freeze/g3c0_task1_g3b4_freeze_reverification.json',
            'g3c0_design_report.{json,md}',
            'freeze/g3c0_design_freeze_manifest.json'],
        'gold_authority': C.GOLD_AUTHORITY,
        'stopping_statement': 'G3-C.0 complete. Gate 3-C paid expansion, real'
            ' model calls, Gemini, R2 and new paid models remain UN-executed; '
            'awaiting separate written approval (G3-C.1). No git commit made.',
    }

    C.G3C0.mkdir(parents=True, exist_ok=True)
    C.OUT_REPORT.write_bytes(C.canonical_bytes(report))

    # Markdown report.
    L = ['# GroundedReview Gate G3-C.0 — Zero-API Design Freeze', '',
         '**Decision:** G3-B.4 accepted; Gate 3-C paid expansion NOT '
         'approved. G3-C.0 covers design freeze and data-quality preparation '
         'only. API budget **$0**; no issue materialised; no model call; no '
         'git commit.', '',
         '## 1. G3-B.4 freeze (task 1)',
         f"All {report['task1_freeze_reverification']['g3b4_n_files_reverified']}"
         ' G3-B.4 files re-hash to their frozen pins and the canonical digest '
         f"matches (all_ok={task1['all_ok']}); G3-B.3 parent pins pass. No "
         'historical artifact was rewritten.', '',
         '## 2. Restricted-evidence projection v2 (task 2)',
         'New **versioned** diagnostic projection removes exactly one extra '
         'field, `pass_to_pass_baseline` (the all-PASSED pre-patch base-commit'
         ' map that was the G3-B.4 tier-2 gap). Offline demonstration over '
         'the 10 frozen served artifacts:',
         '- v1 tier-1/tier-2 findings: 0 / 10; **v2: 0 / 0**',
         '- v2 JSON equals v1 minus that field (+ version tag) for all 10',
         '- static diagnostic block is byte-identical v1 vs v2',
         '- freshness/coverage/consistency/log/linkage channels never read '
         'the field; tier A untouched. Frozen views.py/server.py are NOT '
         'edited; v2 is an out-of-tree, separately versioned path.', '',
         '## 3. Pre-registered endpoints (task 3)',
         '- **P1 Unsupported Commitment** (restricted tier-D, condition-gold '
         'NEED): commitment = ACCEPT or REJECT; reported as P1a unsupported '
         'ACCEPT / P1b unsupported REJECT / P1c correct NEED, never merged.',
         '- **P2 Unsupported Acceptance** (sufficient evidence, oracle-REJECT,'
         ' decisive failure visible): ACCEPT / REJECT-gold. Distinct '
         'denominator and mechanism from P1; no pooled "hallucination rate".',
         '- ACCEPT / REJECT / NEED_EVIDENCE kept separate throughout.', '',
         '## 4. Sampling (task 4)',
         'Independent issue = one upstream id/base commit (multi-arm is one '
         'unit). Target **>=20 NEW independent REJECT issues** (existing 3 '
         'held as anchors), balanced across R-F2P / R-P2P / R-TRAP strata, '
         'plus ~20 ACCEPT/need controls. Natural prevalence is measured '
         'before enrichment; enrichment sampling fractions are logged and '
         'enriched rates are never presented as natural-population rates.',
         '', '## 5. Analysis (task 5)',
         'Issue is the only independent unit (no pseudo-replication across '
         'conditions/turns/repeats). Wilson/exact CIs per rate, exact '
         'McNemar for paired binary contrasts, and issue-cluster bootstrap '
         f'({C.G3C0_BOOTSTRAP_REPLICATES} replicates, seed '
         f'{C.G3C0_BOOTSTRAP_SEED}); Holm correction across the two '
         'co-primary endpoints. Worked provisional P1a 7/10 Wilson95 '
         '~[0.40,0.89]; with n=20 new negatives the P2 half-width is ~0.17 '
         'near p=0.2 (preliminary precision).', '',
         '## 6. Evidence-availability comparison (task 6)',
         'Pre-registered active tier-D vs static tier-D paired contrast for '
         'P1a. Tool access, information content and interaction turns are '
         'separated only by an orthogonal 2x2 (freshness/trust held fixed) '
         'plus a same-content stubbed-active control and a reminder arm. '
         'Until that is run, every G3-B->G3-B.3/static->active contrast is '
         '**ASSOCIATIONAL**; active-query over-commitment stays a candidate '
         'mechanism.', '',
         '## 7. Non-interference protocol (task 7)',
         'Deny list (post-patch F2P/P2P outcomes, gold/gold-reconstructing '
         'fields, f2p/p2p log digests, and now the baseline map); explicit '
         'allow list of legal pre-patch/structural information; hard rule '
         'that HTTP success/freshness TRUE/coverage complete/symptom-gone '
         'never auto-grant acceptance sufficiency. A machine gate (frozen '
         'G3-B.4 scanner) must report tier1=0 and tier2=0 on every rendered '
         'surface before any paid cell unlocks.', '',
         '## 8. Second-human-annotator package (task 8)',
         f"Built **{human['n_packets']} blind packets** (problem, candidate "
         'patch, maintainer test_patch, declared ids, f2p/p2p/baseline/symptom'
         ' logs) with a written rubric, a blank labels CSV, a sealed mapping '
         'and third-human arbitration + gold-flip sensitivity rules. Status '
         '**PENDING** — no independent human labels exist. Identity blinding '
         'is partial: '
         f"{report['human_annotation']['n_packets_with_partial_identity_self_reference']}"
         '/10 verbatim patches self-quote the upstream issue number; the '
         'evidence is not rewritten and the limitation is logged.', '',
         '## 9. Execution & budget plan, estimates only (task 9)',
         'Basis is the frozen REAL G3-B.3 mean '
         f"${report['budget_estimates_only']['observed_real_mean_per_cell_usd']}"
         '/cell (not mock).', '']
    for p in report['budget_estimates_only']['three_phases']:
        L.append(f"- **{p['phase']}**: ~{p['cells']} cells; expected "
                 f"${p['expected_usd']}; observed-max worst case "
                 f"${p['worst_case_usd']}; hard pre-call cap "
                 f"${p['hard_cap_usd']}.")
    L += ['', 'Each phase has pre-call hard caps, drift/protocol-failure '
              'halts, a clean non-interference gate, harm-only interim '
              'stops and no expansion without a new written approval.', '',
          '## 10. Engineering standards (task 10)',
          'Unified checks for served-model id drift, prompt-length/'
          'truncation, tool capability and strict-403 behaviour, fixed '
          'seeds/repeats-within-issue, pre-defined UNPARSEABLE/missing-reason'
          ' handling, finish_reason=length detection, and a None/NaN-tested '
          'pre-call budget guard plus mock + zero-API live gates and raw-'
          'first persistence (the G3-B.3 discipline).', '',
          '## 11. Paper claim boundaries (task 11)',
          '- Old DeepSeek 9/10: substantially protocol-construct driven, '
          'reported associational — not a stable intrinsic defect.',
          '- GPT Strict 7/10: an operationally defined observation on n=10 '
          '(PROVISIONAL gold, single-AI partial-blind coding) — causal '
          'mechanism NOT proven.',
          '- GPT sufficient-evidence false ACCEPT: specific cases only '
          '(n=3 REJECT issues) — no rate; P1 and P2 never pooled.',
          '- Residual abstention: SymPy-13974 only (n=1), not generalised.',
          '- Central question ("evidence integrity vs sufficiency") is a '
          'hypothesis pending independent generalisation.', '',
          '## Deliverables',
          '\n'.join('- ' + d for d in report['deliverables']), '',
          '---', '**STOPPING.** G3-C.0 is complete; awaiting separate written '
          'approval (G3-C.1) before any issue materialisation, real model '
          'call, Gemini/R2 or other paid experiment. No git commit made.']
    C.OUT_REPORT_MD.write_text('\n'.join(L) + '\n', encoding='utf-8')

    freeze = build_freeze({
        'all_ok': task1['all_ok'],
        'n_files': task1['g3b4_freeze_reverification']['n_files_reverified']})
    C.OUT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_FREEZE.write_bytes(C.canonical_bytes(freeze))

    print('report files:', C.OUT_REPORT.name, C.OUT_REPORT_MD.name)
    print('freeze n_files:', freeze['n_files'], 'canonical:',
          freeze['files_canonical_sha256'][:12])
    print('parent g3b4 sha:', freeze['parent_pins']
          ['g3b4_result_freeze_manifest_sha256'][:12])


if __name__ == '__main__':
    main()
