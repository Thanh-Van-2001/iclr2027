"""Write labels.csv from a reader workflow's returned rows.

Usage: python aamas/wf_rows_to_labels.py <wf_run.json> <out_dir>
The run record is the JSON the Workflow tool writes under workflows/; its
"result" holds {"rows": [...]}. Columns follow gold_set.FIELDS, in the same
order as labels_template.csv, so gold_set.py score and agree read it as is.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "study"))
from gold_set import FIELDS  # noqa: E402

run_path, out_dir = sys.argv[1], sys.argv[2]
with open(run_path, encoding="utf-8") as fh:
    rows = json.load(fh)["result"]["rows"]
cols = ["id", "stratum"] + sorted({f for fs in FIELDS.values() for f in fs})
seen = set()
with open(os.path.join(out_dir, "labels.csv"), "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        w.writerow({c: r.get(c, "") for c in cols})
print(len(seen), "rows ->", os.path.join(out_dir, "labels.csv"))
