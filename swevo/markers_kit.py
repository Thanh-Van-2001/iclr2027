"""The per-cell-verdict field is the one the two full-text readers disagree
on, one way: the second quotes a printed verdict where the first says none
is printed. This writes the disputed papers to a sheet for a person to
adjudicate from the paper itself (audits/swevo_markers/adjudicate.csv, with
the two readers' quoted sentences and the PDF path), together with the
census papers whose verdicts were located and whose first reading says no
verdict is printed.

Usage: python swevo/markers_kit.py
"""
import csv
import glob
import json
import os

OUT = "audits/swevo_markers"


def main() -> int:
    first = {}
    for path in sorted(glob.glob("out/swevo/test_reader_part*.json")) + sorted(glob.glob("out/swevo/test_reader_v2_part*.json")):
        first.update(json.load(open(path, encoding="utf-8")))
    second = json.load(open("out/swevo/test_reader_second.json", encoding="utf-8"))
    if os.path.exists("out/swevo/test_reader_second_v2.json"):
        second.update(json.load(open("out/swevo/test_reader_second_v2.json", encoding="utf-8")))
    index = {r["id"]: r for r in json.load(open("out/swevo/index.json", encoding="utf-8"))}
    kinds = {r["id"]: r["label"] for r in csv.DictReader(open("out/swevo/kinds_merged.csv", encoding="utf-8", newline=""))}

    def yes(v):
        return str(v.get("markers", "")).lower().startswith("y")
    rows = []
    for p in second:
        if p in first and "parse_error" not in first[p] and "parse_error" not in second[p] and yes(first[p]) != yes(second[p]):
            rows.append((p, "disputed"))
    vc = "out/swevo/verdict_crosstab.json"
    if os.path.exists(vc):
        d = json.load(open(vc, encoding="utf-8"))
        for p in d.get("per_paper", {}):
            if p in first and not yes(first[p]) and (p, "disputed") not in rows:
                rows.append((p, "verdict located, first reader says none"))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "adjudicate.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "why", "kind", "title", "first_markers", "first_sentence", "second_markers", "second_sentence", "pdf", "markers_human", "sentence_human", "note"])
        for p, why in rows:
            w.writerow([p, why, kinds.get(p, ""), index.get(p, {}).get("title", ""), first[p].get("markers", ""), str(first[p].get("markers_sentence", ""))[:300],
                        second.get(p, {}).get("markers", ""), str(second.get(p, {}).get("markers_sentence", ""))[:300], (glob.glob(f"data/corpus_oa/*_{p}.pdf") or [""])[0], "", "", ""])
    print("wrote", os.path.join(OUT, "adjudicate.csv"), len(rows), "papers")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
