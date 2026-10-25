"""Phase-2 runner: evidence-sufficiency x evidence-integrity x model matrix.

Conditions (explicit tier in the name):
  T0    issue + patch
  T1    + unverified author claim
  T2D   + STATIC diagnostic artifact (acceptance outcomes withheld)
  T3D   + agentic verification tools at the diagnostic tier
  T2A   + STATIC full acceptance artifact (Phase-1 leakage baseline)
  T3A   + tools at the acceptance tier

Each fixture row in phase2_fixtures.jsonl is one hidden integrity scenario
(valid / wrong_patch / stale / incomplete / contradictory). The scenario label and
expected integrity verdicts are kept OUT of every prompt and only rejoined at scoring
time. T0/T1 are scenario-independent: emitted once per sample id.

Cost control for T3: --max-tool-turns and --token-budget (prompt+completion tokens);
a truncated run is recorded with budget_hit=true rather than silently dropped.

Model endpoints are configurable via a profiles JSON:
  {"profile-name": {"base_url": "...", "key_env": "ENV_VAR",
                    "price_in_per_1m": 0.27, "price_out_per_1m": 1.10}}

Usage:
  python -m evidence.phase2_run --fixtures evidence_store/phase2_fixtures.jsonl \
      --raw evidence_store/raw_rows.jsonl --model-profile deepseek \
      --conditions T0,T1,T2D,T3D --output evidence_store/phase2_results.jsonl
"""
from __future__ import annotations

import argparse, json, os, re, time, urllib.request
from pathlib import Path

from pilot import read_jsonl, write_jsonl, parse_decision, DECISION_SCHEMA
from evidence.prompts import build_messages, TOOLS
from evidence.runner import EvidenceClient
from evidence.schemas import make_artifact_id

TIER_COND = {'T2D': ('T2', 'D'), 'T3D': ('T3', 'D'),
             'T2A': ('T2', 'A'), 'T3A': ('T3', 'A')}
DEFAULT_PROFILES = {
    # Current endpoint (api.deepseek.com) no longer serves deepseek-chat; the
    # live models are deepseek-flash (V4.1-Flash) and deepseek-v4-pro. Prices
    # below are deepseek-flash PEAK rates (cache miss), used conservatively;
    # off-peak is half. Override the model id with --model deepseek-flash.
    'deepseek': {'base_url': 'https://api.deepseek.com/v1',
                 'key_env': 'DEEPSEEK_API_KEY',
                 'price_in_per_1m': 0.30, 'price_out_per_1m': 1.20},
}


class P2Client(EvidenceClient):
    def open_session(self, instance_id, base_commit, patch_sha256, cell,
                     served_artifact_id=None, evidence_tier='D', claim=None):
        return self._req('POST', '/sessions',
                         {'instance_id': instance_id, 'base_commit': base_commit,
                          'patch_sha256': patch_sha256, 'cell': cell,
                          'served_artifact_id': served_artifact_id,
                          'evidence_tier': evidence_tier,
                          # Bind the author statement (only present in cells that
                          # show one); consistency evaluates this registered claim.
                          'claim': claim})

    def _req_tool(self, method, path, obj=None, raw=False):
        """Tool calls must surface the service's JSON error body (e.g. the
        designed HTTP 409 'consistency unavailable for this cell') to the model
        as an ordinary tool result, instead of crashing the cell via urllib's
        HTTPError. Session opening still uses the strict _req."""
        import urllib.error
        try:
            return self._req(method, path, obj=obj, raw=raw)
        except urllib.error.HTTPError as he:
            body = he.read().decode('utf-8', errors='replace')
            if raw:
                return body
            try:
                return json.loads(body)
            except Exception:
                return {'error': body[:500], 'http_status': he.code}

    def tool(self, sid, name, args):
        if name == 'get_test_artifact':
            return self._req_tool('GET', f'/sessions/{sid}/artifact')
        if name == 'verify_artifact_linkage':
            return self._req_tool('GET', f'/sessions/{sid}/verify')
        if name == 'check_evidence_freshness':
            return self._req_tool('GET', f'/sessions/{sid}/freshness')
        if name == 'check_test_coverage':
            return self._req_tool('GET', f'/sessions/{sid}/coverage')
        if name == 'check_claim_consistency':
            return self._req_tool('POST', f'/sessions/{sid}/consistency',
                                  {'claim': args.get('claim', '')})
        if name == 'get_run_log':
            return self._req_tool('GET',
                             f"/sessions/{sid}/log/{args.get('name', 'symptom')}",
                             raw=True)
        return {'error': 'unknown tool'}


