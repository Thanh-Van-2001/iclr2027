"""Record what the other publishers of the pre-registered corpus answer to a
polite, throttled PDF request: five listed papers per journal, one request
every five seconds, the OpenAlex PDF URL and then the publisher's own URL
pattern. The status codes are the run record behind the corpus deviation
stated in the paper. Nothing is retried and nothing is scraped around.

Usage: python swevo/fetch_attempts.py  -> out/swevo/fetch_attempts.json
"""
import json
import os
import random
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harvest_oa import JOURNALS  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}


def publisher_url(rec: dict) -> str | None:
    doi = (rec.get("doi") or "").replace("https://doi.org/", "")
    if not doi:
        return None
    if doi.startswith("10.3390/"):          # MDPI: the DOI resolves to the landing page; /pdf is the file
        return f"https://www.mdpi.com/{doi.split('/', 1)[1]}/pdf"
    if doi.startswith("10.1007/"):          # Springer
        return f"https://link.springer.com/content/pdf/{doi}.pdf"
    if doi.startswith("10.7717/"):          # PeerJ
        return f"https://peerj.com/articles/{doi.split('/')[-1]}.pdf"
    if doi.startswith("10.1038/"):          # Nature
        return f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf"
    return None


def attempt(url: str) -> dict:
    try:
        r = requests.get(url, headers=UA, timeout=60, allow_redirects=True, stream=True)
        head = r.raw.read(4096, decode_content=True) if r.status_code == 200 else b""
        r.close()
        return {"url": url, "status": r.status_code, "content_type": r.headers.get("Content-Type", ""),
                "is_pdf": head.startswith(b"%PDF"), "server": r.headers.get("Server", ""),
                "final_url": r.url[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": None, "error": str(exc)[:200]}


def main() -> int:
    index = json.load(open("out/swevo/index.json", encoding="utf-8"))
    rng = random.Random(2026)
    out = {"rule": "five random listed papers per journal, OpenAlex PDF URL then the publisher pattern, five seconds apart, no retries", "journals": {}}
    for issn, name in JOURNALS:
        recs = [r for r in index if r["journal"] == name]
        if not recs:
            continue
        sample = rng.sample(recs, min(5, len(recs)))
        rows = []
        for rec in sample:
            for label, url in (("openalex", rec.get("pdf")), ("publisher", publisher_url(rec))):
                if not url:
                    continue
                res = attempt(url)
                res["source"] = label
                res["id"] = rec["id"]
                rows.append(res)
                print(name[:22].ljust(22), label.ljust(9), res.get("status"), res.get("is_pdf"), res.get("server", "")[:20], flush=True)
                time.sleep(5)
        out["journals"][name] = {"listed": len(recs), "attempts": rows,
                                 "pdf_ok": sum(1 for r in rows if r.get("is_pdf")),
                                 "statuses": sorted({str(r.get("status")) for r in rows})}
    json.dump(out, open("out/swevo/fetch_attempts.json", "w", encoding="utf-8"), indent=1)
    print("wrote out/swevo/fetch_attempts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
