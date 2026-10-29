"""GroundedReview Gate 3-B — External Feasibility Pilot RUNNER.

Executes the 100 frozen cells (2 models x 10 independent SymPy issues x 5
frozen evidence regimes) over the FROZEN v2 ternary protocol. The two static
regimes (T2D-T, T2A-T) are single-turn; the three active regimes
(T3D-Strict, T3D-Escalate, T3A-T) use a REAL multi-turn tool session against
an isolated, frozen copy of the evidence HTTP server (never a single-turn
text substitution).

Discipline (user instructions #6-#10), enforced in code:
  * one fresh session per active cell; real verify/freshness/coverage/log/
    consistency tools with the frozen Strict 403 wall and Escalate 400->200
    reason gate exercised by the live model itself;
  * exactly ONE scored verdict per cell; no retry on a "wrong"/unexpected
    decision, INVALID, AMBIGUOUS or transport fault (a fault is a terminal,
    resume-eligible error row);
  * the complete raw answer, reason/missing_evidence/evidence_gap, full tool
    trace, tokens, cost, wall time, actual served model id and errors are
    persisted;
  * DOUBLE explicit gate (--allow-paid-run plus the G3-B acknowledgement);
  * a composite pre-call BudgetGuard enforces BOTH the per-model $1.50 cap
    and the $3.00 TOTAL cap before EVERY model call; resume accumulates all
    prior spend;
  * served-model id drift HARD-STOPS the whole run (no substitution);
  * the evidence server serves an isolated COPY of the frozen G3-A store so
    its audit log is never appended to;
  * the freeze is never rewritten; hashes/order are verified before a run.

Offline ($0):
    uv run --python 3.13 -m evidence.g3b_run --mock
Live (needs openai, explicit approval):
    uv run --python 3.11 --with openai -m evidence.g3b_run \\
        --allow-paid-run --i-acknowledge-g3b-approved
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from evidence.ev1_adapters import make_driver
from evidence.phase3_run import (
    BudgetGuard, BudgetGuardStop, P3Client, ScriptedModel,
    TERNARY_PROMPT_VERSION_V2, PROMPT_VERSIONS, _spawn_server,
    run_ternary_cell, ternary_condition_tier_policy,
)
from evidence.ternary import read_jsonl
from evidence.g3b_freeze import (
    ACK, ACTIVE_CONDITIONS, COMPLETION_CAP, CONDITIONS, G3B, GATE,
    MAX_MODEL_CALLS_PER_CELL, MAX_TOOL_TURNS, MODELS, PER_MODEL_CAP_USD,
    PROFILES, PROMPT_VERSION, TEMPERATURE, TOTAL_BUDGET_USD, build_cells,
    canonical_bytes, build_freeze,
)
from evidence.g3b_freeze import OUT as FREEZE_PATH

RUN_DIR = G3B / 'runs'
TRACE_DIR = G3B / 'traces'
FREEZE_FORCE_REBUILD = False


def _sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def load_freeze():
    if not FREEZE_PATH.exists():
        raise SystemExit('G3-B freeze missing; run: python -m evidence.g3b_freeze')
    return json.loads(FREEZE_PATH.read_text(encoding='utf-8'))


def assert_freeze_canonical(freeze):
    canon = canonical_bytes(build_freeze())
    if _sha(FREEZE_PATH.read_bytes()) != _sha(canon):
        raise SystemExit(
            'REFUSED: on-disk G3-B freeze differs from the canonical '
            'derivation; rebuild offline and rerun preflight before any '
            'paid call.')


def _out_name(model, mock):
    safe = model.replace('.', '').replace('-', '_')
    return f'g3b_{"mock" if mock else "live"}_{safe}_results.jsonl'


class CompositeGuard:
    """Pre-call guard enforcing BOTH a per-model cap and the shared TOTAL cap.

    Presents the same interface run_ternary_cell uses (check/add/spent). The
    total cap equals the sum of the two per-model caps, but we enforce it
    explicitly on every call rather than relying on that arithmetic.
    """

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
        self.model_guard.check(prompt_tokens_now, cell_calls)
        self.total_guard.check(prompt_tokens_now, cell_calls)

    def add(self, cost):
        self.model_guard.add(cost)
        self.total_guard.add(cost)


def _profile(name):
    p = dict(PROFILES[name])
    p['name'] = name
    return p


def _live_completions(profile):
    from openai import OpenAI
    from evidence.cee_run import _load_key
    key = _load_key(profile)
    if not key:
        raise SystemExit(f"missing API key for {profile['name']} "
                         f"({profile['key_env']})")
    return OpenAI(api_key=key, base_url=profile['base_url']).chat.completions


def _prior_spent(out_path, profile, mock):
    if mock or not out_path.exists():
        return 0.0, 0
    rows = list(read_jsonl(str(out_path)))
    spent = sum(float(r.get('cost_usd') or 0) for r in rows if not r.get('mock'))
    return spent, len(rows)


def run(args, live):
    freeze = load_freeze()
    assert_freeze_canonical(freeze)
    order = freeze['call_order']
    items = {it['cell_key']: it for it in build_cells()}
    for o in order:
        if o['cell_key'] not in items:
            raise SystemExit(f"freeze order cell missing: {o['cell_key']}")

    RUN_DIR.mkdir(parents=True, exist_ok=True)
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    # Isolated COPY of the frozen store; a fresh evidence server on it.
    store_src = str(Path(__file__).resolve().parent.parent
                    / 'evidence_store_g3a' / 'store')
    tmp_root = tempfile.mkdtemp(prefix='g3b_store_copy_')
    shutil.copytree(store_src, tmp_root, dirs_exist_ok=True)
    httpd, api = _spawn_server(tmp_root)
    print(f'evidence server {api} on ISOLATED COPY {tmp_root} '
          '(frozen G3-A store untouched)')

    # Shared TOTAL guard seeded with aggregate prior spend across both models.
    total_guard = BudgetGuard(TOTAL_BUDGET_USD, 0.0, 0.0,
                              completion_cap_tokens=COMPLETION_CAP,
                              max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)
    # The total guard must price tokens; set prices lazily per call is awkward,
    # so it is used only as an absolute cumulative cap checked via the
    # composite against per-call bounds priced at the MORE EXPENSIVE vendor to
    # stay conservative regardless of which model makes the call.
    total_guard.pin = max(p['price_in_per_1m'] for p in PROFILES.values())
    total_guard.pout = max(p['price_out_per_1m'] for p in PROFILES.values())

    files, guards, done, drivers, wire = {}, {}, {}, {}, {}
    aggregate_prior = 0.0
    for m in MODELS:
        prof = _profile(m)
        outp = RUN_DIR / _out_name(m, not live)
        if live:
            # Resume: accumulate prior spend; skip terminal non-error cells.
            spent, _ = _prior_spent(outp, prof, not live)
            aggregate_prior += spent
            files[m] = outp.open('a', encoding='utf-8')
            done[m] = {r['cell'] for r in (read_jsonl(str(outp))
                                           if outp.exists() else [])
                       if not r.get('error') and not r.get('mock')}
        else:
            # A mock run is a clean, reproducible full pipeline exercise.
            spent = 0.0
            files[m] = outp.open('w', encoding='utf-8')
            done[m] = set()
        g = CompositeGuard(PER_MODEL_CAP_USD, total_guard,
                           prof['price_in_per_1m'], prof['price_out_per_1m'],
                           completion_cap_tokens=COMPLETION_CAP,
                           max_model_calls_per_cell=MAX_MODEL_CALLS_PER_CELL)
        g.spent = spent
        guards[m] = g
        if live:
            drv = make_driver(_live_completions(prof), prof)
            drivers[m] = drv
            wire[m] = drv.chat.completions
        else:
            drivers[m] = None
    total_guard.spent = round(aggregate_prior, 8)
    if live:
        print(f'restored prior G3-B live spend across models='
              f'${aggregate_prior:.4f}')

    version_meta = {
        'gate': GATE, 'prompt_version': PROMPT_VERSION,
        'freeze_manifest_sha256': _sha(FREEZE_PATH.read_bytes()),
        'g3b_runner_sha256': _sha(Path(__file__).read_bytes()),
        'temperature': TEMPERATURE, 'completion_cap_tokens': COMPLETION_CAP,
        'retries_per_cell': 0, 'mode': 'live' if live else 'mock',
    }

    counts = {m: {'new': 0, 'error': 0, 'skip_done': 0} for m in MODELS}
    stop_msg = ''
    new_rows = []
    ev = P3Client(api)
    try:
        for o in order:
            m = o['model_profile']
            ck = o['cell_key']
            if ck in done[m]:
                counts[m]['skip_done'] += 1
                continue
            prof = _profile(m)
            item = items[ck]

            if total_guard.spent >= TOTAL_BUDGET_USD - 1e-12:
                stop_msg = (f'TOTAL cap ${TOTAL_BUDGET_USD:.2f} reached '
                            f'(spent ${total_guard.spent:.4f})')
                print('BUDGET STOP ' + stop_msg)
                break

            if live:
                driver = drivers[m]
                guard = guards[m]
                mock = False
            else:
                scripted = ScriptedModel(item['condition'], item,
                                         prompt_version=PROMPT_VERSION)
                driver = make_driver(scripted, prof)
                guard = None
                mock = True

            t0 = time.time()
            try:
                rec = run_ternary_cell(
                    driver, prof['model'], item, ev, prof, mock=mock,
                    max_tool_turns=MAX_TOOL_TURNS,
                    budget_guard=guard, completion_cap=COMPLETION_CAP,
                    version_meta=version_meta, prompt_version=PROMPT_VERSION,
                    trace_dir=str(TRACE_DIR / ('mock' if not live else 'live')))
            except Exception as e:  # terminal error row; NO retry
                rec = {
                    'protocol': 'ternary', 'mock': not live, 'cell': ck,
                    'id': item['id'], 'instance_id': item['instance_id'],
                    'condition': item['condition'], 'gate': GATE,
                    'model': prof['model'], 'model_profile': m,
                    'model_served': None, 'tokens_in': 0, 'tokens_out': 0,
                    'cost_usd': 0.0, 'tool_trace': [], 'tool_calls': 0,
                    'model_calls': 0, 'parsed': None,
                    'version': dict(version_meta),
                    'error': f'{type(e).__name__}: {e}',
                }
                print('ERROR', ck, rec['error'][:200])

            rec['gate'] = GATE
            rec['serial'] = o['serial']
            rec['expected_served_model_id'] = \
                prof['expected_served_model_id']
            rec['served_artifact_id'] = item['served_artifact_id']
            # Audit-only gold columns for the offline analyzer. These are read
            # from the item's private audit keys and are NEVER present in the
            # served prompt (the freeze/preflight leakage audit verifies that).
            rec['audit_oracle_gold'] = item['_oracle_gold']
            rec['audit_condition_gold'] = item['_condition_gold']
            rec['retries'] = 0
            rec['wall_s'] = round(time.time() - t0, 2)
            if live:
                rec['adapter_wire_calls'] = [dict(c) for c in
                                             getattr(wire[m], 'calls', [])]
                wire[m].calls.clear()

            files[m].write(json.dumps(rec, ensure_ascii=False) + '\n')
            files[m].flush()
            new_rows.append(rec)
            counts[m]['new'] += 1
            if rec.get('error'):
                counts[m]['error'] += 1

            # Served-model id drift: hard stop for the WHOLE run.
            if live:
                served = rec.get('model_served')
                want = prof['expected_served_model_id']
                if served and served != want:
                    raise SystemExit(
                        f'SERVED MODEL DRIFT STOP {m}: expected {want}, '
                        f'got {served} at {ck}; halting, no substitution.')
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

    summary = {
        'gate': GATE, 'live': live,
        'new_rows': {m: counts[m]['new'] for m in MODELS},
        'error_rows': {m: counts[m]['error'] for m in MODELS},
        'skipped_already_done': {m: counts[m]['skip_done'] for m in MODELS},
        'per_model_spend_usd': {m: round(guards[m].spent, 6)
                               for m in MODELS},
        'total_spend_usd': round(total_guard.spent, 6),
        'total_hard_cap_usd': TOTAL_BUDGET_USD,
        'per_model_cap_usd': PER_MODEL_CAP_USD,
        'within_total_cap': total_guard.spent <= TOTAL_BUDGET_USD + 1e-9,
        'stop_msg': stop_msg,
        'isolated_store_copy': tmp_root,
    }
    auditp = RUN_DIR / f'g3b_{"live" if live else "mock"}_run_audit.json'
    auditp.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print(f'\nG3-B {"LIVE" if live else "MOCK"} done: '
          f'new={sum(c["new"] for c in counts.values())} '
          f'total_spend=${total_guard.spent:.4f} cap=${TOTAL_BUDGET_USD:.2f} '
          f'within={summary["within_total_cap"]}'
          + (f' STOP: {stop_msg}' if stop_msg else ''))
    print('audit ->', auditp)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mock', action='store_true')
    ap.add_argument('--allow-paid-run', action='store_true')
    ap.add_argument(ACK, action='store_true', dest='ack')
    a = ap.parse_args()

    live = bool(a.allow_paid_run and a.ack)
    if a.allow_paid_run and not a.ack:
        raise SystemExit(f'REFUSED: --allow-paid-run also requires {ACK}.')
    if not a.mock and not live:
        raise SystemExit(
            'REFUSED: Gate 3-B runs ONLY as --mock (offline, $0) or with the '
            'double gate --allow-paid-run ' + ACK + ' (conditional written '
            'approval: 100 cells, TOTAL $3.00, per-model $1.50, PROVISIONAL '
            'gold). No call was made.')
    run(a, live)


if __name__ == '__main__':
    main()
