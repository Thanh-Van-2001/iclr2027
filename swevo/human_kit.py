"""A human-labelling kit for the layout the census is quoted for: reader
groups in tables whose dispersion sits in a separate column or row, with
both dispersions read. A person labels the bold cell's mean and deviation,
the best non-bold rival's mean and deviation, and the run count, from the
page image alone, given only the table caption's first words and the
group's label. Scored against the reader by swevo/human_score.py.

Usage: python swevo/human_kit.py [--n 100 --seed 2026]
"""
import argparse
import csv
import html
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from pages_score import _bar_num  # noqa: E402

KIT = "audits/swevo_census"
OUT = "audits/swevo_human"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--per-page", type=int, default=3)
    args = ap.parse_args(argv)
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    kinds = {}
    if os.path.exists("out/swevo/kinds_merged.csv"):
        kinds = {r["id"]: r["label"] for r in csv.DictReader(open("out/swevo/kinds_merged.csv", encoding="utf-8", newline=""))}
    pool = []
    for iid, pg in labels.items():
        for ti, t in enumerate(pg.get("tables", [])):
            if not str(t.get("results_table", "")).lower().startswith("y"):
                continue
            if not str(t.get("bar_form", "")).lower().startswith("separate"):
                continue
            for gi, g in enumerate(t.get("groups", [])):
                if _bar_num(g.get("winner_disp")) is None or _bar_num(g.get("runner_disp")) is None:
                    continue
                pool.append({"page_id": iid, "paper": items[iid]["paper"], "page": items[iid]["page"],
                             "kind": kinds.get(items[iid]["paper"], "unlabelled"),
                             "table_index": ti, "caption_start": t.get("caption_start", ""), "bar_form": t.get("bar_form", ""),
                             "bar_kind": t.get("bar_kind", ""), "n_runs_reader": t.get("n_runs", ""), "n_source_reader": t.get("n_source", ""),
                             "group_index": gi, "label": g.get("label", ""), "direction": g.get("direction", ""),
                             "reader": {k: g.get(k, "") for k in ("winner_mean", "winner_disp", "runner_mean", "runner_disp")}})
    rng = random.Random(args.seed)
    rng.shuffle(pool)
    per_page, chosen = {}, []
    # alternate kinds so that both strata are represented
    by_kind = {}
    for g in pool:
        by_kind.setdefault(g["kind"], []).append(g)
    order = sorted(by_kind, key=lambda k: -len(by_kind[k]))
    while len(chosen) < args.n and any(by_kind.values()):
        for k in order:
            while by_kind[k]:
                g = by_kind[k].pop()
                if per_page.get(g["page_id"], 0) < args.per_page:
                    per_page[g["page_id"]] = per_page.get(g["page_id"], 0) + 1
                    chosen.append(g)
                    break
            if len(chosen) >= args.n:
                break
    chosen.sort(key=lambda g: (g["page_id"], g["table_index"], g["group_index"]))
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    rows = []
    for i, g in enumerate(chosen, 1):
        g["id"] = f"{i:03d}"
        src = os.path.join(KIT, "img", f"{g['page_id']}_page.png")
        dst = os.path.join(OUT, "img", f"{g['page_id']}.png")
        if not os.path.exists(dst):
            shutil.copy(src, dst)
        runs = os.path.join(KIT, "img", f"{g['page_id']}_runs.txt")
        g["run_sentences"] = open(runs, encoding="utf-8").read()[:3000] if os.path.exists(runs) else ""
        rows.append(g)
    json.dump({"n": args.n, "seed": args.seed, "per_page": args.per_page, "pool": len(pool),
               "pool_pages": len({g["page_id"] for g in pool}), "drawn": len(rows),
               "kinds": {k: sum(1 for g in rows if g["kind"] == k) for k in set(g["kind"] for g in rows)}},
              open(os.path.join(OUT, "draw.json"), "w", encoding="utf-8"), indent=1)
    json.dump(rows, open(os.path.join(OUT, "items.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "labels_template.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "results_table", "bold_ok", "winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs", "note"])
        for g in rows:
            w.writerow([g["id"], "", "", "", "", "", "", "", ""])
    parts = ["<!doctype html><meta charset='utf-8'><title>Separate-column groups</title>",
             "<style>body{font-family:sans-serif;max-width:1200px;margin:auto}img{width:100%;border:1px solid #999}"
             ".q{background:#f6f6f6;padding:10px;margin:8px 0 20px;position:sticky;top:0}input[type=text]{width:110px}"
             "details{margin:6px 0}</style>",
             "<h2>Reader check on the separate-column layout: 100 bold cells</h2>",
             "<p>For each item the page is shown with the table's caption start and the group's label (the function or row/column name). "
             "Find the group; its <b>bold</b> cell is the winner. Record, exactly as printed: the winner's mean and its deviation (from the Std "
             "column or row that belongs to it), the best non-bold cell's mean and deviation in the same group, and the run count that "
             "applies to the table (from the caption, the page, or the run sentences under the item; write none if nothing states one). "
             "Write <i>unclear</i> when a digit cannot be read. <b>results_table</b>: y/n. <b>bold_ok</b>: y if the group has exactly one bold cell.</p>",
             "<p>The button at the end downloads labels.csv; save it as audits/swevo_human/labels.csv.</p><form id='f'>"]
    last = None
    for g in rows:
        parts.append(f"<div class='q'><b>{g['id']}</b> &nbsp; caption: <i>{html.escape(str(g['caption_start'])[:80])}</i> &nbsp; group label: <b>{html.escape(str(g['label']))}</b> &nbsp; direction: {html.escape(str(g['direction']))}<br>"
                     f"results_table <input type='text' name='rt_{g['id']}' size='2'> bold_ok <input type='text' name='bo_{g['id']}' size='2'> "
                     f"winner mean <input type='text' name='wm_{g['id']}'> winner disp <input type='text' name='wd_{g['id']}'> "
                     f"runner mean <input type='text' name='rm_{g['id']}'> runner disp <input type='text' name='rd_{g['id']}'> "
                     f"n_runs <input type='text' name='nr_{g['id']}' size='5'> note <input type='text' name='nt_{g['id']}' size='30'></div>")
        if g["page_id"] != last:
            parts.append(f"<details open><summary>run sentences of this paper</summary><pre style='white-space:pre-wrap;font-size:12px'>{html.escape(g['run_sentences'])}</pre></details>")
            parts.append(f"<img src='img/{g['page_id']}.png'>")
            last = g["page_id"]
        else:
            parts.append(f"<p><i>(same page as above)</i></p>")
    ids = json.dumps([g["id"] for g in rows])
    parts.append("<p><button type='button' onclick='save()'>Save labels</button></p></form>"
                 "<script>function save(){const f=document.getElementById('f');let out='id,results_table,bold_ok,winner_mean,winner_disp,runner_mean,runner_disp,n_runs,note\\n';"
                 "const ids=" + ids + ";for(const i of ids){const v=k=>(f.elements[k+'_'+i].value||'').replace(/,/g,';');"
                 "out+=[i,v('rt'),v('bo'),v('wm'),v('wd'),v('rm'),v('rd'),v('nr'),v('nt')].join(',')+'\\n';}"
                 "const b=new Blob([out],{type:'text/csv'});const u=URL.createObjectURL(b);const l=document.createElement('a');"
                 "l.href=u;l.download='labels.csv';l.click();}</script>")
    open(os.path.join(OUT, "label.html"), "w", encoding="utf-8").write("\n".join(parts))
    print(len(rows), "groups from", len({g['page_id'] for g in rows}), "pages (pool", len(pool), ") ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
