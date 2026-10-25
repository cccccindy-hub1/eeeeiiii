"""Evidence tiers: what a reviewer is *shown*, independent of what exists.

Phase 2 answer-leakage control. The Phase-1 T2 block printed the exact quantities
that define merge_acceptable (FAIL_TO_PASS outcomes + PASS_TO_PASS regression
verdicts), turning "uses evidence" into "reads the acceptance answer". We now
separate two visibility tiers:

  diagnostic ('D')  identity/scope metadata + the issue-derived symptom probe
                    outcome. Acceptance-test outcomes, regression verdicts, the
                    failing/passed test id lists, and raw f2p/p2p logs are WITHHELD.
                    A reviewer can see that the reported symptom was reproduced and
                    re-checked, but cannot read the maintainers' acceptance answer.

  acceptance ('A')  the full signed record (Phase-1 T2/T3 behaviour), kept as an
                    explicit ACCEPTANCE-EVIDENCE baseline so the two questions are
                    measured separately:
                      (a) does seeing the acceptance answer help?  (D vs A)
                      (b) does actively verifying evidence help?    (static vs tools)

The projection is applied BOTH to the static prompt block and to every T3 tool
payload (get_test_artifact / get_run_log); otherwise a diagnostic reviewer could
escalate to acceptance content just by fetching a log.
"""
from __future__ import annotations

import re

TIERS = ('D', 'A')

# Fields that encode maintainer acceptance verdicts and therefore constitute the
# "answer": never present in a diagnostic payload.
_ACCEPTANCE_RECORD_FIELDS = ('fail_to_pass', 'pass_to_pass_scoped')
_ACCEPTANCE_SUMMARY_KEYS = (
    'f2p_passed', 'f2p_failed_ids',
    'p2p_passed', 'p2p_regressed_ids', 'p2p_preexisting_bad_ids',
)
# Raw logs whose verbose pytest columns expose per-acceptance-test verdicts.
_ACCEPTANCE_LOGS = ('f2p', 'p2p', 'p2p_baseline')
# Their log_digests are identity fingerprints of the hidden acceptance content:
# two worlds with identical diagnostics but different hidden acceptance results
# would differ in these hashes, which is itself a hidden-state side channel.
# Strip them from diagnostic projections (the symptom log digest is structural).

# Strings that would betray an acceptance verdict even if a future field is added.
_LEAK_PATTERNS = (
    re.compile(r'FAIL_TO_PASS passed', re.I),
    re.compile(r'PASS_TO_PASS passed', re.I),
    re.compile(r'failing acceptance test ids', re.I),
    re.compile(r'regression test ids', re.I),
)


_PHASE2_RUNNER_RE = re.compile(r'\s*phase2=\S+')
_CANONICAL_SCOPE_RULE = ('F2P all; P2P scoped to test_patch files and tests/ '
                         'adjacent to each changed code file')


def neutralize_fixture(rec: dict, instance_id: str, patch_sha256: str,
                       declared: dict | None = None) -> dict:
    """Return a DISPLAY copy with every scenario-identifying string removed.

    The scenario label must never be derivable from a served payload, even at the
    acceptance tier. This rewrites (display-only; the signed stored record is
    untouched):
      - artifact_id  -> the same neutral `art_<hash>` id a normal run would have
                        for THIS served patch (linkage is still computed server-side
                        from the record's real hashes, so wrong_patch stays false);
      - runner       -> drops the `phase2=<scenario>` token;
      - scope.rule   -> the ordinary scoping rule (the fixture text announced
                        "intentionally restricted", which would hand over the
                        incomplete/stale answer in the static block).

    `declared`, when given (values from the signed attestation for the SERVED
    patch), replaces fields that at tier D are presented as "declared by
    maintainers": f2p/p2p scheduled counts AND the scoped-file list. A doctored
    incomplete record stores EXECUTED values (0 regression checks, 1 file), which
    would otherwise reveal non-coverage statically — both as zero totals and as a
    shrunk file list — and defeat the coverage surface. Declared values are
    structural, not outcomes.
    """
    from .schemas import make_artifact_id
    out = dict(rec)
    out['artifact_id'] = make_artifact_id(instance_id, patch_sha256)
    out.pop('phase2_scenario', None)
    if isinstance(out.get('runner'), str):
        out['runner'] = _PHASE2_RUNNER_RE.sub('', out['runner']).strip()
    if isinstance(out.get('scope'), dict):
        scope = dict(out['scope'])
        scope['rule'] = _CANONICAL_SCOPE_RULE
        if declared and declared.get('scope_files') is not None:
            scope['p2p_scoped_files'] = list(declared['scope_files'])
        out['scope'] = scope
    if declared is not None and isinstance(out.get('summary'), dict):
        summ = dict(out['summary'])
        if declared.get('f2p_total') is not None:
            summ['f2p_total'] = declared['f2p_total']
        if declared.get('p2p_total') is not None:
            summ['p2p_total'] = declared['p2p_total']
        out['summary'] = summ
    return out


