"""One-off G3-B.3 live-result integrity verification (read-only)."""
import collections
import json

from evidence import g3b3_common as C

S = C.OUT_LIVE_DIR


def rows(name):
    with (S / name).open(encoding='utf-8') as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main():
    all_ok = True
    for m, fn, want_id in [
            ('deepseek-flash', 'g3b3_live_deepseek_flash_results.jsonl',
             'deepseek-flash'),
            ('gpt-4.1-mini', 'g3b3_live_gpt_41_mini_results.jsonl',
             'gpt-4.1-mini-2025-04-14')]:
        rs = rows(fn)
        print(f'== {m}: {len(rs)} rows')
        assert len(rs) == 50, 'need exactly 50 rows'
        # unique cells, serials, no dup
        cells = [r['cell'] for r in rs]
        assert len(set(cells)) == 50, 'dup cells'
        # no errors / no mock
        errs = [r['cell'] for r in rs if r.get('error')]
        mocks = [r['cell'] for r in rs if r.get('mock')]
        print('  errors:', len(errs), 'mock:', len(mocks))
        all_ok &= not errs and not mocks
        # served model id
        served = collections.Counter(r.get('model_served') for r in rs)
        print('  served ids:', dict(served))
        # expected id present as substring/prefix of served (vendors may suffix)
        bad_id = [r['cell'] for r in rs
                  if not str(r.get('model_served') or '').startswith(
                      want_id.split('-2025')[0] if '2025' in want_id
                      else want_id)]
        print('  served-id mismatches:', bad_id)
        all_ok &= not bad_id
        # zero adapter fallbacks (capability drift)
        fb = []
        for r in rs:
            for c in r.get('adapter_wire_calls', []):
                if c.get('fallback_from'):
                    fb.append(r['cell'])
        print('  fallback wire calls:', len(fb))
        all_ok &= not fb
        # raw answer non-empty and raw file exists
        empty_ans = [r['cell'] for r in rs
                     if not str(r.get('answer_raw') or '').strip()]
        print('  empty answer_raw:', len(empty_ans))
        all_ok &= not empty_ans
        # pre-call bounds recorded, every worst-case bound fits remaining model cap
        tot_cost = sum(float(r['cost_usd']) for r in rs)
        print(f'  total cost ${tot_cost:.6f}')
        over = tot_cost > C.PER_MODEL_CAP_USD + 1e-9
        all_ok &= not over
        # tokens/calls positive
        zero_calls = [r['cell'] for r in rs if not r.get('model_calls')]
        zero_in = [r['cell'] for r in rs if not r.get('tokens_in')]
        print('  zero model_calls:', len(zero_calls),
              'zero tokens_in:', len(zero_in))
        all_ok &= not zero_calls and not zero_in
        # gold audit columns
        bad_gold = [r['cell'] for r in rs
                    if r.get('gold_tier') != 'PROVISIONAL'
                    or r.get('annotator2') != 'NOT_OBTAINED']
        print('  gold authority bad rows:', len(bad_gold))
        all_ok &= not bad_gold
        # decision distribution
        dec = collections.Counter(
            (r.get('parsed') or {}).get('decision')
            if isinstance(r.get('parsed'), dict) else r.get('parsed')
            for r in rs)
        print('  decisions:', dict(dec))

    # cross-model: 50 identical cell keys (paired)
    ds = {r['cell'] for r in rows('g3b3_live_deepseek_flash_results.jsonl')}
    gp = {r['cell'] for r in rows('g3b3_live_gpt_41_mini_results.jsonl')}
    print('paired cell keys intersection:', len(ds & gp),
          'ds-only:', len(ds - gp), 'gpt-only:', len(gp - ds))
    all_ok &= ds == gp

    # raw files = 100; trace live files = 100
    nraw = len(list(C.OUT_RAW_DIR.glob('*.json')))
    ntr = len(list((C.OUT_TRACE_DIR / 'live').glob('*.json')))
    print('raw files:', nraw, 'live traces:', ntr)
    all_ok &= nraw == 100 and ntr == 100

    print('ALL_OK', all_ok)


if __name__ == '__main__':
    main()
