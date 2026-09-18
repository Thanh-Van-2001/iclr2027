"""Welch's verdict on the printed summaries against the verdict the paper
itself prints for the same pair: join the census's tested groups to the
printed-verdict reading (audits/swevo_verdict) by page, group label and the
bold cell's value, take the verdict printed beside the group on the same
page or, failing that, the entry of a verdict table anywhere in the paper
for the same function and the rival optimizer, and cross-tabulate.
Writes out/swevo/verdict_crosstab.json.
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
sys.path.insert(0, HERE)
from gold_set import _num  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402
from census_readings import _regroup  # noqa: E402

KIT = "audits/swevo_census"
VK = "audits/swevo_verdict"
OUT = "out/swevo/verdict_crosstab.json"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def classify(v: str):
    """The printed verdict as significant / not / unreadable, from the
    paper's own symbol or p-value."""
    s = str(v or "").strip().lower()
    if not s or s in ("none", "n/a", "na", "-", "--") and s != "-":
        return None
    if s in ("+", "−", "-", "w", "l", "win", "loss", "better", "worse", "significant", "*", "**", "†", "‡", "s", "yes", "y", "1"):
        return "significant"
    if s in ("=", "~", "≈", "t", "tie", "ns", "n/s", "n.s.", "not significant", "no", "n", "0", "similar", "equal"):
        return "not_significant"
    m = re.search(r"(\d+\.?\d*(?:e-?\d+)?)", s)
    if m and ("p" in s or "<" in s or ">" in s or re.fullmatch(r"[\d.e-]+", s)):
        try:
            p = float(m.group(1))
        except ValueError:
            return None
        if "<" in s and p <= 0.05:
            return "significant"
        if ">" in s and p >= 0.05:
            return "not_significant"
        return "significant" if p < 0.05 else "not_significant"
    if s.startswith("+") or s.startswith("−") or s.startswith("-"):
        return "significant"
    if s.startswith("="):
        return "not_significant"
    return None


def main() -> int:
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    kinds = {}
    vpages = {}
    for path in sorted(glob.glob(os.path.join(VK, "labels_shard*.json"))):
        for p in json.load(open(path, encoding="utf-8")):
            if p.get("note") != "failed":
                vpages[p["id"]] = p
    papers = {l.strip() for l in open(os.path.join(VK, "papers.txt"), encoding="utf-8") if l.strip()}
    gs = [g for g in _regroup({i: labels[i] for i in labels if items[i]["paper"] in papers}, items, kinds)
          if g["testable"] and g["fail"] is not None]
    # verdict-table entries per paper: (label, competitor) -> verdict
    entries = collections.defaultdict(dict)
    for iid, vp in vpages.items():
        for t in vp.get("verdict_tables", []):
            for e in t.get("entries", []):
                entries[vp["paper"]][(_norm(e.get("label")), _norm(e.get("competitor")))] = e.get("verdict")
    rows = []
    for g in gs:
        vp = vpages.get(g["page"])
        if vp is None:
            rows.append(dict(g, status="page_not_read"))
            continue
        match = None
        for t in vp.get("results_tables", []):
            for vg in t.get("groups", []):
                if _num(vg.get("winner_mean")) is not None and g["w"] is not None and abs(_num(vg.get("winner_mean")) - g["w"]) <= 1e-9 * max(1, abs(g["w"])) \
                        and (_norm(vg.get("label")) == _norm(g["label"]) or not g["label"]):
                    match = vg
                    break
            if match:
                break
        if match is None:
            for t in vp.get("results_tables", []):
                for vg in t.get("groups", []):
                    if _num(vg.get("winner_mean")) is not None and g["w"] is not None and abs(_num(vg.get("winner_mean")) - g["w"]) <= 1e-9 * max(1, abs(g["w"])):
                        match = vg
                        break
                if match:
                    break
        if match is None:
            rows.append(dict(g, status="group_not_matched"))
            continue
        verdict = match.get("verdict_here")
        source = "same_page"
        if classify(verdict) is None:
            key = (_norm(match.get("label") or g["label"]), _norm(match.get("runner_name")))
            verdict = entries[g["paper"]].get(key)
            source = "verdict_table" if verdict is not None else "none"
            if verdict is None:
                # the verdict table may list the winner's name when the rival is the proposed method
                key2 = (_norm(match.get("label") or g["label"]), _norm(match.get("winner_name")))
                verdict = entries[g["paper"]].get(key2)
                source = "verdict_table_winner_named" if verdict is not None else "none"
        cls = classify(verdict)
        rows.append(dict(g, status="located" if cls else "verdict_not_printed", winner_name=match.get("winner_name"),
                         runner_name=match.get("runner_name"), verdict=verdict, verdict_class=cls, source=source))
    located = [r for r in rows if r["status"] == "located"]
    def cell(a, b):
        return sum(1 for r in located if bool(r["fail"]) == a and (r["verdict_class"] == "not_significant") == b)
    xt = {"welch_fail_printed_not_significant": cell(True, True), "welch_fail_printed_significant": cell(True, False),
          "welch_pass_printed_not_significant": cell(False, True), "welch_pass_printed_significant": cell(False, False)}
    agree = xt["welch_fail_printed_not_significant"] + xt["welch_pass_printed_significant"]
    n = len(located)
    by_paper = collections.defaultdict(lambda: [0, 0])
    for r in located:
        by_paper[r["paper"]][0] += 1
        by_paper[r["paper"]][1] += (bool(r["fail"]) == (r["verdict_class"] == "not_significant"))
    out = {"papers": len(papers), "pages_read": len(vpages), "tested_groups": len(rows),
           "status": dict(collections.Counter(r["status"] for r in rows)),
           "source": dict(collections.Counter(r.get("source", "") for r in located)),
           "located": n, "pct_located": round(100 * n / max(len(rows), 1), 1),
           "crosstab": xt, "agree": agree, "pct_agree": round(100 * agree / n, 1) if n else None,
           "ci_agree": [round(100 * x, 1) for x in wilson_interval(agree, n)] if n else None,
           "welch_fail_among_located": round(100 * sum(1 for r in located if r["fail"]) / n, 1) if n else None,
           "printed_not_significant_among_located": round(100 * sum(1 for r in located if r["verdict_class"] == "not_significant") / n, 1) if n else None,
           "papers_located": len(by_paper),
           "per_paper": {k: {"located": v[0], "agree": v[1]} for k, v in by_paper.items()},
           "verdict_classes_raw": dict(collections.Counter(str(r.get("verdict")) for r in located).most_common(15))}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(rows, open(OUT.replace(".json", "_rows.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_paper", "verdict_classes_raw")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
