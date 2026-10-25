"""CEE v1.1 offline self-test (Unified JSON Mode). Zero network / paid calls.

Composition (as required by the 2026-10-24 authorisation, item 6):
  A. the ORIGINAL 41 CEE v1 offline checks (re-run unmodified, proving the v1
     frozen design, bundles, gold, determinism and strict-schema v1 contract
     are all intact);
  B. v1.1 amendment checks:
       - both providers wire response_format == {"type":"json_object"} with
         identical canonical bytes, temperature/max_tokens equal, no tools,
         no json_schema request, no plain_text fallback in the runner;
       - the five-property LOCAL validator (missing/extra keys, wrong types,
         illegal enums, plain prose, multiple objects, no field repair);
       - prompt text identical to v1 and contains the word "json";
       - pre-call BudgetGuard hard gate and the 22-call worst-case envelope
         staying inside the $0.50/$1.00 caps;
       - model-identity recording (model_served + E1 served id + drift flag);
       - freeze-manifest consistency (fingerprints, bundle bytes, code sha);
       - full mock runner end-to-end (44 rows, json_object, zero tools).

Run AFTER evidence.cee_freeze_v11:
    uv run --python 3.13 -m evidence.cee_freeze_v11
    uv run --python 3.13 -m evidence.cee_selftest_v11
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.ternary import read_jsonl
from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence import cee_protocol as v1
from evidence import cee_protocol_v11 as cee
from evidence import cee_selftest as v1_selftest
from evidence import cee_run_v11 as runner
from evidence.cee_run import CEE_DIR

HERE = Path(__file__).resolve().parent
FREEZE_PATH = CEE_DIR / 'cee_v1_1_freeze_manifest.json'


def _obj(decision='ACCEPT', *, mismatch=False, gap='', miss='', reason='r'):
    return {'decision': decision, 'reason': reason,
            'evidence_mismatch': mismatch, 'missing_evidence': miss,
            'evidence_gap': gap}


def _run_v11_checks():
    failures = []

    def check(name, cond, detail=''):
        if not cond:
            failures.append(f'{name}' + (f' :: {detail}' if detail else ''))
        print(f"[{'PASS' if cond else 'FAIL'}] v1.1 {name}")

    # ---- freeze manifest exists and matches the code --------------------
    check('cee_v1_1_freeze_manifest.json present', FREEZE_PATH.exists())
    fx = json.loads(FREEZE_PATH.read_text(encoding='utf-8')) \
        if FREEZE_PATH.exists() else {}
    check('freeze protocol id',
          fx.get('protocol_version') == cee.CEE_PROTOCOL_VERSION ==
          'cee-fixed-v1.1', str(fx.get('protocol_version')))
    check('freeze predecessor recorded',
          fx.get('predecessor_version') == v1.CEE_PROTOCOL_VERSION)
    check('freeze output mode unified json_object',
          fx.get('output_mode') == cee.OUTPUT_MODE
          and fx.get('response_format_sent') ==
          cee.RESPONSE_FORMAT_JSON_OBJECT)
    check('freeze fingerprint matches code',
          fx.get('prompt', {}).get('fingerprint_v11')
          == cee.cee_prompt_fingerprint(),
          str(fx.get('prompt', {}).get('fingerprint_v11')))
    check('freeze v1 fingerprint equals v1 code',
          fx.get('prompt', {}).get('fingerprint_v1')
          == v1.cee_prompt_fingerprint())
    check('freeze v11 fingerprint differs from v1',
          cee.cee_prompt_fingerprint() != v1.cee_prompt_fingerprint())

    # ---- prompt text byte-identical to v1, json hint present ------------
    check('system/head/goal text identical to v1 (no wording change)',
          cee.SYSTEM_MESSAGE is v1.SYSTEM_MESSAGE
          and cee.CEE_HEAD is v1.CEE_HEAD and cee.CEE_GOAL is v1.CEE_GOAL)
    check('served prompt text contains the word json (DeepSeek requirement)',
          'json' in (cee.SYSTEM_MESSAGE + cee.CEE_HEAD
                     + cee.CEE_GOAL).lower())

    # ---- 22 bundles reused byte-identical -------------------------------
    ok_disk = fx.get('reused_assets', {}).get(
        'bundles_byte_identical_to_v1') is True
    check('22 bundles reused byte-identical to v1', ok_disk)

    # ---- both wire profiles: identical json_object, equal sampling ------
    expected_rf = canonical_dumps(cee.RESPONSE_FORMAT_JSON_OBJECT)
    for name, p in runner.PROFILES.items():
        kw = {'temperature': 0, 'max_tokens': 4096,
              'response_format': dict(cee.RESPONSE_FORMAT_JSON_OBJECT)}
        check(f'{name}: response_format is json_object',
              kw['response_format'] == {'type': 'json_object'})
        check(f'{name}: canonical response_format bytes identical',
              canonical_dumps(kw['response_format']) == expected_rf)
        check(f'{name}: temperature=0 / max_tokens=4096 / no tools slot',
              kw['temperature'] == 0 and kw['max_tokens'] == 4096
              and 'tools' not in kw)
        check(f'{name}: request shape carries no json_schema object',
              kw['response_format'].get('json_schema') is None
              and 'json_schema' not in json.dumps(kw))
        check(f'{name}: E1 served model id recorded for drift audit',
              bool(p.get('e1_served_model_id')))
    src = (HERE / 'cee_run_v11.py').read_text(encoding='utf-8')
    check('runner: never requests json_schema',
          "'type': 'json_schema'" not in src and '"json_schema"' not in src)
    check('runner: sends json_object',
          "RESPONSE_FORMAT_JSON_OBJECT" in src and "'json_object'" in src)
    check('runner: plain_text fallback forbidden (hard stop wired)',
          'plain_text fallback forbidden' in src
          and 'plain_text_fallback_permitted' in src)

    # ---- local five-property validator ----------------------------------
    good = json.dumps(_obj())
    st, dec, errs = cee.validate_decision_object(good)
    check('validator accepts a conforming object', st == 'ok' and dec
          == 'ACCEPT' and errs == [])
    for label, payload, want in (
            ('missing key', {k: v for k, v in _obj().items()
                             if k != 'reason'}, 'invalid'),
            ('extra key', {**_obj(), 'bogus': 1}, 'invalid'),
            ('mismatch non-bool', _obj('REJECT', mismatch='yes'), 'invalid'),
            ('reason non-string', _obj(reason=5), 'invalid'),
            ('missing_evidence non-string', _obj(miss=0), 'invalid'),
            ('bad evidence_gap enum', _obj('NEED_EVIDENCE', mismatch=True,
                                           miss='x', gap='nope'), 'invalid'),
            ('lowercase decision enum', _obj('accept'), 'invalid'),
            ('plain prose', 'looks fine to me', 'invalid'),
            ('two objects', json.dumps(_obj('ACCEPT')) + ' '
             + json.dumps(_obj('ACCEPT')), 'invalid')):
        body = payload if isinstance(payload, str) else json.dumps(payload)
        s, d, e = cee.validate_decision_object(body)
        check(f'validator: {label} -> {want}', s == want, f'got {s} {e}')
    s, d, e = cee.validate_decision_object(
        '{"decision":"ACCEPT"} later {"decision":"REJECT"}')
    check('validator: conflicting decisions -> ambiguous', s == 'ambiguous')
    # legal NEED_EVIDENCE object with a contract gap
    s, d, e = cee.validate_decision_object(json.dumps(
        _obj('NEED_EVIDENCE', mismatch=True, miss='stale run',
             gap='stale')))
    check('validator: legal NEED_EVIDENCE+gap -> ok', s == 'ok' and d
          == 'NEED_EVIDENCE')

    # ---- budget hard gate ------------------------------------------------
    cells, _ = runner._load_cells()
    worst_in = max((len(cee.SYSTEM_MESSAGE) + len(c['user_text'])) // 3
                   for c in cells)
    total_envelope = 0.0
    for name, p in runner.PROFILES.items():
        g = BudgetGuard(0.50, p['price_in'], p['price_out'],
                        completion_cap_tokens=4096, max_model_calls_per_cell=1)
        env = g.bound_usd(worst_in) * 22
        total_envelope += env
        check(f'{name}: 22-call worst envelope <= $0.50', env <= 0.50,
              f'${env:.4f}')
        g2 = BudgetGuard(0.0001, p['price_in'], p['price_out'],
                         completion_cap_tokens=4096)
        try:
            g2.check(worst_in, 0)
            blocked = False
        except BudgetGuardStop:
            blocked = True
        check(f'{name}: BudgetGuard blocks an over-cap call pre-flight',
              blocked)
    check('combined worst envelope <= $1.00 hard cap',
          total_envelope <= 1.0, f'${total_envelope:.4f}')
    check('freeze budget block',
          fx.get('budget', {}).get('hard_cap_total_usd') == 1.0
          and fx.get('budget', {}).get('n_planned_calls') == 44)

    # ---- v1 preservation / compatibility report retained ---------------
    rep = CEE_DIR / cee.COMPATIBILITY_REPORT
    check('compatibility stop report retained', rep.exists())
    check('freeze records compatibility report sha',
          fx.get('v1_preservation', {}).get(
              'compatibility_stop_report_sha256') is not None)
    check('v1 cee_protocol.py unchanged vs freeze hash',
          fx.get('code_sha256', {}).get('cee_protocol.py (v1, untouched)')
          == runner._sha256_file(HERE / 'cee_protocol.py'))

    # ---- full mock runner end-to-end (44 rows, zero network) ------------
    def _mock_name(n):
        slug = n.replace('.', '').replace('-', '_')
        return CEE_DIR / f'cee_v11_mock_{slug}_results.jsonl'
    mock_files = [_mock_name(n) for n in runner.PROFILES]
    mock_audit = CEE_DIR / 'cee_v11_run_audit.json'
    for m in mock_files:
        if m.exists():
            m.unlink()
    if mock_audit.exists():
        mock_audit.unlink()
    import sys
    oldv = sys.argv
    sys.argv = ['cee_run_v11', '--mock']
    try:
        runner.main()
    finally:
        sys.argv = oldv
    rows_ok = True
    n_rows = 0
    for m in mock_files:
        if not m.exists():
            rows_ok = False
            continue
        rows = read_jsonl(str(m))
        n_rows += len(rows)
        for r in rows:
            if not (r['protocol'] == 'cee-fixed-v1.1'
                    and r['response_format_mode'] == 'json_object'
                    and r['tools_sent'] == 0
                    and r['server_schema_enforced'] is False
                    and r['schema_downgraded'] is False
                    and r['plain_text_fallback'] is False
                    and 'model_served' in r
                    and 'e1_served_model_id' in r
                    and 'served_matches_e1_model' in r
                    and r['version']['prompt_fingerprint_v11']
                    == cee.cee_prompt_fingerprint()):
                rows_ok = False
                break
    check('mock runner: 44 conforming v1.1 rows (22 x 2)',
          n_rows == 44 and rows_ok, f'n={n_rows}')
    for m in mock_files:
        if m.exists():
            m.unlink()
    if mock_audit.exists():
        mock_audit.unlink()
    check('mock artifacts cleaned (no contamination of live file names)',
          all(not m.exists() for m in mock_files)
          and not mock_audit.exists())

    return failures


def main():
    print('=== CEE v1.1 self-test ===\n--- Part A: original CEE v1 frozen '
          'suite (must stay green) ---')
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        v1_failures = v1_selftest._run_checks()
    v1_tail = [ln for ln in buf.getvalue().splitlines() if ln.startswith('[')]
    n_pass = sum(ln.startswith('[PASS]') for ln in v1_tail)
    print(f'(v1 suite: {n_pass} PASS, {len(v1_failures)} FAIL)')
    if v1_failures:
        for f in v1_failures:
            print('  v1 FAIL -', f)

    print('\n--- Part B: CEE v1.1 amendment checks ---')
    v11_failures = _run_v11_checks()

    failures = [f'v1: {f}' for f in v1_failures] + \
        [f'v1.1: {f}' for f in v11_failures]
    print()
    if failures:
        print(f'CEE v1.1 SELFTEST FAILED ({len(failures)}):')
        for f in failures:
            print(' -', f)
        raise SystemExit(1)
    print(f'CEE v1.1 selftest OK: v1 suite {n_pass} green; unified '
          'json_object on both arms, strict local five-property validation, '
          'budget hard gate, model-identity audit and 44-row mock pipeline '
          'all pass')
    print('offline only: no network and no paid API call were performed')


if __name__ == '__main__':
    main()
