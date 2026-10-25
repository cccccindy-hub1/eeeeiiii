"""Phase-3 TERNARY runner: evidence sufficiency as a three-way decision.

Conditions (protocol='ternary'; all cells register the author claim):
  T2D-T          static diagnostic projection, no tools
  T3D-Strict     tools under policy=strict (acceptance logs hard-denied 403;
                 consistency adjudicated only from the symptom diagnostic)
  T3D-Escalate   tools under policy=escalate (acceptance log / acceptance-based
                 consistency require a non-empty reason; 400 -> audit -> grant)
  T2A-T          static full acceptance artifact (baseline)
  T3A-T          tools at the acceptance tier (baseline)

Outcomes are ACCEPT / REJECT / NEED_EVIDENCE, parsed by evidence.ternary;
INVALID/AMBIGUOUS are protocol failures scored separately (never a correct
rejection). Results go to a DEDICATED file (phase3_ternary_results.jsonl);
Phase-1/2 result files are never touched.

--mock runs a scripted, deterministic "model" against a REAL local evidence
server over REAL HTTP, exercising the full multi-turn tool loop including the
400/403/granted escalation paths, at zero cost. Mock rows carry mock=true and
are excluded from research metrics; per-cell traces are written to
--mock-trace-dir.

Usage:
  python -m evidence.phase3_run --mock --spawn-server \
      --fixtures evidence_store/phase2_fixtures.jsonl
  python -m evidence.phase3_run --model-profile deepseek --model deepseek-flash \
      --max-budget-usd 0.30
"""
from __future__ import annotations

import argparse, hashlib, json, os, re, threading, time, urllib.request
from pathlib import Path
from urllib.parse import urlencode

from pilot import read_jsonl
from evidence.prompts import (build_ternary_messages, build_ternary_messages_v2,
                              ternary_tools, ternary_condition_tier_policy,
                              TERNARY_CONDITIONS, TERNARY_PROMPT_VERSION,
                              TERNARY_PROMPT_VERSION_V2,
                              ternary_prompt_fingerprint,
                              ternary_prompt_fingerprint_v2)
from evidence.gap_w2 import classify_abstention
from evidence.ternary import parse_ternary_decision, TERNARY_DECISION_SCHEMA
from evidence.runner import EvidenceClient

PROMPT_VERSIONS = (TERNARY_PROMPT_VERSION, TERNARY_PROMPT_VERSION_V2)


def _sha256_text_normalized(path):
    """Wave-2 identity hash: read_text() newline-normalised (Windows lands
    CRLF) then utf-8. MUST match evidence.metrics_w2.load_w2_gold's hashing."""
    return hashlib.sha256(
        Path(path).read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def _parse_answer_json(final):
    """Parse the final answer object, tolerating a ```json fence. Returns
    {} on any parse problem (never raises)."""
    text = (final or '').strip()
    if text.startswith('```'):
        text = text.strip('`')
        if text.lower().startswith('json'):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def symptom_persists_from_trace(trace):
    """Mechanically read the issue-symptom probe verdict from the tool trace:
    the first ``$ python <name>.py  (exit N)`` line AFTER the
    '### POST candidate patch' marker of the symptom get_run_log result.
    exit 1 -> True (symptom still reproduces), exit 0 -> False. None when no
    readable 200 symptom log with a POST section is present. The result
    preview (1200 chars) covers the POST exit line for every wave-2 fixture
    (audited TR-9.1)."""
    for t in trace:
        if t.get('tool') != 'get_run_log':
            continue
        if (t.get('args') or {}).get('name', 'symptom') != 'symptom':
            continue
        if t.get('http_status') != 200:
            continue
        preview = t.get('result_preview') or ''
        idx = preview.find('### POST candidate patch')
        if idx < 0:
            continue
        m = re.search(r'\(exit (\d+)\)', preview[idx:])
        if m:
            return int(m.group(1)) != 0
    return None


def tool_verdicts_from_trace(rec):
    """Structured endpoint verdicts actually obtained in the cell, mirroring
    evidence.metrics_w2.derive_tool_verdicts' fallback derivation plus the
    mechanically parsed symptom polarity. Absent keys => not called."""
    tv = {}
    if rec.get('called_linkage'):
        tv['linkage'] = False if rec.get('saw_linked_false') else True
    if rec.get('called_freshness'):
        tv['freshness'] = False if rec.get('saw_fresh_false') else True
    if rec.get('called_coverage'):
        tv['coverage'] = False if rec.get('saw_coverage_incomplete') else True
    if rec.get('called_consistency'):
        tv['consistency'] = ('contradicted' if rec.get('saw_contradicted')
                             else 'consistent')
    sp = symptom_persists_from_trace(rec.get('tool_trace') or [])
    if sp is not None:
        tv['symptom_persists'] = sp
    return tv


class BudgetGuardStop(Exception):
    """Raised BEFORE a model call when the remaining budget cannot cover a
    conservative upper bound on that call's cost. Never raised after a call,
    so cumulative spend can never overshoot the cap."""

DEFAULT_PROFILES = {
    'deepseek': {'base_url': 'https://api.deepseek.com/v1',
                 'key_env': 'DEEPSEEK_API_KEY',
                 'price_in_per_1m': 0.30, 'price_out_per_1m': 1.20},
}
_ACCEPTANCE_LOGS = ('f2p', 'p2p', 'p2p_baseline')


class P3Client(EvidenceClient):
    """HTTP client aware of Phase-3 policies: reasons go on the query string
    for GET logs and in the JSON body for POST consistency."""

    def open_session(self, instance_id, base_commit, patch_sha256, cell,
                     served_artifact_id=None, evidence_tier='D', policy=None,
                     claim=None, symptom=None):
        return self._req('POST', '/sessions',
                         {'instance_id': instance_id, 'base_commit': base_commit,
                          'patch_sha256': patch_sha256, 'cell': cell,
                          'served_artifact_id': served_artifact_id,
                          'evidence_tier': evidence_tier, 'policy': policy,
                          'claim': claim, 'symptom': symptom})

    def _req_tool(self, method, path, obj=None, raw=False):
        import urllib.error
        try:
            return self._req(method, path, obj=obj, raw=raw)
        except urllib.error.HTTPError as he:
            body = he.read().decode('utf-8', errors='replace')
            if raw:
                return f'[http_status={he.code}] {body}'
            try:
                out = json.loads(body)
            except Exception:
                out = {'error': body[:500]}
            out['http_status'] = he.code
            return out

    def tool(self, sid, name, args, policy=None):
        args = args or {}
        if name == 'get_test_artifact':
            return self._req_tool('GET', f'/sessions/{sid}/artifact')
        if name == 'verify_artifact_linkage':
            return self._req_tool('GET', f'/sessions/{sid}/verify')
        if name == 'check_evidence_freshness':
            return self._req_tool('GET', f'/sessions/{sid}/freshness')
        if name == 'check_test_coverage':
            return self._req_tool('GET', f'/sessions/{sid}/coverage')
        if name == 'check_claim_consistency':
            body = {'claim': args.get('claim', '')}
            if policy == 'escalate' and args.get('reason'):
                body['reason'] = args['reason']
            return self._req_tool('POST', f'/sessions/{sid}/consistency', body)
        if name == 'get_run_log':
            logname = args.get('name', 'symptom')
            qs = ''
            if policy == 'escalate' and args.get('reason'):
                qs = '?' + urlencode({'reason': args['reason']})
            return self._req_tool('GET',
                                  f'/sessions/{sid}/log/{logname}{qs}', raw=True)
        return {'error': 'unknown tool', 'http_status': 400}


# ---------------------------------------------------------------------------
# Scripted mock model (zero-cost end-to-end pipeline exercise)
# ---------------------------------------------------------------------------

class _Fn:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, cid, name, args):
        self.id = cid
        self.type = 'function'
        self.function = _Fn(name, json.dumps(args))


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        d = {'role': 'assistant', 'content': self.content}
        if self.tool_calls is not None:
            d['tool_calls'] = [
                {'id': t.id, 'type': 'function',
                 'function': {'name': t.function.name,
                              'arguments': t.function.arguments}}
                for t in self.tool_calls]
        if exclude_none and d['content'] is None:
            d.pop('content')
        return d


