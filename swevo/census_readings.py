"""Readings of the reader census beyond what study/pages_score.py reports.

Two censuses are scored with one set of functions: the pre-registered
reading (audits/swevo_census/labels.json) and the corrected reading, in
which the tables of the pages re-read under the Mean/Std-row instruction
(audits/swevo_census_rows, audits/swevo_census_rows2) replace the original
tables one table at a time, and only where the re-read files a separate
layout or lists at least as many groups of means as the original did (a
re-read that returns fewer groups is a truncation, not a repair).

For each census: the layout of the dispersion over the results tables, the
shares (bar-less, testable, failing) over all groups and over the groups
that are means over runs (not Best/Worst/Median/Std/Rank rows, not tables
of ranks or settings), by kind, the per-paper concentration, the heavy-tail
shape, the impossible mean-deviation pairs, the alternative conventions,
the zero-deviation groups, the bold-rule and journal-note strata, the
citation strata, and the effective number of clusters. Every interval is a
cluster bootstrap over papers from the one function below, with the papers
sorted before drawing.

Writes out/swevo/census_readings.json.
"""
import collections
import csv
import glob
import json
import os
import random
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, HERE)
from paperengine.stats import wilson_interval  # noqa: E402,F401
from pages_score import _bar_num, _se  # noqa: E402
from gold_set import _num  # noqa: E402
from analyze import p_value  # noqa: E402

KIT = "audits/swevo_census"
ROW_KITS = ["audits/swevo_census_rows", "audits/swevo_census_rows2", "audits/swevo_census_rows3"]
OUT = "out/swevo/census_readings.json"

# a group whose label names a summary row rather than a function or an
# optimizer: a Std, Rank or Time row is not a statistic over runs at all; a
# Best, Worst or Median row is a statistic over runs that owes no deviation
# a summary row is named by its label: the deviation, rank, time and test rows by a token anywhere in the
# label, the Wilcoxon h by the whole label or as h-value (a bare "h" would catch "$/h"), and min / max
# only as the whole label (a "Max error" row is a mean over runs of an objective)
STD_ROW = re.compile(r"(?:^|[ ,;:(/])(std|sd|s\.?d\.?|standard deviation|stdev|rank|ave\.? ?rank|mean rank|friedman|p[- ]?value|h[- ]?value)(?:$|[ ,;:)/])|^h$|^(?:cpu |run(?:ning)? |computational |computation |execution |average |mean )?time(?: ?\(s\))?$", re.I)
BEST_ROW = re.compile(r"(?:^|[ ,;:(/])(best|worst|wor\.|median)(?:$|[ ,;:)/])|^(min|max)(imum)?$", re.I)
ROW_LABEL = re.compile("|".join([STD_ROW.pattern, BEST_ROW.pattern]), re.I)
# a table whose caption says it holds ranks, test verdicts or settings
NOT_MEANS_CAPTION = re.compile(r"friedman|rank|wilcoxon|p[- ]?value|sensitivity|parameter setting|settings|complexity|running time|computational time|standard deviations? of|std\.? of", re.I)


def _disp_str(x) -> str:
    """The reader's dispersion string with a trailing verdict marker (the
    paper's +, -, = or ~ glued to the value) and parentheses stripped; a
    bracketed interval keeps its opening bracket."""
    s = str(x if x is not None else "").strip()
    if s.startswith("["):
        return s
    s = re.sub(r"[\s+\-−=≈~*†‡]+$", "", s).strip()
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1].strip()
    # a thousands separator inside a printed number
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    return s


def _disp(x):
    return _bar_num(_disp_str(x))


MULTI_OBJECTIVE = re.compile(r"multi-?objective|many-?objective|pareto|hypervolume|\bIGD\b|NSGA|MOEA|MOPSO|bi-?objective", re.I)
MULTI_OBJECTIVE_ACRONYM = re.compile(r"\bMODE\b")  # the acronym only, never the word "mode"


def _mo_papers(paper_ids: set) -> set:
    """Papers whose title or abstract names a multi-objective study, from the OpenAlex index."""
    path = "out/swevo/index.json"
    if not os.path.exists(path):
        return set()
    out = set()
    for r in json.load(open(path, encoding="utf-8")):
        text = str(r.get("title", "")) + " " + str(r.get("abstract", ""))
        if r.get("id") in paper_ids and (MULTI_OBJECTIVE.search(text) or MULTI_OBJECTIVE_ACRONYM.search(text)):
            out.add(r["id"])
    return out


DROPPED = {"nonextremal": 0, "papers": set()}
COLS_KIT = "audits/swevo_census_cols"


def _wholerow_answers() -> dict:
    """The one-question re-read of the column-oriented tables: (page id, caption key) -> answer record."""
    out = {}
    for path in sorted(glob.glob(os.path.join(COLS_KIT, "labels_shard*.json"))):
        for pg in json.load(open(path, encoding="utf-8")):
            for t in pg.get("tables", []):
                out[(pg["id"], str(t.get("caption_start", ""))[:25].lower())] = t
    return out


WHOLEROW = _wholerow_answers()


def _regroup(labels: dict, items: dict, kinds: dict):
    """Every reader group with the fields the readings need, scored as
    pages_score scores it (extremal-only, Welch on the reader's values).
    Groups whose bold cell is not the better value in its direction, or ties
    its rival, are dropped and counted in DROPPED."""
    groups = []
    DROPPED["nonextremal"] = 0
    DROPPED["papers"] = set()
    for iid, pg in labels.items():
        paper = items[iid]["paper"]
        for ti, t in enumerate(pg.get("tables", [])):
            if not str(t.get("results_table", "")).lower().startswith("y"):
                continue
            kind = str(t.get("bar_kind", "")).lower()
            n = _num(t.get("n_runs"))
            form = str(t.get("bar_form", "")).lower().strip()
            cap = str(t.get("caption_start", ""))
            for g in t.get("groups", []):
                w, r = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                d = str(g.get("direction", "")).lower()
                if w is not None and r is not None and (w == r or (d.startswith("low") and w > r) or (d.startswith("high") and w < r)):
                    DROPPED["nonextremal"] += 1
                    DROPPED["papers"].add(paper)
                    continue
                wd, rd = _disp(g.get("winner_disp")), _disp(g.get("runner_disp"))
                wb = wd is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = rd is not None or str(g.get("runner_disp", "")).startswith("[")
                testable = wb and rb and (n is not None or kind in ("se", "ci"))
                fail = None
                zero_both = False
                pval = None
                if testable and None not in (w, r):
                    sw, sr = _se(_disp_str(g.get("winner_disp")), kind, n), _se(_disp_str(g.get("runner_disp")), kind, n)
                    if None not in (sw, sr):
                        res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                        fail = (res["p"] >= 0.05) if res else None
                        pval = res["p"] if res else None
                        zero_both = res is None and sw == 0 and sr == 0
                label = str(g.get("label", "")).strip()
                groups.append({"page": iid, "paper": paper, "kind": kinds.get(paper, "unlabelled"), "form": form,
                               "label": label, "w": w, "r": r, "wd": wd, "rd": rd, "wb": wb, "rb": rb, "n": n,
                               "n_source": str(t.get("n_source", "")).lower().strip(),
                               "testable": testable, "fail": fail, "zero_both": zero_both, "p": pval,
                               "std_row": bool(STD_ROW.search(label)), "best_row": bool(BEST_ROW.search(label)),
                               "row_label": bool(ROW_LABEL.search(label)), "not_means_table": bool(NOT_MEANS_CAPTION.search(cap)),
                               "table": f"{iid}:{ti}", "kind_label": kind,
                               "orientation": str(t.get("orientation", "")).lower().strip(),
                               "whole_row": _wholerow_flag(iid, cap) if str(t.get("orientation", "")).lower().strip() == "column" else None})
    return groups


