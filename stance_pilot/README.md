# Stance Pilot — feasibility skeleton

> **Research line (updated):** the main line is now **Evidence-Grounded Agentic Code
> Verification** ("GroundedReview"). The stance/sycophancy material below is retained
> as exploratory analysis only. See `evidence/` and the section
> "Evidence Sufficiency Pilot" at the bottom.

This is a **starter implementation**, not a validated experiment or benchmark release.

Dataset: `Lego-X/SWE-Review-Bench`. The 1,384 rows are **AI-generated candidate PRs**; `resolved` is executable-verification ground truth, not evidence that a human merged the PR.

## Installation
```bash
pip install datasets pyarrow openai
```

## Commands
```bash
python pilot.py select --n-per-label 15 --output selected.jsonl
python pilot.py expand --input selected.jsonl --output conditions.jsonl
# Initial variance check: filter conditions.jsonl to 5 patches, neutral_no_evidence,
# and repeat 3 times per model in fresh sessions:
python pilot.py run --input variance_subset.jsonl --model YOUR_MODEL --repeats 3 --output results.jsonl
python pilot.py analyze --input results.jsonl
```

To construct `variance_subset.jsonl`:
```python
import json
rows=[json.loads(x) for x in open('conditions.jsonl')]
ids=list(dict.fromkeys(r['id'] for r in rows))[:5]
with open('variance_subset.jsonl','w') as f:
    for r in rows:
        if r['id'] in ids and r['condition']=='neutral_no_evidence':
            f.write(json.dumps(r)+'\n')
```

## Non-negotiable checks
1. `patch_sha256` must remain identical across conditions; conditions vary only in appended author statement.
2. `resolved=True` means passes the benchmark verification harness, **not** a real merged PR. Confirm reproducibility and patch-specific validity before publishing claims.
3. The evidence condition is currently a clearly marked **placeholder**, deliberately excluded from model calls by default. Build real immutable evidence artifacts with run commit, tested tree hash, test IDs, timestamps, runner identity, exit status, and raw stdout/stderr; allow the reviewer independently to inspect those records. Never write only 'CI verified'.
4. For mismatched commit experiments, generate an explicit controlled mismatch in the *artifact references*, not in patch or issue; record mismatch provenance privately in experimental metadata.
5. This initial runner is **text-only** and supplies a diff, not repository exploration or actual tool execution. It cannot establish the claimed tool-based verification capability. Full P4 needs a sandbox and deterministic verification API.
6. Same token count is not the same information. Stance-only phrases should be more tightly matched for lengths, polarity, and factual implications before final analysis.
7. `temperature=0` is not a guarantee of deterministic responses; estimate repetition variance empirically.
8. Avoid data leakage by excluding reference patches and ground-truth fields from Reviewer prompts; keep truth only in analysis records.
9. Don't interpret 15/15 artificial prevalence as deployed issue distribution. Report class-conditioned rates and, later, prevalence-sensitive utility.
10. Use paired analysis with patch-level clustering; do not treat multiple condition/repetition outputs as independent patches.

## Fixed in this pass
1. **Stance statements are now 3-way length-matched** (18/18/19 tokens, identical prefix and register, only the conclusion clause differs). The previous `neutral` vs `positive` pair differed in both polarity *and* wording, and there was no `negative` arm.
2. **Evidence is a separate artifact field, never spliced into the statement**, and evidence conditions are omitted entirely when no verified artifact is attached. The old `[EVIDENCE_MISSING: ...]` placeholder was still being sent to the model, which is worse than a fabricated CI line because the model is told the thing is missing *and* invited to use it.
3. **`resolved` / `patch_sha256` / `instance_id` make no appearance in the prompt** (`selfcheck.py` enforces this); previously the model had no way to see ground truth, but nothing checked that.
4. **JSON parsing tolerates code fences and prose**; previously a fenced answer was silently counted as INVALID and the accept rate was biased downward.
5. Added `make_variance_subset.py` (the README told you to paste a snippet) and `selfcheck.py` (offline invariant check, no API cost).

## Known gap, not fixed
`run` is still sequential single-threaded with no retry/backoff. At 30 patches x 3 stances x 3 repeats x 3 models = 810 calls it is fine, but wrap it in `--repeats` retries before scaling. Also `temperature=0` plus identical prompts does **not** guarantee identical outputs across providers, which is exactly what the variance experiment is measuring.

## Revised order of work (agreed)
1. **Variance first**: 5-6 patches x neutral only x 3 repeats x 3 models. If within-model agreement is worse than ~0.8, the paired test has no power and everything downstream is wasted. Run:
   ```bash
   python make_variance_subset.py --n 6 --balanced
   python pilot.py run --input variance_subset.jsonl --model M --repeats 3 --output variance_M.jsonl
   python pilot.py analyze --input variance_M.jsonl
   ```
2. **Evidence Verification API** (minimum viable): serve artifacts over HTTP, `GET /artifact/{run_id}` returns `{run_commit, tree_sha256, test_ids, exit_codes, started_at, runner_id, stdout_digest}`, and `GET /artifact/{run_id}/verify?base_commit=...&patch_sha256=...` re-checks the linkage server-side. The reviewer must be able to *query* it, not just read prose. Then P4 becomes "unverified claims cannot be upgraded to verified facts", which is a protocol property and testable.
3. Only then scale to 30 patches.

