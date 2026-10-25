"""Phase-3 ternary review protocol: schema, parsing, asymmetric gold standard.

This module is ADDITIVE. The binary pilot.parse_decision / DECISION_SCHEMA and
every Phase-1/2 code path are untouched.

Three decisions:
  ACCEPT         evidence is intact AND sufficient success is demonstrated
  REJECT         trustworthy, *applicable* DECISIVE FAILURE evidence exists
                  (applicability requires linked + fresh; completeness NOT
                   required -> partial-but-decisive failure still rejects)
  NEED_EVIDENCE  neither: evidence is missing/stale/mismatched/incomplete and
                  no decisive failure has been established

Research construct: Evidence-Asymmetric Verification. The evidence bar to
REJECT (a credible applicable failure) can be lower than the bar to ACCEPT
(complete, fresh, linked, failure-free success). Gold is derived ONLY from
evidence facts (linkage/freshness/completeness + normalized executed test
outcomes of the signed artifact). The hidden merge_acceptable label is never
an input to gold_decision; it is carried solely as an audit column.
"""
from __future__ import annotations

import argparse, json, re
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.store import ArtifactStore

TERNARY = ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')
# parser outcomes add protocol-failure classes
PARSE_CLASSES = TERNARY + ('INVALID', 'AMBIGUOUS')

TERNARY_DECISION_SCHEMA = {
    'name': 'ternary_review_decision', 'strict': True, 'schema': {
        'type': 'object',
        'properties': {
            'decision': {'type': 'string', 'enum': list(TERNARY)},
            'reason': {'type': 'string'},
            'evidence_mismatch': {'type': 'boolean'},
            # when NEED_EVIDENCE: which evidence gap prevents a decision
            'missing_evidence': {'type': 'string'},
        },
        'required': ['decision', 'reason', 'evidence_mismatch'],
        'additionalProperties': False,
    },
}


def extract_candidates(text):
    """Every top-level-looking JSON object substring that parses with a
    'decision' key (same conservative shape as pilot.extract_candidates)."""
    out = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text or ''):
        try:
            obj = json.loads(m.group(0))
        except Exception:
            continue
        if isinstance(obj, dict) and 'decision' in obj:
            out.append(obj)
    return out


def parse_ternary_decision(text):
    """Return one of ACCEPT/REJECT/NEED_EVIDENCE/INVALID/AMBIGUOUS.

    INVALID  : no parseable ternary decision
    AMBIGUOUS: several parseable decisions that disagree (never guess one)
    """
    cands = extract_candidates(text)
    if not cands:
        return 'INVALID'
    votes = {str(c['decision']).upper() for c in cands}
    legal = {v for v in votes if v in TERNARY}
    if not legal:
        return 'INVALID'
    if len(legal) > 1:
        return 'AMBIGUOUS'
    return legal.pop()


# ---------------------------------------------------------------------------
# Asymmetric gold standard — pure function over EVIDENCE FACTS ONLY.
# patch_correct / merge_acceptable must NEVER be passed here.
# ---------------------------------------------------------------------------

def gold_decision(*, evidence_integrity, decisive_failure, sufficient_success):
    """Map evidence facts to the ternary gold label.

    Order matters and encodes asymmetry: an applicable decisive failure
    rejects even when coverage is incomplete; acceptance demands intact AND
    sufficient success; everything else abstains.
    """
    if decisive_failure:
        return 'REJECT'
    if evidence_integrity and sufficient_success:
        return 'ACCEPT'
    return 'NEED_EVIDENCE'


def derive_evidence_facts(*, linked, fresh, complete,
                          executed_failure_count, executed_check_count):
    """Derive the three gold facts from trustworthy, applicability-checked
    evidence.

    `executed_*` counts must come from the SIGNED artifact's normalized run
    summary only (never from hidden labels). A failure counts as decisive
    only when the evidence is APPLICABLE to the target patch (linked +
    fresh): failures in someone else's artifact (wrong_patch) or in a stale
    tree are not grounds to reject the patch under review.
    """
    applicable = bool(linked and fresh)
    decisive_failure = applicable and executed_failure_count > 0
    sufficient_success = (
        applicable and bool(complete)
        and executed_check_count > 0 and executed_failure_count == 0
    )
    evidence_integrity = bool(linked and fresh and complete)
    return {
        'linked': bool(linked),
        'fresh': bool(fresh),
        'complete': bool(complete),
        'evidence_integrity': evidence_integrity,
        'decisive_failure': decisive_failure,
        'sufficient_success': sufficient_success,
    }


