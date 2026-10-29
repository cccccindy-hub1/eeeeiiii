"""EAL Gate 1 — length / evidence-position / truncation / served-byte leak
audit (offline). Runs over the SAME 66 payload files the runner serves.

Outputs:
  evidence_store_eal/eal_gate1_length_position_audit.json

Reports:
  * per-cell bytes/chars and three model-independent token estimators
    (whitespace tokens; chars/4 conservative; anchored chars/3.62);
  * byte offset (absolute + fraction) of every important evidence marker,
    so prompt-order / buried-evidence effects are auditable;
  * truncation risk vs documented context windows and vs completion cap;
  * independent verdict/gold/scenario leak scan of the actually served
    evidence region (raw/structured only).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from evidence import eal_protocol as eal

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
LAYER_DIR = EAL_DIR / 'layers'
MAN_PATH = EAL_DIR / 'eal_materials_manifest.json'

# Conservative context budgets (tokens) used ONLY for risk flags.
CONTEXT_BUDGETS = {'deepseek-flash': 128_000, 'gpt-4.1-mini': 1_000_000}
WARN_TOKENS = 64_000
HARD_TOKENS = 120_000

MARKERS = {
    'raw': ['TARGET UNDER REVIEW', 'REPOSITORY ATTESTATION',
            'ATTESTATION RECORD', 'SIGNED CI RUN RECORD', 'RUN RECORD',
            'LOG: f2p', 'LOG: p2p', 'LOG: p2p_baseline', 'LOG: symptom',
            'PROBE SOURCE', 'log not retained', 'short test summary',
            'exit code'],
    'structured': ['TABLE 1', 'TABLE 2', 'TABLE 3', 'TABLE 4', 'TABLE 5',
                   'TABLE 6', 'TABLE 7', 'pre-patch BASELINE',
                   'post-patch CANDIDATE', 'exit_code', 'FAILED'],
    'adjudicated': ['ACCEPTANCE RESULTS', 'INTEGRITY VERDICTS',
                    'ISSUE-SYMPTOM PROBE', 'linked to THIS patch',
                    'fully executed'],
}

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
BODY_MARK = {'raw': 'RAW EVIDENCE PACKAGE',
             'structured': 'STRUCTURED EVIDENCE PACKAGE',
             'adjudicated': 'FIXED EVIDENCE BUNDLE'}

_WS = re.compile(r"\w+|[^\w\s]")


def token_estimates(text: str):
    chars = len(text)
    ws = len(_WS.findall(text))
    return {
        'whitespace_punct_tokens': ws,
        'tokens_chars_div_4_conservative': chars // 4,
        'tokens_anchored_div_3_62': round(chars / 3.62),
        'chars': chars,
    }


def marker_positions(text: str, layer: str):
    out = {}
    n = len(text)
    for mk in MARKERS[layer]:
        i = text.find(mk)
        if i >= 0:
            out[mk] = {'byte_offset': i,
                       'fraction_of_payload': round(i / max(n, 1), 4)}
    return out


def main():
    man = json.loads(MAN_PATH.read_text(encoding='utf-8'))
    per = []
    leaks_found = []
    for it in man['items']:
        for layer in eal.LAYERS:
            meta = it['layers'][layer]
            p = LAYER_DIR / f"{meta['payload_id']}.txt"
            txt = p.read_text(encoding='utf-8')
            est = token_estimates(txt)
            pos = marker_positions(txt, layer)
            rec = {
                'payload_id': meta['payload_id'],
                'bundle_id': it['bundle_id'], 'layer': layer,
                'bytes': len(txt.encode('utf-8')), **est,
                'evidence_marker_positions': pos,
                'n_distinct_markers_found': len(pos),
            }
            # independent leak scan of the actually served evidence region
            bi = txt.index(BODY_MARK[layer])
            body = txt[bi:]
            if layer != 'adjudicated':
                v = sorted(set(m.group(0).strip()
                               for m in LEAK_VERDICT.finditer(body)))
                mm = sorted(set(m.group(0).strip()
                                for m in LEAK_META.finditer(body)))
                rec['leak_verdict_hits'] = v
                rec['leak_metadata_hits'] = mm
                if v or mm:
                    leaks_found.append({'payload_id': meta['payload_id'],
                                        'verdict': v, 'metadata': mm})
            per.append(rec)

    # Aggregate length stats per layer.
    agg = {}
    for layer in eal.LAYERS:
        cells = [r for r in per if r['layer'] == layer]
        key = 'tokens_anchored_div_3_62'
        vals = sorted(r[key] for r in cells)
        bytesv = sorted(r['bytes'] for r in cells)
        over_warn = [r['payload_id'] for r in cells
                     if r[key] > WARN_TOKENS]
        over_hard = [r['payload_id'] for r in cells
                     if r[key] > HARD_TOKENS]
        fits = {m: max(vals) <= CONTEXT_BUDGETS[m] for m in CONTEXT_BUDGETS}
        agg[layer] = {
            'n': len(cells),
            'bytes_min_median_max': [bytesv[0], bytesv[len(bytesv) // 2],
                                     bytesv[-1]],
            'tokens_min_median_max': [vals[0], vals[len(vals) // 2],
                                      vals[-1]],
            'cells_over_64k_anchor_tokens': over_warn,
            'cells_over_120k_anchor_tokens': over_hard,
            'fits_context_budget': fits,
            'max_context_headroom_tokens':
                {m: CONTEXT_BUDGETS[m] - max(vals) for m in CONTEXT_BUDGETS},
        }

    out = {
        'document': 'EAL Gate-1 served-byte length/position/truncation/leak '
                    'audit',
        'protocol': eal.EAL_PROTOCOL_VERSION,
        'estimators': {
            'whitespace_punct_tokens': 'model-independent lower bound',
            'tokens_chars_div_4_conservative': 'upper-ish bound for English',
            'tokens_anchored_div_3_62': 'anchored to measured CEE '
                                        '2246tok/8119B = 3.615 B/tok',
        },
        'context_budgets_tokens': CONTEXT_BUDGETS,
        'completion_cap_tokens': 4096,
        'per_layer_summary': agg,
        'raw_structured_served_byte_leaks': leaks_found,
        'n_leaks': len(leaks_found),
        'cells': per,
    }
    (EAL_DIR / 'eal_gate1_length_position_audit.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    for layer in eal.LAYERS:
        a = agg[layer]
        print(f"{layer:12s} tok min/med/max={a['tokens_min_median_max']} "
              f"fits={a['fits_context_budget']} "
              f">64k={len(a['cells_over_64k_anchor_tokens'])} "
              f">120k={len(a['cells_over_120k_anchor_tokens'])}")
    print(f"served-byte leak hits (raw/structured): {len(leaks_found)}")


if __name__ == '__main__':
    main()
