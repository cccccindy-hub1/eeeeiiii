# GroundedReview v2 / EAL — Gate 1 Report (Offline Runner & Construct Validation)

- Protocol: `eal-v0-draft1` (frozen at Gate 0)
- Scope: 2 models × 22 fixtures × 3 layers = **132 cells**, offline Mock only
- Spend: **$0.0000**, zero network model calls, zero new issues, zero frozen-data edits, no git commit
- Engineering self-check: **20/20 gates PASS** (`eal_gate1_selftest_report.json`)
- Status: Gate 1 work complete; **stopped pending written Gate 2 approval**

Artifacts (all under `stance_pilot/evidence_store_eal/`, nothing outside it):

| artifact | content |
| --- | --- |
| `gate1_runs/eal_gate1_mock_*_results.jsonl` | 66 terminal rows per model (raw response retained before parse) |
| `gate1_runs/eal_gate1_run_audit.json` | run envelope, caps, byte-identity assertion |
| `eal_sufficiency_certificates.json`, `eal_sufficiency_summary.md` | 22 per-fixture Evidence Sufficiency Certificates |
| `eal_gate1_length_position_audit.json` | tokens, evidence offsets, truncation flags, served-byte leak scan |
| `eal_gate1_selftest_report.json` | 20 engineering gates |

New code is `eal_`-prefixed only: `eal_run.py`, `eal_sufficiency.py`,
`eal_gate1_audit.py`, `eal_gate1_selftest.py`. It imports frozen E1/CEE/EAL
modules read-only and never writes outside `evidence_store_eal/`.

---

## 1. Construct-validity headline (the question Gate 1 existed to answer)

**All 22 fixtures are gold-determined in all three layers; no layer is
information-unsufficient.** `n_underdetermined_any_primary_layer = 0`.

That means the primary estimand

> Δ_Grounding = DA_Adjudicated − DA_Raw

will, on this fixture set, compare reviewers who hold the **same decision-
forcing information at different abstraction levels**, rather than comparing
an informed arm against a starved arm. The "missing information" alternative
explanation is excluded for the forcing operands. Two residual qualifications
remain (§3, §6): some forcing operands reach RAW/STRUCTURED through a
**runner-produced summary** rather than primary per-test bytes (a mild
pre-abstraction), and probe-to-issue fidelity cannot be re-derived from
archived probe **source** in 13 fixtures (the probe **output**, which is the
actual decision operand, is present in all 22).

## 2. 132-cell offline Mock run

Deterministic local Mock backend (no network); two failure cells are injected
by design to prove the validation/retention path end to end:

- cell #10 → non-JSON body → local validator returns **INVALID**
- cell #20 → two JSON objects in one body → **AMBIGUOUS**

Per model (identical for both arms, as expected from a deterministic mock):

| parsed outcome | rows |
| --- | --- |
| ACCEPT | 20 |
| REJECT | 18 |
| NEED_EVIDENCE | 26 |
| INVALID (injected) | 1 |
| AMBIGUOUS (injected) | 1 |

- 64 scored rows match the layer oracle; the 2 injected rows are retained as
  failures (`appropriate=false`, `error_label invalid/ambiguous`), never
  repaired or retried — a 200 with INVALID/AMBIGUOUS is a terminal state.
- `api_error = 0`; `spend = $0`; `tools_sent = 0`; `plain_text_fallback = false`.
- Resume idempotency verified: a second invocation writes **0 rows** (done-set
  keys on `(bundle_id, layer)` with no api_error).
- Mock results validate the **pipeline only**; they carry no information about
  real model capability. `model_served` is recorded with a `mock-` prefix and
  `served_matches_e1_model=false`, so no false identity with a served weight is
  claimed.

Every parseable row persists: `raw_response_text` (written **before**
parsing), `raw_content_sha256`, `reason_verbatim`,
`missing_evidence_verbatim`, `evidence_gap_verbatim`, estimated in/out
tokens, wall latency, served model id, validation errors, payload sha and
prompt fingerprint. No reason or missing_evidence string is empty on the
rows where the schema requires one.

## 3. Evidence Sufficiency Certificates (22 fixtures)

Method (`eal_sufficiency.py`): over the six decision channels
(linked, fresh, complete, acceptance_failure, acceptance_success,
symptom_persists), enumerate channel subsets by size; a subset is the
**minimal forcing set** when fixing its recovered operands forces the frozen
gold for **every** assignment of the remaining channels. Each forcing channel
is then checked for primary-material availability independently in RAW,
STRUCTURED and ADJUDICATED.

Minimal-forcing-set profile across the 22 fixtures:

| forcing channels | n fixtures |
| --- | --- |
| all six (only the full conjunction forces ACCEPT) | 7 |
| linked + fresh + acceptance_failure (REJECT) | 4 |
| fresh + symptom_persists (NEED) | 5 |
| complete + acceptance_failure + symptom_persists (NEED) | 3 |
| linked + symptom_persists (NEED) | 1 |
| symptom_persists alone (REJECT) | 2 |

