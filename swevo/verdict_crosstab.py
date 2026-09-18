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
    # verdict-table entries: per page and table first (a function label such as
    # "F1" repeats across suites and dimensions), then per paper where the key
    # is unique; a key with conflicting verdicts in the paper is unusable
    entries_page = collections.defaultdict(dict)
    entries_paper = collections.defaultdict(lambda: collections.defaultdict(set))
    against = collections.defaultdict(set)
    for iid, vp in vpages.items():
        for t in vp.get("verdict_tables", []):
            if t.get("compared_against"):
                against[vp["paper"]].add(_norm(t.get("compared_against")))
            for e in t.get("entries", []):
                key = (_norm(e.get("label")), _norm(e.get("competitor")))
                entries_page[iid].setdefault(key, e.get("verdict"))
                entries_paper[vp["paper"]][key].add(str(e.get("verdict")))
    conflicts = {paper: sum(1 for v in d.values() if len(v) > 1) for paper, d in entries_paper.items()}

    def lookup(paper, iid, key):
        if key in entries_page.get(iid, {}):
            return entries_page[iid][key], "same_page_table"
        vs = entries_paper.get(paper, {}).get(key)
        if vs and len(vs) == 1:
            return next(iter(vs)), "verdict_table"
        if vs and len(vs) > 1:
            return None, "ambiguous"
        return None, "none"
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
        # the paper's verdicts compare the proposed algorithm with each
        # competitor; the pair is the same only when the bold cell or its rival
        # is that algorithm, and the verdict is then the competitor's entry
        prop = against.get(g["paper"], set())
        wn, rn = _norm(match.get("winner_name")), _norm(match.get("runner_name"))
        same_pair = (not prop) or (wn in prop) or (rn in prop)
        competitor = rn if (wn in prop or not prop) else wn
        verdict = match.get("verdict_here")
        source = "beside_group"
        if classify(verdict) is None:
            key = (_norm(match.get("label") or g["label"]), competitor)
            verdict, source = lookup(g["paper"], g["page"], key)
        cls = classify(verdict)
        if not same_pair:
            status = "different_pair"
        elif source == "ambiguous":
            status = "ambiguous_key"
        elif cls:
            status = "located"
        else:
            status = "verdict_not_printed"
        rows.append(dict(g, status=status, winner_name=match.get("winner_name"),
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
    # a cluster bootstrap over papers for the agreement, and the Welch rate on the groups without a located verdict
    import random
    rng = random.Random(0)
    keys = list(by_paper)
    vals = []
    for _ in range(2000):
        draw = [by_paper[keys[rng.randrange(len(keys))]] for _ in keys]
        k_, n_ = sum(x[1] for x in draw), sum(x[0] for x in draw)
        vals.append(100 * k_ / n_ if n_ else 0)
    vals.sort()
    not_located = [r for r in rows if r["status"] != "located"]
    out = {"papers": len(papers), "pages_read": len(vpages), "tested_groups": len(rows),
           "ci_agree_papers": [round(vals[50], 1), round(vals[1949], 1)] if keys else None,
           "welch_fail_not_located": round(100 * sum(1 for r in not_located if r["fail"]) / len(not_located), 1) if not_located else None,
           "not_located": len(not_located),
           "conflicting_keys_papers": sum(1 for v in conflicts.values() if v),
           "status": dict(collections.Counter(r["status"] for r in rows)),
           "source": dict(collections.Counter(r.get("source", "") for r in located)),
           "located": n, "pct_located": round(100 * n / max(len(rows), 1), 1),
           "crosstab": xt, "agree": agree, "pct_agree": round(100 * agree / n, 1) if n else None,
           "ci_agree": [round(100 * x, 1) for x in wilson_interval(agree, n)] if n else None,
           "welch_fail_among_located": round(100 * sum(1 for r in located if r["fail"]) / n, 1) if n else None,
           "printed_not_significant_among_located": round(100 * sum(1 for r in located if r["verdict_class"] == "not_significant") / n, 1) if n else None,
           "papers_located": len(by_paper),
           "largest_paper_located": max((v[0] for v in by_paper.values()), default=0),
           "pct_largest_paper": round(100 * max((v[0] for v in by_paper.values()), default=0) / n, 1) if n else None,
           "agree_without_largest": (lambda big: {"n": n - by_paper[big][0], "agree": agree - by_paper[big][1],
                                                  "pct": round(100 * (agree - by_paper[big][1]) / max(n - by_paper[big][0], 1), 1)})(max(by_paper, key=lambda k: by_paper[k][0])) if by_paper else None,
           "per_paper": {k: {"located": v[0], "agree": v[1]} for k, v in by_paper.items()},
           "verdict_classes_raw": dict(collections.Counter(str(r.get("verdict")) for r in located).most_common(15))}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    json.dump(rows, open(OUT.replace(".json", "_rows.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_paper", "verdict_classes_raw")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
