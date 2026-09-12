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
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import comparisons_from_table, load_records, orientation  # noqa: E402

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


def headline_with_comparison_audit(pct_neither: float, absent: dict) -> dict:
    """The no-bar share, scaled by the comparison-level audit of that stratum.

    The table-level recall audit is conditional on a table being detected and
    read as empty; the comparison-level audit reads retained comparisons the
    pipeline calls bar-less and finds a few whose dispersion sits in a
    separate column. Scaling the headline by that rate, with its interval, is
    the other bound the paper owes.
    """
    lo, hi = absent["ci"][0] / 100.0, absent["ci"][1] / 100.0
    return {"point": round(pct_neither * absent["pct"] / 100.0, 1),
            "low": round(pct_neither * lo, 1), "high": round(pct_neither * hi, 1)}


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



def _fail_rate(rows: list, p_key: str = "_p", family: str = "table") -> dict:
    """Failure rate, raw and Holm-corrected, with the family stated."""
    if not rows:
        return {"n": 0}
    from paperengine.stats import holm_bonferroni
    groups: dict = {}
    for c in rows:
        key = (c["paper"], c["table"], c["page"]) if family == "table" else c["paper"]
        groups.setdefault(key, []).append(c)
    fail = fail_holm = 0
    for g in groups.values():
        holm = holm_bonferroni([c[p_key] for c in g], 0.05)
        for c, h in zip(g, holm):
            fail += c[p_key] >= 0.05
            fail_holm += not h
    n = len(rows)
    return {"n": n, "pct_fail": round(100 * fail / n, 1),
            "pct_fail_holm": round(100 * fail_holm / n, 1)}


ABLATION = re.compile(r"(?i)\bablat|\bw/o\b|\bwithout\b|\bcomponent|\bvariant|\bremov|\beffect of\b")


def _paper_bootstrap_fail(rows: list, reps: int = 1000, seed: int = 0) -> list:
    """Percentile interval for the failure rate, resampling papers."""
    import random
    by_paper: dict = {}
    for c in rows:
        by_paper.setdefault(c["paper"], []).append(c["_p"] >= 0.05)
    papers = list(by_paper.values())
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        draw = [papers[rng.randrange(len(papers))] for _ in papers]
        flat = [x for p in draw for x in p]
        vals.append(100 * sum(flat) / max(len(flat), 1))
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def subset_direction(records: list, comparisons: list) -> dict:
    """Which way the testable subset is selected, measured two ways.

    (1) The failure rate reweighted to the population's subfield mix, so a
    subfield that reports bars more often does not dominate. (2) Ablation
    tables, flagged from the caption, against the rest: the share reporting a
    bar and the failure rate among the testable, with paper-resampled
    intervals. Neither settles the direction of the selection; both are
    reported so that no bound is asserted.
    """
    testable = [dict(c) for c in comparisons if c.get("test")]
    for c in testable:
        c["_p"] = c["test"]["p"]
    # (1) reweighting by subfield of the paper title
    topic = {r["id"]: topic_of(r.get("title", "")) for r in records}
    by_topic_all: dict = {}
    by_topic_test: dict = {}
    for c in comparisons:
        t = topic[c["paper"]]
        by_topic_all[t] = by_topic_all.get(t, 0) + 1
    for c in testable:
        t = topic[c["paper"]]
        d = by_topic_test.setdefault(t, [0, 0])
        d[0] += 1
        d[1] += c["_p"] >= 0.05
    n_all = len(comparisons)
    covered = sum(n for t, n in by_topic_all.items() if t in by_topic_test)
    reweighted = sum(by_topic_all[t] / covered * (d[1] / d[0]) for t, d in by_topic_test.items())
    # (2) ablation tables
    abl = [c for c in comparisons if ABLATION.search(c.get("caption") or "")]
    main = [c for c in comparisons if not ABLATION.search(c.get("caption") or "")]
    def neither(rows):
        return round(100 * sum(1 for c in rows if c["winner_dispersion"] is None
                                and c["runner_dispersion"] is None) / max(len(rows), 1), 1)
    abl_t = [c for c in testable if ABLATION.search(c.get("caption") or "")]
    main_t = [c for c in testable if not ABLATION.search(c.get("caption") or "")]
    def fr(rows):
        return round(100 * sum(1 for c in rows if c["_p"] >= 0.05) / max(len(rows), 1), 1)
    return {
        "reweighted_to_population_subfields": {"pct_fail": round(100 * reweighted, 1),
                                               "n": len(testable),
                                               "pct_population_covered": round(100 * covered / n_all, 1)},
        "ablation": {"n_all": len(abl), "pct_of_comparisons": round(100 * len(abl) / n_all, 1),
                     "pct_neither": neither(abl), "n_testable": len(abl_t),
                     "pct_testable": round(100 * len(abl_t) / max(len(abl), 1), 1),
                     "pct_fail": fr(abl_t), "ci_fail": _paper_bootstrap_fail(abl_t)},
        "main": {"n_all": len(main), "pct_neither": neither(main), "n_testable": len(main_t),
                 "pct_testable": round(100 * len(main_t) / max(len(main), 1), 1),
                 "pct_fail": fr(main_t), "ci_fail": _paper_bootstrap_fail(main_t)},
    }


