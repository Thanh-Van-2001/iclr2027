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


RATE_WORDS = r"win(?:ning)?[\s-]?rate|success[\s-]?rate|winrate|success \(?%|solved|solve[\s-]?rate|completion rate|win %"
MEDIAN_RX = re.compile(r"\bmedian\b|\bIQM\b", re.I)


def exact_copies(comparisons: list) -> tuple:
    """Comparisons that are exact copies of another on the same page under a
    different table key: the same winner cell position, values and bars. A
    body line taken for a caption yields a second record of the same table
    that the (paper, number, page) duplicate filter does not catch (a
    reviewer found 86 of them). Returns (copies, first occurrences)."""
    seen, copies, kept = set(), [], []
    for c in comparisons:
        key = (c["paper"], c["page"], round(c["winner_cell"]["x"], 1), round(c["winner_cell"]["y"], 1),
               c["winner"], c["runner_up"], c["winner_dispersion"], c["runner_dispersion"])
        if key in seen:
            copies.append(c)
        else:
            seen.add(key)
            kept.append(c)
    return copies, kept


def rate_like(c: dict) -> str | None:
    """'proportion' or 'percent' if the compared values read as a rate over
    episodes (win rate, success rate, solved share), else None."""
    text = f"{c.get('caption', '')} {c.get('header_text', '')}".lower()
    # a named rate only: an earlier pattern also took "reach" and a bare
    # "win", which admitted an efficiency table (a reviewer's example)
    if not re.search(RATE_WORDS, text):
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
        # the seed count from the protocol reading first, the parser's run
        # count second; a parser count equal to K is the episode count read
        # twice, not a seed count (an earlier version squared K that way)
        s = p.get("seeds") or (c.get("n_runs") if c.get("n_runs") != k else None)
        if not k:
            no_k += 1
            continue
        if seed_mode == "stated" and not s:
            no_k += 1
            continue
        if seed_mode == "one":
            s = None
        fixed = p.get("episodes_kind") == "fixed_instances"
        if seed_mode == "typed" and fixed:
            # a fixed set of K instances: seeds re-run the same items and do
            # not multiply the trials
            n = k
        else:
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
                     "fixed_instances": fixed, "k_inherited": bool(p.get("k_inherited")),
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
    ("StarCraft (SMAC, SMACv2)", r"\bsmac|starcraft|\b(?:3s5z|2s3z|5m_vs_6m|corridor|mmm2|protoss|terran|zerg)\b"),
    ("Multi-agent particle (MPE)", r"\bmpe\b|particle|simple_spread|simple spread|cooperative navigation|predator"),
    ("Google Research Football", r"football|\bgrf\b"),
    ("Overcooked, Hanabi, LBF, RWARE", r"overcooked|hanabi|level-based foraging|\blbf\b|\brware\b|warehouse"),
    ("MuJoCo, D4RL, control", r"mujoco|d4rl|halfcheetah|\bhopper\b|\bwalker|\bant\b|humanoid|mamujoco|control suite|\bdmc\b"),
    ("Atari, Procgen, games", r"atari|procgen|\bpong\b|breakout|melting ?pot"),
    ("Path finding, routing, scheduling", r"\bmapf\b|path[- ]finding|routing|scheduling|vehicle|traffic|warehouse"),
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
    out = {"paper": c["paper"], "table": c["table"], "page": c["page"], "winner": c["winner"], "winner_sd": c["winner_dispersion"],
           "runner_up": c["runner_up"], "runner_sd": c["runner_dispersion"], "n_runs": c["n_runs"],
           "n_runs_source": c.get("n_runs_source"),
           "gap": round(abs(c["winner"] - c["runner_up"]), 4), "relative_gap_pct": round(100 * c["relative_gap"], 1),
           "t": round(c["test"]["z"], 2), "df": round(c["test"].get("df", 0.0), 1), "p": round(c["test"]["p"], 3),
           "n_three_seed_failing": len(sel)}
    # the census reader's run count for the same table, and the test under it
    cz_path = f"{OUT}/gold_set_census.json"
    if os.path.exists(cz_path):
        from analyze import p_value
        for pg in json.load(open(cz_path, encoding="utf-8"))["per_page"]:
            if pg["paper"] != c["paper"]:
                continue
            for g in pg.get("tested_groups", []):
                if g.get("w") is not None and abs(g["w"] - c["winner"]) < 1e-6 and g.get("n"):
                    n2 = int(g["n"])
                    res = p_value(abs(c["winner"] - c["runner_up"]), c["winner_dispersion"] / n2 ** 0.5,
                                  c["runner_dispersion"] / n2 ** 0.5, n2)
                    if res:
                        out["reader_n"] = n2
                        out["reader_t"] = round(res["z"], 2)
                        out["reader_df"] = round(res.get("df", 0.0), 1)
                        out["reader_p"] = round(res["p"], 3)
                    break
            if "reader_n" in out:
                break
    return out


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


