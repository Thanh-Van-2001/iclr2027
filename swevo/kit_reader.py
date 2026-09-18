"""A model answers the human kits: for each item the page image, the
table's caption start, the group's label and the run sentences, and the
questions a person would answer. Written for a second vendor's model so
that the reader's pairing on the separate-column and Mean/Std-row layouts
is checked by something other than itself; it is not a human label and is
reported as a model reading.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/kit_reader.py --kit audits/swevo_human --model cc/claude-sonnet-5
"""
import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from read_kit_api import VENDORS, ask  # noqa: E402

PROMPT = """You are checking one bold cell in a results table of a metaheuristics paper. The image is a WHOLE PAGE, rendered at twice its printed size, with nothing marked. Find the table whose caption begins "{caption}" and, in it, the group (row or column) labelled "{label}" (direction: {direction} is better). The group's BOLD cell is the winner.

Record, exactly as printed (write "unclear" for a digit you cannot read, "none" where nothing is printed):
- results_table: y/n (is this a table of experimental results);
- bold_ok: y/n (the group has exactly one bold cell);
- std_printed: y/n (is a standard deviation printed for the bold cell anywhere in the table: in the cell, in a Std row beneath it, or in a Std column beside it);
- winner_mean: the bold cell's value;
- winner_disp: the deviation that belongs to the bold cell (from the Std row or column of the same optimizer and the same function), or none;
- runner_mean: the best NON-bold value in the same group (by the direction);
- runner_disp: the deviation that belongs to that rival cell, or none;
- n_runs: the number of independent runs that applies to this table, from the caption, the page, or the run sentences below; "none" if nothing states one;
- note: one sentence.

Run sentences from the paper:
{runs}

Answer with ONE JSON object and nothing else: {{"results_table": "y", "bold_ok": "y", "std_printed": "y", "winner_mean": "...", "winner_disp": "...", "runner_mean": "...", "runner_disp": "...", "n_runs": "...", "note": "..."}}"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit", default="audits/swevo_human")
    ap.add_argument("--model", default="cc/claude-sonnet-5")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    vendor = dict(VENDORS["relay"])
    vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key or not vendor["url"]:
        print("set the relay URL and key first", file=sys.stderr)
        return 2
    items = json.load(open(os.path.join(args.kit, "items.json"), encoding="utf-8"))
    out = args.out or os.path.join(args.kit, f"labels_{args.model.split('/')[-1]}.csv")
    done = {}
    if os.path.exists(out):
        done = {r["id"]: r for r in csv.DictReader(open(out, encoding="utf-8", newline=""))}
    cols = ["id", "results_table", "bold_ok", "std_printed", "winner_mean", "winner_disp", "runner_mean", "runner_disp", "n_runs", "note"]
    rows = []
    for it in items:
        if it["id"] in done and any(done[it["id"]].get(c) for c in cols[1:]):
            rows.append(done[it["id"]])
            continue
        img = os.path.join(args.kit, "img", f"{it['page_id']}.png")
        text = PROMPT.format(caption=str(it.get("caption_start", ""))[:80].replace('"', "'"), label=str(it.get("label", "")).replace('"', "'"),
                             direction=it.get("direction", ""), runs=str(it.get("run_sentences", ""))[:3000])
        try:
            raw = ask(vendor, key, img, text, max_tokens=1500, return_text=True, timeout=240)
            m = re.search(r"\{.*\}", raw, re.S)
            ans = json.loads(m.group(0)) if m else {}
        except Exception as exc:  # noqa: BLE001
            print(f"  {it['id']} failed: {exc}", flush=True)
            ans = {"note": f"failed: {exc}"}
        row = {"id": it["id"]}
        for c in cols[1:]:
            v = ans.get(c, "")
            row[c] = str(v).strip().replace(",", ";") if v is not None else ""
        rows.append(row)
        with open(out, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"  {it['id']} std={row['std_printed']} w={row['winner_mean']} wd={row['winner_disp']} r={row['runner_mean']} rd={row['runner_disp']} n={row['n_runs']}", flush=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print("wrote", out, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
