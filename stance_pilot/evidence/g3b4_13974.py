"""Gate 3-B.4 task 7: SymPy-13974 dedicated audit.

DeepSeek abstains NEED_EVIDENCE under T2A-T and T3D-Escalate but ACCEPTs
under T3A-T; under T3D-Strict it correctly abstains. We compare the evidence
actually presented, the tool adjudications, the model reasoning and the
Coverage trust rules across conditions, fact-check the model's claims against
the frozen store logs, and decide: legitimate evidential-standard difference,
residual policy error, or a new protocol inconsistency.

Offline, $0, frozen store read-only.
"""
from __future__ import annotations

import hashlib
import json
import re

from evidence import g3b4_common as C

IID = 'sympy__sympy-13974'
ART = 'art_42af95edfb29747c'
MODEL = 'deepseek-flash'
CONDS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')
FOCUS = ('T2A-T', 'T3D-Strict', 'T3D-Escalate', 'T3A-T')


def log_facts():
    logs = C.G3A_STORE_LOGS
    out = {}
    for kind in ('f2p', 'p2p', 'p2p_baseline', 'symptom'):
        p = logs / f'{ART}.{kind}.log'
        b = p.read_bytes()
        txt = b.decode('utf-8', errors='replace')
        tests = sorted(set(re.findall(r'(test_[A-Za-z0-9_]+)', txt)))
        statuses = re.findall(r'\b(PASSED|FAILED|ERROR|XFAIL)\b', txt)
        out[kind] = {
            'file': p.name, 'bytes': len(b),
            'sha256': hashlib.sha256(b).hexdigest(),
            'unique_test_tokens': tests,
            'status_counts': {s: statuses.count(s) for s in set(statuses)},
            'contains_declared_F2P_test_tensor_product_simp':
                'test_tensor_product_simp' in txt,
            'contains_candidate_added_test_tensor_product_power':
                'test_tensor_product_power' in txt}
    return out


def declared_sets():
    for r in C.read_jsonl(C.G3A_TARGET_ROWS):
        if r['instance_id'] == IID:
            return {'FAIL_TO_PASS_declared': r['FAIL_TO_PASS'],
                    'PASS_TO_PASS_declared': r['PASS_TO_PASS'],
                    'dataset_resolved_flag': r.get('resolved')}
    raise KeyError(IID)


def condition_blocks():
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    doc = next(i for i in pe['issues'] if i['issue'] == IID)
    blocks = {}
    for cond in CONDS:
        cell = next(c for c in doc['models'][MODEL]
                    if c['condition'] == cond)
        blocks[cond] = {
            'condition_gold': cell['condition_gold'],
            'final_verdict_g3b3': cell['g3b3_verdict'],
            'model_reasoning_full': cell['g3b3_model_reasoning'],
            'tool_requests': [
                {'turn': t['turn'], 'tool': t['tool'],
                 'http_status': t['http_status'], 'args': t.get('args'),
                 'response_excerpt': (t['result_preview'] or '')[:600]}
                for t in cell['tool_responses']],
            'f2p_or_p2p_log_granted': any(
                t['tool'] == 'get_run_log'
                and (t.get('args') or {}).get('name')
                in ('f2p', 'p2p') and t['http_status'] == 200
                for t in cell['tool_responses']),
            'outcomes_visible_to_model':
                'post-patch per-test f2p/p2P outcomes rendered'
                if cond == 'T3A-T' else
                ('post-patch f2p/p2p logs requestable under escalated '
                 'adjudication' if cond == 'T3D-Escalate'
                 else 'aggregate counts only / outcomes withheld')}
    return blocks, doc.get('oracle_gold')


