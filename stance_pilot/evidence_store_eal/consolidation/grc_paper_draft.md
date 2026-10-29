# GroundedReview: Evaluating Evidence Verification and Decision Calibration in Code-Review Agents

**Working draft — Research Consolidation Gate (zero-API).** All figures are
reproduced from frozen E1/CEE/EAL/R1/X artifacts by independent analysis code
(`evidence/grc_*.py`); cross-validation against the shipped X analysis is
exact on every recomputed value (`grc_x_recompute.json`,
`exact_match_all=true`). Claims are stated at the behavioral level. The
factor labels **Verification Assistance (A)** and **Policy Salience (B)**
name prompt manipulations, not internal mechanisms; a non-zero interaction
ΔAB indicates statistical dependence between the two manipulations, not a
causal claim about cognition.

---

## 1. Scope of the five study stages

The five stages answer different questions and are never pooled.

| Stage | Design | What it can answer | What it cannot |
|---|---|---|---|
| **E1** | Agentic code-review over repo tasks; pooled oracle DA DS 0.591 / GPT 0.673 | Whether reviewers acquire and use evidence at all in an end-to-end review | Separate grounding from policy; evidence is not pre-adjudicated |
| **CEE v1.1** | 22 bundles, adjudicated evidence; 7 sufficient-positive / 6 decisive-negative / 9 insufficient; DA DS 0.909 / GPT 0.818 | **Decision policy execution over pre-adjudicated evidence (L3)** | Whether the model can ground verdicts in raw observations |
| **EAL (G2/G2.5)** | Same 22 issues × 3 abstraction layers (raw / structured / adjudicated) | Whether evidence **verification (L2)** changes with presentation; per-case contradiction audit | Causal mechanism; independent-issue generalization |
| **R1** | Re-run of the three layers at temperature 0 | Test–retest behavior at temperature 0; single-call noise magnitude | A reliability *estimate* from many replicates (only one repeat) |
| **Experiment X** | 2×2 factorial on 22 fixtures (88 calls/model): A = mismatch count assistance, B = asymmetric-policy salience | Main effects and interaction of two prompt-level corrections, with paired issue-cluster CIs | Eliminate the error mode; generalize beyond 10 issues / these fixtures |

The 22 fixtures nest within **10 independent issues**; EAL/X contrasts are
within-issue and within-fixture. The 8 pre-registered "chronic" bundles are a
diagnostic subset and never replace the primary 22-cell analysis.

---

## 2. Results

### 2.1 Evidence acquisition (E1)

End-to-end, both reviewers act on evidence imperfectly (pooled oracle-based
DA 0.591 for deepseek-flash, 0.673 for gpt-4.1-mini). E1 establishes that
reviewers differ in end-to-end calibration but cannot localize failures,
because the evidence there is neither pre-adjudicated nor decomposed.

### 2.2 Decision policy over pre-adjudicated evidence (CEE)

When verdicts on the evidence are effectively supplied, both models apply the
ternary policy most of the time (DA 0.909 / 0.818). The residual errors show
the two models fail in **opposite directions**: deepseek-flash is the more
conservative reviewer (tendency to abstain/reject), gpt-4.1-mini the more
permissive one. This asymmetry is the policy-level seed of everything below.

### 2.3 Evidence verification under abstraction (EAL/G2.5)

When the model must itself compare operands (identity hashes, run tree,
declared-vs-executed test sets, raw-log exit codes), presentation changes
behavior. G2.5 independently audited the 8 pre-registered
structured-NEED→ACCEPT cases: every one contained an explicit affirmative
assertion (fresh / linked / coverage-complete / all-checks-pass) that the
visible operands directly contradicted, with gaps and missing-evidence
fields left empty. On the same structured cells deepseek-flash abstained
correctly in 8/8, citing the precise mismatch channel (stale,
coverage-incomplete, or linkage-mismatch). Audit of field names, table
titles, and instructions found no "pre-verified" wording that would explain
the structured-specific failures; the headers explicitly state that tables
show operands, not verdicts.

G2.5 also refined the mechanism claim: gpt-4.1-mini already false-accepted
6/8 of these cases at the raw layer, so structuring did not create provenance
blindness; rather, it converted an unperformed check into confident claims
(+2 new false accepts), while the adjudicated layer corrected 7/8. We state
this behaviorally: *gpt-4.1-mini does not consistently perform provenance or
coverage verification at any abstraction level; structured presentation
turns that omission into explicit, evidence-contradicting assertions.*

