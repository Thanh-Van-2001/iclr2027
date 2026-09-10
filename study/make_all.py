"""Regenerate every derived result from the extracted corpus, in one command.

The paper claims its numbers are reproducible, so there had better be a single
entry point that produces all of them. This reads the two extraction files and
writes every analysis the paper cites, then the LaTeX macros. Nothing here
touches the network: re-running it is deterministic given the same JSONL.
"""

from __future__ import annotations

import collections
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import (analyse, checklist_agreement, cluster_bootstrap,  # noqa: E402
                     design_effect, extraction_funnel, orientation, _columns, _rows)
from sensitivity import (correlation_sensitivity, error_bar_meaning,  # noqa: E402
                         paper_level_crosstab, power_audit, run_count_scope)

YEARS = (2024, 2025)


def _load(year: int) -> list:
    with open(f"data/extracted_{year}.json", encoding="utf-8") as fh:
        return json.load(fh)


def _summary(analysis: dict, comparisons: list) -> dict:
    cs = comparisons
    t = [c for c in cs if c.get("test")]
    why = collections.Counter()
    for c in cs:
        if c.get("test"):
            why["testable"] += 1
        elif c["winner_dispersion"] is None and c["runner_dispersion"] is None:
            why["neither"] += 1
        elif c["winner_dispersion"] is None or c["runner_dispersion"] is None:
            why["one_side"] += 1
        elif not c["n_runs"]:
            why["no_n"] += 1
        else:
            why["other"] += 1
    n = len(cs)
    fail = [c for c in t if not c["survives_raw"]]
    failh = [c for c in t if not c["survives_holm"]]
    gf = [c["relative_gap"] for c in fail if c["relative_gap"] is not None]
    gs = [c["relative_gap"] for c in t if c["survives_raw"] and c["relative_gap"] is not None]
    corpus = analysis["corpus"]
    return {
        "papers": corpus["n_papers"],
        "pct_err": corpus["pct_reporting_explicit_error_bar"],
        "pct_n": corpus["pct_stating_number_of_runs"],
        "median_runs": corpus["median_runs_when_stated"],
        "comparisons": n,
        "pct_neither": round(100 * why["neither"] / n, 1),
        "pct_no_n": round(100 * why["no_n"] / n, 1),
        "pct_one": round(100 * why["one_side"] / n, 1),
        "pct_testable": round(100 * why["testable"] / n, 1),
        "n_testable": len(t),
        "papers_testable": len(set(c["paper"] for c in t)),
        "pct_fail": round(100 * len(fail) / max(len(t), 1), 1),
        "pct_fail_holm": round(100 * len(failh) / max(len(t), 1), 1),
        "gap_fail": round(statistics.median(gf) * 100, 2) if gf else None,
        "gap_pass": round(statistics.median(gs) * 100, 2) if gs else None,
        "median_comparisons_per_table": analysis["comparisons"]["median_comparisons_per_table"],
    }


def _bootstrap(comparisons: list) -> dict:
    t = [c for c in comparisons if c.get("test")]

    def pct_neither(rows):
        return 100 * sum(1 for c in rows
                         if c["winner_dispersion"] is None and c["runner_dispersion"] is None) / len(rows)

    def pct_testable(rows):
        return 100 * sum(1 for c in rows if c.get("test")) / len(rows)

    def pct_fail(rows):
        tt = [c for c in rows if c.get("test")]
        return 100 * sum(1 for c in tt if not c["survives_raw"]) / len(tt)

    def pct_fail_holm(rows):
        tt = [c for c in rows if c.get("test")]
        return 100 * sum(1 for c in tt if not c["survives_holm"]) / len(tt)

    def holm_delta(rows):
        tt = [c for c in rows if c.get("test")]
        return 100 * (sum(1 for c in tt if not c["survives_holm"])
                      - sum(1 for c in tt if not c["survives_raw"])) / len(tt)

    return {
        "pct_neither": cluster_bootstrap(comparisons, pct_neither),
        "pct_testable": cluster_bootstrap(comparisons, pct_testable),
        "pct_fail": cluster_bootstrap(t, pct_fail),
        "pct_fail_holm": cluster_bootstrap(t, pct_fail_holm),
        "holm_delta": cluster_bootstrap(t, holm_delta),
        "deff": design_effect(t, lambda c: 0.0 if c["survives_raw"] else 1.0),
    }


def bold_semantics(records: list) -> dict:
    stats = collections.Counter()
    for r in records:
        for t in r.get("tables", []):
            cells = t["cells"]
            o = orientation(cells)
            if o == "none":
                continue
            for g in (_columns(cells) if o == "column" else _rows(cells)):
                bold = [c for c in g if c["bold"]]
                plain = [c for c in g if not c["bold"]]
                if len(bold) != 1 or not plain:
                    stats["no_single_bold_with_rival"] += 1
                    continue
                vals = [c["mean"] for c in g]
                w = bold[0]["mean"]
                if w == max(vals) or w == min(vals):
                    stats["extremal"] += 1
                else:
                    stats["not_extremal"] += 1
    usable = stats["extremal"] + stats["not_extremal"]
    return {"n_single_bold_groups": usable,
            "extremal": stats["extremal"], "not_extremal": stats["not_extremal"],
            "pct_not_extremal": round(100 * stats["not_extremal"] / max(usable, 1), 1),
            "groups_without_single_bold_and_rival": stats["no_single_bold_with_rival"]}


def main() -> int:
    os.makedirs("out", exist_ok=True)
    summaries, boots = {}, {}
    for year in YEARS:
        records = _load(year)
        analysis = analyse(records)
        with open(f"out/analysis_{year}.json", "w", encoding="utf-8") as fh:
            json.dump(analysis, fh, indent=1)
        cs = analysis["_comparisons"]
        summaries[str(year)] = _summary(analysis, cs)
        boots[str(year)] = _bootstrap(cs)
        print(f"{year}: {summaries[str(year)]['papers']} papers, "
              f"{summaries[str(year)]['comparisons']} comparisons, "
              f"{summaries[str(year)]['pct_neither']}% neither, "
              f"{summaries[str(year)]['pct_fail']}% fail")

    with open("out/both_years.json", "w", encoding="utf-8") as fh:
        json.dump(summaries, fh, indent=1)
    with open("out/bootstrap_ci.json", "w", encoding="utf-8") as fh:
        json.dump(boots, fh, indent=1)

    # Everything below is reported for the 2025 sample, the larger of the two.
    records = _load(2025)
    with open("out/analysis_2025.json", encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]

    extras = {
        "run_count_scope": run_count_scope(cs, records),
        "error_bar_meaning": error_bar_meaning(cs),
        "paper_level_crosstab": paper_level_crosstab(records),
    }
    with open("out/sensitivity_2025.json", "w", encoding="utf-8") as fh:
        json.dump(extras, fh, indent=1)

    from binomial_check import analyse as binom_analyse
    from benchmark_resolution import identify as _bench_identify  # noqa: F401
    for name, value in (("correlation_sensitivity", correlation_sensitivity(cs)),
                        ("binomial_check", binom_analyse(cs)),
                        ("power_audit", power_audit(cs)),
                        ("funnel", extraction_funnel(records)),
                        ("checklist", checklist_agreement(records)),
                        ("bold_semantics", bold_semantics(records))):
        with open(f"out/{name}.json", "w", encoding="utf-8") as fh:
            json.dump(value, fh, indent=1)
        print(f"  wrote out/{name}.json")

    print("\nnow run: python study/make_numbers.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
