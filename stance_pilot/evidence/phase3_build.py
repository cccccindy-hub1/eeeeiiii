"""Build Phase-3 MIRROR fixtures with REAL git/pytest executions (offline).

The Phase-2 fixtures confound evidence validity with patch correctness:
  valid         -> GOOD patch + valid evidence
  stale/wrong_patch -> GOOD/BAD but asymmetric (stale used a GOOD patch;
                       wrong_patch used a BAD patch)
  contradictory/incomplete -> BAD patch + invalid evidence
Phase 3 mirrors the cells so every integrity condition is crossed with BOTH a
truly acceptable (GOOD) and a truly unacceptable (BAD) patch. Selection is
deterministic (first eligible sample in truth.jsonl order); scenario labels
never enter a prompt.

Mirror scenarios (independent file phase3_fixtures.jsonl; new fix_* ids only):
  stale_bad                 BAD patch, linked, complete, NOT fresh (inert tree)
  wrong_patch_good          GOOD patch served a foreign signed artifact,
                            linked=false
  incomplete_good           GOOD patch, linked/fresh, one PASSING declared f2p
                            omitted -> complete=false, no decisive failure
  incomplete_decisive_bad   BAD patch, linked/fresh, complete=false but an
                            executed declared f2p FAILS and is KEPT ->
                            decisive_failure=true -> gold REJECT (asymmetric
                            proof: completeness gates ACCEPT, not REJECT)

Eligibility is audited. If M1/M2 have no eligible sample the build reports the
candidate list and marks that cell BLOCKED rather than relaxing the criteria
(TR-5.4). No Phase-1/2 file is modified; everything is appended.

Run with the SAME interpreter vintage as the target instances' canonical
Phase-1 artifacts (their f2p log banner records it; old sympy fails to collect
on 3.11 via `collections.Mapping`). The M1..M4 targets here are 3.9-era:
  uv run --python 3.9 --with mpmath --with "pytest==8.4.2" \
      python -m evidence.phase3_build
"""
from __future__ import annotations

import argparse, copy, json, os
from pathlib import Path

from pilot import read_jsonl, write_jsonl
from evidence.builder import now
from evidence.schemas import make_artifact_id, sha256_text
from evidence.store import ArtifactStore
from evidence.ternary import derive_evidence_facts, gold_decision
# Reuse the audited Phase-2 construction primitives (no Phase-2 file changes).
from evidence.phase2_build import (
    stage, fixture_id, make_record, _execute_batched, _git_retry, _write_tree,
    POSITIVE_CLAIM, STALE_MARKER_FILE, STALE_MARKER_LINE,
)
from evidence.builder import (map_names_to_files, name_outcomes,
                              run_pytest_files, parse_node_logs)

os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

MIRROR_SCENARIOS = ('stale_bad', 'wrong_patch_good', 'incomplete_good',
                    'incomplete_decisive_bad')


# ---------------------------------------------------------------------------
# Deterministic eligibility (read-only over existing canonical artifacts)
# ---------------------------------------------------------------------------

