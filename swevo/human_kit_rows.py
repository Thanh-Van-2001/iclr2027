"""The second human kit: recall on the Mean/Std-row layout. From the pages
re-read under the row instruction, draw groups whose bold cell is a mean
row: half that the re-read gives both dispersions (pairing precision) and half
that it still reads as bar-less (recall), capped at three per page. The
person records whether a deviation row or column is printed for the bold
cell and for its rival, the two values, and the run count; the scorer then
gives the pre-registered reader's false-bar-less rate, the re-read's pairing
precision, and Welch on the person's values.

Usage: python swevo/human_kit_rows.py [--n 100 --seed 2026]
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
sys.path.insert(0, HERE)
from pages_score import _bar_num  # noqa: E402
from gold_set import _num  # noqa: E402
from census_readings import ROW_LABEL  # noqa: E402

KIT = "audits/swevo_census"
ROWS = "audits/swevo_census_rows"
OUT = "audits/swevo_human_rows"


def _groups(pg: dict):
    for ti, t in enumerate(pg.get("tables", [])):
        if not str(t.get("results_table", "")).lower().startswith("y"):
            continue
        for gi, g in enumerate(t.get("groups", [])):
            yield ti, t, gi, g


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--per-page", type=int, default=3)
    args = ap.parse_args(argv)
    items = {it["id"]: it for it in json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))}
    before = {p["id"]: p for p in json.load(open(os.path.join(KIT, "labels.json"), encoding="utf-8"))}
    import glob
    after = {}
    for path in sorted(glob.glob(os.path.join(ROWS, "labels_shard*.json"))):
        for p in json.load(open(path, encoding="utf-8")):
            if not str(p.get("note", "")).startswith("failed"):
                after[p["id"]] = p
    kinds = {}
    if os.path.exists("out/swevo/kinds_merged.csv"):
        kinds = {r["id"]: r["label"] for r in csv.DictReader(open("out/swevo/kinds_merged.csv", encoding="utf-8", newline=""))}
    changed, unchanged = [], []
    for iid, pg in after.items():
        old = {}
        if iid in before:
            for _, t0, _, g0 in _groups(before[iid]):
                w0 = _num(g0.get("winner_mean"))
                if w0 is not None:
                    old[(str(g0.get("label", "")).strip().lower(), w0)] = (_bar_num(g0.get("winner_disp")) is not None and _bar_num(g0.get("runner_disp")) is not None)
        for ti, t, gi, g in _groups(pg):
            if ROW_LABEL.search(str(g.get("label", "")).strip()):
                continue
            w = _num(g.get("winner_mean"))
            if w is None:
                continue
            barred_after = _bar_num(g.get("winner_disp")) is not None and _bar_num(g.get("runner_disp")) is not None
            key = (str(g.get("label", "")).strip().lower(), w)
            barred_before = old.get(key)
            rec = {"page_id": iid, "paper": items[iid]["paper"], "page": items[iid]["page"], "kind": kinds.get(items[iid]["paper"], "unlabelled"),
                   "table_index": ti, "caption_start": t.get("caption_start", ""), "bar_form_after": t.get("bar_form", ""),
                   "bar_kind": t.get("bar_kind", ""), "n_runs_reader": t.get("n_runs", ""), "n_source_reader": t.get("n_source", ""),
                   "group_index": gi, "label": g.get("label", ""), "direction": g.get("direction", ""),
                   "reader": {k: g.get(k, "") for k in ("winner_mean", "winner_disp", "runner_mean", "runner_disp")},
                   "barred_before": barred_before, "barred_after": barred_after,
                   "stratum": "barred" if barred_after else "barless"}
            (changed if rec["stratum"] == "barred" else unchanged).append(rec)
    rng = random.Random(args.seed)
    rng.shuffle(changed)
    rng.shuffle(unchanged)
    per_page, chosen = {}, []
    for pool in (changed, unchanged):
        k = 0
        for g in pool:
            if k >= args.n // 2:
                break
            if per_page.get(g["page_id"], 0) < args.per_page:
                per_page[g["page_id"]] = per_page.get(g["page_id"], 0) + 1
                chosen.append(g)
                k += 1
    chosen.sort(key=lambda g: (g["page_id"], g["table_index"], g["group_index"]))
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    rows = []
    for i, g in enumerate(chosen, 1):
        g["id"] = f"{i:03d}"
        dst = os.path.join(OUT, "img", f"{g['page_id']}.png")
        if not os.path.exists(dst):
            shutil.copy(os.path.join(KIT, "img", f"{g['page_id']}_page.png"), dst)
        runs = os.path.join(KIT, "img", f"{g['page_id']}_runs.txt")
        g["run_sentences"] = open(runs, encoding="utf-8").read()[:3000] if os.path.exists(runs) else ""
        rows.append(g)
    json.dump({"n": args.n, "seed": args.seed, "per_page": args.per_page, "pool_changed": len(changed), "pool_unchanged": len(unchanged),
               "drawn": len(rows), "strata": {k: sum(1 for g in rows if g["stratum"] == k) for k in ("barred", "barless")},
               "kinds": {k: sum(1 for g in rows if g["kind"] == k) for k in set(g["kind"] for g in rows)}},
              open(os.path.join(OUT, "draw.json"), "w", encoding="utf-8"), indent=1)
    json.dump(rows, open(os.path.join(OUT, "items.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, "labels_template.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "results_table", "bold_ok", "std_printed", "winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs", "note"])
        for g in rows:
            w.writerow([g["id"]] + [""] * 9)
    parts = ["<!doctype html><meta charset='utf-8'><title>Mean/Std-row groups</title>",
             "<style>body{font-family:sans-serif;max-width:1200px;margin:auto}img{width:100%;border:1px solid #999}"
             ".q{background:#f6f6f6;padding:10px;margin:8px 0 20px;position:sticky;top:0}input[type=text]{width:110px}details{margin:6px 0}</style>",
             "<h2>Reader check on the Mean/Std-row layout: 100 bold cells</h2>",
             "<p>For each item the page is shown with the table's caption start and the group's label. Find the group; its <b>bold</b> cell is the winner. "
             "Record: <b>results_table</b> (y/n); <b>bold_ok</b> (y if the group has exactly one bold cell); <b>std_printed</b> (y if a standard deviation is printed "
             "for the bold cell anywhere in the table, in the cell, in a row beneath, or in a column; n if none is); then, exactly as printed, the winner's mean and its deviation, "
             "the best non-bold cell's mean and deviation in the same group, and the run count that applies (none if nothing states one). Write <i>unclear</i> for a digit you cannot read.</p>",
             "<p>The button at the end downloads labels.csv; save it as audits/swevo_human_rows/labels.csv.</p><form id='f'>"]
    last = None
    for g in rows:
        parts.append(f"<div class='q'><b>{g['id']}</b> &nbsp; caption: <i>{html.escape(str(g['caption_start'])[:80])}</i> &nbsp; group label: <b>{html.escape(str(g['label']))}</b> &nbsp; direction: {html.escape(str(g['direction']))}<br>"
                     f"results_table <input type='text' name='rt_{g['id']}' size='2'> bold_ok <input type='text' name='bo_{g['id']}' size='2'> std_printed <input type='text' name='sp_{g['id']}' size='2'> "
                     f"winner mean <input type='text' name='wm_{g['id']}'> winner disp <input type='text' name='wd_{g['id']}'> "
                     f"runner mean <input type='text' name='rm_{g['id']}'> runner disp <input type='text' name='rd_{g['id']}'> "
                     f"n_runs <input type='text' name='nr_{g['id']}' size='5'> note <input type='text' name='nt_{g['id']}' size='30'></div>")
        if g["page_id"] != last:
            parts.append(f"<details open><summary>run sentences of this paper</summary><pre style='white-space:pre-wrap;font-size:12px'>{html.escape(g['run_sentences'])}</pre></details>")
            parts.append(f"<img src='img/{g['page_id']}.png'>")
            last = g["page_id"]
        else:
            parts.append("<p><i>(same page as above)</i></p>")
    ids = json.dumps([g["id"] for g in rows])
    parts.append("<p><button type='button' onclick='save()'>Save labels</button></p></form>"
                 "<script>function save(){const f=document.getElementById('f');let out='id,results_table,bold_ok,std_printed,winner_mean,winner_disp,runner_mean,runner_disp,n_runs,note\\n';"
                 "const ids=" + ids + ";for(const i of ids){const v=k=>(f.elements[k+'_'+i].value||'').replace(/,/g,';');"
                 "out+=[i,v('rt'),v('bo'),v('sp'),v('wm'),v('wd'),v('rm'),v('rd'),v('nr'),v('nt')].join(',')+'\\n';}"
                 "const b=new Blob([out],{type:'text/csv'});const u=URL.createObjectURL(b);const l=document.createElement('a');"
                 "l.href=u;l.download='labels.csv';l.click();}</script>")
    open(os.path.join(OUT, "label.html"), "w", encoding="utf-8").write("\n".join(parts))
    print(len(rows), "groups from", len({g['page_id'] for g in rows}), "pages (pools", len(changed), "barred,", len(unchanged), "bar-less) ->", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
