"""Submission-finalization v2 freeze manifest (read-only; hashes only).

Extends the historical v1 freeze manifest without modifying it. Adds:
  - analysis_v2/ independent verification products
  - evidence/g4_verify_v2.py
  - the v4 submission manuscript tree (incl. main_v4_submission.pdf)
v1 raw/traces/frozen inputs are re-listed by hash so cross-version equality
can be checked, but no historical file is written.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
FROZ = os.path.join(ROOT, 'evidence_store_g4_sufficiency')
LIVE = os.path.join(ROOT, 'evidence_store_g4_live')
PAPER = os.path.join(ROOT, 'paper_sprint')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def relmap(patterns, base):
    out = {}
    for pat in patterns:
        for f in sorted(glob.glob(os.path.join(base, pat), recursive=True)):
            if os.path.isfile(f):
                r = os.path.relpath(f, ROOT).replace('\\', '/')
                out[r] = {'sha256': sha(f), 'bytes': os.path.getsize(f)}
    return out


def main():
    v2 = json.load(open(os.path.join(
        LIVE, 'analysis_v2', 'g4_verification_v2.json'), encoding='utf-8'))
    v1_manifest = json.load(open(os.path.join(
        LIVE, 'freeze', 'g4live_freeze_manifest.json'), encoding='utf-8'))

    files = {}
    # v2 products and code
    files.update(relmap(['analysis_v2/**/*'], LIVE))
    files.update(relmap(['evidence/g4_verify_v2.py',
                         'evidence/g4_freeze_manifest_v2.py'], ROOT))
    # immutable evidence re-listed (cross-check vs v1 manifest hashes)
    files.update(relmap(['raw/live/*.json'], LIVE))
    files.update(relmap(['traces/**/*'], LIVE))
    files.update(relmap(['runs/*'], LIVE))
    files.update(relmap([
        'g4_fixed_bundles.jsonl', 'g4_cell_manifest.jsonl',
        'g4_payload_hashes.jsonl', 'g4_identifiability_gate.json',
        'g4_identifiability_gate.md', 'G4_PREREGISTRATION_v1.md',
        'G4_PREREGISTRATION_ADDENDUM_v1.1.md',
    ], FROZ))
    # v4 manuscript
    files.update(relmap([
        'main.tex', 'references.bib',
        'sections/*.tex', 'figures/*.tex',
        'main_v3_g4_controlled.pdf', 'main_v4_submission.pdf',
    ], os.path.join(PAPER, 'latex_g4')))
    # human adjudication handoff state
    files.update(relmap([
        'human/HUMAN_ADJUDICATION_HANDOFF.md',
        'human/human_review_tracking.csv',
        'human/author_quick_review_note_2026-11-01.md',
        'human/human_review_workbench.html',
    ], PAPER))
    # submission readiness record
    files.update(relmap(['SUBMISSION_READINESS_v4.md'], PAPER))

    # every shared file must hash identically to the v1 manifest
    shared = set(files) & set(v1_manifest['files'])
    hash_drift = sorted(
        r for r in shared
        if files[r]['sha256'] != v1_manifest['files'][r]['sha256'])

    ver = v2['verification']
    manifest = {
        'manifest': 'g4-live-freeze-manifest-v2-submission',
        'supersedes_nothing': 'g4live_freeze_manifest.json (v1) remains the '
                              'frozen record; this is a superset index.',
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'g4_version': 'g4-sufficiency-iv-v1.1',
        'paper_version': 'Paper Sprint v4 (main_v4_submission.pdf)',
        'analysis_v2': 'analysis_v2/g4_verification_v2.{json,md}',
        'verification_summary': {
            'problems': ver['problems'],
            'bundle_sha256_recompute': ver['bundle_sha256_recompute'],
            'trace_matches_raw': ver['trace_matches_raw'],
            'cost_total_recomputed_usd': ver['cost_total_recomputed_usd'],
            'served': ver['served'],
            'errors': ver['errors'],
            'retries': ver['retries'],
        },
        'stats_v2_summary': {
            'GPT_H1_p': v2['stats']['gpt-4.1-mini']['H1'][
                'two_sided_exact_p_exact'],
            'GPT_paired_diff': v2['stats']['gpt-4.1-mini']['H1'][
                'paired_diff_UA_minus_UB'],
            'GPT_bootstrap95': v2['stats']['gpt-4.1-mini']['H1'][
                'bootstrap95'],
            'GPT_CP95_B_U': v2['stats']['gpt-4.1-mini'][
                'clopper_pearson95_U']['B'],
            'DS_H1_p': v2['stats']['deepseek-flash']['H1'][
                'two_sided_exact_p_exact'],
            'between_model_difference': v2['between_model']['difference'],
            'between_model_bootstrap95':
                v2['between_model']['issue_bootstrap95'],
            'interaction_DiD': v2['interaction'][
                'interaction_DiD_GPT_minus_DS']['point'],
            'interaction_DiD_bootstrap95': v2['interaction'][
                'interaction_DiD_GPT_minus_DS']['bootstrap95'],
        },
        'prereg_deviation_closed': 'v1 reported Wilson where CP was '
                                   'pre-registered; v2 reports CP; Wilson '
                                   'remains only in frozen v1.',
        'human_gold': '18/18 PENDING, adjudicated=NO; FR1/FR2 PENDING; '
                      '19346 separate arbitration PENDING; all gold '
                      'PROVISIONAL, no labels fabricated or upgraded.',
        'git_committed': False,
        'shared_files_checked_against_v1': len(shared),
        'hash_drift_vs_v1': hash_drift,
        'n_files_hashed': len(files),
        'files': files,
    }
    out = os.path.join(LIVE, 'freeze', 'g4live_freeze_manifest_v2.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print('wrote', os.path.relpath(out, ROOT),
          'files=', len(files),
          'shared_with_v1=', len(shared),
          'hash_drift=', len(hash_drift))


if __name__ == '__main__':
    main()
