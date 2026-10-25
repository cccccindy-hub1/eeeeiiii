"""Cache the raw SWE-Review-Bench rows for selected sympy instances locally.

One row per (generator split, instance): candidates from different generators are
distinct patches for the same issue and stay separate units.
"""
import argparse, json
from datasets import load_dataset
from pilot import write_jsonl

def as_list(v):
    # these fields can arrive as str, double-encoded str, or already a list
    while isinstance(v, str):
        v = json.loads(v)
    return list(v)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default='sympy/sympy')
    ap.add_argument('--ids', default='')  # optional comma list
    ap.add_argument('--out', default='evidence_store/raw_rows.jsonl')
    a = ap.parse_args()
    want = set(x for x in a.ids.split(',') if x)
    ds = load_dataset('Lego-X/SWE-Review-Bench')
    rows = []
    for split in ds:
        for r in ds[split]:
            if r['repo'] != a.repo:
                continue
            if want and r['instance_id'] not in want:
                continue
            rows.append({
                'id': f"{split}:{r['instance_id']}", 'split': split,
                'instance_id': r['instance_id'], 'repo': r['repo'],
                'base_commit': r['base_commit'], 'version': r.get('version'),
                'image_name': r.get('image_name'), 'difficulty': r.get('difficulty'),
                'generator_model': r.get('generator_model'), 'resolved': r['resolved'],
                'problem_statement': r['problem_statement'], 'model_patch': r['model_patch'],
                'test_patch': r['test_patch'],
                'FAIL_TO_PASS': as_list(r['FAIL_TO_PASS']),
                'PASS_TO_PASS': as_list(r['PASS_TO_PASS']),
            })
    write_jsonl(a.out, rows)
    print(f'wrote {len(rows)} rows -> {a.out}')

if __name__ == '__main__':
    main()
