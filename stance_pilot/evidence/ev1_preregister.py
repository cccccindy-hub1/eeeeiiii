"""E1 pre-registered case-level analysis lock (offline preparation).

User instruction item 7: the case-level analyses for wrong_patch,
partial-but-decisive and incomplete_good must be PRE-REGISTERED before any
cross-model paid run; cherry-picking "typical cases" after seeing the new
model's output is forbidden.

This module:
  1. anchors the locked case sets by exact served_artifact_id (membership can
     never silently drift);
  2. loads the FROZEN Wave-2.1 gold and asserts every locked case still has
     the pre-registered oracle/condition pattern (the script fails loudly if
     the gold was changed);
  3. writes evidence_store_ev1/ev1_preregistration.json with, for every cell
     of every locked case: the expected decision under BOTH standards and the
     hypothesis label it tests (H1 over-abstention / H2 unsupported rejection
     / H3 verification-decision gap);
  4. provides evaluate_results(path) which mechanically classifies any future
     model result file on exactly these cells - no post-hoc selection.

The contradictory case shares the partial-but-decisive gold PATTERN but is
DELIBERATELY not in the locked sets: it was not named in the pre-registration
request, and adding it after seeing results would be exactly the kind of
post-hoc expansion that is prohibited.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from pilot import read_jsonl
from evidence.metrics_w2 import load_w2_gold

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLD = ROOT / 'evidence_store_w21' / 'wave2_gold.jsonl'
DEFAULT_OUT = ROOT / 'evidence_store_ev1' / 'ev1_preregistration.json'

COND = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')

# ---- membership anchors: exact artifact ids, frozen before E1 -------------
WRONG_PATCH = {
    # decisive bad patch: trusted symptom probe persists after patch.
    'fix_wrong_patch_05f2955c70897168': {
        'case': 'wrong_patch', 'role': 'trusted_decisive_failure',
        'expect_oracle': 'REJECT',
        'expect_condition': {
            'T2D-T': 'REJECT', 'T3D-Strict': 'REJECT',
            'T3D-Escalate': 'REJECT', 'T2A-T': 'ACCEPT',
            'T3A-T': 'REJECT'},
        'tests': ['H1', 'H3'],
        'analysis_rule':
            'On T3D-Strict/T3D-Escalate/T3A-T the independently executed '
            'symptom probe (pre fails, still fails after patch) is a trusted '
            'decisive failure and is acceptance-artifact independent. IF a '
            'model still returns NEED_EVIDENCE there (e.g. on linkage=false), '
            'that outcome WOULD BE a candidate instance of Over-Abstention '
            '(H1) - this is a HYPOTHESIS TO BE TESTED, not a claim that the '
            'new model will exhibit it. Mechanical scoring only labels the '
            'cell; the mechanism attribution is exploratory. T2A-T '
            'condition-gold ACCEPT is keyed on the served acceptance artifact '
            'only; abstaining there is appropriate under the condition '
            'standard but over-abstain under the oracle standard. Both '
            'standards are reported.'},
    # wrong-patch-shaped but GOOD artifact set served in T2A: no decisive
    # failure available -> oracle NEED.
    'fix_wrong_patch_good_244e7c27b638a272': {
        'case': 'wrong_patch', 'role': 'good_artifact_control',
        'expect_oracle': 'NEED_EVIDENCE',
        'expect_condition': {
            'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
            'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': 'ACCEPT',
            'T3A-T': 'NEED_EVIDENCE'},
        'tests': ['H2'],
        'analysis_rule':
            'Control sharing the wrong_patch issue. Only T2A-T may ACCEPT; '
            'IF a model returns REJECT in any other condition it has no '
            'decisive failure behind it and is mechanically labelled '
            'Unsupported Rejection (H2 candidate, hypothesis to test). '
            'Observation, not prediction.'},
}

PARTIAL_DECISIVE = {  # noqa: N816 - locked name
    'fix_incomplete_decisive_bad_97ac402dfa11643a',
    'fix_w2_decisive_bad_9e334c91c8d42c59',
    'fix_w2_decisive_bad_24795537946f1e5f',
}
PARTIAL_PATTERN = {
    'expect_oracle': 'REJECT',
    'expect_condition': {
        'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
        'T3D-Escalate': 'REJECT', 'T2A-T': 'REJECT',
        'T3A-T': 'REJECT'},
    'tests': ['H1', 'H3'],
    'analysis_rule':
        'complete=false with >=1 executed failure (partial-but-decisive). '
        'With only static/denied tools (T2D-T, T3D-Strict) the condition '
        'standard says NEED_EVIDENCE; the oracle standard still says REJECT, '
        'so abstention there is logged as oracle-over-abstain / condition-'
        'appropriate (the standards divergence is the point, not a scoring '
        'bug). With escalation (T3D-Escalate) or the acceptance artifact '
        '(T2A/T3A) REJECT is required: IF a model returns NEED_EVIDENCE '
        'there it is mechanically labelled Over-Abstention (H1 candidate, '
        'hypothesis to test), and ACCEPT is false approval. Whether the new '
        'model does so is not assumed.'}

INCOMPLETE_GOOD = {
    'fix_incomplete_good_244e7c27b638a272',
    'fix_w2_incomplete_good_0be6fdf9dc8c5195',
}
INCOMPLETE_GOOD_PATTERN = {
    'expect_oracle': 'NEED_EVIDENCE',
    'expect_condition': {
        'T2D-T': 'NEED_EVIDENCE', 'T3D-Strict': 'NEED_EVIDENCE',
        'T3D-Escalate': 'NEED_EVIDENCE', 'T2A-T': 'ACCEPT',
        'T3A-T': 'NEED_EVIDENCE'},
    'tests': ['H2'],
    'analysis_rule':
        'Incomplete evidence but the patch itself is good. Only T2A-T (valid '
        'acceptance artifact) may ACCEPT. IF a model returns REJECT in '
        'T2D-T/T3D-Strict/T3D-Escalate/T3A-T it is mechanically labelled '
        'Unsupported Rejection (H2 candidate, hypothesis to test): the '
        'reviewer converts "evidence incomplete" into "patch bad". The label '
        'is contingent on the observed decision, not a prediction that the '
        'new model will reject.'}

LOCKED = [('wrong_patch', WRONG_PATCH),
          ('partial_but_decisive', PARTIAL_DECISIVE),
          ('incomplete_good', INCOMPLETE_GOOD)]


def build_lock(gold):
    by_art = {r.get('served_artifact_id'): r for r in gold['rows']}
    cases = []
    errors = []

    def emit(art, spec, case_name, role=None):
        r = by_art.get(art)
        if r is None:
            errors.append(f'locked artifact missing from frozen gold: {art}')
            return
        if role:
            spec = {**spec, 'role': role}
        if r.get('oracle_gold') != spec['expect_oracle']:
            errors.append(
                f'{art}: oracle drift gold={r.get("oracle_gold")} '
                f'pre-registered={spec["expect_oracle"]}')
        cg = r.get('condition_gold') or {}
        for c, want in spec['expect_condition'].items():
            if cg.get(c) != want:
                errors.append(
                    f'{art} {c}: condition drift gold={cg.get(c)} '
                    f'pre-registered={want}')
        cases.append({
            'case_group': case_name,
            'scenario': r.get('scenario'),
            'id': r.get('id'),
            'instance_id': (r.get('id') or '').split(':')[-1],
            'served_artifact_id': art,
            'tests_hypotheses': spec['tests'],
            'role': spec.get('role'),
            'oracle_gold': r.get('oracle_gold'),
            'condition_gold': {c: cg.get(c) for c in COND},
            'cell_level_expectation': [
                {'condition': c,
                 'expected_oracle_standard': spec['expect_oracle'],
                 'expected_condition_standard':
                     spec['expect_condition'][c]}
                for c in COND],
            'analysis_rule': spec['analysis_rule'],
        })

    for art, spec in WRONG_PATCH.items():
        emit(art, spec, 'wrong_patch')
    for art in PARTIAL_DECISIVE:
        emit(art, PARTIAL_PATTERN, 'partial_but_decisive')
    for art in INCOMPLETE_GOOD:
        emit(art, INCOMPLETE_GOOD_PATTERN, 'incomplete_good')

    # reverse check: no gold row accidentally satisfies a locked pattern
    # without being a member (catches duplicate/renamed lookalikes)
    locked_arts = {a for _, grp in LOCKED for a in
                   (grp.keys() if isinstance(grp, dict) else grp)}
    if len(locked_arts) != 7:
        errors.append(f'expected 7 locked artifacts, got {len(locked_arts)}')
    return cases, errors, locked_arts


def evaluate_results(results_path, gold):
    """Mechanically score one model result file on locked cells only.

    No selection beyond the pre-registered membership; returns one verdict
    per locked (artifact, condition) cell under both standards.
    """
    cases, errors, locked = build_lock(gold)
    if errors:
        raise SystemExit('pre-registration lock invalid: ' + '; '.join(errors))
    want = {}
    for cs in cases:
        for cell in cs['cell_level_expectation']:
            want[(cs['served_artifact_id'], cell['condition'])] = (
                cell['expected_oracle_standard'],
                cell['expected_condition_standard'],
                cs['case_group'], cs['tests_hypotheses'])
    verdicts = []
    for r in read_jsonl(results_path):
        if r.get('error') or r.get('mock'):
            continue
        art = r.get('served_artifact_id')
        cond = r.get('condition')
        if (art, cond) not in want:
            continue
        exp_o, exp_c, group, hyps = want[(art, cond)]
        got = str((r.get('parsed') or {}).get('decision', '')
                  if isinstance(r.get('parsed'), dict)
                  else r.get('parsed') or '').upper() or 'INVALID'
        def tag(exp, got):
            if got in ('INVALID', 'AMBIGUOUS', ''):
                return 'protocol_failure'
            if got == exp:
                return 'appropriate'
            if got == 'NEED_EVIDENCE' and exp in ('ACCEPT', 'REJECT'):
                return 'over_abstention_H1'
            if got == 'REJECT' and exp in ('ACCEPT', 'NEED_EVIDENCE'):
                return 'unsupported_rejection_H2'
            if got == 'ACCEPT' and exp in ('REJECT', 'NEED_EVIDENCE'):
                return 'false_commit_accept'
            return 'other_mismatch'
        verdicts.append({
            'case_group': group, 'served_artifact_id': art,
            'condition': cond, 'hypotheses': hyps,
            'model_decision': got,
            'oracle_expected': exp_o, 'oracle_verdict': tag(exp_o, got),
            'condition_expected': exp_c,
            'condition_verdict': tag(exp_c, got),
            'verification_decision_gap_H3':
                bool(r.get('tool_calls')) and tag(exp_o, got) != 'appropriate'
                and got not in ('INVALID', 'AMBIGUOUS', ''),
        })
    summary = {}
    for v in verdicts:
        for std in ('oracle', 'condition'):
            t = v[f'{std}_verdict']
            summary.setdefault(std, Counter())[t] += 1
    return {'results_file': str(results_path),
            'n_locked_cells_scored': len(verdicts),
            'verdict_counts':
                {std: dict(c) for std, c in summary.items()},
            'verdicts': verdicts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', default=str(DEFAULT_GOLD))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    ap.add_argument('--evaluate-results', default=None,
                    help='optional future model result file to score on the '
                         'locked cells (no selection beyond membership)')
    a = ap.parse_args()
    gold = load_w2_gold(a.gold)
    cases, errors, locked_arts = build_lock(gold)
    if errors:
        raise SystemExit('PRE-REGISTRATION LOCK FAILED:\n' + '\n'.join(errors))
    out = {
        'artifact': 'groundedreview_ev1_preregistration',
        'status': 'FROZEN - locked before any cross-model paid API call',
        'freeze_rule': 'membership is anchored by exact served_artifact_id; '
                       'expected decisions are asserted against the frozen '
                       'Wave-2.1 gold on every run. Cases must not be added, '
                       'removed or re-labelled after seeing E1 outputs.',
        'gold_sha256': gold['sha256'],
        'gold_version': gold['version'],
        'n_locked_cases': len(cases),
        'n_locked_artifacts': len(locked_arts),
        'n_locked_cells': len(cases) * 5,
        'case_groups': ['wrong_patch', 'partial_but_decisive',
                        'incomplete_good'],
        'deliberately_excluded': {
            'contradictory_fix_contradictory_692650aa4edbfaad':
                'shares the partial-but-decisive condition pattern but was '
                'not named in the pre-registration request; including it '
                'post-hoc is prohibited. Remains in the ordinary 110-cell '
                'aggregate metrics only.'},
        'case_analysis_statistical_status': {
            'kind': 'EXPLORATORY MECHANISM ANALYSIS, not confirmatory '
                    'inference',
            'independence': 'the 35 locked cells are NOT 35 independent '
                            'experimental samples: they are 7 artifacts '
                            '(drawn from 6 distinct issues) crossed with 5 '
                            'conditions on the SAME fixture; cells within an '
                            'artifact/issue share patch and evidence and are '
                            'correlated',
            'reporting_unit': 'report each MODEL x FIXTURE behaviour side by '
                              'side on the same exact artifact id (paired, '
                              'descriptive mechanism comparison); no '
                              'population-level p-value or generalisation '
                              'claim is made from these 7 cases',
            'anchoring': 'exact served_artifact_id, decided before any '
                         'cross-model output exists; no post-hoc typical-case '
                         'picking',
            'aggregates_live_elsewhere': 'population rates and clustered CIs '
                                         'come only from the full 110-cell '
                                         'analysis (ev1_paired), not from '
                                         'these cases'},
        'hypotheses': {
            'H1': 'Over-Abstention (HYPOTHESIS TO BE TESTED, not assumed): '
                  'a model returns NEED_EVIDENCE despite having a trusted '
                  'decisive failure / decisive accept evidence. The wave2.1 '
                  'baseline showed it; whether a new cross-provider model '
                  'reproduces it is an open empirical question.',
            'H2': 'Unsupported Rejection (HYPOTHESIS TO BE TESTED): a model '
                  'returns REJECT without a declared, applicable decisive '
                  'failure.',
            'H3': 'Verification-Decision Gap (candidate main thesis): tools '
                  'called / evidence obtained, yet the decision does not '
                  'reflect its verdict. H1 and H2 are two opposite failure '
                  'mechanisms under H3.',
            'attribution_discipline': 'mechanical scoring assigns the label '
                                      'that WOULD hold if the observed '
                                      'decision matches the pattern; it must '
                                      'not be narrated as proof that the new '
                                      'model exhibits the failure before its '
                                      'outputs are examined'},
        'cases': cases,
    }
    if a.evaluate_results:
        out['mechanical_evaluation'] = evaluate_results(
            a.evaluate_results, gold)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print(f'locked cases={len(cases)} cells={len(cases)*5} '
          f'artifacts={len(locked_arts)} gold_sha={gold["sha256"][:12]}')
    for cs in cases:
        print(f'  {cs["case_group"]:22s} {cs["scenario"]:24s} '
              f'{cs["served_artifact_id"][:46]:46s} '
              f'oracle={cs["oracle_gold"]}')
    if errors:
        print('ERRORS:', errors)
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()

