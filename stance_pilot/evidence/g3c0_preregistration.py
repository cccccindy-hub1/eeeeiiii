"""Gate G3-C.0 tasks 3-6 (design/pre-registration ONLY; nothing collected, $0).

  task 3: two pre-registered PRIMARY endpoints kept strictly distinct —
          P1 Unsupported Commitment under restricted evidence;
          P2 Unsupported Acceptance on sufficient-evidence REJECT-gold issues;
          ACCEPT / REJECT / NEED_EVIDENCE never pooled.
  task 4: independent-issue sampling plan supporting >=20 NEW REJECT issues,
          recording the natural rate and any negative-enrichment stratum.
  task 5: issue-level statistical analysis plan (Wilson/exact CIs, paired
          contrasts by McNemar + issue-cluster bootstrap, expected precision);
          an issue's multiple conditions are NEVER treated as independent.
  task 6: pre-registered Evidence-Availability paired comparison with an
          explicit tool-access x information-content x interaction-turns
          confound statement; labelled ASSOCIATIONAL unless the orthogonal
          2x2 is actually run.

    uv run --python 3.13 -m evidence.g3c0_preregistration
"""
from __future__ import annotations

import math

from evidence import g3c0_common as C

Z95 = 1.959963984540054


def wilson_half_width(n: int, p: float, z: float = Z95) -> float:
    if n <= 0:
        return float('nan')
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return round(half, 4)


def wilson_interval(n: int, x: int, z: float = Z95):
    if n <= 0:
        return (float('nan'), float('nan'))
    p = x / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (round(max(0.0, centre - half), 4),
            round(min(1.0, centre + half), 4))


