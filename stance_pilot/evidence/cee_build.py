"""CEE offline builder — construct the 22 frozen, byte-identical evidence
bundles and the independent CEE gold. READ-ONLY against the frozen store.

Reads (all frozen, never modified):
  * evidence_store_w21/{phase2,phase3,wave2}_fixtures.jsonl  (22 fixtures)
  * evidence_store_w21/wave2_pilot_raw_rows.jsonl            (issue/patch)
  * evidence_store_w21/wave2_gold.jsonl                      (cross-check only)
  * the signed artifacts + attestations under evidence_store_w21/

Writes only into the independent namespace evidence_store_cee/:
  bundles/<bundle_id>.txt   exact user-turn bytes BOTH providers receive
  cee_gold.jsonl            independently derived CEE gold (one row/bundle)
  cee_build_manifest.json   hashes + provenance for every bundle

Hard rules enforced here:
  * the served artifact must be HMAC-authentic (refuses otherwise);
  * the independently derived CEE gold must equal the frozen oracle gold row
    for every fixture (the build aborts on the first mismatch);
  * no scenario label / ground-truth token is rendered into a bundle (the
    record is passed through the frozen neutralizer);
  * deterministic output: canonical JSON, sorted manifest keys, bytes written
    verbatim so line endings can never change the frozen bytes.

Zero network, zero paid API calls.

    uv run --python 3.13 -m evidence.cee_build
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from evidence.schemas import canonical_dumps
from evidence.store import ArtifactStore
from evidence.ternary import read_jsonl
from evidence.prompts import CLAIM_POSITIVE
from evidence.phase3_run import fixture_manifest_identity, _sha256_file
from evidence import cee_protocol as cee

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE = ROOT / 'evidence_store_w21'
DEFAULT_OUT = ROOT / 'evidence_store_cee'
FIXTURE_FILES = ('phase2_fixtures.jsonl', 'phase3_fixtures.jsonl',
                 'wave2_fixtures.jsonl')
RAW_FILE = 'wave2_pilot_raw_rows.jsonl'
GOLD_FILE = 'wave2_gold.jsonl'

_FORBIDDEN_TOKENS = ('oracle_gold', 'condition_gold', 'merge_acceptable',
                     'patch_correct', 'ground truth', '"scenario"')


def _bundle_id(scenario: str, fid: str, aid: str) -> str:
    h = hashlib.sha256(
        f'{scenario}|{fid}|{aid}'.encode('utf-8')).hexdigest()[:16]
    return f'cee_{h}'


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_fixture_index(store_root: Path):
    """Return (ordered_fixtures, fixture_paths, raw_by_id, gold_index).

    Order follows the frozen wave2 gold file (sorted by
    scenario,id,served_artifact_id) so bundle order is canonical and every
    bundle has exactly one frozen gold row.
    """
    paths = [str(store_root / f) for f in FIXTURE_FILES]
    fixtures = []
    for fp in paths:
        fixtures.extend(read_jsonl(fp))
    fx_by_key = {(f['scenario'], f['id'], f['served_artifact_id']): f
                 for f in fixtures}
    if len(fx_by_key) != len(fixtures):
        raise SystemExit('cee_build: duplicate fixture keys in manifests')
    raw_by_id = {r['id']: r
                 for r in read_jsonl(str(store_root / RAW_FILE))}
    gold_rows = read_jsonl(str(store_root / GOLD_FILE))
    gold_index = {(g['scenario'], g['id'], g['served_artifact_id']): g
                  for g in gold_rows}
    ordered = []
    for g in gold_rows:
        key = (g['scenario'], g['id'], g['served_artifact_id'])
        if key not in fx_by_key:
            raise SystemExit(f'cee_build: no fixture manifest row for {key}')
        ordered.append(fx_by_key[key])
    if len(ordered) != len(fx_by_key):
        missing = sorted(set(fx_by_key) - set(gold_index))
        raise SystemExit(f'cee_build: fixtures without gold row: {missing}')
    return ordered, paths, raw_by_id, gold_index


def build_all(store_root: Path):
    """Single read-only pass. Returns (bundles, cee_gold_rows, manifest,
    payload_map). Aborts on any authenticity / fact / gold disagreement."""
    fixtures, fixture_paths, raw_by_id, gold_index = \
        load_fixture_index(store_root)
    store = ArtifactStore(str(store_root))
    prompt_fp = cee.cee_prompt_fingerprint()
    schema_sha = _sha256_bytes(
        canonical_dumps(cee.CEE_DECISION_SCHEMA).encode('utf-8'))

    bundles, cee_gold_rows, payload_map = [], [], {}
    for fx in fixtures:
        key = (fx['scenario'], fx['id'], fx['served_artifact_id'])
        grow = gold_index[key]
        if fx['id'] not in raw_by_id:
            raise SystemExit(f"cee_build: raw row missing for {fx['id']}")
        raw = raw_by_id[fx['id']]

        # Primary-evidence re-derivation (HMAC enforced inside loader).
        from evidence.visibility import load_fixture_facts
        facts = load_fixture_facts(store, fx)
        if not facts['authentic_signature']:
            raise SystemExit(
                f"cee_build: refusing inauthentic artifact "
                f"{fx['served_artifact_id']}")

        grow_f = grow.get('facts', {})
        for fk in ('linked', 'fresh', 'complete'):
            if bool(facts[fk]) != bool(grow_f[fk]):
                raise SystemExit(
                    f'cee_build: recomputed fact {fk}={facts[fk]} disagrees '
                    f"with frozen gold {grow_f[fk]} for {key}")
        if int(facts['executed_failure_count']) \
                != int(grow_f['executed_failure_count']) \
                or int(facts['executed_check_count']) \
                != int(grow_f['executed_check_count']):
            raise SystemExit(
                f'cee_build: recomputed executed counts disagree with frozen '
                f'gold for {key}')

        cgrow = cee.derive_cee_gold_row(fx, facts)
        if cgrow['cee_gold'] != grow['oracle_gold']:
            raise SystemExit(
                f"cee_build: CEE gold {cgrow['cee_gold']} != frozen oracle "
                f"gold {grow['oracle_gold']} for {key}")
        if bool(cgrow['decisive_failure']) != bool(grow['decisive_failure']):
            raise SystemExit(
                f'cee_build: decisive_failure disagrees with frozen gold '
                f'for {key}')

        claim = fx.get('claim') or CLAIM_POSITIVE
        body = cee.render_bundle_body(
            issue=raw['problem_statement'], patch=raw['model_patch'],
            claim=claim, facts=facts, fx=fx)
        bundle_bytes = cee.render_user_content(body).encode('utf-8')

        # Leak guard on the EVIDENCE BODY bytes (record/probe/integrity).
        # The item-invariant prompt head legitimately contains the frozen
        # ternary sentence "Ground truth about mergeability is never given",
        # so the label-token scan is scoped to the body, not the whole turn.
        low = body.lower()
        for leak in _FORBIDDEN_TOKENS:
            if leak in low:
                raise SystemExit(
                    f'cee_build: forbidden label token {leak!r} rendered in '
                    f'bundle for {key}')

        bid = _bundle_id(*key)
        if bid in payload_map:
            raise SystemExit(f'cee_build: bundle id collision {bid}')
        payload_map[bid] = bundle_bytes
        rec_sha = _sha256_bytes(
            canonical_dumps(facts['artifact_record']).encode('utf-8'))
        bundles.append({
            'bundle_id': bid,
            'scenario': fx['scenario'], 'id': fx['id'],
            'instance_id': fx['instance_id'],
            'served_artifact_id': fx['served_artifact_id'],
            'base_commit': fx['base_commit'],
            'patch_sha256': fx['patch_sha256'],
            'evidence_class': cgrow['evidence_class'],
            'cee_gold': cgrow['cee_gold'],
            'frozen_oracle_gold': grow['oracle_gold'],
            'oracle_gold_equal': True,
            'bundle_sha256': _sha256_bytes(bundle_bytes),
            'bundle_bytes': len(bundle_bytes),
            'served_artifact_record_sha256': rec_sha,
            'prompt_fingerprint': prompt_fp,
        })
        cgrow['bundle_id'] = bid
        cgrow['frozen_oracle_gold'] = grow['oracle_gold']
        cee_gold_rows.append(cgrow)

    manifest = {
        'cee_protocol_version': cee.CEE_PROTOCOL_VERSION,
        'cee_condition': cee.CEE_CONDITION,
        'generated_by': 'evidence/cee_build.py',
        'store_root_read_only': str(store_root),
        'n_bundles': len(bundles),
        'n_unique_instances': len({b['instance_id'] for b in bundles}),
        'prompt_fingerprint': prompt_fp,
        'decision_schema_sha256': schema_sha,
        'decision_schema_name': cee.CEE_DECISION_SCHEMA['name'],
        'provider_neutral_contract': {
            'schema_mode': 'json_schema strict on BOTH providers',
            'all_properties_required': True,
            'additional_properties': False,
            'note': 'every declared property is in required, so the SAME '
                    'strict schema object is legal for OpenAI Structured '
                    'Outputs and DeepSeek; a json_object downgrade is NOT '
                    'part of the CEE design.'},
        'tools': 'none (single turn; no escalation; fixed bundle only)',
        'fixture_manifest_identity': fixture_manifest_identity(fixture_paths),
        'raw_rows_sha256': _sha256_file(str(store_root / RAW_FILE)),
        'frozen_gold_sha256': _sha256_file(str(store_root / GOLD_FILE)),
        'class_counts': {
            cee.CLASS_SUFFICIENT_POSITIVE:
                sum(b['evidence_class'] == cee.CLASS_SUFFICIENT_POSITIVE
                    for b in bundles),
            cee.CLASS_DECISIVE_NEGATIVE:
                sum(b['evidence_class'] == cee.CLASS_DECISIVE_NEGATIVE
                    for b in bundles),
            cee.CLASS_INSUFFICIENT:
                sum(b['evidence_class'] == cee.CLASS_INSUFFICIENT
                    for b in bundles)},
        'no_post_hoc_selection': 'sample is the FULL 22-fixture frozen set; '
                                 'no bundle was chosen or adjusted using any '
                                 'model output or observed E1 error',
        'bundles': bundles,
    }
    return bundles, cee_gold_rows, manifest, payload_map


def write_outputs(out_root: Path, bundles, cee_gold_rows, manifest,
                  payload_map):
    out_root = Path(out_root)
    bdir = out_root / 'bundles'
    bdir.mkdir(parents=True, exist_ok=True)
    for b in bundles:
        (bdir / f"{b['bundle_id']}.txt").write_bytes(
            payload_map[b['bundle_id']])
    gold_text = ''.join(canonical_dumps(r) + '\n' for r in cee_gold_rows)
    (out_root / 'cee_gold.jsonl').write_bytes(gold_text.encode('utf-8'))
    manifest = dict(manifest)
    manifest['cee_gold_sha256'] = _sha256_bytes(gold_text.encode('utf-8'))
    import json
    (out_root / 'cee_build_manifest.json').write_bytes(
        (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
         + '\n').encode('utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--store', default=str(DEFAULT_STORE))
    ap.add_argument('--out', default=str(DEFAULT_OUT))
    a = ap.parse_args()
    store_root = Path(a.store)
    out_root = Path(a.out)
    try:
        out_root.resolve().relative_to(DEFAULT_OUT.resolve())
    except ValueError:
        raise SystemExit(
            f'CEE SAFETY: output must live under {DEFAULT_OUT}, got {out_root}')

    bundles, cee_gold_rows, manifest, payload_map = build_all(store_root)
    write_outputs(out_root, bundles, cee_gold_rows, manifest, payload_map)
    print(f'CEE build OK: {len(bundles)} bundles '
          f"({manifest['n_unique_instances']} issues) -> {out_root}")
    for cls, n in manifest['class_counts'].items():
        print(f'  {cls}: {n}')
    print(f"  prompt_fingerprint={manifest['prompt_fingerprint']}")
    print('  all CEE gold rows equal frozen oracle_gold: yes')
    print('  offline only: read frozen store; zero network / zero paid calls')


if __name__ == '__main__':
    main()
