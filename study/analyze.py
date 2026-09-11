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
import collections
import json
import re
import math
import os
import statistics
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from paperengine.stats import benjamini_hochberg, holm_bonferroni, norm_cdf  # noqa: E402


def t_cdf(x: float, df: float) -> float:
    """Student t distribution function, via the regularised incomplete beta."""
    from scipy.stats import t as _t
    return float(_t.cdf(x, df))

COLUMN_TOL = 12.0        # points; cells within this x-distance share a column
ROW_TOL = 6.0            # points; cells within this y-distance share a row
MIN_COLUMN_CELLS = 3


def _is_label(c: dict) -> bool:
    """A bare integer among decimals is a row label, not a result.

    "# of demos: 3, 5, 10, 20" and "epoch 10" sit in the first columns of many
    tables, and once the rows of a six-point table were parsed correctly the
    label 10 was the largest value in its row, so the bold 0.67 beside it was
    no longer extremal and the claim vanished. Found by the gold-set audit.
    """
    return c.get("dispersion") is None and "." not in (c.get("text") or "")


def _drop_labels(group: list) -> list:
    if any(not _is_label(c) for c in group):
        return [c for c in group if not _is_label(c)]
    return group


def _group(cells: list, key: str, tol: float) -> list:
    ordered = sorted(cells, key=lambda c: c[key])
    groups, cur = [], []
    for c in ordered:
        if cur and c[key] - cur[-1][key] > tol:
            groups.append(cur)
            cur = []
        cur.append(c)
    if cur:
        groups.append(cur)
    groups = [_drop_labels(g) for g in groups]
    return [g for g in groups if len(g) >= MIN_COLUMN_CELLS]


def _cut_positions(group: list, axis: str) -> list:
    """Where a group with several bold cells would be cut into blocks.

    Between each pair of successive bold cells the cut goes at the widest gap,
    which is where the rule between dataset blocks sits. Returns the
    coordinate of the first cell after each cut.
    """
    bold_idx = [i for i, c in enumerate(group) if c["bold"]]
    cuts = []
    for a, b in zip(bold_idx, bold_idx[1:]):
        gaps = [(group[i + 1][axis] - group[i][axis], i + 1) for i in range(a, b)]
        cuts.append(group[max(gaps)[1]][axis])
    return cuts


