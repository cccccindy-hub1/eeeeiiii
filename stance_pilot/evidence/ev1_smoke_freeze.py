"""Freeze the two GPT-4.1-mini API-smoke cells (offline, no API call).

User-authorised scope (2026-10-21): exactly 2 cells, hard spend cap $0.10,
compatibility-only (correctness is NOT a pass criterion). The two cells are
chosen MECHANICALLY from the frozen Wave-2.1 corrected results, before any
GPT output exists:

  * Static  T2A-T        : a zero-tool static-evidence cell covering strict
                           JSON-schema decision rendering and ternary parse.
                           Pick the lexicographically first T2A-T cell key
                           (deterministic, not outcome-driven).
  * Active  T3D-Escalate : a cell that demonstrably exercised the FULL tool
                           loop AND the reason gate on the baseline. Pick the
                           Escalate cell with the most granted escalations,
                           then most tool calls, then key (so the live API is
                           stressed on parallel/multi-turn tools and the
                           400 missing-reason -> granted escalation audit).

Writes evidence_store_ev1/ev1_smoke_cells.json. The baseline facts recorded
there are CONTEXT ONLY, not expectations the new model must reproduce.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pilot import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
W21 = ROOT / 'evidence_store_w21' / 'wave21_corrected_all110_results.jsonl'
OUT = ROOT / 'evidence_store_ev1' / 'ev1_smoke_cells.json'

STATIC_COND = 'T2A-T'
ACTIVE_COND = 'T3D-Escalate'


def baseline_fact(r):
    return {
        'cell_key': r['cell'], 'scenario': r.get('scenario'),
        'id': r.get('id'), 'instance_id': r.get('instance_id'),
        'served_artifact_id': r.get('served_artifact_id'),
        'condition': r['condition'],
        'baseline_model': r.get('model'),
        'baseline_decision_parsed': r.get('parsed'),
        'baseline_tool_calls': r.get('tool_calls'),
        'baseline_model_calls': r.get('model_calls'),
        'baseline_escalation_granted': r.get('escalation_granted'),
        'baseline_tokens_in': r.get('tokens_in'),
        'baseline_tokens_out': r.get('tokens_out'),
        'note': 'frozen deepseek-flash wave2.1 behaviour for context only; '
                'NOT a target the smoke model must match',
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', default=str(W21))
    ap.add_argument('--out', default=str(OUT))
    a = ap.parse_args()
    rows = [r for r in read_jsonl(a.baseline)
            if not r.get('error') and not r.get('mock')]

    static = sorted((r for r in rows if r['condition'] == STATIC_COND),
                    key=lambda r: r['cell'])[0]
    active = sorted(
        (r for r in rows if r['condition'] == ACTIVE_COND),
        key=lambda r: (-len(r.get('escalation_granted') or []),
                       -(r.get('tool_calls') or 0), r['cell']))[0]

    out = {
        'artifact': 'groundedreview_ev1_smoke_cell_freeze',
        'authorisation': 'user 2026-10-21: gpt-4.1-mini 2-cell real API smoke, '
                         'hard cap $0.10, compatibility-only',
        'model_profile': 'openai_gpt41_mini',
        'model': 'gpt-4.1-mini',
        'hard_spend_cap_usd': 0.10,
        'selection_rule': {
            STATIC_COND: 'lexicographically first T2A-T cell key (no '
                         'outcome-based selection)',
            ACTIVE_COND: 'max granted escalations, then max tool calls, then '
                         'cell key; guarantees the full tool loop and the '
                         'reason gate are exercised on the real API',
        },
        'static_cell': baseline_fact(static),
        'active_cell': baseline_fact(active),
        'compatibility_checkpoints': [
            'static: strict JSON-schema final call accepted; decision '
            'parses into the frozen ternary keys (ACCEPT/REJECT/'
            'NEED_EVIDENCE + reason + evidence_mismatch)',
            'active: multi-turn native tool calls work; the reason-gated '
            'escalation endpoint returns 400 without reason and 200 with '
            'reason; final decision JSON parses',
            'record: model id served, every wire call kwargs, any 400 '
            'response_format downgrade chain, tokens, latency, USD',
            'pass is protocol-level: a parseable decision with the tool '
            'loop intact = pass regardless of which decision is chosen'],
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    print('static:', static['cell'])
    print('active:', active['cell'],
          f"granted={active.get('escalation_granted')} "
          f"tools={active.get('tool_calls')}")
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