### 2.4 Factorial prompt corrections (Experiment X)

All 176 calls succeeded (88 per model), total cost **$0.392409** (hard cap
$1.50), zero API/parse errors; served models were `deepseek-flash` and
`gpt-4.1-mini-2025-04-14` on all 88 respective calls. Four conditions were
freshly invoked; no Gate-2 or R1 control output was reused.

**Decision accuracy (issue-equal-weighted primary estimand; paired
issue-cluster bootstrap, 10 issues, 10,000 replicates, seed 7, percentile
2.5/97.5):**

| Condition | deepseek-flash DA [95% CI] | gpt-4.1-mini DA [95% CI] |
|---|---|---|
| a0b0 | 0.800 [0.633, 0.950] | 0.425 [0.200, 0.650] |
| a1b0 | 0.850 | 0.525 |
| a0b1 | 0.817 | 0.475 |
| a1b1 | 0.883 | 0.625 [0.400, 0.825] |

**Factor effects (issue-equal-weighted):**

| Effect | deepseek-flash Δ [CI] | gpt-4.1-mini Δ [CI] |
|---|---|---|
| Verification Assistance ΔA | +0.058 [0.000, 0.117] | **+0.125 [0.000, 0.325]** |
| Policy Salience ΔB | +0.025 [−0.033, 0.092] | +0.075 [0.000, 0.225] |
| Interaction ΔAB | +0.017 [−0.117, 0.133] | +0.050 [0.000, 0.150] |

**Reading of the intervals.** Every gpt-4.1-mini interval has its lower edge
at exactly 0, and deepseek-flash ΔB/ΔAB cross zero. A bootstrap CI whose
boundary is 0 means "no effect" sits at the edge of the resampling
distribution; this is **directional but weak evidence, not statistical
significance**, and it must not be reported as a confirmed positive effect.
With only 10 independent clusters the intervals are wide. The defensible
statement is that both manipulations moved gpt-4.1-mini accuracy in the
positive direction, that their combination gave the largest point gain
(+20 pp at a0b0→a1b1), and that neither effect is estimated precisely enough
to establish reliability.

### 2.5 Error families

Per 88 parseable cells:

| Family | deepseek-flash | gpt-4.1-mini |
|---|---|---|
| Unsupported acceptance (ACCEPT vs REJECT/NEED gold) | **0 (0.0%)** | **34 (38.6%)** |
| Unsupported rejection | 5 (5.7%) | 3 (3.4%) |
| Over-abstention (NEED vs decisive gold) | 12 (13.6%) | 2 (2.3%) |

The two reviewers exhibit different calibration failures: gpt-4.1-mini
errs predominantly by premature acceptance, deepseek-flash by excess
abstention. Restricting to cells where acceptance is even possible
(gold ∈ {REJECT, NEED_EVIDENCE}), gpt-4.1-mini unsupported-acceptance rate
is 34/60 = 0.567.

### 2.6 Reason-level contradictory assertions: blinded re-coding

Pass-1 mechanically found 48 candidate reasons whose wording matched a
contradiction lexicon **and** whose fixture operands made the flagged
property contradictable (14 deepseek-flash, 34 gpt-4.1-mini). Pass-2
(developer-agent, unblinded) had coded 30/48 as confirmed affirmative
contradictions.

A **blinded pass-3** then re-coded all 48 from packets containing only the
evidence operands, the verbatim reason, and the flagged properties — no
model name, condition, gold, decision, or pass-2 verdict (shuffle seed
20261026; sealed key opened only after coding). Results:

- Overall raw agreement with pass-2 **0.854**, Cohen's κ **0.71**.
- **gpt-4.1-mini (34 cells): agreement 0.971, κ 0.93**; pass-3 confirmed
  25 vs pass-2 24. The operative-on-accept count is **identical at 20/34**
  and per condition 5/6/5/4 (a0b0/a1b0/a0b1/a1b1) — the headline claim that
  ~three in five false accepts carry an evidence-contradicting operative
  assertion is robust to the blinded re-coding.
