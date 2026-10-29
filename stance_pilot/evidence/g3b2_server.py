"""Gate 3-B.2 (task 2/5/7) — repaired HTTP evidence server, independent build.

Subclasses the FROZEN ``evidence.server._Handler`` and overrides ONLY the
freshness endpoint with the three-state adjudication from g3b2_freshness.
No frozen source file is modified; linkage / coverage / consistency / log
gating (strict 403, escalate 400->200 reason-gated, tier A free) are inherited
unchanged, so the repaired endpoint can be proven byte-compatible in its
gating behaviour while fixing only the structural freshness false-negative.

The independent restage cache is attached to the server and used as the
authoritative tree source. This factory MUST be pointed at a tempdir copy of
the store — never at the frozen G3-A store — because serving appends an
audit.jsonl.
"""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

from evidence import server as frozen_server
from evidence import g3b2_freshness as F
from evidence import g3b2_common as C
from evidence.store import ArtifactStore


class G3B2Handler(frozen_server._Handler):
    server_version = 'EvidenceAPI/g3b2-v1'

    def _freshness(self, sid, sess, aid):
        """Three-state freshness.

        Wires the independent restage cache (authoritative git write-tree
        identity) into the verdict. A record missing run_tree is reported as
        fresh=null / fresh_state=UNKNOWN / status_reason=
        schema_error_record_run_tree_missing — it is NEVER served as
        fresh=false. Authenticity or genuine tree mismatch remain FALSE.
        """
        store = self.server.store
        got = store.get(aid)
        if got is None:
            self._audit(sid, 'freshness', {'artifact_id': aid}, 'missing')
            return self._send(404, {'error': 'unknown artifact_id'})
        rec, authentic = got
        att = store.get_attestation(sess['instance_id'], sess['patch_sha256'])
        if att is None:
            self._audit(sid, 'freshness', {'artifact_id': aid},
                        'no_attestation')
            return self._send(404,
                              {'error': 'no attestation for this review target'})

        cache = getattr(self.server, 'g3b2_restage_cache', None) or \
            F.load_restage_cache()
        restaged_tree = None
        hit = cache.get(sess['instance_id'])
        if hit and hit.get('attestation_authentic'):
            restaged_tree = hit.get('recomputed_run_tree')

        linkage = store.check_linkage(aid, sess['base_commit'],
                                      sess['patch_sha256'])
        patch_match = bool(linkage and linkage.get('patch_sha256_match'))

        out = F.adjudicate_freshness(
            rec=rec, authentic=authentic, att=att, sess=sess,
            restaged_tree=restaged_tree, patch_match=patch_match)

        state = out['fresh_state']
        if state == F.FRESH_TRUE:
            audit_result = 'true'
        elif state == F.FRESH_FALSE:
            audit_result = 'false:' + str(out.get('status_reason'))
        else:
            audit_result = 'unknown:' + str(out.get('status_reason'))
        self._audit(sid, 'freshness',
                    {'artifact_id': aid, 'protocol_version': C.PROTOCOL_VERSION},
                    audit_result)
        return self._send(200, out)


def build_g3b2_server(store_root, host='127.0.0.1', port=0, *,
                      restage_cache: dict | None = None,
                      fixtures_meta_name: str = 'g3a_fixtures_meta.json'):
    """Independent factory. Caller is responsible for passing a tempdir copy."""
    store_root = str(store_root)
    store = ArtifactStore(store_root, fixtures_meta_name=fixtures_meta_name)
    httpd = ThreadingHTTPServer((host, port), G3B2Handler)
    httpd.store = store
    httpd.sessions = {}
    httpd.audit = []
    httpd.audit_lock = threading.Lock()
    httpd.audit_path = str(Path(store_root) / 'audit.jsonl')
    httpd.g3b2_restage_cache = (
        restage_cache if restage_cache is not None else F.load_restage_cache())
    httpd.g3b2_protocol_version = C.PROTOCOL_VERSION
    return httpd
