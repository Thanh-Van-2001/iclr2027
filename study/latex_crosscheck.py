"""Check the PDF extractor against LaTeX source, where a bar is unambiguous.

Every validation in the paper so far reads the same rendered PDF the pipeline
reads. Most NeurIPS and ICML papers also exist on arXiv with their LaTeX
source, in which ``\\pm`` and ``\\textbf`` are not a matter of glyph geometry.
This matches a sample of papers to arXiv by title, downloads the source, and
compares, per paper and per table, whether the source prints an error bar in
a table and a bold cell, against what the pipeline read from the PDF.

The arXiv version may differ from the proceedings version, so disagreement is
an upper bound on the extractor's error, not the error itself.

    python study/latex_crosscheck.py --n 300 --seed 0
"""

from __future__ import annotations

import argparse
import difflib
import gzip
import io
import json
import os
import random
import re
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from analyze import load_records  # noqa: E402
from paperengine.stats import wilson_interval  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; paper-audit/0.1; mailto:anonymous@example.org)"}
ARXIV_API = "http://export.arxiv.org/api/query?search_query=ti:%s&max_results=5"
ARXIV_SRC = "https://arxiv.org/e-print/%s"
PAUSE = 3.2  # arXiv asks for one request every three seconds


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def _get(url: str, timeout: int = 90) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def arxiv_match(title: str) -> tuple:
    """The arXiv id whose title matches, or None."""
    q = urllib.parse.quote('"%s"' % re.sub(r'["\\]', " ", title)[:200])
    try:
        xml = _get(ARXIV_API % q, timeout=60)
    except Exception:  # noqa: BLE001
        return None, 0.0
    ns = {"a": "http://www.w3.org/2005/Atom"}
    best, best_sim = None, 0.0
    for e in ET.fromstring(xml).findall("a:entry", ns):
        t = e.findtext("a:title", default="", namespaces=ns)
        aid = e.findtext("a:id", default="", namespaces=ns).rsplit("/abs/", 1)[-1]
        sim = difflib.SequenceMatcher(None, _norm(title), _norm(t)).ratio()
        if sim > best_sim:
            best, best_sim = aid, sim
    return (best, best_sim) if best_sim >= 0.9 else (None, best_sim)


def fetch_source(aid: str) -> dict:
    """Every .tex file in the e-print, by name."""
    blob = _get(ARXIV_SRC % aid)
    files: dict = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.lower().endswith(".tex"):
                    files[m.name] = tf.extractfile(m).read().decode("utf-8", "replace")
        return files
    except tarfile.TarError:
        pass
    try:
        text = gzip.decompress(blob).decode("utf-8", "replace")
        if "\\begin{document}" in text or "\\begin{table" in text:
            files["main.tex"] = text
    except OSError:
        text = blob.decode("utf-8", "replace")
        if "\\begin{table" in text:
            files["main.tex"] = text
    return files


def _resolve_inputs(text: str, files: dict, depth: int = 0) -> str:
    """Inline \\input and \\include so that tables kept in their own files count."""
    if depth > 3:
        return text

    def sub(m):
        name = m.group(1).strip()
        for cand in (name, name + ".tex"):
            for key in files:
                if key == cand or key.endswith("/" + cand):
                    return _resolve_inputs(files[key], files, depth + 1)
        return ""
    return re.sub(r"\\(?:input|include)\{([^}]+)\}", sub, text)


def _strip_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", text)


TABLE_ENV = re.compile(r"\\begin\{table\*?\}(.*?)\\end\{table\*?\}", re.S)
CAPTION = re.compile(r"\\caption\s*(?:\[[^\]]*\])?\s*\{")
BOLD = re.compile(r"\\(?:textbf|mathbf|bm|boldsymbol)\s*\{|\\bf(?:series)?\b|\\B\{")
PM = re.compile(r"\\pm\b|\\mp\b|±|\\scriptsize\s*\\pm|\\stdv|\\std\{")


