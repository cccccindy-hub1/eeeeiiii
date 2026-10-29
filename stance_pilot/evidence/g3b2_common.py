"""GroundedReview Gate 3-B.2 — shared constants/paths for the INDEPENDENT
protocol-repair version.

Gate 3-B.1 construct-validity audit was accepted; Gate 3-B.2 is authorised as
a ZERO-API, independent-version repair of inconsistencies between:
  * Gold (which assumed restage-attested tree identity and an institutional
    linkage/freshness/coverage grant in T2A),
  * the model-visible static evidence + prompt wording (which still said
    "linkage not yet verified" and demanded self-verification), and
  * the live tool endpoint (which compared a record.run_tree field that the
    canonical artifact schema does not carry, so freshness was structurally
    forced to false).

Hard constraints enforced by every g3b2 module:
  * NO frozen Gate 3-B / G3-A / G3-A.1 artifact is ever modified; g3b2 writes
    ONLY under evidence_store_g3b2/ and uses g3b2_-prefixed python modules.
  * API budget $0: no real model call is possible from any g3b2 entry point;
    only deterministic ScriptedModel mocks run, and their rows are research-
    excluded pipeline checks (mock=true).
  * Gold stays PROVISIONAL (single annotator; annotator2 NOT_OBTAINED). The
    protocol repair does not raise gold authority.
  * Nothing here tells a model the ACCEPT/REJECT answer: the T2A repair grants
    provenance premises (L/F/C applicability), never the outcome verdict.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'
G3A = HERE / 'evidence_store_g3a'
G3A1_STORE = HERE / 'evidence_store_g3a1'
G3B = HERE / 'evidence_store_g3b'
G3B1 = HERE / 'evidence_store_g3b1'
G3B2 = HERE / 'evidence_store_g3b2'

# Independent version identifiers (never overlap a frozen version string).
PROTOCOL_VERSION = 'g3b2-protocol-v1'
PROMPT_VERSION = 'p3-ternary-g3b2-v1'
GOLD_CERT_VERSION = 'g3b2-gold-cert-v1'
GATE = 'gate3b2_zero_api_protocol_repair'

# The ten frozen G3-A issues (never re-selected; no new issue in G3-B.2).
G3A_FRESHNESS_CACHE = G3A / 'audit' / 'g3a_freshness_recompute.json'
G3A_STORE = G3A / 'store'
G3A_TARGET_ROWS = G3A / 'raw' / 'g3a_target_rows.jsonl'
G3A_GOLD = G3A / 'gold' / 'g3a_gold.jsonl'
G3A1_CONDITION_GOLD = G3A / 'gold' / 'g3a1_condition_gold.jsonl'
G3B_FREEZE = G3B / 'freeze' / 'g3b_freeze_manifest.json'

# g3b2 output locations.
OUT_FREEZE = G3B2 / 'freeze' / 'g3b2_freeze_manifest.json'
OUT_GOLD = G3B2 / 'gold' / 'g3b2_condition_gold_certificates.jsonl'
OUT_GOLD_CHANGELOG = G3B2 / 'gold' / 'g3b2_gold_changelog.json'
OUT_MATRIX = G3B2 / 'audit' / 'g3b2_three_way_consistency_matrix.json'
OUT_FRESHNESS_AUDIT = G3B2 / 'audit' / 'g3b2_freshness_authoritative_audit.json'
OUT_HTTP_CROSSCHECK = G3B2 / 'audit' / 'g3b2_http_crosscheck.json'
OUT_PROMPT_DIFF = G3B2 / 'prompt_diff' / 'g3b2_prompt_text_diff.json'
OUT_PREFLIGHT = G3B2 / 'preflight' / 'g3b2_preflight.json'
OUT_MOCK_AUDIT = G3B2 / 'runs' / 'g3b2_mock_run_audit.json'
OUT_REGRESSION_17318 = G3B2 / 'audit' / 'g3b2_sympy_17318_regression.json'
OUT_DS9_DIFF = G3B2 / 'audit' / 'g3b2_deepseek9_evidence_diff.json'
OUT_DESIGN = G3B2 / 'design' / 'g3b3_experiment_design.json'
OUT_REPORT = G3B2 / 'g3b2_repair_report.json'

FROZEN_CODE_FILES = (
    # The frozen code whose bytes G3-B.2 must never change.
    'server.py', 'store.py', 'views.py', 'prompts.py', 'gold_w2.py',
    'visibility.py', 'phase3_run.py', 'phase2_build.py', 'g3a_build.py',
    'g3a_gold.py', 'g3a1_conditions.py', 'g3a_freshness_check.py',
    'g3b_freeze.py', 'g3b_run.py', 'g3b_preflight.py', 'g3b_analyze.py',
    'g3b1_audit.py', 'ternary.py', 'schemas.py',
)


# Single, explicit gold-authority declaration reused by every g3b2 report.
# The protocol repair must NOT raise gold authority.
GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Single-annotator gold; no second adjudicator obtained. The '
             'G3-B.2 protocol repair does not raise gold authority. Until a '
             'second annotator adjudicates, all condition/oracle gold and all '
             'derived model comparisons remain PROVISIONAL.'),
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


def frozen_code_hashes() -> dict:
    """Hash the frozen code modules so the g3b2 freeze/report can prove none of
    them was modified by this repair."""
    out = {}
    for name in FROZEN_CODE_FILES:
        p = EVID / name
        out[name] = sha256_file(p) if p.exists() else None
    return out


def verify_frozen_parents():
    """Re-hash G3-A and G3-A.1 via the frozen G3-B freeze routine (which covers
    141 + 122 files), and additionally pin the G3-B freeze manifest and the
    frozen code bytes. Returns a structured verification record. Raises on any
    drift (which would invalidate the repair baseline)."""
    from evidence.g3b_freeze import verify_frozen_parents as _vb
    parents = _vb()  # re-hashes g3a + g3a1 manifests' file lists
    parents['g3b_freeze_manifest'] = {
        'path': str(G3B_FREEZE.relative_to(HERE)),
        'sha256': sha256_file(G3B_FREEZE),
    }
    parents['frozen_code'] = frozen_code_hashes()
    missing_code = [n for n, h in parents['frozen_code'].items() if h is None]
    if missing_code:
        raise SystemExit('frozen code modules missing: ' + ', '.join(missing_code))
    return parents
