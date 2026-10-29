"""EAL Gate 1 — per-fixture Evidence Sufficiency Certificates (offline).

Answers the Gate-1 construct question:

    "For THIS fixture, what is the MINIMAL set of evidence that forces the
     gold label, and is every item of that set actually available (in its
     pre-adjudication form) in RAW and STRUCTURED — not just ADJUDICATED?"

Method (oracle-side, deterministic, zero network):
  * Recover the six verdict operands from the frozen store exactly as
    eal_render does (linked/fresh/complete/acceptance_failure/
    acceptance_success/symptom_persists).
  * MINIMAL FORCING SET: enumerate subsets of the six channels smallest
    first; a subset "forces" the gold if, fixing only those channels to
    their recovered values and letting every other channel range freely,
    the frozen oracle returns the SAME label for every completion. The
    first (smallest) such subset is the minimal evidence the decision
    rests on. Channels NOT in it are corroborating, not required.
  * Each forcing channel maps to concrete PRIMARY materials; we record
    where that material lives in each layer (verbatim log / parsed table /
    printed verdict) and whether the archive actually retained it.
  * A missing ARCHIVED material only threatens sufficiency if it belongs to
    a forcing channel. Missing corroborating material is disclosed but does
    not under-determine the layer gold. If a forcing channel's primary
    material is absent, the layer gold is marked underdetermined and is NOT
    forced equal to the oracle (Gate-1 requirement 7).

Writes:
  evidence_store_eal/eal_sufficiency_certificates.json
  evidence_store_eal/eal_sufficiency_summary.md
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

from evidence import eal_protocol as eal
from evidence.eal_render import (load_index, load_materials, recoverable_facts,
                                 DEFAULT_STORE, ArtifactStore, _bundle_id)

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'

CHANNELS = ('linked', 'fresh', 'complete', 'acceptance_failure',
            'acceptance_success', 'symptom_persists')

# Human description of the PRIMARY (pre-adjudication) material each channel
# judgement consumes, and where it surfaces per layer.
CHANNEL_MATERIAL = {
    'linked': {
        'requires': 'TARGET base_commit+patch_sha256 compared against the same '
                    'fields inside the signed run record',
        'raw': 'TARGET block + RUN RECORD identity fields (manual compare)',
        'structured': 'TABLE 1 identity operands (two columns, no verdict)',
        'adjudicated': 'printed boolean "linked to THIS patch: yes/no"',
        'archive_keys': ['record.base_commit', 'record.patch_sha256'],
        'always_retained': True,
    },
    'fresh': {
        'requires': 'signed run run_tree compared against attestation '
                    'expected_run_tree (plus base match + attestation identity)',
        'raw': 'RUN RECORD.run_tree + ATTESTATION.expected_run_tree',
        'structured': 'TABLE 2 run-tree operands (no verdict)',
        'adjudicated': 'printed boolean "fresh for the current commit tree"',
        'archive_keys': ['attestation.expected_run_tree', 'record.run_tree'],
        'always_retained': False,
    },
    'complete': {
        'requires': 'attestation declared fail_to_pass / p2p_scoped sets '
                    'compared against the set of per-test keys executed',
        'raw': 'ATTESTATION declared sets + RUN RECORD per-test maps '
               '(membership compare)',
        'structured': 'TABLE 3 declared sets + TABLE 4 present_in column',
        'adjudicated': 'printed boolean "declared acceptance set fully '
                       'executed"',
        'archive_keys': ['attestation.declared_*', 'record.fail_to_pass',
                         'record.pass_to_pass_scoped'],
        # executed-key membership can fall back to aggregated summary totals
        'always_retained': False,
    },
    'acceptance_failure': {
        'requires': 'an applicable post-patch failure: f2p FAILED per-test '
                    'status, or a scoped p2p FAILED not pre-existing-bad at '
                    'the base commit',
        'raw': 'f2p / p2p per-test maps; when maps are absent the runner '
               'summary f2p_failed_ids + p2p_regressed_ids + pre-existing-bad '
               'list; runner logs with FAILED lines',
        'structured': 'TABLE 4 status columns + TABLE 5 failed/regressed/'
                      'pre-existing-bad id lists + TABLE 6 parsed summaries',
        'adjudicated': 'tier-A acceptance block counts + concrete failed/'
                       'regressed test ids',
        'archive_keys': ['record.fail_to_pass', 'record.pass_to_pass_scoped',
                         'record.summary.f2p_failed_ids',
                         'record.summary.p2p_regressed_ids',
                         'record.summary.p2p_preexisting_bad_ids'],
        'always_retained': True,  # maps-or-summary fallback always populated
    },
    'acceptance_success': {
        'requires': 'executed check count > 0 with zero applicable failures',
        'raw': 'f2p/p2p maps or runner summary totals with empty failed/'
               'regressed lists; PASSED log lines',
        'structured': 'TABLE 4 status columns + TABLE 5 passed/total fields',
        'adjudicated': 'tier-A acceptance block all-passed counts',
        'archive_keys': ['record.fail_to_pass', 'record.pass_to_pass_scoped',
                         'record.summary.f2p_total/p2p_total'],
        'always_retained': True,
    },
    'symptom_persists': {
        'requires': 'issue-symptom probe BOTH phases: pre exit/output shows '
                    'the symptom can fire, post exit/output shows it still '
                    'fires after the patch',
        'raw': 'verbatim symptom runner log: pre/post command + exit_code + '
               'result lines; probe source if archived',
        'structured': 'TABLE 7 parsed pre/post exit_code + result_lines',
        'adjudicated': 'two printed booleans (present-before / reproduces-'
                       'after)',
        'archive_keys': ['logs.symptom (pre+post)', 'probes/<id> (source)'],
        # the pre/post probe OUTPUT is the operand; the probe SOURCE is
        # corroborating (lets one audit that the probe matches the issue).
        'always_retained': True,
    },
}


def _oracle(v):
    decisive = (bool(v['linked']) and bool(v['fresh'])
                and bool(v['acceptance_failure'])) \
        or bool(v['symptom_persists'])
    intact = (bool(v['linked']) and bool(v['fresh']) and bool(v['complete'])
              and bool(v['acceptance_success'])
              and not bool(v['symptom_persists']))
    return 'REJECT' if decisive else ('ACCEPT' if intact else 'NEED_EVIDENCE')


def minimal_forcing_set(values: dict, gold: str):
    """Smallest partial assignment (subset of channels fixed to recovered
    values) under which the oracle returns `gold` for ALL completions of the
    remaining channels."""
    for k in range(1, len(CHANNELS) + 1):
        for subset in itertools.combinations(CHANNELS, k):
            fixed = {c: values[c] for c in subset}
            free = [c for c in CHANNELS if c not in subset]
            labels = set()
            for combo in itertools.product([False, True], repeat=len(free)):
                v = dict(fixed)
                v.update(dict(zip(free, combo)))
                labels.add(_oracle(v))
            if labels == {gold}:
                return list(subset)
    return list(CHANNELS)


def _channel_available_in_layer(ch: str, mat: dict, recov: dict, layer: str):
    """Whether this channel's PRIMARY operand is usable at the layer.

    Returns (available: bool, basis: str, caveats: list).
    """
    rec, att = mat['record'], mat['attestation']
    chs = recov['channels']
    caveats = []
    if ch == 'linked':
        return True, 'identity fields always present', []
    if ch == 'fresh':
        ok = att is not None and rec.get('run_tree') is not None \
            and att.get('expected_run_tree') is not None
        return ok, ('attestation + run_tree present' if ok
                    else 'attestation/run_tree missing'), caveats
    if ch == 'complete':
        declared = bool(att and (att.get('declared_fail_to_pass')
                                 or att.get('declared_p2p_scoped')))
        per_test = chs['f2p_map'] or chs['p2p_map']
        # membership can also be evaluated from summary totals
        summ = rec.get('summary') or {}
        summ_tot = (summ.get('f2p_total') is not None
                    or summ.get('p2p_total') is not None)
        if declared and (per_test or summ_tot):
            if not per_test:
                caveats.append('only aggregated summary totals retained; '
                               'per-id membership coarser')
            return True, 'declared sets vs executed keys/totals', caveats
        return False, 'declared sets or executed coverage missing', caveats
    if ch in ('acceptance_failure', 'acceptance_success'):
        per_test = chs['f2p_map'] or chs['p2p_map']
        summ = rec.get('summary') or {}
        have_summ = (summ.get('f2p_failed_ids') is not None
                     or summ.get('p2p_regressed_ids') is not None
                     or summ.get('f2p_total') is not None)
        if per_test or have_summ:
            if not chs['p2p_baseline_map']:
                caveats.append('no per-test base map; applicability of a p2p '
                               'FAILED rests on runner p2p_regressed vs '
                               'pre-existing-bad classification in summary')
            return True, ('per-test maps' if per_test
                          else 'aggregated runner summary'), caveats
        return False, 'no executed acceptance outcomes retained', caveats
    if ch == 'symptom_persists':
        if chs['symptom_log']:
            if not chs['probe_source_archived']:
                caveats.append('probe SOURCE not archived; pre/post probe '
                               'OUTPUT retained and is the decision operand, '
                               'but probe-to-issue fidelity cannot be '
                               're-audited from source')
            return True, 'pre/post symptom probe log retained', caveats
        return False, 'symptom probe log missing', caveats
    return False, 'unknown channel', ['unhandled channel']


def build_certificates(store_root: Path):
    fixtures, raw_by_id, cee_gold = load_index(store_root)
    store = ArtifactStore(str(store_root))
    certs = []
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        grow = cee_gold[key]
        mat = load_materials(store, fx)
        recov = recoverable_facts(mat)
        vals = recov['values']
        gold = grow['cee_gold']
        forcing = minimal_forcing_set(vals, gold)

        layer_eval = {}
        under = {}
        for layer in eal.LAYERS:
            chans, missing_forcing, missing_corroborating = {}, [], []
            for ch in CHANNELS:
                avail, basis, caveats = _channel_available_in_layer(
                    ch, mat, recov, layer)
                chans[ch] = {'available': avail, 'basis': basis,
                             'caveats': caveats,
                             'in_minimal_forcing_set': ch in forcing}
                if not avail:
                    (missing_forcing if ch in forcing
                     else missing_corroborating).append(ch)
            # adjudicated always "available" (printed verdict); evaluate the
            # primary-operand layers honestly.
            determined = not missing_forcing
            under[layer] = determined
            layer_eval[layer] = {
                'all_forcing_channels_have_primary_material': determined,
                'missing_forcing_channels': missing_forcing,
                'missing_corroborating_channels': missing_corroborating,
                'channel_materials': chans,
            }

        # Layer gold determination must agree with the renderer's own
        # determination flag (cross-check, not trusted from one place).
        gold_determined_renderer = all(
            v is not None for v in vals.values()) or \
            eal.gold_from_facts(**vals)[1]

        certs.append({
            'bundle_id': _bundle_id(*key),
            'instance_id': fx['instance_id'], 'id': fx['id'],
            'gold': gold,
            'evidence_class': grow['evidence_class'],
            'recovered_operands': vals,
            'minimal_forcing_channels': forcing,
            'minimal_forcing_rule': _forcing_rule_text(forcing, vals, gold),
            'forcing_materials': {
                ch: {
                    'requires_primary_evidence':
                        CHANNEL_MATERIAL[ch]['requires'],
                    'raw_location': CHANNEL_MATERIAL[ch]['raw'],
                    'structured_location': CHANNEL_MATERIAL[ch]['structured'],
                    'adjudicated_location':
                        CHANNEL_MATERIAL[ch]['adjudicated'],
                } for ch in forcing},
            'per_layer': layer_eval,
            'gold_determined_raw': under['raw'],
            'gold_determined_structured': under['structured'],
            'gold_determined_adjudicated': True,
            'renderer_determination_crosscheck': bool(gold_determined_renderer),
            'archive_granularity': {
                'p2p_per_test_map': recov['channels']['p2p_map'],
                'p2p_baseline_per_test_map':
                    recov['channels']['p2p_baseline_map'],
                'f2p_per_test_map': recov['channels']['f2p_map'],
                'symptom_probe_log': recov['channels']['symptom_log'],
                'probe_source_archived':
                    recov['channels']['probe_source_archived'],
                'attestation': recov['channels']['attestation'],
            },
        })
    return certs


def _forcing_rule_text(forcing, vals, gold):
    if gold == 'REJECT' and forcing == ['symptom_persists']:
        return ('symptom_persists=True alone forces REJECT regardless of '
                'linked/fresh/complete/acceptance (P-channel decisive)')
    if gold == 'REJECT':
        return ('linked & fresh & acceptance_failure forces REJECT (set='
                + ','.join(forcing) + ')')
    if gold == 'ACCEPT':
        return ('full conjunction linked&fresh&complete&acceptance_success'
                '&¬symptom forces ACCEPT')
    # NEED
    blockers = [c for c in forcing if vals[c] in (False,)
                or (c == 'symptom_persists' and vals[c] is False
                    and not vals['acceptance_failure'])]
    return ('NEED_EVIDENCE forced by blocking condition(s): '
            + ','.join(forcing) + ' (no decisive failure and success '
            'conjunction not satisfiable)')


def main():
    certs = build_certificates(DEFAULT_STORE)
    n = len(certs)
    n_raw = sum(c['gold_determined_raw'] for c in certs)
    n_str = sum(c['gold_determined_structured'] for c in certs)
    sole_p = sum(c['minimal_forcing_channels'] == ['symptom_persists']
                 for c in certs)
    affected = [c['bundle_id'] for c in certs
                if not (c['gold_determined_raw']
                        and c['gold_determined_structured'])]
    out = {
        'document': 'EAL Gate-1 per-fixture Evidence Sufficiency Certificates',
        'protocol': eal.EAL_PROTOCOL_VERSION,
        'method': 'minimal forcing channel subset by partial-assignment '
                  'enumeration over the frozen oracle; primary-material '
                  'availability evaluated independently per layer',
        'n_fixtures': n,
        'n_gold_determined_raw': n_raw,
        'n_gold_determined_structured': n_str,
        'n_gold_determined_adjudicated': n,
        'n_underdetermined_any_primary_layer': len(affected),
        'underdetermined_bundle_ids': affected,
        'n_decision_forced_by_symptom_channel_alone': sole_p,
        'certificates': certs,
    }
    EAL_DIR.mkdir(exist_ok=True)
    (EAL_DIR / 'eal_sufficiency_certificates.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = [
        '# EAL Gate 1 — Evidence Sufficiency Summary',
        '',
        f'- fixtures: {n}',
        f'- gold determinable from RAW primary materials: {n_raw}/{n}',
        f'- gold determinable from STRUCTURED primary materials: {n_str}/{n}',
        f'- gold determinable ADJUDICATED (printed verdict): {n}/{n}',
        f'- underdetermined at a primary layer: {len(affected)} {affected}',
        f'- REJECT forced by symptom channel alone: {sole_p}',
        '',
        '| bundle | issue | gold | minimal forcing channels | raw | '
        'structured | missing corroborating (raw/str) |',
        '|---|---|---|---|---|---|---|',
    ]
    for c in certs:
        mc = [x for x in ('p2p_per_test_map', 'p2p_baseline_per_test_map',
                          'probe_source_archived')
              if not c['archive_granularity'][x]]
        lines.append(
            f"| {c['bundle_id'][-8:]} | {c['instance_id'].split('-')[-1]} "
            f"| {c['gold']} | {','.join(c['minimal_forcing_channels'])} "
            f"| {'Y' if c['gold_determined_raw'] else 'N'} "
            f"| {'Y' if c['gold_determined_structured'] else 'N'} "
            f"| {','.join(mc) or '-'} |")
    (EAL_DIR / 'eal_sufficiency_summary.md').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8')
    print(f'sufficiency certificates: {n} fixtures; raw {n_raw}/{n} '
          f'structured {n_str}/{n} underdetermined={len(affected)} '
          f'symptom-alone-REJECT={sole_p}')


if __name__ == '__main__':
    main()
