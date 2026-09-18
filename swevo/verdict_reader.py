"""The printed-verdict reading: on every census page of the papers that
print a per-cell verdict of their own statistical test (the full-text
reader's markers field), the image reader lists each single-bold group with
the NAMES of the bold optimizer and of its best rival, and the verdict the
paper prints for that pair (a +/=/- symbol, a p-value, a win/tie/loss entry,
a significance mark) on the same page; and, separately, every table of test
verdicts on the page (function x competitor), so that a verdict printed on
another page can be joined to the group by function label and rival name.
Protocol tag: verdict-protocol-v1. Writes one JSON record per page.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/verdict_reader.py --shard k/n
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from read_kit_api import VENDORS, ask  # noqa: E402

KIT = "audits/swevo_census"
OUT_DIR = "audits/swevo_verdict"

PROTO = """You are reading a WHOLE PAGE of a metaheuristics paper in Scientific Reports (single-column Nature format),
rendered at twice its printed size, for an audit that compares each bold "best" cell with the statistical verdict the
paper itself prints for it. The paper reports a statistical test and prints its verdict somewhere in its tables:
+/=/- symbols (or +/~/- or w/t/l), p-values per function, "win/tie/loss" counts, rank tables, or a significance mark
such as an asterisk or a dagger.

For EVERY table of experimental results on the page record: caption_start (first words of the caption); has_bold
(y/n); groups: every group (row or column) with exactly one bold cell, up to 40, each with label (the function or
problem name, e.g. "F7" or "f12 D=30"), direction (higher/lower), winner_name (the optimizer whose cell is bold, from the
header), winner_mean, runner_name (the optimizer with the best NON-bold value in that group), runner_mean, and
verdict_here: the verdict the page prints for the bold optimizer against the runner-up on this function, exactly as
printed ("+", "=", "-", "p=0.003", "*", "n/s" ...), or "none" if nothing on this page says.

For EVERY table on the page that prints test verdicts (a Wilcoxon or Friedman table, a p-value table, a +/=/- table,
a win/tie/loss summary) record: caption_start; verdict_kind (symbols / p_values / wtl_counts / ranks / marks);
compared_against (the optimizer the verdicts are computed against, usually the proposed one); entries: up to 80 rows
of {label, competitor, verdict} where label is the function/problem, competitor the optimizer named in the column or
row, and verdict the printed symbol or value; note.

Answer with ONE JSON object and nothing else: {"results_tables": [{"caption_start": "...", "has_bold": "y",
"groups": [{"label": "...", "direction": "lower", "winner_name": "...", "winner_mean": "...", "runner_name": "...",
"runner_mean": "...", "verdict_here": "..."}]}], "verdict_tables": [{"caption_start": "...", "verdict_kind": "symbols",
"compared_against": "...", "entries": [{"label": "...", "competitor": "...", "verdict": "..."}], "note": "..."}],
"note": "..."}"""


def _parse(text: str) -> dict:
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        s = max(parts, key=len)
        if s.startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0:
        raise ValueError("no JSON object")
    s = s[i:j + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        k = s.rfind("}")
        while k > 0:
            for tail in ("]}]}", "]}", "}"):
                try:
                    return json.loads(s[:k + 1] + tail)
                except json.JSONDecodeError:
                    pass
            k = s.rfind("}", 0, k)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default=f"{OUT_DIR}/papers.txt")
    ap.add_argument("--shard", default=None)
    ap.add_argument("--model", default="gemini/gemini-3.1-pro-preview")
    ap.add_argument("--max-tokens", type=int, default=12000)
    args = ap.parse_args(argv)
    vendor = dict(VENDORS["relay"])
    vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key or not vendor["url"]:
        print("set the relay URL and key first", file=sys.stderr)
        return 2
    papers = {l.strip() for l in open(args.papers, encoding="utf-8") if l.strip()}
    items = [it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8")) if it["paper"] in papers]
    suffix = ""
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        items = items[k::n]
        suffix = f"_shard{k}"
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"labels{suffix}.json")
    pages = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else []
    done = {p["id"] for p in pages}
    for it in items:
        if it["id"] in done:
            continue
        img = os.path.join(KIT, "img", f"{it['id']}_page.png")
        ans = None
        for attempt in range(3):
            try:
                extra = {"reasoning": {"effort": "low"}} if attempt == 2 else None
                text = ask(vendor, key, img, PROTO, max_tokens=args.max_tokens, return_text=True, extra=extra, timeout=240)
                ans = _parse(text)
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  {it['id']} attempt {attempt + 1} failed: {exc}", flush=True)
        if ans is None:
            pages.append({"id": it["id"], "paper": it["paper"], "page": it["page"], "results_tables": [], "verdict_tables": [], "note": "failed"})
        else:
            pages.append({"id": it["id"], "paper": it["paper"], "page": it["page"],
                          "results_tables": ans.get("results_tables", []) if isinstance(ans, dict) else [],
                          "verdict_tables": ans.get("verdict_tables", []) if isinstance(ans, dict) else [],
                          "note": str(ans.get("note", "")) if isinstance(ans, dict) else ""})
        json.dump(pages, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"  {it['id']} {len(pages[-1]['results_tables'])} results tables, {len(pages[-1]['verdict_tables'])} verdict tables", flush=True)
    print("wrote", out, len(pages), "pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
