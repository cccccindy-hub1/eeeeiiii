"""GroundedReview Gate 3-B.3 — LIVE INTEGRATION GATE (precondition 3), $0.

Before ANY paid model call is permitted, this module exercises the REAL
in-process g3b2 evidence server end to end over HTTP, exactly as the live
g3b3 runner will use it, but with NO model and NO network to any vendor:

  * the server is evidence.g3b2_server.build_g3b2_server, started on an
    ISOLATED tempdir copytree of the frozen G3-A store (the frozen store's
    audit.jsonl is never appended; a before/after hash snapshot proves it);
  * every one of the 10 frozen issues is driven through all 5 frozen
    conditions, opening a REAL session per active cell;
  * the repaired THREE-STATE freshness endpoint is asserted TRUE for every
    active cell, with the authoritative independent git-restage tree source,
    run_tree_match=true, and record_run_tree_present=false WITHOUT any
    structural fresh=false;
  * the frozen gates are re-proven over HTTP: T3D-Strict f2p hard 403 (a
    reason does NOT bypass it) + symptom-only consistency; T3D-Escalate
    400 without/blank reason then 200 with a non-empty reason, both for the
    acceptance log (X-Evidence-Tier-Escalation: 1 + banner) and consistency
    (escalated=true); T3A-T full 200 access with no escalation flag;
  * the static T2A/T2D blocks the model is actually served are asserted
    (institutional warranty, raw F2P/P2P outcomes, no stale-linkage phrase),
    including the SymPy-17318 regression: the visible FAIL_TO_PASS 0/1 and
    failing id test_issue_12420 remain rendered (a REJECT-oracle issue must
    keep its decisive visible failure under the repaired trust grant);
  * negative injections prove the repair never regresses: a restage cache
    miss over HTTP yields UNKNOWN / fresh=null (NEVER false) on a record
    without run_tree, and the pure three-state adjudicator is exercised for
    bad/missing signatures, base mismatch, genuine tree mismatch, and a
    present-but-absent record field.

Output (only g3b3 tree): evidence_store_g3b3/livegate/g3b3_live_gate.json
Run (offline):
    uv run --python 3.13 -m evidence.g3b3_livegate
"""
from __future__ import annotations

import json
import shutil
import tempfile
import threading
import urllib.request
import urllib.error

from evidence.prompts import ternary_condition_tier_policy

from evidence import g3b2_freshness as GF
from evidence import g3b2_prompts as GP
from evidence import g3b2_server as GS
from evidence import g3b3_common as C
from evidence import g3b3_freeze as FZ

REASON = 'g3b3 livegate decision'


# ---------------------------------------------------------------------------
# HTTP helpers (real local server, no vendor)
# ---------------------------------------------------------------------------

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


def _start_server(tmp, *, restage_cache=None):
    httpd = GS.build_g3b2_server(tmp, port=0, restage_cache=restage_cache)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{httpd.server_address[1]}'


def _open_session(base, fx, iid, aid, tier, policy, tag):
    st, body = _http_json(base, 'POST', '/sessions', {
        'instance_id': iid, 'base_commit': fx['base_commit'],
        'patch_sha256': fx['patch_sha256'], 'cell': tag,
        'served_artifact_id': aid, 'evidence_tier': tier,
        'policy': policy, 'claim': fx['claim'], 'symptom': fx['symptom']})
    if st != 201:
        return None, f'open session st={st} {body[:120]}'
    return json.loads(body)['session_id'], None


# ---------------------------------------------------------------------------
# Frozen-store isolation snapshot
# ---------------------------------------------------------------------------

def _snapshot_store():
    out = {}
    for p in C.G3A_STORE.rglob('*'):
        if p.is_file():
            out[str(p.relative_to(C.G3A_STORE))] = C.sha256_file(p)
    return out


# ---------------------------------------------------------------------------
# Main 10-issue x 5-condition real-HTTP matrix
# ---------------------------------------------------------------------------

