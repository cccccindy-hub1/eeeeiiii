"""Gate 3-B.2 (task 9) — offline preflight / self-check ($0).

Validates the repaired protocol payloads and artifacts before any future
G3-B.3 run could be authorised (G3-B.2 itself runs nothing paid):

  1. freeze canonical bytes on disk == deterministic rebuild; 100 balanced
     mock cells; call order balance;
  2. LABEL LEAKAGE: every one of the 50 served g3b2 message payloads is
     rebuilt and scanned — no gold/label key, no answer-assertion, tier-D
     withholds outcomes, and the new T2A institutional grant never states or
     implies ACCEPT/REJECT while still rendering the outcomes;
  3. EVIDENCE SUFFICIENCY: the 50 new certificates agree with the frozen
     g3a1 condition gold (0 value changes), 30 sufficient / 20 NEED;
  4. SCHEMA CONSISTENCY (three-state): freshness payloads use fresh_state in
     {TRUE,FALSE,UNKNOWN}, fresh in {true,false,null}, and null pairs only
     with UNKNOWN (never served as a substantive stale=false); mock rows are
     well-formed;
  5. BUDGET: G3-B.2 live budget is $0 and no real model profile is frozen; a
     BudgetGuard with cap $0 REFUSES even a tiny bound (the zero-API gate),
     while the frozen guard mechanics still accept a normal bound;
  6. RESUME/DETERMINISM: rebuilding the freeze yields identical canonical
     bytes (a resumed/rerun offline derivation cannot drift);
  7. FROZEN HASHES: G3-A (141) + G3-A.1 (122) + G3-B manifest + frozen code
     bytes are unchanged.
"""
from __future__ import annotations

import json

from evidence.phase3_run import BudgetGuard, BudgetGuardStop

from evidence import g3b2_common as C
from evidence import g3b2_freeze as GZ
from evidence import g3b2_prompts as GP
from evidence import g3b2_freshness as GF

FORBIDDEN_SUBSTRINGS = [
    'oracle_gold', 'condition_gold', 'merge_acceptable', 'label_class',
    '"resolved"', 'resolved_in_dataset', 'builder_label_class_audit_only',
    'w2_decisive_bad', 'w2_stale', 'w2_wrong',
]
ANSWER_PATTERNS = [
    'the correct decision is', 'the answer is', 'gold label',
    'should be accepted because it is known', 'you must accept',
    'you must reject', 'the verdict is accept', 'the verdict is reject',
]
OUTCOME_TOKENS_D_ONLY = ['FAIL_TO_PASS', 'PASS_TO_PASS']


def check_freeze_shape_and_bytes():
    on_disk = json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))
    rebuilt = GZ.build_freeze()
    # Parent verification embeds no nondeterminism; compare canonical bytes.
    same = GZ.canonical_bytes(on_disk) == GZ.canonical_bytes(rebuilt)
    order = on_disk['call_order']
    from collections import Counter
    cnt = Counter((o['mock_model'], o['condition']) for o in order)
    balanced = len(order) == 100 and set(cnt.values()) == {10}
    return {'canonical_bytes_deterministic': same,
            'n_cells': on_disk['n_mock_cells'], 'order_balanced': balanced,
            'api_budget_usd': on_disk['api_budget_usd'],
            'real_models': on_disk['real_models']}


def label_leakage_audit():
    items = GZ.build_items()
    hits = []
    for it in items:
        msgs = GP.build_g3b2_messages(it,
                                      artifact=it.get('artifact_record'))
        blob = '\n'.join(str(m.get('content')) for m in msgs)
        low = blob.lower()
        for tok in FORBIDDEN_SUBSTRINGS + ANSWER_PATTERNS:
            if tok.lower() in low:
                hits.append({'cell': it['cell_key'], 'token': tok})
        if it['evidence_tier'] == 'D':
            for tok in OUTCOME_TOKENS_D_ONLY:
                if tok in blob:
                    hits.append({'cell': it['cell_key'],
                                 'token': f'{tok} [tier-D withheld]'})
        if it['condition'] == 'T2A-T':
            # Grant must be present, must not assert the verdict, yet outcomes
            # remain rendered (Evidence Verification vs Decision Policy).
            if 'INSTITUTIONAL TRUST MANDATE' not in blob:
                hits.append({'cell': it['cell_key'],
                             'token': 'missing T2A grant'})
            if 'FAIL_TO_PASS passed' not in blob:
                hits.append({'cell': it['cell_key'],
                             'token': 'T2A outcomes not rendered'})
    return {'n_items': len(items), 'n_hits': len(hits), 'hits': hits}


def evidence_sufficiency_check():
    certs = C.read_jsonl(C.OUT_GOLD)
    changelog = json.loads(C.OUT_GOLD_CHANGELOG.read_text(encoding='utf-8'))
    n_suff = sum(1 for c in certs if c['sufficient_for_decision'])
    by_cond = {}
    for c in certs:
        d = by_cond.setdefault(c['condition'], {})
        d[c['condition_gold_new_protocol']] = \
            d.get(c['condition_gold_new_protocol'], 0) + 1
    provisional_ok = all(c['gold_tier'] == 'PROVISIONAL' and c['annotators'] == 1
                         and c['annotator2'] == 'NOT_OBTAINED' for c in certs)
    return {'n_certificates': len(certs), 'n_sufficient': n_suff,
            'n_need': len(certs) - n_suff,
            'n_value_changes': changelog['n_value_changes'],
            'distribution': by_cond,
            'all_provisional_n1': provisional_ok}


