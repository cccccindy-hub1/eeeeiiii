"""Build evidence_store/pilot_samples.jsonl: truth + reviewer-facing inputs.

Ground-truth fields are kept for offline scoring only; the runner must never place
issue_addressed / merge_acceptable / label_class into a prompt.
"""
import argparse

from pilot import read_jsonl, write_jsonl

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--truth', default='evidence_store/truth.jsonl')
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--out', default='evidence_store/pilot_samples.jsonl')
    ap.add_argument('--classes', default='A,B,C')
    a = ap.parse_args()

    raw = {r['id']: r for r in read_jsonl(a.raw)}
    want = set(a.classes.split(','))
    samples = []
    for t in read_jsonl(a.truth):
        if t['label_class'] not in want:
            continue
        r = raw[t['id']]
        samples.append({
            'id': t['id'], 'instance_id': t['instance_id'], 'repo': t['repo'],
            'base_commit': t['base_commit'], 'patch_sha256': t['patch_sha256'],
            'artifact_id': t['artifact_id'],
            'issue': r['problem_statement'], 'patch': r['model_patch'],
            'resolved': r['resolved'],
            'issue_addressed': t['issue_addressed'],
            'merge_acceptable': t['merge_acceptable'],
            'label_class': t['label_class'],
        })
    write_jsonl(a.out, samples)
    from collections import Counter
    print(f'wrote {len(samples)} samples -> {a.out}', dict(Counter(s['label_class'] for s in samples)))

if __name__ == '__main__':
    main()
