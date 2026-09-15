"""A language model reads the full text of every paper that holds a rate
comparison and reports its evaluation protocol: the number of evaluation
episodes a reported rate averages over, the number of seeds, whether the
rate is a mean over seeds, and the sentences that say so. This validates the
regular expressions of protocol.py on exactly the papers Section 6 uses.

Usage: RELAY_URL=... RELAY_API_KEY=... python aamas/protocol_reader.py
"""
import json
import os
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from classify import ask, parse  # noqa: E402
from make_all_aamas import rate_like  # noqa: E402

PROMPT = """You are reading a multi-agent systems paper to record its evaluation protocol. Answer from the text only.

Questions:
1. eval_episodes: over how many evaluation (test) episodes, rollouts or games is a reported win rate / success rate / return averaged, per seed or per model? Give the integer, or null if the paper never says. Do not use a training-time number (patience windows, number of training episodes, replay sizes).
2. eval_sentence: the sentence that states it (verbatim), or "".
3. seeds: how many random seeds or independent training runs does the paper report results over? Integer or null.
4. seed_sentence: the sentence that states it, or "".
5. rate_is_mean_over_seeds: are the reported rates means over seeds of per-seed rates ("yes"), a pooled rate over all episodes of all seeds ("no"), or not stated ("unsure")?
6. checkpoint: are evaluation numbers taken at the final checkpoint ("final"), the best checkpoint ("best"), or not stated ("unsure")?

Answer as JSON only: {"eval_episodes": <int or null>, "eval_sentence": "...", "seeds": <int or null>, "seed_sentence": "...", "rate_is_mean_over_seeds": "yes|no|unsure", "checkpoint": "final|best|unsure"}

Paper text:
"""


def main():
    key = os.environ.get("RELAY_API_KEY")
    if not key or not os.environ.get("RELAY_URL"):
        sys.exit("set RELAY_URL and RELAY_API_KEY")
    out_path = "out/aamas/protocol_reader.json"
    done = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    recs = {}
    for line in open("data/extracted_aamas.jsonl", encoding="utf-8"):
        r = json.loads(line)
        recs[r["id"]] = r
    cs = json.load(open("out/aamas/analysis.json", encoding="utf-8"))["_comparisons"]
    papers = sorted({c["paper"] for c in cs if rate_like(c)})
    print(len(papers), "papers with a rate comparison;", len(done), "already read")
    for pid in papers:
        if pid in done:
            continue
        r = recs[pid]
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{pid}.pdf")
        text = " ".join(pg.get_text() for pg in fitz.open(path))[:60000]
        raw = ask(PROMPT + text, key)
        s = raw.strip()
        if "```" in s:
            s = s.split("```")[1]
            s = s[4:] if s.startswith("json") else s
        i, j = s.find("{"), s.rfind("}")
        try:
            d = json.loads(s[i:j + 1])
        except Exception:  # noqa: BLE001
            d = {"parse_error": raw[:300]}
        d["title"] = r["title"]
        done[pid] = d
        json.dump(done, open(out_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(pid[:8], d.get("eval_episodes"), d.get("seeds"), d.get("rate_is_mean_over_seeds"))
    print("done", len(done))


if __name__ == "__main__":
    main()