class _Resp:
    def __init__(self, content=None, tool_calls=None, finish='stop'):
        self.choices = [type('C', (), {'message': _Msg(content, tool_calls),
                                       'finish_reason': finish})()]
        self.usage = type('U', (), {'prompt_tokens': 0,
                                    'completion_tokens': 0})()


class ScriptedModel:
    """Deterministic stand-in that follows the protocol-appropriate tool loop.
    It is NOT a subject: decisions are simple heuristics, rows are mock=true."""

    REASON = ('need maintainer acceptance verdict to decide mergeability after '
              'diagnostic integrity checks were inconclusive')

    # Wave-2 v2 scripted orchestration (TR-9.1). These are deliberate,
    # scenario-keyed exercise points; the mock is NOT a subject (rows carry
    # mock=true). Every other v2 cell follows the same endpoint heuristics as
    # v1, merely labelling its NEED_EVIDENCE with a grounded evidence_gap.
    V2_STATIC_PLAN = {
        # tier-D static (T2D-T): stale claims are unverifiable without tools;
        # the rendered persisting symptom is decisive even in the static block.
        'w2_stale': ('NEED_EVIDENCE', 'stale'),
        'w2_stale_bad': ('NEED_EVIDENCE', 'stale'),
        'w2_stale_persists': ('REJECT', None),
    }
    V2_ACTIVE_PLAN = {
        # Deliberate pipeline points on w2_stale_persists: at Strict/Escalate
        # the reviewer abstains despite decisive accessible contradiction
        # (distinct error class); at T3A it correctly REJECTs on the symptom.
        ('w2_stale_persists', 'T3D-Strict'): (
            'NEED_EVIDENCE', 'contradiction',
            'scripted abstention despite symptom-only contradicted verdict'),
        ('w2_stale_persists', 'T3D-Escalate'): (
            'NEED_EVIDENCE', 'contradiction',
            'scripted abstention despite the post-patch symptom log exiting 1'),
        ('w2_stale_persists', 'T3A-T'): (
            'REJECT', None,
            'the issue symptom still reproduces post-patch (symptom log '
            'POST exit 1), a decisive failure independent of acceptance runs'),
    }

    def __init__(self, cond, item=None,
                 prompt_version=TERNARY_PROMPT_VERSION):
        self.cond = cond
        self.item = item or {}
        self.active, self.tier, self.policy = ternary_condition_tier_policy(cond)
        self.prompt_version = prompt_version
        self.v2 = prompt_version == TERNARY_PROMPT_VERSION_V2
        self._n = 0

    def _call(self, name, args=None):
        self._n += 1
        return _Resp(tool_calls=[_TC(f'mock_{self._n}', name, args or {})],
                     finish='tool_calls')

    def _final(self, decision, reason, mismatch=False, missing='', gap=None):
        obj = {'decision': decision, 'reason': reason,
               'evidence_mismatch': bool(mismatch),
               'missing_evidence': missing}
        # v2 carries evidence_gap only on NEED_EVIDENCE (prompt p3-ternary-v2);
        # v1 answers stay byte-for-byte the old four-key object.
        if self.v2 and gap is not None:
            obj['evidence_gap'] = gap
        return _Resp(content=json.dumps(obj))

    @staticmethod
    def _presented_block_all_green(rec):
        """Mirror of evidence.gold_w2._presented_block_all_green for the v2
        tier-A static script: complete rendered run, every check green."""
        summ = rec.get('summary') or {}
        ft = int(summ.get('f2p_total') or 0)
        fp = int(summ.get('f2p_passed') or 0)
        pt = int(summ.get('p2p_total') or 0)
        pp = int(summ.get('p2p_passed') or 0)
        if ft + pt <= 0:
            return False
        if fp != ft or pp != pt:
            return False
        return not (summ.get('f2p_failed_ids')
                    or summ.get('p2p_regressed_ids'))

    def _heuristic_gap(self, fl):
        if fl['fresh'] is False:
            return 'stale'
        if fl['linked'] is False:
            return 'linkage_mismatch'
        if fl['complete'] is False:
            return 'coverage_incomplete'
        return 'unspecified'

    @staticmethod
    def _pairs(messages):
        """Reconstruct (tool_name, args, content) results from the transcript."""
        pend, out = {}, []
        for m in messages:
            role = m.get('role') if isinstance(m, dict) else None
            if role == 'assistant' and m.get('tool_calls'):
                for tc in m['tool_calls']:
                    try:
                        args = json.loads(tc['function']['arguments'] or '{}')
                    except Exception:
                        args = {}
                    pend[tc['id']] = (tc['function']['name'], args)
            elif role == 'tool':
                name, args = pend.pop(m['tool_call_id'], ('?', {}))
                out.append((name, args, m['content']))
        return out

    @staticmethod
    def _flags(pairs):
        f = {'artifact': None, 'linked': None, 'fresh': None, 'complete': None,
             'consistency': [], 'log_status': {}, 'banner': set()}
        for name, args, content in pairs:
            if name == 'get_test_artifact':
                try:
                    f['artifact'] = json.loads(content)['artifact']
                except Exception:
                    pass
            elif name == 'verify_artifact_linkage':
                try:
                    f['linked'] = json.loads(content).get('linked')
                except Exception:
                    pass
            elif name == 'check_evidence_freshness':
                try:
                    f['fresh'] = json.loads(content).get('fresh')
                except Exception:
                    pass
            elif name == 'check_test_coverage':
                try:
                    f['complete'] = json.loads(content).get('complete')
                except Exception:
                    pass
            elif name == 'check_claim_consistency':
                try:
                    f['consistency'].append(json.loads(content))
                except Exception:
                    pass
            elif name == 'get_run_log':
                nm = args.get('name', 'symptom')
                mstat = re.search(r'http_status=(\d+)', content or '')
                f['log_status'][nm] = int(mstat.group(1)) if mstat else 200
                if (content or '').startswith('# TIER ESCALATION'):
                    f['banner'].add(nm)
        return f

    def _decide(self, fl):
        # Applicability (evidence is about THIS patch/current tree) needs only
        # linked+fresh; completeness governs ACCEPT sufficiency, not REJECT.
        applicable = fl['linked'] is True and fl['fresh'] is True
        complete = fl['complete'] is True
        verdicts = [c.get('verdict') for c in fl['consistency']
                    if 'verdict' in c]
        contradicted = 'contradicted' in verdicts
        consistent = 'consistent' in verdicts
        if not applicable:
            # Unlinked/stale evidence cannot adjudicate THIS patch: even a
            # failure seen through inapplicable evidence is not decisive.
            return ('NEED_EVIDENCE', 'evidence is not linked/fresh for this patch '
                    'and current tree; any apparent failure does not apply here and '
                    'no decisive applicable failure is established', True,
                    'linked/fresh applicability')
        if contradicted:
            # Applicable evidence contains a decisive executed failure: REJECT
            # even if the declared set was not fully executed (asymmetric bar).
            return ('REJECT', 'a decisive applicable acceptance/regression failure '
                    'is established', not complete, '')
        if not complete:
            return ('NEED_EVIDENCE', 'evidence is linked and fresh but the declared '
                    'acceptance/regression set was not fully executed and no decisive '
                    'failure was established', True, 'full declared-set coverage')
        if self.policy == 'strict':
            # strict never adjudicates hidden acceptance: abstain unless a
            # diagnostic contradiction already forced REJECT above.
            return ('NEED_EVIDENCE', 'strict policy withholds maintainer acceptance '
                    'outcomes; symptom evidence alone cannot establish success',
                    False, 'maintainer acceptance outcomes')
        if consistent:
            return ('ACCEPT', 'integrity intact and executed checks show no failure',
                    False, '')
        return ('NEED_EVIDENCE', 'no decisive result yet', False,
                'acceptance adjudication')

    def _plan_override(self, fl):
        """Wave-2 v2 deliberate exercise points. Returns a
        (decision, gap, reason) override tuple, or None."""
        if not self.v2:
            return None
        return self.V2_ACTIVE_PLAN.get((self.item.get('scenario'), self.cond))

    def _heuristic_final(self, fl):
        d, why, mm, miss = self._decide(fl)
        if self.v2 and d == 'NEED_EVIDENCE':
            return self._final(d, why, mm, miss, gap=self._heuristic_gap(fl))
        return self._final(d, why, mm, miss)

    def create(self, **kw):
        messages = kw.get('messages') or []
        if not self.active:
            # Static heuristic from whatever the static block discloses.
            # Heuristic only; mock rows are not research data.
            pairs = []  # static cells never have tools
            return self._static_final(messages)
        pairs = self._pairs(messages)
        done = {n for n, _, _ in pairs}
        names_in_order = [n for n, _, _ in pairs]
        fl = self._flags(pairs)

        def did(n):
            return n in done

        if not did('get_test_artifact'):
            return self._call('get_test_artifact')
        if not did('verify_artifact_linkage'):
            return self._call('verify_artifact_linkage')
        if not did('check_evidence_freshness'):
            return self._call('check_evidence_freshness')
        if not did('check_test_coverage'):
            return self._call('check_test_coverage')

        if self.policy == 'strict':
            if not did('get_run_log') or 'symptom' not in fl['log_status']:
                return self._call('get_run_log', {'name': 'symptom'})
            # Prove the hard wall: an acceptance log request must return 403.
            if 'f2p' not in fl['log_status']:
                return self._call('get_run_log', {'name': 'f2p'})
            if not did('check_claim_consistency'):
                return self._call('check_claim_consistency')
            ov = self._plan_override(fl)
            if ov is not None:
                return self._final(ov[0], ov[2], gap=ov[1])
            return self._heuristic_final(fl)

        if self.policy == 'escalate':
            # v2: read the ungated symptom probe first (diagnostic channel).
            if self.v2 and 'symptom' not in fl['log_status']:
                return self._call('get_run_log', {'name': 'symptom'})
            # 1) request an acceptance log WITHOUT a reason -> expect 400
            no_reason_attempt = any(n == 'get_run_log'
                                    and a.get('name') in _ACCEPTANCE_LOGS
                                    and not (a.get('reason') or '').strip()
                                    for n, a, _ in pairs)
            if not no_reason_attempt:
                return self._call('get_run_log', {'name': 'f2p'})
            # 2) same request WITH a reason -> 200 + banner
            granted_log = 'f2p' in fl['banner']
            if not granted_log:
                return self._call('get_run_log',
                                  {'name': 'f2p', 'reason': self.REASON})
            # 3) consistency without reason -> 400
            cons_no_reason = any(n == 'check_claim_consistency'
                                 and not (a.get('reason') or '').strip()
                                 for n, a, _ in pairs)
            if not cons_no_reason:
                return self._call('check_claim_consistency')
            # 4) consistency with reason -> adjudicated
            cons_escalated = any(c.get('escalated') for c in fl['consistency'])
            if not cons_escalated:
                return self._call('check_claim_consistency',
                                  {'reason': self.REASON})
            ov = self._plan_override(fl)
            if ov is not None:
                return self._final(ov[0], ov[2], gap=ov[1])
            return self._heuristic_final(fl)

        # acceptance tier (T3A-T): full log, no reason gate
        if self.v2 and 'symptom' not in fl['log_status']:
            return self._call('get_run_log', {'name': 'symptom'})
        if 'f2p' not in fl['log_status']:
            return self._call('get_run_log', {'name': 'f2p'})
        if not did('check_claim_consistency'):
            return self._call('check_claim_consistency')
        ov = self._plan_override(fl)
        if ov is not None:
            return self._final(ov[0], ov[2], gap=ov[1])
        return self._heuristic_final(fl)

    def _static_final(self, messages):
        # The mock is a pipeline exerciser, not a subject: read the served
        # record it was given directly. At tier A acceptance outcomes are present;
        # at tier D they were projected away.
        rec = self.item.get('artifact_record') or {}
        scenario = self.item.get('scenario')
        if self.tier == 'A':
            summ = rec.get('summary') or {}
            if self.v2:
                # v2 ternary static: distinguish a presented failure (REJECT),
                # a complete all-green presentation (ACCEPT), and an
                # incomplete green presentation (NEED, gap not checkable at T2A).
                if summ.get('f2p_failed_ids') or summ.get('p2p_regressed_ids'):
                    return self._final(
                        'REJECT',
                        'static acceptance artifact presents a failing check')
                if self._presented_block_all_green(rec):
                    return self._final(
                        'ACCEPT',
                        'static acceptance artifact presents a complete '
                        'all-green run')
                return self._final(
                    'NEED_EVIDENCE',
                    'the rendered acceptance record is green but does not '
                    'present a complete executed set; linkage/freshness are '
                    'not adjudicated at this tier',
                    True, 'a complete, applicable acceptance run',
                    gap='unspecified')
            if summ.get('f2p_failed_ids') or summ.get('p2p_regressed_ids'):
                return self._final('REJECT',
                                   'static acceptance artifact shows a failure')
            return self._final('ACCEPT',
                               'static acceptance artifact shows no failure')
        # tier-D static (T2D-T)
        if self.v2:
            plan = self.V2_STATIC_PLAN.get(scenario)
            if plan is not None:
                d, gap = plan
                if d == 'REJECT':
                    return self._final(
                        'REJECT',
                        'the rendered issue-reproduction probe shows the '
                        'symptom still reproduces after the patch')
                return self._final(
                    'NEED_EVIDENCE',
                    'the static diagnostic block hints the run may not be '
                    'fresh, but this condition offers no tool to adjudicate '
                    'freshness', True, 'an adjudicated freshness verdict',
                    gap=gap)
            return self._final(
                'NEED_EVIDENCE',
                'static diagnostic record withholds acceptance outcomes and '
                'offers no tools to adjudicate mergeability',
                False, 'maintainer acceptance outcomes', gap='unspecified')
        # diagnostic static: acceptance outcomes withheld
        return self._final('NEED_EVIDENCE',
                           'static diagnostic record withholds acceptance '
                           'outcomes and offers no tools',
                           False, 'maintainer acceptance outcomes')


