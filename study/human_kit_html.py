"""Build audits/human/label.html: a single-file, offline labelling page for the
human reference kit. It embeds the item list and the paper's run sentences,
shows each cropped table, autosaves to the browser's localStorage and exports
labels.csv in the exact template layout that gold_set.py score reads."""
import csv
import json
import os
import sys

QUICK = "--quick" in sys.argv
argv = [a for a in sys.argv[1:] if a != "--quick"]
KIT = argv[0] if argv else "audits/human"
ITEMS = argv[1] if len(argv) > 1 else "audits/gold_d/items.json"

with open(ITEMS, encoding="utf-8") as fh:
    meta = {it["id"]: it for it in json.load(fh)}
with open(os.path.join(KIT, "labels.csv"), encoding="utf-8", newline="") as fh:
    reader = csv.DictReader(fh)
    columns = reader.fieldnames
    rows = list(reader)

items = []
for r in rows:
    it = meta[r["id"]]
    runs_path = os.path.join(KIT, "img", f"{r['id']}_runs.txt")
    runs = open(runs_path, encoding="utf-8").read() if os.path.exists(runs_path) else ""
    rec = {"id": r["id"], "stratum": r["stratum"], "image": "img/" + it["image"],
           "title": it.get("title", ""), "page": it.get("page"), "table": it.get("table"),
           "runs": runs}
    if QUICK:
        # Verification design: the pipeline's reading is shown and the person
        # confirms or corrects it. Disclosed as such wherever the labels are used.
        pl = it["pipeline"]
        kind = {"std": "sd", "sem": "se", "ci": "ci", "unknown": "unlabelled", "none": "none"}.get(pl.get("dispersion_kind"), "unlabelled")
        num = lambda v: "none" if v is None else str(v)
        pre = {"results_table": "y", "bold_ok": "y",
               "orientation": pl.get("orientation", ""),
               "direction": "higher" if str(pl.get("direction", "")).startswith("higher") else "lower",
               "winner_mean": num(pl.get("winner")), "runner_mean": num(pl.get("runner_up"))}
        if r["stratum"] == "testable":
            pre.update({"winner_disp": num(pl.get("winner_dispersion")), "runner_disp": num(pl.get("runner_dispersion")),
                        "disp_type": kind, "n_runs": num(pl.get("n_runs")),
                        "n_source": pl.get("n_runs_source") or "none", "rival_copied": "n"})
        else:
            pre["error_bar_present"] = "n"
        rec["prefill"] = pre
    items.append(rec)
# Warm-up order: the 20 quick no_bar items first, then the 40 testable ones.
items.sort(key=lambda x: (x["stratum"] != "no_bar", x["id"]))

FIELDS = {
    "testable": [
        ("results_table", "Bảng kết quả thí nghiệm?", ["y", "n"]),
        ("bold_ok", "Ô khung đỏ IN ĐẬM và là ô đậm DUY NHẤT trong nhóm?", ["y", "n"]),
        ("orientation", "Nhóm so sánh là cột hay hàng?", ["column", "row"]),
        ("direction", "Cao hơn tốt hay thấp hơn tốt?", ["higher", "lower"]),
        ("winner_mean", "Số trong ô khung (dán cả '85.2 ± 0.3' cũng được, tự tách)", None),
        ("winner_disp", "Phần ± của ô khung ('none' nếu không có)", None),
        ("runner_mean", "Số TỐT NHẤT trong các ô KHÔNG đậm cùng nhóm", None),
        ("runner_disp", "Phần ± của ô đó ('none' nếu không có)", None),
        ("disp_type", "± là gì? (theo caption / câu bên phải)", ["unlabelled", "sd", "se", "ci"]),
        ("n_runs", "Số run/seed cho bảng này ('none' nếu không tìm thấy)", None),
        ("n_source", "Tìm thấy ở đâu?", ["caption", "page", "paper", "none"]),
        ("rival_copied", "Ô runner-up có trích dẫn / † / * / 'from'? (số chép từ paper khác)", ["n", "y", "unclear"]),
        ("note", "Ghi chú (tuỳ chọn)", "free"),
    ],
    "no_bar": [
        ("results_table", "Bảng kết quả thí nghiệm?", ["y", "n"]),
        ("bold_ok", "Ô khung đỏ IN ĐẬM và là ô đậm DUY NHẤT trong nhóm?", ["y", "n"]),
        ("orientation", "Nhóm so sánh là cột hay hàng?", ["column", "row"]),
        ("direction", "Cao hơn tốt hay thấp hơn tốt?", ["higher", "lower"]),
        ("winner_mean", "Số trong ô khung", None),
        ("runner_mean", "Số TỐT NHẤT trong các ô KHÔNG đậm cùng nhóm", None),
        ("error_bar_present", "Bảng có in BẤT KỲ ± / SD / CI nào cho ô khung hoặc runner-up không?", ["n", "y"]),
        ("note", "Ghi chú (tuỳ chọn)", "free"),
    ],
}

