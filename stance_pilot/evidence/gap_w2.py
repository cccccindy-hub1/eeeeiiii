"""Wave-2 Task 7 (DW2-3): NEED_EVIDENCE gap classification + grounding.

When a reviewer answers NEED_EVIDENCE under prompt v2 it must also return a
structured ``evidence_gap`` in:

    stale | linkage_mismatch | coverage_incomplete | contradiction | unspecified

``classify_abstention`` decides whether that claim is GROUNDED, using only
facts the condition actually makes accessible plus the tool verdicts the
reviewer actually obtained before its final decision:

  verified_gap
      stale/linkage/coverage claim corroborated by an adjudicated endpoint
      verdict IN THIS CELL (verify/freshness/coverage returned false), and the
      projected surface independently agrees the fact is false. Static
      conditions (T2D-T/T2A-T) cannot adjudicate these, so such a claim can
      never be verified there.
  decisive_in_hand_but_abstained
      a contradiction gap (or any NEED answer) while decisive, accessible
      contradictory evidence is in hand: a consistency verdict of
      'contradicted', an observed persisting symptom against a positive claim,
      or a presented acceptance block that already renders failing ids. That
      evidence supports REJECT in this condition; abstaining is a distinct
      error class, not a valid abstention.
  claimed_but_unverified
      a concrete stale/linkage/coverage/contradiction gap was named but the
      required endpoint/log evidence was not obtained in this cell, was
      withheld by the regime, or does not corroborate the claim.
  unspecified
      no gap / empty / unrecognised value: blanket abstention.

The function is pure: it takes the condition, the claimed gap, the projected
presented_facts (evidence.visibility.project_surface) and the observed
tool_verdicts; it never reads model labels, scenario names, or ground truth
beyond the presented surface.
"""
from __future__ import annotations

GAPS = ('stale', 'linkage_mismatch', 'coverage_incomplete',
        'contradiction', 'unspecified')

VERIFIED_GAP = 'verified_gap'
CLAIMED_BUT_UNVERIFIED = 'claimed_but_unverified'
DECISIVE_IN_HAND_BUT_ABSTAINED = 'decisive_in_hand_but_abstained'
UNSPECIFIED = 'unspecified'

CATEGORIES = (VERIFIED_GAP, CLAIMED_BUT_UNVERIFIED,
              DECISIVE_IN_HAND_BUT_ABSTAINED, UNSPECIFIED)

# gap -> (tool_verdicts key, presented_facts channel key)
_INTEGRITY_GAP = {
    'stale': ('freshness', 'freshness'),
    'linkage_mismatch': ('linkage', 'linkage'),
    'coverage_incomplete': ('coverage', 'coverage'),
}


def _integrity_verified(gap, surface, tool_verdicts):
    """A stale/linkage/coverage gap is grounded only when:
      1. the condition actively adjudicates that channel (endpoint exists),
      2. the reviewer actually called the endpoint before deciding, and it
         returned the negative verdict,
      3. the projected surface's own ground value agrees (guards a scripted
         client lying about a verdict)."""
    tv_key, surf_key = _INTEGRITY_GAP[gap]
    chan = surface.get(surf_key) or {}
    # Active ternary conditions expose a real boolean verdict; static
    # conditions show identity strings/timestamps only (value is None).
    if chan.get('value') is None:
        return False, f'{surf_key} is not adjudicated in this condition'
    observed = tool_verdicts.get(tv_key)
    if observed is None:
        return False, f'{tv_key} endpoint was not called before the decision'
    if observed is not False:
        return False, f'{tv_key} endpoint returned {observed!r}, not a violation'
    if chan.get('value') is not False:
        return False, (f'{tv_key} verdict is not corroborated by the served '
                       f'evidence ({chan.get("value")!r})')
    return True, f'{tv_key}=false adjudicated and corroborated in this cell'


