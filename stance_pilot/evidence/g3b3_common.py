"""GroundedReview Gate 3-B.3 — Corrective Replication, shared constants/paths.

G3-B.3 is the FIRST version authorised to make REAL model calls over the
G3-B.2 repaired protocol. It is a corrective replication: the same frozen 10
independent SymPy issues x the same five frozen conditions x the same two
real models (100 cells), but served entirely through the frozen, accepted
G3-B.2 repair:

  * model prompts come from evidence.g3b2_prompts (p3-ternary-g3b2-v1);
  * static T2A evidence uses the repaired INSTITUTIONAL trust text;
  * active-condition HTTP sessions are served by evidence.g3b2_server
    (three-state TRUE/FALSE/UNKNOWN freshness; the old structurally-false
    endpoint is never called);
  * each cell is paired to a G3-B.2 gold certificate.

Hard constraints enforced by every g3b3 module (the written approval):
  * 100 real cells only; NO new issue, NO Gemini/R2, NO Gate 3-C.
  * TOTAL hard cap $3.00 across both models; $1.50 per model; a pre-call
    worst-case bound is computed before EVERY API request; resume restores
    cumulative spend; a cell is NEVER retried because its prediction was
    "wrong" (retries_per_cell = 0; a transport/invalid fault is a terminal,
    resume-eligible error row).
  * DOUBLE explicit gate (--allow-paid-run AND a G3-B.3 acknowledgement);
    served-model id / tool-capability / response_format / freeze drift => a
    HARD STOP and report, never a silent downgrade.
  * Gold stays PROVISIONAL (single annotator, n=1; annotator2
    NOT_OBTAINED). The repair does not raise gold authority.
  * No frozen Gate 3-B / G3-A / G3-A.1 / G3-B.2 artifact is ever modified;
    g3b3 imports the g3b2 modules but never edits them and writes ONLY under
    evidence_store_g3b3/. G3-B historical results are independently
    preserved: never overwritten or re-scored in place.
  * No git commit.

The G3-B -> G3-B.3 comparison is, by design, a CROSS-VERSION, CROSS-RUN-TIME
ASSOCIATIONAL comparison. The repair changed two things at once (the live
freshness endpoint and the T2A trust expression); this run cannot separately
identify each change's causal effect and no module claims to.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'

# Frozen read-only inputs.
G3A = HERE / 'evidence_store_g3a'
G3A_STORE = G3A / 'store'
G3B = HERE / 'evidence_store_g3b'
G3B2 = HERE / 'evidence_store_g3b2'

# G3-B historical live result rows (read-only; independently preserved).
G3B_RUN_DIR = G3B / 'runs'
G3B_LIVE_DEEPSEEK = G3B_RUN_DIR / 'g3b_live_deepseek_flash_results.jsonl'
G3B_LIVE_GPT = G3B_RUN_DIR / 'g3b_live_gpt_41_mini_results.jsonl'
G3B_RUN_AUDIT = G3B_RUN_DIR / 'g3b_live_run_audit.json'
G3B_FREEZE = G3B / 'freeze' / 'g3b_freeze_manifest.json'

# The accepted G3-B.2 repaired protocol artifacts (read-only).
G3B2_FREEZE = G3B2 / 'freeze' / 'g3b2_freeze_manifest.json'
G3B2_GOLD_CERTS = G3B2 / 'gold' / 'g3b2_condition_gold_certificates.jsonl'
G3B2_GOLD_CHANGELOG = G3B2 / 'gold' / 'g3b2_gold_changelog.json'

# G3-B.3 output root (the only tree g3b3 writes).
G3B3 = HERE / 'evidence_store_g3b3'
OUT_FREEZE = G3B3 / 'freeze' / 'g3b3_freeze_manifest.json'
OUT_LIVE_DIR = G3B3 / 'runs'
OUT_RAW_DIR = G3B3 / 'raw'
OUT_TRACE_DIR = G3B3 / 'traces'
OUT_LIVE_AUDIT = OUT_LIVE_DIR / 'g3b3_live_run_audit.json'
OUT_LIVEGATE = G3B3 / 'livegate' / 'g3b3_live_gate.json'
OUT_PREFLIGHT = G3B3 / 'preflight' / 'g3b3_preflight.json'
OUT_MOCK_AUDIT = G3B3 / 'runs' / 'g3b3_mock_run_audit.json'
OUT_ANALYSIS = G3B3 / 'analysis' / 'g3b3_analysis.json'
OUT_ISSUE_EVIDENCE = G3B3 / 'analysis' / 'g3b3_per_issue_evidence.json'
OUT_REPORT = G3B3 / 'g3b3_report.json'
OUT_RESULT_FREEZE = G3B3 / 'freeze' / 'g3b3_result_freeze_manifest.json'

# G3-B.3 version identifiers (never overlap a frozen version string). These
# record that the EXECUTED protocol/prompt/gold-cert are the G3-B.2 versions.
GATE = 'gate3b3_corrective_replication'
RUN_PROTOCOL_VERSION = 'g3b2-protocol-v1'   # the executed server protocol
RUN_PROMPT_VERSION = 'p3-ternary-g3b2-v1'   # the executed prompt version
RUN_GOLD_CERT_VERSION = 'g3b2-gold-cert-v1'
G3B3_RUNNER_VERSION = 'g3b3-runner-v1'
G3B3_FREEZE_VERSION = 'groundedreview-gate3b3-corrective-replication-v1'

# The five frozen regimes and the two REAL, approved subject models.
CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')
# The three SUFFICIENT-EVIDENCE conditions for the pre-registered DeepSeek
# primary endpoint (#10).
SUFFICIENT_CONDITIONS = ('T2A-T', 'T3D-Escalate', 'T3A-T')
# The two deliberately RESTRICTED conditions for the over-acceptance control
# (#12): condition gold is NEED_EVIDENCE for all ten issues.
RESTRICTED_CONDITIONS = ('T2D-T', 'T3D-Strict')
# The three REJECT-oracle issues for the GPT unsupported-acceptance report.
REJECT_ISSUES = ('sympy-17318', 'sympy-17630', 'sympy-19783')
MODELS = ('deepseek-flash', 'gpt-4.1-mini')

# User-authorized HARD caps (the approval; the runner may not exceed them).
TOTAL_BUDGET_USD = 3.00
PER_MODEL_CAP_USD = 1.50

# Frozen execution parameters — identical values to G3-B; only the protocol
# content (prompt/server) is the repaired G3-B.2 one.
TEMPERATURE = 0
COMPLETION_CAP = 8192
MAX_TOOL_TURNS = 8
MAX_MODEL_CALLS_PER_CELL = 12
RETRIES_PER_CELL = 0
# NEW fixed interleaving seed, deliberately distinct from G3-B (7) and the
# g3b2 mock order (7), as promised in the approved design.
ORDER_SEED = 313

# Double explicit gate acknowledgement for THIS version only.
ACK = '--i-acknowledge-g3b3-approved'

# Single, explicit gold-authority declaration reused by every g3b3 report.
GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Single-annotator gold; no second adjudicator obtained. Neither '
             'the G3-B.2 protocol repair nor the G3-B.3 corrective '
             'replication raises gold authority. No Cohen kappa against a '
             'second human is reported; gold is never called human-'
             'adjudicated. Every model comparison is against PROVISIONAL '
             'gold only.'),
}

# Approved-scope flags mirrored into the freeze and every report.
APPROVED_SCOPE = {
    'new_issues_or_mirrors': False,
    'gemini_or_r2': False,
    'gate_3c': False,
    'modify_historical_frozen_artifacts': False,
    'overwrite_or_rescore_g3b_results': False,
    'retry_cell_on_prediction_error': False,
    'git_commit': False,
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path) -> list:
    return [json.loads(line) for line in Path(path).read_text(
        encoding='utf-8').splitlines() if line.strip()]


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                  for r in rows) + '\n', encoding='utf-8')


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')