def headline_span(comparisons: list, records: list = None) -> dict:
    """Every row of the conventions table, each on a stated population.

    A reviewer pointed out that the span quoted in an earlier draft ran from a
    row computed on all testable comparisons to a row computed on the
    unlabelled subset alone, so its two ends were not on the same population.
    Here every row that can be evaluated on the full testable set is, and the
    rows that cannot carry their own n. The span is taken over the full-
    population rows only.
    """
    import math
    from analyze import test_comparison, _standard_error, p_value

    testable = [dict(c) for c in comparisons if c.get("test")]
    for c in testable:
        c["_p"] = c["test"]["p"]
        c["_pz"] = c["test"]["p_z"]
    rows = {}
    rows["as_reported"] = _fail_rate(testable)
    rows["holm_family_paper"] = _fail_rate(testable, family="paper")
    # The two-sample z on every testable comparison: the bars taken as exact,
    # the reading most favourable to the field.
    rows["z_two_sided"] = _fail_rate(testable, p_key="_pz")

    # Unlabelled bars read as standard errors, labelled bars as stated.
    se_rows = []
    for c in testable:
        if c["dispersion_kind"] == "unknown":
            r = test_comparison(c, kind_override="sem")
            d = dict(c); d["_p"] = r["p"]; se_rows.append(d)
        else:
            se_rows.append(c)
    rows["unlabelled_as_sem"] = _fail_rate(se_rows)
    rows["labelled_only"] = _fail_rate([c for c in testable
                                        if c["dispersion_kind"] in ("std", "sem", "ci")])

    strict = []
    for c in comparisons:
        d = dict(c)
        if d.get("n_runs_source") != "caption":
            d["n_runs"] = None
        r = test_comparison(d)
        if r:
            d["_p"] = r["p"]; strict.append(d)
    rows["caption_run_count_only"] = _fail_rate(strict)

    # A count found on the table's own page, as well as in its caption: the
    # middle reading between caption-only and anywhere-in-the-paper.
    local = []
    for c in comparisons:
        d = dict(c)
        if d.get("n_runs_source") not in ("caption", "page"):
            d["n_runs"] = None
        r = test_comparison(d)
        if r:
            d["_p"] = r["p"]; local.append(d)
    rows["caption_or_page_run_count"] = _fail_rate(local)

    for rho in (0.5, 0.9):
        rr = []
        for c in testable:
            kind = c["dispersion_kind"]
            se_w = _standard_error(c["winner_dispersion"], kind, c["n_runs"])
            se_r = _standard_error(c["runner_dispersion"], kind, c["n_runs"])
            r = p_value(c["gap"], se_w, se_r, c["n_runs"], rho=rho)
            if r is None:
                continue
            d = dict(c); d["_p"] = r["p"]; rr.append(d)
        rows[f"rho_{rho}"] = _fail_rate(rr)

    one_sided = [dict(c, _p=c["test"]["p"] / 2) for c in testable]
    rows["one_sided"] = _fail_rate(one_sided)

    # The same comparisons reweighted to the population's subfield mix, so a
    # subfield that reports bars more often does not dominate the rate.
    if records is not None:
        sd = subset_direction(records, comparisons)["reweighted_to_population_subfields"]
        rows["reweighted_subfields"] = {"n": len(testable), "pct_fail": sd["pct_fail"],
                                        "pct_fail_holm": None}

    # The rho rows are a matched-seed hypothetical: run-to-run fluctuations of
    # two methods are independent unless the seeds were matched, which print
    # cannot confirm. They are reported but kept out of the span.
    full = [k for k, v in rows.items() if v.get("n") == len(testable) and not k.startswith("rho_")]
    vals = [rows[k]["pct_fail"] for k in full]
    return {"rows": rows, "n_full_population": len(testable),
            "full_population_rows": full,
            "span": [min(vals), max(vals)],
            "span_all_rows": [min(v["pct_fail"] for v in rows.values() if v.get("n")),
                              max(v["pct_fail"] for v in rows.values() if v.get("n"))]}


