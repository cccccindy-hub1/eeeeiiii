"""GroundedReview v2 — EAL Gate-2 OFFLINE freeze & preflight (zero API).

Gate-2 written approval (2026-10-25) is CONDITIONAL on an offline freeze
review before the first paid call. This module performs it and never opens
a socket:

  1. Builds the Gate-2 served payload set from the SAME frozen fixtures,
     adding ONE item-invariant disclosure to RAW and STRUCTURED that labels
     the upstream CI runner's pre-classified DERIVED SUMMARIES
     (summary counts/id lists incl. runner "regressed"/"pre-existing-bad"
     classifications, and scope metadata). ADJUDICATED is re-served
     byte-identical to the frozen CEE bundle and is NOT annotated.
     The Gate-0 payloads/manifest are left untouched; the Gate-2 set lives
     under evidence_store_eal/gate2/.
  2. Freezes + hashes: all 66 payloads, per-layer Gate-2 prompt
     fingerprints (system/head/goal/schema), per-bundle gold, the local
     validator/schema, the runner, budget config and the scoring rules.
  3. Pre-registers the three primary paired contrasts and the analysis
     discipline (issue-cluster bootstrap seed=7/n=10000; token LENGTH is
     recorded/stratified/discussed but NOT entered as a regression control,
     because length is determined by the condition itself).
  4. Preflight asserts: 22/22 gold still determined (annotation adds no
     operand and no verdict), 0 verdict/metadata leaks in the exact served
     raw/structured bodies, adjudicated == frozen CEE bytes, Gate-1
     self-check still 20/20, no credentials in any payload, and the live
     kill switches REFUSE without the explicit Gate-2 acknowledgement.

Run:
    uv run --python 3.13 -m evidence.eal_gate2_freeze
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.ternary import read_jsonl
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_render import (DEFAULT_STORE, ArtifactStore, _bundle_id,
                                 load_index, load_materials,
                                 render_raw_body, render_structured_body)
from evidence.cee_run import GOLD_PATH as CEE_GOLD_PATH
from evidence.prompts import CLAIM_POSITIVE

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
G0_MANIFEST = EAL_DIR / 'eal_materials_manifest.json'
G2_DIR = EAL_DIR / 'gate2'
G2_LAYERS = G2_DIR / 'layers'
G2_MANIFEST = G2_DIR / 'eal_gate2_materials_manifest.json'
G2_FREEZE = G2_DIR / 'eal_gate2_freeze_manifest.json'
G2_PREFLIGHT = G2_DIR / 'eal_gate2_preflight.json'
CEE_BUNDLES = ROOT / 'evidence_store_cee' / 'bundles'

GATE2_CONDITION = 'eal-v0-draft1+gate2-derived-summary-disclosure'
SEED = 7
N_BOOT = 10000

# ---------------------------------------------------------------------------
# The single Gate-2 delta vs Gate 0: an explicit derived-summary disclosure.
# Item-invariant, identical in RAW and STRUCTURED, appended to the frozen
# layer head (base head text itself is left unchanged). It names NO verdict
# boolean and NO gold/scenario token, so it passes the same leak scanner.
# ---------------------------------------------------------------------------
DERIVED_SUMMARY_DISCLOSURE = (
    '\n\nDERIVED-SUMMARY DISCLOSURE — this condition is "RAW EXECUTION '
    'EVIDENCE WITH DERIVED SUMMARIES". The primary records below also '
    'contain a small number of fields computed BY THE UPSTREAM CI RUNNER '
    'AFTER it compared the post-patch run against the base-commit run: the '
    "run record's nested summary object (run counts and id lists, "
    'including the runner-classified "regressed" and "pre-existing-bad" id '
    'lists) and its scope metadata. Those are derived classifications, not '
    'raw per-test observations — they already encode a post-vs-base '
    'comparison you did not perform. Every raw per-test status map, command '
    'and exit code needed to re-derive them is provided wherever the '
    'archive retained it; where a per-test base map is absent the runner '
    'classification cannot be independently re-derived from the items '
    'shown. Treat such fields as runner-provided summaries: separate '
    'conclusions you verify yourself from primary outputs from conclusions '
    'you merely inherit from a summary, and say which is which in your '
    'reason. This disclosure states nothing about the final decision.')

RAW_RECORD_NOTICE = (
    '\n[DERIVED SUMMARY WITHIN THIS JSON RECORD] Most fields are primary '
    'observations (identity hashes, run_tree, per-test status maps, log '
    'digests). The nested "summary" object (counts and id lists, incl. '
    'runner-classified "regressed" and "pre-existing-bad" lists) and the '
    '"scope" object are DERIVED by the runner from a post-vs-base '
    'comparison; they are summaries rather than raw per-test outputs.')

STR_TABLE5_NOTICE = (
    '\n[DERIVED] TABLE 5 is runner-computed SUMMARY (post-vs-base '
    'classification incl. "regressed"/"pre-existing-bad" lists), not raw '
    'per-test output; TABLE 4 holds the primary per-check operands. See '
    'the DERIVED-SUMMARY DISCLOSURE above.')

_RUN_RECORD_HEADER = ('=== SIGNED CI RUN RECORD (what the runner actually '
                      'executed) ===')
_TABLE5_HEADER = ('=== TABLE 5 — RECORD SUMMARY FIELDS (as recorded by the '
                  'runner) ===')

# Leak / credential scanners (mirror the Gate-1 served-byte audit).
LEAK_VERDICT = re.compile(
    r'symptom_persists|"linked"\s*:|"fresh"\s*:|"complete"\s*:|'
    r'linked to this patch[^\n]{0,20}:\s*(yes|no)|'
    r'fresh for the current commit tree\s*:\s*(yes|no)|'
    r'fully executed\s*:\s*(yes|no)|'
    r'symptom (present before|reproduces after)[^\n]{0,10}:\s*(yes|no)',
    re.I)
LEAK_META = re.compile(
    r'cee_gold|evidence_class|decisive_failure|sufficient_success|'
    r'wrong_patch|stale_persists|stale_bad|incomplete_decisive|w2_valid',
    re.I)
CRED_PAT = re.compile(
    r'sk-[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}|'
    r'DEEPSEEK_API_KEY|OPENAI_API_KEY', re.I)
BODY_MARK = {'raw': 'RAW EVIDENCE PACKAGE',
             'structured': 'STRUCTURED EVIDENCE PACKAGE',
             'adjudicated': 'FIXED EVIDENCE BUNDLE'}


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def gate2_head(layer: str) -> str:
    """Gate-2 head: frozen Gate-0 head + disclosure for raw/structured;
    adjudicated is the untouched frozen CEE head (== CEE bundle bytes)."""
    if layer == 'adjudicated':
        return eal.layer_head('adjudicated')
    return eal.layer_head(layer) + DERIVED_SUMMARY_DISCLOSURE


def gate2_prompt_fingerprint(layer: str, head: str) -> str:
    blob = canonical_dumps({
        'version': eal.EAL_PROTOCOL_VERSION,
        'gate2_condition': GATE2_CONDITION,
        'layer': layer,
        'system': eal.SYSTEM_MESSAGE,
        'head': head,
        'goal': eal.REVIEW_GOAL,
        'schema': eal.DECISION_SCHEMA,
        'tools': [], 'turns': 1})
    return _sha(blob.encode('utf-8'))


def annotate_raw_body(body: str) -> str:
    # 1) top-of-package pointer immediately after the first line
    first = 'RAW EVIDENCE PACKAGE (protocol eal-v0-draft1).'
    assert body.startswith(first)
    body = first + RAW_RECORD_NOTICE + body[len(first):]
    # 2) inline notice directly above the signed run-record JSON
    assert _RUN_RECORD_HEADER in body
    body = body.replace(_RUN_RECORD_HEADER,
                        _RUN_RECORD_HEADER + RAW_RECORD_NOTICE, 1)
    return body


def annotate_structured_body(body: str) -> str:
    assert _TABLE5_HEADER in body
    return body.replace(_TABLE5_HEADER,
                        _TABLE5_HEADER + STR_TABLE5_NOTICE, 1)


def build_gate2():
    """Return (items, payloads[pid]=bytes) for the Gate-2 set."""
    g0 = json.loads(G0_MANIFEST.read_text(encoding='utf-8'))
    fixtures, raw_by_id, cee_gold = load_index(DEFAULT_STORE)
    store = ArtifactStore(str(DEFAULT_STORE))
    g0_by_bid = {it['bundle_id']: it for it in g0['items']}
    heads = {l: gate2_head(l) for l in eal.LAYERS}
    fps = {l: gate2_prompt_fingerprint(l, heads[l]) for l in eal.LAYERS}

    items, payloads = [], {}
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        grow = cee_gold[key]
        raw = raw_by_id[fx['id']]
        claim = fx.get('claim') or CLAIM_POSITIVE
        mat = load_materials(store, fx)
        bid = _bundle_id(*key)
        g0it = g0_by_bid[bid]

        raw_body = annotate_raw_body(
            render_raw_body(issue=raw['problem_statement'],
                            patch=raw['model_patch'], claim=claim, mat=mat))
        str_body = annotate_structured_body(
            render_structured_body(issue=raw['problem_statement'],
                                   patch=raw['model_patch'], claim=claim,
                                   mat=mat))
        user = {
            'raw': heads['raw'] + eal.REVIEW_GOAL + '\n\n' + raw_body,
            'structured': (heads['structured'] + eal.REVIEW_GOAL + '\n\n'
                           + str_body),
        }
        per_layer = {}
        for layer in ('raw', 'structured'):
            ub = user[layer].encode('utf-8')
            pid = f'{bid}__{layer}'
            payloads[pid] = ub
            per_layer[layer] = {
                'payload_id': pid, 'bytes': len(ub), 'sha256': _sha(ub),
                'prompt_fingerprint_gate2': fps[layer],
                'derived_summary_disclosure_present': True}
        # adjudicated: frozen CEE bytes, untouched, asserted equal to Gate 0
        cee_bytes = (CEE_BUNDLES / f'{bid}.txt').read_bytes()
        g0_adj_sha = g0it['layers']['adjudicated']['sha256']
        if _sha(cee_bytes) != g0_adj_sha:
            raise SystemExit(f'CEE bundle drift on {bid}')
        pid = f'{bid}__adjudicated'
        payloads[pid] = cee_bytes
        per_layer['adjudicated'] = {
            'payload_id': pid, 'bytes': len(cee_bytes),
            'sha256': _sha(cee_bytes),
            'prompt_fingerprint_gate2': fps['adjudicated'],
            'derived_summary_disclosure_present': False,
            'identical_to_frozen_cee_bundle': True}

        items.append({
            'bundle_id': bid,
            'instance_id': fx['instance_id'], 'id': fx['id'],
            'scenario_internal': fx['scenario'],
            'served_artifact_id': fx['served_artifact_id'],
            'cee_gold': grow['cee_gold'],
            'evidence_class': grow['evidence_class'],
            'layer_gold_determined':
                g0it['layer_gold_determined_from_visible_materials'],
            'underdetermined_channels': g0it['underdetermined_channels'],
            'channels': g0it['channels'],
            'layers': per_layer})
    return items, payloads, heads, fps


def write_gate2(items, payloads, heads, fps):
    G2_LAYERS.mkdir(parents=True, exist_ok=True)
    for pid, b in payloads.items():
        (G2_LAYERS / f'{pid}.txt').write_bytes(b)
    manifest = {
        'eal_protocol_version': eal.EAL_PROTOCOL_VERSION,
        'gate2_condition': GATE2_CONDITION,
        'generated_by': 'evidence/eal_gate2_freeze.py',
        'delta_vs_gate0': 'one item-invariant DERIVED-SUMMARY DISCLOSURE '
                         'appended to raw/structured heads + inline notices '
                         'at the runner summary fields; adjudicated '
                         'byte-identical to frozen CEE; no operand added or '
                         'removed; gate-0 set untouched',
        'n_items': len(items),
        'n_unique_instances': len({i['instance_id'] for i in items}),
        'layer_prompt_fingerprints_gate2': fps,
        'items': items}
    G2_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')
    return manifest


SCORING_RULES = {
    'decision_space': ['ACCEPT', 'REJECT', 'NEED_EVIDENCE'],
    'appropriate': 'parsed decision == per-bundle frozen cee_gold, only on '
                   'layers whose gold is determined from visible materials',
    'underdetermined': 'appropriate=null, error_label='
                       'layer_gold_underdetermined_unscored; excluded from '
                       'DA and reported separately (0 expected at Gate 2)',
    'terminal_failures': 'INVALID/AMBIGUOUS are delivered HTTP-200 outcomes: '
                         'scored once as not-appropriate, never repaired or '
                         'retried; API_ERROR is the only resumable state',
    'denominators': 'DA reported on parseable AND all-requests denominators; '
                    'INVALID/AMBIGUOUS/API_ERROR never folded into '
                    'NEED_EVIDENCE',
    'error_families': ['over_abstention (gold ACCEPT/REJECT -> NEED)',
                       'unsupported_acceptance_false_commit (non-ACCEPT gold '
                       '-> ACCEPT)',
                       'unsupported_rejection (non-REJECT gold -> REJECT)'],
    'primary_contrasts': [
        {'name': 'Adjudicated_minus_Raw', 'question': 'overall evidence '
         'abstraction gap'},
        {'name': 'Structured_minus_Raw', 'question': 'difficulty of '
         'extracting/organising evidence from raw logs'},
        {'name': 'Adjudicated_minus_Structured', 'question': 'difficulty of '
         'inferring validity/policy from structured facts'}],
    'contrast_sign': 'any contrast may be negative; no monotonicity assumed',
    'bootstrap': {'unit': 'issue cluster (instance_id)', 'seed': SEED,
                  'n_boot': N_BOOT},
    'length_discipline': 'token length is condition-determined; it is '
                         'recorded, stratified and discussed, but NOT used '
                         'as an ad hoc regression control',
    'pooling': 'EAL layer scores are never pooled with E1 or CEE; mirrors '
               'are within-issue repeats, never independent n',
}

BUDGET_CONFIG = {
    'total_hard_cap_usd': 3.00,
    'per_model_cap_usd': 1.50,
    'guard_prices_usd_per_mtok': {
        'deepseek-flash': {'in': 0.30, 'out': 1.20},
        'gpt-4.1-mini': {'in': 0.40, 'out': 1.60}},
    'guard_input_token_estimator': 'whole-wire bytes // 3 (conservative, '
                                   'pre-call only)',
    'completion_cap_tokens': 4096,
    'temperature': 0, 'tools': 0, 'turns_per_cell': 1,
    'response_format': {'type': 'json_object'},
    'models': ['deepseek-flash', 'gpt-4.1-mini'],
    'n_cells_per_model': 66, 'n_planned_paid_cells': 132,
}


def _code_sha(name):
    return _sha((Path(__file__).resolve().parent / name).read_bytes())


def build_freeze_manifest(items, payloads, heads, fps):
    payload_hashes = {pid: {'sha256': _sha(b), 'bytes': len(b)}
                      for pid, b in sorted(payloads.items())}
    fm = {
        'document': 'EAL Gate-2 pre-paid freeze manifest',
        'eal_protocol_version': eal.EAL_PROTOCOL_VERSION,
        'gate2_condition': GATE2_CONDITION,
        'created_before_any_paid_call': True,
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'review_goal_sha256': _sha(eal.REVIEW_GOAL.encode()),
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'response_format': cee.RESPONSE_FORMAT_JSON_OBJECT,
        'layer_heads_gate2_sha256':
            {l: _sha(heads[l].encode()) for l in eal.LAYERS},
        'layer_prompt_fingerprints_gate2': fps,
        'payload_sha256': payload_hashes,
        'gold': [{k: it[k] for k in
                  ('bundle_id', 'instance_id', 'cee_gold', 'evidence_class',
                   'layer_gold_determined', 'underdetermined_channels')}
                 for it in items],
        'cee_gold_file_sha256': _sha(CEE_GOLD_PATH.read_bytes()),
        'code_sha256': {
            'eal_protocol.py': _code_sha('eal_protocol.py'),
            'cee_protocol_v11.py': _code_sha('cee_protocol_v11.py'),
            'eal_render.py': _code_sha('eal_render.py'),
            'eal_gate2_freeze.py': _sha(Path(__file__).read_bytes()),
            'eal_gate2_run.py': _code_sha('eal_gate2_run.py'),
            'eal_gate2_analyze.py': _code_sha('eal_gate2_analyze.py')},
        'budget_config': BUDGET_CONFIG,
        'scoring_rules': SCORING_RULES,
    }
    G2_FREEZE.write_text(
        json.dumps(fm, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8')
    return fm


def preflight(items, payloads):
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'check': gid, 'pass': bool(ok), 'detail': str(detail)})

    # 1. counts + determination
    gate('freeze: 22 items x 3 layers = 66 payloads', len(items) == 22
         and len(payloads) == 66, f'{len(items)} items, {len(payloads)} files')
    n_det = sum(i['layer_gold_determined'] for i in items)
    und = [i['bundle_id'] for i in items if not i['layer_gold_determined']]
    gate('freeze: 22/22 layer-gold determined (no new underdetermined)',
         n_det == 22 and not und, f'determined={n_det} under={und}')
    gold_dist = {}
    for i in items:
        gold_dist[i['cee_gold']] = gold_dist.get(i['cee_gold'], 0) + 1
    gate('freeze: gold distribution 7/6/9',
         gold_dist == {'ACCEPT': 7, 'REJECT': 6, 'NEED_EVIDENCE': 9},
         gold_dist)

    # 2. disclosure present exactly where required, absent in adjudicated
    for i in items:
        for layer in ('raw', 'structured'):
            txt = payloads[i['layers'][layer]['payload_id']].decode('utf-8')
            assert 'DERIVED-SUMMARY DISCLOSURE' in txt
        adj = payloads[i['layers']['adjudicated']['payload_id']].decode()
        assert 'DERIVED-SUMMARY DISCLOSURE' not in adj
    gate('freeze: disclosure in 44 raw/structured, absent in 22 adjudicated',
         True)

    # 3. adjudicated byte identity vs frozen CEE
    bad = [i['bundle_id'] for i in items
           if i['layers']['adjudicated']['sha256']
           != _sha((CEE_BUNDLES / f"{i['bundle_id']}.txt").read_bytes())]
    gate('freeze: adjudicated == frozen CEE bundle bytes (22/22)', not bad, bad)

    # 4. served-body leak scan (body region only) on gate-2 bytes
    leaks = []
    for i in items:
        for layer in ('raw', 'structured'):
            txt = payloads[i['layers'][layer]['payload_id']].decode('utf-8')
            body = txt[txt.index(BODY_MARK[layer]):]
            v = sorted(set(m.group(0).strip()
                           for m in LEAK_VERDICT.finditer(body)))
            mm = sorted(set(m.group(0).strip()
                            for m in LEAK_META.finditer(body)))
            if v or mm:
                leaks.append({'payload': i['layers'][layer]['payload_id'],
                              'verdict': v, 'metadata': mm})
    gate('preflight: 0 verdict/metadata leaks in served gate-2 bodies',
         not leaks, leaks)

    # 5. credential scan over every served byte (incl. heads)
    cred = sorted({pid for pid, b in payloads.items()
                   if CRED_PAT.search(b.decode('utf-8', 'replace'))})
    gate('preflight: no api keys / bearer tokens / key env names in payloads',
         not cred, cred)

    # 6. Gate-1 self-check still green (frozen prior gate unaffected)
    p = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_gate1_selftest'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('preflight: Gate-1 engineering self-check still 20/20',
         p.returncode == 0 and 'all_pass=True' in p.stdout,
         p.stdout.strip().splitlines()[-1][:160])

    # 7. live kill switches: --allow-paid-run alone must REFUSE
    p1 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_gate2_run', '--allow-paid-run'],
        cwd=str(ROOT), capture_output=True, text=True)
    refused1 = p1.returncode != 0 and 'REFUSED' in (p1.stdout + p1.stderr)
    gate('preflight: live without gate-2 acknowledgement REFUSED', refused1)
    # and a bare live invocation (no flags) must REFUSE
    p2 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_gate2_run'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('preflight: bare invocation REFUSED (defaults offline)',
         p2.returncode != 0 and 'REFUSED' in (p2.stdout + p2.stderr))

    # 8. gate-2 mock dry-run envelope is within cap
    p3 = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_gate2_run', '--mock',
         '--dry-run'], cwd=str(ROOT), capture_output=True, text=True)
    gate('preflight: gate-2 runner mock --dry-run ok',
         p3.returncode == 0, (p3.stdout + p3.stderr)[-200:])

    all_pass = all(c['pass'] for c in checks)
    out = {'document': 'EAL Gate-2 offline preflight (must pass before any '
                       'paid call)',
           'gate2_condition': GATE2_CONDITION,
           'freeze_manifest': G2_FREEZE.name,
           'n_checks': len(checks), 'all_pass': all_pass, 'checks': checks}
    G2_PREFLIGHT.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    for c in checks:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['check']
              + ('' if c['pass'] else f" -> {c['detail']}"))
    print(f"\nGATE-2 PREFLIGHT: {sum(c['pass'] for c in checks)}/"
          f"{len(checks)} pass; all_pass={all_pass}")
    return all_pass


def main():
    items, payloads, heads, fps = build_gate2()
    write_gate2(items, payloads, heads, fps)
    build_freeze_manifest(items, payloads, heads, fps)
    print(f'Gate-2 set written: {len(payloads)} payloads -> {G2_DIR}')
    for layer in eal.LAYERS:
        bs = [i['layers'][layer]['bytes'] for i in items]
        print(f'  {layer:12s} bytes min/med/max: '
              f'{min(bs)}/{sorted(bs)[len(bs)//2]}/{max(bs)}')
    ok = preflight(items, payloads)
    if not ok:
        raise SystemExit(1)
    print('Freeze complete. No paid call has been made. The live runner '
          'will only start with --allow-paid-run plus the explicit Gate-2 '
          'acknowledgement flag.')


if __name__ == '__main__':
    main()
