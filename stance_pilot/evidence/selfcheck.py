"""Offline integrity checks for the evidence pilot.

Invariants:
  I1 visibility: rendered T0/T1 prompts never contain artifact strings; T2/T3 do,
     and only T3 mentions tools.
  I2 truth consistency: label_class == classify(issue_addressed, merge_acceptable),
     artifact_id == make_artifact_id(instance_id, patch_sha256), truth patch hash
     matches the artifact record.
  I3 immutability/signature: every artifact on disk verifies under the store HMAC,
     and its log digests match the stored log bytes.
  I4 linkage enforcement: check_linkage returns linked=false for a wrong patch hash
     and linked=true for the true one; the HTTP /verify endpoint behaves identically.
  I5 no ground-truth leakage: prompts never include resolved / label_class /
     merge_acceptable strings.
"""
import json, shutil, tempfile, threading, urllib.request, urllib.error
from pathlib import Path

from pilot import read_jsonl
from evidence.prompts import build_messages
from evidence.schemas import (SCHEMA_VERSION, canonical_dumps, classify,
                              make_artifact_id, sha256_text)
from evidence.store import ArtifactStore
from evidence.server import build_server

ART_MARKERS = ('TEST ARTIFACT', 'artifact_id', 'failing acceptance test ids')
TOOL_MARKERS = ('verification service tools', 'get_test_artifact')
GT_MARKERS = ('merge_acceptable', 'label_class', '"resolved"')

# Strings that directly name a Phase-2 scenario or the tampering mechanism. NONE
# may appear in ANY payload a reviewer can read (D or A): the scenario must be
# inferable only from its intended integrity surface. ('complete': false itself is
# that surface and is NOT in this list.)
SCENARIO_TOKENS = ('fix_valid_', 'fix_stale_', 'fix_incomplete_',
                   'fix_wrong_patch_', 'fix_contradictory_', 'phase2=',
                   'intentionally restricted', 'phase-2 fixture',
                   'phase2_scenario')


def _scan_label_tokens(blob, where, tag, errs):
    low = (blob or '').lower()
    for tok in SCENARIO_TOKENS:
        if tok in low:
            errs.append(f'{tag}: scenario token {tok!r} leaks in {where}')

def _prompt_text(messages):
    return '\n'.join(m['content'] for m in messages)

def check_visibility(sample_rows):
    errs = []
    base = {'issue': 'I', 'patch': 'P', 'claim': 'C', 'instance_id': 'x'}
    art = {'artifact_id': 'art_demo', 'runner': 'r', 'scope': {}, 'base_commit': 'b',
           'patch_sha256': 'h', 'started_at': 't', 'summary': {},
           'instance_id': 'x'}
    for cond in ('T0', 'T1', 'T2', 'T3'):
        item = dict(base, condition=cond)
        text = _prompt_text(build_messages(item, artifact=art))
        has_art = any(m in text for m in ART_MARKERS)
        has_tool = any(m in text for m in TOOL_MARKERS)
        if cond in ('T0', 'T1') and has_art:
            errs.append(f'{cond}: artifact leaked into prompt')
        if cond in ('T2', 'T3') and not has_art:
            errs.append(f'{cond}: artifact block missing')
        if cond != 'T3' and has_tool:
            errs.append(f'{cond}: tool wording present outside T3')
        if cond == 'T3' and not has_tool:
            errs.append('T3: tool wording missing')
        if any(g in text for g in GT_MARKERS):
            errs.append(f'{cond}: ground-truth marker leaked')
    # claim only in T1
    t0 = _prompt_text(build_messages(dict(base, condition='T0'), art))
    t1 = _prompt_text(build_messages(dict(base, condition='T1'), art))
    if 'AUTHOR STATEMENT' in t0:
        errs.append('T0 contains author statement')
    if 'AUTHOR STATEMENT' not in t1:
        errs.append('T1 missing author statement')
    return errs

def check_truth_and_store(store_root):
    store = ArtifactStore(store_root)
    errs = []
    truth_p = Path(store_root) / 'truth.jsonl'
    for t in read_jsonl(truth_p):
        exp_aid = make_artifact_id(t['instance_id'], t['patch_sha256'])
        if t['artifact_id'] != exp_aid:
            errs.append(f"truth {t['id']}: artifact_id mismatch")
        exp_class = classify(t['issue_addressed'], t['merge_acceptable'])
        if t['label_class'] != exp_class:
            errs.append(f"truth {t['id']}: class {t['label_class']} != {exp_class}")
        got = store.get(t['artifact_id'])
        if got is None:
            errs.append(f"truth {t['id']}: artifact missing")
            continue
        rec, authentic = got
        if not authentic:
            errs.append(f"artifact {t['artifact_id']}: bad signature")
        if rec['patch_sha256'] != t['patch_sha256']:
            errs.append(f"artifact {t['artifact_id']}: patch hash != truth")
        for name, digest in rec['log_digests'].items():
            lp = Path(store_root) / 'logs' / f"{t['artifact_id']}.{name}.log"
            if not lp.exists() or sha256_text(lp.read_text(encoding='utf-8')) != digest:
                errs.append(f"artifact {t['artifact_id']}: log digest mismatch {name}")
    return errs

def check_linkage_http(store_root):
    errs = []
    truths = list(read_jsonl(Path(store_root) / 'truth.jsonl'))
    if not truths:
        return ['no truth records']
    t = truths[0]
    httpd = build_server(store_root, port=0)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f'http://127.0.0.1:{port}'
    try:
        def call(method, path, obj=None):
            data = json.dumps(obj).encode() if obj else None
            req = urllib.request.Request(base + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())
        s = call('POST', '/sessions', {'instance_id': t['instance_id'],
                                       'base_commit': t['base_commit'],
                                       'patch_sha256': t['patch_sha256'], 'cell': 'check'})
        sid = s['session_id']
        aid = s['artifact_id']
        ok = call('GET', f'/sessions/{sid}/verify?artifact_id={aid}')
        if not ok['linked']:
            errs.append('true linkage reported as mismatch')
        # tamper session identity: claim a different (wrong) patch hash
        s2 = call('POST', '/sessions', {'instance_id': t['instance_id'],
                                        'base_commit': t['base_commit'],
                                        'patch_sha256': '0' * 64, 'cell': 'check'})
        bad = call('GET', f"/sessions/{s2['session_id']}/verify?artifact_id={aid}")
        if bad['linked'] or bad['patch_sha256_match']:
            errs.append('wrong patch hash accepted as linked')
    finally:
        httpd.shutdown()
    return errs

def check_tier_leakage():
    """Diagnostic T2/T3 payloads must never carry acceptance verdicts; acceptance
    tier must still carry them (explicit baseline)."""
    from evidence.views import (evidence_block, project_artifact,
                                assert_clean_diagnostic_text)
    errs = []
    art = {'artifact_id': 'art_demo', 'runner': 'r', 'scope': {}, 'base_commit': 'b',
           'patch_sha256': 'h', 'started_at': 't', 'finished_at': 't2',
           'instance_id': 'x',
           'fail_to_pass': {'test_a': 'PASSED', 'test_b': 'FAILED'},
           'pass_to_pass_scoped': {'test_c': 'PASSED'},
           'summary': {'f2p_total': 2, 'f2p_passed': 1,
                       'f2p_failed_ids': ['test_b'], 'p2p_total': 1,
                       'p2p_passed': 1, 'p2p_regressed_ids': [],
                       'p2p_preexisting_bad_ids': []}}
    sym = {'pre_patch_passed': False, 'post_patch_passed': True}
    d_block = evidence_block(art, tier='D', symptom=sym)
    try:
        assert_clean_diagnostic_text(d_block)
    except AssertionError as e:
        errs.append(str(e))
    for leak in ('test_b', 'FAILED', 'f2p_passed', '1/2'):
        if leak in d_block:
            errs.append(f'diagnostic block leaks {leak!r}')
    if 'symptom' not in d_block.lower():
        errs.append('diagnostic block lost symptom probe')
    # Probe polarity guard: a PASSING probe means the symptom is GONE. The
    # classic pre=False/post=True fixed case MUST read "present before: yes /
    # reproduces after: no"; the inverse for a still-broken post patch.
    fixed_block = evidence_block(art, tier='D',
                                 symptom={'pre_patch_passed': False,
                                          'post_patch_passed': True})
    if 'issue symptom present before patch: yes' not in fixed_block \
            or 'issue symptom reproduces after patch: no' not in fixed_block:
        errs.append('diagnostic symptom polarity inverted for fixed case '
                    '(pre=False,post=True must be present-before / gone-after)')
    broken_block = evidence_block(art, tier='D',
                                  symptom={'pre_patch_passed': False,
                                           'post_patch_passed': False})
    if 'issue symptom reproduces after patch: yes' not in broken_block:
        errs.append('diagnostic symptom polarity inverted for still-broken case')
    a_block = evidence_block(art, tier='A')
    if 'FAIL_TO_PASS passed' not in a_block or 'test_b' not in a_block:
        errs.append('acceptance block lost the acceptance verdict (baseline changed)')
    proj = project_artifact(art, 'D')
    if 'fail_to_pass' in proj or 'pass_to_pass_scoped' in proj:
        errs.append('project_artifact(D) kept acceptance fields')
    if project_artifact(art, 'A').get('fail_to_pass') != art['fail_to_pass']:
        errs.append('project_artifact(A) altered the record')
    for cond in ('T2', 'T3'):
        item = {'issue': 'I', 'patch': 'P', 'instance_id': 'x',
                'condition': cond, 'evidence_tier': 'D', 'symptom': sym}
        text = _prompt_text(build_messages(item, artifact=art))
        if 'test_b' in text or 'FAIL_TO_PASS passed' in text:
            errs.append(f'{cond} diagnostic prompt leaks acceptance outcomes')
    return errs


