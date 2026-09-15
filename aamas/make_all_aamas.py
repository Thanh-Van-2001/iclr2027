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


def protocol_resolution(comparisons: list, protocol: dict, alpha: float = 0.05, seed_mode: str = "or_one") -> dict:
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
        if seed_mode == "stated" and not s:
            no_k += 1
            continue
        if seed_mode == "one":
            s = None
        n = k * (s or (5 if seed_mode == "or_five" else 1))
        scale = 100.0 if kind == "percent" else 1.0
        pw, pr = c["winner"] / scale, c["runner_up"] / scale
        pw, pr = min(max(pw, 0.0), 1.0), min(max(pr, 0.0), 1.0)
        se = math.sqrt(max(pw * (1 - pw), 1e-9) / n + max(pr * (1 - pr), 1e-9) / n)
        gap = abs(pw - pr)
        # Newcombe's interval for a difference of proportions, built from the
        # Wilson limits of each arm, behaves at 0 and 100 percent where the
        # Wald term collapses (SMAC maps won at every episode sit there).
        hi_p, lo_p = max(pw, pr), min(pw, pr)
        l_hi, u_hi = wilson_interval(round(hi_p * n), n)
        l_lo, u_lo = wilson_interval(round(lo_p * n), n)
        newcombe = math.sqrt((hi_p - l_hi) ** 2 + (u_lo - lo_p) ** 2)
        rows.append({"paper": c["paper"], "table": c["table"], "k": k, "seeds": s, "n": n,
                     "gap": round(gap, 4), "resolvable": round(newcombe, 4), "below": gap < newcombe,
                     "resolvable_wald": round(z * se, 4), "below_wald": gap < z * se,
                     "has_bars": c["winner_dispersion"] is not None and c["runner_dispersion"] is not None,
                     "welch_pass": bool(c.get("test")) and c["survives_raw"],
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
            "below_wald": sum(r["below_wald"] for r in rows),
            "pct_below_wald": round(100 * sum(r["below_wald"] for r in rows) / len(rows), 1) if rows else None,
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
                "below": sum(1 for r in rows if r["has_bars"] and r["below"]),
                "welch_pass": sum(1 for r in rows if r["welch_pass"]),
                "welch_pass_below": sum(1 for r in rows if r["welch_pass"] and r["below"])},
            "rows": rows}


ENV_FAMILIES = [
    ("StarCraft (SMAC, SMACv2)", r"smac|starcraft|(?:3s5z|2s3z|5m_vs_6m|corridor|mmm2|protoss|terran|zerg)"),
    ("Multi-agent particle (MPE)", r"mpe|particle|simple_spread|simple spread|cooperative navigation|predator"),
    ("Google Research Football", r"football|grf"),
    ("Overcooked, Hanabi, LBF, RWARE", r"overcooked|hanabi|level-based foraging|lbf|rware|warehouse"),
    ("MuJoCo, D4RL, control", r"mujoco|d4rl|halfcheetah|hopper|walker|ant|humanoid|mamujoco|control suite|dmc"),
    ("Atari, Procgen, games", r"atari|procgen|pong|breakout|melting pot|meltingpot"),
    ("Path finding, routing, scheduling", r"mapf|path[- ]finding|routing|scheduling|vehicle|traffic|warehouse"),
]


def environment_families(comparisons: list) -> dict:
    """Where the testable comparisons come from, by the environment family the
    caption or header names, with the failure rate in each."""
    out = {}
    t = [c for c in comparisons if c.get("test")]
    for name, pat in ENV_FAMILIES:
        rx = re.compile(pat, re.I)
        sel = [c for c in comparisons if rx.search(f"{c.get('caption', '')} {c.get('header_text', '')}")]
        st = [c for c in sel if c.get("test")]
        out[name] = {"comparisons": len(sel), "papers": len({c["paper"] for c in sel}),
                     "pct_neither": round(100 * sum(1 for c in sel if c["winner_dispersion"] is None and c["runner_dispersion"] is None) / max(len(sel), 1), 1),
                     "testable": len(st), "testable_papers": len({c["paper"] for c in st}),
                     "pct_fail": round(100 * sum(1 for c in st if not c["survives_raw"]) / max(len(st), 1), 1) if st else None}
    named = [c for c in comparisons if any(re.search(p, f"{c.get('caption', '')} {c.get('header_text', '')}", re.I) for _, p in ENV_FAMILIES)]
    out["_any_named"] = {"comparisons": len(named), "testable": sum(1 for c in named if c.get("test")),
                         "pct_of_testable": round(100 * sum(1 for c in named if c.get("test")) / max(len(t), 1), 1)}
    return out


