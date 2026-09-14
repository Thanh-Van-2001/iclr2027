"""Every derived number of the AAMAS paper, from data/extracted_aamas.jsonl.

Same instrument and the same functions as the ICLR study (study/), applied to
the AAMAS corpus, plus what is specific to this paper: per-year and
per-community splits, the evaluation-protocol resolution of win and success
rates, and the side-by-side with the NeurIPS/ICML 2025 sample.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import (analyse, checklist_agreement, extraction_funnel, load_records)  # noqa: E402
from sensitivity import (checkability_span, correlation_sensitivity, design_mde,  # noqa: E402
                         error_bar_meaning, paper_level_crosstab, power_audit, run_count_scope)
import extra_stats  # noqa: E402
import make_all  # noqa: E402
from binomial_check import analyse as binom_analyse  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

OUT = "out/aamas"
EXTRACTED = "data/extracted_aamas.jsonl"


def load_unique(path: str) -> list:
    seen, out = set(), []
    for r in load_records(path):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append(r)
    return out


def summary_and_boot(records: list) -> tuple:
    a = analyse(records)
    cs = a["_comparisons"]
    if not cs:
        return a, {"papers": len(records), "comparisons": 0}, {}
    return a, make_all._summary(a, cs), make_all._bootstrap(cs)


def rate_like(c: dict) -> str | None:
    """'proportion' or 'percent' if the compared values read as a rate over
    episodes (win rate, success rate, solved share), else None."""
    text = f"{c.get('caption', '')} {c.get('header_text', '')}".lower()
    if not re.search(r"win[\s-]?rate|success[\s-]?rate|success|winrate|solved|win %|win\b|completion rate|reach", text):
        return None
    w, r = c["winner"], c["runner_up"]
    if 0 <= w <= 1 and 0 <= r <= 1:
        return "proportion"
    if 0 <= w <= 100 and 0 <= r <= 100 and (w > 1 or r > 1):
        return "percent"
    return None


def protocol_resolution(comparisons: list, protocol: dict, alpha: float = 0.05) -> dict:
    """For rate-like comparisons, the gap a two-proportion test could resolve
    at the paper's stated number of evaluation episodes times seeds, against
    the printed gap. This is the binomial resolution of the evaluation
    protocol itself, with no error bar needed."""
    z = 1.959964
    rows, no_k, no_rate = [], 0, 0
    for c in comparisons:
        kind = rate_like(c)
        if kind is None:
            no_rate += 1
            continue
        p = protocol.get(c["paper"], {})
        k = p.get("eval_episodes")
        s = c.get("n_runs") or p.get("seeds")
        if not k:
            no_k += 1
            continue
        n = k * (s or 1)
        scale = 100.0 if kind == "percent" else 1.0
        pw, pr = c["winner"] / scale, c["runner_up"] / scale
        se = math.sqrt(max(pw * (1 - pw), 1e-9) / n + max(pr * (1 - pr), 1e-9) / n)
        gap = abs(pw - pr)
        rows.append({"paper": c["paper"], "table": c["table"], "k": k, "seeds": s, "n": n,
                     "gap": round(gap, 4), "resolvable": round(z * se, 4), "below": gap < z * se,
                     "has_bars": c["winner_dispersion"] is not None and c["runner_dispersion"] is not None,
                     "seed_assumed_one": s is None})
    below = sum(r["below"] for r in rows)
    lo, hi = wilson_interval(below, len(rows)) if rows else (0, 0)
    papers = {r["paper"] for r in rows}
    # cluster bootstrap over papers
    by_paper = collections.defaultdict(list)
    for r in rows:
        by_paper[r["paper"]].append(r["below"])
    import random
    rng = random.Random(0)
    keys = list(by_paper)
    boots = []
    for _ in range(2000):
        draw = [by_paper[keys[rng.randrange(len(keys))]] for _ in keys]
        flat = [x for d in draw for x in d]
        boots.append(100 * sum(flat) / max(len(flat), 1))
    boots.sort()
    ks = sorted(r["k"] for r in rows)
    return {"n_rate_like": len(rows) + no_k, "n_with_episode_count": len(rows),
            "n_without_episode_count": no_k, "n_papers": len(papers),
            "below_resolution": below,
            "pct_below": round(100 * below / len(rows), 1) if rows else None,
            "ci": [round(100 * lo, 1), round(100 * hi, 1)],
            "paper_ci": [round(boots[50], 1), round(boots[1949], 1)] if rows else None,
            "median_episodes": ks[len(ks) // 2] if ks else None,
            "pct_seed_assumed_one": round(100 * sum(r["seed_assumed_one"] for r in rows) / max(len(rows), 1), 1),
            "below_among_bar_less": {
                "n": sum(1 for r in rows if not r["has_bars"]),
                "below": sum(1 for r in rows if not r["has_bars"] and r["below"])},
            "below_among_barred": {
                "n": sum(1 for r in rows if r["has_bars"]),
                "below": sum(1 for r in rows if r["has_bars"] and r["below"])},
            "rows": rows}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    records = load_unique(EXTRACTED)
    analysis, summary, boot = summary_and_boot(records)
    with open(f"{OUT}/analysis.json", "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=1)
    cs = analysis["_comparisons"]
    print(f"AAMAS: {summary['papers']} papers, {summary['comparisons']} comparisons, "
          f"{summary['pct_neither']}% neither, {summary['pct_testable']}% testable, {summary['pct_fail']}% fail")

    by_year = {}
    for year in sorted({r["year"] for r in records}):
        recs = [r for r in records if r["year"] == year]
        a, s, b = summary_and_boot(recs)
        by_year[str(year)] = {"summary": s, "bootstrap": b}
        print(f"  {year}: {s['papers']} papers, {s['comparisons']} comparisons, {s['pct_neither']}% neither, "
              f"{s['pct_testable']}% testable, {s['pct_fail']}% fail")

    by_comm = {}
    comm_path = f"{OUT}/communities.csv"
    if os.path.exists(comm_path):
        with open(comm_path, encoding="utf-8", newline="") as fh:
            label = {r["id"]: r["label"] for r in csv.DictReader(fh)}
        for lab in sorted(set(label.values())):
            ids = {i for i, l in label.items() if l == lab}
            recs = [r for r in records if r["id"] in ids]
            if not recs or not any(t for r in recs for t in r.get("tables", [])):
                by_comm[lab] = {"summary": {"papers": len(recs), "comparisons": 0}}
                continue
            a, s, b = summary_and_boot(recs)
            by_comm[lab] = {"summary": s, "bootstrap": b,
                            "pct_papers_with_table_claim": round(100 * len({c["paper"] for c in a["_comparisons"]}) / len(recs), 1)}
        by_comm["_unlabelled_papers"] = sum(1 for r in records if r["id"] not in label)

    protocol = json.load(open(f"{OUT}/protocol.json", encoding="utf-8")) if os.path.exists(f"{OUT}/protocol.json") else {}
    res = protocol_resolution(cs, protocol)
    print(f"  protocol resolution: {res['n_with_episode_count']} rate-like comparisons with an episode count, "
          f"{res['pct_below']}% below it")

    with open("out/both_years.json", encoding="utf-8") as fh:
        ml = json.load(fh)
    side = {"aamas": summary, "neurips_icml_2025": ml["2025"], "neurips_icml_2024": ml["2024"]}

    extras = {
        "summary": summary, "bootstrap": boot, "by_year": by_year, "by_community": by_comm,
        "side_by_side": side, "protocol_resolution": {k: v for k, v in res.items() if k != "rows"},
        "headline_span": extra_stats.headline_span(cs, records),
        "subset_direction": extra_stats.subset_direction(records, cs),
        "holm_families": extra_stats.holm_families(cs),
        "failure_by_gap_band": extra_stats.failure_by_gap_band(cs),
        "tie_marking": extra_stats.tie_marking(records, cs),
        "extraction_limits": extra_stats.extraction_limits(records),
        "filter_selection": extra_stats.filter_selection(records),
        "run_count_scope": run_count_scope(cs, records),
        "error_bar_meaning": error_bar_meaning(cs),
        "paper_level_crosstab": paper_level_crosstab(records),
        "correlation_sensitivity": correlation_sensitivity(cs),
        "checkability_span": checkability_span(cs),
        "binomial_check": dict(binom_analyse(cs), metric_named=binom_analyse(cs, metric_named=True)),
        "power_audit": power_audit(cs),
        "design_mde": design_mde(cs, records),
        "funnel": extraction_funnel(records),
        "checklist": checklist_agreement(records),
        "bold_semantics": make_all.bold_semantics(records),
        "protocol_stats": {
            "papers_scanned": len(protocol),
            "state_eval_episodes": sum(1 for p in protocol.values() if p.get("eval_episodes")),
            "state_seeds": sum(1 for p in protocol.values() if p.get("seeds")),
            "episode_counts": collections.Counter(p["eval_episodes"] for p in protocol.values() if p.get("eval_episodes")).most_common(12),
        },
    }
    with open(f"{OUT}/extra.json", "w", encoding="utf-8") as fh:
        json.dump(extras, fh, indent=1)
    with open(f"{OUT}/protocol_resolution_rows.json", "w", encoding="utf-8") as fh:
        json.dump(res["rows"], fh, indent=1)
    print("wrote", f"{OUT}/extra.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
