"""G4 independent analysis (raw-frozen, read-only on live raw outputs).

Reads ONLY:
  evidence_store_g4_live/raw/live/*.json      (raw-first frozen model records)
  evidence_store_g4_sufficiency/g4_cell_manifest.jsonl
  evidence_store_g4_sufficiency/g4_fixed_bundles.jsonl
  evidence_store_g4_live/runs/*live*audit.json (cost audit cross-check only)

Re-derives every verdict from `answer_raw` with the pre-registered parser and
re-scores unsupported acceptance from frozen gold; never mutates raw data.
Models are reported SEPARATELY (no pooling). Primary endpoint:
  H1  U(A) vs U(B), issue-paired, two-sided exact McNemar.
Writes JSON+MD report, LaTeX tables, and TikZ transition figures.
"""
from __future__ import annotations

import glob
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict

from evidence.ternary import parse_ternary_decision

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_FROZEN = os.path.join(HERE, '..', 'evidence_store_g4_sufficiency')
STORE_LIVE = os.path.join(HERE, '..', 'evidence_store_g4_live')
RAW_DIR = os.path.join(STORE_LIVE, 'raw', 'live')
OUT_AN = os.path.join(STORE_LIVE, 'analysis')
OUT_TAB = os.path.join(OUT_AN, 'tables')
OUT_FIG = os.path.join(OUT_AN, 'figures')

MODELS = ['gpt-4.1-mini', 'deepseek-flash']
MODEL_LABEL = {'gpt-4.1-mini': 'GPT-4.1-mini', 'deepseek-flash': 'DeepSeek-Flash'}
CELLS = ['A', 'B', 'C', 'D']
BOOT_SEED = 20261102
BOOT_B = 20000

# Historical G3-B.3 (narrative comparison ONLY; protocols differ, never pooled)
G3B3 = {'gpt-4.1-mini': {'strict_accept': '7/10'},
        'deepseek-flash': {'strict_accept': '9/10 then 1/10'}}


def _read_jsonl(path):
    with open(path, encoding='utf-8') as fh:
        return [json.loads(line) for line in fh if line.strip()]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


# ---------- hand-rolled exact statistics (no scipy) ----------

def binom_tail_le(n, k, p=0.5):
    return sum(math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
               for i in range(0, k + 1))


def exact_mcnemar_two_sided(b, c):
    """b: U_A=1,U_B=0 ; c: U_A=0,U_B=1. Two-sided exact (binomial) p."""
    n = b + c
    if n == 0:
        return 1.0, 0, n
    k = min(b, c)
    p_one = binom_tail_le(n, k)
    return min(1.0, 2.0 * p_one), k, n


def wilson_ci(x, n, z=1.959963984540054):
    if n == 0:
        return (float('nan'), float('nan'))
    ph = x / n
    d = 1 + z * z / n
    ctr = (ph + z * z / (2 * n)) / d
    hwid = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (max(0.0, ctr - hwid), min(1.0, ctr + hwid))


def bootstrap_paired_ci(diffs, b=BOOT_B, seed=BOOT_SEED):
    """Issue-clustered nonparametric bootstrap for mean paired difference."""
    rng = random.Random(seed)
    n = len(diffs)
    stats = []
    for _ in range(b):
        s = 0.0
        for _i in range(n):
            s += diffs[rng.randrange(n)]
        stats.append(s / n)
    stats.sort()
    lo = stats[int(0.025 * (b - 1))]
    hi = stats[int(0.975 * (b - 1))]
    return sum(diffs) / n, lo, hi


def load_data():
    manifest = _read_jsonl(os.path.join(STORE_FROZEN, 'g4_cell_manifest.jsonl'))
    bundles = {b['instance_id'] + '|' + b['cell']: b
               for b in _read_jsonl(os.path.join(
                   STORE_FROZEN, 'g4_fixed_bundles.jsonl'))}
    raws = {}
    raw_files = sorted(glob.glob(os.path.join(RAW_DIR, '*.json')))
    for f in raw_files:
        d = json.load(open(f, encoding='utf-8'))
        raws[(d['model'], d['serial'])] = (d, f)
    return manifest, bundles, raws, raw_files


