"""Gate 3-B.4 final assembly (offline, $0):

  * aggregates every g3b4 audit JSON into g3b4_report.json;
  * writes a human-readable g3b4_report.md;
  * writes a per-issue audit table (JSON + Markdown);
  * writes the G3-B.4 result-freeze manifest pinning every g3b4 artifact and
    the frozen G3-B.3 parent hashes it depends on.

No model call, no issue added, no gold changed, no git commit.
"""
from __future__ import annotations

import json
from pathlib import Path

from evidence import g3b4_common as C

A = C.OUT_AUDIT_DIR
B = C.OUT_BLIND_DIR
G3B4 = C.G3B4


def load(name, folder=A):
    return json.loads((folder / name).read_text(encoding='utf-8'))


def vmap(path):
    return {(r['instance_id'], r['condition']): r['parsed']
            for r in C.read_jsonl(path)}


def main():
    integrity = load('g3b4_integrity_verification.json')
    recompute = load('g3b4_deepseek_recompute.json')
    strict = load('g3b4_gpt_strict_audit.json')
    t2d = load('g3b4_t2d_vs_strict.json')
    focal13974 = load('g3b4_sympy_13974_audit.json')
    focal_gpt = load('g3b4_gpt_focal_families.json')
    firstrun = load('g3b4_first_run_timeline.json')
    planning = load('g3b4_planning_and_revisions.json')
    blind = load('g3b4_blind_coding_results.json', folder=B)

    # ---- per-issue master table -----------------------------------------
    ds_b, ds_b3 = vmap(C.G3B_LIVE_DEEPSEEK), vmap(C.G3B3_LIVE_DEEPSEEK)
    gp_b, gp_b3 = vmap(C.G3B_LIVE_GPT), vmap(C.G3B3_LIVE_GPT)
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    oracle = {i['issue']: i['oracle_gold'] for i in pe['issues']}
    strict_by = {p['issue']: p for p in strict['per_issue']}

    table = []
    for iid in [f'sympy__sympy-{x}' for x in
                ('13615', '13974', '15349', '17318', '17630', '19783',
                 '20590', '21847', '24213', '24443')]:
        short = iid.split('-')[-1]
        sp = strict_by[short]
        row = {
            'issue': short,
            'oracle_gold_PROVISIONAL': oracle[iid],
            'deepseek': {c: {'g3b': ds_b[(iid, c)],
                             'g3b3': ds_b3[(iid, c)]}
                         for c in C.CONDITIONS},
            'gpt': {c: {'g3b': gp_b[(iid, c)], 'g3b3': gp_b3[(iid, c)]}
                    for c in C.CONDITIONS},
            'gpt_T3D_Strict_audit': {
                'final_verdict': sp['final_verdict'],
                'error_family': sp['error_family'],
                'acceptance_verdict_reachable':
                    sp['true_acceptance_verdict_reachable_under_strict'],
                'nondecisive_upgraded_to_sufficient':
                    sp['nondecisive_evidence_upgraded_to_sufficient'],
                'artifact_fetched_saw_baseline_map': any(
                    t['tool'] == 'get_test_artifact'
                    for t in sp['all_tool_requests_and_responses']),
                'primary_blind_code': next(
                    (j['blind_primary_code']
                     for j in blind['joined_results']
                     if j['issue'] == short), None)},
            'special_focus': {
                'is_DeepSeek_residual_overabstention_13974': short == '13974',
                'is_GPT_false_accept_family_F1_17318': short == '17318',
                'is_GPT_reject_to_need_family_F2_17630': short == '17630'}}
        table.append(row)
    table_doc = {
        'document': 'Gate 3-B.4 per-issue audit master table',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'gold_authority': C.GOLD_AUTHORITY,
        'columns': 'oracle gold (PROVISIONAL n=1 annotator2 NOT_OBTAINED); '
                   'DeepSeek and GPT verdicts per condition for G3-B and '
                   'G3-B.3; GPT T3D-Strict audit fields; blind primary code; '
                   'special-focus flags',
        'rows': table}
    (A / 'g3b4_per_issue_audit_table.json').write_bytes(
        C.canonical_bytes(table_doc))

    # ---- report json ------------------------------------------------------
    report = {
        'document': 'GroundedReview Gate 3-B.4 zero-API strict audit report',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'budget_usd': 0,
        'api_calls_made_by_this_audit': 0,
        'issues_added': 0, 'gold_changed': False, 'git_commits_made': 0,
        'gold_authority': C.GOLD_AUTHORITY,
        'headline': {
            'integrity': '100/100 real rows, raw responses and live traces '
                         're-verified against the frozen pins; raw-first '
                         'persistence; 208 real model calls; retries/errors/'
                         'resume-skips all 0; mock and live fully isolated; '
                         'analyser post-collected; prompt/protocol '
                         'fingerprints match the pre-paid freeze',
            'total_live_spend_usd_guard_basis': 0.303539,
            'total_live_spend_usd_rows_rounded': 0.303537,
            'spend_note': '~1e-6 gap is rounding convention only; this audit '
                          'itself spent $0',
            'deepseek_recompute': 'need-any 9/10 (G3-B) -> 1/10 (G3-B.3); '
                '8 need->non-need, 0 reverse; residual = SymPy-13974 only; '
                'cluster bootstrap 95% CI paired difference 0.5-1.0',
            'gpt_strict': '7 unsupported ACCEPT, 0 unsupported REJECT, 3 '
                          'correct NEED; all 7 structurally upgrade non-'
                          'decisive diagnostic evidence to sufficient '
                          'acceptance',
            'blind_coding': 'single AI rule-based coder (no independent human'
                            '/review): all 7 primary code = C3 absence-of-'
                            'failure-as-evidence, co-firing C1+C2+C5, C4 never',
            'non_interference': 'tier-1 post-patch/gold masking 61/61 clean; '
                'one tier-2 minimisation gap (pre-patch all-PASSED '
                'pass_to_pass_baseline map survives projection), present for '
                '10/10 issues but seen by none of the 7 error cells and '
                'unable to reconstruct gold; fix required before Gate 3-C',
            'mechanism_status': 'active-evidence-induced over-commitment is a'
                                ' NEW CANDIDATE mechanism, associational and '
                                'NOT proven (freshness/trust changed with '
                                'activeness)',
            'first_run': 'CompositeGuard.check returned None -> float(None) '
                         'failed pre-network on the first live attempt, $0, '
                         'repaired (return bound), $0 products discarded, '
                         'freeze regenerated; final 100/100 is post-repair'},
        'task_index': {
            'task1_result_freeze_and_protocol': 'g3b4_integrity_verification.json',
            'task2_deepseek_recompute': 'g3b4_deepseek_recompute.json',
            'task3_6_gpt_strict_and_noninterference':
                'g3b4_gpt_strict_audit.json',
            'task4_blind_coding':
                '../blind_coding/g3b4_blind_coding_results.json',
            'task5_t2d_vs_strict': 'g3b4_t2d_vs_strict.json',
            'task7_sympy_13974': 'g3b4_sympy_13974_audit.json',
            'task8_gpt_focal_families': 'g3b4_gpt_focal_families.json',
            'task9_first_run_timeline': 'g3b4_first_run_timeline.json',
            'task11_12_13_planning_and_revisions':
                'g3b4_planning_and_revisions.json',
            'per_issue_audit_table': 'g3b4_per_issue_audit_table.json'},
        'artifacts': {
            'integrity': integrity['document'],
            'recompute_headline': recompute.get('headline'),
            'strict_headline': strict['headline'],
            't2d_headline': t2d['headline'],
            'classification_13974': focal13974['classification']['answer'],
            'gpt_f1_17318': focal_gpt['family_F1_17318_T2A']['error_mechanism'],
            'gpt_f2_17630': focal_gpt['family_F2_17630_T3A']['error_mechanism'],
            'blind_independence': blind['coder_independence'],
            'gate3c_not_executed': planning['gate3c_not_executed']},
        'stop_and_await_approval': True}
    C.OUT_REPORT.write_bytes(C.canonical_bytes(report))

    # ---- markdown ---------------------------------------------------------
    md = _render_markdown(table, integrity, recompute, strict, t2d,
                          focal13974, focal_gpt, firstrun, blind, planning)
    C.OUT_REPORT_MD.write_text(md, encoding='utf-8')

    # ---- result-freeze manifest ------------------------------------------
    _write_freeze()

    print('report ->', C.OUT_REPORT.relative_to(C.HERE))
    print('md     ->', C.OUT_REPORT_MD.relative_to(C.HERE))
    print('table  ->', (A / 'g3b4_per_issue_audit_table.json')
          .relative_to(C.HERE))
    print('freeze ->', C.OUT_FREEZE.relative_to(C.HERE))


