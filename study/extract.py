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
NUM_PM = re.compile(r"(-?\d+\.?\d*)[\s\*†‡§]{0,3}(?:±|\+/-|\+-)[\s]{0,2}(\d+\.?\d*)")
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
    dispersion_style: str   # "pm" (explicit +/-), "paren" (ambiguous), "none"
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
    n_runs_source: Optional[str]  # "caption" | "page" | None

    def to_dict(self) -> dict:
        return {"number": self.number, "caption": self.caption, "page": self.page,
                "dispersion_kind": self.dispersion_kind, "n_runs": self.n_runs,
                "n_runs_source": self.n_runs_source,
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

# How many recently opened lines a span may join. Spans are processed in y
# order, so anything older cannot overlap.
LINE_LOOKBACK = 6

# A cell may sit this far outside the caption's horizontal extent, and rows may
# be this far apart, before they are treated as belonging to something else.
COLUMN_MARGIN = 18.0
ROW_GAP_MAX = 34.0

# Fractions of page height treated as running head and footer.
HEADER_FRACTION = 0.045
FOOTER_FRACTION = 0.055


def _caption_text(spans: list, anchor: dict, span_points: float = 60.0) -> str:
    """Reassemble a caption from the spans that follow its 'Table N' marker."""
    parts = []
    for s in spans:
        if s["page"] != anchor["page"]:
            continue
        if anchor["y"] <= s["y"] <= anchor["y"] + span_points:
            parts.append(s["text"])
    return re.sub(r"\s+", " ", " ".join(parts))[:400]


def _caption_extent(spans: list, anchor: dict, span_points: float = 60.0) -> tuple:
    """Horizontal extent of the caption, which is also the table's column."""
    xs = [(s["x"], s.get("x1", s["x"])) for s in spans
          if s["page"] == anchor["page"] and anchor["y"] <= s["y"] <= anchor["y"] + span_points]
    if not xs:
        return anchor["x"], anchor["x"] + 200.0
    return min(a for a, _ in xs), max(b for _, b in xs)


def _contiguous_run(cells: list) -> list:
    """Keep the rows that actually belong to the table.

    Table rows are a line apart; the gap to the body text or the page number
    below is much larger. Taking the *first* run rather than the largest was too
    eager: a caption reading "with p-value less than 0.05" contributes a numeric
    cell of its own, and the gap from caption to table header then truncated the
    table to that single number. The table body is the largest run.
    """
    if not cells:
        return cells
    runs, cur = [], [cells[0]]
    for c in cells[1:]:
        if c.y - cur[-1].y > ROW_GAP_MAX:
            runs.append(cur)
            cur = []
        cur.append(c)
    runs.append(cur)
    return max(runs, key=len)


def _spans(doc, max_pages: int) -> list:
    """Every text span with its typography and position.

    Running heads and page numbers are dropped: a page number is a bare integer
    sitting below every table on the page, and one of them was extracted as the
    runner-up in a sampled comparison.
    """
    out = []
    for pno, page in enumerate(doc):
        if pno >= max_pages:
            break
        ph = page.rect.height or 792.0
        top_cut, bottom_cut = ph * HEADER_FRACTION, ph * (1.0 - FOOTER_FRACTION)
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "").strip()
                    if not txt:
                        continue
                    font = span.get("font", "")
                    bold = bool(span.get("flags", 0) & BOLD_FLAG) or "bold" in font.lower()
                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    if y0 < top_cut or y0 > bottom_cut:
                        continue
                    out.append({"text": txt, "bold": bold, "page": pno, "y": y0,
                                "x": x0, "x1": x1, "y1": y1,
                                "size": span.get("size", 0.0)})
    return out


