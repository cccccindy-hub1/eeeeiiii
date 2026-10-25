"""Immutable artifact store.

Layout (under ARTIFACT_DIR):
  artifacts/{artifact_id}.json      signed artifact record (public, readable in T2/T3)
  logs/{artifact_id}.{name}.log     raw runner logs (hashes committed into the record)
  signatures/{artifact_id}.sig      HMAC over the canonical artifact bytes (server secret)
  truth.jsonl                       three-label ground truth (NEVER shown to a model)

Tamper/mismatch fixtures (pilot only) are written via insert_mismatch(): the record
carries a *different* patch_sha256 than the served patch, and the verify endpoint must
report linked=false. Provenance is kept in private metadata, never in the prompt.
"""
from __future__ import annotations

import hmac, json, os, secrets
from pathlib import Path

from .schemas import (SCHEMA_VERSION, canonical_dumps, make_artifact_id,
                      sha256_text, validate_artifact)

class ArtifactStore:
    def __init__(self, root, secret=None, fixtures_meta_name='fixtures_meta.json'):
        self.root = Path(root)
        # Wave-2 builds pass a separate meta filename so the frozen Wave-1
        # fixtures_meta.json is never touched; the default stays byte-identical.
        self.fixtures_meta_name = fixtures_meta_name
        (self.root / 'artifacts').mkdir(parents=True, exist_ok=True)
        (self.root / 'logs').mkdir(parents=True, exist_ok=True)
        (self.root / 'signatures').mkdir(parents=True, exist_ok=True)
        self._secret = secret or os.environ.get('EVIDENCE_API_SECRET')
        if not self._secret:
            # generated per-store, stable for the lifetime of this pilot store
            sf = self.root / 'server_secret'
            if sf.exists():
                self._secret = sf.read_text().strip()
            else:
                self._secret = secrets.token_hex(32)
                sf.write_text(self._secret)

    # -- internal paths ----------------------------------------------------
    def _art_path(self, aid): return self.root / 'artifacts' / f'{aid}.json'
    def _sig_path(self, aid): return self.root / 'signatures' / f'{aid}.sig'
    def _log_path(self, aid, name): return self.root / 'logs' / f'{aid}.{name}.log'

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret.encode(), body, 'sha256').hexdigest()

    def verify_signature(self, rec: dict, sig: str) -> bool:
        body = canonical_dumps(rec).encode()
        return hmac.compare_digest(self.sign(body), sig or '')

    # -- write -------------------------------------------------------------
    def put(self, rec: dict, logs: dict | None = None):
        """Store + sign an artifact. `logs` is {name: text}; digests must already
        match rec['log_digests']; this function does not fabricate anything."""
        validate_artifact(rec)
        aid = rec['artifact_id']
        for name, text in (logs or {}).items():
            with open(self._log_path(aid, name), 'w', encoding='utf-8', newline='') as fh:
                fh.write(text)
        body = canonical_dumps(rec).encode()
        self._art_path(aid).write_bytes(body)
        self._sig_path(aid).write_text(self.sign(body))
        return aid

    def insert_mismatch(self, rec: dict, claimed_for_patch_sha: str,
                        mismatch_kind: str = 'different_patch') -> str:
        """Private pilot fixture: re-id the SAME artifact record as if it belonged to
        another patch, without recomputing linkage. Returns the new artifact_id.

        The HMAC stays valid (the record is internally consistent), so only an actual
        linkage check against the served patch can expose the mismatch. Provenance is
        returned to the experimenter and stored in mismatch_meta.json, never served.
        """
        import copy
        bad = copy.deepcopy(rec)
        bad['artifact_id'] = make_artifact_id(bad['instance_id'], claimed_for_patch_sha)
        # leave base_commit/patch_sha256 pointing at the ORIGINAL run: that is the
        # stale/wrong evidence a reviewer must catch
        bad['mismatch_note'] = mismatch_kind  # visible to reviewer in T2/T3? no:
        bad.pop('mismatch_note')
        body = canonical_dumps(bad).encode()
        self._art_path(bad['artifact_id']).write_bytes(body)
        self._sig_path(bad['artifact_id']).write_text(self.sign(body))
        meta_f = self.root / 'mismatch_meta.json'
        meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
        meta[bad['artifact_id']] = {
            'true_artifact_id': rec['artifact_id'],
            'claimed_for_patch_sha256': claimed_for_patch_sha,
            'record_patch_sha256': bad['patch_sha256'],
            'kind': mismatch_kind,
        }
        meta_f.write_text(json.dumps(meta, indent=2))
        return bad['artifact_id']

    # -- Phase 2 controlled fixtures ---------------------------------------
    def put_fixture(self, rec: dict, logs: dict | None = None,
                    meta: dict | None = None) -> str:
        """Store a signed Phase-2 scenario artifact.

        Unlike put(), fixtures are NOT required to satisfy
        artifact_id == make_artifact_id(instance, patch): wrong_patch fixtures are
        deliberately re-identified. Integrity is enforced differently: every stored
        log must hash to rec['log_digests'], the record is HMAC-signed, and the true
        provenance lives in fixtures_meta.json (experimenter-only, never served).
        """
        aid = rec['artifact_id']
        for name, text in (logs or {}).items():
            digest = (rec.get('log_digests') or {}).get(name)
            if digest is not None and sha256_text(text) != digest:
                raise ValueError(f'fixture {aid}: log digest mismatch for {name}')
            with open(self._log_path(aid, name), 'w', encoding='utf-8', newline='') as fh:
                fh.write(text)
        body = canonical_dumps(rec).encode()
        self._art_path(aid).write_bytes(body)
        self._sig_path(aid).write_text(self.sign(body))
        if meta:
            mf = self.root / self.fixtures_meta_name
            allm = json.loads(mf.read_text()) if mf.exists() else {}
            allm[aid] = meta
            mf.write_text(json.dumps(allm, indent=2, ensure_ascii=False))
        return aid

    def fixtures_meta(self) -> dict:
        mf = self.root / self.fixtures_meta_name
        return json.loads(mf.read_text()) if mf.exists() else {}

    # -- run-tree / coverage attestations (freshness & coverage truth) -----
    def _att_dir(self):
        d = self.root / 'attestations'
        d.mkdir(parents=True, exist_ok=True)
        return d

    def put_attestation(self, rec: dict) -> str:
        """Independent signed attestation of the CANONICAL run tree and the declared
        acceptance/regression sets for a review target (instance, patch). Captured from
        real `git write-tree` at build time, never derived from a scenario label.

        Required fields: instance_id, patch_sha256, base_commit, expected_run_tree,
        declared_fail_to_pass (list), declared_p2p_scoped (list), built_at.
        """
        need = ('instance_id', 'patch_sha256', 'base_commit', 'expected_run_tree',
                'declared_fail_to_pass', 'declared_p2p_scoped', 'built_at')
        miss = [k for k in need if k not in rec]
        if miss:
            raise ValueError('attestation missing: ' + ', '.join(miss))
        key = make_artifact_id(rec['instance_id'], rec['patch_sha256'])
        body = canonical_dumps(rec).encode()
        (self._att_dir() / f'{key}.json').write_bytes(body)
        (self.root / 'signatures' / f'{key}.att.sig').write_text(self.sign(body))
        return key

    def get_attestation(self, instance_id: str, patch_sha256: str):
        key = make_artifact_id(instance_id, patch_sha256)
        jp = self._att_dir() / f'{key}.json'
        sp = self.root / 'signatures' / f'{key}.att.sig'
        if not jp.exists():
            return None
        rec = json.loads(jp.read_text(encoding='utf-8'))
        sig = sp.read_text() if sp.exists() else ''
        rec['_attestation_authentic'] = self.verify_signature(rec, sig)
        return rec

    # -- read --------------------------------------------------------------
    def get(self, artifact_id: str):
        p = self._art_path(artifact_id)
        if not p.exists(): return None
        rec = json.loads(p.read_text(encoding='utf-8'))
        sig = self._sig_path(artifact_id).read_text() if self._sig_path(artifact_id).exists() else ''
        authentic = self.verify_signature(rec, sig)
        return rec, authentic

    def check_linkage(self, artifact_id: str, base_commit: str, patch_sha256: str):
        got = self.get(artifact_id)
        if got is None: return None
        rec, authentic = got
        return {
            'authentic_signature': authentic,
            'base_commit_match': rec['base_commit'] == (base_commit or ''),
            'patch_sha256_match': rec['patch_sha256'] == (patch_sha256 or ''),
            'linked': authentic
                      and rec['base_commit'] == (base_commit or '')
                      and rec['patch_sha256'] == (patch_sha256 or ''),
            'record_base_commit': rec['base_commit'],
            'record_patch_sha256': rec['patch_sha256'],
        }

    def list_ids(self):
        return sorted(p.stem for p in (self.root / 'artifacts').glob('*.json'))
