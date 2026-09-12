"""Render the frozen set's testable items again without the red box.

The anchored reading marks the pipeline's chosen cell; the control asks a
reader to find every single-bold group in the same crop unaided, so that the
pipeline's choice of claim, not only its reading of the chosen cell, can be
scored. Usage: python study/render_nobox.py --items audits/gold_d/items.json
--out-dir audits/gold_d_nobox
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_set import render  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="audits/gold_d/items.json")
    ap.add_argument("--out-dir", default="audits/gold_d_nobox")
    ap.add_argument("--stratum", default="testable")
    args = ap.parse_args(argv)
    items = [dict(it, mark=None) for it in json.load(open(args.items, encoding="utf-8"))
             if it["stratum"] == args.stratum]
    render(items, ["neurips2025", "icml2025"], args.out_dir)
    json.dump(items, open(os.path.join(args.out_dir, "items.json"), "w", encoding="utf-8"), indent=1)
    print(len(items), "items ->", args.out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
