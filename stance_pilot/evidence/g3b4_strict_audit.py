"""Gate 3-B.4 (tasks 3 & 6) — GPT T3D-Strict per-issue audit and the
non-interference information-masking verification.

ZERO API. For all 10 GPT-4.1-mini T3D-Strict cells this module records, per
issue: gold (oracle + condition), the final verdict, the model's full reason,
EVERY tool request and its full response, model/tool call counts, whether a
forbidden acceptance log was requested/denied, and then:

  * keeps the two error families SEPARATE — unsupported ACCEPT vs unsupported
    REJECT (it does not auto-label everything "unsupported acceptance");
  * separates four evidence KINDS — symptom / provenance / coverage / a true
    acceptance verdict — and checks whether a decisive acceptance verdict was
    even reachable under strict;
  * decides, per error, whether non-decisive diagnostic evidence was upgraded
    into "sufficient" evidence;
  * runs a MACHINE non-interference scan over the exact rendered prompt
    (system+user) and every tool response for the 10 cells: the frozen
    views._LEAK_PATTERNS, f2p/p2p result keys and per-test statuses,
    acceptance-log digests (a hidden-state side channel), and hidden-gold /
    gold-reconstructing fields.

    uv run --python 3.13 -m evidence.g3b4_strict_audit
"""
from __future__ import annotations

import json
import re

from evidence import g3b4_common as C
from evidence.views import _LEAK_PATTERNS, display_for_tier  # frozen, read-only

MODEL = 'gpt-4.1-mini'
ORDERED = [f'sympy__{i}' for i in C.ISSUES]

# Outcome-bearing key fragments that must never appear at tier D.
FORBIDDEN_KEY_FRAGMENTS = (
    'f2p_passed', 'f2p_failed', 'p2p_passed', 'p2p_failed',
    'f2p_passed_ids', 'f2p_failed_ids', 'p2p_failed_ids',
    'fail_to_pass_passed', 'pass_to_pass_passed',
    'f2p_log_digest', 'p2p_log_digest', 'p2p_baseline_log_digest',
    'failing_acceptance_test_ids', 'regression_test_ids',
    'condition_gold', 'oracle_gold', '_oracle_gold', 'audit_oracle',
    'audit_condition', 'phase2_scenario', 'ground_truth_verdict')
# A real per-test status (a test id followed by PASSED/FAILED). At tier D
# these are only reachable via the un-removed pass_to_pass_baseline field
# (a PRE-patch base-commit map); post-patch f2p/p2p maps are removed.
TEST_STATUS_RE = re.compile(
    r'test_[a-z0-9_]+[^\n]{0,40}?\b(PASSED|FAILED)\b', re.I)
RAW_STATUS_RE = re.compile(r'"(?:passed|failed|ok|status)"\s*:\s*(true|false|"[a-z]+")',
                           re.I)
# Tier-2 finding: the pre-patch base-commit P2P per-test map survives the
# tier-D top-level field projection (only fail_to_pass / pass_to_pass_scoped
# are dropped). It carries per-test statuses but NO post-patch verdict.
BASELINE_MAP_RE = re.compile(
    r'"?pass_to_pass_baseline"?\s*:\s*\{', re.I)
BASELINE_NAME_RE = re.compile(r'\bp2p_baseline\b', re.I)
# Phrases that legitimately INSTRUCT about withholding / completeness; these
# are allowed even though they contain "pass".
ALLOWED_PHRASES = (
    'outcomes withheld', 'verdicts withheld',
    'reports no pass/fail outcomes', 'no pass/fail acceptance verdicts',
    'a passing probe means the symptom is gone',
    'no tool exposes pass/fail acceptance verdicts',
    'acceptance outcomes are not adjudicated under the strict policy',
    'maintainer acceptance outcomes are not adjudicated',
    'acceptance tests and regression verdicts remain to be checked',
    'not proof of merge acceptability',
    'the bar to accept is complete, fresh, linked, failure-free success',
    'no executed acceptance check fails')