def example_three_seeds(comparisons: list) -> dict:
    """The largest gap, in points of a rate, among three-seed rate comparisons
    that still fail Welch's t: the worked example of what three seeds show."""
    sel = [c for c in comparisons if c.get("test") and c["n_runs"] == 3 and not c["survives_raw"]
           and c["dispersion_kind"] in ("std", "unknown") and rate_like(c) == "percent"]
    if not sel:
        return {}
    c = max(sel, key=lambda c: abs(c["winner"] - c["runner_up"]))
    return {"paper": c["paper"], "table": c["table"], "winner": c["winner"], "winner_sd": c["winner_dispersion"],
            "runner_up": c["runner_up"], "runner_sd": c["runner_dispersion"], "n_runs": c["n_runs"],
            "gap": round(abs(c["winner"] - c["runner_up"]), 4), "relative_gap_pct": round(100 * c["relative_gap"], 1),
            "t": round(c["test"]["z"], 2), "df": round(c["test"].get("df", 0.0), 1), "p": round(c["test"]["p"], 3),
            "n_three_seed_failing": len(sel)}


def community_agreement(comm_path: str, second_path: str) -> dict:
    """Agreement between the two labellers (Gemini on every paper, Claude
    Sonnet on a random hundred) under the same prompt: raw agreement and
    Cohen's kappa over the papers both labelled."""
    if not (os.path.exists(comm_path) and os.path.exists(second_path)):
        return {}
    with open(comm_path, encoding="utf-8", newline="") as fh:
        first = {r["id"]: r["label"] for r in csv.DictReader(fh)}
    second = {r["paper"]: r["label"] for r in json.load(open(second_path, encoding="utf-8"))}
    pairs = [(first[p], second[p]) for p in second if p in first and first[p] != "parse_error"]
    if not pairs:
        return {}
    n = len(pairs)
    agree = sum(a == b for a, b in pairs)
    labels = sorted({x for pr in pairs for x in pr})
    pa = agree / n
    pe = sum((sum(1 for a, _ in pairs if a == l) / n) * (sum(1 for _, b in pairs if b == l) / n) for l in labels)
    kappa = (pa - pe) / (1 - pe) if pe < 1 else 1.0
    lo, hi = wilson_interval(agree, n)
    confusion = collections.Counter(pairs)
    return {"n": n, "agree": agree, "pct": round(100 * pa, 1), "ci": [round(100 * lo, 1), round(100 * hi, 1)],
            "kappa": round(kappa, 2),
            "disagreements": [{"first": a, "second": b, "n": c} for (a, b), c in confusion.most_common() if a != b][:10]}


def _rates(cs: list) -> dict:
    t = [c for c in cs if c.get("test")]
    return {"n": len(cs), "papers": len({c["paper"] for c in cs}),
            "pct_neither": round(100 * sum(1 for c in cs if c["winner_dispersion"] is None and c["runner_dispersion"] is None) / max(len(cs), 1), 1),
            "pct_testable": round(100 * len(t) / max(len(cs), 1), 1), "n_testable": len(t),
            "testable_papers": len({c["paper"] for c in t}),
            "pct_fail": round(100 * sum(1 for c in t if not c["survives_raw"]) / max(len(t), 1), 1) if t else None,
            "pct_fail_holm": round(100 * sum(1 for c in t if not c["survives_holm"]) / max(len(t), 1), 1) if t else None}


