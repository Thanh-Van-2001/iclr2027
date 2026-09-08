"""Systematic literature review with citation snowballing.

A related-work section written from a language model's memory is a liability:
the citations may not exist, and the ones that do may not say what they are
credited with saying.  This module builds the review the other way round, from
the citation graph outward, so that every entry in the resulting ``.bib`` came
from an API response.

The procedure is the one used in systematic reviews, adapted to a machine
learning literature that lives on arXiv:

1. **Seed.**  Run several query formulations against OpenAlex and arXiv.
2. **Snowball.**  Follow references backward and citations forward from the
   seeds, for a bounded number of generations.  Backward snowballing finds the
   foundations a reviewer expects you to know; forward snowballing finds the
   2026 work that could scoop you.
3. **Screen.**  Deduplicate across sources and rank by a transparent score.
4. **Map.**  Report which concepts co-occur in the corpus and which pairs never
   do.  A concept pair that is individually well studied and jointly absent is
   where a contribution can go -- the structure Swanson exploited when he
   linked fish oil to Raynaud's syndrome through literatures that did not cite
   each other.

The gap map is a hypothesis generator, not an oracle.  Absence in the corpus
means the searches did not find it, which is evidence only in proportion to how
well the corpus was built; :func:`coverage_report` exists to make that
proportion visible.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import re
import sys
from typing import Iterable, Optional, Sequence

from . import sources
from .sources import Record, normalize_title


# --------------------------------------------------------------------------
# corpus
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Paper:
    key: str
    record: Record
    generation: int             # 0 = seed, 1 = one snowball hop, ...
    found_by: list[str] = dataclasses.field(default_factory=list)
    citations: int = 0
    referenced_works: list[str] = dataclasses.field(default_factory=list)
    openalex_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {"key": self.key, "generation": self.generation, "found_by": self.found_by,
                "citations": self.citations, **self.record.to_dict()}


def _citation_key(rec: Record, taken: set[str]) -> str:
    first = (rec.authors[0] if rec.authors else "anon")
    last = re.split(r"[\s,]+", first.strip())[-1] if first.strip() else "anon"
    last = re.sub(r"[^A-Za-z]", "", last).lower() or "anon"
    year = str(rec.year or "nd")
    word = next((w for w in normalize_title(rec.title).split() if len(w) > 3), "paper")
    base = f"{last}{year}{word}"
    key, i = base, 2
    while key in taken:
        key, i = f"{base}{i}", i + 1
    return key


class Corpus:
    """A deduplicated set of papers, keyed by normalised title."""

    def __init__(self) -> None:
        self.papers: dict[str, Paper] = {}
        self._keys: set[str] = set()

    def _fingerprint(self, rec: Record) -> str:
        if rec.doi:
            return "doi:" + rec.doi.lower()
        if rec.arxiv_id:
            return "arxiv:" + rec.arxiv_id
        return "title:" + normalize_title(rec.title)

    def add(self, rec: Record, *, generation: int, found_by: str) -> Optional[Paper]:
        if not rec.title or len(rec.title) < 8:
            return None
        fp = self._fingerprint(rec)
        if fp in self.papers:
            p = self.papers[fp]
            if found_by not in p.found_by:
                p.found_by.append(found_by)
            p.generation = min(p.generation, generation)
            # Prefer the richer record when a later source knows more.
            if not p.record.abstract and rec.abstract:
                p.record = rec
            return p
        key = _citation_key(rec, self._keys)
        self._keys.add(key)
        p = Paper(key=key, record=rec, generation=generation, found_by=[found_by],
                  citations=int((rec.raw or {}).get("cited_by_count") or (rec.raw or {}).get("citationCount") or 0),
                  openalex_id=(rec.raw or {}).get("id") if rec.source == "openalex" else None)
        self.papers[fp] = p
        return p

    def __len__(self) -> int:
        return len(self.papers)

    def all(self) -> list[Paper]:
        return list(self.papers.values())


# --------------------------------------------------------------------------
# search and snowball
# --------------------------------------------------------------------------

def _openalex_work(work_id: str) -> Optional[dict]:
    wid = work_id.rsplit("/", 1)[-1]
    url = f"https://api.openalex.org/works/{wid}?mailto={sources.CONTACT_EMAIL}"
    try:
        return sources._fetch(url)
    except sources.SourceUnavailable:
        return None


def _openalex_cited_by(work_id: str, limit: int = 25) -> list[Record]:
    wid = work_id.rsplit("/", 1)[-1]
    url = (f"https://api.openalex.org/works?filter=cites:{wid}"
           f"&per-page={limit}&sort=cited_by_count:desc&mailto={sources.CONTACT_EMAIL}")
    try:
        data = sources._fetch(url)
    except sources.SourceUnavailable:
        return []
    if not data or not data.get("results"):
        return []
    return [sources._openalex_to_record(w) for w in data["results"]]


def seed_search(queries: Sequence[str], corpus: Corpus, *, per_query: int = 20) -> None:
    for q in queries:
        for fn, name in ((sources.openalex_search, "openalex"), (sources.arxiv_search, "arxiv")):
            try:
                for rec in fn(q, per_query):
                    corpus.add(rec, generation=0, found_by=f"{name}:{q[:40]}")
            except sources.SourceUnavailable:
                continue


def snowball(corpus: Corpus, *, generations: int = 1, backward: int = 15,
             forward: int = 15, seed_limit: int = 25) -> None:
    """Expand the corpus along the citation graph.

    Only the most-cited papers of each generation are expanded, because the
    graph branches faster than any budget can follow and the highly cited nodes
    are the ones a reviewer will expect to see.
    """
    for gen in range(generations):
        frontier = sorted(
            [p for p in corpus.all() if p.generation == gen and p.openalex_id],
            key=lambda p: -p.citations,
        )[:seed_limit]
        for p in frontier:
            work = _openalex_work(p.openalex_id) if p.openalex_id else None
            if work:
                refs = (work.get("referenced_works") or [])[:backward]
                p.referenced_works = refs
                for ref_id in refs:
                    w = _openalex_work(ref_id)
                    if w:
                        corpus.add(sources._openalex_to_record(w), generation=gen + 1,
                                   found_by=f"backward:{p.key}")
            for rec in _openalex_cited_by(p.openalex_id, forward):
                corpus.add(rec, generation=gen + 1, found_by=f"forward:{p.key}")


# --------------------------------------------------------------------------
# screening
# --------------------------------------------------------------------------

def relevance(paper: Paper, terms: Sequence[str]) -> float:
    """Fraction of the query vocabulary present in title plus abstract."""
    blob = normalize_title((paper.record.title or "") + " " + (paper.record.abstract or ""))
    if not terms:
        return 0.0
    return sum(1 for t in terms if normalize_title(t) in blob) / len(terms)


def rank(corpus: Corpus, terms: Sequence[str], *, current_year: int) -> list[tuple[Paper, float]]:
    """Score papers by relevance, standing and recency.

    Citation counts are log-compressed so that a 40-year-old classic does not
    bury the 2026 preprint that is about to scoop you, and recency is given
    real weight for the same reason.
    """
    scored = []
    for p in corpus.all():
        rel = relevance(p, terms)
        standing = math.log1p(p.citations) / math.log(1000)
        age = max(0, current_year - (p.record.year or current_year))
        recency = math.exp(-age / 3.0)
        corroboration = min(len(p.found_by), 4) / 4.0
        scored.append((p, 0.42 * rel + 0.22 * standing + 0.22 * recency + 0.14 * corroboration))
    scored.sort(key=lambda t: -t[1])
    return scored


def coverage_report(corpus: Corpus, terms: Sequence[str], *, current_year: int) -> dict:
    """How much should we trust an absence in this corpus?"""
    papers = corpus.all()
    by_gen: dict[int, int] = {}
    for p in papers:
        by_gen[p.generation] = by_gen.get(p.generation, 0) + 1
    years = [p.record.year for p in papers if p.record.year]
    recent = [p for p in papers if (p.record.year or 0) >= current_year - 1]
    multi = [p for p in papers if len(p.found_by) >= 2]
    return {
        "n_papers": len(papers),
        "by_generation": dict(sorted(by_gen.items())),
        "year_range": [min(years), max(years)] if years else None,
        "n_last_two_years": len(recent),
        "pct_found_by_multiple_routes": round(100 * len(multi) / max(len(papers), 1), 1),
        "median_relevance": round(sorted(relevance(p, terms) for p in papers)[len(papers) // 2], 3) if papers else 0.0,
        "caveat": ("An absence in this corpus is evidence of a gap only to the extent that the "
                   "corpus is complete. Low overlap between discovery routes, or few papers from "
                   "the last two years, means the search was too narrow to support a novelty claim."),
    }


# --------------------------------------------------------------------------
# gap map
# --------------------------------------------------------------------------

def concept_cooccurrence(corpus: Corpus, concepts: dict[str, Sequence[str]]) -> dict:
    """Count how often each pair of concepts appears in the same paper.

    ``concepts`` maps a concept name to the surface forms that signal it.  A
    pair with healthy individual counts and a joint count of zero is the shape
    worth investigating -- but confirm it with a targeted search before
    believing it, because the corpus was built from queries that may simply
    never have reached the bridging literature.
    """
    names = list(concepts)
    present: dict[str, set[str]] = {n: set() for n in names}
    for p in corpus.all():
        blob = normalize_title((p.record.title or "") + " " + (p.record.abstract or ""))
        for n in names:
            if any(normalize_title(form) in blob for form in concepts[n]):
                present[n].add(p.key)

    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            joint = present[a] & present[b]
            pairs.append({
                "a": a, "b": b,
                "n_a": len(present[a]), "n_b": len(present[b]), "n_joint": len(joint),
                "examples": sorted(joint)[:4],
            })
    pairs.sort(key=lambda d: (d["n_joint"], -min(d["n_a"], d["n_b"])))
    return {"counts": {n: len(v) for n, v in present.items()}, "pairs": pairs}


def verify_gap(concept_a: Sequence[str], concept_b: Sequence[str]) -> dict:
    """Ask the APIs directly how many papers mention both concepts.

    The corpus-level co-occurrence count is only as good as the corpus; this
    goes back to OpenAlex with an explicit conjunctive query so that a claimed
    gap has an independent number attached to it.
    """
    out = {"individual": {}, "joint": {}}
    for form in concept_a:
        out["individual"][form] = sources.openalex_count(form)
    for form in concept_b:
        out["individual"][form] = sources.openalex_count(form)
    for fa in concept_a:
        for fb in concept_b:
            out["joint"][f"{fa} + {fb}"] = sources.openalex_count(f"{fa} {fb}")
    joint_vals = [v for v in out["joint"].values() if v >= 0]
    out["min_joint"] = min(joint_vals) if joint_vals else -1
    out["max_joint"] = max(joint_vals) if joint_vals else -1
    return out


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------

def _escape(s: str) -> str:
    return (s.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")
             .replace("#", r"\#").replace("$", r"\$"))


def to_bibtex(papers: Iterable[Paper]) -> str:
    """Emit BibTeX.  Only fields the API actually returned are written."""
    out = []
    for p in papers:
        r = p.record
        etype = "inproceedings" if (r.venue and re.search(r"conference|proceedings|workshop", r.venue, re.I)) else "article"
        if r.arxiv_id and not r.doi:
            etype = "article"
        lines = [f"@{etype}{{{p.key},"]
        lines.append(f"  title = {{{_escape(r.title)}}},")
        if r.authors:
            lines.append("  author = {" + " and ".join(_escape(a) for a in r.authors if a) + "},")
        if r.year:
            lines.append(f"  year = {{{r.year}}},")
        if r.venue:
            field = "booktitle" if etype == "inproceedings" else "journal"
            lines.append(f"  {field} = {{{_escape(r.venue)}}},")
        if r.doi:
            lines.append(f"  doi = {{{r.doi}}},")
        if r.arxiv_id:
            lines.append(f"  eprint = {{{r.arxiv_id}}},")
            lines.append("  archivePrefix = {arXiv},")
        if r.url:
            lines.append(f"  url = {{{r.url}}},")
        lines.append(f"  note = {{verified via {r.source}}}")
        lines.append("}")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build a snowballed, API-verified literature corpus.")
    ap.add_argument("--query", action="append", required=True, help="seed query (repeatable)")
    ap.add_argument("--term", action="append", default=[], help="relevance term (repeatable)")
    ap.add_argument("--generations", type=int, default=1)
    ap.add_argument("--top", type=int, default=60, help="how many ranked papers to write out")
    ap.add_argument("--year", type=int, default=2026, help="current year, for the recency weight")
    ap.add_argument("--out-dir", default="out/litreview")
    ap.add_argument("--concepts", default=None,
                    help='JSON mapping concept name -> list of surface forms, for the gap map')
    args = ap.parse_args(argv)

    corpus = Corpus()
    print(f"seeding from {len(args.query)} queries ...")
    seed_search(args.query, corpus)
    print(f"  {len(corpus)} papers after seeding")
    if args.generations > 0:
        print(f"snowballing {args.generations} generation(s) ...")
        snowball(corpus, generations=args.generations)
        print(f"  {len(corpus)} papers after snowballing")

    terms = args.term or [w for q in args.query for w in q.split() if len(w) > 4]
    ranked = rank(corpus, terms, current_year=args.year)
    top = [p for p, _ in ranked[:args.top]]

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "corpus.json"), "w", encoding="utf-8") as fh:
        json.dump([p.to_dict() for p, _ in ranked], fh, indent=2)
    with open(os.path.join(args.out_dir, "review.bib"), "w", encoding="utf-8") as fh:
        fh.write(to_bibtex(top))

    cov = coverage_report(corpus, terms, current_year=args.year)
    report = {"coverage": cov, "top": [{"key": p.key, "title": p.record.title,
                                        "year": p.record.year, "citations": p.citations,
                                        "score": round(s, 3), "found_by": p.found_by[:3]}
                                       for p, s in ranked[:args.top]]}
    if args.concepts:
        with open(args.concepts, "r", encoding="utf-8") as fh:
            concepts = json.load(fh)
        report["gap_map"] = concept_cooccurrence(corpus, concepts)
    with open(os.path.join(args.out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(f"\ncoverage: {json.dumps(cov, indent=2)}")
    print(f"\ntop {min(12, len(ranked))} by score:")
    for p, s in ranked[:12]:
        print(f"  {s:.3f}  [{p.citations:>5} cites, {p.record.year}]  {p.record.title[:88]}")
    if "gap_map" in report:
        print("\nconcept pairs with the fewest joint appearances:")
        for pair in report["gap_map"]["pairs"][:8]:
            print(f"  {pair['a']} x {pair['b']}: joint {pair['n_joint']} "
                  f"(individually {pair['n_a']} / {pair['n_b']})")
    print(f"\nwrote {args.out_dir}/review.bib, corpus.json, report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
