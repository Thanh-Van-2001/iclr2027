"""Every derived number of the metaheuristics paper, from
data/extracted_oa.jsonl (the frozen parser on the open-access corpus), the
text scans, the kind labels and the reader audits. Same functions as the
ICLR and AAMAS studies where the question is the same; new here are the
run-count and statistical-test readings of this field's convention.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, os.path.join(HERE, "..", "aamas"))
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import analyse  # noqa: E402
import extra_stats  # noqa: E402
import make_all  # noqa: E402
from make_all_aamas import (load_unique, readings, per_paper_failure, exact_copies, _rates,  # noqa: E402
                            caption_assertion, uncertainty_anywhere, ddof_reading, big_n_and_largest)
from sensitivity import (checkability_span, correlation_sensitivity, error_bar_meaning,  # noqa: E402
                         paper_level_crosstab, run_count_scope)
from paperengine.stats import wilson_interval  # noqa: E402

OUT = "out/swevo"
EXTRACTED = os.environ.get("SWEVO_EXTRACTED", "data/extracted_oa.jsonl")


def _boot_share(items: list, reps: int = 2000, seed: int = 0) -> list | None:
    """Cluster bootstrap over papers of a share of comparisons; items are
    (paper, bool) pairs."""
    import random
    by = collections.defaultdict(list)
    for paper, flag in items:
        by[paper].append(flag)
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


def row_bold_readings(cs: list, records: list) -> dict:
    """This format sets header rows in bold, and many papers set the proposed
    method's whole row in bold. The parser's unit assumes bold marks a cell;
    a comparison whose winner sits in a row whose every numeric cell is bold
    comes from one of those two conventions. Two readings: without the
    comparisons whose winner row is the table's first (header) row, and
    without every all-bold-row comparison."""
    recs = {r["id"]: r for r in records}
    header, rowbold = [], []
    for c in cs:
        table = next((t for t in recs[c["paper"]]["tables"]
                      if t.get("page") == c["page"] and (t.get("caption") or "") == (c.get("caption") or "")), None)
        if table is None:
            continue
        cells = table["cells"]
        wy = c["winner_cell"]["y"]
        row = [x for x in cells if abs(x["y"] - wy) < 1.5]
        first = abs(min(x["y"] for x in cells) - wy) < 1.5
        allbold = len(row) > 1 and all(x["bold"] for x in row)
        c["_row_bold"] = allbold
        c["_header_row"] = allbold and first
        if allbold:
            rowbold.append(c)
            if first:
                header.append(c)
    keep_h = [c for c in cs if not c.get("_header_row")]
    keep_r = [c for c in cs if not c.get("_row_bold")]
    return {"header_row_only": _rates(header), "without_header_row": _rates(keep_h),
            "row_bold_only": _rates(rowbold), "without_row_bold": _rates(keep_r),
            "header_row_papers": len({c["paper"] for c in header}),
            "row_bold_papers": len({c["paper"] for c in rowbold}),
            "papers_all_row_bold": sum(1 for p in {c["paper"] for c in cs}
                                       if all(c.get("_row_bold") for c in cs if c["paper"] == p))}


def by_group(cs: list, label: dict, name: str) -> dict:
    """The census shares and the failure rate by a per-paper label."""
    out = {}
    for lab in sorted(set(label.values())):
        sub = [c for c in cs if label.get(c["paper"]) == lab]
        r = _rates(sub)
        r["papers_labelled"] = sum(1 for v in label.values() if v == lab)
        r["claim_papers"] = len({c["paper"] for c in sub})
        r["ci_neither"] = _boot_share([(c["paper"], c["winner_dispersion"] is None and c["runner_dispersion"] is None) for c in sub])
        r["ci_testable"] = _boot_share([(c["paper"], bool(c.get("test"))) for c in sub])
        out[lab] = r
    return {name: out}


def stat_tests(cs: list, scan: dict) -> dict:
    """The convention's own test: which papers name a statistical test, and
    how the bold cells of those papers fare under Welch on the printed
    numbers, against papers that name none."""
    t = [c for c in cs if c.get("test")]
    papers_t = {c["paper"] for c in t}
    named = {p for p in papers_t if scan.get(p, {}).get("any_test")}
    kinds = collections.Counter()
    for p in papers_t:
        for k, v in scan.get(p, {}).get("tests", {}).items():
            if v:
                kinds[k] += 1
    a = [c for c in t if c["paper"] in named]
    b = [c for c in t if c["paper"] not in named]
    markers = {p for p in papers_t if scan.get(p, {}).get("tests", {}).get("plus_minus_equal")}
    return {"testable_papers": len(papers_t), "papers_naming_a_test": len(named),
            "pct_papers_naming_a_test": round(100 * len(named) / max(len(papers_t), 1), 1),
            "test_kinds_among_testable_papers": dict(kinds),
            "papers_with_plus_equal_minus": len(markers),
            "named": _rates(a), "unnamed": _rates(b),
            "all_papers_naming_a_test": sum(1 for v in scan.values() if v.get("any_test")),
            "all_papers": sum(1 for v in scan.values() if "error" not in v)}


def run_counts(cs: list, scan: dict) -> dict:
    """The run count as the parser reads it beside the table and as the
    text scan reads it anywhere in the paper; the thirty-run convention."""
    t = [c for c in cs if c.get("test")]
    parser_n = collections.Counter(c["n_runs"] for c in t if c.get("n_runs"))
    scan_n = collections.Counter(v["run_modal"] for v in scan.values() if v.get("run_modal"))
    agree = disagree = 0
    for c in t:
        s_ = scan.get(c["paper"], {}).get("run_modal")
        if c.get("n_runs") and s_:
            agree += (c["n_runs"] == s_)
            disagree += (c["n_runs"] != s_)
    thirty = [c for c in t if c.get("n_runs") == 30]
    return {"parser_counts": parser_n.most_common(8), "scan_counts": scan_n.most_common(8),
            "papers_stating_runs_in_text": sum(1 for v in scan.values() if v.get("run_modal")),
            "papers_scanned": sum(1 for v in scan.values() if "error" not in v),
            "pct_papers_stating_runs": round(100 * sum(1 for v in scan.values() if v.get("run_modal")) / max(sum(1 for v in scan.values() if "error" not in v), 1), 1),
            "parser_scan_agree": agree, "parser_scan_disagree": disagree,
            "thirty_runs": _rates(thirty),
            "pct_testable_at_thirty": round(100 * len(thirty) / max(len(t), 1), 1)}


def scan_run_count_reading(cs: list, scan: dict) -> dict:
    """The testable comparisons re-tested at the run count the text scan
    reads as the paper's modal statement, where it has one, instead of the
    parser's smallest count; a reading of the run-count rule, not of the
    parser."""
    from analyze import test_comparison
    out = []
    changed = 0
    for c in cs:
        if not c.get("test"):
            continue
        n = scan.get(c["paper"], {}).get("run_modal")
        if not n:
            continue
        d = dict(c, n_runs=int(n))
        t = test_comparison(d)
        if t is None:
            continue
        changed += (int(n) != c.get("n_runs"))
        out.append((c["paper"], t["p"] >= 0.05))
    n = len(out)
    return {"n": n, "papers": len({p for p, _ in out}), "changed_count": changed,
            "pct_fail": round(100 * sum(f for _, f in out) / n, 1) if n else None,
            "ci_fail": _boot_share(out) if n else None}


BOLD_SENTENCE = re.compile(r"bold", re.I)
BOLD_BEST = re.compile(r"best|optimal|lowest|highest|superior|minimum|maximum|top", re.I)
BOLD_SIG = re.compile(r"statistic|signific", re.I)


def bold_rule_of(x: dict) -> str:
    """The paper's stated bold rule, from the model's field and, where the
    model filed "not stated" while quoting a sentence that states one, from
    that sentence (a review of the first submission found 23 such papers)."""
    b = str(x.get("bold_rule") or "not stated").lower()
    sent = str(x.get("bold_sentence") or "")
    if BOLD_SIG.search(b):
        return "statistically best"
    if BOLD_BEST.search(b):
        return "best"
    if "propos" in b or "our" in b:
        return "proposed"
    if BOLD_SENTENCE.search(sent):
        if BOLD_SIG.search(sent):
            return "statistically best"
        if BOLD_BEST.search(sent):
            return "best"
        if re.search(r"propos|our (?:method|algorithm|approach)", sent, re.I):
            return "proposed"
    return "not stated" if "not stated" in b or b in ("", "none") else "other"


def test_reader_blocks(cs: list, kinds: dict) -> dict:
    """The model's full-text reading (swevo/test_reader.py) aggregated over
    its three paper sets: run counts, where the deviation sits, which test,
    on what, paired or not, per-cell verdicts, what bold means."""
    import glob
    import time
    d = {}
    for path in sorted(glob.glob(f"{OUT}/test_reader_part*.json")) + [f"{OUT}/test_reader.json"]:
        if not os.path.exists(path):
            continue
        for _ in range(5):
            try:
                d.update(json.load(open(path, encoding="utf-8")))
                break
            except json.JSONDecodeError:
                time.sleep(1)
    d = {k: v for k, v in d.items() if "parse_error" not in v}
    if not d:
        return {}
    sets = json.load(open(f"{OUT}/test_reader_set.json", encoding="utf-8")) if os.path.exists(f"{OUT}/test_reader_set.json") else {}
    scan = json.load(open(f"{OUT}/text_scan.json", encoding="utf-8")) if os.path.exists(f"{OUT}/text_scan.json") else {}
    noted = [p for p in d if scan.get(p, {}).get("bold_note")]
    note_block = {"note_papers_read": len(noted),
                  "note_filed_statistically_best": sum(1 for p in noted if bold_rule_of(d[p]) == "statistically best"),
                  "note_filed_not_stated": sum(1 for p in noted if bold_rule_of(d[p]) == "not stated"),
                  "sentence_rescued": sum(1 for x in d.values() if "not stated" in str(x.get("bold_rule") or "not stated").lower() and bold_rule_of(x) != "not stated")}
    testable = {c["paper"] for c in cs if c.get("test")}
    out = {}
    groups = {"all": list(d), "testable": [p for p in d if p in testable],
              "new_optimizer": [p for p in d if kinds.get(p) == "new_optimizer"],
              "random_other": [p for p in d if p in set(sets.get("random_other", []))]}
    for name, ids in groups.items():
        n = len(ids)
        if not n:
            continue
        v = [d[p] for p in ids]
        runs = collections.Counter(x.get("runs") for x in v if isinstance(x.get("runs"), int))
        tests = collections.Counter(t for x in v for t in (x.get("test") or []) if t != "none")
        named = sum(1 for x in v if any(t != "none" for t in (x.get("test") or [])))
        layout = collections.Counter(str(x.get("std_layout") or "unsure") for x in v)
        bold = collections.Counter()
        for x in v:
            bold[bold_rule_of(x)] += 1
        bench = collections.Counter(t for x in v for t in (x.get("benchmark") or []))
        out[name] = {
            "papers": n,
            "runs_stated": sum(runs.values()), "pct_runs_stated": round(100 * sum(runs.values()) / n, 1),
            "runs_thirty": runs.get(30, 0), "pct_runs_thirty": round(100 * runs.get(30, 0) / n, 1),
            "runs_top": runs.most_common(6),
            "layout": dict(layout), "pct_layout": {k: round(100 * c / n, 1) for k, c in layout.items()},
            "pct_std_off_cell": round(100 * (layout.get("separate_row", 0) + layout.get("separate_column", 0)) / n, 1),
            "test_named": named, "pct_test_named": round(100 * named / n, 1),
            "tests": tests.most_common(10),
            "test_on": dict(collections.Counter(str(x.get("test_on") or "unsure") for x in v)),
            "paired": dict(collections.Counter(str(x.get("paired") or "unsure") for x in v)),
            "markers": sum(1 for x in v if str(x.get("markers", "")).lower().startswith("y")),
            "pct_markers": round(100 * sum(1 for x in v if str(x.get("markers", "")).lower().startswith("y")) / n, 1),
            "pct_markers_among_named": round(100 * sum(1 for x in v if str(x.get("markers", "")).lower().startswith("y")
                                                       and any(t != "none" for t in (x.get("test") or []))) / max(named, 1), 1),
            "bold_rule": dict(bold), "pct_bold_rule": {k: round(100 * c / n, 1) for k, c in bold.items()},
            "benchmark": bench.most_common(8),
            "alpha_005": sum(1 for x in v if x.get("alpha") == 0.05),
        }
    out["note"] = note_block
    return out


def test_reader_agreement(second_path: str = "out/swevo/test_reader_second.json") -> dict:
    """Field-by-field agreement between the first full-text reader and a
    second vendor's model on the papers both read."""
    import glob
    if not os.path.exists(second_path):
        return {}
    first = {}
    for path in sorted(glob.glob(f"{OUT}/test_reader_part*.json")):
        first.update(json.load(open(path, encoding="utf-8")))
    second = json.load(open(second_path, encoding="utf-8"))
    both = [p for p in second if p in first and "parse_error" not in first[p] and "parse_error" not in second[p]]
    def bold(v):
        b = str(v.get("bold_rule") or "not stated").lower()
        return "statistically_best" if ("statistic" in b or "signific" in b) else "best" if any(w in b for w in ("best", "optimal", "lowest", "highest")) else "not_stated"
    def named(v):
        return any(t != "none" for t in (v.get("test") or []))
    def layout(v):
        x = str(v.get("std_layout") or "unsure")
        return "off_cell" if x.startswith("separate") else x
    fields = {
        "runs": [(first[p].get("runs"), second[p].get("runs")) for p in both],
        "runs_stated": [(first[p].get("runs") is not None, second[p].get("runs") is not None) for p in both],
        "test_named": [(named(first[p]), named(second[p])) for p in both],
        "markers": [(str(first[p].get("markers", "")).lower().startswith("y"), str(second[p].get("markers", "")).lower().startswith("y")) for p in both],
        "bold_rule": [(bold(first[p]), bold(second[p])) for p in both],
        "std_layout": [(layout(first[p]), layout(second[p])) for p in both],
        "paired": [(str(first[p].get("paired") or "unsure"), str(second[p].get("paired") or "unsure")) for p in both],
    }
    out = {"papers": len(both)}
    for k, pairs in fields.items():
        hit = sum(1 for a, b in pairs if a == b)
        out[k] = {"n": len(pairs), "agree": hit, "pct": round(100 * hit / max(len(pairs), 1), 1),
                  "ci": [round(100 * x, 1) for x in wilson_interval(hit, len(pairs))] if pairs else None}
    # the second reader's rates on the same papers, beside the first's
    for name, rd in (("first", first), ("second", second)):
        v = [rd[p] for p in both]
        out[f"{name}_pct_runs_stated"] = round(100 * sum(1 for x in v if x.get("runs") is not None) / max(len(v), 1), 1)
        out[f"{name}_pct_test_named"] = round(100 * sum(1 for x in v if named(x)) / max(len(v), 1), 1)
        out[f"{name}_pct_markers"] = round(100 * sum(1 for x in v if str(x.get("markers", "")).lower().startswith("y")) / max(len(v), 1), 1)
        out[f"{name}_pct_bold_not_stated"] = round(100 * sum(1 for x in v if bold(x) == "not_stated") / max(len(v), 1), 1)
    return out


