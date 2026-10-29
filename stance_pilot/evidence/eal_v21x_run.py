"""GroundedReview v2.1 Experiment X — 2x2 factorial runner (176 NEW paid
calls: 22 fixtures x 4 conditions x 2 models; TOTAL hard cap $1.50 across
both models).

Conditional written approval 2026-10-25. Paid execution is gated on the
pre-call statistics/freeze audit: estimand reconciliation (cell-weighted vs
issue-equal, never mixed), the frozen shared statistics module, the X freeze
manifest + offline preflight, and a full offline mock run. R2, Gate-3
expansion, Gemini/other models, new issues and git commits are NOT included.

Design / discipline enforced in code
------------------------------------
* ALL FOUR conditions (a0b0, a1b0, a0b1, a1b1) are called fresh in X. The
  Gate-2 / R1 a0b0 rows are NEVER borrowed as the X control.
* Calls are emitted in the single deterministic, pre-frozen INTERLEAVED
  serial order (evidence.eal_v21x_freeze.interleaved_order), alternating
  models and conditions; the order is not changed from interim results.
* One single turn, no tools, temperature 0, max_tokens 4096,
  response_format json_object (a json_object rejection HARD-STOPS).
* Double gate: --allow-paid-run plus
  --i-acknowledge-x-approved-2026-10-25. Anything else is offline.
* Per-request BudgetGuard; TOTAL spend across both models is checked before
  every send against the $1.50 hard cap (per-model $0.75 guards).
* ZERO retries: a wrong decision, INVALID, AMBIGUOUS or transport fault is a
  terminal row (faults persisted as api_error, resume-eligible, never auto-
  retried).
* Raw response persisted BEFORE parse; reason / missing_evidence /
  evidence_gap / usage / latency / served id retained verbatim.
* Served-model id drift or unexplained API-parameter drift HARD-STOPS.
* Resume skips delivered (non-api_error) cells; never double-bills.
* A paid run never (re)writes the freeze; it verifies hashes and order.

Offline (py3.13, $0):
    uv run --python 3.13 -m evidence.eal_v21x_run --preflight
    uv run --python 3.13 -m evidence.eal_v21x_run --mock --dry-run
    uv run --python 3.13 -m evidence.eal_v21x_run --mock
Live (needs openai extra, py3.11):
    uv run --python 3.11 --with openai -m evidence.eal_v21x_run \\
        --allow-paid-run --i-acknowledge-x-approved-2026-10-25 \\
        --total-budget-usd 1.50
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.ternary import read_jsonl, TERNARY
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_run import (PROFILES, MockCompletions, _classify, _sha,
                              pre_send_leak_check)
from evidence.eal_v21x_freeze import (ACK, COMPLETION_CAP, GATE, LAYER,
                                      MODELS, PER_MODEL_CAP_USD,
                                      TOTAL_BUDGET_USD, V21_LAYERS, X_DIR,
                                      X_FREEZE, X_PREFLIGHT, build_x_freeze,
                                      canonical_bytes, interleaved_order,
                                      load_design)

ROOT = Path(__file__).resolve().parent.parent
X_RUNS = ROOT / 'evidence_store_eal' / 'v21x_runs'


def _out_name(model_name, mock):
    safe = model_name.replace('.', '').replace('-', '_')
    return (f'eal_v21x_{"mock" if mock else "live"}_{safe}_results.jsonl')


def load_freeze():
    if not X_FREEZE.exists():
        raise SystemExit('X freeze manifest missing (offline build first).')
    return json.loads(X_FREEZE.read_text(encoding='utf-8'))


def payload_text(payload_id, sha_expected):
    p = V21_LAYERS / f'{payload_id}.txt'
    b = p.read_bytes()
    if _sha(b) != sha_expected:
        raise SystemExit(f'X payload tamper/drift: {payload_id}')
    return b.decode('utf-8')


def preflight(freeze):
    import subprocess
    import sys
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'check': gid, 'pass': bool(ok), 'detail': str(detail)})

    # 1. freeze is canonical derivation from the v2.1 design (offline).
    canon = canonical_bytes(build_x_freeze())
    gate('x: on-disk freeze == canonical v2.1 derivation',
         _sha(X_FREEZE.read_bytes()) == _sha(canon),
         _sha(X_FREEZE.read_bytes())[:12])

    # 2. shape: 176 cells / 176 ordered calls; every order entry has a cell.
    cells = freeze['cells']
    order = freeze['call_order']
    gate('x: 176 frozen cells (22 x 4 x 2)', len(cells) == 176, len(cells))
    gate('x: 176 ordered calls', len(order) == 176, len(order))
    cell_idx = {(c['model_profile'], c['bundle_id'], c['condition']): c
                for c in cells}
    missing = [(o['model_profile'], o['bundle_id'], o['condition'])
               for o in order
               if (o['model_profile'], o['bundle_id'], o['condition'])
               not in cell_idx]
    gate('x: every ordered call maps to a frozen cell', not missing,
         missing[:3])

    # 3. deterministic order recomputed from frozen code matches the manifest
    recomputed = interleaved_order(load_design())
    gate('x: call order is the deterministic interleaved order',
         recomputed == order, 'seed=%s' % freeze['call_order_seed'])

    # 4. balance: each (model, condition) appears exactly 22 times.
    from collections import Counter
    cnt = Counter((o['model_profile'], o['condition']) for o in order)
    gate('x: order balanced (8 combos x 22)',
         len(cnt) == 8 and set(cnt.values()) == {22}, dict(cnt))

    # 5. payload bytes on disk hash-match the freeze for all 88 payloads.
    seen, bad = set(), []
    for c in cells:
        if c['payload_id'] in seen:
            continue
        seen.add(c['payload_id'])
        p = V21_LAYERS / f"{c['payload_id']}.txt"
        if not p.exists() or _sha(p.read_bytes()) != c['payload_sha256']:
            bad.append(c['payload_id'])
    gate('x: 88 payload files byte-match freeze', len(seen) == 88
         and not bad, (len(seen), bad[:2]))

    # 6. pre-send leak guard clean (structured bodies).
    hits = []
    for c in cells[: 88]:  # one model copy is enough; bytes identical
        txt = payload_text(c['payload_id'], c['payload_sha256'])
        h = pre_send_leak_check({'layer': LAYER, 'user_text': txt})
        if h:
            hits.append((c['payload_id'], h))
    gate('x: pre-send leak guard clean on 88 structured payloads', not hits,
         hits[:2])

    # 7. sampling / budget contract.
    gate('x: temp0 / max4096 / json_object / tools0 / retries0',
         freeze['sampling'] == {'temperature': 0, 'max_tokens': COMPLETION_CAP,
                                'response_format': dict(
                                    cee.RESPONSE_FORMAT_JSON_OBJECT),
                                'tools': 0, 'turns': 1,
                                'retries_per_cell': 0})
    gate('x: total cap $1.50, per-model $0.75 x2',
         freeze['budget']['total_hard_cap_usd'] == TOTAL_BUDGET_USD
         and abs(2 * PER_MODEL_CAP_USD - TOTAL_BUDGET_USD) < 1e-9)
    gate('x: all four conditions recalled; no borrowed control',
         freeze['all_four_conditions_recalled']
         and freeze['no_borrowed_control'])

    # 8. frozen code hashes match the files that will actually run.
    here = Path(__file__).resolve().parent
    ch = freeze['code_hashes']
    drift = []
    for mod, fname in (('eal_stats_py', 'eal_stats.py'),
                       ('eal_v21x_freeze_py', 'eal_v21x_freeze.py'),
                       ('eal_v21x_run_py', 'eal_v21x_run.py'),
                       ('eal_v21x_analyze_py', 'eal_v21x_analyze.py')):
        fp = here / fname
        cur = _sha(fp.read_bytes()) if fp.exists() else None
        if cur != ch.get(mod):
            drift.append((fname, ch.get(mod), cur))
    gate('x: code files match frozen hashes', not drift,
         [(d[0], (d[2] or 'MISSING')[:10]) for d in drift])

    # 9. kill switches: live without ack REFUSED; bare REFUSED.
    p1 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_v21x_run', '--allow-paid-run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('x: live without X acknowledgement REFUSED',
         p1.returncode != 0 and 'REFUSED' in (p1.stdout + p1.stderr))
    p2 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_v21x_run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('x: bare invocation REFUSED (offline default)',
         p2.returncode != 0 and 'REFUSED' in (p2.stdout + p2.stderr))
    # 10. budget over-cap refusal + mock dry-run envelope.
    p3 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_v21x_run', '--allow-paid-run',
         ACK, '--total-budget-usd', '1.51'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('x: budget above $1.50 REFUSED',
         p3.returncode != 0 and 'REFUSED' in (p3.stdout + p3.stderr))
    p4 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_v21x_run', '--mock',
         '--dry-run'], cwd=str(ROOT), capture_output=True, text=True)
    gate('x: mock --dry-run ok', p4.returncode == 0,
         (p4.stdout + p4.stderr)[-200:])

    all_pass = all(c['pass'] for c in checks)
    out = {'document': 'Experiment X offline preflight (must pass before '
                       'any paid call)',
           'n_checks': len(checks), 'all_pass': all_pass, 'checks': checks}
    X_PREFLIGHT.write_bytes(
        (json.dumps(out, ensure_ascii=False, indent=2) + '\n')
        .encode('utf-8'))
    for c in checks:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['check']
              + ('' if c['pass'] else f" -> {c['detail']}"))
    print(f'X PREFLIGHT {sum(c["pass"] for c in checks)}/{len(checks)}; '
          f'all_pass={all_pass}')
    return all_pass


def _version_identity(live):
    here = Path(__file__).resolve().parent
    return {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE, 'layer': LAYER,
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'response_format_sent': dict(cee.RESPONSE_FORMAT_JSON_OBJECT),
        'tools': 'none', 'turns': 1, 'retries_per_cell': 0,
        'eal_stats_py_sha256': _sha((here / 'eal_stats.py').read_bytes()),
        'eal_v21x_run_py_sha256':
            _sha((here / 'eal_v21x_run.py').read_bytes()),
        'x_freeze_manifest_sha256': _sha(X_FREEZE.read_bytes()),
        'mode': 'live' if live else 'mock'}


def run(freeze, args, live):
    cells = freeze['cells']
    order = freeze['call_order']
    cell_idx = {(c['model_profile'], c['bundle_id'], c['condition']): c
                for c in cells}
    X_RUNS.mkdir(parents=True, exist_ok=True)

    # Backends, guards, open files per model.
    backends, guards, files, done, spent_model = {}, {}, {}, {}, {}
    global_spent = [0.0]
    for m in MODELS:
        prof = PROFILES[m]
        out_path = X_RUNS / _out_name(m, not live)
        prior = read_jsonl(str(out_path)) if out_path.exists() else []
        done[m] = {(r['bundle_id'], r['condition']) for r in prior
                   if not r.get('api_error')}
        spent_model[m] = sum(float(r.get('cost_usd') or 0) for r in prior
                             if not r.get('api_error'))
        g = BudgetGuard(PER_MODEL_CAP_USD, prof['price_in'],
                        prof['price_out'],
                        completion_cap_tokens=COMPLETION_CAP,
                        max_model_calls_per_cell=1)
        g.spent = spent_model[m]
        guards[m] = g
        files[m] = out_path.open('a', encoding='utf-8')
        if live:
            global_spent[0] = round(global_spent[0] + spent_model[m], 8)
            from openai import OpenAI
            from evidence.cee_run import _load_key
            backends[m] = OpenAI(api_key=_load_key(prof),
                                 base_url=prof['base_url']).chat.completions
        else:
            mc = MockCompletions(mode='hash')
            mc._served_id = f"mock-{prof['model']}"
            backends[m] = mc
    if live:
        print(f'restored prior X live spend=${global_spent[0]:.4f}')

    ident = _version_identity(live)
    profs = {m: PROFILES[m] for m in MODELS}
    counts = {m: {'new': 0, 'error': 0, 'invalid': 0, 'ambiguous': 0}
              for m in MODELS}
    stop_msg = ''

    try:
        for o in order:
            m, bid, cond = o['model_profile'], o['bundle_id'], o['condition']
            prof = profs[m]
            if (bid, cond) in done[m]:
                continue
            cell = cell_idx[(m, bid, cond)]
            txt = payload_text(cell['payload_id'], cell['payload_sha256'])

            hits = pre_send_leak_check({'layer': LAYER, 'user_text': txt})
            if hits:
                raise SystemExit(f'LEAK GUARD STOP {m}/{cond}/{bid}: {hits}')

            messages = eal.build_messages(LAYER, txt)
            est_in = max(sum(len(mm['content']) for mm in messages) // 3, 256)
            try:
                guards[m].check(est_in, 0)
            except BudgetGuardStop as e:
                stop_msg = f'{m}/per-model guard: {e}'
                print('BUDGET STOP ' + stop_msg)
                break
            worst = (est_in * prof['price_in']
                     + COMPLETION_CAP * prof['price_out']) / 1e6
            if global_spent[0] + worst > args.total_budget_usd + 1e-9:
                stop_msg = (f'{m}/{cond}: GLOBAL X cap '
                            f'${args.total_budget_usd} would be exceeded '
                            f'(spent ${global_spent[0]:.4f}, worst next '
                            f'${worst:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            t0 = time.time()
            api_error, resp = '', None
            try:  # ONE attempt; no retry on anything.
                resp = backends[m].create(
                    model=prof['model'], messages=messages, temperature=0,
                    max_tokens=COMPLETION_CAP,
                    response_format=dict(cee.RESPONSE_FORMAT_JSON_OBJECT),
                    **({'extra_body': dict(prof['extra_body'])}
                       if prof['extra_body'] else {}))
            except Exception as e:
                if live and re.search(r'response_format|json_object|'
                                      r'json_schema', str(e), re.I):
                    raise SystemExit(
                        f'STOP: {m} rejected json_object (plain-text '
                        f'fallback forbidden): {type(e).__name__}: '
                        f'{str(e)[:300]}')
                api_error = f'{type(e).__name__}: {str(e)[:300]}'
            wall = round(time.time() - t0, 4)

            tin = tout = 0
            served, content = None, ''
            obj_keys, reason_v, missing_v, gap_v = [], '', '', ''
            parsed, validation_errors = 'INVALID', []
            if resp is not None:
                served = getattr(resp, 'model', None)
                if live and served and served != prof['e1_served_model_id']:
                    raise SystemExit(
                        f'SERVED MODEL DRIFT STOP {m}: expected '
                        f'{prof["e1_served_model_id"]}, got {served}; '
                        'halting, no substitution.')
                u = getattr(resp, 'usage', None)
                if u is not None:
                    tin = int(getattr(u, 'prompt_tokens', 0) or 0)
                    tout = int(getattr(u, 'completion_tokens', 0) or 0)
                content = (resp.choices[0].message.content
                           if getattr(resp, 'choices', None) else '') or ''
                raw_sha = _sha(content.encode('utf-8'))
                status, decision, validation_errors = \
                    cee.validate_decision_object(content)
                if status == 'ok':
                    parsed = decision
                    obj = json.loads(content)
                    obj_keys = sorted(obj.keys())
                    reason_v = obj.get('reason', '')
                    missing_v = obj.get('missing_evidence', '')
                    gap_v = obj.get('evidence_gap', '')
                elif status == 'ambiguous':
                    counts[m]['ambiguous'] += 1
                else:
                    counts[m]['invalid'] += 1
            else:
                raw_sha = _sha(b'')
            cost = round((tin * prof['price_in'] + tout * prof['price_out'])
                         / 1e6, 8) if live else 0.0
            if live and not api_error:
                guards[m].add(cost)
                global_spent[0] = round(global_spent[0] + cost, 8)
            appropriate, error_label = (
                (False, 'api_error') if api_error
                else _classify(cell['cee_gold'], parsed,
                               cell['layer_gold_determined']))
            scored = ((not api_error) and cell['layer_gold_determined']
                      and parsed in TERNARY)
            rec = {
                'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE,
                'mock': not live, 'model_profile': m,
                'model_requested': prof['model'], 'model_served': served,
                'expected_served_model_id': prof['e1_served_model_id'],
                'served_matches_expected':
                    (served == prof['e1_served_model_id']) if live else None,
                'bundle_id': bid, 'condition': cond, 'layer': LAYER,
                'serial': o['serial'],
                'instance_id': cell['instance_id'], 'id': cell['id'],
                'evidence_class': cell['evidence_class'],
                'cee_gold': cell['cee_gold'],
                'layer_gold_determined': cell['layer_gold_determined'],
                'underdetermined_channels':
                    cell['underdetermined_channels'],
                'parsed': parsed if not api_error else 'API_ERROR',
                'appropriate': appropriate, 'error_label': error_label,
                'scored': scored,
                'parseable': parsed in TERNARY and not api_error,
                'raw_response_text': content,
                'raw_content_sha256': raw_sha,
                'raw_persisted_before_parse': True,
                'response_object_keys': obj_keys,
                'reason_verbatim': reason_v,
                'missing_evidence_verbatim': missing_v,
                'evidence_gap_verbatim': gap_v,
                'local_validation_errors': validation_errors,
                'temperature_sent': 0, 'max_tokens_sent': COMPLETION_CAP,
                'response_format_mode': 'json_object',
                'response_format_sent': dict(cee.RESPONSE_FORMAT_JSON_OBJECT),
                'server_schema_enforced': False,
                'plain_text_fallback': False, 'tools_sent': 0,
                'retries': 0,
                'tokens_in': tin, 'tokens_out': tout,
                'cost_usd': cost, 'wall_s': wall, 'api_error': api_error,
                'payload_id': cell['payload_id'],
                'payload_sha256': cell['payload_sha256'],
                'payload_bytes': cell['payload_bytes'],
                'head_sha256': cell['head_sha256'],
                'body_sha256': cell['body_sha256'],
                'prompt_fingerprint': cell['prompt_fingerprint'],
                'version': dict(ident)}
            files[m].write(json.dumps(rec, ensure_ascii=False) + '\n')
            files[m].flush()
            counts[m]['new'] += 1
            if api_error:
                counts[m]['error'] += 1
            print(f'{o["serial"]:>3} {m[:3]} {cond} {bid[-8:]} '
                  f'gold={cell["cee_gold"][:11]:<11} '
                  f'parsed={rec["parsed"][:13]:<13} '
                  f'{error_label[:22]:<22} in={tin:<6} out={tout:<4} '
                  f'${cost:.5f} global=${global_spent[0]:.4f}'
                  f'{" ERR" if api_error else ""}')
    finally:
        for fh in files.values():
            fh.close()

    if stop_msg:
        print('Halted on stop condition; resume later (no retries issued).')

    models_summary = []
    for m in MODELS:
        models_summary.append(
            {'model_profile': m, **counts[m],
             'spend_usd': round(guards[m].spent, 6),
             'out_file': _out_name(m, not live)})
    total_new = sum(counts[m]['new'] for m in MODELS)
    total_spend = round(sum(s['spend_usd'] for s in models_summary), 6)
    audit = {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE, 'live': live,
        'total_new_cells': total_new, 'models': models_summary,
        'total_spend_usd': total_spend,
        'global_hard_cap_usd': args.total_budget_usd,
        'within_global_cap': total_spend <= args.total_budget_usd + 1e-9,
        'completion_cap_tokens': COMPLETION_CAP, 'tools_sent': 0,
        'retries_per_cell': 0, 'plain_text_fallback_used': False,
        'all_four_conditions_recalled': True,
        'stop_msg': stop_msg,
        'x_freeze_manifest_sha256': ident['x_freeze_manifest_sha256'],
        'version': ident}
    (X_RUNS / f'eal_v21x_{"live" if live else "mock"}_run_audit.json') \
        .write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                    encoding='utf-8')
    print(f'\nX {"LIVE" if live else "mock"} complete: new_rows={total_new} '
          f'spend=${total_spend:.4f} cap=${args.total_budget_usd:.2f} '
          f'within_cap={audit["within_global_cap"]}'
          + (f' STOP: {stop_msg}' if stop_msg else ''))
    return audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--total-budget-usd', type=float,
                    default=TOTAL_BUDGET_USD)
    ap.add_argument('--preflight', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument(ACK, action='store_true', dest='ack_x')
    args = ap.parse_args()

    if args.preflight:
        freeze = load_freeze()
        ok = preflight(freeze)
        raise SystemExit(0 if ok else 1)

    live = bool(args.allow_paid_run and args.ack_x)
    if args.allow_paid_run and not args.ack_x:
        raise SystemExit(f'REFUSED: --allow-paid-run also requires {ACK}.')
    if not args.mock and not live:
        raise SystemExit(
            'REFUSED: Experiment X runs ONLY as --mock/--preflight '
            '(offline) or with the double gate --allow-paid-run '
            f'{ACK} (conditional written approval 2026-10-25, 176 NEW '
            'calls, TOTAL hard cap $1.50 both models).')
    if args.total_budget_usd > TOTAL_BUDGET_USD + 1e-9:
        raise SystemExit(
            f'REFUSED: X total cap cannot exceed the approved '
            f'${TOTAL_BUDGET_USD:.2f}.')

    # Freeze discipline: never rewrite the freeze at run time; verify it is
    # the canonical derivation and that the preflight passed.
    freeze = load_freeze()
    canon = canonical_bytes(build_x_freeze())
    if _sha(X_FREEZE.read_bytes()) != _sha(canon):
        raise SystemExit(
            'REFUSED: X freeze differs from the canonical v2.1 derivation; '
            'rebuild offline and rerun preflight before any paid call.')
    if live:
        if not X_PREFLIGHT.exists():
            raise SystemExit('REFUSED: X preflight missing (run --preflight).')
        pf = json.loads(X_PREFLIGHT.read_text(encoding='utf-8'))
        if not pf.get('all_pass'):
            raise SystemExit('REFUSED: X preflight is not all_pass.')

    print(f'X {"LIVE" if live else "MOCK"}: 22 fixtures x 4 conditions x '
          f'2 models = 176 calls; TOTAL cap ${args.total_budget_usd:.2f}; '
          'interleaved frozen order; all four conditions recalled fresh')

    if args.dry_run:
        if live:
            raise SystemExit('REFUSED: --dry-run is offline only.')
        for m in MODELS:
            p = PROFILES[m]
            print(f'  {m}: in=${p["price_in"]} out=${p["price_out"]} '
                  f'expected_served={p["e1_served_model_id"]}')
        print('dry-run: no backend invoked, no rows written')
        return

    run(freeze, args, live)


if __name__ == '__main__':
    main()
