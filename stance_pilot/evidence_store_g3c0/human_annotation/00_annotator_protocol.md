# GroundedReview — Independent Human Annotator Protocol

## Role and independence
You are annotator #2, independent of the model pipeline.
Do not use any LLM and do not consult the pipeline author;
your label must be your own reading of the frozen CI.

## Decision rubric
1. ACCEPT: every declared FAIL_TO_PASS test transitions fail(at base) -> pass(after patch) AND no declared in-scope PASS_TO_PASS test regresses (passed/xfail/skipped at base, bad after patch). SCOPED acceptability: only the attested scoped P2P subset was executed.
2. REJECT: the frozen CI shows at least one decisive, APPLICABLE failure: a declared F2P still fails after the patch, OR a scoped P2P regression is present. Distinguish genuine failures from environment/pre-existing fails (bad at base too -> not a regression) and from xfail/flaky/self-added-test traps; justify applicability in the reason field.
3. NEEDS_REVIEW: the packet is genuinely undecidable from the supplied evidence (ambiguous applicability, uninterpretable log, suspected flake that cannot be resolved). Do not force ACCEPT/REJECT.

## Procedure
1. Work packets P01..P10 in folder order; do not try to infer the issue identity.
2. Read 01-04, then compare the after-patch logs (05-06) against the base-commit log (07).
3. Record the exact decisive failing test id(s) and why they apply.
4. Mark NEEDS_REVIEW rather than guessing.

## Disagreement and adjudication
- Raw agreement and Cohen kappa are computed against annotator #1 after unsealing.
- Any ACCEPT/REJECT mismatch, or any NEEDS_REVIEW, goes to a THIRD senior human arbiter who sees both labels but no model output; the arbiter writes a reason and the final label.
- Every changed label keeps annotator1/annotator2/arbiter labels and the reason; labels are never silently overridden.

## Gold-flip sensitivity (performed by the study, not you)
All headline rates are recomputed under annotator1, annotator2 and adjudicated labels, with leave-one-issue-out and bounds over plausible adjudications; a claim is "robust" only if its sign holds across all three.

## Status
PENDING: no independent human labels exist yet. This protocol and the packets are prepared but un-adjudicated; gold remains PROVISIONAL until labels + arbitration are returned.