def _consensus_cuts(groups: list, axis: str, tol: float) -> list:
    """Cuts that most multi-bold groups agree on, or nothing.

    A column that carries one bold cell per dataset block -- MNIST, then
    F-MNIST, then STL-10, each with its own winner -- has several bold cells,
    and the orientation vote then flipped to rows, where every row has exactly
    one, and compared a method's MCE with its ECE. The gold-set audit found
    this in five of a hundred comparisons. Blocks are real when the columns
    agree on where they are; a column whose bold cells fall at irregular rows
    (a method that wins some tasks and not others) proposes cuts nobody else
    does, and is left whole.
    """
    proposals = [_cut_positions(sorted(g, key=lambda c: c[axis]), axis)
                 for g in groups if sum(1 for c in g if c["bold"]) >= 2]
    if len(proposals) < 2:
        return []
    need = max(2, (len(proposals) + 1) // 2)
    agreed = []
    for cuts in proposals:
        for y in cuts:
            if any(abs(y - a) <= tol for a in agreed):
                continue
            votes = sum(1 for other in proposals if any(abs(y - o) <= tol for o in other))
            if votes >= need:
                agreed.append(y)
    return sorted(agreed)


def _apply_cuts(group: list, axis: str, cuts: list, tol: float) -> list:
    if not cuts:
        return [group]
    ordered = sorted(group, key=lambda c: c[axis])
    pieces, cur = [], []
    for c in ordered:
        if cur and any(abs(c[axis] - y) <= tol for y in cuts) and c[axis] > cur[-1][axis]:
            pieces.append(cur)
            cur = []
        cur.append(c)
    if cur:
        pieces.append(cur)
    return [pc for pc in pieces if len(pc) >= 2]


def _columns(cells: list) -> list:
    """Group a table's cells into columns by horizontal position, split into
    dataset blocks where the columns agree on them."""
    groups = _group(cells, "x", COLUMN_TOL)
    cuts = _consensus_cuts(groups, "y", ROW_TOL)
    return [pc for g in groups for pc in _apply_cuts(g, "y", cuts, ROW_TOL)]


def _rows(cells: list) -> list:
    """Group a table's cells into rows by vertical position, split into
    column blocks where the rows agree on them."""
    groups = _group(cells, "y", ROW_TOL)
    cuts = _consensus_cuts(groups, "x", COLUMN_TOL)
    return [pc for g in groups for pc in _apply_cuts(g, "x", cuts, COLUMN_TOL)]


# A caption that announces first/second/third-best marking is describing a
# ranking, not a claim; every bold cell in such a table is one of several, and
# none of them is a winner against the rest. Such tables are discarded whole.
TOPK_CAPTION = re.compile(
    r"(?i)\b(?:top|best)[- ]?(?:three|3)\b|\bfirst\W.{0,30}\bsecond\W.{0,30}\bthird\b")


def orientation(cells: list) -> str:
    """Does bold mark the best in each column, or the best in each row?

    Both layouts are common and they invert the comparison. A table with methods
    in rows and benchmarks in columns bolds one winner per column; a table with
    methods in columns bolds one per row. Reading the second as though it were
    the first compares a method against itself on a different benchmark, which
    is not a claim anyone made. A sampled offline-RL table was being read that
    way before this check existed.

    The layout is recoverable from where the bold cells fall: whichever
    grouping yields more groups containing exactly one bold cell is the one the
    authors were marking.
    """
    def score(groups):
        return sum(1 for g in groups if sum(1 for c in g if c["bold"]) == 1)
    col_score = score(_columns(cells))
    row_score = score(_rows(cells))
    if col_score == 0 and row_score == 0:
        return "none"
    return "column" if col_score >= row_score else "row"


def _standard_error(dispersion: float, kind: str, n: Optional[int]) -> Optional[float]:
    """Convert a reported error bar into a standard error of the mean.

    A printed ``+/- 0.0`` is an error bar, not a missing one: a deterministic
    method has zero spread. It is kept as zero; the test is undefined only
    when both sides are zero.
    """
    if dispersion is None or dispersion < 0:
        return None
    if dispersion == 0:
        return 0.0
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
    if TOPK_CAPTION.search(table.get("caption") or ""):
        return out
    orient = orientation(table["cells"])
    if orient == "none":
        return out
    # Keep the table's extent so a sampled comparison can be cropped out of the
    # page for visual checking without re-parsing the PDF.
    ys = [c["y"] for c in table["cells"]]
    xs = [c["x"] for c in table["cells"]]
    bbox = {"y_min": min(ys), "y_max": max(ys), "x_min": min(xs), "x_max": max(xs)}
    groups = _columns(table["cells"]) if orient == "column" else _rows(table["cells"])
    for col in groups:
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
            "orientation": orient,
            "bbox": bbox,
            "n_in_column": len(col),
            # Carried so that later passes can ask what the table measures
            # without re-reading the PDF.
            "caption": (table.get("caption") or "")[:300],
            "header_text": table.get("header_text") or "",
            "n_runs_source": table.get("n_runs_source"),
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
    out = {"z": z, "p": 2 * (1 - norm_cdf(abs(z))), "se": se, "kind_used": kind}
    # A standard deviation from three runs is a rough estimate of the true one,
    # and the z test pretends it is exact. Welch's t with Satterthwaite degrees
    # of freedom is what a reader with the same numbers should compute. It is
    # only defined when the run count is printed; the z figure is kept as the
    # headline because it is the reading more favourable to the field.
    n = cmp["n_runs"]
    if n and n >= 2 and kind in ("std", "unknown"):
        df = se ** 4 / ((se_w ** 4 + se_r ** 4) / (n - 1))
        out["df"] = df
        out["p_t"] = 2 * (1 - t_cdf(abs(z), df))
    return out


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

    with_t = [c for c in testable if "p_t" in c["test"]]
    n_survive_t = sum(1 for c in with_t if c["test"]["p_t"] < 0.05)
    n_survive_z_same = sum(1 for c in with_t if c["test"]["p"] < 0.05)
    runs_stated = sorted(c["n_runs"] for c in testable if c.get("n_runs"))
    t_test = {
        "n_with_t": len(with_t),
        "survives_t": n_survive_t,
        "pct_fail_t": round(100 * (1 - n_survive_t / max(len(with_t), 1)), 1),
        "pct_fail_z_same_subset": round(100 * (1 - n_survive_z_same / max(len(with_t), 1)), 1),
        "median_stated_runs": statistics.median(runs_stated) if runs_stated else None,
        "pct_runs_le_3": round(100 * sum(1 for n in runs_stated if n <= 3) / max(len(runs_stated), 1), 1),
        "pct_runs_le_5": round(100 * sum(1 for n in runs_stated if n <= 5) / max(len(runs_stated), 1), 1),
        "runs_quartiles": ([runs_stated[len(runs_stated) // 4], runs_stated[len(runs_stated) // 2],
                            runs_stated[3 * len(runs_stated) // 4]] if runs_stated else None),
    }

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
        "welch_t": t_test,
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


# --------------------------------------------------------------------------
# uncertainty on our own numbers
# --------------------------------------------------------------------------

def cluster_bootstrap(comparisons: list, statistic, *, n_boot: int = 2000,
                      seed: int = 11, alpha: float = 0.05) -> dict:
    """Resample papers, not comparisons.

    A paper contributes many comparisons and they are not independent: one
    author's habits govern every table in it. Bootstrapping comparisons would
    treat 1,240 correlated observations as 1,240 independent ones and produce
    intervals several times too narrow.

    It would be a strange paper that demanded dispersions from everyone else
    and printed point estimates of its own, so every headline number carries one
    of these.

    One trap, hit on the first implementation: a paper drawn twice must become
    two distinct clusters before comparisons are regrouped by table, or its
    tables merge into one oversized multiplicity family and the Holm-corrected
    figure comes out wrong.
    """
    import random as _random

    by_paper: dict = {}
    for c in comparisons:
        by_paper.setdefault(c["paper"], []).append(c)
    papers = list(by_paper)
    if not papers:
        return {"point": None, "lo": None, "hi": None, "n_papers": 0}

    point = statistic(comparisons)
    rng = _random.Random(seed)
    draws = []
    for _ in range(n_boot):
        resampled = []
        for rep, p in enumerate(rng.choices(papers, k=len(papers))):
            for c in by_paper[p]:
                d = dict(c)
                d["paper"] = f"{p}#rep{rep}"
                if d.get("table") is not None:
                    d["table"] = f"{d['table']}#rep{rep}"
                resampled.append(d)
        try:
            draws.append(statistic(resampled))
        except (ZeroDivisionError, ValueError):
            continue
    draws.sort()
    if not draws:
        return {"point": point, "lo": None, "hi": None, "n_papers": len(papers)}
    lo = draws[max(0, int(alpha / 2 * len(draws)) - 1)]
    hi = draws[min(len(draws) - 1, int((1 - alpha / 2) * len(draws)))]
    return {"point": round(point, 4), "lo": round(lo, 4), "hi": round(hi, 4),
            "n_papers": len(papers), "n_boot": len(draws)}


def design_effect(comparisons: list, value) -> dict:
    """How much the clustering costs, expressed as an effective sample size."""
    by_paper: dict = {}
    for c in comparisons:
        v = value(c)
        if v is not None:
            by_paper.setdefault(c["paper"], []).append(float(v))
    groups = [g for g in by_paper.values() if g]
    n = sum(len(g) for g in groups)
    k = len(groups)
    if k < 2 or n <= k:
        return {"icc": None, "mean_cluster": None, "design_effect": None, "n_eff": n}
    grand = sum(sum(g) for g in groups) / n
    between = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups) / (k - 1)
    within = sum(sum((x - sum(g) / len(g)) ** 2 for x in g) for g in groups) / (n - k)
    m = n / k
    icc = (between - within) / (between + (m - 1) * within) if (between + (m - 1) * within) else 0.0
    icc = max(0.0, min(1.0, icc))
    deff = 1 + (m - 1) * icc
    return {"icc": round(icc, 4), "mean_cluster": round(m, 2),
            "design_effect": round(deff, 3), "n_eff": int(round(n / deff))}


# --------------------------------------------------------------------------
# uncertainty that is reported, but not per cell
# --------------------------------------------------------------------------

# A caption reading "standard errors are within 0.005m" reports uncertainty
# without attaching it to any cell. Counting such a table as printing nothing
# would overstate the headline; counting it as testable would be worse, since
# a bound is not an interval. It is its own category, found by looking at a
# table the extractor had called empty.
CAPTION_UNCERTAINTY = re.compile(
    r"(?i)\b(?:standard\s+(?:error|deviation)s?|confidence\s+intervals?|error\s+bars?|"
    r"variance|std\.?\s*dev|s\.?e\.?m)\b[^.]{0,120}?"
    r"(?:are|is|were|was|within|less\s+than|below|at\s+most|<|\u2264)"
)
CAPTION_RUNS = re.compile(
    r"(?i)\b(?:averaged?|mean|median)\b[^.]{0,80}?\b(?:over|across)\b[^.]{0,40}?\b\d{1,3}\b"
    r"[^.]{0,20}?(?:seeds?|runs?|trials?)"
)


def caption_reports_uncertainty(table: dict) -> bool:
    """Does the caption say something quantitative about spread, cell by cell or not?"""
    cap = table.get("caption") or ""
    return bool(CAPTION_UNCERTAINTY.search(cap) or CAPTION_RUNS.search(cap))


def extraction_funnel(records: list) -> dict:
    """Where tables and groups are lost between the PDF and the analysis.

    Reviewers asked what population the comparisons are drawn from, and the
    answer was not in the paper. Every discard here is a decision that could
    have gone another way, so each is counted rather than described.
    """
    n_tables = n_no_orientation = n_with_comparisons = 0
    n_groups = n_single_bold = 0
    n_caption_uncertainty = 0
    tables_no_cell_dispersion = 0

    for r in records:
        for t in r.get("tables", []):
            n_tables += 1
            cells = t["cells"]
            orient = orientation(cells)
            if orient == "none":
                n_no_orientation += 1
            groups = (_columns(cells) if orient == "column"
                      else _rows(cells) if orient == "row" else [])
            n_groups += len(groups)
            n_single_bold += sum(1 for g in groups
                                 if sum(1 for c in g if c["bold"]) == 1 and
                                 any(not c["bold"] for c in g))
            cmps = comparisons_from_table(t)
            if cmps:
                n_with_comparisons += 1
            if not any(c["dispersion"] is not None for c in cells):
                tables_no_cell_dispersion += 1
                if caption_reports_uncertainty(t):
                    n_caption_uncertainty += 1

    return {
        "tables_detected": n_tables,
        "tables_with_no_usable_orientation": n_no_orientation,
        "tables_yielding_at_least_one_comparison": n_with_comparisons,
        "candidate_groups": n_groups,
        "groups_with_exactly_one_bold_and_a_rival": n_single_bold,
        "pct_of_groups_usable": round(100 * n_single_bold / max(n_groups, 1), 1),
        "tables_with_no_cell_level_dispersion": tables_no_cell_dispersion,
        "of_those_whose_caption_reports_uncertainty": n_caption_uncertainty,
        "pct_of_empty_tables_with_caption_uncertainty": round(
            100 * n_caption_uncertainty / max(tables_no_cell_dispersion, 1), 1),
    }


def checklist_agreement(records: list) -> dict:
    """What NeurIPS authors answered, against what their tables contain.

    The checklist question is nearly the one this study asks, so disagreement is
    informative in both directions: it bounds the extractor, and it measures how
    often a declared yes corresponds to anything a reader can use.
    """
    cells: dict = collections.Counter()
    justif_figures = 0
    for r in records:
        ans = r.get("checklist_error_bars")
        if ans not in ("yes", "no", "na"):
            continue
        has = bool(r.get("reports_explicit_error_bar"))
        cells[(ans, has)] += 1
        if ans == "yes" and not has:
            j = (r.get("checklist_justification") or "").lower()
            if "figure" in j or "plot" in j or "curve" in j or "shaded" in j:
                justif_figures += 1
    yes_total = cells[("yes", True)] + cells[("yes", False)]
    return {
        "n_with_a_checklist_answer": sum(cells.values()),
        "answered_yes": yes_total,
        "answered_no": cells[("no", True)] + cells[("no", False)],
        "answered_na": cells[("na", True)] + cells[("na", False)],
        "yes_and_table_has_error_bar": cells[("yes", True)],
        "yes_but_no_table_error_bar": cells[("yes", False)],
        "no_but_table_has_error_bar": cells[("no", True)],
        "pct_of_yes_with_no_table_error_bar": round(
            100 * cells[("yes", False)] / max(yes_total, 1), 1),
        "of_those_justified_by_figures": justif_figures,
    }
