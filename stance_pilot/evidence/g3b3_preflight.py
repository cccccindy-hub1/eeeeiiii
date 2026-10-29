"""GroundedReview Gate 3-B.3 — OFFLINE PREFLIGHT / paid-call authorisation gate.

This is the SINGLE aggregating gate that must be fully GREEN before any paid
model call. It costs $0 and makes no vendor request. It re-derives and checks:

  A. freeze integrity
       - on-disk freeze == canonical derivation from the frozen code;
       - 50 items / 100 cells / balanced interleaved order (seed 313);
       - g3b3 + imported-frozen module code hashes match the files that run;
       - the G3-B.2 anchor (freeze + gold certs) is pinned and unchanged.

  B. label leakage (precondition 5)
       - every one of the 50 served g3b2 prompts is rebuilt and scanned: no
         oracle/condition gold field, no dataset label class, no answer
         assertion, no audit-only underscore key; tier-D serves no
         FAIL_TO_PASS / PASS_TO_PASS outcome token.

  C. resume discipline (precondition 5)
       - a scored row and a terminal ScoringError row are NEVER paid for
         again; a transport/acquisition error row stays resume-eligible;
         cumulative actual spend is restored from the on-disk rows; mock
         rows are never counted.

  D. budget protection (precondition 6)
       - $0 cap refused on the first call;
       - pre-call worst-case bound prices the FULL completion cap;
       - per-model $1.50 and shared TOTAL $3.00 breaches are refused before
         the call; the per-cell 12-call cap is enforced; cumulative add /
         resume restoration behaves.

  E. capability / served-model drift HARD-STOP (precondition 7)
       - any non-empty adapter response_format fallback_from (on success OR
         on a raised 400) raises ProtocolCapabilityDrift (a SystemExit),
         never a silent downgrade; a plain error without fallback propagates
         as a resumable error instead; a served model id != the approved id
         hard-stops.

  F. double-gate kill switches
       - the runner refuses --allow-paid-run without the G3-B.3 ACK and
         refuses a bare invocation (no call is made).

  G. evidence aggregation
       - the g3b3 live integration gate report exists and is all green
         (30/30 active freshness TRUE, 0 structural fresh=false, protocol
         version match, frozen G3-A store byte-unchanged);
       - the offline 100-cell mock produced 100 rows with 0 errors and $0.

Offline:
    uv run --python 3.13 -m evidence.g3b3_preflight
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import types
from collections import Counter
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.prompts import ternary_tools

from evidence import g3b2_prompts as GP
from evidence import g3b3_common as C
from evidence import g3b3_freeze as FZ
from evidence.g3b3_run import (
    CompositeGuard, ProtocolCapabilityDrift, acquire_cell,
    assert_served_model, _prior_spent_and_done, _profile,
)

# Mirrors the frozen g3b preflight token policy: the reviewer-facing schema
# legitimately names ACCEPT/REJECT/NEED_EVIDENCE, so leakage is asserted on
# answer-bearing / dataset-field substrings and on tier-D outcome tokens.
FORBIDDEN_SUBSTRINGS = [
    'oracle_gold', 'condition_gold', 'merge_acceptable', 'label_class',
    '"resolved"', 'resolved_in_dataset', 'builder_label_class_audit_only',
    'w2_decisive_bad', 'w2_stale', 'w2_wrong', 'mirror',
]
OUTCOME_TOKENS_D_ONLY = ['FAIL_TO_PASS', 'PASS_TO_PASS']
ANSWER_PATTERNS = [
    'the correct decision is', 'the answer is', 'gold label',
    'this patch should be accepted because it is known',
]


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# B. label leakage
# ---------------------------------------------------------------------------

def label_leakage_audit():
    items = FZ.build_items()
    hits = []
    for it in items:
        msgs = GP.build_g3b2_messages(
            it, artifact=it.get('artifact_record'))
        blob = '\n'.join(str(m.get('content')) for m in msgs)
        low = blob.lower()
        for tok in FORBIDDEN_SUBSTRINGS + ANSWER_PATTERNS:
            if tok.lower() in low:
                hits.append({'cell': it['cell_key'], 'token': tok})
        if it.get('evidence_tier') == 'D':
            for tok in OUTCOME_TOKENS_D_ONLY:
                if tok in blob:
                    hits.append({'cell': it['cell_key'],
                                 'token': f'{tok} [tier-D withheld]'})
        if '"_oracle_gold"' in blob or '"_condition_gold"' in blob:
            hits.append({'cell': it['cell_key'], 'token': '_gold audit key'})
        # the T2A institutional grant may state the decision RULE but never a
        # concrete answer assertion.
        if it['condition'] == 'T2A-T' and 'linkage not yet verified' in blob:
            hits.append({'cell': it['cell_key'],
                         'token': 'stale linkage phrase in repaired T2A'})
    return {'n_items': len(items), 'hits': hits, 'pass': not hits}


def tier_d_projection_check():
    bad = []
    for it in FZ.build_items():
        if it['evidence_tier'] != 'D':
            continue
        summ = (it['artifact_record'].get('summary') or {})
        if summ.get('outcomes_withheld') is not True:
            bad.append({'cell': it['cell_key'], 'leaked': 'no withhold'})
        for k in ('f2p_failed_ids', 'p2p_regressed_ids'):
            if summ.get(k):
                bad.append({'cell': it['cell_key'], 'leaked': k})
    return {'bad': bad, 'pass': not bad}


# ---------------------------------------------------------------------------
# C. resume discipline
# ---------------------------------------------------------------------------

def resume_selftest():
    rows = [
        # scored terminal row (real spend) -> done, spend restored
        {'cell': 'g3b3:i1:T2A-T', 'mock': False, 'cost_usd': 0.01},
        # paid raw landed, then a LOCAL scoring failure -> terminal, never a
        # second paid call
        {'cell': 'g3b3:i2:T3A-T', 'mock': False, 'cost_usd': 0.02,
         'error': 'ScoringError: KeyError: x'},
        # transport/acquisition fault -> resume-eligible, 0 spend restored
        {'cell': 'g3b3:i3:T3A-T', 'mock': False, 'cost_usd': 0.0,
         'error': 'TimeoutError: transport'},
        # mock row -> never counted as live spend or a live done cell
        {'cell': 'g3b3:i4:T2D-T', 'mock': True, 'cost_usd': 0.0},
    ]
    with tempfile.TemporaryDirectory(prefix='g3b3_resume_') as td:
        p = Path(td) / 'live_results.jsonl'
        p.write_text('\n'.join(json.dumps(r) for r in rows) + '\n',
                     encoding='utf-8')
        spent, done = _prior_spent_and_done(p)
    out = {
        'restored_spend_usd': round(spent, 6),
        'done_cells': sorted(done),
        'expect_spent_usd': 0.03,
        'expect_done': ['g3b3:i1:T2A-T', 'g3b3:i2:T3A-T'],
        'resumable_error_cells': ['g3b3:i3:T3A-T'],
    }
    out['pass'] = (
        abs(spent - 0.03) < 1e-9
        and done == set(out['expect_done']))
    return out


# ---------------------------------------------------------------------------
# D. budget protection
# ---------------------------------------------------------------------------

def _composite(pin=0.30, pout=1.20):
    total = BudgetGuard(C.TOTAL_BUDGET_USD, pin, pout,
                        completion_cap_tokens=C.COMPLETION_CAP,
                        max_model_calls_per_cell=C.MAX_MODEL_CALLS_PER_CELL)
    g = CompositeGuard(C.PER_MODEL_CAP_USD, total, pin, pout,
                       completion_cap_tokens=C.COMPLETION_CAP,
                       max_model_calls_per_cell=C.MAX_MODEL_CALLS_PER_CELL)
    return g, total


def budgetguard_selftest():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    # $0 cap refuses the very first call.
    z = BudgetGuard(0.0, 0.30, 1.20,
                    completion_cap_tokens=C.COMPLETION_CAP,
                    max_model_calls_per_cell=C.MAX_MODEL_CALLS_PER_CELL)
    try:
        z.check(1000, 0)
        rec('zero-cap first call REFUSED', False)
    except BudgetGuardStop:
        rec('zero-cap first call REFUSED', True)

    g, total = _composite(0.30, 1.20)
    # A normal small first call fits both guards.
    try:
        g.check(1000, 0)
        rec('normal call within per-model + total caps accepted', True)
    except BudgetGuardStop as e:
        rec('normal call within per-model + total caps accepted', False, e)

    # per-cell model-call cap (12) refused before any new call.
    try:
        g.check(1000, C.MAX_MODEL_CALLS_PER_CELL)
        rec('per-cell 12th model call REFUSED', False)
    except BudgetGuardStop:
        rec('per-cell 12th model call REFUSED', True)

    # worst-case bound prices the FULL completion cap (true upper bound).
    b = g.bound_usd(10_000)
    expect_ds = (10_000 * 0.30 + C.COMPLETION_CAP * 1.20) / 1e6
    rec('DS worst-case bound prices full completion cap',
        abs(b - expect_ds) < 1e-12, f'{b:.8f}=={expect_ds:.8f}')
    g_gpt, _ = _composite(0.40, 1.60)
    b_gpt = g_gpt.bound_usd(10_000)
    expect_gpt = (10_000 * 0.40 + C.COMPLETION_CAP * 1.60) / 1e6
    rec('GPT worst-case bound prices full completion cap',
        abs(b_gpt - expect_gpt) < 1e-12, f'{b_gpt:.8f}=={expect_gpt:.8f}')

    # conservative worst-case: spent just under the cap leaves less than the
    # next bound -> the call is refused BEFORE it is made.
    g2, _ = _composite(0.30, 1.20)
    g2.spent = C.PER_MODEL_CAP_USD - 0.001
    try:
        g2.check(10_000, 0)
        rec('per-model cap breach (worst-case) REFUSED pre-call', False)
    except BudgetGuardStop:
        rec('per-model cap breach (worst-case) REFUSED pre-call', True)

    # per-model cap reached -> refused.
    g3, _ = _composite(0.30, 1.20)
    g3.spent = C.PER_MODEL_CAP_USD
    try:
        g3.check(1000, 0)
        rec('per-model $1.50 breach REFUSED', False)
    except BudgetGuardStop:
        rec('per-model $1.50 breach REFUSED', True)

    # TOTAL cap reached via the shared total guard (other model spent rest).
    g4, t4 = _composite(0.30, 1.20)
    t4.spent = C.TOTAL_BUDGET_USD
    try:
        g4.check(1000, 0)
        rec('TOTAL $3.00 breach REFUSED even with per-model room', False)
    except BudgetGuardStop:
        rec('TOTAL $3.00 breach REFUSED even with per-model room', True)

    # cumulative add() advances BOTH the per-model and shared total guard.
    g5, t5 = _composite(0.30, 1.20)
    g5.add(0.01)
    g5.add(0.02)
    rec('add() accumulates per-model and total identically',
        abs(g5.spent - 0.03) < 1e-12 and abs(t5.spent - 0.03) < 1e-12,
        f'model={g5.spent} total={t5.spent}')
    # resume restoration: setting spent rehydrates the guard.
    g5.spent = 0.03
    rec('resume spend restoration rehydrates guard',
        abs(g5.spent - 0.03) < 1e-12, g5.spent)

    return {'checks': res, 'pass': all(r['pass'] for r in res)}


# ---------------------------------------------------------------------------
# E. capability / served-model drift HARD-STOP
# ---------------------------------------------------------------------------

def _fake_response(model='deepseek-flash', content='{"decision":"ACCEPT",'
                                                '"reason":"ok"}'):
    msg = types.SimpleNamespace(
        content=content, tool_calls=None,
        model_dump=lambda **kw: {'role': 'assistant', 'content': content})
    choice = types.SimpleNamespace(finish_reason='stop', message=msg)
    usage = types.SimpleNamespace(prompt_tokens=5, completion_tokens=5)
    return types.SimpleNamespace(model=model, choices=[choice], usage=usage)


class _FakeCreate:
    def __init__(self, *, raises=None):
        self._raises = raises

    def create(self, model, messages, temperature=0, **kw):
        if self._raises is not None:
            raise self._raises
        return _fake_response(model=model)


def _fake_driver(*, raises=None):
    create = _FakeCreate(raises=raises)
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=create)), create


class _FakeWire:
    def __init__(self, calls):
        self.calls = calls


def _t2a_item():
    return next(it for it in FZ.build_items() if it['condition'] == 'T2A-T')


def drift_selftest():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    item = _t2a_item()
    assert ternary_tools('T2A-T') is None  # static single-turn
    prof = _profile('deepseek-flash')

    # (1) successful response whose wire record shows a response_format
    # fallback -> ProtocolCapabilityDrift hard stop (no silent downgrade).
    drv, _ = _fake_driver()
    wire = _FakeWire([{'response_format': 'plain',
                       'fallback_from': 'json_schema'}])
    try:
        acquire_cell(drv, prof['model'], item, ev=None, profile=prof,
                     wire=wire, mock=False, guard=None)
        rec('success-path response_format fallback HARD-STOPS', False)
    except SystemExit as e:
        rec('success-path response_format fallback HARD-STOPS',
            isinstance(e, ProtocolCapabilityDrift), type(e).__name__)

    # (2) a 400/exception that drove an adapter fallback also hard-stops.
    drv2, _ = _fake_driver(raises=RuntimeError('400 response_format rejected'))
    wire2 = _FakeWire([{'response_format': 'json_object',
                        'fallback_from': 'json_schema'}])
    try:
        acquire_cell(drv2, prof['model'], item, ev=None, profile=prof,
                     wire=wire2, mock=False, guard=None)
        rec('raised-400 response_format fallback HARD-STOPS', False)
    except SystemExit as e:
        rec('raised-400 response_format fallback HARD-STOPS',
            isinstance(e, ProtocolCapabilityDrift), type(e).__name__)

    # (3) a plain exception WITHOUT any fallback is a normal resumable error,
    # NOT a protocol drift (the runner lands an error row; no retry in-cell).
    drv3, _ = _fake_driver(raises=RuntimeError('connection reset'))
    wire3 = _FakeWire([])
    try:
        acquire_cell(drv3, prof['model'], item, ev=None, profile=prof,
                     wire=wire3, mock=False, guard=None)
        rec('plain error without fallback is NOT a drift stop', False)
    except ProtocolCapabilityDrift:
        rec('plain error without fallback is NOT a drift stop', False,
            'wrongly raised drift')
    except RuntimeError:
        rec('plain error without fallback is NOT a drift stop', True)

    # (4) clean success, no fallback -> returns the raw record normally.
    drv4, create4 = _fake_driver()
    wire4 = _FakeWire([])
    raw = acquire_cell(drv4, prof['model'], item, ev=None, profile=prof,
                       wire=wire4, mock=False, guard=None)
    rec('clean response (no fallback) returns raw',
        raw.get('answer_raw', '').startswith('{"decision"'),
        str(raw.get('answer_raw'))[:40])

    # (5) served-model id drift hard-stops; exact match passes.
    try:
        assert_served_model('gpt-4o',
                            'gpt-4.1-mini-2025-04-14', 'g3b3:drift')
        rec('served model id mismatch HARD-STOPS', False)
    except SystemExit:
        rec('served model id mismatch HARD-STOPS', True)
    try:
        assert_served_model('gpt-4.1-mini-2025-04-14',
                            'gpt-4.1-mini-2025-04-14', 'g3b3:ok')
        rec('served model id exact match accepted', True)
    except SystemExit:
        rec('served model id exact match accepted', False)
    # a None served id (nothing returned yet) does not trip the check.
    try:
        assert_served_model(None, 'gpt-4.1-mini-2025-04-14', 'g3b3:none')
        rec('absent served id does not false-trip', True)
    except SystemExit:
        rec('absent served id does not false-trip', False)

    return {'checks': res, 'pass': all(r['pass'] for r in res)}


# ---------------------------------------------------------------------------
# F. double-gate kill switches (subprocess; both paths refuse before run())
# ---------------------------------------------------------------------------

def subprocess_killswitches():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    def run(*extra):
        p = subprocess.run([sys.executable, '-m', 'evidence.g3b3_run', *extra],
                           cwd=str(C.HERE), capture_output=True, text=True)
        return p.returncode, (p.stdout + p.stderr)

    rc, out = run('--allow-paid-run')
    rec('live flag WITHOUT the G3-B.3 ACK is REFUSED',
        rc != 0 and 'REFUSED' in out, out[-180:])
    rc, out = run()
    rec('bare invocation REFUSED (no paid call possible)',
        rc != 0 and 'REFUSED' in out, out[-180:])
    return {'checks': res, 'pass': all(r['pass'] for r in res)}


# ---------------------------------------------------------------------------
# A. freeze integrity + G. aggregation of livegate + mock
# ---------------------------------------------------------------------------

def freeze_integrity():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    freeze = json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))
    rec('freeze exists', C.OUT_FREEZE.exists(), str(C.OUT_FREEZE))
    canon = C.canonical_bytes(FZ.build_freeze())
    rec('on-disk freeze == canonical derivation',
        _sha(C.OUT_FREEZE.read_bytes()) == _sha(canon),
        _sha(C.OUT_FREEZE.read_bytes())[:12])
    rec('50 items / 100 cells',
        freeze['n_items'] == 50 and freeze['n_cells'] == 100,
        f"items={freeze['n_items']} cells={freeze['n_cells']}")
    cnt = Counter((c['model_profile'], c['condition'])
                  for c in freeze['cells'])
    rec('balanced 10 model-condition combos x 10',
        len(cnt) == 10 and set(cnt.values()) == {10}, str(dict(cnt)))
    rec('new order seed 313', freeze['call_order_seed'] == C.ORDER_SEED,
        freeze['call_order_seed'])
    rec('retries_per_cell 0',
        freeze['sampling']['retries_per_cell'] == 0)
    rec('caps $3.00 total / $1.50 per model',
        freeze['budget']['total_hard_cap_usd'] == C.TOTAL_BUDGET_USD
        and all(p['per_model_cap_usd'] == C.PER_MODEL_CAP_USD
                for p in freeze['profiles'].values()))
    cur_hashes = FZ._g3b3_code_hashes()
    rec('g3b3 + imported frozen code hashes match runnable files',
        cur_hashes == freeze['g3b3_code_hashes'],
        'g3b3_modules=%d imported=%d' % (
            len(cur_hashes['g3b3_modules']),
            len(cur_hashes['imported_frozen_modules'])))
    anchor = freeze['g3b2_anchor']
    rec('g3b2 freeze manifest anchor pinned',
        anchor['g3b2_freeze_manifest_sha256']
        == C.sha256_file(C.G3B2_FREEZE))
    rec('g3b2 gold certs anchor pinned + 0 value changes',
        anchor['g3b2_gold_certificates_sha256']
        == C.sha256_file(C.G3B2_GOLD_CERTS)
        and anchor['g3b2_gold_value_changes_vs_g3a1'] == 0)
    return {'checks': res, 'pass': all(r['pass'] for r in res),
            'freeze': freeze}


def aggregate_livegate():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    exists = C.OUT_LIVEGATE.exists()
    rec('live integration gate report exists', exists, str(C.OUT_LIVEGATE))
    if not exists:
        return {'checks': res, 'pass': False}
    rep = json.loads(C.OUT_LIVEGATE.read_text(encoding='utf-8'))
    rec('livegate zero errors', rep.get('n_errors') == 0,
        rep.get('n_errors'))
    rec('livegate 30/30 active freshness TRUE',
        rep.get('n_active_freshness_TRUE') == 30,
        rep.get('n_active_freshness_TRUE'))
    rec('livegate zero structural fresh=false',
        rep.get('n_structural_fresh_false') == 0,
        rep.get('n_structural_fresh_false'))
    rec('livegate served g3b2 protocol version',
        rep.get('server_protocol_version') == C.RUN_PROTOCOL_VERSION,
        rep.get('server_protocol_version'))
    rec('livegate frozen G3-A store byte-unchanged',
        rep.get('frozen_store_unchanged') is True)
    rec('livegate negative injections included',
        rep.get('negative_restage_miss_injection', {}).get('errors') == []
        and rep.get('negative_freshness_pure', {}).get('errors') == [])
    return {'checks': res, 'pass': all(r['pass'] for r in res)}


def aggregate_mock():
    res = []

    def rec(name, ok, detail=''):
        res.append({'check': name, 'pass': bool(ok), 'detail': str(detail)})

    files = sorted(C.OUT_LIVE_DIR.glob('g3b3_mock_*_results.jsonl')) \
        if C.OUT_LIVE_DIR.exists() else []
    rec('two mock result files present (one per model)', len(files) == 2,
        [f.name for f in files])
    total_rows = total_err = 0
    for f in files:
        rows = C.read_jsonl(f)
        total_rows += len(rows)
        total_err += sum(1 for r in rows if r.get('error'))
        rec(f'{f.name}: 50 rows, all mock/research-excluded/PROVISIONAL',
            len(rows) == 50
            and all(r.get('mock') and r.get('research_excluded')
                    and r.get('gold_tier') == 'PROVISIONAL'
                    and r.get('annotator2') == 'NOT_OBTAINED' for r in rows),
            f'rows={len(rows)}')
    rec('100 mock cells, zero errors, zero spend',
        total_rows == 100 and total_err == 0,
        f'rows={total_rows} errors={total_err}')
    audit_p = C.OUT_LIVE_DIR / 'g3b3_mock_run_audit.json'
    if audit_p.exists():
        au = json.loads(audit_p.read_text(encoding='utf-8'))
        rec('mock audit total_spend $0 within cap',
            au.get('total_spend_usd') == 0 and au.get('within_total_cap'),
            au.get('total_spend_usd'))
    else:
        rec('mock audit present', False, 'missing g3b3_mock_run_audit.json')
    return {'checks': res, 'pass': all(r['pass'] for r in res)}


# ---------------------------------------------------------------------------

def main():
    sections = []

    def add(name, out):
        checks = out.pop('checks') if 'checks' in out else []
        ok = out.pop('pass')
        sections.append({'section': name, 'pass': ok,
                         'checks': checks, 'detail': out})
        return ok

    fz_out = freeze_integrity()
    add('A_freeze_integrity', fz_out)
    add('B_label_leakage', label_leakage_audit())
    add('B2_tier_d_projection', tier_d_projection_check())
    add('C_resume_discipline', resume_selftest())
    add('D_budget_protection', budgetguard_selftest())
    add('E_capability_drift_hardstop', drift_selftest())
    add('F_double_gate_killswitches', subprocess_killswitches())
    add('G_livegate_aggregation', aggregate_livegate())
    add('G_mock_aggregation', aggregate_mock())

    n_checks = sum(len(s['checks']) for s in sections)
    n_pass = sum(sum(1 for c in s['checks'] if c['pass'])
                 for s in sections)
    all_pass = all(s['pass'] for s in sections)

    doc = {
        'document': 'Gate 3-B.3 paid-call authorisation preflight. ALL '
                    'sections must pass before --allow-paid-run '
                    + C.ACK + ' is permitted.',
        'gate': C.GATE,
        'all_pass': all_pass,
        'n_sections': len(sections),
        'n_checks': n_checks, 'n_checks_pass': n_pass,
        'sections': sections,
        'budget': {'total_hard_cap_usd': C.TOTAL_BUDGET_USD,
                   'per_model_cap_usd': C.PER_MODEL_CAP_USD},
        'double_gate': {'flag_paid': '--allow-paid-run',
                        'flag_acknowledgement': C.ACK},
        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope': C.APPROVED_SCOPE,
        'paid_run_authorised_only_if_all_pass': all_pass,
    }
    C.OUT_PREFLIGHT.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_PREFLIGHT.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    for s in sections:
        print(('PASS ' if s['pass'] else 'FAIL ') + s['section']
              + f" ({sum(1 for c in s['checks'] if c['pass'])}/"
              + f"{len(s['checks'])} checks)")
        for c in s['checks']:
            if not c['pass']:
                print('    -', c['check'], '->', c.get('detail'))
    print(f'\nG3-B.3 PREFLIGHT {n_pass}/{n_checks} all_pass={all_pass}')
    print('report ->', C.OUT_PREFLIGHT)
    if not all_pass:
        raise SystemExit(
            'G3-B.3 preflight FAILED — paid run is NOT authorised.')
    return all_pass


if __name__ == '__main__':
    main()
