"""CEE v1.1 - Controlled Evidence Experiment, UNIFIED JSON MODE.

This module is the protocol amendment approved in writing on 2026-10-24
("CEE v1.1 . Unified JSON Mode"). It is ADDITIVE: nothing from CEE v1
(cee-fixed-v1) or any Wave-2/2.1 / E1 frozen artifact is modified.

Why v1.1 exists
===============
CEE v1 requested one provider-neutral STRICT ``json_schema`` response_format
on both arms. On 2026-10-23 the live DeepSeek endpoint REJECTED that
response_format TYPE for every current model, including a 1-property minimal
schema (HTTP 400 "This response_format type is unavailable now"), while
OpenAI gpt-4.1-mini accepted the exact CEE schema. Evidence:
``evidence_store_cee/cee_compatibility_stop_report.json``. Per the v1
authorisation the run was hard-stopped and no downgrade was made.

The v1.1 amendment changes ONE wire-level control:

  * BOTH providers are now sent ``response_format = {"type": "json_object"}``.
  * No provider may use json_schema, and no arm may silently fall back to
    plain_text: the response_format type is IDENTICAL on the two arms.
  * The five-property ``cee_review_decision_v1`` schema is RETAINED VERBATIM
    as a LOCAL VALIDATION CONTRACT. json_object only forces "valid JSON"; it
    does not enforce the schema, so every response is validated locally for
    presence of all five keys, exact types, and legal enums. Any failure is
    scored INVALID (or AMBIGUOUS for the frozen multi-decision rule); fields
    are never auto-completed, coerced, or repaired, and a valid HTTP 200 is
    never retried to obtain a better answer.

Everything else is byte-identical to v1 by construction:

  * the 22 frozen Evidence Bundles are REUSED AS-IS (their bytes already embed
    the string "cee-fixed-v1" and the v1 prompt fingerprint; they are NOT
    rebuilt or re-rendered, so their on-disk sha256 is unchanged);
  * system/user prompt TEXT, evidence order and ternary semantics are the
    frozen cee_protocol text (it already tells both models to return one JSON
    object with exactly the five keys, so no new prompt wording is needed);
  * cee_gold.jsonl, the 7/6/9 classes and the scoring labels are unchanged.

The v1.1 fingerprint therefore covers the SAME prompt text PLUS the amended
output mode and the retained local contract, and is distinct from the v1
fingerprint. v1 and v1.1 are separate frozen experiments and must never be
pooled.

No network and no paid API call happen in this module.
"""
from __future__ import annotations

import hashlib
import json

from evidence.schemas import canonical_dumps
from evidence.ternary import parse_ternary_decision, TERNARY
from evidence import cee_protocol as v1

# ---------------------------------------------------------------------------
# Version identity
# ---------------------------------------------------------------------------
CEE_PROTOCOL_VERSION = 'cee-fixed-v1.1'
CEE_CONDITION = v1.CEE_CONDITION  # 'CEE-FIXED'

# The ONLY amended wire control. Both arms send this exact object.
RESPONSE_FORMAT_JSON_OBJECT = {'type': 'json_object'}
OUTPUT_MODE = 'unified_json_object_both_providers'
PREDECESSOR_VERSION = v1.CEE_PROTOCOL_VERSION  # 'cee-fixed-v1'
COMPATIBILITY_REPORT = 'cee_compatibility_stop_report.json'

# The five-property schema is RETAINED VERBATIM from v1 as the LOCAL contract.
CEE_DECISION_SCHEMA = v1.CEE_DECISION_SCHEMA  # name cee_review_decision_v1

# Identical prompt text / semantics as v1 (no wording change required).
SYSTEM_MESSAGE = v1.SYSTEM_MESSAGE
CEE_HEAD = v1.CEE_HEAD
CEE_GOAL = v1.CEE_GOAL

# Reuse v1 class taxonomy / labels unchanged.
CLASS_SUFFICIENT_POSITIVE = v1.CLASS_SUFFICIENT_POSITIVE
CLASS_DECISIVE_NEGATIVE = v1.CLASS_DECISIVE_NEGATIVE
CLASS_INSUFFICIENT = v1.CLASS_INSUFFICIENT
GOLD_TO_CLASS = v1.GOLD_TO_CLASS

REQUIRED_KEYS = ('decision', 'reason', 'evidence_mismatch',
                 'missing_evidence', 'evidence_gap')


