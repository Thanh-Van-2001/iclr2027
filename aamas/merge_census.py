"""Merge the sharded census readings into audits/aamas_census/labels.json,
in item order, and report coverage."""
import glob
import json
import os

KIT = "audits/aamas_census"
items = json.load(open(os.path.join(KIT, "items.json"), encoding="utf-8"))
pages = {}
for path in sorted(glob.glob(os.path.join(KIT, "labels_shard*.json"))):
    for p in json.load(open(path, encoding="utf-8")):
        if not str(p.get("note", "")).startswith("failed"):
            pages[p["id"]] = p
merged = [pages[it["id"]] for it in items if it["id"] in pages]
json.dump(merged, open(os.path.join(KIT, "labels.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
failed = sum(1 for path in glob.glob(os.path.join(KIT, "labels_shard*.json"))
             for p in json.load(open(path, encoding="utf-8")) if str(p.get("note", "")).startswith("failed"))
print(len(merged), "of", len(items), "pages read;", failed, "failed")