# ---------------------------------------------------------------------------
# Cell construction
# ---------------------------------------------------------------------------

def build_ternary_cells(fixtures, raw_by_id, store, conditions):
    from evidence.views import display_for_tier
    cells = []
    for fx in fixtures:
        if fx['id'] not in raw_by_id:
            raise SystemExit(f"raw row missing for fixture id {fx['id']}")
        raw = raw_by_id[fx['id']]
        for cond in conditions:
            active, tier, policy = ternary_condition_tier_policy(cond)
            item = {
                'id': fx['id'], 'instance_id': fx['instance_id'],
                'repo': fx.get('repo', raw.get('repo')),
                'base_commit': fx['base_commit'],
                'patch_sha256': fx['patch_sha256'],
                'issue': raw['problem_statement'], 'patch': raw['model_patch'],
                'condition': cond, 'scenario': fx.get('scenario'),
                'label_class': fx.get('label_class'),
                'merge_acceptable': fx.get('merge_acceptable'),
                'expected': fx.get('expected'),
                'served_artifact_id': fx['served_artifact_id'],
                'claim': fx.get('claim'), 'with_claim': True,
                'symptom': fx.get('symptom'),
                'cell_key': f"{fx.get('scenario')}:{fx['id']}:{cond}",
            }
            got = store.get(fx['served_artifact_id'])
            if got is None:
                raise SystemExit(f"missing served artifact "
                                 f"{fx['served_artifact_id']}")
            item['artifact_record'] = display_for_tier(
                store, got[0], fx['instance_id'], fx['patch_sha256'], tier)
            item['evidence_tier'] = tier
            cells.append(item)
    return cells


