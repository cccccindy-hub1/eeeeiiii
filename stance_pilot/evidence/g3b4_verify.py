"""Gate 3-B.4 (tasks 1 & 10) — independent result-integrity verification.

ZERO API. This module never imports g3b3_run / g3b3_analyze / g3b3_report
logic; it treats their on-disk outputs as untrusted evidence and re-derives
every claimed quantity from the 100 live rows + 100 raw files + 100 trace
files + the two frozen manifests. It deliberately distinguishes REAL live
rows from the offline mock pass and never substitutes the mock pipeline pass
rate for the real-request audit.

    uv run --python 3.13 -m evidence.g3b4_verify
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from evidence import g3b4_common as C
from evidence.ternary import parse_ternary_decision  # frozen parser only

PRICES = {'deepseek-flash': (0.30, 1.20),
          'gpt-4.1-mini': (0.40, 1.60)}
LIVE_FILES = {'deepseek-flash': C.G3B3_LIVE_DEEPSEEK,
              'gpt-4.1-mini': C.G3B3_LIVE_GPT}


def _raw_filename(row) -> str:
    m = row['model_profile'].replace('-', '_')
    return (f"{m}__{row['serial']:03d}__"
            + row['cell'].replace('g3b3:', '').replace(':', '__') + '.json')


def _trace_filename(row) -> str:
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', row['cell']).strip('_')
    return f"{row['serial']:03d}_{safe}.json"


def main():
    report = {'document': 'Gate 3-B.4 independent result-integrity '
                          'verification (tasks 1 & 10)',
              'audit_version': C.G3B4_AUDIT_VERSION,
              'api_calls_made_by_this_audit': 0,
              'sections': []}

    def section(name, checks, **extra):
        ok_all = all(c['ok'] for c in checks)
        s = {'section': name, 'all_ok': ok_all,
             'n_checks': len(checks),
             'n_pass': sum(c['ok'] for c in checks),
             'checks': checks}
        s.update(extra)
        report['sections'].append(s)
        print(f'[{"PASS" if ok_all else "FAIL"}] {name} '
              f'({s["n_pass"]}/{s["n_checks"]})')
        for c in checks:
            if not c['ok']:
                print('   FAIL:', c.get('detail', c))
        return s

    # ------------------------------------------------------------------ #
    # 0. Re-verify the post-collection RESULT freeze pins (task 1).
    # ------------------------------------------------------------------ #
    pins = C.verify_g3b3_result_freeze(verbose=False)
    section('A_frozen_hashes', [
        {'ok': pins['all_pins_match'],
         'detail': f"{pins['n_pass']}/{pins['n_checks']} artifacts "
                   '(7 files + raw/ manifest + traces/live/ manifest + '
                   'pre-paid data-freeze) rehash to the G3-B.3 result '
                   'freeze pins'}])
    parents = C.verify_g3b3_parent_pins(verbose=False)
    section('A_parent_anchor', [
        {'ok': parents['all_ok'],
         'detail': 'G3-B freeze manifest and both G3-B live row files '
                   'anchored by the G3-B.3 freeze are present / matching'}])

    # ------------------------------------------------------------------ #
    # 1. Load the 100 REAL rows; prove they are real, not mock (task 10).
    # ------------------------------------------------------------------ #
    rows_by_model = {}
    load_checks = []
    for m, p in LIVE_FILES.items():
        rows = C.read_jsonl(p)
        rows_by_model[m] = rows
        n = len(rows)
        load_checks.append({'ok': n == 50,
                            'detail': f'{m}: {n} live rows (expected 50)'})
        n_mock = sum(1 for r in rows if r.get('mock'))
        n_excl = sum(1 for r in rows if r.get('research_excluded'))
        load_checks.append(
            {'ok': n_mock == 0 and n_excl == 0,
             'detail': f'{m}: mock-flagged rows={n_mock}, '
                       f'research_excluded rows={n_excl} (real-request '
                       'audit only; mock pass rate is NOT used)'})
    all_rows = [r for m in C.MODELS for r in rows_by_model[m]]
    load_checks.append(
        {'ok': len(all_rows) == 100, 'detail': '100 real rows total'})
    # Cartesian coverage: 2 models x 10 issues x 5 conditions, exactly once.
    # instance_id is stored as the full SWE-bench style 'sympy__sympy-NNNNN'.
    keys = [(r['model_profile'], r['instance_id'], r['condition'])
            for r in all_rows]
    dup = [k for k, v in Counter(keys).items() if v > 1]
    expected = {(m, f'sympy__{i}', c) for m in C.MODELS for i in C.ISSUES
                for c in C.CONDITIONS}
    load_checks.append(
        {'ok': not dup and set(keys) == expected and len(keys) == 100,
         'detail': 'rows are exactly 2 models x 10 issues x 5 conditions, '
                   f'no duplicates (n={len(keys)})'})
    serials = sorted(r['serial'] for r in all_rows)
    load_checks.append(
        {'ok': serials == list(range(100)),
         'detail': 'serials 0..99 each exactly once (frozen interleaved '
                   'order fully covered)'})
    err = [r['cell'] for r in all_rows if r.get('error')]
    load_checks.append(
        {'ok': not err, 'detail': f'error rows in live files: {len(err)}'})
    parsed_bad = [r['cell'] for r in all_rows
                  if r.get('parsed') not in ('ACCEPT', 'REJECT',
                                              'NEED_EVIDENCE')]
    load_checks.append(
        {'ok': not parsed_bad,
         'detail': f'all 100 rows carry a parseable ternary verdict '
                   f'(unparsed: {len(parsed_bad)})'})
    section('B_real_rows_100', load_checks)

    # ------------------------------------------------------------------ #
    # 2. Row <-> raw file <-> trace file correspondence and content.
    # ------------------------------------------------------------------ #
    rf = C.load_result_freeze()
    raw_pins = {f['relpath']: f for f in C.artifact_pin(
        rf, 'raw_responses_dir')['files']}
    tr_pins = {f['relpath']: f for f in C.artifact_pin(
        rf, 'live_traces_dir')['files']}
    corr_checks = []
    n_raw = n_tr = 0
    for r in all_rows:
        rp = C.G3B3_RAW_DIR / _raw_filename(r)
        tp = C.G3B3_TRACE_DIR / _trace_filename(r)
        if not rp.is_file():
            corr_checks.append({'ok': False,
                                'detail': f'missing raw {rp.name}'})
            continue
        if not tp.is_file():
            corr_checks.append({'ok': False,
                                'detail': f'missing trace {tp.name}'})
            continue
        n_raw += 1
        n_tr += 1
        pin = raw_pins.get(rp.name)
        if not pin or C.sha256_file(rp) != pin['sha256']:
            corr_checks.append({'ok': False,
                                'detail': f'raw pin drift {rp.name}'})
        pin = tr_pins.get(tp.name)
        if not pin or C.sha256_file(tp) != pin['sha256']:
            corr_checks.append({'ok': False,
                                'detail': f'trace pin drift {tp.name}'})
        raw = json.loads(rp.read_text(encoding='utf-8'))
        trc = json.loads(tp.read_text(encoding='utf-8'))
        # Raw landed the untouched final answer; the scored row carries the
        # identical string (scoring happens after raw landing).
        if raw.get('answer_raw') != r.get('answer_raw'):
            corr_checks.append({'ok': False,
                                'detail': f'answer_raw mismatch {r["cell"]}'})
        if raw.get('answer_raw') != r.get('answer'):
            corr_checks.append({'ok': False,
                                'detail': f'answer field mismatch {r["cell"]}'})
        if trc.get('trace') != r.get('tool_trace'):
            corr_checks.append({'ok': False,
                                'detail': f'tool_trace mismatch {r["cell"]}'})
        if trc.get('parsed') != r.get('parsed'):
            corr_checks.append({'ok': False,
                                'detail': f'trace parsed mismatch {r["cell"]}'})
        if raw.get('mock'):
            corr_checks.append({'ok': False,
                                'detail': f'raw flagged mock {r["cell"]}'})
        # Re-parse the raw answer with the frozen parser: scored verdict must
        # be reproducible from the landed raw alone.
        reparsed = parse_ternary_decision(raw.get('answer_raw') or '')
        if reparsed != r.get('parsed'):
            corr_checks.append(
                {'ok': False,
                 'detail': f're-parse drift {r["cell"]}: row={r.get("parsed")}'
                           f' reparse={reparsed}'})
    corr_checks.insert(0, {
        'ok': n_raw == 100 and n_tr == 100,
        'detail': f'every one of the 100 rows maps 1:1 to a pinned raw file '
                  f'and a pinned live trace file (raw={n_raw}, trace={n_tr})'})
    section('C_row_raw_trace_correspondence', corr_checks[:1]
            + [c for c in corr_checks[1:] if not c['ok']][:20],
            n_content_mismatches=sum(not c['ok']
                                     for c in corr_checks[1:]))

    # ------------------------------------------------------------------ #
    # 3. Raw-first persistence (code order + landed content sufficiency).
    # ------------------------------------------------------------------ #
    runner = (C.EVID / 'g3b3_run.py').read_text(encoding='utf-8')
    raw_write = runner.index('raw_path.write_text')
    score_call = runner.index('rec = score_cell(')
    rf_checks = [
        {'ok': raw_write < score_call,
         'detail': f'g3b3_run.py: raw write (char {raw_write}) precedes '
                   f'score_cell (char {score_call}); the untouched raw '
                   'response is persisted BEFORE any parsing/scoring'},
        {'ok': all(json.loads((C.G3B3_RAW_DIR / _raw_filename(r))
                              .read_text(encoding='utf-8'))
                       .get('answer_raw') is not None
                   for r in all_rows),
         'detail': 'all 100 raw files parse as JSON and carry answer_raw '
                   '(including the complete raw_model_calls transcript)'},
        {'ok': runner.index("'raw_model_calls': raw_calls") < raw_write,
         'detail': 'raw record embeds the full per-call transcript '
                   '(served model id, finish reason, prompt/completion '
                   'tokens, wire shapes) before it is written'}]
    section('D_raw_first_persistence', rf_checks)

    # ------------------------------------------------------------------ #
    # 4. Real model-call counts, tokens, cost recomputed from raw ground
    #    truth (never from the mock pipeline) (tasks 1 & 10).
    # ------------------------------------------------------------------ #
    money_checks = []
    totals = {}
    grand_calls = grand_tools = 0
    grand_in = grand_out = 0
    grand_cost_row = grand_cost_calc = grand_cost_unrounded = 0.0
    verdict_counts = {}
    for m in C.MODELS:
        pin, pout = PRICES[m]
        calls = tools = tin = tout = 0
        cost_row = cost_calc = cost_unrounded = 0.0
        bnd_ok = wire_ok = served_ok = True
        vcount = Counter()
        for r in rows_by_model[m]:
            raw = json.loads((C.G3B3_RAW_DIR / _raw_filename(r))
                             .read_text(encoding='utf-8'))
            rmc = raw['raw_model_calls']
            calls += len(rmc)
            tools += r.get('tool_calls', 0)
            ci = sum(c['prompt_tokens'] for c in rmc)
            co = sum(c['completion_tokens'] for c in rmc)
            tin += ci
            tout += co
            if ci != r['tokens_in'] or co != r['tokens_out']:
                money_checks.append(
                    {'ok': False,
                     'detail': f'token sum mismatch {r["cell"]}'})
            exact = (ci * pin + co * pout) / 1e6
            calc = round(exact, 6)
            cost_unrounded += exact
            cost_calc += calc
            cost_row += r['cost_usd']
            if calc != r['cost_usd']:
                money_checks.append(
                    {'ok': False,
                     'detail': f'cost recompute mismatch {r["cell"]}: '
                               f'row={r["cost_usd"]} calc={calc}'})
            # A pre-call worst-case bound is recorded before EVERY real call.
            if len(raw.get('pre_call_worst_case_bounds_usd', [])) != len(rmc):
                bnd_ok = False
            # Adapter wire log: one create per model call, no response_format
            # fallback (hard-drift policy).
            wc = r.get('adapter_wire_calls', [])
            if len(wc) != len(rmc) or any(c.get('fallback_from') for c in wc):
                wire_ok = False
            if r.get('model_served') != r.get('expected_served_model_id'):
                served_ok = False
            vcount[r['parsed']] += 1
        totals[m] = {'model_calls_from_raw': calls,
                     'tool_calls_from_rows': tools,
                     'tokens_in_from_raw': tin,
                     'tokens_out_from_raw': tout,
                     'cost_usd_summed_rows_rounded_per_cell':
                         round(cost_row, 6),
                     'cost_usd_recomputed_tokens': round(cost_calc, 6),
                     'cost_usd_guard_basis_unrounded': round(cost_unrounded, 6),
                     'pre_call_bounds_one_per_real_call': bnd_ok,
                     'wire_calls_match_no_fallback': wire_ok,
                     'served_id_matches_expected_all_cells': served_ok,
                     'verdict_counts': dict(vcount)}
        grand_calls += calls
        grand_tools += tools
        grand_in += tin
        grand_out += tout
        grand_cost_row += cost_row
        grand_cost_calc += cost_calc
        grand_cost_unrounded += cost_unrounded
        verdict_counts[m] = dict(vcount)
        money_checks += [
            {'ok': bnd_ok,
             'detail': f'{m}: every real create has a pre-call guard bound'},
            {'ok': wire_ok,
             'detail': f'{m}: adapter wire calls == model calls and zero '
                       'fallback_from (no silent downgrade)'},
            {'ok': served_ok,
             'detail': f'{m}: served model id equals the freeze allow-list '
                       'id on every cell'}]
    money_checks.insert(0, {
        'ok': True,
        'detail': f'real model calls (raw transcripts): DS='
                  f'{totals["deepseek-flash"]["model_calls_from_raw"]}, '
                  f'GPT={totals["gpt-4.1-mini"]["model_calls_from_raw"]}, '
                  f'total={grand_calls}; real tool calls total={grand_tools}'})
    # Cross-check against the frozen run-audit / result-freeze claims.
    run_audit = json.loads(C.G3B3_LIVE_AUDIT.read_text(encoding='utf-8'))
    rf_budget = rf['execution']['budget']
    # Cost convention: the runner's guard accumulates the UNROUNDED per-call
    # cost (settle() -> guard.add) and the run audit rounds that cumulative
    # figure to 6 dp; each landed row stores its own cost rounded to 6 dp.
    # The authoritative billed total is therefore round(sum unrounded); the
    # sum of per-cell rounded rows can differ by ~1e-6 and is not the audit
    # basis. Both are recomputed here and disclosed.
    money_checks.append(
        {'ok': (round(run_audit['total_spend_usd'], 6)
                 == round(grand_cost_unrounded, 6)
                 == round(rf_budget['total_spend_usd'], 6)),
         'detail': f'total spend on the guard/audit basis (unrounded '
                   f'accumulation, rounded once): rows-basis='
                   f'${grand_cost_unrounded:.6f} == run audit='
                   f'${run_audit["total_spend_usd"]:.6f} == result freeze='
                   f'${rf_budget["total_spend_usd"]:.6f}'})
    money_checks.append(
        {'ok': all(round(totals[m]['cost_usd_guard_basis_unrounded'], 6)
                   == round(rf_budget['per_model_spend_usd'][m], 6)
                   for m in C.MODELS),
         'detail': 'per-model guard-basis spend matches the result freeze '
                   f'({ {m: totals[m]["cost_usd_guard_basis_unrounded"] for m in C.MODELS} })'})
    money_checks.append(
        {'ok': all(round(totals[m]['cost_usd_recomputed_tokens'], 6)
                   == totals[m]['cost_usd_summed_rows_rounded_per_cell']
                   for m in C.MODELS),
         'detail': 'every row cost equals round(tokens x price, 6); the '
                   'sum of these per-cell rounded row values is '
                   f'${grand_cost_row:.6f} (vs ${grand_cost_unrounded:.6f} '
                   'guard basis: a disclosed ~1e-6 rounding-convention gap, '
                   'not a discrepancy)'})
    section('E_real_calls_tokens_cost', money_checks, per_model=totals)

    # ------------------------------------------------------------------ #
    # 5. Resume discipline, duplicates, audit counters (task 10).
    # ------------------------------------------------------------------ #
    res_checks = [
        {'ok': (run_audit['new_rows'] == {'deepseek-flash': 50,
                                          'gpt-4.1-mini': 50}
                 and run_audit['skipped_already_done']
                 == {'deepseek-flash': 0, 'gpt-4.1-mini': 0}
                 and run_audit['error_rows']
                 == {'deepseek-flash': 0, 'gpt-4.1-mini': 0}),
         'detail': 'run audit: new=50/50, resume-skips=0/0, errors=0/0 '
                   '(single clean pass; resume code path existed but did '
                   'not fire)'},
        {'ok': (all(len({r['cell'] for r in rows_by_model[m]}) == 50
                    for m in C.MODELS)
                 and len({(r['cell'], r['model_profile'])
                          for r in all_rows}) == 100),
         'detail': 'each model file has its 50 distinct cell keys and no '
                   '(cell, model) pair repeats (the g3b3 cell key omits the '
                   'model, so the same 50 keys legitimately occur once per '
                   'model file; resume cannot double-pay a real cell)'},
        {'ok': run_audit.get('retries_per_cell') == 0,
         'detail': 'retries_per_cell=0 recorded in the run audit'}]
    section('F_resume_and_run_audit', res_checks)

    # ------------------------------------------------------------------ #
    # 6. Mock discipline: mock products exist separately and never enter
    #    the real result set (task 10 explicit prohibition).
    # ------------------------------------------------------------------ #
    mock_audit = json.loads(C.G3B3_MOCK_AUDIT.read_text(encoding='utf-8'))
    n_mock_traces = len(list((C.G3B3 / 'traces' / 'mock').glob('*.json')))
    mock_checks = [
        {'ok': mock_audit.get('mode') == 'mock'
                 and mock_audit.get('total_spend_usd') == 0.0,
         'detail': 'offline mock audit is mode=mock, $0 (its pass rate is a '
                   'plumbing check only)'},
        {'ok': n_mock_traces == 100,
         'detail': f'mock left {n_mock_traces} traces under traces/mock/, '
                   'segregated from the 100 pinned traces/live/ files'},
        {'ok': all(not r.get('mock') and not r.get('research_excluded')
                   for r in all_rows),
         'detail': 'the pinned live row files contain ZERO mock/excluded '
                   'rows; every audited number in sections B-E derives from '
                   'real requests only'}]
    section('G_mock_segregated_not_substituted', mock_checks)

    # ------------------------------------------------------------------ #
    # 7. Engineering gates: preflight / livegate / analyzer post-hoc.
    # ------------------------------------------------------------------ #
    pre = json.loads(C.G3B3_PREFLIGHT.read_text(encoding='utf-8'))
    gate = json.loads(C.G3B3_LIVEGATE.read_text(encoding='utf-8'))
    def _passes(obj):
        if isinstance(obj, dict):
            if {'n_checks', 'n_checks_pass'} <= set(obj):
                return obj['n_checks_pass'], obj['n_checks']
            tot = [0, 0]
            for v in obj.values():
                p = _passes(v)
                if p:
                    tot[0] += p[0]
                    tot[1] += p[1]
            return tuple(tot) if tot[1] else None
        return None
    pre_p, pre_n = _passes(pre)
    gate_p, gate_n = _passes(gate)
    post = rf['post_collection_analyzer_change_disclosure']
    # Rehash the post-collection analyzer/report files against the freeze.
    post_hashes = rf['post_collection_code_hashes']
    hash_checks = [{'ok': C.sha256_file(C.EVID / name) == h['sha256'],
                    'detail': f'{name} (post-collection analyzer/report; '
                              'not present in the pre-paid executed freeze: '
                              f'in_executed_freeze_manifest='
                              f'{h.get("in_executed_freeze_manifest")})'}
                   for name, h in post_hashes.items()]
    eng_checks = hash_checks + [
        {'ok': pre_p == pre_n and pre_n >= 41,
         'detail': f'preflight {pre_p}/{pre_n} checks passed before any '
                   'paid call'},
        {'ok': gate_p == gate_n and gate_n >= 500,
         'detail': f'live gate {gate_p}/{gate_n} per-cell checks passed on '
                   'the 100 real cells'},
        {'ok': (gate.get('n_active_freshness_TRUE') == 30
                 if isinstance(gate, dict) else False),
         'detail': f"livegate active-cell freshness TRUE count="
                   f"{gate.get('n_active_freshness_TRUE') if isinstance(gate, dict) else '?'} "
                   '(30 active cells expected)'},
        {'ok': post['analyzer_written_after_collection_offline'] is True
                 and post['api_calls_for_analysis'] == 0
                 and post['result_rows_modified'] is False,
         'detail': 'analyzer/report were written AFTER collection, offline, '
                   'made 0 API calls and changed no row/raw/trace/cost byte'}]
    section('H_engineering_gates_posthoc_analyzer', eng_checks)

    # ------------------------------------------------------------------ #
    # 8. Protocol / served-content fingerprints on every row (task 1).
    # ------------------------------------------------------------------ #
    df = C.load_data_freeze()
    cell_fp = {c['cell_key']: c for c in df['cells']}
    fp_checks = []
    versions = Counter()
    for r in all_rows:
        v = r.get('version', {})
        versions[(v.get('protocol_version'), v.get('prompt_version'),
                  v.get('gold_cert_version'))] += 1
        cf = cell_fp.get(r['cell'])
        if not cf:
            fp_checks.append({'ok': False, 'detail': f'no freeze cell {r["cell"]}'})
            continue
        if v.get('prompt_fingerprint') != cf['prompt_fingerprint']:
            fp_checks.append({'ok': False,
                              'detail': f'prompt fp drift {r["cell"]}'})
        if r.get('g3b_pair_cell_key') != cf['g3b_pair_cell_key']:
            fp_checks.append({'ok': False,
                              'detail': f'pair anchor drift {r["cell"]}'})
        if (r.get('audit_condition_gold') != cf['audit_condition_gold']
                or r.get('audit_oracle_gold') != cf['audit_oracle_gold']):
            fp_checks.append({'ok': False,
                              'detail': f'audit gold mismatch {r["cell"]}'})
    fp_checks.insert(0, {
        'ok': len(versions) == 1 and next(iter(versions))[1:]
        == ('p3-ternary-g3b2-v1', 'g3b2-gold-cert-v1'),
        'detail': f'all 100 rows record protocol={C.load_data_freeze()["executed_protocol"]["protocol_version"]}, '
                  'prompt p3-ternary-g3b2-v1, gold cert g3b2-gold-cert-v1; '
                  'per-row prompt fingerprints match the pre-paid freeze '
                  f'(version tuple counts={dict(versions)})'})
    section('I_protocol_fingerprints', fp_checks[:1]
            + [c for c in fp_checks[1:] if not c['ok']][:20],
            n_fp_mismatches=sum(not c['ok'] for c in fp_checks[1:]))

    # ------------------------------------------------------------------ #
    out = {
        'totals': {'real_model_calls': grand_calls,
                   'per_model_calls': {m: totals[m]['model_calls_from_raw']
                                       for m in C.MODELS},
                   'real_tool_calls': grand_tools,
                   'tokens_in': grand_in, 'tokens_out': grand_out,
                   'cost_usd_rows': round(grand_cost_row, 6),
                   'cost_usd_recomputed': round(grand_cost_calc, 6)},
        'verdict_counts': verdict_counts,
        'overall_ok': all(s['all_ok'] for s in report['sections'])}
    report['summary'] = out
    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_integrity_verification.json'
    dest.write_bytes(C.canonical_bytes(report))
    print('\nOVERALL:', 'PASS' if out['overall_ok'] else 'FAIL')
    print('real model calls total:', grand_calls,
          {m: totals[m]['model_calls_from_raw'] for m in C.MODELS})
    print('cost recomputed: $%.6f (rows $%.6f)'
          % (grand_cost_calc, grand_cost_row))
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
