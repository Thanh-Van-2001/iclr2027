"""Is the reported gap larger than the benchmark can resolve?

The previous section asked how large a test set the reported gaps would need.
This asks the sharper version: for the comparisons where we can identify which
benchmark was used, is the gap larger than that benchmark's own resolution?

A benchmark of $n$ items cannot distinguish two systems whose accuracies differ
by less than roughly the width of a binomial interval at that $n$. That number
is a property of the benchmark, fixed and public, and independent of anything
the paper prints about uncertainty. Where a table names its benchmark and
reports a gap, the comparison can be checked against it whether or not the
authors printed an error bar.

Benchmark sizes are the published evaluation splits. They are entered by hand
from the dataset papers and release notes, and a wrong size would move one row
rather than the conclusion; the table is released so the numbers can be checked.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import load_records  # noqa: E402
from paperengine.stats import norm_ppf  # noqa: E402

# name -> (regex, test-set size). Sizes are the standard evaluation split.
BENCHMARKS = {
    "MMLU":              (r"\bMMLU\b(?!-)", 14042),
    "MMLU-Pro":          (r"\bMMLU[- ]Pro\b", 12032),
    "GSM8K":             (r"\bGSM-?8K\b", 1319),
    "HumanEval":         (r"\bHumanEval\b", 164),
    "MBPP":              (r"\bMBPP\b", 500),
    "HellaSwag":         (r"\bHellaSwag\b", 10042),
    "ARC-Challenge":     (r"\bARC[- ]?(?:Challenge|c)\b", 1172),
    "ARC-Easy":          (r"\bARC[- ]?(?:Easy|e)\b", 2376),
    "PIQA":              (r"\bPIQA\b", 1838),
    "WinoGrande":        (r"\bWinoGrande\b", 1267),
    "BoolQ":             (r"\bBoolQ\b", 3270),
    "OpenBookQA":        (r"\bOpenBookQA\b|\bOBQA\b", 500),
    "TruthfulQA":        (r"\bTruthfulQA\b", 817),
    "MATH-500":          (r"\bMATH-?500\b", 500),
    "MATH":              (r"\bMATH\b(?!-)", 5000),
    "GPQA Diamond":      (r"\bGPQA\b", 198),
    "AIME":              (r"\bAIME\b", 30),
    "SWE-bench Verified": (r"\bSWE-?bench\b", 500),
    "ImageNet":          (r"\bImageNet(?:-1[Kk])?\b", 50000),
    "CIFAR-10":          (r"\bCIFAR-?10\b(?!0)", 10000),
    "CIFAR-100":         (r"\bCIFAR-?100\b", 10000),
    "SST-2":             (r"\bSST-?2\b", 872),
    "MNLI":              (r"\bMNLI\b", 9815),
    "QNLI":              (r"\bQNLI\b", 5463),
    "SQuAD":             (r"\bSQuAD\b", 10570),
    "DROP":              (r"\bDROP\b", 9536),
    "CoQA":              (r"\bCoQA\b", 7983),
}
_COMPILED = {k: (re.compile(v[0], re.I), v[1]) for k, v in BENCHMARKS.items()}


def identify(text: str) -> list:
    """Which benchmarks this caption names, if any."""
    return [(name, size) for name, (pat, size) in _COMPILED.items() if pat.search(text or "")]


def resolvable_gap(n: int, p: float = 0.5, *, alpha: float = 0.05, power: float = 0.8) -> float:
    """Smallest accuracy difference a benchmark of n items can resolve, in points.

    Evaluated at the accuracy the comparison actually reports rather than at the
    worst case, and treating the two systems as independent, which is
    conservative: scored on the same items they are correlated and the true
    resolution is finer than this.
    """
    z = norm_ppf(1 - alpha / 2) + norm_ppf(power)
    var = 2 * p * (1 - p)
    return 100.0 * z * math.sqrt(var / n)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare reported gaps against benchmark resolution.")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--extracted", default="data/extracted_2025.jsonl")
    ap.add_argument("--out", default="out/benchmark_resolution.json")
    args = ap.parse_args(argv)

    with open(args.analysis, encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]
    recs = load_records(args.extracted)

    captions = {}
    for r in recs:
        for t in r.get("tables", []):
            captions[(r["id"], t.get("number"), t.get("page"))] = t.get("caption") or ""

    rows = []
    for c in cs:
        cap = captions.get((c["paper"], c["table"], c["page"]), "")
        hits = identify(cap)
        if len(hits) != 1:
            continue                      # ambiguous or unnamed: skip rather than guess
        name, size = hits[0]
        w, r_ = c["winner"], c["runner_up"]
        if not (0 < w <= 100 and 0 < r_ <= 100):
            continue
        p = (w + r_) / 200.0
        if not 0.02 < p < 0.98:
            continue
        gap = abs(w - r_)
        res = resolvable_gap(size, p)
        rows.append({"benchmark": name, "size": size, "gap": gap, "resolution": res,
                     "below": gap < res, "paper": c["paper"]})

    if not rows:
        print("no comparisons could be matched to a named benchmark")
        return 1

    below = [r for r in rows if r["below"]]
    by_bench = {}
    for r in rows:
        d = by_bench.setdefault(r["benchmark"], {"n": 0, "below": 0, "size": r["size"]})
        d["n"] += 1
        d["below"] += r["below"]
    for d in by_bench.values():
        d["pct_below"] = round(100 * d["below"] / d["n"], 1)

    # The independence assumption makes the resolution coarser than reality, so
    # the headline is an upper bound. The whole range is emitted here rather
    # than computed separately, so the released script produces every number the
    # paper cites.
    corr = {}
    for rho in (0.0, 0.3, 0.5, 0.7, 0.9):
        f = math.sqrt(1.0 - rho)
        corr[str(rho)] = round(
            100 * sum(1 for r in rows if r["gap"] < r["resolution"] * f) / len(rows), 1)

    res = {
        "n_comparisons": len(rows),
        "correlation_sensitivity": corr,
        "n_papers": len(set(r["paper"] for r in rows)),
        "n_below_resolution": len(below),
        "pct_below_resolution": round(100 * len(below) / len(rows), 1),
        "median_gap": round(statistics.median(r["gap"] for r in rows), 2),
        "median_resolution": round(statistics.median(r["resolution"] for r in rows), 2),
        "by_benchmark": dict(sorted(by_bench.items(), key=lambda kv: -kv[1]["n"])),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    print(f"comparisons matched to exactly one named benchmark: {res['n_comparisons']} "
          f"from {res['n_papers']} papers")
    print(f"median reported gap {res['median_gap']} points against a median resolution of "
          f"{res['median_resolution']} points")
    print(f"below the benchmark's own resolution: {res['n_below_resolution']} "
          f"({res['pct_below_resolution']}%)")
    print("\nby benchmark:")
    for name, d in list(res["by_benchmark"].items())[:12]:
        print(f"  {name:<18} n={d['n']:>5}  size={d['size']:>6}  below resolution {d['pct_below']}%")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