def scan_candidates(store, truth_rows, raw_by_id):
    by_instance = {}
    for tr in truth_rows:
        by_instance.setdefault(tr['instance_id'], []).append(tr)
    cands = []
    for i, tr in enumerate(truth_rows):
        raw = raw_by_id.get(tr['id'])
        if raw is None:
            continue
        aid = make_artifact_id(tr['instance_id'], tr['patch_sha256'])
        got = store.get(aid)
        if got is None:
            cands.append({'order': i, 'id': tr['id'], 'eligible': False,
                          'reason': 'canonical artifact missing'})
            continue
        rec, _auth = got
        f2p = rec.get('fail_to_pass') or {}
        p2p = rec.get('pass_to_pass_scoped') or {}
        declared = set(raw['FAIL_TO_PASS'])
        missing = sorted(declared - set(f2p))
        fail_ids = [k for k, v in f2p.items() if v == 'FAILED']
        pass_ids = [k for k, v in f2p.items()
                    if v in ('PASSED', 'XFAIL', 'SKIPPED')]
        siblings = []
        for s in by_instance[tr['instance_id']]:
            if s['id'] == tr['id']:
                continue
            said = make_artifact_id(tr['instance_id'], s['patch_sha256'])
            if store.get(said) is not None and s['patch_sha256'] != tr['patch_sha256']:
                siblings.append(s['id'])
        is_good = tr.get('merge_acceptable') is True
        is_bad = tr.get('merge_acceptable') is False
        full_exec = (not missing and len(declared) >= 1 and len(p2p) >= 1)
        c = {
            'order': i, 'id': tr['id'], 'instance_id': tr['instance_id'],
            'label_class': tr.get('label_class'),
            'merge_acceptable': tr.get('merge_acceptable'),
            'f2p_executed': len(f2p), 'f2p_declared': len(declared),
            'p2p_executed': len(p2p), 'f2p_failed': fail_ids,
            'f2p_passed': pass_ids, 'siblings_with_artifacts': siblings,
            'm1_stale_bad': bool(is_bad and full_exec),
            'm2_wrong_patch_good': bool(is_good and siblings),
            'm3_incomplete_good': bool(is_good and len(pass_ids) >= 2),
            'm4_decisive_bad': bool(is_bad and fail_ids
                                    and (len(f2p) >= 2 or len(p2p) >= 1)),
        }
        cands.append(c)
    return cands


def _first(cands, key):
    for c in cands:
        if c.get(key):
            return c
    return None


# ---------------------------------------------------------------------------
# Generalised builders
# ---------------------------------------------------------------------------

def build_mirror_stale(store, raw, ctx, scenario):
    """Full declared F2P+P2P execution on a tree one inert comment away from
    canonical -> linked & complete, NOT fresh. Outcomes are real, so a BAD
    patch records a genuine failure inside a stale run."""
    from evidence.phase2_build import REPO
    mf = REPO / STALE_MARKER_FILE
    if not mf.exists():
        raise RuntimeError(f'{STALE_MARKER_FILE} missing at {raw["base_commit"]}')
    with open(mf, 'a', encoding='utf-8', newline='') as fh:
        fh.write('\n' + STALE_MARKER_LINE + '\n')
    run_tree = _write_tree()
    assert run_tree != ctx['canon_tree']

    f2p_map = map_names_to_files(list(raw['FAIL_TO_PASS']), ctx['scope_files'],
                                 ctx['idx'])
    p2p_map = map_names_to_files(ctx['p2p_names'], ctx['scope_files'], ctx['idx'])
    run_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    started = now()
    log, node_status = _execute_batched(run_files, scenario)
    f2p = name_outcomes(list(raw['FAIL_TO_PASS']), f2p_map, node_status)
    p2p = name_outcomes(ctx['p2p_names'], p2p_map, node_status)
    rec = make_record(scenario=scenario, raw=raw, patch_sha=ctx['patch_sha'],
                      test_patch_sha=ctx['tp_sha'], started=started,
                      scope_files=ctx['scope_files'], f2p_outcomes=f2p,
                      p2p_outcomes=p2p, f2p_log=log, p2p_log=log,
                      symptom_log=ctx['symptom_log'], run_tree=run_tree)
    store.put_fixture(rec, logs={'f2p': log, 'p2p': log,
                                 'symptom': ctx['symptom_log']},
                      meta={'scenario': scenario, 'canon_tree': ctx['canon_tree'],
                            'run_tree': run_tree,
                            'tree_delta': f'inert comment appended to '
                                          f'{STALE_MARKER_FILE}'})
    return rec


def _canonical_f2p_status(store, raw, names):
    """Signed canonical outcomes for the named declared f2p checks (the status
    a faithful batch replay MUST reproduce)."""
    aid = make_artifact_id(raw['instance_id'], sha256_text(raw['model_patch']))
    got = store.get(aid)
    if got is None:
        raise RuntimeError(f'canonical artifact missing: {aid}')
    canon = got[0].get('fail_to_pass') or {}
    return {n: canon[n] for n in names}


