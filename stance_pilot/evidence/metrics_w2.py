"""Wave-2 Task 8: dual-standard ternary metrics with issue-cluster bootstrap.

Every scored cell is judged against TWO INDEPENDENT gold labels frozen in
wave2_gold.jsonl:

  oracle_gold     the objectively supportable decision when BOTH trustworthy
                  channels are accessible (acceptance outcomes O on linked,
                  fresh evidence; the issue-symptom polarity P).
  condition_gold  the decision supportable from the evidence THIS condition's
                  regime presents/adjudicates/makes obtainable. Cells where
                  the two agree are COMPARABLE; cells where they differ are
                  INSTITUTIONAL DIVERGENCES (the regime withholds a decisive
                  channel, or presents an acceptance block without adjudicating
                  linkage/freshness) and are reported in their own partition.

For each model x condition the module reports:
  * standards.oracle / standards.condition  — separate Decision
    Appropriateness (parseable denominator), E2E success (all cells), and the
    error taxonomy; INVALID/AMBIGUOUS is a single protocol-failure column that
    is gold-independent.
  * partitions.comparable / partitions.divergent — counts and per-standard
    accuracies on each set, with the divergence kind.
  * gap_rates — among parseable NEED_EVIDENCE answers on prompt-v2 rows, the
    four grounding categories from evidence.gap_w2 (grounded verified gap,
    claimed-but-unverified, decisive-in-hand abstention, blanket/unspecified).
    Rows produced under p3-ternary-v1 carry no evidence_gap field: the section
    is explicitly not_applicable there rather than silently scored.
  * static/active arm, escalation passthrough and cost fields.

CIs are issue-cluster bootstraps (evidence.metrics2.cluster_bootstrap,
seed=7, n=10000 default). No model output is ever read to derive gold.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from pilot import read_jsonl
from evidence.gap_w2 import (CATEGORIES, CLAIMED_BUT_UNVERIFIED,
                             DECISIVE_IN_HAND_BUT_ABSTAINED, UNSPECIFIED,
                             VERIFIED_GAP, classify_abstention)
from evidence.metrics2 import cluster_bootstrap
from evidence.metrics3 import load_gold as _load_v1_gold, gold_for as _v1_gold_for
from evidence.ternary import PARSE_CLASSES, TERNARY

CLUSTER_KEY = 'instance_id'
STATIC_CONDITIONS = ('T2D-T', 'T2A-T')
ACTIVE_CONDITIONS = ('T3D-Strict', 'T3D-Escalate', 'T3A-T')
ALL_CONDITIONS = STATIC_CONDITIONS + ACTIVE_CONDITIONS
PROTOCOL_FAILURES = ('INVALID', 'AMBIGUOUS')

# error classes reused from the phase-3 taxonomy
ERROR_CLASSES = (
    'appropriate_accept', 'appropriate_reject', 'appropriate_abstain',
    'over_abstain', 'false_approve', 'false_reject',
    'false_commit_accept', 'unsupported_reject',
    'invalid_protocol', 'ambiguous_protocol',
)

PROMPT_V2 = 'p3-ternary-v2'


# ---------------------------------------------------------------------------
# Gold loading
# ---------------------------------------------------------------------------

def load_w2_gold(path):
    """Index wave2 gold rows by (scenario, id, served_artifact_id), with a
    (scenario, id) fallback for mirror fixtures."""
    rows = list(read_jsonl(path))
    full, loose = {}, {}
    for r in rows:
        full[(r['scenario'], r['id'], r['served_artifact_id'])] = r
        loose.setdefault((r['scenario'], r['id']), r)
    text = Path(path).read_text(encoding='utf-8')
    return {'full': full, 'loose': loose, 'rows': rows,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
            'version': rows[0].get('version') if rows else None}


def w2_gold_for(rec, gold):
    k = (rec.get('scenario'), rec.get('id'), rec.get('served_artifact_id'))
    if k in gold['full']:
        return gold['full'][k]
    return gold['loose'].get((rec.get('scenario'), rec.get('id')))


# ---------------------------------------------------------------------------
# Per-cell classification under one gold label
# ---------------------------------------------------------------------------

def _error_class(parsed, g):
    if parsed not in TERNARY:
        return ('invalid_protocol' if parsed == 'INVALID'
                else 'ambiguous_protocol')
    if parsed == g:
        return {'ACCEPT': 'appropriate_accept',
                'REJECT': 'appropriate_reject',
                'NEED_EVIDENCE': 'appropriate_abstain'}[parsed]
    if g == 'NEED_EVIDENCE':
        return ('false_commit_accept' if parsed == 'ACCEPT'
                else 'unsupported_reject')
    if g == 'ACCEPT':
        return 'false_reject' if parsed == 'REJECT' else 'over_abstain'
    return 'false_approve' if parsed == 'ACCEPT' else 'over_abstain'


def _norm_parsed(rec):
    parsed = rec.get('parsed')
    return parsed if parsed in PARSE_CLASSES else 'INVALID'


def extract_evidence_gap(rec):
    """Return the prompt-v2 evidence_gap string, or None.

    Prefer a runner-captured field (Task 9); fall back to parsing the final
    JSON answer object. v1 answers have no such slot and yield None.
    """
    gap = rec.get('evidence_gap')
    if isinstance(gap, str) and gap.strip():
        return gap.strip().lower()
    answer = rec.get('answer')
    if isinstance(answer, str):
        text = answer.strip()
        if text.startswith('```'):
            text = text.strip('`')
            if text.lower().startswith('json'):
                text = text[4:].strip()
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            return None
        if isinstance(obj, dict):
            g = obj.get('evidence_gap')
            if isinstance(g, str) and g.strip():
                return g.strip().lower()
    return None


def derive_tool_verdicts(rec):
    """Endpoint verdicts actually obtained in this cell.

    Runner aggregation flags (any negative verdict observed) plus an optional
    explicit structured ``tool_verdicts`` row field (used by the wave-2 mock
    /runner). None means the endpoint was not called before the decision.
    """
    tv = dict(rec.get('tool_verdicts') or {})
    if 'linkage' not in tv:
        if rec.get('called_linkage'):
            tv['linkage'] = False if rec.get('saw_linked_false') else True
    if 'freshness' not in tv:
        if rec.get('called_freshness'):
            tv['freshness'] = False if rec.get('saw_fresh_false') else True
    if 'coverage' not in tv:
        if rec.get('called_coverage'):
            tv['coverage'] = False if rec.get('saw_coverage_incomplete') else True
    if 'consistency' not in tv:
        if rec.get('called_consistency'):
            tv['consistency'] = ('contradicted' if rec.get('saw_contradicted')
                                 else 'consistent')
    return tv


def classify_cell(rec, grow):
    """Join one result row with its frozen wave-2 gold row; evaluate against
    BOTH standards and attach grounding / partition / passthrough fields."""
    parsed = _norm_parsed(rec)
    parseable = parsed in TERNARY
    cond = rec.get('condition')
    oracle = grow['oracle_gold']
    cgold = grow['condition_gold'][cond]

    def std(g):
        ec = _error_class(parsed, g)
        return {'gold': g, 'error_class': ec,
                'appropriate': parseable and parsed == g,
                'e2e_success': parseable and parsed == g}

    comparable = oracle == cgold
    if comparable:
        kind = 'aligned'
    elif oracle == 'REJECT' and cgold == 'NEED_EVIDENCE':
        kind = 'restricted_abstention_reject_withheld'
    elif oracle == 'ACCEPT' and cgold == 'NEED_EVIDENCE':
        kind = 'restricted_abstention_accept_unsupportable'
    elif oracle != 'ACCEPT' and cgold == 'ACCEPT':
        kind = 'institutionally_granted_accept'
    elif oracle != 'REJECT' and cgold == 'REJECT':
        kind = 'institutionally_granted_reject'
    else:
        kind = 'other_divergence'

    prompt_version = ((rec.get('version') or {}).get('prompt_version')
                      or rec.get('prompt_version'))
    gap_applicable = parseable and parsed == 'NEED_EVIDENCE' \
        and prompt_version == PROMPT_V2
    gap = None
    if gap_applicable:
        surface = grow['visibility_matrix'][cond]
        gap = classify_abstention(cond, extract_evidence_gap(rec), surface,
                                  derive_tool_verdicts(rec))

    return {
        'scenario': rec.get('scenario'),
        'id': rec.get('id'),
        'instance_id': rec.get(CLUSTER_KEY),
        'served_artifact_id': rec.get('served_artifact_id'),
        'condition': cond,
        'model': rec.get('model'),
        'mock': bool(rec.get('mock')),
        'prompt_version': prompt_version,
        'parsed': parsed,
        'parseable': parseable,
        'standards': {'oracle': std(oracle), 'condition': std(cgold)},
        'oracle_gold': oracle,
        'condition_gold': cgold,
        'comparable': comparable,
        'divergence_kind': kind,
        'decisive_fixture': bool(grow.get('decisive_failure')),
        'wave': grow.get('wave'),
        'gap_classifiable': bool(gap_applicable),
        'gap': gap,
        'cost_usd': float(rec.get('cost_usd') or 0),
        'tokens_in': int(rec.get('tokens_in') or 0),
        'tokens_out': int(rec.get('tokens_out') or 0),
        'tool_calls': int(rec.get('tool_calls') or 0),
        'wall_s': float(rec.get('wall_s') or 0),
        'escalation_requested': len(rec.get('escalation_requested') or []),
        'escalation_granted': len(rec.get('escalation_granted') or []),
        'escalation_denied': len(rec.get('escalation_denied') or []),
        'budget_hit': bool(rec.get('budget_hit')),
        'emergency_hit': bool(rec.get('emergency_hit')),
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _ratio(num, den):
    return round(num / den, 4) if den else None


def _bootstrap(rows, key, n_boot):
    vals = [int(e['standards'][key]['appropriate']) for e in rows]
    if not rows:
        return {'mean': None, 'ci95': [None, None], 'n_clusters': 0}
    return cluster_bootstrap(vals, [e[CLUSTER_KEY] for e in rows],
                             n_boot=n_boot)


def _standard_block(cells, standard, n_boot, *, use_e2e_denom=False):
    """DA (parseable denominator) or E2E (all cells) for one gold standard."""
    if use_e2e_denom:
        denom_rows = cells
        n_ok = sum(e['standards'][standard]['e2e_success'] for e in cells)
        ci_rows = cells
    else:
        denom_rows = [e for e in cells if e['parseable']]
        n_ok = sum(e['standards'][standard]['appropriate']
                   for e in denom_rows)
        ci_rows = denom_rows
    n = len(denom_rows)
    bs = _bootstrap(ci_rows, standard, n_boot) if ci_rows else \
        {'mean': None, 'ci95': [None, None], 'n_clusters': 0}
    return {'n_denominator': n, 'n_correct': n_ok,
            'rate': _ratio(n_ok, n),
            'ci95_cluster_bootstrap_seed7': bs['ci95'],
            'n_issues': len({e[CLUSTER_KEY] for e in denom_rows
                            if e[CLUSTER_KEY]})}


def _gap_rates(cells):
    need = [e for e in cells if e['gap_classifiable']]
    if not need:
        return {'applicable': False,
                'reason': 'no parseable NEED_EVIDENCE rows produced under '
                          'p3-ternary-v2 in this block',
                'n_need_denominator': 0,
                'rates': {c: None for c in CATEGORIES},
                'category_counts': {c: 0 for c in CATEGORIES},
                'raw_gap_distribution': {}}
    counts = Counter(e['gap']['category'] for e in need)
    raw = Counter(e['gap']['gap'] for e in need)
    n = len(need)
    return {
        'applicable': True,
        'n_need_denominator': n,
        'denominator_note': 'parseable NEED_EVIDENCE answers from '
                            'p3-ternary-v2 rows only',
        'rates': {c: _ratio(counts.get(c, 0), n) for c in CATEGORIES},
        'category_counts': {c: counts.get(c, 0) for c in CATEGORIES},
        'raw_gap_distribution': dict(raw),
        'rate_names': {
            VERIFIED_GAP: 'grounded_abstention_rate',
            CLAIMED_BUT_UNVERIFIED: 'claimed_but_unverified_rate',
            DECISIVE_IN_HAND_BUT_ABSTAINED:
                'decisive_in_hand_but_abstained_rate',
            UNSPECIFIED: 'blanket_unspecified_rate'},
        'cells': [{'scenario': e['scenario'], 'condition': e['condition'],
                   'served_artifact_id': e['served_artifact_id'],
                   'gap': e['gap']['gap'], 'category': e['gap']['category'],
                   'basis': e['gap']['basis']} for e in need],
    }


def _partition_block(cells, divergent, n_boot):
    rows = [e for e in cells if e['comparable'] != divergent] if divergent \
        else [e for e in cells if e['comparable']]
    if not rows:
        return {'n_cells': 0}
    kinds = Counter(e['divergence_kind'] for e in rows)
    out = {
        'n_cells': len(rows),
        'n_issues': len({e[CLUSTER_KEY] for e in rows if e[CLUSTER_KEY]}),
        'oracle': _standard_block(rows, 'oracle', n_boot),
        'condition': _standard_block(rows, 'condition', n_boot),
    }
    if divergent:
        out['divergence_kind_counts'] = dict(kinds)
        out['cells'] = [{
            'scenario': e['scenario'], 'condition': e['condition'],
            'served_artifact_id': e['served_artifact_id'],
            'parsed': e['parsed'], 'oracle_gold': e['oracle_gold'],
            'condition_gold': e['condition_gold'], 'kind': e['divergence_kind'],
            'oracle_appropriate':
                e['standards']['oracle']['appropriate'],
            'condition_appropriate':
                e['standards']['condition']['appropriate'],
        } for e in rows]
    return out


def _condition_block(cells, n_boot):
    n = len(cells)
    n_parseable = sum(e['parseable'] for e in cells)
    n_inv = sum(e['parsed'] == 'INVALID' for e in cells)
    n_amb = sum(e['parsed'] == 'AMBIGUOUS' for e in cells)
    err = {k: Counter() for k in ('oracle', 'condition')}
    for e in cells:
        for std in ('oracle', 'condition'):
            err[std][e['standards'][std]['error_class']] += 1
    usd = sum(e['cost_usd'] for e in cells)
    n_appr_o = sum(e['standards']['oracle']['appropriate']
                   for e in cells if e['parseable'])
    cond = cells[0]['condition']
    return {
        'condition': cond,
        'arm': ('static' if cond in STATIC_CONDITIONS
                else 'active' if cond in ACTIVE_CONDITIONS else 'other'),
        'n_cells': n,
        'n_issues': len({e[CLUSTER_KEY] for e in cells if e[CLUSTER_KEY]}),
        'n_parseable': n_parseable,
        'n_invalid': n_inv,
        'n_ambiguous': n_amb,
        'invalid_or_ambiguous_rate_of_all': _ratio(n_inv + n_amb, n),
        'standards': {
            'oracle': {
                **_standard_block(cells, 'oracle', n_boot),
                'e2e': _standard_block(cells, 'oracle', n_boot,
                                       use_e2e_denom=True),
                'error_class_counts': {
                    k: err['oracle'].get(k, 0) for k in ERROR_CLASSES},
            },
            'condition': {
                **_standard_block(cells, 'condition', n_boot),
                'e2e': _standard_block(cells, 'condition', n_boot,
                                       use_e2e_denom=True),
                'error_class_counts': {
                    k: err['condition'].get(k, 0) for k in ERROR_CLASSES},
            },
        },
        'partitions': {
            'comparable': _partition_block(cells, False, n_boot),
            'divergent': _partition_block(cells, True, n_boot),
        },
        'gap_rates': _gap_rates(cells),
        'escalation': {
            'requests': sum(e['escalation_requested'] for e in cells),
            'granted': sum(e['escalation_granted'] for e in cells),
            'denied': sum(e['escalation_denied'] for e in cells),
            'cells_with_granted_escalation':
                sum(1 for e in cells if e['escalation_granted'] > 0),
        },
        'cost': {
            'tokens_in': sum(e['tokens_in'] for e in cells),
            'tokens_out': sum(e['tokens_out'] for e in cells),
            'tool_calls': sum(e['tool_calls'] for e in cells),
            'wall_s_total': round(sum(e['wall_s'] for e in cells), 2),
            'usd_total': round(usd, 6),
            'usd_per_oracle_appropriate_decision':
                round(usd / n_appr_o, 6) if n_appr_o else None,
            'budget_hits': sum(e['budget_hit'] for e in cells),
            'emergency_hits': sum(e['emergency_hit'] for e in cells),
        },
    }


def _overall(cells, name, n_boot):
    if not cells:
        return {'slice': name, 'n_cells': 0}
    static = [e for e in cells if e['condition'] in STATIC_CONDITIONS]
    active = [e for e in cells if e['condition'] in ACTIVE_CONDITIONS]
    return {
        'slice': name,
        'n_cells': len(cells),
        'n_issues': len({e[CLUSTER_KEY] for e in cells if e[CLUSTER_KEY]}),
        'n_invalid': sum(e['parsed'] == 'INVALID' for e in cells),
        'n_ambiguous': sum(e['parsed'] == 'AMBIGUOUS' for e in cells),
        'standards': {
            std: {
                'decision_appropriateness':
                    _standard_block(cells, std, n_boot),
                'end_to_end_review_success':
                    _standard_block(cells, std, n_boot,
                                    use_e2e_denom=True),
            } for std in ('oracle', 'condition')},
        'arms': {
            'static': {
                'n_cells': len(static),
                'oracle': _standard_block(static, 'oracle', n_boot),
                'condition': _standard_block(static, 'condition', n_boot),
            },
            'active': {
                'n_cells': len(active),
                'oracle': _standard_block(active, 'oracle', n_boot),
                'condition': _standard_block(active, 'condition', n_boot),
            },
        },
        'gap_rates': _gap_rates(cells),
    }


# ---------------------------------------------------------------------------
# v1 ledger: what changed when the same 45 rows are rescored under wave-2 gold
# ---------------------------------------------------------------------------

def v1_flip_ledger(records, cells, v1_gold_path):
    """For each wave-1 cell, compare its phase-3 single-gold classification
    with BOTH wave-2 standards. Returns every cell whose v1 error class
    differs from at least one wave-2 standard. Missing v1 gold is tolerated
    (returns None) so wave-2-only runs need not supply it."""
    if not v1_gold_path or not Path(v1_gold_path).exists():
        return None
    v1 = _load_v1_gold(v1_gold_path)
    by_key = {(e['scenario'], e['condition'], e['served_artifact_id']): e
              for e in cells}
    flips = []
    for r in records:
        g1 = _v1_gold_for(r, v1)
        if g1 is None:
            continue
        parsed = _norm_parsed(r)
        c1 = _error_class(parsed, g1['gold'])
        e = by_key.get((r.get('scenario'), r.get('condition'),
                        r.get('served_artifact_id')))
        if e is None:
            continue
        co = e['standards']['oracle']['error_class']
        cc = e['standards']['condition']['error_class']
        if c1 == co == cc:
            continue
        flips.append({
            'scenario': e['scenario'], 'condition': e['condition'],
            'id': e['id'], 'served_artifact_id': e['served_artifact_id'],
            'parsed': parsed,
            'v1_gold': g1['gold'], 'v1_error_class': c1,
            'oracle_gold': e['oracle_gold'], 'oracle_error_class': co,
            'condition_gold': e['condition_gold'],
            'condition_error_class': cc,
            'comparable': e['comparable'],
            'divergence_kind': e['divergence_kind'],
        })
    flips.sort(key=lambda x: (x['scenario'],
                              ALL_CONDITIONS.index(x['condition'])))
    kinds = Counter((f['scenario'], f['condition']) for f in flips)
    return {
        'v1_gold_path': str(v1_gold_path),
        'n_changed_cells': len(flips),
        'changed_cell_counts': {f'{s}|{c}': n for (s, c), n in
                                sorted(kinds.items())},
        'interpretation': {
            'oracle_vs_v1': 'oracle gold applies the dual-channel rule: a '
                            'persisting issue symptom alone forces REJECT '
                            '(v1 scored wrong_patch NEED), independent of '
                            'artifact linkage',
            'condition_vs_v1': 'condition gold scores the answer the regime '
                               'actually supports: withheld decisive channels '
                               'turn v1 over-abstention into appropriate '
                               'abstention; an institutionally presented '
                               'all-green block (T2A) can turn v1 appropriate '
                               'abstention into over-abstention',
        },
        'cells': flips,
    }


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def compute(records, gold, *, include_mock=False, n_boot=10000,
            v1_gold_path=None):
    records = [r for r in list(records)
               if not r.get('error') and (include_mock or not r.get('mock'))]
    cells, missing = [], []
    for r in records:
        grow = w2_gold_for(r, gold)
        if grow is None:
            missing.append(f"{r.get('scenario')}|{r.get('id')}|"
                           f"{r.get('served_artifact_id')}")
            continue
        cells.append(classify_cell(r, grow))
    if missing:
        raise SystemExit('metrics_w2: results without frozen wave-2 gold row: '
                         + '; '.join(sorted(set(missing))))

    by_mc = defaultdict(list)
    for e in cells:
        by_mc[(e['model'], e['condition'])].append(e)
    conditions = {}
    for (model, cond), rows in sorted(by_mc.items()):
        blk = _condition_block(rows, n_boot)
        blk['model'] = model
        conditions[f'{model}|{cond}'] = blk

    comparable = [e for e in cells if e['comparable']]
    divergent = [e for e in cells if not e['comparable']]
    out = {
        'metric': 'groundedreview_wave2_dual_standard',
        'official': False,
        'version_notes': {
            'gold_version': gold['version'],
            'gold_sha256': gold['sha256'],
            'scoring': 'dual standard: oracle_gold (channels O+P) and '
                       'condition_gold (evidence accessible per regime)',
            'bootstrap': 'issue-cluster resample, seed=7, '
                         f'n_boot={n_boot}',
            'not_official': 'this file never replaces '
                            'metrics_phase3_ternary.json; the phase-3 file '
                            'remains the frozen single-gold official score',
            'gap_rates': 'four grounding categories among parseable '
                         'NEED_EVIDENCE answers; only p3-ternary-v2 rows are '
                         'classifiable',
        },
        'n_records_scored': len(cells),
        'n_fixture_artifacts': len({e['served_artifact_id'] for e in cells}),
        'n_issues': len({e[CLUSTER_KEY] for e in cells if e[CLUSTER_KEY]}),
        'models': sorted({e['model'] for e in cells}),
        'prompt_versions': sorted({e['prompt_version'] for e in cells
                                   if e['prompt_version']}),
        'conditions': conditions,
        'overall': _overall(cells, 'all_cells', n_boot),
        'overall_comparable': _overall(comparable, 'comparable_cells', n_boot),
        'overall_divergent': _overall(divergent, 'divergent_cells', n_boot),
        'cells': [{
            'scenario': e['scenario'], 'id': e['id'],
            'instance_id': e['instance_id'], 'wave': e['wave'],
            'condition': e['condition'], 'model': e['model'],
            'served_artifact_id': e['served_artifact_id'],
            'parsed': e['parsed'], 'parseable': e['parseable'],
            'oracle_gold': e['oracle_gold'],
            'oracle_error_class':
                e['standards']['oracle']['error_class'],
            'oracle_appropriate': e['standards']['oracle']['appropriate'],
            'condition_gold': e['condition_gold'],
            'condition_error_class':
                e['standards']['condition']['error_class'],
            'condition_appropriate':
                e['standards']['condition']['appropriate'],
            'comparable': e['comparable'],
            'divergence_kind': e['divergence_kind'],
            'prompt_version': e['prompt_version'],
            'gap_category': (e['gap']['category'] if e['gap'] else None),
            'evidence_gap': (e['gap']['gap'] if e['gap'] else None),
            'cost_usd': e['cost_usd'],
            'escalation_granted': e['escalation_granted'],
        } for e in sorted(
            cells, key=lambda x: (x['scenario'] or '',
                                  ALL_CONDITIONS.index(x['condition'])))],
        'flip_ledger_vs_phase3_v1_gold':
            v1_flip_ledger(records, cells, v1_gold_path),
        'interpretation': {
            'oracle_standard': 'would the decision be appropriate with all '
                               'trustworthy evidence (O and P channels)?',
            'condition_standard': 'was the decision appropriate given ONLY '
                                  'evidence the condition regime makes '
                                  'accessible?',
            'no_cross_condition_averaging': 'oracle-vs-condition deltas are '
                                            'descriptive; paired comparisons '
                                            'remain restricted to shared '
                                            'fixture sets',
        },
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results',
                    default='evidence_store/phase3_ternary_results.jsonl')
    ap.add_argument('--w2-gold', default='evidence_store/wave2_gold.jsonl')
    ap.add_argument('--v1-gold', default='evidence_store/phase3_gold.jsonl')
    ap.add_argument('--out',
                    default='evidence_store/wave2_shadow_wave1_scores.json')
    ap.add_argument('--include-mock', action='store_true')
    ap.add_argument('--bootstrap', type=int, default=10000)
    a = ap.parse_args()
    gold = load_w2_gold(a.w2_gold)
    records = list(read_jsonl(a.results))
    m = compute(records, gold, include_mock=a.include_mock,
                n_boot=a.bootstrap, v1_gold_path=a.v1_gold)
    Path(a.out).write_text(json.dumps(m, indent=2, ensure_ascii=False),
                           encoding='utf-8')
    print(f"scored {m['n_records_scored']} rows; "
          f"issues={m['n_issues']} artifacts={m['n_fixture_artifacts']}")
    for k, blk in m['conditions'].items():
        o = blk['standards']['oracle']
        c = blk['standards']['condition']
        print(f"{k:<40} oracle DA={o['rate']}  condition DA={c['rate']}  "
              f"comparable={blk['partitions']['comparable']['n_cells']} "
              f"divergent={blk['partitions']['divergent']['n_cells']}")
    led = m['flip_ledger_vs_phase3_v1_gold']
    if led:
        print(f"v1 ledger changed cells: {led['n_changed_cells']}")
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