def holm_families(comparisons: list) -> dict:
    """How large the within-table families the Holm correction runs over are."""
    fam: dict = {}
    for c in comparisons:
        if c.get("test"):
            fam[(c["paper"], c["table"], c["page"])] = fam.get((c["paper"], c["table"], c["page"]), 0) + 1
    sizes = list(fam.values())
    n = len(sizes)
    per_table = {}
    for c in comparisons:
        per_table[(c["paper"], c["table"], c["page"])] = c.get("n_ties_in_table", 0)
    ties = sum(per_table.values())
    return {
        "n_tables_with_testable": n,
        "pct_family_size_1": round(100 * sum(1 for s in sizes if s == 1) / max(n, 1), 1),
        "pct_family_size_2_to_5": round(100 * sum(1 for s in sizes if 2 <= s <= 5) / max(n, 1), 1),
        "pct_family_size_over_5": round(100 * sum(1 for s in sizes if s > 5) / max(n, 1), 1),
        "median_family_size": statistics.median(sizes) if sizes else None,
        "pct_testable_in_families_over_5": round(100 * sum(s for s in sizes if s > 5) / max(sum(sizes), 1), 1),
        "exact_ties_dropped": ties,
    }


def venue_counts(records: list, comparisons: list) -> dict:
    """How the sample and the comparisons divide between the two venues."""
    out = {}
    for venue in sorted({r["venue"] for r in records}):
        ids = {r["id"] for r in records if r["venue"] == venue}
        cs = [c for c in comparisons if c["paper"] in ids]
        t = [c for c in cs if c.get("test")]
        out[venue] = {
            "papers": len(ids), "comparisons": len(cs), "testable": len(t),
            "pct_neither": round(100 * sum(1 for c in cs if c["winner_dispersion"] is None
                                           and c["runner_dispersion"] is None) / max(len(cs), 1), 1),
            "pct_fail": round(100 * sum(1 for c in t if not c["survives_raw"]) / max(len(t), 1), 1),
            "pct_papers_with_error_bar": round(100 * sum(
                1 for r in records if r["venue"] == venue and r.get("reports_explicit_error_bar"))
                / max(len(ids), 1), 1),
        }
    return out


def other_routes(records: list, comparisons: list) -> dict:
    """Ways a claim can be checked that are not an error bar on both cells.

    A dagger from a permutation test, a p-value in the footnote, an interval
    on the cell, a figure with error bars: the definition of "testable" sees
    none of these, and a reviewer was right that the paper should say how
    much it is leaving out. Daggers are counted as markers of some kind,
    which overstates them -- a dagger often means "copied from the original
    paper" -- so the figures here are ceilings on what the definition misses.
    """
    tables = {(r["id"], t.get("number"), t.get("page")): t
              for r in records for t in r.get("tables", [])}

    def marked(t):
        m = t.get("markers") or {}
        return any(m.get(k, 0) for k in ("dagger", "star", "pvalue", "signif_word"))

    def marked_strict(t):
        m = t.get("markers") or {}
        return bool(m.get("pvalue", 0) or m.get("signif_word", 0))

    n = len(comparisons)
    no_bar = [c for c in comparisons
              if c["winner_dispersion"] is None and c["runner_dispersion"] is None]
    no_bar_marked = sum(1 for c in no_bar if marked(tables.get((c["paper"], c["table"], c["page"]), {})))
    no_bar_strict = sum(1 for c in no_bar
                        if marked_strict(tables.get((c["paper"], c["table"], c["page"]), {})))
    testable = sum(1 for c in comparisons if c.get("test"))
    interval_cells = sum(1 for t in tables.values() for c in t["cells"]
                         if c.get("dispersion_style") == "ci")
    ci_comparisons = sum(1 for c in comparisons
                         if c.get("winner_style") == "ci" or c.get("runner_style") == "ci")

    papers = len(records)
    mentions_test = sum(1 for r in records if r.get("mentions_significance_test"))
    fig_unc = sum(1 for r in records if r.get("n_figure_captions_with_uncertainty", 0) > 0)
    no_bar_papers = [r for r in records if not r.get("reports_explicit_error_bar")]
    no_bar_fig = sum(1 for r in no_bar_papers if r.get("n_figure_captions_with_uncertainty", 0) > 0)
    captions = sum(r.get("n_table_captions", 0) for r in records)
    detected = sum(r.get("n_tables_detected", 0) for r in records)

    def pct(a, b):
        return round(100 * a / b, 1) if b else None

    return {
        "n_comparisons": n,
        "n_no_bar": len(no_bar),
        "no_bar_with_any_marker": no_bar_marked,
        "pct_no_bar_with_any_marker": pct(no_bar_marked, len(no_bar)),
        "no_bar_with_pvalue_or_significance_word": no_bar_strict,
        "pct_no_bar_with_pvalue_or_significance_word": pct(no_bar_strict, len(no_bar)),
        "pct_testable_or_any_marker": pct(testable + no_bar_marked, n),
        "pct_testable_or_strict_marker": pct(testable + no_bar_strict, n),
        "interval_cells": interval_cells,
        "comparisons_with_an_interval_cell": ci_comparisons,
        "pct_papers_mentioning_a_test": pct(mentions_test, papers),
        "pct_papers_with_figure_caption_uncertainty": pct(fig_unc, papers),
        "pct_no_table_bar_papers_with_figure_caption_uncertainty": pct(no_bar_fig, len(no_bar_papers)),
        "table_captions_seen": captions,
        "tables_detected": detected,
        "pct_captions_not_yielding_a_table": pct(captions - detected, captions),
    }


