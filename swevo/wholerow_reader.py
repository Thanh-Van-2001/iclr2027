"""One question, asked after review, for every census table the reader filed
as column-oriented (each column holds exactly one bold cell, which is what a
whole bold row produces): do all of this table's bold cells lie in one row,
or in one column, and which label does that row or column carry? The
answer separates a proposed method's row set in bold from column-wise
winners, which the census protocol does not distinguish. Reads the census
page images with the same relay model as the census; writes
audits/swevo_census_cols/labels.json, one record per table.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/wholerow_reader.py [--shard k/n] [--model gemini/gemini-3.1-pro-preview]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from read_kit_api import VENDORS, ask  # noqa: E402

KIT = "audits/swevo_census"
OUT = "audits/swevo_census_cols"
PROMPT = """The image is a WHOLE PAGE of a paper, rendered at twice its printed size, with nothing marked. For each table listed below (by the first words of its caption), look at every BOLD numeric cell of the table's body and answer:
- all_bold_in_one_row: y if every bold cell of the table lies in a single row (for example a proposed method's whole row set in bold, or a header row of numbers), n otherwise;
- row_label: if y, the label of that row (the method or header name), else none;
- all_bold_in_one_column: y if every bold cell lies in a single column, n otherwise;
- bold_cells: the number of bold numeric cells you count in the table's body (an integer, or "many" if more than forty);
- note: one short sentence.

Tables on this page:
{tables}

Answer with ONE JSON object and nothing else: {{"tables": [{{"caption_start": "...", "all_bold_in_one_row": "y", "row_label": "...", "all_bold_in_one_column": "n", "bold_cells": 12, "note": "..."}}]}}"""


def _loads_ok(o: str) -> bool:
    try:
        json.loads(o)
        return True
    except json.JSONDecodeError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", default=None, help="k/n")
    ap.add_argument("--model", default="gemini/gemini-3.1-pro-preview")
    args = ap.parse_args(argv)
    vendor = dict(VENDORS["relay"])
    vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key or not vendor["url"]:
        print("set the relay URL and key first", file=sys.stderr)
        return 2
    labs = json.load(open(os.path.join(KIT, "labels_corrected.json"), encoding="utf-8"))
    pages = []
    for pg in labs:
        ts = [t for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y")
              and str(t.get("orientation", "")).lower().strip() == "column" and t.get("groups")]
        if ts:
            pages.append((pg["id"], [str(t.get("caption_start", ""))[:80] for t in ts]))
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        pages = pages[k::n]
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"labels_shard{args.shard.replace('/', 'of') if args.shard else 'all'}.json")
    done = {}
    if os.path.exists(out):
        done = {r["id"]: r for r in json.load(open(out, encoding="utf-8"))}
    rows = list(done.values())
    for i, (pid, caps) in enumerate(pages, 1):
        if pid in done and done[pid].get("tables"):
            continue
        img = os.path.join(KIT, "img", f"{pid}_page.png")
        text = PROMPT.format(tables="\n".join(f"- {c}" for c in caps).replace('"', "'"))
        try:
            raw = ask(vendor, key, img, text, max_tokens=8000, return_text=True, timeout=300)
            m = re.search(r"\{.*\}", raw, re.S)
            try:
                ans = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError:
                # a truncated answer: keep every complete table object
                objs = re.findall(r"\{[^{}]*\"caption_start\"[^{}]*\}", raw, re.S)
                ans = {"tables": [json.loads(o) for o in objs if o.strip().endswith("}") and _loads_ok(o)]}
            rec = {"id": pid, "captions": caps, "tables": ans.get("tables", []), "model": args.model, "protocol": "wholerow-question-v1"}
            if not rec["tables"]:
                rec["raw"] = raw[:600]
        except Exception as exc:  # noqa: BLE001
            rec = {"id": pid, "captions": caps, "tables": [], "error": str(exc)[:200], "model": args.model, "protocol": "wholerow-question-v1"}
        done[pid] = rec
        rows = list(done.values())
        json.dump(rows, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"  {i}/{len(pages)} {pid}: {[t.get('all_bold_in_one_row') for t in rec['tables']]}", flush=True)
    print("wrote", out, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
