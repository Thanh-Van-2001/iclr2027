"""Figures for the AAMAS paper, from run records only.

fig_census.pdf: (a) what a highlighted comparison carries, AAMAS against
NeurIPS/ICML 2025; (b) the Welch failure rate by stated run count, both
corpora, with Wilson intervals.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

OUT = "paper/aamas"


def _j(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main():
    ex = _j("out/aamas/extra.json")
    ml = _j("out/both_years.json")["2025"]
    ml_runs = _j("out/extra_stats.json")["subset_direction"]["by_runs"]
    a = ex["summary"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.7), gridspec_kw={"width_ratios": [1.15, 1]})

    # (a) stacked composition of comparisons
    ax = axes[0]
    cats = [("No bar on either side", "pct_neither", "#c8c8c8"),
            ("Bar on one side", "pct_one", "#a0a0a0"),
            ("Bars, no run count", "pct_no_n", "#787878"),
            ("Testable, fails", None, "#c0392b"),
            ("Testable, survives", None, "#27ae60")]
    rows = [("AAMAS\n2024--26\n(parser)", a), ("NeurIPS/ICML\n2025 (parser)", ml)]
    if os.path.exists("out/aamas/gold_set_census.json"):
        cz = _j("out/aamas/gold_set_census.json")
        rz, fz = cz["reader"], cz["reader_failure"]
        fail = fz["pct_fail"] if fz["n"] else 0.0
        rows.insert(0, ("AAMAS\n2024--26\n(reader census)", {
            "pct_neither": rz["pct_neither"], "pct_one": rz["pct_one_side"],
            "pct_no_n": max(0.0, 100.0 - rz["pct_neither"] - rz["pct_one_side"] - rz["pct_testable"]),
            "pct_testable": rz["pct_testable"], "pct_fail": fail}))
    for i, (name, s) in enumerate(rows):
        left = 0.0
        vals = [s["pct_neither"], s["pct_one"], s["pct_no_n"],
                s["pct_testable"] * s["pct_fail"] / 100.0,
                s["pct_testable"] * (100.0 - s["pct_fail"]) / 100.0]
        for (label, _, color), v in zip(cats, vals):
            ax.barh(i, v, left=left, color=color, edgecolor="white", linewidth=0.5,
                    label=label if i == 0 else None)
            if v >= 6:
                ax.text(left + v / 2, i, f"{v:.0f}%", ha="center", va="center", fontsize=6.5,
                        color="white" if color in ("#787878", "#c0392b", "#27ae60") else "black")
            left += v
    ax.set_yticks(list(range(len(rows))))
    ax.set_yticklabels([r[0] for r in rows], fontsize=7)
    ax.set_xlim(0, 100)
    ax.set_xlabel("share of highlighted comparisons (%)", fontsize=7.5)
    ax.tick_params(axis="x", labelsize=7)
    ax.invert_yaxis()
    ax.legend(fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=3, frameon=False)
    ax.set_title("(a) What the page prints beside a bold cell", fontsize=8)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)

    # (b) failure by run count band
    ax = axes[1]
    bands = [("le3", "$\\leq 3$"), ("4to5", "4--5"), ("ge6", "$\\geq 6$")]
    for j, (src, name, color) in enumerate(((ex["subset_direction"]["by_runs"], "AAMAS", "#1f4e79"),
                                             (ml_runs, "NeurIPS/ICML", "#7f7f7f"))):
        xs = [k + (j - 0.5) * 0.3 for k in range(len(bands))]
        ys = [src[b]["pct_fail"] for b, _ in bands]
        lo = [src[b]["pct_fail"] - src[b]["ci_fail"][0] for b, _ in bands]
        hi = [src[b]["ci_fail"][1] - src[b]["pct_fail"] for b, _ in bands]
        ax.bar(xs, ys, width=0.3, color=color, label=name)
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor="black", elinewidth=0.7, capsize=2)
        for x, y, (b, _) in zip(xs, ys, bands):
            ax.text(x, 2, f"n={src[b]['n']}", ha="center", va="bottom", fontsize=5.5, color="white", rotation=90)
    ax.set_xticks(range(len(bands)))
    ax.set_xticklabels([n for _, n in bands], fontsize=7.5)
    ax.set_xlabel("stated run count", fontsize=7.5)
    ax.set_ylabel("failing at $p \\geq 0.05$ (%)", fontsize=7.5)
    ax.set_ylim(0, 100)
    ax.tick_params(axis="y", labelsize=7)
    ax.legend(fontsize=6.5, frameon=False, loc="upper right")
    ax.set_title("(b) Failure rate by run count (Welch)", fontsize=8)
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)

    fig.tight_layout()
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(os.path.join(OUT, "fig_census.pdf"), bbox_inches="tight")
    fig.savefig("out/aamas/fig_census.png", dpi=160, bbox_inches="tight")
    print("wrote", os.path.join(OUT, "fig_census.pdf"))

    # protocol resolution: printed gap against what K episodes x seeds resolve
    # the model-read set of Section 6 (typed reading), else the earlier readings
    rows = None
    for cand in ("out/aamas/protocol_resolution_rows_reader2.json", "out/aamas/protocol_resolution_rows_reader.json",
                 "out/aamas/protocol_resolution_rows.json"):
        if os.path.exists(cand):
            rows = _j(cand)
            break
    fig, ax = plt.subplots(figsize=(3.3, 2.6))
    for has_bars, color, label in ((False, "#1f4e79", "no error bar printed"), (True, "#e67e22", "error bar printed")):
        xs = [r["resolvable"] * 100 for r in rows if r["has_bars"] == has_bars]
        ys = [r["gap"] * 100 for r in rows if r["has_bars"] == has_bars]
        ax.scatter(xs, ys, s=12, color=color, alpha=0.75, label=label, edgecolor="none")
    lim = max(max(r["resolvable"] for r in rows), max(r["gap"] for r in rows)) * 100 * 1.1
    ax.plot([0, lim], [0, lim], color="black", linewidth=0.6, linestyle="--")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("gap the stated episodes can resolve (points)", fontsize=7.5)
    ax.set_ylabel("printed gap (points)", fontsize=7.5)
    ax.tick_params(labelsize=7)
    ax.text(lim * 0.55, lim * 0.08, "below resolution", fontsize=7, color="#555")
    ax.legend(fontsize=6.5, frameon=False, loc="upper left")
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "fig_protocol.pdf"), bbox_inches="tight")
    fig.savefig("out/aamas/fig_protocol.png", dpi=160, bbox_inches="tight")
    print("wrote", os.path.join(OUT, "fig_protocol.pdf"))


if __name__ == "__main__":
    main()