def load_profiles(path):
    prof = dict(DEFAULT_PROFILES)
    if path and Path(path).exists():
        prof.update(json.loads(Path(path).read_text(encoding='utf-8')))
    return prof


def make_llm(profile):
    from openai import OpenAI
    key = os.environ.get(profile['key_env']) or os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit(f"set {profile['key_env']} for this model profile")
    return OpenAI(api_key=key, base_url=profile.get('base_url'))


def _tally(tot, msg):
    if msg.usage:
        tot['in'] += getattr(msg.usage, 'prompt_tokens', 0) or 0
        tot['out'] += getattr(msg.usage, 'completion_tokens', 0) or 0


def run_p2_cell(llm, model, item, ev: P2Client | None, profile, *,
                max_tool_turns=6, token_budget=0, emergency_tokens=120_000,
                variant=''):
    cond_name = item['condition']            # T0/T1/T2D/T3D/T2A/T3A
    cond, tier = TIER_COND.get(cond_name, (cond_name, item.get('evidence_tier', 'A')))
    prompt_item = dict(item)
    prompt_item['condition'] = cond
    prompt_item['evidence_tier'] = tier
    messages = build_messages(prompt_item, artifact=item.get('artifact_record'))
    trace, usage, t0 = [], {'in': 0, 'out': 0}, time.time()

    def over_cap():
        """Hard emergency cap always applies; the optional (smaller) token_budget
        marks an explicit budget-condition truncation. Either stops the loop."""
        return (emergency_tokens and usage['in'] + usage['out'] >= emergency_tokens)

    def chat(tools=None):
        kw = {}
        # deepseek-flash defaults to a billed thinking mode; the approved anchor
        # (deepseek-chat) and the ~$0.14 budget were NON-thinking. Disable
        # thinking so the model/budget match the registered design and Phase 1.
        kw['extra_body'] = {'thinking': {'type': 'disabled'}}
        if tools:
            kw['tools'] = tools
        else:
            kw['response_format'] = {'type': 'json_schema',
                                     'json_schema': DECISION_SCHEMA}
        try:
            return llm.chat.completions.create(model=model, messages=messages,
                                               temperature=0, **kw)
        except Exception as re_:
            if 'response_format' in kw and re.search(r'response_format|400', str(re_)):
                kw.pop('response_format')
                return llm.chat.completions.create(model=model, messages=messages,
                                                   temperature=0, **kw)
            raise

    sid = None
    if cond == 'T3':
        s = ev.open_session(item['instance_id'], item['base_commit'],
                            item['patch_sha256'], cell=item['cell_key'],
                            served_artifact_id=item.get('served_artifact_id'),
                            evidence_tier=tier,
                            claim=item.get('claim') if item.get('with_claim') else None)
        sid = s['session_id']

    msg = chat(TOOLS if cond == 'T3' else None)
    _tally(usage, msg)
    final = msg.choices[0].message.content or ''
    turns, budget_hit, emergency_hit = 0, False, False

    while (cond == 'T3'
           and msg.choices[0].finish_reason == 'tool_calls'
           and turns < max_tool_turns):
        if token_budget and usage['in'] + usage['out'] >= token_budget:
            budget_hit = True
            break
        if over_cap():
            emergency_hit = True
            break
        tcb = msg.choices[0].message
        messages.append(tcb.model_dump(exclude_none=True))
        for tc in (tcb.tool_calls or []):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            # A single failing tool call must not abort the cell: feed the error
            # back so the model can recover, and record it in the trace.
            try:
                result = ev.tool(sid, name, args)
            except Exception as te:
                result = {'error': f'tool {name} failed: {type(te).__name__}: {te}'}
                trace.append({'turn': turns, 'tool': name, 'args': args,
                              'error': str(te)[:300]})
            else:
                trace.append({'turn': turns, 'tool': name, 'args': args,
                              'result_preview': (result if isinstance(result, str)
                                                 else json.dumps(result))[:800]})
            messages.append({'role': 'tool', 'tool_call_id': tc.id,
                             'content': (result if isinstance(result, str)
                                         else json.dumps(result, ensure_ascii=False))[:8000]})
        turns += 1
        if over_cap():
            emergency_hit = True
            break
        msg = chat(TOOLS)
        _tally(usage, msg)
        final = msg.choices[0].message.content or ''

    # Turn/budget cap reached while the model still wants tools: force ONE final
    # answer without tools so the cell is never left without a decision.
    if cond == 'T3' and (msg.choices[0].finish_reason == 'tool_calls'
                         or not (final or '').strip()):
        messages.append({'role': 'user', 'content': 'Stop calling tools now and '
                         'return your final single JSON decision.'})
        msg = chat(None)
        _tally(usage, msg)
        final = msg.choices[0].message.content or ''

    parsed = parse_decision(final or '')
    try:
        mismatch_flag = bool(json.loads(final).get('evidence_mismatch'))
    except Exception:
        mismatch_flag = None

    def saw(tool, key, bad):
        return any(t['tool'] == tool
                   and f'"{key}": {bad}' in (t.get('result_preview') or '')
                   for t in trace)

    reveals = [t for t in trace if t['tool'] == 'get_run_log'
               and (t.get('args') or {}).get('name') in ('f2p', 'p2p', 'p2p_baseline')]
    cost = (usage['in'] * profile.get('price_in_per_1m', 0)
            + usage['out'] * profile.get('price_out_per_1m', 0)) / 1e6
    return {
        'cell': item['cell_key'], 'id': item['id'],
        'instance_id': item['instance_id'], 'condition': cond_name,
        'evidence_tier': tier if cond_name in TIER_COND else None,
        'scenario': item.get('scenario'),
        'model': model, 'model_profile': profile.get('name'),
        'budget_variant': variant, 'max_tool_turns': max_tool_turns,
        'token_budget': token_budget or None, 'budget_hit': budget_hit,
        'emergency_tokens': emergency_tokens or None,
        'emergency_hit': emergency_hit,
        'label_class': item.get('label_class'),
        'merge_acceptable': item.get('merge_acceptable'),
        'expected_integrity': item.get('expected'),
        'served_artifact_id': item.get('served_artifact_id'),
        'answer': final, 'parsed': parsed,
        'evidence_mismatch_flag': mismatch_flag,
        'tool_trace': trace, 'tool_calls': len(trace), 'evidence_session': sid,
        'called_linkage': any(t['tool'] == 'verify_artifact_linkage' for t in trace),
        'saw_linked_false': saw('verify_artifact_linkage', 'linked', 'false'),
        'called_freshness': any(t['tool'] == 'check_evidence_freshness' for t in trace),
        'saw_fresh_false': saw('check_evidence_freshness', 'fresh', 'false'),
        'called_coverage': any(t['tool'] == 'check_test_coverage' for t in trace),
        'saw_coverage_incomplete': saw('check_test_coverage', 'complete', 'false'),
        'called_consistency': any(t['tool'] == 'check_claim_consistency' for t in trace),
        'saw_contradicted': any(t['tool'] == 'check_claim_consistency'
                                and '"verdict": "contradicted"'
                                in (t.get('result_preview') or '')
                                for t in trace),
        'acceptance_log_reveals': len(reveals) if tier == 'D' else 0,
        'tokens_in': usage['in'], 'tokens_out': usage['out'],
        'cost_usd': round(cost, 6), 'wall_s': round(time.time() - t0, 2),
    }


