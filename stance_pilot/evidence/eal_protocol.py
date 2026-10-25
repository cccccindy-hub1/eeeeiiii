"""GroundedReview v2 — Evidence Abstraction Ladder (EAL), offline protocol.

Version identity: ``eal-v0-draft1`` (offline design/prototype only; no live
runner is created in this phase, zero network / zero paid API calls).

Why EAL exists
==============
The Task-20 construct-validity audit of CEE v1.1 found that the 22 fixed
bundles never state the gold label, but on 22/22 bundles the gold is
mechanically recomputable from the rendered *adjudication booleans*
(linked / fresh / complete / symptom present-before / reproduces-after) plus
the decision rule printed in the prompt head. CEE therefore measures

    Policy Execution over Pre-Adjudicated Evidence

and not the middle construct that is currently missing from GroundedReview:

    Layer 2 — Evidence Grounding: deciding, from primary records, which
    facts are trustworthy, applicable to THIS patch, current, complete,
    and what the raw probe/test outputs actually say.

EAL presents the SAME review item (issue, patch, actual executed facts,
gold) at three evidence-abstraction levels. Only the abstraction of the
evidence changes; the decision policy, the response contract, the author
statement, the issue/patch text and the review target are held constant.

  RAW          Primary, auditable records only: the signed run record as
               neutralised JSON, the separately-signed repository
               attestation as JSON, the verbatim (host-path-redacted)
               f2p / p2p / p2p_baseline / symptom runner logs with exit
               codes and digests, and — when the archive retained it —
               the issue-symptom probe source. No verdict of any kind is
               stated; the reviewer performs every comparison itself.

  STRUCTURED   The same primary facts parsed into deterministic tables:
               target vs record identity hashes, record run tree vs the
               attested expected tree, declared vs executed test sets,
               per-test post/base status transitions, parsed pre/post
               probe exit codes and assertion lines. Nothing is removed
               relative to RAW; verbatim logs are replaced BY their
               lossless parse. The adjudication booleans
               linked / fresh / complete / symptom_persists are NOT
               present in any form (no yes/no, no synonyms).

  ADJUDICATED  The frozen CEE v1.1 bundle: tier-A acceptance block,
               two probe booleans, four pre-adjudicated integrity
               verdicts. Reused byte-for-byte via cee_protocol; it is the
               Layer-3 Policy-Execution control arm.

Information-equivalence discipline (user requirement 4/5): a verdict may be
removed from RAW/STRUCTURED only if every operand needed to recompute it is
present in that same layer. The replacement map is:

  linked             target base_commit+patch_sha256  vs  record's own
  (authenticity is a constant channel premise: every served record/log is
  pre-verified through the repository integrity service; the HMAC secret is
  not a reviewer-accessible object in ANY layer)
  fresh              record.run_tree  vs  attestation.expected_run_tree
                     (+ base_commit match + attestation identity)
  complete           attestation.declared_{fail_to_pass,p2p_scoped}
                     vs  the set of per-test keys actually executed
  acceptance result  per-test status maps (f2p; scoped p2p) + the
                     base-commit baseline map that lets the reviewer itself
                     distinguish a regression from a pre-existing failure
  symptom_persists   pre/post probe runner logs (RAW) or parsed pre/post
                     probe exit codes + assertion lines (STRUCTURED)

Per-layer gold is derived FROM THE LAYER'S OWN VISIBLE MATERIALS, never
forced equal. When a layer lacks the operands for a channel (e.g. a future
issue whose attestation was not retained), the gold for that layer is
marked ``gold_underdetermined`` with the missing channels; a decision that
is invariant to the unknown facts (e.g. REJECT on a fully-supported
persisting symptom regardless of coverage) stays determined.

This module is ADDITIVE and read-only with respect to every frozen asset:
it imports frozen modules but mutates nothing, and writes only into the
independent ``evidence_store_eal`` namespace.
"""
from __future__ import annotations

import hashlib
import itertools

from evidence.schemas import canonical_dumps
from evidence import cee_protocol as cee
from evidence import prompts as _frozen_prompts

EAL_PROTOCOL_VERSION = 'eal-v0-draft1'
LAYERS = ('raw', 'structured', 'adjudicated')
LAYER_TITLES = {
    'raw': 'RAW',
    'structured': 'STRUCTURED',
    'adjudicated': 'ADJUDICATED',
}

