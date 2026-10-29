"""GroundedReview v2.1 Experiment X — PRE-CALL FREEZE builder (offline).

Builds the immutable freeze manifest for the 2x2 factorial experiment:
22 fixtures x 4 conditions (a0b0 / a1b0 / a0b1 / a1b1) x 2 models = 176
NEW paid calls. Every one of the four conditions is re-called in X; the
Gate-2 / R1 a0b0 observations are NOT borrowed as the X control (batch /
time / stochasticity confound protection).

The manifest records, before any paid call:
  * the 88 byte-frozen payloads (sha asserted against the v2.1 design
    manifest) expanded to 176 model-specific cells;
  * per-condition head/body/prompt fingerprints, system prompt and decision
    schema hashes, sampling parameters and scoring rubric;
  * the frozen shared statistics implementation (evidence/eal_stats.py) and
    the estimand policy (PRIMARY = issue-equal-weighted; cell-weighted always
    reported alongside, never mixed in one column);
  * the pre-registered effect formulas dA / dB / dAB;
  * the precomputed per-cell operand-contradiction fact table and the frozen
    reason-coding lexicon + two-pass blinded procedure (G2.5 standard);
  * the deterministic, pre-frozen INTERLEAVED call order (176 entries);
  * code hashes (runner / stats / this builder) and the budget contract
    (TOTAL hard cap $1.50 across both models, zero retries).

$0 network. Writes only evidence_store_eal/v21x/.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence import eal_protocol as eal
from evidence import cee_protocol_v11 as cee
from evidence.eal_run import PROFILES, _sha
from evidence.eal_v21_design import (CONDITIONS, V21_VERSION,
                                     contradiction_facts)

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
V21_DIR = EAL_DIR / 'v21'
V21_LAYERS = V21_DIR / 'layers'
DESIGN_MANIFEST = V21_DIR / 'eal_v21_design_manifest.json'
V21_FREEZE = V21_DIR / 'eal_v21_freeze_manifest.json'

X_DIR = EAL_DIR / 'v21x'
X_FREEZE = X_DIR / 'eal_v21x_freeze_manifest.json'
X_PREFLIGHT = X_DIR / 'eal_v21x_preflight.json'

GATE = 'v21x_live'
ACK = '--i-acknowledge-x-approved-2026-10-25'
TOTAL_BUDGET_USD = 1.50
PER_MODEL_CAP_USD = 0.75
COMPLETION_CAP = 4096
MODELS = ('deepseek-flash', 'gpt-4.1-mini')
LAYER = 'structured'  # X manipulates the STRUCTURED layer only.
ORDER_SEED = 7

# Pre-registered factorial effects (Y_ab = DA at A=a, B=b), paired on the
# same fixtures, issue-cluster bootstrap (instance_id, seed 7, n 10000).
EFFECT_FORMULAS = {
    'dA': '((Y10-Y00)+(Y11-Y01))/2',
    'dB': '((Y01-Y00)+(Y11-Y10))/2',
    'dAB': 'Y11-Y10-Y01+Y00',
    'note': 'each Y_ab is computed on the SAME 22 frozen fixtures; deltas '
            'are paired per fixture, aggregated within issue cluster before '
            'any contrast; bootstrap resamples the 10 issue clusters.'}

ESTIMAND_POLICY = {
    'primary': 'issue',
    'report': ['issue', 'cell'],
    'issue_equal_weighted': 'mean of the 10 within-issue means; each '
        'independent issue counts once regardless of mirror count',
    'cell_weighted': 'mean over all scored cells; mirrors/layers weight by '
        'cell count',
    'no_mixing_rule': 'a point estimate and its CI always use the same '
        'estimand; cell-weighted levels are never placed beside an '
        'issue-weighted delta in one column (the R1 0.591/0.591/+0.022 '
        'mixing is corrected in evidence/eal_stats.py)',
    'bootstrap': {'unit': 'instance_id', 'n_clusters': 10, 'seed': 7,
                  'n_boot': 10000,
                  'type': 'paired percentile over resampled clusters'},
    'gate2_reconciliation': 'Gate-2 CIs were cell-weighted (it resampled '
        'clusters but pooled cells); R1 CIs were issue-equal-weighted; X '
        'reports BOTH and labels the issue-equal column primary. Gate-2 and '
        'R1 CIs are therefore not directly compared across estimands.'}

# ---------------------------------------------------------------------------
# Frozen reason-coding rubric (Evidence Verification Failure marker).
# Operand facts are precomputed mechanically; the reason lexicon and the
# two-pass blinded procedure are frozen BEFORE seeing any X response.
# ---------------------------------------------------------------------------
REASON_CODING = {
    'standard': 'GroundedReview G2.5 contradiction standard: a cell is '
        'coded contradictory when its reason AFFIRMATIVELY asserts a '
        'verification property whose served operands directly contradict '
        'it. Coded from reason_verbatim only, joined to the per-bundle '
        'operand fact table; the model decision is not consulted.',
    'properties': {
        'P1_identity_match': {
            'asserts': 'TARGET.base_commit / patch_sha256 match the run '
                       'record (linkage / identity operands match)',
            'lexicon': ['identity operands match', 'identity matches',
                        'base commit matches', 'patch sha matches',
                        'patch hash matches', 'matches the target',
                        'linked to the target', 'linked to the current',
                        'correctly linked', 'identity is consistent',
                        'linked to this patch'],
            'operand_flag': 'p1_identity_contradictable'},
        'P2_freshness': {
            'asserts': 'the run tree matches the attested expected tree '
                       '(fresh for the current commit)',
            'lexicon': ['run tree matches', 'run-tree matches',
                        'expected run tree matches', 'attestation matches',
                        'tree matches the attestation', 'is fresh',
                        'are fresh', 'fresh for the current',
                        'fresh run', 'current commit tree'],
            'operand_flag': 'p2_runtree_contradictable'},
        'P3_coverage_complete': {
            'asserts': 'all declared acceptance/regression tests were '
                       'executed (coverage complete)',
            'lexicon': ['all declared tests', 'all acceptance tests',
                        'all regression tests', 'all the declared',
                        'every declared test', 'coverage is complete',
                        'coverage complete', 'fully covered',
                        'complete coverage', 'all listed tests',
                        'all scoped tests ran', 'tests were all run',
                        'all tests were executed'],
            'operand_flag': 'p3_coverage_contradictable'},
        'P4_all_checks_pass': {
            'asserts': 'the executed checks all pass / no failures or '
                       'regressions',
            'lexicon': ['all tests pass', 'all checks pass',
                        'all checks passed', 'tests pass fully',
                        'tests passed fully', 'no failures',
                        'no regressions', 'no acceptance failures',
                        'no test failures', 'all green', 'fully passing',
                        'all pass'],
            'operand_flag': 'p4_f2p_failed_contradictable'}},
    'p3_p4_relation': 'P3 concerns MISSING declared tests (absent_post); P4 '
        'concerns an EXECUTED f2p that FAILED. c637f604 coverage is the '
        'frozen special case: its +coverage is p4 (executed f2p FAILED), '
        'not p3 (absent declared).',
    'affirmative_rule': 'only AFFIRMATIVE assertions count; exclude a '
        'lexicon hit that is negated or hedged in the same clause '
        '("do not pass", "not fresh", "uncertain whether ... matches").',
    'two_pass': {
        'pass1_auto': 'case-insensitive lexicon scan of reason_verbatim '
                      'produces candidate (cell, property) flags, blinded '
                      'to parsed decision and gold',
        'pass2_adjudication': 'author confirms each candidate is a genuine '
                      'affirmative operand assertion (applies the negation '
                      'rule); auto and adjudicated flags plus their '
                      'agreement are both reported',
        'denominator': 'parseable responses per condition (INVALID / '
                       'AMBIGUOUS / API_ERROR listed separately)'},
    'prereg8': {
        '62dfb1c6': 'freshness', '2c11095a': 'freshness',
        'e4e8b26c': 'freshness', 'c637f604': 'freshness+coverage(p4)',
        'ec813709': 'coverage', 'a25d0cf5': 'coverage',
        '403163cb': 'coverage', 'c59a8ceb': 'linkage+freshness'},
}


def load_design():
    man = json.loads(DESIGN_MANIFEST.read_text(encoding='utf-8'))
    if man['n_items'] != 22 or man['n_conditions'] != 4:
        raise SystemExit('v2.1 design manifest shape drift')
    if set(man['conditions']) != set(CONDITIONS):
        raise SystemExit('v2.1 condition set drift')
    if set(man['items'][0]['conditions']) != set(CONDITIONS):
        raise SystemExit('v2.1 item condition set drift')
    return man


def build_cells(man):
    """88 byte-asserted payloads -> 176 model cells."""
    cells = []
    for it in man['items']:
        for cond in CONDITIONS:
            meta = it['conditions'][cond]
            p = V21_LAYERS / f"{meta['payload_id']}.txt"
            b = p.read_bytes()
            if _sha(b) != meta['sha256']:
                raise SystemExit(
                    f"X payload drift vs v2.1 design: {meta['payload_id']}")
            for model in MODELS:
                cells.append({
                    'model_profile': model,
                    'bundle_id': it['bundle_id'], 'condition': cond,
                    'layer': LAYER, 'instance_id': it['instance_id'],
                    'id': it['id'], 'cee_gold': it['cee_gold'],
                    'evidence_class': it['evidence_class'],
                    'layer_gold_determined':
                        bool(it['layer_gold_determined']),
                    'underdetermined_channels':
                        it['underdetermined_channels'],
                    'payload_id': meta['payload_id'],
                    'payload_sha256': meta['sha256'],
                    'payload_bytes': len(b),
                    'head_sha256': meta['head_sha256'],
                    'body_sha256': meta['body_sha256'],
                    'prompt_fingerprint':
                        meta['prompt_fingerprint_v21']})
    if len(cells) != 176:
        raise SystemExit(f'expected 176 X cells, got {len(cells)}')
    return cells


def interleaved_order(man):
    """Deterministic pre-frozen serial order over 176 calls.

    Within each fixture block the 8 (model x condition) combos follow a base
    alternating sequence, and the block's start rotates by one slot per
    fixture (cyclic Latin shift). Models and conditions therefore alternate
    across serial position; every combo occupies every within-block slot
    roughly equally (22 blocks over 8 slots), so neither model, condition,
    fixture nor a time/batch trend is confounded with a factor."""
    base = [('deepseek-flash', 'a0b0'), ('gpt-4.1-mini', 'a0b1'),
            ('deepseek-flash', 'a1b0'), ('gpt-4.1-mini', 'a1b1'),
            ('gpt-4.1-mini', 'a0b0'), ('deepseek-flash', 'a0b1'),
            ('gpt-4.1-mini', 'a1b0'), ('deepseek-flash', 'a1b1')]
    order = []
    for f, it in enumerate(man['items']):
        block = base[f % len(base):] + base[:f % len(base)]
        for model, cond in block:
            order.append({'serial': len(order),
                          'model_profile': model,
                          'bundle_id': it['bundle_id'],
                          'instance_id': it['instance_id'],
                          'condition': cond,
                          'payload_id': f"{it['bundle_id']}__{cond}"})
    if len(order) != 176:
        raise SystemExit('order length drift')
    # balance self-check: each (model,cond) appears exactly 22 times.
    from collections import Counter
    cnt = Counter((o['model_profile'], o['condition']) for o in order)
    if set(cnt.values()) != {22} or len(cnt) != 8:
        raise SystemExit(f'order balance broken: {cnt}')
    return order


def _code_file_sha(name):
    p = ROOT / 'evidence' / name
    return _sha(p.read_bytes()) if p.exists() else None


def build_x_freeze():
    man = load_design()
    cells = build_cells(man)
    order = interleaved_order(man)
    operand_facts, fact_bad = contradiction_facts(man['items'])
    if fact_bad:
        raise SystemExit(f'operand fact table fails G2.5 validation: '
                         f'{fact_bad}')

    # condition-level fingerprint sets (identical across fixtures per factor)
    cond_fp = {}
    for cond in CONDITIONS:
        heads = {c['head_sha256'] for c in cells if c['condition'] == cond}
        bodies = {c['body_sha256'] for c in cells if c['condition'] == cond}
        pfs = {c['prompt_fingerprint'] for c in cells
               if c['condition'] == cond}
        cond_fp[cond] = {'n_distinct_head_sha': len(heads),
                         'n_distinct_body_sha': len(bodies),
                         'n_distinct_prompt_fingerprints': len(pfs)}

    freeze = {
        'document': 'GroundedReview v2.1 Experiment X pre-call freeze '
                    '(2x2 factorial, 22 fixtures x 4 conditions x 2 models)',
        'gate': GATE,
        'created_before_any_paid_call': True,
        'approval': 'conditional written approval 2026-10-25; paid execution '
                    'requires this freeze + preflight + offline mock to pass',
        'v21_version': V21_VERSION,
        'eal_protocol_version': eal.EAL_PROTOCOL_VERSION,
        'n_new_paid_calls': 176,
        'n_fixtures': 22, 'n_conditions': 4, 'n_models': 2,
        'layer': LAYER,
        'all_four_conditions_recalled': True,
        'no_borrowed_control': 'A0B0 is re-called fresh in X for both '
                               'models; Gate-2/R1 a0b0 rows are never reused '
                               'as the X control',
        'conditions': list(CONDITIONS),
        'condition_design': {
            'a0b0': 'original structured + original rule',
            'a1b0': 'verification assistance (TABLE 0 counts) + original rule',
            'a0b1': 'original structured + policy reminder',
            'a1b1': 'verification assistance + policy reminder'},
        'factor_a_spec': man.get('factor_a_spec'),
        'factor_b_spec': man.get('factor_b_spec'),
        'condition_fingerprint_sets': cond_fp,
        'condition_prompt_fingerprints':
            man.get('condition_prompt_fingerprints'),
        'v21_design_manifest_sha256': _sha(DESIGN_MANIFEST.read_bytes()),
        'v21_freeze_manifest_sha256': _sha(V21_FREEZE.read_bytes()),
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'decision_schema_sha256': _sha(
            json.dumps(eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'sampling': {'temperature': 0, 'max_tokens': COMPLETION_CAP,
                     'response_format': dict(cee.RESPONSE_FORMAT_JSON_OBJECT),
                     'tools': 0, 'turns': 1, 'retries_per_cell': 0},
        'models': {m: {'requested': PROFILES[m]['model'],
                       'expected_served_model_id':
                           PROFILES[m]['e1_served_model_id'],
                       'price_in_usd_per_mtok': PROFILES[m]['price_in'],
                       'price_out_usd_per_mtok': PROFILES[m]['price_out']}
                   for m in MODELS},
        'budget': {'total_hard_cap_usd': TOTAL_BUDGET_USD,
                   'per_model_cap_usd': PER_MODEL_CAP_USD,
                   'total_is_across_both_models': True,
                   'guard': 'pre-call BudgetGuard per request; global cap '
                            'checked before every send; resume restores '
                            'cumulative spend'},
        'retries': 'zero retries: wrong / INVALID / AMBIGUOUS / transport '
                   'fault are terminal rows; no call is repeated',
        'effect_formulas': EFFECT_FORMULAS,
        'estimand_policy': ESTIMAND_POLICY,
        'scoring_prereg': {
            'primary_sample': 'all 22 fixtures; the 8 G2.5 cases are a '
                              'pre-registered DIAGNOSTIC subset only',
            'gold_distribution': {'ACCEPT': 7, 'REJECT': 6,
                                  'NEED_EVIDENCE': 9},
            'error_families': ['unsupported_acceptance',
                               'unsupported_rejection',
                               'over_abstention'],
            'causal_claim_limit': 'behavioural-level Verification Assistance '
                '/ Policy Salience interpretation only; factor effects are '
                'not asserted to identify an internal causal mechanism'},
        'reason_coding': REASON_CODING,
        'operand_facts_by_bundle8': operand_facts,
        'chronic_oscillation_cells': ['59e46a77', 'ec813709'],
        'call_order_seed': ORDER_SEED,
        'call_order': order,
        'cells': cells,
        'code_hashes': {
            'eal_stats_py': _code_file_sha('eal_stats.py'),
            'eal_v21x_freeze_py': _code_file_sha('eal_v21x_freeze.py'),
            'eal_v21x_run_py': _code_file_sha('eal_v21x_run.py'),
            'eal_v21x_analyze_py':
                _code_file_sha('eal_v21x_analyze.py')},
        'exclusions': 'R2, Gate-3 expansion, Gemini / other models, new '
                      'issues, and git commits are NOT part of X'}
    return freeze


def write_freeze():
    X_DIR.mkdir(parents=True, exist_ok=True)
    freeze = build_x_freeze()
    X_FREEZE.write_bytes(
        (json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True)
         + '\n').encode('utf-8'))
    return freeze


def canonical_bytes(freeze):
    return (json.dumps(freeze, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def main():
    freeze = write_freeze()
    print(f'X freeze written: {len(freeze["cells"])} cells, '
          f'{len(freeze["call_order"])} ordered calls -> {X_FREEZE}')
    print('sha256', _sha(X_FREEZE.read_bytes()))


if __name__ == '__main__':
    main()
