"""GroundedReview Gate 3-B — External Feasibility Pilot FREEZE (zero API).

Conditional written approval (Gate 3-A.1 acceptance + Gate 3-B authorisation):
100 REAL model cells = 2 models x 10 independent SymPy issues x 5 FROZEN
evidence-regime conditions, served over the FROZEN v2 ternary protocol and
the FROZEN Wave-2 evidence tool server. Gold stays PROVISIONAL (single
annotator; annotator2 NOT_OBTAINED); this is NOT an independent gold
validation. No prompt/gold/evidence material is changed: only a G3-B cell
builder and manifest are added.

This module ONLY derives and writes a deterministic freeze manifest:
  evidence_store_g3b/g3b_freeze_manifest.json
It re-verifies that the G3-A (141) and G3-A.1 (122) frozen file sets are
byte-identical, constructs the 100 cells from the frozen G3-A target rows +
signed artifact store (labels never enter a cell), fixes the interleaved
serial order, the sampling parameters, the vendor prices, the served-model
id allow-list, and the user-authorized budget HARD caps:
    TOTAL $3.00 across both models; $1.50 per model.
It never calls a model and never writes outside evidence_store_g3b except the
one manifest itself.

Offline:
    uv run --python 3.13 -m evidence.g3b_freeze
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence.phase3_run import TERNARY_PROMPT_VERSION_V2
from evidence.prompts import (CLAIM_POSITIVE, ternary_prompt_fingerprint_v2,
                              ternary_tools)
from evidence.schemas import make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl
from evidence.views import display_for_tier
from evidence.visibility import W2_CONDITIONS, project_surface
from evidence.g3a1_conditions import COND_VER

HERE = Path(__file__).resolve().parent.parent
EVID = HERE / 'evidence'
G3A = HERE / 'evidence_store_g3a'
G3A1 = HERE / 'evidence_store_g3a1'
G3B = HERE / 'evidence_store_g3b'
G3A_MANIFEST = G3A / 'g3a_freeze_manifest.json'
G3A1_MANIFEST = G3A1 / 'g3a1_freeze_manifest.json'
OUT_DIR = G3B / 'freeze'
OUT = OUT_DIR / 'g3b_freeze_manifest.json'

GATE = 'gate3b_external_feasibility_pilot'
PROMPT_VERSION = TERNARY_PROMPT_VERSION_V2
CONDITIONS = tuple(W2_CONDITIONS)           # the five frozen regimes
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')       # one model turn, no tools
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')  # real tool loop
MODELS = ('deepseek-flash', 'gpt-4.1-mini')

# User-authorized hard caps (the $5/$2.5 planning suggestion was explicitly
# rejected; these values are the approval, the runner may not exceed them).
TOTAL_BUDGET_USD = 3.00
PER_MODEL_CAP_USD = 1.50

# FROZEN execution parameters. v2 ternary protocol defaults: temperature 0,
# hard per-call completion cap 8192 (identical to phase3/ev1 multi-turn). The
# prompt and the 8192 cap are NOT new choices for Gate 3-B: they are the
# frozen Wave-2 multi-turn protocol values, recorded here for audit.
TEMPERATURE = 0
COMPLETION_CAP = 8192
MAX_TOOL_TURNS = 8
MAX_MODEL_CALLS_PER_CELL = 12
ORDER_SEED = 7

# Vendor profiles for the two approved models. Prices are per 1,000,000 tokens
# and are the same PEAK-list prices used across the EAL/E1 work; the runner
# refuses to run if a profile in code differs from what this freeze records.
PROFILES = {
    'deepseek-flash': {
        'provider': 'deepseek', 'model': 'deepseek-flash',
        'base_url': 'https://api.deepseek.com/v1',
        'key_env': 'DEEPSEEK_API_KEY',
        'price_in_per_1m': 0.30, 'price_out_per_1m': 1.20,
        'extra_body': {'thinking': {'type': 'disabled'}},
        'completion_param': 'max_tokens',
        'response_format': 'json_object',
        'temperature_supported': True,
        'expected_served_model_id': 'deepseek-flash',
        'per_model_cap_usd': PER_MODEL_CAP_USD,
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
        'temperature_supported': True,
        'expected_served_model_id': 'gpt-4.1-mini-2025-04-14',
        'per_model_cap_usd': PER_MODEL_CAP_USD,
    },
}

ACK = '--i-acknowledge-g3b-approved'

# Fields that carry an answer/label and must NEVER be placed into a cell or
# rendered to a model. The builder asserts none of these keys are attached.
_LABEL_KEYS = ('oracle_gold', 'label_class', 'merge_acceptable', 'resolved',
               'builder_label_class_audit_only', 'expected', 'gold',
               'condition_gold', 'resolved_in_dataset')


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_frozen_parents():
    """Re-hash every file in the G3-A and G3-A.1 manifests; assert zero drift."""
    out = {}
    for tag, man_path, base in (('g3a', G3A_MANIFEST, G3A),
                                ('g3a1', G3A1_MANIFEST, G3A1)):
        man = json.loads(man_path.read_text(encoding='utf-8'))
        changed, missing = [], []
        for f in man['files']:
            p = base / f['path'] if tag == 'g3a1' else G3A / f['path']
            # g3a1 manifest paths are repo-relative (evidence_store_g3a1/...).
            if tag == 'g3a1':
                p = HERE / f['path']
            if not p.exists():
                missing.append(f['path'])
            elif _sha_file(p) != f['sha256']:
                changed.append(f['path'])
        if changed or missing:
            raise SystemExit(
                f'FROZEN {tag} DRIFT changed={changed} missing={missing}')
        out[tag] = {'manifest': man_path.name, 'files_verified': len(man['files']),
                    'manifest_sha256': _sha_file(man_path)}
    return out


def _issue_fact_bundle(gold_row, pres_a):
    """Oracle fact bundle with IDENTICAL semantics to g3a1_conditions.main,
    used only to precompute the projected presented facts for v2 gap
    classification. These facts are NEVER rendered (only their projection is
    attached for the offline classifier)."""
    from evidence.ternary import _executed_counts
    f = gold_row['facts']
    pf, pe = _executed_counts(pres_a)
    return {
        'linked': f['linked'], 'fresh': f['fresh'], 'complete': f['complete'],
        'executed_failure_count': f['executed_failure_count'],
        'executed_check_count': f['executed_check_count'],
        'symptom_polarity': f['symptom_polarity'],
        'presented_a_record': pres_a,
        'presented_failure_count': pf, 'presented_check_count': pe,
    }


def build_cells():
    """Construct the 50 issue-condition items (x2 models at run time =100).

    Labels are deliberately excluded; issue/patch/claim and the tier-projected
    artifact are the only served content. symptom is the issue-derived
    reproduction probe polarity (diagnostic evidence), not a verdict.
    """
    store = ArtifactStore(str(G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    raw = {r['instance_id']: r
           for r in read_jsonl(str(G3A / 'raw' / 'g3a_target_rows.jsonl'))}
    gold = {g['instance_id']: g
            for g in read_jsonl(str(G3A / 'gold' / 'g3a_gold.jsonl'))}
    cond_gold = {r['instance_id']: r
                 for r in read_jsonl(str(G3A / 'gold' / 'g3a1_condition_gold.jsonl'))}

    items = []
    for iid in sorted(raw):
        if iid not in gold:
            raise SystemExit(f'missing frozen gold for {iid}')
        r, grow = raw[iid], gold[iid]
        patch = grow['patch_sha256']
        aid = make_artifact_id(iid, patch)
        rec, authentic = store.get(aid)
        if not authentic:
            raise SystemExit(f'inauthentic artifact for {iid}')
        symptom = {
            'pre_patch_passed': grow['facts']['symptom_pre_passed'],
            'post_patch_passed': grow['facts']['symptom_post_passed'],
        }
        f = grow['facts']
        facts_bundle = None
        for cond in CONDITIONS:
            from evidence.phase3_run import ternary_condition_tier_policy
            _, tier, _ = ternary_condition_tier_policy(cond)
            artifact_record = display_for_tier(store, rec, iid, patch, tier)
            if facts_bundle is None:
                facts_bundle = _issue_fact_bundle(
                    grow, display_for_tier(store, rec, iid, patch, 'A'))
            item = {
                'id': r['id'], 'instance_id': iid, 'repo': r.get('repo'),
                'base_commit': grow['base_commit'], 'patch_sha256': patch,
                'issue': r['problem_statement'], 'patch': r['model_patch'],
                'condition': cond,
                'served_artifact_id': aid,
                'claim': CLAIM_POSITIVE, 'with_claim': True,
                'symptom': symptom,
                'evidence_tier': tier,
                'cell_key': f'g3b:{iid}:{cond}',
                'artifact_record': artifact_record,
                # offline-only projected surface for v2 gap classification
                '_presented_facts': project_surface(cond, facts_bundle),
                # audit-only gold linkage (never rendered; used by analyzer)
                '_oracle_gold': grow['oracle_gold'],
                '_condition_gold': cond_gold[iid]['condition_gold'][cond],
            }
            for k in _LABEL_KEYS:
                base = item
                if k in base and not k.startswith('_'):
                    raise SystemExit(f'label leak: {k} on cell {iid}:{cond}')
            items.append(item)
    if len(items) != 50:
        raise SystemExit(f'expected 50 items, got {len(items)}')
    return items


def interleaved_order(items):
    """Deterministic serial order over 100 cells.

    One issue block = 10 (model x condition) slots. Within a block the two
    models alternate across the five conditions on a fixed base sequence; the
    block rotates by one slot per issue (cyclic Latin shift). Every
    (model, condition) appears exactly once per issue and 10 times overall;
    neither model nor condition is confounded with serial/time position.
    """
    base = [
        ('deepseek-flash', 'T2D-T'), ('gpt-4.1-mini', 'T2D-T'),
        ('deepseek-flash', 'T3D-Strict'), ('gpt-4.1-mini', 'T3D-Strict'),
        ('deepseek-flash', 'T3D-Escalate'), ('gpt-4.1-mini', 'T3D-Escalate'),
        ('deepseek-flash', 'T2A-T'), ('gpt-4.1-mini', 'T2A-T'),
        ('deepseek-flash', 'T3A-T'), ('gpt-4.1-mini', 'T3A-T'),
    ]
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
                'served_artifact_id': it['served_artifact_id'],
            })
    from collections import Counter
    cnt = Counter((o['model_profile'], o['condition']) for o in order)
    if len(order) != 100 or len(cnt) != 10 or set(cnt.values()) != {10}:
        raise SystemExit(f'G3-B order balance broken: {dict(cnt)}')
    return order


def build_freeze():
    parent = verify_frozen_parents()
    items = build_cells()
    order = interleaved_order(items)

    # One frozen cell record per (model, issue, condition) = 100. The rendered
    # item content is identical for both models; only model identity differs.
    cells = []
    prompt_fp = {c: ternary_prompt_fingerprint_v2(c) for c in CONDITIONS}
    for o in order:
        it = next(x for x in items
                  if x['instance_id'] == o['instance_id']
                  and x['condition'] == o['condition'])
        active = o['condition'] in ACTIVE_CONDITIONS
        cells.append({
            'serial': o['serial'], 'model_profile': o['model_profile'],
            'instance_id': it['instance_id'], 'id': it['id'],
            'condition': it['condition'], 'cell_key': it['cell_key'],
            'served_artifact_id': it['served_artifact_id'],
            'evidence_tier': it['evidence_tier'],
            'active_tools': active,
            'n_static_turns': 1 if not active else None,
            'prompt_version': PROMPT_VERSION,
            'prompt_fingerprint': prompt_fp[it['condition']],
            'tools_fingerprint': _sha(json.dumps(
                ternary_tools(it['condition']) or [],
                sort_keys=True, ensure_ascii=False).encode()),
            'audit_oracle_gold': it['_oracle_gold'],
            'audit_condition_gold': it['_condition_gold'],
        })

    # Deterministic content hashes of the item-invariant + item-variant served
    # content, excluding the artifact_record (recomputed through the signed
    # store chokepoint at run time and hash-checked there) and the _-audit
    # facts/gold. These pin issue/patch/claim/symptom and the tier projection.
    served = []
    for it in items:
        payload = {
            'id': it['id'], 'instance_id': it['instance_id'],
            'base_commit': it['base_commit'], 'patch_sha256': it['patch_sha256'],
            'issue': it['issue'], 'patch': it['patch'],
            'claim': it['claim'], 'symptom': it['symptom'],
            'condition': it['condition'], 'evidence_tier': it['evidence_tier'],
            'artifact_record': it['artifact_record'],
        }
        served.append({
            'cell_key': it['cell_key'], 'instance_id': it['instance_id'],
            'condition': it['condition'],
            'served_payload_sha256': _sha(json.dumps(
                payload, sort_keys=True, ensure_ascii=False).encode()),
        })

    freeze = {
        'freeze_id': 'groundedreview-gate3b-external-feasibility-pilot-v1',
        'gate': GATE,
        'approval': ('Conditional written approval after Gate 3-A.1 '
                     'acceptance: 100 real model cells; TOTAL hard cap '
                     '$3.00; per-model cap $1.50; PROVISIONAL gold; not an '
                     'independent human-adjudicated validation.'),
        'gold_tier': ('PROVISIONAL (mechanically adjudicated, single '
                      'annotator; annotator2 NOT_OBTAINED, n=1). Against '
                      'provisional, singly-adjudicated gold only.'),
        'condition_gold_version': COND_VER,
        'prompt_version': PROMPT_VERSION,
        'conditions': list(CONDITIONS),
        'static_conditions': list(STATIC_CONDITIONS),
        'active_tool_conditions': list(ACTIVE_CONDITIONS),
        'models': list(MODELS),
        'n_independent_issues': 10,
        'n_cells': 100,
        'oracle_distribution': {'ACCEPT': 7, 'REJECT': 3, 'NEED_EVIDENCE': 0},
        'condition_distribution': {
            'T2D-T': {'NEED_EVIDENCE': 10},
            'T3D-Strict': {'NEED_EVIDENCE': 10},
            'T3D-Escalate': {'ACCEPT': 7, 'REJECT': 3},
            'T2A-T': {'ACCEPT': 7, 'REJECT': 3},
            'T3A-T': {'ACCEPT': 7, 'REJECT': 3},
        },
        'sampling': {
            'temperature': TEMPERATURE,
            'completion_cap_tokens': COMPLETION_CAP,
            'max_tool_turns': MAX_TOOL_TURNS,
            'max_model_calls_per_cell': MAX_MODEL_CALLS_PER_CELL,
            'retries_per_cell': 0,
            'response_format': 'json_object (final decision turn); tools on '
                               'tool turns only',
        },
        'profiles': PROFILES,
        'budget': {
            'total_hard_cap_usd': TOTAL_BUDGET_USD,
            'per_model_cap_usd': PER_MODEL_CAP_USD,
            'enforcement': 'pre-call BudgetGuard on every model call + a '
                           'global total-cap check before every send; '
                           'resume accumulates prior spend',
            'multi_turn_note': '100 CELLS, not 100 single API calls: the 3 '
                               'active conditions use a real multi-turn tool '
                               'session (frozen max %d tool turns / %d model '
                               'calls per cell). The $1.13 single-turn '
                               'planning figure under-counts; the wave2.1 '
                               'multi-turn observed-token proxy (~$0.49 for '
                               '100 cells across both models) leaves wide '
                               'headroom under the $3.00 cap, to be '
                               'confirmed by the zero-cost full mock.'
                               % (MAX_TOOL_TURNS, MAX_MODEL_CALLS_PER_CELL),
        },
        'call_order_seed': ORDER_SEED,
        'parent_freeze_verification': parent,
        'prompt_fingerprints': prompt_fp,
        'cells': cells,
        'served_payloads': served,
        'call_order': order,
        'code_hashes': _code_hashes(),
        'approved_scope': {
            'new_issues_or_mirrors': False,
            'prompt_gold_evidence_changes': False,
            'gemini_or_r2_or_gate3c': False,
            'git_commit': False,
        },
    }
    return freeze


def _code_hashes():
    names = ['g3b_freeze.py', 'g3b_run.py', 'g3b_preflight.py',
             'g3b_analyze.py', 'phase3_run.py', 'ev1_adapters.py',
             'prompts.py', 'views.py', 'visibility.py', 'server.py',
             'ternary.py', 'cee_protocol.py']
    out = {}
    for n in names:
        p = EVID / n
        out[n] = _sha_file(p) if p.exists() else None
    return out


def canonical_bytes(freeze):
    return (json.dumps(freeze, ensure_ascii=False, indent=2,
                       sort_keys=True) + '\n').encode('utf-8')


def main():
    freeze = build_freeze()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(canonical_bytes(freeze))
    print(f'G3-B freeze -> {OUT}')
    print(f"cells={freeze['n_cells']} conditions={len(CONDITIONS)} "
          f"models={len(MODELS)} order={len(freeze['call_order'])}")
    print('parent freezes verified:',
          {k: v['files_verified'] for k, v in
           freeze['parent_freeze_verification'].items()})
    print(f"budget: total=${TOTAL_BUDGET_USD:.2f} "
          f"per_model=${PER_MODEL_CAP_USD:.2f}")


if __name__ == '__main__':
    main()