def arxiv_check(path: str = "data/extracted_arxiv_csne.jsonl") -> dict:
    """The parser on a second, LaTeX-set corpus: every arXiv cs.NE preprint of
    2025 the API listed, and the subset whose title matches the phrase list
    of the OpenAlex query. Added after the main corpus was read (a post-hoc
    check that the format hazard is the field's table layout and not one
    publisher's typesetting), and said so in the paper."""
    import re
    if not os.path.exists(path):
        return {}
    sys.path.insert(0, os.path.join(HERE))
    from harvest_oa import PHRASES
    rx = re.compile("|".join(re.escape(p) for p in PHRASES), re.I)
    recs = load_unique(path)
    stats_path = "out/pipeline_stats_extracted_arxiv_csne.json"
    listed = json.load(open(stats_path, encoding="utf-8")).get("listed", {}).get("arxiv-csne-2025") if os.path.exists(stats_path) else None
    out = {"listed": listed, "parsed": len(recs)}
    for name, rs in (("all", recs), ("metaheuristics_titles", [r for r in recs if rx.search(r["title"])])):
        a = analyse(rs)
        cs_ = a["_comparisons"]
        s = make_all._summary(a, cs_)
        b = make_all._bootstrap(cs_)
        out[name] = {"papers": s["papers"], "comparisons": s["comparisons"], "claim_papers": len({c["paper"] for c in cs_}),
                     "pct_neither": s["pct_neither"], "ci_neither": [b["pct_neither"]["lo"], b["pct_neither"]["hi"]],
                     "pct_testable": s["pct_testable"], "n_testable": s["n_testable"], "papers_testable": s["papers_testable"],
                     "pct_fail": s["pct_fail"], "ci_fail": [b["pct_fail"]["lo"], b["pct_fail"]["hi"]] if s["n_testable"] else None,
                     "pct_papers_err": s["pct_err"], "pct_papers_runs": s["pct_n"]}
    return out