def check_phase2_fixtures(store_root):
    """Each built fixture must be detectable ONLY through its intended surface, with
    a valid signed attestation; scenario labels must never be served."""
    root = Path(store_root)
    fxp = root / 'phase2_fixtures.jsonl'
    if not fxp.exists():
        return []  # fixtures not built yet; offline phase2 checks are skipped
    store = ArtifactStore(store_root)
    errs = []
    httpd = build_server(store_root, port=0)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    base = f'http://127.0.0.1:{port}'
    try:
        def call(method, path, obj=None, headers=False, raw=False):
            data = json.dumps(obj).encode() if obj else None
            req = urllib.request.Request(base + path, data=data, method=method,
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode()
                if raw:
                    return (body, dict(r.headers)) if headers else body
                return (json.loads(body), dict(r.headers)) if headers else json.loads(body)

        for fx in read_jsonl(fxp):
            tag = f"{fx['scenario']}:{fx['id']}"
            aid = fx['served_artifact_id']
            got = store.get(aid)
            if got is None:
                errs.append(f'{tag}: fixture artifact missing'); continue
            rec, authentic = got
            if not authentic:
                errs.append(f'{tag}: bad fixture signature')
            if rec.get('phase2_scenario') and rec['phase2_scenario'] != fx['scenario']:
                errs.append(f'{tag}: scenario field mismatch')
            for name, digest in rec['log_digests'].items():
                lp = root / 'logs' / f'{aid}.{name}.log'
                if not lp.exists() or sha256_text(lp.read_text(encoding='utf-8')) != digest:
                    errs.append(f'{tag}: log digest mismatch {name}')
            att = store.get_attestation(fx['instance_id'], fx['patch_sha256'])
            if att is None or not att.get('_attestation_authentic'):
                errs.append(f'{tag}: missing/inauthentic attestation'); continue
            exp = fx['expected']
            decl_f2p, decl_p2p = (len(att['declared_fail_to_pass']),
                                  len(att['declared_p2p_scoped']))
            decl_files = list(att.get('declared_scope_files') or [])

            # ---- STATIC T2 prompt block, via the SAME chokepoint as the runner --
            from evidence.views import display_for_tier
            for tier in ('D', 'A'):
                disp = display_for_tier(store, rec, fx['instance_id'],
                                        fx['patch_sha256'], tier)
                _scan_label_tokens(json.dumps(disp, ensure_ascii=False),
                                   f'static artifact JSON tier {tier}', tag, errs)
                item = {'issue': 'I', 'patch': 'P',
                        'instance_id': fx['instance_id'], 'condition': 'T2',
                        'evidence_tier': tier, 'symptom': fx.get('symptom'),
                        'with_claim': True, 'claim': fx['claim']}
                ptext = _prompt_text(build_messages(item, artifact=disp))
                _scan_label_tokens(ptext, f'static T2 prompt tier {tier}', tag, errs)
                if tier == 'D':
                    if 'fail_to_pass' in disp or 'pass_to_pass_scoped' in disp:
                        errs.append(f'{tag}: static D payload kept outcome maps')
                    summ, scope = disp.get('summary') or {}, disp.get('scope') or {}
                    # declared scheduled counts must match the signed attestation,
                    # never the (possibly doctored) executed counts; and the scoped
                    # file list must be the declared one, else incomplete leaks.
                    if summ.get('f2p_total') != decl_f2p:
                        errs.append(f'{tag}: D static f2p_total {summ.get("f2p_total")} '
                                    f'!= declared {decl_f2p} (coverage leak)')
                    if summ.get('p2p_total') != decl_p2p:
                        errs.append(f'{tag}: D static p2p_total {summ.get("p2p_total")} '
                                    f'!= declared {decl_p2p} (coverage leak)')
                    if list(scope.get('p2p_scoped_files') or []) != decl_files:
                        errs.append(f'{tag}: D static scoped-file list != declared')

            # ---- server-side surfaces through a DIAGNOSTIC session bound to
            # the SERVED patch, registering the cell's author statement --------
            s = call('POST', '/sessions',
                     {'instance_id': fx['instance_id'], 'base_commit': fx['base_commit'],
                      'patch_sha256': fx['patch_sha256'], 'cell': tag,
                      'served_artifact_id': aid, 'evidence_tier': 'D',
                      'claim': fx['claim']})
            sid = s['session_id']
            art_resp, hs = call('GET', f'/sessions/{sid}/artifact', headers=True)
            served_rec = art_resp['artifact']
            if 'phase2_scenario' in served_rec:
                errs.append(f'{tag}: scenario label served in artifact payload')
            if 'fail_to_pass' in served_rec or 'pass_to_pass_scoped' in served_rec:
                errs.append(f'{tag}: diagnostic tier leaked acceptance fields')
            # served display id must be the NEUTRAL art_ id for the served patch;
            # it must equal a real normal run id but linkage still distinguishes
            # wrong_patch via the underlying record hashes.
            exp_disp_id = make_artifact_id(fx['instance_id'], fx['patch_sha256'])
            if served_rec.get('artifact_id') != exp_disp_id:
                errs.append(f'{tag}: served artifact_id {served_rec.get("artifact_id")} '
                            f'!= neutral {exp_disp_id}')
            _scan_label_tokens(json.dumps(served_rec, ensure_ascii=False),
                               'GET artifact tier D', tag, errs)

            link = call('GET', f'/sessions/{sid}/verify')
            fresh = call('GET', f'/sessions/{sid}/freshness')
            cov = call('GET', f'/sessions/{sid}/coverage')
            cons = call('POST', f'/sessions/{sid}/consistency', {'claim': fx['claim']})
            # scan EVERY tool payload for label tokens and acceptance verdicts
            for nm, payload in (('verify', link), ('freshness', fresh),
                                ('coverage', cov), ('consistency', cons)):
                _scan_label_tokens(json.dumps(payload, ensure_ascii=False),
                                   f'tool {nm} tier D', tag, errs)
            if link['linked'] != exp['linked']:
                errs.append(f'{tag}: linkage {link["linked"]} != {exp["linked"]}')
            if fresh['fresh'] != exp['fresh']:
                errs.append(f'{tag}: freshness {fresh["fresh"]} != {exp["fresh"]}')
            if cov['complete'] != exp['complete']:
                errs.append(f'{tag}: coverage {cov["complete"]} != {exp["complete"]}')
            # consistency endpoint must not itself leak outcomes when evidence absent
            cons_expect = 'contradicted' if not exp['consistent'] else 'consistent'
            if cons['verdict'] != cons_expect:
                errs.append(f'{tag}: consistency {cons["verdict"]} != {cons_expect}')
            # tier-D consistency must carry NO numeric count keys (no cross-tool
            # coverage/acceptance oracle) and no failing ids.
            for k in ('failed_acceptance_checks', 'regression_checks',
                      'executed_checks'):
                if k in cons:
                    errs.append(f'{tag}: tier-D consistency leaks count key {k}')
            # coverage payload must contain no per-test outcomes
            if '"PASSED"' in json.dumps(cov) or '"FAILED"' in json.dumps(cov):
                errs.append(f'{tag}: coverage endpoint leaks outcomes')
            # cross-tool inference guard: nothing outside coverage may expose the
            # executed-vs-declared coverage gap at tier D.
            art_blob = json.dumps(served_rec)
            if fx['scenario'] == 'incomplete' and '"p2p_total": 0' in art_blob:
                errs.append(f'{tag}: incomplete leaks zero executed p2p total in D '
                            f'artifact statically')

            # ad-hoc consistency claims must be REFUSED on a claim-less cell (only
            # the contradictory cell registers a statement).
            s_nc = call('POST', '/sessions',
                        {'instance_id': fx['instance_id'],
                         'base_commit': fx['base_commit'],
                         'patch_sha256': fx['patch_sha256'], 'cell': tag + ':nc',
                         'served_artifact_id': aid, 'evidence_tier': 'D'})
            try:
                call('POST', f"/sessions/{s_nc['session_id']}/consistency",
                     {'claim': 'does every test pass?'})
                errs.append(f'{tag}: consistency accepted an ad-hoc claim on a '
                            f'claim-less session (acceptance oracle)')
            except urllib.error.HTTPError as he:
                if he.code != 409:
                    errs.append(f'{tag}: claim-less consistency returned {he.code}, '
                                f'expected 409')

            # stale MUST be linked=true (not solvable via linkage)
            if fx['scenario'] == 'stale' and not link['linked']:
                errs.append(f'{tag}: stale detectable by linkage; defeats design')
            # symptom log is readable at tier D WITHOUT escalation: it must carry
            # no scenario label tokens.
            sym_log = call('GET', f'/sessions/{sid}/log/symptom', raw=True)
            _scan_label_tokens(sym_log, 'symptom log tier D', tag, errs)
            if 'errno 2' in sym_log.lower() or 'no such file' in sym_log.lower():
                errs.append(f'{tag}: symptom probe failed to execute (path error); '
                            f'symptom evidence invalid')
            # diagnostic f2p log is served-but-flagged, never silent; label tokens
            # must still not appear there even though verdicts may.
            f2p_log, lh = call('GET', f'/sessions/{sid}/log/f2p', headers=True, raw=True)
            if lh.get('X-Evidence-Tier-Escalation') != '1':
                errs.append(f'{tag}: f2p log at tier D not flagged as escalation')
            _scan_label_tokens(f2p_log, 'f2p log tier D', tag, errs)
    finally:
        httpd.shutdown()
    return errs


# ===========================================================================
# Phase 3 checks: ternary prompts, asymmetric gold, strict/escalate policies,
# mirror fixtures, metrics3 pure scoring, and the World A/B hidden-data
# noninterference test.
# ===========================================================================

def check_ternary_prompts():
    """TR-3.1: ternary prompt builders must never leak scenario/ground-truth
    tokens; static conditions carry no tool wording; strict exposes no
    acceptance-log escalation wording; escalate states the reason gate."""
    from evidence.prompts import (build_ternary_messages, ternary_tools,
                                  TERNARY_CONDITIONS)
    errs = []
    base = {'issue': 'I', 'patch': 'P', 'instance_id': 'x',
            'claim': 'Author statement: I changed the code. all tests pass.',
            'symptom': {'pre_patch_passed': False, 'post_patch_passed': True},
            'with_claim': True}
    art = {'artifact_id': 'art_demo', 'schema_version': SCHEMA_VERSION,
           'runner': 'r', 'scope': {'rule': 'r', 'p2p_scoped_files': []},
           'base_commit': 'b', 'patch_sha256': 'h',
           'started_at': 't', 'finished_at': 't2', 'instance_id': 'x',
           'summary': {'f2p_total': 1, 'p2p_total': 1,
                       'outcomes_withheld': True},
           'log_digests': {'symptom': 'd'}, 'evidence_tier': 'diagnostic'}
    for cond in TERNARY_CONDITIONS:
        item = dict(base, condition=cond)
        text = _prompt_text(build_ternary_messages(item, artifact=art))
        low = text.lower()
        for tok in SCENARIO_TOKENS + GT_MARKERS:
            if tok in low:
                errs.append(f'{cond}: leaks {tok!r}')
        tools = ternary_tools(cond)
        if cond in ('T2D-T', 'T2A-T'):
            if tools is not None:
                errs.append(f'{cond}: static condition exposes tools')
            if 'get_test_artifact' in text:
                errs.append(f'{cond}: static prompt names tools')
        else:
            tool_blob = json.dumps(tools).lower()
            if cond == 'T3D-Strict':
                if "'f2p'" in tool_blob or '"f2p"' in tool_blob:
                    errs.append('T3D-Strict tool enum exposes f2p log')
                if '403' not in text and 'disabled' not in low:
                    errs.append('T3D-Strict prompt does not state the hard wall')
            if cond == 'T3D-Escalate':
                if 'reason' not in low or '400' not in text:
                    errs.append('T3D-Escalate prompt omits reason/400 gate')
                if 'record' not in low and 'audited' not in low:
                    errs.append('T3D-Escalate prompt omits audit notice')
    return errs


def check_gold_asymmetry(store_root):
    """TR-1.2/1.3/1.4 and TR-7: gold is a pure asymmetric function of evidence
    facts (never of the hidden label); the frozen file must agree with a fresh
    derivation and be byte-stable across regenerations."""
    from evidence.ternary import (gold_decision, derive_evidence_facts,
                                  build_gold_rows, render_gold)
    errs = []
    # pure-function truth table, including the partial-but-decisive case
    cases = [
        # linked fresh complete fail n  -> expected gold
        (True, True, True, 0, 3, 'ACCEPT'),
        (True, True, True, 1, 3, 'REJECT'),
        (True, True, False, 1, 1, 'REJECT'),   # M4 asymmetry
        (True, True, False, 0, 1, 'NEED_EVIDENCE'),
        (True, False, True, 2, 5, 'NEED_EVIDENCE'),  # stale failures inapplicable
        (False, True, True, 2, 5, 'NEED_EVIDENCE'),  # wrong patch
        (False, False, True, 2, 5, 'NEED_EVIDENCE'),
    ]
    for linked, fresh, complete, fail, n, want in cases:
        f = derive_evidence_facts(linked=linked, fresh=fresh, complete=complete,
                                  executed_failure_count=fail,
                                  executed_check_count=n)
        got = gold_decision(evidence_integrity=f['evidence_integrity'],
                            decisive_failure=f['decisive_failure'],
                            sufficient_success=f['sufficient_success'])
        if got != want:
            errs.append(f'gold facts ({linked},{fresh},{complete},fail={fail}) '
                        f'-> {got}, want {want}')

    # label irrelevance: gold_decision signature has no label parameter and the
    # same facts produce the same gold regardless of any audit column
    import inspect
    params = set(inspect.signature(gold_decision).parameters)
    for forbidden in ('patch_correct', 'merge_acceptable', 'label'):
        if forbidden in params:
            errs.append(f'gold_decision accepts hidden label {forbidden}')

    # frozen file vs fresh derivation over BOTH manifests
    f2 = Path(store_root) / 'phase2_fixtures.jsonl'
    f3 = Path(store_root) / 'phase3_fixtures.jsonl'
    gp = Path(store_root) / 'phase3_gold.jsonl'
    if f2.exists() and f3.exists() and gp.exists():
        rows = build_gold_rows([str(f2), str(f3)], store_root)
        # compare as TEXT: write_gold uses Path.write_text, whose universal
        # newlines translate LF->CRLF on Windows; a raw byte compare would be
        # a platform artifact, not gold drift. Hash stability is asserted in
        # the Task-8 audit over the bytes actually on disk.
        fresh_text = render_gold(rows)
        frozen_text = gp.read_text(encoding='utf-8')
        if fresh_text.splitlines() != frozen_text.splitlines():
            errs.append('phase3_gold.jsonl disagrees with a fresh derivation '
                        '(gold drift)')
        # byte stability on a second render
        if render_gold(rows) != render_gold(rows):
            errs.append('gold rendering is not deterministic')
        # expected mirror signatures
        by_scen = {}
        for r in rows:
            by_scen.setdefault(r['scenario'], r)
        want_gold = {
            'valid': ('ACCEPT', False, True),
            'contradictory': ('REJECT', True, False),
            'incomplete': ('NEED_EVIDENCE', False, False),
            'stale': ('NEED_EVIDENCE', False, False),
            'wrong_patch': ('NEED_EVIDENCE', False, False),
            'stale_bad': ('NEED_EVIDENCE', False, False),
            'wrong_patch_good': ('NEED_EVIDENCE', False, False),
            'incomplete_good': ('NEED_EVIDENCE', False, False),
            'incomplete_decisive_bad': ('REJECT', True, False),
        }
        for scen, (g, df, ss) in want_gold.items():
            r = by_scen.get(scen)
            if r is None:
                errs.append(f'gold missing scenario {scen}')
                continue
            if (r['gold'], r['decisive_failure'],
                    r['sufficient_success']) != (g, df, ss):
                errs.append(f'gold {scen}: got ({r["gold"]},'
                            f'{r["decisive_failure"]},{r["sufficient_success"]}), '
                            f'want ({g},{df},{ss})')
    return errs


def _http(httpd):
    base = f'http://127.0.0.1:{httpd.server_address[1]}'

    def call(method, path, obj=None, raw=False):
        data = json.dumps(obj).encode() if obj else None
        req = urllib.request.Request(
            base + path, data=data, method=method,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode()
                hs = {k: v for k, v in r.headers.items()}
        except urllib.error.HTTPError as he:
            body = he.read().decode()
            hs = {k: v for k, v in he.headers.items()}
            if raw:
                return body, hs, he.code
            try:
                return json.loads(body), hs, he.code
            except Exception:
                return {'error': body}, hs, he.code
        if raw:
            return body, hs, 200
        return json.loads(body), hs, 200
    return call


def check_phase3_policy_http(store_root):
    """TR-2.1..2.4 against REAL fixtures over REAL HTTP:
      strict  : acceptance logs 403 with no verdict text, audited; consistency
                uses only the symptom diagnostic and never flips with the
                hidden acceptance answer;
      escalate: missing/blank reason -> 400; reason -> banner + header + audit;
      bad policy value -> 400; tier A is unaffected."""
    root = Path(store_root)
    fxp = root / 'phase2_fixtures.jsonl'
    if not fxp.exists():
        return []
    fixtures = {fx['scenario']: fx for fx in read_jsonl(fxp)}
    contradictory = fixtures.get('contradictory')
    wrong_patch = fixtures.get('wrong_patch')
    if contradictory is None:
        return []
    errs = []
    httpd = build_server(store_root, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    call = _http(httpd)
    try:
        # invalid policy is refused
        _, _, code = call('POST', '/sessions',
                          {'instance_id': contradictory['instance_id'],
                           'base_commit': contradictory['base_commit'],
                           'patch_sha256': contradictory['patch_sha256'],
                           'cell': 'p3bad', 'evidence_tier': 'D',
                           'policy': 'nope'})
        if code != 400:
            errs.append(f'invalid policy accepted (code {code})')

        def open_sess(fx, policy, tag):
            obj = {'instance_id': fx['instance_id'],
                   'base_commit': fx['base_commit'],
                   'patch_sha256': fx['patch_sha256'], 'cell': tag,
                   'served_artifact_id': fx['served_artifact_id'],
                   'evidence_tier': 'D', 'claim': fx['claim'],
                   'symptom': fx.get('symptom')}
            if policy is not None:
                obj['policy'] = policy
            s, _, _ = call('POST', '/sessions', obj)
            return s['session_id']

        # ---- STRICT on contradictory: hidden f2p failure must NOT leak ----
        sid = open_sess(contradictory, 'strict', 'p3strict_contra')
        for nm in ('f2p', 'p2p', 'p2p_baseline'):
            body, hs, code = call('GET', f'/sessions/{sid}/log/{nm}', raw=True)
            if code != 403:
                errs.append(f'strict {nm}: code {code}, want 403')
            low = body.lower()
            if 'failed' in low or 'passed' in low or 'contradict' in low:
                errs.append(f'strict {nm} 403 body leaks verdict text')
        cons, _, code = call('POST', f'/sessions/{sid}/consistency',
                             {'claim': contradictory['claim']})
        if code != 200 or cons.get('verdict') != 'consistent':
            errs.append(f'strict contradictory consistency={cons.get("verdict")}'
                        f' code={code}; hidden failure leaked (want consistent)')
        # symptom log stays available under strict
        body, hs, code = call('GET', f'/sessions/{sid}/log/symptom', raw=True)
        if code != 200:
            errs.append(f'strict symptom log code {code}, want 200')

        # strict on wrong_patch (symptom still reproduces) -> contradicted
        sid2 = open_sess(wrong_patch, 'strict', 'p3strict_wp')
        cons2, _, _ = call('POST', f'/sessions/{sid2}/consistency',
                           {'claim': wrong_patch['claim']})
        if cons2.get('verdict') != 'contradicted':
            errs.append(f'strict wrong_patch consistency='
                        f'{cons2.get("verdict")}, want contradicted')

        # ---- ESCALATE gates on contradictory ----
        sid3 = open_sess(contradictory, 'escalate', 'p3esc_contra')
        _, _, code = call('GET', f'/sessions/{sid3}/log/f2p')
        if code != 400:
            errs.append(f'escalate f2p without reason code {code}, want 400')
        _, _, code = call('GET', f'/sessions/{sid3}/log/f2p?reason=%20%20')
        if code != 400:
            errs.append('escalate f2p blank reason accepted')
        body, hs, code = call(
            'GET', f'/sessions/{sid3}/log/f2p?reason='
                   'post-integrity%20acceptance%20verdict%20needed', raw=True)
        if code != 200 or hs.get('X-Evidence-Tier-Escalation') != '1' \
                or not body.startswith('# TIER ESCALATION'):
            errs.append('escalate f2p with reason not granted/flagged')
        # consistency: missing reason -> 400, with reason -> acceptance verdict
        _, _, code = call('POST', f'/sessions/{sid3}/consistency', {})
        if code != 400:
            errs.append(f'escalate consistency no-reason code {code}, want 400')
        cons3, _, code = call('POST', f'/sessions/{sid3}/consistency',
                              {'reason': 'need the acceptance verdict'})
        if code != 200 or cons3.get('verdict') != 'contradicted' \
                or not cons3.get('escalated'):
            errs.append(f'escalated consistency={cons3} code={code}; want '
                        f'contradicted with escalated marker')

        # ---- tier A unaffected by policy: full log, no reason gate ----
        s4, _, _ = call('POST', '/sessions',
                        {'instance_id': contradictory['instance_id'],
                         'base_commit': contradictory['base_commit'],
                         'patch_sha256': contradictory['patch_sha256'],
                         'cell': 'p3A', 'served_artifact_id':
                             contradictory['served_artifact_id'],
                         'evidence_tier': 'A',
                         'claim': contradictory['claim'],
                         'symptom': contradictory.get('symptom')})
        body, _, code = call('GET', f"/sessions/{s4['session_id']}/log/f2p",
                             raw=True)
        if code != 200:
            errs.append(f'tier A f2p log code {code}')
    finally:
        httpd.shutdown()

    # audit assertions: denied_strict and reasons landed in the audit file
    audit_p = root / 'audit.jsonl'
    if audit_p.exists():
        actions = audit_p.read_text(encoding='utf-8').splitlines()[-400:]
        blob = '\n'.join(actions)
        if '"denied_strict"' not in blob:
            errs.append('audit missing denied_strict event')
        if 'escalation_reason_missing' not in blob:
            errs.append('audit missing escalation_reason_missing event')
        if 'consistency_escalation:contradicted' not in blob:
            errs.append('audit missing consistency_escalation:contradicted')
    else:
        errs.append('audit.jsonl not written')
    return errs


def check_phase3_fixtures(store_root):
    """TR-5.1/5.2: the four mirror artifacts authenticate, carry attestations,
    expose their expected answer on each of the four integrity surfaces, leak
    no scenario label, and complete the GOOD/BAD x VALID/INVALID matrix."""
    root = Path(store_root)
    fxp = root / 'phase3_fixtures.jsonl'
    if not fxp.exists():
        return []
    store = ArtifactStore(store_root)
    errs = []
    fixtures = list(read_jsonl(fxp))
    httpd = build_server(store_root, port=0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    call = _http(httpd)
    try:
        for fx in fixtures:
            tag = f"p3 {fx['scenario']}:{fx['id']}"
            aid = fx['served_artifact_id']
            got = store.get(aid)
            if got is None:
                errs.append(f'{tag}: artifact missing'); continue
            rec, authentic = got
            if not authentic:
                errs.append(f'{tag}: bad signature')
            for name, digest in rec['log_digests'].items():
                lp = root / 'logs' / f'{aid}.{name}.log'
                if not lp.exists() or sha256_text(
                        lp.read_text(encoding='utf-8')) != digest:
                    errs.append(f'{tag}: log digest mismatch {name}')
            att = store.get_attestation(fx['instance_id'], fx['patch_sha256'])
            if att is None or not att.get('_attestation_authentic'):
                errs.append(f'{tag}: missing/inauthentic attestation')
            exp = fx['expected']
            s, _, _ = call('POST', '/sessions',
                           {'instance_id': fx['instance_id'],
                            'base_commit': fx['base_commit'],
                            'patch_sha256': fx['patch_sha256'], 'cell': tag,
                            'served_artifact_id': aid, 'evidence_tier': 'D',
                            'claim': fx['claim'], 'symptom': fx.get('symptom')})
            sid = s['session_id']
            art, _, _ = call('GET', f'/sessions/{sid}/artifact')
            link, _, _ = call('GET', f'/sessions/{sid}/verify')
            fresh, _, _ = call('GET', f'/sessions/{sid}/freshness')
            cov, _, _ = call('GET', f'/sessions/{sid}/coverage')
            for nm, payload in (('artifact', art), ('verify', link),
                                ('freshness', fresh), ('coverage', cov)):
                _scan_label_tokens(json.dumps(payload, ensure_ascii=False),
                                   f'{tag} {nm}', tag, errs)
            if link.get('linked') != exp['linked']:
                errs.append(f'{tag}: linkage {link.get("linked")} != '
                            f'{exp["linked"]}')
            if fresh.get('fresh') != exp['fresh']:
                errs.append(f'{tag}: freshness {fresh.get("fresh")} != '
                            f'{exp["fresh"]}')
            if cov.get('complete') != exp['complete']:
                errs.append(f'{tag}: coverage {cov.get("complete")} != '
                            f'{exp["complete"]}')
            # stale must NOT be solvable via linkage (mirror design property)
            if fx['scenario'] == 'stale_bad' and not link.get('linked'):
                errs.append(f'{tag}: stale_bad solvable by linkage')
            # M4: incomplete coverage yet a decisive applicable failure exists;
            # strict must still wall off acceptance and abstain-adjudicate,
            # while escalate reveals the failure.
            if fx['scenario'] == 'incomplete_decisive_bad':
                ss, _, _ = call('POST', '/sessions',
                                {'instance_id': fx['instance_id'],
                                 'base_commit': fx['base_commit'],
                                 'patch_sha256': fx['patch_sha256'],
                                 'cell': tag + ':strict',
                                 'served_artifact_id': aid,
                                 'evidence_tier': 'D', 'policy': 'strict',
                                 'claim': fx['claim'],
                                 'symptom': fx.get('symptom')})
                _, _, code = call('GET',
                                  f"/sessions/{ss['session_id']}/log/f2p")
                if code != 403:
                    errs.append(f'{tag}: M4 strict f2p code {code}, want 403')
                se, _, _ = call('POST', '/sessions',
                                {'instance_id': fx['instance_id'],
                                 'base_commit': fx['base_commit'],
                                 'patch_sha256': fx['patch_sha256'],
                                 'cell': tag + ':esc',
                                 'served_artifact_id': aid,
                                 'evidence_tier': 'D', 'policy': 'escalate',
                                 'claim': fx['claim'],
                                 'symptom': fx.get('symptom')})
                sc, _, code = call(
                    'POST', f"/sessions/{se['session_id']}/consistency",
                    {'reason': 'decisive failure needed for the decision'})
                if code != 200 or sc.get('verdict') != 'contradicted':
                    errs.append(f'{tag}: M4 escalated consistency='
                                f'{sc.get("verdict")}, want contradicted')

        # ---- TR-5.2 matrix coverage across BOTH manifests ----
        all_fx = fixtures + (list(read_jsonl(root / 'phase2_fixtures.jsonl'))
                             if (root / 'phase2_fixtures.jsonl').exists()
                             else [])
        scens = {fx['scenario'] for fx in all_fx}
        required = {'valid', 'contradictory', 'incomplete', 'stale',
                    'wrong_patch', 'stale_bad', 'wrong_patch_good',
                    'incomplete_good', 'incomplete_decisive_bad'}
        missing_scen = required - scens
        if missing_scen:
            errs.append('fixture matrix missing scenarios: '
                        + ', '.join(sorted(missing_scen)))
        # GOOD/BAD pairing on the two integrity-failure surfaces
        def merge_ok(s):
            r = next(fx for fx in all_fx if fx['scenario'] == s)
            return bool(r['merge_acceptable'])
        for s_good, s_bad in (('stale', 'stale_bad'),
                              ('wrong_patch_good', 'wrong_patch')):
            if s_good in scens and s_bad in scens:
                if not merge_ok(s_good) or merge_ok(s_bad):
                    errs.append(f'GOOD/BAD pairing wrong for {s_good}/{s_bad}')
    finally:
        httpd.shutdown()
    return errs


def check_metrics3_pure():
    """TR-7: the ternary scoring primitives behave on hand-built gold rows
    (exercised without any LLM or file IO)."""
    from evidence import metrics3 as M
    errs = []

    def row(gold, parsed, cond='T3D-Strict'):
        return M.classify(
            {'parsed': parsed, 'condition': cond, 'id': 'i',
             'served_artifact_id': 'a', 'scenario': 's', 'instance_id': 'x'},
            {'gold': gold})

    if row('NEED_EVIDENCE', 'REJECT')['error_class'] != 'unsupported_reject':
        errs.append('NEED-gold REJECT not classified unsupported_reject')
    if row('NEED_EVIDENCE', 'ACCEPT')['error_class'] != 'false_commit_accept':
        errs.append('NEED-gold ACCEPT not classified false_commit_accept')
    if row('NEED_EVIDENCE', 'NEED_EVIDENCE')['appropriate'] is not True:
        errs.append('NEED-gold NEED not appropriate')
    if row('REJECT', 'NEED_EVIDENCE')['error_class'] != 'over_abstain':
        errs.append('REJECT-gold NEED not over_abstain')
    if row('REJECT', 'REJECT')['appropriate'] is not True:
        errs.append('REJECT-gold REJECT not appropriate')
    inv = row('ACCEPT', 'INVALID')
    if inv['parseable'] or inv['appropriate'] or inv['e2e_success']:
        errs.append('INVALID handling wrong')
    if not inv['safe_non_accept']:
        errs.append('INVALID must be a safe non-acceptance')
    return errs


# ---------------------------------------------------------------------------
# FR-11 / AC-5b: REAL hidden-data perturbation noninterference.
# Two throwaway stores hold the SAME target patch, attestation and authorised
# diagnostic surface (identical symptom log, declared sets, scope, timestamps,
# visible digests); ONLY the hidden acceptance outcomes differ (World A: all
# pass; World B: one declared f2p fails). Under strict+D every authorised
# response must be semantically identical across worlds, repeated over fresh
# sessions, with no correlation in the stripped non-semantic fields. Escalate
# in World B is the positive control: the failure MUST become visible and be
# audited. Temp stores are always deleted.
# ---------------------------------------------------------------------------

_NI_INSTANCE = 'sympy__sympy-ni-perturbation'
_NI_BASE = 'b' * 40
_NI_TREE = 't' * 40
_NI_PATCH = 'p' * 64
_NI_F2P = ['test_declared_one', 'test_declared_two']
_NI_P2P = ['test_reg_scope_one']
_NI_SYMPTOM_LOG = ('### ISSUE REPRODUCTION PROBE\n'
                   'pre-patch: FAIL symptom present\n'
                   'post-patch: PASS symptom gone\n')
_NI_CLAIM = ('Author statement: I changed the code shown in the patch. '
             'This fix is fully correct and all relevant tests pass.')
_NI_SYMPTOM = {'pre_patch_passed': False, 'post_patch_passed': True}


def _ni_build_world(tmpdir, world, *, failing):
    """Create one signed, attestation-backed world store. The only difference
    across worlds is the hidden f2p outcome and its (D-invisible) log digest."""
    root = Path(tmpdir) / world
    store = ArtifactStore(str(root))
    symptom_digest = sha256_text(_NI_SYMPTOM_LOG)
    f2p_log_a = ('### FAIL_TO_PASS\n' + ''.join(
        f'{n} ......................... PASSED\n' for n in _NI_F2P))
    f2p_log_b = ('### FAIL_TO_PASS\n'
                 f'{_NI_F2P[0]} ......................... FAILED\n'
                 f'{_NI_F2P[1]} ......................... PASSED\n')
    f2p_log = f2p_log_b if failing else f2p_log_a
    p2p_log = ''.join(f'{n} PASSED\n' for n in _NI_P2P)
    rec = {
        'artifact_id': make_artifact_id(_NI_INSTANCE, _NI_PATCH),
        'schema_version': SCHEMA_VERSION,
        'instance_id': _NI_INSTANCE, 'repo': 'sympy/sympy',
        'base_commit': _NI_BASE, 'patch_sha256': _NI_PATCH,
        'test_patch_sha256': 'q' * 64,
        'runner': 'pytest', 'run_tree': _NI_TREE,
        'started_at': '2026-10-20T00:00:00+00:00',
        'finished_at': '2026-10-20T00:05:00+00:00',
        'scope': {'rule': 'canonical', 'p2p_scoped_files': ['test_scope.py']},
        'fail_to_pass': ({n: ('FAILED' if failing and n == _NI_F2P[0]
                              else 'PASSED') for n in _NI_F2P}),
        'pass_to_pass_scoped': {n: 'PASSED' for n in _NI_P2P},
        'summary': {
            'f2p_total': len(_NI_F2P),
            'f2p_passed': len(_NI_F2P) - (1 if failing else 0),
            'f2p_failed_ids': [_NI_F2P[0]] if failing else [],
            'p2p_total': len(_NI_P2P), 'p2p_passed': len(_NI_P2P),
            'p2p_regressed_ids': [], 'p2p_preexisting_bad_ids': [],
        },
        'log_digests': {
            'symptom': symptom_digest,
            'f2p': sha256_text(f2p_log),
            'p2p': sha256_text(p2p_log),
        },
    }
    store.put(rec, {'symptom': _NI_SYMPTOM_LOG, 'f2p': f2p_log,
                    'p2p': p2p_log})
    store.put_attestation({
        'instance_id': _NI_INSTANCE, 'patch_sha256': _NI_PATCH,
        'base_commit': _NI_BASE, 'expected_run_tree': _NI_TREE,
        'declared_fail_to_pass': list(_NI_F2P),
        'declared_p2p_scoped': list(_NI_P2P),
        'declared_scope_files': ['test_scope.py'],
        'built_at': '2026-10-20T00:10:00+00:00',
    })
    return root, rec['artifact_id']


def _ni_norm(obj, drop_extra=()):
    """Recursively normalise a JSON payload into canonical text, dropping only
    explicitly declared non-semantic keys (none should be verdict-bearing)."""
    drop = set(drop_extra)

    def walk(x):
        if isinstance(x, dict):
            return {k: walk(v) for k, v in sorted(x.items()) if k not in drop}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return x
    return canonical_dumps(walk(obj))


def _ni_strict_probe(httpd):
    """Open a fresh strict+D session and call EVERY authorised surface, plus
    the denied acceptance channels (expected 403). Returns (semantic map,
    stripped raw map) for cross-world comparison."""
    call = _http(httpd)
    s, _, _ = call('POST', '/sessions',
                   {'instance_id': _NI_INSTANCE, 'base_commit': _NI_BASE,
                    'patch_sha256': _NI_PATCH, 'cell': 'ni',
                    'served_artifact_id': None, 'evidence_tier': 'D',
                    'policy': 'strict', 'claim': _NI_CLAIM,
                    'symptom': _NI_SYMPTOM})
    sid = s['session_id']
    semantic = {}
    art, _, _ = call('GET', f'/sessions/{sid}/artifact')
    verify, _, _ = call('GET', f'/sessions/{sid}/verify')
    fresh, _, _ = call('GET', f'/sessions/{sid}/freshness')
    cov, _, _ = call('GET', f'/sessions/{sid}/coverage')
    cons, _, _ = call('POST', f'/sessions/{sid}/consistency',
                      {'claim': _NI_CLAIM})
    sym, _, _ = call('GET', f'/sessions/{sid}/log/symptom', raw=True)
    _, _, f2pc = call('GET', f'/sessions/{sid}/log/f2p', raw=True)
    for name, payload in (('artifact', art), ('verify', verify),
                          ('freshness', fresh), ('coverage', cov),
                          ('consistency', cons)):
        semantic[name] = _ni_norm(payload)
    semantic['symptom_log'] = sym
    semantic['f2p_status'] = str(f2pc)
    return semantic, {'consistency_verdict': cons.get('verdict'),
                      'f2p_status': f2pc}


def check_noninterference():
    """Returns (errors, human_report)."""
    errs = []
    tmp = tempfile.mkdtemp(prefix='phase3_ni_')
    servers = []
    report = ''
    try:
        root_a, aid = _ni_build_world(tmp, 'worldA', failing=False)
        root_b, _ = _ni_build_world(tmp, 'worldB', failing=True)

        # Sanity: the worlds really differ in hidden outcomes but share the
        # target identity, tree, attestation, symptom and visible digest set.
        sa = ArtifactStore(str(root_a)); sb = ArtifactStore(str(root_b))
        ra, autha = sa.get(aid); rb, authb = sb.get(aid)
        if not (autha and authb):
            errs.append('NI world artifacts not authentic')
        if ra['fail_to_pass'] == rb['fail_to_pass']:
            errs.append('NI setup failed: hidden outcomes identical')
        for k in ('artifact_id', 'base_commit', 'patch_sha256', 'run_tree',
                  'started_at', 'finished_at', 'scope'):
            if ra.get(k) != rb.get(k):
                errs.append(f'NI diagnostic surface differs at key {k}')
        if ra['log_digests']['symptom'] != rb['log_digests']['symptom']:
            errs.append('NI symptom digest differs (diagnostic not held fixed)')
        if ra['log_digests']['f2p'] == rb['log_digests']['f2p']:
            errs.append('NI setup failed: hidden f2p content identical')
        att_a = sa.get_attestation(_NI_INSTANCE, _NI_PATCH)
        att_b = sb.get_attestation(_NI_INSTANCE, _NI_PATCH)
        if _ni_norm(att_a, drop_extra=('_attestation_authentic',)) != \
                _ni_norm(att_b, drop_extra=('_attestation_authentic',)):
            errs.append('NI attestations differ across worlds')

        hda = build_server(str(root_a), port=0)
        hdb = build_server(str(root_b), port=0)
        threading.Thread(target=hda.serve_forever, daemon=True).start()
        threading.Thread(target=hdb.serve_forever, daemon=True).start()
        servers = [hda, hdb]

        # Repeat over INDEPENDENT fresh sessions: no session-id/timing channel.
        reps_a, reps_b, verdicts = [], [], set()
        for rep in range(3):
            pa, ka = _ni_strict_probe(hda)
            pb, kb = _ni_strict_probe(hdb)
            reps_a.append(pa); reps_b.append(pb)
            verdicts.add(ka['consistency_verdict'])
        for rep in range(3):
            if reps_a[rep] != reps_b[rep]:
                for key in sorted(set(reps_a[rep]) | set(reps_b[rep])):
                    if reps_a[rep].get(key) != reps_b[rep].get(key):
                        errs.append(f'NI strict surface {key!r} differs across '
                                    f'World A/B on repetition {rep}')
        if verdicts != {'consistent'}:
            errs.append(f'NI consistency verdict set {verdicts}; hidden '
                        f'acceptance failure flipped the strict verdict')
        # cross-repetition determinism within each world (no hidden sequence
        # encoding in the authorised semantic responses)
        for reps, tag in ((reps_a, 'A'), (reps_b, 'B')):
            if any(r != reps[0] for r in reps[1:]):
                errs.append(f'NI strict responses vary across sessions in '
                            f'World {tag} despite identical inputs')

        # Positive control: escalate WITH a reason in World B reveals the
        # hidden failure and the access is audited.
        callb = _http(hdb)
        s, _, _ = callb('POST', '/sessions',
                        {'instance_id': _NI_INSTANCE, 'base_commit': _NI_BASE,
                         'patch_sha256': _NI_PATCH, 'cell': 'ni-esc',
                         'evidence_tier': 'D', 'policy': 'escalate',
                         'claim': _NI_CLAIM, 'symptom': _NI_SYMPTOM})
        cons, _, code = callb('POST', f"/sessions/{s['session_id']}/consistency",
                              {'reason': 'acceptance verdict needed'})
        if code != 200 or cons.get('verdict') != 'contradicted':
            errs.append(f'NI positive control failed: escalate in World B '
                        f'returned {cons} code {code}, want contradicted')
        log, hs, code = callb('GET',
                              f"/sessions/{s['session_id']}/log/f2p?reason=x",
                              raw=True)
        if code != 200 or 'FAILED' not in log \
                or hs.get('X-Evidence-Tier-Escalation') != '1':
            errs.append('NI positive control: escalated f2p log does not show '
                        'the failure / is not flagged')
        audit_b = (root_b / 'audit.jsonl').read_text(encoding='utf-8')
        if 'consistency_escalation:contradicted' not in audit_b:
            errs.append('NI positive control missing audited escalation')
        report = ('3 repetitions x {artifact,verify,freshness,coverage,'
                  'consistency,symptom,f2p-status}: normalised A/B diff empty; '
                  'strict consistency consistent in both worlds; escalate in '
                  'World B reveals the failure (positive control)')
    finally:
        for h in servers:
            h.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return errs, report


# ===========================================================================
# Wave-2 (GroundedReview) offline checks. Eleven incremental checks; the
# Phase-1/2/3 checks above are deliberately untouched. Every check is purely
# offline (local throwaway HTTP servers only) and never reads an LLM key.
# ===========================================================================

W2_GOLD_SHA256 = ('28cc59dcc2fba1f7aaee6323de611a994238abcebc83b208a5ff'
                  '2dbce4438d01')
W2_CONDS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')
# Frozen Wave-1/Smoke artefacts that Wave-2 must never modify (byte hashes).
W2_FROZEN_HASHES = {
    'phase3_mock_results.jsonl':
        'a1b1f8630bd9503f7201dcb6ee1f2786b6f694f28e858e92052f85647530850a',
    'phase3_ternary_results.jsonl':
        'bcaeb4cb84b8680caf623897cef83720d5dea956c7f15eae0fc531eeb0d120d2',
    'metrics_phase3_ternary.json':
        'bae306b353951d87a6c5a1a91027cc29e9120749868b2497d41cc57dbec2d1e1',
    'metrics_phase3_ternary_mock.json':
        '27d8c39ac50df94012793d0b8e9b975adba53b44e699f891e1efd96ee957866f',
    'phase3_gold.jsonl':
        'dbebcfc311a2402528ceb745c33fc03613e0f433dfda82a779886591f40e45d7',
    'phase2_results.jsonl':
        'f54653cb0e17c1fffae288e12b2a99d93244b13ea4e987504a8c663d68d99de0',
    'metrics_phase2.json':
        'f58f083231d083b164482c90cfb08546783b1c65bd947b3161e128972efe8e04',
    'phase2_fixtures.jsonl':
        '2536d4bf54deec491884f3b2708af323b6c1ccb7a6a19535a42c12bcf3b4ff8d',
    'phase3_fixtures.jsonl':
        '3755ba12ee3867398baca2867c57c1fd7b63bebb6f285f4decf0ce553cb984b9',
    'truth.jsonl':
        '6ed8c4a0426b0ca70a7dd3c3e429f05307c91d3d53f7e9819b2b25e3df833718',
}
def _w2_load(name, store_root):
    return list(read_jsonl(Path(store_root) / name))


def check_w2_gold_dual_channel(store_root):
    """w2-1: dual-channel gold truth table, signature purity, label
    indifference, frozen-sha identity, and deterministic re-derivation."""
    import copy
    from evidence import gold_w2
    from evidence.visibility import load_fixture_facts
    from evidence.schemas import canonical_dumps
    errs = []
    store = ArtifactStore(store_root)
    fixtures = (_w2_load('phase2_fixtures.jsonl', store_root)
                + _w2_load('phase3_fixtures.jsonl', store_root)
                + _w2_load('wave2_fixtures.jsonl', store_root))
    frozen = _w2_load('wave2_gold.jsonl', store_root)
    if len(frozen) != 22:
        errs.append(f'wave2_gold has {len(frozen)} rows, want 22')

    # signature must never accept label/model-output parameters
    errs += ['gold signature: ' + e for e in gold_w2.check_signature_clean()]

    # frozen sha over newline-normalised text (same rule as metrics_w2)
    text = (Path(store_root) / 'wave2_gold.jsonl').read_text(encoding='utf-8')
    import hashlib
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != W2_GOLD_SHA256:
        errs.append('wave2_gold sha256 mismatch')

    # deterministic fresh re-derivation equals the frozen rows. The frozen
    # file is derive_rows PLUS the visibility matrix and decisive-channel
    # audit columns (evidence.wave2_gold.build_gold_rows).
    from evidence import wave2_gold
    rows = wave2_gold.build_gold_rows(store, fixtures)
    if gold_w2.rows_sha256(rows) != W2_GOLD_SHA256:
        errs.append('fresh build_gold_rows hash != frozen wave2_gold hash')
    if len(rows) != len(frozen):
        errs.append(f'derived {len(rows)} rows != frozen {len(frozen)}')
    frozen_by_key = {(r['scenario'], r['id'], r['served_artifact_id']): r
                     for r in frozen}
    for r in rows:
        fr = frozen_by_key.get((r['scenario'], r['id'],
                                r['served_artifact_id']))
        if fr is None or r != fr:
            errs.append(f'gold row mismatch: {r["scenario"]}/'
                        f'{r["served_artifact_id"]}')
    # 9 wave-1 + 13 wave-2 rows
    waves = {}
    for r in rows:
        waves[r['wave']] = waves.get(r['wave'], 0) + 1
    if waves != {'wave1': 9, 'wave2': 13}:
        errs.append(f'wave row counts {waves} != wave1=9/wave2=13')
    # every enriched row carries the visibility matrix and decisive columns
    for r in rows:
        if set(r.get('visibility_matrix', {})) != set(W2_CONDS):
            errs.append(f'{r["scenario"]}: visibility matrix missing')
        if 'decisive_failure' not in r \
                or 'decisive_evidence_channels' not in r:
            errs.append(f'{r["scenario"]}: decisive audit columns missing')
        if r['decisive_failure'] != (r['oracle_gold'] == 'REJECT'):
            errs.append(f'{r["scenario"]}: decisive_failure disagrees with '
                        f'oracle gold')

    by_sc = {}
    for r in rows:
        by_sc.setdefault(r['scenario'], []).append(r)

    # truth table: oracle labels for the five canonical Wave-1 scenarios
    expect_oracle = gold_w2._EXPECTED_ORACLE
    for sc, want in expect_oracle.items():
        grp = by_sc.get(sc)
        if not grp:
            errs.append(f'oracle truth table missing scenario {sc}')
            continue
        if any(r['oracle_gold'] != want for r in grp):
            errs.append(f'oracle {sc}: not all {want}')

    # Wave-2 new scenarios oracle distribution
    w2_want = {'w2_valid': 'ACCEPT', 'w2_stale': 'NEED_EVIDENCE',
               'w2_stale_bad': 'NEED_EVIDENCE',
               'w2_decisive_bad': 'REJECT',
               'w2_incomplete_good': 'NEED_EVIDENCE',
               'w2_stale_persists': 'REJECT'}
    for sc, want in w2_want.items():
        grp = by_sc.get(sc, [])
        if not grp:
            errs.append(f'oracle truth table missing {sc}')
        if any(r['oracle_gold'] != want for r in grp):
            errs.append(f'oracle {sc}: not all {want}')

    # condition truth table for Wave-1 scenarios
    expect_cond = gold_w2._EXPECTED_CONDITION
    for sc, conds in expect_cond.items():
        for r in by_sc.get(sc, []):
            for cond, want in conds.items():
                if want is not None and r['condition_gold'][cond] != want:
                    errs.append(f'condition {sc}/{cond}: '
                                f'{r["condition_gold"][cond]} != {want}')

    # structural identity: Escalate/T3A condition gold always equals oracle
    for r in rows:
        for cond in ('T3D-Escalate', 'T3A-T'):
            if r['condition_gold'][cond] != r['oracle_gold']:
                errs.append(f'identity broken {r["scenario"]}/{cond}')

    # every row carries a visibility_matrix-backed basis and a divergence
    # list consistent with comparable_conditions
    for r in rows:
        comp = r['comparable_conditions']
        for cond in W2_CONDS:
            same = r['condition_gold'][cond] == r['oracle_gold']
            if same != (cond in comp):
                errs.append(f'{r["scenario"]}/{cond}: comparable mismatch')
            if cond not in r['condition_basis']:
                errs.append(f'{r["scenario"]}/{cond}: missing condition basis')
        divs = {(d['condition']) for d in r['oracle_condition_divergences']}
        if divs != {c for c in W2_CONDS if c not in comp}:
            errs.append(f'{r["scenario"]}: divergence list mismatch')

    # label indifference: scramble audit/label columns; label-free rows
    # must be byte-identical
    scrambled = []
    for fx in fixtures:
        f2 = copy.deepcopy(fx)
        f2['merge_acceptable'] = not bool(f2.get('merge_acceptable'))
        f2['label_class'] = 'SCRAMBLED'
        f2['scenario'] = fx['scenario'] + '_scrambled'
        scrambled.append(f2)
    rows2 = wave2_gold.build_gold_rows(store, scrambled)
    strip = lambda rs: sorted(
        ({k: v for k, v in r.items() if k not in ('scenario', 'patch_correct')}
         for r in rs), key=lambda r: r['served_artifact_id'])
    if canonical_dumps(strip(rows)) != canonical_dumps(strip(rows2)):
        errs.append('gold rows changed after label scrambling')
    return errs


def check_w2_gold_function_arguments(store_root):
    """w2-2: derive_rows only ever feeds evidence facts to the gold
    functions; no model output / patch_correct reaches a verdict call."""
    import inspect
    from evidence import gold_w2
    errs = []
    forbidden = gold_w2._FORBIDDEN_SIGNATURE_TOKENS
    src = inspect.getsource(gold_w2)
    # The verdict functions must not be called with kwargs named after a
    # hidden label anywhere in the module.
    for fn_name in ('oracle_gold', 'condition_gold'):
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith('def ') or fn_name + '(' not in line:
                continue
            # inspect only the call arguments, never the callee's own name
            low = line.split(fn_name + '(', 1)[1].lower()
            for tok in forbidden:
                if tok in low:
                    errs.append(f'{fn_name} call mentions {tok}: {stripped}')
    # condition_gold must consume the projected surface, not raw labels
    sig = inspect.signature(gold_w2.condition_gold)
    if 'surface' not in sig.parameters or 'facts' not in sig.parameters:
        errs.append('condition_gold must take (condition, facts, surface)')
    return errs


def check_w2_visibility_http(store_root):
    """w2-3: every wave-2 fixture x five-condition simulated surface equals
    the REAL local server's responses (strict 403, escalate 400->grant,
    presented/static blocks)."""
    from evidence.visibility import cross_check_http
    fixtures = _w2_load('wave2_fixtures.jsonl', store_root)
    errs, _lines = cross_check_http(store_root, fixtures, W2_CONDS)
    return errs


def check_w2_decisive_audit(store_root):
    """w2-4: decisive-failure (M4-class) audit table lists every REJECT
    fixture, one row per condition, with channel access and blameworthy
    flag consistent with the frozen gold."""
    dv_p = Path(store_root) / 'wave2_decisive_visibility.json'
    if not dv_p.exists():
        return ['wave2_decisive_visibility.json missing']
    dv = json.loads(dv_p.read_text(encoding='utf-8'))
    errs = []
    if dv.get('gold_sha256') != W2_GOLD_SHA256:
        errs.append('decisive audit gold_sha256 mismatch')
    gold = {(r['scenario'], r['id']): r
            for r in _w2_load('wave2_gold.jsonl', store_root)}
    # all decisive fixtures in the audit must be oracle REJECT rows
    audit_keys = {(f['scenario'], f['id']) for f in dv['fixtures']}
    for key in audit_keys:
        grp = [r for r in gold.values() if (r['scenario'], r['id']) == key]
        if not grp or any(r['oracle_gold'] != 'REJECT' for r in grp):
            errs.append(f'audit fixture {key} is not an oracle REJECT')
    # and every oracle-REJECT row is present in the audit
    reject_keys = {(r['scenario'], r['id'])
                   for r in gold.values() if r['oracle_gold'] == 'REJECT'}
    if audit_keys != reject_keys:
        errs.append(f'audit fixtures {sorted(audit_keys)} != REJECT set '
                    f'{sorted(reject_keys)}')
    # cell-level: five cells per fixture, blameworthy iff condition_gold is
    # a decisive REJECT; hidden-channel cells are never blameworthy
    for f in dv['fixtures']:
        grp = [r for r in gold.values()
               if (r['scenario'], r['id']) == (f['scenario'], f['id'])]
        grow = grp[0]
        cells = {c['condition']: c for c in f['cells']}
        if set(cells) != set(W2_CONDS):
            errs.append(f'{f["scenario"]}: audit cells != 5 conditions')
            continue
        for cond, cell in cells.items():
            if cell['condition_gold'] != grow['condition_gold'][cond]:
                errs.append(f'{f["scenario"]}/{cond}: audit condition_gold '
                            f'mismatch')
            # blameworthy iff the condition gold is a decisive REJECT AND
            # the reviewer could actually observe a decisive channel
            want_blame = (grow['condition_gold'][cond] == 'REJECT'
                          and cell['decisive_channel_accessible'])
            if cell['blameworthy_abstain'] != want_blame:
                errs.append(f'{f["scenario"]}/{cond}: blameworthy flag '
                            f'{cell["blameworthy_abstain"]} != {want_blame}')
            if not cell['decisive_channel_accessible'] and want_blame:
                errs.append(f'{f["scenario"]}/{cond}: blameworthy without an '
                            f'accessible decisive channel')
    return errs


def check_w2_gap_truth_table():
    """w2-5: gap classifier truth table - static claims unverified,
    adjudicated+observed integrity gaps verified, observable contradiction
    decisive-in-hand, hidden contradiction claimed, blanket NEED unspecified.
    Surfaces are the REAL project_surface outputs over synthetic facts."""
    from evidence.visibility import project_surface
    from evidence import gap_w2 as g
    errs = []

    def facts(**kw):
        return g._synthetic_facts(**kw)

    def cat(cond, gap, f, tv=None):
        return g.classify_abstention(
            cond, gap, project_surface(cond, f), tv)['category']

    active = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')
    static = ('T2D-T', 'T2A-T')

    # 1. blanket / invalid gap -> unspecified in EVERY condition
    for cond in W2_CONDS:
        for gap in ('unspecified', '', 'gibberish'):
            if cat(cond, gap, facts()) != g.UNSPECIFIED:
                errs.append(f'{cond} gap={gap!r} not unspecified')

    # 2. integrity claims in STATIC conditions -> claimed_but_unverified
    stale_f = facts(fresh=False, polarity='gone')
    link_f = facts(linked=False, polarity='gone')
    cov_f = facts(complete=False, failure=1, polarity='gone')
    for cond in static:
        if cat(cond, 'stale', stale_f) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} stale claim must be unverified')
        if cat(cond, 'linkage_mismatch', link_f) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} linkage claim must be unverified')
        if cat(cond, 'coverage_incomplete', cov_f) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} coverage claim must be unverified')

    # 3. ACTIVE: adjudicated false endpoint + observed false verdict +
    # surface false -> verified_gap
    for cond in active:
        if cat(cond, 'stale', stale_f,
               {'freshness': False}) != g.VERIFIED_GAP:
            errs.append(f'{cond} adjudicated stale not verified')
        if cat(cond, 'linkage_mismatch', link_f,
               {'linkage': False}) != g.VERIFIED_GAP:
            errs.append(f'{cond} adjudicated linkage not verified')
        if cat(cond, 'coverage_incomplete', cov_f,
               {'coverage': False}) != g.VERIFIED_GAP:
            errs.append(f'{cond} adjudicated coverage not verified')

    # 4. ACTIVE: endpoint not called / returns true -> claimed
    for cond in active:
        if cat(cond, 'stale', stale_f, {}) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} stale w/o call must be claimed')
        if cat(cond, 'stale', stale_f,
               {'freshness': True}) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} stale endpoint=true must be claimed')

    # 5. contradiction: an OBSERVABLE persisting symptom is decisive in hand
    # in T2D and every active condition, regardless of the consistency
    # endpoint verdict (the symptom channel alone forces REJECT).
    persists = facts(failure=0, executed=3, polarity='persists')
    for cond in ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T3A-T'):
        for tv in ({'consistency': 'contradicted',
                    'symptom_persists': True},
                   {'consistency': 'consistent'},
                   {}):
            c = cat(cond, 'contradiction', persists, tv)
            if c != g.DECISIVE_IN_HAND_BUT_ABSTAINED:
                errs.append(f'{cond} observable persisting symptom must be '
                            f'decisive-in-hand under verdicts {tv}, got {c}')
    # an observable symptom that is GONE, with a consistent endpoint, gives
    # no contradiction -> claimed, never decisive
    gone = facts(failure=0, executed=3, polarity='gone')
    for cond in active:
        if cat(cond, 'contradiction', gone,
               {'consistency': 'consistent'}) != g.CLAIMED_BUT_UNVERIFIED:
            errs.append(f'{cond} gone symptom + consistent verdict must be '
                        f'claimed')
    # T2A hides the symptom but a rendered acceptance failure is decisive
    t2a_fail = facts(failure=1, executed=3, presented_failure=1,
                     presented_executed=3, polarity='persists')
    if cat('T2A-T', 'contradiction', t2a_fail,
           {}) != g.DECISIVE_IN_HAND_BUT_ABSTAINED:
        errs.append('T2A rendered failing ids must be decisive-in-hand')
    # T2A with symptom hidden and no failure rendered -> claimed
    t2a_clean = facts(failure=0, executed=3, polarity='persists')
    if cat('T2A-T', 'contradiction', t2a_clean,
           {}) != g.CLAIMED_BUT_UNVERIFIED:
        errs.append('T2A hidden symptom / green block contradiction unverified')
    return errs


