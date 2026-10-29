"""G3-C.1 tasks 1-3 — run BOTH pre-registered selection queues and freeze the
complete screening funnel BEFORE any issue is built.

Queue A (natural): every eligible issue is sorted by instance_id and shuffled
with the G3-C.0 sampling seed (418237). This order is the natural-prevalence
screen; the natural oracle label rate is measured AFTER the build and reported
separately (the order itself is frozen before any outcome exists).

Queue B (REJECT-enriched): eligibility is identical, but candidates are
ordered by PRE-REGISTERED STATIC CI-STRUCTURE signals only. No model output,
no harness `resolved` posterior and no executed outcome is consulted:

  R-TRAP: the maintainer test_patch text carries an xfail/skip/flaky marker
          or creates a brand-new test file ('--- /dev/null'); the naive-token
          mislabel trap family (13974/17630-type surface).
  R-F2P : declared FAIL_TO_PASS set is tiny (<=2): a single concentrated
          acceptance criterion where a still-failing declared test decides
          REJECT (17318-type family).
  R-P2P : declared PASS_TO_PASS surface is large (>=20): more regression
          opportunities (19783/17630-type family).
Strata are shuffled independently with seed 418241, concatenated in the
pre-registered rarity/mechanism order R-TRAP, R-P2P, R-F2P, then all other
eligible issues in natural order as fallback. Multi-stratum membership is
recorded; primary stratum priority is R-TRAP > R-P2P > R-F2P (the f2p<=1
feature is near-universal in this pool, so trap and large-regression-surface
issues are assigned to their more informative stratum first).

Pilot slots: first 4 natural + first 4 enriched (union, dedup-corrected,
capped at 8). Enriched picks are flagged; their later error rates estimate
CONDITIONAL behaviour, never the natural population rate.

Independence: dedup key = repo + sha256(sorted candidate changed-file set);
only the first issue in each queue order survives a shared-file-set cluster.

  uv run --offline --python 3.9 -m evidence.g3c1_select
"""
from __future__ import annotations

import hashlib
import json
import random

from evidence import g3c1_common as C

OUT_SELECTION = C.OUT_SELECTION / 'g3c1_selection.json'

TRAP_MARKERS = ('xfail', 'skipif', 'pytest.mark.skip', 'pytest.mark.xfail',
                'flaky', 'expected_failure', 'XFAIL', 'SKIP')
R_F2P_MAX = 2
R_P2P_MIN = 20


def changed_files(patch: str):
    return sorted({l[6:] for l in patch.splitlines()
                   if l.startswith('+++ b/')})


def dedup_key(repo: str, files) -> str:
    h = hashlib.sha256('\n'.join(files).encode('utf-8')).hexdigest()
    return f'{repo}:{h}'


def structural_signals(cand_gates: dict, pool_row: dict) -> dict:
    """Static CI-structure signals ONLY. Never reads resolved/model results."""
    tp = pool_row['test_patch']
    f2p_n = cand_gates.get('f2p_declared_n') or 0
    p2p_n = cand_gates.get('p2p_declared_n') or 0
    adds_new_test_file = '--- /dev/null' in tp and '+++ b/' in tp and any(
        '/tests/' in l[6:] or l[6:].startswith('tests/')
        for l in tp.splitlines() if l.startswith('+++ b/'))
    marker_hits = sorted({m for m in TRAP_MARKERS if m in tp})
    trap = bool(marker_hits) or bool(adds_new_test_file)
    f2p_small = f2p_n <= R_F2P_MAX
    p2p_large = p2p_n >= R_P2P_MIN
    strata = []
    if trap:
        strata.append('R-TRAP')
    if f2p_small:
        strata.append('R-F2P')
    if p2p_large:
        strata.append('R-P2P')
    return {'f2p_declared_n': f2p_n, 'p2p_declared_n': p2p_n,
            'adds_new_test_file': adds_new_test_file,
            'marker_hits': marker_hits, 'is_R_TRAP': trap,
            'is_R_F2P': f2p_small, 'is_R_P2P': p2p_large,
            'strata': strata}


# Primary partition priority: rare/mechanism-distinct strata first. Membership
# flags remain non-exclusive (an issue can be both R-P2P and R-F2P), but the
# primary stratum is assigned by this order so the (near-universal) f2p<=1
# feature does not swallow big-regression-surface or trap issues.
STRATUM_PRIORITY = ('R-TRAP', 'R-P2P', 'R-F2P')


def primary_stratum(sig: dict):
    for s in STRATUM_PRIORITY:
        if sig.get(f'is_{s.replace("-", "_")}'):
            return s
    return 'UNENRICHED'


