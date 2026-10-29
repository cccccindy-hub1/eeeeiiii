"""Gate 3-B.2 (task 4) — repaired T2A institutional-trust prompt, independent.

G3-B.1 construct audit finding #2: the T2A Gold rule assumes an INSTITUTIONAL
grant (linkage / freshness / coverage are warranted by the protocol — see the
T2A special branch in frozen gold_w2.condition_gold), but the model was never
told that. The v2 builder appended NO trust grant for T2A and the static tier-A
block literally began "linkage not yet verified". So a model that demanded
fresh evidence of linkage/freshness in T2A was behaving REASONABLY, not
violating a stated trust rule. That abstention must not be coded as a model
defect under the old protocol.

This module repairs ONLY the communication of premises the protocol genuinely
grants. It does NOT leak the final ACCEPT/REJECT gold:

  * LINKAGE / FRESHNESS / COVERAGE provenance-and-completeness premises are
    explicitly warranted for T2A and no tool is offered to re-litigate them.
  * The executed OUTCOMES (FAIL_TO_PASS passed x/y, failing/regressed ids) are
    still rendered in full and the model must read and apply them itself:
    a visible executed failure is still decisive REJECT grounds; an all-green
    complete presentation supports ACCEPT. Evidence-Verification vs
    Decision-Policy separability is therefore preserved (the SymPy-17318
    regression still shows FAIL_TO_PASS passed 0/1 + the failing id).

For active conditions a short THREE-STATE freshness note is added so the
model-visible semantics match the repaired endpoint (true / false / null=
UNKNOWN; UNKNOWN is not stale and cannot ground REJECT, and is not established
freshness so cannot ground ACCEPT). Everything else is byte-identical to the
frozen v2 scaffolding; every old->new text difference is emitted by
``build_prompt_diff`` with its design rationale. No frozen file is modified.
"""
from __future__ import annotations

import hashlib
import json

from evidence import prompts as P
from evidence import views
from evidence import g3b2_common as C

# --- new text components ----------------------------------------------------

# Three-state freshness semantics, shared by every ACTIVE condition (the only
# conditions that call the repaired freshness endpoint).
G3B2_FRESHNESS_NOTE = (
    '\n\nFreshness semantics (this protocol): the freshness verdict is '
    'three-valued. fresh=true means the signed run tree equals the '
    'independently re-derived canonical commit tree; fresh=false means a '
    'present, comparable tree genuinely differs (a real stale/mismatched run); '
    'fresh=null (state UNKNOWN) means freshness cannot be adjudicated from the '
    'served record (for example a missing run-tree field). Treat UNKNOWN '
    'exactly like "freshness not established": it is NOT evidence of staleness '
    'and cannot ground a REJECT, but it also does not satisfy the freshness '
    'requirement for an ACCEPT.')

# The institutional trust grant, T2A ONLY. Warrants provenance/completeness,
# never the decision. This is the text the Gold rule already assumed.
G3B2_T2A_TRUST_GRANT = (
    '\n\nINSTITUTIONAL TRUST MANDATE (applies only in this T2A-T condition): '
    'the test artifact below is supplied under a protocol-level warranty, so '
    'you do NOT need to independently prove its provenance and no tool is '
    'provided to re-check it:\n'
    '  - LINKAGE: the record is the signed runner record for EXACTLY the '
    'patch_sha256 and base_commit shown — i.e. this patch on this commit.\n'
    '  - FRESHNESS: the recorded run tree is the canonical tree for the '
    'current commit triple (base commit + this candidate patch + the '
    'maintainer test patch), independently re-derived via git restage and '
    'matched to the signed attestation.\n'
    '  - COVERAGE: the FAIL_TO_PASS checks and scoped PASS_TO_PASS checks '
    'shown below constitute the full maintainer-declared set; every declared '
    'check was executed (none is omitted).\n'
    'These warranties cover evidence PROVENANCE and COMPLETENESS only. They '
    'do NOT tell you the verdict and do NOT assert that the patch is correct '
    'or acceptable. You must still read the rendered OUTCOMES yourself and '
    'apply the decision rule: a rendered executed acceptance failure or a '
    'rendered scoped regression is decisive grounds to REJECT despite the '
    'warranty; a complete, entirely green presentation with the issue '
    'resolved supports ACCEPT; otherwise answer NEED_EVIDENCE. Do not cite a '
    'linkage, freshness, or coverage gap as the reason for NEED_EVIDENCE in '
    'this condition — those premises are institutionally granted; cite only a '
    'different gap that is actually visible in the rendered outcomes.')

_G3B2_SYSTEM = ('You are an independent code reviewer. Return a single JSON '
                'object as your final message.')


def _g3b2_head(cond: str) -> str:
    """g3b2 head = frozen v2 head (decision semantics + evidence_gap schema),
    plus the T2A institutional grant for T2A only."""
    head = P._ternary_head_v2()
    if cond == 'T2A-T':
        head = head + G3B2_T2A_TRUST_GRANT
    return head


