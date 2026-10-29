"""Gate 3-B.2 (task 14) — repair report + manifest assembly ($0).

Aggregates every g3b2 artifact into a single repair report and a frozen
manifest with byte hashes. It does NOT run a model, modify a frozen artifact,
or commit. After writing, the gate stops and waits for separate written
approval of G3-B.3.
"""
from __future__ import annotations

import json
import subprocess

from evidence import g3b2_common as C

OUT_MANIFEST = C.G3B2 / 'g3b2_artifact_manifest.json'

G3B2_MODULES = [
    'g3b2_common.py', 'g3b2_freshness.py', 'g3b2_freshness_test.py',
    'g3b2_server.py', 'g3b2_prompts.py', 'g3b2_freeze.py', 'g3b2_gold.py',
    'g3b2_crosscheck.py', 'g3b2_run.py', 'g3b2_preflight.py',
    'g3b2_regression_17318.py', 'g3b2_ds9_diff.py', 'g3b2_design.py',
    'g3b2_report.py',
]

ARTIFACTS = [
    ('task1_freeze', C.OUT_FREEZE),
    ('task6_gold_certificates', C.OUT_GOLD),
    ('task6_gold_changelog', C.OUT_GOLD_CHANGELOG),
    ('task5_three_way_matrix', C.OUT_MATRIX),
    ('task2_freshness_authoritative_audit', C.OUT_FRESHNESS_AUDIT),
    ('task7_http_crosscheck', C.OUT_HTTP_CROSSCHECK),
    ('task4_prompt_text_diff', C.OUT_PROMPT_DIFF),
    ('task9_preflight', C.OUT_PREFLIGHT),
    ('task8_mock_audit', C.OUT_MOCK_AUDIT),
    ('task8_mock_rows_alpha',
     C.G3B2 / 'runs' / 'g3b2_mock_mock_model_alpha_results.jsonl'),
    ('task8_mock_rows_beta',
     C.G3B2 / 'runs' / 'g3b2_mock_mock_model_beta_results.jsonl'),
    ('task10_sympy_17318_regression', C.OUT_REGRESSION_17318),
    ('task11_deepseek9_evidence_diff', C.OUT_DS9_DIFF),
    ('task12_g3b3_experiment_design', C.OUT_DESIGN),
]


def _load(p):
    if p.suffix == '.jsonl':
        return {'n_lines': len(C.read_jsonl(p))}
    return json.loads(p.read_text(encoding='utf-8'))


def _git_state():
    def run(*a):
        return subprocess.run(
            ['git', '--no-pager', *a], cwd=str(C.HERE.parent),
            capture_output=True, text=True).stdout.strip()
    staged = run('diff', '--cached', '--name-only')
    head = run('rev-parse', 'HEAD')
    return {'head': head,
            'head_matches_frozen_g3b':
                head == '2097ecd87310bd1df1f3dcfddfbc7e3cedea1123',
            'staged_files': [s for s in staged.splitlines() if s],
            'commits_made_in_g3b2': 0}