def build_eligible():
    audit = json.loads(C.WAVE2_SELECTION_AUDIT.read_text(encoding='utf-8'))
    pool = C.read_jsonl(C.POOL)
    pool_by_id = {}
    for r in pool:
        pool_by_id.setdefault(r['instance_id'], []).append(r)

    funnel = [{'step': 'S0_pool_instances',
               'n_in': audit['pool_instances'], 'n_out': audit['pool_instances'],
               'rule': 'locally cached wave2 candidate pool (frozen audit)'}]
    excluded = []
    eligible = []
    n_wave2 = n_offline = n_gate = n_noclean = 0
    for cand in audit['candidates']:
        iid = cand['instance_id']
        g = cand.get('gates', {})
        reason = None
        if iid in C.WAVE2_CONSUMED:
            reason = 'previously_used_wave2'; n_wave2 += 1
        elif iid in C.G3A_CONSUMED:
            reason = 'previously_used_g3a_cohort'
        elif iid in C.OFFLINE_INCOMPLETE:
            reason = 'offline_blob_incomplete'; n_offline += 1
        elif not g or not all(g.get(k) for k in C.GATE_KEYS):
            reason = 'static_test_spec_gate_failed'; n_gate += 1
        if reason is None:
            clean = [rc for rc in cand.get('row_checks', [])
                     if rc.get('model_patch_clean')]
            if not clean:
                reason = 'no_clean_target_patch'; n_noclean += 1
        if reason:
            excluded.append({'instance_id': iid, 'reason': reason})
            continue
        # deterministic target generator (resolved is used ONLY as the frozen
        # tie-break documented in g3a_select; never for enrichment/eligibility)
        clean = [rc for rc in cand['row_checks'] if rc.get('model_patch_clean')]
        clean.sort(key=lambda rc: (0 if rc.get('resolved') else 1,
                                   C.GEN_PRIORITY.get(rc['generator_model'], 9),
                                   rc['id']))
        target_rc = clean[0]
        prow = next((r for r in pool_by_id.get(iid, [])
                     if r.get('id') == target_rc['id']), None)
        if prow is None:
            reason = 'target_pool_row_missing'
            excluded.append({'instance_id': iid, 'reason': reason})
            continue
        files = changed_files(prow['model_patch'])
        eligible.append({
            'instance_id': iid,
            'repo': prow['repo'],
            'n_generators': cand.get('n_rows'),
            'n_clean_targets': len(clean),
            'target_generator': target_rc['generator_model'],
            'target_row_id': target_rc['id'],
            'base_commit': prow['base_commit'],
            'candidate_changed_files': files,
            'dedup_key': dedup_key(prow['repo'], files),
            'signals': structural_signals(g, prow)})

    funnel += [
        {'step': 'S1_exclude_wave2_consumed', 'rule': '12 pre-G3A issues',
         'n_removed': n_wave2},
        {'step': 'S2_exclude_g3a_cohort', 'rule': '10 G3-A materialised issues',
         'n_removed': sum(1 for e in excluded
                          if e['reason'] == 'previously_used_g3a_cohort')},
        {'step': 'S3_exclude_offline_incomplete', 'rule': 'sympy-11618 blobs',
         'n_removed': n_offline},
        {'step': 'S4_static_test_spec_gates',
         'rule': 'all six frozen wave2 gates must pass', 'n_removed': n_gate},
        {'step': 'S5_no_clean_target_patch',
         'rule': '>=1 clean-apply generator row required',
         'n_removed': n_noclean},
        {'step': 'S6_eligible',
         'rule': 'G3-C.1 eligible pool (expect 51)', 'n_out': len(eligible)}]
    return eligible, excluded, funnel


def apply_dedup(order, eligible_by_id):
    """Keep first issue per dedup cluster; record suppressed duplicates."""
    seen = {}
    out, suppressed = [], []
    for iid in order:
        key = eligible_by_id[iid]['dedup_key']
        if key in seen:
            suppressed.append({'instance_id': iid,
                               'reason': 'duplicate_changed_file_cluster',
                               'cluster_kept_first': seen[key]})
            continue
        seen[key] = iid
        out.append(iid)
    return out, suppressed


