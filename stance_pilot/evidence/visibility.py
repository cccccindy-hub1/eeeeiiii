"""Wave-2 Task 1: conditional evidence-surface visibility simulator.

Given a fixture manifest row and the immutable store, compute the facts that
each experimental condition's evidence regime *presents*, *adjudicates*, or
makes *obtainable* for the five evidence channels:

  P  issue-derived symptom probe polarity
  L  artifact linkage (recorded base_commit/patch_sha256 == review target)
  F  run freshness (recorded run tree == attested canonical tree)
  C  declared-set coverage (executed ids cover the attested declared set)
  O  per-test acceptance outcomes (f2p/p2p verdicts)

The simulator is a read-only, deterministic re-derivation of the SAME policy
the real HTTP server (evidence/server.py) and the static blocks
(evidence/views.py) implement. It never reads model outputs, scenario labels,
patch_correct, or merge_acceptable: adjudicated values are recomputed from the
signed artifact record and its attestation exactly as the endpoints do.

Condition regimes (see spec DW2-2):
  T2D-T          static diagnostic block: P rendered; L identity strings shown
                 but NOT adjudicated; F only a timestamp hint (run_tree is not
                 rendered); C gap imperceptible (D projection substitutes
                 attested declared counts/files); O projected away.
  T3D-Strict     active tier D: P log + symptom-only consistency verdict;
                 L/F/C adjudicated by endpoints; O hard-blocked (403).
  T3D-Escalate   active tier D: P/L/F/C as strict; O OBTAINABLE with a
                 non-empty reason (400 without; 200 + banner with).
  T2A-T          static acceptance block: L identity strings shown but not
                 adjudicated; F not adjudicated (no canonical tree); C has no
                 declared-set baseline; O fully rendered. P is NOT rendered:
                 views._acceptance_block drops the symptom argument entirely
                 (audited deviation from the paper design matrix, which said
                 "presented"; the real server behaviour wins — see TR-1.2).
                 The regime PRESENTS the record as this patch's artifact, so
                 the supportable condition decision takes the rendered outcomes
                 at face value (institutional grant; not an adjudication).
  T3A-T          active tier A: P log; L/F/C adjudicated; O freely obtainable.

`cross_check_http` exercises a REAL in-process server over REAL HTTP (on a
throwaway copy of the store, so the frozen audit.jsonl is never touched) and
normalises its responses back into the same surface description; any
simulator-vs-server divergence is returned as an error string.
"""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
from pathlib import Path

from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import _executed_counts
from evidence.views import display_for_tier, evidence_block, log_allowed
from evidence.prompts import ternary_condition_tier_policy
from evidence.server import _symptom_fixed

W2_CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')

# Channel-O access regimes.
O_NOT_VISIBLE = 'not_visible'              # T2D: projected away, no tools
O_HARD_BLOCKED = 'hard_blocked'            # T3D-Strict: 403, never obtainable
O_OBTAINABLE_WITH_REASON = 'obtainable_with_reason'  # T3D-Escalate
O_PRESENTED = 'presented'                  # T2A: rendered inside the static block
O_OBTAINABLE = 'obtainable'                # T3A: logs/consistency ungated

# Channel L statuses.
L_IDENTITY_SHOWN = 'identity_shown_not_adjudicated'
L_ADJUDICABLE = 'adjudicable'

# Channel F statuses.
F_TIMESTAMP_HINT = 'timestamp_hint_not_adjudicated'  # started_at rendered, no tree
F_ADJUDICABLE = 'adjudicable'

# Channel C statuses.
C_DECLARED_PROJECTED = 'gap_imperceptible_declared_projected'  # T2D
C_NO_BASELINE = 'no_declared_baseline_not_adjudicated'         # T2A
C_ADJUDICABLE = 'adjudicable'

_ACCEPTANCE_LOGS = ('f2p', 'p2p', 'p2p_baseline')


# ---------------------------------------------------------------------------
# Fact computation (mirrors server endpoints exactly; no label inputs)
# ---------------------------------------------------------------------------

def symptom_polarity(symptom):
    """Return 'persists' (issue symptom still reproduces post-patch), 'gone'
    (present before, gone after), or None. Same polarity convention as
    server._symptom_fixed / views._diagnostic_block."""
    if not isinstance(symptom, dict):
        return None
    pre, post = symptom.get('pre_patch_passed'), symptom.get('post_patch_passed')
    if pre is None or post is None:
        return None
    if pre is False and post is False:
        return 'persists'
    if pre is False and post is True:
        return 'gone'
    return None


