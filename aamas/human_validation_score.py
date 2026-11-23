"""Score the independent human-validation kits of the AAMAS paper (submission 3154).

Inputs (nothing else is read; no network, no model, no PDF):
  audits/human_aamas/<kit>/raw/*.csv        one file per annotator, exported by the kit's label.html
  audits/human_aamas/annotators.csv         who is primary / second / adjudicator, and whether they
                                            had seen any machine reading before labelling
  audits/human_aamas/<kit>/adjudication.csv optional; never replaces a raw answer, reported apart
  audits/human_aamas/machine_keys/*.json    the sealed machine readings (parser, both readers)
  audits/human_aamas/empty_pages_labels.csv and protocol_check.csv   the two earlier kits

Outputs (out/aamas/human_validation/):
  summary.json             every number below with numerator, denominator, papers, seeds, exclusions
  agreement_by_field.csv   one row per (comparison, annotator, stratum, field)
  verdicts.csv             Welch's t recomputed from each human-read comparison, beside the machines'
  disagreements.csv        every field on which a human and a machine (or two humans) differ
  report.md                the same in prose and tables; N/A wherever there are no data
  rebuttal_filled.md       audits/human_aamas/REBUTTAL_TEMPLATE.md with every slot that has human
                           data filled and every other slot left visibly pending
  runcount_decisions.csv   C3: each disputed run count with the human decision and passage
  page_groups_matched.csv  B: every human-listed group and every machine group, matched or not

Conventions (the paper's, from study/analyze.py): the comparison is the bold cell against the best
non-bold cell of its group; the test is Welch's t with Satterthwaite degrees of freedom at the stated
run count, the normal limit for a standard error or interval without one; an unlabelled bar is read
as a standard deviation; a 95% interval is converted with 1.96; alpha = 0.05, two-sided, no
multiplicity correction per item. p >= 0.05 means "not separable from the reported evidence at the
stated run count", never "the claimed superiority is false".

Intervals: Wilson 95% for item proportions (descriptive: items are not independent) and a 95%
percentile bootstrap over papers (pages for the page audit), 2000 resamples, seed 0. A zero
denominator prints N/A.

Usage: python aamas/human_validation_score.py [--kit-dir audits/human_aamas] [--out out/aamas/human_validation]
       [--require-labels]   exit 1 when no human label file is present
Exit status 2 when a label file fails validation (schema, duplicates, unknown ids, edited after freezing).
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "study"))
sys.path.insert(0, ROOT)
from analyze import test_comparison  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

ALPHA = 0.05
BOOT_REPS = 2000
BOOT_SEED = 0
KIND_MAP = {"sd": "std", "std": "std", "se": "sem", "sem": "sem", "ci": "ci", "unlabelled": "unknown",
            "unknown": "unknown", "unclear": "unknown", "absent": "none", "none": "none", "other": "other"}

A_COLS = ["target_visible", "results_table", "bold_unique", "orientation", "direction", "winner_mean", "winner_bar",
          "winner_disp", "runner_mean", "runner_bar", "runner_disp", "rival_copied", "disp_type", "disp_source",
          "n_runs", "n_runs_other", "n_source", "paper_opened", "evidence", "confidence", "comment"]
A_ALLOWED = {
    "target_visible": {"y", "n"}, "results_table": {"y", "n", "unclear"},
    "bold_unique": {"y", "not_bold", "several_bold", "unclear"}, "orientation": {"column", "row", "unclear"},
    "direction": {"higher", "lower", "unclear"}, "winner_bar": {"present", "absent", "unclear"},
    "runner_bar": {"present", "absent", "not_applicable", "unclear"}, "rival_copied": {"y", "n", "unclear"},
    "disp_type": {"sd", "se", "ci", "unlabelled", "other", "absent", "unclear"},
    "disp_source": {"caption", "table", "page", "elsewhere", "absent", "not_applicable"},
    "n_source": {"caption", "page", "elsewhere", "absent", "ambiguous"}, "paper_opened": {"y", "n"},
    "confidence": {"high", "medium", "low"},
}
C3_COLS = ["n_runs", "n_unit", "applies_to_table", "n_source", "other_counts", "passage", "passage_location",
           "confidence", "comment"]
C3_ALLOWED = {"n_unit": {"seeds", "episodes", "instances", "folds", "repetitions", "other", "none"},
              "applies_to_table": {"explicit", "paper_wide", "no", "unclear"},
              "n_source": {"caption", "page", "elsewhere", "absent", "ambiguous"}, "confidence": {"high", "medium", "low"}}
C4_COLS = ["table_found", "has_bars", "bar_kind", "stated_where", "passage", "passage_location", "n_runs",
           "confidence", "comment"]
C4_ALLOWED = {"table_found": {"y", "n"}, "has_bars": {"y", "n", "unclear"},
              "bar_kind": {"sd", "se", "ci", "range", "iqr", "other", "not_stated", "conflicting"},
              "stated_where": {"caption", "table", "page", "methods", "appendix", "elsewhere", "not_stated"},
              "confidence": {"high", "medium", "low"}}
B_COLS = ["row_type", "page_id", "annotator_id", "page_status", "table_key", "table_ref", "results_table",
          "orientation", "bold_rule", "group_key", "group_table_key", "group_label", "winner_value", "bold_is_best",
          "x_px", "y_px"]
B_ALLOWED = {"row_type": {"page", "table", "group"}, "page_status": {"groups_listed", "none_found", "unclear"},
             "results_table": {"y", "n", "unclear"}, "orientation": {"column", "row", "unclear"},
             "bold_rule": {"single_best", "top_k", "other", "no_bold", "unclear"},
             "bold_is_best": {"y", "tie", "n", "unclear"}}
KITS = {"comparison_blind": (A_COLS, A_ALLOWED), "runcount_disputes": (C3_COLS, C3_ALLOWED),
        "bartype_random": (C4_COLS, C4_ALLOWED), "page_detection": (B_COLS, B_ALLOWED)}


class ValidationError(Exception):
    pass


# ======================================================================= small statistics
def rate(k, n, *, clusters=None, what=""):
    """k of n with a Wilson interval and, given one cluster id per item (a list
    of (cluster, success) pairs), a percentile bootstrap over clusters."""
    out = {"k": k, "n": n, "what": what}
    if not n:
        out.update({"pct": None, "wilson": None, "boot": None, "n_clusters": 0, "text": "N/A (no items)"})
        return out
    lo, hi = wilson_interval(k, n)
    out.update({"pct": round(100 * k / n, 1), "wilson": [round(100 * lo, 1), round(100 * hi, 1)]})
    if clusters is not None:
        out["n_clusters"] = len({c for c, _ in clusters})
        out["boot"] = cluster_boot(clusters)
    out["text"] = fmt(out)
    return out


def fmt(r):
    if not r or not r.get("n"):
        return "N/A (no items)"
    s = f"{r['k']}/{r['n']} ({r['pct']}%, Wilson [{r['wilson'][0]}, {r['wilson'][1]}]"
    if r.get("boot"):
        s += f"; {r.get('n_clusters')}-cluster bootstrap [{r['boot'][0]}, {r['boot'][1]}]"
    return s + ")"


def cluster_boot(pairs, weights=None, reps=BOOT_REPS, seed=BOOT_SEED):
    """Percentile interval of a pooled proportion, resampling whole clusters.
    pairs: [(cluster, success)]; weights: {cluster: w} for a weighted ratio."""
    by = defaultdict(list)
    for c, ok in pairs:
        by[c].append(1.0 if ok else 0.0)
    keys = sorted(by)
    if len(keys) < 2:
        return None
    rng = random.Random(seed)
    vals = []
    for _ in range(reps):
        num = den = 0.0
        for _ in keys:
            c = keys[rng.randrange(len(keys))]
            w = weights.get(c, 1.0) if weights else 1.0
            num += w * sum(by[c])
            den += w * len(by[c])
        vals.append(100 * num / den if den else 0.0)
    vals.sort()
    return [round(vals[int(0.025 * reps)], 1), round(vals[int(0.975 * reps) - 1], 1)]


def kappa(pairs):
    """Cohen's kappa for two raters' categorical answers; None if undefined."""
    if not pairs:
        return None
    n = len(pairs)
    cats = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    po = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[c] * cb[c] for c in cats) / (n * n)
    return None if pe >= 1 else round((po - pe) / (1 - pe), 3)


# ======================================================================= value parsing
NONE_WORDS = {"none", "n/a", "na", "-", "--", "—", "absent", "not stated", "no", "nil"}
UNCLEAR_WORDS = {"unclear", "?", "unreadable", "ambiguous", "unknown"}
THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def parse_value(s):
    """(status, value) for a number typed by a person: status is num, none,
    unclear, missing or bad. Accepts 85.2, 85.20%, -0.3, −0.3, 1,234.5,
    1.2e-3, '85.2 ± 0.3' (keeps the mean), '±0.3', '(0.3)', '[0.1;0.5]'
    (an interval: half its width)."""
    if s is None:
        return "missing", None
    t = str(s).strip()
    if not t:
        return "missing", None
    low = t.lower()
    if low in UNCLEAR_WORDS:
        return "unclear", None
    if low in NONE_WORDS:
        return "none", None
    t = t.replace("−", "-").replace("–", "-").replace(" ", " ")
    for sep in ("±", "+/-", "+-"):
        if sep in t:
            head = t.split(sep)[0].strip()
            if head:
                t = head
            else:
                t = t.split(sep)[1].strip()
            break
    t = t.strip().strip("()[]{}").strip().rstrip("%").strip()
    if ";" in t:
        a, b = (parse_value(x)[1] for x in t.split(";", 1))
        return ("num", abs(b - a) / 2) if a is not None and b is not None else ("bad", None)
    if THOUSANDS.match(t):
        t = t.replace(",", "")
    try:
        return "num", float(t)
    except ValueError:
        return "bad", None


def same_num(a, b, tol=1e-6):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def low(s):
    return (s or "").strip().lower()


def rel(path):
    """A path relative to the repository when it lies inside it, else as given
    (os.path.relpath raises across Windows drives)."""
    try:
        r = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return path if r.startswith("..") else r


# ======================================================================= loading and validation
def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        return rd.fieldnames or [], list(rd)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load_raw_kit(kit_dir, kit, item_ids=None, errors=None, warnings=None):
    """{annotator_id: {item_id: row}} from <kit_dir>/raw/*.csv, validated.

    One file per annotator: a file holding two annotator ids, a duplicated
    item id, an unknown item id, a value outside the allowed set or a file
    changed after `freeze` is an error. Blank answers are allowed (they are
    counted as missing, never filled from a machine)."""
    errors = errors if errors is not None else []
    warnings = warnings if warnings is not None else []
    cols, allowed = KITS[kit]
    raw = os.path.join(kit_dir, "raw")
    out = {}
    if not os.path.isdir(raw):
        return out
    frozen_path = os.path.join(raw, "FROZEN.json")
    frozen = json.load(open(frozen_path, encoding="utf-8")) if os.path.exists(frozen_path) else {}
    for name in sorted(os.listdir(raw)):
        if not name.endswith(".csv"):
            continue
        path = os.path.join(raw, name)
        where = f"{kit}/raw/{name}"
        if name in frozen and frozen[name]["sha256"] != sha256(path):
            errors.append(f"{where}: changed after it was frozen ({frozen[name]['frozen_at']}); raw labels are immutable")
        elif frozen and name not in frozen:
            warnings.append(f"{where}: not frozen yet (python aamas/human_validation_kits.py freeze --kit {kit})")
        head, rows = _read_csv(path)
        id_col = "page_id" if kit == "page_detection" else "id"
        need = [id_col, "annotator_id"] + [c for c in cols if c != "annotator_id"]
        miss = [c for c in need if c not in head]
        if miss:
            errors.append(f"{where}: missing column(s) {miss}")
            continue
        ann = {r["annotator_id"].strip() for r in rows if (r.get("annotator_id") or "").strip()}
        if len(ann) != 1:
            errors.append(f"{where}: expected exactly one annotator_id, found {sorted(ann) or 'none'}")
            continue
        aid = ann.pop()
        if aid in out:
            errors.append(f"{where}: a second file for annotator {aid}")
            continue
        for r in rows:
            if r.get("kit") and r["kit"].strip() != kit:
                errors.append(f"{where}: row for kit {r['kit']!r}, not {kit}")
                break
        if kit == "page_detection":
            out[aid] = _load_pages(rows, where, item_ids, errors)
            continue
        recs = {}
        for k, r in enumerate(rows, 2):
            iid = r["id"].strip()
            if item_ids is not None and iid not in item_ids:
                errors.append(f"{where} line {k}: unknown item id {iid!r}")
                continue
            if iid in recs:
                errors.append(f"{where} line {k}: duplicate item id {iid}")
                continue
            for c, ok in allowed.items():
                v = low(r.get(c))
                if v and v not in ok:
                    errors.append(f"{where} line {k} ({iid}): {c}={r.get(c)!r} not in {sorted(ok)}")
            for c in ("winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs"):
                if c in r and parse_value(r[c])[0] == "bad":
                    errors.append(f"{where} line {k} ({iid}): {c}={r[c]!r} is not a number, none or unclear")
            recs[iid] = {c: (r.get(c) or "").strip() for c in head}
        out[aid] = recs
    return out


def _load_pages(rows, where, page_ids, errors):
    pages = {}
    for k, r in enumerate(rows, 2):
        pid = (r.get("page_id") or "").strip()
        if page_ids is not None and pid not in page_ids:
            errors.append(f"{where} line {k}: unknown page id {pid!r}")
            continue
        for c, ok in B_ALLOWED.items():
            v = low(r.get(c))
            if v and v not in ok:
                errors.append(f"{where} line {k} ({pid}): {c}={r.get(c)!r} not in {sorted(ok)}")
        p = pages.setdefault(pid, {"status": None, "note": "", "tables": {}, "groups": [], "_page_rows": 0})
        rt = low(r.get("row_type"))
        if rt == "page":
            p["_page_rows"] += 1
            p["status"] = low(r.get("page_status")) or None
            p["note"] = (r.get("page_note") or "").strip()
        elif rt == "table":
            key = (r.get("table_key") or "").strip()
            if key in p["tables"]:
                errors.append(f"{where} line {k} ({pid}): duplicate table key {key}")
            p["tables"][key] = {"ref": (r.get("table_ref") or "").strip(), "caption": (r.get("table_caption") or "").strip(),
                                "results": low(r.get("results_table")), "orient": low(r.get("orientation")),
                                "rule": low(r.get("bold_rule"))}
        elif rt == "group":
            g = {"key": (r.get("group_key") or "").strip(), "table": (r.get("group_table_key") or "").strip(),
                 "label": (r.get("group_label") or "").strip(), "winner_raw": (r.get("winner_value") or "").strip(),
                 "best": low(r.get("bold_is_best")), "note": (r.get("group_note") or "").strip()}
            st, v = parse_value(g["winner_raw"])
            if st == "bad":
                errors.append(f"{where} line {k} ({pid}): winner_value {g['winner_raw']!r} is not a number")
            g["winner"] = v if st == "num" else None
            try:
                g["x"] = float(r["x_px"]) if (r.get("x_px") or "").strip() else None
                g["y"] = float(r["y_px"]) if (r.get("y_px") or "").strip() else None
            except ValueError:
                errors.append(f"{where} line {k} ({pid}): x_px/y_px not numeric")
                g["x"] = g["y"] = None
            # a click stored as NaN/Infinity (an older sheet, an image not yet loaded) carries no location
            if g["x"] is None or g["y"] is None or not (math.isfinite(g["x"]) and math.isfinite(g["y"])):
                g["x"] = g["y"] = None
            p["groups"].append(g)
        else:
            errors.append(f"{where} line {k}: row_type {r.get('row_type')!r}")
    for pid, p in pages.items():
        if p["_page_rows"] != 1:
            errors.append(f"{where}: page {pid} has {p['_page_rows']} page rows (expected 1)")
        for g in p["groups"]:
            if g["table"] not in p["tables"]:
                errors.append(f"{where}: page {pid} group {g['key']} refers to an unlisted table {g['table']!r}")
        keys = [g["key"] for g in p["groups"]]
        if len(keys) != len(set(keys)):
            errors.append(f"{where}: page {pid} repeats a group key")
    return pages


def load_registry(kit_dir, warnings):
    path = os.path.join(kit_dir, "annotators.csv")
    if not os.path.exists(path):
        return {}
    _, rows = _read_csv(path)
    reg = defaultdict(dict)
    for r in rows:
        if not (r.get("annotator_id") or "").strip():
            continue
        reg[(r.get("kit") or "").strip()][r["annotator_id"].strip()] = {
            "role": low(r.get("role")), "seen_machine_outputs": low(r.get("seen_machine_outputs")),
            "notes": (r.get("notes") or "").strip()}
    return reg


def roles(kit, raws, reg, errors, warnings):
    """(primary, second, independence notes) for one kit."""
    ids = sorted(raws)
    if not ids:
        return None, None, {}
    declared = reg.get(kit, {})
    prim = [a for a in ids if declared.get(a, {}).get("role") == "primary"]
    sec = [a for a in ids if declared.get(a, {}).get("role") == "second"]
    undeclared = [a for a in ids if a not in declared]
    if undeclared and len(ids) > 1:
        errors.append(f"{kit}: annotator(s) {undeclared} have raw files but no row in annotators.csv; "
                      f"declare each one's role (primary / second)")
    if not prim and len(ids) == 1:
        warnings.append(f"{kit}: one annotator ({ids[0]}) and no annotators.csv row; treated as primary")
        prim = ids
    if len(prim) != 1:
        errors.append(f"{kit}: exactly one primary annotator needed, found {prim}")
        return None, None, {}
    indep = {a: declared.get(a, {}).get("seen_machine_outputs", "undeclared") for a in ids}
    for a, s in indep.items():
        if s != "n":
            warnings.append(f"{kit}: annotator {a} declared seen_machine_outputs={s!r}; their labels are reported as "
                            f"NOT independent of the machine readings")
    return prim[0], (sec[0] if sec else None), indep


def load_adjudication(kit_dir, kit, errors):
    path = os.path.join(kit_dir, kit, "adjudication.csv")
    if not os.path.exists(path):
        return {}
    head, rows = _read_csv(path)
    need = ["id", "field", "value_a", "value_b", "adjudicated_value", "adjudicator"]
    if any(c not in head for c in need):
        errors.append(f"{kit}/adjudication.csv: needs columns {need}")
        return {}
    out = {}
    for r in rows:
        if (r.get("adjudicated_value") or "").strip():
            if not (r.get("adjudicator") or "").strip():
                errors.append(f"{kit}/adjudication.csv: {r['id']} {r['field']} adjudicated without an adjudicator id")
            out[(r["id"].strip(), r["field"].strip())] = r["adjudicated_value"].strip()
    return out


# ======================================================================= A: blind comparisons
def human_view(lb):
    """A normalised reading of one human answer row of the comparison kit."""
    if lb is None:
        return None
    h = {c: low(lb.get(c)) for c in A_ALLOWED}
    for c in ("winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs"):
        h[c] = parse_value(lb.get(c))
    h["evidence"] = (lb.get("evidence") or "").strip()
    h["comment"] = (lb.get("comment") or "").strip()
    h["n_runs_other"] = (lb.get("n_runs_other") or "").strip()
    return h


def human_category(h):
    """Why a human reading is or is not testable under the paper's rules."""
    if h is None:
        return "not_labelled"
    if h["target_visible"] == "n":
        return "void_no_box"
    if not h["target_visible"] or not h["results_table"]:
        return "missing_answers"
    if h["results_table"] != "y":
        return "not_results_table" if h["results_table"] == "n" else "results_table_unclear"
    if h["bold_unique"] != "y":
        return "not_a_single_bold" if h["bold_unique"] else "missing_answers"
    w, r = h["winner_mean"], h["runner_mean"]
    if w[0] == "missing" or r[0] == "missing":
        return "missing_answers"
    if w[0] != "num" or r[0] == "unclear":
        return "value_unreadable"
    if r[0] == "none":
        return "no_runner_up"
    if h["direction"] in ("higher", "lower"):
        better = (w[1] > r[1]) if h["direction"] == "higher" else (w[1] < r[1])
        if w[1] == r[1]:
            return "bold_ties_runner_up"
        if not better:
            return "bold_not_best_by_printed_means"
    wb, rb = h["winner_bar"], h["runner_bar"]
    if not wb or not rb:
        return "missing_answers"
    if "unclear" in (wb, rb):
        return "bar_presence_unclear"
    if wb != "present" and rb != "present":
        return "no_bar_either_side"
    if wb != "present" or rb != "present":
        return "bar_one_side_only"
    if h["winner_disp"][0] != "num" or h["runner_disp"][0] != "num":
        return "bar_value_unreadable"
    kind = KIND_MAP.get(h["disp_type"])
    if kind == "other":
        return "bar_kind_not_convertible"
    if kind is None:
        return "missing_answers"
    n = h["n_runs"]
    if kind in ("std", "unknown") and not (n[0] == "num" and n[1] >= 2):
        return "bars_without_run_count" if n[0] in ("none", "num") else "run_count_unclear"
    return "testable"


def human_test(h, kind_override=None):
    if human_category(h) != "testable":
        return None
    kind = kind_override or KIND_MAP[h["disp_type"]]
    n = h["n_runs"][1] if h["n_runs"][0] == "num" else None
    c = {"gap": abs(h["winner_mean"][1] - h["runner_mean"][1]), "winner_dispersion": h["winner_disp"][1],
         "runner_dispersion": h["runner_disp"][1], "dispersion_kind": kind,
         "n_runs": int(n) if n and n >= 2 else None}
    return test_comparison(c)


def parser_test(p):
    if p.get("winner") is None or p.get("runner_up") is None:
        return None
    return test_comparison({"gap": abs(p["winner"] - p["runner_up"]), "winner_dispersion": p.get("winner_dispersion"),
                            "runner_dispersion": p.get("runner_dispersion"),
                            "dispersion_kind": p.get("dispersion_kind") or "unknown", "n_runs": p.get("n_runs")})


def reader_test(lb):
    """A reference reader's own verdict, by study/gold_set.py's rule."""
    if not low(lb.get("results_table")).startswith("y") or not low(lb.get("bold_ok")).startswith("y"):
        return None
    w, r = parse_value(lb.get("winner_mean")), parse_value(lb.get("runner_mean"))
    wd, rd = parse_value(lb.get("winner_disp")), parse_value(lb.get("runner_disp"))
    n = parse_value(lb.get("n_runs"))
    if w[0] != "num" or r[0] != "num":
        return None
    kind = KIND_MAP.get(low(lb.get("disp_type")), "unknown")
    return test_comparison({"gap": abs(w[1] - r[1]), "winner_dispersion": wd[1] if wd[0] == "num" else None,
                            "runner_dispersion": rd[1] if rd[0] == "num" else None,
                            "dispersion_kind": kind if kind in ("std", "sem", "ci", "unknown") else "unknown",
                            "n_runs": int(n[1]) if n[0] == "num" and n[1] >= 2 else None})


def verdict(t):
    if t is None:
        return "not_testable"
    return "not_separable" if t["p"] >= ALPHA else "separable"


def _src(p):
    if p.get("n_runs") is None:
        return "absent"
    return {"caption": "caption", "page": "page"}.get(p.get("n_runs_source"), "elsewhere")


def _reader_src(s):
    s = low(s)
    if s in ("caption", "page"):
        return s
    if s in ("paper", "elsewhere", "appendix"):
        return "elsewhere"
    return "absent" if s in ("none", "", "absent") else s


# each comparable field: (name, how to read the human, how to read each machine, kind)
# machine readers get (key_item) and return a comparable value, or EXCLUDE
EXCLUDE = object()


def _num_or(t):
    return t[1] if t[0] == "num" else (None if t[0] == "none" else EXCLUDE)


def _bar_present(t, bar):
    if bar == "present":
        return "present"
    if bar in ("absent", "not_applicable"):
        return "absent"
    return EXCLUDE


A_FIELD_SPECS = [
    # field, human value fn, parser fn, reader fn, numeric?
    ("results_table", lambda h: h["results_table"] if h["results_table"] in ("y", "n") else EXCLUDE,
     lambda k: "y", lambda lb: "y" if low(lb.get("results_table")).startswith("y") else "n", False),
    ("bold_unique", lambda h: ("y" if h["bold_unique"] == "y" else "n") if h["bold_unique"] in ("y", "not_bold", "several_bold") else EXCLUDE,
     lambda k: "y", lambda lb: ("y" if low(lb.get("bold_ok")).startswith("y") else "n") if low(lb.get("bold_ok")) in ("y", "n", "yes", "no") else EXCLUDE, False),
    ("orientation", lambda h: h["orientation"] if h["orientation"] in ("row", "column") else EXCLUDE,
     lambda k: low(k["parser"].get("orientation")), lambda lb: low(lb.get("orientation")) or EXCLUDE, False),
    ("direction", lambda h: h["direction"][:3] if h["direction"] in ("higher", "lower") else EXCLUDE,
     lambda k: low(k["parser"].get("direction"))[:3], lambda lb: low(lb.get("direction"))[:3] or EXCLUDE, False),
    ("winner_mean", lambda h: _num_or(h["winner_mean"]), lambda k: k["parser"].get("winner"),
     lambda lb: _num_or(parse_value(lb.get("winner_mean"))), True),
    ("runner_mean", lambda h: _num_or(h["runner_mean"]), lambda k: k["parser"].get("runner_up"),
     lambda lb: _num_or(parse_value(lb.get("runner_mean"))), True),
    ("winner_bar_present", lambda h: _bar_present(h["winner_disp"], h["winner_bar"]),
     lambda k: "present" if k["parser"].get("winner_dispersion") is not None else "absent",
     lambda lb: "present" if parse_value(lb.get("winner_disp"))[0] == "num" else ("absent" if parse_value(lb.get("winner_disp"))[0] == "none" else EXCLUDE), False),
    ("runner_bar_present", lambda h: _bar_present(h["runner_disp"], h["runner_bar"]),
     lambda k: "present" if k["parser"].get("runner_dispersion") is not None else "absent",
     lambda lb: "present" if parse_value(lb.get("runner_disp"))[0] == "num" else ("absent" if parse_value(lb.get("runner_disp"))[0] == "none" else EXCLUDE), False),
    ("winner_disp", lambda h: h["winner_disp"][1] if h["winner_bar"] == "present" and h["winner_disp"][0] == "num" else EXCLUDE,
     lambda k: k["parser"].get("winner_dispersion") if k["parser"].get("winner_dispersion") is not None else EXCLUDE,
     lambda lb: _num_or(parse_value(lb.get("winner_disp"))) if parse_value(lb.get("winner_disp"))[0] == "num" else EXCLUDE, True),
    ("runner_disp", lambda h: h["runner_disp"][1] if h["runner_bar"] == "present" and h["runner_disp"][0] == "num" else EXCLUDE,
     lambda k: k["parser"].get("runner_dispersion") if k["parser"].get("runner_dispersion") is not None else EXCLUDE,
     lambda lb: _num_or(parse_value(lb.get("runner_disp"))) if parse_value(lb.get("runner_disp"))[0] == "num" else EXCLUDE, True),
    ("disp_type", lambda h: KIND_MAP.get(h["disp_type"], EXCLUDE) if h["disp_type"] not in ("", "unclear") else EXCLUDE,
     lambda k: k["parser"].get("dispersion_kind") or "none",
     lambda lb: KIND_MAP.get(low(lb.get("disp_type")), EXCLUDE) if low(lb.get("disp_type")) else EXCLUDE, False),
    ("disp_treatment", lambda h: {"std": "sd_like", "unknown": "sd_like", "sem": "se_like", "ci": "se_like"}.get(KIND_MAP.get(h["disp_type"]), EXCLUDE),
     lambda k: {"std": "sd_like", "unknown": "sd_like", "sem": "se_like", "ci": "se_like"}.get(k["parser"].get("dispersion_kind"), EXCLUDE),
     lambda lb: {"std": "sd_like", "unknown": "sd_like", "sem": "se_like", "ci": "se_like"}.get(KIND_MAP.get(low(lb.get("disp_type"))), EXCLUDE), False),
    ("n_runs", lambda h: _num_or(h["n_runs"]), lambda k: k["parser"].get("n_runs"),
     lambda lb: _num_or(parse_value(lb.get("n_runs"))), True),
    ("n_source", lambda h: h["n_source"] or EXCLUDE, lambda k: _src(k["parser"]),
     lambda lb: _reader_src(lb.get("n_source")) if low(lb.get("n_source")) else EXCLUDE, False),
    ("rival_copied", lambda h: h["rival_copied"] if h["rival_copied"] in ("y", "n") else EXCLUDE,
     None, lambda lb: low(lb.get("rival_copied"))[:1] if low(lb.get("rival_copied"))[:1] in ("y", "n") else EXCLUDE, False),
]


UNDERLYING = {"winner_bar_present": "winner_bar", "runner_bar_present": "runner_bar", "disp_treatment": "disp_type"}


def _excl_reason(h, field):
    raw = h.get(UNDERLYING.get(field, field))
    status = raw[0] if isinstance(raw, tuple) else raw
    if status == "unclear":
        return "unclear"
    if status in ("", "missing", None):
        return "missing"
    return "not_applicable"


def _in_base(h, field):
    """Items a field is asked of: a box was drawn, and for every field but the
    first, the region is a results table."""
    if h is None or h["target_visible"] != "y":
        return False
    return True if field == "results_table" else h["results_table"] == "y"


def compare_fields(items, key, human, machine_name, machine_fn_index, stratum, annotator):
    """Per-field agreement of one human with one machine on one stratum."""
    rows, dis = [], []
    for field, hfn, pfn, rfn, numeric in A_FIELD_SPECS:
        mfn = pfn if machine_fn_index == "parser" else rfn
        if mfn is None:
            continue
        pairs, excl = [], Counter()
        for bid in items:
            k = key[bid]
            if k["stratum"] != stratum:
                continue
            h = human.get(bid)
            if h is None:
                excl["not_labelled"] += 1
                continue
            if not _in_base(h, field):
                excl["void_or_not_results_table" if h["target_visible"] else "missing"] += 1
                continue
            hv = hfn(h)
            if hv is EXCLUDE:
                excl[_excl_reason(h, field)] += 1
                continue
            if machine_fn_index == "parser":
                mv = mfn(k)
            else:
                mv = mfn(k[machine_fn_index])
            if mv is EXCLUDE:
                excl["machine_not_applicable"] += 1
                continue
            ok = same_num(hv, mv) if numeric else (hv == mv)
            pairs.append((k["paper"], ok))
            if not ok:
                dis.append({"kit": "comparison_blind", "item": bid, "orig_id": k["orig_id"], "stratum": stratum,
                            "paper": k["paper"], "annotator": annotator, "field": field, "human_value": hv,
                            "other": machine_name, "other_value": mv,
                            "evidence": (human[bid].get("evidence") or "")[:300], "comment": (human[bid].get("comment") or "")[:300]})
        r = rate(sum(1 for _, ok in pairs if ok), len(pairs), clusters=pairs, what=field)
        rows.append({"comparison": f"human_vs_{machine_name}", "annotator": annotator, "stratum": stratum, "field": field,
                     **{k2: r[k2] for k2 in ("k", "n", "pct")},
                     "wilson_lo": r["wilson"][0] if r["wilson"] else "", "wilson_hi": r["wilson"][1] if r["wilson"] else "",
                     "n_papers": r.get("n_clusters", 0), "boot_lo": r["boot"][0] if r.get("boot") else "",
                     "boot_hi": r["boot"][1] if r.get("boot") else "", "excluded": dict(excl)})
    return rows, dis


def compare_humans(items, key, ha, hb, a, b):
    rows, dis = [], []
    for field, hfn, _, _, numeric in A_FIELD_SPECS:
        pairs, cat_pairs, excl = [], [], Counter()
        for bid in items:
            k = key[bid]
            x, y = ha.get(bid), hb.get(bid)
            if x is None or y is None:
                excl["not_labelled_by_both"] += 1
                continue
            if not (_in_base(x, field) and _in_base(y, field)):
                excl["base_differs_or_void"] += 1
                continue
            vx, vy = hfn(x), hfn(y)
            if vx is EXCLUDE or vy is EXCLUDE:
                excl["unclear_or_missing"] += 1
                continue
            ok = same_num(vx, vy) if numeric else vx == vy
            pairs.append((k["paper"], ok))
            if not numeric:
                cat_pairs.append((vx, vy))
            if not ok:
                dis.append({"kit": "comparison_blind", "item": bid, "orig_id": k["orig_id"], "stratum": k["stratum"],
                            "paper": k["paper"], "annotator": a, "field": field, "human_value": vx,
                            "other": f"human:{b}", "other_value": vy, "evidence": "", "comment": ""})
        r = rate(sum(1 for _, ok in pairs if ok), len(pairs), clusters=pairs, what=field)
        rows.append({"comparison": "human_vs_human", "annotator": f"{a}|{b}", "stratum": "both", "field": field,
                     "k": r["k"], "n": r["n"], "pct": r["pct"],
                     "wilson_lo": r["wilson"][0] if r["wilson"] else "", "wilson_hi": r["wilson"][1] if r["wilson"] else "",
                     "n_papers": r.get("n_clusters", 0), "boot_lo": r["boot"][0] if r.get("boot") else "",
                     "boot_hi": r["boot"][1] if r.get("boot") else "", "excluded": dict(excl),
                     "kappa": kappa(cat_pairs) if cat_pairs else ""})
    # the derived quantities
    for name, fn in (("category", human_category), ("verdict", lambda h: verdict(human_test(h)))):
        pairs = [(key[b_]["paper"], fn(ha[b_]) == fn(hb[b_]), fn(ha[b_]), fn(hb[b_]))
                 for b_ in items if b_ in ha and b_ in hb]
        r = rate(sum(1 for p in pairs if p[1]), len(pairs), clusters=[(p[0], p[1]) for p in pairs], what=name)
        rows.append({"comparison": "human_vs_human", "annotator": f"{a}|{b}", "stratum": "both", "field": name,
                     "k": r["k"], "n": r["n"], "pct": r["pct"],
                     "wilson_lo": r["wilson"][0] if r["wilson"] else "", "wilson_hi": r["wilson"][1] if r["wilson"] else "",
                     "n_papers": r.get("n_clusters", 0), "boot_lo": r["boot"][0] if r.get("boot") else "",
                     "boot_hi": r["boot"][1] if r.get("boot") else "", "excluded": {},
                     "kappa": kappa([(p[2], p[3]) for p in pairs]) if pairs else ""})
    return rows, dis


def score_comparison(kit_dir, keys_dir, reg, errors, warnings):
    kpath = os.path.join(keys_dir, "comparison_key.json")
    if not os.path.exists(kpath):
        errors.append("machine_keys/comparison_key.json missing: run python aamas/human_validation_kits.py build")
        return None
    key = json.load(open(kpath, encoding="utf-8"))["items"]
    raws = load_raw_kit(os.path.join(kit_dir, "comparison_blind"), "comparison_blind", set(key), errors, warnings)
    out = {"status": "no_human_labels", "annotators": sorted(raws)}
    if not raws:
        return out
    prim, sec, indep = roles("comparison_blind", raws, reg, errors, warnings)
    if prim is None:
        return out
    H = {bid: human_view(lb) for bid, lb in raws[prim].items() if any(lb.get(c) for c in A_COLS)}
    out.update({"status": "scored", "primary": prim, "second": sec, "independence": indep})
    ids = sorted(H)
    # completeness and exclusions
    cats = {bid: human_category(H.get(bid)) for bid in key}
    out["coverage"] = {
        "items_in_kit": len(key), "labelled_by_primary": len(ids),
        "labelled_core": sum(1 for b in ids if key[b]["in_core"]),
        "labelled_by_stratum": dict(Counter(key[b]["stratum"] for b in ids)),
        "papers_labelled": len({key[b]["paper"] for b in ids}),
        "void_no_box": sum(1 for b in ids if cats[b] == "void_no_box"),
        "missing_answers": sum(1 for b in ids if cats[b] == "missing_answers"),
        "paper_not_opened": sum(1 for b in ids if H[b]["paper_opened"] == "n"),
        "unclear_answers_by_field": {c: sum(1 for b in ids if (H[b].get(c) == "unclear") or
                                            (isinstance(H[b].get(c), tuple) and H[b][c][0] == "unclear"))
                                     for c in ("results_table", "bold_unique", "orientation", "direction", "winner_mean",
                                               "runner_mean", "winner_disp", "runner_disp", "disp_type", "n_runs", "rival_copied")},
        "run_count_ambiguous_or_conflicting": sum(1 for b in ids if H[b]["n_source"] == "ambiguous" or H[b]["n_runs_other"]),
        "core_items_unlabelled": sorted(b for b in key if key[b]["in_core"] and b not in H),
    }
    agree_rows, dis_rows = [], []
    for stratum in ("testable", "no_bar"):
        for mname, idx in (("parser", "parser"), ("reader1", "reader1"), ("reader2", "reader2")):
            r_, d_ = compare_fields(ids, key, H, mname, idx, stratum, prim)
            agree_rows += r_
            dis_rows += d_
    # testability and verdicts
    vrows, confusion = [], defaultdict(Counter)
    for bid in sorted(key):
        k = key[bid]
        h = H.get(bid)
        cat = cats[bid]
        th = human_test(h) if h else None
        th_se = human_test(h, "sem") if h and h["disp_type"] in ("unlabelled", "unclear") else None
        tp = parser_test(k["parser"])
        t1, t2 = reader_test(k["reader1"]), reader_test(k["reader2"])
        if h is not None:
            confusion[k["stratum"]][(cat, "parser_testable" if tp else "parser_not_testable")] += 1
        vrows.append({"id": bid, "orig_id": k["orig_id"], "stratum": k["stratum"], "paper": k["paper"],
                      "table": k["table"], "pdf_page": k["page"] + 1, "labelled": "y" if h else "n",
                      "human_category": cat,
                      "human_winner": h["winner_mean"][1] if h else "", "human_runner": h["runner_mean"][1] if h else "",
                      "human_winner_disp": h["winner_disp"][1] if h else "", "human_runner_disp": h["runner_disp"][1] if h else "",
                      "human_kind": h["disp_type"] if h else "", "human_n_runs": h["n_runs"][1] if h else "",
                      "human_p": round(th["p"], 6) if th else "", "human_test": th["test"] if th else "",
                      "human_verdict": verdict(th) if h else "",
                      "human_verdict_unlabelled_as_se": verdict(th_se) if th_se is not None else "",
                      "parser_p": round(tp["p"], 6) if tp else "", "parser_verdict": verdict(tp),
                      "reader1_verdict": verdict(t1), "reader2_verdict": verdict(t2),
                      "human_agrees_with_parser": ("y" if verdict(th) == verdict(tp) else "n") if th and tp else ""})
    out["testability_confusion"] = {s: {f"{a}|{b}": n for (a, b), n in sorted(c.items())} for s, c in confusion.items()}
    res = {}
    for stratum in ("testable", "no_bar"):
        S = [v for v in vrows if v["stratum"] == stratum and v["labelled"] == "y"]
        tested = [v for v in S if v["human_p"] != ""]
        ns = [(v["paper"], v["human_verdict"] == "not_separable") for v in tested]
        both = [v for v in tested if v["parser_p"] != ""]
        res[stratum] = {
            "labelled": len(S), "papers": len({v["paper"] for v in S}),
            "human_testable": rate(len(tested), len(S), clusters=[(v["paper"], v["human_p"] != "") for v in S],
                                   what="human-read comparisons that can be tested"),
            "human_not_separable": rate(sum(1 for _, x in ns if x), len(ns), clusters=ns,
                                        what="of the human-testable, p >= 0.05 at the human-read run count"),
            "parser_not_separable_same_items": rate(sum(1 for v in both if v["parser_verdict"] == "not_separable"), len(both),
                                                    clusters=[(v["paper"], v["parser_verdict"] == "not_separable") for v in both],
                                                    what="the parser's verdict on the items both test"),
            "verdict_agreement_with_parser": rate(sum(1 for v in both if v["human_verdict"] == v["parser_verdict"]), len(both),
                                                  clusters=[(v["paper"], v["human_verdict"] == v["parser_verdict"]) for v in both],
                                                  what="same verdict, on items both the human and the parser test"),
            "verdict_2x2_human_by_parser": dict(Counter(f"{v['human_verdict']}|{v['parser_verdict']}" for v in both)),
            "categories": dict(Counter(v["human_category"] for v in S)),
            "unlabelled_bars_read_as_se": {
                "n": sum(1 for v in tested if v["human_verdict_unlabelled_as_se"]),
                "not_separable_as_sd": sum(1 for v in tested if v["human_verdict_unlabelled_as_se"] and v["human_verdict"] == "not_separable"),
                "not_separable_as_se": sum(1 for v in tested if v["human_verdict_unlabelled_as_se"] == "not_separable")},
            "bold_not_best_by_printed_means": sum(1 for v in S if v["human_category"] in ("bold_not_best_by_printed_means", "bold_ties_runner_up")),
        }
        if stratum == "no_bar":
            Br = [(key[b]["paper"], H[b]) for b in ids if key[b]["stratum"] == "no_bar" and _in_base(H[b], "x")]
            absent = [(p, h["winner_bar"] == "absent" and h["runner_bar"] in ("absent", "not_applicable"))
                      for p, h in Br if h["winner_bar"] in ("present", "absent") and h["runner_bar"] in ("present", "absent", "not_applicable")]
            res[stratum]["no_bar_on_either_side"] = rate(sum(1 for _, x in absent if x), len(absent), clusters=absent,
                                                         what="no error bar printed for either cell, as the parser said")
    out["by_stratum"] = res
    out["welch_conventions"] = ("Welch t (Satterthwaite df) at the human-read run count; normal limit for SE/CI without one; "
                                "unlabelled or unclear bar read as SD; CI / 1.96; alpha 0.05 two-sided; gap = |winner - runner-up| "
                                "of the human-read means; study/analyze.py:test_comparison")
    # second annotator and adjudication
    if sec:
        H2 = {bid: human_view(lb) for bid, lb in raws[sec].items() if any(lb.get(c) for c in A_COLS)}
        both = sorted(set(H) & set(H2))
        hh_rows, hh_dis = compare_humans(both, key, H, H2, prim, sec)
        agree_rows += hh_rows
        dis_rows += hh_dis
        out["human_vs_human"] = {"second": sec, "items_both": len(both), "papers_both": len({key[b]["paper"] for b in both}),
                                 "share_of_kit": f"{len(both)}/{len(key)}"}
        if len(both) < math.ceil(0.2 * len(H)):
            warnings.append(f"comparison_blind: the second annotator overlaps {len(both)} of the primary's {len(H)} items, "
                            f"below the 20% the protocol asks for")
        adj = load_adjudication(kit_dir, "comparison_blind", errors)
        if adj:
            cons = {}
            for bid in both:
                lb = dict(raws[prim][bid])
                for (iid, f), v in adj.items():
                    if iid == bid:
                        lb[f] = v
                cons[bid] = human_view(lb)
            adj_rows = []
            for stratum in ("testable", "no_bar"):
                r_, _ = compare_fields(both, key, cons, "parser", "parser", stratum, f"adjudicated({prim},{sec})")
                adj_rows += r_
            for r in adj_rows:
                r["comparison"] = "adjudicated_vs_parser"
            agree_rows += adj_rows
            out["adjudication"] = {"fields_adjudicated": len(adj), "note": "raw answers are kept; adjudicated values are "
                                   "reported only in the adjudicated_vs_parser rows"}
    out["_agree_rows"] = agree_rows
    out["_dis_rows"] = dis_rows
    out["_verdict_rows"] = vrows
    return out


# ======================================================================= B: page detection
def _extremal(g):
    w, r = parse_value(g.get("winner_mean")), parse_value(g.get("runner_mean"))
    d = low(g.get("direction"))
    if w[0] == "num" and r[0] == "num":
        if w[1] == r[1] or (d.startswith("low") and w[1] > r[1]) or (d.startswith("high") and w[1] < r[1]):
            return False
    return True


def reader_groups(tables):
    """A reader's groups as the paper's unit: results tables only, the bold
    cell the better value (pages_score --extremal-only)."""
    out = []
    for ti, t in enumerate(tables or []):
        if not low(t.get("results_table")).startswith("y"):
            continue
        for g in t.get("groups", []):
            if not _extremal(g):
                continue
            st, v = parse_value(g.get("winner_mean"))
            out.append({"winner": v if st == "num" else None, "label": g.get("label", ""),
                        "table": (t.get("caption_start") or "")[:60]})
    return out


def eligible_groups(p, include_unclear_rule=False):
    rules = ("single_best", "unclear") if include_unclear_rule else ("single_best",)
    out = []
    for g in p["groups"]:
        t = p["tables"].get(g["table"], {})
        if g["best"] == "y" and t.get("results") == "y" and t.get("rule") in rules:
            out.append(g)
    return out


def match_groups(hgroups, preds, zoom=2.0, coords=True):
    """One-to-one: equal winner value (relative 1e-6); among several, the
    prediction whose winner cell is nearest the human's click. Returns
    {human index: prediction index}."""
    used, pair = set(), {}
    for hi, g in enumerate(hgroups):
        if g.get("winner") is None:
            continue
        cands = [pi for pi, p in enumerate(preds) if pi not in used and p.get("winner") is not None
                 and same_num(g["winner"], p["winner"])]
        if not cands:
            continue
        if coords and len(cands) > 1 and g.get("x") is not None:
            def dist(pi):
                c = preds[pi].get("winner_cell") or {}
                if "x" not in c:
                    return 1e9
                return math.hypot(c["x"] - g["x"] / zoom, c["y"] - g["y"] / zoom)
            cands.sort(key=dist)
        pair[hi] = cands[0]
        used.add(cands[0])
    return pair


def location_matches(hgroups, preds, pair, zoom=2.0, tol_pt=12.0):
    """Unmatched human groups whose click lies within tol_pt of an unmatched
    parser winner cell: a value typed differently, or read differently."""
    used = set(pair.values())
    out = []
    for hi, g in enumerate(hgroups):
        if hi in pair or g.get("x") is None:
            continue
        for pi, p in enumerate(preds):
            c = p.get("winner_cell") or {}
            if pi in used or "x" not in c:
                continue
            if math.hypot(c["x"] - g["x"] / zoom, c["y"] - g["y"] / zoom) <= tol_pt:
                out.append((hi, pi))
                used.add(pi)
                break
    return out


def score_pages(kit_dir, keys_dir, reg, errors, warnings):
    kpath = os.path.join(keys_dir, "page_key.json")
    if not os.path.exists(kpath):
        errors.append("machine_keys/page_key.json missing: run python aamas/human_validation_kits.py build --analysis ...")
        return None
    key = json.load(open(kpath, encoding="utf-8"))["pages"]
    raws = load_raw_kit(os.path.join(kit_dir, "page_detection"), "page_detection", set(key), errors, warnings)
    out = {"status": "no_human_labels", "annotators": sorted(raws)}
    if not raws:
        return out
    prim, sec, indep = roles("page_detection", raws, reg, errors, warnings)
    if prim is None:
        return out
    P = raws[prim]
    out.update({"status": "scored", "primary": prim, "second": sec, "independence": indep})
    match_rows = []
    strata = {}
    for frame in ("caption_pilot", "noncaption"):
        pages = [pid for pid in sorted(key) if key[pid]["frame"] == frame]
        done = [pid for pid in pages if pid in P and P[pid]["status"] in ("groups_listed", "none_found")]
        unclear = [pid for pid in pages if pid in P and P[pid]["status"] == "unclear"]
        res = {"pages_in_kit": len(pages), "pages_labelled": len(done), "pages_unclear": len(unclear),
               "pages_unlabelled": len(pages) - len(done) - len(unclear),
               "papers": len({key[p]["paper"] for p in done})}
        H = {pid: eligible_groups(P[pid]) for pid in done}
        res["human_eligible_groups"] = sum(len(v) for v in H.values())
        res["human_eligible_groups_incl_unclear_bold_rule"] = sum(len(eligible_groups(P[p], True)) for p in done)
        ne = Counter()
        for pid in done:
            elig = {g["key"] for g in H[pid]}
            n_elig_marked = sum(1 for g in P[pid]["groups"] if g["best"] == "y")
            if P[pid]["status"] == "none_found" and n_elig_marked:
                warnings.append(f"page_detection {pid}: status none_found but {n_elig_marked} group(s) marked strictly best")
            if P[pid]["status"] == "groups_listed" and not P[pid]["groups"]:
                warnings.append(f"page_detection {pid}: status groups_listed but no group rows")
            for g in P[pid]["groups"]:
                if g["key"] in elig:
                    continue
                t = P[pid]["tables"].get(g["table"], {})
                if t.get("results") != "y":
                    ne["table_not_a_results_table"] += 1
                elif t.get("rule") != "single_best":
                    ne[f"bold_rule_{t.get('rule') or 'missing'}"] += 1
                else:
                    ne[f"bold_is_best_{g['best'] or 'missing'}"] += 1
        res["human_single_bold_groups_not_eligible"] = dict(ne)
        res["pages_with_zero_eligible_groups"] = sum(1 for p in done if not H[p])
        res["pages_status_none_found"] = sum(1 for p in done if P[p]["status"] == "none_found")
        weights = {p: float(key[p].get("caption_pages_in_paper") or 1) for p in done}
        comparators = [("parser", lambda k: k["parser"])]
        comparators.append(("census_reader", lambda k: reader_groups(k["census_reader"]["tables"]) if k["census_reader"]["tables"] else []))
        if frame == "caption_pilot":
            comparators.append(("pilot_reader", lambda k: reader_groups((k.get("pilot_reader") or {}).get("tables"))))
        else:
            comparators.append(("noncaption_reader", lambda k: reader_groups((k.get("noncaption_reader") or {}).get("tables"))))
        res["comparators"] = {}
        for name, getter in comparators:
            rec_pairs, prec_pairs, fn, fp, loc = [], [], [], [], 0
            for pid in done:
                k = key[pid]
                preds = getter(k)
                hg = H[pid]
                pair = match_groups(hg, preds, k.get("zoom", 2.0), coords=(name == "parser"))
                if name == "parser":
                    loc += len(location_matches(hg, preds, pair, k.get("zoom", 2.0)))
                matched_preds = set(pair.values())
                for hi, g in enumerate(hg):
                    rec_pairs.append((pid, hi in pair))
                    if hi not in pair:
                        fn.append({"page": pid, "paper": k["paper"], "pdf_page": k["page"] + 1,
                                   "table": P[pid]["tables"].get(g["table"], {}).get("ref"), "group": g["label"],
                                   "bold_value": g["winner_raw"]})
                    match_rows.append({"frame": frame, "page": pid, "paper": k["paper"], "pdf_page": k["page"] + 1,
                                       "comparator": name, "side": "human", "table": P[pid]["tables"].get(g["table"], {}).get("ref"),
                                       "group": g["label"], "value": g["winner_raw"],
                                       "matched": "y" if hi in pair else "n",
                                       "matched_value": preds[pair[hi]].get("winner") if hi in pair else ""})
                for pi, pr in enumerate(preds):
                    prec_pairs.append((pid, pi in matched_preds))
                    if pi not in matched_preds:
                        fp.append({"page": pid, "paper": k["paper"], "pdf_page": k["page"] + 1,
                                   "table": pr.get("table"), "group": pr.get("label", ""), "bold_value": pr.get("winner")})
                        match_rows.append({"frame": frame, "page": pid, "paper": k["paper"], "pdf_page": k["page"] + 1,
                                           "comparator": name, "side": name, "table": pr.get("table"),
                                           "group": pr.get("label", ""), "value": pr.get("winner"), "matched": "n",
                                           "matched_value": ""})
            rec = rate(sum(1 for _, x in rec_pairs if x), len(rec_pairs), clusters=rec_pairs,
                       what=f"human eligible groups that the {name} also lists (recall on this frame)")
            prec = rate(sum(1 for _, x in prec_pairs if x), len(prec_pairs), clusters=prec_pairs,
                        what=f"{name} groups that the human also lists as eligible (precision on this frame)")
            entry = {"recall": rec, "precision": prec, "false_negatives": fn, "false_positives": fp}
            if frame == "caption_pilot":
                entry["recall_weighted_all_caption_pages"] = {
                    "pct": round(100 * sum(weights[p] * x for p, x in rec_pairs) / sum(weights[p] for p, _ in rec_pairs), 1) if rec_pairs else None,
                    "boot": cluster_boot(rec_pairs, weights) if rec_pairs else None,
                    "weights": "caption pages in the page's paper (inverse within-paper selection probability)"}
            if name == "parser":
                entry["unmatched_but_clicked_on_a_parser_winner_cell"] = loc
            if name == "census_reader":
                entry["pages_outside_census_frame"] = sum(1 for p in done if not key[p]["census_reader"]["in_census_frame"])
            res["comparators"][name] = entry
        res["groups_per_page"] = {"mean_unweighted": round(sum(len(H[p]) for p in done) / len(done), 3) if done else None,
                                  "mean_weighted": round(sum(weights[p] * len(H[p]) for p in done) / sum(weights.values()), 3) if done else None}
        strata[frame] = res
    out["strata"] = strata
    cap, nc = strata.get("caption_pilot", {}), strata.get("noncaption", {})
    if cap.get("pages_labelled") and nc.get("pages_labelled"):
        mc = cap["groups_per_page"]["mean_weighted"]
        mn = nc["groups_per_page"]["mean_unweighted"]
        Nc, Nn = 1008, 5612
        tot = Nc * mc + Nn * mn
        out["share_of_groups_on_noncaption_pages"] = {
            "estimate_pct": round(100 * Nn * mn / tot, 1) if tot else None,
            "assumes": "1008 caption pages (the census frame) and 5612 non-caption pages (audits/aamas_noncaption/draw.json); "
                       "the pilot frame (a 'Table N:' line) and the census frame (a caption the parser detected) differ "
                       "slightly, so this is approximate"}
    else:
        out["share_of_groups_on_noncaption_pages"] = {"estimate_pct": None, "why": "needs both strata labelled"}
    if sec:
        Q = raws[sec]
        both = sorted(p for p in set(P) & set(Q) if P[p]["status"] in ("groups_listed", "none_found")
                      and Q[p]["status"] in ("groups_listed", "none_found"))
        a_found = b_found = a_n = b_n = 0
        for pid in both:
            ga, gb = eligible_groups(P[pid]), eligible_groups(Q[pid])
            pr = match_groups(ga, [{"winner": g["winner"]} for g in gb], coords=False)
            a_found += len(pr)
            a_n += len(ga)
            pr2 = match_groups(gb, [{"winner": g["winner"]} for g in ga], coords=False)
            b_found += len(pr2)
            b_n += len(gb)
        out["human_vs_human"] = {"second": sec, "pages_both": len(both),
                                 "status_agree": rate(sum(1 for p in both if P[p]["status"] == Q[p]["status"]), len(both)),
                                 "primary_groups_found_by_second": rate(a_found, a_n),
                                 "second_groups_found_by_primary": rate(b_found, b_n)}
    out["_match_rows"] = match_rows
    out["scope"] = ("caption-page frame of the pilot draw only (and, separately, the non-caption stratum); not a "
                    "statement about every AAMAS page unless both strata are labelled")
    return out


# ======================================================================= C1, C2: the two earlier kits
def score_empty_pages(kit_dir):
    items_path = os.path.join(kit_dir, "empty_pages", "items.json")
    items = {r["id"]: r for r in json.load(open(items_path, encoding="utf-8"))}
    st_path = os.path.join(kit_dir, "empty_pages", "image_status.json")
    status = json.load(open(st_path, encoding="utf-8")) if os.path.exists(st_path) else {}
    files = [os.path.join(kit_dir, "empty_pages_labels.csv")]
    raw = os.path.join(kit_dir, "empty_pages", "raw")
    if os.path.isdir(raw):
        files += [os.path.join(raw, f) for f in sorted(os.listdir(raw)) if f.endswith(".csv")]
    files = [f for f in files if os.path.exists(f)]
    out = {"design": "deliberately selected hard cases (5 pages the two readers disagree on, 30 random pages the census "
                     "reader read as results tables with no single winner); a check of those pages, not an accuracy sample",
           "image_status": dict(Counter(v["status"] for v in status.values())), "files": [rel(f) for f in files]}
    if not files:
        out["status"] = "no_human_labels"
        return out
    _, rows = _read_csv(files[0])
    rows = [r for r in rows if (r.get("answer") or "").strip()]
    out["status"] = "scored"
    out["annotator"] = sorted({(r.get("annotator_id") or "").strip() or "undeclared" for r in rows})
    for kind in ("pilot_empty", "orientation_none"):
        sub = [r for r in rows if items.get(r["id"], {}).get("kind") == kind]
        out[kind] = {"labelled": len(sub), "of": sum(1 for v in items.values() if v["kind"] == kind),
                     "yes_census_reader_missed_a_group": sum(1 for r in sub if r["answer"] == "yes"),
                     "no": sum(1 for r in sub if r["answer"] == "no"),
                     "unclear": sum(1 for r in sub if r["answer"] == "unclear"),
                     "groups_on_yes_pages": sum(int(r["groups"]) for r in sub if r["answer"] == "yes" and (r.get("groups") or "").strip().isdigit())}
    return out


def score_protocol(kit_dir):
    path = os.path.join(kit_dir, "protocol_check.csv")
    _, rows = _read_csv(path)
    out = {"design": "human review and correction of the model's reading, with the model's values visible: NOT blind "
                     "ground truth", "papers": len(rows)}
    fields = {}

    def val(s):
        s = low(s)
        if s in ("", "?"):
            return None
        return "none" if s in ("none", "null", "not stated", "-", "no") else s
    for f in ("K", "seeds", "kind", "shares_instances", "sd_over"):
        filled = [r for r in rows if val(r.get(f"human_{f}")) is not None]
        same = [r for r in filled if val(r[f"human_{f}"]) == "same" or val(r[f"human_{f}"]) == (val(r.get(f"model_{f}")) or "none")]
        k_rows = [r for r in filled if (r.get("model_K") or "").strip()]
        fields[f] = {"filled": len(filled), "model_confirmed": rate(len(same), len(filled)),
                     "corrected": len(filled) - len(same),
                     "on_the_8_K_papers": rate(sum(1 for r in k_rows if r in same), len(k_rows))}
    out["fields"] = fields
    out["status"] = "scored" if any(v["filled"] for v in fields.values()) else "no_human_labels"
    out["K_papers_labelled"] = sum(1 for r in rows if val(r.get("human_K")) is not None and (r.get("model_K") or "").strip())
    return out


# ======================================================================= C3, C4
def score_runcount(kit_dir, keys_dir, reg, errors, warnings):
    kpath = os.path.join(keys_dir, "runcount_key.json")
    if not os.path.exists(kpath):
        errors.append("machine_keys/runcount_key.json missing")
        return None
    key = json.load(open(kpath, encoding="utf-8"))["items"]
    raws = load_raw_kit(os.path.join(kit_dir, "runcount_disputes"), "runcount_disputes", set(key), errors, warnings)
    out = {"status": "no_human_labels", "items": len(key), "annotators": sorted(raws),
           "rule": "testable boxed reference items where parser vs reader1, parser vs reader2 or reader1 vs reader2 "
                   "disagree on the run count (exact join on the reference item id)"}
    items = json.load(open(os.path.join(kit_dir, "runcount_disputes", "items.json"), encoding="utf-8"))
    meta = {it["id"]: it for it in items}
    rows = []
    prim = None
    if raws:
        prim, sec, indep = roles("runcount_disputes", raws, reg, errors, warnings)
        out["independence"] = indep
    L = raws.get(prim, {}) if prim else {}
    agree = Counter()
    n_dec = 0
    for rid in sorted(key):
        k = key[rid]
        lb = L.get(rid)
        hv = parse_value(lb.get("n_runs")) if lb else ("missing", None)
        decided = hv[0] in ("num", "none")
        n_dec += decided
        m = {"parser": k["parser"]["n_runs"], "reader1": parse_value(k["reader1"]["n_runs"]),
             "reader2": parse_value(k["reader2"]["n_runs"])}
        m["reader1"] = m["reader1"][1] if m["reader1"][0] == "num" else (None if m["reader1"][0] == "none" else "unclear")
        m["reader2"] = m["reader2"][1] if m["reader2"][0] == "num" else (None if m["reader2"][0] == "none" else "unclear")
        ag = {}
        for name, v in m.items():
            ag[name] = (v != "unclear" and same_num(hv[1], v)) if decided else None
            if decided and ag[name]:
                agree[name] += 1
        if decided and not any(ag.values()):
            agree["none_of_the_three"] += 1
        rows.append({"id": rid, "orig_id": k["orig_id"], "paper": k["paper"], "table": k["table"], "pdf_page": k["page"] + 1,
                     "pdf_url": meta[rid].get("pdf_url"), "disputed_by": ";".join(k["disputed_by"]),
                     "human_n_runs": (lb or {}).get("n_runs", ""), "human_unit": (lb or {}).get("n_unit", ""),
                     "human_applies": (lb or {}).get("applies_to_table", ""), "human_source": (lb or {}).get("n_source", ""),
                     "human_passage": (lb or {}).get("passage", ""), "human_location": (lb or {}).get("passage_location", ""),
                     "human_confidence": (lb or {}).get("confidence", ""),
                     "parser_n_runs": m["parser"], "reader1_n_runs": m["reader1"], "reader2_n_runs": m["reader2"],
                     "human_agrees": ";".join(n for n, v in ag.items() if v) if decided else ""})
    if L:
        out["status"] = "scored"
        out["primary"] = prim
        out["decided"] = n_dec
        out["unclear_or_missing"] = len(key) - n_dec
        out["human_agrees_with"] = {n: rate(agree[n], n_dec) for n in ("parser", "reader1", "reader2")}
        out["human_agrees_with_none"] = rate(agree["none_of_the_three"], n_dec)
        out["passages_quoted"] = sum(1 for r in rows if r["human_passage"].strip())
    out["_rows"] = rows
    return out


def score_bartype(kit_dir, keys_dir, reg, errors, warnings):
    kpath = os.path.join(keys_dir, "bartype_key.json")
    if not os.path.exists(kpath):
        return {"status": "not_built"}
    key = json.load(open(kpath, encoding="utf-8"))["items"]
    raws = load_raw_kit(os.path.join(kit_dir, "bartype_random"), "bartype_random", set(key), errors, warnings)
    out = {"status": "no_human_labels", "tables": len(key),
           "core_tables": sum(1 for v in key.values() if v["in_core"]), "annotators": sorted(raws)}
    if not raws:
        return out
    prim, sec, indep = roles("bartype_random", raws, reg, errors, warnings)
    if prim is None:
        return out
    L = raws[prim]
    done = [t for t in sorted(key) if t in L and L[t].get("bar_kind") and L[t].get("table_found") == "y"]
    taken = sorted({key[t]["paper_rank"] for t in done})
    if taken and taken != list(range(1, max(taken) + 1)):
        warnings.append(f"bartype_random: labelled papers are not a prefix of the seeded order (ranks {taken}); "
                        f"the set is then not a simple random sample")
    kinds = Counter(low(L[t]["bar_kind"]) for t in done)
    flips = Counter()
    n_cmp = 0
    for t in done:
        hk = {"sd": "std", "se": "sem", "ci": "ci", "not_stated": "unknown", "conflicting": "unknown"}.get(low(L[t]["bar_kind"]))
        for c in key[t]["parser"]:
            if not c["testable"] or c["dispersion_kind"] != "unknown":
                continue
            n_cmp += 1
            before = "not_separable" if c["p"] >= ALPHA else "separable"
            if hk is None:
                flips[f"{before}->not_convertible"] += 1
                continue
            tt = test_comparison({"gap": abs(c["winner"] - c["runner_up"]), "winner_dispersion": c["winner_dispersion"],
                                  "runner_dispersion": c["runner_dispersion"], "dispersion_kind": hk, "n_runs": c["n_runs"]})
            flips[f"{before}->{verdict(tt)}"] += 1
    out.update({"status": "scored", "primary": prim, "independence": indep, "tables_decided": len(done),
                "papers_decided": len({key[t]['paper'] for t in done}), "paper_ranks_labelled": taken,
                "bar_kind": dict(kinds),
                "stated_somewhere": rate(sum(v for k_, v in kinds.items() if k_ not in ("not_stated", "conflicting")), len(done)),
                "se_or_ci": rate(kinds["se"] + kinds["ci"], len(done)),
                "parser_comparisons_on_these_tables_with_unlabelled_bars": n_cmp,
                "verdicts_if_the_human_bar_kind_is_applied_to_the_parser_values": dict(flips),
                "note": "verdict changes mix the human's bar kind with the parser's values; a sensitivity, not a re-reading",
                "passages_quoted": sum(1 for t in done if (L[t].get("passage") or "").strip())})
    return out


# ======================================================================= report and rebuttal
def _slot_values(S):
    """Flat slot -> text map for the rebuttal template; only from human data."""
    v = {}
    A = S.get("A_comparison_blind") or {}
    if A.get("status") == "scored":
        v["A_annotator"] = A["primary"]
        v["A_independent"] = "yes" if A["independence"].get(A["primary"]) == "n" else "NO (declared exposure to machine output)"
        v["A_items"] = str(A["coverage"]["labelled_by_primary"])
        v["A_papers"] = str(A["coverage"]["papers_labelled"])
        v["A_testable_items"] = str(A["by_stratum"]["testable"]["labelled"])
        v["A_nobar_items"] = str(A["by_stratum"]["no_bar"]["labelled"])
        for r in A["_agree_rows"]:
            if r["comparison"] == "human_vs_parser" and r["stratum"] == "testable":
                v[f"A_T_{r['field']}"] = fmt({**r, "wilson": [r["wilson_lo"], r["wilson_hi"]] if r["n"] else None,
                                              "boot": [r["boot_lo"], r["boot_hi"]] if r.get("boot_lo") != "" else None,
                                              "n_clusters": r["n_papers"]})
        T = A["by_stratum"]["testable"]
        v["A_T_human_testable"] = T["human_testable"]["text"]
        v["A_T_not_separable"] = T["human_not_separable"]["text"]
        v["A_T_parser_not_separable_same"] = T["parser_not_separable_same_items"]["text"]
        v["A_T_verdict_agree"] = T["verdict_agreement_with_parser"]["text"]
        v["A_T_bold_not_best"] = str(T["bold_not_best_by_printed_means"])
        v["A_B_no_bar"] = (A["by_stratum"]["no_bar"].get("no_bar_on_either_side") or {}).get("text", "N/A")
        hh = A.get("human_vs_human")
        if hh:
            v["A_hh_items"] = str(hh["items_both"])
            for r in A["_agree_rows"]:
                if r["comparison"] == "human_vs_human" and r["field"] in ("winner_mean", "runner_mean", "n_runs", "disp_type", "verdict"):
                    v[f"A_hh_{r['field']}"] = f"{r['k']}/{r['n']}" + (f" (kappa {r['kappa']})" if r.get("kappa") not in ("", None) else "")
    B = S.get("B_page_detection") or {}
    if B.get("status") == "scored":
        c = B["strata"]["caption_pilot"]
        v["B_pages"] = str(c["pages_labelled"])
        v["B_groups"] = str(c["human_eligible_groups"])
        v["B_zero_pages"] = str(c["pages_with_zero_eligible_groups"])
        for name in ("parser", "census_reader"):
            e = c["comparators"].get(name)
            if e:
                v[f"B_recall_{name}"] = e["recall"]["text"]
                v[f"B_precision_{name}"] = e["precision"]["text"]
        fn = c["comparators"].get("parser", {}).get("false_negatives", [])
        v["B_fn_examples"] = "; ".join(f"{x['page']} {x['table']} '{x['group']}' {x['bold_value']}" for x in fn[:3]) or "none"
        n = B["strata"].get("noncaption", {})
        if n.get("pages_labelled"):
            v["B_nc_pages"] = str(n["pages_labelled"])
            v["B_nc_groups"] = str(n["human_eligible_groups"])
    C1 = S.get("C1_empty_pages") or {}
    if C1.get("status") == "scored":
        for kind in ("pilot_empty", "orientation_none"):
            v[f"C1_{kind}"] = f"{C1[kind]['yes_census_reader_missed_a_group']} of {C1[kind]['labelled']}"
    C2 = S.get("C2_protocol") or {}
    if C2.get("status") == "scored":
        v["C2_K"] = C2["fields"]["K"]["on_the_8_K_papers"]["text"]
    C3 = S.get("C3_runcount_disputes") or {}
    if C3.get("status") == "scored":
        v["C3_decided"] = f"{C3['decided']} of {C3['items']}"
        for n in ("parser", "reader1", "reader2"):
            v[f"C3_{n}"] = C3["human_agrees_with"][n]["text"]
    C4 = S.get("C4_bartype_random") or {}
    if C4.get("status") == "scored":
        v["C4_tables"] = f"{C4['tables_decided']} tables in {C4['papers_decided']} papers"
        v["C4_se_or_ci"] = C4["se_or_ci"]["text"]
        v["C4_not_stated"] = str(C4["bar_kind"].get("not_stated", 0))
        v["C4_flips"] = ", ".join(f"{k}: {n}" for k, n in sorted(C4["verdicts_if_the_human_bar_kind_is_applied_to_the_parser_values"].items())) or "none"
    return v


TEMPLATE_SLOTS = (
    {"A_annotator", "A_independent", "A_items", "A_papers", "A_testable_items", "A_nobar_items",
     "A_T_human_testable", "A_T_not_separable", "A_T_parser_not_separable_same", "A_T_verdict_agree",
     "A_T_bold_not_best", "A_B_no_bar", "A_hh_items",
     "B_pages", "B_groups", "B_zero_pages", "B_fn_examples", "B_nc_pages", "B_nc_groups",
     "C1_pilot_empty", "C1_orientation_none", "C2_K", "C3_decided", "C3_parser", "C3_reader1", "C3_reader2",
     "C4_tables", "C4_se_or_ci", "C4_not_stated", "C4_flips"}
    | {f"A_T_{f}" for f, *_ in A_FIELD_SPECS}
    | {f"A_hh_{f}" for f in ("winner_mean", "runner_mean", "n_runs", "disp_type", "verdict")}
    | {f"B_{m}_{n}" for m in ("recall", "precision") for n in ("parser", "census_reader")})


def fill_template(text, values):
    def rep(m):
        k = m.group(1)
        return values.get(k, f"[PENDING: {k} needs human labels]")
    return re.sub(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", rep, text)


def write_report(S, out_dir):
    L = ["# AAMAS submission 3154: independent human validation", "",
         f"Generated {S['generated']} by `python aamas/human_validation_score.py`. Every proportion is "
         "numerator/denominator with a Wilson 95% interval (descriptive) and, where items share a paper or page, "
         "a cluster bootstrap over papers or pages. N/A means no data, never zero.", ""]
    if S["errors"]:
        L += ["## Validation errors (scores below are incomplete)", ""] + [f"- {e}" for e in S["errors"]] + [""]
    if S["warnings"]:
        L += ["## Warnings", ""] + [f"- {w}" for w in S["warnings"]] + [""]
    A = S.get("A_comparison_blind") or {}
    L += ["## A. Blind re-reading of the 140 reference comparisons", ""]
    if A.get("status") != "scored":
        L += ["No human labels yet (`audits/human_aamas/comparison_blind/raw/` is empty). Nothing below is filled from a machine.", ""]
    else:
        cv = A["coverage"]
        L += [f"Primary annotator `{A['primary']}` (independent of machine output: "
              f"{'yes' if A['independence'].get(A['primary']) == 'n' else 'NOT DECLARED/NO'}); "
              f"{cv['labelled_by_primary']} items labelled ({cv['labelled_core']} of the 100 core), "
              f"{cv['papers_labelled']} papers; by stratum {cv['labelled_by_stratum']}. "
              f"Void (no box) {cv['void_no_box']}, incomplete {cv['missing_answers']}, paper not opened {cv['paper_not_opened']}, "
              f"run count ambiguous or conflicting {cv['run_count_ambiguous_or_conflicting']}.", "",
              f"Unclear answers by field: {cv['unclear_answers_by_field']}.", "",
              "Strata are reported separately: the testable stratum is oversampled on purpose and neither stratum is "
              "representative of the corpus.", ""]
        for stratum in ("testable", "no_bar"):
            L += [f"### Stratum `{stratum}`: field-by-field agreement", "",
                  "| field | human vs parser | human vs reader 1 | human vs reader 2 |", "|---|---|---|---|"]
            fields = [f for f, *_ in A_FIELD_SPECS]
            idx = {(r["comparison"], r["field"]): r for r in A["_agree_rows"] if r["stratum"] == stratum}
            for f in fields:
                cells = []
                for c in ("human_vs_parser", "human_vs_reader1", "human_vs_reader2"):
                    r = idx.get((c, f))
                    cells.append("--" if r is None else (f"{r['k']}/{r['n']} ({r['pct']}%)" if r["n"] else "N/A"))
                L.append(f"| {f} | " + " | ".join(cells) + " |")
            T = A["by_stratum"][stratum]
            L += ["", "The parser has no explicit reading of `results_table` or `bold_unique`: every reference item "
                  "is a claim it made, so agreement there is the share of items the person accepts as such a claim. "
                  "Bar values are compared only where both sides read a bar; bar presence is its own row.",
                  "", f"Human-testable: {T['human_testable']['text']}. Categories: {T['categories']}.", ""]
            if stratum == "testable":
                L += [f"Welch's t from the human-read values: not separable at the stated run count {T['human_not_separable']['text']}; "
                      f"the parser's verdict on the same items {T['parser_not_separable_same_items']['text']}; "
                      f"same verdict {T['verdict_agreement_with_parser']['text']}; 2x2 (human|parser) {T['verdict_2x2_human_by_parser']}. "
                      f"Unlabelled bars read as standard errors instead: {T['unlabelled_bars_read_as_se']}. "
                      f"Bold cell not the best (or tied) by the printed means: {T['bold_not_best_by_printed_means']}.", ""]
            else:
                L += [f"No error bar on either cell, as the parser said: {T.get('no_bar_on_either_side', {}).get('text', 'N/A')}.", ""]
        L += ["### Testability: human category by parser", "", "```", json.dumps(A["testability_confusion"], indent=1), "```", ""]
        if A.get("human_vs_human"):
            hh = A["human_vs_human"]
            L += [f"### Human against human ({A['primary']} vs {hh['second']}, {hh['items_both']} items, {hh['papers_both']} papers)", "",
                  "| field | agreement | kappa |", "|---|---|---|"]
            for r in A["_agree_rows"]:
                if r["comparison"] == "human_vs_human":
                    L.append(f"| {r['field']} | {r['k']}/{r['n']}" + (f" ({r['pct']}%)" if r["n"] else " (N/A)") + f" | {r.get('kappa', '')} |")
            L.append("")
    B = S.get("B_page_detection") or {}
    L += ["## B. Page-level detection on random caption pages", ""]
    if B.get("status") != "scored":
        L += ["No human labels yet (`audits/human_aamas/page_detection/raw/` is empty).", ""]
    else:
        L += [f"Scope: {B['scope']}.", ""]
        for frame, res in B["strata"].items():
            L += [f"### Frame `{frame}`: {res['pages_labelled']} of {res['pages_in_kit']} pages labelled "
                  f"({res['pages_unclear']} unclear), {res['papers']} papers", "",
                  f"Human eligible groups: {res['human_eligible_groups']} (with an unclear bold rule: "
                  f"{res['human_eligible_groups_incl_unclear_bold_rule']}); pages with none: {res['pages_with_zero_eligible_groups']}; "
                  f"single-bold groups not eligible: {res['human_single_bold_groups_not_eligible']}.", "",
                  "| comparator | recall (human groups it lists) | precision (its groups the human lists) |", "|---|---|---|"]
            for name, e in res["comparators"].items():
                L.append(f"| {name} | {e['recall']['text']} | {e['precision']['text']} |")
            pe = res["comparators"].get("parser", {})
            if pe.get("recall_weighted_all_caption_pages"):
                w = pe["recall_weighted_all_caption_pages"]
                L += ["", f"Parser recall weighted to all caption pages: {w['pct']}% (bootstrap {w['boot']})."]
            fn = pe.get("false_negatives", [])
            if fn:
                L += ["", "Parser false negatives (first 10):", ""] + [f"- {x['page']} (PDF p. {x['pdf_page']}) {x['table']} '{x['group']}' bold {x['bold_value']}" for x in fn[:10]]
            L.append("")
        L += [f"Share of eligible groups on non-caption pages: {B['share_of_groups_on_noncaption_pages']}", ""]
    C1 = S.get("C1_empty_pages") or {}
    L += ["## C1. The 35 hard-case pages (not an accuracy sample)", "", f"Images: {C1.get('image_status')}.", ""]
    if C1.get("status") == "scored":
        for kind in ("pilot_empty", "orientation_none"):
            d = C1[kind]
            L.append(f"- {kind}: {d['labelled']} of {d['of']} labelled; yes {d['yes_census_reader_missed_a_group']}, "
                     f"no {d['no']}, unclear {d['unclear']}; groups on yes pages {d['groups_on_yes_pages']}")
        L.append("")
    else:
        L += ["No labels yet (`audits/human_aamas/empty_pages_labels.csv`).", ""]
    C2 = S.get("C2_protocol") or {}
    L += ["## C2. Protocol review of the 20 rate papers (unblinded: model values visible)", ""]
    if C2.get("status") == "scored":
        L += ["| field | filled | model confirmed | on the 8 K papers |", "|---|---|---|---|"]
        for f, d in C2["fields"].items():
            L.append(f"| {f} | {d['filled']} | {d['model_confirmed']['text']} | {d['on_the_8_K_papers']['text']} |")
        L.append("")
    else:
        L += ["No human columns filled yet in `audits/human_aamas/protocol_check.csv`.", ""]
    C3 = S.get("C3_runcount_disputes") or {}
    L += ["## C3. The 18 disputed run counts", "", f"Rule: {C3.get('rule')}.", ""]
    if C3.get("status") == "scored":
        L += [f"Decided {C3['decided']} of {C3['items']}; human agrees with the parser {C3['human_agrees_with']['parser']['text']}, "
              f"reader 1 {C3['human_agrees_with']['reader1']['text']}, reader 2 {C3['human_agrees_with']['reader2']['text']}, "
              f"none of them {C3['human_agrees_with_none']['text']}. Passages quoted: {C3['passages_quoted']}. "
              "Per item: `runcount_decisions.csv`.", ""]
    else:
        L += ["No labels yet.", ""]
    C4 = S.get("C4_bartype_random") or {}
    L += ["## C4. Random set of unlabelled or disputed bar kinds", ""]
    if C4.get("status") == "scored":
        L += [f"{C4['tables_decided']} tables in {C4['papers_decided']} papers (ranks {C4['paper_ranks_labelled']}). Bar kind: "
              f"{C4['bar_kind']}. Stated somewhere in the paper: {C4['stated_somewhere']['text']}; SE or CI: {C4['se_or_ci']['text']}. "
              f"Verdicts of the {C4['parser_comparisons_on_these_tables_with_unlabelled_bars']} parser comparisons on these "
              f"tables if the human's bar kind is applied: {C4['verdicts_if_the_human_bar_kind_is_applied_to_the_parser_values']} "
              f"({C4['note']}).", ""]
    else:
        L += ["No labels yet." if C4.get("status") == "no_human_labels" else "Kit not built.", ""]
    L += ["## What these numbers can and cannot say", "",
          "- A p-value at or above 0.05 means the printed means, bars and run count do not separate the two methods. "
          "It does not show that the claimed superiority is false.",
          "- The reference strata and the hard-case pages were selected on purpose; none of their rates is a corpus rate, "
          "a lower bound or an upper bound.",
          "- Page-level recall and precision hold for the pilot caption-page frame (and the non-caption stratum when labelled).",
          "- Labels from an annotator who had seen machine output are reported, but not as independent.", ""]
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(L))


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted(_jsonable(v) for v in x)
    if isinstance(x, Counter):
        return dict(x)
    return x


def run(kit_dir, out_dir, template=None):
    errors, warnings = [], []
    reg = load_registry(kit_dir, warnings)
    keys_dir = os.path.join(kit_dir, "machine_keys")
    S = {"generated": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
         "kit_dir": rel(kit_dir),
         "conventions": {"alpha": ALPHA, "bootstrap": {"reps": BOOT_REPS, "seed": BOOT_SEED, "interval": "percentile 2.5/97.5"},
                         "wilson": "95%, descriptive", "numbers_match": "relative tolerance 1e-6",
                         "kind_map": KIND_MAP}}
    S["A_comparison_blind"] = score_comparison(kit_dir, keys_dir, reg, errors, warnings)
    S["B_page_detection"] = score_pages(kit_dir, keys_dir, reg, errors, warnings)
    S["C1_empty_pages"] = score_empty_pages(kit_dir) if os.path.exists(os.path.join(kit_dir, "empty_pages", "items.json")) else None
    S["C2_protocol"] = score_protocol(kit_dir) if os.path.exists(os.path.join(kit_dir, "protocol_check.csv")) else None
    S["C3_runcount_disputes"] = score_runcount(kit_dir, keys_dir, reg, errors, warnings)
    S["C4_bartype_random"] = score_bartype(kit_dir, keys_dir, reg, errors, warnings)
    for kit in ("comparison_blind", "page_detection", "runcount_disputes", "bartype_random"):
        for name in ("manifest.json",):
            p = os.path.join(kit_dir, kit, name)
            if os.path.exists(p):
                S.setdefault("manifests", {})[kit] = {k: v for k, v in json.load(open(p, encoding="utf-8")).items()
                                                      if k in ("seeds", "counts", "sampling_fractions", "pool", "draw")}
    S["errors"], S["warnings"] = errors, warnings
    S["human_labels_present"] = any((S.get(k) or {}).get("status") == "scored"
                                    for k in ("A_comparison_blind", "B_page_detection", "C1_empty_pages", "C2_protocol",
                                              "C3_runcount_disputes", "C4_bartype_random"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(_jsonable(S), fh, indent=1, ensure_ascii=False, default=str)
    A = S["A_comparison_blind"] or {}
    acols = ["comparison", "annotator", "stratum", "field", "k", "n", "pct", "wilson_lo", "wilson_hi", "n_papers",
             "boot_lo", "boot_hi", "kappa", "excluded"]
    with open(os.path.join(out_dir, "agreement_by_field.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=acols, lineterminator="\n")
        w.writeheader()
        for r in A.get("_agree_rows", []):
            w.writerow({c: (json.dumps(r[c], sort_keys=True) if c == "excluded" else ("N/A" if c == "pct" and r[c] is None else r.get(c, "")))
                        for c in acols})
    vcols = ["id", "orig_id", "stratum", "paper", "table", "pdf_page", "labelled", "human_category", "human_winner",
             "human_runner", "human_winner_disp", "human_runner_disp", "human_kind", "human_n_runs", "human_p", "human_test",
             "human_verdict", "human_verdict_unlabelled_as_se", "parser_p", "parser_verdict", "reader1_verdict",
             "reader2_verdict", "human_agrees_with_parser"]
    with open(os.path.join(out_dir, "verdicts.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=vcols, lineterminator="\n")
        w.writeheader()
        for r in A.get("_verdict_rows", []):
            if r["labelled"] == "y":
                w.writerow({c: r.get(c, "") for c in vcols})
    dcols = ["kit", "item", "orig_id", "stratum", "paper", "annotator", "field", "human_value", "other", "other_value",
             "evidence", "comment"]
    with open(os.path.join(out_dir, "disagreements.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=dcols, lineterminator="\n")
        w.writeheader()
        for r in A.get("_dis_rows", []):
            w.writerow({c: r.get(c, "") for c in dcols})
    C3 = S["C3_runcount_disputes"] or {}
    if C3.get("_rows"):
        cols = list(C3["_rows"][0].keys())
        with open(os.path.join(out_dir, "runcount_decisions.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(C3["_rows"])
    B = S["B_page_detection"] or {}
    if B.get("_match_rows"):
        cols = list(B["_match_rows"][0].keys())
        with open(os.path.join(out_dir, "page_groups_matched.csv"), "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
            w.writeheader()
            w.writerows(B["_match_rows"])
    write_report(S, out_dir)
    template = template or os.path.join(kit_dir, "REBUTTAL_TEMPLATE.md")
    if os.path.exists(template):
        text = open(template, encoding="utf-8").read()
        with open(os.path.join(out_dir, "rebuttal_filled.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(fill_template(text, _slot_values(S)))
    return S


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--kit-dir", default=os.path.join(ROOT, "audits", "human_aamas"))
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "aamas", "human_validation"))
    ap.add_argument("--require-labels", action="store_true")
    args = ap.parse_args(argv)
    S = run(args.kit_dir, args.out)
    for e in S["errors"]:
        print("ERROR:", e)
    for w in S["warnings"]:
        print("warning:", w)
    print(f"wrote {args.out}/summary.json, agreement_by_field.csv, verdicts.csv, disagreements.csv, report.md")
    if not S["human_labels_present"]:
        print("No human label file is present: every human number is N/A. Human validation has NOT been done.")
    if S["errors"]:
        return 2
    if args.require_labels and not S["human_labels_present"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
