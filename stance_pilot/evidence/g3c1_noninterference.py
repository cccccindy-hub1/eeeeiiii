"""G3-C.1 task 7 (part B) — strict restricted-evidence non-interference audit
of the surfaces ACTUALLY SERVED by the G3-C.1 local server, zero API.

Consumes:
  * audit/g3c1_http_transcript.jsonl produced by g3c1_crosscheck (every real
    tool response across 8 issues x 5 conditions), and
  * the rendered static evidence block (frozen views.evidence_block over the
    G3-C.0 projection-v2 diagnostic artifact) per issue.

Hard gate (per the frozen G3-C.0 non-interference protocol):
  * every scannable tier-D surface (all diagnostic endpoints, including the
    strict 403 and reason-less 400 bodies, but EXCLUDING an explicitly
    reason-granted escalation log body and ungated tier-A logs) must have
      tier-1 forbidden findings == 0  AND
      tier-2 baseline-map findings == 0  (v2 removed pass_to_pass_baseline);
  * schema lint: no tier-D surface may name acceptance_sufficient / merge_ok
    or carry a final verdict token ACCEPT;
  * tier-A surfaces are institutional presentations and are SUPPOSED to carry
    outcomes, so they are only linted for hidden-gold reconstruction keys
    (oracle_gold/condition_gold/ground_truth_verdict/...) which must be 0.

A single finding fails the gate with a non-zero exit; the offending surface is
frozen into the audit record. Nothing here calls a model or the network.

  uv run --offline --python 3.9 -m evidence.g3c1_noninterference
"""
from __future__ import annotations

import json
import re

from evidence import g3c1_common as C
from evidence import g3b4_strict_audit as SCAN  # frozen scanner, read-only
from evidence.store import ArtifactStore
from evidence.schemas import make_artifact_id
from evidence.views import display_for_tier, evidence_block
from evidence.g3c0_projection_v2 import project_diagnostic_v2

TRANSCRIPT = C.OUT_AUDIT / 'g3c1_http_transcript.jsonl'
OUT = C.OUT_PROJECTION / 'g3c1_noninterference_audit.json'

# Schema lint: tier-D must never auto-grant acceptance or leak a final verdict.
AUTO_SUFFICIENCY_KEYS = ('acceptance_sufficient', 'merge_ok', 'merge_acceptable',
                         'sufficient_to_accept')
VERDICT_ACCEPT_RE = re.compile(r'"verdict"\s*:\s*"ACCEPT"')
# Hidden-gold reconstruction keys, forbidden at ANY served tier.
GOLD_KEYS = ('oracle_gold', 'condition_gold', 'ground_truth_verdict',
             'phase2_scenario', 'audit_oracle', 'audit_condition',
             '_oracle_gold', 'label_class')


def _schema_lint_tier_d(text):
    low = text.lower()
    hits = [k for k in AUTO_SUFFICIENCY_KEYS if k in low]
    if VERDICT_ACCEPT_RE.search(text):
        hits.append('verdict=ACCEPT')
    return hits


def _gold_key_hits(text):
    low = text.lower()
    return [k for k in GOLD_KEYS if k in low]