def build_mirror_batch_replay(store, raw, ctx, scenario, *, keep_f2p_names,
                              expect_f2p, reason):
    """Partial-coverage fixture via HONEST replay of exact canonical batches.

    The canonical Phase-1 run executes sorted(union(f2p,p2p files)) in batches
    of three files PER PYTEST PROCESS (builder.build_one / phase2_build). Test
    isolation means a node's outcome can depend on which other files share its
    process. Replaying a node therefore means re-running the WHOLE canonical
    3-file batch that contains its defining file — never a re-batched subset —
    under the SAME interpreter vintage as the canonical run.

    Only the kept declared f2p outcomes are recorded; every other declared f2p
    and ALL scoped p2p checks are omitted (coverage complete=false). The raw
    pytest log for the replayed batch(es) is stored verbatim; the scenario
    remains discoverable only through its integrity surface.

    `expect_f2p` maps each kept node to the status it MUST reproduce, taken
    from the signed canonical artifact (so replay is verified to reproduce the
    genuine result, never guessed). Mismatch raises -> report BLOCKED, never
    relax the criterion.
    """
    f2p_map = map_names_to_files(list(raw['FAIL_TO_PASS']), ctx['scope_files'],
                                 ctx['idx'])
    p2p_map = map_names_to_files(ctx['p2p_names'], ctx['scope_files'],
                                 ctx['idx'])
    all_files = sorted(set(sum(f2p_map.values(), []))
                       | set(sum(p2p_map.values(), [])))
    keep = list(keep_f2p_names)
    replay_idx = set()
    for nm in keep:
        fl = f2p_map.get(nm)
        if not fl:
            raise RuntimeError(f'{scenario}: kept f2p {nm!r} unmapped')
        for i in range(0, len(all_files), 3):
            if fl[0] in all_files[i:i + 3]:
                replay_idx.add(i)
    batches = [all_files[i:i + 3] for i in sorted(replay_idx)]
    if not batches:
        raise RuntimeError(f'{scenario}: no canonical batch to replay')
    # Leak guard: the replayed batch runs whole files, so it must NOT define any
    # omitted declared f2p node, or the raw log would leak hidden acceptance
    # outcomes that coverage says are missing. Same-patch p2p lines in an f2p
    # log are only reachable under escalate (strict returns 403), matching the
    # Phase-2 incomplete design.
    omitted = [n for n in raw['FAIL_TO_PASS'] if n not in keep]
    batch_files = {f for b in batches for f in b}
    for n in omitted:
        if set(f2p_map.get(n, [])) & batch_files:
            raise RuntimeError(
                f'{scenario}: canonical batch for kept node also defines '
                f'omitted declared f2p {n}; cannot replay without leaking. '
                'Report BLOCKED; criteria NOT relaxed.')
    print(f'    replaying {len(batches)} canonical batch(es) '
          f'{batches} (canonical run_files n={len(all_files)})')

    started = now()
    logs = []
    for b in batches:
        log, _rc = run_pytest_files(b, scenario)
        logs.append(log)
    joined = '\n\n'.join(logs)
    node_status = parse_node_logs(logs)
    f2p = name_outcomes(keep, f2p_map, node_status)
    for nm in keep:
        got = f2p.get(nm)
        if got != expect_f2p[nm]:
            raise RuntimeError(
                f'{scenario}: replay did not reproduce canonical outcome for '
                f'{nm}: got {got}, expected {expect_f2p[nm]}. Criteria NOT '
                'relaxed; report BLOCKED.')
    empty = ('(no scoped regression checks were executed for this run)')
    rec = make_record(scenario=scenario, raw=raw, patch_sha=ctx['patch_sha'],
                      test_patch_sha=ctx['tp_sha'], started=started,
                      scope_files=ctx['scope_files'], f2p_outcomes=f2p,
                      p2p_outcomes={}, f2p_log=joined, p2p_log=empty,
                      symptom_log=ctx['symptom_log'], run_tree=ctx['canon_tree'])
    store.put_fixture(rec, logs={'f2p': joined, 'p2p': empty,
                                 'symptom': ctx['symptom_log']},
                      meta={'scenario': scenario, 'construction_reason': reason,
                            'replayed_batches': batches,
                            'canonical_run_files_total': len(all_files),
                            'executed_f2p': keep,
                            'omitted_f2p': [n for n in raw['FAIL_TO_PASS']
                                            if n not in keep],
                            'executed_p2p': []})
    return rec


