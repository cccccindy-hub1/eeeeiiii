# GroundedReview — Results Draft (E1 + CEE v1.1) and Threats to Validity

Status: offline analysis draft, zero paid API calls. All numbers are read back
from frozen artifacts; this document does not re-run any model and does not
change any frozen Prompt / Gold / Bundle / result / metric.

- E1 cross-model metrics: `evidence_store_ev1/ev1_gpt41mini_paired_metrics.json`
- CEE v1.1 metrics: `evidence_store_cee/cee_v11_metrics.json`
- CEE v1.1 construct / leakage audit:
  `evidence_store_cee/cee_v11_label_leakage_audit.json`
- CEE v1.1 final report: `evidence_store_cee/cee_v11_final_report.json`

---

## 1. Setup and the two capabilities being separated

GroundedReview studies an agentic code reviewer that must emit one of three
verdicts — **ACCEPT**, **REJECT**, **NEED_EVIDENCE** — under an asymmetric
standard: reject on a single credible applicable (linked and fresh) failing
check even when coverage is incomplete; accept only on linked, fresh,
complete, failure-free evidence; otherwise abstain.

End-to-end agent performance conflates two capabilities:

1. **Evidence acquisition / verification policy** — whether the agent calls
   enough tools, escalates, and surfaces the evidence it needs; and
2. **Evidence interpretation** — whether, *given* the evidence, it maps the
   facts to the correct verdict.

We use two frozen protocols to separate them.

- **E1** (22 fixtures × 5 visibility/tool conditions × 2 models = 110 cells
  per model) measures the full agentic workflow: the model decides how many
  verification tools to call and whether to escalate. We report against two
  standards that are never averaged: `oracle_gold` (the verdict supportable
  from complete information) and `condition_gold` (the verdict supportable
  from what that condition actually exposes).
- **CEE-FIXED** (the same 22 fixtures, one single tool-free turn per model,
  protocol `cee-fixed-v1.1`) hands both models **byte-identical, complete,
  pre-adjudicated evidence bundles** and no tools. Both models received
  `response_format={"type":"json_object"}`; a strict five-property schema was
  enforced **locally** (no field repair). CEE isolates interpretation.

The two protocols are compared side by side only; their accuracy is never
pooled, and no causal effect size is computed across them.

Sample: **22 fixtures over 10 distinct issues** (classes 7
sufficient-positive / 6 decisive-negative / 9 insufficient). Cells are
clustered by issue; all confidence intervals are issue-cluster bootstrap
(seed 7, 10 000 resamples) and all paired tests are reported as descriptive.

## 2. E1 — end-to-end workflow performance

Pooled over the five conditions (110 cells/model), under `oracle_gold`:

| Metric (E1, pooled oracle standard) | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| Decision appropriateness | 0.591 (65/110) CI [0.525, 0.675] | 0.673 (74/110) CI [0.590, 0.743] |
| Appropriate abstention (of 45 NEED-gold) | 0.911 (41) | 0.733 (33) |
| Over-abstention (of 65 decisive/accept-gold) | 0.631 (41) | 0.323 (21) |
| Unsupported ACCEPT (false commit, of 45 NEED-gold) | **0** | **7 (0.156)** |
| Unsupported REJECT (of non-REJECT-gold) | 4 (0.050) | 5 (0.063) |
| Cells with escalation granted | 22/22 | 12/22 |

Paired cross-model Δ(GPT−DS) = **+0.082**, cluster CI **[−0.019, 0.167]**,
24 GPT-only-correct vs 15 DS-only-correct discordant cells, exact McNemar
**p = 0.20** (descriptive).

The two models erred on opposite sides. DeepSeek rarely committed without
evidence (0 unsupported accepts) but abstained on 63.1% of cells that already
contained decisive or sufficient evidence, and escalated on every cell.
GPT-4.1-mini abstained less but produced 7 unsupported accepts; all 7 occurred
in the static acceptance condition T2A-T (false-commit rate 0.778 on its
NEED-gold cells there), where green-looking but inapplicable records were
presented without tools. In the fully-empowered active condition T3A-T both
models reached oracle DA 0.864 (DS over-abstention 0.154, GPT 0.077).

Read literally, E1 shows different *acquisition* behaviour (DeepSeek
22/22 escalations vs GPT 12/22) and opposite *surface* failure modes, but it
cannot say whether the divergence originates in acquisition or in
interpretation, because the two models did not see identical evidence.

## 3. CEE — interpretation of identical, fixed evidence

In CEE both models received the exact same bundle bytes, the same prompt, and
no tools. All 44 cells parsed; there were **0 INVALID, 0 AMBIGUOUS, 0 API
errors, 0 tool calls**.

| Metric (CEE-FIXED) | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| Decision appropriateness | **0.909** (20/22) CI [0.789, 1.000] | **0.818** (18/22) CI [0.682, 0.952] |
| Verdict distribution | A7 / R4 / N11 | A7 / R2 / N13 |
| Always-NEED baseline (= 9/22) | 0.409 | 0.409 |
| Sufficient-positive (7) | 7/7 | 7/7 |
| Insufficient (9) | 9/9 | 9/9 |
| Decisive-negative (6) | 4/6 | 2/6 |
| Over-abstention | **2** | **4** |
| Unsupported ACCEPT | **0** | **0** |
| Unsupported REJECT | **0** | **0** |

