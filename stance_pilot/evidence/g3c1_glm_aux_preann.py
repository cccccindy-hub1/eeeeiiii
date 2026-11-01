"""GroundedReview - GLM AUXILIARY pre-annotation run (NOT a research result).

This module is deliberately isolated from the frozen G3-C.1 research pipeline:
  * it imports none of the frozen evidence.* analysis modules;
  * it writes only to evidence_store_glm_aux/;
  * its outputs are decision-support pre-labels for the HUMAN annotator, never
    annotator2 labels, and they never upgrade PROVISIONAL gold;
  * GLM is an AI, not an independent human. These rows MUST NOT be pooled with
    the GPT-4.1-mini / DeepSeek-Flash 80-cell research results.

Modes:
  --ping           one tiny authenticated call to verify model id / auth
  --run            blind pre-annotation of packets P01..P08 (resumable)
  --fr             post-unblind focused review answers for FR1 (19495=P02)
                   and FR2 (14248=P01 + 15875=P08), using GLM's own saved labels

Cost ledger: token counts are hard data taken from each response. RMB cost is
an UPPER-BOUND ESTIMATE at the conservative domestic list price
(glm-4.6: RMB 2.0 / 1M input tokens, RMB 8.0 / 1M output tokens); the vendor
console bill is authoritative.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from decimal import Decimal, getcontext

getcontext().prec = 28

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
HERE = Path(__file__).resolve().parent
_SP = HERE.parent

# Per-cohort configuration. Outputs are isolated so the completed G3-C.1 aux
# artifacts are never touched by a G3-A run.
COHORTS = {
    "G3C1": {
        "label": "G3-C.1",
        "n_packets": 8,
        "packet_root": _SP / "evidence_store_g3c1" / "human_annotation" / "packets",
        "human_dir": _SP / "evidence_store_g3c1" / "human_annotation",
        "gold_jsonl": _SP / "evidence_store_g3c1" / "gold" / "g3c1_oracle_gold.jsonl",
        "out_root": _SP / "evidence_store_glm_aux",
        "has_focused_review": True,
    },
    "G3A": {
        "label": "G3-A",
        "n_packets": 10,
        "packet_root": _SP / "evidence_store_g3c0" / "human_annotation" / "packets",
        "human_dir": _SP / "evidence_store_g3c0" / "human_annotation",
        "gold_jsonl": _SP / "evidence_store_g3a" / "gold" / "g3a_gold.jsonl",
        "out_root": _SP / "evidence_store_glm_aux_g3a",
        "has_focused_review": False,
    },
}

COHORT_KEY = "G3C1"
_CFG = COHORTS[COHORT_KEY]
COHORT_LABEL = _CFG["label"]
PACKET_ROOT = _CFG["packet_root"]
OUT_ROOT = _CFG["out_root"]
RAW_DIR = OUT_ROOT / "raw"
RECORD_DIR = OUT_ROOT / "records"
LABELS_JSON = OUT_ROOT / "glm_prelabels.jsonl"
LABELS_CSV = OUT_ROOT / "glm_prelabels_for_human_correction.csv"
LEDGER_JSON = OUT_ROOT / "glm_cost_ledger.json"
FR_JSON = OUT_ROOT / "glm_focused_review_fr1_fr2.json"
REPORT_MD = OUT_ROOT / "glm_aux_evaluation_report.md"
# Frozen inputs used ONLY for post-run unblinding/report; never modified.
HUMAN_DIR = _CFG["human_dir"]
SEALED_MAP_JSON = HUMAN_DIR / "SEALED_packet_mapping.json"
ORACLE_GOLD_JSONL = _CFG["gold_jsonl"]


def configure(cohort_key: str) -> None:
    """Rebind path globals for the selected cohort (isolated output trees)."""
    global COHORT_KEY, _CFG, COHORT_LABEL, PACKET_ROOT, OUT_ROOT, RAW_DIR
    global RECORD_DIR, LABELS_JSON, LABELS_CSV, LEDGER_JSON, FR_JSON, REPORT_MD
    global HUMAN_DIR, SEALED_MAP_JSON, ORACLE_GOLD_JSONL, PACKET_IDS
    if cohort_key not in COHORTS:
        raise SystemExit(f"unknown cohort {cohort_key}; choose from {sorted(COHORTS)}")
    COHORT_KEY = cohort_key
    _CFG = COHORTS[cohort_key]
    COHORT_LABEL = _CFG["label"]
    PACKET_ROOT = _CFG["packet_root"]
    OUT_ROOT = _CFG["out_root"]
    RAW_DIR = OUT_ROOT / "raw"
    RECORD_DIR = OUT_ROOT / "records"
    LABELS_JSON = OUT_ROOT / "glm_prelabels.jsonl"
    LABELS_CSV = OUT_ROOT / "glm_prelabels_for_human_correction.csv"
    LEDGER_JSON = OUT_ROOT / "glm_cost_ledger.json"
    FR_JSON = OUT_ROOT / "glm_focused_review_fr1_fr2.json"
    REPORT_MD = OUT_ROOT / "glm_aux_evaluation_report.md"
    HUMAN_DIR = _CFG["human_dir"]
    SEALED_MAP_JSON = HUMAN_DIR / "SEALED_packet_mapping.json"
    ORACLE_GOLD_JSONL = _CFG["gold_jsonl"]
    PACKET_IDS = [f"P{i:02d}" for i in range(1, _CFG["n_packets"] + 1)]


MODEL = "glm-4.6"
BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
# Conservative upper-bound RMB list price per 1,000,000 tokens.
PRICE_RMB_IN_PER_1M = Decimal("2.0")
PRICE_RMB_OUT_PER_1M = Decimal("8.0")
# Hard pre-call guard; the whole run is expected to cost well under RMB 1.
BUDGUARD_RMB = Decimal("20.0")
# Rough chars-per-token used only for the conservative pre-call estimate.
CHARS_PER_TOKEN = 3.0
MAX_OUTPUT_TOKENS = 8192
PACKET_FILES = [
    "01_problem_statement.txt",
    "02_candidate_patch.diff",
    "03_maintainer_test_patch.diff",
    "04_declared_test_ids.json",
    "05_ci_fail_to_pass.log",
    "06_ci_pass_to_pass_scoped.log",
    "07_ci_pass_to_pass_base_commit.log",
    "08_issue_symptom_probe.log",
]
PACKET_IDS = [f"P{i:02d}" for i in range(1, 9)]

SYSTEM_PROMPT = """You are an independent, BLIND adjudicator reviewing a software patch from the frozen CI evidence in ONE packet. Judge ONLY from the supplied text. Do not use the web, an issue tracker, or any outside knowledge. Folder ids are blinded; if a patch or problem statement quotes an upstream issue number, ignore it.

