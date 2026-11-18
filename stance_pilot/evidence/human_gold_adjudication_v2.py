"""Human gold adjudication record v2 (2026-11-08).

Builds on the read-only v1 verification and adds the human decisions
confirmed by the study coordinator in-session:
  - the 18 blind verdicts and packet-level arbitration were produced by an
    independent third-party annotator (verbal confirmation; a signed
    attestation with name/role remains a pre-submission action item);
  - FR1 = instrument_fix, FR2 = same_standard (human; agrees with GLM,
    rubric amendment = no, inferred from the A choices);
  - 15875 stays frozen REJECT and is disclosed as an unresolved
    human-vs-oracle disagreement (no arbiter verdict);
  - the 19495 blind label is the 2026-11-01 lock, retained by explicit
    coordinator decision (identical to the provisional oracle label);
  - 19346 carries a human arbiter verdict REJECT (returned JSON, packet
    G3-C.1::P03); it is recorded as the candidate post-adjudication label.

Gold is NOT mass-promoted: the adjudicated label set is published as a
separate versioned table and every G4 figure is reported under both the
frozen provisional labels and the ARB-1 human-reviewed scenario.
Read-only over all frozen inputs; writes only to
evidence_store_human_gold/adjudication_v2/.
"""
from __future__ import annotations

import csv
import glob
import json
import os

from evidence.g4_verify_v2 import clopper_pearson

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..')
V1_DIR = os.path.join(ROOT, 'evidence_store_human_gold', 'adjudication_v1')
OUT = os.path.join(ROOT, 'evidence_store_human_gold', 'adjudication_v2')
CELLS = ('A', 'B', 'C', 'D')
MODELS = ('gpt-4.1-mini', 'deepseek-flash')

FR_DECISIONS = {
    'FR1': {
        'issue': '19495',
        'human_choice': 'instrument_fix',
        'rubric_amendment': 'no',
        'rubric_amendment_basis': 'inferred from choice A; coordinator gave '
                                  'no separate amendment instruction',
        'glm_choice': 'instrument_fix', 'human_glm_agree': True,
        'meaning': 'the test_subs_CondSet assertion change repaired the test '
                   'instrument only; the acceptability oracle was not '
                   'redefined; 19495 ACCEPT label stands',
    },
    'FR2': {
        'issues': ['14248', '15875'],
        'human_choice': 'same_standard',
        'rubric_amendment': 'no',
        'rubric_amendment_basis': 'inferred from choice A; coordinator gave '
                                  'no separate amendment instruction',
        'glm_choice': 'same_standard', 'human_glm_agree': True,
        'meaning': 'both REJECTs apply one disjunctive standard (decisive '
                   'P2P regression on inputs the base handled); no split '
                   'pre-registration required',
    },
}


