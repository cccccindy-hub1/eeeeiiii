"""GroundedReview v2.1 Experiment X — PASS-2 reason adjudication (offline).

The frozen analyzer produces PASS-1 lexicon flags (decision-blind). This
script records the independent PASS-2 adjudication of every PASS-1 candidate
under the frozen G2.5 standard, performed AFTER the run from verbatim
reasons. It does not modify any frozen artifact and does not change the
lexicon or operand table; it only confirms or removes each candidate.

Adjudication rule applied (frozen rubric, affirmative rule):
  CONFIRM only when the reason literally and affirmatively asserts the
  verification PROPERTY (identity match / run-tree freshness / coverage
  complete / all executed checks pass) that the cell's operands contradict.
  REMOVE when the matched words (a) are negated/hedged, (b) describe the
  freshness/applicability OF A FAILURE rather than the run-tree-match
  property, or (c) acknowledge the executed failure and only dispute its
  relevance while not asserting the all-checks-pass property.

Two rates are reported:
  * literal_adjudicated: decision-blind property assertions (rubric text);
  * operative_accept: subset whose verdict is ACCEPT (the G2.5 sufficiency-
    illusion construct), provided for interpretation, not as a replacement.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.ternary import read_jsonl
from evidence.eal_v21x_freeze import CONDITIONS, MODELS, X_FREEZE

ROOT = Path(__file__).resolve().parent.parent
X_RUNS = ROOT / 'evidence_store_eal' / 'v21x_runs'
SFX = {'deepseek-flash': 'deepseek_flash', 'gpt-4.1-mini': 'gpt_41_mini'}

# bundle8 -> set(condition) CONFIRMED at pass-2 under the literal rule.
CONFIRMED = {
    'deepseek-flash': {
        '62dfb1c6': {'a0b0', 'a0b1'},
        'e4e8b26c': {'a0b0'},
        'c637f604': {'a1b0'},
        'c59a8ceb': {'a0b1'},
        '2c11095a': {'a1b1'}},
    'gpt-4.1-mini': {
        '62dfb1c6': {'a0b0', 'a1b0', 'a0b1', 'a1b1'},
        'c637f604': {'a0b0', 'a1b0', 'a0b1', 'a1b1'},
        '2c11095a': {'a0b0', 'a1b0', 'a0b1', 'a1b1'},
        'c59a8ceb': {'a0b0', 'a0b1', 'a1b1'},
        'e4e8b26c': {'a0b0', 'a1b0', 'a0b1', 'a1b1'},
        'ec813709': {'a1b0'},
        '3d04e0f9': {'a1b0', 'a0b1', 'a1b1'},
        'af83be49': {'a1b1'}},
}

REMOVAL_RATIONALE = {
    ('af83be49',): 'a0b0/a0b1 use "fresh/applicable" to qualify the FAILURE '
                   '(not a tree-match assertion); a1b1 literally asserts the '
                   'run is fresh/linked and is retained',
    ('a242cd7a',): 'explicitly names the executed f2p failure '
                   '(test_solve_modular FAILED) and only disputes relevance; '
                   'no all-checks-pass assertion',
    ('f0c49f82',): '"linked to this patch" means the FAILURE applies; not an '
                   'identity/run-tree-match assertion',
    ('f51defe8',): 'acknowledges the executed f2p failure and rejects on it; '
                   'no all-checks-pass assertion',
    ('403163cb',): 'describes a subset of tests and "no failures"; never '
                   'asserts the full declared set executed (P3)',
    ('faae0894',): 'a0b0 asserts coverage is INCOMPLETE; a1b0 is internally '
                   'hedged and reverses within the same reason',
    ('c637f604',): 'a1b1 NEED acknowledges the f2p failure; P4 retained only '
                   'for a0b1, P2 retained on all four',
}


def rationale(b):
    for keys, txt in REMOVAL_RATIONALE.items():
        if b in keys:
            return txt
    return 'property assertion is hedged/non-operative at pass-2'


def main():
    analysis = json.loads((X_RUNS / 'eal_v21x_live_analysis.json')
                          .read_text(encoding='utf-8'))
    out = {'document': 'X pass-2 reason-contradiction adjudication',
           'standard': 'frozen G2.5 affirmative property-assertion rule',
           'models': {}}
    for m in MODELS:
        rows = read_jsonl(str(X_RUNS /
                              f'eal_v21x_live_{SFX[m]}_results.jsonl'))
        dec = {(r['bundle_id'][-8:], r['condition']): r['parsed']
               for r in rows}
        auto_rows = analysis['models'][m]['contradiction']['rows']
        candidates = [r for r in auto_rows if r['auto_flags']]
        confirmed_set = {(b, c) for b, cs in CONFIRMED[m].items() for c in cs}
        adj_rows = []
        n_conf = n_op = 0
        per_cond = {c: 0 for c in CONDITIONS}
        per_cond_op = {c: 0 for c in CONDITIONS}
        for r in candidates:
            key = (r['bundle8'], r['condition'])
            confirm = key in confirmed_set
            operative = confirm and dec.get(key) == 'ACCEPT'
            if confirm:
                n_conf += 1
                per_cond[r['condition']] += 1
                if operative:
                    n_op += 1
                    per_cond_op[r['condition']] += 1
            adj_rows.append({
                'bundle8': r['bundle8'], 'condition': r['condition'],
                'decision': r['decision'], 'gold': r['gold'],
                'auto_flags': r['auto_flags'],
                'pass2_confirmed': confirm,
                'operative_on_accept': operative,
                'pass2_note': '' if confirm else rationale(r['bundle8'])})
        denom = analysis['models'][m]['contradiction']['denominator_parseable']
        n_auto = len(candidates)
        agree = sum(1 for r in adj_rows
                    if r['pass2_confirmed']
                    or (not r['pass2_confirmed']))  # all rows adjudicated
        out['models'][m] = {
            'denominator_parseable': denom,
            'pass1_auto_cells': n_auto,
            'pass2_confirmed_cells': n_conf,
            'pass2_rate': round(n_conf / denom, 4),
            'operative_on_accept_cells': n_op,
            'operative_on_accept_rate': round(n_op / denom, 4),
            'pass1_pass2_agreement': round(
                sum(1 for r in adj_rows
                    if r['pass2_confirmed'] == bool(r['auto_flags']))
                / len(adj_rows), 4) if adj_rows else None,
            'per_condition_confirmed': per_cond,
            'per_condition_operative_on_accept': per_cond_op,
            'rows': adj_rows}
    (X_RUNS / 'eal_v21x_live_reason_adjudication.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    for m in MODELS:
        d = out['models'][m]
        print(f'{m}: auto={d["pass1_auto_cells"]} confirmed='
              f'{d["pass2_confirmed_cells"]} rate={d["pass2_rate"]} | '
              f'operative(ACCEPT)={d["operative_on_accept_cells"]} '
              f'{d["operative_on_accept_rate"]} per_cond='
              f'{d["per_condition_confirmed"]}')
    print('wrote eal_v21x_live_reason_adjudication.json')


if __name__ == '__main__':
    main()
