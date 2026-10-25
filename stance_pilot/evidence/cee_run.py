"""CEE live runner (Controlled Evidence Experiment).

Single-turn, no tools, no escalation. Both providers receive the exact
on-disk bundle bytes with the SAME strict json_schema. A response_format
rejection is a HARD STOP (never downgraded to json_object/plain_text), per
the 2026-10-23 authorisation.

Offline check (zero network):
    uv run --python 3.13 -m evidence.cee_run --mock --dry-run
    uv run --python 3.13 -m evidence.cee_run --mock

Live (requires explicit approval flag):
    uv run --python 3.11 --with openai -m evidence.cee_run --allow-paid-run \
        --max-budget-usd 1.00 --per-model-usd 0.50 --completion-cap 4096
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.schemas import canonical_dumps
from evidence.ternary import read_jsonl, parse_ternary_decision, TERNARY
from evidence import cee_protocol as cee
from evidence.cee_build import DEFAULT_OUT

CEE_DIR = DEFAULT_OUT
BUNDLES_DIR = CEE_DIR / 'bundles'
GOLD_PATH = CEE_DIR / 'cee_gold.jsonl'
PLAN_PATH = CEE_DIR / 'cee_plan.json'
MANIFEST_PATH = CEE_DIR / 'cee_build_manifest.json'

# CEE-specific wire profiles (both strict schema, single turn). Prices frozen.
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in': 0.30, 'price_out': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'out_file': 'cee_deepseek_flash_results.jsonl',
    },
    'gpt-4.1-mini': {
        'provider': 'openai', 'model': 'gpt-4.1-mini',
        'base_url': 'https://api.openai.com/v1',
        'key_env': 'OPENAI_API_KEY',
        'openai_key_file': str(Path.home() / '.openai_key'),
        'price_in': 0.40, 'price_out': 1.60,
        'extra_body': {},
        'out_file': 'cee_gpt41mini_results.jsonl',
    },
}

_RF_RE = re.compile(r'response_format|json_schema|400|invalid', re.I)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: Path):
    return _sha256_bytes(path.read_bytes()) if path.exists() else None


def _load_key(prof):
    key = os.environ.get(prof['key_env'])
    if not key and prof.get('openai_key_file'):
        kp = Path(prof['openai_key_file'])
        if kp.exists():
            key = kp.read_text(encoding='utf-8').strip()
    if not key:
        raise SystemExit(f"missing API key for {prof['provider']} "
                         f"({prof['key_env']})")
    return key


def _load_cells():
    rows = read_jsonl(str(GOLD_PATH))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    sha_by_id = {b['bundle_id']: b['bundle_sha256']
                 for b in manifest['bundles']}
    cells = []
    for r in rows:
        bid = r['bundle_id']
        path = BUNDLES_DIR / f'{bid}.txt'
        if not path.exists():
            raise SystemExit(f'missing bundle file {path}')
        raw = path.read_bytes()
        if _sha256_bytes(raw) != sha_by_id[bid]:
            raise SystemExit(f'bundle sha mismatch on disk: {bid}')
        cells.append({'row': r, 'path': path, 'user_text': raw.decode('utf-8'),
                      'bundle_sha256': sha_by_id[bid]})
    return cells, manifest


def _version_identity():
    here = Path(__file__).resolve().parent
    return {
        'protocol': cee.CEE_PROTOCOL_VERSION,
        'condition': cee.CEE_CONDITION,
        'prompt_fingerprint': cee.cee_prompt_fingerprint(),
        'decision_schema_name': cee.CEE_DECISION_SCHEMA['name'],
        'decision_schema_sha256': _sha256_bytes(
            canonical_dumps(cee.CEE_DECISION_SCHEMA).encode('utf-8')),
        'cee_gold_sha256': _sha256_file(GOLD_PATH),
        'cee_build_manifest_sha256': _sha256_file(MANIFEST_PATH),
        'cee_plan_sha256': _sha256_file(PLAN_PATH),
        'cee_protocol_py_sha256': _sha256_file(here / 'cee_protocol.py'),
        'cee_build_py_sha256': _sha256_file(here / 'cee_build.py'),
        'cee_run_py_sha256': _sha256_file(here / 'cee_run.py'),
        'tools': 'none', 'turns': 1,
        'response_format': 'json_schema strict; no downgrade permitted',
    }


def _classify(gold, parsed):
    if parsed not in TERNARY:
        return False, parsed  # INVALID / AMBIGUOUS
    if parsed == gold:
        label = {('ACCEPT', 'ACCEPT'): 'appropriate_accept',
                 ('REJECT', 'REJECT'): 'appropriate_reject',
                 ('NEED_EVIDENCE', 'NEED_EVIDENCE'):
                     'appropriate_abstain'}[(gold, parsed)]
        return True, label
    # errors
    if parsed == 'ACCEPT':
        label = ('false_commit_accept_on_negative' if gold == 'REJECT'
                 else 'false_commit_accept_on_insufficient')
    elif parsed == 'NEED_EVIDENCE':
        label = ('over_abstain_on_positive' if gold == 'ACCEPT'
                 else 'over_abstain_on_negative')
    else:  # REJECT
        label = ('unsupported_reject_on_positive' if gold == 'ACCEPT'
                 else 'unsupported_reject_on_insufficient')
    return False, label


class _FakeCompletions:
    """Deterministic offline completions; returns the gold decision wrapped
    in a schema-conforming object. Zero network."""

    def __init__(self):
        self.calls = 0

    def create(self, *, model, messages, temperature=None, max_tokens=None,
               response_format=None, extra_body=None):
        self.calls += 1
        text = messages[-1]['content']
        # echo the gold keyword present in the on-disk bundle metadata? No
        # labels are served; fake instead cycles deterministically by hash so
        # the write/parse/classify path is exercised across all three labels.
        h = int(hashlib.sha256(text.encode('utf-8')).hexdigest(), 16)
        dec = TERNARY[h % 3]
        payload = {'decision': dec, 'reason': 'mock',
                   'evidence_mismatch': dec == 'NEED_EVIDENCE',
                   'missing_evidence': 'mock' if dec == 'NEED_EVIDENCE' else '',
                   'evidence_gap': 'unspecified'
                   if dec == 'NEED_EVIDENCE' else ''}

        class _Msg:
            content = json.dumps(payload)
            model = 'mock-model'
            usage = type('U', (), {'prompt_tokens': 100,
                                   'completion_tokens': 20})()
        return _Msg()


def _run_model(name, prof, cells, args, ident):
    fname = (f'cee_mock_{name.replace(".", "").replace("-", "_")}_results.jsonl'
             if args.mock else prof['out_file'])
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
        client = type('C', (), {})()
        completions = _FakeCompletions()
    else:
        from openai import OpenAI
        client = OpenAI(api_key=_load_key(prof), base_url=prof['base_url'])
        completions = client.chat.completions

    strict_obj = {'type': 'json_schema',
                  'json_schema': cee.CEE_DECISION_SCHEMA}
    n_new = n_err = 0
    schema_rejected = False
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
                          response_format=strict_obj)
                if prof['extra_body']:
                    kw['extra_body'] = dict(prof['extra_body'])
                try:
                    resp = completions.create(**kw)
                except Exception as e:
                    # Authorisation: schema rejection is a HARD STOP; any
                    # other transport error gets ONE retry, then is recorded.
                    if _RF_RE.search(str(e)):
                        schema_rejected = True
                        raise SystemExit(
                            f'STOP: {name} rejected the strict json_schema '
                            f'(no downgrade permitted): '
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
            if resp is not None:
                model_served = getattr(resp, 'model', None)
                u = getattr(resp, 'usage', None)
                if u is not None:
                    tin = int(getattr(u, 'prompt_tokens', 0) or 0)
                    tout = int(getattr(u, 'completion_tokens', 0) or 0)
                content = resp.content or ''
                parsed = parse_ternary_decision(content)
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
                'response_object_keys': obj_keys,
                'raw_content_sha256': _sha256_bytes(content.encode('utf-8')),
                'temperature_sent': 0,
                'max_tokens_sent': args.completion_cap,
                'response_format_mode': 'json_schema_strict',
                'schema_downgraded': False,
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
          f'${args.per_model_usd:.2f}) -> {out_path.name}')
    return {'model_profile': name, 'new_calls': n_new, 'errors': n_err,
            'spend_usd': round(guard.spent, 6),
            'out_file': prof['out_file'], 'schema_rejected': schema_rejected}


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

    print(f'CEE {cee.CEE_PROTOCOL_VERSION}: {len(cells)} bundles x '
          f'{len(names)} models = {len(cells) * len(names)} calls; '
          f'mock={args.mock}')
    print(f'prompt_fingerprint={ident["prompt_fingerprint"]}')
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
            'REFUSED: live CEE run requires --allow-paid-run plus written '
            'authorisation (approved 2026-10-23, hard cap $1.00).')

    summaries = []
    for n in names:
        summaries.append(_run_model(n, PROFILES[n], cells, args, ident))
    total = round(sum(s['spend_usd'] for s in summaries), 6)
    audit = {'protocol': cee.CEE_PROTOCOL_VERSION, 'mock': args.mock,
             'models': summaries, 'total_spend_usd': total,
             'hard_cap_usd': args.max_budget_usd,
             'within_cap': total <= args.max_budget_usd + 1e-9,
             'completion_cap_tokens': args.completion_cap,
             'n_bundles': len(cells), 'version': ident}
    ap_path = CEE_DIR / 'cee_run_audit.json'
    ap_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False),
                       encoding='utf-8')
    print(f'\nCEE run complete: total_spend=${total:.4f} '
          f'hard_cap=${args.max_budget_usd:.2f} within_cap='
          f'{audit["within_cap"]} audit={ap_path.name}')


if __name__ == '__main__':
    main()
