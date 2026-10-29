"""GroundedReview v2 — EAL Gate-2 runner (132 real cells, hard cap $3.00).

Live execution is DOUBLE-GATED and impossible by accident:
    --allow-paid-run  --i-acknowledge-gate2-approved-2026-10-25
Anything else, including --allow-paid-run alone, is REFUSED. Default mode is
offline (--mock or --dry-run), zero network, zero spend.

Served bytes are read ONLY from the Gate-2 frozen set
(evidence_store_eal/gate2/layers) and sha-asserted against BOTH the Gate-2
materials manifest and the Gate-2 freeze manifest before every send. The two
models receive byte-identical messages per layer.

Scoring/retention mirror the Gate-1 runner and the frozen CEE v1.1 controls:
  * response_format json_object, temperature 0, max_tokens 4096, no tools;
  * local five-key validation; an HTTP-200 INVALID/AMBIGUOUS is terminal
    (scored once, never retried/repaired); one technical retry (2s) only on
    a transport error; a json_object rejection HARD-STOPS (no plain-text
    fallback);
  * raw response persisted BEFORE parse; reason / missing_evidence /
    evidence_gap stored verbatim; served id, usage, latency, errors kept;
  * BudgetGuard pre-call on every request ($1.50/model, $3.00 total, peak
    guard prices); a budget stop is recorded, not retried; resume skips
    delivered cells (only api_error cells are eligible).

Offline:
    uv run --python 3.13 -m evidence.eal_gate2_run --mock --dry-run
    uv run --python 3.13 -m evidence.eal_gate2_run --mock
Live (written Gate-2 approval 2026-10-25; needs the openai extra, py3.11):
    uv run --python 3.11 --with openai -m evidence.eal_gate2_run \
        --allow-paid-run --i-acknowledge-gate2-approved-2026-10-25 \
        --max-budget-usd 3.00 --per-model-usd 1.50
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.ternary import read_jsonl, TERNARY
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_run import (PROFILES, RF, MockCompletions, _classify,
                              _sha, _body_region, _FORBIDDEN_VERDICT,
                              _FORBIDDEN_META)

ROOT = Path(__file__).resolve().parent.parent
G2_DIR = ROOT / 'evidence_store_eal' / 'gate2'
LAYER_DIR = G2_DIR / 'layers'
RUN_DIR = ROOT / 'evidence_store_eal' / 'gate2_runs'
MANIFEST_PATH = G2_DIR / 'eal_gate2_materials_manifest.json'
FREEZE_PATH = G2_DIR / 'eal_gate2_freeze_manifest.json'
GATE = 'gate2_live'
ACK = '--i-acknowledge-gate2-approved-2026-10-25'
_RF_REJECT_RE = re.compile(r'response_format|json_object|json_schema', re.I)


def _version_identity(live: bool):
    here = Path(__file__).resolve().parent
    return {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE,
        'gate2_condition':
            'eal-v0-draft1+gate2-derived-summary-disclosure',
        'layers': list(eal.LAYERS),
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'response_format_sent': RF,
        'local_schema_validation':
            'cee_protocol_v11.validate_decision_object',
        'tools': 'none', 'turns': 1,
        'eal_gate2_run_py_sha256': _sha((here / 'eal_gate2_run.py')
                                       .read_bytes()),
        'eal_gate2_freeze_manifest_sha256': _sha(FREEZE_PATH.read_bytes())
        if FREEZE_PATH.exists() else None,
        'mode': 'live' if live else 'mock',
    }


def load_cells():
    man = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    freeze = json.loads(FREEZE_PATH.read_text(encoding='utf-8'))
    fz_payload = freeze['payload_sha256']
    cells = []
    for it in man['items']:
        for layer in eal.LAYERS:
            meta = it['layers'][layer]
            pid = meta['payload_id']
            p = LAYER_DIR / f'{pid}.txt'
            if not p.exists():
                raise SystemExit(f'missing gate-2 payload {p}')
            b = p.read_bytes()
            if _sha(b) != meta['sha256']:
                raise SystemExit(f'gate-2 payload drift vs manifest: {pid}')
            if _sha(b) != fz_payload[pid]['sha256']:
                raise SystemExit(f'gate-2 payload drift vs FREEZE: {pid}')
            cells.append({
                'bundle_id': it['bundle_id'], 'layer': layer,
                'instance_id': it['instance_id'], 'id': it['id'],
                'scenario_internal': it['scenario_internal'],
                'evidence_class': it['evidence_class'],
                'cee_gold': it['cee_gold'], 'payload_id': pid,
                'payload_sha256': meta['sha256'],
                'payload_bytes': len(b),
                'prompt_fingerprint': meta['prompt_fingerprint_gate2'],
                'user_text': b.decode('utf-8'),
                'layer_gold_determined': it['layer_gold_determined'],
                'underdetermined_channels': it['underdetermined_channels']})
    return man, freeze, cells


def pre_send_leak_check(cell):
    if cell['layer'] == 'adjudicated':
        return []
    body = _body_region(cell['layer'], cell['user_text']).lower()
    return [t for t in (_FORBIDDEN_VERDICT + _FORBIDDEN_META) if t in body]


def _out_name(model_name, mock):
    safe = model_name.replace('.', '').replace('-', '_')
    return (f'eal_gate2_{"mock" if mock else "live"}_{safe}_results.jsonl')


def _run_model(name, prof, cells, args, ident, live):
    from evidence.cee_run import _load_key
    out_path = RUN_DIR / _out_name(name, not live)
    prior = read_jsonl(str(out_path)) if out_path.exists() else []
    done = {(r['bundle_id'], r['layer']) for r in prior
            if not r.get('api_error')}
    spent = sum(float(r.get('cost_usd') or 0) for r in prior
                if not r.get('api_error'))
    guard = BudgetGuard(args.per_model_usd, prof['price_in'],
                        prof['price_out'],
                        completion_cap_tokens=args.completion_cap,
                        max_model_calls_per_cell=1)
    guard.spent = spent

    if live:
        from openai import OpenAI
        client = OpenAI(api_key=_load_key(prof), base_url=prof['base_url'])
        completions = client.chat.completions
    else:
        backend = MockCompletions(mode='hash')
        backend._served_id = f"mock-{prof['model']}"
        completions = backend

    n_new = n_err = n_inv = n_amb = 0
    budget_stopped = ''
    with out_path.open('a', encoding='utf-8') as f:
        for cell in cells:
            key = (cell['bundle_id'], cell['layer'])
            if key in done:
                continue
            hits = pre_send_leak_check(cell)
            if hits:
                raise SystemExit(
                    f'LEAK GUARD STOP {name}/{cell["layer"]}/'
                    f'{cell["bundle_id"]}: {hits}')
            messages = eal.build_messages(cell['layer'], cell['user_text'])
            est_in = max(sum(len(m['content']) for m in messages) // 3, 256)
            try:
                bound = guard.check(est_in, 0)
            except BudgetGuardStop as e:
                budget_stopped = f'{name}/{key}: {e}'
                print(f'BUDGET STOP {budget_stopped}')
                break

            t0 = time.time()
            api_error, resp = '', None
            try:
                kw = dict(model=prof['model'], messages=messages,
                          temperature=0, max_tokens=args.completion_cap,
                          response_format=dict(RF))
                if prof['extra_body']:
                    kw['extra_body'] = dict(prof['extra_body'])
                try:
                    resp = completions.create(**kw)
                except Exception as e:  # first failure path
                    if live and _RF_REJECT_RE.search(str(e)):
                        raise SystemExit(
                            f'STOP: {name} rejected json_object (plain-text '
                            f'fallback forbidden): '
                            f'{type(e).__name__}: {str(e)[:300]}')
                    if not live:
                        raise
                    time.sleep(2)
                    resp = completions.create(**kw)
            except SystemExit:
                raise
            except Exception as e:
                api_error = f'{type(e).__name__}: {str(e)[:300]}'
            wall = round(time.time() - t0, 4)

            tin = tout = 0
            served, content = None, ''
            obj_keys, reason_v, missing_v, gap_v = [], '', '', ''
            parsed, validation_errors = 'INVALID', []
            if resp is not None:
                served = getattr(resp, 'model', None)
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
                    parsed, n_amb = 'AMBIGUOUS', n_amb + 1
                else:
                    parsed, n_inv = 'INVALID', n_inv + 1
            else:
                raw_sha = _sha(b'')
            cost = round((tin * prof['price_in']
                          + tout * prof['price_out']) / 1e6, 8) if live \
                else 0.0
            if live and not api_error:
                guard.add(cost)
            appropriate, error_label = (
                (False, 'api_error') if api_error
                else _classify(cell['cee_gold'], parsed,
                               cell['layer_gold_determined']))
            scored = (not api_error) and cell['layer_gold_determined'] \
                and parsed in TERNARY
            rec = {
                'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE,
                'mock': not live,
                'model_profile': name, 'model_requested': prof['model'],
                'model_served': served,
                'e1_served_model_id': prof['e1_served_model_id'],
                'served_matches_e1_model':
                    (served == prof['e1_served_model_id'])
                    if served and live else (False if not live else None),
                'bundle_id': cell['bundle_id'], 'layer': cell['layer'],
                'instance_id': cell['instance_id'], 'id': cell['id'],
                'evidence_class': cell['evidence_class'],
                'cee_gold': cell['cee_gold'],
                'layer_gold_determined': cell['layer_gold_determined'],
                'underdetermined_channels': cell['underdetermined_channels'],
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
                'temperature_sent': 0,
                'max_tokens_sent': args.completion_cap,
                'response_format_mode': 'json_object',
                'response_format_sent': RF,
                'server_schema_enforced': False,
                'plain_text_fallback': False, 'tools_sent': 0,
                'tokens_in_est': tin, 'tokens_out_est': tout,
                'cost_usd': cost,
                'projected_worst_call_usd': round(bound, 8),
                'wall_s': wall, 'api_error': api_error,
                'payload_id': cell['payload_id'],
                'payload_sha256': cell['payload_sha256'],
                'payload_bytes': cell['payload_bytes'],
                'prompt_fingerprint': cell['prompt_fingerprint'],
                'version': dict(ident)}
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            n_new += 1
            if api_error:
                n_err += 1
            print(f'{name:<15} {cell["layer"]:<12} '
                  f'{cell["bundle_id"][-8:]} gold={cell["cee_gold"][:11]:<11} '
                  f'parsed={rec["parsed"][:13]:<13} {error_label[:30]:<30} '
                  f'in={tin:<6} out={tout:<4} ${cost:.5f} '
                  f'cum=${guard.spent:.4f}{" ERR" if api_error else ""}')
            if budget_stopped:
                break
    return {'model_profile': name, 'new_calls': n_new, 'errors': n_err,
            'invalid': n_inv, 'ambiguous': n_amb,
            'spend_usd': round(guard.spent, 6),
            'budget_stopped': budget_stopped,
            'out_file': out_path.name}


def _select(cells, args):
    sel = cells
    if args.only_layers:
        want = {x.strip() for x in args.only_layers.split(',')}
        sel = [c for c in sel if c['layer'] in want]
    if args.only_cells:
        want = {x.strip() for x in args.only_cells.split(',') if x.strip()}
        sel = [c for c in sel if c['bundle_id'] in want
               or c['payload_id'] in want]
    return sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', default='deepseek-flash,gpt-4.1-mini')
    ap.add_argument('--max-budget-usd', type=float, default=3.00)
    ap.add_argument('--per-model-usd', type=float, default=1.50)
    ap.add_argument('--completion-cap', type=int, default=4096)
    ap.add_argument('--only-layers', default='')
    ap.add_argument('--only-cells', default='')
    ap.add_argument('--only-models', default='')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument('--i-acknowledge-gate2-approved-2026-10-25',
                    action='store_true', dest='ack_gate2')
    args = ap.parse_args()

    if args.per_model_usd * 2 > args.max_budget_usd + 1e-9:
        raise SystemExit('per-model caps exceed total budget cap')

    live = bool(args.allow_paid_run and args.ack_gate2)
    if args.allow_paid_run and not args.ack_gate2:
        raise SystemExit(
            'REFUSED: --allow-paid-run also requires the explicit Gate-2 '
            f'acknowledgement flag {ACK}.')
    if not args.mock and not live:
        raise SystemExit(
            'REFUSED: EAL Gate-2 runs ONLY as --mock (offline) or with the '
            f'double gate --allow-paid-run {ACK} (written Gate-2 approval '
            '2026-10-25, hard cap $3.00).')

    if not FREEZE_PATH.exists():
        raise SystemExit('Gate-2 freeze manifest missing; run '
                         'evidence.eal_gate2_freeze (offline) first.')
    man, freeze, all_cells = load_cells()
    cells = _select(all_cells, args)
    names = [x.strip() for x in
             (args.only_models or args.models).split(',') if x.strip()]
    for n in names:
        if n not in PROFILES:
            raise SystemExit(f'unknown model profile {n}')
    ident = _version_identity(live)

    print(f'EAL Gate-2 {"LIVE" if live else "MOCK"}: {len(cells)} cells/'
          f'model x {len(names)} model(s) = {len(cells)*len(names)} '
          f'(frozen gate-2 set; derived-summary disclosure on raw/'
          f'structured)')

    if args.dry_run:
        if live:
            raise SystemExit('REFUSED: --dry-run is offline only; drop '
                             '--allow-paid-run for an envelope check.')
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        worst = {}
        for l in eal.LAYERS:
            bc = [c['payload_bytes'] for c in cells if c['layer'] == l]
            worst[l] = max(bc) if bc else 0
        for n in names:
            p = PROFILES[n]
            print(f'  {n}: per-model cap ${args.per_model_usd:.2f}; guard '
                  f'in=${p["price_in"]} out=${p["price_out"]}')
        print('  worst-case gate-2 payload bytes by layer:', worst)
        print('dry-run: no backend invoked, no rows written')
        return

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for n in names:
        summaries.append(_run_model(n, PROFILES[n], cells, args, ident, live))
        if summaries[-1]['budget_stopped']:
            print('Halting further models on budget stop (resume later).')
            break

    # cross-model byte identity on delivered rows
    seen = {}
    for s in summaries:
        for r in read_jsonl(str(RUN_DIR / s['out_file'])):
            seen.setdefault((r['bundle_id'], r['layer']), set()).add(
                r['payload_sha256'])
    mismatches = {f'{k}': sorted(v) for k, v in seen.items() if len(v) > 1}
    if mismatches:
        raise SystemExit(f'payload byte mismatch across models: {mismatches}')

    total_spend = round(sum(s['spend_usd'] for s in summaries), 6)
    budget_status = 'stopped' if any(s['budget_stopped']
                                     for s in summaries) else 'within_cap'
    audit = {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE, 'live': live,
        'gate2_condition': ident['gate2_condition'],
        'n_cells_per_model_planned': len(cells), 'n_models': len(names),
        'models': summaries,
        'total_spend_usd': total_spend,
        'hard_cap_usd': args.max_budget_usd,
        'per_model_cap_usd': args.per_model_usd,
        'within_total_cap': total_spend <= args.max_budget_usd + 1e-9,
        'budget_status': budget_status,
        'cross_model_payload_byte_identity': not mismatches,
        'payload_sha_mismatches': mismatches,
        'completion_cap_tokens': args.completion_cap,
        'tools_sent': 0, 'plain_text_fallback_used': False,
        'freeze_manifest_sha256': ident['eal_gate2_freeze_manifest_sha256'],
        'version': ident}
    ap_path = RUN_DIR / 'eal_gate2_run_audit.json'
    ap_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                       encoding='utf-8')
    print(f'\nEAL Gate-2 {"live" if live else "mock"} complete: '
          f'new_rows={sum(s["new_calls"] for s in summaries)} '
          f'spend=${total_spend:.4f} cap=${args.max_budget_usd:.2f} '
          f'status={budget_status} byte_identity={not mismatches} '
          f'audit={ap_path.name}')


if __name__ == '__main__':
    main()
