"""GroundedReview G4 — Controlled Intervention 144-CELL LIVE RUNNER.

Written authorisation dated 2026-11-02 ("GroundedReview G4"): execute the
FROZEN 18 issues x 4 cells (A/B/C/D) x 2 approved models = 144 REAL cells
(g4-sufficiency-iv-v1.1), one successful sample per planned cell, with a SINGLE
shared hard budget cap of $2.00 total. PROVISIONAL gold only
(annotator2 NOT_OBTAINED); no human gold is fabricated. No git commit.

This runner is NEW and G4-EXCLUSIVE. It never imports, executes or mixes a G3
condition/prompt/tool-server: it CONSUMES the frozen G4 artifacts
(evidence_store_g4_sufficiency/) and re-verifies their hashes before any paid
call; it never regenerates or edits them.

Fixed-presentation design (addendum A5/A6, claim_scope=fixed_presentation_only):
  * per cell the model gets ONE fresh, independent context;
  * it receives the frozen system + first user message, then the frozen ordered
    transcript of 9 scripted tool calls replayed EXACTLY (assistant tool_calls
    + tool results). The live model never chooses a tool, cannot change the
    call path, and there is no HTTP tool server;
  * its ONLY degree of freedom is exactly ONE final paid generation that must
    return the frozen strict ternary JSON decision.

Therefore each planned cell is exactly ONE paid generation. retries=0; a
successful cell is never re-run to improve a result; no fallback model; an
adapter response_format downgrade is a hard ProtocolCapabilityDrift stop.

Hard-stop invariants (checked before any paid call and during the run):
  G1-G6 gate decision == GO; bundle sha256, per-payload hashes, prereg version
  strings, Latin order (seed 20261102) and parent frozen pins all match; served
  model id allow-list; raw-first persistence; independent context per cell;
  pre-call conservative worst-case budget bound before EVERY paid call against
  one shared $2.00 guard; NaN/Inf/negative reported cost poisons the ledger and
  blocks every further call.

Offline ($0):
    uv run --offline --python 3.11 -m evidence.g4_live_run --verify
    uv run --offline --python 3.11 -m evidence.g4_live_run --fingerprint
    uv run --offline --python 3.11 -m evidence.g4_live_run --mock-gate
    uv run --offline --python 3.11 -m evidence.g4_live_run --selftest
Live (needs openai + the DOUBLE gate; max 144 single-call cells, $2 shared):
    uv run --python 3.11 --with openai -m evidence.g4_live_run \\
        --allow-paid-run --i-acknowledge-g4live-144cells-2usd-approved
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

from evidence.ev1_adapters import make_driver
from evidence.phase3_run import BudgetGuard, BudgetGuardStop
from evidence.ternary import parse_ternary_decision, TERNARY_DECISION_SCHEMA
from evidence.cee_run import _load_key
from evidence.g3b3_run import (
    assert_served_model, _live_completions, ProtocolCapabilityDrift,
)
# Frozen G4 build constants / Latin order (imported read-only; the frozen
# jsonl artifacts are the source of truth that actually runs).
from evidence import g4_sufficiency_build as B

HERE = Path(__file__).resolve().parent.parent
G4_STORE = HERE / 'evidence_store_g4_sufficiency'
LIVE_ROOT = HERE / 'evidence_store_g4_live'
OUT_RUNS = LIVE_ROOT / 'runs'
OUT_RAW = LIVE_ROOT / 'raw'
OUT_TRACES = LIVE_ROOT / 'traces'
OUT_FREEZE = LIVE_ROOT / 'freeze'
OUT_FINGERPRINT = OUT_FREEZE / 'g4live_fingerprint.json'

BUNDLES_PATH = G4_STORE / 'g4_fixed_bundles.jsonl'
MANIFEST_PATH = G4_STORE / 'g4_cell_manifest.jsonl'
PAYLOAD_HASH_PATH = G4_STORE / 'g4_payload_hashes.jsonl'
GATE_PATH = G4_STORE / 'g4_identifiability_gate.json'
PREREG_PATH = G4_STORE / 'G4_PREREGISTRATION_v1.md'
ADDENDUM_PATH = G4_STORE / 'G4_PREREGISTRATION_ADDENDUM_v1.1.md'

GATE = 'gate4_controlled_intervention_144cell'
RUNNER_VERSION = 'g4live-runner-v1'
G4_VERSION = B.G4_VERSION                 # g4-sufficiency-iv-v1.1
ORDER_SEED = B.G4_ORDER_SEED             # 20261102
ACK = '--i-acknowledge-g4live-144cells-2usd-approved'

TEMPERATURE = B.TEMPERATURE              # 0
COMPLETION_CAP = B.COMPLETION_CAP        # 8192
RETRIES_PER_CELL = B.RETRIES_PER_CELL    # 0
TOTAL_BUDGET_USD = B.TOTAL_BUDGET_USD    # 2.00 shared across both models
# Exactly ONE paid generation per fixed-presentation cell.
MAX_MODEL_CALLS_PER_CELL = 1

# Frozen served id allow-list and vendor prices (identical to frozen runners).
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'name': 'deepseek-flash',
        'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in_per_1m': 0.30, 'price_out_per_1m': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'completion_param': 'max_tokens',
        'response_format': 'json_object',
        'temperature_supported': True,
        'expected_served_model_id': 'deepseek-flash'},
    'gpt-4.1-mini': {
        'provider': 'openai', 'name': 'gpt-4.1-mini',
        'model': 'gpt-4.1-mini',
        'base_url': 'https://api.openai.com/v1',
        'key_env': 'OPENAI_API_KEY',
        'openai_key_file': str(Path.home() / '.openai_key'),
        'price_in_per_1m': 0.40, 'price_out_per_1m': 1.60,
        'extra_body': {},
        'completion_param': 'max_tokens',
        'response_format': 'json_object',
        'temperature_supported': True,
        'expected_served_model_id': 'gpt-4.1-mini-2025-04-14'},
}
MODELS = B.MODELS
CELLS = B.CELLS

GOLD_STATUS = 'PROVISIONAL; annotator2 NOT_OBTAINED'


# ---------------------------------------------------------------------------
# hashing / canonical
# ---------------------------------------------------------------------------
def _sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def _sha_file(p: Path) -> str:
    return _sha_bytes(p.read_bytes())


def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False).encode('utf-8')


def read_jsonl(p: Path):
    return [json.loads(line) for line in p.read_text(
        encoding='utf-8').splitlines() if line.strip()]


def bundle_content_hash(b: dict) -> str:
    """Must match the builder's manifest bundle_sha256 derivation: sha256 over
    canonical json of (system, user, transcript, tools)."""
    return _sha_text(json.dumps(
        {k: b[k] for k in ('system', 'user', 'transcript', 'tools')},
        sort_keys=True, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Independent pre-run verification of ALL frozen materials (zero API).
# ---------------------------------------------------------------------------
def verify_frozen(*, verbose=True):
    report = {'checks': [], 'failures': []}

    def check(name, ok, detail=''):
        report['checks'].append({'name': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            report['failures'].append(f'{name}: {detail}')
        if verbose:
            print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")

    for p in (BUNDLES_PATH, MANIFEST_PATH, PAYLOAD_HASH_PATH, GATE_PATH,
              PREREG_PATH, ADDENDUM_PATH):
        check(f'file_exists:{p.name}', p.exists(), str(p))

    bundles = read_jsonl(BUNDLES_PATH)
    manifest = read_jsonl(MANIFEST_PATH)
    payload_rows = read_jsonl(PAYLOAD_HASH_PATH)
    gate = json.loads(GATE_PATH.read_text(encoding='utf-8'))

    # counts
    check('bundle_count_72', len(bundles) == 72, f'n={len(bundles)}')
    check('manifest_count_144', len(manifest) == 144, f'n={len(manifest)}')
    check('payload_hash_count_72', len(payload_rows) == 72,
          f'n={len(payload_rows)}')

    # schema / version
    bad_ver = sorted({b.get('g4_version') for b in bundles} - {G4_VERSION})
    check('all_bundle_g4_version', not bad_ver, f'unexpected={bad_ver}')
    bad_schema = [b['instance_id'] for b in bundles
                  if b.get('schema') != 'g4-fixed-bundle-v1.1']
    check('all_bundle_schema', not bad_schema, f'{bad_schema[:3]}')
    bad_mver = [r['serial'] for r in manifest
                if r.get('g4_version') != G4_VERSION]
    check('all_manifest_g4_version', not bad_mver, f'{bad_mver[:3]}')

    # 72 unique issue x cell; 18 issues x 4 cells
    bc = {(b['instance_id'], b['cell']) for b in bundles}
    iids = sorted({b['instance_id'] for b in bundles})
    check('bundle_18_issues', len(iids) == 18, f'n={len(iids)}')
    check('bundle_72_unique_pairs', len(bc) == 72, f'n={len(bc)}')
    for iid in iids:
        cells = {b['cell'] for b in bundles if b['instance_id'] == iid}
        if cells != set(CELLS):
            check(f'four_cells:{iid}', False, f'{sorted(cells)}')
            break
    else:
        check('every_issue_has_ABCD', True)

    # gold status provisional
    bad_gold = [r['serial'] for r in manifest
                if r.get('gold_status') != GOLD_STATUS]
    check('gold_provisional_all_slots', not bad_gold, f'{bad_gold[:3]}')
    # condition gold rules
    bad_cg = [(b['instance_id'], b['cell']) for b in bundles
              if b['condition_gold'] !=
              ('per_oracle' if b['cell'] in ('C', 'D') else 'NEED_EVIDENCE')]
    check('condition_gold_rules', not bad_cg, f'{bad_cg[:3]}')
    # 13/5 strata
    oracle = {b['instance_id']: b['oracle_gold'] for b in bundles}
    n_acc = sum(1 for iid in iids if oracle[iid] == 'ACCEPT')
    n_rej = sum(1 for iid in iids if oracle[iid] == 'REJECT')
    check('strata_13_accept_5_reject', (n_acc, n_rej) == (13, 5),
          f'accept={n_acc} reject={n_rej}')

    # factor levels
    want_factor = {
        'A': ('blocked', 'withheld'), 'B': ('blocked', 'adjudicated'),
        'C': ('presented', 'withheld'), 'D': ('presented', 'adjudicated')}
    bad_f = []
    for b in bundles:
        f = b['factors']
        w = want_factor[b['cell']]
        if (f['O'], f['fc_attestation']) != w or f['linkage'] != \
                'linked_constant':
            bad_f.append((b['instance_id'], b['cell']))
    check('factor_levels_ABCD', not bad_f, f'{bad_f[:3]}')

    # transcript: exactly 9 ordered steps, fixed names/args/status/content_type
    want_steps = [
        ('get_test_artifact', {}, 200, 'application/json'),
        ('verify_artifact_linkage', {}, 200, 'application/json'),
        ('check_evidence_freshness', {}, 200, 'application/json'),
        ('check_test_coverage', {}, 200, 'application/json'),
        ('check_claim_consistency', {'claim': B.CLAIM}, 200,
         'application/json'),
        ('get_run_log', {'name': 'symptom'}, 200, 'text/plain'),
    ]
    bad_t = []
    for b in bundles:
        tr = b['transcript']
        if len(tr) != 9:
            bad_t.append((b['instance_id'], b['cell'], 'len'))
            continue
        for i, st in enumerate(tr):
            if st['step'] != i:
                bad_t.append((b['instance_id'], b['cell'], f'step{i}'))
                break
            if i < 6:
                n, a, s, ct = want_steps[i]
                if (st['name'], st['args'], st['http_status'],
                        st['content_type']) != (n, a, s, ct):
                    bad_t.append((b['instance_id'], b['cell'], f'head{i}'))
                    break
            else:
                nm = ('f2p', 'p2p', 'p2p_baseline')[i - 6]
                presented = b['cell'] in ('C', 'D')
                ws, wct = ((200, 'text/plain') if presented
                           else (403, 'application/json'))
                if (st['name'], st['args'], st['http_status'],
                        st['content_type']) != \
                        ('get_run_log', {'name': nm}, ws, wct):
                    bad_t.append((b['instance_id'], b['cell'], f'log{i}'))
                    break
    check('transcript_9_steps_fixed', not bad_t, f'{bad_t[:3]}')

    # per-payload hashes recompute from the bundle content
    bad_ph = []
    for b in bundles:
        ph = dict(b['payload_hashes'])
        recomputed = {'system': _sha_text(b['system']),
                      'user': _sha_text(b['user']),
                      'tools': _sha_text(json.dumps(
                          b['tools'], sort_keys=True, ensure_ascii=False)),
                      'evidence_block': _sha_text(b['evidence_block'])}
        for st in b['transcript']:
            key = (f"step{st['step']}:{st['name']}:"
                   f"{st['args'].get('name', '')}")
            recomputed[key] = _sha_text(st['body'])
        if ph != recomputed:
            bad_ph.append((b['instance_id'], b['cell']))
    check('payload_hashes_recompute', not bad_ph, f'{bad_ph[:3]}')

    # payload hash file matches bundle
    phm = {(r['instance_id'], r['cell']): r['payload_hashes']
           for r in payload_rows}
    bad_phf = [(b['instance_id'], b['cell']) for b in bundles
               if phm.get((b['instance_id'], b['cell']))
               != b['payload_hashes']]
    check('payload_hash_file_matches_bundle', not bad_phf, f'{bad_phf[:3]}')

    # bundle content hash over system/user/transcript/tools
    content_hash = {(b['instance_id'], b['cell']): bundle_content_hash(b)
                    for b in bundles}

    # manifest: serials unique & contiguous; each slot bundle_sha256 matches;
    # each model x cell appears exactly 18 times
    serials = [r['serial'] for r in manifest]
    check('manifest_serials_0_143', sorted(serials) == list(range(144)),
          f'min={min(serials)} max={max(serials)}')
    bad_mh = []
    from collections import Counter
    slot_counts = Counter((r['model_profile'], r['cell']) for r in manifest)
    for r in manifest:
        if content_hash.get((r['instance_id'], r['cell'])) != \
                r.get('bundle_sha256'):
            bad_mh.append(r['serial'])
    check('manifest_bundle_sha256_all', not bad_mh, f'{bad_mh[:3]}')
    expect_slots = {(m, c) for m in MODELS for c in CELLS}
    check('manifest_8_slots', set(slot_counts) == expect_slots,
          f'{sorted(set(slot_counts))}')
    check('manifest_slot_balance_18',
          set(slot_counts.values()) == {18} and len(slot_counts) == 8,
          f'{dict(slot_counts)}')

    # Latin order equals regenerated frozen order (serial order). The frozen
    # builder iterates issues in cohort order (g3c1 8 then g3a 10); recover the
    # issue-block order independently from the manifest itself (each run of 8
    # consecutive serials is one issue's cyclic Latin block).
    block_iids = []
    block_ok = True
    for b in range(18):
        grp = [r for r in manifest if r['serial'] // 8 == b]
        giids = {r['instance_id'] for r in grp}
        slots = sorted((r['model_profile'], r['cell']) for r in grp)
        if len(giids) != 1 or slots != sorted(expect_slots):
            block_ok = False
            break
        block_iids.append(next(iter(giids)))
    check('manifest_18_latin_blocks_single_issue_each', block_ok)
    regen = B.latin_order(block_iids)
    regen_keys = [(x['serial'], x['model_profile'], x['instance_id'],
                   x['cell']) for x in regen]
    man_keys = [(r['serial'], r['model_profile'], r['instance_id'], r['cell'])
                for r in sorted(manifest, key=lambda r: r['serial'])]
    check('latin_order_seed_20261102', regen_keys == man_keys,
          f'seed={ORDER_SEED}')

    # G1-G6 decision GO
    gates = gate.get('gates', {})
    all_pass = all(gates.get(g, {}).get('pass') is True
                   for g in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6'))
    check('gate_g1_g6_all_pass', all_pass,
          ', '.join(f'{g}={gates.get(g, {}).get("pass")}'
                    for g in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6')))
    check('gate_decision_GO', gate.get('decision') == 'GO',
          str(gate.get('decision')))
    check('gate_zero_api_calls', gate.get('api_calls_made') == 0,
          str(gate.get('api_calls_made')))
    check('stats_plan_locked', gate.get('stats_plan', {}).get('locked')
          is True, str(gate.get('stats_plan', {}).get('locked')))
    check('stats_cap_is_2usd',
          gate.get('stats_plan', {}).get('total_budget_usd_hard_cap')
          == 2.00, str(gate.get('stats_plan', {}).get(
              'total_budget_usd_hard_cap')))

    # preregistration version strings present on disk
    pv = PREREG_PATH.read_text(encoding='utf-8')
    av = ADDENDUM_PATH.read_text(encoding='utf-8')
    check('prereg_v1_marker', 'g4-sufficiency-iv-v1' in pv)
    check('addendum_v1.1_marker', G4_VERSION in av)
    check('addendum_governs', 'this addendum governs' in av.lower())

    # parent frozen pins (truth/gold consumed by the builder) — hashes only.
    pins = {}
    for c in B.COHORTS:
        root = c['root']
        pins[c['tag']] = {
            'truth': _sha_file(root / c['truth']),
            'target_rows': _sha_file(root / c['raw']),
            'oracle_gold': _sha_file(root / c['gold'][0]),
            'freshness_recompute': _sha_file(root / c['restage']),
        }
    report['parent_frozen_pins'] = pins

    report['verified_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                              time.gmtime())
    report['issues'] = iids
    report['ok'] = not report['failures']
    if not report['ok']:
        raise SystemExit('FROZEN VERIFICATION FAILED:\n  '
                         + '\n  '.join(report['failures']))
    if verbose:
        print(f"\nFROZEN VERIFICATION OK: {len(bundles)} bundles, "
              f"{len(manifest)} slots, G1-G6 GO, 13/5 strata, $2 cap.")
    return report, bundles, manifest, gate, pins


# ---------------------------------------------------------------------------
# NaN/Inf-safe shared-total guard (one $2 guard across both models).
# ---------------------------------------------------------------------------
class UntrackableCost(BudgetGuardStop):
    pass


class G4TotalGuard:
    """Wraps the single frozen BudgetGuard at the SHARED $2.00 cap, priced at
    the conservative max in/out price, with the hardened poison ledger. There
    is deliberately NO per-model cap (the authorisation specifies one $2.00
    total only)."""

    def __init__(self):
        pin = max(p['price_in_per_1m'] for p in PROFILES.values())
        pout = max(p['price_out_per_1m'] for p in PROFILES.values())
        self.guard = BudgetGuard(
            TOTAL_BUDGET_USD, pin, pout,
            completion_cap_tokens=COMPLETION_CAP,
            max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)
        self.poisoned = False
        self.poison_reason = None

    @property
    def spent(self):
        return self.guard.spent

    @spent.setter
    def spent(self, v):
        self.guard.spent = v

    @staticmethod
    def safe_cost(cost):
        if cost is None:
            return 0.0
        try:
            c = float(cost)
        except (TypeError, ValueError):
            return None
        if math.isnan(c) or math.isinf(c) or c < 0.0:
            return None
        return c

    def poison(self, raw_cost):
        self.poisoned = True
        self.poison_reason = f'untrackable cost reported: {raw_cost!r}'
        self.guard.spent = self.guard.cap

    def check(self, prompt_tokens_now, cell_calls):
        return self.guard.check(prompt_tokens_now, cell_calls)

    def bound_usd(self, prompt_tokens_now):
        return self.guard.bound_usd(prompt_tokens_now)

    def add(self, cost):
        c = self.safe_cost(cost)
        if c is None:
            self.poison(cost)
            raise UntrackableCost(
                f'{self.poison_reason}; ledger poisoned, halting spend')
        self.guard.add(c)


def safe_resume_spent(v):
    if v is None:
        return 0.0
    c = float(v)
    if math.isnan(c) or math.isinf(c) or c < 0.0:
        raise SystemExit(f'REFUSED: resume ledger has untrackable spent {v!r}')
    return c


# ---------------------------------------------------------------------------
# Yoked fixed-presentation message construction (independent context/cell).
# ---------------------------------------------------------------------------
def yoked_messages(bundle: dict):
    """Build ONE fresh independent context for a cell: system, first user, then
    the frozen 9-step transcript replayed as scripted assistant tool_calls +
    tool results. A new list (and new tool-call ids) is constructed per call so
    nothing can carry over between cells. The model never chooses a tool."""
    messages = [{'role': 'system', 'content': bundle['system']},
                {'role': 'user', 'content': bundle['user']}]
    for st in bundle['transcript']:
        cid = f"call_g4_{st['step']:02d}_{_fresh_token()}"
        messages.append({
            'role': 'assistant', 'content': None,
            'tool_calls': [{'id': cid, 'type': 'function',
                            'function': {
                                'name': st['name'],
                                'arguments': json.dumps(
                                    st['args'], ensure_ascii=False)}}]})
        messages.append({'role': 'tool', 'tool_call_id': cid,
                         'content': st['body']})
    return messages


_NONCE = [0]


def _fresh_token():
    _NONCE[0] += 1
    return f'{_NONCE[0]:08x}'


def est_prompt_tokens(messages):
    n = 0
    for m in messages:
        c = m.get('content')
        if isinstance(c, str):
            n += len(c)
        if m.get('tool_calls'):
            for tc in m['tool_calls']:
                n += len(json.dumps(tc, ensure_ascii=False))
    return max(n // 3, 256)


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------
def _module_sha(name: str) -> str:
    import importlib
    mod = importlib.import_module(name)
    return _sha_file(Path(mod.__file__))


def build_fingerprint(pins):
    fp = {
        'document': 'G4 controlled-intervention 144-cell live PRE-RUN '
                    'fingerprint',
        'gate': GATE,
        'runner_version': RUNNER_VERSION,
        'g4_version': G4_VERSION,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'execution': {
            'design': 'fixed presentation; yoked 9-step transcript replayed; '
                      'exactly ONE paid final generation per cell; model never '
                      'chooses a tool; no HTTP tool server',
            'claim_scope': 'fixed_presentation_only',
            'final_response_format': 'json_schema strict (frozen ternary '
                                     'schema); adapter json_object mapping; '
                                     'any 400-driven downgrade is a hard stop',
            'independent_context_per_cell': True,
            'model_calls_per_cell': MAX_MODEL_CALLS_PER_CELL,
        },
        'frozen_g4_pins': {
            'fixed_bundles': {'path': str(BUNDLES_PATH.relative_to(HERE)),
                              'sha256': _sha_file(BUNDLES_PATH)},
            'cell_manifest': {'path': str(MANIFEST_PATH.relative_to(HERE)),
                              'sha256': _sha_file(MANIFEST_PATH)},
            'payload_hashes': {'sha256': _sha_file(PAYLOAD_HASH_PATH)},
            'identifiability_gate': {'sha256': _sha_file(GATE_PATH)},
            'preregistration_v1': {'sha256': _sha_file(PREREG_PATH)},
            'addendum_v1.1': {'sha256': _sha_file(ADDENDUM_PATH)},
        },
        'parent_frozen_pins': pins,
        'code_hashes': {
            'g4_live_run.py': _module_sha('evidence.g4_live_run'),
            'g4_sufficiency_build.py':
                _module_sha('evidence.g4_sufficiency_build'),
            'ev1_adapters.py': _module_sha('evidence.ev1_adapters'),
            'phase3_run.py': _module_sha('evidence.phase3_run'),
            'ternary.py': _module_sha('evidence.ternary'),
            'cee_run.py': _module_sha('evidence.cee_run'),
            'g3b3_run.py (served-id/live primitives)':
                _module_sha('evidence.g3b3_run'),
        },
        'models': {m: {k: p[k] for k in
                       ('model', 'base_url', 'key_env', 'price_in_per_1m',
                        'price_out_per_1m', 'extra_body', 'completion_param',
                        'response_format', 'expected_served_model_id')}
                   for m, p in PROFILES.items()},
        'sampling': {'temperature': TEMPERATURE,
                     'completion_cap_tokens': COMPLETION_CAP,
                     'retries_per_cell': RETRIES_PER_CELL,
                     'order_seed': ORDER_SEED,
                     'order_design': 'frozen manifest serial order (balanced '
                                     'Latin; strict execution order)'},
        'budget': {
            'total_hard_cap_usd': TOTAL_BUDGET_USD,
            'per_model_cap_usd': None,
            'enforcement': 'single shared guard; pre-call conservative '
                           'worst-case bound (prompt_tokens*max_in + '
                           'completion_cap*max_out)/1e6 checked before EVERY '
                           'paid call; resume restores cumulative spend; '
                           'NaN/Inf/negative cost poisons and blocks'},
        'scope': {'issues': 18, 'cells': 4, 'models': 2, 'planned_slots': 144,
                  'one_successful_sample_per_cell': True,
                  'no_new_issues_models_cells': True,
                  'no_rerun_successful_cell': True,
                  'no_fallback_model': True,
                  'no_response_format_downgrade': True,
                  'no_git_commit': True},
        'gold_status': GOLD_STATUS,
    }
    return fp


def write_fingerprint(pins):
    OUT_FREEZE.mkdir(parents=True, exist_ok=True)
    fp = build_fingerprint(pins)
    OUT_FINGERPRINT.write_bytes(_canon(fp))
    print('fingerprint ->', OUT_FINGERPRINT)
    return fp


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------
def _out_name(model, mock):
    safe = model.replace('.', '').replace('-', '_')
    return f'g4live_{"mock" if mock else "live"}_{safe}_results.jsonl'


def prior_spent_and_done(out_path: Path):
    if not out_path.exists():
        return 0.0, set()
    rows = read_jsonl(out_path)
    spent = sum(float(r.get('cost_usd') or 0) for r in rows if not r.get('mock'))
    # terminal = a landed scored verdict (or a local ScoringError whose paid
    # raw already landed). Pure transport errors are resume-eligible.
    done = {r['serial'] for r in rows
            if not r.get('mock')
            and (not r.get('error')
                 or str(r.get('error')).startswith('ScoringError'))}
    return spent, done


# ---------------------------------------------------------------------------
# One cell acquisition (no scoring inside): yoked transcript + ONE final call.
# ---------------------------------------------------------------------------
def acquire_cell(driver, profile, bundle, wire, *, mock=False, guard=None,
                 mock_decision='NEED_EVIDENCE'):
    messages = yoked_messages(bundle)
    est_in = est_prompt_tokens(messages)
    bound = None
    if not mock and guard is not None:
        bound = guard.check(est_in, 0)  # single-call cell; cell_calls=0
    pre_bound = round(float(bound), 6) if bound is not None else None

    # Scripted stand-in for the offline gate: returns a valid frozen-schema
    # decision object. It exercises the SAME yoked path and adapter mapping.
    if mock:
        from evidence.phase3_run import _Resp
        content = json.dumps(
            {'decision': mock_decision,
             'reason': 'g4 offline mock decision (not a subject)',
             'evidence_mismatch': False}, ensure_ascii=False)
        resp = _Resp(content=content)
        served = profile['model']
        prompt_tokens = est_in
        completion_tokens = 60
        wire_shapes = [dict(c) for c in getattr(wire, 'calls', [])]
    else:
        kw = {profile.get('completion_param', 'max_tokens'): COMPLETION_CAP,
              'response_format': {'type': 'json_schema',
                                  'json_schema': TERNARY_DECISION_SCHEMA}}
        if profile.get('extra_body'):
            kw['extra_body'] = dict(profile['extra_body'])
        n_before = len(getattr(wire, 'calls', []))
        try:
            resp = driver.chat.completions.create(
                model=profile['model'], messages=messages,
                temperature=TEMPERATURE, **kw)
        except Exception:
            # adapter downgrade after a 400 is a hard capability drift
            for c in getattr(wire, 'calls', []):
                if c.get('fallback_from'):
                    raise ProtocolCapabilityDrift(
                        f'response_format capability drift: '
                        f'{c.get("response_format")} (fallback from '
                        f'{c.get("fallback_from")}); halting')
            raise
        for c in getattr(wire, 'calls', [])[n_before:]:
            if c.get('fallback_from'):
                raise ProtocolCapabilityDrift(
                    f'response_format capability drift: '
                    f'{c.get("response_format")} (fallback from '
                    f'{c.get("fallback_from")}); halting')
        served = getattr(resp, 'model', None) or profile['model']
        u = getattr(resp, 'usage', None)
        prompt_tokens = getattr(u, 'prompt_tokens', est_in) if u else est_in
        completion_tokens = getattr(u, 'completion_tokens', 0) if u else 0
        wire_shapes = [dict(c) for c in
                       getattr(wire, 'calls', [])[n_before:]]

    answer_raw = resp.choices[0].message.content or ''
    finish = resp.choices[0].finish_reason

    cost = 0.0 if mock else round(
        (prompt_tokens * profile['price_in_per_1m']
         + completion_tokens * profile['price_out_per_1m']) / 1e6, 6)

    return {
        'protocol': 'ternary-g4-fixed-presentation',
        'g4_version': G4_VERSION,
        'mock': bool(mock),
        'model': profile['model'],
        'model_profile': profile['name'],
        'model_served': served,
        'answer_raw': answer_raw,
        'finish_reason': finish,
        'yoked_steps': len(bundle['transcript']),
        'messages_in_context': len(messages),  # 2 + 9*2 = 20
        'model_calls': 0 if mock else 1,
        'tokens_in_est': est_in,
        'tokens_in': prompt_tokens if not mock else est_in,
        'tokens_out': completion_tokens if not mock else 0,
        'cost_usd': cost,
        'pre_call_worst_case_bound_usd': pre_bound,
        'wire_shapes': wire_shapes,
        'tool_path_fixed': True,
        'tools_inventory_sha256': _sha_text(json.dumps(
            bundle['tools'], sort_keys=True, ensure_ascii=False)),
    }


def score_cell(raw, manifest_row):
    rec = dict(raw)
    parsed = parse_ternary_decision(rec['answer_raw'])
    text = (rec['answer_raw'] or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        obj = {}
    if not isinstance(obj, dict):
        obj = {}
    cell = manifest_row['cell']
    oracle = manifest_row['oracle_gold']
    # Unsupported ACCEPT indicator per preregistration.
    if cell in ('A', 'B'):
        # condition gold NEED for all 18: any ACCEPT is unsupported.
        unsupported_accept = (parsed == 'ACCEPT')
    else:
        # C/D: ACCEPT is unsupported only on oracle-REJECT issues.
        unsupported_accept = (parsed == 'ACCEPT' and oracle == 'REJECT')
    oracle_match = (parsed == oracle) if cell in ('C', 'D') else None
    rec.update({
        'parsed': parsed,
        'reason': obj.get('reason'),
        'evidence_mismatch': obj.get('evidence_mismatch'),
        'missing_evidence': obj.get('missing_evidence'),
        'unsupported_accept': unsupported_accept,
        'oracle_match': oracle_match,
        'audit_oracle_gold': oracle,
        'audit_condition_gold': manifest_row['condition_gold'],
        'gold_tier': 'PROVISIONAL',
        'annotator2': 'NOT_OBTAINED',
        'retries': RETRIES_PER_CELL,
    })
    return rec


# ---------------------------------------------------------------------------
# The run (mock or live)
# ---------------------------------------------------------------------------
def run(*, live: bool, decision_cycle=None):
    verify_report, bundles, manifest, gate, pins = verify_frozen(verbose=True)
    if live and not OUT_FINGERPRINT.exists():
        raise SystemExit('REFUSED: run --fingerprint (pre-run fingerprint) '
                         'before any paid call.')
    bmap = {(b['instance_id'], b['cell']): b for b in bundles}

    OUT_RUNS.mkdir(parents=True, exist_ok=True)
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    OUT_TRACES.mkdir(parents=True, exist_ok=True)

    guard = G4TotalGuard()
    files, done, drivers, wire = {}, {}, {}, {}
    prior_total = 0.0
    for m in MODELS:
        outp = OUT_RUNS / _out_name(m, not live)
        if live:
            spent, dset = prior_spent_and_done(outp)
            spent = safe_resume_spent(spent)
            prior_total += spent
            files[m] = outp.open('a', encoding='utf-8')
            done[m] = dset
            prof = PROFILES[m]
            drv = make_driver(_live_completions(prof), prof)
            drivers[m] = drv
            wire[m] = drv.chat.completions
        else:
            files[m] = outp.open('w', encoding='utf-8')
            done[m] = set()
            drivers[m] = wire[m] = None
    if live:
        guard.spent = round(prior_total, 8)
        print(f'restored prior G4 spend across models=${prior_total:.4f}')

    counts = {m: {'new': 0, 'error': 0, 'skip_done': 0} for m in MODELS}
    stop_msg = ''

    # deterministic mock decision rotation so the offline gate exercises all
    # three parse classes across cells in a fixed, model-symmetric way.
    def mock_choice(serial):
        if decision_cycle:
            return decision_cycle[serial % len(decision_cycle)]
        return ('NEED_EVIDENCE', 'ACCEPT', 'REJECT')[serial % 3]

    try:
        for row in sorted(manifest, key=lambda r: r['serial']):
            serial = row['serial']
            m = row['model_profile']
            prof = PROFILES[m]
            if live and serial in done[m]:
                counts[m]['skip_done'] += 1
                continue
            bundle = bmap[(row['instance_id'], row['cell'])]

            if live and guard.spent >= TOTAL_BUDGET_USD - 1e-12:
                stop_msg = (f'TOTAL cap ${TOTAL_BUDGET_USD:.2f} reached '
                            f'(spent ${guard.spent:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            t0 = time.time()
            error = None
            raw = None
            if live:
                cell_driver, cell_wire = drivers[m], wire[m]
            else:
                cell_driver = make_driver(
                    _MockCompletions(prof, mock_choice(serial)), prof)
                cell_wire = cell_driver.chat.completions
            try:
                raw = acquire_cell(
                    cell_driver, prof, bundle, cell_wire,
                    mock=not live, guard=guard,
                    mock_decision=mock_choice(serial))
            except ProtocolCapabilityDrift:
                raise
            except BudgetGuardStop as bs:
                # pre-call hard stop: no call made; resume-eligible row
                raw = _empty_raw(prof, bundle, guard_stop=str(bs))
                error = f'BudgetGuardStop: {bs}'
            except Exception as e:
                raw = _empty_raw(prof, bundle)
                error = f'{type(e).__name__}: {e}'

            # RAW-FIRST: land the untouched raw record before parse/score.
            raw_record = dict(raw)
            raw_record.update({
                'serial': serial,
                'instance_id': row['instance_id'],
                'cohort': row['cohort'],
                'cell': row['cell'],
                'factors': row['factors'],
                'bundle_sha256': row['bundle_sha256'],
                'expected_served_model_id':
                    prof['expected_served_model_id'],
                'wall_s': round(time.time() - t0, 2),
            })
            raw_path = (OUT_RAW / ('live' if live else 'mock')) / (
                f'{m.replace("-", "_")}__{serial:03d}__'
                f'{row["instance_id"]}__{row["cell"]}.json')
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(
                raw_record, ensure_ascii=False, indent=2, sort_keys=True),
                encoding='utf-8')

            if error is None:
                try:
                    rec = score_cell(raw_record, row)
                except Exception as se:
                    rec = dict(raw_record)
                    rec['parsed'] = None
                    error = f'ScoringError: {type(se).__name__}: {se}'
            else:
                rec = dict(raw_record)
                rec['parsed'] = None
            if error is not None:
                rec['error'] = error
            rec['gate'] = GATE
            rec['runner_version'] = RUNNER_VERSION
            if not live:
                rec['research_excluded'] = True

            # settle cost into the shared guard only after raw is landed.
            if live and not str(error or '').startswith('BudgetGuardStop'):
                guard.add(rec.get('cost_usd'))

            files[m].write(json.dumps(rec, ensure_ascii=False) + '\n')
            files[m].flush()
            counts[m]['new'] += 1
            if error:
                counts[m]['error'] += 1

            # per-cell trace
            tdir = OUT_TRACES / ('live' if live else 'mock')
            tdir.mkdir(parents=True, exist_ok=True)
            (tdir / f'{serial:03d}_{m.replace("-", "_")}__'
                    f'{row["instance_id"]}__{row["cell"]}.json').write_text(
                json.dumps({
                    'serial': serial, 'model': m, 'cell': row['cell'],
                    'instance_id': row['instance_id'],
                    'factors': row['factors'],
                    'yoked_steps': raw_record.get('yoked_steps'),
                    'tool_path_fixed': raw_record.get('tool_path_fixed'),
                    'messages_in_context':
                        raw_record.get('messages_in_context'),
                    'final_answer': raw_record.get('answer_raw', ''),
                    'parsed': rec.get('parsed'),
                    'unsupported_accept': rec.get('unsupported_accept'),
                    'oracle_match': rec.get('oracle_match'),
                    'tokens_in': rec.get('tokens_in'),
                    'tokens_out': rec.get('tokens_out'),
                    'cost_usd': rec.get('cost_usd'),
                    'served_model': rec.get('model_served'),
                    'error': error}, ensure_ascii=False, indent=2),
                encoding='utf-8')

            if live:
                assert_served_model(rec.get('model_served'),
                                    prof['expected_served_model_id'],
                                    f'serial {serial}')
                if str(error or '').startswith('BudgetGuardStop'):
                    stop_msg = f'{m} BudgetGuardStop at serial {serial}: {error}'
                    print('BUDGET STOP ' + stop_msg)
                    break
            print(f'{serial:>3} {m[:3]} {row["cell"]} '
                  f'{row["instance_id"].split("-")[-1]:<6} '
                  f'parsed={str(rec.get("parsed")):<13} '
                  f'U={int(bool(rec.get("unsupported_accept")))} '
                  f'in={rec.get("tokens_in",0):<6} '
                  f'out={rec.get("tokens_out",0):<5} '
                  f'${rec.get("cost_usd",0):.5f} '
                  f'tot=${guard.spent:.4f}'
                  + (' ERR' if error else ''))
    finally:
        for fh in files.values():
            fh.close()

    per_model_spend = {}
    if live:
        for m in MODELS:
            p = OUT_RUNS / _out_name(m, False)
            per_model_spend[m] = round(
                sum(float(r.get('cost_usd') or 0) for r in read_jsonl(p)
                    if not r.get('mock')), 6)

    summary = {
        'gate': GATE, 'mode': 'live' if live else 'mock',
        'runner_version': RUNNER_VERSION, 'g4_version': G4_VERSION,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'planned_slots': 144,
        'new_rows': {m: counts[m]['new'] for m in MODELS},
        'error_rows': {m: counts[m]['error'] for m in MODELS},
        'skipped_already_done': {m: counts[m]['skip_done'] for m in MODELS},
        'per_model_spend_usd': per_model_spend if live else
        {m: 0.0 for m in MODELS},
        'total_spend_usd': round(guard.spent if live else 0.0, 6),
        'total_hard_cap_usd': TOTAL_BUDGET_USD,
        'within_total_cap': (guard.spent <= TOTAL_BUDGET_USD + 1e-9)
        if live else True,
        'model_calls_per_cell': MAX_MODEL_CALLS_PER_CELL,
        'retries_per_cell': RETRIES_PER_CELL,
        'stop_msg': stop_msg,
        'gold_status': GOLD_STATUS,
    }
    auditp = OUT_RUNS / f'g4live_{"live" if live else "mock"}_run_audit.json'
    auditp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print(f'\nG4 {"LIVE" if live else "MOCK"} done: '
          f'new={sum(c["new"] for c in counts.values())} '
          f'total_spend=${summary["total_spend_usd"]:.4f} '
          f'cap=${TOTAL_BUDGET_USD:.2f} within={summary["within_total_cap"]}'
          + (f' STOP: {stop_msg}' if stop_msg else ''))
    print('audit ->', auditp)
    return summary


def _empty_raw(prof, bundle, *, guard_stop=None):
    return {
        'protocol': 'ternary-g4-fixed-presentation', 'g4_version': G4_VERSION,
        'mock': False, 'model': prof['model'],
        'model_profile': prof['name'], 'model_served': None,
        'answer_raw': '', 'finish_reason': None,
        'yoked_steps': len(bundle['transcript']),
        'messages_in_context': 2 + 2 * len(bundle['transcript']),
        'model_calls': 0, 'tokens_in_est': 0, 'tokens_in': 0,
        'tokens_out': 0, 'cost_usd': 0.0,
        'pre_call_worst_case_bound_usd': None, 'wire_shapes': [],
        'tool_path_fixed': True,
        'tools_inventory_sha256': _sha_text(json.dumps(
            bundle['tools'], sort_keys=True, ensure_ascii=False)),
        'pre_call_budget_reason': guard_stop}


# ---------------------------------------------------------------------------
# Offline mock completions
# ---------------------------------------------------------------------------
class _MockCompletions:
    """Stand-in inner completions returning a frozen-schema decision; the
    adapter still maps response_format/extra_body and records wire shapes."""

    def __init__(self, profile, decision):
        self.profile = profile
        self.decision = decision

    def create(self, *, model, messages, temperature=None, **kwargs):
        from evidence.phase3_run import _Resp
        content = json.dumps(
            {'decision': self.decision,
             'reason': 'g4 offline mock decision (not a subject)',
             'evidence_mismatch': False}, ensure_ascii=False)
        return _Resp(content=content)


# ---------------------------------------------------------------------------
# Offline mock gate: full 144-cell yoked path, $0, balanced, raw-first.
# ---------------------------------------------------------------------------
def mock_gate():
    summary = run(live=False)
    rows = []
    for m in MODELS:
        rows.extend((m, r) for r in read_jsonl(OUT_RUNS / _out_name(m, True)))
    n = len(rows)
    balanced = all(summary['new_rows'][m] == 72 for m in MODELS)
    zero_cost = (round(summary['total_spend_usd'], 9) == 0.0
                 and all(round(v, 9) == 0.0
                         for v in summary['per_model_spend_usd'].values()))
    zero_errors = all(summary['error_rows'][m] == 0 for m in MODELS)
    excluded = all(r.get('mock') and r.get('research_excluded')
                   for _, r in rows)
    fixed_path = all(r.get('tool_path_fixed') and r.get('yoked_steps') == 9
                     and r.get('messages_in_context') == 20
                     for _, r in rows)
    parseable = all(r.get('parsed') in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')
                    for _, r in rows)
    # raw files landed for every serial, both models (mock isolated subtree)
    raw_ok = len(list((OUT_RAW / 'mock').glob('*.json'))) == 144
    # all three decisions appear across the rotation
    decs = {r.get('parsed') for _, r in rows}
    ok = (n == 144 and balanced and zero_cost and zero_errors and excluded
          and fixed_path and parseable and raw_ok
          and decs == {'ACCEPT', 'REJECT', 'NEED_EVIDENCE'})
    detail = {'n': n, 'balanced': balanced, 'zero_cost': zero_cost,
              'zero_errors': zero_errors, 'research_excluded': excluded,
              'fixed_9step_path_20msgs': fixed_path, 'parseable': parseable,
              'raw_files': len(list((OUT_RAW / 'mock').glob('*.json'))),
              'decisions_exercised': sorted(decs)}
    OUT_FREEZE.mkdir(parents=True, exist_ok=True)
    (OUT_FREEZE / 'g4live_mock_gate.json').write_text(
        json.dumps({'ok': ok, **detail}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print('MOCK GATE: ' + json.dumps(detail, ensure_ascii=False))
    if not ok:
        raise SystemExit('PRE-PAID MOCK GATE FAILED: '
                         + json.dumps(detail)[:1500])
    return ok


# ---------------------------------------------------------------------------
# Budget guard selftest ($0, no network): single shared $2 guard, poison,
# resume ledger, one-call-per-cell cap.
# ---------------------------------------------------------------------------
def selftest():
    results = []

    def record(name, ok, detail=''):
        results.append({'case': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            raise AssertionError(f'selftest failed: {name} {detail}')

    # 1 None -> 0
    g = G4TotalGuard()
    g.add(None)
    record('none_cost_zero', g.spent == 0.0)
    # 2 accumulation
    g.add(0.0025)
    record('accumulates', abs(g.spent - 0.0025) < 1e-12)
    # 3 NaN poison + block
    try:
        g.add(float('nan'))
    except BudgetGuardStop:
        pass
    blocked = False
    try:
        g.check(1000, 0)
    except BudgetGuardStop:
        blocked = True
    record('nan_poisons_blocks', g.poisoned and blocked)
    # 3b inf / negative
    for bad, label in ((float('inf'), 'inf'), (-0.01, 'negative')):
        g2 = G4TotalGuard()
        raised = after = False
        try:
            g2.add(bad)
        except BudgetGuardStop:
            raised = True
        try:
            g2.check(100, 0)
        except BudgetGuardStop:
            after = True
        record(f'{label}_untrackable', raised and after)
    # 4 single-call-per-cell cap: cell_calls=1 blocks
    g3 = G4TotalGuard()
    blocked1 = False
    try:
        g3.check(1000, 1)
    except BudgetGuardStop:
        blocked1 = True
    record('one_call_per_cell_cap_blocks', blocked1)
    # 5 shared $2 cap reached -> next bound blocked
    g4 = G4TotalGuard()
    g4.spent = TOTAL_BUDGET_USD - 0.0001
    at_cap = False
    try:
        g4.check(1000, 0)
    except BudgetGuardStop:
        at_cap = True
    record('shared_2usd_blocks_at_cap', at_cap)
    # 6 conservative bound: a single biggest call fits at fresh ledger
    g5 = G4TotalGuard()
    b0 = g5.bound_usd(115000)  # bigger than the largest C/D cell (~114.5k)
    record('worst_single_call_bound_sane', 0 < b0 < TOTAL_BUDGET_USD,
           f'bound=${b0:.4f}')
    # and the SAME bound is refused once too little headroom remains
    g5.spent = TOTAL_BUDGET_USD - b0 + 0.001
    refused = False
    try:
        g5.check(115000, 0)
    except BudgetGuardStop:
        refused = True
    record('guard_refuses_overshoot_before_call', refused)
    # 7 resume ledger restore + NaN refusal
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix='g4live_selftest_')
    p = Path(d) / 'rows.jsonl'
    p.write_text('\n'.join(json.dumps(r) for r in [
        {'serial': 0, 'cost_usd': 0.10, 'mock': False},
        {'serial': 1, 'cost_usd': 0.20, 'mock': False},
        {'serial': 2, 'cost_usd': 0.0, 'mock': True},
        {'serial': 3, 'cost_usd': 0.0, 'mock': False,
         'error': 'TransportError: x'},
        {'serial': 4, 'cost_usd': 0.30, 'mock': False,
         'error': 'ScoringError:y'},
        {'serial': 5, 'cost_usd': None, 'mock': False}]) + '\n',
        encoding='utf-8')
    spent, done = prior_spent_and_done(p)
    record('resume_spent', abs(spent - 0.60) < 1e-12, f'spent={spent}')
    record('resume_done', done == {0, 1, 4, 5}, f'done={sorted(done)}')
    nan_refused = False
    try:
        safe_resume_spent(float('nan'))
    except SystemExit:
        nan_refused = True
    record('resume_nan_refused', nan_refused)
    shutil.rmtree(d, ignore_errors=True)
    # 8 caps value
    record('cap_is_single_shared_2usd', TOTAL_BUDGET_USD == 2.00
           and MAX_MODEL_CALLS_PER_CELL == 1)

    out = {'document': 'G4 live runner budget guard self-test ($0)',
           'all_ok': all(r['ok'] for r in results),
           'total_hard_cap_usd': TOTAL_BUDGET_USD,
           'model_calls_per_cell': MAX_MODEL_CALLS_PER_CELL,
           'checks': results}
    OUT_FREEZE.mkdir(parents=True, exist_ok=True)
    (OUT_FREEZE / 'g4live_budget_selftest.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f'BUDGET SELFTEST: {sum(r["ok"] for r in results)}/'
          f'{len(results)} passed; single shared cap $2.00, one call/cell')
    if not out['all_ok']:
        raise SystemExit('budget selftest FAILED')
    return out


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--fingerprint', action='store_true')
    ap.add_argument('--mock-gate', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument(ACK, action='store_true', dest='ack')
    a = ap.parse_args()

    if a.verify:
        verify_frozen()
        return
    if a.selftest:
        selftest()
        return
    if a.fingerprint:
        rep, _, _, _, pins = verify_frozen(verbose=False)
        write_fingerprint(pins)
        return
    if a.mock_gate:
        mock_gate()
        return

    live = bool(a.allow_paid_run and a.ack)
    if a.allow_paid_run and not a.ack:
        raise SystemExit(f'REFUSED: --allow-paid-run also requires {ACK}.')
    if not live:
        raise SystemExit(
            'REFUSED: G4 runs ONLY offline (--verify / --fingerprint / '
            '--mock-gate / --selftest, $0) or with the double gate '
            '--allow-paid-run ' + ACK + ' (144 REAL single-call cells, '
            'TOTAL $2.00 shared, retries 0, PROVISIONAL gold). No call made.')
    run(live=True)


if __name__ == '__main__':
    main()
