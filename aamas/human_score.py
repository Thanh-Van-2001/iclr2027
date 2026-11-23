"""Score the human kits of aamas/human_kits.py against the model readings.

  audits/human_aamas/protocol_check.csv        -> out/aamas/human_protocol.json
  audits/human_aamas/empty_pages_labels.csv    -> out/aamas/human_empty_pages.json

A row counts as labelled when the human column is filled ("same" accepts
the model's value). Only filled rows are scored; the counts say how many.
"""
import csv
import json
import os

KIT = "audits/human_aamas"
# a checkout without the run records has no out/aamas yet
os.makedirs("out/aamas", exist_ok=True)


def _val(s):
    s = (s or "").strip().lower()
    if s in ("", "?"):
        return None
    if s in ("none", "null", "no", "not stated", "-"):
        return "none"
    return s


def protocol():
    path = os.path.join(KIT, "protocol_check.csv")
    if not os.path.exists(path):
        return {}
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    out = {"papers": len(rows), "labelled": 0, "fields": {}}
    for field in ("K", "seeds", "kind", "shares_instances", "sd_over"):
        agree = n = 0
        for r in rows:
            h = _val(r.get(f"human_{field}"))
            if h is None:
                continue
            m = _val(r.get(f"model_{field}")) or "none"
            n += 1
            agree += (h == "same") or (h == m)
        out["fields"][field] = {"n": n, "agree": agree, "pct": round(100 * agree / n, 1) if n else None}
    out["labelled"] = sum(1 for r in rows if any(_val(r.get(f"human_{f}")) is not None for f in ("K", "seeds", "kind")))
    out["k_papers_labelled"] = sum(1 for r in rows if _val(r.get("human_K")) is not None and r.get("model_K"))
    json.dump(out, open("out/aamas/human_protocol.json", "w", encoding="utf-8"), indent=1)
    return out


def empty_pages():
    path = os.path.join(KIT, "empty_pages_labels.csv")
    if not os.path.exists(path):
        return {}
    items = {r["id"]: r for r in json.load(open(os.path.join(KIT, "empty_pages", "items.json"), encoding="utf-8"))}
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    out = {}
    for kind in ("pilot_empty", "orientation_none"):
        sub = [r for r in rows if items.get(r["id"], {}).get("kind") == kind and r.get("answer")]
        out[kind] = {"labelled": len(sub),
                     "yes": sum(1 for r in sub if r["answer"] == "yes"),
                     "no": sum(1 for r in sub if r["answer"] == "no"),
                     "unclear": sum(1 for r in sub if r["answer"] == "unclear"),
                     "groups": sum(int(r["groups"]) for r in sub if (r.get("groups") or "").strip().isdigit())}
    json.dump(out, open("out/aamas/human_empty_pages.json", "w", encoding="utf-8"), indent=1)
    return out


if __name__ == "__main__":
    print(json.dumps({"protocol": protocol(), "empty_pages": empty_pages()}, indent=1))