BACK_MATTER = re.compile(r"References|Received:.*Accepted|Data availab|Author contributions|Acknowledg|Competing interests", re.I)


def _year_like(x) -> bool:
    return x is not None and float(x).is_integer() and 1990 <= x <= 2026


def back_matter(c: dict) -> bool:
    """A comparison read from a page's back matter: a reference-list line
    "13 (1)" against "564 (2022)" parsed as mean (deviation), or a table whose
    caption or header sits after the References or Data availability heading.
    The reference set exposed this class; the frozen unit keeps it and the
    readings below remove it."""
    text = (c.get("header_text") or "") + " " + (c.get("caption") or "")
    return bool(BACK_MATTER.search(text)) or _year_like(c.get("winner_dispersion")) or _year_like(c.get("runner_dispersion"))


def _retest(c: dict, n) -> dict | None:
    from analyze import test_comparison
    d = dict(c, n_runs=int(n) if n else None)
    return test_comparison(d)


def _scan_rates(cs: list, scan: dict) -> dict:
    """The testable comparisons re-tested at the text scan's modal run count
    where the paper states one, the parser's count otherwise; fail share and
    papers, so that every subgroup rate can be printed both ways."""
    out = []
    for c in cs:
        if not c.get("test"):
            continue
        n = scan.get(c["paper"], {}).get("run_modal") or c.get("n_runs")
        t = _retest(c, n)
        if t is None:
            continue
        out.append((c["paper"], t["p"] >= 0.05))
    n = len(out)
    return {"n": n, "papers": len({p for p, _ in out}), "fails": sum(f for _, f in out),
            "pct_fail": round(100 * sum(f for _, f in out) / n, 1) if n else None,
            "ci_fail": _boot_share(out) if len({p for p, _ in out}) >= 10 else None}