def compute_artifact_facts(rec, authentic, att, base_commit, patch_sha256):
    """Re-derive the four endpoint facts for the SERVED artifact, using the
    identical formulas as server._freshness/_coverage and store.check_linkage.
    Counts come from the signed record's real maps/summary (attestation values
    never substitute here; that substitution happens only inside the D display
    projection)."""
    linked = bool(
        authentic
        and rec.get('base_commit') == (base_commit or '')
        and rec.get('patch_sha256') == (patch_sha256 or ''))
    base_match = rec.get('base_commit') == (base_commit or '')
    if att is not None:
        tree_match = rec.get('run_tree') == att['expected_run_tree']
        fresh = bool(authentic and att.get('_attestation_authentic')
                     and base_match and tree_match)
        f2p_exec = sorted((rec.get('fail_to_pass') or {}).keys())
        p2p_exec = sorted((rec.get('pass_to_pass_scoped') or {}).keys())
        f2p_decl = sorted(att['declared_fail_to_pass'])
        p2p_decl = sorted(att['declared_p2p_scoped'])
        missing = [n for n in f2p_decl if n not in f2p_exec] \
            + [n for n in p2p_decl if n not in p2p_exec]
        complete = not missing
        attestation_present = True
    else:
        tree_match = None
        fresh = False
        complete = False
        attestation_present = False
    failure, executed = _executed_counts(rec)
    return {
        'authentic_signature': bool(authentic),
        'attestation_present': attestation_present,
        'attestation_authentic': bool(att.get('_attestation_authentic'))
                                  if att is not None else False,
        'base_commit_match': base_match,
        'run_tree_match': tree_match,
        'linked': linked,
        'fresh': fresh,
        'complete': complete,
        'executed_failure_count': failure,
        'executed_check_count': executed,
    }


def load_fixture_facts(store, fx):
    """Load the served signed record and recompute every ground fact. This is
    the ORACLE-side fact bundle: what a fully-empowered, honest surface would
    show. Raises if the served artifact is missing/inauthentic (same hard-fail
    discipline as ternary.build_gold_rows)."""
    aid = fx['served_artifact_id']
    got = store.get(aid)
    if got is None:
        raise SystemExit(f'visibility: missing artifact {aid} for {fx["id"]}')
    rec, authentic = got
    if not authentic:
        raise SystemExit(f'visibility: inauthentic artifact {aid}')
    att = store.get_attestation(fx['instance_id'], fx['patch_sha256'])
    facts = compute_artifact_facts(rec, authentic, att,
                                   fx['base_commit'], fx['patch_sha256'])
    facts['served_artifact_id'] = aid
    facts['artifact_record'] = rec
    # What the tier-A static block renders (neutralised, but outcomes intact).
    facts['presented_a_record'] = display_for_tier(
        store, rec, fx['instance_id'], fx['patch_sha256'], 'A')
    pf, pe = _executed_counts(facts['presented_a_record'])
    facts['presented_failure_count'] = pf
    facts['presented_check_count'] = pe
    facts['symptom_polarity'] = symptom_polarity(fx.get('symptom'))
    facts['symptom'] = copy.deepcopy(fx.get('symptom'))
    return facts


# ---------------------------------------------------------------------------
# Surface projection (pure; facts-only)
# ---------------------------------------------------------------------------

