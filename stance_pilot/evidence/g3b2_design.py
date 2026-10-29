"""Gate 3-B.2 (task 12) — Gate 3-B.3 experiment DESIGN ONLY. NOT RUN.

G3-B.3 = "revised-protocol validation": re-run the SAME ten frozen issues
under the repaired, three-way-consistent g3b2 protocol to test whether the
behaviours previously attributed to model over-abstention persist once the
benchmark no longer serves a contradictory freshness conclusion and once T2A
actually communicates the institutional premises its gold assumed.

This module emits the design, control structure, reproducibility/randomness
plan, provisional-gold sensitivity analysis, estimated request counts and the
worst-case budget. It makes NO model call and authorises nothing; G3-B.3 needs
a separate written approval.
"""
from __future__ import annotations

import json

from evidence import g3b2_common as C

# Observed G3-B economics (frozen results), used only to estimate G3-B.3.
G3B_OBSERVED = {
    'total_cost_usd': 0.290658,
    'model_calls': 218,
    'tokens_in': 748085,
    'tokens_out': 34372,
    'cells': 100,
    'models': 2,
}
# Same hard caps as frozen G3-B (no cap increase requested).
TOTAL_HARD_CAP_USD = 3.00
PER_MODEL_CAP_USD = 1.50
COMPLETION_CAP = 8192
MAX_TOOL_TURNS = 8
# Vendor PEAK-list prices (frozen profiles).
PRICES = {
    'deepseek-flash': {'in': 0.30, 'out': 1.20},
    'gpt-4.1-mini': {'in': 0.40, 'out': 1.60},
}