# ---------------------------------------------------------------------------
# Agent loop (shared by live LLM and scripted mock)
# ---------------------------------------------------------------------------

def _tally(tot, msg):
    if getattr(msg, 'usage', None):
        tot['in'] += getattr(msg.usage, 'prompt_tokens', 0) or 0
        tot['out'] += getattr(msg.usage, 'completion_tokens', 0) or 0


class BudgetGuard:
    """Pre-call budget enforcement.

    Before EVERY model call, require:
      remaining_usd >= conservative upper bound on that single call:
        input tokens now  * price_in
        + completion_cap  * price_out
    plus a per-cell call cap. If the bound does not fit, the call is never
    made -> BudgetGuardStop. Bounds err HIGH (max_tokens cap, fresh full
    resend of transcript each turn), so actual spend stays below the cap.
    """

    def __init__(self, max_budget_usd, price_in, price_out, *,
                 completion_cap_tokens=8192, max_model_calls_per_cell=12):
        self.cap = float(max_budget_usd)
        self.pin = price_in
        self.pout = price_out
        self.completion_cap = completion_cap_tokens
        self.max_calls = max_model_calls_per_cell
        self.spent = 0.0
        self.calls_total = 0

    def bound_usd(self, prompt_tokens_now):
        return (prompt_tokens_now * self.pin
                + self.completion_cap * self.pout) / 1e6

    def check(self, prompt_tokens_now, cell_calls):
        if cell_calls >= self.max_calls:
            raise BudgetGuardStop(
                f'per-cell model-call cap {self.max_calls} reached')
        bound = self.bound_usd(prompt_tokens_now)
        if self.spent + bound > self.cap + 1e-12:
            raise BudgetGuardStop(
                f'pre-call bound ${bound:.5f} would breach cap: spent '
                f'${self.spent:.5f} + ${bound:.5f} > ${self.cap:.5f}')
        return bound

    def add(self, cost):
        self.spent += float(cost or 0.0)
        self.calls_total += 1


