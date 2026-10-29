# GroundedReview: Evaluating Evidence Sufficiency in LLM-Based Code Review

**Working draft — Paper Sprint v1 (2026-10-29).** Every quantitative statement in
this draft is produced by `paper_sprint/scripts/` from frozen result stores and
carries a source hash in `paper_sprint/tables/results_summary.json` and
`paper_sprint/tables/result_inventory.csv`. Gold labels are **PROVISIONAL**
throughout (single annotator, n=1, `annotator2 = NOT_OBTAINED`). Findings are
reported in three strictly separated classes: **corrective replication**,
**exploratory**, and **independent-issue pilot (not yet model-evaluated)**.

---

## Abstract

LLM-based code-review agents are increasingly asked to gate code changes, yet
current benchmarks largely measure whether an agent reaches the correct
accept/reject label without separating two distinct questions: whether the
*evidence* presented is intact and trustworthy, and whether it is *sufficient*
to justify a decision at all. We introduce **GroundedReview**, a benchmark that
(a) casts code review as a three-way decision — **ACCEPT / REJECT /
NEED_EVIDENCE** — and (b) evaluates the same real issue–patch pair under
several evidence conditions that independently control which test outcomes are
visible, whether the agent can actively fetch artifacts, and whether provenance
and freshness are verifiable. We distinguish **Oracle Gold** (the decision
warranted by a fresh, scoped pytest run) from **Condition Gold** (the decision
warranted by the evidence actually granted, which is legitimately
NEED_EVIDENCE on restricted surfaces). On ten independent SymPy issue–patch
pairs with two served models (`deepseek-flash`, `gpt-4.1-mini`) across five
conditions, a corrective replication shows that repairing protocol-construct
defects in our own instrument moved one model's sufficient-evidence abstention
from 9/10 to 1/10 — an associational, not causal, contrast — while the other
model, under a restricted "strict" surface whose correct answer is
NEED_EVIDENCE, returned unsupported **ACCEPT on 7/10** issues, upgrading
non-decisive evidence into acceptance. A traceable case shows an agent
accepting a patch after an already-visible fail-to-pass test had failed. We
further contribute eight newly constructed, independently de-duplicated issues
with 40 per-condition gold certificates and a non-interference-checked
evidence projection, as a pre-registered validation bed. All model-facing
claims on the new issues are currently **PROVISIONAL** pending independent human
arbitration and a single, capped external run; we therefore present a
measurement framework and clearly bounded evidence rather than population-level
claims about model behavior.

---

## 1. Introduction

Automated code review is moving from passive summarization toward agents that
fetch artifacts, run or read tests, and emit binding accept/reject decisions.
Evaluating such agents is subtle because a correct-looking label can arise from
insufficient or corrupted evidence, and a withheld decision (asking for more
evidence) can be the *correct* response when the granted evidence is
non-decisive. A benchmark that scores only ACCEPT/REJECT against a single oracle
cannot tell these apart and will systematically reward over-commitment.

We organize the evaluation around one question:

> **Can code-review agents distinguish evidence integrity from evidence
> sufficiency?**

*Evidence integrity* asks whether the artifacts an agent sees are authentic,
fresh, linked to the patch, and complete. *Evidence sufficiency* asks whether
those artifacts, even if perfectly intact, are decisive for the review
verdict. These are orthogonal: a restricted evidence view can be 100% authentic
yet genuinely insufficient (the correct output is NEED_EVIDENCE), and a
sufficient view can be misread (a visible failure can be ignored).

GroundedReview makes three contributions.

1. **Benchmark formulation.** A three-way review task (ACCEPT / REJECT /
   NEED_EVIDENCE) with an explicit distinction between **Oracle Gold** and
   **Condition Gold**, and a *scoped* notion of acceptability tied to declared
   tests rather than whole-project correctness.
2. **Evidence-controlled evaluation.** Five evidence conditions per issue that
   vary (i) static vs. active tool access and (ii) restricted vs. decisive
   test outcomes, with machine-checked non-interference so restricted surfaces
   cannot leak the verdict.
3. **Empirical analysis.** A corrective replication that isolates a
   protocol-construct artifact in our own earlier instrument, evidence of
   unsupported commitment under restricted evidence, and a traceable case of a
   sufficient-but-ignored failure — all reported with explicit denominators,
   issue-level units, and confidence bounds, plus an independently constructed
   validation set awaiting human adjudication.