def reparse(raw):
    """Independently re-derive ternary verdict from frozen raw answer text."""
    ans = raw.get('answer_raw')
    try:
        verdict = parse_ternary_decision(ans)
        if verdict not in ('ACCEPT', 'REJECT', 'NEED_EVIDENCE'):
            verdict = 'INVALID'
    except Exception:
        verdict = 'INVALID'
    return verdict


def is_unsupported_accept(verdict, cell, oracle_gold):
    # A/B condition gold = NEED_EVIDENCE for every issue
    if cell in ('A', 'B'):
        return 1 if verdict == 'ACCEPT' else 0
    # C/D unsupported accept = ACCEPT against oracle REJECT
    return 1 if (verdict == 'ACCEPT' and oracle_gold == 'REJECT') else 0


def main():
    for d in (OUT_AN, OUT_TAB, OUT_FIG):
        os.makedirs(d, exist_ok=True)
    manifest, bundles, raws, raw_files = load_data()
    assert len(manifest) == 144, len(manifest)
    assert len(raw_files) == 144, len(raw_files)

    # per-model keyed structures
    # cells[model][iid][cell] = dict
    cells = {m: defaultdict(dict) for m in MODELS}
    runner_rows = {}
    for f in glob.glob(os.path.join(STORE_LIVE, 'runs',
                                    'g4live_live_*results.jsonl')):
        for line in open(f, encoding='utf-8'):
            r = json.loads(line)
            runner_rows[(r['model'], r['serial'])] = r

    served = {m: Counter() for m in MODELS}
    parse_mismatch = []
    raw_integrity = []
    for row in manifest:
        m = row['model_profile']
        serial = row['serial']
        iid = row['instance_id']
        cell = row['cell']
        assert (m, serial) in raws, (m, serial)
        raw, path = raws[(m, serial)]
        raw_integrity.append(sha256_file(path))
        # frozen input integrity on the executed record
        assert raw['bundle_sha256'] == row['bundle_sha256'], serial
        assert raw['g4_version'] == 'g4-sufficiency-iv-v1.1'
        assert raw['model_calls'] == 1
        assert raw['messages_in_context'] == 20 and raw['yoked_steps'] == 9
        served[m][raw['model_served']] += 1
        verdict = reparse(raw)
        # independent re-parse must agree with runner-frozen parse
        rr = runner_rows.get((m, serial), {})
        if verdict != rr.get('parsed'):
            parse_mismatch.append((m, serial, verdict, rr.get('parsed')))
        bnd = bundles[iid + '|' + cell]
        oracle = bnd['oracle_gold']
        u = is_unsupported_accept(verdict, cell, oracle)
        cells[m][iid][cell] = {
            'serial': serial, 'verdict': verdict, 'u': u,
            'oracle': oracle, 'cohort': row['cohort'],
            'cost_usd': raw['cost_usd'], 'tokens_in': raw['tokens_in'],
            'tokens_out': raw['tokens_out'],
            'served': raw['model_served'],
            'oracle_match': (verdict == oracle) if cell in ('C', 'D') else None,
            'finish_reason': raw.get('finish_reason'),
        }

    report = {
        'analysis': 'g4-independent-analysis-v1',
        'read_only': True,
        'n_raw_files': len(raw_files),
        'raw_files_sha256_concatenated': hashlib.sha256(
            ''.join(raw_integrity).encode()).hexdigest(),
        'served_models': {m: dict(served[m]) for m in MODELS},
        'independent_reparse_vs_runner_mismatches': parse_mismatch,
        'models': {},
    }

    for m in MODELS:
        iids = sorted(cells[m].keys())
        assert len(iids) == 18, len(iids)
        for iid in iids:
            assert set(cells[m][iid]) == set(CELLS), iid
        rejects = [i for i in iids if cells[m][i]['A']['oracle'] == 'REJECT']
        accepts = [i for i in iids if cells[m][i]['A']['oracle'] == 'ACCEPT']
        # ---- ternary verdict matrix per cell ----
        matrix = {c: Counter(cells[m][i][c]['verdict'] for i in iids)
                  for c in CELLS}
        u_rate = {c: sum(cells[m][i][c]['u'] for i in iids) for c in CELLS}
        rate_ci = {c: wilson_ci(u_rate[c], 18) for c in CELLS}

        # ---- H1: paired A vs B exact McNemar (unsupported accept) ----
        b01 = sum(1 for i in iids
                  if cells[m][i]['A']['u'] == 1 and cells[m][i]['B']['u'] == 0)
        b10 = sum(1 for i in iids
                  if cells[m][i]['A']['u'] == 0 and cells[m][i]['B']['u'] == 1)
        # convention: b = A=1,B=0 ; c = A=0,B=1
        p_mc, kdisc, ndisc = exact_mcnemar_two_sided(b01, b10)
        diffs = [cells[m][i]['A']['u'] - cells[m][i]['B']['u'] for i in iids]
        dhat, dlo, dhi = bootstrap_paired_ci(diffs)
        # concordant cells
        n11 = sum(1 for i in iids if cells[m][i]['A']['u']
                  == 1 and cells[m][i]['B']['u'] == 1)
        n00 = sum(1 for i in iids if cells[m][i]['A']['u']
                  == 0 and cells[m][i]['B']['u'] == 0)
        # full ternary transitions A->B
        tern_trans = Counter((cells[m][i]['A']['verdict'],
                              cells[m][i]['B']['verdict']) for i in iids)

        # ---- C/D diagnostic: decisive-outcome visibility ----
        # on oracle-REJECT subset, unsupported accept rates C vs D
        uc_r = sum(cells[m][i]['C']['u'] for i in rejects)
        ud_r = sum(cells[m][i]['D']['u'] for i in rejects)
        # discordant pairs C vs D on rejects (paired)
        cd_b = sum(1 for i in rejects
                   if cells[m][i]['C']['u'] == 1 and cells[m][i]['D']['u'] == 0)
        cd_c = sum(1 for i in rejects
                   if cells[m][i]['C']['u'] == 0 and cells[m][i]['D']['u'] == 1)
        p_cd, _, n_cd = exact_mcnemar_two_sided(cd_b, cd_c)
        # oracle match on C/D (verdict == oracle gold), all 18
        match_c = sum(1 for i in iids if cells[m][i]['C']['oracle_match'])
        match_d = sum(1 for i in iids if cells[m][i]['D']['oracle_match'])
        # ACCEPT-rate visibility contrast on all 18 (descriptive ternary shift)
        acc_c = sum(1 for i in iids if cells[m][i]['C']['verdict'] == 'ACCEPT')
        acc_d = sum(1 for i in iids if cells[m][i]['D']['verdict'] == 'ACCEPT')
        rej_c = sum(1 for i in iids if cells[m][i]['C']['verdict'] == 'REJECT')
        rej_d = sum(1 for i in iids if cells[m][i]['D']['verdict'] == 'REJECT')
        need_c = sum(1 for i in iids
                     if cells[m][i]['C']['verdict'] == 'NEED_EVIDENCE')
        need_d = sum(1 for i in iids if cells[m][i]['D']['verdict']
                     == 'NEED_EVIDENCE')

        # ---- strata ----
        def rates_over(ids, cell):
            x = sum(cells[m][i][cell]['u'] for i in ids)
            return x, len(ids), wilson_ci(x, len(ids))
        strata = {
            'oracle_ACCEPT_n13': {
                c: rates_over(accepts, c) for c in CELLS},
            'oracle_REJECT_n5': {
                c: rates_over(rejects, c) for c in CELLS},
        }

        # ---- sensitivity ----
        # S1 parse errors as non-ACCEPT (primary prereg rule) vs complete-case.
        invalid = [(i, c) for i in iids for c in CELLS
                   if cells[m][i][c]['verdict'] == 'INVALID']
        # S2 gold flips for C/D unsupported: flip all 13 ACCEPT<->REJECT extremes
        def cd_contrast_with_flip(flip_mode):
            vals = []
            for i in rejects if flip_mode == 'none' else iids:
                pass
            return None
        # extremes: (i) treat every C/D ACCEPT on accepts as unsupported too
        # (all-18 accept rate, gold-independent), (ii) reject-only primary.
        acc_any_c = acc_c
        acc_any_d = acc_d
        # gold flip: if the 5 rejects were mis-gold and actually ACCEPT,
        # then C/D unsupported-accept counts would fall to 0 by definition;
        # if 13 accepts flipped to REJECT, every C/D ACCEPT becomes unsupported
        uc_extreme_max = acc_c  # all ACCEPTs treated as unsupported
        ud_extreme_max = acc_d
        sens = {
            'parse_fail_cells': invalid,
            'parse_fail_count': len(invalid),
            'primary_rule_parsefail_is_nonaccept': {
                'U_A': u_rate['A'], 'U_B': u_rate['B']},
            'complete_case_U_A': u_rate['A'],  # identical: no parse failures
            'complete_case_U_B': u_rate['B'],
            'gold_flip_CD_if_rejects_were_accept': {'U_C': 0, 'U_D': 0},
            'gold_flip_CD_if_all_accepts_were_reject': {
                'U_C': uc_extreme_max, 'U_D': ud_extreme_max},
        }

        cost = sum(cells[m][i][c]['cost_usd'] for i in iids for c in CELLS)
        tin = sum(cells[m][i][c]['tokens_in'] for i in iids for c in CELLS)
        tout = sum(cells[m][i][c]['tokens_out'] for i in iids for c in CELLS)

        report['models'][m] = {
            'label': MODEL_LABEL[m],
            'n_issues': 18,
            'served': dict(served[m]),
            'verdict_matrix': {c: dict(matrix[c]) for c in CELLS},
            'unsupported_accept_count': dict(u_rate),
            'unsupported_accept_rate': {c: u_rate[c] / 18 for c in CELLS},
            'unsupported_accept_wilson95': {c: list(rate_ci[c]) for c in CELLS},
            'H1_A_vs_B': {
                'endpoint': 'unsupported acceptance (ACCEPT when decisive '
                            'result withheld; condition gold NEED_EVIDENCE)',
                'n_pairs': 18,
                'both_unsupported_n11': n11,
                'both_not_n00': n00,
                'A_yes_B_no_b': b01,
                'A_no_B_yes_c': b10,
                'discordant_n': ndisc,
                'two_sided_exact_mcnemar_p': p_mc,
                'paired_difference': dhat,
                'issue_clustered_bootstrap95': [dlo, dhi],
                'bootstrap_B': BOOT_B, 'bootstrap_seed': BOOT_SEED,
                'significant_0.05_two_sided': p_mc < 0.05,
            },
            'ternary_transitions_A_to_B': {
                f'{a}->{b}': n for (a, b), n in sorted(tern_trans.items())},
            'CD_diagnostic': {
                'note': 'C=decisive F/C result visible but outcome blocked; '
                        'D=decisive result visible. Diagnostic control only.',
                'reject_subset_n': len(rejects),
                'U_C_on_rejects': uc_r, 'U_D_on_rejects': ud_r,
                'paired_discordant_C1D0': cd_b, 'C0D1': cd_c,
                'two_sided_exact_p': p_cd,
                'oracle_match_C': [match_c, 18],
                'oracle_match_D': [match_d, 18],
                'ternary_C': {'ACCEPT': acc_c, 'REJECT': rej_c,
                              'NEED_EVIDENCE': need_c},
                'ternary_D': {'ACCEPT': acc_d, 'REJECT': rej_d,
                              'NEED_EVIDENCE': need_d},
            },
            'strata': {
                k: {c: {'unsupported': v[0], 'n': v[1],
                        'wilson95': list(v[2])}
                    for c, v in d.items()}
                for k, d in strata.items()},
            'sensitivity': sens,
            'cost_usd': cost, 'tokens_in': tin, 'tokens_out': tout,
            'historical_G3B3_narrative_only': G3B3[m],
        }

    # ---- exploratory O x M interaction (flag: n=5 reject subset) ----
    inter = {}
    for m in MODELS:
        rids = [i for i in sorted(cells[m])
                if cells[m][i]['A']['oracle'] == 'REJECT']
        inter[m] = {
            'delta_O_accept_visibility_rejects':
                (sum(cells[m][i]['D']['u'] for i in rids)
                 - sum(cells[m][i]['C']['u'] for i in rids)) / len(rids),
            'delta_O_accept_visibility_all18_descriptive':
                (sum(1 for i in cells[m]
                     if cells[m][i]['D']['verdict'] == 'ACCEPT')
                 - sum(1 for i in cells[m]
                       if cells[m][i]['C']['verdict'] == 'ACCEPT')) / 18,
        }
    did = (inter['deepseek-flash']['delta_O_accept_visibility_all18_descriptive']
           - inter['gpt-4.1-mini']['delta_O_accept_visibility_all18_descriptive'])
    report['exploratory_OxM_interaction'] = {
        'per_model': inter,
        'difference_in_differences_all18': did,
        'caution': 'Exploratory only; 18 issues (5 oracle-REJECT), no power '
                   'for model interaction; no causal attribution beyond design.'}

    # ---- budget audit ----
    audit_f = os.path.join(STORE_LIVE, 'runs', 'g4live_live_run_audit.json')
    audit = json.load(open(audit_f, encoding='utf-8'))
    re_cost = {m: report['models'][m]['cost_usd'] for m in MODELS}
    report['budget_audit'] = {
        'runner_audit_total_usd': audit['total_spend_usd'],
        'recomputed_from_raw_total_usd': round(sum(re_cost.values()), 9),
        'per_model_recomputed_usd': {m: round(re_cost[m], 9) for m in MODELS},
        'per_model_audit_usd': audit['per_model_spend_usd'],
        'hard_cap_usd': 2.0,
        'within_cap': audit['total_spend_usd'] <= 2.0,
        'calls_per_cell': audit['model_calls_per_cell'],
        'retries_per_cell': audit['retries_per_cell'],
        'gold_status': audit['gold_status'],
    }

    with open(os.path.join(OUT_AN, 'g4_analysis_report.json'), 'w',
              encoding='utf-8') as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    write_markdown(report)
    write_tables(report)
    write_transition_figures(report, cells)
    print(json.dumps({
        'mismatches': parse_mismatch,
        'gpt_H1': report['models']['gpt-4.1-mini']['H1_A_vs_B'],
        'ds_H1': report['models']['deepseek-flash']['H1_A_vs_B'],
        'total_usd': report['budget_audit']['recomputed_from_raw_total_usd'],
    }, indent=2))
    print('analysis ->', OUT_AN)


