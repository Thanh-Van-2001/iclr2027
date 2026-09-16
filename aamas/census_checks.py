"""Three checks on the census, each from a reading the census reader made
under the census protocol:

  non-caption pages   a random sample of pages on which the parser detected
                      no table caption: how many hold a results table with a
                      single-bold group (the recall of caption detection)
  zero-group re-read  the pages on which the parser reads a comparison and
                      the census listed no group, read a second time: how
                      many yield groups on the second read, and the census
                      shares with those second reads substituted (the union)
  mainstream pages    the concurrent study's random NeurIPS/ICML pages read by
                      the census reader, so the cross-venue comparison holds
                      one reader fixed

Usage: python aamas/census_checks.py
"""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from reader_retest import groups_of  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

OUT = "out/aamas/census_checks.json"


def _boot_pages(vals, num, den, reps=2000, seed=0):
    rng = random.Random(seed)
    out = []
    for _ in range(reps):
        draw = [vals[rng.randrange(len(vals))] for _ in vals]
        d = sum(v[den] for v in draw)
        if d:
            out.append(100.0 * sum(v[num] for v in draw) / d)
    out.sort()
    return [round(out[int(0.025 * len(out))], 1), round(out[int(0.975 * len(out)) - 1], 1)] if out else None


def noncaption(kit="audits/aamas_noncaption"):
    if not os.path.exists(os.path.join(kit, "labels.json")):
        return {}
    items = json.load(open(os.path.join(kit, "items.json"), encoding="utf-8"))
    labels = {p["id"]: p for p in json.load(open(os.path.join(kit, "labels.json"), encoding="utf-8"))}
    draw = json.load(open(os.path.join(kit, "draw.json"), encoding="utf-8"))
    per = []
    for it in items:
        p = labels.get(it["id"])
        if p is None:
            continue
        results = [t for t in p.get("tables", []) if t.get("results_table", "").lower().startswith("y")]
        g = groups_of(p)
        per.append({"id": it["id"], "paper": it["paper"], "tables": len(p.get("tables", [])),
                    "results_tables": len(results), "groups": len(g),
                    "neither": sum(1 for x in g if x["neither"]), "testable": sum(1 for x in g if x["testable"])})
    n = len(per)
    with_results = sum(1 for p in per if p["results_tables"])
    with_groups = sum(1 for p in per if p["groups"])
    g_all = sum(p["groups"] for p in per)
    return {"pages_read": n, "pool_pages": draw["pool_pages"], "pool_papers": draw["pool_papers"],
            "pages_with_any_table": sum(1 for p in per if p["tables"]),
            "pages_with_results_table": with_results,
            "pages_with_groups": with_groups,
            "pct_pages_with_groups": round(100.0 * with_groups / n, 1) if n else None,
            "ci_pages_with_groups": [round(100 * x, 1) for x in wilson_interval(with_groups, n)] if n else None,
            "ci_pages_with_any_table": [round(100 * x, 1) for x in wilson_interval(sum(1 for p in per if p["tables"]), n)] if n else None,
            "groups": g_all,
            "pct_neither": round(100.0 * sum(p["neither"] for p in per) / g_all, 1) if g_all else None,
            "pct_testable": round(100.0 * sum(p["testable"] for p in per) / g_all, 1) if g_all else None,
            # the implied number of caption-less pages with groups in the corpus
            "implied_corpus_pages_with_groups": round(draw["pool_pages"] * with_groups / n) if n else None,
            "implied_corpus_pages_upper": round(draw["pool_pages"] * wilson_interval(with_groups, n)[1]) if n else None,
            "per_page": per}


