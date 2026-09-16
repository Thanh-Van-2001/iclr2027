"""The metric label of every candidate rate comparison, read from the PDF
text layer: the row label to the left of the winner cell and the column
header above it. Section 6 needs the GROUP to be a rate, not merely its
table; the table-level filter admitted time, cost and return columns of
tables whose caption named a success rate (a reviewer's finding).

A filter on the parser's output, not a change to it: the parser's cells are
untouched, and the labels are looked up around the coordinates it recorded.

Usage: python aamas/rate_labels.py   (needs data/corpus; writes
       out/aamas/rate_group_labels.json, which make_all_aamas.py consults)
"""
import json
import os
import re
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from analyze import load_records  # noqa: E402

OUT = "out/aamas/rate_group_labels.json"
# the table-level candidate set: any table whose caption or header names a rate
TABLE_RATE = re.compile(r"win(?:ning)?[\s-]?rate|success[\s-]?rate|winrate|success \(?%|solved|solve[\s-]?rate|completion rate|win %", re.I)
NUM = re.compile(r"^[\s$]*[-+]?\d[\d.,]*\s*(%|\\%)?[\s$]*$")


def key(c: dict) -> str:
    return f"{c['paper']}|{c['table']}|{c['page']}|{c['winner_cell']['x']}|{c['winner_cell']['y']}"


def _spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                t = sp["text"].strip()
                if t:
                    x0, y0, x1, y1 = sp["bbox"]
                    out.append({"text": t, "x0": x0, "x1": x1, "y0": y0, "y1": y1, "yc": (y0 + y1) / 2})
    return out


def labels_for(c: dict, spans: list, table_cells: list) -> dict:
    wx, wy = c["winner_cell"]["x"], c["winner_cell"]["y"]
    bb = c["bbox"]
    cell_ys = sorted({round(cell["y"], 1) for cell in table_cells})
    first_y = cell_ys[0] if cell_ys else bb["y_min"]
    x_first = min((cell["x"] for cell in table_cells), default=bb["x_min"])
    # row label: the non-numeric spans on the winner's line to its left (the
    # parser's y is the span's top edge)
    row = [s for s in spans if abs(s["y0"] - wy) <= 3 and s["x0"] < wx and not NUM.match(s["text"])
           and s["x0"] >= bb["x_min"] - 20]
    row.sort(key=lambda s: s["x0"])
    # column and block headers: the nearest non-numeric spans above the
    # winner's line whose x-range covers the winner cell, within the table's
    # width and up to forty points above its body (a block header such as
    # "episode return" sits mid-table, a column header above it)
    above = [s for s in spans if first_y - 40 <= s["y0"] < wy - 2 and s["x0"] - 6 <= wx + 12 <= s["x1"] + 6
             and s["x0"] >= bb["x_min"] - 10 and s["x1"] <= bb["x_max"] + 10 and not NUM.match(s["text"])]
    above.sort(key=lambda s: -s["y0"])
    col = above[:3]
    col.sort(key=lambda s: s["y0"])
    return {"row_label": " ".join(s["text"] for s in row)[:120], "col_header": " ".join(s["text"] for s in col)[:160]}


def main():
    recs = {r["id"]: r for r in load_records("data/extracted_aamas.jsonl")}
    cs = json.load(open("out/aamas/analysis.json", encoding="utf-8"))["_comparisons"]
    cand = [c for c in cs if TABLE_RATE.search(f"{c.get('caption', '')} {c.get('header_text', '')}")]
    out = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    docs = {}
    for c in cand:
        k = key(c)
        if k in out:
            continue
        r = recs[c["paper"]]
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{c['paper']}.pdf")
        if not os.path.exists(path):
            continue
        if path not in docs:
            docs[path] = fitz.open(path)
        page = docs[path][c["page"]]
        spans = _spans(page)
        cells = []
        for t in r["tables"]:
            if t.get("number") == c["table"] and t.get("page") == c["page"]:
                cells = t["cells"]
                if any(abs(cell["x"] - c["winner_cell"]["x"]) < 0.2 and abs(cell["y"] - c["winner_cell"]["y"]) < 0.2 for cell in cells):
                    break
        out[k] = labels_for(c, spans, cells)
        out[k]["paper"] = c["paper"]
        out[k]["orientation"] = c["orientation"]
        out[k]["direction"] = c["direction"]
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(len(cand), "candidate comparisons,", len(out), "labelled")


if __name__ == "__main__":
    main()