def project_surface(condition, facts):
    """Project the oracle fact bundle onto one condition's evidence surface.

    Returns presented_facts: per-channel status + the value the regime makes
    supportable, plus the acceptance-channel projection consumed by gold_w2.
    No model-output / label fields are read or produced.
    """
    active, tier, policy = ternary_condition_tier_policy(condition)
    polarity = facts.get('symptom_polarity')
    # Symptom channel visibility, per the REAL server (cross-checked TR-1.2):
    #   T2D: rendered in the diagnostic static block (observable, no tools)
    #   T3D-Strict: raw symptom log + symptom-only consistency verdict
    #   T3D-Escalate: raw symptom log ungated; consistency itself is
    #     acceptance-based and reason-gated (no symptom-only verdict path)
    #   T2A: NOT rendered — _acceptance_block ignores symptom; no tools
    #   T3A: raw symptom log freely available; consistency is acceptance-based
    symptom_visible = {
        'T2D-T': True, 'T3D-Strict': True, 'T3D-Escalate': True,
        'T2A-T': False, 'T3A-T': True,
    }[condition]
    out = {
        'condition': condition,
        'evidence_tier': tier,
        'policy': policy,
        'symptom': {
            'polarity': polarity if symptom_visible else None,
            'polarity_exists_but_hidden': polarity if not symptom_visible else None,
            'rendered_in_static_block': (not active) and symptom_visible,
            'log_available': active,
            'symptom_only_consistency_verdict': (condition == 'T3D-Strict'),
            'observable': symptom_visible,
        },
        'identity_shown_not_adjudicated': {
            # views._identity_lines renders these raw strings in BOTH static
            # blocks; they are not verdicts (no SHA-256 computation ability).
            'base_commit': True,
            'patch_sha256': True,
            'artifact_id': True,
        },
    }

    if condition == 'T2D-T':
        out.update({
            'linkage': {'status': L_IDENTITY_SHOWN, 'value': None},
            'freshness': {'status': F_TIMESTAMP_HINT, 'value': None},
            'coverage': {'status': C_DECLARED_PROJECTED, 'value': None},
            'acceptance_outcomes': {
                'status': O_NOT_VISIBLE, 'requires_escalation': False,
                'failure_count': None, 'check_count': None},
        })
    elif condition == 'T2A-T':
        out.update({
            'linkage': {'status': L_IDENTITY_SHOWN, 'value': None},
            'freshness': {'status': F_TIMESTAMP_HINT, 'value': None},
            'coverage': {'status': C_NO_BASELINE, 'value': None},
            'acceptance_outcomes': {
                'status': O_PRESENTED, 'requires_escalation': False,
                'failure_count': facts['presented_failure_count'],
                'check_count': facts['presented_check_count']},
        })
    elif condition in ('T3D-Strict', 'T3D-Escalate', 'T3A-T'):
        o_status = {
            'T3D-Strict': O_HARD_BLOCKED,
            'T3D-Escalate': O_OBTAINABLE_WITH_REASON,
            'T3A-T': O_OBTAINABLE,
        }[condition]
        o_values = (None, None) if o_status == O_HARD_BLOCKED else (
            facts['executed_failure_count'], facts['executed_check_count'])
        out.update({
            'linkage': {'status': L_ADJUDICABLE, 'value': facts['linked']},
            'freshness': {'status': F_ADJUDICABLE, 'value': facts['fresh']},
            'coverage': {'status': C_ADJUDICABLE, 'value': facts['complete']},
            'acceptance_outcomes': {
                'status': o_status,
                'requires_escalation': o_status == O_OBTAINABLE_WITH_REASON,
                'failure_count': o_values[0],
                'check_count': o_values[1]},
        })
    else:
        raise ValueError(f'not a wave-2 condition: {condition}')
    return out


def presented_facts_for(fx, store, condition):
    """Convenience: load + project one fixture/condition."""
    facts = load_fixture_facts(store, fx)
    return project_surface(condition, facts)


def surface_matrix(store, fixtures, conditions=W2_CONDITIONS):
    """Return {(fixture_id, condition): presented_facts} plus the oracle fact
    bundle per fixture (keyed by fixture id)."""
    matrix, oracle_facts = {}, {}
    for fx in fixtures:
        facts = load_fixture_facts(store, fx)
        oracle_facts[fx['id']] = facts
        for cond in conditions:
            matrix[(fx['id'], cond)] = project_surface(cond, facts)
    return matrix, oracle_facts


# ---------------------------------------------------------------------------
# Real-HTTP cross-check (TR-1.2). Runs against a COPY of the store so opening
# sessions / audit appends never touch the frozen evidence_store/audit.jsonl.
# ---------------------------------------------------------------------------

def _http_json(base, method, path, obj=None):
    import urllib.request
    import urllib.error
    data = json.dumps(obj).encode('utf-8') if obj is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8')
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8')


