"""GroundedReview Gate G3-C.0 — zero-API study-design freeze and protocol
quality preparation, shared constants/paths.

G3-C.0 is a purely OFFLINE design-and-preparation gate. The user accepted the
G3-B.4 audit and approved ONLY:

  * freezing the G3-B.4 products (read-only, never rewritten);
  * designing a NEW versioned restricted-evidence projection that removes the
    pass_to_pass_baseline Tier-2 redundancy;
  * pre-registering two primary endpoints (P1 unsupported commitment under
    restricted evidence; P2 unsupported acceptance on sufficient-evidence
    REJECT-gold issues);
  * designing the independent-issue sampling plan (>=20 NEW REJECT issues),
    the issue-level statistical analysis plan, the evidence-availability
    paired comparison and its confounds, a strict non-interference audit,
    a ship-ready SECOND HUMAN annotator blind packet, the three-phase
    execution/budget plan (ESTIMATES ONLY), and the engineering checklist;
  * stating paper claim boundaries.

Hard constraints enforced by every g3c0 module:
  * ZERO real model calls, ZERO spend; no Gemini/R2; no Gate 3-C execution;
  * no actual issue is materialised/added in this gate (design targets only);
  * gold stays PROVISIONAL (single annotator, annotator2 NOT_OBTAINED); AI
    self-review is never presented as independent human adjudication;
  * ALL historical gates G3-A..G3-B.4 remain strictly read-only; the frozen
    views.py/server.py are imported and re-used for offline demonstration but
    NEVER edited. The proposed projection v2 is demonstrated as an out-of-tree
    wrapper, not wired into the frozen runtime;
  * every cross-version/availability contrast is labelled ASSOCIATIONAL unless
    the orthogonal 2x2 is actually run (it is only designed here);
  * no git commit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'

# Frozen read-only historical gates.
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
G3B = HERE / 'evidence_store_g3b'
G3B1 = HERE / 'evidence_store_g3b1'
G3B2 = HERE / 'evidence_store_g3b2'
G3B3 = HERE / 'evidence_store_g3b3'
G3B4 = HERE / 'evidence_store_g3b4'

# G3-B.4 frozen products being re-verified (task 1) and used as the parent pin.
G3B4_RESULT_FREEZE = G3B4 / 'freeze' / 'g3b4_result_freeze_manifest.json'
G3B3_RESULT_FREEZE = (G3B3 / 'freeze' /
                      'g3b3_result_freeze_manifest.json')
G3B3_LIVE_DEEPSEEK = G3B3 / 'runs' / 'g3b3_live_deepseek_flash_results.jsonl'
G3B3_LIVE_GPT = G3B3 / 'runs' / 'g3b3_live_gpt_41_mini_results.jsonl'
G3B3_DATA_FREEZE = G3B3 / 'freeze' / 'g3b3_freeze_manifest.json'

# G3-C.0 output tree (the ONLY tree g3c0 writes).
G3C0 = HERE / 'evidence_store_g3c0'
OUT_DESIGN = G3C0 / 'design'
OUT_PROJECTION = G3C0 / 'projection'
OUT_HUMAN = G3C0 / 'human_annotation'
OUT_BUDGET = G3C0 / 'budget'
OUT_FREEZE_DIR = G3C0 / 'freeze'
OUT_FREEZE = OUT_FREEZE_DIR / 'g3c0_design_freeze_manifest.json'
OUT_REPORT = G3C0 / 'g3c0_design_report.json'
OUT_REPORT_MD = G3C0 / 'g3c0_design_report.md'

# Version identifiers (never overlap a frozen version string).
G3C0_DESIGN_VERSION = 'groundedreview-gate3c0-zero-api-design-freeze-v1'
PROJECTION_V2_VERSION = 'diagnostic-v2-no-baseline-map-v1'
# Distinct bootstrap seed for the pre-registered Gate 3-C analyses (not used
# to collect anything here; recorded in the frozen plan).
G3C0_BOOTSTRAP_SEED = 418231
G3C0_SAMPLING_SEED = 418237
G3C0_BOOTSTRAP_REPLICATES = 10000

# The frozen observed design, restated locally (never mutating frozen consts).
CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')
MODELS = ('gpt-4.1-mini', 'deepseek-flash')
PRIMARY_MODEL = 'gpt-4.1-mini'
EXISTING_ISSUES = ('sympy-13615', 'sympy-13974', 'sympy-15349', 'sympy-17318',
                   'sympy-17630', 'sympy-19783', 'sympy-20590', 'sympy-21847',
                   'sympy-24213', 'sympy-24443')
EXISTING_REJECT_ISSUES = ('sympy-17318', 'sympy-17630', 'sympy-19783')

# Gold stays PROVISIONAL; this is restated, never raised.
GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Single-annotator gold carried unchanged from Gate 3-A.1; no '
             'second independent human adjudicator has been obtained as of '
             'Gate G3-C.0. All Gate 3-C endpoint definitions are pre-'
             'registered against the FUTURE adjudicated gold; PROVISIONAL-'
             'gold re-analyses are secondary only. The AI preparing this '
             'design is NOT an independent human annotator or arbiter.'),
}

# Zero-API scope enforced by every g3c0 module.
APPROVED_SCOPE = {
    'real_model_calls': 0,
    'spend_usd': 0.0,
    'actual_new_issues_materialised': 0,
    'gemini_or_r2': False,
    'gate_3c_execution': False,
    'gold_changes': False,
    'modify_historical_frozen_artifacts': False,
    'wire_v2_into_frozen_runtime': False,
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


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def verify_g3b4_freeze(verbose: bool = True) -> dict:
    """Recompute hashes of every file pinned in the G3-B.4 result-freeze
    manifest AND the canonical digest of the sorted file list, proving the
    accepted G3-B.4 products are unchanged (task 1). Read-only."""
    mf = json.loads(G3B4_RESULT_FREEZE.read_text(encoding='utf-8'))
    checks = []
    disk_entries = []
    for f in mf['files']:
        p = G3B4 / f['relpath']
        ok = p.exists() and sha256_file(p) == f['sha256']
        checks.append({'relpath': f['relpath'], 'ok': ok,
                       'bytes': f['bytes']})
        if verbose:
            print(('PASS' if ok else 'FAIL'), f['relpath'])
        if p.exists():
            disk_entries.append({'relpath': f['relpath'],
                                 'bytes': p.stat().st_size,
                                 'sha256': sha256_file(p)})
    entries = sorted(
        ({'relpath': e['relpath'], 'bytes': e['bytes'],
          'sha256': e['sha256']} for e in disk_entries),
        key=lambda e: e['relpath'])
    # Replicate g3b4_report._write_freeze exactly: canonical_bytes wraps the
    # sorted list under a 'files' key (indent=2, sorted keys, trailing \n).
    rebuilt = canonical_bytes({'files': entries})
    canon_ok = sha256_bytes(rebuilt) == mf['files_canonical_sha256']
    n_ok = (sum(c['ok'] for c in checks) + (1 if canon_ok else 0))
    n_total = len(checks) + 1
    if verbose:
        print(('PASS' if canon_ok else 'FAIL'),
              'g3b4 files_canonical_sha256')
    return {
        'manifest': str(G3B4_RESULT_FREEZE.relative_to(HERE)),
        'n_files_declared': mf['n_files'],
        'n_files_reverified': len(disk_entries),
        'every_file_sha_matches': all(c['ok'] for c in checks),
        'canonical_digest_matches': canon_ok,
        'n_pass': n_ok, 'n_checks': n_total,
        'all_ok': all(c['ok'] for c in checks) and canon_ok,
        'checks': checks,
        'g3b4_audit_version': mf.get('audit_version'),
    }
