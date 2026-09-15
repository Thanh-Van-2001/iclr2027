"""End-to-end reading of whole pages by an API model: every results table on
the page, every single-bold group, its bars and run count, under the same
protocol the random-page reader followed. Writes labels.json in the shape
pages_score.py reads.

Usage: RELAY_URL=... RELAY_API_KEY=... python study/read_pages_api.py --kit audits/aamas_testable_pages
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from read_kit_api import VENDORS, ask  # noqa: E402

PROTO = """You are the end-to-end reader for a paper that audits results tables. The image is a WHOLE PAGE of a
multi-agent-systems paper (two-column ACM format), rendered at twice its printed size, with nothing marked.

List every table of experimental results whose body is on the page (ignore tables of hyperparameters, dataset
statistics, notation, prompts). For each such table record: caption_start (the first words of its caption);
results_table (y/n); orientation (the grouping it marks winners within: "column" if each column holds one bold
cell, "row" if each row does, "none" if no cell is bold or bold marks something other than a single winner per
group, e.g. every cell bold); any_error_bar (y/n: does ANY cell print a dispersion, a +/- value, a parenthesised
or subscript value, a bracketed interval, or a separate std/SE column); bar_kind (sd / se / ci / unlabelled if
bars exist but nothing says what they are / none if no bars, from the caption); n_runs (the run count that
applies to this table, from its caption first and otherwise from the run sentences below, or "none"); n_source
(caption / page / paper / none); groups: EVERY group with exactly one bold cell (up to 40), each with label (its
header label), direction (higher/lower), winner_mean, winner_disp, runner_mean, runner_disp (the bold cell's
mean and bar, and the best NON-bold cell's mean and bar in that group; values exactly as printed; "none" for a
value with no bar; "unclear" if you cannot read a digit); note.

Run sentences from the paper:
{runs}

Answer with ONE JSON object and nothing else: {{"tables": [{{"caption_start": "...", "results_table": "y",
"orientation": "column", "any_error_bar": "y", "bar_kind": "sd", "n_runs": "5", "n_source": "caption",
"groups": [{{"label": "...", "direction": "higher", "winner_mean": "...", "winner_disp": "...",
"runner_mean": "...", "runner_disp": "..."}}], "note": "..."}}], "note": "..."}}"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", default="relay", choices=sorted(VENDORS))
    ap.add_argument("--model", default=None)
    ap.add_argument("--kit", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    vendor = dict(VENDORS[args.vendor])
    if args.model:
        vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key or not vendor["url"]:
        print("set the relay URL and key first", file=sys.stderr)
        return 2
    out = args.out or os.path.join(args.kit, "labels.json")
    items = json.load(open(os.path.join(args.kit, "items.json"), encoding="utf-8"))
    pages = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else []
    done = {p["id"] for p in pages}
    for it in items:
        if it["id"] in done:
            continue
        img = os.path.join(args.kit, "img", f"{it['id']}_page.png")
        runs_path = os.path.join(args.kit, "img", f"{it['id']}_runs.txt")
        runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else "(none)"
        try:
            ans = ask(vendor, key, img, PROTO.format(runs=runs[:6000]))
        except Exception as exc:  # noqa: BLE001
            print(f"  {it['id']} failed: {exc}", flush=True)
            ans = {"tables": [], "note": f"failed: {exc}"}
        tables = ans.get("tables", []) if isinstance(ans, dict) else []
        for t in tables:
            t.setdefault("groups", [])
            for k in ("caption_start", "results_table", "orientation", "any_error_bar", "bar_kind", "n_runs", "n_source", "note"):
                t[k] = str(t.get(k, "")).strip()
            for g in t["groups"]:
                for k in ("label", "direction", "winner_mean", "winner_disp", "runner_mean", "runner_disp"):
                    g[k] = str(g.get(k, "")).strip()
        pages.append({"id": it["id"], "tables": tables, "note": str(ans.get("note", "")) if isinstance(ans, dict) else ""})
        json.dump(pages, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"  {it['id']} {len(tables)} tables, {sum(len(t['groups']) for t in tables)} groups", flush=True)
    print("wrote", out, len(pages), "pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