def load_live_verdicts():
    man = {}
    for line in open(os.path.join(
            ROOT, 'evidence_store_g4_sufficiency',
            'g4_cell_manifest.jsonl'), encoding='utf-8'):
        r = json.loads(line)
        man[(r['model_profile'], r['serial'])] = r
    verdict = {m: {} for m in MODELS}
    for f in glob.glob(os.path.join(
            ROOT, 'evidence_store_g4_live', 'raw', 'live', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        r = man[(d['model_profile'], d['serial'])]
        iid = r['instance_id'].split('-')[-1]
        verdict[d['model_profile']].setdefault(iid, {})[r['cell']] = \
            json.loads(d['answer_raw'])['decision']
    oracle = {}
    for (m, _ser), r in man.items():
        if m == 'gpt-4.1-mini' and r['cell'] == 'A':
            oracle[r['instance_id'].split('-')[-1]] = r['oracle_gold']
    return verdict, oracle


def cell_table(verdict, gold, rejects):
    out = {}
    for m in MODELS:
        out[m] = {}
        for c in CELLS:
            accepts = [i for i in sorted(gold)
                       if verdict[m][i][c] == 'ACCEPT']
            unsup = sorted(set(accepts) & rejects)
            match = sum(1 for i in gold if verdict[m][i][c] == gold[i])
            out[m][c] = {
                'raw_accepts': len(accepts),
                'unsup_issues': unsup,
                'unsup_x': len(unsup), 'reject_n': len(rejects),
                'cp95_unsup': list(clopper_pearson(len(unsup), len(rejects))),
                'oracle_match_x': match, 'oracle_match_n': len(gold),
                'cp95_match': list(clopper_pearson(match, len(gold))),
            }
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    v1 = json.load(open(os.path.join(
        V1_DIR, 'human_gold_adjudication_v1.json'), encoding='utf-8'))
    verdict, oracle = load_live_verdicts()

    # ---- final per-issue gold status --------------------------------------
    final = []
    for r in v1['reconciliation']:
        iid = r['issue']
        status = {
            'issue': iid, 'provisional_oracle': r['oracle_provisional'],
            'glm_label': r['glm'], 'human_blind': r['human_blind'],
            'human_arbiter': (r['arb'] or {}).get('verdict'),
            'human_arbiter_reason': (r['arb'] or {}).get('reason'),
        }
        if iid == '19346':
            status.update({
                'final_label_for_analysis': 'REJECT',
                'label_basis': 'HUMAN_ARBITER_OVERRIDE (returned JSON P03 '
                               'arb; dedicated 19346 card left blank)',
                'promotion_state': 'CANDIDATE_PENDING_SIGNED_ATTESTATION',
            })
        elif iid == '15875':
            status.update({
                'final_label_for_analysis': 'REJECT',
                'label_basis': 'FROZEN_PROVISIONAL_KEPT; human blind ACCEPT '
                               'disagreement unresolved (no arbiter); FR2 '
                               'same-standard decision supports the REJECT',
                'promotion_state': 'DISPUTED_PROVISIONAL',
            })
        elif iid == '19495':
            status.update({
                'final_label_for_analysis': 'ACCEPT',
                'label_basis': 'provisional label confirmed by human blind '
                               '(2026-11-01 lock retained by coordinator '
                               'decision); FR1 instrument-fix decision',
                'promotion_state': 'HUMAN_CONFIRMED_PENDING_SIGNATURE',
            })
        else:
            agree = r['human_vs_oracle'] == 'agree'
            status.update({
                'final_label_for_analysis': r['oracle_provisional'],
                'label_basis': 'human blind agrees with provisional oracle'
                if agree else 'see note',
                'promotion_state': 'HUMAN_CONFIRMED_PENDING_SIGNATURE'
                if agree else 'DISPUTED_PROVISIONAL',
            })
        final.append(status)

    gold_arb1 = {s['issue']: s['final_label_for_analysis'] for s in final}
    rejects0 = sorted(i for i, g in oracle.items() if g == 'REJECT')
    rejects1 = sorted(i for i, g in gold_arb1.items() if g == 'REJECT')

    record = {
        'record': 'human-gold-adjudication-v2',
        'date': '2026-11-08',
        'supersedes': 'adjudication_v1 (v1 retained unchanged)',
        'identity': {
            'annotator': 'independent third party (coordinator verbal '
                         'confirmation, in-session 2026-11-08)',
            'signed_attestation': 'NOT YET OBTAINED',
            'pre_submission_action': 'collect signed statement with name, '
                                     'role/competence, independence and date; '
                                     'until then HUMAN_CONFIRMED labels are '
                                     'not upgraded in the manuscript',
            'note_19495': 'blind lock timestamp 2026-11-01 (author quick-look '
                          'session, research_excluded); retained by explicit '
                          'coordinator decision; label equals provisional '
                          'oracle so no statistic changes',
        },
        'focused_reviews': FR_DECISIONS,
        'per_issue_final': final,
        'agreement': v1['agreement_summary'],
        'open_protocol_items': [
            'signed annotator/arbiter attestation missing',
            '15875 human-vs-oracle disagreement has no arbiter verdict',
            '19346 dedicated arbitration card blank (packet-level arb used)',
            'per-packet time and confidence fields empty (18/18)',
            'two contradictory GLM "agree" clicks on P03/P08 (verbal labels '
            'in JSON remain authoritative)',
        ],
        'scenarios': {
            'S0_frozen_provisional': {
                'rejects': rejects0,
                'cells': cell_table(verdict, oracle, set(rejects0)),
            },
            'S1_human_reviewed_ARB1': {
                'rejects': rejects1,
                'change_vs_S0': ['19346 ACCEPT->REJECT (human arbiter)'],
                'cells': cell_table(verdict, gold_arb1, set(rejects1)),
                'H1_unchanged': True,
                'H1_evidence': 'GPT 0/18->8/18 McNemar p=0.0078125, delta '
                               '-0.4444 [-0.667,-0.222]; DeepSeek 0/18->0/18 '
                               'p=1.0; condition gold is NEED by construction',
                'exploratory_contrasts_unchanged': True,
                'contrast_evidence': 'between-model difference 0.4444 '
                                     '[0.222,0.667]; interaction DiD 0.500 '
                                     '[0.278,0.722]; both use raw binary Y',
            },
        },
    }

    with open(os.path.join(OUT, 'human_gold_adjudication_v2.json'),
              'w', encoding='utf-8') as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)

    with open(os.path.join(OUT, 'human_final_gold_v2.csv'),
              'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['issue', 'provisional_oracle', 'glm_label',
                    'human_blind', 'human_arbiter', 'final_label',
                    'label_basis', 'promotion_state'])
        for s in final:
            w.writerow([s['issue'], s['provisional_oracle'], s['glm_label'],
                        s['human_blind'], s['human_arbiter'] or '',
                        s['final_label_for_analysis'], s['label_basis'],
                        s['promotion_state']])

    write_md(record, os.path.join(OUT, 'human_gold_adjudication_v2.md'))
    print('issues:', len(final),
          '| S0 rejects:', len(rejects0), '| S1 rejects:', len(rejects1))
    print('->', os.path.relpath(OUT, ROOT))


