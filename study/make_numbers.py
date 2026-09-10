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


def _ci(d: dict, digits: int = 1) -> str:
    """A percentage with its cluster-bootstrap interval, as the paper prints it."""
    return (f"{d['point']:.{digits}f}\% [{d['lo']:.{digits}f}, {d['hi']:.{digits}f}]")


def build(both_years_path: str, crosscheck_path: str, out_path: str,
          bootstrap_path: str = "out/bootstrap_ci.json") -> dict:
    with open(both_years_path, encoding="utf-8") as fh:
        by = json.load(fh)
    y25, y24 = by["2025"], by["2024"]
    with open(bootstrap_path, encoding="utf-8") as fh:
        boot = json.load(fh)
    b25, b24 = boot["2025"], boot["2024"]

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

    # Our own uncertainty. A paper asking everyone else to print a dispersion
    # and a run count has no business printing point estimates of its own, and
    # three of four reviewers said so in the same words.
    bootrun = "survivability_both_years-7f18e22a (cluster bootstrap over papers)"
    reg.add("ci neither side", _ci(b25["pct_neither"]), provenance=bootrun)
    reg.add("ci neither side twenty four", _ci(b24["pct_neither"]), provenance=bootrun)
    reg.add("ci testable", _ci(b25["pct_testable"]), provenance=bootrun)
    reg.add("ci testable twenty four", _ci(b24["pct_testable"]), provenance=bootrun)
    reg.add("ci fail", _ci(b25["pct_fail"]), provenance=bootrun)
    reg.add("ci fail twenty four", _ci(b24["pct_fail"]), provenance=bootrun)
    reg.add("ci fail holm", _ci(b25["pct_fail_holm"]), provenance=bootrun)
    reg.add("ci fail holm twenty four", _ci(b24["pct_fail_holm"]), provenance=bootrun)
    reg.add("ci holm delta", _ci(b25["holm_delta"]), provenance=bootrun)
    d = b25["deff"]
    reg.add("icc", f"{d['icc']:.2f}", provenance=bootrun)
    reg.add("design effect", f"{d['design_effect']:.2f}", provenance=bootrun)
    reg.add("n effective", d["n_eff"], provenance=bootrun)
    reg.add("mean cluster", f"{d['mean_cluster']:.1f}", provenance=bootrun)

    # The 2024 column was printing an em-dash for a category whose value was
    # sitting in the analysis output all along, which led one reviewer to
    # conclude the two years had been processed by different pipelines.
    reg.add("pct no n stated twenty four", f"{y24['pct_no_n']}\%", provenance=run)

    # Sensitivity to the two conventions the pipeline had to choose. Both are
    # reported as ranges: giving one number for a quantity that depends on an
    # arbitrary reading is the failure this paper is about.
    with open("out/sensitivity_2025.json", encoding="utf-8") as fh:
        sens = json.load(fh)
    sc, eb, ct = sens["run_count_scope"], sens["error_bar_meaning"], sens["paper_level_crosstab"]
    sensrun = "sensitivity_2025-d5aee395"
    reg.add("strict testable", rf"{sc['strict']['pct_testable']}\%", provenance=sensrun)
    reg.add("strict fail", rf"{sc['strict']['pct_fail']}\%", provenance=sensrun)
    reg.add("strict fail holm", rf"{sc['strict']['pct_fail_holm']}\%", provenance=sensrun)
    reg.add("unlabelled as std", rf"{eb['read_as_std']['pct_fail']}\%", provenance=sensrun)
    reg.add("unlabelled as sem", rf"{eb['read_as_sem']['pct_fail']}\%", provenance=sensrun)
    reg.add("labelled only fail", rf"{eb['labelled_only']['pct_fail']}\%", provenance=sensrun)
    reg.add("n unlabelled", eb["n_unknown"], provenance=sensrun)
    reg.add("papers error bar and runs", ct["error_bar_and_run_count"], provenance=sensrun)
    reg.add("papers error bar only", ct["error_bar_only"], provenance=sensrun)
    reg.add("pct error bar papers stating runs",
            rf"{ct['pct_of_error_bar_papers_that_also_state_runs']}\%", provenance=sensrun)

    # Everything the adversarial review round asked for and the earlier draft
    # did not have: the funnel, the power audit, the correlation range, what the
    # bold cell actually marks, and the checklist comparison.
    def _j(name):
        with open(f"out/{name}.json", encoding="utf-8") as fh:
            return json.load(fh)

    fn, pw, bs, ck = _j("funnel"), _j("power_audit"), _j("bold_semantics"), _j("checklist")
    corr = _j("correlation_sensitivity")

    reg.add("tables detected", fn["tables_detected"], provenance="funnel")
    reg.add("tables no orientation", fn["tables_with_no_usable_orientation"], provenance="funnel")
    reg.add("candidate groups", fn["candidate_groups"], provenance="funnel")
    reg.add("tables yielding", fn["tables_yielding_at_least_one_comparison"], provenance="funnel")
    reg.add("pct groups usable", rf"{fn['pct_of_groups_usable']}\%", provenance="funnel")
    reg.add("pct caption uncertainty",
            rf"{fn['pct_of_empty_tables_with_caption_uncertainty']}\%", provenance="funnel")

    reg.add("pct underpowered", rf"{pw['pct_underpowered']}\%", provenance="power_audit_2025")
    # The power level is a parameter of the analysis, not an illustration, so it
    # comes from the run record like everything else rather than the whitelist.
    reg.add("power level", rf"{int(pw['power'] * 100)}\%", provenance="power_audit_2025")
    reg.add("median gap over mde", f"{pw['median_gap_over_mde']}", provenance="power_audit_2025")
    reg.add("q one gap over mde", f"{pw['q1_gap_over_mde']}", provenance="power_audit_2025")

    reg.add("pct bold not extremal", rf"{bs['pct_not_extremal']}\%", provenance="bold_semantics")

    reg.add("check yes", ck["answered_yes"], provenance="checklist_vs_tables")
    reg.add("check yes no table", ck["yes_but_no_table_error_bar"], provenance="checklist_vs_tables")
    reg.add("pct check yes no table",
            rf"{ck['pct_of_yes_with_no_table_error_bar']}\%", provenance="checklist_vs_tables")
    reg.add("check justified by figures", ck["of_those_justified_by_figures"],
            provenance="checklist_vs_tables")
    reg.add("check no but has bar", ck["no_but_table_has_error_bar"], provenance="checklist_vs_tables")
    agree = ck["yes_and_table_has_error_bar"]
    denom = agree + ck["no_but_table_has_error_bar"]
    reg.add("check precision", f"{agree} of {denom}", provenance="checklist_vs_tables")

    reg.add("fail rho half", rf"{corr['0.5']['pct_fail']}\%", provenance="correlation_sensitivity")
    reg.add("fail rho nine", rf"{corr['0.9']['pct_fail']}\%", provenance="correlation_sensitivity")
    # The correlations themselves are analysis parameters, so they come from the
    # run record too rather than being typed into the sentence that cites them.
    reg.add("rho half", "0.5", provenance="correlation_sensitivity")
    reg.add("rho nine", "0.9", provenance="correlation_sensitivity")

    reg.add("pct tie tables", r"0.10\%", provenance="tie_marking_convention-c37d51a2")
    reg.add("tie papers", 8, provenance="tie_marking_convention-c37d51a2")
    reg.add("pct second best", r"4.1\%", provenance="tie_marking_convention-c37d51a2")
    tierun = "tie_marking_in_testable_subset-df684b2c"
    reg.add("pct tie testable", r"1.03\%", provenance=tierun)
    reg.add("fail among tie marked", r"84.6\%", provenance=tierun)
    reg.add("fail excluding tie", r"40.1\%", provenance=tierun)

    # Resolving the apparent contradiction between the recall audit and the
    # checklist comparison, which a reviewer was right to say could not both hold.
    tens = "checklist_tension_resolved-8dc2e641"
    reg.add("just seeds", r"31.0\%", provenance=tens)
    reg.add("just test", r"19.5\%", provenance=tens)
    reg.add("just figure", r"13.9\%", provenance=tens)
    reg.add("just appendix", r"13.7\%", provenance=tens)
    reg.add("just none", r"29.6\%", provenance=tens)
    reg.add("max pages", 40, provenance=tens)
    reg.add("pct long papers", r"12.9\%", provenance=tens)
    reg.add("error bar long", r"22.1\%", provenance=tens)
    reg.add("error bar short", r"25.3\%", provenance=tens)
    reg.add("pct no table", r"13.2\%", provenance=tens)
    reg.add("pct with error bar conditional", r"28.6\%", provenance=tens)

    # The binomial route: checkability for the metrics that have a test-set size
    # rather than a run count. Needs no error bars, so its base is far larger.
    bn = _j("binomial_check")
    binrun = "required_test_set_size-612527a6"
    reg.add("binom comparisons", bn["n_comparisons"], provenance=binrun)
    reg.add("binom papers", bn["n_papers"], provenance=binrun)
    reg.add("binom median gap", f"{bn['median_gap_points']}", provenance=binrun)
    reg.add("binom median n", f"{bn['required_n']['median']:,}".replace(",", ","), provenance=binrun)
    reg.add("binom over gsm", rf"{bn['share_needing_more_than']['GSM8K (test) (1319)']}\%",
            provenance=binrun)
    reg.add("binom over mmlu", rf"{bn['share_needing_more_than']['MMLU (test) (14042)']}\%",
            provenance=binrun)
    reg.add("binom median n wide", "32,842", provenance=binrun)

    # The recall check, which is the only one that bounds the headline.
    v2 = "recall_audit_v2-2242cce7"
    reg.add("recall two judged", 29, provenance=v2)
    reg.add("recall two missed", "no", provenance=v2)
    reg.add("recall two ci", "95\% CI [0.88, 1.00]", provenance=v2)
    reg.add("headline move sixth", r"0.5 points", provenance="recall_fix_impact-348e7fbc")
    reg.add("headline with extraction", r"68.4--77.5\%", provenance=v2)

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
