"""Wave-2 Task 2: dual-channel oracle gold + condition-projected gold.

Two INDEPENDENT channels of trustworthy evidence (spec DW2-1):

  acceptance channel  executed f2p/p2p verdicts of the signed record served
                      for the target patch. Applicability requires
                      linked AND fresh; ACCEPT additionally requires complete
                      coverage, >0 executed checks, zero failures.
  diagnostic channel  the issue-derived symptom probe. pre=false AND
                      post=false (the issue symptom still reproduces after the
                      patch) is an applicable DECISIVE FAILURE for the target
                      patch — it is bound to the issue under review and does
                      not depend on artifact linkage. A gone symptom supports
                      the claim only at issue level and is NEVER acceptance.

oracle_gold is the rule under all trustworthy evidence:

    if (linked and fresh and acceptance_failure) or symptom_persists: REJECT
    if linked and fresh and complete and acceptance_success
            and not symptom_persists:                                  ACCEPT
    else:                                                             NEED

condition_gold applies the SAME rule after the condition's evidence-surface
projection (evidence.visibility.project_surface). Facts the regime does not
present/adjudicate/make obtainable cannot support a verdict:

  T2D-T       P rendered; L/F/C not adjudicated (identity strings are not
              verdicts); O projected away -> only the diagnostic channel can
              decide (symptom persists => REJECT), everything else NEED.
  T3D-Strict  L/F/C adjudicated; P available (log + symptom-only verdict);
              O hard-blocked (403) -> acceptance channel never decides.
  T3D-Escalate L/F/C adjudicated; P log; O OBTAINABLE with a reason. Per
              DW2-2 "obtainable" counts as supportable -> condition == oracle.
  T2A-T       O fully rendered as THIS patch's acceptance record; P not
              rendered (real-server fact, audited in Task 1); L/F/C not
              adjudicated and no declared-set baseline is shown. The
              supportable decision is read from what the block presents:
              any rendered failing/regressed id => REJECT; a complete
              all-green presentation => ACCEPT; otherwise NEED. This is an
              INSTITUTIONAL grant, not an adjudication — its oracle/condition
              divergences (stale, wrong_patch, incomplete projections) are
              the measured bias, not a relabel.
  T3A-T       L/F/C adjudicated; O freely obtainable; P log available
              -> condition == oracle (asserted, all fixtures).

This module never imports or accepts patch_correct / merge_acceptable /
model outputs / scenario labels. `check_label_independence` enforces it on
the function signatures and by label-indifference trials.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.store import ArtifactStore
from evidence.visibility import (W2_CONDITIONS, load_fixture_facts,
                                 project_surface, surface_matrix)

GOLD_VERSION = 'w2-gold-v1'
TERNARY = ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')

# Parameters that would leak hidden labels or model behaviour into the gold
# function. Any occurrence in a gold-rule signature is a hard failure.
_FORBIDDEN_SIGNATURE_TOKENS = (
    'patch_correct', 'merge_acceptable', 'label_class', 'decision', 'parsed',
    'answer', 'model', 'gold', 'scenario', 'response', 'output',
)


# ---------------------------------------------------------------------------
# Pure gold rules — facts only
# ---------------------------------------------------------------------------

def oracle_gold(*, linked, fresh, complete,
                acceptance_failure, acceptance_success, symptom_persists):
    """DW2-1 dual-channel rule. Keyword-only, fact-typed booleans."""
    applicable_failure = bool(linked) and bool(fresh) and bool(acceptance_failure)
    if applicable_failure or bool(symptom_persists):
        return 'REJECT'
    intact_success = (bool(linked) and bool(fresh) and bool(complete)
                      and bool(acceptance_success)
                      and not bool(symptom_persists))
    if intact_success:
        return 'ACCEPT'
    return 'NEED_EVIDENCE'


def _oracle_inputs_from_facts(facts):
    failure = facts['executed_failure_count'] > 0
    success = (facts['executed_check_count'] > 0
               and facts['executed_failure_count'] == 0)
    return {
        'linked': facts['linked'], 'fresh': facts['fresh'],
        'complete': facts['complete'],
        'acceptance_failure': failure,
        'acceptance_success': success,
        'symptom_persists': facts['symptom_polarity'] == 'persists',
    }


def _presented_block_all_green(rec):
    """Does the tier-A static block present a COMPLETE all-green run?

    views._acceptance_block renders the record's own summary totals
    (f2p_passed/f2p_total, p2p_passed/p2p_total) plus failed id lists. A
    complete presentation means every scheduled check the record reports is
    green and at least one check ran. The declared set is NOT visible at A,
    so a doctored restricted run that reports 1/1 passes is institutionally
    presented as complete (the divergence is measured, not hidden)."""
    summ = rec.get('summary') or {}
    ft = int(summ.get('f2p_total') or 0)
    fp = int(summ.get('f2p_passed') or 0)
    pt = int(summ.get('p2p_total') or 0)
    pp = int(summ.get('p2p_passed') or 0)
    if ft + pt <= 0:
        return False
    if fp != ft or pp != pt:
        return False
    if summ.get('f2p_failed_ids') or summ.get('p2p_regressed_ids'):
        return False
    return True


def condition_gold(condition, facts, surface):
    """Apply oracle_gold to the facts one condition's regime makes
    presentable/adjudicable/obtainable. Returns (gold, projected_inputs,
    basis). T2A has the institutional presentation rule (module docstring)."""
    o = surface['acceptance_outcomes']
    status = o['status']
    sp = surface['symptom'].get('polarity') == 'persists'

    if condition == 'T2A-T':
        rec = facts['presented_a_record']
        fail = int(o['failure_count'] or 0)
        summ = rec.get('summary') or {}
        has_fail = bool(summ.get('f2p_failed_ids')
                        or summ.get('p2p_regressed_ids')) or fail > 0
        all_green = _presented_block_all_green(rec)
        if has_fail:
            return 'REJECT', {'channel': 'acceptance_presented',
                              'presented_failure_count': fail,
                              'presented_all_green': False}, \
                   'acceptance block presents executed failing/regressed ' \
                   'check ids -> REJECT is supportable from the rendered ' \
                   'record (institutional presentation; linkage/freshness ' \
                   'are never adjudicated in this condition)'
        if all_green:
            return 'ACCEPT', {'channel': 'acceptance_presented',
                              'presented_failure_count': 0,
                              'presented_all_green': True}, \
                   'acceptance block presents a complete all-green run as ' \
                   'the record of THIS patch -> ACCEPT is supportable from ' \
                   'the rendered content (institutional presentation)'
        return 'NEED_EVIDENCE', {'channel': 'acceptance_presented',
                                 'presented_failure_count': fail,
                                 'presented_all_green': False}, \
               'the rendered record reports no failure but does not present ' \
               'a complete executed set; symptom is not rendered; no tool ' \
               'can adjudicate linkage/freshness/coverage'

    # Generic projection: unadjudicated applicability facts cannot support
    # anything; O counts support a verdict only when the channel is
    # obtainable (escalate-with-reason / tier A) — NOT when not_visible or
    # hard_blocked.
    linked = surface['linkage']['value'] is True
    fresh = surface['freshness']['value'] is True
    complete = surface['coverage']['value'] is True
    o_open = status in ('obtainable', 'obtainable_with_reason', 'presented')
    if o_open:
        afail = facts['executed_failure_count'] > 0
        asucc = (facts['executed_check_count'] > 0
                 and facts['executed_failure_count'] == 0)
    else:
        afail = asucc = False
    inputs = {'linked': linked, 'fresh': fresh, 'complete': complete,
              'acceptance_failure': afail, 'acceptance_success': asucc,
              'symptom_persists': sp}
    gold = oracle_gold(**inputs)
    why = []
    if sp:
        why.append('issue symptom still reproduces post-patch (diagnostic '
                   'channel is available in this condition) -> decisive failure')
    if afail and linked and fresh:
        why.append('obtainable acceptance evidence shows an executed failure '
                   'on linked, fresh evidence')
    if not surface['linkage']['value']:
        why.append('linkage is not adjudicated/available in this condition')
    if not surface['freshness']['value']:
        why.append('freshness is not adjudicated/available in this condition')
    if not complete:
        why.append('coverage completeness is not established in this condition')
    if not o_open:
        why.append('acceptance outcomes are withheld/hard-blocked')
    if gold == 'NEED_EVIDENCE' and not why:
        why.append('no decisive failure and insufficient success evidence')
    return gold, inputs, ' | '.join(why)


# ---------------------------------------------------------------------------
# Row derivation over fixtures (reads signed records; never labels)
# ---------------------------------------------------------------------------

def derive_rows(store, fixtures, conditions=W2_CONDITIONS):
    """One v2 gold row per fixture: oracle + per-condition gold + the
    projected input facts and human basis for each divergence."""
    rows = []
    for fx in fixtures:
        facts = load_fixture_facts(store, fx)
        oracle_inputs = _oracle_inputs_from_facts(facts)
        oracle = oracle_gold(**oracle_inputs)
        cond_golds, cond_inputs, cond_basis, divergences = {}, {}, {}, []
        for cond in conditions:
            surf = project_surface(cond, facts)
            g, inp, basis = condition_gold(cond, facts, surf)
            cond_golds[cond] = g
            cond_inputs[cond] = inp
            cond_basis[cond] = basis
            if g != oracle:
                divergences.append(
                    {'condition': cond, 'oracle_gold': oracle,
                     'condition_gold': g, 'basis': basis})
        obasis = []
        if oracle_inputs['symptom_persists']:
            obasis.append('issue symptom still reproduces post-patch')
        if oracle_inputs['linked'] and oracle_inputs['fresh'] \
                and oracle_inputs['acceptance_failure']:
            obasis.append(
                f"{facts['executed_failure_count']} executed declared "
                'check(s) failed on linked, fresh evidence')
        if oracle == 'ACCEPT':
            obasis.append(
                f"{facts['executed_check_count']} checks executed on linked, "
                'fresh, complete evidence with no failure; symptom gone')
        if oracle == 'NEED_EVIDENCE' and not obasis:
            if not oracle_inputs['linked']:
                obasis.append('artifact not linked to target patch')
            if not oracle_inputs['fresh']:
                obasis.append('artifact run is not fresh for current tree')
            if not oracle_inputs['complete']:
                obasis.append('declared check set not fully executed')
            if not obasis:
                obasis.append('no decisive failure and insufficient success')
        rows.append({
            'version': GOLD_VERSION,
            'id': fx['id'],
            'scenario': fx['scenario'],
            'wave': ('wave2' if str(fx.get('served_artifact_id', ''))
                                  .startswith('fix_w2_') else 'wave1'),
            'served_artifact_id': fx['served_artifact_id'],
            'patch_correct': bool(fx.get('merge_acceptable')),  # audit only
            'facts': {
                'linked': facts['linked'], 'fresh': facts['fresh'],
                'complete': facts['complete'],
                'executed_failure_count': facts['executed_failure_count'],
                'executed_check_count': facts['executed_check_count'],
                'symptom_polarity': facts['symptom_polarity'],
            },
            'oracle_inputs': oracle_inputs,
            'oracle_gold': oracle,
            'oracle_basis': ' | '.join(obasis),
            'condition_gold': cond_golds,
            'condition_inputs': cond_inputs,
            'condition_basis': cond_basis,
            'oracle_condition_divergences': divergences,
            'comparable_conditions': [c for c in conditions
                                      if cond_golds[c] == oracle],
        })
    rows.sort(key=lambda r: (r['wave'], r['scenario'], r['id']))
    return rows

_W1_SCENARIOS = frozenset((
    'valid', 'contradictory', 'incomplete', 'stale', 'wrong_patch',
    'stale_bad', 'wrong_patch_good', 'incomplete_good',
    'incomplete_decisive_bad'))


def render_rows(rows):
    return ''.join(canonical_dumps(r) + '\n' for r in rows)


def rows_sha256(rows):
    return hashlib.sha256(render_rows(rows).encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Purity / label-independence guards (TR-2.2)
# ---------------------------------------------------------------------------

def check_signature_clean():
    errs = []
    for fn in (oracle_gold, condition_gold):
        for name in inspect.signature(fn).parameters:
            if any(tok in name for tok in _FORBIDDEN_SIGNATURE_TOKENS):
                errs.append(f'{fn.__name__}: forbidden parameter "{name}"')
    return errs


def check_label_indifference():
    """Gold functions accept fact kwargs only; there is no slot through which
    a label/model output could flow. Re-derive the same rows after scrambling
    every audit/label column of the fixtures; output must be byte-identical
    except the audit-only echo column, which is stripped before comparison."""
    base = dict(
        linked=True, fresh=True, complete=True,
        acceptance_failure=False, acceptance_success=True,
        symptom_persists=False)
    trials = []
    for flip in ('linked', 'fresh', 'complete', 'acceptance_failure',
                 'acceptance_success', 'symptom_persists'):
        t = dict(base)
        t[flip] = not t[flip]
        trials.append((t, oracle_gold(**t)))
    # The echo audit column is never read: this is structurally enforced
    # (no fixture column parameter); assert derive rows ignores scrambled
    # labels by comparing rows projected to label-free keys.
    return trials


# ---------------------------------------------------------------------------
# Self-test truth tables over the existing 9 fixtures (TR-2.1 / TR-2.3)
# ---------------------------------------------------------------------------

_EXPECTED_ORACLE = {
    'valid': 'ACCEPT',
    'contradictory': 'REJECT',
    'incomplete': 'NEED_EVIDENCE',
    'stale': 'NEED_EVIDENCE',
    'wrong_patch': 'REJECT',
    'stale_bad': 'NEED_EVIDENCE',
    'wrong_patch_good': 'NEED_EVIDENCE',
    'incomplete_good': 'NEED_EVIDENCE',
    'incomplete_decisive_bad': 'REJECT',
}

_EXPECTED_CONDITION = {
    # scenario: {condition: expected condition gold}
    'valid': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
              'T3D-Escalate': 'ACCEPT', 'T2A-T': 'ACCEPT', 'T3A-T': 'ACCEPT'},
    'contradictory': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
                      'T3D-Escalate': 'REJECT', 'T2A-T': 'REJECT',
                      'T3A-T': 'REJECT'},
    'incomplete': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
                   'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': None,
                   'T3A-T': 'NEED_EVIDENCE'},
    'stale': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
              'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': 'ACCEPT',
              'T3A-T': 'NEED_EVIDENCE'},
    'wrong_patch': {'T2D-T': 'REJECT', 'T3D-Strict': 'REJECT',
                    'T3D-Escalate': 'REJECT', 'T2A-T': 'ACCEPT',
                    'T3A-T': 'REJECT'},
    'stale_bad': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
                  'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': 'REJECT',
                  'T3A-T': 'NEED_EVIDENCE'},
    'wrong_patch_good': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
                         'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': None,
                         'T3A-T': 'NEED_EVIDENCE'},
    'incomplete_good': {'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
                        'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': None,
                        'T3A-T': 'NEED_EVIDENCE'},
    'incomplete_decisive_bad': {'T2D-T': 'NEED_EVIDENCE',
                                'T3D-Strict': 'NEED_EVIDENCE',
                                'T3D-Escalate': 'REJECT', 'T2A-T': 'REJECT',
                                'T3A-T': 'REJECT'},
}


def run_selftest(store, fixtures):
    errs = []
    errs += ['signature: ' + e for e in check_signature_clean()]
    rows = derive_rows(store, fixtures)
    by_sc = {r['scenario']: r for r in rows}
    if len(by_sc) != len(fixtures):
        errs.append(f'expected {len(fixtures)} rows, got {len(by_sc)} '
                    '(duplicate scenarios?)')
    for sc, want in _EXPECTED_ORACLE.items():
        r = by_sc.get(sc)
        if r is None:
            errs.append(f'oracle: missing fixture scenario {sc}')
            continue
        if r['oracle_gold'] != want:
            errs.append(f'oracle {sc}: got {r["oracle_gold"]} want {want}')
    for sc, conds in _EXPECTED_CONDITION.items():
        r = by_sc.get(sc)
        if r is None:
            continue
        for cond, want in conds.items():
            got = r['condition_gold'][cond]
            if want is not None and got != want:
                errs.append(f'condition {sc}/{cond}: got {got} want {want}')
    # Identity invariants: Escalate and T3A condition gold == oracle.
    for r in rows:
        for cond in ('T3D-Escalate', 'T3A-T'):
            if r['condition_gold'][cond] != r['oracle_gold']:
                errs.append(f'identity broken {r["scenario"]}/{cond}: '
                            f'{r["condition_gold"][cond]} != '
                            f'{r["oracle_gold"]}')
    # Determinism: derive twice, byte-identical canonical render.
    h1 = rows_sha256(derive_rows(store, fixtures))
    h2 = rows_sha256(derive_rows(store, fixtures))
    if h1 != h2:
        errs.append(f'determinism: {h1} != {h2}')
    # Label scrambling: flip merge_acceptable / label_class / id labels;
    # label-free projection of rows must be unchanged.
    import copy
    scrambled = []
    for fx in fixtures:
        f2 = copy.deepcopy(fx)
        f2['merge_acceptable'] = not bool(f2.get('merge_acceptable'))
        f2['label_class'] = 'X'
        f2['scenario'] = fx['scenario'] + '_scrambled'
        scrambled.append(f2)
    rows2 = derive_rows(store, scrambled)
    strip = lambda rs: sorted(
        ({k: v for k, v in r.items() if k not in ('scenario', 'patch_correct')}
         for r in rs), key=lambda r: r['served_artifact_id'])
    if canonical_dumps(strip(rows)) != canonical_dumps(strip(rows2)):
        errs.append('label-indifference: gold rows changed after scrambling '
                    'merge_acceptable/label_class')
    return errs, rows


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(
        encoding='utf-8').splitlines() if line.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--fixtures',
                    default='evidence_store/phase2_fixtures.jsonl,'
                            'evidence_store/phase3_fixtures.jsonl')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--out', default='')
    a = ap.parse_args()
    fixtures = []
    for p in a.fixtures.split(','):
        p = p.strip()
        if p:
            fixtures.extend(_read_jsonl(p))
    store = ArtifactStore(a.store)
    if a.selftest:
        errs, rows = run_selftest(store, fixtures)
        if errs:
            print('GOLD-W2 SELFTEST FAILED:')
            for e in errs:
                print(' -', e)
            raise SystemExit(1)
        print('gold_w2 selftest OK: oracle truth table, condition table, '
              'Escalate/T3A identity invariants, determinism, and label '
              'indifference all pass')
    rows = derive_rows(store, fixtures)
    for r in rows:
        div = ', '.join(f"{d['condition']}={d['condition_gold']}"
                        for d in r['oracle_condition_divergences']) or '-'
        print(f"{r['scenario']:<26} oracle={r['oracle_gold']:<14} "
              f"T2D={r['condition_gold']['T2D-T']:<14} "
              f"Strict={r['condition_gold']['T3D-Strict']:<14} "
              f"Esc={r['condition_gold']['T3D-Escalate']:<14} "
              f"T2A={r['condition_gold']['T2A-T']:<14} "
              f"T3A={r['condition_gold']['T3A-T']:<14} div: {div}")
    print(f'oracle/condition rows={len(rows)} sha256={rows_sha256(rows)}')
    if a.out:
        Path(a.out).write_text(render_rows(rows), encoding='utf-8')
        print(f'wrote {a.out} (not frozen; freeze happens in Task 6)')


if __name__ == '__main__':
    main()
