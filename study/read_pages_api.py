"""End-to-end reading of whole pages by an API model: every results table on
the page, every single-bold group, its bars and run count, under the same
protocol the random-page reader followed. Writes labels.json in the shape
pages_score.py reads.

Usage: RELAY_URL=... RELAY_API_KEY=... python study/read_pages_api.py --kit audits/aamas_testable_pages
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from read_kit_api import VENDORS, ask  # noqa: E402

PROTO = """You are the end-to-end reader for a paper that audits results tables. The image is a WHOLE PAGE of a
multi-agent-systems paper (two-column ACM format), rendered at twice its printed size, with nothing marked.

List every table of experimental results whose body is on the page (ignore tables of hyperparameters, dataset
statistics, notation, prompts). For each such table record: caption_start (the first words of its caption);
results_table (y/n); orientation (the grouping it marks winners within: "column" if each column holds one bold
cell, "row" if each row does, "none" if no cell is bold or bold marks something other than a single winner per
group, e.g. every cell bold); any_error_bar (y/n: does ANY cell print a dispersion, a +/- value, a parenthesised
or subscript value, a bracketed interval, or a separate std/SE column); bar_kind (sd / se / ci / unlabelled if
bars exist but nothing says what they are / none if no bars, from the caption); n_runs (the run count that
applies to this table, from its caption first and otherwise from the run sentences below, or "none"); n_source
(caption / page / paper / none); bar_form (how bars are set in this table: pm / paren / bracket / subscript /
separate_column / none); groups: EVERY group with exactly one bold cell (up to 40), each with label (its
header label), direction (higher/lower), winner_mean, winner_disp, runner_mean, runner_disp (the bold cell's
mean and bar, and the best NON-bold cell's mean and bar in that group; values exactly as printed; "none" for a
value with no bar; "unclear" if you cannot read a digit); note. At the page level also record
figure_band_on_page (y/n: does any figure on this page draw shaded bands, error bars or intervals).

Run sentences from the paper:
{runs}

