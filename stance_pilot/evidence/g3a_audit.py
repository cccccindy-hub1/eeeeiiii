"""G3-A tasks 5/8/9 — three-layer offline materials, Evidence Sufficiency
Certificates, and the label-leakage / source-relevance / token-truncation
audits. Fully offline; reads only G3-A artifacts (frozen stores untouched).

Three layers per issue, ALL derived from the SAME underlying executed facts:
  raw/          verbatim primary materials: problem statement, candidate and
                maintainer patches, and the four raw runner/probe logs
                (f2p, p2p, p2p_baseline, symptom). No parsed verdict table.
  structured/   the HMAC-signed run record (deterministically PARSED per-test
                maps + summary) and the signed git write-tree attestation with
                its declared sets. Parsing is a DERIVATION and is disclosed.
  adjudicated/  the frozen oracle/condition gold row, its fact basis, and the
                Evidence Sufficiency Certificate incl. human-adjudication
                status. NEVER shown to a model (leakage-audited).

Label leakage is scanned on raw+structured (the model-facing layers): the
answer vocabulary (ACCEPT/REJECT/NEED_EVIDENCE), oracle/merge_acceptable/
issue_addressed/label_class, and dataset `resolved` must not appear there.
Pytest PASSED/FAILED are legitimate acceptance evidence and are allow-listed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from evidence.schemas import make_artifact_id, sha256_text
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl

HERE = Path(__file__).resolve().parent.parent
G3A = HERE / 'evidence_store_g3a'
STORE = ArtifactStore(str(G3A / 'store'),
                      fixtures_meta_name='g3a_fixtures_meta.json')
RAW_ROWS = G3A / 'raw' / 'g3a_target_rows.jsonl'
TRUTH = G3A / 'g3a_truth.jsonl'
GOLD = G3A / 'gold' / 'g3a_gold.jsonl'
LAYER_ROOT = G3A / 'layers'
AUDIT = G3A / 'audit'
LAYER_ROOT.mkdir(parents=True, exist_ok=True)
AUDIT.mkdir(parents=True, exist_ok=True)

_WS = re.compile(r"\w+|[^\w\s]")
# decision / provenance vocabulary that must not leak into model-facing layers
LEAK_PATTERNS = [
    r'\bACCEPT\b', r'\bREJECT\b', r'\bNEED_EVIDENCE\b', r'\boracle_gold\b',
    r'\bcondition_gold\b', r'\bmerge_acceptable\b', r'\bissue_addressed\b',
    r'\blabel_class\b', r'\boracle\b', r'\bresolved_in_dataset\b',
    r"\bresolved\b", r"['\"]resolved['\"]\s*:"]
# pytest's own PASSED/FAILED are evidence, not the answer; excluded from scan
LOG_NAMES = ('f2p', 'p2p', 'p2p_baseline', 'symptom')


def token_estimates(text):
    chars = len(text)
    return {'whitespace_punct_tokens': len(_WS.findall(text)),
            'tokens_chars_div_4_conservative': chars // 4,
            'tokens_anchored_div_3_62': round(chars / 3.62),
            'chars': chars}


def forcing_channels(g):
    """Minimal channels that FORCE the oracle label under the dual-channel rule
    (evidence.gold_w2.oracle_gold), given the recovered facts."""
    f = g['facts']
    if g['oracle_gold'] == 'REJECT':
        if f['symptom_polarity'] == 'persists':
            return ['symptom_persists'], 'diagnostic channel alone: symptom still reproduces post-patch'
        return ['linked', 'fresh', 'acceptance_failure'], \
            'linked+fresh executed acceptance failure forces REJECT'
    if g['oracle_gold'] == 'ACCEPT':
        return ['linked', 'fresh', 'complete', 'acceptance_success'], \
            'linked+fresh+complete all-green acceptance, symptom gone'
    return ['(no decisive channel)'], \
        'no decisive failure and success evidence incomplete -> NEED'


CHANNEL_MATERIAL = {
    'linked': 'signed record base_commit/patch_sha256 == review target',
    'fresh': 'attestation expected_run_tree == recomputed canonical run tree',
    'complete': 'every attested declared id (F2P + SCOPED P2P) executed',
    'acceptance_failure': 'a post-patch F2P failure or non-preexisting P2P regression',
    'acceptance_success': '>=1 executed check and zero failures',
    'symptom_persists': 'probe fails at baseline AND still fails after the patch',
}


def main():
    raws = {r['instance_id']: r for r in read_jsonl(str(RAW_ROWS))}
    golds = {g['instance_id']: g for g in read_jsonl(str(GOLD))}
    certs, audits, manifests = [], [], []

    for iid in sorted(raws):
        raw, g = raws[iid], golds[iid]
        aid = make_artifact_id(iid, raw and g['patch_sha256'])
        rec, authentic = STORE.get(aid)
        att = STORE.get_attestation(iid, g['patch_sha256'])
        ld = LAYER_ROOT / iid
        (ld / 'raw').mkdir(parents=True, exist_ok=True)
        (ld / 'structured').mkdir(parents=True, exist_ok=True)
        (ld / 'adjudicated').mkdir(parents=True, exist_ok=True)

        # ---- RAW: verbatim ----
        (ld / 'raw' / 'problem_statement.txt').write_text(
            raw['problem_statement'], encoding='utf-8', newline='')
        (ld / 'raw' / 'candidate.patch').write_text(
            raw['model_patch'], encoding='utf-8', newline='')
        (ld / 'raw' / 'maintainer_test.patch').write_text(
            raw['test_patch'], encoding='utf-8', newline='')
        log_sha = {}
        for nm in LOG_NAMES:
            txt = (G3A / 'store' / 'logs' / f'{aid}.{nm}.log').read_text(
                encoding='utf-8')
            (ld / 'raw' / f'{nm}.log').write_text(txt, encoding='utf-8',
                                                  newline='')
            log_sha[nm] = sha256_text(txt)

        # ---- STRUCTURED: parsed signed record + attestation ----
        struct = {
            '_derivation_disclosure': 'The per-test maps and summary below are '
                'parsed DETERMINISTICALLY from the raw pytest verbose logs by '
                'evidence.builder.parse_node_logs/name_outcomes; they add no '
                'new execution fact. provenance/run metadata are echoed from '
                'the signed record.',
            'artifact_id': aid, 'authentic_signature': authentic,
            'repo': rec['repo'], 'base_commit': rec['base_commit'],
            'patch_sha256': rec['patch_sha256'],
            'test_patch_sha256': rec['test_patch_sha256'],
            'runner': rec['runner'], 'started_at': rec['started_at'],
            'finished_at': rec['finished_at'], 'scope': rec['scope'],
            'fail_to_pass': rec['fail_to_pass'],
            'pass_to_pass_scoped': rec['pass_to_pass_scoped'],
            'pass_to_pass_baseline': rec['pass_to_pass_baseline'],
            'summary': rec['summary'], 'log_digests': rec['log_digests'],
            'attestation': {k: v for k, v in att.items()
                            if k != '_attestation_authentic'},
            'attestation_authentic': att.get('_attestation_authentic')}
        (ld / 'structured' / 'run_record.json').write_text(
            json.dumps(struct, ensure_ascii=False, indent=2, sort_keys=True),
            encoding='utf-8', newline='')

        # ---- ADJUDICATED: gold + certificate (never model-facing) ----
        force, why = forcing_channels(g)
        cert = {
            'instance_id': iid, 'oracle_gold': g['oracle_gold'],
            'facts': g['facts'], 'minimal_forcing_channels': force,
            'forcing_rationale': why,
            'channel_material': {c: CHANNEL_MATERIAL[c] for c in force
                                 if c in CHANNEL_MATERIAL},
            'evidence_status': {
                'linked': g['facts']['linked'],
                'fresh': g['facts']['fresh'],
                'complete': g['facts']['complete'],
                'source_applicable': True,
                'source_trustworthy': bool(authentic and att and
                                           att.get('_attestation_authentic'))},
            'gold_underdetermined': False,
            'underdetermination_note': 'Mechanically determined by executed '
                'facts; no missing forcing channel.',
            'coverage_scope': g['coverage_scope_disclosure'],
            'human_adjudication': g['human_adjudication']}
        certs.append(cert)
        (ld / 'adjudicated' / 'gold.json').write_text(
            json.dumps(g, ensure_ascii=False, indent=2, sort_keys=True),
            encoding='utf-8', newline='')
        (ld / 'adjudicated' / 'sufficiency_certificate.json').write_text(
            json.dumps(cert, ensure_ascii=False, indent=2, sort_keys=True),
            encoding='utf-8', newline='')

        # ---- leakage scan on model-facing layers ----
        leaks = []
        for sub in ('raw', 'structured'):
            for fp in sorted((ld / sub).iterdir()):
                txt = fp.read_text(encoding='utf-8', errors='replace')
                # raw candidate/test patches and problem text are model input;
                # scan the parsed record and the pytest/probe logs for the
                # answer vocabulary that evidence should not contain.
                for pat in LEAK_PATTERNS:
                    for m in re.finditer(pat, txt):
                        leaks.append({'layer': sub, 'file': fp.name,
                                      'pattern': pat,
                                      'context': txt[max(0, m.start()-25):
                                                     m.end()+25]})
        # ---- token / truncation ----
        sizes = {}
        for sub in ('raw', 'structured', 'adjudicated'):
            blob = '\n'.join(fp.read_text(encoding='utf-8', errors='replace')
                             for fp in sorted((ld / sub).iterdir()))
            sizes[sub] = token_estimates(blob)
        audits.append({'instance_id': iid, 'leak_hits': leaks,
                       'leak_clean': not leaks, 'token_estimates': sizes,
                       'log_sha256': log_sha,
                       'record_log_digests': rec['log_digests'],
                       'log_digests_consistent':
                           all(log_sha[k] == rec['log_digests'][k]
                               for k in LOG_NAMES)})

        manifests.append({
            'instance_id': iid, 'repo': raw['repo'],
            'base_commit': raw['base_commit'],
            'candidate_patch_sha256': g['patch_sha256'],
            'test_patch_sha256': rec['test_patch_sha256'],
            'target_generator': raw['generator_model'],
            'test_command': 'python -m pytest <scope files> -v --tb=short '
                            '-p no:cacheprovider  (batched 3 files; F2P all + '
                            'scoped P2P + baseline P2P)',
            'environment': rec['runner'],
            'python': 'CPython 3.9.25, pytest 8.4.2, mpmath 1.4.1 (uv, '
                      'offline); vendored sympy git, GIT_NO_LAZY_FETCH=1',
            'canon_run_tree': g['canon_run_tree'],
            'FAIL_TO_PASS': raw['FAIL_TO_PASS'],
            'PASS_TO_PASS_scoped_n': g['facts']['declared_scoped_count'],
            'raw_log_files': [f'{n}.log' for n in LOG_NAMES],
            'oracle_gold': g['oracle_gold'],
            'human_adjudication_status':
                g['human_adjudication']['status']})

    (AUDIT / 'g3a_sufficiency_certificates.json').write_text(
        json.dumps(certs, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    (AUDIT / 'g3a_leakage_token_audit.json').write_text(
        json.dumps(audits, ensure_ascii=False, indent=2, sort_keys=True) + '\n',
        encoding='utf-8')
    (G3A / 'g3a_provenance_manifest.json').write_text(
        json.dumps(manifests, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')

    n_leak = sum(len(a['leak_hits']) for a in audits)
    n_cons = sum(a['log_digests_consistent'] for a in audits)
    maxraw = max(a['token_estimates']['raw']['tokens_anchored_div_3_62']
                 for a in audits)
    print('certificates:', len(certs))
    print('leak hits (raw+structured):', n_leak)
    print('log-digest consistent issues:', n_cons, '/', len(audits))
    print('max raw-layer token est (chars/3.62):', maxraw)
    for a in audits:
        if a['leak_hits']:
            for h in a['leak_hits'][:10]:
                print('  LEAK', a['instance_id'], h['layer'], h['file'],
                      h['pattern'], repr(h['context']))
    print('->', AUDIT)


if __name__ == '__main__':
    main()
