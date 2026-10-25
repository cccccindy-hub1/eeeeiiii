#!/usr/bin/env python3
"""Flip replication analysis: do the pilot flips survive independent re-runs?"""
import argparse, collections, json
from pilot import read_jsonl, parse_decision

ARMS = ("neutral", "positive", "negative")
NL = chr(10)

def wilson(k, n, z=1.96):
    if n == 0: return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / d
    return (max(0.0, c - h), min(1.0, c + h))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="replication_results.jsonl")
    ap.add_argument("--meta", default="replication_meta.json")
    ap.add_argument("--out", default="replication_report.json")
    a = ap.parse_args()

    meta = json.load(open(a.meta))
    votes = collections.defaultdict(list)
    for r in read_jsonl(a.results):
        if r.get("error"): continue
        arm = r["condition"].split("_")[0]
        votes[(r["id"], arm)].append(r.get("parsed") or parse_decision(r.get("answer", "")))

    print("== per-patch replication ==")
    out = {}
    for pid in sorted(meta):
        role, gt = meta[pid]["role"], meta[pid]["ground_truth"]
        print(NL + pid + "  [" + role + ", GT=" + gt + "]")
        row = {}
        for arm in ARMS:
            v = [x for x in votes.get((pid, arm), []) if x in ("ACCEPT", "REJECT")]
            other = [x for x in votes.get((pid, arm), []) if x not in ("ACCEPT", "REJECT")]
            k = sum(x == "ACCEPT" for x in v)
            lo, hi = wilson(k, len(v))
            pilot = meta[pid]["pilot"][arm]
            agree = len(v) > 0 and all(x == pilot for x in v)
            rate = k / len(v) if v else float("nan")
            row[arm] = dict(n=len(v), accept=k, rate=rate, ci=[lo, hi], pilot=pilot,
                            stable=agree, invalid=len(other), votes=v)
            print("  " + arm.ljust(9) + " pilot=" + str(pilot).ljust(6) + " rerun=" + str(v) +
                  " accept=" + str(k) + "/" + str(len(v)) + " rate=%.2f" % rate +
                  " CI[%.2f,%.2f]" % (lo, hi) + " reproduced=" + str(agree))
        out[pid] = row

    print(NL + "== flip replication summary (descriptive; 4 patches is too few for inference) ==")
    for mode in ("strict", "majority"):
        rep = 0
        for pid in meta:
            if meta[pid]["role"] != "flipped": continue
            pilot = meta[pid]["pilot"]
            if mode == "strict":
                ok = all(out[pid][arm]["stable"] for arm in ARMS)
            else:
                ok = True
                for arm in ARMS:
                    v = out[pid][arm]["votes"]
                    if v:
                        ok = ok and collections.Counter(v).most_common(1)[0][0] == pilot[arm]
            rep += ok
        print("  " + mode + ": reproduced " + str(rep) + "/4")

    print(NL + "== controls: did a NEW flip appear under re-sampling? ==")
    new = 0
    for pid in meta:
        if meta[pid]["role"] != "control": continue
        majs = {}
        for arm in ARMS:
            v = out[pid][arm]["votes"]
            if v: majs[arm] = collections.Counter(v).most_common(1)[0][0]
        if len(set(majs.values())) > 1:
            new += 1
            print("  NEW FLIP " + pid + " " + str(majs))
    print("  " + str(new) + "/8 controls flipped across repeats")

    json.dump(out, open(a.out, "w"), indent=2)
    print(NL + "wrote " + a.out)

if __name__ == "__main__":
    main()