# A coarse subfield from the title, by keyword, in this order of precedence.
# Crude, transparent, and enough to say whether the headline is a property of
# one community; a reviewer asked which subfield the failure rate describes.
TOPICS = [
    ("reinforcement learning", r"(?i)reinforcement|polic(?:y|ies)|reward|RL|agents?|robot|control|offline|imitation|bandit"),
    ("graphs and molecules", r"(?i)graph|GNN|node|molecul|protein|chemi|drug"),
    ("vision and generation", r"(?i)image|vision|visual|video|segment|detect|3D|diffusion|generat|render|point cloud|scene|pixel"),
    ("language models", r"(?i)language model|LLMs?|GPT|transformer|instruction|reasoning|prompt|token|text|alignment|RLHF|retrieval|dialogue|code generation"),
    ("theory and optimisation", r"(?i)bound|convergen|optimal|theorem|complexity|regret|minimax|convex|provabl|guarantee|sample complexity|kernel|bayesian|causal|estimation"),
]


def topic_of(title: str) -> str:
    for name, pat in TOPICS:
        if re.search(pat, title or ""):
            return name
    return "other"


def topic_breakdown(records: list, comparisons: list) -> dict:
    """The two headline figures by coarse subfield of the paper's title."""
    topic = {r["id"]: topic_of(r.get("title", "")) for r in records}
    out = {}
    for name in [t for t, _ in TOPICS] + ["other"]:
        ids = {i for i, t in topic.items() if t == name}
        cs = [c for c in comparisons if c["paper"] in ids]
        tt = [c for c in cs if c.get("test")]
        out[name] = {
            "papers": len(ids),
            "pct_papers_with_error_bar": round(100 * sum(
                1 for r in records if r["id"] in ids and r.get("reports_explicit_error_bar"))
                / max(len(ids), 1), 1),
            "comparisons": len(cs),
            "pct_neither": round(100 * sum(1 for c in cs if c["winner_dispersion"] is None
                                           and c["runner_dispersion"] is None) / max(len(cs), 1), 1),
            "pct_testable": round(100 * len(tt) / max(len(cs), 1), 1),
            "n_testable": len(tt),
            "pct_fail": round(100 * sum(1 for c in tt if not c["survives_raw"]) / max(len(tt), 1), 1),
        }
    return out


def compute(records: list, comparisons: list, pct_neither: float,
            recall_lo: float) -> dict:
    return {
        "tie_marking": tie_marking(records, comparisons),
        "checklist_justifications": checklist_justifications(records),
        "extraction_limits": extraction_limits(records),
        "filter_selection": filter_selection(records),
        "headline_with_extraction": headline_with_extraction(pct_neither, recall_lo),
        "headline_with_comparison_audit": headline_with_comparison_audit(
            pct_neither, json.load(open("out/gold_set_heldout.json", encoding="utf-8"))["no_bar"]["error_bar_truly_absent"]),
        "failure_by_gap_band": failure_by_gap_band(comparisons),
        "headline_span": headline_span(comparisons, records),
        "venue_counts": venue_counts(records, comparisons),
        "other_routes": other_routes(records, comparisons),
        "topic_breakdown": topic_breakdown(records, comparisons),
        "holm_families": holm_families(comparisons),
        "subset_direction": subset_direction(records, comparisons),
    }


def main() -> int:
    records = load_records("data/extracted_2025.jsonl")
    with open("out/analysis_2025.json", encoding="utf-8") as fh:
        comparisons = json.load(fh)["_comparisons"]
    with open("out/both_years.json", encoding="utf-8") as fh:
        pct_neither = json.load(fh)["2025"]["pct_neither"]

    # The lower end of the visual recall audit, scored from its manifest by
    # contact_sheet.py; the manifest is the one input here a reader supplies.
    with open("out/recall_v4.json", encoding="utf-8") as fh:
        recall_lo = json.load(fh)["wilson_95"][0]
    res = compute(records, comparisons, pct_neither, recall_lo=recall_lo)
    with open("out/extra_stats.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    # The conventions table reads its rows from here; it used to read a file
    # that no script regenerated.
    with open("out/headline_span.json", "w", encoding="utf-8") as fh:
        json.dump(res["headline_span"], fh, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