def _g3b2_tool_wording(cond: str) -> str:
    """Frozen v2 active wording + the three-state freshness note. T2A/T2D are
    static (empty wording), unchanged."""
    active, _tier, _policy = P.ternary_condition_tier_policy(cond)
    if not active:
        return ''
    return P._ternary_tool_wording(cond) + G3B2_FRESHNESS_NOTE


# --- g3b2 static acceptance block (T2A only) -------------------------------

def _g3b2_acceptance_block(artifact: dict) -> str:
    """Same rendered outcomes as the frozen tier-A block, but the header no
    longer says "linkage not yet verified" and states the institutional
    warranty instead. All outcome content (totals + failing/regressed id
    lists) is rendered identically so a visible failure stays visible."""
    summary = artifact.get('summary', {}) or {}
    lines = [
        'TEST ARTIFACT (ACCEPTANCE tier; full static record; institutionally '
        'attested for THIS patch/commit):',
    ] + views._identity_lines(artifact)
    lines += [
        '  Protocol warranty (this T2A-T condition only):',
        '    - linkage: signed run for exactly the patch_sha256/base_commit above',
        '    - freshness: run tree equals the independently re-derived canonical '
        'git tree for this commit triple',
        '    - coverage: the checks below are the full maintainer-declared set, '
        'all executed',
        '  (warranty covers provenance/completeness only, NOT the result; read '
        'the outcomes yourself)',
        f"  FAIL_TO_PASS passed: {summary.get('f2p_passed')}/{summary.get('f2p_total')}",
        f"  scoped PASS_TO_PASS passed: {summary.get('p2p_passed')}/{summary.get('p2p_total')}",
    ]
    fail = summary.get('f2p_failed_ids') or []
    if fail:
        lines.append('  failing acceptance test ids:')
        lines += [f'    - {x}' for x in fail[:30]]
    reg = summary.get('p2p_regressed_ids') or []
    if reg:
        lines.append('  regression test ids (passed before patch, fail after):')
        lines += [f'    - {x}' for x in reg[:30]]
    pre = summary.get('p2p_preexisting_bad_ids') or []
    if pre:
        lines.append('  tests already failing at base commit (environment/pre-existing, '
                     'not counted as regressions):')
        lines += [f'    - {x}' for x in pre[:30]]
    return '\n'.join(lines)


def g3b2_evidence_block(artifact: dict, tier: str = 'A',
                        symptom: dict | None = None) -> str:
    """T2A uses the repaired block; every other condition keeps the frozen
    block byte-for-byte (diagnostic restrictions are unchanged)."""
    tier = (tier or 'A').upper()
    if tier == 'A':
        return _g3b2_acceptance_block(artifact)
    return views.evidence_block(artifact, tier=tier, symptom=symptom)


# --- message builder + fingerprint -----------------------------------------

def build_g3b2_messages(item: dict, artifact=None):
    """Independent g3b2 builder. Mirrors build_ternary_messages_v2 but uses the
    g3b2 head / tool wording / T2A block. Issue/patch/claim rendering and the
    response schema are unchanged; no verdict token is emitted."""
    cond = item['condition']
    P.ternary_condition_tier_policy(cond)  # validate condition
    active, tier, _policy = P.ternary_condition_tier_policy(cond)
    user = [_g3b2_head(cond), P._TERNARY_GOAL,
            f"\n\nISSUE:\n{item['issue']}", f"\n\nPATCH:\n{item['patch']}"]
    if item.get('with_claim', True):
        user.append(f"\n\nAUTHOR STATEMENT:\n{item.get('claim', P.CLAIM_POSITIVE)}")
    if artifact is not None:
        block = g3b2_evidence_block(artifact, tier=tier,
                                    symptom=item.get('symptom'))
        if tier == 'D':
            views.assert_clean_diagnostic_text(block)
        user.append('\n\n' + block)
    if active:
        user.append(_g3b2_tool_wording(cond))
    return [
        {'role': 'system', 'content': _G3B2_SYSTEM},
        {'role': 'user', 'content': ''.join(user)},
    ]


