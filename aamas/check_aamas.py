"""The AAMAS paper's gate: build, page limit, citations, numbers, prose.

The ICLR desk-rejection module does not apply; the AAMAS rules checked here
are the ones in the submission instructions: anonymous sigconf class, main
text within eight pages (references excluded), no author names.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from paperengine import provenance, refcheck, style  # noqa: E402

D = "paper/aamas"
MAIN = "main.tex"
PAGE_LIMIT = 8
# Literals that are legitimately hand-written: the CC licence version (4.0), the
# conference ordinal (26th), the CCS concept ids and significance (10010147...,
# 500) from the ACM template, and the version in a model's name (Gemini 3.1).
# 32 is PyMARL's default evaluation-episode count, a design parameter of the
# lookup table rather than a measurement.
ALLOW = sys.argv[1] if len(sys.argv) > 1 else "4.0,26,10010147.10010919,10010177,500,3.1,32"


def build() -> bool:
    subprocess.run(["latexmk", "-C", MAIN], cwd=D, capture_output=True, text=True)
    r = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", MAIN],
                       cwd=D, capture_output=True, text=True)
    open(os.path.join(D, "build.log"), "w", encoding="utf-8").write(r.stdout + r.stderr)
    return r.returncode == 0


def page_check() -> tuple:
    import fitz
    doc = fitz.open(os.path.join(D, "main.pdf"))
    last_text_page = None
    for i in range(len(doc)):
        t = doc[i].get_text()
        m = re.search(r"(?im)^\s*references\s*$", t)
        if m or "\n[1] " in t:
            # the main text ends on the previous page when the references
            # heading is the first thing on this one (after the running head)
            before = t[:m.start()] if m else t[:t.find("\n[1] ")]
            body = [ln for ln in before.splitlines()[2:] if ln.strip()]
            last_text_page = i + 1 if body else i
            break
    return len(doc), last_text_page


def abstract_words() -> int:
    """Words in the abstract as the PDF prints it; the call asks for 100 to 300."""
    import fitz
    t = fitz.open(os.path.join(D, "main.pdf"))[0].get_text()
    i, j = t.find("Abstract"), t.find("CCS Concepts")
    return len(t[i + len("Abstract"):j].split()) if 0 <= i < j else -1


def main() -> int:
    ok = {}
    print("1. BUILD")
    ok["build"] = build()
    print("  compiled" if ok["build"] else "  FAILED (see paper/aamas/build.log)")
    if not ok["build"]:
        return 1
    n, ref_page = page_check()
    print(f"2. PAGES: {n} pages, main text ends on page {ref_page} (limit {PAGE_LIMIT}; references unlimited)")
    ok["pages"] = ref_page is not None and ref_page <= PAGE_LIMIT
    aw = abstract_words()
    print(f"   abstract: {aw} words (100 to 300)")
    ok["abstract"] = 100 <= aw <= 300
    src = open(os.path.join(D, MAIN), encoding="utf-8").read()
    ok["anonymous"] = bool(re.search(r"\\documentclass\[[^\]]*anonymous", src))
    print("3. ANONYMOUS:", "yes" if ok["anonymous"] else "NO")
    print("4. CITATIONS")
    ok["citations"] = refcheck.main([os.path.join(D, "refs.bib"), "--json", "out/aamas/refcheck.json"]) == 0
    print("5. NUMBERS")
    args = [os.path.join(D, MAIN)] + (["--allow", ALLOW] if ALLOW else []) + ["--json", "out/aamas/numbers.json"]
    ok["numbers"] = provenance.main(args) == 0
    print("6. PROSE")
    ok["prose"] = style.main([os.path.join(D, MAIN), "--json", "out/aamas/style.json", "--max-style", "25"]) == 0
    print("\nVERDICT")
    for k, v in ok.items():
        print(f"  {'pass' if v else 'FAIL':<5} {k}")
    return 0 if all(ok.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
