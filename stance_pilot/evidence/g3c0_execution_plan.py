"""Gate G3-C.0 tasks 9-10 (ESTIMATES and STANDARDS only; nothing executed,$0).

  task 9: three-phase execution plan (quality pilot -> external batch 1 ->
          expansion) with per-phase API REQUEST counts, token estimates,
          worst-case budget and stopping rules. Costs are derived from the
          FROZEN real G3-B.3 rows (no mock substitution).
  task 10: unified engineering checks for model-version drift, prompt length,
          tool capability, randomness, missing reason, truncation and budget
          protection.

    uv run --python 3.13 -m evidence.g3c0_execution_plan
"""
from __future__ import annotations

import statistics
from collections import defaultdict

from evidence import g3c0_common as C


def observed_cell_profile():
    rows = (C.read_jsonl(C.G3B3_LIVE_GPT)
            + C.read_jsonl(C.G3B3_LIVE_DEEPSEEK))
    rows = [r for r in rows if not r.get('mock')]
    by_model = defaultdict(list)
    for r in rows:
        by_model[r['model_profile']].append(r)
    prof = {}
    for m, rs in by_model.items():
        def nums(k):
            return [float(r.get(k) or 0) for r in rs]
        req = [int(r.get('model_calls') or 0) for r in rs]
        prof[m] = {
            'n_live_cells': len(rs),
            'mean_model_requests_per_cell': round(statistics.mean(req), 3),
            'max_model_requests_per_cell': max(req),
            'mean_tokens_in': round(statistics.mean(nums('tokens_in')), 1),
            'mean_tokens_out': round(statistics.mean(nums('tokens_out')), 1),
            'p90_tokens_in': round(sorted(nums('tokens_in'))
                                   [int(0.9 * (len(rs) - 1))], 1),
            'max_tokens_in': max(nums('tokens_in')),
            'mean_cost_usd': round(statistics.mean(nums('cost_usd')), 6),
            'max_cost_usd': round(max(nums('cost_usd')), 6),
            'mean_wall_s': round(statistics.mean(nums('wall_s')), 2),
        }
    prof['ALL'] = {
        'n_live_cells': len(rows),
        'mean_cost_usd': round(statistics.mean(
            [float(r.get('cost_usd') or 0) for r in rows]), 6),
        'max_cost_usd': round(max(
            [float(r.get('cost_usd') or 0) for r in rows]), 6)}
    return prof