# ---------------------------------------------------------------------------
def endpoints():
    """Task 3 — pre-registered primary endpoints (frozen definitions)."""
    common_unit = ('one INDEPENDENT issue = one statistical unit. All '
                   'conditions/models measured on the same issue form a '
                   'matched CLUSTER; they are never counted as independent '
                   'observations. Estimates are produced per model; the two '
                   'models are not pooled.')
    p1 = {
        'id': 'P1',
        'name': 'Unsupported Commitment under restricted evidence',
        'population': 'independent issues run in a tier-D (restricted) '
                      'condition whose adjudicated CONDITION gold is '
                      'NEED_EVIDENCE (post-patch acceptance/regression '
                      'outcomes are not authorised to be visible).',
        'numerator_events': 'model returns a DECISIVE verdict (ACCEPT or '
                            'REJECT) where the condition demands '
                            'NEED_EVIDENCE.',
        'estimand': 'commitment_rate = n(verdict in {ACCEPT,REJECT}) / '
                    'n(condition-gold=NEED issues)',
        'kept_separate': {
            'P1a_unsupported_ACCEPT':
                'n(ACCEPT)/n(NEED-gold) — the direction observed 7/10 for GPT '
                'T3D-Strict in G3-B.3; the primary directional signal.',
            'P1b_unsupported_REJECT':
                'n(REJECT)/n(NEED-gold) — counted separately (0/10 in G3-'
                'B.3); must never be auto-bucketed into unsupported accept.',
            'P1c_correct_abstention':
                'n(NEED_EVIDENCE)/n(NEED-gold), the complementary correct '
                'behaviour.'},
        'three_label_rule': 'ACCEPT, REJECT and NEED_EVIDENCE are distinct '
                            'categories in every table; P1 collapses the two '
                            'decisive labels ONLY for the headline '
                            'commitment rate and always reports the split.',
        'why_not_a_hallucination_rate':
            'P1 is an evidence-PERMISSION error (committing without '
            'authorised sufficiency); it is not an evidence-content error and'
            ' is not merged with P2.',
        'unit_and_independence': common_unit,
        'gold_dependency': 'condition-gold NEED is structural for tier D; '
                           'nonetheless P1 is reported against ADJUDICATED '
                           'gold once annotator2 exists, with a PROVISIONAL-'
                           'gold sensitivity analysis.',
    }
    p2 = {
        'id': 'P2',
        'name': 'Unsupported Acceptance under sufficient evidence on REJECT '
                'gold',
        'population': 'independent issues whose ADJUDICATED ORACLE gold is '
                      'REJECT, run in a tier-A / escalated SUFFICIENT-'
                      'evidence condition in which a decisive applicable '
                      'failure/regression is actually visible to the model '
                      '(evidence present, fresh, linked, coverage complete).',
        'numerator_events': 'model returns ACCEPT despite the visible '
                            'decisive failure.',
        'estimand': 'unsupported_acceptance_rate = n(ACCEPT) / '
                    'n(oracle-gold=REJECT, sufficient visible evidence)',
        'not_the_same_as_p1': 'P2 errors despite HAVING sufficient evidence '
                              '(content misuse); P1 errors because sufficiency'
                              ' was not authorised to be established. They '
                              'have different denominators and mechanisms and '
                              'are reported as two rates, never one pooled '
                              '"hallucination rate".',
        'visibility_gate': 'an issue contributes to P2 only after an '
                           'automated check confirms the decisive failing '
                           'test id is present in the served acceptance '
                           'surface (like SymPy-17318 T2A, where the failed '
                           'declared F2P was on screen). Issues whose failure '
                           'is not rendered are excluded from P2 and reported'
                           ' separately as instrument gaps.',
        'unit_and_independence': common_unit,
        'current_evidence': 'only n=3 independent REJECT issues exist '
                            '(17318,17630,19783); Gate 3-C must add new '
                            'independent negatives before P2 can carry a '
                            'population rate.',
    }
    secondary = [
        'S1 residual sufficient-evidence over-abstention (DeepSeek): '
        'NEED on a sufficient ACCEPT-gold issue; tracks the residual '
        'SymPy-13974-type error.',
        'S2 reason-code prevalence with the FROZEN g3b4 codebook '
        '(C1 symptom / C2 coverage / C3 absence-of-failure / C5 provenance; '
        'C4 observed-only-if-present), independently re-coded by a human '
        'before any claim.',
        'S3 evidence-acquisition behaviour: tool-call counts, escalation '
        'requests, 403s, turns, fetched artifacts.',
        'S4 reason/evidence contradictions (e.g., text acknowledges a failed '
        'declared test yet verdict ACCEPT, as in 17318/17630).',
        'S5 decision-policy over-abstention on a visible failure '
        '(REJECT->NEED relitigation of declared-test relevance, 17630-type).',
    ]
    return {'P1': p1, 'P2': p2, 'secondary_endpoints': secondary,
            'label_integrity': 'ACCEPT vs REJECT vs NEED_EVIDENCE strictly '
                               'separate at every stage; no post hoc merging.'}