GUIDE_QUICK = """
<b>Chế độ kiểm tra:</b> mọi ô đã được điền sẵn theo máy đọc. Anh nhìn ảnh, đối chiếu 4 số + ± + số run;
<b>đúng thì Enter liên tục</b> cho hết form (Enter ở câu cuối = lưu &amp; item tiếp), <b>sai thì sửa</b> rồi Enter.
Riêng hai câu đầu (bảng kết quả? ô khung in đậm và đậm duy nhất?) máy luôn điền <code>y</code> — anh phải tự nhìn.
Không đọc được → <code>unclear</code>. Xong bấm <b>Xuất labels_quick.csv</b>, lưu vào <code>audits/human/</code>. <b>Alt+←/→</b> lùi/tiến, click ảnh phóng to.
"""
GUIDE = """
<b>Cách làm (đọc 1 lần):</b> ảnh bên trái là bảng đã cắt, ô <span style="color:#c00">khung đỏ</span> là ô pipeline
cho là "winner". Anh chỉ cần trả lời các câu bên phải theo thứ tự; <b>Enter</b> = sang câu tiếp, ở câu cuối
<b>Enter</b> = lưu &amp; sang item tiếp. Với câu chọn: gõ chữ đầu (y/n, c/r, h/l...) rồi Enter.
Không đọc được số nào thì gõ <code>unclear</code>. Số run/seed: tìm trong caption của bảng hoặc trong hộp
"Câu có seed/run/trial" (đã trích từ cả paper); nếu paper nói nhiều số khác nhau, lấy số áp dụng cho bảng này.
Tự động lưu trong trình duyệt sau mỗi phím; xong bấm <b>Xuất labels.csv</b> và lưu đè vào
<code>audits/human/labels.csv</code>. Không mở <code>audits/gold_d/labels.csv</code> (kết quả máy, cần giữ mù).
<b>Alt+←/→</b> lùi/tiến item, click ảnh để phóng to.
"""