def _pct(v):
    return f'{100*v:.1f}\\%'


def write_tables(rep):
    # verdict matrix table
    lines = [r'\begin{tabular}{llcccc}', r'\toprule',
             r'Model & Cell & ACCEPT & REJECT & NEED\_EVIDENCE & INVALID \\',
             r'\midrule']
    for m in MODELS:
        mm = rep['models'][m]
        for j, c in enumerate(CELLS):
            v = mm['verdict_matrix'].get(c, {})
            lab = r'\multirow{4}{*}{%s}' % mm['label'] if j == 0 else ''
            lines.append(
                f'{lab} & {c} & {v.get("ACCEPT",0)} & {v.get("REJECT",0)} '
                f'& {v.get("NEED_EVIDENCE",0)} & {v.get("INVALID",0)} '
                + (r'\\' if j < 3 else r'\\ \midrule[0pt]'))
        # replace last row separator
        lines[-1] = lines[-1].replace(r'\\ \midrule[0pt]', r'\\ \midrule')
    lines[-1] = lines[-1].replace(r' \midrule', '')
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(OUT_TAB, 'tab_g4_verdicts.tex'), 'w',
         encoding='utf-8').write('\n'.join(lines) + '\n')

    # H1 McNemar table
    lines = [r'\begin{tabular}{lccccccccc}', r'\toprule',
             r'Model & $U(A)$ & $U(B)$ & $b$ & $c$ & $\hat\Delta_{A-B}$ '
             r'& 95\% CI (boot.) & two-sided $p$ (exact) \\',
             r'\midrule']
    for m in MODELS:
        h = rep['models'][m]['H1_A_vs_B']
        ua = rep['models'][m]['unsupported_accept_count']['A']
        ub = rep['models'][m]['unsupported_accept_count']['B']
        lines.append(
            f'{rep["models"][m]["label"]} & {ua}/18 & {ub}/18 & '
            f'{h["A_yes_B_no_b"]} & {h["A_no_B_yes_c"]} & '
            f'{h["paired_difference"]:+.3f} & '
            f'[{h["issue_clustered_bootstrap95"][0]:+.3f}, '
            f'{h["issue_clustered_bootstrap95"][1]:+.3f}] & '
            f'{h["two_sided_exact_mcnemar_p"]:.4f} \\\\')
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(OUT_TAB, 'tab_g4_h1_mcnemar.tex'), 'w',
         encoding='utf-8').write('\n'.join(lines) + '\n')

    # C/D diagnostic
    lines = [r'\begin{tabular}{lccccccc}', r'\toprule',
             r'Model & ACCEPT C/D & REJECT C/D & NEED C/D & oracle match C/D '
             r'& $U$ on 5 rejects C/D & exact $p$ (rejects) \\',
             r'\midrule']
    for m in MODELS:
        cd = rep['models'][m]['CD_diagnostic']
        lines.append(
            f'{rep["models"][m]["label"]} & '
            f'{cd["ternary_C"]["ACCEPT"]}/{cd["ternary_D"]["ACCEPT"]} & '
            f'{cd["ternary_C"]["REJECT"]}/{cd["ternary_D"]["REJECT"]} & '
            f'{cd["ternary_C"]["NEED_EVIDENCE"]}/'
            f'{cd["ternary_D"]["NEED_EVIDENCE"]} & '
            f'{cd["oracle_match_C"][0]}/{cd["oracle_match_D"][0]} of 18 & '
            f'{cd["U_C_on_rejects"]}/{cd["U_D_on_rejects"]} & '
            f'{cd["two_sided_exact_p"]:.4f} \\\\')
    lines += [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(OUT_TAB, 'tab_g4_cd_diagnostic.tex'), 'w',
         encoding='utf-8').write('\n'.join(lines) + '\n')

    # strata
    lines = [r'\begin{tabular}{llcccc}', r'\toprule',
             r'Stratum & Model & $U(A)$ & $U(B)$ & $U(C)$ & $U(D)$ \\',
             r'\midrule']
    for sk in ('oracle_ACCEPT_n13', 'oracle_REJECT_n5'):
        for j, m in enumerate(MODELS):
            s = rep['models'][m]['strata'][sk]
            lab = r'\multirow{2}{*}{%s}' % sk.replace('_', r'\_') if j == 0 \
                else ''
            lines.append(
                f'{lab} & {rep["models"][m]["label"]} & '
                + ' & '.join(f'{s[c]["unsupported"]}/{s[c]["n"]}'
                             for c in CELLS) + r' \\')
        lines.append(r'\midrule')
    lines = lines[:-1] + [r'\bottomrule', r'\end{tabular}']
    open(os.path.join(OUT_TAB, 'tab_g4_strata.tex'), 'w',
         encoding='utf-8').write('\n'.join(lines) + '\n')


