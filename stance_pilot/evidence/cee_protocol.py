"""Controlled Evidence Experiment (CEE) — frozen protocol, version cee-fixed-v1.

PURPOSE
=======
E1 (the frozen Wave-2.1 22-fixture x 5-condition ternary protocol) measures
END-TO-END agent performance: each model decides how many verification tools to
call, whether to escalate, and then interprets whatever evidence it obtained.
DeepSeek-flash and GPT-4.1-mini showed opposite failure patterns there, but
that comparison cannot tell whether the gap comes from (a) different evidence
ACQUISITION / verification policy (DeepSeek escalated 22/22 cells, GPT 12/22)
or (b) different INTERPRETATION of the same evidence.

CEE isolates (b):

  * ONE arm, ``CEE-FIXED`` — no tools, no escalation, one single model turn.
  * Both providers receive BYTE-IDENTICAL, pre-built fixed evidence bundles.
  * A bundle is the COMPLETE evidence an honest, fully-empowered surface would
    hold for the fixture: the neutralised signed test record rendered exactly
    like the frozen tier-A acceptance block, the issue-reproduction probe
    block, PLUS pre-adjudicated integrity verdicts (linkage / freshness /
    coverage), i.e. everything the E1 T3A-T active arm could obtain through
    tools, handed over at once.
  * Because every channel (P/L/F/C/O) is available and adjudicated in the
    bundle, the CEE gold label equals the frozen oracle gold. The CEE gold is
    nonetheless DERIVED INDEPENDENTLY from the signed record + attestation
    (never copied) and then asserted row-by-row equal to wave2 oracle_gold.

This module is ADDITIVE and read-only with respect to every frozen asset:
  * it imports the frozen decision semantics / record projection / fact
    derivation (ternary, views, visibility, prompts) but never mutates them;
  * all CEE outputs live in the independent ``evidence_store_cee`` namespace;
  * no Phase-1/2/3, Wave-2/2.1 or E1 file is ever written.

Design constraints honoured here (user decision, 2026-10-23):
  * reuse the existing 22 fixtures — NO new issues, NO selection based on
    observed model errors (the sample is the full pre-registered 22);
  * bundles separate sufficient_positive / decisive_negative / insufficient;
  * one provider-neutral JSON schema legal under BOTH OpenAI strict Structured
    Outputs and DeepSeek strict schema (ALL properties required — the frozen
    ternary schema omitted missing_evidence from `required`, which is why E1
    GPT needed json_object; CEE does not inherit that defect);
  * this file performs NO network and NO paid API call. A live runner is not
    even created in the offline phase.
"""
from __future__ import annotations

import hashlib
import json

from evidence.schemas import canonical_dumps
from evidence.ternary import TERNARY
from evidence.gold_w2 import oracle_gold as _w2_oracle_gold
from evidence.visibility import load_fixture_facts
from evidence.views import neutralize_fixture
from evidence import views
from evidence import prompts as _frozen_prompts

CEE_PROTOCOL_VERSION = 'cee-fixed-v1'
CEE_CONDITION = 'CEE-FIXED'

# Provider-neutral response schema. OpenAI strict Structured Outputs reject a
# schema whose `required` does not list every property; DeepSeek strict is
# lenient but accepts the strict-legal shape. Listing ALL properties makes the
# SAME strict schema valid for both providers — the P1 format-confound control.
CEE_GAP_ENUM = ['stale', 'linkage_mismatch', 'coverage_incomplete',
                'contradiction', 'unspecified', '']
CEE_DECISION_SCHEMA = {
    'name': 'cee_review_decision_v1', 'strict': True, 'schema': {
        'type': 'object',
        'properties': {
            'decision': {'type': 'string', 'enum': list(TERNARY)},
            'reason': {'type': 'string'},
            'evidence_mismatch': {'type': 'boolean'},
            'missing_evidence': {'type': 'string'},
            'evidence_gap': {'type': 'string', 'enum': CEE_GAP_ENUM},
        },
        'required': ['decision', 'reason', 'evidence_mismatch',
                     'missing_evidence', 'evidence_gap'],
        'additionalProperties': False,
    },
}

