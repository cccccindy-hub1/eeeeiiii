"""Minimal Evidence Verification Service (stdlib only).

Sessions bind a review cell to the identity of the patch actually served
(base_commit + patch_sha256), a served artifact id, and an evidence tier
('D' diagnostic / 'A' acceptance). The reviewer can READ artifact records and logs,
and can ask the service to verify four independent integrity surfaces:

  linkage      verify_artifact_linkage  record belongs to THIS patch & base commit
  freshness    check_evidence_freshness run tree equals the attested canonical tree
  coverage     check_test_coverage      executed test set covers the declared set
  consistency  check_claim_consistency  author claim vs real runner log markers

It cannot make a wrong record match by restating a hash or tree: the expected
identity/tree/sets are held in the session and the signed attestation store.

Tier gating: at the diagnostic tier, artifact records are projected (acceptance
outcomes removed) and f2p/p2p logs are NOT normally available. A reviewer may still
request them; the service serves the raw log but records an
`acceptance_log_reveal` audit event, so analysis can separate reviewers who verify
via freshness/coverage from those who simply escalate to the acceptance answer.

Phase-3 session policy (optional; omitted => legacy Phase-2 behaviour, byte-for-byte
compatible with the binary protocol):
  policy=strict    acceptance logs (f2p/p2p/p2p_baseline) return 403 and are
                   audited `denied_strict`; consistency is adjudicated ONLY from
                   authorised diagnostic evidence (the registered issue-symptom
                   probe) and never from hidden acceptance counts, so flipping the
                   hidden acceptance outcomes cannot change any strict response
                   (noninterference). A claim diagnostics cannot adjudicate returns
                   verdict `insufficient_evidence`.
  policy=escalate  acceptance logs AND acceptance-based consistency are available
                   only with a non-empty `reason` (query param for GET logs, JSON
                   body for consistency); missing/blank reason => 400; every grant
                   is audited with the reason and flagged X-Evidence-Tier-Escalation.

The fixture scenario label (phase2_scenario) is stripped from EVERY served payload.

Endpoints:
  POST /sessions                         {instance_id, base_commit, patch_sha256,
                                          cell?, served_artifact_id?, evidence_tier?,
                                          policy?, claim?, symptom?}
  GET  /sessions/{sid}/artifact[?artifact_id=...]
  GET  /sessions/{sid}/verify
  GET  /sessions/{sid}/freshness
  GET  /sessions/{sid}/coverage
  POST /sessions/{sid}/consistency       {claim is session-bound; reason? under
                                          policy=escalate}
  GET  /sessions/{sid}/log/{name}[?reason=...]
  GET  /healthz
"""
import json, re, secrets, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from .schemas import make_artifact_id
from .store import ArtifactStore
from . import views

# Claim classification for check_claim_consistency. Verdicts are taken from the
# normalised artifact record (not by scanning whole-file pytest logs, which contain
# unrelated/environment failures).
_POSITIVE_CLAIM_RE = re.compile(r'\b(pass(?:es|ed|ing)?|correct|works?|success'
                                r'|fixed|resolv)\b', re.I)
NEGATIVE_MARKERS = ('fail', 'error', 'broke', 'regress', 'doesn\'t work',
                    'does not work')

# Phase-3 session policies. None/absent means legacy Phase-2 behaviour.
POLICIES = ('strict', 'escalate')


def _symptom_fixed(symptom):
    """The issue-derived diagnostic probe (pilot builder polarity):
    pre_patch_passed=False  => the issue symptom IS present before the patch
    post_patch_passed=True  => the symptom does NOT reproduce after the patch
    A fix is symptom-supported only by the directed pair present->gone.
    Returns True (symptom supports a success claim), False (symptom reproduces
    after the patch and contradicts a success claim), or None (not adjudicable).
    """
    if not isinstance(symptom, dict):
        return None
    pre, post = symptom.get('pre_patch_passed'), symptom.get('post_patch_passed')
    if pre is None or post is None:
        return None
    present_before = pre is False
    gone_after = post is True
    still_reproduces = post is False
    if present_before and gone_after:
        return True
    if present_before and still_reproduces:
        return False
    return None


