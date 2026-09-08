"""Bibliographic source clients.

Every network call goes through :class:`Cache` so that a paper build is
reproducible offline once the cache is warm, and so that repeated verification
passes do not hammer public APIs.

Design rules:
  * No client ever fabricates a record.  A lookup either returns a
    :class:`Record` that came verbatim from an upstream API, or ``None``.
  * Each ``Record`` keeps ``source`` and ``raw`` so that any downstream claim
    can be traced back to the exact API response that supports it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Iterable, Optional

CACHE_DIR = os.environ.get("PAPERENGINE_CACHE", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"))
# OpenAlex and Crossref ask for a contact address so they can put the caller in
# their polite pool.  It is read from the environment rather than written here:
# this file ships as supplementary material, and a hard-coded address would
# deanonymise the submission.  Set PAPERENGINE_EMAIL locally.
CONTACT_EMAIL = os.environ.get("PAPERENGINE_EMAIL", "anonymous@example.org")
USER_AGENT = f"paperengine/0.1 (mailto:{CONTACT_EMAIL})"
S2_API_KEY = os.environ.get("S2_API_KEY", "")

ARXIV_ID_RE = re.compile(r"(?:arXiv:)?(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
OLD_ARXIV_ID_RE = re.compile(r"([a-z-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

class Cache:
    """Filesystem cache keyed by a hash of the request URL."""

    def __init__(self, root: str = CACHE_DIR) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key: str) -> str:
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
        return os.path.join(self.root, f"{h}.json")

    def get(self, key: str) -> Optional[Any]:
        p = self._path(key)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as fh:
                return json.load(fh)["value"]
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def put(self, key: str, value: Any) -> None:
        tmp = self._path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"key": key, "value": value}, fh)
        os.replace(tmp, self._path(key))


_CACHE = Cache()


class SourceUnavailable(RuntimeError):
    """The upstream API could not be reached or refused to answer.

    This is deliberately a different outcome from "the API answered and the
    record does not exist".  Conflating the two is how a citation checker comes
    to report a real paper as fabricated, which destroys trust in the gate.
    """

    def __init__(self, host: str, detail: str) -> None:
        super().__init__(f"{host}: {detail}")
        self.host = host
        self.detail = detail


# Politeness intervals.  arXiv's terms ask for roughly one request every three
# seconds; the others are more permissive but we stay well inside their limits.
_MIN_INTERVAL = {
    "export.arxiv.org": 3.1,
    "api.semanticscholar.org": 1.2,
    # OpenAlex moved to a spend-based limiter in 2026: a request costs a small
    # amount from a slowly refilling budget, and exceeding it returns 429 with
    # "Insufficient budget" rather than a retry-after. Measured empirically on
    # 2026-09-09, roughly one request per second is sustainable from an
    # unauthenticated client in the polite pool.
    "api.openalex.org": 1.1,
    "api.crossref.org": 0.2,
}
# A spend limiter needs a much longer pause than an ordinary rate limiter,
# because the budget refills with time rather than resetting on a window.
_BACKOFF_BASE = {"api.openalex.org": 12.0}
_LAST_CALL: dict[str, float] = {}


def _throttle(host: str) -> None:
    interval = _MIN_INTERVAL.get(host, 0.2)
    elapsed = time.monotonic() - _LAST_CALL.get(host, 0.0)
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _LAST_CALL[host] = time.monotonic()


def _fetch(url: str, *, headers: Optional[dict] = None, retries: int = 4, is_json: bool = True) -> Optional[Any]:
    """GET a URL with throttling, backoff and caching.

    Returns the parsed body, or ``None`` when the server answered but the
    resource does not exist (HTTP 404/410).  Raises :class:`SourceUnavailable`
    when the server could not be reached or throttled us out.
    """
    cache_key = url + "|" + json.dumps(headers or {}, sort_keys=True)
    hit = _CACHE.get(cache_key)
    if hit is not None:
        return hit

    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json" if is_json else "*/*"}
    hdrs.update(headers or {})
    host = urllib.parse.urlparse(url).netloc

    delay, last = _BACKOFF_BASE.get(host, 2.0), "unknown error"
    for attempt in range(retries):
        _throttle(host)
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            value = json.loads(body) if is_json else body
            _CACHE.put(cache_key, value)
            return value
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410):
                _CACHE.put(cache_key, None)
                return None
            last = f"HTTP {exc.code}"
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2.5
                continue
            raise SourceUnavailable(host, last) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = f"{type(exc).__name__}: {exc}"
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2.0
                continue
            raise SourceUnavailable(host, last) from exc
        except json.JSONDecodeError as exc:
            raise SourceUnavailable(host, f"malformed response: {exc}") from exc
    raise SourceUnavailable(host, last)


# --------------------------------------------------------------------------
# record
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Record:
    """A bibliographic record that provably came from an upstream API."""

    title: str
    authors: list[str]
    year: Optional[int]
    venue: Optional[str]
    doi: Optional[str]
    arxiv_id: Optional[str]
    url: Optional[str]
    abstract: Optional[str]
    source: str
    raw: dict = dataclasses.field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d.pop("raw", None)
        return d


def normalize_title(title: str) -> str:
    """Aggressive normalisation used for fuzzy title matching."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(a: str, b: str) -> float:
    """Token-level Jaccard on normalised titles.  Cheap and adequate here."""
    ta, tb = set(normalize_title(a).split()), set(normalize_title(b).split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# --------------------------------------------------------------------------
# arXiv
# --------------------------------------------------------------------------

_ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _arxiv_entry_to_record(entry: ET.Element) -> Optional[Record]:
    def txt(path: str) -> Optional[str]:
        node = entry.find(path, _ATOM)
        return " ".join(node.text.split()) if node is not None and node.text else None

    raw_id = txt("a:id") or ""
    m = ARXIV_ID_RE.search(raw_id) or OLD_ARXIV_ID_RE.search(raw_id)
    if not m:
        return None
    title = txt("a:title")
    if not title:
        return None
    authors = [
        " ".join(n.text.split())
        for n in entry.findall("a:author/a:name", _ATOM)
        if n.text
    ]
    published = txt("a:published") or ""
    year = int(published[:4]) if published[:4].isdigit() else None
    doi = txt("arxiv:doi")
    journal_ref = txt("arxiv:journal_ref")
    return Record(
        title=title,
        authors=authors,
        year=year,
        venue=journal_ref,
        doi=doi,
        arxiv_id=m.group(1),
        url=f"https://arxiv.org/abs/{m.group(1)}",
        abstract=txt("a:summary"),
        source="arxiv",
        raw={"id": raw_id},
    )


def arxiv_by_id(arxiv_id: str) -> Optional[Record]:
    aid = arxiv_id.strip()
    m = ARXIV_ID_RE.search(aid) or OLD_ARXIV_ID_RE.search(aid)
    if not m:
        return None
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": m.group(1), "max_results": 1})
    body = _fetch(url, is_json=False)
    if not body:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    for entry in root.findall("a:entry", _ATOM):
        rec = _arxiv_entry_to_record(entry)
        # arXiv returns a stub entry with the title "Error" for unknown ids.
        if rec and rec.title.lower() != "error":
            return rec
    return None


def arxiv_search(query: str, limit: int = 8) -> list[Record]:
    escaped = query.replace('"', " ")
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": f'all:"{escaped}"', "max_results": limit, "sortBy": "relevance"}
    )
    body = _fetch(url, is_json=False)
    if not body:
        return []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out = []
    for entry in root.findall("a:entry", _ATOM):
        rec = _arxiv_entry_to_record(entry)
        if rec:
            out.append(rec)
    return out


