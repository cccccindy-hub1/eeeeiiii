"""Pilot metrics from review cells + truth.

Metrics (per condition T0..T3, and overall):

1. Unsupported Acceptance Rate, split by evidence situation:
   - no_evidence:      ACCEPT when no evidence channel was available (T0/T1), or
                       T2/T3 reviewer never fetched/verified anything
   - counter_evidence: ACCEPT while served evidence explicitly contradicts merge
                       acceptability (failing F2P/P2P in the static record, or a
                       linkage check that returned linked=false)
   Kept separate so justified accepts are never lumped with groundless ones.

2. Evidence Verification Success Rate (EVSR): of mismatch cases, fraction where the
   reviewer actually called verify AND observed linked=false AND acted on it
   (evidence_mismatch flag or REJECT). Call rate reported alongside.

3. Merge Decision Accuracy vs merge_acceptable truth, with false-approve and
   false-reject rates reported separately (classes A and C are both unacceptable).

4. Cost per Correct Review: mean total tokens over correct cells per condition.
"""
import argparse, json
from collections import defaultdict

from pilot import read_jsonl

CONDITIONS = ('T0', 'T1', 'T2', 'T3')

def is_accept(rec):
    p = rec.get('parsed')
    if isinstance(p, str):
        return p == 'ACCEPT'
    return isinstance(p, dict) and p.get('decision') == 'ACCEPT'

def evidence_state(rec):
    """Return ('none'|'supporting'|'counter', verified:bool) for one cell."""
    cond = rec['condition']
    if cond in ('T0', 'T1'):
        return 'none', False
    # T2 sees the static block; T3 may additionally fetch/verify. Situation is
    # classified from the artifact content the reviewer was actually shown
    # (served_shows_failure), never from the hidden truth label.
    linked_fail = bool(rec.get('verify_saw_mismatch'))
    shows_failure = bool(rec.get('served_shows_failure'))
    verified = bool(rec.get('called_verify'))
    if linked_fail:
        return 'counter', True
    if shows_failure:
        return 'counter', verified
    return 'supporting', verified