def design():
    return {
        'document': ('Gate 3-B.3 revised-protocol validation — DESIGN ONLY. '
                     'Nothing here is an authorisation; requires separate '
                     'written approval. G3-B.2 produced this with $0.'),
        'status': 'DESIGN_NOT_RUN',
        'requires_separate_written_approval': True,
        'protocol_version_to_run': C.PROTOCOL_VERSION,
        'prompt_version_to_run': C.PROMPT_VERSION,
        'gold_cert_version_to_run': C.GOLD_CERT_VERSION,

        'research_question': (
            'Under a protocol whose Gold, model-visible evidence, prompt trust '
            'semantics and live tool surface are three-way consistent, do the '
            'G3-B behaviours persist: (a) DeepSeek high NEED/abstention rate '
            '(esp. T2A trust-granted and T3A/Escalate now truly fresh); '
            '(b) GPT evidence-verification failure on sympy-17318/T2A despite '
            'a visible FAIL_TO_PASS passed 0/1.'),

        'subjects_and_cells': {
            'issues': 10,
            'issues_source': 'the SAME frozen G3-A ten issues; NO new issue',
            'conditions': ['T2D-T', 'T2A-T', 'T3D-Strict',
                           'T3D-Escalate', 'T3A-T'],
            'real_models': ['deepseek-flash', 'gpt-4.1-mini'],
            'primary_cells': 100,
            'note': ('10 issues x 5 conditions x 2 models = 100 primary cells, '
                     'matching G3-B cell count for direct paired comparison.'),
        },

        'version_control': {
            'new_version_never_overwrites_g3b': True,
            'frozen_g3b_artifacts_read_only': True,
            'outputs_under': 'evidence_store_g3b3/ (new directory, not g3b2)',
            'prompt_fingerprints_locked_to': 'p3-ternary-g3b2-v1 hashes',
            'server_to_run': 'g3b2_server (repaired adjudicator), tempdir copy',
            'g3b2_modules_imported_not_edited': True,
            'no_change_to_gold_to_improve_model_scores': True,
        },

        'control_structure': {
            'paired_design': ('each (issue, condition, model) cell pairs '
                              'directly against its frozen G3-B cell (same '
                              'issue/patch/condition/model, only the repaired '
                              'protocol differs)'),
            'internal_controls': [
                'T2D-T and T3D-Strict are intentionally UNCHANGED restricted '
                'regimes (condition gold NEED for all ten): they control for '
                'drift unrelated to the repair; NEED there is gold-consistent.',
                'T3D-Escalate retains 400-without-reason then reason-gated 200; '
                'T3D-Strict retains hard 403 (gating must still hold).',
                'T3A-T retains full access; only the freshness verdict changes '
                '(false -> authoritative TRUE).',
            ],
            'change_attribution': ('the ONLY intended between-version changes '
                                   'are (i) T2A institutional grant text, (ii) '
                                   'authoritative three-state freshness; '
                                   'everything else frozen.'),
        },

        'randomness_and_retest': {
            'sampling': 'temperature 0 (frozen), deterministic where supported',
            'residual_nondeterminism': ('temperature-0 does not guarantee '
                                        'bit-identical vendor output; tools and '
                                        'interleaving are deterministic'),
            'interleaving': ('same cyclic Latin-shift scheme, NEW fixed seed '
                             'distinct from G3-B and g3b2 mock, recorded in the '
                             'G3-B.3 freeze'),
            'optional_reliability_substudy': {
                'included_by_default': False,
                'description': ('if approved, repeat each primary cell R extra '
                                'times (recommend R=2 => 3 total judgements per '
                                'cell) to estimate temperature-0 test-retest '
                                'agreement; reported separately from primary'),
                'extra_cells_if_enabled': 200,
                'decision': 'NOT funded by this design; opt-in only',
            },
            'primary_analysis': ('single primary judgement per cell; sign-flip '
                                 'rates vs G3-B reported per condition; no '
                                 'cherry-picking of retries'),
        },

        'provisional_gold_sensitivity': {
            'gold_tier': 'PROVISIONAL',
            'annotators': 1,
            'annotator2': 'NOT_OBTAINED',
            'rule': ('protocol repair does NOT raise gold authority; if no '
                     'second annotator is obtained, every G3-B.3 result stays '
                     'provisional and is reported as such'),
            'sensitivity_plan': [
                'primary scoring uses the 50 repaired certificates (0 value '
                'changes vs frozen g3a1 gold, 30 sufficient / 20 NEED).',
                'boundary analysis: flag any cell whose decision would change '
                'under the alternative assumption that the 3 acceptance-failure '
                'REJECT issues or the institutional-trust grant are not '
                'warranted; report conclusions both ways.',
                'no certificate is edited using observed model behaviour.',
            ],
        },

        'expected_real_requests': {
            'primary_model_calls_estimate': G3B_OBSERVED['model_calls'],
            'basis': ('G3-B observed 218 model calls over 100 cells (static '
                      'conditions 1 turn; active conditions multi-turn up to '
                      'the cap). g3b2 adds short prompt text, which changes '
                      'tokens, not the call count materially.'),
            'primary_http_tool_calls': 'deterministic, $0, not vendor calls',
            'with_optional_retest_r2': 218 * 3,
        },

        'budget': {
            'observed_g3b_cost_usd': G3B_OBSERVED['total_cost_usd'],
            'g3b3_primary_point_estimate_usd': round(
                G3B_OBSERVED['total_cost_usd'] * 1.10, 4),
            'point_estimate_basis': ('G3-B actual + ~10% for the added T2A '
                                     'grant / freshness-note tokens; repair '
                                     'changes wording, not call structure'),
            'per_model_hard_cap_usd': PER_MODEL_CAP_USD,
            'total_hard_cap_usd': TOTAL_HARD_CAP_USD,
            'worst_case_usd': TOTAL_HARD_CAP_USD,
            'worst_case_mechanism': ('BudgetGuard pre-call conservative bound '
                                     '(fresh full transcript resend each turn x '
                                     f'pin + completion cap {COMPLETION_CAP} x '
                                     'pout) refuses before any call that would '
                                     'breach the cap; per-cell call cap '
                                     f'{MAX_TOOL_TURNS}; so spend cannot exceed '
                                     'the hard cap'),
            'with_optional_retest_worst_case_usd':
                'would require a separately raised, separately approved cap; '
                'NOT requested here',
            'kill_switch': ('run only with an explicit ACK flag; no ACK -> '
                            'refused; total cap > hard cap -> refused; per-model '
                            'cap enforced independently'),
            'prices': PRICES,
        },

        'decision_interpretation_pre_registered': {
            'if_deepseek_need_drops_substantially': (
                'original C2 over-abstention was largely induced by the '
                'benchmark protocol (spurious fresh=false / unstated trust); '
                'the model-defect claim is weakened.'),
            'if_deepseek_need_remains_high_on_sufficient_truly_fresh_cells': (
                'stronger basis to study a calibration/decision-policy defect.'),
            'gpt_17318_t2a': ('continue to treat an ACCEPT despite visible '
                              'FAIL_TO_PASS passed 0/1 as a warranted Evidence '
                              'Verification Failure; repaired protocol keeps '
                              'that failure visible without leaking REJECT.'),
            '17630_t3a': ('separately tagged Decision-Policy probe; not pooled '
                          'with freshness-driven abstention.'),
        },

        'scope_limit_for_paper': (
            'This benchmark quality audit is NOT, by itself, a general finding '
            'about all code-review-agent benchmarks. Claiming Benchmark '
            'Reliability as a contribution would require additional '
            'cross-benchmark evidence.'),

        'deliverables_when_approved': [
            'g3b3 freeze manifest (new versions, seed, fingerprints)',
            '100 primary live result rows with BudgetGuard logs',
            'paired G3-B vs G3-B.3 sign-flip table per condition/model',
            'provisional-gold sensitivity + boundary analysis',
            'gate integrity evidence (403/400/200, freshness TRUE)',
        ],
    }


def main():
    d = design()
    C.OUT_DESIGN.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_DESIGN.write_text(
        json.dumps(d, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print('->', C.OUT_DESIGN)
    print('primary cells =', d['subjects_and_cells']['primary_cells'],
          '| est calls =',
          d['expected_real_requests']['primary_model_calls_estimate'],
          '| point $ =', d['budget']['g3b3_primary_point_estimate_usd'],
          '| worst $ =', d['budget']['worst_case_usd'])


if __name__ == '__main__':
    main()
