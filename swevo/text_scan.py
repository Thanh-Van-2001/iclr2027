"""Text scans over the corpus PDFs for what the metaheuristics convention
says a paper should state: the number of independent runs, the statistical
test it reports (Wilcoxon, Friedman, t-test ...), the +/=/- convention, the
benchmark suite (CEC year, BBOB), whether the title proposes an optimizer,
whether that optimizer is a metaphor from the EC Bestiary, and which
methodology papers it cites. Regular expressions only; every match is kept
with its sentence so a reader can check it.

Usage: python swevo/text_scan.py [--corpus data/corpus_oa] [--index out/swevo/index.json]
"""
import argparse
import collections
import json
import os
import re

import fitz

RUNS = re.compile(r"\b(\d{1,4})\s+(?:independent\s+|separate\s+|random\s+)?(?:runs|trials|repetitions|executions|independent experiments)\b", re.I)
RUNS_WORDS = {"ten": 10, "twenty": 20, "thirty": 30, "fifty": 50, "hundred": 100, "five": 5, "fifteen": 15, "twenty-five": 25, "twenty five": 25}
RUNS_WORDY = re.compile(r"\b(ten|twenty|thirty|fifty|hundred|five|fifteen|twenty-five|twenty five)\s+(?:independent\s+)?(?:runs|trials|repetitions)\b", re.I)
TESTS = {
    "wilcoxon": re.compile(r"wilcoxon", re.I),
    "friedman": re.compile(r"friedman", re.I),
    "t_test": re.compile(r"\bt[- ]test|student'?s?\s+t\b", re.I),
    "mann_whitney": re.compile(r"mann[- ]whitney", re.I),
    "kruskal": re.compile(r"kruskal", re.I),
    "anova": re.compile(r"\banova\b", re.I),
    "p_value": re.compile(r"\bp[- ]?values?\b|\bp\s*[<≤]\s*0\.0", re.I),
    "bonferroni_holm": re.compile(r"bonferroni|holm|nemenyi|post[- ]hoc", re.I),
    "plus_minus_equal": re.compile(r"[\(\[]?\+\s*/\s*[=≈]\s*/\s*[−\-][\)\]]?|[\(\[]\+/=/-[\)\]]|\bwin/tie/loss|\bwins?/ties?/loss", re.I),
}
SUITES = {
    "cec": re.compile(r"\bCEC[\s'’-]?(20)?(05|13|14|15|17|19|20|21|22|24|2005|2013|2014|2015|2017|2019|2020|2021|2022|2024)\b"),
    "bbob": re.compile(r"\bBBOB\b|\bCOCO\b"),
    "classical_functions": re.compile(r"\b(sphere|rastrigin|rosenbrock|ackley|griewank|schwefel)\b", re.I),
}
OPTIMIZER_TITLE = re.compile(r"\b(optimi[sz]er|optimi[sz]ation algorithm|search algorithm|metaheuristic|algorithm)\b", re.I)
NOVEL_TITLE = re.compile(r"\b(novel|new|improved|enhanced|modified|hybrid|adaptive)\b", re.I)
METHODOLOGY = {
    "derrac2011": r"practical tutorial on the use of nonparametric statistical tests",
    "garcia2009": r"study on the use of non-parametric tests for analyzing the evolutionary algorithms",
    "garcia2010": r"advanced nonparametric tests for multiple comparisons in the design of experiments",
    "sorensen2015": r"metaheuristics.{0,10}the metaphor exposed",
    "aranha2022": r"metaphor-based metaheuristics, a call for action",
    "camacho2022": r"exposing the grey wolf, moth-flame, whale, firefly, bat",
    "bartz2020": r"benchmarking in optimization: best practice and open issues",
    "beiranvand2017": r"best practices for comparing optimization algorithms",
    "kendall2016": r"good laboratory practice for optimization research",
    "hansen_coco": r"coco: a platform for comparing continuous optimizers",
    "wolpert_nfl": r"no free lunch theorems for optimization",
}
BESTIARY = "out/swevo/ec_bestiary.json"


def _sentence(text: str, pos: int, width: int = 160) -> str:
    a = max(0, text.rfind(".", 0, pos) + 1)
    b = text.find(".", pos)
    b = len(text) if b < 0 else b + 1
    return re.sub(r"\s+", " ", text[max(a, pos - width):min(b, pos + width)]).strip()


def _singular(name: str) -> str:
    """Crude singular: wolves -> wolf, flies -> fly, walruses -> walrus."""
    if name.endswith("ves"):
        return name[:-3] + "f"
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith(("uses", "shes", "ches", "xes")):
        return name[:-2]
    if name.endswith(("us", "ss")):
        return name
    return name[:-1] if name.endswith("s") else name