def parser_readings(cs: list, scan: dict) -> dict:
    """Readings on the parser's testable set that the reference set and the
    first review exposed: back-matter rows, the smallest-count rule, zero
    deviations, interval cells tested without a count, and all of them at once."""
    t = [c for c in cs if c.get("test")]
    bm = [c for c in t if back_matter(c)]
    zero = [c for c in t if c.get("winner_dispersion") == 0 or c.get("runner_dispersion") == 0]
    interval = [c for c in t if not c.get("n_runs")]
    keep_bm = [c for c in t if not back_matter(c)]
    clean = [c for c in keep_bm if c not in zero and c.get("n_runs")]
    def rates(sub):
        r = _rates(sub)
        r["scan"] = _scan_rates(sub, scan)
        return r
    small = [c for c in t if c.get("n_runs") and c["n_runs"] <= 5]
    return {"as_reported": rates(t), "back_matter_only": rates(bm), "without_back_matter": rates(keep_bm),
            "zero_sd_only": rates(zero), "without_zero_sd": rates([c for c in t if c not in zero]),
            "interval_only": rates(interval), "without_interval": rates([c for c in t if c.get("n_runs")]),
            "cleaned": rates(clean),
            "back_matter_all_comparisons": sum(1 for c in cs if back_matter(c)),
            "back_matter_papers": len({c["paper"] for c in bm}),
            "tested_at_five_or_fewer": len(small), "tested_at_five_or_fewer_papers": len({c["paper"] for c in small}),
            "median_n": __import__("statistics").median([c["n_runs"] for c in t if c.get("n_runs")]) if any(c.get("n_runs") for c in t) else None}