def main():
    prof = observed_cell_profile()
    mean_cell = prof['ALL']['mean_cost_usd']
    max_cell = prof['ALL']['max_cost_usd']
    p90_in = max(v['p90_tokens_in'] for v in prof.values()
                 if 'p90_tokens_in' in v)

    # ---- Planning geometry (NOT a frozen issue list; estimates only) ------
    # Primary cohort: 40 independent issues (20 new REJECT + ~20 ACCEPT/need
    # controls). Arms: 5 existing conditions + 2 identification arms
    # (stubbed-same-payload active tier-D; active tier-D reminder) = 7 cells.
    n_issues_full = 40
    n_arms = 7
    n_models = 2
    cells_full = n_issues_full * n_arms * n_models
    # Pilot: 8 issues (stratified: >=4 REJECT), all 7 arms, both models.
    n_issues_pilot = 8
    cells_pilot = n_issues_pilot * n_arms * n_models
    # Batch 1 external validation: 20 issues (the >=20 REJECT core) x 5
    # primary conditions x 2 models (identification arms already validated
    # in pilot; reminder arm carried here as one extra cell -> 6).
    n_issues_b1 = 20
    n_arms_b1 = 6
    cells_b1 = n_issues_b1 * n_arms_b1 * n_models
    # Expansion: remaining controls/extra accept issues to reach 40-issue
    # full design, 5 conditions x 2 models.
    n_issues_exp = n_issues_full - n_issues_b1
    cells_exp = n_issues_exp * 5 * n_models

    def phase(name, issues, arms, cells, note):
        mean_budget = round(cells * mean_cell, 2)
        # Worst case: every cell at the observed MAX cell cost (defensive).
        worst_budget = round(cells * max_cell, 2)
        # Token planning: mean in/out observed, with a p90-based guard.
        mean_tin = round(cells * statistics.mean(
            [v['mean_tokens_in'] for v in prof.values()
             if 'mean_tokens_in' in v]), 0)
        return {'phase': name, 'issues': issues, 'arms_per_issue': arms,
                'models': n_models, 'estimated_cells': cells,
                'estimated_model_requests_mean':
                    round(cells * statistics.mean(
                        [v['mean_model_requests_per_cell'] for v in prof.values()
                         if 'mean_model_requests_per_cell' in v]), 0),
                'estimated_total_input_tokens_at_observed_mean': mean_tin,
                'expected_cost_at_observed_mean_usd': mean_budget,
                'worst_case_cost_if_every_cell_hits_observed_max_usd':
                    worst_budget,
                'hard_pre_call_cap_usd': round(worst_budget * 1.15, 2),
                'note': note}

    phases = [
        phase('P0 quality pilot (mock + zero-API live gate + small real)',
              n_issues_pilot, n_arms, cells_pilot,
              'validates projection v2, the non-interference gate, packets, '
              'drift checks and budget guard on a tiny real sample; gates '
              'release of batch 1'),
        phase('B1 first external validation (>=20 new independent REJECT '
              'issues)', n_issues_b1, n_arms_b1, cells_b1,
              'the P2-defining cohort; P1 measured on the tier-D arms; '
              'orthogonal static/active cells collected for P1a'),
        phase('B2 expansion to balanced 40-issue design', n_issues_exp, 5,
              cells_exp,
              'ACCEPT/need controls and additional repos; only after B1 '
              'quality review and a written (separately approved) release'),
    ]
    totals_cells = cells_pilot + cells_b1 + cells_exp
    plan = {
        'observed_real_cell_profile_from_g3b3': prof,
        'planning_assumptions': {
            'mean_cell_cost_source': 'frozen G3-B.3 REAL live rows (100 '
                                    'cells), not mock',
            'observed_mean_cell_usd': mean_cell,
            'observed_max_cell_usd': max_cell,
            'p90_input_tokens_any_model': p90_in,
            'issues_full_design': n_issues_full,
            'new_reject_floor': 20,
            'arms': ['T2D-T', 'T3D-Strict(v2)', 'T3D-Escalate', 'T2A-T',
                     'T3A-T', 'active-tier-D-stubbed-same-content (turns '
                     'control)', 'active-tier-D-positive-signals+reminder'],
            'two_models': list(prof.keys()),
            'price_drift_warning': 'provider list prices and model versions '
                    'can change; recompute mean/max from the pilot before B1 '
                    'and re-approve caps; estimates here are planning figures,'
                    ' not commitments',
        },
        'phases': phases,
        'totals_estimated_cells': totals_cells,
        'totals_expected_cost_usd': round(totals_cells * mean_cell, 2),
        'totals_worst_case_observed_max_usd':
            round(totals_cells * max_cell, 2),
        'stopping_rules': [
            'HARD pre-call budget guard (the repaired CompositeGuard pattern):'
            ' float(bound) is evaluated before any network call; no call that '
            'could breach the phase cap is issued; per-model sub-caps too.',
            'stop the phase if the cumulative run-rate projects > hard cap '
            'with the next batch; require a new written approval to continue.',
            'stop and freeze on any protocol-capability drift: silent '
            'response_format downgrade, wire fallback, unexpected model id '
            'served, or tool-schema rejection.',
            'stop if the zero-API live gate / preflight / non-interference '
            'scan (tier1>0 or tier2>0) fails.',
            'abort-and-investigate trigger (harm-only interim look, at most '
            'once): e.g. a model commits unsupported ACCEPT on essentially '
            'every REJECT issue in B1; never stop to cherry-pick a favourable '
            'result.',
            'no expansion beyond the frozen issue/projection list without a '
            'new separate written approval (G3-C.2); G3-C.0 executes none of '
            'this.',
        ],
        'executed_in_gate_g3c0': False,
        'budget_spent_in_gate_g3c0_usd': 0,
    }

    engineering = {
        'model_version_drift': [
            'record expected_model_id and model_served for EVERY cell; '
            'mismatch flags the row and fails the batch',
            'pin provider model snapshot/date where supported; log the raw '
            'version field; a version change mid-phase forces a pause and a '
            'fresh calibration cell',
            'no silent alias resolution (e.g. mini -> a newer revision)'],
        'prompt_length': [
            'capture tokens_in per cell; fail if a prompt exceeds a pre-set '
            f'fraction of the context (guard basis p90 observed ~{p90_in} '
            'tokens); log truncation indicators',
            'rendered prompts are persisted raw-first and byte-hashed so '
            'prompt changes across phases are detectable'],
        'tool_capability': [
            'validate the tool schema is accepted before the batch; count '
            'HTTP 4xx/5xx and tool-schema errors; any new tool error type '
            'halts the phase',
            'assert 403 (never 200) for f2p/p2p/p2p_baseline under strict and'
            ' that the body is never read',
            'synthetic canary cells confirm linkage/freshness/coverage still '
            'return the designed structural fields under projection v2'],
        'randomness': [
            'record temperature/seed/top_p per call; use a fixed pre-'
            'registered seed schedule; any repeat/replicate cells average '
            'WITHIN issue (never inflate n)',
            'log raw_model_calls and retries; retries must reuse the seed '
            'policy and are audited, never silently dropped'],
        'missing_reason_or_unparseable': [
            'a missing/empty reason or unparseable verdict is a PRE-DEFINED '
            'outcome: verdict=UNPARSEABLE is logged and retained (not '
            'retried away); for P1 it counts as non-commitment/NEED; for P2 '
            'it is failure-to-evaluate with a complete-case sensitivity '
            'bound',
            'no post-hoc exclusion of such rows from the frozen analysis'],
        'truncation': [
            'set and record max_tokens; detect finish_reason=length / cut-off'
            ' JSON; truncated verdicts are flagged and treated like '
            'UNPARSEABLE, with the raw tail retained'],
        'budget_protection': [
            'pre-call worst-case bound computed from token caps BEFORE the '
            'HTTP call (the regression test that would have caught the '
            'CompositeGuard None bug); guard returns a float and is unit-'
            'tested for None/NaN',
            'mock gate and zero-API local live gate must pass before any paid'
            ' batch; cumulative cost is persisted per row and re-checked on '
            'resume (no double-spend across restarts)'],
        'integrity_persistence': [
            'raw-first persistence (raw response + tool trace written before'
            ' parsing), row-level sha256, resume idempotency, post-hoc '
            'analyzer hash match — the same discipline as G3-B.3'],
    }

    out = {
        'document': 'Gate G3-C.0 tasks 9-10: three-phase execution/budget '
                    'plan (not executed) and unified engineering checks',
        'design_version': C.G3C0_DESIGN_VERSION,
        'api_calls_made': 0,
        'task9_execution_and_budget_plan': plan,
        'task10_engineering_standards': engineering,
        'gold_authority': C.GOLD_AUTHORITY,
    }
    C.OUT_BUDGET.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_BUDGET / 'g3c0_execution_budget_and_engineering.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('observed mean/max cell USD:', mean_cell, max_cell)
    for p in phases:
        print(p['phase'][:28], 'cells=', p['estimated_cells'],
              'expected$=', p['expected_cost_at_observed_mean_usd'],
              'worst$=', p['worst_case_cost_if_every_cell_hits_observed_max_usd'])
    print('total cells ~', totals_cells)
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
