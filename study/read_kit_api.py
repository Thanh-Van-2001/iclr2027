"""Read the sixty-item labelling kit with a vision model from another vendor.

The kit (audits/human) is the same sixty items a person would label; this
sends each rendering, with the run sentences, to an OpenAI-compatible
chat endpoint that accepts images, under the Appendix D prompt, and writes a
labels.csv in the kit's format. The result is a machine reading from a
different vendor, reported as such; it is not a human reference.

Usage (key in an environment variable, never on the command line):
  set MOONSHOT_API_KEY=...   (or DASHSCOPE_API_KEY, ZHIPU_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY)
  python study/read_kit_api.py --vendor kimi   --out audits/gold_d_kimi/labels.csv
  python study/read_kit_api.py --vendor qwen   --out audits/gold_d_qwen/labels.csv
  python study/read_kit_api.py --vendor glm    --out audits/gold_d_glm/labels.csv
Then: python study/gold_set.py score --items audits/gold_d/items.json --labels <out> --out out/gold_set_<vendor>.json
      python study/gold_set.py agree --a audits/gold_d/labels.csv --b <out>
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.request

VENDORS = {
    "kimi": {"url": "https://api.moonshot.cn/v1/chat/completions", "key": "MOONSHOT_API_KEY",
             "model": "kimi-latest"},
    "qwen": {"url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
             "key": "DASHSCOPE_API_KEY", "model": "qwen-vl-max"},
    "glm": {"url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "key": "ZHIPU_API_KEY",
            "model": "glm-4.5v"},
    "openai": {"url": "https://api.openai.com/v1/chat/completions", "key": "OPENAI_API_KEY",
               "model": "gpt-5"},
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "key": "GEMINI_API_KEY", "model": "gemini-2.5-pro"},
    # an OpenAI-compatible relay carrying several vendors; pass --model
    "relay": {"url": os.environ.get("RELAY_URL", ""),
              "key": "RELAY_API_KEY", "model": "gemini/gemini-3.1-pro-preview"},
}

COLS = ["id", "stratum", "results_table", "bold_ok", "orientation", "direction", "winner_mean",
        "winner_disp", "runner_mean", "runner_disp", "disp_type", "n_runs", "n_source",
        "rival_copied", "error_bar_present", "note"]

PROMPT = """You are the blind reader of a reference set for a paper that audits results tables in machine-learning
papers. The image is a crop of a page around one table, rendered at twice its printed size, with a RED BOX drawn
around one cell (the cell under audit) and nothing else drawn.

Definitions. The boxed cell's GROUP is its row or its column, whichever the table marks winners within (exactly one
bold cell per group). orientation = "row" if the group is a row, "column" if a column. direction = "higher" if a
larger value is better for that metric, "lower" otherwise. The RUNNER-UP is the best (by direction) cell in the group
that is NOT bold. Read means and error bars exactly as printed (e.g. "84.3", "0.7"); write "none" if a value has no
error bar and "unclear" if you cannot make out a digit. disp_type: "sd" if the caption or the sentences say standard
deviation, "se" for standard error, "ci" for a confidence interval, "unlabelled" if nothing says.

{task}