class _Handler(BaseHTTPRequestHandler):
    server_version = 'EvidenceAPI/2.0'

    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _audit(self, sid, action, params, result):
        entry = {'ts': time.time(), 'session': sid, 'action': action,
                 'params': params, 'result': result}
        with self.server.audit_lock:
            self.server.audit.append(entry)
            with open(self.server.audit_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                f.flush()

    def _served_artifact(self, sess, rec, authentic):
        """Single sanitisation chokepoint shared with the T2 static prompt block
        (views.display_for_tier): neutralise fixture labels at both tiers; at tier D
        substitute attestation-backed declared counts/files and project away all
        acceptance outcomes. Linkage/freshness are computed elsewhere from the
        record's real hashes, so display sanitisation never changes a verdict."""
        tier = sess.get('evidence_tier', 'A')
        projected = views.display_for_tier(self.server.store, rec,
                                           sess['instance_id'],
                                           sess['patch_sha256'], tier)
        return projected, authentic, tier

    # -- GET ---------------------------------------------------------------
    def do_GET(self):
        u = urlparse(self.path)
        parts = u.path.strip('/').split('/')
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == '/healthz':
            return self._send(200, {'ok': True})
        if len(parts) < 3 or parts[0] != 'sessions':
            return self._send(404, {'error': 'not found'})
        sid = parts[1]
        sess = self.server.sessions.get(sid)
        if sess is None:
            return self._send(404, {'error': 'unknown session'})
        store = self.server.store
        aid = q.get('artifact_id') or sess.get('served_artifact_id') \
            or make_artifact_id(sess['instance_id'], sess['patch_sha256'])
        action = parts[2]

        if action == 'artifact':
            got = store.get(aid)
            if got is None:
                self._audit(sid, 'artifact', {'artifact_id': aid}, 'missing')
                return self._send(404, {'error': 'unknown artifact_id'})
            projected, authentic, tier = self._served_artifact(sess, got[0], got[1])
            self._audit(sid, 'artifact', {'artifact_id': aid, 'tier': tier}, 'served')
            return self._send(200, {'artifact': projected,
                                    'authentic_signature': authentic,
                                    'evidence_tier': tier})

        if action == 'verify':
            link = store.check_linkage(aid, sess['base_commit'], sess['patch_sha256'])
            if link is None:
                self._audit(sid, 'verify', {'artifact_id': aid}, 'missing')
                return self._send(404, {'error': 'unknown artifact_id'})
            self._audit(sid, 'verify', {'artifact_id': aid},
                        'linked' if link['linked'] else 'mismatch')
            return self._send(200, link)

        if action == 'freshness':
            return self._freshness(sid, sess, aid)

        if action == 'coverage':
            return self._coverage(sid, sess, aid)

        if action == 'log' and len(parts) == 4:
            return self._log(sid, sess, aid, parts[3], q.get('reason'))

        return self._send(404, {'error': 'not found'})

    def _freshness(self, sid, sess, aid):
        """Canonical run tree comes from a signed attestation captured at build
        time for the SERVED patch; the artifact's run_tree is compared to it."""
        store = self.server.store
        got = store.get(aid)
        if got is None:
            self._audit(sid, 'freshness', {'artifact_id': aid}, 'missing')
            return self._send(404, {'error': 'unknown artifact_id'})
        rec, authentic = got
        att = store.get_attestation(sess['instance_id'], sess['patch_sha256'])
        if att is None:
            self._audit(sid, 'freshness', {'artifact_id': aid}, 'no_attestation')
            return self._send(404, {'error': 'no attestation for this review target'})
        base_match = rec.get('base_commit') == sess['base_commit']
        tree_match = rec.get('run_tree') == att['expected_run_tree']
        fresh = bool(authentic and att.get('_attestation_authentic')
                     and base_match and tree_match)
        out = {
            'authentic_signature': authentic,
            'attestation_authentic': att.get('_attestation_authentic'),
            'base_commit_match': base_match,
            'run_tree_match': tree_match,
            'fresh': fresh,
            'record_run_tree': rec.get('run_tree'),
            'expected_run_tree': att['expected_run_tree'],
            'artifact_started_at': rec.get('started_at'),
            'attestation_built_at': att.get('built_at'),
        }
        self._audit(sid, 'freshness', {'artifact_id': aid},
                    'fresh' if fresh else 'stale_or_mismatched')
        return self._send(200, out)

    def _coverage(self, sid, sess, aid):
        """Executed vs DECLARED test sets. Names/counts only — acceptance outcomes
        are never returned by this endpoint, even at tier A."""
        store = self.server.store
        got = store.get(aid)
        if got is None:
            self._audit(sid, 'coverage', {'artifact_id': aid}, 'missing')
            return self._send(404, {'error': 'unknown artifact_id'})
        rec, authentic = got
        att = store.get_attestation(sess['instance_id'], sess['patch_sha256'])
        if att is None:
            self._audit(sid, 'coverage', {'artifact_id': aid}, 'no_attestation')
            return self._send(404, {'error': 'no attestation for this review target'})
        f2p_exec = sorted((rec.get('fail_to_pass') or {}).keys())
        p2p_exec = sorted((rec.get('pass_to_pass_scoped') or {}).keys())
        f2p_decl = sorted(att['declared_fail_to_pass'])
        p2p_decl = sorted(att['declared_p2p_scoped'])
        f2p_missing = [n for n in f2p_decl if n not in f2p_exec]
        p2p_missing = [n for n in p2p_decl if n not in p2p_exec]
        extra_f2p = [n for n in f2p_exec if n not in f2p_decl]
        complete = not f2p_missing and not p2p_missing
        out = {
            'authentic_signature': authentic,
            'attestation_authentic': att.get('_attestation_authentic'),
            'fail_to_pass': {'declared': len(f2p_decl), 'executed': len(f2p_exec),
                             'missing_ids': f2p_missing, 'undeclared_executed': extra_f2p},
            'pass_to_pass_scoped': {'declared': len(p2p_decl), 'executed': len(p2p_exec),
                                    'missing_count': len(p2p_missing),
                                    'missing_ids_sample': p2p_missing[:20]},
            'complete': complete,
            'note': 'coverage compares executed test ids to the declared acceptance '
                    'set; it reports no pass/fail outcomes',
        }
        self._audit(sid, 'coverage', {'artifact_id': aid},
                    'complete' if complete else 'incomplete')
        return self._send(200, out)

    def _log(self, sid, sess, aid, name, reason=None):
        store = self.server.store
        lp = store.root / 'logs' / f'{aid}.{name}.log'
        if not lp.exists():
            self._audit(sid, 'log', {'artifact_id': aid, 'name': name}, 'missing')
            return self._send(404, {'error': 'unknown log'})
        tier = sess.get('evidence_tier', 'A')
        policy = sess.get('policy')
        accepted = views.log_allowed(name, tier)
        if accepted:
            self._audit(sid, 'log', {'artifact_id': aid, 'name': name, 'tier': tier},
                        'served')
            body = lp.read_text(encoding='utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('X-Evidence-Tier-Escalation', '0')
            self.end_headers()
            return self.wfile.write(body.encode('utf-8'))

        # Diagnostic request for an ACCEPTANCE verdict log.
        params = {'artifact_id': aid, 'name': name, 'tier': tier, 'policy': policy}
        if policy == 'strict':
            # Hard isolation: never read the body; tell the reviewer the channel
            # is unavailable under this policy.
            self._audit(sid, 'log', params, 'denied_strict')
            return self._send(403, {'error': 'acceptance logs are disabled under '
                                             'the strict evidence policy'})
        if policy == 'escalate':
            reason = (reason or '').strip()
            if not reason:
                self._audit(sid, 'log', params, 'escalation_reason_missing')
                return self._send(400, {'error': 'a non-empty reason is required to '
                                                 'escalate to acceptance logs'})
            params['reason'] = reason
            self._audit(sid, 'log', params, 'acceptance_log_reveal')
            body = lp.read_text(encoding='utf-8')
            banner = ('# TIER ESCALATION: this acceptance-test log reveals maintainer '
                      'verdict columns; your stated reason and this access are '
                      'recorded.\n')
            body = banner + body
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('X-Evidence-Tier-Escalation', '1')
            self.end_headers()
            return self.wfile.write(body.encode('utf-8'))

        # Legacy Phase-2 path (no policy): serve flagged, audited, no reason gate.
        self._audit(sid, 'log', params, 'acceptance_log_reveal')
        body = lp.read_text(encoding='utf-8')
        banner = ('# TIER ESCALATION: this acceptance-test log reveals maintainer '
                  'verdict columns; this access is recorded.\n')
        body = banner + body
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('X-Evidence-Tier-Escalation', '1')
        self.end_headers()
        return self.wfile.write(body.encode('utf-8'))

    # -- POST --------------------------------------------------------------
    def do_POST(self):
        u = urlparse(self.path)
        parts = u.path.strip('/').split('/')
        if u.path == '/sessions':
            return self._open_session()
        if len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'consistency':
            return self._consistency(parts[1])
        return self._send(404, {'error': 'not found'})

    def _open_session(self):
        n = int(self.headers.get('Content-Length', 0))
        try:
            data = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            return self._send(400, {'error': 'bad json'})
        need = ('instance_id', 'base_commit', 'patch_sha256')
        if any(k not in data for k in need):
            return self._send(400, {'error': 'missing fields'})
        tier = (data.get('evidence_tier') or 'A').upper()
        if tier not in views.TIERS:
            return self._send(400, {'error': 'evidence_tier must be D or A'})
        policy = data.get('policy')
        if policy is not None:
            policy = str(policy).lower()
            if policy not in POLICIES:
                return self._send(400, {'error': 'policy must be strict or escalate'})
        symptom = data.get('symptom')
        if symptom is not None and not isinstance(symptom, dict):
            return self._send(400, {'error': 'symptom must be an object'})
        sid = secrets.token_hex(12)
        true_aid = make_artifact_id(data['instance_id'], data['patch_sha256'])
        served = data.get('served_artifact_id') or true_aid
        self.server.sessions[sid] = {
            'instance_id': data['instance_id'], 'base_commit': data['base_commit'],
            'patch_sha256': data['patch_sha256'], 'cell': data.get('cell', ''),
            'served_artifact_id': served, 'evidence_tier': tier,
            # None => legacy Phase-2 binary behaviour; 'strict'/'escalate' opt in
            # to the Phase-3 isolation policies.
            'policy': policy,
            # The issue-derived diagnostic probe bound to the cell. This is the
            # ONLY acceptance-independent evidence strict consistency may use.
            'symptom': symptom,
            # The author claim under review is bound to the session at open time.
            # Cells without an author statement register none; the consistency
            # surface then refuses to evaluate ad-hoc claims (which would turn it
            # into a free acceptance oracle).
            'claim': (data.get('claim') or '').strip() or None,
        }
        self._audit(sid, 'session_open',
                    {'instance_id': data['instance_id'], 'cell': data.get('cell', ''),
                     'served_artifact_id': served, 'truly_linked': served == true_aid,
                     'evidence_tier': tier, 'policy': policy}, 'ok')
        self._send(201, {'session_id': sid, 'artifact_id': served,
                         'evidence_tier': tier, 'policy': policy})

    def _read_json_body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(n) if n else b''
        if not raw:
            return {}
        try:
            obj = json.loads(raw)
        except Exception:
            return None
        return obj if isinstance(obj, dict) else {}

    def _consistency(self, sid):
        """Check ONLY the author statement registered for this review session.

        Ad-hoc claims supplied in the request body are ignored: allowing a
        reviewer to invent "does everything pass?" as a claim would turn this
        surface into a free acceptance oracle. The body may carry `reason`,
        which is required to USE acceptance outcomes under policy=escalate.

        Three adjudication modes:
          * policy=strict (tier D): ONLY authorised diagnostic evidence (the
            registered issue-symptom probe) is consulted. Hidden acceptance
            counts are never read, so the verdict is independent of hidden
            acceptance outcomes (noninterference). A claim diagnostics cannot
            adjudicate -> `insufficient_evidence`.
          * policy=escalate (tier D): acceptance-based adjudication is allowed
            only with a non-empty reason, audited `consistency_escalation`.
          * no policy (legacy binary) OR tier A: the Phase-2 behaviour —
            normalised acceptance/regression verdicts, qualitative-only at D.
        """
        sess = self.server.sessions.get(sid)
        if sess is None:
            return self._send(404, {'error': 'unknown session'})
        claim = sess.get('claim')
        if not claim:
            self._audit(sid, 'consistency', {}, 'no_registered_claim')
            return self._send(409, {'error': 'no author statement is part of this '
                                             'review cell; consistency is not '
                                             'available'})
        aid = sess.get('served_artifact_id')
        store = self.server.store
        got = store.get(aid)
        if got is None:
            self._audit(sid, 'consistency', {'artifact_id': aid}, 'missing')
            return self._send(404, {'error': 'unknown artifact_id'})
        rec = got[0]
        tier = sess.get('evidence_tier', 'A')
        policy = sess.get('policy')
        claim_positive = bool(_POSITIVE_CLAIM_RE.search(claim))
        claim_negative = any(k in claim.lower() for k in NEGATIVE_MARKERS)

        # ---- strict: diagnostic symptom probe only (no hidden outcomes) ----
        if policy == 'strict' and tier == 'D':
            fixed = _symptom_fixed(sess.get('symptom'))
            if fixed is False and claim_positive and not claim_negative:
                verdict = 'contradicted'
                why = ('the registered positive claim is contradicted by the '
                       'authorised diagnostic evidence: the issue symptom still '
                       'reproduces after the patch (reproduction probe fails)')
            elif fixed is True and claim_positive:
                verdict = 'consistent'
                why = ('the authorised diagnostic evidence supports the claim at '
                       'issue level: the reported symptom no longer reproduces; '
                       'maintainer acceptance outcomes are not adjudicated under '
                       'the strict policy')
            elif fixed is False and not claim_positive:
                verdict = 'consistent'
                why = ('the claim does not assert success and the diagnostic '
                       'probe shows the symptom still reproduces')
            else:
                verdict = 'insufficient_evidence'
                why = ('the authorised diagnostic evidence (issue-symptom probe) '
                       'cannot adjudicate this claim; maintainer acceptance '
                       'outcomes are not available under the strict policy')
            out = {'verdict': verdict, 'reason': why}
            self._audit(sid, 'consistency',
                        {'artifact_id': aid, 'policy': policy, 'basis': 'symptom'},
                        verdict)
            return self._send(200, out)

        # ---- escalate: reason gate before acceptance outcomes at tier D ----
        reason = None
        if policy == 'escalate' and tier == 'D':
            body = self._read_json_body()
            if body is None:
                return self._send(400, {'error': 'bad json'})
            reason = (body.get('reason') or '').strip() if isinstance(body, dict) else ''
            if not reason:
                self._audit(sid, 'consistency',
                            {'artifact_id': aid, 'policy': policy},
                            'escalation_reason_missing')
                return self._send(400, {'error': 'a non-empty reason is required to '
                                                 'escalate consistency to acceptance '
                                                 'outcomes'})

        # ---- acceptance-based adjudication (legacy / tier A / escalated) ----
        summ = rec.get('summary') or {}
        n_f2p_fail = len(summ.get('f2p_failed_ids') or [])
        n_p2p_regr = len(summ.get('p2p_regressed_ids') or [])
        n_exec = len(rec.get('fail_to_pass') or {}) + len(
            rec.get('pass_to_pass_scoped') or {})
        bad = n_f2p_fail + n_p2p_regr
        if bad and claim_positive and not claim_negative:
            verdict = 'contradicted'
            why_d = ('the registered positive claim is contradicted by the '
                     'normalised acceptance/regression verdicts of this artifact')
            why_a = ('claim asserts success; the artifact records '
                     f'{n_f2p_fail} failed acceptance and {n_p2p_regr} regression '
                     'checks')
        elif bad:
            verdict = 'consistent'
            why_d = 'the claim does not deny the failures recorded by the artifact'
            why_a = 'the artifact records failures and the claim does not deny them'
        elif n_exec == 0:
            verdict = 'unverifiable'
            why_d = 'no acceptance/regression checks were executed for this artifact'
            why_a = why_d
        else:
            verdict = 'consistent'
            why_d = 'the claim is consistent with the normalised verdicts of this ' \
                    'artifact'
            why_a = 'executed acceptance/regression checks show no failure'
        out = {'verdict': verdict, 'reason': why_d if tier == 'D' else why_a}
        if tier == 'A':
            out.update({'failed_acceptance_checks': n_f2p_fail,
                        'regression_checks': n_p2p_regr,
                        'executed_checks': n_exec})
        if policy == 'escalate' and tier == 'D':
            # mark and audit the escalation so answer-peeking via consistency is
            # never free or silent
            out['escalated'] = True
            self._audit(sid, 'consistency',
                        {'artifact_id': aid, 'policy': policy,
                         'basis': 'acceptance', 'reason': reason},
                        'consistency_escalation:' + verdict)
        else:
            self._audit(sid, 'consistency', {'artifact_id': aid}, verdict)
        return self._send(200, out)


def build_server(store_root, host='127.0.0.1', port=0):
    from pathlib import Path
    store = ArtifactStore(store_root)
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.store = store
    httpd.sessions = {}
    httpd.audit = []
    httpd.audit_lock = threading.Lock()
    httpd.audit_path = str(Path(store_root) / 'audit.jsonl')
    return httpd

def serve_forever(store_root, host='127.0.0.1', port=8321):
    httpd = build_server(store_root, host, port)
    print(f'evidence API on http://{host}:{httpd.server_address[1]} root={store_root}')
    print(f'audit log appended live to {httpd.audit_path}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default='evidence_store')
    ap.add_argument('--port', type=int, default=8321)
    a = ap.parse_args()
    serve_forever(a.root, port=a.port)
