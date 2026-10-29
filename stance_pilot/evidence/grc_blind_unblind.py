"""GroundedReview consolidation — UNBLIND pass-3 vs frozen pass-2 ($0).

Runs ONLY after grc_blind_coding.json is complete. Opens the sealed key and
compares the blind pass-3 coding against the frozen pass-2 cell verdicts in
eal_v21x_live_reason_adjudication.json.

Coding is property-level; the frozen pass-2 is cell-level. A pass-3 cell is
CONFIRMED iff at least one auto-flagged property is CONFIRMED.

Outputs grc_blind_unblind.json with per-cell join, raw/positive/negative
agreement, per-model confirmed and operative-on-accept rates, and the full
disagreement list. Does not modify any frozen artifact.

DISCLOSED LIMITS (do not erase): the pass-3 coder is the SAME agent that
authored pass-2 (residual recall bias); blinding removed model/condition/
gold/decision/pass2 labels but assisted-cell prose sometimes mentions the
provided count tables, so condition is occasionally inferable from text.
Agreement therefore quantifies test-retest/self-consistency of one coder,
NOT independent inter-annotator reliability.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTDIR = ROOT / 'evidence_store_eal' / 'consolidation'
KEY = OUTDIR / 'grc_blind_key_SEALED.json'
CODING = OUTDIR / 'grc_blind_coding.json'
OUT = OUTDIR / 'grc_blind_unblind.json'

PROP_PREFIX = 'P'


def main():
    key = {k['blind_id']: k for k in
           json.loads(KEY.read_text(encoding='utf-8'))['key']}
    coding = json.loads(CODING.read_text(encoding='utf-8'))['verdicts']
    assert set(key) == set(coding), 'blind id set drift'

    rows = []
    for bid in sorted(key):
        k = key[bid]
        c = coding[bid]
        props = [p for p in c if p.startswith(PROP_PREFIX)]
        p3_conf = any(c[p] == 'C' for p in props)
        p3_conf_props = sorted(p for p in props if c[p] == 'C')
        agree = (p3_conf == bool(k['pass2_confirmed']))
        # operative pass-3: blind confirmed contradiction AND cell is ACCEPT.
        # decision label is only consulted HERE, post-coding.
        p3_operative = p3_conf and k['decision'] == 'ACCEPT'
        rows.append({
            'blind_id': bid, 'model': k['model'], 'bundle8': k['bundle8'],
            'condition': k['condition'], 'decision': k['decision'],
            'gold': k['gold'], 'flagged_properties': k['auto_flags'],
            'pass3_confirmed_properties': p3_conf_props,
            'pass3_cell_confirmed': p3_conf,
            'pass2_confirmed': bool(k['pass2_confirmed']),
            'confirm_agreement': agree,
            'pass3_operative_on_accept': p3_operative,
            'pass2_operative_on_accept': bool(k['pass2_operative_on_accept']),
            'borderline': bool(c.get('borderline')),
            'pass3_note': c.get('note', '')})

    def rates(sub):
        n = len(sub)
        both_c = sum(r['pass3_cell_confirmed'] and r['pass2_confirmed']
                     for r in sub)
        both_n = sum((not r['pass3_cell_confirmed']) and
                     (not r['pass2_confirmed']) for r in sub)
        p3c = sum(r['pass3_cell_confirmed'] for r in sub)
        p2c = sum(r['pass2_confirmed'] for r in sub)
        agree = sum(r['confirm_agreement'] for r in sub)
        # Cohen's kappa
        po = agree / n
        pe = ((p3c * p2c) + ((n - p3c) * (n - p2c))) / (n * n)
        kappa = (po - pe) / (1 - pe) if pe < 1 else None
        return {'n_cells': n, 'pass3_confirmed': p3c,
                'pass2_confirmed': p2c,
                'pass3_confirmed_rate': round(p3c / n, 4),
                'pass2_confirmed_rate': round(p2c / n, 4),
                'raw_agreement': round(agree / n, 4),
                'both_confirmed': both_c, 'both_not_confirmed': both_n,
                'cohen_kappa': None if kappa is None else round(kappa, 4)}

    by_model = {m: rates([r for r in rows if r['model'] == m])
                for m in sorted({r['model'] for r in rows})}
    overall = rates(rows)

    # operative on accept, only among rows either pass labels operative
    op_rows = [r for r in rows if r['pass3_operative_on_accept']
               or r['pass2_operative_on_accept']]
    op_by_model = {}
    for m in sorted({r['model'] for r in rows}):
        sub = [r for r in rows if r['model'] == m]
        op_by_model[m] = {
            'pass3_operative_accept': sum(r['pass3_operative_on_accept']
                                         for r in sub),
            'pass2_operative_accept': sum(r['pass2_operative_on_accept']
                                         for r in sub)}

    disagree = [r for r in rows if not r['confirm_agreement']]
    result = {
        'document': 'Post-unblinding pass-3 (blind) vs frozen pass-2 join. '
                    'Same-coder, partially-blind sensitivity check, NOT '
                    'independent inter-annotator reliability.',
        'coding_standard': coding.get('document', ''),
        'overall_confirm': overall,
        'by_model_confirm': by_model,
        'operative_on_accept_by_model': op_by_model,
        'n_disagreements': len(disagree),
        'disagreements': disagree,
        'borderline_cells': [r['blind_id'] for r in rows if r['borderline']],
        'rows': rows}
    OUT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2,
                                sort_keys=True) + '\n').encode())

    print('overall', overall)
    for m, v in by_model.items():
        print(m, v)
    print('operative', op_by_model)
    print('disagreements:', [(r['blind_id'], r['model'], r['bundle8'],
                              r['condition'], r['decision'],
                              r['pass3_cell_confirmed'],
                              r['pass2_confirmed']) for r in disagree])
    print('->', OUT.name)


if __name__ == '__main__':
    main()
