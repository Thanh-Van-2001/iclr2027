"""Prose diagnostics for an academic manuscript.

Two problems are worth separating.

The first is *disclosure*: ICLR 2027 requires an AI use statement, so there is
nothing to hide and no reason to try.  Concealment is against policy and, given
that reviewers now read hundreds of machine-drafted submissions a season, it
does not work anyway.

The second is *quality*, and that is what this module is for.  Text drafted by a
language model has recognisable habits: a vocabulary that spiked in the
literature after 2022, a fondness for three-part lists, hedges stacked on
hedges, and — most tellingly — sentences of unnervingly uniform length.  None of
these is a moral failing.  They are simply the marks of prose that nobody has
yet taken responsibility for, and reviewers read them as a signal that the
science underneath was not owned either.

The checks below are advisory.  They point at sentences; a human decides.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import statistics
import sys
from typing import Iterable, Optional

# --------------------------------------------------------------------------
# lexicon
# --------------------------------------------------------------------------

# Words whose relative frequency in scientific abstracts rose sharply after
# late 2022.  Each entry maps the tell to a plainer alternative.  The point is
# not that these words are forbidden -- "crucial" is a fine English word -- but
# that a draft containing eight of them was not written by a person choosing
# each one.
LLM_LEXICON: dict[str, str] = {
    "delve": "examine, study",
    "delves": "examines",
    "delving": "examining",
    "intricate": "complex, or just delete it",
    "intricacies": "details",
    "pivotal": "central, or delete",
    "realm": "area, field",
    "showcase": "show, demonstrate",
    "showcases": "shows",
    "showcasing": "showing",
    "underscore": "emphasise, show",
    "underscores": "shows",
    "underscoring": "showing",
    "meticulous": "careful, or delete",
    "meticulously": "carefully",
    "nuanced": "specific, or delete",
    "seamless": "delete",
    "seamlessly": "delete",
    "testament": "evidence",
    "tapestry": "delete",
    "harness": "use",
    "harnessing": "using",
    "foster": "encourage, support",
    "fostering": "supporting",
    "garner": "attract, receive",
    "garnered": "received",
    "myriad": "many",
    "plethora": "many",
    "landscape": "literature, field (when used metaphorically)",
    "paramount": "essential",
    "leverage": "use",
    "leveraging": "using",
    "leverages": "uses",
    "unleash": "delete",
    "unlock": "delete",
    "revolutionize": "change",
    "revolutionary": "delete",
    "groundbreaking": "delete",
    "cutting-edge": "recent, state-of-the-art",
    "game-changer": "delete",
    "holistic": "overall, or be specific",
    "multifaceted": "delete, or name the facets",
    "robustly": "delete or quantify",
    "notably": "delete",
    "importantly": "delete",
    "crucially": "delete",
    "furthermore": "also, and",
    "moreover": "also",
    "additionally": "also",
}

# Phrases that read as filler in a nine-page paper where every line is contested.
LLM_PHRASES: dict[str, str] = {
    r"\bin the realm of\b": "in",
    r"\bit is worth noting that\b": "delete; just state it",
    r"\bit is important to note that\b": "delete; just state it",
    r"\bplays? a (?:pivotal|crucial|vital|key|significant) role\b": "name the mechanism instead",
    r"\bsheds? light on\b": "shows, explains",
    r"\bpaves? the way\b": "delete",
    r"\bin recent years,\b": "delete, or give the actual date",
    r"\bwith the advent of\b": "since",
    r"\bin today'?s (?:rapidly )?(?:evolving|changing)\b": "delete",
    r"\ba wide range of\b": "give the number",
    r"\bvast (?:amounts?|array)\b": "give the number",
    r"\bstate-of-the-art performance\b": "say on which benchmark, by how much",
    r"\bwe propose a novel\b": "'novel' is the reviewer's word, not yours",
    r"\bto the best of our knowledge,? (?:this is )?the first\b": "risky claim; be sure, and cite what you searched",
    r"\bcomprehensive (?:experiments|evaluation|analysis)\b": "say how many, on what",
    r"\bextensive experiments\b": "say how many",
    r"\bnot only .{3,60} but also\b": "split into two sentences",
    r"\bhowever,? it is\b": "tighten",
    r"\bin conclusion,\b": "delete in a paper",
    r"\bfirstly\b": "first",
    r"\bsecondly\b": "second",
    r"\blastly\b": "finally",
    r"\bcan potentially\b": "one hedge is enough",
    r"\bmay possibly\b": "one hedge is enough",
    r"\bmight potentially\b": "one hedge is enough",
    r"\bwe believe that\b": "either show it or drop it",
    r"\bsignificantly (?:improve|outperform|better)": "'significant' implies a test; run one or reword",
}

# Rules from the writing advice that has actually survived: state the problem
# before the method, own the claim, delete the intensifier.
STYLE_RULES: dict[str, str] = {
    r"\bvery\b": "delete; find a stronger word",
    r"\bquite\b": "delete",
    r"\brather\b(?! than)": "delete",
    r"\bsimply\b": "delete",
    r"\bobviously\b": "if it were obvious you would not say so",
    r"\bclearly\b": "if it were clear you would not say so",
    r"\beasily\b": "delete",
    r"\bmassive(?:ly)?\b": "quantify",
    r"\bhuge(?:ly)?\b": "quantify",
    r"\bdramatic(?:ally)?\b": "quantify",
}

SEVERITY = {"lexicon": "style", "phrase": "style", "rule": "nit", "structure": "structure", "metric": "metric"}


# --------------------------------------------------------------------------
# TeX handling
# --------------------------------------------------------------------------

_STRIP = [
    (re.compile(r"(?<!\\)%.*$", re.MULTILINE), " "),
    (re.compile(r"\\begin\{(equation|align|gather|split|array|cases|tabular|figure|table|lstlisting|verbatim)\*?\}.*?\\end\{\1\*?\}", re.DOTALL), " "),
    (re.compile(r"\$\$.*?\$\$", re.DOTALL), " MATH "),
    (re.compile(r"\$[^$]*\$"), " MATH "),
    (re.compile(r"\\(?:cite|citep|citet|citealp|ref|autoref|eqref|label|input|include|includegraphics|usepackage|documentclass|bibliography|bibliographystyle)\*?(?:\[[^\]]*\])*\{[^}]*\}"), " CITE "),
    (re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])*"), " "),
    (re.compile(r"[{}]"), " "),
]

_ABBREV = ["e.g.", "i.e.", "et al.", "cf.", "vs.", "Fig.", "Eq.", "Sec.", "App.", "Tab.", "Refs.", "approx.", "Dr.", "Prof."]


def detex(text: str) -> str:
    out = text
    for pat, rep in _STRIP:
        out = pat.sub(rep, out)
    return re.sub(r"[ \t]+", " ", out)


def sentences(text: str) -> list[tuple[int, str]]:
    """Split into ``(char_offset, sentence)`` pairs."""
    protected = text
    for ab in _ABBREV:
        protected = protected.replace(ab, ab.replace(".", "\u0001"))
    out, start = [], 0
    for m in re.finditer(r"(?<=[.!?])[\s\n]+(?=[A-Z(])", protected):
        piece = protected[start:m.start()].replace("\u0001", ".").strip()
        if piece:
            out.append((start, piece))
        start = m.end()
    tail = protected[start:].replace("\u0001", ".").strip()
    if tail:
        out.append((start, tail))
    return out


# --------------------------------------------------------------------------
# findings
# --------------------------------------------------------------------------

@dataclasses.dataclass
class StyleFinding:
    kind: str
    severity: str
    tex_file: str
    line: int
    match: str
    suggestion: str
    context: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _ctx(text: str, start: int, end: int, pad: int = 45) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - pad):end + pad]).strip()


def lint_text(raw: str, filename: str) -> list[StyleFinding]:
    body = detex(raw)
    findings: list[StyleFinding] = []

    for word, suggestion in LLM_LEXICON.items():
        for m in re.finditer(rf"\b{re.escape(word)}\b", body, re.IGNORECASE):
            findings.append(StyleFinding("lexicon", SEVERITY["lexicon"], filename,
                                         _line_of(body, m.start()), m.group(0), suggestion,
                                         _ctx(body, m.start(), m.end())))
    for pat, suggestion in LLM_PHRASES.items():
        for m in re.finditer(pat, body, re.IGNORECASE):
            findings.append(StyleFinding("phrase", SEVERITY["phrase"], filename,
                                         _line_of(body, m.start()), m.group(0), suggestion,
                                         _ctx(body, m.start(), m.end())))
    for pat, suggestion in STYLE_RULES.items():
        for m in re.finditer(pat, body, re.IGNORECASE):
            findings.append(StyleFinding("rule", SEVERITY["rule"], filename,
                                         _line_of(body, m.start()), m.group(0), suggestion,
                                         _ctx(body, m.start(), m.end())))

    # Three-item lists are the model's favourite rhythm.  A few are fine; a
    # paragraph built from them is a tell.
    for m in re.finditer(r"\b\w+, \w+,? and \w+\b", body):
        findings.append(StyleFinding("structure", SEVERITY["structure"], filename,
                                     _line_of(body, m.start()), m.group(0),
                                     "tricolon; vary the rhythm if these cluster",
                                     _ctx(body, m.start(), m.end(), 30)))
    for m in re.finditer(r"\s—\s|\s--\s", body):
        findings.append(StyleFinding("structure", "nit", filename, _line_of(body, m.start()),
                                     m.group(0).strip(), "em-dash; two per page is plenty",
                                     _ctx(body, m.start(), m.end(), 35)))
    return findings


# --------------------------------------------------------------------------
# rhythm metrics
# --------------------------------------------------------------------------

def rhythm(raw: str) -> dict:
    """Measure sentence-length variation.

    Human academic prose alternates long explanatory sentences with short
    declarative ones; a coefficient of variation below roughly 0.4 means every
    sentence is the same length, which reads as machine-flat. The threshold is
    a heuristic, not a test statistic -- treat it as a prompt to reread, and
    check the histogram rather than the single number.
    """
    body = detex(raw)
    lengths = [len(s.split()) for _, s in sentences(body) if len(s.split()) > 2]
    if len(lengths) < 8:
        return {"n_sentences": len(lengths), "note": "too few sentences to judge"}
    mean = statistics.mean(lengths)
    sd = statistics.pstdev(lengths)
    return {
        "n_sentences": len(lengths),
        "mean_words": round(mean, 1),
        "sd_words": round(sd, 1),
        "coef_variation": round(sd / mean, 3) if mean else 0.0,
        "pct_short_under_10": round(100 * sum(1 for x in lengths if x < 10) / len(lengths), 1),
        "pct_long_over_35": round(100 * sum(1 for x in lengths if x > 35) / len(lengths), 1),
        "longest": max(lengths),
        "flat_warning": (sd / mean) < 0.40 if mean else False,
    }


def lint_files(paths: Iterable[str]) -> tuple[list[StyleFinding], dict]:
    findings: list[StyleFinding] = []
    joined = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            raw = fh.read()
        joined.append(raw)
        findings.extend(lint_text(raw, os.path.basename(p)))
    return findings, rhythm("\n".join(joined))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Diagnose machine-flat prose in a LaTeX manuscript.")
    ap.add_argument("tex", nargs="+")
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--max-style", type=int, default=25,
                    help="fail if more than this many style-level findings remain")
    args = ap.parse_args(argv)

    findings, rhy = lint_files(args.tex)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"findings": [f.to_dict() for f in findings], "rhythm": rhy}, fh, indent=2)

    by_kind: dict[str, list[StyleFinding]] = {}
    for f in findings:
        by_kind.setdefault(f.kind, []).append(f)

    print("PROSE REPORT\n")
    print(f"  rhythm: {rhy}\n")
    for kind in ("lexicon", "phrase", "structure", "rule"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        print(f"  {kind} ({len(items)})")
        counts: dict[str, int] = {}
        for f in items:
            counts[f.match.lower()] = counts.get(f.match.lower(), 0) + 1
        for match, n in sorted(counts.items(), key=lambda kv: -kv[1])[:14]:
            ex = next(f for f in items if f.match.lower() == match)
            print(f"     {n:>3}x {match:<28} -> {ex.suggestion}")
            print(f"          {ex.tex_file}:{ex.line}  ...{ex.context[:110]}...")
        print()

    hard = len(by_kind.get("lexicon", [])) + len(by_kind.get("phrase", []))
    if rhy.get("flat_warning"):
        print("  WARNING: sentence lengths are unusually uniform; vary them.")
    if hard > args.max_style:
        print(f"\nPROSE CHECK FAILED: {hard} lexicon/phrase findings exceed the budget of {args.max_style}.")
        return 1
    print(f"\nPROSE CHECK PASSED: {hard} lexicon/phrase findings, budget {args.max_style}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