def scan_by_kind_holders(scan: dict, kinds: dict, cs: list) -> dict:
    """The text-scan rates by kind restricted to the papers in which the
    parser found a highlighted comparison: papers that compare something."""
    holders = {c["paper"] for c in cs}
    out = {}
    for lab in ("new_optimizer", "application", "all"):
        ids = [p for p, v in scan.items() if "error" not in v and p in holders and (lab == "all" or kinds.get(p) == lab)]
        n = len(ids)
        out[lab] = {"papers": n,
                    "pct_runs_stated": round(100 * sum(1 for p in ids if scan[p].get("run_modal")) / max(n, 1), 1),
                    "pct_test_named": round(100 * sum(1 for p in ids if scan[p].get("any_test")) / max(n, 1), 1),
                    "pct_thirty_modal": round(100 * sum(1 for p in ids if scan[p].get("run_modal") == 30) / max(n, 1), 1)}
    return out


def bold_note(scan: dict, kinds: dict) -> dict:
    """The journal's production note "Significant values are in bold" as the
    text scan finds it, by kind."""
    out = {}
    for lab in ("new_optimizer", "application", "all"):
        ids = [p for p, v in scan.items() if "error" not in v and (lab == "all" or kinds.get(p) == lab)]
        n = len(ids)
        k = sum(1 for p in ids if scan[p].get("bold_note"))
        out[lab] = {"papers": n, "with_note": k, "pct": round(100 * k / max(n, 1), 1)}
    return out


def _method_citers(scan: dict) -> set:
    keys = ["derrac2011", "garcia2009", "garcia2010", "sorensen2015", "aranha2022", "camacho2022", "bartz2020",
            "beiranvand2017", "kendall2016", "hansen_coco", "carrasco2020", "latorre2021", "osaba2021"]
    return {p for p, v in scan.items() if any(v.get("cites", {}).get(k) for k in keys)}


def cites(cs: list, scan: dict) -> dict:
    """Papers citing the methodology literature, and how they report."""
    keys = ["derrac2011", "garcia2009", "garcia2010", "sorensen2015", "aranha2022", "camacho2022", "bartz2020",
            "beiranvand2017", "kendall2016", "hansen_coco", "carrasco2020", "latorre2021", "osaba2021", "wolpert_nfl"]
    counts = {k: sum(1 for v in scan.values() if v.get("cites", {}).get(k)) for k in keys}
    method = _method_citers(scan)
    claim_papers = {c["paper"] for c in cs}
    a = [c for c in cs if c["paper"] in method]
    b = [c for c in cs if c["paper"] not in method]
    return {"counts": counts, "citing_papers": len(method & claim_papers), "claim_papers": len(claim_papers),
            "citing": _rates(a), "not_citing": _rates(b),
            "citing_name_a_test": sum(1 for p in method if scan[p].get("any_test")),
            "citing_state_runs": sum(1 for p in method if scan[p].get("run_modal"))}


