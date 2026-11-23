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
       python aamas/human_kits.py --html-only
                                             (rewrites empty_pages/label.html from the existing
                                              empty_pages/items.json; no redraw, no run records needed)
       python aamas/human_score.py           (scores the filled files)
"""
import csv
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "study"))

OUT = "audits/human_aamas"


def kit_a():
    # imported here so that --html-only runs on a checkout without the run records
    from make_all_aamas import build_rate_set, rate_like, reader_protocol2  # noqa: E402
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
    write_empty_pages_html()
    print("kit B:", len(pilot_empty), "pilot pages +", len(draw), "orientation-none pages ->", d)


EMPTY_INTRO = """
<h3>One question per page</h3>
Does the page hold a results table in which a row (or a column) has <b>exactly one bold cell</b>?
Answer for the page as a whole. <b>yes</b>: at least one results table on the page marks exactly one bold cell per row
or per column (a table split into blocks, one bold per column in each block, counts as yes); type how many such rows or
columns there are. <b>no</b>: every table on the page has several bold cells per line, or bolds the authors' whole row,
or is not a results table. <b>unclear</b>: cannot tell.
<h3>Images</h3>
Some page images are not shipped; for those a red note says so, and <b>Open the full paper</b> opens
the public PDF at the right page.
Enter your annotator ID first; answers autosave in this browser; <b>Export CSV</b> downloads
<code>empty_pages_labels.csv</code>. Send that file unchanged.
"""


def write_empty_pages_html():
    """Rewrite empty_pages/label.html from the frozen empty_pages/items.json.

    The 35 pages are census pages, whose renders are not shipped. For each page
    the sheet shows, in order of preference: a local census render
    (empty_pages/img/<id>.png, produced from data/corpus by kit_b), the shipped
    pilot render of the same paper page (audits/aamas_pages/img, copied into
    empty_pages/img_shipped/), or nothing, with the PDF link. Which one each page
    got is written to empty_pages/image_status.json, so a missing image is a
    recorded fact rather than a broken link.
    """
    from human_kit_ui import form_kit_html  # noqa: E402
    d = os.path.join(OUT, "empty_pages")
    rows = json.load(open(os.path.join(d, "items.json"), encoding="utf-8"))
    pilot = {(it["paper"], it["page"]): it["id"] for it in json.load(open("audits/aamas_pages/items.json", encoding="utf-8"))}
    url_path = os.path.join(OUT, "paper_urls.json")
    urls = json.load(open(url_path, encoding="utf-8")) if os.path.exists(url_path) else {}
    status, view = {}, []
    for r in rows:
        local = os.path.join(d, "img", f"{r['id']}.png")
        pid = pilot.get((r["paper"], r["page"]))
        if os.path.exists(local):
            image, st = f"img/{r['id']}.png", "local_census_render"
        elif pid and os.path.exists(os.path.join("audits", "aamas_pages", "img", f"{pid}_page.png")):
            os.makedirs(os.path.join(d, "img_shipped"), exist_ok=True)
            shutil.copyfile(os.path.join("audits", "aamas_pages", "img", f"{pid}_page.png"),
                            os.path.join(d, "img_shipped", f"{r['id']}.png"))
            image, st = f"img_shipped/{r['id']}.png", "shipped_pilot_render"
        else:
            image, st = None, "missing_needs_data_corpus_or_pdf"
        u = urls.get(r["paper"])
        status[r["id"]] = {"status": st, "pilot_id": pid, "pdf_page": r["page"] + 1, "pdf_url": u["pdf"] if u else None}
        links = [{"label": f"Open the full paper at PDF page {r['page'] + 1}", "href": f"{u['pdf']}#page={r['page'] + 1}"}] if u else []
        view.append({"id": r["id"], "sets": ["all"], "image": image,
                     "image_note": "This page image is not shipped: open the full paper with the link below.",
                     "meta": [f"Paper: {r['title']}", f"PDF page {r['page'] + 1}"], "links": links})
    json.dump(status, open(os.path.join(d, "image_status.json"), "w", encoding="utf-8"), indent=1)
    fields = [
        {"name": "answer", "label": "Does the page hold a results table with exactly one bold cell in a row or a column?",
         "kind": "select", "options": [["yes", "yes"], ["no", "no"], ["unclear", "unclear"]]},
        {"name": "groups", "label": "If yes: how many such rows or columns (an estimate is fine)", "kind": "text",
         "req": {"if": ["answer", ["yes"]]}},
        {"name": "note", "label": "Note (optional)", "kind": "area", "req": "never"},
    ]
    html_text = form_kit_html(kit="empty_pages", version="aamas-hv-1", title="Bold cells on 35 pages",
                              intro_html=EMPTY_INTRO, items=view, fields=fields, gates=[],
                              sets={"all": "All 35"},
                              default_set="all", export_name="empty_pages_labels.csv")
    with open(os.path.join(d, "label.html"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html_text)
    counts = {}
    for v in status.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print("empty_pages sheet:", counts)
    return status


if __name__ == "__main__":
    if "--html-only" in sys.argv:
        write_empty_pages_html()
    else:
        kit_a()
        kit_b()