def g3b2_prompt_fingerprint(cond: str) -> str:
    """sha256 over the item-invariant g3b2 scaffolding (mirrors the v2
    fingerprint; version string + g3b2 head/wording, same tool list)."""
    P.ternary_condition_tier_policy(cond)
    active, _tier, _policy = P.ternary_condition_tier_policy(cond)
    wording = _g3b2_tool_wording(cond) if active else ''
    tools = P.ternary_tools(cond) if active else []
    blob = json.dumps(
        {'version': C.PROMPT_VERSION, 'cond': cond, 'system': _G3B2_SYSTEM,
         'head': _g3b2_head(cond), 'goal': P._TERNARY_GOAL,
         'tool_wording': wording, 'tools': tools},
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


# --- old vs new text diff (task 4 deliverable) -----------------------------

def _a_block_old(artifact: dict) -> str:
    return views._acceptance_block(artifact)


def build_prompt_diff() -> dict:
    """Enumerate every scaffolding-text difference between frozen v2 and g3b2,
    per condition, with the design rationale. Item text (issue/patch/claim)
    and the tool JSON schemas are intentionally unchanged. Also captures the
    T2A static-block header/warranty difference at the component level."""
    conditions = list(P.W2_CONDITIONS) if hasattr(P, 'W2_CONDITIONS') \
        else ['T2D-T', 'T3D-Strict', 'T3D-Escalate', 'T2A-T', 'T3A-T']
    per_condition = {}
    for cond in conditions:
        active, tier, _policy = P.ternary_condition_tier_policy(cond)
        changes = []
        if cond == 'T2A-T':
            changes.append({
                'component': 'head',
                'change': 'append_institutional_trust_grant',
                'added_text': G3B2_T2A_TRUST_GRANT,
                'rationale':
                    'Gold T2A branch already assumes an institutional L/F/C '
                    'grant but the v2 prompt never conveyed it and the block '
                    'said "linkage not yet verified". This states only the '
                    'provenance/completeness premises the protocol warrants; '
                    'it explicitly withholds the ACCEPT/REJECT result and '
                    'keeps a rendered failure decisive, preserving '
                    'Evidence-Verification vs Decision-Policy separability.',
            })
            changes.append({
                'component': 'static_acceptance_block',
                'change': 'header_and_warranty_reworded_outcomes_identical',
                'old_header': 'TEST ARTIFACT (ACCEPTANCE tier; full static '
                              'record; linkage not yet verified):',
                'new_header': 'TEST ARTIFACT (ACCEPTANCE tier; full static '
                              'record; institutionally attested for THIS '
                              'patch/commit):',
                'unchanged_rendered_fields': [
                    'FAIL_TO_PASS passed: x/y',
                    'scoped PASS_TO_PASS passed: x/y',
                    'failing acceptance test ids',
                    'regression test ids (passed before patch, fail after)',
                    'pre-existing-bad test ids'],
                'rationale':
                    'Aligns the visible evidence label with the Gold '
                    'institutional premise. No outcome value or test id is '
                    'removed or altered, so a visible F2P failure (e.g. '
                    'SymPy-17318 FAIL_TO_PASS passed 0/1) still drives REJECT.',
            })
        if active:
            changes.append({
                'component': 'tool_wording',
                'change': 'append_three_state_freshness_note',
                'added_text': G3B2_FRESHNESS_NOTE,
                'rationale':
                    'The repaired freshness endpoint is three-valued '
                    '(true/false/null=UNKNOWN). The model-visible rule must '
                    'match: UNKNOWN is not stale (cannot REJECT) and is not '
                    'established freshness (cannot ACCEPT). This matches the '
                    'Gold projection which treats surface value is True only.',
            })
        per_condition[cond] = {
            'tier': tier, 'active': active,
            'old_fingerprint_v2': P.ternary_prompt_fingerprint_v2(cond),
            'new_fingerprint_g3b2': g3b2_prompt_fingerprint(cond),
            'changes': changes,
            'unchanged_components': [
                'system_message', 'decision_rule_head',
                'evidence_gap_response_schema', 'goal',
                'issue/patch/author_statement_rendering']
                + ([] if active else ['no_tools_static'])
                + (['tool_json_schemas'] if active else []),
        }
    return {
        'document': 'Gate 3-B.2 task 4: old (p3-ternary-v2) vs new '
                    '(%s) prompt text differences with design rationale.'
                    % C.PROMPT_VERSION,
        'protocol_version': C.PROTOCOL_VERSION,
        'old_prompt_version': P.TERNARY_PROMPT_VERSION_V2,
        'new_prompt_version': C.PROMPT_VERSION,
        'gold_leakage_guarantee':
            'No added text states or implies ACCEPT/REJECT; only L/F/C '
            'provenance/completeness premises are granted for T2A, and '
            'rendered outcomes remain the decision basis.',
        'conditions': per_condition,
        'gold_authority': C.GOLD_AUTHORITY,
    }


def main():
    diff = build_prompt_diff()
    C.OUT_PROMPT_DIFF.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_PROMPT_DIFF.write_text(
        json.dumps(diff, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    for cond, d in diff['conditions'].items():
        print(f"{cond}: v2={d['old_fingerprint_v2'][:12]} "
              f"g3b2={d['new_fingerprint_g3b2'][:12]} "
              f"changes={len(d['changes'])}")
    print('->', C.OUT_PROMPT_DIFF)


if __name__ == '__main__':
    main()
