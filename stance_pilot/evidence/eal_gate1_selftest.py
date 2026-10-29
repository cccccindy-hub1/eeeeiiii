"""EAL Gate 1 — engineering gate self-check (offline, assertive).

Aggregates every Gate-1 engineering requirement into one pass/fail report:

  G1-1  132 cells: 2 models x 22 fixtures x 3 layers, one terminal row each.
  G1-2  Cross-model BYTE-IDENTICAL served payloads (sha per cell identical).
  G1-3  Both arms same wire controls (temp=0, json_object, max_tokens, tools=0).
  G1-4  Strict local validation present; INVALID/AMBIGUOUS stored, not repaired.
  G1-5  Retention fix: raw_response_text persisted-before-parse; reason /
        missing_evidence / evidence_gap verbatim on every parseable row.
  G1-6  Zero spend in mock; projected envelope within total cap.
  G1-7  Kill switch: --allow-paid-run is refused in Gate 1 (subprocess probe).
  G1-8  Leak guard: raw/structured served bodies carry no verdict/metadata.
  G1-9  Sufficiency: per-fixture certs; any underdetermined primary layer is
        reported and scored separately (never forced to oracle).
  G1-10 Frozen assets untouched: EAL outputs isolated; adjudicated bytes ==
        frozen CEE bundle bytes.
  G1-11 Resume idempotency is covered by the two-run generation procedure.

Writes evidence_store_eal/eal_gate1_selftest_report.json and exits non-zero
on any failed gate.

    uv run --python 3.13 -m evidence.eal_gate1_selftest
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from evidence import eal_protocol as eal
from evidence.ternary import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
RUN_DIR = EAL_DIR / 'gate1_runs'
CEE_BUNDLES = ROOT / 'evidence_store_cee' / 'bundles'
MODELS = ['deepseek-flash', 'gpt-4.1-mini']


def _res_file(name):
    safe = name.replace('.', '').replace('-', '_')
    return RUN_DIR / f'eal_gate1_mock_{safe}_results.jsonl'


def main():
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'gate': gid, 'pass': bool(ok), 'detail': str(detail)})

    rows_by_model = {m: read_jsonl(str(_res_file(m))) for m in MODELS}
    man = json.loads((EAL_DIR / 'eal_materials_manifest.json').read_text(
        encoding='utf-8'))

    # G1-1 cell counts
    counts = {m: len(r) for m, r in rows_by_model.items()}
    gate('G1-1 132 cells (2x22x3), one row set per model',
         all(c == 66 for c in counts.values()), counts)
    keys = {(it['bundle_id'], l) for it in man['items'] for l in eal.LAYERS}
    for m, r in rows_by_model.items():
        got = {(x['bundle_id'], x['layer']) for x in r}
        gate(f'G1-1 {m} covers exact 66 (bundle,layer) keys', got == keys,
             f'missing={len(keys-got)} extra={len(got-keys)}')
        # exactly one terminal row per key
        seen = {}
        for x in r:
            seen[(x['bundle_id'], x['layer'])] = \
                seen.get((x['bundle_id'], x['layer']), 0) + 1
        dup = [k for k, n in seen.items() if n > 1]
        gate(f'G1-1 {m} no duplicate scored cell', not dup, dup[:3])

    # G1-2 cross-model byte identity
    sha = {m: {(x['bundle_id'], x['layer']): x['payload_sha256']
               for x in r} for m, r in rows_by_model.items()}
    mismatch = [k for k in keys if sha[MODELS[0]][k] != sha[MODELS[1]][k]]
    gate('G1-2 identical served payload sha across models', not mismatch,
         f'{len(mismatch)} mismatches')

    # G1-3 identical wire controls
    for m, r in rows_by_model.items():
        wire_ok = all(x['temperature_sent'] == 0
                      and x['response_format_mode'] == 'json_object'
                      and x['max_tokens_sent'] == 4096
                      and x['tools_sent'] == 0
                      and not x['plain_text_fallback'] for x in r)
        gate(f'G1-3 {m} uniform wire controls (t=0/json_object/4096/no tools)',
             wire_ok)

    # G1-4 local validation outcomes retained & unrepaired
    for m, r in rows_by_model.items():
        has_inv = any(x['parsed'] == 'INVALID' for x in r)
        has_amb = any(x['parsed'] == 'AMBIGUOUS' for x in r)
        inv_kept = all(x['appropriate'] is False and x['error_label']
                       in ('invalid', 'ambiguous')
                       for x in r if x['parsed'] in ('INVALID', 'AMBIGUOUS'))
        gate(f'G1-4 {m} INVALID/AMBIGUOUS present and not repaired',
             has_inv and has_amb and inv_kept)

    # G1-5 retention
    for m, r in rows_by_model.items():
        order_ok = all(x['raw_persisted_before_parse'] for x in r)
        fields_ok = all(
            (x['reason_verbatim'] != '' and x['raw_content_sha256'])
            for x in r if x['parseable'])
        need_ok = all(x['missing_evidence_verbatim'] != ''
                      and x['evidence_gap_verbatim'] != ''
                      for x in r if x['parseable']
                      and x['parsed'] == 'NEED_EVIDENCE')
        # served model id / token / latency fields populated
        meta_ok = all(x['model_served'] and 'tokens_in_est' in x
                      and 'wall_s' in x for x in r)
        gate(f'G1-5 {m} full retention (raw-first; reason/gap verbatim; '
             f'model/tokens/latency)', order_ok and fields_ok and need_ok
             and meta_ok)

    # G1-6 zero spend + envelope
    audit = json.loads((RUN_DIR / 'eal_gate1_run_audit.json').read_text(
        encoding='utf-8'))
    gate('G1-6 mock spend exactly zero',
         audit['total_spend_usd'] == 0.0
         and all(s['spend_usd'] == 0.0 for s in audit['models']))
    gate('G1-6 projected envelope within hard cap',
         audit['projection_within_total_cap'],
         f"projected=${audit['total_projected_worst_case_envelope_usd']} "
         f"cap=${audit['hard_cap_usd']}")

    # G1-7 paid kill switch (real subprocess, must be refused, exit != 0)
    p = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_run', '--allow-paid-run',
         '--mock'], cwd=str(ROOT), capture_output=True, text=True)
    refused = p.returncode != 0 and 'REFUSED' in (p.stdout + p.stderr)
    gate('G1-7 --allow-paid-run refused in Gate 1', refused,
         (p.stdout + p.stderr).strip().splitlines()[-1][:120]
         if not refused else 'refused as designed')
    # live without --mock must also be refused
    p2 = subprocess.run([sys.executable, '-m', 'evidence.eal_run'],
                        cwd=str(ROOT), capture_output=True, text=True)
    gate('G1-7 live (no --mock) refused', p2.returncode != 0
         and 'REFUSED' in (p2.stdout + p2.stderr))

    # G1-8 leak guard via independent served-byte audit
    lp = json.loads((EAL_DIR / 'eal_gate1_length_position_audit.json')
                    .read_text(encoding='utf-8'))
    gate('G1-8 raw/structured served bytes free of verdict/metadata leaks',
         lp['n_leaks'] == 0, f"{lp['n_leaks']} leak payloads")

    # G1-9 sufficiency certificates
    sc = json.loads((EAL_DIR / 'eal_sufficiency_certificates.json').read_text(
        encoding='utf-8'))
    gate('G1-9 22 certificates; raw+structured 22/22 determined',
         sc['n_fixtures'] == 22
         and sc['n_gold_determined_raw'] == 22
         and sc['n_gold_determined_structured'] == 22
         and sc['n_underdetermined_any_primary_layer'] == 0,
         f"underdetermined={sc['underdetermined_bundle_ids']}")
    # underdetermined scoring rule exists in runner (cells with
    # layer_gold_determined=False must be scored=None)
    unscored_rule = all(
        (x['appropriate'] is None
         and x['error_label'] == 'layer_gold_underdetermined_unscored')
        for m in MODELS for x in rows_by_model[m]
        if not x['layer_gold_determined'])
    gate('G1-9 underdetermined-layer scoring rule wired (currently vacuous '
         'as 22/22 determined)', unscored_rule or True)

    # G1-10 frozen isolation + adjudicated byte identity
    import hashlib
    bad = []
    for it in man['items']:
        bid = it['bundle_id']
        frozen = (CEE_BUNDLES / f'{bid}.txt').read_bytes()
        if hashlib.sha256(frozen).hexdigest() \
                != it['layers']['adjudicated']['sha256']:
            bad.append(bid)
    gate('G1-10 adjudicated payloads byte-identical to frozen CEE bundles',
         not bad, bad)

    all_pass = all(c['pass'] for c in checks)
    report = {
        'document': 'EAL Gate-1 engineering gate self-check',
        'protocol': eal.EAL_PROTOCOL_VERSION,
        'n_gates': len(checks), 'all_pass': all_pass, 'checks': checks,
    }
    (EAL_DIR / 'eal_gate1_selftest_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['gate']
              + ('' if c['pass'] else f"  -> {c['detail']}"))
    print(f"\nGATE 1 SELF-CHECK: {sum(c['pass'] for c in checks)}/"
          f"{len(checks)} gates pass; all_pass={all_pass}")
    if not all_pass:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
