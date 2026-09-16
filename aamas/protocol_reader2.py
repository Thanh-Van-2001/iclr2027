"""The evaluation-protocol reading, extended: a language model reads the full
text of every learning-labelled paper and every paper that highlights a rate,
and reports the evaluation episodes, seeds, whether the episodes are sampled
or a fixed set of instances, the environments, single- or multi-agent, the
codebase, whether the compared methods share evaluation episodes, and what
the printed deviation is over. The first reading (protocol_reader.py, six
fields) is kept; this one adds fields and covers more papers.

Usage: RELAY_URL=... RELAY_API_KEY=... python aamas/protocol_reader2.py [--papers ids.txt]
"""
import argparse
import csv
import json
import os
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from classify import ask  # noqa: E402
from make_all_aamas import rate_like  # noqa: E402

OUT = "out/aamas/protocol_reader2.json"

PROMPT = """You are reading a paper from the AAMAS conference to record its evaluation protocol. Answer from the text only; never guess a number the paper does not state.

Questions:
1. eval_episodes: over how many evaluation (test) episodes, rollouts, games, tasks or instances is a reported win rate / success rate / return averaged, per seed or per model? Integer, or null if the paper never says. Do not use a training-time number (patience windows, number of training episodes, replay sizes).
2. eval_sentence: the sentence that states it (verbatim), or "".
3. episodes_kind: are those evaluation episodes SAMPLED (random starts, random opponents, random maps or seeds drawn afresh, so that two methods see different draws) or a FIXED set of instances, tasks, problems or prompts that every method is evaluated on once each? "sampled", "fixed_instances", or "unsure".
4. seeds: how many random seeds or independent training runs does the paper report results over? Integer or null.
5. seed_sentence: the sentence that states it, or "".
6. rate_is_mean_over_seeds: are reported rates means over seeds of per-seed rates ("yes"), a pooled rate over all episodes of all seeds ("no"), or not stated ("unsure")?
7. checkpoint: are evaluation numbers taken at the final checkpoint ("final"), the best checkpoint ("best"), or not stated ("unsure")?
8. environments: the benchmark environments or datasets the main results use, as a list from this vocabulary where it fits and the paper's own name otherwise: "SMAC", "SMACv2", "GRF" (Google Research Football), "MPE", "MaMuJoCo", "Hanabi", "Overcooked", "MeltingPot", "StarCraft-other", "MuJoCo/DMC single-agent", "D4RL", "Atari", "gridworld/MiniGrid", "traffic (SUMO/CityFlow)", "real robots", "LLM benchmark: <name>", "matrix/normal-form games", "auction/market simulation", "other: <name>".
9. agents: does the evaluated system control one agent ("single"), several ("multi"), or both settings appear ("both")?
10. framework: the codebase the experiments run on if one is named (e.g. "PyMARL", "EPyMARL", "MARLlib", "BenchMARL", "JaxMARL", "MAPPO official", "CleanRL", "Stable-Baselines3", "RLlib"), else "".
11. follows_standard_setup: does the paper say it follows the standard or default evaluation setup of a named benchmark or codebase WITHOUT stating the number of evaluation episodes itself? Give the sentence, or "".
12. shares_eval_episodes: are the compared methods evaluated on the same evaluation episodes, seeds or instances ("yes"), on independent draws ("no"), or not stated ("unsure")?
13. sd_over: when the paper prints a mean with a +/- or a deviation, is that deviation taken over seeds ("seeds"), over pooled evaluation episodes ("episodes"), stated as a standard error ("se"), a confidence interval ("ci"), or not stated ("unsure")?
14. sd_sentence: the sentence that says what the deviation is, or "".

Answer as JSON only, every key present:
{"eval_episodes": <int or null>, "eval_sentence": "...", "episodes_kind": "sampled|fixed_instances|unsure", "seeds": <int or null>, "seed_sentence": "...", "rate_is_mean_over_seeds": "yes|no|unsure", "checkpoint": "final|best|unsure", "environments": ["..."], "agents": "single|multi|both", "framework": "...", "follows_standard_setup": "...", "shares_eval_episodes": "yes|no|unsure", "sd_over": "seeds|episodes|se|ci|unsure", "sd_sentence": "..."}

Paper text:
"""


def paper_set():
    cs = json.load(open("out/aamas/analysis.json", encoding="utf-8"))["_comparisons"]
    rate = {c["paper"] for c in cs if rate_like(c)}
    learning = {r["id"] for r in csv.DictReader(open("out/aamas/communities.csv", encoding="utf-8"))
                if r["label"] == "learning"}
    testable = {c["paper"] for c in cs if c.get("test")}
    return sorted(rate | learning | testable), rate, learning, testable


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default=None, help="file of paper ids, one per line (default: rate, learning and testable papers)")
    args = ap.parse_args(argv)
    key = os.environ.get("RELAY_API_KEY")
    if not key or not os.environ.get("RELAY_URL"):
        sys.exit("set RELAY_URL and RELAY_API_KEY")
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    recs = {}
    for line in open("data/extracted_aamas.jsonl", encoding="utf-8"):
        r = json.loads(line)
        recs[r["id"]] = r
    if args.papers:
        papers = [l.strip() for l in open(args.papers, encoding="utf-8") if l.strip()]
    else:
        papers, rate, learning, testable = paper_set()
        print(len(papers), "papers:", len(rate), "rate,", len(learning), "learning,", len(testable), "testable;", len(done), "already read")
    for pid in papers:
        if pid in done and "parse_error" not in done[pid]:
            continue
        r = recs[pid]
        path = os.path.join("data", "corpus", f"{r['venue']}{r['year']}_{pid}.pdf")
        text = " ".join(pg.get_text() for pg in fitz.open(path))[:60000]
        # the quoted sentences make long answers; 2000 tokens truncated 60 of 324
        raw = ask(PROMPT + text, key, max_tokens=6000)
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
        json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(pid[:8], d.get("eval_episodes"), d.get("episodes_kind"), d.get("seeds"), d.get("environments"), flush=True)
    print("done", len(done))


if __name__ == "__main__":
    main()