# --------------------------------------------------------------------------
# OpenAlex
# --------------------------------------------------------------------------

def _openalex_abstract(inverted: Optional[dict]) -> Optional[str]:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    if not positions:
        return None
    positions.sort()
    return " ".join(w for _, w in positions)


def _openalex_to_record(w: dict) -> Record:
    ids = w.get("ids") or {}
    arxiv_id = None
    loc = (w.get("primary_location") or {}).get("landing_page_url") or ""
    m = ARXIV_ID_RE.search(loc) or OLD_ARXIV_ID_RE.search(loc)
    if m:
        arxiv_id = m.group(1)
    doi = (w.get("doi") or "").replace("https://doi.org/", "") or None
    if arxiv_id is None and doi and "arxiv" in doi.lower():
        m2 = ARXIV_ID_RE.search(doi)
        if m2:
            arxiv_id = m2.group(1)
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
    return Record(
        title=w.get("display_name") or "",
        authors=[(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])],
        year=w.get("publication_year"),
        venue=venue,
        doi=doi,
        arxiv_id=arxiv_id,
        url=ids.get("openalex") or loc or None,
        abstract=_openalex_abstract(w.get("abstract_inverted_index")),
        source="openalex",
        raw={"cited_by_count": w.get("cited_by_count"), "type": w.get("type"), "id": ids.get("openalex")},
    )


