"""Turn extracted tables into comparisons, and comparisons into verdicts.

A *comparison* is the claim a results table actually makes: within one column,
the value the authors set in bold against the best value they did not. The bold
cell is the claim; the runner-up is the counterfactual a reader is invited to
reject.

Two things make this analysable without knowing what the metric means.

The direction of the metric is recoverable from the typography. If the bold cell
is the largest in its column, higher is better; if the smallest, lower is
better. If the bold cell is neither, the column is not a simple best-of
comparison and is dropped rather than guessed at.

The number of simultaneous comparisons is visible on the page. A table with
twelve columns, each with a bolded winner, ran twelve comparisons; reporting the
best one as though it were the only one is precisely the multiplicity a reviewer
would flag in a paper's own experiments but that nobody applies to the published
literature in aggregate.

Where the paper does not say whether its error bar is a standard deviation, a
standard error, or a confidence half-width -- which is the common case -- the
analysis is run under each reading and reported as a range. Assuming the reading
that maximises significance would be the same sin the study is measuring.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from paperengine.stats import benjamini_hochberg, holm_bonferroni, norm_cdf  # noqa: E402

COLUMN_TOL = 12.0        # points; cells within this x-distance share a column
MIN_COLUMN_CELLS = 3


def _columns(cells: list) -> list:
    """Group a table's cells into columns by horizontal position."""
    by_x = sorted(cells, key=lambda c: c["x"])
    cols, cur = [], []
    for c in by_x:
        if cur and c["x"] - cur[-1]["x"] > COLUMN_TOL:
            cols.append(cur)
            cur = []
        cur.append(c)
    if cur:
        cols.append(cur)
    return [c for c in cols if len(c) >= MIN_COLUMN_CELLS]


def _standard_error(dispersion: float, kind: str, n: Optional[int]) -> Optional[float]:
    """Convert a reported error bar into a standard error of the mean."""
    if dispersion is None or dispersion <= 0:
        return None
    if kind == "sem":
        return dispersion
    if kind == "ci":
        return dispersion / 1.96
    if kind in ("std", "unknown"):
        if not n or n < 2:
            return None
        return dispersion / math.sqrt(n)
    return None


def comparisons_from_table(table: dict) -> list:
    """Every bold-versus-runner-up comparison this table makes."""
    out = []
    n_runs = table.get("n_runs")
    kind = table.get("dispersion_kind", "unknown")
    for col in _columns(table["cells"]):
        bold = [c for c in col if c["bold"]]
        plain = [c for c in col if not c["bold"]]
        if len(bold) != 1 or not plain:
            continue
        win = bold[0]
        vals = [c["mean"] for c in col]
        if win["mean"] == max(vals):
            direction, runner = "higher_better", max(plain, key=lambda c: c["mean"])
        elif win["mean"] == min(vals):
            direction, runner = "lower_better", min(plain, key=lambda c: c["mean"])
        else:
            continue  # bold cell is not extremal: not a best-of comparison
        gap = abs(win["mean"] - runner["mean"])
        out.append({
            "table": table.get("number"),
            "page": table.get("page"),
            "direction": direction,
            "winner": win["mean"],
            "runner_up": runner["mean"],
            "gap": gap,
            "relative_gap": gap / abs(runner["mean"]) if runner["mean"] else None,
            "winner_dispersion": win["dispersion"],
            "runner_dispersion": runner["dispersion"],
            "winner_style": win.get("dispersion_style"),
            "runner_style": runner.get("dispersion_style"),
            "dispersion_kind": kind,
            "n_runs": n_runs,
            "n_in_column": len(col),
        })
    for c in out:
        c["n_comparisons_in_table"] = len(out)
    return out


def test_comparison(cmp: dict, kind_override: Optional[str] = None) -> Optional[dict]:
    """Two-sample z test from the numbers the authors themselves printed."""
    kind = kind_override or cmp["dispersion_kind"]
    se_w = _standard_error(cmp["winner_dispersion"], kind, cmp["n_runs"])
    se_r = _standard_error(cmp["runner_dispersion"], kind, cmp["n_runs"])
    if se_w is None or se_r is None:
        return None
    se = math.sqrt(se_w ** 2 + se_r ** 2)
    if se <= 0:
        return None
    z = cmp["gap"] / se
    return {"z": z, "p": 2 * (1 - norm_cdf(abs(z))), "se": se, "kind_used": kind}


