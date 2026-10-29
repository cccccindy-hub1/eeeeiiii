"""Paper Sprint shared helpers (zero-API, read-only over frozen stores).

All paper numbers must be produced by scripts in this package so every table
cell can be traced to a frozen source file + sha256.
"""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PS = ROOT / "paper_sprint"
TBL = PS / "tables"
FIG = PS / "figures"

CONDITIONS = ["T2D-T", "T3D-Strict", "T3D-Escalate", "T2A-T", "T3A-T"]
# Conditions whose condition-gold is non-decisive (acceptance outcomes withheld)
RESTRICTED = ["T2D-T", "T3D-Strict"]
# Conditions that deliver decisive evidence (escalation grants tier-A outcomes,
# or tier-A directly): condition gold == oracle gold.
SUFFICIENT = ["T3D-Escalate", "T2A-T", "T3A-T"]

MODELS = ["deepseek-flash", "gpt-4.1-mini"]
MODEL_SHORT = {"deepseek-flash": "DeepSeek", "gpt-4.1-mini": "GPT"}

G3A_ISSUES = [
    "sympy__sympy-24443", "sympy__sympy-13615", "sympy__sympy-19783",
    "sympy__sympy-20590", "sympy__sympy-17630", "sympy__sympy-21847",
    "sympy__sympy-15349", "sympy__sympy-24213", "sympy__sympy-17318",
    "sympy__sympy-13974",
]
G3C1_ISSUES = [
    "sympy__sympy-14248", "sympy__sympy-19495", "sympy__sympy-19346",
    "sympy__sympy-19040", "sympy__sympy-16886", "sympy__sympy-19637",
    "sympy__sympy-22914", "sympy__sympy-15875",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(rel: str) -> dict:
    with (ROOT / rel).open(encoding="utf-8") as fh:
        return json.load(fh)


def short_issue(iid: str) -> str:
    return iid.replace("sympy__sympy-", "")


def write_csv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