def _lines(spans: list, min_overlap: float = 0.45) -> list:
    """Reassemble spans into visual lines by vertical overlap.

    Two earlier versions of this got it wrong in ways that would have produced a
    confident and false paper.

    Parsing spans one at a time missed almost every error bar, because a PDF
    splits ``82.4 +/- 0.3`` into separate spans for the mean, the symbol and the
    dispersion.

    Grouping spans into lines by rounding the y coordinate then broke the very
    common table style that sets the error bar as a subscript: a subscript sits
    a point or two lower than its baseline, so it landed in its own line, and a
    row rendered as ``91.48*±0.40  66.53*±8.55`` was read as the single value
    0.40 +/- 8.55 -- one column's error bar paired with the next column's. That
    was found by rendering a sampled table and looking at it.

    Clustering on vertical overlap fixes both, because a subscript overlaps the
    line it belongs to and the next table row does not.
    """
    by_page: dict = {}
    for s_ in spans:
        by_page.setdefault(s_["page"], []).append(s_)

    lines = []
    for page, members in by_page.items():
        members.sort(key=lambda s_: (s_["y"], s_["x"]))
        groups: list = []
        # Spans arrive sorted by y, and a group's vertical extent only grows, so
        # a new span can overlap only the most recently opened groups. Scanning
        # every group instead made this quadratic and cut throughput from about
        # twenty papers a minute to three and a half.
        for s_ in members:
            y0, y1 = s_["y"], s_.get("y1", s_["y"])
            h = max(1e-6, y1 - y0)
            placed = False
            for g in reversed(groups[-LINE_LOOKBACK:]):
                if g["y1"] <= y0:
                    continue
                gh = max(1e-6, g["y1"] - g["y0"])
                overlap = min(g["y1"], y1) - max(g["y0"], y0)
                if overlap / min(h, gh) >= min_overlap:
                    g["items"].append(s_)
                    g["y0"] = min(g["y0"], y0)
                    g["y1"] = max(g["y1"], y1)
                    placed = True
                    break
            if not placed:
                groups.append({"y0": y0, "y1": y1, "items": [s_]})

        for g in groups:
            items = sorted(g["items"], key=lambda s_: s_["x"])
            text, offsets, pos, prev_x1 = "", [], 0, None
            for s_ in items:
                # Only separate spans that are visually apart. PDFs routinely
                # split "0.29" into "0." and "29"; inserting a space there turns
                # 0.29 into the number 29.
                gap = None if prev_x1 is None else s_["x"] - prev_x1
                if text and (gap is None or gap > GLUE_GAP):
                    text += " "
                    pos += 1
                offsets.append((pos, pos + len(s_["text"]), s_))
                text += s_["text"]
                pos += len(s_["text"])
                prev_x1 = s_.get("x1", s_["x"])
            lines.append({"page": page, "y": g["y0"], "x": items[0]["x"],
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
        for pat, style in ((NUM_PM, "pm"), (NUM_PAREN, "paren")):
            for m in pat.finditer(text):
                if any(s <= m.start() < e for s, e in claimed):
                    continue
                claimed.add((m.start(), m.end()))
                cells.append(Cell(text=m.group(0), mean=float(m.group(1)),
                                  dispersion=float(m.group(2)), dispersion_style=style,
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
                              dispersion_style="none",
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
    """How many runs produced these means, and how sure are we.

    Returns ``(n, source)`` where source is "caption", "page" or None.

    The first version scanned caption and page together and kept the largest
    match. That was wrong twice over. Scanning the page picks up any number
    followed by "runs" anywhere on it, and a row label reading "top 100" in a
    table about something else produced n=100 for a table whose true n is
    unstated. And taking the maximum is the anti-conservative choice: a larger n
    shrinks the standard error and manufactures significance, which biases this
    study towards under-reporting failures -- the opposite of the direction an
    author should be willing to err in.

    The caption is authoritative. Failing that, the page is used but the
    smallest plausible value is taken, and the source is recorded so the
    analysis can report results with and without page-derived counts.
    """
    def scan(text):
        vals = [int(m.group(1)) for m in N_RUNS.finditer(text)]
        return [v for v in vals if 2 <= v <= 200]

    cap = scan(caption)
    if cap:
        return min(cap), "caption"
    page = scan(body_nearby)
    if page:
        return min(page), "page"
    return None, None


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
            cx0, cx1 = _caption_extent(spans, s)
            caption_spans.append({"number": m.group(1), "page": s["page"], "y": s["y"],
                                  "x0": cx0, "x1": cx1,
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
        # Two-column venues put an unrelated table beside this one, and the page
        # number sits below every table on the page. Both were being swept in: a
        # sampled ICML table came out with the page number 8 as its runner-up.
        # Constrain to the caption's own horizontal band, then keep only the run
        # of rows contiguous with the caption.
        cells = [c for c in numeric
                 if c.page == cap["page"] and cap["y"] - WINDOW_UP <= c.y < y_stop
                 and cap["x0"] - COLUMN_MARGIN <= c.x <= cap["x1"] + COLUMN_MARGIN]
        cells.sort(key=lambda c: (c.y, c.x))
        cells = _contiguous_run(cells)
        if len(cells) < MIN_CELLS:
            continue
        page_text = page_texts[cap["page"]] if cap["page"] < len(page_texts) else ""
        has_disp = any(c.dispersion is not None for c in cells)
        n_runs, n_runs_source = _n_runs(cap["text"], page_text)
        blocks.append(TableBlock(
            number=cap["number"],
            caption=cap["text"][:300],
            page=cap["page"],
            cells=cells,
            dispersion_kind=("none" if not has_disp else _dispersion_kind(cap["text"], page_text)),
            n_runs=n_runs,
            n_runs_source=n_runs_source,
        ))

    # Only cells inside a detected table count. A "(0.3)" in the running text is
    # far more often a citation year or an equation tag than an error bar, and
    # counting those inflated the headline figure from 27% to 92% before this
    # distinction was drawn.
    in_tables = [c for b in blocks for c in b.cells]
    n_pm = sum(1 for c in in_tables if c.dispersion_style == "pm")
    n_paren = sum(1 for c in in_tables if c.dispersion_style == "paren")
    return {
        "path": pdf_path,
        "n_pages": n_pages,
        "n_numeric_cells": len(numeric),
        "n_table_cells": len(in_tables),
        "n_cells_pm": n_pm,
        "n_cells_paren": n_paren,
        "n_cells_with_dispersion": n_pm + n_paren,
        "reports_explicit_error_bar": n_pm > 0,
        "reports_any_dispersion": (n_pm + n_paren) > 0,
        "n_runs_global": _n_runs("", full_text)[0],
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
