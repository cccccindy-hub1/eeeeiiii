"""CEE v1.1 Label-Leakage / Construct-Validity audit. ZERO API, read-only.

User authorisation (2026-10-25): CEE v1.1 accepted; only OFFLINE analysis is
approved; no new paid calls, no modification of any frozen Prompt / Gold /
Bundle / result / metric, no git commit.

Question under audit
--------------------
Did the 22 fixed-evidence bundles hand the model something close to the gold
answer? We separate three kinds of content:

  Raw evidence              - the actual issue text, the patch, the signed run
                              counts and the concrete failing/regressed test
                              ids; the author statement.
  Derived evidence metadata - binary adjudications computed OFFLINE from the
                              signed record + attestation + executed probe:
                              linked / fresh / complete / signature authentic,
                              and the two issue-symptom probe booleans.
  Decision-equivalent meta  - any token/field that states or all-but-states the
                              ACCEPT/REJECT/NEED_EVIDENCE label itself (gold,
                              class, decisive_failure, scenario name, an
                              imperative "reject this", ...).

This script (1) scans the exact served bytes for decision-equivalent tokens,
(2) proves whether the label is MECHANICALLY derivable from the rendered
fields plus the decision rule that the (item-invariant) prompt states, and
(3) audits each decisive-negative cell for whether the model saw a CONCRETE
failure fact versus only a pre-derived verdict.

Reads (frozen, never written):
  evidence_store_cee/bundles/*.txt
  evidence_store_cee/cee_gold.jsonl
  evidence_store_cee/cee_v11_{deepseek_flash,gpt41mini}_results.jsonl
Writes only:
  evidence_store_cee/cee_v11_label_leakage_audit.json

    uv run --python 3.13 -m evidence.cee_leakage_audit_v11
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from evidence import cee_protocol as cee
from evidence.gold_w2 import oracle_gold

ROOT = Path(__file__).resolve().parent.parent
CEE_DIR = ROOT / 'evidence_store_cee'
BUNDLE_DIR = CEE_DIR / 'bundles'
DS_FILE = 'cee_v11_deepseek_flash_results.jsonl'
GPT_FILE = 'cee_v11_gpt41mini_results.jsonl'

# Literal label / hidden-state tokens. Scanned against the EVIDENCE BODY only
# (the item-invariant head legitimately contains the frozen sentence
# "Ground truth about mergeability is never given" and the decision rule).
DIRECT_LABEL_TOKENS = [
    'oracle_gold', 'condition_gold', 'cee_gold', 'merge_acceptable',
    'patch_correct', 'label_class', 'evidence_class', 'decisive_failure',
    'sufficient_success', 'symptom_polarity', 'sufficient_positive',
    'decisive_negative', '"scenario"', 'ground truth', 'gold label',
    'correct decision', 'the answer is', 'answer: accept', 'answer: reject',
    'you should accept', 'you should reject', 'you must reject',
    'you must accept', 'this patch is correct', 'this patch is incorrect',
    'wrong patch', 'wrong_patch', 'this is a valid patch',
]
# Class/scenario labels scanned as whole words (avoid "valid" inside
# "ACCEPTANCE-tier" false positives).
CLASS_WORD_TOKENS = ['insufficient', 'stale', 'valid', 'incomplete',
                     'contradictory', 'decisive', 'sufficient']
ENUM_LINE_RE = re.compile(r'^\s*(decision|verdict|label|gold)\s*[:=]\s*'
                          r'(ACCEPT|REJECT|NEED_EVIDENCE)\b', re.I)

# --- rendered-field parsers (everything comes straight from the body text) --
_LINK_RE = re.compile(r'linked to THIS patch and base commit:\s*(yes|no|n/a)')
_FRESH_RE = re.compile(r'fresh for the current commit tree:\s*(yes|no|n/a)')
_COMP_RE = re.compile(r'declared acceptance/regression set fully executed:\s*'
                      r'(yes|no|n/a)')
_PRE_RE = re.compile(r'issue symptom present before patch:\s*(yes|no|n/a)')
_POST_RE = re.compile(r'issue symptom reproduces after patch:\s*(yes|no|n/a)')
_F2P_RE = re.compile(r'FAIL_TO_PASS passed:\s*(\d+)/(\d+)')
_P2P_RE = re.compile(r'scoped PASS_TO_PASS passed:\s*(\d+)/(\d+)')
_REG_SECTION_RE = re.compile(r'regression test ids \(passed before patch, '
                             r'fail after\):')
_PREEXIST_SECTION_RE = re.compile(r'tests already failing at base commit')


def _read_jsonl(name):
    return [json.loads(l) for l in
            (CEE_DIR / name).read_text(encoding='utf-8').splitlines() if l.strip()]


def _split(text):
    marker = 'FIXED EVIDENCE BUNDLE'
    i = text.index(marker)
    return text[:i], text[i:]


def _yn(m, text):
    hit = m.search(text)
    return None if not hit or hit.group(1) == 'n/a' else hit.group(1) == 'yes'


def _bullets_after_header(lines, header_substr, stop_prefixes=('    -', '  ')):
    """Return the bullet test ids listed directly under a given section."""
    ids = []
    in_sec = False
    for ln in lines:
        if header_substr in ln:
            in_sec = True
            continue
        if in_sec:
            if ln.startswith('    - '):
                ids.append(ln[6:].strip())
            elif ln.strip() == '':
                continue
            else:
                in_sec = False
    return ids


def parse_rendered_fields(body):
    """Recover ONLY what a rule-following reader has in the body text."""
    linked = _yn(_LINK_RE, body)
    fresh = _yn(_FRESH_RE, body)
    complete = _yn(_COMP_RE, body)
    present_before = _yn(_PRE_RE, body)
    reproduces_after = _yn(_POST_RE, body)
    symptom_persists = bool(present_before) and bool(reproduces_after)
    f2p = _F2P_RE.search(body)
    p2p = _P2P_RE.search(body)
    f2p_pass, f2p_tot = (int(f2p.group(1)), int(f2p.group(2))) if f2p else (0, 0)
    p2p_pass, p2p_tot = (int(p2p.group(1)), int(p2p.group(2))) if p2p else (0, 0)
    lines = body.splitlines()
    f2p_fail_ids = _bullets_after_header(lines, 'failing acceptance test ids')
    p2p_regressed_ids = _bullets_after_header(
        lines, 'regression test ids (passed before patch, fail after)')
    preexisting_listed = bool(_PREEXIST_SECTION_RE.search(body))
    # Acceptance-channel failure as a reader of the rendered acceptance block
    # computes it: a failed FAIL_TO_PASS, or a true P2P regression. The
    # separately-labelled pre-existing list is explicitly not a regression.
    acceptance_failure = (f2p_pass < f2p_tot and f2p_tot > 0) or \
        (len(p2p_regressed_ids) > 0)
    executed = f2p_tot + p2p_tot
    acceptance_success = (not acceptance_failure) and executed > 0
    return {
        'linked': linked, 'fresh': fresh, 'complete': complete,
        'present_before': present_before, 'reproduces_after': reproduces_after,
        'symptom_persists': symptom_persists,
        'f2p_passed': f2p_pass, 'f2p_total': f2p_tot,
        'p2p_passed': p2p_pass, 'p2p_total': p2p_tot,
        'acceptance_failure_from_rendered_block': acceptance_failure,
        'acceptance_success_from_rendered_block': acceptance_success,
        'concrete_f2p_failure_ids_visible': f2p_fail_ids,
        'concrete_p2p_regression_ids_visible': p2p_regressed_ids,
        'preexisting_failures_listed_separately': preexisting_listed,
        'executed_total_rendered': executed,
    }


def _issue_patch_span(body):
    """Character span of the raw ISSUE+PATCH+AUTHOR text (everything before
    the rendered TEST ARTIFACT). Natural-language token hits inside this span
    are part of the ORIGINAL GitHub issue / patch, not injected verdicts."""
    m = re.search(r'TEST ARTIFACT', body)
    return (0, m.start()) if m else (0, len(body))


def scan_body(body):
    low = body.lower()
    lo, hi = _issue_patch_span(body)
    raw_hits, injected_hits, contexts = [], [], {}
    for t in DIRECT_LABEL_TOKENS:
        start = 0
        while True:
            k = low.find(t, start)
            if k < 0:
                break
            (raw_hits if lo <= k < hi else injected_hits).append(t)
            contexts.setdefault(t, low[max(0, k - 60):k + len(t) + 60])
            start = k + len(t)
    word_hits = sorted({t for t in CLASS_WORD_TOKENS
                        if re.search(r'\b' + re.escape(t) + r'\b', low)})
    enum_lines = [ln.strip() for ln in body.splitlines()
                  if ENUM_LINE_RE.search(ln)]
    # Standalone decision enums in the body (exclude the ACCEPTANCE-tier word).
    body_no_acc = re.sub(r'ACCEPTANCE', '', body)
    enum_counts = {d: len(re.findall(r'\b' + d + r'\b', body_no_acc))
                   for d in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE')}
    return {'injected_label_token_hits': sorted(set(injected_hits)),
            'natural_language_hits_inside_issue_or_patch':
                sorted(set(raw_hits)),
            'natural_language_hit_context': contexts,
            'class_word_hits_in_body': word_hits,
            'explicit_decision_line_hits': enum_lines,
            'standalone_decision_enum_mentions_in_body': enum_counts}


def main():
    gold_rows = {r['bundle_id']: r for r in _read_jsonl('cee_gold.jsonl')}
    ds = {r['bundle_id']: r for r in _read_jsonl(DS_FILE)}
    gp = {r['bundle_id']: r for r in _read_jsonl(GPT_FILE)}

    per_bundle = []
    n_mechanical_match = 0
    n_direct = 0
    for bid, grow in gold_rows.items():
        served = (BUNDLE_DIR / f'{bid}.txt').read_text(encoding='utf-8')
        head, body = _split(served)
        scan = scan_body(body)
        if scan['injected_label_token_hits'] or scan['explicit_decision_line_hits']:
            n_direct += 1
        rf = parse_rendered_fields(body)
        # Apply the EXACT frozen oracle rule to the fields rendered in the
        # body. This is the rule the CEE head states in prose.
        mech = oracle_gold(
            linked=rf['linked'], fresh=rf['fresh'], complete=rf['complete'],
            acceptance_failure=rf['acceptance_failure_from_rendered_block'],
            acceptance_success=rf['acceptance_success_from_rendered_block'],
            symptom_persists=rf['symptom_persists'])
        gold = grow['cee_gold']
        match = mech == gold
        n_mechanical_match += int(match)
        f = grow['facts']
        per_bundle.append({
            'bundle_id': bid,
            'scenario_internal_not_served': grow['scenario'],
            'evidence_class_internal_not_served': grow['evidence_class'],
            'gold': gold,
            'body_bytes': len(body.encode('utf-8')),
            'leakage_scan': scan,
            'rendered_fields': rf,
            'gold_mechanically_recomputed_from_rendered_fields': mech,
            'mechanical_matches_gold': match,
            'ds_decision': ds[bid]['parsed'],
            'gpt_decision': gp[bid]['parsed'],
            'ds_appropriate': bool(ds[bid]['appropriate']),
            'gpt_appropriate': bool(gp[bid]['appropriate']),
            '_facts_oracle': {
                'linked': f['linked'], 'fresh': f['fresh'],
                'complete': f['complete'],
                'executed_failure_count': f['executed_failure_count'],
                'executed_check_count': f['executed_check_count'],
                'symptom_polarity': f['symptom_polarity']},
        })

    # ---- decisive-negative deep audit ----------------------------------
    dn_cases = []
    for c in per_bundle:
        if c['gold'] != 'REJECT':
            continue
        rf = c['rendered_fields']
        o_channel = bool(rf['linked']) and bool(rf['fresh']) and \
            rf['acceptance_failure_from_rendered_block']
        p_channel = rf['symptom_persists']
        dn_cases.append({
            'bundle_id': c['bundle_id'],
            'scenario_internal': c['scenario_internal_not_served'],
            'reject_supported_by_O_channel_linked_fresh_failure': o_channel,
            'reject_supported_by_P_channel_symptom_persists': p_channel,
            'concrete_failure_test_ids_visible':
                rf['concrete_f2p_failure_ids_visible']
                + rf['concrete_p2p_regression_ids_visible'],
            'reject_rests_only_on_derived_probe_binary':
                p_channel and not o_channel and not
                (rf['concrete_f2p_failure_ids_visible']
                 or rf['concrete_p2p_regression_ids_visible']),
            'linked': rf['linked'], 'fresh': rf['fresh'],
            'complete': rf['complete'],
            'f2p_passed_total': [rf['f2p_passed'], rf['f2p_total']],
            'p2p_passed_total': [rf['p2p_passed'], rf['p2p_total']],
            'ds_decision': c['ds_decision'], 'gpt_decision': c['gpt_decision'],
            'ds_appropriate': c['ds_appropriate'],
            'gpt_appropriate': c['gpt_appropriate'],
        })

    def errset(model_key):
        return {c['bundle_id']: c['scenario_internal_not_served']
                for c in per_bundle
                if not c[f'{model_key}_appropriate']}
    ds_err, gp_err = errset('ds'), errset('gpt')
    error_sets = {
        'all_errors_lie_in_class': sorted({
            c['evidence_class_internal_not_served']
            for c in per_bundle
            if not c['ds_appropriate'] or not c['gpt_appropriate']}),
        'deepseek_over_abstain_cells': ds_err,
        'gpt_over_abstain_cells': gp_err,
        'intersection_both_wrong': sorted(set(ds_err) & set(gp_err)),
        'deepseek_only_wrong': sorted(set(ds_err) - set(gp_err)),
        'gpt_only_wrong': sorted(set(gp_err) - set(ds_err)),
        'rationale_text_available': False,
        'rationale_limitation':
            'cee_run_v11 persisted only raw_content_sha256 and the parsed '
            'decision; the model reason/missing_evidence strings were NOT '
            'stored, so error attribution rests on served inputs + decisions, '
            'not on quoted rationale. Re-calling to retrieve rationale is '
            'forbidden by the zero-API authorisation.'}

    field_taxonomy = [
        {'tier': 'raw', 'field': 'ISSUE (problem_statement)',
         'enters_model_input': True,
         'provenance': 'frozen wave2_pilot_raw_rows (original GitHub issue)'},
        {'tier': 'raw', 'field': 'PATCH (model_patch diff)',
         'enters_model_input': True,
         'provenance': 'frozen served patch text'},
        {'tier': 'raw', 'field': 'AUTHOR STATEMENT',
         'enters_model_input': True,
         'provenance': 'single constant CLAIM_POSITIVE for all 22; unverified'},
        {'tier': 'raw', 'field': 'TEST ARTIFACT counts (F2P x/y, P2P x/y)',
         'enters_model_input': True,
         'provenance': 'signed record own summary, tier-A acceptance block'},
        {'tier': 'raw', 'field': 'concrete failing acceptance / regression '
                                 'test ids + pre-existing list',
         'enters_model_input': True,
         'provenance': 'signed record; pre-existing failures labelled '
                       'not-regressions in the same block'},
        {'tier': 'derived_metadata', 'field': 'record signature authentic',
         'enters_model_input': True,
         'provenance': 'HMAC verification of the signed record'},
        {'tier': 'derived_metadata', 'field': 'linked to THIS patch/commit',
         'enters_model_input': True,
         'provenance': 'offline adjudication over record hashes + attestation'},
        {'tier': 'derived_metadata', 'field': 'fresh for current commit tree',
         'enters_model_input': True,
         'provenance': 'offline freshness adjudication'},
        {'tier': 'derived_metadata', 'field': 'declared set fully executed',
         'enters_model_input': True,
         'provenance': 'offline coverage adjudication'},
        {'tier': 'derived_metadata', 'field': 'issue symptom present before / '
                                            'reproduces after (two booleans)',
         'enters_model_input': True,
         'provenance': 'executed pre/post symptom probe; only the binary '
                       'verdict is rendered, NOT the raw probe log'},
        {'tier': 'decision_equivalent', 'field': 'cee_gold (ACCEPT/REJECT/NEED)',
         'enters_model_input': False,
         'provenance': 'cee_gold.jsonl only; never rendered'},
        {'tier': 'decision_equivalent', 'field': 'evidence_class',
         'enters_model_input': False,
         'provenance': 'manifest/gold only; never rendered'},
        {'tier': 'decision_equivalent', 'field': 'decisive_failure / '
                                               'sufficient_success booleans',
         'enters_model_input': False,
         'provenance': 'gold derivation only; never rendered'},
        {'tier': 'decision_equivalent', 'field': 'internal scenario name '
                                               '(valid/stale/wrong_patch/...)',
         'enters_model_input': False,
         'provenance': 'fixture/gold key only; neutralised out of the record'},
        {'tier': 'decision_equivalent', 'field': 'bundle_id / expected{} / '
                                               'merge_acceptable / label_class',
         'enters_model_input': False,
         'provenance': 'build/manifest side data only; never rendered'},
    ]

    head_text = cee.CEE_HEAD + cee.CEE_GOAL
    report = {
        'document': 'GroundedReview CEE v1.1 label-leakage & construct-'
                    'validity audit (offline, zero API)',
        'protocol': cee.CEE_PROTOCOL_VERSION,
        'method': {
            'served_bytes_source': 'evidence_store_cee/bundles/*.txt (frozen; '
                                  'sha matches every executed result row)',
            'body_scan_tokens': DIRECT_LABEL_TOKENS,
            'body_scan_class_words': CLASS_WORD_TOKENS,
            'mechanical_test': 'parse linked/fresh/complete + symptom booleans '
                               '+ acceptance counts from the RENDERED body and '
                               'apply the frozen gold_w2.oracle_gold rule that '
                               'the CEE head states in prose',
        },
        'summary': {
            'n_bundles': len(per_bundle),
            'bodies_with_direct_label_or_decision_line': n_direct,
            'gold_mechanically_recomputable_from_rendered_fields':
                n_mechanical_match,
            'mechanical_match_rate':
                round(n_mechanical_match / len(per_bundle), 4),
            'head_contains_explicit_decision_rule': True,
            'head_text_sha256':
                hashlib.sha256(head_text.encode('utf-8')).hexdigest(),
            'verdict_word_in_body':
                'section heading "INTEGRITY VERDICTS" only (the adjudicated '
                'metadata); no ACCEPT/REJECT verdict follows it',
            'ground_truth_phrase': 'present ONLY in the item-invariant head '
                'sentence "Ground truth about mergeability is never given '
                'to you."; absent from every evidence body',
        },
        'construct_validity_verdict': {
            'literal_label_leakage': 'NONE FOUND: no gold token, class name, '
                'scenario name, decisive_failure/sufficient_success flag, or '
                'imperative answer sentence is rendered into any bundle body; '
                'the decision enum never appears as a label in the body.',
            'decision_rule_executability': 'HIGH: the prompt head states the '
                'complete asymmetric decision rule and the body renders every '
                'boolean rule input as pre-adjudicated yes/no, so the gold '
                f'label is mechanically recoverable on '
                f'{n_mechanical_match}/{len(per_bundle)} bundles by pure '
                'rule application. CEE therefore measures faithful EXECUTION '
                'OF A STATED POLICY OVER ADJUDICATED EVIDENCE FACTS, not '
                'unaided inference from primary logs.',
            'what_is_and_isnt_tested':
                'Linked/fresh/complete applicability and symptom persistence '
                'are GIVEN as verdicts, so CEE does not test deriving them. '
                'It tests whether the model (i) applies the asymmetric '
                'standard correctly and (ii) refuses/commits at the right '
                'point. 4/6 REJECT-gold cells additionally show a concrete '
                'failing test id; 2/6 (wrong_patch, stale_persists) support '
                'REJECT solely through the derived binary "reproduces after '
                'patch: yes" with green acceptance record, so on those 2 the '
                'cell does not test reading a primary failure at all.'
        },
        'field_taxonomy': field_taxonomy,
        'decisive_negative_audit': dn_cases,
        'error_intersection_and_difference': error_sets,
        'per_bundle': per_bundle,
    }
    out = CEE_DIR / 'cee_v11_label_leakage_audit.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print(f'bodies={len(per_bundle)} direct_leak_bodies={n_direct} '
          f'mechanical_gold_match={n_mechanical_match}/{len(per_bundle)}')
    for c in dn_cases:
        print(f"  DN {c['bundle_id']} O={c['reject_supported_by_O_channel_linked_fresh_failure']} "
              f"P={c['reject_supported_by_P_channel_symptom_persists']} "
              f"onlyProbeBinary={c['reject_rests_only_on_derived_probe_binary']} "
              f"DS={c['ds_decision']} GPT={c['gpt_decision']}")
    print('wrote', out.name)


if __name__ == '__main__':
    main()
