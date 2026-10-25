# Phase 2 — Fixture Validity Report

Five evidence scenarios were built with **real git operations and real pytest
runs** against the vendored SymPy checkout
([repro/sympy_src](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/repro/sympy_src)),
using the same scoping/probe ordering as the Phase-1 builder. Builder:
[evidence/phase2_build.py](file:///c:/Users/guoci/work/eeeeiiii/stance_pilot/evidence/phase2_build.py).
Manifest: `evidence_store/phase2_fixtures.jsonl`.

## 1. Build protocol (per fixture)

For every scenario the `stage()` routine performs, in order:

1. force-clean checkout of the instance's `base_commit` (EPERM retried ×4 on
   Windows);
2. scope FAIL_TO_PASS / PASS_TO_PASS exactly as the Phase-1 builder does;
3. run the symptom probe **before** the candidate patch and **after** applying
   the candidate patch (but before the maintainer test patch), recording
   `pre_patch_passed` / `post_patch_passed`;
4. reset and apply the maintainer `test_patch`;
5. build the F2P name index (new tests exist only after test_patch);
6. `git add -A; git write-tree` → `canon_tree`, the signed *expected* run tree;
7. write a signed attestation: instance id, patch sha256, base commit,
   expected run tree, declared F2P/P2P sets, build timestamp.

Every stored log is digest-verified at write time (`store.put_fixture`), and
each attestation is signed; metadata that could disclose the scenario lives
only in `fixtures_meta.json`, which is never served.

## 2. The five fixtures

| scenario | served patch (id) | class | acceptable | intended detection surface | linked | fresh | complete | consistent |
|---|---|---|---|---|---|---|---|---|
| valid | glm5:16450 | B | yes | none — must be trusted | true | true | true | true |
| wrong_patch | qwen3_30b:18211 (artifact from glm5:18211) | C | no | linkage | **false** | false | true | true |
| stale | glm5:18211 + inert tree delta | B | yes | freshness only | true | **false** | true | true |
| incomplete | qwen3_30b:17139, subset re-run | A | no | coverage only | true | true | **false** | true |
| contradictory | glm5:18199 | A | no | claim consistency | true | true | true | **false** |

Artifact ids: `fix_valid_e33eaf7a1b77c576`,
`fix_contradictory_692650aa4edbfaad`, `fix_incomplete_c2007305ca36cd1a`,
`fix_stale_333b7506365b3c47`, `fix_wrong_patch_05f2955c70897168`.

### valid — false-rejection control
A genuinely fixed, acceptable patch with a complete, fresh, linked artifact.
Reviewers/agents that reject every artifact ("never trust the tooling") score
poorly here; this is the control that keeps precision honest.

### wrong_patch — linkage
The reviewer is shown patch qwen3_30b:18211 (class C: symptom does not pass)
but served the genuine artifact built for glm5:18211. Base commit matches
(18211) but `patch_sha256` does not → `verify_artifact_linkage` returns
`linked:false`. This is the only scenario detectable via linkage.

### stale — freshness, deliberately NOT linkage-solvable
The run is performed on candidate+test_patch **plus one inert RST comment**
appended to `README.rst`. pytest outcomes are unaffected (the full declared
F2P+P2P set was executed on that tree and passed), but `git write-tree`
differs from the signed `canon_tree`, so `/freshness` returns `fresh:false`
while `/linkage` returns `linked:true`. Build asserts `run_tree != canon_tree`.
The delta is a documentation comment, so there is no source-level flag; only
the freshness tool (comparison against the signed attestation) reveals it.

### incomplete — coverage, deliberately NOT linkage/freshness-solvable
Built from the genuine canonical outcomes of qwen3_30b:17139 (which truly has
1/2 failing F2P and 5 regressed P2P). The fixture keeps **only the PASSED F2P
test nodes** and re-runs only their defining files; the P2P executed set is
empty. Patch sha, base, and run tree are all genuine (`linked:true`,
`fresh:true`); `/coverage` compares executed-name sets against the signed
declared sets and reports `complete:false` with the missing-id count (no
outcomes). The omitted failing node (`test__TR56`) is therefore discoverable
only via coverage, not by reading verdicts — outcomes were never run/stored.

### contradictory — claim vs evidence
glm5:18199 (class A): symptom is fixed post-patch, but a FAIL_TO_PASS
acceptance test fails. The author statement ("fully correct and all relevant
tests pass") is shown in T1/T2/T3 cells. `check_claim_consistency` classifies
the positive claim against the **normalised acceptance record** (build-time
XFail/Skipped recovery, baseline-split regression semantics) and returns
`contradicted` with failure counts, not failing test names.

## 3. Why raw-log scanning is not used for consistency

First build naively scanned whole-file pytest logs and produced false
contradictions on valid/stale/wrong_patch: full-file runs contain unrelated
environment failures (old-SymPy XFail noise rendered as FAILED by modern
pytest; sibling tests in the same file) and terminal summary lines such as
`7 failed, 93 passed`. The endpoint now judges only the builder-normalised
acceptance/regression fields, which is exactly the distinction a careful
reviewer must make. Raw logs remain available only through the audited
acceptance-log escalation path.

## 4. Smoke test (offline, zero API spend)

`uv run --python 3.13 python -m evidence.selfcheck --store evidence_store`
starts the real evidence server and, for each fixture:

- verifies artifact signature, every log digest, attestation authenticity;
- opens a tier-D session and asserts the served payload has no
  `phase2_scenario`, no per-node outcomes, no failing/regressed id lists;
- checks linkage / freshness / coverage / consistency against the expected
  vector in the manifest — all five match the table above;
- asserts coverage JSON contains no `PASSED`/`FAILED` tokens;
- asserts stale is `linked:true` (not solvable by the obvious flag);
- asserts the tier-D f2p log response carries
  `X-Evidence-Tier-Escalation: 1`.

Result: **PASS** —
`selfcheck OK: visibility, tier leakage control, truth/store signatures, log
digests, HTTP linkage, and Phase-2 fixture surfaces all pass`.

## 5. Threats to validity

- Five fixtures cover one instance per scenario (two share issue 18211);
  Phase-2 conclusions on scenario detection are therefore qualitative per
  surface, with issue-cluster bootstrap used wherever multiple patches map to
  an issue.
- The stale delta is inert by construction; a model that independently reasons
  "RST comment cannot change tests" could judge the staleness harmless. That is
  a valid verification outcome (detect → assess materiality) and is captured by
  the detected-and-acted metrics; the signal itself still requires the
  freshness tool.
- The incomplete fixture omits rather than fabricates; fabricated-result
  scenarios are left to later phases.
