"""ICLR 2027 desk-rejection checks.

A desk rejection is the cheapest possible way to lose a year of work, and every
cause of one is mechanically detectable.  This module checks the submission
against the rules stated in the ICLR 2027 Author Guidelines and AI Policy for
Authors, retrieved 2026-09-09:

* main text of nine pages or fewer at submission; references and appendices do
  not count toward that limit;
* full anonymity -- "any paper where author identity is revealed in either the
  main text or the supplementary material will be desk rejected";
* the official style files, unmodified;
* a mandatory AI use statement, which does not count toward the page limit.

Run it before every submission, and again after the last edit.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
from typing import Optional

MAIN_TEXT_PAGE_LIMIT = 9          # submission; rises to 10 for camera-ready
PAGE_LABEL = "lastmainpage"       # \label{lastmainpage} goes just before \bibliography

# sha256 of the files as shipped in the official iclr2027.zip.  Any difference
# means the style was edited, which reviewers are asked to report.
OFFICIAL_STYLE_FILES = ("iclr2027_conference.sty", "iclr2027_conference.bst", "fancyhdr.sty", "natbib.sty")

LEVEL_FAIL = "FAIL"
LEVEL_WARN = "WARN"
LEVEL_OK = "OK"


@dataclasses.dataclass
class Check:
    name: str
    level: str
    detail: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --------------------------------------------------------------------------
# individual checks
# --------------------------------------------------------------------------

def check_style_files(paper_dir: str, reference_dir: Optional[str]) -> list[Check]:
    out = []
    for name in OFFICIAL_STYLE_FILES:
        here = os.path.join(paper_dir, name)
        if not os.path.exists(here):
            out.append(Check(f"style:{name}", LEVEL_WARN, "not present in the build directory"))
            continue
        if not reference_dir:
            out.append(Check(f"style:{name}", LEVEL_WARN, "present, but no pristine copy to compare against"))
            continue
        ref = os.path.join(reference_dir, name)
        if not os.path.exists(ref):
            out.append(Check(f"style:{name}", LEVEL_WARN, "no pristine copy to compare against"))
        elif _sha(here) == _sha(ref):
            out.append(Check(f"style:{name}", LEVEL_OK, "byte-identical to the official file"))
        else:
            out.append(Check(f"style:{name}", LEVEL_FAIL,
                             "differs from the official file; editing the style is grounds for rejection"))
    return out


def check_anonymity(tex_paths: list[str]) -> list[Check]:
    out: list[Check] = []
    joined = "\n".join(_read(p) for p in tex_paths)
    uncommented = re.sub(r"(?<!\\)%.*$", "", joined, flags=re.MULTILINE)

    if re.search(r"^\s*\\iclrfinalcopy", uncommented, re.MULTILINE):
        out.append(Check("anonymity:finalcopy", LEVEL_FAIL,
                         "\\iclrfinalcopy is active, which prints author names; comment it out for submission"))
    else:
        out.append(Check("anonymity:finalcopy", LEVEL_OK, "\\iclrfinalcopy is not active"))

    ack = re.search(r"\\(?:sub)*section\*?\{\s*Acknowledg", uncommented, re.IGNORECASE)
    out.append(Check("anonymity:acknowledgements",
                     LEVEL_FAIL if ack else LEVEL_OK,
                     "an acknowledgements section identifies the authors; remove it until camera-ready"
                     if ack else "no acknowledgements section"))

    leaks = []
    for pat, why in [
        (r"https?://github\.com/[\w.-]+/[\w.-]+", "a GitHub URL names its owner; use an anonymised mirror"),
        (r"https?://(?:www\.)?(?:gitlab|bitbucket)\.com/[\w.-]+", "a repository URL names its owner"),
        (r"[\w.+-]+@[\w-]+\.[\w.]+", "an email address"),
        (r"\\thanks\{", "a \\thanks footnote"),
        (r"(?i)\b(?:funded|supported)\s+by\s+(?:the\s+)?[A-Z]", "a funding acknowledgement"),
        (r"(?i)\bour\s+(?:lab|group|university|institute)\b", "a self-identifying phrase"),
    ]:
        for m in re.finditer(pat, uncommented):
            leaks.append(f"{why}: {m.group(0)[:70]}")
    if leaks:
        out.append(Check("anonymity:leaks", LEVEL_FAIL, "; ".join(sorted(set(leaks))[:8])))
    else:
        out.append(Check("anonymity:leaks", LEVEL_OK, "no identifying strings found in the LaTeX source"))
    return out


def check_required_sections(tex_paths: list[str]) -> list[Check]:
    joined = re.sub(r"(?<!\\)%.*$", "", "\n".join(_read(p) for p in tex_paths), flags=re.MULTILINE)
    out = []
    for label, pattern, level, note in [
        ("AI use statement", r"\\(?:sub)*section\*?\{[^}]*AI\s+use\s+statement", LEVEL_FAIL,
         "required by the ICLR 2027 AI Policy for Authors and does not count toward the page limit"),
        ("Reproducibility statement", r"\\(?:sub)*section\*?\{[^}]*Reproducibility", LEVEL_WARN,
         "recommended; its absence is a visible gap to a reviewer"),
        ("Ethics statement", r"\\(?:sub)*section\*?\{[^}]*Ethics", LEVEL_WARN,
         "recommended where the work raises Code of Ethics questions"),
    ]:
        present = re.search(pattern, joined, re.IGNORECASE) is not None
        out.append(Check(f"section:{label}", LEVEL_OK if present else level,
                         "present" if present else f"missing -- {note}"))
    return out


def check_page_limit(aux_path: str, pdf_pages: Optional[int]) -> list[Check]:
    """Read the page number of ``\\label{lastmainpage}`` out of the .aux file."""
    if not os.path.exists(aux_path):
        return [Check("pages:main", LEVEL_WARN, f"{os.path.basename(aux_path)} not found; build the paper first")]
    aux = _read(aux_path)
    m = re.search(r"\\newlabel\{" + PAGE_LABEL + r"\}\{\{[^}]*\}\{(\d+)\}", aux)
    if not m:
        return [Check("pages:main", LEVEL_WARN,
                      f"no \\label{{{PAGE_LABEL}}} found; place it immediately before the bibliography "
                      "so the main-text length can be measured")]
    last = int(m.group(1))
    level = LEVEL_OK if last <= MAIN_TEXT_PAGE_LIMIT else LEVEL_FAIL
    detail = f"main text ends on page {last} (limit {MAIN_TEXT_PAGE_LIMIT})"
    if pdf_pages:
        detail += f"; {pdf_pages} pages in total including references and appendices"
    return [Check("pages:main", level, detail)]


def check_build_log(log_path: str) -> list[Check]:
    if not os.path.exists(log_path):
        return [Check("build:log", LEVEL_WARN, "no .log file; build the paper first")]
    log = _read(log_path)
    out = []

    errors = re.findall(r"^! (.+)$", log, re.MULTILINE)
    out.append(Check("build:errors", LEVEL_FAIL if errors else LEVEL_OK,
                     "; ".join(errors[:4]) if errors else "compiled without errors"))

    undefined = set(re.findall(r"Citation `([^']+)' (?:on page \d+ )?undefined", log))
    out.append(Check("build:citations", LEVEL_FAIL if undefined else LEVEL_OK,
                     f"undefined citations: {sorted(undefined)[:8]}" if undefined else "every citation resolves"))

    badref = set(re.findall(r"Reference `([^']+)' (?:on page \d+ )?undefined", log))
    out.append(Check("build:references", LEVEL_FAIL if badref else LEVEL_OK,
                     f"undefined labels: {sorted(badref)[:8]}" if badref else "every \\ref resolves"))

    overfull = re.findall(r"Overfull \\hbox \(([\d.]+)pt too wide\)", log)
    bad = [float(x) for x in overfull if float(x) > 5.0]
    out.append(Check("build:overfull", LEVEL_WARN if bad else LEVEL_OK,
                     f"{len(bad)} overfull boxes wider than 5pt (worst {max(bad):.1f}pt); text runs into the margin"
                     if bad else "no serious overfull boxes"))
    return out


def check_layout_hacks(tex_paths: list[str]) -> list[Check]:
    """Catch the tricks that reviewers are explicitly asked to look for."""
    joined = re.sub(r"(?<!\\)%.*$", "", "\n".join(_read(p) for p in tex_paths), flags=re.MULTILINE)
    hits = []
    for pat, why in [
        (r"\\(?:textheight|textwidth|topmargin|oddsidemargin|evensidemargin|footskip|baselineskip)\s*=?\s*[-\d]", "geometry redefined"),
        (r"\\usepackage(?:\[[^\]]*\])?\{geometry\}", "the geometry package overrides the ICLR page layout"),
        (r"\\vspace\{\s*-\s*[\d.]+\s*(?:cm|in|em|ex|pt|\\baselineskip)", "negative \\vspace used to claw back space"),
        (r"\\setlength\{\\(?:abovedisplayskip|belowdisplayskip|textfloatsep|floatsep|intextsep)\}", "float or display spacing shrunk"),
        (r"\\fontsize\{[\d.]+\}", "explicit font size change"),
        (r"\\(?:small|footnotesize|scriptsize|tiny)\s*\\begin\{(?:abstract|document)\}", "body text shrunk"),
        (r"\\renewcommand\{?\\baselinestretch\}?", "line spacing changed"),
    ]:
        if re.search(pat, joined):
            hits.append(why)
    return [Check("layout:hacks", LEVEL_WARN if hits else LEVEL_OK,
                  "; ".join(hits) if hits else "no page-layout manipulation detected")]


def check_placeholders(tex_paths: list[str]) -> list[Check]:
    joined = "\n".join(_read(p) for p in tex_paths)
    pats = [r"\bTODO\b", r"\bTBD\b", r"\bFIXME\b", r"\bXXX\b", r"\[CITATION\]", r"\bLorem ipsum\b",
            r"\bplaceholder\b", r"\?\?\?", r"\bAnonymous et al\b"]
    hits = [m.group(0) for p in pats for m in re.finditer(p, joined, re.IGNORECASE)]
    return [Check("content:placeholders", LEVEL_FAIL if hits else LEVEL_OK,
                  f"{len(hits)} placeholder marker(s): {sorted(set(hits))[:6]}" if hits
                  else "no placeholder markers left in the source")]


def check_pdf_metadata(pdf_path: str) -> list[Check]:
    """A PDF that carries the author's name in its metadata breaks anonymity."""
    if not os.path.exists(pdf_path):
        return [Check("pdf:metadata", LEVEL_WARN, "no PDF; build the paper first")]
    with open(pdf_path, "rb") as fh:
        head = fh.read(400_000)
    leaks = []
    for field in (b"/Author", b"/Creator", b"/Title", b"/Subject", b"/Keywords"):
        for m in re.finditer(re.escape(field) + rb"\s*\(([^)]{0,160})\)", head):
            val = m.group(1).decode("latin-1", errors="replace").strip()
            if val and not re.fullmatch(r"(?i)(LaTeX.*|pdfTeX.*|TeX.*|)", val):
                leaks.append(f"{field.decode()}={val[:60]}")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", head))
    checks = [Check("pdf:metadata", LEVEL_FAIL if leaks else LEVEL_OK,
                    "; ".join(leaks) if leaks else "no identifying PDF metadata")]
    if pages:
        checks.append(Check("pdf:pages", LEVEL_OK, f"{pages} pages detected in the PDF object table"))
    return checks


