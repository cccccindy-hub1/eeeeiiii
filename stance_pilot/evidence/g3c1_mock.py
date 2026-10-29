"""G3-C.1 task 7 (part C) — full offline MOCK over the G3-C.1 protocol, $0.

40 cells = 8 new pilot issues x 5 frozen conditions, one deterministic
scripted mock reviewer. The mock is NOT a subject and its decisions are
research-excluded (mock=true / research_excluded=true / api_calls=0 /
cost_usd=0.0 on every row); it exists to validate the whole G3-C.1 pipeline
against the frozen protocol:

  * the real in-process g3c1 HTTP server serves on a tempdir store copy;
  * the scripted agent runs the genuine tool loop — artifact (projection v2),
    linkage, three-state freshness, coverage, symptom log, strict 403,
    escalate 400->reason->200 banner, ungated tier A — and commits only on
    observed, applicable evidence;
  * its rule is the SAME frozen gold rule applied to OBSERVED evidence, so for
    these genuinely-built issues it must reproduce the 40 frozen condition
    certificates 1:1 (a pipeline/alignment check, not a finding).

No vendor call is made or possible; only 127.0.0.1.

  uv run --offline --python 3.9 -m evidence.g3c1_mock
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from evidence.prompts import ternary_condition_tier_policy
from evidence.visibility import W2_CONDITIONS

from evidence import g3c1_common as C

CLAIM = 'This fix is correct and all relevant tests pass.'


def _http(base, method, path, obj=None):
    data = json.dumps(obj).encode('utf-8') if obj is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8'), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8'), dict(he.headers)


def _j(st_body):
    st, body, _ = st_body
    return st, (json.loads(body) if body else None)


class ScriptedG3C1Agent:
    """Evidence-faithful deterministic mock. NEED_EVIDENCE whenever the
    applicable acceptance surface is withheld or evidence isn't linked/fresh."""

    def __init__(self, fx, cond):
        self.fx, self.cond = fx, cond
        self.trace, self.model_calls = [], 0
        self.flags = {'linked': None, 'fresh': None, 'complete': None,
                      'consistency': None, 'saw_v2': False, 'baseline_seen':
                      False, 'strict_403': False, 'escalation': []}

    def _note(self, tool, st, preview):
        self.trace.append({'tool': tool, 'http_status': st,
                           'preview': str(preview)[:300]})

    def run_static_a(self, art):
        # T2A institutional: the presented record carries executed outcomes.
        summ = (art or {}).get('summary') or {}
        fail = summ.get('f2p_failed_ids') or []
        regr = summ.get('p2p_regressed_ids') or []
        self.model_calls = 1
        if fail or regr:
            return 'REJECT', f'institutionally presented record has ' \
                             f'{len(fail)} f2p failures, {len(regr)} regressions'
        ft = int(summ.get('f2p_total') or 0)
        pt = int(summ.get('p2p_total') or 0)
        if ft + pt > 0 and int(summ.get('f2p_passed') or 0) == ft \
                and int(summ.get('p2p_passed') or 0) == pt:
            return 'ACCEPT', 'institutionally presented complete all-green record'
        return 'NEED_EVIDENCE', 'presented record not a complete executed set'

    def run(self, base):
        fx, cond = self.fx, self.cond
        active, tier, policy = ternary_condition_tier_policy(cond)
        st, body, _ = _http(base, 'POST', '/sessions', {
            'instance_id': fx['instance_id'], 'base_commit': fx['base_commit'],
            'patch_sha256': fx['patch_sha256'], 'cell': f'{fx["instance_id"]}:{cond}',
            'served_artifact_id': fx['served_artifact_id'],
            'evidence_tier': tier, 'policy': policy, 'claim': CLAIM,
            'symptom': fx['symptom']})
        self._note('open_session', st, body)
        if st != 201:
            return 'NEED_EVIDENCE', 'session open failed'
        sid = json.loads(body)['session_id']

        def get(path):
            s, b, h = _http(base, 'GET', f'/sessions/{sid}/{path}')
            self._note(path, s, b[:200])
            return s, b, h

        st, b, _ = get('artifact')
        art = (json.loads(b).get('artifact') if st == 200 else None) or {}
        self.flags['saw_v2'] = art.get('projection_version') == \
            C.PROJECTION_V2_VERSION
        self.flags['baseline_seen'] = 'pass_to_pass_baseline' in art

        if not active:
            if tier == 'A':
                return self.run_static_a(art)
            # T2D-T diagnostic: outcomes withheld, L/F/C not adjudicated.
            self.model_calls = 1
            return 'NEED_EVIDENCE', \
                'diagnostic v2: acceptance outcomes withheld; no applicable ' \
                'acceptance verdict'

        st, b, _ = get('verify')
        self.flags['linked'] = (json.loads(b).get('linked')
                                if st == 200 else None)
        st, b, _ = get('freshness')
        fr = json.loads(b) if st == 200 else {}
        self.flags['fresh'] = fr.get('fresh')
        st, b, _ = get('coverage')
        self.flags['complete'] = (json.loads(b).get('complete')
                                  if st == 200 else None)
        get('log/symptom')
        applicable = self.flags['linked'] is True and \
            self.flags['fresh'] is True

        if policy == 'strict':
            st, b, _ = get('log/f2p')
            if st == 403:
                self.flags['strict_403'] = True
            _j(_http(base, 'POST', f'/sessions/{sid}/consistency', {}))
            self.model_calls = 2
            # Acceptance hard-blocked: strict can never reach a maintainer
            # decision for these resolved-symptom issues.
            return 'NEED_EVIDENCE', 'strict: acceptance logs 403-blocked'

        if policy == 'escalate':
            st0, _, _ = get('log/f2p')  # expect 400
            self.flags['escalation'].append(f'f2p_no_reason:{st0}')
            st1, _, h1 = get('log/f2p?reason=g3c1%20mock%20decision')
            self.flags['escalation'].append(
                f"f2p_reason:{st1}:{h1.get('X-Evidence-Tier-Escalation')}")
            _j(_http(base, 'POST', f'/sessions/{sid}/consistency', {}))
            st2, b2, _ = _http(base, 'POST',
                               f'/sessions/{sid}/consistency',
                               {'reason': 'g3c1 mock decision'})
            cons = json.loads(b2) if st2 == 200 else {}
            self.flags['consistency'] = cons.get('verdict')
            self.model_calls = 2
        else:  # T3A-T ungated
            get('log/f2p')
            st2, b2, _ = _http(base, 'POST',
                               f'/sessions/{sid}/consistency', {})
            cons = json.loads(b2) if st2 == 200 else {}
            self.flags['consistency'] = cons.get('verdict')
            self.model_calls = 2

        if not applicable:
            return 'NEED_EVIDENCE', 'evidence not linked/fresh for this patch'
        if self.flags['consistency'] == 'contradicted':
            return 'REJECT', 'applicable acceptance evidence contradicts the ' \
                             'positive claim'
        if self.flags['complete'] and self.flags['consistency'] == 'consistent':
            return 'ACCEPT', 'linked, fresh, complete, failure-free success'
        return 'NEED_EVIDENCE', 'completeness/success not established'


