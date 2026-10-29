"""Gate 3-B.2 (task 3) — five-scenario unit tests for ternary freshness.

Fully offline; synthetic tempdir ArtifactStore; never touches the frozen
G3-A store; no model/API request. Explicit expected outcomes (NEVER
"make everything fresh=true"):

  S1 tree_match                 -> TRUE,  fresh=true,  run_tree_match=true
  S2 genuine_tree_mismatch      -> FALSE, fresh=false, tree_mismatch
  S3 record_run_tree_missing    -> UNKNOWN, fresh=null,
                                   schema_error_record_run_tree_missing
                                  (THE G3-B structural false-negative fix:
                                   absence must NOT collapse to stale/false)
  S4 signature_invalid          -> FALSE, *_signature_invalid (artifact-sig
                                   and attestation-sig variants)
  S5 patch_mismatch             -> FALSE, patch_mismatch

Also asserts the OLD boolean comparison (rec.get('run_tree') == expected)
would indeed be False on S1, confirming the audit's causal claim that the
missing field drove the false negatives.

Run: uv run --python 3.13 -m evidence.g3b2_freshness_test
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from evidence.schemas import make_artifact_id, canonical_dumps
from evidence.store import ArtifactStore
from evidence import g3b2_freshness as F

IID = 'synthetic__g3b2-freshness-test'
REPO = 'synthetic/repo'
BASE = 'b' * 40
PATCH = 'p' * 64
PATCH_OTHER = 'q' * 64
TEST_PATCH = 't' * 64
TREE_GOOD = 'tree-good-' + 'a' * 31
TREE_OTHER = 'tree-other-' + 'z' * 30

FAILURES = []


def check(name, cond, detail=''):
    status = 'PASS' if cond else 'FAIL'
    print(f'[{status}] {name}' + (f' :: {detail}' if detail and not cond else ''))
    if not cond:
        FAILURES.append(name)


def make_record(*, base=BASE, patch=PATCH):
    aid = make_artifact_id(IID, patch)
    return {
        'artifact_id': aid,
        'schema_version': '1.0',
        'instance_id': IID,
        'repo': REPO,
        'base_commit': base,
        'patch_sha256': patch,
        'test_patch_sha256': TEST_PATCH,
        'runner': 'synthetic/g3b2',
        'started_at': '2026-10-27T00:00:00+00:00',
        'finished_at': '2026-10-27T00:00:01+00:00',
        'scope': {'rule': 'synthetic', 'test_patch_applied_cleanly': True,
                  'p2p_total_in_dataset': 1,
                  'p2p_scoped_files': ['tests/test_x.py']},
        'fail_to_pass': {'test_f2p': 'PASSED'},
        'pass_to_pass_scoped': {'test_p2p': 'PASSED'},
        'pass_to_pass_baseline': {'test_p2p': 'PASSED'},
        'summary': {'f2p_total': 1, 'p2p_total': 1,
                    'outcomes_withheld': False},
        'log_digests': {},
        'evidence_tier': 'acceptance',
    }


def make_attestation(*, tree=TREE_GOOD, base=BASE, patch=PATCH):
    return {
        'instance_id': IID,
        'patch_sha256': patch,
        'base_commit': base,
        'expected_run_tree': tree,
        'declared_fail_to_pass': ['test_f2p'],
        'declared_p2p_scoped': ['test_p2p'],
        'built_at': '2026-10-27T00:00:01+00:00',
    }


def write_signed(store: ArtifactStore, rec: dict):
    aid = rec['artifact_id']
    body = canonical_dumps(rec).encode()
    (store.root / 'artifacts').mkdir(parents=True, exist_ok=True)
    (store.root / 'artifacts' / f'{aid}.json').write_bytes(body)
    (store.root / 'signatures').mkdir(parents=True, exist_ok=True)
    (store.root / 'signatures' / f'{aid}.sig').write_text(store.sign(body))
    return aid


def corrupt_artifact_signature(store: ArtifactStore, aid: str):
    (store.root / 'signatures' / f'{aid}.sig').write_text('0' * 64)


def corrupt_attestation_signature(store: ArtifactStore, att: dict):
    key = make_artifact_id(att['instance_id'], att['patch_sha256'])
    (store.root / 'attestations').mkdir(parents=True, exist_ok=True)
    (store.root / 'attestations' / f'{key}.json').write_bytes(
        canonical_dumps(att).encode())
    (store.root / 'signatures').mkdir(parents=True, exist_ok=True)
    (store.root / 'signatures' / f'{key}.att.sig').write_text('f' * 64)


def session(*, base=BASE, patch=PATCH):
    return {'instance_id': IID, 'base_commit': base, 'patch_sha256': patch}


def fresh_store(tmp: Path):
    return ArtifactStore(str(tmp), secret='g3b2-unit-secret',
                         fixtures_meta_name='g3b2_fixtures_meta.json')


def s1_tree_match(store):
    rec = make_record()                       # canonical record: NO run_tree
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD))
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att, sess=session(),
        restaged_tree=TREE_GOOD, patch_match=True)
    check('S1 tree_match -> TRUE',
          out['fresh_state'] == F.FRESH_TRUE and out['fresh'] is True
          and out['run_tree_match'] is True,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'run_tree_match',
                       'status_reason')}))
    # Independent restage is the authoritative source, not the record field.
    check('S1 authoritative source = independent restage',
          out['authoritative_tree_source'] == 'independent_git_restage_write_tree')


def s2_genuine_mismatch(store):
    rec = make_record()
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD))
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    # Real, comparable restaged tree that genuinely differs.
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att, sess=session(),
        restaged_tree=TREE_OTHER, patch_match=True)
    check('S2 genuine tree mismatch -> FALSE',
          out['fresh_state'] == F.FRESH_FALSE and out['fresh'] is False
          and out['run_tree_match'] is False
          and out['status_reason'] == F.REASON_TREE_MISMATCH,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'run_tree_match',
                       'status_reason')}))


def s3_record_field_missing(store):
    rec = make_record()                       # no run_tree, as in G3-B
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD))
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    # No independent restage available in this channel -> must not say FALSE.
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att, sess=session(),
        restaged_tree=None, patch_match=True)
    check('S3 missing run_tree -> UNKNOWN (not false)',
          out['fresh_state'] == F.FRESH_UNKNOWN and out['fresh'] is None
          and out['run_tree_match'] is None
          and out['status_reason'] == F.REASON_RECORD_FIELD_MISSING,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'run_tree_match',
                       'status_reason')}))
    # Demonstrate the exact G3-B bug mechanically on the same record.
    old_bool = bool(got[0].get('run_tree') == TREE_GOOD)
    check('S3 old boolean comparison would be False (root cause proven)',
          old_bool is False)


def s4_signature_invalid(store):
    # 4a: artifact signature invalid.
    rec = make_record()
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD))
    corrupt_artifact_signature(store, aid)
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att, sess=session(),
        restaged_tree=TREE_GOOD, patch_match=True)
    check('S4a artifact sig invalid -> FALSE',
          got[1] is False and out['fresh_state'] == F.FRESH_FALSE
          and out['fresh'] is False
          and out['status_reason'] == F.REASON_ARTIFACT_SIG_INVALID,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'status_reason')}))

    # 4b: attestation signature invalid.
    rec2 = make_record()
    aid2 = write_signed(store, rec2)
    corrupt_attestation_signature(store, make_attestation(tree=TREE_GOOD))
    got2 = store.get(aid2)
    att2 = store.get_attestation(IID, PATCH)
    out2 = F.adjudicate_freshness(
        rec=got2[0], authentic=got2[1], att=att2, sess=session(),
        restaged_tree=TREE_GOOD, patch_match=True)
    check('S4b attestation sig invalid -> FALSE',
          att2.get('_attestation_authentic') is False
          and out2['fresh_state'] == F.FRESH_FALSE and out2['fresh'] is False
          and out2['status_reason'] == F.REASON_ATTESTATION_SIG_INVALID,
          json.dumps({k: out2.get(k) for k in
                      ('fresh_state', 'fresh', 'status_reason')}))


def s5_patch_mismatch(store):
    # Served session binds a different patch than the signed record/attestation.
    rec = make_record(patch=PATCH)
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD, patch=PATCH))
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att,
        sess=session(patch=PATCH_OTHER),
        restaged_tree=TREE_GOOD, patch_match=False)
    check('S5 patch mismatch -> FALSE',
          out['fresh_state'] == F.FRESH_FALSE and out['fresh'] is False
          and out['status_reason'] == F.REASON_PATCH_MISMATCH,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'status_reason')}))


def extra_wrong_type(store):
    rec = make_record()
    rec['run_tree'] = 12345  # present but structurally wrong type
    aid = write_signed(store, rec)
    store.put_attestation(make_attestation(tree=TREE_GOOD))
    got = store.get(aid)
    att = store.get_attestation(IID, PATCH)
    out = F.adjudicate_freshness(
        rec=got[0], authentic=got[1], att=att, sess=session(),
        restaged_tree=None, patch_match=True)
    check('S3b wrong-type run_tree -> UNKNOWN/schema_wrong_type',
          out['fresh_state'] == F.FRESH_UNKNOWN and out['fresh'] is None
          and out['status_reason'] == F.REASON_RECORD_FIELD_WRONG_TYPE,
          json.dumps({k: out.get(k) for k in
                      ('fresh_state', 'fresh', 'status_reason')}))


def main():
    with tempfile.TemporaryDirectory() as d:
        scenarios = [
            ('S1', s1_tree_match), ('S2', s2_genuine_mismatch),
            ('S3', s3_record_field_missing), ('S4', s4_signature_invalid),
            ('S5', s5_patch_mismatch),
        ]
        # Each scenario needs a fresh store because S4/S5 corrupt shared state.
        for name, fn in scenarios:
            sd = Path(d) / name
            sd.mkdir(parents=True, exist_ok=True)
            fn(fresh_store(sd))
        # Wrong-type extra check in its own store.
        sd = Path(d) / 'S3b'
        sd.mkdir(parents=True, exist_ok=True)
        extra_wrong_type(fresh_store(sd))
    print('-' * 60)
    if FAILURES:
        print(f'FRESHNESS UNIT TESTS: {len(FAILURES)} FAILURE(S): '
              + ', '.join(FAILURES))
        raise SystemExit(1)
    print('FRESHNESS UNIT TESTS: ALL PASS (S1-S5 + wrong-type)')


if __name__ == '__main__':
    main()