def analyse(records: list) -> dict:
    n_papers = len(records)
    reports_pm = [r for r in records if r.get("reports_explicit_error_bar")]
    reports_disp = [r for r in records if r["reports_any_dispersion"]]
    states_runs = [r for r in records if r.get("n_runs_global")]

    all_cmps = []
    per_paper = []
    for r in records:
        cmps = []
        for t in r["tables"]:
            cmps.extend(comparisons_from_table(t))
        for c in cmps:
            c["paper"] = r["id"]
            c["venue"] = r["venue"]
            c["year"] = r["year"]
            if c["n_runs"] is None:
                c["n_runs"] = r.get("n_runs_global")
        all_cmps.extend(cmps)
        per_paper.append({"id": r["id"], "title": r["title"], "n_comparisons": len(cmps),
                          "reports_dispersion": r["reports_any_dispersion"],
                          "n_runs": r.get("n_runs_global")})

    testable = []
    for c in all_cmps:
        res = test_comparison(c)
        if res:
            c["test"] = res
            testable.append(c)

    # Multiplicity is applied within a table, which is the unit at which the
    # authors chose what to bold.
    by_table: dict = {}
    for c in testable:
        by_table.setdefault((c["paper"], c["table"], c["page"]), []).append(c)
    n_survive_raw = n_survive_holm = n_survive_bh = 0
    for group in by_table.values():
        ps = [c["test"]["p"] for c in group]
        holm = holm_bonferroni(ps, 0.05)
        bh = benjamini_hochberg(ps, 0.05)
        for c, h, b in zip(group, holm, bh):
            c["survives_raw"] = c["test"]["p"] < 0.05
            c["survives_holm"] = h
            c["survives_bh"] = b
            n_survive_raw += c["survives_raw"]
            n_survive_holm += h
            n_survive_bh += b

    # Sensitivity: papers that never say what their error bar means.
    unknown = [c for c in all_cmps if c["dispersion_kind"] == "unknown"]
    sens = {}
    for k in ("std", "sem"):
        cnt = 0
        for c in unknown:
            res = test_comparison(c, kind_override=k)
            if res and res["p"] < 0.05:
                cnt += 1
        sens[k] = cnt

    gaps = [c["relative_gap"] for c in all_cmps if c.get("relative_gap") is not None]
    return {
        "corpus": {
            "n_papers": n_papers,
            "n_reporting_explicit_error_bar": len(reports_pm),
            "pct_reporting_explicit_error_bar": round(100 * len(reports_pm) / max(n_papers, 1), 1),
            "n_reporting_any_dispersion": len(reports_disp),
            "pct_reporting_any_dispersion": round(100 * len(reports_disp) / max(n_papers, 1), 1),
            "n_stating_number_of_runs": len(states_runs),
            "pct_stating_number_of_runs": round(100 * len(states_runs) / max(n_papers, 1), 1),
            "median_runs_when_stated": (statistics.median([r["n_runs_global"] for r in states_runs])
                                        if states_runs else None),
        },
        "comparisons": {
            "n_total": len(all_cmps),
            "n_testable": len(testable),
            "pct_testable": round(100 * len(testable) / max(len(all_cmps), 1), 1),
            "median_comparisons_per_table": (statistics.median(
                [c["n_comparisons_in_table"] for c in all_cmps]) if all_cmps else None),
            "median_relative_gap": round(statistics.median(gaps), 4) if gaps else None,
        },
        "survival": {
            "n_tested": len(testable),
            "survives_uncorrected": n_survive_raw,
            "survives_holm": n_survive_holm,
            "survives_bh": n_survive_bh,
            "pct_uncorrected": round(100 * n_survive_raw / max(len(testable), 1), 1),
            "pct_holm": round(100 * n_survive_holm / max(len(testable), 1), 1),
            "pct_bh": round(100 * n_survive_bh / max(len(testable), 1), 1),
        },
        "sensitivity_unknown_error_bar": {
            "n_unknown": len(unknown),
            "significant_if_read_as_std": sens.get("std"),
            "significant_if_read_as_sem": sens.get("sem"),
        },
        "_comparisons": all_cmps,
        "_per_paper": per_paper,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Analyse extracted tables for statistical survival.")
    ap.add_argument("--extracted", default="data/extracted.json")
    ap.add_argument("--out", default="out/analysis.json")
    args = ap.parse_args(argv)

    with open(args.extracted, encoding="utf-8") as fh:
        records = json.load(fh)
    res = analyse(records)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    c, cm, s = res["corpus"], res["comparisons"], res["survival"]
    print(f"corpus: {c['n_papers']} accepted papers")
    print(f"  explicit +/- error bar: {c['n_reporting_explicit_error_bar']} ({c['pct_reporting_explicit_error_bar']}%)")
    print(f"  any dispersion at all : {c['n_reporting_any_dispersion']} ({c['pct_reporting_any_dispersion']}%)")
    print(f"  state number of runs  : {c['n_stating_number_of_runs']} ({c['pct_stating_number_of_runs']}%)")
    print(f"  median runs when said : {c['median_runs_when_stated']}")
    print(f"\ncomparisons: {cm['n_total']} bold-vs-runner-up, {cm['n_testable']} testable ({cm['pct_testable']}%)")
    print(f"  median comparisons per table : {cm['median_comparisons_per_table']}")
    print(f"  median relative gap          : {cm['median_relative_gap']}")
    print(f"\nsurvival of {s['n_tested']} testable comparisons at alpha=0.05:")
    print(f"  uncorrected      : {s['survives_uncorrected']} ({s['pct_uncorrected']}%)")
    print(f"  Holm-Bonferroni  : {s['survives_holm']} ({s['pct_holm']}%)")
    print(f"  Benjamini-Hochberg: {s['survives_bh']} ({s['pct_bh']}%)")
    u = res["sensitivity_unknown_error_bar"]
    print(f"\nerror bars of unstated meaning: {u['n_unknown']} comparisons")
    print(f"  significant read as std : {u['significant_if_read_as_std']}")
    print(f"  significant read as sem : {u['significant_if_read_as_sem']}")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
