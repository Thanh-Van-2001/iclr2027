"""One-question human verification kit for the frozen set D items in audits/human.

Re-renders each item with the pipeline's winner cell boxed in red and its
runner-up boxed in blue, then writes label_simple.html: the page states the
pipeline's reading of the item in one line and the person answers correct /
wrong / unclear with one key. This is a verification design (the reader sees
the pipeline's values), and every use of its labels says so.

Usage: python study/human_verify_kit.py            # render + page
       python study/human_verify_kit.py --no-render # page only
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import fitz  # noqa: E402
from analyze import load_records  # noqa: E402
from harvest import SOURCES, _get  # noqa: E402

KIT = "audits/human"
ITEMS = "audits/gold_d/items.json"
EXTRACTED = "data/extracted_2025.jsonl"
SOURCE_NAMES = ["neurips2025", "icml2025"]
RENDER = "--no-render" not in sys.argv


def find_cell(t, value, disp, bold):
    for c in t["cells"]:
        if c["bold"] == bold and c["mean"] == value and c["dispersion"] == disp:
            return c
    for c in t["cells"]:
        if c["bold"] == bold and c["mean"] == value:
            return c
    return None


with open(ITEMS, encoding="utf-8") as fh:
    meta = {it["id"]: it for it in json.load(fh)}
with open(os.path.join(KIT, "labels.csv"), encoding="utf-8", newline="") as fh:
    ids = [r["id"] for r in csv.DictReader(fh)]
items = [meta[i] for i in ids]

if RENDER:
    recs = load_records(EXTRACTED)
    tables = {(r["id"], t.get("number"), t.get("page")): t for r in recs for t in r.get("tables", [])}
    index = {}
    for s in SOURCE_NAMES:
        for rec in SOURCES[s]():
            index[rec["id"]] = rec
    cache: dict = {}
    for it in items:
        t = tables.get((it["paper"], it["table"], it["page"]))
        pl = it["pipeline"]
        rival = find_cell(t, pl["runner_up"], pl["runner_dispersion"], False) if t else None
        it["rival_mark"] = {"x": rival["x"], "y": rival["y"]} if rival else None
        rec = index[it["paper"]]
        if it["paper"] not in cache:
            cache[it["paper"]] = _get(rec["pdf"])
        doc = fitz.open(stream=cache[it["paper"]], filetype="pdf")
        page = doc[it["page"]]
        b = it["bbox"]
        pad = 26.0
        clip = fitz.Rect(max(0, b["x_min"] - pad * 5.0), max(0, b["y_min"] - pad * 2.8),
                         min(page.rect.width, b["x_max"] + pad * 5.0),
                         min(page.rect.height, b["y_max"] + pad * 1.6))
        shape = page.new_shape()
        for mark, color in ((it.get("mark"), (1, 0, 0)), (it.get("rival_mark"), (0, 0.3, 1))):
            if mark:
                shape.draw_rect(fitz.Rect(mark["x"] - 4, mark["y"] - 3, mark["x"] + 30, mark["y"] + 11))
                shape.finish(color=color, width=0.9)
        shape.commit()
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=clip)
        name = f"{it['id']}_verify.png"
        pix.save(os.path.join(KIT, "img", name))
        print(it["id"], "rival box" if rival else "NO RIVAL CELL FOUND")
    with open(os.path.join(KIT, "verify_marks.json"), "w", encoding="utf-8") as fh:
        json.dump({it["id"]: it.get("rival_mark") for it in items}, fh)

marks = json.load(open(os.path.join(KIT, "verify_marks.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(KIT, "verify_marks.json")) else {}

KIND = {"std": "độ lệch chuẩn (SD)", "sem": "sai số chuẩn (SE)", "ci": "khoảng tin cậy (CI)",
        "unknown": "± không ghi là gì", "none": "không có ±"}
SRC = {"caption": "caption bảng", "page": "cùng trang", "paper": "chỗ khác trong paper"}


def fmt(v):
    return "không có" if v is None else str(v)


page_items = []
for it in items:
    pl = it["pipeline"]
    runs_path = os.path.join(KIT, "img", f"{it['id']}_runs.txt")
    runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else ""
    better = "cao hơn là tốt" if str(pl["direction"]).startswith("higher") else "thấp hơn là tốt"
    group = "cùng cột" if pl["orientation"] == "column" else "cùng hàng"
    lines = [f"<b style='color:#c00'>Ô đỏ</b> = <b>{fmt(pl['winner'])}</b>"
             + (f" ± {pl['winner_dispersion']}" if pl["winner_dispersion"] is not None else "")
             + " — in đậm, và là ô đậm duy nhất trong nhóm",
             f"<b style='color:#04c'>Ô xanh</b> = <b>{fmt(pl['runner_up'])}</b>"
             + (f" ± {pl['runner_dispersion']}" if pl["runner_dispersion"] is not None else "")
             + f" — ô tốt nhất trong các ô KHÔNG đậm {group} ({better})"]
    if it["stratum"] == "testable":
        lines.append("± là " + KIND.get(pl["dispersion_kind"], pl["dispersion_kind"]))
        if pl["n_runs"]:
            src = SRC.get(pl["n_runs_source"])
            lines.append(f"Số run/seed cho bảng này = <b>{pl['n_runs']}</b>" + (f" (máy lấy từ {src})" if src else ""))
        else:
            lines.append("Không cần số run (± là SE hoặc CI)" if pl["dispersion_kind"] in ("sem", "ci")
                         else "Số run/seed: máy không tìm thấy")
    else:
        lines.append("Không ô nào trong hai ô này có ± / SD / CI ở bất kỳ đâu trong bảng")
    page_items.append({"id": it["id"], "stratum": it["stratum"], "image": f"img/{it['id']}_verify.png",
                       "title": it.get("title", ""), "table": it.get("table"), "page": it.get("page"),
                       "claim": lines, "runs": runs, "n_runs": pl["n_runs"], "no_rival_box": not marks.get(it["id"])})
page_items.sort(key=lambda x: (x["stratum"] != "no_bar", x["id"]))

html = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>Kiểm tra 60 item</title>
<style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f5f5f5;color:#111}
header{padding:8px 14px;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button{padding:5px 10px;font-size:13px;cursor:pointer}
#guide{font-size:13px;padding:8px 14px;background:#fffbe6;border-bottom:1px solid #eee;line-height:1.5}
#wrap{display:flex;gap:10px;padding:10px;align-items:flex-start}
#left{flex:1 1 60%;min-width:0;background:#fff;border:1px solid #ddd;padding:6px;max-height:88vh;overflow:auto}
#left img{max-width:100%;cursor:zoom-in;display:block}
#left img.zoom{max-width:none;cursor:zoom-out}
#right{flex:0 0 480px;background:#fff;border:1px solid #ddd;padding:12px;max-height:88vh;overflow:auto}
#claim{font-size:15px;line-height:1.6;background:#f3f7ff;border:1px solid #cfe0ff;padding:10px;margin:8px 0}
#claim div{margin:3px 0}
.meta{font-size:12px;color:#555}
#runs{font-size:12px;white-space:pre-wrap;background:#f7f7f7;border:1px solid #e5e5e5;padding:6px;max-height:150px;overflow:auto;margin:6px 0}
#runs mark{background:#ffe08a}
.big{display:flex;gap:8px;margin:10px 0}
.big button{flex:1;font-size:16px;padding:12px 6px}
.big button.sel{outline:3px solid #333}
#note{width:100%;box-sizing:border-box;padding:6px;font-size:14px}
#prog{font-variant-numeric:tabular-nums}
.warn{color:#b00;font-size:12px}
#ta{width:100%;height:100px;font-size:11px;display:none}
</style></head><body>
<header><b>Kiểm tra set D</b> <span id="prog"></span>
<button onclick="exportCsv()">Xuất verify.csv</button>
<button onclick="copyCsv()">Copy CSV</button>
<button onclick="if(confirm('Xoá toàn bộ?')){localStorage.removeItem(KEY);labels={};go(0)}">Xoá hết</button>
</header>
<div id="guide"><b>Một câu hỏi mỗi item:</b> máy đọc bảng như ghi trong ô xanh nhạt bên phải. Nhìn ảnh, thấy <b>đúng hết</b> thì bấm <b>1</b>,
<b>sai bất kỳ điểm nào</b> (ô đỏ không đậm / có ô đậm khác cùng nhóm / ô xanh không phải tốt nhất trong ô không đậm / số hoặc ± lệch / số run không đúng bảng này) bấm <b>2</b>,
không nhìn rõ bấm <b>3</b>. Bấm số là tự sang item sau; muốn ghi chú thì gõ vào ô ghi chú rồi Enter. <b>Alt+←/→</b> lùi/tiến, click ảnh phóng to.
Xong bấm <b>Xuất verify.csv</b>, lưu vào <code>audits/human/</code>. Tự lưu trong trình duyệt, nghỉ giữa chừng được.</div>
<div id="wrap">
<div id="left"><img id="img" src="" alt="" onclick="this.classList.toggle('zoom')"></div>
<div id="right">
<div class="meta" id="meta"></div>
<div id="claim"></div>
<div id="runsbox"><div class="meta">Câu có seed/run/trial trong paper (để kiểm tra số run):</div><div id="runs"></div></div>
<div class="big">
<button id="b1" onclick="answer('correct')">1 &nbsp;Đúng</button>
<button id="b2" onclick="answer('wrong')">2 &nbsp;Sai</button>
<button id="b3" onclick="answer('unclear')">3 &nbsp;Không rõ</button>
</div>
<input id="note" placeholder="Ghi chú (tuỳ chọn) — Enter để sang item sau">
<div style="display:flex;gap:6px;margin-top:8px"><button onclick="go(cur-1)">← Trước</button><button onclick="go(cur+1)">Sau →</button></div>
<textarea id="ta"></textarea>
</div></div>
<script>
const ITEMS = __ITEMS__;
const KEY = 'iclr_human_verify_v1';
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { labels = {}; }
let cur = ITEMS.findIndex(x => !(labels[x.id] && labels[x.id].verdict)); if (cur < 0) cur = 0;
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
function hl(s, n) {
  let h = esc(s).replace(/(seeds?|runs?|trials?|repetitions?|repeat\w*|folds?|restarts?|independent)/gi, '<mark>$1</mark>');
  if (n) {
    const words = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 20: 'twenty'};
    const alt = words[n] ? '(?:' + n + '|' + words[n] + ')' : String(n);
    h = h.replace(new RegExp('\\b' + alt + '\\b', 'gi'), m => '<mark><b>' + m + '</b></mark>');
  }
  return h;
}
function render() {
  const it = ITEMS[cur]; const lb = labels[it.id] || {};
  document.getElementById('img').src = it.image; document.getElementById('img').classList.remove('zoom');
  document.getElementById('meta').innerHTML = '<b>Item ' + it.id + '</b> (' + (cur + 1) + '/' + ITEMS.length + ') — ' + esc(it.title) + ' — Table ' + esc(it.table) + ' &nbsp; <a href="' + it.image + '" target="_blank">ảnh gốc</a>';
  document.getElementById('claim').innerHTML = it.claim.map(l => '<div>' + l + '</div>').join('') + (it.no_rival_box ? '<div class="warn">(không vẽ được ô xanh: tự tìm ô tốt nhất không đậm cùng nhóm)</div>' : '');
  const rb = document.getElementById('runsbox'); rb.style.display = (it.stratum === 'testable' && it.runs) ? 'block' : 'none';
  document.getElementById('runs').innerHTML = hl(it.runs, it.n_runs);
  ['correct', 'wrong', 'unclear'].forEach((v, i) => document.getElementById('b' + (i + 1)).classList.toggle('sel', lb.verdict === v));
  document.getElementById('note').value = lb.note || '';
  document.getElementById('note').blur();
  updateProg();
}
function save(patch) {
  const it = ITEMS[cur]; labels[it.id] = Object.assign(labels[it.id] || {}, patch);
  try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {}
  updateProg();
}
function answer(v) {
  save({ verdict: v, note: document.getElementById('note').value.trim() });
  if (cur + 1 < ITEMS.length) go(cur + 1); else { render(); alert('Xong ' + ITEMS.length + ' item. Bấm "Xuất verify.csv".'); }
}
function go(i) { save({ note: document.getElementById('note').value.trim() }); if (i < 0 || i >= ITEMS.length) return; cur = i; render(); window.scrollTo(0, 0); }
function updateProg() {
  const n = ITEMS.filter(x => labels[x.id] && labels[x.id].verdict).length;
  document.getElementById('prog').textContent = n + '/' + ITEMS.length + ' xong';
}
document.addEventListener('keydown', ev => {
  const inNote = document.activeElement && document.activeElement.id === 'note';
  if (ev.altKey && ev.key === 'ArrowLeft') { ev.preventDefault(); go(cur - 1); return; }
  if (ev.altKey && ev.key === 'ArrowRight') { ev.preventDefault(); go(cur + 1); return; }
  if (inNote) { if (ev.key === 'Enter') { ev.preventDefault(); const lb = labels[ITEMS[cur].id]; if (lb && lb.verdict) go(cur + 1); else save({ note: document.activeElement.value.trim() }); } return; }
  if (ev.key === '1') answer('correct'); else if (ev.key === '2') answer('wrong'); else if (ev.key === '3') answer('unclear');
});
function csvCell(s) { s = String(s == null ? '' : s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
function buildCsv() {
  const rows = ['id,stratum,verdict,note'];
  ITEMS.slice().sort((a, b) => a.id.localeCompare(b.id)).forEach(it => { const lb = labels[it.id] || {}; rows.push([it.id, it.stratum, lb.verdict || '', csvCell(lb.note || '')].join(',')); });
  return rows.join('\n') + '\n';
}
function exportCsv() {
  save({ note: document.getElementById('note').value.trim() });
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([buildCsv()], { type: 'text/csv' })); a.download = 'verify.csv'; document.body.appendChild(a); a.click(); a.remove();
}
function copyCsv() { const ta = document.getElementById('ta'); ta.style.display = 'block'; ta.value = buildCsv(); ta.select(); try { navigator.clipboard.writeText(ta.value); } catch (e) {} }
render();
</script></body></html>
"""
html = html.replace("__ITEMS__", json.dumps(page_items, ensure_ascii=False))
out = os.path.join(KIT, "label_simple.html")
with open(out, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(html)
print("wrote", out, len(page_items), "items")
