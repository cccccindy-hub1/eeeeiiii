"""G3-A — extract the single selected target raw row per cohort issue into the
G3-A working store, plus a short digest (problem statement head, F2P, changed
files) used to author the mandatory human-written symptom probes.

No execution, no API; reads the cached pool + frozen selection only.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL = ROOT / 'evidence_store' / 'wave2_candidate_pool.jsonl'
SEL = ROOT / 'evidence_store_g3a' / 'selection' / 'g3a_selection.json'
OUTDIR = ROOT / 'evidence_store_g3a' / 'raw'
OUTDIR.mkdir(parents=True, exist_ok=True)
RAW = OUTDIR / 'g3a_target_rows.jsonl'
DIGEST = OUTDIR / 'g3a_target_digest.json'


def changed_files(patch):
    return [l[6:] for l in patch.splitlines() if l.startswith('+++ b/')]


def main():
    sel = json.loads(SEL.read_text(encoding='utf-8'))
    cohort = {e['instance_id']: e for e in sel['cohort']}
    pool = [json.loads(l) for l in
            POOL.read_text(encoding='utf-8').splitlines() if l.strip()]
    rows, digest = [], {}
    for r in pool:
        e = cohort.get(r['instance_id'])
        if not e:
            continue
        if r['id'] != e['target_row_id']:
            continue
        rows.append(r)
        digest[r['instance_id']] = {
            'id': r['id'], 'generator_model': r['generator_model'],
            'resolved_in_dataset': r['resolved'],
            'base_commit': r['base_commit'],
            'FAIL_TO_PASS': r['FAIL_TO_PASS'],
            'PASS_TO_PASS_n': len(r['PASS_TO_PASS']),
            'candidate_changed_files': changed_files(r['model_patch']),
            'test_patch_files': changed_files(r['test_patch']),
            'problem_statement': r['problem_statement']}
    RAW.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows)
                   + '\n', encoding='utf-8')
    DIGEST.write_text(json.dumps(digest, ensure_ascii=False, indent=2),
                      encoding='utf-8')
    print('target rows:', len(rows), '->', RAW)
    for iid, d in digest.items():
        print('\n====', iid, '| gen', d['generator_model'],
              '| resolved', d['resolved_in_dataset'])
        print(' F2P:', d['FAIL_TO_PASS'])
        print(' candidate files:', d['candidate_changed_files'][:8])
        print(' test files:', d['test_patch_files'])
        print(' problem:', ' '.join(d['problem_statement'].split())[:400])


if __name__ == '__main__':
    main()