Apply this decision rubric EXACTLY:
1. ACCEPT: every declared FAIL_TO_PASS test transitions fail(at base) -> pass(after patch), AND no declared in-scope PASS_TO_PASS test regresses (a test that passed/xfailed/skipped at base but is bad after the patch). Only the attested SCOPED P2P subset was executed locally (the full dataset P2P suite was not run); judge scoped acceptability.
2. REJECT: the executed CI shows at least one decisive, APPLICABLE failure: a declared FAIL_TO_PASS test still fails after the patch, OR a scoped PASS_TO_PASS regression is present. You MUST separate genuine failures from environment/pre-existing failures (bad at base too => not a regression) and from xfail / flaky / self-added-test traps, and justify applicability.
3. NEEDS_REVIEW: genuinely undecidable from the supplied evidence (ambiguous applicability, uninterpretable log, suspected flake). Do not force ACCEPT/REJECT.

Procedure: read the problem statement, candidate patch, maintainer test patch, and declared test ids; then compare the after-patch logs (FAIL_TO_PASS and scoped PASS_TO_PASS) against the BASE pre-patch log. Quote the exact pytest summary lines and any decisive failing test ids. The issue-symptom probe is derived from the issue text, not a maintainer acceptance test; it is supporting evidence only.

Respond with ONE JSON object and nothing else, using exactly these keys:
{
  "label": "ACCEPT" | "REJECT" | "NEEDS_REVIEW",
  "decisive_failing_test_ids": [ "exact test ids; empty array if none" ],
  "applicability_reason": "1-4 sentences; for REJECT explain why each cited failure is applicable and not pre-existing/xfail/flaky/self-added; for ACCEPT note scoped-P2P limitation if relevant",
  "xfail_flaky_self_added_concern": "yes/no + short note",
  "confidence": "high" | "medium" | "low",
  "evidence_summary": {
    "f2p_after_summary_line": "verbatim pytest summary from 05",
    "p2p_after_summary_line": "verbatim pytest summary from 06",
    "p2p_base_summary_line": "verbatim pytest summary from 07",
    "key_failures_or_diffs": ["..."]
  },
  "labeling_notes": "anything the human reviewer should double-check"
}"""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_key() -> str:
    key = os.environ.get("ZAI_API_KEY") or os.environ.get("GLM_API_KEY")
    if key:
        return key.strip()
    key_file = Path(os.path.expanduser("~")) / ".glm_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    raise SystemExit(
        "ERROR: no GLM key found. Set $env:ZAI_API_KEY or place the key in "
        "%USERPROFILE%\\.glm_key (outside the repo)."
    )


def make_client():
    from openai import OpenAI  # provided via `uv run --with openai`

    return OpenAI(api_key=load_key(), base_url=BASE_URL, timeout=300.0)


def ensure_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def packet_text(pid: str) -> tuple[str, list[dict]]:
    pdir = PACKET_ROOT / pid
    parts: list[str] = [f"BLIND PACKET {pid}"]
    file_meta: list[dict] = []
    for fname in PACKET_FILES:
        fpath = pdir / fname
        body = fpath.read_text(encoding="utf-8", errors="replace")
        file_meta.append(
            {"file": fname, "bytes": fpath.stat().st_size, "sha256": sha256_file(fpath)}
        )
        parts.append(f"\n===== FILE {fname} =====\n{body}")
    return "\n".join(parts), file_meta


def rmb_cost(tokens_in: int, tokens_out: int) -> Decimal:
    return (
        Decimal(tokens_in) * PRICE_RMB_IN_PER_1M / Decimal(1_000_000)
        + Decimal(tokens_out) * PRICE_RMB_OUT_PER_1M / Decimal(1_000_000)
    )


# The model occasionally renames keys (observed: it emitted
# "xfail_flaky_self_added<parameter>"). Normalize tolerant key names onto the
# canonical schema so downstream CSV/report parsing never breaks.
_KEY_ALIASES = {
    "xfail_flaky_self_added_concern": "xfail_flaky_self_added_concern",
    "xfail_flaky_self_added<parameter>": "xfail_flaky_self_added_concern",
    "xfail_flaky_selfadded_concern": "xfail_flaky_self_added_concern",
}


def normalize_verdict(parsed: dict) -> dict:
    if not isinstance(parsed, dict) or parsed.get("_parse_error"):
        return parsed
    out: dict = {}
    for k, v in parsed.items():
        out[_KEY_ALIASES.get(k, k)] = v
    if isinstance(out.get("label"), str):
        lab = out["label"].strip().upper().replace(" ", "_")
        if lab in ("ACCEPT", "REJECT", "NEEDS_REVIEW", "NEEDS-REVIEW"):
            out["label"] = "NEEDS_REVIEW" if lab == "NEEDS-REVIEW" else lab
    return out


def load_ledger() -> dict:
    if LEDGER_JSON.exists():
        return json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    return {
        "model": MODEL,
        "base_url": BASE_URL,
        "price_rmb_per_1m": {
            "input": str(PRICE_RMB_IN_PER_1M),
            "output": str(PRICE_RMB_OUT_PER_1M),
            "price_note": "conservative upper-bound list-price estimate; vendor bill authoritative",
        },
        "budget_guard_rmb": str(BUDGUARD_RMB),
        "research_excluded": True,
        "annotator_kind": "AI_preannotation_NOT_annotator2",
        "gold_tier_effect": "none_gold_remains_PROVISIONAL",
        "calls": [],
    }


def save_ledger(ledger: dict) -> None:
    LEDGER_JSON.write_text(
        json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def spent_so_far(ledger: dict) -> Decimal:
    return sum(
        (Decimal(c["estimated_cost_rmb"]) for c in ledger["calls"]), Decimal("0")
    )


def pre_call_guard(ledger: dict, est_input_chars: int, mode: str) -> None:
    est_in_tokens = int(est_input_chars / CHARS_PER_TOKEN) + 64
    worst = rmb_cost(est_in_tokens, MAX_OUTPUT_TOKENS)
    projected = spent_so_far(ledger) + worst
    if projected > BUDGUARD_RMB:
        raise SystemExit(
            f"BUDGET GUARD: projected spend RMB {projected:.4f} exceeds cap "
            f"{BUDGUARD_RMB} ({mode}); aborting before any API call."
        )


# --------------------------------------------------------------------------- #
# Modes
# --------------------------------------------------------------------------- #
def mode_ping(client) -> None:
    ensure_dirs()
    ledger = load_ledger()
    pre_call_guard(ledger, 64, "ping")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "Reply with the single token: pong"},
            {"role": "user", "content": "ping"},
        ],
        max_tokens=16,
        temperature=0.0,
    )
    dt = time.time() - t0
    served = resp.model
    usage = resp.usage
    cost = rmb_cost(usage.prompt_tokens, usage.completion_tokens)
    ledger["calls"].append(
        {
            "mode": "ping",
            "packet": None,
            "utc": utc_now(),
            "requested_model": MODEL,
            "served_model": served,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "estimated_cost_rmb": str(cost.quantize(Decimal("0.000001"))),
            "elapsed_s": round(dt, 2),
        }
    )
    save_ledger(ledger)
    print(f"PING ok served_model={served!r} reply={resp.choices[0].message.content!r}")
    print(
        f"tokens in={usage.prompt_tokens} out={usage.completion_tokens} "
        f"est_cost=RMB {cost:.6f}"
    )


def annotate_packet(client, ledger: dict, pid: str) -> dict:
    user_content, file_meta = packet_text(pid)
    pre_call_guard(ledger, len(user_content), f"annotate {pid}")

    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )
    dt = time.time() - t0
    raw_text = resp.choices[0].message.content
    served = resp.model
    usage = resp.usage
    cost = rmb_cost(usage.prompt_tokens, usage.completion_tokens)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {"_parse_error": True, "raw_text": raw_text}
    parsed = normalize_verdict(parsed)

    record = {
        "cohort": COHORT_LABEL,
        "packet": pid,
        "utc": utc_now(),
        "requested_model": MODEL,
        "served_model": served,
        "research_excluded": True,
        "annotator_kind": "AI_preannotation_NOT_annotator2",
        "gold_tier": "PROVISIONAL_unchanged",
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "estimated_cost_rmb": str(cost.quantize(Decimal("0.000001"))),
        "elapsed_s": round(dt, 2),
        "packet_files": file_meta,
        "verdict": parsed,
    }

    (RAW_DIR / f"{pid}_response.json").write_text(
        json.dumps(
            {
                "served_model": served,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "finish_reason": resp.choices[0].finish_reason,
                "content": raw_text,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    ledger["calls"].append(
        {
            "mode": "annotate",
            "packet": pid,
            "utc": utc_now(),
            "requested_model": MODEL,
            "served_model": served,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "estimated_cost_rmb": str(cost.quantize(Decimal("0.000001"))),
            "elapsed_s": round(dt, 2),
        }
    )
    save_ledger(ledger)
    RECORD_DIR.mkdir(parents=True, exist_ok=True)
    (RECORD_DIR / f"{pid}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"{pid}: {parsed.get('label', 'PARSE_ERROR')} "
        f"(in={usage.prompt_tokens} out={usage.completion_tokens} "
        f"RMB {cost:.6f} {dt:.1f}s)"
    )
    return record


def mode_run(client, force: bool, only: list[str] | None = None) -> None:
    ensure_dirs()
    ledger = load_ledger()
    targets = only if only else PACKET_IDS
    done_packets = {
        c["packet"] for c in ledger["calls"] if c.get("mode") == "annotate"
    }
    records: list[dict] = []
    for pid in targets:
        if pid not in PACKET_IDS:
            raise SystemExit(f"unknown packet {pid}")
        if pid in done_packets and not force:
            print(f"{pid}: already annotated, skipping (use --force to redo)")
            continue
        rec = annotate_packet(client, ledger, pid)
        records.append(rec)

    # Rebuild the aggregate jsonl idempotently from one record file per packet.
    lines: list[str] = []
    for pid in PACKET_IDS:
        rp = RECORD_DIR / f"{pid}.json"
        if rp.exists():
            lines.append(rp.read_text(encoding="utf-8").strip())
    if lines:
        payload = [json.loads(x) for x in lines]
        LABELS_JSON.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in payload) + "\n",
            encoding="utf-8",
        )

    total = spent_so_far(ledger)
    tin = sum(c["prompt_tokens"] for c in ledger["calls"] if c.get("mode") == "annotate")
    tout = sum(c["completion_tokens"] for c in ledger["calls"] if c.get("mode") == "annotate")
    print(
        f"\nannotation calls: in={tin} out={tout} tokens; "
        f"ledger total (incl ping) est RMB {total:.6f}"
    )


def _saved_verdict(pid: str) -> dict:
    rp = RECORD_DIR / f"{pid}.json"
    if not rp.exists():
        raise SystemExit("run --run before --fr")
    return json.loads(rp.read_text(encoding="utf-8"))


def mode_fr(client) -> None:
    ensure_dirs()
    ledger = load_ledger()
    p01, p02, p08 = (_saved_verdict(p) for p in ("P01", "P02", "P08"))

    def brief(row: dict) -> str:
        v = row["verdict"]
        return json.dumps(
            {
                "packet": row["packet"],
                "label": v.get("label"),
                "decisive_failing_test_ids": v.get("decisive_failing_test_ids"),
                "reason": v.get("applicability_reason"),
                "concern": v.get("xfail_flaky_self_added_concern"),
                "evidence_summary": v.get("evidence_summary"),
            },
            ensure_ascii=False,
        )

    # Post-unblind: identities and the fact that 14248/15875 are the two REJECT
    # cases are revealed here, AFTER all blind labels have been persisted.
    p01_text, _ = packet_text("P01")
    p02_text, _ = packet_text("P02")
    p08_text, _ = packet_text("P08")

    fr_prompt = f"""You earlier acted as a BLIND patch adjudicator. The packets have now been unsealed for a post-unblind FOCUSED REVIEW. Your earlier blind labels were:
