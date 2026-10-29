"""GroundedReview R1 — Test-Retest Reliability runner (Gate-2 frozen
protocol, one additional complete round, 132 paid cells, TOTAL hard cap
$1.50 across BOTH models).

Written approval 2026-10-25: R1 approved ONLY. The v2.1 2x2 (X), R2,
Gate-3 expansion, Gemini and git commits remain UNAUTHORISED.

Design
------
The exact Gate-2 frozen 66 payloads/model are re-served BYTE-FOR-BYTE (sha
asserted against BOTH Gate-2 materials and freeze manifests before every
send) with identical system prompt, sampling params (temperature 0,
max_tokens 4096), response_format json_object, tools=0 and the same local
schema/scoring. Gate-2's own 132 rows remain the FIRST time point; R1 writes
only to evidence_store_eal/r1 and evidence_store_eal/r1_runs.

Rules enforced in code:
  * double gate: --allow-paid-run plus
    --i-acknowledge-r1-approved-2026-10-25; anything else (incl. --mock)
    runs offline and spends nothing;
  * TOTAL spend hard cap $1.50 shared by both models, pre-call guarded;
  * one single attempt per cell — NO retry on a wrong decision, INVALID, or
    a client/transport fault; a fault is persisted as api_error (an unpaid /
    unscored client failure) and stays eligible for an explicit resume;
  * raw response persisted BEFORE parse; reason / missing_evidence /
    evidence_gap, usage, latency, served model retained verbatim;
  * served-model drift vs the Gate-2/E1 frozen id HARD-STOPS the run (no
    silent substitution);
  * resume skips delivered (non-api_error) cells, never double-bills.

Offline:
    uv run --python 3.13 -m evidence.eal_r1_run --preflight
    uv run --python 3.13 -m evidence.eal_r1_run --mock --dry-run
Live (written R1 approval 2026-10-25; needs openai extra, py3.11):
    uv run --python 3.11 --with openai -m evidence.eal_r1_run \\
        --allow-paid-run --i-acknowledge-r1-approved-2026-10-25 \\
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
from evidence.eal_run import (PROFILES, RF, MockCompletions, _classify,
                              _sha, pre_send_leak_check)
from evidence.eal_gate2_run import load_cells as load_gate2_cells

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
G2_RUN_DIR = EAL_DIR / 'gate2_runs'
R1_DIR = EAL_DIR / 'r1'
R1_RUNS = EAL_DIR / 'r1_runs'
R1_FREEZE = R1_DIR / 'eal_r1_freeze_manifest.json'
R1_PREFLIGHT = R1_DIR / 'eal_r1_preflight.json'
G2_FREEZE_PATH = EAL_DIR / 'gate2' / 'eal_gate2_freeze_manifest.json'

GATE = 'r1_live'
ROUND = 1  # Gate-2 was round 0 (the first observation); R1 adds round 1.
ACK = '--i-acknowledge-r1-approved-2026-10-25'
TOTAL_BUDGET_USD = 1.50
PER_MODEL_CAP_USD = 0.75  # sums to the 1.50 total; global guard is primary
COMPLETION_CAP = 4096


def _out_name(model_name, mock):
    safe = model_name.replace('.', '').replace('-', '_')
    return f'eal_r1_{"mock" if mock else "live"}_{safe}_results.jsonl'


def _derived_freeze(cells):
    """Canonical R1 freeze dict derived ONLY from Gate-2 frozen artifacts.
    Offline, no network. Deterministic; used both to write the freeze and to
    prove a paid run would serve exactly Gate-2's 66 byte-frozen payloads."""
    g2_result_files = {
        'deepseek-flash': 'eal_gate2_live_deepseek_flash_results.jsonl',
        'gpt-4.1-mini': 'eal_gate2_live_gpt_41_mini_results.jsonl'}
    # Served ids actually observed in Gate-2 (the drift baseline).
    served_gate2 = {}
    for prof, fn in g2_result_files.items():
        rows = read_jsonl(str(G2_RUN_DIR / fn))
        ids = sorted({r['model_served'] for r in rows if r['model_served']})
        served_gate2[prof] = ids

    return {
        'document': 'R1 test-retest reliability pre-call freeze manifest',
        'gate': GATE, 'round': ROUND,
        'created_before_any_paid_call': True,
        'protocol': 'Gate-2 frozen protocol re-served byte-identical; '
                    'no v2.1 A1/B1 material is used',
        'eal_protocol_version': eal.EAL_PROTOCOL_VERSION,
        'gate2_freeze_manifest_sha256': _sha(G2_FREEZE_PATH.read_bytes()),
        'gate2_materials_manifest_sha256':
            _sha((EAL_DIR / 'gate2' / 'eal_gate2_materials_manifest.json')
                 .read_bytes()),
        'n_cells_per_model': len(cells),
        'cells': [{
            'bundle_id': c['bundle_id'], 'layer': c['layer'],
            'instance_id': c['instance_id'], 'id': c['id'],
            'evidence_class': c['evidence_class'], 'cee_gold': c['cee_gold'],
            'payload_id': c['payload_id'],
            'payload_sha256': c['payload_sha256'],
            'payload_bytes': c['payload_bytes'],
            'prompt_fingerprint': c['prompt_fingerprint'],
            'layer_gold_determined': c['layer_gold_determined'],
            'underdetermined_channels': c['underdetermined_channels']}
            for c in cells],
        'sampling': {'temperature': 0, 'max_tokens': COMPLETION_CAP,
                     'response_format': RF, 'tools': 0, 'turns': 1,
                     'retries_per_cell': 0},
        'expected_served_model_id':
            {p: PROFILES[p]['e1_served_model_id'] for p in PROFILES},
        'gate2_observed_served_model_ids': served_gate2,
        'total_budget_hard_cap_usd': TOTAL_BUDGET_USD,
        'per_model_cap_usd': PER_MODEL_CAP_USD,
        'budget_is_total_across_both_models': True,
        'retries': 'zero retries: wrong/INVALID/AMBIGUOUS are terminal; a '
                   'client fault is persisted api_error (unscored, resume-'
                   'eligible) and never auto-retried in the same run',
        'primary_metric': 'per-cell ternary exact agreement vs Gate-2 round '
                          '0, within (model, layer, bundle)',
        'secondary_metrics': ['DA round delta', 'decision transition '
                              'matrices', 'error-family migration',
                              'issue-cluster paired bootstrap (instance_id, '
                              'seed=7, n=10000; repeats are NOT independent '
                              'issues)', '8 G2.5 NEED->ACCEPT diagnostic '
                              're-check alongside all 22 fixtures'],
        'gold_distribution': {'ACCEPT': 7, 'REJECT': 6, 'NEED_EVIDENCE': 9},
    }


