"""Render every caption page of a fixed random subset of the open-access
corpus for the reader census. The subset size (500 papers) was fixed in
swevo/PLAN.md before any page was read; the draw is seeded and reproducible
from the parsed corpus.

Usage: python swevo/census_kit.py [--n-papers 500] [--seed 2026]
       [--extracted data/extracted_oa.jsonl] [--out-dir audits/swevo_census]
"""
import argparse
import json
import os
import random
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from analyze import load_records  # noqa: E402
from gold_set import RUN_SENTENCE  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extracted", default="data/extracted_oa.jsonl")
    ap.add_argument("--corpus", default="data/corpus_oa")
    ap.add_argument("--out-dir", default="audits/swevo_census")
    ap.add_argument("--n-papers", type=int, default=500)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--max-pages-per-paper", type=int, default=0, help="0 means every caption page")
    args = ap.parse_args(argv)
    recs = [r for r in load_records(args.extracted)
            if any(t.get("page") is not None for t in r.get("tables", []))]
    recs.sort(key=lambda r: r["id"])
    eligible = len(recs)
    if args.n_papers and args.n_papers < len(recs):
        recs = random.Random(args.seed).sample(recs, args.n_papers)
        recs.sort(key=lambda r: r["id"])
    img_dir = os.path.join(args.out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    items = []
    i = 0
    for r in recs:
        pages = sorted({t.get("page") for t in r.get("tables", []) if t.get("page") is not None})
        if args.max_pages_per_paper:
            pages = pages[:args.max_pages_per_paper]
        path = os.path.join(args.corpus, f"{r['venue']}{r['year']}_{r['id']}.pdf")
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
    json.dump({"n_papers": args.n_papers, "seed": args.seed, "papers_eligible": eligible, "papers_drawn": len(recs),
               "protocol": "census-protocol-v1 with bar_form separate_row (swevo)"},
              open(os.path.join(args.out_dir, "draw.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "pages from", len({it["paper"] for it in items}), "papers ->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