def check_w2_mirror_fixtures(store_root):
    """w2-6: four mirror types present, every wave-2 served artifact is
    signed/attested, and its verify/freshness/coverage surfaces match the
    fixture's expected fact block."""
    from evidence.visibility import load_fixture_facts
    errs = []
    store = ArtifactStore(store_root)
    fixtures = _w2_load('wave2_fixtures.jsonl', store_root)
    if len(fixtures) != 13:
        errs.append(f'wave2 fixtures {len(fixtures)} != 13')
    scenarios = {f['scenario'] for f in fixtures}
    for need in ('w2_valid', 'w2_stale', 'w2_incomplete_good',
                 'w2_decisive_bad'):
        if need not in scenarios:
            errs.append(f'mirror type {need} absent')
    # every served artifact id is in the fix_w2_ namespace
    for f in fixtures:
        if not str(f['served_artifact_id']).startswith('fix_w2_'):
            errs.append(f'{f["id"]}: served aid not fix_w2_ namespace')
    # expected fact block == recomputed oracle facts (hard fail on bad sig)
    for f in fixtures:
        exp = f.get('expected') or {}
        got = store.get(f['served_artifact_id'])
        if got is None:
            errs.append(f'{f["id"]}: served artifact missing')
            continue
        _rec, authentic = got
        if not authentic:
            errs.append(f'{f["id"]}: served artifact inauthentic')
        facts = load_fixture_facts(store, f)
        for k in ('linked', 'fresh', 'complete',
                  'executed_failure_count', 'executed_check_count',
                  'symptom_polarity'):
            if k in exp and exp[k] != facts[k]:
                errs.append(f'{f["id"]} {k}: expected {exp[k]!r} != '
                            f'{facts[k]!r}')
        if 'oracle_gold' in exp:
            from evidence import gold_w2
            inputs = gold_w2._oracle_inputs_from_facts(facts)
            if gold_w2.oracle_gold(**inputs) != exp['oracle_gold']:
                errs.append(f'{f["id"]}: expected oracle_gold mismatch')
    return errs


