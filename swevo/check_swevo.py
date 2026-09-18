"""The metaheuristics paper's gate: build, citations, numbers, prose. No
page limit at the journal; the abstract is capped by the journal at 300
words, and the elsarticle class must compile from the frozen macro file.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine import provenance, refcheck, style  # noqa: E402

D = "paper/swevo"
MAIN = "main.tex"
# hand-written literals that are not measurements: the canonical thirty runs, HTTP status codes,
# of the convention, the CEC suite years, the licence version
ALLOW = sys.argv[1] if len(sys.argv) > 1 else "30,2005,2013,2014,2017,2019,2020,2021,2022,4.0,0.05,403,200,3.1"


def build() -> bool:
    subprocess.run(["latexmk", "-C", MAIN], cwd=D, capture_output=True, text=True)
    r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", MAIN],
                       cwd=D, capture_output=True, text=True)
    open(os.path.join(D, "build.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    return r.returncode == 0


def abstract_words() -> int:
    import fitz
    doc = fitz.open(os.path.join(D, "main.pdf"))
    t = "".join(doc[k].get_text() for k in range(min(2, len(doc))))
    i, j = t.find("Abstract"), t.find("Keywords")
    if not (0 <= i < j):
        return -1
    body = t[i + len("Abstract"):j]
    # the corresponding-author footnote is set on the same page and is not part of the abstract
    body = re.sub(r"\S?Corresponding author\..*?\)", " ", body, flags=re.S)
    return len(body.split())


def main() -> int:
    ok = {}
    print("1. BUILD")
    ok["build"] = build()
    print("  compiled" if ok["build"] else "  FAILED (see paper/swevo/build.log)")
    if not ok["build"]:
        return 1
    import fitz
    n = len(fitz.open(os.path.join(D, "main.pdf")))
    aw = abstract_words()
    print(f"2. PAGES: {n}; abstract {aw} words (journal cap 300)")
    ok["abstract"] = 0 < aw <= 300
    print("3. CITATIONS")
    ok["citations"] = refcheck.main([os.path.join(D, "refs.bib"), "--json", "out/swevo/refcheck.json"]) == 0
    print("4. NUMBERS")
    args = [os.path.join(D, MAIN)] + (["--allow", ALLOW] if ALLOW else []) + ["--json", "out/swevo/numbers.json"]
    ok["numbers"] = provenance.main(args) == 0
    print("5. PROSE")
    ok["prose"] = style.main([os.path.join(D, MAIN), "--json", "out/swevo/style.json", "--max-style", "30"]) == 0
    print("\nVERDICT")
    for k, v in ok.items():
        print(f"  {'pass' if v else 'FAIL':<5} {k}")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
