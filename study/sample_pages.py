"""Draw random table pages from the corpus for an end-to-end reading.

Nothing here uses the extractor: papers are drawn from the corpus records by
id, a page is chosen among those whose text contains a table caption
("Table N" at the start of a line), and the whole page is rendered. A reader
then lists every results table on the page and every single-bold group in it,
with the bars and run count it finds, so that the no-bar and testable shares
can be computed from the reader's labels alone and set beside the pipeline's
on the same pages.

Usage: python study/sample_pages.py --n 120 --seed 20260914 --out-dir audits/gold_f
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # noqa: E402

from analyze import load_records  # noqa: E402
from gold_set import RUN_SENTENCE  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402

CAPTION = re.compile(r"(?m)^\s*Table\s+\d+[:.]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extracted", default="data/extracted_2025.jsonl")
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--max-pages", type=int, default=40)
    ap.add_argument("--out-dir", default="audits/gold_f")
    ap.add_argument("--exclude-items", action="append", default=None,
                    help="items.json of an earlier draw whose papers are skipped (repeatable)")
    ap.add_argument("--start-id", type=int, default=1, help="first item id, to continue an earlier draw")
    args = ap.parse_args(argv)
    exclude = set()
    for path in args.exclude_items or []:
        exclude |= {it["paper"] for it in json.load(open(path, encoding="utf-8"))}

    recs = load_records(args.extracted)
    ids = sorted(r["id"] for r in recs)
    rng = random.Random(args.seed)
    rng.shuffle(ids)
    index = {}
    for s in ("neurips2025", "icml2025"):
        for rec in SOURCES[s]():
            index[rec["id"]] = rec
    img_dir = os.path.join(args.out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    items = []
    tried = 0
    for pid in ids:
        if len(items) >= args.n:
            break
        if pid in exclude:
            continue
        tried += 1
        rec = index.get(pid)
        if rec is None:
            continue
        try:
            blob = _get(rec["pdf"])
        except Exception as exc:  # noqa: BLE001
            print(f"  {pid[:8]} download failed: {exc}")
            continue
        doc = fitz.open(stream=blob, filetype="pdf")
        pages = [p.get_text() for p in doc]
        cands = [i for i, t in enumerate(pages[: args.max_pages]) if CAPTION.search(t)]
        if not cands:
            doc.close()
            continue
        page_no = rng.choice(cands)
        iid = f"{args.start_id + len(items):03d}"
        pix = doc[page_no].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        pix.save(os.path.join(img_dir, f"{iid}_page.png"))
        text = "\n".join(pages)
        sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
        with open(os.path.join(img_dir, f"{iid}_runs.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n---\n".join(sents[:40]))
        items.append({"id": iid, "paper": pid, "page": page_no, "title": rec["title"],
                      "n_caption_pages": len(cands)})
        doc.close()
        print(f"  {iid} {pid[:8]} page {page_no + 1} of {len(pages)} ({len(cands)} table pages)", flush=True)
        json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "pages from", tried, "papers tried ->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
