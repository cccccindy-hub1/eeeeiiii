"""CEE v1.1 freeze manifest writer (zero network, zero paid calls).

Computes and records the CEE v1.1 frozen identity: hashes of every v1.1 code
module, the reused v1 module, the 22 (byte-identical) bundles, cee_gold, the
v1 build manifest and plan, both prompt fingerprints, the unified output mode,
guard prices, and the authorisation reference. Writing this file does NOT
modify any v1 artifact.

    uv run --python 3.13 -m evidence.cee_freeze_v11
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.cee_run import (_sha256_bytes, _sha256_file, CEE_DIR,
                              GOLD_PATH, PLAN_PATH, MANIFEST_PATH,
                              BUNDLES_DIR)
from evidence import cee_protocol as v1
from evidence import cee_protocol_v11 as cee
from evidence.cee_run_v11 import PROFILES

HERE = Path(__file__).resolve().parent
FREEZE_PATH = CEE_DIR / 'cee_v1_1_freeze_manifest.json'


def build_freeze() -> dict:
    v1_manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    bundle_hashes = {b['bundle_id']: b['bundle_sha256']
                     for b in v1_manifest['bundles']}
    # Verify on-disk bundle bytes still match the v1 manifest (reused as-is).
    disk_match = all(
        _sha256_file(BUNDLES_DIR / f'{bid}.txt') == sha
        for bid, sha in bundle_hashes.items())
    profiles = {}
    for name, p in PROFILES.items():
        profiles[name] = {
            'model_requested': p['model'],
            'base_url': p['base_url'],
            'price_in_per_1m_peak_guard': p['price_in'],
            'price_out_per_1m_peak_guard': p['price_out'],
            'response_format': cee.RESPONSE_FORMAT_JSON_OBJECT,
            'temperature': 0,
            'max_tokens_completion_cap': 4096,
            'extra_body_keys': sorted(p['extra_body'].keys()),
            'tools': 'none',
            'e1_served_model_id': p['e1_served_model_id'],
            'result_file': p['out_file'],
        }
    return {
        'document': 'GroundedReview CEE v1.1 frozen identity - Unified JSON '
                    'Mode amendment',
        'protocol_version': cee.CEE_PROTOCOL_VERSION,
        'predecessor_version': cee.PREDECESSOR_VERSION,
        'condition': cee.CEE_CONDITION,
        'amendment': {
            'date': '2026-10-24',
            'change': 'response_format unified to json_object on BOTH '
                      'providers; json_schema no longer requested; plain_text '
                      'fallback forbidden; five-property schema retained as a '
                      'strict LOCAL validation contract with no field repair',
            'authorisation': 'written user approval "CEE v1.1 - Unified JSON '
                             'Mode", 44 calls, hard cap $1.00',
            'predecessor_blocked_by': cee.COMPATIBILITY_REPORT,
            'pooling_with_v1': 'forbidden: v1 and v1.1 are separate frozen '
                               'experiments',
        },
        'output_mode': cee.OUTPUT_MODE,
        'response_format_sent': cee.RESPONSE_FORMAT_JSON_OBJECT,
        'server_schema_enforced': False,
        'local_validation': {
            'contract_name': cee.CEE_DECISION_SCHEMA['name'],
            'contract_sha256': _sha256_bytes(
                canonical_dumps(cee.CEE_DECISION_SCHEMA).encode('utf-8')),
            'five_required_keys': list(cee.REQUIRED_KEYS),
            'on_violation': 'scored INVALID/AMBIGUOUS; no auto-completion, '
                            'no coercion, no retry',
        },
        'prompt': {
            'text_identical_to_v1': True,
            'system': cee.SYSTEM_MESSAGE,
            'head': cee.CEE_HEAD,
            'goal': cee.CEE_GOAL,
            'contains_word_json': 'json' in (
                cee.SYSTEM_MESSAGE + cee.CEE_HEAD).lower(),
            'fingerprint_v11': cee.cee_prompt_fingerprint(),
            'fingerprint_v1': v1.cee_prompt_fingerprint(),
        },
        'reused_assets': {
            'bundles_dir': str(BUNDLES_DIR),
            'n_bundles': len(bundle_hashes),
            'bundles_byte_identical_to_v1': disk_match,
            'bundle_sha256_by_id': bundle_hashes,
            'cee_gold_sha256': _sha256_file(GOLD_PATH),
            'cee_build_manifest_sha256': _sha256_file(MANIFEST_PATH),
            'cee_plan_sha256': _sha256_file(PLAN_PATH),
        },
        'models': profiles,
        'budget': {'hard_cap_total_usd': 1.00, 'per_model_usd': 0.50,
                   'n_planned_calls': 44,
                   'guard': 'pre-call conservative upper bound; BudgetGuard '
                            'from frozen phase3_run; peak prices used'},
        'code_sha256': {
            'cee_protocol.py (v1, untouched)':
                _sha256_file(HERE / 'cee_protocol.py'),
            'cee_protocol_v11.py':
                _sha256_file(HERE / 'cee_protocol_v11.py'),
            'cee_run_v11.py':
                _sha256_file(HERE / 'cee_run_v11.py'),
            'cee_selftest_v11.py':
                _sha256_file(HERE / 'cee_selftest_v11.py'),
            'cee_freeze_v11.py':
                _sha256_file(HERE / 'cee_freeze_v11.py'),
        },
        'v1_preservation': {
            'cee_protocol_v1_unchanged': True,
            'compatibility_stop_report_sha256':
                _sha256_file(CEE_DIR / cee.COMPATIBILITY_REPORT),
        },
    }


def main():
    fx = build_freeze()
    if not fx['reused_assets']['bundles_byte_identical_to_v1']:
        raise SystemExit('FREEZE ABORT: on-disk bundles differ from v1 '
                         'manifest; v1.1 must reuse the frozen bundles')
    FREEZE_PATH.write_text(
        json.dumps(fx, indent=2, ensure_ascii=False, sort_keys=True) + '\n',
        encoding='utf-8')
    print(f'CEE v1.1 freeze manifest -> {FREEZE_PATH.name}')
    print(f"  fingerprint_v11 = {fx['prompt']['fingerprint_v11']}")
    print(f"  bundles byte-identical to v1: "
          f"{fx['reused_assets']['bundles_byte_identical_to_v1']}")
    print('  offline only: zero network / zero paid calls')


if __name__ == '__main__':
    main()