We emphasize what the present evidence does **not** support: population-level
false-acceptance rates (our oracle-REJECT sample is three, later eight with
only two rejects), causal attribution of a cross-version change to a single
fix, or any claim that the six scoped ACCEPT issues in the new pilot passed the
entire SymPy test suite.

## 2. Related Work

*LLM code review and agent benchmarks.* Existing work evaluates review models on
accept/reject accuracy, comment quality, or repository-level repair, but
typically presents a single fixed evidence bundle and a binary label, so
abstention and evidence insufficiency are not first-class outcomes. GroundedReview
instead fixes the issue–patch pair and varies the evidence grant.

*Tool use and information-seeking agents.* Active agents can retrieve tests and
logs; benchmarks increasingly provide tools. We treat the tool surface itself
as an experimental variable (static vs. active; outcomes granted vs. withheld)
and verify non-interference rather than assuming it.

*Abstention and calibrated refusal.* Selective prediction and calibrated
abstention study when a model should decline; our NEED_EVIDENCE label is a
contextual analogue where abstention is defined relative to the *granted
evidence*, not merely model uncertainty.

*Benchmark reliability and construct validity.* Data contamination, label
noise, and leakage are known threats. Our setting adds a specific construct
risk — the evaluation instrument itself can force a wrong freshness/trust
judgment — which we document through a corrective replication, and we keep gold
PROVISIONAL until independent human adjudication.

*Test-based patch correctness.* fail-to-pass / pass-to-pass tests are standard
for program repair. We adopt them as the oracle mechanism but explicitly bound
acceptance to declared, in-scope tests and track collateral, undeclared test
changes as a disclosed blind spot.

## 3. Benchmark and Task Definition

### 3.1 Unit of analysis and decision space

The unit of independence is a **real GitHub issue with a candidate patch** in a
single project (SymPy). For each issue $i$, the agent receives the issue text,
the candidate diff, and a condition-specific evidence package, and must emit
exactly one of:

- **ACCEPT** — the patch is acceptable *under the scope of the granted
  evidence*;
- **REJECT** — a decisive failure is evidenced within scope;
- **NEED_EVIDENCE** — the granted evidence is non-decisive; a verdict cannot be
  justified without more evidence.

Cells (issue × condition × model) are **repeated measures** within an issue;
they are never treated as independent samples.

### 3.2 Oracle Gold vs. Condition Gold

**Oracle Gold** $g_O(i)$ is determined from a fresh, real pytest execution at
base and patched commits using maintainer-declared fail-to-pass (F2P) and
scoped pass-to-pass (P2P) tests plus the issue symptom: ACCEPT if declared
acceptance tests pass with no in-scope regression; REJECT on any decisive
declared failure. It is **scoped acceptability**: the P2P set is predefined and
not the entire SymPy suite, so an ACCEPT must never be described as
whole-project correctness.

**Condition Gold** $g_C(i,c)$ is the decision warranted by the evidence actually
granted in condition $c$:

- on **restricted** conditions (test outcomes withheld), $g_C =
  \text{NEED\_EVIDENCE}$ for every issue, regardless of $g_O$;
- on **sufficient** conditions (decisive outcomes granted), $g_C = g_O$.

This two-tier gold is what lets us score *respect for insufficiency* separately
from *accuracy when decisive evidence is available*.

### 3.3 Evidence integrity vs. evidence sufficiency

A package carries integrity metadata: linkage to the patch, freshness (commit
and timestamps), provenance, and coverage of declared tests. Integrity is
necessary but not sufficient: on a correctly projected restricted surface all
four can hold while the decisive acceptance outcomes are absent. Conversely, a
sufficient surface can be present but misread. The five conditions below
cross-cut integrity with sufficiency.

## 4. Evidence Conditions and the Integrity/Sufficiency Axis

Each issue is evaluated under five conditions (Figure 1).

| Condition | Access | Tier-D outcomes | Tier-A outcomes | Condition gold |
|---|---|---|---|---|
| **T2D-T** | static | restricted (withheld) | absent | NEED_EVIDENCE |
| **T3D-Strict** | active tools, strict policy | withheld even on fetch | absent | NEED_EVIDENCE |
| **T3D-Escalate** | active, may escalate | granted after escalation | — | = Oracle |
| **T2A-T** | static | — | tier-A sufficient | = Oracle |
| **T3A-T** | active | — | tier-A sufficient | = Oracle |

