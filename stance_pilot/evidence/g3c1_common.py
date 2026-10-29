"""GroundedReview Gate G3-C.1 — local zero-API pilot construction of up to 8
NEW independent SymPy issues. Shared constants/paths/helpers.

The user has given EXPLICIT WRITTEN APPROVAL for Gate G3-C.1 (Gate G3-C.0 is
complete, accepted and frozen and must never be re-run or rewritten).

Approved scope:
  * build AT MOST 8 brand-new independent SymPy issues;
  * local data extraction, patch replay, REAL pytest execution, gold
    construction, evidence signing, REAL local HTTP cross-check, offline mock;
  * model API budget = $0: no real Reviewer model call, no Gemini, no R2,
    no Gate G3-C.2;
  * all historical frozen products strictly read-only (import only);
  * no git commit/add (constructively never invoked).

Hard rules enforced by every g3c1 module:
  * new code uses the g3c1_ prefix; the ONLY output tree written is
    evidence_store_g3c1/;
  * issues are never chosen because of a model's prior errors; gold is never
    edited to fill a category quota;
  * on a pre-registered stop condition the failure is recorded and the build
    halts — the problematic item is not skipped to keep construction going;
  * every new gold stays PROVISIONAL (annotators=1, annotator2=NOT_OBTAINED)
    until a real second human adjudicator labels the blind packet.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'

# --------------------------------------------------------------------------
# Frozen read-only historical gates (import/read only; NEVER written).
WAVE2_STORE = HERE / 'evidence_store'
POOL = WAVE2_STORE / 'wave2_candidate_pool.jsonl'
WAVE2_SELECTION_AUDIT = WAVE2_STORE / 'wave2_selection_audit.json'

G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
G3B = HERE / 'evidence_store_g3b'
G3B1 = HERE / 'evidence_store_g3b1'
G3B2 = HERE / 'evidence_store_g3b2'
G3B3 = HERE / 'evidence_store_g3b3'
G3B4 = HERE / 'evidence_store_g3b4'
G3C0 = HERE / 'evidence_store_g3c0'

# Frozen parent manifests pinned by the G3-C.1 freeze manifest.
G3B4_RESULT_FREEZE = G3B4 / 'freeze' / 'g3b4_result_freeze_manifest.json'
G3B3_RESULT_FREEZE = G3B3 / 'freeze' / 'g3b3_result_freeze_manifest.json'
G3B3_DATA_FREEZE = G3B3 / 'freeze' / 'g3b3_freeze_manifest.json'
G3C0_DESIGN_FREEZE = G3C0 / 'freeze' / 'g3c0_design_freeze_manifest.json'

# --------------------------------------------------------------------------
# G3-C.1 output tree (the ONLY tree any g3c1 module writes).
G3C1 = HERE / 'evidence_store_g3c1'
OUT_RAW = G3C1 / 'raw'
OUT_PROBES = G3C1 / 'probes'
OUT_PATCHES = G3C1 / 'patches'
OUT_STORE = G3C1 / 'store'
OUT_SELECTION = G3C1 / 'selection'
OUT_GOLD = G3C1 / 'gold'
OUT_AUDIT = G3C1 / 'audit'
OUT_PROJECTION = G3C1 / 'projection'
OUT_HUMAN = G3C1 / 'human_annotation'
OUT_RUNS = G3C1 / 'runs'
OUT_FREEZE_DIR = G3C1 / 'freeze'
OUT_FREEZE = OUT_FREEZE_DIR / 'g3c1_freeze_manifest.json'
OUT_REPORT = G3C1 / 'g3c1_report.json'
OUT_REPORT_MD = G3C1 / 'g3c1_report.md'
TRUTH = G3C1 / 'g3c1_truth.jsonl'
FAILURES = G3C1 / 'g3c1_failures.jsonl'

ALL_OUT_DIRS = (G3C1, OUT_RAW, OUT_PROBES, OUT_PATCHES, OUT_STORE,
                OUT_SELECTION, OUT_GOLD, OUT_AUDIT, OUT_PROJECTION, OUT_HUMAN,
                OUT_RUNS, OUT_FREEZE_DIR)

# --------------------------------------------------------------------------
# Version identifiers (must not collide with any frozen version string).
G3C1_DESIGN_VERSION = 'groundedreview-gate3c1-local-pilot-freeze-v1'
G3C1_PROTOCOL_VERSION = 'g3c1-protocol-v1'
G3C1_GOLD_CERT_VERSION = 'g3c1-gold-cert-v1'
# Reuse the G3-C.0 frozen projection implementation/version; the served v2
# payload is produced by the frozen g3c0_projection_v2 wrapper, never by
# editing frozen views/server code.
PROJECTION_V2_VERSION = 'diagnostic-v2-no-baseline-map-v1'

# Sampling seed REUSES the G3-C.0 frozen sampling seed (418237) as the frozen
# G3-C.0 sampling plan mandates; distinct derived seeds for local pilot needs.
G3C1_SAMPLING_SEED = 418237
G3C1_ENRICHED_SEED = 418241
G3C1_HUMAN_BLIND_SEED = 418307

MAX_NEW_ISSUES = 8
# The pilot fills the 8 slots: 4 natural-order, 4 REJECT-enriched-order; the
# union is taken (an issue in both queues counts once), capped at 8. This
# split is pre-registered here BEFORE any build/outcome is known.
N_NATURAL_SLOTS = 4
N_ENRICHED_SLOTS = 4

# The five frozen evidence conditions (identical protocol set to G3-B/G3-C.0).
CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')

# --------------------------------------------------------------------------
# Exclusion sets (frozen by history, not by outcome).
# 12 wave2 issues consumed before G3-A (10 wave2 cohort + 2 canonical builds).
WAVE2_CONSUMED = {
    'sympy__sympy-12419', 'sympy__sympy-12481', 'sympy__sympy-12489',
    'sympy__sympy-13091', 'sympy__sympy-13798', 'sympy__sympy-14531',
    'sympy__sympy-16450', 'sympy__sympy-17139', 'sympy__sympy-18199',
    'sympy__sympy-18211', 'sympy__sympy-16597', 'sympy__sympy-20428'}
# 10 G3-A primary cohort issues (already materialised with gold).
G3A_CONSUMED = {
    'sympy__sympy-13615', 'sympy__sympy-13974', 'sympy__sympy-15349',
    'sympy__sympy-17318', 'sympy__sympy-17630', 'sympy__sympy-19783',
    'sympy__sympy-20590', 'sympy__sympy-21847', 'sympy__sympy-24213',
    'sympy__sympy-24443'}
# known issue whose base tree blobs are not fully cached offline.
OFFLINE_INCOMPLETE = {'sympy__sympy-11618'}
HISTORY_EXCLUDED = WAVE2_CONSUMED | G3A_CONSUMED | OFFLINE_INCOMPLETE

# Static test-spec gates reused verbatim from the frozen wave2/g3a audits.
GATE_KEYS = ('base_present', 'test_patch_clean', 'declared_nonempty',
             'all_test_files_exist_after_apply', 'test_patch_real_apply_ok',
             'f2p_all_mapped')
# deterministic target generator priority (frozen dataset split prefixes).
GEN_PRIORITY = {'GLM-5-FP8': 0,
                'Qwen/Qwen3-Coder-30B-A3B-Instruct': 1,
                'Qwen/Qwen3-30B-A3B-Instruct-2507': 2}

# Gold authority — restated, never raised.
GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Single-annotator gold constructed in Gate G3-C.1 from executed '
             'local evidence only; no second independent human adjudicator '
             'has been obtained. All gold stays PROVISIONAL until the sealed '
             'blind packet is labelled by a real annotator2 and adjudicated. '
             'The AI building this gate is NOT an independent human annotator '
             'or arbiter.'),
}

# Zero-API scope enforced by every g3c1 module.
APPROVED_SCOPE = {
    'real_model_calls': 0,
    'spend_usd': 0.0,
    'max_new_issues': 8,
    'gemini_or_r2': False,
    'gate_3c2_execution': False,
    'gold_quota_editing': False,
    'issue_choice_from_model_errors': False,
    'mirror_fixtures': False,
    'modify_historical_frozen_artifacts': False,
    'edit_frozen_runtime_code': False,
    'git_commit_or_add': False,
}


# --------------------------------------------------------------------------
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


def read_jsonl(path) -> list:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in
            p.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_jsonl(path, rows: list) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)
        + ('\n' if rows else ''), encoding='utf-8')


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def write_canonical(path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(canonical_bytes(obj))


def ensure_out_dirs() -> None:
    for d in ALL_OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)


def record_failure(stage: str, instance_id: str, detail: dict) -> None:
    """Append a structured stop/failure record; construction halts after this."""
    import datetime as dt
    rec = {
        'recorded_at': dt.datetime.now(dt.timezone.utc).isoformat(
            timespec='seconds'),
        'stage': stage, 'instance_id': instance_id, **detail}
    rows = read_jsonl(FAILURES)
    rows.append(rec)
    write_jsonl(FAILURES, rows)
