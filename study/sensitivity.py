"""How much of the result is a definitional choice?

Two decisions in the pipeline are not forced by the data, and a reviewer is
entitled to ask what happens under the other reading of each. Reporting a single
number for a quantity that depends on an arbitrary convention is the failure
this paper is about, so both are reported as ranges.

**Where a run count may come from.** The strict reading counts a comparison as
testable only when the table's own caption states how many runs produced the
means. The permissive reading lets a count stated anywhere in the paper apply to
every table in it. The strict reading is defensible -- a number of seeds quoted
in Section 3 need not govern Table 7 -- but it is a choice, and it controls 58%
of all error-barred comparisons.

**What an unlabelled error bar means.** Most papers that print ``82.4 +/- 0.3``
never say whether ``0.3`` is a standard deviation or a standard error. The two
readings differ by a factor of sqrt(n), which at the run counts these papers
report is between 1.7 and 3.2 -- easily enough to move a comparison across the
threshold. Picking the reading that produces the more striking headline would be
indefensible, so both are computed.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import load_records, test_comparison  # noqa: E402
from paperengine.stats import benjamini_hochberg, holm_bonferroni  # noqa: E402


def _survival(comparisons: list, kind_override=None) -> dict:
    """Failure rates over whatever set of comparisons is passed in."""
    tested = []
    for c in comparisons:
        res = test_comparison(c, kind_override=kind_override)
        if res:
            d = dict(c)
            d["_p"] = res["p"]
            tested.append(d)
    if not tested:
        return {"n": 0}

    by_table: dict = {}
    for c in tested:
        by_table.setdefault((c["paper"], c["table"], c["page"]), []).append(c)
    fail_raw = fail_holm = 0
    for group in by_table.values():
        ps = [c["_p"] for c in group]
        holm = holm_bonferroni(ps, 0.05)
        for c, h in zip(group, holm):
            fail_raw += c["_p"] >= 0.05
            fail_holm += not h
    n = len(tested)
    return {"n": n,
            "pct_fail": round(100 * fail_raw / n, 1),
            "pct_fail_holm": round(100 * fail_holm / n, 1),
            "n_papers": len(set(c["paper"] for c in tested))}


def run_count_scope(comparisons: list, papers: list) -> dict:
    """Strict (caption only) against permissive (anywhere in the paper)."""
    doc_n = {p["id"]: p.get("n_runs_global") for p in papers}

    # The analysis already falls back to a document-level count, so the
    # "permissive" reading is what the paper reports and the strict one has to
    # be reconstructed by removing counts that did not come from the caption.
    strict = []
    for c in comparisons:
        d = dict(c)
        if d.get("n_runs_source") != "caption":
            d["n_runs"] = None
        strict.append(d)
    permissive = []
    borrowed = 0
    for c in comparisons:
        d = dict(c)
        if not d.get("n_runs"):
            n = doc_n.get(d["paper"])
            if n:
                d["n_runs"] = n
                borrowed += 1
        permissive.append(d)

    total = len(comparisons)
    strict_testable = sum(1 for c in strict if test_comparison(c))
    perm_testable = sum(1 for c in permissive if test_comparison(c))
    return {
        "n_comparisons": total,
        "strict": {"pct_testable": round(100 * strict_testable / total, 1),
                   **_survival(strict)},
        "permissive": {"pct_testable": round(100 * perm_testable / total, 1),
                       "n_borrowed_a_document_level_count": borrowed,
                       **_survival(permissive)},
    }


def error_bar_meaning(comparisons: list) -> dict:
    """The unlabelled error bars, read both ways.

    Both readings must be evaluated on the *same* comparisons or the contrast is
    meaningless: reading a bar as a standard deviation needs a run count and
    reading it as a standard error does not, so a naive split compares 627
    comparisons against 1,836. Only those with a run count are used here.
    """
    # Both subsets are testable comparisons, so that their sizes add up to the
    # testable population; the earlier count included one-sided bars and did
    # not reconcile.
    unknown = [c for c in comparisons
               if c.get("dispersion_kind") == "unknown" and c.get("n_runs") and c.get("test")]
    labelled = [c for c in comparisons
                if c.get("dispersion_kind") in ("std", "sem", "ci") and c.get("test")]
    return {
        "n_unknown": len(unknown),
        "n_labelled": len(labelled),
        "pct_of_error_barred_that_are_unlabelled": round(
            100 * len(unknown) / max(len(unknown) + len(labelled), 1), 1),
        "read_as_std": _survival(unknown, kind_override="std"),
        "read_as_sem": _survival(unknown, kind_override="sem"),
        "labelled_only": _survival(labelled),
    }


def paper_level_crosstab(papers: list) -> dict:
    """Do the papers that print error bars also state run counts?

    A reviewer noticed that these two paper-level rates are nearly equal while
    most error-barred *comparisons* lack a run count, and pointed out that
    either the two sets are near-disjoint -- which would itself be worth
    reporting -- or the table-to-count attribution is failing.
    """
    cells = collections.Counter()
    for p in papers:
        eb = bool(p.get("reports_explicit_error_bar"))
        nr = bool(p.get("n_runs_global"))
        cells[(eb, nr)] += 1
    n = len(papers)
    both = cells[(True, True)]
    eb_only = cells[(True, False)]
    nr_only = cells[(False, True)]
    neither = cells[(False, False)]
    with_eb = both + eb_only
    return {
        "n_papers": n,
        "error_bar_and_run_count": both,
        "error_bar_only": eb_only,
        "run_count_only": nr_only,
        "neither": neither,
        "pct_of_error_bar_papers_that_also_state_runs": round(
            100 * both / max(with_eb, 1), 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sensitivity of the headline to two conventions.")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--extracted", default="data/extracted_2025.jsonl")
    ap.add_argument("--out", default="out/sensitivity_2025.json")
    args = ap.parse_args(argv)

    with open(args.analysis, encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]
    papers = load_records(args.extracted)

    res = {
        "run_count_scope": run_count_scope(cs, papers),
        "error_bar_meaning": error_bar_meaning(cs),
        "paper_level_crosstab": paper_level_crosstab(papers),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)

    r = res["run_count_scope"]
    print("Where may a run count come from?")
    print(f"  strict (caption only) : {r['strict']['pct_testable']}% testable, "
          f"{r['strict'].get('pct_fail')}% fail, {r['strict'].get('pct_fail_holm')}% fail under Holm")
    print(f"  permissive (anywhere) : {r['permissive']['pct_testable']}% testable, "
          f"{r['permissive'].get('pct_fail')}% fail, {r['permissive'].get('pct_fail_holm')}% fail under Holm")
    print(f"  comparisons that borrowed a document-level count: "
          f"{r['permissive']['n_borrowed_a_document_level_count']}")

    e = res["error_bar_meaning"]
    print(f"\nUnlabelled error bars: {e['n_unknown']} of "
          f"{e['n_unknown'] + e['n_labelled']} "
          f"({e['pct_of_error_barred_that_are_unlabelled']}% of error-barred comparisons)")
    print(f"  read as standard deviation : {e['read_as_std'].get('pct_fail')}% fail "
          f"(n={e['read_as_std'].get('n')})")
    print(f"  read as standard error     : {e['read_as_sem'].get('pct_fail')}% fail "
          f"(n={e['read_as_sem'].get('n')})")
    print(f"  labelled subset only       : {e['labelled_only'].get('pct_fail')}% fail "
          f"(n={e['labelled_only'].get('n')})")

    c = res["paper_level_crosstab"]
    print(f"\nPaper level: {c['error_bar_and_run_count']} print both, "
          f"{c['error_bar_only']} an error bar with no run count, "
          f"{c['run_count_only']} a run count with no error bar, {c['neither']} neither")
    print(f"  of papers printing an error bar, "
          f"{c['pct_of_error_bar_papers_that_also_state_runs']}% also state a run count")
    print(f"\n-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def correlation_sensitivity(comparisons: list, rhos=(0.0, 0.3, 0.5, 0.7, 0.9)) -> dict:
    """What if the two compared values are not independent?

    Two methods in one results table are nearly always evaluated on the same
    benchmark instances, so their errors are positively correlated and the
    difference is a paired quantity:

        Var(A - B) = SE_A^2 + SE_B^2 - 2 rho SE_A SE_B

    Assuming rho = 0 inflates the standard error of the difference, which makes
    a gap harder to call significant and therefore makes this paper's failure
    rate *higher* than it should be. That is the direction an author auditing
    other people's statistics has the least right to err in, so the whole range
    is reported and the headline uses a moderate positive correlation rather
    than the value most flattering to the thesis.

    The papers do not print the covariance, so this is a sensitivity analysis,
    not an estimate.
    """
    import math
    from analyze import _standard_error
    from paperengine.stats import holm_bonferroni
    from analyze import p_value

    out = {}
    for rho in rhos:
        tested = []
        for c in comparisons:
            kind = c.get("dispersion_kind")
            se_w = _standard_error(c["winner_dispersion"], kind, c.get("n_runs"))
            se_r = _standard_error(c["runner_dispersion"], kind, c.get("n_runs"))
            if se_w is None or se_r is None:
                continue
            r = p_value(c["gap"], se_w, se_r, c.get("n_runs"), rho=rho)
            if r is None:
                continue
            tested.append((c, r["p"]))
        if not tested:
            out[str(rho)] = {"n": 0}
            continue
        by_table: dict = {}
        for c, p in tested:
            by_table.setdefault((c["paper"], c["table"], c["page"]), []).append((c, p))
        fail = fail_holm = 0
        for group in by_table.values():
            ps = [p for _, p in group]
            holm = holm_bonferroni(ps, 0.05)
            for (c, p), h in zip(group, holm):
                fail += p >= 0.05
                fail_holm += not h
        n = len(tested)
        out[str(rho)] = {"n": n,
                         "pct_fail": round(100 * fail / n, 1),
                         "pct_fail_holm": round(100 * fail_holm / n, 1)}
    return out


def power_audit(comparisons: list, power: float = 0.8, alpha: float = 0.05) -> dict:
    """Was the experiment ever capable of detecting what it claims?

    A reviewer called the finding that failing improvements are smaller ones
    close to tautological, and he was right as it was stated: a smaller gap is
    harder to detect, so of course the failures are small. The non-tautological
    question runs the other way. From the dispersion and run count a paper
    prints, one can compute the smallest difference that experiment could have
    detected at conventional power -- and then ask how the gap it reports
    compares.

    A comparison whose reported gap falls below its own minimum detectable
    effect was not a close call. The experiment could not have distinguished
    that difference from zero however it came out, and the bold cell records a
    coin flip rather than a finding.
    """
    import math
    from analyze import _standard_error
    from paperengine.stats import norm_ppf

    z_a, z_b = norm_ppf(1 - alpha / 2), norm_ppf(power)
    rows = []
    for c in comparisons:
        kind = c.get("dispersion_kind")
        se_w = _standard_error(c["winner_dispersion"], kind, c.get("n_runs"))
        se_r = _standard_error(c["runner_dispersion"], kind, c.get("n_runs"))
        if se_w is None or se_r is None:
            continue
        se_diff = math.sqrt(se_w ** 2 + se_r ** 2)
        mde = (z_a + z_b) * se_diff
        rows.append({"gap": c["gap"], "mde": mde,
                     "underpowered": c["gap"] < mde,
                     "ratio": c["gap"] / mde if mde > 0 else None,
                     "paper": c["paper"]})
    if not rows:
        return {"n": 0}

    under = [r for r in rows if r["underpowered"]]
    ratios = sorted(r["ratio"] for r in rows if r["ratio"] is not None)
    return {
        "n": len(rows),
        "n_papers": len(set(r["paper"] for r in rows)),
        "underpowered": len(under),
        "pct_underpowered": round(100 * len(under) / len(rows), 1),
        "median_gap_over_mde": round(ratios[len(ratios) // 2], 3) if ratios else None,
        "q1_gap_over_mde": round(ratios[len(ratios) // 4], 3) if ratios else None,
        "power": power, "alpha": alpha,
        "reading": ("A ratio below 1 means the experiment could not have detected the "
                    "difference it reports, at conventional power, whichever way it came out."),
    }


def design_mde(comparisons: list, records: list, power: float = 0.8, alpha: float = 0.05,
               min_cells: int = 10, min_papers: int = 3) -> dict:
    """Could a design with this many runs have detected this gap?

    The first version of this audit computed the minimum detectable effect from
    the paper's own error bar and run count. Two reviewers pointed out, rightly,
    that gap over that quantity is the z statistic divided by 2.80, so "below
    its own MDE" is the significance test at a different cutoff, the observed-
    power fallacy of Hoenig and Heisey (2001). That version is kept below as
    ``own_dispersion`` for comparison and is not what the paper reports.

    This version takes the run count from the paper and the dispersion from
    everyone else: the median standard deviation printed by other papers on the
    same benchmark, on the same scale, or across the corpus when the benchmark
    is unnamed or rarely reported with bars. That is a prospective statement
    about the design -- three seeds, typical noise -- and it is independent of
    the gap and of whatever the paper printed. It also reaches the comparisons
    with a run count but no error bar at all, which the z test cannot.
    """
    import math
    import statistics
    from benchmark_resolution import identify
    from paperengine.stats import norm_ppf

    k = norm_ppf(1 - alpha / 2) + norm_ppf(power)

    def scale_of(v):
        if v is None:
            return None
        a = abs(v)
        return "unit" if a <= 1.0 else ("percent" if a <= 100.0 else None)

    from extra_stats import topic_of

    captions = {}
    topic = {r["id"]: topic_of(r.get("title", "")) for r in records}
    sd_by_key: dict = {}      # (benchmark, scale) -> [(paper, sd)]
    sd_by_topic: dict = {}    # (subfield, scale) -> [(paper, sd)]
    sd_by_scale: dict = {}    # scale -> [(paper, sd)]
    for r in records:
        for t in r.get("tables", []):
            key = (r["id"], t.get("number"), t.get("page"))
            captions[key] = t.get("caption") or ""
            if t.get("dispersion_kind") != "std":
                continue
            benches = identify(captions[key])
            for c in t["cells"]:
                if c.get("dispersion") is None or c["dispersion"] <= 0:
                    continue
                sc = scale_of(c.get("mean"))
                if sc is None:
                    continue
                sd_by_scale.setdefault(sc, []).append((r["id"], c["dispersion"]))
                sd_by_topic.setdefault((topic[r["id"]], sc), []).append((r["id"], c["dispersion"]))
                for b in benches:
                    sd_by_key.setdefault((b, sc), []).append((r["id"], c["dispersion"]))

    def _pool(store, key, paper):
        rows_ = store.get(key, [])
        pool = [sd for (p_, sd) in rows_ if p_ != paper]
        if len(pool) >= min_cells and len({p_ for (p_, _) in rows_ if p_ != paper}) >= min_papers:
            return statistics.median(pool)
        return None

    def external_sd(paper, benches, sc):
        # Same benchmark first, then the paper's own subfield, then the corpus:
        # the corpus pool is written by whoever prints deviations, which is a
        # different mix of subfields from the population that prints none.
        for b in benches:
            v = _pool(sd_by_key, (b, sc), paper)
            if v is not None:
                return v, "benchmark"
        v = _pool(sd_by_topic, (topic.get(paper, "other"), sc), paper)
        if v is not None:
            return v, "subfield"
        pool = [sd for (p_, sd) in sd_by_scale.get(sc, []) if p_ != paper]
        return (statistics.median(pool), "corpus") if pool else (None, None)

    rows = []
    excluded = {"no_run_count": 0, "outside_both_scales": 0, "scales_differ": 0, "no_noise_level": 0}
    from analyze import t_ppf
    # The cut-point is the critical value a reader would use at that run
    # count: Welch's t with 2(n-1) degrees of freedom when both arms share
    # the imputed noise, which is the headline's footing rather than a normal
    # cut. At n = 5 it is 2.31 rather than 1.96.
    def k_alpha_at(n):
        return t_ppf(1 - alpha / 2, 2 * (n - 1))
    for c in comparisons:
        n = c.get("n_runs")
        if not n or n < 2:
            excluded["no_run_count"] += 1
            continue
        sc = scale_of(c["winner"])
        if sc is None:
            excluded["outside_both_scales"] += 1
            continue
        if scale_of(c["runner_up"]) != sc:
            excluded["scales_differ"] += 1
            continue
        benches = identify(captions.get((c["paper"], c["table"], c["page"]), ""))
        sd, source = external_sd(c["paper"], benches, sc)
        if sd is None:
            excluded["no_noise_level"] += 1
            continue
        se_diff = sd * math.sqrt(2.0 / n)
        mde = k * se_diff
        own = None
        k_alpha = k_alpha_at(n)
        if c.get("test"):
            own = c["test"]["p"] >= alpha   # the paper's own numbers, the paper's own test
        rows.append({"gap": c["gap"], "mde": mde, "below": c["gap"] < mde,
                     "below_alpha": c["gap"] < k_alpha * se_diff,
                     "own_below_alpha": own,
                     "source": source, "testable": bool(c.get("test")),
                     "local_n": c.get("n_runs_source") in ("caption", "page"),
                     "topic": topic.get(c["paper"], "other"),
                     "no_bars": c["winner_dispersion"] is None and c["runner_dispersion"] is None,
                     "paper": c["paper"], "n": n, "scale": sc, "sd": sd})
    if not rows:
        return {"n": 0}

    def pct(sub, key="below"):
        return round(100 * sum(1 for r in sub if r[key]) / len(sub), 1) if sub else None

    testable = [r for r in rows if r["testable"]]
    no_bars = [r for r in rows if r["no_bars"]]
    own = power_audit(comparisons, power=power, alpha=alpha)
    sds_pct = [r["sd"] for r in rows if r["scale"] == "percent"]
    unit = [r for r in rows if r["scale"] == "unit"]
    sds_unit = [r["sd"] for r in unit]
    # Borrowed against own noise on the identical comparisons, at the same
    # threshold: the calibration a reviewer asked for, as a 2x2.
    same = [r for r in testable if r["own_below_alpha"] is not None]
    agree = sum(1 for r in same if r["below_alpha"] == r["own_below_alpha"])
    by_topic = {}
    for name in sorted({r["topic"] for r in rows}):
        sub = [r for r in rows if r["topic"] == name]
        by_topic[name] = {"n": len(sub), "pct_below_alpha": pct(sub, "below_alpha"),
                          "pct_no_bars_below_alpha": pct([r for r in sub if r["no_bars"]], "below_alpha")}
    return {
        "same_subset": {"n": len(same),
                        "borrowed_below_alpha": pct(same, "below_alpha"),
                        "own_below_alpha": pct(same, "own_below_alpha"),
                        "per_comparison_agreement": round(100 * agree / len(same), 1) if same else None,
                        "both_below": sum(1 for r in same if r["below_alpha"] and r["own_below_alpha"]),
                        "borrowed_only": sum(1 for r in same if r["below_alpha"] and not r["own_below_alpha"]),
                        "own_only": sum(1 for r in same if r["own_below_alpha"] and not r["below_alpha"])},
        "by_subfield": by_topic,
        "pct_sd_from_subfield": round(100 * sum(1 for r in rows if r["source"] == "subfield") / len(rows), 1),
        "n": len(rows),
        "n_papers": len(set(r["paper"] for r in rows)),
        "excluded": excluded,
        "pct_below_design_mde": pct(rows),
        "pct_below_alpha_threshold": pct(rows, "below_alpha"),
        "pct_below_alpha_threshold_no_bars": pct(no_bars, "below_alpha"),
        "n_percent_scale": len(rows) - len(unit),
        "n_unit_scale": len(unit),
        "pct_below_design_mde_percent_scale": pct([r for r in rows if r["scale"] == "percent"]),
        "pct_below_design_mde_unit_scale": pct(unit),
        "median_external_sd_unit_scale": round(statistics.median(sds_unit), 4) if sds_unit else None,
        "pct_below_design_mde_benchmark_matched": pct([r for r in rows if r["source"] == "benchmark"]),
        "n_testable": len(testable),
        "pct_below_design_mde_testable": pct(testable),
        "n_no_bars": len(no_bars),
        "pct_below_design_mde_no_bars": pct(no_bars),
        # Only run counts read from the caption or the table's own page, which
        # the bar-less audit found to apply to the table where a count read
        # from elsewhere in the paper applied about half the time.
        "n_local_n": sum(1 for r in rows if r["local_n"]),
        "pct_below_alpha_threshold_local_n": pct([r for r in rows if r["local_n"]], "below_alpha"),
        "n_no_bars_local_n": sum(1 for r in no_bars if r["local_n"]),
        "pct_below_alpha_threshold_no_bars_local_n": pct([r for r in no_bars if r["local_n"]], "below_alpha"),
        "pct_sd_from_benchmark": round(100 * sum(1 for r in rows if r["source"] == "benchmark") / len(rows), 1),
        "median_external_sd_percent_scale": round(statistics.median(sds_pct), 2) if sds_pct else None,
        "median_runs": statistics.median(r["n"] for r in rows),
        "median_mde_percent_scale": round(statistics.median(
            r["mde"] for r in rows if r["scale"] == "percent"), 2) if sds_pct else None,
        "power": power, "alpha": alpha, "min_cells": min_cells, "min_papers": min_papers,
        "own_dispersion": {"n": own.get("n"), "pct_underpowered": own.get("pct_underpowered"),
                           "note": "gap/MDE = z/2.80 here; kept for comparison, not reported"},
    }


def checkability_span(comparisons: list) -> dict:
    """How far the share that can be checked moves across the conventions.

    A standard error is already the dispersion of a mean, so a comparison whose
    bars are standard errors needs no run count to be testable. That makes the
    checkability headline the most convention-dependent number in the paper --
    more so than the failure rate, which is the only one an earlier draft gave a
    range for.

    Both ends and the ratio are computed here rather than typed, because when
    they were typed the ratio drifted from 8.3 to 9.5 the first time the
    analysis was regenerated.
    """
    n = len(comparisons)
    if not n:
        return {}
    as_reported = sum(1 for c in comparisons if c.get("test"))

    strict = 0
    for c in comparisons:
        d = dict(c)
        if d.get("n_runs_source") != "caption":
            d["n_runs"] = None
        if test_comparison(d):
            strict += 1

    as_sem = 0
    for c in comparisons:
        if c.get("test"):
            as_sem += 1
        elif (c["winner_dispersion"] is not None and c["runner_dispersion"] is not None
              and test_comparison(c, kind_override="sem")):
            as_sem += 1

    lo = round(100 * strict / n, 1)
    hi = round(100 * as_sem / n, 1)
    return {
        "n_comparisons": n,
        "pct_strict_caption_only": lo,
        "pct_as_reported": round(100 * as_reported / n, 1),
        "pct_every_bar_a_standard_error": hi,
        "span_factor": round(hi / lo, 1) if lo else None,
    }