- **deepseek-flash (14 cells): agreement 0.571, κ 0.00**; pass-3 confirmed
  **0** vs pass-2 6. All six disagreements are NEED_EVIDENCE cells in which
  the reason *explicitly and correctly* reports the tree/sha mismatch or the
  executed failing test and abstains; the pass-1 lexicon had hit affirmative
  words elsewhere in those reasons (e.g. "cannot confirm complete, fresh…"),
  and the wider pass-2 reading counted them. Under the strict literal rule
  they are correct acknowledgments, not contradictions. Crucially,
  **operative-on-accept is 0 under both codings** — deepseek-flash never
  couples an evidence-contradicting claim to a false acceptance.
- One gpt-4.1-mini cell moved in the opposite direction (faae0894/a1b0): the
  reason first reasons toward REJECT then reverses and explicitly asserts
  "the acceptance set coverage is complete … fully executed" while 102/102
  declared p2p tests are absent post-patch; pass-3 coded this P3 assertion
  as confirmed (the cell verdict was NEED_EVIDENCE, so it is not operative).

**Methodological status.** Pass-3 is a same-coder, partially-blind
sensitivity check, not independent inter-annotator reliability: the coder is
the same agent that authored pass-2 (residual recall), and assisted-cell
prose sometimes discusses the supplied count tables, making the condition
occasionally inferable from text alone. The numbers in §2.6 must therefore
be presented with that limitation; what the blind re-coding substantiates is
(a) the robustness of the gpt-4.1-mini operative-contradiction count and
(b) the fragility of the deepseek-flash non-operative count, which rests on a
coding-convention boundary rather than on a substantive difference.

### 2.7 Concentration across issues and mirror fixtures

Per-issue analysis of the 34 gpt-4.1-mini unsupported acceptances:

- They occur in **9 of the 10 independent issues**; the issue-equal-weighted
  rate over acceptance-eligible cells is 0.662, *higher* than the
  cell-weighted 0.567, so the count is not inflated by the largest issue
  clusters. The single largest contributing issue (sympy-14531) accounts for
  8/34 (0.235).
- At fixture granularity the 34 events come from **9 distinct fixtures**
  (7 accepted wrongly in all four conditions; 2 in only some), and **24/34
  events lie in the negative member of a mirror pair** (a stale/wrong
  counterpart built from the same artifact base as a valid fixture). The
  mirror construction repeats one underlying issue up to four times across
  conditions, so the informative number of independent error *instances* is
  closer to 9 fixtures / 9 issues than to 34 cells. This motivates the Gate 3
  emphasis on new independent issues rather than more cells on old fixtures.

### 2.8 Stability of the eight pre-registered cases across G2.5 → R1 → X

Trajectories on the chronic 8 (structured at G2.5 and R1; all four X cells):

- **gpt-4.1-mini:** 7/8 are *stable wrong accepts* at every observed
  timepoint and every X condition; the single intervention-responsive case
  (c637f604) recovered to NEED_EVIDENCE only in a1b1 (both factors jointly)
  and had been a stable false accept at G2.5, R1, a0b0, a1b0, a0b1.
- **deepseek-flash:** 7/8 are *stable correct* abstentions across all
  timepoints; one case (c637f604) oscillated (NEED at G2.5 and all X cells,
  REJECT at R1) — a boundary swing, not an intervention response.
- Across the full 22 fixtures, three-timepoint comparison (Gate 2 / R1 /
  X-a0b0) showed 20/22 identical verdicts for each model with 2 drifting
  cells per model (deepseek-flash: c564f50f, c637f604; gpt-4.1-mini:
  faae0894, a242cd7a).

### 2.9 Reliability

Temperature-0 calls are not deterministic in this API backend (no pinned
weights, no seed). The CEE-vs-EAL adjudicated comparison on byte-identical
prompts showed two zero-sum gpt-4.1-mini flips, placing single-call noise at
roughly ±2 cells/22 (≈±9 pp) — the same order as the X factor effects.
Consequently the X point estimates should be read as sitting on top of an
unquantified repeat-noise floor; a replicate-based reliability estimate is a
prerequisite for any future between-condition inference on this model.

---

## 3. Discussion