def _boot_fail(t: list, reps: int = 2000, seed: int = 0) -> list | None:
    """95% cluster bootstrap over papers of the failure rate among tested
    comparisons, for the rows of Table 3."""
    import random
    by = collections.defaultdict(list)
    for c in t:
        by[c["paper"]].append(not c["survives_raw"])
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


def _rates(cs: list) -> dict:
    t = [c for c in cs if c.get("test")]
    return {"n": len(cs), "papers": len({c["paper"] for c in cs}),
            "ci_fail": _boot_fail(t),
            "pct_neither": round(100 * sum(1 for c in cs if c["winner_dispersion"] is None and c["runner_dispersion"] is None) / max(len(cs), 1), 1),
            "pct_testable": round(100 * len(t) / max(len(cs), 1), 1), "n_testable": len(t),
            "testable_papers": len({c["paper"] for c in t}),
            "pct_fail": round(100 * sum(1 for c in t if not c["survives_raw"]) / max(len(t), 1), 1) if t else None,
            "pct_fail_holm": round(100 * sum(1 for c in t if not c["survives_holm"]) / max(len(t), 1), 1) if t else None}


def ddof_reading(comparisons: list) -> dict:
    """A printed deviation read as a population standard deviation (numpy's
    default) rather than a sample one: the sample deviation Welch's t wants
    is larger by sqrt(n/(n-1)), 22 percent at three seeds, so this reading
    fails more often. Standard errors and intervals are unchanged."""
    from analyze import p_value
    t = [c for c in comparisons if c.get("test")]
    fails = n = 0
    for c in t:
        if c["dispersion_kind"] in ("std", "unknown") and c.get("n_runs") and c["n_runs"] >= 2:
            k = c["n_runs"]
            f = (k / (k - 1)) ** 0.5
            res = p_value(abs(c["winner"] - c["runner_up"]), c["winner_dispersion"] * f / k ** 0.5,
                          c["runner_dispersion"] * f / k ** 0.5, k)
            fail = (res["p"] >= 0.05) if res else (not c["survives_raw"])
        else:
            fail = not c["survives_raw"]
        n += 1
        fails += fail
    return {"n": n, "pct_fail": round(100 * fails / max(n, 1), 1), "papers": len({c["paper"] for c in t})}


