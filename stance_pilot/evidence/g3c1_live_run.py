"""GroundedReview G3-C.1 EXPLORATORY 80-CELL LIVE RUNNER (independent, new).

Written authorisation dated 2026-10-29 ("Workflow B"): execute AT MOST 80 REAL
Reviewer cells = the 8 FROZEN G3-C.1 independent SymPy issues x 2 approved
models x the 5 frozen evidence conditions, as an EXPLORATORY INDEPENDENT-ISSUE
VALIDATION under PROVISIONAL gold (annotator2 = NOT_OBTAINED). This is NOT a
human-arbitrated external benchmark.

This runner is NEW and INDEPENDENT. It never edits, overwrites or re-runs:
  * the frozen G3-B.3 runner/results (its hardwired 10 g3a issues + $3/$1.50),
  * the frozen G3-C.1 store/gold/freeze trees (read / tempdir-copy only).
It REUSES the frozen, already-audited execution primitives by import:
  * acquire_cell / score_cell / served-id drift / resume / live completions
    come from evidence.g3b3_run UNCHANGED;
  * the evidence server is evidence.g3c1_server (projection v2, 3-state
    freshness) on an ISOLATED tempdir COPY of the frozen G3-C.1 store;
  * prompts are evidence.g3b2_prompts (p3-ternary-g3b2-v1);
  * guards are the frozen phase3_run.BudgetGuard, composed per-model + a
    SINGLE shared total guard, but armed at THIS authorisation's caps.

Hard caps (the 2026-10-29 authorisation; NOT the historical $3.00/$1.50):
    TOTAL $2.00 across both models; $1.00 per model.
A conservative pre-call worst-case bound is enforced before EVERY paid call by
both the per-model guard and the shared total guard. Resume restores cumulative
spend. retries_per_cell = 0; a successful cell is never re-run to improve a
result; there is no fallback model and no response_format downgrade.

NaN / Inf / negative reported costs are UNTRACKABLE: the ledger is poisoned
(the remaining headroom is forced to zero) and every further paid call is
blocked (G3C1Guard.add -> BudgetGuardStop). None / missing cost is coerced to
0.0 exactly like the frozen runner. This is proven by --selftest and is part
of the mandatory pre-paid gate.

The ONLY tree this module writes is evidence_store_g3c1_live/ (raw/, traces/,
runs/, freeze/). On a complete 80-cell live run it additionally EMITS (never
reads for scoring) paper_sprint/experiment80/RESULTS_REAL.json, the single path
the pre-registered analyser consumes.

Offline ($0; 80 scripted cells over the real g3c1 server, research-excluded):
    uv run --offline --python 3.11 -m evidence.g3c1_live_run --mock
Budget guard self-test ($0, no network):
    uv run --offline --python 3.11 -m evidence.g3c1_live_run --selftest
Live (needs openai + the DOUBLE gate; max 80 cells, $2/$1):
    uv run --python 3.11 --with openai -m evidence.g3c1_live_run \\
        --allow-paid-run --i-acknowledge-g3c1live-80cells-2usd-approved
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

from evidence.ev1_adapters import make_driver
from evidence.phase3_run import (
    BudgetGuard, BudgetGuardStop, P3Client, ScriptedModel,
)
from evidence.prompts import ternary_tools, ternary_condition_tier_policy
from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.views import display_for_tier
from evidence.visibility import project_surface
from evidence.ternary import _executed_counts
from evidence.g3c0_projection_v2 import project_diagnostic_v2

# Reuse the frozen, audited live primitives verbatim (no copy-edit).
from evidence.g3b3_run import (
    CompositeGuard as _FrozenCompositeGuard,
    acquire_cell, score_cell, assert_served_model,
    _prior_spent_and_done, _live_completions, ProtocolCapabilityDrift,
)
from evidence import g3b2_prompts as GP
from evidence import g3c1_common as GC
from evidence import g3c1_server as GS

# ---------------------------------------------------------------------------
# This run's constants (independent from g3b3_common's $3.00/$1.50).
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent.parent
LIVE_ROOT = HERE / 'evidence_store_g3c1_live'
OUT_RUNS = LIVE_ROOT / 'runs'
OUT_RAW = LIVE_ROOT / 'raw'
OUT_TRACES = LIVE_ROOT / 'traces'
OUT_FREEZE_DIR = LIVE_ROOT / 'freeze'
OUT_FINGERPRINT = OUT_FREEZE_DIR / 'g3c1live_fingerprint.json'
RESULTS_REAL = (HERE / 'paper_sprint' / 'experiment80' / 'RESULTS_REAL.json')

GATE = 'gate3c1_exploratory_80cell_validation'
RUNNER_VERSION = 'g3c1live-runner-v1'
# The executed prompt/protocol/gold-cert are the frozen G3-B.2 / G3-C.1 ones.
RUN_PROMPT_VERSION = 'p3-ternary-g3b2-v1'
RUN_PROTOCOL_VERSION = GC.G3C1_PROTOCOL_VERSION          # g3c1-protocol-v1
RUN_GOLD_CERT_VERSION = GC.G3C1_GOLD_CERT_VERSION        # g3c1-gold-cert-v1
PROJECTION_VERSION = GC.PROJECTION_V2_VERSION

# The 2026-10-29 authorisation caps (deliberately distinct from g3b3).
TOTAL_BUDGET_USD = 2.00
PER_MODEL_CAP_USD = 1.00

# Frozen sampling parameters (identical values to the frozen runners).
TEMPERATURE = 0
COMPLETION_CAP = 8192
MAX_TOOL_TURNS = 8
MAX_MODEL_CALLS_PER_CELL = 12
RETRIES_PER_CELL = 0
# NEW fixed interleaving seed, distinct from g3b (7), g3b3 (313) and the g3c1
# construction/analysis seeds.
ORDER_SEED = 418401

# The 8 frozen G3-C.1 issues, model order, served id allow-list and prices.
MODELS = ('deepseek-flash', 'gpt-4.1-mini')
ACK = '--i-acknowledge-g3c1live-80cells-2usd-approved'

# Vendor profiles: identical prices/base/extra_body/served ids to the frozen
# G3-B.3 profiles, but the per-model cap is THIS authorisation's $1.00.
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
        'tool_calling_supported': True,
        'temperature_supported': True,
        'expected_served_model_id': 'deepseek-flash',
        'per_model_cap_usd': PER_MODEL_CAP_USD,
    },
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
        'tool_calling_supported': True,
        'temperature_supported': True,
        'expected_served_model_id': 'gpt-4.1-mini-2025-04-14',
        'per_model_cap_usd': PER_MODEL_CAP_USD,
    },
}

GOLD_AUTHORITY = dict(GC.GOLD_AUTHORITY)
RESEARCH_KIND = 'Exploratory Independent-Issue Validation (PROVISIONAL gold; ' \
                'annotator2 NOT_OBTAINED; not a human-arbitrated benchmark)'


# ---------------------------------------------------------------------------
# NaN/Inf-safe composite guard (frozen guards composed, add() hardened here).
# ---------------------------------------------------------------------------
class UntrackableCost(BudgetGuardStop):
    """A reported cost was NaN/Inf/negative and cannot be accounted for."""


class G3C1Guard(_FrozenCompositeGuard):
    """Composite per-model + shared-total guard at $1.00 / $2.00, with a
    hardened ledger: None/missing cost -> 0.0 (as frozen); NaN/Inf/negative is
    untrackable -> POISON the ledger (force both caps to their limit) and stop
    immediately, so no further paid call can ever leak past the cap."""

    def __init__(self, model_cap, total_guard, pin, pout, *,
                 completion_cap_tokens=COMPLETION_CAP,
                 max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL):
        super().__init__(model_cap, total_guard, pin, pout,
                         completion_cap_tokens=completion_cap_tokens,
                         max_model_calls_per_cell=max_model_calls_per_cell)
        self.poisoned = False
        self.poison_reason = None

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
        # Force every remaining pre-call bound to fail; never silently reset.
        self.poisoned = True
        self.poison_reason = f'untrackable cost reported: {raw_cost!r}'
        self.model_guard.spent = self.model_guard.cap
        self.total_guard.spent = self.total_guard.cap

    def add(self, cost):
        c = self.safe_cost(cost)
        if c is None:
            self.poison(cost)
            raise UntrackableCost(
                f'{self.poison_reason}; ledger poisoned, halting spend')
        super().add(c)


def safe_resume_spent(v):
    """Resume restore must never accept a NaN/Inf ledger (that would disable
    the cap). None/non-numeric -> 0.0; NaN/Inf/negative -> hard refusal."""
    if v is None:
        return 0.0
    c = float(v)
    if math.isnan(c) or math.isinf(c) or c < 0.0:
        raise SystemExit(f'REFUSED: resume ledger has untrackable spent {v!r}')
    return c


# ---------------------------------------------------------------------------
# G3-C.1 item construction (40 issue-condition items, shared by both models).
# ---------------------------------------------------------------------------
def build_items():
    store = ArtifactStore(str(GC.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')
    raws = {r['instance_id']: r
            for r in GC.read_jsonl(GC.OUT_RAW / 'g3c1_target_rows.jsonl')}
    truths = {t['instance_id']: t for t in GC.read_jsonl(GC.TRUTH)}
    oracles = {o['instance_id']: o
               for o in GC.read_jsonl(GC.OUT_GOLD / 'g3c1_oracle_gold.jsonl')}
    certs = {(c['instance_id'], c['condition']): c
             for c in GC.read_jsonl(
                 GC.OUT_GOLD / 'g3c1_condition_certificates.jsonl')}

    items = []
    iids = sorted(raws)
    if len(iids) != 8:
        raise SystemExit(f'expected 8 frozen g3c1 issues, got {len(iids)}')
    for iid in iids:
        raw, truth, oracle = raws[iid], truths[iid], oracles[iid]
        patch = truth['patch_sha256']
        aid = make_artifact_id(iid, patch)
        got = store.get(aid)
        if got is None:
            raise SystemExit(f'missing authenticatable artifact {aid}')
        rec, authentic = got
        if not authentic:
            raise SystemExit(f'inauthentic artifact signature for {iid}')
        lp = truth.get('label_provenance', {})
        symptom = {'pre_patch_passed': lp.get('symptom_pre_patch_passed'),
                   'post_patch_passed': lp.get('symptom_post_patch_passed')}
        facts = oracle['facts']
        pres_a = display_for_tier(store, rec, iid, patch, 'A')
        pf, pe = _executed_counts(pres_a)
        bundle = {
            'linked': facts['linked'],
            'fresh': facts['fresh'],
            'fresh_state_repaired': facts['fresh_state_authoritative'],
            'complete': facts['complete'],
            'executed_failure_count': facts['executed_failure_count'],
            'executed_check_count': facts['executed_check_count'],
            'symptom_polarity': facts['symptom_polarity'],
            'presented_a_record': pres_a,
            'presented_failure_count': pf,
            'presented_check_count': pe,
        }
        for cond in GC.CONDITIONS:
            _active, tier, _policy = ternary_condition_tier_policy(cond)
            disp = display_for_tier(store, rec, iid, patch, tier)
            # G3-C.1 projection v2: tier-D served content has the redundant
            # pass_to_pass_baseline map removed; tier A is byte-for-byte.
            artifact_record = project_diagnostic_v2(disp) if tier == 'D' \
                else disp
            cert = certs[(iid, cond)]
            items.append({
                'id': raw['id'], 'instance_id': iid, 'repo': raw.get('repo'),
                'base_commit': truth['base_commit'], 'patch_sha256': patch,
                'issue': raw['problem_statement'],
                'patch': raw['model_patch'],
                'condition': cond, 'served_artifact_id': aid,
                'claim': 'This fix is correct and all relevant tests pass.',
                'with_claim': True, 'symptom': symptom,
                'evidence_tier': tier,
                'cell_key': f'g3c1live:{iid}:{cond}',
                'artifact_record': artifact_record,
                '_presented_facts': project_surface(cond, bundle),
                '_oracle_gold': oracle['oracle_gold'],
                '_condition_gold': cert['condition_gold'],
            })
    if len(items) != 40:
        raise SystemExit(f'expected 40 g3c1live items, got {len(items)}')
    return items


def interleaved_order(items):
    """Deterministic balanced serial order over 80 cells: a 10-slot
    (model x condition) base permutation (seed ORDER_SEED) cyclically
    Latin-shifted one slot per issue. Every (model, condition) appears once
    per issue and 8 times overall."""
    import random
    from collections import Counter
    base = []
    for cond in GC.CONDITIONS:
        base.append(('deepseek-flash', cond))
        base.append(('gpt-4.1-mini', cond))
    random.Random(ORDER_SEED).shuffle(base)
    by = {(it['instance_id'], it['condition']): it for it in items}
    order = []
    for b, iid in enumerate(sorted({it['instance_id'] for it in items})):
        block = base[b % len(base):] + base[:b % len(base)]
        for model, cond in block:
            it = by[(iid, cond)]
            order.append({'serial': len(order), 'model_profile': model,
                          'instance_id': iid, 'condition': cond,
                          'cell_key': it['cell_key'],
                          'served_artifact_id': it['served_artifact_id']})
    cnt = Counter((o['model_profile'], o['condition']) for o in order)
    if len(order) != 80 or len(cnt) != 10 or set(cnt.values()) != {8}:
        raise SystemExit(f'g3c1live order balance broken: {dict(cnt)}')
    return order


# ---------------------------------------------------------------------------
# Pre-run fingerprint (runner / prompt / projection / server / gold / models).
# ---------------------------------------------------------------------------
def _sha_bytes(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def _sha_file(p: Path) -> str | None:
    return GC.sha256_file(p) if p.exists() else None


def _module_sha(name: str) -> str:
    import importlib
    mod = importlib.import_module(name)
    return GC.sha256_file(Path(mod.__file__))


def build_fingerprint():
    g3c1_manifest = json.loads(GC.OUT_FREEZE.read_text(encoding='utf-8'))
    prompt_fp = {c: GP.g3b2_prompt_fingerprint(c) for c in GC.CONDITIONS}
    tools_fp = {c: _sha_bytes(json.dumps(ternary_tools(c) or [],
                                         sort_keys=True,
                                         ensure_ascii=False).encode())
                for c in GC.CONDITIONS}
    fp = {
        'document': 'G3-C.1 exploratory 80-cell live run PRE-RUN fingerprint',
        'gate': GATE,
        'runner_version': RUNNER_VERSION,
        'research_kind': RESEARCH_KIND,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                          time.gmtime()),
        'executed': {
            'prompt_module': 'evidence.g3b2_prompts.build_g3b2_messages',
            'prompt_version': RUN_PROMPT_VERSION,
            'prompt_fingerprints': prompt_fp,
            'tools_fingerprints': tools_fp,
            'server_factory': 'evidence.g3c1_server.build_g3c1_server',
            'server_version_tag': 'EvidenceAPI/g3c1-v1',
            'protocol_version': RUN_PROTOCOL_VERSION,
            'projection_version': PROJECTION_VERSION,
            'gold_cert_version': RUN_GOLD_CERT_VERSION,
        },
        'frozen_parent_pins': {
            'g3c1_freeze_manifest': {
                'path': str(GC.OUT_FREEZE.relative_to(HERE)),
                'sha256': GC.sha256_file(GC.OUT_FREEZE)},
            'g3c1_truth': {'path': str(GC.TRUTH.relative_to(HERE)),
                           'sha256': GC.sha256_file(GC.TRUTH)},
            'g3c1_target_rows': {
                'path': str((GC.OUT_RAW / 'g3c1_target_rows.jsonl')
                            .relative_to(HERE)),
                'sha256': GC.sha256_file(
                    GC.OUT_RAW / 'g3c1_target_rows.jsonl')},
            'g3c1_oracle_gold': {
                'sha256': GC.sha256_file(
                    GC.OUT_GOLD / 'g3c1_oracle_gold.jsonl')},
            'g3c1_condition_certificates': {
                'sha256': GC.sha256_file(
                    GC.OUT_GOLD / 'g3c1_condition_certificates.jsonl')},
            'g3c1_freeze_declared_sha': g3c1_manifest.get('freeze_sha256'),
        },
        'code_hashes': {
            'g3c1_live_run.py': _module_sha('evidence.g3c1_live_run'),
            'g3b3_run.py (acquire/score/guard primitives)':
                _module_sha('evidence.g3b3_run'),
            'g3c1_server.py': _module_sha('evidence.g3c1_server'),
            'g3c0_projection_v2.py':
                _module_sha('evidence.g3c0_projection_v2'),
            'g3b2_prompts.py': _module_sha('evidence.g3b2_prompts'),
            'phase3_run.py (BudgetGuard/P3Client/ScriptedModel)':
                _module_sha('evidence.phase3_run'),
            'ev1_adapters.py': _module_sha('evidence.ev1_adapters'),
            'server.py': _module_sha('evidence.server'),
            'views.py': _module_sha('evidence.views'),
            'visibility.py': _module_sha('evidence.visibility'),
            'ternary.py': _module_sha('evidence.ternary'),
        },
        'models': {m: {
            'model': p['model'], 'base_url': p['base_url'],
            'key_env': p['key_env'],
            'price_in_per_1m': p['price_in_per_1m'],
            'price_out_per_1m': p['price_out_per_1m'],
            'extra_body': p['extra_body'],
            'completion_param': p['completion_param'],
            'response_format': p['response_format'],
            'expected_served_model_id': p['expected_served_model_id'],
            'per_model_cap_usd': p['per_model_cap_usd']}
            for m, p in PROFILES.items()},
        'sampling': {'temperature': TEMPERATURE,
                     'completion_cap_tokens': COMPLETION_CAP,
                     'max_tool_turns': MAX_TOOL_TURNS,
                     'max_model_calls_per_cell': MAX_MODEL_CALLS_PER_CELL,
                     'retries_per_cell': RETRIES_PER_CELL,
                     'order_seed': ORDER_SEED,
                     'response_format': 'json_schema strict on the final '
                                        'decision turn (frozen ternary '
                                        'schema); tools on tool turns; no '
                                        'error-triggered downgrade, no retry'},
        'budget': {
            'total_hard_cap_usd': TOTAL_BUDGET_USD,
            'per_model_cap_usd': PER_MODEL_CAP_USD,
            'enforcement': 'pre-call worst-case bound (fresh transcript '
                           'tokens*price_in + completion_cap*price_out) '
                           'checked by BOTH a per-model guard and one shared '
                           'total guard before EVERY paid call; resume '
                           'restores cumulative spend; NaN/Inf/negative '
                           'cost poisons the ledger and blocks all further '
                           'calls',
        },
        'scope': {'issues': 8, 'conditions': 5, 'models': 2, 'cells': 80,
                  'no_new_issues_models_conditions': True,
                  'no_rerun_successful_cell': True,
                  'no_fallback_model': True,
                  'no_response_format_downgrade': True},
        'gold_authority': GOLD_AUTHORITY,
    }
    return fp


def write_fingerprint():
    OUT_FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    fp = build_fingerprint()
    OUT_FINGERPRINT.write_bytes(GC.canonical_bytes(fp))
    return fp


# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
def _out_name(model, mock):
    safe = model.replace('.', '').replace('-', '_')
    return f'g3c1live_{"mock" if mock else "live"}_{safe}_results.jsonl'


def _spawn_g3c1_server():
    tmp = tempfile.mkdtemp(prefix='g3c1live_store_copy_')
    shutil.copytree(str(GC.OUT_STORE), tmp, dirs_exist_ok=True)
    httpd = GS.build_g3c1_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}', tmp


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
def run(*, live: bool):
    # Pre-paid invariants: the frozen G3-C.1 freeze must be intact and a
    # fingerprint must exist (written by --fingerprint / the pre-paid gate).
    if not GC.OUT_FREEZE.exists():
        raise SystemExit('REFUSED: frozen G3-C.1 freeze manifest missing.')
    items = build_items()
    order = interleaved_order(items)
    items_by = {(it['instance_id'], it['condition']): it for it in items}
    prompt_fp = {c: GP.g3b2_prompt_fingerprint(c) for c in GC.CONDITIONS}
    certs = {(c['instance_id'], c['condition']): c
             for c in GC.read_jsonl(
                 GC.OUT_GOLD / 'g3c1_condition_certificates.jsonl')}

    OUT_RUNS.mkdir(parents=True, exist_ok=True)
    OUT_RAW.mkdir(parents=True, exist_ok=True)
    OUT_TRACES.mkdir(parents=True, exist_ok=True)

    httpd, api, tmp_root = _spawn_g3c1_server()
    print(f'g3c1 evidence server {api} on ISOLATED COPY {tmp_root} '
          '(frozen G3-C.1 store untouched)')
    print('server protocol_version='
          f'{getattr(httpd, "g3c1_protocol_version")}')

    # One SHARED total guard across both models, priced at the conservative
    # max in/out price, exactly like the frozen runner's composition.
    total_guard = BudgetGuard(
        TOTAL_BUDGET_USD,
        max(p['price_in_per_1m'] for p in PROFILES.values()),
        max(p['price_out_per_1m'] for p in PROFILES.values()),
        completion_cap_tokens=COMPLETION_CAP,
        max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)

    files, guards, done, drivers, wire = {}, {}, {}, {}, {}
    aggregate_prior = 0.0
    for m in MODELS:
        prof = PROFILES[m]
        outp = OUT_RUNS / _out_name(m, not live)
        if live:
            spent, dset = _prior_spent_and_done(outp)
            spent = safe_resume_spent(spent)
            aggregate_prior += spent
            files[m] = outp.open('a', encoding='utf-8')
            done[m] = dset
            drv = make_driver(_live_completions(prof), prof)
            drivers[m] = drv
            wire[m] = drv.chat.completions
            g = G3C1Guard(PER_MODEL_CAP_USD, total_guard,
                          prof['price_in_per_1m'], prof['price_out_per_1m'],
                          completion_cap_tokens=COMPLETION_CAP,
                          max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)
            g.spent = spent
            guards[m] = g
        else:
            files[m] = outp.open('w', encoding='utf-8')
            done[m] = set()
            guards[m] = None
            drivers[m] = wire[m] = None
    total_guard.spent = round(aggregate_prior, 8)
    if live:
        print(f'restored prior g3c1live spend across models='
              f'${aggregate_prior:.4f}')

    counts = {m: {'new': 0, 'error': 0, 'skip_done': 0} for m in MODELS}
    stop_msg = ''
    ev = P3Client(api)
    try:
        for o in order:
            m = o['model_profile']
            ck = o['cell_key']
            if live and ck in done[m]:
                counts[m]['skip_done'] += 1
                continue
            prof = PROFILES[m]
            item = items_by[(o['instance_id'], o['condition'])]

            if total_guard.spent >= TOTAL_BUDGET_USD - 1e-12:
                stop_msg = (f'TOTAL cap ${TOTAL_BUDGET_USD:.2f} reached '
                            f'(spent ${total_guard.spent:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            if live:
                driver, guard, mock = drivers[m], guards[m], False
            else:
                scripted = ScriptedModel(item['condition'], item,
                                         prompt_version='p3-ternary-v2')
                driver = make_driver(scripted, prof)
                wrec = driver.chat.completions
                guard, mock = None, True
            wire_obj = wire[m] if live else wrec

            t0 = time.time()
            error = None
            raw = None
            try:
                raw = acquire_cell(
                    driver, prof['model'], item, ev, prof, wire_obj,
                    mock=mock, guard=guard)
            except ProtocolCapabilityDrift:
                raise
            except BudgetGuardStop as bs:
                # Pre-call hard stop: no call was made, resume-eligible row.
                error = f'BudgetGuardStop: {bs}'
                raw = {
                    'protocol': 'ternary-g3c1live', 'mock': not live,
                    'cell': ck, 'id': item['id'],
                    'instance_id': item['instance_id'],
                    'condition': item['condition'],
                    'evidence_tier': item['evidence_tier'],
                    'policy': ternary_condition_tier_policy(
                        item['condition'])[2],
                    'model': prof['model'], 'model_profile': m,
                    'model_served': None,
                    'served_artifact_id': item['served_artifact_id'],
                    'evidence_session': None, 'answer_raw': '',
                    'raw_model_calls': [], 'tool_trace': [],
                    'tool_calls': 0, 'model_calls': 0,
                    'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                    'pre_call_worst_case_bounds_usd': [],
                    'pre_call_budget_stop': True,
                    'pre_call_budget_reason': str(bs),
                    'wall_s': round(time.time() - t0, 2),
                    '_guard_stop_internal': True}
            except Exception as e:  # terminal error row; NO retry
                error = f'{type(e).__name__}: {e}'
                raw = {
                    'protocol': 'ternary-g3c1live', 'mock': not live,
                    'cell': ck, 'id': item['id'],
                    'instance_id': item['instance_id'],
                    'condition': item['condition'],
                    'evidence_tier': item['evidence_tier'],
                    'policy': ternary_condition_tier_policy(
                        item['condition'])[2],
                    'model': prof['model'], 'model_profile': m,
                    'model_served': None,
                    'served_artifact_id': item['served_artifact_id'],
                    'evidence_session': None, 'answer_raw': '',
                    'raw_model_calls': [], 'tool_trace': [],
                    'tool_calls': 0, 'model_calls': 0,
                    'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                    'pre_call_worst_case_bounds_usd': [],
                    'pre_call_budget_stop': False,
                    'pre_call_budget_reason': None,
                    'wall_s': round(time.time() - t0, 2),
                    '_guard_stop_internal': False}

            # RAW lands FIRST, before any parse/score.
            raw_path = OUT_RAW / (
                f'{m.replace("-", "_")}__{o["serial"]:03d}__'
                + ck.replace('g3c1live:', '').replace(':', '__') + '.json')
            raw_path.write_text(json.dumps(
                raw, ensure_ascii=False, indent=2, sort_keys=True),
                encoding='utf-8')

            if error is None:
                try:
                    rec = score_cell(raw, item,
                                     prompt_fp=prompt_fp[item['condition']])
                except Exception as se:
                    rec = dict(raw)
                    rec['parsed'] = None
                    error = f'ScoringError: {type(se).__name__}: {se}'
            else:
                rec = dict(raw)
            if error is not None:
                rec['parsed'] = None
                rec['answer'] = rec.get('answer_raw', '')
                rec['error'] = error
            # Unconditionally (success AND error paths) override whatever the
            # frozen g3b3 score_cell stamped into rec['version'] -- this live
            # run is a distinct gate/protocol/prompt/gold-cert, never g3b3.
            rec.setdefault('version', {})
            rec['version'].update({
                'gate': GATE, 'runner_version': RUNNER_VERSION,
                'protocol_version': RUN_PROTOCOL_VERSION,
                'prompt_version': RUN_PROMPT_VERSION,
                'gold_cert_version': RUN_GOLD_CERT_VERSION,
                'prompt_fingerprint': prompt_fp[item['condition']]})

            cert = certs[(item['instance_id'], item['condition'])]
            rec['gate'] = GATE
            rec['serial'] = o['serial']
            rec['expected_served_model_id'] = \
                prof['expected_served_model_id']
            rec['audit_oracle_gold'] = cert['oracle_gold']
            rec['audit_condition_gold'] = cert['condition_gold']
            rec['raw_sha256'] = _sha_bytes(raw_path.read_bytes())
            rec['gold_tier'] = 'PROVISIONAL'
            rec['annotators'] = 1
            rec['annotator2'] = 'NOT_OBTAINED'
            rec['research_kind'] = RESEARCH_KIND
            if not live:
                rec['research_excluded'] = True
            if live:
                rec['adapter_wire_calls'] = [dict(c) for c in
                                             getattr(wire[m], 'calls', [])]
                wire[m].calls.clear()

            files[m].write(json.dumps(rec, ensure_ascii=False) + '\n')
            files[m].flush()
            counts[m]['new'] += 1
            if rec.get('error'):
                counts[m]['error'] += 1

            tdir = OUT_TRACES / ('live' if live else 'mock')
            tdir.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[^A-Za-z0-9._-]+', '_', ck).strip('_')
            (tdir / f'{o["serial"]:03d}_{safe}.json').write_text(
                json.dumps({'cell': ck, 'condition': item['condition'],
                            'policy': rec.get('policy'),
                            'session_id': rec.get('evidence_session'),
                            'trace': rec.get('tool_trace', []),
                            'final_answer': rec.get('answer', ''),
                            'parsed': rec.get('parsed'),
                            'fresh_state_served':
                                rec.get('fresh_state_served'),
                            'error': rec.get('error')},
                           ensure_ascii=False, indent=2), encoding='utf-8')

            if live:
                assert_served_model(rec.get('model_served'),
                                    prof['expected_served_model_id'], ck)
                if guards[m].poisoned:
                    stop_msg = f'LEDGER POISONED at {ck}: ' \
                               f'{guards[m].poison_reason}'
                    print('HARD STOP ' + stop_msg)
                    break
                if rec.get('error') and 'BudgetGuardStop' in \
                        str(rec['error']):
                    stop_msg = f'{m} BudgetGuardStop at {ck}: {rec["error"]}'
                    print('BUDGET STOP ' + stop_msg)
                    break
            print(f'{o["serial"]:>3} {m[:3]} {item["condition"]:<13} '
                  f'{item["instance_id"].split("-")[-1]:<6} '
                  f'parsed={str(rec.get("parsed"))[:13]:<13} '
                  f'tools={rec.get("tool_calls",0)} '
                  f'calls={rec.get("model_calls",0)} '
                  f'in={rec.get("tokens_in",0):<6} '
                  f'out={rec.get("tokens_out",0):<5} '
                  f'${rec.get("cost_usd",0):.5f} '
                  f'tot=${total_guard.spent:.4f}'
                  + (' ERR' if rec.get('error') else ''))
    finally:
        for fh in files.values():
            fh.close()
        httpd.shutdown()
        shutil.rmtree(tmp_root, ignore_errors=True)

    per_model_spend = {m: round(guards[m].spent, 6) for m in MODELS} \
        if live else {m: 0.0 for m in MODELS}
    total_spend = round(total_guard.spent if live else 0.0, 6)
    summary = {
        'gate': GATE, 'mode': 'live' if live else 'mock',
        'runner_version': RUNNER_VERSION, 'research_kind': RESEARCH_KIND,
        'executed_protocol_version': RUN_PROTOCOL_VERSION,
        'executed_prompt_version': RUN_PROMPT_VERSION,
        'executed_gold_cert_version': RUN_GOLD_CERT_VERSION,
        'projection_version': PROJECTION_VERSION,
        'order_seed': ORDER_SEED,
        'new_rows': {m: counts[m]['new'] for m in MODELS},
        'error_rows': {m: counts[m]['error'] for m in MODELS},
        'skipped_already_done': {m: counts[m]['skip_done'] for m in MODELS},
        'per_model_spend_usd': per_model_spend,
        'total_spend_usd': total_spend,
        'total_hard_cap_usd': TOTAL_BUDGET_USD,
        'per_model_cap_usd': PER_MODEL_CAP_USD,
        'within_total_cap': total_spend <= TOTAL_BUDGET_USD + 1e-9,
        'within_per_model_cap': all(
            per_model_spend[m] <= PER_MODEL_CAP_USD + 1e-9 for m in MODELS),
        'retries_per_cell': RETRIES_PER_CELL,
        'stop_msg': stop_msg,
        'isolated_store_copy_removed': not Path(tmp_root).exists(),
        'gold_authority': GOLD_AUTHORITY,
    }
    auditp = OUT_RUNS / (f'g3c1live_{"live" if live else "mock"}_run_audit.json')
    auditp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print(f'\nG3-C.1 {"LIVE" if live else "MOCK"} done: '
          f'new={sum(c["new"] for c in counts.values())} '
          f'total_spend=${total_spend:.4f} cap=${TOTAL_BUDGET_USD:.2f} '
          f'within={summary["within_total_cap"]}'
          + (f' STOP: {stop_msg}' if stop_msg else ''))
    print('audit ->', auditp)

    if live:
        export_results_real()
    return summary


def _all_rows_live():
    rows = []
    for m in MODELS:
        p = OUT_RUNS / _out_name(m, False)
        if p.exists():
            rows.extend(GC.read_jsonl(p))
    return rows


def export_results_real():
    """Emit paper_sprint/experiment80/RESULTS_REAL.json from the live rows.
    Complete only when all 80 (issue,model,condition) cells have a ternary
    verdict; an unfinished run is exported as INCOMPLETE (never padded, never
    imputed) so the pre-registered analyser cannot read a fabricated cell."""
    rows = _all_rows_live()
    good = [r for r in rows
            if r.get('parsed') in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')]
    seen = {(r['instance_id'], r['model_profile'], r['condition'])
            for r in good}
    expected = {(it['instance_id'], m, c)
                for it in build_items() for m in MODELS
                for c in GC.CONDITIONS}
    missing = sorted(expected - seen)
    out_rows = [{
        'issue': r['instance_id'], 'model': r['model_profile'],
        'condition': r['condition'], 'verdict': r['parsed'],
        'oracle_gold': r.get('audit_oracle_gold'),
        'condition_gold': r.get('audit_condition_gold'),
        'cost_usd': r.get('cost_usd'), 'tokens_in': r.get('tokens_in'),
        'tokens_out': r.get('tokens_out'),
        'model_calls': r.get('model_calls'),
        'tool_calls': r.get('tool_calls'),
        'model_served': r.get('model_served'),
        'expected_served_model_id': r.get('expected_served_model_id'),
        'raw_sha256': r.get('raw_sha256'),
        'cell': r.get('cell'), 'error': r.get('error'),
    } for r in sorted(good, key=lambda x: (x['instance_id'],
                                           x['model_profile'],
                                           x['condition']))]
    status = 'COMPLETE_80' if not missing and len(out_rows) == 80 \
        else 'INCOMPLETE'
    payload = {'status': status,
               'research_kind': RESEARCH_KIND,
               'gold_tier': 'PROVISIONAL',
               'annotator2': 'NOT_OBTAINED',
               'n_rows': len(out_rows),
               'missing_cells': [
                   {'issue': i, 'model': m, 'condition': c}
                   for i, m, c in missing],
               'rows': out_rows}
    RESULTS_REAL.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_REAL.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                            + '\n', encoding='utf-8')
    print(f"RESULTS_REAL.json -> {RESULTS_REAL} status={status} "
          f"rows={len(out_rows)} missing={len(missing)}")
    return status


# ---------------------------------------------------------------------------
# Mandatory $0 pre-paid gate: an 80-cell offline mock over the REAL g3c1
# server. This gate proves plumbing, $0 spend, raw-first landing, resume row
# shapes and scoring wiring -- it is NOT a model result (rows carry
# mock=true/research_excluded and are never analysed).
#
# Gold alignment is asserted on the 64 non-Escalate cells, where the frozen
# generic protocol script (evidence.phase3_run.ScriptedModel, the exact same
# stand-in used by G3-B.3) converges inside the frozen MAX_TOOL_TURNS=8. On
# T3D-Escalate that generic v2 script performs a 9-turn reason-gated exercise
# (symptom -> log 400 -> log 200 banner -> consistency 400 -> consistency
# 200) and is cut off at turn 8; it therefore ends INVALID. This is a
# frozen-known property of the GENERIC SCRIPT, identical in the G3-B.3 frozen
# mock (all 10 of its Escalate mock cells are INVALID too) -- it is not a
# server, gold or live-runner defect. Escalate condition-gold alignment for
# G3-C.1 is certified independently by the dedicated frozen gate
# evidence.g3c1_mock (40/40, mock_match_rate=1.0, model-symmetric), and the
# real G3-B.3 live models converged on Escalate in 3-5 model calls (< 8).
# We therefore record, rather than fail on, the 16 script-truncated Escalate
# mock cells, and require the dedicated frozen mock gate separately.
# ---------------------------------------------------------------------------
def mock_gate():
    summary = run(live=False)

    rows = []
    for m in MODELS:
        p = OUT_RUNS / _out_name(m, True)
        rows.extend((m, r) for r in GC.read_jsonl(p))

    n = len(rows)
    non_esc_mismatch, esc_truncated, esc_unexpected = [], [], []
    for m, r in rows:
        cond, parsed = r.get('condition'), r.get('parsed')
        if cond != 'T3D-Escalate':
            if parsed != r.get('audit_condition_gold'):
                non_esc_mismatch.append(
                    {'model': m, 'cell': r.get('cell'), 'parsed': parsed,
                     'condition_gold': r.get('audit_condition_gold')})
            continue
        # Escalate: the generic script must be cut at the tool-turn cap with
        # no terminal error, raw landed and marked research-excluded.
        truncated = (
            parsed not in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')
            and not r.get('error')
            and r.get('tool_calls') == MAX_TOOL_TURNS
            and bool(r.get('mock')) and bool(r.get('research_excluded')))
        (esc_truncated if truncated else esc_unexpected).append(
            {'model': m, 'cell': r.get('cell'), 'parsed': parsed,
             'error': r.get('error'), 'tool_calls': r.get('tool_calls')})

    zero_cost = (round(summary['total_spend_usd'], 9) == 0.0
                 and all(round(v, 9) == 0.0
                         for v in summary['per_model_spend_usd'].values()))
    zero_errors = all(summary['error_rows'][m] == 0 for m in MODELS)
    balanced = all(summary['new_rows'][m] == 40 for m in MODELS)
    all_excluded = all(bool(r.get('mock')) and bool(r.get('research_excluded'))
                       for _, r in rows)

    ok = (n == 80 and balanced and zero_cost and zero_errors
          and all_excluded and not non_esc_mismatch and not esc_unexpected
          and len(esc_truncated) == 16)

    print(f'MOCK GATE: cells={n}/80 balanced={balanced} zero_cost={zero_cost} '
          f'terminal_errors={zero_errors} raw_excluded={all_excluded}')
    print(f'  non-Escalate gold alignment: {64 - len(non_esc_mismatch)}/64 '
          f'(T2D-T, T3D-Strict, T2A-T, T3A-T over all 8 issues x 2 models)')
    print(f'  T3D-Escalate generic-script turn-cap truncation: '
          f'{len(esc_truncated)}/16 recorded (frozen-known, model-symmetric; '
          f'gold certified by dedicated evidence.g3c1_mock 40/40)')
    if not ok:
        detail = {'n': n, 'balanced': balanced, 'zero_cost': zero_cost,
                  'zero_errors': zero_errors, 'all_excluded': all_excluded,
                  'non_esc_mismatch': non_esc_mismatch[:5],
                  'esc_unexpected': esc_unexpected[:5]}
        raise SystemExit(
            'PRE-PAID MOCK GATE FAILED: ' + json.dumps(detail)[:1500]
            + '; NO paid call allowed.')
    return ok


# ---------------------------------------------------------------------------
# Budget guard self-test (None / NaN / accumulation / resume / per-cell /
# per-model $1.00 / shared total $2.00). Pure, offline, no network.
# ---------------------------------------------------------------------------
def selftest():
    results = []

    def record(name, ok, detail=''):
        results.append({'case': name, 'ok': bool(ok), 'detail': detail})
        if not ok:
            raise AssertionError(f'selftest failed: {name} {detail}')

    prices = {m: (PROFILES[m]['price_in_per_1m'],
                  PROFILES[m]['price_out_per_1m']) for m in MODELS}

    # 1) None cost is coerced to 0.0 and the ledger is unchanged.
    tg = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                     completion_cap_tokens=COMPLETION_CAP)
    g = G3C1Guard(PER_MODEL_CAP_USD, tg, 0.40, 1.60,
                  completion_cap_tokens=COMPLETION_CAP)
    g.add(None)
    record('none_cost_coerced_zero', g.spent == 0.0 and tg.spent == 0.0)

    # 2) normal accumulation is reflected in BOTH guards.
    g.add(0.0025)
    record('cost_accumulates_per_model_and_total',
           abs(g.spent - 0.0025) < 1e-12 and abs(tg.spent - 0.0025) < 1e-12)

    # 3) NaN cost poisons the ledger and blocks the NEXT pre-call check.
    blocked_after_nan = False
    try:
        g.add(float('nan'))
    except BudgetGuardStop:
        pass
    try:
        g.check(1000, 0)
    except BudgetGuardStop:
        blocked_after_nan = True
    record('nan_cost_poisons_and_blocks_further_calls',
           g.poisoned and blocked_after_nan)

    # 3b) Inf and negative costs are likewise untrackable.
    for bad, label in ((float('inf'), 'inf'), (-0.01, 'negative')):
        t2 = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                         completion_cap_tokens=COMPLETION_CAP)
        g2 = G3C1Guard(PER_MODEL_CAP_USD, t2, 0.40, 1.60,
                       completion_cap_tokens=COMPLETION_CAP)
        raised = False
        try:
            g2.add(bad)
        except BudgetGuardStop:
            raised = True
        after_blocked = False
        try:
            g2.check(500, 0)
        except BudgetGuardStop:
            after_blocked = True
        record(f'{label}_cost_untrackable_blocks', raised and after_blocked)

    # 4) per-cell model-call hard cap (12) blocks.
    t3 = BudgetGuard(TOTAL_BUDGET_USD, 0.40, 1.60,
                     completion_cap_tokens=COMPLETION_CAP)
    g3 = G3C1Guard(PER_MODEL_CAP_USD, t3, 0.40, 1.60,
                   completion_cap_tokens=COMPLETION_CAP,
                   max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)
    cell_block = False
    try:
        g3.check(1000, MAX_MODEL_CALLS_PER_CELL)
    except BudgetGuardStop:
        cell_block = True
    record('per_cell_call_cap_blocks', cell_block)

    # 5) per-model $1.00 blocks even while the shared $2.00 has room.
    for m, (pin, pout) in prices.items():
        tt = BudgetGuard(TOTAL_BUDGET_USD, pin, pout,
                         completion_cap_tokens=COMPLETION_CAP)
        gm = G3C1Guard(PER_MODEL_CAP_USD, tt, pin, pout,
                       completion_cap_tokens=COMPLETION_CAP)
        gm.spent = PER_MODEL_CAP_USD - 0.0001
        model_blocks = False
        try:
            gm.check(4000, 1)
        except BudgetGuardStop:
            model_blocks = True
        record(f'{m}__per_model_1usd_blocks_with_total_room',
               model_blocks and tt.spent < TOTAL_BUDGET_USD)

    # 6) the two per-model guards share ONE total accumulator across models.
    pin, pout = 0.40, 1.60
    total = BudgetGuard(TOTAL_BUDGET_USD, pin, pout,
                        completion_cap_tokens=COMPLETION_CAP)
    ga = G3C1Guard(PER_MODEL_CAP_USD, total, pin, pout,
                   completion_cap_tokens=COMPLETION_CAP)
    gb = G3C1Guard(PER_MODEL_CAP_USD, total, pin, pout,
                   completion_cap_tokens=COMPLETION_CAP)
    ga.add(0.60)          # model A spends $0.60 (< $1)
    gb.add(0.70)          # model B spends $0.70 (< $1); shared total $1.30
    record('total_accumulator_shared_across_models',
           abs(ga.spent - 0.60) < 1e-12 and abs(gb.spent - 0.70) < 1e-12
           and abs(total.spent - 1.30) < 1e-9)
    # the independent shared TOTAL guard blocks at $2.00 even though it is
    # not a per-model guard (same frozen-guard primitive, $2 cap).
    total.spent = TOTAL_BUDGET_USD - 0.0001
    total_blocks = False
    try:
        total.check(4000, 0)
    except BudgetGuardStop:
        total_blocks = True
    record('shared_total_2usd_blocks_at_cap', total_blocks)

    # 7) resume: cumulative spend + terminal-done restore (transport errors
    # resume-eligible; ScoringError terminal; mocks never counted).
    d = tempfile.mkdtemp(prefix='g3c1live_selftest_')
    p = Path(d) / 'rows.jsonl'
    seed_rows = [
        {'cell': 'a', 'cost_usd': 0.10, 'mock': False},
        {'cell': 'b', 'cost_usd': 0.20, 'mock': False},
        {'cell': 'mockrow', 'cost_usd': 0.0, 'mock': True},
        {'cell': 'e', 'cost_usd': 0.0, 'mock': False,
         'error': 'TransportError: x'},
        {'cell': 's', 'cost_usd': 0.30, 'mock': False,
         'error': 'ScoringError:y'},
        {'cell': 'n', 'cost_usd': None, 'mock': False},
    ]
    p.write_text('\n'.join(json.dumps(r) for r in seed_rows) + '\n',
                 encoding='utf-8')
    spent, done = _prior_spent_and_done(p)
    record('resume_restores_cumulative_spent', abs(spent - 0.60) < 1e-12,
           f'spent={spent}')
    record('resume_terminal_done_set',
           sorted(done) == ['a', 'b', 'n', 's'], f'done={sorted(done)}')
    record('resume_spent_nan_refused',
           _resume_spent_refuses_nan())
    shutil.rmtree(d, ignore_errors=True)

    # 8) caps really are the authorisation values (not the old $3/$1.5).
    record('caps_are_2usd_total_and_1usd_model',
           TOTAL_BUDGET_USD == 2.00 and PER_MODEL_CAP_USD == 1.00)

    out = {'document': 'G3-C.1 live runner budget guard self-test ($0)',
           'all_ok': all(r['ok'] for r in results),
           'total_hard_cap_usd': TOTAL_BUDGET_USD,
           'per_model_cap_usd': PER_MODEL_CAP_USD,
           'checks': results}
    OUT_FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_FREEZE_DIR / 'g3c1live_budget_selftest.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f'BUDGET SELFTEST: {sum(r["ok"] for r in results)}/'
          f'{len(results)} checks passed; caps $2.00/$1.00')
    return out


def _resume_spent_refuses_nan():
    try:
        safe_resume_spent(float('nan'))
    except SystemExit:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--fingerprint', action='store_true')
    ap.add_argument('--mock-gate', action='store_true')
    ap.add_argument('--export', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument(ACK, action='store_true', dest='ack')
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return
    if a.fingerprint:
        fp = write_fingerprint()
        print('fingerprint ->', OUT_FINGERPRINT)
        return
    if a.mock_gate:
        # Refresh the fingerprint (no network) then run the 80-cell mock.
        write_fingerprint()
        mock_gate()
        return
    if a.export:
        st = export_results_real()
        return

    live = bool(a.allow_paid_run and a.ack)
    if a.allow_paid_run and not a.ack:
        raise SystemExit(f'REFUSED: --allow-paid-run also requires {ACK}.')
    if a.mock:
        mock_gate()
        return
    if not live:
        raise SystemExit(
            'REFUSED: run ONLY as --mock-gate (offline, $0), --selftest, '
            '--fingerprint, or with the double gate --allow-paid-run '
            + ACK + ' (80 REAL cells max, TOTAL $2.00, per-model $1.00, '
            'retries 0, PROVISIONAL gold, exploratory). No call was made.')

    # Mandatory pre-paid checks before a single real call.
    st = selftest()
    if not st['all_ok']:
        raise SystemExit('PRE-PAID budget self-test failed; not charging.')
    fp = write_fingerprint()
    if not OUT_FINGERPRINT.exists():
        raise SystemExit('fingerprint missing; not charging.')
    run(live=True)


if __name__ == '__main__':
    main()