def _md_table(table):
    hdr = ('| issue | gold* | DS T2A g3b/g3b3 | DS T3D-Esc g3b/g3b3 | '
           'DS T3A g3b/g3b3 | GPT Strict g3b/g3b3 | GPT Strict family | '
           'blind | focus |\n')
    sep = '|' + '---|' * 9 + '\n'
    lines = [hdr, sep]
    for r in table:
        d, g = r['deepseek'], r['gpt']
        s = r['gpt_T3D_Strict_audit']
        focus = []
        sf = r['special_focus']
        if sf['is_DeepSeek_residual_overabstention_13974']:
            focus.append('DS residual')
        if sf['is_GPT_false_accept_family_F1_17318']:
            focus.append('F1 false-accept')
        if sf['is_GPT_reject_to_need_family_F2_17630']:
            focus.append('F2 reject->need')
        fam = s['error_family'].replace('UNSUPPORTED_ACCEPT', 'unsup ACCEPT')
        fam = fam.replace('CORRECT_ABSTENTION', 'correct NEED')
        blind = (s['primary_blind_code'] or '').split('_')[0] or '-'
        lines.append(
            f"| {r['issue']} | {r['oracle_gold_PROVISIONAL']} | "
            f"{d['T2A-T']['g3b'][:4]}/{d['T2A-T']['g3b3'][:4]} | "
            f"{d['T3D-Escalate']['g3b'][:4]}/{d['T3D-Escalate']['g3b3'][:4]} | "
            f"{d['T3A-T']['g3b'][:4]}/{d['T3A-T']['g3b3'][:4]} | "
            f"{g['T3D-Strict']['g3b'][:4]}/{g['T3D-Strict']['g3b3'][:4]}"
            f"{'(A)' if s['final_verdict']=='ACCEPT' else ''} | "
            f"{fam} | {blind} | {', '.join(focus) or '-'} |\n")
    lines.append('\n\\* gold is PROVISIONAL: single annotator, n=1, '
                 'annotator2 NOT_OBTAINED. Verdicts abbreviated '
                 '(ACCE/REJE/NEED).\n')
    return ''.join(lines)