# Class labels for the three pre-registered evidence families.
CLASS_SUFFICIENT_POSITIVE = 'sufficient_positive'
CLASS_DECISIVE_NEGATIVE = 'decisive_negative'
CLASS_INSUFFICIENT = 'insufficient'

GOLD_TO_CLASS = {
    'ACCEPT': CLASS_SUFFICIENT_POSITIVE,
    'REJECT': CLASS_DECISIVE_NEGATIVE,
    'NEED_EVIDENCE': CLASS_INSUFFICIENT,
}

SYSTEM_MESSAGE = ('You are an independent code reviewer. Return a single JSON '
                  'object as your final message.')

# Decision-semantics text is REUSED from the frozen v1 ternary head (its last
# schema-instruction sentence is removed) so CEE cannot silently change the
# meaning of ACCEPT/REJECT/NEED_EVIDENCE. Only the fixed-evidence condition
# wording and the all-properties-required schema sentence are CEE-specific.
_SEMANTICS_BASE = _frozen_prompts.TERNARY_HEAD.split(
    '\nRespond with a single JSON object:')[0]

_FIXED_EVIDENCE_PARAGRAPH = (
    '\n\nFIXED-EVIDENCE CONDITION (CEE-FIXED): The evidence below is a COMPLETE, '
    'fixed bundle assembled for this review. It contains the signed test run '
    'record with the maintainer acceptance/regression outcomes, the '
    'issue-reproduction probe outcome, and integrity verdicts that have ALREADY '
    'been adjudicated over the signed record and the repository attestation: '
    'whether the record is linked to THIS patch/commit, whether it is fresh for '
    'the current commit tree, and whether the declared acceptance/regression '
    'set was fully executed. In this condition there are NO tools, NO further '
    'endpoints and NO escalation: you cannot fetch additional logs, re-run any '
    'check, or request more evidence. Make your decision solely from this '
    'bundle.\n'
    'Apply the same asymmetric standard: REJECT on a single credible, '
    'applicable (linked and fresh) failing check, even if coverage is '
    'incomplete; ACCEPT only when the bundle establishes linked, fresh, '
    'complete, failure-free success; otherwise NEED_EVIDENCE. Do not abstain '
    'when the bundle already lets you decide, and do not accept on a bundle '
    'that does not establish complete success. A missing/tool-only check that '
    'is already answered inside this bundle is NOT a reason to abstain.')

_CEE_SCHEMA_SENTENCE = (
    '\nRespond with a single JSON object containing exactly these keys: '
    '{"decision":"ACCEPT|REJECT|NEED_EVIDENCE","reason":"...",'
    '"evidence_mismatch":false,"missing_evidence":"",'
    '"evidence_gap":"stale|linkage_mismatch|coverage_incomplete|'
    'contradiction|unspecified|"}. Always include every key. Set '
    'missing_evidence and evidence_gap to "" unless the decision is '
    'NEED_EVIDENCE; for NEED_EVIDENCE choose exactly one non-empty '
    'evidence_gap that is directly supported by the bundle.')

# Gap taxonomy text: semantics identical to the frozen v2 _GAP_INSTRUCTION,
# re-pointed at the fixed bundle instead of authorised tools.
_CEE_GAP_TAXONOMY = (
    '\nEvidence-gap taxonomy when you answer "NEED_EVIDENCE": stale = the run '
    'is not fresh for the current commit tree; linkage_mismatch = the record '
    'does not link to THIS patch/commit; coverage_incomplete = the declared '
    'set was not fully executed; contradiction = bundle evidence conflicts '
    '(e.g. the issue symptom still reproduces or an applicable check fails '
    '— note such a contradiction on linked, fresh evidence is decisive '
    'grounds to REJECT, not to abstain); unspecified = you cannot name a '
    'concrete, bundle-supported gap. Report a gap only when it is directly '
    'supported by the fixed bundle; never invent one.')

