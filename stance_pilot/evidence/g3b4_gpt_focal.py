"""Gate 3-B.4 task 8: two DISTINCT GPT error families, kept in separate
tables and never pooled:

  Family F1 — SymPy-17318 / T2A-T  erroneous ACCEPT (evidence-verification
  failure): the declared FAIL_TO_PASS acceptance test actually FAILED in the
  frozen run, yet GPT accepted from a static tier-A surface, persisting across
  G3-B -> G3-B.3.

  Family F2 — SymPy-17630 / T3A-T  REJECT -> NEED_EVIDENCE shift (decision
  policy / over-abstention in the presence of a real declared failure): GPT
  reads the failing declared F2P test but declines to REJECT because it judges
  the failure unrelated to the patch.

All raw reasons and failing-test evidence are retained verbatim. Offline, $0.
"""
from __future__ import annotations

import hashlib
import json
import re

from evidence import g3b4_common as C
from evidence.store import ArtifactStore

MODEL = 'gpt-4.1-mini'
STORE = ArtifactStore(str(C.G3A / 'store'),
                      fixtures_meta_name='g3a_fixtures_meta.json')


def cell(by, issue, model, cond):
    return next(c for c in by[issue]['models'][model]
                if c['condition'] == cond)


def log_evidence(aid):
    out = {}
    for kind in ('f2p', 'p2p'):
        p = C.G3A_STORE_LOGS / f'{aid}.{kind}.log'
        b = p.read_bytes()
        txt = b.decode('utf-8', errors='replace')
        statuses = re.findall(r'\b(PASSED|FAILED|ERROR|XFAIL)\b', txt)
        fail_lines = [ln.strip() for ln in txt.splitlines()
                      if re.search(r'FAILED|ERROR', ln)]
        out[kind] = {
            'file': p.name, 'bytes': len(b),
            'sha256': hashlib.sha256(b).hexdigest(),
            'status_counts': {s: statuses.count(s) for s in set(statuses)},
            'failure_lines_verbatim': fail_lines}
    return out


def declared(issue):
    for r in C.read_jsonl(C.G3A_TARGET_ROWS):
        if r['instance_id'] == issue:
            return {'resolved': r.get('resolved'),
                    'FAIL_TO_PASS': r['FAIL_TO_PASS'],
                    'PASS_TO_PASS_n': len(r['PASS_TO_PASS'])}
    raise KeyError(issue)


def artifact_summary(aid):
    rec, auth = STORE.get(aid)
    assert auth
    return rec.get('summary')


