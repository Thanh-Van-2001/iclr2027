"""Build the corpus of accepted papers.

The study needs papers whose acceptance is not in question, whose PDFs are
publicly downloadable without an account, and whose venue is central enough to
machine learning that a reviewer cannot dismiss the sample as unrepresentative.

Three sources satisfy that:

- NeurIPS, from ``papers.nips.cc``, which lists every accepted paper per year.
- ICML and the other PMLR volumes, from ``proceedings.mlr.press``.
- ICLR, which has no open proceedings mirror; OpenReview now sits behind a bot
  challenge, so ICLR is reached through arXiv where the paper is also posted.

Everything is cached on disk and recorded in a manifest, so a rerun downloads
nothing and produces the same corpus. A study about other people's
reproducibility that cannot itself be rerun would be an embarrassment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Iterable, Optional

UA = {"User-Agent": "Mozilla/5.0 (compatible; paper-audit/0.1)", "Accept": "*/*"}   # arXiv answers 406 without an Accept header
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "corpus")
DELAY = 1.0


def _get(url: str, *, retries: int = 3, timeout: int = 90) -> bytes:
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as exc:  # IncompleteRead is not an OSError
            last = exc
            time.sleep(2.0 * (attempt + 1) + (8.0 if "406" in str(exc) else 0.0))
    raise RuntimeError(f"failed to fetch {url}: {last}")


# --------------------------------------------------------------------------
# indexes
# --------------------------------------------------------------------------

def neurips_index(year: int) -> list[dict]:
    """Every accepted NeurIPS paper for a year, with its PDF URL.

    From 2025 the site splits each year into volume pages, so the year index
    lists only a handful of links and the papers live one level down. Checking
    this was prompted by an obvious question -- why 2024 and not 2025 -- that
    the first version of this file had simply never asked.
    """
    url = f"https://papers.nips.cc/paper_files/paper/{year}"
    html = _get(url).decode("utf-8", "replace")
    if html.count("/hash/") < 200:
        vols = re.findall(rf'href="(/paper_files/paper/{year}/[a-z0-9-]*(?:main-conference|track)[^"]*)"',
                          html, re.I)
        parts = []
        for v in dict.fromkeys(vols):
            try:
                parts.append(_get("https://papers.nips.cc" + v).decode("utf-8", "replace"))
            except RuntimeError:
                continue
        if parts:
            html = chr(10).join(parts)
    out = []
    for m in re.finditer(
        r'href="(/paper_files/paper/%d/hash/([0-9a-f]+)-Abstract[^"]*\.html)"[^>]*>(.*?)</a>' % year,
        html, re.S,
    ):
        href, digest, title = m.group(1), m.group(2), re.sub(r"<[^>]+>", "", m.group(3)).strip()
        suffix = "-Paper-Conference.pdf" if "Abstract-Conference" in href else "-Paper.pdf"
        out.append({
            "venue": "NeurIPS", "year": year, "id": digest, "title": title,
            "pdf": f"https://papers.nips.cc/paper_files/paper/{year}/file/{digest}{suffix}",
            "abstract_page": "https://papers.nips.cc" + href,
        })
    return out


def pmlr_index(volume: str, venue: str, year: int) -> list[dict]:
    """Every paper in one PMLR volume (e.g. ``v235`` is ICML 2024)."""
    html = _get(f"https://proceedings.mlr.press/{volume}/").decode("utf-8", "replace")
    out = []
    for m in re.finditer(r'<p class="title">(.*?)</p>.*?href="([^"]*?\.pdf)"', html, re.S):
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        pdf = m.group(2)
        if pdf.startswith("/"):
            pdf = "https://proceedings.mlr.press" + pdf
        out.append({"venue": venue, "year": year, "id": hashlib.sha1(pdf.encode()).hexdigest()[:16],
                    "title": title, "pdf": pdf, "abstract_page": f"https://proceedings.mlr.press/{volume}/"})
    return out


def aamas_index(year: int) -> list[dict]:
    """Every main-track ("Research Paper Track") paper of one AAMAS year from
    the open IFAAMAS proceedings. The contents page lists every track under
    its own anchor; extended abstracts, demos, doctoral consortium, JAAMAS and
    Blue Sky papers are left out, so the corpus holds full papers only.
    """
    base = f"https://www.ifaamas.org/Proceedings/aamas{year}/"
    html = _get(base + "forms/contents.htm").decode("utf-8", "replace")
    nav = {}
    for m in re.finditer(r'href="#([^"]+)"[^>]*>(?:<font[^>]*>)?(?:<strong>)?([^<]+)', html):
        nav[m.group(1)] = re.sub(r"\s+", " ", m.group(2)).strip()
    key = next(k for k, v in nav.items() if v.startswith("Research Paper") or v.startswith("Full Papers"))
    anchors = [(m.start(), m.group(1)) for m in re.finditer(r'<a name="([^"]+)"', html)]
    start = next(pos for pos, name in anchors if name == key)
    end = min((pos for pos, name in anchors if pos > start), default=len(html))
    out = []
    for m in re.finditer(r'<a href="\.\./pdfs/([^"]+)\.pdf"[^>]*>(.*?)</a>&nbsp;<font[^>]*>\(Page\s*(\d+)\)',
                         html[start:end], re.S):
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(2))).strip()
        pdf = f"{base}pdfs/{m.group(1)}.pdf"
        out.append({"venue": "AAMAS", "year": year, "id": hashlib.sha1(pdf.encode()).hexdigest()[:16],
                    "title": title, "pdf": pdf, "abstract_page": base + "forms/contents.htm",
                    "page": int(m.group(3))})
    return out


def arxiv_index(category: str, year: int, max_results: int = 4000) -> list[dict]:
    """Every arXiv paper with the given primary category submitted in one
    year, from the arXiv API (Atom), with its PDF URL. Cross-lists are kept
    when the category is primary. The API asks for three seconds between
    calls; 200 records per call."""
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    out, start = [], 0
    while start < max_results:
        # the API answers urllib's requests with 406 past the first page; the
        # requests library, with the same headers, is accepted
        import requests
        time.sleep(4.0)   # the API rate limit
        r = requests.get("https://export.arxiv.org/api/query",
                         params={"search_query": f"cat:{category} AND submittedDate:[{year}01010000 TO {year}12312359]",
                                 "start": start, "max_results": 200, "sortBy": "submittedDate", "sortOrder": "ascending"},
                         headers=UA, timeout=120)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        entries = root.findall("a:entry", ns)
        if not entries:
            break
        for e in entries:
            prim = e.find("arxiv:primary_category", ns)
            if prim is None or prim.get("term") != category:
                continue
            aid = e.find("a:id", ns).text.strip().rsplit("/", 1)[-1]   # e.g. 2501.01234v2
            title = re.sub(r"\s+", " ", e.find("a:title", ns).text).strip()
            out.append({"venue": f"arXiv-{category.replace('.', '')}", "year": year,
                        "id": hashlib.sha1(aid.encode()).hexdigest()[:16], "arxiv_id": aid,
                        "title": title, "pdf": f"https://arxiv.org/pdf/{aid}",
                        "abstract_page": f"https://arxiv.org/abs/{aid}",
                        "published": (e.find("a:published", ns).text or "")[:10]})
        start += 200
        time.sleep(3.0)
    return out


def oa_index(path: str = "out/swevo/index.json") -> list[dict]:
    """The open-access metaheuristics corpus listed by swevo/harvest_oa.py
    (OpenAlex); the PDFs are fetched by swevo/fetch_oa.py into data/corpus_oa."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