def readings(records: list, comparisons: list) -> dict:
    """Readings of the corpus a reviewer asked for, each a filter on the
    parser's comparisons rather than a change to the parser: duplicate table
    records removed; tables whose bold cells all lie on one line (the authors'
    row) removed; comparisons with a zero deviation counted."""
    from analyze import ROW_TOL, COLUMN_TOL
    keys = collections.defaultdict(list)
    for r in records:
        for t in r.get("tables", []):
            keys[(r["id"], t.get("number"), t.get("page"))].append(t)
    dup_keys = {k for k, ts in keys.items() if len(ts) > 1}
    in_dup = [c for c in comparisons if (c["paper"], c["table"], c["page"]) in dup_keys]
    not_dup = [c for c in comparisons if (c["paper"], c["table"], c["page"]) not in dup_keys]
    # own-row tables: every bold cell on one line
    own_keys = set()
    for k, ts in keys.items():
        for tb in ts:
            bold = [c for c in tb["cells"] if c["bold"]]
            if len(bold) >= 3:
                ys = sorted(c["y"] for c in bold)
                xs = sorted(c["x"] for c in bold)
                if ys[-1] - ys[0] <= ROW_TOL or xs[-1] - xs[0] <= COLUMN_TOL:
                    own_keys.add(k)
    own = [c for c in comparisons if (c["paper"], c["table"], c["page"]) in own_keys]
    not_own = [c for c in comparisons if (c["paper"], c["table"], c["page"]) not in own_keys]
    t = [c for c in comparisons if c.get("test")]
    zero = [c for c in t if c["winner_dispersion"] == 0 or c["runner_dispersion"] == 0]
    both_zero = [c for c in t if c["winner_dispersion"] == 0 and c["runner_dispersion"] == 0]
    # tables whose caption string holds two "Table n" captions: two tables
    # set side by side that the window merged, a two-column artefact
    merged_keys = set()
    for k, ts in keys.items():
        for tb in ts:
            if len(re.findall(r"\bTable\s+\d+", tb.get("caption", "") or "")) >= 2:
                merged_keys.add(k)
    merged = [c for c in comparisons if (c["paper"], c["table"], c["page"]) in merged_keys]
    not_merged = [c for c in comparisons if (c["paper"], c["table"], c["page"]) not in merged_keys]
    artefact_keys = dup_keys | merged_keys
    clean = [c for c in comparisons if (c["paper"], c["table"], c["page"]) not in artefact_keys]
    abl_rx = re.compile(r"ablat", re.I)
    abl = [c for c in comparisons if abl_rx.search(c.get("caption", "") or "")]
    not_abl = [c for c in comparisons if not abl_rx.search(c.get("caption", "") or "")]
    return {"duplicates": _rates(in_dup), "without_duplicates": _rates(not_dup),
            "merged_caption_tables": {"tables": len(merged_keys), **_rates(merged)}, "without_merged": _rates(not_merged),
            "without_artefacts": _rates(clean),
            "ablation_tables": _rates(abl), "without_ablation": _rates(not_abl),
            "own_row_tables": {"tables": len(own_keys), **_rates(own)}, "without_own_row": _rates(not_own),
            "zero_deviation": {"n_testable_with_a_zero": len(zero), "n_both_zero": len(both_zero),
                               "pct_fail_among_zero": round(100 * sum(1 for c in zero if not c["survives_raw"]) / max(len(zero), 1), 1) if zero else None,
                               "without_zero": _rates([c for c in comparisons if c not in zero])},
            "figure_caption_uncertainty": {
                "papers": sum(1 for r in records if r.get("n_figure_captions_with_uncertainty", 0) > 0),
                "pct_papers": round(100 * sum(1 for r in records if r.get("n_figure_captions_with_uncertainty", 0) > 0) / len(records), 1),
                "testable_papers": sum(1 for r in records if r.get("n_figure_captions_with_uncertainty", 0) > 0
                                       and r["id"] in {c["paper"] for c in t}),
                "n_testable_papers": len({c["paper"] for c in t})}}