Answer with ONE JSON object and nothing else, with exactly these keys (strings): {keys}."""

TASK_TESTABLE = """Record: results_table (y/n: is this a table of experimental results); bold_ok (y/n: the boxed cell is
bold and the only bold cell in its group); orientation; direction; winner_mean, winner_disp, runner_mean,
runner_disp; disp_type; n_runs and n_source (caption/page/paper/none) using ONLY the run sentences below (the
paper's sentences mentioning seeds, runs, trials, times, repetitions), choosing the count that applies to this
table and "none" if no sentence states one that applies; rival_copied (y/n: the runner-up's row or column carries
a citation, dagger, asterisk, or wording such as "from" or "reported in", marking a number copied from another
paper; "unclear" if you cannot tell); note (one sentence).

Run sentences from the paper:
{runs}"""

TASK_NOBAR = """Record: results_table (y/n); bold_ok (y/n: the boxed cell is bold and the only bold cell in its group);
orientation; direction; winner_mean; runner_mean; error_bar_present (y/n: does the table print ANY dispersion for
the boxed cell or its runner-up, inside the cell, in a separate column or row, or a +/- anywhere in the table);
note (one sentence saying where the bar is if present)."""

KEYS = {
    "testable": ["results_table", "bold_ok", "orientation", "direction", "winner_mean", "winner_disp",
                 "runner_mean", "runner_disp", "disp_type", "n_runs", "n_source", "rival_copied", "note"],
    "no_bar": ["results_table", "bold_ok", "orientation", "direction", "winner_mean", "runner_mean",
               "error_bar_present", "note"],
}


def ask(vendor: dict, key: str, image_path: str, text: str, retries: int = 4, max_tokens: int = 4096, return_text: bool = False,
        extra: dict | None = None):
    """extra: request fields merged into the body (e.g. {"stream": True} to keep a
    gateway from timing out on a long answer); the relay may ignore them."""
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    body = {
        "model": vendor["model"],
        "temperature": 0,
        "stream": False,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]}],
    }
    body.update(extra or {})
    req = urllib.request.Request(vendor["url"], data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read().decode()
            if raw.lstrip().startswith("data:"):
                # a relay that streams regardless: stitch the deltas together
                parts = []
                for line in raw.splitlines():
                    if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                        chunk = json.loads(line[5:])
                        for ch in chunk.get("choices", []):
                            parts.append(ch.get("delta", {}).get("content") or "")
                content = "".join(parts)
            else:
                out = json.loads(raw)
                content = out["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content)
            if return_text:
                return content
            m = re.search(r"\{.*\}", content, re.S)
            return json.loads(m.group(0)) if m else {"note": content}
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3.0 * (attempt + 1))
    raise RuntimeError(f"{image_path}: {last}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", choices=sorted(VENDORS), required=True)
    ap.add_argument("--model", default=None, help="override the vendor's default model name")
    ap.add_argument("--kit", default="audits/human")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    vendor = dict(VENDORS[args.vendor])
    if args.model:
        vendor["model"] = args.model
    key = os.environ.get(vendor["key"], "")
    if not key:
        print(f"set {vendor['key']} first", file=sys.stderr)
        return 2
    rows = list(csv.DictReader(open(os.path.join(args.kit, "labels.csv"), encoding="utf-8")))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done = {}
    if os.path.exists(args.out):
        done = {r["id"]: r for r in csv.DictReader(open(args.out, encoding="utf-8"))}
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            iid, stratum = r["id"], r["stratum"]
            if iid in done and any(done[iid].get(c) for c in COLS[2:]):
                w.writerow(done[iid]); fh.flush()
                continue
            img = os.path.join(args.kit, "img", f"{iid}_{stratum}.png")
            runs_path = os.path.join(args.kit, "img", f"{iid}_runs.txt")
            runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else "(none)"
            task = TASK_TESTABLE.format(runs=runs[:6000]) if stratum == "testable" else TASK_NOBAR
            text = PROMPT.format(task=task, keys=", ".join(KEYS[stratum]))
            try:
                ans = ask(vendor, key, img, text)
            except Exception as exc:  # noqa: BLE001
                print(f"  {iid} failed: {exc}", flush=True)
                ans = {"note": f"failed: {exc}"}
            row = {"id": iid, "stratum": stratum}
            for c in COLS[2:]:
                v = ans.get(c, "")
                row[c] = str(v).strip() if v is not None else ""
            w.writerow(row); fh.flush()
            print(f"  {iid} {stratum:9s} bold_ok={row['bold_ok']} winner={row['winner_mean']} runner={row['runner_mean']}", flush=True)
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
