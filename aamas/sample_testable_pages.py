"""Draw one page per paper that holds a testable comparison: the page of a
randomly chosen testable comparison of that paper, rendered like the random
pages, so the end-to-end reader can be run on the stratum the failure rate
rests on.

Usage: python aamas/sample_testable_pages.py [--out-dir audits/aamas_testable_pages] [--seed 2027]
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
    ap.add_argument("--analysis", default="out/aamas/analysis.json")
    ap.add_argument("--extracted", default="data/extracted_aamas.jsonl")
    ap.add_argument("--out-dir", default="audits/aamas_testable_pages")
    ap.add_argument("--seed", type=int, default=2027)
    args = ap.parse_args(argv)
    cs = json.load(open(args.analysis, encoding="utf-8"))["_comparisons"]
    recs = {r["id"]: r for r in load_records(args.extracted)}
    rng = random.Random(args.seed)
    by_paper = {}
    for c in cs:
        if c.get("test"):
            by_paper.setdefault(c["paper"], []).append(c)
    img_dir = os.path.join(args.out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    items = []
    for i, pid in enumerate(sorted(by_paper), 1):
        c = rng.choice(by_paper[pid])
        r = recs[pid]
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{pid}.pdf")
        doc = fitz.open(path)
        page_no = c["page"]
        iid = f"{i:03d}"
        doc[page_no].get_pixmap(matrix=fitz.Matrix(2.0, 2.0)).save(os.path.join(img_dir, f"{iid}_page.png"))
        text = "\n".join(p.get_text() for p in doc)
        sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
        with open(os.path.join(img_dir, f"{iid}_runs.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n---\n".join(sents[:40]))
        items.append({"id": iid, "paper": pid, "page": page_no, "title": r["title"],
                      "n_testable_on_page": sum(1 for x in by_paper[pid] if x["page"] == page_no)})
        doc.close()
    json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "pages ->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