def scan_by_kind(scan: dict, kinds: dict, metaphor: dict, suite: dict) -> dict:
    """The text-scan readings (run count stated, test named, CEC suite used)
    and the classifier's metaphor flag, by paper kind, over the scanned papers."""
    out = {}
    for lab in sorted(set(kinds.values())) + ["all"]:
        ids = [p for p, v in scan.items() if "error" not in v and (lab == "all" or kinds.get(p) == lab)]
        n = len(ids)
        out[lab] = {"papers": n,
                    "runs_stated": sum(1 for p in ids if scan[p].get("run_modal")),
                    "pct_runs_stated": round(100 * sum(1 for p in ids if scan[p].get("run_modal")) / max(n, 1), 1),
                    "test_named": sum(1 for p in ids if scan[p].get("any_test")),
                    "pct_test_named": round(100 * sum(1 for p in ids if scan[p].get("any_test")) / max(n, 1), 1),
                    "wilcoxon": sum(1 for p in ids if scan[p].get("tests", {}).get("wilcoxon")),
                    "friedman": sum(1 for p in ids if scan[p].get("tests", {}).get("friedman")),
                    "t_test": sum(1 for p in ids if scan[p].get("tests", {}).get("t_test")),
                    "thirty_modal": sum(1 for p in ids if scan[p].get("run_modal") == 30),
                    "pct_thirty_modal": round(100 * sum(1 for p in ids if scan[p].get("run_modal") == 30) / max(n, 1), 1),
                    "cec": sum(1 for p in ids if scan[p].get("suites", {}).get("cec")),
                    "pct_cec": round(100 * sum(1 for p in ids if scan[p].get("suites", {}).get("cec")) / max(n, 1), 1),
                    "metaphor_yes": sum(1 for p in ids if metaphor.get(p) == "yes"),
                    "pct_metaphor_yes": round(100 * sum(1 for p in ids if metaphor.get(p) == "yes") / max(n, 1), 1),
                    "bestiary_hit": sum(1 for p in ids if scan[p].get("metaphors_in_title_or_abstract")),
                    "pct_bestiary_hit": round(100 * sum(1 for p in ids if scan[p].get("metaphors_in_title_or_abstract")) / max(n, 1), 1),
                    "cites_methodology": sum(1 for p in ids if any(v for k, v in scan[p].get("cites", {}).items() if k != "wolpert_nfl")),
                    "pct_cites_methodology": round(100 * sum(1 for p in ids if any(v for k, v in scan[p].get("cites", {}).items() if k != "wolpert_nfl")) / max(n, 1), 1)}
    return out


