"""A second notion of checkability, for the metrics that have one.

Our definition of testable assumes the uncertainty that matters is variance
across training runs, which needs a dispersion and a run count. A reviewer
pointed out that this is one model and not the only one: for an accuracy on a
fixed test set, the dominant uncertainty is over test examples, and a binomial
interval is computable from the accuracy and the size of the test set alone. No
error bar is required.

That route is real, and it changes who is at fault when a comparison cannot be
checked: not the missing error bar, but the missing test-set size. So we ask the
question the other way round. Given the gaps papers actually report between two
accuracy-like values, how large would the shared test set have to be for those
gaps to be distinguishable from zero?

The answer is a property of the reported numbers, needs nothing the papers did
not print, and can be compared against the sizes of the benchmarks in use.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from paperengine.stats import norm_ppf  # noqa: E402

# Benchmarks in common use, for the comparison at the end. Test-set sizes as
# published; these are reference points, not measurements of our corpus.
REFERENCE_BENCHMARKS = {
    "MMLU (test)": 14042,
    "GSM8K (test)": 1319,
    "HumanEval": 164,
    "ImageNet (val)": 50000,
    "SWE-bench Verified": 500,
    "MATH-500": 500,
}


# Both values must lie in this range for the pair to be treated as rates. The
# lower bound is not cosmetic: it is where a metric is almost certainly an
# accuracy rather than a loss, a runtime or a count, and the paper reports the
# figures from this filter. Widening it to (0, 100] moves the median requirement
# but not the conclusion; the numbers for both appear in the run record.
RATE_LOW, RATE_HIGH = 40.0, 100.0


def looks_like_a_percentage(value: float) -> bool:
    return RATE_LOW <= value <= RATE_HIGH


def required_test_set_size(p1: float, p2: float, *, alpha: float = 0.05,
                           power: float = 0.8) -> float:
    """Items needed for a gap between two proportions to be detectable.

    Both values are treated as independent binomials on the same test set. That
    is conservative: two systems scored on the same items are positively
    correlated, so a paired test needs fewer items than this. Reporting the
    conservative figure means the real requirement is at most what we state.
    """
    p1, p2 = p1 / 100.0, p2 / 100.0
    if not (0 < p1 < 1 and 0 < p2 < 1):
        return math.inf
    d = abs(p1 - p2)
    if d <= 0:
        return math.inf
    z_a, z_b = norm_ppf(1 - alpha / 2), norm_ppf(power)
    var = p1 * (1 - p1) + p2 * (1 - p2)
    return ((z_a + z_b) ** 2) * var / (d ** 2)


# A value in [40, 100] is usually an accuracy, but F1, mIoU, BLEU and PSNR live
# there too and are not proportions over test items. A caption or header that
# names an accuracy-like metric is the stricter filter a reviewer asked for.
ACCURACY_METRIC = re.compile(
    r"(?i)\bacc(?:uracy|\.)?\b|exact[ -]match|\bEM\b|pass@\d|top-?[15]\b|"
    r"success rate|win rate|solve[d]? rate|\bcorrect\b|error rate")


def names_accuracy_metric(c: dict) -> bool:
    return bool(ACCURACY_METRIC.search((c.get("caption") or "") + " " + (c.get("header_text") or "")))


def analyse(comparisons: list, lo: float = RATE_LOW, hi: float = RATE_HIGH,
            metric_named: bool = False) -> dict:
    rows = []
    for c in comparisons:
        w, r = c["winner"], c["runner_up"]
        if not (lo <= w <= hi and lo <= r <= hi):
            continue
        if metric_named and not names_accuracy_metric(c):
            continue
        if w == r:
            continue
        n = required_test_set_size(w, r)
        if math.isfinite(n):
            rows.append({"gap": abs(w - r), "n_required": n, "paper": c["paper"]})
    if not rows:
        return {"n": 0}

    needed = sorted(r["n_required"] for r in rows)
    q = lambda f: needed[min(len(needed) - 1, int(f * len(needed)))]  # noqa: E731

    out = {
        "n_comparisons": len(rows),
        "filter": f"both values in [{lo:.0f}, {hi:.0f}]" + (", accuracy-like metric named" if metric_named else ""),
        "n_papers": len(set(r["paper"] for r in rows)),
        "median_gap_points": round(statistics.median(r["gap"] for r in rows), 2),
        "required_test_set_size": {
            "q25": int(q(0.25)), "median": int(q(0.50)),
            "q75": int(q(0.75)), "q90": int(q(0.90)),
        },
        "share_needing_more_than": {},
    }
    for label, size in sorted(REFERENCE_BENCHMARKS.items(), key=lambda kv: kv[1]):
        share = sum(1 for r in rows if r["n_required"] > size) / len(rows)
        out["share_needing_more_than"][f"{label} ({size})"] = round(100 * share, 1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="How large a test set would the reported gaps need?")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--out", default="out/binomial_check.json")
    args = ap.parse_args(argv)

    with open(args.analysis, encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]
    res = analyse(cs)
    res["wide"] = analyse(cs, lo=1e-9, hi=100.0)
    res["metric_named"] = analyse(cs, metric_named=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    print(f"rate-like comparisons: {res['n_comparisons']} from {res['n_papers']} papers "
          f"({res['filter']})")
    print(f"median reported gap: {res['median_gap_points']} points")
    r = res["required_test_set_size"]
    print(f"test-set size needed to detect it, at 80% power:")
    print(f"  q25 {r['q25']}   median {r['median']}   q75 {r['q75']}   q90 {r['q90']}")
    print("\nshare of comparisons needing a test set larger than:")
    for k, v in res["share_needing_more_than"].items():
        print(f"  {k:<28} {v}%")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
