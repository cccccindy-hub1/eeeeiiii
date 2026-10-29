"""GroundedReview Gate 3-B.3 — Corrective Replication LIVE RUNNER (independent).

Executes the 100 frozen REAL cells (2 real models x 10 frozen independent
SymPy issues x 5 frozen conditions) over the ACCEPTED G3-B.2 repaired
protocol. This runner is independent of evidence.g3b_run: the G3-B runner,
its server and its historical results are never modified, overwritten or
re-scored. The ONLY executed protocol pieces are the frozen G3-B.2 ones:

  * messages : evidence.g3b2_prompts.build_g3b2_messages
               (p3-ternary-g3b2-v1; T2A institutional trust; active three-
               state freshness note);
  * tools    : the frozen ternary tool sets (frozen JSON schemas);
  * HTTP     : evidence.g3b2_server.build_g3b2_server on an ISOLATED tempdir
               copytree of the signed G3-A store; freshness is the G3-B.2
               three-state adjudicator (the old structurally-false endpoint
               is never called);
  * gold     : per-cell pairing to the g3b2 gold certificates (PROVISIONAL).

Discipline enforced in code (the written approval):
  * static regimes (T2D-T, T2A-T) are single-turn; active regimes
    (T3D-Strict, T3D-Escalate, T3A-T) use a REAL multi-turn tool session with
    one fresh session per active cell, the frozen Strict 403 wall and
    Escalate 400 -> reason -> 200 exercised by the live model itself;
  * exactly ONE scored verdict per cell; retries_per_cell = 0; a
    wrong/unexpected/INVALID/AMBIGUOUS/transport fault is a TERMINAL,
    resume-eligible error row (never retried within the run);
  * the raw response of EVERY model call is written under raw/ BEFORE the
    final decision is parsed or scored;
  * full tool trace, tokens, per-call worst-case and actual cost, wall time,
    actual served model id, wire-call shapes, decision/reason and error state
    are persisted per cell;
  * DOUBLE explicit gate (--allow-paid-run AND the G3-B.3 acknowledgement);
  * a composite pre-call BudgetGuard enforces BOTH the per-model $1.50 cap
    and the $3.00 TOTAL cap before EVERY model call; resume restores
    cumulative spend from the on-disk rows;
  * served-model id drift, any error-triggered response_format downgrade
    (adapter fallback), or freeze/protocol drift HARD-STOP the whole run and
    are reported -- never a silent downgrade/substitution;
  * the evidence server serves an isolated COPY of the frozen store so its
    audit log is never appended to; the freeze is never rewritten.

Offline ($0; full live code path against a deterministic scripted driver):
    uv run --python 3.13 -m evidence.g3b3_run --mock
Live (needs openai, explicit double-gate approval):
    uv run --python 3.11 --with openai -m evidence.g3b3_run \\
        --allow-paid-run --i-acknowledge-g3b3-approved
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path

from evidence.ev1_adapters import make_driver
from evidence.phase3_run import (
    BudgetGuard, BudgetGuardStop, P3Client, ScriptedModel,
    symptom_persists_from_trace,
)
from evidence.prompts import ternary_tools, ternary_condition_tier_policy
from evidence.ternary import parse_ternary_decision, TERNARY_DECISION_SCHEMA
from evidence.gap_w2 import classify_abstention
from evidence.cee_run import _load_key

from evidence import g3b2_prompts as GP
from evidence import g3b2_server as GS
from evidence import g3b3_common as C
from evidence import g3b3_freeze as FZ

_ACCEPTANCE_LOGS = ('f2p', 'p2p', 'p2p_baseline')


class ProtocolCapabilityDrift(SystemExit):
    """Raised when a live response reveals protocol incompatibility / freeze
    drift (e.g. the adapter had to downgrade response_format after a 400, or
    served model id changed). The WHOLE run halts; no silent downgrade."""


def assert_served_model(served, expected, cell_key=None):
    """The vendor-returned served model id must equal the approved frozen id.
    Any drift HARD-STOPS the run; there is never a silent substitution."""
    if served and served != expected:
        raise SystemExit(
            f'SERVED MODEL DRIFT STOP at {cell_key}: expected {expected}, '
            f'got {served}; halting, no substitution.')


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_freeze():
    if not C.OUT_FREEZE.exists():
        raise SystemExit('G3-B.3 freeze missing; run: '
                         'python -m evidence.g3b3_freeze')
    return json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))


def assert_freeze_canonical():
    """The on-disk freeze must equal the canonical derivation from the frozen
    code. Any drift -> refuse before a single paid call."""
    canon = C.canonical_bytes(FZ.build_freeze())
    if _sha(C.OUT_FREEZE.read_bytes()) != _sha(canon):
        raise SystemExit(
            'REFUSED: on-disk G3-B.3 freeze differs from the canonical '
            'derivation; rebuild offline and rerun preflight before any paid '
            'call.')


def _out_name(model, mock):
    safe = model.replace('.', '').replace('-', '_')
    return f'g3b3_{"mock" if mock else "live"}_{safe}_results.jsonl'


class CompositeGuard:
    """Pre-call guard enforcing BOTH a per-model cap and the shared TOTAL cap.
    Copied in structure from the frozen g3b_run CompositeGuard."""

    def __init__(self, model_cap, total_guard, pin, pout, *,
                 completion_cap_tokens, max_model_calls_per_cell):
        self.model_guard = BudgetGuard(
            model_cap, pin, pout,
            completion_cap_tokens=completion_cap_tokens,
            max_model_calls_per_cell=max_model_calls_per_cell)
        self.total_guard = total_guard
        self.pin, self.pout = pin, pout

    @property
    def spent(self):
        return self.model_guard.spent

    @spent.setter
    def spent(self, v):
        self.model_guard.spent = v

    @property
    def calls_total(self):
        return self.model_guard.calls_total

    def bound_usd(self, prompt_tokens_now):
        return self.model_guard.bound_usd(prompt_tokens_now)

    def check(self, prompt_tokens_now, cell_calls):
        # Enforce BOTH caps; report this model's own conservative bound so
        # the runner can record the per-call worst-case spend.
        bound = self.model_guard.check(prompt_tokens_now, cell_calls)
        self.total_guard.check(prompt_tokens_now, cell_calls)
        return bound

    def add(self, cost):
        self.model_guard.add(cost)
        self.total_guard.add(cost)


def _profile(name):
    p = dict(FZ.PROFILES[name])
    p['name'] = name
    return p


def _live_completions(profile):
    from openai import OpenAI
    key = _load_key(profile)
    if not key:
        raise SystemExit(f"missing API key for {profile['name']} "
                         f"({profile['key_env']})")
    return OpenAI(api_key=key, base_url=profile['base_url']).chat.completions


def _prior_spent_and_done(out_path):
    """Resume: restore cumulative actual spend and the set of terminal non-
    error cells from the on-disk rows."""
    if not out_path.exists():
        return 0.0, set()
    rows = C.read_jsonl(out_path)
    spent = sum(float(r.get('cost_usd') or 0) for r in rows if not r.get('mock'))
    # A scored row is terminal (never paid for again). Transport/acquisition
    # error rows are resume-eligible (re-run); a local ScoringError row is
    # also terminal: its paid raw is already landed and re-paying would
    # violate the one-call-per-cell discipline.
    done = {r['cell'] for r in rows
            if not r.get('mock')
            and (not r.get('error')
                 or str(r.get('error')).startswith('ScoringError'))}
    return spent, done


# ---------------------------------------------------------------------------
# Raw cell acquisition (no scoring): returns a record whose 'answer_raw' is
# the untouched final model output. The runner writes this to raw/ BEFORE
# parsing or scoring.
# ---------------------------------------------------------------------------

def _est_prompt_tokens(messages):
    n = 0
    for m in messages:
        c = m.get('content')
        if isinstance(c, str):
            n += len(c)
        if m.get('tool_calls'):
            for tc in m['tool_calls']:
                n += len(json.dumps(tc, ensure_ascii=False))
    return max(n // 3, 256)


def acquire_cell(driver, model, item, ev, profile, wire, *, mock=False,
                 guard=None):
    """Run one g3b3 cell over the repaired protocol and return RAW evidence.
    No decision is parsed here."""
    cond = item['condition']
    active, tier, policy = ternary_condition_tier_policy(cond)
    # (1) prompts come from g3b2_prompts -- the ONLY message builder used.
    messages = GP.build_g3b2_messages(item, artifact=item.get('artifact_record'))
    # (2) frozen tool sets; None for static regimes.
    tools = ternary_tools(cond)
    usage, last_usage = {'in': 0, 'out': 0}, {'in': 0, 'out': 0}
    trace, raw_calls = [], []
    sid = model_served = None
    cell_calls = 0
    t0 = time.time()

    if active:
        s = ev.open_session(
            item['instance_id'], item['base_commit'], item['patch_sha256'],
            cell=item['cell_key'], served_artifact_id=item.get(
                'served_artifact_id'), evidence_tier=tier, policy=policy,
            claim=item.get('claim'), symptom=item.get('symptom'))
        sid = s['session_id']

    pre_call_bounds = []

    def _guard_drift():
        # #7: any error-triggered adapter response_format downgrade is a hard
        # capability drift -- never a silent downgrade.
        for c in getattr(wire, 'calls', []):
            if c.get('fallback_from'):
                raise ProtocolCapabilityDrift(
                    f'response_format capability drift at {item["cell_key"]}: '
                    f'{c.get("response_format")} (fallback from '
                    f'{c.get("fallback_from")}); halting, no silent downgrade')

    def chat(tools_=None):
        nonlocal model_served, cell_calls
        if not mock and guard is not None:
            bound = guard.check(_est_prompt_tokens(messages), cell_calls)
            pre_call_bounds.append(round(float(bound), 6))
        kw = {}
        if not mock:
            # vendor-specific extra_body (DS thinking disabled) via the frozen
            # profile; hard per-call completion cap makes the bound a bound.
            if profile.get('extra_body'):
                kw['extra_body'] = dict(profile['extra_body'])
            kw[profile.get('completion_param', 'max_tokens')] = C.COMPLETION_CAP
        if tools_:
            kw['tools'] = tools_
        else:
            # final decision turn: frozen strict ternary JSON schema; the
            # adapter maps it to the profile's response_format. NO in-cell
            # response_format retry (a 400 is a terminal fault / drift, never
            # a silent downgrade, and never a retry on a wrong prediction).
            kw['response_format'] = {'type': 'json_schema',
                                     'json_schema': TERNARY_DECISION_SCHEMA}
        n_before = len(getattr(wire, 'calls', []))
        try:
            resp = driver.chat.completions.create(
                model=model, messages=messages, temperature=C.TEMPERATURE,
                **kw)
        except Exception:
            # A capability incompatibility that drove the adapter to a
            # response_format downgrade (even one that ultimately failed) is
            # a hard protocol drift per approval #7, not a resumable error
            # row: halt the whole run, never a silent downgrade.
            _guard_drift()
            raise
        cell_calls += 1
        served = getattr(resp, 'model', None)
        if served:
            model_served = served
        u = getattr(resp, 'usage', None)
        raw_calls.append({
            'model_call': cell_calls,
            'served_model': served,
            'finish_reason': resp.choices[0].finish_reason,
            'raw_content': resp.choices[0].message.content or '',
            'tool_calls': [
                {'id': tc.id, 'name': tc.function.name,
                 'arguments': tc.function.arguments}
                for tc in (resp.choices[0].message.tool_calls or [])],
            'prompt_tokens': getattr(u, 'prompt_tokens', 0) if u else 0,
            'completion_tokens': getattr(u, 'completion_tokens', 0)
            if u else 0,
            'wire_shapes': [dict(c) for c in
                            getattr(wire, 'calls', [])[n_before:]],
        })
        _guard_drift()
        return resp

    def tally(msg):
        if getattr(msg, 'usage', None):
            usage['in'] += getattr(msg.usage, 'prompt_tokens', 0) or 0
            usage['out'] += getattr(msg.usage, 'completion_tokens', 0) or 0

    def settle():
        if not mock and guard is not None:
            din = usage['in'] - last_usage['in']
            dout = usage['out'] - last_usage['out']
            last_usage['in'], last_usage['out'] = usage['in'], usage['out']
            guard.add((din * profile.get('price_in_per_1m', 0)
                       + dout * profile.get('price_out_per_1m', 0)) / 1e6)

    guard_stop = guard_reason = ''
    msg = None
    final = ''
    try:
        msg = chat(tools)
    except BudgetGuardStop as bs:
        guard_stop, guard_reason = True, str(bs)
    if msg is not None:
        tally(msg)
        settle()
        final = msg.choices[0].message.content or ''

    turns = 0
    while (not guard_stop) and active \
            and msg.choices[0].finish_reason == 'tool_calls' \
            and turns < C.MAX_TOOL_TURNS:
        tcb = msg.choices[0].message
        messages.append(tcb.model_dump(exclude_none=True))
        for tc in (tcb.tool_calls or []):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            try:
                # (3) active HTTP session is served by g3b2_server via P3Client.
                result = ev.tool(sid, name, args, policy=policy)
            except Exception as te:
                result = {'error': f'tool {name} failed: {te}',
                          'http_status': 599}
            preview = result if isinstance(result, str) else json.dumps(result)
            if isinstance(result, dict):
                http_status = result.get('http_status', 200)
            else:
                mstat = re.search(r'http_status=(\d+)', preview or '')
                http_status = int(mstat.group(1)) if mstat else 200
            trace.append({'turn': turns, 'tool': name, 'args': args,
                          'http_status': http_status,
                          'result_preview': preview[:8000]})
            messages.append({'role': 'tool', 'tool_call_id': tc.id,
                             'content': preview[:8000]})
        turns += 1
        try:
            msg = chat(tools)
        except BudgetGuardStop as bs:
            guard_stop, guard_reason = True, str(bs)
            break
        tally(msg)
        settle()
        final = msg.choices[0].message.content or ''

    if not guard_stop and active and (
            msg.choices[0].finish_reason == 'tool_calls'
            or not (final or '').strip()):
        messages.append({'role': 'user', 'content': 'Stop calling tools now '
                         'and return your final single JSON decision.'})
        try:
            msg = chat(None)
        except BudgetGuardStop as bs:
            guard_stop, guard_reason = True, str(bs)
        else:
            tally(msg)
            settle()
            final = msg.choices[0].message.content or ''

    cost = 0.0 if mock else round(
        (usage['in'] * profile.get('price_in_per_1m', 0)
         + usage['out'] * profile.get('price_out_per_1m', 0)) / 1e6, 6)

    return {
        'protocol': 'ternary-g3b3', 'mock': bool(mock),
        'cell': item['cell_key'], 'id': item['id'],
        'instance_id': item['instance_id'], 'condition': cond,
        'evidence_tier': tier, 'policy': policy,
        'model': model, 'model_profile': profile.get('name'),
        'model_served': model_served or (model if mock else None),
        'served_artifact_id': item.get('served_artifact_id'),
        'evidence_session': sid,
        'answer_raw': final,                 # parsed only AFTER raw landing
        'raw_model_calls': raw_calls,
        'tool_trace': trace,
        'tool_calls': len(trace),
        'model_calls': cell_calls,
        'tokens_in': usage['in'], 'tokens_out': usage['out'],
        'cost_usd': cost,
        'pre_call_worst_case_bounds_usd': pre_call_bounds,
        'pre_call_budget_stop': bool(guard_stop),
        'pre_call_budget_reason': guard_reason or None,
        'wall_s': round(time.time() - t0, 2),
        '_guard_stop_internal': bool(guard_stop),
    }


# ---------------------------------------------------------------------------
# Scoring (only after the raw record has been landed)
# ---------------------------------------------------------------------------

def _escalation_bookkeeping(trace, tier):
    esc_req, esc_granted, esc_denied, reasons = [], [], [], []
    for t in trace:
        if t['tool'] == 'get_run_log' and (t.get('args') or {}).get('name') \
                in _ACCEPTANCE_LOGS:
            st, reason = t['http_status'], (t.get('args') or {}).get('reason')
            if reason:
                esc_req.append('log'); reasons.append(reason)
                (esc_granted if st == 200 else esc_denied).append('log')
            elif tier == 'D' and st in (400, 403):
                esc_denied.append('log:missing_reason' if st == 400
                                  else 'log:strict_denied')
        if t['tool'] == 'check_claim_consistency':
            st, reason = t['http_status'], (t.get('args') or {}).get('reason')
            if reason:
                esc_req.append('consistency'); reasons.append(reason)
                (esc_granted if st == 200 else esc_denied).append('consistency')
            elif tier == 'D' and st == 400:
                esc_denied.append('consistency:missing_reason')
    return esc_req, esc_granted, esc_denied, reasons


def _freshness_three_state(trace):
    """Three-state-safe freshness reading (never coerces null to false).

    Also surfaces the fields needed to detect the G3-B.1 structural defect:
    a record WITHOUT a run_tree being served fresh_state=FALSE. Under the
    repaired three-state protocol that combination can never occur (absence
    is UNKNOWN); the analyzer/livegate asserts this stays false.
    """
    out = {'state': None, 'fresh': None, 'record_run_tree_present': None,
           'status_reason': None, 'structural_false': False}
    for t in trace:
        if t['tool'] != 'check_evidence_freshness' or t['http_status'] != 200:
            continue
        try:
            obj = json.loads(t.get('result_preview') or '{}')
        except Exception:
            continue
        out['state'] = obj.get('fresh_state')
        out['fresh'] = obj.get('fresh')
        out['record_run_tree_present'] = obj.get('record_run_tree_present')
        out['status_reason'] = obj.get('status_reason')
        out['structural_false'] = (
            obj.get('fresh_state') == 'FALSE'
            and obj.get('record_run_tree_present') is False)
    return out


def _saw(tool, key, val, trace):
    return any(t['tool'] == tool and f'"{key}": {val}'
               in (t.get('result_preview') or '') for t in trace)


def score_cell(raw, item, *, prompt_fp):
    """Parse the landed raw answer and derive audit-only scored columns."""
    rec = dict(raw)
    rec.pop('_guard_stop_internal', None)
    trace = rec['tool_trace']
    tier = rec['evidence_tier']
    guard_stop = raw.get('pre_call_budget_stop')

    parsed = None if guard_stop else parse_ternary_decision(rec['answer_raw'])
    fr = _freshness_three_state(trace)

    answer_obj = {}
    if not guard_stop:
        text = (rec['answer_raw'] or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lower().startswith('json'):
                text = text[4:].strip()
        try:
            answer_obj = json.loads(text)
        except (ValueError, TypeError):
            answer_obj = {}
        if not isinstance(answer_obj, dict):
            answer_obj = {}

    esc_req, esc_granted, esc_denied, reasons = _escalation_bookkeeping(
        trace, tier)

    rec.update({
        'answer': rec['answer_raw'],
        'parsed': parsed,
        'reason': answer_obj.get('reason') if answer_obj else None,
        'missing_evidence': answer_obj.get('missing_evidence')
        if answer_obj else None,
        'evidence_gap': (str(answer_obj.get('evidence_gap')).strip().lower()
                         if answer_obj.get('evidence_gap') else None),
        'called_artifact': any(t['tool'] == 'get_test_artifact'
                               for t in trace),
        'called_linkage': any(t['tool'] == 'verify_artifact_linkage'
                              for t in trace),
        'saw_linked_false': _saw('verify_artifact_linkage', 'linked', 'false',
                                 trace),
        'called_freshness': any(t['tool'] == 'check_evidence_freshness'
                                for t in trace),
        # three-state-safe freshness columns
        'fresh_state_served': fr['state'],
        'saw_fresh_true': fr['state'] == 'TRUE',
        'saw_fresh_unknown': fr['state'] == 'UNKNOWN',
        'saw_fresh_false': fr['state'] == 'FALSE',
        'called_coverage': any(t['tool'] == 'check_test_coverage'
                               for t in trace),
        'saw_coverage_incomplete': _saw('check_test_coverage', 'complete',
                                        'false', trace),
        'called_consistency': any(t['tool'] == 'check_claim_consistency'
                                  for t in trace),
        'saw_contradicted': any('"verdict": "contradicted"'
                                in (t.get('result_preview') or '')
                                for t in trace if t['tool']
                                == 'check_claim_consistency'),
        'strict_denied_403': any(t['http_status'] == 403 for t in trace),
        'escalation_requested': esc_req,
        'escalation_granted': esc_granted,
        'escalation_denied': esc_denied,
        'escalation_reasons': reasons,
        'retries': C.RETRIES_PER_CELL,
        'version': {
            'gate': C.GATE, 'runner_version': C.G3B3_RUNNER_VERSION,
            'protocol_version': C.RUN_PROTOCOL_VERSION,
            'prompt_version': C.RUN_PROMPT_VERSION,
            'gold_cert_version': C.RUN_GOLD_CERT_VERSION,
            'prompt_fingerprint': prompt_fp,
        },
    })

    # Structured tool verdicts (three-state-safe freshness).
    tv = {}
    if rec['called_linkage']:
        tv['linkage'] = not rec['saw_linked_false']
    if rec['called_freshness']:
        tv['freshness_state'] = fr['state']
        if fr['state'] == 'TRUE':
            tv['freshness'] = True
        elif fr['state'] == 'FALSE':
            tv['freshness'] = False
    if rec['called_coverage']:
        tv['coverage'] = not rec['saw_coverage_incomplete']
    if rec['called_consistency']:
        tv['consistency'] = ('contradicted' if rec['saw_contradicted']
                             else 'consistent')
    sp = symptom_persists_from_trace(trace)
    if sp is not None:
        tv['symptom_persists'] = sp
    rec['tool_verdicts'] = tv

    # Grounded gap classification on NEED_EVIDENCE (frozen classifier).
    if not guard_stop and parsed == 'NEED_EVIDENCE':
        surface = item.get('_presented_facts')
        if surface is not None:
            rec['gap_classification'] = classify_abstention(
                rec['condition'], rec.get('evidence_gap'), surface, tv)

    if guard_stop:
        rec['error'] = (f'BudgetGuardStop: {raw.get("pre_call_budget_reason")}')
    return rec


def _spawn_g3b2_server():
    tmp_root = tempfile.mkdtemp(prefix='g3b3_store_copy_')
    shutil.copytree(str(C.G3A_STORE), tmp_root, dirs_exist_ok=True)
    httpd = GS.build_g3b2_server(tmp_root, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}', tmp_root


def run(*, live):
    assert_freeze_canonical()
    freeze = load_freeze()
    order = freeze['call_order']
    items = {(it['instance_id'], it['condition']): it for it in
             FZ.build_items()}
    fp_by_cond = {c['condition']: c['prompt_fingerprint']
                  for c in freeze['cells']}
    for o in order:
        if (o['instance_id'], o['condition']) not in items:
            raise SystemExit(f"freeze order cell missing: {o['cell_key']}")

    C.OUT_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    C.OUT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    C.OUT_TRACE_DIR.mkdir(parents=True, exist_ok=True)

    httpd, api, tmp_root = _spawn_g3b2_server()
    print(f'g3b2 evidence server {api} on ISOLATED COPY {tmp_root} '
          '(frozen G3-A store untouched)')
    print(f"server protocol_version={getattr(httpd, 'g3b2_protocol_version')}")

    total_guard = BudgetGuard(
        C.TOTAL_BUDGET_USD,
        max(p['price_in_per_1m'] for p in FZ.PROFILES.values()),
        max(p['price_out_per_1m'] for p in FZ.PROFILES.values()),
        completion_cap_tokens=C.COMPLETION_CAP,
        max_model_calls_per_cell=C.MAX_MODEL_CALLS_PER_CELL)

    files, guards, done, drivers, wire = {}, {}, {}, {}, {}
    aggregate_prior = 0.0
    for m in C.MODELS:
        prof = _profile(m)
        outp = C.OUT_LIVE_DIR / _out_name(m, not live)
        if live:
            spent, dset = _prior_spent_and_done(outp)
            aggregate_prior += spent
            files[m] = outp.open('a', encoding='utf-8')
            done[m] = dset
            drv = make_driver(_live_completions(prof), prof)
            drivers[m] = drv
            wire[m] = drv.chat.completions
            g = CompositeGuard(C.PER_MODEL_CAP_USD, total_guard,
                               prof['price_in_per_1m'],
                               prof['price_out_per_1m'],
                               completion_cap_tokens=C.COMPLETION_CAP,
                               max_model_calls_per_cell=
                               C.MAX_MODEL_CALLS_PER_CELL)
            g.spent = spent
            guards[m] = g
        else:
            files[m] = outp.open('w', encoding='utf-8')
            done[m] = set()
            guards[m] = None
            drivers[m] = wire[m] = None
    total_guard.spent = round(aggregate_prior, 8)
    if live:
        print(f'restored prior G3-B.3 live spend across models='
              f'${aggregate_prior:.4f}')

    counts = {m: {'new': 0, 'error': 0, 'skip_done': 0} for m in C.MODELS}
    stop_msg = ''
    ev = P3Client(api)
    try:
        for o in order:
            m = o['model_profile']
            ck = o['cell_key']
            if live and ck in done[m]:
                counts[m]['skip_done'] += 1
                continue
            prof = _profile(m)
            item = items[(o['instance_id'], o['condition'])]

            if total_guard.spent >= C.TOTAL_BUDGET_USD - 1e-12:
                stop_msg = (f'TOTAL cap ${C.TOTAL_BUDGET_USD:.2f} reached '
                            f'(spent ${total_guard.spent:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            if live:
                driver, guard, mock = drivers[m], guards[m], False
            else:
                scripted = ScriptedModel(item['condition'], item,
                                         prompt_version='p3-ternary-v2')
                driver = make_driver(scripted, prof)
                # the offline driver still records wire shapes through the
                # adapter, so acquire_cell's drift check has a calls list
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
            except Exception as e:  # terminal error row; NO retry
                error = f'{type(e).__name__}: {e}'
                raw = {
                    'protocol': 'ternary-g3b3', 'mock': not live,
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

            # (9) RAW responses land FIRST, before parsing/scoring.
            raw_path = C.OUT_RAW_DIR / (
                f'{m.replace("-", "_")}__'
                f'{o["serial"]:03d}__'
                + ck.replace('g3b3:', '').replace(':', '__') + '.json')
            raw_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2,
                           sort_keys=True), encoding='utf-8')

            if error is None:
                try:
                    rec = score_cell(raw, item,
                                     prompt_fp=fp_by_cond[item['condition']])
                except Exception as se:
                    # The paid call already happened and its raw is landed; a
                    # local scoring failure must NOT cause a second paid call
                    # on resume. Persist it as a terminal scoring error row.
                    rec = dict(raw)
                    rec['parsed'] = None
                    error = f'ScoringError: {type(se).__name__}: {se}'
            else:
                rec = dict(raw)
            if error is not None:
                rec['parsed'] = None
                rec['answer'] = rec.get('answer_raw', '')
                rec['error'] = error
                rec['version'] = {
                    'gate': C.GATE, 'runner_version': C.G3B3_RUNNER_VERSION,
                    'protocol_version': C.RUN_PROTOCOL_VERSION,
                    'prompt_version': C.RUN_PROMPT_VERSION,
                    'gold_cert_version': C.RUN_GOLD_CERT_VERSION,
                    'prompt_fingerprint': fp_by_cond[item['condition']]}

            # audit-only gold columns (never in the served prompt)
            cell_freeze = next(c for c in freeze['cells']
                               if c['serial'] == o['serial'])
            rec['gate'] = C.GATE
            rec['serial'] = o['serial']
            rec['expected_served_model_id'] = \
                prof['expected_served_model_id']
            rec['audit_oracle_gold'] = cell_freeze['audit_oracle_gold']
            rec['audit_condition_gold'] = cell_freeze['audit_condition_gold']
            rec['g3b_pair_cell_key'] = o['g3b_pair_cell_key']
            rec['gold_tier'] = 'PROVISIONAL'
            rec['annotators'] = 1
            rec['annotator2'] = 'NOT_OBTAINED'
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

            # Per-cell trace file.
            tdir = C.OUT_TRACE_DIR / ('live' if live else 'mock')
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
                served = rec.get('model_served')
                want = prof['expected_served_model_id']
                assert_served_model(served, want, ck)
                if rec.get('error') and 'BudgetGuardStop' in str(rec['error']):
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

    summary = {
        'gate': C.GATE, 'mode': 'live' if live else 'mock',
        'runner_version': C.G3B3_RUNNER_VERSION,
        'executed_protocol_version': C.RUN_PROTOCOL_VERSION,
        'executed_prompt_version': C.RUN_PROMPT_VERSION,
        'new_rows': {m: counts[m]['new'] for m in C.MODELS},
        'error_rows': {m: counts[m]['error'] for m in C.MODELS},
        'skipped_already_done': {m: counts[m]['skip_done']
                                 for m in C.MODELS},
        'per_model_spend_usd': {m: round(guards[m].spent, 6)
                                for m in C.MODELS} if live else
        {m: 0.0 for m in C.MODELS},
        'total_spend_usd': round(total_guard.spent if live else 0.0, 6),
        'total_hard_cap_usd': C.TOTAL_BUDGET_USD,
        'per_model_cap_usd': C.PER_MODEL_CAP_USD,
        'within_total_cap': (total_guard.spent <= C.TOTAL_BUDGET_USD + 1e-9)
        if live else True,
        'retries_per_cell': C.RETRIES_PER_CELL,
        'stop_msg': stop_msg,
        'isolated_store_copy': tmp_root,
        'gold_authority': C.GOLD_AUTHORITY,
    }
    auditp = C.OUT_LIVE_DIR / (
        f'g3b3_{"live" if live else "mock"}_run_audit.json')
    auditp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print(f'\nG3-B.3 {"LIVE" if live else "MOCK"} done: '
          f'new={sum(c["new"] for c in counts.values())} '
          f'total_spend=${summary["total_spend_usd"]:.4f} '
          f'cap=${C.TOTAL_BUDGET_USD:.2f} within='
          f'{summary["within_total_cap"]}'
          + (f' STOP: {stop_msg}' if stop_msg else ''))
    print('audit ->', auditp)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument(C.ACK, action='store_true', dest='ack')
    a = ap.parse_args()

    live = bool(a.allow_paid_run and a.ack)
    if a.allow_paid_run and not a.ack:
        raise SystemExit(f'REFUSED: --allow-paid-run also requires {C.ACK}.')
    if not a.mock and not live:
        raise SystemExit(
            'REFUSED: Gate 3-B.3 runs ONLY as --mock (offline, $0) or with '
            'the double gate --allow-paid-run ' + C.ACK + ' (conditional '
            'written approval: 100 REAL cells, TOTAL $3.00, per-model '
            '$1.50, retries 0, PROVISIONAL gold). No call was made.')
    run(live=live)


if __name__ == '__main__':
    main()
