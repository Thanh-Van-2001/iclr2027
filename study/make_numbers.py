"""Every number the paper prints, defined once, from a run record.

The paper writes ``\nPctNeitherSide`` and never ``78.0``. If an analysis is
rerun and a figure moves, the macro moves with it and the text cannot silently
disagree with the table. A number typed by hand into the LaTeX is caught by
``paperengine.provenance``'s audit and fails the build.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from paperengine.provenance import NumberRegistry, load_runs  # noqa: E402


def build(both_years_path: str, crosscheck_path: str, out_path: str) -> dict:
    with open(both_years_path, encoding="utf-8") as fh:
        by = json.load(fh)
    y25, y24 = by["2025"], by["2024"]

    reg = NumberRegistry()
    run = "survivability_both_years-7f18e22a"

    # Corpus
    reg.add("papers total", y24["papers"] + y25["papers"], provenance=run)
    reg.add("papers twenty five", y25["papers"], provenance=run)
    reg.add("papers twenty four", y24["papers"], provenance=run)
    reg.add("comparisons total", y24["comparisons"] + y25["comparisons"], provenance=run)
    reg.add("comparisons twenty five", y25["comparisons"], provenance=run)
    reg.add("comparisons twenty four", y24["comparisons"], provenance=run)

    # The headline, which is the same in both years
    reg.add("pct neither side", f"{y25['pct_neither']}\\%", provenance=run)
    reg.add("pct neither side twenty four", f"{y24['pct_neither']}\\%", provenance=run)
    reg.add("pct with error bar", f"{y25['pct_err']}\\%", provenance=run)
    reg.add("pct with error bar twenty four", f"{y24['pct_err']}\\%", provenance=run)
    reg.add("pct stating n", f"{y25['pct_n']}\\%", provenance=run)
    reg.add("pct stating n twenty four", f"{y24['pct_n']}\\%", provenance=run)
    reg.add("pct no n stated", f"{y25['pct_no_n']}\\%", provenance=run)
    reg.add("pct one side only", f"{y25['pct_one']}\\%", provenance=run)
    reg.add("pct testable", f"{y25['pct_testable']}\\%", provenance=run)
    reg.add("pct testable twenty four", f"{y24['pct_testable']}\\%", provenance=run)

    # Survival
    reg.add("n testable", y25["n_testable"], provenance=run)
    reg.add("n testable twenty four", y24["n_testable"], provenance=run)
    reg.add("papers contributing", y25["papers_testable"], provenance=run)
    reg.add("papers contributing twenty four", y24["papers_testable"], provenance=run)
    reg.add("pct fail", f"{y25['pct_fail']}\\%", provenance=run)
    reg.add("pct fail twenty four", f"{y24['pct_fail']}\\%", provenance=run)
    reg.add("pct fail holm", f"{y25['pct_fail_holm']}\\%", provenance=run)
    reg.add("pct fail holm twenty four", f"{y24['pct_fail_holm']}\\%", provenance=run)
    reg.add("gap failing", f"{y25['gap_fail']}\\%", provenance=run)
    reg.add("gap passing", f"{y25['gap_pass']}\\%", provenance=run)
    reg.add("gap failing twenty four", f"{y24['gap_fail']}\\%", provenance=run)
    reg.add("gap passing twenty four", f"{y24['gap_pass']}\\%", provenance=run)

    # How much multiplicity alone moves the verdict
    moved = round(y25["pct_fail_holm"] - y25["pct_fail"], 1)
    reg.add("pct moved by multiplicity", f"{moved}\\%", provenance=run)
    reg.add("one in n moved by multiplicity", int(round(100.0 / moved)) if moved else 0,
            provenance=run)

    # Extractor validation
    with open(crosscheck_path, encoding="utf-8") as fh:
        cc = json.load(fh)["summary"]
    reg.add("crosscheck confirmation", f"{round(100 * cc['confirmation_rate'], 1)}\\%",
            provenance="extractor_crosscheck_pilot-8e982993")
    reg.add("crosscheck values", cc["primary_values_with_dispersion"],
            provenance="extractor_crosscheck_pilot-8e982993")

    reg.write(out_path)
    return reg.manifest()


def main(argv=None) -> int:
    out = os.path.join("paper", "submission", "numbers.tex")
    manifest = build("out/both_years.json", "out/crosscheck_pilot.json", out)
    print(f"wrote {len(manifest)} macros to {out}")
    for macro, meta in list(manifest.items())[:8]:
        print(f"  {macro:<34} = {meta['value']}")
    print(f"  ... and {max(0, len(manifest) - 8)} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