def resolution_lookup() -> list:
    """The binomial resolution of a rate comparison at common (K, seeds)
    pairs, near p = 0.5 and p = 0.8, as Newcombe's interval gives it: the
    table a reviewer can apply without a calculator."""
    rows = []
    for k, s_ in ((10, 1), (10, 3), (10, 5), (32, 1), (32, 3), (32, 5), (32, 10), (100, 1), (100, 3), (100, 5), (1000, 1), (1000, 5)):
        n = k * s_
        out = {"k": k, "seeds": s_, "n": n}
        for p, name in ((0.5, "half"), (0.8, "eighty")):
            l, u = wilson_interval(round(p * n), n)
            out[name] = round(100 * math.sqrt((p - l) ** 2 + (u - p) ** 2), 1)
        rows.append(out)
    return rows


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
    copies, deduped = exact_copies(comparisons)
    copy_ids = {id(c) for c in copies}
    clean_all = [c for c in clean if id(c) not in copy_ids]
    big = [c for c in comparisons if c.get("test") and c.get("n_runs") and c["n_runs"] > 30]
    not_big = [c for c in comparisons if not (c.get("test") and c.get("n_runs") and c["n_runs"] > 30)]
    med = [c for c in comparisons if c.get("test") and MEDIAN_RX.search(c.get("caption", "") or "")]
    not_med = [c for c in comparisons if not (c.get("test") and MEDIAN_RX.search(c.get("caption", "") or ""))]
    return {"duplicates": _rates(in_dup), "without_duplicates": _rates(not_dup),
            "merged_caption_tables": {"tables": len(merged_keys), **_rates(merged)}, "without_merged": _rates(not_merged),
            "without_artefacts": _rates(clean),
            "exact_copies": {"papers_with_copies": len({c["paper"] for c in copies}), **_rates(copies)},
            "without_exact_copies": _rates(deduped),
            "without_all_artefacts": _rates(clean_all),
            "run_count_above_30": _rates(big), "without_run_count_above_30": _rates(not_big),
            "median_or_iqm_captions": _rates(med), "without_median_or_iqm": _rates(not_med),
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
                       ("seeds_stated_or_five", "or_five"), ("typed", "typed")):
        pr = protocol_resolution(comparisons, protocol, seed_mode=mode)
        rows[name] = {k: pr[k] for k in ("n_with_episode_count", "n_papers", "below_resolution", "pct_below", "ci", "paper_ci")}
    base = protocol_resolution(comparisons, protocol)
    by_paper = collections.Counter(r["paper"] for r in base["rows"])
    top = by_paper.most_common(1)[0] if by_paper else (None, 0)
    per_paper = {}
    for r in base["rows"]:
        per_paper.setdefault(r["paper"], []).append(r["below"])
    rows["largest_paper_share_pct"] = round(100 * top[1] / max(len(base["rows"]), 1), 1)
    rest = [r for r in base["rows"] if r["paper"] != top[0]]
    rows["without_largest_paper"] = {"n": len(rest), "papers": len({r["paper"] for r in rest}),
                                     "pct_below": round(100 * sum(r["below"] for r in rest) / max(len(rest), 1), 1) if rest else None}
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


SMAC_FAMILY = ("SMAC", "SMACv2")
PYMARL_TEST_NEPISODE = 32  # test_nepisode in PyMARL's default config, inherited by SMAC papers that state no K

ENV_GROUPS = [
    ("SMAC / SMACv2", ("SMAC", "SMACv2", "StarCraft-other")),
    ("Google Research Football", ("GRF",)),
    ("MPE", ("MPE",)),
    ("MaMuJoCo", ("MaMuJoCo",)),
    ("Hanabi / Overcooked / Melting Pot", ("Hanabi", "Overcooked", "MeltingPot")),
    ("single-agent MuJoCo, DMC, D4RL", ("MuJoCo/DMC single-agent", "D4RL")),
    ("Atari", ("Atari",)),
    ("gridworlds", ("gridworld/MiniGrid",)),
    ("traffic", ("traffic (SUMO/CityFlow)",)),
    ("LLM benchmarks", ("LLM benchmark",)),
    ("matrix and normal-form games", ("matrix/normal-form games",)),
]


def _env_group(env: str) -> str | None:
    for name, keys in ENV_GROUPS:
        for k in keys:
            if env == k or env.startswith(k):
                return name
    return None


