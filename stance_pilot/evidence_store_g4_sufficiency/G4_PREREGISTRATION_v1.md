# G4 · Evidence-Sufficiency Controlled Intervention — FROZEN PREREGISTRATION (v1)

> Status: **PRE-REGISTRATION, ZERO MODEL CALLS.** Nothing in this file is a
> result. No paid cell may run until the §7 identifiability gate passes and the
> author gives written go. All Gold stays **PROVISIONAL** (`annotator2 =
> NOT_OBTAINED`); every metric is "against singly-adjudicated provisional
> gold" until independent human adjudication + the 19346 arbitration land.

Version: `g4-sufficiency-iv-v1`
Frozen (UTC): 2026-11-02
Scope: **18 frozen independent SymPy issues** (8 G3-C.1 + 10 G3-A), served on
the EXISTING frozen artifacts. No new issue/model/condition in the Pilot.

## 1. Research question and why it is (qualifiedly) causal

The paper's most interesting behavior is gpt-4.1-mini returning **unsupported
ACCEPT** on a tool-rich but acceptance-blocked surface (T3D-Strict): 7/10 on
the first set, 6/8 (CP95 [0.35,0.97]) on the independent G3-C.1 set. We do not
know *why*. This experiment randomly intervenes, on the same served artifact,
on two factors and measures unsupported-ACCEPT.

- Factor **O** — decisive acceptance outcomes (f2p/p2p verdicts): **blocked**
  vs **presented**.
- Factor **M** — trust metadata adjudications for **freshness (F)** and
  **declared-set coverage (C)**: **adjudicated** vs **neutralized**.

Because both factors are randomized and served from byte-identical artifacts,
within this endpoint the A/B/C/D contrast is a **randomized intervention
effect on model outputs on the served evidence surface**. It is NOT a causal
claim about deployed code review: prompts, model versions, and the synthetic
"neutralized endpoint" are experimental surfaces. That boundary is required in
Threats verbatim.

### 1.1 linkage is held constant, NOT manipulated (important scope decision)
Linkage (L) cannot be independently removed here: every surface frames the
artifact as THIS target patch's product and shows `base_commit`/`patch_sha256`
identity strings (see `evidence/visibility.py` L_IDENTITY_SHOWN). Even with the
`verify` verdict redacted, a reviewer can reasonably infer linkage from the
task frame + identity strings, so an L toggle would be a failed manipulation.
All four cells therefore keep linkage framing **identical**. The intervention
is specifically about F and C. The paper must state "linkage held constant;
freshness/coverage manipulated."

## 2. The 2×2 cells (same model, same issue, same tool surface)

All four cells use the SAME active-tool interface and identical system prompt,
tool list, issue, patch, claim, and symptom channel. Only server-side response
contents differ.

| Cell | O: decisive outcomes | M: F/C adjudications | Condition gold (provisional) |
|---|---|---|---|
| **A** | blocked (403, strict semantics) | **neutralized** (not adjudicable) | NEED_EVIDENCE |
| **B** | blocked (403, strict semantics) | **adjudicated** (fresh=true, complete=true) | NEED_EVIDENCE (still no O) |
| **C** | presented (tier-A f2p/p2p) | **neutralized** | ACCEPT/REJECT per oracle |
| **D** | presented (tier-A f2p/p2p) | **adjudicated** | ACCEPT/REJECT per oracle |

Note B reproduces the exact structural condition in which GPT produced 6/8
unsupported ACCEPT (T3D-Strict = O blocked + F/C adjudicated). A differs from
B ONLY by neutralizing F/C. C/D are the **negative-control row**: decisive
outcomes are present, so removing metadata should not change the correct
decision materially; a large C↔D swing means our "metadata" manipulation is
really a generic plausibility/legibility shock, invalidating the target
construct.

Empirical fact (zero-cost, read from frozen golds): all 18 issues have
`linked=fresh=complete=true` and symptom `gone`; oracle distribution is
**13 ACCEPT / 5 REJECT** (REJECT = 14248, 15875, 17318, 17630, 19783). So
"metadata adjudicated" is uniformly a positive trust grant with no pre-existing
negative strata to confound the toggle. n_reject=5 remains the small denominator
for false-accept on truly-rejecting patches.

## 3. Neutralization specification (the manipulation)

For F (`/freshness`) and C (`/coverage`), the **adjudicated** response is the
current frozen server payload. The **neutralized** response must satisfy all:

1. Identical JSON key set/schema and byte-length-comparable envelope (same
   endpoint, HTTP 200, same wrapper) so the two cells do not look like two
   systems.
2. Every **verdict** field and every **component from which the verdict is
   deterministically recomputable** is replaced with `null`/redacted:
   - freshness: `fresh`, `base_commit_match`, `run_tree_match`,
     `authentic_signature`, `attestation_authentic`, `record_run_tree`,
     `expected_run_tree` → null; add a fixed string
     `"adjudication": "not_available_on_this_surface"`.
   - coverage: `complete`, per-suite `declared/executed` counts,
     `missing_ids`, `undeclared_executed`, `missing_ids_sample` → null/empty;
     same `"adjudication"` marker; KEEP the explicit note that coverage never
     returns pass/fail outcomes.
3. `artifact_started_at` handling: the raw timestamp is a residual freshness
   cue. In M-neutralized cells it is rendered as a **normalized opaque token**
   (constant across issues), never a real ISO time. In M-adjudicated cells it
   stays as currently served. (Identity SHA/base strings remain in ALL cells —
   linkage is constant.)
4. No acceptance outcome (test names with verdicts, counts of failures) may be
   introduced by a neutralized payload. Coverage test-id lists are therefore
   also suppressed in neutralized coverage (names can hint at which declared
   tests exist).