def compute(records):
    records = list(records)   # read_jsonl yields a generator; compute iterates twice
    by_cond = defaultdict(list)
    for r in records:
        by_cond[r['condition']].append(r)

    report = {'conditions': {}, 'verification_mismatch_cells': {}}
    pool = defaultdict(lambda: {'accepts': 0, 'no_evidence_accepts': 0,
                                'counter_evidence_accepts': 0, 'no_evidence_n': 0,
                                'counter_evidence_n': 0})
    confusion = defaultdict(lambda: {'tp': 0, 'fp': 0, 'tn': 0, 'fn': 0})
    cost = defaultdict(lambda: {'n': 0, 'correct': 0, 'tokens_correct': 0,
                                'tokens_all': 0, 'wall_correct': 0.0,
                                'tool_calls': 0, 'verify_calls': 0})

    mismatch_cells = []
    for r in records:
        true_aid = _true_aid(r)
        if (true_aid and r.get('served_artifact_id')
                and r['served_artifact_id'] != true_aid):
            mismatch_cells.append(r)
    detected = called = 0
    for r in mismatch_cells:
        if r['condition'] == 'T3':
            if r.get('called_verify'):
                called += 1
                acted = bool(r.get('verify_saw_mismatch')) and (
                    bool(r.get('evidence_mismatch_flag')) or not is_accept(r))
                detected += int(acted)

    for cond in CONDITIONS:
        for r in by_cond.get(cond, []):
            acc = is_accept(r)
            state, verified = evidence_state(r)
            p = pool[cond]
            p['accepts'] += int(acc)
            if state == 'none':
                p['no_evidence_n'] += 1
                p['no_evidence_accepts'] += int(acc)
            elif state == 'counter':
                p['counter_evidence_n'] += 1
                p['counter_evidence_accepts'] += int(acc)
            # confusion against merge acceptability
            truth = bool(r.get('merge_acceptable'))
            c = confusion[cond]
            if acc and truth: c['tp'] += 1
            elif acc and not truth: c['fp'] += 1
            elif not acc and not truth: c['tn'] += 1
            else: c['fn'] += 1
            # cost
            correct = acc == truth
            toks = (r.get('tokens_in') or 0) + (r.get('tokens_out') or 0)
            cc = cost[cond]
            cc['n'] += 1; cc['tokens_all'] += toks
            cc['tool_calls'] += len(r.get('tool_trace') or [])
            cc['verify_calls'] += int(bool(r.get('called_verify')))
            if correct:
                cc['correct'] += 1
                cc['tokens_correct'] += toks
                cc['wall_correct'] += r.get('wall_s') or 0

        p, c, cc = pool[cond], confusion[cond], cost[cond]
        n = sum(confusion[cond].values())
        report['conditions'][cond] = {
            'n_cells': n,
            'accepts': p['accepts'],
            'uar_no_evidence': _div(p['no_evidence_accepts'], p['no_evidence_n']),
            'uar_counter_evidence': _div(p['counter_evidence_accepts'], p['counter_evidence_n']),
            'counter_evidence_cells': p['counter_evidence_n'],
            'merge_accuracy': _div(c['tp'] + c['tn'], n),
            'false_approve_rate': _div(c['fp'], c['fp'] + c['tn']),
            'false_reject_rate': _div(c['fn'], c['fn'] + c['tp']),
            'precision_accept': _div(c['tp'], c['tp'] + c['fp']),
            'cost_per_correct_review_tokens': _div(cc['tokens_correct'], cc['correct']),
            'mean_tokens_all': _div(cc['tokens_all'], cc['n']),
            'mean_wall_s_correct': _div(cc['wall_correct'], cc['correct']),
            'tool_calls_per_cell': _div(cc['tool_calls'], cc['n']),
            'verify_call_rate': _div(cc['verify_calls'], cc['n']),
        }

    report['verification_mismatch_cells'] = {
        't3_mismatch_cells': len([r for r in mismatch_cells if r['condition'] == 'T3']),
        'verify_call_rate': _div(called, len([r for r in mismatch_cells if r['condition'] == 'T3'])),
        'evidence_verification_success_rate': _div(detected, called or 0),
        'evsr_denominator_note': 'cells where verify was actually called',
    }

    # paired T2->T3 / T0->T2 accuracy deltas
    report['deltas'] = {}
    for hi, lo in (('T2', 'T0'), ('T3', 'T2'), ('T1', 'T0')):
        rh = {r['id']: r for r in by_cond.get(hi, [])}
        rl = {r['id']: r for r in by_cond.get(lo, [])}
        ids = sorted(set(rh) & set(rl))
        if not ids:
            continue
        flips_help = sum(1 for i in ids
                         if is_accept(rh[i]) == bool(rh[i].get('merge_acceptable'))
                         and is_accept(rl[i]) != bool(rl[i].get('merge_acceptable')))
        flips_hurt = sum(1 for i in ids
                         if is_accept(rl[i]) == bool(rl[i].get('merge_acceptable'))
                         and is_accept(rh[i]) != bool(rh[i].get('merge_acceptable')))
        report['deltas'][f'{lo}_to_{hi}'] = {
            'n_pairs': len(ids), 'corrected': flips_help, 'broken': flips_hurt,
            'net_accuracy_delta': _div(flips_help - flips_hurt, len(ids)),
        }
    return report

def _true_aid(r):
    from evidence.schemas import make_artifact_id
    iid = r.get('instance_id')
    if not iid or not r.get('patch_sha256'):
        return None
    return make_artifact_id(iid, r['patch_sha256'])

def _div(a, b):
    return round(a / b, 4) if b else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', default='evidence_results.jsonl')
    ap.add_argument('--out', default='evidence_metrics.json')
    a = ap.parse_args()
    recs = read_jsonl(a.results)
    rep = compute(recs)
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(json.dumps(rep, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
