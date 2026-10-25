"""E1 thin runner (External Validation, offline preparation).

Reuses the FROZEN Wave-2.1 execution machinery unchanged
(``build_ternary_cells`` / ``run_ternary_cell`` / ``P3Client`` /
``BudgetGuard`` / ``_spawn_server``) and only changes what E1 requires:

  * model construction goes through evidence.ev1_adapters (profile-driven
    wire adaptation; task semantics, prompts, tools and scoring untouched);
  * every input defaults to the frozen Wave-2.1 store and fixture/gold/raw
    lists, and EVERY output is forced into the independent
    ``evidence_store_ev1`` namespace (the runner refuses to write anywhere
    else), so no Phase-1/2/3 or Wave-2/2.1 file can ever be modified;
  * the evidence HTTP server always serves an isolated COPY of the store
    (even for a future approved live run), so the frozen store's audit log
    is never appended to;
  * result rows carry extra version identity (ev1 namespace + model
    profile) for the paired cross-model analysis.

Offline use (zero network, zero cost), 22 fixtures x 5 conditions:
    uv run --python 3.11 --with openai -m evidence.ev1_run --mock \
        --spawn-server --store evidence_store_w21 \
        --fixtures evidence_store_w21/phase2_fixtures.jsonl,\
evidence_store_w21/phase3_fixtures.jsonl,evidence_store_w21/wave2_fixtures.jsonl \
        --raw evidence_store_w21/wave2_pilot_raw_rows.jsonl

A live (paid) run is NOT authorised by this module's existence; it must be
explicitly approved and then invoked with --model-profile <name>.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from evidence.phase3_run import (
    BudgetGuard, P3Client, ScriptedModel, TERNARY_CONDITIONS,
    TERNARY_PROMPT_VERSION_V2, PROMPT_VERSIONS,
    build_ternary_cells, fixture_manifest_identity, read_jsonl,
    run_ternary_cell, summarize_run_audit, ternary_condition_tier_policy,
    _sha256_text_normalized, _spawn_server,
)
from evidence.ev1_adapters import (
    DEFAULT_PROFILES, load_ev1_profile, make_live_driver, make_driver,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EV1_DIR = ROOT / 'evidence_store_ev1'
W21_STORE = 'evidence_store_w21'

DEFAULT_FIXTURES = ','.join([
    f'{W21_STORE}/phase2_fixtures.jsonl',
    f'{W21_STORE}/phase3_fixtures.jsonl',
    f'{W21_STORE}/wave2_fixtures.jsonl',
])
DEFAULT_RAW = f'{W21_STORE}/wave2_pilot_raw_rows.jsonl'
DEFAULT_GOLD = f'{W21_STORE}/wave2_gold.jsonl'


def _ev1_path(p):
    """Resolve and enforce the independent ev1 output namespace."""
    path = Path(p)
    if not path.is_absolute():
        path = ROOT / path
    try:
        path.resolve().relative_to(EV1_DIR.resolve())
    except ValueError:
        raise SystemExit(
            f'E1 SAFETY: output/audit path must live under '
            f'{EV1_DIR.relative_to(ROOT)}, got {p}')
    return path


def _load_cells(a, store):
    fixtures = []
    for fp in a.fixtures.split(','):
        fp = fp.strip()
        if fp:
            fixtures.extend(list(read_jsonl(fp)))
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    missing_raw = sorted({f['id'] for f in fixtures} - set(raw_by_id))
    if missing_raw:
        raise SystemExit(f'raw rows missing for ids: {missing_raw}')
    conds = tuple(x.strip() for x in a.conditions.split(',') if x.strip())
    for c in conds:
        ternary_condition_tier_policy(c)
    cells = build_ternary_cells(fixtures, raw_by_id, store, conds)
    if a.only_cells:
        only = {x.strip() for x in a.only_cells.split(',') if x.strip()}
        cells = [c for c in cells if c['cell_key'] in only]
        missing = only - {c['cell_key'] for c in cells}
        if missing:
            raise SystemExit(f'--only-cells missing: {sorted(missing)}')
    if a.prompt_version == TERNARY_PROMPT_VERSION_V2:
        # Same frozen pure projection phase3_run.main computes (v2 only).
        from evidence.visibility import load_fixture_facts, project_surface
        fx_by_aid = {f['served_artifact_id']: f for f in fixtures}
        facts_cache = {}
        for item in cells:
            aid = item['served_artifact_id']
            if aid not in facts_cache:
                facts_cache[aid] = load_fixture_facts(store, fx_by_aid[aid])
            item['_presented_facts'] = project_surface(
                item['condition'], facts_cache[aid])
    return cells, conds


def _sha256_file(path):
    import hashlib
    p = Path(path)
    if not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _version_meta(a):
    fixture_paths = [x.strip() for x in a.fixtures.split(',') if x.strip()]
    gold_hash = (_sha256_text_normalized(a.gold)
                 if Path(a.gold).exists() else None)
    return {
        'prompt_version': a.prompt_version,
        'gold_sha256': gold_hash,
        'fixture_manifest': fixture_manifest_identity(fixture_paths),
        'gold_path': a.gold,
        'ev1_namespace': 'evidence_store_ev1',
        'ev1_adapter': 'evidence/ev1_adapters.py',
        'ev1_adapter_sha256': _sha256_file(HERE / 'ev1_adapters.py'),
        'ev1_runner_sha256': _sha256_file(HERE / 'ev1_run.py'),
        'ev1_model_profile': None if a.mock else a.model_profile,
        'ev1_profiles_path': a.profiles,
        'ev1_profiles_sha256': _sha256_file(a.profiles),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=W21_STORE)
    ap.add_argument('--fixtures', default=DEFAULT_FIXTURES)
    ap.add_argument('--raw', default=DEFAULT_RAW)
    ap.add_argument('--gold', default=DEFAULT_GOLD)
    ap.add_argument('--conditions', default=','.join(TERNARY_CONDITIONS))
    ap.add_argument('--profiles', default=str(DEFAULT_PROFILES))
    ap.add_argument('--model-profile', default='openai_gpt41_mini')
    ap.add_argument('--model', default='')
    ap.add_argument('--output', default='')
    ap.add_argument('--audit-out', default='')
    ap.add_argument('--max-tool-turns', type=int, default=8)
    ap.add_argument('--token-budget', type=int, default=0)
    ap.add_argument('--emergency-tokens', type=int, default=120_000)
    ap.add_argument('--max-budget-usd', type=float, default=1.0)
    ap.add_argument('--completion-cap', type=int, default=8192)
    ap.add_argument('--max-model-calls-per-cell', type=int, default=12)
    ap.add_argument('--prompt-version', default=TERNARY_PROMPT_VERSION_V2,
                    choices=PROMPT_VERSIONS)
    ap.add_argument('--mock', action='store_true',
                    help='scripted deterministic model; zero API cost')
    ap.add_argument('--spawn-server', action='store_true')
    ap.add_argument('--api', default='http://127.0.0.1:8321')
    ap.add_argument('--mock-trace-dir',
                    default='evidence_store_ev1/ev1_mock_traces')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--only-cells', default='',
                    help='comma-separated cell keys to run; only these cells')
    ap.add_argument('--allow-paid-run', action='store_true',
                    help='REQUIRED for any real (paid) API run; refused '
                         'otherwise so a live call can never happen by '
                         'accident')
    ap.add_argument('--adapter-check', action='store_true',
                    help='offline: run the FULL live chat closure with a '
                         'RecordingCompletions-wrapped ScriptedModel (zero '
                         'network), asserting the profile-adapted kwargs for '
                         'every condition; writes no result rows')
    a = ap.parse_args()

    # Force every E1 output into the independent ev1 namespace.
    tag = 'mock' if a.mock else a.model_profile
    outp = _ev1_path(a.output or f'evidence_store_ev1/ev1_{tag}_results.jsonl')
    audit_out = _ev1_path(
        a.audit_out or f'evidence_store_ev1/ev1_{tag}_run_audit.json')
    trace_dir = _ev1_path(a.mock_trace_dir) if a.mock else None
    outp.parent.mkdir(parents=True, exist_ok=True)

    from evidence.store import ArtifactStore
    store = ArtifactStore(a.store)
    cells, conds = _load_cells(a, store)
    version_meta = _version_meta(a)

    print(f'cells={len(cells)} conditions={conds} mock={a.mock} '
          f'profile={a.model_profile} prompt={a.prompt_version}')
    if a.dry_run:
        for c in cells:
            print(' ', c['cell_key'])
        return

    # Always serve an isolated COPY: the frozen store and its audit log are
    # never modified by E1 (offline mock or future approved live run).
    httpd = None
    audit_path = str(Path(tempfile.gettempdir()) / 'ev1_unused_audit.jsonl')
    if a.spawn_server:
        tmp_root = tempfile.mkdtemp(prefix='ev1_store_copy_')
        shutil.copytree(a.store, tmp_root, dirs_exist_ok=True)
        httpd, a.api = _spawn_server(tmp_root)
        audit_path = httpd.audit_path
        print(f'spawned evidence server at {a.api} on ISOLATED COPY '
              f'{tmp_root} (frozen store untouched)')

    if a.adapter_check:
        # Full live closure, zero network: ScriptedModel is wrapped by the
        # profile RecordingCompletions, run_ternary_cell is called with
        # mock=False so the exact kwarg mapping for a REAL vendor executes.
        from evidence.ev1_adapters import load_ev1_profiles
        ev = P3Client(a.api)
        profiles = {n: load_ev1_profile(n, a.profiles)
                    for n in load_ev1_profiles(a.profiles)}
        # one representative cell per condition covers all 5 permission paths
        seen_cond = set()
        sample_cells = []
        for c in cells:
            if c['condition'] not in seen_cond:
                seen_cond.add(c['condition'])
                sample_cells.append(c)
        if seen_cond != set(conds):
            raise SystemExit(f'adapter-check missing conditions: {seen_cond}')
        total_assertions = 0
        failures = []
        for pname, prof in profiles.items():
            for item in sample_cells:
                scripted = ScriptedModel(item['condition'], item,
                                         prompt_version=a.prompt_version)
                driver = make_driver(scripted, prof)
                rec = run_ternary_cell(
                    driver, prof['model'], item, ev, prof, mock=False,
                    max_tool_turns=a.max_tool_turns,
                    budget_guard=None, completion_cap=a.completion_cap,
                    version_meta=version_meta,
                    prompt_version=a.prompt_version)
                calls = driver.chat.completions.calls
                if not calls:
                    failures.append(f'{pname}/{item["condition"]}: no calls')
                    continue
                expected_param = prof['completion_param']
                expected_rf = prof['response_format']
                for i, cal in enumerate(calls):
                    total_assertions += 1
                    if cal['completion_param'] != expected_param:
                        failures.append(
                            f'{pname}/{item["condition"]} call{i}: cap param '
                            f'{cal["completion_param"]} != {expected_param}')
                    total_assertions += 1
                    if 'thinking' in cal['extra_body_keys']:
                        failures.append(
                            f'{pname}/{item["condition"]} call{i}: deepseek '
                            f'thinking body leaked')
                    total_assertions += 1
                    want_temp = prof.get('temperature_supported', True)
                    if cal['temperature_present'] != want_temp:
                        failures.append(
                            f'{pname}/{item["condition"]} call{i}: temp '
                            f'present={cal["temperature_present"]} '
                            f'expected {want_temp}')
                # Decision-turn mode: the runner only attaches response_format
                # on a call WITHOUT tools. ScriptedModel sometimes returns its
                # final JSON while still on the last tool turn (finish=stop),
                # in which case there is no dedicated decision call; that is a
                # mock artefact (a live model gets the explicit stop nudge),
                # so assert the declared mode only on the actual no-tools call.
                decision_calls = [c for c in calls if not c['has_tools']]
                if decision_calls:
                    final_mode = decision_calls[-1]['response_format']
                    total_assertions += 1
                    if final_mode != expected_rf \
                            and decision_calls[-1]['fallback_from'] is None:
                        failures.append(
                            f'{pname}/{item["condition"]}: decision mode '
                            f'{final_mode} != {expected_rf}')
                else:
                    final_mode = 'n/a (scripted final on tool turn)'
                print(f'{pname} {item["condition"]}: parsed={rec["parsed"]} '
                      f'model_calls={rec["model_calls"]} '
                      f'tool_calls={rec["tool_calls"]} '
                      f'decision_calls={len(decision_calls)} '
                      f'final_rf={final_mode}')
        if httpd is not None:
            httpd.shutdown()
        print(f'\nadapter-check: profiles={len(profiles)} '
              f'conditions={len(conds)} assertions={total_assertions} '
              f'failures={len(failures)}')
        if failures:
            for fmsg in failures:
                print('FAIL', fmsg)
            raise SystemExit('adapter-check FAILED')
        print('adapter-check PASSED (zero network, zero paid calls)')
        return

    if a.mock:
        model = 'scripted-mock'
        profile = {'name': 'mock'}
        ev = P3Client(a.api)
        n_err = 0
        with outp.open('a', encoding='utf-8') as f:
            for item in cells:
                driver = type('D', (), {})()
                driver.chat = type('C', (), {})()
                driver.chat.completions = ScriptedModel(
                    item['condition'], item, prompt_version=a.prompt_version)
                try:
                    rec = run_ternary_cell(
                        driver, model, item, ev, profile, mock=True,
                        max_tool_turns=a.max_tool_turns,
                        trace_dir=str(trace_dir), version_meta=version_meta,
                        prompt_version=a.prompt_version)
                except Exception as e:
                    n_err += 1
                    rec = {'cell': item['cell_key'],
                           'condition': item['condition'],
                           'mock': True, 'protocol': 'ternary',
                           'version': dict(version_meta),
                           'error': f'{type(e).__name__}: {e}'}
                    print('ERROR', rec['cell'], rec['error'][:200])
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                if 'error' not in rec:
                    print(rec['cell'], rec['parsed'],
                          f"tools={rec['tool_calls']} "
                          f"403={rec['strict_denied_403']} "
                          f"granted={rec['escalation_granted']}")
        if httpd is not None:
            httpd.shutdown()
        print(f'E1 mock done: cells={len(cells)} failed_cells={n_err} '
              f'spend=$0.0 output={outp}')
        if n_err:
            raise SystemExit('E1 mock had failed cells')
        return

    # ---------------- live path: explicit approval gate ----------------
    if not a.allow_paid_run:
        raise SystemExit(
            'REFUSED: a real paid API run requires --allow-paid-run and an '
            'explicit user authorisation. No call was made.')
    profile = load_ev1_profile(a.model_profile, a.profiles)
    model = a.model or profile['model']
    driver = make_live_driver(profile)          # raises if no API key
    wire_calls = driver.chat.completions       # RecordingCompletions
    ev = P3Client(a.api)
    prior = list(read_jsonl(str(outp))) if outp.exists() else []
    # resume key includes the model profile so different models never share
    done = {r['cell'] for r in prior
            if not r.get('error') and not r.get('mock')
            and (r.get('model_profile') or r.get('model'))
            in (a.model_profile, model)}
    spent = sum(float(r.get('cost_usd') or 0) for r in prior
                if not r.get('mock')
                and (r.get('model_profile') or r.get('model'))
                in (a.model_profile, model))
    guard = BudgetGuard(a.max_budget_usd,
                        profile.get('price_in_per_1m', 0),
                        profile.get('price_out_per_1m', 0),
                        completion_cap_tokens=a.completion_cap,
                        max_model_calls_per_cell=a.max_model_calls_per_cell)
    guard.spent = spent
    n_err = n_budget_stop = 0
    batch_stop = False
    session_cells = {}
    new_rows = []
    with outp.open('a', encoding='utf-8') as f:
        for item in cells:
            if item['cell_key'] in done:
                continue
            if guard.spent >= a.max_budget_usd:
                batch_stop = True
                print(f'BATCH BUDGET STOP: ${guard.spent:.4f}')
                break
            try:
                rec = run_ternary_cell(
                    driver, model, item, ev, profile,
                    max_tool_turns=a.max_tool_turns,
                    token_budget=a.token_budget,
                    emergency_tokens=a.emergency_tokens,
                    budget_guard=guard, completion_cap=a.completion_cap,
                    version_meta=version_meta,
                    prompt_version=a.prompt_version)
            except Exception as e:
                n_err += 1
                rec = {'protocol': 'ternary', 'mock': False,
                       'cell': item['cell_key'], 'id': item['id'],
                       'condition': item['condition'],
                       'policy': ternary_condition_tier_policy(
                           item['condition'])[2],
                       'scenario': item.get('scenario'), 'model': model,
                       'model_profile': a.model_profile,
                       'model_served': None,
                       'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                       'tool_calls': 0, 'tool_trace': [],
                       'version': dict(version_meta),
                       'error': f'{type(e).__name__}: {e}'}
                print('ERROR', rec['cell'], rec['error'][:200])
            # Snapshot the exact wire kwargs the adapter sent on every model
            # call for this cell (content-free): cap param, response_format
            # mode and any 400-driven downgrade chain, for the smoke audit.
            rec['adapter_wire_calls'] = [
                dict(c) for c in getattr(wire_calls, 'calls', [])]
            wire_calls.calls.clear()
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            new_rows.append(rec)
            if rec.get('evidence_session'):
                session_cells[rec['evidence_session']] = {
                    'cell': rec.get('cell'), 'condition': rec.get('condition')}
            if rec.get('pre_call_budget_stop'):
                n_budget_stop += 1
            elif 'error' not in rec:
                print(rec['cell'], rec['parsed'],
                      f"tools={rec['tool_calls']} calls={rec.get('model_calls')} "
                      f"in={rec['tokens_in']} out={rec['tokens_out']} "
                      f"${rec['cost_usd']:.4f} cum=${guard.spent:.4f} "
                      f"model={rec.get('model_served')}")

    run_audit = summarize_run_audit(audit_path, session_cells)
    summary = {
        'protocol': 'ternary', 'mock': False, 'model': model,
        'model_profile': a.model_profile,
        'cells_planned': len(cells), 'cells_already_done': len(done),
        'cells_attempted_this_process': len(new_rows),
        'error_cells': n_err, 'budget_stop_cells': n_budget_stop,
        'batch_budget_stop': batch_stop,
        'budget_cap_usd': a.max_budget_usd,
        'cumulative_spend_usd': round(guard.spent, 6),
        'completion_cap_tokens': a.completion_cap,
        'version': version_meta, 'server_audit': run_audit,
    }
    audit_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                         encoding='utf-8')
    if httpd is not None:
        httpd.shutdown()
    print(f'E1 live done: failed={n_err} budget_stops={n_budget_stop} '
          f'cumulative_spend=${guard.spent:.4f} audit={audit_out}')


if __name__ == '__main__':
    main()