def count_pdf_pages(pdf_path: str) -> Optional[int]:
    try:
        out = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True, timeout=20)
        m = re.search(r"Pages:\s+(\d+)", out.stdout)
        if m:
            return int(m.group(1))
    except (OSError, subprocess.SubprocessError):
        pass
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as fh:
            data = fh.read()
        n = len(re.findall(rb"/Type\s*/Page[^s]", data))
        return n or None
    return None


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def run_all(paper_dir: str, main_tex: str, reference_dir: Optional[str] = None) -> list[Check]:
    stem = os.path.splitext(os.path.basename(main_tex))[0]
    tex_paths = sorted(
        os.path.join(paper_dir, f) for f in os.listdir(paper_dir)
        if f.endswith(".tex") and not f.startswith("math_commands")
    )
    pdf = os.path.join(paper_dir, stem + ".pdf")
    checks: list[Check] = []
    checks += check_build_log(os.path.join(paper_dir, stem + ".log"))
    checks += check_page_limit(os.path.join(paper_dir, stem + ".aux"), count_pdf_pages(pdf))
    checks += check_anonymity(tex_paths)
    checks += check_required_sections(tex_paths)
    checks += check_style_files(paper_dir, reference_dir)
    checks += check_layout_hacks(tex_paths)
    checks += check_placeholders(tex_paths)
    checks += check_pdf_metadata(pdf)
    return checks


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Check an ICLR 2027 submission for desk-rejection risks.")
    ap.add_argument("--dir", required=True, help="directory holding the paper build")
    ap.add_argument("--main", default="main.tex", help="main .tex filename")
    ap.add_argument("--reference-style-dir", default=None,
                    help="directory holding the pristine official style files")
    ap.add_argument("--json", dest="json_out")
    args = ap.parse_args(argv)

    checks = run_all(args.dir, args.main, args.reference_style_dir)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump([c.to_dict() for c in checks], fh, indent=2)

    fails = [c for c in checks if c.level == LEVEL_FAIL]
    warns = [c for c in checks if c.level == LEVEL_WARN]
    print("ICLR 2027 SUBMISSION CHECK\n")
    for c in checks:
        print(f"  [{c.level:4}] {c.name:34} {c.detail}")
    print()
    if fails:
        print(f"NOT SUBMITTABLE: {len(fails)} blocking issue(s), {len(warns)} warning(s).")
        return 1
    print(f"SUBMITTABLE: no blocking issues, {len(warns)} warning(s) to review.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
