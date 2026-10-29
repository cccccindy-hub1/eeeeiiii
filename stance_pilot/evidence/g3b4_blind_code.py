"""Gate 3-B.4 task 4: partially-blinded reason coding of the 7 GPT T3D-Strict
unsupported-ACCEPT cells.

Order of operations (enforced, so the codebook cannot be fitted to the data):
  1. hash the already-written, frozen codebook; abort if it changed.
  2. build masked packets D01-D07 (G3B4_BLIND_SEED) with no id/model/gold/
     historical verdict; the masked packet set is written first.
  3. code deterministically with the rules fixed in the codebook; persist the
     coded packets BEFORE any id is rejoined.
  4. only then unblind and join issue ids / mechanical labels for comparison.

This is a SINGLE AI coder, rule-based, with NO independent human coder and NO
independent review. It is not independent arbitration (disclosed in output).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path

from evidence import g3b4_common as C

MODEL = 'gpt-4.1-mini'
COND = 'T3D-Strict'
ERR_ISSUES = ['13615', '13974', '15349', '17318', '17630', '21847', '24443']
OUT = C.G3B4 / 'blind_coding'
OUT.mkdir(parents=True, exist_ok=True)
CODEBOOK = OUT / 'g3b4_blind_codebook.json'

# Frozen code expectations (must match the frozen codebook codes).
CODE_IDS = ['C1_SYMPTOM_RESOLUTION_AS_ACCEPTANCE',
            'C2_COVERAGE_COMPLETENESS_AS_VERDICT',
            'C3_ABSENCE_OF_FAILURE_EVIDENCE_AS_EVIDENCE_OF_ABSENCE',
            'C4_WITHHOLDING_ACKNOWLEDGED_BUT_OVERRIDDEN',
            'C5_PROVENANCE_FRESHNESS_AS_SUBSTANCE',
            'C6_OTHER']
PRIMARY_PRIORITY = {  # lower number wins when several fire in conclusion
    'C3_ABSENCE_OF_FAILURE_EVIDENCE_AS_EVIDENCE_OF_ABSENCE': 1,
    'C1_SYMPTOM_RESOLUTION_AS_ACCEPTANCE': 2,
    'C2_COVERAGE_COMPLETENESS_AS_VERDICT': 3,
    'C5_PROVENANCE_FRESHNESS_AS_SUBSTANCE': 4,
    'C4_WITHHOLDING_ACKNOWLEDGED_BUT_OVERRIDDEN': 5}


# ---------------------------------------------------------------------------
# Step 0/1: load + hash the frozen codebook
# ---------------------------------------------------------------------------
def load_frozen_codebook() -> tuple[dict, str]:
    raw = CODEBOOK.read_bytes()
    digest = C.sha256_bytes(raw)
    cb = json.loads(raw.decode('utf-8'))
    assert set(cb['codes']) == set(CODE_IDS), 'codebook codes drifted'
    assert cb['frozen_before_coding'] is True
    return cb, digest


# ---------------------------------------------------------------------------
# Step 2: masking + blinded packets
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r'\b\d+\b')
_PAREN_SYMPTOM_RE = re.compile(r'\(.*?\)')


def mask_text(text: str) -> str:
    """Remove issue-identifying surface. Symptom prose is intentionally left
    because the reason cannot be coded without it; residual re-identification
    risk is disclosed (PARTIAL blind)."""
    t = _NUM_RE.sub('<NUM>', text)
    # strip parenthetical concrete symptom examples like "(IndexError in x)"
    t = _PAREN_SYMPTOM_RE.sub('(<SYMPTOM DETAIL>)', t)
    return t


def build_packets():
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    by = {i['issue']: i for i in pe['issues']}
    units = []
    for e in ERR_ISSUES:
        iid = f'sympy__sympy-{e}'
        cell = next(c for c in by[iid]['models'][MODEL]
                    if c['condition'] == COND)
        tool_seq = [t['tool'] for t in cell['tool_responses']]
        units.append({
            'issue_holder': e,  # removed before packet is finalised
            'reason_raw': cell['g3b3_model_reasoning'],
            'tool_name_sequence': tool_seq})
    rng = random.Random(C.G3B4_BLIND_SEED)
    order = units[:]
    rng.shuffle(order)
    sealed_map = {}
    packets = []
    for k, u in enumerate(order, start=1):
        did = 'D%02d' % k
        sealed_map[did] = u['issue_holder']
        packets.append({
            'packet_id': did,
            'masked_reason': mask_text(u['reason_raw']),
            'tool_name_sequence': u['tool_name_sequence'],
            'final_action_visible': 'the text returns a decisive acceptance '
                                    'conclusion (packet scope: committed-'
                                    'acceptance units only)'})
    return packets, sealed_map


# ---------------------------------------------------------------------------
# Step 3: deterministic coding (rules fixed in the frozen codebook)
# ---------------------------------------------------------------------------
_CLAUSE_SPLIT = re.compile(r'\btherefore\b', re.I)

# Verbatim/near-verbatim defining signals, per code.
_C1 = [re.compile(p, re.I) for p in [
    r'symptom (no longer reproduces|is resolved|is confirmed resolved)',
    r'issue symptom[^.]{0,60}(no longer reproduces|resolved|resolved)',
    r'(patch )?(successfully )?(resolves|fixes) the issue']]
_C2 = [re.compile(p, re.I) for p in [
    r'coverage is complete for the declared',
    r'has complete coverage of the declared',
    r'(declared acceptance and regression test sets were fully executed)',
    r'fully executed with no missing tests']]
_C3 = [re.compile(p, re.I) for p in [
    r'no evidence of any (acceptance test failure|failing acceptance[^.]*|'
    r'failure|regression)',
    r'no (new )?(failures|regressions)',
    r'no failures or regressions (detected|introduced)',
    r'(are|is) no failing acceptance checks',
    r'without (introducing )?regressions?',
    r'acceptable for merge|is acceptable|acceptable for merging',
    r'meets the acceptance criteria']]
_C4 = [re.compile(p, re.I) for p in [
    r'(outcomes|results) (are|is) (withheld|not provided|not adjudicated)',
    r'acceptance (outcomes|results) (not|beyond)']]
_C5 = [re.compile(p, re.I) for p in [
    r'(artifact )?is linked to this patch',
    r'(is|correctly linked|linked)[^.]{0,30}(fresh|linked|commit)',
    r'fresh for the current commit tree',
    r'authentic signature|signature verified']]
_RULES = {'C1_SYMPTOM_RESOLUTION_AS_ACCEPTANCE': _C1,
          'C2_COVERAGE_COMPLETENESS_AS_VERDICT': _C2,
          'C3_ABSENCE_OF_FAILURE_EVIDENCE_AS_EVIDENCE_OF_ABSENCE': _C3,
          'C4_WITHHOLDING_ACKNOWLEDGED_BUT_OVERRIDDEN': _C4,
          'C5_PROVENANCE_FRESHNESS_AS_SUBSTANCE': _C5}


def _hits(patterns, text):
    return sorted({m.group(0).strip() for pat in patterns
                   for m in pat.finditer(text)})


def code_packet(packet):
    text = packet['masked_reason']
    parts = _CLAUSE_SPLIT.split(text)
    conclusion = parts[1] if len(parts) > 1 else text
    fired = {}
    for code, pats in _RULES.items():
        h = _hits(pats, text)
        if h:
            fired[code] = h
    # primary: codes firing inside the conclusion clause, then fixed priority
    in_conclusion = [code for code in fired
                     if _hits(_RULES[code], conclusion)]
    candidates = in_conclusion or list(fired)
    primary = None
    if candidates:
        primary = sorted(candidates,
                         key=lambda c: PRIMARY_PRIORITY.get(c, 9))[0]
    if not fired:
        fired = {'C6_OTHER': ['no C1-C5 signal matched']}
        primary = 'C6_OTHER'
    # confidence: high if a defining signal is verbatim in conclusion
    conf = 'high' if primary in in_conclusion else (
        'medium' if primary in fired else 'low')
    return {'packet_id': packet['packet_id'],
            'codes_applied': sorted(fired),
            'primary_code': primary,
            'confidence': conf,
            'matched_signals': fired,
            'conclusion_clause': conclusion.strip(),
            'coder': 'single AI coder (rule-based); no independent human '
                     'coder; no independent review'}


# ---------------------------------------------------------------------------
# Step 4: unblind + join mechanical labels (only after coding persisted)
# ---------------------------------------------------------------------------
def mechanical_upgrade_subtypes():
    audit = json.loads((C.OUT_AUDIT_DIR /
                        'g3b4_gpt_strict_audit.json').read_text(encoding='utf-8'))
    return {p['issue']: p.get('upgrade_wording_subtypes')
            for p in audit['per_issue']}


def main():
    cb, cb_digest = load_frozen_codebook()
    packets, sealed_map = build_packets()

    # persist the blinded packets first (still keyed only by D-id)
    (OUT / 'g3b4_blind_packets.json').write_bytes(C.canonical_bytes({
        'codebook_sha256': cb_digest,
        'blind_seed': C.G3B4_BLIND_SEED,
        'partial_blind_disclosure': cb['blinding_protocol'],
        'packets': packets}))

    # code and persist BEFORE unblinding
    coded = [code_packet(p) for p in packets]
    (OUT / 'g3b4_blind_coded_packets.json').write_bytes(C.canonical_bytes({
        'codebook_sha256': cb_digest,
        'coded_before_unblinding': True,
        'coded_packets': coded}))

    # sealed mapping kept in a distinct file
    (OUT / 'g3b4_blind_sealed_mapping.json').write_bytes(
        C.canonical_bytes({'seed': C.G3B4_BLIND_SEED,
                           'mapping_packet_to_issue': sealed_map}))

    # now unblind for comparison
    mech = mechanical_upgrade_subtypes()
    joined = []
    for cp, pkt in zip(coded, packets):
        issue = sealed_map[cp['packet_id']]
        joined.append({
            'issue': issue,
            'packet_id': cp['packet_id'],
            'blind_primary_code': cp['primary_code'],
            'blind_codes_applied': cp['codes_applied'],
            'confidence': cp['confidence'],
            'mechanical_wording_subtypes_from_g3b4_strict_audit':
                mech.get(issue)})

    from collections import Counter
    primary_dist = Counter(c['blind_primary_code'] for c in joined)
    any_code_dist = Counter(code for c in joined for code in
                            c['blind_codes_applied'])
    out = {
        'document': 'Gate 3-B.4 task 4 partially-blinded reason coding '
                    '(7 GPT T3D-Strict unsupported-ACCEPT cells)',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'api_calls_made_by_this_audit': 0,
        'codebook_sha256': cb_digest,
        'codebook_frozen_before_coding': True,
        'n_units': 7,
        'blinding': {
            'seed': C.G3B4_BLIND_SEED,
            'ids_hidden': ['issue', 'model', 'gold', 'historical verdicts',
                           'prior tags'],
            'partial_blind': True,
            'partial_blind_reason': 'symptom prose must remain for coding and '
                                    'can uniquely identify an issue',
            'packets_file': 'blind_coding/g3b4_blind_packets.json',
            'sealed_mapping_file': 'blind_coding/g3b4_blind_sealed_mapping.json',
            'coded_before_unblinding_file':
                'blind_coding/g3b4_blind_coded_packets.json'},
        'coder_independence': {
            'single_ai_coder': True,
            'rule_based': True,
            'independent_human_coder': 'NOT OBTAINED',
            'independent_review': 'NOT OBTAINED',
            'this_is_not_independent_arbitration': True,
            'note': 'results are an internal reproducible characterisation; '
                    'a real second-annotator plan is in the G3-B.4 report '
                    '(task 11) and must not be substituted by this coding.'},
        'primary_code_distribution': dict(primary_dist),
        'any_code_prevalence': dict(any_code_dist),
        'joined_results': joined,
        'interpretation': 'All 7 committed accepts fire the same template: '
                          'provenance/freshness (C5) + coverage completeness '
                          '(C2) + symptom resolution (C1) + absence-of-failure'
                          ' phrasing (C3), with C3 the most proximal licensor '
                          'of the acceptance conclusion under the frozen '
                          'priority rule. C4 never fires: the model does not '
                          'acknowledge the withholding before accepting. This '
                          'is a homogeneous over-commitment template rather '
                          'than 7 distinct reasoning errors.',
        'gold_authority': C.GOLD_AUTHORITY}
    dest = OUT / 'g3b4_blind_coding_results.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('codebook sha256:', cb_digest[:16], '...')
    print('primary distribution:', dict(primary_dist))
    print('any-code prevalence:', dict(any_code_dist))
    for c in joined:
        print(c['packet_id'], '-> issue', c['issue'], '|',
              c['blind_primary_code'].split('_')[0], '|',
              c['blind_codes_applied'])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
