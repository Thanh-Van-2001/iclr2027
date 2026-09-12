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

from analyze import (_columns, _rows, comparisons_from_table, load_records,  # noqa: E402
                     orientation, test_comparison)
from harvest import SOURCES, _get  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

RUN_SENTENCE = re.compile(
    r"(?i)[^.\n]{0,160}\b(?:seeds?|runs?|trials?|repetitions?|replicates?|repeat(?:ed|s)?|"
    r"times|folds?|initiali[sz]ations?|restarts?|rollouts?|episodes|independent experiments)\b[^.\n]{0,160}")

FIELDS = {
    "testable": ["results_table", "bold_ok", "orientation", "direction", "winner_mean",
                 "winner_disp", "runner_mean", "runner_disp", "disp_type", "n_runs",
                 "n_source", "rival_copied", "note"],
    "no_bar": ["results_table", "bold_ok", "orientation", "direction", "winner_mean",
               "runner_mean", "error_bar_present", "note"],
    "discarded": ["results_table", "cause", "note"],
    "non_extremal": ["results_table", "cause", "note"],
    "no_n": ["results_table", "n_runs", "n_source", "note"],
    # no error bar on either cell, but a run count attached from the paper:
    # does the paper state that count for this table's experiment?
    "no_bar_n": ["results_table", "n_runs", "n_source", "note"],
}


def _bbox(cells: list) -> dict:
    return {"y_min": min(c["y"] for c in cells), "y_max": max(c["y"] for c in cells),
            "x_min": min(c["x"] for c in cells), "x_max": max(c["x"] for c in cells)}