CEE_HEAD = (_SEMANTICS_BASE + _FIXED_EVIDENCE_PARAGRAPH
            + _CEE_GAP_TAXONOMY + _CEE_SCHEMA_SENTENCE)

# Item-invariant goal, identical in meaning to the frozen ternary goal.
CEE_GOAL = _frozen_prompts._TERNARY_GOAL


def cee_prompt_fingerprint() -> str:
    """sha256 over the item-invariant CEE scaffolding: protocol version,
    system text, head (semantics + fixed-evidence wording + gap taxonomy +
    schema sentence) and goal. Issue/patch/bundle content is excluded."""
    blob = canonical_dumps({
        'version': CEE_PROTOCOL_VERSION,
        'condition': CEE_CONDITION,
        'system': SYSTEM_MESSAGE,
        'head': CEE_HEAD,
        'goal': CEE_GOAL,
        'schema': CEE_DECISION_SCHEMA,
        'tools': [],
    })
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Fixed evidence bundle rendering (deterministic; no label inputs)
# ---------------------------------------------------------------------------

def _yesno(v):
    if v is True:
        return 'yes'
    if v is False:
        return 'no'
    return 'n/a'


def _integrity_lines(facts: dict) -> list[str]:
    """Pre-adjudicated integrity verdicts — exactly the values the E1 T3A-T
    active arm obtained one tool call at a time (verify/freshness/coverage),
    presented as settled facts rather than as answer leakage (no ACCEPT/REJECT
    verdict is stated)."""
    return [
        'INTEGRITY VERDICTS (already adjudicated over the signed record and '
        'the repository attestation):',
        f"  record signature authentic: {_yesno(facts['authentic_signature'])}",
        f"  linked to THIS patch and base commit: {_yesno(facts['linked'])}",
        f"  fresh for the current commit tree: {_yesno(facts['fresh'])}",
        f"  declared acceptance/regression set fully executed: "
        f"{_yesno(facts['complete'])}",
    ]


def _probe_lines(symptom: dict | None) -> list[str]:
    """Issue-reproduction probe wording identical to the frozen
    views._diagnostic_block polarity convention (a passing probe means the
    symptom is GONE)."""
    if not isinstance(symptom, dict) or symptom.get('pre_patch_passed') is None \
            or symptom.get('post_patch_passed') is None:
        return ['ISSUE-REPRODUCTION PROBE: (not attached)']
    pre = symptom.get('pre_patch_passed')
    post = symptom.get('post_patch_passed')
    present_before = 'yes' if pre is False else 'no'
    reproduces_after = 'yes' if post is False else 'no'
    return [
        'ISSUE-REPRODUCTION PROBE (derived from the issue text, not the '
        'maintainer test suite; a passing probe means the symptom is GONE):',
        f'  issue symptom present before patch: {present_before}',
        f'  issue symptom reproduces after patch: {reproduces_after}',
    ]


def render_bundle_body(*, issue: str, patch: str, claim: str,
                       facts: dict, fx: dict) -> str:
    """Render the COMPLETE fixed evidence text for one fixture.

    `facts` is evidence.visibility.load_fixture_facts output for the SERVED
    artifact (oracle-side re-derivation; recomputed from signed record +
    attestation, never from labels). The signed record is neutralised exactly
    as in every frozen tier-A rendering (scenario-identifying strings removed)
    and rendered with the SAME acceptance-block function E1 uses; CEE then
    adds the probe and the pre-adjudicated integrity verdicts.
    """
    disp = neutralize_fixture(
        facts['artifact_record'], fx['instance_id'], fx['patch_sha256'],
        declared=None)
    sections: list[str] = []
    sections.append('FIXED EVIDENCE BUNDLE (protocol cee-fixed-v1).')
    sections.append(f"\n\nISSUE:\n{issue}")
    sections.append(f"\n\nPATCH:\n{patch}")
    sections.append(f"\n\nAUTHOR STATEMENT:\n{claim}")
    sections.append('\n\n' + views._acceptance_block(disp))
    sections.append('\n\n' + '\n'.join(_probe_lines(facts.get('symptom'))))
    sections.append('\n\n' + '\n'.join(_integrity_lines(facts)))
    return ''.join(sections)