def _wholerow_flag(iid: str, cap: str):
    """y / n from the whole-row question, or None where the table was not asked or not answered."""
    t = WHOLEROW.get((iid, str(cap)[:25].lower()))
    if not t:
        return None
    row = str(t.get("all_bold_in_one_row", "")).lower().startswith("y")
    col = str(t.get("all_bold_in_one_column", "")).lower().startswith("y")
    cells = _num(t.get("bold_cells"))
    # one row of several bold cells (or one column): the whole-row convention;
    # both at once is a single bold cell, which is not that convention
    if (row and col) or (cells is not None and cells < 3):
        return "n"  # a single bold cell, or two, is not the whole-row convention
    return "y" if (row or col) else "n"


def _is_mean(g) -> bool:
    return not g["row_label"] and not g["not_means_table"]


def _welch_variant(g, *, one_sided=False, ddof=False, rho=0.0, unlabelled_as_se=False):
    if not (g["testable"] and g["fail"] is not None) or g["w"] is None or g["r"] is None:
        return None
    kind, n = g["kind_label"], g["n"]
    wd, rd = g["wd"], g["rd"]
    if wd is None or rd is None:
        return None
    if kind == "se":
        sw, sr = wd, rd
    elif kind == "ci":
        sw, sr = wd / 1.96, rd / 1.96
    elif unlabelled_as_se and kind not in ("sd", "std"):
        sw, sr = wd, rd
    else:
        if not n:
            return None
        f = (n / (n - 1)) ** 0.5 if (ddof and n > 1) else 1.0
        sw, sr = f * wd / n ** 0.5, f * rd / n ** 0.5
    res = p_value(abs(g["w"] - g["r"]), sw, sr, int(n) if n else None, rho=rho)
    if res is None:
        return None
    pv = res["p"] / 2 if one_sided else res["p"]
    return pv >= 0.05


def _impossible(g) -> bool:
    """A sample deviation over n non-negative runs cannot exceed sqrt(n)
    times the mean; a printed mean of exactly zero is rounding and a
    summary row is not a mean, so neither is flagged."""
    n = g["n"]
    if not n or g["row_label"]:
        return False
    for m, d in ((g["w"], g["wd"]), (g["r"], g["rd"])):
        if m is not None and d is not None and m > 0 and d > (n ** 0.5) * m * 1.0000001:
            return True
    return False


def _holm_fail(gs: list, family: str):
    tested = [g for g in gs if g["testable"] and g["fail"] is not None and g["w"] is not None and g["r"] is not None]
    fam = collections.defaultdict(list)
    for g in tested:
        kind, n = g["kind_label"], g["n"]
        wd, rd = g["wd"], g["rd"]
        if kind == "se":
            sw, sr = wd, rd
        elif kind == "ci":
            sw, sr = wd / 1.96, rd / 1.96
        elif n:
            sw, sr = wd / n ** 0.5, rd / n ** 0.5
        else:
            continue
        res = p_value(abs(g["w"] - g["r"]), sw, sr, int(n) if n else None)
        if res is None:
            continue
        fam[g[family] if family == "table" else g["paper"]].append(res["p"])
    fails = total = 0
    for ps in fam.values():
        m = len(ps)
        order = sorted(range(m), key=lambda i: ps[i])
        rejected = [False] * m
        for rank, i in enumerate(order):
            if ps[i] <= 0.05 / (m - rank):
                rejected[i] = True
            else:
                break
        fails += sum(1 for x in rejected if not x)
        total += m
    return round(100 * fails / total, 1) if total else None


def _boot_pairs(pairs: list, reps: int = 2000, seed: int = 0):
    """Cluster bootstrap over papers of a share; pairs are (paper, num, den).
    The papers are sorted before drawing so the interval is reproducible
    whatever the order the groups arrive in."""
    by = collections.defaultdict(lambda: [0, 0])
    for paper, k, n in pairs:
        by[paper][0] += k
        by[paper][1] += n
    keys = sorted(by)
    if not keys or sum(v[1] for v in by.values()) == 0:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        draw = [by[keys[rng.randrange(len(keys))]] for _ in keys]
        n, d = sum(x[0] for x in draw), sum(x[1] for x in draw)
        vals.append(100 * n / d if d else 0.0)
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def _boot_mean(vals: list, reps: int = 2000, seed: int = 0):
    """Percentile bootstrap of a mean over units that are already one per paper."""
    rng = random.Random(seed)
    vals = sorted(vals)
    out = []
    for _ in range(reps):
        draw = [vals[rng.randrange(len(vals))] for _ in vals]
        out.append(sum(draw) / len(draw))
    out.sort()
    return [round(out[int(0.025 * reps)], 1), round(out[int(0.975 * reps) - 1], 1)]


def _cluster_wald(cl: list):
    """Cluster-robust Wald interval for a pooled share: the clusters are the
    units, the variance is the cluster-level residual sum with the k/(k-1)
    correction, and the quantile is Student's t on k-1 degrees of freedom."""
    from scipy.stats import t as student_t
    k, N = len(cl), sum(n for n, _ in cl)
    if k < 2 or not N:
        return None
    p = sum(f for _, f in cl) / N
    v = sum((f - n * p) ** 2 for n, f in cl) / N ** 2 * k / (k - 1)
    q = student_t.ppf(0.975, k - 1)
    return [round(100 * max(p - q * v ** 0.5, 0.0), 1), round(100 * min(p + q * v ** 0.5, 1.0), 1)]