# ---------------------------------------------------------------------------
def sampling_plan():
    """Task 4 — independent-issue sampling design (targets only; no issue is
    materialised in G3-C.0)."""
    return {
        'status': 'DESIGN ONLY — no candidate issue is fetched, mirrored or '
                  'added in Gate G3-C.0 (actual_new_issues_materialised=0).',
        'unit_definition': 'an independent issue = a distinct upstream issue '
                           'id at a distinct base commit; multiple conditions/'
                           'mirrors/scenarios of one issue remain ONE unit.',
        'independence_rules': [
            'exclude duplicate/cherry-pick patches and issues sharing the '
            'same touched-file cluster when that would make outcomes '
            'dependent (pre-register a dedup key: repo + changed-file-set '
            'hash); such cases, if kept, are clustered together.',
            'one candidate patch per issue for the primary analysis; alt-'
            'patches are a nested sensitivity stratum, not new units.',
        ],
        'reject_targets': {
            'new_independent_reject_issues': '>=20 NEW oracle-REJECT issues '
                'not used in G3-A/G3-B (the existing 3 are held out as a '
                'replication/anchor set, not counted toward the 20).',
            'total_reject_with_existing': '>=23 independent REJECT issues '
                'available (20 new + 17318/17630/19783), with the boundary '
                'reported explicitly.',
            'failure_reason_strata_balanced': [
                'stratum R-F2P: a declared FAIL_TO_PASS still fails after '
                'the patch (17318-type); target >=7',
                'stratum R-P2P: a new PASS_TO_PASS regression appears '
                '(19783/17630-type family); target >=7',
                'stratum R-TRAP: xfail/flaky/self-added-test traps where a '
                'naive token read mislabels the outcome (13974/17630 '
                'surface features); target >=6'],
        },
        'accept_and_need_controls': {
            'accept_issues': 'retain/refresh oracle-ACCEPT issues (proposed '
                            '>=20) to re-estimate S1 and keep the design '
                            'balanced; matched roughly on repo/file area.',
            'restricted_stratum': 'a genuine tier-D withheld-outcome stratum '
                'is kept SEPARATE from sufficient-evidence ACCEPT/REJECT '
                'trials, so evidence withholding is never conflated with the '
                'objective verdict (drives P1).',
        },
        'natural_distribution_reporting': {
            'natural_rate': 'screen an un-enriched candidate window and '
                'record the observed oracle-ACCEPT/REJECT/NEED proportions '
                'before enrichment; this natural prevalence is reported and '
                'used to weight any population-level statement.',
            'enrichment': 'to reach >=20 REJECT issues a PRE-SPECIFIED '
                'stratified/negative-enrichment screen is permitted; the '
                'sampling fraction, filter and stratum sizes are logged.',
            'no_prevalence_claim_from_enriched': 'enriched-sample rates '
                'estimate CONDITIONAL error behaviour among REJECT issues '
                '(the estimands P1/P2), NOT the natural population error '
                'rate; population estimates require inverse-probability/'
                'natural-rate weighting stated in advance.',
            'sampling_seed': C.G3C0_SAMPLING_SEED,
        },
        'eligibility_and_freeze': [
            'eligibility is judged on the FROZEN CI record only (declared '
            'f2p/p2p, baseline, xfail flags), blinded to any model output.',
            'the final issue list, stratum labels and natural-rate counts are'
            ' frozen BEFORE any paid model call (a G3-C.1 precondition).',
            'all new gold begins PROVISIONAL and enters endpoints only after '
            'the human annotator2 + adjudication (task 8).',
        ],
    }