def build_cells(fixtures, raw_by_id, store, conditions, truth_rows=()):
    """Tiered T2/T3 cells exist per fixture (scenario) row; T0/T1 baselines
    cover ALL labelled samples (the 19 truth rows): fixture rows first, then
    every remaining truth id. The served static record is the fixture record
    (rendered through the tiered evidence block); scenario label is stripped
    like the server does."""
    seen, cells = set(), []

    def add_baselines(fx, raw):
        if fx['id'] in seen:
            return
        for cond in ('T0', 'T1'):
            if cond in conditions:
                cells.append(_item(fx, raw, store, cond, None, None))
        seen.add(fx['id'])

    for fx in fixtures:
        raw = raw_by_id[fx['id']]
        add_baselines(fx, raw)
        for cond in conditions:
            if cond in TIER_COND:
                _, tier = TIER_COND[cond]
                cells.append(_item(fx, raw, store, cond, tier,
                                   fx['served_artifact_id']))

    # Baseline-only samples: the remaining labelled patches with no Phase-2
    # fixture. Labels come from truth.jsonl; T0/T1 need no served artifact.
    for tr in truth_rows:
        if tr['id'] in seen or tr['id'] not in raw_by_id:
            continue
        raw = raw_by_id[tr['id']]
        fx = {'id': tr['id'], 'instance_id': tr['instance_id'],
              'repo': tr.get('repo', raw.get('repo')),
              'base_commit': tr['base_commit'], 'patch_sha256': tr['patch_sha256'],
              'label_class': tr['label_class'],
              'merge_acceptable': tr['merge_acceptable']}
        add_baselines(fx, raw)
    return cells


