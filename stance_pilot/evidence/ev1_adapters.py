"""E1 model adapters (External Validation, offline preparation).

The Wave-2.1 runner (evidence.phase3_run) hard-codes DeepSeek wire
conventions in its live ``chat()`` closure:

    extra_body   = {'thinking': {'type': 'disabled'}}
    cap param    = max_tokens
    temperature  = 0
    final answer = response_format json_schema(strict), with a single
                   400-driven fallback that drops response_format entirely

Other vendors reject or ignore parts of that shape. E1 must keep the TASK
frozen (same prompts, tools, tool permissions, decision JSON, scoring) while
adapting only API-wire parameters. This module adds that adaptation layer
without touching phase3_run.py:

  * load_ev1_profile      - validated profile from ev1_model_profiles.json,
                            with the price/key/base_url keys phase3_run and
                            BudgetGuard already understand;
  * adapt_call_kwargs     - pure mapping from the runner's frozen kwargs to
                            one vendor's accepted kwargs (profile-driven);
  * RecordingCompletions  - wraps ANY inner chat.completions object (live
                            OpenAI SDK or the offline ScriptedModel), maps
                            kwargs per call, records a compact audit of each
                            call's shape, and adds the
                            strict-schema -> json_object -> plain-text 400
                            downgrade chain (the frozen runner itself only
                            has strict -> plain);
  * make_driver           - convenience constructors for the live SDK driver
                            and the offline recording driver.

Nothing here ever changes prompts, tool schemas, session semantics or gold.
No network is performed at import time; the live OpenAI import is deferred.

Offline self-check:
    uv run --python 3.13 -m evidence.ev1_adapters
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PROFILES = HERE / 'ev1_model_profiles.json'

PROFILE_REQUIRED = (
    'provider', 'model', 'base_url', 'key_env',
    'price_in_per_1m', 'price_out_per_1m',
    'temperature_supported', 'completion_param', 'response_format',
)
_VALID_COMPLETION_PARAM = ('max_tokens', 'max_completion_tokens')
_VALID_RF = ('json_schema_strict', 'json_object', 'plain_text')


# ---------------------------------------------------------------------------
# Profile loading / validation
# ---------------------------------------------------------------------------

def load_ev1_profiles(path=DEFAULT_PROFILES):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return {k: v for k, v in raw.items() if not k.startswith('_')}


def load_ev1_profile(name, path=DEFAULT_PROFILES):
    profiles = load_ev1_profiles(path)
    if name not in profiles:
        raise SystemExit(f'unknown E1 profile {name}; have {sorted(profiles)}')
    p = dict(profiles[name])
    missing = [k for k in PROFILE_REQUIRED if k not in p]
    if missing:
        raise SystemExit(f'E1 profile {name} missing keys: {missing}')
    if p['completion_param'] not in _VALID_COMPLETION_PARAM:
        raise SystemExit(
            f"profile {name}: completion_param must be one of "
            f"{_VALID_COMPLETION_PARAM}, got {p['completion_param']!r}")
    if p['response_format'] not in _VALID_RF:
        raise SystemExit(
            f"profile {name}: response_format must be one of {_VALID_RF}, "
            f"got {p['response_format']!r}")
    p['name'] = name
    return p


# ---------------------------------------------------------------------------
# Pure kwargs mapping (the only place vendor conventions live)
# ---------------------------------------------------------------------------

def _strict_schema_obj():
    # Imported lazily from the frozen protocol module; never modified here.
    from evidence.ternary import TERNARY_DECISION_SCHEMA
    return {'type': 'json_schema', 'json_schema': TERNARY_DECISION_SCHEMA}


def adapt_call_kwargs(profile, kwargs):
    """Map the frozen runner's call kwargs to this vendor's wire shape.

    Input kwargs (as built by phase3_run.run_ternary_cell.chat):
        {'extra_body': {'thinking': ...}, 'max_tokens': cap,
         'temperature' is passed positionally,
         'tools': [...]}                          # tool turns, OR
        {'response_format': {strict json_schema}} # final decision turn

    Returns a NEW dict; the input is never mutated.
    """
    out = dict(kwargs)

    # 1) DeepSeek-only thinking toggle: vendors reject unknown extra_body
    #    fields. Replace wholesale with the profile's vendor body.
    out.pop('extra_body', None)
    eb = profile.get('extra_body') or {}
    if eb:
        out['extra_body'] = dict(eb)

    # 2) hard completion cap parameter name
    cap = out.pop('max_tokens', None)
    if cap is not None:
        out[profile['completion_param']] = cap

    # 3) reasoning effort (reasoning models only); top-level passthrough
    re_effort = profile.get('reasoning_effort')
    if re_effort:
        out['reasoning_effort'] = re_effort

    # 4) response_format downgrade for the FINAL decision call
    if 'response_format' in out:
        mode = profile['response_format']
        if mode == 'json_schema_strict':
            out['response_format'] = _strict_schema_obj()
        elif mode == 'json_object':
            out['response_format'] = {'type': 'json_object'}
        else:  # plain_text
            out.pop('response_format', None)
    return out


def _rf_mode(kwargs):
    rf = kwargs.get('response_format')
    if not rf:
        return 'plain_text'
    if rf.get('type') == 'json_schema':
        return 'json_schema_strict'
    if rf.get('type') == 'json_object':
        return 'json_object'
    return 'plain_text'


def _downgrade_rf(kwargs):
    """One step: json_schema -> json_object -> (drop) plain_text."""
    mode = _rf_mode(kwargs)
    nxt = dict(kwargs)
    if mode == 'json_schema_strict':
        nxt['response_format'] = {'type': 'json_object'}
        return nxt, 'json_object'
    if mode == 'json_object':
        nxt.pop('response_format', None)
        return nxt, 'plain_text'
    return nxt, mode


# ---------------------------------------------------------------------------
# Recording wrapper
# ---------------------------------------------------------------------------

class RecordingCompletions:
    """Wrap an inner ``chat.completions`` object with profile adaptation.

    `calls` accumulates one compact, content-free record per ACTUAL wire call,
    so offline tests can assert exact request shapes without a network.
    """

    _RF_RE = re.compile(r'response_format|json_schema|400|invalid', re.I)

    def __init__(self, inner, profile):
        self.inner = inner
        self.profile = profile
        self.calls = []

    def _record(self, kwargs, mode_after, *, fallback_from=None):
        self.calls.append({
            'model': self.profile.get('model'),
            'n_messages': len(kwargs.get('messages') or []),
            'has_tools': 'tools' in kwargs,
            'completion_param': next(
                (k for k in ('max_tokens', 'max_completion_tokens')
                 if k in kwargs), None),
            'completion_cap': kwargs.get('max_tokens')
                if 'max_tokens' in kwargs
                else kwargs.get('max_completion_tokens'),
            'temperature_present': 'temperature' in kwargs,
            'extra_body_keys': sorted((kwargs.get('extra_body') or {}).keys()),
            'reasoning_effort': kwargs.get('reasoning_effort'),
            'response_format': mode_after,
            'fallback_from': fallback_from,
        })

    def create(self, *, model, messages, temperature=None, **kwargs):
        kwargs['messages'] = messages
        if temperature is not None:
            kwargs['temperature'] = temperature
        if not self.profile.get('temperature_supported', True):
            kwargs.pop('temperature', None)

        adapted = adapt_call_kwargs(self.profile, kwargs)
        try:
            resp = self.inner.create(model=model, **adapted)
        except Exception as e:
            # Adapter-level strict -> json_object -> plain chain. The frozen
            # runner also has its own strict -> plain fallback; performing the
            # downgrade here keeps the intermediate json_object step usable for
            # vendors whose compatibility layer rejects strict schemas.
            mode = _rf_mode(adapted)
            if mode in ('json_schema_strict', 'json_object') \
                    and self._RF_RE.search(str(e)):
                adapted2, mode2 = _downgrade_rf(adapted)
                self._record(dict(adapted), mode, fallback_from=None)
                try:
                    resp = self.inner.create(model=model, **adapted2)
                    self._record(dict(adapted2), mode2, fallback_from=mode)
                    return resp
                except Exception as e2:
                    mode3 = _rf_mode(adapted2)
                    if mode3 == 'json_object' and self._RF_RE.search(str(e2)):
                        adapted3, mode3b = _downgrade_rf(adapted2)
                        resp = self.inner.create(model=model, **adapted3)
                        self._record(dict(adapted3), mode3b,
                                     fallback_from=mode3)
                        return resp
                    raise
            raise
        self._record(dict(adapted), _rf_mode(adapted))
        return resp


class _Chat:
    def __init__(self, completions):
        self.completions = completions


def make_driver(inner_completions, profile):
    """Duck-typed driver: driver.chat.completions.create(...)"""
    d = type('E1Driver', (), {})()
    d.chat = _Chat(RecordingCompletions(inner_completions, profile))
    return d


def make_live_driver(profile):
    """Real network driver (only used after explicit paid-run approval)."""
    from openai import OpenAI
    key_note = ' (or OPENAI_API_KEY fallback)' if profile['provider'] \
        == 'openai' else ''
    import os
    key = os.environ.get(profile['key_env'])
    if profile['provider'] == 'openai':
        key = key or os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit(
            f"set {profile['key_env']}{key_note} for profile {profile['name']}")
    inner = OpenAI(api_key=key, base_url=profile['base_url'])
    return make_driver(inner.chat.completions, profile)


def make_offline_recording_driver(profile, cond='T3D-Strict', item=None):
    """Wrap the frozen ScriptedModel so the FULL live runner path (mock=False
    from run_ternary_cell's perspective this driver still returns scripted
    responses) executes with zero network while the adapter records every
    wire shape. Note: callers still pass mock=True to run_ternary_cell in the
    pipeline test; this wrapper is for direct kwargs-interception tests."""
    from evidence.phase3_run import ScriptedModel
    scripted = ScriptedModel(cond, item or {})
    return make_driver(scripted, profile)


# ---------------------------------------------------------------------------
# Offline self-check (zero network, zero paid calls)
# ---------------------------------------------------------------------------

class _Fake400:
    """Inner completions that rejects strict schema once, then accepts."""

    def __init__(self, reject_modes=('json_schema_strict',)):
        self.reject_modes = set(reject_modes)
        self.seen = []

    def create(self, *, model, **kwargs):
        mode = _rf_mode(kwargs)
        self.seen.append(mode)
        if mode in self.reject_modes:
            raise Exception('400 response_format json_schema not supported')
        from evidence.phase3_run import _Resp
        return _Resp(content=json.dumps(
            {'decision': 'NEED_EVIDENCE', 'reason': 'x',
             'evidence_mismatch': False}))


def _strict_kw():
    return {'response_format': _strict_schema_obj(), 'max_tokens': 8192}


def _tools_kw():
    return {'tools': [{'type': 'function'}], 'max_tokens': 8192}


def selfcheck():
    profiles_path = DEFAULT_PROFILES
    profiles = {n: load_ev1_profile(n, profiles_path)
                for n in load_ev1_profiles(profiles_path)}
    checks = []

    def check(name, cond):
        checks.append((name, bool(cond)))

    # --- gpt-4.1-mini: closest frozen-shape match ------------------------
    p = profiles['openai_gpt41_mini']
    d = make_offline_recording_driver(p)
    d.chat.completions.create(model=p['model'], messages=[{'role': 'user'}],
                              temperature=0, **_strict_kw())
    r = d.chat.completions.calls[-1]
    check('gpt41mini final-decision mapped to profile json_object',
          r['response_format'] == p['response_format'] == 'json_object')
    check('gpt41mini max_tokens retained', r['completion_param'] == 'max_tokens')
    check('gpt41mini temperature retained', r['temperature_present'] is True)
    check('gpt41mini deepseek thinking body removed',
          r['extra_body_keys'] == [])
    d.chat.completions.create(model=p['model'], messages=[{'role': 'user'}],
                              temperature=0, **_tools_kw())
    r = d.chat.completions.calls[-1]
    check('gpt41mini tools pass through', r['has_tools'] is True)
    check('gpt41mini no response_format on tool turns',
          r['response_format'] == 'plain_text')

    # --- gemini-3-flash: pre-downgrade to json_object --------------------
    p = profiles['google_gemini3_flash']
    d = make_offline_recording_driver(p)
    d.chat.completions.create(model=p['model'], messages=[{'role': 'user'}],
                              temperature=0, **_strict_kw())
    r = d.chat.completions.calls[-1]
    check('gemini pre-downgraded json_object',
          r['response_format'] == 'json_object')
    check('gemini max_tokens retained', r['completion_param'] == 'max_tokens')
    check('gemini temperature retained', r['temperature_present'] is True)
    check('gemini thinking body not forwarded', r['extra_body_keys'] == [])

    # --- gpt-5.1-codex-mini: reasoning-model wire shape ------------------
    p = profiles['openai_gpt51_codex_mini']
    d = make_offline_recording_driver(p)
    d.chat.completions.create(model=p['model'], messages=[{'role': 'user'}],
                              temperature=0, **_strict_kw())
    r = d.chat.completions.calls[-1]
    check('codexmini max_completion_tokens',
          r['completion_param'] == 'max_completion_tokens')
    check('codexmini temperature dropped', r['temperature_present'] is False)
    check('codexmini reasoning_effort=minimal',
          r['reasoning_effort'] == 'minimal')
    check('codexmini strict schema retained',
          r['response_format'] == 'json_schema_strict')
    check('codexmini cap value preserved', r['completion_cap'] == 8192)

    # --- 400 downgrade chain: strict -> json_object -> plain -------------
    # Pin a strict-starting test profile so this chain is covered regardless
    # of the production profile's configured response_format (the live
    # fallback chain is a runtime capability, not a profile choice).
    base = dict(profiles['openai_gpt41_mini'])
    base['response_format'] = 'json_schema_strict'
    fake = _Fake400(reject_modes=('json_schema_strict', 'json_object'))
    drv = make_driver(fake, base)
    drv.chat.completions.create(model='x', messages=[{'role': 'user'}],
                                temperature=0, **_strict_kw())
    check('400 chain tried all three modes',
          fake.seen == ['json_schema_strict', 'json_object', 'plain_text'])
    rec = drv.chat.completions.calls
    check('400 chain recorded successful plain-text fallback',
          rec[-1]['response_format'] == 'plain_text'
          and rec[-1]['fallback_from'] == 'json_object')

    # single-step strict -> json_object success
    fake2 = _Fake400(reject_modes=('json_schema_strict',))
    drv2 = make_driver(fake2, base)
    drv2.chat.completions.create(model='x', messages=[{'role': 'user'}],
                                 temperature=0, **_strict_kw())
    check('400 one-step to json_object succeeds',
          fake2.seen == ['json_schema_strict', 'json_object']
          and drv2.chat.completions.calls[-1]['fallback_from']
          == 'json_schema_strict')

    failed = [n for n, ok in checks if not ok]
    width = max(len(n) for n, _ in checks)
    for n, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {n.ljust(width)}")
    print(f'\n{len(checks) - len(failed)}/{len(checks)} adapter checks '
          f'passed; profiles={sorted(profiles)}')
    if failed:
        raise SystemExit(f'adapter selfcheck FAILED: {failed}')
    print('offline only: no network and no paid API call were performed')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--selfcheck', action='store_true',
                    help='zero-network kwargs interception tests (default '
                         'action when run with no arguments)')
    a = ap.parse_args()
    selfcheck()


if __name__ == '__main__':
    main()