def _executed_counts(rec):
    """Executed acceptance/regression counts from a signed artifact record.

    Uses the record's own normalized summary (actual run outcomes), not any
    declared/attestation counts. fail_to_pass / pass_to_pass_scoped maps,
    when present, are authoritative per-test outcomes; fall back to summary
    ids for fixtures that only carry the aggregated summary.

    A p2p check whose literal status is FAILED but which the record classifies
    in `p2p_preexisting_bad_ids` was already bad at the base commit (an
    environment/pre-existing failure), NOT a regression introduced by THIS
    patch. It is excluded from the executed-failure count, matching the real
    server adjudication (`bad = f2p_failed + p2p_regressed`, server.py) and the
    tier-A view ("tests already failing at base commit ... not counted as
    regressions"). Counting it would falsely REJECT an empirically GOOD patch
    (e.g. sympy-13091 glm has one pre-existing bad p2p and zero regressions).
    """
    preexisting = set((rec.get('summary') or {})
                      .get('p2p_preexisting_bad_ids') or [])
    failure = 0
    executed = 0
    f2p = rec.get('fail_to_pass') or {}
    if isinstance(f2p, dict) and f2p:
        executed += len(f2p)
        failure += sum(1 for v in f2p.values() if str(v).upper() == 'FAILED')
    p2p = rec.get('pass_to_pass_scoped') or {}
    if isinstance(p2p, dict) and p2p:
        executed += len(p2p)
        failure += sum(1 for k, v in p2p.items()
                       if str(v).upper() == 'FAILED' and k not in preexisting)
    if executed == 0:  # normalized-summary fallback
        summ = rec.get('summary') or {}
        failed_ids = summ.get('f2p_failed_ids') or []
        regressed = summ.get('p2p_regressed_ids') or []
        failure = len(failed_ids) + len(regressed)
        executed = int(summ.get('f2p_total') or 0) + int(summ.get('p2p_total') or 0)
    return failure, executed


def build_gold_row(fx, rec):
    """Build one deterministic gold row from a fixture manifest line and its
    AUTHENTIC signed artifact record."""
    exp = fx['expected']
    linked, fresh, complete = bool(exp['linked']), bool(exp['fresh']), bool(exp['complete'])
    failure, executed = _executed_counts(rec)
    facts = derive_evidence_facts(
        linked=linked, fresh=fresh, complete=complete,
        executed_failure_count=failure, executed_check_count=executed)
    gold = gold_decision(**{k: facts[k] for k in
                            ('evidence_integrity', 'decisive_failure',
                             'sufficient_success')})
    basis = []
    if not linked:
        basis.append('artifact not linked to target patch: failure evidence '
                     'is not applicable')
    if not fresh:
        basis.append('artifact ran on a stale tree: outcomes are not '
                     'applicable to the current patch')
    if not complete:
        basis.append('declared check set not fully executed: success cannot '
                     'be established')
    if facts['decisive_failure']:
        basis.append(f'{failure} executed declared check(s) failed on linked, '
                     f'fresh evidence -> decisive failure (completeness not '
                     f'required to reject)')
    if facts['sufficient_success']:
        basis.append(f'{executed} declared checks executed on linked, fresh, '
                     f'complete evidence with no failure -> sufficient success')
    if gold == 'NEED_EVIDENCE' and not basis:
        basis.append('no decisive failure and insufficient success evidence')
    return {
        'id': fx['id'],
        'scenario': fx['scenario'],
        'patch_correct': bool(fx.get('merge_acceptable')),  # audit column only
        'served_artifact_id': fx['served_artifact_id'],
        'evidence_integrity': facts['evidence_integrity'],
        'decisive_failure': facts['decisive_failure'],
        'sufficient_success': facts['sufficient_success'],
        'linked': facts['linked'], 'fresh': facts['fresh'],
        'complete': facts['complete'],
        'executed_failure_count': failure,
        'executed_check_count': executed,
        'gold': gold,
        'basis': ' | '.join(basis),
    }


def read_jsonl(path):
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def build_gold_rows(fixture_paths, store_root):
    """Load fixture manifests (phase-2 + phase-3) and derive one gold row per
    fixture. Every served artifact MUST verify under the store HMAC; an
    inauthentic record aborts generation rather than silently labeling it.
    """
    store = ArtifactStore(store_root)
    rows, seen = [], set()
    for p in fixture_paths:
        for fx in read_jsonl(p):
            key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
            if key in seen:
                continue
            seen.add(key)
            got = store.get(fx['served_artifact_id'])
            if got is None:
                raise SystemExit(f"gold: missing artifact "
                                 f"{fx['served_artifact_id']} for {fx['id']}")
            rec, authentic = got
            if not authentic:
                raise SystemExit(f"gold: refusing to derive label from "
                                 f"inauthentic artifact {fx['served_artifact_id']}")
            row = build_gold_row(fx, rec)
            # cross-check against an optional builder-provided expectation,
            # but never read it as an input
            exp_dec = fx.get('expected', {}).get('decisive_failure')
            if exp_dec is not None and bool(exp_dec) != row['decisive_failure']:
                raise SystemExit(
                    f"gold: derived decisive_failure={row['decisive_failure']} "
                    f"disagrees with manifest cross-check for {fx['id']}")
            rows.append(row)
    rows.sort(key=lambda r: (r['scenario'], r['id'], r['served_artifact_id']))
    return rows


def render_gold(rows):
    return ''.join(canonical_dumps(r) + '\n' for r in rows)


def write_gold(rows, out_path):
    Path(out_path).write_text(render_gold(rows), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixtures', required=True,
                    help='comma-separated fixture manifests (phase2,phase3)')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--out', default='evidence_store/phase3_gold.jsonl')
    a = ap.parse_args()
    paths = [p for p in a.fixtures.split(',') if p]
    rows = build_gold_rows(paths, a.store)
    write_gold(rows, a.out)
    for r in rows:
        print(f"{r['scenario']:<24} {r['id']:<55} -> {r['gold']:<14} "
              f"(df={int(r['decisive_failure'])},ss={int(r['sufficient_success'])},"
              f"fail={r['executed_failure_count']},n={r['executed_check_count']})")
    print(f'wrote {len(rows)} gold rows -> {a.out}')


if __name__ == '__main__':
    main()