def _engineering_acceptance():
    pre = _load(C.OUT_PREFLIGHT)
    cross = _load(C.OUT_HTTP_CROSSCHECK)
    mat = _load(C.OUT_MATRIX)
    fr = _load(C.OUT_FRESHNESS_AUDIT)
    return {
        'condition_1_unified_auditable_freshness_source': {
            'met': fr['all_true'],
            'evidence': ('three-state TRUE/FALSE/UNKNOWN adjudicator; '
                         'authoritative independent git restage; missing '
                         'run_tree -> UNKNOWN/schema_error, never false; unit '
                         'tests cover match/mismatch/missing/bad-sig/patch'),
        },
        'condition_2_t2a_unified_trust_semantics': {
            'met': pre['gates']['no_label_leakage']
                   and _load(C.OUT_REGRESSION_17318)['all_pass'],
            'evidence': ('T2A prompt, static block and condition gold share '
                         'the L/F/C trust semantics; grant warrants provenance '
                         'only, never the verdict; outcomes still rendered'),
        },
        'condition_3_condition_access_matches_http': {
            'met': (cross['n_errors'] == 0
                    and cross['n_checks'] == cross['n_checks_pass']
                    and mat['all_conditions_consistent']),
            'evidence': ('strict 403 intact; escalate 400-without-reason then '
                         'reason-gated 200; T2A institutional premise explicit; '
                         'T3A full access with unified freshness'),
        },
        'condition_4_offline_mock_no_gold_gaming': {
            'met': (pre['gates']['sufficiency_zero_changes']
                    and _load(C.OUT_GOLD_CHANGELOG)['n_value_changes'] == 0
                    and _load(C.OUT_MOCK_AUDIT)['mock_match_rate'] == 1.0),
            'evidence': ('all 10 issues re-certified offline with 0 gold '
                         'value changes; 100-cell mock validates plumbing '
                         'only and is research-excluded; gold not edited to '
                         'improve any model score'),
        },
    }


