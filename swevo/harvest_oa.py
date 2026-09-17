"""The open-access metaheuristics corpus: every 2024–2025 article in seven
fully open-access CC-BY journals whose title or abstract names a
metaheuristic, listed through OpenAlex, with the publisher's PDF URL.

Usage: python swevo/harvest_oa.py --out out/swevo/index.json
       then python study/pipeline.py --source swevo-oa --cache-pdfs data/corpus_oa ...
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import requests

MAILTO = "felicenguyen2001@gmail.com"
UA = {"User-Agent": f"paper-audit/0.1 (mailto:{MAILTO})"}
JOURNALS = [
    ("2045-2322", "Scientific Reports"),
    ("2227-7390", "Mathematics"),
    ("2076-3417", "Applied Sciences"),
    ("2313-7673", "Biomimetics"),
    ("1999-4893", "Algorithms"),
    ("2198-6053", "Complex & Intelligent Systems"),
    ("2376-5992", "PeerJ Computer Science"),
]
PHRASES = ["metaheuristic", "meta-heuristic", "evolutionary algorithm", "genetic algorithm", "particle swarm",
           "differential evolution", "swarm intelligence", "ant colony", "simulated annealing", "nature-inspired",
           "bio-inspired optimization", "grey wolf", "whale optimization", "memetic", "NSGA"]
SEARCH = " OR ".join(f'"{p}"' for p in PHRASES)


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words = sorted((pos, w) for w, poss in inv.items() for pos in poss)
    return " ".join(w for _, w in words)


def _pdf_url(work: dict, issn: str) -> str | None:
    loc = work.get("best_oa_location") or {}
    if loc.get("pdf_url"):
        return loc["pdf_url"].split("?")[0]
    doi = (work.get("doi") or "").replace("https://doi.org/", "")
    if doi.startswith("10.3390/"):
        # MDPI: journal code + VV + II + NNN, e.g. a18040187 -> 1999-4893/18/4/187
        m = re.match(r"10\.3390/[a-z]+(\d{2})(\d{2})(\d{3,5})$", doi)
        if m:
            return f"https://www.mdpi.com/{issn}/{int(m.group(1))}/{int(m.group(2))}/{int(m.group(3))}/pdf"
    if doi.startswith("10.1007/") or doi.startswith("10.1038/"):
        return f"https://link.springer.com/content/pdf/{doi}.pdf" if doi.startswith("10.1007/") else f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf"
    if doi.startswith("10.7717/"):
        return f"https://peerj.com/articles/{doi.split('/')[-1].replace('peerj-', '')}.pdf"
    return None


def index(years=(2024, 2025)) -> list:
    out = []
    for issn, name in JOURNALS:
        cursor = "*"
        n = 0
        while cursor:
            r = requests.get("https://api.openalex.org/works", params={
                "filter": f"primary_location.source.issn:{issn},publication_year:{'|'.join(map(str, years))},type:article,title_and_abstract.search:{SEARCH}",
                "per-page": 200, "cursor": cursor, "mailto": MAILTO,
                "select": "id,doi,title,publication_year,publication_date,abstract_inverted_index,best_oa_location,primary_location,cited_by_count,referenced_works_count"},
                headers=UA, timeout=120)
            r.raise_for_status()
            j = r.json()
            for w in j["results"]:
                doi = (w.get("doi") or "").replace("https://doi.org/", "")
                if not doi:
                    continue
                pdf = _pdf_url(w, issn)
                if not pdf:
                    continue
                out.append({"venue": "OA", "year": w["publication_year"], "journal": name, "issn": issn,
                            "id": hashlib.sha1(doi.encode()).hexdigest()[:16], "doi": doi,
                            "openalex": w["id"], "title": re.sub(r"\s+", " ", w.get("title") or "").strip(),
                            "abstract": _abstract(w.get("abstract_inverted_index")),
                            "published": w.get("publication_date"), "pdf": pdf,
                            "abstract_page": f"https://doi.org/{doi}", "cited_by": w.get("cited_by_count", 0)})
                n += 1
            cursor = j["meta"].get("next_cursor")
            time.sleep(0.3)
        print(f"{name}: {n}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/swevo/index.json")
    args = ap.parse_args(argv)
    recs = index()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump(recs, open(args.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(len(recs), "papers ->", args.out)


if __name__ == "__main__":
    main()
