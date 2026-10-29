"""G3-A.1 task 12 — freeze manifest & G3-A zero-change verification (zero API).

1) Re-hash every file listed in the G3-A freeze manifest and assert it is
   byte-identical (proof that A.1 did not modify frozen G3-A raw data).
2) Hash all NEW Gate 3-A.1 artefacts (evidence_store_g3a1/** and the new
   sidecar evidence_store_g3a/gold/g3a1_condition_gold.jsonl), excluding this
   manifest itself (self-hash avoidance, same fix as g3a_freeze).
Writes evidence_store_g3a1/g3a1_freeze_manifest.json with a changelog.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
G3A_MANIFEST = G3A / 'g3a_freeze_manifest.json'
OUT = G3A1 / 'g3a1_freeze_manifest.json'

# A.1 introduces exactly one new file INSIDE the frozen G3-A tree (a sidecar);
# all other new artefacts live under evidence_store_g3a1/.
G3A_NEW_SIDECARS = ['gold/g3a1_condition_gold.jsonl']


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    frozen = json.load(open(G3A_MANIFEST, encoding='utf-8'))
    # 1) verify G3-A frozen files unchanged
    unchanged, changed, missing = [], [], []
    for f in frozen['files']:
        p = G3A / f['path']
        if not p.exists():
            missing.append(f['path'])
        elif sha256_file(p) != f['sha256']:
            changed.append(f['path'])
        else:
            unchanged.append(f['path'])
    assert not changed, f'FROZEN G3-A FILES MODIFIED: {changed}'
    assert not missing, f'FROZEN G3-A FILES MISSING: {missing}'

    # 2) confirm the sidecar really is new (not colliding with a frozen path)
    frozen_paths = {f['path'] for f in frozen['files']}
    for s in G3A_NEW_SIDECARS:
        assert s not in frozen_paths, f'sidecar collides with frozen file: {s}'

    # 3) hash all new A.1 artefacts, excluding this manifest
    new_files = []
    for base, prefix in ((G3A1, 'evidence_store_g3a1'),
                         (G3A, 'evidence_store_g3a')):
        for p in sorted(base.rglob('*')):
            if not p.is_file():
                continue
            rel = p.relative_to(HERE).as_posix()
            if p == OUT:
                continue
            if prefix == 'evidence_store_g3a':
                sub = p.relative_to(G3A).as_posix()
                if sub not in G3A_NEW_SIDECARS:
                    continue  # only the declared new sidecar from the g3a tree
            new_files.append({
                'path': rel,
                'bytes': p.stat().st_size,
                'sha256': sha256_file(p),
            })

    doc = {
        'freeze_id': 'groundedreview-gate3a1-adjudication-prep-frozen',
        'gate': 'G3-A.1 (independent gold adjudication prep + G3-B pre-audit)',
        'api_budget_used_usd': 0.0,
        'paid_model_calls': 0,
        'g3a_original_data_modified': False,
        'g3a_frozen_files_verified': len(unchanged),
        'g3a_frozen_files_changed': changed,
        'g3a_frozen_files_missing': missing,
        'g3a_new_sidecars_in_frozen_tree': G3A_NEW_SIDECARS,
        'new_file_count': len(new_files),
        'files': new_files,
        'gold_tier': 'PROVISIONAL (mechanically adjudicated; human-agreement '
                     'pending; annotator2 NOT obtained; n_independent=1)',
        'natural_oracle_distribution': '7 ACCEPT / 3 REJECT / 0 NEED_EVIDENCE',
        'condition_projection': {
            'T2D-T': '10/10 NEED_EVIDENCE',
            'T3D-Strict': '10/10 NEED_EVIDENCE',
            'T3D-Escalate': '7 ACCEPT / 3 REJECT',
            'T2A-T': '7 ACCEPT / 3 REJECT',
            'T3A-T': '7 ACCEPT / 3 REJECT',
            'oracle_condition_divergences': 20,
        },
        'changelog': [
            'G3-A frozen raw data, rules, and E1/CEE/EAL/R1/X/Consolidation '
            'artifacts left byte-identical (all %d sha256 reverified).'
            % len(unchanged),
            'NEW code (evidence/): g3a1_conditions.py, g3a1_dossiers.py, '
            'g3a1_adjudication.py, g3a1_stats_plan.py, g3a1_budget.py, '
            'g3a1_freeze.py.',
            'NEW sidecar inside evidence_store_g3a/gold/: '
            'g3a1_condition_gold.jsonl (condition projection; does not alter '
            'g3a_gold.jsonl).',
            'NEW artefacts under evidence_store_g3a1/: blinded annotator-2 '
            'dossiers + coding manual (no model output, no annotator-1 label), '
            'sealed blind-code map, adjudication status ledger + protocol, '
            'dossier leakage audit, Gate 3-B minimal protocol, frozen stats '
            'plan, and budget/BudgetGuard plan.',
            'No labels changed; no mirror fixtures; no class balancing. Any '
            'future adjudication revision must be a NEW versioned file with a '
            'changelog entry; frozen files remain append-only/immutable.',
            'No git commit made.',
        ],
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2,
                              sort_keys=True) + '\n', encoding='utf-8')
    print('G3-A files verified unchanged:', len(unchanged))
    print('changed:', changed, 'missing:', missing)
    print('new A.1 files hashed:', len(new_files))
    print('manifest ->', OUT)


if __name__ == '__main__':
    main()
