# GroundedReview — Independent Human Annotator Protocol
## Gate G3-C.1 local pilot (8 new issues)

## Role and independence
You are annotator #2, independent of the model pipeline.
Do not use any LLM and do not consult the pipeline author;
your label must be your own reading of the frozen CI.

## Decision rubric
1. ACCEPT: every declared FAIL_TO_PASS test transitions fail(at base) -> pass(after patch) AND no declared in-scope PASS_TO_PASS test regresses (passed/xfail/skipped at base, bad after patch). SCOPED acceptability: only the attested scoped P2P subset was executed locally; the full dataset P2P suite was not run for this pilot.
2. REJECT: the executed CI shows at least one decisive, APPLICABLE failure: a declared F2P still fails after the patch, OR a scoped P2P regression is present. Separate genuine failures from environment/pre-existing fails (bad at base too -> not a regression) and from xfail/flaky/self-added-test traps; justify applicability in the reason field.
3. NEEDS_REVIEW: genuinely undecidable from the supplied evidence (ambiguous applicability, uninterpretable log, suspected flake). Do not force ACCEPT/REJECT.

## Procedure
1. Work packets P01..P08 in folder order; do not infer identity.
2. Read 01-04, then compare after-patch logs (05-06) to the base log (07).
3. Record the exact decisive failing test id(s) and applicability.
4. Mark NEEDS_REVIEW rather than guessing.

## Disagreement and adjudication
- Raw agreement and Cohen kappa are computed against annotator #1 after unsealing.
- Any ACCEPT/REJECT mismatch, or any NEEDS_REVIEW, goes to a THIRD senior human arbiter who sees both labels but no model output.
- Every changed label keeps annotator1/annotator2/arbiter labels and the reason; labels are never silently overridden.

## Status
PENDING: no independent human labels exist yet. Gold remains PROVISIONAL until labels + arbitration are returned.
