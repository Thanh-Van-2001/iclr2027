"""Check the extractor against the source PDFs, by eye.

Every number in this study passes through a parser, and a parser that is wrong
in a systematic way would produce a confident, entirely false paper. The claim
"90% of comparisons carry no uncertainty" is indistinguishable, from the inside,
from "our regex misses most error bars". Only looking at the pages settles it.

This samples comparisons, re-downloads the papers they came from, and renders
the region of the page around each table as an image, with the extracted values
printed beside it. A human -- or a model that can see -- then marks each one
correct or not, and the resulting precision goes in the paper. If it is low, the
finding changes; that is the point of measuring it.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import fitz  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402


def sample_comparisons(analysis_path: str, n: int, seed: int, bucket: str) -> list:
    """Sample from one of the buckets the study reports.

    ``no_error_bar`` matters most. The headline claim is that most highlighted
    comparisons print no uncertainty, and the way that claim fails is a false
    negative: an error bar the extractor could not see. Checking only the
    comparisons it did parse would confirm nothing.
    """
    with open(analysis_path, encoding="utf-8") as fh:
        cmps = json.load(fh)["_comparisons"]
    if bucket == "testable":
        pool = [c for c in cmps if c.get("test")]
    elif bucket == "no_error_bar":
        pool = [c for c in cmps
                if c["winner_dispersion"] is None and c["runner_dispersion"] is None]
    else:
        pool = cmps
    rng = random.Random(seed)
    return rng.sample(pool, min(n, len(pool)))


def _index_by_id(sources: list) -> dict:
    out = {}
    for s in sources:
        for rec in SOURCES[s]():
            out[rec["id"]] = rec
    return out


def _table_clip(page, comparison: dict, pad: float = 26.0):
    """Bounding box of the table this comparison came from.

    Rendering the whole page is legible but wasteful: most of the pixels are
    body text nobody needs to read to decide whether two numbers were parsed
    correctly. Cropping to the caption's band and the rows beneath it makes each
    check cheap enough to do a hundred times, which is what the paper needs.
    """
    b = comparison.get("bbox")
    if not b:
        return None
    top = max(0.0, b["y_min"] - pad * 2.4)
    bottom = min(page.rect.height, b["y_max"] + pad * 1.2)
    left = max(0.0, b["x_min"] - pad * 3.2)
    right = min(page.rect.width, b["x_max"] + pad * 3.2)
    if bottom - top < 60 or right - left < 120:
        return None
    return fitz.Rect(left, top, right, bottom)


def render(comparisons: list, index: dict, out_dir: str, *, zoom: float = 2.6,
           crop: bool = True) -> list:
    os.makedirs(out_dir, exist_ok=True)
    cache: dict = {}
    manifest = []
    for i, c in enumerate(comparisons, 1):
        rec = index.get(c["paper"])
        if rec is None:
            print(f"  [{i}] paper {c['paper']} not in the source index")
            continue
        if c["paper"] not in cache:
            try:
                cache[c["paper"]] = _get(rec["pdf"])
            except Exception as exc:
                print(f"  [{i}] download failed: {exc}")
                continue
        blob = cache[c["paper"]]
        tmp = os.path.join(out_dir, "_tmp.pdf")
        with open(tmp, "wb") as fh:
            fh.write(blob)
        doc = fitz.open(tmp)
        if c["page"] >= len(doc):
            doc.close()
            continue
        page = doc[c["page"]]
        clip = _table_clip(page, c) if crop else None
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip)
        name = f"{i:03d}_{c['paper'][:8]}_p{c['page']}_t{c['table']}.png"
        pix.save(os.path.join(out_dir, name))
        doc.close()
        manifest.append({
            "image": name,
            "title": rec["title"],
            "venue": rec["venue"], "year": rec["year"],
            "table": c["table"], "page_zero_indexed": c["page"],
            "extracted": {
                "winner": c["winner"], "winner_dispersion": c["winner_dispersion"],
                "runner_up": c["runner_up"], "runner_dispersion": c["runner_dispersion"],
                "direction": c["direction"], "gap": round(c["gap"], 4),
                "dispersion_kind": c["dispersion_kind"], "n_runs": c["n_runs"],
                "n_comparisons_in_table": c["n_comparisons_in_table"],
            },
            "verdict": None,   # to be filled in: "correct" | "wrong" | "unclear"
            "note": "",
        })
        print(f"  [{i}] {name}  winner={c['winner']}±{c['winner_dispersion']} "
              f"runner={c['runner_up']}±{c['runner_dispersion']} ({rec['title'][:45]})")
    tmp = os.path.join(out_dir, "_tmp.pdf")
    if os.path.exists(tmp):
        os.unlink(tmp)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    return manifest


def score(manifest_path: str) -> dict:
    with open(manifest_path, encoding="utf-8") as fh:
        items = json.load(fh)
    judged = [i for i in items if i.get("verdict")]
    correct = [i for i in judged if i["verdict"] == "correct"]
    wrong = [i for i in judged if i["verdict"] == "wrong"]
    unclear = [i for i in judged if i["verdict"] == "unclear"]
    n = len(judged)
    from paperengine.stats import wilson_interval
    lo, hi = wilson_interval(len(correct), n) if n else (0.0, 1.0)
    return {
        "n_rendered": len(items), "n_judged": n,
        "correct": len(correct), "wrong": len(wrong), "unclear": len(unclear),
        "precision": round(len(correct) / n, 3) if n else None,
        "wilson_95": [round(lo, 3), round(hi, 3)],
        "errors": [{"image": i["image"], "note": i["note"]} for i in wrong],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Render sampled comparisons for visual validation.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render")
    r.add_argument("--analysis", default="out/analysis_2025.json")
    r.add_argument("--source", action="append", default=["neurips2025", "icml2025"])
    r.add_argument("--n", type=int, default=20)
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--bucket", choices=["testable", "no_error_bar", "all"], default="all")
    r.add_argument("--out-dir", default="out/validation")
    r.add_argument("--no-crop", action="store_true",
                   help="render the whole page instead of just the table")

    s = sub.add_parser("score")
    s.add_argument("--manifest", default="out/validation/manifest.json")

    args = ap.parse_args(argv)
    if args.cmd == "score":
        print(json.dumps(score(args.manifest), indent=1))
        return 0

    cmps = sample_comparisons(args.analysis, args.n, args.seed, args.bucket)
    print(f"sampled {len(cmps)} comparisons; building the source index ...")
    index = _index_by_id(args.source)
    print(f"index has {len(index)} papers")
    manifest = render(cmps, index, args.out_dir, crop=not args.no_crop)
    print(f"\nrendered {len(manifest)} pages into {args.out_dir}")
    print("Now open each image, compare with the 'extracted' block in manifest.json,")
    print("and set verdict to correct / wrong / unclear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