html = r"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>Chấm 60 item (set D)</title>
<style>
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#f5f5f5;color:#111}
header{padding:8px 14px;background:#fff;border-bottom:1px solid #ddd;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header b{font-size:15px}
button{padding:5px 10px;font-size:13px;cursor:pointer}
#guide{font-size:13px;padding:8px 14px;background:#fffbe6;border-bottom:1px solid #eee;line-height:1.45}
#wrap{display:flex;gap:10px;padding:10px;align-items:flex-start}
#left{flex:1 1 60%;min-width:0;background:#fff;border:1px solid #ddd;padding:6px;max-height:88vh;overflow:auto}
#left img{max-width:100%;cursor:zoom-in;display:block}
#left img.zoom{max-width:none;cursor:zoom-out}
#right{flex:0 0 470px;background:#fff;border:1px solid #ddd;padding:10px;max-height:88vh;overflow:auto}
.q{margin:6px 0}
.q label{display:block;font-size:12.5px;color:#333;margin-bottom:2px}
.q input,.q select{width:100%;box-sizing:border-box;padding:5px 6px;font-size:14px;border:1px solid #bbb;border-radius:3px}
.q input.missing,.q select.missing{border-color:#e33;background:#fff4f4}
#runs{font-size:12px;white-space:pre-wrap;background:#f7f7f7;border:1px solid #e5e5e5;padding:6px;max-height:170px;overflow:auto;margin:6px 0 8px}
#runs mark{background:#ffe08a}
.meta{font-size:12px;color:#555;margin-bottom:4px}
#nav{display:flex;gap:6px;margin-top:8px}
#prog{font-variant-numeric:tabular-nums}
.done{color:#080}
#ta{width:100%;height:120px;font-size:11px;display:none}
</style></head><body>
<header><b>Chấm set D__MODE__</b> <span id="prog"></span>
<button onclick="exportCsv()">Xuất labels.csv</button>
<label style="font-size:13px">Nhập CSV cũ <input type="file" id="imp" accept=".csv" style="font-size:12px"></label>
<button onclick="copyCsv()">Copy CSV</button>
<button onclick="if(confirm('Xoá toàn bộ nhãn đã lưu trong trình duyệt?')){localStorage.removeItem(KEY);labels={};render()}">Xoá hết</button>
<button onclick="document.getElementById('guide').hidden=!document.getElementById('guide').hidden">Ẩn/hiện hướng dẫn</button>
</header>
<div id="guide">__GUIDE__</div>
<div id="wrap">
<div id="left"><img id="img" src="" alt="" onclick="this.classList.toggle('zoom')"></div>
<div id="right">
<div class="meta" id="meta"></div>
<div class="meta">Câu có seed/run/trial trong paper:</div>
<div id="runs"></div>
<div id="form"></div>
<div id="nav"><button onclick="go(cur-1)">← Trước (Alt+←)</button><button onclick="saveAndNext()">Lưu &amp; tiếp (Enter)</button><button onclick="go(cur+1)">Sau → (Alt+→)</button></div>
<textarea id="ta"></textarea>
</div></div>
<script>
const ITEMS = __ITEMS__;
const FIELDS = __FIELDS__;
const COLUMNS = __COLUMNS__;
const QUICK = __QUICK__;
const KEY = QUICK ? 'iclr_human_labels_quick_v1' : 'iclr_human_labels_v1';
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { labels = {}; }
let cur = 0;
for (let i = 0; i < ITEMS.length; i++) { if (!isDone(ITEMS[i].id)) { cur = i; break; } if (i === ITEMS.length - 1) cur = 0; }

function isDone(id) {
  const it = ITEMS.find(x => x.id === id); const lb = labels[id]; if (!lb) return false;
  return FIELDS[it.stratum].every(f => f[0] === 'note' || (lb[f[0]] || '').trim() !== '');
}
function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); }
function hl(s) { return esc(s).replace(/(\b\d+\b|seeds?|runs?|trials?|repetitions?|repeat\w*|folds?|restarts?|independent)/gi, '<mark>$1</mark>'); }

function render() {
  const it = ITEMS[cur]; const lb = labels[it.id] || (QUICK ? Object.assign({}, it.prefill) : {});
  document.getElementById('img').src = it.image; document.getElementById('img').classList.remove('zoom');
  document.getElementById('meta').innerHTML = '<b>Item ' + it.id + '</b> (' + it.stratum + ', ' + (cur + 1) + '/' + ITEMS.length + ') — ' + esc(it.title) + ' — Table ' + esc(it.table) + ', trang ' + esc(it.page) + ' &nbsp; <a href="' + it.image + '" target="_blank">ảnh gốc</a>';
  document.getElementById('runs').innerHTML = it.runs ? hl(it.runs) : '<i>(không có câu nào — với item no_bar không cần run count)</i>';
  let h = '';
  for (const [name, label, opts] of FIELDS[it.stratum]) {
    const v = lb[name] || '';
    h += '<div class="q"><label>' + esc(label) + '</label>';
    if (Array.isArray(opts)) {
      h += '<select data-f="' + name + '"><option value="">--</option>' + opts.map(o => '<option' + (v === o ? ' selected' : '') + '>' + o + '</option>').join('') + '</select>';
    } else {
      h += '<input data-f="' + name + '" value="' + esc(v).replace(/"/g, '&quot;') + '" autocomplete="off">';
    }
    h += '</div>';
  }
  document.getElementById('form').innerHTML = h;
  const els = document.querySelectorAll('#form [data-f]');
  els.forEach((el, i) => {
    el.addEventListener('input', () => { store(); });
    el.addEventListener('change', () => { store(); });
    el.addEventListener('keydown', ev => {
      if (ev.key === 'Enter') {
        ev.preventDefault();
        if (el.tagName === 'INPUT') splitPm(el);
        store();
        if (i + 1 < els.length) { els[i + 1].focus(); if (els[i + 1].tagName === 'INPUT') els[i + 1].select(); }
        else saveAndNext();
      }
    });
  });
  if (els.length) { els[0].focus(); }
  updateProg();
}
function splitPm(el) {
  // "85.2 ± 0.3", "85.2+-0.3", "85.2 (0.3)" typed into a mean field fills the ± field next to it.
  const f = el.dataset.f; if (!f.endsWith('_mean')) return;
  const disp = f.replace('_mean', '_disp'); const dEl = document.querySelector('#form [data-f="' + disp + '"]'); if (!dEl) return;
  let m = el.value.match(/^\s*(-?[\d.]+)\s*(?:±|\+\/?-|\+-|\(|\{)\s*(-?[\d.]+)/);
  if (m) { el.value = m[1]; if (!dEl.value) dEl.value = m[2]; }
}
function store() {
  const it = ITEMS[cur]; const lb = labels[it.id] || {};
  document.querySelectorAll('#form [data-f]').forEach(el => { lb[el.dataset.f] = el.value.trim(); });
  labels[it.id] = lb;
  try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {}
  updateProg();
}
function updateProg() {
  const n = ITEMS.filter(x => isDone(x.id)).length;
  document.getElementById('prog').innerHTML = '<span class="' + (n === ITEMS.length ? 'done' : '') + '">' + n + '/' + ITEMS.length + ' xong</span>';
}
function saveAndNext() {
  document.querySelectorAll('#form input[data-f]').forEach(splitPm);
  store();
  const it = ITEMS[cur]; let missing = false;
  document.querySelectorAll('#form [data-f]').forEach(el => {
    const bad = el.dataset.f !== 'note' && el.value.trim() === '';
    el.classList.toggle('missing', bad); if (bad) missing = true;
  });
  if (missing) { document.querySelector('#form .missing').focus(); return; }
  if (cur + 1 < ITEMS.length) go(cur + 1); else { updateProg(); alert('Xong ' + ITEMS.length + ' item. Bấm "Xuất labels.csv".'); }
}
function go(i) { store(); if (i < 0 || i >= ITEMS.length) return; cur = i; render(); window.scrollTo(0, 0); }
document.addEventListener('keydown', ev => {
  if (ev.altKey && ev.key === 'ArrowLeft') { ev.preventDefault(); go(cur - 1); }
  if (ev.altKey && ev.key === 'ArrowRight') { ev.preventDefault(); go(cur + 1); }
});
function csvCell(s) { s = String(s == null ? '' : s); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
function buildCsv() {
  const byId = ITEMS.slice().sort((a, b) => a.id.localeCompare(b.id));
  const lines = [COLUMNS.join(',')];
  for (const it of byId) {
    const lb = labels[it.id] || {};
    lines.push(COLUMNS.map(c => c === 'id' ? it.id : c === 'stratum' ? it.stratum : csvCell(lb[c] || '')).join(','));
  }
  return lines.join('\n') + '\n';
}
function exportCsv() {
  store();
  const blob = new Blob([buildCsv()], { type: 'text/csv' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = QUICK ? 'labels_quick.csv' : 'labels.csv'; document.body.appendChild(a); a.click(); a.remove();
}
function copyCsv() {
  store(); const ta = document.getElementById('ta'); ta.style.display = 'block'; ta.value = buildCsv(); ta.select();
  try { navigator.clipboard.writeText(ta.value); } catch (e) {}
}
function parseCsv(text) {
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; }
    else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += ch;
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  return rows;
}
document.getElementById('imp').addEventListener('change', ev => {
  const f = ev.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    const rows = parseCsv(rd.result); const head = rows[0]; let n = 0;
    for (const r of rows.slice(1)) {
      if (!r.length || !r[0]) continue; const id = r[0]; const lb = {};
      head.forEach((c, j) => { if (c !== 'id' && c !== 'stratum' && (r[j] || '').trim()) lb[c] = r[j].trim(); });
      if (Object.keys(lb).length) { labels[id] = Object.assign(labels[id] || {}, lb); n++; }
    }
    try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {}
    alert('Đã nhập ' + n + ' dòng có nhãn.'); render();
  };
  rd.readAsText(f);
});
render();
</script></body></html>
"""
html = (html.replace("__GUIDE__", GUIDE_QUICK if QUICK else GUIDE)
        .replace("__ITEMS__", json.dumps(items, ensure_ascii=False))
        .replace("__FIELDS__", json.dumps(FIELDS, ensure_ascii=False))
        .replace("__COLUMNS__", json.dumps(columns))
        .replace("__QUICK__", "true" if QUICK else "false")
        .replace("__MODE__", " — chế độ kiểm tra (máy điền sẵn, anh sửa)" if QUICK else ""))
out = os.path.join(KIT, "label_quick.html" if QUICK else "label.html")
with open(out, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(html)
print("wrote", out, len(items), "items")
