"""Pull the numbers out of a paper's results tables.

The unit of analysis is a *comparison*: within one table column, the value the
authors marked as best against the strongest value they did not mark. Everything
here exists to recover that pair, together with whatever the authors said about
uncertainty.

Three observations make this tractable without a language model:

**Bold means claimed.** In almost every machine learning results table the
winning cell is bold. PyMuPDF exposes font flags per span, so the claim can be
read off the typography rather than inferred from prose. This is not perfect --
some papers bold a whole row, some bold nothing -- and the extractor records
which case it saw rather than guessing.

**Dispersion travels with the mean.** A cell reading ``82.4 +/- 0.3`` carries its
own error bar. Cells without one are recorded as having none, which is itself
one of the study's findings rather than a parsing failure to be papered over.

**The semantics live in the caption.** Whether ``0.3`` is a standard deviation, a
standard error, or a half-width confidence interval changes the analysis by a
factor of sqrt(n), and papers say which in the caption if they say it at all.
Cells whose semantics cannot be determined are marked ``unknown`` and handled
explicitly downstream; silently assuming a standard deviation would manufacture
significance that the source never claimed.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

BOLD_FLAG = 1 << 4

# 82.4 +/- 0.3, 82.4 (0.3)
NUM_PM = re.compile(r"(-?\d+\.?\d*)\s*(?:±|\+/-|\+-)\s*(\d+\.?\d*)")
NUM_PAREN = re.compile(r"(-?\d+\.?\d*)\s*\(\s*(\d+\.?\d*)\s*\)")
NUM_BARE = re.compile(r"^-?\d+\.?\d*$")

SEM_WORDS = re.compile(r"(?i)standard error|std\.?\s*err|s\.e\.m|\bsem\b")
STD_WORDS = re.compile(r"(?i)standard deviation|std\.?\s*dev|\bstd\b|\bsd\b")
CI_WORDS = re.compile(r"(?i)confidence interval|\b9[05]%\s*ci\b|\bci\b")
IQR_WORDS = re.compile(r"(?i)interquartile|\biqr\b|median absolute")

N_RUNS = re.compile(
    r"(?i)\b(?:over|across|averaged?\s+over|mean\s+of|using)?\s*(\d{1,3})\s+"
    r"(?:random\s+|independent\s+|different\s+)?(seeds?|runs?|trials?|repetitions?|replicates?)\b"
)


@dataclasses.dataclass
class Cell:
    text: str
    mean: Optional[float]
    dispersion: Optional[float]
    bold: bool
    page: int
    y: float
    x: float

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class TableBlock:
    number: Optional[str]
    caption: str
    page: int
    cells: list
    dispersion_kind: str          # std | sem | ci | iqr | unknown | none
    n_runs: Optional[int]

    def to_dict(self) -> dict:
        return {"number": self.number, "caption": self.caption, "page": self.page,
                "dispersion_kind": self.dispersion_kind, "n_runs": self.n_runs,
                "cells": [c.to_dict() for c in self.cells]}


# How far below a caption a table's numbers may lie, in PDF points, and how far
# above for the venues that caption underneath. A two-column ICLR page is 792
# points tall, so 420 spans most of a column without reaching the next caption.
WINDOW_DOWN = 420.0
WINDOW_UP = 40.0
MIN_CELLS = 6

# Horizontal gap, in points, above which two spans are treated as separate
# tokens rather than one number split by the typesetter.
GLUE_GAP = 0.8


def _caption_text(spans: list, anchor: dict, span_points: float = 60.0) -> str:
    """Reassemble a caption from the spans that follow its 'Table N' marker."""
    parts = []
    for s in spans:
        if s["page"] != anchor["page"]:
            continue
        if anchor["y"] <= s["y"] <= anchor["y"] + span_points:
            parts.append(s["text"])
    return re.sub(r"\s+", " ", " ".join(parts))[:400]


def _spans(doc, max_pages: int) -> list:
    """Every text span with its typography and position."""
    out = []
    for pno, page in enumerate(doc):
        if pno >= max_pages:
            break
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if not txt:
                        continue
                    font = span.get("font", "")
                    bold = bool(span.get("flags", 0) & BOLD_FLAG) or "bold" in font.lower()
                    x0, y0, x1, _ = span.get("bbox", (0, 0, 0, 0))
                    out.append({"text": txt, "bold": bold, "page": pno, "y": y0,
                                "x": x0, "x1": x1})
    return out


def _lines(spans: list, tol: float = 2.5) -> list:
    """Reassemble spans into visual lines.

    A cell reading ``82.4 +/- 0.3`` is routinely split by the PDF into three
    spans -- the mean, the symbol, the dispersion -- because they differ in
    font. Parsing spans individually therefore misses almost every error bar in
    the corpus, which was the first thing this extractor got wrong. Working at
    line level restores the pairs, and the character offsets are kept so that
    boldness can still be attributed to the exact number it decorates.
    """
    groups: dict = {}
    for s in spans:
        groups.setdefault((s["page"], round(s["y"] / tol)), []).append(s)

    lines = []
    for (page, _), members in groups.items():
        members.sort(key=lambda s: s["x"])
        text, offsets, pos, prev_x1 = "", [], 0, None
        for s in members:
            # Only separate spans that are visually apart. PDFs routinely split
            # "0.29" into "0." and "29"; inserting a space there turns 0.29 into
            # the number 29, which would silently corrupt every value parsed.
            gap = None if prev_x1 is None else s["x"] - prev_x1
            if text and (gap is None or gap > GLUE_GAP):
                text += " "
                pos += 1
            offsets.append((pos, pos + len(s["text"]), s))
            text += s["text"]
            pos += len(s["text"])
            prev_x1 = s.get("x1", s["x"])
        lines.append({"page": page, "y": members[0]["y"], "x": members[0]["x"],
                      "text": text, "offsets": offsets})
    lines.sort(key=lambda l: (l["page"], l["y"], l["x"]))
    return lines


def _bold_at(line: dict, start: int, end: int) -> bool:
    """Was any span overlapping this character range set in bold?"""
    for a, b, s in line["offsets"]:
        if a < end and start < b and s["bold"]:
            return True
    return False


def _x_at(line: dict, start: int) -> float:
    for a, b, s in line["offsets"]:
        if a <= start < b:
            return s["x"]
    return line["x"]


def _cells_from_lines(lines: list) -> list:
    """Every numeric value in the document, with its error bar if it has one."""
    cells = []
    for line in lines:
        text = line["text"]
        claimed = set()
        for pat in (NUM_PM, NUM_PAREN):
            for m in pat.finditer(text):
                if any(s <= m.start() < e for s, e in claimed):
                    continue
                claimed.add((m.start(), m.end()))
                cells.append(Cell(text=m.group(0), mean=float(m.group(1)),
                                  dispersion=float(m.group(2)),
                                  bold=_bold_at(line, m.start(), m.end()),
                                  page=line["page"], y=round(line["y"], 1),
                                  x=round(_x_at(line, m.start()), 1)))
        for m in re.finditer(r"(?<![\w.])(-?\d+\.\d+|\d{1,3})(?![\w.])", text):
            if any(s <= m.start() < e for s, e in claimed):
                continue
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            cells.append(Cell(text=m.group(1), mean=val, dispersion=None,
                              bold=_bold_at(line, m.start(), m.end()),
                              page=line["page"], y=round(line["y"], 1),
                              x=round(_x_at(line, m.start()), 1)))
    return cells


def _parse_value(text: str):
    m = NUM_PM.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = NUM_PAREN.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    t = text.replace("*", "").replace("†", "").strip()
    if NUM_BARE.match(t):
        try:
            return float(t), None
        except ValueError:
            return None, None
    return None, None


def _dispersion_kind(caption: str, body_nearby: str) -> str:
    blob = caption + " " + body_nearby
    if CI_WORDS.search(blob):
        return "ci"
    if SEM_WORDS.search(blob):
        return "sem"
    if STD_WORDS.search(blob):
        return "std"
    if IQR_WORDS.search(blob):
        return "iqr"
    return "unknown"


def _n_runs(caption: str, body_nearby: str):
    best = None
    for m in N_RUNS.finditer(caption + " " + body_nearby):
        n = int(m.group(1))
        if 2 <= n <= 200:
            best = n if best is None else max(best, n)
    return best


def extract_paper(pdf_path: str, max_pages: int = 40) -> dict:
    """Extract every table-like numeric block from one paper."""
    if fitz is None:
        raise RuntimeError("PyMuPDF is required: pip install pymupdf")
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    page_texts = []
    for pno, page in enumerate(doc):
        if pno >= max_pages:
            break
        page_texts.append(page.get_text())
    full_text = "\n".join(page_texts)
    spans = _spans(doc, max_pages)
    lines = _lines(spans)

    # Anchor tables on their captions rather than on numeric density. A theory
    # paper's appendix is wall-to-wall numerals -- equation tags, indices,
    # bounds -- and clustering on proximity alone harvests all of it. A caption
    # is the one reliable signal that what follows is a results table.
    caption_spans = []
    for s in spans:
        m = re.match(r"^\s*Tab(?:le|\.)\s*(\d+|[IVX]+)\b", s["text"], re.I)
        if m:
            caption_spans.append({"number": m.group(1), "page": s["page"], "y": s["y"],
                                  "text": _caption_text(spans, s)})

    numeric = _cells_from_lines(lines)

    # In machine learning papers the caption sits above the table, so cells are
    # collected downward; a small upward margin catches the journals that put it
    # below. Cells beyond the next caption on the same page belong to that table.
    blocks = []
    for i, cap in enumerate(caption_spans):
        same_page = [c for c in caption_spans[i + 1:] if c["page"] == cap["page"] and c["y"] > cap["y"]]
        y_stop = min([c["y"] for c in same_page], default=cap["y"] + WINDOW_DOWN)
        y_stop = min(y_stop, cap["y"] + WINDOW_DOWN)
        cells = [c for c in numeric
                 if c.page == cap["page"] and cap["y"] - WINDOW_UP <= c.y < y_stop]
        if len(cells) < MIN_CELLS:
            continue
        cells.sort(key=lambda c: (c.y, c.x))
        page_text = page_texts[cap["page"]] if cap["page"] < len(page_texts) else ""
        has_disp = any(c.dispersion is not None for c in cells)
        blocks.append(TableBlock(
            number=cap["number"],
            caption=cap["text"][:300],
            page=cap["page"],
            cells=cells,
            dispersion_kind=("none" if not has_disp else _dispersion_kind(cap["text"], page_text)),
            n_runs=_n_runs(cap["text"], page_text),
        ))

    n_with_disp = sum(1 for c in numeric if c.dispersion is not None)
    return {
        "path": pdf_path,
        "n_pages": n_pages,
        "n_numeric_cells": len(numeric),
        "n_cells_with_dispersion": n_with_disp,
        "reports_any_dispersion": n_with_disp > 0,
        "n_runs_global": _n_runs("", full_text),
        "n_tables_detected": len(blocks),
        "tables": [b.to_dict() for b in blocks],
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Extract results-table numbers from a corpus of PDFs.")
    ap.add_argument("--manifest", default="data/corpus_manifest.json")
    ap.add_argument("--out", default="data/extracted.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    with open(args.manifest, encoding="utf-8") as fh:
        papers = json.load(fh)["papers"]
    if args.limit:
        papers = papers[:args.limit]

    out = []
    for i, p in enumerate(papers, 1):
        if not os.path.exists(p["path"]):
            continue
        try:
            rec = extract_paper(p["path"])
        except Exception as exc:
            print(f"  [{i}] FAIL {os.path.basename(p['path'])}: {type(exc).__name__}: {exc}")
            continue
        rec.update({"venue": p["venue"], "year": p["year"], "title": p["title"],
                    "id": p["id"], "sha256": p.get("sha256")})
        out.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(papers)} extracted", flush=True)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    n = len(out)
    disp = sum(1 for r in out if r["reports_any_dispersion"])
    runs = sum(1 for r in out if r["n_runs_global"])
    print(f"\n{n} papers extracted")
    print(f"  report some dispersion : {disp} ({100 * disp / max(n, 1):.1f}%)")
    print(f"  state a number of runs : {runs} ({100 * runs / max(n, 1):.1f}%)")
    print(f"  tables detected        : {sum(r['n_tables_detected'] for r in out)}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
