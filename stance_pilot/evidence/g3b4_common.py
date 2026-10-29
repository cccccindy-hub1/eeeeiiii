"""GroundedReview Gate 3-B.4 — zero-API strict audit, shared constants/paths.

Gate 3-B.4 is a purely OFFLINE, INDEPENDENT audit of the frozen Gate 3-B.3
corrective replication. It makes NO model call and spends $0. It neither adds
issues nor changes gold. Every g3b4 module:

  * reads the frozen gates G3-A / G3-A.1 / G3-B / G3-B.1 / G3-B.2 / G3-B.3
    strictly read-only (imports of frozen modules are allowed for protocol
    reasoning; frozen modules are never edited);
  * writes ONLY under evidence_store_g3b4/;
  * independently re-derives numbers with a THIRD implementation (it does not
    import g3b3_analyze / g3b_analyze / g3b1_audit scoring code);
  * keeps every G3-B -> G3-B.3 comparison explicitly ASSOCIATIONAL;
  * keeps gold PROVISIONAL (single annotator, n=1; annotator2 NOT_OBTAINED);
    AI self-review is never presented as independent human adjudication;
  * makes no git commit.

The audit scope (written approval, Gate 3-B.3 accepted):
  result integrity of the 100 real cells + raw responses + tool traces +
  metrics + cost + protocol fingerprints; independent recomputation of the
  DeepSeek sufficient-evidence 9/10 -> 1/10 paired change with a full
  transition matrix and issue-cluster bootstrap; per-issue audit of the GPT
  T3D-Strict errors with ACCEPT vs REJECT kept separate; partial-blind reason
  coding with the taxonomy frozen BEFORE coding; T2D vs Strict mechanism
  comparison; non-interference leakage scan; SymPy-13974 and the two GPT focal
  cases; first-run CompositeGuard None timeline; second-annotator plan;
  revised Gate 3-C design (design only, not executed); paper Results/
  Discussion revision language.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'

# Frozen read-only gates.
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
G3B = HERE / 'evidence_store_g3b'
G3B1 = HERE / 'evidence_store_g3b1'
G3B2 = HERE / 'evidence_store_g3b2'
G3B3 = HERE / 'evidence_store_g3b3'

# G3-B.3 frozen inputs (the audited gate).
G3B3_LIVE_DEEPSEEK = G3B3 / 'runs' / 'g3b3_live_deepseek_flash_results.jsonl'
G3B3_LIVE_GPT = G3B3 / 'runs' / 'g3b3_live_gpt_41_mini_results.jsonl'
G3B3_LIVE_AUDIT = G3B3 / 'runs' / 'g3b3_live_run_audit.json'
G3B3_MOCK_AUDIT = G3B3 / 'runs' / 'g3b3_mock_run_audit.json'
G3B3_RAW_DIR = G3B3 / 'raw'
G3B3_TRACE_DIR = G3B3 / 'traces' / 'live'
G3B3_PREFLIGHT = G3B3 / 'preflight' / 'g3b3_preflight.json'
G3B3_LIVEGATE = G3B3 / 'livegate' / 'g3b3_live_gate.json'
G3B3_ANALYSIS = G3B3 / 'analysis' / 'g3b3_analysis.json'
G3B3_ISSUE_EVIDENCE = G3B3 / 'analysis' / 'g3b3_per_issue_evidence.json'
G3B3_REPORT = G3B3 / 'g3b3_report.json'
G3B3_FREEZE = G3B3 / 'freeze' / 'g3b3_freeze_manifest.json'
G3B3_RESULT_FREEZE = (G3B3 / 'freeze' /
                      'g3b3_result_freeze_manifest.json')

# G3-B historical live rows (read-only pairing anchor).
G3B_LIVE_DEEPSEEK = (G3B / 'runs' /
                     'g3b_live_deepseek_flash_results.jsonl')
G3B_LIVE_GPT = G3B / 'runs' / 'g3b_live_gpt_41_mini_results.jsonl'
G3B_FREEZE = G3B / 'freeze' / 'g3b_freeze_manifest.json'

# G3-A frozen fixture rows / store logs (for the SymPy-13974 fact check).
G3A_TARGET_ROWS = G3A / 'raw' / 'g3a_target_rows.jsonl'
G3A_STORE_LOGS = G3A / 'store' / 'logs'

# G3-B.4 output root (the ONLY tree g3b4 writes).
G3B4 = HERE / 'evidence_store_g3b4'
OUT_AUDIT_DIR = G3B4 / 'audits'
OUT_BLIND_DIR = G3B4 / 'blind_coding'
OUT_FREEZE = G3B4 / 'freeze' / 'g3b4_result_freeze_manifest.json'
OUT_REPORT = G3B4 / 'g3b4_report.json'
OUT_REPORT_MD = G3B4 / 'g3b4_report.md'

# Version identifiers (never overlap a frozen version string).
GATE = 'gate3b4_zero_api_strict_audit'
G3B4_AUDIT_VERSION = 'groundedreview-gate3b4-zero-api-strict-audit-v1'
G3B4_TAXONOMY_VERSION = 'g3b4-strict-error-taxonomy-v1'
G3B4_BOOTSTRAP_SEED = 417313          # distinct from g3b/g3b3 seed 313
G3B4_BOOTSTRAP_REPLICATES = 10000
G3B4_BLIND_SEED = 417997

# The frozen design, restated locally so g3b4 never mutates g3b3 constants.
CONDITIONS = ('T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T')
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')
SUFFICIENT_CONDITIONS = ('T2A-T', 'T3D-Escalate', 'T3A-T')
RESTRICTED_CONDITIONS = ('T2D-T', 'T3D-Strict')
REJECT_ISSUES = ('sympy-17318', 'sympy-17630', 'sympy-19783')
MODELS = ('deepseek-flash', 'gpt-4.1-mini')
ISSUES = ('sympy-13615', 'sympy-13974', 'sympy-15349', 'sympy-17318',
          'sympy-17630', 'sympy-19783', 'sympy-20590', 'sympy-21847',
          'sympy-24213', 'sympy-24443')

# Gold stays PROVISIONAL; this is restated, not raised.
GOLD_AUTHORITY = {
    'gold_tier': 'PROVISIONAL',
    'annotators': 1,
    'annotator2': 'NOT_OBTAINED',
    'note': ('Single-annotator gold carried unchanged from Gate 3-A.1; no '
             'second adjudicator has been obtained as of Gate 3-B.4. No '
             'Cohen kappa is reported and gold is never called human-'
             'adjudicated. Gate 3-B.4 audits model behaviour against this '
             'PROVISIONAL gold only; the same AI operator performing the '
             'audit is NOT an independent human adjudicator.'),
}

# Zero-API scope enforced by every g3b4 module.
APPROVED_SCOPE = {
    'real_model_calls': 0,
    'spend_usd': 0.0,
    'new_issues_or_mirrors': False,
    'gemini_or_r2': False,
    'gate_3c_execution': False,
    'gold_changes': False,
    'modify_historical_frozen_artifacts': False,
    'overwrite_g3b3_data': False,
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
    """Yield already-parsed dict rows; callers MUST NOT json.loads again."""
    return [json.loads(line) for line in Path(path).read_text(
        encoding='utf-8').splitlines() if line.strip()]


def canonical_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def load_result_freeze() -> dict:
    return json.loads(G3B3_RESULT_FREEZE.read_text(encoding='utf-8'))


def load_data_freeze() -> dict:
    return json.loads(G3B3_FREEZE.read_text(encoding='utf-8'))


def artifact_pin(result_freeze: dict, name: str) -> dict:
    for a in result_freeze['artifacts']:
        if a['name'] == name:
            return a
    raise KeyError(name)


def verify_g3b3_result_freeze(verbose: bool = True) -> dict:
    """Independently recompute hashes of every artifact pinned in the G3-B.3
    RESULT freeze (7 files + raw/ and traces/ manifests) and confirm the data
    freeze manifest itself matches its post-collection pin. Returns a
    structured report; raises only if a pin is missing."""
    rf = load_result_freeze()
    checks = []

    def record(name, ok, detail):
        checks.append({'artifact': name, 'ok': bool(ok), 'detail': detail})
        if verbose:
            print(('PASS' if ok else 'FAIL'), name, detail)

    for a in rf['artifacts']:
        p = HERE / a['path']
        if 'sha256' in a and a['sha256']:
            ok = p.exists() and sha256_file(p) == a['sha256']
            record(a['name'], ok,
                   'file sha256 == result-freeze pin' if ok
                   else f'hash drift or missing at {p}')
        else:
            # Directory manifest: sorted (relpath, bytes, sha256) entries.
            files = a['files']
            present = {f['relpath']: f for f in files}
            disk = {}
            for f in sorted(p.glob('*')):
                if f.is_file():
                    disk[f.name] = (f.stat().st_size, sha256_file(f))
            entry_ok = (len(disk) == a['n_files'] == len(files))
            mism = []
            for rel, f in present.items():
                if rel not in disk:
                    mism.append(f'missing:{rel}')
                elif disk[rel] != (f['bytes'], f['sha256']):
                    mism.append(f'drift:{rel}')
            extra = sorted(set(disk) - set(present))
            if extra:
                mism.append('extra:' + ','.join(extra[:3]))
            # Recompute exactly as g3b3_report did: entries in relpath order,
            # json.dumps(sort_keys=True), no indent and no trailing newline.
            entries = sorted(
                ({'relpath': f['relpath'], 'bytes': f['bytes'],
                  'sha256': f['sha256']} for f in files),
                key=lambda e: e['relpath'])
            rebuilt = json.dumps(entries, sort_keys=True,
                                 ensure_ascii=False).encode()
            manifest_ok = (sha256_bytes(rebuilt)
                           == a['sha256_of_sorted_file_manifest'])
            ok = entry_ok and not mism and manifest_ok
            record(a['name'], ok,
                   f'{len(disk)}/{a["n_files"]} files; '
                   f'manifest recompute {"ok" if manifest_ok else "DRIFT"}'
                   + (f'; {mism[:3]}' if mism else ''))

    dcf = rf['data_collection_freeze']
    df_ok = (G3B3_FREEZE.exists()
             and sha256_file(G3B3_FREEZE) == dcf['sha256'])
    record('g3b3_data_collection_freeze', df_ok,
           'pre-paid-run freeze manifest sha256 == post-collection pin'
           if df_ok else 'data freeze manifest drift')
    all_ok = all(c['ok'] for c in checks)
    return {'all_pins_match': all_ok, 'n_checks': len(checks),
            'n_pass': sum(c['ok'] for c in checks), 'checks': checks}


def verify_g3b3_parent_pins(verbose: bool = True) -> dict:
    """Verify the parent anchors the G3-B.3 result freeze claims:
    G3-B freeze manifest sha and both G3-B live row files (the pairing
    anchor). Values are read FROM the frozen manifest, not hard-coded."""
    rf = load_result_freeze()
    anchor = rf['g3b_pairing_anchor']
    out = {'checks': []}
    g3b_pin = anchor['g3b_freeze_manifest_sha256']
    ok = G3B_FREEZE.exists() and sha256_file(G3B_FREEZE) == g3b_pin
    out['checks'].append({'artifact': 'g3b_freeze_manifest', 'ok': ok})
    if verbose:
        print(('PASS' if ok else 'FAIL'), 'g3b_freeze_manifest')
    for model, rel in anchor['g3b_live_results'].items():
        p = HERE / rel
        # The G3-B.3 pin only names the path; cross-check against the G3-B
        # freeze's own post-collection record when available, else existence.
        exists = p.exists()
        out['checks'].append({'artifact': f'g3b_live_rows:{model}',
                              'ok': exists, 'path': rel})
        if verbose:
            print(('PASS' if exists else 'FAIL'), 'g3b_live_rows', model)
    out['all_ok'] = all(c['ok'] for c in out['checks'])
    return out