def run():
    from evidence import g3c1_server as GS
    certs = {(c['instance_id'], c['condition']): c
             for c in C.read_jsonl(C.OUT_GOLD /
                                   'g3c1_condition_certificates.jsonl')}
    fxs = []
    from evidence.schemas import make_artifact_id
    for t in C.read_jsonl(C.TRUTH):
        lp = t.get('label_provenance', {})
        fxs.append({'instance_id': t['instance_id'], 'id': t['id'],
                    'base_commit': t['base_commit'],
                    'patch_sha256': t['patch_sha256'],
                    'served_artifact_id': make_artifact_id(
                        t['instance_id'], t['patch_sha256']),
                    'symptom': {'pre_patch_passed':
                                lp.get('symptom_pre_patch_passed'),
                                'post_patch_passed':
                                lp.get('symptom_post_patch_passed')}})
    fxs.sort(key=lambda x: x['instance_id'])

    tmp = tempfile.mkdtemp(prefix='g3c1_mock_store_')
    shutil.copytree(str(C.OUT_STORE), tmp, dirs_exist_ok=True)
    httpd = GS.build_g3c1_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    rows = []
    try:
        for fx in fxs:
            for cond in W2_CONDITIONS:
                ag = ScriptedG3C1Agent(fx, cond)
                decision, reason = ag.run(base)
                cert = certs[(fx['instance_id'], cond)]
                rows.append({
                    'protocol': C.G3C1_PROTOCOL_VERSION, 'mock': True,
                    'research_excluded': True,
                    'cell': f'{fx["instance_id"]}:{cond}',
                    'id': fx['id'], 'instance_id': fx['instance_id'],
                    'condition': cond, 'mock_model': 'scripted-g3c1-v1',
                    'decision': decision, 'reason': reason,
                    'tool_calls': len(ag.trace), 'tool_trace': ag.trace,
                    'model_calls': ag.model_calls,
                    'saw_projection_v2_tag': ag.flags['saw_v2'],
                    'saw_baseline_map_at_tier_d': ag.flags['baseline_seen']
                    if cond != 'T2A-T' and cond != 'T3A-T' else None,
                    'strict_denied_403': ag.flags['strict_403'],
                    'escalation_sequence': ag.flags['escalation'],
                    'api_calls': 0, 'cost_usd': 0.0,
                    'audit_condition_gold': cert['condition_gold'],
                    'mock_matches_condition_gold':
                        decision == cert['condition_gold'],
                    'gold_tier': 'PROVISIONAL', 'annotators': 1,
                    'annotator2': 'NOT_OBTAINED'})
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def main():
    rows = run()
    C.ensure_out_dirs()
    C.write_jsonl(C.OUT_RUNS / 'g3c1_mock_results.jsonl', rows)
    n = len(rows)
    agree = sum(1 for r in rows if r['mock_matches_condition_gold'])
    dist = {}
    for r in rows:
        dist.setdefault(r['condition'], {})
        dist[r['condition']][r['decision']] = \
            dist[r['condition']].get(r['decision'], 0) + 1
    audit = {
        'document': 'G3-C.1 task 7: 40-cell offline mock pipeline audit. Mock '
                    'decisions are research-excluded; validates plumbing and '
                    'frozen-protocol alignment only.',
        'design_version': C.G3C1_DESIGN_VERSION,
        'protocol_version': C.G3C1_PROTOCOL_VERSION,
        'n_cells': n, 'n_mock_models': 1, 'api_calls_total': 0,
        'cost_usd_total': 0.0,
        'mock_matches_condition_gold': agree,
        'mock_match_rate': agree / n,
        'strict_403_cells': sum(1 for r in rows if r['strict_denied_403']),
        'all_active_diagnostic_cells_saw_v2_tag': all(
            r['saw_projection_v2_tag'] for r in rows
            if r['condition'] in ('T3D-Strict', 'T3D-Escalate')),
        'baseline_map_leaked_at_tier_d_cells': sum(
            1 for r in rows if r['saw_baseline_map_at_tier_d'] is True),
        'decision_distribution': dist,
        'note': 'A 100% mock/gold match is EXPECTED for these genuinely built '
                'issues under the frozen protocol and is not a model result.',
        'gold_authority': C.GOLD_AUTHORITY,
    }
    C.write_canonical(C.OUT_AUDIT / 'g3c1_mock_audit.json', audit)
    print(f"cells={n} match={agree}/{n} rate={audit['mock_match_rate']} "
          f"api_calls=0 cost=0")
    print('distribution:', json.dumps(dist))
    if agree != n:
        bad = [f"{r['cell']} mock={r['decision']} gold="
               f"{r['audit_condition_gold']}"
               for r in rows if not r['mock_matches_condition_gold']]
        for x in bad:
            print('  MISMATCH', x)
        raise SystemExit('g3c1 mock did not reproduce frozen condition gold')


if __name__ == '__main__':
    main()
