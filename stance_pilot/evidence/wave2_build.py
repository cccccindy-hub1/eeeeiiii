"""Build Wave-2 mirror fixtures with REAL git/pytest executions (offline).

Four integrity archetypes (DW2-4), drawn from the 4 NEW issues' empirical
wave2_truth.jsonl (11 labelled candidates) and their genuine canonical
artifacts (built by evidence.wave2_truth under 3.9 + pytest 8.4.2):

  w2_valid             GOOD patch, symptom GONE; copy of the genuine canonical
                       artifact -> linked/fresh/complete, zero failure -> ACCEPT
  w2_stale             GOOD patch, full declared execution on a tree one inert
                       comment away from canonical -> fresh=false, symptom gone
                       -> NEED_EVIDENCE (acceptance success is not applicable)
  w2_stale_bad         BAD patch, full execution on the inert tree, genuine
                       failures, symptom GONE -> oracle NEED_EVIDENCE (fresh
                       gates the acceptance failure; diagnostic channel is
                       gone); T2A institutionally presents the failures.
  w2_stale_persists    BAD patch, full execution on the inert tree, genuine
                       failures, symptom PERSISTS -> the diagnostic channel is
                       independent of freshness -> REJECT in every condition.
  w2_incomplete_good   GOOD patch; honest replay of the exact canonical 3-file
                       batch(es) for a subset of PASSING declared f2p, omitting
                       one passing declared f2p and ALL scoped p2p ->
                       complete=false, zero failure -> NEED_EVIDENCE
  w2_decisive_bad      BAD patch; replay keeps a genuinely FAILING declared f2p
                       (canonical outcome must be reproduced exactly) ->
                       complete=false but linked/fresh executed failure ->
                       REJECT (completeness gates ACCEPT, never REJECT).

Namespace discipline (AC-W2-7 / TR-5.3):
  * scenario ids are all w2_*; fixture_id() therefore yields fix_w2_* ids.
  * provenance meta is written to the SEPARATE wave2_fixtures_meta.json
    (ArtifactStore(fixtures_meta_name=...)); frozen fixtures_meta.json is
    never opened for writing.
  * the manifest is the independent evidence_store/wave2_fixtures.jsonl.
  * no Phase-1/2/3 file is modified.

Every expected fact is recomputed from the SIGNED built record via
evidence.visibility (identical formulas to the server endpoints) and
cross-checked against evidence.gold_w2.oracle_gold; labels are never copied.
A replay whose canonical batch would leak an omitted declared node, or whose
replayed status != the signed canonical status, raises and is reported BLOCKED
without relaxing the construction (TR-5.2 / TR-5.4).

Run:
  uv run --python 3.9 --with mpmath --with "pytest==8.4.2" \
      python -m evidence.wave2_build [--scan-only]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.builder import (now, changed_files, scope_test_files,
                              build_test_name_index, map_names_to_files,
                              run_probe, WORK)
from evidence.phase2_build import (_git_retry, _write_tree, _apply_candidate,
                                   _apply_test_patch, POSITIVE_CLAIM,
                                   copy_canonical_fixture)
from evidence.phase3_build import (build_mirror_stale,
                                   build_mirror_batch_replay,
                                   _canonical_f2p_status)
from evidence.schemas import make_artifact_id, sha256_text
from evidence.store import ArtifactStore
from evidence.visibility import load_fixture_facts
from evidence.gold_w2 import (_oracle_inputs_from_facts, oracle_gold,
                              GOLD_VERSION)

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

RESTORE_HEAD = '7121bdf1facdd90d05b6994b4c2e5b2865a4638a'
PROBE_DIR = WORK / 'probes_wave2'

# Archetype tags used in the build audit.
VALID = 'w2_valid'
STALE_GOOD = 'w2_stale'
STALE_BAD = 'w2_stale_bad'
STALE_PERSISTS = 'w2_stale_persists'
INCOMPLETE_GOOD = 'w2_incomplete_good'
DECISIVE_BAD = 'w2_decisive_bad'

# Deterministic build plan (wave2_truth.jsonl order is the tie-break; ids are
# global generator:instance names so selections are unambiguous). 12 fixtures;
# the optional 13th (a second decisive replay on sympy-13091) is added only if
# its leak guard passes on the real canonical batches.
PLAN = [
    # --- VALID: every GOOD, symptom-gone, fully-green canonical candidate ---
    {'scenario': VALID, 'id': 'glm5_500:sympy__sympy-12419'},
    {'scenario': VALID, 'id': 'qwen3_coder_30b_500:sympy__sympy-12419'},
    {'scenario': VALID, 'id': 'glm5_500:sympy__sympy-12481'},
    {'scenario': VALID, 'id': 'qwen3_30b_instruct2507_500:sympy__sympy-12481'},
    {'scenario': VALID, 'id': 'qwen3_coder_30b_500:sympy__sympy-12481'},
    {'scenario': VALID, 'id': 'glm5_500:sympy__sympy-13091'},
    # --- STALE: GOOD full run on inert tree (symptom gone) ---
    {'scenario': STALE_GOOD, 'id': 'glm5_500:sympy__sympy-12419'},
    {'scenario': STALE_GOOD, 'id': 'glm5_500:sympy__sympy-12481'},
    # --- STALE_BAD: BAD full run, genuine failures, symptom GONE -> NEED ---
    {'scenario': STALE_BAD, 'id': 'glm5_500:sympy__sympy-12489'},
    # --- STALE_PERSISTS: BAD full run, symptom PERSISTS -> REJECT via P ---
    {'scenario': STALE_PERSISTS,
     'id': 'qwen3_30b_instruct2507_500:sympy__sympy-12489'},
    # --- INCOMPLETE_GOOD: the ONLY GOOD candidate with >=2 passing f2p ---
    {'scenario': INCOMPLETE_GOOD, 'id': 'glm5_500:sympy__sympy-13091',
     'omit_pass': 'test_equality'},
    # --- DECISIVE_BAD: keep the genuine failing f2p (single declared f2p) ---
    {'scenario': DECISIVE_BAD, 'id': 'glm5_500:sympy__sympy-12489'},
    # --- optional 13th: second decisive issue (13091), keep one failing f2p ---
    {'scenario': DECISIVE_BAD, 'id': 'qwen3_coder_30b_500:sympy__sympy-13091',
     'keep_fail': 'test_comparisons_with_unknown_type', 'optional': True},
]


# ---------------------------------------------------------------------------
# Wave-2 staging (probe lookup points at probes_wave2, never probes.probe_source)
# ---------------------------------------------------------------------------

def w2_stage(store, raw, attest=True):
    """Clean base checkout -> wave-2 issue probe pre/post -> maintainer
    test_patch -> canonical write-tree + scope maps + signed attestation.
    No acceptance pytest runs here.

    The signed canonical attestations were first captured in Task 4
    (wave2_truth.restage_attestation); they are rewritten only if missing so
    their built_at provenance stays stable across rebuilds."""
    iid = raw['instance_id']
    probe_path = PROBE_DIR / f'{iid}.py'
    if not probe_path.exists():
        raise RuntimeError(f'wave-2 probe missing: {probe_path}')
    _git_retry('checkout', '-f', raw['base_commit'])
    _git_retry('clean', '-fdq')

    code_files = changed_files(raw['model_patch'], code_only=True)
    scope_files = scope_test_files(raw, code_files)
    pre_ok, pre_log = run_probe('probe', probe_path)

    _apply_candidate(raw)
    post_ok, post_log = run_probe('probe', probe_path)
    _apply_test_patch(raw)

    idx = build_test_name_index(scope_files)
    p2p_names = [n for n in raw['PASS_TO_PASS'] if n in idx]
    canon_tree = _write_tree()
    patch_sha = sha256_text(raw['model_patch'])
    existing = store.get_attestation(iid, patch_sha)
    if attest and (existing is None
                   or existing.get('expected_run_tree') != canon_tree):
        store.put_attestation({
            'instance_id': iid,
            'patch_sha256': patch_sha,
            'base_commit': raw['base_commit'],
            'expected_run_tree': canon_tree,
            'declared_fail_to_pass': list(raw['FAIL_TO_PASS']),
            'declared_p2p_scoped': list(p2p_names),
            'declared_scope_files': scope_files,
            'built_at': now(),
        })
    elif existing is not None and existing.get('expected_run_tree') != canon_tree:
        raise RuntimeError(
            f'canonical run tree drift for {iid}: attestation says '
            f'{existing.get("expected_run_tree")}, rebuilt {canon_tree}')
    symptom_log = ('### BASELINE (pre-patch)\n' + pre_log +
                   '\n\n### POST candidate patch\n' + post_log)
    return {
        'scope_files': scope_files, 'idx': idx, 'p2p_names': p2p_names,
        'canon_tree': canon_tree, 'patch_sha': patch_sha,
        'tp_sha': sha256_text(raw['test_patch']),
        'pre_ok': pre_ok, 'post_ok': post_ok, 'symptom_log': symptom_log,
    }


# ---------------------------------------------------------------------------
# Canonical-batch replay planning (pure over a staged ctx; leaks => infeasible)
# ---------------------------------------------------------------------------

def replay_layout(raw, ctx, keep):
    """Reproduce build_mirror_batch_replay's batch math WITHOUT pytest.

    Returns (batches, leaked_omitted_f2p). A kept node's canonical 3-file batch
    is infeasible if it also defines an OMITTED declared f2p node (the raw log
    would then leak a hidden acceptance outcome)."""
    f2p_map = map_names_to_files(list(raw['FAIL_TO_PASS']), ctx['scope_files'],
                                 ctx['idx'])
    p2p_map = map_names_to_files(ctx['p2p_names'], ctx['scope_files'], ctx['idx'])
    all_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    replay_idx = set()
    unmapped = [n for n in keep if not f2p_map.get(n)]
    for nm in keep:
        fl = f2p_map.get(nm)
        if not fl:
            continue
        for i in range(0, len(all_files), 3):
            if fl[0] in all_files[i:i + 3]:
                replay_idx.add(i)
    batches = [all_files[i:i + 3] for i in sorted(replay_idx)]
    omitted = [n for n in raw['FAIL_TO_PASS'] if n not in keep]
    batch_files = {f for b in batches for f in b}
    leaked = [n for n in omitted if set(f2p_map.get(n, [])) & batch_files]
    return batches, leaked, unmapped


# ---------------------------------------------------------------------------
# Eligibility scan (read-only over canonical artifacts; git for replay layout)
# ---------------------------------------------------------------------------

def _symptom(truth_row, ctx=None):
    lp = truth_row.get('label_provenance', {})
    pre = lp.get('symptom_pre_patch_passed')
    post = lp.get('symptom_post_patch_passed')
    if ctx is not None:
        pre = ctx['pre_ok'] if pre is None else pre
        post = ctx['post_ok'] if post is None else post
    return {'pre_patch_passed': pre, 'post_patch_passed': post}


def scan(store, raw_by_id, truth_by_id):
    """One audit entry per empirical truth row: canonical artifact presence,
    real signed f2p/p2p outcomes, symptom polarity, archetype eligibility."""
    entries = []
    for tr in read_jsonl_path('wave2_truth.jsonl'):
        raw = raw_by_id.get(tr['id'])
        if raw is None:
            continue
        aid = make_artifact_id(tr['instance_id'], tr['patch_sha256'])
        got = store.get(aid)
        e = {
            'id': tr['id'], 'instance_id': tr['instance_id'],
            'label_class': tr.get('label_class'),
            'merge_acceptable': tr.get('merge_acceptable'),
            'canonical_artifact_id': aid,
            'canonical_present': got is not None,
        }
        if got is not None:
            rec, authentic = got
            f2p = rec.get('fail_to_pass') or {}
            p2p = rec.get('pass_to_pass_scoped') or {}
            lp = tr.get('label_provenance', {})
            fail_ids = sorted(k for k, v in f2p.items() if v == 'FAILED')
            pass_ids = sorted(k for k, v in f2p.items()
                              if v in ('PASSED', 'XFAIL', 'SKIPPED'))
            declared = set(raw['FAIL_TO_PASS'])
            e.update({
                'authentic': authentic,
                'f2p_executed': len(f2p), 'f2p_declared': len(declared),
                'f2p_failed': fail_ids, 'f2p_passed': pass_ids,
                'p2p_executed': len(p2p),
                'symptom_pre': lp.get('symptom_pre_patch_passed'),
                'symptom_post': lp.get('symptom_post_patch_passed'),
            })
            full_green = bool(
                authentic and not fail_ids
                and declared <= set(f2p)
                and not any(v == 'FAILED' for v in p2p.values()))
            full_exec = bool(authentic and declared <= set(f2p) and p2p)
            e['eligible_valid'] = bool(
                tr.get('merge_acceptable') is True and full_green
                and lp.get('symptom_pre_patch_passed') is False
                and lp.get('symptom_post_patch_passed') is True)
            e['eligible_stale_good'] = e['eligible_valid']
            e['eligible_stale_bad_gone'] = bool(
                tr.get('merge_acceptable') is False and full_exec
                and fail_ids
                and lp.get('symptom_pre_patch_passed') is False
                and lp.get('symptom_post_patch_passed') is True)
            e['eligible_stale_bad_persists'] = bool(
                tr.get('merge_acceptable') is False and full_exec
                and lp.get('symptom_pre_patch_passed') is False
                and lp.get('symptom_post_patch_passed') is False)
            e['eligible_incomplete_good'] = bool(
                tr.get('merge_acceptable') is True and len(pass_ids) >= 2)
            e['eligible_decisive_bad'] = bool(
                tr.get('merge_acceptable') is False and fail_ids)
        entries.append(e)
    return entries


def read_jsonl_path(name):
    return list(read_jsonl(WORK / name))


# ---------------------------------------------------------------------------
# Expected facts from the REAL signed record, cross-checked with gold_w2
# ---------------------------------------------------------------------------

def _fixture_row(scenario, raw, ctx, served_aid, truth_row, extra=None):
    row = {
        'scenario': scenario, 'id': raw['id'],
        'instance_id': raw['instance_id'], 'repo': raw['repo'],
        'base_commit': raw['base_commit'],
        'patch_sha256': ctx['patch_sha'], 'served_artifact_id': served_aid,
        'label_class': truth_row.get('label_class'),
        'merge_acceptable': truth_row.get('merge_acceptable'),
        'symptom': _symptom(truth_row, ctx),
        'claim': POSITIVE_CLAIM, 'canon_tree': ctx['canon_tree'],
        'gold_version_intended': GOLD_VERSION,
    }
    if extra:
        row.update(extra)
    return row


def cross_check_row(store, row, intended):
    """Recompute every fact from the signed built record (same formulas as the
    server) and assert both the integrity surface and oracle_gold. Mutates the
    row with the evidence-derived `expected` block; returns error strings."""
    errs = []
    facts = load_fixture_facts(store, row)
    oi = _oracle_inputs_from_facts(facts)
    og = oracle_gold(**oi)
    for key in ('linked', 'fresh', 'complete'):
        if bool(facts[key]) != bool(intended[key]):
            errs.append(f"{row['scenario']} {row['id']}: {key} built="
                        f"{facts[key]} intended={intended[key]}")
    if og != intended['oracle']:
        errs.append(f"{row['scenario']} {row['id']}: oracle_gold={og} "
                    f"intended={intended['oracle']} inputs={oi}")
    if not facts['authentic_signature']:
        errs.append(f"{row['scenario']} {row['id']}: signature not authentic")
    row['expected'] = {
        'linked': facts['linked'], 'fresh': facts['fresh'],
        'complete': facts['complete'],
        'executed_failure_count': facts['executed_failure_count'],
        'executed_check_count': facts['executed_check_count'],
        'symptom_polarity': facts['symptom_polarity'],
        'oracle_gold': og,
    }
    return errs


# ---------------------------------------------------------------------------
# Per-archetype builders
# ---------------------------------------------------------------------------

def build_valid(store, raw, ctx, scenario):
    return copy_canonical_fixture(store, scenario, raw, ctx)['artifact_id']


def build_stale(store, raw, ctx, scenario):
    return build_mirror_stale(store, raw, ctx, scenario)['artifact_id']


def build_replay(store, raw, ctx, scenario, keep, reason):
    expect = _canonical_f2p_status(store, raw, keep)
    rec = build_mirror_batch_replay(
        store, raw, ctx, scenario, keep_f2p_names=keep,
        expect_f2p=expect, reason=reason)
    return rec['artifact_id']


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def intended_for(scenario, truth_row):
    lp = truth_row.get('label_provenance', {})
    persists = (lp.get('symptom_pre_patch_passed') is False
                and lp.get('symptom_post_patch_passed') is False)
    if scenario == VALID:
        return dict(linked=True, fresh=True, complete=True, oracle='ACCEPT')
    if scenario in (STALE_GOOD, STALE_BAD):
        return dict(linked=True, fresh=False, complete=True,
                    oracle='NEED_EVIDENCE')
    if scenario == STALE_PERSISTS:
        # Diagnostic channel is freshness-independent -> decisive everywhere.
        assert persists, 'stale_persists requires symptom post_patch_passed=false'
        return dict(linked=True, fresh=False, complete=True, oracle='REJECT')
    if scenario == INCOMPLETE_GOOD:
        return dict(linked=True, fresh=True, complete=False,
                    oracle='NEED_EVIDENCE')
    if scenario == DECISIVE_BAD:
        return dict(linked=True, fresh=True, complete=False, oracle='REJECT')
    raise ValueError(scenario)


def run_plan(store, raw_by_id, truth_by_id, *, do_pytest=True):
    rows, blocked, audit = [], [], []
    planned_ctx = {}

    def ctx_for(raw):
        # One staging per (instance, patch); replays/stales need a clean tree.
        return w2_stage(store, raw)

    for step in PLAN:
        scenario, rid = step['scenario'], step['id']
        raw = raw_by_id.get(rid)
        tr = truth_by_id.get(rid)
        if raw is None or tr is None:
            blocked.append({'scenario': scenario, 'id': rid,
                            'reason': 'raw/truth row missing'})
            continue
        intended = intended_for(scenario, tr)
        print(f'== {scenario:20s} {rid}')
        try:
            ctx = ctx_for(raw)

            # Replay archetypes: verify the canonical-batch leak guard on the
            # REAL batch layout before any pytest.
            keep = None
            if scenario == INCOMPLETE_GOOD:
                omit = step['omit_pass']
                pass_ids = sorted(
                    k for k, v in _canonical_map(store, raw).items()
                    if v in ('PASSED', 'XFAIL', 'SKIPPED'))
                if omit not in pass_ids:
                    raise RuntimeError(f'omit node {omit} not a passing f2p '
                                       f'{pass_ids}')
                keep = [n for n in pass_ids if n != omit]
                if not keep:
                    raise RuntimeError('no passing f2p remains after omit')
                batches, leaked, unmapped = replay_layout(raw, ctx, keep)
                audit.append({'scenario': scenario, 'id': rid,
                              'keep': keep, 'omit': [omit],
                              'replay_batches': batches,
                              'leaked_omitted_f2p': leaked,
                              'unmapped_kept': unmapped})
                if leaked or unmapped or not batches:
                    raise RuntimeError(f'replay infeasible leaked={leaked} '
                                       f'unmapped={unmapped} batches={batches}')
            elif scenario == DECISIVE_BAD:
                fail_map = _canonical_map(store, raw)
                fail_ids = sorted(k for k, v in fail_map.items()
                                  if v == 'FAILED')
                if not fail_ids:
                    raise RuntimeError('no canonical failing f2p to keep')
                if step.get('keep_fail'):
                    keep_fail = step['keep_fail']
                    if keep_fail not in fail_ids:
                        raise RuntimeError(
                            f'requested keep_fail {keep_fail} not failing '
                            f'{fail_ids}')
                else:
                    keep_fail = fail_ids[0]
                keep = [keep_fail]
                batches, leaked, unmapped = replay_layout(raw, ctx, keep)
                audit.append({'scenario': scenario, 'id': rid,
                              'keep': keep,
                              'replay_batches': batches,
                              'leaked_omitted_f2p': leaked,
                              'unmapped_kept': unmapped})
                if leaked or unmapped or not batches:
                    raise RuntimeError(f'replay infeasible leaked={leaked} '
                                       f'unmapped={unmapped} batches={batches}')

            if not do_pytest:
                # scan-only: record feasibility, store nothing.
                _git_retry('checkout', '-f', RESTORE_HEAD)
                continue

            if scenario == VALID:
                aid = build_valid(store, raw, ctx, scenario)
                extra = None
            elif scenario in (STALE_GOOD, STALE_BAD, STALE_PERSISTS):
                aid = build_stale(store, raw, ctx, scenario)
                extra = None
            else:
                reason = {
                    INCOMPLETE_GOOD:
                        'wave2: replay exact canonical batch(es) of the kept '
                        'PASSING f2p; omit one PASSING declared f2p and ALL '
                        'scoped p2p -> complete=false, zero failure -> NEED',
                    DECISIVE_BAD:
                        'wave2: replay exact canonical batch exhibiting the '
                        'real declared f2p FAILURE; omit the remaining '
                        'declared f2p and ALL scoped p2p -> complete=false '
                        'but an executed applicable failure is decisive',
                }[scenario]
                aid = build_replay(store, raw, ctx, scenario, keep, reason)
                extra = {'replay_kept_f2p': keep}

            row = _fixture_row(scenario, raw, ctx, aid, tr, extra=extra)
            errs = cross_check_row(store, row, intended)
            if errs:
                blocked.append({'scenario': scenario, 'id': rid,
                                'reason': '; '.join(errs)})
            else:
                rows.append(row)
                print(f'   -> {aid} oracle={intended["oracle"]} '
                      f'L={intended["linked"]} F={intended["fresh"]} '
                      f'C={intended["complete"]}')
        except Exception as ex:  # noqa: BLE001 - build failure => BLOCKED, no relax
            msg = f'{type(ex).__name__}: {ex}'
            blocked.append({'scenario': scenario, 'id': rid, 'reason': msg,
                            'optional': bool(step.get('optional'))})
            print('   BLOCKED:', msg)
        finally:
            try:
                _git_retry('checkout', '-f', RESTORE_HEAD)
            except Exception:
                pass
            try:
                _git_retry('clean', '-fdq')
            except Exception:
                pass

    # Deterministic manifest order.
    rows.sort(key=lambda r: (r['scenario'], r['id']))
    return rows, blocked, audit


def _canonical_map(store, raw):
    aid = make_artifact_id(raw['instance_id'],
                           sha256_text(raw['model_patch']))
    got = store.get(aid)
    if got is None:
        raise RuntimeError(f'canonical artifact missing: {aid}')
    return got[0].get('fail_to_pass') or {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='evidence_store/wave2_raw_rows.jsonl')
    ap.add_argument('--truth', default='evidence_store/wave2_truth.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--out', default='evidence_store/wave2_fixtures.jsonl')
    ap.add_argument('--audit-out',
                    default='evidence_store/wave2_build_audit.json')
    ap.add_argument('--scan-only', action='store_true')
    a = ap.parse_args()

    # Separate meta file => frozen fixtures_meta.json is never written.
    store = ArtifactStore(a.store,
                          fixtures_meta_name='wave2_fixtures_meta.json')
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    truth_by_id = {r['id']: r for r in read_jsonl(a.truth)}

    entries = scan(store, raw_by_id, truth_by_id)
    print('canonical-artefact eligibility:')
    for e in entries:
        if not e.get('canonical_present'):
            print(f"  {e['id']:<52.52} canonical MISSING")
            continue
        tags = [k.replace('eligible_', '') for k in e
                if k.startswith('eligible_') and e[k]]
        print(f"  good={str(e['merge_acceptable']):<5} "
              f"f2p={e['f2p_executed']}/{e['f2p_declared']} "
              f"fail={len(e['f2p_failed'])} p2p={e['p2p_executed']} "
              f"pre={e['symptom_pre']} post={e['symptom_post']} "
              f"{e['id']:<46.46} [{','.join(tags) or '-'}]")

    try:
        rows, blocked, replay_audit = run_plan(
            store, raw_by_id, truth_by_id, do_pytest=not a.scan_only)
    finally:
        try:
            _git_retry('checkout', '-f', RESTORE_HEAD)
        except Exception:
            pass
        try:
            _git_retry('clean', '-fdq')
        except Exception:
            pass

    audit = {'gold_version': GOLD_VERSION,
             'eligibility': entries,
             'replay_layouts': replay_audit,
             'blocked': blocked,
             'built': [{'scenario': r['scenario'], 'id': r['id'],
                        'served_artifact_id': r['served_artifact_id'],
                        'expected': r.get('expected')} for r in rows]}
    Path(a.audit_out).write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print('build audit ->', a.audit_out)

    if a.scan_only:
        print('scan-only: no artifacts written')
        return

    write_jsonl(a.out, rows)
    print(f'\nwrote {len(rows)} wave-2 fixture rows -> {a.out}')
    # TR-5.4: every archetype must be present or explicitly blocked.
    built_types = {r['scenario'] for r in rows}
    for tag in (VALID, STALE_GOOD, STALE_BAD, STALE_PERSISTS,
                INCOMPLETE_GOOD, DECISIVE_BAD):
        n = sum(1 for r in rows if r['scenario'] == tag)
        mark = 'OK ' if n else 'MISSING'
        print(f'  [{mark}] {tag}: {n}')
    if blocked:
        print('BLOCKED (criteria NOT relaxed):')
        for b in blocked:
            print(' ', b)


if __name__ == '__main__':
    main()
