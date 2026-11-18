"""Independent verification of the returned human review (2026-11-08).

Read-only over every frozen artifact. Writes only to
evidence_store_human_gold/adjudication_v1/.

Pipeline:
 1. archive hashes of the two returned files
 2. verify the 144 workbench-embedded evidence files (internal sha and
    byte-equality with the frozen on-disk blind packets, both cohorts)
 3. verify sealed packet->instance mapping
 4. reconcile human blind labels vs GLM pre-labels vs PROVISIONAL oracle
 5. diagnose the hand-edited returned CSV (column shift)
 6. protocol-gap checks (FR1/FR2, signature, time, identity, old timestamp)
 7. recompute G4 statistics under the single recorded arbitration
    (19346 ACCEPT->REJECT); 15875 stays frozen REJECT (no arbitration)
No gold file is rewritten; promotion requires human decisions documented
in the output report.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import os
import re

from evidence.g4_verify_v2 import clopper_pearson

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
HUMAN = os.path.join(ROOT, 'paper_sprint', 'human')
RET = os.path.join(HUMAN, 'returns')
OUT = os.path.join(ROOT, 'evidence_store_human_gold', 'adjudication_v1')

RET_JSON = os.path.join(RET, 'human_review_workbench_return_20261108.json')
RET_CSV = os.path.join(
    RET, 'human_review_tracking_filled_return_20261108.csv')
WORKBENCH = os.path.join(HUMAN, 'human_review_workbench.html')

COHORTS = {
    'G3-C.1': {
        'n': 8,
        'packets': os.path.join(
            ROOT, 'evidence_store_g3c1', 'human_annotation', 'packets'),
        'sealed': os.path.join(
            ROOT, 'evidence_store_g3c1', 'human_annotation',
            'SEALED_packet_mapping.json'),
        'glm': os.path.join(ROOT, 'evidence_store_glm_aux', 'records'),
    },
    'G3-A': {
        'n': 10,
        'packets': os.path.join(
            ROOT, 'evidence_store_g3c0', 'human_annotation', 'packets'),
        'sealed': os.path.join(
            ROOT, 'evidence_store_g3c0', 'human_annotation',
            'SEALED_packet_mapping.json'),
        'glm': os.path.join(ROOT, 'evidence_store_glm_aux_g3a', 'records'),
    },
}
PACKET_FILES = [
    '01_problem_statement.txt', '02_candidate_patch.diff',
    '03_maintainer_test_patch.diff', '04_declared_test_ids.json',
    '05_ci_fail_to_pass.log', '06_ci_pass_to_pass_scoped.log',
    '07_ci_pass_to_pass_base_commit.log', '08_issue_symptom_probe.log',
]
CELLS = ('A', 'B', 'C', 'D')
MODELS = ('gpt-4.1-mini', 'deepseek-flash')


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load_workbench_data():
    html = open(WORKBENCH, encoding='utf-8').read()
    i = html.index('const DATA = ') + len('const DATA = ')
    dec = json.JSONDecoder()
    data, _end = dec.raw_decode(html[i:])
    return data


def main():
    os.makedirs(OUT, exist_ok=True)
    returned = json.load(open(RET_JSON, encoding='utf-8'))
    wb = load_workbench_data()

    findings = {'source_files': {}, 'packet_integrity': {},
                'reconciliation': [], 'csv_diagnosis': {},
                'protocol_gaps': [], 'scenario_stats': {}}
    findings['source_files'] = {
        os.path.basename(RET_JSON): {
            'sha256': sha256_file(RET_JSON),
            'bytes': os.path.getsize(RET_JSON)},
        os.path.basename(RET_CSV): {
            'sha256': sha256_file(RET_CSV),
            'bytes': os.path.getsize(RET_CSV)},
        'workbench_html': {
            'sha256': sha256_file(WORKBENCH),
            'bytes': os.path.getsize(WORKBENCH)},
    }

    # ---- 2. packet integrity ------------------------------------------------
    int_results = {'embedded_files': 0, 'embedded_sha_matches_disk': 0,
                   'decoded_text_matches_disk': 0,
                   'disk_match_ok': 0, 'failures': [],
                   'sealed_mapping_ok': True}
    for p in wb['packets']:
        cfg = COHORTS[p['set']]
        pdir = os.path.join(cfg['packets'], p['packet'])
        for f in p['files']:
            int_results['embedded_files'] += 1
            # NB embedded sha256 is over the on-disk bytes (the builder hashes
            # raw bytes; decoded text uses errors='replace' and cannot be
            # re-encoded byte-identically), so integrity is checked against
            # the frozen disk files rather than by re-hashing the string.
            disk = os.path.join(pdir, f['name'])
            if not os.path.exists(disk):
                int_results['failures'].append(f"missing disk file {disk}")
                continue
            disk_bytes = open(disk, 'rb').read()
            disk_sha = sha256_bytes(disk_bytes)
            disk_text = open(disk, encoding='utf-8', errors='replace').read()
            sha_ok = disk_sha == f['sha256']
            txt_ok = disk_text == f['text']
            if sha_ok:
                int_results['embedded_sha_matches_disk'] += 1
            if txt_ok:
                int_results['decoded_text_matches_disk'] += 1
            if sha_ok and txt_ok:
                int_results['disk_match_ok'] += 1
            else:
                int_results['failures'].append(
                    f"disk divergence {p['id']}/{f['name']} "
                    f"(sha_ok={sha_ok}, text_ok={txt_ok})")
        sealed = json.load(open(cfg['sealed'], encoding='utf-8'))
        if sealed['mapping_packet_to_instance'][p['packet']] != p['instance']:
            int_results['sealed_mapping_ok'] = False
            int_results['failures'].append(
                f"sealed mapping mismatch {p['id']}")
    findings['packet_integrity'] = int_results

    # ---- 3/4. reconciliation ------------------------------------------------
    # frozen provisional oracle from the G4 manifest (cell A, either model)
    oracle = {}
    man_path = os.path.join(
        ROOT, 'evidence_store_g4_sufficiency', 'g4_cell_manifest.jsonl')
    for line in open(man_path, encoding='utf-8'):
        r = json.loads(line)
        if r['cell'] == 'A' and r['model_profile'] == 'gpt-4.1-mini':
            oracle[r['instance_id'].split('-')[-1]] = r['oracle_gold']

    glm_label = {}
    for cfg in COHORTS.values():
        for f in sorted(glob.glob(os.path.join(cfg['glm'], 'P*.json'))):
            pid = os.path.splitext(os.path.basename(f))[0]
            rec = json.load(open(f, encoding='utf-8'))
            glm_label[pid] = rec['verdict'].get('label')

    rows = []
    for p in wb['packets']:
        pid_key = f"{p['set']}::{p['packet']}"
        st = returned['packets'].get(pid_key, {})
        blind = (st.get('blind') or {}).get('label')
        issue = p['issue']
        rows.append({
            'set': p['set'], 'packet': p['packet'], 'issue': issue,
            'oracle_provisional': oracle[issue],
            'glm': p['glm']['label'],
            'glm_record_check': glm_label[p['packet']],
            'human_blind': blind,
            'human_ts': (st.get('blind') or {}).get('ts'),
            'indep_flag': (st.get('blind') or {}).get('indep'),
            'mins': (st.get('blind') or {}).get('mins'),
            'conf': (st.get('blind') or {}).get('conf'),
            'glm_review_click': (st.get('glmReview') or {}).get('agree'),
            'unblinded': st.get('unblinded'),
            'arb': st.get('arb'),
            'human_vs_oracle': (
                'agree' if blind == oracle[issue] else 'DISAGREE'),
            'human_vs_glm': (
                'agree' if blind == p['glm']['label'] else 'DISAGREE'),
        })
    findings['reconciliation'] = rows

    n = len(rows)
    n_blind = sum(1 for r in rows if r['human_blind'] in
                  ('ACCEPT', 'REJECT', 'NEEDS_REVIEW'))
    n_oracle_agree = sum(1 for r in rows if r['human_vs_oracle'] == 'agree')
    n_glm_agree = sum(1 for r in rows if r['human_vs_glm'] == 'agree')

    # ---- 5. CSV diagnosis ---------------------------------------------------
    with open(RET_CSV, encoding='utf-8', newline='') as fh:
        reader = list(csv.reader(fh))
    header, body = reader[0], reader[1:]
    field_counts = {len(r) for r in body}
    # canonical machine export would carry 10 fields incl. the blind label;
    # returned rows carry 9 because the oracle column was deleted by hand,
    # shifting every later value under the wrong header.
    shift_confirmed = all(len(r) == 9 for r in body) and len(header) == 10
    # cross-check: value under CSV header 'oracle_gold_provisional' must
    # equal the JSON blind label (not the frozen oracle) for every row
    shift_evidence = []
    idx = {h: i for i, h in enumerate(header)}
    for r in body:
        issue = r[idx['issue_revealed_after_unblind']]
        jrow = next(x for x in rows if x['issue'] == issue)
        shift_evidence.append({
            'issue': issue,
            'csv_oracle_column': r[idx['oracle_gold_provisional']],
            'frozen_oracle': jrow['oracle_provisional'],
            'json_human_blind': jrow['human_blind'],
            'csv_col_equals_blind':
                r[idx['oracle_gold_provisional']] == jrow['human_blind'],
        })
    findings['csv_diagnosis'] = {
        'header_fields': len(header), 'row_field_counts': sorted(field_counts),
        'column_shift_confirmed': shift_confirmed,
        'note': 'oracle column deleted by hand; all later columns shifted; '
                'JSON export is the authoritative source',
        'per_row': shift_evidence,
        'frozen_oracle_error_in_csv': [
            x['issue'] for x in shift_evidence
            if x['csv_oracle_column'] != x['frozen_oracle']],
    }

    # ---- 6. protocol gaps ---------------------------------------------------
    gaps = []
    if not returned.get('sign'):
        gaps.append('SIGN_NULL: no annotator name/role/attestation recorded')
    if not returned['fr']['FR1'].get('blind'):
        gaps.append('FR1_PENDING: focused review on 19495 not answered')
    if not returned['fr']['FR2'].get('blind'):
        gaps.append('FR2_PENDING: focused review on 14248/15875 not answered')
    if not returned.get('c19346') or not returned['c19346'].get('blind'):
        gaps.append('C19346_CARD_NULL: dedicated 19346 arbitration card not '
                    'filled (a packet-level arb verdict exists instead)')
    missing_mins = [r['packet'] for r in rows if not r['mins']]
    if missing_mins:
        gaps.append(f'MINS_EMPTY: time not recorded on {len(missing_mins)}/18 '
                    f'packets (protocol requires per-packet time)')
    missing_conf = [r['packet'] for r in rows if not r['conf']]
    if missing_conf:
        gaps.append(f'CONF_EMPTY: confidence not recorded on '
                    f'{len(missing_conf)}/18 packets')
    old = [r for r in rows if r['human_ts'] and r['human_ts'][:10] <
           '2026-11-08']
    for r in old:
        gaps.append(f"OLD_TIMESTAMP {r['set']}::{r['packet']} issue "
                    f"{r['issue']}: blind locked {r['human_ts']} (from the "
                    '2026-11-01 author quick-look session, then tagged '
                    'research_excluded; needs a fresh independent lock)')
    # contradictory GLM-review clicks
    for r in rows:
        if (r['human_vs_glm'] == 'DISAGREE'
                and r['glm_review_click'] == 'yes'):
            gaps.append(f"CONTRADICTORY_GLM_CLICK {r['set']}::"
                        f"{r['packet']} issue {r['issue']}: blind "
                        f"{r['human_blind']} != GLM {r['glm']} but review "
                        'marked "agree"')
    # unresolved arbitration needs
    for r in rows:
        if r['human_vs_oracle'] == 'DISAGREE':
            arb = r['arb'] or {}
            if not arb.get('verdict'):
                gaps.append(f"UNRESOLVED_DISAGREEMENT issue {r['issue']}: "
                            f"human {r['human_blind']} vs oracle "
                            f"{r['oracle_provisional']} (GLM {r['glm']}); "
                            'no arbiter verdict')
    findings['protocol_gaps'] = gaps

    # ---- 7. G4 recomputation under recorded arbitration --------------------
    # live verdicts straight from frozen raw + manifest
    man = {}
    for line in open(man_path, encoding='utf-8'):
        rr = json.loads(line)
        man[(rr['model_profile'], rr['serial'])] = rr
    verdict = {m: {} for m in MODELS}
    for f in glob.glob(os.path.join(
            ROOT, 'evidence_store_g4_live', 'raw', 'live', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        rr = man[(d['model_profile'], d['serial'])]
        iid = rr['instance_id'].split('-')[-1]
        v = json.loads(d['answer_raw'])['decision']
        verdict[d['model_profile']].setdefault(iid, {})[rr['cell']] = v

    rejects0 = {i for i, g in oracle.items() if g == 'REJECT'}
    accepts0 = set(oracle) - rejects0
    # Scenario ARB-1: only the recorded 19346 arbitration (ACCEPT->REJECT)
    flip = {'19346': 'REJECT'}
    gold1 = dict(oracle)
    gold1.update(flip)
    rejects1 = {i for i, g in gold1.items() if g == 'REJECT'}

    def cell_stats(gold, rejects):
        out = {}
        for m in MODELS:
            out[m] = {}
            for c in CELLS:
                accepts = [i for i in sorted(gold)
                           if verdict[m][i][c] == 'ACCEPT']
                unsup = sorted(set(accepts) & rejects)
                match = sum(1 for i in gold
                            if verdict[m][i][c] == gold[i])
                out[m][c] = {
                    'raw_accepts': len(accepts),
                    'unsupported_accepts_on_rejects': unsup,
                    'unsup_x': len(unsup), 'reject_n': len(rejects),
                    'cp95_unsup': list(clopper_pearson(
                        len(unsup), len(rejects))),
                    'oracle_match_x': match, 'oracle_match_n': len(gold),
                    'cp95_match': list(clopper_pearson(match, len(gold))),
                }
        return out

    base = cell_stats(oracle, rejects0)
    sc1 = cell_stats(gold1, rejects1)

    # B-cell strata under ARB-1
    strata1 = {}
    for m in MODELS:
        b_bad = {i for i in rejects1 if verdict[m][i]['B'] == 'ACCEPT'}
        b_good_bad = {i for i in (set(gold1) - rejects1)
                      if verdict[m][i]['B'] == 'ACCEPT'}
        strata1[m] = {
            'unsupported_on_rejects': (len(b_bad), len(rejects1),
                                       sorted(b_bad)),
            'cp95_reject_stratum': list(clopper_pearson(
                len(b_bad), len(rejects1))),
            'accepts_on_accept_stratum': (len(b_good_bad),
                                          len(gold1) - len(rejects1),
                                          sorted(b_good_bad)),
            'cp95_accept_stratum': list(clopper_pearson(
                len(b_good_bad), len(gold1) - len(rejects1))),
        }

    # hypothetical ARB-2 (NOT adopted): also honor human blind on 15875
    gold2 = dict(gold1)
    gold2['15875'] = 'ACCEPT'
    rejects2 = {i for i, g in gold2.items() if g == 'REJECT'}
    sc2 = cell_stats(gold2, rejects2)

    findings['scenario_stats'] = {
        'baseline_provisional': {
            'rejects': sorted(rejects0), 'n_rejects': len(rejects0),
            'cells': base},
        'ARB1_adopted_candidate_19346_flip': {
            'arbitration_source': 'returned JSON packet G3-C.1::P03 arb',
            'arb_verdict': 'REJECT', 'arb_reason': 'incorrect',
            'arbiter_name': None, 'arbiter_date': None,
            'rejects': sorted(rejects1), 'n_rejects': len(rejects1),
            'cells': sc1, 'strata_B': strata1,
            'H1_A_B_unchanged': True,
            'H1_note': 'condition gold is NEED by construction; oracle '
                       'flips cannot change A/B U counts, McNemar p, paired '
                       'delta or its bootstrap CI',
            'interaction_unchanged': True,
            'interaction_note': 'DiD and between-model contrasts use raw '
                                'binary acceptance Y, gold-independent'},
        'ARB2_hypothetical_not_adopted_15875_human_blind': {
            'note': 'human blind ACCEPT on 15875 has no arbitration; shown '
                    'for sensitivity only, frozen label retained',
            'rejects': sorted(rejects2), 'n_rejects': len(rejects2),
            'cells': sc2},
    }
    findings['gold_promotion'] = {
        'decision': 'NOT_PROMOTED',
        'reason': 'gold stays PROVISIONAL: identity/signature missing, '
                  'arbiter independence unverifiable, FR1/FR2 unanswered, '
                  '15875 disagreement unresolved, one stale 2026-11-01 lock',
        'adopted_change_now': [],
        'candidate_change_after_human_confirmation': ['19346 ACCEPT->REJECT'],
    }
    findings['agreement_summary'] = {
        'blind_labels_locked': f'{n_blind}/{n}',
        'human_blind_vs_provisional_oracle': f'{n_oracle_agree}/{n}',
        'human_blind_vs_glm': f'{n_glm_agree}/{n}',
        'disagreements_vs_oracle': [
            r['issue'] for r in rows if r['human_vs_oracle'] == 'DISAGREE'],
        'disagreements_vs_glm': [
            r['issue'] for r in rows if r['human_vs_glm'] == 'DISAGREE'],
    }

    out_json = os.path.join(OUT, 'human_gold_adjudication_v1.json')
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump(findings, fh, indent=2, ensure_ascii=False)

    # corrected canonical tracking CSV derived from the authoritative JSON
    out_csv = os.path.join(OUT, 'human_review_tracking_corrected_v1.csv')
    with open(out_csv, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['set', 'packet', 'issue', 'oracle_gold_provisional',
                    'annotator2_blind', 'glm_label', 'human_vs_oracle',
                    'human_vs_glm', 'arb_verdict', 'arb_reason',
                    'blind_ts', 'indep_flag', 'unblinded'])
        for r in rows:
            arb = r['arb'] or {}
            w.writerow([r['set'], r['packet'], r['issue'],
                        r['oracle_provisional'], r['human_blind'], r['glm'],
                        r['human_vs_oracle'], r['human_vs_glm'],
                        arb.get('verdict', ''), arb.get('reason', ''),
                        r['human_ts'], r['indep_flag'], r['unblinded']])

    write_markdown(findings, rows, os.path.join(
        OUT, 'human_gold_adjudication_v1.md'))
    print('integrity files:', int_results['embedded_files'],
          'sha_ok:', int_results['embedded_sha_matches_disk'],
          'disk_ok:', int_results['disk_match_ok'],
          'failures:', len(int_results['failures']))
    print('blind vs oracle:', findings['agreement_summary'][
        'human_blind_vs_provisional_oracle'],
          'vs glm:', findings['agreement_summary']['human_blind_vs_glm'])
    print('protocol gaps:', len(gaps))
    print('->', os.path.relpath(OUT, ROOT))


def write_markdown(findings, rows, path):
    L = []
    L.append('# Human gold return — independent verification & adjudication '
             'record v1 (2026-11-08)\n')
    L.append('All frozen inputs read-only. This record promotes no gold by '
             'itself.\n')
    L.append('## 1. Source files (sha256)')
    for k, v in findings['source_files'].items():
        L.append(f"- `{k}` — {v['bytes']} bytes — `{v['sha256']}`")
    pi = findings['packet_integrity']
    L.append('\n## 2. Blind-packet integrity')
    L.append(f"- embedded evidence files: {pi['embedded_files']}")
    L.append(f"- embedded sha256 matches frozen disk file: "
             f"{pi['embedded_sha_matches_disk']}")
    L.append(f"- decoded text matches frozen disk file: "
             f"{pi['decoded_text_matches_disk']}")
    L.append(f"- full byte+text identity: "
             f"{pi['disk_match_ok']}")
    L.append(f"- sealed packet->instance mapping ok: "
             f"{pi['sealed_mapping_ok']}")
    for x in pi['failures']:
        L.append(f"  - FAILURE: {x}")
    L.append('\n## 3. Reconciliation (18 packets)')
    L.append('| set | packet | issue | oracle (prov.) | GLM | human blind '
             '| vs oracle | vs GLM | GLM-click | arb | blind ts |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        arb = (r['arb'] or {}).get('verdict', '')
        L.append('| {set} | {packet} | {issue} | {o} | {g} | {h} | {vo} | '
                 '{vg} | {click} | {arb} | {ts} |'.format(
                     set=r['set'], packet=r['packet'], issue=r['issue'],
                     o=r['oracle_provisional'], g=r['glm'],
                     h=r['human_blind'], vo=r['human_vs_oracle'],
                     vg=r['human_vs_glm'],
                     click=r['glm_review_click'] or '', arb=arb,
                     ts=(r['human_ts'] or '')[:10]))
    s = findings['agreement_summary']
    L.append(f"\n- blind labels locked: **{s['blind_labels_locked']}**")
    L.append(f"- human blind vs PROVISIONAL oracle: **"
             f"{s['human_blind_vs_provisional_oracle']}** "
             f"(disagreements: {', '.join(s['disagreements_vs_oracle'])})")
    L.append(f"- human blind vs GLM: **{s['human_blind_vs_glm']}** "
             f"(disagreements: {', '.join(s['disagreements_vs_glm'])})")
    cd = findings['csv_diagnosis']
    L.append('\n## 4. Returned CSV diagnosis')
    L.append(f"- header fields {cd['header_fields']}, row field counts "
             f"{cd['row_field_counts']}; column-shift confirmed: "
             f"**{cd['column_shift_confirmed']}**")
    L.append(f"- {cd['note']}")
    L.append('- rows whose CSV "oracle" column differs from frozen oracle: '
             + ', '.join(cd['frozen_oracle_error_in_csv']))
    L.append('- authoritative source = returned JSON; corrected canonical '
             'CSV written alongside this report.')
    L.append('\n## 5. Protocol gaps (must be closed before gold promotion)')
    for g in findings['protocol_gaps']:
        L.append(f'- {g}')
    L.append('\n## 6. G4 recomputation — ARB-1 candidate (19346 '
             'ACCEPT->REJECT only)')
    sc = findings['scenario_stats']['ARB1_adopted_candidate_19346_flip']
    L.append(f"reject stratum becomes {sc['n_rejects']} issues: "
             f"{', '.join(sc['rejects'])}")
    L.append('\n| model | cell | raw ACCEPT | unsupported on rejects '
             '(x/n) | CP95 | oracle match | CP95 |')
    L.append('|---|---|---|---|---|---|---|')
    for m in MODELS:
        for c in CELLS:
            d = sc['cells'][m][c]
            L.append(f"| {m} | {c} | {d['raw_accepts']} | {d['unsup_x']}/"
                     f"{d['reject_n']} | [{d['cp95_unsup'][0]:.3f},"
                     f"{d['cp95_unsup'][1]:.3f}] | {d['oracle_match_x']}/"
                     f"{d['oracle_match_n']} | [{d['cp95_match'][0]:.3f},"
                     f"{d['cp95_match'][1]:.3f}] |")
    L.append('\nB-cell strata under ARB-1:')
    for m in MODELS:
        st = sc['strata_B'][m]
        L.append(f"- {m}: rejects {st['unsupported_on_rejects'][0]}/"
                 f"{st['unsupported_on_rejects'][1]} "
                 f"{st['unsupported_on_rejects'][2]} CP95 "
                 f"[{st['cp95_reject_stratum'][0]:.3f},"
                 f"{st['cp95_reject_stratum'][1]:.3f}]; accept-stratum "
                 f"{st['accepts_on_accept_stratum'][0]}/"
                 f"{st['accepts_on_accept_stratum'][1]} CP95 "
                 f"[{st['cp95_accept_stratum'][0]:.3f},"
                 f"{st['cp95_accept_stratum'][1]:.3f}]")
    L.append('\n- H1 A/B (McNemar p=0.0078125, paired delta, bootstrap CI) '
             'and the exploratory DiD/between-model CIs are **unchanged** '
             '(gold-independent).')
    h2 = findings['scenario_stats'][
        'ARB2_hypothetical_not_adopted_15875_human_blind']
    L.append('\n### Hypothetical ARB-2 (NOT adopted; 15875 also flipped to '
             'ACCEPT)')
    L.append(f"reject stratum {h2['n_rejects']}: {', '.join(h2['rejects'])}")
    for m in MODELS:
        for c in ('B', 'C', 'D'):
            d = h2['cells'][m][c]
            L.append(f"- {m} {c}: unsupported {d['unsup_x']}/"
                     f"{d['reject_n']}, oracle match {d['oracle_match_x']}/"
                     f"{d['oracle_match_n']}")
    L.append('\n## 7. Promotion decision')
    gp = findings['gold_promotion']
    L.append(f"**{gp['decision']}** — {gp['reason']}")
    L.append(f"Pending confirmation, candidate change: "
             f"{', '.join(gp['candidate_change_after_human_confirmation'])}")
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
