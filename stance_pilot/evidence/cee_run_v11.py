"""CEE v1.1 live runner - UNIFIED JSON MODE (approved 2026-10-24).

Single turn, no tools, no escalation, ONE valid response per (model, bundle).
Both providers are sent the SAME ``response_format={"type":"json_object"}``;
the five-property schema is enforced LOCALLY (cee_protocol_v11.validate_
decision_object). There is no json_schema request and no plain_text fallback:
if a provider rejects json_object the run HARD-STOPS and reports.

A valid HTTP 200 is scored exactly once - malformed / non-conforming output is
INVALID or AMBIGUOUS, never retried; only a genuine transport/API failure gets
a single technical retry (2s), then is recorded as api_error.

Offline (zero network):
    uv run --python 3.13 -m evidence.cee_run_v11 --mock --dry-run
    uv run --python 3.13 -m evidence.cee_run_v11 --mock

Live (written CEE v1.1 authorisation, hard cap $1.00):
    uv run --python 3.11 --with openai -m evidence.cee_run_v11 \
        --allow-paid-run --max-budget-usd 1.00 --per-model-usd 0.50 \
        --completion-cap 4096
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.ternary import read_jsonl, TERNARY
from evidence import cee_protocol as v1
from evidence import cee_protocol_v11 as cee
from evidence.cee_run import (_load_key, _load_cells, _sha256_bytes,
                              _sha256_file, _classify, CEE_DIR, GOLD_PATH,
                              PLAN_PATH, MANIFEST_PATH)

# A response_format rejection on the unified json_object mode is fatal: the
# amendment forbids both json_schema use and a plain_text downgrade.
_RF_REJECT_RE = re.compile(r'response_format|json_object|json_schema', re.I)

# DeepSeek PEAK list prices are used as conservative guard prices (actual
# billing may be lower off-peak). gpt-4.1-mini prices unchanged from v1.
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in': 0.30, 'price_out': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'out_file': 'cee_v11_deepseek_flash_results.jsonl',
        'e1_served_model_id': 'deepseek-flash',
    },
    'gpt-4.1-mini': {
        'provider': 'openai', 'model': 'gpt-4.1-mini',
        'base_url': 'https://api.openai.com/v1',
        'key_env': 'OPENAI_API_KEY',
        'openai_key_file': str(Path.home() / '.openai_key'),
        'price_in': 0.40, 'price_out': 1.60,
        'extra_body': {},
        'out_file': 'cee_v11_gpt41mini_results.jsonl',
        'e1_served_model_id': 'gpt-4.1-mini-2025-04-14',
    },
}


def _version_identity():
    here = Path(__file__).resolve().parent
    return {
        'protocol': cee.CEE_PROTOCOL_VERSION,
        'predecessor_protocol': cee.PREDECESSOR_VERSION,
        'condition': cee.CEE_CONDITION,
        'prompt_fingerprint_v11': cee.cee_prompt_fingerprint(),
        'prompt_fingerprint_v1_text': v1.cee_prompt_fingerprint(),
        'decision_schema_name': cee.CEE_DECISION_SCHEMA['name'],
        'decision_schema_sha256': _sha256_bytes(
            json.dumps(cee.CEE_DECISION_SCHEMA, sort_keys=True)
            .encode('utf-8')),
        'output_mode': cee.OUTPUT_MODE,
        'response_format_sent': cee.RESPONSE_FORMAT_JSON_OBJECT,
        'server_schema_enforced': False,
        'local_schema_validation': 'cee_protocol_v11.validate_decision_object',
        'plain_text_fallback_permitted': False,
        'cee_gold_sha256': _sha256_file(GOLD_PATH),
        'cee_build_manifest_sha256': _sha256_file(MANIFEST_PATH),
        'cee_plan_sha256': _sha256_file(PLAN_PATH),
        'cee_compatibility_report_sha256':
            _sha256_file(CEE_DIR / cee.COMPATIBILITY_REPORT),
        'cee_protocol_py_sha256': _sha256_file(here / 'cee_protocol.py'),
        'cee_protocol_v11_py_sha256':
            _sha256_file(here / 'cee_protocol_v11.py'),
        'cee_run_v11_py_sha256': _sha256_file(here / 'cee_run_v11.py'),
        'tools': 'none', 'turns': 1,
    }


class _FakeCompletions:
    """Deterministic offline completions in UNIFIED JSON MODE: returns a JSON
    object (no server schema), always five-key conforming so the happy path is
    exercised. Zero network."""

    def __init__(self):
        self.calls = 0

    def create(self, *, model, messages, temperature=None, max_tokens=None,
               response_format=None, extra_body=None):
        self.calls += 1
        text = messages[-1]['content']
        h = int(_sha256_bytes(text.encode('utf-8')).hexdigest(), 16)
        dec = TERNARY[h % 3]
        payload = {'decision': dec, 'reason': 'mock',
                   'evidence_mismatch': dec == 'NEED_EVIDENCE',
                   'missing_evidence': 'mock' if dec == 'NEED_EVIDENCE' else '',
                   'evidence_gap': 'unspecified'
                   if dec == 'NEED_EVIDENCE' else ''}

        class _Choice:
            class _Message:
                content = json.dumps(payload)
            message = _Message()
        return type('_Resp', (), {
            'model': 'mock-model',
            'choices': [_Choice()],
            'usage': type('U', (), {'prompt_tokens': 100,
                                    'completion_tokens': 20})()})()


def _run_model(name, prof, cells, args, ident):
    fname = (f'cee_v11_mock_{name.replace(".", "").replace("-", "_")}_results'
             f'.jsonl' if args.mock else prof['out_file'])
    out_path = CEE_DIR / fname
    prior = read_jsonl(str(out_path)) if out_path.exists() else []
    done = {r['bundle_id'] for r in prior if not r.get('api_error')}
    spent = sum(float(r.get('cost_usd') or 0) for r in prior
                if not r.get('api_error'))
    guard = BudgetGuard(args.per_model_usd, prof['price_in'],
                        prof['price_out'],
                        completion_cap_tokens=args.completion_cap,
                        max_model_calls_per_cell=1)
    guard.spent = spent

    if args.mock:
        completions = _FakeCompletions()
    else:
        from openai import OpenAI
        client = OpenAI(api_key=_load_key(prof), base_url=prof['base_url'])
        completions = client.chat.completions

    rf = dict(cee.RESPONSE_FORMAT_JSON_OBJECT)  # {'type':'json_object'}
    n_new = n_err = 0
    with out_path.open('a', encoding='utf-8') as f:
        for cell in cells:
            r = cell['row']
            bid = r['bundle_id']
            if bid in done:
                continue
            messages = [{'role': 'system', 'content': cee.SYSTEM_MESSAGE},
                        {'role': 'user', 'content': cell['user_text']}]
            est_in = max(
                sum(len(m['content']) for m in messages) // 3, 256)
            try:
                if not args.mock:
                    guard.check(est_in, 0)
            except BudgetGuardStop as e:
                raise SystemExit(f'BUDGET STOP before {name}/{bid}: {e}')

            t0 = time.time()
            api_error = ''
            resp = None
            try:
                kw = dict(model=prof['model'], messages=messages,
                          temperature=0, max_tokens=args.completion_cap,
                          response_format=rf)
                if prof['extra_body']:
                    kw['extra_body'] = dict(prof['extra_body'])
                try:
                    resp = completions.create(**kw)
                except Exception as e:
                    # A response_format rejection is a HARD STOP (no plain-text
                    # fallback permitted). Any other transport error gets ONE
                    # technical retry; a scored response is never retried.
                    if _RF_REJECT_RE.search(str(e)):
                        raise SystemExit(
                            f'STOP: {name} rejected unified json_object mode '
                            f'(plain_text fallback forbidden by CEE v1.1): '
                            f'{type(e).__name__}: {str(e)[:300]}')
                    time.sleep(2)
                    resp = completions.create(**kw)
            except SystemExit:
                raise
            except Exception as e:
                api_error = f'{type(e).__name__}: {str(e)[:300]}'
            wall = round(time.time() - t0, 3)

            tin = tout = 0
            model_served = None
            content = ''
            obj_keys = []
            parsed = 'INVALID'
            validation_errors: list[str] = []
            if resp is not None:
                model_served = getattr(resp, 'model', None)
                u = getattr(resp, 'usage', None)
                if u is not None:
                    tin = int(getattr(u, 'prompt_tokens', 0) or 0)
                    tout = int(getattr(u, 'completion_tokens', 0) or 0)
                content = (resp.choices[0].message.content
                           if getattr(resp, 'choices', None) else '') or ''
                status, decision, validation_errors = \
                    cee.validate_decision_object(content)
                if status == 'ok':
                    parsed = decision
                elif status == 'ambiguous':
                    parsed = 'AMBIGUOUS'
                else:
                    parsed = 'INVALID'
                try:
                    obj_keys = sorted(json.loads(content).keys())
                except Exception:
                    obj_keys = []
            cost = round((tin * prof['price_in']
                          + tout * prof['price_out']) / 1e6, 8)
            if not args.mock and not api_error:
                guard.add(cost)
            appropriate, error_label = (
                (False, 'api_error') if api_error
                else _classify(r['cee_gold'], parsed))
            rec = {
                'protocol': cee.CEE_PROTOCOL_VERSION,
                'condition': cee.CEE_CONDITION,
                'model_profile': name,
                'model_requested': prof['model'],
                'model_served': model_served,
                'e1_served_model_id': prof['e1_served_model_id'],
                'served_matches_e1_model':
                    (model_served == prof['e1_served_model_id'])
                    if model_served is not None else None,
                'bundle_id': bid,
                'scenario': r['scenario'], 'id': r['id'],
                'instance_id': r['instance_id'],
                'served_artifact_id': r['served_artifact_id'],
                'evidence_class': r['evidence_class'],
                'cee_gold': r['cee_gold'],
                'parsed': parsed if not api_error else 'API_ERROR',
                'appropriate': appropriate,
                'error_label': error_label,
                'parseable': parsed in TERNARY and not api_error,
                'local_validation_errors': validation_errors,
                'response_object_keys': obj_keys,
                'raw_content_sha256':
                    _sha256_bytes(content.encode('utf-8')),
                'temperature_sent': 0,
                'max_tokens_sent': args.completion_cap,
                'response_format_mode': 'json_object',
                'response_format_sent': rf,
                'server_schema_enforced': False,
                'schema_downgraded': False,
                'plain_text_fallback': False,
                'extra_body_keys': sorted(prof['extra_body'].keys()),
                'tools_sent': 0,
                'tokens_in': tin, 'tokens_out': tout,
                'cost_usd': cost, 'wall_s': wall,
                'api_error': api_error,
                'bundle_sha256': cell['bundle_sha256'],
                'version': dict(ident),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            n_new += 1
            if api_error:
                n_err += 1
            print(f'{name:<15} {bid} gold={r["cee_gold"]:<13} '
                  f'parsed={rec["parsed"]:<13} {error_label:<38} '
                  f'in={tin:<5} out={tout:<4} ${cost:.5f} '
                  f'cum=${guard.spent:.4f}{" ERR" if api_error else ""}')
    print(f'[{name}] new={n_new} errors={n_err} '
          f'cumulative=${guard.spent:.4f} (per-model cap '
          f'${args.per_model_usd:.2f}) served~={prof["model"]} '
          f'-> {out_path.name}')
    return {'model_profile': name, 'model_requested': prof['model'],
            'new_calls': n_new, 'errors': n_err,
            'spend_usd': round(guard.spent, 6),
            'out_file': prof['out_file']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--models', default='deepseek-flash,gpt-4.1-mini')
    ap.add_argument('--max-budget-usd', type=float, default=1.00)
    ap.add_argument('--per-model-usd', type=float, default=0.50)
    ap.add_argument('--completion-cap', type=int, default=4096)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mock', action='store_true',
                    help='deterministic fake model; zero network/cost')
    ap.add_argument('--allow-paid-run', action='store_true')
    args = ap.parse_args()

    if args.per_model_usd * 2 > args.max_budget_usd + 1e-9:
        raise SystemExit('per-model caps exceed total budget cap')
    cells, manifest = _load_cells()
    ident = _version_identity()
    names = [x.strip() for x in args.models.split(',') if x.strip()]
    for n in names:
        if n not in PROFILES:
            raise SystemExit(f'unknown model profile {n}')

    print(f'CEE {cee.CEE_PROTOCOL_VERSION} (unified json_object): {len(cells)} '
          f'bundles x {len(names)} models = {len(cells) * len(names)} calls; '
          f'mock={args.mock}')
    print(f'prompt_fingerprint_v11={ident["prompt_fingerprint_v11"]}')
    if args.dry_run:
        worst = max((len(cee.SYSTEM_MESSAGE) + len(c['user_text'])) // 3
                    for c in cells)
        for n in names:
            p = PROFILES[n]
            bound = (worst * p['price_in']
                     + args.completion_cap * p['price_out']) / 1e6
            print(f'  {n}: {len(cells)} calls; worst per-call pre-call '
                  f'bound=${bound:.5f}; per-model cap=${args.per_model_usd}')
        print('dry run: no call made')
        return

    if not args.mock and not args.allow_paid_run:
        raise SystemExit(
            'REFUSED: live CEE v1.1 run requires --allow-paid-run plus the '
            'written 2026-10-24 CEE v1.1 authorisation (hard cap $1.00).')

    summaries = []
    for n in names:
        summaries.append(_run_model(n, PROFILES[n], cells, args, ident))
    total = round(sum(s['spend_usd'] for s in summaries), 6)
    audit = {'protocol': cee.CEE_PROTOCOL_VERSION,
             'predecessor_protocol': cee.PREDECESSOR_VERSION,
             'output_mode': cee.OUTPUT_MODE, 'mock': args.mock,
             'models': summaries, 'total_spend_usd': total,
             'hard_cap_usd': args.max_budget_usd,
             'within_cap': total <= args.max_budget_usd + 1e-9,
             'completion_cap_tokens': args.completion_cap,
             'n_bundles': len(cells),
             'n_planned_calls': len(cells) * len(names),
             'tools_sent': 0, 'plain_text_fallback_used': False,
             'version': ident}
    ap_path = CEE_DIR / 'cee_v11_run_audit.json'
    ap_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                       encoding='utf-8')
    print(f'\nCEE v1.1 run complete: total_spend=${total:.4f} '
          f'hard_cap=${args.max_budget_usd:.2f} within_cap='
          f'{audit["within_cap"]} audit={ap_path.name}')


if __name__ == '__main__':
    main()