"T2" is a static, single-shot surface; "T3" permits active tool calls. "D"
denotes the tier-D (restricted) artifact and "A" the tier-A (decisive)
artifact. T3D-**Strict** is the key insufficiency probe: an active agent can
inspect linkage/freshness/coverage and the symptom, but post-patch F2P/P2P
verdicts are structurally unreachable, so accepting or rejecting necessarily
upgrades non-decisive evidence. T3D-**Escalate** grants the decisive outcomes
only after the agent explicitly requests them.

Non-interference is machine-checked: restricted projections are scanned for
post-patch verdicts, hidden gold, acceptance digests, and reconstructing keys.
We disclose one residual instrument gap found in the corrective replication (a
*pre-patch* baseline P2P map survived the tier-D projection); it cannot
reconstruct gold and was seen by none of the error cells, and is mandated for
removal before the next live run (Section 9.3).

## 5. Dataset Construction

### 5.1 Original ten issues (G3-A)

Ten independently selected SymPy issue–patch pairs were used for the original
run (**G3-B**) and the corrective replication (**G3-B.3**). Oracle gold is
PROVISIONAL (single annotator). Seven are scoped ACCEPT and three are REJECT
(17318, 17630, 19783). The full issue list and per-issue grid is Appendix A.1.

### 5.2 Eight new independent issues (G3-C.1 pilot)

A separate pilot constructed **eight new** SymPy issues, de-duplicated against
history and against each other by changed file. The selection funnel was
**75 → 51 → 8**: 75 candidates; 24 mutually exclusive exclusions (12 prior
wave, 10 already in G3-A, one unavailable offline blob, one no-clean-checkout)
leave 51; a separate changed-file independence step removes 4 (distinct from
the exclusion count — no double counting) to leave 47; sampling then selects
eight. Two queues of four each are used:

- **Natural** (seed 418237): issues 19346, 22914, 19495, 15875;
- **REJECT-enriched** (seed 418241): issues 19040, 14248, 19637, 16886.

The two queues have **zero issue overlap**. Oracle distribution is **6 scoped
ACCEPT / 2 REJECT** (14248 and 15875). Each issue has five condition gold
certificates = **40 certificates: 24 sufficient, 16 NEED_EVIDENCE**. Freshness
is 8/8; the frozen manifest lists 185 files with zero hash mismatch.

**Sampling disclosure.** The enrichment category priority (TRAP > P2P > F2P)
was an operational refinement finalized *before* any real test outcome was
observed (selection rule fixed at 09:20:33 UTC; first pytest result at 09:48:33),
but it is **not a verbatim pre-registration**: a counterfactual F2P-first
ordering would have moved 29 strata and selected four different issues. We
therefore label it **pilot-stage adaptive sampling**, not fully pre-registered,
and never pool natural and enriched queues to estimate a natural-population
rate. The two rejects also arose naturally rather than being manufactured
fixtures; whether their distinct failure modes instantiate one uniform
disjunctive REJECT standard is left to human adjudication (FR2).

### 5.3 Evidence-system engineering

For the eight-issue pilot: 144 restricted surfaces return **zero** forbidden
hits; an offline HTTP cross-check retallies **456/456** assertions; **40/40**
mock cells behave as expected but are **excluded from research analysis** (mock
correctness is plumbing, not model performance); three deterministic reruns are
byte-identical. Mock and live runs are fully isolated and prompts/protocol are
frozen and fingerprinted before any paid call.

## 6. Experimental Setup

**Models.** Two served models identified by their served IDs:
`deepseek-flash` and `gpt-4.1-mini`. The corrective replication used 100 new
real cells (10 issues × 5 conditions × 2 models) over the repaired protocol;
208 real model calls were made in total across the audited runs (DeepSeek 114,
GPT 94), with zero retries, zero errors, and zero resume skips; wire traffic
shows no model fallback.

**Protocol repair (G3-B → G3-B.3).** The earlier instrument had structural
construct problems (a forced `fresh=FALSE` and coverage/trust handling). The
repaired protocol (`g3b2-protocol-v1`, prompt `p3-ternary-g3b2-v1`) fixes
freshness/trust. Because activeness, freshness, and trust rules changed
together, G3-B → G3-B.3 contrasts are **cross-version and associational**.

**Budget controls.** A pre-call hard guard accumulates spend; the live
replication spent **$0.303539** (DeepSeek 0.189045, GPT 0.114494) under a
$3.00 total / $1.50 per-model cap. Raw responses are persisted before any
analysis. We also disclose a first-run failure that raised **before any HTTP
request ($0 spent)** and whose products were discarded.