- P01 (sympy issue 14248): {brief(p01)}
- P02 (sympy issue 19495): {brief(p02)}
- P08 (sympy issue 15875): {brief(p08)}

Answer TWO focused questions for the human reviewer. Read the three full packets again (they follow).

FR1 (issue 19495 / P02): the maintainer acceptance concern is whether the FAIL_TO_PASS change shown here constitutes an INSTRUMENT FIX (the test/probe instrument was wrong and was corrected, target behaviour stable) or an ORACLE REDEFINITION (the accepted correctness oracle itself was redefined). Classify and explain from the patch + test patch + issue-symptom probe.

FR2 (issues 14248 / P01 and 15875 / P08): these are the two REJECT cases. Decide whether both REJECTs apply ONE shared standard (the same kind of decisive applicable failure) or DIFFERENT standards, based strictly on the evidence in the two packets.

Respond with ONE JSON object, no other text:
{{
  "FR1_19495": {{
    "choice": "instrument_fix" | "oracle_redefinition" | "undecidable",
    "reason": "3-6 sentences grounded in the files",
    "rubric_amendment_needed": "yes/no + exact suggested wording if yes",
    "confidence": "high" | "medium" | "low"
  }},
  "FR2_14248_15875": {{
    "choice": "same_standard" | "different_standard" | "undecidable",
    "reason": "3-6 sentences; name the shared/distinct failure type with test ids",
    "rubric_amendment_needed": "yes/no + exact suggested wording if yes",
    "confidence": "high" | "medium" | "low"
  }}
}}

