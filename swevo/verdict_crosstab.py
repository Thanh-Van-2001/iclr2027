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
from census_readings import _regroup, corrected_labels, _is_mean  # noqa: E402

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
    # the corrected census (per-table merge of the row re-reads) is the set the paper quotes
    labels = corrected_labels()
    kinds = {}
    vpages = {}
    for path in sorted(glob.glob(os.path.join(VK, "labels_shard*.json"))):
        for p in json.load(open(path, encoding="utf-8")):
            if p.get("note") != "failed":
                vpages[p["id"]] = p
    papers = {l.strip() for l in open(os.path.join(VK, "papers.txt"), encoding="utf-8") if l.strip()}
    first_draw = len(papers)
    # the second draw, after review round five: every remaining tested census paper, whatever the reader field said
    second = os.path.join(VK, "papers2.txt")
    papers2 = {l.strip() for l in open(second, encoding="utf-8") if l.strip()} if os.path.exists(second) else set()
    read_ids = set(vpages)
    papers |= papers2
    # the groups that are means over runs, the base the abstract quotes (summary rows and rank tables out)
    gs = [g for g in _regroup({i: labels[i] for i in labels if items[i]["paper"] in papers}, items, kinds)
          if g["testable"] and g["fail"] is not None and _is_mean(g)]
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
    # the sign convention of each paper: among located pairs whose bold cell is
    # the proposed optimizer, the sign printed most often is the sign that
    # marks the proposed optimizer as better; a pair whose printed sign says
    # the bold cell is worse contradicts the bold and is flagged
    sign_of = {}
    for paper in {r["paper"] for r in located}:
        signs = collections.Counter(str(r["verdict"]).strip() for r in located if r["paper"] == paper
                                    and _norm(r.get("winner_name")) in against.get(paper, set()) and str(r["verdict"]).strip() in ("+", "-", "−"))
        if signs:
            sign_of[paper] = signs.most_common(1)[0][0]
    contradictions = 0
    for r in located:
        v = str(r["verdict"]).strip()
        if v in ("+", "-", "−") and r["paper"] in sign_of:
            better = sign_of[r["paper"]]
            bold_is_proposed = _norm(r.get("winner_name")) in against.get(r["paper"], set())
            # for a bold proposed optimizer the printed sign should be the "better" sign; for a bold competitor the other
            expected = better if bold_is_proposed else ("-" if better == "+" else "+")
            r["sign_contradicts_bold"] = (v.replace("−", "-") != expected.replace("−", "-"))
            contradictions += r["sign_contradicts_bold"]
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
    # chance agreement and Cohen's kappa on the located pairs
    p_fail = sum(1 for r in located if r["fail"]) / n if n else 0
    p_ns = sum(1 for r in located if r["verdict_class"] == "not_significant") / n if n else 0
    p_e = p_fail * p_ns + (1 - p_fail) * (1 - p_ns)
    p_o = agree / n if n else 0
    kappa = round((p_o - p_e) / (1 - p_e), 3) if n and p_e < 1 else None
    per_paper_2x2 = {}
    for r in located:
        d = per_paper_2x2.setdefault(r["paper"], {"located": 0, "agree": 0, "fail_ns": 0, "fail_sig": 0, "pass_ns": 0, "pass_sig": 0})
        d["located"] += 1
        ns = r["verdict_class"] == "not_significant"
        d["agree"] += (bool(r["fail"]) == ns)
        d[("fail_" if r["fail"] else "pass_") + ("ns" if ns else "sig")] += 1
    top3 = sorted(per_paper_2x2.values(), key=lambda d: -d["located"])[:3]
    items_all = json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))
    pages_of = collections.Counter(it["paper"] for it in items_all if it["paper"] in papers)
    pages_read_of = collections.Counter(items[i]["paper"] for i in read_ids if i in items)
    out = {"papers": len(papers), "papers_first_draw": first_draw, "papers_second_draw": len(papers2),
           "papers_fully_read": sum(1 for p_ in papers if pages_read_of.get(p_, 0) >= pages_of.get(p_, 0) and pages_of.get(p_, 0)),
           "pages_read": len(vpages), "tested_groups": len(rows),
           "ci_agree_papers": [round(vals[50], 1), round(vals[1949], 1)] if keys else None,
           "chance_agreement": round(100 * p_e, 1) if n else None, "kappa": kappa,
           # specific agreement on each side (Cicchetti and Feinstein), which kappa's prevalence dependence does not touch
           "specific_agreement_fail_ns": round(100 * 2 * xt["welch_fail_printed_not_significant"] / max(2 * xt["welch_fail_printed_not_significant"] + xt["welch_fail_printed_significant"] + xt["welch_pass_printed_not_significant"], 1), 1) if n else None,
           "specific_agreement_pass_sig": round(100 * 2 * xt["welch_pass_printed_significant"] / max(2 * xt["welch_pass_printed_significant"] + xt["welch_fail_printed_significant"] + xt["welch_pass_printed_not_significant"], 1), 1) if n else None,
           "top_three_share": round(100 * sum(d["located"] for d in top3) / n, 1) if n else None,
           "macro_agreement": round(100 * sum(d["agree"] / d["located"] for d in per_paper_2x2.values()) / len(per_paper_2x2), 1) if per_paper_2x2 else None,
           "per_paper_agreement_min": round(100 * min(d["agree"] / d["located"] for d in per_paper_2x2.values()), 1) if per_paper_2x2 else None,
           "per_paper_agreement_max": round(100 * max(d["agree"] / d["located"] for d in per_paper_2x2.values()), 1) if per_paper_2x2 else None,
           "sign_contradictions": contradictions, "sign_checked": sum(1 for r in located if "sign_contradicts_bold" in r),
           "sign_conventions": {k: v for k, v in sign_of.items()},
           "per_paper_2x2": per_paper_2x2,
           "effective_papers": round(n ** 2 / sum(d["located"] ** 2 for d in per_paper_2x2.values()), 1) if per_paper_2x2 else None,
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
           # of the located Welch failures, how many carry a printed significant verdict, and where they sit
           "welch_fail_located": sum(1 for r in located if r["fail"]),
           "welch_fail_located_papers": len({r["paper"] for r in located if r["fail"]}),
           "welch_fail_printed_significant_rest_papers": (lambda big3: len({r["paper"] for r in located if r["fail"] and r["verdict_class"] != "not_significant" and r["paper"] not in big3}))(
               set(sorted(by_paper, key=lambda k: -by_paper[k][0])[:3])),
           "papers_outside_top_three": max(len(by_paper) - 3, 0),
           "page_not_read_groups": sum(1 for r in rows if r["status"] == "page_not_read"),
           "page_not_read_papers": len({r["paper"] for r in rows if r["status"] == "page_not_read"}),
           "welch_fail_printed_significant_top_three": (lambda big3: sum(1 for r in located if r["fail"] and r["verdict_class"] != "not_significant" and r["paper"] in big3))(
               set(sorted(by_paper, key=lambda k: -by_paper[k][0])[:3])),
           "agree_without_top_three": (lambda big3: {"n": n - sum(by_paper[b][0] for b in big3), "agree": agree - sum(by_paper[b][1] for b in big3),
                                                      "papers": len(by_paper) - len(big3),
                                                      "pct": round(100 * (agree - sum(by_paper[b][1] for b in big3)) / max(n - sum(by_paper[b][0] for b in big3), 1), 1)})(
               sorted(by_paper, key=lambda k: -by_paper[k][0])[:3]) if by_paper else None,
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