def _boot_coverage(by_paper: dict, sims: int = 1000, reps: int = 1000, seed: int = 1) -> dict:
    """How often the percentile cluster bootstrap covers the pooled rate when the
    observed papers (their group counts and failure shares) are taken as the
    population: each simulated corpus draws the same number of papers with
    replacement, draws each paper's failures as a binomial at its observed share,
    and asks whether the interval covers the population's pooled rate. Nominal 95."""
    pop = [(n, f / n) for n, f in by_paper.values() if n]
    if len(pop) < 10:
        return {"papers": len(pop), "coverage": None}
    theta = 100 * sum(n * p for n, p in pop) / sum(n for n, _ in pop)
    rng = random.Random(seed)
    hits = 0
    hits_wald = 0
    widths = []
    for _ in range(sims):
        draw = [pop[rng.randrange(len(pop))] for _ in pop]
        obs = [(n, sum(1 for _ in range(n) if rng.random() < p)) for n, p in draw]
        w = _cluster_wald(obs)
        hits_wald += bool(w and w[0] <= theta <= w[1])
        vals = []
        for _ in range(reps):
            b = [obs[rng.randrange(len(obs))] for _ in obs]
            d = sum(x[0] for x in b)
            vals.append(100 * sum(x[1] for x in b) / d if d else 0.0)
        vals.sort()
        lo, hi = vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]
        hits += lo <= theta <= hi
        widths.append(hi - lo)
    cov = hits / sims
    mc = 1.96 * (cov * (1 - cov) / sims) ** 0.5
    return {"papers": len(pop), "sims": sims, "coverage": round(100 * hits / sims, 1), "coverage_wald": round(100 * hits_wald / sims, 1),
            "coverage_mc_ci": [round(100 * (cov - mc), 1), round(100 * (cov + mc), 1)],
            "mean_width": round(sum(widths) / len(widths), 1), "theta": round(theta, 1),
            "wald_ci": _cluster_wald([(n, f) for n, f in by_paper.values() if n])}


def _icc_design(by_paper: dict) -> dict:
    """One-way ANOVA intra-class correlation of the failure indicator within
    papers, the design effect 1 + (n0 - 1) * ICC with n0 the ANOVA cluster
    size, and the effective number of tested groups N / DE."""
    cl = [(n, f) for n, f in by_paper.values() if n]
    k, N = len(cl), sum(n for n, _ in cl)
    if k < 2 or N <= k:
        return {"icc": None, "design_effect": None, "effective_groups": None, "n0": None}
    ybar = sum(f for _, f in cl) / N
    msb = sum(n * (f / n - ybar) ** 2 for n, f in cl) / (k - 1)
    msw = sum(f * (1 - f / n) ** 2 + (n - f) * (f / n) ** 2 for n, f in cl) / (N - k)
    n0 = (N - sum(n * n for n, _ in cl) / N) / (k - 1)
    icc = (msb - msw) / (msb + (n0 - 1) * msw) if (msb + (n0 - 1) * msw) > 0 else 0.0
    icc = max(icc, 0.0)
    # the pooled share weights papers by their group counts, so the design effect that
    # belongs to it uses Kish's n* = sum(n^2)/N, not the ANOVA n0; the empirical design
    # effect is the cluster-robust variance over the binomial one, which is what the
    # printed intervals already embody
    n_star = sum(n * n for n, _ in cl) / N
    de_kish = 1 + (n_star - 1) * icc
    v_cluster = sum((f - n * ybar) ** 2 for n, f in cl) / N ** 2 * k / (k - 1)
    v_binom = ybar * (1 - ybar) / N
    de_emp = v_cluster / v_binom if v_binom > 0 else None
    return {"icc": round(icc, 3), "n0": round(n0, 1), "n_star": round(n_star, 1),
            "design_effect_anova": round(1 + (n0 - 1) * icc, 2),
            "design_effect_kish": round(de_kish, 2), "effective_groups_kish": round(N / de_kish, 1),
            "design_effect": round(de_emp, 2) if de_emp else None, "effective_groups": round(N / de_emp, 1) if de_emp else None}


def _kish(gs: list) -> dict:
    sizes = collections.Counter(g["paper"] for g in gs)
    tot = sum(sizes.values())
    if not tot:
        return {"papers": 0, "effective": None, "largest": 0}
    return {"papers": len(sizes), "effective": round(tot ** 2 / sum(v * v for v in sizes.values()), 1),
            "largest": max(sizes.values())}


def _shares(gs: list) -> dict:
    n = len(gs)
    tested = [g for g in gs if g["testable"] and g["fail"] is not None]
    return {"groups": n, "papers": len({g["paper"] for g in gs}), "effective_papers": _kish(gs)["effective"],
            "pct_neither": round(100 * sum(1 for g in gs if not g["wb"] and not g["rb"]) / n, 1) if n else None,
            "ci_neither": _boot_pairs([(g["paper"], int(not g["wb"] and not g["rb"]), 1) for g in gs]) if n else None,
            "pct_one_side": round(100 * sum(1 for g in gs if g["wb"] != g["rb"]) / n, 1) if n else None,
            "pct_testable": round(100 * sum(1 for g in gs if g["testable"]) / n, 1) if n else None,
            "ci_testable": _boot_pairs([(g["paper"], int(g["testable"]), 1) for g in gs]) if n else None,
            "testable_n": sum(1 for g in gs if g["testable"]),
            "tested": len(tested), "tested_papers": len({g["paper"] for g in tested}),
            "tested_effective_papers": _kish(tested)["effective"],
            "pct_fail": round(100 * sum(1 for g in tested if g["fail"]) / len(tested), 1) if tested else None,
            "ci_fail": _boot_pairs([(g["paper"], int(bool(g["fail"])), 1) for g in tested]) if tested else None,
            "zero_both": sum(1 for g in gs if g["zero_both"]),
            "unreadable": sum(1 for g in gs if g["testable"] and g["fail"] is None and not g["zero_both"]),
            **_largest(tested)}


def _largest(tested: list) -> dict:
    """The largest paper's share of a stratum's tested groups, its failure rate, and the rate without it."""
    by = collections.Counter(g["paper"] for g in tested)
    if not by:
        return {"largest_tested": 0, "largest_fail": None, "without_largest_tested": 0, "without_largest_fail": None}
    big = max(by, key=by.get)
    rest = [g for g in tested if g["paper"] != big]
    return {"largest_tested": by[big], "largest_fail": round(100 * sum(1 for g in tested if g["paper"] == big and g["fail"]) / by[big], 1),
            "without_largest_tested": len(rest), "without_largest_fail": round(100 * sum(1 for g in rest if g["fail"]) / len(rest), 1) if rest else None}


def _by_kind(gs: list) -> dict:
    out = {lab: _shares([g for g in gs if g["kind"] == lab]) for lab in ("new_optimizer", "application")}
    out["all"] = _shares(gs)
    return out


