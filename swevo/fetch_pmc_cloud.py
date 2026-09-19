"""Fetch the PDFs of the listed papers that Europe PMC mirrors (Biomimetics,
PeerJ Computer Science) through PMC's sanctioned bulk route, the PMC Open
Access Subset on AWS (bucket pmc-oa-opendata over plain HTTPS, no login):
DOI -> PMCID through the NCBI ID converter, then the bucket listing under
the PMCID prefix gives the PDF key. Found after review; the paper says so.
PDFs go to a second cache with the same naming the pipeline expects, so
that the text scan, the classifier and the frozen parser run on them
unchanged; the image census is not extended to them.

Usage: python swevo/fetch_pmc_cloud.py [--journal Biomimetics --journal "PeerJ Computer Science"] [--cache data/corpus_pmc]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

INDEX = "out/swevo/index.json"
LOG = "out/swevo/fetch_pmc_cloud_log.json"
IDCONV = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids={ids}&format=json&tool=checkable-metaheuristics&email=anon@example.org"
BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com/"
H = {"User-Agent": "Mozilla/5.0 (research corpus fetch; one request per second)"}


def _get(url: str, timeout: int = 120) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=timeout).read()


def pmcids(dois: list) -> dict:
    out = {}
    for i in range(0, len(dois), 150):
        chunk = dois[i:i + 150]
        j = json.loads(_get(IDCONV.format(ids=urllib.parse.quote(",".join(chunk)))).decode())
        for r in j.get("records", []):
            if r.get("pmcid"):
                out[r.get("doi", "").lower()] = r["pmcid"]
        time.sleep(1)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", action="append", default=None)
    ap.add_argument("--cache", default="data/corpus_pmc")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args(argv)
    journals = args.journal or ["Biomimetics", "PeerJ Computer Science"]
    recs = [r for r in json.load(open(INDEX, encoding="utf-8")) if r["journal"] in journals]
    os.makedirs(args.cache, exist_ok=True)
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {"route": "PMC Open Access Subset on AWS (pmc-oa-opendata, HTTPS), PMCID from the NCBI ID converter", "papers": {}}
    todo = [r for r in recs if not os.path.exists(os.path.join(args.cache, f"OA{r['year']}_{r['id']}.pdf"))]
    ids = pmcids([r["doi"] for r in todo if r.get("doi")])
    print(f"{len(recs)} listed, {len(todo)} to fetch, {len(ids)} PMCIDs resolved", flush=True)
    ok = fail = 0
    for i, r in enumerate(todo, 1):
        path = os.path.join(args.cache, f"OA{r['year']}_{r['id']}.pdf")
        pmc = ids.get(str(r.get("doi", "")).lower())
        entry = {"journal": r["journal"], "doi": r.get("doi"), "pmcid": pmc}
        try:
            if not pmc:
                raise RuntimeError("no PMCID")
            listing = _get(f"{BUCKET}?list-type=2&prefix={pmc}.&max-keys=20").decode()
            keys = [k for k in re.findall(r"<Key>([^<]+)</Key>", listing) if k.endswith(".pdf")]
            if not keys:
                raise RuntimeError("no pdf in bucket")
            body = _get(BUCKET + keys[0], timeout=300)
            if body[:5] != b"%PDF-" or len(body) < 20_000:
                raise RuntimeError(f"not a pdf ({len(body)} bytes)")
            open(path, "wb").write(body)
            entry.update(status="ok", key=keys[0], bytes=len(body))
            ok += 1
        except Exception as exc:  # noqa: BLE001
            entry.update(status="fail", error=str(exc)[:120])
            fail += 1
        log["papers"][r["id"]] = entry
        if i % 20 == 0 or i == len(todo):
            json.dump(log, open(LOG, "w", encoding="utf-8"), indent=0)
            print(f"  {i}/{len(todo)}: ok {ok}, fail {fail}", flush=True)
        time.sleep(args.delay)
    json.dump(log, open(LOG, "w", encoding="utf-8"), indent=0)
    print("done: ok", ok, "fail", fail, "->", args.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
