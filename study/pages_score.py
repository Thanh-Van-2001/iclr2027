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
from paperengine.stats import wilson_interval  # noqa: E402


def _rate(k, n, what):
    lo, hi = wilson_interval(k, n) if n else (0.0, 0.0)
    return {"correct": k, "n": n, "pct": round(100 * k / n, 1) if n else None,
            "ci": [round(100 * lo, 1), round(100 * hi, 1)], "what": what}


def _eq(a, b):
    return a is not None and b is not None and abs(float(a) - float(b)) <= 1e-9


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
    args = ap.parse_args(argv)

    items = {it["id"]: it for it in json.load(open(args.items, encoding="utf-8"))}
    pages = {p["id"]: p for p in json.load(open(args.labels, encoding="utf-8"))}
    cmps = json.load(open(args.analysis, encoding="utf-8"))["_comparisons"]
    by_page: dict = {}
    for c in cmps:
        by_page.setdefault((c["paper"], c["page"]), []).append(c)

    per_page = []
    m_g = m_n = u_g = u_n = 0   # reader groups the pipeline also has / does not
    r_groups = r_neither = r_testable = r_onebar = 0
    p_groups = p_neither = p_testable = 0
    r_found = p_found = 0
    n_tables = n_results = n_tables_bar = 0
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
                wb = _num(g.get("winner_disp")) is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = _num(g.get("runner_disp")) is not None or str(g.get("runner_disp", "")).startswith("[")
                groups.append({"w": _num(g.get("winner_mean")), "wb": wb, "rb": rb,
                               "testable": wb and rb and (n is not None or kind in ("se", "ci"))})
        pc = by_page.get((it["paper"], it["page"]), [])
        page = {"id": iid, "n_groups": len(groups),
                "neither": sum(1 for g in groups if not g["wb"] and not g["rb"]),
                "testable": sum(1 for g in groups if g["testable"]),
                "pipe_groups": len(pc),
                "pipe_neither": sum(1 for c in pc if c["winner_dispersion"] is None and c["runner_dispersion"] is None),
                "pipe_testable": sum(1 for c in pc if c.get("test"))}
        per_page.append(page)
        r_groups += page["n_groups"]; r_neither += page["neither"]; r_testable += page["testable"]
        r_onebar += sum(1 for g in groups if g["wb"] != g["rb"])
        p_groups += page["pipe_groups"]; p_neither += page["pipe_neither"]; p_testable += page["pipe_testable"]
        for g in groups:
            if any(_eq(g["w"], c["winner"]) for c in pc):
                m_g += 1; m_n += (not g["wb"] and not g["rb"])
            else:
                u_g += 1; u_n += (not g["wb"] and not g["rb"])
        r_found += sum(1 for g in groups if any(_eq(g["w"], c["winner"]) for c in pc))
        p_found += sum(1 for c in pc if any(_eq(g["w"], c["winner"]) for g in groups))
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
    out = {
        "corpus_one_page_per_paper": {"pct_neither": round(sum(nei) / len(nei), 1),
                                      "pct_testable": round(sum(tes) / len(tes), 1)},
        "reader_groups_matched": {"groups": m_g, "pct_neither": round(100 * m_n / m_g, 1) if m_g else None},
        "reader_groups_unmatched": {"groups": u_g, "pct_neither": round(100 * u_n / u_g, 1) if u_g else None},
        "n_pages": len(per_page),
        "n_tables_listed": n_tables, "n_results_tables": n_results,
        "pct_results_tables_with_any_bar": round(100 * n_tables_bar / n_results, 1) if n_results else None,
        "reader": {"groups": r_groups,
                   "pct_neither": round(100 * r_neither / r_groups, 1) if r_groups else None,
                   "ci_neither": _boot(per_page, "neither"),
                   "pct_one_side": round(100 * r_onebar / r_groups, 1) if r_groups else None,
                   "pct_testable": round(100 * r_testable / r_groups, 1) if r_groups else None,
                   "ci_testable": _boot(per_page, "testable")},
        "pipeline_same_pages": {"groups": p_groups,
                                "pct_neither": round(100 * p_neither / p_groups, 1) if p_groups else None,
                                "pct_testable": round(100 * p_testable / p_groups, 1) if p_groups else None},
        "reader_groups_found_by_pipeline": _rate(r_found, r_groups, "reader groups whose winner the pipeline also has on that page"),
        "pipeline_groups_found_by_reader": _rate(p_found, p_groups, "pipeline comparisons whose winner the reader also lists"),
        "per_page": per_page,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_page"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