def _item(fx, raw, store, cond_name, tier, served_aid):
    item = {
        'id': fx['id'], 'instance_id': fx['instance_id'],
        'repo': fx.get('repo', raw.get('repo')),
        'base_commit': fx['base_commit'], 'patch_sha256': fx['patch_sha256'],
        'issue': raw['problem_statement'], 'patch': raw['model_patch'],
        'condition': cond_name,
        # T0/T1 are scenario-independent baselines: do not tag them with the first
        # fixture's scenario (would double-count / bias scenario grouping).
        'scenario': fx.get('scenario') if cond_name in TIER_COND else None,
        'label_class': fx.get('label_class'),
        'merge_acceptable': fx.get('merge_acceptable'),
        'expected': fx.get('expected'),
        'claim': fx.get('claim'),
        'with_claim': fx.get('scenario') == 'contradictory',
        'symptom': fx.get('symptom'),
    }
    if served_aid:
        got = store.get(served_aid)
        if got is None:
            raise SystemExit(f'missing fixture artifact {served_aid}')
        # SAME sanitisation chokepoint as the HTTP artifact endpoint: neutral
        # labels at both tiers; at D substitute attestation-declared counts/files
        # and project away acceptance outcomes. The static T2 block and the T3
        # tool payload therefore cannot differ in what they disclose.
        from evidence.views import display_for_tier
        item['served_artifact_id'] = served_aid
        item['artifact_record'] = display_for_tier(
            store, got[0], fx['instance_id'], fx['patch_sha256'], tier)
        item['evidence_tier'] = tier
    item['cell_key'] = (f"{item['scenario'] or 'base'}:{item['id']}:{cond_name}"
                        if cond_name in TIER_COND
                        else f"base:{item['id']}:{cond_name}")
    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixtures', default='evidence_store/phase2_fixtures.jsonl')
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--truth', default='evidence_store/truth.jsonl',
                    help='labelled samples; T0/T1 baselines cover all of them')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--profiles', default='evidence_store/model_profiles.json')
    ap.add_argument('--model-profile', default='deepseek')
    ap.add_argument('--model', default='', help='override model id')
    ap.add_argument('--conditions', default='T0,T1,T2D,T3D')
    ap.add_argument('--output', default='evidence_store/phase2_results.jsonl')
    ap.add_argument('--api', default='http://127.0.0.1:8321')
    ap.add_argument('--max-tool-turns', type=int, default=6)
    ap.add_argument('--token-budget', type=int, default=0)
    ap.add_argument('--emergency-tokens', type=int, default=120_000,
                    help='hard per-cell prompt+completion ceiling; stops runaway '
                         'tool loops regardless of --token-budget')
    ap.add_argument('--max-budget-usd', type=float, default=1.0,
                    help='batch-level fail-fast: stop once cumulative recorded '
                         'spend reaches this amount')
    ap.add_argument('--variant', default='')
    ap.add_argument('--dry-run', action='store_true',
                    help='build cells and print budget only; no API calls')
    a = ap.parse_args()

    profiles = load_profiles(a.profiles)
    if a.model_profile not in profiles:
        raise SystemExit(f'unknown profile {a.model_profile}; have {sorted(profiles)}')
    profile = dict(profiles[a.model_profile]); profile['name'] = a.model_profile
    model = a.model or a.model_profile

    from evidence.store import ArtifactStore
    store = ArtifactStore(a.store)
    fixtures = list(read_jsonl(a.fixtures))
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    conds = tuple(x.strip() for x in a.conditions.split(',') if x.strip())
    truth_rows = list(read_jsonl(a.truth)) if a.truth else []
    cells = build_cells(fixtures, raw_by_id, store, conds, truth_rows)

    n_tool = sum(1 for c in cells if c['condition'].startswith('T3'))
    print(f'cells={len(cells)} (T3={n_tool}) model={model} profile={a.model_profile} '
          f'max_turns={a.max_tool_turns} token_budget={a.token_budget or "off"} '
          f'emergency_tokens={a.emergency_tokens} max_budget_usd={a.max_budget_usd}')
    if a.dry_run:
        for c in cells:
            print(' ', c['cell_key'])
        return

    llm = make_llm(profile)
    ev = P2Client(a.api) if any(c['condition'].startswith('T3') for c in cells) else None
    outp = Path(a.output)
    prior = list(read_jsonl(a.output)) if outp.exists() else []
    # Resume only on cells that previously COMPLETED without an error; failed cells
    # are retried rather than silently skipped.
    done = {r['cell'] for r in prior if not r.get('error')}
    spent = sum(float(r.get('cost_usd') or 0) for r in prior)
    n_err = 0
    with outp.open('a', encoding='utf-8') as f:
        for item in cells:
            if item['cell_key'] in done:
                continue
            if spent >= a.max_budget_usd:
                print(f'BATCH BUDGET STOP: cumulative spend ${spent:.4f} >= '
                      f'${a.max_budget_usd:.4f}; remaining cells not run')
                break
            try:
                rec = run_p2_cell(llm, model, item, ev, profile,
                                  max_tool_turns=a.max_tool_turns,
                                  token_budget=a.token_budget,
                                  emergency_tokens=a.emergency_tokens,
                                  variant=a.variant)
            except Exception as e:
                # Fail one CELL, not the batch: persist the raw error so the run is
                # resumable and the anomaly is reported, never silently dropped.
                n_err += 1
                rec = {'cell': item['cell_key'], 'id': item['id'],
                       'instance_id': item['instance_id'],
                       'condition': item['condition'],
                       'evidence_tier': item.get('evidence_tier'),
                       'scenario': item.get('scenario'),
                       'model': model, 'model_profile': profile.get('name'),
                       'label_class': item.get('label_class'),
                       'merge_acceptable': item.get('merge_acceptable'),
                       'expected_integrity': item.get('expected'),
                       'served_artifact_id': item.get('served_artifact_id'),
                       'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                       'tool_calls': 0, 'tool_trace': [],
                       'error': f'{type(e).__name__}: {e}'}
                print('ERROR', rec['cell'], rec['error'][:200])
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            spent += float(rec.get('cost_usd') or 0)
            if 'error' not in rec:
                print(rec['cell'], rec['parsed'],
                      f"tools={rec['tool_calls']} in={rec['tokens_in']} "
                      f"out={rec['tokens_out']} ${rec['cost_usd']:.4f} "
                      f"cum=${spent:.4f}")
    print(f'done: failed_cells={n_err} cumulative_spend=${spent:.4f}')


if __name__ == '__main__':
    main()