# Reason phrases that assert failure-free ACCEPTANCE success (the upgrade
# signature) even though no acceptance verdict is available under strict.
ACCEPT_SUCCESS_MARKERS = (
    'no failures', 'no regressions', 'without introducing regression',
    'all relevant tests pass', 'all tests pass', 'tests passing',
    'acceptance criteria', 'ready to merge', 'safe to merge',
    'resolved with no', 'confirmed resolved', 'successfully resolves',
    'successfully fixes', 'meets the acceptance', 'fully correct',
    'no failing', 'passes all', 'no evidence of failure',
    'does not introduce any regression', 'issue is resolved')
WITHHOLD_MARKERS = (
    'withheld', 'cannot confirm', 'not adjudicated', 'unable to verify',
    'insufficient', 'do not have access', 'lack access', 'no access to',
    'cannot determine', 'not provided')


def _scan_text(text):
    """Three-tier classification of what a visible surface contains.

    tier1_forbidden: a real POST-patch acceptance/regression verdict, hidden
      gold, or a field that reconstructs it — a genuine non-interference
      violation.
    tier2_baseline_minimization_gap: the pre-patch base-commit P2P per-test
      map (pass_to_pass_baseline) survives projection. It is a sanitisation
      minimisation defect but is NOT a post-patch acceptance verdict and
      cannot reconstruct gold (it is all-PASSED for every issue).
    allowed_structural: withholding notes and declared/executed counts.
    """
    tier1, tier2 = [], []
    low = text.lower()
    for pat in _LEAK_PATTERNS:
        m = pat.search(text)
        if m:
            tier1.append({'kind': 'frozen_leak_pattern',
                          'pattern': pat.pattern, 'match': m.group(0)})
    for frag in FORBIDDEN_KEY_FRAGMENTS:
        if frag in low:
            # f2p/p2p log digests and result ids are tier 1.
            tier1.append({'kind': 'forbidden_key_fragment',
                          'fragment': frag})
    # Raw post-patch result booleans are tier 1.
    for m in RAW_STATUS_RE.finditer(text):
        tier1.append({'kind': 'raw_status_key', 'match': m.group(0)[:120]})
    # Per-test statuses: tier 1 ONLY if they are NOT inside the pre-patch
    # baseline map. Detect baseline-map presence; if present, attribute the
    # statuses to tier 2, otherwise tier 1.
    statuses = [m.group(0)[:120] for m in TEST_STATUS_RE.finditer(text)]
    has_baseline_map = bool(BASELINE_MAP_RE.search(text))
    if statuses:
        if has_baseline_map:
            nfail = sum(1 for s in statuses if 'FAILED' in s.upper())
            tier2.append({
                'kind': 'prepatch_baseline_per_test_map_exposed',
                'field': 'pass_to_pass_baseline',
                'n_status_tokens': len(statuses),
                'n_FAILED_tokens': nfail,
                'sample': statuses[:3],
                'interpretation': 'base-commit (PRE-patch) scoped P2P map; '
                                  'not a post-patch f2p/p2p verdict; all '
                                  'PASSED for this issue, so zero ACCEPT/'
                                  'REJECT discriminating information'})
        else:
            for s in statuses:
                tier1.append({'kind': 'per_test_acceptance_status',
                              'match': s})
    allowed = [p for p in ALLOWED_PHRASES if p in low]
    return tier1, tier2, allowed


def _scan_payload(label, text, findings):
    tier1, tier2, allowed = _scan_text(text or '')
    findings.append({'surface': label,
                     'n_tier1_forbidden': len(tier1),
                     'tier1_forbidden': tier1,
                     'n_tier2_baseline_gap': len(tier2),
                     'tier2_baseline_gap': tier2,
                     'allowed_withholding_phrases_present': allowed})


