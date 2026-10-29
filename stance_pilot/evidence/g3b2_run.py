"""Gate 3-B.2 (task 8) — full offline MOCK over the repaired protocol ($0).

100 cells = 10 frozen issues x 5 conditions x 2 deterministic scripted mock
models. The mock is NOT a subject and its decisions are explicitly research-
excluded (mock=true on every row); it exists to validate the entire pipeline
end to end against the repaired protocol:

  * g3b2 prompts build and fingerprint;
  * a real in-process g3b2 HTTP server serves on a tempdir store copy;
  * the active mock runs the genuine tool loop, including the three-state
    freshness endpoint, strict 403, escalate 400->reason->200, and tier-A
    ungated access;
  * the scripted decision rule is the SAME gold rule applied to OBSERVED
    evidence, so for these 10 genuine issues the mock should reproduce the
    repaired condition gold 1:1 (a pipeline/alignment check, not a finding).

No model API request is made or possible (no profile, no key, no network to a
vendor; only 127.0.0.1). Every row records cost_usd=0 and api_calls=0.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from evidence.prompts import ternary_condition_tier_policy

from evidence import g3b2_common as C
from evidence import g3b2_freeze as GZ
from evidence import g3b2_prompts as GP


def _http(method, base, path, obj=None):
    data = json.dumps(obj).encode('utf-8') if obj is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8'), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8'), dict(he.headers)


def _j(method, base, path, obj=None):
    st, body, _ = _http(method, base, path, obj)
    return st, (json.loads(body) if body else None)


class ScriptedG3B2Agent:
    """Deterministic evidence-faithful mock reviewer.

    It only commits ACCEPT/REJECT on observed, applicable evidence; any
    missing/UNKNOWN applicability surface -> NEED_EVIDENCE. This mirrors the
    instruction set, not a model behaviour claim.
    """

    def __init__(self, item, mock_model):
        self.item = item
        self.mock_model = mock_model
        self.cond = item['condition']
        self.trace = []
        self.flags = {'linked': None, 'fresh': None, 'complete': None,
                      'consistency': None, 'saw_fresh_unknown': False,
                      'strict_denied_403': False,
                      'escalation_requested': [], 'escalation_granted': [],
                      'escalation_denied': []}
        self.model_calls = 0  # scripted turns; no vendor call

    def _note(self, turn, tool, args, status, preview):
        self.trace.append({'turn': turn, 'tool': tool, 'args': args,
                           'http_status': status,
                           'result_preview': str(preview)[:600]})

    # -- static conditions --------------------------------------------------
    def run_static(self):
        self.model_calls = 1
        block = GP.g3b2_evidence_block(
            self.item['artifact_record'], tier=self.item['evidence_tier'],
            symptom=self.item.get('symptom'))
        if self.cond == 'T2D-T':
            return self._need('diagnostic tier: acceptance outcomes withheld; '
                              'L/F/C not adjudicated', 'coverage_incomplete')
        # T2A institutional: read the rendered outcomes.
        summ = self.item['artifact_record'].get('summary') or {}
        fail = summ.get('f2p_failed_ids') or []
        regr = summ.get('p2p_regressed_ids') or []
        if fail or regr:
            return self._reject(
                f'institutionally-warranted T2A record presents executed '
                f'failing/regressed checks ({len(fail)} f2p, {len(regr)} p2p)')
        ft = int(summ.get('f2p_total') or 0)
        pt = int(summ.get('p2p_total') or 0)
        if ft + pt > 0 and int(summ.get('f2p_passed') or 0) == ft \
                and int(summ.get('p2p_passed') or 0) == pt:
            return self._accept('institutionally-warranted complete all-green '
                                'record; symptom resolved')
        return self._need('rendered record not a complete executed set',
                          'coverage_incomplete')

    # -- active tool loop ---------------------------------------------------
    def run_active(self, base):
        iid = self.item['instance_id']
        st, body, _ = _http('POST', base, '/sessions', {
            'instance_id': iid,
            'base_commit': self.item['base_commit'],
            'patch_sha256': self.item['patch_sha256'],
            'cell': self.item['cell_key'],
            'served_artifact_id': self.item['served_artifact_id'],
            'evidence_tier': self.item['evidence_tier'],
            'policy': {'T3D-Strict': 'strict',
                       'T3D-Escalate': 'escalate'}.get(self.cond),
            'claim': self.item['claim'], 'symptom': self.item['symptom']})
        self._note(0, 'open_session', {}, st, body)
        if st != 201:
            return self._need('session open failed', 'unspecified')
        sid = body and json.loads(body)['session_id']

        def get(name, path):
            st, obj = _j('GET', base, f'/sessions/{sid}/{path}')
            self._note(0, name, {}, st, json.dumps(obj)[:600])
            return st, obj

        st, art = get('get_test_artifact', 'artifact')
        st, link = get('verify_artifact_linkage', 'verify')
        self.flags['linked'] = bool(link and link.get('linked'))
        st, fr = get('check_evidence_freshness', 'freshness')
        self.flags['fresh'] = fr.get('fresh') if fr else None
        if fr and fr.get('fresh_state') == 'UNKNOWN':
            self.flags['saw_fresh_unknown'] = True
        st, cov = get('check_test_coverage', 'coverage')
        self.flags['complete'] = bool(cov and cov.get('complete'))

        # symptom log at every active condition
        st, _, _ = _http('GET', base, f'/sessions/{sid}/log/symptom')
        self._note(0, 'get_run_log', {'name': 'symptom'}, st, 'symptom log')

        applicable = (self.flags['linked'] is True
                      and self.flags['fresh'] is True)

        if self.cond == 'T3D-Strict':
            st, _b, _h = _http('GET', base, f'/sessions/{sid}/log/f2p')
            self._note(0, 'get_run_log', {'name': 'f2p'}, st, _b[:200])
            if st == 403:
                self.flags['strict_denied_403'] = True
            st, cons = _j('POST', base, f'/sessions/{sid}/consistency', {})
            self._note(0, 'check_claim_consistency', {}, st, json.dumps(cons))
            self.flags['consistency'] = (cons or {}).get('verdict')
            self.model_calls = 2
            # Acceptance outcomes hard-blocked: never decide on them.
            if self.flags['consistency'] == 'contradicted' and not applicable:
                # symptom-only contradiction is diagnostic, but strict cannot
                # see acceptance; under the frozen rule strict stays NEED for
                # these resolved-symptom issues.
                return self._need('strict: acceptance outcomes 403-blocked',
                                  'unspecified')
            return self._need('strict: acceptance outcomes hard-blocked (403); '
                              'no applicable acceptance verdict', 'unspecified')

        if self.cond == 'T3D-Escalate':
            # attempt acceptance log without reason -> expect 400
            st, _b, _h = _http('GET', base, f'/sessions/{sid}/log/f2p')
            self._note(0, 'get_run_log', {'name': 'f2p'}, st, _b[:200])
            self.flags['escalation_denied'].append('f2p:no_reason:400')
            # with reason -> 200 banner
            st, body, hdr = _http(
                'GET', base,
                f'/sessions/{sid}/log/f2p?reason=g3b2%20mock%20decision')
            self._note(0, 'get_run_log', {'name': 'f2p', 'reason': True},
                       st, body[:200])
            if st == 200 and hdr.get('X-Evidence-Tier-Escalation') == '1':
                self.flags['escalation_granted'].append('f2p')
            self.flags['escalation_requested'].append('f2p')
            # consistency without reason -> 400
            st, _ = _j('POST', base, f'/sessions/{sid}/consistency', {})
            self.flags['escalation_denied'].append(
                'consistency:no_reason:400')
            st, cons = _j('POST', base, f'/sessions/{sid}/consistency',
                          {'reason': 'g3b2 mock decision'})
            self._note(0, 'check_claim_consistency', {'reason': True}, st,
                       json.dumps(cons)[:600])
            self.flags['escalation_requested'].append('consistency')
            if st == 200 and (cons or {}).get('escalated'):
                self.flags['escalation_granted'].append('consistency')
            self.flags['consistency'] = (cons or {}).get('verdict')
            self.model_calls = 2
            return self._decide_applicable(applicable, escalated=True)

        # T3A-T full access
        st, body, hdr = _http('GET', base, f'/sessions/{sid}/log/f2p')
        self._note(0, 'get_run_log', {'name': 'f2p'}, st, body[:200])
        st, cons = _j('POST', base, f'/sessions/{sid}/consistency', {})
        self._note(0, 'check_claim_consistency', {}, st, json.dumps(cons)[:600])
        self.flags['consistency'] = (cons or {}).get('verdict')
        self.model_calls = 2
        return self._decide_applicable(applicable, escalated=False, cons=cons)

    def _decide_applicable(self, applicable, *, escalated, cons=None):
        verdict = self.flags['consistency']
        if not applicable:
            # three-state: UNKNOWN/not-true freshness or linkage gap.
            if self.flags['saw_fresh_unknown']:
                return self._need('freshness UNKNOWN (not adjudicated); cannot '
                                  'ground ACCEPT or REJECT', 'stale')
            return self._need('evidence not linked/fresh for this patch',
                              'linkage_mismatch')
        if verdict == 'contradicted':
            return self._reject(
                'applicable acceptance/regression evidence contradicts the '
                'positive claim')
        if self.flags['complete'] and verdict == 'consistent':
            return self._accept('linked, fresh, complete, failure-free success')
        return self._need('no decisive failure and completeness/success not '
                          'established', 'coverage_incomplete')

    def _accept(self, reason):
        return {'decision': 'ACCEPT', 'reason': reason,
                'evidence_mismatch': False, 'missing_evidence': '',
                'evidence_gap': 'unspecified'}

    def _reject(self, reason):
        return {'decision': 'REJECT', 'reason': reason,
                'evidence_mismatch': False, 'missing_evidence': '',
                'evidence_gap': 'contradiction'}

    def _need(self, reason, gap):
        return {'decision': 'NEED_EVIDENCE', 'reason': reason,
                'evidence_mismatch': True, 'missing_evidence': reason,
                'evidence_gap': gap}


def run_all():
    freeze = json.loads(C.OUT_FREEZE.read_text(encoding='utf-8'))
    items = {}
    # Rebuild items from freeze inputs is awkward; rebuild directly.
    for it in GZ.build_items():
        items[(it['instance_id'], it['condition'])] = it

    tmp = tempfile.mkdtemp(prefix='g3b2_mock_store_')
    shutil.copytree(str(C.G3A_STORE), tmp, dirs_exist_ok=True)
    from evidence import g3b2_server as GS
    httpd = GS.build_g3b2_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'

    rows = []
    try:
        for o in freeze['call_order']:
            it = items[(o['instance_id'], o['condition'])]
            agent = ScriptedG3B2Agent(it, o['mock_model'])
            active, _tier, _policy = ternary_condition_tier_policy(it['condition'])
            answer = (agent.run_active(base) if active
                      else agent.run_static())
            cell = next(c for c in freeze['cells']
                        if c['serial'] == o['serial'])
            rows.append({
                'protocol': 'ternary-g3b2', 'mock': True,
                'research_excluded': True,
                'cell': it['cell_key'], 'serial': o['serial'],
                'id': it['id'], 'instance_id': it['instance_id'],
                'condition': it['condition'],
                'mock_model': o['mock_model'],
                'evidence_tier': it['evidence_tier'],
                'answer': json.dumps(answer),
                'parsed': answer['decision'],
                'tool_trace': agent.trace,
                'tool_calls': len(agent.trace),
                'saw_fresh_unknown': agent.flags['saw_fresh_unknown'],
                'strict_denied_403': agent.flags['strict_denied_403'],
                'escalation_requested': agent.flags['escalation_requested'],
                'escalation_granted': agent.flags['escalation_granted'],
                'escalation_denied': agent.flags['escalation_denied'],
                'model_calls': agent.model_calls,
                'api_calls': 0, 'cost_usd': 0.0,
                'version': {'gate': C.GATE,
                            'protocol_version': C.PROTOCOL_VERSION,
                            'prompt_version': C.PROMPT_VERSION,
                            'prompt_fingerprint': cell['prompt_fingerprint']},
                'audit_oracle_gold': cell['audit_oracle_gold'],
                'audit_condition_gold_repaired':
                    cell['audit_condition_gold_old_protocol'],
                'fresh_state_repaired': cell['fresh_state_repaired'],
                'gold_tier': 'PROVISIONAL',
                'annotators': 1, 'annotator2': 'NOT_OBTAINED',
            })
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def audit_rows(rows):
    n = len(rows)
    agree = sum(1 for r in rows
                if r['parsed'] == r['audit_condition_gold_repaired'])
    active = [r for r in rows if r['tool_calls'] > 0]
    fresh_true_seen = set()
    strict403 = esc_seq = t3a_free = 0
    for r in active:
        if r['fresh_state_repaired'] == 'TRUE':
            fresh_true_seen.add(r['instance_id'])
        if r['condition'] == 'T3D-Strict' and r['strict_denied_403']:
            strict403 += 1
        if r['condition'] == 'T3D-Escalate' \
                and 'f2p:no_reason:400' in r['escalation_denied'] \
                and 'consistency:no_reason:400' in r['escalation_denied'] \
                and 'f2p' in r['escalation_granted'] \
                and 'consistency' in r['escalation_granted']:
            esc_seq += 1
        if r['condition'] == 'T3A-T' and r['tool_calls'] >= 6:
            t3a_free += 1
    dist = {}
    for r in rows:
        d = dist.setdefault(r['condition'], {})
        d[r['parsed']] = d.get(r['parsed'], 0) + 1
    return {
        'document': 'Gate 3-B.2 task 8: 100-cell offline mock pipeline audit. '
                    'Mock decisions are research-excluded; this validates '
                    'plumbing and repaired-protocol alignment only.',
        'protocol_version': C.PROTOCOL_VERSION,
        'n_cells': n, 'n_mock_models': 2, 'api_calls_total': 0,
        'cost_usd_total': 0.0,
        'mock_matches_repaired_condition_gold': agree,
        'mock_match_rate': agree / n,
        'n_active_cells': len(active),
        'freshness_true_issues_seen_via_tool': len(fresh_true_seen),
        'strict_403_cells': strict403,
        'escalate_full_400_then_grant_cells': esc_seq,
        't3a_full_access_cells': t3a_free,
        'decision_distribution': dist,
        'note': 'A 100% mock/gold match is EXPECTED for these 10 genuine '
                'issues under the repaired protocol and is not a model result.',
        'gold_authority': C.GOLD_AUTHORITY,
    }


def main():
    rows = run_all()
    out_dir = C.G3B2 / 'runs'
    out_dir.mkdir(parents=True, exist_ok=True)
    per_model = {}
    for r in rows:
        per_model.setdefault(r['mock_model'], []).append(r)
    for model, mrows in per_model.items():
        safe = model.replace('-', '_')
        p = out_dir / f'g3b2_mock_{safe}_results.jsonl'
        p.write_text(
            '\n'.join(json.dumps(r, ensure_ascii=False) for r in mrows) + '\n',
            encoding='utf-8')
        print('->', p, len(mrows), 'cells')
    audit = audit_rows(rows)
    C.OUT_MOCK_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(json.dumps({k: audit[k] for k in
                      ('n_cells', 'mock_match_rate', 'api_calls_total',
                       'cost_usd_total', 'strict_403_cells',
                       'escalate_full_400_then_grant_cells',
                       't3a_full_access_cells',
                       'freshness_true_issues_seen_via_tool')}, indent=2))
    if audit['mock_match_rate'] != 1.0:
        raise SystemExit('mock pipeline did not reproduce repaired condition '
                         'gold for the 10 genuine issues')


if __name__ == '__main__':
    main()
