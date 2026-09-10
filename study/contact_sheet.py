"""Contact sheets of sampled tables, for measuring recall by eye.

The headline claim is that most highlighted comparisons print no uncertainty.
The way that claim fails is a false negative: an error bar present in the PDF
that the extractor could not see. Precision checks cannot detect it, because
they only examine values the extractor already found. Only looking at tables the
extractor called empty can.

Rendering one table per image makes a sample of forty expensive. Stacking six
crops into a single sheet, each labelled with what the extractor concluded about
it, makes the same sample cheap enough to do properly -- and the judgement
required per table is small: does this table print any error bar at all?
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import fitz  # noqa: E402
import requests  # noqa: E402

from harvest import SOURCES  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (compatible; paper-audit/0.1)"}
SHEET_WIDTH = 1500
PAD = 14
LABEL_H = 26


def sample_tables(analysis_path: str, n: int, seed: int, bucket: str) -> list:
    """One entry per (paper, table), not per comparison."""
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    by_table: dict = {}
    for c in cmps:
        key = (c["paper"], c["table"], c["page"])
        by_table.setdefault(key, []).append(c)

    rows = []
    for (paper, table, page), group in by_table.items():
        any_disp = any(c["winner_dispersion"] is not None or c["runner_dispersion"] is not None
                       for c in group)
        if bucket == "no_error_bar" and any_disp:
            continue
        if bucket == "has_error_bar" and not any_disp:
            continue
        rows.append({"paper": paper, "table": table, "page": page,
                     "n_comparisons": len(group),
                     "extractor_says": "no error bar anywhere in this table" if not any_disp
                                       else "error bars present",
                     "bbox": group[0].get("bbox")})
    rng = random.Random(seed)
    return rng.sample(rows, min(n, len(rows)))


def _crop(page, bbox, zoom: float = 2.0):
    if not bbox:
        return None
    pad = 26.0
    clip = fitz.Rect(max(0.0, bbox["x_min"] - pad * 3.2),
                     max(0.0, bbox["y_min"] - pad * 2.4),
                     min(page.rect.width, bbox["x_max"] + pad * 3.2),
                     min(page.rect.height, bbox["y_max"] + pad * 1.2))
    if clip.width < 100 or clip.height < 40:
        return None
    return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)


def build_sheets(rows: list, index: dict, out_dir: str, per_sheet: int = 6) -> list:
    from PIL import Image, ImageDraw

    os.makedirs(out_dir, exist_ok=True)
    sess = requests.Session()
    sess.headers.update(UA)
    cache: dict = {}

    crops = []
    for r in rows:
        rec = index.get(r["paper"])
        if rec is None:
            continue
        if r["paper"] not in cache:
            try:
                cache[r["paper"]] = sess.get(rec["pdf"], timeout=90).content
            except Exception as exc:
                print(f"  download failed for {rec['title'][:40]}: {type(exc).__name__}")
                continue
        try:
            doc = fitz.open(stream=cache[r["paper"]], filetype="pdf")
            if r["page"] >= len(doc):
                doc.close()
                continue
            pix = _crop(doc[r["page"]], r["bbox"])
            doc.close()
        except Exception:
            continue
        if pix is None:
            continue
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        if img.width > SHEET_WIDTH - 2 * PAD:
            ratio = (SHEET_WIDTH - 2 * PAD) / img.width
            img = img.resize((int(img.width * ratio), int(img.height * ratio)))
        crops.append((r, rec, img))

    sheets = []
    for start in range(0, len(crops), per_sheet):
        chunk = crops[start:start + per_sheet]
        height = PAD + sum(im.height + LABEL_H + PAD for _, _, im in chunk)
        sheet = Image.new("RGB", (SHEET_WIDTH, height), "white")
        draw = ImageDraw.Draw(sheet)
        y = PAD
        entries = []
        for i, (r, rec, im) in enumerate(chunk, start=start + 1):
            label = (f"[{i}] Table {r['table']}  p{r['page'] + 1}  "
                     f"{r['n_comparisons']} comparison(s)  |  extractor: {r['extractor_says']}"
                     f"  |  {rec['venue']} {rec['year']}")
            draw.text((PAD, y + 6), label, fill="black")
            y += LABEL_H
            sheet.paste(im, (PAD, y))
            draw.rectangle([PAD - 1, y - 1, PAD + im.width, y + im.height], outline="#bbbbbb")
            y += im.height + PAD
            entries.append({"index": i, "paper": r["paper"], "table": r["table"],
                            "page": r["page"], "title": rec["title"],
                            "venue": rec["venue"], "year": rec["year"],
                            "extractor_says": r["extractor_says"],
                            "n_comparisons": r["n_comparisons"],
                            "verdict": None, "note": ""})
        name = f"sheet_{start // per_sheet + 1:02d}.png"
        sheet.save(os.path.join(out_dir, name))
        sheets.append({"sheet": name, "entries": entries})
        print(f"  {name}: {len(chunk)} tables")

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(sheets, fh, indent=1, ensure_ascii=False)
    return sheets


def score(manifest_path: str) -> dict:
    with open(manifest_path, encoding="utf-8") as fh:
        sheets = json.load(fh)
    entries = [e for s in sheets for e in s["entries"]]
    judged = [e for e in entries if e.get("verdict")]
    agree = [e for e in judged if e["verdict"] == "agree"]
    missed = [e for e in judged if e["verdict"] == "missed"]
    unclear = [e for e in judged if e["verdict"] == "unclear"]
    n = len(judged)
    from paperengine.stats import wilson_interval
    lo, hi = wilson_interval(len(agree), n) if n else (0.0, 1.0)
    return {
        "n_tables_rendered": len(entries), "n_judged": n,
        "agree": len(agree), "extractor_missed_an_error_bar": len(missed),
        "unclear": len(unclear),
        "recall_on_no_error_bar_calls": round(len(agree) / n, 3) if n else None,
        "wilson_95": [round(lo, 3), round(hi, 3)],
        "misses": [{"index": e["index"], "title": e["title"][:60], "note": e["note"]}
                   for e in missed],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Contact sheets of sampled tables for visual recall checking.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--analysis", default="out/analysis_2025.json")
    b.add_argument("--source", action="append", default=["neurips2025", "icml2025"])
    b.add_argument("--n", type=int, default=36)
    b.add_argument("--seed", type=int, default=17)
    b.add_argument("--bucket", choices=["no_error_bar", "has_error_bar", "all"],
                   default="no_error_bar")
    b.add_argument("--per-sheet", type=int, default=6)
    b.add_argument("--out-dir", default="out/sheets")
    s = sub.add_parser("score")
    s.add_argument("--manifest", default="out/sheets/manifest.json")
    args = ap.parse_args(argv)

    if args.cmd == "score":
        print(json.dumps(score(args.manifest), indent=1))
        return 0

    rows = sample_tables(args.analysis, args.n, args.seed, args.bucket)
    print(f"sampled {len(rows)} tables from the '{args.bucket}' bucket; building index ...")
    index = {}
    for src in args.source:
        for rec in SOURCES[src]():
            index[rec["id"]] = rec
    build_sheets(rows, index, args.out_dir, per_sheet=args.per_sheet)
    print(f"\n-> {args.out_dir}")
    print("For each numbered table, decide: does it print ANY error bar?")
    print("  'agree'  = extractor is right, no error bar present")
    print("  'missed' = an error bar is visible that the extractor did not find")
    return 0


if __name__ == "__main__":
    sys.exit(main())