def display_for_tier(store, rec: dict, instance_id: str, patch_sha256: str,
                     tier: str) -> dict:
    """Single chokepoint for EVERY record a reviewer can see (HTTP payloads AND
    the T2 static prompt block): neutralise fixture labels at both tiers; at tier
    D additionally substitute attestation-backed declared counts/file list, then
    project away acceptance outcomes."""
    tier = (tier or 'A').upper()
    declared = None
    if tier == 'D':
        att = store.get_attestation(instance_id, patch_sha256)
        if att is not None:
            declared = {
                'f2p_total': len(att['declared_fail_to_pass']),
                'p2p_total': len(att['declared_p2p_scoped']),
                'scope_files': list(att.get('declared_scope_files') or []),
            }
    disp = neutralize_fixture(rec, instance_id, patch_sha256, declared)
    return project_artifact(disp, tier)


def project_artifact(rec: dict, tier: str) -> dict:
    """Return the artifact record safe to embed at the given visibility tier.

    Diagnostic keeps structural facts (how many tests were scheduled) but removes
    every outcome. The returned object is a copy; the signed original is untouched.
    """
    tier = (tier or 'A').upper()
    if tier == 'A':
        return dict(rec)
    out = {k: v for k, v in rec.items() if k not in _ACCEPTANCE_RECORD_FIELDS}
    scope = dict(out.get('scope') or {})
    summ = dict(out.get('summary') or {})
    # Counts of scheduled tests are structural, outcomes are not.
    for k in _ACCEPTANCE_SUMMARY_KEYS:
        summ.pop(k, None)
    summ['outcomes_withheld'] = True
    summ['note'] = ('acceptance-test outcomes and regression verdicts are withheld at '
                    'the diagnostic tier; use the verification service to seek them.')
    out['summary'] = summ
    # Remove acceptance-log content hashes: a digest of hidden acceptance output
    # is a fingerprint correlated with the hidden verdict. Keep only the digest
    # of the authorised diagnostic (symptom) log.
    digests = dict(out.get('log_digests') or {})
    for name in _ACCEPTANCE_LOGS:
        digests.pop(name, None)
    if 'log_digests' in out:
        out['log_digests'] = digests
    out['evidence_tier'] = 'diagnostic'
    return out


def log_allowed(log_name: str, tier: str) -> bool:
    """Diagnostic reviewers may read the issue-derived symptom log only."""
    if (tier or 'A').upper() == 'A':
        return True
    return log_name not in _ACCEPTANCE_LOGS


def evidence_block(artifact: dict, tier: str = 'A', symptom: dict | None = None) -> str:
    """Static evidence block for T2-style cells.

    symptom: optional {'pre_patch_passed': bool, 'post_patch_passed': bool}
    sourced from the issue-derived reproduction probe (NOT the maintainer
    test_patch). It is diagnostic evidence even when acceptance is withheld.
    """
    tier = (tier or 'A').upper()
    if tier == 'A':
        return _acceptance_block(artifact)
    return _diagnostic_block(artifact, symptom)