def openalex_by_doi(doi: str) -> Optional[Record]:
    doi = doi.strip().replace("https://doi.org/", "")
    url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}?mailto={urllib.parse.quote(CONTACT_EMAIL)}"
    data = _fetch(url)
    if not data or "id" not in data:
        return None
    return _openalex_to_record(data)


def openalex_search(query: str, limit: int = 8) -> list[Record]:
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "per-page": limit, "mailto": CONTACT_EMAIL}
    )
    data = _fetch(url)
    if not data or not data.get("results"):
        return []
    return [_openalex_to_record(w) for w in data["results"]]


def openalex_count(query: str) -> int:
    """Number of works matching a full-text search.  Used by gap mining."""
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(
        {"search": query, "per-page": 1, "mailto": CONTACT_EMAIL}
    )
    data = _fetch(url)
    if not data:
        return -1
    return int((data.get("meta") or {}).get("count", -1))


# --------------------------------------------------------------------------
# Crossref
# --------------------------------------------------------------------------

def _crossref_to_record(it: dict) -> Record:
    title = (it.get("title") or [""])[0]
    authors = [
        " ".join(x for x in [a.get("given"), a.get("family")] if x)
        for a in (it.get("author") or [])
    ]
    parts = ((it.get("issued") or {}).get("date-parts") or [[None]])[0]
    year = parts[0] if parts and isinstance(parts[0], int) else None
    return Record(
        title=title,
        authors=authors,
        year=year,
        venue=(it.get("container-title") or [None])[0] or it.get("event", {}).get("name"),
        doi=it.get("DOI"),
        arxiv_id=None,
        url=it.get("URL"),
        abstract=it.get("abstract"),
        source="crossref",
        raw={"type": it.get("type"), "publisher": it.get("publisher")},
    )


def crossref_by_doi(doi: str) -> Optional[Record]:
    doi = doi.strip().replace("https://doi.org/", "")
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={urllib.parse.quote(CONTACT_EMAIL)}"
    data = _fetch(url)
    if not data or data.get("status") != "ok":
        return None
    return _crossref_to_record(data["message"])


def crossref_search(query: str, limit: int = 8) -> list[Record]:
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(
        {"query.bibliographic": query, "rows": limit, "mailto": CONTACT_EMAIL}
    )
    data = _fetch(url)
    if not data or data.get("status") != "ok":
        return []
    return [_crossref_to_record(it) for it in data["message"].get("items", [])]


# --------------------------------------------------------------------------
# Semantic Scholar (secondary: aggressively rate limited without a key)
# --------------------------------------------------------------------------

_S2_FIELDS = "title,authors,year,venue,externalIds,abstract,url,citationCount"


def _s2_headers() -> dict:
    return {"x-api-key": S2_API_KEY} if S2_API_KEY else {}


