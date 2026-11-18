"""Write the G4 final freeze manifest (read-only; hashes only)."""
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
    analysis = json.load(open(os.path.join(
        LIVE, 'analysis', 'g4_analysis_report.json'), encoding='utf-8'))
    audit = json.load(open(os.path.join(
        LIVE, 'runs', 'g4live_live_run_audit.json'), encoding='utf-8'))

    files = {}
    files.update(relmap(['raw/live/*.json'], LIVE))
    files.update(relmap(['runs/*'], LIVE))
    files.update(relmap(['traces/**/*'], LIVE))
    files.update(relmap(['analysis/**/*'], LIVE))
    files.update(relmap(['freeze/g4live_fingerprint.json',
                         'freeze/g4live_mock_gate.json',
                         'freeze/g4live_budget_selftest.json',
                         'freeze/REPRODUCE_G4.md'], LIVE))
    # code
    files.update(relmap([
        'evidence/g4_sufficiency_build.py',
        'evidence/g4_live_run.py',
        'evidence/g4_analysis.py',
        'evidence/g4_freeze_manifest.py',
    ], ROOT))
    # frozen parents (must be untouched)
    files.update(relmap([
        'g4_fixed_bundles.jsonl', 'g4_cell_manifest.jsonl',
        'g4_payload_hashes.jsonl', 'g4_identifiability_gate.json',
        'g4_identifiability_gate.md', 'G4_PREREGISTRATION_v1.md',
        'G4_PREREGISTRATION_ADDENDUM_v1.1.md',
    ], FROZ))
    # paper tree (G4 copy) + versioned PDF
    files.update(relmap([
        'main.tex', 'references.bib',
        'sections/*.tex', 'figures/*.tex',
        'main_v3_g4_controlled.pdf',
    ], os.path.join(PAPER, 'latex_g4')))

    n_raw = len(glob.glob(os.path.join(LIVE, 'raw', 'live', '*.json')))
    key_stats = {}
    for m in ('gpt-4.1-mini', 'deepseek-flash'):
        mm = analysis['models'][m]
        key_stats[m] = {
            'served': mm['served'],
            'verdict_matrix': mm['verdict_matrix'],
            'U': mm['unsupported_accept_count'],
            'H1': mm['H1_A_vs_B'],
            'CD': {k: mm['CD_diagnostic'][k] for k in (
                'oracle_match_C', 'oracle_match_D', 'U_C_on_rejects',
                'U_D_on_rejects', 'two_sided_exact_p')},
            'cost_usd': mm['cost_usd'],
        }

    manifest = {
        'manifest': 'g4-live-freeze-manifest-v1',
        'generated_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'g4_version': 'g4-sufficiency-iv-v1.1',
        'runner_version': audit['runner_version'],
        'analysis_version': analysis['analysis'],
        'issues': 18, 'cells_per_issue': 4, 'models': 2,
        'planned_slots': 144, 'live_raw_files': n_raw,
        'one_call_per_cell': audit['model_calls_per_cell'] == 1,
        'retries': audit['retries_per_cell'],
        'new_rows': audit['new_rows'], 'error_rows': audit['error_rows'],
        'served_models_verified': analysis['served_models'],
        'reparse_mismatches': analysis['independent_reparse_vs_runner_mismatches'],
        'stats': key_stats,
        'budget': analysis['budget_audit'],
        'gold_status': audit['gold_status'],
        'human_adjudication': 'annotator2 NOT_OBTAINED; no AI output used '
                              'as human gold; gold not upgraded',
        'git_committed': False,
        'frozen_inputs_modified': False,
        'n_files_hashed': len(files),
        'files': files,
    }
    out = os.path.join(LIVE, 'freeze', 'g4live_freeze_manifest.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print('wrote', os.path.relpath(out, ROOT), 'files=', len(files),
          'raw=', n_raw, 'spent=', audit['total_spend_usd'])


if __name__ == '__main__':
    main()