# names that are ordinary words of the field and would match everything
STOP = {"hybrid", "swarm", "vehicle", "memetic", "cultural", "genetic", "evolution", "search", "group",
        "social", "team", "human", "parallel", "random", "society", "population", "colony", "learning",
        "teaching", "neural", "gravity", "election", "strategy", "game", "leader", "sport", "war", "state",
        "system", "network", "field", "cloud", "wave", "flow", "energy", "force", "path", "point", "model",
        "regular", "binary", "artificial", "chaotic", "quantum", "improved", "modified", "particle", "vibrating",
        "plant", "water", "forest", "world", "design", "method", "dynamic", "behavior", "theory", "transfer", "molecule"}


def metaphor_patterns() -> list:
    """One pattern per bestiary family ("Whales"), matching the family word or
    any of its specific names ("beluga", "killer whale") near an optimizer word."""
    if not os.path.exists(BESTIARY):
        return []
    fam = collections.defaultdict(set)
    for e in json.load(open(BESTIARY, encoding="utf-8")):
        parts = [re.sub(r"\s*\(.*?\)|'s", "", x).strip().lower() for x in e["metaphor"].split(":")]
        family = parts[0]
        words = set()
        for x in parts:
            sing = _singular(x)
            if len(sing) >= 4 and sing not in STOP:
                words.add(sing)
        fam[family] |= words
    out = []
    for family, words in sorted(fam.items()):
        if not words:
            continue
        alt = "|".join(re.escape(w) + "(s|es)?" for w in sorted(words, key=len, reverse=True))
        out.append((family, re.compile(r"\b(" + alt + r")\b.{0,40}\b(optimi[sz]|algorithm|search)", re.I)))
    return out


def scan(path: str, title: str, abstract: str, patterns: list) -> dict:
    doc = fitz.open(path)
    text = " ".join(p.get_text() for p in doc)
    body = text[:400000]
    refs_start = max(body.rfind("\nReferences"), body.rfind("\nREFERENCES"), int(len(body) * 0.85))
    main = body[:refs_start]
    runs = collections.Counter()
    for m in RUNS.finditer(main):
        n = int(m.group(1))
        if 2 <= n <= 10000:
            runs[n] += 1
    for m in RUNS_WORDY.finditer(main):
        runs[RUNS_WORDS[m.group(1).lower()]] += 1
    run_sent = _sentence(main, RUNS.search(main).start()) if RUNS.search(main) else ""
    tests = {k: len(rx.findall(main)) for k, rx in TESTS.items()}
    test_sents = {k: _sentence(main, rx.search(main).start()) for k, rx in TESTS.items() if rx.search(main)}
    suites = {k: bool(rx.search(main)) for k, rx in SUITES.items()}
    cec_years = sorted({m.group(0)[-2:] for m in SUITES["cec"].finditer(main)})
    head = f"{title} {abstract}"
    metaphors = [name for name, rx in patterns if rx.search(head)]
    cites = {k: bool(re.search(pat, body, re.I)) for k, pat in METHODOLOGY.items()}
    return {"pages": len(doc), "runs": dict(runs.most_common(6)), "run_modal": runs.most_common(1)[0][0] if runs else None,
            "run_sentence": run_sent[:300], "tests": tests, "test_sentences": {k: v[:300] for k, v in test_sents.items()},
            "any_test": any(tests[k] for k in ("wilcoxon", "friedman", "t_test", "mann_whitney", "kruskal", "anova")),
            "suites": suites, "cec_years": cec_years,
            "title_proposes_algorithm": bool(OPTIMIZER_TITLE.search(title)), "title_novelty_word": bool(NOVEL_TITLE.search(title)),
            "metaphors_in_title_or_abstract": metaphors, "cites": cites}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="data/corpus_oa")
    ap.add_argument("--index", default="out/swevo/index.json")
    ap.add_argument("--out", default="out/swevo/text_scan.json")
    args = ap.parse_args(argv)
    recs = json.load(open(args.index, encoding="utf-8"))
    done = json.load(open(args.out, encoding="utf-8")) if os.path.exists(args.out) else {}
    patterns = metaphor_patterns()
    n = 0
    for r in recs:
        path = os.path.join(args.corpus, f"OA{r['year']}_{r['id']}.pdf")
        if r["id"] in done or not os.path.exists(path):
            continue
        try:
            done[r["id"]] = scan(path, r["title"], r.get("abstract", ""), patterns)
        except Exception as exc:  # noqa: BLE001
            done[r["id"]] = {"error": str(exc)[:120]}
        n += 1
        if n % 100 == 0:
            json.dump(done, open(args.out, "w", encoding="utf-8"), indent=0)
            print(n, flush=True)
    json.dump(done, open(args.out, "w", encoding="utf-8"), indent=0)
    ok = [v for v in done.values() if "error" not in v]
    print(len(done), "papers scanned;", sum(1 for v in ok if v["run_modal"]), "state a run count;",
          sum(1 for v in ok if v["any_test"]), "name a statistical test;", sum(1 for v in ok if v["metaphors_in_title_or_abstract"]), "name a bestiary metaphor")


if __name__ == "__main__":
    main()