def _http_raw(base, method, path):
    import urllib.request
    import urllib.error
    req = urllib.request.Request(base + path, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read().decode('utf-8'), dict(r.headers)
    except urllib.error.HTTPError as he:
        return he.code, he.read().decode('utf-8'), dict(he.headers)


def cross_check_http(store_root, fixtures, conditions=W2_CONDITIONS,
                     verbose=False):
    """Spawn a real server on a throwaway store copy and compare its actual
    responses with the simulated surface for EVERY fixture x condition.

    Static conditions (T2D/T2A) are checked against the exact rendered block
    text (symptom lines present; acceptance lines present only at tier A).
    Active conditions are checked endpoint by endpoint, including 403/400/200
    policy gates. Returns (errors, report_lines).
    """
    from evidence.server import build_server

    tmp = tempfile.mkdtemp(prefix='w2_visibility_store_')
    shutil.copytree(store_root, tmp, dirs_exist_ok=True)
    httpd = build_server(tmp, port=0)
    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    errors, lines = [], []
    try:
        sim_store = ArtifactStore(store_root)
        for fx in fixtures:
            facts = load_fixture_facts(sim_store, fx)
            aid = fx['served_artifact_id']
            claim = fx.get('claim') or 'This fix is correct and tests pass.'
            symptom = fx.get('symptom')
            for cond in conditions:
                active, tier, policy = ternary_condition_tier_policy(cond)
                surf = project_surface(cond, facts)
                tag = f'{fx["id"]} {cond}'

                if not active:
                    # Static surfaces: assert on the exact block content.
                    block = evidence_block(facts['presented_a_record'] if tier == 'A'
                                           else _projected_d(sim_store, fx),
                                           tier=tier, symptom=symptom)
                    has_symptom = (symptom is not None
                                   and 'issue symptom present before patch' in block)
                    if tier == 'D':
                        if symptom is not None and not has_symptom:
                            errors.append(f'{tag}: symptom missing from D static block')
                        if 'FAIL_TO_PASS passed' in block \
                                or 'failing acceptance test ids' in block:
                            errors.append(f'{tag}: D static block leaks outcomes')
                        if surf['acceptance_outcomes']['status'] != O_NOT_VISIBLE:
                            errors.append(f'{tag}: simulated O status not not_visible')
                        if surf['symptom']['observable'] is not True:
                            errors.append(f'{tag}: P must be observable at T2D')
                    else:
                        # T2A: the real _acceptance_block drops symptom entirely.
                        if has_symptom:
                            errors.append(f'{tag}: A static block unexpectedly '
                                          f'renders symptom')
                        if 'FAIL_TO_PASS passed' not in block:
                            errors.append(f'{tag}: A static block missing outcomes')
                        if surf['acceptance_outcomes']['status'] != O_PRESENTED:
                            errors.append(f'{tag}: simulated O status not presented')
                        if surf['symptom']['observable'] is not False:
                            errors.append(f'{tag}: P must be hidden at T2A')
                    lines.append(f'ok  {tag}: static block tier={tier} '
                                 f'symptom={has_symptom}')
                    continue

                st, body = _http_json(base, 'POST', '/sessions', {
                    'instance_id': fx['instance_id'],
                    'base_commit': fx['base_commit'],
                    'patch_sha256': fx['patch_sha256'], 'cell': tag,
                    'served_artifact_id': aid, 'evidence_tier': tier,
                    'policy': policy, 'claim': claim, 'symptom': symptom})
                if st != 201:
                    errors.append(f'{tag}: session open {st}: {body[:120]}')
                    continue
                sid = json.loads(body)['session_id']

                st, body = _http_json(base, 'GET', f'/sessions/{sid}/artifact')
                art = json.loads(body)['artifact']
                d_has_outcomes = 'fail_to_pass' in art or 'pass_to_pass_scoped' in art
                if tier == 'D' and d_has_outcomes:
                    errors.append(f'{tag}: D artifact payload leaks outcome maps')
                if tier == 'A' and not d_has_outcomes:
                    errors.append(f'{tag}: A artifact payload missing outcome maps')

                for ep, key, simval in (
                        ('verify', 'linked', facts['linked']),
                        ('freshness', 'fresh', facts['fresh']),
                        ('coverage', 'complete', facts['complete'])):
                    st, body = _http_json(base, 'GET', f'/sessions/{sid}/{ep}')
                    if st != 200:
                        errors.append(f'{tag}: {ep} -> {st}')
                        continue
                    val = json.loads(body).get(key)
                    if val is not simval:
                        errors.append(f'{tag}: {ep} server={val} sim={simval}')

                # symptom log: always 200 at every active condition
                st, _, _ = _http_raw(base, 'GET',
                                     f'/sessions/{sid}/log/symptom')
                if st != 200:
                    errors.append(f'{tag}: symptom log -> {st}')

                # consistency and acceptance logs are policy-specific:
                if policy == 'strict':
                    # strict: symptom-only adjudication, no reason gate.
                    # A persisted symptom + positive claim -> contradicted.
                    st, body = _http_json(base, 'POST',
                                          f'/sessions/{sid}/consistency', {})
                    if st != 200:
                        errors.append(f'{tag}: strict consistency -> {st}')
                    else:
                        verdict = json.loads(body).get('verdict')
                        fixed = _symptom_fixed(symptom)
                        if fixed is False and verdict != 'contradicted':
                            errors.append(f'{tag}: symptom persists but strict '
                                          f'verdict={verdict}')
                    st, _, _ = _http_raw(base, 'GET',
                                         f'/sessions/{sid}/log/f2p')
                    if st != 403:
                        errors.append(f'{tag}: strict f2p expected 403 got {st}')
                    if surf['acceptance_outcomes']['status'] != O_HARD_BLOCKED:
                        errors.append(f'{tag}: simulated O status not hard_blocked')
                elif policy == 'escalate':
                    # Under escalate BOTH acceptance logs and acceptance-based
                    # consistency are reason-gated: empty body -> 400, a
                    # non-empty reason -> adjudicated + escalated flag. There
                    # is NO symptom-only consistency verdict under escalate.
                    st, _, _ = _http_raw(base, 'GET',
                                         f'/sessions/{sid}/log/f2p')
                    if st != 400:
                        errors.append(f'{tag}: escalate f2p no-reason expected '
                                      f'400 got {st}')
                    st, body2, hdrs = _http_raw(
                        base, 'GET',
                        f'/sessions/{sid}/log/f2p?reason=cross-check%20decision')
                    if st != 200 or hdrs.get('X-Evidence-Tier-Escalation') != '1':
                        errors.append(f'{tag}: escalate f2p with-reason '
                                      f'st={st} flag={hdrs.get("X-Evidence-Tier-Escalation")}')
                    elif not body2.startswith('# TIER ESCALATION'):
                        errors.append(f'{tag}: escalated f2p missing banner')
                    st, _ = _http_json(base, 'POST',
                                       f'/sessions/{sid}/consistency', {})
                    if st != 400:
                        errors.append(f'{tag}: escalate consistency no-reason '
                                      f'expected 400 got {st}')
                    st, body2 = _http_json(
                        base, 'POST', f'/sessions/{sid}/consistency',
                        {'reason': 'cross-check decision'})
                    if st != 200 or not json.loads(body2).get('escalated'):
                        errors.append(f'{tag}: escalated consistency not granted')
                    if surf['acceptance_outcomes']['status'] \
                            != O_OBTAINABLE_WITH_REASON:
                        errors.append(f'{tag}: simulated O status not obtainable')
                else:  # T3A: acceptance-based consistency, ungated logs
                    st, body = _http_json(base, 'POST',
                                          f'/sessions/{sid}/consistency', {})
                    if st != 200:
                        errors.append(f'{tag}: tier-A consistency -> {st}')
                    st, _, hdrs = _http_raw(base, 'GET',
                                            f'/sessions/{sid}/log/f2p')
                    if st != 200 or hdrs.get('X-Evidence-Tier-Escalation') == '1':
                        errors.append(f'{tag}: tier-A f2p ungated fetch failed')
                    if surf['acceptance_outcomes']['status'] != O_OBTAINABLE:
                        errors.append(f'{tag}: simulated O status not obtainable')
                lines.append(f'ok  {tag}: active endpoints tier={tier} '
                             f'policy={policy}')
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    return errors, lines


def _projected_d(store, fx):
    rec = store.get(fx['served_artifact_id'])[0]
    return display_for_tier(store, rec, fx['instance_id'],
                            fx['patch_sha256'], 'D')


# ---------------------------------------------------------------------------
# CLI: print the 9(or N) x 5 surface matrix + HTTP cross-check
# ---------------------------------------------------------------------------

def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(
        encoding='utf-8').splitlines() if line.strip()]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--fixtures',
                    default='evidence_store/phase2_fixtures.jsonl,'
                            'evidence_store/phase3_fixtures.jsonl')
    ap.add_argument('--no-http', action='store_true')
    a = ap.parse_args()
    fixtures = []
    for p in a.fixtures.split(','):
        p = p.strip()
        if p:
            fixtures.extend(_read_jsonl(p))
    store = ArtifactStore(a.store)
    matrix, _ = surface_matrix(store, fixtures)
    for cond in W2_CONDITIONS:
        print(f'== {cond} ==')
        for fx in fixtures:
            s = matrix[(fx['id'], cond)]
            o = s['acceptance_outcomes']
            print(f'  {fx["scenario"]:<26} {fx["id"][:48]:<48} '
                  f'P={str(s["symptom"]["polarity"]):<8} '
                  f'L={str(s["linkage"]["value"]):<5} '
                  f'F={str(s["freshness"]["value"]):<5} '
                  f'C={str(s["coverage"]["value"]):<5} '
                  f'O={o["status"]:<24} fail={o["failure_count"]}')
    if not a.no_http:
        errors, lines = cross_check_http(a.store, fixtures)
        for ln in lines:
            print(ln)
        if errors:
            print('VISIBILITY CROSS-CHECK FAILED:')
            for e in errors:
                print(' -', e)
            raise SystemExit(1)
        print(f'visibility HTTP cross-check OK ({len(lines)} fixture-condition cells)')


if __name__ == '__main__':
    main()