def ml_main_text(analysis_path: str = "out/analysis_2025.json", extracted_path: str = "data/extracted_2025.jsonl") -> dict:
    """The NeurIPS/ICML 2025 sample restricted to main-text pages (the first
    nine pages of a NeurIPS paper, eight of an ICML paper, zero-indexed), so
    that the side-by-side does not count appendix tables the AAMAS format has
    no room for."""
    if not os.path.exists(analysis_path):
        return {}
    with open(analysis_path, encoding="utf-8") as fh:
        cs = json.load(fh)["_comparisons"]
    limit = {"NeurIPS": 9, "ICML": 8}
    main = [c for c in cs if c["page"] < limit.get(c["venue"], 9)]
    out = {"all_pages": _rates(cs), "main_text": _rates(main), "page_limits": limit}
    recs = load_records(extracted_path) if os.path.exists(extracted_path) else []
    if recs:
        with_bar = sum(1 for r in recs if any(c.get("dispersion_style") == "pm" and t.get("page", 99) < limit.get(r["venue"], 9)
                                             for t in r.get("tables", []) for c in t["cells"]))
        out["papers_with_main_text_bar_pct"] = round(100 * with_bar / len(recs), 1)
        out["papers"] = len(recs)
    return out


def protocol_span(comparisons: list, protocol: dict) -> dict:
    """The below-resolution share under each reading of the seed count."""
    rows = {}
    for name, mode in (("seeds_stated_or_one", "or_one"), ("seeds_stated_only", "stated"), ("seeds_one_for_all", "one"),
                       ("seeds_stated_or_five", "or_five")):
        pr = protocol_resolution(comparisons, protocol, seed_mode=mode)
        rows[name] = {k: pr[k] for k in ("n_with_episode_count", "n_papers", "below_resolution", "pct_below", "ci", "paper_ci")}
    base = protocol_resolution(comparisons, protocol)
    by_paper = collections.Counter(r["paper"] for r in base["rows"])
    top = by_paper.most_common(1)[0] if by_paper else (None, 0)
    per_paper = {}
    for r in base["rows"]:
        per_paper.setdefault(r["paper"], []).append(r["below"])
    rows["largest_paper_share_pct"] = round(100 * top[1] / max(len(base["rows"]), 1), 1)
    rows["per_paper_pct_below"] = sorted(round(100 * sum(v) / len(v), 1) for v in per_paper.values())
    return rows


