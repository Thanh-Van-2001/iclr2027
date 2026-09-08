"""Citation verification.

The gate this module enforces is simple and absolute: a reference may appear in
the compiled paper only if a public bibliographic API returned a record whose
title matches the ``.bib`` entry.  Nothing is taken on trust from the language
model that drafted the text.

Three checks run, in increasing strength:

``resolve``
    Does the entry carry a DOI or arXiv id that resolves to a real record whose
    title matches?  If the entry carries no identifier, can a title search find
    a record that matches closely enough?

``metadata``
    Do year, authors and venue agree with the upstream record?  Disagreement is
    reported as a warning rather than a failure, because ``.bib`` entries
    legitimately differ (preprint year versus proceedings year, for instance).

``support``
    Does the cited work actually support the sentence that cites it?  This is
    the check that catches the failure mode where a model cites a real paper
    for a claim the paper never makes.  It needs a judge; see
    :func:`check_claim_support`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
from typing import Callable, Iterable, Optional

from . import sources
from .sources import Record, title_similarity

# A title match this close to a hard identifier is accepted outright.
IDENTIFIER_TITLE_THRESHOLD = 0.72
# Without an identifier we demand a much closer match from a title search.
SEARCH_TITLE_THRESHOLD = 0.88

VERDICT_OK = "VERIFIED"
VERDICT_MISMATCH = "MISMATCH"
VERDICT_NOT_FOUND = "NOT_FOUND"
VERDICT_NO_TITLE = "NO_TITLE"
# The APIs never answered, so we know nothing.  Kept distinct from NOT_FOUND:
# reporting a rate limit as a fabricated citation is worse than reporting
# nothing at all.
VERDICT_UNAVAILABLE = "UNAVAILABLE"


# --------------------------------------------------------------------------
# BibTeX parsing
# --------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)


def _strip_braces(value: str) -> str:
    value = value.strip().rstrip(",").strip()
    while len(value) >= 2 and ((value[0] == "{" and value[-1] == "}") or (value[0] == '"' and value[-1] == '"')):
        value = value[1:-1].strip()
    return re.sub(r"\s+", " ", value)


def parse_bib(text: str) -> list[dict]:
    """A tolerant BibTeX reader.

    Full BibTeX is a macro language; papers do not need that, so this reads the
    subset actually produced by reference managers and by us: ``@type{key,
    field = {value},...}`` with balanced braces.
    """
    entries: list[dict] = []
    for m in _ENTRY_RE.finditer(text):
        entry_type, key = m.group(1).lower(), m.group(2)
        i, depth = m.end(), 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[m.end():i - 1]

        fields: dict[str, str] = {}
        j, n = 0, len(body)
        while j < n:
            eq = body.find("=", j)
            if eq == -1:
                break
            name = body[j:eq].strip().strip(",").strip().lower()
            k, d, started = eq + 1, 0, False
            while k < n:
                ch = body[k]
                if ch == "{":
                    d += 1
                    started = True
                elif ch == "}":
                    d -= 1
                elif ch == "," and d == 0 and started:
                    break
                elif ch == "," and d == 0 and body[eq + 1:k].strip():
                    break
                k += 1
            if name:
                fields[name] = _strip_braces(body[eq + 1:k])
            j = k + 1
        entries.append({"type": entry_type, "key": key, **fields})
    return entries


def split_authors(author_field: str) -> list[str]:
    out = []
    for chunk in re.split(r"\s+and\s+", author_field or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "," in chunk:
            last, _, first = chunk.partition(",")
            chunk = f"{first.strip()} {last.strip()}".strip()
        out.append(re.sub(r"\s+", " ", chunk))
    return out


def surname(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", name.strip()) if p]
    return parts[-1].lower() if parts else ""


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

@dataclasses.dataclass
class RefVerdict:
    key: str
    verdict: str
    bib_title: str
    matched_title: Optional[str]
    similarity: float
    identifier: Optional[str]
    source: Optional[str]
    warnings: list[str] = dataclasses.field(default_factory=list)
    evidence_url: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.verdict == VERDICT_OK

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def _extract_identifiers(entry: dict) -> tuple[Optional[str], Optional[str]]:
    doi = entry.get("doi") or None
    if not doi:
        for field in ("url", "note", "howpublished", "eprint"):
            m = sources.DOI_RE.search(entry.get(field, "") or "")
            if m:
                doi = m.group(0).rstrip(".,;")
                break

    arxiv_id = None
    if (entry.get("archiveprefix", "") or entry.get("eprinttype", "")).lower() == "arxiv" and entry.get("eprint"):
        arxiv_id = entry["eprint"].strip()
    if not arxiv_id:
        for field in ("eprint", "url", "journal", "note", "booktitle", "howpublished"):
            blob = entry.get(field, "") or ""
            if "arxiv" in blob.lower() or field == "eprint":
                m = sources.ARXIV_ID_RE.search(blob) or sources.OLD_ARXIV_ID_RE.search(blob)
                if m:
                    arxiv_id = m.group(1)
                    break
    return doi, arxiv_id


def _metadata_warnings(entry: dict, rec: Record) -> list[str]:
    warns: list[str] = []

    bib_year = re.search(r"\d{4}", entry.get("year", "") or "")
    if bib_year and rec.year and abs(int(bib_year.group(0)) - rec.year) > 1:
        warns.append(f"year {bib_year.group(0)} vs upstream {rec.year}")

    bib_authors = split_authors(entry.get("author", ""))
    if bib_authors and rec.authors:
        bib_sur = {surname(a) for a in bib_authors if surname(a)}
        up_sur = {surname(a) for a in rec.authors if surname(a)}
        if bib_sur and up_sur and not (bib_sur & up_sur):
            warns.append(f"no author surname overlap (bib: {sorted(bib_sur)[:3]}, upstream: {sorted(up_sur)[:3]})")
        elif bib_sur and up_sur and len(bib_sur & up_sur) < min(2, len(bib_sur)):
            warns.append("weak author overlap with upstream record")
        if len(bib_authors) != len(rec.authors) and abs(len(bib_authors) - len(rec.authors)) > 1:
            warns.append(f"author count {len(bib_authors)} vs upstream {len(rec.authors)}")

    bib_venue = entry.get("booktitle") or entry.get("journal") or ""
    if bib_venue and rec.venue and title_similarity(bib_venue, rec.venue) < 0.2:
        low = bib_venue.lower()
        if not any(w in low for w in ("arxiv", "preprint", "corr")):
            warns.append(f"venue '{bib_venue[:48]}' vs upstream '{(rec.venue or '')[:48]}'")
    return warns


def verify_entry(entry: dict) -> RefVerdict:
    title = entry.get("title", "").strip()
    key = entry.get("key", "?")
    if not title:
        return RefVerdict(key, VERDICT_NO_TITLE, "", None, 0.0, None, None, ["entry has no title field"])

    doi, arxiv_id = _extract_identifiers(entry)

    if doi or arxiv_id:
        ident = f"arXiv:{arxiv_id}" if arxiv_id else f"doi:{doi}"
        try:
            rec = sources.lookup_by_identifier(doi=doi, arxiv_id=arxiv_id)
        except sources.SourceUnavailable as exc:
            return RefVerdict(key, VERDICT_UNAVAILABLE, title, None, 0.0, ident, None,
                              [f"no bibliographic API answered, so this entry is unchecked, not disproved ({exc})"])
        if rec is None:
            return RefVerdict(key, VERDICT_NOT_FOUND, title, None, 0.0, ident, None,
                              [f"identifier {ident} did not resolve at arXiv/OpenAlex/Crossref/S2"])
        sim = title_similarity(title, rec.title)
        if sim < IDENTIFIER_TITLE_THRESHOLD:
            return RefVerdict(key, VERDICT_MISMATCH, title, rec.title, sim, ident, rec.source,
                              [f"identifier resolves but to a different title (similarity {sim:.2f})"],
                              rec.url)
        return RefVerdict(key, VERDICT_OK, title, rec.title, sim, ident, rec.source,
                          _metadata_warnings(entry, rec), rec.url)

    try:
        candidates = sources.search_all(title, limit=6)
    except sources.SourceUnavailable as exc:
        return RefVerdict(key, VERDICT_UNAVAILABLE, title, None, 0.0, None, None,
                          [f"no bibliographic API answered, so this entry is unchecked, not disproved ({exc})"])
    rec, sim = sources.best_title_match(title, candidates)
    if rec is None or sim < SEARCH_TITLE_THRESHOLD:
        detail = f"closest was '{rec.title[:70]}' at {sim:.2f}" if rec else "no candidates returned"
        return RefVerdict(key, VERDICT_NOT_FOUND, title, rec.title if rec else None, sim, None,
                          rec.source if rec else None,
                          [f"no identifier in entry and title search failed ({detail})"],
                          rec.url if rec else None)
    ident = f"arXiv:{rec.arxiv_id}" if rec.arxiv_id else (f"doi:{rec.doi}" if rec.doi else None)
    warns = _metadata_warnings(entry, rec)
    warns.append(f"entry had no identifier; matched by title search via {rec.source}"
                 + (f", suggest adding {ident}" if ident else ""))
    return RefVerdict(key, VERDICT_OK, title, rec.title, sim, ident, rec.source, warns, rec.url)


def verify_bib(path: str) -> list[RefVerdict]:
    with open(path, "r", encoding="utf-8") as fh:
        entries = parse_bib(fh.read())
    return [verify_entry(e) for e in entries]


# --------------------------------------------------------------------------
# citation-in-context extraction
# --------------------------------------------------------------------------

_CITE_RE = re.compile(r"\\(?:cite|citep|citet|citealp|citeauthor|citeyear)\*?(?:\[[^\]]*\])*\{([^}]+)\}")
_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)


@dataclasses.dataclass
class CitationUse:
    keys: list[str]
    sentence: str
    tex_file: str
    line: int


def extract_citation_uses(tex_paths: Iterable[str]) -> list[CitationUse]:
    """Find every ``\\cite`` and the sentence it sits in."""
    uses: list[CitationUse] = []
    for path in tex_paths:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        text = _COMMENT_RE.sub("", raw)
        # Sentence boundaries, avoiding the obvious abbreviation traps.
        protected = text
        for abbr in ("e.g.", "i.e.", "et al.", "cf.", "vs.", "Fig.", "Eq.", "Sec.", "App.", "Tab."):
            protected = protected.replace(abbr, abbr.replace(".", "\u0001"))
        pieces, start = [], 0
        for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z\\])", protected):
            pieces.append((start, protected[start:m.start()]))
            start = m.end()
        pieces.append((start, protected[start:]))

        for offset, piece in pieces:
            sentence = piece.replace("\u0001", ".").strip()
            if not sentence:
                continue
            keys: list[str] = []
            for cm in _CITE_RE.finditer(sentence):
                keys.extend(k.strip() for k in cm.group(1).split(",") if k.strip())
            if keys:
                uses.append(CitationUse(
                    keys=sorted(set(keys)),
                    sentence=re.sub(r"\s+", " ", sentence),
                    tex_file=os.path.basename(path),
                    line=text.count("\n", 0, offset) + 1,
                ))
    return uses


def check_claim_support(
    uses: list[CitationUse],
    bib_entries: list[dict],
    judge: Callable[[str, str, str], dict],
) -> list[dict]:
    """Ask ``judge`` whether each cited work supports the citing sentence.

    ``judge(sentence, cited_title, cited_abstract)`` must return a dict with at
    least ``{"supports": bool, "reason": str}``.  Wiring an LLM in here is the
    caller's job; keeping the judge injectable is what lets the same code run
    under a subagent, an API call, or a human.
    """
    by_key = {e["key"]: e for e in bib_entries}
    results = []
    for use in uses:
        for key in use.keys:
            entry = by_key.get(key)
            if entry is None:
                results.append({"key": key, "sentence": use.sentence, "tex_file": use.tex_file,
                                "line": use.line, "supports": False,
                                "reason": "cited key is absent from the .bib file"})
                continue
            doi, arxiv_id = _extract_identifiers(entry)
            rec = sources.lookup_by_identifier(doi=doi, arxiv_id=arxiv_id)
            if rec is None:
                cands = sources.search_all(entry.get("title", ""), limit=4)
                rec, sim = sources.best_title_match(entry.get("title", ""), cands)
                if rec is None or sim < SEARCH_TITLE_THRESHOLD:
                    results.append({"key": key, "sentence": use.sentence, "tex_file": use.tex_file,
                                    "line": use.line, "supports": False,
                                    "reason": "could not retrieve the cited work to check support"})
                    continue
            verdict = judge(use.sentence, rec.title, rec.abstract or "")
            results.append({
                "key": key, "sentence": use.sentence, "tex_file": use.tex_file, "line": use.line,
                "cited_title": rec.title, "url": rec.url, **verdict,
            })
    return results


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _report(verdicts: list[RefVerdict], strict: bool) -> int:
    ok = [v for v in verdicts if v.ok]
    unavailable = [v for v in verdicts if v.verdict == VERDICT_UNAVAILABLE]
    bad = [v for v in verdicts if not v.ok and v.verdict != VERDICT_UNAVAILABLE]
    warned = [v for v in ok if v.warnings]

    print(f"checked {len(verdicts)} references: {len(ok)} verified, {len(bad)} failed, "
          f"{len(unavailable)} unchecked, {len(warned)} with warnings\n")
    for v in unavailable:
        print(f"  UNCHECKED {v.key} -- {v.warnings[0] if v.warnings else 'source unavailable'}")
    if unavailable:
        print("  (re-run once the APIs recover; these are not evidence of a bad citation)\n")
    for v in bad:
        print(f"  FAIL [{v.verdict}] {v.key}")
        print(f"       bib title : {v.bib_title[:90]}")
        if v.matched_title:
            print(f"       closest   : {v.matched_title[:90]} ({v.similarity:.2f})")
        for w in v.warnings:
            print(f"       - {w}")
    if bad and warned:
        print()
    for v in warned:
        print(f"  WARN {v.key} ({v.source}, sim {v.similarity:.2f})")
        for w in v.warnings:
            print(f"       - {w}")
    if bad:
        print(f"\nREFCHECK FAILED: {len(bad)} reference(s) contradict the public record.")
        return 1
    if unavailable:
        print(f"\nREFCHECK INCOMPLETE: {len(unavailable)} reference(s) could not be checked. Re-run before submitting.")
        return 2
    if warned and strict:
        print(f"\nREFCHECK FAILED (strict): {len(warned)} reference(s) carry metadata warnings.")
        return 1
    print("\nREFCHECK PASSED: every reference resolves to a real record.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Verify that every .bib entry is a real, correctly described paper.")
    ap.add_argument("bib", help="path to the .bib file")
    ap.add_argument("--json", dest="json_out", help="write the full verdict table here")
    ap.add_argument("--strict", action="store_true", help="treat metadata warnings as failures")
    args = ap.parse_args(argv)

    verdicts = verify_bib(args.bib)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump([v.to_dict() for v in verdicts], fh, indent=2)
    return _report(verdicts, args.strict)


if __name__ == "__main__":
    sys.exit(main())