Answer with ONE JSON object and nothing else: {{"tables": [{{"caption_start": "...", "results_table": "y",
"orientation": "column", "any_error_bar": "y", "bar_kind": "sd", "n_runs": "5", "n_source": "caption",
"bar_form": "pm", "groups": [{{"label": "...", "direction": "higher", "winner_mean": "...", "winner_disp": "...",
"runner_mean": "...", "runner_disp": "..."}}], "note": "..."}}], "figure_band_on_page": "n", "note": "..."}}"""


STRICT = ("\n\nYour previous answer was not valid JSON. Output strictly valid JSON: every string in double quotes, "
          "no double quotes inside strings (use single quotes instead), no trailing commas, no comments, no text "
          "before or after the object.")


def _parse(text: str) -> dict:
    """Parse the model's JSON; strip code fences and any text around the
    object, and repair a truncated array by closing it."""
    s = text.strip()
    if "```" in s:
        parts = s.split("```")
        s = max(parts, key=len)
        if s.startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0:
        raise ValueError("no JSON object")
    s = s[i:j + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # a truncated answer: cut back to the last complete group and close
        k = s.rfind("}")
        while k > 0:
            try:
                return json.loads(s[:k + 1] + "]}]}")
            except json.JSONDecodeError:
                k = s.rfind("}", 0, k)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", default="relay", choices=sorted(VENDORS))
    ap.add_argument("--model", default=None)
    ap.add_argument("--kit", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--shard", default=None, help="k/n: read only every n-th item starting at k (parallel runs)")
    ap.add_argument("--reverse", action="store_true", help="read the shard from its end (a second worker meeting the first)")
    ap.add_argument("--max-tokens", type=int, default=12000, help="output budget per call")
    ap.add_argument("--venue-phrase", default="multi-agent-systems paper (two-column ACM format)",
                    help="the one phrase of the protocol naming the page's format; for the mainstream pages "
                         "'machine-learning paper (single-column NeurIPS/ICML format)'")
    ap.add_argument("--bar-forms", default="pm / paren / bracket / subscript / separate_column / none",
                    help="the bar_form vocabulary of the protocol; the metaheuristics census adds separate_row "
                         "(mean and deviation printed as two rows of the same table)")
    ap.add_argument("--extra-instruction", default=None,
                    help="a paragraph appended to the protocol (the metaheuristics re-read of Mean/Std-row tables)")
    ap.add_argument("--reasoning-effort", default=None,
                    help="sent as {'reasoning': {'effort': ...}}; the 15 census pages on which the relay timed out at "
                         "the default were read at 'low', everything else identical")
    args = ap.parse_args(argv)
    vendor = dict(VENDORS[args.vendor])
    if args.model:
        vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key or not vendor["url"]:
        print("set the relay URL and key first", file=sys.stderr)
        return 2
    items = json.load(open(os.path.join(args.kit, "items.json"), encoding="utf-8"))
    suffix = ""
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        items = items[k::n]
        suffix = f"_shard{k}" + ("r" if args.reverse else "")
    if args.reverse:
        items = list(reversed(items))
    out = args.out or os.path.join(args.kit, f"labels{suffix}.json")
    if args.out and args.reverse:
        # a reverse worker on a named output writes beside it, never into it
        out = out[:-5] + "r.json"
    pages = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else []
    done = {p["id"] for p in pages}
    # a forward worker on the same shard writes its own file; skip what it has done
    twin = out.replace("r.json", ".json") if args.reverse else out.replace("_shard", "_shard").replace(".json", "r.json")
    if os.path.exists(twin):
        done |= {p["id"] for p in json.load(open(twin, encoding="utf-8"))}
    for it in items:
        if it["id"] in done:
            continue
        if os.path.exists(twin):
            try:
                if it["id"] in {p["id"] for p in json.load(open(twin, encoding="utf-8"))}:
                    continue
            except Exception:  # noqa: BLE001
                pass
        img = os.path.join(args.kit, "img", f"{it['id']}_page.png")
        runs_path = os.path.join(args.kit, "img", f"{it['id']}_runs.txt")
        runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else "(none)"
        ans = None
        proto = PROTO.replace("multi-agent-systems paper (two-column ACM format)", args.venue_phrase)
        proto = proto.replace("pm / paren / bracket / subscript / separate_column / none", args.bar_forms)
        if args.extra_instruction:
            proto = proto.replace("Run sentences from the paper:", args.extra_instruction.strip() + chr(10) + chr(10) + "Run sentences from the paper:", 1)
        prompt = proto.format(runs=runs[:6000])
        effort_used = args.reasoning_effort
        for attempt in range(3):
            try:
                # a page on which the relay times out twice at the default
                # reasoning setting is read at 'low' on the third attempt,
                # as the fifteen densest census pages were; the record says so
                effort = args.reasoning_effort or ("low" if attempt == 2 else None)
                # a default-setting attempt that has not answered in two
                # minutes is a dense page the gateway will time out on
                text = ask(vendor, key, img, prompt, max_tokens=args.max_tokens, return_text=True,
                           retries=1 if attempt < 2 else 2, timeout=120 if attempt < 2 else 300,
                           extra={"reasoning": {"effort": effort}} if effort else None)
                ans = _parse(text)
                effort_used = effort
                break
            except Exception as exc:  # noqa: BLE001
                print(f"  {it['id']} attempt {attempt + 1} failed: {str(exc)[:120]}", flush=True)
                prompt = proto.format(runs=runs[:6000]) + (STRICT if "JSON" in str(exc) or "Expecting" in str(exc) else "")
        if ans is None:
            ans = {"tables": [], "note": "failed: no valid JSON after three attempts"}
        tables = ans.get("tables", []) if isinstance(ans, dict) else []
        for t in tables:
            t.setdefault("groups", [])
            for k in ("caption_start", "results_table", "orientation", "any_error_bar", "bar_kind", "n_runs", "n_source", "bar_form", "note"):
                t[k] = str(t.get(k, "")).strip()
            for g in t["groups"]:
                for k in ("label", "direction", "winner_mean", "winner_disp", "runner_mean", "runner_disp"):
                    g[k] = str(g.get(k, "")).strip()
        pages.append({"id": it["id"], "tables": tables,
                      "figure_band_on_page": str(ans.get("figure_band_on_page", "")).strip() if isinstance(ans, dict) else "",
                      "note": str(ans.get("note", "")) if isinstance(ans, dict) else "",
                      "reasoning_effort": effort_used or "default"})
        json.dump(pages, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(f"  {it['id']} {len(tables)} tables, {sum(len(t['groups']) for t in tables)} groups", flush=True)
    print("wrote", out, len(pages), "pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
