"""Assign each AAMAS paper to one community from its title and first page.

The proceedings do not print the area a paper was submitted to, so a language
model reads the title and the first page (abstract, keywords, introduction
opening) and picks one label from a fixed list. The prompt, the model name and
every answer are released; a hand-checkable sample is drawn by `--sample`.

Usage: RELAY_API_KEY=... python aamas/classify.py [--out out/aamas/communities.csv]
"""
import csv
import glob
import json
import os
import sys
import time
import urllib.request

import fitz

LABELS = [
    ("learning", "reinforcement learning, multi-agent RL, imitation, bandits, learning in games"),
    ("game_theory_social_choice", "game theory, mechanism design, auctions, voting, fair division, matching, cooperative games"),
    ("llm_agents", "LLM-based agents, generative or agentic AI, language models as agents"),
    ("simulation", "agent-based modelling and simulation of societies, markets, epidemics, traffic"),
    ("planning_search", "planning, scheduling, search, optimisation, path finding, constraint solving"),
    ("reasoning_norms", "logic, knowledge representation, argumentation, norms, ethics, trust, formal verification"),
    ("robotics_hai", "robotics, control, human-agent or human-robot interaction"),
    ("other", "anything else, including systems and engineering of agent platforms"),
]
PROMPT = """You are classifying a paper from the AAMAS conference into exactly one community.
Labels (answer with the label id only):
{labels}

Also say whether the paper reports quantitative experimental results in tables (yes/no) as far as the first page suggests.

Answer as JSON: {{"label": "<id>", "confidence": "high|medium|low", "tables_expected": "yes|no|unsure"}}

Title: {title}

First page:
{page}
"""

URL = os.environ.get("RELAY_URL", "")
MODEL = os.environ.get("RELAY_MODEL", "gemini/gemini-3.1-pro-preview")


def ask(text: str, key: str, retries: int = 4, max_tokens: int = 2000, timeout: int = 180) -> str:
    body = {"model": MODEL, "temperature": 0, "stream": False, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": text}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode()
            if raw.lstrip().startswith("data:"):
                parts = []
                for line in raw.splitlines():
                    if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                        for ch in json.loads(line[5:]).get("choices", []):
                            parts.append(ch.get("delta", {}).get("content") or "")
                return "".join(parts)
            return json.loads(raw)["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"relay failed: {last}")


def parse(answer: str) -> dict:
    s = answer.strip()
    if "```" in s:
        s = s.split("```")[1]
        s = s[4:] if s.startswith("json") else s
    i, j = s.find("{"), s.rfind("}")
    try:
        d = json.loads(s[i:j + 1])
    except Exception:  # noqa: BLE001
        return {"label": "parse_error", "confidence": "", "tables_expected": "", "raw": answer[:200]}
    if d.get("label") not in {k for k, _ in LABELS}:
        d["label"] = "parse_error"
        d["raw"] = answer[:200]
    return d


def main():
    key = os.environ.get("RELAY_API_KEY")
    if not key or not URL:
        sys.exit("set RELAY_URL (an OpenAI-compatible chat completions endpoint) and RELAY_API_KEY")
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "out/aamas/communities.csv"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    done = {}
    if os.path.exists(out_path):
        with open(out_path, encoding="utf-8", newline="") as fh:
            done = {r["id"]: r for r in csv.DictReader(fh)}
    fields = ["id", "venue_year", "title", "label", "confidence", "tables_expected", "raw"]
    fh = open(out_path, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=fields)
    if not done:
        w.writeheader()
    labels = "\n".join(f"- {k}: {v}" for k, v in LABELS)
    titles = {}
    for fn in glob.glob("data/extracted_aamas*.jsonl"):
        with open(fn, encoding="utf-8") as fh_:
            for line in fh_:
                r = json.loads(line)
                titles[r["id"]] = r["title"]
    pdfs = sorted(glob.glob("data/corpus/AAMAS*.pdf"))
    n = 0
    for p in pdfs:
        stem = os.path.basename(p)[:-4]
        venue_year, pid = stem.split("_", 1)
        if pid in done:
            continue
        doc = fitz.open(p)
        page = doc[0].get_text()
        title = titles.get(pid) or page.strip().split("\n")[0][:200]
        try:
            d = parse(ask(PROMPT.format(labels=labels, title=title, page=page[:3500]), key))
        except RuntimeError as exc:
            print(pid, exc)
            continue
        row = {"id": pid, "venue_year": venue_year, "title": title, "label": d.get("label", ""),
               "confidence": d.get("confidence", ""), "tables_expected": d.get("tables_expected", ""),
               "raw": d.get("raw", "")}
        w.writerow(row)
        fh.flush()
        n += 1
        if n % 25 == 0:
            print(n, "classified")
    print("done", n, "new;", len(done) + n, "total")


if __name__ == "__main__":
    main()
