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
# 82.4 +/- 0.3, 82.4(+/-0.3), 82.4 [+/- 0.3]. The bracketed forms were missing
# until a contact sheet showed a whole ICML table of "76.63(+/-3.98)" values
# being reported as carrying no error bar at all: the mean-then-symbol pattern
# needs the symbol adjacent, and the mean-then-parenthesis pattern needs a digit
# after the bracket, so this style fell between the two.
NUM_PM = re.compile(
    r"(-?\d+\.?\d*)[\s\*†‡§]{0,3}[\(\[]?[\s]{0,2}"
    r"(?:±|\+/-|\+-)[\s]{0,2}(\d+\.?\d*)[\)\]]?")
# 76.3 [75.1, 77.5] or 76.3 (75.1-77.5): an interval, which needs no run count
# to be tested. Rare in machine learning tables, but a reviewer was right that
# a definition of "checkable" that could not see one was too narrow.
NUM_CI = re.compile(
    r"(-?\d+\.?\d*)\s*[\(\[]\s*(-?\d+\.?\d*)\s*(?:,|\u2013|-)\s*(-?\d+\.?\d*)\s*[\)\]]")
NUM_PAREN = re.compile(r"(-?\d+\.?\d*)\s*\(\s*(\d+\.?\d*)\s*\)")
NUM_BARE = re.compile(r"^-?\d+\.?\d*$")

SEM_WORDS = re.compile(r"(?i)standard error|std\.?\s*err|s\.e\.m|\bsem\b")
STD_WORDS = re.compile(r"(?i)standard deviation|std\.?\s*dev|\bstd\b|\bsd\b")
CI_WORDS = re.compile(r"(?i)confidence interval|\b9[05]%\s*ci\b|\bci\b")
IQR_WORDS = re.compile(r"(?i)interquartile|\biqr\b|median absolute")