The 2 **symptom-alone REJECT** fixtures (wrong-patch / stale-persists family)
are the most demanding grounding cases: the verdict is forced purely by the
issue symptom reproducing post-patch despite green/fresh coverage, with the
symptom probe log placed last in the payload (§4).

### 3.1 Missing-archive special audit (p2p map / baseline / probe source)

Missing archives do **not** coincide with missing forcing operands:

| archive gap | fixtures affected | decision role | Gate-1 ruling |
| --- | --- | --- | --- |
| per-test post-patch p2p map | 6 / 22 | corroborating where f2p or runner summary supplies the failure | not forcing in any affected fixture |
| per-test baseline p2p map | 12 / 22 | needed only to independently re-derive regressed vs pre-existing-bad | **caveat**, see below |
| probe source | 13 / 22 | probe→issue fidelity provenance | **caveat**, not forcing |

- **Zero fixtures become underdetermined.** Every forcing channel has its
  decision operand visible in RAW and STRUCTURED; missing maps/source appear
  only as per-channel `caveats`, never as `missing_forcing_channels`.
- **Baseline-map caveat (12 fixtures, acceptance channels):** without the
  per-test base map, whether a scoped p2p FAILED is *applicable* cannot be
  re-derived by the reviewer from primary bytes; RAW/STRUCTURED instead expose
  the runner summary's `p2p_regressed_ids` / `p2p_preexisting_bad_ids`.
  **This is a mild semi-adjudication leak**: an upstream program already
  performed the applicability classification the reviewer otherwise would.
  It is identical in RAW and STRUCTURED (so it does not bias the RAW-vs-
  STRUCTURED contrast), but it slightly narrows the grounding demanded of the
  reviewer and must be disclosed, not silently counted as full grounding.
- **Probe-source caveat (13 fixtures, symptom channel):** the retained
  pre/post probe **output and exit codes** — the actual symptom operand — are
  present in 22/22; what is absent is the probe **source**, so fidelity of the
  probe to the original issue cannot be re-audited from source. Symptom
  grounding is therefore operable but its provenance rests on the signed run
  record.

Any fixture whose layer lacked a forcing operand would have been scored
`layer_gold_undetermined_unscored` (`appropriate=null`) rather than forced to
the oracle; the runner rule is implemented and self-checked (currently
vacuous because determination is 22/22).

## 4. Length, evidence position, truncation

Three model-independent estimators are reported; anchor = 8119 B / 2246 tok
measured on CEE adjudicated payloads = 3.615 B/tok.

| layer | bytes min / med / max | anchor tokens min / med / max | whitespace-punct max | fits 128k (DS) | fits 1M (GPT) |
| --- | --- | --- | --- | --- | --- |
| raw | 24,692 / 55,581 / 245,381 | 6,817 / 15,349 / **67,780** | 57,521 | yes (60.2k headroom) | yes |
| structured | 12,674 / 24,770 / 36,729 | 3,493 / 6,832 / 10,138 | — | yes | yes |
| adjudicated | 6,633 / 8,091 / 14,480 | 1,830 / 2,232 / 3,997 | — | yes | yes |

- One RAW payload (`cee_cfc14244c59a8ceb`) crosses the 64k caution line at
  ~67.8k anchor tokens, but remains ~60k tokens inside DeepSeek's 128k window;
  even the conservative chars/4 estimate (61.3k) fits. **No deterministic
  truncation is triggered in Gate 1.**
- Gate 2 guardrail (pre-registered): if a served prompt would exceed the
  target model's usable context (window − completion cap), apply a
  deterministic, logged truncation that retains the head (identity/attestation)
  and the tail (symptom probe + exit codes) and replaces elided log middle with
  its sha256 + line span — never deleting a grounding operand; the rule and
  every affected cell are recorded.
- **Position is balanced across layers — a key internal-validity result.**
  The decisive symptom evidence sits at payload fraction
  0.871 / 0.969 / 0.992 (min/med/max) in RAW, 0.95 / 0.971 / 0.984 in
  STRUCTURED, and 0.959 / 0.967 / 0.981 in ADJUDICATED. Evidence is near the
  end in **all three** arms, so recency/burial is a level playing field and a
  layer effect cannot be attributed to differential ordering. Within RAW the
  f2p log is early (median fraction 0.275) while p2p baseline is deep (0.682),
  so RAW-only extraction difficulty still varies by channel.

## 5. Label / verdict leak re-scan (actual served bytes)

An independent scan over the **exact bytes the runner serves**, restricted to
the evidence region after the layer body marker (to avoid flagging legitimate
words in the shared instruction head):

- forbidden verdict booleans (`linked`, `fresh`, `complete`,
  `symptom_persists` statuses and their printed yes/no forms): **0 hits**
- gold / scenario / decision-equivalent metadata (`cee_gold`,
  `evidence_class`, `decisive_failure`, class names such as `wrong_patch`,
  `stale_persists`, etc.): **0 hits**
- scope: 44 RAW + STRUCTURED payloads; ADJUDICATED is exempt by design
  (it is the frozen CEE bundle, which intentionally prints pre-adjudicated
  facts) and is byte-identical to the frozen CEE bundle for all 22 fixtures.

