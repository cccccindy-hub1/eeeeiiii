# Gate 3 Design — External Validation on Independent Issues

**Status: DESIGN ONLY.** This document is produced under the zero-API
Research Consolidation Gate. It specifies how a *future*, separately
authorized Gate 3 would sample new independent issues and validate the error
modes discovered in E1/CEE/EAL/R1/X. **No new issues are built, no fixtures
constructed, no API called, and no budget is committed here.** Execution
requires a new written approval.

The primary purpose of Gate 3 is **cross-independent-issue validation of the
already-discovered behavioral error modes** (premature evidence-contradicting
acceptance in gpt-4.1-mini; over-abstention without operative contradictions
in deepseek-flash), **not** further prompt optimization on the existing 22
fixtures.

---

## 1. Objectives and estimands (pre-registered before sampling)

**Primary (model-vs-gold calibration on new issues).**
- P1. Unsupported-acceptance rate over acceptance-eligible new cells
  (predicted ACCEPT with gold ∈ {REJECT, NEED_EVIDENCE}), per model,
  issue-equal-weighted, with an issue-cluster bootstrap CI.
- P2. Operative contradiction rate: among unsupported acceptances, the
  fraction whose reason contains an explicit affirmative evidence assertion
  contradicted by visible operands, coded by the blinded procedure in §5.
- P3. Over-abstention and unsupported-rejection rates (secondary calibration
  families).

**Secondary (intervention validation, only if P1 replicates).**
- S1. Factorial effects ΔA / ΔB / ΔAB exactly as defined in X (Verification
  Assistance, Policy Salience), issue-equal-weighted, paired issue-cluster
  bootstrap, but treated as confirmatory only with adequate n (see §6).
- S2. Test–retest reliability: within-cell repeat variation at temperature 0.

The X 22 fixtures and any Gate 3 new issues are **never pooled** for
inference; Gate 3 is reported as an independent replication cohort, and the
old set is referenced only as the discovery cohort.

## 2. Sampling rules for new independent issues

1. **Universe.** New issues drawn from a pre-named, version-pinned issue/PR
   source (the same upstream task family for the first replication wave, so
   harness semantics are comparable; a later wave may add a second ecosystem).
   Sampling frame and snapshot commit are frozen and published before any
   labels are produced.
2. **Independence.** An "issue" is one upstream issue thread with its merged
   or proposed fix. Two fixtures may not share a base commit, target patch,
   or served-artifact hash. **Mirror pairing is forbidden in the primary
   cohort** — each issue contributes one target patch; this directly removes
   the mirror-count inflation identified in consolidation (24/34 X
   unsupported accepts sat in mirrored negative fixtures).
3. **Eligibility (mechanical, applied blind to model behavior).**
   - A real CI/run record exists or can be deterministically replayed for the
     target base commit, with per-test status available for post runs and, for
     REJECT/NEED constructions, enough primary log content to establish the
     decisive channel.
   - At least one declared FAIL_TO_PASS or an explicit issue-symptom probe is
     definable.
   - The issue is not already in the discovery set (id, title, and patch hash
     dedupe).
4. **Stratification.** To preserve estimability of the ternary gold classes,
   sample toward a target mix (e.g. ≈ 1/3 sufficient-positive, 1/3
   decisive-negative, 1/3 insufficient), but select *candidates* mechanically
   from the frame and assign stratum only through the §4 fact arbitration; do
   not hand-pick issues to force a class. Report the unstratified frame size
   and exclusions with reasons.
5. **Sample size.** Two tiers (see §6 power): a **replication tier of ~30
   new issues** adequate for P1/P2 prevalence with tight CIs and for the
   larger (Δ≥0.15–0.20) factorial effects; expansion to **~60 new issues**
   only if the confirmatory ΔA question for gpt-4.1-mini at effect ≈0.125 is
   explicitly approved.
6. **No reuse for tuning.** New issues are locked before any model call;
   prompts are frozen on the discovery cohort and must not be edited after
   seeing Gate 3 outputs.

## 3. Evidence-quality gates (per candidate issue, before gold assignment)

A candidate is admitted only if all hold, verified from primary artifacts
(not derived summaries):
- **Q1 Linkage operands present.** Target base commit and target patch hash
  are available and a run record carries comparable fields.
- **Q2 Freshness operands present.** An expected/attested run tree and the
  executed run tree are both available as explicit hashes (or the issue is
  logged as a linkage-only design and not used for freshness contrasts).
- **Q3 Coverage operands present.** Declared f2p/p2p sets and executed
  per-test post maps are both available; set differences are mechanically
  computable.
- **Q4 Primary logs retained.** Raw post f2p and p2p logs with exit codes
  and test summaries are retained; a baseline p2p log is required to label a
  post failure "pre-existing", otherwise such cells are limited to NEED/REJECT
  labels that do not depend on baseline attribution.
- **Q5 Symptom probe provenance.** Where a symptom probe drives a label, the
  probe source and pre/post exit codes are retained; derived probes without
  retained source cannot alone support a decisive label.
- **Q6 No label leakage.** Rendered evidence contains no
  linked/fresh/complete verdict and no field name implying pre-verification
  (the G2.5 audit standard); headers state tables are operands, not verdicts.
Candidates failing any gate are excluded with a recorded reason; exclusions
are reported as a flow diagram so selection on evidence availability is
visible.

