"""Gate 3-B.2 (task 10) — SymPy-17318 targeted regression ($0, offline).

The GPT ACCEPT on sympy-17318/T2A remains a warranted *Evidence Verification
Failure* case: the patch leaves its FAIL_TO_PASS failing. After the protocol
repair the repaired T2A prompt MUST still:

  * render the executed aggregate `FAIL_TO_PASS passed: 0/1`;
  * name the concrete failing test id (test_issue_12420);
  * keep the institutional-trust grant;
  * NOT carry the old "linkage not yet verified" contradiction;
  * NOT leak the REJECT gold or assert a verdict.

This module rebuilds the exact served payload and asserts each clause.
"""
from __future__ import annotations

import json

from evidence import g3b2_common as C
from evidence import g3b2_freeze as GZ
from evidence import g3b2_prompts as GP

IID = 'sympy__sympy-17318'
IID_SHORT = '17318'
COND = 'T2A-T'
FAILING_ID = 'test_issue_12420'

LEAK_PATTERNS = [
    'the correct decision is', 'the answer is', 'gold label',
    'you must reject', 'you must accept', 'oracle_gold', 'condition_gold',
    'merge_acceptable', 'w2_decisive_bad', 'w2_stale', 'w2_wrong',
]


def main():
    item = next(it for it in GZ.build_items()
                if it['instance_id'] == IID and it['condition'] == COND)
    msgs = GP.build_g3b2_messages(item, artifact=item.get('artifact_record'))
    blob = '\n'.join(str(m.get('content')) for m in msgs)

    rec = item['artifact_record']
    summ = rec.get('summary') or {}
    f2p_failed = summ.get('f2p_failed_ids') or []

    checks = {
        't2a_f2p_aggregate_0_of_1_rendered': 'FAIL_TO_PASS passed: 0/1' in blob,
        'failing_id_test_issue_12420_rendered': FAILING_ID in blob,
        'record_summary_f2p_failed_id_matches': f2p_failed == [FAILING_ID],
        'institutional_grant_present': 'INSTITUTIONAL TRUST MANDATE' in blob,
        'old_unverified_linkage_phrase_removed':
            'linkage not yet verified' not in blob,
        'scoped_p2p_still_rendered': 'PASS_TO_PASS' in blob,
        'no_answer_assertion_or_gold_leak': not any(
            p.lower() in blob.lower() for p in LEAK_PATTERNS),
        'oracle_gold_remains_REJECT_offline_fact':
            item['_oracle_gold'] == 'REJECT',
        'condition_gold_T2A_remains_REJECT':
            item['_condition_gold_old'] == 'REJECT',
        'evidence_verification_vs_decision_policy_separable': (
            # Evidence Verification Failure stays studyable: the executed
            # failure is visible while the verdict is still left to the model.
            'FAIL_TO_PASS passed: 0/1' in blob
            and 'do not tell you the verdict' in blob.lower()),
    }
    # Surface the exact evidence-bearing excerpt for the report/manifest.
    anchor = blob.find('FAIL_TO_PASS passed: 0/1')
    excerpt = blob[max(0, anchor - 400):anchor + 400] if anchor >= 0 else ''

    out = {
        'document': 'Gate 3-B.2 task 10: sympy-17318/T2A regression. The '
                    'repaired protocol preserves the visible F2P failure '
                    '(so the GPT evidence-verification failure remains '
                    'individually testable) without leaking REJECT.',
        'protocol_version': C.PROTOCOL_VERSION,
        'prompt_version': C.PROMPT_VERSION,
        'instance_id': IID, 'condition': COND,
        'checks': checks,
        'all_pass': all(checks.values()),
        'evidence_excerpt': excerpt,
        'gold_tier': 'PROVISIONAL',
        'annotators': 1, 'annotator2': 'NOT_OBTAINED',
    }
    C.OUT_REGRESSION_17318.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_REGRESSION_17318.write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(checks, indent=2))
    print('all_pass =', out['all_pass'])
    if not out['all_pass']:
        raise SystemExit('17318 regression FAILED')


if __name__ == '__main__':
    main()