**Primary and secondary research questions.**

- **P1 (primary) — Unsupported commitment under restricted evidence.** On
  conditions whose condition gold is NEED_EVIDENCE, report per issue:
  **P1a** unsupported ACCEPT, **P1b** unsupported REJECT, **P1c** correct
  NEED_EVIDENCE.
- **P2 (secondary, exploratory) — Unsupported acceptance under sufficient
  evidence on oracle-REJECT issues.** Given the tiny reject sample this is
  case- and interval-based, not a rate estimate.

Statistics use the **issue** as the independent unit; we report exact
Clopper–Pearson intervals and issue-cluster non-parametric bootstrap
(B=10000), and never inflate denominators by counting cells as independent.

## 7. Results

> Classes are kept distinct. **7.1–7.3 are corrective-replication results on
> the original ten issues (associational across protocol versions). 7.4 is
> explicitly exploratory. The eight new issues have no model results yet.**

### 7.1 Primary RQ (P1): unsupported commitment under restricted evidence

Table 1 (from `T2_restricted_commitment_P1.csv`). Condition gold is
NEED_EVIDENCE for all ten issues on both restricted conditions.

| Model | Condition | P1a unsupported ACCEPT | P1b unsupported REJECT | P1c correct NEED |
|---|---|---|---|---|
| deepseek-flash | T2D-T (static) | 0/10 | 0/10 | **10/10** |
| deepseek-flash | T3D-Strict (active) | 0/10 | 0/10 | **10/10** |
| gpt-4.1-mini | T2D-T (static) | 0/10 | 0/10 | **10/10** |
| gpt-4.1-mini | T3D-Strict (active) | **7/10** | 0/10 | 3/10 |

On the static restricted surface both models correctly abstain 10/10. Given
*active* restricted access under the strict policy, GPT commits to ACCEPT on
7/10 issues although the decisive outcomes are unreachable; DeepSeek continues
to abstain 10/10 (it fetched the tier-D artifact in 8/10 cells and still
abstained). The seven GPT issues are 13615, 13974, 15349, 17318, 17630, 21847,
24443; the three correct NEEDs are 19783, 20590, 24213. Pooling the two
restricted conditions yields 7/20 GPT cells but is a repeated-measures count,
not 20 independent samples. The G3-B baseline for GPT strict was 0/10; because
freshness/trust changed with activeness, the increase is consistent with — but
does **not** demonstrate — active-evidence-induced over-commitment (Section 8).

### 7.2 Corrective replication: DeepSeek abstention 9/10 → 1/10

Aggregating NEED over the three sufficient conditions per issue (NEED_ANY on
T3D-Escalate/T2A/T3A), DeepSeek abstained on **9/10** issues under the original
instrument and **1/10** after the protocol repair: **8 issues reversed
NEED→commit, 0 reversed back**, with a single residual (SymPy-13974).
Clopper–Pearson 95% intervals for the NEED_ANY rate are (0.555, 0.997) for
G3-B and (0.003, 0.445) for G3-B.3; the paired-difference issue-cluster
bootstrap 95% CI is **0.5–1.0** (seed 417313, independently reimplemented). We
interpret this as evidence that the originally observed over-abstention was
substantially a **protocol-construct artifact**, and report it strictly as an
**associational before/after contrast**, not as the causal effect of one fix.

### 7.3 Decisions under sufficient evidence

Table `T3_sufficient_appropriateness.csv` scores each sufficient condition
against condition gold (= oracle). Per-condition agreement with gold out of 10:
DeepSeek 9/10 (T3D-Escalate), 9/10 (T2A-T), 10/10 (T3A-T); GPT 8/10, 8/10,
9/10. GPT's single wrong ACCEPT on T3D-Escalate and T2A-T is SymPy-17318
(Section 8.2); its one abstention on a decisive issue is SymPy-17630
(Section 8.3); on active T3A-T 17318 flips to a correct REJECT, leaving only
the 17630 abstention. DeepSeek's single residual abstention is SymPy-13974
(Section 8.4). We report per-condition /10 and do not collapse conditions into
one accuracy number, because doing so would count the same issue three times.

### 7.4 Secondary RQ (P2): unsupported acceptance on REJECT issues — exploratory