def _caption_of(block: str) -> str:
    m = CAPTION.search(block)
    if not m:
        return ""
    i, depth, out = m.end(), 1, []
    while i < len(block) and depth:
        ch = block[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        out.append(ch)
        i += 1
    cap = "".join(out)
    cap = re.sub(r"\\(?:label|cite[pt]?|ref)\{[^}]*\}", " ", cap)
    cap = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", cap)
    return re.sub(r"[{}$]", " ", cap)


def source_tables(files: dict) -> list:
    mains = [k for k, v in files.items() if "\\begin{document}" in v] or list(files)
    tables = []
    for k in mains:
        text = _strip_comments(_resolve_inputs(files[k], files))
        for m in TABLE_ENV.finditer(text):
            block = m.group(1)
            body = block[block.find("\\begin{tabular"):] if "\\begin{tabular" in block else block
            tables.append({
                "caption": _caption_of(block)[:300],
                "has_pm": bool(PM.search(body)),
                "n_pm": len(PM.findall(body)),
                "has_bold": bool(BOLD.search(body)),
                "n_cells": body.count("&"),
            })
    return tables


def compare(records: list, matched: dict) -> dict:
    """Paper- and table-level agreement between source and pipeline."""
    paper_2x2 = {"both_bar": 0, "both_none": 0, "source_only": 0, "pipeline_only": 0}
    tab_pm = {"both": 0, "neither": 0, "source_only": 0, "pipeline_only": 0}
    tab_bold = {"both": 0, "neither": 0, "source_only": 0, "pipeline_only": 0}
    n_tables_matched = 0
    unmatched_source_tables = 0
    for r in records:
        m = matched.get(r["id"])
        if not m or not m.get("tables"):
            continue
        src_bar = any(t["has_pm"] for t in m["tables"] if t["n_cells"] >= 6)
        pipe_bar = bool(r.get("reports_explicit_error_bar"))
        if src_bar and pipe_bar:
            paper_2x2["both_bar"] += 1
        elif not src_bar and not pipe_bar:
            paper_2x2["both_none"] += 1
        elif src_bar:
            paper_2x2["source_only"] += 1
        else:
            paper_2x2["pipeline_only"] += 1
        pdf_tables = [{"caption": _norm(t.get("caption") or "")[:120],
                       "has_pm": any(c.get("dispersion_style") in ("pm", "ci") for c in t["cells"]),
                       "has_bold": any(c["bold"] for c in t["cells"])} for t in r.get("tables", [])]
        for st in m["tables"]:
            if st["n_cells"] < 6:
                continue
            key = _norm(st["caption"])[:120]
            if len(key) < 20:
                unmatched_source_tables += 1
                continue
            best, best_sim = None, 0.0
            for pt in pdf_tables:
                sim = difflib.SequenceMatcher(None, key, pt["caption"]).ratio()
                if sim > best_sim:
                    best, best_sim = pt, sim
            if best is None or best_sim < 0.6:
                unmatched_source_tables += 1
                continue
            n_tables_matched += 1
            for d, a, b in ((tab_pm, st["has_pm"], best["has_pm"]),
                            (tab_bold, st["has_bold"], best["has_bold"])):
                if a and b:
                    d["both"] += 1
                elif not a and not b:
                    d["neither"] += 1
                elif a:
                    d["source_only"] += 1
                else:
                    d["pipeline_only"] += 1

    def agree(d, keys):
        n = sum(d.values())
        a = sum(d[k] for k in keys)
        lo, hi = wilson_interval(a, n) if n else (0.0, 0.0)
        return {"n": n, "agree": a, "pct": round(100 * a / n, 1) if n else None,
                "ci": [round(100 * lo, 1), round(100 * hi, 1)]}

    n_src_bar = paper_2x2["both_bar"] + paper_2x2["source_only"]
    return {
        "papers_compared": sum(paper_2x2.values()),
        "paper_level": {**paper_2x2, **agree(paper_2x2, ("both_bar", "both_none")),
                        "pipeline_recall_of_source_bar": round(
                            100 * paper_2x2["both_bar"] / n_src_bar, 1) if n_src_bar else None,
                        "pipeline_recall_ci": [round(100 * x, 1) for x in wilson_interval(
                            paper_2x2["both_bar"], n_src_bar)] if n_src_bar else None},
        "tables_matched": n_tables_matched,
        "source_tables_unmatched": unmatched_source_tables,
        "table_level_error_bar": {**tab_pm, **agree(tab_pm, ("both", "neither"))},
        "table_level_bold": {**tab_bold, **agree(tab_bold, ("both", "neither"))},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--extracted", default="data/extracted_2025.jsonl")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache", default="out/latex_crosscheck_cache.json")
    ap.add_argument("--out", default="out/latex_crosscheck.json")
    args = ap.parse_args(argv)

    records = load_records(args.extracted)
    with_tables = [r for r in records if r.get("n_tables_detected", 0) > 0]
    sample = random.Random(args.seed).sample(with_tables, min(args.n, len(with_tables)))
    cache = {}
    if os.path.exists(args.cache):
        with open(args.cache, encoding="utf-8") as fh:
            cache = json.load(fh)

    for i, r in enumerate(sample, 1):
        if r["id"] in cache:
            continue
        entry = {"title": r["title"]}
        aid, sim = arxiv_match(r["title"])
        entry["arxiv_id"], entry["title_similarity"] = aid, round(sim, 3)
        time.sleep(PAUSE)
        if aid:
            try:
                files = fetch_source(aid)
                entry["n_tex_files"] = len(files)
                entry["tables"] = source_tables(files)
            except Exception as exc:  # noqa: BLE001
                entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
            time.sleep(PAUSE)
        cache[r["id"]] = entry
        with open(args.cache, "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        if i % 10 == 0:
            print(f"  {i}/{len(sample)} matched={sum(1 for v in cache.values() if v.get('arxiv_id'))} "
                  f"with_tables={sum(1 for v in cache.values() if v.get('tables'))}", flush=True)

    res = compare(sample, cache)
    res["papers_sampled"] = len(sample)
    res["matched_to_arxiv"] = sum(1 for r in sample if cache.get(r["id"], {}).get("arxiv_id"))
    res["source_with_table_environment"] = sum(1 for r in sample if cache.get(r["id"], {}).get("tables"))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
