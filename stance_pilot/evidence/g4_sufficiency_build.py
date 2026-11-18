"""G4 Evidence-Sufficiency 2x2 — ZERO-API fixed-bundle builder + identifiability gate.

Version: g4-sufficiency-iv-v1.1 (G4_PREREGISTRATION_v1.md +
G4_PREREGISTRATION_ADDENDUM_v1.1.md; the addendum governs where they differ).

Strictly zero-cost:
  * 0 model API calls, $0, no network, no new issues, no git commit;
  * imports the FROZEN evidence modules/stores READ-ONLY (nothing is written
    into evidence_store_g3a / evidence_store_g3c1);
  * renders, per 18 frozen issues x 4 cells (A/B/C/D), the deterministic
    surface: system message, first user message, ONE unified tool interface,
    and a FIXED ordered transcript of every tool call a reviewer can make with
    its exact content-controlled response;
  * hashes every payload (sha256), expands the 72 bundles x 2 models into a
    144-slot pre-registered manifest (Latin order seed 20261102), and runs
    gates G1..G5 plus G6 Interaction Parity.

Factors (addendum A1):
  O  decisive acceptance outcomes            C/D presented, A/B blocked (403)
  M  fc_attestation = Freshness/Coverage
     ATTESTATION availability                B/D adjudicated, A/C withheld
  Linkage held CONSTANT across all four cells (never manipulated).

WITHHELD is UNKNOWN/null, never FALSE (addendum A2).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from evidence import prompts as P
from evidence import views
from evidence import g3b2_freshness as F
from evidence.store import ArtifactStore
from evidence.schemas import make_artifact_id
from evidence.g3c0_projection_v2 import project_diagnostic_v2
from evidence.g3b2_common import PROTOCOL_VERSION as G3A_PROTOCOL
from evidence.g3c1_common import G3C1_PROTOCOL_VERSION as G3C1_PROTOCOL

HERE = Path(__file__).resolve().parent
STANCE = HERE.parent
OUT = STANCE / 'evidence_store_g4_sufficiency'

G4_VERSION = 'g4-sufficiency-iv-v1.1'
G4_ORDER_SEED = 20261102
MODELS = ('deepseek-flash', 'gpt-4.1-mini')
CELLS = ('A', 'B', 'C', 'D')

TEMPERATURE = 0
COMPLETION_CAP = 8192
MAX_TOOL_TURNS = 8
MAX_MODEL_CALLS_PER_CELL = 12
RETRIES_PER_CELL = 0
TOTAL_BUDGET_USD = 2.00

CLAIM = 'This fix is correct and all relevant tests pass.'
OPAQUE_TIME_TOKEN = 'g4-withheld-timestamp-0000000000'
ATTEST_MARKER_W = 'withheld_on_this_surface'
ATTEST_MARKER_A = 'adjudicated_on_this_surface'

# Neutral prose used ONLY to length-match a withheld envelope to its
# adjudicated twin (addendum A2 "positive-length, matched neutral sentence").
# It deliberately carries no fresh/complete/stale/missing verdict vocabulary.
_NEUTRAL_FILLER = (
    'This review surface does not adjudicate the attestation; it reports the '
    'state UNKNOWN and provides no tree comparison and no declared-versus-run '
    'set comparison, so the point can neither support nor oppose a decision. ')

# ---------------------------------------------------------------------------
# Cohort loading (read-only over the two frozen stores)
# ---------------------------------------------------------------------------
COHORTS = [
    dict(tag='g3c1', root=STANCE / 'evidence_store_g3c1',
         raw='raw/g3c1_target_rows.jsonl', truth='g3c1_truth.jsonl',
         gold=('gold/g3c1_oracle_gold.jsonl', 'oracle_gold'),
         meta='g3c1_fixtures_meta.json',
         restage='audit/g3c1_freshness_recompute.json',
         protocol=G3C1_PROTOCOL),
    dict(tag='g3a', root=STANCE / 'evidence_store_g3a',
         raw='raw/g3a_target_rows.jsonl', truth='g3a_truth.jsonl',
         gold=('gold/g3a_gold.jsonl', 'oracle_gold'),
         meta='g3a_fixtures_meta.json',
         restage='audit/g3a_freshness_recompute.json',
         protocol=G3A_PROTOCOL),
]


def _read_jsonl(p):
    return [json.loads(line) for line in Path(p).read_text(
        encoding='utf-8').splitlines() if line.strip()]


def load_issues():
    issues, stores = [], {}
    for c in COHORTS:
        store = ArtifactStore(str(c['root'] / 'store'),
                              fixtures_meta_name=c['meta'])
        stores[c['tag']] = store
        raws = {r['instance_id']: r
                for r in _read_jsonl(c['root'] / c['raw'])}
        truths = {t['instance_id']: t
                  for t in _read_jsonl(c['root'] / c['truth'])}
        golds = {g['instance_id']: g
                 for g in _read_jsonl(c['root'] / c['gold'][0])}
        cache = {x['instance_id']: x
                 for x in json.loads((c['root'] / c['restage'])
                                     .read_text(encoding='utf-8'))['issues']}
        for iid in sorted(raws):
            raw, truth, gold = raws[iid], truths[iid], golds[iid]
            patch_sha = truth['patch_sha256']
            aid = make_artifact_id(iid, patch_sha)
            got = store.get(aid)
            if got is None:
                raise SystemExit(f'missing artifact {aid}')
            rec, authentic = got
            if not authentic:
                raise SystemExit(f'inauthentic artifact {iid}')
            att = store.get_attestation(iid, patch_sha)
            if att is None or not att.get('_attestation_authentic'):
                raise SystemExit(f'bad attestation {iid}')
            lp = truth.get('label_provenance', {})
            symptom = {'pre_patch_passed':
                       lp.get('symptom_pre_patch_passed'),
                       'post_patch_passed':
                       lp.get('symptom_post_patch_passed')}
            logs = {n: (store.root / 'logs' / f'{aid}.{n}.log')
                    .read_text(encoding='utf-8')
                    for n in ('f2p', 'p2p', 'p2p_baseline', 'symptom')}
            issues.append(dict(
                cohort=c['tag'], iid=iid, raw=raw, truth=truth, gold=gold,
                rec=rec, att=att, aid=aid, symptom=symptom, logs=logs,
                restaged_tree=cache[iid]['recomputed_run_tree'],
                protocol=c['protocol'], store=store,
                base_commit=truth['base_commit'], patch_sha=patch_sha,
                oracle=gold[c['gold'][1]]))
    if len(issues) != 18:
        raise SystemExit(f'expected 18 issues, got {len(issues)}')
    return issues


# ---------------------------------------------------------------------------
# Homogeneous prompt scaffolding (identical across cells; only block + the two
# registered policy paragraphs vary)
# ---------------------------------------------------------------------------
G4_SYSTEM = (
    'You are an independent code reviewer. Return a single JSON object as your '
    'final message.\n\n'
    'Evidence-surface semantics (G4 protocol): freshness and coverage '
    'ATTESTATIONS are three-valued. An adjudicated attestation reports the '
    'independently verified state; a WITHHELD attestation is UNKNOWN. UNKNOWN '
    'is a withheld state: it is not a negative verdict, it does not establish '
    'staleness, a tree mismatch, or an incomplete declared set, and it can '
    'neither support nor refute an ACCEPT or a REJECT. Linkage framing is held '
    'constant on every surface. Ground truth about mergeability is never given.')

O_WORDING_BLOCKED = (
    '\n\nOUTCOME POLICY: decisive maintainer acceptance-test outcomes '
    '(FAIL_TO_PASS / PASS_TO_PASS verdicts) are BLOCKED on this surface. '
    'Requests for the f2p, p2p, or baseline run logs return HTTP 403, and no '
    'tool exposes pass/fail acceptance verdicts. The issue-derived symptom '
    'probe and the symptom reproduction log remain available to you.')
O_WORDING_PRESENTED = (
    '\n\nOUTCOME POLICY: decisive maintainer acceptance-test outcomes '
    '(FAIL_TO_PASS / PASS_TO_PASS verdicts) are PRESENTED on this surface. '
    'Requests for the f2p, p2p, or baseline run logs return HTTP 200 with the '
    'maintainer verdict columns. The issue-derived symptom probe and the '
    'symptom reproduction log are also available to you.')

M_WORDING_ADJUDICATED = (
    '\n\nFRESHNESS / COVERAGE ATTESTATIONS (adjudicated on this surface): the '
    'verification service has independently adjudicated the freshness and '
    'declared-set coverage attestations for THIS patch and commit triple. '
    'fresh=TRUE means the signed run tree equals the independently re-derived '
    'canonical commit tree; coverage complete=TRUE means every '
    'maintainer-declared acceptance and scoped regression check was actually '
    'executed. These attestations cover provenance and completeness only; '
    'they report no pass/fail outcomes, which stay governed by the outcome '
    'policy above. Read them through the tools before trusting the record.')
M_WORDING_WITHHOLD = (
    '\n\nFRESHNESS / COVERAGE ATTESTATIONS (withheld on this surface): the '
    'freshness and declared-set coverage attestations are NOT adjudicated on '
    'this review surface. Their tool responses carry the marker '
    'attestation="' + ATTEST_MARKER_W + '" and the state UNKNOWN: this is '
    'neither fresh=FALSE nor coverage=FALSE, gives no run-tree or '
    'declared/executed set comparison, and neither supports nor refutes an '
    'ACCEPT or a REJECT. Do not treat UNKNOWN as staleness or incompleteness; '
    'decide using only the evidence this surface actually provides.')


def _clone(o):
    return json.loads(json.dumps(o))


def _mark(disp, marker):
    """Attach the G4 attestation-availability marker (key parity A/B C/D)."""
    disp.setdefault('summary', {})['attestation'] = marker
    disp.setdefault('scope', {})['attestation'] = marker
    return disp


def _opaque_timestamps(disp):
    disp['started_at'] = OPAQUE_TIME_TOKEN
    disp['finished_at'] = OPAQUE_TIME_TOKEN
    return disp


def diagnostic_withheld_display(it):
    """Cell A: frozen tier-D v2 projection, then every F/C-recomputable cue is
    moved to UNKNOWN/null: declared scheduled totals, scoped file list, run
    timestamps. Outcomes were already removed by the frozen D/v2 projection."""
    disp = project_diagnostic_v2(views.display_for_tier(
        it['store'], it['rec'], it['iid'], it['patch_sha'], 'D'))
    disp['summary']['f2p_total'] = None
    disp['summary']['p2p_total'] = None
    disp['scope']['p2p_scoped_files'] = None
    disp.pop('run_tree', None)
    _opaque_timestamps(disp)
    return _mark(disp, ATTEST_MARKER_W)


def diagnostic_adjud_display(it):
    """Cell B: the frozen tier-D v2 record exactly as T3D-Strict serves it
    (real declared counts, real timestamps), plus the G4 marker for key
    parity with cell A."""
    disp = project_diagnostic_v2(views.display_for_tier(
        it['store'], it['rec'], it['iid'], it['patch_sha'], 'D'))
    return _mark(disp, ATTEST_MARKER_A)


def acceptance_display(it, withheld: bool):
    """C/D: identical neutralized tier-A record (decisive O intact). For the
    withheld cell the only changes are the run timestamps (a residual
    freshness cue) and the marker; the f2p/p2p outcome maps, passed counts,
    and failing/regressed id lists stay byte-identical to the adjudicated
    cell so decisive O is held fixed across the M toggle."""
    disp = views.display_for_tier(
        it['store'], it['rec'], it['iid'], it['patch_sha'], 'A')
    disp.pop('run_tree', None)
    if withheld:
        _opaque_timestamps(disp)
        return _mark(disp, ATTEST_MARKER_W)
    return _mark(disp, ATTEST_MARKER_A)


def diagnostic_block_withheld(artifact, symptom):
    """Cell A static block: frozen diagnostic line structure, with the
    attestation-derived scheduled counts/file count rendered as UNKNOWN and
    timestamps already normalized on `artifact`."""
    scope = artifact.get('scope', {}) or {}
    lines = [
        'TEST ARTIFACT (DIAGNOSTIC tier; linkage not yet verified):',
        '  Evidence in this record is limited to reproduction/regression-check metadata.',
        '  Maintainer acceptance-test outcomes are intentionally NOT included.',
    ] + views._identity_lines(artifact)
    lines += [
        '  scope:',
        f"    rule: {scope.get('rule', 'n/a')}",
        '    scoped test files: UNKNOWN (coverage attestation withheld)',
        '    acceptance tests scheduled by maintainers: UNKNOWN (coverage '
        'attestation withheld; outcomes withheld)',
        '    scoped regression checks scheduled: UNKNOWN (coverage '
        'attestation withheld; verdicts withheld)',
    ]
    pre = symptom.get('pre_patch_passed')
    post = symptom.get('post_patch_passed')
    present_before = ('yes' if pre is False else 'no' if pre is True else 'n/a')
    reproduces_after = ('yes' if post is False else 'no' if post is True else 'n/a')
    lines.append('  issue-reproduction probe (derived from the issue text, not the '
                 'maintainer test suite; a passing probe means the symptom is GONE):')
    lines.append(f'    issue symptom present before patch: {present_before}')
    lines.append(f'    issue symptom reproduces after patch: {reproduces_after}')
    lines.append('  NOTE: a reproduced/removed symptom is NOT proof of merge '
                 'acceptability; acceptance tests and regression verdicts remain to be '
                 'checked or independently sought.')
    return '\n'.join(lines)


def render_surface(it, cell):
    """Return (artifact_json_dict, static_block_text) for one issue x cell."""
    o_present = cell in ('C', 'D')
    m_adjud = cell in ('B', 'D')
    if not o_present:
        if m_adjud:  # B = frozen T3D-Strict
            disp = diagnostic_adjud_display(it)
            block = views.evidence_block(disp, tier='D', symptom=it['symptom'])
        else:       # A = withheld diagnostic
            disp = diagnostic_withheld_display(it)
            block = diagnostic_block_withheld(disp, it['symptom'])
    else:
        disp = acceptance_display(it, withheld=not m_adjud)
        block = views.evidence_block(disp, tier='A', symptom=None)
    return disp, block


def build_messages(it, cell, block):
    o_present = cell in ('C', 'D')
    m_adjud = cell in ('B', 'D')
    user = [P._ternary_head_v2(), P._TERNARY_GOAL,
            f"\n\nISSUE:\n{it['raw']['problem_statement']}",
            f"\n\nPATCH:\n{it['raw']['model_patch']}",
            f"\n\nAUTHOR STATEMENT:\n{CLAIM}",
            '\n\n' + block,
            O_WORDING_PRESENTED if o_present else O_WORDING_BLOCKED,
            M_WORDING_ADJUDICATED if m_adjud else M_WORDING_WITHHOLD]
    return G4_SYSTEM, ''.join(user)


# ---------------------------------------------------------------------------
# Fixed tool-response payloads (faithful to the frozen server semantics)
# ---------------------------------------------------------------------------
def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def linkage_payload(it):
    # Exactly evidence.store.ArtifactStore.check_linkage output.
    return {
        'authentic_signature': True,
        'base_commit_match': it['rec']['base_commit'] == it['base_commit'],
        'patch_sha256_match': it['rec']['patch_sha256'] == it['patch_sha'],
        'linked': True,
        'record_base_commit': it['rec']['base_commit'],
        'record_patch_sha256': it['rec']['patch_sha256'],
    }


def freshness_adjudicated(it):
    v = F.adjudicate_freshness(
        rec=it['rec'], authentic=True, att=it['att'],
        sess={'base_commit': it['base_commit']},
        restaged_tree=it['restaged_tree'], patch_match=True)
    v['protocol_version'] = it['protocol']
    v['attestation'] = ATTEST_MARKER_A
    return v


def _length_match(withheld: dict, adjudicated: dict, note_key='note'):
    """Expand the withheld note with neutral prose so the JSON byte length is
    within +/-10% of the adjudicated envelope (identical key set). Aimed just
    under parity (0.98x). No verdict vocabulary is introduced."""
    target = len(_dump(adjudicated))
    lo, hi = int(target * 0.90), int(target * 1.02)
    w = _clone(withheld)
    w[note_key] = ''
    base = len(_dump(w))
    needed = max(0, int(0.98 * target) - base)
    note = ''
    while len(note) < needed:
        note += _NEUTRAL_FILLER
    note = note[:max(0, needed)].rstrip()
    w[note_key] = note
    body = _dump(w)
    # if still short of the band floor, top up; if above ceiling, trim a word
    while len(body) < lo:
        note += ' ' + _NEUTRAL_FILLER.rstrip()
        w[note_key] = note
        body = _dump(w)
    while len(body) > hi and len(note) > 40:
        note = note.rsplit(' ', 1)[0]
        w[note_key] = note
        body = _dump(w)
    return w


def freshness_withheld(it):
    adj = freshness_adjudicated(it)
    w = {
        'protocol_version': it['protocol'],
        'authentic_signature': None,
        'attestation_authentic': None,
        'base_commit_match': None,
        'record_run_tree': None,
        'record_run_tree_present': None,
        'expected_run_tree': None,
        'authoritative_tree_source': None,
        'authoritative_run_tree': None,
        'run_tree_match': None,
        'fresh': None,
        'fresh_state': 'UNKNOWN',
        'status_reason': 'attestation_withheld_on_this_surface',
        'artifact_started_at': OPAQUE_TIME_TOKEN,
        'attestation_built_at': OPAQUE_TIME_TOKEN,
        'note': 'freshness attestation withheld on this surface; state UNKNOWN; '
                'it can neither support nor refute an ACCEPT or a REJECT',
        'attestation': ATTEST_MARKER_W,
    }
    assert set(w) == set(adj), (set(w) ^ set(adj))
    out = _length_match(w, adj)
    assert set(out) == set(adj)
    return out


def coverage_components(it):
    rec, att = it['rec'], it['att']
    f2p_exec = sorted((rec.get('fail_to_pass') or {}).keys())
    p2p_exec = sorted((rec.get('pass_to_pass_scoped') or {}).keys())
    f2p_decl = sorted(att['declared_fail_to_pass'])
    p2p_decl = sorted(att['declared_p2p_scoped'])
    return f2p_decl, f2p_exec, p2p_decl, p2p_exec


def coverage_adjudicated(it):
    f2p_decl, f2p_exec, p2p_decl, p2p_exec = coverage_components(it)
    return {
        'authentic_signature': True,
        'attestation_authentic': True,
        'fail_to_pass': {
            'declared': len(f2p_decl), 'executed': len(f2p_exec),
            'missing_ids': [n for n in f2p_decl if n not in f2p_exec],
            'undeclared_executed': [n for n in f2p_exec if n not in f2p_decl]},
        'pass_to_pass_scoped': {
            'declared': len(p2p_decl), 'executed': len(p2p_exec),
            'missing_count': len([n for n in p2p_decl if n not in p2p_exec]),
            'missing_ids_sample': [n for n in p2p_decl
                                   if n not in p2p_exec][:20]},
        'complete': True,
        'note': 'coverage compares executed test ids to the declared acceptance '
                'set; it reports no pass/fail outcomes',
        'attestation': ATTEST_MARKER_A,
    }


def coverage_withheld(it):
    adj = coverage_adjudicated(it)
    w = {
        'authentic_signature': None,
        'attestation_authentic': None,
        'fail_to_pass': {'declared': None, 'executed': None,
                         'missing_ids': None, 'undeclared_executed': None},
        'pass_to_pass_scoped': {'declared': None, 'executed': None,
                                'missing_count': None,
                                'missing_ids_sample': None},
        'complete': None,
        'note': 'coverage attestation withheld on this surface; state UNKNOWN; '
                'coverage here reports no pass/fail outcomes',
        'attestation': ATTEST_MARKER_W,
    }
    assert set(w) == set(adj), (set(w) ^ set(adj))
    out = _length_match(w, adj)
    assert set(out) == set(adj)
    return out


def consistency_blocked():
    """Frozen strict/tier-D symptom-only adjudication; identical A and B.
    All 18 have the symptom gone + a positive claim => 'consistent'."""
    return {'verdict': 'consistent',
            'reason': 'the authorised diagnostic evidence supports the claim at '
                      'issue level: the reported symptom no longer reproduces; '
                      'maintainer acceptance outcomes are not adjudicated under '
                      'the strict policy'}


def consistency_presented(it):
    """Frozen tier-A acceptance adjudication; identical C and D."""
    rec = it['rec']
    summ = rec.get('summary') or {}
    n_fail = len(summ.get('f2p_failed_ids') or [])
    n_regr = len(summ.get('p2p_regressed_ids') or [])
    n_exec = len(rec.get('fail_to_pass') or {}) + len(
        rec.get('pass_to_pass_scoped') or {})
    if n_fail + n_regr > 0:
        return {'verdict': 'contradicted',
                'reason': f'claim asserts success; the artifact records '
                          f'{n_fail} failed acceptance and {n_regr} regression '
                          'checks',
                'failed_acceptance_checks': n_fail,
                'regression_checks': n_regr,
                'executed_checks': n_exec}
    return {'verdict': 'consistent',
            'reason': 'executed acceptance/regression checks show no failure',
            'failed_acceptance_checks': 0,
            'regression_checks': 0,
            'executed_checks': n_exec}


STRICT_403 = {'error': 'acceptance logs are disabled under the strict '
                       'evidence policy'}


def artifact_payload(disp, cell):
    # Tier-A projected records carry no evidence_tier key (the frozen server
    # passes tier separately), so the cell determines the envelope tier.
    return {'artifact': disp, 'authentic_signature': True,
            'evidence_tier': 'acceptance' if cell in ('C', 'D')
            else 'diagnostic'}


def fixed_transcript(it, cell, disp):
    o_present = cell in ('C', 'D')
    m_adjud = cell in ('B', 'D')
    steps = [
        ('get_test_artifact', {}, 200, 'application/json',
         _dump(artifact_payload(disp, cell))),
        ('verify_artifact_linkage', {}, 200, 'application/json',
         _dump(linkage_payload(it))),
        ('check_evidence_freshness', {}, 200, 'application/json',
         _dump(freshness_adjudicated(it) if m_adjud
               else freshness_withheld(it))),
        ('check_test_coverage', {}, 200, 'application/json',
         _dump(coverage_adjudicated(it) if m_adjud
               else coverage_withheld(it))),
        ('check_claim_consistency', {'claim': CLAIM}, 200,
         'application/json',
         _dump(consistency_presented(it) if o_present
               else consistency_blocked())),
        ('get_run_log', {'name': 'symptom'}, 200, 'text/plain',
         it['logs']['symptom']),
        ('get_run_log', {'name': 'f2p'},
         200 if o_present else 403,
         'text/plain' if o_present else 'application/json',
         it['logs']['f2p'] if o_present else _dump(STRICT_403)),
        ('get_run_log', {'name': 'p2p'},
         200 if o_present else 403,
         'text/plain' if o_present else 'application/json',
         it['logs']['p2p'] if o_present else _dump(STRICT_403)),
        ('get_run_log', {'name': 'p2p_baseline'},
         200 if o_present else 403,
         'text/plain' if o_present else 'application/json',
         it['logs']['p2p_baseline'] if o_present else _dump(STRICT_403)),
    ]
    return [dict(step=i, name=n, args=a, http_status=s,
                 content_type=ct, body=b)
            for i, (n, a, s, ct, b) in enumerate(steps)]


# ONE unified six-tool interface in every cell. It is the acceptance-tier
# schema (all four log names in the enum); in A/B the f2p/p2p/baseline calls
# still return the frozen strict 403, so inventory is identical while the
# blocked-outcome information content is preserved.
G4_TOOLS = P.ternary_tools('T3A-T')


def sha256_text(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def build_bundle(it, cell):
    disp, block = render_surface(it, cell)
    system, user = build_messages(it, cell, block)
    transcript = fixed_transcript(it, cell, disp)
    payload_hashes = {'system': sha256_text(system),
                      'user': sha256_text(user),
                      'tools': sha256_text(_dump(G4_TOOLS)),
                      'evidence_block': sha256_text(block)}
    for st in transcript:
        payload_hashes[f"step{st['step']}:{st['name']}:"
                       f"{st['args'].get('name', '')}"] = sha256_text(
            st['body'])
    return {
        'schema': 'g4-fixed-bundle-v1.1',
        'g4_version': G4_VERSION,
        'cohort': it['cohort'],
        'instance_id': it['iid'],
        'cell': cell,
        'factors': {'O': 'presented' if cell in ('C', 'D') else 'blocked',
                    'fc_attestation': 'adjudicated'
                    if cell in ('B', 'D') else 'withheld',
                    'linkage': 'linked_constant'},
        'oracle_gold': it['oracle'],
        'condition_gold': ('per_oracle' if cell in ('C', 'D')
                           else 'NEED_EVIDENCE'),
        'system': system,
        'user': user,
        'evidence_block': block,
        'tools': G4_TOOLS,
        'transcript': transcript,
        'payload_hashes': payload_hashes,
    }


# ---------------------------------------------------------------------------
# Latin order over 144 slots (seed frozen)
# ---------------------------------------------------------------------------
def latin_order(iids):
    base = []
    for cell in CELLS:
        for m in MODELS:
            base.append((m, cell))
    random.Random(G4_ORDER_SEED).shuffle(base)
    order = []
    for b, iid in enumerate(iids):
        block = base[b % len(base):] + base[:b % len(base)]
        for model, cell in block:
            order.append({'model_profile': model, 'instance_id': iid,
                          'cell': cell, 'serial': len(order)})
    cnt = Counter((r['model_profile'], r['cell']) for r in order)
    assert len(order) == 144 and len(cnt) == 8 \
        and set(cnt.values()) == {18}, cnt
    return order


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------
def _key_paths(obj):
    out = set()

    def walk(o, pre):
        if isinstance(o, dict):
            for k, v in o.items():
                p = f'{pre}.{k}' if pre else k
                out.add(p)
                walk(v, p)
        elif isinstance(o, list):
            for j, v in enumerate(o):
                walk(v, f'{pre}[{j}]')
    walk(obj, '')
    return out


def gate_g1(bundles):
    """Schema parity + payload length band (+/-10%) withheld vs adjudicated."""
    rows, failures = [], []
    by = {(b['instance_id'], b['cell']): b for b in bundles}
    for iid in sorted({b['instance_id'] for b in bundles}):
        for endpoint, step in (('freshness', 2), ('coverage', 3)):
            wb = by[(iid, 'A')]['transcript'][step]['body']
            ab = by[(iid, 'B')]['transcript'][step]['body']
            wj, aj = json.loads(wb), json.loads(ab)
            kw, ka = _key_paths(wj), _key_paths(aj)
            same_keys = kw == ka
            ratio = len(wb) / max(1, len(ab))
            ok = same_keys and 0.90 <= ratio <= 1.10
            rows.append({'issue': iid, 'endpoint': endpoint,
                         'same_key_set': same_keys,
                         'len_withheld': len(wb),
                         'len_adjudicated': len(ab),
                         'ratio': round(ratio, 4), 'pass': ok})
            if not ok:
                failures.append({'issue': iid, 'endpoint': endpoint,
                                 'keys_only_withheld': sorted(kw - ka),
                                 'keys_only_adjudicated': sorted(ka - kw),
                                 'ratio': round(ratio, 4)})
    return {'name': 'G1 schema parity',
            'pass': all(r['pass'] for r in rows),
            'criterion': 'identical recursive key set and byte length within '
                         '+/-10% for withheld vs adjudicated F/C payloads',
            'rows': rows, 'failures': failures}


_TREE_FIELDS = ('run_tree_match', 'expected_run_tree', 'record_run_tree',
                'authoritative_run_tree', 'authoritative_tree_source',
                'base_commit_match', 'authentic_signature',
                'attestation_authentic')
_BAD_PATTERNS = [re.compile(p, re.I) for p in (
    r'fresh\s*=\s*false', r'freshness\s*=\s*false',
    r'coverage\s*=\s*false', r'stale', r'not fresh',
    r'missing tests?', r'incomplete coverage', r'tree mismatch')]


def _fc_surface_text(bundle, symptom=False):
    """Static block + tool bodies (optionally incl. symptom). Excludes the
    issue/patch/claim and the O/M policy paragraphs (registered scaffolding)."""
    parts = [bundle['evidence_block']]
    for st in bundle['transcript']:
        if not symptom and st['name'] == 'get_run_log' \
                and st['args'].get('name') == 'symptom':
            continue
        parts.append(st['body'])
    return '\n'.join(parts)


def gate_g2_g3(bundles, issues):
    import re
    imap = {it['iid']: it for it in issues}
    by = {(b['instance_id'], b['cell']): b for b in bundles}
    g2_rows, g3_rows, g2_fail, g3_fail = [], [], [], []
    iids = sorted({b['instance_id'] for b in bundles})

    for iid in iids:
        it = imap[iid]
        secret_trees = {t for t in (it['att']['expected_run_tree'],
                                    it['restaged_tree']) if t}
        f2p_decl, f2p_exec, p2p_decl, p2p_exec = coverage_components(it)
        decisive_ids = set(f2p_exec) | set(p2p_exec)
        declared_sample = set(f2p_decl[:3]) | set(p2p_decl[:3])

        # ---- G2: F/C cannot be reconstructed on withheld cells A and C ----
        for cell in ('A', 'C'):
            b = by[(iid, cell)]
            text = _fc_surface_text(b, symptom=True)
            probs = []
            for t in secret_trees:
                if t in text:
                    probs.append('secret_run_tree_present')
            fr = json.loads(b['transcript'][2]['body'])
            cv = json.loads(b['transcript'][3]['body'])
            for fld in _TREE_FIELDS:
                if fr.get(fld) is not None:
                    probs.append(f'freshness.{fld}_non_null')
            if fr.get('fresh') is not None or fr.get('fresh_state') != 'UNKNOWN':
                probs.append('freshness_verdict_not_unknown')
            for grp in ('fail_to_pass', 'pass_to_pass_scoped'):
                if any(v is not None for v in cv[grp].values()):
                    probs.append(f'coverage.{grp}_component_non_null')
            if cv.get('complete') is not None:
                probs.append('coverage.complete_non_null')
            if str(it['att'].get('built_at') or '') in text:
                probs.append('attestation_built_at_present')
            if cell == 'A':  # declared set is fully hidden only when O blocked
                art = b['transcript'][0]
                aj = json.loads(art['body'])['artifact']
                if (aj['summary'].get('f2p_total') is not None
                        or aj['summary'].get('p2p_total') is not None):
                    probs.append('cellA_declared_total_non_null')
                if aj.get('scope', {}).get('p2p_scoped_files') is not None:
                    probs.append('cellA_scoped_files_present')
                for name in declared_sample:
                    if name in text:
                        probs.append(f'declared_name_present:{name}')
            for pat in _BAD_PATTERNS:
                if pat.search(text):
                    probs.append(f'negative_wording:{pat.pattern}')
            ok = not probs
            g2_rows.append({'issue': iid, 'cell': cell, 'pass': ok,
                            'n_problems': len(probs)})
            if not ok:
                g2_fail.append({'issue': iid, 'cell': cell,
                                'problems': sorted(set(probs))})

        # ---- G3: no decisive acceptance outcome leaks into A/B ----
        for cell in ('A', 'B'):
            b = by[(iid, cell)]
            text_nosym = _fc_surface_text(b, symptom=False)
            probs = []
            for pat in views._LEAK_PATTERNS:
                if pat.search(text_nosym):
                    probs.append(f'leak_pattern:{pat.pattern}')
            for step in (6, 7, 8):
                if b['transcript'][step]['http_status'] != 403:
                    probs.append(
                        f"step{step}_status_{b['transcript'][step]['http_status']}")
            art = json.loads(b['transcript'][0]['body'])['artifact']
            for k in ('fail_to_pass', 'pass_to_pass_scoped',
                      'pass_to_pass_baseline', 'run_tree'):
                if k in art:
                    probs.append(f'artifact_carries_{k}')
            for k in ('f2p_passed', 'f2p_failed_ids', 'p2p_passed',
                      'p2p_regressed_ids', 'p2p_preexisting_bad_ids'):
                if k in (art.get('summary') or {}):
                    probs.append(f'summary_carries_{k}')
            for name in decisive_ids:
                # Node-boundary match. The frozen tier-D surface keeps the
                # scope FILE list (e.g. sympy/sets/tests/test_contains.py),
                # and a decisive node id can be a substring of such a path
                # (node test_pow vs file test_power.py). File paths are scope
                # metadata, not executed-node verdicts, so a hit counts only
                # when the name stands as a test node (not inside a .py path
                # or a longer identifier); a pytest node path::test_x still
                # matches because the char before it is ':'.
                node_re = re.compile(
                    r'(?<![\w/.\-])' + re.escape(name) + r'(?![\w.\-])')
                if node_re.search(text_nosym):
                    probs.append(f'decisive_id_present:{name}')
            if 'oracle_gold' in text_nosym:
                probs.append('gold_key_present')
            # symptom channel must carry no verdict token either
            sym = b['transcript'][5]['body']
            for tok in ('FAIL_TO_PASS', 'PASS_TO_PASS'):
                if tok in sym:
                    probs.append(f'symptom_token:{tok}')
            ok = not probs
            g3_rows.append({'issue': iid, 'cell': cell, 'pass': ok,
                            'n_problems': len(probs)})
            if not ok:
                g3_fail.append({'issue': iid, 'cell': cell,
                                'problems': sorted(set(probs))[:20]})

    return ({'name': 'G2 F/C non-reconstructability',
             'pass': all(r['pass'] for r in g2_rows),
             'criterion': 'withheld cells expose no run-tree hash, attestation '
                          'time, declared/executed set, missing list, or '
                          'negative wording that recomputes freshness/coverage',
             'rows': g2_rows, 'failures': g2_fail},
            {'name': 'G3 outcome blocking / noninterference',
             'pass': all(r['pass'] for r in g3_rows),
             'criterion': 'A/B expose no acceptance verdict, failing/regressed '
                          'id, failure count, or gold; acceptance logs return '
                          'the frozen strict 403',
             'rows': g3_rows, 'failures': g3_fail})


def gate_g4(bundles):
    by = {(b['instance_id'], b['cell']): b for b in bundles}
    rows, failures = [], []
    for iid in sorted({b['instance_id'] for b in bundles}):
        verify = {c: by[(iid, c)]['transcript'][1]['body'] for c in CELLS}
        symptom = {c: by[(iid, c)]['transcript'][5]['body'] for c in CELLS}
        v_const = len(set(verify.values())) == 1
        s_const = len(set(symptom.values())) == 1
        ok = v_const and s_const
        rows.append({'issue': iid, 'verify_identical_all4': v_const,
                     'symptom_identical_all4': s_const, 'pass': ok})
        if not ok:
            failures.append({'issue': iid, 'verify_constant': v_const,
                             'symptom_constant': s_const})
    return {'name': 'G4 linkage constancy',
            'pass': all(r['pass'] for r in rows),
            'criterion': '/verify payload and symptom surface byte-identical '
                         'across A/B/C/D; linkage framing never toggled',
            'rows': rows, 'failures': failures}


def _canon_cd(disp):
    """C vs D must be identical apart from timestamps + attestation marker."""
    d = _clone(disp)
    d['started_at'] = 0
    d['finished_at'] = 0
    d.get('summary', {})['attestation'] = 0
    d.get('scope', {})['attestation'] = 0
    return _dump(d)


def gate_g5(bundles):
    by = {(b['instance_id'], b['cell']): b for b in bundles}
    rows, failures = [], []
    for iid in sorted({b['instance_id'] for b in bundles}):
        B = {c: by[(iid, c)] for c in CELLS}
        prob = []
        if len({B[c]['system'] for c in CELLS}) != 1:
            prob.append('system_varies')
        if len({sha256_text(_dump(B[c]['tools'])) for c in CELLS}) != 1:
            prob.append('tools_vary')
        for step, label in ((1, 'verify'), (5, 'symptom')):
            if len({B[c]['transcript'][step]['body'] for c in CELLS}) != 1:
                prob.append(f'{label}_varies')
        # M components constant within an M level across the two O rows
        for step, label in ((2, 'freshness'), (3, 'coverage')):
            if B['A']['transcript'][step]['body'] != \
                    B['C']['transcript'][step]['body']:
                prob.append(f'{label}_withheld_differs_across_rows')
            if B['B']['transcript'][step]['body'] != \
                    B['D']['transcript'][step]['body']:
                prob.append(f'{label}_adjudicated_differs_across_rows')
        # O log gating constant within a row
        for step in (6, 7, 8):
            if B['A']['transcript'][step]['body'] != \
                    B['B']['transcript'][step]['body']:
                prob.append(f'step{step}_blocked_AB_differs')
            if B['C']['transcript'][step]['body'] != \
                    B['D']['transcript'][step]['body']:
                prob.append(f'step{step}_presented_CD_differs')
        if B['A']['transcript'][4]['body'] != \
                B['B']['transcript'][4]['body']:
            prob.append('consistency_AB_differs')
        if B['C']['transcript'][4]['body'] != \
                B['D']['transcript'][4]['body']:
            prob.append('consistency_CD_differs')
        # decisive O record C vs D identical apart from registered M cues
        art_c = json.loads(B['C']['transcript'][0]['body'])['artifact']
        art_d = json.loads(B['D']['transcript'][0]['body'])['artifact']
        cd_equal = _canon_cd(art_c) == _canon_cd(art_d)
        if not cd_equal:
            prob.append('decisive_artifact_CD_differs_beyond_M')
        rows.append({'issue': iid, 'decisive_O_CD_identical': cd_equal,
                     'pass': not prob})
        if prob:
            failures.append({'issue': iid, 'problems': sorted(set(prob))})
    return {'name': 'G5 only-registered-factors change',
            'pass': all(r['pass'] for r in rows),
            'criterion': 'F/C payloads constant within M level across rows; '
                         'logs/consistency constant within row; C/D decisive '
                         'outcomes identical apart from timestamp + marker; '
                         'only O and fc_attestation vary',
            'rows': rows, 'failures': failures}


def _ntok(s):
    return len(s.split())


def gate_g6(bundles):
    by = {(b['instance_id'], b['cell']): b for b in bundles}
    rows, failures = [], []
    for iid in sorted({b['instance_id'] for b in bundles}):
        B = {c: by[(iid, c)] for c in CELLS}
        inv = {c: [(s['name'], _dump(s['args'])) for s in B[c]['transcript']]
               for c in CELLS}
        g61 = len({_dump(inv[c]) for c in CELLS}) == 1
        seq = {c: [(s['http_status'], s['content_type'])
                   for s in B[c]['transcript']] for c in CELLS}
        # Interaction parity is ROW-WISE: A must behave exactly like B and C
        # exactly like D (same statuses/content types at every fixed step).
        # The only cross-row sequence difference permitted is the registered
        # O manipulation: f2p/p2p/baseline (steps 6-8) return the frozen
        # strict 403/json when O is blocked (A,B) but 200/text when O is
        # presented (C,D). Steps 0-5 are identical across all four cells.
        g62_ab = seq['A'] == seq['B']
        g62_cd = seq['C'] == seq['D']
        g62_head = all([seq[c][i] == seq['A'][i]
                        for c in CELLS for i in range(6)])
        g62_blocked = all(seq[c][i] == (403, 'application/json')
                          for c in ('A', 'B') for i in (6, 7, 8))
        g62_presented = all(seq[c][i] == (200, 'text/plain')
                            for c in ('C', 'D') for i in (6, 7, 8))
        g62 = (g62_ab and g62_cd and g62_head
               and g62_blocked and g62_presented)
        def ul(c):
            return len(B[c]['system']) + len(B[c]['user'])
        rAB = ul('B') / max(1, ul('A'))
        rCD = ul('D') / max(1, ul('C'))
        g63 = 0.92 <= rAB <= 1.08 and 0.92 <= rCD <= 1.08
        ok = g61 and g62 and g63
        rows.append({'issue': iid, 'inventory_identical': g61,
                     'sequence_identical': g62,
                     'len_A': ul('A'), 'len_B': ul('B'),
                     'len_C': ul('C'), 'len_D': ul('D'),
                     'ratio_B_over_A': round(rAB, 4),
                     'ratio_D_over_C': round(rCD, 4),
                     'whitespace_tokens': {c: _ntok(B[c]['system'])
                                           + _ntok(B[c]['user'])
                                           for c in CELLS},
                     'pass': ok})
        if not ok:
            failures.append({'issue': iid, 'g61': g61, 'g62': g62,
                             'g63': g63, 'rAB': round(rAB, 4),
                             'rCD': round(rCD, 4)})
    return {'name': 'G6 interaction parity',
            'pass': all(r['pass'] for r in rows),
            'criterion': 'G6.1 identical tool inventory/order; G6.2 row-wise '
                         'identical fixed response status/content-type '
                         'sequence (A==B, C==D; steps 0-5 constant all four; '
                         'steps 6-8 differ across rows ONLY by the registered '
                         'O factor: frozen strict 403/json vs 200/text); G6.3 '
                         'within-row system+user char delta within +/-8% '
                         '(toggled tool payloads excluded)',
            'rows': rows, 'failures': failures,
            'residual_confounds': [
                'A/B vs C/D differ in static-block size and log bodies; that '
                'IS the registered O factor, not an interaction confound.',
                'Responses are pre-rendered/fixed, so tool call COUNT cannot '
                'diverge in this first round; an interactive round where the '
                'model chooses calls would need a fresh parity audit.',
                'The unified tool enum lists acceptance log names even in A/B; '
                'they return the frozen strict 403, so information content is '
                'blocked but the schema is homogeneous by design.',
                'Equal presentation does not guarantee equal attention; fixed '
                'presentation isolates content, not the model\u2019s allocation '
                'of attention.'],
            'claim_scope': 'fixed_presentation_only'}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    issues = load_issues()

    for it in issues:  # frozen-fact guards
        f = it['gold']['facts']
        assert f['linked'] and f['fresh'] and f['complete'], it['iid']
        assert f['symptom_polarity'] == 'gone', it['iid']
        assert freshness_adjudicated(it)['fresh_state'] == 'TRUE', it['iid']
        assert coverage_adjudicated(it)['complete'] is True, it['iid']

    bundles = [build_bundle(it, cell)
               for it in issues for cell in CELLS]

    g1 = gate_g1(bundles)
    g2, g3 = gate_g2_g3(bundles, issues)
    g4 = gate_g4(bundles)
    g5 = gate_g5(bundles)
    g6 = gate_g6(bundles)
    gates = [g1, g2, g3, g4, g5, g6]
    decision = 'GO' if all(g['pass'] for g in gates) else 'NO-GO'

    with (OUT / 'g4_fixed_bundles.jsonl').open(
            'w', encoding='utf-8', newline='') as fh:
        for b in bundles:
            fh.write(json.dumps(b, ensure_ascii=False) + '\n')

    iids = [it['iid'] for it in issues]
    order = latin_order(iids)
    bmap = {(b['instance_id'], b['cell']): b for b in bundles}
    bhash = {(b['instance_id'], b['cell']):
             sha256_text(_dump({k: b[k] for k in
                                ('system', 'user', 'transcript', 'tools')}))
             for b in bundles}
    with (OUT / 'g4_cell_manifest.jsonl').open(
            'w', encoding='utf-8', newline='') as fh:
        for row in order:
            b = bmap[(row['instance_id'], row['cell'])]
            fh.write(json.dumps({
                'serial': row['serial'],
                'g4_version': G4_VERSION,
                'model_profile': row['model_profile'],
                'instance_id': row['instance_id'],
                'cohort': b['cohort'], 'cell': row['cell'],
                'factors': b['factors'],
                'oracle_gold': b['oracle_gold'],
                'condition_gold': b['condition_gold'],
                'gold_status': 'PROVISIONAL; annotator2 NOT_OBTAINED',
                'bundle_sha256': bhash[(row['instance_id'], row['cell'])],
                'payload_hashes': b['payload_hashes'],
                'sampling': {'temperature': TEMPERATURE,
                             'completion_cap_tokens': COMPLETION_CAP,
                             'max_tool_turns': MAX_TOOL_TURNS,
                             'max_model_calls_per_cell':
                             MAX_MODEL_CALLS_PER_CELL,
                             'retries_per_cell': RETRIES_PER_CELL},
                'api_calls_authorized': 0}, ensure_ascii=False) + '\n')

    with (OUT / 'g4_payload_hashes.jsonl').open(
            'w', encoding='utf-8', newline='') as fh:
        for b in bundles:
            fh.write(json.dumps(
                {'instance_id': b['instance_id'], 'cell': b['cell'],
                 'factors': b['factors'],
                 'payload_hashes': b['payload_hashes']},
                ensure_ascii=False) + '\n')

    diff_rows = []
    for iid in iids:
        rec = {}
        for cell in CELLS:
            b = bmap[(iid, cell)]
            rec[cell] = {
                'system_chars': len(b['system']),
                'user_chars': len(b['user']),
                'step_bodies': {st['name']
                                + (':' + st['args'].get('name', '')
                                   if st['args'].get('name') else ''):
                                {'status': st['http_status'],
                                 'chars': len(st['body'])}
                                for st in b['transcript']}}
        diff_rows.append({'issue': iid, 'cells': rec})

    gate_doc = {
        'document': 'G4 evidence-sufficiency 2x2 identifiability gate',
        'g4_version': G4_VERSION,
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                          time.gmtime()),
        'api_calls_made': 0, 'spend_usd': 0,
        'frozen_artifacts_modified': False,
        'factor_O': 'decisive acceptance outcomes (blocked vs presented)',
        'factor_M': 'fc_attestation = Freshness/Coverage attestation '
                    'availability (withheld vs adjudicated)',
        'linkage': 'held constant across all four cells',
        'identified_estimand': 'when freshness/coverage genuinely hold (all '
                               '18 fresh=complete=true), does attestation '
                               'availability change unsupported acceptance; no '
                               'claim about fresh=false/coverage=false',
        'issue_set': {'n': 18, 'accept': 13, 'reject': 5,
                      'reject_ids': ['sympy__sympy-14248',
                                     'sympy__sympy-15875',
                                     'sympy__sympy-17318',
                                     'sympy__sympy-17630',
                                     'sympy__sympy-19783']},
        'gates': {'G1': g1, 'G2': g2, 'G3': g3, 'G4': g4, 'G5': g5,
                  'G6': g6},
        'decision': decision,
        'next_action': ('eligible to request a SEPARATE written authorization '
                        'for the 144-cell paid pilot (<=$2)'
                        if decision == 'GO' else
                        'repair the manipulation offline at zero cost; no '
                        'paid call and do not alter gold/issues'),
        'stats_plan': {
            'H1': 'two-sided U(A) != U(B) unsupported-ACCEPT rate; sign not '
                  'pre-committed',
            'H2': 'diagnostic specificity control: |U(C)-U(D)| on the 5 '
                  'reject issues + oracle-match on C and D; a comparable '
                  'C/D effect weakens the construct (reported, not auto-fail)',
            'primary_test': 'issue-paired exact McNemar on A vs B unsupported '
                            'ACCEPT indicators (discordant b/c)',
            'ci': 'issue-clustered bootstrap 95% CI of U(A)-U(B); '
                  'Clopper-Pearson per cell',
            'unit': 'independent issue (n=18); cells and models are '
                    'within-issue repeated measures',
            'cells': 144, 'models': list(MODELS),
            'order_seed': G4_ORDER_SEED,
            'order_design': 'balanced Latin; 8 model x cell slots shuffled '
                            'and cyclically shifted one slot per issue',
            'total_budget_usd_hard_cap': TOTAL_BUDGET_USD,
            'multiplicity': 'H1 is the sole confirmatory test; H2 is a gate',
            'parse_rule': 'unparseable final message = non-ACCEPT; parse-fail '
                          'rate reported separately',
            'locked': True},
        'per_issue_condition_diff': diff_rows,
        'elapsed_sec': round(time.time() - t0, 2),
    }
    (OUT / 'g4_identifiability_gate.json').write_text(
        json.dumps(gate_doc, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8')
    _write_gate_md(gate_doc)

    print('bundles:', len(bundles), '-> g4_fixed_bundles.jsonl')
    print('manifest slots:', len(order), '-> g4_cell_manifest.jsonl')
    for g in gates:
        print(f"{g['name']}: {'PASS' if g['pass'] else 'FAIL'} "
              f"({len(g.get('failures', []))} failures)")
    print('DECISION:', decision)


def _write_gate_md(doc):
    L = ['# G4 Identifiability Gate - GO / NO-GO report', '',
         f"- Version: `{doc['g4_version']}`",
         f"- Generated (UTC): {doc['generated_at_utc']}",
         f"- API calls: **{doc['api_calls_made']}**, spend: "
         f"**${doc['spend_usd']}**, frozen artifacts modified: "
         f"{doc['frozen_artifacts_modified']}",
         '- Factors: **O** decisive outcomes (blocked/presented); **M** '
         '`fc_attestation` freshness/coverage attestation '
         '(withheld/adjudicated); **linkage constant**.',
         f"- Issues: {doc['issue_set']['n']} "
         f"({doc['issue_set']['accept']} ACCEPT / "
         f"{doc['issue_set']['reject']} REJECT); all linked/fresh/complete, "
         'symptom gone.', '',
         '## Decision', '', f"# **{doc['decision']}**", '',
         doc['next_action'], '']
    for key in ('G1', 'G2', 'G3', 'G4', 'G5', 'G6'):
        g = doc['gates'][key]
        L += [f"## {key} - {g['name']}: "
              f"{'PASS' if g['pass'] else 'FAIL'}", '', g['criterion'], '']
        if g.get('failures'):
            L += ['Failures:', '```json',
                  json.dumps(g['failures'], ensure_ascii=False,
                             indent=2)[:6000], '```']
        else:
            L.append('No failures across the 18 issues / applicable cells.')
        L.append('')
        if key == 'G6':
            L.append('Residual interaction confounds:')
            L += [f'- {x}' for x in g['residual_confounds']]
            L += [f"- Claim scope: `{g['claim_scope']}`", '']
    sp = doc['stats_plan']
    L += ['## Frozen statistics / execution plan', '',
          f"- H1: {sp['H1']}", f"- H2: {sp['H2']}",
          f"- Primary: {sp['primary_test']}", f"- CI: {sp['ci']}",
          f"- Order: {sp['order_design']} (seed {sp['order_seed']})",
          f"- Budget hard cap: ${sp['total_budget_usd_hard_cap']}; "
          f"{sp['cells']} cells; parse: {sp['parse_rule']}", '',
          '## Identified-estimand boundary (mandatory in paper)', '',
          doc['identified_estimand'], '']
    (OUT / 'g4_identifiability_gate.md').write_text(
        '\n'.join(L), encoding='utf-8')


if __name__ == '__main__':
    main()
