"""Adversarial reviews of the manuscript by relay models (a substitute for
the workflow reviewers when those are unavailable): each brief is sent with
the paper text and the pre-registered plan to a model, which answers with a
rating and a list of objections. Reviews go to out/swevo/reviews_relay/.

Usage: RELAY_URL=... RELAY_API_KEY=... python swevo/review_relay.py [--model cc/claude-sonnet-5] [--tag r4]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "aamas"))
import classify  # noqa: E402

BRIEFS = {
    "methodologist": "You are one of the authors of the field's statistical-methodology guides (the Derrac, Garcia, Carrasco, LaTorre line). You care whether the measurements support the claims. Attack whether each instrument's precision is established, whether the corrected census is a repair or a second model correcting a model, whether the abstract's numbers are the body's, whether the two-literatures split is an artefact of the classifier, and whether the verdict cross-tab shows what it is said to show.",
    "statistician": "You are a statistician who reviews for methods journals. Attack the inference: Welch's t on printed summaries at an equal run count, the bootstrap over few effective clusters, the Kish count, the Holm rows, the heavy-tail argument, the impossible-pair check, the kappa, and every place where the paper says 'bound', 'floor', 'valid' or 'conservative'. Cite the sentence.",
    "practitioner": "You are a senior metaheuristics researcher who has proposed algorithms, run CEC suites at 51 runs and reported Wilcoxon and Friedman tables. Read this as a member of the community being audited. Is the audit fair? Does a per-cell Welch test of a bold mean say anything about the paper's aggregate claim? Would the recommendations change what you do? What would make you dismiss the paper?",
    "editor": "You are an associate editor of Swarm and Evolutionary Computation with forty minutes. Read the title, abstract, tables, section openings and the limitations. Is the manuscript readable, is its length justified, does the abstract match the body, is the corpus deviation acceptable, and what is your decision (reject / major revision / minor revision / accept) and why?",
}

CONTEXT = """You are reviewing a submission to Swarm and Evolutionary Computation (Elsevier; single-blind; acceptance well under 20 percent). Rate on a 1-10 scale where 6 is a weak accept after major revision and 5 a reject-and-resubmit. Do not inflate. Be specific to this paper; generic advice is useless. Every objection needs a short stable id and a severity (blocking / major / minor) and the concrete edit that would fix it. Quote the passage you object to. You cannot open the run records; judge from the text, and say so where a number would need checking.

Answer as JSON only: {"rating": <number>, "confidence": <1-5>, "summary": "...", "strengths": "...", "objections": [{"id": "...", "severity": "blocking|major|minor", "objection": "...", "what_would_fix_it": "..."}], "questions_to_authors": "...", "would_champion": true|false}
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--tag", default="relay")
    ap.add_argument("--paper", default="out/swevo/paper_text.txt")
    ap.add_argument("--plan", default="swevo/PLAN.md")
    args = ap.parse_args(argv)
    key = os.environ.get("RELAY_API_KEY")
    if not key or not os.environ.get("RELAY_URL"):
        sys.exit("set RELAY_URL and RELAY_API_KEY")
    if args.model:
        classify.MODEL = args.model
    paper = open(args.paper, encoding="utf-8").read()
    plan = open(args.plan, encoding="utf-8").read()
    os.makedirs("out/swevo/reviews_relay", exist_ok=True)
    for name, brief in BRIEFS.items():
        out = f"out/swevo/reviews_relay/{args.tag}_{name}_{(args.model or classify.MODEL).split('/')[-1]}.json"
        if os.path.exists(out):
            continue
        prompt = brief + "\n\n" + CONTEXT + "\n\nPRE-REGISTERED PLAN:\n" + plan + "\n\nMANUSCRIPT (text extracted from the PDF; tables read row by row; line numbers removed):\n" + paper
        raw = classify.ask(prompt, key, max_tokens=8000, timeout=900)
        s = raw.strip()
        if "```" in s:
            s = max(s.split("```"), key=len)
            s = s[4:] if s.startswith("json") else s
        i, j = s.find("{"), s.rfind("}")
        try:
            d = json.loads(s[i:j + 1])
        except Exception:  # noqa: BLE001
            d = {"parse_error": raw[:2000]}
        d["model"] = args.model or classify.MODEL
        d["brief"] = name
        json.dump(d, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print(name, d.get("rating"), len(d.get("objections", [])), "objections", flush=True)


if __name__ == "__main__":
    main()
