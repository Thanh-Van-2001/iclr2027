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


def _word(n: int) -> str:
    return ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"][n]


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
    reg.add("a tables yielding", ex["funnel"]["tables_yielding_at_least_one_comparison"], provenance=run)
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

    ka = ex.get("kind_agreement", {})
    if ka.get("papers"):
        reg.add("ka papers", ka["papers"], provenance=run)
        reg.add("ka agree", ka["agree"], provenance=run)
        reg.add("ka pct agree", _pct(ka["pct_agree"]), provenance=run)
        reg.add("ka ci agree", f"[{ka['ci_agree'][0]}, {ka['ci_agree'][1]}]", provenance=run)
        reg.add("ka kappa", f"{ka['kappa']:.2f}", provenance=run)
        reg.add("ka metaphor papers", ka["metaphor_papers"], provenance=run)
        reg.add("ka metaphor agree", ka["metaphor_agree"], provenance=run)
        reg.add("ka pct metaphor agree", _pct(ka["pct_metaphor_agree"]), provenance=run)

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

    for lab, d in ex.get("scan_by_kind", {}).items():
        for k, v in d.items():
            reg.add(f"sk {lab.replace('_', ' ')} {k.replace('_', ' ')}", _pct(v) if k.startswith("pct") else v, provenance=run)

    rc = ex.get("run_counts", {})
    if rc:
        for rank, (n_, cnt) in enumerate(rc["parser_counts"][:6]):
            reg.add(f"rc parser rank {_word(rank + 1)} n", n_, provenance=run)
            reg.add(f"rc parser rank {_word(rank + 1)} count", cnt, provenance=run)
        for rank, (n_, cnt) in enumerate(rc["scan_counts"][:6]):
            reg.add(f"rc scan rank {_word(rank + 1)} n", n_, provenance=run)
            reg.add(f"rc scan rank {_word(rank + 1)} count", cnt, provenance=run)
        reg.add("rc papers stating", rc["papers_stating_runs_in_text"], provenance=run)
        reg.add("rc papers scanned", rc["papers_scanned"], provenance=run)
        reg.add("rc papers stating pct", _pct(rc["pct_papers_stating_runs"]), provenance=run)
        reg.add("rc agree", rc["parser_scan_agree"], provenance=run)
        reg.add("rc disagree", rc["parser_scan_disagree"], provenance=run)
        _rates_block(reg, "rc thirty", rc["thirty_runs"], run)
        reg.add("rc thirty share", _pct(rc["pct_testable_at_thirty"]), provenance=run)

    sr = ex.get("scan_run_count", {})
    if sr:
        reg.add("sr n", sr["n"], provenance=run)
        reg.add("sr papers", sr["papers"], provenance=run)
        reg.add("sr changed", sr["changed_count"], provenance=run)
        reg.add("sr fail", _pct(sr["pct_fail"]) if sr["pct_fail"] is not None else "--", provenance=run)
        reg.add("sr fail ci", f"[{sr['ci_fail'][0]}, {sr['ci_fail'][1]}]" if sr.get("ci_fail") else "--", provenance=run)

    for name, d in ex.get("test_reader", {}).items():
        if name == "note":
            for k, v in d.items():
                reg.add("tr " + k.replace("_", " "), v, provenance=run)
            continue
        key = "tr " + name.replace("_", " ")
        for k in ("papers", "runs_stated", "runs_thirty", "test_named", "markers"):
            reg.add(f"{key} {k.replace('_', ' ')}", d[k], provenance=run)
        reg.add(f"{key} alpha five percent", d["alpha_005"], provenance=run)
        for k in ("pct_runs_stated", "pct_runs_thirty", "pct_std_off_cell", "pct_test_named", "pct_markers", "pct_markers_among_named"):
            reg.add(f"{key} {k.replace('_', ' ')}", _pct(d[k]), provenance=run)
        for lab in ("same_cell", "separate_row", "separate_column", "none", "unsure"):
            reg.add(f"{key} layout {lab.replace('_', ' ')}", d["layout"].get(lab, 0), provenance=run)
            reg.add(f"{key} layout {lab.replace('_', ' ')} pct", _pct(d["pct_layout"].get(lab, 0.0)), provenance=run)
        for lab in ("best", "statistically best", "proposed", "not stated", "other"):
            reg.add(f"{key} bold {lab}", d["bold_rule"].get(lab, 0), provenance=run)
            reg.add(f"{key} bold {lab} pct", _pct(d["pct_bold_rule"].get(lab, 0.0)), provenance=run)
        for lab in ("per_run_values", "per_function_means", "ranks", "unsure", "none"):
            reg.add(f"{key} on {lab.replace('_', ' ')}", d["test_on"].get(lab, 0), provenance=run)
        for lab in ("yes", "no", "unsure"):
            reg.add(f"{key} paired {lab}", d["paired"].get(lab, 0), provenance=run)
        tests = dict(d["tests"])
        for t in sorted(set(tests) | {"wilcoxon_signed_rank", "wilcoxon_rank_sum", "mann_whitney", "friedman", "t_test", "anova", "holm", "bonferroni", "kruskal_wallis", "other"}):
            reg.add(f"{key} test {t.replace('_', ' ')}", tests.get(t, 0), provenance=run)
        for rank, (n_, c) in enumerate(d["runs_top"][:4]):
            reg.add(f"{key} runs rank {_word(rank + 1)} n", n_, provenance=run)
            reg.add(f"{key} runs rank {_word(rank + 1)} count", c, provenance=run)

    ax = ex.get("arxiv", {})
    if ax:
        reg.add("ax listed", ax["listed"] or "--", provenance=run)
        reg.add("ax parsed", ax["parsed"], provenance=run)
        for name, d in ((k, v) for k, v in ax.items() if isinstance(v, dict)):
            key = "ax " + ("all" if name == "all" else "mh")
            reg.add(f"{key} papers", d["papers"], provenance=run)
            reg.add(f"{key} comparisons", d["comparisons"], provenance=run)
            reg.add(f"{key} claim papers", d["claim_papers"], provenance=run)
            reg.add(f"{key} neither", _pct(d["pct_neither"]), provenance=run)
            reg.add(f"{key} neither ci", f"[{d['ci_neither'][0]:.1f}, {d['ci_neither'][1]:.1f}]", provenance=run)
            reg.add(f"{key} testable", _pct(d["pct_testable"]), provenance=run)
            reg.add(f"{key} testable n", d["n_testable"], provenance=run)
            reg.add(f"{key} testable papers", d["papers_testable"], provenance=run)
            reg.add(f"{key} fail", _pct(d["pct_fail"]) if d["n_testable"] else "--", provenance=run)
            reg.add(f"{key} fail ci", f"[{d['ci_fail'][0]:.1f}, {d['ci_fail'][1]:.1f}]" if d["ci_fail"] else "--", provenance=run)
            reg.add(f"{key} papers err", _pct(d["pct_papers_err"]), provenance=run)
            reg.add(f"{key} papers runs", _pct(d["pct_papers_runs"]), provenance=run)

    def _scan_block(prefix, d):
        reg.add(f"{prefix} n", d["n"], provenance=run)
        reg.add(f"{prefix} papers", d["papers"], provenance=run)
        reg.add(f"{prefix} fails", d["fails"], provenance=run)
        reg.add(f"{prefix} fail", _pct(d["pct_fail"]) if d["pct_fail"] is not None else "--", provenance=run)
        reg.add(f"{prefix} fail ci", f"[{d['ci_fail'][0]}, {d['ci_fail'][1]}]" if d.get("ci_fail") else "--", provenance=run)

    pr = ex.get("parser_readings", {})
    for key in ("as_reported", "back_matter_only", "without_back_matter", "zero_sd_only", "without_zero_sd",
                "interval_only", "without_interval", "cleaned"):
        d = pr[key]
        k = "pr " + key.replace("_", " ")
        reg.add(f"{k} n", d["n"], provenance=run)
        reg.add(f"{k} papers", d["papers"], provenance=run)
        reg.add(f"{k} fail", _pct(d["pct_fail"]) if d["pct_fail"] is not None else "--", provenance=run)
        reg.add(f"{k} fail holm", _pct(d["pct_fail_holm"]) if d.get("pct_fail_holm") is not None else "--", provenance=run)
        reg.add(f"{k} fail ci", f"[{d['ci_fail'][0]}, {d['ci_fail'][1]}]" if d.get("ci_fail") and d["papers"] >= 10 else "--", provenance=run)
        _scan_block(f"{k} scan", d["scan"])
    reg.add("pr back matter all comparisons", pr["back_matter_all_comparisons"], provenance=run)
    reg.add("pr back matter papers", pr["back_matter_papers"], provenance=run)
    reg.add("pr tested at five or fewer", pr["tested_at_five_or_fewer"], provenance=run)
    reg.add("pr tested at five or fewer papers", pr["tested_at_five_or_fewer_papers"], provenance=run)
    reg.add("pr median n", int(pr["median_n"]) if pr["median_n"] else "--", provenance=run)
    for lab, d in ex.get("kind_scan_fail", {}).items():
        _scan_block("ks " + lab.replace("_", " "), d)
    for lab, d in ex.get("cites_scan_fail", {}).items():
        _scan_block("cs " + lab.replace("_", " "), d)
    for lab, d in ex.get("tests_scan_fail", {}).items():
        _scan_block("ts " + lab, d)
    reg.add("hk genuine papers", ex.get("holders_genuine", 0), provenance=run)
    reg.add("hk any comparison papers", ex.get("holders_all", 0), provenance=run)
    reg.add("a effective papers", f"{b['effective_papers']:.1f}" if b.get("effective_papers") else "--", provenance=run)
    for lab, d in ex.get("scan_by_kind_holders", {}).items():
        k = "hk " + lab.replace("_", " ")
        reg.add(f"{k} papers", d["papers"], provenance=run)
        for f in ("pct_runs_stated", "pct_test_named", "pct_thirty_modal"):
            reg.add(f"{k} {f.replace('_', ' ')}", _pct(d[f]), provenance=run)
    for lab, d in ex.get("bold_note", {}).items():
        k = "bn " + lab.replace("_", " ")
        reg.add(f"{k} papers", d["papers"], provenance=run)
        reg.add(f"{k} with note", d["with_note"], provenance=run)
        reg.add(f"{k} pct", _pct(d["pct"]), provenance=run)
    ka2 = ex.get("kind_agreement", {})
    if ka2.get("direction"):
        for k, v in ka2["direction"].items():
            reg.add("ka dir " + k.replace("_", " "), _pct(v) if k.startswith(("precision", "recall")) else v, provenance=run)
        for k, d in ka2["strata"].items():
            reg.add(f"ka st {k.replace('_', ' ')} papers", d["papers"], provenance=run)
            reg.add(f"ka st {k.replace('_', ' ')} runs", _pct(d["pct_runs_stated"]), provenance=run)
            reg.add(f"ka st {k.replace('_', ' ')} test", _pct(d["pct_test_named"]), provenance=run)
        reg.add("ka metaphor none disagreements", ka2["metaphor_none_disagreements"], provenance=run)

    for j, d in ex.get("fetch_attempts", {}).items():
        key = "fa " + j.lower().replace("&", "and").replace(" ", " ")
        reg.add(f"{key} attempts", d["attempts"], provenance=run)
        reg.add(f"{key} pdf ok", d["pdf_ok"], provenance=run)
        reg.add(f"{key} html only", d["html_only"], provenance=run)
        reg.add(f"{key} statuses", d["statuses"].replace("None", "no answer"), provenance=run)
    fa = ex.get("fetch_attempts", {})
    if fa:
        mdpi = [j for j in fa if j in ("Mathematics", "Applied Sciences", "Biomimetics", "Algorithms")]
        reg.add("fa mdpi attempts", sum(fa[j]["attempts"] for j in mdpi), provenance=run)
        reg.add("fa mdpi pdf ok", sum(fa[j]["pdf_ok"] for j in mdpi), provenance=run)
        reg.add("fa mdpi listed", sum(fa[j]["listed"] for j in mdpi), provenance=run)

    ta = ex.get("test_reader_agreement", {})
    if ta:
        reg.add("ta papers", ta["papers"], provenance=run)
        for k in ("runs", "runs_stated", "test_named", "markers", "bold_rule", "std_layout", "paired"):
            reg.add(f"ta {k.replace('_', ' ')} frac", f"{ta[k]['agree']} of {ta[k]['n']}", provenance=run)
            reg.add(f"ta {k.replace('_', ' ')} pct", _pct(ta[k]["pct"]), provenance=run)
            reg.add(f"ta {k.replace('_', ' ')} ci", f"[{ta[k]['ci'][0]}, {ta[k]['ci'][1]}]" if ta[k]["ci"] else "--", provenance=run)
        for k, v in ta.items():
            if k.startswith(("first_", "second_")):
                reg.add("ta " + k.replace("_", " "), _pct(v), provenance=run)

    cc = ex.get("cites", {})
    if cc:
        names = {"derrac2011": "derrac", "garcia2009": "garcia nine", "garcia2010": "garcia ten", "sorensen2015": "sorensen",
                 "aranha2022": "aranha", "camacho2022": "camacho", "bartz2020": "bartz", "beiranvand2017": "beiranvand",
                 "kendall2016": "kendall", "hansen_coco": "coco", "wolpert_nfl": "nfl",
                 "carrasco2020": "carrasco", "latorre2021": "latorre", "osaba2021": "osaba"}
        for k, v in cc["counts"].items():
            reg.add(f"cc {names.get(k, k.replace('_', ' '))}", v, provenance=run)
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
        if "pct_fail" not in row:  # an empty subset carries only its count
            reg.add(f"span {key} n", row.get("n", 0), provenance=run)
            continue
        reg.add(f"span {key} fail", _pct(row["pct_fail"]), provenance=run)
        if row.get("pct_fail_holm") is not None:
            reg.add(f"span {key} fail holm", _pct(row["pct_fail_holm"]), provenance=run)
        if row.get("n") is not None:
            reg.add(f"span {key} n", row["n"], provenance=run)
        if row.get("ci_fail"):
            ci = [b["pct_fail"]["lo"], b["pct_fail"]["hi"]] if name == "as_reported" else row["ci_fail"]
            reg.add(f"span {key} fail ci", f"[{ci[0]:.1f}, {ci[1]:.1f}]", provenance=run)
            reg.add(f"span {key} papers", row["papers"], provenance=run)
    reg.add("span lo", _pct(hs["span"][0]), provenance=run)
    reg.add("span hi", _pct(hs["span"][1]), provenance=run)
    sp = ex.get("span_rows", {})
    if sp:
        reg.add("span rows lo", _pct(min(sp["lo"], ex["ddof_reading"]["pct_fail"])), provenance=run)
        reg.add("span rows hi", _pct(max(sp["hi"], ex["ddof_reading"]["pct_fail"])), provenance=run)

    rb = ex["row_bold"]
    for key in ("header row only", "without header row", "row bold only", "without row bold"):
        _rates_block(reg, "rb " + key, rb[key.replace(" ", "_")], run)
    reg.add("rb header row papers", rb["header_row_papers"], provenance=run)
    reg.add("rb row bold papers", rb["row_bold_papers"], provenance=run)
    reg.add("rb papers all row bold", rb["papers_all_row_bold"], provenance=run)
    co = ex["corpus"]
    reg.add("o journals listed", co["journals_listed"], provenance=run)
    reg.add("o fetched", co["fetched"], provenance=run)
    for y, n in co["listed_by_year"].items():
        reg.add(f"o listed srep {({'2024': 'twenty four', '2025': 'twenty five'})[str(y)]}", n, provenance=run)

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
    for key, d in (("labelled", ebm["labelled_only"]), ("as sem", ebm["read_as_sem"]), ("as std", ebm["read_as_std"])):
        reg.add(f"bars {key} n", d.get("n", 0), provenance=run)
        reg.add(f"bars {key} fail", _pct(d["pct_fail"]) if "pct_fail" in d else "--", provenance=run)
    rcs = ex["run_count_scope"]
    reg.add("strict testable", _pct(rcs["strict"]["pct_testable"]), provenance=run)
    reg.add("strict fail", _pct(rcs["strict"]["pct_fail"]), provenance=run)
    reg.add("strict n", rcs["strict"]["n"], provenance=run)
    hf = ex["holm_families"]
    reg.add("holm median family", hf["median_family_size"], provenance=run)
    reg.add("holm pct in families over five", _pct(hf["pct_testable_in_families_over_5"]), provenance=run)
    sd = ex["subset_direction"]
    for band, d in sd["by_runs"].items():
        key = {"le3": "le three", "4to5": "four to five", "ge6": "ge six", "6to30": "six to thirty", "gt30": "gt thirty"}.get(band, band)
        reg.add(f"runs {key} n", d["n"], provenance=run)
        reg.add(f"runs {key} fail", _pct(d["pct_fail"]) if d["n"] else "--", provenance=run)
        reg.add(f"runs {key} fail ci", f"{d['pct_fail']}{PCT} [{d['ci_fail'][0]}, {d['ci_fail'][1]}]" if d.get("ci_fail") else "--", provenance=run)
    ua = ex["uncertainty_anywhere"]
    for k, v in ua.items():
        if isinstance(v, (int, float)):
            reg.add("ua " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)
    cap = ex["caption_assertion"]
    _rates_block(reg, "cap asserting", cap["asserting"], run)
    _rates_block(reg, "cap describing", cap["describing"], run)
    bl = ex["big_n_and_largest"]
    reg.add("bign papers", len(bl["big_n_papers"]), provenance=run)
    lg = bl["largest"] or {}
    reg.add("largest n", lg.get("n", 0), provenance=run)
    reg.add("largest pct of testable", _pct(lg["pct_of_testable"]) if lg else "--", provenance=run)
    reg.add("largest fail", _pct(lg["pct_fail"]) if lg else "--", provenance=run)
    reg.add("largest runs", lg.get("n_runs", "--"), provenance=run)
    fu = ex["funnel"]
    for k, v in fu.items():
        if isinstance(v, (int, float)):
            reg.add("fu " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)
    bs = ex["bold_semantics"]
    for k, v in bs.items():
        if isinstance(v, (int, float)):
            reg.add("bs " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance=run)

    def _frac(d: dict, k="correct", n="n") -> str:
        return f"{d[k]} of {d[n]}"

    def _pct_ci(d: dict) -> str:
        if d.get("pct") is None:
            return "--"
        return f"{d['pct']}{PCT} [{d['ci'][0]}, {d['ci'][1]}]"

    for tag, path, grun in (("g", "gold_set", "swevo_gold_set_gemini"), ("g two", "gold_set_sonnet", "swevo_gold_set_sonnet")):
        if not os.path.exists(f"out/swevo/{path}.json"):
            continue
        g = _j(path)
        gt = g["testable"]
        f = gt["fields"]
        reg.add(f"{tag} testable n", gt["n_labelled"], provenance=grun)
        reg.add(f"{tag} unboxed n", gt["n_unboxed"] + g["no_bar"]["n_unboxed"], provenance=grun)
        reg.add(f"{tag} drawn n", gt["n_labelled"] + gt["n_unboxed"] + g["no_bar"]["n"] + g["no_bar"]["n_unboxed"], provenance=grun)
        reg.add(f"{tag} claim frac", _frac(f["claim_and_values"]), provenance=grun)
        reg.add(f"{tag} claim of drawn frac", f"{f['claim_and_values']['correct']} of {sum(1 for it in json.load(open('audits/swevo_gold/items.json', encoding='utf-8')) if it['stratum'] == 'testable')}", provenance=grun)
        reg.add(f"{tag} claim", _pct_ci(f["claim_and_values"]), provenance=grun)
        for name in ("bold_cell", "winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs", "orientation", "direction"):
            if name in f:
                reg.add(f"{tag} {name.replace('_', ' ')}", _pct_ci(f[name]), provenance=grun)
                reg.add(f"{tag} {name.replace('_', ' ')} frac", _frac(f[name]), provenance=grun)
        v = gt["verdict_2x2"]
        both = v["both_fail"] + v["both_survive"]
        reg.add(f"{tag} verdict frac", f"{both} of {gt['n_testable_under_both']}", provenance=grun)
        reg.add(f"{tag} verdict", _pct(v["per_item_agreement"]) if v["per_item_agreement"] is not None else "--", provenance=grun)
        reg.add(f"{tag} fail reader", _pct(gt["failure_rate_reader_values"]) if gt.get("failure_rate_reader_values") is not None else "--", provenance=grun)
        reg.add(f"{tag} fail pipe", _pct(gt["failure_rate_pipeline_values_same_items"]) if gt.get("failure_rate_pipeline_values_same_items") is not None else "--", provenance=grun)
        reg.add(f"{tag} reader fail only", v["reader_fail_pipeline_survive"], provenance=grun)
        reg.add(f"{tag} pipe fail only", v["pipeline_fail_reader_survive"], provenance=grun)
        reg.add(f"{tag} verdict full frac", f"{both} of {gt['n_labelled']}", provenance=grun)
        nb = g["no_bar"]
        reg.add(f"{tag} no bar n", nb["n"], provenance=grun)
        reg.add(f"{tag} no bar results table frac", _frac(nb["results_table"]), provenance=grun)
        reg.add(f"{tag} no bar bold frac", _frac(nb["bold_cell"]), provenance=grun)
        reg.add(f"{tag} no bar winner frac", _frac(nb["winner_mean"]), provenance=grun)
        reg.add(f"{tag} no bar runner frac", _frac(nb["runner_mean"]) if "runner_mean" in nb else "--", provenance=grun)
        reg.add(f"{tag} no bar absent", _pct_ci(nb["error_bar_truly_absent"]), provenance=grun)
        reg.add(f"{tag} no bar absent frac", _frac(nb["error_bar_truly_absent"]), provenance=grun)
        vocab = {"discarded": ("no_bold", "multi_bold", "whole_row_bold", "not_results", "bold_missed", "parse_error", "other"),
                 "non_extremal": ("subclass_best", "excluding_oracle", "own_method", "header_bold", "misread", "parse_error", "other")}
        for st in ("discarded", "non_extremal"):
            if st in g and isinstance(g[st], dict):
                reg.add(f"{tag} {st.replace('_', ' ')} n", g[st].get("n", 0), provenance=grun)
                for k, d in g[st].items():
                    if isinstance(d, dict) and "correct" in d and "n" in d:
                        reg.add(f"{tag} {st.replace('_', ' ')} {k.replace('_', ' ')} frac", _frac(d), provenance=grun)
                causes = g[st].get("causes", {})
                for c in sorted(set(vocab[st]) | set(causes)):
                    reg.add(f"{tag} {st.replace('_', ' ')} cause {c.replace('_', ' ')}", causes.get(c, 0), provenance=grun)
        import csv as _csv
        lab_path = {"g": "audits/swevo_gold/labels_gemini.csv", "g two": "audits/swevo_gold/labels_sonnet.csv"}[tag]
        rows_g = list(_csv.DictReader(open(lab_path, encoding="utf-8", newline="")))
        for st in ("testable", "no_bar"):
            sub = [r for r in rows_g if r["stratum"] == st]
            reg.add(f"{tag} {st.replace('_', ' ')} not results", sum(1 for r in sub if r["results_table"].strip().lower().startswith("n")), provenance=grun)
            reg.add(f"{tag} {st.replace('_', ' ')} rows", len(sub), provenance=grun)
        cv = f["claim_and_values"]
        if cv.get("paper_ci"):
            reg.add(f"{tag} claim paper ci", f"[{cv['paper_ci'][0]}, {cv['paper_ci'][1]}]", provenance=grun)
            reg.add(f"{tag} claim papers", cv.get("n_papers", 0), provenance=grun)
            reg.add(f"{tag} claim max one paper", cv.get("max_disagreements_one_paper", 0), provenance=grun)
        items_g = json.load(open("audits/swevo_gold/items.json", encoding="utf-8"))
        reg.add(f"{tag} items n", len(items_g), provenance=grun)
        for st in ("testable", "no_bar", "discarded", "non_extremal"):
            reg.add(f"{tag} stratum {st.replace('_', ' ')}", sum(1 for it in items_g if it["stratum"] == st), provenance=grun)
    if os.path.exists("out/swevo/reader_agreement.json"):
        ag = _j("reader_agreement")
        for k, v in ag.items():
            if isinstance(v, (int, float)):
                reg.add("ag " + k.replace("_", " "), _pct(v) if "pct" in k else v, provenance="swevo_reader_agreement")
            elif isinstance(v, dict) and "n" in v and ("agree" in v or "correct" in v):
                reg.add("ag " + k.replace("_", " ") + " frac", f"{v.get('agree', v.get('correct'))} of {v['n']}", provenance="swevo_reader_agreement")
                reg.add("ag " + k.replace("_", " ") + " pct", _pct(v["pct"]) if v.get("pct") is not None else "--", provenance="swevo_reader_agreement")

    if os.path.exists("out/swevo/verdict_crosstab.json"):
        vc = _j("verdict_crosstab")
        vrun = "swevo_verdict_crosstab"
        for k in ("papers", "pages_read", "tested_groups", "located", "agree", "papers_located"):
            reg.add("vc " + k.replace("_", " "), vc[k], provenance=vrun)
        reg.add("vc pct located", _pct(vc["pct_located"]), provenance=vrun)
        reg.add("vc pct agree", _pct(vc["pct_agree"]) if vc["pct_agree"] is not None else "--", provenance=vrun)
        reg.add("vc ci agree", f"[{vc['ci_agree'][0]}, {vc['ci_agree'][1]}]" if vc.get("ci_agree") else "--", provenance=vrun)
        reg.add("vc welch fail among located", _pct(vc["welch_fail_among_located"]) if vc["welch_fail_among_located"] is not None else "--", provenance=vrun)
        reg.add("vc printed not significant", _pct(vc["printed_not_significant_among_located"]) if vc["printed_not_significant_among_located"] is not None else "--", provenance=vrun)
        for k, v in vc["crosstab"].items():
            reg.add("vc " + k.replace("_", " "), v, provenance=vrun)
        reg.add("vc ci agree papers", f"[{vc['ci_agree_papers'][0]}, {vc['ci_agree_papers'][1]}]" if vc.get("ci_agree_papers") else "--", provenance=vrun)
        reg.add("vc welch fail not located", _pct(vc["welch_fail_not_located"]) if vc.get("welch_fail_not_located") is not None else "--", provenance=vrun)
        reg.add("vc not located", vc.get("not_located", 0), provenance=vrun)
        reg.add("vc conflicting keys papers", vc.get("conflicting_keys_papers", 0), provenance=vrun)
        for k in ("beside_group", "same_page_table"):
            reg.add("vc source " + k.replace("_", " "), vc["source"].get(k, 0), provenance=vrun)
        reg.add("vc chance agreement", _pct(vc["chance_agreement"]) if vc.get("chance_agreement") is not None else "--", provenance=vrun)
        reg.add("vc macro agreement", _pct(vc["macro_agreement"]) if vc.get("macro_agreement") is not None else "--", provenance=vrun)
        reg.add("vc per paper agreement min", _pct(vc["per_paper_agreement_min"]) if vc.get("per_paper_agreement_min") is not None else "--", provenance=vrun)
        reg.add("vc per paper agreement max", _pct(vc["per_paper_agreement_max"]) if vc.get("per_paper_agreement_max") is not None else "--", provenance=vrun)
        reg.add("vc kappa", f"{vc['kappa']:.2f}" if vc.get("kappa") is not None else "--", provenance=vrun)
        reg.add("vc top three share", _pct(vc["top_three_share"]) if vc.get("top_three_share") is not None else "--", provenance=vrun)
        reg.add("vc sign contradictions", vc.get("sign_contradictions", 0), provenance=vrun)
        reg.add("vc sign checked", vc.get("sign_checked", 0), provenance=vrun)
        reg.add("vc effective papers", f"{vc['effective_papers']:.1f}" if vc.get("effective_papers") else "--", provenance=vrun)
        reg.add("vc largest paper located", vc.get("largest_paper_located", 0), provenance=vrun)
        reg.add("vc pct largest paper", _pct(vc["pct_largest_paper"]) if vc.get("pct_largest_paper") is not None else "--", provenance=vrun)
        aw = vc.get("agree_without_largest") or {}
        reg.add("vc agree without largest n", aw.get("n", 0), provenance=vrun)
        reg.add("vc agree without largest pct", _pct(aw["pct"]) if aw else "--", provenance=vrun)
        for k in sorted(set(vc["status"]) | {"located", "verdict_not_printed", "group_not_matched", "page_not_read", "different_pair", "ambiguous_key"}):
            reg.add("vc status " + k.replace("_", " "), vc["status"].get(k, 0), provenance=vrun)
        for k in ("same_page", "verdict_table", "verdict_table_winner_named"):
            reg.add("vc source " + k.replace("_", " "), vc["source"].get(k, 0), provenance=vrun)

    if os.path.exists("out/swevo/gold_set_census.json"):
        cz = _j("gold_set_census")
        crun = "swevo_gold_set_census"
        items_c = json.load(open("audits/swevo_census/items.json", encoding="utf-8"))
        reg.add("cz pages drawn", len(items_c), provenance=crun)
        reg.add("cz papers drawn", len({it["paper"] for it in items_c}), provenance=crun)
        reg.add("cz pages read", cz["n_pages"], provenance=crun)
        reg.add("cz tables", cz["n_results_tables"], provenance=crun)
        reg.add("cz tables with bar", _pct(cz["pct_results_tables_with_any_bar"]), provenance=crun)
        rz = cz["reader"]
        reg.add("cz groups", rz["groups"], provenance=crun)
        reg.add("cz papers with groups", rz["papers_with_groups"], provenance=crun)
        reg.add("cz neither", _pct(rz["pct_neither"]), provenance=crun)
        _rg = _j("census_readings").get("pre", {}).get("all", {}) if os.path.exists("out/swevo/census_readings.json") else {}
        _rgci = lambda key, fallback: (f"[{_rg[key][0]}, {_rg[key][1]}]" if _rg.get(key) else fallback)
        reg.add("cz neither ci", _rgci("ci_neither", f"[{rz['ci_neither_papers'][0]}, {rz['ci_neither_papers'][1]}]"), provenance=crun)
        reg.add("cz one side", _pct(rz["pct_one_side"]), provenance=crun)
        reg.add("cz testable", _pct(rz["pct_testable"]), provenance=crun)
        reg.add("cz testable n", rz["n_testable"], provenance=crun)
        reg.add("cz testable ci", _rgci("ci_testable", f"[{rz['ci_testable_papers'][0]}, {rz['ci_testable_papers'][1]}]"), provenance=crun)
        reg.add("cz bars no n", _pct(rz["pct_bars_no_n"]), provenance=crun)
        pz = cz["pipeline_same_pages"]
        reg.add("cz pipe groups", pz["groups"], provenance=crun)
        reg.add("cz pipe neither", _pct(pz["pct_neither"]), provenance=crun)
        reg.add("cz pipe testable", _pct(pz["pct_testable"]), provenance=crun)
        reg.add("cz reader found pct", _pct(cz["reader_groups_found_by_pipeline"]["pct"]), provenance=crun)
        reg.add("cz pipe found pct", _pct(cz["pipeline_groups_found_by_reader"]["pct"]), provenance=crun)
        reg.add("cz matched neither", _pct(cz["reader_groups_matched"]["pct_neither"]), provenance=crun)
        reg.add("cz unmatched neither", _pct(cz["reader_groups_unmatched"]["pct_neither"]), provenance=crun)
        reg.add("cz reader matched groups", cz["reader_groups_matched"]["groups"], provenance=crun)
        reg.add("cz reader unmatched groups", cz["reader_groups_unmatched"]["groups"], provenance=crun)
        fz = cz["reader_failure"]
        _fci = _rg.get("ci_fail") or fz.get("ci")
        reg.add("cz reader fail", f"{fz['pct_fail']}{PCT} [{_fci[0]}, {_fci[1]}]" if fz["n"] else "--", provenance=crun)
        reg.add("cz reader fail n", fz["n"], provenance=crun)
        reg.add("cz reader fail pct", _pct(fz["pct_fail"]) if fz["n"] else "--", provenance=crun)
        reg.add("cz reader fail ci", f"[{_fci[0]}, {_fci[1]}]" if fz["n"] else "--", provenance=crun)
        reg.add("cz reader fail papers", fz["n_papers"], provenance=crun)
        vz = cz["verdicts_same_pages"]
        reg.add("cz shared", vz["shared"]["n"], provenance=crun)
        reg.add("cz shared agree", vz["shared"]["agree"], provenance=crun)
        reg.add("cz shared reader fails", vz["shared"]["reader_fails"], provenance=crun)
        reg.add("cz shared pipe fails", vz["shared"]["pipeline_fails"], provenance=crun)
        reg.add("cz reader only n", vz["reader_only"]["n"], provenance=crun)
        reg.add("cz reader only fails", vz["reader_only"]["fails"], provenance=crun)
        reg.add("cz pipe only n", vz["pipeline_only"]["n"], provenance=crun)
        reg.add("cz pipe only fails", vz["pipeline_only"]["fails"], provenance=crun)
        rs = cz["reader_sensitivity"]
        reg.add("cz reader se n", rs["unlabelled_as_se"]["n"], provenance=crun)
        reg.add("cz reader unlabelled n", rs["unlabelled_as_se"]["n_unlabelled"], provenance=crun)
        reg.add("cz reader unlabelled as se fail", _pct(rs["unlabelled_as_se"]["pct_fail_unlabelled_as_se"]), provenance=crun)
    if os.path.exists("out/swevo/census_readings.json"):
        cr = _j("census_readings")
        rrun = "swevo_census_readings"
        reg.add("cr pages read", cr["pages_read"], provenance=rrun)
        reg.add("cr papers read", cr["papers_read"], provenance=rrun)
        reg.add("cr papers in kit", cr["papers_in_kit"], provenance=rrun)

        def _sh(prefix, d, prov=rrun):
            reg.add(f"{prefix} groups", d["groups"], provenance=prov)
            reg.add(f"{prefix} papers", d["papers"], provenance=prov)
            reg.add(f"{prefix} neither", _pct(d["pct_neither"]) if d["pct_neither"] is not None else "--", provenance=prov)
            reg.add(f"{prefix} neither ci", f"[{d['ci_neither'][0]}, {d['ci_neither'][1]}]" if d.get("ci_neither") and d["papers"] >= 10 else "--", provenance=prov)
            reg.add(f"{prefix} one side", _pct(d["pct_one_side"]) if d.get("pct_one_side") is not None else "--", provenance=prov)
            reg.add(f"{prefix} testable", _pct(d["pct_testable"]) if d["pct_testable"] is not None else "--", provenance=prov)
            reg.add(f"{prefix} testable ci", f"[{d['ci_testable'][0]}, {d['ci_testable'][1]}]" if d.get("ci_testable") and d["papers"] >= 10 else "--", provenance=prov)
            reg.add(f"{prefix} testable n", d.get("testable_n", 0), provenance=prov)
            reg.add(f"{prefix} tested", d["tested"], provenance=prov)
            reg.add(f"{prefix} tested papers", d["tested_papers"], provenance=prov)
            reg.add(f"{prefix} tested effective", f"{d['tested_effective_papers']:.1f}" if d.get("tested_effective_papers") else "--", provenance=prov)
            reg.add(f"{prefix} fail", _pct(d["pct_fail"]) if d["pct_fail"] is not None else "--", provenance=prov)
            reg.add(f"{prefix} fail ci", f"[{d['ci_fail'][0]}, {d['ci_fail'][1]}]" if d.get("ci_fail") and d["tested_papers"] >= 10 else "--", provenance=prov)
            reg.add(f"{prefix} zero both", d.get("zero_both", 0), provenance=prov)
            reg.add(f"{prefix} unreadable", d.get("unreadable", 0), provenance=prov)

        for tag, lay in (("cr", cr["layout"]), ("crc", cr["layout_corrected"])):
            reg.add(f"{tag} results tables", lay["results_tables"], provenance=rrun)
            reg.add(f"{tag} tables any bar", _pct(lay["pct_tables_any_bar"]), provenance=rrun)
            for k in sorted(set(lay["bar_form"]) | {"pm", "paren", "bracket", "subscript", "separate_column", "separate_row", "none"}):
                reg.add(f"{tag} form {k.replace('_', ' ')}", lay["bar_form"].get(k, 0), provenance=rrun)
                reg.add(f"{tag} form {k.replace('_', ' ')} pct", _pct(lay["pct_bar_form"].get(k, 0.0)), provenance=rrun)
            reg.add(f"{tag} form separate pct", _pct(round(lay["pct_bar_form"].get("separate_column", 0.0) + lay["pct_bar_form"].get("separate_row", 0.0), 1)), provenance=rrun)
            reg.add(f"{tag} groups separate layout pct", _pct(lay["pct_groups_in_separate_layout"]), provenance=rrun)
            reg.add(f"{tag} barred groups separate layout pct", _pct(lay["pct_barred_groups_in_separate_layout"]), provenance=rrun)
            reg.add(f"{tag} tables with run count", _pct(lay["pct_tables_with_run_count"]), provenance=rrun)
            reg.add(f"{tag} tables at thirty", _pct(lay["pct_tables_at_thirty"]), provenance=rrun)
            for rank, (n_, cnt) in enumerate(lay["n_runs"][:5]):
                reg.add(f"{tag} runs rank {_word(rank + 1)} n", n_, provenance=rrun)
                reg.add(f"{tag} runs rank {_word(rank + 1)} count", cnt, provenance=rrun)
            for k in sorted(set(lay["n_source"]) | {"caption", "page", "paper", "none", "unstated"}):
                reg.add(f"{tag} n source {k}", lay["n_source"].get(k, 0), provenance=rrun)

        for tag, d in (("cr", cr["pre"]), ("crc", cr["corrected"])):
            _sh(f"{tag} all", d["all"])
            for lab, dd in d["by_kind"].items():
                _sh(f"{tag} {lab.replace('_', ' ')}", dd)
            rw = d["rows"]
            _sh(f"{tag} means", rw["means_only"])
            for lab, dd in rw["means_only_by_kind"].items():
                _sh(f"{tag} means {lab.replace('_', ' ')}", dd)
            for k in ("std_row_groups", "best_row_groups", "not_means_table_groups", "row_label_groups"):
                reg.add(f"{tag} rows {k.replace('_', ' ')}", rw[k], provenance=rrun)
            reg.add(f"{tag} rows row label pct", _pct(rw["row_label_pct"]), provenance=rrun)
            _sh(f"{tag} rows only", rw["row_label_only"])
            _sh(f"{tag} rows without", rw["without_row_label"])
            pp = d["per_paper"]
            for k in ("papers", "tested", "papers_any_fail", "largest_paper_tested"):
                reg.add(f"{tag} pp {k.replace('_', ' ')}", pp[k], provenance=rrun)
            reg.add(f"{tag} pp effective papers", f"{pp['effective_papers']:.1f}" if pp.get("effective_papers") else "--", provenance=rrun)
            for k in ("top_four_share", "top_ten_share", "median_rate", "q1_rate", "q3_rate", "largest_paper_fail"):
                reg.add(f"{tag} pp {k.replace('_', ' ')}", _pct(pp[k]) if pp[k] is not None else "--", provenance=rrun)
            _sh(f"{tag} pp without largest", pp["without_largest"])
            _sh(f"{tag} pp without top four", pp["without_top_four"])
            sh = d["shape"]
            for k in ("sd_ge_mean", "mean_tiny", "either", "neither", "zero_sd", "without_zero_sd"):
                _sh(f"{tag} sh {k.replace('_', ' ')}", sh[k])
            reg.add(f"{tag} sh pct tested sd ge mean", _pct(sh["pct_tested_sd_ge_mean"]) if sh["pct_tested_sd_ge_mean"] is not None else "--", provenance=rrun)
            reg.add(f"{tag} sh pct tested zero sd", _pct(sh["pct_tested_zero_sd"]) if sh["pct_tested_zero_sd"] is not None else "--", provenance=rrun)
            reg.add(f"{tag} sh zero both groups", sh["zero_both_groups"], provenance=rrun)
            reg.add(f"{tag} sh zero both papers", sh["zero_both_papers"], provenance=rrun)
            reg.add(f"{tag} sh unreadable groups", sh["unreadable_groups"], provenance=rrun)
            al = d["alternatives"]
            for k in ("as_reported", "holm_table", "holm_paper", "one_sided", "population_sd", "rho_half", "rho_nine_tenths", "unlabelled_as_se", "impossible_pairs_fail"):
                reg.add(f"{tag} al {k.replace('_', ' ')}", _pct(al[k]) if al[k] is not None else "--", provenance=rrun)
            for k in ("unlabelled_tested", "impossible_pairs", "impossible_pairs_tested", "impossible_pairs_papers", "impossible_pairs_separate",
                      "count_from_caption_or_page_tested", "count_from_paper_sentences"):
                reg.add(f"{tag} al {k.replace('_', ' ')}", al[k], provenance=rrun)
            _sh(f"{tag} al without impossible", al["without_impossible"])
            _sh(f"{tag} al count from caption or page", al["count_from_caption_or_page"])
            for lab, dd in d["bold_rule"].items():
                _sh(f"{tag} bold {lab.replace('_', ' ')}", dd)
            _sh(f"{tag} note with", d["note"]["with_note"])
            _sh(f"{tag} note without", d["note"]["without_note"])
            reg.add(f"{tag} note papers", d["note"]["papers_with_note"], provenance=rrun)
            for lab, dd in d["citing"].items():
                _sh(f"{tag} cite {lab.replace('_', ' ')}", dd)
            for k, v in d["scan_runs"].items():
                reg.add(f"{tag} runs {k.replace('_', ' ')}", v, provenance=rrun)

        rr = cr["rows_reread"]
        for k in ("pages_reread", "tables_reread", "tables_replaced", "tables_kept", "tables_truncated", "pages_with_a_kept_table",
                  "before_barred", "after_barred", "before_means", "after_means", "tables_separate_row_after", "tables_separate_after",
                  "tables_none_after", "pages_in_kits", "pages_new_optimizer", "pages_application"):
            reg.add(f"crrr {k.replace('_', ' ')}", rr[k], provenance=rrun)
        _sh("crrr before", rr["before_on_those_pages"])
        _sh("crrr after", rr["after_on_those_pages"])

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