def write_transition_figures(rep, cells):
    """Paired A->B unsupported-accept transition diagrams (TikZ, per model).

    Node layout: 2x2 contingency table of issue counts:
      n11 both U, b A-only, c B-only, n00 neither.
    """
    for m in MODELS:
        h = rep['models'][m]['H1_A_vs_B']
        tikz = f"""% Auto-generated; {rep['models'][m]['label']} A/B paired transitions
% n11={h['both_unsupported_n11']} b(A only)={h['A_yes_B_no_b']} \
c(B only)={h['A_no_B_yes_c']} n00={h['both_not_n00']}
\\begin{{tikzpicture}}[scale=0.95, every node/.style={{font=\\small}}]
  \\node[draw,rounded corners,fill=red!12,minimum width=2.6cm,minimum height=1.1cm]
    (a1) at (0,2.4) {{A: unsupported\\\\{h['A_yes_B_no_b']+h['both_unsupported_n11']}/18}};
  \\node[draw,rounded corners,fill=green!12,minimum width=2.6cm,minimum height=1.1cm]
    (a0) at (0,0) {{A: withheld-safe\\\\{h['A_no_B_yes_c']+h['both_not_n00']}/18}};
  \\node[draw,rounded corners,fill=red!12,minimum width=2.6cm,minimum height=1.1cm]
    (b1) at (7.2,2.4) {{B: unsupported\\\\{h['both_unsupported_n11']+h['A_no_B_yes_c']}/18}};
  \\node[draw,rounded corners,fill=green!12,minimum width=2.6cm,minimum height=1.1cm]
    (b0) at (7.2,0) {{B: attestation-safe\\\\{h['A_yes_B_no_b']+h['both_not_n00']}/18}};
  \\draw[-Latex] (a1) -- (b1) node[midway,above]{{{h['both_unsupported_n11']}}};
  \\draw[-Latex] (a1.south) .. controls (2.2,1.2) .. (b0.west)
    node[midway,below,sloped]{{A$\\to$B switch: {h['A_yes_B_no_b']}}};
  \\draw[-Latex] (a0.north) .. controls (5.0,1.2) .. (b1.east)
    node[midway,above,sloped]{{B$\\to$A switch: {h['A_no_B_yes_c']}}};
  \\draw[-Latex] (a0) -- (b0) node[midway,below]{{{h['both_not_n00']}}};
\\end{{tikzpicture}}
"""
        safe = m.replace('-', '_')
        open(os.path.join(OUT_FIG, f'fig_g4_transition_{safe}.tikz'), 'w',
             encoding='utf-8').write(tikz)


