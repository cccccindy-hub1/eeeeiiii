import json
from evidence import g3b3_common as C


def first(p):
    with open(p, encoding='utf-8') as fh:
        return json.loads(fh.readline())


g3b_ds = first(C.G3B_LIVE_DEEPSEEK)
g3b_gpt = first(C.G3B_LIVE_GPT)
g3b3_ds = first(C.OUT_LIVE_DIR / 'g3b3_live_deepseek_flash_results.jsonl')

print('G3B DS keys:')
print(sorted(g3b_ds.keys()))
print()
for k in ('cell', 'instance_id', 'condition', 'model', 'parsed',
          'audit_oracle_gold', 'audit_condition_gold', 'model_served',
          'cost_usd', 'tool_calls'):
    print(' g3b_ds', k, '=', g3b_ds.get(k))
print()
print('G3B3 DS keys:')
print(sorted(g3b3_ds.keys()))
print()
for k in ('cell', 'g3b_pair_cell_key', 'instance_id', 'condition', 'model',
          'model_profile', 'parsed', 'audit_oracle_gold',
          'audit_condition_gold', 'model_served', 'cost_usd', 'tool_calls',
          'gold_tier'):
    print(' g3b3_ds', k, '=', g3b3_ds.get(k))

# check pairing key format across all rows
def cells(p):
    out = []
    with open(p, encoding='utf-8') as fh:
        for line in fh:
            r = json.loads(line)
            out.append((r.get('cell'), r.get('g3b_pair_cell_key'),
                        r.get('instance_id'), r.get('condition'),
                        r.get('parsed'), r.get('model_profile')
                        if 'model_profile' in r else r.get('model')))
    return out


a = cells(C.G3B_LIVE_DEEPSEEK)
b = cells(C.OUT_LIVE_DIR / 'g3b3_live_deepseek_flash_results.jsonl')
print()
print('sample g3b  cell tuples:')
for t in a[:3]:
    print(' ', t)
print('sample g3b3 cell tuples:')
for t in b[:3]:
    print(' ', t)
print('n g3b ds rows', len(a), 'n g3b3 ds rows', len(b))
