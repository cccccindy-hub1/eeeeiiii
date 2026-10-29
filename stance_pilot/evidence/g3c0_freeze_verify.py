"""Gate G3-C.0 task 1 — freeze and independently re-verify the accepted
G3-B.4 products (report, per-issue audit, reason coding, result hashes) and
the G3-B.3 parent pins. READ-ONLY: nothing historical is rewritten.

    uv run --python 3.13 -m evidence.g3c0_freeze_verify
"""
from __future__ import annotations

from evidence import g3b4_common as B4
from evidence import g3c0_common as C


def main():
    g3b4 = C.verify_g3b4_freeze(verbose=True)
    g3b3 = B4.verify_g3b3_parent_pins(verbose=True)
    g3b3_rf = B4.verify_g3b3_result_freeze(verbose=False)

    out = {
        'document': 'Gate G3-C.0 task 1: re-verification that the accepted '
                    'G3-B.4 products and the G3-B.3 parents are unchanged',
        'design_version': C.G3C0_DESIGN_VERSION,
        'api_calls_made': 0,
        'g3b4_freeze_reverification': g3b4,
        'g3b3_parent_pins': g3b3,
        'g3b3_result_freeze': {
            'all_pins_match': g3b3_rf['all_pins_match'],
            'n_pass': g3b3_rf['n_pass'], 'n_checks': g3b3_rf['n_checks']},
        'historical_artifacts_modified': False,
        'all_ok': (g3b4['all_ok'] and g3b3['all_ok']
                   and g3b3_rf['all_pins_match']),
        'note': 'G3-B.4 accepted; this only re-hashes its frozen files and '
                'confirms the G3-B.3 anchors. No file under evidence_store_'
                'g3b4 or any earlier gate was written.',
    }
    C.OUT_FREEZE_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_FREEZE_DIR / 'g3c0_task1_g3b4_freeze_reverification.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('all_ok:', out['all_ok'], '->',
          dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