There are only **three** oracle-REJECT issues in the original ten (17318,
17630, 19783). Across the full 15 cells (3 × 5) GPT returns unsupported
acceptance in **4/15 cells**; the confirmatory sufficient-regime OR-aggregate
is **2 of 3 issues**, exact Clopper–Pearson 95% **[0.094, 0.992]**, issue
cluster bootstrap **[0.0, 1.0]**. This is severely underpowered: we report the
interval and traceable cases, and explicitly **do not** quote a false-accept
rate. The new pilot adds only two reject issues, so P2 remains exploratory in
the planned validation as well.

### 7.5 Independent-issue pilot status

For the eight new G3-C.1 issues, **no reviewer model predictions have been
run**. The completed artifacts are gold certificates (24 sufficient / 16
NEED), evidence projections with 144/144 clean restricted surfaces, 456/456
HTTP cross-checks, and frozen manifests. These establish the measurement bed;
they contribute **zero** model-performance datapoints and are not used to fill
any Results cell.

## 8. Ablations and Case Studies

### 8.1 Static vs. active restricted access (candidate mechanism)

The only P1a errors arise on the *active* strict condition; the static
restricted condition is 10/10 correct for both models. A partially blind
coding of GPT's seven strict acceptances (codebook frozen before coding; masked
packets D01–D07) assigned primary code **C3 — treating absence of failure
evidence as evidence of absence** — to all seven, co-firing C1 (symptom
resolution) + C2 (coverage completeness) + C5 (provenance/freshness); **C4
(acknowledging the withholding) never fired**. This is a **single AI
rule-based coder with no independent human coder**, so it is a qualitative
hypothesis, and the active/static comparison is confounded across protocol
versions. An activeness-only controlled arm (freshness/trust held fixed) is
required before calling this a demonstrated mechanism.

### 8.2 Case F1 — SymPy-17318: ignoring an already-visible F2P failure

Oracle gold REJECT. On static T2A-T the declared F2P test `test_issue_12420`
**failed** (`assert [4 + I, 0, 1] == []`), yet GPT returned ACCEPT in both
G3-B and G3-B.3; the active T3A-T control on the same issue correctly returned
REJECT. The failure was visible in both surface variants; only the active
condition forced verification. This is a traceable evidence-*interpretation*
failure (sufficient evidence misread), distinct from the insufficiency errors
of 7.1.

### 8.3 Case F2 — SymPy-17630: over-abstention in the opposite direction

On T3A-T GPT saw the failed declared F2P `test_zero_matrix_add` (other FAIL
tokens are xfail markers; P2P regressed/bad-id sets empty) but judged the test
"unrelated to the patch" and returned NEED_EVIDENCE instead of REJECT. This is
a decision-policy over-abstention that relitigates declared-test relevance. It
is the opposite error direction from F1 and is never pooled with false
acceptance.

### 8.4 Case residual — SymPy-13974

DeepSeek returns NEED on T2A-T and T3D-Escalate but ACCEPT on T3A-T.
Fact-checking shows the abstention rests on two incorrect readings: the
declared acceptance test `test_tensor_product_simp` is present and passing
(not missing), and the three logs are not identical (the baseline differs);
the test the model believed missing is added by the candidate patch itself. We
classify this as a residual model interpretation/policy error (n=1), not a
legitimate evidential-standard difference.

### 8.5 Instrument residual: baseline P2P leakage

The tier-1 non-interference scan was 61/61 clean, but a tier-2 minimization
found the *pre-patch* `pass_to_pass_baseline` per-test map surviving the
tier-D projection (all-PASSED, zero FAILED). It cannot reconstruct gold (the
post-patch P2P map is removed), was reachable only by explicit fetch, was seen
by none of the seven error cells (the one GPT cell that saw it, 20590,
abstained; DeepSeek saw it in eight cells and abstained throughout), and has no
causal link to the errors. It must be stripped before any next live run.

## 9. Limitations and Threats to Validity

1. **Gold is PROVISIONAL.** All labels come from one annotator; `annotator2 =
   NOT_OBTAINED`. AI self-review is not independent arbitration. Every rate may
   shift under the planned second-human-plus-senior-adjudication process; we do
   not upgrade gold in this draft.
2. **Small numbers and unit of analysis.** Ten issues (three REJECT) for the
   model results; eight new issues (two REJECT) with no model results. P2
   intervals span essentially [0,1]. Cells are repeated measures, not
   independent data.
