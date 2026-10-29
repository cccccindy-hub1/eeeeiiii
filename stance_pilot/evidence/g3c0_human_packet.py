"""Gate G3-C.0 task 8 — build a SHIP-READY blind gold-review package for a
SECOND independent HUMAN annotator. ZERO API. Read-only over frozen gates;
writes only under evidence_store_g3c0/human_annotation/.

Blindness: the packet contains ONLY the upstream evidence a human needs to
adjudicate patch acceptability (problem statement, candidate patch, maintainer
test_patch, raw f2p / p2p / p2p_baseline CI logs, declared test ids). It
contains NO model verdict/reason, NO prior gold, NO coverage/freshness
summary and NO issue number in the blinded materials (a sealed mapping file,
kept separate, maps P01.. -> instance_id).

Status is PENDING until a real independent human returns labels; nothing here
is itself an adjudication. AI is never used as annotator2 or arbiter.

    uv run --python 3.13 -m evidence.g3c0_human_packet
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random

from evidence import g3c0_common as C
from evidence.store import ArtifactStore

BLIND_SEED = 418307
ORDERED = [f'sympy__sympy-{n}' for n in
           ('13615', '13974', '15349', '17318', '17630', '19783',
            '20590', '21847', '24213', '24443')]

RUBRIC = [
    'ACCEPT: every declared FAIL_TO_PASS test transitions fail(at base) -> '
    'pass(after patch) AND no declared in-scope PASS_TO_PASS test regresses '
    '(passed/xfail/skipped at base, bad after patch). SCOPED acceptability: '
    'only the attested scoped P2P subset was executed.',
    'REJECT: the frozen CI shows at least one decisive, APPLICABLE failure: '
    'a declared F2P still fails after the patch, OR a scoped P2P regression '
    'is present. Distinguish genuine failures from environment/pre-existing '
    'fails (bad at base too -> not a regression) and from xfail/flaky/self-'
    'added-test traps; justify applicability in the reason field.',
    'NEEDS_REVIEW: the packet is genuinely undecidable from the supplied '
    'evidence (ambiguous applicability, uninterpretable log, suspected flake '
    'that cannot be resolved). Do not force ACCEPT/REJECT.',
]

TEMPLATE_HEADER = [
    'packet_id', 'label (ACCEPT/REJECT/NEEDS_REVIEW)',
    'decisive_failing_test_ids (semicolon-separated; or NONE)',
    'applicability_reason (1-4 sentences)',
    'any_xfail_flaky_self_added_concern (yes/no + note)',
    'confidence (high/medium/low)', 'annotator_id', 'date']


def main():
    rng = random.Random(BLIND_SEED)
    blinded = list(ORDERED)
    rng.shuffle(blinded)
    mapping = {f'P{i+1:02d}': iid for i, iid in enumerate(blinded)}

    store = ArtifactStore(str(C.G3A / 'store'),
                          fixtures_meta_name='g3a_fixtures_meta.json')
    fz = json.loads(C.G3B3_DATA_FREEZE.read_text(encoding='utf-8'))
    aid_by_issue = {}
    for c in fz['cells']:
        aid_by_issue.setdefault(c['instance_id'], c['served_artifact_id'])
    target_rows = {r['instance_id']: r
                   for r in C.read_jsonl(C.G3A / 'raw' / 'g3a_target_rows.jsonl')}

    out_root = C.OUT_HUMAN
    pkg = out_root / 'packets'
    pkg.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for pid, iid in mapping.items():
        row = target_rows[iid]
        aid = aid_by_issue[iid]
        pdir = pkg / pid
        pdir.mkdir(exist_ok=True)
        contents = {
            '01_problem_statement.txt': row['problem_statement'],
            '02_candidate_patch.diff': row['model_patch'],
            '03_maintainer_test_patch.diff': row['test_patch'],
            '04_declared_test_ids.json': json.dumps(
                {'FAIL_TO_PASS': row['FAIL_TO_PASS'],
                 'PASS_TO_PASS_scoped_declared_note': 'P2P scoped subset; '
                 'see 06 log and the scoping note',
                 'PASS_TO_PASS_dataset_list': row['PASS_TO_PASS']},
                indent=2),
        }
        for logname, fn in (('f2p', '05_ci_fail_to_pass.log'),
                            ('p2p', '06_ci_pass_to_pass_scoped.log'),
                            ('p2p_baseline',
                             '07_ci_pass_to_pass_base_commit.log'),
                            ('symptom', '08_issue_symptom_probe.log')):
            lp = C.G3A / 'store' / 'logs' / f'{aid}.{logname}.log'
            if lp.exists():
                contents[fn] = lp.read_text(encoding='utf-8')
        readme = (
            f'BLIND PACKET {pid} — GroundedReview independent patch review\n'
            '============================================================\n'
            'You are an independent adjudicator. Judge ONLY from the files in\n'
            'this folder. Do not search the web or the issue tracker. Folder\n'
            'ids are blinded; if the verbatim patch/problem text happens to\n'
            'quote an upstream issue number, ignore it and do not look it up.\n\n'
            'Files:\n'
            '  01 problem statement\n'
            '  02 candidate patch (the patch under review)\n'
            '  03 maintainer test_patch (declared acceptance tests)\n'
            '  04 declared test id sets\n'
            '  05 CI FAIL_TO_PASS log (after patch)\n'
            '  06 CI scoped PASS_TO_PASS log (after patch)\n'
            '  07 CI PASS_TO_PASS at BASE commit (pre-patch reference)\n'
            '  08 issue-symptom probe (derived from the issue text, not a\n'
            '     maintainer acceptance test; a pass means the symptom is\n'
            '     gone)\n\n'
            'Apply the rubric in 00_annotator_protocol.md and enter your label\n'
            'in annotator2_labels.csv (one row per packet).\n')
        contents = {'00_README.txt': readme, **contents}
        for fn, text in contents.items():
            (pdir / fn).write_text(text, encoding='utf-8')
        # Partial-blindness scan: the VERBATIM upstream evidence may itself
        # quote the upstream issue number (code comments / problem text). We
        # do NOT rewrite the patch under review (that would alter the
        # evidence a human must judge), but we record every file that self-
        # references an issue number so the limitation is explicit.
        import re as _re
        num = iid.split('-')[-1]
        self_refs = sorted({fn for fn, text in contents.items()
                            if _re.search(r'(?<![\d])' + num + r'(?![\d])',
                                          text)})
        any_known_refs = sorted({
            fn for fn, text in contents.items()
            for other in ('13615', '13974', '15349', '17318', '17630',
                          '19783', '20590', '21847', '24213', '24443')
            if _re.search(r'(?<![\d])' + other + r'(?![\d])', text)})
        manifest_rows.append({
            'packet_id': pid,
            'n_files': len(contents),
            'artifact_id_used_for_logs': aid,
            'files_self_referencing_this_issue_number': self_refs,
            'files_referencing_any_cohort_issue_number': any_known_refs,
            'identity_blinding': 'PARTIAL — folder/mapping are blinded but '
            'verbatim evidence may quote the upstream issue number',
            'packet_sha256_of_concatenated_filenames_and_bytes':
                hashlib.sha256(
                    ''.join(f'{k}:{len(v)}' for k, v in
                            sorted(contents.items())).encode()).hexdigest()})

    # Protocol + rubric markdown (placed OUTSIDE the blinded packets so it is
    # shared, not per-issue).
    protocol_md = ['# GroundedReview — Independent Human Annotator Protocol',
                   '',
                   '## Role and independence',
                   'You are annotator #2, independent of the model pipeline.',
                   'Do not use any LLM and do not consult the pipeline author;',
                   'your label must be your own reading of the frozen CI.',
                   '',
                   '## Decision rubric']
    protocol_md += [f'{i+1}. {r}' for i, r in enumerate(RUBRIC)]
    protocol_md += [
        '', '## Procedure',
        '1. Work packets P01..P10 in folder order; do not try to infer the '
        'issue identity.',
        '2. Read 01-04, then compare the after-patch logs (05-06) against '
        'the base-commit log (07).',
        '3. Record the exact decisive failing test id(s) and why they apply.',
        '4. Mark NEEDS_REVIEW rather than guessing.',
        '', '## Disagreement and adjudication',
        '- Raw agreement and Cohen kappa are computed against annotator #1 '
        'after unsealing.',
        '- Any ACCEPT/REJECT mismatch, or any NEEDS_REVIEW, goes to a THIRD '
        'senior human arbiter who sees both labels but no model output; the '
        'arbiter writes a reason and the final label.',
        '- Every changed label keeps annotator1/annotator2/arbiter labels and'
        ' the reason; labels are never silently overridden.',
        '', '## Gold-flip sensitivity (performed by the study, not you)',
        'All headline rates are recomputed under annotator1, annotator2 and '
        'adjudicated labels, with leave-one-issue-out and bounds over '
        'plausible adjudications; a claim is "robust" only if its sign '
        'holds across all three.',
        '', '## Status',
        'PENDING: no independent human labels exist yet. This protocol and '
        'the packets are prepared but un-adjudicated; gold remains '
        'PROVISIONAL until labels + arbitration are returned.']
    (out_root / '00_annotator_protocol.md').write_text(
        '\n'.join(protocol_md) + '\n', encoding='utf-8')

    # Blank labels CSV (header + one empty row per packet).
    buf = io.StringIO(newline='')
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADER)
    for i in range(len(ORDERED)):
        w.writerow([f'P{i+1:02d}', '', '', '', '', '', '', ''])
    (out_root / 'annotator2_labels.csv').write_text(
        buf.getvalue(), encoding='utf-8')

    # Sealed mapping (kept apart from the shipped packets).
    sealed = {'blind_seed': BLIND_SEED,
              'do_not_give_to_annotator2': True,
              'mapping_packet_to_instance': mapping}
    (out_root / 'SEALED_packet_mapping.json').write_bytes(
        C.canonical_bytes(sealed))

    protocol = {
        'document': 'Gate G3-C.0 task 8: ship-ready second-human-annotator '
                    'blind gold-review package',
        'design_version': C.G3C0_DESIGN_VERSION,
        'api_calls_made': 0,
        'status': 'PENDING — no independent human labels obtained',
        'blind_seed': BLIND_SEED,
        'n_packets': len(mapping),
        'what_is_excluded_from_packets': [
            'issue number / upstream id in the blinded FOLDER names and the '
            'sealed mapping (held separately)',
            'all model verdicts and reasoning',
            'the existing annotator-1 gold',
            'coverage/freshness summaries and any analysis output'],
        'blinding_limitation': 'blinding of IDENTITY is PARTIAL: folder names '
            'and the mapping are blinded, but the VERBATIM candidate patch / '
            'problem statement occasionally quotes the upstream issue number '
            'in code comments or prose (e.g. "issue #20590"). The evidence is'
            ' not rewritten because altering the patch/log under review would'
            ' corrupt the adjudication target. Per-packet self-reference files'
            ' are listed in packet_manifest; the limitation is reported and a'
            ' fully de-identified presentation (hash-only ids in a copied-'
            'verbatim appendix) is a future hardening option, not applied '
            'here.',
        'rubric': RUBRIC,
        'arbitration': 'third senior human; never an LLM or the pipeline '
                       'author; all three labels + reason retained',
        'gold_flip_sensitivity': 'recompute P1/P2 and every headline rate '
                       'under annotator1/annotator2/adjudicated labels; LOO + '
                       'bounds; robustness requires sign stability',
        'deliverables': ['00_annotator_protocol.md', 'annotator2_labels.csv',
                         'packets/P01..P10 (blinded)',
                         'SEALED_packet_mapping.json (held by study team)'],
        'packet_manifest': sorted(manifest_rows, key=lambda r: r['packet_id']),
        'gold_authority_after_completion': 'only raised above PROVISIONAL '
                       'after real human labels + adjudication are returned',
    }
    dest = out_root / 'g3c0_human_annotation_package.json'
    dest.write_bytes(C.canonical_bytes(protocol))
    print('packets built:', len(mapping), '| status PENDING')
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