The runner also hard-blocks at send time (`pre_send_leak_check`); both the
runtime guard and this offline re-scan are clean.

## 6. Threats to validity

Confounds bundled in the RAW→STRUCTURED→ADJUDICATED manipulation — end-to-end
layer differences cannot automatically be read as pure "grounding ability":

1. **Information extraction vs credibility judgement.** RAW requires parsing
   logs/stacks/exit codes; STRUCTURED organizes the same facts; ADJUDICATED
   adds trusted verdicts. A RAW deficit conflates extraction error with
   evidence-use policy. The sufficiency certificates bound this (forcing
   operands exist in every layer) but do not eliminate effort differences.
2. **Context length.** RAW median 15.3k / max 67.8k tokens vs adjudicated
   median 2.2k. Long-context attention effects can depress RAW independently
   of grounding. Mitigation: report per-layer token counts as a covariate and
   flag the one >64k cell; consider a length-matched sensitivity analysis.
3. **Presentation order.** Decisive evidence is near the tail in every layer
   (§4), so order is balanced across arms; within-arm channel order still
   differs and RAW extraction difficulty is channel-dependent.
4. **Pre-adjudication anchoring (demand characteristics).** ADJUDICATED
   prints explicit booleans; the model may anchor on the printed claim rather
   than independently judge. That arm measures *policy execution over trusted
   facts* (the CEE construct), not grounding; this is intended but must label
   the contrast correctly.
5. **Format/structure is itself a treatment.** RAW↔STRUCTURED differences
   contain both a *formatting* component and a *grounding-step* component;
   the two cannot be separated by these two arms alone.

Additional limits:

6. **Runner-summary semi-adjudication** for p2p applicability in 12 fixtures
   (§3.1): grounding is partly pre-done, identically in RAW and STRUCTURED.
7. **Probe provenance** unverifiable from source in 13 fixtures; symptom
   grounding rests on signed outputs.
8. **Sample independence / generalisation:** 22 fixtures are mirrors of only
   **10 independent issues**; within-issue mirrors are clustered, not i.i.d.
   Gate 2 supports a small-sample **mechanism** check, not broad benchmark
   claims. Use the pre-registered issue-cluster bootstrap (seed 7, 10 000
   resamples); do not pool EAL scores with E1/CEE.
9. **Model drift / determinism:** temperature 0 is not guaranteed
   deterministic; the served model id need not pin weights. Record served id
   and timestamp per request; treat a Gate-2 run as a single time-point.
10. **Mock ceiling:** Gate-1 numbers are plumbing evidence only.

## 7. Engineering gates (20/20 PASS)

Cell coverage & uniqueness (5 gates); cross-model payload sha identity;
uniform wire controls per arm (temp 0, json_object, 4096 cap, no tools, no
plain-text fallback); INVALID/AMBIGUOUS retained unrepaired; full raw-first
retention incl. verbatim reason/gap and model/tokens/latency; zero mock spend
and envelope within cap; **kill switches verified by real subprocess** —
`--allow-paid-run` exits non-zero with `REFUSED`, and a live run without
`--mock` is likewise refused; served-byte leak scan clean; 22/22 sufficiency
with the underdetermined-scoring rule wired; adjudicated byte-identity with
frozen CEE bundles. BudgetGuard runs pre-call on every request against the
$1.50/model and $3.00 total caps; `--only-cells/--only-layers/--only-models`
selectors and resumable JSONL are in place.

## 8. Projected real-API cost for a Gate-2 132-cell run (estimate only)

Input total per model over 66 prompts: ~752k tokens by the conservative
runner bytes/3 estimator; ~623k by the anchored 3.615 B/tok estimator
(raw 1.53 MB / structured 0.53 MB / adjudicated 0.20 MB served across the 22
fixtures).

| model | worst case (bytes/3, 4096 out every call) | realistic (anchored, ~400 out) |
| --- | --- | --- |
| deepseek-flash ($0.30/$1.20) | **$0.55** | $0.22 |
| gpt-4.1-mini ($0.40/$1.60) | **$0.73** | $0.29 |
| both arms | **≈ $1.28** | ≈ $0.51 |

Hard caps enforced at run time: $1.50/model, $3.00 total — the worst-case
envelope (~$1.28) sits inside the total cap with margin. These are guard
prices; Gate 2 must re-confirm vendor pricing before any paid call.

## 9. Gate 2 readiness (not yet approved)

Mechanism is plumbed and construct-controlled for the forcing operands.
Before any paid run we recommend: (a) written Gate 2 approval and explicit
budget; (b) re-verify model context windows and prices; (c) decide the
sensitivity handling for the single >64k RAW cell; (d) frame Gate 2 as a
10-issue mechanism study with cluster bootstrap, and pre-register the
Δ_Grounding primary contrast plus the length/summary-abstraction covariates
described above.

**No sampling was expanded, no paid API was called, no E1/CEE gold, prompt,
bundle, result or scoring rule was modified, and nothing was committed.**
Awaiting the next written approval.