def run_ternary_cell(driver, model, item, ev, profile, *, mock=False,
                     max_tool_turns=8, token_budget=0, emergency_tokens=120_000,
                     trace_dir=None, budget_guard=None, completion_cap=8192,
                     version_meta=None,
                     prompt_version=TERNARY_PROMPT_VERSION):
    cond = item['condition']
    active, tier, policy = ternary_condition_tier_policy(cond)
    if prompt_version == TERNARY_PROMPT_VERSION_V2:
        messages = build_ternary_messages_v2(
            item, artifact=item.get('artifact_record'))
    else:
        messages = build_ternary_messages(
            item, artifact=item.get('artifact_record'))
    tools = ternary_tools(cond)
    usage, t0 = {'in': 0, 'out': 0}, time.time()
    last_usage = {'in': 0, 'out': 0}
    trace = []
    sid = None
    model_served = None
    cell_calls = 0
    if active:
        s = ev.open_session(item['instance_id'], item['base_commit'],
                            item['patch_sha256'], cell=item['cell_key'],
                            served_artifact_id=item.get('served_artifact_id'),
                            evidence_tier=tier, policy=policy,
                            claim=item.get('claim'), symptom=item.get('symptom'))
        sid = s['session_id']

    def _est_prompt_tokens():
        # Conservative chars/3 upper estimate over the full transcript that
        # will be (re)sent; only used for the pre-call budget bound.
        n = 0
        for m in messages:
            c = m.get('content')
            if isinstance(c, str):
                n += len(c)
            if m.get('tool_calls'):
                for tc in m['tool_calls']:
                    n += len(json.dumps(tc, ensure_ascii=False))
        return max(n // 3, 256)

    def chat(tools_=None):
        nonlocal model_served, cell_calls
        if not mock and budget_guard is not None:
            budget_guard.check(_est_prompt_tokens(), cell_calls)
        kw = {}
        if not mock:
            kw['extra_body'] = {'thinking': {'type': 'disabled'}}
            # hard per-call completion cap so the bound above is a true bound
            kw['max_tokens'] = completion_cap
        if tools_:
            kw['tools'] = tools_
        else:
            kw['response_format'] = {'type': 'json_schema',
                                     'json_schema': TERNARY_DECISION_SCHEMA}
        try:
            resp = driver.chat.completions.create(model=model, messages=messages,
                                                  temperature=0, **kw)
        except Exception as e:
            if 'response_format' in kw and re.search(r'response_format|400', str(e)):
                kw.pop('response_format')
                if not mock and budget_guard is not None:
                    budget_guard.check(_est_prompt_tokens(), cell_calls)
                resp = driver.chat.completions.create(model=model,
                                                       messages=messages,
                                                       temperature=0, **kw)
            else:
                raise
        cell_calls += 1
        served = getattr(resp, 'model', None)
        if served:
            model_served = served
        return resp

    def over_cap():
        return emergency_tokens and usage['in'] + usage['out'] >= emergency_tokens

    def settle():
        # book the MARGINAL spend of the last model call against the guard
        # (usage counters are cumulative; tally only what is new)
        if not mock and budget_guard is not None:
            din = usage['in'] - last_usage['in']
            dout = usage['out'] - last_usage['out']
            last_usage['in'], last_usage['out'] = usage['in'], usage['out']
            budget_guard.add(
                (din * profile.get('price_in_per_1m', 0)
                 + dout * profile.get('price_out_per_1m', 0)) / 1e6)

    msg = None
    final = ''
    guard_reason = ''
    guard_stop = False
    try:
        msg = chat(tools)
    except BudgetGuardStop as bs:
        guard_stop = True
        guard_reason = str(bs)
    if msg is not None:
        _tally(usage, msg)
        settle()
        final = msg.choices[0].message.content or ''
    turns, budget_hit, emergency_hit = 0, False, False

    while (not guard_stop) and active \
            and msg.choices[0].finish_reason == 'tool_calls' \
            and turns < max_tool_turns:
        if token_budget and usage['in'] + usage['out'] >= token_budget:
            budget_hit = True
            break
        if over_cap():
            emergency_hit = True
            break
        tcb = msg.choices[0].message
        messages.append(tcb.model_dump(exclude_none=True))
        for tc in (tcb.tool_calls or []):
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or '{}')
            except Exception:
                args = {}
            try:
                result = ev.tool(sid, name, args, policy=policy)
            except Exception as te:
                result = {'error': f'tool {name} failed: {te}',
                          'http_status': 599}
            preview = result if isinstance(result, str) else json.dumps(result)
            if isinstance(result, dict):
                http_status = result.get('http_status', 200)
            else:
                mstat = re.search(r'http_status=(\d+)', preview or '')
                http_status = int(mstat.group(1)) if mstat else 200
            # v1 keeps the frozen 1200-char trace preview; v2 widens it to
            # match the content the model actually receives (8000) so the
            # mechanical symptom-polarity parse never misses a POST exit line
            # (three wave-2 logs put the marker at offset ~1200).
            trace_preview_cap = (8000 if prompt_version
                                 == TERNARY_PROMPT_VERSION_V2 else 1200)
            trace.append({'turn': turns, 'tool': name, 'args': args,
                          'http_status': http_status,
                          'result_preview': preview[:trace_preview_cap]})
            messages.append({'role': 'tool', 'tool_call_id': tc.id,
                             'content': preview[:8000]})
        turns += 1
        if over_cap():
            emergency_hit = True
            break
        try:
            msg = chat(tools)
        except BudgetGuardStop as bs:
            guard_stop = True
            guard_reason = str(bs)
            break
        _tally(usage, msg)
        settle()
        final = msg.choices[0].message.content or ''

    if not guard_stop and active and (msg.choices[0].finish_reason == 'tool_calls'
                   or not (final or '').strip()):
        messages.append({'role': 'user', 'content': 'Stop calling tools now and '
                         'return your final single JSON decision.'})
        try:
            msg = chat(None)
        except BudgetGuardStop as bs:
            guard_stop = True
            guard_reason = str(bs)
        else:
            _tally(usage, msg)
            settle()
            final = msg.choices[0].message.content or ''

    parsed = None if guard_stop else parse_ternary_decision(final or '')

    # Escalation bookkeeping (only meaningful at tier D).
    esc_req, esc_granted, esc_denied, reasons = [], [], [], []
    for t in trace:
        if t['tool'] == 'get_run_log' and (t.get('args') or {}).get('name') \
                in _ACCEPTANCE_LOGS:
            st = t['http_status']
            reason = (t.get('args') or {}).get('reason')
            if reason:
                esc_req.append('log')
                reasons.append(reason)
                (esc_granted if st == 200 else esc_denied).append('log')
            elif tier == 'D' and st in (400, 403):
                esc_denied.append('log:missing_reason' if st == 400
                                  else 'log:strict_denied')
        if t['tool'] == 'check_claim_consistency':
            st = t['http_status']
            reason = (t.get('args') or {}).get('reason')
            if reason:
                esc_req.append('consistency')
                reasons.append(reason)
                (esc_granted if st == 200 else esc_denied).append('consistency')
            elif tier == 'D' and st == 400:
                esc_denied.append('consistency:missing_reason')

    def saw(tool, key, val):
        return any(t['tool'] == tool
                   and f'"{key}": {val}' in (t.get('result_preview') or '')
                   for t in trace)

    cost = 0.0 if mock else (
        usage['in'] * profile.get('price_in_per_1m', 0)
        + usage['out'] * profile.get('price_out_per_1m', 0)) / 1e6
    if guard_stop:
        # Pre-call budget/call-cap stop: the guarded call was never made.
        # Recorded as an operational error row (excluded from research
        # metrics, like other error cells) with all partial evidence kept.
        parsed = None

    rec = {
        'protocol': 'ternary', 'mock': bool(mock),
        'cell': item['cell_key'], 'id': item['id'],
        'instance_id': item['instance_id'], 'condition': cond,
        'evidence_tier': tier, 'policy': policy, 'scenario': item.get('scenario'),
        'model': model, 'model_profile': profile.get('name'),
        'model_served': model_served or (model if mock else None),
        'label_class': item.get('label_class'),          # audit column only
        'merge_acceptable': item.get('merge_acceptable'),  # audit column only
        'expected_integrity': item.get('expected'),
        'served_artifact_id': item.get('served_artifact_id'),
        'answer': final, 'parsed': parsed,
        'evidence_session': sid, 'tool_trace': trace,
        'tool_calls': len(trace),
        'called_artifact': any(t['tool'] == 'get_test_artifact' for t in trace),
        'called_linkage': any(t['tool'] == 'verify_artifact_linkage'
                              for t in trace),
        'saw_linked_false': saw('verify_artifact_linkage', 'linked', 'false'),
        'called_freshness': any(t['tool'] == 'check_evidence_freshness'
                                for t in trace),
        'saw_fresh_false': saw('check_evidence_freshness', 'fresh', 'false'),
        'called_coverage': any(t['tool'] == 'check_test_coverage' for t in trace),
        'saw_coverage_incomplete': saw('check_test_coverage', 'complete',
                                       'false'),
        'called_consistency': any(t['tool'] == 'check_claim_consistency'
                                  for t in trace),
        'saw_contradicted': any('"verdict": "contradicted"'
                                in (t.get('result_preview') or '')
                                for t in trace if t['tool']
                                == 'check_claim_consistency'),
        'strict_denied_403': any(t['http_status'] == 403 for t in trace),
        'escalation_requested': esc_req,
        'escalation_granted': esc_granted,
        'escalation_denied': esc_denied,
        'escalation_reasons': reasons,
        'max_tool_turns': max_tool_turns,
        'token_budget': token_budget or None, 'budget_hit': budget_hit,
        'emergency_tokens': emergency_tokens or None,
        'emergency_hit': emergency_hit,
        'model_calls': cell_calls,
        'pre_call_budget_stop': guard_stop,
        'pre_call_budget_reason': guard_reason or None,
        'tokens_in': usage['in'], 'tokens_out': usage['out'],
        'cost_usd': round(cost, 6), 'wall_s': round(time.time() - t0, 2),
    }
    if guard_stop:
        rec['error'] = f'BudgetGuardStop: {guard_reason}'
    if version_meta:
        rec['version'] = dict(version_meta)
        if prompt_version == TERNARY_PROMPT_VERSION_V2:
            rec['version']['prompt_fingerprint'] = \
                ternary_prompt_fingerprint_v2(cond)
        else:
            rec['version']['prompt_fingerprint'] = \
                ternary_prompt_fingerprint(cond)

    # Wave-2 v2 only: structured evidence_gap, mechanically derived tool
    # verdicts, and the grounded gap classification. v1 rows gain NO new
    # keys (TR-9.2 byte-level regression against the 45 frozen smoke rows).
    if prompt_version == TERNARY_PROMPT_VERSION_V2 and not guard_stop:
        answer_obj = _parse_answer_json(final)
        gap = answer_obj.get('evidence_gap')
        if isinstance(gap, str) and gap.strip():
            rec['evidence_gap'] = gap.strip().lower()
        tool_verdicts = tool_verdicts_from_trace(rec)
        rec['tool_verdicts'] = tool_verdicts
        surface = item.get('_presented_facts')
        if parsed == 'NEED_EVIDENCE' and surface is not None:
            rec['gap_classification'] = classify_abstention(
                cond, rec.get('evidence_gap'), surface, tool_verdicts)
    if trace_dir is not None:
        tdp = Path(trace_dir)
        tdp.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^A-Za-z0-9._-]+', '_', item['cell_key']).strip('_')
        (tdp / f'{safe}.json').write_text(
            json.dumps({'cell': item['cell_key'], 'condition': cond,
                        'policy': policy, 'session_id': sid,
                        'trace': trace, 'final_answer': final,
                        'parsed': parsed,
                        'pre_call_budget_stop': guard_stop,
                        'pre_call_budget_reason': guard_reason or None},
                       ensure_ascii=False, indent=2),
            encoding='utf-8')
    return rec


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def load_profiles(path):
    prof = dict(DEFAULT_PROFILES)
    if path and Path(path).exists():
        prof.update(json.loads(Path(path).read_text(encoding='utf-8')))
    return prof