def main():
    C.ensure_out_dirs()
    eligible, excluded, funnel = build_eligible()
    assert len(eligible) == 51, f'expected 51 eligible, got {len(eligible)}'
    by_id = {e['instance_id']: e for e in eligible}

    # ---- Queue A: natural ----
    nat_ids = sorted(by_id)
    rng_n = random.Random(C.G3C1_SAMPLING_SEED)
    rng_n.shuffle(nat_ids)
    nat_dedup, nat_suppressed = apply_dedup(nat_ids, by_id)

    # ---- Queue B: REJECT-enriched (static structure only) ----
    strata_groups = {'R-TRAP': [], 'R-F2P': [], 'R-P2P': [], 'UNENRICHED': []}
    for iid in nat_dedup:
        sig = by_id[iid]['signals']
        strata_groups[primary_stratum(sig)].append(iid)
    rng_e = random.Random(C.G3C1_ENRICHED_SEED)
    enriched_order = []
    stratum_record = {}
    for s in (*STRATUM_PRIORITY, 'UNENRICHED'):
        grp = sorted(strata_groups[s])
        rng_e.shuffle(grp)
        stratum_record[s] = {'n_members': len(grp),
                             'shuffled_order': grp}
        enriched_order.extend(grp)

    # ---- pilot slots: 4 natural + 4 enriched union, capped at 8 ----
    chosen_nat = nat_dedup[:C.N_NATURAL_SLOTS]
    chosen = list(chosen_nat)
    chosen_keys = {by_id[i]['dedup_key'] for i in chosen}
    chosen_enr = []
    for iid in enriched_order:
        if len(chosen) >= C.MAX_NEW_ISSUES:
            break
        if by_id[iid]['dedup_key'] in chosen_keys:
            continue
        chosen_enr.append(iid)
        chosen.append(iid)
        chosen_keys.add(by_id[iid]['dedup_key'])
        if len(chosen_enr) >= C.N_ENRICHED_SLOTS:
            break

    for e in eligible:
        e['queue_natural_rank'] = (nat_dedup.index(e['instance_id'])
                                   if e['instance_id'] in nat_dedup else None)
        e['queue_enriched_rank'] = (enriched_order.index(e['instance_id'])
                                    if e['instance_id'] in enriched_order
                                    else None)
        e['primary_stratum'] = primary_stratum(e['signals'])
        e['selected_for_pilot'] = e['instance_id'] in chosen
        e['pilot_queue_label'] = (
            'natural+enriched' if e['instance_id'] in chosen_nat
            and e['instance_id'] in chosen_enr
            else 'natural' if e['instance_id'] in chosen_nat
            else 'enriched' if e['instance_id'] in chosen_enr else None)

    result = {
        'document': 'G3-C.1 pre-registered dual-queue selection; frozen '
                    'BEFORE any build/execution; no model output consulted.',
        'protocol_version': C.G3C1_PROTOCOL_VERSION,
        'seeds': {'natural_shuffle_seed': C.G3C1_SAMPLING_SEED,
                  'enriched_strata_shuffle_seed': C.G3C1_ENRICHED_SEED},
        'slot_rule': {'natural_slots': C.N_NATURAL_SLOTS,
                      'enriched_slots': C.N_ENRICHED_SLOTS,
                      'cap': C.MAX_NEW_ISSUES,
                      'union_dedup_capped': True},
        'enrichment_rule': {
            'inputs': 'frozen wave2 gates (f2p/p2p declared counts) + '
                      'maintainer test_patch text + candidate changed files',
            'forbidden_inputs': ['model prediction text', 'generator resolved '
                                 'posterior for eligibility/stratification',
                                 'any executed pytest outcome',
                                 'any prior gate gold/model error'],
            'R_TRAP': 'xfail/skip/flaky marker in test_patch OR test_patch '
                      'adds a new tests/ file',
            'R_F2P': f'f2p_declared_n <= {R_F2P_MAX}',
            'R_P2P': f'p2p_declared_n >= {R_P2P_MIN}',
            'primary_stratum_priority': list(STRATUM_PRIORITY),
            'interpretation': 'enriched-sample rates estimate CONDITIONAL '
                              'error behaviour among screen-positive issues, '
                              'NOT the natural population rate'},
        'dedup_rule': 'one issue per repo+sha256(sorted changed-file-set) '
                      'cluster; earliest queue rank kept',
        'screening_funnel': funnel,
        'n_eligible': len(eligible),
        'n_excluded_total': len(excluded),
        'excluded': excluded,
        'natural_dedup_suppressed': nat_suppressed,
        'natural_queue_order': nat_dedup,
        'enriched_strata': stratum_record,
        'enriched_queue_order': enriched_order,
        'pilot_instance_ids': chosen,
        'pilot_natural_picks': chosen_nat,
        'pilot_enriched_picks': chosen_enr,
        'natural_rate_note': 'natural oracle ACCEPT/REJECT/NEED prevalence is '
                             'measured after the build and reported in g3c1_'
                             'report; the natural ORDER above is frozen now.',
        'eligible_detail': eligible,
        'approved_scope': C.APPROVED_SCOPE,
    }
    C.write_canonical(OUT_SELECTION, result)

    print('eligible:', len(eligible), 'excluded:', len(excluded))
    for f in funnel:
        print(' funnel', f)
    print('stratum sizes:', {s: v['n_members']
                             for s, v in stratum_record.items()})
    print('natural dedup suppressed:', nat_suppressed)
    print('pilot (n=%d):' % len(chosen))
    for iid in chosen:
        e = by_id[iid]
        print(' ', iid, '|', e['pilot_queue_label'],
              '| stratum', e['primary_stratum'], e['signals']['strata'],
              '| f2p', e['signals']['f2p_declared_n'],
              'p2p', e['signals']['p2p_declared_n'],
              '| target', e['target_generator'])
    print('->', OUT_SELECTION.relative_to(C.HERE))


if __name__ == '__main__':
    main()