def reader_protocol2(path: str = "out/aamas/protocol_reader2.json") -> tuple:
    """The extended protocol reading: K, seeds, whether the episodes are a
    fixed instance set, the environments, the codebase, whether the arms
    share evaluation episodes and what the deviation is over. Returns the
    protocol dict in the shape protocol_resolution() takes (with
    episodes_kind), the same with PyMARL's evaluation count imputed to
    SMAC-family papers that state none, and summary statistics."""
    if not os.path.exists(path):
        return {}, {}, {}
    rd = json.load(open(path, encoding="utf-8"))
    proto, inherited = {}, {}
    for pid, d in rd.items():
        if "parse_error" in d:
            continue
        k = d.get("eval_episodes") if isinstance(d.get("eval_episodes"), int) else None
        sd = d.get("seeds") if isinstance(d.get("seeds"), int) else None
        envs = d.get("environments") if isinstance(d.get("environments"), list) else []
        base = {"eval_episodes": k, "seeds": sd, "episodes_kind": d.get("episodes_kind"),
                "environments": envs, "agents": d.get("agents"), "framework": d.get("framework") or "",
                "follows_standard_setup": d.get("follows_standard_setup") or "",
                "shares_eval_episodes": d.get("shares_eval_episodes"), "sd_over": d.get("sd_over")}
        proto[pid] = base
        inh = dict(base)
        if not k and any(str(e).startswith(SMAC_FAMILY) for e in envs):
            inh["eval_episodes"] = PYMARL_TEST_NEPISODE
            inh["k_inherited"] = True
        inherited[pid] = inh
    n = len(proto)
    stats = {"papers": n,
             "with_k": sum(1 for p in proto.values() if p["eval_episodes"]),
             "with_seeds": sum(1 for p in proto.values() if p["seeds"]),
             "fixed_instances": sum(1 for p in proto.values() if p["episodes_kind"] == "fixed_instances"),
             "sampled": sum(1 for p in proto.values() if p["episodes_kind"] == "sampled"),
             "smac_family": sum(1 for p in proto.values() if any(str(e).startswith(SMAC_FAMILY) for e in p["environments"])),
             "smac_family_no_k": sum(1 for p in inherited.values() if p.get("k_inherited")),
             "framework_named": sum(1 for p in proto.values() if p["framework"]),
             "follows_standard_setup": sum(1 for p in proto.values() if p["follows_standard_setup"]),
             "shares_eval_yes": sum(1 for p in proto.values() if p["shares_eval_episodes"] == "yes"),
             "shares_eval_no": sum(1 for p in proto.values() if p["shares_eval_episodes"] == "no"),
             "sd_over": dict(collections.Counter(p["sd_over"] for p in proto.values())),
             "agents": dict(collections.Counter(p["agents"] for p in proto.values())),
             "frameworks": collections.Counter(p["framework"] for p in proto.values() if p["framework"]).most_common(8)}
    return proto, inherited, stats


def environment_protocols(proto: dict, comparisons: list) -> list:
    """Per environment family among the papers read: how many papers, how
    many state K and seeds, the modal values, the binomial resolution at the
    modal K x S near p = 0.5 (Newcombe), and the parser's failure rate on the
    testable comparisons of those papers."""
    rows = []
    t_by_paper = collections.defaultdict(list)
    for c in comparisons:
        if c.get("test"):
            t_by_paper[c["paper"]].append(not c["survives_raw"])
    for name, _ in ENV_GROUPS:
        pids = [pid for pid, p in proto.items() if any(_env_group(str(e)) == name for e in p["environments"])]
        if not pids:
            continue
        ks = [proto[pid]["eval_episodes"] for pid in pids if proto[pid]["eval_episodes"]]
        ss = [proto[pid]["seeds"] for pid in pids if proto[pid]["seeds"]]
        modal_k = collections.Counter(ks).most_common(1)[0][0] if ks else None
        modal_s = collections.Counter(ss).most_common(1)[0][0] if ss else None
        res = None
        if modal_k and modal_s:
            n = modal_k * modal_s
            l, u = wilson_interval(round(0.5 * n), n)
            res = round(100 * math.sqrt((0.5 - l) ** 2 + (u - 0.5) ** 2), 1)
        tested = [x for pid in pids for x in t_by_paper.get(pid, [])]
        rows.append({"environment": name, "papers": len(pids),
                     "pct_state_k": round(100 * len(ks) / len(pids), 1), "modal_k": modal_k,
                     "pct_state_seeds": round(100 * len(ss) / len(pids), 1), "modal_seeds": modal_s,
                     "resolution_points_at_modal": res,
                     "fixed_instances": sum(1 for pid in pids if proto[pid]["episodes_kind"] == "fixed_instances"),
                     "testable_comparisons": len(tested),
                     "testable_papers": len([pid for pid in pids if t_by_paper.get(pid)]),
                     "pct_fail": round(100 * sum(tested) / len(tested), 1) if tested else None})
    rows.sort(key=lambda r: -r["papers"])
    return rows


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


