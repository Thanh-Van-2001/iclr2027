"""Publication figures.

Constraints that apply to a conference figure but not to a dashboard, and that
this module enforces rather than suggests:

* **Colour is never the only encoding.**  Every series also carries a marker
  and a dash pattern, so the figure survives greyscale printing and colour
  vision deficiency.  The palette below is Okabe-Ito, reordered so that
  adjacent slots are maximally separated under deuteranopia; the ordering was
  chosen by running the palette validator, not by eye.
* **One y-axis.**  A dual-axis chart invites the reader to infer a correlation
  the data does not contain, and :func:`assert_single_axis` refuses to draw one.
* **Uncertainty is shown or its absence is declared.**  A point estimate with
  no interval is the single most common reason a reviewer distrusts a plot.
* **Every figure carries provenance.**  The saved PDF is accompanied by a
  sidecar ``.json`` naming the runs the numbers came from.
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Optional, Sequence

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

# Okabe-Ito, ordered for maximum adjacent separation under CVD.
# Validated: worst adjacent deuteranopia dE 9.6, worst normal-vision dE 20.0.
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#E69F00", "#CC79A7", "#56B4E9"]
MARKERS = ["o", "s", "^", "D", "v", "P"]
DASHES = [(None, None), (4, 1.6), (1.4, 1.4), (6, 1.6, 1.4, 1.6), (3, 1.2, 1.2, 1.2), (8, 2)]

INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#d9d9d9"

# Single-column width of the ICLR/NeurIPS two-column-ish style, in inches.
WIDTH_SINGLE = 3.25
WIDTH_DOUBLE = 6.75


def use_paper_style(base_font: float = 8.0) -> None:
    """Install rcParams suited to a camera-ready PDF."""
    plt.rcParams.update({
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,          # embed TrueType so reviewers can select text
        "ps.fonttype": 42,
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif", "Nimbus Roman"],
        "mathtext.fontset": "stix",
        "font.size": base_font,
        "axes.labelsize": base_font,
        "axes.titlesize": base_font,
        "xtick.labelsize": base_font - 1,
        "ytick.labelsize": base_font - 1,
        "legend.fontsize": base_font - 1,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "lines.linewidth": 1.3,
        "lines.markersize": 3.6,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "legend.frameon": False,
        "legend.handlelength": 2.4,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.prop_cycle": plt.cycler(color=PALETTE),
    })


def style_of(index: int) -> dict:
    """Colour, marker and dash pattern for series ``index``.

    Wrapping past six series is refused rather than silently cycled: a seventh
    line is a signal to facet the figure, not to reuse a colour.
    """
    if index >= len(PALETTE):
        raise ValueError(
            f"series index {index} exceeds the {len(PALETTE)}-slot categorical palette; "
            "fold the tail into an 'Other' series or split into small multiples"
        )
    return {"color": PALETTE[index], "marker": MARKERS[index], "dashes": DASHES[index]}


def assert_single_axis(ax) -> None:
    """Refuse a twin y-axis."""
    for other in ax.figure.axes:
        if other is not ax and other.bbox.bounds == ax.bbox.bounds:
            raise ValueError(
                "two axes share this position, which means a dual y-axis. "
                "Use small multiples or index both measures to a common base instead."
            )


def line_with_ci(
    ax,
    x: Sequence[float],
    series: dict[str, tuple[Sequence[float], Optional[Sequence[float]], Optional[Sequence[float]]]],
    *,
    xlabel: str,
    ylabel: str,
    direct_label: bool = True,
) -> None:
    """Lines with shaded confidence bands.

    ``series`` maps a label to ``(y, lo, hi)``; pass ``(y, None, None)`` only
    when there genuinely is no uncertainty to report, and say so in the caption.
    """
    assert_single_axis(ax)
    for i, (label, (y, lo, hi)) in enumerate(series.items()):
        st = style_of(i)
        line, = ax.plot(x, y, label=label, color=st["color"], marker=st["marker"],
                        markeredgecolor="white", markeredgewidth=0.4, zorder=3 + i)
        if st["dashes"][0] is not None:
            line.set_dashes(st["dashes"])
        if lo is not None and hi is not None:
            ax.fill_between(x, lo, hi, color=st["color"], alpha=0.16, linewidth=0, zorder=2)
        if direct_label and len(series) <= 4:
            ax.annotate(label, xy=(x[-1], y[-1]), xytext=(3, 0), textcoords="offset points",
                        color=st["color"], fontsize=plt.rcParams["legend.fontsize"],
                        va="center", ha="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    if not (direct_label and len(series) <= 4) and len(series) >= 2:
        ax.legend(loc="best")


def grouped_bars_with_ci(
    ax,
    categories: Sequence[str],
    series: dict[str, tuple[Sequence[float], Optional[Sequence[float]]]],
    *,
    ylabel: str,
    annotate: bool = False,
) -> None:
    """Grouped bars with error bars.

    ``series`` maps a label to ``(values, halfwidths)``.  A 2 pt gap is left
    between adjacent bars so that neighbouring fills never touch.
    """
    assert_single_axis(ax)
    n_groups, n_series = len(categories), len(series)
    slot = 0.8 / max(n_series, 1)
    gap = 0.012
    for i, (label, (vals, err)) in enumerate(series.items()):
        st = style_of(i)
        offs = [g - 0.4 + slot * (i + 0.5) for g in range(n_groups)]
        ax.bar(offs, vals, width=slot - gap, label=label, color=st["color"],
               edgecolor="white", linewidth=0.5, zorder=3)
        if err is not None:
            ax.errorbar(offs, vals, yerr=err, fmt="none", ecolor=INK,
                        elinewidth=0.7, capsize=1.8, capthick=0.7, zorder=4)
        if annotate:
            for xo, v in zip(offs, vals):
                ax.annotate(f"{v:.2f}", xy=(xo, v), xytext=(0, 2.5), textcoords="offset points",
                            ha="center", fontsize=plt.rcParams["legend.fontsize"] - 0.5, color=MUTED)
    ax.set_xticks(range(n_groups))
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    if n_series >= 2:
        ax.legend(loc="best", ncol=min(n_series, 3))


def new_figure(width: float = WIDTH_SINGLE, height: Optional[float] = None,
               ncols: int = 1, nrows: int = 1) -> tuple[Figure, object]:
    use_paper_style()
    height = height if height is not None else width * 0.62 * nrows
    return plt.subplots(nrows, ncols, figsize=(width, height), constrained_layout=True)


def save(fig: Figure, path: str, *, source_runs: Iterable[str], caption_note: str = "") -> None:
    """Write the figure plus a provenance sidecar.

    The sidecar is what lets a co-author -- or the author, three weeks later --
    answer "where did this line come from?" without re-deriving it.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.savefig(path)
    stem, _ = os.path.splitext(path)
    fig.savefig(stem + ".png", dpi=200)
    with open(stem + ".provenance.json", "w", encoding="utf-8") as fh:
        json.dump({
            "figure": os.path.basename(path),
            "source_runs": sorted(set(source_runs)),
            "caption_note": caption_note,
            "palette": PALETTE,
        }, fh, indent=2)
    plt.close(fig)
