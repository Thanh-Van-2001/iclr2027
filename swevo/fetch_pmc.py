"""Fetch the listed papers of the journals Europe PMC mirrors (Biomimetics,
PeerJ Computer Science) through its REST API and PDF endpoint, the
sanctioned route a review of the second submission pointed to. One request
every two seconds; resumable; the log records every DOI's outcome.

Usage: python swevo/fetch_pmc.py [--journal "Biomimetics"] [--limit N]
"""
import argparse
import json
import os
import sys
import time

import requests

UA = {"User-Agent": "paper-audit/0.1 (mailto:audit@example.org)", "Accept": "*/*"}
OUT_DIR = "data/corpus_oa"
LOG = "out/swevo/fetch_pmc_log.json"


def pmcid_for(doi: str) -> str | None:
    r = requests.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                     params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 3, "resultType": "lite"},
                     headers=UA, timeout=60)
    r.raise_for_status()
    for x in r.json().get("resultList", {}).get("result", []):
        if x.get("pmcid"):
            return x["pmcid"]
    return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", default="out/swevo/index.json")
    ap.add_argument("--journal", action="append", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=2.0)
    args = ap.parse_args(argv)
    journals = args.journal or ["Biomimetics", "PeerJ Computer Science"]
    recs = [r for r in json.load(open(args.index, encoding="utf-8")) if r["journal"] in journals]
    if args.limit:
        recs = recs[:args.limit]
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    os.makedirs(OUT_DIR, exist_ok=True)
    ok = fail = cached = 0
    for i, rec in enumerate(recs, 1):
        path = os.path.join(OUT_DIR, f"{rec['venue']}{rec['year']}_{rec['id']}.pdf")
        if os.path.exists(path) and os.path.getsize(path) > 20_000:
            cached += 1
            continue
        doi = (rec.get("doi") or "").replace("https://doi.org/", "")
        entry = {"journal": rec["journal"], "doi": doi}
        try:
            pmcid = pmcid_for(doi) if doi else None
            entry["pmcid"] = pmcid
            if not pmcid:
                entry["status"] = "no pmcid"
                fail += 1
            else:
                time.sleep(args.delay)
                r = requests.get(f"https://europepmc.org/articles/{pmcid}?pdf=render", headers=UA, timeout=120)
                entry["http"] = r.status_code
                if r.status_code == 200 and r.content.startswith(b"%PDF"):
                    open(path, "wb").write(r.content)
                    entry["status"] = "ok"
                    entry["bytes"] = len(r.content)
                    ok += 1
                else:
                    entry["status"] = "not a pdf"
                    fail += 1
        except Exception as exc:  # noqa: BLE001
            entry["status"] = f"error: {str(exc)[:120]}"
            fail += 1
        log[rec["id"]] = entry
        json.dump(log, open(LOG, "w", encoding="utf-8"), indent=1)
        if i % 20 == 0:
            print(f"  {i}/{len(recs)}: ok {ok}, fail {fail}, cached {cached}", flush=True)
        time.sleep(args.delay)
    print(f"done: ok {ok}, fail {fail}, cached {cached} of {len(recs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