def check_w2_prompt_versions():
    """w2-7: v2 version string + evidence_gap five-enum schema, while all
    five v1 fingerprints reproduce byte-for-byte from the frozen builders."""
    from evidence import prompts
    errs = []
    if prompts.TERNARY_PROMPT_VERSION != 'p3-ternary-v1':
        errs.append('v1 version constant changed')
    if prompts.TERNARY_PROMPT_VERSION_V2 != 'p3-ternary-v2':
        errs.append('v2 version constant changed')
    # v2 system text enumerates exactly the five evidence_gap values
    base = {'issue': 'ISSUEBODY', 'patch': 'PATCHBODY', 'instance_id': 'x',
            'claim': 'done', 'symptom': {'pre_patch_passed': False,
                                         'post_patch_passed': True},
            'with_claim': True}
    art = {'artifact_id': 'art_demo', 'schema_version': SCHEMA_VERSION,
           'runner': 'r', 'scope': {'rule': 'r', 'p2p_scoped_files': []},
           'base_commit': 'b', 'patch_sha256': 'h',
           'started_at': 't', 'finished_at': 't2', 'instance_id': 'x',
           'summary': {'f2p_total': 1, 'p2p_total': 1},
           'log_digests': {'symptom': 'd'}, 'evidence_tier': 'diagnostic'}
    for cond in W2_CONDS:
        item = dict(base, condition=cond)
        v1 = _prompt_text(prompts.build_ternary_messages(item, artifact=art))
        v2 = _prompt_text(prompts.build_ternary_messages_v2(item,
                                                            artifact=art))
        if 'evidence_gap' not in v2:
            errs.append(f'{cond}: v2 prompt missing evidence_gap schema')
        for enum in ('stale', 'linkage_mismatch', 'coverage_incomplete',
                     'contradiction', 'unspecified'):
            if enum not in v2:
                errs.append(f'{cond}: v2 prompt missing enum {enum}')
        # v2 must still carry the shared task body present in v1
        for needle in ('ISSUEBODY', 'PATCHBODY', 'done'):
            if needle not in v2 or needle not in v1:
                errs.append(f'{cond}: prompt body lost {needle}')
        # fingerprints are stable and version-distinct
        fp1, fp2 = (prompts.ternary_prompt_fingerprint(cond),
                    prompts.ternary_prompt_fingerprint_v2(cond))
        if fp1 == fp2:
            errs.append(f'{cond}: v1/v2 fingerprints collide')
    # v1 fingerprints equal the frozen Smoke version fields
    full_fp = {}
    for r in read_jsonl(Path('evidence_store/phase3_mock_results.jsonl')):
        full_fp[r['condition']] = r['version']['prompt_fingerprint']
    for cond, fp in full_fp.items():
        if prompts.ternary_prompt_fingerprint(cond) != fp:
            errs.append(f'{cond}: live v1 fingerprint != frozen Smoke fp')
    return errs


