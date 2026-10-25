"""EAL per-layer construct-validity / label-leakage audit. ZERO API, read-only.

Runs entirely against the RENDERED BYTES in evidence_store_eal/layers/ plus
the frozen CEE bundle bytes; it never trusts renderer in-memory state.

Four questions per layer:

  Q1 LITERAL LEAK        gold/class/scenario/decisive tokens in the served
                         evidence body (head excluded; issue/patch natural
                         language reported separately)?
  Q2 VERDICT ABSENCE     do RAW/STRUCTURED bodies avoid pre-adjudicated
                         verdicts (linked/fresh/complete/symptom yes-no,
                         "verdict"/"adjudicated" phrases, match columns)?
                         ADJUDICATED is expected to contain them by design.
  Q3 MECHANICAL GOLD     can the frozen gold be mechanically recomputed by
                         parsing ONLY that layer's served text (independent
                         text parsers per layer), and how many grounding
                         comparisons does that require?
  Q4 SUFFICIENCY         are all five gold operands supported by auditable
                         material inside that same layer (information
                         equivalence; no mere deletion)?

Writes: evidence_store_eal/eal_construct_audit.json

    uv run --python 3.13 -m evidence.eal_audit
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from evidence import eal_protocol as eal
from evidence.cee_leakage_audit_v11 import parse_rendered_fields as cee_parse
from evidence.gold_w2 import oracle_gold

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
LAYER_DIR = EAL_DIR / 'layers'

DIRECT_LABEL_TOKENS = [
    'oracle_gold', 'cee_gold', 'merge_acceptable', 'patch_correct',
    'label_class', 'evidence_class', 'decisive_failure',
    'sufficient_success', 'symptom_polarity', 'sufficient_positive',
    'decisive_negative', '"scenario"', 'ground truth', 'gold label',
    'the answer is', 'answer: accept', 'answer: reject',
    'you should accept', 'you should reject', 'you must reject',
    'you must accept', 'this patch is correct', 'this patch is incorrect',
]
# Compound internal scenario identifiers that the frozen neutralizer must
# keep out of every served body (these tokens cannot occur in normal record
# field names). Bare generic words (stale/valid/bad/...) are reported
# informationally only — e.g. the frozen field p2p_preexisting_bad_ids
# legitimately contains 'bad'.
SCENARIO_VOCAB = ['wrong_patch', 'stale_persists', 'stale_bad',
                  'incomplete_decisive', 'wrong_patch_good',
                  'incomplete_good', 'incomplete_decisive_bad',
                  'w2_decisive_bad', 'w2_incomplete_good', 'w2_stale',
                  'w2_stale_bad', 'w2_stale_persists', 'w2_valid',
                  'wrong patch']
GENERIC_WORDS = ['stale', 'valid', 'incomplete', 'contradictory',
                 'decisive', 'good', 'bad', 'sufficient', 'insufficient']
# Verdict forms that constitute pre-adjudication. Scoped to the EVIDENCE
# BODY (the head legitimately explains linked/fresh/complete in prose).
VERDICT_PATTERNS = [
    (re.compile(r'\blinked\b[^\n]{0,45}:\s*(yes|no|n/a)\b', re.I),
     'linked yes/no verdict'),
    (re.compile(r'\bfresh\b[^\n]{0,45}:\s*(yes|no|n/a)\b', re.I),
     'fresh yes/no verdict'),
    (re.compile(r'fully executed[^\n]{0,20}:\s*(yes|no|n/a)\b', re.I),
     'complete yes/no verdict'),
    (re.compile(r'present (before|after) patch\s*:\s*(yes|no|n/a)\b', re.I),
     'probe binary verdict'),
    (re.compile(r'reproduces after patch\s*:\s*(yes|no|n/a)\b', re.I),
     'probe binary verdict'),
    (re.compile(r'symptom[_\s]+persists\s*[:=]\s*(true|false|yes|no)\b',
                re.I), 'symptom_persists verdict'),
    (re.compile(r'integrity verdicts?', re.I), 'integrity verdict heading'),
    (re.compile(r'\balready adjudicated\b', re.I), 'adjudicated phrase'),
    (re.compile(r'^\s*\|[^\n]*\b(matches?|verdict|linked\?|fresh\?)\b[^\n]*\|',
                re.M), 'verdict table column'),
]

BODY_MARKERS = {
    'raw': 'RAW EVIDENCE PACKAGE',
    'structured': 'STRUCTURED EVIDENCE PACKAGE',
    'adjudicated': 'FIXED EVIDENCE BUNDLE',
}
# In raw/structured bodies everything up to the first evidence section is
# the original issue/patch/author text.
EVIDENCE_START_RE = {
    'raw': re.compile(r'\n=== TARGET PATCH UNDER REVIEW ==='),
    'structured': re.compile(r'\n=== TABLE 1 '),
    'adjudicated': re.compile(r'TEST ARTIFACT'),
}


def split_head_body(text: str, layer: str):
    m = BODY_MARKERS[layer]
    i = text.index(m)
    return text[:i], text[i:]


def evidence_region_span(body: str, layer: str):
    m = EVIDENCE_START_RE[layer].search(body)
    return (m.start(), len(body)) if m else (0, len(body))


def scan_leakage(body: str, layer: str, scenario: str):
    lo, hi = evidence_region_span(body, layer)
    low = body.lower()
    natural, injected = [], []
    contexts = {}
    tokens = DIRECT_LABEL_TOKENS + [scenario.lower()]
    for tok in tokens:
        start = 0
        while True:
            k = low.find(tok.lower(), start)
            if k < 0:
                break
            (injected if lo <= k < hi else natural).append(tok)
            contexts.setdefault(tok, low[max(0, k - 50):k + len(tok) + 50])
            start = k + len(tok)
    vocab_hits_natural, vocab_hits_injected = [], []
    for w in SCENARIO_VOCAB:
        for m in re.finditer(re.escape(w), low):
            k = m.start()
            (vocab_hits_injected if lo <= k < hi
             else vocab_hits_natural).append(w)
    generic_injected = []
    for w in GENERIC_WORDS:
        for m in re.finditer(r'\b' + re.escape(w) + r'\b', low):
            if m.start() >= lo:
                generic_injected.append(w)
    return {
        'direct_tokens_in_issue_patch_region': sorted(set(natural)),
        'direct_tokens_in_injected_evidence': sorted(set(injected)),
        'scenario_vocab_in_issue_patch_region': sorted(set(vocab_hits_natural)),
        'scenario_vocab_in_injected_evidence':
            sorted(set(vocab_hits_injected)),
        'generic_words_in_injected_evidence_informational_only':
            sorted(set(generic_injected)),
        'contexts': contexts,
    }


def scan_verdicts(body: str, layer: str):
    lo, _ = evidence_region_span(body, layer)
    hits = []
    for rx, name in VERDICT_PATTERNS:
        for m in rx.finditer(body):
            if m.start() >= lo:
                hits.append({'pattern': name,
                             'text': m.group(0).strip()[:120]})
    return hits


# ---------------------------------------------------------------------------
# Independent TEXT-ONLY parsers
# ---------------------------------------------------------------------------

_JSON_SEC_RE = re.compile(r'--- (?:RUN RECORD|ATTESTATION RECORD) ---\n')


def _extract_json_sections(body: str):
    out = {}
    for m in _JSON_SEC_RE.finditer(body):
        # JSON ends at the next '\n\n===' marker.
        rest = body[m.end():]
        end = rest.find('\n\n===')
        chunk = rest[:end if end >= 0 else len(rest)].strip()
        obj = json.loads(chunk)
        out['RUN RECORD' if 'fail_to_pass' in obj or 'run_tree' in obj
            else 'ATTESTATION'] = obj
    return out


def _parse_probe_exits_raw(body: str):
    secs = re.split(r'###\s*(BASELINE \(pre-patch\)|POST candidate patch)',
                    body)
    # body after the split marker keeps the section text
    exits = {}
    labels = [s for s in secs if 'BASELINE' in s or 'POST' in s]
    texts = [secs[i + 1] for i, s in enumerate(secs)
             if 'BASELINE' in s or 'POST' in s]
    for lab, txt in zip(labels, texts):
        ex = re.search(r'\(exit\s+(-?\d+)\)', txt)
        key = 'pre' if 'BASELINE' in lab else 'post'
        exits[key] = int(ex.group(1)) if ex else None
    return exits


def _table_rows(body: str, title: str):
    i = body.index(title)
    seg = body[i:].split('\n\n', 1)[0]
    lines = seg.splitlines()
    # Locate the first pipe-delimited line (the header), tolerating a
    # heading glued to it or a leading blank line.
    hdr_idx = next(k for k, ln in enumerate(lines) if ' | ' in ln)
    header = [c.strip() for c in lines[hdr_idx].split(' | ')]
    rows = []
    for ln in lines[hdr_idx + 2:]:
        cells = [c.strip() for c in ln.split(' | ')]
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return header, rows


def _ids(cell: str):
    return [x.strip() for x in cell.split(',') if x.strip() and x != '(empty)']


def parse_structured_layer(body: str):
    _, idrows = _table_rows(body, 'TABLE 1')
    _, treerows = _table_rows(body, 'TABLE 2')
    _, declrows = _table_rows(body, 'TABLE 3')
    _, joinrows = _table_rows(body, 'TABLE 4')
    idm = {r['field']: r for r in idrows}
    treem = {r['item']: r['value'] for r in treerows}
    declm = {r['set']: _ids(r['ids']) for r in declrows}
    target_base = idm['base_commit']['TARGET under review']
    record_base = idm['base_commit']['value inside SIGNED RUN RECORD']
    target_patch = idm['patch_sha256']['TARGET under review']
    record_patch = idm['patch_sha256']['value inside SIGNED RUN RECORD']
    rec_tree = treem['git tree of the signed run']
    exp_tree = treem['expected canonical tree declared in the attestation']
    att_present = exp_tree != '(no attestation)'
    decl = set(declm.get('declared FAIL_TO_PASS', [])) \
        | set(declm.get('declared scoped PASS_TO_PASS', []))
    executed = set()
    f2p_fail = 0
    regressions = 0
    for r in joinrows:
        in_f2p = r['f2p_post_status'] != '-'
        in_p2p = r['p2p_post_status'] != '-'
        if in_f2p or in_p2p:
            executed.add(r['test_id'])
        if in_f2p and r['f2p_post_status'].upper() == 'FAILED':
            f2p_fail += 1
        if in_p2p and r['p2p_post_status'].upper() == 'FAILED' \
                and r['p2p_base_status'].upper() != 'FAILED':
            regressions += 1
    failure = f2p_fail + regressions
    executed_n = sum(r['f2p_post_status'] != '-' for r in joinrows) \
        + sum(r['p2p_post_status'] != '-' for r in joinrows)
    pre_ex = re.search(r'\[pre-patch BASELINE\].*?exit_code:\s*(-?\d+|None)',
                       body, re.S)
    post_ex = re.search(r'\[post-patch CANDIDATE\].*?exit_code:\s*(-?\d+|None)',
                        body, re.S)
    exits = {
        'pre': int(pre_ex.group(1)) if pre_ex and pre_ex.group(1) != 'None'
        else None,
        'post': int(post_ex.group(1)) if post_ex
        and post_ex.group(1) != 'None' else None,
    }
    linked = target_base == record_base and target_patch == record_patch
    fresh = att_present and record_base == target_base \
        and rec_tree == exp_tree
    complete = att_present and all(d in executed for d in decl)
    acceptance_failure = failure > 0 if executed_n > 0 else None
    acceptance_success = (failure == 0) if executed_n > 0 else None
    persists = None
    if exits['pre'] is not None and exits['post'] is not None:
        persists = exits['pre'] != 0 and exits['post'] != 0
    return {
        'values': {
            'linked': linked, 'fresh': fresh, 'complete': complete,
            'acceptance_failure': acceptance_failure,
            'acceptance_success': acceptance_success,
            'symptom_persists': persists,
        },
        'grounding_steps': {
            'identity_field_comparisons': 2,
            'run_tree_comparisons': 1,
            'declared_checks_membership_tests': len(decl),
            'per_test_status_classifications': len(joinrows),
            'probe_exit_codes_to_read': 2,
        },
        'attestation_present_in_text': att_present,
        'source': 'structured_tables',
    }


def parse_raw_layer_v2(body: str):
    """Raw derivation: TARGET block + JSON record/attestation + probe exits."""
    secs = _extract_json_sections(body)
    rec, att = secs['RUN RECORD'], secs.get('ATTESTATION')
    tb = body[body.index('=== TARGET PATCH UNDER REVIEW ==='):
              body.index('=== REPOSITORY ATTESTATION')]
    t_base = re.search(r'base_commit:\s*(\w{40})', tb).group(1)
    t_patch = re.search(r'patch_sha256:\s*(\w{64})', tb).group(1)
    exits = _parse_probe_exits_raw(body)
    linked = rec['base_commit'] == t_base and rec['patch_sha256'] == t_patch
    fresh = complete = None
    declared = set()
    if att is not None:
        fresh = (rec['base_commit'] == t_base
                 and rec['run_tree'] == att['expected_run_tree'])
        executed = set(rec.get('fail_to_pass') or {}) \
            | set(rec.get('pass_to_pass_scoped') or {})
        declared = set(att['declared_fail_to_pass']) \
            | set(att['declared_p2p_scoped'])
        complete = all(d in executed for d in declared)
    failure = 0
    executed_n = 0
    f2p = rec.get('fail_to_pass') or {}
    p2p = rec.get('pass_to_pass_scoped') or {}
    base = rec.get('pass_to_pass_baseline') or {}
    preexisting = set((rec.get('summary') or {})
                      .get('p2p_preexisting_bad_ids') or [])
    executed_n += len(f2p) + len(p2p)
    failure += sum(1 for v in f2p.values() if str(v).upper() == 'FAILED')
    failure += sum(1 for k, v in p2p.items()
                   if str(v).upper() == 'FAILED' and k not in preexisting)
    acceptance_failure = failure > 0 if executed_n > 0 else None
    acceptance_success = failure == 0 if executed_n > 0 else None
    persists = None
    if exits.get('pre') is not None and exits.get('post') is not None:
        persists = exits['pre'] != 0 and exits['post'] != 0
    return {
        'values': {
            'linked': linked, 'fresh': fresh, 'complete': complete,
            'acceptance_failure': acceptance_failure,
            'acceptance_success': acceptance_success,
            'symptom_persists': persists},
        'grounding_steps': {
            'json_blocks_to_parse': 2 if att is not None else 1,
            'identity_field_comparisons': 2,
            'run_tree_comparisons': 1,
            'declared_checks_membership_tests': len(declared),
            'per_test_statuses_in_record_maps': len(f2p) + len(p2p),
            'runner_logs_attached_to_read': 4,
            'probe_sections_to_read': 2,
        },
        'source': 'raw_json_and_logs',
    }


def parse_adjudicated_layer(body: str):
    rf = cee_parse(body)
    return {
        'values': {
            'linked': rf['linked'], 'fresh': rf['fresh'],
            'complete': rf['complete'],
            'acceptance_failure':
                rf['acceptance_failure_from_rendered_block'],
            'acceptance_success':
                rf['acceptance_success_from_rendered_block'],
            'symptom_persists': rf['symptom_persists']},
        'grounding_steps': {
            'identity_field_comparisons': 0,
            'run_tree_comparisons': 0,
            'declared_checks_membership_tests': 0,
            'printed_adjudication_booleans_to_read': 6,
            'rule_applications': 1,
        },
        'source': 'printed_booleans',
    }


def parse_raw_layer(body: str):
    return parse_raw_layer_v2(body)


PARSERS = {
    'raw': parse_raw_layer_v2,
    'structured': parse_structured_layer,
    'adjudicated': parse_adjudicated_layer,
}


def main():
    manifest = json.loads((EAL_DIR / 'eal_materials_manifest.json')
                          .read_text(encoding='utf-8'))
    per_item = []
    mech_counts = {l: 0 for l in eal.LAYERS}
    verdict_clean = {l: 0 for l in ('raw', 'structured')}
    inject_clean = {l: 0 for l in eal.LAYERS}
    for it in manifest['items']:
        row = {'bundle_id': it['bundle_id'],
               'scenario_internal': it['scenario'],
               'gold': it['cee_gold'],
               'evidence_class_internal': it['evidence_class']}
        for layer in eal.LAYERS:
            text = (LAYER_DIR / f"{it['layers'][layer]['payload_id']}.txt")\
                .read_text(encoding='utf-8')
            head, body = split_head_body(text, layer)
            leak = scan_leakage(body, layer, it['scenario'])
            verdicts = scan_verdicts(body, layer) if layer != 'adjudicated' \
                else [{'pattern': 'printed_booleans_by_design', 'text': '(CEE)'}]
            parsed = PARSERS[layer](body)
            vals = parsed['values']
            if any(v is None for v in vals.values()):
                # Missing operand at this layer: gold not mechanically
                # determined from the served text.
                gold, undetermined = None, [k for k, v in vals.items()
                                            if v is None]
            else:
                gold = oracle_gold(**vals)
                undetermined = []
            mech = gold == it['cee_gold']
            mech_counts[layer] += int(mech)
            if layer in ('raw', 'structured'):
                verdict_clean[layer] += int(len(verdicts) == 0)
            inject_clean[layer] += int(
                not leak['direct_tokens_in_injected_evidence']
                and not leak['scenario_vocab_in_injected_evidence'])
            row[layer] = {
                'body_bytes': len(body.encode('utf-8')),
                'leakage': leak,
                'verdict_hits_in_body': verdicts,
                'mechanically_recomputed_gold_from_served_text': gold,
                'mechanical_matches_oracle': mech,
                'grounding_steps': parsed['grounding_steps'],
                'parser': parsed['source'],
            }
        per_item.append(row)

    layer_summary = {}
    for layer in eal.LAYERS:
        layer_summary[layer] = {
            'n_mechanical_gold_match_from_text': mech_counts[layer],
            'n_injected_evidence_clean_of_labels_and_scenario':
                inject_clean[layer],
            'n_bodies_free_of_pre_adjudicated_verdicts':
                verdict_clean.get(layer, 'n/a (verdicts printed by design)'),
            'construct_reading': {
                'raw': 'gold recoverable ONLY by parsing record/'
                       'attestation JSON, comparing hashes/trees/declared '
                       'sets and reading raw probe exits; no verdict given',
                'structured': 'gold recoverable by executing the side-by-'
                              'side operand comparisons in tables 1/2/4/7; '
                              'no verdict given',
                'adjudicated': 'gold recoverable by reading 6 printed '
                               'booleans and applying the stated rule '
                               '(Task-20 finding reproduced)',
            }[layer],
        }

    report = {
        'document': 'GroundedReview EAL per-layer label-leakage & '
                    'construct-validity audit (offline, zero API)',
        'protocol': eal.EAL_PROTOCOL_VERSION,
        'method': {
            'served_bytes': 'evidence_store_eal/layers/*.txt (rendered '
                            'outputs audited as text; renderer state not '
                            'trusted)',
            'head_body_split': list(BODY_MARKERS.values()),
            'issue_patch_region_excluded_from_injected_scan': True,
            'mechanical_test': 'independent per-layer text parsers recover '
                               'operands and apply the frozen oracle_gold',
        },
        'summary': {'n_items': len(per_item), 'layers': layer_summary},
        'information_equivalence_claim': 'Every adjudication withheld in '
            'raw/structured has all operands present in that same layer: '
            'TARGET vs record hashes (linked), record vs attested run tree '
            '(fresh), declared vs executed sets (complete), post/base '
            'per-test statuses (applicable failure), pre/post probe exits '
            '(persistence). Authenticity is a constant channel premise in '
            'all layers. Withholding therefore changes ABSTRACTION, not '
            'available information.',
        'per_item': per_item,
    }
    out = EAL_DIR / 'eal_construct_audit.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print(f'items={len(per_item)}')
    for layer in eal.LAYERS:
        print(f'  {layer:12s} mechanical_gold='
              f"{mech_counts[layer]}/{len(per_item)} "
              f'label_clean={inject_clean[layer]}/{len(per_item)} '
              f'verdict_free='
              f"{verdict_clean.get(layer, '-')}")
    # Hard construct assertions.
    assert mech_counts['raw'] == len(per_item)
    assert mech_counts['structured'] == len(per_item)
    assert mech_counts['adjudicated'] == len(per_item)
    assert verdict_clean['raw'] == len(per_item)
    assert verdict_clean['structured'] == len(per_item)
    assert all(inject_clean[l] == len(per_item) for l in eal.LAYERS)
    print('all construct assertions PASSED; wrote', out.name)


if __name__ == '__main__':
    main()
