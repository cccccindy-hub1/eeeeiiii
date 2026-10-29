"""Gate 3-B.3 (task 16) — corrective-replication report + RESULT freeze ($0).

Aggregates the executed G3-B.3 run and its offline analysis into:
  * C.OUT_REPORT        — a readable gate report JSON (findings + audits);
  * C.OUT_RESULT_FREEZE — a byte-level manifest pinning every RESULT artifact
                          (100 live rows, 100 raws, 100 traces, run audit,
                          preflight/livegate, analysis + per-issue evidence),
                          the as-executed data-collection freeze, the budget
                          and served-model-version audit, and the STRICT
                          G3-B<->G3-B.3 paired comparison.

It does NOT call a model, does NOT rebuild the data-collection freeze (that
manifest was canonical at paid-run time and must stay byte-identical), does
NOT touch any frozen G3-A/G3-A.1/G3-B/G3-B.1/G3-B.2 artifact, and does NOT
commit. The G3-B -> G3-B.3 contrast is recorded as cross-version / cross-run
-time ASSOCIATIONAL only.

Offline:
    uv run --python 3.13 -m evidence.g3b3_report
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess

from evidence import g3b3_common as C

FROZEN_HEAD = '2097ecd87310bd1df1f3dcfddfbc7e3cedea1123'

LIVE_ROWS = {
    'deepseek-flash':
        C.OUT_LIVE_DIR / 'g3b3_live_deepseek_flash_results.jsonl',
    'gpt-4.1-mini':
        C.OUT_LIVE_DIR / 'g3b3_live_gpt_41_mini_results.jsonl',
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_jsonl(p):
    return list(C.read_jsonl(str(p)))


def _file_entry(name, p):
    p = C.Path(p)
    b = p.read_bytes()
    return {'name': name,
            'path': str(p.relative_to(C.HERE)).replace('\\', '/'),
            'bytes': len(b), 'sha256': C.sha256_bytes(b)}


def _dir_fingerprint(name, d):
    """Hash every file under a result directory deterministically."""
    d = C.Path(d)
    files = sorted(x for x in d.rglob('*') if x.is_file())
    entries = []
    for x in files:
        rel = str(x.relative_to(d)).replace('\\', '/')
        entries.append({'relpath': rel, 'bytes': x.stat().st_size,
                        'sha256': C.sha256_file(x)})
    blob = json.dumps(entries, sort_keys=True, ensure_ascii=False).encode()
    return {'name': name,
            'path': str(d.relative_to(C.HERE)).replace('\\', '/'),
            'n_files': len(entries),
            'sha256_of_sorted_file_manifest': C.sha256_bytes(blob),
            'files': entries}


def _git_state():
    def run(*a):
        return subprocess.run(['git', '--no-pager', *a],
                              cwd=str(C.HERE.parent), capture_output=True,
                              text=True).stdout.strip()
    head = run('rev-parse', 'HEAD')
    staged = [s for s in run('diff', '--cached', '--name-only').splitlines()
              if s]
    status = run('status', '--porcelain')
    modified = [ln[3:] for ln in status.splitlines()
                if ln and ln[0] in ('M', 'A', 'D', 'R', 'C')]
    untracked = [ln[3:] for ln in status.splitlines()
                 if ln and ln[:2] == '??']
    return {'head': head, 'head_matches_frozen': head == FROZEN_HEAD,
            'frozen_head_expected': FROZEN_HEAD,
            'staged_files': staged, 'n_staged': len(staged),
            'modified_or_added_tracked': modified,
            'untracked_count': len(untracked),
            'commits_made_in_g3b3': 0,
            'note': 'untracked (??) g3b3 artifacts are expected; tracked '
                    'modifications and staged files must be zero.'}


# ---------------------------------------------------------------------------
# audits
# ---------------------------------------------------------------------------

def model_version_audit():
    out = {}
    for m, p in LIVE_ROWS.items():
        rows = _read_jsonl(p)
        served = {}
        fallbacks = 0
        wire_shapes = {}
        for r in rows:
            served[r.get('model_served')] = served.get(
                r.get('model_served'), 0) + 1
            for c in r.get('adapter_wire_calls', []):
                if c.get('fallback_from'):
                    fallbacks += 1
                rf = c.get('response_format')
                wire_shapes[rf] = wire_shapes.get(rf, 0) + 1
        out[m] = {
            'n_rows': len(rows),
            'expected_served_model_id':
                rows[0].get('expected_served_model_id') if rows else None,
            'served_model_id_distribution': served,
            'served_id_drift': any(
                k != (rows[0].get('expected_served_model_id')
                      if rows else None) for k in served),
            'adapter_response_format_distribution': wire_shapes,
            'capability_fallback_calls': fallbacks,
            'total_tokens_in': sum(r.get('tokens_in', 0) for r in rows),
            'total_tokens_out': sum(r.get('tokens_out', 0) for r in rows),
            'total_model_calls': sum(r.get('model_calls', 0) for r in rows),
            'total_tool_calls': sum(r.get('tool_calls', 0) for r in rows),
            'total_cost_usd': round(sum(r.get('cost_usd', 0) for r in rows),
                                   6),
            'error_rows': sum(1 for r in rows if r.get('error')),
            'retries_per_row': sorted({r.get('retries') for r in rows}),
        }
    return out


def budget_audit(run_audit, mva):
    per = mva
    total = run_audit['total_spend_usd']
    return {
        'total_spend_usd': total,
        'total_hard_cap_usd': run_audit['total_hard_cap_usd'],
        'per_model_spend_usd': run_audit['per_model_spend_usd'],
        'per_model_cap_usd': run_audit['per_model_cap_usd'],
        'within_total_cap': run_audit['within_total_cap'],
        'per_model_within_cap': {
            m: run_audit['per_model_spend_usd'][m]
            <= run_audit['per_model_cap_usd'] + 1e-9 for m in per},
        'total_margin_usd': round(
            run_audit['total_hard_cap_usd'] - total, 6),
        'cost_recomputed_from_rows_matches_audit': all(
            abs(per[m]['total_cost_usd']
                - run_audit['per_model_spend_usd'][m]) < 1e-5
            for m in per),
        'retries_per_cell': run_audit['retries_per_cell'],
        'stop_msg': run_audit.get('stop_msg', ''),
        'price_basis': 'DS $0.30/$1.20, GPT $0.40/$1.60 per 1M tokens '
                       '(identical to frozen G3-B profiles)',
    }


def findings(analysis):
    q10 = analysis['Q10_deepseek_sufficient_need_and_paired_transition']
    q11 = analysis['Q11_gpt_unsupported_acceptance_reject_issues']
    q12 = analysis['Q12_restricted_regime_abstention']
    ornew = q10['or_aggregated_over_abstention']
    orold = q10['strict_paired_g3b_transition']['or_aggregated_need_any'][
        'g3b']
    delta = q10['strict_paired_g3b_transition'][
        'matched_issue_delta_bootstrap']
    c1 = q11['confirmatory_sufficient_or_aggregate']
    f17318 = q11['focal_sympy_17318_T2A']
    p17630 = q11['decision_policy_probe_sympy_17630_T3A']
    return {
        'Q10_deepseek_over_abstention_corrected': {
            'g3b_needany': {'k': orold['k'], 'n': 10,
                            'bootstrap_ci95': [orold['bootstrap']['ci95_low'],
                                               orold['bootstrap']['ci95_high']]},
            'g3b3_needany': {'k': ornew['k'], 'n': 10,
                             'cp_ci95': [ornew['exact']['ci95_low'],
                                         ornew['exact']['ci95_high']],
                             'bootstrap_ci95':
                                 [ornew['issue_cluster_bootstrap']['ci95_low'],
                                  ornew['issue_cluster_bootstrap']['ci95_high']]},
            'matched_per_issue_delta': {'point': delta['point'],
                                        'bootstrap_ci95':
                                            [delta['ci95_low'],
                                             delta['ci95_high']]},
            'discordant_pairs_need_to_other': q10['strict_paired_g3b_transition'][
                'discordant_needany_need_to_other'],
            'discordant_pairs_other_to_need': q10['strict_paired_g3b_transition'][
                'discordant_needany_other_to_need'],
            'interpretation': (
                'DeepSeek sufficient-regime NEED fell 9/10 -> 1/10 over the '
                'repaired protocol with 8 matched issue-level reversals and '
                'zero reversals in the other direction (the matched CI is '
                'entirely below zero). Under the pre-registered reading the '
                'original G3-B C2 over-abstention was therefore largely '
                'PROTOCOL-INDUCED, which WEAKENS the model-defect claim. It '
                'is not erased: the single residual issue (sympy-13974) '
                'still abstains on T2A/T3D-Escalate under visible sufficient '
                'evidence, the only candidate calibration/decision-policy '
                'case left in the DeepSeek arm.'),
            'associational_only': analysis['associational_caution']},
        'Q11_gpt_unsupported_acceptance': {
            'sufficient_or_aggregate': {
                'k_issues': c1['k_issues'], 'n_issues': 3,
                'cp_ci95': [c1['exact']['ci95_low'],
                            c1['exact']['ci95_high']],
                'bootstrap_ci95':
                    [c1['issue_cluster_bootstrap']['ci95_low'],
                     c1['issue_cluster_bootstrap']['ci95_high']]},
            'full_15_cell_unsupported_acceptance':
                q11['full_sample']['unsupported_acceptance_cells'],
            'focal_sympy_17318_T2A': {
                'g3b_verdict': f17318['g3b_verdict'],
                'g3b3_verdict': f17318['g3b3_verdict'],
                'unsupported_acceptance':
                    f17318['g3b3_unsupported_acceptance'],
                'interpretation': 'The specific evidence-verification failure '
                    'PERSISTS unchanged: GPT returns ACCEPT on the static '
                    'T2A block that renders FAIL_TO_PASS 0/1 + failing id '
                    'test_issue_12420. T2A is static (no freshness tool), so '
                    'this is not a freshness artefact and cannot be explained '
                    'away by the repair.'},
            'decision_policy_probe_sympy_17630_T3A': {
                'g3b_verdict': p17630['g3b_verdict'],
                'g3b3_verdict': p17630['g3b3_verdict'],
                'interpretation': 'Separately tagged, never pooled. Under '
                    'repaired TRUE freshness the cell moved REJECT(G3-B) -> '
                    'NEED_EVIDENCE(G3-B.3); it is no longer an unsupported '
                    'ACCEPTANCE but is still not the gold REJECT, so it '
                    'remains an over-abstention/decision-policy residual.'},
            'note': 'Two additional G3-B.3 ACCEPTs occur on the two '
                    'RESTRICTED regimes for issues 17318/17630 (T3D-Strict); '
                    'these are improper commitments under restricted '
                    'evidence (reported in Q12), not sufficient-evidence '
                    'unsupported acceptances.'},
        'Q12_restricted_regime_abstention': {
            m: {c: {'correct_abstain': q12[m][c]['correct_abstain_k'],
                    'n': 10,
                    'improper_commitments':
                        len(q12[m][c]['improper_commitments'])}
                for c in C.RESTRICTED_CONDITIONS}
            for m in C.MODELS},
        'parse_failures': analysis['parse_or_transport_failures'],
    }


# ---------------------------------------------------------------------------

def build():
    run_audit = json.loads(C.OUT_LIVE_AUDIT.read_text(encoding='utf-8'))
    preflight = json.loads(C.OUT_PREFLIGHT.read_text(encoding='utf-8'))
    livegate = json.loads(C.OUT_LIVEGATE.read_text(encoding='utf-8'))
    collection_freeze = json.loads(
        C.OUT_FREEZE.read_text(encoding='utf-8'))
    analysis = json.loads(C.OUT_ANALYSIS.read_text(encoding='utf-8'))

    mva = model_version_audit()
    git = _git_state()
    created = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # ---- result artifacts (hashed) ------------------------------------
    result_artifacts = [
        _file_entry('live_rows_deepseek_flash', LIVE_ROWS['deepseek-flash']),
        _file_entry('live_rows_gpt_41_mini', LIVE_ROWS['gpt-4.1-mini']),
        _file_entry('live_run_audit', C.OUT_LIVE_AUDIT),
        _file_entry('preflight', C.OUT_PREFLIGHT),
        _file_entry('livegate', C.OUT_LIVEGATE),
        _file_entry('analysis', C.OUT_ANALYSIS),
        _file_entry('per_issue_evidence', C.OUT_ISSUE_EVIDENCE),
        _dir_fingerprint('raw_responses_dir', C.OUT_RAW_DIR),
        _dir_fingerprint('live_traces_dir', C.OUT_TRACE_DIR / 'live'),
    ]

    executed_freeze_sha = C.sha256_file(C.OUT_FREEZE)

    # Post-collection code hashes: the analyzer/reporter did not exist (None)
    # in the manifest the paid run validated; hashing them here is purely an
    # audit trail of the offline-only post-collection tooling.
    post_code = {}
    for n in ('g3b3_analyze.py', 'g3b3_report.py'):
        p = C.EVID / n
        post_code[n] = {'sha256': C.sha256_file(p),
                        'in_executed_freeze_manifest':
            collection_freeze['g3b3_code_hashes']['g3b3_modules'].get(n)}

    result_freeze = {
        'document': 'Gate 3-B.3 Corrective Replication RESULT freeze '
                    '(post-collection, offline, $0)',
        'freeze_id': 'groundedreview-gate3b3-result-freeze-v1',
        'gate': C.GATE,
        'created_utc': created,
        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope_executed': {
            **C.APPROVED_SCOPE,
            'real_cells_executed': 100,
            'new_issues': 0, 'gemini_or_r2_cells': 0, 'gate_3c': False,
            'git_commit': False},
        'data_collection_freeze': {
            'manifest': str(C.OUT_FREEZE.relative_to(C.HERE)).replace(
                '\\', '/'),
            'sha256': executed_freeze_sha,
            'canonical_at_paid_run_time': True,
            'note': 'NOT rebuilt after collection: g3b3_analyze.py and '
                    'g3b3_report.py were authored offline after the paid run '
                    'and are recorded as null hashes in this executed '
                    'manifest by design; rebuilding would rewrite history.'},
        'g3b_pairing_anchor': collection_freeze['g3b_pairing'],
        'post_collection_code_hashes': post_code,
        'post_collection_analyzer_change_disclosure': {
            'analyzer_written_after_collection_offline': True,
            'api_calls_for_analysis': 0,
            'result_rows_modified': False,
            'fixes': [
                'read helper initially wrapped the already-parsed read_jsonl '
                'in json.loads (raised before any output); fixed offline.',
                'Q11 full-sample accumulator was reset per issue so the '
                '15-cell unsupported-acceptance count only reflected the '
                'last issue (reported 0 instead of 4); corrected with a '
                'loop-persistent accumulator and re-run. Confirmatory OR '
                'aggregate, focal probes, Q10/Q12/Q14/Q15 were unaffected.'],
            'impact': 'analysis JSON only; no row, raw, trace, cost, token, '
                      'served-id or freeze byte changed'},
        'execution': {
            'runner_version': run_audit['runner_version'],
            'protocol_version': run_audit['executed_protocol_version'],
            'prompt_version': run_audit['executed_prompt_version'],
            'call_order_seed': collection_freeze['call_order_seed'],
            'budget': budget_audit(run_audit, mva),
            'model_version_audit': mva,
            'engineering_gates_from_paid_run': {
                'rows_per_model_50_50': all(
                    mva[m]['n_rows'] == 50 for m in mva),
                'zero_error_rows': all(
                    mva[m]['error_rows'] == 0 for m in mva),
                'zero_served_id_drift': all(
                    not mva[m]['served_id_drift'] for m in mva),
                'zero_capability_fallback': all(
                    mva[m]['capability_fallback_calls'] == 0 for m in mva),
                'raw_files': next(a['n_files'] for a in result_artifacts
                                  if a['name'] == 'raw_responses_dir'),
                'live_trace_files': next(a['n_files'] for a in result_artifacts
                                         if a['name'] ==
                                         'live_traces_dir')}},
        'preflight_at_gate': {
            'all_pass': preflight.get('all_pass'),
            'n_checks': preflight.get('n_checks'),
            'n_checks_pass': preflight.get('n_checks_pass'),
            'n_sections': preflight.get('n_sections'),
            'paid_run_authorised_only_if_all_pass':
                preflight.get('paid_run_authorised_only_if_all_pass')},
        'livegate_at_gate': {
            'n_cells': livegate.get('n_cells'),
            'n_checks': livegate.get('n_checks'),
            'n_checks_pass': livegate.get('n_checks_pass'),
            'n_errors': livegate.get('n_errors'),
            'n_active_cells': livegate.get('n_active_cells'),
            'n_active_freshness_TRUE': livegate.get('n_active_freshness_TRUE'),
            'frozen_store_unchanged': livegate.get('frozen_store_unchanged'),
            'server_protocol_version': livegate.get('server_protocol_version')},
        'associational_comparison_notice': (
            'All G3-B vs G3-B.3 paired numbers are cross-version, cross-run-'
            'time and ASSOCIATIONAL. Freshness repair and T2A policy-trust '
            'repair shipped together; separate causal effects are not '
            'identified and are not claimed.'),
        'artifacts': result_artifacts,
        'git_state': git,
    }

    report = {
        'document': 'Gate 3-B.3 Corrective Replication report',
        'gate': C.GATE,
        'created_utc': created,
        'gold_authority': C.GOLD_AUTHORITY,
        'approval_basis': collection_freeze['approval'],
        'headline': (
            '100/100 real cells completed for $0.3035 (cap $3.00) with zero '
            'errors, retries, served-id drift and capability fallback. Under '
            'the repaired G3-B.2 protocol DeepSeek sufficient-regiment over-'
            'abstention fell from 9/10 (G3-B) to 1/10 (G3-B.3) on strict '
            'same-issue/condition/model pairs, i.e. the original C2 effect '
            'was largely protocol-induced; GPT still unsupported-accepts the '
            'specific static sympy-17318/T2A cell despite visible FAIL_TO_PASS '
            '0/1.'),
        'budget_audit': result_freeze['execution']['budget'],
        'model_version_audit': mva,
        'engineering_gates':
            result_freeze['execution']['engineering_gates_from_paid_run'],
        'findings': findings(analysis),
        'gold_sensitivity': analysis['Q14_gold_sensitivity'],
        'decision_appropriateness': analysis['decision_appropriateness'],
        'per_issue_raw_verdict_grids':
            analysis['per_issue_raw_verdict_grids_g3b_vs_g3b3'],
        'evidence_package_classification_tag_counts': analysis[
            'Q15_evidence_package_index']['classification_tag_counts'],
        'associational_comparison_notice':
            result_freeze['associational_comparison_notice'],
        'scope_and_generalisation_limits': analysis['do_not'],
        'result_freeze_path': str(
            C.OUT_RESULT_FREEZE.relative_to(C.HERE)).replace('\\', '/'),
        'git_state': git,
        'gate_state': 'COMPLETE; stopped pending the next written approval. '
                      'No Gate 3-C, no new issue/model, no commit.',
    }

    C.OUT_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    # Pin the just-written report too (no self-hash of the freeze manifest;
    # re-running after any byte drift changes exactly this entry).
    result_freeze['artifacts'].append(
        _file_entry('gate_report', C.OUT_REPORT))
    C.OUT_RESULT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_RESULT_FREEZE.write_text(
        json.dumps(result_freeze, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    return report, result_freeze


def main():
    report, rf = build()
    print(f'report -> {C.OUT_REPORT}')
    print(f'result freeze -> {C.OUT_RESULT_FREEZE}')
    g = report['git_state']
    print(f"git head={g['head'][:12]} matches_frozen={g['head_matches_frozen']}"
          f" staged={g['n_staged']} tracked_modified="
          f"{len(g['modified_or_added_tracked'])} untracked={g['untracked_count']}")
    ba = report['budget_audit']
    print(f"budget total=${ba['total_spend_usd']} cap=${ba['total_hard_cap_usd']}"
          f" within={ba['within_total_cap']} per_model={ba['per_model_within_cap']}")
    if not g['head_matches_frozen']:
        print('WARNING: git HEAD does not match the frozen commit '
              f'{FROZEN_HEAD}')
    if g['n_staged'] or g['modified_or_added_tracked']:
        print('WARNING: staged or tracked-modified files present: '
              f"{g['staged_files']} {g['modified_or_added_tracked']}")


if __name__ == '__main__':
    main()
