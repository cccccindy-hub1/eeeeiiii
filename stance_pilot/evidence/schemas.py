"""Canonical schemas and hashing for the evidence pilot.

Three orthogonal labels (keep all three; `resolved` from the benchmark is retained
separately and must never be treated as identical to any one of them):

  issue_addressed        applying the patch removes the symptom reported in the issue
                         (checked by an explicit symptom probe, executable evidence)
  regression_free_scoped pre-existing tests in the declared scope still pass
  merge_acceptable       all FAIL_TO_PASS pass AND scoped PASS_TO_PASS do not regress

Note: issue_addressed does NOT imply merge_acceptable (sympy-16597 is the reference).
"""
import hashlib, json

SCHEMA_VERSION = '1.0'

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode('utf-8'))

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

def canonical_dumps(obj) -> str:
    """Stable JSON serialisation for hash-bearing records."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))

# --- truth record (one per candidate patch) ---------------------------------
TRUTH_REQUIRED = (
    'id', 'instance_id', 'repo', 'base_commit', 'patch_sha256',
    'issue_addressed', 'regression_free_scoped', 'merge_acceptable',
    'label_class', 'label_provenance',
)

# label_class derived from (issue_addressed, merge_acceptable):
#   A = (True,  False)  symptom fixed, acceptance criteria not met  (headline)
#   B = (True,  True )  symptom fixed and fully acceptable
#   C = (False, False)  symptom not fixed, not acceptable
#   D = (False, True )  impossible under monotone acceptance; flag as error
def classify(issue_addressed: bool, merge_acceptable: bool) -> str:
    return {(True, False): 'A', (True, True): 'B',
            (False, False): 'C', (False, True): 'D'}[(bool(issue_addressed), bool(merge_acceptable))]

# --- immutable test artifact ------------------------------------------------
ARTIFACT_REQUIRED = (
    'artifact_id', 'schema_version', 'instance_id', 'repo', 'base_commit',
    'patch_sha256', 'test_patch_sha256', 'runner', 'started_at', 'finished_at',
    'scope', 'fail_to_pass', 'pass_to_pass_scoped', 'summary', 'log_digests',
)

def make_artifact_id(instance_id: str, patch_sha256: str) -> str:
    return 'art_' + sha256_text(instance_id + '|' + patch_sha256)[:16]

def validate_artifact(rec: dict):
    missing = [k for k in ARTIFACT_REQUIRED if k not in rec]
    if missing:
        raise ValueError('artifact missing fields: ' + ', '.join(missing))
    if rec['schema_version'] != SCHEMA_VERSION:
        raise ValueError('schema_version mismatch: ' + str(rec['schema_version']))
    expect = make_artifact_id(rec['instance_id'], rec['patch_sha256'])
    if rec['artifact_id'] != expect:
        raise ValueError(f"artifact_id mismatch: {rec['artifact_id']} != {expect}")
