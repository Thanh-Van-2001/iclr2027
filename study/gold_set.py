"""A gold set for the extractor, read from rendered tables with its output hidden.

Every number in the paper rests on the extractor pairing the right bold cell
with the right rival and reading the right error bar and run count. Four rounds
of review said the same thing about that: the paper measured presence, not
values, and never against ground truth. This builds the ground truth.

Four strata, each answering a different objection:

  testable      comparisons the failure rate is computed on: every field
  no_bar        retained comparisons with no error bar: is it really absent?
  discarded     tables thrown away for having no single-bold group: why?
  non_extremal  single-bold groups whose bold cell is not the best: why?

``sample`` draws the items and renders each table with the pipeline's chosen
cell circled and nothing else -- no values, no verdict -- so the reader labels
blind. Candidate run-count sentences from the whole paper are written beside
the image, because the pipeline saw the same sentences. ``score`` compares the
labels against the pipeline field by field, with Wilson intervals, and
recomputes the failure rate on the gold subset from the reader's values.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import fitz  # noqa: E402

from analyze import _columns, _rows, comparisons_from_table, orientation, test_comparison  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

RUN_SENTENCE = re.compile(r"(?i)[^.\n]{0,160}\b(?:seeds?|runs?|trials?|repetitions?|replicates?)\b[^.\n]{0,160}")

FIELDS = {
    "testable": ["results_table", "bold_ok", "orientation", "direction", "winner_mean",
                 "winner_disp", "runner_mean", "runner_disp", "disp_type", "n_runs",
                 "n_source", "note"],
    "no_bar": ["results_table", "bold_ok", "orientation", "direction", "winner_mean",
               "runner_mean", "error_bar_present", "note"],
    "discarded": ["results_table", "cause", "note"],
    "non_extremal": ["results_table", "cause", "note"],
}


def _bbox(cells: list) -> dict:
    return {"y_min": min(c["y"] for c in cells), "y_max": max(c["y"] for c in cells),
            "x_min": min(c["x"] for c in cells), "x_max": max(c["x"] for c in cells)}


def sample(extracted_path: str, analysis_path: str, sizes: dict, seed: int) -> list:
    with open(extracted_path, encoding="utf-8") as fh:
        recs = json.load(fh)
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    rng = random.Random(seed)
    tables = {(r["id"], t.get("number"), t.get("page")): t for r in recs for t in r.get("tables", [])}
    items = []

    def find_cell(t, value, bold):
        for c in t["cells"]:
            if c["bold"] == bold and c["mean"] == value:
                return c
        return None

    for stratum, pool in (("testable", [c for c in cmps if c.get("test")]),
                          ("no_bar", [c for c in cmps if c["winner_dispersion"] is None
                                      and c["runner_dispersion"] is None])):
        for c in rng.sample(pool, min(sizes[stratum], len(pool))):
            t = tables[(c["paper"], c["table"], c["page"])]
            w = find_cell(t, c["winner"], True)
            items.append({"stratum": stratum, "paper": c["paper"], "table": c["table"],
                          "page": c["page"], "bbox": c["bbox"],
                          "mark": {"x": w["x"], "y": w["y"]} if w else None,
                          "pipeline": {k: c.get(k) for k in (
                              "winner", "winner_dispersion", "runner_up", "runner_dispersion",
                              "direction", "orientation", "dispersion_kind", "n_runs",
                              "n_runs_source", "winner_style", "runner_style")},
                          "pipeline_test": c.get("test")})

    discarded, non_ext = [], []
    for r in recs:
        for t in r.get("tables", []):
            cells = t["cells"]
            o = orientation(cells)
            key = {"paper": r["id"], "table": t.get("number"), "page": t.get("page")}
            if o == "none" or not comparisons_from_table(t):
                discarded.append({**key, "bbox": _bbox(cells), "mark": None,
                                  "pipeline": {"n_bold": sum(1 for c in cells if c["bold"]),
                                               "n_cells": len(cells), "orientation": o,
                                               "dispersion_kind": t.get("dispersion_kind")}})
                continue
            for g in (_columns(cells) if o == "column" else _rows(cells)):
                bold = [c for c in g if c["bold"]]
                plain = [c for c in g if not c["bold"]]
                if len(bold) != 1 or not plain:
                    continue
                vals = [c["mean"] for c in g]
                if bold[0]["mean"] not in (max(vals), min(vals)):
                    non_ext.append({**key, "bbox": _bbox(cells),
                                    "mark": {"x": bold[0]["x"], "y": bold[0]["y"]},
                                    "pipeline": {"bold_value": bold[0]["mean"],
                                                 "group_values": sorted(vals),
                                                 "orientation": o}})
    for stratum, pool in (("discarded", discarded), ("non_extremal", non_ext)):
        for it in rng.sample(pool, min(sizes[stratum], len(pool))):
            items.append({"stratum": stratum, **it})

    for i, it in enumerate(items, 1):
        it["id"] = f"{i:03d}"
    return items


def render(items: list, sources: list, out_dir: str, zoom: float = 2.0) -> None:
    index = {}
    for s in sources:
        for rec in SOURCES[s]():
            index[rec["id"]] = rec
    img_dir = os.path.join(out_dir, "img")
    os.makedirs(img_dir, exist_ok=True)
    cache: dict = {}
    for it in items:
        rec = index.get(it["paper"])
        if rec is None:
            it["image"] = None
            continue
        if it["paper"] not in cache:
            try:
                cache[it["paper"]] = _get(rec["pdf"])
            except Exception as exc:  # noqa: BLE001
                print(f"  {it['id']} download failed: {exc}")
                it["image"] = None
                continue
        doc = fitz.open(stream=cache[it["paper"]], filetype="pdf")
        if it["page"] >= len(doc):
            it["image"] = None
            continue
        page = doc[it["page"]]
        b = it["bbox"]
        pad = 26.0
        clip = fitz.Rect(max(0, b["x_min"] - pad * 5.0), max(0, b["y_min"] - pad * 2.8),
                         min(page.rect.width, b["x_max"] + pad * 5.0),
                         min(page.rect.height, b["y_max"] + pad * 1.6))
        if it.get("mark"):
            shape = page.new_shape()
            shape.draw_circle(fitz.Point(it["mark"]["x"] + 8, it["mark"]["y"] + 4), 9)
            shape.finish(color=(1, 0, 0), width=1.2)
            shape.commit()
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        name = f"{it['id']}_{it['stratum']}.png"
        pix.save(os.path.join(img_dir, name))
        it["image"] = name
        it["title"] = rec["title"]
        if it["stratum"] == "testable":
            text = "\n".join(p.get_text() for p in doc)
            sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
            with open(os.path.join(img_dir, f"{it['id']}_runs.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n---\n".join(sents[:40]))
        doc.close()
        print(f"  {it['id']} {it['stratum']:12s} {rec['title'][:50]}")


def _num(x):
    if x is None:
        return None
    s = str(x).strip().lower()
    if s in ("", "none", "na", "n/a", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _match(a, b, tol=1e-6) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def score(items_path: str, labels_path: str) -> dict:
    with open(items_path, encoding="utf-8") as fh:
        items = {it["id"]: it for it in json.load(fh)}
    labels = {}
    with open(labels_path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            labels[row["id"]] = row
    out: dict = {}

    def rate(hits, n, label):
        lo, hi = wilson_interval(hits, n) if n else (0.0, 0.0)
        return {"correct": hits, "n": n, "pct": round(100 * hits / n, 1) if n else None,
                "ci": [round(100 * lo, 1), round(100 * hi, 1)], "what": label}

    # --- testable: field by field
    T = [(items[i], labels[i]) for i in labels if items[i]["stratum"] == "testable"
         and labels[i].get("results_table", "").lower().startswith("y")]
    fields = {}
    n = len(T)
    fields["results_table"] = rate(n, sum(1 for i in labels if items[i]["stratum"] == "testable"),
                                   "the cropped region is a results table")
    fields["bold_cell"] = rate(sum(1 for it, lb in T if lb["bold_ok"].lower().startswith("y")), n,
                               "the circled cell is bold and alone in its group")
    fields["orientation"] = rate(sum(1 for it, lb in T
                                     if lb["orientation"].lower()[:3] == it["pipeline"]["orientation"][:3]), n,
                                 "row/column grouping")
    fields["direction"] = rate(sum(1 for it, lb in T
                                   if lb["direction"].lower()[:3] == it["pipeline"]["direction"][:3]), n,
                               "higher/lower is better")
    for f, key in (("winner_mean", "winner"), ("winner_disp", "winner_dispersion"),
                   ("runner_mean", "runner_up"), ("runner_disp", "runner_dispersion")):
        fields[f] = rate(sum(1 for it, lb in T if _match(_num(lb[f]), it["pipeline"][key])), n, f)
    kind_map = {"sd": "std", "se": "sem", "ci": "ci", "unlabelled": "unknown", "unknown": "unknown"}
    fields["disp_type"] = rate(sum(1 for it, lb in T
                                   if kind_map.get(lb["disp_type"].lower(), lb["disp_type"].lower())
                                   == it["pipeline"]["dispersion_kind"]), n,
                               "what the error bar is (SD, SE, CI, unlabelled)")
    fields["n_runs"] = rate(sum(1 for it, lb in T if _match(_num(lb["n_runs"]), it["pipeline"]["n_runs"])), n,
                            "the run count")
    all_ok = sum(1 for it, lb in T
                 if lb["bold_ok"].lower().startswith("y")
                 and all(_match(_num(lb[f]), it["pipeline"][k]) for f, k in (
                     ("winner_mean", "winner"), ("winner_disp", "winner_dispersion"),
                     ("runner_mean", "runner_up"), ("runner_disp", "runner_dispersion"),
                     ("n_runs", "n_runs"))))
    fields["every_field"] = rate(all_ok, n, "all of the above at once")

    # failure rate on the gold subset, from the reader's values vs the pipeline's
    fail_reader = fail_pipe = n_both = 0
    for it, lb in T:
        r = dict(it["pipeline"])
        c = {"gap": None, "winner_dispersion": _num(lb["winner_disp"]),
             "runner_dispersion": _num(lb["runner_disp"]),
             "dispersion_kind": kind_map.get(lb["disp_type"].lower(), "unknown"),
             "n_runs": _num(lb["n_runs"])}
        wm, rm = _num(lb["winner_mean"]), _num(lb["runner_mean"])
        if wm is None or rm is None:
            continue
        c["gap"] = abs(wm - rm)
        if c["n_runs"]:
            c["n_runs"] = int(c["n_runs"])
        t_reader = test_comparison(c)
        t_pipe = it.get("pipeline_test")
        if t_reader and t_pipe:
            n_both += 1
            fail_reader += t_reader["p"] >= 0.05
            fail_pipe += t_pipe["p"] >= 0.05
    out["testable"] = {"n_labelled": len(T), "fields": fields,
                       "failure_rate_reader_values": round(100 * fail_reader / n_both, 1) if n_both else None,
                       "failure_rate_pipeline_values_same_items": round(100 * fail_pipe / n_both, 1) if n_both else None,
                       "n_testable_under_both": n_both,
                       "reader_says_not_testable": sum(1 for it, lb in T if not test_comparison({
                           "gap": 1.0, "winner_dispersion": _num(lb["winner_disp"]),
                           "runner_dispersion": _num(lb["runner_disp"]),
                           "dispersion_kind": kind_map.get(lb["disp_type"].lower(), "unknown"),
                           "n_runs": int(_num(lb["n_runs"]) or 0) or None}))}

    # --- no_bar
    B = [(items[i], labels[i]) for i in labels if items[i]["stratum"] == "no_bar"]
    Br = [(it, lb) for it, lb in B if lb.get("results_table", "").lower().startswith("y")]
    out["no_bar"] = {
        "n": len(B),
        "results_table": rate(len(Br), len(B), "results table"),
        "error_bar_truly_absent": rate(sum(1 for it, lb in Br
                                           if not lb["error_bar_present"].lower().startswith("y")),
                                       len(Br), "no error bar on either cell, as the pipeline said"),
        "bold_cell": rate(sum(1 for it, lb in Br if lb["bold_ok"].lower().startswith("y")), len(Br),
                          "circled cell bold and alone in its group"),
        "winner_mean": rate(sum(1 for it, lb in Br if _match(_num(lb["winner_mean"]), it["pipeline"]["winner"])),
                            len(Br), "winner value"),
        "runner_mean": rate(sum(1 for it, lb in Br if _match(_num(lb["runner_mean"]), it["pipeline"]["runner_up"])),
                            len(Br), "runner-up value"),
        "direction": rate(sum(1 for it, lb in Br
                              if lb["direction"].lower()[:3] == it["pipeline"]["direction"][:3]), len(Br),
                          "direction"),
    }

    # --- discarded and non_extremal: cause breakdown
    for stratum in ("discarded", "non_extremal"):
        S = [labels[i] for i in labels if items[i]["stratum"] == stratum]
        causes: dict = {}
        for lb in S:
            causes[lb["cause"].strip().lower()] = causes.get(lb["cause"].strip().lower(), 0) + 1
        out[stratum] = {"n": len(S), "causes": dict(sorted(causes.items(), key=lambda kv: -kv[1])),
                        "pct": {k: round(100 * v / len(S), 1) for k, v in causes.items()} if S else {}}
        if stratum == "discarded":
            miss = causes.get("bold_missed", 0) + causes.get("parse_error", 0)
            out[stratum]["extractor_at_fault"] = rate(miss, len(S), "bold missed or parse error")
        else:
            miss = causes.get("parse_error", 0) + causes.get("misread", 0)
            out[stratum]["extractor_at_fault"] = rate(miss, len(S), "parse error or orientation/direction misread")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--extracted", default="data/extracted_2025.json")
    s.add_argument("--analysis", default="out/analysis_2025.json")
    s.add_argument("--source", action="append", default=["neurips2025", "icml2025"])
    s.add_argument("--seed", type=int, default=2027)
    s.add_argument("--testable", type=int, default=100)
    s.add_argument("--no-bar", type=int, default=40)
    s.add_argument("--discarded", type=int, default=40)
    s.add_argument("--non-extremal", type=int, default=40)
    s.add_argument("--out-dir", default="out/gold")
    sc = sub.add_parser("score")
    sc.add_argument("--items", default="out/gold/items.json")
    sc.add_argument("--labels", default="out/gold/labels.csv")
    sc.add_argument("--out", default="out/gold_set.json")
    args = ap.parse_args(argv)

    if args.cmd == "sample":
        sizes = {"testable": args.testable, "no_bar": args.no_bar,
                 "discarded": args.discarded, "non_extremal": args.non_extremal}
        items = sample(args.extracted, args.analysis, sizes, args.seed)
        os.makedirs(args.out_dir, exist_ok=True)
        render(items, args.source, args.out_dir)
        with open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8") as fh:
            json.dump(items, fh, indent=1)
        # The answer sheet, with only the id and stratum filled in.
        with open(os.path.join(args.out_dir, "labels_template.csv"), "w", encoding="utf-8", newline="") as fh:
            cols = ["id", "stratum"] + sorted({f for fs in FIELDS.values() for f in fs})
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for it in items:
                w.writerow({"id": it["id"], "stratum": it["stratum"]})
        print(f"{len(items)} items -> {args.out_dir}")
        return 0
    res = score(args.items, args.labels)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