def sample(extracted_path: str, analysis_path: str, sizes: dict, seed: int,
           exclude_papers: set = frozenset()) -> list:
    recs = load_records(extracted_path)
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    # A held-out draw never touches a paper the development set saw.
    recs = [r for r in recs if r["id"] not in exclude_papers]
    cmps = [c for c in cmps if c["paper"] not in exclude_papers]
    rng = random.Random(seed)
    tables = {(r["id"], t.get("number"), t.get("page")): t for r in recs for t in r.get("tables", [])}
    items = []

    def find_cell(t, value, disp, bold):
        # Mean and dispersion together: a table can hold the same bold mean
        # twice (0.99 in four rows of success rates), and marking the first
        # one circled the wrong claim in four of the first hundred items.
        for c in t["cells"]:
            if c["bold"] == bold and c["mean"] == value and c["dispersion"] == disp:
                return c
        for c in t["cells"]:
            if c["bold"] == bold and c["mean"] == value:
                return c
        return None

    for stratum, pool in (("testable", [c for c in cmps if c.get("test")]),
                          ("no_bar", [c for c in cmps if c["winner_dispersion"] is None
                                      and c["runner_dispersion"] is None]),
                          # both bars printed, no run count found anywhere: does the
                          # paper state one the pattern does not match?
                          ("no_n", [c for c in cmps if c["winner_dispersion"] is not None
                                    and c["runner_dispersion"] is not None
                                    and not c.get("n_runs") and not c.get("test")]),
                          ("no_bar_n", [c for c in cmps if c["winner_dispersion"] is None
                                        and c["runner_dispersion"] is None and c.get("n_runs")])):
        for c in rng.sample(pool, min(sizes.get(stratum, 0), len(pool))):
            t = tables[(c["paper"], c["table"], c["page"])]
            w = find_cell(t, c["winner"], c["winner_dispersion"], True)
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
            # The first renderings drew a circle over the cell, and the circle
            # covered the digits being audited in a third of the items. A box
            # drawn around the cell with a margin marks it without touching it.
            shape = page.new_shape()
            x, y = it["mark"]["x"], it["mark"]["y"]
            shape.draw_rect(fitz.Rect(x - 4, y - 3, x + 30, y + 11))
            shape.finish(color=(1, 0, 0), width=0.9)
            shape.commit()
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        name = f"{it['id']}_{it['stratum']}.png"
        pix.save(os.path.join(img_dir, name))
        it["image"] = name
        it["title"] = rec["title"]
        if it["stratum"] in ("testable", "no_n", "no_bar_n"):
            text = "\n".join(p.get_text() for p in doc)
            sents = sorted({m.group(0).strip() for m in RUN_SENTENCE.finditer(text)})
            with open(os.path.join(img_dir, f"{it['id']}_runs.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n---\n".join(sents[:40]))
            if it["stratum"] in ("no_n", "no_bar_n"):
                # The residual run-count miss is measured against the whole paper,
                # not against the sentences the pattern already selects.
                with open(os.path.join(img_dir, f"{it['id']}_fulltext.txt"), "w", encoding="utf-8") as fh:
                    fh.write(text)
        doc.close()
        title = rec["title"][:50].encode("ascii", "replace").decode()
        print(f"  {it['id']} {it['stratum']:12s} {title}")


def _pipeline_test(it: dict):
    p = it.get("pipeline") or {}
    if p.get("winner") is None or p.get("runner_up") is None:
        return it.get("pipeline_test")
    c = {"gap": abs(p["winner"] - p["runner_up"]),
         "winner_dispersion": p.get("winner_dispersion"),
         "runner_dispersion": p.get("runner_dispersion"),
         "dispersion_kind": p.get("dispersion_kind") or "unknown",
         "n_runs": p.get("n_runs")}
    try:
        return test_comparison(c)
    except Exception:  # noqa: BLE001
        return it.get("pipeline_test")


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


def _unclear(v) -> bool:
    """A cell the reader could not read (the circle covered it, or two rivals
    tied) is left out of that field's denominator rather than scored."""
    return str(v).strip().lower() == "unclear"


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
    # Labels whose item is absent (a rescore drops claims the new pipeline no
    # longer makes) are skipped, not scored.
    labels = {i: lb for i, lb in labels.items() if i in items}
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
        clear = [(it, lb) for it, lb in T if not _unclear(lb[f])]
        fields[f] = rate(sum(1 for it, lb in clear if _match(_num(lb[f]), it["pipeline"][key])),
                         len(clear), f)
    kind_map = {"sd": "std", "se": "sem", "ci": "ci", "unlabelled": "unknown", "unknown": "unknown"}
    fields["disp_type"] = rate(sum(1 for it, lb in T
                                   if kind_map.get(lb["disp_type"].lower(), lb["disp_type"].lower())
                                   == it["pipeline"]["dispersion_kind"]), n,
                               "what the error bar is (SD, SE, CI, unlabelled)")
    # What the test actually consumes: an unlabelled bar is read as a standard
    # deviation, so "unlabelled" and "SD" are the same treatment, and the
    # material disagreement is SD-or-unlabelled against SE-or-CI.

    def treatment(kind):
        return "se_like" if kind in ("sem", "ci") else "sd_like"

    fields["disp_treatment"] = rate(sum(1 for it, lb in T
                                        if treatment(kind_map.get(lb["disp_type"].lower(), "unknown"))
                                        == treatment(it["pipeline"]["dispersion_kind"])), n,
                                    "SD-or-unlabelled versus SE-or-CI, which is what the test uses")
    clear_n = [(it, lb) for it, lb in T if not _unclear(lb["n_runs"])]
    fields["n_runs"] = rate(sum(1 for it, lb in clear_n
                                if _match(_num(lb["n_runs"]), it["pipeline"]["n_runs"])),
                            len(clear_n), "the run count")
    with_n = [(it, lb) for it, lb in clear_n if _num(lb["n_runs"]) is not None]
    fields["n_runs_when_reader_found_one"] = rate(
        sum(1 for it, lb in with_n if _match(_num(lb["n_runs"]), it["pipeline"]["n_runs"])),
        len(with_n), "the run count, on items where the reader found one")
    fields["reader_found_no_run_count"] = rate(
        sum(1 for it, lb in clear_n if _num(lb["n_runs"]) is None), len(clear_n),
        "items where the reader found no run count in the paper")
    value_fields = (("winner_mean", "winner"), ("winner_disp", "winner_dispersion"),
                    ("runner_mean", "runner_up"), ("runner_disp", "runner_dispersion"))
    # An item with a value the reader could not read is left out of this
    # denominator rather than counted as agreed; the earlier version counted
    # it, which a reviewer rightly called optimistic.
    readable = [(it, lb) for it, lb in T if not any(_unclear(lb[f]) for f, _ in value_fields)]
    all_ok = sum(1 for it, lb in readable
                 if lb["bold_ok"].lower().startswith("y")
                 and all(_match(_num(lb[f]), it["pipeline"][k]) for f, k in value_fields))
    fields["claim_and_values"] = rate(all_ok, len(readable),
                                      "bold cell, rival and all four values at once, on fully readable items")
    # The same agreement with an interval that resamples papers, because a
    # draw of comparisons lands several items in one paper, and the largest
    # share of disagreements any single paper contributes.
    def _claim_ok(it, lb):
        return (lb["bold_ok"].lower().startswith("y")
                and all(_match(_num(lb[f]), it["pipeline"][k]) for f, k in value_fields))
    by_paper: dict = {}
    for it, lb in readable:
        by_paper.setdefault(it["paper"], []).append(_claim_ok(it, lb))
    papers = list(by_paper.values())
    rng = random.Random(0)
    boots = []
    for _ in range(2000):
        draw = [papers[rng.randrange(len(papers))] for _ in papers]
        flat = [x for pp in draw for x in pp]
        boots.append(100 * sum(flat) / max(len(flat), 1))
    boots.sort()
    fields["claim_and_values"]["paper_ci"] = [round(boots[50], 1), round(boots[1949], 1)]
    fields["claim_and_values"]["n_papers"] = len(papers)
    dis = {k: sum(1 for x in v if not x) for k, v in by_paper.items()}
    fields["claim_and_values"]["n_disagreements"] = sum(dis.values())
    fields["claim_and_values"]["max_disagreements_one_paper"] = max(dis.values()) if dis else 0
    if "rival_copied" in (T[0][1] if T else {}):
        fields["rival_copied"] = rate(sum(1 for it, lb in T if lb["rival_copied"].lower().startswith("y")),
                                      sum(1 for it, lb in T if lb["rival_copied"].lower() in ("y", "n")),
                                      "the runner-up carries a citation, dagger or 'from' marker")
    fields["claim_or_unreadable"] = rate(
        sum(1 for it, lb in T if lb["bold_ok"].lower().startswith("y")
            and all(_unclear(lb[f]) or _match(_num(lb[f]), it["pipeline"][k]) for f, k in value_fields)),
        n, "the same, counting an unreadable value as not contradicted")

    # failure rate on the gold subset, from the reader's values vs the pipeline's,
    # and the per-item 2x2 of verdicts, which is what agreement means; the two
    # marginal rates can match while every verdict flips.
    fail_reader = fail_pipe = n_both = 0
    both_fail = both_pass = reader_fail_only = pipe_fail_only = 0
    for it, _ in T:
        # The verdict is recomputed from the pipeline's values with the paper's
        # current test, so a change of test (z to Welch) reaches the audit too.
        it["pipeline_test"] = _pipeline_test(it)
    pipe_fail_all = sum(1 for it, lb in T if it.get("pipeline_test") and it["pipeline_test"]["p"] >= 0.05)
    pipe_tested_all = sum(1 for it, lb in T if it.get("pipeline_test"))
    # Why the reader could not test an item the pipeline did: the boxed cell is
    # not a single bold (so there is no claim to test), a value is unreadable,
    # or the bars carry no usable run count. Each carries the pipeline's verdict.
    untestable: dict = {}
    for it, lb in T:
        r = dict(it["pipeline"])
        c = {"gap": None, "winner_dispersion": _num(lb["winner_disp"]),
             "runner_dispersion": _num(lb["runner_disp"]),
             "dispersion_kind": kind_map.get(lb["disp_type"].lower(), "unknown"),
             "n_runs": _num(lb["n_runs"])}
        wm, rm = _num(lb["winner_mean"]), _num(lb["runner_mean"])
        t_pipe = it.get("pipeline_test")
        is_claim = lb["bold_ok"].lower().startswith("y")
        t_reader = None
        if wm is not None and rm is not None:
            c["gap"] = abs(wm - rm)
            if c["n_runs"]:
                c["n_runs"] = int(c["n_runs"])
            t_reader = test_comparison(c)
        if t_pipe and not (t_reader and is_claim):
            why = ("not a single bold cell" if not is_claim else
                   "a value unreadable" if wm is None or rm is None else
                   "no usable bar or run count")
            d_ = untestable.setdefault(why, {"n": 0, "pipeline_fails": 0, "papers": set()})
            d_["n"] += 1
            d_["pipeline_fails"] += t_pipe["p"] >= 0.05
            d_["papers"].add(it["paper"])
            continue
        if t_reader and t_pipe:
            n_both += 1
            rf, pf = t_reader["p"] >= 0.05, t_pipe["p"] >= 0.05
            fail_reader += rf
            fail_pipe += pf
            both_fail += rf and pf
            both_pass += (not rf) and (not pf)
            reader_fail_only += rf and not pf
            pipe_fail_only += pf and not rf
    for d_ in untestable.values():
        d_["papers"] = len(d_["papers"])
    out["testable"] = {"n_labelled": len(T), "fields": fields,
                       "reader_untestable": untestable,
                       "verdict_2x2": {"both_fail": both_fail, "both_survive": both_pass,
                                       "reader_fail_pipeline_survive": reader_fail_only,
                                       "pipeline_fail_reader_survive": pipe_fail_only,
                                       "per_item_agreement": round(100 * (both_fail + both_pass) / n_both, 1) if n_both else None},
                       "pipeline_fail_rate_all_items": round(100 * pipe_fail_all / pipe_tested_all, 1) if pipe_tested_all else None,
                       "pipeline_tested_all_items": pipe_tested_all,
                       "pipeline_fail_all_items": pipe_fail_all,
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

    # --- no_n: run-count recall
    N = [labels[i] for i in labels if items[i]["stratum"] == "no_n"]
    if N:
        found = sum(1 for lb in N if _num(lb["n_runs"]) is not None)
        out["no_n"] = {"n": len(N),
                       "reader_found_a_run_count": rate(found, len(N),
                                                        "the paper states a run count the pattern missed"),
                       "pipeline_right_that_none_is_stated": rate(len(N) - found, len(N),
                                                                  "no run count anywhere in the paper"),
                       "sources": dict(sorted(__import__("collections").Counter(
                           lb["n_source"].strip().lower() for lb in N if _num(lb["n_runs"]) is not None).items()))}

    # --- no_bar_n: does the run count the pipeline attached to a bar-less
    # table apply to it? The reader, given the whole paper, states the count
    # that applies (or none); agreement with the pipeline's count is the
    # precision of attachment on the population Section 6 rests on.
    B = [(items[i], labels[i]) for i in labels if items[i]["stratum"] == "no_bar_n"]
    if B:
        with_pipe = [(it, lb) for it, lb in B if it["pipeline"].get("n_runs")]
        agree = sum(1 for it, lb in with_pipe
                    if _num(lb["n_runs"]) is not None and int(_num(lb["n_runs"])) == int(it["pipeline"]["n_runs"]))
        reader_none = sum(1 for it, lb in with_pipe if _num(lb["n_runs"]) is None)
        other = len(with_pipe) - agree - reader_none
        out["no_bar_n"] = {"n": len(B),
                           "attached_count_applies": rate(agree, len(with_pipe),
                                                          "the paper states the pipeline's count for this table"),
                           "reader_found_none": rate(reader_none, len(with_pipe),
                                                     "the paper states no count for this table"),
                           "reader_found_a_different_count": rate(other, len(with_pipe),
                                                                  "the paper states another count for this table"),
                           "by_source": {}}
        for src in ("caption", "page", None):
            sub = [(it, lb) for it, lb in with_pipe if it["pipeline"].get("n_runs_source") == src]
            ok = sum(1 for it, lb in sub
                     if _num(lb["n_runs"]) is not None and int(_num(lb["n_runs"])) == int(it["pipeline"]["n_runs"]))
            out["no_bar_n"]["by_source"][src or "paper"] = rate(ok, len(sub), "count applies, by where it was read")

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


def rescore(items_path: str, labels_path: str, analysis_path: str, tol: float = 3.0) -> dict:
    """Score a later pipeline on the claims of an existing gold set.

    The development set was used to find bugs, so its post-fix accuracy is
    optimistic and is reported as such; the point of this function is to say
    what the fixes did to the very items that exposed them. Each item is
    matched to the comparison the new pipeline makes for the same bold cell
    (same paper, table, page, and cell position); an item with no such
    comparison is "no longer extracted", which is the right outcome when the
    reader had marked the bold cell as not alone in its group.
    """
    with open(items_path, encoding="utf-8") as fh:
        items = {it["id"]: it for it in json.load(fh)}
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    with open(labels_path, encoding="utf-8", newline="") as fh:
        labels = {r["id"]: r for r in csv.DictReader(fh)}
    by_table: dict = {}
    for c in cmps:
        by_table.setdefault((c["paper"], c["table"], c["page"]), []).append(c)

    new_items = []
    dropped, dropped_rightly = 0, 0
    for i, it in items.items():
        if it["stratum"] != "testable" or i not in labels or not it.get("mark"):
            continue
        lb = labels[i]
        found = None
        cands = by_table.get((it["paper"], it["table"], it["page"]), [])
        # The same claim is the same bold cell: match on its printed value
        # first (an extractor change can shift a cell's coordinates by a few
        # points), then on position if the value occurs twice.
        p = it["pipeline"]
        same = [c for c in cands if c["winner"] == p["winner"]
                and c["winner_dispersion"] == p["winner_dispersion"]]
        if len(same) == 1:
            found = same[0]
        else:
            for c in same or cands:
                w = c.get("winner_cell") or {}
                if abs(w.get("x", 1e9) - it["mark"]["x"]) <= tol and abs(w.get("y", 1e9) - it["mark"]["y"]) <= tol:
                    found = c
                    break
        if found is None or not found.get("test"):
            dropped += 1
            if not lb["bold_ok"].lower().startswith("y") or lb["runner_disp"].strip().lower() == "none":
                dropped_rightly += 1
            continue
        new_items.append({**it, "pipeline": {k: found.get(k) for k in it["pipeline"]},
                          "pipeline_test": found.get("test")})
    tmp_items = items_path + ".rescored.json"
    with open(tmp_items, "w", encoding="utf-8") as fh:
        json.dump(new_items, fh)
    res = score(tmp_items, labels_path)
    os.unlink(tmp_items)
    res["testable"]["no_longer_extracted"] = dropped
    res["testable"]["no_longer_extracted_and_reader_agreed"] = dropped_rightly
    return res


def recall_under(manifest_path: str, analysis_path: str) -> dict:
    """Score the recall audit against the pipeline as it now stands.

    The audit was drawn from tables one version of the pipeline called
    empty. A later version that reads the bars the audit found no longer
    calls those tables empty, so its recall is scored on the judged tables
    it still calls empty: a table the reader marked as missed and the new
    pipeline still misses counts against it; one it now reads does not.
    """
    with open(manifest_path, encoding="utf-8") as fh:
        sheets = json.load(fh)
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    seen, with_bar = set(), set()
    for c in cmps:
        key = (c["paper"], str(c["table"]), c["page"])
        seen.add(key)
        if c["winner_dispersion"] is not None or c["runner_dispersion"] is not None:
            with_bar.add(key)
    entries = [e for sh in sheets for e in sh["entries"] if e.get("verdict")]

    def key_of(e):
        return (e["paper"], str(e["table"]), e["page"])
    # Three fates for a judged table under the current pipeline: it now reads
    # a bar (the fixed misses), it yields no claim at all any more (ties,
    # top-k captions, block rules) and so leaves the population, or it is
    # still called empty, which is where recall is scored.
    reads_bar = [e for e in entries if key_of(e) in with_bar]
    dropped = [e for e in entries if key_of(e) not in seen]
    still = [e for e in entries if key_of(e) in seen and key_of(e) not in with_bar]
    agree = sum(1 for e in still if e["verdict"] == "agree")
    missed = sum(1 for e in still if e["verdict"] == "missed")
    lo, hi = wilson_interval(agree, len(still)) if still else (0.0, 1.0)
    return {"n_judged": len(entries), "n_still_called_empty": len(still),
            "agree": agree, "extractor_missed_an_error_bar": missed,
            "now_reads_a_bar": len(reads_bar),
            "now_reads_a_bar_that_the_reader_saw": sum(1 for e in reads_bar if e["verdict"] == "missed"),
            "dropped_from_population": len(dropped),
            "no_longer_called_empty": len(entries) - len(still),
            "missed_in_the_audited_version": sum(1 for e in entries if e["verdict"] == "missed"),
            "recall_on_no_error_bar_calls": round(agree / len(still), 3) if still else None,
            "wilson_95": [round(lo, 3), round(hi, 3)]}


def agree(path_a: str, path_b: str) -> dict:
    """Field-by-field agreement between two label files on the items both hold.

    Meant for a human reading against the model's reading of the same
    renderings: the number a reviewer asks for when the reference labels come
    from a model.
    """
    def load(path):
        with open(path, encoding="utf-8", newline="") as fh:
            return {r["id"]: r for r in csv.DictReader(fh) if any(v.strip() for k, v in r.items() if k not in ("id", "stratum"))}
    A, B = load(path_a), load(path_b)
    ids = sorted(set(A) & set(B))
    out = {"items": len(ids)}
    def _asked(a, b):
        # a field neither reader filled (a stratum that does not ask for it) is not a comparison
        return bool(a.strip() or b.strip())

    for f in ("bold_ok", "orientation", "direction", "disp_type"):
        pairs = [(A[i][f].strip().lower()[:3], B[i][f].strip().lower()[:3]) for i in ids
                 if _asked(A[i][f], B[i][f]) and not _unclear(A[i][f]) and not _unclear(B[i][f])]
        hit = sum(1 for a, b in pairs if a == b)
        out[f] = {"n": len(pairs), "agree": hit, "pct": round(100 * hit / len(pairs), 1) if pairs else None}
    for f in ("winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs"):
        pairs = [(_num(A[i][f]), _num(B[i][f])) for i in ids
                 if _asked(A[i][f], B[i][f]) and not _unclear(A[i][f]) and not _unclear(B[i][f])]
        hit = sum(1 for a, b in pairs if _match(a, b))
        out[f] = {"n": len(pairs), "agree": hit, "pct": round(100 * hit / len(pairs), 1) if pairs else None}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--extracted", default="data/extracted_2025.jsonl")
    s.add_argument("--analysis", default="out/analysis_2025.json")
    s.add_argument("--source", action="append", default=["neurips2025", "icml2025"])
    s.add_argument("--seed", type=int, default=2027)
    s.add_argument("--testable", type=int, default=100)
    s.add_argument("--no-bar", type=int, default=40)
    s.add_argument("--discarded", type=int, default=40)
    s.add_argument("--non-extremal", type=int, default=40)
    s.add_argument("--no-n", type=int, default=0)
    s.add_argument("--no-bar-n", type=int, default=0)
    s.add_argument("--out-dir", default="out/gold")
    s.add_argument("--exclude-items", action="append", default=None,
                   help="items.json of an earlier draw whose papers are held out (repeatable)")
    sc = sub.add_parser("score")
    sc.add_argument("--items", default="out/gold/items.json")
    sc.add_argument("--labels", default="out/gold/labels.csv")
    sc.add_argument("--out", default="out/gold_set.json")
    sc.add_argument("--rescore-with", default=None,
                    help="analysis JSON of a later pipeline to score on the same claims")
    ag = sub.add_parser("agree")
    ag.add_argument("--a", required=True)
    ag.add_argument("--b", required=True)
    rc = sub.add_parser("recall")
    rc.add_argument("--manifest", default="audits/recall/manifest.json")
    rc.add_argument("--analysis", default="out/analysis_2025.json")
    rc.add_argument("--out", default="out/recall_v4.json")
    args = ap.parse_args(argv)

    if args.cmd == "agree":
        print(json.dumps(agree(args.a, args.b), indent=1))
        return 0
    if args.cmd == "recall":
        res = recall_under(args.manifest, args.analysis)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
        print(json.dumps(res, indent=1))
        return 0

    if args.cmd == "sample":
        sizes = {"testable": args.testable, "no_bar": args.no_bar,
                 "discarded": args.discarded, "non_extremal": args.non_extremal,
                 "no_n": args.no_n, "no_bar_n": args.no_bar_n}
        exclude = set()
        for path in args.exclude_items or []:
            with open(path, encoding="utf-8") as fh:
                exclude |= {it["paper"] for it in json.load(fh)}
        items = sample(args.extracted, args.analysis, sizes, args.seed, exclude)
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
    res = (rescore(args.items, args.labels, args.rescore_with) if args.rescore_with
           else score(args.items, args.labels))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
