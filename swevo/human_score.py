"""Score the human labels on the separate-column kit against the reader:
field by field (bold cell confirmed, winner mean and deviation, runner mean
and deviation, run count), the whole claim, and how many Welch verdicts
change when the human's values replace the reader's.

Usage: python swevo/human_score.py  (reads audits/swevo_human/labels.csv)
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from paperengine.stats import wilson_interval  # noqa: E402
from pages_score import _bar_num, _se  # noqa: E402
from gold_set import _num, _match  # noqa: E402
from analyze import p_value  # noqa: E402

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--kit", default="audits/swevo_human")
_ap.add_argument("--out", default=None)
_ap.add_argument("--labels", default=None, help="a labels file other than the kit's labels.csv (a model's answers to the kit)")
_args, _ = _ap.parse_known_args()
KIT = _args.kit
LABELS = _args.labels or os.path.join(KIT, "labels.csv")
_tag = "" if _args.labels is None else "_" + os.path.basename(_args.labels).replace("labels_", "").replace(".csv", "")
OUT = _args.out or (("out/swevo/human_rows" if KIT.endswith("_rows") else "out/swevo/human_separate") + _tag + ".json")
sys.path.insert(0, HERE)
from census_readings import _disp, _disp_str  # noqa: E402
import re as _re


def _clean(v):
    """A typed value with a Unicode minus or a space after the sign."""
    x = str(v if v is not None else "").replace("−", "-").replace("–", "-")
    return _re.sub(r"^([+-])\s+", r"\1", x.strip())


def _rate(k, n):
    lo, hi = wilson_interval(k, n) if n else (0, 0)
    return {"correct": k, "n": n, "pct": round(100 * k / n, 1) if n else None, "ci": [round(100 * lo, 1), round(100 * hi, 1)]}


def main() -> int:
    path = LABELS
    if not os.path.exists(path):
        print("no human labels yet:", path)
        return 0
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    # a row counts as labelled only if some answer field is filled; a note alone (a model's "failed: ...") is not an answer
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8", newline="")) if any(v.strip() for k, v in r.items() if k not in ("id", "note"))]
    fields = {"winner_mean": [0, 0], "winner_disp": [0, 0], "runner_mean": [0, 0], "runner_disp": [0, 0], "n_runs": [0, 0]}
    recall = {"std_printed_y": 0, "std_printed_y_reader_barred": 0, "std_printed_n": 0, "std_printed_n_reader_barred": 0}
    bold_ok = [0, 0]
    whole_row = [0, 0]  # the added question: every bold cell of the table in one row or column
    results = [0, 0]
    claim = [0, 0]
    flips = [0, 0]
    unclear = 0
    pages = {}
    for r in rows:
        it = items[r["id"]]
        rd = it["reader"]
        if str(r.get("results_table", "")).strip().lower().startswith("n"):
            results[1] += 1
            continue
        results[0] += 1; results[1] += 1
        sp = str(r.get("std_printed", "")).strip().lower()
        if sp:
            reader_barred = _disp(rd.get("winner_disp")) is not None and _disp(rd.get("runner_disp")) is not None
            if sp.startswith("y"):
                recall["std_printed_y"] += 1
                recall["std_printed_y_reader_barred"] += reader_barred
            else:
                recall["std_printed_n"] += 1
                recall["std_printed_n_reader_barred"] += reader_barred
        bold_ok[1] += 1
        bold_ok[0] += str(r.get("bold_ok", "")).strip().lower().startswith("y")
        wr = str(r.get("whole_row_bold", "")).strip().lower()
        if wr:
            whole_row[1] += 1
            whole_row[0] += wr.startswith("y")
        if any(str(r.get(f, "")).strip().lower() == "unclear" for f in fields):
            unclear += 1
        ok_all = str(r.get("bold_ok", "")).strip().lower().startswith("y")
        for f in fields:
            h = str(r.get(f, "")).strip()
            if not h or h.lower() == "unclear":
                continue
            fields[f][1] += 1
            if f == "n_runs":
                a, b = _num(h), _num(it.get("n_runs_reader"))
                hit = (a is not None and b is not None and a == b) or (h.lower() == "none" and str(it.get("n_runs_reader", "")).lower() in ("", "none"))
            elif f.endswith("_disp"):
                hit = _match(_disp(_clean(h)), _disp(_clean(rd.get(f))))
            else:
                hit = _match(_num(_clean(h)), _num(_clean(rd.get(f))))
            fields[f][0] += hit
            if f != "n_runs":
                ok_all = ok_all and hit
        claim[1] += 1
        claim[0] += ok_all
        # verdict under the human's values against the reader's
        kind = str(it.get("bar_kind", "")).lower()
        n_r = _num(it.get("n_runs_reader"))
        n_h = _num(r.get("n_runs")) or n_r
        def verdict(w, wd, rm, rdd, n):
            w, rm = _num(w), _num(rm)
            sw, sr = _se(_disp_str(wd), kind, n), _se(_disp_str(rdd), kind, n)
            if None in (w, rm, sw, sr):
                return None
            res = p_value(abs(w - rm), sw, sr, int(n) if n else None)
            return (res["p"] >= 0.05) if res else None
        v_r = verdict(rd["winner_mean"], rd["winner_disp"], rd["runner_mean"], rd["runner_disp"], n_r)
        v_h = verdict(_clean(r.get("winner_mean")), _clean(r.get("winner_disp")), _clean(r.get("runner_mean")), _clean(r.get("runner_disp")), n_h)
        if v_r is not None and v_h is not None:
            flips[1] += 1
            flips[0] += (v_r != v_h)
        pages.setdefault(it["page_id"], [0, 0])
        pages[it["page_id"]][1] += 1
        pages[it["page_id"]][0] += ok_all
    # a page-resampled interval for the whole claim
    import random
    rng = random.Random(0)
    keys = list(pages)
    vals = []
    for _ in range(2000):
        draw = [pages[keys[rng.randrange(len(keys))]] for _ in keys]
        k, n = sum(x[0] for x in draw), sum(x[1] for x in draw)
        vals.append(100 * k / n if n else 0)
    vals.sort()
    out = {"labels": LABELS, "labelled": len(rows), "results_table": _rate(*results), "bold_ok": _rate(*bold_ok),
           "whole_row_bold": _rate(*whole_row),
           "fields": {f: _rate(*v) for f, v in fields.items()}, "claim": _rate(*claim),
           "claim_page_ci": [round(vals[50], 1), round(vals[1949], 1)], "pages": len(pages),
           "verdict_flips": _rate(*flips), "unclear_items": unclear,
           "recall": dict(recall, reader_recall=_rate(recall["std_printed_y_reader_barred"], recall["std_printed_y"]),
                          reader_false_bar=_rate(recall["std_printed_n_reader_barred"], recall["std_printed_n"])),
           "by_stratum": {st: {"n": sum(1 for r in rows if items[r["id"]].get("stratum") == st)} for st in {items[r["id"]].get("stratum", "") for r in rows}}}
    os.makedirs("out/swevo", exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(json.dumps(out, indent=None)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