def main():
    C.ensure_out_dirs()
    transcript = C.read_jsonl(TRANSCRIPT)
    if not transcript:
        raise SystemExit('missing/empty HTTP transcript; run g3c1_crosscheck '
                         'first')
    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')

    surfaces = []

    def add(name, tier, text, *, scannable_d):
        t1, t2, _allowed = SCAN._scan_text(text)
        surfaces.append({'name': name, 'tier': tier,
                         'scannable_restricted': scannable_d,
                         'n_chars': len(text), 'tier1': t1, 'tier2': t2,
                         'schema_hits': (_schema_lint_tier_d(text)
                                         if tier == 'D' else []),
                         'gold_key_hits': _gold_key_hits(text)})

    # 1) real served tool responses
    for e in transcript:
        # A scannable tier-D surface is in the restricted set: every diagnostic
        # endpoint and every denied log body (strict 403, reason-less 400).
        # Granted reveals (escalation 200 with a reason) and ungated tier-A
        # logs are recorded with scannable=False by the cross-check, so they
        # are correctly excluded here.
        restricted = e['tier'] == 'D' and e['scannable']
        add(f"http:{e['cell']}:{e['endpoint']}:{e['http_status']}",
            e['tier'], e['body'], scannable_d=restricted)

    # 2) rendered static evidence block per issue (T2D diagnostic + T2A anchor)
    for t in C.read_jsonl(C.TRUTH):
        iid = t['instance_id']
        aid = make_artifact_id(iid, t['patch_sha256'])
        rec, authentic = store.get(aid)
        if not authentic:
            raise SystemExit(f'inauthentic artifact for {iid}')
        symptom = {
            'pre_patch_passed':
                t['label_provenance'].get('symptom_pre_patch_passed'),
            'post_patch_passed':
                t['label_provenance'].get('symptom_post_patch_passed')}
        v2 = project_diagnostic_v2(
            display_for_tier(store, rec, iid, t['patch_sha256'], 'D'))
        add(f'static-block:{iid}:T2D-D', 'D',
            evidence_block(v2, 'D', symptom=symptom), scannable_d=True)
        add(f'v2-artifact-json:{iid}', 'D',
            json.dumps(v2, ensure_ascii=False), scannable_d=True)
        view_a = display_for_tier(store, rec, iid, t['patch_sha256'], 'A')
        add(f'static-block:{iid}:T2A-A', 'A',
            evidence_block(view_a, 'A', symptom=symptom), scannable_d=False)

    # 3) evaluate the hard gate
    violations = []
    n_d = n_d_t1 = n_d_t2 = n_d_schema = n_a_gold = 0
    for s in surfaces:
        if s['tier'] == 'D' and s['scannable_restricted']:
            n_d += 1
            n_d_t1 += len(s['tier1'])
            n_d_t2 += len(s['tier2'])
            n_d_schema += len(s['schema_hits'])
            if s['tier1']:
                violations.append({'surface': s['name'], 'kind': 'tier1',
                                   'findings': s['tier1'][:5]})
            if s['tier2']:
                violations.append({'surface': s['name'], 'kind': 'tier2',
                                   'findings': s['tier2'][:5]})
            if s['schema_hits']:
                violations.append({'surface': s['name'], 'kind': 'schema',
                                   'findings': s['schema_hits']})
        if s['gold_key_hits']:
            n_a_gold += len(s['gold_key_hits'])
            violations.append({'surface': s['name'], 'kind': 'hidden_gold_key',
                               'findings': s['gold_key_hits']})

    passed = not violations
    report = {
        'document': 'G3-C.1 task 7: non-interference audit of actually served '
                    'surfaces (real g3c1 HTTP transcript + rendered static '
                    'blocks), projection v2, zero API.',
        'design_version': C.G3C1_DESIGN_VERSION,
        'projection_version': C.PROJECTION_V2_VERSION,
        'scanner': 'frozen evidence.g3b4_strict_audit._scan_text (reused, '
                   'not modified)',
        'api_calls_made': 0,
        'n_surfaces': len(surfaces),
        'n_restricted_tier_d_surfaces': n_d,
        'tier1_forbidden_findings': n_d_t1,
        'tier2_baseline_gap_findings': n_d_t2,
        'tier_d_schema_lint_findings': n_d_schema,
        'hidden_gold_key_findings_any_tier': n_a_gold,
        'pass_criteria': {
            'tier1_forbidden_findings': 0,
            'tier2_baseline_gap_findings': 0,
            'tier_d_schema_lint_findings': 0,
            'hidden_gold_key_findings_any_tier': 0},
        'passed': passed,
        'violations': violations,
        'authorized_reveal_policy': 'reason-granted escalation logs (200) and '
                                    'ungated tier-A logs are institutional '
                                    'acceptance channels by design and are '
                                    'excluded from the restricted scan; strict '
                                    '403 and reason-less 400 bodies are in '
                                    'scope and must be clean.',
        'surfaces': surfaces,
        'gold_authority': C.GOLD_AUTHORITY,
    }
    C.write_canonical(OUT, report)
    print(f"surfaces={len(surfaces)} restricted_D={n_d} tier1={n_d_t1} "
          f"tier2={n_d_t2} schema={n_d_schema} gold_keys={n_a_gold} "
          f"passed={passed}")
    if not passed:
        for v in violations[:20]:
            print('  VIOLATION', v)
        raise SystemExit('g3c1 non-interference gate FAILED')
    print('->', OUT.relative_to(C.HERE))


if __name__ == '__main__':
    main()
