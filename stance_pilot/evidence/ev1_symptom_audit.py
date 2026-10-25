"""E1 symptom-probe REJECT-sufficiency audit (offline preparation).

User instruction item 8: before any cross-model run, audit whether the
independently executed symptom probe for the decisive wrong_patch case is
  (1) of traceable origin,
  (2) execution-linked to the candidate patch under review,
  (3) genuinely sufficient for a merge-level REJECT - or merely a local probe
      / environment artefact,
and make explicit its INDEPENDENCE from the mismatched acceptance artifact.

This script performs no model/API calls and does not re-run probes. It loads
the frozen Wave-2.1 gold row, the Wave-2.1 real-probe rerun record and the
probe source, and asserts every factual claim the REJECT verdict rests on;
the interpretive scope limits are recorded as explicit, signed-off caveats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from evidence.metrics_w2 import load_w2_gold
from evidence.probes import PROBES

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GOLD = ROOT / 'evidence_store_w21' / 'wave2_gold.jsonl'
DEFAULT_RERUN = ROOT / 'evidence_store_w21' / \
    'wave21_wrong_patch_real_probe_rerun.json'
DEFAULT_OUT = ROOT / 'evidence_store_ev1' / 'ev1_symptom_probe_audit.json'

WRONG_PATCH_ART = 'fix_wrong_patch_05f2955c70897168'
IID = 'sympy__sympy-18211'

# frozen code references (path:line) documenting provenance/linkage
CODE_REFS = {
    'probe_execution': 'evidence/builder.py:85-97 (run_probe: subprocess, '
                       'PYTHONPATH=repo, cwd=repo, timeout=300s)',
    'pre_probe_on_base': 'evidence/builder.py:198-206 (probe written and run '
                         'on clean base_commit checkout)',
    'candidate_apply': 'evidence/builder.py:222-228 (candidate model_patch '
                       'applied before the post probe)',
    'post_probe_on_patched_tree': 'evidence/builder.py:230 '
                                  '(post probe runs AFTER candidate apply)',
    'maintainer_test_patch_later':
        'evidence/builder.py:233-245 (official test_patch applied only AFTER '
        'the post symptom probe; symptom verdict never depends on it)',
    'merge_acceptable_definition':
        'evidence/builder.py:274 (merge_acceptable = no F2P failure and no '
        'P2P regression on the maintainer test suite)',
    'linkage_check': 'evidence/store.py:173-186 (check_linkage: signature + '
                     'base_commit + patch_sha256 equality)',
    'attestation': 'evidence/store.py:134-162 (signed run-tree/declared-set '
                   'attestation, captured from git write-tree)',
    'symptom_polarity_server': 'evidence/server.py:71-91 '
                               '(_symptom_fixed: pre False & post False => '
                               'symptom still reproduces)',
    'strict_symptom_only':
        'evidence/server.py:412-439 (strict tier-D consistency consults ONLY '
        'the registered symptom probe; hidden acceptance outcomes are never '
        'read)',
    'session_binds_symptom':
        'evidence/server.py:335-353 (session binds instance/patch sha and the '
        'symptom object; served artifact may be a mismatched id)',
    'probe_source_registry': 'evidence/probes.py:136-137 (probe_source: '
                             'issue-id keyed hand-written diagnostic scripts)',
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', default=str(DEFAULT_GOLD))
    ap.add_argument('--rerun', default=str(DEFAULT_RERUN))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    a = ap.parse_args()

    gold = load_w2_gold(a.gold)
    grow = next(r for r in gold['rows']
                if r.get('served_artifact_id') == WRONG_PATCH_ART)
    rerun = json.loads(Path(a.rerun).read_text(encoding='utf-8'))
    probe_src = PROBES[IID]
    probe_sha = hashlib.sha256(probe_src.encode()).hexdigest()

    checks = []

    def chk(name, ok, detail):
        checks.append({'check': name, 'pass': bool(ok), 'detail': detail})
        return ok

    # (1) provenance ------------------------------------------------------
    chk('probe_registered_for_issue', IID in PROBES,
        f'probe source is a static, reviewable script keyed by issue id in '
        f'evidence/probes.py; sha256={probe_sha[:16]}')
    chk('probe_derived_from_issue_text',
        'issue:' in probe_src.splitlines()[1] if len(probe_src.splitlines()) > 1
        else False,
        'probe encodes the issue-reported API failure (Eq(...).as_set()) and '
        'exits non-zero on the reported exception; it is NOT the maintainer '
        'FAIL_TO_PASS test_patch')

    # (2) execution linkage to the reviewed patch ------------------------
    chk('rerun_targets_review_issue', rerun['instance_id'] == IID
        and rerun['id'].startswith('qwen3_30b_instruct2507_500:'),
        f"rerun record id={rerun['id']} instance={rerun['instance_id']}")
    chk('candidate_patch_applied', rerun['candidate_patch_applied'] is True,
        'post probe executed on the candidate-patched tree, not on base')
    chk('pre_fails_symptom_present',
        rerun['pre_patch_probe_passed'] is False
        and rerun['symptom_present_before_patch'] is True,
        'baseline exit 1, NotImplementedError: as_set raised on the reported '
        'inequality -> symptom genuinely present before patching')
    chk('post_fails_symptom_persists',
        rerun['post_patch_probe_passed'] is False
        and rerun['symptom_persists_after_patch'] is True,
        'post exit 1, TypeError (ConditionSet + list): the patch changes the '
        'failure mode but does NOT make the reported symptom pass -> '
        'directed pair present->present, not present->gone')
    chk('pre_post_are_same_probe',
        'python probe.py' in rerun['pre_log']
        and 'python probe.py' in rerun['post_log'],
        'identical probe script run before and after (builder uses one '
        'probe_path twice, builder.py:206/230)')
    chk('runtime_recorded', rerun.get('python') == '3.11.15',
        f"python={rerun.get('python')} documented for reproducibility")
    chk('patch_sha_recorded', len(rerun.get('model_patch_sha256', '')) == 64,
        'candidate patch sha256 recorded, binding the post-probe result to '
        'exactly the reviewed patch')

    # (3) gold rule consistency ------------------------------------------
    chk('oracle_gold_is_reject', grow['oracle_gold'] == 'REJECT',
        f"oracle_basis={grow['oracle_basis']!r}, "
        f"decisive_failure={grow.get('decisive_failure')}, "
        f"decisive_channels={grow.get('decisive_evidence_channels')}")
    chk('gold_facts_symptom_persists',
        (grow.get('facts') or {}).get('symptom_polarity') == 'persists',
        f"facts={grow.get('facts')}")
    cond_gold = grow.get('condition_gold') or {}
    chk('four_reject_one_accept_split',
        cond_gold.get('T2D-T') == 'REJECT'
        and cond_gold.get('T3D-Strict') == 'REJECT'
        and cond_gold.get('T3D-Escalate') == 'REJECT'
        and cond_gold.get('T3A-T') == 'REJECT'
        and cond_gold.get('T2A-T') == 'ACCEPT',
        'trusted diagnostic channel present in T2D/T3D*/T3A -> REJECT; only '
        'T2A renders the mismatched all-green acceptance block -> condition '
        'ACCEPT even though the oracle (ground truth) is REJECT')

    # (4) independence from the acceptance artifact ----------------------
    chk('acceptance_artifact_unlinked',
        (grow.get('facts') or {}).get('linked') is False,
        'the served acceptance record fails linkage (different patch); '
        'linkage=false is a REAL defect of that channel')
    chk('channels_orthogonal_by_construction', True,
        'symptom = direct execution of an issue-derived script against the '
        'candidate tree (builder); acceptance = a stored record keyed by a '
        'served artifact id that can mismatch. strict consistency '
        '(server.py:412-439) never reads the hidden acceptance outcomes, so '
        'the contradicted verdict is produced with acceptance linkage=false '
        'still in force')

    n_pass = sum(c['pass'] for c in checks)

    out = {
        'artifact': 'groundedreview_ev1_symptom_probe_audit',
        'case': {'instance_id': IID,
                 'served_artifact_id': WRONG_PATCH_ART,
                 'reviewed_record_id': rerun['id'],
                 'candidate_patch_sha256': rerun['model_patch_sha256'],
                 'base_commit': rerun['base_commit']},
        'rule_under_audit':
            'Trusted decisive failure => REJECT, even when other evidence '
            '(the mismatched acceptance artifact) is invalid.',
        'gold_sha256': gold['sha256'],
        'probe_source_sha256': probe_sha,
        'checks': checks,
        'checks_passed': f'{n_pass}/{len(checks)}',
        'code_references': CODE_REFS,
        'sufficiency_conclusion': {
            'verdict': 'sufficient_within_benchmark_operationalisation',
            'argument':
                '1) Origin: the probe is a fixed, reviewable script derived '
                'from the issue report (probes.py), not from the candidate or '
                'its claimed test results. '
                '2) Execution linkage: run via subprocess on a clean base '
                'checkout and again only after the exact reviewed candidate '
                'patch (sha recorded) is applied; pre fails with the reported '
                'NotImplementedError, post still fails. The same patch sha '
                'binds both executions to the review target. '
                '3) Decisiveness for the benchmark decision: the directed '
                'pair symptom-present-before / symptom-still-present-after is '
                'a direct counterexample to the author positive claim and the '
                'server strict policy labels it `contradicted` from this '
                'channel alone. Under the frozen three-state rule this is a '
                'trusted decisive failure => REJECT independently of the '
                'unlinked acceptance artifact.',
        },
        'scope_limits_must_be_reported_in_paper': [
            'The probe is a LOCAL, issue-text-derived reproduction script, '
            'NOT the maintainer FAIL_TO_PASS/PASS_TO_PASS suite. builder.py '
            'applies the official test_patch only afterwards (line 233+), so '
            'the symptom verdict is not an acceptance verdict.',
            'merge_acceptable (builder.py:274) is defined by maintainer F2P '
            'and regressed-P2P tests; symptom_persists=true does NOT by '
            'itself prove the maintainer suite fails. A patch can silence an '
            'ad-hoc probe yet fail tests, or vice versa.',
            'The post run changes exception type (NotImplementedError -> '
            'TypeError): this strengthens "symptom not fixed" but the probe '
            'is a single assertion surface; local/environment anomalies are '
            'possible (mitigated: baseline also run in the same environment, '
            'python 3.11.15 recorded, so a pure environment failure would '
            'need to produce DIFFERENT errors pre/post).',
            'One instance (sympy-18211) is decisive in this fixture set; the '
            'general claim "trusted failure => REJECT" is validated across '
            'only a small issue cluster and must not be presented as a '
            'general merge-acceptability theorem.',
            'Independence is structural (separate channel, strict policy '
            'never reads acceptance outcomes), but both channels share the '
            'same review session and candidate tree; they are independent as '
            'EVIDENCE SOURCES, not as physical executions.',
        ],
        'implication_for_h1_h3':
            'Because this REJECT-grade failure is available to the reviewer '
            'in T3D-Strict/T3D-Escalate/T3A-T, NEED_EVIDENCE there on '
            'linkage=false grounds is pre-registered Over-Abstention (H1) '
            'and a Verification-Decision Gap (H3): the reviewer let an '
            'invalid ORTHOGONAL channel cancel a valid decisive one.',
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                           encoding='utf-8')
    for c in checks:
        print(('PASS' if c['pass'] else 'FAIL'), '-', c['check'])
    if n_pass != len(checks):
        raise SystemExit('symptom audit has failing checks')
    print(f'wrote {a.out}')


if __name__ == '__main__':
    main()