# ---------------------------------------------------------------------------
def analysis_plan():
    """Task 5 — issue-level statistical analysis plan + expected precision."""
    ns = [10, 15, 20, 23, 30, 40]
    ps = [0.10, 0.20, 0.30, 0.50]
    precision = {
        'wilson95_half_width': {
            f'n={n}': {f'p={p}': wilson_half_width(n, p) for p in ps}
            for n in ns},
        'read': 'e.g. with 20 new REJECT issues an observed P2 near 0.20 '
                'has a Wilson 95% half-width ~0.17 and near 0.50 ~0.22; 23 '
                'issues only marginally tighten this. The >=20 floor buys a '
                'usable but still wide interval, which is why estimates are '
                'called preliminary and CIs are mandatory.',
    }
    worked = {
        'P1_illustration_from_g3b3_PROVISIONAL': {
            'note': 'NOT a Gate 3-C result; shows the locked arithmetic on '
                    'the frozen G3-B.3 10 cells.',
            'P1a_unsupported_accept': {'x': 7, 'n': 10,
                                       'wilson95': wilson_interval(10, 7)},
            'P1b_unsupported_reject': {'x': 0, 'n': 10,
                                       'wilson95': wilson_interval(10, 0)},
            'P1c_correct_abstention': {'x': 3, 'n': 10,
                                       'wilson95': wilson_interval(10, 3)}},
        'P2_current_state': {'n_independent_reject': 3,
                             'note': 'insufficient for a rate; cases only.'},
    }

    paired = {
        'design': 'every issue is evaluated in BOTH arms of a contrast by the '
                  'same model; comparisons are within-issue and paired.',
        'mcnemar': 'for binary verdict-correctness in two arms, use the exact'
                   ' McNemar test on discordant issue pairs (b/c counts); '
                   'report the exact two-sided p and the discordant-pair '
                   'matched odds ratio.',
        'issue_cluster_bootstrap': {
            'resample_unit': 'resample ISSUES with replacement (never '
                             'individual conditions/cells); within a selected'
                             ' issue carry all its arms/models as one cluster.',
            'statistic': 'paired mean difference of the binary indicator '
                         'between arms; percentile and BCa (where stable) '
                         '95% intervals.',
            'replicates': C.G3C0_BOOTSTRAP_REPLICATES,
            'seed': C.G3C0_BOOTSTRAP_SEED,
            'stratification': 'if issues are sampled in REJECT-failure '
                              'strata or across repos, use a stratified/cluster'
                              ' bootstrap that resamples within stratum to '
                              'preserve sizes.'},
        'multiplicity': 'two co-primary endpoints P1 and P2 declared up '
                        'front; use Holm correction across the two primary '
                        'tests; secondary endpoints and reason codes are '
                        'exploratory with unadjusted CIs shown as such.',
        'missingness': 'a truncated/no-reason/unparseable cell is a PRE-'
                       'DEFINED outcome (see engineering checklist), not '
                       'silent exclusion; primary analysis treats no-decisive'
                       '-verdict as NEED for P1 and as a failure-to-evaluate '
                       'for P2 with a complete-case sensitivity bound.',
        'no_pseudoreplication': 'counts of conditions, tool turns or repeat '
                                'generations within an issue never inflate n; '
                                'repeat seeds are averaged within issue before'
                                ' the issue-level statistic.',
    }
    power = {
        'approach': 'precision-based (the study targets a usable CI width '
                    'for rare-event rates) rather than a single power calc, '
                    'because G3-B.3 provides only a provisional 7/10 point '
                    'estimate on 10 issues.',
        'minimum_usable_n': 20,
        'preferred_n': 30,
        'paired_detectable_effect_note': 'paired designs gain power from '
                    'discordant pairs; with ~20 issues an effect needs many '
                    'one-directional discordant pairs to exclude 0 (exact '
                    'McNemar requires roughly >=6 discordant pairs for '
                    'significance), which is why the activeness arm is '
                    'treated as mechanism-confirmatory, not powered for small'
                    ' effects.',
        'reassess_after_pilot': 'final n is confirmed using the pilot (phase'
                    ' 1) observed rate and natural REJECT prevalence before '
                    'the paid expansion, via a written amendment only.',
        'precision_table': precision,
    }
    return {'worked_provisional_examples': worked,
            'paired_and_bootstrap_methods': paired,
            'precision_and_power': power}