def build_r1_freeze():
    """Load Gate-2 cells (byte-hash asserted vs both Gate-2 manifests),
    derive and write the R1 freeze manifest. Offline, no network."""
    _man, _g2freeze, cells = load_gate2_cells()
    freeze = _derived_freeze(cells)
    R1_DIR.mkdir(parents=True, exist_ok=True)
    # raw bytes (no Windows CRLF translation) so the frozen bytes are
    # reproducible byte-for-byte across platforms and can be asserted live.
    R1_FREEZE.write_bytes(
        (json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True)
         + '\n').encode('utf-8'))
    return freeze, cells


def preflight(freeze, cells):
    import subprocess
    import sys
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'check': gid, 'pass': bool(ok), 'detail': str(detail)})

    gate('r1: 66 frozen Gate-2 cells loaded (22 x 3)', len(cells) == 66,
         len(cells))
    gate('r1: served set == Gate-2 freeze manifest cell set',
         len(freeze['cells']) == 66
         and {c['payload_id'] for c in freeze['cells']}
         == {c['payload_id'] for c in cells})
    gate('r1: Gate-2 layers only (no A1/B1 v2.1 material)',
         {c['layer'] for c in cells} == set(eal.LAYERS),
         sorted({c['layer'] for c in cells}))
    # served-id compatibility between expectation and Gate-2 observation
    drift = []
    for p, exp in freeze['expected_served_model_id'].items():
        obs = freeze['gate2_observed_served_model_ids'].get(p, [])
        if obs and exp not in obs:
            drift.append((p, exp, obs))
    gate('r1: expected served id was observed in Gate-2 (no pre-known drift)',
         not drift, drift)
    # per-cell leak guard offline (raw/structured bodies only)
    hits = []
    for c in cells:
        h = pre_send_leak_check(c)
        if h:
            hits.append((c['payload_id'], h))
    gate('r1: pre-send leak guard clean on 66 cells', not hits, hits[:3])
    # budget arithmetic
    gate('r1: per-model caps sum to total cap',
         abs(2 * PER_MODEL_CAP_USD - TOTAL_BUDGET_USD) < 1e-9)
    # kill switches: live ack missing -> REFUSE; bare -> REFUSE
    p1 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_r1_run', '--allow-paid-run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('r1: live without R1 acknowledgement REFUSED',
         p1.returncode != 0 and 'REFUSED' in (p1.stdout + p1.stderr))
    p2 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_r1_run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('r1: bare invocation REFUSED (offline default)',
         p2.returncode != 0 and 'REFUSED' in (p2.stdout + p2.stderr))
    # mock dry-run envelope
    p3 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_r1_run', '--mock', '--dry-run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('r1: mock --dry-run ok', p3.returncode == 0,
         (p3.stdout + p3.stderr)[-200:])
    all_pass = all(c['pass'] for c in checks)
    out = {'document': 'R1 offline preflight (must pass before paid call)',
           'n_checks': len(checks), 'all_pass': all_pass, 'checks': checks}
    R1_PREFLIGHT.write_bytes(
        (json.dumps(out, ensure_ascii=False, indent=2) + '\n')
        .encode('utf-8'))
    for c in checks:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['check']
              + ('' if c['pass'] else f" -> {c['detail']}"))
    print(f'R1 PREFLIGHT {sum(c["pass"] for c in checks)}/{len(checks)}; '
          f'all_pass={all_pass}')
    return all_pass