def http_matrix(items_by):
    tmp = tempfile.mkdtemp(prefix='g3b3_livegate_store_')
    shutil.copytree(str(C.G3A_STORE), tmp, dirs_exist_ok=True)
    before = _snapshot_store()
    httpd, base = _start_server(tmp)
    errors, cells = [], []
    proto_seen = getattr(httpd, 'g3b2_protocol_version', None)
    try:
        iids = sorted({k[0] for k in items_by})
        for iid in iids:
            any_it = items_by[(iid, C.CONDITIONS[0])]
            fx = {'base_commit': any_it['base_commit'],
                  'patch_sha256': any_it['patch_sha256'],
                  'served_artifact_id': any_it['served_artifact_id'],
                  'claim': any_it['claim'], 'symptom': any_it['symptom']}
            aid = fx['served_artifact_id']
            for cond in C.CONDITIONS:
                it = items_by[(iid, cond)]
                active, tier, policy = ternary_condition_tier_policy(cond)
                tag = f'g3b3-livegate:{iid}:{cond}'
                checks = []

                def ok(name, cond_ok, detail=''):
                    checks.append({'check': name, 'pass': bool(cond_ok),
                                   'detail': str(detail)[:240]})
                    if not cond_ok:
                        errors.append(f'{tag}: {name} {detail}')

                # ---- static regimes: assert the exact served text block ----
                if not active:
                    block = GP.g3b2_evidence_block(
                        it['artifact_record'], tier=tier,
                        symptom=it.get('symptom'))
                    if tier == 'A':
                        ok('T2A_institutional_warranty',
                           'institutionally attested for THIS patch/commit'
                           in block)
                        ok('T2A_outcomes_rendered',
                           'FAIL_TO_PASS passed' in block
                           and 'PASS_TO_PASS passed' in block)
                        ok('T2A_no_stale_linkage_phrase',
                           'linkage not yet verified' not in block)
                        ok('T2A_no_verdict_leak',
                           'the verdict is ACCEPT' not in block
                           and 'the verdict is REJECT' not in block)
                        # SymPy-17318 regression: a REJECT-oracle issue keeps
                        # its decisive visible failure under the repair.
                        if iid.endswith('sympy-17318'):
                            ok('17318_f2p_0_of_1_visible',
                               'FAIL_TO_PASS passed: 0/1' in block,
                               'visible executed failure must survive repair')
                            ok('17318_failing_id_visible',
                               'test_issue_12420' in block,
                               'failing acceptance id must be rendered')
                            ok('17318_p2p_10_of_10',
                               'PASS_TO_PASS passed: 10/10' in block)
                    else:  # T2D tier D diagnostic block
                        ok('T2D_no_outcome_leak',
                           'FAIL_TO_PASS passed' not in block
                           and 'failing acceptance test ids' not in block)
                        ok('T2D_symptom_rendered',
                           'issue symptom present before patch' in block
                           or 'symptom' in block.lower())
                    cells.append({'cell': tag, 'tier': tier,
                                  'active_tools': False, 'checks': checks})
                    continue

                sid, err = _open_session(base, fx, iid, aid, tier, policy,
                                         tag)
                ok('session_open_201', sid is not None, err or '')
                if sid is None:
                    cells.append({'cell': tag, 'tier': tier,
                                  'active_tools': True, 'checks': checks})
                    continue

                # linkage
                st, b = _http_json(base, 'GET', f'/sessions/{sid}/verify')
                link = json.loads(b) if st == 200 else {}
                ok('linkage_200_linked', st == 200
                   and link.get('linked') is True, f'st={st}')

                # repaired three-state freshness — the core G3-B.2 fix
                st, b = _http_json(base, 'GET',
                                   f'/sessions/{sid}/freshness')
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
                   fr.get('authoritative_tree_source'))
                # THE structural-false-negative regression must be absent.
                ok('no_structural_fresh_false',
                   not (fr.get('record_run_tree_present') is False
                        and fr.get('fresh') is False),
                   'absent record.run_tree must never be served as false')
                ok('freshness_record_tree_absent_expected',
                   fr.get('record_run_tree_present') is False,
                   f"present={fr.get('record_run_tree_present')}")

                # coverage: complete, but never leaks acceptance outcomes
                st, b = _http_json(base, 'GET',
                                   f'/sessions/{sid}/coverage')
                cov = json.loads(b) if st == 200 else {}
                ok('coverage_200_complete', st == 200
                   and cov.get('complete') is True, f'st={st}')
                ok('coverage_no_outcomes',
                   'f2p_outcomes' not in b
                   and '"PASSED"' not in b and '"FAILED"' not in b)

                # symptom diagnostic log available at every active condition
                st, _, _ = _http_raw(base, f'/sessions/{sid}/log/symptom')
                ok('symptom_log_200', st == 200, f'st={st}')

                # --- acceptance-log + consistency gating by policy ---------
                if policy == 'strict':
                    st, _, _ = _http_raw(base, f'/sessions/{sid}/log/f2p')
                    ok('strict_f2p_403', st == 403, f'st={st}')
                    # a reason must NOT bypass the strict wall
                    import urllib.parse
                    st, _, _ = _http_raw(
                        base, f'/sessions/{sid}/log/f2p?reason='
                        + urllib.parse.quote(REASON))
                    ok('strict_f2p_reason_still_403', st == 403,
                       f'st={st}')
                    st, b = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    cs = json.loads(b) if st == 200 else {}
                    ok('strict_consistency_200_symptom_only',
                       st == 200
                       and 'failed_acceptance_checks' not in b
                       and 'executed_checks' not in b, f'st={st}')
                    # even with a reason, strict never reveals acceptance
                    st, b = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency',
                                       {'reason': REASON})
                    ok('strict_consistency_reason_no_acceptance_leak',
                       st == 200 and 'escalated' not in
                       (json.loads(b) if st == 200 else {}), f'st={st}')
                elif policy == 'escalate':
                    st, _, _ = _http_raw(base, f'/sessions/{sid}/log/f2p')
                    ok('escalate_f2p_no_reason_400', st == 400, f'st={st}')
                    st, _, _ = _http_raw(
                        base, f'/sessions/{sid}/log/f2p?reason=')
                    ok('escalate_f2p_empty_reason_400', st == 400,
                       f'st={st}')
                    st, _, _ = _http_raw(
                        base, f'/sessions/{sid}/log/f2p?reason=%20%20')
                    ok('escalate_f2p_blank_reason_400', st == 400,
                       f'st={st}')
                    import urllib.parse
                    q = urllib.parse.quote(REASON)
                    st, b2, hdr = _http_raw(
                        base, f'/sessions/{sid}/log/f2p?reason={q}')
                    ok('escalate_f2p_with_reason_200_banner',
                       st == 200
                       and hdr.get('X-Evidence-Tier-Escalation') == '1'
                       and b2.startswith('# TIER ESCALATION'),
                       f'st={st} flag='
                       f'{hdr.get("X-Evidence-Tier-Escalation")}')
                    st, _ = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    ok('escalate_consistency_no_reason_400', st == 400,
                       f'st={st}')
                    st, b = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency',
                                       {'reason': ''})
                    ok('escalate_consistency_empty_reason_400', st == 400,
                       f'st={st}')
                    st, b2 = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency',
                        {'reason': REASON})
                    ok('escalate_consistency_with_reason_200',
                       st == 200
                       and json.loads(b2).get('escalated') is True,
                       f'st={st}')
                else:  # T3A-T full access
                    st, _, hdr = _http_raw(base,
                                           f'/sessions/{sid}/log/f2p')
                    ok('t3a_f2p_200_no_escalation_flag',
                       st == 200
                       and hdr.get('X-Evidence-Tier-Escalation') == '0',
                       f'st={st} flag='
                       f'{hdr.get("X-Evidence-Tier-Escalation")}')
                    st, b = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    cs = json.loads(b) if st == 200 else {}
                    ok('t3a_consistency_200_acceptance_based',
                       st == 200 and 'failed_acceptance_checks' in cs,
                       f'st={st}')

                cells.append({'cell': tag, 'tier': tier, 'policy': policy,
                              'active_tools': True,
                              'freshness': {
                                  'state': fr.get('fresh_state'),
                                  'fresh': fr.get('fresh'),
                                  'run_tree_match': fr.get('run_tree_match'),
                                  'record_run_tree_present':
                                      fr.get('record_run_tree_present'),
                                  'authoritative_tree_source':
                                      fr.get('authoritative_tree_source')},
                              'checks': checks})
    finally:
        httpd.shutdown()
        after = _snapshot_store()
        shutil.rmtree(tmp, ignore_errors=True)
    isolation_ok = before == after
    if not isolation_ok:
        errors.append('FROZEN G3-A STORE MODIFIED BY THE LIVEGATE SERVER')
    return {
        'cells': cells, 'errors': errors,
        'server_protocol_version': proto_seen,
        'isolated_tempdir_store': True,
        'frozen_store_unchanged': isolation_ok,
        'frozen_store_n_files': len(before),
    }


