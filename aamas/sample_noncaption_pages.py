"""Render a random sample of pages on which the parser detected NO table
caption, from every paper of the corpus, so the census reader can say how
many results tables with single-bold groups sit where the parser never
looked: the recall of caption detection on the ACM two-column format.

Usage: python aamas/sample_noncaption_pages.py [--n 100] [--out-dir audits/aamas_noncaption]
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
    ap.add_argument("--extracted", default="data/extracted_aamas.jsonl")
    ap.add_argument("--out-dir", default="audits/aamas_noncaption")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20260916)
    args = ap.parse_args(argv)
    recs = load_records(args.extracted)
    # every (paper, page) the parser did not flag, skipping the first page
    # (title and abstract) and anything after the references begin
    pool = []
    for r in sorted(recs, key=lambda r: r["id"]):
        flagged = {t.get("page") for t in r.get("tables", []) if t.get("page") is not None}
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{r['id']}.pdf")
        if not os.path.exists(path):
            continue
        doc = fitz.open(path)
        last = len(doc)
        for k in range(len(doc)):
            t = doc[k].get_text()
            if "\nREFERENCES\n" in t or "\nReferences\n" in t:
                last = k + 1
                break
        for k in range(1, last):
            if k not in flagged:
                pool.append((r["id"], k, r["title"], r["venue"], r["year"], len(flagged)))
        doc.close()
    rng = random.Random(args.seed)
    pick = sorted(rng.sample(pool, args.n))
    img_dir = os.path.join(args.out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    items = []
    for i, (pid, page_no, title, venue, year, nflag) in enumerate(pick, 1):
        iid = f"{i:04d}"
        doc = fitz.open(os.path.join("data", "corpus", f"{venue}{year}_{pid}.pdf"))
        text = "\n".join(p.get_text() for p in doc)
        sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
        doc[page_no].get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).save(os.path.join(img_dir, f"{iid}_page.png"))
        with open(os.path.join(img_dir, f"{iid}_runs.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n---\n".join(sents[:40]))
        items.append({"id": iid, "paper": pid, "page": page_no, "title": title,
                      "paper_caption_pages": nflag})
        doc.close()
    json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    json.dump({"pool_pages": len(pool), "pool_papers": len({p[0] for p in pool}), "n": args.n, "seed": args.seed,
               "rule": "pages after the first and before the references on which the parser detected no caption"},
              open(os.path.join(args.out_dir, "draw.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "pages drawn from a pool of", len(pool), "->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