def schema_consistency_check():
    # Three-state enumeration + fresh/state coherence on all 50 items.
    states_ok = {GF.FRESH_TRUE, GF.FRESH_FALSE, GF.FRESH_UNKNOWN}
    items = GZ.build_items()
    bad = []
    for it in items:
        fr = it['_freshness_repaired']
        if fr['fresh_state'] not in states_ok:
            bad.append((it['cell_key'], 'bad state'))
        if fr['fresh_state'] == GF.FRESH_TRUE and fr['fresh'] is not True:
            bad.append((it['cell_key'], 'TRUE must pair fresh=true'))
        if fr['fresh_state'] == GF.FRESH_FALSE and fr['fresh'] is not False:
            bad.append((it['cell_key'], 'FALSE must pair fresh=false'))
        if fr['fresh_state'] == GF.FRESH_UNKNOWN and fr['fresh'] is not None:
            bad.append((it['cell_key'], 'UNKNOWN must pair fresh=null'))
    # Mock rows: well-formed, zero cost/api, mock flag.
    mock_audit = json.loads(C.OUT_MOCK_AUDIT.read_text(encoding='utf-8'))
    rows = []
    for p in sorted((C.G3B2 / 'runs').glob('g3b2_mock_*_results.jsonl')):
        rows.extend(C.read_jsonl(p))
    rows_ok = (len(rows) == 100
               and all(r['mock'] is True and r['research_excluded'] is True
                       and r['cost_usd'] == 0.0 and r['api_calls'] == 0
                       for r in rows))
    return {'n_items': len(items), 'n_state_violations': len(bad),
            'violations': bad[:10], 'n_mock_rows': len(rows),
            'mock_rows_zero_cost_and_flagged': rows_ok,
            'mock_match_rate': mock_audit['mock_match_rate']}


def budget_check():
    freeze = json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))
    # The $0 live gate: a zero-cap guard must refuse any nonzero bound.
    g0 = BudgetGuard(0.0, 0.30, 1.20)
    refused_zero = False
    try:
        g0.check(1, 0)
    except BudgetGuardStop:
        refused_zero = True
    # A normal (hypothetical, NOT used in B.2) cap accepts a tiny bound; this
    # only proves the frozen guard mechanics behave, not authorisation.
    g_pos = BudgetGuard(1.50, 0.30, 1.20)
    accepted_pos = False
    try:
        g_pos.check(100, 0)
        accepted_pos = True
    except BudgetGuardStop:
        accepted_pos = False
    return {'freeze_api_budget_usd': freeze['api_budget_usd'],
            'real_models_frozen': freeze['real_models'],
            'zero_cap_refuses_any_call': refused_zero,
            'guard_mechanics_normal_bound_accepted': accepted_pos}


def resume_determinism_check():
    a = GZ.canonical_bytes(GZ.build_freeze())
    b = GZ.canonical_bytes(GZ.build_freeze())
    return {'rebuild_bytes_identical': a == b,
            'freeze_sha256': C.sha256_bytes(a)}


def frozen_hash_check():
    parents = C.verify_frozen_parents()
    return {
        'g3a_files_verified': parents['g3a']['files_verified'],
        'g3a1_files_verified': parents['g3a1']['files_verified'],
        'g3b_freeze_manifest_sha256': parents['g3b_freeze_manifest']['sha256'],
        'n_frozen_code_modules': len(parents['frozen_code']),
    }


def main():
    report = {
        'document': 'Gate 3-B.2 task 9: offline preflight/self-check ($0).',
        'protocol_version': C.PROTOCOL_VERSION,
        'prompt_version': C.PROMPT_VERSION,
        'freeze_shape': check_freeze_shape_and_bytes(),
        'label_leakage': label_leakage_audit(),
        'evidence_sufficiency': evidence_sufficiency_check(),
        'schema_consistency_three_state': schema_consistency_check(),
        'budget': budget_check(),
        'resume_determinism': resume_determinism_check(),
        'frozen_hashes': frozen_hash_check(),
    }
    gates = {
        'freeze_canonical_and_balanced': (
            report['freeze_shape']['canonical_bytes_deterministic']
            and report['freeze_shape']['order_balanced']),
        'no_label_leakage': report['label_leakage']['n_hits'] == 0,
        'sufficiency_zero_changes': (
            report['evidence_sufficiency']['n_value_changes'] == 0
            and report['evidence_sufficiency']['n_sufficient'] == 30
            and report['evidence_sufficiency']['all_provisional_n1']),
        'three_state_schema_consistent': (
            report['schema_consistency_three_state']['n_state_violations'] == 0
            and report['schema_consistency_three_state'][
                'mock_rows_zero_cost_and_flagged']),
        'zero_api_gate': (
            report['budget']['freeze_api_budget_usd'] == 0.0
            and report['budget']['real_models_frozen'] == []
            and report['budget']['zero_cap_refuses_any_call']),
        'resume_deterministic':
            report['resume_determinism']['rebuild_bytes_identical'],
        'frozen_unchanged': (
            report['frozen_hashes']['g3a_files_verified'] == 141
            and report['frozen_hashes']['g3a1_files_verified'] == 122),
    }
    report['gates'] = gates
    report['all_gates_pass'] = all(gates.values())
    C.OUT_PREFLIGHT.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_PREFLIGHT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps(gates, indent=2))
    print('all_gates_pass =', report['all_gates_pass'])
    if not report['all_gates_pass']:
        raise SystemExit('g3b2 preflight gate FAILED')


if __name__ == '__main__':
    main()