def merged_labels(labels: dict, kits=ROW_KITS, wholesale: bool = False) -> tuple:
    """The corrected census: per table, the re-read table replaces the
    original only where it files a separate layout or lists at least as
    many groups of means; the record of gains and losses comes with it.
    With wholesale=True every re-read table replaces its original (both
    directions), the reading that shows the size of the one-way rule."""
    reread = {}
    for kit in kits:
        for path in sorted(glob.glob(os.path.join(kit, "labels_shard*.json"))):
            for pg in json.load(open(path, encoding="utf-8")):
                if not str(pg.get("note", "")).startswith("failed"):
                    reread[pg["id"]] = pg
    merged = {iid: json.loads(json.dumps(pg)) for iid, pg in labels.items()}
    log = {"pages_reread": len(reread), "tables_reread": 0, "tables_replaced": 0, "tables_kept": 0, "tables_truncated": 0,
           "pages_with_a_kept_table": 0, "kept_barred_lost": 0, "kept_means_lost": 0, "kept_groups_old": 0, "kept_groups_new": 0,
           "pages_truncated": sum(1 for pg in reread.values() if pg.get("figure_band_on_page") == ""),
           "corrections_accepted": 0, "corrections_groups_old": 0, "corrections_groups_new": 0}

    def n_means(t):
        return sum(1 for g in t.get("groups", []) if not ROW_LABEL.search(str(g.get("label", "")).strip()))

    def n_barred(t):
        return sum(1 for g in t.get("groups", []) if _disp(g.get("winner_disp")) is not None and _disp(g.get("runner_disp")) is not None)

    def key(t):
        return str(t.get("caption_start", ""))[:25].lower()

    for iid, pg in reread.items():
        if iid not in merged:
            merged[iid] = pg
            continue
        old_tabs = [t for t in merged[iid].get("tables", []) if str(t.get("results_table", "")).lower().startswith("y")]
        new_tabs = [t for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y")]
        used = set()
        out_tabs = []
        kept_any = False
        for k, new in enumerate(new_tabs):
            log["tables_reread"] += 1
            old_i = next((i for i, t in enumerate(old_tabs) if i not in used and key(t) == key(new)), None)
            if old_i is None and k < len(old_tabs) and k not in used:
                old_i = k
            if old_i is None:
                out_tabs.append(new)
                log["tables_replaced"] += 1
                continue
            used.add(old_i)
            old = old_tabs[old_i]
            # a re-read whose answer was cut at the output budget leaves the page-level
            # fields empty after the JSON repair; such a table is a truncation and keeps
            # its original. A complete re-read that lists fewer groups is the reader's
            # correction under the instruction (a whole bold row, a table of deviations,
            # two bold cells per row) and is accepted.
            truncated = pg.get("figure_band_on_page") == ""
            fewer = n_barred(new) < n_barred(old) or n_means(new) < n_means(old)
            enough = not (truncated and fewer)
            if enough and fewer:
                log["corrections_accepted"] += 1
                log["corrections_groups_old"] += len(old.get("groups", []))
                log["corrections_groups_new"] += len(new.get("groups", []))
            if not enough:
                # what the refused re-read would have lost
                log["kept_barred_lost"] += max(n_barred(old) - n_barred(new), 0)
                log["kept_means_lost"] += max(n_means(old) - n_means(new), 0)
                log["kept_groups_old"] += len(old.get("groups", []))
                log["kept_groups_new"] += len(new.get("groups", []))
            if enough or wholesale:
                out_tabs.append(new)
                log["tables_replaced"] += 1
            else:
                out_tabs.append(old)
                log["tables_kept"] += 1
                log["tables_truncated"] += 1
                kept_any = True
        for i, t in enumerate(old_tabs):
            if i not in used:
                out_tabs.append(t)
        non_results = [t for t in merged[iid].get("tables", []) if not str(t.get("results_table", "")).lower().startswith("y")]
        merged[iid]["tables"] = out_tabs + non_results
        log["pages_with_a_kept_table"] += kept_any
    return merged, reread, log


def corrected_labels(items: dict | None = None) -> dict:
    """The corrected census labels, for the other scripts."""
    labels = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    merged, _, _ = merged_labels(labels)
    return merged


def main() -> int:
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    kinds = {}
    if os.path.exists("out/swevo/kinds_merged.csv"):
        for r in csv.DictReader(open("out/swevo/kinds_merged.csv", encoding="utf-8", newline="")):
            kinds[r["id"]] = r["label"]
    kinds2 = {}
    if os.path.exists("out/swevo/kinds2_merged.csv"):
        for r in csv.DictReader(open("out/swevo/kinds2_merged.csv", encoding="utf-8", newline="")):
            if r["label"] != "parse_error":
                kinds2[r["id"]] = r["label"]
    scan = json.load(open("out/swevo/text_scan.json", encoding="utf-8")) if os.path.exists("out/swevo/text_scan.json") else {}
    tr = {}
    paths = sorted(glob.glob("out/swevo/test_reader_part*.json")) + sorted(glob.glob("out/swevo/test_reader_v2_part*.json"))
    for path in paths:
        tr.update(json.load(open(path, encoding="utf-8")))
    from make_all_swevo import bold_rule_of, _method_citers  # noqa: E402
    citers = _method_citers(scan) if scan else set()

    def layout_of(labs: dict) -> dict:
        forms = collections.Counter()
        groups_by_form, barred_by_form = collections.Counter(), collections.Counter()
        n_runs_vals, n_src, bar_kind = collections.Counter(), collections.Counter(), collections.Counter()
        for iid, pg in labs.items():
            for t in pg.get("tables", []):
                if not str(t.get("results_table", "")).lower().startswith("y"):
                    continue
                f = str(t.get("bar_form", "")).lower().strip() or "unstated"
                forms[f] += 1
                bar_kind[str(t.get("bar_kind", "")).lower().strip() or "unstated"] += 1
                n = str(t.get("n_runs", "")).strip().lower()
                if n and n != "none":
                    try:
                        n_runs_vals[int(float(n))] += 1
                    except ValueError:
                        n_runs_vals["unreadable"] += 1
                    n_src[str(t.get("n_source", "")).lower().strip() or "unstated"] += 1
                else:
                    n_src["none"] += 1
                if t.get("groups"):
                    groups_by_form[f] += len(t["groups"])
                    barred_by_form[f] += sum(1 for g in t["groups"] if _disp(g.get("winner_disp")) is not None and _disp(g.get("runner_disp")) is not None)
        n_results = sum(forms.values())
        return {"results_tables": n_results, "bar_form": dict(forms.most_common()),
                "pct_bar_form": {k: round(100 * v / max(n_results, 1), 1) for k, v in forms.items()},
                "bar_kind": dict(bar_kind.most_common()),
                "n_runs": [[k, v] for k, v in n_runs_vals.most_common(10)], "n_source": dict(n_src.most_common()),
                "groups_by_form": dict(groups_by_form), "groups_with_both_bars_by_form": dict(barred_by_form),
                "pct_groups_in_separate_layout": round(100 * sum(v for k, v in groups_by_form.items() if k.startswith("separate")) / max(sum(groups_by_form.values()), 1), 1),
                "pct_barred_groups_in_separate_layout": round(100 * sum(v for k, v in barred_by_form.items() if k.startswith("separate")) / max(sum(barred_by_form.values()), 1), 1),
                "tables_at_group_cap": sum(1 for pg in labs.values() for t in pg.get("tables", []) if len(t.get("groups", [])) >= 40),
                "pct_tables_with_run_count": round(100 * sum(v for k, v in n_src.items() if k not in ("none", "unstated")) / max(n_results, 1), 1),
                "pct_tables_at_thirty": round(100 * n_runs_vals.get(30, 0) / max(n_results, 1), 1),
                "pct_tables_any_bar": round(100 * sum(v for k, v in forms.items() if k not in ("none", "unstated")) / max(n_results, 1), 1)}

    def readings_of(gs: list, name: str) -> dict:
        tested = [g for g in gs if g["testable"] and g["fail"] is not None]
        means = [g for g in gs if _is_mean(g)]
        by_paper = collections.defaultdict(lambda: [0, 0])
        for g in tested:
            by_paper[g["paper"]][0] += 1
            by_paper[g["paper"]][1] += bool(g["fail"])
        sizes = sorted(by_paper.values(), key=lambda x: -x[0])
        tot = sum(x[0] for x in sizes)
        rates = [100 * f / n for n, f in by_paper.values()]
        largest = max(by_paper, key=lambda k: by_paper[k][0]) if by_paper else None
        top4 = {k for k, _ in sorted(by_paper.items(), key=lambda kv: -kv[1][0])[:4]}
        top3 = [k for k, _ in sorted(by_paper.items(), key=lambda kv: -kv[1][0])[:3]]
        mo = _mo_papers({g["paper"] for g in gs})
        per_paper = {"papers": len(by_paper), "tested": tot, "effective_papers": _kish(tested)["effective"],
                     # each paper weighted equally: the mean of the per-paper failure shares, with a percentile bootstrap over papers as units
                     "macro_rate": round(statistics.mean(rates), 1) if rates else None,
                     "macro_rate_ci": _boot_mean(rates) if len(rates) >= 10 else None,
                     "boot_coverage": _boot_coverage(by_paper),
                     "icc": _icc_design(by_paper),
                     "top_four_share": round(100 * sum(x[0] for x in sizes[:4]) / tot, 1) if tot else None,
                     "top_ten_share": round(100 * sum(x[0] for x in sizes[:10]) / tot, 1) if tot else None,
                     "median_rate": round(statistics.median(rates), 1) if rates else None,
                     "q1_rate": round(statistics.quantiles(rates, n=4)[0], 1) if len(rates) >= 4 else None,
                     "q3_rate": round(statistics.quantiles(rates, n=4)[2], 1) if len(rates) >= 4 else None,
                     "papers_any_fail": sum(1 for n, f in by_paper.values() if f),
                     "largest_paper_tested": by_paper[largest][0] if largest else 0,
                     "largest_paper_fail": round(100 * by_paper[largest][1] / by_paper[largest][0], 1) if largest else None,
                     "without_largest": _shares([g for g in gs if g["paper"] != largest]),
                     "without_top_four": _shares([g for g in gs if g["paper"] not in top4]),
                     "top_three_share": round(100 * sum(x[0] for x in sizes[:3]) / tot, 1) if tot else None,
                     "top_three_ids": top3, "top_three_multi_objective": sum(1 for k in top3 if k in mo),
                     "top_three_share_means": round(100 * sum(1 for g in tested if g["paper"] in top3 and _is_mean(g)) / max(sum(1 for g in tested if _is_mean(g)), 1), 1),
                     "top_three_only": _shares([g for g in gs if g["paper"] in top3]),
                     "without_top_three": _shares([g for g in gs if g["paper"] not in top3])}
        # multi-objective studies (title or abstract) against the rest; a post-hoc split
        objective = {"multi_objective": _shares([g for g in gs if g["paper"] in mo]),
                     "single_objective": _shares([g for g in gs if g["paper"] not in mo]),
                     "multi_objective_by_kind": _by_kind([g for g in gs if g["paper"] in mo]),
                     "single_objective_by_kind": _by_kind([g for g in gs if g["paper"] not in mo]),
                     "multi_objective_papers_tested": len({g["paper"] for g in tested if g["paper"] in mo})}
        # tables the reader filed as column-oriented, where a whole bold row gives one bold cell per column
        col = [g for g in gs if g["orientation"] == "column"]
        orientation = {"column_oriented": _shares(col), "column_oriented_by_kind": _by_kind(col),
                       "column_oriented_means": _shares([g for g in col if _is_mean(g)]),
                       "without_column_oriented": _shares([g for g in gs if g["orientation"] != "column"]),
                       "without_column_oriented_by_kind": _by_kind([g for g in gs if g["orientation"] != "column"]),
                       "without_column_oriented_means": _shares([g for g in gs if g["orientation"] != "column" and _is_mean(g)]),
                       "without_column_oriented_means_by_kind": _by_kind([g for g in gs if g["orientation"] != "column" and _is_mean(g)]),
                       "whole_row_tables": len({g["table"] for g in gs if g["whole_row"] == "y"}),
                       "whole_row_tables_no": len({g["table"] for g in gs if g["whole_row"] == "n"}),
                       "whole_row_tables_unanswered": len({g["table"] for g in col if g["whole_row"] is None}),
                       "whole_row": _shares([g for g in gs if g["whole_row"] == "y"]),
                       "whole_row_by_kind": _by_kind([g for g in gs if g["whole_row"] == "y"]),
                       "without_whole_row": _shares([g for g in gs if g["whole_row"] != "y"]),
                       "without_whole_row_by_kind": _by_kind([g for g in gs if g["whole_row"] != "y"]),
                       "without_whole_row_means": _shares([g for g in gs if g["whole_row"] != "y" and _is_mean(g)]),
                       "without_whole_row_means_by_kind": _by_kind([g for g in gs if g["whole_row"] != "y" and _is_mean(g)]),
                       "column_oriented_tables": len({g["table"] for g in col}),
                       "column_oriented_tables_tested": len({g["table"] for g in col if g["testable"] and g["fail"] is not None})}

        def heavy(g):
            return (g["wd"] is not None and g["w"] is not None and g["wd"] >= abs(g["w"])) or (g["rd"] is not None and g["r"] is not None and g["rd"] >= abs(g["r"]))

        def tiny(g):
            return (g["w"] is not None and abs(g["w"]) < 1e-3) or (g["r"] is not None and abs(g["r"]) < 1e-3)

        def zero_sd(g):
            return (g["wd"] is not None and g["wd"] == 0) or (g["rd"] is not None and g["rd"] == 0)

        def heavy_w(g):
            return g["wd"] is not None and g["w"] is not None and g["wd"] >= abs(g["w"])

        def heavy_r(g):
            return g["rd"] is not None and g["r"] is not None and g["rd"] >= abs(g["r"])

        def ceiling_binds(g):
            # for non-negative quantities with s >= m on both arms, |t| <= sqrt(n) |m2 - m1| / sqrt(m1^2 + m2^2)
            if not (heavy_w(g) and heavy_r(g)) or not g["n"] or g["n"] < 2 or (g["w"] == 0 and g["r"] == 0):
                return False
            from scipy.stats import t as student_t
            den = (g["w"] ** 2 + g["r"] ** 2) ** 0.5  # underflows to zero for means near 1e-160
            if den == 0:
                return False
            tmax = (g["n"] ** 0.5) * abs(g["r"] - g["w"]) / den
            return tmax < student_t.ppf(0.975, g["n"] - 1)
        cb = [g for g in tested if ceiling_binds(g)]
        shape = {"tested": len(tested),
                 "sd_ge_mean_bold_only": _shares([g for g in gs if heavy_w(g) and not heavy_r(g)]),
                 "sd_ge_mean_rival_only": _shares([g for g in gs if heavy_r(g) and not heavy_w(g)]),
                 "sd_ge_mean_both": _shares([g for g in gs if heavy_w(g) and heavy_r(g)]),
                 "sd_lt_mean": _shares([g for g in gs if not heavy(g)]),
                 "bold_zero_pm_zero": sum(1 for g in tested if g["w"] == 0 and g["wd"] == 0),
                 "ceiling_binds": len(cb), "ceiling_binds_fail": sum(1 for g in cb if g["fail"]),
                 "ceiling_binds_pct_tested": round(100 * len(cb) / len(tested), 1) if tested else None,
                 "zero_both_as_pass_pct_fail": round(100 * sum(1 for g in tested if g["fail"]) / (len(tested) + sum(1 for g in gs if g["zero_both"])), 1) if tested else None,
                 "zero_both_as_pass_tested": len(tested) + sum(1 for g in gs if g["zero_both"]),
                 "sd_ge_mean": _shares([g for g in gs if heavy(g)]), "mean_tiny": _shares([g for g in gs if tiny(g)]),
                 "either": _shares([g for g in gs if heavy(g) or tiny(g)]), "neither": _shares([g for g in gs if not heavy(g) and not tiny(g)]),
                 "zero_sd": _shares([g for g in gs if zero_sd(g)]), "without_zero_sd": _shares([g for g in gs if not zero_sd(g)]),
                 "pct_tested_sd_ge_mean": round(100 * sum(1 for g in tested if heavy(g)) / len(tested), 1) if tested else None,
                 "pct_tested_zero_sd": round(100 * sum(1 for g in tested if zero_sd(g)) / len(tested), 1) if tested else None,
                 "zero_both_groups": sum(1 for g in gs if g["zero_both"]), "zero_both_papers": len({g["paper"] for g in gs if g["zero_both"]}),
                 "unreadable_groups": sum(1 for g in gs if g["testable"] and g["fail"] is None and not g["zero_both"])}

        def vrate(**kw):
            v = [_welch_variant(g, **kw) for g in gs]
            v = [x for x in v if x is not None]
            return round(100 * sum(v) / len(v), 1) if v else None
        imp = [g for g in gs if _impossible(g)]
        cap_page = [g for g in tested if g["n_source"] in ("caption", "page")]
        alternatives = {"as_reported": _shares(gs)["pct_fail"], "holm_table": _holm_fail(gs, "table"), "holm_paper": _holm_fail(gs, "paper"),
                        "one_sided": vrate(one_sided=True), "population_sd": vrate(ddof=True),
                        "rho_half": vrate(rho=0.5), "rho_nine_tenths": vrate(rho=0.9),
                        "unlabelled_as_se": vrate(unlabelled_as_se=True),
                        "unlabelled_tested": sum(1 for g in tested if g["kind_label"] not in ("sd", "std", "se", "ci")),
                        "impossible_pairs": len(imp), "impossible_pairs_tested": sum(1 for g in imp if g["testable"] and g["fail"] is not None),
                        "impossible_pairs_fail": round(100 * sum(1 for g in imp if g["fail"]) / max(sum(1 for g in imp if g["fail"] is not None), 1), 1),
                        "impossible_pairs_papers": len({g["paper"] for g in imp}),
                        "impossible_pairs_separate": sum(1 for g in imp if g["form"].startswith("separate")),
                        "without_impossible": _shares([g for g in gs if not _impossible(g)]),
                        "count_from_caption_or_page": _shares([g for g in gs if g["n_source"] in ("caption", "page")]),
                        "count_from_caption_or_page_tested": len(cap_page),
                        "count_from_paper_sentences": sum(1 for g in tested if g["n_source"] == "paper")}
        rows = {"std_row_groups": sum(1 for g in gs if g["std_row"]), "best_row_groups": sum(1 for g in gs if g["best_row"] and not g["std_row"]),
                "not_means_table_groups": sum(1 for g in gs if g["not_means_table"] and not g["row_label"]),
                "row_label_groups": sum(1 for g in gs if g["row_label"]),
                "row_label_pct": round(100 * sum(1 for g in gs if g["row_label"]) / max(len(gs), 1), 1),
                "row_label_only": _shares([g for g in gs if g["row_label"]]),
                "without_row_label": _shares([g for g in gs if not g["row_label"]]),
                "means_only": _shares(means), "means_only_by_kind": _by_kind(means)}
        bold = {lab: _shares([g for g in gs if (bold_rule_of(tr[g["paper"]]) if g["paper"] in tr and "parse_error" not in tr[g["paper"]] else "not read") == lab])
                for lab in ("best", "statistically best", "not stated", "not read")}
        note = {"with_note": _shares([g for g in gs if scan.get(g["paper"], {}).get("bold_note")]),
                "without_note": _shares([g for g in gs if not scan.get(g["paper"], {}).get("bold_note")]),
                "papers_with_note": len({g["paper"] for g in gs if scan.get(g["paper"], {}).get("bold_note")})}
        citing = {"citing": _shares([g for g in gs if g["paper"] in citers]), "not_citing": _shares([g for g in gs if g["paper"] not in citers])}
        scan_runs = {"reader_n_agrees_scan": sum(1 for g in tested if g["n"] and scan.get(g["paper"], {}).get("run_modal") == int(g["n"])),
                     "reader_n_disagrees_scan": sum(1 for g in tested if g["n"] and scan.get(g["paper"], {}).get("run_modal") and scan[g["paper"]]["run_modal"] != int(g["n"])),
                     "tested_n_at_most_five": sum(1 for g in tested if g["n"] and g["n"] <= 5),
                     "tested_n_thirty": sum(1 for g in tested if g["n"] == 30)}
        # where the p-values sit, and the rate on the stratum where a t-type check is least objectionable
        ps = [g["p"] for g in tested if g["p"] is not None]
        fails_p = [x for x in ps if x >= 0.05]
        passes_p = [x for x in ps if x < 0.05]

        def floor_pair(g):
            return g["w"] is not None and g["r"] is not None and abs(g["w"]) < 1e-10 and abs(g["r"]) < 1e-10
        p_dist = {"tested_with_p": len(ps),
                  "fail_p_at_least_half": round(100 * sum(1 for x in fails_p if x >= 0.5) / len(fails_p), 1) if fails_p else None,
                  "fail_p_below_tenth": round(100 * sum(1 for x in fails_p if x < 0.10) / len(fails_p), 1) if fails_p else None,
                  "pass_p_below_thousandth": round(100 * sum(1 for x in passes_p if x < 1e-3) / len(passes_p), 1) if passes_p else None,
                  "pct_fail_at_one_percent": round(100 * sum(1 for x in ps if x >= 0.01) / len(ps), 1) if ps else None,
                  "pct_fail_at_ten_percent": round(100 * sum(1 for x in ps if x >= 0.10) / len(ps), 1) if ps else None,
                  "median_p_fail": round(statistics.median(fails_p), 3) if fails_p else None,
                  "median_p_pass": ("%.1e" % statistics.median(passes_p)) if passes_p else None,
                  "both_means_below_floor": sum(1 for g in tested if floor_pair(g)),
                  "without_floor": _shares([g for g in gs if not floor_pair(g)])}
        least = [g for g in means if not heavy(g) and g["paper"] not in mo and g["n"] and g["n"] >= 20 and g["whole_row"] != "y"]
        p_dist["least_objectionable"] = _shares(least)
        # the bar-less rate's own concentration, for the means of each kind: what per_paper gives the failure rate
        def per_paper_of(rec, hit):
            byp = collections.defaultdict(lambda: [0, 0])
            for g in rec:
                byp[g["paper"]][0] += 1
                byp[g["paper"]][1] += bool(hit(g))
            if not byp:
                return {}
            sizes = sorted(byp.values(), key=lambda x: -x[1])
            tot_hit = sum(x[1] for x in sizes)
            rates_ = [100 * h / n_ for n_, h in byp.values()]
            big = max(byp, key=lambda k: byp[k][1])
            top5 = {k for k, _ in sorted(byp.items(), key=lambda kv: -kv[1][1])[:5]}
            hits = [g for g in rec if hit(g)]
            rest_big = [g for g in rec if g["paper"] != big]
            rest_top5 = [g for g in rec if g["paper"] not in top5]
            return {"papers": len(byp), "groups": len(rec), "hits": tot_hit, "papers_with_hits": sum(1 for x in byp.values() if x[1]),
                    "effective_papers": _kish(rec)["effective"], "effective_papers_hits": _kish(hits)["effective"] if hits else None,
                    "largest_share": round(100 * byp[big][1] / tot_hit, 1) if tot_hit else None,
                    "top_three_share": round(100 * sum(x[1] for x in sizes[:3]) / tot_hit, 1) if tot_hit else None,
                    "top_five_share": round(100 * sum(x[1] for x in sizes[:5]) / tot_hit, 1) if tot_hit else None,
                    "median_rate": round(statistics.median(rates_), 1), "q1_rate": round(statistics.quantiles(rates_, n=4)[0], 1) if len(rates_) >= 4 else None,
                    "q3_rate": round(statistics.quantiles(rates_, n=4)[2], 1) if len(rates_) >= 4 else None,
                    "macro_rate": round(statistics.mean(rates_), 1), "macro_rate_ci": _boot_mean(rates_) if len(rates_) >= 10 else None,
                    "papers_at_zero": sum(1 for x in byp.values() if x[1] == 0), "papers_at_least_half": sum(1 for n_, h in byp.values() if h >= n_ / 2),
                    "papers_at_hundred": sum(1 for n_, h in byp.values() if h == n_),
                    "without_largest_pct": round(100 * sum(1 for g in rest_big if hit(g)) / len(rest_big), 1) if rest_big else None,
                    "without_largest_groups": len(rest_big),
                    "without_top_five_pct": round(100 * sum(1 for g in rest_top5 if hit(g)) / len(rest_top5), 1) if rest_top5 else None,
                    "without_top_five_groups": len(rest_top5)}
        barless = lambda g: not g["wb"] and not g["rb"]  # noqa: E731
        per_paper_barless = {lab: per_paper_of([g for g in means if g["kind"] == lab], barless) for lab in ("new_optimizer", "application")}
        per_paper_barless["all"] = per_paper_of(means, barless)
        # where the bar-less new-optimizer means sit, at paper level, against the full-text layout field
        bl_no = [g for g in means if g["kind"] == "new_optimizer" and barless(g)]
        per_paper_barless["new_optimizer_in_papers_printing_a_deviation_somewhere"] = sum(1 for g in bl_no if (tr.get(g["paper"]) or {}).get("std_layout") not in (None, "none", "unsure") and "parse_error" not in (tr.get(g["paper"]) or {}))
        per_paper_barless["new_optimizer_in_papers_printing_none"] = sum(1 for g in bl_no if (tr.get(g["paper"]) or {}).get("std_layout") == "none")
        per_paper_barless["new_optimizer_in_tables_filed_no_bar"] = sum(1 for g in bl_no if g["form"] in ("none", ""))
        # the residual blind spot: bar-less mean groups against where the full-text reading says the deviation sits
        def layout_of(paper):
            x = tr.get(paper) or {}
            return str(x.get("std_layout") or "unread").lower() if "parse_error" not in x else "unread"
        residual = {}
        for lay in ("separate_row", "separate_column", "same_cell", "none", "unsure", "unread"):
            gl = [g for g in means if layout_of(g["paper"]).startswith(lay)]
            residual[lay] = {"groups": len(gl), "papers": len({g["paper"] for g in gl}),
                             "pct_barless": round(100 * sum(1 for g in gl if not g["wb"] and not g["rb"]) / len(gl), 1) if gl else None}
        # the simulated coverage of every printed failure interval, on that stratum's own cluster configuration
        def cov_of(rec):
            byp = collections.defaultdict(lambda: [0, 0])
            for g in rec:
                if g["testable"] and g["fail"] is not None:
                    byp[g["paper"]][0] += 1
                    byp[g["paper"]][1] += bool(g["fail"])
            if len(byp) < 10 or _kish([g for g in rec if g["testable"] and g["fail"] is not None])["effective"] < 8:
                return None
            return _boot_coverage(byp, sims=400, reps=500, seed=2)
        strata = {"all": gs, "means_only": means,
                  "new_optimizer": [g for g in gs if g["kind"] == "new_optimizer"], "application": [g for g in gs if g["kind"] == "application"],
                  "means_new_optimizer": [g for g in means if g["kind"] == "new_optimizer"], "means_application": [g for g in means if g["kind"] == "application"],
                  "without_top_three": [g for g in gs if g["paper"] not in top3], "without_top_four": [g for g in gs if g["paper"] not in top4],
                  "sd_lt_mean": [g for g in gs if not heavy(g)], "without_column_oriented": [g for g in gs if g["orientation"] != "column"],
                  "without_whole_row": [g for g in gs if g["whole_row"] != "y"], "single_objective": [g for g in gs if g["paper"] not in mo],
                  "without_note": [g for g in gs if not scan.get(g["paper"], {}).get("bold_note")],
                  "without_impossible": [g for g in gs if not _impossible(g)]}
        coverage = {k: cov_of(v) for k, v in strata.items()}
        covs = [v["coverage"] for v in coverage.values() if v]
        coverage_summary = {"strata": sum(1 for v in coverage.values() if v), "min": min(covs) if covs else None, "max": max(covs) if covs else None}
        # the kinds under the second labeller, and where both labellers agree
        second = {lab: _shares([g for g in gs if kinds2.get(g["paper"]) == lab]) for lab in ("new_optimizer", "application")} if kinds2 else {}
        both = {lab: _shares([g for g in gs if kinds2.get(g["paper"]) == lab and g["kind"] == lab]) for lab in ("new_optimizer", "application")} if kinds2 else {}
        second_m = {lab: _shares([g for g in means if kinds2.get(g["paper"]) == lab]) for lab in ("new_optimizer", "application")} if kinds2 else {}
        both_m = {lab: _shares([g for g in means if kinds2.get(g["paper"]) == lab and g["kind"] == lab]) for lab in ("new_optimizer", "application")} if kinds2 else {}
        return {"name": name, "all": _shares(gs), "by_kind": _by_kind(gs), "per_paper": per_paper, "shape": shape,
                "by_kind_second": second, "by_kind_both": both, "by_kind_second_means": second_m, "by_kind_both_means": both_m,
                "residual_layout": residual, "coverage_by_stratum": coverage, "coverage_summary": coverage_summary,
                "per_paper_barless": per_paper_barless, "p_dist": p_dist,
                "objective": objective, "orientation": orientation,
                "alternatives": alternatives, "rows": rows, "bold_rule": bold, "note": note, "citing": citing, "scan_runs": scan_runs,
                "dropped_nonextremal": DROPPED["nonextremal"], "dropped_nonextremal_papers": len(DROPPED["papers"])}

    gs1 = _regroup(labels, items, kinds)
    pre_readings = readings_of(gs1, "pre-registered")
    merged, reread, mlog = merged_labels(labels)
    gs2 = _regroup(merged, items, kinds)
    corrected_readings = readings_of(gs2, "corrected")
    # the re-read taken wholesale, both directions, as the size of the one-way merge rule
    merged_w, _, _ = merged_labels(labels, wholesale=True)
    gs3 = _regroup(merged_w, items, kinds)
    wholesale = {"all": _shares(gs3), "by_kind": _by_kind(gs3), "means_only": _shares([g for g in gs3 if _is_mean(g)]),
                 "means_only_by_kind": _by_kind([g for g in gs3 if _is_mean(g)])}

    def on_pages(gs):
        return [g for g in gs if g["page"] in reread]
    before, after = _shares(on_pages(gs1)), _shares(on_pages(gs2))
    rows_reread = dict(mlog, before_on_those_pages=before, after_on_those_pages=after,
                       before_barred=sum(1 for g in on_pages(gs1) if g["wb"] and g["rb"]),
                       after_barred=sum(1 for g in on_pages(gs2) if g["wb"] and g["rb"]),
                       before_means=sum(1 for g in on_pages(gs1) if _is_mean(g)), after_means=sum(1 for g in on_pages(gs2) if _is_mean(g)),
                       tables_separate_row_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y") and str(t.get("bar_form", "")).lower() == "separate_row"),
                       tables_separate_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y") and str(t.get("bar_form", "")).lower().startswith("separate")),
                       tables_none_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y") and str(t.get("bar_form", "")).lower() in ("none", "")),
                       pages_in_kits=sum(len(json.load(open(os.path.join(k, "items.json"), encoding="utf-8"))) for k in ROW_KITS if os.path.exists(os.path.join(k, "items.json"))),
                       pages_new_optimizer=sum(1 for i in reread if kinds.get(items[i]["paper"]) == "new_optimizer"),
                       pages_application=sum(1 for i in reread if kinds.get(items[i]["paper"]) == "application"))
    # papers with a results table in the census, and those with at least one single-bold group, by kind
    def papers_by_kind(labs, gs):
        with_tables = collections.Counter()
        seen = set()
        for iid, pg in labs.items():
            paper = items[iid]["paper"]
            if paper in seen:
                continue
            if any(str(t.get("results_table", "")).lower().startswith("y") for t in pg.get("tables", [])):
                seen.add(paper)
                with_tables[kinds.get(paper, "unlabelled")] += 1
        with_groups = collections.Counter()
        for paper in {g["paper"] for g in gs}:
            with_groups[kinds.get(paper, "unlabelled")] += 1
        return {"papers_with_results_tables": dict(with_tables), "papers_with_single_bold_groups": dict(with_groups)}
    out = {"layout": layout_of(labels), "layout_corrected": layout_of(merged),
           "papers_pre": papers_by_kind(labels, gs1), "papers_corrected": papers_by_kind(merged, gs2),
           "pre": pre_readings, "corrected": corrected_readings, "wholesale": wholesale,
           "rows_reread": rows_reread,
           "pages_read": len(labels), "pages_in_kit": len(items), "papers_in_kit": len({it["paper"] for it in items.values()}),
           "papers_read": len({items[i]["paper"] for i in labels})}
    json.dump([merged[i] for i in sorted(merged)], open(os.path.join(KIT, "labels_corrected.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    os.makedirs("out/swevo", exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    a, b = out["pre"]["all"], out["corrected"]["all"]
    print("pre:", a["groups"], a["pct_neither"], a["pct_testable"], a["tested"], a["pct_fail"], "| corrected:", b["groups"], b["pct_neither"], b["pct_testable"], b["tested"], b["pct_fail"], "| merge:", mlog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