Both models accepted every sufficient-positive bundle, abstained on every
insufficient bundle, and produced **no** unsupported accept or reject. The
**only** errors were over-abstention on decisive-negative (REJECT-gold)
bundles: DeepSeek 2/6, GPT 4/6.

Paired over the 22 bundles, Δ(DS−GPT) = **+0.091**, cluster CI
**[0.000, 0.217]** (lower bound exactly zero), 3 DS-only-correct vs 1
GPT-only-correct discordant pairs, exact McNemar **p = 0.625**. At this
sample size there is **no reliable cross-model difference** in fixed-evidence
interpretation.

### 3.1 The decisive-negative error set

- **Both wrong (intersection):** `cee_58d93f77…` (wrong_patch; record
  unlinked + stale, acceptance green 1/1, 54/54; REJECT is supported *only*
  by the probe line "issue symptom reproduces after patch: yes").
- **DeepSeek-only wrong:** `cee_5cfbc476…` (stale_persists; linked but not
  fresh; probe reports the symptom persists; a failing FAIL_TO_PASS id is
  listed but inapplicable because the tree is stale).
- **GPT-only wrong (3):** `cee_13b04ca1…`, `cee_76028c65…`,
  `cee_b203936c…` — all linked + fresh with a **concrete failing test id**
  (`test_latex_basic`, `test_Permutation_subclassing`,
  `test_comparisons_with_unknown_type`) but with coverage marked incomplete.
  GPT abstained where the stated policy says to reject on a single applicable
  failure even under incomplete coverage; DeepSeek rejected.

The two models' residual hesitation therefore has a different texture: GPT
let incomplete coverage veto an otherwise applicable concrete failure (3
cases), whereas DeepSeek's two abstentions sit on the issue-reproduction
(probe) channel rather than the maintainer acceptance channel.

## 4. Side-by-side mechanism reading (not a causal contrast)

| | DeepSeek-flash | GPT-4.1-mini |
|---|---|---|
| E1 pooled oracle DA | 0.591 | 0.673 |
| E1 over-abstention | 0.631 | 0.323 |
| E1 unsupported accept | 0 | 7 |
| E1 T3A-T (full active evidence) oracle DA | 0.864 | 0.864 |
| CEE fixed-evidence DA | 0.909 | 0.818 |
| CEE over-abstention | 2 | 4 |
| CEE unsupported accept / reject | 0 / 0 | 0 / 0 |

On identical, complete evidence the cross-model gap shrank and changed sign
(E1 GPT +0.082 → CEE DS +0.091), GPT's unsupported accepts disappeared
(7 → 0), and DeepSeek's over-abstention fell sharply (41 cells → 2). This
pattern is **consistent with** a substantial share of the E1 divergence being
driven by evidence acquisition / verification policy rather than by an
inability to read evidence.

It is **not** a causal decomposition. (i) GPT already reached 0.864 in T3A-T
with full active evidence, so acquisition and framing are not cleanly
separable; (ii) E1 is multi-turn/tool-using while CEE is a single turn with
pre-adjudicated metadata — the *rendering* of evidence differs, not just its
availability; (iii) the DeepSeek backend id does not pin identical weights
across E1 and CEE (see Threats); and (iv) n = 22 / 10 issues with wide,
zero-touching intervals makes every cross-model statement exploratory.

## 5. What CEE measures — construct-validity finding

A zero-API audit (`cee_v11_label_leakage_audit.json`) scanned the exact
served bundle bytes and attempted to recompute the gold label from rendered
fields alone.

- **No literal label leakage.** No bundle body contains the gold token, an
  evidence-class name, the internal scenario name, `decisive_failure` /
  `sufficient_success`, a `decision:`/`verdict:` line, or an imperative
  answer sentence. The only `ground truth` phrase is the item-invariant
  prompt sentence *"Ground truth about mergeability is never given to you."*;
  the word *verdict* appears only in the heading **INTEGRITY VERDICTS**.
  Token hits such as "the answer is 0!" and `def valid(x)` are verbatim
  issue/patch code text, not injected answers.
- **But the decision is fully executable from what is shown.** The prompt
  head states the complete asymmetric rule, and each bundle renders every
  boolean rule input as an adjudicated yes/no (linked / fresh / complete /
  signature authentic; symptom present-before / reproduces-after). Applying
  the frozen `oracle_gold` rule to those rendered fields reproduces the gold
  label on **22/22** bundles.
- **Two of six REJECT cases rest on a derived binary, not a primary failure.**
  For the wrong-patch and stale-persists bundles the acceptance record is
  green and the *only* applicable ground for REJECT is the rendered probe
  verdict "reproduces after patch: yes"; the raw probe log is not shown. The
  other four decisive-negative bundles show a concrete failing test id.

