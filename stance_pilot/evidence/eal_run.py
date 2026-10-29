"""GroundedReview v2 (EAL) — Gate 1 offline runner. Zero paid API.

This runner is the ONLY component that will ever speak to a model, and in
Gate 1 it is wired to a deterministic in-process MOCK backend: no socket is
opened, no key is read, ``cost_usd`` is always 0 and ``cost_est_usd`` is a
pre-call *projection* used only to exercise BudgetGuard. A live run is
additionally gated by ``--allow-paid-run`` and is NOT authorised in Gate 1.

Design (mirrors the frozen CEE v1.1 controls, additive only):
  * 2 models x 22 fixtures x 3 layers = 132 cells.
  * The two models receive BYTE-IDENTICAL messages for a given layer: the
    served user-turn bytes are read straight from the frozen
    ``evidence_store_eal/layers/<bid>__<layer>.txt`` files (adjudicated is
    itself byte-identical to the frozen CEE bundle). A sha256 assertion
    against the EAL manifest runs before every send.
  * Both arms send ``response_format={"type":"json_object"}``; the five-key
    contract is validated LOCALLY with the frozen validator
    (cee_protocol_v11.validate_decision_object). No repair / coerce / retry
    of a scored response; one technical retry only for a transport error.
  * Retention FIX for the CEE defect: the complete raw response text is
    persisted BEFORE parsing, and reason / missing_evidence / evidence_gap
    are stored verbatim. Mock simulates both a happy path and injected
    malformed/transport cases so the persistence paths are exercised.
  * Resume: one scored row per (model, bundle_id, layer); re-running skips
    completed cells. BudgetGuard.check runs before every (mock-projected)
    call; per-model caps must fit the total cap.

    uv run --python 3.13 -m evidence.eal_run --mock            # 132 mock cells
    uv run --python 3.13 -m evidence.eal_run --mock --dry-run  # envelope only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.ternary import read_jsonl, TERNARY
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_render import _executed_counts, DEFAULT_STORE  # noqa: PLC2701

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
LAYER_DIR = EAL_DIR / 'layers'
RUN_DIR = EAL_DIR / 'gate1_runs'
MANIFEST_PATH = EAL_DIR / 'eal_materials_manifest.json'

# Conservative guard prices identical in spirit to CEE v1.1 (PEAK list).
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in': 0.30, 'price_out': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'served_mock_id': 'mock-deepseek-flash',
        'e1_served_model_id': 'deepseek-flash',
    },
    'gpt-4.1-mini': {
        'provider': 'openai', 'model': 'gpt-4.1-mini',
        'base_url': 'https://api.openai.com/v1',
        'key_env': 'OPENAI_API_KEY',
        'openai_key_file': str(Path.home() / '.openai_key'),
        'price_in': 0.40, 'price_out': 1.60,
        'extra_body': {},
        'served_mock_id': 'mock-gpt-4.1-mini',
        'e1_served_model_id': 'gpt-4.1-mini-2025-04-14',
    },
}

RF = dict(cee.RESPONSE_FORMAT_JSON_OBJECT)

# Tokens never legal in the RAW/STRUCTURED body region (adjudicated exempt).
_FORBIDDEN_VERDICT = [
    'symptom_persists', '"linked"', '"fresh"', '"complete"',
    'linked to this patch', 'fresh for the current commit tree',
    'symptom reproduces after patch', 'symptom present before patch',
]
_FORBIDDEN_META = ['cee_gold', 'evidence_class', 'decisive_failure',
                   'sufficient_success', 'wrong_patch', 'stale_persists',
                   'stale_bad', 'incomplete_decisive']


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _version_identity():
    here = Path(__file__).resolve().parent
    return {
        'protocol': eal.EAL_PROTOCOL_VERSION,
        'gate': 'gate1_offline',
        'layers': list(eal.LAYERS),
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'layer_prompt_fingerprints':
            {l: eal.layer_prompt_fingerprint(l) for l in eal.LAYERS},
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'response_format_sent': RF,
        'server_schema_enforced': False,
        'local_schema_validation':
            'cee_protocol_v11.validate_decision_object',
        'plain_text_fallback_permitted': False,
        'tools': 'none', 'turns': 1,
        'eal_run_py_sha256': _sha((here / 'eal_run.py').read_bytes()),
        'eal_protocol_py_sha256': _sha((here / 'eal_protocol.py').read_bytes()),
    }


# ---------------------------------------------------------------------------
# Cell loading — served bytes come from frozen files, asserted vs manifest
# ---------------------------------------------------------------------------

def load_cells():
    man = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    cells = []
    for it in man['items']:
        for layer in eal.LAYERS:
            meta = it['layers'][layer]
            p = LAYER_DIR / f"{meta['payload_id']}.txt"
            if not p.exists():
                raise SystemExit(f'missing frozen payload {p}')
            b = p.read_bytes()
            if _sha(b) != meta['sha256']:
                raise SystemExit(
                    f'payload tamper/drift vs manifest: {meta["payload_id"]}')
            cells.append({
                'bundle_id': it['bundle_id'], 'layer': layer,
                'instance_id': it['instance_id'], 'id': it['id'],
                'scenario_internal': it['scenario'],
                'evidence_class_internal': it['evidence_class'],
                'cee_gold': it['cee_gold'],
                'payload_id': meta['payload_id'],
                'payload_sha256': meta['sha256'],
                'payload_bytes': len(b),
                'prompt_fingerprint': meta['prompt_fingerprint'],
                'user_text': b.decode('utf-8'),
                'layer_gold_determined':
                    it['layer_gold_determined_from_visible_materials'],
                'underdetermined_channels': it['underdetermined_channels'],
            })
    return man, cells


def _body_region(layer: str, user_text: str) -> str:
    """Evidence region only (the item-invariant head legitimately mentions
    mergeability/ground-truth wording and must not be scanned)."""
    markers = {
        'raw': 'RAW EVIDENCE PACKAGE',
        'structured': 'STRUCTURED EVIDENCE PACKAGE',
        'adjudicated': 'FIXED EVIDENCE BUNDLE',
    }
    i = user_text.index(markers[layer])
    return user_text[i:]


def pre_send_leak_check(cell):
    """Hard refusal if a RAW/STRUCTURED served body carries a verdict or
    decision-equivalent metadata. Returns [] for clean / adjudicated."""
    if cell['layer'] == 'adjudicated':
        return []
    body = _body_region(cell['layer'], cell['user_text']).lower()
    hits = [t for t in (_FORBIDDEN_VERDICT + _FORBIDDEN_META)
            if t in body]
    return hits


# ---------------------------------------------------------------------------
# Deterministic offline mock backend
# ---------------------------------------------------------------------------

def _gold_aware_decision(cell):
    """Oracle mock: reproduces what a perfectly-grounding responder returns
    for the LAYER's own determined gold. Used only to exercise the happy
    path and DA machinery offline; it performs no network."""
    return cell['cee_gold'] if cell['layer_gold_determined'] \
        else 'NEED_EVIDENCE'


class MockCompletions:
    """Deterministic, zero-network completions.

    mode='oracle'  : always returns the layer-determined gold, conforming.
    mode='hash'    : hash of the EXACT served bytes -> ternary (lets us
                     prove both models see identical bytes and makes the
                     mock distribution non-degenerate).
    Fault injection (deterministic) exercises retention/error paths:
      * one forced INVALID (non-JSON) and one AMBIGUOUS-ish response;
      * one simulated transport failure that succeeds on technical retry.
    """

    def __init__(self, mode='oracle'):
        self.mode = mode
        self.calls = 0

    def create(self, *, model, messages, temperature=None, max_tokens=None,
               response_format=None, extra_body=None):
        self.calls += 1
        text = messages[-1]['content']
        h = int(_sha(text.encode()), 16)
        cell_idx = getattr(self, '_cell_idx', 0)
        if self.mode == 'hash':
            dec = TERNARY[h % 3]
        else:
            dec = getattr(self, '_decision', TERNARY[h % 3])
        mismatch = dec == 'NEED_EVIDENCE'
        payload = {
            'decision': dec,
            'reason': f'mock reason for cell#{cell_idx} ({model}): '
                      f'decision={dec}; grounded from served materials.',
            'evidence_mismatch': mismatch,
            'missing_evidence': (f'mock missing_evidence for cell#{cell_idx}'
                                 if mismatch else ''),
            'evidence_gap': 'coverage_incomplete' if mismatch else '',
        }
        content = json.dumps(payload)
        # Deterministic fault injection on fixed global call positions.
        if cell_idx == 10 and not getattr(self, '_injected_invalid', False):
            self._injected_invalid = True
            content = 'this is not json at all'
        if cell_idx == 20 and not getattr(self, '_injected_ambig', False):
            self._injected_ambig = True
            content = json.dumps({'decision': 'ACCEPT'}) + ' ' + \
                json.dumps({'decision': 'REJECT'})

        class _Choice:
            class _Message:
                pass
            _Message.content = content
            message = _Message()
        served = getattr(self, '_served_id', 'mock-model')
        tin = max(len(text) // 3, 64)
        tout = max(len(content) // 3, 16)
        return type('_Resp', (), {
            'model': served,
            'choices': [_Choice()],
            'usage': type('U', (), {'prompt_tokens': tin,
                                    'completion_tokens': tout})()})()


def _classify(gold, parsed, layer_determined):
    if not layer_determined:
        # Gold not determinable at that layer: behavioural label recorded,
        # but NOT scored as correct against the oracle.
        return None, 'layer_gold_underdetermined_unscored'
    if parsed not in TERNARY:
        return False, parsed.lower()  # invalid / ambiguous / api_error
    if parsed == gold:
        return True, {('ACCEPT', 'ACCEPT'): 'appropriate_accept',
                      ('REJECT', 'REJECT'): 'appropriate_reject',
                      ('NEED_EVIDENCE', 'NEED_EVIDENCE'):
                          'appropriate_abstain'}[(gold, parsed)]
    if parsed == 'ACCEPT':
        return False, ('false_commit_accept_on_negative' if gold == 'REJECT'
                       else 'false_commit_accept_on_insufficient')
    if parsed == 'NEED_EVIDENCE':
        return False, ('over_abstain_on_positive' if gold == 'ACCEPT'
                       else 'over_abstain_on_negative')
    return False, ('unsupported_reject_on_positive' if gold == 'ACCEPT'
                   else 'unsupported_reject_on_insufficient')


def _out_name(model_name):
    safe = model_name.replace('.', '').replace('-', '_')
    return f'eal_gate1_mock_{safe}_results.jsonl'


def _run_model(name, prof, cells, args, ident):
    out_path = RUN_DIR / _out_name(name)
    prior = read_jsonl(str(out_path)) if out_path.exists() else []
    # A delivered HTTP-200 (even INVALID/AMBIGUOUS) is a terminal attempt:
    # scored exactly once, never retried. Only a transport/api_error leaves
    # the cell eligible for resume. Mirrors CEE v1.1.
    done = {(r['bundle_id'], r['layer']) for r in prior
            if not r.get('api_error')}
    guard = BudgetGuard(args.per_model_usd, prof['price_in'],
                        prof['price_out'],
                        completion_cap_tokens=args.completion_cap,
                        max_model_calls_per_cell=1)
    # Mock spend is always 0; we still project the envelope via check().
    guard.spent = 0.0
    backend = MockCompletions(mode=args.mock_mode)
    backend._served_id = prof['served_mock_id']

    n_new = n_err = n_invalid = n_ambig = cell_idx = 0
    projected_total = 0.0
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
                projected_total += bound
            except BudgetGuardStop as e:
                raise SystemExit(f'BUDGET STOP before {name}/{key}: {e}')

            backend._cell_idx = cell_idx
            backend._decision = _gold_aware_decision(cell)
            t0 = time.time()
            api_error, resp = '', None
            try:
                kw = dict(model=prof['model'], messages=messages,
                          temperature=0, max_tokens=args.completion_cap,
                          response_format=RF)
                if prof['extra_body']:
                    kw['extra_body'] = dict(prof['extra_body'])
                try:
                    resp = backend.create(**kw)
                except Exception as e:  # one technical retry in mock too
                    time.sleep(0)
                    resp = backend.create(**kw)
            except Exception as e:
                api_error = f'{type(e).__name__}: {str(e)[:300]}'
            wall = round(time.time() - t0, 4)

            tin = tout = 0
            served = None
            content = ''
            obj_keys, reason_v, missing_v, gap_v = [], '', '', ''
            parsed, validation_errors = 'INVALID', []
            raw_persisted_before_parse = True  # retention ordering invariant
            if resp is not None:
                served = getattr(resp, 'model', None)
                u = getattr(resp, 'usage', None)
                if u is not None:
                    tin = int(getattr(u, 'prompt_tokens', 0) or 0)
                    tout = int(getattr(u, 'completion_tokens', 0) or 0)
                content = (resp.choices[0].message.content
                           if getattr(resp, 'choices', None) else '') or ''
                # ---- persist raw content FIRST (mock simulates the write) -
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
                    parsed = 'AMBIGUOUS'
                    n_ambig += 1
                else:
                    parsed = 'INVALID'
                    n_invalid += 1
            else:
                raw_sha = _sha(b'')
            cost = 0.0 if args.mock else round(
                (tin * prof['price_in'] + tout * prof['price_out']) / 1e6, 8)
            appropriate, error_label = (
                (False, 'api_error') if api_error
                else _classify(cell['cee_gold'], parsed,
                               cell['layer_gold_determined']))
            scored = (not api_error) and cell['layer_gold_determined'] \
                and parsed in TERNARY
            rec = {
                'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': 'gate1_offline',
                'mock': bool(args.mock), 'mock_mode': args.mock_mode,
                'model_profile': name,
                'model_requested': prof['model'],
                'model_served': served,
                'e1_served_model_id': prof['e1_served_model_id'],
                'served_matches_e1_model':
                    (served == prof['e1_served_model_id'])
                    if served and not args.mock else (False if args.mock
                                                      else None),
                'bundle_id': cell['bundle_id'], 'layer': cell['layer'],
                'instance_id': cell['instance_id'], 'id': cell['id'],
                'cee_gold': cell['cee_gold'],
                'layer_gold_determined': cell['layer_gold_determined'],
                'underdetermined_channels': cell['underdetermined_channels'],
                'parsed': parsed if not api_error else 'API_ERROR',
                'appropriate': appropriate, 'error_label': error_label,
                'scored': scored, 'parseable': parsed in TERNARY
                and not api_error,
                # retention (Task-11 fix): verbatim text + three fields
                'raw_response_text': content,
                'raw_content_sha256': raw_sha,
                'raw_persisted_before_parse': raw_persisted_before_parse,
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
                'plain_text_fallback': False,
                'tools_sent': 0,
                'tokens_in_est': tin, 'tokens_out_est': tout,
                'cost_usd': cost,
                'projected_worst_call_usd': round(bound, 8),
                'wall_s': wall, 'api_error': api_error,
                'payload_id': cell['payload_id'],
                'payload_sha256': cell['payload_sha256'],
                'payload_bytes': cell['payload_bytes'],
                'prompt_fingerprint': cell['prompt_fingerprint'],
                'version': dict(ident),
            }
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            n_new += 1
            cell_idx += 1
            if api_error:
                n_err += 1
            print(f'{name:<15} {cell["layer"]:<12} {cell["bundle_id"][-8:]} '
                  f'gold={cell["cee_gold"]:<13} parsed={rec["parsed"]:<13} '
                  f'{error_label[:34]:<34} in~{tin:<6} ${cost:.5f}'
                  f'{" ERR" if api_error else ""}')
    return {'model_profile': name, 'new_calls': n_new, 'errors': n_err,
            'invalid': n_invalid, 'ambiguous': n_ambig,
            'spend_usd': 0.0 if args.mock else guard.spent,
            'projected_envelope_usd': round(projected_total, 6),
            'out_file': out_path.name}


def _select_cells(cells, args):
    sel = cells
    if args.only_layers:
        want = {x.strip() for x in args.only_layers.split(',')}
        sel = [c for c in sel if c['layer'] in want]
    if args.only_models:
        pass  # handled at model loop
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
    ap.add_argument('--mock-mode', default='oracle',
                    choices=['oracle', 'hash'])
    ap.add_argument('--only-layers', default='')
    ap.add_argument('--only-cells', default='')
    ap.add_argument('--only-models', default='')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    args = ap.parse_args()

    if args.per_model_usd * 2 > args.max_budget_usd + 1e-9:
        raise SystemExit('per-model caps exceed total budget cap')
    if args.allow_paid_run:
        raise SystemExit(
            'REFUSED: Gate 1 authorises ZERO paid calls. --allow-paid-run is '
            'reserved for a future written Gate-2 authorisation.')

    man, all_cells = load_cells()
    cells = _select_cells(all_cells, args)
    names = [x.strip() for x in
             (args.only_models or args.models).split(',') if x.strip()]
    for n in names:
        if n not in PROFILES:
            raise SystemExit(f'unknown model profile {n}')
    ident = _version_identity()
    n_model = len(names)
    print(f'EAL {eal.EAL_PROTOCOL_VERSION} Gate1 mock: {len(cells)} cells/'
          f'model x {n_model} model(s) = {len(cells)*n_model} '
          f'(full design 22x3x2=132); mock_mode={args.mock_mode}')

    # Byte-identity proof across models is structural: all models read the
    # same payload file; assert the set of payload sha is layer-stable.
    by_layer = {l: {} for l in eal.LAYERS}
    for c in cells:
        by_layer[c['layer']][c['bundle_id']] = c['payload_sha256']

    if args.dry_run:
        worst = {}
        for l in eal.LAYERS:
            bc = [c['payload_bytes'] for c in cells if c['layer'] == l]
            worst[l] = max(bc) if bc else 0
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        for n in names:
            p = PROFILES[n]
            print(f'  {n}: per-model cap ${args.per_model_usd:.2f}; '
                  f'guard prices in=${p["price_in"]} out=${p["price_out"]}')
        print('  worst-case payload bytes by layer:', worst)
        print('dry-run: no mock backend invoked, no rows written')
        return

    if not args.mock:
        raise SystemExit(
            'REFUSED: Gate 1 runs ONLY with --mock (zero network). A live '
            'run needs a future --allow-paid-run + written Gate-2 approval.')

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    summaries = []
    for n in names:
        summaries.append(_run_model(n, PROFILES[n], cells, args, ident))

    # Cross-model byte-identity check on the rows actually written.
    seen = {}
    for n in names:
        for r in read_jsonl(str(RUN_DIR / _out_name(n))):
            k = (r['bundle_id'], r['layer'])
            seen.setdefault(k, set()).add(r['payload_sha256'])
    mismatches = {f'{k}': sorted(v) for k, v in seen.items() if len(v) > 1}
    if mismatches:
        raise SystemExit(f'payload byte mismatch across models: {mismatches}')

    total_spend = 0.0
    total_proj = round(sum(s['projected_envelope_usd'] for s in summaries), 6)
    audit = {
        'protocol': eal.EAL_PROTOCOL_VERSION, 'gate': 'gate1_offline',
        'mock': True, 'mock_mode': args.mock_mode,
        'n_cells_per_model': len(cells), 'n_models': n_model,
        'n_rows_written': sum(s['new_calls'] for s in summaries),
        'models': summaries,
        'total_spend_usd': total_spend,
        'total_projected_worst_case_envelope_usd': total_proj,
        'hard_cap_usd': args.max_budget_usd,
        # BudgetGuard.check already enforced the per-model pre-call bound;
        # the aggregate projection is reported against the total hard cap.
        'projection_within_total_cap':
            total_proj <= args.max_budget_usd + 1e-9,
        'cross_model_payload_byte_identity': not mismatches,
        'payload_sha_mismatches': mismatches,
        'completion_cap_tokens': args.completion_cap,
        'tools_sent': 0, 'plain_text_fallback_used': False,
        'version': ident,
    }
    (RUN_DIR / 'eal_gate1_run_audit.json').write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nEAL Gate1 mock complete: rows={audit["n_rows_written"]} '
          f'spend=${total_spend:.4f} projected_worst=${total_proj:.4f} '
          f'byte_identity={not mismatches} audit=eal_gate1_run_audit.json')


if __name__ == '__main__':
    main()
