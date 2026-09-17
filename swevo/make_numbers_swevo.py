"""Every number the metaheuristics paper prints, as a LaTeX macro from a run
record. Reads out/swevo/*.json and writes paper/swevo/numbers.tex."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine.provenance import NumberRegistry  # noqa: E402

PCT = chr(92) + "%"


def _j(name: str, base: str = "out/swevo"):
    with open(os.path.join(base, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ci(d: dict, digits: int = 1) -> str:
    return f"{d['point']:.{digits}f}{PCT} [{d['lo']:.{digits}f}, {d['hi']:.{digits}f}]"


def _pct(x) -> str:
    return f"{x}{PCT}"


def _rates_block(reg, prefix: str, d: dict, run: str):
    """Macros for one _rates() record: n, papers, shares, failure, intervals."""
    reg.add(f"{prefix} n", d["n"], provenance=run)
    reg.add(f"{prefix} papers", d["papers"], provenance=run)
    reg.add(f"{prefix} testable n", d["n_testable"], provenance=run)
    reg.add(f"{prefix} testable papers", d["testable_papers"], provenance=run)
    reg.add(f"{prefix} neither", _pct(d["pct_neither"]), provenance=run)
    reg.add(f"{prefix} testable", _pct(d["pct_testable"]), provenance=run)
    reg.add(f"{prefix} fail", _pct(d["pct_fail"]) if d["pct_fail"] is not None else "--", provenance=run)
    reg.add(f"{prefix} fail holm", _pct(d["pct_fail_holm"]) if d["pct_fail_holm"] is not None else "--", provenance=run)
    ci = d.get("ci_fail")
    reg.add(f"{prefix} fail ci", f"[{ci[0]}, {ci[1]}]" if ci else "--", provenance=run)
    for k in ("ci_neither", "ci_testable"):
        if d.get(k):
            reg.add(f"{prefix} {k.replace('_', ' ')}", f"[{d[k][0]}, {d[k][1]}]", provenance=run)


def build(out_path: str) -> dict:
    ex = _j("extra")
    reg = NumberRegistry()
    run = "swevo_make_all"
    s, b = ex["summary"], ex["bootstrap"]

    co = ex["corpus"]
    reg.add("o listed", co["listed"], provenance=run)
    reg.add("o listed srep", co["listed_in_corpus_journal"], provenance=run)
    reg.add("o parsed", co["parsed"], provenance=run)
    for j, n in co["by_journal"].items():
        reg.add("o journal " + j.lower().replace("&", "and"), n, provenance=run)

    reg.add("a papers", s["papers"], provenance=run)
    reg.add("a comparisons", s["comparisons"], provenance=run)
    reg.add("a comparisons per table", int(s["median_comparisons_per_table"]), provenance=run)
    reg.add("a pct neither", _pct(s["pct_neither"]), provenance=run)
    reg.add("a pct neither ci", _ci(b["pct_neither"]), provenance=run)
    reg.add("a pct one side", _pct(s["pct_one"]), provenance=run)
    reg.add("a pct no n", _pct(s["pct_no_n"]), provenance=run)
    reg.add("a pct testable", _pct(s["pct_testable"]), provenance=run)
    reg.add("a pct testable ci", _ci(b["pct_testable"]), provenance=run)
    reg.add("a n testable", s["n_testable"], provenance=run)
    reg.add("a papers testable", s["papers_testable"], provenance=run)
    reg.add("a pct fail", _pct(s["pct_fail"]), provenance=run)
    reg.add("a pct fail ci", _ci(b["pct_fail"]), provenance=run)
    reg.add("a pct fail holm", _pct(s["pct_fail_holm"]), provenance=run)
    reg.add("a pct fail holm ci", _ci(b["pct_fail_holm"]), provenance=run)
    reg.add("a pct papers err", _pct(s["pct_err"]), provenance=run)
    reg.add("a pct papers runs", _pct(s["pct_n"]), provenance=run)
    reg.add("a median runs", int(s["median_runs"]) if s.get("median_runs") else "--", provenance=run)
    reg.add("a claim papers", len({c["paper"] for c in _j("analysis")["_comparisons"]}), provenance=run)
    reg.add("a tables detected", ex["funnel"]["tables_detected"], provenance=run)
    reg.add("a tables yielding", ex["funnel"]["tables_with_comparison"], provenance=run)
    for year, d in ex["by_year"].items():
        tag = {"2024": "twenty four", "2025": "twenty five"}[year]
        ys, yb = d["summary"], d["bootstrap"]
        reg.add(f"a papers {tag}", ys["papers"], provenance=run)
        reg.add(f"a comparisons {tag}", ys["comparisons"], provenance=run)
        reg.add(f"a neither {tag} ci", _ci(yb["pct_neither"]), provenance=run)
        reg.add(f"a testable {tag} ci", _ci(yb["pct_testable"]), provenance=run)
        reg.add(f"a fail {tag} ci", _ci(yb["pct_fail"]), provenance=run)

    # kinds, metaphor naming, benchmark suite (from the classifier)
    for group, prefix in (("kinds", "k"), ("metaphor", "m"), ("suite", "b")):
        g = ex.get(group, {})
        for _, rows in g.items():
            for lab, d in rows.items():
                _rates_block(reg, f"{prefix} {lab.replace('_', ' ')}", d, run)
                reg.add(f"{prefix} {lab.replace('_', ' ')} labelled", d["papers_labelled"], provenance=run)
                reg.add(f"{prefix} {lab.replace('_', ' ')} claim papers", d["claim_papers"], provenance=run)
    for lab, n in ex.get("kind_counts", {}).items():
        reg.add(f"kc {lab.replace('_', ' ')}", n, provenance=run)
    for lab, n in ex.get("metaphor_counts", {}).items():
        reg.add(f"mc {lab}", n, provenance=run)

    st = ex.get("stat_tests", {})
    if st:
        reg.add("st testable papers", st["testable_papers"], provenance=run)
        reg.add("st naming", st["papers_naming_a_test"], provenance=run)
        reg.add("st naming pct", _pct(st["pct_papers_naming_a_test"]), provenance=run)
        for k, v in st["test_kinds_among_testable_papers"].items():
            reg.add(f"st kind {k.replace('_', ' ')}", v, provenance=run)
        reg.add("st markers", st["papers_with_plus_equal_minus"], provenance=run)
        _rates_block(reg, "st named", st["named"], run)
        _rates_block(reg, "st unnamed", st["unnamed"], run)
        reg.add("st all naming", st["all_papers_naming_a_test"], provenance=run)
        reg.add("st all papers", st["all_papers"], provenance=run)
        reg.add("st all naming pct", _pct(round(100 * st["all_papers_naming_a_test"] / max(st["all_papers"], 1), 1)), provenance=run)

    rc = ex.get("run_counts", {})
    if rc:
        for n_, cnt in rc["parser_counts"][:6]:
            reg.add(f"rc parser {n_}", cnt, provenance=run)
        for n_, cnt in rc["scan_counts"][:6]:
            reg.add(f"rc scan {n_}", cnt, provenance=run)
        reg.add("rc papers stating", rc["papers_stating_runs_in_text"], provenance=run)
        reg.add("rc papers scanned", rc["papers_scanned"], provenance=run)
        reg.add("rc papers stating pct", _pct(rc["pct_papers_stating_runs"]), provenance=run)
        reg.add("rc agree", rc["parser_scan_agree"], provenance=run)
        reg.add("rc disagree", rc["parser_scan_disagree"], provenance=run)
        _rates_block(reg, "rc thirty", rc["thirty_runs"], run)
        reg.add("rc thirty share", _pct(rc["pct_testable_at_thirty"]), provenance=run)

    cc = ex.get("cites", {})
    if cc:
        for k, v in cc["counts"].items():
            reg.add(f"cc {k.replace('_', ' ')}", v, provenance=run)
        reg.add("cc citing papers", cc["citing_papers"], provenance=run)
        reg.add("cc claim papers", cc["claim_papers"], provenance=run)
        _rates_block(reg, "cc citing", cc["citing"], run)
        _rates_block(reg, "cc not citing", cc["not_citing"], run)
        reg.add("cc citing name a test", cc["citing_name_a_test"], provenance=run)
        reg.add("cc citing state runs", cc["citing_state_runs"], provenance=run)

    hs = ex["headline_span"]
    nice = {"rho_0.5": "rho half", "rho_0.9": "rho nine tenths", "caption_or_page_run_count": "caption or page",
            "caption_run_count_only": "caption only", "holm_family_all_groups": "holm all groups",
            "run_count_from_caption": "runs from caption", "run_count_from_page": "runs from page",
            "run_count_from_paper": "runs from paper", "run_count_from_none": "runs from none"}
    for name, row in hs["rows"].items():
        key = nice.get(name, name.replace("_", " "))
        reg.add(f"span {key} fail", _pct(row["pct_fail"]), provenance=run)
        reg.add(f"span {key} fail holm", _pct(row["pct_fail_holm"]), provenance=run)
        if row.get("n") is not None:
            reg.add(f"span {key} n", row["n"], provenance=run)
        if row.get("ci_fail"):
            ci = [b["pct_fail"]["lo"], b["pct_fail"]["hi"]] if name == "as_reported" else row["ci_fail"]
            reg.add(f"span {key} fail ci", f"[{ci[0]:.1f}, {ci[1]:.1f}]", provenance=run)
            reg.add(f"span {key} papers", row["papers"], provenance=run)
    reg.add("span lo", _pct(hs["span"][0]), provenance=run)
    reg.add("span hi", _pct(hs["span"][1]), provenance=run)

    rd = ex["readings"]
    for key, d in (("dup removed", rd["without_duplicates"]), ("dup only", rd["duplicates"]),
                   ("merged removed", rd["without_merged"]), ("merged only", rd["merged_caption_tables"]),
                   ("artefacts removed", rd["without_artefacts"]),
                   ("own row removed", rd["without_own_row"]), ("own row only", rd["own_row_tables"]),
                   ("ablation removed", rd["without_ablation"]), ("ablation only", rd["ablation_tables"]),
                   ("zero removed", rd["zero_deviation"]["without_zero"]),
                   ("copies removed", rd["without_exact_copies"]), ("copies only", rd["exact_copies"]),
                   ("all artefacts removed", rd["without_all_artefacts"]),
                   ("big n removed", rd["without_run_count_above_30"]), ("big n only", rd["run_count_above_30"]),
                   ("median removed", rd["without_median_or_iqm"]), ("median only", rd["median_or_iqm_captions"])):
        _rates_block(reg, f"r {key}", d, run)
    reg.add("r own row tables", rd["own_row_tables"]["tables"], provenance=run)
    reg.add("r merged tables", rd["merged_caption_tables"]["tables"], provenance=run)
    reg.add("r copies papers", rd["exact_copies"]["papers_with_copies"], provenance=run)
    z = rd["zero_deviation"]
    reg.add("r zero n", z["n_testable_with_a_zero"], provenance=run)
    reg.add("r zero both", z["n_both_zero"], provenance=run)
    reg.add("r zero fail", _pct(z["pct_fail_among_zero"]) if z["pct_fail_among_zero"] is not None else "--", provenance=run)

    pp = ex["per_paper_failure"]
    reg.add("pp papers", pp["papers"], provenance=run)
    reg.add("pp any fail", _pct(pp["pct_papers_any_fail"]), provenance=run)
    reg.add("pp all fail", _pct(pp["pct_papers_all_fail"]), provenance=run)
    reg.add("pp median", _pct(pp["median_paper_rate"]), provenance=run)
    reg.add("pp q one", _pct(pp["q1_paper_rate"]), provenance=run)
    reg.add("pp q three", _pct(pp["q3_paper_rate"]), provenance=run)
    reg.add("pp mean", _pct(pp["mean_of_paper_rates"]), provenance=run)
    reg.add("pp top ten share", _pct(pp["top10_share"]), provenance=run)
    reg.add("ppd top ten share", _pct(ex["per_paper_failure_dedup"]["top10_share"]), provenance=run)
    dd = ex["ddof_reading"]
    reg.add("ddof n", dd["n"], provenance=run)
    reg.add("ddof fail", _pct(dd["pct_fail"]), provenance=run)

    ebm = ex["error_bar_meaning"]
    reg.add("bars unlabelled n", ebm["n_unknown"], provenance=run)
    reg.add("bars unlabelled pct", _pct(ebm["pct_of_error_barred_that_are_unlabelled"]), provenance=run)
    reg.add("bars labelled fail", _pct(ebm["labelled_only"]["pct_fail"]), provenance=run)
    reg.add("bars as sem fail", _pct(ebm["read_as_sem"]["pct_fail"]), provenance=run)
    reg.add("bars as std fail", _pct(ebm["read_as_std"]["pct_fail"]), provenance=run)
    rcs = ex["run_count_scope"]
    reg.add("strict testable", _pct(rcs["strict"]["pct_testable"]), provenance=run)
    reg.add("strict fail", _pct(rcs["strict"]["pct_fail"]), provenance=run)
    reg.add("strict n", rcs["strict"]["n"], provenance=run)
    hf = ex["holm_families"]
    reg.add("holm median family", hf["median_family_size"], provenance=run)
    reg.add("holm pct in families over five", _pct(hf["pct_in_families_over_five"]), provenance=run)
    sd = ex["subset_direction"]
    for band, d in sd["by_runs"].items():
        key = {"le3": "le three", "4to5": "four to five", "ge6": "ge six", "6to30": "six to thirty", "gt30": "gt thirty"}.get(band, band)
        reg.add(f"runs {key} n", d["n"], provenance=run)
        reg.add(f"runs {key} fail", _pct(d["pct_fail"]), provenance=run)
        reg.add(f"runs {key} fail ci", f"{d['pct_fail']}{PCT} [{d['ci_fail'][0]}, {d['ci_fail'][1]}]", provenance=run)
    ua = ex["uncertainty_anywhere"]
    for k, v in ua.items():
        if isinstance(v, (int, float)):
            reg.add("ua " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)
    cap = ex["caption_assertion"]
    _rates_block(reg, "cap asserting", cap["asserting"], run)
    _rates_block(reg, "cap describing", cap["describing"], run)
    bl = ex["big_n_and_largest"]
    reg.add("bign papers", len(bl["big_n_papers"]), provenance=run)
    lg = bl["largest"]
    reg.add("largest n", lg["n"], provenance=run)
    reg.add("largest pct of testable", _pct(lg["pct_of_testable"]), provenance=run)
    reg.add("largest fail", _pct(lg["pct_fail"]), provenance=run)
    reg.add("largest runs", lg["n_runs"], provenance=run)
    fu = ex["funnel"]
    for k, v in fu.items():
        if isinstance(v, (int, float)):
            reg.add("fu " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)
    bs = ex["bold_semantics"]
    for k, v in bs.items():
        if isinstance(v, (int, float)):
            reg.add("bs " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)

    reg.write(out_path)
    return reg.manifest()


def main() -> int:
    out = os.path.join("paper", "swevo", "numbers.tex")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    m = build(out)
    print(f"wrote {len(m)} macros to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
