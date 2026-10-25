"""EAL offline renderer — build RAW / STRUCTURED / ADJUDICATED evidence bytes
for the frozen 22 fixtures, READ-ONLY against every frozen store.

Reads (never modified):
  evidence_store_w21/{phase2,phase3,wave2}_fixtures.jsonl
  evidence_store_w21/wave2_pilot_raw_rows.jsonl
  evidence_store_w21/artifacts|logs|attestations/...
  evidence_store/probes/<instance_id>.py            (when archived)
  evidence_store_cee/bundles/<cee_bundle_id>.txt    (adjudicated arm: the
                                                     frozen CEE bytes reused
                                                     byte-for-byte)

Writes only into evidence_store_eal/:
  layers/<bundle_id>__<layer>.txt   exact user-turn bytes per layer
  eal_materials_manifest.json       operand/channel inventory + hashes

The ADJUDICATED arm is not re-rendered: the frozen CEE bundle bytes are
served as-is, which makes "EAL adjudicated == CEE v1.1" an equality of
bytes, not an aspiration.

    uv run --python 3.13 -m evidence.eal_render
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from evidence.schemas import canonical_dumps, make_artifact_id
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl, _executed_counts
from evidence.visibility import symptom_polarity
from evidence.views import neutralize_fixture
from evidence.prompts import CLAIM_POSITIVE
from evidence import eal_protocol as eal
from evidence import cee_protocol as cee

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = ROOT / 'evidence_store_w21'
PROBE_DIR = ROOT / 'evidence_store' / 'probes'
CEE_DIR = ROOT / 'evidence_store_cee'
DEFAULT_OUT = ROOT / 'evidence_store_eal'
FIXTURE_FILES = ('phase2_fixtures.jsonl', 'phase3_fixtures.jsonl',
                 'wave2_fixtures.jsonl')
RAW_FILE = 'wave2_pilot_raw_rows.jsonl'

LOG_NAMES = ('f2p', 'p2p', 'p2p_baseline', 'symptom')

# ---------------------------------------------------------------------------
# Host-local redaction (deterministic; original bytes' digest stays visible)
# ---------------------------------------------------------------------------
_UV_CACHE_RE = re.compile(
    r'(?:[A-Za-z]:\\Users\\[^\\\s"\r\n]+|(?:\.\.[\\/])+)?[\\/]?'
    r'AppData\\Local\\uv\\cache\\(?:builds-v0|archive-v0)'
    r'(?:[\\/][^\s\r\n"]*)?')
_UV_PYTHON_RE = re.compile(
    r'(?:[A-Za-z]:\\Users\\[^\\\s"\r\n]+|(?:\.\.[\\/])+)?[\\/]?'
    r'AppData\\Roaming\\uv(?:[\\/][^\s\r\n"]*)?')
# Order matters: longest/most specific patterns first, the home-directory
# fallback last (otherwise it would leave an "\AppData\..." tail behind).
_REDACTIONS = (
    (re.compile(r'[A-Za-z]:\\Users\\[^\\]+?\\work\\eeeeiiii\\stance_pilot'
                r'(?:[\\/][^\s\r\n"]*)?'), '<REPO_WORKTREE>'),
    (re.compile(r'<HOME>\\work\\eeeeiiii\\stance_pilot'
                r'(?:[\\/][^\s\r\n"]*)?'), '<REPO_WORKTREE>'),
    (_UV_CACHE_RE, '<UV_CACHE>'),
    (_UV_PYTHON_RE, '<UV_PYTHON_HOME>'),
    (re.compile(r'(?:\.\.[\\/])+AppData[\\/][^\s\r\n"]*'), '<UV_CACHE>'),
    (re.compile(r'[A-Za-z]:\\Users\\[^\\\s"\r\n]+'), '<HOME>'),
)


def redact_host(text: str | None) -> str:
    if text is None:
        return ''
    out = text
    for rx, rep in _REDACTIONS:
        out = rx.sub(rep, out)
    return out.replace('\r\n', '\n')


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


# ---------------------------------------------------------------------------
# Material loading
# ---------------------------------------------------------------------------

def load_index(store_root: Path):
    paths = [str(store_root / f) for f in FIXTURE_FILES]
    fixtures = []
    for fp in paths:
        fixtures.extend(read_jsonl(fp))
    fx_by_key = {(f['scenario'], f['id'], f['served_artifact_id']): f
                 for f in fixtures}
    raw_by_id = {r['id']: r
                 for r in read_jsonl(str(store_root / RAW_FILE))}
    cee_gold = { (g['scenario'], g['id'], g['served_artifact_id']): g
                 for g in (json.loads(l) for l in
                           (CEE_DIR / 'cee_gold.jsonl').read_text(
                               encoding='utf-8').splitlines() if l.strip())}
    ordered = [fx_by_key[k] for k in cee_gold]
    return ordered, raw_by_id, cee_gold


def load_materials(store: ArtifactStore, fx: dict):
    """Extract every primary operand for one fixture from the frozen store.
    Nothing here is a linked/fresh/complete verdict — only records,
    attestations, logs and target hashes."""
    aid = fx['served_artifact_id']
    rec, authentic = store.get(aid)
    if not authentic:
        raise SystemExit(f'eal_render: inauthentic artifact {aid}')
    att = store.get_attestation(fx['instance_id'], fx['patch_sha256'])
    logs = {}
    for name in LOG_NAMES:
        p = store.root / 'logs' / f'{aid}.{name}.log'
        if p.exists():
            logs[name] = p.read_text(encoding='utf-8', errors='replace')
    probe_src_path = PROBE_DIR / f"{fx['instance_id']}.py"
    probe_source = (probe_src_path.read_text(encoding='utf-8', errors='replace')
                    if probe_src_path.exists() else None)
    # Display copy through the FROZEN neutraliser chokepoint (scenario token
    # / runner token / scope-rule answer leak removed), declared=None so the
    # record's own executed scope is preserved for the model to compare
    # against the attestation.
    disp = neutralize_fixture(rec, fx['instance_id'], fx['patch_sha256'],
                              declared=None)
    att_pub = None
    if att is not None:
        att_pub = {k: v for k, v in att.items()
                   if k != '_attestation_authentic'}
    return {
        'target': {
            'instance_id': fx['instance_id'],
            'base_commit': fx['base_commit'],
            'patch_sha256': fx['patch_sha256'],
        },
        'record': disp,
        'attestation': att_pub,
        'logs': logs,
        'probe_source': probe_source,
        'symptom_fixture': fx.get('symptom'),
    }


# ---------------------------------------------------------------------------
# Probe-log parsing (deterministic; exit codes + assertion lines, NO verdict)
# ---------------------------------------------------------------------------

_PROBE_SEC_RE = re.compile(r'###\s*(BASELINE \(pre-patch\)|POST candidate patch)')
_EXIT_RE = re.compile(r'^\$.*?\(exit\s+(-?\d+)\)', re.M)
_ASSERT_RE = re.compile(r'^(FAIL|ERROR|PASS|OK)\b.*$', re.M)


def parse_probe_log(symptom_log: str | None):
    """Split the frozen symptom log into pre/post sections and extract the
    command, exit code and assertion/result lines for each. The persistence
    VERDICT is never computed here — only what the runs printed."""
    if not symptom_log:
        return None
    secs = list(_PROBE_SEC_RE.finditer(symptom_log))
    out = {}
    for i, m in enumerate(secs):
        start = m.end()
        end = secs[i + 1].start() if i + 1 < len(secs) else len(symptom_log)
        body = symptom_log[start:end]
        ex = _EXIT_RE.search(body)
        cmd = body.strip().splitlines()[0] if body.strip() else ''
        stdout = body.split('--- stdout ---', 1)
        so = stdout[1] if len(stdout) == 2 else ''
        so = so.split('--- stderr ---', 1)[0]
        lines = [ln.rstrip() for ln in so.splitlines() if ln.strip()]
        key = 'pre' if 'BASELINE' in m.group(1) else 'post'
        out[key] = {
            'command': cmd.strip(),
            'exit_code': int(ex.group(1)) if ex else None,
            'result_lines': lines,
        }
    return out


def parse_pytest_log(log: str | None):
    """Extract command/exit and the pytest summary line from a runner log."""
    if not log:
        return None
    first = log.strip().splitlines()[0] if log.strip() else ''
    ex = re.search(r'\(exit\s+(-?\d+)\s*(?:,[^)]*)?\)', first)
    summ = re.search(r'^=+ .*?(?:passed|failed).*?=+$', log, re.M)
    return {
        'command': first,
        'exit_code': int(ex.group(1)) if ex else None,
        'pytest_summary_line': summ.group(0).strip() if summ else None,
    }


# ---------------------------------------------------------------------------
# RAW rendering
# ---------------------------------------------------------------------------

def _json_block(title: str, obj) -> str:
    return (f'--- {title} ---\n'
            + json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
            + '\n')


def render_raw_body(*, issue: str, patch: str, claim: str, mat: dict) -> str:
    t = mat['target']
    s = []
    s.append('RAW EVIDENCE PACKAGE (protocol eal-v0-draft1).')
    s.append(f"\n\nISSUE:\n{issue}")
    s.append(f"\n\nPATCH:\n{patch}")
    s.append(f"\n\nAUTHOR STATEMENT:\n{claim}")
    s.append('\n\n=== TARGET PATCH UNDER REVIEW ===')
    s += ['instance_id: ' + t['instance_id'],
          'base_commit: ' + t['base_commit'],
          'patch_sha256: ' + t['patch_sha256']]
    s.append('\n\n=== REPOSITORY ATTESTATION (maintainers’ separately-signed '
             'declaration) ===')
    if mat['attestation'] is not None:
        s.append(_json_block('ATTESTATION RECORD', mat['attestation']))
    else:
        s.append('(no attestation retained in the archive)')
    s.append('\n=== SIGNED CI RUN RECORD (what the runner actually executed) '
             '===')
    s.append(_json_block('RUN RECORD', mat['record']))
    s.append('\n=== RUNNER LOGS (verbatim except host-local path redaction; '
             'digests below are of the ORIGINAL pre-redaction bytes and match '
             'the run record log_digests) ===')
    titles = {
        'f2p': 'FAIL_TO_PASS acceptance run (post-patch)',
        'p2p': 'scoped PASS_TO_PASS run (post-patch)',
        'p2p_baseline': 'scoped PASS_TO_PASS run at BASE commit',
        'symptom': 'issue-symptom probe (pre-patch + post-patch)',
    }
    for name in LOG_NAMES:
        text = mat['logs'].get(name)
        s.append(f"\n--- LOG: {name} ({titles[name]}) ---")
        if text is None:
            s.append('(log not retained in the archive)')
            continue
        digest = (mat['record'].get('log_digests') or {}).get(name)
        s.append(f'[original log sha256: {digest if digest else "n/a"}]')
        s.append(redact_host(text).rstrip('\n'))
    if mat['probe_source'] is not None:
        s.append('\n\n=== ISSUE-SYMPTOM PROBE SOURCE (executable check '
                 'derived from the issue text; exit 0 = symptom assertion '
                 'does not fire, non-zero = it fires) ===')
        s.append(redact_host(mat['probe_source']).rstrip('\n'))
    else:
        s.append('\n\n(Probe source file was not retained in the archive; '
                 'the pre/post probe outputs above are the only record of '
                 'what the probe asserted.)')
    return ''.join(s)


# ---------------------------------------------------------------------------
# STRUCTURED rendering
# ---------------------------------------------------------------------------

def _table(headers: list[str], rows: list[list[str]]) -> str:
    rows = [[('' if c is None else str(c)) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    line = lambda cells: ' | '.join(
        c.ljust(widths[i]) for i, c in enumerate(cells))
    out = [line(headers), '-+-'.join('-' * w for w in widths)]
    out += [line(r) for r in rows]
    return '\n' + '\n'.join(out)


def render_structured_body(*, issue: str, patch: str, claim: str,
                           mat: dict) -> str:
    t, rec, att = mat['target'], mat['record'], mat['attestation']
    s = []
    s.append('STRUCTURED EVIDENCE PACKAGE (protocol eal-v0-draft1). '
             'Deterministic parse of the same primary records; every table '
             'shows operands, not verdicts.')
    s.append(f"\n\nISSUE:\n{issue}")
    s.append(f"\n\nPATCH:\n{patch}")
    s.append(f"\n\nAUTHOR STATEMENT:\n{claim}")

    # 1. Identity operands (no match column on purpose).
    s.append('\n\n=== TABLE 1 — IDENTITY OPERANDS ===')
    s.append(_table(
        ['field', 'TARGET under review', 'value inside SIGNED RUN RECORD'],
        [['base_commit', t['base_commit'], rec.get('base_commit', '')],
         ['patch_sha256', t['patch_sha256'], rec.get('patch_sha256', '')]]))

    # 2. Run-tree operands.
    s.append('\n\n=== TABLE 2 — RUN-TREE OPERANDS ===')
    s.append(_table(
        ['item', 'value'],
        [['git tree of the signed run', str(rec.get('run_tree'))],
         ['expected canonical tree declared in the attestation',
          str(att['expected_run_tree']) if att else '(no attestation)'],
         ['attestation base_commit',
          str(att['base_commit']) if att else '(no attestation)'],
         ['attestation patch_sha256',
          str(att['patch_sha256']) if att else '(no attestation)'],
         ['attestation built_at',
          str(att.get('built_at')) if att else '(no attestation)'],
         ['run started_at / finished_at',
          f"{rec.get('started_at')} / {rec.get('finished_at')}"]]))

    # 3. Declared vs executed sets (membership parse only; no universal
    #    "fully executed" verdict).
    decl_f2p = sorted(att['declared_fail_to_pass']) if att else []
    decl_p2p = sorted(att['declared_p2p_scoped']) if att else []
    f2p_map = rec.get('fail_to_pass') or {}
    p2p_map = rec.get('pass_to_pass_scoped') or {}
    base_map = rec.get('pass_to_pass_baseline') or {}
    s.append('\n\n=== TABLE 3 — DECLARED SETS (attestation) ===')
    s.append(_table(['set', 'n', 'ids'],
                    [['declared FAIL_TO_PASS', str(len(decl_f2p)),
                      ', '.join(decl_f2p) or '(empty)'],
                     ['declared scoped PASS_TO_PASS', str(len(decl_p2p)),
                      ', '.join(decl_p2p) or '(empty)']]))
    s.append('\n\n=== TABLE 4 — PER-CHECK EXECUTION JOIN (parsed from the '
             'signed record maps; membership + statuses, no applicability '
             'verdict) ===')
    ids = sorted(set(decl_f2p) | set(decl_p2p)
                 | set(f2p_map) | set(p2p_map) | set(base_map))
    rows = []
    for tid in ids:
        declared = ('fail_to_pass' if tid in decl_f2p else '') \
            + ('pass_to_pass' if tid in decl_p2p else '') \
            or 'not_declared'
        executed = '+'.join(x for x, m in
                            (('f2p', f2p_map), ('p2p_post', p2p_map),
                             ('p2p_base', base_map)) if tid in m) or 'absent'
        rows.append([tid, declared, executed,
                     str(f2p_map.get(tid, '-')),
                     str(p2p_map.get(tid, '-')),
                     str(base_map.get(tid, '-'))])
    s.append(_table(
        ['test_id', 'declared_as', 'present_in',
         'f2p_post_status', 'p2p_post_status', 'p2p_base_status'], rows))

    # 5. Runner's own aggregated summary (as recorded).
    summ = rec.get('summary') or {}
    scope = rec.get('scope') or {}
    s.append('\n\n=== TABLE 5 — RECORD SUMMARY FIELDS (as recorded by the '
             'runner) ===')
    s.append(_table(['field', 'value'], [
        ['f2p passed / total',
         f"{summ.get('f2p_passed')} / {summ.get('f2p_total')}"],
        ['f2p failed ids', ', '.join(summ.get('f2p_failed_ids') or []) or '-'],
        ['p2p passed / total',
         f"{summ.get('p2p_passed')} / {summ.get('p2p_total')}"],
        ['p2p regressed ids (runner-classified)',
         ', '.join(summ.get('p2p_regressed_ids') or []) or '-'],
        ['p2p pre-existing-bad ids (runner-classified)',
         ', '.join(summ.get('p2p_preexisting_bad_ids') or []) or '-'],
        ['scope rule', str(scope.get('rule'))],
        ['scoped files n', str(len(scope.get('p2p_scoped_files') or []))],
        ['test_patch_applied_cleanly',
         str((scope.get('test_patch_applied_cleanly')))],
    ]))

    # 6. Parsed runner-log headers (commands, exit codes, pytest summaries).
    s.append('\n\n=== TABLE 6 — PARSER RESULT PER RUNNER LOG ===')
    log_rows = []
    for name in LOG_NAMES:
        if name == 'symptom':
            continue
        p = parse_pytest_log(mat['logs'].get(name))
        log_rows.append([name,
                         redact_host(p['command']) if p
                         else '(log not retained)',
                         str(p['exit_code']) if p else '-',
                         redact_host(p['pytest_summary_line']) if p else '-'])
    s.append(_table(['log', 'command', 'exit_code', 'pytest_summary'],
                    log_rows))

    # 7. Parsed probe outputs (pre/post operands; NO present/persists
    #    verdict).
    probe = parse_probe_log(mat['logs'].get('symptom'))
    s.append('\n\n=== TABLE 7 — ISSUE-SYMPTOM PROBE, PARSED PRE/POST '
             'OPERANDS ===\n'
             'Instrument semantics: this executable probe is derived from '
             'the issue text; exit 0 = its symptom assertion did not fire, '
             'non-zero = the assertion fired (see result lines for what was '
             'observed).')
    if probe:
        for key, label in (('pre', 'pre-patch BASELINE'),
                           ('post', 'post-patch CANDIDATE')):
            sec = probe.get(key)
            if not sec:
                s.append(f'\n[{label}] (section absent)')
                continue
            s.append(f"\n[{label}]")
            s.append(f"  command: {sec['command']}")
            s.append(f"  exit_code: {sec['exit_code']}")
            s.append('  result_lines:')
            if sec['result_lines']:
                s += [f'    {ln}' for ln in sec['result_lines']]
            else:
                s.append('    (none)')
    else:
        s.append('(symptom probe log not retained)')
    if mat['probe_source'] is not None:
        s.append('\n[probe source retained] the executable probe source is '
                 'available in the RAW condition of this same item.')
    else:
        s.append('\n[probe source not retained in the archive]')
    return ''.join(s)


# ---------------------------------------------------------------------------
# Per-layer fact recovery / gold sufficiency (oracle-side audit inputs)
# ---------------------------------------------------------------------------

def recoverable_facts(mat: dict) -> dict:
    """Which gold operands are recoverable from THIS material set, and their
    recovered values. Deterministic and layer-independent: RAW and
    STRUCTURED expose the same operands (verbatim vs parsed). Any operand
    whose primary material is missing is reported as channel_available=False
    (value stays None) so per-layer gold can be marked underdetermined."""
    t, rec, att = mat['target'], mat['record'], mat['attestation']
    channels = {
        'identity_fields': True,
        'attestation': att is not None,
        'f2p_map': bool(rec.get('fail_to_pass')),
        'p2p_map': bool(rec.get('pass_to_pass_scoped')),
        'p2p_baseline_map': bool(rec.get('pass_to_pass_baseline')),
        'symptom_log': mat['logs'].get('symptom') is not None,
        'probe_source_archived': mat['probe_source'] is not None,
        'acceptance_logs': all(mat['logs'].get(n) is not None
                               for n in ('f2p', 'p2p', 'p2p_baseline')),
    }
    vals = {
        'linked': (rec.get('base_commit') == t['base_commit']
                   and rec.get('patch_sha256') == t['patch_sha256']),
        'fresh': None, 'complete': None,
        'acceptance_failure': None, 'acceptance_success': None,
        'symptom_persists': None,
    }
    if att is not None:
        vals['fresh'] = (rec.get('base_commit') == t['base_commit']
                         and rec.get('run_tree') == att['expected_run_tree'])
        executed = set((rec.get('fail_to_pass') or {})) \
            | set((rec.get('pass_to_pass_scoped') or {}))
        declared = set(att['declared_fail_to_pass']) \
            | set(att['declared_p2p_scoped'])
        vals['complete'] = all(d in executed for d in declared)
    failure, executed_n = _executed_counts(rec)
    if executed_n > 0 or channels['f2p_map'] or channels['p2p_map']:
        vals['acceptance_failure'] = failure > 0
        vals['acceptance_success'] = executed_n > 0 and failure == 0
    pol = symptom_polarity(mat['symptom_fixture']) \
        if mat.get('symptom_fixture') else None
    # Independently confirm the polarity from the RAW LOG (not from fixture
    # metadata): pre fires and post fires => persists.
    probe = parse_probe_log(mat['logs'].get('symptom'))
    log_pol = None
    if probe and probe.get('pre') and probe.get('post'):
        pre_fire = probe['pre']['exit_code'] not in (0, None)
        post_fire = probe['post']['exit_code'] not in (0, None)
        log_pol = 'persists' if (pre_fire and post_fire) else (
            'gone' if (pre_fire and not post_fire) else None)
    if pol is not None and log_pol is not None and pol != log_pol:
        raise SystemExit(
            f"eal_render: symptom polarity mismatch fixture={pol} "
            f"log={log_pol} for {t['instance_id']}")
    if log_pol is not None:
        vals['symptom_persists'] = (log_pol == 'persists')
    return {'channels': channels, 'values': vals,
            'symptom_polarity_from_log': log_pol}


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _bundle_id(scenario, fid, aid):
    return 'cee_' + hashlib.sha256(
        f'{scenario}|{fid}|{aid}'.encode('utf-8')).hexdigest()[:16]


def build_all(store_root: Path):
    fixtures, raw_by_id, cee_gold = load_index(store_root)
    store = ArtifactStore(str(store_root))
    rows, payloads = [], {}
    fps = {l: eal.layer_prompt_fingerprint(l) for l in eal.LAYERS}
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        grow = cee_gold[key]
        raw = raw_by_id[fx['id']]
        claim = fx.get('claim') or CLAIM_POSITIVE
        mat = load_materials(store, fx)
        recov = recoverable_facts(mat)
        gold, determined, unknown = eal.gold_from_facts(**recov['values'])

        bodies = {
            'raw': render_raw_body(issue=raw['problem_statement'],
                                   patch=raw['model_patch'], claim=claim,
                                   mat=mat),
            'structured': render_structured_body(
                issue=raw['problem_statement'], patch=raw['model_patch'],
                claim=claim, mat=mat),
        }
        bid = _bundle_id(*key)
        per_layer = {}
        for layer in ('raw', 'structured'):
            user = eal.render_user_content(layer, bodies[layer])
            ub = user.encode('utf-8')
            pid = f'{bid}__{layer}'
            payloads[pid] = ub
            per_layer[layer] = {
                'payload_id': pid,
                'bytes': len(ub),
                'sha256': hashlib.sha256(ub).hexdigest(),
                'prompt_fingerprint': fps[layer],
            }
        # Adjudicated: serve the frozen CEE bytes verbatim and assert equality.
        cee_bytes = (CEE_DIR / 'bundles' / f'{bid}.txt').read_bytes()
        pid = f'{bid}__adjudicated'
        payloads[pid] = cee_bytes
        per_layer['adjudicated'] = {
            'payload_id': pid,
            'bytes': len(cee_bytes),
            'sha256': hashlib.sha256(cee_bytes).hexdigest(),
            'prompt_fingerprint': fps['adjudicated'],
            'identical_to_frozen_cee_bundle': True,
        }
        rows.append({
            'bundle_id': bid,
            'scenario': fx['scenario'], 'id': fx['id'],
            'instance_id': fx['instance_id'],
            'served_artifact_id': fx['served_artifact_id'],
            'base_commit': fx['base_commit'],
            'patch_sha256': fx['patch_sha256'],
            'cee_gold': grow['cee_gold'],
            'evidence_class': grow['evidence_class'],
            'recoverable_values': recov['values'],
            'channels': recov['channels'],
            'symptom_polarity_from_log': recov['symptom_polarity_from_log'],
            'layer_gold_determined_from_visible_materials': determined,
            'layer_gold': gold,
            'gold_matches_oracle_when_determined':
                (gold == grow['cee_gold']) if determined else None,
            'underdetermined_channels': unknown,
            'layers': per_layer,
        })
    manifest = {
        'eal_protocol_version': eal.EAL_PROTOCOL_VERSION,
        'generated_by': 'evidence/eal_render.py',
        'store_root_read_only': str(store_root),
        'n_items': len(rows),
        'n_unique_instances': len({r['instance_id'] for r in rows}),
        'layer_prompt_fingerprints': fps,
        'adjudicated_arm': 'frozen CEE v1.1 bundles served byte-identical; '
                           'EAL and CEE adjudicated scores must never be '
                           'pooled with raw/structured (abstraction differs)',
        'items': rows,
    }
    return rows, manifest, payloads


def write_outputs(out_root: Path, rows, manifest, payloads):
    out_root = Path(out_root)
    ldir = out_root / 'layers'
    ldir.mkdir(parents=True, exist_ok=True)
    for pid, b in payloads.items():
        (ldir / f'{pid}.txt').write_bytes(b)
    (out_root / 'eal_materials_manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
        + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=str(DEFAULT_STORE))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    a = ap.parse_args()
    out_root = Path(a.out)
    try:
        out_root.resolve().relative_to(DEFAULT_OUT.resolve())
    except ValueError:
        raise SystemExit(f'EAL SAFETY: output must live under {DEFAULT_OUT}')
    rows, manifest, payloads = build_all(Path(a.store))
    write_outputs(out_root, rows, manifest, payloads)
    n_det = sum(r['layer_gold_determined_from_visible_materials'] for r in rows)
    n_match = sum(r['gold_matches_oracle_when_determined'] for r in rows)
    print(f'EAL render OK: {len(rows)} items x 3 layers -> {out_root}')
    print(f'  layer-gold determined from visible materials: {n_det}/'
          f'{len(rows)} (raw & structured share operands)')
    print(f'  determined gold == frozen CEE oracle: {n_match}/{len(rows)}')
    for layer in eal.LAYERS:
        bs = [r['layers'][layer]['bytes'] for r in rows]
        print(f'  {layer:12s} bytes min/median/max: '
              f'{min(bs)}/{sorted(bs)[len(bs)//2]}/{max(bs)}')
    print('  offline only: read frozen stores; zero network / zero paid calls')


if __name__ == '__main__':
    main()
