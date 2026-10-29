"""GroundedReview v2.1 — OFFLINE 2x2 ablation DESIGN gate (zero API, by
construction: this module has NO live code path and no model client import).

Written approval 2026-10-25: v2.1 *design* approved at $0; real model calls,
new issues, paid Gate-3 expansion, Gemini runs and git commits remain
forbidden. This module therefore only:

  1. Builds the four structured-only v2.1 conditions for the frozen 22
     fixtures (88 payloads), as an orthogonal 2x2:

            B0  frozen Gate-2 decision head
            B1  + ASYMMETRIC-RULE REMINDER (verbatim restatement only)
        A0  Gate-2 structured bytes           A0B0 (control)   A0B1
        A1  + deterministic operand counts    A1B0             A1B1

     A0B0 re-serves the FROZEN Gate-2 structured payload byte-for-byte.
       Factor A (rendering): one "TABLE 0" block of COUNTS mechanically
         derived from operands already printed in TABLES 1-4 (differing
         identity pairs, differing run-tree pair, declared-vs-present /
         absent test counts). It states NO linked/fresh/complete/symptom
         boolean and no gold; a count of differing pairs is not the
         conjunctive verdict (e.g. freshness needs base identity AND tree
         equality; the block never combines them).
       Factor B (policy): a compact reminder whose every substantive
         sentence occurs VERBATIM in the frozen Gate-2 head; the meanings
         of ACCEPT/REJECT/NEED_EVIDENCE are unchanged (provenance-checked).

  2. Freezes hashes/fingerprints, head/body byte deltas, gold and the
     pre-registered scoring/statistics, then runs the OFFLINE audits:
     label leakage, evidence sufficiency (count correctness + full operand
     preservation + 22/22 determination), prompt/payload hash freeze,
     factor orthogonality, reminder wording provenance.

  3. Runs a deterministic zero-network mock through the full 88-cell
     ingestion -> scoring -> 2x2 estimation pipeline (oracle mock must
     score 1.00 in every condition).

  4. Emits SEPARATE budget envelopes for (i) the 2x2 ablation and
     (ii) the independent reliability re-call check, priced from actual
     Gate-2 token usage. Nothing here can spend money.

Read-only against: evidence_store_eal/{gate2,gate2_runs,gate25},
evidence_store_w21, evidence_store_cee, evidence/eal_*.py / cee_*.py.
Writes only under evidence_store_eal/v21 and evidence_store_eal/v21_runs.

    uv run --python 3.13 -m evidence.eal_v21_design
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.ternary import read_jsonl
from evidence import cee_protocol_v11 as cee
from evidence import eal_protocol as eal
from evidence.eal_render import (DEFAULT_STORE, ArtifactStore, _bundle_id,
                                 load_index, load_materials)
from evidence.eal_gate2_freeze import (LEAK_VERDICT, LEAK_META, CRED_PAT,
                                       BODY_MARK)
from evidence.eal_run import _sha

ROOT = Path(__file__).resolve().parent.parent
EAL_DIR = ROOT / 'evidence_store_eal'
G2_DIR = EAL_DIR / 'gate2'
G2_LAYERS = G2_DIR / 'layers'
G2_MANIFEST = G2_DIR / 'eal_gate2_materials_manifest.json'
V21_DIR = EAL_DIR / 'v21'
V21_LAYERS = V21_DIR / 'layers'
V21_RUNS = EAL_DIR / 'v21_runs'
DESIGN_MANIFEST = V21_DIR / 'eal_v21_design_manifest.json'
FREEZE_MANIFEST = V21_DIR / 'eal_v21_freeze_manifest.json'
PREFLIGHT = V21_DIR / 'eal_v21_preflight.json'

V21_VERSION = 'eal-v0-draft1+gate2-disclosure+v21design1'
CONDITIONS = ('a0b0', 'a1b0', 'a0b1', 'a1b1')
SEED = 7
N_BOOT = 10000

# Gate-2 actual unit prices (peak guard prices; identical to freeze config).
PRICES = {'deepseek-flash': {'in': 0.30, 'out': 1.20},
          'gpt-4.1-mini': {'in': 0.40, 'out': 1.60}}

# ---------------------------------------------------------------------------
# Factor B — asymmetric-rule reminder. Every substantive quoted sentence is
# taken VERBATIM from the frozen head (evidence/prompts.py TERNARY_HEAD, which
# is inside every Gate-2 raw/structured payload). Only connectives and the
# wrapper are new; no definition is added or altered.
# ---------------------------------------------------------------------------
B_QUOTES = [
    # REJECT bar, incl. the coverage-asymmetry the G2.5 negative audit found
    # models sometimes violating: one applicable failure suffices.
    'A single credible, applicable failing check is enough to REJECT even '
    'if not every declared check was run.',
    'But a failure seen in a stale run, in an artifact linked to a '
    "different patch, or in an inapplicable log is NOT grounds to reject "
    'THIS patch.',
    # ACCEPT bar (conjunctive) — operand comparisons must actually resolve.
    'the bar to ACCEPT is complete, fresh, linked, failure-free success',
    # NEED bar, and the two symmetric abstention errors.
    'do not REJECT merely because evidence is stale/mismatched/incomplete.',
    'abstaining on a decisive applicable failure or on complete success is '
    'an error.',
]

POLICY_REMINDER = (
    '\n\nASYMMETRIC DECISION-RULE REMINDER — the following sentences are '
    'quoted VERBATIM from the decision rule already printed above; this '
    'reminder only makes that frozen rule more salient and changes no '
    'definition of ACCEPT, REJECT or NEED_EVIDENCE:\n'
    + ''.join(f'  • {q}\n' for q in B_QUOTES)
    + 'Apply them yourself to the operand comparisons in this condition.')

# ---------------------------------------------------------------------------
# Factor A — deterministic operand-count block (TABLE 0). Deliberately avoids
# the verdict words linked/fresh/complete and never states a boolean; counts
# disagreement/absence only.
# ---------------------------------------------------------------------------
_TABLE0_HEADER = (
    '\n\n=== TABLE 0 — DETERMINISTIC OPERAND COUNTS (mechanical counts of '
    'operands already printed in TABLES 1-4; membership/equality arithmetic '
    'only, no applicability or decision verdict) ===')


def operand_counts(mat: dict) -> dict:
    """Counts derived solely from the same visible operands TABLES 1-4 show.
    No channel verdict is produced here."""
    t, rec, att = mat['target'], mat['record'], mat['attestation']
    f2p_map = rec.get('fail_to_pass') or {}
    p2p_map = rec.get('pass_to_pass_scoped') or {}
    base_map = rec.get('pass_to_pass_baseline') or {}
    post_exec = set(f2p_map) | set(p2p_map)
    decl_f2p = sorted(att['declared_fail_to_pass']) if att else []
    decl_p2p = sorted(att['declared_p2p_scoped']) if att else []

    id_pairs = [('base_commit', rec.get('base_commit') == t['base_commit']),
                ('patch_sha256',
                 rec.get('patch_sha256') == t['patch_sha256'])]
    tree_compared = att is not None
    tree_equal = tree_compared and (
        rec.get('base_commit') == t['base_commit']
        and rec.get('run_tree') == att['expected_run_tree'])

    def grp(decl):
        present = sorted(d for d in decl if d in post_exec)
        return {'declared': len(decl), 'present_post': len(present),
                'absent_post': len(decl) - len(present),
                'absent_ids': sorted(d for d in decl if d not in post_exec)}

    f2p_failed_post = sorted(k for k, v in f2p_map.items()
                             if str(v).upper() == 'FAILED')
    return {
        'identity_pairs_compared': 2,
        'identity_equal': sum(1 for _, ok in id_pairs if ok),
        'identity_differing': sum(1 for _, ok in id_pairs if not ok),
        'identity_differing_fields': [n for n, ok in id_pairs if not ok],
        'runtree_pair_compared': int(tree_compared),
        'runtree_equal': int(tree_equal),
        'runtree_differing': int(tree_compared and not tree_equal),
        'f2p': grp(decl_f2p),
        'p2p': grp(decl_p2p),
        'declared_p2p_with_base_status':
            sum(1 for d in decl_p2p if d in base_map),
        'f2p_failed_post_ids': f2p_failed_post,
        'n_f2p_failed_post': len(f2p_failed_post),
    }


def render_table0(c: dict) -> str:
    rows = [
        ['identity operand pairs (TABLE 1): pairs compared',
         f"{c['identity_pairs_compared']}"],
        ['identity operand pairs: side-by-side values equal',
         f"{c['identity_equal']}"],
        ['identity operand pairs: values differing',
         f"{c['identity_differing']}"],
        ['run-tree operand pair (TABLE 2): pairs compared',
         f"{c['runtree_pair_compared']}"],
        ['run-tree operand pair: side-by-side values equal',
         f"{c['runtree_equal']}"],
        ['run-tree operand pair: values differing',
         f"{c['runtree_differing']}"],
        ['declared FAIL_TO_PASS (TABLE 3 vs TABLE 4): declared',
         f"{c['f2p']['declared']}"],
        ['declared FAIL_TO_PASS: present in a post-patch status map',
         f"{c['f2p']['present_post']}"],
        ['declared FAIL_TO_PASS: absent from every post-patch status map',
         f"{c['f2p']['absent_post']}"],
        ['declared scoped PASS_TO_PASS: declared',
         f"{c['p2p']['declared']}"],
        ['declared scoped PASS_TO_PASS: present in a post-patch status map',
         f"{c['p2p']['present_post']}"],
        ['declared scoped PASS_TO_PASS: absent from every post-patch map',
         f"{c['p2p']['absent_post']}"],
        ['declared scoped PASS_TO_PASS with a base-commit status present',
         f"{c['declared_p2p_with_base_status']}"],
        ['post-patch FAIL_TO_PASS checks whose status is FAILED',
         f"{c['n_f2p_failed_post']}"],
    ]
    w = max(len(r[0]) for r in rows)
    out = [_TABLE0_HEADER]
    out += [f'  {k.ljust(w)} : {v}' for k, v in rows]
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Build the 2x2 set from frozen Gate-2 structured bytes
# ---------------------------------------------------------------------------

def _split_head_goal_body(user_text: str):
    i = user_text.index(eal.REVIEW_GOAL)
    head = user_text[:i]
    rest = user_text[i + len(eal.REVIEW_GOAL):]
    assert rest.startswith('\n\n')
    body = rest[2:]
    return head, body


def v21_prompt_fingerprint(condition: str, head: str) -> str:
    blob = canonical_dumps({
        'version': V21_VERSION, 'condition': condition,
        'system': eal.SYSTEM_MESSAGE, 'head': head,
        'goal': eal.REVIEW_GOAL, 'schema': eal.DECISION_SCHEMA,
        'tools': [], 'turns': 1})
    return _sha(blob.encode('utf-8'))


def build_design():
    g2 = json.loads(G2_MANIFEST.read_text(encoding='utf-8'))
    fixtures, raw_by_id, cee_gold = load_index(DEFAULT_STORE)
    store = ArtifactStore(str(DEFAULT_STORE))

    # Gate-2 structured frozen bytes, indexed by bundle id.
    g2_str = {}
    for it in g2['items']:
        meta = it['layers']['structured']
        b = (G2_LAYERS / f"{meta['payload_id']}.txt").read_bytes()
        if _sha(b) != meta['sha256']:
            raise SystemExit('Gate-2 structured drift before v2.1 build')
        g2_str[it['bundle_id']] = {
            'bytes': b, 'meta': meta,
            'instance_id': it['instance_id'], 'id': it['id'],
            'scenario_internal': it['scenario_internal'],
            'cee_gold': it['cee_gold'], 'evidence_class': it['evidence_class'],
            'determined': it['layer_gold_determined'],
            'underdetermined': it['underdetermined_channels']}

    items, payloads = [], {}
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        bid = _bundle_id(*key)
        grow = cee_gold[key]
        mat = load_materials(store, fx)
        counts = operand_counts(mat)
        block = render_table0(counts)
        base = g2_str[bid]
        a0b0 = base['bytes']
        head0, body0 = _split_head_goal_body(a0b0.decode('utf-8'))

        # Factor A: insert TABLE 0 directly after the first body sentence.
        mi = body0.index(BODY_MARK['structured'])
        j = body0.index('\n', mi)
        body_a1 = body0[:j] + block + body0[j:]
        a1b0 = (head0 + eal.REVIEW_GOAL + '\n\n' + body_a1).encode('utf-8')

        # Factor B: head only (+ verbatim restatement).
        head_b1 = head0 + POLICY_REMINDER
        a0b1 = (head_b1 + eal.REVIEW_GOAL + '\n\n' + body0).encode('utf-8')
        a1b1 = (head_b1 + eal.REVIEW_GOAL + '\n\n' + body_a1).encode('utf-8')

        cond_bytes = {'a0b0': a0b0, 'a1b0': a1b0, 'a0b1': a0b1,
                      'a1b1': a1b1}
        per_cond, fps = {}, {}
        for cond, bts in cond_bytes.items():
            h = (_split_head_goal_body(bts.decode('utf-8'))[0]
                 if cond in ('a0b0', 'a1b0') else head_b1)
            fps[cond] = v21_prompt_fingerprint(cond, h)
            pid = f'{bid}__{cond}'
            payloads[pid] = bts
            per_cond[cond] = {
                'payload_id': pid, 'bytes': len(bts), 'sha256': _sha(bts),
                'prompt_fingerprint_v21': fps[cond],
                'head_sha256': _sha(h.encode()),
                'body_sha256': _sha(
                    (_split_head_goal_body(bts.decode('utf-8'))[1]
                     if cond in ('a0b0', 'a0b1') else body_a1)
                    .encode()),
                'delta_bytes_vs_a0b0': len(bts) - len(a0b0)}
        items.append({
            'bundle_id': bid, 'instance_id': fx['instance_id'],
            'id': fx['id'], 'scenario_internal': fx['scenario'],
            'served_artifact_id': fx['served_artifact_id'],
            'cee_gold': grow['cee_gold'], 'evidence_class': grow['evidence_class'],
            'layer_gold_determined': base['determined'],
            'underdetermined_channels': base['underdetermined'],
            'operand_counts': counts,
            'g2_structured_payload_sha256': base['meta']['sha256'],
            'conditions': per_cond})
    return items, payloads, fps


# ---------------------------------------------------------------------------
# Offline audits
# ---------------------------------------------------------------------------

def _body_of(payload_text: str) -> str:
    i = payload_text.index(BODY_MARK['structured'])
    return payload_text[i:]


def run_audits(items, payloads, fps):
    checks = []

    def gate(gid, ok, detail=''):
        checks.append({'check': gid, 'pass': bool(ok), 'detail': str(detail)})

    # 1. shape
    gate('design: 22 items x 4 conditions = 88 payloads',
         len(items) == 22 and len(payloads) == 88,
         f'{len(items)} items, {len(payloads)} payloads')
    gate('design: 10 unique issue clusters',
         len({i['instance_id'] for i in items}) == 10)
    dist = {}
    for i in items:
        dist[i['cee_gold']] = dist.get(i['cee_gold'], 0) + 1
    gate('design: frozen gold distribution 7/6/9',
         dist == {'ACCEPT': 7, 'REJECT': 6, 'NEED_EVIDENCE': 9}, dist)
    gate('design: 22/22 gold determined from visible materials',
         all(i['layer_gold_determined'] for i in items))

    # 2. A0B0 == frozen Gate-2 structured bytes (exact reuse)
    bad = [i['bundle_id'] for i in items
           if i['conditions']['a0b0']['sha256']
           != i['g2_structured_payload_sha256']]
    gate('design: A0B0 byte-identical to frozen Gate-2 structured (22/22)',
         not bad, bad)

    # 3. factor orthogonality: A changes body only, B changes head only
    ortho_bad = []
    for i in items:
        c = i['conditions']
        if c['a0b0']['head_sha256'] != c['a1b0']['head_sha256']:
            ortho_bad.append((i['bundle_id'], 'A moved head'))
        if c['a0b0']['body_sha256'] != c['a0b1']['body_sha256']:
            ortho_bad.append((i['bundle_id'], 'B moved body'))
        if c['a0b1']['head_sha256'] != c['a1b1']['head_sha256']:
            ortho_bad.append((i['bundle_id'], 'A head differs under B'))
        if c['a1b0']['body_sha256'] != c['a1b1']['body_sha256']:
            ortho_bad.append((i['bundle_id'], 'B body differs under A'))
        # additive deltas
        if (c['a1b0']['delta_bytes_vs_a0b0']
                + c['a0b1']['delta_bytes_vs_a0b0']
                != c['a1b1']['delta_bytes_vs_a0b0']):
            ortho_bad.append((i['bundle_id'], 'non-additive byte deltas'))
    gate('design: A touches body only / B touches head only / deltas add',
         not ortho_bad, ortho_bad[:5])

    # 4. label-leakage scan over every served BODY (frozen Gate-2 regexes)
    leaks = []
    for i in items:
        for cond in CONDITIONS:
            txt = payloads[i['conditions'][cond]['payload_id']].decode()
            body = _body_of(txt)
            v = sorted(set(m.group(0).strip()
                           for m in LEAK_VERDICT.finditer(body)))
            mm = sorted(set(m.group(0).strip()
                            for m in LEAK_META.finditer(body)))
            # TABLE 0 must not introduce the verdict words either
            if cond in ('a1b0', 'a1b1'):
                low = body.lower()
                for w in ('linked', 'fresh', 'complete', 'symptom_persists'):
                    if re.search(r'\b' + w + r'\b', low):
                        v.append(f'table0_word:{w}')
            if v or mm:
                leaks.append({'payload': i['conditions'][cond]['payload_id'],
                              'verdict': v, 'metadata': mm})
    gate('audit: 0 verdict/metadata/verdict-word leaks in 88 bodies',
         not leaks, leaks[:5])

    # 5. credentials over every served byte
    cred = sorted(pid for pid, b in payloads.items()
                  if CRED_PAT.search(b.decode('utf-8', 'replace')))
    gate('audit: no credentials in any payload', not cred, cred[:5])

    # 6. evidence sufficiency: counts arithmetically consistent and the
    #    frozen Gate-2 body is preserved verbatim inside A1 bodies.
    count_bad, preserve_bad = [], []
    for i in items:
        c = i['operand_counts']
        f = c['f2p']; p = c['p2p']
        if not (f['present_post'] + f['absent_post'] == f['declared']
                and p['present_post'] + p['absent_post'] == p['declared']
                and c['identity_equal'] + c['identity_differing'] == 2
                and c['runtree_equal'] + c['runtree_differing']
                == c['runtree_pair_compared']):
            count_bad.append(i['bundle_id'])
        a0_body = _body_of(payloads[i['conditions']['a0b0']['payload_id']]
                           .decode())
        # A1 body is a0 body with exactly one TABLE-0 block inserted after
        # the first body line; removing it must reproduce a0 byte-for-byte.
        first_nl = a0_body.index('\n')
        prefix = a0_body[:first_nl]
        for cond in ('a1b0', 'a1b1'):
            a1_body = _body_of(
                payloads[i['conditions'][cond]['payload_id']].decode())
            assert a1_body.startswith(prefix + _TABLE0_HEADER)
            k = a1_body.index('\n', len(prefix) + len(_TABLE0_HEADER))
            # walk to end of the block (block ends right before '\n\nISSUE:')
            end = a1_body.index('\n\nISSUE:', k)
            removed = a1_body[:first_nl] + a1_body[end:]
            if removed != a0_body:
                preserve_bad.append((i['bundle_id'], cond))
    gate('audit: TABLE 0 counts are internally consistent (additive)',
         not count_bad, count_bad)
    gate('audit: Gate-2 structured body preserved verbatim inside A1',
         not preserve_bad, preserve_bad[:5])

    # 7. reminder wording provenance: every quoted sentence is verbatim in
    #    the frozen Gate-2 head (item-invariant), and head0 == gate2 head.
    head0 = _split_head_goal_body(
        payloads[items[0]['conditions']['a0b0']['payload_id']]
        .decode())[0]
    missing_q = [q[:40] for q in B_QUOTES if q not in head0]
    gate('audit: every Factor-B quote is verbatim in the frozen Gate-2 head',
         not missing_q, missing_q)
    gate('audit: Factor-B head delta is exactly the reminder block',
         head0 + POLICY_REMINDER == _split_head_goal_body(
             payloads[items[0]['conditions']['a0b1']['payload_id']]
             .decode())[0])

    # 8. Gate-1 self-check still green (frozen prior gate unaffected).
    p = subprocess.run(
        [sys.executable, '-m', 'evidence.eal_gate1_selftest'],
        cwd=str(ROOT), capture_output=True, text=True)
    gate('audit: frozen Gate-1 engineering self-check still 20/20',
         p.returncode == 0 and 'all_pass=True' in p.stdout,
         (p.stdout + p.stderr).strip().splitlines()[-1][:160])

    return checks


# ---------------------------------------------------------------------------
# Pre-registered statistics: DA, error families, 2x2 main effects /
# interaction, issue-cluster paired bootstrap (mirrors are within-issue
# repeats, never independent n).
# ---------------------------------------------------------------------------

def instance_table(rows):
    """Average the (mirror) fixture outcomes within each issue cluster, per
    condition, so every independent unit (instance_id) contributes once."""
    by = {}
    for r in rows:
        by.setdefault((r['model_profile'], r['instance_id'], r['condition']),
                      []).append(1 if r['appropriate'] else 0)
    tab = {}
    for (m, inst, cond), vals in by.items():
        tab.setdefault(m, {}).setdefault(inst, {})[cond] = sum(vals) / len(vals)
    return tab


def contrast(tab_m: dict, kind: str) -> float:
    d = 0.0
    for inst, c in tab_m.items():
        if kind == 'A':   # rendering main effect
            d += (c['a1b0'] + c['a1b1'] - c['a0b0'] - c['a0b1']) / 2
        elif kind == 'B':  # policy main effect
            d += (c['a0b1'] + c['a1b1'] - c['a0b0'] - c['a1b0']) / 2
        else:              # AB interaction
            d += (c['a1b1'] - c['a1b0'] - c['a0b1'] + c['a0b0'])
    return d / len(tab_m)


def cluster_boot(tab_m: dict, kind: str):
    insts = sorted(tab_m)
    rng = random.Random(SEED)
    vals = []
    for _ in range(N_BOOT):
        sample = [tab_m[rng.choice(insts)] for _ in insts]
        vals.append(contrast({i: v for i, v in enumerate(sample)}, kind))
    vals.sort()
    return vals[round(.025 * (N_BOOT - 1))], vals[round(.975 * (N_BOOT - 1))]


def analyze(mock_rows):
    out = {}
    for m in ('deepseek-flash', 'gpt-4.1-mini'):
        rows = [r for r in mock_rows if r['model_profile'] == m]
        per = {}
        for cond in CONDITIONS:
            cr = [r for r in rows if r['condition'] == cond]
            da = sum(1 for r in cr if r['appropriate']) / len(cr)
            need = [r for r in cr if r['cee_gold'] == 'NEED_EVIDENCE']
            need_accept = sum(1 for r in need if r['parsed'] == 'ACCEPT')
            nonneed = [r for r in cr if r['cee_gold'] in
                       ('ACCEPT', 'REJECT')]
            over_abst = sum(1 for r in nonneed
                            if r['parsed'] == 'NEED_EVIDENCE')
            neg = [r for r in cr if r['cee_gold'] == 'REJECT']
            over_abst_neg = sum(1 for r in neg
                                if r['parsed'] == 'NEED_EVIDENCE')
            per[cond] = {
                'da': round(da, 4), 'n': len(cr),
                'need_to_accept_rate':
                    round(need_accept / len(need), 4) if need else None,
                'over_abstention_rate':
                    round(over_abst / len(nonneed), 4) if nonneed else None,
                'over_abstention_on_negatives_rate':
                    round(over_abst_neg / len(neg), 4) if neg else None}
        tab = instance_table(rows)[m]
        effects = {}
        for kind in ('A', 'B', 'AB'):
            lo, hi = cluster_boot(tab, kind)
            effects[kind] = {'point': round(contrast(tab, kind), 4),
                             'ci95_cluster_bootstrap':
                                 [round(lo, 4), round(hi, 4)]}
        out[m] = {'per_condition': per, 'effects': effects}
    return out


# ---------------------------------------------------------------------------
# Deterministic offline mock (oracle responder -> DA must be 1.00; exists to
# exercise ingestion/scoring/2x2 machinery, never to estimate real effects).
# ---------------------------------------------------------------------------

def mock_run(items, payloads):
    runs = []
    for prof in ('deepseek-flash', 'gpt-4.1-mini'):
        for i in items:
            for cond in CONDITIONS:
                meta = i['conditions'][cond]
                b = payloads[meta['payload_id']]
                dec = i['cee_gold'] if i['layer_gold_determined'] \
                    else 'NEED_EVIDENCE'
                runs.append({
                    'protocol': V21_VERSION, 'gate': 'v21_design_mock',
                    'mock': True, 'model_profile': prof,
                    'bundle_id': i['bundle_id'], 'condition': cond,
                    'instance_id': i['instance_id'], 'id': i['id'],
                    'evidence_class': i['evidence_class'],
                    'cee_gold': i['cee_gold'], 'parsed': dec,
                    'appropriate': dec == i['cee_gold'],
                    'error_label': 'appropriate',
                    'payload_id': meta['payload_id'],
                    'payload_sha256': meta['sha256'],
                    'payload_bytes': len(b), 'cost_usd': 0.0})
    return runs


# ---------------------------------------------------------------------------
# Separate budget envelopes priced from ACTUAL Gate-2 token usage
# ---------------------------------------------------------------------------

def budget_envelopes(items, payloads):
    gate2 = {}
    for f, prof in (('eal_gate2_live_deepseek_flash_results.jsonl',
                     'deepseek-flash'),
                    ('eal_gate2_live_gpt_41_mini_results.jsonl',
                     'gpt-4.1-mini')):
        rows = [r for r in read_jsonl(
            str(EAL_DIR / 'gate2_runs' / f)) if r['layer'] == 'structured']
        gate2[prof] = {
            'mean_in_per_structured_cell':
                sum(r['tokens_in_est'] for r in rows) // len(rows),
            'mean_out_per_structured_cell':
                sum(r['tokens_out_est'] for r in rows) // len(rows)}

    a_delta = items[0]['conditions']['a1b0']['delta_bytes_vs_a0b0']
    b_delta = items[0]['conditions']['a0b1']['delta_bytes_vs_a0b0']
    est = lambda extra_bytes: -(-extra_bytes // 3)  # ceil tokens (bytes/3)

    def arm_cost(prof, n_cells, extra_a=0, extra_b=0, repeats=1):
        g = gate2[prof]; pr = PRICES[prof]
        tin = (g['mean_in_per_structured_cell']
               + est(extra_a) + est(extra_b)) * n_cells * repeats
        tout = g['mean_out_per_structured_cell'] * n_cells * repeats
        return {'input_tokens': tin, 'output_tokens': tout,
                'cost_usd': round((tin * pr['in'] + tout * pr['out']) / 1e6, 4)}

    ablation = {}
    for prof in PRICES:
        # 88 cells = 22 x 4; extra tokens averaged over the 4 conditions:
        # A present in 2/4, B present in 2/4 -> half-weight deltas.
        ablation[prof] = arm_cost(prof, 88, extra_a=a_delta / 2,
                                  extra_b=b_delta / 2)
        ablation[prof]['guard_price_in_out_per_mtok'] = PRICES[prof]

    # Reliability: Gate-2 FROZEN 66 cells/model, r fresh repeats; NO v21
    # delta (identical prompt/payload/params/gold). Priced from all-layer
    # Gate-2 actuals.
    reliability = {}
    for f, prof in (('eal_gate2_live_deepseek_flash_results.jsonl',
                     'deepseek-flash'),
                    ('eal_gate2_live_gpt_41_mini_results.jsonl',
                     'gpt-4.1-mini')):
        rows = read_jsonl(str(EAL_DIR / 'gate2_runs' / f))
        tin = sum(r['tokens_in_est'] for r in rows)
        tout = sum(r['tokens_out_est'] for r in rows)
        pr = PRICES[prof]
        reliability[prof] = {
            'gate2_round_input_tokens': tin,
            'gate2_round_output_tokens': tout,
            'r2_new_repeats_per_cell': 2,
            'cost_per_extra_round_usd':
                round((tin * pr['in'] + tout * pr['out']) / 1e6, 4),
            'r2_total_new_calls_usd':
                round(2 * (tin * pr['in'] + tout * pr['out']) / 1e6, 4)}
    return {
        'pricing_note': 'Point estimates from Gate-2 ACTUAL measured tokens '
                        'at peak guard prices; pre-call guard uses bytes//3 '
                        'and hard per-model caps. Two arms are separately '
                        'approvable and must never be auto-merged.',
        'ablation_arm': {
            'cells_per_model': 88, 'models': list(PRICES),
            'factor_a_mean_extra_input_bytes_per_cell': a_delta / 2,
            'factor_b_mean_extra_input_bytes_per_cell': b_delta / 2,
            'by_model': ablation,
            'total_estimate_usd': round(
                sum(v['cost_usd'] for v in ablation.values()), 4)},
        'reliability_arm': {
            'cells_per_model_per_round': 66, 'models': list(PRICES),
            'recommended_new_repeats_per_cell_r': 2,
            'rounds_including_gate2_original': 3,
            'by_model': reliability,
            'total_new_calls_estimate_usd': round(
                sum(v['r2_total_new_calls_usd'] for v in reliability.values()),
                4),
            'independence_caveat': 'Repeated calls are NOT statistically '
                'independent: same frozen inputs, shared serving backend, '
                'possible temporal weight drift. Quantify agreement/Fleiss '
                'kappa and per-cell decision stability; do not treat repeats '
                'as an independent n.'}}


# ---------------------------------------------------------------------------
# Contradiction-rubric operand facts (precomputed now so post-run reason
# coding is mechanical and blinded to the model decision)
# ---------------------------------------------------------------------------

# The 8 G2.5-audited NEED->ACCEPT bundles and their G2.5 primary attribution;
# the precomputed operand fact flags below must reproduce these (design
# validation tying the rubric to the audited evidence).
PREREG_8 = {
    '62dfb1c6': 'freshness', '2c11095a': 'freshness',
    'e4e8b26c': 'freshness', 'c637f604': 'freshness+coverage',
    'ec813709': 'coverage', 'a25d0cf5': 'coverage',
    '403163cb': 'coverage', 'c59a8ceb': 'linkage+freshness'}


def contradiction_facts(items):
    out = {}
    for i in items:
        c = i['operand_counts']
        facts = {
            'p1_identity_contradictable': c['identity_differing'] > 0,
            'p1_fields': c['identity_differing_fields'],
            'p2_runtree_contradictable': c['runtree_differing'] > 0,
            'p3_coverage_contradictable':
                c['f2p']['absent_post'] + c['p2p']['absent_post'] > 0,
            'p3_absent_f2p': c['f2p']['absent_post'],
            'p3_absent_p2p': c['p2p']['absent_post'],
            'p4_f2p_failed_contradictable': c['n_f2p_failed_post'] > 0,
            'p4_f2p_failed_ids': c['f2p_failed_post_ids']}
        out[i['bundle_id'][-8:]] = facts
    # Validate against the 8 audited cases.
    val_bad = []
    for short, attr in PREREG_8.items():
        f = out.get(short)
        if f is None:
            val_bad.append((short, 'missing')); continue
        need = {'freshness': f['p2_runtree_contradictable'],
                'coverage': f['p3_coverage_contradictable'],
                'linkage': f['p1_identity_contradictable']}
        # G2.5 '+coverage' for c637f604 was an EXECUTED f2p failure ignored
        # (test_latex_basic FAILED: 0/1 f2p, 101/102 p2p), i.e. the p4
        # executed-failure operand, not an absent declared test (p3).
        coverage_ok = (need['coverage']
                       or (short == 'c637f604'
                           and f['p4_f2p_failed_contradictable']))
        for token, required in (('freshness', need['freshness']),
                                ('coverage', coverage_ok),
                                ('linkage', need['linkage'])):
            if token in attr and not required:
                val_bad.append((short, attr, token))
    return out, val_bad


SCORING_PREREG = {
    'primary_sample': 'ALL 22 frozen fixtures (7 ACCEPT / 6 REJECT / 9 NEED); '
                      'the 8 G2.5 cases are a pre-registered DIAGNOSTIC '
                      'subset only, never the primary sample and never used '
                      'to select items.',
    'unit_of_independence': 'issue cluster (instance_id, n=10); mirror '
                            'fixtures averaged within cluster before any '
                            'contrast or bootstrap',
    'endpoints': {
        'DA': 'decision appropriateness vs frozen gold, parseable + '
              'all-request denominators',
        'NEED_to_ACCEPT': 'fraction of 9 gold=NEED predicted ACCEPT per '
                          'condition (Evidence Verification Failure marker)',
        'contradictory_assertion_rate': 'fraction of responses whose reason '
              'asserts a verification property {identity-match, run-tree '
              'freshness, coverage complete/all-executed, all-checks-pass} '
              'while the served operands of THAT cell directly contradict it; '
              'coded from verbatim reasons against the precomputed operand '
              'fact table, blinded two-pass coding with disagreement '
              'adjudicated and agreement reported',
        'over_abstention': 'gold in {ACCEPT,REJECT} predicted NEED; '
                           'reported overall and split on REJECT-gold '
                           '(decision-policy-failure marker)'},
    'design_estimands': {
        'A_main': 'rendering main effect (counts vs none), averaged over B',
        'B_main': 'policy-reminder main effect, averaged over A',
        'AB_interaction': 'whether the reminder effect depends on counts '
                          'being present (and vice-versa)'},
    'causal_claim_limit': 'Factor effects are BEHAVIOURAL and do not '
        'uniquely identify an internal failure mechanism. An A effect '
        'supports a VERIFICATION ASSISTANCE account (counts may reduce a '
        'comparison/computation error OR merely raise operand salience; '
        'these are not separable here). A B effect supports a POLICY '
        'SALIENCE account (re-attention to the asymmetric rule OR a '
        'length/prominence nudge; not separable). A nonzero AB interaction '
        'means the two interventions are interdependent. Do NOT state that '
        'A/B isolates the model\'s unique internal cause of error.',
    'bootstrap': {'unit': 'instance_id', 'seed': SEED, 'n_boot': N_BOOT,
                  'type': 'paired percentile, resample 10 clusters'},
    'interpretation_gate': 'attribute an observed effect to a factor ONLY '
                           'via its orthogonal arm, and only at the '
                           'assistance/salience behavioural level; the A0B0 '
                           'arm is the frozen Gate-2 structured observation '
                           'reused, not a new call',
    'pooling': 'never pooled with E1/CEE/Gate-2 raw/adjudicated scores',
}


def write_outputs(items, payloads, fps, checks, mock_rows, analysis,
                  budgets, fact_table, fact_val_bad):
    V21_LAYERS.mkdir(parents=True, exist_ok=True)
    for pid, b in payloads.items():
        (V21_LAYERS / f'{pid}.txt').write_bytes(b)

    design_manifest = {
        'v21_version': V21_VERSION,
        'generated_by': 'evidence/eal_v21_design.py',
        'live_code_path_exists': False,
        'n_items': len(items), 'n_conditions': 4,
        'n_unique_instances': len({i['instance_id'] for i in items}),
        'conditions': {
            'a0b0': 'frozen Gate-2 structured, byte-identical (control)',
            'a1b0': 'Gate-2 structured + TABLE 0 deterministic counts',
            'a0b1': 'Gate-2 structured + asymmetric-rule reminder (head)',
            'a1b1': 'both interventions'},
        'factor_a_spec': {'name': 'rendering_counts',
                          'mechanism': 'salience of operand disagreement / '
                                       'absence; no verdict boolean',
                          'mean_added_bytes':
                              items[0]['conditions']['a1b0'][
                                  'delta_bytes_vs_a0b0']},
        'factor_b_spec': {'name': 'policy_reminder',
                          'mechanism': 'salience of frozen asymmetric rule; '
                                       'verbatim quotes only',
                          'quotes_verbatim_from_frozen_head': B_QUOTES,
                          'added_bytes':
                              items[0]['conditions']['a0b1'][
                                  'delta_bytes_vs_a0b0']},
        'condition_prompt_fingerprints': fps,
        'items': items}
    DESIGN_MANIFEST.write_text(
        json.dumps(design_manifest, ensure_ascii=False, indent=2,
                   sort_keys=True) + '\n', encoding='utf-8')

    freeze = {
        'document': 'v2.1 pre-implementation OFFLINE freeze (design gate)',
        'v21_version': V21_VERSION, 'created_before_any_paid_call': True,
        'system_message_sha256': _sha(eal.SYSTEM_MESSAGE.encode()),
        'review_goal_sha256': _sha(eal.REVIEW_GOAL.encode()),
        'decision_schema_sha256': _sha(json.dumps(
            eal.DECISION_SCHEMA, sort_keys=True).encode()),
        'payload_sha256': {pid: {'sha256': _sha(b), 'bytes': len(b)}
                           for pid, b in sorted(payloads.items())},
        'gold': [{k: it[k] for k in
                  ('bundle_id', 'instance_id', 'cee_gold', 'evidence_class',
                   'layer_gold_determined', 'underdetermined_channels')}
                 for it in items],
        'code_sha256': {
            'eal_v21_design.py':
                _sha((ROOT / 'evidence' / 'eal_v21_design.py').read_bytes()),
            'eal_protocol.py':
                _sha((ROOT / 'evidence' / 'eal_protocol.py').read_bytes()),
            'eal_gate2_freeze.py':
                _sha((ROOT / 'evidence' / 'eal_gate2_freeze.py').read_bytes())},
        'scoring_preregistration': SCORING_PREREG,
        'contradiction_rubric_operand_facts': fact_table,
        'contradiction_fact_validation_vs_g25_8cases': fact_val_bad,
        'budget_envelopes_separate_arms': budgets}
    FREEZE_MANIFEST.write_text(
        json.dumps(freeze, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')

    V21_RUNS.mkdir(parents=True, exist_ok=True)
    mp = V21_RUNS / 'eal_v21_mock_oracle_results.jsonl'
    with mp.open('w', encoding='utf-8') as f:
        for r in mock_rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    pre = {'document': 'v2.1 offline preflight (design gate; no paid call '
                       'can be made by this module)',
           'n_checks': len(checks) + 2,
           'checks': checks + [
               {'check': 'mock: oracle responder scores 88/88 per model',
                'pass': all(v['per_condition'][c]['da'] == 1.0
                            for v in analysis.values() for c in CONDITIONS),
                'detail': json.dumps(
                    {m: {c: analysis[m]['per_condition'][c]['da']
                         for c in CONDITIONS} for m in analysis})},
               {'check': 'rubric: operand flags reproduce all 8 G2.5 '
                         'case attributions',
                'pass': not fact_val_bad, 'detail': str(fact_val_bad)}],
           'mock_analysis_2x2': analysis,
           'all_pass': False}
    pre['all_pass'] = all(c['pass'] for c in pre['checks'])
    PREFLIGHT.write_text(json.dumps(pre, ensure_ascii=False, indent=2)
                         + '\n', encoding='utf-8')
    return pre


def main():
    items, payloads, fps = build_design()
    checks = run_audits(items, payloads, fps)
    mock_rows = mock_run(items, payloads)
    analysis = analyze(mock_rows)
    budgets = budget_envelopes(items, payloads)
    fact_table, fact_val_bad = contradiction_facts(items)
    pre = write_outputs(items, payloads, fps, checks, mock_rows, analysis,
                        budgets, fact_table, fact_val_bad)
    print(f'v2.1 design built: {len(payloads)} payloads -> {V21_DIR}')
    print(f'  A delta bytes/item: '
          f"{items[0]['conditions']['a1b0']['delta_bytes_vs_a0b0']}; "
          f"B delta bytes/item: "
          f"{items[0]['conditions']['a0b1']['delta_bytes_vs_a0b0']}")
    for c in checks + pre['checks'][-2:]:
        print(('PASS ' if c['pass'] else 'FAIL ') + c['check']
              + ('' if c['pass'] else f" -> {c['detail']}"))
    print('\nSeparate budget envelopes:')
    print('  ablation 2x2: '
          f"${budgets['ablation_arm']['total_estimate_usd']} "
          '(88 cells/model, both models)')
    r = budgets['reliability_arm']
    print(f"  reliability r=2: ${r['total_new_calls_estimate_usd']} "
          '(66 frozen cells/model x 2 new repeats, both models; Gate-2 '
          'original kept as a separate time point)')
    print(f"\nV2.1 PREFLIGHT all_pass={pre['all_pass']}; zero network, "
          'zero spend; no live code path exists in this module.')
    if not pre['all_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
