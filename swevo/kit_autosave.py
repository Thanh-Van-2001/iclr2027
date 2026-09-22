"""Add autosave and resume to the two labelling sheets: every keystroke is kept
in the browser's local storage and restored when the page is reopened, a
"Load labels.csv" control refills the form from a saved file, and a counter
shows how many items have an answer. The questions and the CSV format are
unchanged.

Usage: python swevo/kit_autosave.py
"""
import os

KITS = {"audits/swevo_human": "swevo_kit_separate", "audits/swevo_human_rows": "swevo_kit_rows"}

SCRIPT = """<script>
(function(){
  const KEY='%(key)s';
  const f=document.getElementById('f');
  function fields(){return Array.from(f.querySelectorAll('input[type=text]'));}
  function store(){const d={};for(const el of fields()){if(el.value)d[el.name]=el.value;}try{localStorage.setItem(KEY,JSON.stringify(d));}catch(e){}updateCount();}
  function restore(){try{const d=JSON.parse(localStorage.getItem(KEY)||'{}');for(const el of fields()){if(d[el.name]!==undefined&&!el.value)el.value=d[el.name];}}catch(e){}updateCount();}
  function updateCount(){const ids=new Set();for(const el of fields()){if(el.value)ids.add(el.name.slice(3));}const c=document.getElementById('count');if(c)c.textContent='Items with an answer: '+ids.size+' / '+document.querySelectorAll('div.q').length;}
  function loadCsv(file){const r=new FileReader();r.onload=function(){const lines=r.result.split(/\\r?\\n/).filter(x=>x.trim());const head=lines[0].split(',');const map={results_table:'rt',bold_ok:'bo',whole_row_bold:'wr',std_printed:'sp',winner_mean:'wm',winner_disp:'wd',runner_mean:'rm',runner_disp:'rd',n_runs:'nr',note:'nt'};for(const line of lines.slice(1)){const cells=line.split(',');const id=cells[0];head.forEach((h,i)=>{const k=map[h.trim()];if(k&&cells[i]!==undefined){const el=f.elements[k+'_'+id];if(el)el.value=cells[i];}});}store();};r.readAsText(file);}
  f.addEventListener('input',store);
  const bar=document.createElement('div');
  bar.style.cssText='position:fixed;right:12px;top:12px;background:#fff3c4;border:1px solid #c9a400;padding:8px 12px;font-size:13px;z-index:10';
  bar.innerHTML="<b id='count'></b><br>Answers are saved in this browser as you type. Resume by reopening this file.<br>Load a saved labels.csv: <input type='file' id='loadcsv' accept='.csv'>";
  document.body.appendChild(bar);
  document.getElementById('loadcsv').addEventListener('change',e=>{if(e.target.files[0])loadCsv(e.target.files[0]);});
  restore();
})();
</script>"""


def main() -> int:
    for kit, key in KITS.items():
        path = os.path.join(kit, "label.html")
        if not os.path.exists(path):
            continue
        s = open(path, encoding="utf-8").read()
        if "swevo_kit_" in s:
            print(kit, "already has autosave")
            continue
        s = s + "\n" + SCRIPT % {"key": key}
        open(path, "w", encoding="utf-8").write(s)
        print(kit, "autosave added")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
