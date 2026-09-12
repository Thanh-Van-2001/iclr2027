"""Score the unanchored reading of the frozen set against the pipeline.

The anchored reading marks the pipeline's chosen cell; here the reader listed
every single-bold group it could find in the same crop, unaided. Two things
are measured: whether the pipeline's chosen claim appears among the reader's
groups with the same rival (the anchoring control), and how the sets of groups
compare in both directions (the pipeline choosing a wrong group, or missing
one, which a boxed reading cannot see).

Usage: python study/nobox_score.py --items audits/gold_d/items.json
       --labels audits/gold_d_nobox/labels.json --analysis out/analysis_2025.json
       --out out/gold_set_nobox.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from gold_set import _num  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402


def _rate(k: int, n: int, what: str) -> dict:
    lo, hi = wilson_interval(k, n) if n else (0.0, 0.0)
    return {"correct": k, "n": n, "pct": round(100 * k / n, 1) if n else None,
            "ci": [round(100 * lo, 1), round(100 * hi, 1)], "what": what}


def _eq(a, b, tol: float = 1e-9) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="audits/gold_d/items.json")
    ap.add_argument("--labels", default="audits/gold_d_nobox/labels.json")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--out", default="out/gold_set_nobox.json")
    args = ap.parse_args(argv)

    items = {it["id"]: it for it in json.load(open(args.items, encoding="utf-8")) if it["stratum"] == "testable"}
    rows = {r["id"]: r for r in json.load(open(args.labels, encoding="utf-8"))}
    cmps = json.load(open(args.analysis, encoding="utf-8"))["_comparisons"]
    by_table: dict = {}
    for c in cmps:
        by_table.setdefault((c["paper"], c["table"], c["page"]), []).append(c)

    n = 0
    winner_found = rival_same = orient_same = 0
    reader_empty = 0
    pipe_groups = pipe_found = reader_groups = reader_found = 0
    per_item = []
    for iid, it in sorted(items.items()):
        r = rows.get(iid)
        if r is None:
            continue
        n += 1
        groups = r.get("groups") or []
        if not groups:
            reader_empty += 1
        p = it["pipeline"]
        hit = next((g for g in groups if _eq(_num(g["winner_mean"]), p["winner"])), None)
        if hit is not None:
            winner_found += 1
            if _eq(_num(hit["runner_mean"]), p["runner_up"]):
                rival_same += 1
        if r.get("orientation", "").lower().startswith(p["orientation"][:3]):
            orient_same += 1
        # group sets for the whole table
        tcs = by_table.get((it["paper"], it["table"], it["page"]), [])
        pipe_groups += len(tcs)
        pipe_found += sum(1 for c in tcs if any(_eq(_num(g["winner_mean"]), c["winner"]) for g in groups))
        reader_groups += len(groups)
        reader_found += sum(1 for g in groups if any(_eq(_num(g["winner_mean"]), c["winner"]) for c in tcs))
        per_item.append({"id": iid, "reader_groups": len(groups), "pipeline_groups": len(tcs),
                         "winner_found": hit is not None,
                         "rival_same": bool(hit is not None and _eq(_num(hit["runner_mean"]), p["runner_up"]))})
    out = {
        "n": n,
        "reader_lists_no_single_bold_group": reader_empty,
        "pipeline_winner_among_reader_groups": _rate(winner_found, n, "the pipeline's bold cell is a single-bold group's winner for the unanchored reader"),
        "same_rival_given_winner_found": _rate(rival_same, winner_found, "and the reader's best non-bold cell is the pipeline's rival"),
        "claim_recovered_unanchored": _rate(rival_same, n, "pipeline's winner and rival both recovered without the box"),
        "orientation_agreement": _rate(orient_same, n, "same grouping"),
        "pipeline_groups_found_by_reader": _rate(pipe_found, pipe_groups, "pipeline comparisons in these tables whose winner the reader also lists"),
        "reader_groups_found_by_pipeline": _rate(reader_found, reader_groups, "reader groups whose winner the pipeline also has"),
        "per_item": per_item,
    }
    json.dump(out, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_item"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
