"""Wave-2 Task 6: freeze the dual-channel gold for ALL fixtures (9 Wave-1 +
the new Wave-2 mirrors) and audit decisive-failure visibility per condition.

Outputs (frozen, deterministic; never overwritten by pilots):
  evidence_store/wave2_gold.jsonl
      one row per fixture: oracle gold + five condition golds + the full
      projected visibility matrix + the channels (O acceptance / P symptom)
      that carry the oracle decisive failure.
  evidence_store/wave2_decisive_visibility.json
      every fixture whose oracle gold is REJECT, crossed with the five
      conditions: O/P visibility, condition gold, whether the oracle decisive
      channel is accessible in the condition, and blameworthy_abstain
      (abstaining / answering NEED in a cell where the decisive failure is
      accessible is culpable over-abstention; NEED where the decisive channel
      is institutionally withheld is NOT blameworthy).

The gold rules live in evidence.gold_w2; this module only derives and freezes.
No model outputs or scenario labels are read as inputs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from evidence.gold_w2 import (GOLD_VERSION, W2_CONDITIONS, derive_rows,
                              render_rows, rows_sha256, _oracle_inputs_from_facts)
from evidence.schemas import canonical_dumps
from evidence.store import ArtifactStore
from evidence.visibility import load_fixture_facts, project_surface


def read_jsonl(path):
    return [json.loads(line)
            for line in Path(path).read_text(encoding='utf-8').splitlines()
            if line.strip()]


def load_all_fixtures(store_root):
    root = Path(store_root)
    fixtures = []
    for name in ('phase2_fixtures.jsonl', 'phase3_fixtures.jsonl',
                 'wave2_fixtures.jsonl'):
        fixtures.extend(read_jsonl(root / name))
    return fixtures


def decisive_channels(oracle_inputs):
    """Channels that independently force the oracle REJECT:
    O = an executed acceptance failure on linked, fresh evidence;
    P = the issue symptom still reproduces post-patch."""
    ch = []
    if (oracle_inputs['linked'] and oracle_inputs['fresh']
            and oracle_inputs['acceptance_failure']):
        ch.append('O')
    if oracle_inputs['symptom_persists']:
        ch.append('P')
    return ch


def build_gold_rows(store, fixtures):
    """derive_rows + embedded visibility matrix + decisive-channel audit
    columns. Derivation is delegated to gold_w2; rows stay deterministic.

    Note: mirror scenarios can share the same reviewer id (e.g. the same
    candidate is served as both w2_decisive_bad and w2_stale_bad under
    different artifact ids), so the oracle fact bundle is keyed by the unique
    served_artifact_id — never by the reviewer id.
    """
    derived = derive_rows(store, fixtures, W2_CONDITIONS)
    facts_by_aid = {fx['served_artifact_id']: load_fixture_facts(store, fx)
                    for fx in fixtures}
    out = []
    for r in derived:
        facts = facts_by_aid[r['served_artifact_id']]
        matrix = {c: project_surface(c, facts) for c in W2_CONDITIONS}
        oi = _oracle_inputs_from_facts(facts)
        rr = copy.deepcopy(r)
        rr['visibility_matrix'] = matrix
        rr['decisive_failure'] = (r['oracle_gold'] == 'REJECT')
        rr['decisive_evidence_channels'] = decisive_channels(oi)
        out.append(rr)
    return out


def _cell_audit(row, surface, channel):
    """One decisive-fixture x condition cell."""
    cond = surface['condition']
    p = surface['symptom']
    o = surface['acceptance_outcomes']
    p_pol = p.get('polarity')
    if p_pol is None and p.get('polarity_exists_but_hidden'):
        p_pol_display = p['polarity_exists_but_hidden'] + ' (hidden)'
    else:
        p_pol_display = p_pol
    o_accessible = o['status'] in ('obtainable', 'obtainable_with_reason',
                                   'presented')
    p_accessible = bool(p.get('observable'))
    if channel == 'O':
        accessible = o_accessible
        channel_note = (
            'acceptance outcomes ' + o['status']
            + ('; linked/fresh adjudicated in this condition'
               if surface['linkage']['value'] is True
                  and surface['freshness']['value'] is True
               else '; linkage/freshness are not adjudicated in this condition'
                  if surface['linkage']['value'] is None
               else '; adjudicated linkage/freshness do not both hold'))
    elif channel == 'P':
        accessible = p_accessible
        channel_note = (
            'symptom ' + ('observable' if p_accessible else 'not rendered')
            + (' via symptom-only strict verdict'
               if p.get('symptom_only_consistency_verdict')
               else (' via log' if p.get('log_available')
                     else ' in the static diagnostic block'
                     if p.get('rendered_in_static_block') else '')))
    else:
        # both channels decisive (union)
        accessible = o_accessible or p_accessible
        channel_note = f'O={o["status"]}; P observable={p_accessible}'
    return {
        'condition': cond,
        'evidence_tier': surface['evidence_tier'],
        'policy': surface['policy'],
        'condition_gold': row['condition_gold'][cond],
        'P': {
            'observable': p_accessible,
            'log_available': bool(p.get('log_available')),
            'rendered_in_static_block': bool(
                p.get('rendered_in_static_block')),
            'symptom_only_consistency_verdict': bool(
                p.get('symptom_only_consistency_verdict')),
            'polarity_shown': p_pol_display,
        },
        'O': {
            'status': o['status'],
            'requires_escalation': bool(o.get('requires_escalation')),
            'failure_count': o.get('failure_count'),
            'linkage_adjudicated': surface['linkage']['value'],
            'freshness_adjudicated': surface['freshness']['value'],
        },
        'oracle_decisive_channel': channel,
        'decisive_channel_accessible': accessible,
        # Answering NEED_EVIDENCE in this cell is blameworthy iff the channel
        # carrying the oracle decisive failure is accessible there.
        'blameworthy_abstain': accessible,
        'basis': row['condition_basis'][cond] + ' || ' + channel_note,
    }


def build_decisive_audit(store, fixtures, gold_rows):
    fx_by_aid = {fx['served_artifact_id']: fx for fx in fixtures}
    out_fixtures = []
    for r in gold_rows:
        if not r['decisive_failure']:
            continue
        channels = ''.join(r['decisive_evidence_channels'])  # 'O' / 'P' / 'OP'
        cells = [_cell_audit(r, r['visibility_matrix'][c], channels)
                 for c in W2_CONDITIONS]
        out_fixtures.append({
            'id': r['id'],
            'scenario': r['scenario'],
            'wave': r['wave'],
            'instance_id': fx_by_aid[r['served_artifact_id']]['instance_id'],
            'served_artifact_id': r['served_artifact_id'],
            'oracle_gold': r['oracle_gold'],
            'oracle_basis': r['oracle_basis'],
            'symptom_polarity': r['facts']['symptom_polarity'],
            'oracle_decisive_channels': r['decisive_evidence_channels'],
            'cells': cells,
        })
    out_fixtures.sort(key=lambda f: (f['wave'], f['scenario'], f['id']))
    blame = [(f['scenario'], c['condition'])
             for f in out_fixtures for c in f['cells']
             if c['blameworthy_abstain']]
    return {
        'version': GOLD_VERSION,
        'definition': {
            'decisive_failure': "oracle_gold == 'REJECT' (an executed "
                'acceptance failure on linked/fresh evidence and/or the issue '
                'symptom persisting post-patch)',
            'O': 'acceptance channel: per-test f2p/p2p outcomes',
            'P': 'diagnostic channel: issue-derived symptom probe polarity',
            'decisive_channel_accessible': 'the channel that forces the '
                'oracle REJECT is rendered / adjudicated / obtainable '
                '(escalation with reason counts) in this condition',
            'blameworthy_abstain': 'a NEED_EVIDENCE answer in this cell '
                'would be culpable over-abstention because decisive evidence '
                'is accessible; when the decisive channel is withheld '
                '(not_visible/hard_blocked/hidden), NEED is NOT blameworthy',
        },
        'n_decisive_fixtures': len(out_fixtures),
        'blameworthy_cells': [
            {'scenario': s, 'condition': c} for s, c in blame],
        'fixtures': out_fixtures,
    }


def freeze(store_root):
    """Deterministically derive the frozen gold text and decisive audit."""
    store = ArtifactStore(str(store_root))
    fixtures = load_all_fixtures(store_root)
    rows = build_gold_rows(store, fixtures)
    gold_text = render_rows(rows)
    gh = hashlib.sha256(gold_text.encode('utf-8')).hexdigest()
    audit = build_decisive_audit(store, fixtures, rows)
    audit['gold_sha256'] = gh
    audit_text = canonical_dumps(audit) + '\n'
    return rows, gold_text, gh, audit, audit_text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--out', default='evidence_store/wave2_gold.jsonl')
    ap.add_argument('--decisive-out',
                    default='evidence_store/wave2_decisive_visibility.json')
    ap.add_argument('--check', action='store_true',
                    help='re-derive and require byte-identical files')
    a = ap.parse_args()
    rows, want_gold, gh, want_audit, want_audit_text = freeze(a.store)
    if a.check:
        errs = []
        if Path(a.out).read_text(encoding='utf-8') != want_gold:
            errs.append('wave2_gold.jsonl is not byte-identical to a fresh '
                        'deterministic derivation')
        if Path(a.decisive_out).read_text(encoding='utf-8') \
                != want_audit_text:
            errs.append('wave2_decisive_visibility.json differs from a fresh '
                        'deterministic derivation')
        if errs:
            for e in errs:
                print('FREEZE CHECK FAILED:', e)
            raise SystemExit(1)
        print(f'freeze check OK: {a.out} (n={len(rows)}) and '
              f'{a.decisive_out} are deterministic; gold sha256={gh}')
        return
    Path(a.out).write_text(want_gold, encoding='utf-8')
    Path(a.decisive_out).write_text(want_audit_text, encoding='utf-8')
    ah = hashlib.sha256(want_audit_text.encode('utf-8')).hexdigest()
    print(f'froze {len(rows)} gold rows -> {a.out}')
    print(f'wave2_gold.jsonl sha256={gh}')
    print(f'wave2_decisive_visibility.json sha256={ah} '
          f'({want_audit["n_decisive_fixtures"]} decisive fixtures, '
          f'{len(want_audit["blameworthy_cells"])} blameworthy cells)')


if __name__ == '__main__':
    main()