def _contradiction_assessment(surface, tool_verdicts):
    """Return (decisive_in_hand, grounding, reasons).

    Accessible decisive contradiction channels per condition (see
    visibility.project_surface / gold_w2.condition_gold):
      * symptom: rendered in T2D static block; symptom-only strict verdict
        under T3D-Strict; raw symptom log under Escalate/T3A; hidden at T2A.
      * consistency endpoint: contradicted verdict at every ACTIVE condition
        (strict = symptom-only; escalate = acceptance-based with reason;
        T3A = acceptance-based).
      * T2A static acceptance block: rendered failing ids are themselves a
        contradiction of a positive claim.
    """
    reasons, accessible, in_hand = [], False, False
    cond = surface['condition']
    symptom = surface.get('symptom') or {}
    outcomes = surface.get('acceptance_outcomes') or {}

    # 1. Consistency endpoint verdict (active conditions only).
    verdict = tool_verdicts.get('consistency')
    consistency_possible = surface.get('policy') is not None or cond == 'T3A-T'
    # T3A-T has policy None but is active; distinguish from static T2A-T via
    # the presence of adjudicated linkage.
    active = surface.get('linkage', {}).get('value') is not None \
        and surface['linkage'].get('status') == 'adjudicable'
    if active:
        if verdict == 'contradicted':
            in_hand = True
            accessible = True
            reasons.append('consistency endpoint returned contradicted')
        elif verdict is None:
            reasons.append('contradiction claimed but consistency endpoint '
                           'was not called')
        else:
            reasons.append(f'consistency endpoint returned {verdict!r}')

    # 2. Symptom channel: observable polarity or an explicitly observed log.
    if symptom.get('observable'):
        accessible = True
        polarity = symptom.get('polarity')
        observed_persists = tool_verdicts.get('symptom_persists')
        if polarity == 'persists' and (observed_persists is not False):
            # Rendered in the static block (T2D) or observed via the log on
            # active conditions. An explicit False observation would mean the
            # reviewer's log reading disagreed with the served polarity.
            in_hand = True
            reasons.append('the issue symptom still reproduces post-patch '
                           'and is observable in this condition')
        elif observed_persists is True:
            in_hand = True
            reasons.append('symptom log shows the symptom persists')
        else:
            reasons.append('symptom channel accessible but no persisting '
                           'symptom observed')
    else:
        hidden = symptom.get('polarity_exists_but_hidden')
        if hidden:
            reasons.append('persisting symptom exists but is hidden in this '
                           'condition')
        else:
            reasons.append('symptom is not observable in this condition')

    # 3. T2A static presentation: failing ids rendered outright.
    if outcomes.get('status') == 'presented':
        accessible = True
        if (outcomes.get('failure_count') or 0) > 0:
            in_hand = True
            reasons.append('the acceptance block presents failing check ids')

    return in_hand, accessible, reasons


def classify_abstention(condition, gap, presented_facts, tool_verdicts=None):
    """Classify a NEED_EVIDENCE answer's grounding (DW2-3).

    Returns a dict:
      {'category': one of CATEGORIES, 'gap': normalised gap, 'condition': ...,
       'basis': human-readable explanation}
    """
    tool_verdicts = dict(tool_verdicts or {})
    surface = presented_facts
    if surface.get('condition') != condition:
        # Tolerate callers that pass the bare condition separately.
        surface = dict(surface)
        surface['condition'] = condition
    norm = (gap or '').strip().lower() or 'unspecified'
    if norm not in GAPS:
        norm = 'unspecified'

    if norm == 'unspecified':
        return {'category': UNSPECIFIED, 'gap': norm, 'condition': condition,
                'basis': 'no specific evidence gap was named (blanket '
                         'abstention)'}

    if norm == 'contradiction':
        in_hand, accessible, reasons = _contradiction_assessment(
            surface, tool_verdicts)
        if in_hand:
            return {'category': DECISIVE_IN_HAND_BUT_ABSTAINED, 'gap': norm,
                    'condition': condition,
                    'basis': 'accessible decisive contradiction is in hand '
                             'yet the reviewer abstained: '
                             + '; '.join(reasons)}
        if not accessible:
            return {'category': CLAIMED_BUT_UNVERIFIED, 'gap': norm,
                    'condition': condition,
                    'basis': 'contradiction cannot be established in this '
                             'condition: ' + '; '.join(reasons)}
        return {'category': CLAIMED_BUT_UNVERIFIED, 'gap': norm,
                'condition': condition,
                'basis': 'contradiction claimed but not established: '
                         + '; '.join(reasons)}

    # integrity gaps: stale / linkage_mismatch / coverage_incomplete
    ok, why = _integrity_verified(norm, surface, tool_verdicts)
    if ok:
        return {'category': VERIFIED_GAP, 'gap': norm, 'condition': condition,
                'basis': why}
    return {'category': CLAIMED_BUT_UNVERIFIED, 'gap': norm,
            'condition': condition,
            'basis': f'{norm} claim is not grounded: {why}'}


# ---------------------------------------------------------------------------
# Truth-table helpers (TR-7.1): surfaces for every condition are produced by
# evidence.visibility.project_surface over real/synthetic fact bundles.
# ---------------------------------------------------------------------------

def _synthetic_facts(*, linked=True, fresh=True, complete=True,
                     failure=0, executed=3, polarity=None,
                     presented_failure=0, presented_executed=3):
    """Minimal oracle fact bundle shaped like visibility.load_fixture_facts,
    sufficient for project_surface (presented_a_record only used by T2A gold,
    not by this classifier)."""
    return {
        'linked': linked, 'fresh': fresh, 'complete': complete,
        'executed_failure_count': failure,
        'executed_check_count': executed,
        'symptom_polarity': polarity,
        'symptom': ({'pre_patch_passed': False,
                     'post_patch_passed': polarity != 'gone'}
                    if polarity is not None else None),
        'presented_failure_count': presented_failure,
        'presented_check_count': presented_executed,
        'presented_a_record': {
            'summary': {
                'f2p_total': presented_executed,
                'f2p_passed': presented_executed - presented_failure,
                'p2p_total': 0, 'p2p_passed': 0,
                'f2p_failed_ids': (['x'] if presented_failure else []),
                'p2p_regressed_ids': []}},
    }
