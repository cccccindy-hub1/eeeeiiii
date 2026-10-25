"""Run T0-T3 review cells against an OpenAI-compatible API.

T0/T1/T2 are single-turn requests (different visible information).
T3 is an agentic loop: the model may call get_test_artifact / verify_artifact_linkage /
get_run_log; the service executes them against the session-bound patch identity.

Per cell we record: decision, reason, evidence_mismatch flag, the ordered tool trace,
whether a verify call was made and its result, token usage, and wall time. No new
ground-truth field enters any prompt.
"""
import argparse, json, os, re, time, urllib.request, urllib.error
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.prompts import build_messages, TOOLS
from evidence.schemas import make_artifact_id

CONDITIONS = ('T0', 'T1', 'T2', 'T3')

class EvidenceClient:
    def __init__(self, base_url):
        self.base = base_url.rstrip('/')

    def _req(self, method, path, obj=None, raw=False):
        data = json.dumps(obj).encode() if obj is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method,
                                   headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(r, timeout=60) as resp:
            text = resp.read().decode('utf-8', errors='replace')
            return text if raw else json.loads(text)

    def open_session(self, instance_id, base_commit, patch_sha256, cell,
                     served_artifact_id=None):
        return self._req('POST', '/sessions',
                         {'instance_id': instance_id, 'base_commit': base_commit,
                          'patch_sha256': patch_sha256, 'cell': cell,
                          'served_artifact_id': served_artifact_id})

    def tool(self, sid, name, args):
        if name == 'get_test_artifact':
            return self._req('GET', f'/sessions/{sid}/artifact')
        if name == 'verify_artifact_linkage':
            return self._req('GET', f'/sessions/{sid}/verify')
        if name == 'get_run_log':
            return self._req('GET', f"/sessions/{sid}/log/{args.get('name','f2p')}",
                             raw=True)
        return {'error': 'unknown tool'}


def make_llc():
    from openai import OpenAI
    key = os.environ.get('OPENAI_API_KEY') or os.environ.get('DEEPSEEK_API_KEY')
    base = os.environ.get('OPENAI_BASE_URL')
    if not base and os.environ.get('DEEPSEEK_API_KEY') and not os.environ.get('OPENAI_API_KEY'):
        base = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
    if not key:
        raise SystemExit('Set DEEPSEEK_API_KEY or OPENAI_API_KEY')
    return (OpenAI(api_key=key, base_url=base) if base else OpenAI(api_key=key)), key is not None


def parse_final(content):
    from pilot import parse_decision
    return parse_decision(content or '')


def run_cell(llm, model, item, ev: EvidenceClient | None, max_tool_turns=6):
    """Single review cell. item keys: id, instance_id, repo, base_commit, patch_sha256,
    issue, patch, condition, artifact_record (dict for T2/T3), served_artifact_id."""
    cond = item['condition']
    art = item.get('artifact_record') if cond in ('T2', 'T3') else None
    messages = build_messages(item, artifact=art)
    trace, usage_tot, t0 = [], {'in': 0, 'out': 0}, time.time()

    from pilot import DECISION_SCHEMA

    def chat(tools=None):
        kw = {}
        if tools:
            kw['tools'] = tools          # providers disallow response_format + tools
        else:
            kw['response_format'] = {'type': 'json_schema',
                                     'json_schema': DECISION_SCHEMA}
        try:
            return llm.chat.completions.create(
                model=model, messages=messages, temperature=0, **kw)
        except Exception as e:
            if 'response_format' in kw and re.search(r'response_format|400', str(e)):
                kw.pop('response_format')   # plain-mode fallback, same call budget
                return llm.chat.completions.create(
                    model=model, messages=messages, temperature=0, **kw)
            raise

    sid = None
    if cond == 'T3':
        assert ev is not None
        s = ev.open_session(item['instance_id'], item['base_commit'],
                            item['patch_sha256'], cell=item['id'] + ':' + cond,
                            served_artifact_id=item.get('served_artifact_id'))
        sid = s['session_id']

    msg = chat(TOOLS if cond == 'T3' else None)
    final_content = msg.choices[0].message.content or ''
    _tally(usage_tot, msg)

    turns = 0
    while cond == 'T3' and msg.choices[0].finish_reason == 'tool_calls' and turns < max_tool_turns:
        tcb = msg.choices[0].message
        messages.append(tcb.model_dump(exclude_none=True))
        for tc in (tcb.tool_calls or []):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            result = ev.tool(sid, name, args)
            trace.append({'turn': turns, 'tool': name, 'args': args,
                          'result_preview': json.dumps(result)[:600]})
            messages.append({'role': 'tool', 'tool_call_id': tc.id,
                             'content': json.dumps(result, ensure_ascii=False)[:8000]})
        turns += 1
        msg = chat(TOOLS)
        _tally(usage_tot, msg)
        final_content = msg.choices[0].message.content or ''

    # describe what the SERVIED static artifact showed (experiment metadata; the
    # reviewer in T2/T3 saw these exact numbers, no ground truth is added to prompts)
    served = item.get('artifact_record') if cond in ('T2', 'T3') else None
    ssum = (served or {}).get('summary', {})
    rec = {'cell': item['id'] + ':' + cond, 'id': item['id'],
           'instance_id': item.get('instance_id'), 'condition': cond,
           'model': model, 'resolved': item.get('resolved'),
           'merge_acceptable': item.get('merge_acceptable'),
           'issue_addressed': item.get('issue_addressed'),
           'label_class': item.get('label_class'),
           'patch_sha256': item['patch_sha256'], 'served_artifact_id': item.get('served_artifact_id'),
           'mismatch_kind': item.get('mismatch_kind'),
           'served_shows_failure': bool(ssum.get('f2p_failed_ids')
                                        or ssum.get('p2p_regressed_ids')),
           'served_f2p_passed': ssum.get('f2p_passed'), 'served_f2p_total': ssum.get('f2p_total'),
           'served_record_patch_sha256': (served or {}).get('patch_sha256'),
           'answer': final_content, 'parsed': parse_final(final_content),
           'tool_trace': trace, 'evidence_session': sid,
           'tokens_in': usage_tot['in'], 'tokens_out': usage_tot['out'],
           'wall_s': round(time.time() - t0, 2)}
    try:
        rec['evidence_mismatch_flag'] = bool(json.loads(final_content).get('evidence_mismatch'))
    except Exception:
        rec['evidence_mismatch_flag'] = None
    rec['called_verify'] = any(t['tool'] == 'verify_artifact_linkage' for t in trace)
    rec['verify_saw_mismatch'] = any(
        t['tool'] == 'verify_artifact_linkage' and '"linked": false' in t['result_preview']
        for t in trace)
    return rec

