"""Every number the AAMAS paper prints, as a LaTeX macro from a run record.

Reads out/aamas/*.json (written by aamas/make_all_aamas.py and the audit
scorers) and writes paper/aamas/numbers.tex. The paper never types a number.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine.provenance import NumberRegistry  # noqa: E402


def _j(name: str, base: str = "out/aamas"):
    with open(os.path.join(base, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _ci(d: dict, digits: int = 1) -> str:
    return f"{d['point']:.{digits}f}\\% [{d['lo']:.{digits}f}, {d['hi']:.{digits}f}]"


def _pct(x) -> str:
    return f"{x}\\%"


def _frac(d: dict, k="correct", n="n") -> str:
    return f"{d[k]} of {d[n]}"


def _pct_ci(d: dict) -> str:
    return f"{d['pct']}\\% [{d['ci'][0]}, {d['ci'][1]}]"


def build(out_path: str) -> dict:
    ex = _j("extra")
    reg = NumberRegistry()
    run = "aamas_make_all"
    s, b = ex["summary"], ex["bootstrap"]

    # corpus and census
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
    reg.add("a median runs", int(s["median_runs"]), provenance=run)
    reg.add("a gap fail", _pct(s["gap_fail"]), provenance=run)
    reg.add("a gap pass", _pct(s["gap_pass"]), provenance=run)
    reg.add("a design effect", f"{b['deff']['design_effect']:.1f}", provenance=run)
    reg.add("a mean cluster", f"{b['deff']['mean_cluster']:.1f}", provenance=run)

    # per year
    for year, d in ex["by_year"].items():
        ys, yb = d["summary"], d["bootstrap"]
        tag = {"2024": "twenty four", "2025": "twenty five", "2026": "twenty six"}[year]
        reg.add(f"a papers {tag}", ys["papers"], provenance=run)
        reg.add(f"a comparisons {tag}", ys["comparisons"], provenance=run)
        reg.add(f"a neither {tag}", _pct(ys["pct_neither"]), provenance=run)
        reg.add(f"a neither {tag} ci", _ci(yb["pct_neither"]), provenance=run)
        reg.add(f"a testable {tag}", _pct(ys["pct_testable"]), provenance=run)
        reg.add(f"a n testable {tag}", ys["n_testable"], provenance=run)
        reg.add(f"a fail {tag}", _pct(ys["pct_fail"]), provenance=run)
        reg.add(f"a fail {tag} ci", _ci(yb["pct_fail"]), provenance=run)
        reg.add(f"a papers err {tag}", _pct(ys["pct_err"]), provenance=run)
        reg.add(f"a papers runs {tag}", _pct(ys["pct_n"]), provenance=run)

    # per community
    comm = ex.get("by_community", {})
    for lab, d in comm.items():
        if lab.startswith("_"):
            continue
        cs_ = d["summary"]
        name = lab.replace("_", " ")
        reg.add(f"c {name} papers", cs_["papers"], provenance=run)
        reg.add(f"c {name} comparisons", cs_["comparisons"], provenance=run)
        if cs_["comparisons"]:
            reg.add(f"c {name} claim papers", _pct(d["pct_papers_with_table_claim"]), provenance=run)
            reg.add(f"c {name} neither", _pct(cs_["pct_neither"]), provenance=run)
            reg.add(f"c {name} testable", _pct(cs_["pct_testable"]), provenance=run)
            reg.add(f"c {name} n testable", cs_["n_testable"], provenance=run)
            reg.add(f"c {name} fail", _pct(cs_["pct_fail"]) if cs_["n_testable"] >= 20 else "--", provenance=run)
            reg.add(f"c {name} papers err", _pct(cs_["pct_err"]), provenance=run)
    if "_unlabelled_papers" in comm:
        reg.add("c unlabelled papers", comm["_unlabelled_papers"], provenance=run)

    # side by side with the NeurIPS/ICML sample
    ml = ex["side_by_side"]["neurips_icml_2025"]
    reg.add("ml papers", ml["papers"], provenance="survivability_both_years")
    reg.add("ml comparisons", ml["comparisons"], provenance="survivability_both_years")
    reg.add("ml pct neither", _pct(ml["pct_neither"]), provenance="survivability_both_years")
    reg.add("ml pct testable", _pct(ml["pct_testable"]), provenance="survivability_both_years")
    reg.add("ml pct fail", _pct(ml["pct_fail"]), provenance="survivability_both_years")
    reg.add("ml pct fail holm", _pct(ml["pct_fail_holm"]), provenance="survivability_both_years")
    reg.add("ml pct papers err", _pct(ml["pct_err"]), provenance="survivability_both_years")
    reg.add("ml pct papers runs", _pct(ml["pct_n"]), provenance="survivability_both_years")
    reg.add("ml median runs", int(ml["median_runs"]), provenance="survivability_both_years")
    reg.add("ml comparisons per table", int(ml["median_comparisons_per_table"]), provenance="survivability_both_years")
    ml24 = ex["side_by_side"]["neurips_icml_2024"]
    reg.add("ml papers twenty four", ml24["papers"], provenance="survivability_both_years")
    reg.add("ml testable papers", ml["papers_testable"], provenance="survivability_both_years")

    # conventions: the headline span
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
    reg.add("span lo", _pct(hs["span"][0]), provenance=run)
    reg.add("span hi", _pct(hs["span"][1]), provenance=run)

    rcs = ex["run_count_scope"]
    reg.add("strict testable", _pct(rcs["strict"]["pct_testable"]), provenance=run)
    reg.add("strict fail", _pct(rcs["strict"]["pct_fail"]), provenance=run)
    reg.add("strict n", rcs["strict"]["n"], provenance=run)
    ebm = ex["error_bar_meaning"]
    reg.add("bars unlabelled n", ebm["n_unknown"], provenance=run)
    reg.add("bars unlabelled pct", _pct(ebm["pct_of_error_barred_that_are_unlabelled"]), provenance=run)
    reg.add("bars labelled fail", _pct(ebm["labelled_only"]["pct_fail"]), provenance=run)
    reg.add("bars as sem fail", _pct(ebm["read_as_sem"]["pct_fail"]), provenance=run)
    reg.add("bars as std fail", _pct(ebm["read_as_std"]["pct_fail"]), provenance=run)

    sd = ex["subset_direction"]
    for band, d in sd["by_runs"].items():
        key = {"le3": "le three", "4to5": "four to five", "ge6": "ge six"}.get(band, band)
        reg.add(f"runs {key} fail", _pct(d["pct_fail"]), provenance=run)
        reg.add(f"runs {key} n", d["n"], provenance=run)

    pa = ex["power_audit"]
    reg.add("power n", pa["n"], provenance=run)
    reg.add("power papers", pa["n_papers"], provenance=run)
    reg.add("power underpowered", _pct(pa["pct_underpowered"]), provenance=run)
    reg.add("power median ratio", f"{pa['median_gap_over_mde']:.2f}", provenance=run)
    reg.add("power level", _pct(int(round(100 * pa["power"]))), provenance=run)

    fn = ex["funnel"]
    reg.add("a tables detected", fn["tables_detected"], provenance=run)
    reg.add("a tables yielding", fn["tables_yielding_at_least_one_comparison"], provenance=run)
    reg.add("a groups candidate", fn["candidate_groups"], provenance=run)
    reg.add("a groups usable pct", _pct(fn["pct_of_groups_usable"]), provenance=run)
    reg.add("a empty tables caption uncertainty", fn["of_those_whose_caption_reports_uncertainty"], provenance=run)
    reg.add("a empty tables", fn["tables_with_no_cell_level_dispersion"], provenance=run)
    bs = ex["bold_semantics"]
    reg.add("a bold not extremal pct", _pct(bs["pct_not_extremal"]), provenance=run)
    reg.add("a bold single groups", bs["n_single_bold_groups"], provenance=run)
    reg.add("a bold topk", bs["topk_caption"], provenance=run)
    reg.add("a bold tied", bs["tied_with_rival"], provenance=run)
    tm = ex["tie_marking"]
    reg.add("tie pct tables second best", _pct(tm["pct_tables_marking_second_best"]), provenance=run)
    reg.add("tie n excluding", tm["n_testable_excluding_tie_marked"], provenance=run)
    reg.add("tie fail excluding", _pct(tm["fail_rate_excluding_tie_marked"]), provenance=run)
    hf = ex["holm_families"]
    reg.add("holm tables", hf["n_tables_with_testable"], provenance=run)
    reg.add("holm median family", hf["median_family_size"], provenance=run)
    reg.add("holm pct family one", _pct(hf["pct_family_size_1"]), provenance=run)
    reg.add("holm pct in families over five", _pct(hf["pct_testable_in_families_over_5"]), provenance=run)

    ef = ex["environment_families"]
    for name, d in ef.items():
        if name.startswith("_"):
            continue
        key = "env " + name.split(" (")[0].split(",")[0].lower()
        reg.add(f"{key} comparisons", d["comparisons"], provenance=run)
        reg.add(f"{key} papers", d["papers"], provenance=run)
        reg.add(f"{key} testable papers", d["testable_papers"], provenance=run)
        reg.add(f"{key} neither", _pct(d["pct_neither"]), provenance=run)
        reg.add(f"{key} testable", d["testable"], provenance=run)
        reg.add(f"{key} fail", _pct(d["pct_fail"]) if d["testable"] >= 20 else "--", provenance=run)
    reg.add("env named testable pct", _pct(ef["_any_named"]["pct_of_testable"]), provenance=run)
    reg.add("env named comparisons", ef["_any_named"]["comparisons"], provenance=run)
    exm = ex.get("example_three_seeds", {})
    if exm:
        def _g(v):
            return f"{v:g}"
        reg.add("ex winner", _g(exm["winner"]), provenance=run)
        reg.add("ex winner sd", _g(exm["winner_sd"]), provenance=run)
        reg.add("ex runner", _g(exm["runner_up"]), provenance=run)
        reg.add("ex runner sd", _g(exm["runner_sd"]), provenance=run)
        reg.add("ex gap", _g(exm["gap"]), provenance=run)
        reg.add("ex relative gap", _pct(exm["relative_gap_pct"]), provenance=run)
        reg.add("ex t", f"{exm['t']:.2f}", provenance=run)
        reg.add("ex df", f"{exm['df']:.1f}", provenance=run)
        reg.add("ex p", f"{exm['p']:.2f}", provenance=run)
        reg.add("ex n three seed failing", exm["n_three_seed_failing"], provenance=run)
    ca = ex.get("community_agreement", {})
    if ca:
        reg.add("comm agree n", ca["n"], provenance=run)
        reg.add("comm agree frac", f"{ca['agree']} of {ca['n']}", provenance=run)
        reg.add("comm agree", f"{ca['pct']}\\% [{ca['ci'][0]}, {ca['ci'][1]}]", provenance=run)
        reg.add("comm kappa", f"{ca['kappa']:.2f}", provenance=run)
    rd = ex["readings"]
    for key, d in (("dup removed", rd["without_duplicates"]), ("dup only", rd["duplicates"]),
                   ("own row removed", rd["without_own_row"]), ("own row only", rd["own_row_tables"]),
                   ("zero removed", rd["zero_deviation"]["without_zero"])):
        reg.add(f"r {key} n", d["n"], provenance=run)
        reg.add(f"r {key} testable n", d["n_testable"], provenance=run)
        reg.add(f"r {key} testable papers", d["testable_papers"], provenance=run)
        reg.add(f"r {key} neither", _pct(d["pct_neither"]), provenance=run)
        reg.add(f"r {key} testable", _pct(d["pct_testable"]), provenance=run)
        reg.add(f"r {key} fail", _pct(d["pct_fail"]) if d["pct_fail"] is not None else "--", provenance=run)
    reg.add("r own row tables", rd["own_row_tables"]["tables"], provenance=run)
    z = rd["zero_deviation"]
    reg.add("r zero n", z["n_testable_with_a_zero"], provenance=run)
    reg.add("r zero both", z["n_both_zero"], provenance=run)
    reg.add("r zero fail", _pct(z["pct_fail_among_zero"]) if z["pct_fail_among_zero"] is not None else "--", provenance=run)
    fc = rd["figure_caption_uncertainty"]
    reg.add("fig caption unc papers pct", _pct(fc["pct_papers"]), provenance=run)
    reg.add("fig caption unc testable papers", fc["testable_papers"], provenance=run)
    mm = ex.get("ml_main_text", {})
    if mm:
        m = mm["main_text"]
        reg.add("ml main comparisons", m["n"], provenance="analysis_2025")
        reg.add("ml main neither", _pct(m["pct_neither"]), provenance="analysis_2025")
        reg.add("ml main testable", _pct(m["pct_testable"]), provenance="analysis_2025")
        reg.add("ml main fail", _pct(m["pct_fail"]), provenance="analysis_2025")
        reg.add("ml main fail holm", _pct(m["pct_fail_holm"]), provenance="analysis_2025")
        reg.add("ml main testable papers", m["testable_papers"], provenance="analysis_2025")
        if "papers_with_main_text_bar_pct" in mm:
            reg.add("ml main papers err", _pct(mm["papers_with_main_text_bar_pct"]), provenance="analysis_2025")
    mlb = json.load(open("out/bootstrap_ci.json", encoding="utf-8"))["2025"]
    reg.add("ml pct neither ci", _ci(mlb["pct_neither"]), provenance="bootstrap_ci")
    reg.add("ml pct testable ci", _ci(mlb["pct_testable"]), provenance="bootstrap_ci")
    reg.add("ml pct fail ci", _ci(mlb["pct_fail"]), provenance="bootstrap_ci")
    reg.add("ml pct fail holm ci", _ci(mlb["pct_fail_holm"]), provenance="bootstrap_ci")
    mps = json.load(open("out/pipeline_stats_extracted_2025.json", encoding="utf-8"))
    reg.add("ml drawn", mps["drawn"], provenance="pipeline_stats_2025")
    reg.add("ml listed", sum(mps["listed"].values()) if isinstance(mps.get("listed"), dict) else mps.get("listed", 0), provenance="pipeline_stats_2025")
    ps_ = ex["protocol_span"]
    for name, d in ps_.items():
        if not isinstance(d, dict):
            continue
        key = name.replace("_", " ")
        reg.add(f"pspan {key} n", d["n_with_episode_count"], provenance=run)
        reg.add(f"pspan {key} papers", d["n_papers"], provenance=run)
        reg.add(f"pspan {key} below", _pct(d["pct_below"]) if d["pct_below"] is not None else "--", provenance=run)
    reg.add("pspan largest paper share", _pct(ps_["largest_paper_share_pct"]), provenance=run)
    reg.add("pspan per paper lo", _pct(ps_["per_paper_pct_below"][0]), provenance=run)
    reg.add("pspan per paper hi", _pct(ps_["per_paper_pct_below"][-1]), provenance=run)
    rb = ex.get("recall_breakdown", {})
    if rb:
        reg.add("rb pages reader groups", rb.get("pages_both", 0) + rb.get("pages_no_parser_table", 0) + rb.get("pages_parser_table_no_groups", 0), provenance=run)
        reg.add("rb pages no parser table", rb.get("pages_no_parser_table", 0), provenance=run)
        reg.add("rb pages parser no groups", rb.get("pages_parser_table_no_groups", 0), provenance=run)
        reg.add("rb pages both", rb.get("pages_both", 0), provenance=run)
        reg.add("rb groups no parser table", rb.get("groups_no_parser_table", 0), provenance=run)
        reg.add("rb groups parser no groups", rb.get("groups_parser_table_no_groups", 0), provenance=run)
        reg.add("rb groups both", rb.get("groups_both", 0), provenance=run)
        reg.add("rb top five share", _pct(rb["top5_pages_share_pct"]), provenance=run)
        reg.add("rb pages at cap", rb["pages_at_cap"], provenance=run)
    tb = ex["table_retention_bias"]
    reg.add("tb kept with bar", _pct(tb["pct_kept_with_bar"]), provenance=run)
    reg.add("tb discarded with bar", _pct(tb["pct_discarded_with_bar"]), provenance=run)
    bw = ex["protocol_resolution"]["below_among_barred"]
    reg.add("res barred welch pass", bw["welch_pass"], provenance=run)
    reg.add("res barred welch pass below", bw["welch_pass_below"], provenance=run)
    dr = ex["duplicate_table_records"]
    reg.add("a dup keys", dr["duplicate_keys"], provenance=run)
    reg.add("a dup identical", dr["identical_records"], provenance=run)
    reg.add("a dup comparisons", dr["comparisons_in_duplicates"], provenance=run)
    reg.add("a dup pct", _pct(dr["pct_of_comparisons"]), provenance=run)
    reg.add("a table keys", dr["table_keys"], provenance=run)

    # evaluation protocol
    ps = ex["protocol_stats"]
    reg.add("proto papers scanned", ps["papers_scanned"], provenance="aamas_protocol")
    reg.add("proto state episodes", ps["state_eval_episodes"], provenance="aamas_protocol")
    reg.add("proto state episodes pct", _pct(round(100 * ps["state_eval_episodes"] / max(ps["papers_scanned"], 1), 1)), provenance="aamas_protocol")
    reg.add("proto state seeds", ps["state_seeds"], provenance="aamas_protocol")
    reg.add("proto state seeds pct", _pct(round(100 * ps["state_seeds"] / max(ps["papers_scanned"], 1), 1)), provenance="aamas_protocol")
    if ps["episode_counts"]:
        reg.add("proto mode episodes", ps["episode_counts"][0][0], provenance="aamas_protocol")
        reg.add("proto mode episodes n", ps["episode_counts"][0][1], provenance="aamas_protocol")
    pr = ex["protocol_resolution"]
    reg.add("res rate like", pr["n_rate_like"], provenance=run)
    reg.add("res with k", pr["n_with_episode_count"], provenance=run)
    reg.add("res without k", pr["n_without_episode_count"], provenance=run)
    reg.add("res papers", pr["n_papers"], provenance=run)
    if pr["pct_below"] is not None:
        reg.add("res below", pr["below_resolution"], provenance=run)
        reg.add("res below pct", _pct(pr["pct_below"]), provenance=run)
        reg.add("res below ci", f"{pr['pct_below']}\\% [{pr['ci'][0]}, {pr['ci'][1]}]", provenance=run)
        reg.add("res below paper ci", f"[{pr['paper_ci'][0]}, {pr['paper_ci'][1]}]", provenance=run)
        reg.add("res median episodes", pr["median_episodes"], provenance=run)
        reg.add("res seed assumed one", _pct(pr["pct_seed_assumed_one"]), provenance=run)
        reg.add("res barless n", pr["below_among_bar_less"]["n"], provenance=run)
        reg.add("res barless below", pr["below_among_bar_less"]["below"], provenance=run)
        reg.add("res barred n", pr["below_among_barred"]["n"], provenance=run)
        reg.add("res barred below", pr["below_among_barred"]["below"], provenance=run)

    # audits, when scored
    if os.path.exists("out/aamas/gold_set.json"):
        g = _j("gold_set")
        gt = g["testable"]
        f = gt["fields"]
        reg.add("g testable n", gt["n_labelled"], provenance="aamas_gold_set")
        reg.add("g unboxed n", gt["n_unboxed"] + g["no_bar"]["n_unboxed"], provenance="aamas_gold_set")
        reg.add("g drawn n", gt["n_labelled"] + gt["n_unboxed"] + g["no_bar"]["n"] + g["no_bar"]["n_unboxed"], provenance="aamas_gold_set")
        reg.add("g claim frac", _frac(f["claim_and_values"]), provenance="aamas_gold_set")
        reg.add("g claim", _pct_ci(f["claim_and_values"]), provenance="aamas_gold_set")
        reg.add("g claim paper ci", f"[{f['claim_and_values']['paper_ci'][0]}, {f['claim_and_values']['paper_ci'][1]}]", provenance="aamas_gold_set")
        for name in ("bold_cell", "winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs", "disp_treatment", "orientation", "direction"):
            reg.add(f"g {name.replace('_', ' ')}", _pct_ci(f[name]), provenance="aamas_gold_set")
            reg.add(f"g {name.replace('_', ' ')} frac", _frac(f[name]), provenance="aamas_gold_set")
        v = gt["verdict_2x2"]
        both = v["both_fail"] + v["both_survive"]
        reg.add("g verdict frac", f"{both} of {gt['n_testable_under_both']}", provenance="aamas_gold_set")
        reg.add("g verdict", _pct(v["per_item_agreement"]), provenance="aamas_gold_set")
        reg.add("g fail reader", _pct(gt["failure_rate_reader_values"]), provenance="aamas_gold_set")
        reg.add("g fail pipe", _pct(gt["failure_rate_pipeline_values_same_items"]), provenance="aamas_gold_set")
        reg.add("g reader fail only", v["reader_fail_pipeline_survive"], provenance="aamas_gold_set")
        reg.add("g pipe fail only", v["pipeline_fail_reader_survive"], provenance="aamas_gold_set")
        un = gt.get("reader_untestable", {})
        reg.add("g untestable n", sum(d["n"] for d in un.values()), provenance="aamas_gold_set")
        nb = g["no_bar"]
        reg.add("g no bar n", nb["n"], provenance="aamas_gold_set")
        reg.add("g no bar results table frac", _frac(nb["results_table"]), provenance="aamas_gold_set")
        reg.add("g no bar not table", nb["results_table"]["n"] - nb["results_table"]["correct"], provenance="aamas_gold_set")
        reg.add("g no bar bold frac", _frac(nb["bold_cell"]), provenance="aamas_gold_set")
        reg.add("g no bar winner frac", _frac(nb["winner_mean"]), provenance="aamas_gold_set")
        reg.add("g no bar runner frac", _frac(nb["runner_mean"]), provenance="aamas_gold_set")
        reg.add("g no bar absent", _pct_ci(nb["error_bar_truly_absent"]), provenance="aamas_gold_set")
        reg.add("g no bar absent frac", _frac(nb["error_bar_truly_absent"]), provenance="aamas_gold_set")
        reg.add("g rival copied", _pct_ci(f["rival_copied"]) if "rival_copied" in f else "--", provenance="aamas_gold_set")
    if os.path.exists("out/aamas/gold_set_pages.json"):
        pg = _j("gold_set_pages")
        prun = "aamas_gold_set_pages"
        items = json.load(open("audits/aamas_pages/items.json", encoding="utf-8"))
        reg.add("pages read", pg["n_pages"], provenance=prun)
        reg.add("pages drawn", len(items), provenance=prun)
        reg.add("pages papers", len({it["paper"] for it in items}), provenance=prun)
        reg.add("pages tables", pg["n_results_tables"], provenance=prun)
        reg.add("pages tables with bar", _pct(pg["pct_results_tables_with_any_bar"]), provenance=prun)
        reg.add("pages reader groups", pg["reader"]["groups"], provenance=prun)
        reg.add("pages reader neither", f"{pg['reader']['pct_neither']}\\% [{pg['reader']['ci_neither'][0]}, {pg['reader']['ci_neither'][1]}]", provenance=prun)
        reg.add("pages reader testable", f"{pg['reader']['pct_testable']}\\% [{pg['reader']['ci_testable'][0]}, {pg['reader']['ci_testable'][1]}]", provenance=prun)
        reg.add("pages pipe groups", pg["pipeline_same_pages"]["groups"], provenance=prun)
        reg.add("pages pipe neither", _pct(pg["pipeline_same_pages"]["pct_neither"]), provenance=prun)
        reg.add("pages pipe testable", _pct(pg["pipeline_same_pages"]["pct_testable"]), provenance=prun)
        reg.add("pages reader found pct", _pct(pg["reader_groups_found_by_pipeline"]["pct"]), provenance=prun)
        reg.add("pages reader found", _pct_ci(pg["reader_groups_found_by_pipeline"]), provenance=prun)
        pc_ = pg["reader_groups_found_by_pipeline"].get("page_ci")
        if pc_:
            reg.add("pages reader found page ci", f"[{pc_[0]}, {pc_[1]}]", provenance=prun)
        reg.add("pages pipe found pct", _pct(pg["pipeline_groups_found_by_reader"]["pct"]), provenance=prun)
        reg.add("pages matched neither", _pct(pg["reader_groups_matched"]["pct_neither"]), provenance=prun)
        reg.add("pages unmatched neither", _pct(pg["reader_groups_unmatched"]["pct_neither"]), provenance=prun)
        ratio = pg["reader"]["pct_neither"] / pg["pipeline_same_pages"]["pct_neither"]
        reg.add("pages census ratio", f"{ratio:.2f}", provenance=prun)
        reg.add("a neither census scaled", _pct(round(s["pct_neither"] * ratio, 1)), provenance=prun)
        lo_r = pg["reader"]["ci_neither"][0] / pg["pipeline_same_pages"]["pct_neither"]
        hi_r = pg["reader"]["ci_neither"][1] / pg["pipeline_same_pages"]["pct_neither"]
        reg.add("a neither census scaled lo", _pct(round(s["pct_neither"] * lo_r, 1)), provenance=prun)
        reg.add("a neither census scaled hi", _pct(round(s["pct_neither"] * hi_r, 1)), provenance=prun)
        vs = pg["verdicts_same_pages"]
        reg.add("pages shared", vs["shared"]["n"], provenance=prun)
        reg.add("pages shared agree", vs["shared"]["agree"], provenance=prun)
        reg.add("pages reader only n", vs["reader_only"]["n"], provenance=prun)
        reg.add("pages reader only fails", vs["reader_only"]["fails"], provenance=prun)
        reg.add("pages pipe only n", vs["pipeline_only"]["n"], provenance=prun)
        reg.add("pages pipe only fails", vs["pipeline_only"]["fails"], provenance=prun)
        rf_ = pg["reader_failure"]
        reg.add("pages reader fail", f"{rf_['pct_fail']}\\% [{rf_['ci'][0]}, {rf_['ci'][1]}]", provenance=prun)
        reg.add("pages reader fail n", rf_["n"], provenance=prun)
    reg.write(out_path)
    return reg.manifest()


def main() -> int:
    out = os.path.join("paper", "aamas", "numbers.tex")
    m = build(out)
    print(f"wrote {len(m)} macros to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