def _spawn_server(store):
    from evidence.server import build_server
    httpd = build_server(store, port=0)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f'http://127.0.0.1:{port}'


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fixture_manifest_identity(fixture_paths):
    """Per-file sha256 over raw bytes plus a combined hash.

    Combining the per-file hashes (not the file contents) keeps the identity
    stable regardless of path-list ordering quirks; the per-file values let a
    reader pinpoint which fixture list changed.
    """
    per = {}
    h = hashlib.sha256()
    for fp in fixture_paths:
        fp = fp.strip()
        if not fp:
            continue
        digest = _sha256_file(fp)
        per[fp] = digest
        h.update(fp.encode('utf-8'))
        h.update(b':')
        h.update(digest.encode('ascii'))
        h.update(b'\n')
    return {'files': per, 'combined_sha256': h.hexdigest()}


def summarize_run_audit(audit_path, session_cells):
    """Slice the server audit log to THIS run's sessions and aggregate the
    Strict/Escalate events the reviewer asked to preserve:
      denied_strict, escalation_reason_missing, escalation granted
      (consistency_escalation:contradicted / acceptance_log_reveal),
      and per-session evidence reads.
    `session_cells`: {session_id: {'cell':..., 'condition':...}}.
    """
    sids = set(session_cells)
    counts = {'events': 0, 'denied_strict': 0,
              'escalation_reason_missing': 0,
              'consistency_escalation_granted': 0,
              'acceptance_log_reveal': 0}
    by_condition = {}
    per_session = {}
    if not Path(audit_path).exists():
        return {'audit_path': audit_path, 'sessions': len(sids),
                'counts': counts, 'by_condition': {}, 'per_session': {},
                'note': 'audit log not found'}
    for e in read_jsonl(audit_path):
        sid = e.get('session')
        if sid not in sids:
            continue
        meta = session_cells.get(sid, {})
        cond = meta.get('condition', '?')
        action, result = e.get('action'), e.get('result', '')
        counts['events'] += 1
        ps = per_session.setdefault(sid, {'cell': meta.get('cell'),
                                          'condition': cond, 'events': 0,
                                          'denied_strict': 0,
                                          'escalation_reason_missing': 0,
                                          'escalation_granted': 0,
                                          'acceptance_log_reveal': 0,
                                          'reads': {}})
        ps['events'] += 1
        ps['reads'].setdefault(action, 0)
        ps['reads'][action] += 1
        bc = by_condition.setdefault(cond, {'events': 0, 'denied_strict': 0,
                                            'escalation_reason_missing': 0,
                                            'escalation_granted': 0,
                                            'acceptance_log_reveal': 0})
        bc['events'] += 1
        if result == 'denied_strict':
            counts['denied_strict'] += 1
            ps['denied_strict'] += 1
            bc['denied_strict'] += 1
        if result == 'escalation_reason_missing':
            counts['escalation_reason_missing'] += 1
            ps['escalation_reason_missing'] += 1
            bc['escalation_reason_missing'] += 1
        if isinstance(result, str) and result.startswith(
                'consistency_escalation:'):
            counts['consistency_escalation_granted'] += 1
            ps['escalation_granted'] += 1
            bc['escalation_granted'] += 1
        elif result == 'acceptance_log_reveal':
            counts['acceptance_log_reveal'] += 1
            ps['escalation_granted'] += 1
            ps['acceptance_log_reveal'] += 1
            bc['escalation_granted'] += 1
            bc['acceptance_log_reveal'] += 1
    return {'audit_path': str(audit_path), 'sessions': len(sids),
            'counts': counts, 'by_condition': by_condition,
            'per_session': per_session}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixtures', default='evidence_store/phase2_fixtures.jsonl')
    ap.add_argument('--raw', default='evidence_store/raw_rows.jsonl')
    ap.add_argument('--store', default='evidence_store')
    ap.add_argument('--output', default='evidence_store/phase3_ternary_results.jsonl')
    ap.add_argument('--conditions', default=','.join(TERNARY_CONDITIONS))
    ap.add_argument('--api', default='http://127.0.0.1:8321')
    ap.add_argument('--profiles', default='evidence_store/model_profiles.json')
    ap.add_argument('--model-profile', default='deepseek')
    ap.add_argument('--model', default='')
    ap.add_argument('--max-tool-turns', type=int, default=8)
    ap.add_argument('--token-budget', type=int, default=0)
    ap.add_argument('--emergency-tokens', type=int, default=120_000)
    ap.add_argument('--max-budget-usd', type=float, default=0.30)
    ap.add_argument('--completion-cap', type=int, default=8192,
                    help='hard max_tokens per model call; anchors the '
                         'pre-call conservative budget bound')
    ap.add_argument('--max-model-calls-per-cell', type=int, default=12)
    ap.add_argument('--gold', default='evidence_store/phase3_gold.jsonl')
    ap.add_argument('--audit-out',
                    default='evidence_store/phase3_run_audit_summary.json')
    ap.add_argument('--mock', action='store_true',
                    help='scripted deterministic model; zero API cost')
    ap.add_argument('--spawn-server', action='store_true',
                    help='start an in-process real evidence HTTP server '
                         '(mock: isolated store copy; live: real store)')
    ap.add_argument('--isolate-store', action='store_true', default=True,
                    help='mock spawn: serve a throwaway COPY of the store so the '
                         'real audit.jsonl and baselines are never touched')
    ap.add_argument('--no-isolate-store', dest='isolate_store',
                    action='store_false')
    ap.add_argument('--mock-trace-dir',
                    default='evidence_store/phase3_mock_traces')
    ap.add_argument('--prompt-version', default=TERNARY_PROMPT_VERSION,
                    choices=PROMPT_VERSIONS,
                    help='p3-ternary-v1 (frozen smoke protocol) or '
                         'p3-ternary-v2 (wave-2 structured evidence_gap)')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    # Mock rows are engineering checks (mock=true), never research data: keep
    # them in a dedicated file unless the operator explicitly overrides output.
    # v2 mock runs default to a SEPARATE wave2 namespace so the frozen v1
    # phase3_mock_results.jsonl can never be appended to or overwritten.
    v2 = a.prompt_version == TERNARY_PROMPT_VERSION_V2
    if a.mock:
        default_live_out = 'evidence_store/phase3_ternary_results.jsonl'
        default_mock_out = ('evidence_store/wave2_mock_results.jsonl' if v2
                            else 'evidence_store/phase3_mock_results.jsonl')
        if a.output == default_live_out:
            a.output = default_mock_out
        if a.mock_trace_dir == 'evidence_store/phase3_mock_traces' and v2:
            a.mock_trace_dir = 'evidence_store/wave2_mock_traces'

    from evidence.store import ArtifactStore
    store = ArtifactStore(a.store)
    fixtures = []
    for fp in a.fixtures.split(','):
        fp = fp.strip()
        if fp:
            fixtures.extend(read_jsonl(fp))
    raw_by_id = {r['id']: r for r in read_jsonl(a.raw)}
    conds = tuple(x.strip() for x in a.conditions.split(',') if x.strip())
    for c in conds:
        ternary_condition_tier_policy(c)  # validate
    cells = build_ternary_cells(fixtures, raw_by_id, store, conds)
    if v2:
        # Precompute each condition's projected evidence surface (pure,
        # fact-only; evidence.visibility) for runner-side gap grounding. This
        # is the SAME projection frozen in wave2_gold.visibility_matrix and
        # never reads model outputs or scenario labels.
        from evidence.visibility import load_fixture_facts, project_surface
        # Key facts by SERVED artifact: mirror fixtures share the same
        # model:instance id but serve distinct artifacts with different
        # linkage/freshness/coverage facts.
        fx_by_aid = {f['served_artifact_id']: f for f in fixtures}
        facts_cache = {}
        for item in cells:
            aid = item['served_artifact_id']
            if aid not in facts_cache:
                facts_cache[aid] = load_fixture_facts(store, fx_by_aid[aid])
            item['_presented_facts'] = project_surface(
                item['condition'], facts_cache[aid])
    print(f'cells={len(cells)} conditions={conds} mock={a.mock} '
          f'prompt_version={a.prompt_version}')
    if a.dry_run:
        for c in cells:
            print(' ', c['cell_key'])
        return

    # Version identity shared by every result row in this run.
    fixture_paths = [x.strip() for x in a.fixtures.split(',') if x.strip()]
    if v2:
        # Wave-2 gold is hashed over newline-normalised text (Windows lands
        # CRLF); this MUST equal metrics_w2.load_w2_gold's sha256.
        gold_hash = (_sha256_text_normalized(a.gold)
                     if Path(a.gold).exists() else None)
    else:
        gold_hash = (_sha256_file(a.gold) if Path(a.gold).exists() else None)
    version_meta = {
        'prompt_version': a.prompt_version,
        'gold_sha256': gold_hash,
        'fixture_manifest': fixture_manifest_identity(fixture_paths),
        'gold_path': a.gold,
    }

    httpd = None
    audit_path = str(Path(a.store) / 'audit.jsonl')
    if a.spawn_server:
        serve_root = a.store
        tmp_root = None
        if a.mock and a.isolate_store:
            import shutil, tempfile
            tmp_root = tempfile.mkdtemp(prefix='phase3_mock_store_')
            shutil.copytree(a.store, tmp_root, dirs_exist_ok=True)
            serve_root = tmp_root
        httpd, a.api = _spawn_server(serve_root)
        audit_path = httpd.audit_path
        print(f'spawned real evidence server at {a.api} root={serve_root}')

    if a.mock:
        model = 'scripted-mock'
        profile = {'name': 'mock'}
        ev = P3Client(a.api)
        outp = Path(a.output)
        spent, n_err = 0.0, 0
        with outp.open('a', encoding='utf-8') as f:
            for item in cells:
                driver = type('D', (), {})()
                driver.chat = type('C', (), {})()
                driver.chat.completions = ScriptedModel(
                    item['condition'], item,
                    prompt_version=a.prompt_version)
                try:
                    rec = run_ternary_cell(driver, model, item, ev, profile,
                                           mock=True,
                                           max_tool_turns=a.max_tool_turns,
                                           trace_dir=a.mock_trace_dir,
                                           version_meta=version_meta,
                                           prompt_version=a.prompt_version)
                except Exception as e:
                    n_err += 1
                    rec = {'cell': item['cell_key'], 'condition': item['condition'],
                           'mock': True, 'protocol': 'ternary',
                           'error': f'{type(e).__name__}: {e}'}
                    print('ERROR', rec['cell'], rec['error'][:200])
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                f.flush()
                if 'error' not in rec:
                    print(rec['cell'], rec['parsed'],
                          f"tools={rec['tool_calls']} "
                          f"403={rec['strict_denied_403']} "
                          f"granted={rec['escalation_granted']} "
                          f"denied={rec['escalation_denied']}")
        if httpd is not None:
            httpd.shutdown()
        print(f'mock done: failed_cells={n_err} spend=$0.0 traces={a.mock_trace_dir}')
        return

    profiles = load_profiles(a.profiles)
    if a.model_profile not in profiles:
        raise SystemExit(f'unknown profile {a.model_profile}; have {sorted(profiles)}')
    profile = dict(profiles[a.model_profile]); profile['name'] = a.model_profile
    model = a.model or a.model_profile
    from openai import OpenAI
    key = os.environ.get(profile['key_env']) or os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit(f"set {profile['key_env']} for this model profile")
    driver = OpenAI(api_key=key, base_url=profile.get('base_url'))
    ev = P3Client(a.api)
    outp = Path(a.output)
    prior = list(read_jsonl(a.output)) if outp.exists() else []
    done = {r['cell'] for r in prior if not r.get('error') and not r.get('mock')}
    spent = sum(float(r.get('cost_usd') or 0) for r in prior if not r.get('mock'))
    # Pre-call guard seeded with any prior spend (resume-safe).
    guard = BudgetGuard(a.max_budget_usd,
                        profile.get('price_in_per_1m', 0),
                        profile.get('price_out_per_1m', 0),
                        completion_cap_tokens=a.completion_cap,
                        max_model_calls_per_cell=a.max_model_calls_per_cell)
    guard.spent = spent
    n_err = 0
    n_budget_stop = 0
    batch_budget_stop = False
    session_cells = {}
    new_rows = []
    with outp.open('a', encoding='utf-8') as f:
        for item in cells:
            if item['cell_key'] in done:
                continue
            if guard.spent >= a.max_budget_usd:
                print(f'BATCH BUDGET STOP: ${guard.spent:.4f} >= '
                      f'${a.max_budget_usd:.4f}')
                batch_budget_stop = True
                break
            try:
                rec = run_ternary_cell(driver, model, item, ev, profile,
                                       max_tool_turns=a.max_tool_turns,
                                       token_budget=a.token_budget,
                                       emergency_tokens=a.emergency_tokens,
                                       budget_guard=guard,
                                       completion_cap=a.completion_cap,
                                       version_meta=version_meta,
                                       prompt_version=a.prompt_version)
            except Exception as e:
                n_err += 1
                rec = {'protocol': 'ternary', 'mock': False,
                       'cell': item['cell_key'],
                       'id': item['id'], 'condition': item['condition'],
                       'policy': ternary_condition_tier_policy(item['condition'])[2],
                       'scenario': item.get('scenario'), 'model': model,
                       'model_served': None,
                       'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                       'tool_calls': 0, 'tool_trace': [],
                       'version': dict(version_meta),
                       'error': f'{type(e).__name__}: {e}'}
                print('ERROR', rec['cell'], rec['error'][:200])
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            new_rows.append(rec)
            spent = guard.spent
            if rec.get('evidence_session'):
                session_cells[rec['evidence_session']] = {
                    'cell': rec.get('cell'), 'condition': rec.get('condition')}
            if rec.get('pre_call_budget_stop'):
                n_budget_stop += 1
                print('BUDGET-GUARD STOP', rec['cell'],
                      (rec.get('pre_call_budget_reason') or '')[:160])
            elif 'error' not in rec:
                print(rec['cell'], rec['parsed'],
                      f"tools={rec['tool_calls']} calls={rec.get('model_calls')} "
                      f"in={rec['tokens_in']} out={rec['tokens_out']} "
                      f"${rec['cost_usd']:.4f} cum=${spent:.4f} "
                      f"model={rec.get('model_served')}")

    # Run-level server audit aggregation (Strict/Escalate evidence behavior).
    run_audit = summarize_run_audit(audit_path, session_cells)
    summary = {
        'protocol': 'ternary', 'mock': False, 'model': model,
        'cells_planned': len(cells),
        'cells_already_done': len(done),
        'cells_attempted_this_process': len(new_rows),
        'error_cells': n_err, 'budget_stop_cells': n_budget_stop,
        'batch_budget_stop': batch_budget_stop,
        'budget_cap_usd': a.max_budget_usd,
        'cumulative_spend_usd': round(guard.spent, 6),
        'guard_calls_total': guard.calls_total,
        'completion_cap_tokens': a.completion_cap,
        'max_model_calls_per_cell': a.max_model_calls_per_cell,
        'version': version_meta,
        'server_audit': run_audit,
    }
    Path(a.audit_out).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    if httpd is not None:
        httpd.shutdown()
    print(f'done: failed_cells={n_err} budget_stop_cells={n_budget_stop} '
          f'cumulative_spend=${guard.spent:.4f} '
          f'audit_events={run_audit["counts"]["events"]} '
          f'summary={a.audit_out}')


if __name__ == '__main__':
    main()