# The noun is matched case-sensitively in lower case: "Run" and "Walker Run"
# are task names in the control benchmarks, and a row label reading "Run"
# beneath a cell ending in 95 was read as 95 runs. "four seeds" and "ten runs
# of cross-validation" are written out in words at least as often as in
# digits, and the digits-only version missed every one of them. Both were
# found by the gold-set audit.
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
    "fifty": 50, "hundred": 100,
}
N_RUNS = re.compile(
    r"(?:\b(?:over|across|averaged?\s+over|mean\s+of|using|with|on|for|from)\s+)?"
    r"\b(\d{1,3}|" + "|".join(_NUMBER_WORDS) + r")\s+"
    r"(?:random\s+|independent\s+|different\s+|fixed\s+|distinct\s+)?"
    r"(?:random\s+)?(?:(?:weight|model|training|evaluation|test)\s+)?(seeds?|runs?|trials?|repetitions?|replicates?|repeats?|"
    r"(?:random\s+)?initiali[sz]ations?|restarts?|rollouts?)\b",
    re.IGNORECASE,
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
    markers: dict = dataclasses.field(default_factory=dict)
    header_text: str = ""         # the rows above the first numeric row

    def to_dict(self) -> dict:
        return {"number": self.number, "caption": self.caption, "page": self.page,
                "dispersion_kind": self.dispersion_kind, "n_runs": self.n_runs,
                "n_runs_source": self.n_runs_source, "markers": self.markers,
                "header_text": self.header_text,
                "cells": [c.to_dict() for c in self.cells]}


# Uncertainty can be printed in forms that are not an error bar: a dagger or
# star on the winning cell, a p-value in the footnote, a sentence in the
# caption. The pipeline cannot test those, but it can count them, so that the
# share of tables the definition of "testable" leaves out is a number rather
# than a worry.
MARKER_DAGGER = re.compile(r"[†‡§¶]")
MARKER_STAR = re.compile(r"\d\s?\*{1,3}(?!\w)")
MARKER_PVALUE = re.compile(r"(?i)\bp\s*(?:-\s*)?(?:value|<|\u2264|=)\s*0?\.\d")
MARKER_SIGNIF = re.compile(r"(?i)significan")
PAPER_TEST = re.compile(
    r"(?i)\b(?:t-test|t test|Wilcoxon|Mann.Whitney|permutation test|sign test|"
    r"bootstrap(?:ped)?\s+(?:confidence|interval|CI)|significance test|"
    r"statistically significant|p-value|p\s*<\s*0?\.0)"
)


def _header_text(spans: list, cells: list, cap: dict, above: float = 45.0) -> str:
    """The text between the caption and the first numeric row: column headers."""
    if not cells:
        return ""
    y_top = min(c.y for c in cells)
    x0, x1 = cap["x0"] - COLUMN_MARGIN, cap["x1"] + COLUMN_MARGIN
    parts = [s["text"] for s in spans
             if s["page"] == cap["page"] and y_top - above <= s["y"] < y_top - 1.0
             and x0 <= s["x"] <= x1 and s["y"] > cap["y"]]
    return re.sub(r"\s+", " ", " ".join(parts))[:300]


FIGURE_CAPTION = re.compile(r"(?:Figure|Fig\.)\s*\d+[.:]\s")
FIGURE_UNCERTAINTY = re.compile(
    r"(?i)error bars?|shaded|shading|standard deviation|std|confidence|"
    r"(?:seeds|runs|trials)|±|interquartile|percentile")


def _figure_uncertainty(full_text: str) -> tuple:
    """How many figure captions mention uncertainty at all."""
    starts = [m.end() for m in FIGURE_CAPTION.finditer(full_text)]
    caps = [full_text[a:min(a + 400, b)] for a, b in zip(starts, starts[1:] + [len(full_text)])]
    return len(caps), sum(1 for c in caps if FIGURE_UNCERTAINTY.search(c))


def _table_markers(spans: list, cells: list, cap: dict, below: float = 40.0) -> dict:
    """Count significance markers in the table's own region and footnote."""
    if not cells:
        return {}
    y0 = min(c.y for c in cells) - 2.0
    y1 = max(c.y for c in cells) + below
    x0, x1 = cap["x0"] - COLUMN_MARGIN, cap["x1"] + COLUMN_MARGIN
    text = " ".join(s["text"] for s in spans
                    if s["page"] == cap["page"] and y0 <= s["y"] <= y1
                    and x0 <= s["x"] <= x1)
    blob = cap["text"] + " " + text
    return {
        "dagger": len(MARKER_DAGGER.findall(text)),
        "star": len(MARKER_STAR.findall(text)),
        "pvalue": len(MARKER_PVALUE.findall(blob)),
        "signif_word": len(MARKER_SIGNIF.findall(blob)),
    }


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
        for block in page.get_text("rawdict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    bold = bool(span.get("flags", 0) & BOLD_FLAG) or "bold" in font.lower()
                    size = span.get("size", 0.0)
                    for piece in _split_span(span.get("chars", []), size):
                        txt, x0, y0, x1, y1 = piece
                        if y0 < top_cut or y0 > bottom_cut:
                            continue
                        out.append({"text": txt, "bold": bold, "page": pno, "y": y0,
                                    "x": x0, "x1": x1, "y1": y1, "size": size})
    return out


def _split_span(chars: list, size: float) -> list:
    """Cut a span wherever its glyphs leave a visible gap.

    A span is a run of glyphs in one font, and some PDFs set a whole table row
    as one span with the columns separated by positioning rather than by
    space characters. Read as text, such a row is "0.5943+-0.00160.7015+-0.0007",
    and the parser then found a winner of 2577 +- 0.0046 in a column of values
    near 0.25. Found by the gold-set audit. Splitting on the glyph geometry
    recovers the cells; the threshold is a fraction of the font size so that
    the kerning inside a number never counts as a gap.
    """
    gap_min = max(0.9, 0.28 * (size or 8.0))
    pieces, cur, prev_x1, prev_space = [], [], None, False
    for ch in chars:
        c = ch.get("c", "")
        cx0, cy0, cx1, cy1 = ch.get("bbox", (0, 0, 0, 0))
        # A gap that the PDF already marks with a space character is left to
        # the text; only an unmarked gap cuts the span, so that "Table 1:" and
        # "82.4 +/- 0.3" keep their spaces and their caption anchors.
        if cur and not prev_space and not c.isspace() and prev_x1 is not None                 and cx0 - prev_x1 > gap_min:
            pieces.append(cur)
            cur = []
        cur.append((c, cx0, cy0, cx1, cy1))
        prev_x1, prev_space = cx1, c.isspace()
    if cur:
        pieces.append(cur)
    out = []
    for pc in pieces:
        body = [b for b in pc if not b[0].isspace()]
        txt = "".join(c for c, *_ in pc).strip()
        if not txt or not body:
            continue
        out.append((txt, min(b[1] for b in body), min(b[2] for b in body),
                    max(b[3] for b in body), max(b[4] for b in body)))
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
        # A line's vertical extent must not grow when a tall span joins it.
        # A row label that spans two tightly set rows ("10" beside a Score row
        # and an Ent row, in a six-point table) used to widen the line to cover
        # both, and the second row was then glued onto the first: 0.67 and
        # 0.00 +/- 0.00 became 670.0 +/- 0.0. Found by the gold-set audit. The
        # test is therefore against the line's core, the extent of its
        # shortest member, which a row label cannot widen.
        for s_ in members:
            y0, y1 = s_["y"], s_.get("y1", s_["y"])
            h = max(1e-6, y1 - y0)
            placed = False
            for g in reversed(groups[-LINE_LOOKBACK:]):
                if g["c1"] <= y0:
                    continue
                ch = max(1e-6, g["c1"] - g["c0"])
                overlap = min(g["c1"], y1) - max(g["c0"], y0)
                if overlap / min(h, ch) >= min_overlap:
                    g["items"].append(s_)
                    if h < ch:
                        g["c0"], g["c1"] = y0, y1
                    placed = True
                    break
            if not placed:
                groups.append({"c0": y0, "c1": y1, "items": [s_]})

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
            lines.append({"page": page, "y": g["c0"], "x": items[0]["x"],
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
        for m in NUM_CI.finditer(text):
            mean, lo, hi = (float(m.group(i)) for i in (1, 2, 3))
            if not (lo <= mean <= hi and hi > lo):
                continue
            claimed.add((m.start(), m.end()))
            cells.append(Cell(text=m.group(0), mean=mean, dispersion=(hi - lo) / 2.0,
                              dispersion_style="ci",
                              bold=_bold_at(line, m.start(), m.end()),
                              page=line["page"], y=round(line["y"], 1),
                              x=round(_x_at(line, m.start()), 1)))
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


def _kind_in(text: str) -> str:
    """Which kind of dispersion a stretch of text names, if any.

    Standard error and standard deviation are checked before the confidence
    interval: a page that says "mean and standard error" in one sentence and
    "95% confidence intervals" in a figure caption is describing two things,
    and the table's bars are the first.
    """
    if SEM_WORDS.search(text):
        return "sem"
    if STD_WORDS.search(text):
        return "std"
    if CI_WORDS.search(text):
        return "ci"
    if IQR_WORDS.search(text):
        return "iqr"
    return "unknown"


def _dispersion_kind(caption: str, body_nearby: str, full_text: str = "") -> str:
    """What the error bar means, from the caption first, then the page, then
    the paper.

    The first version pooled caption and page, so a caption saying "standard
    deviation" lost to a "standard error" sentence elsewhere on the page. The
    gold-set audit also found that most bars the pipeline called unlabelled
    were named once, in the experimental setup, on another page; a reader who
    has read the paper knows what they are. The paper as a whole is therefore
    consulted last, and only when it names exactly one kind.
    """
    for text in (caption, body_nearby):
        k = _kind_in(text)
        if k != "unknown":
            return k
    if full_text:
        named = {k for k, pat in (("sem", SEM_WORDS), ("std", STD_WORDS),
                                  ("ci", CI_WORDS), ("iqr", IQR_WORDS))
                 if pat.search(full_text)}
        if len(named) == 1:
            return named.pop()
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
        vals = []
        for m in N_RUNS.finditer(text):
            noun = m.group(2)
            # The count is case-insensitive ("Five seeds" opens sentences) but
            # the noun must be lower case: "Run" is a task, "Trial" a heading.
            if not noun.islower():
                continue
            tok = m.group(1).lower()
            vals.append(_NUMBER_WORDS[tok] if tok in _NUMBER_WORDS else int(tok))
        return [v for v in vals if 2 <= v <= 200]

    cap = scan(caption)
    if cap:
        return min(cap), "caption"
    page = scan(body_nearby)
    if page:
        return min(page), "page"
    return None, None


# Every NeurIPS submission since 2021 carries a mandatory checklist, printed in
# the paper itself, one of whose questions is exactly what this study measures.
# It is external ground truth for free, and the gap between what authors answer
# and what their tables contain is a finding in its own right. ICML has no
# equivalent, which makes the pair a natural experiment.
CHECKLIST_Q = re.compile(
    r"(?is)experiment\s+statistical\s+significance.{0,400}?answer:\s*\[?\s*(yes|no|na|n/a)\s*\]?"
    r"(.{0,600}?)(?:guidelines:|\d+\.\s+[A-Z])")


def checklist_error_bar_answer(full_text: str) -> dict:
    """What the authors told the NeurIPS checklist about their error bars."""
    m = CHECKLIST_Q.search(full_text)
    if not m:
        return {"answer": None, "justification": None}
    ans = m.group(1).lower().replace("n/a", "na")
    just = re.sub(r"\s+", " ", m.group(2) or "")
    just = re.sub(r"(?i)^\s*justification:\s*", "", just).strip()
    return {"answer": ans, "justification": just[:400]}


def extract_paper(pdf_path=None, max_pages: int = 40, *, blob: bytes = None) -> dict:
    """Extract every table-like numeric block from one paper.

    Accepts either a path or the PDF bytes. Passing bytes skips a write and a
    read of several megabytes per paper, which is pure overhead when the file is
    deleted immediately afterwards anyway.
    """
    if fitz is None:
        raise RuntimeError("PyMuPDF is required: pip install pymupdf")
    if blob is not None:
        doc = fitz.open(stream=blob, filetype="pdf")
    elif pdf_path is not None:
        doc = fitz.open(pdf_path)
    else:
        raise ValueError("give extract_paper a path or a blob")
    n_pages = len(doc)
    page_texts = []
    for pno, page in enumerate(doc):
        if pno >= max_pages:
            break
        page_texts.append(page.get_text())
    full_text = "\n".join(page_texts)
    # The checklist sits at the end of the paper, past max_pages, so it needs
    # its own pass over the whole document.
    checklist = checklist_error_bar_answer("\n".join(p.get_text() for p in doc))
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
            dispersion_kind=("none" if not has_disp
                             else _dispersion_kind(cap["text"], page_text, full_text)),
            n_runs=n_runs,
            n_runs_source=n_runs_source,
            markers=_table_markers(spans, cells, cap),
            header_text=_header_text(spans, cells, cap),
        ))

    # Only cells inside a detected table count. A "(0.3)" in the running text is
    # far more often a citation year or an equation tag than an error bar, and
    # counting those inflated the headline figure from 27% to 92% before this
    # distinction was drawn.
    in_tables = [c for b in blocks for c in b.cells]
    fig_total, fig_unc = _figure_uncertainty(full_text)
    n_pm = sum(1 for c in in_tables if c.dispersion_style in ("pm", "ci"))
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
        "mentions_significance_test": bool(PAPER_TEST.search(full_text)),
        "n_table_captions": len(caption_spans),
        "n_figure_captions": fig_total,
        "n_figure_captions_with_uncertainty": fig_unc,
        "checklist_error_bars": checklist["answer"],
        "checklist_justification": checklist["justification"],
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