# The asymmetric decision semantics are the FROZEN ternary semantics (the
# same base CEE uses). EAL never rewords what ACCEPT/REJECT/NEED_EVIDENCE
# mean; only the evidence-abstraction framing changes.
SEMANTICS_BASE = _frozen_prompts.TERNARY_HEAD.split(
    '\nRespond with a single JSON object:')[0]
SYSTEM_MESSAGE = cee.SYSTEM_MESSAGE
REVIEW_GOAL = cee.CEE_GOAL

# The five-property contract is the frozen CEE contract verbatim, so output
# parsing/scoring is identical across CEE and every EAL layer.
DECISION_SCHEMA = cee.CEE_DECISION_SCHEMA
GAP_ENUM = cee.CEE_GAP_ENUM

_SCHEMA_SENTENCE = (
    '\nRespond with a single JSON object containing exactly these keys: '
    '{"decision":"ACCEPT|REJECT|NEED_EVIDENCE","reason":"...",'
    '"evidence_mismatch":false,"missing_evidence":"",'
    '"evidence_gap":"stale|linkage_mismatch|coverage_incomplete|'
    'contradiction|unspecified|"}. Always include every key. Set '
    'missing_evidence and evidence_gap to "" unless the decision is '
    'NEED_EVIDENCE; for NEED_EVIDENCE choose exactly one non-empty '
    'evidence_gap directly supported by the materials in this condition.')

# Stated identically in every layer (true for every served bundle: the
# offline build refuses inauthentic records and verifies every log digest).
# HMAC authenticity is therefore a constant channel premise, not a task —
# without the server secret no reviewer could recompute it at any layer.
_INTEGRITY_PREMISE = (
    '\n\nCHANNEL INTEGRITY (identical in every condition of this study): '
    'every run record below was served through the repository integrity '
    'service: its HMAC signature was verified before you received it, and '
    'every attached log hashes to the digest recorded in that signed '
    'record. Treat record/log authenticity and log-to-record binding as '
    'established. What is NOT established for you in advance is whether an '
    'authentic record actually applies to THIS patch and its current '
    'commit tree, whether its run covered the declared acceptance set, and '
    'what the raw runs show. Those judgments are yours to make from the '
    'materials provided.')

_GAP_TAXONOMY = cee._CEE_GAP_TAXONOMY.replace('fixed bundle', 'materials')

# ---------------------------------------------------------------------------
# Layer-specific framing (decision semantics identical; framing differs)
# ---------------------------------------------------------------------------

_RAW_PARAGRAPH = (
    '\n\nRAW-EVIDENCE CONDITION: you receive primary records only. Nothing '
    'is pre-adjudicated. The TARGET block names the patch under review. '
    'The ATTESTATION is the maintainers’ separately-signed declaration of '
    'the canonical run tree and the declared acceptance/regression sets. '
    'The RUN RECORD is the CI runner’s signed record of what actually ran '
    '(identity hashes, run tree, scope, per-test status maps, aggregated '
    'summary, log digests). The RUNNER LOGS are the verbatim commands, '
    'exit codes and stdout/stderr (host-local paths redacted; each '
    'redacted log is shown with its original digest so the redaction is '
    'auditable). You must yourself: (1) compare the record identity '
    'hashes against the TARGET; (2) compare the record run tree against '
    'the attested expected run tree; (3) compare the declared test sets '
    'against the per-test entries that actually executed; (4) determine '
    'acceptance and regression outcomes from the per-test statuses and '
    'the base-commit baseline (a check failing already at the base '
    'commit is recorded in the baseline map); (5) read the pre/post '
    'symptom-probe logs to determine whether the reported symptom is '
    'present before and after the patch. There are no tools and no '
    'further endpoints; decide solely from these materials.')

_STRUCTURED_PARAGRAPH = (
    '\n\nSTRUCTURED-EVIDENCE CONDITION: the same primary records have been '
    'parsed into deterministic tables. No integrity or applicability '
    'verdict is supplied: there is no linked/fresh/complete indicator and '
    'no symptom verdict. The tables show both operands of every '
    'comparison side by side — TARGET vs record identity, record run tree '
    'vs attested expected tree, declared vs executed test sets, each '
    'check’s post-patch and base-commit status, and the parsed pre/post '
    'probe exit codes and assertion lines. Perform the comparisons '
    'yourself and apply the asymmetric standard. No information present '
    'in the raw records has been discarded; verbatim log prose was '
    'replaced by these tables. There are no tools and no further '
    'endpoints; decide solely from these tables.')