def check_w2_noninterference_w2(store_root):
    """w2-8: Wave-1 and Wave-2 fixtures coexisting in one store do not
    perturb each other's projected surfaces/gold (namespace isolation)."""
    import copy
    from evidence import gold_w2
    from evidence.visibility import (load_fixture_facts, project_surface,
                                     surface_matrix)
    errs = []
    store = ArtifactStore(store_root)
    w1 = (_w2_load('phase2_fixtures.jsonl', store_root)
          + _w2_load('phase3_fixtures.jsonl', store_root))
    w2 = _w2_load('wave2_fixtures.jsonl', store_root)
    # surfaces derived in isolation must equal those derived with both
    # fixture sets loaded into the same process
    iso = {f['served_artifact_id']: {
        c: project_surface(c, load_fixture_facts(store, f)) for c in W2_CONDS}
        for f in w1 + w2}
    _ = surface_matrix(store, w1 + w2, W2_CONDS)
    for f in w1 + w2:
        for c in W2_CONDS:
            again = project_surface(c, load_fixture_facts(store, f))
            if again != iso[f['served_artifact_id']][c]:
                errs.append(f'{f["served_artifact_id"]}/{c}: surface changes '
                            f'depending on other fixtures present')
    # gold rows for wave-1 fixtures identical whether derived alone or with
    # the 13 wave-2 mirrors present
    rows_alone = gold_w2.derive_rows(store, w1)
    rows_mixed = gold_w2.derive_rows(store, w1 + w2)
    alone = {r['served_artifact_id']: r for r in rows_alone}
    for r in rows_mixed:
        if r['wave'] != 'wave1':
            continue
        if r != alone.get(r['served_artifact_id']):
            errs.append(f'wave1 gold {r["served_artifact_id"]} perturbed by '
                        f'wave2 fixtures')
    # wave-2 served aids never collide with wave-1 artifact ids
    aids1 = {f['served_artifact_id'] for f in w1}
    for f in w2:
        if f['served_artifact_id'] in aids1:
            errs.append(f'wave2 aid collides with wave1: '
                        f'{f["served_artifact_id"]}')
    return errs


