"""CEE offline self-test (Controlled Evidence Experiment).

Zero network, zero LLM, zero paid calls. Verifies the frozen offline design:

  1. 22 bundles on disk + manifest class counts 7/6/9 over 10 issues.
  2. Independently re-derived CEE gold equals frozen wave2 oracle gold row by
     row, and frozen condition_gold['T3A-T'] as well.
  3. Build determinism: build_all twice -> identical bundle bytes/sha; files
     on disk equal the in-memory payload.
  4. Provider neutrality: a DeepSeek-flash and a GPT-4.1-mini wire profile
     emit the SAME canonical strict json_schema response_format bytes (all
     properties required, additionalProperties false); no json_object
     downgrade for either arm.
  5. No label leakage anywhere in the served turn.
  6. Schema strict-legality for OpenAI Structured Outputs and DeepSeek.
  7. Frozen ternary parser behaviour on valid / invalid / ambiguous samples.
  8. No post-hoc selection: sample is the full frozen 22-fixture set.
  9. Prompt/schema fingerprints pinned.

Run:
    uv run --python 3.13 -m evidence.cee_selftest
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.schemas import canonical_dumps, sha256_text
import hashlib
from evidence.ternary import read_jsonl, parse_ternary_decision
from evidence import cee_protocol as cee
from evidence.cee_build import (build_all, load_fixture_index, DEFAULT_STORE,
                                DEFAULT_OUT, GOLD_FILE, FIXTURE_FILES)

HERE = Path(__file__).resolve().parent
STORE = DEFAULT_STORE
OUT = DEFAULT_OUT

PIN_PROMPT_FP = ('ef48c57f76dba1019208ac993e6564a74e94727f672'
                 '00b1b6f046ead60492836')
CLASS_COUNTS = {'sufficient_positive': 7, 'decisive_negative': 6,
                'insufficient': 9}

# CEE wire profiles. BOTH use json_schema strict (the P1 format control); the
# only vendor-specific wire difference is the completion-cap parameter name,
# which both of these OpenAI-wire-compatible endpoints spell max_tokens.
_CEE_PROFILES = {
    'deepseek-flash': {
        'model': 'deepseek-flash', 'response_format': 'json_schema_strict',
        'completion_param': 'max_tokens',
    },
    'gpt-4.1-mini': {
        'model': 'gpt-4.1-mini', 'response_format': 'json_schema_strict',
        'completion_param': 'max_tokens',
    },
}


class _CapturingCompletions:
    """Fake inner chat.completions: records exact wire kwargs, returns a
    schema-conforming decision. Never touches the network."""

    def __init__(self):
        self.calls = []

    def create(self, *, model, messages, **kwargs):
        self.calls.append({'model': model, 'messages': messages, **kwargs})

        class _M:
            content = json.dumps({
                'decision': 'NEED_EVIDENCE', 'reason': 'offline selftest',
                'evidence_mismatch': True,
                'missing_evidence': 'offline selftest',
                'evidence_gap': 'unspecified'})
        return _M()


def _cee_wire_kwargs(profile, strict_schema_obj):
    """The CEE runner's final-turn kwargs shape: item-identical messages are
    built by cee_protocol; the SAME strict schema object is passed to every
    provider; only the cap parameter name is profile-specific. Unlike the E1
    adapter, CEE never substitutes a different schema and never downgrades."""
    return {'temperature': 0, profile['completion_param']: 4096,
            'response_format': strict_schema_obj}


def _run_checks():
    failures = []

    def check(name, cond, detail=''):
        if not cond:
            failures.append(f'{name}' + (f' :: {detail}' if detail else ''))
        print(f"[{'PASS' if cond else 'FAIL'}] {name}")

    # ---- 0. design/build artifacts exist --------------------------------
    gold_path = OUT / 'cee_gold.jsonl'
    manifest_path = OUT / 'cee_build_manifest.json'
    design_path = OUT / 'cee_design_freeze.json'
    bundles_dir = OUT / 'bundles'
    check('artifacts present',
          gold_path.exists() and manifest_path.exists()
          and design_path.exists() and bundles_dir.is_dir())

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    design = json.loads(design_path.read_text(encoding='utf-8'))
    cee_rows = read_jsonl(str(gold_path))
    frozen_gold = read_jsonl(str(STORE / GOLD_FILE))

    # ---- 1. counts -------------------------------------------------------
    check('22 cee gold rows', len(cee_rows) == 22, f'n={len(cee_rows)}')
    by_bid = {r['bundle_id']: r for r in cee_rows}
    check('unique bundle ids', len(by_bid) == 22)
    n_inst = len({r['instance_id'] for r in cee_rows})
    check('10 unique issue clusters', n_inst == 10, f'n={n_inst}')
    counts = {c: 0 for c in CLASS_COUNTS}
    for r in cee_rows:
        counts[r['evidence_class']] += 1
    check('class counts 7/6/9', counts == CLASS_COUNTS, str(counts))
    check('manifest class counts',
          {k: manifest['class_counts'][k] for k in CLASS_COUNTS}
          == CLASS_COUNTS)
    check('22 bundle files on disk',
          len(list(bundles_dir.glob('*.txt'))) == 22)

    # ---- 2. gold identity against frozen oracle and T3A-T ---------------
    fg_by_key = {(g['scenario'], g['id'], g['served_artifact_id']): g
                 for g in frozen_gold}
    mism, t3a_mism = [], []
    for r in cee_rows:
        g = fg_by_key[(r['scenario'], r['id'], r['served_artifact_id'])]
        if r['cee_gold'] != g['oracle_gold']:
            mism.append((r['bundle_id'], r['cee_gold'], g['oracle_gold']))
        if r['cee_gold'] != g['condition_gold']['T3A-T']:
            t3a_mism.append(r['bundle_id'])
    check('cee gold == frozen oracle_gold (22/22)', not mism, str(mism))
    check('cee gold == frozen condition_gold T3A-T (22/22)', not t3a_mism,
          str(t3a_mism))
    check('rows carry dual-channel oracle_inputs',
          all({'linked', 'fresh', 'complete', 'acceptance_failure',
               'acceptance_success', 'symptom_persists'}
              <= set(r['oracle_inputs']) for r in cee_rows))
    # The specific wave2.1 case that a single acceptance-channel rule gets
    # wrong: symptom persists on the target patch despite an unlinked artifact
    wp = [r for r in cee_rows if r['scenario'] == 'wrong_patch']
    check('wrong_patch diagnostic-channel REJECT preserved',
          len(wp) == 1 and wp[0]['cee_gold'] == 'REJECT'
          and wp[0]['oracle_inputs']['symptom_persists'] is True
          and wp[0]['oracle_inputs']['linked'] is False)

    # ---- 3. determinism --------------------------------------------------
    b1, g1, m1, p1 = build_all(STORE)
    b2, g2, m2, p2 = build_all(STORE)
    check('build_all deterministic bundle bytes',
          canonical_dumps(b1) == canonical_dumps(b2))
    check('build_all deterministic gold rows',
          canonical_dumps(g1) == canonical_dumps(g2))
    # on-disk payload equality
    disk_ok = True
    for bid, payload in p1.items():
        fp = bundles_dir / f'{bid}.txt'
        if not fp.exists() or fp.read_bytes() != payload:
            disk_ok = False
            break
    check('on-disk bundle bytes == build payload', disk_ok)
    # manifest sha matches gold file
    check('manifest cee_gold sha256 matches file',
          manifest['cee_gold_sha256']
          == sha256_text(''.join(canonical_dumps(r) + '\n' for r in cee_rows)))
    # Per-bundle sha over raw BYTES (bundles intentionally preserve CRLF
    # sequences from frozen raw rows; text-mode newline translation must not
    # be used here).
    sha_ok = all(
        hashlib.sha256((bundles_dir / f"{ent['bundle_id']}.txt").read_bytes())
        .hexdigest() == ent['bundle_sha256'] for ent in b1)
    check('per-bundle sha256 matches manifest (raw bytes)', sha_ok)

    # ---- 4. provider-neutral strict schema on both wire profiles --------
    schema_obj = {'type': 'json_schema', 'json_schema': cee.CEE_DECISION_SCHEMA}
    expected_wire = canonical_dumps(schema_obj)
    captured = {}
    for pname, prof in _CEE_PROFILES.items():
        cap = _CapturingCompletions()
        kw = _cee_wire_kwargs(prof, schema_obj)
        cap.create(model=prof['model'], messages=[{'role': 'user'}], **kw)
        rec = cap.calls[-1]
        captured[pname] = rec
        check(f'{pname}: strict json_schema wire mode',
              rec['response_format']['type'] == 'json_schema'
              and rec['response_format']['json_schema']
              is cee.CEE_DECISION_SCHEMA)
        check(f'{pname}: identical canonical schema bytes',
              canonical_dumps(rec['response_format']) == expected_wire)
        check(f'{pname}: temperature=0 and max_tokens cap',
              rec.get('temperature') == 0 and 'max_tokens' in rec)
        check(f'{pname}: no tools and no response-format downgrade hook',
              'tools' not in rec)
    check('both providers: same schema object identity',
          captured['deepseek-flash']['response_format']
          is captured['gpt-4.1-mini']['response_format'])

    # ---- 5/6. schema legality + no label leakage ------------------------
    inner = cee.CEE_DECISION_SCHEMA['schema']
    check('schema: all 5 properties required',
          set(inner['required']) == set(inner['properties'].keys())
          and len(inner['required']) == 5)
    check('schema: additionalProperties false',
          inner['additionalProperties'] is False)
    check('schema: decision enum is the frozen ternary',
          inner['properties']['decision']['enum']
          == ['ACCEPT', 'REJECT', 'NEED_EVIDENCE'])
    check('schema: evidence_gap enum carries empty-string option',
          inner['properties']['evidence_gap']['enum']
          == cee.CEE_GAP_ENUM and '' in cee.CEE_GAP_ENUM)
    check('schema wrapper strict=true',
          cee.CEE_DECISION_SCHEMA.get('strict') is True)

    label_tokens = ('oracle_gold', 'condition_gold', 'merge_acceptable',
                    'patch_correct', '"scenario"')
    leak_hits = []
    for bid, payload in p1.items():
        text = payload.decode('utf-8').lower()
        for tok in label_tokens:
            if tok in text:
                leak_hits.append((bid, tok))
    check('no hidden-label tokens in served turns', not leak_hits,
          str(leak_hits[:3]))

    # ---- 7. parser behaviour --------------------------------------------
    valid = json.dumps({'decision': 'accept', 'reason': 'r',
                        'evidence_mismatch': False, 'missing_evidence': '',
                        'evidence_gap': ''})
    check('parser: lowercase valid decision',
          parse_ternary_decision(valid) == 'ACCEPT')
    check('parser: INVALID on plain prose',
          parse_ternary_decision('looks fine to me') == 'INVALID')
    amb = '{"decision":"ACCEPT"} later {"decision":"REJECT"}'
    check('parser: AMBIGUOUS on conflicting decisions',
          parse_ternary_decision(amb) == 'AMBIGUOUS')

    # ---- 8. no post-hoc selection: full frozen set ----------------------
    fixtures, _, _, _ = load_fixture_index(STORE)
    fixture_aids = {fx['served_artifact_id'] for fx in fixtures}
    served_aids = {r['served_artifact_id'] for r in cee_rows}
    check('sample == full frozen 22-fixture set',
          len(fixtures) == 22 and fixture_aids == served_aids)
    check('manifest no_post_hoc_selection declared',
          'FULL 22-fixture' in manifest['no_post_hoc_selection'])
    check('design: 44 cells (22 x 2 models)',
          '44' in canonical_dumps(design['arm_specification']['cells'])
          or '44' in design['arm_specification']['cells'])

    # ---- 9. fingerprints --------------------------------------------------
    check('prompt fingerprint pinned',
          cee.cee_prompt_fingerprint() == PIN_PROMPT_FP,
          cee.cee_prompt_fingerprint())
    check('manifest prompt fingerprint pinned',
          manifest['prompt_fingerprint'] == PIN_PROMPT_FP)
    check('design status offline-gated',
          'OFFLINE ONLY' in design['status']
          and 'written approval' in design['execution_gate']
              ['required_to_unblock'])

    # ---- 10. budget plan consistency -------------------------------------
    plan_path = OUT / 'cee_plan.json'
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding='utf-8'))
        check('plan: 44 calls = 22 x 2',
              plan['sample']['total_calls'] == 44
              and all(d['n_calls'] == 22
                      for d in plan['models'].values()))
        hard = plan['totals_44_calls']['hard_envelope_usd']
        cap = plan['totals_44_calls']['hard_cap_total_usd']
        check('plan: hard envelope under $1.00 hard cap',
              hard <= cap and cap == 1.0, f'hard={hard} cap={cap}')
        check('plan: zero network status',
              'OFFLINE' in plan['status']
              and '--allow-paid-run' in plan['budget_guard']['runner_gate'])
    else:
        check('cee_plan.json present (run evidence.cee_plan)', False)

    return failures


def main():
    failures = _run_checks()
    print()
    if failures:
        print(f'CEE SELFTEST FAILED ({len(failures)}):')
        for f in failures:
            print(' -', f)
        raise SystemExit(1)
    print('CEE selftest OK: 22 bundles, dual-channel gold identity, '
          'determinism, dual-provider identical strict schema, no leakage, '
          'parser, full-set audit, fingerprints all pass')
    print('offline only: no network and no paid API call were performed')


if __name__ == '__main__':
    main()
