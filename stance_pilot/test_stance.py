#!/usr/bin/env python3
"""Offline tests for stance.py. No API calls. Must pass before any model run."""
import json, random, subprocess, sys
from stance import exact_mcnemar, bootstrap_ci, classify, collapse, contrast

fails = []
def check(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(('PASS ' if ok else 'FAIL ') + name + f'  got={got} want={want}')
    if not ok: fails.append(name)

# exact McNemar reference values (scipy.stats.binomtest, two-sided)
check('mcnemar b=0,c=5', exact_mcnemar(0, 5), 0.0625, 1e-9)      # 2*(1/32)
check('mcnemar b=0,c=10', exact_mcnemar(0, 10), 0.001953125, 1e-9)
check('mcnemar b=3,c=3', exact_mcnemar(3, 3), 1.0, 1e-9)
check('mcnemar b=1,c=9', exact_mcnemar(1, 9), 0.021484375, 1e-9)   # scipy binomtest, two-sided
check('mcnemar b=2,c=8', exact_mcnemar(2, 8), 0.109375, 1e-9)      # 2*(1+10+45)/1024

# classification semantics
check('bad: reject->accept is HARMFUL', classify('BAD', 'REJECT', 'ACCEPT'), 'HARMFUL')
check('bad: accept->reject is BENEFICIAL', classify('BAD', 'ACCEPT', 'REJECT'), 'BENEFICIAL')
check('bad: accept->accept UNCHANGED', classify('BAD', 'ACCEPT', 'ACCEPT'), 'UNCHANGED')
check('good: accept->reject is HARMFUL', classify('GOOD', 'ACCEPT', 'REJECT'), 'HARMFUL')
check('good: reject->accept BENEFICIAL', classify('GOOD', 'REJECT', 'ACCEPT'), 'BENEFICIAL')

# bootstrap CI covers a constant vector exactly
lo, hi = bootstrap_ci([1, 1, 1], ['a', 'b', 'c'], n_boot=200)
check('bootstrap constant vector width', hi - lo, 0.0, 1e-12)

# end-to-end on a synthetic design where the answer is known
rng = random.Random(0)
N = 20
conds, results, truth = [], [], {}
for i in range(N):
    pid = f'p{i:02d}'; gt = 'BAD' if i % 2 == 0 else 'GOOD'
    truth[pid] = gt
    neu = 'REJECT' if gt == 'BAD' else 'ACCEPT'          # neutral is always correct
    # positive stance flips BAD patches to ACCEPT (harmful), leaves GOOD unchanged
    pos = 'ACCEPT' if gt == 'BAD' else 'ACCEPT'
    neg = 'REJECT' if gt == 'BAD' else 'REJECT'          # negative flips GOOD to REJECT
    for arm, d in (('neutral', neu), ('positive', pos), ('negative', neg)):
        results.append({'id': pid, 'condition': f'{arm}_no_evidence', 'repeat': 0,
                        'model': 'SIM', 'resolved': gt == 'GOOD', 'patch_sha256': 'x',
                        'parsed': d, 'answer': json.dumps({'decision': d})})
with open('sim_stance.jsonl', 'w') as f:
    for r in results: f.write(json.dumps(r) + '\n')
with open('sim_stance_cond.jsonl', 'w') as f:
    for pid, gt in truth.items():
        f.write(json.dumps({'id': pid, 'resolved': gt == 'GOOD'}) + '\n')

out = subprocess.run([sys.executable, 'stance.py', '--input', 'sim_stance.jsonl',
                      '--patches', 'sim_stance_cond.jsonl', '--boot', '500'],
                     capture_output=True, text=True)
print(out.stdout[-1800:])
if 'Traceback' in out.stderr: print(out.stderr[-800:]); fails.append('stance.py crashed')
check('pooled positive HARMFUL block', "{'HARMFUL': 10, 'UNCHANGED': 10}" in out.stdout, True)
check('pooled negative HARMFUL block', "{'UNCHANGED': 10, 'HARMFUL': 10}" in out.stdout, True)
check('no outcome filtering', 'no outcome-based filtering' in out.stdout, True)
check('delta +1.0 appears twice', out.stdout.count('delta=+1.000'), 2)
check('mcnemar p reported for BAD', 'exact McNemar p=0.0020' in out.stdout, True)

print(('\nFAILURES: ' + ', '.join(fails)) if fails else '\nALL OFFLINE TESTS PASSED')
sys.exit(1 if fails else 0)
