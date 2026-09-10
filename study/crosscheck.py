"""A second, independent extractor, to see whether the first one can be trusted.

Checking a hundred tables by eye is the gold standard and does not scale; it
found five real bugs but gives a precision estimate with a useless interval.
This is the complement: a completely different way of reading the same tables,
run over the whole corpus, so agreement can be measured on thousands of tables
rather than dozens.

The two paths share nothing but the PDF. The primary extractor works from text
spans and their geometry, reassembling lines by vertical overlap and inferring
structure from position. This one asks ``pdfplumber`` to detect ruling lines and
whitespace columns and hand back a grid of cells. Where they agree, a parsing
error would have to be made twice, in the same direction, by two unrelated
algorithms. Where they disagree, one of them is wrong and the case is worth
looking at.

Agreement is not accuracy: both could be fooled by the same unusual table. It is
reported as what it is, alongside the hand-checked sample.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import pdfplumber  # noqa: E402
import requests  # noqa: E402

from extract import NUM_PM, NUM_PAREN, extract_paper  # noqa: E402
from harvest import SOURCES  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; paper-audit/0.1)"}

TEXT_STRATEGY = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "text_x_tolerance": 2,
    "text_y_tolerance": 2,
    "intersection_tolerance": 5,
}
MIXED_STRATEGY = {
    "vertical_strategy": "text",
    "horizontal_strategy": "lines",
    "text_x_tolerance": 2,
    "intersection_tolerance": 5,
}


def _cell_value(text: str):
    """Mean and dispersion from one grid cell, or (None, None)."""
    if not text:
        return None, None
    t = re.sub(r"\s+", " ", text).strip()
    m = NUM_PM.search(t) or NUM_PAREN.search(t)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    m = re.fullmatch(r"(-?\d+\.?\d*)[\s\*†‡§]*", t)
    if m:
        try:
            return float(m.group(1)), None
        except ValueError:
            return None, None
    return None, None


def plumber_tables(blob: bytes, max_pages: int = 40) -> list:
    """Every numeric grid pdfplumber can find, as lists of (mean, dispersion)."""
    out = []
    with pdfplumber.open(_BytesIO(blob)) as pdf:
        for pno, page in enumerate(pdf.pages):
            if pno >= max_pages:
                break
            # Machine learning papers use booktabs: horizontal rules only, no
            # vertical lines. pdfplumber's default detector looks for ruling
            # lines and finds nothing, so it must be told to infer columns from
            # whitespace instead. With the default settings this second
            # extractor returned zero cells on every paper, which looked at
            # first like the primary extractor being unconfirmed.
            tables = []
            for settings in (TEXT_STRATEGY, MIXED_STRATEGY):
                try:
                    found = page.extract_tables(settings)
                except Exception:
                    found = []
                if found:
                    tables = found
                    break
            for tbl in tables:
                cells = []
                for row in tbl:
                    for cell in row:
                        mean, disp = _cell_value(cell or "")
                        if mean is not None:
                            cells.append((mean, disp))
                if len(cells) >= 6:
                    out.append({"page": pno, "cells": cells})
    return out


class _BytesIO:
    """pdfplumber wants a file-like object."""

    def __new__(cls, blob: bytes):
        import io
        return io.BytesIO(blob)


def compare_paper(blob: bytes, *, tol: float = 1e-6) -> dict:
    """How much of what the primary extractor found does the second one confirm?"""
    primary = extract_paper(blob=blob)
    prim_cells = {(round(c["mean"], 6), round(c["dispersion"], 6) if c["dispersion"] is not None else None)
                  for t in primary["tables"] for c in t["cells"]}
    prim_with_disp = {p for p in prim_cells if p[1] is not None}

    secondary = plumber_tables(blob)
    sec_cells = {(round(m, 6), round(d, 6) if d is not None else None)
                 for t in secondary for (m, d) in t["cells"]}
    sec_with_disp = {p for p in sec_cells if p[1] is not None}

    # A value counts as confirmed when the other extractor produced the same
    # (mean, dispersion) pair anywhere in the document.
    confirmed = prim_with_disp & sec_with_disp
    only_primary = prim_with_disp - sec_with_disp
    only_secondary = sec_with_disp - prim_with_disp

    return {
        "primary_cells": len(prim_cells),
        "primary_with_dispersion": len(prim_with_disp),
        "secondary_cells": len(sec_cells),
        "secondary_with_dispersion": len(sec_with_disp),
        "confirmed": len(confirmed),
        "only_primary": len(only_primary),
        "only_secondary": len(only_secondary),
        "agreement": (len(confirmed) / len(prim_with_disp)) if prim_with_disp else None,
        "examples_only_primary": sorted(only_primary)[:5],
        "examples_only_secondary": sorted(only_secondary)[:5],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Cross-check the extractor against pdfplumber.")
    ap.add_argument("--source", action="append", default=["neurips2025", "icml2025"])
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=5)
    ap.add_argument("--max-bytes", type=int, default=30_000_000)
    ap.add_argument("--out", default="out/crosscheck.json")
    args = ap.parse_args(argv)

    records = []
    for s in args.source:
        records.extend(SOURCES[s]())
    records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
    sample = random.Random(args.seed).sample(records, min(args.n, len(records)))

    sess = requests.Session()
    sess.headers.update(UA)
    rows = []
    for i, rec in enumerate(sample, 1):
        try:
            head = sess.head(rec["pdf"], timeout=25, allow_redirects=True)
            size = int(head.headers.get("Content-Length") or 0)
            if size > args.max_bytes:
                continue
            blob = sess.get(rec["pdf"], timeout=90).content
            res = compare_paper(blob)
        except Exception as exc:
            print(f"  [{i}] skip {rec['title'][:45]}: {type(exc).__name__}")
            continue
        res.update({"id": rec["id"], "title": rec["title"], "venue": rec["venue"]})
        rows.append(res)
        if i % 10 == 0:
            print(f"  {i}/{len(sample)}", flush=True)

    scored = [r for r in rows if r["agreement"] is not None]
    total_prim = sum(r["primary_with_dispersion"] for r in scored)
    total_conf = sum(r["confirmed"] for r in scored)
    total_sec_only = sum(r["only_secondary"] for r in scored)
    summary = {
        "n_papers_compared": len(rows),
        "n_papers_with_dispersion": len(scored),
        "primary_values_with_dispersion": total_prim,
        "confirmed_by_second_extractor": total_conf,
        "confirmation_rate": round(total_conf / total_prim, 4) if total_prim else None,
        "found_only_by_second_extractor": total_sec_only,
        "recall_gap": round(total_sec_only / max(total_prim + total_sec_only, 1), 4),
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "papers": rows}, fh, indent=1)
    print(json.dumps(summary, indent=1))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
