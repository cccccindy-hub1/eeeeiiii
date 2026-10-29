"""Gate 3-B.2 (tasks 5 & 7) — three-way consistency matrix + real-HTTP check.

Task 5 — for each of the five conditions, prove agreement across three
independently-derived descriptions:
  (A) Gold Policy        : the frozen gold_w2 rule's per-channel status + gold
  (B) Model-Visible      : the g3b2 prompt scaffolding + rendered static block
                           (institutional grant for T2A; three-state freshness
                           note for active conditions)
  (C) Actual Tool Surface: the REAL in-process g3b2 HTTP server's behaviour on
                           a throwaway copy of the signed store (200/403/400,
                           banners/headers, three-state freshness body).

Task 7 — spawn the real local g3b2 server (g3b2_server.build_g3b2_server) on a
tempdir copytree of the G3-A store (the frozen store's audit.jsonl is never
touched) and verify static rendering, tool returns, 403/400/200 gating,
signatures, linkage, coverage, provenance, and the repaired three-state
freshness for all 10 issues. No model/API request.

Acceptance condition 3: T2D-T and T3D-Strict stay genuinely restricted;
T3D-Escalate stays reason-gated; T2A-T's institutional premise is explicit;
T3A-T full access + the repaired unified freshness rule.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.visibility import (project_surface, W2_CONDITIONS,
                                  O_NOT_VISIBLE, O_HARD_BLOCKED,
                                  O_OBTAINABLE_WITH_REASON, O_PRESENTED,
                                  O_OBTAINABLE)
from evidence.gold_w2 import condition_gold
from evidence.prompts import ternary_condition_tier_policy

from evidence import g3b2_common as C
from evidence import g3b2_freeze as GZ
from evidence import g3b2_freshness as GF
from evidence import g3b2_prompts as GP


def _http_json(base, method, path, obj=None):
    data = json.dumps(obj).encode('utf-8') if obj is not None else None
    req = urllib.request.Request(
        base + path, data=data, method=method,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8')
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8')


def _http_raw(base, path):
    req = urllib.request.Request(base + path, method='GET')
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8'), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8'), dict(he.headers)


def _fixtures_and_facts():
    """Build the 10 cross-check fixtures + repaired oracle fact bundles."""
    store = ArtifactStore(str(C.G3A_STORE),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    gold = {g['instance_id']: g for g in C.read_jsonl(C.G3A_GOLD)}
    raw = {r['instance_id']: r for r in C.read_jsonl(C.G3A_TARGET_ROWS)}
    restage = GF.load_restage_cache()
    fixtures, facts_by_iid = [], {}
    for iid in sorted(raw):
        grow = gold[iid]
        patch = grow['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        att = store.get_attestation(iid, patch)
        from evidence.views import display_for_tier
        pres_a = display_for_tier(store, rec, iid, patch, 'A')
        vfresh = GF.adjudicate_freshness(
            rec=rec, authentic=authentic, att=att,
            sess={'instance_id': iid, 'base_commit': grow['base_commit'],
                  'patch_sha256': patch},
            restaged_tree=(restage.get(iid) or {}).get('recomputed_run_tree'),
            patch_match=True)
        facts = GZ._issue_fact_bundle(grow, pres_a, vfresh['fresh_state'])
        symptom = {'pre_patch_passed': grow['facts']['symptom_pre_passed'],
                   'post_patch_passed': grow['facts']['symptom_post_passed']}
        fx = {'id': grow['id'], 'instance_id': iid,
              'base_commit': grow['base_commit'], 'patch_sha256': patch,
              'served_artifact_id': aid, 'symptom': symptom,
              'claim': 'This fix is correct and all relevant tests pass.'}
        fixtures.append(fx)
        facts_by_iid[iid] = facts
    return fixtures, facts_by_iid


# ---------------------------------------------------------------------------
# Task 7: real-HTTP cross-check on a throwaway store copy
# ---------------------------------------------------------------------------

def http_crosscheck(fixtures):
    from evidence import g3b2_server as GS
    tmp = tempfile.mkdtemp(prefix='g3b2_store_')
    shutil.copytree(str(C.G3A_STORE), tmp, dirs_exist_ok=True)
    httpd = GS.build_g3b2_server(tmp, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    errors, cells = [], []
    try:
        for fx in fixtures:
            aid = fx['served_artifact_id']
            iid = fx['instance_id']
            for cond in W2_CONDITIONS:
                active, tier, policy = ternary_condition_tier_policy(cond)
                tag = f'{iid}:{cond}'
                checks = []

                def ok(name, cond_ok, detail=''):
                    checks.append({'check': name, 'pass': bool(cond_ok),
                                   'detail': detail})
                    if not cond_ok:
                        errors.append(f'{tag}: {name} {detail}')

                # Static conditions: no session/tools; verify rendered block.
                if not active:
                    # Recreate the exact static block the model is served.
                    sim_store = ArtifactStore(str(C.G3A_STORE),
                                              fixtures_meta_name=
                                              'g3a_fixtures_meta.json')
                    rec = sim_store.get(aid)[0]
                    from evidence.views import display_for_tier
                    proj = display_for_tier(sim_store, rec, iid,
                                            fx['patch_sha256'], tier)
                    block = GP.g3b2_evidence_block(
                        proj, tier=tier, symptom=fx['symptom'])
                    if tier == 'D':
                        ok('T2D_no_outcome_leak',
                           'FAIL_TO_PASS passed' not in block
                           and 'failing acceptance test ids' not in block)
                        ok('T2D_symptom_rendered',
                           'issue symptom present before patch' in block)
                    else:
                        ok('T2A_outcomes_rendered',
                           'FAIL_TO_PASS passed' in block)
                        ok('T2A_institutional_warranty_header',
                           'institutionally attested for THIS patch/commit'
                           in block)
                        ok('T2A_no_stale_linkage_phrase',
                           'linkage not yet verified' not in block)
                        ok('T2A_no_verdict_token',
                           'REJECT' not in block and 'ACCEPT' not in block
                           .replace('ACCEPTANCE', ''))
                    cells.append({'cell': tag, 'tier': tier,
                                  'active_tools': False, 'checks': checks})
                    continue

                st, body = _http_json(base, 'POST', '/sessions', {
                    'instance_id': iid,
                    'base_commit': fx['base_commit'],
                    'patch_sha256': fx['patch_sha256'], 'cell': tag,
                    'served_artifact_id': aid, 'evidence_tier': tier,
                    'policy': policy, 'claim': fx['claim'],
                    'symptom': fx['symptom']})
                ok('session_open_201', st == 201, f'st={st} {body[:100]}')
                if st != 201:
                    cells.append({'cell': tag, 'tier': tier,
                                  'active_tools': True, 'checks': checks})
                    continue
                sid = json.loads(body)['session_id']

                # linkage
                st, b = _http_json(base, 'GET', f'/sessions/{sid}/verify')
                link = json.loads(b) if st == 200 else {}
                ok('linkage_200_linked', st == 200 and link.get('linked') is True,
                   f'st={st}')

                # freshness — THE repair: three-state, TRUE for genuine issues
                st, b = _http_json(base, 'GET', f'/sessions/{sid}/freshness')
                fr = json.loads(b) if st == 200 else {}
                ok('freshness_200', st == 200, f'st={st}')
                ok('freshness_state_TRUE', fr.get('fresh_state') == 'TRUE',
                   f"state={fr.get('fresh_state')}")
                ok('freshness_true_bool', fr.get('fresh') is True,
                   f"fresh={fr.get('fresh')}")
                ok('freshness_run_tree_match_true',
                   fr.get('run_tree_match') is True,
                   f"match={fr.get('run_tree_match')}")
                ok('freshness_authoritative_restage',
                   fr.get('authoritative_tree_source') ==
                   'independent_git_restage_write_tree',
                   str(fr.get('authoritative_tree_source')))
                ok('freshness_not_false_negative',
                   fr.get('record_run_tree_present') is False
                   and fr.get('fresh') is not False,
                   'absent record.run_tree must not force false')

                # coverage
                st, b = _http_json(base, 'GET', f'/sessions/{sid}/coverage')
                cov = json.loads(b) if st == 200 else {}
                ok('coverage_200_complete', st == 200
                   and cov.get('complete') is True, f'st={st}')
                ok('coverage_no_outcomes',
                   'f2p_outcomes' not in b
                   and '"PASSED"' not in b and '"FAILED"' not in b)

                # symptom log available at every active condition
                st, _, _ = _http_raw(base, f'/sessions/{sid}/log/symptom')
                ok('symptom_log_200', st == 200, f'st={st}')

                # acceptance-log + consistency gating by policy
                if policy == 'strict':
                    st, _, _ = _http_raw(base, f'/sessions/{sid}/log/f2p')
                    ok('strict_f2p_403', st == 403, f'st={st}')
                    st, b = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    ok('strict_consistency_200', st == 200, f'st={st}')
                elif policy == 'escalate':
                    st, _, _ = _http_raw(base, f'/sessions/{sid}/log/f2p')
                    ok('escalate_f2p_no_reason_400', st == 400, f'st={st}')
                    st, b2, hdr = _http_raw(
                        base,
                        f'/sessions/{sid}/log/f2p?reason=g3b2%20decision')
                    ok('escalate_f2p_with_reason_200_banner',
                       st == 200
                       and hdr.get('X-Evidence-Tier-Escalation') == '1'
                       and b2.startswith('# TIER ESCALATION'),
                       f'st={st} flag={hdr.get("X-Evidence-Tier-Escalation")}')
                    st, _ = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    ok('escalate_consistency_no_reason_400', st == 400,
                       f'st={st}')
                    st, b2 = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency',
                        {'reason': 'g3b2 decision'})
                    ok('escalate_consistency_with_reason_200',
                       st == 200 and json.loads(b2).get('escalated') is True,
                       f'st={st}')
                else:  # T3A full access
                    st, _, hdr = _http_raw(base, f'/sessions/{sid}/log/f2p')
                    ok('t3a_f2p_200_no_escalation_flag',
                       st == 200
                       and hdr.get('X-Evidence-Tier-Escalation') != '1',
                       f'st={st} flag={hdr.get("X-Evidence-Tier-Escalation")}')
                    st, _ = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    ok('t3a_consistency_200', st == 200, f'st={st}')

                cells.append({'cell': tag, 'tier': tier, 'policy': policy,
                              'active_tools': True,
                              'freshness': {'state': fr.get('fresh_state'),
                                            'fresh': fr.get('fresh'),
                                            'run_tree_match':
                                                fr.get('run_tree_match'),
                                            'authoritative_tree_source':
                                                fr.get(
                                                    'authoritative_tree_source')},
                              'checks': checks})
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    report = {
        'document': 'Gate 3-B.2 task 7: real local g3b2 HTTP server '
                    'cross-check on a throwaway store copy (zero API).',
        'protocol_version': C.PROTOCOL_VERSION,
        'n_cells': len(cells),
        'n_checks': sum(len(c['checks']) for c in cells),
        'n_checks_pass': sum(1 for c in cells for k in c['checks'] if k['pass']),
        'n_errors': len(errors), 'errors': errors, 'cells': cells,
        'gold_authority': C.GOLD_AUTHORITY,
    }
    return report


# ---------------------------------------------------------------------------
# Task 5: three-way consistency matrix
# ---------------------------------------------------------------------------

def _model_visible_description(cond):
    active, tier, policy = ternary_condition_tier_policy(cond)
    msgs = GP.build_g3b2_messages(
        {'condition': cond,
         'issue': 'ISSUE-PLACEHOLDER', 'patch': 'PATCH-PLACEHOLDER',
         'claim': 'CLAIM-PLACEHOLDER', 'symptom': None},
        artifact=None)
    head_text = msgs[1]['content']
    return {
        'tier': tier, 'active_tools': active, 'policy': policy,
        't2a_institutional_grant_present':
            'INSTITUTIONAL TRUST MANDATE' in head_text if cond == 'T2A-T'
            else False,
        'three_state_freshness_note_present':
            'Freshness semantics (this protocol)' in head_text if active
            else False,
        'acceptance_outcome_visible_in_static':
            (not active) and tier == 'A',
        'symptom_visible_in_static': (not active) and tier == 'D',
        'prompt_fingerprint': GP.g3b2_prompt_fingerprint(cond),
    }


def _tool_surface_expected(cond):
    return {
        'T2D-T': {'tools_offered': False, 'acceptance_log': 'n/a_static',
                  'consistency': 'n/a_static'},
        'T3D-Strict': {'tools_offered': True, 'acceptance_log': '403_denied',
                       'consistency': 'symptom_only_no_reason_gate'},
        'T3D-Escalate': {'tools_offered': True,
                         'acceptance_log': '400_without_reason_then_200',
                         'consistency': '400_without_reason_then_200'},
        'T2A-T': {'tools_offered': False, 'acceptance_log': 'n/a_static',
                  'consistency': 'n/a_static'},
        'T3A-T': {'tools_offered': True, 'acceptance_log': '200_ungated',
                  'consistency': 'acceptance_based_200'},
    }[cond]


def build_matrix(fixtures, facts_by_iid, http_report):
    # Aggregate actual-tool-surface conformance per condition from the HTTP run.
    actual = {}
    for cond in W2_CONDITIONS:
        cond_cells = [c for c in http_report['cells']
                      if c['cell'].endswith(':' + cond)]
        n = len(cond_cells)
        all_pass = all(k['pass'] for c in cond_cells for k in c['checks'])
        if cond in ('T3D-Strict', 'T3D-Escalate', 'T3A-T'):
            fresh_true = all(
                (c.get('freshness') or {}).get('state') == 'TRUE'
                for c in cond_cells)
        else:
            fresh_true = None
        actual[cond] = {'n_issues': n, 'all_http_checks_pass': all_pass,
                        'freshness_TRUE_all_issues': fresh_true}

    rows = []
    for cond in W2_CONDITIONS:
        active, tier, policy = ternary_condition_tier_policy(cond)
        # Gold-side expected channel statuses + golds across the 10 issues.
        golds, o_status, l_val, f_val, c_val, p_val = set(), set(), set(), \
            set(), set(), set()
        for fx in fixtures:
            facts = facts_by_iid[fx['instance_id']]
            surf = project_surface(cond, facts)
            g, _inp, _basis = condition_gold(cond, facts, surf)
            golds.add(g)
            o_status.add(surf['acceptance_outcomes']['status'])
            l_val.add(surf['linkage']['value'])
            f_val.add(surf['freshness']['value'])
            c_val.add(surf['coverage']['value'])
            p_val.add(surf['symptom']['polarity'])
        mv = _model_visible_description(cond)
        ts = _tool_surface_expected(cond)
        ac = actual[cond]

        # Three-way agreement predicates.
        agreement = []
        if cond == 'T2D-T':
            agreement.append(('O restricted: gold not_visible == static hides '
                              'outcomes == no tools',
                              o_status == {O_NOT_VISIBLE}
                              and not mv['acceptance_outcome_visible_in_static']
                              and not ts['tools_offered']))
            agreement.append(('P observable: gold symptom rendered == D block',
                              mv['symptom_visible_in_static']))
        if cond == 'T3D-Strict':
            agreement.append(('O hard-blocked: gold == 403 tool surface == '
                              'HTTP 403',
                              o_status == {O_HARD_BLOCKED}
                              and ts['acceptance_log'] == '403_denied'
                              and ac['all_http_checks_pass']))
            agreement.append(('F three-state TRUE via repaired endpoint',
                              f_val == {True}
                              and ac['freshness_TRUE_all_issues'] is True
                              and mv['three_state_freshness_note_present']))
        if cond == 'T3D-Escalate':
            agreement.append(('O reason-gated: gold obtainable_with_reason == '
                              '400/200 surface == HTTP',
                              o_status == {O_OBTAINABLE_WITH_REASON}
                              and ts['acceptance_log'].startswith('400')
                              and ac['all_http_checks_pass']))
            agreement.append(('F three-state TRUE via repaired endpoint',
                              f_val == {True}
                              and ac['freshness_TRUE_all_issues'] is True
                              and mv['three_state_freshness_note_present']))
        if cond == 'T2A-T':
            agreement.append(('O presented: gold institutional presentation == '
                              'A block renders outcomes',
                              o_status == {O_PRESENTED}
                              and mv['acceptance_outcome_visible_in_static']
                              and not ts['tools_offered']))
            agreement.append(('L/F/C institutional grant explicit to model',
                              mv['t2a_institutional_grant_present']
                              and not mv['three_state_freshness_note_present']))
            agreement.append(('no verdict leak in static/prompt',
                              ac['all_http_checks_pass']))
        if cond == 'T3A-T':
            agreement.append(('O obtainable: gold == ungated tool surface == '
                              'HTTP 200',
                              o_status == {O_OBTAINABLE}
                              and ts['acceptance_log'] == '200_ungated'
                              and ac['all_http_checks_pass']))
            agreement.append(('F three-state TRUE via repaired endpoint',
                              f_val == {True}
                              and ac['freshness_TRUE_all_issues'] is True
                              and mv['three_state_freshness_note_present']))

        rows.append({
            'condition': cond, 'tier': tier, 'active_tools': active,
            'policy': policy,
            'A_gold_policy': {
                'gold_values': sorted(golds),
                'acceptance_outcomes_status': sorted(o_status),
                'linkage_values': sorted(_safe(x) for x in l_val),
                'freshness_values': sorted(_safe(x) for x in f_val),
                'coverage_values': sorted(_safe(x) for x in c_val),
                'symptom_polarities': sorted(str(x) for x in p_val),
            },
            'B_model_visible': mv,
            'C_actual_tool_surface_expected': ts,
            'C_actual_http_observed': ac,
            'three_way_agreement': [
                {'requirement': name, 'pass': bool(p)}
                for name, p in agreement],
            'condition_consistent': all(p for _, p in agreement),
        })
    all_consistent = all(r['condition_consistent'] for r in rows)
    return {
        'document': 'Gate 3-B.2 task 5: Gold Policy / Model-Visible Prompt+ '
                    'Evidence / Actual Tool Surface three-way consistency '
                    'matrix.',
        'protocol_version': C.PROTOCOL_VERSION,
        'prompt_version': C.PROMPT_VERSION,
        'n_issues': len(fixtures),
        'all_conditions_consistent': all_consistent,
        'conditions': rows,
        'gold_authority': C.GOLD_AUTHORITY,
    }


def _safe(v):
    return v if isinstance(v, bool) or v is None else str(v)


def freshness_authoritative_audit(fixtures, facts_by_iid):
    restage = GF.load_restage_cache()
    rows = []
    for fx in fixtures:
        hit = restage[fx['instance_id']]
        rows.append({
            'instance_id': fx['instance_id'],
            'recomputed_run_tree': hit['recomputed_run_tree'],
            'attested_run_tree': hit['attested_run_tree'],
            'tree_matches_independent_restage': hit['tree_matches'],
            'attestation_authentic': hit['attestation_authentic'],
            'repaired_fresh_state': 'TRUE' if hit['tree_matches']
                                    and hit['attestation_authentic']
                                    else 'CHECK',
            'record_run_tree_field_present': False,
            'old_endpoint_would_have_returned': 'fresh=false (record.run_tree '
                                                'absent -> None != tree)',
            'f2p_n': hit['f2p_n'], 'p2p_scoped_n': hit['p2p_scoped_n'],
        })
    return {
        'document': 'Gate 3-B.2 task 2: authoritative freshness audit for '
                    'the 10 issues. Independent git restage tree vs signed '
                    'attestation; the old endpoint false-negative is '
                    'documented per issue.',
        'protocol_version': C.PROTOCOL_VERSION,
        'authoritative_source': str(C.G3A_FRESHNESS_CACHE.relative_to(C.HERE)),
        'all_true': all(r['tree_matches_independent_restage']
                        and r['attestation_authentic'] for r in rows),
        'issues': rows,
        'gold_authority': C.GOLD_AUTHORITY,
    }


def main():
    fixtures, facts_by_iid = _fixtures_and_facts()
    http_report = http_crosscheck(fixtures)
    C.OUT_HTTP_CROSSCHECK.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_HTTP_CROSSCHECK.write_text(
        json.dumps(http_report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f"HTTP cross-check: checks={http_report['n_checks']} "
          f"pass={http_report['n_checks_pass']} "
          f"errors={http_report['n_errors']} cells={http_report['n_cells']}")

    matrix = build_matrix(fixtures, facts_by_iid, http_report)
    C.OUT_MATRIX.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print('three-way matrix all consistent:',
          matrix['all_conditions_consistent'])

    audit = freshness_authoritative_audit(fixtures, facts_by_iid)
    C.OUT_FRESHNESS_AUDIT.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print('freshness authoritative audit all_true:', audit['all_true'])

    if http_report['n_errors'] or not matrix['all_conditions_consistent']:
        raise SystemExit('g3b2 cross-check / matrix FAILED')


if __name__ == '__main__':
    main()