def per_paper_failure(comparisons: list) -> dict:
    """The failure rate with the paper as the unit: share of papers with a
    testable comparison that have at least one failing one, the median and
    quartiles of the per-paper failure share, and the ten largest papers'
    rates."""
    t = [c for c in comparisons if c.get("test")]
    by = collections.defaultdict(list)
    for c in t:
        by[c["paper"]].append(not c["survives_raw"])
    rates = sorted(100 * sum(v) / len(v) for v in by.values())
    n = len(rates)
    q = lambda f: rates[min(n - 1, int(f * n))] if n else None
    top = sorted(by.items(), key=lambda kv: -len(kv[1]))[:10]
    return {"papers": n,
            "pct_papers_any_fail": round(100 * sum(1 for v in by.values() if any(v)) / max(n, 1), 1),
            "pct_papers_all_fail": round(100 * sum(1 for v in by.values() if all(v)) / max(n, 1), 1),
            "median_paper_rate": round(q(0.5), 1), "q1_paper_rate": round(q(0.25), 1), "q3_paper_rate": round(q(0.75), 1),
            "mean_of_paper_rates": round(sum(rates) / max(n, 1), 1),
            "top10": [{"paper": k[:8], "n": len(v), "pct_fail": round(100 * sum(v) / len(v), 1)} for k, v in top],
            "top10_share": round(100 * sum(len(v) for _, v in top) / max(len(t), 1), 1)}


FRAMEWORK_DEFAULT_K = {
    # evaluation episodes per checkpoint in the framework's shipped configs
    "pymarl": (r"\bpymarl\b|\bepymarl\b", 32),
    "marllib": (r"\bmarllib\b", 20),
    "benchmarl": (r"\bbenchmarl\b", 200),
    "jaxmarl": (r"\bjaxmarl\b", 32),
}


def framework_defaults(records: list, comparisons: list, protocol: dict, corpus_dir: str = "data/corpus") -> dict:
    """Among papers with a rate comparison and no stated K, which name a
    framework whose shipped configuration fixes the evaluation episode
    count, and the resolution reading with that default imputed."""
    import fitz
    recs = {r["id"]: r for r in records}
    rate_papers = sorted({c["paper"] for c in comparisons if rate_like(c)})
    named = {}
    for pid in rate_papers:
        r = recs[pid]
        path = os.path.join(corpus_dir, f"{r['venue']}{r['year']}_{pid}.pdf")
        if not os.path.exists(path):
            continue
        text = " ".join(pg.get_text() for pg in fitz.open(path))
        for name, (pat, k) in FRAMEWORK_DEFAULT_K.items():
            if re.search(pat, text, re.I):
                named[pid] = (name, k)
                break
    imputed = {pid: dict(protocol.get(pid, {})) for pid in rate_papers}
    n_imputed = 0
    for pid, (name, k) in named.items():
        if not imputed[pid].get("eval_episodes"):
            imputed[pid]["eval_episodes"] = k
            n_imputed += 1
    res = protocol_resolution(comparisons, imputed)
    return {"rate_papers": len(rate_papers), "naming_a_framework": len(named),
            "stated_k": sum(1 for pid in rate_papers if protocol.get(pid, {}).get("eval_episodes")),
            "imputed_k": n_imputed,
            "with_imputed": {k: v for k, v in res.items() if k != "rows"}}