def _identity_lines(artifact: dict):
    return [
        f"  artifact_id: {artifact['artifact_id']}",
        f"  runner: {artifact.get('runner')}",
        f"  base_commit: {artifact.get('base_commit')}",
        f"  patch_sha256: {artifact.get('patch_sha256')}",
        f"  started_at: {artifact.get('started_at')}",
        f"  finished_at: {artifact.get('finished_at')}",
    ]


def _diagnostic_block(artifact: dict, symptom: dict | None) -> str:
    summary = artifact.get('summary', {}) or {}
    scope = artifact.get('scope', {}) or {}
    files = scope.get('p2p_scoped_files') or []
    lines = [
        'TEST ARTIFACT (DIAGNOSTIC tier; linkage not yet verified):',
        '  Evidence in this record is limited to reproduction/regression-check metadata.',
        '  Maintainer acceptance-test outcomes are intentionally NOT included.',
    ] + _identity_lines(artifact)
    lines += [
        '  scope:',
        f"    rule: {scope.get('rule', 'n/a')}",
        f"    scoped test files: {len(files)}",
        f"    acceptance tests scheduled by maintainers: {summary.get('f2p_total', 'n/a')}"
        " (outcomes withheld)",
        f"    scoped regression checks scheduled: {summary.get('p2p_total', 'n/a')}"
        " (verdicts withheld)",
    ]
    if symptom is not None:
        # Probe polarity (see builder.py: issue_addressed = (not pre_ok) and
        # post_ok): the issue-reproduction probe PASSES when the symptom is
        # GONE. So pre_patch_passed=False means the symptom IS present before
        # the patch, and post_patch_passed=True means it does NOT reproduce
        # after the patch. Render the human-facing symptom wording accordingly;
        # inverting this injects false anti-patch evidence.
        pre = symptom.get('pre_patch_passed')
        post = symptom.get('post_patch_passed')
        present_before = ('yes' if pre is False else 'no' if pre is True else 'n/a')
        reproduces_after = ('yes' if post is False else 'no' if post is True else 'n/a')
        lines.append('  issue-reproduction probe (derived from the issue text, not the '
                     'maintainer test suite; a passing probe means the symptom is GONE):')
        lines.append(f'    issue symptom present before patch: {present_before}')
        lines.append(f'    issue symptom reproduces after patch: {reproduces_after}')
    else:
        lines.append('  issue-reproduction probe: (not attached)')
    lines.append('  NOTE: a reproduced/removed symptom is NOT proof of merge '
                 'acceptability; acceptance tests and regression verdicts remain to be '
                 'checked or independently sought.')
    return '\n'.join(lines)


def _acceptance_block(artifact: dict) -> str:
    summary = artifact.get('summary', {}) or {}
    lines = [
        'TEST ARTIFACT (ACCEPTANCE tier; full static record; linkage not yet verified):',
    ] + _identity_lines(artifact)
    lines += [
        f"  FAIL_TO_PASS passed: {summary.get('f2p_passed')}/{summary.get('f2p_total')}",
        f"  scoped PASS_TO_PASS passed: {summary.get('p2p_passed')}/{summary.get('p2p_total')}",
    ]
    fail = summary.get('f2p_failed_ids') or []
    if fail:
        lines.append('  failing acceptance test ids:')
        lines += [f'    - {x}' for x in fail[:30]]
    reg = summary.get('p2p_regressed_ids') or []
    if reg:
        lines.append('  regression test ids (passed before patch, fail after):')
        lines += [f'    - {x}' for x in reg[:30]]
    pre = summary.get('p2p_preexisting_bad_ids') or []
    if pre:
        lines.append('  tests already failing at base commit (environment/pre-existing, '
                     'not counted as regressions):')
        lines += [f'    - {x}' for x in pre[:30]]
    return '\n'.join(lines)


def assert_clean_diagnostic_text(text: str):
    """Self-test guard: no acceptance verdict may appear in a diagnostic payload."""
    hits = [p.pattern for p in _LEAK_PATTERNS if p.search(text or '')]
    if hits:
        raise AssertionError('diagnostic payload leaks acceptance verdict: ' + ', '.join(hits))