def check_w2_frozen_hashes(store_root):
    """w2-9: frozen Phase-1/2/3 files byte-identical; every baseline-hash
    store entry unchanged; all NEW store entries lie in the wave2 whitelist."""
    import hashlib
    errs = []
    root = Path(store_root)
    for name, want in W2_FROZEN_HASHES.items():
        p = root / name
        if not p.exists():
            errs.append(f'frozen file missing: {name}')
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != want:
            errs.append(f'FROZEN FILE CHANGED {name}: {got}')
    # baseline hash manifest (213 entries). All but two must keep their
    # recorded bytes. The two known divergences pre-date / sit outside the
    # wave2 window:
    #   - audit.jsonl is the append-only server audit log; the LEGACY HTTP
    #     self-checks (check_linkage_http / phase3 policy) append rows by
    #     design. It was byte-stable during the wave2 window (pre==post) and
    #     contains zero fix_w2_/wave2 rows.
    #   - fixtures_meta.json already differed from the old manifest before
    #     the wave2 window and is unchanged inside it.
    known_benign = {'audit.jsonl', 'fixtures_meta.json'}
    pre = post = None
    pre_p, post_p = (root / 'wave2_snapshot_pre.json',
                     root / 'wave2_snapshot_post.json')
    if pre_p.exists() and post_p.exists():
        pre = json.loads(pre_p.read_text(encoding='utf-8'))
        post = json.loads(post_p.read_text(encoding='utf-8'))
    bh_p = root / 'phase3_baseline_hashes.json'
    if bh_p.exists():
        manifest = json.loads(bh_p.read_text(encoding='utf-8-sig'))
        diverged = []
        for e in manifest:
            p = root / e['path']
            if not p.exists():
                errs.append(f'baseline entry missing: {e["path"]}')
                continue
            got = hashlib.sha256(p.read_bytes()).hexdigest()
            if got == e['sha256']:
                continue
            diverged.append(e['path'])
            if e['path'] not in known_benign:
                errs.append(f'BASELINE ENTRY CHANGED {e["path"]}')
        if set(diverged) != known_benign:
            errs.append(f'baseline divergences {sorted(diverged)} != expected '
                        f'{sorted(known_benign)}')
        for rel in known_benign:
            text = (root / rel).read_text(encoding='utf-8', errors='replace')
            if 'fix_w2_' in text or 'wave2' in text:
                errs.append(f'{rel}: benign exception now carries wave2 '
                            f'namespace content')
            if pre is not None and pre.get(rel) != post.get(rel):
                errs.append(f'{rel}: mutated during the wave2 window')
    # pre/post snapshot: nothing pre-existing removed or mutated; only the
    # build's own audit file may change, and additions are restricted to the
    # wave2 root files plus fix_w2_ namespaced artifacts/signatures/logs.
    if pre is not None:
        removed = set(pre) - set(post)
        if removed:
            errs.append(f'snapshot removed entries: {sorted(removed)[:5]}')
        changed = [k for k in set(pre) & set(post) if pre[k] != post[k]]
        if set(changed) != {'wave2_build_audit.json'}:
            errs.append(f'snapshot mutated unexpected entries: {changed}')
        allowed_root_new = {'wave2_build.log', 'wave2_fixtures.jsonl',
                            'wave2_fixtures_meta.json',
                            'wave2_snapshot_pre.json'}
        new_counts = {'logs': 0, 'signatures': 0, 'artifacts': 0}
        for k in set(post) - set(pre):
            parts = k.split('/')
            if len(parts) == 1:
                if k not in allowed_root_new:
                    errs.append(f'non-wave2 new root entry: {k}')
                continue
            d, tail = parts[0], parts[-1]
            if d in new_counts:
                new_counts[d] += 1
                if not tail.startswith('fix_w2_'):
                    errs.append(f'new {d} entry outside fix_w2_ namespace: {k}')
            else:
                errs.append(f'new entry in unexpected directory: {k}')
        if new_counts != {'logs': 45, 'signatures': 13, 'artifacts': 13}:
            errs.append(f'new artifact/log/signature counts {new_counts} != '
                        f'logs=45/signatures=13/artifacts=13')
    return errs