def build_mirror_wrong_patch(store, raw_served, raw_source, ctx_source, scenario):
    """Re-identify the SOURCE patch's genuine canonical artifact as a fix_ id
    for the GOOD served patch, WITHOUT running any new pytest. The record keeps
    the source base/hash/run_tree, so linkage against the served target fails.
    Probes/attestation for the served target are handled by the caller."""
    src_sha = sha256_text(raw_source['model_patch'])
    src_aid = make_artifact_id(raw_source['instance_id'], src_sha)
    src_store = ArtifactStore(str(Path(store.root)))
    got = src_store.get(src_aid)
    if got is None:
        raise RuntimeError(f'source canonical artifact missing: {src_aid}')
    served_sha = sha256_text(raw_served['model_patch'])
    rec = copy.deepcopy(got[0])
    rec['artifact_id'] = fixture_id(scenario, raw_served['instance_id'],
                                    served_sha)
    rec['phase2_scenario'] = scenario
    rec['run_tree'] = ctx_source['canon_tree']
    logs = {}
    for name in rec['log_digests']:
        lp = src_store.root / 'logs' / f'{src_aid}.{name}.log'
        if lp.exists():
            logs[name] = lp.read_text(encoding='utf-8')
    store.put_fixture(rec, logs=logs,
                      meta={'scenario': scenario, 'served_id': raw_served['id'],
                            'source_artifact_id': src_aid,
                            'source_id': raw_source['id'],
                            'source_patch_sha256': src_sha})
    return rec


# ---------------------------------------------------------------------------
# Expected evidence facts (computed from the REAL built record, never labels)
# ---------------------------------------------------------------------------

def _expected_row(*, linked, fresh, complete, rec):
    f2p = rec.get('fail_to_pass') or {}
    p2p = rec.get('pass_to_pass_scoped') or {}
    n_fail = sum(1 for v in list(f2p.values()) + list(p2p.values())
                 if v == 'FAILED')
    n_exec = len(f2p) + len(p2p)
    facts = derive_evidence_facts(linked=linked, fresh=fresh, complete=complete,
                                  executed_failure_count=n_fail,
                                  executed_check_count=n_exec)
    gold = gold_decision(evidence_integrity=facts['evidence_integrity'],
                         decisive_failure=facts['decisive_failure'],
                         sufficient_success=facts['sufficient_success'])
    return {
        'linked': linked, 'fresh': fresh, 'complete': complete,
        # legacy consistency flag (positive claim vs hidden record outcomes)
        'consistent': (n_fail == 0),
        'decisive_failure': facts['decisive_failure'],
        'sufficient_success': facts['sufficient_success'],
        'evidence_integrity': facts['evidence_integrity'],
        'executed_failure_count': n_fail, 'executed_check_count': n_exec,
        'gold_decision': gold,
    }