def render_user_content(bundle_body: str) -> str:
    """The exact user-turn bytes both providers receive: item-invariant CEE
    head + goal, then the fixed bundle body."""
    return CEE_HEAD + CEE_GOAL + '\n\n' + bundle_body


def build_messages(user_content: str) -> list[dict]:
    return [{'role': 'system', 'content': SYSTEM_MESSAGE},
            {'role': 'user', 'content': user_content}]


# ---------------------------------------------------------------------------
# Independent CEE gold derivation (asserted equal to frozen oracle afterwards)
# ---------------------------------------------------------------------------

def derive_cee_gold_row(fx: dict, facts: dict) -> dict:
    """Derive the CEE gold from recomputed facts of the SERVED signed record
    plus the issue symptom probe, using the frozen Wave-2 DUAL-CHANNEL rule.

    The fixed bundle presents (a) the signed acceptance record with
    linked/fresh/complete adjudications and executed outcomes (acceptance
    channel O) and (b) the issue-derived symptom probe pre/post verdict
    (diagnostic channel P). Under complete information the supportable
    decision is the frozen ``gold_w2.oracle_gold`` rule:

        decisive failure  = (linked & fresh & acceptance_failure)
                            OR symptom_persists
        intact success    = linked & fresh & complete & acceptance_success
                            & not symptom_persists

    A target-patch symptom that still reproduces (P) is a decisive failure
    even when the served artifact is unlinked/stale — this is exactly why a
    single acceptance-channel rule would mislabel e.g. wrong_patch. This is
    an independent derivation from primary evidence; the builder
    cross-checks it against wave2_gold oracle_gold and refuses to proceed on
    any mismatch.
    """
    linked = bool(facts['linked'])
    fresh = bool(facts['fresh'])
    complete = bool(facts['complete'])
    failure = int(facts['executed_failure_count'])
    executed = int(facts['executed_check_count'])
    acceptance_failure = failure > 0
    acceptance_success = executed > 0 and failure == 0
    symptom_persists = facts.get('symptom_polarity') == 'persists'
    decisive_failure = (linked and fresh and acceptance_failure) \
        or symptom_persists
    sufficient_success = (linked and fresh and complete
                          and acceptance_success and not symptom_persists)
    decision = _w2_oracle_gold(
        linked=linked, fresh=fresh, complete=complete,
        acceptance_failure=acceptance_failure,
        acceptance_success=acceptance_success,
        symptom_persists=symptom_persists)
    return {
        'version': CEE_PROTOCOL_VERSION,
        'id': fx['id'],
        'instance_id': fx['instance_id'],
        'scenario': fx['scenario'],
        'served_artifact_id': fx['served_artifact_id'],
        'cee_gold': decision,
        'evidence_class': GOLD_TO_CLASS[decision],
        'facts': {
            'linked': linked,
            'fresh': fresh,
            'complete': complete,
            'executed_failure_count': failure,
            'executed_check_count': executed,
            'symptom_polarity': facts.get('symptom_polarity'),
        },
        'oracle_inputs': {
            'linked': linked,
            'fresh': fresh,
            'complete': complete,
            'acceptance_failure': acceptance_failure,
            'acceptance_success': acceptance_success,
            'symptom_persists': symptom_persists,
        },
        'decisive_failure': bool(decisive_failure),
        'sufficient_success': bool(sufficient_success),
    }