def cee_prompt_fingerprint() -> str:
    """v1.1 item-invariant fingerprint.

    Covers the identical prompt text (system/head/goal), the unchanged five-
    property JSON CONTRACT, and the AMENDED output mode (json_object on both
    providers, no schema, no plain-text fallback). Bundle content is excluded
    just as in v1. This hash intentionally differs from the v1 fingerprint.
    """
    blob = canonical_dumps({
        'version': CEE_PROTOCOL_VERSION,
        'predecessor': PREDECESSOR_VERSION,
        'condition': CEE_CONDITION,
        'system': SYSTEM_MESSAGE,
        'head': CEE_HEAD,
        'goal': CEE_GOAL,
        'json_contract': CEE_DECISION_SCHEMA,
        'response_format': RESPONSE_FORMAT_JSON_OBJECT,
        'output_enforcement': 'local_schema_validation; no field repair',
        'tools': [],
        'turns': 1,
    })
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Local five-property validation (replaces server-side strict enforcement)
# ---------------------------------------------------------------------------
def validate_decision_object(content: str):
    """Strict LOCAL validation of one model response against the retained
    five-property contract.

    Returns ``(status, decision, reasons)`` where status is one of:
      'ok'         : a single object, all five keys present with exact
                     types/types and legal enums; `decision` is the normalised
                     ACCEPT/REJECT/NEED_EVIDENCE;
      'ambiguous'  : the frozen parser saw several conflicting decisions;
      'invalid'    : anything else (no JSON, >0/>1 objects, missing/extra
                     keys, wrong types, illegal enum, non-boolean mismatch...).

    No field is ever defaulted, coerced or repaired. Boolean/integral checks
    are strict (``isinstance``, not truthiness) and extra keys are rejected
    because the contract says additionalProperties=false.
    """
    reasons: list[str] = []
    if not isinstance(content, str):
        return 'invalid', None, ['response body is not a string']
    parsed = parse_ternary_decision(content)  # ACCEPT/REJECT/NEED/INVALID/AMBIG
    if parsed == 'AMBIGUOUS':
        return 'ambiguous', None, ['frozen parser: multiple conflicting '
                                   'decision candidates']
    if parsed == 'INVALID':
        return 'invalid', None, ['frozen parser: no parseable ternary decision']

    # Exactly one top-level JSON object is admissible.
    try:
        obj = json.loads(content)
        single = isinstance(obj, dict)
    except Exception:
        single = False
        obj = None
    if not single:
        # Fall back to the frozen candidate extractor so wrapped JSON gets the
        # same single-object treatment; >1 object is invalid.
        from evidence.ternary import extract_candidates
        cands = extract_candidates(content)
        if len(cands) != 1:
            return 'invalid', None, [f'expected exactly one JSON object, '
                                     f'found {len(cands)}']
        obj = cands[0]

    keys = set(obj.keys())
    missing = [k for k in REQUIRED_KEYS if k not in obj]
    extra = sorted(k for k in keys if k not in REQUIRED_KEYS)
    if missing:
        reasons.append('missing keys: ' + ','.join(missing))
    if extra:
        reasons.append('unexpected keys: ' + ','.join(extra))

    # decision: string, exact ternary enum (case-sensitive at contract level;
    # the frozen parser already normalised a legal value, so a lowercase value
    # that the parser accepted but the strict contract spells uppercase is
    # flagged as an enum violation rather than silently rewritten).
    dv = obj.get('decision')
    if 'decision' in obj:
        if not isinstance(dv, str) or dv not in TERNARY:
            reasons.append(f'decision not exact enum '
                           f'ACCEPT/REJECT/NEED_EVIDENCE: {dv!r}')
    # reason: string
    if 'reason' in obj and not isinstance(obj['reason'], str):
        reasons.append('reason is not a string')
    # evidence_mismatch: strict boolean
    if 'evidence_mismatch' in obj and not isinstance(
            obj['evidence_mismatch'], bool):
        reasons.append('evidence_mismatch is not a boolean')
    # missing_evidence: string
    if 'missing_evidence' in obj and not isinstance(
            obj['missing_evidence'], str):
        reasons.append('missing_evidence is not a string')
    # evidence_gap: string within the frozen enum (empty string allowed)
    if 'evidence_gap' in obj:
        gv = obj['evidence_gap']
        if not isinstance(gv, str) or gv not in v1.CEE_GAP_ENUM:
            reasons.append(f'evidence_gap not in contract enum: {gv!r}')

    if reasons:
        return 'invalid', None, reasons
    return 'ok', dv, []
