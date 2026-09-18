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
ROW_KITS = ["audits/swevo_census_rows", "audits/swevo_census_rows2"]
OUT = "out/swevo/census_readings.json"

# a group whose label names a summary row rather than a function or an
# optimizer: a Std, Rank or Time row is not a statistic over runs at all; a
# Best, Worst or Median row is a statistic over runs that owes no deviation
STD_ROW = re.compile(r"(?:^|[ ,;:(/])(std|sd|s\.?d\.?|standard deviation|stdev|rank|ave\.? ?rank|mean rank|friedman|time|p[- ]?value|h)(?:$|[ ,;:)/])", re.I)
BEST_ROW = re.compile(r"(?:^|[ ,;:(/])(best|worst|wor\.|median|min|max)(?:$|[ ,;:)/])", re.I)
ROW_LABEL = re.compile("|".join([STD_ROW.pattern, BEST_ROW.pattern]), re.I)
# a table whose caption says it holds ranks, test verdicts or settings
NOT_MEANS_CAPTION = re.compile(r"friedman|rank|wilcoxon|p[- ]?value|sensitivity|parameter setting|settings|complexity|running time|computational time", re.I)


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


def _regroup(labels: dict, items: dict, kinds: dict):
    """Every reader group with the fields the readings need, scored as
    pages_score scores it (extremal-only, Welch on the reader's values)."""
    groups = []
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
                    continue
                wd, rd = _disp(g.get("winner_disp")), _disp(g.get("runner_disp"))
                wb = wd is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = rd is not None or str(g.get("runner_disp", "")).startswith("[")
                testable = wb and rb and (n is not None or kind in ("se", "ci"))
                fail = None
                zero_both = False
                if testable and None not in (w, r):
                    sw, sr = _se(_disp_str(g.get("winner_disp")), kind, n), _se(_disp_str(g.get("runner_disp")), kind, n)
                    if None not in (sw, sr):
                        res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                        fail = (res["p"] >= 0.05) if res else None
                        zero_both = res is None and sw == 0 and sr == 0
                label = str(g.get("label", "")).strip()
                groups.append({"page": iid, "paper": paper, "kind": kinds.get(paper, "unlabelled"), "form": form,
                               "label": label, "w": w, "r": r, "wd": wd, "rd": rd, "wb": wb, "rb": rb, "n": n,
                               "n_source": str(t.get("n_source", "")).lower().strip(),
                               "testable": testable, "fail": fail, "zero_both": zero_both,
                               "std_row": bool(STD_ROW.search(label)), "best_row": bool(BEST_ROW.search(label)),
                               "row_label": bool(ROW_LABEL.search(label)), "not_means_table": bool(NOT_MEANS_CAPTION.search(cap)),
                               "table": f"{iid}:{ti}", "kind_label": kind})
    return groups


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


def _boot_coverage(by_paper: dict, sims: int = 300, reps: int = 1000, seed: int = 1) -> dict:
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
    return {"papers": len(pop), "sims": sims, "coverage": round(100 * hits / sims, 1), "coverage_wald": round(100 * hits_wald / sims, 1),
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
    de = 1 + (n0 - 1) * icc
    return {"icc": round(icc, 3), "design_effect": round(de, 2), "effective_groups": round(N / de, 1), "n0": round(n0, 1)}


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
    return {"groups": n, "papers": len({g["paper"] for g in gs}),
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
            "unreadable": sum(1 for g in gs if g["testable"] and g["fail"] is None and not g["zero_both"])}


def _by_kind(gs: list) -> dict:
    out = {lab: _shares([g for g in gs if g["kind"] == lab]) for lab in ("new_optimizer", "application")}
    out["all"] = _shares(gs)
    return out


def merged_labels(labels: dict, kits=ROW_KITS) -> tuple:
    """The corrected census: per table, the re-read table replaces the
    original only where it files a separate layout or lists at least as
    many groups of means; the record of gains and losses comes with it."""
    reread = {}
    for kit in kits:
        for path in sorted(glob.glob(os.path.join(kit, "labels_shard*.json"))):
            for pg in json.load(open(path, encoding="utf-8")):
                if not str(pg.get("note", "")).startswith("failed"):
                    reread[pg["id"]] = pg
    merged = {iid: json.loads(json.dumps(pg)) for iid, pg in labels.items()}
    log = {"pages_reread": len(reread), "tables_reread": 0, "tables_replaced": 0, "tables_kept": 0, "tables_truncated": 0,
           "pages_with_a_kept_table": 0}

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
            separate = str(new.get("bar_form", "")).lower().startswith("separate")
            # the re-read must not lose a dispersion the original had, and
            # must list as many means unless it files a separate layout
            enough = n_barred(new) >= n_barred(old) and (n_means(new) >= n_means(old) or separate)
            if enough:
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
                     "without_top_four": _shares([g for g in gs if g["paper"] not in top4])}

        def heavy(g):
            return (g["wd"] is not None and g["w"] is not None and g["wd"] >= abs(g["w"])) or (g["rd"] is not None and g["r"] is not None and g["rd"] >= abs(g["r"]))

        def tiny(g):
            return (g["w"] is not None and abs(g["w"]) < 1e-3) or (g["r"] is not None and abs(g["r"]) < 1e-3)

        def zero_sd(g):
            return (g["wd"] is not None and g["wd"] == 0) or (g["rd"] is not None and g["rd"] == 0)
        shape = {"tested": len(tested),
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
        return {"name": name, "all": _shares(gs), "by_kind": _by_kind(gs), "per_paper": per_paper, "shape": shape,
                "alternatives": alternatives, "rows": rows, "bold_rule": bold, "note": note, "citing": citing, "scan_runs": scan_runs}

    gs1 = _regroup(labels, items, kinds)
    merged, reread, mlog = merged_labels(labels)
    gs2 = _regroup(merged, items, kinds)

    def on_pages(gs):
        return [g for g in gs if g["page"] in reread]
    before, after = _shares(on_pages(gs1)), _shares(on_pages(gs2))
    rows_reread = dict(mlog, before_on_those_pages=before, after_on_those_pages=after,
                       before_barred=sum(1 for g in on_pages(gs1) if g["wb"] and g["rb"]),
                       after_barred=sum(1 for g in on_pages(gs2) if g["wb"] and g["rb"]),
                       before_means=sum(1 for g in on_pages(gs1) if _is_mean(g)), after_means=sum(1 for g in on_pages(gs2) if _is_mean(g)),
                       tables_separate_row_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("bar_form", "")).lower() == "separate_row"),
                       tables_separate_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("bar_form", "")).lower().startswith("separate")),
                       tables_none_after=sum(1 for pg in reread.values() for t in pg.get("tables", []) if str(t.get("results_table", "")).lower().startswith("y") and str(t.get("bar_form", "")).lower() in ("none", "")),
                       pages_in_kits=sum(len(json.load(open(os.path.join(k, "items.json"), encoding="utf-8"))) for k in ROW_KITS if os.path.exists(os.path.join(k, "items.json"))),
                       pages_new_optimizer=sum(1 for i in reread if kinds.get(items[i]["paper"]) == "new_optimizer"),
                       pages_application=sum(1 for i in reread if kinds.get(items[i]["paper"]) == "application"))
    out = {"layout": layout_of(labels), "layout_corrected": layout_of(merged),
           "pre": readings_of(gs1, "pre-registered"), "corrected": readings_of(gs2, "corrected"),
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
