"""Prepare the run-count adjudication of held-out items where the reader found no count.

For each testable held-out item whose reader recorded no run count while the
pipeline attached one, write the paper's full text, the pipeline's count and
where the pattern matched it, so a reader with the whole paper can decide whether
the count applies to the boxed table.
"""
from __future__ import annotations

import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz  # noqa: E402

import extract as ex  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402


def main(items="audits/gold_b/items.json", labels="audits/gold_b/labels.csv",
         analysis="out/analysis_2025.json", out_dir="out/adjudicate",
         cache_dir="out/gold_pdf_cache") -> None:
    its = {i["id"]: i for i in json.load(open(items, encoding="utf-8"))}
    rows = [r for r in csv.DictReader(open(labels, encoding="utf-8")) if r["stratum"] == "testable"]
    cmps = json.load(open(analysis, encoding="utf-8"))["_comparisons"]
    idx: dict = {}
    for c in cmps:
        idx.setdefault((c["paper"], c["table"], c["page"]), []).append(c)
    index = {}
    for s in ("neurips2025", "icml2025"):
        for rec in SOURCES[s]():
            index[rec["id"]] = rec
    os.makedirs(out_dir, exist_ok=True)
    manifest = []
    for r in rows:
        if r["n_runs"].strip().lower() not in ("", "none"):
            continue
        it = its[r["id"]]
        cs = idx.get((it["paper"], it["table"], it["page"]), [])
        m = [c for c in cs if c["winner"] == it["pipeline"]["winner"]] or cs
        c = m[0] if m else None
        n = c.get("n_runs") if c else None
        entry = {"id": r["id"], "paper": it["paper"], "page": it["page"],
                 "image": f"audits/gold_b/img/{it['image']}",
                 "pipeline_n_runs": n, "pipeline_n_source": (c or {}).get("n_runs_source"),
                 "pipeline_kind": (c or {}).get("dispersion_kind"),
                 "reader_note": r["note"]}
        if n is None:
            entry["case"] = "pipeline has no count either"
            manifest.append(entry)
            continue
        pdf = os.path.join(cache_dir, it["paper"] + ".pdf")
        if not os.path.exists(pdf):
            data = _get(index[it["paper"]]["pdf"])
            open(pdf, "wb").write(data)
        doc = fitz.open(pdf)
        pages = [p.get_text() for p in doc]
        full = "\n".join(pages)
        txt = os.path.join(out_dir, f"{r['id']}_fulltext.txt")
        open(txt, "w", encoding="utf-8").write(full)
        # where the pattern matched
        hits = []
        for name in ("N_RUNS", "N_TIMES", "N_SEEDED", "N_OVER", "SEED_LIST"):
            rx = getattr(ex, name)
            for mm in rx.finditer(full):
                hits.append({"pattern": name, "page": next((k + 1 for k, p in enumerate(pages)
                                                            if mm.group(0) in p), None),
                             "context": full[max(0, mm.start() - 120): mm.end() + 80].replace("\n", " ")})
        entry.update({"fulltext": txt, "matches": hits[:12],
                      "table_page_number": it["page"] + 1,
                      "caption": (c or {}).get("caption", "")[:300]})
        manifest.append(entry)
        print(r["id"], it["paper"][:8], "n=", n, len(hits), "matches")
    json.dump(manifest, open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8"), indent=1)
    print(len(manifest), "items;", sum(1 for e in manifest if "fulltext" in e), "to adjudicate")


if __name__ == "__main__":
    main()
