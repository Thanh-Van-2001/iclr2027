"""Fetch the corpus PDFs listed by harvest_oa.py, one journal host at a time,
with a browser-like client and a fixed delay, into data/corpus_oa/ under
the same naming the pipeline expects (OA<year>_<id>.pdf). Resumable; a
failure is recorded, not retried in the same run.

Usage: python swevo/fetch_oa.py --journal "Scientific Reports" [--delay 2.0]
"""
import argparse
import json
import os
import time

import requests

INDEX = "out/swevo/index.json"
CACHE = "data/corpus_oa"
LOG = "out/swevo/fetch_log.json"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
     "Accept": "application/pdf,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)
    recs = [r for r in json.load(open(INDEX, encoding="utf-8")) if r["journal"] == args.journal]
    if args.limit:
        recs = recs[:args.limit]
    os.makedirs(CACHE, exist_ok=True)
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    s = requests.Session()
    s.headers.update(H)
    ok = fail = skip = 0
    for i, r in enumerate(recs, 1):
        path = os.path.join(CACHE, f"OA{r['year']}_{r['id']}.pdf")
        if os.path.exists(path) and os.path.getsize(path) > 20_000:
            skip += 1
            continue
        if log.get(r["id"], {}).get("status") == "fail":
            continue
        try:
            resp = s.get(r["pdf"], timeout=120, allow_redirects=True)
            body = resp.content
            if resp.status_code == 200 and body[:5] == b"%PDF-" and len(body) > 20_000:
                with open(path, "wb") as fh:
                    fh.write(body)
                log[r["id"]] = {"status": "ok", "bytes": len(body)}
                ok += 1
            else:
                log[r["id"]] = {"status": "fail", "code": resp.status_code, "type": resp.headers.get("content-type", "")[:40]}
                fail += 1
        except Exception as exc:  # noqa: BLE001
            log[r["id"]] = {"status": "fail", "error": str(exc)[:120]}
            fail += 1
        if i % 20 == 0:
            json.dump(log, open(LOG, "w", encoding="utf-8"), indent=0)
            print(f"  {i}/{len(recs)}: ok {ok}, fail {fail}, cached {skip}", flush=True)
        time.sleep(args.delay)
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=0)
    print(f"done: ok {ok}, fail {fail}, cached {skip} of {len(recs)}")


if __name__ == "__main__":
    main()
