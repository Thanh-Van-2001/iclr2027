"""Everything the paper cites that was once computed at a command line.

Each of these numbers answers a reviewer objection, and each was first produced
by a one-off script, read off the terminal, and typed into the macro generator.
That is a boundary problem rather than a bookkeeping one: the number audit
guards the LaTeX, so a value typed on the far side of it inherits none of the
guarantee. One of them, the checkability span factor, had already drifted from
8.3 to 9.5 by the time anyone looked.

So they live here, computed from the corpus like everything else, and
``make_all.py`` regenerates them.
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import comparisons_from_table, orientation  # noqa: E402

TIE_STRICT = re.compile(
    r"(?i)not (?:statistically )?significan|no significant differ|statistically indistinguish|"
    r"within (?:one|1|the) standard (?:error|deviation)|equal(?:ly)? best|"
    r"comparable to the best|statistically tied|not significantly (?:worse|different)")
TIE_SECOND = re.compile(r"(?i)second[- ]best|underlin")

JUSTIFICATION = [
    ("figure", r"(?i)\bfig(?:ure)?\.?\s*\d|\bplot|shaded|curve"),
    ("appendix", r"(?i)appendix|supplement"),
    ("test", r"(?i)\bt-test|p-value|significan|wilcoxon|permutation|bootstrap"),
    ("seeds", r"(?i)\b(?:random\s+)?seeds?\b|\bruns?\b|\btrials?\b|averag"),
    # Without this category a paper whose whole justification is "we report
    # standard deviations" falls into "no recognisable claim", which moved that
    # figure from 29.6% to 38.0% the first time this module was written.
    ("dispersion", r"(?i)standard deviation|standard error|confidence interval|"
                   r"credible interval|\bstd\b|variance"),
]
_JUST = [(k, re.compile(p)) for k, p in JUSTIFICATION]


def tie_marking(records: list, comparisons: list) -> dict:
    """How common the tie convention is, and what removing it does."""
    caption = {}
    n_tables = n_tie = n_second = 0
    for r in records:
        for t in r.get("tables", []):
            n_tables += 1
            cap = t.get("caption") or ""
            caption[(r["id"], t.get("number"), t.get("page"))] = cap
            n_tie += bool(TIE_STRICT.search(cap))
            n_second += bool(TIE_SECOND.search(cap))

    testable = [c for c in comparisons if c.get("test")]
    tie = [c for c in testable
           if TIE_STRICT.search(caption.get((c["paper"], c["table"], c["page"]), ""))]
    keep = [c for c in testable if c not in tie]

    def fail_rate(rows):
        return round(100 * sum(1 for c in rows if not c["survives_raw"]) / len(rows), 1) if rows else None

    tie_papers = set()
    for r in records:
        if any(TIE_STRICT.search(t.get("caption") or "") for t in r.get("tables", [])):
            tie_papers.add(r["id"])

    return {
        "n_tables": n_tables,
        "pct_tables_claiming_a_tie": round(100 * n_tie / max(n_tables, 1), 2),
        "pct_tables_marking_second_best": round(100 * n_second / max(n_tables, 1), 1),
        "papers_affected": len(tie_papers),
        "pct_of_testable_tie_marked": round(100 * len(tie) / max(len(testable), 1), 2),
        "fail_rate_all": fail_rate(testable),
        "fail_rate_excluding_tie_marked": fail_rate(keep),
        "fail_rate_among_tie_marked": fail_rate(tie),
    }


def checklist_justifications(records: list) -> dict:
    """What the checklist 'yes' answers actually claim, when the tables show nothing."""
    yes = [r for r in records if r.get("checklist_error_bars") == "yes"]
    gap = [r for r in yes if not r.get("reports_explicit_error_bar")]
    counts = collections.Counter()
    unrecognised = 0
    for r in gap:
        j = r.get("checklist_justification") or ""
        hit = False
        for key, pat in _JUST:
            if pat.search(j):
                counts[key] += 1
                hit = True
        if not hit:
            unrecognised += 1
    n = max(len(gap), 1)
    return {
        "n_yes": len(yes),
        "n_yes_without_table_error_bar": len(gap),
        "pct_seeds": round(100 * counts["seeds"] / n, 1),
        "pct_test": round(100 * counts["test"] / n, 1),
        "pct_claims_dispersion": round(100 * counts["dispersion"] / n, 1),
        "pct_figure": round(100 * counts["figure"] / n, 1),
        "pct_appendix": round(100 * counts["appendix"] / n, 1),
        "pct_unrecognised": round(100 * unrecognised / n, 1),
    }


def extraction_limits(records: list, max_pages: int = 40) -> dict:
    """The two limits that could have explained the checklist gap, and do not."""
    n = len(records)
    long_papers = [r for r in records if r["n_pages"] > max_pages]
    short = [r for r in records if r["n_pages"] <= max_pages]
    no_table = [r for r in records if r["n_tables_detected"] == 0]
    with_table = [r for r in records if r["n_tables_detected"] > 0]

    def bar_rate(rows):
        return round(100 * sum(1 for r in rows if r.get("reports_explicit_error_bar"))
                     / max(len(rows), 1), 1)

    return {
        "max_pages": max_pages,
        "pct_papers_over_window": round(100 * len(long_papers) / n, 1),
        "error_bar_rate_long": bar_rate(long_papers),
        "error_bar_rate_short": bar_rate(short),
        "pct_papers_with_no_table": round(100 * len(no_table) / n, 1),
        "paper_level_rate_all": bar_rate(records),
        "paper_level_rate_with_a_table": bar_rate(with_table),
    }


def filter_selection(records: list) -> dict:
    """Does the bold filter select against tables that report uncertainty?"""
    kept_t = kept_bar = disc_t = disc_bar = 0
    papers_no_cmp = papers_no_cmp_bar = 0
    for r in records:
        contributed = False
        for t in r.get("tables", []):
            has_bar = any(c["dispersion"] is not None and c.get("dispersion_style") == "pm"
                          for c in t["cells"])
            if orientation(t["cells"]) != "none" and comparisons_from_table(t):
                kept_t += 1
                kept_bar += has_bar
                contributed = True
            else:
                disc_t += 1
                disc_bar += has_bar
        if r["n_tables_detected"] > 0 and not contributed:
            papers_no_cmp += 1
            papers_no_cmp_bar += bool(r.get("reports_explicit_error_bar"))
    return {
        "n_tables_retained": kept_t,
        "pct_error_bar_retained": round(100 * kept_bar / max(kept_t, 1), 1),
        "n_tables_discarded": disc_t,
        "pct_error_bar_discarded": round(100 * disc_bar / max(disc_t, 1), 1),
        "papers_with_tables_but_no_comparison": papers_no_cmp,
        "of_those_with_an_error_bar": papers_no_cmp_bar,
    }


def headline_with_extraction(pct_neither: float, recall_lo: float) -> dict:
    """The headline once the recall interval is folded in."""
    return {
        "pct_neither": pct_neither,
        "recall_lower_bound": recall_lo,
        "low": round(pct_neither * recall_lo, 1),
        "high": pct_neither,
    }


def failure_by_gap_band(comparisons: list) -> dict:
    """Failure rate in the smallest and largest bands of reported improvement.

    The figure shows the whole curve; the text quotes its two ends, and they
    should come from the same computation as the figure rather than be read off
    it.
    """
    tested = [c for c in comparisons
              if c.get("test") and c.get("relative_gap") is not None]

    def rate(lo, hi):
        band = [c for c in tested if lo <= 100 * c["relative_gap"] < hi]
        return (round(100 * sum(1 for c in band if not c["survives_raw"]) / len(band))
                if band else None), len(band)

    low, n_low = rate(0, 0.5)
    high, n_high = rate(10, 1e9)
    return {"pct_fail_under_half_point": low, "n_under_half_point": n_low,
            "pct_fail_over_ten_points": high, "n_over_ten_points": n_high}



def compute(records: list, comparisons: list, pct_neither: float,
            recall_lo: float) -> dict:
    return {
        "tie_marking": tie_marking(records, comparisons),
        "checklist_justifications": checklist_justifications(records),
        "extraction_limits": extraction_limits(records),
        "filter_selection": filter_selection(records),
        "headline_with_extraction": headline_with_extraction(pct_neither, recall_lo),
        "failure_by_gap_band": failure_by_gap_band(comparisons),
    }


def main() -> int:
    with open("data/extracted_2025.json", encoding="utf-8") as fh:
        records = json.load(fh)
    with open("out/analysis_2025.json", encoding="utf-8") as fh:
        comparisons = json.load(fh)["_comparisons"]
    with open("out/both_years.json", encoding="utf-8") as fh:
        pct_neither = json.load(fh)["2025"]["pct_neither"]

    # The lower end of the visual recall audit, which is hand-counted and so is
    # the one input here that a person supplies.
    res = compute(records, comparisons, pct_neither, recall_lo=0.940)
    with open("out/extra_stats.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