# ---------------------------------------------------------------------------
# HTTP negative: a restage miss must be UNKNOWN, never a structural FALSE
# ---------------------------------------------------------------------------

def http_unknown_injection(items_by):
    """Start a second isolated server whose authoritative restage cache has
    NO entry for one issue. Its artifact records carry no run_tree field, so
    the repaired endpoint MUST answer fresh=null/UNKNOWN (the old endpoint
    answered fresh=false). $0, local only."""
    errors, checks = [], []
    tmp = tempfile.mkdtemp(prefix='g3b3_livegate_unknown_')
    shutil.copytree(str(C.G3A_STORE), tmp, dirs_exist_ok=True)
    full_cache = GF.load_restage_cache()
    iids = sorted({k[0] for k in items_by})
    target = iids[0]
    miss_cache = {k: v for k, v in full_cache.items() if k != target}
    httpd, base = _start_server(tmp, restage_cache=miss_cache)

    def ok(name, cond_ok, detail=''):
        checks.append({'check': name, 'pass': bool(cond_ok),
                       'detail': str(detail)[:240]})
        if not cond_ok:
            errors.append(f'unknown-injection: {name} {detail}')

    try:
        it = items_by[(target, 'T3A-T')]
        fx = {'base_commit': it['base_commit'],
              'patch_sha256': it['patch_sha256'],
              'served_artifact_id': it['served_artifact_id'],
              'claim': it['claim'], 'symptom': it['symptom']}
        sid, err = _open_session(base, fx, target, it['served_artifact_id'],
                                 'A', None, f'g3b3-livegate-unk:{target}')
        ok('session_open_201', sid is not None, err or '')
        if sid is not None:
            st, b = _http_json(base, 'GET',
                               f'/sessions/{sid}/freshness')
            fr = json.loads(b) if st == 200 else {}
            ok('restage_miss_200', st == 200, f'st={st}')
            ok('restage_miss_state_UNKNOWN',
               fr.get('fresh_state') == 'UNKNOWN',
               f"state={fr.get('fresh_state')}")
            ok('restage_miss_fresh_null', fr.get('fresh') is None,
               f"fresh={fr.get('fresh')}")
            ok('restage_miss_not_false', fr.get('fresh') is not False,
               'absence must never be served as false')
            ok('restage_miss_reason',
               fr.get('status_reason') ==
               'schema_error_record_run_tree_missing',
               fr.get('status_reason'))
            ok('restage_miss_record_tree_absent',
               fr.get('record_run_tree_present') is False,
               f"present={fr.get('record_run_tree_present')}")
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return {'target_instance_id': target, 'checks': checks,
            'errors': errors}


