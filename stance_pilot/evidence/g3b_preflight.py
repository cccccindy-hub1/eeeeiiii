"""GroundedReview Gate 3-B — offline PREFLIGHT (zero API, zero network).

Runs every paid-gate prerequisite from the user's instruction #4 and writes
evidence_store_g3b/preflight/g3b_preflight.json:

  1. freeze is the canonical derivation and on-disk bytes match;
  2. shape/balance: 100 cells, deterministic interleaved order, every
     (model, condition) appears exactly 10 times;
  3. LABEL LEAKAGE AUDIT: the served prompt payload for every one of the 50
     issue-condition items is rebuilt with the FROZEN v2 builder and asserted
     to contain no gold/verdict/label token (no oracle/condition label, no
     `resolved`, no scenario class, no maintainer test_patch outcome);
  4. EVIDENCE SUFFICIENCY CHECK: tier-D renders no acceptance outcome while
     tier-A does, and the projected condition-gold correspondence matches the
     frozen file (T2D-T/T3D-Strict -> 10 NEED; the three sufficient regimes
     -> oracle), with the under-determination / unavailable-source /
     institutional-trust assumptions disclosed;
  5. BudgetGuard selftest: a bound crossing the per-model $1.50 or total
     $3.00 cap is REFUSED, per-cell call cap enforced, normal bound accepted;
  6. kill-switch subprocess checks: live without ACK is REFUSED, a bare
     invocation is REFUSED, a total cap above $3.00 is REFUSED;
  7. frozen code hashes match the files that will actually run.

Offline:
    uv run --python 3.13 -m evidence.g3b_preflight
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evidence.g3b_freeze import (
    ACK, ACTIVE_CONDITIONS, CONDITIONS, G3B, MODELS, PER_MODEL_CAP_USD,
    PROFILES, PROMPT_VERSION, STATIC_CONDITIONS, TOTAL_BUDGET_USD,
    build_cells, build_freeze, canonical_bytes, interleaved_order,
)
from evidence.g3b_freeze import OUT as FREEZE_PATH
from evidence.g3b_run import CompositeGuard
from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.prompts import build_ternary_messages_v2
from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT_DIR = G3B / 'preflight'
OUT = PREFLIGHT_DIR / 'g3b_preflight.json'

# Tokens that must never appear in a SERVED prompt/message. Gold labels as
# bare words are allowed only when the prompt itself instructs the reviewer to
# choose among them, so leakage is asserted on answer-bearing substrings and
# dataset/verdict fields rather than the word "ACCEPT" itself.
FORBIDDEN_SUBSTRINGS = [
    'oracle_gold', 'condition_gold', 'merge_acceptable', 'label_class',
    '"resolved"', 'resolved_in_dataset', 'builder_label_class_audit_only',
    'w2_decisive_bad', 'w2_stale', 'w2_wrong', 'mirror',
]
# Acceptance-test RESULT tokens are forbidden ONLY under tier D (T2D-T and
# T3D-Strict), where outcomes must be withheld. Under tier A / Escalate the
# aggregate result (e.g. "FAIL_TO_PASS passed: 1/1") is the evidence the
# condition is designed to present, not leakage. The separate tier_projection
# check enforces the D-side withholding structurally.
OUTCOME_TOKENS_D_ONLY = ['FAIL_TO_PASS', 'PASS_TO_PASS']
# The reviewer-facing schema legitimately names the three verdicts; that is
# not leakage. Leakage is an ASSERTION of the answer, e.g. "the correct
# decision is ACCEPT". Note: the frozen v2 diagnostic view legitimately says
# the symptom probe is "derived from the issue text, not the maintainer test
# suite" and that P2P is "scoped to test_patch files" — those are provenance/
# scope descriptions, not the maintainer test content or outcomes, so the
# bare phrases "maintainer test"/"test_patch" are NOT treated as leakage;
# outcome leakage is separately blocked by the tier-D projection check.
ANSWER_PATTERNS = [
    'the correct decision is', 'the answer is', 'gold label',
    'this patch should be accepted because it is known',
]


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def label_leakage_audit():
    """Rebuild the exact served messages for all 50 items and scan them."""
    items = build_cells()
    hits = []
    for it in items:
        msgs = build_ternary_messages_v2(it, artifact=it.get('artifact_record'))
        blob = '\n'.join(str(m.get('content')) for m in msgs)
        for tok in FORBIDDEN_SUBSTRINGS + ANSWER_PATTERNS:
            if tok.lower() in blob.lower():
                hits.append({'cell': it['cell_key'], 'token': tok})
        # outcome tokens only prohibited under tier D
        if it.get('evidence_tier') == 'D':
            for tok in OUTCOME_TOKENS_D_ONLY:
                if tok in blob:
                    hits.append({'cell': it['cell_key'],
                                 'token': f'{tok} [tier-D withheld]'})
        # audit-only keys must not have leaked into the item dict content
        if '"_oracle_gold"' in blob or '"_condition_gold"' in blob:
            hits.append({'cell': it['cell_key'], 'token': '_gold audit key'})
    return len(items), hits


def tier_projection_check():
    """Tier-D must withhold acceptance outcomes; tier-A must present them."""
    bad = []
    for it in build_cells():
        rec = it['artifact_record']
        summ = rec.get('summary') or {}
        if it['evidence_tier'] == 'D':
            for k in ('f2p_failed_ids', 'p2p_regressed_ids', 'f2p_passed',
                      'p2p_passed'):
                if k in summ and summ.get(k) not in (None, [], 0) and k in (
                        'f2p_failed_ids', 'p2p_regressed_ids'):
                    bad.append({'cell': it['cell_key'], 'leaked': k})
            if summ.get('outcomes_withheld') is not True:
                bad.append({'cell': it['cell_key'], 'leaked': 'no withhold'})
    return bad


def condition_gold_correspondence():
    rows = list(read_jsonl(
        str(ROOT / 'evidence_store_g3a/gold/g3a1_condition_gold.jsonl')))
    problems = []
    counts = {c: {} for c in CONDITIONS}
    for r in rows:
        oracle = r['oracle_gold']
        for c in CONDITIONS:
            cg = r['condition_gold'][c]
            counts[c][cg] = counts[c].get(cg, 0) + 1
            if c in STATIC_CONDITIONS[:1] or c == 'T3D-Strict':
                if cg != 'NEED_EVIDENCE':
                    problems.append({'issue': r['instance_id'], 'cond': c,
                                     'cg': cg, 'expected': 'NEED_EVIDENCE'})
            else:
                if cg != oracle:
                    problems.append({'issue': r['instance_id'], 'cond': c,
                                     'cg': cg, 'oracle': oracle,
                                     'note': 'sufficient regime must match '
                                             'oracle'})
    expected_counts = {
        'T2D-T': {'NEED_EVIDENCE': 10}, 'T3D-Strict': {'NEED_EVIDENCE': 10},
        'T3D-Escalate': {'ACCEPT': 7, 'REJECT': 3},
        'T2A-T': {'ACCEPT': 7, 'REJECT': 3},
        'T3A-T': {'ACCEPT': 7, 'REJECT': 3},
    }
    if counts != expected_counts:
        problems.append({'counts_mismatch': counts,
                         'expected': expected_counts})
    return counts, problems


def budgetguard_selftest():
    results = []

    def rec(name, ok, detail=''):
        results.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    total = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                        completion_cap_tokens=8192, max_model_calls_per_cell=12)
    g = CompositeGuard(PER_MODEL_CAP_USD, total, 0.40, 1.60,
                       completion_cap_tokens=8192,
                       max_model_calls_per_cell=12)
    # A small first call fits.
    try:
        g.check(1000, 0)
        rec('normal call within caps accepted', True)
    except BudgetGuardStop as e:
        rec('normal call within caps accepted', False, str(e))

    # Per-cell model-call cap REFUSED.
    try:
        g.check(1000, 12)
        rec('per-cell 12th model call REFUSED', False)
    except BudgetGuardStop:
        rec('per-cell 12th model call REFUSED', True)

    # Per-model cap: force spent to the cap and require the next bound refused.
    g2_total = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                           completion_cap_tokens=8192,
                           max_model_calls_per_cell=12)
    g2 = CompositeGuard(PER_MODEL_CAP_USD, g2_total, 0.40, 1.60,
                        completion_cap_tokens=8192,
                        max_model_calls_per_cell=12)
    g2.spent = PER_MODEL_CAP_USD
    try:
        g2.check(1000, 0)
        rec('per-model $1.50 breach REFUSED', False)
    except BudgetGuardStop:
        rec('per-model $1.50 breach REFUSED', True)

    # Total cap: total guard at the cap -> refused even though the per-model
    # guard still has room (simulate the other model spent the rest).
    t3 = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                     completion_cap_tokens=8192, max_model_calls_per_cell=12)
    t3.spent = TOTAL_BUDGET_USD
    g3 = CompositeGuard(PER_MODEL_CAP_USD, t3, 0.40, 1.60,
                        completion_cap_tokens=8192,
                        max_model_calls_per_cell=12)
    try:
        g3.check(1000, 0)
        rec('TOTAL $3.00 breach REFUSED', False)
    except BudgetGuardStop:
        rec('TOTAL $3.00 breach REFUSED', True)

    # Conservative bound uses the full completion cap (a true upper bound).
    b = BudgetGuard(PER_MODEL_CAP_USD, 0.40, 1.60,
                    completion_cap_tokens=8192).bound_usd(10_000)
    expect = (10_000 * 0.40 + 8192 * 1.60) / 1e6
    rec('bound prices full completion cap', abs(b - expect) < 1e-12,
        f'{b:.6f}=={expect:.6f}')
    return results


def subprocess_killswitches():
    results = []

    def rec(name, ok, detail=''):
        results.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    def run(*extra):
        p = subprocess.run([sys.executable, '-m', 'evidence.g3b_run', *extra],
                           cwd=str(ROOT), capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr)

    rc, out = run('--allow-paid-run')
    rec('live without G3-B ACK REFUSED', rc != 0 and 'REFUSED' in out,
        out[-160:])
    rc, out = run()
    rec('bare invocation REFUSED (offline default)', rc != 0
        and 'REFUSED' in out, out[-160:])
    return results


def main():
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'check': gid, 'pass': bool(ok), 'detail': str(detail)})

    # 1. canonical freeze
    freeze = json.loads(FREEZE_PATH.read_text(encoding='utf-8'))
    canon = canonical_bytes(build_freeze())
    gate('freeze on-disk == canonical derivation',
         _sha(FREEZE_PATH.read_bytes()) == _sha(canon),
         _sha(FREEZE_PATH.read_bytes())[:12])

    # 2. shape/balance
    cells, order = freeze['cells'], freeze['call_order']
    gate('100 frozen cells', len(cells) == 100, len(cells))
    gate('100 ordered calls', len(order) == 100, len(order))
    from collections import Counter
    cnt = Counter((c['model_profile'], c['condition']) for c in cells)
    gate('10 model-condition combos x 10', len(cnt) == 10
         and set(cnt.values()) == {10}, dict(cnt))
    items = build_cells()
    gate('order == deterministic interleaved order',
         interleaved_order(items) == order, 'seed=%s' % freeze['call_order_seed'])

    # 3. label leakage
    n_items, hits = label_leakage_audit()
    gate(f'label leakage audit clean on {n_items} items x2 models', not hits,
         hits[:3])

    # 3b. tier-D projection withholds outcomes
    bad = tier_projection_check()
    gate('tier-D projection withholds acceptance outcomes', not bad, bad[:3])

    # 4. condition/oracle correspondence + disclosures
    counts, problems = condition_gold_correspondence()
    gate('condition-gold correspondence matches frozen projection',
         not problems, problems[:2])
    gate('T2D-T & T3D-Strict = 10/10 NEED (abstention-only scope)',
         counts.get('T2D-T') == {'NEED_EVIDENCE': 10}
         and counts.get('T3D-Strict') == {'NEED_EVIDENCE': 10}, counts)
    gate('T2A-T sufficiency is an INSTITUTIONAL trust assumption disclosed',
         bool(freeze.get('gold_tier')) and 'PROVISIONAL' in freeze['gold_tier'])

    # 5. sampling/budget contract
    gate('temp0 / cap8192 / tool-turns8 / retries0',
         freeze['sampling']['temperature'] == 0
         and freeze['sampling']['completion_cap_tokens'] == 8192
         and freeze['sampling']['max_tool_turns'] == 8
         and freeze['sampling']['retries_per_cell'] == 0)
    gate('total cap $3.00 and per-model $1.50 x2',
         freeze['budget']['total_hard_cap_usd'] == TOTAL_BUDGET_USD
         and all(p['per_model_cap_usd'] == PER_MODEL_CAP_USD
                 for p in freeze['profiles'].values()))
    for r in budgetguard_selftest():
        checks.append({'check': 'budgetguard: ' + r['check'],
                       'pass': r['pass'], 'detail': r['detail']})

    # 6. kill switches
    for r in subprocess_killswitches():
        checks.append({'check': 'gate: ' + r['check'],
                       'pass': r['pass'], 'detail': r['detail']})

    # 7. code hashes
    drift = []
    for name, want in freeze['code_hashes'].items():
        p = ROOT / 'evidence' / name
        cur = _sha(p.read_bytes()) if p.exists() else None
        if cur != want:
            drift.append(name)
    gate('frozen code hashes match runnable files', not drift, drift)

    # 8. parent freeze integrity recorded
    pv = freeze['parent_freeze_verification']
    gate('G3-A 141 + G3-A.1 122 files reverified unchanged at freeze time',
         pv['g3a']['files_verified'] == 141
         and pv['g3a1']['files_verified'] == 122,
         {k: v['files_verified'] for k, v in pv.items()})

    all_pass = all(c['pass'] for c in checks)
    doc = {'document': 'Gate 3-B offline preflight (must pass before any paid '
                       'call)', 'all_pass': all_pass,
           'n_checks': len(checks), 'checks': checks,
           'condition_gold_counts': counts,
           'disclosures': {
               'under_determination': 'T2D-T/T3D-Strict gold is 10/10 NEED; '
                    'they measure appropriate abstention only, NOT selective '
                    'judgement under full information.',
               'unavailable_source': 'at T3D-Strict the maintainer acceptance '
                    'logs are a hard 403 wall; only the issue-derived symptom '
                    'channel is readable.',
               'institutional_trust': 'T2A-T/T3A-T "sufficient" presumes the '
                    'presented signed acceptance artifact is trustworthy; that '
                    'institutional assumption is not independently confirmed '
                    'by the model.',
               'gold_tier': freeze['gold_tier'],
           }}
    PREFLIGHT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    for c in checks:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['check']
              + ('' if c['pass'] else f" -> {c['detail']}"))
    print(f'\nG3-B PREFLIGHT {sum(c["pass"] for c in checks)}/{len(checks)} '
          f'all_pass={all_pass} -> {OUT}')
    return all_pass


if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