def _render_markdown(table, integrity, recompute, strict, t2d, f13974,
                     fgpt, firstrun, blind, planning):
    L = []
    w = L.append
    w('# GroundedReview — Gate 3-B.4 zero-API strict audit\n\n')
    w(f"audit version: `{C.G3B4_AUDIT_VERSION}`  \n")
    w('budget: **$0** · model calls by this audit: **0** · issues added: 0 · '
      'gold changed: **no** · git commits: **0**\n\n')
    w('> Gold is **PROVISIONAL** throughout: one annotator, n=1, '
      '`annotator2 = NOT_OBTAINED`. AI self-review is never independent human'
      ' arbitration. Cross-version contrasts are **ASSOCIATIONAL**.\n\n')

    w('## 1. Result integrity (tasks 1 & 10)\n')
    w('100/100 real cells (2 models x 10 issues x 5 conditions) re-verified '
      'against the frozen result pins; all 100 raw responses and 100 live '
      'traces match; raw-first persistence holds; **208 real model calls** '
      '(DeepSeek 114, GPT 94); retries = errors = resume-skips = 0; wire '
      'shows no fallback; served model ids match; mock run ($0) and live run '
      'are fully isolated; the analyser/report are post-collected and their '
      'hashes match the post-collection freeze; prompt/protocol fingerprints '
      'match the pre-paid freeze. Live spend: guard-accumulated '
      '**$0.303539** (DeepSeek 0.189045 / GPT 0.114494); row-rounded sum '
      '$0.303537 (the ~1e-6 gap is rounding only).\n\n')

    w('## 2. DeepSeek 9/10 -> 1/10 independent recomputation (task 2)\n')
    h = recompute.get('headline', {})
    w('Independent third implementation (own Clopper-Pearson bisection and '
      'issue-cluster bootstrap, seed 417313, B=10000): need-any '
      f"**{h.get('g3b_need_any')} -> {h.get('g3b3_need_any')}**; "
      '8 need->non-need reversals, 0 reverse; the single residual is '
      '**SymPy-13974**. CP95 need-any intervals: G3-B (0.555, 0.997), '
      'G3-B.3 (0.003, 0.445); paired-difference cluster bootstrap 95% CI '
      '**0.5-1.0**. Full per-condition transition matrices are in '
      '`g3b4_deepseek_recompute.json`.\n\n')

    w('## 3. GPT T3D-Strict per-issue audit (task 3)\n')
    w('Condition gold is NEED_EVIDENCE for all 10 cells. Result: **7 '
      'unsupported ACCEPT** (13615, 13974, 15349, 17318, 17630, 21847, '
      '24443), **0 unsupported REJECT**, **3 correct NEED** (19783, 20590, '
      '24213). ACCEPT and REJECT error families are counted separately — '
      'nothing is auto-bucketed as unsupported acceptance. Under strict the '
      'post-patch acceptance verdict is unreachable (no f2p/p2p log '
      'granted; consistency adjudicates symptom only); all 7 ACCEPTs '
      'therefore **structurally upgrade non-decisive evidence** '
      '(linkage=true + fresh=true + coverage-complete + symptom-gone) into '
      'sufficient acceptance. Full gold/final verdict/reason/every tool '
      'request-and-response is in `g3b4_gpt_strict_audit.json`.\n\n')

    w('## 4. Partially-blinded reason coding (task 4)\n')
    w('Codebook frozen **before** coding '
      f"(`blind_coding/g3b4_blind_codebook.json`, sha "
      f"{blind['codebook_sha256'][:16]}…); masked packets D01-D07 (seed "
      f"{blind['blinding']['seed']}), coded before unblinding. This is a "
      '**single AI, rule-based coder with NO independent human coder and NO '
      'independent review** — it is not independent arbitration. All 7 units '
      'received primary code **C3** (absence-of-failure-evidence treated as '
      'evidence of absence) and all co-fired C1 (symptom resolution) + C2 '
      '(coverage completeness) + C5 (provenance/freshness); **C4 never '
      'fired** — the model never acknowledged the withholding before '
      'accepting. Blind is partial: symptom prose can identify an issue.\n\n')

    w('## 5. T2D vs Strict (task 5)\n')
    w('Both models abstain 10/10 on static **T2D-T** in both gates. '
      'DeepSeek Strict abstains 10/10 in both gates (it fetched the tier-D '
      'artifact in 8/10 G3-B.3 cells and still abstained). GPT Strict moved '
      '10/10 abstain (G3-B) -> 3/10 (G3-B.3), committing on the same 7 '
      'issues, none of which fetched the artifact. This supports — but does '
      'not prove — **active-evidence-induced over-commitment**; the '
      'cross-version contrast is confounded because freshness and trust '
      'rules changed together with activeness.\n\n')

    w('## 6. Non-interference masking (task 6)\n')
    ni = strict['non_interference_scan']
    w(f"Tier-1 scan (real post-patch f2p/p2p verdict, hidden gold, "
      f"acceptance digests, reconstructing keys): **{ni['surfaces_tier1_clean']}"
      f"/{ni['surfaces_scanned']} surfaces clean**. One **tier-2 "
      'minimisation gap**: the *pre-patch* base-commit '
      '`pass_to_pass_baseline` per-test map survives the tier-D projection '
      f"({ni['tier2_baseline_minimization_gap']['n_issues_field_present']}/10"
      ' issues carry it, all-PASSED with 0 FAILED). It cannot reconstruct '
      'gold (the post-patch P2P map is removed; zero ACCEPT/REJECT '
      'discrimination), is reachable only via an explicit artifact fetch, '
      'was seen by **none** of the 7 error cells (the one GPT cell that saw '
      'it, 20590, abstained; DeepSeek saw it in 8 cells and abstained 10/10)'
      ', and has no causal link to the over-commitments. It must be stripped'
      ' (add the field to `views._ACCEPTANCE_RECORD_FIELDS`) before Gate '
      '3-C; frozen G3-B.3 code is not modified here.\n\n')

    w('## 7. SymPy-13974 dedicated audit (task 7)\n')
    w('DeepSeek NEED under T2A and T3D-Escalate but ACCEPT under T3A; '
      'Strict correctly NEED. Fact-checking against the frozen store: the '
      f"declared F2P test is **{f13974['declared_gold_test_sets']['FAIL_TO_PASS_declared']}**"
      ' and it **is present and PASSED**; the test DeepSeek believed missing '
      '(`test_tensor_product_power`) is a test the candidate patch itself '
      'adds, not a maintainer-declared test. f2p and p2p post-patch logs are'
      ' byte-identical (one combined test-file run) but the baseline differs'
      ' — so the model\u2019s "all three logs identical / declared acceptance'
      ' test absent" claims are wrong. Classification: **residual model '
      'evidence-interpretation / policy error (over-abstention), n=1**, not '
      'a legitimate evidential-standard difference and not a new protocol '
      'inconsistency. The identical-file presentation is a hardening '
      'candidate.\n\n')

    w('## 8. GPT focal error families (task 8, kept separate)\n')
    w('- **Family F1 — SymPy-17318 / T2A false ACCEPT** (evidence-'
      'verification failure): the declared F2P `test_issue_12420` actually '
      'FAILED (`assert [4 + I, 0, 1] == []`), yet GPT accepted from the '
      'static tier-A surface in both G3-B and G3-B.3; the active T3A control'
      ' on the same issue correctly REJECTed.\n')
    w('- **Family F2 — SymPy-17630 / T3A REJECT -> NEED**: GPT saw the '
      'failed declared F2P `test_zero_matrix_add` (other FAILED tokens are '
      'xfail markers, p2p regressed/bad ids empty) but judged it "unrelated '
      'to the patch" and abstained instead of REJECT — a decision-policy '
      'over-abstention that relitigates declared-test relevance.\n')
    w('These are opposite error directions and are not pooled. The '
      'independent-REJECT set is only n=3, so report cases, not a rate.\n\n')

    w('## 9. First-run failure and repair timeline (task 9)\n')
    w('`CompositeGuard.check` ended without a return, giving `None`; the '
      'runner then ran `float(None)` at g3b3_run.py L251, **before** '
      '`driver.chat.completions.create` at L270, so the first live attempt '
      'raised before any HTTP request — **zero API spend**. The mock gate '
      'had passed because the mock path skips the guard. Repair: added '
      '`return bound` (current L148-153); the $0 error products were '
      'discarded; the executed freeze + preflight were regenerated; the '
      'corrected run produced the final 100/100 (0 error rows, no on-disk '
      'residue; run audit new=50/model, skipped=0). The live-gate artifact '
      '(mtime 02:04) is the pre-paid, zero-API local g3b2 HTTP integration '
      'gate, which explains its earlier timestamp. Deleted $0 products '
      'cannot now be hashed; this is disclosed rather than presenting only '
      'the final 100/100.\n\n')

    w('## Per-issue audit table\n')
    w(_md_table(table))
    w('\n')

    w('## 11. Second independent annotator plan (task 11)\n')
    w('See `g3b4_planning_and_revisions.json` -> `task11_second_annotator_'
      'plan`: a human annotator2 blind to all model output and prior labels, '
      'randomised sealed packets, a third senior human arbiter for any '
      'ACCEPT/REJECT disagreement (never an LLM or the pipeline author), and '
      'recomputation of every rate under annotator1 / annotator2 / '
      'adjudicated labels with leave-one-issue-out sensitivity. Proposed '
      'only; not executed.\n\n')

    w('## 12. Revised Gate 3-C design (task 12) — NOT executed\n')
    w('Priority 1 is expanding independent REJECT issues (target >=20 in '
      'total) to enable a false-accept rate; priority 2 is a genuinely '
      'restricted-evidence stratum kept separate from sufficient-evidence '
      'trials. An activeness-only controlled arm (freshness/trust held '
      'fixed) is specified to identify the candidate over-commitment '
      'mechanism. Primary endpoint, paired issue-clustered analysis, sample '
      'size/Wilson-width rationale, hard pre-call budget caps and explicit '
      'stopping rules are pre-registered. Planning uses the observed mean '
      f"${planning['planning_cost_inputs']['observed_mean_per_live_cell_usd']}"
      '/live cell. **No expansion is run in Gate 3-B.4; budget remains $0.**\n\n')

    w('## 13. Paper Results / Discussion revisions (task 13)\n')
    for item in planning['task13_paper_revisions']['results_revisions']:
        w(f"- **{item['claim']}** — {item['revised_wording']}\n")
    w('\nDiscussion additions and the explicit "claims not to make" list are '
      'in `g3b4_planning_and_revisions.json`.\n\n')

    w('---\n**Stopping here as instructed. Gate 3-C expansion, Gemini, R2 '
      'and any new paid-model experiment remain un-approved and un-executed; '
      'awaiting the next written approval.**\n')
    return ''.join(L)


def _write_freeze():
    root = C.G3B4
    files = []
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name != 'g3b4_result_freeze_manifest.json':
            files.append({'relpath': str(p.relative_to(root)).replace('\\', '/'),
                          'bytes': p.stat().st_size,
                          'sha256': C.sha256_file(p)})
    digest = C.canonical_bytes(
        {'files': sorted(files, key=lambda f: f['relpath'])})
    manifest = {
        'document': 'GroundedReview Gate 3-B.4 result-freeze manifest',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'budget_usd': 0,
        'api_calls_made_by_this_audit': 0,
        'issues_added': 0,
        'gold_changed': False,
        'git_commits_made': 0,
        'parent_pins': C.verify_g3b3_parent_pins()
        if hasattr(C, 'verify_g3b3_parent_pins') else None,
        'n_files': len(files),
        'files': files,
        'files_canonical_sha256': C.sha256_bytes(digest),
        'gold_authority': C.GOLD_AUTHORITY}
    C.OUT_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    C.OUT_FREEZE.write_bytes(C.canonical_bytes(manifest))


if __name__ == '__main__':
    main()
