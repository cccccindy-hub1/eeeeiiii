"""Gate G3-C.0 task 7 — strict restricted-evidence non-interference audit
PROTOCOL (design only, $0). Defines what tier D must never show, what pre-
patch information is legal, and a machine+human audit to run inside the Gate
3-C mock gate before any paid call. Reuses the frozen G3-B.4 scanner for the
machine part and references the demonstrated projection v2.

    uv run --python 3.13 -m evidence.g3c0_noninterference
"""
from __future__ import annotations

from evidence import g3c0_common as C


def main():
    deny = {
        'title': 'DENY list — never present at the restricted (tier-D) tier',
        'post_patch_outcomes': [
            'post-patch FAIL_TO_PASS per-test statuses or pass/fail counts',
            'post-patch scoped PASS_TO_PASS per-test statuses or regression '
            'verdicts (pass_to_pass_scoped)',
            'summary f2p_passed / f2p_failed_ids / p2p_passed / '
            'p2p_regressed_ids / p2p_preexisting_bad_ids',
            'the f2p and p2p raw logs and their log_digests (a digest of '
            'hidden outcome output is a hidden-state side channel)'],
        'gold_channels': [
            'hidden condition gold / oracle gold / any *_gold field',
            'ground_truth_verdict, phase2_scenario, audit_condition, '
            'audit_oracle, or any field from which the final ACCEPT/REJECT '
            'gold is directly reconstructable',
            'the maintainer merge_acceptable/classify label'],
        'prepatch_redundancy_closed_in_v2': [
            'pass_to_pass_baseline: the pre-patch base-commit per-test P2P '
            'MAP embedded in the active artifact JSON is removed in '
            'projection v2 (the G3-B.4 tier-2 minimisation gap)',
            'the p2p_baseline RAW LOG already stays denied at tier D and '
            'strict returns HTTP 403 before reading any body'],
        'wording_leaks': 'the frozen views._LEAK_PATTERNS phrases '
                         '("FAIL_TO_PASS passed", "PASS_TO_PASS passed", '
                         '"failing acceptance test ids", "regression test '
                         'ids") must not appear in any served surface.',
    }

    allow_prepatch = {
        'title': 'ALLOW list — legal pre-patch / structural information at '
                 'tier D',
        'rationale': 'structural/identity/metadata and the issue-derived '
                     'symptom probe carry provenance and coverage information'
                     ' WITHOUT encoding the post-patch maintainer verdict.',
        'items': [
            'identity metadata: neutral artifact_id, runner, base_commit, '
            'patch_sha256, start/finish timestamps',
            'DECLARED scheduled test SET composition and COUNTS (f2p_total, '
            'p2p_total) — how many/which tests maintainers declared, not how '
            'they came out',
            'scope rule and the declared scoped file list',
            'coverage comparison of executed vs declared test IDS: declared '
            'count, executed count, missing ids, complete=true/false — but '
            'NEVER any pass/fail outcome',
            'linkage/provenance: whether the served patch matches the signed '
            'attestation (authentic/linked), run-tree match',
            'freshness: whether the record is fresh for the served patch and '
            'current base commit (fresh boolean + structural trees)',
            'the issue-derived SYMPTOM reproduction probe (pre: symptom '
            'present? post: symptom reproduces?), explicitly labelled as NOT '
            'a maintainer acceptance test',
            'explicit withholding notices stating acceptance outcomes are '
            'not adjudicated under strict'],
        'prepatch_status_policy': 'PRE-patch per-test pass/fail statuses are '
            'not needed for the restricted construct; the embedded baseline '
            'MAP is removed in v2 even though it was all-PASSED. If a future '
            'research question requires a pre-patch signal, only the issue-'
            'symptom probe polarity (already allowed) or an aggregate '
            'count with no per-test ids may be added, and only via a new '
            'versioned projection with its own non-interference audit.',
    }

    no_auto_sufficiency = {
        'title': 'No automatic acceptance-sufficiency grant',
        'rule': 'a tool success (HTTP 200), freshness=TRUE, linkage=TRUE, '
                'coverage complete=TRUE, or symptom-resolution MUST NOT, by '
                'itself or jointly, cause the harness/protocol to mark '
                'Acceptance Sufficiency as satisfied or to emit an ACCEPT.',
        'enforcement': [
            'the strict consistency endpoint adjudicates the symptom claim '
            'only and appends "maintainer acceptance outcomes are not '
            'adjudicated under the strict policy"',
            'coverage returns counts/ids and an explicit note that it reports'
            ' no pass/fail outcomes; complete!=acceptable',
            'freshness returns recency/identity, never a verdict',
            'no server response field is named or worded to imply '
            '"sufficient to accept"; a schema lint rejects fields like '
            'acceptance_sufficient / merge_ok / verdict=ACCEPT on a tier-D '
            'channel',
            'the system prompt states these signals are necessary-not-'
            'sufficient; the reminder arm makes this even more explicit'],
        'audit_check': 'grep/schema-scan every tier-D response and the system'
                       ' prompt for any implication that fresh+linked+complete'
                       '+symptom-gone entails acceptance; any such statement '
                       'fails the pre-paid gate.',
    }

    machine_audit = {
        'when': 'automatically, inside the zero-API mock/live gate, for EVERY '
                'issue x condition x model cell before the paid batch is '
                'unlocked',
        'scanner': 'the frozen evidence.g3b4_strict_audit three-tier scanner '
                   '(tier-1 forbidden / tier-2 baseline gap / allowed '
                   'structural), applied to the exact rendered system+user '
                   'prompt and every tool response',
        'surfaces': [
            'rendered static block(s)',
            'active artifact JSON (projection v2)',
            'every linkage/freshness/coverage/consistency response',
            'every log response (must be 403, body never read, for f2p/p2p/'
            'p2p_baseline under strict)',
            'any error/404/400 payload (must not echo hidden content)'],
        'pass_criteria': {
            'tier1_forbidden_findings': 0,
            'tier2_baseline_gap_findings': 0,
            'gold_reconstruction_keys': 0,
            'log_escalations_under_strict': 0,
            'auto_sufficiency_implications': 0},
        'fail_action': 'hard block: no paid call for that protocol build '
                       'until the surface is clean and the gate is re-run; '
                       'the failing surface is frozen for the record.',
        'demonstrated_clean_v2': 'Gate G3-C.0 offline demonstration over the '
                                '10 frozen served artifacts: v1 tier-1=0/'
                                'tier-2=10; v2 tier-1=0/tier-2=0 (see '
                                'g3c0_projection_v2_spec_and_test.json).',
    }

    human_audit = {
        'when': 'once per protocol build (and after any prompt/tool change)',
        'reviewer': 'a reviewer independent of the projection author where '
                    'feasible; at minimum a second human reading the rendered'
                    ' surfaces with the deny list in hand (AI-only review is '
                    'labelled, not treated as independent sign-off)',
        'task': 'read full rendered transcripts of a stratified sample and '
                'confirm no channel lets a motivated reader reconstruct the '
                'post-patch acceptance verdict or the hidden gold.',
    }

    out = {
        'document': 'Gate G3-C.0 task 7: strict restricted-evidence non-'
                    'interference audit protocol for Gate 3-C',
        'design_version': C.G3C0_DESIGN_VERSION,
        'projection_required': C.PROJECTION_V2_VERSION,
        'api_calls_made': 0,
        'deny_list': deny,
        'legal_prepatch_information': allow_prepatch,
        'no_automatic_acceptance_sufficiency': no_auto_sufficiency,
        'machine_audit': machine_audit,
        'human_audit': human_audit,
        'three_prohibitions_from_approval': [
            'no post-patch F2P/P2P pass-fail results shown',
            'no hidden gold or gold-reconstructing equivalent field shown',
            'no automatic acceptance sufficiency from tool success / freshness'
            ' TRUE / coverage complete'],
    }
    C.OUT_PROJECTION.mkdir(parents=True, exist_ok=True)
    dest = C.OUT_PROJECTION / 'g3c0_noninterference_audit_protocol.json'
    dest.write_bytes(C.canonical_bytes(out))
    print('deny groups:', len(deny), 'allow items:',
          len(allow_prepatch['items']))
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
