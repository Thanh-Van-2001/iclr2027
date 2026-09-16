"""Two human-labelling kits for the AAMAS paper, the checks six review
rounds asked for and no model can supply:

  A. protocol_check.csv    the rate papers of Section 6 with the model's
                           reading of K, seeds and protocol type pre-filled;
                           the labeller confirms or corrects each from the PDF
  B. empty_pages/          the pilot pages the census reader returned empty
                           and a random draw of the pages it read as results
                           tables with no single winner per line; one HTML
                           sheet with each page image and one question

Usage: python aamas/human_kits.py            (writes audits/human_aamas/)
       python aamas/human_score.py           (scores the filled files)
"""
import csv
import html
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from make_all_aamas import build_rate_set, rate_like, reader_protocol2  # noqa: E402

OUT = "audits/human_aamas"


def kit_a():
    cs = json.load(open("out/aamas/analysis.json", encoding="utf-8"))["_comparisons"]
    build_rate_set(cs)
    rate_papers = sorted({c["paper"] for c in cs if rate_like(c)})
    rd = json.load(open("out/aamas/protocol_reader2.json", encoding="utf-8"))
    proto, _, _ = reader_protocol2()
    recs = {}
    for line in open("data/extracted_aamas.jsonl", encoding="utf-8"):
        r = json.loads(line)
        recs[r["id"]] = r
    rows = []
    for pid in rate_papers:
        d = rd.get(pid, {})
        r = recs[pid]
        n_cmp = sum(1 for c in cs if c["paper"] == pid and rate_like(c))
        rows.append({
            "paper": pid, "title": r["title"], "pdf": f"data/corpus/{r['venue']}{r['year']}_{pid}.pdf",
            "rate_comparisons": n_cmp,
            "model_K": d.get("eval_episodes"), "model_K_sentence": (d.get("eval_sentence") or "")[:300],
            "model_seeds": d.get("seeds"), "model_seed_sentence": (d.get("seed_sentence") or "")[:300],
            "model_kind": d.get("episodes_kind"), "model_shares_instances": d.get("shares_eval_episodes"),
            "model_sd_over": d.get("sd_over"),
            # the labeller's columns
            "human_K": "", "human_seeds": "", "human_kind": "", "human_shares_instances": "", "human_sd_over": "",
            "human_note": "",
        })
    # the K-stating papers first: they carry Section 6
    rows.sort(key=lambda x: (x["model_K"] is None, x["paper"]))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "protocol_check.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("kit A:", len(rows), "rate papers,", sum(1 for x in rows if x["model_K"]), "with a model-read K")


def kit_b(n_random=30, seed=20260916):
    items = {it["id"]: it for it in json.load(open("audits/aamas_census/items.json", encoding="utf-8"))}
    labels = {p["id"]: p for p in json.load(open("audits/aamas_census/labels.json", encoding="utf-8"))}
    cross = json.load(open("out/aamas/reader_cross_pilot.json", encoding="utf-8"))
    key = {(it["paper"], it["page"]): iid for iid, it in items.items()}
    pilot_empty = [key[(p["paper"], p["page"])] for p in cross["per_page"] if p["g2"] == 0 and p["g1"] > 0]
    cs = json.load(open("out/aamas/analysis.json", encoding="utf-8"))["_comparisons"]
    parser_pages = {(c["paper"], c["page"]) for c in cs}
    none_pages = []
    for iid, lab in labels.items():
        it = items[iid]
        groups = sum(len(t.get("groups", [])) for t in lab.get("tables", []))
        results = any(str(t.get("results_table", "")).lower().startswith("y") for t in lab.get("tables", []))
        if groups == 0 and results and (it["paper"], it["page"]) in parser_pages and iid not in pilot_empty:
            none_pages.append(iid)
    rng = random.Random(seed)
    draw = sorted(rng.sample(none_pages, min(n_random, len(none_pages))))
    pages = [("pilot_empty", i) for i in pilot_empty] + [("orientation_none", i) for i in draw]
    d = os.path.join(OUT, "empty_pages")
    os.makedirs(os.path.join(d, "img"), exist_ok=True)
    rows = []
    for kind, iid in pages:
        src = os.path.join("audits/aamas_census/img", f"{iid}_page.png")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(d, "img", f"{iid}.png"))
        notes = "; ".join((t.get("note") or "")[:120] for t in labels[iid].get("tables", []))
        rows.append({"id": iid, "kind": kind, "paper": items[iid]["paper"], "page": items[iid]["page"],
                     "title": items[iid]["title"], "census_note": notes,
                     "parser_comparisons": sum(1 for c in cs if (c["paper"], c["page"]) == (items[iid]["paper"], items[iid]["page"]))})
    json.dump(rows, open(os.path.join(d, "items.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    # one HTML sheet: the page, one question, a count
    parts = ["<!doctype html><meta charset='utf-8'><title>Empty census pages</title>",
             "<style>body{font-family:sans-serif;max-width:1100px;margin:auto}img{width:100%;border:1px solid #999}"
             ".q{background:#f6f6f6;padding:10px;margin:8px 0 30px}label{margin-right:14px}</style>",
             "<h2>Empty census pages: does the page hold a results table where each row (or each column) has exactly one bold cell?</h2>",
             "<p>Answer for the page as a whole. <b>yes</b>: at least one results table on the page marks exactly one bold cell per row or per column "
             "(a table split into blocks, one bold per column in each block, counts as yes). <b>no</b>: every table on the page has several bold cells "
             "per line, or bolds the authors' whole row, or is not a results table. <b>unclear</b>: cannot tell. If yes, type the number of such rows or columns.</p>",
             "<p>Save with the button at the end; the file downloads as empty_pages_labels.csv.</p><form id='f'>"]
    for r in rows:
        parts.append(f"<div class='q'><b>{r['id']}</b> ({r['kind']}) &mdash; {html.escape(r['title'][:90])}<br>"
                     f"<label><input type='radio' name='a_{r['id']}' value='yes'> yes</label>"
                     f"<label><input type='radio' name='a_{r['id']}' value='no'> no</label>"
                     f"<label><input type='radio' name='a_{r['id']}' value='unclear'> unclear</label>"
                     f" &nbsp; groups: <input name='n_{r['id']}' size='4'></div>"
                     f"<img src='img/{r['id']}.png'>")
    parts.append("<p><button type='button' onclick='save()'>Save labels</button></p></form>"
                 "<script>function save(){const f=document.getElementById('f');let out='id,answer,groups\\n';"
                 "const ids=" + json.dumps([r["id"] for r in rows]) + ";for(const i of ids){const a=f.querySelector('input[name=a_'+i+']:checked');"
                 "out+=i+','+(a?a.value:'')+','+(f.elements['n_'+i].value||'')+'\\n';}"
                 "const b=new Blob([out],{type:'text/csv'});const u=URL.createObjectURL(b);const l=document.createElement('a');"
                 "l.href=u;l.download='empty_pages_labels.csv';l.click();}</script>")
    open(os.path.join(d, "label.html"), "w", encoding="utf-8").write("\n".join(parts))
    print("kit B:", len(pilot_empty), "pilot pages +", len(draw), "orientation-none pages ->", d)


if __name__ == "__main__":
    kit_a()
    kit_b()
