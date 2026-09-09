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
import tempfile
import threading
import time
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from extract import extract_paper  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402


# Above this size a PDF is skipped rather than parsed.
MAX_PDF_BYTES = 30_000_000


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


def run(records: list, out_jsonl: str, *, workers: int = 3, delay: float = 0.1,
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
            tmp = None
            try:
                blob = _get(rec["pdf"])
                if len(blob) < 20_000 or not blob.startswith(b"%PDF"):
                    raise ValueError("not a usable PDF")
                # A handful of very large PDFs -- image-heavy appendices, mostly
                # -- can hang the parser indefinitely. One of them stalled a
                # 2,000-paper run for eighty minutes with no output. Skipping
                # them costs a little coverage and is recorded as a skip.
                if len(blob) > MAX_PDF_BYTES:
                    raise ValueError(f"PDF too large ({len(blob) // 1_000_000} MB)")
                digest = hashlib.sha256(blob).hexdigest()[:16]
                fd, tmp = tempfile.mkstemp(suffix=".pdf")
                with os.fdopen(fd, "wb") as tf:
                    tf.write(blob)
                out = extract_paper(tmp, max_pages=max_pages)
            except Exception as exc:
                with lock:
                    if "too large" in str(exc):
                        key = "skipped_large"
                    else:
                        key = "parse_failed" if tmp else "download_failed"
                    stats[key] += 1
                    if (stats["download_failed"] + stats["parse_failed"]) % 25 == 1:
                        print(f"  [{key}] {rec['title'][:55]}: {type(exc).__name__}")
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
                work.task_done()
                time.sleep(delay)
                continue
            finally:
                pass

            os.unlink(tmp)
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
    args = ap.parse_args(argv)

    records = []
    for src in args.source:
        if src not in SOURCES:
            print(f"unknown source {src!r}; known: {sorted(SOURCES)}")
            return 2
        idx = SOURCES[src]()
        print(f"{src}: {len(idx)} papers listed")
        records.extend(idx)

    records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))
    if args.sample and args.sample < len(records):
        records = random.Random(args.seed).sample(records, args.sample)
        records.sort(key=lambda r: (r["venue"], r["year"], r["id"]))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    stats = run(records, args.out, workers=args.workers)
    print(f"\nextracted {stats['ok']}  |  download failures {stats['download_failed']}  "
          f"|  parse failures {stats['parse_failed']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