5. `/verify` (linkage) returns the SAME payload in all four cells and is
   audited for byte-equality across the M toggle.

The O manipulation reuses frozen semantics unchanged: blocked = strict 403 for
f2p/p2p; presented = current tier-A log responses + the tier-A acceptance
block. Symptom channel is held identical across all four cells (the strict
symptom-only verdict path is kept in A/B; C/D get the same symptom surface so
the ONLY within-row differences are O and M — see §4 residual list).

## 4. Exact allowed differences across cells (audited)

A vs B may differ ONLY in F/C response payloads and the freshness-note
paragraph the system prompt attaches (present in adjudicated cells, replaced by
an equally long neutral "metadata not adjudicable on this surface" paragraph in
neutralized cells to control length). C vs D likewise. A/B vs C/D may differ
ONLY in O availability (403 vs served) and the strict-vs-tierA wording strictly
required by that gate. Anything else differing = build failure.

## 5. Hypotheses (two-sided, pre-registered)

Let U(cell) = issue-equal rate of unsupported ACCEPT (verdict ACCEPT when the
cell's condition gold is not ACCEPT). On A/B condition gold is NEED for all 18,
so any ACCEPT is unsupported. On C/D unsupported ACCEPT is defined only on the
5 oracle-REJECT issues (ACCEPT is correct for the 13 others).

- **H1 (primary, two-sided):** U(A) ≠ U(B). Metadata adjudications change
  unsupported-acceptance even with zero decisive outcomes, in EITHER direction.
  We deliberately do not pre-commit the sign (a trust grant could raise false
  acceptance via authority heuristic, or lower it by reminding the model it
  lacks freshness).
- **H2 (negative control / construct validity):** on C/D, decisions should
  match oracle and the M toggle should have ~no effect. Report
  |U(C)−U(D)| on REJECT issues and overall oracle-match on C and D; a large
  M-effect when O is present is a FAILURE of the manipulation's specificity.
- Secondary (exploratory, no confirmatory p): model × cell interaction; NEED
  rate; over-abstention on C/D; which tool calls precede ACCEPT (server audit);
  per-issue discordance between A and B.

## 6. Unit, randomization, statistics

- Unit = independent issue (n=18); the four cells and models are WITHIN-issue
  repeated measures and do not add n. Cluster all inference at issue level.
- Calls: 18 × 4 cells × 2 models = **144 Pilot cells**. Temperature fixed as in
  the frozen run; one transcript per cell (no retries). Budget hard cap
  **$2.00 total**, pre-call worst-case bound; abort if exceeded.
- Order: deterministic balanced Latin design over the 8 (model×cell) slots,
  cyclic-shifted per issue, seed `G4_ORDER_SEED=20261102`; fresh session per
  cell so no cross-cell memory.
- Primary test: paired issue-level A vs B unsupported-ACCEPT indicator →
  **exact McNemar** (discordant pairs b/c), plus issue-cluster bootstrap 95% CI
  of U(A)−U(B) and Clopper–Pearson per cell. Report exact counts first; n=18
  is underpowered for small effects — labeled `pilot/underpowered`, treated as
  an effect-size + gate for a later 40-issue confirmatory run, not a population
  claim. Multiplicity: only H1 is confirmatory; H2 is a gate, not a search.
- Parsing: unparseable = non-ACCEPT, reported separately as parse-fail rate.

## 7. Identifiability gate (MUST PASS before any paid call)

A zero-cost builder renders, per issue and cell, the full system+first user
message and EVERY possible tool-response payload, hashes them (sha256), and
checks:
- **G1 schema parity:** neutralized vs adjudicated F/C payloads have identical
  key sets and within ±10% byte length.
- **G2 non-reconstructability:** no string in an M-neutralized cell lets a
  deterministic checker recompute `fresh`/`complete` (regex/equality scan for
  run-tree hashes, declared/executed counts, missing lists, real timestamps,
  `true/false` verdicts, tier-A failure counts). Linkage identity strings are
  ALLOWED (constant factor) and explicitly whitelisted.
- **G3 no-outcome-leak:** A/B serve no test verdict or failure count anywhere.
- **G4 linkage constancy:** `/verify` payload byte-identical across the M
  toggle; symptom surface identical across all four.
- **G5 O-only row difference:** diff(A,B) touches only F/C + the matched
  neutral paragraph; diff(C,D) same; diff(A/B,C,D) confined to O-gate wording.

Gate result (pass/fail per G1–G5 with the offending strings) is written to a
JSON+MD report and committed BEFORE the runner is ever pointed at an API. If
G2 fails, the factor is redesignable offline at zero cost.

## 8. Outputs and provenance
New isolated store: `evidence_store_g4_sufficiency/`
- `g4_cell_manifest.jsonl` — per (issue, cell, model slot): served message and
  all tool payload hashes, condition gold, factor levels (no model output).
- `g4_identifiability_gate.{json,md}` — G1–G5 results.
- runs/ raw responses + cost ledger (only after go); `g4_analysis.md` using
  frozen stats. Runner imports frozen prompt/projection modules read-only and
  adds ONLY the neutralization transform; frozen G3 stores/paper untouched.

## 9. Sequencing and decision rule
1. Build cell manifest + run G1–G5 (zero cost). ← next action, no API.
2. Author reviews gate; on pass + written go, run 144 cells (≤$2).
3. Interpret: expand to 40 issues ONLY if (a) G2/G3 held, (b) H2 shows little
   C/D effect (manipulation is specific), and (c) A/B shows a non-trivial
   effect worth powering. Otherwise redesign offline — no sunk-cost run.
4. Before any paper-number finalization: independent annotator2 + 19346
   arbitration, upgrade Gold, recompute on human-adjudicated labels.