def caption_assertion(comparisons: list) -> dict:
    """Testable comparisons split by whether the table's caption asserts
    superiority for the bold cell (outperform, best, significant, superior,
    consistently, state of the art) or only describes what is shown."""
    rx = re.compile(r"outperform|significant|superior|consistently|state[- ]of[- ]the[- ]art|surpass|"
                    r"improves? (?:over|upon|on)|achieves? the (?:best|highest)", re.I)
    t = [c for c in comparisons if c.get("test")]
    asserting = [c for c in t if rx.search(c.get("caption", "") or "")]
    plain = [c for c in t if not rx.search(c.get("caption", "") or "")]
    return {"asserting": _rates(asserting), "describing": _rates(plain)}


def uncertainty_anywhere(records: list) -> dict:
    """Papers with any uncertainty statement the extraction can see: a +/-
    or parenthesised cell in a table, or a figure caption naming a deviation,
    interval or shaded band."""
    n = len(records)
    pm = sum(1 for r in records if r.get("reports_explicit_error_bar"))
    anyd = sum(1 for r in records if r.get("reports_any_dispersion"))
    fig = sum(1 for r in records if r.get("n_figure_captions_with_uncertainty", 0) > 0)
    anyw = sum(1 for r in records if r.get("reports_any_dispersion") or r.get("n_figure_captions_with_uncertainty", 0) > 0)
    return {"papers": n, "pct_pm_cell": round(100 * pm / n, 1), "pct_any_cell": round(100 * anyd / n, 1),
            "pct_figure_caption": round(100 * fig / n, 1), "pct_anywhere": round(100 * anyw / n, 1)}