# ---------------------------------------------------------------------------
# Pure-function negative matrix for the three-state adjudicator
# ---------------------------------------------------------------------------

def _base_triple(items_by):
    """A real authentic (rec, att, sess, restaged_tree) triple from one issue.
    Only used as in-memory inputs to the pure adjudicator; nothing is written.
    """
    from evidence.schemas import make_artifact_id
    from evidence.store import ArtifactStore
    iid = sorted({k[0] for k in items_by})[0]
    it = items_by[(iid, 'T3A-T')]
    store = ArtifactStore(str(C.G3A_STORE),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    aid = make_artifact_id(iid, it['patch_sha256'])
    rec, authentic = store.get(aid)
    att = store.get_attestation(iid, it['patch_sha256'])
    sess = {'instance_id': iid, 'base_commit': it['base_commit'],
            'patch_sha256': it['patch_sha256']}
    restaged = (GF.load_restage_cache().get(iid) or {}) \
        .get('recomputed_run_tree')
    return rec, authentic, att, sess, restaged


def freshness_pure_negatives(items_by):
    rec, authentic, att, sess, restaged = _base_triple(items_by)
    errors, checks = [], []

    def ok(name, cond_ok, detail=''):
        checks.append({'check': name, 'pass': bool(cond_ok),
                       'detail': str(detail)[:240]})
        if not cond_ok:
            errors.append(f'freshness-pure: {name} {detail}')

    expected = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=att, sess=sess,
        restaged_tree=restaged, patch_match=True)
    ok('baseline_TRUE_restage',
       expected['fresh_state'] == 'TRUE'
       and expected['fresh'] is True
       and expected['authoritative_tree_source'] ==
       'independent_git_restage_write_tree',
       f"state={expected['fresh_state']}")

    # missing record.run_tree + NO restage -> UNKNOWN, never FALSE (the bug)
    rec_no_tree = {k: v for k, v in rec.items() if k != 'run_tree'}
    v = GF.adjudicate_freshness(
        rec=rec_no_tree, authentic=authentic, att=att, sess=sess,
        restaged_tree=None, patch_match=True)
    ok('missing_field_UNKNOWN_not_false',
       v['fresh_state'] == 'UNKNOWN' and v['fresh'] is None
       and v['run_tree_match'] is None
       and v['status_reason'] ==
       'schema_error_record_run_tree_missing',
       f"state={v['fresh_state']} fresh={v['fresh']}")

    # wrong-typed run_tree field -> UNKNOWN (wrong-type sub-state)
    v = GF.adjudicate_freshness(
        rec=rec_no_tree, authentic=authentic, att=att, sess=sess,
        restaged_tree=None, record_tree_override=12345, patch_match=True)
    ok('wrong_type_field_UNKNOWN',
       v['fresh_state'] == 'UNKNOWN' and v['fresh'] is None
       and v['status_reason'] ==
       'schema_error_record_run_tree_wrong_type',
       f"state={v['fresh_state']}")

    # present, comparable record tree genuinely differs -> FALSE
    v = GF.adjudicate_freshness(
        rec=rec_no_tree, authentic=authentic, att=att, sess=sess,
        restaged_tree=None, record_tree_override='deadbeef' * 5,
        patch_match=True)
    ok('present_mismatched_tree_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['run_tree_match'] is False
       and v['status_reason'] == 'tree_mismatch',
       f"state={v['fresh_state']}")

    # present matching record tree -> TRUE via record field
    v = GF.adjudicate_freshness(
        rec=rec_no_tree, authentic=authentic, att=att, sess=sess,
        restaged_tree=None,
        record_tree_override=att.get('expected_run_tree'),
        patch_match=True)
    ok('present_matching_tree_TRUE',
       v['fresh_state'] == 'TRUE' and v['fresh'] is True
       and v['authoritative_tree_source'] == 'record_run_tree_field',
       f"state={v['fresh_state']}")

    # independent restage tree genuinely differs -> FALSE
    v = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=att, sess=sess,
        restaged_tree='cafef00d' * 5, patch_match=True)
    ok('restage_mismatch_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['status_reason'] == 'tree_mismatch',
       f"state={v['fresh_state']}")

    # bad artifact signature -> genuine FALSE
    v = GF.adjudicate_freshness(
        rec=rec, authentic=False, att=att, sess=sess,
        restaged_tree=restaged, patch_match=True)
    ok('bad_artifact_signature_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['status_reason'] == 'artifact_signature_invalid',
       f"state={v['fresh_state']}")

    # bad attestation signature -> genuine FALSE
    att_bad = dict(att)
    att_bad['_attestation_authentic'] = False
    v = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=att_bad, sess=sess,
        restaged_tree=restaged, patch_match=True)
    ok('bad_attestation_signature_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['status_reason'] == 'attestation_signature_invalid',
       f"state={v['fresh_state']}")

    # missing attestation -> UNKNOWN (cannot adjudicate)
    v = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=None, sess=sess,
        restaged_tree=restaged, patch_match=True)
    ok('missing_attestation_UNKNOWN',
       v['fresh_state'] == 'UNKNOWN' and v['fresh'] is None
       and v['status_reason'] == 'attestation_missing',
       f"state={v['fresh_state']}")

    # base commit mismatch -> genuine FALSE
    sess_bad = dict(sess)
    sess_bad['base_commit'] = '0' * 40
    v = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=att, sess=sess_bad,
        restaged_tree=restaged, patch_match=True)
    ok('base_commit_mismatch_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['status_reason'] == 'base_commit_mismatch',
       f"state={v['fresh_state']}")

    # explicit patch mismatch -> genuine FALSE
    v = GF.adjudicate_freshness(
        rec=rec, authentic=authentic, att=att, sess=sess,
        restaged_tree=restaged, patch_match=False)
    ok('patch_mismatch_FALSE',
       v['fresh_state'] == 'FALSE' and v['fresh'] is False
       and v['status_reason'] == 'patch_mismatch',
       f"state={v['fresh_state']}")

    return {'checks': checks, 'errors': errors,
            'baseline_instance_id': sess['instance_id']}


