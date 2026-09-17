"""Every derived number of the metaheuristics paper, from
data/extracted_oa.jsonl (the frozen parser on the open-access corpus), the
text scans, the kind labels and the reader audits. Same functions as the
ICLR and AAMAS studies where the question is the same; new here are the
run-count and statistical-test readings of this field's convention.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, os.path.join(HERE, "..", "aamas"))
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import analyse  # noqa: E402
import extra_stats  # noqa: E402
import make_all  # noqa: E402
from make_all_aamas import (load_unique, readings, per_paper_failure, exact_copies, _rates,  # noqa: E402
                            caption_assertion, uncertainty_anywhere, ddof_reading, big_n_and_largest)
from sensitivity import (checkability_span, correlation_sensitivity, error_bar_meaning,  # noqa: E402
                         paper_level_crosstab, run_count_scope)
from paperengine.stats import wilson_interval  # noqa: E402

OUT = "out/swevo"
EXTRACTED = "data/extracted_oa.jsonl"


def _boot_share(items: list, key, reps: int = 2000, seed: int = 0) -> list | None:
    """Cluster bootstrap over papers of a share of comparisons; items are
    (paper, bool) pairs."""
    import random
    by = collections.defaultdict(list)
    for paper, flag in items:
        by[paper].append(flag)
    keys = list(by)
    if not keys:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        draw = [by[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [x for d in draw for x in d]
        vals.append(100 * sum(flat) / max(len(flat), 1))
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def by_group(cs: list, label: dict, name: str) -> dict:
    """The census shares and the failure rate by a per-paper label."""
    out = {}
    for lab in sorted(set(label.values())):
        sub = [c for c in cs if label.get(c["paper"]) == lab]
        r = _rates(sub)
        r["papers_labelled"] = sum(1 for v in label.values() if v == lab)
        r["claim_papers"] = len({c["paper"] for c in sub})
        r["ci_neither"] = _boot_share([(c["paper"], c["winner_dispersion"] is None and c["runner_dispersion"] is None) for c in sub])
        r["ci_testable"] = _boot_share([(c["paper"], bool(c.get("test"))) for c in sub])
        out[lab] = r
    return {name: out}


def stat_tests(cs: list, scan: dict) -> dict:
    """The convention's own test: which papers name a statistical test, and
    how the bold cells of those papers fare under Welch on the printed
    numbers, against papers that name none."""
    t = [c for c in cs if c.get("test")]
    papers_t = {c["paper"] for c in t}
    named = {p for p in papers_t if scan.get(p, {}).get("any_test")}
    kinds = collections.Counter()
    for p in papers_t:
        for k, v in scan.get(p, {}).get("tests", {}).items():
            if v:
                kinds[k] += 1
    a = [c for c in t if c["paper"] in named]
    b = [c for c in t if c["paper"] not in named]
    markers = {p for p in papers_t if scan.get(p, {}).get("tests", {}).get("plus_minus_equal")}
    return {"testable_papers": len(papers_t), "papers_naming_a_test": len(named),
            "pct_papers_naming_a_test": round(100 * len(named) / max(len(papers_t), 1), 1),
            "test_kinds_among_testable_papers": dict(kinds),
            "papers_with_plus_equal_minus": len(markers),
            "named": _rates(a), "unnamed": _rates(b),
            "all_papers_naming_a_test": sum(1 for v in scan.values() if v.get("any_test")),
            "all_papers": sum(1 for v in scan.values() if "error" not in v)}


def run_counts(cs: list, scan: dict) -> dict:
    """The run count as the parser reads it beside the table and as the
    text scan reads it anywhere in the paper; the thirty-run convention."""
    t = [c for c in cs if c.get("test")]
    parser_n = collections.Counter(c["n_runs"] for c in t if c.get("n_runs"))
    scan_n = collections.Counter(v["run_modal"] for v in scan.values() if v.get("run_modal"))
    agree = disagree = 0
    for c in t:
        s_ = scan.get(c["paper"], {}).get("run_modal")
        if c.get("n_runs") and s_:
            agree += (c["n_runs"] == s_)
            disagree += (c["n_runs"] != s_)
    thirty = [c for c in t if c.get("n_runs") == 30]
    return {"parser_counts": parser_n.most_common(8), "scan_counts": scan_n.most_common(8),
            "papers_stating_runs_in_text": sum(1 for v in scan.values() if v.get("run_modal")),
            "papers_scanned": sum(1 for v in scan.values() if "error" not in v),
            "pct_papers_stating_runs": round(100 * sum(1 for v in scan.values() if v.get("run_modal")) / max(sum(1 for v in scan.values() if "error" not in v), 1), 1),
            "parser_scan_agree": agree, "parser_scan_disagree": disagree,
            "thirty_runs": _rates(thirty),
            "pct_testable_at_thirty": round(100 * len(thirty) / max(len(t), 1), 1)}


def cites(cs: list, scan: dict) -> dict:
    """Papers citing the methodology literature, and how they report."""
    keys = ["derrac2011", "garcia2009", "garcia2010", "sorensen2015", "aranha2022", "camacho2022", "bartz2020",
            "beiranvand2017", "kendall2016", "hansen_coco", "wolpert_nfl"]
    counts = {k: sum(1 for v in scan.values() if v.get("cites", {}).get(k)) for k in keys}
    method = {p for p, v in scan.items() if any(v.get("cites", {}).get(k) for k in keys if k != "wolpert_nfl")}
    claim_papers = {c["paper"] for c in cs}
    a = [c for c in cs if c["paper"] in method]
    b = [c for c in cs if c["paper"] not in method]
    return {"counts": counts, "citing_papers": len(method & claim_papers), "claim_papers": len(claim_papers),
            "citing": _rates(a), "not_citing": _rates(b),
            "citing_name_a_test": sum(1 for p in method if scan[p].get("any_test")),
            "citing_state_runs": sum(1 for p in method if scan[p].get("run_modal"))}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    records = load_unique(EXTRACTED)
    analysis = analyse(records)
    with open(f"{OUT}/analysis.json", "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=1)
    cs = analysis["_comparisons"]
    summary, boot = make_all._summary(analysis, cs), make_all._bootstrap(cs)
    print(f"OA metaheuristics: {summary['papers']} papers, {summary['comparisons']} comparisons, "
          f"{summary['pct_neither']}% neither, {summary['pct_testable']}% testable, {summary['pct_fail']}% fail")
    scan = json.load(open(f"{OUT}/text_scan.json", encoding="utf-8")) if os.path.exists(f"{OUT}/text_scan.json") else {}
    kinds, metaphor, suite = {}, {}, {}
    import glob
    for path in sorted(glob.glob(f"{OUT}/kinds*.csv")):
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["label"] == "parse_error" or r["id"] in kinds:
                    continue
                kinds[r["id"]] = r["label"]
                metaphor[r["id"]] = r["metaphor_named"] or "unsure"
                suite[r["id"]] = r["benchmark_suite"] or "unsure"
    if kinds:
        with open(f"{OUT}/kinds_merged.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "label", "metaphor_named", "benchmark_suite"])
            for k in sorted(kinds):
                w.writerow([k, kinds[k], metaphor[k], suite[k]])
    by_year = {}
    for year in sorted({r["year"] for r in records}):
        recs = [r for r in records if r["year"] == year]
        a = analyse(recs)
        by_year[str(year)] = {"summary": make_all._summary(a, a["_comparisons"]), "bootstrap": make_all._bootstrap(a["_comparisons"])}
    index = {r["id"]: r for r in json.load(open(f"{OUT}/index.json", encoding="utf-8"))}
    extras = {
        "summary": summary, "bootstrap": boot, "by_year": by_year,
        "corpus": {"listed": len(index), "listed_in_corpus_journal": sum(1 for r in index.values() if r["journal"] == "Scientific Reports"),
                   "parsed": len(records), "by_journal": dict(collections.Counter(index[r["id"]]["journal"] for r in records if r["id"] in index))},
        "kinds": by_group(cs, kinds, "by_kind") if kinds else {},
        "metaphor": by_group(cs, metaphor, "by_metaphor") if metaphor else {},
        "suite": by_group(cs, suite, "by_suite") if suite else {},
        "kind_counts": dict(collections.Counter(kinds.values())),
        "metaphor_counts": dict(collections.Counter(metaphor.values())),
        "stat_tests": stat_tests(cs, scan) if scan else {},
        "run_counts": run_counts(cs, scan) if scan else {},
        "cites": cites(cs, scan) if scan else {},
        "headline_span": extra_stats.headline_span(cs, records),
        "subset_direction": extra_stats.subset_direction(records, cs),
        "holm_families": extra_stats.holm_families(cs),
        "run_count_scope": run_count_scope(cs, records),
        "error_bar_meaning": error_bar_meaning(cs),
        "paper_level_crosstab": paper_level_crosstab(records),
        "correlation_sensitivity": correlation_sensitivity(cs),
        "checkability_span": checkability_span(cs),
        "readings": readings(records, cs),
        "per_paper_failure": per_paper_failure(cs),
        "per_paper_failure_dedup": per_paper_failure(exact_copies(cs)[1]),
        "ddof_reading": ddof_reading(cs),
        "caption_assertion": caption_assertion(cs),
        "uncertainty_anywhere": uncertainty_anywhere(records),
        "big_n_and_largest": big_n_and_largest(cs, {}, communities_path=f"{OUT}/kinds_merged.csv"),
        "funnel": __import__("analyze").extraction_funnel(records),
        "bold_semantics": make_all.bold_semantics(records),
    }
    with open(f"{OUT}/extra.json", "w", encoding="utf-8") as fh:
        json.dump(extras, fh, indent=1)
    print("wrote", f"{OUT}/extra.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
