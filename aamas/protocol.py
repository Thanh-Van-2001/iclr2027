"""Evaluation-protocol statements in the AAMAS corpus.

For every cached AAMAS PDF, find the sentences that state how many evaluation
(test) episodes a reported number averages over, and how many seeds. The
output is one row per paper with the counts and the sentences they came from,
so that any row can be checked against the paper.

Usage: python aamas/protocol.py [--corpus data/corpus] [--out out/aamas/protocol.json]
"""
import glob
import json
import os
import re
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100}
NUM = r"(\d{1,5}|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|fifty|hundred)"
# "averaged over 32 evaluation episodes", "32 test episodes", "evaluated for 100 episodes",
# "over 10 evaluation rollouts", "100 evaluation runs"
EPISODE = re.compile(
    rf"(?i)\b{NUM}\s+(?:independent\s+|random\s+|different\s+)?(?:evaluation|eval\.?|test(?:ing)?|held-?out)\s+"
    rf"(?:episodes?|rollouts?|trajectories|games?|matches|trials?|runs?)\b"
    rf"|\b(?:evaluat\w+|test\w*)\s+(?:the\s+\w+\s+)?(?:over|on|for|across|with|using)\s+{NUM}\s+"
    rf"(?:independent\s+|random\s+|different\s+)?(?:episodes?|rollouts?|games?|matches|trials?)\b")
SEED = re.compile(rf"(?i)\b{NUM}\s+(?:independent\s+|random\s+|different\s+)?(?:seeds?|random seeds?|independent runs?|training runs?)\b"
                  rf"|\b(?:over|across|with|using|averaged over)\s+{NUM}\s+(?:seeds?|runs?)\b")


# "averaged over 50 episodes", "return over 32 episodes", "evaluated across 500
# episodes": a count of episodes under an averaging or evaluating verb.
EPISODE_BROAD = re.compile(rf"(?i)\b(?:over|across|on|for)\s+{NUM}\s+(?:\w+\s+)?(?:episodes?|rollouts?|games)\b")
EPISODE_GATE = re.compile(r"(?i)evaluat|test|averag|\bmean\b|return|measur|determin|comput|report|success|win")


def _n(tok: str):
    tok = tok.lower()
    return WORDS.get(tok) or (int(tok) if tok.isdigit() else None)


def sentences(text: str):
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"\s+", " ", text)
    return re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text)


def scan(pdf_path: str, max_pages: int = 40) -> dict:
    doc = fitz.open(pdf_path)
    text = "\n".join(doc[i].get_text() for i in range(min(len(doc), max_pages)))
    eps, seeds = [], []
    for s in sentences(text):
        found = False
        for m in EPISODE.finditer(s):
            n = _n(m.group(1) or m.group(2))
            if n and 2 <= n <= 100000:
                eps.append({"n": n, "sentence": s[:300]})
                found = True
        if not found and EPISODE_GATE.search(s):
            for m in EPISODE_BROAD.finditer(s):
                n = _n(m.group(1))
                if n and 2 <= n <= 100000:
                    eps.append({"n": n, "sentence": s[:300], "broad": True})
        for m in SEED.finditer(s):
            n = _n(m.group(1) or m.group(2))
            if n and 2 <= n <= 1000:
                seeds.append({"n": n, "sentence": s[:300]})
    return {"n_pages": len(doc),
            "eval_episodes": min((e["n"] for e in eps), default=None),
            "eval_episode_statements": eps[:8],
            "seeds": min((e["n"] for e in seeds), default=None),
            "seed_statements": seeds[:8]}


def main():
    corpus = sys.argv[sys.argv.index("--corpus") + 1] if "--corpus" in sys.argv else "data/corpus"
    out_path = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else "out/aamas/protocol.json"
    rows = {}
    for p in sorted(glob.glob(os.path.join(corpus, "AAMAS*.pdf"))):
        stem = os.path.basename(p)[:-4]
        venue_year, pid = stem.split("_", 1)
        try:
            rows[pid] = {"venue_year": venue_year, **scan(p)}
        except Exception as exc:  # noqa: BLE001
            rows[pid] = {"venue_year": venue_year, "error": str(exc)}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    ok = [r for r in rows.values() if "error" not in r]
    print(len(rows), "papers;", sum(1 for r in ok if r["eval_episodes"]), "state evaluation episodes;",
          sum(1 for r in ok if r["seeds"]), "state seeds")


if __name__ == "__main__":
    main()
