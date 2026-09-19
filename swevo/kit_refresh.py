"""Refresh the two human kits in place, without redrawing their items (a
second vendor's model has already answered them): recompute the Mean/Std-row
kit's strata with the deviation parser that strips a trailing verdict marker
(the builder's flag missed deviations printed as "(9.69e-4)-"), and add one
question to both labelling sheets, whether every bold cell of the table lies
in one row or column, so that a person's labels also measure the whole-row
convention the census protocol does not distinguish.

Usage: python swevo/kit_refresh.py
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from census_readings import _disp  # noqa: E402

KITS = ["audits/swevo_human", "audits/swevo_human_rows"]
QUESTION = ("<p><b>whole_row_bold</b>: y if every bold cell of this table lies in one row or one column (a proposed method's row set in bold, "
            "or a header row), n if bold marks one cell per group.</p>")


def restrata(kit: str) -> dict:
    path = os.path.join(kit, "items.json")
    items = json.load(open(path, encoding="utf-8"))
    changed = 0
    for it in items:
        if "stratum" not in it:
            return {}
        rd = it.get("reader", {})
        barred = _disp(rd.get("winner_disp")) is not None and _disp(rd.get("runner_disp")) is not None
        st = "barred" if barred else "barless"
        if st != it["stratum"]:
            changed += 1
            it["stratum_at_draw"] = it["stratum"]
            it["stratum"] = st
            it["barred_after"] = barred
    json.dump(items, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    strata = {k: sum(1 for g in items if g["stratum"] == k) for k in ("barred", "barless")}
    dpath = os.path.join(kit, "draw.json")
    if os.path.exists(dpath):
        d = json.load(open(dpath, encoding="utf-8"))
        d["strata_at_draw"] = d.get("strata_at_draw", d.get("strata"))
        d["strata"] = strata
        d["restrata_changed"] = changed
        json.dump(d, open(dpath, "w", encoding="utf-8"), indent=1)
    return {"changed": changed, "strata": strata}


def add_question(kit: str) -> bool:
    path = os.path.join(kit, "label.html")
    s = open(path, encoding="utf-8").read()
    if "whole_row_bold" in s:
        return False
    s = s.replace("<form id='f'>", QUESTION + "<form id='f'>", 1)
    s = s.replace("bold_ok <input type='text' name='bo_", "bold_ok <input type='text' name='bo_")
    import re
    s = re.sub(r"(bold_ok <input type='text' name='bo_(\d+)' size='2'>)", r"\1 whole_row_bold <input type='text' name='wr_\2' size='2'>", s)
    s = s.replace("let out='id,results_table,bold_ok,", "let out='id,results_table,bold_ok,whole_row_bold,", 1)
    s = s.replace("out+=[i,v('rt'),v('bo'),", "out+=[i,v('rt'),v('bo'),v('wr'),", 1)
    open(path, "w", encoding="utf-8").write(s)
    tpath = os.path.join(kit, "labels_template.csv")
    rows = list(csv.reader(open(tpath, encoding="utf-8", newline="")))
    if rows and "whole_row_bold" not in rows[0]:
        k = rows[0].index("bold_ok") + 1
        for r in rows:
            r.insert(k, "whole_row_bold" if r is rows[0] else "")
        with open(tpath, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh).writerows(rows)
    return True


def main() -> int:
    for kit in KITS:
        if not os.path.exists(os.path.join(kit, "items.json")):
            continue
        print(kit, "strata:", restrata(kit), "question added:", add_question(kit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
