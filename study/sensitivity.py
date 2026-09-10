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

from analyze import test_comparison  # noqa: E402
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
    unknown = [c for c in comparisons
               if c.get("dispersion_kind") == "unknown" and c.get("n_runs")]
    labelled = [c for c in comparisons if c.get("dispersion_kind") in ("std", "sem", "ci")]
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
    ap.add_argument("--extracted", default="data/extracted_2025.json")
    ap.add_argument("--out", default="out/sensitivity_2025.json")
    args = ap.parse_args(argv)

    with open(args.analysis, encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]
    with open(args.extracted, encoding="utf-8") as fh:
        papers = json.load(fh)

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
    from paperengine.stats import holm_bonferroni, norm_cdf

    out = {}
    for rho in rhos:
        tested = []
        for c in comparisons:
            kind = c.get("dispersion_kind")
            se_w = _standard_error(c["winner_dispersion"], kind, c.get("n_runs"))
            se_r = _standard_error(c["runner_dispersion"], kind, c.get("n_runs"))
            if se_w is None or se_r is None:
                continue
            var = se_w ** 2 + se_r ** 2 - 2 * rho * se_w * se_r
            if var <= 0:
                continue
            z = c["gap"] / math.sqrt(var)
            tested.append((c, 2 * (1 - norm_cdf(abs(z)))))
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