**3.1 A coherent behavioral narrative.** Three observations hold across the
stages: (i) reviewers calibrate errors differently — one predominantly
over-abstains, the other prematurely accepts (§2.2, §2.5); (ii) changing
evidence structure and pre-adjudication changes gpt-4.1-mini's judgments,
but these differences cannot be read as pure grounding competence, because
the same model already fails on raw evidence and frequently asserts
properties it has not checked (§2.3, §2.6); (iii) on the current set, even
explicit mismatch counts and a restated asymmetric policy do not reliably
remove the verification failures: 7/8 chronic false accepts survive every
intervention, and the one recovery required both factors at once (§2.4,
§2.8).

**3.2 The research question the data support.** The sharper question is not
"can the model compare hashes?" but: **why can a reviewer produce a
complete-looking verification narrative while committing to a verdict that
the visible evidence contradicts?** In gpt-4.1-mini the operative pattern is
an affirmative evidence claim fused to a permissive decision; in
deepseek-flash the analogous prose either negates the claim or is followed
by abstention. The blind re-coding strengthens this contrast for operative
(false-accept) errors while showing that the broader non-operative count is
coding-convention-sensitive (§2.6).

**3.3 What X does and does not establish.** X demonstrates feasibility of a
controlled 2×2 test of two behavioral corrections and yields positive point
directions, but with 10 clusters, CI edges at 0, a temperature-0 noise floor
of comparable size, and condition–evidence-length confounding (assisted
cells contain more text), it cannot establish that either intervention
causes reliable improvement or that they address the core error. ΔAB ≠ 0
only signals that the two manipulations do not combine additively.

**3.4 Scope of inference.** Findings are established on 22 fixtures over 10
issues from one repository, with mirror pairs reusing artifacts. They
support a hypothesis about cross-model calibration differences and
verification–verdict dissociation, not a population-level prevalence claim.

## 4. Threats to validity

1. **Few independent issues (n=10).** Bootstrap units are issues; 10
   clusters yield wide intervals and low power; CI edges at 0 are
   uninformative about small/moderate effects.
2. **Single repository / ecosystem.** All issues are SymPy tasks drawn from
   one review benchmark style; test-harness conventions and evidence layouts
   may not transfer to other languages or CI systems.
3. **Mirror fixtures.** Valid and stale/wrong counterparts share an artifact
   base, and negative fixtures recur across four conditions; cell-weighted
   counts (e.g. 34) overstate independent evidence relative to 9 fixtures /
   9 issues.
4. **Pre-adjudicated facts.** CEE and the adjudicated layer supply verdicts
   on evidence; performance there measures policy execution, not grounding,
   and must not be pooled with EAL/E1.
5. **Derived summaries.** Runner-derived classifications (e.g. "0/0, no
   regressions") are presented alongside primary logs; models may inherit
   them without re-derivation, and five of eight chronic cases lack retained
   p2p baseline logs.
6. **Model versions.** Results are pinned to `gpt-4.1-mini-2025-04-14` and
   the served `deepseek-flash`; silent backend changes would shift behavior.
7. **Temperature-0 non-determinism.** Observed ≈±9 pp single-call swing on
   identical prompts; X has no within-condition replicates, so effects are
   not separated from repeat noise.
8. **Subjective reason coding.** Contradiction coding relies on prose
   interpretation. Pass-3 blinding reduced label exposure but was performed
   by the same agent with possible residual recall and occasional
   condition-leakage through assisted-cell text; κ is self-agreement, not
   independent inter-rater reliability. The deepseek-flash non-operative
   count is convention-sensitive.
9. **Condition–evidence-length confounding.** Verification Assistance adds
   count/table content, so assisted cells are longer; any A effect is
   entangled with added verbatim length and with the presence of the
   supplied numbers, and cannot be attributed specifically to "assistance."

## 5. Immediate conclusion

On the current benchmark, gpt-4.1-mini shows a stable, intervention-resistant
tendency toward evidence-contradicting premature acceptance, while
deepseek-flash leans toward over-abstention without operative
contradictions. Neither prompt-level correction tested in Experiment X is
established as an effective remedy. We therefore stop optimizing prompts on
the existing 22 fixtures; the next budgeted step should be external
validation on newly sampled independent issues (Gate 3 design, separate
document), after blinded adjudication and statistical consolidation — not
further prompt engineering on the old fixtures.