_ADJ_PARAGRAPH = cee._FIXED_EVIDENCE_PARAGRAPH

LAYER_PARAGRAPHS = {
    'raw': _RAW_PARAGRAPH,
    'structured': _STRUCTURED_PARAGRAPH,
    'adjudicated': _ADJ_PARAGRAPH,
}


def layer_head(layer: str) -> str:
    """Item-invariant scaffolding for one layer."""
    if layer == 'adjudicated':
        # Byte-identical to the frozen CEE v1.1 head (it already is
        # SEMANTICS_BASE + fixed-evidence paragraph + gap taxonomy + schema
        # sentence); reuse it so ADJUCATED == CEE by construction.
        return cee.CEE_HEAD
    return (SEMANTICS_BASE + _INTEGRITY_PREMISE + LAYER_PARAGRAPHS[layer]
            + _GAP_TAXONOMY + _SCHEMA_SENTENCE)


def layer_prompt_fingerprint(layer: str) -> str:
    blob = canonical_dumps({
        'version': EAL_PROTOCOL_VERSION,
        'layer': layer,
        'system': SYSTEM_MESSAGE,
        'head': layer_head(layer),
        'goal': REVIEW_GOAL,
        'schema': DECISION_SCHEMA,
        'tools': [],
        'turns': 1,
    })
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def render_user_content(layer: str, body: str) -> str:
    if layer == 'adjudicated':
        return cee.render_user_content(body)
    return layer_head(layer) + REVIEW_GOAL + '\n\n' + body


def build_messages(layer: str, user_content: str) -> list[dict]:
    return [{'role': 'system', 'content': SYSTEM_MESSAGE},
            {'role': 'user', 'content': user_content}]


# ---------------------------------------------------------------------------
# Per-layer gold: derive from the layer's OWN visible materials.
# Facts may be None (channel operands absent at that layer).
# ---------------------------------------------------------------------------

# Channel -> verdict operands (documentation + audit hooks).
VERDICT_OPERANDS = {
    'signature_authentic': ('constant channel premise (pre-verified HMAC); '
                            'not a task at any layer'),
    'linked': 'TARGET.base_commit/patch_sha256 vs RUN_RECORD same fields',
    'fresh': 'RUN_RECORD.run_tree vs ATTESTATION.expected_run_tree '
             '(+ base match + attestation identity)',
    'complete': 'ATTESTATION.declared sets vs executed per-test key sets',
    'acceptance_failure': 'f2p per-test FAILED statuses; p2p post-FAILED '
                          'with non-FAILED base status (baseline map)',
    'symptom_persists': 'probe pre exit/output and post exit/output '
                        '(raw logs or parsed probe table)',
}


def gold_from_facts(*, linked, fresh, complete, acceptance_failure,
                    acceptance_success, symptom_persists):
    """Frozen oracle rule over facts that may be None (unknown).

    Returns (decision_or_None, determined, decisive_unknowns). When the
    facts admit more than one label across the unknown channels, returns
    (None, False, [channels that would have to be resolved]).
    """
    names = ('linked', 'fresh', 'complete', 'acceptance_failure',
             'acceptance_success', 'symptom_persists')
    vals = dict(linked=linked, fresh=fresh, complete=complete,
                acceptance_failure=acceptance_failure,
                acceptance_success=acceptance_success,
                symptom_persists=symptom_persists)
    unknown = [n for n in names if vals[n] is None]
    choices = {n: ([False, True] if n in ('linked', 'fresh', 'complete',
                                          'symptom_persists')
                   else [False, True])
               for n in unknown}
    labels = set()
    for combo in itertools.product(*([choices[n] for n in unknown])):
        v = dict(vals)
        v.update(dict(zip(unknown, combo)))
        labels.add(_oracle(**v))
    if len(labels) == 1:
        lab = next(iter(labels))
        return lab, True, []
    return None, False, unknown


def _oracle(*, linked, fresh, complete, acceptance_failure,
            acceptance_success, symptom_persists):
    decisive_failure = (bool(linked) and bool(fresh)
                        and bool(acceptance_failure)) \
        or bool(symptom_persists)
    intact_success = (bool(linked) and bool(fresh) and bool(complete)
                      and bool(acceptance_success)
                      and not bool(symptom_persists))
    if decisive_failure:
        return 'REJECT'
    if intact_success:
        return 'ACCEPT'
    return 'NEED_EVIDENCE'
