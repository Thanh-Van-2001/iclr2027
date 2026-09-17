"""Assign each corpus paper to one kind from its title and abstract: does it
propose a new or modified optimizer, compare existing ones, apply one to a
problem, or survey the field. The prompt, the model name and every answer
are released; a second vendor labels a random hundred (swevo/classify.py
--sample 100 --out ...) so the agreement can be reported.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/classify.py [--out out/swevo/kinds.csv]
"""
import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "aamas"))
from classify import ask  # noqa: E402  (the relay call, same as the AAMAS classifier)

LABELS = [
    ("new_optimizer", "proposes a new metaheuristic, or a modified / improved / hybrid variant of one, and evaluates it against other optimizers"),
    ("comparison", "compares or benchmarks existing optimizers, or studies their behaviour, without proposing a new one as the main contribution"),
    ("application", "applies one or more metaheuristics to a domain problem (engineering design, scheduling, energy, medicine, machine learning tuning ...) and the contribution is the application"),
    ("survey_theory", "a survey, review, tutorial, or a theoretical or methodological paper without a new optimizer"),
    ("other", "anything else, or not about metaheuristics at all"),
]
PROMPT = """You are classifying a paper that mentions a metaheuristic into exactly one kind.
Labels (answer with the label id only):
{labels}

Also say: is the proposed or studied optimizer named after a natural, animal, human or physical metaphor (e.g. grey wolf, whale, hippopotamus, political, chemical) rather than a mechanism (yes/no/none)? Does the abstract mention benchmark functions or a CEC test suite (yes/no)?

Answer as JSON: {{"label": "<id>", "confidence": "high|medium|low", "metaphor_named": "yes|no|none", "benchmark_suite": "yes|no"}}

Title: {title}

Abstract:
{abstract}
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="out/swevo/index.json")
    ap.add_argument("--out", default="out/swevo/kinds.csv")
    ap.add_argument("--sample", type=int, default=0, help="label a random n papers only (second labeller)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--journal", default=None, help="restrict to one journal of the index")
    ap.add_argument("--shard", default=None, help="k/n: every n-th paper from k, for parallel workers writing separate files")
    args = ap.parse_args(argv)
    key = os.environ.get("RELAY_API_KEY")
    if not key or not os.environ.get("RELAY_URL"):
        sys.exit("set RELAY_URL and RELAY_API_KEY")
    recs = json.load(open(args.index, encoding="utf-8"))
    if args.journal:
        recs = [r for r in recs if r["journal"] == args.journal]
    if args.sample:
        import random
        recs = random.Random(args.seed).sample(recs, args.sample)
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        recs = recs[k::n]
    done = {}
    if os.path.exists(args.out):
        with open(args.out, encoding="utf-8", newline="") as fh:
            done = {r["id"]: r for r in csv.DictReader(fh)}
    fields = ["id", "journal", "year", "title", "label", "confidence", "metaphor_named", "benchmark_suite", "raw"]
    fh = open(args.out, "a", encoding="utf-8", newline="")
    w = csv.DictWriter(fh, fieldnames=fields)
    if not done:
        w.writeheader()
    labels = "\n".join(f"- {k}: {v}" for k, v in LABELS)
    n = 0
    for r in recs:
        if r["id"] in done:
            continue
        raw = ask(PROMPT.format(labels=labels, title=r["title"], abstract=r.get("abstract", "")[:3000]), key)
        s = raw.strip()
        if "```" in s:
            s = s.split("```")[1]
            s = s[4:] if s.startswith("json") else s
        i, j = s.find("{"), s.rfind("}")
        try:
            d = json.loads(s[i:j + 1])
        except Exception:  # noqa: BLE001
            d = {}
        lab = d.get("label") if d.get("label") in {k for k, _ in LABELS} else "parse_error"
        w.writerow({"id": r["id"], "journal": r["journal"], "year": r["year"], "title": r["title"], "label": lab,
                    "confidence": d.get("confidence", ""), "metaphor_named": d.get("metaphor_named", ""),
                    "benchmark_suite": d.get("benchmark_suite", ""), "raw": raw[:200] if lab == "parse_error" else ""})
        fh.flush()
        n += 1
        if n % 50 == 0:
            print(n, flush=True)
    print("labelled", n, "->", args.out)


if __name__ == "__main__":
    main()