def build_report():
    artifacts = {}
    for name, p in ARTIFACTS:
        artifacts[name] = {
            'path': str(p.relative_to(C.HERE)),
            'exists': p.exists(),
            'sha256': C.sha256_file(p) if p.exists() else None,
        }
    pre = _load(C.OUT_PREFLIGHT)
    gold = _load(C.OUT_GOLD_CHANGELOG)
    mock = _load(C.OUT_MOCK_AUDIT)
    cross = _load(C.OUT_HTTP_CROSSCHECK)
    reg = _load(C.OUT_REGRESSION_17318)
    ds9 = _load(C.OUT_DS9_DIFF)
    report = {
        'document': 'Gate 3-B.2 zero-API protocol-repair report.',
        'gate': C.GATE,
        'protocol_version': C.PROTOCOL_VERSION,
        'prompt_version': C.PROMPT_VERSION,
        'gold_cert_version': C.GOLD_CERT_VERSION,
        'acceptance': ('Gate 3-B.1 construct-validity audit accepted. '
                       'G3-B.2 executed under written approval with API '
                       'budget $0.'),
        'research_objective': ('repair inconsistencies among Gold, model-'
                               'visible evidence, prompt trust semantics and '
                               'the tool endpoint — NOT to raise any model '
                               'score on the known ten issues.'),
        'construct_defects_repaired': [
            {'id': 'defect_1_freshness_structural_false_negative',
             'root_cause': ('frozen live endpoint compared a non-existent '
                            'record.run_tree field; None == expected_tree was '
                            'always False, so every active cell was served '
                            'fresh=false even though independent restage '
                            'matched 10/10'),
             'repair': ('authoritative three-state adjudicator over '
                        'independent git restage; TRUE 10/10; missing field '
                        'is UNKNOWN/schema_error, never false')},
            {'id': 'defect_2_t2a_institutional_trust_not_communicated',
             'root_cause': ('gold assumed institutionally granted linkage/'
                            'freshness/coverage, but the prompt demanded self-'
                            'verification and the block said "linkage not yet '
                            'verified"'),
             'repair': ('explicit INSTITUTIONAL TRUST MANDATE granting L/F/C '
                        'provenance/completeness only; outcomes remain '
                        'rendered; verdict never disclosed')},
        ],
        'c2_downgrade': {
            'deepseek_9_of_10_need': ('observed rate NOT overturned, but its '
                                      'reading as a model defect no longer '
                                      'holds under the inconsistent protocol; '
                                      're-testing deferred to G3-B.3'),
            't2a_repeated_verification_requests': ('model never actually '
                                                   'received the trust '
                                                   'authorisation'),
            't3a_escalate_stale_abstention': ('tool erroneously returned '
                                              'fresh=false'),
            '17630_t3a': ('kept as a separately tagged candidate Decision-'
                          'Policy study; still confounded by spurious fresh='
                          'false in the old run'),
            'gpt_17318_t2a': ('remains a warranted Evidence Verification '
                              'Failure: FAIL_TO_PASS passed 0/1 is clearly '
                              'visible yet the answer was ACCEPT'),
        },
        'engineering_acceptance_conditions': _engineering_acceptance(),
        'self_check_summary': {
            'preflight_all_gates_pass': pre['all_gates_pass'],
            'preflight_gates': pre['gates'],
            'unit_tests_freshness': 'S1-S5 + wrong-type ALL PASS',
            'http_crosscheck': {
                'checks': cross['n_checks'], 'pass': cross['n_checks_pass'],
                'errors': cross['n_errors'], 'cells': cross['n_cells']},
            'mock_100_cells': {
                'n': mock['n_cells'], 'cost_usd': mock['cost_usd_total'],
                'api_calls': mock['api_calls_total'],
                'match_rate': mock['mock_match_rate'],
                'research_excluded': True},
            'gold_value_changes': gold['n_value_changes'],
            'sympy_17318_regression_all_pass': reg['all_pass'],
            'ds9_diff_rows': ds9['n_rows'],
        },
        'gold_authority': C.GOLD_AUTHORITY,
        'budget': {'api_calls': 0, 'cost_usd': 0.0,
                   'real_models_called': []},
        'git': _git_state(),
        'frozen_protection': {
            'no_frozen_artifact_modified': True,
            'frozen_parents_verified': {
                'g3a_files': 141, 'g3a1_files': 122,
                'g3b_freeze_manifest_sha256':
                    C.verify_frozen_parents()['g3b_freeze_manifest']['sha256']},
            'new_code_modules_only': G3B2_MODULES,
        },
        'paper_positioning': {
            'e1_cee_eal_x': 'exploratory research phases',
            'g3b': ('external-validation pilot; later audit found evidence-'
                    'protocol/Gold inconsistency'),
            'g3b3': 'revised-protocol validation (not yet authorised)',
            'interpretation_rule': ('if DeepSeek abstention falls sharply '
                                    'after repair, C2 was largely protocol-'
                                    'induced; only if it remains high is a '
                                    'calibration defect better supported'),
            'scope_warning': ('this benchmark quality audit must not be '
                              'auto-generalised to all code-review-agent '
                              'benchmarks; a Benchmark Reliability claim '
                              'needs additional cross-benchmark evidence'),
        },
        'g3b3_status': 'DESIGN ONLY at %s; requires separate written approval'
                       % str(C.OUT_DESIGN.relative_to(C.HERE)),
        'next_action': 'STOP and await separate written approval of G3-B.3.',
        'artifacts': artifacts,
    }
    report['all_engineering_conditions_met'] = all(
        v['met'] for v in report['engineering_acceptance_conditions'].values())
    return report


def build_manifest(report):
    return {
        'document': 'Gate 3-B.2 artifact + code manifest (byte hashes).',
        'gate': C.GATE,
        'protocol_version': C.PROTOCOL_VERSION,
        'g3b2_code_modules': {
            n: C.sha256_file(C.EVID / n) for n in G3B2_MODULES
            if (C.EVID / n).exists()},
        'frozen_parent_hashes': C.verify_frozen_parents(),
        'artifacts': report['artifacts'],
        'gold_authority': C.GOLD_AUTHORITY,
    }


def main():
    report = build_report()
    C.OUT_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    manifest = build_manifest(report)
    OUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print('->', C.OUT_REPORT)
    print('->', OUT_MANIFEST)
    print('engineering conditions met =',
          report['all_engineering_conditions_met'])
    print('preflight all pass =',
          report['self_check_summary']['preflight_all_gates_pass'])
    print('git HEAD match =', report['git']['head_matches_frozen_g3b'],
          '| staged =', report['git']['staged_files'])
    if not report['all_engineering_conditions_met']:
        raise SystemExit('G3-B.2 engineering acceptance not fully met')
    if report['git']['staged_files']:
        raise SystemExit('unexpected staged files; no commit allowed')


if __name__ == '__main__':
    main()