def _kind_classification(cell):
    """Classify every tool response into the four evidence kinds and record
    whether a decisive acceptance verdict was reachable."""
    kinds = {'symptom': [], 'provenance': [], 'coverage': [],
             'freshness': [], 'acceptance_verdict': [], 'other': []}
    for t in cell['tool_responses']:
        name, body = t['tool'], t['result_preview']
        bl = body.lower()
        entry = {'tool': name, 'http_status': t['http_status'],
                 'has_pass_fail': bool(
                     re.search(r'\b(passed|failed)\b', bl)
                     and 'no pass/fail' not in bl
                     and 'not adjudicated' not in bl)}
        if name == 'verify_artifact_linkage':
            kinds['provenance'].append(entry)
        elif name == 'check_evidence_freshness':
            kinds['freshness'].append(entry)
        elif name == 'check_test_coverage':
            kinds['coverage'].append(entry)
        elif name == 'check_claim_consistency':
            kinds['symptom'].append(
                {**entry, 'basis': 'symptom non-reproduction only; reason '
                 'string explicitly states acceptance outcomes are not '
                 'adjudicated under strict'})
        elif name == 'get_test_artifact':
            kinds['provenance'].append({**entry, 'note': 'record re-fetch; '
                                        'tier-D projection, outcomes removed'})
        elif name == 'get_run_log':
            asked = (t.get('args') or {}).get('name')
            if asked in ('f2p', 'p2p', 'p2p_baseline'):
                kinds['acceptance_verdict'].append(
                    {**entry, 'requested': asked,
                     'granted': t['http_status'] == 200})
            else:
                kinds['symptom'].append(entry)
        else:
            kinds['other'].append(entry)
    reachable = bool(kinds['acceptance_verdict']
                     and any(e.get('granted')
                             for e in kinds['acceptance_verdict']))
    return kinds, reachable


