"""GroundedReview Gate G3-C.1.1 - task 13 (part 2): freeze manifest for the
whole evidence_store_g3c11 output tree.

Recursively hashes every file produced by this gate (audit/, human_annotation/,
report/), builds the canonical {'files': sorted} digest exactly like the parent
gates, pins the four parent freeze manifests, and records the approved
zero-API scope. The manifest itself is excluded from its own digest and is the
only file written into freeze/.

Run:  uv run --offline --python 3.9 -m evidence.g3c11_freeze   (run LAST)
"""
from __future__ import annotations

from evidence import g3c11_common as K

PARENT_MANIFESTS = [
    ("g3c1_freeze", K.G3C1_FREEZE),
    ("g3c0_design_freeze", K.G3C0_DESIGN_FREEZE),
    ("g3b4_result_freeze", K.G3B4_RESULT_FREEZE),
    ("g3b3_result_freeze", K.G3B3_RESULT_FREEZE),
    ("g3b3_data_freeze", K.G3B3_DATA_FREEZE),
]


def parent_pins():
    pins = []
    for name, path in PARENT_MANIFESTS:
        raw = path.read_bytes()
        pin = {"name": name,
               "path": str(path.relative_to(K.HERE)).replace("\\", "/"),
               "file_sha256": K.sha256_bytes(raw),
               "file_bytes": len(raw)}
        try:
            doc = K.read_json(path)
            if "files_canonical_sha256" in doc:
                pin["parent_files_canonical_sha256"] = \
                    doc["files_canonical_sha256"]
            if "n_files" in doc:
                pin["parent_n_files"] = doc["n_files"]
            for k in ("all_ok", "passed"):
                if k in doc:
                    pin["parent_%s" % k] = doc[k]
        except Exception:  # a parent manifest may store digest differently
            pass
        pins.append(pin)
    return pins


def collect_entries():
    entries = []
    root = K.G3C11
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if "__pycache__" in path.parts or rel.endswith(".pyc"):
            continue
        if rel == K.OUT_FREEZE.relative_to(root).as_posix().replace("\\", "/"):
            continue  # never hash this manifest into itself
        raw = path.read_bytes()
        entries.append({"relpath": rel, "sha256": K.sha256_bytes(raw),
                        "bytes": len(raw)})
    entries.sort(key=lambda e: e["relpath"])
    return entries


def main():
    K.ensure_out_dirs()
    entries = collect_entries()
    canonical = K.canonical_bytes({"files": entries})
    digest = K.sha256_bytes(canonical)
    pins = parent_pins()

    by_dir = {}
    for e in entries:
        top = e["relpath"].split("/", 1)[0]
        d = by_dir.setdefault(top, {"files": 0, "bytes": 0})
        d["files"] += 1
        d["bytes"] += e["bytes"]

    manifest = {
        "document": "GroundedReview Gate G3-C.1.1 zero-API audit freeze "
                    "manifest (task 13)",
        "gate": "G3-C.1.1",
        "design_version": K.G3C11_DESIGN_VERSION,
        "protocol_version": K.G3C11_PROTOCOL_VERSION,
        "root": "evidence_store_g3c11",
        "n_files": len(entries),
        "total_bytes": sum(e["bytes"] for e in entries),
        "files_by_top_dir": by_dir,
        "files": entries,
        "files_canonical_sha256": digest,
        "canonical_form": "json.dumps({'files': sorted(entries)}, "
                          "ensure_ascii=False, indent=2, sort_keys=True) + '\\n'",
        "manifest_excluded_from_own_digest": True,
        "parent_pins": pins,
        "all_parent_pins_read_only": True,
        "approved_scope": K.APPROVED_SCOPE,
        "scope_assertions": {
            "new_api_spend_usd": 0,
            "new_issues_added": 0,
            "real_model_calls": 0,
            "historical_gold_modified": False,
            "frozen_raw_tests_rewritten": False,
            "new_data_collection": False,
            "git_commit_or_add": False,
            "r2_or_gemini_used": False,
            "ai_labels_substituted_for_human": False,
            "all_18_gold_remain_provisional": True,
            "annotator2": "NOT_OBTAINED",
            "g3c2_executed": False,
        },
        "gate3c2_recommendation": "NO-GO pending PC1/PC2/PC3; see report/",
        "next_action": "STOP and await separate written G3-C.2 approval.",
    }
    K.write_canonical(K.OUT_FREEZE, manifest)

    # self-check: re-hash tree excluding the now-written manifest
    re_entries = collect_entries()
    ok = ([e["relpath"] for e in re_entries] == [e["relpath"] for e in entries]
          and K.sha256_bytes(K.canonical_bytes(
              {"files": re_entries})) == digest)
    print("n_files:", len(entries), "by_dir:", by_dir)
    print("files_canonical_sha256:", digest)
    print("self_check_excluding_manifest_ok:", ok)
    print("parent pins:", [(p["name"], p["file_sha256"][:12]) for p in pins])
    print("->", K.OUT_FREEZE.relative_to(K.HERE))


if __name__ == "__main__":
    main()
