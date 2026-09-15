"""Test-retest of the image-based reader: the 66 pages of
audits/aamas_testable_pages were read once for that kit and again, under the
same protocol, as part of the full census (audits/aamas_census). Match the
two lists of single-bold groups one-to-one on the winner's printed value and
report how often the two reads agree on what they list and on the verdicts.

Usage: python aamas/reader_retest.py [--first KIT] [--second KIT] [--out FILE]
The same script compares any two readings of overlapping pages, e.g. the
census against the 40 pages re-read at low reasoning effort.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "study"))
from pages_score import _bar_num, _se, _eq  # noqa: E402
from gold_set import _num  # noqa: E402
from analyze import p_value  # noqa: E402

FIRST = "audits/aamas_testable_pages"
SECOND = "audits/aamas_census"
OUT = "out/aamas/reader_retest.json"


def groups_of(page):
    out = []
    for t in page.get("tables", []):
        if not t.get("results_table", "").lower().startswith("y"):
            continue
        kind = t.get("bar_kind", "").lower()
        n = _num(t.get("n_runs"))
        for g in t.get("groups", []):
            wb = _bar_num(g.get("winner_disp")) is not None or str(g.get("winner_disp", "")).startswith("[")
            rb = _bar_num(g.get("runner_disp")) is not None or str(g.get("runner_disp", "")).startswith("[")
            testable = wb and rb and (n is not None or kind in ("se", "ci"))
            fail = None
            if testable:
                w, r = _num(g.get("winner_mean")), _num(g.get("runner_mean"))
                sw, sr = _se(g.get("winner_disp"), kind, n), _se(g.get("runner_disp"), kind, n)
                if None not in (w, r, sw, sr):
                    res = p_value(abs(w - r), sw, sr, int(n) if n else None)
                    fail = (res["p"] >= 0.05) if res else None
            out.append({"w": _num(g.get("winner_mean")), "neither": not wb and not rb,
                        "testable": testable, "fail": fail})
    return out


def _boot(per_page, num, den, reps=2000, seed=0):
    rng = random.Random(seed)
    papers = sorted({p["paper"] for p in per_page})
    by = {pp: [p for p in per_page if p["paper"] == pp] for pp in papers}
    vals = []
    for _ in range(reps):
        draw = [p for pp in rng.choices(papers, k=len(papers)) for p in by[pp]]
        d = sum(p[den] for p in draw)
        if d:
            vals.append(100.0 * sum(p[num] for p in draw) / d)
    vals.sort()
    return [round(vals[int(0.025 * len(vals))], 1), round(vals[int(0.975 * len(vals)) - 1], 1)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--first", default=FIRST)
    ap.add_argument("--second", default=SECOND)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    items1 = json.load(open(os.path.join(args.first, "items.json"), encoding="utf-8"))
    items2 = json.load(open(os.path.join(args.second, "items.json"), encoding="utf-8"))
    lab1 = {p["id"]: p for p in json.load(open(os.path.join(args.first, "labels.json"), encoding="utf-8"))}
    lab2 = {p["id"]: p for p in json.load(open(os.path.join(args.second, "labels.json"), encoding="utf-8"))}
    key2 = {(it["paper"], it["page"]): it["id"] for it in items2}
    per_page = []
    for it in items1:
        i2 = key2.get((it["paper"], it["page"]))
        if it["id"] not in lab1 or i2 not in lab2:
            continue
        g1, g2 = groups_of(lab1[it["id"]]), groups_of(lab2[i2])
        used, pairs = set(), []
        for a in g1:
            for j, b in enumerate(g2):
                if j not in used and a["w"] is not None and _eq(a["w"], b["w"]):
                    used.add(j); pairs.append((a, b))
                    break
        both_tested = [(a, b) for a, b in pairs if a["fail"] is not None and b["fail"] is not None]
        per_page.append({
            "paper": it["paper"], "page": it["page"],
            "g1": len(g1), "g2": len(g2), "matched": len(pairs),
            "neither_agree": sum(1 for a, b in pairs if a["neither"] == b["neither"]),
            "testable_agree": sum(1 for a, b in pairs if a["testable"] == b["testable"]),
            "n1_neither": sum(1 for a in g1 if a["neither"]),
            "n2_neither": sum(1 for b in g2 if b["neither"]),
            "n1_testable": sum(1 for a in g1 if a["testable"]),
            "n2_testable": sum(1 for b in g2 if b["testable"]),
            "n1_tested": sum(1 for a in g1 if a["fail"] is not None),
            "n2_tested": sum(1 for b in g2 if b["fail"] is not None),
            "n1_fail": sum(1 for a in g1 if a["fail"]),
            "n2_fail": sum(1 for b in g2 if b["fail"]),
            "both_tested": len(both_tested),
            "fail_agree": sum(1 for a, b in both_tested if a["fail"] == b["fail"]),
        })
    T = lambda k: sum(p[k] for p in per_page)  # noqa: E731
    res = {
        "n_pages": len(per_page), "n_papers": len({p["paper"] for p in per_page}),
        "groups_first": T("g1"), "groups_second": T("g2"), "matched": T("matched"),
        "pct_matched_of_first": round(100.0 * T("matched") / T("g1"), 1) if T("g1") else None,
        "pct_matched_of_second": round(100.0 * T("matched") / T("g2"), 1) if T("g2") else None,
        "ci_matched_of_first": _boot(per_page, "matched", "g1"),
        "neither_agree": T("neither_agree"),
        "pct_neither_agree": round(100.0 * T("neither_agree") / T("matched"), 1) if T("matched") else None,
        "testable_agree": T("testable_agree"),
        "pct_testable_agree": round(100.0 * T("testable_agree") / T("matched"), 1) if T("matched") else None,
        "pct_neither_first": round(100.0 * T("n1_neither") / T("g1"), 1) if T("g1") else None,
        "pct_neither_second": round(100.0 * T("n2_neither") / T("g2"), 1) if T("g2") else None,
        "pct_testable_first": round(100.0 * T("n1_testable") / T("g1"), 1) if T("g1") else None,
        "pct_testable_second": round(100.0 * T("n2_testable") / T("g2"), 1) if T("g2") else None,
        "tested_first": T("n1_tested"), "tested_second": T("n2_tested"),
        "pct_fail_first": round(100.0 * T("n1_fail") / T("n1_tested"), 1) if T("n1_tested") else None,
        "pct_fail_second": round(100.0 * T("n2_fail") / T("n2_tested"), 1) if T("n2_tested") else None,
        "both_tested": T("both_tested"), "fail_agree": T("fail_agree"),
        "pct_fail_agree": round(100.0 * T("fail_agree") / T("both_tested"), 1) if T("both_tested") else None,
        "per_page": per_page,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(res, open(args.out, "w", encoding="utf-8"), indent=1)
    print({k: v for k, v in res.items() if k != "per_page"})


if __name__ == "__main__":
    main()
