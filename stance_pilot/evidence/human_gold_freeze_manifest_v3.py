"""Human-gold extension freeze manifest v3 (read-only; hashes only).

Indexes the human adjudication evidence and the v5 manuscript, and
cross-checks every file shared with the G4 v2 freeze manifest. Evidence
stores must hash identically; only manuscript sources and the readiness
record are allowed to differ (deliberate v4 -> v5 update), and the script
fails loudly on any other drift. Writes only to
evidence_store_human_gold/freeze/.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
HUMAN = os.path.join(ROOT, 'evidence_store_human_gold')
LIVE = os.path.join(ROOT, 'evidence_store_g4_live')
PAPER = os.path.join(ROOT, 'paper_sprint')
ALLOWED_CHANGE_PREFIXES = (
    'paper_sprint/latex_g4/',
    'paper_sprint/SUBMISSION_READINESS_v4.md',
)


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
        LIVE, 'freeze', 'g4live_freeze_manifest_v2.json'), encoding='utf-8'))
    adj2 = json.load(open(os.path.join(
        HUMAN, 'adjudication_v2',
        'human_gold_adjudication_v2.json'), encoding='utf-8'))

    files = {}
    # human gold stores (exclude this manifest's own output dir)
    files.update(relmap(['adjudication_v1/**/*',
                         'adjudication_v2/**/*'], HUMAN))
    # returned workbench artifacts and human code
    files.update(relmap(['human/returns/**/*'], PAPER))
    files.update(relmap([
        'evidence/human_gold_adjudication_v1.py',
        'evidence/human_gold_adjudication_v2.py',
        'evidence/human_gold_freeze_manifest_v3.py',
    ], ROOT))
    # manuscript tree and all versioned PDFs
    files.update(relmap([
        'main.tex', 'references.bib',
        'sections/*.tex', 'figures/*.tex',
        'main_v1_frozen_g3b3.pdf', 'main_v3_g4_controlled.pdf',
        'main_v4_submission.pdf', 'main_v5_human_gold.pdf',
    ], os.path.join(PAPER, 'latex_g4')))
    files.update(relmap(['SUBMISSION_READINESS_v4.md'], PAPER))

    shared = set(files) & set(v2['files'])
    changed = sorted(r for r in shared
                     if files[r]['sha256'] != v2['files'][r]['sha256'])
    illegal = [r for r in changed
               if not r.startswith(ALLOWED_CHANGE_PREFIXES)]
    unchanged = sorted(shared - set(changed))

    # historical frozen PDFs must never move: check against every prior
    # manifest that indexed them (v1 predates the v3 PDF naming)
    prior = [v2['files']]
    v1_path = os.path.join(LIVE, 'freeze', 'g4live_freeze_manifest.json')
    if os.path.exists(v1_path):
        prior.append(json.load(open(v1_path, encoding='utf-8'))['files'])
    for frozen_pdf in ('paper_sprint/latex_g4/main_v1_frozen_g3b3.pdf',
                       'paper_sprint/latex_g4/main_v3_g4_controlled.pdf',
                       'paper_sprint/latex_g4/main_v4_submission.pdf'):
        for prior_files in prior:
            if frozen_pdf in prior_files:
                assert files[frozen_pdf]['sha256'] == \
                    prior_files[frozen_pdf]['sha256'], \
                    f'frozen PDF changed: {frozen_pdf}'

    s1 = adj2['scenarios']['S1_human_reviewed_ARB1']
    manifest = {
        'manifest': 'human-gold-freeze-manifest-v3',
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'paper_version': 'Paper Sprint v5 (main_v5_human_gold.pdf, 25 pages)',
        'human_return_date': '2026-11-08',
        'identity': adj2['identity'],
        'focused_reviews': {
            k: {'human_choice': v['human_choice'],
                'rubric_amendment': v['rubric_amendment']}
            for k, v in adj2['focused_reviews'].items()},
        'agreement': adj2['agreement'],
        's1_rejects': s1['rejects'],
        's1_H1_unchanged': s1['H1_unchanged'],
        's1_exploratory_unchanged': s1['exploratory_contrasts_unchanged'],
        'gold_promotion': 'NOT_PROMOTED; signed attestation pending; '
                          '15875 disagreement open',
        'v2_shared_files_checked': len(shared),
        'v2_unchanged_files': len(unchanged),
        'v2_deliberately_changed_files': changed,
        'illegal_drift': illegal,
        'n_files_hashed': len(files),
        'files': files,
    }
    out_dir = os.path.join(HUMAN, 'freeze')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'human_gold_freeze_manifest_v3.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print('wrote', os.path.relpath(out, ROOT))
    print('files=', len(files), 'shared_with_v2=', len(shared),
          'unchanged=', len(unchanged), 'changed=', len(changed),
          'illegal_drift=', len(illegal))
    if illegal:
        raise SystemExit('ILLEGAL DRIFT: ' + ', '.join(illegal))


if __name__ == '__main__':
    main()