def write_md(rec, path):
    L = ['# Human gold adjudication record v2 (2026-11-08)\n',
         'Versioned record; v1 verification and all frozen evidence remain '
         'untouched.\n',
         '## 1. Identity and attestation',
         f"- Annotator: {rec['identity']['annotator']}",
         f"- Signed attestation: **{rec['identity']['signed_attestation']}**",
         f"- Pre-submission action: {rec['identity']['pre_submission_action']}",
         f"- 19495 note: {rec['identity']['note_19495']}",
         '', '## 2. Focused reviews (human decisions)',
    ]
    for k, d in rec['focused_reviews'].items():
        L.append(f"- **{k}** -> `{d['human_choice']}` (GLM: "
                 f"{d['glm_choice']}, agree={d['human_glm_agree']}); rubric "
                 f"amendment={d['rubric_amendment']} — {d['meaning']}")
    L += ['', '## 3. Per-issue final labels',
          '| issue | prov. oracle | GLM | human blind | human arbiter | '
          'final label | basis | state |',
          '|---|---|---|---|---|---|---|---|']
    for s in rec['per_issue_final']:
        L.append('| {issue} | {p} | {g} | {h} | {a} | **{f}** | {b} | {st} |'
                 .format(issue=s['issue'], p=s['provisional_oracle'],
                         g=s['glm_label'], h=s['human_blind'],
                         a=s['human_arbiter'] or '—',
                         f=s['final_label_for_analysis'],
                         b=s['label_basis'], st=s['promotion_state']))
    L += ['', 'Agreement: ' + json.dumps(rec['agreement'], ensure_ascii=False),
          '', '## 4. Open protocol items']
    for x in rec['open_protocol_items']:
        L.append(f'- {x}')
    L += ['', '## 5. G4 figures under both label scenarios',
          '### S0 frozen provisional vs S1 human-reviewed (ARB-1)',
          '| model | cell | S0 unsupported (x/n) | S0 match | '
          'S1 unsupported (x/n) | S1 match |',
          '|---|---|---|---|---|---|']
    s0, s1 = rec['scenarios']['S0_frozen_provisional'], \
        rec['scenarios']['S1_human_reviewed_ARB1']
    for m in MODELS:
        for c in CELLS:
            a, b = s0['cells'][m][c], s1['cells'][m][c]
            L.append(f"| {m} | {c} | {a['unsup_x']}/{a['reject_n']} | "
                     f"{a['oracle_match_x']}/{a['oracle_match_n']} | "
                     f"{b['unsup_x']}/{b['reject_n']} | "
                     f"{b['oracle_match_x']}/{b['oracle_match_n']} |")
    L += ['', '- H1 and exploratory contrasts are identical under S0 and S1 '
          '(gold-independent); see record JSON for full CP intervals.']
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