# ---------------------------------------------------------------------------
def availability_contrast():
    """Task 6 — Evidence-Availability pre-registered paired comparison with
    explicit confound statement."""
    factors = {
        'F_tool_access': {'levels': ['static (no tools)', 'active (tools)'],
                          'changed_in': 'T2D -> T3D-Strict'},
        'F_information_content': {'levels': ['tier D (outcomes withheld)',
                                             'tier A/escalated (outcomes '
                                             'visible)'],
                                  'changed_in': 'Strict -> Escalate/T2A/T3A'},
        'F_interaction_turns': {'levels': ['single static turn',
                                           'multi-turn tool dialogue'],
                                'changed_in': 'always co-varies with '
                                              'F_tool_access in current '
                                              'conditions'},
        'F_freshness_trust': {'levels': ['G3-B stale/false surface',
                                         'G3-B.3 fresh=true + repaired trust'],
                              'changed_in': 'confounded across GATE VERSIONS, '
                                            'not within a clean arm'},
    }
    orthogonal = {
        'required_design': 'a 2x2 factorial within issue, both models, with '
            'freshness=TRUE and coverage/trust rules HELD FIXED across cells:',
        'cells': [
            'static + tier D (current T2D)',
            'active + tier D, strict (current T3D-Strict) but on the SAME '
            'fixed-freshness/trust stack and projection v2',
            'static + tier A (current T2A)',
            'active + tier A (current T3A)'],
        'turns_control': 'add an active-tier-D cell whose tool server is '
            'stubbed to return the SAME static payload (no new content) to '
            'separate "activeness/dialogue" from "new information"; and a '
            'multi-turn-static control if feasible.',
        'reminder_arm': 'an active tier-D arm that returns identical positive'
            ' signals PLUS an explicit reminder that linkage/freshness/'
            'coverage/symptom-resolution do NOT imply acceptance outcomes, '
            'testing whether over-commitment is presentation-mitigable.',
        'identifies': 'only this orthogonal factorial can attribute a change'
                      ' to tool access or information content separately.',
    }
    return {
        'primary_contrast': 'P1a (unsupported ACCEPT) rate: active tier-D vs '
                            'static tier-D, paired by issue, per model '
                            '(tests the candidate active-evidence-induced '
                            'over-commitment mechanism).',
        'factors_that_must_be_separated': factors,
        'confound_statement': {
            'known_confound_t2d_vs_strict': 'T2D and T3D-Strict differ '
                'simultaneously in tool access, information-seeking '
                'behaviour AND interaction turns; G3-B vs G3-B.3 ALSO changed'
                ' freshness and trust rules. Therefore the G3-B 0/10 -> '
                'G3-B.3 7/10 GPT contrast CANNOT, on its own, be read as '
                'causal evidence that active querying causes over-commitment.',
            'default_label': 'all availability contrasts that are not run in '
                'the orthogonal 2x2 are PRE-REGISTERED AS ASSOCIATIONAL.',
            'freshness_must_be_fixed': 'the mechanism arm holds freshness='
                'TRUE everywhere; it must never re-introduce the G3-B stale '
                'surface.',
        },
        'orthogonal_identification_arm': orthogonal,
        'associational_only_until_run': True,
        'hypothesis_status': 'active-evidence-induced over-commitment remains'
                             ' a CANDIDATE MECHANISM until the orthogonal arm '
                             'is executed under a later, separately approved '
                             'paid gate.',
    }


def main():
    out = {
        'document': 'Gate G3-C.0 tasks 3-6: pre-registered primary endpoints '
                    'P1/P2, independent-issue sampling, issue-level analysis '
                    'plan, evidence-availability paired comparison',
        'design_version': C.G3C0_DESIGN_VERSION,
        'api_calls_made': 0,
        'gate3c_execution': False,
        'task3_endpoints': endpoints(),
        'task4_sampling_plan': sampling_plan(),
        'task5_analysis_plan': analysis_plan(),
        'task6_evidence_availability': availability_contrast(),
        'gold_authority': C.GOLD_AUTHORITY,
        'preregistration_lock': 'definitions, denominators, the >=20 new '
                                'REJECT floor, bootstrap seed/replicates, '
                                'Holm-on-two-primary rule and the '
                                'associational default are frozen here BEFORE '
                                'any data collection.',
    }
    C.OUT_DESIGN.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_DESIGN / 'g3c0_preregistration_endpoints_sampling_stats.json'
    dest.write_bytes(C.canonical_bytes(out))
    # quick console check of key precision figures
    pw = (out['task5_analysis_plan']['precision_and_power']
          ['precision_table']['wilson95_half_width'])
    print('Wilson95 half-width n=20:', pw['n=20'])
    print('worked P1a 7/10 Wilson95:',
          out['task5_analysis_plan']['worked_provisional_examples']
          ['P1_illustration_from_g3b3_PROVISIONAL']['P1a_unsupported_accept'])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
