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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine.stats import wilson_interval  # noqa: E402

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
                        "pct_fail": (round(100 * sum(p["fails"] for p in sub) / sum(p["tested"] for p in sub), 1)
                                     if sum(p["tested"] for p in sub) else None),
                        "ci_fail": _boot(sub, "fails", "tested")}
    out = {"layout": layout, "by_kind": by_kind,
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