SOURCES = {
    "swevo-oa": lambda: oa_index(),
    "arxiv-csne-2025": lambda: arxiv_index("cs.NE", 2025),
    "arxiv-mathoc-2025": lambda: arxiv_index("math.OC", 2025),
    "aamas2026": lambda: aamas_index(2026),
    "aamas2025": lambda: aamas_index(2025),
    "aamas2024": lambda: aamas_index(2024),
    "neurips2025": lambda: neurips_index(2025),
    "neurips2024": lambda: neurips_index(2024),
    "neurips2023": lambda: neurips_index(2023),
    "neurips2022": lambda: neurips_index(2022),
    "icml2025": lambda: pmlr_index("v267", "ICML", 2025),
    "icml2024": lambda: pmlr_index("v235", "ICML", 2024),
    "icml2023": lambda: pmlr_index("v202", "ICML", 2023),
}


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------

def fetch_pdfs(records: Iterable[dict], *, cache_dir: str = CACHE, delay: float = DELAY,
               verbose: bool = True) -> list[dict]:
    os.makedirs(cache_dir, exist_ok=True)
    out = []
    for i, rec in enumerate(records, 1):
        path = os.path.join(cache_dir, f"{rec['venue']}{rec['year']}_{rec['id']}.pdf")
        rec = dict(rec)
        if os.path.exists(path) and os.path.getsize(path) > 20_000:
            rec["path"], rec["cached"] = path, True
        else:
            try:
                blob = _get(rec["pdf"])
            except Exception as exc:
                if verbose:
                    print(f"  [{i}] SKIP {rec['title'][:60]}: {exc}")
                continue
            if len(blob) < 20_000 or not blob.startswith(b"%PDF"):
                if verbose:
                    print(f"  [{i}] SKIP {rec['title'][:60]}: not a usable PDF")
                continue
            with open(path, "wb") as fh:
                fh.write(blob)
            rec["path"], rec["cached"] = path, False
            time.sleep(delay)
        rec["sha256"] = _sha256(path)
        rec["bytes"] = os.path.getsize(path)
        out.append(rec)
        if verbose and i % 25 == 0:
            print(f"  {i} done ({sum(1 for r in out if r['cached'])} from cache)")
    return out


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Harvest accepted-paper PDFs into a cached, manifested corpus.")
    ap.add_argument("--source", action="append", required=True,
                    help=f"one of {sorted(SOURCES)} (repeatable)")
    ap.add_argument("--sample", type=int, default=0, help="random subsample size, 0 for all")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--cache-dir", default=CACHE)
    ap.add_argument("--manifest", default="data/corpus_manifest.json")
    args = ap.parse_args(argv)

    records: list[dict] = []
    for src in args.source:
        if src not in SOURCES:
            print(f"unknown source {src!r}; known: {sorted(SOURCES)}")
            return 2
        idx = SOURCES[src]()
        print(f"{src}: {len(idx)} papers listed")
        records.extend(idx)

    # Sample before downloading, and sample deterministically, so that the
    # corpus is a function of the seed alone and can be regenerated exactly.
    records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
    if args.sample and args.sample < len(records):
        records = random.Random(args.seed).sample(records, args.sample)
        records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
        print(f"sampled {len(records)} with seed {args.seed}")

    fetched = fetch_pdfs(records, cache_dir=args.cache_dir)
    os.makedirs(os.path.dirname(os.path.abspath(args.manifest)) or ".", exist_ok=True)
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump({"sources": args.source, "sample": args.sample, "seed": args.seed,
                   "n": len(fetched), "papers": fetched}, fh, indent=1)
    print(f"\n{len(fetched)} PDFs in corpus -> {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