## 4. Gold arbitration

- **Deterministic base.** Gold is computed from the six-channel operand facts
  by the frozen rule set (linkage/freshness/coverage/executed-failure/symptom),
  i.e. the same mechanical oracle used for X; the computation and its inputs
  are persisted per issue.
- **Independent human adjudicator.** A reviewer who has not seen any model
  output independently assigns ternary gold and a primary mismatch channel.
  Disagreement with the oracle is resolved by a second adjudicator; the
  resolution rationale is recorded. Inter-adjudicator agreement (and any
  oracle override) is reported.
- **Blinding.** Adjudicators see issue/patch/primary evidence only — never
  model reasons, condition, or accuracy.
- **Pre-registration.** The final gold table and per-issue channel labels are
  frozen before the first model call; no post-hoc gold edits are allowed
  (corrections are appended as an auditable amendment).

## 5. Blinded reason coding (fixing the X limitation)

- Candidate reasons are selected by the frozen pass-1 lexicon **plus** the
  operand-contradictability filter.
- Coding packets show only operands + verbatim reason + flagged properties
  (model, condition, gold, decision, and prior coding hidden; the X sealed-key
  mechanism is reused).
- **At least one coder must be independent of the discovery team** to replace
  the X same-coder sensitivity check with genuine inter-annotator
  reliability; report raw agreement and Cohen's κ between independent coders,
  plus adjudication of ties. The X lesson — that affirmative words elsewhere
  in a reason that ultimately negates the property are false positives, and
  that explicit acknowledgment followed by a wrong relevance dismissal is a
  *decision* error, not an all-pass assertion — is written into the coding
  manual as worked (unlabeled) examples before coding.
- Operative-on-accept is derived only after unblinding.

## 6. Statistical power (offline simulation, `grc_gate3_power.json`)

Using frozen X issue-level paired-contrast dispersion (issues equal-weighted;
mirrors averaged within issue), 20,000 simulated studies, paired-t rule
approximating the percentile issue-cluster CI at n≥10:

| gpt-4.1-mini effect (obs. SD) | n=10 | n=20 | n=30 | n=40 | n=60 |
|---|---|---|---|---|---|
| ΔA, true 0.125 (SD 0.317) | .16 | .37 | .55 | .68 | **.85** |
| ΔA, true 0.15 | .23 | .51 | .71 | .83 | .95 |
| ΔB, true 0.125 (SD 0.237) | .27 | .60 | .80 | .90 | .98 |
| ΔAB, true 0.125 (SD 0.158) | .60 | .92 | .99 | 1.0 | 1.0 |

Implication: the **prevalence/replication targets P1/P2 are well served by
~30 new independent issues**, but confirming a gpt-4.1-mini ΔA factorial
effect of the size X observed (~0.125) needs roughly **60 independent
issues**, because that effect is highly heterogeneous across issues. Gate 3
should therefore lead with error-mode replication (30 issues) and treat the
factorial confirmatory test as a separate, adequately-powered expansion that
is approved only if the mode replicates. CIs that merely touch 0 will be
reported as directional, never as significance.

## 7. Reliability design (temperature-0 non-determinism)

- Every Gate 3 cell is called **k=3 times** at temperature 0 in the primary
  wave so within-cell repeat variation is estimated directly (X could not
  separate effects from a ≈±9 pp single-call noise floor).
- Primary analysis uses the per-cell distribution (e.g. proportion of
  replicates correct) and a mixed/bootstrap analysis with issue as cluster;
  single-call claims are demoted to sensitivity checks.
- Served model version and any backend identifier are recorded for every
  call; a version change mid-wave invalidates pooling and triggers a new
  frozen cohort.

## 8. Budget (planning numbers, not an authorization)

Realized X price was $0.392409 / 176 calls ≈ **$0.00223 per call**. At that
price, two models × four conditions:

| New issues | calls (both models, k=1) | USD k=1 | USD k=3 |
|---|---|---|---|
| 10 | 80 | $0.18 | $0.54 |
| 20 | 160 | $0.36 | $1.07 |
| 30 | 240 | $0.54 | $1.61 |
| 40 | 320 | $0.71 | $2.14 |
| 60 | 480 | $1.07 | $3.20 |

Token cost is negligible at the X rate; the real constraints are issue
curation and independent gold/reason adjudication labor. A hard budget cap
and a stop rule (abort if per-call price deviates >2× from the planning rate
or served-model identity changes) are set at approval time. This table is a
planning estimate only and does not commit funds.

## 9. Confound controls carried forward

- **Length confounding:** Verification Assistance adds text; Gate 3 includes
  a length-matched control prompt (same added verbatim length, no computed
  counts) so the A contrast is not reducible to added length.
- **Presentation:** keep raw/structured/adjudicated rendering byte-stable
  relative to the frozen X protocol except for the explicitly pre-registered
  factor changes.
- **Selection reporting:** publish the sampling frame, exclusion flow, and
  evidence-quality gate failures to bound generalization.

## 10. Hard prohibitions honored by this document

No Gate 3 sample is constructed, no model/API invoked, no issue added, no
prompt tuned on old fixtures, no E1/CEE/EAL/R1/X artifact modified, and no
git commit made. This is a design artifact awaiting separate written
approval; work stops here.