================ PACKET P01 (14248) ================
{p01_text}

================ PACKET P02 (19495) ================
{p02_text}

================ PACKET P08 (15875) ================
{p08_text}
"""
    est_chars = len(fr_prompt)
    pre_call_guard(ledger, est_chars, "focused-review")
    t0 = time.time()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a meticulous code-review adjudicator. Reply with JSON only.",
            },
            {"role": "user", "content": fr_prompt},
        ],
        max_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
        response_format={"type": "json_object"},
        extra_body={"thinking": {"type": "disabled"}},
    )
    dt = time.time() - t0
    raw_text = resp.choices[0].message.content
    usage = resp.usage
    cost = rmb_cost(usage.prompt_tokens, usage.completion_tokens)
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = {"_parse_error": True, "raw_text": raw_text}
    parsed = normalize_verdict(parsed)

    out = {
        "utc": utc_now(),
        "served_model": resp.model,
        "research_excluded": True,
        "annotator_kind": "AI_preannotation_NOT_annotator2",
        "post_unblind": True,
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "estimated_cost_rmb": str(cost.quantize(Decimal("0.000001"))),
        "focused_review": parsed,
    }
    FR_JSON.write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ledger["calls"].append(
        {
            "mode": "focused_review",
            "packet": "P01+P02+P08",
            "utc": utc_now(),
            "requested_model": MODEL,
            "served_model": resp.model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "estimated_cost_rmb": str(cost.quantize(Decimal("0.000001"))),
            "elapsed_s": round(dt, 2),
        }
    )
    save_ledger(ledger)
    print("focused review saved:")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    print(f"ledger total est RMB {spent_so_far(ledger):.6f}")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def mode_report() -> None:
    """Post-unblind comparison vs PROVISIONAL oracle gold; human-correction CSV."""
    ensure_dirs()
    sealed = json.loads(SEALED_MAP_JSON.read_text(encoding="utf-8"))["mapping_packet_to_instance"]
    gold: dict[str, dict] = {}
    for line in ORACLE_GOLD_JSONL.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        gold[row["instance_id"]] = row

    rows: list[dict] = []
    for pid in PACKET_IDS:
        rec_path = RECORD_DIR / f"{pid}.json"
        if not rec_path.exists():
            raise SystemExit(f"missing record {pid}; run --run first")
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        instance = sealed[pid]
        g = gold[instance]
        v = rec["verdict"]
        gl = v.get("label", "")
        og = g["oracle_gold"]
        rows.append(
            {
                "cohort": COHORT_LABEL,
                "packet": pid,
                "instance_unblinded": instance,
                "provisional_oracle_gold": og,
                "ai_glm_suggestion": gl,
                "glm_agrees_with_gold": "YES" if gl == og else "NO",
                "glm_confidence": v.get("confidence", ""),
                "glm_decisive_failing_test_ids": ";".join(
                    v.get("decisive_failing_test_ids", []) or []
                ),
                "glm_applicability_reason": v.get("applicability_reason", ""),
                "glm_xfail_flaky_self_added_concern": v.get(
                    "xfail_flaky_self_added_concern", ""
                ),
                "glm_labeling_notes": v.get("labeling_notes", ""),
                "human_corrected_label": "",
                "human_agrees_with_glm": "",
                "human_notes": "",
            }
        )

    csv_fields = [
        "cohort", "packet", "instance_unblinded", "provisional_oracle_gold",
        "ai_glm_suggestion", "glm_agrees_with_gold", "glm_confidence",
        "glm_decisive_failing_test_ids", "glm_applicability_reason",
        "glm_xfail_flaky_self_added_concern", "glm_labeling_notes",
        "human_corrected_label", "human_agrees_with_glm", "human_notes",
    ]
    with LABELS_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=csv_fields)
        w.writeheader()
        w.writerows(rows)

    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    total = spent_so_far(ledger)
    annot = [c for c in ledger["calls"] if c.get("mode") == "annotate"]
    tin = sum(c["prompt_tokens"] for c in annot)
    tout = sum(c["completion_tokens"] for c in annot)
    n_agree = sum(r["glm_agrees_with_gold"] == "YES" for r in rows)
    n = len(rows)

    def confusion(a: str, b: str) -> str:
        return f"{a} vs gold {b}"

    disagree = [r for r in rows if r["glm_agrees_with_gold"] == "NO"]
    fr = json.loads(FR_JSON.read_text(encoding="utf-8")) if FR_JSON.exists() else None

    md: list[str] = []
    md.append("# GLM auxiliary pre-annotation — evaluation report (NOT a research result)\n")
    md.append(
        "**Status:** exploratory, decision-support only. GLM-4.6 is an AI, **not** "
        "independent annotator #2. These labels are excluded from the GPT/DeepSeek "
        "80-cell research results (`research_excluded=true`), are **not pooled**, and "
        "do **not** upgrade Gold, which stays **PROVISIONAL**. The three right-most "
        "columns of the CSV are for the human reviewer to fill.\n"
    )
    md.append(f"- Model served: `{ledger['calls'][0]['served_model']}` (OpenAI-compatible bigmodel endpoint)")
    md.append("- Mode: blind static packet annotation (same 9-file packet + same human rubric), thinking disabled, temperature 0.2, JSON mode")
    md.append(f"- Cohort: {COHORT_LABEL} packets P01–P{len(PACKET_IDS):02d} ({n}/{len(PACKET_IDS)})")
    md.append(f"- Annotation tokens: in={tin:,} out={tout:,}")
    md.append(
        f"- Estimated cost: **RMB {total:.4f}** (conservative upper-bound list price "
        f"¥{ledger['price_rmb_per_1m']['input']}/M in, ¥{ledger['price_rmb_per_1m']['output']}/M out; "
        "vendor console bill authoritative)"
    )
    md.append(f"- Hard pre-call budget guard: RMB {BUDGUARD_RMB} (never approached)\n")

    md.append("## Headline\n")
    md.append(f"- GLM agrees with PROVISIONAL oracle gold on **{n_agree}/{n}** packets.")
    if disagree:
        md.append(f"- **{len(disagree)} disagreement(s), flagged for human adjudication:**")
        for r in disagree:
            md.append(
                f"  - {r['packet']} (unsealed {r['instance_unblinded']}): "
                f"GLM **{r['ai_glm_suggestion']}** vs oracle gold **{r['provisional_oracle_gold']}**"
            )
    md.append("")

    md.append("## Label table\n")
    md.append("| Packet | Instance (unblinded) | GLM | Gold (PROV.) | Agree | Conf. | Decisive failing test ids |")
    md.append("|---|---|---|---|---|---|---|")
    for r in rows:
        ids = r["glm_decisive_failing_test_ids"] or "—"
        md.append(
            f"| {r['packet']} | {r['instance_unblinded']} | {r['ai_glm_suggestion']} "
            f"| {r['provisional_oracle_gold']} | {r['glm_agrees_with_gold']} "
            f"| {r['glm_confidence']} | {ids} |"
        )
    md.append("")

    if disagree:
        md.append("## Disagreement detail (read carefully before correcting)\n")
        for r in disagree:
            md.append(f"### {r['packet']} — {r['instance_unblinded']}")
            md.append(f"- GLM: **{r['ai_glm_suggestion']}**; oracle gold: **{r['provisional_oracle_gold']}**")
            md.append(f"- GLM reason: {r['glm_applicability_reason']}")
            md.append(f"- GLM trap concern: {r['glm_xfail_flaky_self_added_concern']}")
            md.append(f"- GLM notes: {r['glm_labeling_notes']}")
            md.append(
                "- **How to adjudicate:** open the packet and check (a) whether each "
                "cited failing test is in the *declared* set `04_declared_test_ids.json`, "
                "(b) whether it also failed at BASE in log 07 (pre-existing => not a "
                "regression), and (c) whether it is an xfail/flaky/self-added-test trap "
                "or a genuine maintainer-acceptance failure. The oracle gold counts only "
                "declared checks; a failure introduced by the maintainer gold test patch "
                "but absent from the declared list is the boundary that most often drives "
                "a GLM-vs-gold split."
            )
            if COHORT_KEY == "G3C1" and r["packet"] == "P03":
                md.append(
                    "- **Specifics of this P03/19346 case:** oracle gold = ACCEPT because "
                    "only the declared F2P `test_dict` is counted (41 checks / 0 failures). "
                    "The failing `test_set` comes from the maintainer gold test patch "
                    "(`srepr(set()) == 'set()'`) and is NOT in the declared F2P list; the "
                    "candidate's new `_print_set` wrongly emits `'{}'` for an empty set. "
                    "GLM mislabels it as a P2P regression 'that passed at base' (the test "
                    "did not exist at base); the correct framing is an undeclared-but-"
                    "authoritative acceptance failure."
                )
            md.append("")

    if fr:
        md.append("## Focused review (post-unblind AI opinion; not a human answer)\n")
        f = fr["focused_review"]
        md.append("| Item | GLM choice | Conf. | Rubric amendment |")
        md.append("|---|---|---|---|")
        fr1, fr2 = f.get("FR1_19495", {}), f.get("FR2_14248_15875", {})
        md.append(f"| FR1 (19495) instrument vs oracle | {fr1.get('choice')} | {fr1.get('confidence')} | {fr1.get('rubric_amendment_needed')} |")
        md.append(f"| FR2 (14248+15875) standard | {fr2.get('choice')} | {fr2.get('confidence')} | {fr2.get('rubric_amendment_needed')} |")
        md.append(f"\n- **FR1 reason:** {fr1.get('reason')}")
        md.append(f"- **FR2 reason:** {fr2.get('reason')}\n")

    md.append("## Artifacts\n")
    md.append("- Raw responses: `raw/P0x_response.json` (verbatim model JSON, usage, finish reason)")
    md.append("- Per-packet records: `records/P0x.json` (with packet file sha256 provenance)")
    md.append("- Human correction worksheet: `glm_prelabels_for_human_correction.csv`")
    md.append("- Token/cost ledger: `glm_cost_ledger.json`")
    if FR_JSON.exists():
        md.append("- FR1/FR2: `glm_focused_review_fr1_fr2.json`")
    md.append("- Runner: `stance_pilot/evidence/g3c1_glm_aux_preann.py` (imports no frozen modules)\n")
    md.append("> Boundary reminder: fill `human_corrected_label` / `human_agrees_with_glm` / "
              "`human_notes` yourself. Only an independent human + arbiter can populate "
              "annotator2 and move Gold off PROVISIONAL.\n")

    REPORT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {LABELS_CSV.name} and {REPORT_MD.name}")
    print(f"agreement {n_agree}/{n}; est total RMB {total:.4f}")
    for r in disagree:
        print("  DISAGREE", r["packet"], r["instance_unblinded"],
              confusion(r["ai_glm_suggestion"], r["provisional_oracle_gold"]))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GLM auxiliary pre-annotation (not a research result)")
    ap.add_argument("--ping", action="store_true", help="tiny auth/model check")
    ap.add_argument("--run", action="store_true", help="blind-annotate all packets in the cohort")
    ap.add_argument("--fr", action="store_true", help="post-unblind FR1/FR2 review (G3-C.1 only)")
    ap.add_argument("--report", action="store_true", help="offline: build human-correction CSV + markdown report")
    ap.add_argument(
        "--cohort",
        choices=sorted(COHORTS),
        default="G3C1",
        help="which blind-packet cohort to evaluate (default G3C1); outputs are isolated per cohort",
    )
    ap.add_argument("--force", action="store_true", help="redo annotated packets")
    ap.add_argument(
        "--only",
        nargs="+",
        metavar="Pxx",
        help="limit --run to specific packet ids (pilot single packet)",
    )
    args = ap.parse_args(argv)
    configure(args.cohort)

    if not (args.ping or args.run or args.fr or args.report):
        ap.print_help()
        return 2

    if args.fr and not _CFG["has_focused_review"]:
        raise SystemExit(f"--fr focused review is only defined for G3-C.1 (not {COHORT_LABEL})")

    if args.report:
        mode_report()
    if args.ping or args.run or args.fr:
        client = make_client()
        if args.ping:
            mode_ping(client)
        if args.run:
            mode_run(client, force=args.force, only=args.only)
        if args.fr:
            mode_fr(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
