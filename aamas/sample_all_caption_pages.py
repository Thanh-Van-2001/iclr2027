"""Render every page of the AAMAS corpus on which the parser detected a table
caption, with the paper's run sentences, for the reader census: the
image-based reader is the primary instrument on this format, and reads every
such page rather than a sample.

Usage: python aamas/sample_all_caption_pages.py [--out-dir audits/aamas_census]
"""
import argparse
import json
import os
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from analyze import load_records  # noqa: E402
from gold_set import RUN_SENTENCE  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extracted", default="data/extracted_aamas.jsonl")
    ap.add_argument("--out-dir", default="audits/aamas_census")
    args = ap.parse_args(argv)
    recs = load_records(args.extracted)
    img_dir = os.path.join(args.out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    items = []
    i = 0
    for r in sorted(recs, key=lambda r: r["id"]):
        pages = sorted({t.get("page") for t in r.get("tables", []) if t.get("page") is not None})
        if not pages:
            continue
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{r['id']}.pdf")
        doc = fitz.open(path)
        text = "\n".join(p.get_text() for p in doc)
        sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
        runs = "\n---\n".join(sents[:40])
        for page_no in pages:
            if page_no >= len(doc):
                continue
            i += 1
            iid = f"{i:04d}"
            doc[page_no].get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).save(os.path.join(img_dir, f"{iid}_page.png"))
            with open(os.path.join(img_dir, f"{iid}_runs.txt"), "w", encoding="utf-8") as fh:
                fh.write(runs)
            items.append({"id": iid, "paper": r["id"], "page": page_no, "title": r["title"],
                          "n_tables_detected": sum(1 for t in r["tables"] if t.get("page") == page_no)})
        doc.close()
    json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "pages from", len({it["paper"] for it in items}), "papers ->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