def census_cross_reader(a_items="audits/aamas_pages/items.json", a_labels="audits/aamas_pages/labels.json",
                        c_items="audits/aamas_census/items.json", c_labels="audits/aamas_census/labels.json") -> dict:
    """The two page readers on the pages both read: groups listed, bar-less
    share, and the share of the first reader's groups the second lists (by
    the winner's value, one to one)."""
    if not all(os.path.exists(x) for x in (a_items, a_labels, c_items, c_labels)):
        return {}
    from pages_score import _bar_num
    ai = {it["id"]: it for it in json.load(open(a_items, encoding="utf-8"))}
    A = {(ai[p["id"]]["paper"], ai[p["id"]]["page"]): p for p in json.load(open(a_labels, encoding="utf-8"))}
    ci = {it["id"]: it for it in json.load(open(c_items, encoding="utf-8"))}
    C = {(ci[p["id"]]["paper"], ci[p["id"]]["page"]): p for p in json.load(open(c_labels, encoding="utf-8"))}
    common = [k for k in A if k in C]

    def groups(p):
        out = []
        for t in p["tables"]:
            if not str(t.get("results_table", "")).lower().startswith("y"):
                continue
            for g in t["groups"]:
                wb = _bar_num(g.get("winner_disp")) is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = _bar_num(g.get("runner_disp")) is not None or str(g.get("runner_disp", "")).startswith("[")
                out.append({"wm": str(g.get("winner_mean", "")).strip(), "neither": not wb and not rb})
        return out
    ga = gc = na = nc = matched = 0
    m_agree = m_na = 0          # bar-less verdict on the matched groups
    un_a = un_na = 0            # first-reader groups the second does not list, and their bar-less count
    empty_second = empty_first = 0
    for k in common:
        a, c = groups(A[k]), groups(C[k])
        ga += len(a); gc += len(c); na += sum(g["neither"] for g in a); nc += sum(g["neither"] for g in c)
        if a and not c:
            empty_second += 1
        if c and not a:
            empty_first += 1
        cw = [(g["wm"], g["neither"]) for g in c]
        for g in a:
            hit = next((x for x in cw if x[0] == g["wm"]), None)
            if hit is not None:
                matched += 1
                m_agree += (hit[1] == g["neither"])
                cw.remove(hit)
            else:
                un_a += 1
                un_na += g["neither"]
    return {"pages": len(common), "first_groups": ga, "second_groups": gc,
            "first_pct_neither": round(100 * na / max(ga, 1), 1), "second_pct_neither": round(100 * nc / max(gc, 1), 1),
            "first_matched_by_second": matched, "pct_first_matched": round(100 * matched / max(ga, 1), 1),
            "matched_neither_agree": m_agree,
            "pct_matched_neither_agree": round(100 * m_agree / max(matched, 1), 1),
            "first_unmatched": un_a, "pct_first_unmatched_neither": round(100 * un_na / max(un_a, 1), 1),
            "pages_second_lists_nothing": empty_second, "pages_first_lists_nothing": empty_first}


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
    # Section 6 works on the comparisons with exact copies removed (a filter
    # on the parser's output; the parser itself is untouched)
    _, cs_dd = exact_copies(cs)
    res = protocol_resolution(cs_dd, protocol)
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
        "protocol_span": protocol_span(cs_dd, protocol),
        "section6_dedup": {"comparisons": len(cs_dd), "exact_copies_removed": len(cs) - len(cs_dd)},
        "protocol_reader2": (lambda p2: {
            "stats": p2[2],
            "resolution_typed": {k: v for k, v in protocol_resolution(cs_dd, p2[0], seed_mode="typed").items() if k != "rows"},
            "resolution_typed_inherited": {k: v for k, v in protocol_resolution(cs_dd, p2[1], seed_mode="typed").items() if k != "rows"},
            "resolution_or_one": {k: v for k, v in protocol_resolution(cs_dd, p2[0]).items() if k != "rows"},
            "span": protocol_span(cs_dd, p2[0]),
            "span_inherited": protocol_span(cs_dd, p2[1]),
            "by_environment": environment_protocols(p2[0], cs),
            "rate_papers": len({c["paper"] for c in cs_dd if rate_like(c)}),
            "rate_papers_read": len({c["paper"] for c in cs_dd if rate_like(c) and c["paper"] in p2[0]}),
            "rate_papers_with_k": len({c["paper"] for c in cs_dd if rate_like(c) and p2[0].get(c["paper"], {}).get("eval_episodes")}),
            "rate_papers_with_k_inherited": len({c["paper"] for c in cs_dd if rate_like(c) and p2[1].get(c["paper"], {}).get("eval_episodes")}),
            "rate_papers_with_seeds": len({c["paper"] for c in cs_dd if rate_like(c) and p2[0].get(c["paper"], {}).get("seeds")}),
            "rate_papers_fixed": len({c["paper"] for c in cs_dd if rate_like(c) and p2[0].get(c["paper"], {}).get("episodes_kind") == "fixed_instances"}),
            "rate_papers_smac": len({c["paper"] for c in cs_dd if rate_like(c) and any(str(e).startswith(SMAC_FAMILY) for e in p2[0].get(c["paper"], {}).get("environments", []))}),
            "rate_papers_regex_k": len({c["paper"] for c in cs_dd if rate_like(c) and protocol.get(c["paper"], {}).get("eval_episodes")}),
            "agreement_with_first_reading": (lambda rd1: {
                "both": sum(1 for pid in p2[0] if pid in rd1 and rd1[pid]["eval_episodes"] and p2[0][pid]["eval_episodes"]),
                "agree_k": sum(1 for pid in p2[0] if pid in rd1 and rd1[pid]["eval_episodes"] and p2[0][pid]["eval_episodes"] == rd1[pid]["eval_episodes"]),
                "first_k_second_none": sum(1 for pid in p2[0] if pid in rd1 and rd1[pid]["eval_episodes"] and not p2[0][pid]["eval_episodes"]),
                "second_k_first_none": sum(1 for pid in p2[0] if pid in rd1 and not rd1[pid]["eval_episodes"] and p2[0][pid]["eval_episodes"]),
                "shared_papers": sum(1 for pid in p2[0] if pid in rd1),
                "both_seeds": sum(1 for pid in p2[0] if pid in rd1 and rd1[pid]["seeds"] and p2[0][pid]["seeds"]),
                "agree_seeds": sum(1 for pid in p2[0] if pid in rd1 and rd1[pid]["seeds"] and p2[0][pid]["seeds"] == rd1[pid]["seeds"]),
            })(reader_protocol()[0]),
            "regex_agreement": (lambda rx: {
                "both_k": sum(1 for pid in p2[0] if rx.get(pid, {}).get("eval_episodes") and p2[0][pid]["eval_episodes"]),
                "agree_k": sum(1 for pid in p2[0] if rx.get(pid, {}).get("eval_episodes") and p2[0][pid]["eval_episodes"] == rx[pid]["eval_episodes"]),
                "regex_k_only": sum(1 for pid in p2[0] if rx.get(pid, {}).get("eval_episodes") and not p2[0][pid]["eval_episodes"]),
                "model_k_only": sum(1 for pid in p2[0] if not rx.get(pid, {}).get("eval_episodes") and p2[0][pid]["eval_episodes"]),
                "both_seeds": sum(1 for pid in p2[0] if rx.get(pid, {}).get("seeds") and p2[0][pid]["seeds"]),
                "agree_seeds": sum(1 for pid in p2[0] if rx.get(pid, {}).get("seeds") and p2[0][pid]["seeds"] == rx[pid]["seeds"]),
            })(protocol),
        } if p2[0] else {})(reader_protocol2()),
        "per_paper_failure": per_paper_failure(cs),
        "per_paper_failure_dedup": per_paper_failure(exact_copies(cs)[1]),
        "ddof_reading": ddof_reading(cs),
        "resolution_lookup": resolution_lookup(),
        "census_cross_reader": census_cross_reader(),
        "runs_band_papers": {band: len({c["paper"] for c in cs if c.get("test") and c.get("n_runs") and
                                        ((band == "le3" and c["n_runs"] <= 3) or (band == "4to5" and 4 <= c["n_runs"] <= 5) or (band == "ge6" and c["n_runs"] >= 6))})
                             for band in ("le3", "4to5", "ge6")},
        "framework_defaults": framework_defaults(records, cs_dd, protocol),
        "caption_assertion": caption_assertion(cs),
        "uncertainty_anywhere": uncertainty_anywhere(records),
        "protocol_reader": (lambda pr_: {"stats": pr_[1],
                                         "resolution": {k: v for k, v in protocol_resolution(cs_dd, pr_[0]).items() if k != "rows"},
                                         "resolution_stated_seeds": {k: v for k, v in protocol_resolution(cs_dd, pr_[0], seed_mode="stated").items() if k != "rows"},
                                         "span": protocol_span(cs_dd, pr_[0])}
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
    rp_, _ = reader_protocol()
    if rp_:
        with open(f"{OUT}/protocol_resolution_rows_reader.json", "w", encoding="utf-8") as fh:
            json.dump(protocol_resolution(cs_dd, rp_)["rows"], fh, indent=1)
    p2_, p2i_, _ = reader_protocol2()
    if p2_:
        with open(f"{OUT}/protocol_resolution_rows_reader2.json", "w", encoding="utf-8") as fh:
            json.dump(protocol_resolution(cs_dd, p2_, seed_mode="typed")["rows"], fh, indent=1)
        with open(f"{OUT}/protocol_resolution_rows_reader2_inherited.json", "w", encoding="utf-8") as fh:
            json.dump(protocol_resolution(cs_dd, p2i_, seed_mode="typed")["rows"], fh, indent=1)
    print("wrote", f"{OUT}/extra.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
