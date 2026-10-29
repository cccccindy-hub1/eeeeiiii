"""Gate 3-B.2 (task 2) — ternary freshness adjudication, independent protocol.

G3-B.1 construct audit finding #1: the live freshness endpoint compared a
``run_tree`` field that the canonical artifact record does not carry
(``rec.get('run_tree')`` -> None) against the signed attestation's
``expected_run_tree``.  The comparison therefore ALWAYS failed and every
active-condition cell was served ``fresh=false``, even though the independent
G3-A git-restage recomputation (evidence_store_g3a/audit/
g3a_freshness_recompute.json) found 10/10 tree identity.  A missing field was
silently coerced into a substantive *stale* verdict — a structural false
negative that contradicted the Gold-side freshness source of truth.

This module implements the repaired, AUDITABLE three-state verdict:

  TRUE             — authentic artifact signature AND authentic attestation
                     signature AND base_commit matches AND an authoritative
                     restaged run tree equals the attested expected_run_tree.
  FALSE            — a present, comparable tree genuinely differs from the
                     attested tree (real stale/mismatched triple).
  UNKNOWN          — the verdict cannot be adjudicated from the served record.
                     ``status_reason`` carries the sub-state:
                       schema_error_record_run_tree_missing
                       schema_error_record_run_tree_wrong_type
                       attestation_missing
                       attestation_signature_invalid
                       artifact_signature_invalid
                       base_commit_mismatch
                       restage_unavailable
                       patch_mismatch

CRITICAL: a missing ``run_tree`` is NEVER folded into FALSE.  It is
UNKNOWN/SCHEMA_ERROR.  The authoritative tree is the independently restaged
git tree (preferring the frozen G3-A recomputation cache; falling back to
``g3a_freshness_check.restage_tree`` against an explicit raw row), not the
absent record field.  Nothing here edits any frozen file or store.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence import g3b2_common as C

# Public verdict constants.
FRESH_TRUE = 'TRUE'
FRESH_FALSE = 'FALSE'
FRESH_UNKNOWN = 'UNKNOWN'

# Sub-state reasons (status_reason). Never collide with a boolean stale verdict.
REASON_TREE_MISMATCH = 'tree_mismatch'
REASON_RECORD_FIELD_MISSING = 'schema_error_record_run_tree_missing'
REASON_RECORD_FIELD_WRONG_TYPE = 'schema_error_record_run_tree_wrong_type'
REASON_ATTESTATION_MISSING = 'attestation_missing'
REASON_ATTESTATION_SIG_INVALID = 'attestation_signature_invalid'
REASON_ARTIFACT_SIG_INVALID = 'artifact_signature_invalid'
REASON_BASE_MISMATCH = 'base_commit_mismatch'
REASON_RESTAGE_UNAVAILABLE = 'restage_unavailable'
REASON_PATCH_MISMATCH = 'patch_mismatch'


def load_restage_cache(path: Path | None = None) -> dict:
    """Load the frozen independent G3-A restage recomputation.

    Returns {instance_id: issue_dict}. This is the preferred authoritative
    tree source: it was produced by an independent ``git write-tree`` of the
    exact (base + candidate patch + maintainer test_patch) triple and is
    itself under the G3-A frozen hash manifest.
    """
    path = path or C.G3A_FRESHNESS_CACHE
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    return {x['instance_id']: x for x in payload.get('issues', [])}


def _record_run_tree_state(rec: dict) -> tuple[str | None, str | None]:
    """Inspect the OPTIONAL record run_tree field without coercing absence.

    Returns (value_or_None, reason_or_None).
    Absent/None  -> (None, schema_error_record_run_tree_missing)
    Wrong type   -> (None, schema_error_record_run_tree_wrong_type)
    Present str  -> (value, None)
    """
    if 'run_tree' not in rec or rec.get('run_tree') is None:
        return None, REASON_RECORD_FIELD_MISSING
    val = rec.get('run_tree')
    if not isinstance(val, str) or not val.strip():
        return None, REASON_RECORD_FIELD_WRONG_TYPE
    return val.strip(), None


def adjudicate_freshness(*, rec, authentic, att, sess,
                         restaged_tree: str | None = None,
                         record_tree_override=None,
                         patch_match: bool | None = None) -> dict:
    """Pure three-state freshness adjudication.

    Parameters
    ----------
    rec : dict            canonical artifact record (as served by store.get)
    authentic : bool      artifact record signature authenticity (store.get)
    att : dict | None     signed attestation (store.get_attestation), or None
    sess : dict           review session binding (instance_id/base_commit/...)
    restaged_tree :       authoritative independently-restaged run tree for
                          this triple, or None when no restage is available.
    record_tree_override: test hook — simulate a present record.run_tree.
    patch_match :         explicit patch_sha256 linkage; when False the triple
                          is a genuine patch mismatch (FALSE). None => infer
                          from session/attestation identity rather than assert.
    """
    rec = dict(rec or {})
    if record_tree_override is not None:
        rec['run_tree'] = record_tree_override

    result = {
        'protocol_version': C.PROTOCOL_VERSION,
        'authentic_signature': bool(authentic),
        'attestation_authentic': bool(att and att.get('_attestation_authentic')),
        'base_commit_match': rec.get('base_commit') == sess.get('base_commit'),
        'record_run_tree': rec.get('run_tree'),
        'record_run_tree_present': isinstance(rec.get('run_tree'), str)
                                    and bool(rec.get('run_tree')),
        'expected_run_tree': (att or {}).get('expected_run_tree'),
        'authoritative_tree_source': None,
        'authoritative_run_tree': restaged_tree,
        'run_tree_match': None,
        'fresh': None,                 # three-state: true / false / null
        'fresh_state': FRESH_UNKNOWN,  # TRUE / FALSE / UNKNOWN
        'status_reason': None,
        'artifact_started_at': rec.get('started_at'),
        'attestation_built_at': (att or {}).get('built_at'),
        'note': 'three-state freshness: null fresh means UNKNOWN, not stale',
    }

    # --- hard signature / linkage failures => FALSE (genuine, adjudicated) ---
    if att is None:
        result['status_reason'] = REASON_ATTESTATION_MISSING
        result['fresh_state'] = FRESH_UNKNOWN
        return result
    if not authentic:
        result['status_reason'] = REASON_ARTIFACT_SIG_INVALID
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['run_tree_match'] = False
        return result
    if not att.get('_attestation_authentic'):
        result['status_reason'] = REASON_ATTESTATION_SIG_INVALID
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['run_tree_match'] = False
        return result
    if not result['base_commit_match']:
        result['status_reason'] = REASON_BASE_MISMATCH
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['run_tree_match'] = False
        return result
    if patch_match is False:
        result['status_reason'] = REASON_PATCH_MISMATCH
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['run_tree_match'] = False
        return result

    expected = att.get('expected_run_tree')

    # --- authoritative tree: independent restage preferred -------------------
    if restaged_tree:
        result['authoritative_tree_source'] = (
            'independent_git_restage_write_tree')
        match = restaged_tree == expected
        result['run_tree_match'] = match
        if match:
            result['fresh_state'] = FRESH_TRUE
            result['fresh'] = True
            result['status_reason'] = 'authoritative_restage_tree_matches_attestation'
            return result
        # A real, comparable restaged tree that differs is a genuine FALSE.
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['status_reason'] = REASON_TREE_MISMATCH
        return result

    # --- no independent restage available: fall back to record field ---------
    rec_tree, field_reason = _record_run_tree_state(rec)
    if rec_tree is None:
        # THE G3-B BUG: absence must NOT become false.
        result['fresh_state'] = FRESH_UNKNOWN
        result['fresh'] = None
        result['run_tree_match'] = None
        result['status_reason'] = field_reason
        return result

    result['authoritative_tree_source'] = 'record_run_tree_field'
    match = rec_tree == expected
    result['run_tree_match'] = match
    if match:
        result['fresh_state'] = FRESH_TRUE
        result['fresh'] = True
        result['status_reason'] = 'record_tree_matches_attestation'
    else:
        result['fresh_state'] = FRESH_FALSE
        result['fresh'] = False
        result['status_reason'] = REASON_TREE_MISMATCH
    return result


def adjudicate_for_session(store, sess, aid, *, restage_cache: dict | None = None,
                           restage_fn=None, raw_row=None) -> dict:
    """Build a full three-state verdict using a live/temp store + session.

    ``restage_fn(raw) -> tree`` may be passed for tests; by default the frozen
    G3-A recomputation cache is the authoritative source. If the cache has no
    entry and no restage_fn is supplied, restaged_tree stays None and the
    verdict falls through to record-field handling (which yields UNKNOWN on a
    missing field, never FALSE).
    """
    got = store.get(aid)
    if got is None:
        return {'fresh_state': FRESH_UNKNOWN, 'fresh': None,
                'status_reason': 'artifact_missing', 'http_status': 404}
    rec, authentic = got
    att = store.get_attestation(sess['instance_id'], sess['patch_sha256'])

    restaged_tree = None
    cache = restage_cache if restage_cache is not None else load_restage_cache()
    hit = cache.get(sess['instance_id'])
    if hit and hit.get('tree_matches') is not None:
        # Use the independent recomputation only when it itself was authentic.
        if hit.get('attestation_authentic'):
            restaged_tree = hit.get('recomputed_run_tree')
    if restaged_tree is None and restage_fn is not None and raw_row is not None:
        restaged_tree = restage_fn(raw_row)

    linkage = store.check_linkage(aid, sess['base_commit'], sess['patch_sha256'])
    patch_match = bool(linkage and linkage.get('patch_sha256_match'))

    out = adjudicate_freshness(
        rec=rec, authentic=authentic, att=att, sess=sess,
        restaged_tree=restaged_tree, patch_match=patch_match)
    out['http_status'] = 200
    return out


def audit_all_ten(store, sessions_by_iid: dict, aid_by_iid: dict,
                  restage_cache: dict | None = None) -> dict:
    """Offline audit of the 10 frozen issues against the repaired endpoint."""
    cache = restage_cache or load_restage_cache()
    rows = []
    n_true = n_false = n_unknown = 0
    for iid in sorted(cache):
        if iid not in sessions_by_iid:
            continue
        v = adjudicate_for_session(
            store, sessions_by_iid[iid], aid_by_iid[iid], restage_cache=cache)
        rows.append({'instance_id': iid,
                     'fresh_state': v.get('fresh_state'),
                     'fresh': v.get('fresh'),
                     'run_tree_match': v.get('run_tree_match'),
                     'status_reason': v.get('status_reason'),
                     'authoritative_tree_source': v.get(
                         'authoritative_tree_source'),
                     'record_run_tree_present': v.get(
                         'record_run_tree_present')})
        n_true += v.get('fresh_state') == FRESH_TRUE
        n_false += v.get('fresh_state') == FRESH_FALSE
        n_unknown += v.get('fresh_state') == FRESH_UNKNOWN
    return {'protocol_version': C.PROTOCOL_VERSION,
            'n': len(rows), 'n_true': n_true, 'n_false': n_false,
            'n_unknown': n_unknown, 'issues': rows}
