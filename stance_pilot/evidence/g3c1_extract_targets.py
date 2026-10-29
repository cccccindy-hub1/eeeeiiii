"""G3-C.1 task 3 — extract the single selected target raw row per pilot issue
(frozen target_row_id) plus a digest used to author the mandatory
human-written symptom probes. No execution, no API.

  uv run --offline --python 3.9 -m evidence.g3c1_extract_targets
"""
from __future__ import annotations

import json

from evidence import g3c1_common as C

SEL = C.OUT_SELECTION / 'g3c1_selection.json'
RAW_OUT = C.OUT_RAW / 'g3c1_target_rows.jsonl'
DIGEST_OUT = C.OUT_RAW / 'g3c1_target_digest.json'


def changed_files(patch: str):
    return sorted({l[6:] for l in patch.splitlines()
                   if l.startswith('+++ b/')})


def main():
    sel = json.loads(SEL.read_text(encoding='utf-8'))
    pilot = {iid for iid in sel['pilot_instance_ids']}
    detail = {e['instance_id']: e for e in sel['eligible_detail']}
    pool = C.read_jsonl(C.POOL)
    rows, digest = [], {}
    for r in pool:
        iid = r['instance_id']
        if iid not in pilot:
            continue
        if r['id'] != detail[iid]['target_row_id']:
            continue
        rows.append(r)
        digest[iid] = {
            'id': r['id'], 'generator_model': r['generator_model'],
            'resolved_in_dataset': r['resolved'],
            'base_commit': r['base_commit'],
            'FAIL_TO_PASS': r['FAIL_TO_PASS'],
            'PASS_TO_PASS_n': len(r['PASS_TO_PASS']),
            'PASS_TO_PASS': r['PASS_TO_PASS'],
            'candidate_changed_files': changed_files(r['model_patch']),
            'test_patch_files': changed_files(r['test_patch']),
            'problem_statement': r['problem_statement'],
            'pilot_queue_label': detail[iid]['pilot_queue_label'],
            'primary_stratum': detail[iid]['primary_stratum'],
            'signals': detail[iid]['signals']}
    rows.sort(key=lambda r: r['instance_id'])
    C.write_jsonl(RAW_OUT, rows)
    digest = {k: digest[k] for k in sorted(digest)}
    C.write_canonical(DIGEST_OUT, digest)
    missing = pilot - {r['instance_id'] for r in rows}
    if missing:
        C.record_failure('extract_targets', 'MULTI',
                         {'missing_target_rows': sorted(missing)})
        raise SystemExit('missing target rows: %s' % sorted(missing))
    print('target rows:', len(rows), '->', RAW_OUT.relative_to(C.HERE))
    for iid, d in digest.items():
        print('\n====', iid, '|', d['pilot_queue_label'], d['primary_stratum'],
              '| gen', d['generator_model'], '| resolved',
              d['resolved_in_dataset'])
        print(' base:', d['base_commit'])
        print(' F2P:', d['FAIL_TO_PASS'])
        print(' P2P n:', d['PASS_TO_PASS_n'])
        print(' candidate files:', d['candidate_changed_files'][:10])
        print(' test files:', d['test_patch_files'])
        print(' problem:', ' '.join(d['problem_statement'].split())[:600])


if __name__ == '__main__':
    main()
