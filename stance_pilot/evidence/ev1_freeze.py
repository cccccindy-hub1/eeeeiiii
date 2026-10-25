"""E1 protocol freeze (External Validation, offline preparation).

Read-only regeneration of the frozen Wave-2.1 protocol identity that E1 cross-
model replication must use byte-for-byte. This script never calls an LLM API
and never modifies any Wave-2/Wave-2.1 input; it only:

  * re-hashes the three fixture lists, the raw rows, and the gold
    (byte sha + newline-normalised gold sha used by metrics_w2);
  * recomputes the five p3-ternary-v2 prompt fingerprints and asserts they
    match wave2_freeze_manifest.json;
  * re-hashes the full frozen protocol-code set (the seven files already in
    the Wave-2 manifest plus metrics2/gap_w2/visibility/probes/builder used
    by E1 scoring and audit);
  * runs evidence.visibility.cross_check_http over 22 fixtures x 5 conditions
    on a throwaway store copy, capturing the tool-permission matrix evidence;
  * writes evidence_store_ev1/ev1_protocol_freeze.json.

Usage:
    uv run --python 3.13 -m evidence.ev1_freeze
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence.prompts import ternary_prompt_fingerprint_v2
from evidence.visibility import cross_check_http
from evidence.phase3_run import read_jsonl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STORE = ROOT / 'evidence_store_w21'
OUT_DIR = ROOT / 'evidence_store_ev1'

W2_MANIFEST = STORE / 'wave2_freeze_manifest.json'
GOLD = STORE / 'wave2_gold.jsonl'
FIXTURE_LISTS = [
    STORE / 'phase2_fixtures.jsonl',
    STORE / 'phase3_fixtures.jsonl',
    STORE / 'wave2_fixtures.jsonl',
]
RAW_ROWS = [
    STORE / 'wave2_pilot_raw_rows.jsonl',      # canonical frozen run raw (covers all)
    STORE / 'raw_rows.jsonl',                  # corrected-run aggregate
]
CORRECTED_RESULTS = STORE / 'wave21_corrected_all110_results.jsonl'
WRONG_PATCH_RERUN = STORE / 'wave21_wrong_patch_real_probe_rerun.json'

CONDITIONS = ["T2D-T", "T3D-Strict", "T3D-Escalate", "T2A-T", "T3A-T"]

# The seven files frozen in wave2_freeze_manifest plus the additional frozen
# protocol modules E1 scoring/audit reads from. E1 adds ev1_* files but those
# are analysis-only and recorded separately.
PROTOCOL_CODE = [
    'evidence/prompts.py',
    'evidence/views.py',
    'evidence/server.py',
    'evidence/phase3_run.py',
    'evidence/gold_w2.py',
    'evidence/metrics_w2.py',
    'evidence/store.py',
    'evidence/metrics2.py',
    'evidence/gap_w2.py',
    'evidence/visibility.py',
    'evidence/probes.py',
    'evidence/builder.py',
]


def sha_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_text_normalized(path: Path) -> str:
    """Mirror metrics_w2.load_w2_gold: newline-normalised utf-8 text."""
    return hashlib.sha256(
        path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def file_entry(path: Path, *, normalized: bool = False) -> dict:
    e = {'path': str(path.relative_to(ROOT)) if path.is_relative_to(ROOT)
         else path.name,
         'exists': path.exists(),
         'bytes': path.stat().st_size if path.exists() else 0,
         'sha256_bytes': sha_bytes(path) if path.exists() else None}
    if normalized:
        e['sha256_newline_normalized'] = sha_text_normalized(path)
    return e


def main() -> None:
    manifest = json.loads(W2_MANIFEST.read_text(encoding='utf-8'))
    expected_fp = manifest['experiment']['prompt_fingerprints_v2']

    # --- prompt fingerprints (recomputed, asserted equal) -----------------
    fingerprints = {c: ternary_prompt_fingerprint_v2(c) for c in CONDITIONS}
    fp_match = {c: fingerprints[c] == expected_fp[c] for c in CONDITIONS}
    if not all(fp_match.values()):
        raise SystemExit(f'PROMPT DRIFT vs wave2 manifest: {fp_match}')

    # --- fixtures / gold / raw --------------------------------------------
    fixtures = []
    fixture_entries = []
    for fp in FIXTURE_LISTS:
        rows = list(read_jsonl(str(fp)))
        fixtures.extend(rows)
        fixture_entries.append({**file_entry(fp), 'n_rows': len(rows)})
    if len(fixtures) != 22:
        raise SystemExit(f'expected 22 fixtures across 3 lists, got {len(fixtures)}')
    # Mirror fixtures share model:instance id but serve DISTINCT artifacts, so
    # identity is the full (scenario, id, served_artifact_id) gold join key.
    fkeys = [(f['scenario'], f['id'], f['served_artifact_id'])
             for f in fixtures]
    if len(set(fkeys)) != 22:
        raise SystemExit('duplicate (scenario,id,served_artifact_id) fixture key')
    issues = sorted({f['instance_id'] for f in fixtures})

    gold_entry = file_entry(GOLD, normalized=True)
    gold_rows = list(read_jsonl(str(GOLD)))
    gold_entry['n_rows'] = len(gold_rows)
    if len(gold_rows) != 22:
        raise SystemExit(f'expected 22 gold rows, got {len(gold_rows)}')
    # every served artifact in fixtures must have a gold row under the full
    # join key used by metrics_w2 (scenario, id, served_artifact_id)
    gkeys = {(g['scenario'], g['id'], g['served_artifact_id']) for g in gold_rows}
    missing = [(f['scenario'], f['id'], f['served_artifact_id'])
               for f in fixtures
               if (f['scenario'], f['id'], f['served_artifact_id']) not in gkeys]
    if missing:
        raise SystemExit(f'gold rows missing for {missing}')

    raw_entries = [{**file_entry(rp), 'n_rows': len(list(read_jsonl(str(rp))))}
                   for rp in RAW_ROWS]
    raw_by_id = {r['id']: r for r in read_jsonl(str(RAW_ROWS[0]))}
    raw_cover = sorted({f['id'] for f in fixtures} - set(raw_by_id))
    if raw_cover:
        raise SystemExit(f'raw_rows.jsonl missing ids: {raw_cover}')

    # --- corrected Wave-2.1 results (110 cells) ---------------------------
    corrected = file_entry(CORRECTED_RESULTS)
    corrected_rows = list(read_jsonl(str(CORRECTED_RESULTS)))
    corrected['n_rows'] = len(corrected_rows)
    corrected['n_mock'] = sum(1 for r in corrected_rows if r.get('mock'))
    corrected['n_error'] = sum(1 for r in corrected_rows if r.get('error'))
    if len(corrected_rows) != 110:
        raise SystemExit(f'expected 110 corrected rows, got {len(corrected_rows)}')

    # --- protocol code -----------------------------------------------------
    code_entries = []
    manifest_by_path = {x['path']: x for x in
                        manifest['files']['protocol_code_frozen_at_freeze']}
    for rel in PROTOCOL_CODE:
        p = ROOT / rel
        e = file_entry(p)
        if rel in manifest_by_path:
            frozen = manifest_by_path[rel]['sha256']
            e['matches_wave2_manifest'] = (e['sha256_bytes'] == frozen)
            if not e['matches_wave2_manifest']:
                raise SystemExit(f'FROZEN CODE DRIFT: {rel}')
        else:
            e['matches_wave2_manifest'] = None  # added for E1 audit scope
        code_entries.append(e)

    # --- tool-permission matrix: real server, 22 x 5, throwaway copy ------
    errors, lines = cross_check_http(str(STORE), fixtures,
                                     conditions=CONDITIONS, verbose=False)
    permission = {
        'check': 'evidence.visibility.cross_check_http(22 fixtures x 5)',
        'cells_checked': 22 * 5,
        'n_report_lines': len(lines),
        'n_errors': len(errors),
        'errors': errors,
        'passed': not errors,
    }

    out = {
        'freeze_id': 'groundedreview-ev1-protocol-frozen-2026-10-22',
        'title': 'E1 cross-model external validation: frozen Wave-2.1 protocol '
                 'inputs (no paid API call authorised by this freeze)',
        'frozen_at': '2026-10-22',
        'inherits': {
            'wave2_freeze_manifest': str(W2_MANIFEST.relative_to(ROOT)),
            'wave2_freeze_id': manifest['freeze_id'],
            'wave2_manifest_sha256_bytes': sha_bytes(W2_MANIFEST),
            'correction_record': str(WRONG_PATCH_RERUN.name),
            'correction_record_sha256_bytes': (sha_bytes(WRONG_PATCH_RERUN)
                                               if WRONG_PATCH_RERUN.exists()
                                               else None),
        },
        'experiment': {
            'prompt_version': 'p3-ternary-v2',
            'conditions': CONDITIONS,
            'n_fixtures': 22,
            'n_independent_issues': len(issues),
            'independent_issues': issues,
            'cells_per_model': 110,
            'session_isolation': 'one fresh server session per cell',
            'frozen_subject_model_wave21': 'deepseek-flash',
            'completion_cap_wave21': manifest['experiment']['completion_cap'],
            'reasoning_wave21': manifest['experiment']['reasoning_effort'],
            'gold_version': 'w2-gold-v1',
            'mutation_policy': [
                'Gold, fixtures, prompt semantics, tool permissions and '
                'scoring code are FROZEN; no adjustment from new-model output.',
                'Only model-profile API adaptation (ev1_adapters.py) is added.',
                'No new issues in E1 (issue expansion is E2 only).',
            ],
        },
        'prompt_fingerprints_v2': fingerprints,
        'prompt_fingerprints_match_wave2_manifest': fp_match,
        'files': {
            'fixture_lists': fixture_entries,
            'gold': gold_entry,
            'raw_rows': raw_entries,
            'corrected_wave21_results': corrected,
            'protocol_code': code_entries,
        },
        'tool_permission_matrix': permission,
        'notes': 'Byte sha over exact disk bytes; gold additionally hashed '
                 'newline-normalised to match metrics_w2.load_w2_gold. '
                 'Generated offline; no LLM API used.',
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outp = OUT_DIR / 'ev1_protocol_freeze.json'
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding='utf-8')
    print(f'wrote {outp}')
    print(f'fixtures={len(fixtures)} issues={len(issues)} '
          f'gold={len(gold_rows)} corrected_rows={len(corrected_rows)}')
    print(f'prompt fingerprints match: {all(fp_match.values())}')
    print(f'permission matrix errors: {len(errors)}')


if __name__ == '__main__':
    main()
