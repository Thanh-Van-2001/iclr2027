"""Download, extract, discard -- so the corpus can be thousands of papers.

Keeping the PDFs was fine for a few hundred papers and impossible for several
thousand: the 475-paper pilot already occupied 2.3 GB, and the finding that
matters needs an order of magnitude more papers, because only about one paper in
twenty prints enough for its comparisons to be checked.

Each paper is fetched, parsed, appended to a JSONL file, and deleted. The file
is the checkpoint: a rerun skips whatever is already in it, so an interrupted
run resumes where it stopped and a completed run costs nothing to repeat. The
SHA-256 of each PDF is kept so a later reader can verify they parsed the same
bytes even though the bytes are gone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import random
import sys
import threading
import time
from urllib.parse import urlsplit
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import requests  # noqa: E402

from extract import extract_paper  # noqa: E402
from harvest import SOURCES  # noqa: E402

# One connection pool per worker thread. Every paper was previously a fresh TLS
# handshake to the same two hosts; keeping the connection alive removes a round
# trip per download, and there are thousands of downloads.
_local = threading.local()
UA = {"User-Agent": "Mozilla/5.0 (compatible; paper-audit/0.1)"}

# Concurrency is limited per host, not globally. Measured on 2026-09-10: one
# connection to either host sustains about 5 MB/s, but twenty-four parallel
# downloads from raw.githubusercontent.com -- which is where PMLR keeps every
# ICML PDF -- collapse to 2 MB/s in total, because GitHub throttles concurrent
# raw requests. Reading that as "we are bandwidth-limited" was wrong, and it
# cost an hour of pointlessly adding workers.
HOST_LIMITS = {
    "raw.githubusercontent.com": 4,
    "papers.nips.cc": 28,
    "proceedings.mlr.press": 6,
}
DEFAULT_HOST_LIMIT = 6
_host_semaphores: dict = {}
_host_lock = threading.Lock()


def _host_gate(url: str) -> threading.Semaphore:
    host = urlsplit(url).netloc
    with _host_lock:
        sem = _host_semaphores.get(host)
        if sem is None:
            sem = threading.Semaphore(HOST_LIMITS.get(host, DEFAULT_HOST_LIMIT))
            _host_semaphores[host] = sem
    return sem


def _session() -> "requests.Session":
    sess = getattr(_local, "session", None)
    if sess is None:
        sess = requests.Session()
        sess.headers.update(UA)
        adapter = requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4,
                                                max_retries=2)
        sess.mount("https://", adapter)
        _local.session = sess
    return sess


def _content_length(url: str, timeout: int = 25):
    """Ask how big the file is before spending bandwidth on it.

    The size distribution is heavily skewed -- a median of 2 MB against a mean
    of 5 -- so the few very large PDFs dominate the transfer. They were being
    downloaded in full and then discarded for exceeding the cap, which is the
    worst of both worlds. A HEAD request costs one round trip.

    Note that the cap itself is a source of selection bias: image-heavy papers
    are not a random subset of the literature. The count of papers skipped this
    way is reported, and the cap is set high enough that it is small.
    """
    try:
        with _host_gate(url):
            r = _session().head(url, timeout=timeout, allow_redirects=True)
        n = r.headers.get("Content-Length")
        return int(n) if n else None
    except requests.RequestException:
        return None


def _fetch(url: str, timeout: int = 90) -> bytes:
    with _host_gate(url):
        r = _session().get(url, timeout=timeout)
        r.raise_for_status()
        return r.content


# Above this size a PDF is skipped rather than parsed.
MAX_PDF_BYTES = 30_000_000
# Set by --cache-pdfs: directory in which every downloaded PDF is kept.
PDF_CACHE = None


def _already_done(path: str) -> set:
    done = set()
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                continue
    return done


def run(records: list, out_jsonl: str, *, workers: int = 3, delay: float = 0.02,
        max_pages: int = 40) -> dict:
    done = _already_done(out_jsonl)
    todo = [r for r in records if r["id"] not in done]
    print(f"{len(records)} papers, {len(done)} already extracted, {len(todo)} to do")

    work: queue.Queue = queue.Queue()
    for r in todo:
        work.put(r)

    lock = threading.Lock()
    stats = {"ok": 0, "download_failed": 0, "parse_failed": 0, "skipped_large": 0}
    fh = open(out_jsonl, "a", encoding="utf-8")

    def worker() -> None:
        while True:
            try:
                rec = work.get_nowait()
            except queue.Empty:
                return
            try:
                declared = _content_length(rec["pdf"])
                if declared is not None and declared > MAX_PDF_BYTES:
                    raise ValueError(f"PDF too large ({declared // 1_000_000} MB, from HEAD)")
                # The AAMAS corpus keeps its PDFs on disk (data/corpus) so that
                # the reference-set renderings and the full-text passes need no
                # second download.
                cache_path = os.path.join(PDF_CACHE, f"{rec['venue']}{rec['year']}_{rec['id']}.pdf") if PDF_CACHE else None
                if cache_path and os.path.exists(cache_path):
                    blob = open(cache_path, "rb").read()
                else:
                    blob = _fetch(rec["pdf"])
                if len(blob) < 20_000 or not blob.startswith(b"%PDF"):
                    raise ValueError("not a usable PDF")
                if cache_path and not os.path.exists(cache_path):
                    os.makedirs(PDF_CACHE, exist_ok=True)
                    with open(cache_path, "wb") as cf:
                        cf.write(blob)
                # A handful of very large PDFs -- image-heavy appendices, mostly
                # -- can hang the parser indefinitely. One of them stalled a
                # 2,000-paper run for eighty minutes with no output. Skipping
                # them costs a little coverage and is recorded as a skip.
                if len(blob) > MAX_PDF_BYTES:
                    raise ValueError(f"PDF too large ({len(blob) // 1_000_000} MB)")
                digest = hashlib.sha256(blob).hexdigest()[:16]
                out = extract_paper(blob=blob, max_pages=max_pages)
            except Exception as exc:
                with lock:
                    if "too large" in str(exc):
                        key = "skipped_large"
                    elif isinstance(exc, (requests.RequestException, ValueError)):
                        key = "download_failed"
                    else:
                        key = "parse_failed"
                    stats[key] += 1
                    if (stats["download_failed"] + stats["parse_failed"]) % 25 == 1:
                        print(f"  [{key}] {rec['title'][:55]}: {type(exc).__name__}")
                work.task_done()
                time.sleep(delay)
                continue

            out.pop("path", None)
            # The full cell dump is what makes the file enormous; keep the
            # per-table summaries and the cells, but not the page text.
            out.update({"venue": rec["venue"], "year": rec["year"], "title": rec["title"],
                        "id": rec["id"], "sha256": digest})
            with lock:
                fh.write(json.dumps(out, ensure_ascii=False) + "\n")
                fh.flush()
                stats["ok"] += 1
                n = stats["ok"]
                if n % 25 == 0:
                    print(f"  {n} extracted "
                          f"({stats['download_failed']} dl-fail, {stats['parse_failed']} parse-fail)",
                          flush=True)
            work.task_done()
            time.sleep(delay)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    fh.close()
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stream a large corpus through the extractor.")
    ap.add_argument("--source", action="append", required=True, help=f"one of {sorted(SOURCES)}")
    ap.add_argument("--sample", type=int, default=0, help="0 means every paper in the source")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", default="data/extracted_large.jsonl")
    ap.add_argument("--cache-pdfs", default=None, help="keep every downloaded PDF in this directory")
    args = ap.parse_args(argv)
    global PDF_CACHE
    PDF_CACHE = args.cache_pdfs

    records = []
    listed = {}
    for src in args.source:
        if src not in SOURCES:
            print(f"unknown source {src!r}; known: {sorted(SOURCES)}")
            return 2
        idx = SOURCES[src]()
        listed[src] = len(idx)
        print(f"{src}: {len(idx)} papers listed")
        records.extend(idx)

    records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
    if args.sample and args.sample < len(records):
        records = random.Random(args.seed).sample(records, args.sample)
        records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    already = len(_already_done(args.out))
    stats = run(records, args.out, workers=args.workers)
    # A resumed run must report the corpus, not the batch it just added.
    stats["ok"] += already
    print(f"\nextracted {stats['ok']}  |  download failures {stats['download_failed']}  "
          f"|  parse failures {stats['parse_failed']}  |  skipped as too large {stats['skipped_large']}")
    print(f"-> {args.out}")
    # The exclusions are part of the corpus definition, so they are recorded
    # where the paper can cite them rather than left in a terminal.
    stem = os.path.splitext(os.path.basename(args.out))[0]
    os.makedirs("out", exist_ok=True)
    with open(os.path.join("out", f"pipeline_stats_{stem}.json"), "w", encoding="utf-8") as fh:
        json.dump({"sources": args.source, "sample": args.sample, "seed": args.seed,
                   "listed": listed, "drawn": len(records), "max_pdf_bytes": MAX_PDF_BYTES,
                   **stats}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