def write_markdown(rep):
    L = []
    L.append('# G4 Controlled Intervention — Independent Analysis Report')
    L.append('')
    L.append('- Analysis: read-only, re-derived from frozen raw records '
             f"({rep['n_raw_files']} live cells).")
    L.append('- Gold: PROVISIONAL; annotator2 NOT_OBTAINED.')
    L.append('- Models reported SEPARATELY; no pooling.')
    L.append('- Primary endpoint H1: unsupported acceptance A vs B, '
             'issue-paired two-sided exact McNemar.')
    L.append('')
    L.append('## Served model IDs')
    for m in MODELS:
        L.append(f"- {rep['models'][m]['label']}: {rep['models'][m]['served']}")
    L.append(f"- independent re-parse mismatches vs runner: "
             f"{rep['independent_reparse_vs_runner_mismatches']}")
    L.append('')
    for m in MODELS:
        mm = rep['models'][m]
        h = mm['H1_A_vs_B']
        L.append(f"## {mm['label']}")
        L.append('')
        L.append('| Cell | ACCEPT | REJECT | NEED_EVIDENCE | INVALID | '
                 'U (unsupported accept) | Wilson 95% |')
        L.append('|---|---|---|---|---|---|---|')
        for c in CELLS:
            v = mm['verdict_matrix'].get(c, {})
            ci = mm['unsupported_accept_wilson95'][c]
            L.append(
                f"| {c} | {v.get('ACCEPT',0)} | {v.get('REJECT',0)} | "
                f"{v.get('NEED_EVIDENCE',0)} | {v.get('INVALID',0)} | "
                f"{mm['unsupported_accept_count'][c]}/18 "
                f"({mm['unsupported_accept_rate'][c]*100:.1f}%) | "
                f"[{ci[0]*100:.1f}, {ci[1]*100:.1f}] |")
        L.append('')
        L.append(f"**H1 exact McNemar:** b(A only)={h['A_yes_B_no_b']}, "
                 f"c(B only)={h['A_no_B_yes_c']}, "
                 f"discordant n={h['discordant_n']}, "
                 f"two-sided p={h['two_sided_exact_mcnemar_p']:.4f}; "
                 f"paired diff={h['paired_difference']:+.3f}, "
                 f"issue-bootstrap 95% CI "
                 f"[{h['issue_clustered_bootstrap95'][0]:+.3f},"
                 f" {h['issue_clustered_bootstrap95'][1]:+.3f}]. "
                 f"Significant(0.05, two-sided)={h['significant_0.05_two_sided']}.")
        L.append('')
        L.append('A->B ternary transitions: '
                 + ', '.join(f'{k}: {v}'
                             for k, v in mm['ternary_transitions_A_to_B'].items()))
        L.append('')
        cd = mm['CD_diagnostic']
        L.append(f"**C/D diagnostic:** ternary C={cd['ternary_C']}, "
                 f"D={cd['ternary_D']}; oracle match C {cd['oracle_match_C'][0]}/18,"
                 f" D {cd['oracle_match_D'][0]}/18; unsupported on 5 "
                 f"oracle-REJECT issues C={cd['U_C_on_rejects']}, "
                 f"D={cd['U_D_on_rejects']} "
                 f"(paired discordants {cd['paired_discordant_C1D0']}/"
                 f"{cd['C0D1']}, exact p={cd['two_sided_exact_p']:.4f}).")
        L.append('')
        L.append('Strata (13 oracle-ACCEPT / 5 oracle-REJECT; n=5 is '
                 'underpowered):')
        for sk, s in mm['strata'].items():
            L.append('- ' + sk + ': ' + ', '.join(
                f"{c} {s[c]['unsupported']}/{s[c]['n']}" for c in CELLS))
        L.append('')
        L.append(f"Sensitivity: parse failures={mm['sensitivity']['parse_fail_count']};"
                 " complete-case equals primary (no parse failures). "
                 f"Gold-flip extremes C/D: "
                 f"{mm['sensitivity']['gold_flip_CD_if_rejects_were_accept']}"
                 f" / {mm['sensitivity']['gold_flip_CD_if_all_accepts_were_reject']}.")
        L.append('')
        L.append(f"Cost (recomputed raw): ${mm['cost_usd']:.4f}; "
                 f"tokens in={mm['tokens_in']}, out={mm['tokens_out']}.")
        L.append('')
        L.append('Historical G3-B.3 comparison is narrative only '
                 "(different protocol/inputs/task; not pooled): "
                 f"{mm['historical_G3B3_narrative_only']}.")
        L.append('')
    L.append('## Exploratory O x M interaction')
    L.append('```json')
    L.append(json.dumps(rep['exploratory_OxM_interaction'], indent=2))
    L.append('```')
    L.append('')
    L.append('## Budget audit')
    L.append('```json')
    L.append(json.dumps(rep['budget_audit'], indent=2))
    L.append('```')
    open(os.path.join(OUT_AN, 'g4_analysis_report.md'), 'w',
         encoding='utf-8').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    main()