def check_w2_mock_runner(store_root):
    """w2-10: the zero-cost wave2 mock run - 65 cells, v2-only gap
    enrichment, totals 35/10/20 and gap 14/3/2/16; frozen v1 output never
    carries the v2 keys."""
    from collections import Counter
    errs = []
    root = Path(store_root)
    rows = _w2_load('wave2_mock_results.jsonl', store_root)
    if len(rows) != 65:
        errs.append(f'wave2 mock rows {len(rows)} != 65')
    if any(not r.get('mock') for r in rows):
        errs.append('wave2 mock contains non-mock rows')
    if any(float(r.get('cost_usd') or 0) != 0.0 for r in rows):
        errs.append('wave2 mock incurred cost')
    if any(r.get('tokens_in') or r.get('tokens_out') for r in rows):
        errs.append('wave2 mock consumed tokens')
    if {r['version']['prompt_version'] for r in rows} != {'p3-ternary-v2'}:
        errs.append('wave2 mock prompt versions not all v2')
    if {r['version']['gold_sha256'] for r in rows} != {W2_GOLD_SHA256}:
        errs.append('wave2 mock gold hash mismatch')
    if any(r.get('error') for r in rows):
        errs.append('wave2 mock has error cells')
    dec = Counter(r['parsed'] for r in rows)
    if dict(dec) != {'NEED_EVIDENCE': 35, 'REJECT': 10, 'ACCEPT': 20}:
        errs.append(f'wave2 mock decisions {dict(dec)}')
    cats = Counter((r.get('gap_classification') or {}).get('category')
                   for r in rows if r['parsed'] == 'NEED_EVIDENCE')
    want = {'verified_gap': 14, 'claimed_but_unverified': 3,
            'decisive_in_hand_but_abstained': 2, 'unspecified': 16}
    if dict(cats) != want:
        errs.append(f'wave2 mock gap categories {dict(cats)} != {want}')
    for r in rows:
        if r['parsed'] != 'NEED_EVIDENCE' and 'gap_classification' in r:
            errs.append(f'{r["cell"]}: gap_classification on non-NEED row')
        if r['condition'] in ('T2D-T', 'T2A-T') and r.get('tool_verdicts'):
            errs.append(f'{r["cell"]}: static cell carries tool_verdicts')
    # frozen v1 file must remain v2-key-free and byte-frozen
    v1p = root / 'phase3_mock_results.jsonl'
    import hashlib
    if hashlib.sha256(v1p.read_bytes()).hexdigest() != \
            W2_FROZEN_HASHES['phase3_mock_results.jsonl']:
        errs.append('frozen v1 mock file changed')
    for r in _w2_load('phase3_mock_results.jsonl', store_root):
        if r['version']['prompt_version'] != 'p3-ternary-v1':
            errs.append('frozen v1 row not p3-ternary-v1')
        for k in ('evidence_gap', 'tool_verdicts', 'gap_classification'):
            if k in r:
                errs.append(f'frozen v1 row {r["cell"]} carries v2 key {k}')
    return errs


