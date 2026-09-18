"""The statistical-test reading: a language model reads the full text of
every paper with a testable comparison (and, optionally, a random sample of
the rest) and records the run count, the summary statistics printed, which
statistical test the paper reports, on what quantity, paired or not, at
what significance level, and whether the test's verdict is printed beside
the tables (+/=/- markers, p-values, ranks). The prompt, the model name and
every answer are released.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/test_reader.py [--papers ids.txt] [--sample 100 --seed 11]
"""
import argparse
import json
import os
import random
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "aamas"))
from classify import ask  # noqa: E402

OUT = "out/swevo/test_reader.json"

PROMPT = """You are reading a paper that uses or proposes a metaheuristic optimizer, to record how its experiments are reported. Answer from the text only; never guess a number the paper does not state.

Questions:
1. runs: how many independent runs (repetitions, trials, executions) of each optimizer produce the reported summary statistics? Integer, or null if never stated.
2. runs_sentence: the sentence that states it (verbatim), or "".
3. summary: which summary statistics do the results tables print, as a list from: "mean", "std", "best", "worst", "median", "se", "ci", "rank", "other".
4. std_layout: where the standard deviation (or other dispersion) sits relative to the mean in the main results tables: "same_cell" (a +/- or parenthesis in the cell), "separate_row" (a Mean row and a Std row), "separate_column" (Mean and Std columns), "none" (no dispersion printed), or "unsure".
5. test: the statistical test(s) the paper reports on the comparison of optimizers, as a list from: "wilcoxon_signed_rank", "wilcoxon_rank_sum", "mann_whitney", "friedman", "friedman_aligned", "quade", "nemenyi", "holm", "bonferroni", "t_test", "anova", "kruskal_wallis", "other", "none".
6. test_sentence: the sentence that names the test, or "".
7. test_on: what the test compares: "per_run_values" (the N run results of two optimizers on one function), "per_function_means" (one mean per function, paired across functions), "ranks", "unsure", or "none".
8. paired: does the text say the test is paired / signed-rank / on matched runs ("yes"), unpaired ("no"), or not stated ("unsure")?
9. alpha: the significance level the paper uses (e.g. 0.05), or null.
10. markers: does the paper print a per-cell verdict of the test beside the results (+/=/- symbols, w/t/l counts, p-values per function, or a significance mark)? "yes" or "no".
11. markers_sentence: the sentence that explains the markers, or "".
12. bold_rule: what the paper says bold marks in its tables ("best mean", "best value", "statistically best", "not stated"), quoting the sentence in bold_sentence.
13. bold_sentence: the sentence, or "".
14. benchmark: the benchmark suite(s) of the main results: "CEC2005", "CEC2013", "CEC2014", "CEC2017", "CEC2019", "CEC2020", "CEC2021", "CEC2022", "BBOB", "classical" (sphere, Rastrigin ... without a CEC year), "engineering_design", "application_data", "other", as a list.
15. budget: the stopping criterion per run (e.g. "500 iterations", "10000*D evaluations"), or "".

Answer as JSON only, every key present:
{"runs": <int or null>, "runs_sentence": "...", "summary": ["..."], "std_layout": "same_cell|separate_row|separate_column|none|unsure", "test": ["..."], "test_sentence": "...", "test_on": "per_run_values|per_function_means|ranks|unsure|none", "paired": "yes|no|unsure", "alpha": <number or null>, "markers": "yes|no", "markers_sentence": "...", "bold_rule": "...", "bold_sentence": "...", "benchmark": ["..."], "budget": "..."}

Paper text:
"""


def paper_set(analysis: str = "out/swevo/analysis.json") -> list:
    cs = json.load(open(analysis, encoding="utf-8"))["_comparisons"]
    return sorted({c["paper"] for c in cs if c.get("test")})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--papers", default=None, help="file of paper ids, one per line (default: the papers with a testable comparison)")
    ap.add_argument("--sample", type=int, default=0, help="add a random n of the other parsed papers")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--extracted", default=os.environ.get("SWEVO_EXTRACTED", "data/extracted_oa.jsonl"))
    ap.add_argument("--corpus", default="data/corpus_oa")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--max-chars", type=int, default=400000, help="characters of the paper's text sent to the model (the first submission used 80000, which cut two thirds of the new-optimizer papers)")
    args = ap.parse_args(argv)
    key = os.environ.get("RELAY_API_KEY")
    if not key or not os.environ.get("RELAY_URL"):
        sys.exit("set RELAY_URL and RELAY_API_KEY")
    done = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
    recs = {}
    for line in open(args.extracted, encoding="utf-8"):
        r = json.loads(line)
        recs[r["id"]] = r
    if args.papers:
        papers = [l.strip() for l in open(args.papers, encoding="utf-8") if l.strip()]
    else:
        papers = paper_set()
        print(len(papers), "testable papers;", len(done), "already read")
    tset = set(paper_set()) if not args.papers else set()
    if args.sample:
        rest = sorted(set(recs) - set(papers))
        papers = papers + random.Random(args.seed).sample(rest, min(args.sample, len(rest)))
    for pid in papers:
        if pid in done and "parse_error" not in done[pid]:
            continue
        r = recs[pid]
        path = os.path.join(args.corpus, f"{r['venue']}{r['year']}_{pid}.pdf")
        full = " ".join(pg.get_text() for pg in fitz.open(path))
        text = full[:args.max_chars]
        raw = ask(PROMPT + text, key, max_tokens=4000)
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
        d["model"] = os.environ.get("RELAY_MODEL", "gemini/gemini-3.1-pro-preview")
        d["chars_sent"] = len(text)
        d["chars_total"] = len(full)
        d["in_testable_set"] = (pid in tset) if not args.papers else None
        done[pid] = d
        json.dump(done, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(pid[:8], d.get("runs"), d.get("std_layout"), d.get("test"), d.get("markers"), flush=True)
    print("done", len(done))


if __name__ == "__main__":
    main()