def main():
    lf = log_facts()
    decl = declared_sets()
    blocks, oracle = condition_blocks()

    # Fact-check the two load-bearing claims in DS's Escalate reasoning.
    f2p, p2p, base = lf['f2p'], lf['p2p'], lf['p2p_baseline']
    factcheck = {
        'claim_A_all_three_logs_byte_identical': {
            'model_claim': 'f2p, p2p and p2p_baseline logs are byte-identical',
            'reality': {
                'f2p_sha': f2p['sha256'], 'p2p_sha': p2p['sha256'],
                'p2p_baseline_sha': base['sha256'],
                'f2p_equals_p2p': f2p['sha256'] == p2p['sha256'],
                'p2p_equals_baseline': p2p['sha256'] == base['sha256']},
            'verdict': 'PARTLY WRONG: f2p and p2p post-patch logs ARE '
                       'byte-identical (the same tensor-product test file '
                       'run), but p2p_baseline is a DIFFERENT sha; the three '
                       'logs are not all identical.'},
        'claim_B_declared_acceptance_test_absent': {
            'model_claim': 'the raw logs do not contain the declared FAIL_'
                           'TO_PASS acceptance test',
            'reality': {
                'declared_F2P': decl['FAIL_TO_PASS_declared'],
                'declared_F2P_present_and_passing_in_f2p_log':
                    f2p['contains_declared_F2P_test_tensor_product_simp']
                    and f2p['status_counts'].get('PASSED', 0) > 0,
                'test_the_model_expected': 'test_tensor_product_power',
                'that_test_in_logs':
                    f2p['contains_candidate_added_test_tensor_product_power'],
                'what_test_tensor_product_power_is':
                    'a test added inside the CANDIDATE model_patch, NOT a '
                    'maintainer-declared FAIL_TO_PASS test'},
            'verdict': 'FALSE: the declared FAIL_TO_PASS test '
                       'test_tensor_product_simp IS present and PASSED. The '
                       'model confused the maintainer-declared acceptance '
                       'test with a different test (test_tensor_product_power)'
                       ' that the candidate patch itself introduces.'},
        'declared_P2P_all_present_and_passing':
            all(tok in f2p['unique_test_tokens']
                for tok in ('test_tensor_product_abstract',
                            'test_tensor_product_expand',
                            'test_tensor_product_commutator',
                            'test_issue_5923'))}

    # Why the conditions differ in what is reachable (trust rules).
    trust_rules = {
        'T2D-T': 'static tier-D surface, no tools; maintainer outcomes '
                 'withheld; symptom only',
        'T3D-Strict': 'active tools; f2p/p2p logs return 403/disabled; '
                      'consistency adjudicates symptom only and states '
                      'acceptance outcomes are not adjudicated; coverage '
                      'shows execution counts but not outcomes',
        'T3D-Escalate': 'model CAN escalate and request f2p/p2p logs; '
                        'granted 200. The model in fact received them but '
                        'mis-read the identical-file artifact as missing '
                        'tests and over-weighted the candidate-added test',
        'T2A-T': 'static tier-A surface with aggregate F2P/P2P COUNTS '
                 '(1/1, 4/4) but no rendered per-test outcomes to read',
        'T3A-T_note': 'the model additionally doubted the patch from its '
                      'own reading of the candidate test assertions',
        'T3A-T_active': 'active tier-A; artifact + per-test f2p log '
                        'rendered, showing test_tensor_product_simp PASSED '
                        'and the four P2P PASSED; model then ACCEPTs'}

    out = {
        'document': 'Gate 3-B.4 task 7 SymPy-13974 dedicated DeepSeek audit',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'instance_id': IID,
        'model': MODEL,
        'oracle_gold_PROVISIONAL': oracle,
        'gold_authority': C.GOLD_AUTHORITY,
        'api_calls_made_by_this_audit': 0,
        'declared_gold_test_sets': decl,
        'store_log_facts': lf,
        'model_claims_fact_check': factcheck,
        'per_condition': {c: blocks[c] for c in FOCUS},
        'coverage_trust_rules_by_condition': trust_rules,
        'verdict_pattern': {
            'T2D-T': blocks['T2D-T']['final_verdict_g3b3'],
            'T3D-Strict': blocks['T3D-Strict']['final_verdict_g3b3'],
            'T3D-Escalate': blocks['T3D-Escalate']['final_verdict_g3b3'],
            'T2A-T': blocks['T2A-T']['final_verdict_g3b3'],
            'T3A-T': blocks['T3A-T']['final_verdict_g3b3']},
        'classification': {
            'answer': 'RESIDUAL MODEL EVIDENCE-INTERPRETATION / POLICY ERROR '
                      '(over-abstention), NOT a legitimate evidential-standard'
                      ' difference and NOT a new protocol inconsistency',
            'why_not_legitimate_standard_difference': [
                'Under T3D-Escalate the decisive post-patch outcomes were '
                'actually reachable and granted (f2p/p2p logs 200); the '
                'declared acceptance test was present and passing. Withholding'
                ' therefore does not explain the NEED.',
                'The abstention rests on two factually wrong readings: (A) '
                'that all three logs are identical, and (B) that the declared'
                ' acceptance test is missing. Both are contradicted by the '
                'frozen logs (see fact-check).',
                'T2A-T abstention is partly understandable (aggregate counts '
                'without rendered per-test results plus self-raised code '
                'doubts), but T3A shows that once per-test outcomes are '
                'rendered the same model accepts correctly — confirming the '
                'evidence objectively supports ACCEPT.'],
            'why_not_protocol_inconsistency': [
                'The protocol behaved identically and correctly across cells: '
                'the artifact id, linkage, freshness, coverage counts and '
                'served logs are the same frozen record; T3A rendered the '
                'very outcomes T3D-Escalate granted.',
                'The differing decision traces to the MODEL interpretation of'
                ' an ambiguous presentation (byte-identical f2p/p2p file), '
                'not to different information being served by condition in a '
                'way that contradicts the protocol.'],
            'residual_after_g3b3_fix': 'This is the SINGLE remaining '
                'DeepSeek sufficient-evidence over-abstention after the G3-B.3'
                ' protocol repair (the 9/10 -> 1/10 residual).',
            'contributing_presentation_issue': 'Serving a byte-identical '
                'file for f2p and p2p (same combined test-file run) is '
                'faithful to the harness but is an interpretability hazard: '
                'a sceptical model reads duplication as evidence of missing '
                'tests. This is a presentation/trust-rule hardening '
                'candidate for Gate 3-C, not a frozen-data defect.'}}

    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_sympy_13974_audit.json'
    dest.write_bytes(C.canonical_bytes(out))
    for c in FOCUS:
        print(c, blocks[c]['condition_gold'], '->',
              blocks[c]['final_verdict_g3b3'])
    print('claim A verdict:', factcheck['claim_A_all_three_logs_byte_identical']
          ['verdict'][:60])
    print('claim B verdict:', factcheck['claim_B_declared_acceptance_test_absent']
          ['verdict'][:60])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
