"""G3-C.1 task 5 (part 2) — Gate 3-C local HTTP evidence server, $0.

Subclasses the FROZEN evidence.server._Handler WITHOUT editing it, and
overrides exactly two chokepoints:

  1. _served_artifact: tier D output is additionally passed through the FROZEN
     G3-C.0 projection v2 wrapper (g3c0_projection_v2.project_diagnostic_v2),
     which removes the redundant pass_to_pass_baseline map and tags
     projection_version. Tier A is returned byte-for-byte as the frozen view.

  2. _freshness: the FROZEN pure three-state adjudicator
     (g3b2_freshness.adjudicate_freshness) is reused verbatim, but the
     authoritative tree is the G3-C.1 independent restage cache
     (audit/g3c1_freshness_recompute.json) and the protocol tag is the G3-C.1
     protocol version. A missing run_tree is UNKNOWN, never FALSE.

All linkage / coverage / consistency / log gating (strict 403, escalate
400->200 reason-gated, tier A free) is inherited unchanged.

Serve ONLY against a tempdir copytree of the G3-C.1 store (serving appends
audit.jsonl); the built store tree stays pristine for freezing.
"""
from __future__ import annotations

import threading
from http.server import ThreadingHTTPServer

from evidence import server as frozen_server
from evidence import g3b2_freshness as F
from evidence.g3c0_projection_v2 import project_diagnostic_v2
from evidence.store import ArtifactStore

from evidence import g3c1_common as C
from evidence.g3c1_freshness import load_restage_cache


class G3C1Handler(frozen_server._Handler):
    server_version = 'EvidenceAPI/g3c1-v1'

    # -- override 1: projection v2 at the diagnostic tier only --------------
    def _served_artifact(self, sess, rec, authentic):
        projected, authentic, tier = super()._served_artifact(
            sess, rec, authentic)
        if tier == 'D':
            projected = project_diagnostic_v2(projected)
        return projected, authentic, tier

    # -- override 2: three-state freshness keyed to the G3-C.1 restage -----
    def _freshness(self, sid, sess, aid):
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

        cache = getattr(self.server, 'g3c1_restage_cache', None) or \
            load_restage_cache()
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
        # Same pure three-state logic; G3-C.1 protocol/projection tagging.
        out['protocol_version'] = C.G3C1_PROTOCOL_VERSION

        state = out['fresh_state']
        if state == F.FRESH_TRUE:
            audit_result = 'true'
        elif state == F.FRESH_FALSE:
            audit_result = 'false:' + str(out.get('status_reason'))
        else:
            audit_result = 'unknown:' + str(out.get('status_reason'))
        self._audit(sid, 'freshness',
                    {'artifact_id': aid,
                     'protocol_version': C.G3C1_PROTOCOL_VERSION},
                    audit_result)
        return self._send(200, out)


def build_g3c1_server(store_root, host='127.0.0.1', port=0, *,
                      restage_cache: dict | None = None,
                      fixtures_meta_name: str = 'g3c1_fixtures_meta.json'):
    """Independent factory. Caller must pass a tempdir COPY of the store."""
    store_root = str(store_root)
    store = ArtifactStore(store_root, fixtures_meta_name=fixtures_meta_name)
    httpd = ThreadingHTTPServer((host, port), G3C1Handler)
    httpd.store = store
    httpd.sessions = {}
    httpd.audit = []
    httpd.audit_lock = threading.Lock()
    httpd.audit_path = str(__import__('pathlib').Path(store_root)
                           / 'audit.jsonl')
    httpd.g3c1_restage_cache = (
        restage_cache if restage_cache is not None else load_restage_cache())
    httpd.g3c1_protocol_version = C.G3C1_PROTOCOL_VERSION
    return httpd
