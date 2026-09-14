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
ALLOW = sys.argv[1] if len(sys.argv) > 1 else ""


def build() -> bool:
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
        if re.search(r"^\s*REFERENCES\s*$", t, re.M):
            last_text_page = i + 1
            break
    return len(doc), last_text_page


def main() -> int:
    ok = {}
    print("1. BUILD")
    ok["build"] = build()
    print("  compiled" if ok["build"] else "  FAILED (see paper/aamas/build.log)")
    if not ok["build"]:
        return 1
    n, ref_page = page_check()
    print(f"2. PAGES: {n} pages, references begin on page {ref_page} (main text limit {PAGE_LIMIT})")
    ok["pages"] = ref_page is not None and ref_page <= PAGE_LIMIT
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