def main():
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    by = {i['issue']: i for i in pe['issues']}
    fz = C.load_data_freeze()
    g3b = {(r['instance_id'], r['condition']): r
           for r in C.read_jsonl(C.G3B_LIVE_GPT)}

    def aid_of(issue):
        return next(c['served_artifact_id'] for c in fz['cells']
                    if c['instance_id'] == issue)

    # ---------------- Family F1: 17318 / T2A-T ----------------------------
    i1 = 'sympy__sympy-17318'
    t2a = cell(by, i1, MODEL, 'T2A-T')
    t3a = cell(by, i1, MODEL, 'T3A-T')
    a1 = aid_of(i1)
    f1 = {
        'family': 'F1_ERRONEOUS_ACCEPT_EVIDENCE_VERIFICATION_FAILURE',
        'issue': '17318', 'focal_condition': 'T2A-T',
        'oracle_gold_PROVISIONAL': by[i1]['oracle_gold'],
        'condition_gold_T2A': t2a['condition_gold'],
        'declared_gold_sets': declared(i1),
        'artifact_summary': artifact_summary(a1),
        'store_log_evidence': log_evidence(a1),
        'g3b_historical_verdict_T2A': g3b[(i1, 'T2A-T')]['parsed'],
        'g3b3_verdict_T2A': t2a['g3b3_verdict'],
        'g3b3_verdict_T3A_control': t3a['g3b3_verdict'],
        'persists_g3b_to_g3b3': (g3b[(i1, 'T2A-T')]['parsed'] == 'ACCEPT'
                                 and t2a['g3b3_verdict'] == 'ACCEPT'),
        'T2A_static_tools': [t['tool'] for t in t2a['tool_responses']],
        'T3A_active_control_reason_full': t3a['g3b3_model_reasoning'],
        'T2A_erroneous_reason_full_verbatim': t2a['g3b3_model_reasoning'],
        'error_mechanism': 'On the static tier-A T2A surface GPT asserted '
            '"all relevant acceptance tests passing" and "no failures or '
            'regressions" although the declared F2P test test_issue_12420 '
            'FAILED (assert [4 + I, 0, 1] == []). The static surface exposes '
            'aggregate counts but not the rendered per-test failure, and the '
            'model did not verify; it converted a "fresh/linked/complete" '
            'presentation into an unverified green claim. The active T3A '
            'control on the SAME issue correctly REJECTed once the per-test '
            'failure was rendered.',
        'why_distinct_from_family_F2': 'this is a false ACCEPT against a real'
            ' failing declared test (over-commitment / evidence-verification '
            'failure), not an abstention'}

    # ---------------- Family F2: 17630 / T3A-T ----------------------------
    i2 = 'sympy__sympy-17630'
    u2_t2a = cell(by, i2, MODEL, 'T2A-T')
    u2_t3a = cell(by, i2, MODEL, 'T3A-T')
    a2 = aid_of(i2)
    f2 = {
        'family': 'F2_REJECT_TO_NEED_OVER_ABSTENTION_ON_DECLARED_FAILURE',
        'issue': '17630', 'focal_condition': 'T3A-T',
        'oracle_gold_PROVISIONAL': by[i2]['oracle_gold'],
        'condition_gold_T3A': u2_t3a['condition_gold'],
        'declared_gold_sets': declared(i2),
        'artifact_summary': artifact_summary(a2),
        'store_log_evidence': log_evidence(a2),
        'g3b_historical_verdict_T3A': g3b[(i2, 'T3A-T')]['parsed'],
        'g3b3_verdict_T2A': u2_t2a['g3b3_verdict'],
        'g3b3_verdict_T3A': u2_t3a['g3b3_verdict'],
        'transition_T3A': f"{g3b[(i2,'T3A-T')]['parsed']} -> "
                          f"{u2_t3a['g3b3_verdict']}",
        'T3A_tools': [{'turn': t['turn'], 'tool': t['tool'],
                       'http_status': t['http_status'],
                       'log_name': (t.get('args') or {}).get('name')}
                      for t in u2_t3a['tool_responses']],
        'T2A_reason_full_verbatim': u2_t2a['g3b3_model_reasoning'],
        'T3A_reason_full_verbatim': u2_t3a['g3b3_model_reasoning'],
        'objective_fact': 'the declared FAIL_TO_PASS set contains '
            'test_zero_matrix_add and it FAILED in the frozen run '
            '(f2p_failed_ids=[test_zero_matrix_add], f2p_passed=1/2). The '
            'other FAILED tokens in the combined log are XFail markers '
            '(pre-existing expected failures), not declared regressions; '
            'p2p_preexisting_bad_ids=[] and p2p_regressed_ids=[].',
        'error_mechanism': 'GPT saw the failing declared F2P test but '
            'classified it as "unrelated to the patch issue" and therefore '
            'abstained NEED_EVIDENCE instead of REJECT. Under the declared '
            'acceptance contract a failing declared FAIL_TO_PASS id is '
            'decisive for non-resolution regardless of the model\u2019s '
            'subjective relevance judgement. This is a decision-policy / '
            'over-abstention error (relitigating declared-test relevance), '
            'not a missing-evidence situation.',
        'why_distinct_from_family_F1': 'the model did NOT accept and did not '
            'miss the failure; it saw a real declared failure and softened a '
            'mandatory REJECT into NEED by second-guessing test relevance'}

    out = {
        'document': 'Gate 3-B.4 task 8 GPT focal error families (kept '
                    'separate, not pooled)',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'api_calls_made_by_this_audit': 0,
        'families_are_distinct': True,
        'family_F1_17318_T2A': f1,
        'family_F2_17630_T3A': f2,
        'cross_family_note': 'F1 is over-commitment (false ACCEPT despite a '
                            'real failing declared test); F2 is over-'
                            'abstention (NEED despite a real failing declared'
                            ' test that mandates REJECT). They are different '
                            'error directions and must not be merged into one '
                            '"GPT failure" statistic.',
        'independent_negative_example_caveat': 'The G3-B.3 independent-REJECT'
            ' set is only n=3 issues; these two cases are illustrative, not a '
            'rate estimate. Gold is PROVISIONAL (single annotator).',
        'gold_authority': C.GOLD_AUTHORITY}

    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_gpt_focal_families.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('F1 17318/T2A:', f1['g3b_historical_verdict_T2A'], '->',
          f1['g3b3_verdict_T2A'], '| T3A control', f1['g3b3_verdict_T3A_control'])
    print('F2 17630/T3A:', f2['transition_T3A'])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