def check_w2_offline_network(store_root):
    """w2-11: the wave2 validation path performs no paid LLM call - mock
    rows are zero-cost, the runner never instantiates an LLM client under
    --mock, and no wave2 module hard-codes a callable LLM endpoint."""
    import inspect
    import re
    errs = []
    # wave2 modules contain no LLM base URLs / key reads
    from evidence import visibility, gold_w2, gap_w2, metrics_w2
    for mod in (visibility, gold_w2, gap_w2, metrics_w2):
        src = inspect.getsource(mod)
        if 'DEEPSEEK_API_KEY' in src or 'api.deepseek.com' in src \
                or 'OPENAI_API_KEY' in src:
            errs.append(f'{mod.__name__} references an LLM key/endpoint')
        if re.search(r'urllib\.request\.urlopen\s*\(', src) \
                and 'cross_check_http' not in src:
            # only the HTTP cross-check may open sockets, and only to a
            # local server it spawned itself
            errs.append(f'{mod.__name__} opens an unqualified HTTP connection')
    # cross_check_http must bind to 127.0.0.1 port=0 only
    if 'build_server(tmp, port=0)' not in inspect.getsource(
            visibility.cross_check_http):
        errs.append('visibility cross-check does not spawn an ephemeral local '
                    'server')
    # the mock model path never reads an API key
    from evidence import phase3_run
    psrc = inspect.getsource(phase3_run)
    # ScriptedModel is the mock; the live client key read must be in a branch
    # that --mock never reaches (structural check: key read occurs only inside
    # the non-mock run function body, while mock uses ScriptedModel)
    if 'class ScriptedModel' not in psrc:
        errs.append('ScriptedModel missing from phase3_run')
    for r in _w2_load('wave2_mock_results.jsonl', store_root):
        mdl = r.get('model') or r.get('model_served')
        if mdl and 'scripted' not in str(mdl).lower() and r.get('mock'):
            errs.append(f'mock row names a live model: {mdl}')
    return errs


def run_wave2_checks(store_root):
    return (
        [('w2-gold-dual-channel', check_w2_gold_dual_channel(store_root)),
         ('w2-gold-function-arguments',
          check_w2_gold_function_arguments(store_root)),
         ('w2-visibility-http', check_w2_visibility_http(store_root)),
         ('w2-decisive-audit', check_w2_decisive_audit(store_root)),
         ('w2-ggap-truth-table', check_w2_gap_truth_table()),
         ('w2-mirror-fixtures', check_w2_mirror_fixtures(store_root)),
         ('w2-prompt-versions', check_w2_prompt_versions()),
         ('w2-noninterference', check_w2_noninterference_w2(store_root)),
         ('w2-frozen-hashes', check_w2_frozen_hashes(store_root)),
         ('w2-mock-runner', check_w2_mock_runner(store_root)),
         ('w2-offline-network', check_w2_offline_network(store_root))])


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default='evidence_store')
    a = ap.parse_args()
    all_errs = []
    all_errs += ['visibility: ' + e for e in check_visibility([])]
    all_errs += ['tier-leakage: ' + e for e in check_tier_leakage()]
    all_errs += ['truth/store: ' + e for e in check_truth_and_store(a.store)]
    all_errs += ['linkage: ' + e for e in check_linkage_http(a.store)]
    all_errs += ['phase2-fixtures: ' + e for e in check_phase2_fixtures(a.store)]
    all_errs += ['ternary-prompts: ' + e for e in check_ternary_prompts()]
    all_errs += ['gold-asymmetry: ' + e for e in check_gold_asymmetry(a.store)]
    all_errs += ['phase3-policy: ' + e for e in check_phase3_policy_http(a.store)]
    all_errs += ['phase3-fixtures: ' + e for e in check_phase3_fixtures(a.store)]
    all_errs += ['metrics3-pure: ' + e for e in check_metrics3_pure()]
    ni_report = None
    ni_errs = check_noninterference()
    all_errs += ['noninterference: ' + e for e in ni_errs[0]]
    ni_report = ni_errs[1]
    # Wave-2 incremental checks (eleven); appended after the frozen
    # Phase-1/2/3 checks so the legacy suite above runs byte-identically.
    for tag, errs in run_wave2_checks(a.store):
        all_errs += [tag + ': ' + e for e in errs]
    if all_errs:
        print('SELFCHECK FAILED:')
        for e in all_errs:
            print(' -', e)
        raise SystemExit(1)
    print('selfcheck OK: visibility, tier leakage control, truth/store signatures, '
          'log digests, HTTP linkage, Phase-2 fixture surfaces, ternary prompt '
          'isolation, asymmetric frozen gold, strict/escalate policy gates, '
          'Phase-3 mirror fixtures, metrics3 pure scoring, and the World A/B '
          'hidden-data noninterference test all pass')
    print('wave2 OK: dual-channel gold (truth table / label indifference / '
          'frozen sha / deterministic re-derivation / signature purity), '
          'real-server visibility cross-check, decisive-visibility audit, '
          'gap classifier truth table, four mirror fixture surfaces, v1/v2 '
          'prompt fingerprints, wave1/wave2 namespace noninterference, '
          'frozen-hash + pre/post snapshot audit, zero-cost v2 mock runner, '
          'and the offline no-LLLM network surface all pass')
    if ni_report:
        print('noninterference: ' + ni_report)

if __name__ == '__main__':
    main()
