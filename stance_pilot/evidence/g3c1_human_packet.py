"""G3-C.1 task 8 — SHIP-READY blind gold-review packet for a SECOND independent
HUMAN annotator over the 8 NEW pilot issues. ZERO API. Reads the built G3-C.1
store/raw (frozen at this gate) and writes ONLY under
evidence_store_g3c1/human_annotation/.

Blindness is identical to the frozen G3-C.0 protocol: each packet carries only
the upstream evidence a human needs to judge acceptability (problem statement,
candidate patch, maintainer test_patch, declared test ids, raw f2p / scoped p2p
/ base-commit p2p / issue-symptom logs). It contains NO model verdict, NO
annotator-1 gold/oracle/certificate, and NO issue number in the blinded folder
name; a sealed P-id -> instance_id mapping is held separately.

Status is PENDING and all G3-C.1 gold stays PROVISIONAL until a real
independent human returns labels and any disagreement is arbitrated by a third
senior human. The AI that built this gate is never annotator2 or arbiter.

    uv run --offline --python 3.9 -m evidence.g3c1_human_packet
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re

from evidence import g3c1_common as C
from evidence.store import ArtifactStore

RUBRIC = [
    'ACCEPT: every declared FAIL_TO_PASS test transitions fail(at base) -> '
    'pass(after patch) AND no declared in-scope PASS_TO_PASS test regresses '
    '(passed/xfail/skipped at base, bad after patch). SCOPED acceptability: '
    'only the attested scoped P2P subset was executed locally; the full '
    'dataset P2P suite was not run for this pilot.',
    'REJECT: the executed CI shows at least one decisive, APPLICABLE failure: '
    'a declared F2P still fails after the patch, OR a scoped P2P regression '
    'is present. Separate genuine failures from environment/pre-existing '
    'fails (bad at base too -> not a regression) and from xfail/flaky/self-'
    'added-test traps; justify applicability in the reason field.',
    'NEEDS_REVIEW: genuinely undecidable from the supplied evidence '
    '(ambiguous applicability, uninterpretable log, suspected flake). Do not '
    'force ACCEPT/REJECT.',
]
TEMPLATE_HEADER = [
    'packet_id', 'label (ACCEPT/REJECT/NEEDS_REVIEW)',
    'decisive_failing_test_ids (semicolon-separated; or NONE)',
    'applicability_reason (1-4 sentences)',
    'any_xfail_flaky_self_added_concern (yes/no + note)',
    'confidence (high/medium/low)', 'annotator_id', 'date']


def main():
    truths = sorted(C.read_jsonl(C.TRUTH), key=lambda r: r['instance_id'])
    iids = [t['instance_id'] for t in truths]
    if len(iids) != C.MAX_NEW_ISSUES:
        raise SystemExit(f'expected {C.MAX_NEW_ISSUES} built issues, got '
                         f'{len(iids)}')
    target = {r['instance_id']: r
              for r in C.read_jsonl(C.OUT_RAW / 'g3c1_target_rows.jsonl')}
    aid_by_iid = {t['instance_id']: t['artifact_id'] for t in truths}
    all_issue_numbers = [i.split('-')[-1] for i in iids]

    rng = random.Random(C.G3C1_HUMAN_BLIND_SEED)
    blinded = list(iids)
    rng.shuffle(blinded)
    mapping = {f'P{i+1:02d}': iid for i, iid in enumerate(blinded)}

    store = ArtifactStore(str(C.OUT_STORE),
                          fixtures_meta_name='g3c1_fixtures_meta.json')
    pkg = C.OUT_HUMAN / 'packets'
    pkg.mkdir(parents=True, exist_ok=True)
    manifest_rows = []

    for pid, iid in mapping.items():
        row = target[iid]
        aid = aid_by_iid[iid]
        pdir = pkg / pid
        pdir.mkdir(exist_ok=True)
        contents = {
            '01_problem_statement.txt': row['problem_statement'],
            '02_candidate_patch.diff': row['model_patch'],
            '03_maintainer_test_patch.diff': row['test_patch'],
            '04_declared_test_ids.json': json.dumps(
                {'FAIL_TO_PASS': row['FAIL_TO_PASS'],
                 'PASS_TO_PASS_scoped_declared_note':
                     'P2P executed subset is scoped to test_patch files and '
                     'tests/ adjacent to changed code files; see 06 log',
                 'PASS_TO_PASS_dataset_list': row['PASS_TO_PASS']}, indent=2)}
        for logname, fn in (('f2p', '05_ci_fail_to_pass.log'),
                            ('p2p', '06_ci_pass_to_pass_scoped.log'),
                            ('p2p_baseline',
                             '07_ci_pass_to_pass_base_commit.log'),
                            ('symptom', '08_issue_symptom_probe.log')):
            lp = C.OUT_STORE / 'logs' / f'{aid}.{logname}.log'
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
            'SCOPE NOTE: this local pilot executed only the scoped P2P subset\n'
            '(06), not the entire dataset P2P list in 04; judge scoped\n'
            'acceptability and say so in your reason if it matters.\n\n'
            'Apply the rubric in 00_annotator_protocol.md and enter your label\n'
            'in annotator2_labels.csv (one row per packet).\n')
        contents = {'00_README.txt': readme, **contents}
        for fn, text in contents.items():
            (pdir / fn).write_text(text, encoding='utf-8')

        num = iid.split('-')[-1]
        self_refs = sorted({fn for fn, text in contents.items()
                            if re.search(r'(?<![\d])' + num + r'(?![\d])',
                                         text)})
        any_known_refs = sorted({
            fn for fn, text in contents.items()
            for other in all_issue_numbers
            if re.search(r'(?<![\d])' + other + r'(?![\d])', text)})
        manifest_rows.append({
            'packet_id': pid,
            'instance_id_sealed': 'see SEALED_packet_mapping.json',
            'n_files': len(contents),
            'artifact_id_used_for_logs': aid,
            'files_self_referencing_this_issue_number': self_refs,
            'files_referencing_any_pilot_issue_number': any_known_refs,
            'identity_blinding': 'PARTIAL — folder/mapping blinded but '
            'verbatim evidence may quote the upstream issue number',
            'packet_sha256_of_concatenated_filenames_and_bytes':
                hashlib.sha256(
                    ''.join(f'{k}:{len(v)}' for k, v in
                            sorted(contents.items())).encode()).hexdigest()})

    protocol_md = ['# GroundedReview — Independent Human Annotator Protocol',
                   '## Gate G3-C.1 local pilot (8 new issues)', '',
                   '## Role and independence',
                   'You are annotator #2, independent of the model pipeline.',
                   'Do not use any LLM and do not consult the pipeline author;',
                   'your label must be your own reading of the frozen CI.',
                   '', '## Decision rubric']
    protocol_md += [f'{i+1}. {r}' for i, r in enumerate(RUBRIC)]
    protocol_md += [
        '', '## Procedure',
        '1. Work packets P01..P08 in folder order; do not infer identity.',
        '2. Read 01-04, then compare after-patch logs (05-06) to the base '
        'log (07).',
        '3. Record the exact decisive failing test id(s) and applicability.',
        '4. Mark NEEDS_REVIEW rather than guessing.',
        '', '## Disagreement and adjudication',
        '- Raw agreement and Cohen kappa are computed against annotator #1 '
        'after unsealing.',
        '- Any ACCEPT/REJECT mismatch, or any NEEDS_REVIEW, goes to a THIRD '
        'senior human arbiter who sees both labels but no model output.',
        '- Every changed label keeps annotator1/annotator2/arbiter labels and '
        'the reason; labels are never silently overridden.',
        '', '## Status',
        'PENDING: no independent human labels exist yet. Gold remains '
        'PROVISIONAL until labels + arbitration are returned.']
    (C.OUT_HUMAN / '00_annotator_protocol.md').write_text(
        '\n'.join(protocol_md) + '\n', encoding='utf-8')

    buf = io.StringIO(newline='')
    w = csv.writer(buf)
    w.writerow(TEMPLATE_HEADER)
    for i in range(len(iids)):
        w.writerow([f'P{i+1:02d}', '', '', '', '', '', '', ''])
    (C.OUT_HUMAN / 'annotator2_labels.csv').write_text(
        buf.getvalue(), encoding='utf-8')

    sealed = {'blind_seed': C.G3C1_HUMAN_BLIND_SEED,
              'do_not_give_to_annotator2': True,
              'mapping_packet_to_instance': mapping}
    (C.OUT_HUMAN / 'SEALED_packet_mapping.json').write_bytes(
        C.canonical_bytes(sealed))

    protocol = {
        'document': 'G3-C.1 task 8: ship-ready second-human-annotator blind '
                    'gold-review package for the 8 new pilot issues',
        'design_version': C.G3C1_DESIGN_VERSION,
        'api_calls_made': 0,
        'status': 'PENDING — no independent human labels obtained',
        'gold_tier': 'PROVISIONAL',
        'blind_seed': C.G3C1_HUMAN_BLIND_SEED,
        'n_packets': len(mapping),
        'what_is_excluded_from_packets': [
            'issue number / upstream id in blinded folder names and the '
            'sealed mapping (held separately)',
            'all model verdicts and reasoning',
            "annotator-1 oracle/condition gold and sufficiency certificates",
            'freshness/coverage/noninterference/mock analysis outputs'],
        'blinding_limitation': 'IDENTITY blinding is PARTIAL: folder names '
            'and mapping are blinded, but verbatim patch/problem text may '
            'quote the upstream issue number; evidence is not rewritten '
            'because doing so would corrupt the adjudication target.',
        'rubric': RUBRIC,
        'arbitration': 'third senior human; never an LLM or the pipeline '
                       'author; all three labels + reason retained',
        'deliverables': ['00_annotator_protocol.md', 'annotator2_labels.csv',
                         'packets/P01..P08 (blinded)',
                         'SEALED_packet_mapping.json (held by study team)'],
        'packet_manifest': sorted(manifest_rows, key=lambda r: r['packet_id']),
        'gold_authority': C.GOLD_AUTHORITY,
    }
    dest = C.OUT_HUMAN / 'g3c1_human_annotation_package.json'
    dest.write_bytes(C.canonical_bytes(protocol))
    print('packets built:', len(mapping), '| status PENDING/PROVISIONAL')
    print('->', dest.relative_to(C.HERE))


if __name__ == '__main__':
    main()