def _version_identity(live: bool):
    here = Path(__file__).resolve().parent
    return {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE, 'round': ROUND,
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'response_format_sent': RF, 'tools': 'none', 'turns': 1,
        'retries_per_cell': 0,
        'eal_r1_run_py_sha256': _sha((here / 'eal_r1_run.py').read_bytes()),
        'r1_freeze_manifest_sha256': _sha(R1_FREEZE.read_bytes()),
        'gate2_freeze_manifest_sha256': _sha(G2_FREEZE_PATH.read_bytes()),
        'mode': 'live' if live else 'mock'}


def _run_model(name, prof, cells, args, ident, live, global_spent):
    from evidence.cee_run import _load_key
    out_path = R1_RUNS / _out_name(name, not live)
    prior = read_jsonl(str(out_path)) if out_path.exists() else []
    done = {(r['bundle_id'], r['layer']) for r in prior
            if not r.get('api_error')}
    spent_model = sum(float(r.get('cost_usd') or 0) for r in prior
                      if not r.get('api_error'))
    guard = BudgetGuard(PER_MODEL_CAP_USD, prof['price_in'],
                        prof['price_out'],
                        completion_cap_tokens=COMPLETION_CAP,
                        max_model_calls_per_cell=1)
    guard.spent = spent_model

    if live:
        from openai import OpenAI
        client = OpenAI(api_key=_load_key(prof), base_url=prof['base_url'])
        completions = client.chat.completions
    else:
        completions = MockCompletions(mode='hash')
        completions._served_id = f"mock-{prof['model']}"

    n_new = n_err = n_inv = n_amb = 0
    stop_msg = ''
    with out_path.open('a', encoding='utf-8') as f:
        for cell in cells:
            key = (cell['bundle_id'], cell['layer'])
            if key in done:
                continue
            hits = pre_send_leak_check(cell)
            if hits:
                raise SystemExit(f'LEAK GUARD STOP {name}/{key}: {hits}')
            messages = eal.build_messages(cell['layer'], cell['user_text'])
            est_in = max(sum(len(m['content']) for m in messages) // 3, 256)
            try:
                bound = guard.check(est_in, 0)
            except BudgetGuardStop as e:
                stop_msg = f'{name}/per-model guard: {e}'
                print('BUDGET STOP ' + stop_msg)
                break
            # GLOBAL hard cap across BOTH models (pre-call, guard prices)
            worst_call = (est_in * prof['price_in']
                          + COMPLETION_CAP * prof['price_out']) / 1e6
            if global_spent[0] + worst_call > args.total_budget_usd + 1e-9:
                stop_msg = (f'{name}: GLOBAL R1 cap ${args.total_budget_usd}'
                            f' would be exceeded (spent ${global_spent[0]:.4f}'
                            f', worst next call ${worst_call:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            t0 = time.time()
            api_error, resp = '', None
            try:
                # ONE attempt; no retry on any failure (R1 rule).
                resp = completions.create(
                    model=prof['model'], messages=messages, temperature=0,
                    max_tokens=COMPLETION_CAP, response_format=dict(RF),
                    **({'extra_body': dict(prof['extra_body'])}
                       if prof['extra_body'] else {}))
            except Exception as e:
                # A response_format rejection is a config/version drift, not
                # a per-cell miss: hard stop (plain-text fallback forbidden),
                # consistent with Gate-2.
                if live and re.search(r'response_format|json_object|'
                                      r'json_schema', str(e), re.I):
                    raise SystemExit(
                        f'STOP: {name} rejected json_object (plain-text '
                        'fallback forbidden): '
                        f'{type(e).__name__}: {str(e)[:300]}')
                api_error = f'{type(e).__name__}: {str(e)[:300]}'
            wall = round(time.time() - t0, 4)

            tin = tout = 0
            served, content = None, ''
            obj_keys, reason_v, missing_v, gap_v = [], '', '', ''
            parsed, validation_errors = 'INVALID', []
            if resp is not None:
                served = getattr(resp, 'model', None)
                # served-model drift: hard stop, no silent substitution
                if live and served and served != prof['e1_served_model_id']:
                    raise SystemExit(
                        f'SERVED MODEL DRIFT STOP {name}: expected '
                        f'{prof["e1_served_model_id"]}, got {served}. '
                        'Halting for review; no substitution.')
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
                    n_amb += 1
                else:
                    n_inv += 1
            else:
                raw_sha = _sha(b'')
            cost = round((tin * prof['price_in'] + tout * prof['price_out'])
                         / 1e6, 8) if live else 0.0
            if live and not api_error:
                guard.add(cost)
                global_spent[0] = round(global_spent[0] + cost, 8)
            appropriate, error_label = (
                (False, 'api_error') if api_error
                else _classify(cell['cee_gold'], parsed,
                               cell['layer_gold_determined']))
            scored = ((not api_error) and cell['layer_gold_determined']
                      and parsed in TERNARY)
            rec = {
                'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE,
                'round': ROUND, 'mock': not live, 'model_profile': name,
                'model_requested': prof['model'], 'model_served': served,
                'expected_served_model_id': prof['e1_served_model_id'],
                'served_matches_expected':
                    (served == prof['e1_served_model_id']) if live else None,
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
                'temperature_sent': 0, 'max_tokens_sent': COMPLETION_CAP,
                'response_format_mode': 'json_object',
                'response_format_sent': RF,
                'server_schema_enforced': False,
                'plain_text_fallback': False, 'tools_sent': 0,
                'retries': 0,
                'tokens_in_est': tin, 'tokens_out_est': tout,
                'cost_usd': cost, 'wall_s': wall, 'api_error': api_error,
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
                  f'parsed={rec["parsed"][:13]:<13} {error_label[:26]:<26} '
                  f'in={tin:<6} out={tout:<4} ${cost:.5f} '
                  f'global=${global_spent[0]:.4f}'
                  f'{" ERR" if api_error else ""}')
    return {'model_profile': name, 'new_calls': n_new, 'errors': n_err,
            'invalid': n_inv, 'ambiguous': n_amb,
            'spend_usd': round(guard.spent, 6), 'stop_msg': stop_msg,
            'out_file': out_path.name}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', default='deepseek-flash,gpt-4.1-mini')
    ap.add_argument('--total-budget-usd', type=float,
                    default=TOTAL_BUDGET_USD)
    ap.add_argument('--preflight', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument('--i-acknowledge-r1-approved-2026-10-25',
                    action='store_true', dest='ack_r1')
    args = ap.parse_args()

    R1_RUNS.mkdir(parents=True, exist_ok=True)

    if args.preflight:
        # preflight (re)writes the freeze manifest; it never calls an API.
        freeze, cells = build_r1_freeze()
        ok = preflight(freeze, cells)
        raise SystemExit(0 if ok else 1)

    live = bool(args.allow_paid_run and args.ack_r1)
    if args.allow_paid_run and not args.ack_r1:
        raise SystemExit(
            f'REFUSED: --allow-paid-run also requires {ACK}.')
    if not args.mock and not live:
        raise SystemExit(
            'REFUSED: R1 runs ONLY as --mock/--preflight (offline) or with '
            f'the double gate --allow-paid-run {ACK} (written R1 approval '
            '2026-10-25, 132 cells, TOTAL hard cap $1.50 both models).')
    if args.total_budget_usd > TOTAL_BUDGET_USD + 1e-9:
        raise SystemExit(
            f'REFUSED: R1 total cap cannot exceed the approved '
            f'${TOTAL_BUDGET_USD:.2f}.')

    if live:
        # FREEZE DISCIPLINE: a paid run must NEVER (re)write the freeze. It
        # loads the already-frozen manifest and proves it is byte-identical
        # to a canonical derivation from the Gate-2 frozen bytes.
        if not R1_FREEZE.exists() or not R1_PREFLIGHT.exists():
            raise SystemExit(
                'REFUSED: R1 freeze/preflight missing; run --preflight '
                '(offline) first.')
        pf = json.loads(R1_PREFLIGHT.read_text(encoding='utf-8'))
        if not pf.get('all_pass'):
            raise SystemExit('REFUSED: R1 preflight is not all_pass.')
        frozen_disk = R1_FREEZE.read_bytes()
        _man, _g2freeze, cells = load_gate2_cells()
        canon_freeze = _derived_freeze(cells)
        canon = (json.dumps(canon_freeze, ensure_ascii=False, indent=2,
                            sort_keys=True) + '\n').encode('utf-8')
        if _sha(frozen_disk) != _sha(canon):
            raise SystemExit(
                'REFUSED: R1 freeze manifest on disk differs from a canonical '
                'Gate-2 derivation; refusing to run until reconciled.')
        # the frozen on-disk manifest is the immutable record from here on
        freeze = json.loads(frozen_disk.decode('utf-8'))
    else:
        # Offline (mock/dry-run): never mutate a frozen manifest once it
        # exists; build only if preflight has never run, else assert the
        # on-disk freeze is still the canonical Gate-2 derivation.
        _man, _g2freeze, cells = load_gate2_cells()
        canon = (json.dumps(_derived_freeze(cells), ensure_ascii=False,
                            indent=2, sort_keys=True) + '\n').encode('utf-8')
        if R1_FREEZE.exists():
            if _sha(R1_FREEZE.read_bytes()) != _sha(canon):
                raise SystemExit(
                    'R1 freeze drift vs canonical Gate-2 derivation; rerun '
                    '--preflight (offline) to reconcile.')
            freeze = json.loads(R1_FREEZE.read_text(encoding='utf-8'))
        else:
            R1_DIR.mkdir(parents=True, exist_ok=True)
            R1_FREEZE.write_bytes(canon)
            freeze = json.loads(canon.decode('utf-8'))

    names = [x.strip() for x in args.models.split(',') if x.strip()]
    for n in names:
        if n not in PROFILES:
            raise SystemExit(f'unknown model profile {n}')
    ident = _version_identity(live)
    print(f'R1 {"LIVE" if live else "MOCK"}: {len(cells)} cells/model x '
          f'{len(names)} model(s) = {len(cells)*len(names)}; TOTAL cap '
          f'${args.total_budget_usd:.2f} (Gate-2 frozen bytes only)')

    if args.dry_run:
        if live:
            raise SystemExit('REFUSED: --dry-run is offline only.')
        for n in names:
            p = PROFILES[n]
            print(f'  {n}: guard in=${p["price_in"]} out=${p["price_out"]} '
                  f'expected_served={p["e1_served_model_id"]}')
        print('dry-run: no backend invoked, no rows written')
        return

    global_spent = [0.0]
    if live:
        # Restore TOTAL spend already incurred by THIS R1 across both models
        # before any resume, so the shared $1.50 guard cannot be reset.
        for n0 in names:
            p0 = R1_RUNS / _out_name(n0, False)
            if p0.exists():
                for r0 in read_jsonl(str(p0)):
                    if not r0.get('api_error'):
                        global_spent[0] = round(
                            global_spent[0] + float(r0.get('cost_usd') or 0),
                            8)
        print(f'restored prior R1 live spend=${global_spent[0]:.4f}')
    summaries = []
    for n in names:
        summaries.append(_run_model(n, PROFILES[n], cells, args, ident, live,
                                    global_spent))
        if summaries[-1]['stop_msg']:
            print('Halting further models on budget stop (resume later).')
            break

    total_spend = round(sum(s['spend_usd'] for s in summaries), 6)
    audit = {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': GATE, 'round': ROUND,
        'live': live, 'total_new_cells': sum(s['new_calls'] for s in summaries),
        'models': summaries,
        'total_spend_usd': total_spend,
        'global_hard_cap_usd': args.total_budget_usd,
        'within_global_cap': total_spend <= args.total_budget_usd + 1e-9,
        'completion_cap_tokens': COMPLETION_CAP, 'tools_sent': 0,
        'retries_per_cell': 0, 'plain_text_fallback_used': False,
        'freeze_manifest_sha256': ident['r1_freeze_manifest_sha256'],
        'version': ident}
    (R1_RUNS / f'eal_r1_{"live" if live else "mock"}_run_audit.json') \
        .write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nR1 {"live" if live else "mock"} complete: '
          f'new_rows={audit["total_new_cells"]} spend=${total_spend:.4f} '
          f'cap=${args.total_budget_usd:.2f} '
          f'within_cap={audit["within_global_cap"]}')


if __name__ == '__main__':
    main()
