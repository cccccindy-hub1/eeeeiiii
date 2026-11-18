# G4 Addendum v1.1 — factor naming, WITHHELD semantics, diagnostic C/D, fixed-presentation-first

> This is a **versioned supplement** to `G4_PREREGISTRATION_v1.md`. It does NOT
> silently modify the original; where they differ, this addendum governs and
> the original is retained for history. Still **ZERO model calls / $0 / no new
> issues / no edits to frozen artifacts / no git commit**. Authorized in
> writing 2026-11-02 for the zero-cost identifiability gate only.

Version: `g4-sufficiency-iv-v1.1`

## A1. Rename the manipulated factor (scope precision)
The M factor is **Freshness/Coverage Attestation Availability**, NOT generic
"evidence integrity". Reasons:
- Linkage (L) is **held constant across all four cells**, never manipulated.
- The underlying test evidence is not altered; only whether the freshness and
  coverage **attestations (and their recomputable components)** are available
  to the reviewer is toggled.
All code fields, manifest labels, tables, and paper text MUST use the name
`fc_attestation` with levels `adjudicated` vs `withheld`. Avoid the phrase
"evidence integrity intervention."

## A2. WITHHELD is UNKNOWN, never FALSE
The neutralized level is semantic **UNKNOWN / WITHHELD**, explicitly not
freshness=false and not coverage=false:
- Neutralized F/C payloads set the verdict and every recomputable component to
  `null` and carry a fixed marker `"attestation": "withheld_on_this_surface"`.
- No word in any payload or prompt may state/imply "stale", "mismatched",
  "incomplete", "missing tests", or any negative F/C conclusion.
- A positive-length, matched neutral sentence replaces the adjudicated
  metadata paragraph so A/B (and C/D) differ in meaning, not merely in token
  volume.
- The system prompt must state three-valued semantics: an attestation that is
  not available is UNKNOWN — it neither supports nor refutes acceptance.

## A3. Identified estimand is narrower than "metadata in general"
All 18 frozen issues have fresh=true AND complete=true. Therefore the Pilot
identifies ONLY:
> *When freshness/coverage genuinely hold, does AVAILABILITY of their trusted
> attestations change unsupported-acceptance, with decisive outcomes blocked?*

It provides **no evidence** about model behavior when freshness=false or
coverage=false (that would need a separate, deliberately stale/incomplete
artifact arm, out of scope here). This limitation is mandatory in the paper.

## A4. C/D is a DIAGNOSTIC control, not a pass/fail identity assumption
Do not pre-assert C and D must be numerically identical. C/D (decisive outcomes
present) is a **diagnostic specificity control**: a small M-effect there is
expected/acceptable; a M-effect in C/D comparable to A/B suggests the toggle is
a non-specific plausibility/legibility shock. Reporting rule:
- Report |U(C)-U(D)| and overall oracle-match for C and D.
- A large comparable C/D effect is a **finding that weakens the construct**,
  surfaced transparently; it is not an automatic "run failed" and must not
  cause post-hoc rule changes. Interpretation scope is narrowed instead.

## A5. Fixed, content-controlled tool responses first round; separate the two effects
Any A/B/C/D difference can arise from (i) **information presentation** or (ii)
**tool interaction** (different calls/counts/order). The first round therefore
uses **pre-rendered, fixed, content-controlled tool responses**:
- Every cell serves the SAME ordered list of tool calls a reviewer can make and
  the SAME response ORDER; the only payload-content differences are O and the
  F/C attestation, exactly as registered.
- An **Interaction Parity** check (§A6) records tool call count, response
  order, and prompt-token length differences from the FIXED transcript design.
- If parity cannot be guaranteed in an interactive run, the confirmatory claim
  is limited to the **fixed evidence-presentation** intervention; we do NOT
  claim a pure tool-use causal effect.

## A6. Additional gate G6 — Interaction/Parity (beyond G1–G5)
G6 checks, from the frozen fixed transcripts (no model needed):
- G6.1 identical tool inventory across A/B/C/D;
- G6.2 identical fixed response sequence length/order for matched tools;
- G6.3 per-cell system+user token-length delta reported (char and whitespace
  tokenized estimate); A vs B and C vs D must be within a pre-set band
  (|Δchar| ≤ 8%) excluding the intentionally toggled payloads;
- G6.4 enumerate any residual interaction confound; if any cannot be removed,
  emit `claim_scope = fixed_presentation_only`.

## A7. Hard prohibitions for this zero-cost stage
- 0 model API calls; $0 new spend; no new issues; no edit to frozen G3
  artifacts/gold/paper; no git commit.
- Neutralization must not be implemented by setting booleans false or by
  fabricating stale/missing evidence.
- If G1–G6 fail: STOP paid preparation, report the failing strings and a
  MINIMAL offline repair. Do NOT touch Gold and do NOT drop hard issues to make
  the gate pass.

## A8. Deliverables (this stage)
`evidence_store_g4_sufficiency/`:
- this addendum (retained alongside the v1 preregistration);
- builder script (zero-API) + fixed transcript/payload hashes per issue×cell;
- `g4_cell_manifest.jsonl` (72 fixed evidence bundles → 144 model slots);
- `g4_identifiability_gate.json` / `.md` with G1–G6 per-cell findings, a
  per-issue×condition diff report, and an explicit **GO / NO-GO** recommendation;
- frozen H1 (two-sided), issue-paired exact McNemar, clustered bootstrap,
  order seed `G4_ORDER_SEED=20261102`, $2 total hard cap — unchangeable after
  any model output exists.

## A9. Decision rule after the gate (next, separate authorization)
- G1–G6 all PASS + interaction parity: eligible to request the 144-cell paid
  Pilot authorization.
- Any GATE FAIL: repair the manipulation offline first; no paid test.
- Gates pass but G6 interaction parity cannot hold: may still run a FIXED
  PRESENTATION experiment, with causal claims explicitly limited to that
  presentation intervention.