# ---------------------------------------------------------------------------

def main():
    items = FZ.build_items()
    items_by = {(it['instance_id'], it['condition']): it for it in items}

    matrix = http_matrix(items_by)
    unknown = http_unknown_injection(items_by)
    pure = freshness_pure_negatives(items_by)

    n_checks = sum(len(c['checks']) for c in matrix['cells']) \
        + len(unknown['checks']) + len(pure['checks'])
    n_pass = sum(1 for c in matrix['cells']
                 for k in c['checks'] if k['pass']) \
        + sum(1 for k in unknown['checks'] if k['pass']) \
        + sum(1 for k in pure['checks'] if k['pass'])
    errors = matrix['errors'] + unknown['errors'] + pure['errors']

    # Aggregate freshness TRUE across active cells (30 = 10 x 3 conditions).
    active_fresh = [c for c in matrix['cells'] if c.get('active_tools')]
    n_active = len(active_fresh)
    n_fresh_true = sum((c.get('freshness') or {}).get('state') == 'TRUE'
                       for c in active_fresh)
    n_structural_false = sum(
        (c.get('freshness') or {}).get('state') == 'FALSE'
        and (c.get('freshness') or {}).get('record_run_tree_present') is False
        for c in active_fresh)

    report = {
        'document': 'Gate 3-B.3 precondition 3: REAL local g3b2 HTTP '
                    'end-to-end live integration gate (zero API, zero '
                    'vendor traffic).',
        'gate': C.GATE,
        'runner_version': C.G3B3_RUNNER_VERSION,
        'executed_protocol_version': C.RUN_PROTOCOL_VERSION,
        'executed_prompt_version': C.RUN_PROMPT_VERSION,
        'server_factory': 'evidence.g3b2_server.build_g3b2_server',
        'n_issues': 10, 'n_conditions': len(C.CONDITIONS),
        'n_cells': len(matrix['cells']),
        'n_active_cells': n_active,
        'n_active_freshness_TRUE': n_fresh_true,
        'n_structural_fresh_false': n_structural_false,
        'n_checks': n_checks, 'n_checks_pass': n_pass,
        'n_errors': len(errors), 'errors': errors,
        'server_protocol_version': matrix['server_protocol_version'],
        'frozen_store_unchanged': matrix['frozen_store_unchanged'],
        'cells': matrix['cells'],
        'negative_restage_miss_injection': unknown,
        'negative_freshness_pure': pure,
        'gold_authority': C.GOLD_AUTHORITY,
        'approved_scope': C.APPROVED_SCOPE,
    }
    C.OUT_LIVEGATE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_LIVEGATE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    print(f"livegate: cells={report['n_cells']} "
          f"active={n_active} fresh_TRUE={n_fresh_true} "
          f"structural_false={n_structural_false}")
    print(f"checks={n_checks} pass={n_pass} errors={len(errors)} "
          f"frozen_store_unchanged={matrix['frozen_store_unchanged']}")
    print('server protocol:', matrix['server_protocol_version'])
    print('report ->', C.OUT_LIVEGATE)
    if errors:
        for e in errors[:20]:
            print('FAIL', e)
        raise SystemExit('G3-B.3 LIVE INTEGRATION GATE FAILED')
    if n_fresh_true != n_active or n_structural_false != 0:
        raise SystemExit(
            'G3-B.3 livegate freshness invariants broken')
    if matrix['server_protocol_version'] != C.RUN_PROTOCOL_VERSION:
        raise SystemExit('G3-B.3 livegate served wrong protocol version')


if __name__ == '__main__':
    main()
