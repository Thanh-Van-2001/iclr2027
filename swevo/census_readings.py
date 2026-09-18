"""Readings of the reader census beyond what study/pages_score.py reports:
the layout of the dispersion in the results tables (beside the mean, in a
separate row, in a separate column, nowhere), the reader's run counts and
their sources, and the reader's bar-less / testable / failing shares by
kind of paper, with cluster-bootstrap intervals over papers.

Reads audits/swevo_census/{items,labels}.json, out/swevo/gold_set_census.json
and out/swevo/kinds_merged.csv; writes out/swevo/census_readings.json.
"""
import collections
import csv
import json
import os
import random
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from paperengine.stats import wilson_interval  # noqa: E402
from pages_score import _bar_num, _se  # noqa: E402
from gold_set import _num  # noqa: E402
from analyze import p_value  # noqa: E402

# a reader "group" whose header label names a summary row rather than an
# optimizer or a function is a Std, Rank or Best/Worst row read as a group
ROW_LABEL = re.compile(r"^(std|sd|s\.?d\.?|standard deviation|stdev|rank|ave\.? ?rank|mean rank|friedman|best|worst|median|min|max|time|p[- ]?value|h)\b", re.I)


def _regroup(labels: dict, items: dict, kinds: dict):
    """Every reader group with the fields the readings below need, scored
    as pages_score scores it (extremal-only, Welch on the reader's values)."""
    groups = []
    for iid, pg in labels.items():
        paper = items[iid]["paper"]
        for t in pg.get("tables", []):
            if not str(t.get("results_table", "")).lower().startswith("y"):
                continue
            kind = str(t.get("bar_kind", "")).lower()
            n = _num(t.get("n_runs"))
            form = str(t.get("bar_form", "")).lower().strip()
            for g in t.get("groups", []):
                w, r = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                d = str(g.get("direction", "")).lower()
                if w is not None and r is not None and (w == r or (d.startswith("low") and w > r) or (d.startswith("high") and w < r)):
                    continue
                wd, rd = _bar_num(g.get("winner_disp")), _bar_num(g.get("runner_disp"))
                wb = wd is not None or str(g.get("winner_disp", "")).startswith("[")
                rb = rd is not None or str(g.get("runner_disp", "")).startswith("[")
                testable = wb and rb and (n is not None or kind in ("se", "ci"))
                fail = None
                if testable and None not in (w, r):
                    sw, sr = _se(g.get("winner_disp"), kind, n), _se(g.get("runner_disp"), kind, n)
                    if None not in (sw, sr):
                        res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                        fail = (res["p"] >= 0.05) if res else None
                groups.append({"page": iid, "paper": paper, "kind": kinds.get(paper, "unlabelled"), "form": form,
                               "label": str(g.get("label", "")), "w": w, "r": r, "wd": wd, "rd": rd,
                               "wb": wb, "rb": rb, "n": n, "testable": testable, "fail": fail,
                               "row_label": bool(ROW_LABEL.match(str(g.get("label", "")).strip()))})
    return groups


def _shares(gs: list) -> dict:
    n = len(gs)
    tested = [g for g in gs if g["testable"] and g["fail"] is not None]
    pages = collections.defaultdict(lambda: {"paper": "", "n_groups": 0, "neither": 0, "testable": 0, "fails": 0, "tested": 0})
    for g in gs:
        d = pages[g["page"]]
        d["paper"] = g["paper"]; d["n_groups"] += 1; d["neither"] += (not g["wb"] and not g["rb"])
        d["testable"] += g["testable"]; d["tested"] += (g["testable"] and g["fail"] is not None); d["fails"] += bool(g["fail"])
    pp = list(pages.values())
    return {"groups": n, "papers": len({g["paper"] for g in gs}),
            "pct_neither": round(100 * sum(1 for g in gs if not g["wb"] and not g["rb"]) / n, 1) if n else None,
            "ci_neither": _boot(pp, "neither", "n_groups") if n else None,
            "pct_testable": round(100 * sum(1 for g in gs if g["testable"]) / n, 1) if n else None,
            "ci_testable": _boot(pp, "testable", "n_groups") if n else None,
            "tested": len(tested), "tested_papers": len({g["paper"] for g in tested}),
            "pct_fail": round(100 * sum(1 for g in tested if g["fail"]) / len(tested), 1) if tested else None,
            "ci_fail": _boot(pp, "fails", "tested") if tested else None}

KIT = "audits/swevo_census"
OUT = "out/swevo/census_readings.json"


def _boot(pages: list, num: str, den: str, reps: int = 2000, seed: int = 0):
    by = collections.defaultdict(lambda: [0, 0])
    for p in pages:
        by[p["paper"]][0] += p[num]
        by[p["paper"]][1] += p[den]
    keys = list(by)
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


