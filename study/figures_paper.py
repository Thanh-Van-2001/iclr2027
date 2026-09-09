"""The paper's figures.

Three of them, each answering one question a reader will have, and none of them
decorative. Colour is never the only channel that carries meaning, every axis
starts where it should, and each figure writes a sidecar recording the run it
came from so a number in the caption can be traced to the run that produced it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from paperengine.figures import PALETTE, WIDTH_DOUBLE, new_figure, save, use_paper_style  # noqa: E402


def fig_why_untestable(analysis: dict, out: str, run_id: str) -> None:
    """What stops a highlighted comparison from being checkable."""
    u = analysis["untestable_reasons"]
    order = [
        ("Neither value has\nan error bar", u["neither_side"]),
        ("Only one value\nhas an error bar", u["one_side_only"]),
        ("Error bar given,\nnumber of runs not", u["no_n_stated"]),
        ("Testable", u["testable"]),
    ]
    total = sum(v for _, v in order) + u.get("other", 0)
    labels = [k for k, _ in order]
    vals = [100 * v / total for _, v in order]
    colours = [PALETTE[1], PALETTE[1], PALETTE[1], PALETTE[0]]
    hatches = ["", "//", "xx", ""]

    fig, ax = new_figure(width=WIDTH_DOUBLE, height=2.6)
    bars = ax.barh(range(len(vals)), vals, color=colours, edgecolor="black", linewidth=0.6)
    for b, h in zip(bars, hatches):
        b.set_hatch(h)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Share of highlighted comparisons (%)")
    ax.set_xlim(0, 100)
    for i, v in enumerate(vals):
        ax.text(v + 1.2, i, f"{v:.1f}%", va="center", fontsize=8)
    save(fig, out, source_runs=[run_id],
         caption_note="Why a highlighted comparison cannot be checked.")


def fig_gap_vs_survival(analysis: dict, comparisons: list, out: str, run_id: str) -> None:
    """Improvements that fail are the small ones."""
    passing = [100 * c["relative_gap"] for c in comparisons
               if c.get("survives_raw") and c.get("relative_gap") is not None]
    failing = [100 * c["relative_gap"] for c in comparisons
               if c.get("test") and not c.get("survives_raw") and c.get("relative_gap") is not None]

    fig, ax = new_figure(width=WIDTH_DOUBLE, height=2.6)
    bins = [0, 0.5, 1, 2, 3, 5, 8, 12, 20, 40]
    ax.hist([failing, passing], bins=bins, color=[PALETTE[1], PALETTE[0]],
            edgecolor="black", linewidth=0.6,
            label=["Not distinguishable from zero", "Survives its own error bars"])
    for patch in ax.patches[:len(bins) - 1]:
        patch.set_hatch("//")
    ax.set_xlabel("Reported improvement over the runner-up (%)")
    ax.set_ylabel("Comparisons")
    ax.legend(frameon=False, fontsize=8)
    save(fig, out, source_runs=[run_id],
         caption_note="Failures concentrate in the small margins that decide rankings.")


def fig_replication(rows: list, out: str, run_id: str) -> None:
    """The same measurement, in two years and two venues."""
    labels = [r["label"] for r in rows]
    pct = [r["pct_explicit_error_bar"] for r in rows]
    n = [r["n"] for r in rows]

    fig, ax = new_figure(width=WIDTH_DOUBLE, height=2.4)
    bars = ax.bar(range(len(rows)), pct, color=PALETTE[2],
                  edgecolor="black", linewidth=0.6, width=0.6)
    for i, (b, v, k) in enumerate(zip(bars, pct, n)):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.1f}%\nn={k}",
                ha="center", fontsize=8)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Papers with an explicit\nerror bar in a results table (%)")
    ax.set_ylim(0, max(pct) * 1.45)
    save(fig, out, source_runs=[run_id],
         caption_note="The measurement replicates across venues and years.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the paper's figures.")
    ap.add_argument("--analysis", default="out/analysis_2025.json")
    ap.add_argument("--run-id", default="survivability_2025")
    ap.add_argument("--out-dir", default="paper/submission/figures")
    args = ap.parse_args(argv)

    with open(args.analysis, encoding="utf-8") as fh:
        a = json.load(fh)
    cmps = a["_comparisons"]

    reasons = {"neither_side": 0, "one_side_only": 0, "no_n_stated": 0, "testable": 0, "other": 0}
    for c in cmps:
        if c.get("test"):
            reasons["testable"] += 1
        elif c["winner_dispersion"] is None and c["runner_dispersion"] is None:
            reasons["neither_side"] += 1
        elif c["winner_dispersion"] is None or c["runner_dispersion"] is None:
            reasons["one_side_only"] += 1
        elif not c["n_runs"]:
            reasons["no_n_stated"] += 1
        else:
            reasons["other"] += 1
    a["untestable_reasons"] = reasons

    os.makedirs(args.out_dir, exist_ok=True)
    fig_why_untestable(a, os.path.join(args.out_dir, "untestable.pdf"), args.run_id)
    fig_gap_vs_survival(a, cmps, os.path.join(args.out_dir, "gap_survival.pdf"), args.run_id)
    print(f"wrote figures to {args.out_dir}")
    print(json.dumps(reasons, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
