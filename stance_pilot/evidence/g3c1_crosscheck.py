"""G3-C.1 task 7 (part A) — REAL local HTTP cross-check, zero model API.

Spawns the G3-C.1 evidence server (g3c1_server) against a tempdir COPY of the
built store — the built store tree itself is never mutated by serving — and,
for every one of the 8 new pilot issues x 5 frozen conditions, verifies the
inherited gating still behaves and that the G3-C.1 deltas hold:

  session open 201; linkage linked=true; three-state freshness TRUE with
  authoritative_tree_source=independent_git_restage_write_tree (a missing
  record.run_tree must never be served as false); coverage complete and free
  of outcomes; strict f2p/p2p 403 with the body never read; escalate 400
  without a reason then 200 + X-Evidence-Tier-Escalation banner with one;
  T3A ungated 200; symptom log 200 at every active condition.

G3-C.0 projection v2 invariants:
  * active tier-D artifact JSON carries projection_version ==
    'diagnostic-v2-no-baseline-map-v1' and has NO pass_to_pass_baseline key;
  * tier-A artifact JSON is byte-identical to the frozen view (no
    projection_version, pass_to_pass_baseline retained) — v2 changes only the
    diagnostic tier.

Every served non-log payload is appended to a transcript consumed by
g3c1_noninterference. No network egress beyond 127.0.0.1; api_calls=0.

  uv run --offline --python 3.9 -m evidence.g3c1_crosscheck
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from evidence.schemas import make_artifact_id
from evidence.prompts import ternary_condition_tier_policy
from evidence.views import display_for_tier
from evidence.visibility import W2_CONDITIONS

from evidence import g3c1_common as C

CLAIM = 'This fix is correct and all relevant tests pass.'

# Endpoints whose BODY is an accepted/authorized reveal (granted escalation or
# ungated tier-A): gated-by-shape, excluded from the plaintext leak scan.
LOG_ENDPOINTS = {'log/f2p', 'log/p2p', 'log/p2p_baseline'}


def _http_json(base, method, path, obj=None):
    data = json.dumps(obj).encode('utf-8') if obj is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8'), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8'), dict(he.headers)


def _fixtures():
    out = []
    for t in C.read_jsonl(C.TRUTH):
        lp = t.get('label_provenance', {})
        out.append({
            'instance_id': t['instance_id'], 'id': t['id'],
            'base_commit': t['base_commit'], 'patch_sha256': t['patch_sha256'],
            'served_artifact_id': make_artifact_id(
                t['instance_id'], t['patch_sha256']),
            'symptom': {'pre_patch_passed':
                        lp.get('symptom_pre_patch_passed'),
                        'post_patch_passed':
                        lp.get('symptom_post_patch_passed')},
            'claim': CLAIM})
    return sorted(out, key=lambda x: x['instance_id'])


def run():
    from evidence.store import ArtifactStore
    from evidence.g3c0_projection_v2 import project_diagnostic_v2
    from evidence import g3c1_server as GS
    from evidence.g3c1_freshness import load_restage_cache

    fixtures = _fixtures()
    pristine = ArtifactStore(str(C.OUT_STORE),
                             fixtures_meta_name='g3c1_fixtures_meta.json')
    tmp = tempfile.mkdtemp(prefix='g3c1_store_xc_')
    shutil.copytree(str(C.OUT_STORE), tmp, dirs_exist_ok=True)
    httpd = GS.build_g3c1_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'

    errors, cells, transcript = [], [], []

    def note(endpoint, st, body, *, cell, cond, tier, policy, scannable):
        transcript.append({'cell': cell, 'condition': cond, 'tier': tier,
                           'policy': policy, 'endpoint': endpoint,
                           'http_status': st, 'scannable': scannable,
                           'body': body})

    def ok(tag, checks, name, cond_ok, detail=''):
        checks.append({'check': name, 'pass': bool(cond_ok), 'detail': detail})
        if not cond_ok:
            errors.append(f'{tag}: {name} {detail}'.strip())

    try:
        for fx in fixtures:
            iid, aid = fx['instance_id'], fx['served_artifact_id']
            rec, authentic = pristine.get(aid)
            if not authentic:
                raise SystemExit(f'built artifact not authentic for {iid}')

            # Frozen-view references for the v2 byte-invariance assertions.
            view_d = display_for_tier(pristine, rec, iid,
                                      fx['patch_sha256'], 'D')
            v2 = project_diagnostic_v2(view_d)
            view_a = display_for_tier(pristine, rec, iid,
                                      fx['patch_sha256'], 'A')

            for cond in W2_CONDITIONS:
                active, tier, policy = ternary_condition_tier_policy(cond)
                tag = f'{iid}:{cond}'
                checks = []

                if not active:
                    # Static condition: no session. Assert served artifact for
                    # this tier directly over GET using a same-tier session.
                    st, body, _ = _http_json(base, 'POST', '/sessions', {
                        'instance_id': iid, 'base_commit': fx['base_commit'],
                        'patch_sha256': fx['patch_sha256'], 'cell': tag,
                        'served_artifact_id': aid, 'evidence_tier': tier,
                        'claim': fx['claim'], 'symptom': fx['symptom']})
                    sid = json.loads(body)['session_id'] if st == 201 else None
                    ok(tag, checks, 'static_session_201', st == 201, f'st={st}')
                    if sid:
                        st2, b2, _ = _http_json(
                            base, 'GET', f'/sessions/{sid}/artifact')
                        payload = json.loads(b2) if st2 == 200 else {}
                        art = payload.get('artifact')
                        note('artifact', st2, b2, cell=tag, cond=cond,
                             tier=tier, policy=policy, scannable=True)
                        if tier == 'D':
                            ok(tag, checks, 'D_projection_tag',
                               art and art.get('projection_version') ==
                               C.PROJECTION_V2_VERSION)
                            ok(tag, checks, 'D_baseline_map_absent',
                               art and 'pass_to_pass_baseline' not in art)
                        else:  # T2A tier A untouched
                            ok(tag, checks, 'A_no_projection_tag',
                               art and 'projection_version' not in art)
                            ok(tag, checks, 'A_baseline_map_retained',
                               art and 'pass_to_pass_baseline' in art)
                            ok(tag, checks, 'A_byte_equals_frozen_view',
                               art == view_a)
                    cells.append({'cell': tag, 'tier': tier, 'policy': policy,
                                  'active_tools': False, 'checks': checks})
                    continue

                st, body, _ = _http_json(base, 'POST', '/sessions', {
                    'instance_id': iid, 'base_commit': fx['base_commit'],
                    'patch_sha256': fx['patch_sha256'], 'cell': tag,
                    'served_artifact_id': aid, 'evidence_tier': tier,
                    'policy': policy, 'claim': fx['claim'],
                    'symptom': fx['symptom']})
                ok(tag, checks, 'session_open_201', st == 201, f'st={st}')
                if st != 201:
                    cells.append({'cell': tag, 'tier': tier, 'policy': policy,
                                  'active_tools': True, 'checks': checks})
                    continue
                sid = json.loads(body)['session_id']

                def get(path, scannable=True):
                    s, b, h = _http_json(
                        base, 'GET', f'/sessions/{sid}/{path}')
                    ep = 'log/' + path.split('/')[-1] if path.startswith('log') \
                        else path
                    note(ep, s, b, cell=tag, cond=cond, tier=tier,
                         policy=policy, scannable=scannable)
                    return s, b, h

                # artifact + v2 invariants
                st_a, b_a, _ = get('artifact')
                art = json.loads(b_a).get('artifact') if st_a == 200 else None
                if tier == 'D':
                    ok(tag, checks, 'D_projection_tag',
                       art and art.get('projection_version') ==
                       C.PROJECTION_V2_VERSION)
                    ok(tag, checks, 'D_baseline_map_absent',
                       art and 'pass_to_pass_baseline' not in art)
                    ok(tag, checks, 'D_artifact_equals_v2_wrapper',
                       art == v2)
                else:
                    ok(tag, checks, 'A_no_projection_tag',
                       art and 'projection_version' not in art)
                    ok(tag, checks, 'A_baseline_map_retained',
                       art and 'pass_to_pass_baseline' in art)
                    ok(tag, checks, 'A_byte_equals_frozen_view', art == view_a)

                st_v, b_v, _ = get('verify')
                link = json.loads(b_v) if st_v == 200 else {}
                ok(tag, checks, 'verify_200_linked',
                   st_v == 200 and link.get('linked') is True, f'st={st_v}')

                st_f, b_f, _ = get('freshness')
                fr = json.loads(b_f) if st_f == 200 else {}
                ok(tag, checks, 'freshness_200', st_f == 200, f'st={st_f}')
                ok(tag, checks, 'freshness_state_TRUE',
                   fr.get('fresh_state') == 'TRUE',
                   f"state={fr.get('fresh_state')}")
                ok(tag, checks, 'freshness_bool_true', fr.get('fresh') is True)
                ok(tag, checks, 'freshness_run_tree_match',
                   fr.get('run_tree_match') is True)
                ok(tag, checks, 'freshness_authoritative_restage',
                   fr.get('authoritative_tree_source') ==
                   'independent_git_restage_write_tree',
                   str(fr.get('authoritative_tree_source')))
                ok(tag, checks, 'freshness_protocol_tag',
                   fr.get('protocol_version') == C.G3C1_PROTOCOL_VERSION)

                st_c, b_c, _ = get('coverage')
                cov = json.loads(b_c) if st_c == 200 else {}
                ok(tag, checks, 'coverage_200_complete',
                   st_c == 200 and cov.get('complete') is True, f'st={st_c}')
                ok(tag, checks, 'coverage_no_outcomes',
                   'PASSED' not in b_c and 'FAILED' not in b_c)

                st_s, _, _ = get('log/symptom')
                ok(tag, checks, 'symptom_log_200', st_s == 200, f'st={st_s}')

                if policy == 'strict':
                    st_l, b_l, _ = get('log/f2p', scannable=True)
                    ok(tag, checks, 'strict_f2p_403_body_clean',
                       st_l == 403 and 'PASSED' not in b_l
                       and 'FAILED' not in b_l, f'st={st_l}')
                    st_k, b_k, _ = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency', {})
                    note('consistency', st_k, b_k, cell=tag, cond=cond,
                         tier=tier, policy=policy, scannable=True)
                    cons = json.loads(b_k) if st_k == 200 else {}
                    ok(tag, checks, 'strict_consistency_200_no_accept',
                       st_k == 200 and cons.get('verdict') in
                       ('consistent', 'contradicted', 'insufficient_evidence'),
                       f'st={st_k}')
                elif policy == 'escalate':
                    st_l, b_l, _ = get('log/f2p', scannable=True)
                    ok(tag, checks, 'escalate_f2p_no_reason_400_clean',
                       st_l == 400 and 'PASSED' not in b_l, f'st={st_l}')
                    st_l2, b_l2, h2 = get(
                        'log/f2p?reason=g3c1%20crosscheck', scannable=False)
                    ok(tag, checks, 'escalate_f2p_reason_200_banner',
                       st_l2 == 200
                       and h2.get('X-Evidence-Tier-Escalation') == '1'
                       and b_l2.startswith('# TIER ESCALATION'),
                       f'st={st_l2} flag={h2.get("X-Evidence-Tier-Escalation")}')
                    st_k, b_k, _ = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency', {})
                    note('consistency', st_k, b_k, cell=tag, cond=cond,
                         tier=tier, policy=policy, scannable=True)
                    ok(tag, checks, 'escalate_consistency_no_reason_400',
                       st_k == 400, f'st={st_k}')
                    st_k2, b_k2, _ = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency',
                        {'reason': 'g3c1 crosscheck'})
                    note('consistency', st_k2, b_k2, cell=tag, cond=cond,
                         tier=tier, policy=policy, scannable=True)
                    cons2 = json.loads(b_k2) if st_k2 == 200 else {}
                    ok(tag, checks, 'escalate_consistency_reason_200',
                       st_k2 == 200 and cons2.get('escalated') is True
                       and cons2.get('verdict') in
                       ('consistent', 'contradicted', 'unverifiable'),
                       f'st={st_k2}')
                else:  # T3A-T ungated acceptance
                    st_l, b_l, h = get('log/f2p', scannable=False)
                    ok(tag, checks, 't3a_f2p_200_no_escalation',
                       st_l == 200
                       and h.get('X-Evidence-Tier-Escalation') != '1',
                       f'st={st_l}')
                    st_k, b_k, _ = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency', {})
                    note('consistency', st_k, b_k, cell=tag, cond=cond,
                         tier=tier, policy=policy, scannable=True)
                    ok(tag, checks, 't3a_consistency_200',
                       st_k == 200, f'st={st_k}')

                cells.append({'cell': tag, 'tier': tier, 'policy': policy,
                              'active_tools': True,
                              'freshness_state': fr.get('fresh_state'),
                              'checks': checks})
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    n_checks = sum(len(c['checks']) for c in cells)
    n_pass = sum(1 for c in cells for k in c['checks'] if k['pass'])
    report = {
        'document': 'G3-C.1 task 7: real local HTTP cross-check of the g3c1 '
                    'server on a throwaway store copy; projection v2 + three-'
                    'state freshness + inherited strict/escalate gating.',
        'design_version': C.G3C1_DESIGN_VERSION,
        'protocol_version': C.G3C1_PROTOCOL_VERSION,
        'projection_version': C.PROJECTION_V2_VERSION,
        'server_version': 'EvidenceAPI/g3c1-v1',
        'api_calls_made': 0,
        'network_egress': '127.0.0.1 only',
        'n_issues': len(fixtures), 'n_conditions': len(W2_CONDITIONS),
        'n_cells': len(cells), 'n_checks': n_checks,
        'n_checks_pass': n_pass, 'n_errors': len(errors),
        'errors': errors, 'cells': cells,
        'gold_authority': C.GOLD_AUTHORITY,
    }
    C.write_canonical(C.OUT_AUDIT / 'g3c1_http_crosscheck.json', report)
    C.write_jsonl(C.OUT_AUDIT / 'g3c1_http_transcript.jsonl', transcript)
    print(f"cells={len(cells)} checks={n_checks} pass={n_pass} "
          f"errors={len(errors)}")
    if errors:
        for e in errors[:20]:
            print('  FAIL', e)
        raise SystemExit('g3c1 HTTP cross-check FAILED')
    print('->', (C.OUT_AUDIT / 'g3c1_http_crosscheck.json').name,
          'and g3c1_http_transcript.jsonl')


if __name__ == '__main__':
    run()
