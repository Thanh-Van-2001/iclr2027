"""Score audits/human/verify.csv: one person's correct / wrong / unclear verdict
on the pipeline's reading of each frozen-set item, given the reading.

Usage: python study/human_verify_score.py [verify.csv] [items.json] [out.json]
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine.stats import wilson_interval  # noqa: E402
from gold_set import _pipeline_test  # noqa: E402

argv = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--") and "=" in a)
VERIFY = argv[0] if argv else "audits/human/verify.csv"
ITEMS = argv[1] if len(argv) > 1 else "audits/gold_d/items.json"
OUT = argv[2] if len(argv) > 2 else "out/human_verify.json"

with open(ITEMS, encoding="utf-8") as fh:
    items = {it["id"]: it for it in json.load(fh)}
with open(VERIFY, encoding="utf-8", newline="") as fh:
    rows = [r for r in csv.DictReader(fh) if r.get("verdict", "").strip()]


def rate(hits, n):
    lo, hi = wilson_interval(hits, n) if n else (0.0, 0.0)
    return {"correct": hits, "n": n, "pct": round(100 * hits / n, 1) if n else None,
            "ci": [round(100 * lo, 1), round(100 * hi, 1)]}


out = {"design": "verification: the person saw the pipeline's winner and runner-up boxed on the "
                 "rendered table and its values, bar kind and run count, and marked the whole "
                 "reading correct, wrong or unclear", "n_answered": len(rows)}
for stratum in ("testable", "no_bar", "all"):
    sel = [r for r in rows if stratum == "all" or r["stratum"] == stratum]
    judged = [r for r in sel if r["verdict"] in ("correct", "wrong")]
    out[stratum] = {
        "correct_of_judged": rate(sum(r["verdict"] == "correct" for r in judged), len(judged)),
        "correct_of_all": rate(sum(r["verdict"] == "correct" for r in sel), len(sel)),
        "unclear": sum(r["verdict"] == "unclear" for r in sel),
        "wrong_ids": [r["id"] for r in sel if r["verdict"] == "wrong"],
        "notes": {r["id"]: r["note"] for r in sel if r.get("note", "").strip()},
    }
# Pipeline verdicts on the items the person confirmed: the failure rate on
# human-confirmed readings, which the paper can set beside the headline.
conf = [items[r["id"]] for r in rows if r["stratum"] == "testable" and r["verdict"] == "correct"]
tests = [_pipeline_test(it) for it in conf]
tests = [t for t in tests if t]
out["testable"]["pipeline_fail_on_confirmed"] = rate(sum(t["p"] >= 0.05 for t in tests), len(tests))
# Agreement with the machine readers' majority on whether the pipeline's claim
# (bold cell, winner and rival values) holds, over the items the person judged.
READERS = ["audits/gold_d/labels.csv", "audits/gold_d_reader2/labels.csv", "audits/gold_d_gemini/labels.csv"]


def _num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


machine = {}
for path in READERS:
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8", newline="") as fh:
        for lb in csv.DictReader(fh):
            it = items.get(lb["id"])
            if not it or lb["id"] not in {r["id"] for r in rows}:
                continue
            pl = it["pipeline"]
            ok = (lb.get("bold_ok", "").lower().startswith("y") and _num(lb.get("winner_mean")) == pl["winner"]
                  and _num(lb.get("runner_mean")) == pl["runner_up"])
            machine.setdefault(lb["id"], []).append(ok)
judged = [r for r in rows if r["verdict"] in ("correct", "wrong") and r["id"] in machine]
agree = sum((r["verdict"] == "correct") == (sum(machine[r["id"]]) * 2 > len(machine[r["id"]])) for r in judged)
out["agreement_with_machine_majority"] = rate(agree, len(judged))
out["agreement_with_machine_majority"]["readers"] = len([p for p in READERS if os.path.exists(p)])
papers = {items[r["id"]]["paper"] for r in rows}
out["n_papers"] = len(papers)
out["verdicts"] = {v: sum(r["verdict"] == v for r in rows) for v in ("correct", "wrong", "unclear")}
if "started" in opts and "saved" in opts:
    # --started: when the page was published (git commit time); --saved: the
    # exported file's modification time. Both ISO 8601 with offset.
    from datetime import datetime
    t0, t1 = datetime.fromisoformat(opts["started"]), datetime.fromisoformat(opts["saved"])
    out["timing"] = {"started": opts["started"], "saved": opts["saved"],
                     "elapsed_minutes": round((t1 - t0).total_seconds() / 60, 1)}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, ensure_ascii=False)
print(json.dumps({k: (v["correct_of_judged"] if isinstance(v, dict) and "correct_of_judged" in v else v)
                  for k, v in out.items() if k != "design"}, ensure_ascii=False))