def _fixture_row(scenario, served, ctx, served_aid, truth_row, expected,
                 source=None):
    lp = truth_row.get('label_provenance', {})
    row = {
        'scenario': scenario, 'id': served['id'],
        'instance_id': served['instance_id'], 'repo': served['repo'],
        'base_commit': served['base_commit'],
        'patch_sha256': ctx['patch_sha'], 'served_artifact_id': served_aid,
        'label_class': truth_row.get('label_class'),
        'merge_acceptable': truth_row.get('merge_acceptable'),
        'symptom': {
            'pre_patch_passed': lp.get('symptom_pre_patch_passed',
                                       ctx['pre_ok']),
            'post_patch_passed': lp.get('symptom_post_patch_passed',
                                        ctx['post_ok']),
        },
        'claim': POSITIVE_CLAIM, 'expected': expected,
        'canon_tree': ctx['canon_tree'],
    }
    if source:
        row['source'] = source
    return row


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_all(store, raw_by_id, truth_by_id, probe_dir, *, include=()):
    cands = scan_candidates(store, list(truth_by_id.values()), raw_by_id)
    audit = [c for c in cands]
    rows, blocked = [], []

    def target(cand):
        return raw_by_id[cand['id']]

    # ---- M1: stale_bad ----
    if 'stale_bad' in include:
        m1 = _first(cands, 'm1_stale_bad')
        if m1 is None:
            blocked.append({'scenario': 'stale_bad',
                            'reason': 'no class A/C fully-executed sample'})
        else:
            print(f'== stale_bad  served={m1["id"]} (order={m1["order"]})')
            served = target(m1)
            ctx = stage(served, store, probe_dir)
            rec = build_mirror_stale(store, served, ctx, 'stale_bad')
            exp = _expected_row(linked=True, fresh=False, complete=True, rec=rec)
            tr = truth_by_id[served['id']]
            rows.append(_fixture_row('stale_bad', served, ctx,
                                     rec['artifact_id'], tr, exp))
            _git_retry('checkout', '-f', 'HEAD')

    # ---- M2: wrong_patch_good ----
    if 'wrong_patch_good' in include:
        m2 = _first(cands, 'm2_wrong_patch_good')
        if m2 is None:
            blocked.append({'scenario': 'wrong_patch_good',
                            'reason': 'no GOOD (merge_acceptable=true) sample '
                                      'with a foreign canonical artifact'})
        else:
            source_id = sorted(m2['siblings_with_artifacts'])[0]
            print(f'== wrong_patch_good served={m2["id"]} (order={m2["order"]}) '
                  f'source={source_id}')
            served = target(m2)
            source = raw_by_id[source_id]
            ctx = stage(served, store, probe_dir)  # served canonical attestation
            ctx_source = stage(source, store, probe_dir, attest=False)
            rec = build_mirror_wrong_patch(store, served, source, ctx_source,
                                           'wrong_patch_good')
            exp = _expected_row(linked=False, fresh=False, complete=True,
                                rec=rec)
            tr = truth_by_id[served['id']]
            rows.append(_fixture_row('wrong_patch_good', served, ctx,
                                     rec['artifact_id'], tr, exp,
                                     source=source_id))
            _git_retry('checkout', '-f', 'HEAD')

    # ---- M3: incomplete_good (omit ONE passing declared f2p) ----
    if 'incomplete_good' in include:
        m3 = _first(cands, 'm3_incomplete_good')
        if m3 is None:
            blocked.append({'scenario': 'incomplete_good',
                            'reason': 'no GOOD sample with >=2 passing declared '
                                      'f2p to omit one'})
        else:
            omit = sorted(m3['f2p_passed'])[0]
            keep = [n for n in m3['f2p_passed'] if n != omit]
            print(f'== incomplete_good served={m3["id"]} (order={m3["order"]}) '
                  f'omit_pass={omit}')
            served = target(m3)
            ctx = stage(served, store, probe_dir)
            expect = _canonical_f2p_status(store, served, keep)
            rec = build_mirror_batch_replay(
                store, served, ctx, 'incomplete_good', keep_f2p_names=keep,
                expect_f2p=expect,
                reason='replay exact canonical batch of the kept PASSING f2p; '
                       'omit one PASSING declared f2p and ALL scoped p2p -> '
                       'complete=false, zero executed failure -> NEED_EVIDENCE')
            exp = _expected_row(linked=True, fresh=True, complete=False, rec=rec)
            assert exp['decisive_failure'] is False
            assert exp['gold_decision'] == 'NEED_EVIDENCE'
            tr = truth_by_id[served['id']]
            rows.append(_fixture_row('incomplete_good', served, ctx,
                                     rec['artifact_id'], tr, exp))
            _git_retry('checkout', '-f', 'HEAD')

    # ---- M4: incomplete_decisive_bad (keep a FAILING f2p, omit the rest) ----
    if 'incomplete_decisive_bad' in include:
        m4 = _first(cands, 'm4_decisive_bad')
        if m4 is None:
            blocked.append({'scenario': 'incomplete_decisive_bad',
                            'reason': 'no BAD sample with a failing declared f2p '
                                      'and room to omit (>=2 f2p or >=1 p2p)'})
        else:
            fail_keep = sorted(m4['f2p_failed'])[0]
            print(f'== incomplete_decisive_bad served={m4["id"]} '
                  f'(order={m4["order"]}) keep_fail={fail_keep}')
            served = target(m4)
            ctx = stage(served, store, probe_dir)
            expect = _canonical_f2p_status(store, served, [fail_keep])
            rec = build_mirror_batch_replay(
                store, served, ctx, 'incomplete_decisive_bad',
                keep_f2p_names=[fail_keep], expect_f2p=expect,
                reason='replay exact canonical 3-file batch that exhibits the '
                       'real declared f2p FAILURE; omit every other declared '
                       'f2p and ALL scoped p2p -> complete=false but an '
                       'executed applicable failure is decisive -> REJECT')
            exp = _expected_row(linked=True, fresh=True, complete=False, rec=rec)
            assert exp['decisive_failure'] is True, exp
            assert exp['sufficient_success'] is False
            assert exp['gold_decision'] == 'REJECT', exp
            tr = truth_by_id[served['id']]
            rows.append(_fixture_row('incomplete_decisive_bad', served, ctx,
                                     rec['artifact_id'], tr, exp))
            _git_retry('checkout', '-f', 'HEAD')

    return rows, blocked, audit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--truth', default='evidence_store/truth.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--out', default='evidence_store/phase3_fixtures.jsonl')
    ap.add_argument('--audit-out',
                    default='evidence_store/phase3_selection_audit.json')
    ap.add_argument('--scenarios', default=','.join(MIRROR_SCENARIOS))
    ap.add_argument('--scan-only', action='store_true',
                    help='print deterministic eligibility and exit (no git/pytest)')
    a = ap.parse_args()

    store = ArtifactStore(a.store)
    truth_rows = list(read_jsonl(a.truth))
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    truth_by_id = {r['id']: r for r in truth_rows}

    cands = scan_candidates(store, truth_rows, raw_by_id)
    print('deterministic eligibility (truth.jsonl order):')
    for c in cands:
        tags = [k for k in ('m1_stale_bad', 'm2_wrong_patch_good',
                            'm3_incomplete_good', 'm4_decisive_bad') if c.get(k)]
        print(f"  {c['order']:>2} {str(c.get('label_class')):<2} "
              f"{str(c.get('merge_acceptable')):<5} {c['id']:<48.48} "
              f'f2p={c.get("f2p_executed")}/{c.get("f2p_declared")} '
              f'p2p={c.get("p2p_executed")} fail={len(c.get("f2p_failed", []))} '
              f'[{",".join(tags) or "-"}]')
    picks = {
        'M1 stale_bad': (_first(cands, 'm1_stale_bad') or {}).get('id'),
        'M2 wrong_patch_good': (_first(cands, 'm2_wrong_patch_good') or {}).get('id'),
        'M3 incomplete_good': (_first(cands, 'm3_incomplete_good') or {}).get('id'),
        'M4 decisive_bad': (_first(cands, 'm4_decisive_bad') or {}).get('id'),
    }
    print('deterministic picks:', json.dumps(picks, ensure_ascii=False))
    Path(a.audit_out).write_text(
        json.dumps({'candidates': cands, 'picks': picks}, indent=2,
                   ensure_ascii=False), encoding='utf-8')
    print('selection audit ->', a.audit_out)
    if a.scan_only:
        return

    include = tuple(x.strip() for x in a.scenarios.split(',') if x.strip())
    probe_dir = Path(a.store) / 'probes_phase3'
    rows, blocked, audit = [], [], cands
    try:
        rows, blocked, audit = build_all(store, raw_by_id, truth_by_id,
                                         probe_dir, include=include)
    finally:
        try:
            _git_retry('checkout', '-f', 'HEAD')
        except Exception:
            pass
        from evidence.builder import git
        git('clean', '-fdq', check=False)

    write_jsonl(a.out, rows)
    print(f'\nwrote {len(rows)} mirror fixture rows -> {a.out}')
    for r in rows:
        e = r['expected']
        print(f"  {r['scenario']:24s} {r['id']:48s} gold={e['gold_decision']} "
              f"linked={e['linked']} fresh={e['fresh']} "
              f"complete={e['complete']} decisive={e['decisive_failure']}")
    if blocked:
        print('BLOCKED (criteria NOT relaxed):')
        for b in blocked:
            print(' ', b)


if __name__ == '__main__':
    main()
