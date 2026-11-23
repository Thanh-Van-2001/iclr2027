"""Independent human-validation kits for the AAMAS paper (submission 3154).

Nothing here changes the frozen parser, its run records, the reader labels,
the reference-set draw or any headline number. Everything is written under
audits/human_aamas/ and every draw below is seeded and recorded.

Kits (annotator-facing folders hold no machine reading of any kind):

  comparison_blind/   A.  blind re-reading of the 140 boxed reference comparisons,
                          with a seeded 100-item core (70 + 30 by stratum) and a
                          seeded 30-item double-annotation subset
  page_detection/     B.  every eligible single-bold group on 30 random pilot caption
                          pages (+20 random non-caption pages as a separate stratum)
  runcount_disputes/  C3. the 18 reference comparisons whose run count the
                          instruments dispute (parser vs either reader, or reader vs reader)
  bartype_random/     C4. a seeded random set of papers whose bars the parser read as
                          unlabelled, or whose bar kind the two readers disputed
  protocol_review/    C2. PDF links for the existing protocol_check.csv (model
                          suggestions visible there: a review/correction, not blind)
  empty_pages/        C1. the existing 35 hard-case pages; its sheet is rebuilt by
                          `python aamas/human_kits.py --html-only`
  machine_keys/       the sealed machine readings the scorer compares against

Usage
  python aamas/human_validation_kits.py build --analysis out/aamas/analysis.json
        draws + keys + sheets (deterministic; run once, outputs are committed).
        Without --analysis the existing keys are kept and only the
        annotator-facing files are rewritten.
  python aamas/human_validation_kits.py html        rewrite the label.html pages only
  python aamas/human_validation_kits.py check       every image present? every URL? leaks? (exit 1 if not)
  python aamas/human_validation_kits.py pack --kit comparison_blind --out DIR
        an annotator-only folder (+ .zip): sheet, images, blank template, instructions
  python aamas/human_validation_kits.py freeze --kit comparison_blind
        record the sha256 of every raw label file; the scorer refuses edited raw files
  python aamas/human_validation_kits.py adjudication-sheet --kit comparison_blind --a H1 --b H2
        a separate CSV listing every field the two annotators answered differently
  python aamas/human_validation_kits.py urls        refetch the public IFAAMAS indexes (network)
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import os
import platform
import random
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from human_kit_ui import form_kit_html, page_kit_html  # noqa: E402

KIT = os.path.join("audits", "human_aamas")
KEYS = os.path.join(KIT, "machine_keys")
VERSION = "aamas-hv-1"
SEEDS = {
    "core": 20261123,           # A: the 70 + 30 core draw from the boxed reference items
    "overlap": 20261124,        # A: the 21 + 9 double-annotation subset of the core
    "blind_order": 20261125,    # A: presentation order and blind ids
    "pages": 20261126,          # B: 30 of the 100 pilot caption pages
    "noncaption": 20261127,     # B: 20 of the 100 non-caption pages
    "page_overlap": 20261128,   # B: 8 of the 30 caption pages for a second annotator
    "runcount_order": 20261129,  # C3: presentation order
    "bartype": 20261130,        # C4: permutation of the pool's papers
}
SIZES = {"core_testable": 70, "core_no_bar": 30, "overlap_testable": 21, "overlap_no_bar": 9,
         "pages": 30, "noncaption": 20, "page_overlap": 8, "bartype_core_papers": 12}
ZOOM = 2.0   # every page and crop in these audits was rendered at fitz.Matrix(2.0, 2.0)

# keys and values of the machine records; none may appear in an annotator-facing
# file. Quoted key forms only where the bare word can occur in a paper title
# ("Pareto-guided Pipeline for ..." is one of the drawn pages).
FORBIDDEN = ("\"pipeline\"", "pipeline_test", "winner_dispersion", "runner_dispersion", "runner_up",
             "dispersion_kind", "n_runs_source", "\"testable\"", "no_bar", "\"stratum\"", "survives_",
             "reader1", "reader2", "census_reader", "pilot_reader", "orig_id", "why_in_pool", "disputed_by",
             "\"parser\"", "kind_used")
# phrases that would tell a C1 annotator what the readers said about the 35 pages
C1_FORBIDDEN = ("pilot_empty", "orientation_none", "no-single-winner", "readers disagree", "listed as empty",
                "census reader", "census_note", "parser_comparisons")


# ----------------------------------------------------------------- helpers
def _p(*parts):
    return os.path.join(ROOT, *parts)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(*parts):
    with open(_p(*parts), encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(obj, *parts):
    path = _p(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def write_text(text, *parts):
    path = _p(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read_csv(*parts):
    with open(_p(*parts), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(rows, cols, *parts):
    path = _p(*parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def copy_image(src_parts, dst_parts):
    src, dst = _p(*src_parts), _p(*dst_parts)
    if not os.path.exists(src):
        raise SystemExit(f"missing source image {os.path.relpath(src, ROOT)}: the kit cannot be built without it "
                         f"(it ships with the repository; nothing is re-rendered here)")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst) or sha256(src) != sha256(dst):
        shutil.copyfile(src, dst)


def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def paper_urls():
    path = _p(KIT, "paper_urls.json")
    if not os.path.exists(path):
        raise SystemExit("audits/human_aamas/paper_urls.json is missing; run `python aamas/human_validation_kits.py urls` "
                         "(reads the public IFAAMAS contents pages)")
    urls = load_json(KIT, "paper_urls.json")
    bad = [pid for pid, u in urls.items() if hashlib.sha1(u["pdf"].encode()).hexdigest()[:16] != pid]
    if bad:
        raise SystemExit(f"paper_urls.json: {len(bad)} ids do not hash to their URL (study/harvest.py sets "
                         f"id = sha1(pdf url)[:16]); first: {bad[:3]}")
    return urls


def pdf_link(urls, paper, page0):
    u = urls.get(paper)
    return (u["pdf"] + f"#page={page0 + 1}") if u else None


def local_pdf_hint(urls, paper):
    u = urls.get(paper)
    return f"data/corpus/AAMAS{u['year']}_{paper}.pdf" if u else None


def source_record(*parts):
    path = _p(*parts)
    return {"path": "/".join(parts), "sha256": sha256(path)} if os.path.exists(path) else {"path": "/".join(parts), "sha256": None}


def env_record():
    return {"python": platform.python_version(), "script": "aamas/human_validation_kits.py", "kit_version": VERSION}


# ----------------------------------------------------------------- A: blind comparisons
A_FIELDS = [
    {"name": "target_visible", "label": "Is exactly one cell outlined by a thin red box?", "kind": "select",
     "options": [["y", "yes"], ["n", "no: there is no box, or I cannot tell which cell it marks"]]},
    {"name": "results_table", "label": "Is the boxed cell part of a table of experimental results (measured numbers)?",
     "kind": "select", "options": [["y", "yes"], ["n", "no (hyperparameters, dataset statistics, pseudocode, ...)"], ["unclear", "unclear"]]},
    {"name": "bold_unique", "label": "Is the boxed cell printed in bold, and is it the ONLY bold cell in its comparison group?",
     "kind": "select", "options": [["y", "yes"], ["not_bold", "no: the boxed cell is not bold"],
                                   ["several_bold", "no: another cell in the same group is bold too"], ["unclear", "unclear"]],
     "help": "The group is the row or the column inside which the authors pick a winner (next question)."},
    {"name": "orientation", "label": "Along which line are methods compared for the boxed cell?", "kind": "select",
     "options": [["column", "column: methods are rows, compare down the column"],
                 ["row", "row: methods are columns, compare along the row"], ["unclear", "unclear"]]},
    {"name": "direction", "label": "For this metric, is higher or lower better?", "kind": "select",
     "options": [["higher", "higher is better"], ["lower", "lower is better"], ["unclear", "unclear"]],
     "help": "Use an arrow in the header, the caption, or the metric's meaning; say in the evidence box if you inferred it."},
    {"name": "winner_mean", "label": "Boxed cell: the mean exactly as printed", "kind": "text",
     "help": "Digits as printed (85.20, not 85.2; keep a % sign if printed). Not the ± part. 'unclear' if unreadable."},
    {"name": "winner_bar", "label": "Boxed cell: is an error bar printed with it (±, (x), subscript, [lo, hi])?", "kind": "select",
     "options": [["present", "present"], ["absent", "absent"], ["unclear", "unclear"]]},
    {"name": "winner_disp", "label": "Boxed cell: the error bar exactly as printed (number only)", "kind": "text",
     "req": {"if": ["winner_bar", ["present"]]}, "help": "0.3 for '85.2 ± 0.3'. For an interval [lo, hi] write lo;hi."},
    {"name": "runner_mean", "label": "Runner-up: the best NON-bold value in the same group (by the direction above)", "kind": "text",
     "help": "'none' if no other cell of the group holds a number; 'unclear' if unreadable. A tie between two non-bold cells: give the value and say so in the comment."},
    {"name": "runner_bar", "label": "Runner-up: is an error bar printed with it?", "kind": "select",
     "options": [["present", "present"], ["absent", "absent"], ["not_applicable", "there is no runner-up"], ["unclear", "unclear"]]},
    {"name": "runner_disp", "label": "Runner-up: the error bar exactly as printed (number only)", "kind": "text",
     "req": {"if": ["runner_bar", ["present"]]}},
    {"name": "rival_copied", "label": "Is the runner-up's number marked as taken from another paper (citation, dagger, star, 'reported in', 'from')?",
     "kind": "select", "options": [["n", "no"], ["y", "yes"], ["unclear", "unclear"]]},
    {"name": "disp_type", "label": "What does the error bar of this table mean, according to the paper?", "kind": "select",
     "options": [["sd", "standard deviation"], ["se", "standard error"], ["ci", "confidence interval"],
                 ["unlabelled", "printed, but the paper never says what it is"],
                 ["other", "something else (min/max, IQR, ...): say which in the comment"],
                 ["absent", "no error bar on these cells"], ["unclear", "unclear, or the paper says two different things"]]},
    {"name": "disp_source", "label": "Where did you find what the error bar means?", "kind": "select",
     "options": [["caption", "the table's caption"], ["table", "the table header or a footnote"], ["page", "text on the same page"],
                 ["elsewhere", "elsewhere in the paper (methods, appendix)"], ["absent", "nowhere: not stated"],
                 ["not_applicable", "no error bars"]]},
    {"name": "n_runs", "label": "Over how many independent runs (seeds, trials, repetitions) are this table's numbers averaged?", "kind": "text",
     "help": "An integer; 'none' if the paper never states it for this table; 'unclear' if you cannot decide. Search the whole PDF for seed, run, trial, repeat, independent, average."},
    {"name": "n_runs_other", "label": "Other counts the paper states that might apply (optional)", "kind": "text", "req": "never",
     "help": "e.g. '5 (Sec. 5.1, training seeds); 100 (evaluation episodes)'."},
    {"name": "n_source", "label": "Where is the run count you entered stated?", "kind": "select",
     "options": [["caption", "the table's caption"], ["page", "text on the same page"], ["elsewhere", "elsewhere in the paper"],
                 ["absent", "not stated (run count = none)"], ["ambiguous", "several different counts could apply"]]},
    {"name": "paper_opened", "label": "Did you open the full paper to check the error bar meaning and the run count?", "kind": "select",
     "options": [["y", "yes"], ["n", "no"]]},
    {"name": "evidence", "label": "Evidence: page/section and a short quote for the error bar meaning and the run count", "kind": "area",
     "help": "e.g. 'p.7 Sec 5.1: \"averaged over 5 seeds; shaded/± is one std\"'. If nothing is stated: 'searched seed/run/trial/std: not stated'."},
    {"name": "confidence", "label": "Your confidence in this item", "kind": "select",
     "options": [["high", "high"], ["medium", "medium"], ["low", "low"]]},
    {"name": "comment", "label": "Comment (ties, odd layout, anything you were unsure about)", "kind": "area", "req": "never"},
]
A_GATES = [{"field": "target_visible", "skip": ["n"]}, {"field": "results_table", "skip": ["n"]}]

A_INTRO = """
<h3>What you are doing</h3>
Each item is a crop of a results table from an AAMAS paper with one cell outlined by a thin <b>red box</b>.
Read the table and the paper and answer the questions on the right. Nothing on this page tells you what any
program or model read from the table: the answers must come from the table and the paper alone.
<h3>How</h3>
<ol>
<li>Enter your annotator ID at the top (the ID you were given; never a name). Answers autosave in this browser under that ID.</li>
<li>Read the crop. Click it to zoom. If the crop is not enough (caption cut off, header missing), use <b>Open the full paper</b>: it opens the public PDF at the right page.</li>
<li>For the error-bar meaning and the run count, <b>always open the full paper</b> and search it (Ctrl+F: seed, run, trial, repeat, std, standard error, confidence). Do not decide them from the crop.</li>
<li>The <b>runner-up</b> is the best value among the non-bold cells of the same group, in the direction you chose (highest if higher is better).</li>
<li>Write <code>unclear</code> (or pick <i>unclear</i>) whenever you cannot tell; never guess. <code>none</code> means the paper does not state it.</li>
<li><b>Enter</b> moves to the next question, <b>Ctrl+Enter</b> saves and moves to the next item, <b>Alt+&larr;/&rarr;</b> moves between items.</li>
<li>When you stop, press <b>Export CSV</b> and send the file unchanged. To continue on another computer, use <b>Resume from CSV</b>.</li>
</ol>
Start with the item set <b>Core 100</b>. A second annotator only does the set <b>Double-annotation 30</b>.
Do not open any other file of the project while labelling.
"""


def _comparison_items(urls):
    items = load_json("audits", "aamas_gold", "items.json")
    by_id = {it["id"]: it for it in items}
    boxed = {s: sorted(i for i, it in by_id.items() if it["stratum"] == s and it.get("mark")) for s in ("testable", "no_bar")}
    rng = random.Random(SEEDS["core"])
    core_t = sorted(rng.sample(boxed["testable"], SIZES["core_testable"]))
    core_b = sorted(rng.sample(boxed["no_bar"], SIZES["core_no_bar"]))
    rng = random.Random(SEEDS["overlap"])
    ov = sorted(rng.sample(core_t, SIZES["overlap_testable"])) + sorted(rng.sample(core_b, SIZES["overlap_no_bar"]))
    core = core_t + core_b
    optional = sorted(set(by_id) - set(core))
    rng = random.Random(SEEDS["blind_order"])
    core_order, opt_order = core[:], optional[:]
    rng.shuffle(core_order)
    rng.shuffle(opt_order)
    blind = {orig: f"B{k:03d}" for k, orig in enumerate(core_order + opt_order, 1)}
    return by_id, boxed, core_t, core_b, ov, optional, blind


def build_comparison(urls, write_keys=True):
    by_id, boxed, core_t, core_b, ov, optional, blind = _comparison_items(urls)
    d = os.path.join(KIT, "comparison_blind")
    items, key = [], {}
    for orig, bid in sorted(blind.items(), key=lambda kv: kv[1]):
        it = by_id[orig]
        sets = (["core"] + (["overlap"] if orig in ov else [])) if orig in core_t + core_b else ["optional"]
        copy_image(("audits", "aamas_gold", "img", it["image"]), (d, "images", f"{bid}.png"))
        link = pdf_link(urls, it["paper"], it["page"])
        items.append({"id": bid, "sets": sets, "paper_title": it.get("title", ""), "table": it["table"],
                      "pdf_page": it["page"] + 1, "pdf_url": link, "local_pdf": local_pdf_hint(urls, it["paper"]),
                      "image": f"images/{bid}.png"})
        key[bid] = {"orig_id": orig, "stratum": it["stratum"], "paper": it["paper"], "table": it["table"],
                    "page": it["page"], "boxed": it.get("mark") is not None, "in_core": orig in core_t + core_b,
                    "in_overlap": orig in ov}
    dump_json(items, d, "items.json")
    cols = ["id", "annotator_id", "kit", "kit_version"] + [f["name"] for f in A_FIELDS] + \
           ["complete", "first_opened_at", "last_saved_at", "seconds_on_item"]
    write_csv([{"id": it["id"]} for it in items], cols, d, "labels_template.csv")
    os.makedirs(_p(d, "raw"), exist_ok=True)
    manifest = {
        "kit": "comparison_blind", **env_record(), "seeds": {k: SEEDS[k] for k in ("core", "overlap", "blind_order")},
        "frame": "the 140 reference comparisons of audits/aamas_gold (100 drawn from the parser's testable "
                 "comparisons, 40 from its bar-less ones, after the parser was frozen)",
        "draw": {"core": f"{SIZES['core_testable']} of the {len(boxed['testable'])} boxed testable items and "
                         f"{SIZES['core_no_bar']} of the {len(boxed['no_bar'])} boxed bar-less items, simple random "
                         f"samples without replacement (random.Random(seed).sample on the sorted ids)",
                 "overlap": f"{SIZES['overlap_testable']} + {SIZES['overlap_no_bar']} of the core, same rule, for a second annotator",
                 "optional": f"the other {len(optional)} items, including the {sum(1 for i in by_id.values() if not i.get('mark'))} "
                             f"the paper's kit rendered without a box (their answers are void, as in the paper)",
                 "blind_ids": "core first then optional, each shuffled with blind_order; ids B001-B140 carry no stratum"},
        "counts": {"items": len(items), "core": len(core_t) + len(core_b), "overlap": len(ov), "optional": len(optional)},
        "sampling_fractions": {"testable": f"{SIZES['core_testable']}/{len(boxed['testable'])}",
                               "no_bar": f"{SIZES['core_no_bar']}/{len(boxed['no_bar'])}"},
        "report_by_stratum": "the testable stratum is deliberately oversampled relative to the corpus; never pool the two strata",
        "hidden_from_annotators": ["parser values and verdicts", "both readers' labels", "the stratum of each item",
                                   "the run sentences (only shipped for one stratum, so showing them would reveal it)"],
        "sources": [source_record("audits", "aamas_gold", "items.json")],
    }
    dump_json(manifest, d, "manifest.json")
    if write_keys:
        r1 = {r["id"]: r for r in read_csv("audits", "aamas_gold", "labels.csv")}
        r2 = {r["id"]: r for r in read_csv("audits", "aamas_gold_gemini", "labels.csv")}
        for bid, k in key.items():
            it = by_id[k["orig_id"]]
            k["parser"] = it["pipeline"]
            k["parser_test_frozen"] = it.get("pipeline_test")
            k["reader1"] = {c: v for c, v in r1[k["orig_id"]].items() if c not in ("id", "stratum")}
            k["reader2"] = {c: v for c, v in r2[k["orig_id"]].items() if c not in ("id", "stratum")}
        dump_json({"kit": "comparison_blind", **env_record(), "seeds": manifest["seeds"],
                   "sources": [source_record("audits", "aamas_gold", "items.json"),
                               source_record("audits", "aamas_gold", "labels.csv"),
                               source_record("audits", "aamas_gold_gemini", "labels.csv")],
                   "items": key}, KEYS, "comparison_key.json")
    return items


def html_comparison():
    d = os.path.join(KIT, "comparison_blind")
    items = load_json(d, "items.json")
    view = []
    for it in items:
        links = []
        if it.get("pdf_url"):
            links.append({"label": f"Open the full paper at PDF page {it['pdf_page']}", "href": it["pdf_url"]})
        links.append({"label": "Open the crop in a new tab", "href": it["image"]})
        view.append({"id": it["id"], "sets": it["sets"], "image": it["image"],
                     "meta": [f"Paper: {it['paper_title']}", f"Table {it['table']}, PDF page {it['pdf_page']}",
                              f"Local copy, if you have the corpus: {it['local_pdf']}" if it.get("local_pdf") else ""],
                     "links": links})
    html = form_kit_html(kit="comparison_blind", version=VERSION, title="AAMAS boxed comparisons (blind)",
                         intro_html=A_INTRO, items=view, fields=A_FIELDS, gates=A_GATES,
                         sets={"core": "Core 100 (do these first)", "overlap": "Double-annotation 30",
                               "optional": "Optional 40", "all": "All 140"},
                         default_set="core", export_name="comparison_blind_{annotator}.csv")
    write_text(html, d, "label.html")


# ----------------------------------------------------------------- B: page-level detection
B_INTRO = """
<h3>What you are doing</h3>
Each item is one whole page of an AAMAS paper, drawn at random. List <b>every table</b> on the page and, in every
results table, <b>every group that has exactly one bold cell</b>. A page can have none: say so explicitly.
<h3>Definitions</h3>
<ul>
<li><b>Results table</b>: a table of measured outcomes (scores, rewards, errors, times) of methods or settings. Not hyperparameters, dataset statistics, notation or pseudocode.</li>
<li><b>Orientation</b>: <i>column</i> if the methods are rows and you compare down a column; <i>row</i> if the methods are columns.</li>
<li><b>Group</b>: one column (column orientation) or one row (row orientation) of numbers in which methods are compared. If the table is split into blocks by rules, each block's column is a separate group.</li>
<li><b>Eligible group</b>: exactly one bold cell, at least one non-bold number, and the bold number is <i>strictly</i> the best in the direction the metric is read (choose <i>tie</i> or <i>no</i> otherwise). List the other single-bold groups too, with the right answer in <i>Bold is best?</i></li>
<li><b>Bold rule</b>: if the caption says bold marks something other than the single best (top-3, significance, the authors' method), pick that option.</li>
</ul>
<h3>How</h3>
<ol>
<li>Enter your annotator ID. Answers autosave in this browser under that ID.</li>
<li>Add each table (<b>+ Add table</b>), then each group (<b>+ Add group</b>). With a group selected, <b>click its bold cell on the page</b> to record where it is.</li>
<li>Type the bold value exactly as printed (85.20, keep %). The group label is the row or column header (e.g. "Hopper", "Acc. (%)").</li>
<li>Set the page status last. A page with no eligible group needs <i>This page has NO eligible group</i>, and a short note on what is there.</li>
<li>Use <b>Open the full paper</b> when the page image is unclear. Export the CSV when you stop; resume with <b>Resume from CSV</b>.</li>
</ol>
"""


def _page_draw():
    pil = load_json("audits", "aamas_pages", "items.json")
    nc = load_json("audits", "aamas_noncaption", "items.json")
    rng = random.Random(SEEDS["pages"])
    draw = rng.sample(sorted(it["id"] for it in pil), SIZES["pages"])
    rng = random.Random(SEEDS["noncaption"])
    draw_nc = rng.sample(sorted(it["id"] for it in nc), SIZES["noncaption"])
    rng = random.Random(SEEDS["page_overlap"])
    ov = sorted(rng.sample(draw, SIZES["page_overlap"]))
    return {it["id"]: it for it in pil}, {it["id"]: it for it in nc}, draw, draw_nc, ov


def _parser_on_page(cmps, paper, page):
    out = []
    for c in cmps:
        if c["paper"] == paper and c["page"] == page:
            t = c.get("test")
            out.append({"table": c["table"], "orientation": c.get("orientation"), "direction": c.get("direction"),
                        "winner": c["winner"], "runner_up": c["runner_up"],
                        "winner_dispersion": c["winner_dispersion"], "runner_dispersion": c["runner_dispersion"],
                        "dispersion_kind": c.get("dispersion_kind"), "n_runs": c.get("n_runs"),
                        "winner_cell": c.get("winner_cell"), "runner_cell": c.get("runner_cell"),
                        "testable": bool(t), "p": t["p"] if t else None,
                        "caption": (c.get("caption") or "")[:160]})
    return out


def _reader_tables(lab):
    """A reader's page labels as the scorer needs them: tables with their groups."""
    if lab is None:
        return None
    return [{"caption_start": (t.get("caption_start") or "")[:160], "results_table": t.get("results_table"),
             "orientation": t.get("orientation"), "bar_kind": t.get("bar_kind"), "n_runs": t.get("n_runs"),
             "groups": t.get("groups", [])} for t in lab.get("tables", [])]


def build_pages(urls, analysis_path=None):
    pil, nc, draw, draw_nc, ov = _page_draw()
    d = os.path.join(KIT, "page_detection")
    hard = {(r["paper"], r["page"]): r["id"] for r in load_json(KIT, "empty_pages", "items.json")}
    items, key = [], {}
    order = [("caption_pilot", i) for i in draw] + [("noncaption", i) for i in draw_nc]
    for k, (frame, sid) in enumerate(order, 1):
        pid = f"P{k:02d}"
        src = pil[sid] if frame == "caption_pilot" else nc[sid]
        kit_dir = "aamas_pages" if frame == "caption_pilot" else "aamas_noncaption"
        copy_image(("audits", kit_dir, "img", f"{sid}_page.png"), (d, "images", f"{pid}.png"))
        w, h = png_size(_p(d, "images", f"{pid}.png"))
        sets = (["core"] + (["overlap"] if sid in ov else [])) if frame == "caption_pilot" else ["extra"]
        items.append({"id": pid, "sets": sets, "paper_title": src["title"], "pdf_page": src["page"] + 1,
                      "pdf_url": pdf_link(urls, src["paper"], src["page"]), "local_pdf": local_pdf_hint(urls, src["paper"]),
                      "image": f"images/{pid}.png", "width": w, "height": h})
        key[pid] = {"frame": frame, "source_kit": f"audits/{kit_dir}", "source_id": sid, "paper": src["paper"],
                    "page": src["page"], "zoom": ZOOM, "width": w, "height": h, "in_overlap": sid in ov,
                    "caption_pages_in_paper": src.get("n_caption_pages", src.get("paper_caption_pages")),
                    "also_in_hard_case_kit": hard.get((src["paper"], src["page"]))}
    dump_json(items, d, "items.json")
    cols = ["row_type", "page_id", "annotator_id", "kit", "kit_version", "page_status", "page_note", "table_key", "table_ref",
            "table_caption", "results_table", "orientation", "bold_rule", "group_key", "group_table_key", "group_label",
            "winner_value", "bold_is_best", "x_px", "y_px", "group_note", "complete", "first_opened_at", "last_saved_at",
            "seconds_on_page"]
    write_csv([{"row_type": "page", "page_id": it["id"]} for it in items], cols, d, "groups_template.csv")
    os.makedirs(_p(d, "raw"), exist_ok=True)
    n_cap = len(pil)
    manifest = {
        "kit": "page_detection", **env_record(),
        "seeds": {k: SEEDS[k] for k in ("pages", "noncaption", "page_overlap")},
        "frames": {
            "caption_pilot": f"the {n_cap} pilot pages of audits/aamas_pages, drawn by study/sample_pages.py: papers in a "
                             f"seeded random order, one page drawn uniformly among each paper's pages (of the first 40) "
                             f"holding a 'Table N:' caption line; one page per paper, so page = paper cluster",
            "noncaption": "the 100 pages of audits/aamas_noncaption: random pages after the first and before the references "
                          "on which the parser detected no caption (pool 5612 pages, 827 papers; draw.json)",
        },
        "draw": {"caption_pilot": f"{SIZES['pages']} of {n_cap}, simple random sample without replacement "
                                  "(random.Random(seed).sample on the sorted ids); the 35 hard-case pages were NOT used to "
                                  "select or exclude anything, and a drawn page that is also a hard-case page is kept and flagged",
                 "noncaption": f"{SIZES['noncaption']} of 100, same rule; a separate stratum, scored separately",
                 "overlap": f"{SIZES['page_overlap']} of the {SIZES['pages']} caption pages for a second annotator"},
        "estimands": {"unweighted": "a random caption page of a random paper (the pilot's own design)",
                      "weighted": "all caption pages: each page weighted by its paper's number of caption pages "
                                  "(the inverse of its within-paper selection probability)"},
        "ids": "P01-P30 caption pages (set 'core'), P31-P50 non-caption pages (set 'extra'); ids carry no machine reading",
        "counts": {"caption_pilot": len(draw), "noncaption": len(draw_nc), "overlap": len(ov),
                   "drawn_pages_also_in_hard_case_kit": sum(1 for v in key.values() if v["also_in_hard_case_kit"])},
        "sources": [source_record("audits", "aamas_pages", "items.json"), source_record("audits", "aamas_noncaption", "items.json")],
    }
    dump_json(manifest, d, "manifest.json")
    if analysis_path:
        cmps = json.load(open(analysis_path, encoding="utf-8"))["_comparisons"]
        cz_items = {(it["paper"], it["page"]): it["id"] for it in load_json("audits", "aamas_census", "items.json")}
        cz = {p["id"]: p for p in load_json("audits", "aamas_census", "labels.json")}
        r1 = {p["id"]: p for p in load_json("audits", "aamas_pages", "labels.json")}
        rn = {p["id"]: p for p in load_json("audits", "aamas_noncaption", "labels.json")}
        for pid, k in key.items():
            k["parser"] = _parser_on_page(cmps, k["paper"], k["page"])
            cid = cz_items.get((k["paper"], k["page"]))
            k["census_reader"] = {"in_census_frame": cid is not None, "census_id": cid,
                                  "tables": _reader_tables(cz.get(cid)) if cid else None}
            if k["frame"] == "caption_pilot":
                k["pilot_reader"] = {"tables": _reader_tables(r1.get(k["source_id"]))}
            else:
                k["noncaption_reader"] = {"tables": _reader_tables(rn.get(k["source_id"]))}
        dump_json({"kit": "page_detection", **env_record(), "seeds": manifest["seeds"],
                   "sources": [{"path": "out/aamas/analysis.json (the frozen run record)", "sha256": sha256(analysis_path)},
                               source_record("audits", "aamas_census", "items.json"),
                               source_record("audits", "aamas_census", "labels.json"),
                               source_record("audits", "aamas_pages", "labels.json"),
                               source_record("audits", "aamas_noncaption", "labels.json")],
                   "pages": key}, KEYS, "page_key.json")
    return items


def html_pages():
    d = os.path.join(KIT, "page_detection")
    items = load_json(d, "items.json")
    view = [{"id": it["id"], "sets": it["sets"], "image": it["image"], "width": it["width"], "height": it["height"],
             "meta": [f"Paper: {it['paper_title']}", f"PDF page {it['pdf_page']}"],
             "links": ([{"label": f"Open the full paper at PDF page {it['pdf_page']}", "href": it["pdf_url"]}] if it.get("pdf_url") else [])
             + [{"label": "Open the page image in a new tab", "href": it["image"]}]} for it in items]
    html = page_kit_html(kit="page_detection", version=VERSION, title="AAMAS pages: every single-bold group",
                         intro_html=B_INTRO, items=view,
                         sets={"core": "Set 1: 30 pages (do first)", "overlap": "Double-annotation 8",
                               "extra": "Set 2: 20 pages", "all": "All 50"},
                         default_set="core", export_name="page_detection_{annotator}.csv")
    write_text(html, d, "label.html")


# ----------------------------------------------------------------- C3: disputed run counts
C3_FIELDS = [
    {"name": "n_runs", "label": "Over how many independent runs are the numbers of this table averaged?", "kind": "text",
     "help": "An integer; 'none' if the paper never states it; 'unclear' if you cannot decide between counts."},
    {"name": "n_unit", "label": "What does that count count?", "kind": "select",
     "options": [["seeds", "random seeds / independent training runs"], ["episodes", "evaluation episodes / rollouts / games"],
                 ["instances", "problem instances / scenarios / datasets"], ["folds", "cross-validation folds"],
                 ["repetitions", "repetitions of the whole experiment"], ["other", "other (comment)"], ["none", "no count"]]},
    {"name": "applies_to_table", "label": "Does the statement apply to THIS table?", "kind": "select",
     "options": [["explicit", "yes: it names this table or its experiment"], ["paper_wide", "probably: a paper-wide statement"],
                 ["no", "no: it belongs to another experiment"], ["unclear", "unclear"]]},
    {"name": "n_source", "label": "Where is it stated?", "kind": "select",
     "options": [["caption", "the table's caption"], ["page", "text on the same page"], ["elsewhere", "elsewhere in the paper"],
                 ["absent", "nowhere"], ["ambiguous", "several different counts could apply"]]},
    {"name": "other_counts", "label": "Other counts the paper states that a reader might take for this table (optional)",
     "kind": "text", "req": "never"},
    {"name": "passage", "label": "The passage that settles it, quoted (as short as possible)", "kind": "area",
     "help": "If nothing is stated: 'searched seed/run/trial/repeat/independent/average: not stated'."},
    {"name": "passage_location", "label": "Where the passage is (PDF page, section, caption/footnote)", "kind": "text"},
    {"name": "confidence", "label": "Your confidence", "kind": "select", "options": [["high", "high"], ["medium", "medium"], ["low", "low"]]},
    {"name": "comment", "label": "Comment", "kind": "area", "req": "never"},
]
C3_INTRO = """
<h3>What you are doing</h3>
For each boxed table cell, find in the <b>full paper</b> how many independent runs the table's numbers average over,
and quote the passage that settles it. The grey box under the image lists sentences a search pattern pulled out of the
paper (mentions of seeds, runs, trials, episodes); it is only a search aid, may be incomplete, and is not anyone's answer.
Always check the PDF. Enter your annotator ID first; answers autosave; export the CSV when you stop.
"""


def runcount_disputed_ids():
    """The reference comparisons whose run count the instruments dispute.

    Testable, boxed items where at least one of three pairs disagrees on the
    run count (parser vs first reader, parser vs second reader, first reader
    vs second reader), each pair compared only when both sides gave a
    readable answer (study/gold_set.py: _num/_match/_unclear) and, for a
    reader, only when it called the region a results table. This reproduces
    the 15 + 11 + 9 pairwise disagreements and their union of 18.
    """
    sys.path.insert(0, _p("study"))
    from gold_set import _match, _num, _unclear  # noqa: E402
    items = {it["id"]: it for it in load_json("audits", "aamas_gold", "items.json")}
    r1 = {r["id"]: r for r in read_csv("audits", "aamas_gold", "labels.csv")}
    r2 = {r["id"]: r for r in read_csv("audits", "aamas_gold_gemini", "labels.csv")}
    pairs = {"reader1_vs_parser": [], "reader2_vs_parser": [], "reader1_vs_reader2": []}
    for i, it in items.items():
        if it["stratum"] != "testable" or not it.get("mark"):
            continue
        p = it["pipeline"]["n_runs"]
        a, b = r1[i]["n_runs"], r2[i]["n_runs"]
        if r1[i]["results_table"].lower().startswith("y") and not _unclear(a) and not _match(_num(a), p):
            pairs["reader1_vs_parser"].append(i)
        if r2[i]["results_table"].lower().startswith("y") and not _unclear(b) and not _match(_num(b), p):
            pairs["reader2_vs_parser"].append(i)
        if not _unclear(a) and not _unclear(b) and (a.strip() or b.strip()) and not _match(_num(a), _num(b)):
            pairs["reader1_vs_reader2"].append(i)
    union = sorted(set().union(*pairs.values()))
    return union, pairs, items, r1, r2


def build_runcount(urls, write_keys=True):
    union, pairs, items, r1, r2 = runcount_disputed_ids()
    if len(union) != 18:
        print(f"note: the disputed-run-count rule yields {len(union)} items, not the 18 the reviews cite; "
              f"the kit uses the rule's output and the manifest records it")
    order = union[:]
    random.Random(SEEDS["runcount_order"]).shuffle(order)
    d = os.path.join(KIT, "runcount_disputes")
    out, key = [], {}
    for k, orig in enumerate(order, 1):
        rid = f"R{k:02d}"
        it = items[orig]
        copy_image(("audits", "aamas_gold", "img", it["image"]), (d, "images", f"{rid}.png"))
        runs_path = _p("audits", "aamas_gold", "img", f"{orig}_runs.txt")
        runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else ""
        out.append({"id": rid, "sets": ["all"], "paper_title": it.get("title", ""), "table": it["table"],
                    "pdf_page": it["page"] + 1, "pdf_url": pdf_link(urls, it["paper"], it["page"]),
                    "local_pdf": local_pdf_hint(urls, it["paper"]), "image": f"images/{rid}.png", "search_aid": runs})
        key[rid] = {"orig_id": orig, "paper": it["paper"], "table": it["table"], "page": it["page"],
                    "disputed_by": [name for name, ids in pairs.items() if orig in ids],
                    "parser": {"n_runs": it["pipeline"]["n_runs"], "n_runs_source": it["pipeline"]["n_runs_source"]},
                    "reader1": {f: r1[orig][f] for f in ("n_runs", "n_source", "note")},
                    "reader2": {f: r2[orig][f] for f in ("n_runs", "n_source", "note")}}
    dump_json(out, d, "items.json")
    cols = ["id", "annotator_id", "kit", "kit_version"] + [f["name"] for f in C3_FIELDS] + \
           ["complete", "first_opened_at", "last_saved_at", "seconds_on_item"]
    write_csv([{"id": it["id"]} for it in out], cols, d, "labels_template.csv")
    os.makedirs(_p(d, "raw"), exist_ok=True)
    dump_json({"kit": "runcount_disputes", **env_record(), "seeds": {"runcount_order": SEEDS["runcount_order"]},
               "rule": runcount_disputed_ids.__doc__.strip(),
               "pairwise_counts": {k: len(v) for k, v in pairs.items()}, "union": len(union),
               "join": "exact, on the reference item id shared by audits/aamas_gold/items.json, labels.csv and "
                       "audits/aamas_gold_gemini/labels.csv; no fuzzy matching",
               "hidden_from_annotators": ["the parser's run count and source", "both readers' run counts and notes",
                                          "which instruments disagree"],
               "sources": [source_record("audits", "aamas_gold", "items.json"),
                           source_record("audits", "aamas_gold", "labels.csv"),
                           source_record("audits", "aamas_gold_gemini", "labels.csv")]}, d, "manifest.json")
    if write_keys:
        dump_json({"kit": "runcount_disputes", **env_record(), "items": key}, KEYS, "runcount_key.json")
    return out


def html_runcount():
    d = os.path.join(KIT, "runcount_disputes")
    items = load_json(d, "items.json")
    view = [{"id": it["id"], "sets": it["sets"], "image": it["image"],
             "meta": [f"Paper: {it['paper_title']}", f"Table {it['table']}, PDF page {it['pdf_page']}",
                      f"Local copy, if you have the corpus: {it['local_pdf']}" if it.get("local_pdf") else ""],
             "links": ([{"label": f"Open the full paper at PDF page {it['pdf_page']}", "href": it["pdf_url"]}] if it.get("pdf_url") else []),
             "context": it.get("search_aid") or "", "context_title": "Search aid: sentences a pattern pulled from the paper (not an answer; check the PDF)"}
            for it in items]
    html = form_kit_html(kit="runcount_disputes", version=VERSION, title="AAMAS run counts from the full paper",
                         intro_html=C3_INTRO, items=view, fields=C3_FIELDS, gates=[],
                         sets={"all": "All items"}, default_set="all", export_name="runcount_disputes_{annotator}.csv")
    write_text(html, d, "label.html")


# ----------------------------------------------------------------- C4: bar-type random set
C4_FIELDS = [
    {"name": "table_found", "label": "Did you find this table on (or next to) the stated PDF page?", "kind": "select",
     "options": [["y", "yes"], ["n", "no"]]},
    {"name": "has_bars", "label": "Does the table print error bars (±, parentheses, subscripts, intervals)?", "kind": "select",
     "options": [["y", "yes"], ["n", "no"], ["unclear", "unclear"]]},
    {"name": "bar_kind", "label": "What do the error bars mean, according to the paper?", "kind": "select",
     "options": [["sd", "standard deviation"], ["se", "standard error of the mean"], ["ci", "confidence interval"],
                 ["range", "min-max range"], ["iqr", "interquartile range / percentiles"], ["other", "other (comment)"],
                 ["not_stated", "the paper never says"], ["conflicting", "the paper says two different things"]]},
    {"name": "stated_where", "label": "Where is it stated?", "kind": "select",
     "options": [["caption", "the table's caption"], ["table", "table header or footnote"], ["page", "text on the same page"],
                 ["methods", "experimental setup / methods section"], ["appendix", "appendix"],
                 ["elsewhere", "elsewhere"], ["not_stated", "nowhere"]]},
    {"name": "passage", "label": "The passage that settles it, quoted (as short as possible)", "kind": "area",
     "help": "If nothing is stated: 'searched std/standard deviation/standard error/confidence/±: not stated'."},
    {"name": "passage_location", "label": "Where the passage is (PDF page, section)", "kind": "text"},
    {"name": "n_runs", "label": "Run count for this table, if you saw it (optional)", "kind": "text", "req": "never"},
    {"name": "confidence", "label": "Your confidence", "kind": "select", "options": [["high", "high"], ["medium", "medium"], ["low", "low"]]},
    {"name": "comment", "label": "Comment", "kind": "area", "req": "never"},
]
C4_GATES = [{"field": "table_found", "skip": ["n"]}]
C4_INTRO = """
<h3>What you are doing</h3>
Each item names one table of one AAMAS paper. Open the <b>full paper</b>, find the table, and read the whole
experimental-methodology part (setup, captions, footnotes, appendix) to decide what its error bars mean.
Quote the shortest passage that settles it. If nothing in the paper says, answer <i>the paper never says</i>
and record what you searched for. Enter your annotator ID first; answers autosave; export the CSV when you stop.
"""


def bartype_pool(cmps):
    """The pool: tables (paper, table, page) on which the frozen parser read an
    error bar on both sides of at least one comparison and found no statement
    of what the bar is (dispersion_kind 'unknown', read as a deviation by the
    paper's convention), plus the reference-set tables whose bar kind the two
    readers labelled differently. The unit drawn is the paper, because the
    whole PDF's methodology is what decides; every pool table of a drawn
    paper is checked."""
    tables = {}
    for c in cmps:
        if c.get("dispersion_kind") == "unknown" and c["winner_dispersion"] is not None and c["runner_dispersion"] is not None:
            tables.setdefault((c["paper"], str(c["table"]), c["page"]), set()).add("parser_unlabelled")
    items = {it["id"]: it for it in load_json("audits", "aamas_gold", "items.json")}
    r1 = {r["id"]: r for r in read_csv("audits", "aamas_gold", "labels.csv")}
    r2 = {r["id"]: r for r in read_csv("audits", "aamas_gold_gemini", "labels.csv")}
    km = {"sd": "std", "se": "sem", "ci": "ci", "unlabelled": "unknown", "unknown": "unknown"}
    for i, it in items.items():
        a, b = r1[i]["disp_type"].strip().lower(), r2[i]["disp_type"].strip().lower()
        if it["stratum"] == "testable" and it.get("mark") and a and b and km.get(a, a) != km.get(b, b):
            tables.setdefault((it["paper"], str(it["table"]), it["page"]), set()).add("readers_disagree")
    return tables


def build_bartype(urls, analysis_path):
    cmps = json.load(open(analysis_path, encoding="utf-8"))["_comparisons"]
    pool = bartype_pool(cmps)
    papers = sorted({p for p, _, _ in pool})
    perm = papers[:]
    random.Random(SEEDS["bartype"]).shuffle(perm)
    core = perm[:SIZES["bartype_core_papers"]]
    d = os.path.join(KIT, "bartype_random")
    out, key = [], {}
    k = 0
    for rank, paper in enumerate(perm, 1):
        for (pp, table, page) in sorted(t for t in pool if t[0] == paper):
            k += 1
            tid = f"T{k:02d}"
            sets = ["core"] if paper in core else ["reserve"]
            u = urls.get(paper, {})
            out.append({"id": tid, "sets": sets, "paper_rank": rank, "paper_title": u.get("title", ""),
                        "table": table, "pdf_page": page + 1, "pdf_url": pdf_link(urls, paper, page),
                        "local_pdf": local_pdf_hint(urls, paper), "image": None})
            tc = [c for c in cmps if c["paper"] == paper and str(c["table"]) == table and c["page"] == page]
            key[tid] = {"paper": paper, "table": table, "page": page, "paper_rank": rank, "in_core": paper in core,
                        "why_in_pool": sorted(pool[(pp, table, page)]),
                        "parser": [{"winner": c["winner"], "runner_up": c["runner_up"],
                                    "winner_dispersion": c["winner_dispersion"], "runner_dispersion": c["runner_dispersion"],
                                    "dispersion_kind": c.get("dispersion_kind"), "n_runs": c.get("n_runs"),
                                    "n_runs_source": c.get("n_runs_source"), "testable": bool(c.get("test")),
                                    "p": c["test"]["p"] if c.get("test") else None} for c in tc]}
    dump_json(out, d, "items.json")
    cols = ["id", "annotator_id", "kit", "kit_version"] + [f["name"] for f in C4_FIELDS] + \
           ["complete", "first_opened_at", "last_saved_at", "seconds_on_item"]
    write_csv([{"id": it["id"]} for it in out], cols, d, "labels_template.csv")
    os.makedirs(_p(d, "raw"), exist_ok=True)
    dump_json({"kit": "bartype_random", **env_record(), "seeds": {"bartype": SEEDS["bartype"]},
               "pool_rule": bartype_pool.__doc__.strip(),
               "pool": {"tables": len(pool), "papers": len(papers),
                        "by_reason": {r: sum(1 for v in pool.values() if r in v) for r in ("parser_unlabelled", "readers_disagree")}},
               "draw": f"the pool's papers in a seeded random order (random.Random(seed).shuffle of the sorted ids); the first "
                       f"{SIZES['bartype_core_papers']} papers are the core sample and every later paper is a reserve to be "
                       f"taken strictly in order, so any prefix is a simple random sample of papers",
               "counts": {"core_papers": len(core), "core_tables": sum(1 for it in out if "core" in it["sets"]),
                          "reserve_papers": len(perm) - len(core), "reserve_tables": sum(1 for it in out if "reserve" in it["sets"])},
               "images": "none shipped: these tables are checked in the public PDF (link) or data/corpus",
               "hidden_from_annotators": ["parser values, run counts and verdicts", "the reason each table is in the pool"],
               "sources": [{"path": "out/aamas/analysis.json (the frozen run record)", "sha256": sha256(analysis_path)},
                           source_record("audits", "aamas_gold", "labels.csv"),
                           source_record("audits", "aamas_gold_gemini", "labels.csv")]}, d, "manifest.json")
    dump_json({"kit": "bartype_random", **env_record(), "items": key}, KEYS, "bartype_key.json")
    return out


def html_bartype():
    d = os.path.join(KIT, "bartype_random")
    if not os.path.exists(_p(d, "items.json")):
        return
    items = load_json(d, "items.json")
    view = [{"id": it["id"], "sets": it["sets"], "image": None,
             "image_note": "No image is shipped for this kit: the decision needs the whole paper.",
             "meta": [f"Paper: {it['paper_title']}", f"Table {it['table']}, PDF page {it['pdf_page']}",
                      f"Local copy, if you have the corpus: {it['local_pdf']}" if it.get("local_pdf") else ""],
             "links": ([{"label": f"Open the full paper at PDF page {it['pdf_page']}", "href": it["pdf_url"]}] if it.get("pdf_url") else [])}
            for it in items]
    html = form_kit_html(kit="bartype_random", version=VERSION, title="AAMAS error-bar meaning from the full paper",
                         intro_html=C4_INTRO, items=view, fields=C4_FIELDS, gates=C4_GATES,
                         sets={"core": "Core papers (do these)", "reserve": "Reserve (only in order, if asked)", "all": "All"},
                         default_set="core", export_name="bartype_random_{annotator}.csv")
    write_text(html, d, "label.html")


# ----------------------------------------------------------------- C2: protocol review links
def build_protocol_links(urls):
    rows = read_csv(KIT, "protocol_check.csv")
    out = []
    for rank, r in enumerate(rows, 1):
        u = urls.get(r["paper"], {})
        out.append({"row": rank, "paper": r["paper"], "title": r["title"],
                    "priority": "first 8 (model-read K)" if (r.get("model_K") or "").strip() else "after",
                    "pdf_url": u.get("pdf", ""), "local_pdf": r["pdf"]})
    write_csv(out, ["row", "paper", "title", "priority", "pdf_url", "local_pdf"], KIT, "protocol_review", "protocol_links.csv")


# ----------------------------------------------------------------- check / pack / freeze / adjudication
KITS = {"comparison_blind": "labels", "page_detection": "groups", "runcount_disputes": "labels", "bartype_random": "labels"}


def leak_scan(paths):
    hits = []
    for path in paths:
        if not os.path.isfile(path) or path.endswith(".png"):
            continue
        text = open(path, encoding="utf-8").read().lower()
        for tok in FORBIDDEN:
            if tok in text:
                hits.append((os.path.relpath(path, ROOT), tok))
    return hits


def check(verbose=True):
    problems, report = [], {}
    urls = paper_urls()
    report["paper_urls"] = len(urls)
    for kit in KITS:
        d = _p(KIT, kit)
        if not os.path.exists(os.path.join(d, "items.json")):
            problems.append(f"{kit}: items.json missing (run build)")
            continue
        items = json.load(open(os.path.join(d, "items.json"), encoding="utf-8"))
        with_img = [it for it in items if it.get("image")]
        missing = [it["image"] for it in with_img if not os.path.exists(os.path.join(d, it["image"]))]
        no_url = [it["id"] for it in items if not it.get("pdf_url")]
        report[kit] = {"items": len(items), "with_shipped_image": len(with_img) - len(missing),
                       "image_missing": len(missing), "pdf_only": len(items) - len(with_img), "without_pdf_url": len(no_url)}
        if missing:
            problems.append(f"{kit}: {len(missing)} image(s) missing, first {missing[:3]}; rerun build (they are copies of shipped images)")
        if no_url:
            problems.append(f"{kit}: {len(no_url)} item(s) without a PDF URL: {no_url[:5]}")
        leaks = leak_scan([os.path.join(d, "items.json"), os.path.join(d, "label.html")])
        if leaks:
            problems.append(f"{kit}: annotator-facing file mentions a machine field: {leaks[:5]}")
    ep = load_json(KIT, "empty_pages", "items.json")
    st_path = _p(KIT, "empty_pages", "image_status.json")
    if os.path.exists(st_path):
        st = json.load(open(st_path, encoding="utf-8"))
        report["empty_pages"] = {"items": len(ep), **{k: sum(1 for v in st.values() if v["status"] == k)
                                                      for k in sorted({v["status"] for v in st.values()})}}
    else:
        problems.append("empty_pages: image_status.json missing (run `python aamas/human_kits.py --html-only`)")
    ep_sheet = _p(KIT, "empty_pages", "label.html")
    ep_text = open(ep_sheet, encoding="utf-8").read().lower() if os.path.exists(ep_sheet) else ""
    ep_leaks = [t for t in C1_FORBIDDEN if t in ep_text]
    if ep_leaks:
        problems.append(f"empty_pages: label.html reveals the machine reading: {ep_leaks} "
                        f"(rebuild with `python aamas/human_kits.py --html-only`)")
    keys = {k: os.path.exists(_p(KEYS, f"{k}_key.json")) for k in ("comparison", "page", "runcount", "bartype")}
    report["machine_keys_present"] = keys
    if verbose:
        print(json.dumps(report, indent=1))
        for p in problems:
            print("PROBLEM:", p)
        print("check:", "OK" if not problems else f"{len(problems)} problem(s)")
    return problems, report


ANNOTATOR_README = """Instructions for annotators ({kit})

1. Open label.html in a current browser (Chrome, Edge, Firefox). It works offline;
   only the "Open the full paper" links need the internet.
2. Enter the annotator ID you were given (never your name).
3. Answers autosave in this browser under your ID. Press "Export CSV" whenever you
   stop and send the exported file unchanged. To move to another computer, open
   label.html there and use "Resume from CSV".
4. Work only from the table images and the papers. Do not open any other file of the
   project, do not discuss items with another annotator, and do not look up any
   model's or program's reading of these tables.
"""


PACKABLE = sorted(KITS) + ["empty_pages"]


def pack(kit, out_dir):
    """Copy what an annotator needs (sheet, images, blank template, instructions) to <out_dir>/<kit> and zip it.

    empty_pages (C1) ships only its sheet and the shipped renders (img_shipped/, plus img/ when local
    census renders exist); its items.json carries the census reading and never goes in a pack.
    """
    if kit not in PACKABLE:
        raise SystemExit(f"unknown kit {kit}; one of {PACKABLE}")
    src = _p(KIT, kit)
    dst = os.path.abspath(os.path.join(out_dir, kit))
    if os.path.exists(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    names = ["label.html"] + ([f"{KITS[kit]}_template.csv"] if kit in KITS else [])
    for name in names:
        shutil.copyfile(os.path.join(src, name), os.path.join(dst, name))
    for sub in ("images", "img_shipped", "img"):
        if os.path.isdir(os.path.join(src, sub)):
            shutil.copytree(os.path.join(src, sub), os.path.join(dst, sub))
    write_path = os.path.join(dst, "README_ANNOTATOR.txt")
    with open(write_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ANNOTATOR_README.format(kit=kit))
    leaks = leak_scan([os.path.join(dst, n) for n in os.listdir(dst)])
    sheet = open(os.path.join(dst, "label.html"), encoding="utf-8").read().lower()
    leaks += [("label.html", t) for t in C1_FORBIDDEN if t in sheet]
    if leaks:
        shutil.rmtree(dst)
        raise SystemExit(f"refusing to pack: annotator files mention machine fields {leaks[:5]}")
    zpath = dst + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(dst):
            for f in sorted(files):
                full = os.path.join(base, f)
                z.write(full, os.path.relpath(full, os.path.dirname(dst)))
    print(f"packed {kit} -> {dst} and {zpath}")


def freeze(kit):
    raw = _p(KIT, kit, "raw")
    files = sorted(f for f in os.listdir(raw) if f.endswith(".csv")) if os.path.isdir(raw) else []
    if not files:
        raise SystemExit(f"{kit}/raw holds no CSV to freeze")
    path = os.path.join(raw, "FROZEN.json")
    frozen = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    for f in files:
        h = sha256(os.path.join(raw, f))
        if f in frozen and frozen[f]["sha256"] != h:
            raise SystemExit(f"{kit}/raw/{f} changed after it was frozen; raw labels are immutable. "
                             f"Put corrections in the adjudication CSV instead.")
        frozen.setdefault(f, {"sha256": h, "frozen_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")})
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(frozen, fh, indent=1)
        fh.write("\n")
    print(f"froze {len(frozen)} raw file(s) of {kit}")


def adjudication_sheet(kit, a, b):
    sys.path.insert(0, HERE)
    from human_validation_score import load_raw_kit  # noqa: E402
    raws = load_raw_kit(_p(KIT, kit), kit)
    if a not in raws or b not in raws:
        raise SystemExit(f"need raw files for both annotators {a} and {b} in {kit}/raw (found {sorted(raws)})")
    path = _p(KIT, kit, "adjudication.csv")
    if os.path.exists(path):
        raise SystemExit(f"{os.path.relpath(path, ROOT)} exists; adjudication is never overwritten. "
                         f"Move it away first if you really mean to start over.")
    fields = {"comparison_blind": A_FIELDS, "runcount_disputes": C3_FIELDS, "bartype_random": C4_FIELDS}[kit]
    rows = []
    for iid in sorted(set(raws[a]) & set(raws[b])):
        for f in fields:
            va, vb = raws[a][iid].get(f["name"], "").strip(), raws[b][iid].get(f["name"], "").strip()
            if f["name"] in ("comment", "evidence", "passage", "passage_location", "n_runs_other", "other_counts"):
                continue
            if va.lower() != vb.lower():
                rows.append({"id": iid, "field": f["name"], "annotator_a": a, "value_a": va, "annotator_b": b,
                             "value_b": vb, "adjudicated_value": "", "adjudicator": "", "rationale": ""})
    write_csv(rows, ["id", "field", "annotator_a", "value_a", "annotator_b", "value_b", "adjudicated_value",
                     "adjudicator", "rationale"], KIT, kit, "adjudication.csv")
    print(f"{len(rows)} field disagreements -> {os.path.relpath(path, ROOT)} (raw files untouched)")


def fetch_urls():
    sys.path.insert(0, _p("study"))
    from harvest import aamas_index  # noqa: E402
    out = {}
    for y in (2024, 2025, 2026):
        for r in aamas_index(y):
            out[r["id"]] = {"year": y, "pdf": r["pdf"], "title": r["title"]}
    dump_json(dict(sorted(out.items())), KIT, "paper_urls.json")
    print(len(out), "papers ->", os.path.join(KIT, "paper_urls.json"))


def html_all():
    html_comparison()
    html_pages()
    html_runcount()
    html_bartype()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--analysis", default=None,
                   help="the frozen run record out/aamas/analysis.json (released as run_records/analysis.json); "
                        "needed only to (re)write the machine keys of the page and bar-type kits")
    sub.add_parser("html")
    sub.add_parser("check")
    sub.add_parser("urls")
    pk = sub.add_parser("pack")
    pk.add_argument("--kit", required=True)
    pk.add_argument("--out", required=True)
    fz = sub.add_parser("freeze")
    fz.add_argument("--kit", required=True)
    ad = sub.add_parser("adjudication-sheet")
    ad.add_argument("--kit", required=True)
    ad.add_argument("--a", required=True)
    ad.add_argument("--b", required=True)
    args = ap.parse_args(argv)
    os.chdir(ROOT)
    if args.cmd == "urls":
        fetch_urls()
    elif args.cmd == "build":
        urls = paper_urls()
        analysis = args.analysis
        if analysis and not os.path.exists(analysis):
            raise SystemExit(f"--analysis {analysis} does not exist")
        build_comparison(urls)
        build_pages(urls, analysis)
        build_runcount(urls)
        if analysis:
            build_bartype(urls, analysis)
        elif not os.path.exists(_p(KIT, "bartype_random", "items.json")):
            print("bartype_random not built: it needs --analysis (the frozen out/aamas/analysis.json)")
        build_protocol_links(urls)
        html_all()
        from human_kits import write_empty_pages_html  # noqa: E402
        write_empty_pages_html()
        problems, _ = check()
        return 1 if problems else 0
    elif args.cmd == "html":
        html_all()
    elif args.cmd == "check":
        problems, _ = check()
        return 1 if problems else 0
    elif args.cmd == "pack":
        pack(args.kit, args.out)
    elif args.cmd == "freeze":
        freeze(args.kit)
    elif args.cmd == "adjudication-sheet":
        adjudication_sheet(args.kit, args.a, args.b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