def _tally(tot, msg):
    if msg.usage:
        tot['in'] += getattr(msg.usage, 'prompt_tokens', 0) or 0
        tot['out'] += getattr(msg.usage, 'completion_tokens', 0) or 0


def build_cells(samples, conditions, store, integrity='authentic'):
    """samples rows carry instance/patch + truth + artifact_record (preloaded).
    integrity='mismatch' serves a DIFFERENT patch's artifact in T2/T3 so T3's
    linkage tool must return linked=false. Prefer same-instance/different-patch
    (same base_commit, only patch hash differs: the harder linkage case); fall
    back to a deterministic cyclic rotation across instances."""
    cells = []
    n = len(samples)
    by_instance = {}
    for s in samples:
        by_instance.setdefault(s['instance_id'], []).append(s)
    for idx, s in enumerate(samples):
        other = None
        if integrity == 'mismatch' and n > 1:
            sibs = [x for x in by_instance[s['instance_id']] if x['id'] != s['id']]
            if sibs:
                other = sibs[idx % len(sibs)]
                kind = 'same_instance_diff_patch'
            else:
                other = samples[(idx + 1) % n]
                kind = 'cross_instance'
        for cond in conditions:
            item = dict(s)
            item['condition'] = cond
            if cond in ('T2', 'T3'):
                if other is not None:
                    item['served_artifact_id'] = make_artifact_id(
                        other['instance_id'], other['patch_sha256'])
                    # serve the OTHER record statically too
                    item['artifact_record'] = other['artifact_record']
                    item['mismatch_kind'] = kind
                else:
                    item['served_artifact_id'] = make_artifact_id(
                        s['instance_id'], s['patch_sha256'])
            cells.append(item)
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--samples', default='evidence_store/pilot_samples.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--output', default='evidence_results.jsonl')
    ap.add_argument('--model', required=True)
    ap.add_argument('--conditions', default='T0,T1,T2,T3')
    ap.add_argument('--integrity', choices=('authentic', 'mismatch'), default='authentic')
    ap.add_argument('--api', default='http://127.0.0.1:8321')
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()

    from evidence.store import ArtifactStore
    store = ArtifactStore(a.store)
    samples = list(read_jsonl(a.samples))[: (a.limit or None)]
    # attach signed records
    for s in samples:
        aid = make_artifact_id(s['instance_id'], s['patch_sha256'])
        got = store.get(aid)
        if got is None:
            raise SystemExit(f'missing artifact {aid} for {s["id"]}; build it first')
        s['artifact_record'], _ = got
    conds = tuple(a.conditions.split(','))
    cells = build_cells(samples, conds, store, a.integrity)
    llm, _ = make_llc()
    ev = EvidenceClient(a.api) if 'T3' in conds else None

    done = set()
    outp = Path(a.output)
    if outp.exists():
        done = {(r['cell']) for r in read_jsonl(a.output)}
    with outp.open('a', encoding='utf-8') as f:
        for item in cells:
            if item['id'] + ':' + item['condition'] in done:
                continue
            rec = run_cell(llm, a.model, item, ev)
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            print(rec['cell'], rec['parsed'], 'verify=' + str(rec['called_verify']),
                  f"in={rec['tokens_in']} out={rec['tokens_out']}")

if __name__ == '__main__':
    main()