def _s2_to_record(p: dict) -> Record:
    ext = p.get("externalIds") or {}
    return Record(
        title=p.get("title") or "",
        authors=[a.get("name", "") for a in (p.get("authors") or [])],
        year=p.get("year"),
        venue=p.get("venue"),
        doi=ext.get("DOI"),
        arxiv_id=ext.get("ArXiv"),
        url=p.get("url"),
        abstract=p.get("abstract"),
        source="semanticscholar",
        raw={"citationCount": p.get("citationCount"), "paperId": p.get("paperId")},
    )


def s2_search(query: str, limit: int = 8) -> list[Record]:
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        {"query": query, "limit": limit, "fields": _S2_FIELDS}
    )
    data = _fetch(url, headers=_s2_headers(), retries=3)
    if not data or not data.get("data"):
        return []
    return [_s2_to_record(p) for p in data["data"]]


def s2_by_id(ident: str) -> Optional[Record]:
    """``ident`` may be ``DOI:10.x/y``, ``ARXIV:2401.00001`` or an S2 paper id."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/{urllib.parse.quote(ident, safe=':')}?fields={_S2_FIELDS}"
    data = _fetch(url, headers=_s2_headers(), retries=3)
    if not data or not data.get("title"):
        return None
    return _s2_to_record(data)


# --------------------------------------------------------------------------
# unified lookup
# --------------------------------------------------------------------------

def _try_each(calls: list[tuple[str, Any]]) -> tuple[Optional[Record], list[str], int]:
    """Run lookups in order; return the first hit plus availability bookkeeping.

    Returns ``(record, unavailable_hosts, definitive_misses)``.  A definitive
    miss is a source that answered and said the record does not exist.
    """
    unavailable: list[str] = []
    misses = 0
    for name, fn in calls:
        try:
            rec = fn()
        except SourceUnavailable as exc:
            unavailable.append(f"{name} ({exc.detail})")
            continue
        if rec:
            return rec, unavailable, misses
        misses += 1
    return None, unavailable, misses


def lookup_by_identifier(*, doi: Optional[str] = None, arxiv_id: Optional[str] = None) -> Optional[Record]:
    """Resolve a hard identifier through every source until one answers.

    Raises :class:`SourceUnavailable` if no source ever gave a definitive
    answer, so that a rate limit is never mistaken for a fabricated citation.
    """
    calls: list[tuple[str, Any]] = []
    if arxiv_id:
        calls.append(("arxiv", lambda: arxiv_by_id(arxiv_id)))
    if doi:
        calls.append(("openalex", lambda: openalex_by_doi(doi)))
        calls.append(("crossref", lambda: crossref_by_doi(doi)))
    if arxiv_id:
        calls.append(("semanticscholar", lambda: s2_by_id(f"ARXIV:{arxiv_id}")))
    if doi:
        calls.append(("semanticscholar", lambda: s2_by_id(f"DOI:{doi}")))

    rec, unavailable, misses = _try_each(calls)
    if rec:
        return rec
    if misses == 0 and unavailable:
        raise SourceUnavailable("all sources", "; ".join(unavailable))
    return None


def search_all(query: str, limit: int = 6) -> list[Record]:
    """Title search fanned out across sources.

    Raises :class:`SourceUnavailable` only if every source failed to answer, so
    that an empty result genuinely means "nobody has heard of this paper".
    """
    out: list[Record] = []
    unavailable: list[str] = []
    answered = 0
    for name, fn in (("arxiv", arxiv_search), ("openalex", openalex_search),
                     ("crossref", crossref_search), ("semanticscholar", s2_search)):
        try:
            out.extend(fn(query, limit))
            answered += 1
        except SourceUnavailable as exc:
            unavailable.append(f"{name} ({exc.detail})")
    if not answered:
        raise SourceUnavailable("all sources", "; ".join(unavailable))
    return out


def best_title_match(query_title: str, candidates: Iterable[Record]) -> tuple[Optional[Record], float]:
    best, best_score = None, 0.0
    for rec in candidates:
        score = title_similarity(query_title, rec.title)
        if score > best_score:
            best, best_score = rec, score
    return best, best_score
