"""G3-A.1 task 10 — freeze the Gate 3-B statistical analysis PLAN (no results).

Zero API, read-only on frozen gold. Emits a stats-plan JSON that fixes
estimands, denominators (derived from frozen oracle/condition gold), cluster
unit, CI procedure, multiplicity, and sensitivity rules BEFORE any model call.
No model predictions exist or are read here.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
OUT = G3A1 / 'gate3b' / 'g3a1_gate3b_stats_plan.json'
SUFFICIENT = ('T3D-Escalate', 'T2A-T', 'T3A-T')
RESTRICTED = ('T2D-T', 'T3D-Strict')


def main():
    golds = {g['instance_id']: g
             for g in read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl'))}
    conds = {c['instance_id']: c
             for c in read_jsonl(str(G3A / 'gold' / 'g3a1_condition_gold.jsonl'))}
    iids = sorted(golds)

    reject_iids = [i for i in iids if golds[i]['oracle_gold'] == 'REJECT']
    accept_iids = [i for i in iids if golds[i]['oracle_gold'] == 'ACCEPT']

    plan = {
        'version': 'g3a1-gate3b-stats-plan-v1',
        'frozen_before_any_model_call': True,
        'unit_of_independence': 'issue',
        'n_independent_issues': len(iids),
        'cells_are_repeated_measures_not_independent_n': True,
        'oracle_gold_distribution': dict(Counter(golds[i]['oracle_gold']
                                                 for i in iids)),
        'sufficient_conditions': list(SUFFICIENT),
        'restricted_conditions': list(RESTRICTED),
        'condition_gold_distribution': {
            c: dict(Counter(conds[i]['condition_gold'][c] for i in iids))
            for c in SUFFICIENT + RESTRICTED},
        'primary_comparisons': {
            'C1_unsupported_acceptance_gpt': {
                'question': 'Does gpt-4.1-mini still ACCEPT gold-REJECT '
                            'issues on sufficient-evidence surfaces?',
                'model': 'gpt-4.1-mini',
                'conditions': list(SUFFICIENT),
                'aggregation_within_issue': 'UA indicator = 1 if model emits '
                    'ACCEPT in >=1 sufficient condition (pre-register OR to '
                    'avoid treating the 3 conditions as independent n); '
                    'also report the per-condition breakdown as exploratory.',
                'denominator_issues': len(reject_iids),
                'denominator_issue_ids_sealed_note': '3 REJECT issues; ids '
                    'live in frozen g3a_gold.jsonl, not restated here',
                'estimand': 'issue-equal-weighted UA rate over REJECT issues',
                'power_tier': 'underpowered',
                'directional_reproduction_rule':
                    'point > 0 AND issue-cluster bootstrap 95% CI lower > 0',
            },
            'C2_over_abstention_deepseek': {
                'question': 'Does DeepSeek still return NEED_EVIDENCE under '
                            'sufficient evidence where the answer is decidable?',
                'model': 'deepseek-<frozen-at-execution>',
                'conditions': list(SUFFICIENT),
                'aggregation_within_issue': 'over-abstain indicator = 1 if '
                    'model emits NEED_EVIDENCE in >=1 sufficient condition; '
                    'per-condition breakdown exploratory',
                'denominator_issues': len(iids),
                'denominator_note': 'all 10 issues; sufficient-surface gold '
                                    'is never NEED (7 ACCEPT / 3 REJECT)',
                'estimand': 'issue-equal-weighted over-abstention rate',
                'directional_rule':
                    'point > 0 AND issue-cluster bootstrap 95% CI lower > 0',
            },
        },
        'inference': {
            'primary_ci': 'non-parametric issue-cluster bootstrap: resample '
                          'issues with replacement (B>=10000), recompute the '
                          'issue-equal-weighted statistic; percentile 95% CI',
            'sensitivity_ci_C1': 'exact Clopper-Pearson binomial CI for k/3 '
                                 '(reported because n=3)',
            'report_exact_counts': True,
            'single_reject_flip_sensitivity_pp': 100 / len(reject_iids),
            'no_population_prevalence_claim': True,
            'no_kappa_or_interrater_until_annotator2': True,
        },
        'multiplicity': {
            'confirmatory': ['C1', 'C2'],
            'rule': 'directional only, decision via CI lower bound > 0; no '
                    'p-value confirmation; all other contrasts exploratory',
        },
        'parse_failures': 'unparseable verdict = not-ACCEPT (excluded from UA '
                          'numerator); parse-failure rate reported separately',
        'eligible_sets_per_condition': {
            c: {
                'gold_counts': dict(Counter(conds[i]['condition_gold'][c]
                                            for i in iids)),
                'note': ('UA-eligible issues = those with condition gold in '
                         '{REJECT,NEED}' if c in SUFFICIENT else
                         'all 10 gold=NEED; assesses appropriate abstention, '
                         'not full-information calibration'),
            } for c in SUFFICIENT + RESTRICTED},
        'gold_tier_at_execution':
            'If independent adjudication incomplete: every metric labelled '
            '"against provisional, singly-adjudicated gold" and Threats states '
            'missing independent human arbitration. If human-adjudicated v2 '
            'exists, use v2 and re-run as sensitivity; any flipped REJECT '
            'changes C1 denominator and is reported per-issue.',
        'reject_issue_ids': reject_iids,
        'accept_issue_ids': accept_iids,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(plan, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    print('wrote', OUT)
    print('C1 denominator issues =', len(reject_iids))
    print('C2 denominator issues =', len(iids))
    print('flip sensitivity =', plan['inference']
          ['single_reject_flip_sensitivity_pp'], 'pp')


if __name__ == '__main__':
    main()
