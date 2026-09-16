"""Score the end-to-end page reading against the pipeline on the same pages.

From the reader's labels alone: the share of single-bold groups with no error
bar on either side, and the share testable (both bars and a run count, or bars
that are standard errors or intervals). From the pipeline: the same two shares
over its comparisons on the same pages, and the overlap of the two sets of
groups matched by the winner's printed value. Intervals resample pages.

Usage: python study/pages_score.py --items audits/gold_f/items.json
       --labels audits/gold_f/labels.json --analysis out/analysis_2025.json
       --out out/gold_set_pages.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from gold_set import _num  # noqa: E402
from analyze import p_value  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402


def _bar_num(x):
    """The reader writes a bar as printed: "0.7", "+/-0.7", "(+/-18)", "[0.048]".
    Strip the sign and the brackets before parsing; an earlier version parsed
    only the bare number and counted every "+/-0.7" as no bar at all, which a
    reviewer of the AAMAS study caught."""
    if x is None:
        return None
    s = str(x).strip().strip("()[]").strip()
    for pre in ("±", "+/-", "+-"):
        if s.startswith(pre):
            s = s[len(pre):].strip()
    return _num(s)


def _se(disp, kind, n):
    """Standard error of one arm from the reader's bar and the caption's kind."""
    d = _bar_num(disp)
    if d is None:
        return None
    if kind == "se":
        return d
    if kind == "ci":
        return d / 1.96
    # a deviation, or an unlabelled bar read as one, needs the run count
    return d / (n ** 0.5) if n else None


def _rate(k, n, what):
    lo, hi = wilson_interval(k, n) if n else (0.0, 0.0)
    return {"correct": k, "n": n, "pct": round(100 * k / n, 1) if n else None,
            "ci": [round(100 * lo, 1), round(100 * hi, 1)], "what": what}


def _eq(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) <= 1e-9


def _boot_papers(per_page, key, reps=2000, seed=0):
    """The same interval resampling papers rather than pages, for a census
    that reads several pages of one paper."""
    rng = random.Random(seed)
    by = {}
    for p in per_page:
        if p["n_groups"]:
            by.setdefault(p.get("paper"), []).append(p)
    papers = list(by.values())
    vals = []
    for _ in range(reps):
        draw = [papers[rng.randrange(len(papers))] for _ in papers]
        num = sum(p[key] for pp in draw for p in pp)
        den = sum(p["n_groups"] for pp in draw for p in pp)
        vals.append(100 * num / den if den else 0)
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def _boot(per_page, key, reps=2000, seed=0):
    rng = random.Random(seed)
    pages = [p for p in per_page if p["n_groups"]]
    vals = []
    for _ in range(reps):
        draw = [pages[rng.randrange(len(pages))] for _ in pages]
        num = sum(p[key] for p in draw)
        den = sum(p["n_groups"] for p in draw)
        vals.append(100 * num / den if den else 0)
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="audits/gold_f/items.json")
    ap.add_argument("--labels", default="audits/gold_f/labels.json")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--out", default="out/gold_set_pages.json")
    ap.add_argument("--extremal-only", action="store_true",
                    help="drop reader groups whose bold cell is not the better value in the stated direction, "
                         "or ties its rival, as the parser's rules do (the AAMAS study's unit)")
    args = ap.parse_args(argv)

    items = {it["id"]: it for it in json.load(open(args.items, encoding="utf-8"))}
    pages = {p["id"]: p for p in json.load(open(args.labels, encoding="utf-8"))}
    cmps = json.load(open(args.analysis, encoding="utf-8"))["_comparisons"]
    by_page: dict = {}
    for c in cmps:
        by_page.setdefault((c["paper"], c["page"]), []).append(c)

    per_page = []
    shared, reader_only, pipe_only = [], [], []
    m_g = m_n = u_g = u_n = 0   # reader groups the pipeline also has / does not
    pm_g = [0, 0, 0]            # parser comparisons the reader also lists: n, bar-less, testable
    r_groups = r_neither = r_testable = r_onebar = 0
    p_groups = p_neither = p_testable = 0
    r_found = p_found = 0
    p_unconfirmed = p_unconfirmed_neither = 0
    p_found_testable = p_testable_total = 0
    n_tables = n_results = n_tables_bar = 0
    n_nonextremal = 0
    for iid, it in sorted(items.items()):
        pg = pages.get(iid)
        if pg is None:
            continue
        groups = []
        for t in pg.get("tables", []):
            n_tables += 1
            if not t.get("results_table", "").lower().startswith("y"):
                continue
            n_results += 1
            n_tables_bar += t.get("any_error_bar", "").lower().startswith("y")
            kind = t.get("bar_kind", "").lower()
            n = _num(t.get("n_runs"))
            for g in t.get("groups", []):
                if args.extremal_only:
                    w_, r_ = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                    d_ = str(g.get("direction", "")).lower()
                    if w_ is not None and r_ is not None and (
                            w_ == r_ or (d_.startswith("low") and w_ > r_) or (d_.startswith("high") and w_ < r_)):
                        n_nonextremal += 1
                        continue
                wb = _bar_num(g.get("winner_disp")) is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = _bar_num(g.get("runner_disp")) is not None or str(g.get("runner_disp", "")).startswith("[")
                testable = wb and rb and (n is not None or kind in ("se", "ci"))
                fail = None
                if testable:
                    w, r = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                    sw, sr = _se(g.get("winner_disp"), kind, n), _se(g.get("runner_disp"), kind, n)
                    if None not in (w, r, sw, sr):
                        res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                        fail = (res["p"] >= 0.05) if res else None
                fail_se = None
                if testable and kind not in ("se", "ci"):
                    # the same group with an unlabelled or SD bar read as a
                    # standard error (the parser's Table 3 sensitivity)
                    w, r = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                    sw, sr = _bar_num(g.get("winner_disp")), _bar_num(g.get("runner_disp"))
                    if None not in (w, r, sw, sr):
                        res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                        fail_se = (res["p"] >= 0.05) if res else None
                groups.append({"w": _num(g.get("winner_mean")), "wb": wb, "rb": rb,
                               "testable": testable, "fail": fail, "paper": it["paper"],
                               "kind": kind, "n": n, "fail_se": fail_se,
                               "bars_no_n": wb and rb and n is None and kind not in ("se", "ci")})
        pc = by_page.get((it["paper"], it["page"]), [])
        page = {"id": iid, "paper": it["paper"], "n_groups": len(groups),
                "neither": sum(1 for g in groups if not g["wb"] and not g["rb"]),
                "testable": sum(1 for g in groups if g["testable"]),
                "pipe_groups": len(pc),
                "pipe_neither": sum(1 for c in pc if c["winner_dispersion"] is None and c["runner_dispersion"] is None),
                "pipe_testable": sum(1 for c in pc if c.get("test"))}
        page["tested_groups"] = [g for g in groups if g["testable"] and g["fail"] is not None]
        page["testable_unreadable"] = sum(1 for g in groups if g["testable"] and g["fail"] is None)
        # a shaded band in a figure on the same page: evidence the table's
        # bar-less cells may have elsewhere on the page
        page["figure_band"] = str(pg.get("figure_band_on_page", "")).lower().startswith("y")
        page["bars_no_n"] = sum(1 for g in groups if g["bars_no_n"])
        per_page.append(page)
        r_groups += page["n_groups"]; r_neither += page["neither"]; r_testable += page["testable"]
        r_onebar += sum(1 for g in groups if g["wb"] != g["rb"])
        p_groups += page["pipe_groups"]; p_neither += page["pipe_neither"]; p_testable += page["pipe_testable"]
        # One-to-one matching on the winner's value: a parser comparison can
        # vouch for at most one reader group and vice versa. Matching on the
        # value alone credited nine reader groups to two parser comparisons
        # on a page of repeated values (a reviewer of the AAMAS study).
        used = set()
        matched_ids = set()
        for gi, g in enumerate(groups):
            for ci, c in enumerate(pc):
                if ci not in used and _eq(g["w"], c["winner"]):
                    used.add(ci); matched_ids.add(gi)
                    break
        for gi, g in enumerate(groups):
            if gi in matched_ids:
                m_g += 1; m_n += (not g["wb"] and not g["rb"])
            else:
                u_g += 1; u_n += (not g["wb"] and not g["rb"])
        # verdicts on the same pages, on the one-to-one matching: groups both
        # instruments test, and the ones only one of them can. An earlier
        # version matched on the first value hit and lost 22 parser-testable
        # comparisons between the two lists (a reviewer's reconciliation).
        pair = {}
        used_list = []
        for gi, g in enumerate(groups):
            for ci, c in enumerate(pc):
                if ci not in used_list and _eq(g["w"], c["winner"]):
                    used_list.append(ci); pair[gi] = ci
                    break
        for gi, g in enumerate(groups):
            c = pc[pair[gi]] if gi in pair else None
            if g["fail"] is not None and c is not None and c.get("test"):
                shared.append((g["fail"], c["test"]["p"] >= 0.05))
            elif g["fail"] is not None:
                reader_only.append(g["fail"])
            elif c is not None and c.get("test"):
                pipe_only.append(c["test"]["p"] >= 0.05)
        for ci, c in enumerate(pc):
            if ci not in used_list and c.get("test"):
                pipe_only.append(c["test"]["p"] >= 0.05)
        # the parser's comparisons the reader confirms: their own shares
        for ci in used:
            c = pc[ci]
            pm_g[0] += 1
            pm_g[1] += (c["winner_dispersion"] is None and c["runner_dispersion"] is None)
            pm_g[2] += bool(c.get("test"))
        r_found += len(matched_ids)
        p_found += len(used)
        p_found_testable += sum(1 for ci in used if pc[ci].get("test"))
        p_testable_total += sum(1 for c in pc if c.get("test"))
        page["found"] = len(matched_ids)
        # the parser's groups the reader does not list, and how many of them
        # carry no bar: the false positives' contribution to the census
        for ci, c in enumerate(pc):
            if ci not in used:
                p_unconfirmed += 1
                p_unconfirmed_neither += (c["winner_dispersion"] is None and c["runner_dispersion"] is None)
    # The corpus weighted as the page draw is: one page with comparisons per
    # paper, pooled, averaged over draws.
    by_paper: dict = {}
    for (paper, page), cs in by_page.items():
        by_paper.setdefault(paper, []).append(cs)
    rng = random.Random(0)
    nei, tes = [], []
    for _ in range(200):
        g = n_ = t_ = 0
        for cs_list in by_paper.values():
            cs = cs_list[rng.randrange(len(cs_list))]
            g += len(cs)
            n_ += sum(1 for c in cs if c["winner_dispersion"] is None and c["runner_dispersion"] is None)
            t_ += sum(1 for c in cs if c.get("test"))
        nei.append(100 * n_ / g); tes.append(100 * t_ / g)
    # the reader's own verdicts, with an interval that resamples papers
    tested = [g for p_ in per_page for g in p_.get("tested_groups", [])]
    by_pp: dict = {}
    for g in tested:
        by_pp.setdefault(g["paper"], []).append(g["fail"])
    reader_failure = None
    if tested:
        papers_ = list(by_pp.values())
        rng2 = random.Random(1)
        bvals = []
        for _ in range(2000):
            draw = [papers_[rng2.randrange(len(papers_))] for _ in papers_]
            flat = [x for pp in draw for x in pp]
            bvals.append(100 * sum(flat) / len(flat))
        bvals.sort()
        reader_failure = {"n": len(tested), "n_papers": len(papers_),
                          "pct_fail": round(100 * sum(g["fail"] for g in tested) / len(tested), 1),
                          "ci": [round(bvals[50], 1), round(bvals[1949], 1)]}
    # sensitivities on the reader's own verdicts
    se_tested = [g for g in tested if g["fail_se"] is not None]
    small_n = [g for g in tested if not (g["n"] is not None and g["n"] > 30)]
    reader_sens = {
        "unlabelled_or_sd_as_se": {"n": len(se_tested),
                                   "pct_fail": round(100 * sum(g["fail_se"] for g in se_tested) / len(se_tested), 1) if se_tested else None},
        "bar_kinds_tested": dict(__import__("collections").Counter(g["kind"] or "unlabelled" for g in tested)),
        "run_count_above_30": {"n": sum(1 for g in tested if g["n"] is not None and g["n"] > 30),
                               "papers": len({g["paper"] for g in tested if g["n"] is not None and g["n"] > 30}),
                               "pct_fail": round(100 * sum(g["fail"] for g in tested if g["n"] is not None and g["n"] > 30) /
                                                 max(sum(1 for g in tested if g["n"] is not None and g["n"] > 30), 1), 1)},
        "without_run_count_above_30": {"n": len(small_n),
                                       "pct_fail": round(100 * sum(g["fail"] for g in small_n) / len(small_n), 1) if small_n else None},
        "testable_unreadable_values": sum(p_["testable_unreadable"] for p_ in per_page),
        "testable_papers": len({p_["paper"] for p_ in per_page if p_["testable"]}),
    }
    out = {
        "reader_failure": reader_failure,
        "reader_sensitivity": reader_sens,
        "verdicts_same_pages": {
            "shared": {"n": len(shared), "reader_fails": sum(1 for a, b in shared if a),
                       "pipeline_fails": sum(1 for a, b in shared if b),
                       "agree": sum(1 for a, b in shared if a == b),
                       "both_fail": sum(1 for a, b in shared if a and b),
                       "pipeline_fails_reader_survives": sum(1 for a, b in shared if b and not a),
                       "reader_fails_pipeline_survives": sum(1 for a, b in shared if a and not b)},
            "reader_only": {"n": len(reader_only), "fails": sum(reader_only)},
            "pipeline_only": {"n": len(pipe_only), "fails": sum(pipe_only)},
        },
        "corpus_one_page_per_paper": {"pct_neither": round(sum(nei) / len(nei), 1),
                                      "pct_testable": round(sum(tes) / len(tes), 1)},
        "reader_groups_matched": {"groups": m_g, "pct_neither": round(100 * m_n / m_g, 1) if m_g else None},
        "pipeline_groups_matched": {"groups": pm_g[0], "pct_neither": round(100 * pm_g[1] / pm_g[0], 1) if pm_g[0] else None,
                                    "pct_testable": round(100 * pm_g[2] / pm_g[0], 1) if pm_g[0] else None},
        "reader_groups_unmatched": {"groups": u_g, "pct_neither": round(100 * u_n / u_g, 1) if u_g else None},
        "n_pages": len(per_page),
        "n_tables_listed": n_tables, "n_results_tables": n_results,
        "reader_groups_dropped_nonextremal": n_nonextremal,
        "pct_results_tables_with_any_bar": round(100 * n_tables_bar / n_results, 1) if n_results else None,
        "reader": {"groups": r_groups,
                   "pct_neither": round(100 * r_neither / r_groups, 1) if r_groups else None,
                   "ci_neither": _boot(per_page, "neither"),
                   "pct_one_side": round(100 * r_onebar / r_groups, 1) if r_groups else None,
                   "pct_testable": round(100 * r_testable / r_groups, 1) if r_groups else None,
                   "n_testable": r_testable,
                   "pct_bars_no_n": round(100 * sum(p_["bars_no_n"] for p_ in per_page) / r_groups, 1) if r_groups else None,
                   "pct_neither_on_banded_page": round(100 * sum(p_["neither"] for p_ in per_page if p_["figure_band"]) / r_neither, 1) if r_neither else None,
                   "pages_with_groups_and_band": sum(1 for p_ in per_page if p_["n_groups"] and p_["figure_band"]),
                   "ci_testable": _boot(per_page, "testable"),
                   "ci_neither_papers": _boot_papers(per_page, "neither"),
                   "ci_testable_papers": _boot_papers(per_page, "testable"),
                   "papers_with_groups": len({p["paper"] for p in per_page if p["n_groups"]})},
        "pipeline_same_pages": {"groups": p_groups,
                                "pct_neither": round(100 * p_neither / p_groups, 1) if p_groups else None,
                                "pct_testable": round(100 * p_testable / p_groups, 1) if p_groups else None},
        "reader_groups_found_by_pipeline": dict(_rate(r_found, r_groups, "reader groups whose winner the pipeline also has on that page"),
                                                page_ci=_boot(per_page, "found")),
        "pipeline_groups_found_by_reader": _rate(p_found, p_groups, "pipeline comparisons whose winner the reader also lists"),
        "pipeline_testable_found_by_reader": _rate(p_found_testable, p_testable_total, "pipeline testable comparisons whose winner the reader also lists"),
        "pipeline_groups_unconfirmed": {"n": p_unconfirmed, "neither": p_unconfirmed_neither,
                                        "pct_neither": round(100 * p_unconfirmed_neither / p_unconfirmed, 1) if p_unconfirmed else None},
        "per_page": per_page,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_page"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