def main() -> int:
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    score = json.load(open("out/swevo/gold_set_census.json", encoding="utf-8"))
    kinds, metaphor = {}, {}
    if os.path.exists("out/swevo/kinds_merged.csv"):
        for r in csv.DictReader(open("out/swevo/kinds_merged.csv", encoding="utf-8", newline="")):
            kinds[r["id"]] = r["label"]
            metaphor[r["id"]] = r["metaphor_named"]

    # 1. the layout of the dispersion, over the reader's results tables
    forms = collections.Counter()
    groups_by_form, barred_by_form = collections.Counter(), collections.Counter()
    forms_by_kind = collections.defaultdict(collections.Counter)
    n_runs_vals = collections.Counter()
    n_src = collections.Counter()
    bar_kind = collections.Counter()
    tables_with_groups = 0
    for iid, pg in labels.items():
        paper = items[iid]["paper"]
        for t in pg.get("tables", []):
            if not str(t.get("results_table", "")).lower().startswith("y"):
                continue
            f = str(t.get("bar_form", "")).lower().strip() or "unstated"
            forms[f] += 1
            forms_by_kind[kinds.get(paper, "unlabelled")][f] += 1
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
                tables_with_groups += 1
                groups_by_form[f] += len(t["groups"])
                barred_by_form[f] += sum(1 for g in t["groups"] if str(g.get("winner_disp", "")).strip().lower() not in ("", "none", "unclear")
                                         and str(g.get("runner_disp", "")).strip().lower() not in ("", "none", "unclear"))
    n_results = sum(forms.values())
    layout = {"results_tables": n_results, "tables_with_groups": tables_with_groups,
              "bar_form": dict(forms.most_common()),
              "pct_bar_form": {k: round(100 * v / max(n_results, 1), 1) for k, v in forms.items()},
              "bar_form_by_kind": {k: dict(v) for k, v in forms_by_kind.items()},
              "bar_kind": dict(bar_kind.most_common()),
              "n_runs": [[k, v] for k, v in n_runs_vals.most_common(10)],
              "n_source": dict(n_src.most_common()),
              "groups_by_form": dict(groups_by_form), "groups_with_both_bars_by_form": dict(barred_by_form),
              "pct_groups_in_separate_layout": round(100 * sum(v for k, v in groups_by_form.items() if k.startswith("separate")) / max(sum(groups_by_form.values()), 1), 1),
              "pct_barred_groups_in_separate_layout": round(100 * sum(v for k, v in barred_by_form.items() if k.startswith("separate")) / max(sum(barred_by_form.values()), 1), 1),
              "pct_tables_with_run_count": round(100 * sum(v for k, v in n_src.items() if k not in ("none", "unstated")) / max(n_results, 1), 1),
              "pct_tables_at_thirty": round(100 * n_runs_vals.get(30, 0) / max(n_results, 1), 1)}

    # 2. the reader's shares by kind, from the scorer's per-page records
    per_page = score["per_page"]
    for p in per_page:
        p["kind"] = kinds.get(p["paper"], "unlabelled")
        p["fails"] = sum(1 for g in p.get("tested_groups", []) if g.get("fail"))
        p["tested"] = len(p.get("tested_groups", []))
    by_kind = {}
    for lab in sorted({p["kind"] for p in per_page}) + ["all"]:
        sub = [p for p in per_page if lab == "all" or p["kind"] == lab]
        g = sum(p["n_groups"] for p in sub)
        by_kind[lab] = {"pages": len(sub), "papers": len({p["paper"] for p in sub}),
                        "papers_with_groups": len({p["paper"] for p in sub if p["n_groups"]}),
                        "groups": g,
                        "pct_neither": round(100 * sum(p["neither"] for p in sub) / g, 1) if g else None,
                        "ci_neither": _boot(sub, "neither", "n_groups"),
                        "pct_testable": round(100 * sum(p["testable"] for p in sub) / g, 1) if g else None,
                        "ci_testable": _boot(sub, "testable", "n_groups"),
                        "tested": sum(p["tested"] for p in sub),
                        "tested_papers": len({p["paper"] for p in sub if p["tested"]}),
                        "pct_fail": (round(100 * sum(p["fails"] for p in sub) / sum(p["tested"] for p in sub), 1)
                                     if sum(p["tested"] for p in sub) else None),
                        "ci_fail": _boot(sub, "fails", "tested")}
    # 3. readings on the reader's groups themselves
    gs = _regroup(labels, items, kinds)
    tested = [g for g in gs if g["testable"] and g["fail"] is not None]
    by_paper = collections.defaultdict(lambda: [0, 0])
    for g in tested:
        by_paper[g["paper"]][0] += 1
        by_paper[g["paper"]][1] += bool(g["fail"])
    sizes = sorted(by_paper.values(), key=lambda x: -x[0])
    tot = sum(x[0] for x in sizes)
    rates = [100 * f / n for n, f in by_paper.values()]
    largest = max(by_paper, key=lambda k: by_paper[k][0]) if by_paper else None
    per_paper = {"papers": len(by_paper), "tested": tot,
                 "top_four_share": round(100 * sum(x[0] for x in sizes[:4]) / tot, 1) if tot else None,
                 "top_ten_share": round(100 * sum(x[0] for x in sizes[:10]) / tot, 1) if tot else None,
                 "median_rate": round(statistics.median(rates), 1) if rates else None,
                 "q1_rate": round(statistics.quantiles(rates, n=4)[0], 1) if len(rates) >= 4 else None,
                 "q3_rate": round(statistics.quantiles(rates, n=4)[2], 1) if len(rates) >= 4 else None,
                 "papers_any_fail": sum(1 for n, f in by_paper.values() if f),
                 "largest_paper_tested": by_paper[largest][0] if largest else 0,
                 "largest_paper_fail": round(100 * by_paper[largest][1] / by_paper[largest][0], 1) if largest else None,
                 "without_largest": _shares([g for g in gs if g["paper"] != largest]),
                 "without_top_four": _shares([g for g in gs if g["paper"] not in {k for k, _ in sorted(by_paper.items(), key=lambda kv: -kv[1][0])[:4]}])}
    # heavy tails: a deviation at least the size of the mean, or a mean near zero
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
             "pct_tested_zero_sd": round(100 * sum(1 for g in tested if zero_sd(g)) / len(tested), 1) if tested else None}
    # row labels: Std, Rank, Best/Worst rows read as groups
    row = {"row_label_groups": sum(1 for g in gs if g["row_label"]), "row_label_pct": round(100 * sum(1 for g in gs if g["row_label"]) / max(len(gs), 1), 1),
           "row_label_only": _shares([g for g in gs if g["row_label"]]), "without_row_label": _shares([g for g in gs if not g["row_label"]])}
    # the paper's stated bold rule and the journal's note, joined from the full-text reader and the text scan
    tr = {}
    import glob
    for path in sorted(glob.glob("out/swevo/test_reader_part*.json")):
        tr.update(json.load(open(path, encoding="utf-8")))
    scan = json.load(open("out/swevo/text_scan.json", encoding="utf-8")) if os.path.exists("out/swevo/text_scan.json") else {}
    def rule(paper):
        v = tr.get(paper)
        if v is None or "parse_error" in v:
            return "not_read"
        b = str(v.get("bold_rule") or "not stated").lower()
        if "statistic" in b or "signific" in b:
            return "statistically_best"
        if "best" in b or "optimal" in b or "lowest" in b or "highest" in b:
            return "best"
        return "not_stated"
    bold = {lab: _shares([g for g in gs if rule(g["paper"]) == lab]) for lab in ("best", "statistically_best", "not_stated", "not_read")}
    note = {"with_note": _shares([g for g in gs if scan.get(g["paper"], {}).get("bold_note")]),
            "without_note": _shares([g for g in gs if not scan.get(g["paper"], {}).get("bold_note")]),
            "papers_with_note_in_census": len({g["paper"] for g in gs if scan.get(g["paper"], {}).get("bold_note")})}
    keys = ["derrac2011", "garcia2009", "garcia2010", "sorensen2015", "aranha2022", "camacho2022", "bartz2020", "beiranvand2017", "kendall2016", "hansen_coco"]
    def cites(paper):
        return any(scan.get(paper, {}).get("cites", {}).get(k) for k in keys)
    citing = {"citing": _shares([g for g in gs if cites(g["paper"])]), "not_citing": _shares([g for g in gs if not cites(g["paper"])])}
    scan_runs = {"reader_n_agrees_scan": sum(1 for g in tested if g["n"] and scan.get(g["paper"], {}).get("run_modal") == int(g["n"])),
                 "reader_n_disagrees_scan": sum(1 for g in tested if g["n"] and scan.get(g["paper"], {}).get("run_modal") and scan[g["paper"]]["run_modal"] != int(g["n"]))}
    out = {"layout": layout, "by_kind": by_kind, "per_paper": per_paper, "shape": shape, "row": row, "bold_rule": bold,
           "note": note, "citing": citing, "scan_runs": scan_runs, "regrouped": _shares(gs),
           "pages_read": len(labels), "pages_in_kit": len(items),
           "papers_in_kit": len({it["paper"] for it in items.values()}),
           "papers_read": len({items[i]["paper"] for i in labels})}
    os.makedirs("out/swevo", exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(json.dumps(layout["pct_bar_form"]), "| groups", by_kind["all"]["groups"], "neither", by_kind["all"]["pct_neither"],
          "testable", by_kind["all"]["pct_testable"], "fail", by_kind["all"]["pct_fail"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