def recall_breakdown(records: list, items_path: str = "audits/aamas_pages/items.json",
                     labels_path: str = "audits/aamas_pages/labels.json") -> dict:
    """Where the reader's groups on random pages fall relative to the parser:
    on pages where the parser detected no table (a detection failure), on
    pages where it detected a table but produced no comparison (its rules), or
    on pages where both list groups. Also the concentration of the reader's
    groups across pages."""
    if not (os.path.exists(items_path) and os.path.exists(labels_path)):
        return {}
    from analyze import comparisons_from_table
    items = {it["id"]: it for it in json.load(open(items_path, encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open(labels_path, encoding="utf-8"))}
    recs = {r["id"]: r for r in records}
    out = collections.Counter()
    per_page = []
    for i, it in items.items():
        lb = labels.get(i)
        if not lb:
            continue
        rtabs = [t for t in lb["tables"] if str(t.get("results_table", "")).lower().startswith("y")]
        rg = sum(len(t.get("groups", [])) for t in rtabs)
        per_page.append(rg)
        if rg == 0:
            out["pages_reader_no_groups"] += 1
            continue
        ptabs = [t for t in recs[it["paper"]]["tables"] if t.get("page") == it["page"]]
        pg = sum(len(comparisons_from_table(t)) for t in ptabs)
        if not ptabs:
            out["pages_no_parser_table"] += 1
            out["groups_no_parser_table"] += rg
        elif pg == 0:
            out["pages_parser_table_no_groups"] += 1
            out["groups_parser_table_no_groups"] += rg
        else:
            out["pages_both"] += 1
            out["groups_both"] += rg
    per_page.sort(reverse=True)
    total = sum(per_page)
    return {**out, "reader_groups_total": total,
            "top5_pages_share_pct": round(100 * sum(per_page[:5]) / max(total, 1), 1),
            "pages_at_cap": sum(1 for x in per_page if x >= 40)}


def table_retention_bias(records: list) -> dict:
    """Share of detected tables with any +/- cell, among tables that yield a
    comparison and among those that do not: whether the parser's rules keep
    bar-carrying tables preferentially."""
    from analyze import comparisons_from_table
    kept = disc = kept_bar = disc_bar = 0
    for r in records:
        for t in r.get("tables", []):
            bar = any(c.get("dispersion_style") == "pm" for c in t["cells"])
            if comparisons_from_table(t):
                kept += 1; kept_bar += bar
            else:
                disc += 1; disc_bar += bar
    return {"tables_kept": kept, "pct_kept_with_bar": round(100 * kept_bar / max(kept, 1), 1),
            "tables_discarded": disc, "pct_discarded_with_bar": round(100 * disc_bar / max(disc, 1), 1)}


def denominators(records: list, comparisons: list, protocol: dict) -> dict:
    """The shares a reviewer asked for over the right populations: K stated
    among papers with a rate comparison; a +/- cell among papers with a
    highlighted comparison."""
    recs = {r["id"]: r for r in records}
    rate_papers = {c["paper"] for c in comparisons if rate_like(c)}
    claim_papers = {c["paper"] for c in comparisons}
    t = [c for c in comparisons if c.get("test")]
    return {"rate_papers": len(rate_papers),
            "rate_papers_stating_k": sum(1 for p in rate_papers if protocol.get(p, {}).get("eval_episodes")),
            "pct_rate_papers_stating_k": round(100 * sum(1 for p in rate_papers if protocol.get(p, {}).get("eval_episodes")) / max(len(rate_papers), 1), 1),
            "claim_papers": len(claim_papers),
            "pct_claim_papers_with_pm": round(100 * sum(1 for p in claim_papers if recs[p].get("reports_explicit_error_bar")) / max(len(claim_papers), 1), 1),
            "welch_n": sum(1 for c in t if c["test"].get("test") == "welch"),
            "z_n": sum(1 for c in t if c["test"].get("test") != "welch"),
            "welch_fail": round(100 * sum(1 for c in t if c["test"].get("test") == "welch" and not c["survives_raw"]) / max(sum(1 for c in t if c["test"].get("test") == "welch"), 1), 1),
            "z_fail": round(100 * sum(1 for c in t if c["test"].get("test") != "welch" and not c["survives_raw"]) / max(sum(1 for c in t if c["test"].get("test") != "welch"), 1), 1),
            "top10_papers_share_of_testable": round(100 * sum(sorted(collections.Counter(c["paper"] for c in t).values(), reverse=True)[:10]) / max(len(t), 1), 1)}


CITED = {
    "gorsane2022": r"standardi[sz]ed performance evaluation protocol",
    "agarwal2021": r"statistical precipice",
    "colas2018": r"how many random seeds",
    "henderson2018": r"reinforcement learning that matters",
    "papoudakis2021": r"benchmarking multi-?agent deep reinforcement learning",
    "patterson2023": r"empirical design in reinforcement learning",
}


def citation_conditioned(records: list, comparisons: list, protocol: dict, corpus_dir: str = "data/corpus") -> dict:
    """Among papers with a highlighted comparison: do those that cite the
    evaluation-methodology literature print bars, run counts and episode
    counts more often? Citation is detected in the paper's text by author
    name and title words."""
    import fitz
    recs = {r["id"]: r for r in records}
    claim_papers = sorted({c["paper"] for c in comparisons})
    cites = {}
    for pid in claim_papers:
        r = recs[pid]
        path = os.path.join(corpus_dir, f"{r['venue']}{r['year']}_{pid}.pdf")
        if not os.path.exists(path):
            continue
        try:
            text = " ".join(pg.get_text() for pg in fitz.open(path))
        except Exception:  # noqa: BLE001
            continue
        text = re.sub(r"\s+", " ", text)
        cites[pid] = {k: bool(re.search(pat, text, re.I)) for k, pat in CITED.items()}
    def group(ids):
        cs = [c for c in comparisons if c["paper"] in ids]
        t = [c for c in cs if c.get("test")]
        return {"papers": len(ids), "comparisons": len(cs),
                "pct_papers_pm": round(100 * sum(1 for p in ids if recs[p].get("reports_explicit_error_bar")) / max(len(ids), 1), 1),
                "pct_papers_runs": round(100 * sum(1 for p in ids if recs[p].get("n_runs_global")) / max(len(ids), 1), 1),
                "pct_papers_k": round(100 * sum(1 for p in ids if protocol.get(p, {}).get("eval_episodes")) / max(len(ids), 1), 1),
                "pct_neither": round(100 * sum(1 for c in cs if c["winner_dispersion"] is None and c["runner_dispersion"] is None) / max(len(cs), 1), 1),
                "pct_testable": round(100 * len(t) / max(len(cs), 1), 1),
                "pct_fail": round(100 * sum(1 for c in t if not c["survives_raw"]) / max(len(t), 1), 1) if t else None,
                "n_testable": len(t)}
    citing = {p for p, d in cites.items() if any(d.values())}
    not_citing = {p for p in cites if p not in citing}
    return {"detected_in": len(cites), "per_work": {k: sum(1 for d in cites.values() if d[k]) for k in CITED},
            "citing": group(citing), "not_citing": group(not_citing)}


def reference_disagreements(items_path: str = "audits/aamas_gold/items.json",
                            labels_path: str = "audits/aamas_gold/labels.csv") -> dict:
    """On the testable reference items where reader and parser disagree on the
    claim, which way the parser's verdict went: a spurious survival biases the
    failure rate down, a spurious failure up."""
    if not (os.path.exists(items_path) and os.path.exists(labels_path)):
        return {}
    from gold_set import _match, _num, _unclear, _pipeline_test
    items = {it["id"]: it for it in json.load(open(items_path, encoding="utf-8"))}
    rows = {r["id"]: r for r in csv.DictReader(open(labels_path, encoding="utf-8", newline=""))}
    vf = (("winner_mean", "winner"), ("winner_disp", "winner_dispersion"), ("runner_mean", "runner_up"), ("runner_disp", "runner_dispersion"))
    n = survive = fail = 0
    for i, r in rows.items():
        it = items[i]
        if it["stratum"] != "testable" or it.get("mark") is None or not r["results_table"].lower().startswith("y"):
            continue
        bad = not r["bold_ok"].lower().startswith("y") or any(
            not _unclear(r[f]) and not _match(_num(r[f]), it["pipeline"][k]) for f, k in vf)
        if not bad:
            continue
        t = _pipeline_test(it)
        if not t:
            continue
        n += 1
        if t["p"] >= 0.05:
            fail += 1
        else:
            survive += 1
    return {"n": n, "parser_survives": survive, "parser_fails": fail}


def reader_protocol(path: str = "out/aamas/protocol_reader.json") -> dict:
    """The language model's reading of K and seeds for every paper with a
    rate comparison, in the shape protocol_resolution() takes, plus its
    agreement with the regular expressions."""
    if not os.path.exists(path):
        return {}, {}
    rd = json.load(open(path, encoding="utf-8"))
    rx = json.load(open(f"{OUT}/protocol.json", encoding="utf-8"))
    proto = {}
    for pid, d in rd.items():
        k = d.get("eval_episodes") if isinstance(d.get("eval_episodes"), int) else None
        sd = d.get("seeds") if isinstance(d.get("seeds"), int) else None
        proto[pid] = {"eval_episodes": k, "seeds": sd}
    both = [pid for pid in rd if proto[pid]["eval_episodes"] and rx.get(pid, {}).get("eval_episodes")]
    sboth = [pid for pid in rd if proto[pid]["seeds"] and rx.get(pid, {}).get("seeds")]
    stats = {"papers": len(rd),
             "reader_k": sum(1 for pid in rd if proto[pid]["eval_episodes"]),
             "regex_k": sum(1 for pid in rd if rx.get(pid, {}).get("eval_episodes")),
             "both_k": len(both), "agree_k": sum(1 for pid in both if proto[pid]["eval_episodes"] == rx[pid]["eval_episodes"]),
             "reader_seeds": sum(1 for pid in rd if proto[pid]["seeds"]),
             "regex_seeds": sum(1 for pid in rd if rx.get(pid, {}).get("seeds")),
             "both_seeds": len(sboth), "agree_seeds": sum(1 for pid in sboth if proto[pid]["seeds"] == rx[pid]["seeds"]),
             "mean_over_seeds_yes": sum(1 for d in rd.values() if d.get("rate_is_mean_over_seeds") == "yes"),
             "mean_over_seeds_no": sum(1 for d in rd.values() if d.get("rate_is_mean_over_seeds") == "no"),
             "checkpoint_best": sum(1 for d in rd.values() if d.get("checkpoint") == "best"),
             "checkpoint_final": sum(1 for d in rd.values() if d.get("checkpoint") == "final")}
    return proto, stats


def single_column_reference(path: str = "out/gold_set_pages.json") -> dict:
    """The parser's recall and precision on single-column pages, from the
    concurrent study's random-page reading, for the cross-format comparison."""
    if not os.path.exists(path):
        return {}
    d = json.load(open(path, encoding="utf-8"))
    return {"recall_pct": d["reader_groups_found_by_pipeline"]["pct"],
            "recall_page_ci": d["reader_groups_found_by_pipeline"].get("page_ci"),
            "precision_pct": d["pipeline_groups_found_by_reader"]["pct"],
            "pages": d["n_pages"], "reader_groups": d["reader"]["groups"],
            "reader_pct_neither": d["reader"]["pct_neither"], "reader_ci_neither": d["reader"]["ci_neither"],
            "reader_pct_testable": d["reader"]["pct_testable"], "reader_ci_testable": d["reader"]["ci_testable"],
            "pipe_pct_neither": d["pipeline_same_pages"]["pct_neither"],
            "pipe_pct_testable": d["pipeline_same_pages"]["pct_testable"]}


def duplicate_table_records(records: list) -> dict:
    """Tables the parser recorded more than once under one (paper, number,
    page): a two-column artefact in which a caption is attached to a body
    from the neighbouring column, or a table is split. The reference-set kit
    could not box a cell in such a table, and the comparisons they hold are
    counted here so the paper can say how much of the corpus they are."""
    from analyze import comparisons_from_table
    keys = collections.defaultdict(list)
    for r in records:
        for t in r.get("tables", []):
            keys[(r["id"], t.get("number"), t.get("page"))].append(t)
    dup = {k: ts for k, ts in keys.items() if len(ts) > 1}
    identical = sum(1 for ts in dup.values()
                    if len({tuple((c["x"], c["y"], c["mean"]) for c in t["cells"]) for t in ts}) < len(ts))
    n_cmp = sum(len(comparisons_from_table(t)) for ts in dup.values() for t in ts)
    total = sum(len(comparisons_from_table(t)) for ts in keys.values() for t in ts)
    return {"table_keys": len(keys), "duplicate_keys": len(dup), "identical_records": identical,
            "tables_in_duplicates": sum(len(ts) for ts in dup.values()),
            "comparisons_in_duplicates": n_cmp, "pct_of_comparisons": round(100 * n_cmp / max(total, 1), 1)}


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
        "duplicate_table_records": duplicate_table_records(records),
        "environment_families": environment_families(cs),
        "example_three_seeds": example_three_seeds(cs),
        "community_agreement": community_agreement(f"{OUT}/communities.csv", "audits/aamas_comm_check/labels_sonnet.json"),
        "readings": readings(records, cs),
        "recall_breakdown": recall_breakdown(records),
        "denominators": denominators(records, cs, protocol),
        "citation_conditioned": citation_conditioned(records, cs, protocol),
        "single_column_reference": single_column_reference(),
        "reference_disagreements": reference_disagreements(),
        "table_retention_bias": table_retention_bias(records),
        "ml_main_text": ml_main_text(),
        "protocol_span": protocol_span(cs, protocol),
        "protocol_reader": (lambda pr_: {"stats": pr_[1],
                                         "resolution": {k: v for k, v in protocol_resolution(cs, pr_[0]).items() if k != "rows"},
                                         "resolution_stated_seeds": {k: v for k, v in protocol_resolution(cs, pr_[0], seed_mode="stated").items() if k != "rows"}}
                            if pr_[0] else {})(reader_protocol()),
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