def zero_reread(kit="audits/aamas_census_zero", census="audits/aamas_census"):
    if not os.path.exists(os.path.join(kit, "labels.json")):
        return {}
    items = json.load(open(os.path.join(kit, "items.json"), encoding="utf-8"))
    draw = json.load(open(os.path.join(kit, "draw.json"), encoding="utf-8"))
    relab = {p["id"]: p for p in json.load(open(os.path.join(kit, "labels.json"), encoding="utf-8"))}
    zero_ids = set(draw["zero_group_pages"])
    per = []
    for it in items:
        p = relab.get(it["id"])
        if p is None:
            continue
        g = groups_of(p)
        per.append({"id": it["id"], "zero_group_page": it["id"] in zero_ids, "groups": len(g),
                    "neither": sum(1 for x in g if x["neither"]), "testable": sum(1 for x in g if x["testable"])})
    z = [p for p in per if p["zero_group_page"]]
    d = [p for p in per if not p["zero_group_page"]]
    res = {"zero_pages_reread": len(z), "zero_pages_with_groups_on_reread": sum(1 for p in z if p["groups"]),
           "groups_found_on_reread": sum(p["groups"] for p in z),
           "pct_zero_pages_with_groups_on_reread": round(100.0 * sum(1 for p in z if p["groups"]) / len(z), 1) if z else None,
           "reread_pct_neither": round(100.0 * sum(p["neither"] for p in z) / max(sum(p["groups"] for p in z), 1), 1) if z else None,
           "pilot_dropouts_reread": len(d), "pilot_dropouts_with_groups_on_reread": sum(1 for p in d if p["groups"]),
           "groups_on_pilot_dropouts": sum(p["groups"] for p in d)}
    # the union census: the census labels with every re-read page that lists
    # groups substituted, scored by the same script as the census
    census_labels = json.load(open(os.path.join(census, "labels.json"), encoding="utf-8"))
    sub = {p["id"] for p in per if p["groups"]}
    union = [relab[p["id"]] if p["id"] in sub else p for p in census_labels]
    upath = os.path.join(census, "labels_union.json")
    json.dump(union, open(upath, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    subprocess.run([sys.executable, "study/pages_score.py", "--items", os.path.join(census, "items.json"),
                    "--labels", upath, "--analysis", "out/aamas/analysis.json",
                    "--out", "out/aamas/gold_set_census_union.json"], check=True, capture_output=True)
    u = json.load(open("out/aamas/gold_set_census_union.json", encoding="utf-8"))
    res["union"] = {"pages_substituted": len(sub), "groups": u["reader"]["groups"],
                    "pct_neither": u["reader"]["pct_neither"], "ci_neither_papers": u["reader"]["ci_neither_papers"],
                    "pct_testable": u["reader"]["pct_testable"], "ci_testable_papers": u["reader"]["ci_testable_papers"],
                    "reader_failure": u["reader_failure"],
                    "recall_pct": u["reader_groups_found_by_pipeline"]["pct"],
                    "precision_pct": u["pipeline_groups_found_by_reader"]["pct"]}
    res["per_page"] = per
    return res


def mainstream(kit="audits/gold_f", labels="labels_gemini.json"):
    path = os.path.join(kit, labels)
    if not os.path.exists(path):
        return {}
    subprocess.run([sys.executable, "study/pages_score.py", "--items", os.path.join(kit, "items.json"),
                    "--labels", path, "--analysis", "out/analysis_2025.json",
                    "--out", "out/aamas/gold_set_ml_pages_census_reader.json"], check=True, capture_output=True)
    d = json.load(open("out/aamas/gold_set_ml_pages_census_reader.json", encoding="utf-8"))
    # the two readers on the same mainstream pages
    subprocess.run([sys.executable, "aamas/reader_retest.py", "--first", kit, "--second", kit,
                    "--second-labels", path, "--out", "out/aamas/reader_cross_ml.json"], check=True, capture_output=True)
    x = json.load(open("out/aamas/reader_cross_ml.json", encoding="utf-8"))
    return {"pages": d["n_pages"], "groups": d["reader"]["groups"],
            "pct_neither": d["reader"]["pct_neither"], "ci_neither_papers": d["reader"]["ci_neither_papers"],
            "pct_testable": d["reader"]["pct_testable"], "ci_testable_papers": d["reader"]["ci_testable_papers"],
            "reader_failure": d["reader_failure"],
            "recall_pct": d["reader_groups_found_by_pipeline"]["pct"],
            "recall_page_ci": d["reader_groups_found_by_pipeline"].get("page_ci"),
            "precision_pct": d["pipeline_groups_found_by_reader"]["pct"],
            "cross_reader": {k: v for k, v in x.items() if k != "per_page"}}


def main():
    out = {"noncaption": noncaption(), "zero_reread": zero_reread(), "mainstream": mainstream()}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    for k, v in out.items():
        print(k, json.dumps({kk: vv for kk, vv in v.items() if kk != "per_page"})[:600])


if __name__ == "__main__":
    main()
