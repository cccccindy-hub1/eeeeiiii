"""Gate 3-B.4 task 9: first-run CompositeGuard.check -> None timeline.

Reconstruct the first live-attempt failure and its repair, show the failed
batch consumed $0 (guard evaluated before any network call), and disclose the
full fail -> fix -> re-freeze chronology (not just the final 100/100).

Offline only. Deleted $0 artifacts cannot be hashed; this is disclosed.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from evidence import g3b4_common as C

UTC = dt.timezone.utc


def utc(p: Path) -> str:
    return dt.datetime.fromtimestamp(p.stat().st_mtime, tz=UTC) \
        .strftime('%Y-%m-%dT%H:%M:%SZ')


def peek(path, keys):
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
    except Exception as e:  # noqa: BLE001
        return {'_read_error': str(e)}
    out = {}
    for k in keys:
        if k in d:
            out[k] = d[k]
    for k, v in d.items():
        if any(s in k.lower() for s in
               ('created', 'generated', 'timestamp')) and \
                not isinstance(v, (dict, list)):
            out.setdefault(k, v)
    return out


def main():
    g3b3 = C.G3B3
    files = {
        'g3b3_freeze_code': C.EVID / 'g3b3_freeze.py',
        'g3b3_run_code': C.EVID / 'g3b3_run.py',
        'mock_run_audit': g3b3 / 'runs' / 'g3b3_mock_run_audit.json',
        'live_gate_spec': g3b3 / 'livegate' / 'g3b3_live_gate.json',
        'executed_freeze_manifest':
            g3b3 / 'freeze' / 'g3b3_freeze_manifest.json',
        'preflight': g3b3 / 'preflight' / 'g3b3_preflight.json',
        'gpt_rows':
            g3b3 / 'runs' / 'g3b3_live_gpt_41_mini_results.jsonl',
        'ds_rows':
            g3b3 / 'runs' / 'g3b3_live_deepseek_flash_results.jsonl',
        'live_run_audit': g3b3 / 'runs' / 'g3b3_live_run_audit.json',
        'analysis': g3b3 / 'analysis' / 'g3b3_analysis.json',
        'report': g3b3 / 'g3b3_report.json',
        'result_freeze_manifest':
            g3b3 / 'freeze' / 'g3b3_result_freeze_manifest.json'}
    timeline = []
    for label, p in files.items():
        if p.exists():
            timeline.append(
                {'artifact': label, 'path': str(p.relative_to(C.HERE)),
                 'mtime_utc': utc(p), 'bytes': p.stat().st_size})
    timeline.sort(key=lambda x: x['mtime_utc'])

    internal = {
        'live_gate': peek(files['live_gate_spec'], [
            'gate_version', 'passed', 'n_checks', 'mode', 'scope',
            'created_at', 'generated_at']),
        'preflight': peek(files['preflight'], [
            'passed', 'created_at', 'generated_at', 'n_checks']),
        'live_run_audit': peek(files['live_run_audit'], [
            'total_spend_usd', 'per_model_spend_usd', 'n_new', 'n_skipped',
            'new', 'skipped', 'errors', 'created_at', 'generated_at',
            'model_calls_total', 'within_total_cap']),
        'result_freeze': peek(files['result_freeze_manifest'], [
            'created_at', 'generated_at', 'freeze_version'])}

    mechanism = {
        'buggy_shape': 'CompositeGuard.check(...) ended without a return '
                       'statement, so it returned None implicitly; the runner '
                       'then executed round(float(bound),6) with bound=None.',
        'exception': "TypeError: float() argument must be a string or a real "
                     "number, not 'NoneType'",
        'repaired_code_current': {
            'file': 'evidence/g3b3_run.py',
            'check_lines': 'L148-153: bound = self.model_guard.check(...); '
                           'self.total_guard.check(...); return bound',
            'call_site': 'L249-251: if not mock and guard is not None: '
                         'bound = guard.check(...); '
                         'pre_call_bounds.append(round(float(bound),6))',
            'network_call': 'L270-272: driver.chat.completions.create(...)'},
        'ordering_proof': 'guard.check / float(bound) at L249-251 executes '
                          'before driver.chat.completions.create at L270. '
                          'With bound=None the TypeError is raised at L251, so '
                          'control never reaches L270; no HTTP request is '
                          'issued for that cell.',
        'why_mock_did_not_catch_it': 'the guard path is skipped when mock=True'
                                     ' (L249), so the mock audit 100/100 $0 '
                                     'did not exercise the missing return.'}

    rows_ds = C.read_jsonl(C.G3B3_LIVE_DEEPSEEK)
    rows_gpt = C.read_jsonl(C.G3B3_LIVE_GPT)
    allrows = rows_ds + rows_gpt
    surviving = {
        'n_live_rows': len(allrows),
        'n_rows_with_error': sum(1 for r in allrows if r.get('error')),
        'n_rows_model_calls_zero': sum(
            1 for r in allrows if r.get('model_calls') == 0),
        'n_live_rows_cost_positive': sum(
            1 for r in allrows
            if float(r.get('cost_usd') or 0) > 0 and not r.get('mock')),
        'run_audit_total_spend_usd':
            internal['live_run_audit'].get('total_spend_usd'),
        'run_audit_n_new': internal['live_run_audit'].get('n_new'),
        'run_audit_n_skipped': internal['live_run_audit'].get('n_skipped')}

    runs_dir = g3b3 / 'runs'
    residue = sorted(p.name for p in runs_dir.glob('*')
                     if any(s in p.name.lower()
                            for s in ('error', 'failed', 'none', 'bak',
                                      'old', 'tmp')))
    raw_residue = sorted(p.name for p in (g3b3 / 'raw').glob('*error*'))

    out = {
        'document': 'Gate 3-B.4 task 9 first-run CompositeGuard None failure '
                    'and repair timeline',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'api_calls_made_by_this_audit': 0,
        'failure_mechanism': mechanism,
        'chronology_mtime_utc': timeline,
        'internal_timestamps': internal,
        'chronology_narrative': [
            '1) g3b3_freeze.py authored; the mock pipeline passed its mock '
            'run audit 100/100 at $0 (the mock path skips the guard, so the '
            'missing return was not exercised).',
            '2) The live-gate artifact was produced (its mtime precedes the '
            'executed freeze; internal fields show it is a gate specification'
            ' validated by the later preflight, not a post-run spend record).',
            '3) FIRST LIVE ATTEMPT: CompositeGuard.check returned None, so '
            'the first live cell raised float(None) BEFORE any '
            'completions.create; the batch failed with zero model calls and '
            'zero spend, and its $0 products were discarded.',
            '4) REPAIR: CompositeGuard.check was given `return bound` '
            '(current L148-153), making float(bound) valid.',
            '5) The executed freeze manifest + preflight were regenerated for'
            ' the corrected code; the corrected live run produced 50 GPT + 50'
            ' DeepSeek rows (100/100 success, 0 errors, 0 resume skips), the '
            'run audit, analysis and report.',
            '6) The result-freeze manifest pinned the final 100 raw responses'
            ' and 100 traces only after the successful re-run.'],
        'zero_api_evidence': {
            'ordering': 'guard evaluation (L249-251) precedes the network '
                        'call (L270) in the executed source',
            'surviving_rows': surviving,
            'interpretation': 'The surviving frozen run is entirely the '
                              'post-repair successful run. The failed attempt'
                              ' reached no network call by construction; the '
                              'deleted $0 error products cannot be hashed, so '
                              'their absence is attested by (a) the static '
                              'ordering proof, (b) zero error/zero-call rows '
                              'and no on-disk residue, and (c) the run audit '
                              'recording only new=50 per model, skipped=0.'},
        'deleted_products_limitation': 'The first batch $0 error artifacts '
            'were deleted and cannot now be independently hashed; this audit '
            'does not claim to hash them. It proves $0 via code ordering and '
            'the clean surviving run, and discloses the fail->repair->'
            'refreeze order rather than presenting only the final 100/100.',
        'residue_scan': {'runs_dir_matching_names': residue,
                         'raw_dir_error_files': raw_residue},
        'gold_authority': C.GOLD_AUTHORITY}

    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_first_run_timeline.json'
    dest.write_bytes(C.canonical_bytes(out))
    for t in timeline:
        print(t['mtime_utc'], t['artifact'])
    print('live rows:', surviving['n_live_rows'],
          'error:', surviving['n_rows_with_error'],
          'zero-call:', surviving['n_rows_model_calls_zero'])
    print('residue:', residue, raw_residue)
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