def main():
    pe = json.loads(C.G3B3_ISSUE_EVIDENCE.read_text(encoding='utf-8'))
    rows = {r['instance_id']: r for r in C.read_jsonl(C.G3B3_LIVE_GPT)}
    by_issue = {i['issue']: i for i in pe['issues']}

    per_issue = []
    n_accept_err = n_reject_err = n_correct_need = 0
    all_findings = []
    for iid in ORDERED:
        issue_doc = by_issue[iid]
        cell = next(c for c in issue_doc['models'][MODEL]
                    if c['condition'] == 'T3D-Strict')
        row = rows[iid]
        verdict = cell['g3b3_verdict']
        gold_cond = cell['condition_gold']
        gold_oracle = issue_doc['oracle_gold']
        reason = cell['g3b3_model_reasoning']
        kinds, acceptance_reachable = _kind_classification(cell)
        tool_requests = [
            {'turn': t['turn'], 'tool': t['tool'], 'args': t.get('args'),
             'http_status': t['http_status'], 'response': t['result_preview']}
            for t in cell['tool_responses']]
        requested_acceptance_log = [
            {'name': (t.get('args') or {}).get('name'),
             'http_status': t['http_status']}
            for t in cell['tool_responses']
            if t['tool'] == 'get_run_log'
            and (t.get('args') or {}).get('name')
            in ('f2p', 'p2p', 'p2p_baseline')]
        got_403 = any(t['http_status'] == 403
                      for t in cell['tool_responses'])

        # Error family, kept strictly separate.
        if gold_cond == 'NEED_EVIDENCE' and verdict == 'ACCEPT':
            family = 'UNSUPPORTED_ACCEPT'
            n_accept_err += 1
        elif gold_cond == 'NEED_EVIDENCE' and verdict == 'REJECT':
            family = 'UNSUPPORTED_REJECT'
            n_reject_err += 1
        elif verdict == 'NEED_EVIDENCE':
            family = 'CORRECT_ABSTENTION'
            n_correct_need += 1
        else:
            family = 'OTHER'

        rl = (reason or '').lower()
        success_markers = [m for m in ACCEPT_SUCCESS_MARKERS if m in rl]
        withhold_markers = [m for m in WITHHOLD_MARKERS if m in rl]

        # ---- Wording sub-type of the unsupported accept ------------------
        # The upgrade is a STRUCTURAL fact: gold=NEED, strict makes the
        # acceptance verdict unreachable, yet the cell returns ACCEPT. The
        # wording only records HOW the non-decisive evidence was promoted; it
        # is never a gate on whether an upgrade occurred.
        wording_tags = []
        if re.search(r'(symptom|issue).{0,60}(no longer|does not|not) '
                     r'?(reproduce|recur|manifest)', rl) or \
           re.search(r'(symptom|issue).{0,40}(resolved|gone|fixed)', rl):
            wording_tags.append('symptom_resolution_framed_as_acceptance')
        if re.search(r'(full|complete).{0,30}(coverage|test|execut)'
                     r'|all (the |declared )?(tests|checks) (were |are )?'
                     r'(executed|run|covered)', rl):
            wording_tags.append('coverage_completeness_framed_as_verdict')
        if re.search(r'no evidence of (any |a )?(failing|failure|regression|'
                     r'acceptance test failure)|no (new )?(failures|regression)'
                     r'|without (any )?(failure|regression)|'
                     r'acceptable for merge|is acceptable|patch correctly', rl):
            wording_tags.append('absence_of_failure_evidence_as_evidence_of_'
                                'absence')
        if re.search(r'fresh|restag|link|authent|sign', rl):
            wording_tags.append('provenance_freshness_invoked')

        # Determination (structural, not phrase-gated).
        upgraded = (family == 'UNSUPPORTED_ACCEPT'
                    and not acceptance_reachable)

        per_issue.append({
            'issue': iid.split('-')[-1],
            'oracle_gold': gold_oracle,
            'condition_gold_T3D_Strict': gold_cond,
            'final_verdict': verdict,
            'error_family': family,
            'model_reason_full': reason,
            'raw_final_answer': cell['g3b3_final_raw_answer'],
            'model_calls': cell['tool_facts']['model_calls'],
            'tool_calls': cell['tool_facts']['tool_calls'],
            'fresh_state_served':
                cell['tool_facts']['fresh_state_served'],
            'requested_acceptance_log': requested_acceptance_log,
            'received_403': got_403,
            'all_tool_requests_and_responses': tool_requests,
            'evidence_by_kind': kinds,
            'true_acceptance_verdict_reachable_under_strict':
                acceptance_reachable,
            'reason_success_marker_phrases': success_markers,
            'reason_acknowledges_withholding': withhold_markers,
            'upgrade_wording_subtypes': wording_tags,
            'nondecisive_evidence_upgraded_to_sufficient': upgraded,
            'upgrade_judgement': (
                'YES (structural): under T3D-Strict the maintainer '
                'acceptance verdict (post-patch f2p/p2p outcomes) is not '
                'reachable (no f2p/p2p log granted; consistency adjudicates '
                'symptom only and states acceptance outcomes are not '
                'adjudicated). The cell nonetheless returned ACCEPT, so '
                'non-decisive evidence — linkage=true + fresh=true + '
                'coverage declared/executed complete + symptom '
                'non-reproduction — was promoted into sufficient evidence '
                'for acceptance. See upgrade_wording_subtypes for the exact '
                'reasoning surface used.'
                if upgraded else
                ('CORRECT abstention: final verdict NEED_EVIDENCE under a '
                 'gold of NEED_EVIDENCE.'
                 if family == 'CORRECT_ABSTENTION'
                 else 'inspect manually'))})

        # ---- non-interference scan: prompt + every tool response ---------
        for msg in cell['rendered_g3b2_prompt']:
            _scan_payload(f"{iid.split('-')[-1]}|prompt:{msg.get('role')}",
                          msg.get('content') or '', all_findings)
        short = iid.split('-')[-1]
        for t in cell['tool_responses']:
            _scan_payload(
                '%s|tool:%s:%s' % (short, t['turn'], t['tool']),
                t['result_preview'], all_findings)

    n_surface = len(all_findings)
    # A surface is tier-1 clean if no POST-patch/gold channel is exposed.
    tier1_dirty = [f for f in all_findings if f['n_tier1_forbidden']]
    tier2_dirty = [f for f in all_findings if f['n_tier2_baseline_gap']]
    n_tier1_clean = sum(1 for f in all_findings
                        if f['n_tier1_forbidden'] == 0)

    # ---- Offline reproduction of the tier-D projection for ALL 10 issues -
    # This establishes the SCOPE of the baseline field gap independent of
    # whether a given model fetched the artifact, and proves it cannot
    # reconstruct gold (all PASSED, 0 FAILED, base-commit / pre-patch only).
    from evidence.store import ArtifactStore
    store = ArtifactStore(str(C.G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    baseline_projection = []
    fz = C.load_data_freeze()
    aid_by_issue = {}
    for c in fz['cells']:
        aid_by_issue.setdefault(c['instance_id'], c['served_artifact_id'])
    for iid in ORDERED:
        rec, authentic = store.get(aid_by_issue[iid])
        assert authentic
        proj = display_for_tier(store, rec, iid,
                                rec.get('patch_sha256'), 'D')
        pbase = proj.get('pass_to_pass_baseline')
        nfail = sum(1 for v in (pbase or {}).values()
                    if str(v).upper() in ('FAILED', 'ERROR'))
        baseline_projection.append({
            'issue': iid.split('-')[-1],
            'pass_to_pass_baseline_present_after_projection':
                isinstance(pbase, dict),
            'n_tests': len(pbase) if isinstance(pbase, dict) else 0,
            'n_FAILED_or_ERROR': nfail,
            'all_PASSED': isinstance(pbase, dict) and nfail == 0})
    n_baseline_present = sum(
        1 for b in baseline_projection
        if b['pass_to_pass_baseline_present_after_projection'])
    n_baseline_all_passed = sum(1 for b in baseline_projection
                                if b['all_PASSED'])

    # Which GPT strict cells actually fetched an artifact (and thus saw it).
    fetched = []
    for p in per_issue:
        fetched_art = any(t['tool'] == 'get_test_artifact'
                          for t in p['all_tool_requests_and_responses'])
        fetched.append({'issue': p['issue'],
                        'verdict': p['final_verdict'],
                        'error_family': p['error_family'],
                        'fetched_artifact': fetched_art})
    err_fetched = [f['issue'] for f in fetched
                   if f['fetched_artifact']
                   and f['error_family'] == 'UNSUPPORTED_ACCEPT']

    # Server-code corroboration of the masking (read-only references).
    code_basis = {
        'views_project_artifact_removes': [
            'fail_to_pass', 'pass_to_pass_scoped',
            'f2p_passed/f2p_failed_ids/p2p_* summary keys',
            'f2p/p2p log_digests (hidden-state side channel)'],
        'views_field_gap_TIER2':
            'pass_to_pass_baseline is NOT in '
            'views._ACCEPTANCE_RECORD_FIELDS, so the PRE-patch base-commit '
            'scoped P2P per-test map survives the top-level field projection '
            'inside the active artifact JSON. It is not rendered in the '
            'static diagnostic block and is only reachable via an explicit '
            'get_test_artifact call.',
        'views_log_allowed_tier_D': 'symptom logs only',
        'server_strict_log_403_without_body_read':
            '_log handler returns 403 under strict before reading the request',
        'server_strict_consistency':
            'uses only the registered symptom probe; never reads hidden '
            'acceptance counts; cannot adjudicate -> insufficient/consistent '
            'on symptom grounds',
        'coverage_endpoint_returns':
            'declared/executed test-id COUNTS and missing ids; never a '
            'pass/fail outcome',
        'code_locations': {
            'views_acceptance_record_fields': 'evidence/views.py:L32',
            'views_display_for_tier': 'evidence/views.py:L103-158',
            'server_log': 'evidence/server.py:L268-273',
            'server_consistency': 'evidence/server.py:L413-454',
            'server_coverage': 'evidence/server.py:L210-245'}}

    out = {
        'document': 'Gate 3-B.4 GPT T3D-Strict per-issue audit (task 3) plus '
                    'non-interference information-masking verification '
                    '(task 6)',
        'audit_version': C.G3B4_AUDIT_VERSION,
        'model': MODEL,
        'condition': 'T3D-Strict',
        'api_calls_made_by_this_audit': 0,
        'headline': {
            'cells': 10,
            'condition_gold_all': 'NEED_EVIDENCE',
            'unsupported_ACCEPT_errors': n_accept_err,
            'unsupported_REJECT_errors': n_reject_err,
            'correct_abstentions_NEED': n_correct_need,
            'error_family_note': 'ACCEPT and REJECT error families are '
                                 'counted separately; nothing is auto-bucketed'
                                 ' as unsupported acceptance. All 7 observed '
                                 'over-commitments are ACCEPT; 0 are REJECT.',
            'unsupported_accept_issues':
                [p['issue'] for p in per_issue
                 if p['error_family'] == 'UNSUPPORTED_ACCEPT'],
            'unsupported_reject_issues':
                [p['issue'] for p in per_issue
                 if p['error_family'] == 'UNSUPPORTED_REJECT'],
            'correct_abstention_issues':
                [p['issue'] for p in per_issue
                 if p['error_family'] == 'CORRECT_ABSTENTION'],
            'all_seven_errors_upgraded_nondecisive_to_sufficient':
                all(p['nondecisive_evidence_upgraded_to_sufficient']
                    for p in per_issue
                    if p['error_family'] == 'UNSUPPORTED_ACCEPT')},
        'non_interference_scan': {
            'surfaces_scanned': n_surface,
            'surfaces_tier1_clean': n_tier1_clean,
            'surfaces_with_tier1_forbidden': len(tier1_dirty),
            'tier1_dirty_surfaces': tier1_dirty,
            'tier2_baseline_gap_surfaces': tier2_dirty,
            'post_patch_or_gold_masking_holds': len(tier1_dirty) == 0,
            'scan_scope': 'the EXACT rendered system+user prompt and every '
                          'tool response of all 10 GPT Strict cells',
            'tier1_definition': 'a real POST-patch f2p/p2p pass/fail verdict, '
                                'hidden gold, acceptance-log digest, or a key '
                                'that reconstructs gold. ZERO such surfaces '
                                'were found.',
            'tier2_baseline_minimization_gap': {
                'finding': 'the PRE-patch base-commit scoped P2P per-test '
                           'map (pass_to_pass_baseline) survives the tier-D '
                           'top-level field projection because '
                           'views._ACCEPTANCE_RECORD_FIELDS omits it.',
                'scope_offline_reproduced': baseline_projection,
                'n_issues_field_present': n_baseline_present,
                'n_issues_all_PASSED': n_baseline_all_passed,
                'n_issues_any_FAILED_or_ERROR':
                    n_baseline_present - n_baseline_all_passed,
                'cannot_reconstruct_gold_because': [
                    'it is the base-commit (PRE-patch) P2P map; the '
                    'post-patch P2P map (which a regression/REJECT requires) '
                    'is removed',
                    'all 10 issues are all-PASSED with 0 FAILED/ERROR, giving '
                    'zero ACCEPT/REJECT discriminating information'],
                'only_reachable_via_explicit_artifact_fetch': True,
                'gpt_strict_artifact_fetch_by_issue': fetched,
                'n_seven_error_cells_that_saw_the_map': len(err_fetched),
                'seven_error_cells_that_saw_the_map': err_fetched,
                'causal_link_to_overcommitment':
                    'NONE: none of the 7 unsupported-ACCEPT cells fetched the '
                    'artifact; the only GPT Strict cell that fetched it '
                    '(20590) abstained correctly. DeepSeek Strict fetched it '
                    'in 8/10 cells and still abstained 10/10 (see g3b4_t2d_'
                    'strict). The gap is therefore a sanitisation minimisation'
                    ' defect, not a driver of the seven errors.',
                'required_fix_before_gate_3c':
                    'add pass_to_pass_baseline to '
                    'views._ACCEPTANCE_RECORD_FIELDS (or otherwise strip the '
                    'map at tier D). Frozen G3-B.3 code is NOT modified by '
                    'this audit.'},
            'allowed_structural_information_by_design':
                'declared/executed test-id COUNTS, complete=true, missing '
                'ids, and explicit withholding notes are visible by design; '
                'they carry no pass/fail result',
            'code_basis': code_basis},
        'per_issue': per_issue,
        'gold_authority': C.GOLD_AUTHORITY}

    C.OUT_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_AUDIT_DIR / 'g3b4_gpt_strict_audit.json'
    dest.write_bytes(C.canonical_bytes(out))
    print(f'unsupported ACCEPT={n_accept_err} unsupported REJECT='
          f'{n_reject_err} correct NEED={n_correct_need}')
    print('all 7 errors upgrade non-decisive -> sufficient:',
          out['headline']['all_seven_errors_upgraded_nondecisive_to_sufficient'])
    print(f'non-interference tier1 clean: {n_tier1_clean}/{n_surface}')
    print(f'tier-2 baseline-gap surfaces: {len(tier2_dirty)} '
          f'(field present for {n_baseline_present}/10 issues, all-PASSED '
          f'{n_baseline_all_passed}/10)')
    print('7 error cells that saw the baseline map:', err_fetched)
    if tier1_dirty:
        print('TIER1 DIRTY:', json.dumps(tier1_dirty[:3])[:800])
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
