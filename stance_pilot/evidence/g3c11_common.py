"""GroundedReview Gate G3-C.1.1 - zero-API sampling-compliance, Gold
construct-validity and human-arbitration-readiness AUDIT of the frozen
Gate G3-C.1 local pilot.

The user has given EXPLICIT WRITTEN APPROVAL for Gate G3-C.1.1 only:
  * new API budget = $0; new Issue cap = 0;
  * all G3-C.1 and earlier frozen products are strictly READ-ONLY;
  * G3-C.2 expansion, any real Reviewer API call, Gemini, R2 and git
    commit/add are NOT approved and are not executed;
  * only offline analysis, review-material preparation and the *registry*
    of genuinely obtained real human annotator-2 labels are permitted. No
    real second human was obtained in this gate, therefore every Gold stays
    PROVISIONAL / annotator2=NOT_OBTAINED; the AI is never a substitute.

Hard rules enforced by every g3c11 module:
  * new code uses the g3c11_ prefix; the ONLY output tree written is
    evidence_store_g3c11/;
  * g3c1 / g3c0 / g3b* stores and evidence code are imported/read but
    never written; g3c1 build/freezing functions are never invoked;
  * the audit independently RECOMPUTES hashes, funnels and counts; it does
    not trust a frozen manifest's self-report;
  * no model call, no network egress, no data collection, no historical
    Gold edit, no frozen-raw-test rewrite, no git commit/add.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence import g3c1_common as G1  # read-only reuse of helpers/constants

HERE = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Frozen read-only gates (never written by g3c11).
G3C1 = HERE / 'evidence_store_g3c1'
G3C0 = HERE / 'evidence_store_g3c0'
G3B3 = HERE / 'evidence_store_g3b3'
G3B4 = HERE / 'evidence_store_g3b4'

G3C1_FREEZE = G3C1 / 'freeze' / 'g3c1_freeze_manifest.json'
G3C0_DESIGN_FREEZE = G3C0 / 'freeze' / 'g3c0_design_freeze_manifest.json'
G3B4_RESULT_FREEZE = G3B4 / 'freeze' / 'g3b4_result_freeze_manifest.json'
G3B3_RESULT_FREEZE = G3B3 / 'freeze' / 'g3b3_result_freeze_manifest.json'
G3B3_DATA_FREEZE = G3B3 / 'freeze' / 'g3b3_freeze_manifest.json'

G3C1_SELECTION = G3C1 / 'selection' / 'g3c1_selection.json'
G3C1_TRUTH = G3C1 / 'g3c1_truth.jsonl'
G3C1_ORACLE = G3C1 / 'gold' / 'g3c1_oracle_gold.jsonl'
G3C1_CERTS = G3C1 / 'gold' / 'g3c1_condition_certificates.jsonl'
G3C1_REPORT_JSON = G3C1 / 'g3c1_report.json'
G3C1_FRESHNESS = G3C1 / 'audit' / 'g3c1_freshness_recompute.json'
G3C1_NI = G3C1 / 'projection' / 'g3c1_noninterference_audit.json'
G3C1_HTTP = G3C1 / 'audit' / 'g3c1_http_crosscheck.json'
G3C1_MOCK = G3C1 / 'audit' / 'g3c1_mock_audit.json'
G3C1_PROBE_NOTE = G3C1 / 'audit' / 'g3c1_probe_revision_note_19495.json'
G3C1_HUMAN_PKG = G3C1 / 'human_annotation' / 'g3c1_human_annotation_package.json'
G3C0_HUMAN_PKG = G3C0 / 'human_annotation' / 'g3c0_human_annotation_package.json'
G3C0_PREREG = G3C0 / 'design' / 'g3c0_preregistration_endpoints_sampling_stats.json'
G3C0_BUDGET = G3C0 / 'budget' / 'g3c0_execution_budget_and_engineering.json'

# --------------------------------------------------------------------------
# G3-C.1.1 output tree (the ONLY tree any g3c11 module writes).
G3C11 = HERE / 'evidence_store_g3c11'
OUT_AUDIT = G3C11 / 'audit'
OUT_HUMAN = G3C11 / 'human_annotation'
OUT_REPORT = G3C11 / 'report'
OUT_FREEZE_DIR = G3C11 / 'freeze'
OUT_FREEZE = OUT_FREEZE_DIR / 'g3c11_freeze_manifest.json'

ALL_OUT_DIRS = (G3C11, OUT_AUDIT, OUT_HUMAN, OUT_REPORT, OUT_FREEZE_DIR)

G3C11_DESIGN_VERSION = 'groundedreview-gate3c11-zero-api-audit-freeze-v1'
G3C11_PROTOCOL_VERSION = 'g3c11-protocol-v1'

# The eight frozen G3-C.1 pilot issues (instance_id -> short).
PILOT_ISSUES = (
    'sympy__sympy-14248', 'sympy__sympy-15875', 'sympy__sympy-16886',
    'sympy__sympy-19040', 'sympy__sympy-19346', 'sympy__sympy-19495',
    'sympy__sympy-19637', 'sympy__sympy-22914')
REJECT_ISSUES = ('sympy__sympy-14248', 'sympy__sympy-15875')
ACCEPT_ISSUES = tuple(i for i in PILOT_ISSUES if i not in REJECT_ISSUES)
CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')

# G3-C.1.1 approved scope (mirrors the written approval; enforced, not just
# asserted).
APPROVED_SCOPE = {
    'real_model_calls': 0,
    'spend_usd': 0.0,
    'new_issues': 0,
    'gemini_or_r2': False,
    'gate_3c2_execution': False,
    'new_data_collection': False,
    'historical_gold_modified': False,
    'frozen_raw_tests_rewritten': False,
    'modify_historical_frozen_artifacts': False,
    'git_commit_or_add': False,
    'ai_self_labelling_as_annotator2': False,
}

GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Gate G3-C.1.1 is a read-only audit. No real second independent '
             'human annotator was obtained in this gate, so all 18/18 Gold '
             'items (10 G3-A + 8 G3-C.1) remain PROVISIONAL/PENDING. The '
             'auditing AI is explicitly NOT annotator2 and never substitutes '
             'one; only genuinely obtained real human labels may be registered.'),
}


# --------------------------------------------------------------------------
# Read-only helpers (re-implemented here; no g3c1 write path is reachable).
def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in
            p.read_text(encoding='utf-8').splitlines() if line.strip()]


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def write_canonical(path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(canonical_bytes(obj))


def relpath(posix: str) -> str:
    return posix.replace('\\', '/')


def ensure_out_dirs() -> None:
    for d in ALL_OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
