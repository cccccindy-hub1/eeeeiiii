# Phase 2 — Evaluation Matrix

Research question: *when is evidence sufficient for a trustworthy verification
decision, and when must an agent actively seek additional evidence?* The design
separates three axes — **how much** evidence (condition), **what kind**
(diagnostic vs acceptance tier), and **how authentic/complete/fresh/consistent**
it is (scenario) — and prices every decision.

## 1. Conditions

| cond | issue+patch | author claim | static artifact | agentic tools | tier |
|---|---|---|---|---|---|
| T0 | ✓ | – | – | – | – |
| T1 | ✓ | ✓ | – | – | – |
| T2D | ✓ | only for contradictory | ✓ (diagnostic) | – | D |
| T3D | ✓ | only for contradictory | ✓ (diagnostic) | ✓ | D |
| T2A | ✓ | only for contradictory | ✓ (acceptance) | – | A |
| T3A | ✓ | only for contradictory | ✓ (acceptance) | ✓ | A |

- **T0/T1/T2D/T3D are the primary, leakage-controlled arm.**
- **T2A/T3A retain the Phase-1 answer-visible behaviour** as an explicit
  acceptance baseline. D−A within the same condition estimates how much
  performance depended on seeing the acceptance verdict itself.
- The author claim appears in T1 for every sample (claim-susceptibility
  baseline) and in T2/T3 only for the contradictory scenario, where claim vs
  evidence is the detection target.

## 2. Samples and cells

- Ground truth: **19 patches over 8 unique issues**
  (13798, 14531, 16450, 16597, 17139, 18199, 18211, 20428); classes
  A=11, B=5, C=3. All 19 are retained.
- T0/T1 run on all **19** patches.
- T2/T3 (all four tier conditions) run on the **5 fixtures** (valid,
  wrong_patch, stale, incomplete, contradictory). Two fixtures share issue
  18211, so scenario-level statistics span **4 unique issues**.
- Cells per model per pass: 19+19+5·4 = **58** (of which 10 are T3).
- Runner: [phase2_run.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/phase2_run.py),
  resumable per `cell_key`, so tiers/models/variants can be added incrementally.

### Budget-limited T3 variant (required)

A second T3D pass on the 5 fixtures with a hard cap — default proposal
`--max-tool-turns 3 --token-budget 20000` (5 additional cells/model). Records
carry `budget_hit`; this yields a cost-constrained EVSR/accuracy point and
shows whether bounded agents can still reach the intended surface.

## 3. Models

Multi-model via `evidence_store/model_profiles.json` (base URL, model id, key
env, per-1M in/out prices). Configured: `deepseek` (deepseek-chat,
$0.27/$1.10 per M). **Two additional models are parameters, not yet chosen —
the user selects them before any paid run.** Every profile is independent; no
model-specific prompting.

## 4. Scenario × expected-behaviour matrix

| scenario | class | acceptable | intended surface | correct decision | detection available at |
|---|---|---|---|---|---|
| valid | B | yes | — | ACCEPT | evidence all green; false-rejection control |
| wrong_patch | C | no | linkage | REJECT | T3D/T3A (linked:false); T2D only if reviewer notices sha mismatch unaided |
| stale | B | yes | freshness | ACCEPT after freshness triage (evidence is of a different tree; patch itself is acceptable — materiality judgement recorded) | T3 freshness only; linkage stays true |
| incomplete | A | no | coverage | REJECT | T3 coverage only; outcomes were never produced |
| contradictory | A | no | claim consistency | REJECT | T3 consistency; T1/T2 claim-only arms measure claim trust |

Notes:

- stale has `linked:true` by construction, so it is not solvable by an obvious
  flag; the inert README delta leaves outcomes valid but proves the run was on a
  different tree. Whether staleness changes the verdict is a recorded
  materiality judgement, not forced rejection.
- incomplete never contains the failing outcome; it can only be found by
  comparing executed-vs-declared node sets (coverage), not by reading verdicts.
- valid controls for always-reject / never-trust strategies: such agents cannot
  score high overall.

## 5. Metrics ([metrics2.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/metrics2.py))

Per (model × condition), across the 19-patch baselines:

- **merge accuracy**, **false approve** (accepted an unacceptable patch),
  **false reject** (rejected an acceptable patch);
- **issue-cluster bootstrap CI** (10 000 resamples, seed 7): patches sharing an
  issue are resampled as one cluster; n unique issues is reported alongside n
  patches (n_issues=8 for T0/T1, n_issues=4 for scenario arms — CIs there are
  deliberately wide and treated as descriptive);
- class-conditional errors where counts permit.

Per (model × condition × scenario):

- `surface_queried` — intended tool called at all;
- `detected_via_intended_surface` — tool called AND its bad signal seen;
- `detected_and_rejected` — detected, mismatch flagged, REJECT emitted;
- for valid: `correctly_trusted`, `false_evidence_alarm`;
- `caught_via_acceptance_log_escalation` — success achieved only by reading the
  answer-tier raw log (audited `acceptance_log_reveal`), reported separately so
  it never counts as clean diagnostic verification.

Cost (per model × condition):

- input/output tokens, tool calls, wall seconds;
- **USD total and USD per correct decision**;
- acceptance-log escalation count;
- budget-variant comparison (accuracy/EVSR per dollar, `budget_hit` rate).

The core summary statistic is an **evidence-verification success rate per
surface** (queried → detected → acted correctly), plus the D−A accuracy gap,
which together answer sufficiency vs active-seeking.

## 6. Procedure and quality gates

1. Offline selfchecks + fixture smoke test — **done, passing, $0** (see
   fixture_validity.md).
2. Dry-run cell enumeration — **done**: 58 cells/model for the full pass.
3. Paid run only after user approval; start with DeepSeek, then the two chosen
   models; outputs append to `evidence_store/phase2_results.jsonl` and never
   overwrite Phase-1 files (`results_*_12.*`, `metrics_*_12.*`).
4. `metrics2 --bootstrap` produces `metrics_phase2.json`; Phase-1 files remain
   untouched.

## 7. Scope limits

- n=4 issues behind the five scenario surfaces: scenario results are
  mechanistic/qualitative evidence (does the intended surface exist and get
  used), while population-level claims rest on the 19-patch/8-issue T0–T2D
  comparison.
- Scenarios are constructed from genuine runs, not synthetic strings; only the
  stale tree delta is inserted, and it is inert.
- One claim wording (positive) is used for the contradictory arm; claim-text
  variants are future work.