---

# Evidence Sufficiency Pilot (`evidence/`)

**Research question.** When an LLM reviewer evaluates a code patch, does providing
verifiable evidence improve its ability to distinguish *symptom resolution* from
*complete patch correctness*? This is an evidence-sufficiency question, not a claim
that reviewing without tools is information-theoretically impossible: the T0 reviewer
can still reason about the code; what it lacks is direct evidence about the hidden
acceptance tests.

Three orthogonal labels per candidate (executed, never inferred):
- `issue_addressed` — a **symptom probe** derived from the issue passes after the
  patch and fails at base commit (guards against vacuous probes);
- `regression_free_scoped` — scoped pre-existing tests still pass (scope is declared
  on each artifact; full SWE-bench PASS_TO_PASS is infeasible locally);
- `merge_acceptable` — all FAIL_TO_PASS pass **and** scoped PASS_TO_PASS pass.

Label classes: **A** = symptom fixed but acceptance unmet (headline;
Issue-Addressed ⇏ Merge-Acceptable), **B** = both, **C** = neither, **D** =
impossible monotone violation (flagged as an error). sympy-16597 is the reference
class A: `even=True ⇒ is_finite` fixed, 74/74 scoped existing tests pass, but 3/3
maintainer FAIL_TO_PASS assertions still fail.

## Conditions (T2/T3 change the action space, not just the prompt)
| Cond | Reviewer sees / can do |
|---|---|
| T0 | Issue + Patch (text-only baseline) |
| T1 | T0 + author's unverified claim |
| T2 | T0 + the **real static test artifact** (readable, no tools) |
| T3 | T2 + callable verification service (fetch artifact / raw logs / server-side linkage recheck) |

Information gain (T2−T0), tool gain (T3−T2), and claim effect (T1−T0) are reported
separately, with token/wall cost per condition.

## Pipeline
```powershell
# 0. cache raw dataset rows (Python 3.13 via uv)
uv run --python 3.13 --with datasets --with pyarrow python -m evidence.cache_raw `
  --ids "sympy__sympy-13798,..."

# 1. build artifacts + truth in the vendored sympy checkout (Python 3.11; old sympy
#    needs distutils). Runs probes before/after patch and pytest per scope file.
uv run --python 3.11 --with mpmath --with pytest python -m evidence.builder

# 2. offline invariants (no API cost)
uv run --python 3.13 python -m evidence.selfcheck

# 3. reviewer-facing sample manifest (truth fields stay offline)
uv run --python 3.13 python -m evidence.manifest

# 4. start the verification service (T3), then run cells
uv run --python 3.13 python -m evidence.server --port 8321
uv run --python 3.13 --with openai python -m evidence.runner --model DEEPSEEK_MODEL

# 5. metrics: UAR (no-evidence vs counter-evidence split), EVSR, merge accuracy
#    (false-approve / false-reject), cost per correct review, paired deltas
uv run --python 3.13 python -m evidence.metrics
```

## Artifacts and integrity
- Content-addressed, HMAC-signed immutable records: `evidence_store/artifacts/`,
  raw logs in `evidence_store/logs/` with sha256 digests committed into the record.
- Sessions bind the served patch identity server-side; `verify` compares the
  artifact's recorded `base_commit`/`patch_sha256` against that identity — restating
  a hash in the prompt cannot forge linkage. Every service call is appended to
  `audit.jsonl` (called? effective? order?).
- Controlled mismatch probes serve another patch's artifact id while keeping the
  artifact internally valid (valid signature); only an actual linkage check exposes
  it. Provenance is kept in `mismatch_meta.json`, never shown to the model.
- Ground truth (`resolved`, `issue_addressed`, `merge_acceptable`, `label_class`)
  never enters a prompt; `selfcheck.py` verifies visibility, signatures, log
  digests, and HTTP linkage enforcement offline.

## Scope honesty
Full PASS_TO_PASS (1.5k–3k tests per instance) is not run locally. The declared
scope is every test file touched by the maintainer test_patch plus the `tests/`
package adjacent to each changed source file; scope files and the dataset P2P total
are recorded on every artifact so the limitation auditable.

## Module map
- `evidence/schemas.py` — labels, hashing, artifact schema, classification
- `evidence/probes.py` — executable per-instance symptom probes
- `evidence/builder.py` — git/pytest orchestration → signed artifact + truth
- `evidence/store.py` — immutable signed store (+ controlled mismatch fixtures)
- `evidence/server.py` — stdlib HTTP verification service + audit log
- `evidence/prompts.py` — T0–T3 prompt construction (visibility controls)
- `evidence/runner.py` — T0–T3 cells; T3 agentic tool loop; token/cost accounting
- `evidence/metrics.py` — UAR / EVSR / merge accuracy / cost / paired deltas
- `evidence/selfcheck.py` — offline integrity invariants
- `evidence/manifest.py` — builds reviewer-facing sample list
- `evidence/cache_raw.py` — caches raw dataset rows with parsed F2P/P2P