**Accurate construct name.** CEE measures **faithful execution of a stated
review policy over pre-adjudicated evidence facts**, *not* unaided inference
from primary logs (it does not test whether a model could itself derive
linkage, freshness, coverage, or symptom persistence) and not open-ended
evidence grounding. The high DA (0.91/0.82) should be read as policy-following
on adjudicated facts; the residual errors localise where the policy is
genuinely hard — committing to REJECT on decisive-negative evidence.

---

# Threats to Validity

1. **Small number of independent issues (10).** The 22 fixtures are mirrored
   variants of 10 issues; cells within an issue are not independent. We
   cluster bootstrap by issue and report McNemar only as descriptive. With
   classes of 7/6/9, intervals are wide (CEE DeepSeek CI reaches 1.0; the
   paired CI lower bound is exactly 0) and the study is underpowered for any
   definitive cross-model claim.

2. **Mirror-fixture dependence.** The 22 bundles share issue text, patches
   and probes across variants; apparent per-cell agreement overstates the
   independent evidence, and results may not generalise beyond SymPy or these
   issue types. Replication on new, independent issues is required before
   external claims.

3. **Model-version drift (DeepSeek).** The API returns the id string
   `deepseek-flash`, identical to the E1 id, but vendor documentation
   (2026-10-23/24) identifies the current backend as DeepSeek-V4.1-Flash-1017.
   Same id string does not establish same weights, so the DeepSeek
   E1→CEE comparison is **not** a same-version reproduction; a model-version
   contribution to the observed shift cannot be excluded. GPT-4.1-mini
   (`gpt-4.1-mini-2025-04-14`) matched the E1 served id.

4. **Output-protocol differences across experiments.** E1 mixed strict
   `json_schema` (DeepSeek) with `json_object`/plain decision rounds (GPT);
   CEE v1 (strict schema on both) could not run because DeepSeek rejected
   `json_schema`, so CEE v1.1 used unified `json_object` with strict **local**
   validation on both. All 44 CEE outputs were locally valid, but CEE v1.1 is
   a different protocol from E1 and from the aborted v1; accuracies must not
   be merged, and the small format change is a (minor) residual confound.

5. **Evidence-rendering difference (construct bounds).** Beyond removing
   tool-use, CEE hands over **pre-adjudicated** linked/fresh/complete and
   symptom verdicts that E1 agents had to obtain and (in part) infer. The
   audit shows the label is mechanically recoverable on 22/22 bundles by
   rule application, and 2/6 REJECT cases rely solely on a derived probe
   binary. Consequently CEE isolates *policy execution on adjudicated facts*,
   not primary-evidence grounding; E1↔CEE differences conflate acquisition,
   single-turn framing, and metadata pre-adjudication and cannot be causally
   attributed to acquisition alone. One stale bundle additionally lists a
   FAIL_TO_PASS id that the normalized oracle maps exclude; freshness makes it
   inapplicable, but readers of only the rendered aggregate counts could be
   misled (the adjudicated `fresh: no` line is what makes the rule fire
   correctly).

6. **Locality of the symptom probe.** The issue-reproduction probe is a
   single issue-author-derived, local behavioural check, not the maintainer
   test suite. Treating "symptom reproduces after patch" as decisive negative
   evidence encodes the benchmark's dual-channel gold rule; probes can be
   brittle or incomplete, and on two fixtures this binary is the sole REJECT
   ground, amplifying dependence on probe correctness.

7. **Potential label leakage / answerability (audited, not assumed).** No
   literal gold or class token is served, but the explicit rule plus all
   boolean inputs make the task near-deterministic; this caps the strength of
   any "the models understand evidence" claim and is the main reason the
   construct is named policy execution. Relatedly, the runner persisted only
   the parsed decision and a hash of the raw response, **not** the model
   `reason`/`missing_evidence` text, so qualitative error analysis rests on
   served inputs and verdicts rather than quoted rationales (re-calling to
   retrieve rationales was not authorised).

8. **Operational and cost transparency.** 44 cells were scored, but 46 paid
   completions were issued: two early DeepSeek calls on the first bundle
   returned HTTP 200 and were billed, then failed in the local client (SDK
   attribute bug) before any row was written. They were not scored or
   retried as decisions. Recorded scored spend was **$0.044253**; including a
   conservative bound for the two faulted calls the total is ≈ **$0.0554**,
   under the $1.00 hard cap. These must remain distinguished in any
   reproduction report. Determinism also relies on `temperature=0`, which
   providers do not guarantee to be fully deterministic.

**Bottom line.** E1 and CEE together support a focused, exploratory claim:
when two reviewers acquire evidence differently they fail in opposite ways,
but when given the same complete, adjudicated evidence they converge,
committing no unsupported accepts/rejects and differing only in willingness
to REJECT on decisive-negative evidence. The decisive-negative boundary — and
specifically letting incomplete coverage or a non-acceptance-channel probe
induce abstention — is the residual, construct-valid target worth studying
next, on new independent issues and with raw (not pre-adjudicated) evidence
if the goal is to test evidence grounding rather than policy execution.