def kind_agreement(kinds: dict, metaphor: dict, second_path: str = "out/swevo/kinds_second_sonnet.csv") -> dict:
    """Agreement between the primary labeller and a second vendor's model on
    the papers both labelled: raw agreement, Cohen's kappa, the confusion."""
    if not os.path.exists(second_path):
        return {}
    second, second_m = {}, {}
    with open(second_path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["label"] != "parse_error":
                second[r["id"]] = r["label"]
                second_m[r["id"]] = r["metaphor_named"] or "unsure"
    both = [p for p in second if p in kinds]
    if not both:
        return {"papers": 0}
    agree = sum(1 for p in both if kinds[p] == second[p])
    labs = sorted(set(kinds[p] for p in both) | set(second[p] for p in both))
    pa = {a: sum(1 for p in both if kinds[p] == a) / len(both) for a in labs}
    pb = {a: sum(1 for p in both if second[p] == a) / len(both) for a in labs}
    pe = sum(pa[a] * pb[a] for a in labs)
    po = agree / len(both)
    kappa = (po - pe) / (1 - pe) if pe < 1 else 1.0
    conf = collections.Counter((kinds[p], second[p]) for p in both if kinds[p] != second[p])
    scan = json.load(open(f"{OUT}/text_scan.json", encoding="utf-8")) if os.path.exists(f"{OUT}/text_scan.json") else {}
    def srates(ids):
        n = len(ids)
        return {"papers": n,
                "pct_runs_stated": round(100 * sum(1 for p in ids if scan.get(p, {}).get("run_modal")) / max(n, 1), 1),
                "pct_test_named": round(100 * sum(1 for p in ids if scan.get(p, {}).get("any_test")) / max(n, 1), 1)}
    strata = {"first_new_optimizer": srates([p for p in both if kinds[p] == "new_optimizer"]),
              "second_new_optimizer": srates([p for p in both if second[p] == "new_optimizer"]),
              "both_new_optimizer": srates([p for p in both if kinds[p] == "new_optimizer" and second[p] == "new_optimizer"]),
              "either_new_optimizer": srates([p for p in both if kinds[p] == "new_optimizer" or second[p] == "new_optimizer"]),
              "first_application": srates([p for p in both if kinds[p] == "application"]),
              "second_application": srates([p for p in both if second[p] == "application"]),
              "both_application": srates([p for p in both if kinds[p] == "application" and second[p] == "application"])}
    tp = sum(1 for p in both if kinds[p] == "new_optimizer" and second[p] == "new_optimizer")
    direction = {"first_new_optimizer": sum(1 for p in both if kinds[p] == "new_optimizer"),
                 "second_new_optimizer": sum(1 for p in both if second[p] == "new_optimizer"),
                 "application_to_new_optimizer": sum(1 for p in both if kinds[p] == "application" and second[p] == "new_optimizer"),
                 "new_optimizer_to_application": sum(1 for p in both if kinds[p] == "new_optimizer" and second[p] == "application"),
                 "precision_vs_second": round(100 * tp / max(sum(1 for p in both if kinds[p] == "new_optimizer"), 1), 1),
                 "recall_vs_second": round(100 * tp / max(sum(1 for p in both if second[p] == "new_optimizer"), 1), 1)}
    m_both = [p for p in both if p in metaphor]
    m_agree = sum(1 for p in m_both if metaphor[p] == second_m[p])
    return {"papers": len(both), "agree": agree, "pct_agree": round(100 * agree / len(both), 1),
            "kappa": round(kappa, 3), "disagreements": [[a, b, n] for (a, b), n in conf.most_common()],
            "metaphor_papers": len(m_both), "metaphor_agree": m_agree,
            "pct_metaphor_agree": round(100 * m_agree / max(len(m_both), 1), 1),
            "ci_agree": [round(100 * x, 1) for x in wilson_interval(agree, len(both))],
            "strata": strata, "direction": direction,
            "metaphor_none_disagreements": sum(1 for p in m_both if metaphor[p] != second_m[p] and "none" in (metaphor[p], second_m[p]))}


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    records = load_unique(EXTRACTED)
    analysis = analyse(records)
    with open(f"{OUT}/analysis.json", "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, indent=1)
    cs = analysis["_comparisons"]
    summary, boot = make_all._summary(analysis, cs), make_all._bootstrap(cs)
    # every parser interval in the paper comes from one cluster bootstrap (_boot_share, seed 0)
    boot["pct_neither"]["lo"], boot["pct_neither"]["hi"] = _boot_share([(c["paper"], c["winner_dispersion"] is None and c["runner_dispersion"] is None) for c in cs])
    boot["pct_testable"]["lo"], boot["pct_testable"]["hi"] = _boot_share([(c["paper"], bool(c.get("test"))) for c in cs])
    _t = [c for c in cs if c.get("test")]
    boot["pct_fail"]["lo"], boot["pct_fail"]["hi"] = _boot_share([(c["paper"], c["test"]["p"] >= 0.05) for c in _t])
    boot["pct_fail_holm"]["lo"], boot["pct_fail_holm"]["hi"] = _boot_share([(c["paper"], not c.get("survives_holm")) for c in _t])
    print(f"OA metaheuristics: {summary['papers']} papers, {summary['comparisons']} comparisons, "
          f"{summary['pct_neither']}% neither, {summary['pct_testable']}% testable, {summary['pct_fail']}% fail")
    scan = json.load(open(f"{OUT}/text_scan.json", encoding="utf-8")) if os.path.exists(f"{OUT}/text_scan.json") else {}
    kinds, metaphor, suite = {}, {}, {}
    import glob
    for path in sorted(glob.glob(f"{OUT}/kinds_shard*.csv")) + [f"{OUT}/kinds.csv"]:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r["label"] == "parse_error" or r["id"] in kinds:
                    continue
                kinds[r["id"]] = r["label"]
                metaphor[r["id"]] = r["metaphor_named"] or "unsure"
                suite[r["id"]] = r["benchmark_suite"] or "unsure"
    if kinds:
        with open(f"{OUT}/kinds_merged.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["id", "label", "metaphor_named", "benchmark_suite"])
            for k in sorted(kinds):
                w.writerow([k, kinds[k], metaphor[k], suite[k]])
    by_year = {}
    for year in sorted({r["year"] for r in records}):
        recs = [r for r in records if r["year"] == year]
        a = analyse(recs)
        by_year[str(year)] = {"summary": make_all._summary(a, a["_comparisons"]), "bootstrap": make_all._bootstrap(a["_comparisons"])}
    index = {r["id"]: r for r in json.load(open(f"{OUT}/index.json", encoding="utf-8"))}
    fetched = len([f for f in os.listdir("data/corpus_oa")]) if os.path.isdir("data/corpus_oa") else None
    by_journal_listed = collections.Counter(r["journal"] for r in index.values())
    extras = {
        "summary": summary, "bootstrap": boot, "by_year": by_year,
        "corpus": {"listed": len(index), "listed_in_corpus_journal": sum(1 for r in index.values() if r["journal"] == "Scientific Reports"),
                   "journals_listed": len(by_journal_listed), "by_journal_listed": dict(by_journal_listed),
                   "fetched": fetched, "parsed": len(records),
                   "listed_by_year": dict(collections.Counter(r["year"] for r in index.values() if r["journal"] == "Scientific Reports")),
                   "by_journal": dict(collections.Counter(index[r["id"]]["journal"] for r in records if r["id"] in index))},
        "kinds": by_group(cs, kinds, "by_kind") if kinds else {},
        "metaphor": by_group(cs, metaphor, "by_metaphor") if metaphor else {},
        "suite": by_group(cs, suite, "by_suite") if suite else {},
        "kind_counts": dict(collections.Counter(kinds.values())),
        "kind_agreement": kind_agreement(kinds, metaphor),
        "metaphor_counts": dict(collections.Counter(metaphor.values())),
        "stat_tests": stat_tests(cs, scan) if scan else {},
        "scan_by_kind": scan_by_kind(scan, kinds, metaphor, suite) if scan and kinds else {},
        "run_counts": run_counts(cs, scan) if scan else {},
        "cites": cites(cs, scan) if scan else {},
        "parser_readings": parser_readings(cs, scan),
        "scan_by_kind_holders": scan_by_kind_holders(scan, kinds, cs) if scan and kinds else {},
        "bold_note": bold_note(scan, kinds) if scan and kinds else {},
        "kind_scan_fail": {lab: _scan_rates([c for c in cs if kinds.get(c["paper"]) == lab], scan) for lab in ("new_optimizer", "application")} if scan and kinds else {},
        "cites_scan_fail": ({"citing": _scan_rates([c for c in cs if c["paper"] in _method_citers(scan)], scan),
                             "not_citing": _scan_rates([c for c in cs if c["paper"] not in _method_citers(scan)], scan)} if scan else {}),
        "tests_scan_fail": ({"named": _scan_rates([c for c in cs if scan.get(c["paper"], {}).get("any_test")], scan),
                             "unnamed": _scan_rates([c for c in cs if not scan.get(c["paper"], {}).get("any_test")], scan)} if scan else {}),
        "scan_run_count": scan_run_count_reading(cs, scan) if scan else {},
        "test_reader": test_reader_blocks(cs, kinds),
        "arxiv": arxiv_check(),
        "test_reader_agreement": test_reader_agreement(),
        "fetch_attempts": ({j: {"listed": v["listed"], "attempts": len(v["attempts"]), "pdf_ok": v["pdf_ok"], "statuses": "/".join(v["statuses"]),
                                "html_only": sum(1 for r in v["attempts"] if r.get("status") == 200 and not r.get("is_pdf"))}
                            for j, v in json.load(open(f"{OUT}/fetch_attempts.json", encoding="utf-8"))["journals"].items()}
                           if os.path.exists(f"{OUT}/fetch_attempts.json") else {}),
        "headline_span": extra_stats.headline_span(cs, records),
        "span_rows": (lambda hs: {"lo": min(hs["rows"][k]["pct_fail"] for k in ("as_reported", "z_two_sided", "one_sided", "rho_0.5", "rho_0.9") if k in hs["rows"]),
                                  "hi": max(hs["rows"][k]["pct_fail"] for k in ("as_reported", "z_two_sided", "one_sided", "rho_0.5", "rho_0.9") if k in hs["rows"]),
                                  "rows": [k for k in ("as_reported", "z_two_sided", "one_sided", "rho_0.5", "rho_0.9") if k in hs["rows"]]})(extra_stats.headline_span(cs, records)),
        "subset_direction": extra_stats.subset_direction(records, cs),
        "holm_families": extra_stats.holm_families(cs),
        "run_count_scope": run_count_scope(cs, records),
        "error_bar_meaning": error_bar_meaning(cs),
        "paper_level_crosstab": paper_level_crosstab(records),
        "correlation_sensitivity": correlation_sensitivity(cs),
        "checkability_span": checkability_span(cs),
        "readings": readings(records, cs),
        "row_bold": row_bold_readings(cs, records),
        "per_paper_failure": per_paper_failure(cs),
        "per_paper_failure_dedup": per_paper_failure(exact_copies(cs)[1]),
        "ddof_reading": ddof_reading(cs),
        "caption_assertion": caption_assertion(cs),
        "uncertainty_anywhere": uncertainty_anywhere(records),
        "big_n_and_largest": big_n_and_largest(cs, {}, communities_path=f"{OUT}/kinds_merged.csv"),
        "funnel": __import__("analyze").extraction_funnel(records),
        "bold_semantics": make_all.bold_semantics(records),
    }
    with open(f"{OUT}/extra.json", "w", encoding="utf-8") as fh:
        json.dump(extras, fh, indent=1)
    print("wrote", f"{OUT}/extra.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