3. **Associational cross-version contrast.** The 9/10→1/10 change conflates
   activeness with freshness/trust repair; it must not be given single-cause
   attribution.
4. **Adaptive pilot sampling.** The new-issue enrichment priority is pre-outcome
   but not verbatim pre-registered and changes the selected set; natural and
   enriched queues are not pooled for a natural rate.
5. **Scoped oracle.** ACCEPT means "passes the declared, scoped F2P/P2P and
   symptom checks," not the whole SymPy suite. Two new reject issues also carry
   disclosed *undeclared* collateral test changes (e.g., 15875 has two
   candidate-era collateral failures outside the dataset P2P id set) that do
   not score but bound what "accept" means; these are open for human review.
6. **Partial blinding.** Symptom prose and verbatim patch/probe text can quote
   an issue number (12 of 18 blind packets self-reference the issue number), so
   identity blinding is partial.
7. **Single project and two models.** SymPy-only and two served IDs limit
   external validity; the framework, not cross-project generality, is the
   contribution.
8. **Instrument residual.** The baseline-P2P projection gap (8.5) is a known,
   disclosed non-interference imperfection pending removal.
9. **Probe-revision construct risk (FR1).** The strengthened probe for
   SymPy-19495 was frozen ~24 minutes before the real build, but the prior
   diagnostic had already observed the post-candidate behavior; whether the
   revision was instrument-only correction or post-hoc oracle redefinition is
   reserved for the independent human (FR1), with no AI determination.

## 10. Conclusion

GroundedReview turns "did the agent say the right label?" into two answerable
questions — is the evidence intact, and is it enough to decide — by pairing a
three-way verdict with condition-specific gold and non-interference-checked
evidence grants. A corrective replication shows how a benchmark instrument can
itself manufacture apparent model behavior (9/10 to 1/10 abstention), while on
a repaired system one model still commits to unsupported ACCEPT on 7/10
restricted-but-active cells and, in a traceable case, accepts despite a visible
test failure. These are bounded findings with provisional labels and small
samples; the eight-issue independent bed, a capped 80-cell validation plan, and
an independent human adjudication protocol are prepared so that the next result
either replicates under confirmed gold or is reported as exploratory.

## Appendix

### A.1 Original ten issues (G3-A; gold PROVISIONAL)
24443 (A), 13615 (A), 19783 (R), 20590 (A), 17630 (R), 21847 (A), 15349 (A),
24213 (A), 17318 (R), 13974 (A). Full per-issue × condition grid:
`tables/T1_per_issue_condition_grid_g3b3.csv`.

### A.2 Eight new issues (G3-C.1; gold PROVISIONAL/PENDING, no model results)
Natural: 19346, 22914, 19495, 15875(R). Enriched: 19040, 14248(R), 19637,
16886. Six scoped ACCEPT / two REJECT.

### A.3 Figures and tables
- `figures/fig1_concept.svg` — three-way verdict, two gold tiers, condition ladder.
- `figures/fig2_deepseek_transition.svg` — 9/10→1/10 paired abstention.
- `figures/fig3_gpt_strict_distribution.svg` — GPT strict 0→7 unsupported ACCEPT.
- `figures/fig4_focal_17318.svg` — visible-F2P-failure case.
- `tables/results_summary.json` — all counts + source sha256 provenance.
- `tables/result_inventory.csv/.md` — every finding tagged by result class.
- `tables/T1/T2/T3*.csv` — per-issue grid, P1 counts, sufficient appropriateness.

### A.4 Frozen provenance (source pins)
Corrective replication analysis and independent recomputation, strict audit,
focal-family audit, and the G3-C.1 zero-API audit/freeze are referenced by
sha256 inside `results_summary.json` and `result_inventory.csv`; parent pins
include g3c1_freeze `7a40d231989b`, g3c0_design `ef85962111d4`,
g3b4_result `45fef964f053`, g3b3_result `752a4f2980b2`, and
g3b3_data `8ca2c984faed`. Spend: $0.303539; the planned 80-cell validation is
capped at $2.00 total ($1.00/model) and is **not yet authorized or run**
(see `paper_sprint/experiment80/`).

### A.5 Reproduction
All paper numbers regenerate offline with `$0` via
`-m paper_sprint.scripts.ps_build_tables`, `...ps_inventory`, and
`...ps_build_figures`, reading only frozen stores; mock cells are excluded from
research analysis and no Reviewer API is invoked.
