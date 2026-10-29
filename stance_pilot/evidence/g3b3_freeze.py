"""GroundedReview Gate 3-B.3 — Corrective Replication FREEZE (zero API).

Conditional written approval (Gate 3-B.2 accepted; G3-B.3 authorised as a
corrective replication): 100 REAL model cells = 2 real models x the SAME 10
frozen independent SymPy issues x the SAME 5 frozen evidence regimes, but now
executed over the accepted G3-B.2 repaired protocol:

  * prompt_version  = p3-ternary-g3b2-v1   (g3b2_prompts)
  * protocol_version = g3b2-protocol-v1    (g3b2_server three-state freshness)
  * gold certs       = g3b2-gold-cert-v1   (50 certificates, 0 value changes)

This module ONLY derives and writes a deterministic freeze manifest:
  evidence_store_g3b3/freeze/g3b3_freeze_manifest.json
It makes no model call. It re-verifies the frozen G3-A/G3-A.1 parents (via the
frozen g3b/g3b2 verification chains), pins the G3-B.2 freeze + gold
certificates byte-for-byte, constructs the 50 issue-condition items by REUSING
the g3b2 item builder (identical served content; cell_key re-namespaced to
g3b3:), fixes a NEW interleaved serial order (a fixed seed distinct from G3-B
and the g3b2 mock), the sampling parameters, the vendor prices, the served
model id allow-list, and the user-authorized budget HARD caps:
    TOTAL $3.00 across both models; $1.50 per model.

Every cell carries the G3-B pairing anchor (the exact frozen G3-B cell key)
needed for the strict same issue/condition/model paired transition analysis.
G3-B historical results are only referenced; never overwritten or re-scored.

Offline:
    uv run --python 3.13 -m evidence.g3b3_freeze
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence.prompts import ternary_tools

from evidence import g3b2_freeze as GZ
from evidence import g3b2_prompts as GP
from evidence import g3b3_common as C


# Real vendor profiles — identical values/prices to the frozen G3-B profiles
# so the two versions are directly comparable on cost; the runner refuses to
# run if an in-code profile differs from what this freeze records.
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in_per_1m': 0.30, 'price_out_per_1m': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'completion_param': 'max_tokens',
        'response_format': 'json_object',
        'tool_calling_supported': True,
        'temperature_supported': True,
        'expected_served_model_id': 'deepseek-flash',
        'per_model_cap_usd': C.PER_MODEL_CAP_USD,
    },
    'gpt-4.1-mini': {
        'provider': 'openai', 'model': 'gpt-4.1-mini',
        'base_url': 'https://api.openai.com/v1',
        'key_env': 'OPENAI_API_KEY',
        'openai_key_file': str(Path.home() / '.openai_key'),
        'price_in_per_1m': 0.40, 'price_out_per_1m': 1.60,
        'extra_body': {},
        'completion_param': 'max_tokens',
        'response_format': 'json_object',
        'tool_calling_supported': True,
        'temperature_supported': True,
        'expected_served_model_id': 'gpt-4.1-mini-2025-04-14',
        'per_model_cap_usd': C.PER_MODEL_CAP_USD,
    },
}


def build_items():
    """50 issue-condition items = the g3b2 items (identical served content)
    with the cell key re-namespaced to g3b3:. No label field is added; the
    g3b2 builder already keeps gold only under audit-only underscore keys."""
    items = []
    for it in GZ.build_items():
        it = dict(it)
        iid, cond = it['instance_id'], it['condition']
        it['cell_key'] = f'g3b3:{iid}:{cond}'
        it['g3b_pair_cell_key'] = f'g3b:{iid}:{cond}'
        it['g3b2_cell_key'] = f'g3b2:{iid}:{cond}'
        items.append(it)
    if len(items) != 50:
        raise SystemExit(f'expected 50 g3b3 items, got {len(items)}')
    return items


def base_permutation():
    """The fixed 10-slot (model x condition) base sequence, permuted by a
    Fisher-Yates shuffle seeded with the NEW ORDER_SEED (distinct from G3-B/
    g3b2 seed 7). Recorded verbatim in the freeze for audit."""
    import random
    base = []
    for cond in C.CONDITIONS:
        base.append(('deepseek-flash', cond))
        base.append(('gpt-4.1-mini', cond))
    random.Random(C.ORDER_SEED).shuffle(base)
    return base


def interleaved_order(items, base=None):
    """Deterministic serial order over the 100 REAL cells.

    Same cyclic Latin-shift discipline as G3-B (one issue block = 10
    model x condition slots; the block rotates one slot per issue), but over
    the NEW fixed base permutation. Balance is asserted: every
    (model, condition) appears once per issue and 10 times overall, so neither
    model nor condition is confounded with serial/time position.
    """
    base = base or base_permutation()
    issues = sorted({it['instance_id'] for it in items})
    by = {(it['instance_id'], it['condition']): it for it in items}
    order = []
    for b, iid in enumerate(issues):
        block = base[b % len(base):] + base[:b % len(base)]
        for model, cond in block:
            it = by[(iid, cond)]
            order.append({
                'serial': len(order), 'model_profile': model,
                'instance_id': iid, 'condition': cond,
                'cell_key': it['cell_key'],
                'g3b_pair_cell_key': it['g3b_pair_cell_key'],
                'served_artifact_id': it['served_artifact_id'],
            })
    from collections import Counter
    cnt = Counter((o['model_profile'], o['condition']) for o in order)
    if len(order) != 100 or len(cnt) != 10 or set(cnt.values()) != {10}:
        raise SystemExit(f'g3b3 order balance broken: {dict(cnt)}')
    return order


def _rendered_block(item):
    return GP.g3b2_evidence_block(item['artifact_record'],
                                  tier=item['evidence_tier'],
                                  symptom=item.get('symptom'))


def _load_gold_certs():
    certs = C.read_jsonl(C.G3B2_GOLD_CERTS)
    by = {(c['instance_id'], c['condition']): c for c in certs}
    if len(by) != 50:
        raise SystemExit(f'expected 50 g3b2 gold certs, got {len(by)}')
    return by


def build_freeze():
    # Re-verify G3-A (141) + G3-A.1 (122) + G3-B freeze + frozen code bytes.
    parent = GZ.C.verify_frozen_parents()

    # Pin the G3-B.2 freeze manifest and gold certificates byte-for-byte.
    g3b2_freeze = json.loads(C.G3B2_FREEZE.read_text(encoding='utf-8'))
    g3b2_manifest_sha = C.sha256_file(C.G3B2_FREEZE)
    certs = _load_gold_certs()
    certs_sha = C.sha256_file(C.G3B2_GOLD_CERTS)
    # All 50 certificates must report zero value change vs frozen g3a1 gold.
    changed_certs = [(k[0], k[1]) for k, c in certs.items()
                     if c.get('value_changed')]
    if changed_certs:
        raise SystemExit(
            f'g3b2 gold certs unexpectedly changed vs g3a1: {changed_certs}')

    items = build_items()
    base = base_permutation()
    order = interleaved_order(items, base)
    items_by = {(it['instance_id'], it['condition']): it for it in items}

    prompt_fp = {c: GP.g3b2_prompt_fingerprint(c) for c in C.CONDITIONS}
    # Guard: the fingerprints we freeze must equal the accepted G3-B.2 freeze.
    if prompt_fp != g3b2_freeze['prompt_fingerprints']:
        raise SystemExit(
            'g3b2 prompt fingerprints drifted from the accepted G3-B.2 freeze')

    cells, served = [], []
    for o in order:
        it = items_by[(o['instance_id'], o['condition'])]
        active = o['condition'] in C.ACTIVE_CONDITIONS
        cert = certs[(o['instance_id'], o['condition'])]
        cells.append({
            'serial': o['serial'], 'model_profile': o['model_profile'],
            'instance_id': it['instance_id'], 'id': it['id'],
            'condition': it['condition'], 'cell_key': it['cell_key'],
            'g3b_pair_cell_key': it['g3b_pair_cell_key'],
            'served_artifact_id': it['served_artifact_id'],
            'evidence_tier': it['evidence_tier'], 'active_tools': active,
            'n_static_turns': 1 if not active else None,
            'protocol_version': C.RUN_PROTOCOL_VERSION,
            'prompt_version': C.RUN_PROMPT_VERSION,
            'gold_cert_version': C.RUN_GOLD_CERT_VERSION,
            'prompt_fingerprint': prompt_fp[it['condition']],
            'tools_fingerprint': C.sha256_bytes(json.dumps(
                ternary_tools(it['condition']) or [],
                sort_keys=True, ensure_ascii=False).encode()),
            'audit_oracle_gold': it['_oracle_gold'],
            'audit_condition_gold': cert['condition_gold_new_protocol'],
            'audit_gold_value_changed_vs_g3a1': cert['value_changed'],
            'fresh_state_repaired': it['_freshness_repaired']['fresh_state'],
        })
        payload = {
            'id': it['id'], 'instance_id': it['instance_id'],
            'base_commit': it['base_commit'], 'patch_sha256': it['patch_sha256'],
            'issue': it['issue'], 'patch': it['patch'],
            'claim': it['claim'], 'symptom': it['symptom'],
            'condition': it['condition'], 'evidence_tier': it['evidence_tier'],
            'rendered_static_block': _rendered_block(it),
            'artifact_record': it['artifact_record'],
        }
        served.append({
            'cell_key': it['cell_key'],
            'g3b_pair_cell_key': it['g3b_pair_cell_key'],
            'instance_id': it['instance_id'], 'condition': it['condition'],
            'served_payload_sha256': C.sha256_bytes(json.dumps(
                payload, sort_keys=True, ensure_ascii=False).encode()),
        })

    fresh_states = {}
    for it in items:
        fresh_states.setdefault(it['instance_id'],
                                it['_freshness_repaired']['fresh_state'])
    n_true = sum(1 for s in fresh_states.values() if s == 'TRUE')

    freeze = {
        'freeze_id': C.G3B3_FREEZE_VERSION,
        'gate': C.GATE,
        'runner_version': C.G3B3_RUNNER_VERSION,
        'approval': ('Conditional written approval after Gate 3-B.2 '
                     'acceptance: 100 REAL model cells over the G3-B.2 '
                     'repaired protocol; TOTAL hard cap $3.00; per-model '
                     'cap $1.50; retries_per_cell 0; PROVISIONAL gold '
                     '(annotator2 NOT_OBTAINED, n=1). No new issue, no '
                     'Gemini/R2, no Gate 3-C, no modification of historical '
                     'frozen artifacts, no git commit.'),
        'gold_tier': C.GOLD_AUTHORITY['gold_tier']
                     + ' (mechanically adjudicated, single annotator; '
                       'annotator2 NOT_OBTAINED, n=1).',
        'executed_protocol': {
            'protocol_version': C.RUN_PROTOCOL_VERSION,
            'prompt_version': C.RUN_PROMPT_VERSION,
            'gold_cert_version': C.RUN_GOLD_CERT_VERSION,
            'prompt_module': 'evidence.g3b2_prompts.build_g3b2_messages',
            'server_factory': 'evidence.g3b2_server.build_g3b2_server',
            'freshness_verdicts': 'three-state TRUE/FALSE/UNKNOWN '
                                  '(g3b2_freshness); legacy structurally-'
                                  'false endpoint never called',
        },
        'conditions': list(C.CONDITIONS),
        'static_conditions': list(C.STATIC_CONDITIONS),
        'active_tool_conditions': list(C.ACTIVE_CONDITIONS),
        'sufficient_conditions_primary_endpoint':
            list(C.SUFFICIENT_CONDITIONS),
        'restricted_conditions_overacceptance_control':
            list(C.RESTRICTED_CONDITIONS),
        'reject_oracle_issues': list(C.REJECT_ISSUES),
        'models': list(C.MODELS),
        'n_independent_issues': 10, 'n_items': 50, 'n_cells': 100,
        'oracle_distribution': {'ACCEPT': 7, 'REJECT': 3, 'NEED_EVIDENCE': 0},
        'condition_distribution': {
            'T2D-T': {'NEED_EVIDENCE': 10},
            'T3D-Strict': {'NEED_EVIDENCE': 10},
            'T3D-Escalate': {'ACCEPT': 7, 'REJECT': 3},
            'T2A-T': {'ACCEPT': 7, 'REJECT': 3},
            'T3A-T': {'ACCEPT': 7, 'REJECT': 3}},
        'sampling': {
            'temperature': C.TEMPERATURE,
            'completion_cap_tokens': C.COMPLETION_CAP,
            'max_tool_turns': C.MAX_TOOL_TURNS,
            'max_model_calls_per_cell': C.MAX_MODEL_CALLS_PER_CELL,
            'retries_per_cell': C.RETRIES_PER_CELL,
            'response_format': 'json_schema strict on the final decision '
                               'turn with the frozen ternary schema; tools '
                               'on tool turns only. The adapter maps the '
                               'frozen schema to the per-profile native mode '
                               '(json_object for both approved models). '
                               'Per approval #7 there is NO error-triggered '
                               'in-cell downgrade and NO retry: a 400 on '
                               'response_format (or any non-empty adapter '
                               'fallback_from), like any other capability '
                               'incompatibility or freeze drift, HARD-STOPS '
                               'the run and is reported; never a silent '
                               'downgrade and never a retry on a wrong '
                               'prediction.',
        },
        'profiles': PROFILES,
        'budget': {
            'total_hard_cap_usd': C.TOTAL_BUDGET_USD,
            'per_model_cap_usd': C.PER_MODEL_CAP_USD,
            'price_basis': 'identical peak-list per-1M prices to frozen '
                           'G3-B (DS in 0.30/out 1.20; GPT in 0.40/out '
                           '1.60)',
            'enforcement': 'pre-call BudgetGuard worst-case bound before '
                           'EVERY API request (fresh full transcript resend '
                           'x price_in + completion_cap x price_out), both a '
                           'per-model guard and the shared total guard; '
                           'resume restores cumulative spend; no retry for a '
                           'wrong/unexpected/INVALID/AMBIGUOUS decision',
            'observed_g3b_cost_usd': 0.290658,
            'g3b3_point_estimate_usd': 0.3197,
            'worst_case_usd': C.TOTAL_BUDGET_USD,
        },
        'double_gate': {
            'flag_paid': '--allow-paid-run',
            'flag_acknowledgement': C.ACK,
            'both_required': True,
        },
        'call_order_seed': C.ORDER_SEED,
        'call_order_base_permutation': [
            {'model_profile': m, 'condition': c} for m, c in base],
        'g3b2_anchor': {
            'g3b2_freeze_manifest': str(C.G3B2_FREEZE.relative_to(C.HERE)),
            'g3b2_freeze_manifest_sha256': g3b2_manifest_sha,
            'g3b2_gold_certificates':
                str(C.G3B2_GOLD_CERTS.relative_to(C.HERE)),
            'g3b2_gold_certificates_sha256': certs_sha,
            'g3b2_gold_value_changes_vs_g3a1': len(changed_certs),
        },
        'g3b_pairing': {
            'design': 'each g3b3 cell pairs to its frozen G3-B cell by '
                      'SAME instance_id + condition + model_profile; only '
                      'the protocol version/run time differs',
            'g3b_freeze_manifest': str(C.G3B_FREEZE.relative_to(C.HERE)),
            'g3b_freeze_manifest_sha256': parent['g3b_freeze_manifest']
            ['sha256'],
            'g3b_live_results': {
                'deepseek-flash':
                    str(C.G3B_LIVE_DEEPSEEK.relative_to(C.HERE)),
                'gpt-4.1-mini': str(C.G3B_LIVE_GPT.relative_to(C.HERE))},
            'comparison_kind': 'cross-version, cross-run-time ASSOCIATIONAL '
                               'change; the repair changed freshness and T2A '
                               'trust together, so their separate causal '
                               'effects are NOT identified',
        },
        'repaired_freshness_distribution': {
            'n_true': n_true, 'n_total_issues': len(fresh_states),
            'per_issue': fresh_states,
            'authoritative_source':
                'evidence_store_g3a/audit/g3a_freshness_recompute.json '
                '(independent git restage write-tree vs signed attestation)',
        },
        'prompt_fingerprints': prompt_fp,
        'parent_freeze_verification': parent,
        'cells': cells,
        'served_payloads': served,
        'call_order': order,
        'g3b3_code_hashes': _g3b3_code_hashes(),
        'approved_scope': C.APPROVED_SCOPE,
    }
    return freeze


def _g3b3_code_hashes():
    """Hash the g3b3 modules PLUS the imported g3b2/frozen modules the live
    path depends on, so a freeze drift is detectable before any paid call."""
    g3b3_names = ['g3b3_common.py', 'g3b3_freeze.py', 'g3b3_run.py',
                  'g3b3_livegate.py', 'g3b3_preflight.py',
                  'g3b3_analyze.py', 'g3b3_report.py']
    imported_names = ['g3b2_common.py', 'g3b2_freshness.py', 'g3b2_server.py',
                      'g3b2_prompts.py', 'g3b2_freeze.py',
                      'phase3_run.py', 'ev1_adapters.py', 'prompts.py',
                      'views.py', 'visibility.py', 'server.py', 'store.py',
                      'ternary.py', 'gap_w2.py', 'schemas.py']
    out = {'g3b3_modules': {}, 'imported_frozen_modules': {}}
    for n in g3b3_names:
        p = C.EVID / n
        out['g3b3_modules'][n] = C.sha256_file(p) if p.exists() else None
    for n in imported_names:
        p = C.EVID / n
        out['imported_frozen_modules'][n] = (
            C.sha256_file(p) if p.exists() else None)
    return out


def main():
    freeze = build_freeze()
    C.OUT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_FREEZE.write_bytes(C.canonical_bytes(freeze))
    print(f'g3b3 freeze -> {C.OUT_FREEZE}')
    print(f"items={freeze['n_items']} cells={freeze['n_cells']} "
          f"models={len(freeze['models'])} order={len(freeze['call_order'])}")
    print(f"freshness TRUE {freeze['repaired_freshness_distribution']['n_true']}"
          f"/{freeze['repaired_freshness_distribution']['n_total_issues']}")
    print(f"budget total=${C.TOTAL_BUDGET_USD:.2f} "
          f"per_model=${C.PER_MODEL_CAP_USD:.2f} seed={C.ORDER_SEED}")


if __name__ == '__main__':
    main()
