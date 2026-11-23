"""Offline, single-file labelling pages for the AAMAS human-validation kits.

Two page types, both plain HTML + JavaScript with no network access:

  form_kit_html   one item at a time (an image and/or a PDF link on the left,
                  a fixed list of questions on the right). Used by the blind
                  comparison kit, the run-count and bar-type checks and the
                  empty-page check.
  page_kit_html   one whole page at a time; the annotator lists every results
                  table and every eligible group on it (or states there is
                  none) and clicks the bold cell of each group on the image.

Both pages: ask for an annotator ID before anything can be entered, autosave
every keystroke to the browser's localStorage under a key that includes the
kit, its version and the annotator ID (two annotators on one machine never
share a store), resume from a previously exported CSV, and export a CSV whose
columns the scorer (aamas/human_validation_score.py) reads. Nothing in the
page carries a machine reading: the builder passes only what a human needs to
find the table in the paper.
"""
from __future__ import annotations

import html as _html
import json

CSS = r"""
:root{--bg:#f4f4f2;--panel:#fff;--ink:#141414;--muted:#5b5b5b;--line:#d8d8d4;--accent:#0b5cad;--warn:#b3261e;--ok:#1b7a2f;--hl:#fff4c2}
*{box-sizing:border-box}
body{font-family:system-ui,"Segoe UI",Arial,sans-serif;margin:0;background:var(--bg);color:var(--ink);font-size:14px}
header{position:sticky;top:0;z-index:5;padding:8px 12px;background:var(--panel);border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:center;flex-wrap:wrap}
header b{font-size:15px}
header label{font-size:13px}
button{padding:5px 10px;font-size:13px;cursor:pointer;border:1px solid #999;background:#fafafa;border-radius:3px}
button.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
#guide{font-size:13px;padding:8px 14px;background:var(--hl);border-bottom:1px solid var(--line);line-height:1.5;max-height:40vh;overflow:auto}
#guide h3{margin:6px 0 4px;font-size:14px}
#wrap{display:flex;gap:10px;padding:10px;align-items:flex-start}
#left{flex:1 1 58%;min-width:0;background:var(--panel);border:1px solid var(--line);padding:6px;max-height:calc(100vh - 120px);overflow:auto}
#right{flex:0 0 480px;max-width:100%;background:var(--panel);border:1px solid var(--line);padding:10px;max-height:calc(100vh - 120px);overflow:auto}
@media (max-width:900px){#wrap{flex-direction:column}#right{flex-basis:auto;width:100%}}
#imgbox{position:relative;display:inline-block;width:100%}
#imgbox img{width:100%;display:block}
#imgbox.zoom{width:200%}
.banner{background:#fdecea;color:var(--warn);border:1px solid #f3b8b3;padding:8px;margin-bottom:6px;font-weight:600}
.banner a{color:var(--warn)}
#context{white-space:pre-wrap;font-size:12px;background:#f7f7f5;border:1px solid var(--line);padding:6px;max-height:220px;overflow:auto}
.meta{font-size:12.5px;color:var(--muted);margin-bottom:6px;line-height:1.45}
.links a{display:inline-block;margin:0 8px 6px 0;font-weight:600;color:var(--accent)}
.q{margin:7px 0}
.q label{display:block;font-size:12.5px;margin-bottom:2px}
.q .help{font-size:11.5px;color:var(--muted);margin-top:2px}
.q input,.q select,.q textarea{width:100%;padding:5px 6px;font-size:14px;border:1px solid #b8b8b4;border-radius:3px;background:#fff;color:var(--ink)}
.q textarea{height:62px;font-size:13px}
.q.missing input,.q.missing select,.q.missing textarea{border-color:var(--warn);background:#fff6f5}
.q.skipped{opacity:.45}
#nav{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
#status{font-size:12px;color:var(--muted);margin-top:6px}
.done{color:var(--ok);font-weight:600}
.locked{padding:14px;background:#fdecea;border:1px solid #f3b8b3;color:var(--warn);font-weight:600}
table.list{border-collapse:collapse;width:100%;font-size:12.5px;margin:4px 0}
table.list td,table.list th{border:1px solid var(--line);padding:3px 4px;vertical-align:top}
table.list input,table.list select{width:100%;font-size:12.5px;padding:2px 3px}
.marker{position:absolute;transform:translate(-50%,-50%);min-width:20px;height:20px;border-radius:10px;background:rgba(179,38,30,.85);color:#fff;font-size:11px;font-weight:700;text-align:center;line-height:20px;padding:0 4px;pointer-events:none}
.marker.sel{background:rgba(11,92,173,.95)}
.armed{outline:3px solid var(--accent)}
"""

COMMON_JS = r"""
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
const LS=(function(){try{const k='__hv_t';localStorage.setItem(k,'1');localStorage.removeItem(k);return localStorage;}catch(e){return null;}})();
function lsGet(k){try{return LS?LS.getItem(k):null;}catch(e){return null;}}
function lsSet(k,v){try{if(LS)LS.setItem(k,v);}catch(e){}}
function nowIso(){return new Date().toISOString();}
function csvCell(s){s=String(s==null?'':s);return /[",\n\r]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s;}
function parseCsv(text){
  if(text.charCodeAt(0)===0xFEFF)text=text.slice(1);
  const rows=[];let row=[],cell='',q=false;
  for(let i=0;i<text.length;i++){const ch=text[i];
    if(q){if(ch==='"'){if(text[i+1]==='"'){cell+='"';i++;}else q=false;}else cell+=ch;}
    else if(ch==='"')q=true;
    else if(ch===','){row.push(cell);cell='';}
    else if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(cell);rows.push(row);row=[];cell='';}
    else cell+=ch;}
  if(cell!==''||row.length){row.push(cell);rows.push(row);}
  return rows.filter(r=>r.length>1||(r[0]||'').trim()!=='');
}
function download(name,text){
  const blob=new Blob(["﻿"+text],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();
}
"""

FORM_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>__CSS__</style></head><body>
<header><b>__TITLE__</b>
<label>Annotator ID <input id="ann" size="9" placeholder="e.g. H1"></label>
<label>Items <select id="set"></select></label>
<span id="prog"></span>
<button class="primary" id="exp">Export CSV</button>
<label>Resume from CSV <input type="file" id="imp" accept=".csv"></label>
<button id="guideBtn">Show/hide instructions</button>
</header>
<div id="guide">__INTRO__</div>
<div id="wrap">
<div id="left"><div id="banner"></div><div id="imgbox"><img id="img" alt=""></div><div id="ctxhead" class="meta"></div><pre id="context" hidden></pre></div>
<div id="right"><div class="meta" id="meta"></div><div class="links" id="links"></div><div id="form"></div>
<div id="nav"><button id="prev">&larr; Previous</button><button class="primary" id="next">Save &amp; next &rarr;</button><button id="skip">Next without completing &rarr;</button></div>
<div id="status"></div></div></div>
<script>
const CFG=__CFG__;
__COMMON__
const ITEMS=CFG.items, FIELDS=CFG.fields, GATES=CFG.gates||[];
let annotator=(lsGet('aamasHV:annotator')||'').trim();
let labels={}, view=[], cur=0, setName=lsGet('aamasHV:'+CFG.kit+':set')||CFG.defaultSet, t0=Date.now();
function storeKey(){return 'aamasHV:'+CFG.kit+':'+CFG.version+':'+annotator;}
function loadLabels(){labels={};if(!annotator)return;try{labels=JSON.parse(lsGet(storeKey())||'{}');}catch(e){labels={};}}
function persist(){if(annotator)lsSet(storeKey(),JSON.stringify(labels));}
function inSet(it){return setName==='all'||(it.sets||[]).indexOf(setName)>=0;}
function rebuildView(){view=ITEMS.filter(inSet);if(!view.length){setName='all';view=ITEMS.slice();}if(cur>=view.length)cur=0;}
function skippedFrom(lb){
  // index of the first field after a gate that switched the rest off
  for(const g of GATES){const i=FIELDS.findIndex(f=>f.name===g.field);if(i>=0&&g.skip.indexOf(lb[g.field]||'')>=0)return i+1;}
  return FIELDS.length;
}
function isRequired(f,i,lb){
  if(f.req==='never')return false;
  if(i>=skippedFrom(lb)&&!f.always)return false;
  if(f.req&&f.req.if){const g=f.req.if[0],vals=f.req.if[1];return vals.indexOf(lb[g]||'')>=0;}
  return true;
}
function missingFields(lb){return FIELDS.filter((f,i)=>isRequired(f,i,lb)&&!String(lb[f.name]||'').trim()).map(f=>f.name);}
function hasAny(lb){return !!lb&&FIELDS.some(f=>String(lb[f.name]||'').trim()!=='');}
function isDone(id){const lb=labels[id];return hasAny(lb)&&missingFields(lb).length===0;}
function updateProg(){
  const n=view.filter(x=>isDone(x.id)).length, all=ITEMS.filter(x=>isDone(x.id)).length;
  document.getElementById('prog').innerHTML='<span class="'+(n===view.length?'done':'')+'">'+n+'/'+view.length+' complete in this set</span> ('+all+'/'+ITEMS.length+' overall)';
}
function leaveItem(){
  if(!annotator||!view.length)return;const it=view[cur];const lb=labels[it.id];
  if(lb&&hasAny(lb)){lb._seconds=Math.round((lb._seconds||0)+(Date.now()-t0)/1000);persist();}
}
function render(){
  rebuildView();t0=Date.now();
  const sel=document.getElementById('set');
  sel.innerHTML=Object.keys(CFG.sets).map(k=>'<option value="'+k+'"'+(k===setName?' selected':'')+'>'+esc(CFG.sets[k])+'</option>').join('');
  document.getElementById('ann').value=annotator;
  const form=document.getElementById('form');
  if(!annotator){form.innerHTML='<div class="locked">Enter your annotator ID at the top before labelling. Each annotator\'s answers are stored separately.</div>';updateProg();return;}
  const it=view[cur];const lb=labels[it.id]||{};
  const img=document.getElementById('img'), banner=document.getElementById('banner');
  banner.innerHTML='';
  if(it.image){img.hidden=false;img.src=it.image;img.onerror=function(){img.hidden=true;banner.innerHTML='<div class="banner">Image file missing: '+esc(it.image)+'. Run <code>python aamas/human_validation_kits.py check</code>. Use the PDF link instead.</div>';};}
  else{img.hidden=true;img.removeAttribute('src');banner.innerHTML='<div class="banner">'+esc(it.image_note||'No page image is shipped for this item.')+' Open the full paper with the link on the right.</div>';}
  document.getElementById('imgbox').classList.remove('zoom');
  const ctx=document.getElementById('context');
  if(it.context){ctx.hidden=false;ctx.textContent=it.context;document.getElementById('ctxhead').textContent=it.context_title||'';}
  else{ctx.hidden=true;document.getElementById('ctxhead').textContent='';}
  document.getElementById('meta').innerHTML='<b>'+esc(it.id)+'</b> ('+(cur+1)+' of '+view.length+')'+(isDone(it.id)?' <span class="done">complete</span>':'')+'<br>'+(it.meta||[]).map(esc).join('<br>');
  document.getElementById('links').innerHTML=(it.links||[]).map(l=>'<a href="'+esc(l.href)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a>').join('');
  let h='';const skipAt=skippedFrom(lb);
  FIELDS.forEach((f,i)=>{
    const v=lb[f.name]||'';const skip=i>=skipAt&&!f.always;
    h+='<div class="q'+(skip?' skipped':'')+'" data-q="'+f.name+'"><label for="f_'+f.name+'">'+esc(f.label)+(isRequired(f,i,lb)?' *':'')+'</label>';
    if(f.kind==='select'){h+='<select id="f_'+f.name+'" data-f="'+f.name+'"><option value="">--</option>'+f.options.map(o=>'<option value="'+esc(o[0])+'"'+(v===o[0]?' selected':'')+'>'+esc(o[1])+'</option>').join('')+'</select>';}
    else if(f.kind==='area'){h+='<textarea id="f_'+f.name+'" data-f="'+f.name+'">'+esc(v)+'</textarea>';}
    else{h+='<input id="f_'+f.name+'" data-f="'+f.name+'" value="'+esc(v)+'" autocomplete="off">';}
    if(f.help)h+='<div class="help">'+esc(f.help)+'</div>';
    h+='</div>';});
  form.innerHTML=h;
  const els=Array.from(document.querySelectorAll('#form [data-f]'));
  els.forEach((el,i)=>{
    el.addEventListener('input',()=>store(false));
    el.addEventListener('change',()=>{store(false);if(el.tagName==='SELECT'&&GATES.some(g=>g.field===el.dataset.f)){const k=el.dataset.f;render();const n=document.getElementById('f_'+k);if(n)n.focus();}});
    el.addEventListener('keydown',ev=>{
      if(ev.key==='Enter'&&(ev.ctrlKey||ev.metaKey)){ev.preventDefault();saveAndNext();return;}
      if(ev.key==='Enter'&&el.tagName!=='TEXTAREA'){ev.preventDefault();store(false);
        const nx=els.slice(i+1).find(e=>!e.closest('.q').classList.contains('skipped'));if(nx)nx.focus();else saveAndNext();}
    });});
  const first=els.find(e=>!String(lb[e.dataset.f]||'').trim());(first||els[0]).focus();
  updateProg();
  document.getElementById('status').textContent=LS?'Autosaved in this browser for annotator '+annotator+'. Export the CSV when you stop.':'This browser blocks local storage: export the CSV before closing the page.';
}
function store(){
  if(!annotator)return;const it=view[cur];const lb=labels[it.id]||{};
  document.querySelectorAll('#form [data-f]').forEach(el=>{lb[el.dataset.f]=el.value.trim();});
  if(!lb._first_opened)lb._first_opened=nowIso();lb._last_saved=nowIso();
  labels[it.id]=lb;persist();updateProg();
}
function saveAndNext(){
  store();const it=view[cur];const lb=labels[it.id]||{};const miss=missingFields(lb);
  document.querySelectorAll('#form .q').forEach(q=>q.classList.toggle('missing',miss.indexOf(q.dataset.q)>=0));
  if(miss.length){const q=document.querySelector('#form .q.missing [data-f]');if(q)q.focus();
    document.getElementById('status').textContent='Missing: '+miss.join(', ')+' (write "unclear" or pick "unclear" where you cannot tell).';return;}
  go(cur+1);
}
function go(i){leaveItem();if(i<0)i=0;if(i>=view.length){updateProg();alert('End of this set. Export the CSV.');i=view.length-1;}cur=i;render();window.scrollTo(0,0);}
function buildCsv(){
  const cols=['id','annotator_id','kit','kit_version'].concat(FIELDS.map(f=>f.name)).concat(['complete','first_opened_at','last_saved_at','seconds_on_item']);
  const lines=[cols.join(',')];
  ITEMS.slice().sort((a,b)=>a.id<b.id?-1:1).forEach(it=>{const lb=labels[it.id]||{};
    const row={id:it.id,annotator_id:annotator,kit:CFG.kit,kit_version:CFG.version,complete:isDone(it.id)?'y':'n',
      first_opened_at:lb._first_opened||'',last_saved_at:lb._last_saved||'',seconds_on_item:(lb._seconds!=null?lb._seconds:'')};
    FIELDS.forEach(f=>{row[f.name]=lb[f.name]||'';});
    lines.push(cols.map(c=>csvCell(row[c])).join(','));});
  return lines.join('\n')+'\n';
}
document.getElementById('exp').onclick=()=>{if(!annotator){alert('Enter an annotator ID first.');return;}store();download(CFG.exportName.replace('{annotator}',annotator),buildCsv());};
document.getElementById('prev').onclick=()=>go(cur-1);
document.getElementById('next').onclick=saveAndNext;
document.getElementById('skip').onclick=()=>{store();go(cur+1);};
document.getElementById('guideBtn').onclick=()=>{const g=document.getElementById('guide');g.hidden=!g.hidden;};
document.getElementById('img').onclick=()=>document.getElementById('imgbox').classList.toggle('zoom');
document.getElementById('set').onchange=ev=>{leaveItem();setName=ev.target.value;lsSet('aamasHV:'+CFG.kit+':set',setName);cur=0;render();};
document.getElementById('ann').onchange=ev=>{
  const v=ev.target.value.trim().replace(/[^A-Za-z0-9_-]/g,'');
  if(annotator)leaveItem();annotator=v;lsSet('aamasHV:annotator',annotator);loadLabels();
  cur=0;rebuildView();const k=view.findIndex(x=>!isDone(x.id));cur=k<0?0:k;render();};
document.getElementById('imp').addEventListener('change',ev=>{
  const f=ev.target.files[0];if(!f)return;const rd=new FileReader();
  rd.onload=()=>{const rows=parseCsv(rd.result);if(!rows.length)return;const head=rows[0].map(s=>s.trim());
    const ai=head.indexOf('annotator_id');const ids=new Set(ITEMS.map(x=>x.id));
    const owners=new Set(rows.slice(1).map(r=>ai>=0?(r[ai]||'').trim():'').filter(Boolean));
    if(owners.size>1){alert('This CSV holds several annotator IDs: '+Array.from(owners).join(', ')+'. Import one annotator\'s file at a time.');return;}
    const owner=owners.size?Array.from(owners)[0]:'';
    if(!annotator&&owner){annotator=owner;lsSet('aamasHV:annotator',annotator);loadLabels();}
    if(owner&&owner!==annotator&&!confirm('The CSV belongs to annotator '+owner+' but the page is set to '+annotator+'. Import into '+annotator+' anyway?'))return;
    if(!annotator){alert('Enter an annotator ID first.');return;}
    let n=0;
    rows.slice(1).forEach(r=>{const id=(r[0]||'').trim();if(!ids.has(id))return;const lb=labels[id]||{};let any=false;
      FIELDS.forEach(fl=>{const j=head.indexOf(fl.name);if(j>=0&&(r[j]||'').trim()){lb[fl.name]=r[j].trim();any=true;}});
      const j1=head.indexOf('first_opened_at'),j2=head.indexOf('last_saved_at'),j3=head.indexOf('seconds_on_item');
      if(j1>=0&&r[j1])lb._first_opened=r[j1];if(j2>=0&&r[j2])lb._last_saved=r[j2];if(j3>=0&&r[j3])lb._seconds=Number(r[j3])||0;
      if(any){labels[id]=lb;n++;}});
    persist();alert('Imported '+n+' labelled items for annotator '+annotator+'.');render();};
  rd.readAsText(f,'utf-8');ev.target.value='';});
document.addEventListener('keydown',ev=>{if(ev.altKey&&ev.key==='ArrowLeft'){ev.preventDefault();go(cur-1);}if(ev.altKey&&ev.key==='ArrowRight'){ev.preventDefault();store();go(cur+1);}});
window.addEventListener('beforeunload',()=>{leaveItem();});
loadLabels();rebuildView();{const k=view.findIndex(x=>!isDone(x.id));cur=k<0?0:k;}render();
</script></body></html>
"""

PAGE_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title><style>__CSS__</style></head><body>
<header><b>__TITLE__</b>
<label>Annotator ID <input id="ann" size="9" placeholder="e.g. H1"></label>
<label>Pages <select id="set"></select></label>
<span id="prog"></span>
<button class="primary" id="exp">Export CSV</button>
<label>Resume from CSV <input type="file" id="imp" accept=".csv"></label>
<button id="guideBtn">Show/hide instructions</button>
<button id="zoomBtn">Zoom page</button>
</header>
<div id="guide">__INTRO__</div>
<div id="wrap">
<div id="left"><div id="banner"></div><div id="imgbox"><img id="img" alt=""></div></div>
<div id="right"><div class="meta" id="meta"></div><div class="links" id="links"></div><div id="form"></div>
<div id="nav"><button id="prev">&larr; Previous page</button><button class="primary" id="next">Save &amp; next page &rarr;</button></div>
<div id="status"></div></div></div>
<script>
const CFG=__CFG__;
__COMMON__
const PAGES=CFG.items;
let annotator=(lsGet('aamasHV:annotator')||'').trim();
let st={}, view=[], cur=0, setName=lsGet('aamasHV:'+CFG.kit+':set')||CFG.defaultSet, armed=null, t0=Date.now();
const OPT={status:[['groups_listed','I listed every eligible group on this page'],['none_found','This page has NO eligible group (checked every table)'],['unclear','Cannot tell']],
 results:[['y','results table'],['n','not a results table'],['unclear','unclear']],
 orient:[['column','column (methods are rows)'],['row','row (methods are columns)'],['unclear','unclear']],
 rule:[['single_best','bold = the single best'],['top_k','bold = top-k / several marks'],['other','bold means something else'],['no_bold','no bold numbers'],['unclear','unclear']],
 best:[['y','yes: bold is strictly best'],['tie','tied with a non-bold cell'],['n','no: a non-bold cell is better'],['unclear','unclear']]};
function storeKey(){return 'aamasHV:'+CFG.kit+':'+CFG.version+':'+annotator;}
function loadSt(){st={};if(!annotator)return;try{st=JSON.parse(lsGet(storeKey())||'{}');}catch(e){st={};}}
function persist(){if(annotator)lsSet(storeKey(),JSON.stringify(st));}
function inSet(p){return setName==='all'||(p.sets||[]).indexOf(setName)>=0;}
function rebuildView(){view=PAGES.filter(inSet);if(!view.length){setName='all';view=PAGES.slice();}if(cur>=view.length)cur=0;}
function pg(id){if(!st[id])st[id]={status:'',note:'',tables:[],groups:[],next:1};return st[id];}
function problems(p){
  const out=[];if(!p.status)out.push('page status');
  p.tables.forEach((t,i)=>{if(!t.ref)out.push('table '+(i+1)+' identifier');if(!t.results)out.push('table '+(i+1)+' results?');
    if(t.results==='y'){if(!t.orient)out.push('table '+(i+1)+' orientation');if(!t.rule)out.push('table '+(i+1)+' bold rule');}});
  p.groups.forEach((g,i)=>{if(!g.table)out.push('group '+(i+1)+' table');if(!g.label)out.push('group '+(i+1)+' label');
    if(!g.winner)out.push('group '+(i+1)+' bold value');if(!g.best)out.push('group '+(i+1)+' bold is best?');});
  const elig=p.groups.filter(g=>g.best==='y').length;
  if(p.status==='groups_listed'&&elig===0)out.push('status says groups are listed but no group has "bold is strictly best"');
  if(p.status==='none_found'&&elig>0)out.push('status says no eligible group but '+elig+' group(s) are marked strictly best');
  if(p.status==='none_found'&&p.tables.length===0&&!p.note)out.push('write in the note what is on the page (e.g. "no table", "only a figure")');
  return out;
}
function isDone(id){const p=st[id];return !!p&&!!p.status&&problems(p).length===0;}
function updateProg(){const n=view.filter(x=>isDone(x.id)).length;document.getElementById('prog').innerHTML='<span class="'+(n===view.length?'done':'')+'">'+n+'/'+view.length+' pages complete</span>';}
function sel(name,opts,v,attrs){return '<select '+attrs+'><option value="">--</option>'+opts.map(o=>'<option value="'+o[0]+'"'+(v===o[0]?' selected':'')+'>'+esc(o[1])+'</option>').join('')+'</select>';}
function leavePage(){if(!annotator||!view.length)return;const p=st[view[cur].id];if(p){p._seconds=Math.round((p._seconds||0)+(Date.now()-t0)/1000);persist();}}
function drawMarkers(){
  const box=document.getElementById('imgbox');box.querySelectorAll('.marker').forEach(m=>m.remove());
  const it=view[cur];const p=st[it.id];if(!p||!it.width)return;
  p.groups.forEach((g,i)=>{if(g.x===''||g.x==null)return;const m=document.createElement('div');m.className='marker'+(armed===g.key?' sel':'');
    m.style.left=(100*g.x/it.width)+'%';m.style.top=(100*g.y/it.height)+'%';m.textContent=String(i+1);box.appendChild(m);});
}
function render(){
  rebuildView();t0=Date.now();
  document.getElementById('set').innerHTML=Object.keys(CFG.sets).map(k=>'<option value="'+k+'"'+(k===setName?' selected':'')+'>'+esc(CFG.sets[k])+'</option>').join('');
  document.getElementById('ann').value=annotator;
  const form=document.getElementById('form');
  if(!annotator){form.innerHTML='<div class="locked">Enter your annotator ID at the top before labelling.</div>';updateProg();return;}
  const it=view[cur];const p=pg(it.id);
  const img=document.getElementById('img'),banner=document.getElementById('banner');banner.innerHTML='';
  if(it.image){img.hidden=false;img.src=it.image;img.onerror=function(){img.hidden=true;banner.innerHTML='<div class="banner">Image file missing: '+esc(it.image)+'. Run <code>python aamas/human_validation_kits.py check</code>, or use the PDF link.</div>';};}
  else{img.hidden=true;banner.innerHTML='<div class="banner">No page image is shipped. Open the PDF page with the link on the right and click positions are unavailable; describe the location in the group label.</div>';}
  document.getElementById('meta').innerHTML='<b>'+esc(it.id)+'</b> ('+(cur+1)+' of '+view.length+')'+(isDone(it.id)?' <span class="done">complete</span>':'')+'<br>'+(it.meta||[]).map(esc).join('<br>');
  document.getElementById('links').innerHTML=(it.links||[]).map(l=>'<a href="'+esc(l.href)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a>').join('');
  let h='<div class="q"><label>Page status *</label>'+sel('status',OPT.status,p.status,'data-p="status"')+'</div>';
  h+='<div class="q"><label>Tables on this page (list every table, results or not)</label><table class="list"><tr><th>#</th><th>Identifier (e.g. Table 2)</th><th>Caption start</th><th>Results?</th><th>Orientation</th><th>Bold rule</th><th></th></tr>';
  p.tables.forEach((t,i)=>{h+='<tr><td>'+(i+1)+'</td><td><input data-t="'+i+'" data-k="ref" value="'+esc(t.ref)+'"></td><td><input data-t="'+i+'" data-k="caption" value="'+esc(t.caption)+'"></td><td>'+sel('',OPT.results,t.results,'data-t="'+i+'" data-k="results"')+'</td><td>'+sel('',OPT.orient,t.orient,'data-t="'+i+'" data-k="orient"')+'</td><td>'+sel('',OPT.rule,t.rule,'data-t="'+i+'" data-k="rule"')+'</td><td><button data-deltable="'+i+'">x</button></td></tr>';});
  h+='</table><button id="addTable">+ Add table</button></div>';
  const tabOpts=p.tables.map((t,i)=>[t.key,(t.ref||('table '+(i+1)))]);
  h+='<div class="q"><label>Groups with exactly one bold cell (one row per group). Select a group, then click its bold cell on the page.</label><table class="list"><tr><th>#</th><th>Table</th><th>Group label (row/column header)</th><th>Bold value as printed</th><th>Bold is best?</th><th>Location</th><th>Note</th><th></th></tr>';
  p.groups.forEach((g,i)=>{h+='<tr'+(armed===g.key?' class="armed"':'')+'><td>'+(i+1)+'</td><td>'+sel('',tabOpts,g.table,'data-g="'+i+'" data-k="table"')+'</td><td><input data-g="'+i+'" data-k="label" value="'+esc(g.label)+'"></td><td><input data-g="'+i+'" data-k="winner" value="'+esc(g.winner)+'"></td><td>'+sel('',OPT.best,g.best,'data-g="'+i+'" data-k="best"')+'</td><td><button data-arm="'+i+'">'+(g.x!==''&&g.x!=null?'set ✓':'click to set')+'</button></td><td><input data-g="'+i+'" data-k="note" value="'+esc(g.note)+'"></td><td><button data-delgroup="'+i+'">x</button></td></tr>';});
  h+='</table><button id="addGroup"'+(p.tables.length?'':' disabled')+'>+ Add group</button>'+(p.tables.length?'':' <span class="help">add a table first</span>')+'</div>';
  h+='<div class="q"><label>Page note (what is on the page; anything unusual)</label><textarea data-p="note">'+esc(p.note)+'</textarea></div>';
  form.innerHTML=h;
  form.querySelectorAll('[data-p]').forEach(el=>{el.oninput=el.onchange=()=>{p[el.dataset.p]=el.value.trim();touch(p);};});
  form.querySelectorAll('[data-t]').forEach(el=>{el.oninput=()=>{p.tables[+el.dataset.t][el.dataset.k]=el.value.trim();touch(p);};
    // a renamed table is renamed in every group's table menu once the field is left
    el.onchange=()=>{p.tables[+el.dataset.t][el.dataset.k]=el.value.trim();touch(p);if(el.dataset.k==='ref')render();};});
  form.querySelectorAll('[data-g]').forEach(el=>{el.oninput=el.onchange=()=>{p.groups[+el.dataset.g][el.dataset.k]=el.value.trim();touch(p);};});
  form.querySelectorAll('[data-deltable]').forEach(b=>b.onclick=()=>{const t=p.tables[+b.dataset.deltable];
    if(p.groups.some(g=>g.table===t.key)&&!confirm('Delete this table and its groups?'))return;p.groups=p.groups.filter(g=>g.table!==t.key);p.tables.splice(+b.dataset.deltable,1);touch(p);render();});
  form.querySelectorAll('[data-delgroup]').forEach(b=>b.onclick=()=>{p.groups.splice(+b.dataset.delgroup,1);touch(p);render();});
  form.querySelectorAll('[data-arm]').forEach(b=>b.onclick=()=>{const g=p.groups[+b.dataset.arm];armed=(armed===g.key)?null:g.key;render();});
  document.getElementById('addTable').onclick=()=>{p.tables.push({key:'t'+(p.next++),ref:'',caption:'',results:'',orient:'',rule:''});touch(p);render();};
  const ag=document.getElementById('addGroup');if(ag)ag.onclick=()=>{const last=p.groups.length?p.groups[p.groups.length-1].table:(p.tables[0]||{}).key;
    const g={key:'g'+(p.next++),table:last||'',label:'',winner:'',best:'',x:'',y:'',note:''};p.groups.push(g);armed=g.key;touch(p);render();};
  drawMarkers();updateProg();
  const pr=problems(p);document.getElementById('status').textContent=pr.length?('To finish this page: '+pr.join('; ')):'Page complete. Autosaved for annotator '+annotator+'.';
}
function touch(p){if(!p._first_opened)p._first_opened=nowIso();p._last_saved=nowIso();persist();updateProg();
  const pr=problems(p);document.getElementById('status').textContent=pr.length?('To finish this page: '+pr.join('; ')):'Page complete. Autosaved for annotator '+annotator+'.';}
document.getElementById('img').addEventListener('click',ev=>{
  if(!annotator)return;const it=view[cur];const p=pg(it.id);
  if(!armed){document.getElementById('status').textContent='Select a group ("click to set") before clicking the page.';return;}
  const g=p.groups.find(x=>x.key===armed);if(!g)return;const r=ev.target.getBoundingClientRect();
  // a click before the image has laid out has no size to scale by: refuse it rather than store NaN
  if(!(r.width>0&&r.height>0&&ev.target.naturalWidth>0)){document.getElementById('status').textContent='The page image has not loaded yet; click again once it shows.';return;}
  const x=Math.round((ev.clientX-r.left)*it.width/r.width),y=Math.round((ev.clientY-r.top)*it.height/r.height);
  if(!isFinite(x)||!isFinite(y))return;
  g.x=x;g.y=y;armed=null;touch(p);render();});
function go(i){leavePage();if(i<0)i=0;if(i>=view.length){alert('End of this set. Export the CSV.');i=view.length-1;}cur=i;armed=null;render();window.scrollTo(0,0);}
const COLS=['row_type','page_id','annotator_id','kit','kit_version','page_status','page_note','table_key','table_ref','table_caption','results_table','orientation','bold_rule','group_key','group_table_key','group_label','winner_value','bold_is_best','x_px','y_px','group_note','complete','first_opened_at','last_saved_at','seconds_on_page'];
function buildCsv(){
  const lines=[COLS.join(',')];
  PAGES.slice().sort((a,b)=>a.id<b.id?-1:1).forEach(it=>{const p=st[it.id];if(!p||(!p.status&&!p.tables.length&&!p.groups.length&&!p.note))return;
    const base={page_id:it.id,annotator_id:annotator,kit:CFG.kit,kit_version:CFG.version};
    const put=o=>lines.push(COLS.map(c=>csvCell(o[c])).join(','));
    put(Object.assign({},base,{row_type:'page',page_status:p.status,page_note:p.note,complete:isDone(it.id)?'y':'n',first_opened_at:p._first_opened||'',last_saved_at:p._last_saved||'',seconds_on_page:p._seconds||''}));
    p.tables.forEach(t=>put(Object.assign({},base,{row_type:'table',table_key:t.key,table_ref:t.ref,table_caption:t.caption,results_table:t.results,orientation:t.orient,bold_rule:t.rule})));
    p.groups.forEach(g=>put(Object.assign({},base,{row_type:'group',group_key:g.key,group_table_key:g.table,group_label:g.label,winner_value:g.winner,bold_is_best:g.best,x_px:g.x,y_px:g.y,group_note:g.note})));});
  return lines.join('\n')+'\n';
}
document.getElementById('exp').onclick=()=>{if(!annotator){alert('Enter an annotator ID first.');return;}download(CFG.exportName.replace('{annotator}',annotator),buildCsv());};
document.getElementById('prev').onclick=()=>go(cur-1);
document.getElementById('next').onclick=()=>{const it=view[cur];const pr=problems(pg(it.id));if(pr.length&&!confirm('This page is not complete ('+pr.join('; ')+'). Move on anyway?'))return;go(cur+1);};
document.getElementById('guideBtn').onclick=()=>{const g=document.getElementById('guide');g.hidden=!g.hidden;};
document.getElementById('zoomBtn').onclick=()=>{document.getElementById('imgbox').classList.toggle('zoom');};
document.getElementById('set').onchange=ev=>{leavePage();setName=ev.target.value;lsSet('aamasHV:'+CFG.kit+':set',setName);cur=0;render();};
document.getElementById('ann').onchange=ev=>{const v=ev.target.value.trim().replace(/[^A-Za-z0-9_-]/g,'');if(annotator)leavePage();annotator=v;lsSet('aamasHV:annotator',annotator);loadSt();cur=0;render();};
document.getElementById('imp').addEventListener('change',ev=>{
  const f=ev.target.files[0];if(!f)return;const rd=new FileReader();
  rd.onload=()=>{const rows=parseCsv(rd.result);if(!rows.length)return;const head=rows[0].map(s=>s.trim());const ix=c=>head.indexOf(c);
    const owners=new Set(rows.slice(1).map(r=>(r[ix('annotator_id')]||'').trim()).filter(Boolean));
    if(owners.size>1){alert('This CSV holds several annotator IDs. Import one annotator\'s file at a time.');return;}
    const owner=owners.size?Array.from(owners)[0]:'';
    if(!annotator&&owner){annotator=owner;lsSet('aamasHV:annotator',annotator);loadSt();}
    if(owner&&owner!==annotator&&!confirm('The CSV belongs to '+owner+' but the page is set to '+annotator+'. Import anyway?'))return;
    const ids=new Set(PAGES.map(x=>x.id));const g=(r,c)=>{const j=ix(c);return j>=0?(r[j]||'').trim():'';};let n=0;
    const fresh={};
    rows.slice(1).forEach(r=>{const id=g(r,'page_id');if(!ids.has(id))return;if(!fresh[id])fresh[id]={status:'',note:'',tables:[],groups:[],next:1};const p=fresh[id];
      const rt=g(r,'row_type');
      if(rt==='page'){p.status=g(r,'page_status');p.note=g(r,'page_note');p._first_opened=g(r,'first_opened_at');p._last_saved=g(r,'last_saved_at');p._seconds=Number(g(r,'seconds_on_page'))||0;n++;}
      else if(rt==='table'){p.tables.push({key:g(r,'table_key'),ref:g(r,'table_ref'),caption:g(r,'table_caption'),results:g(r,'results_table'),orient:g(r,'orientation'),rule:g(r,'bold_rule')});}
      else if(rt==='group'){p.groups.push({key:g(r,'group_key'),table:g(r,'group_table_key'),label:g(r,'group_label'),winner:g(r,'winner_value'),best:g(r,'bold_is_best'),x:g(r,'x_px'),y:g(r,'y_px'),note:g(r,'group_note')});}});
    Object.keys(fresh).forEach(id=>{const p=fresh[id];const ks=p.tables.map(t=>t.key).concat(p.groups.map(x=>x.key)).map(k=>parseInt(String(k).slice(1),10)||0);p.next=1+Math.max(0,...ks);
      p.groups.forEach(x=>{x.x=x.x===''?'':Number(x.x);x.y=x.y===''?'':Number(x.y);});st[id]=p;});
    persist();alert('Imported '+n+' pages for annotator '+annotator+'.');render();};
  rd.readAsText(f,'utf-8');ev.target.value='';});
document.addEventListener('keydown',ev=>{if(ev.altKey&&ev.key==='ArrowLeft'){ev.preventDefault();go(cur-1);}if(ev.altKey&&ev.key==='ArrowRight'){ev.preventDefault();go(cur+1);}});
window.addEventListener('beforeunload',()=>{leavePage();});
loadSt();rebuildView();{const k=view.findIndex(x=>!isDone(x.id));cur=k<0?0:k;}render();
</script></body></html>
"""


def _fill(template: str, *, title: str, intro_html: str, cfg: dict) -> str:
    # json.dumps escapes nothing that could close the script element by
    # itself; "</" is broken up so a title containing "</script>" cannot.
    payload = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    return (template.replace("__CSS__", CSS)
            .replace("__COMMON__", COMMON_JS)
            .replace("__TITLE__", _html.escape(title))
            .replace("__INTRO__", intro_html)
            .replace("__CFG__", payload))


def form_kit_html(*, kit: str, version: str, title: str, intro_html: str, items: list, fields: list,
                  sets: dict, default_set: str, export_name: str, gates: list | None = None) -> str:
    """items: [{id, sets, meta: [str], links: [{label, href}], image|None, image_note, context, context_title}]
    fields: [{name, label, kind: select|text|area, options: [[value, label]], help, req: True|'never'|{'if': [field, [values]]}, always}]
    gates:  [{field, skip: [values]}]: once a gate field takes a skip value, the fields after it are optional."""
    cfg = {"kit": kit, "version": version, "items": items, "fields": fields, "gates": gates or [],
           "sets": sets, "defaultSet": default_set, "exportName": export_name}
    return _fill(FORM_HTML, title=title, intro_html=intro_html, cfg=cfg)


def page_kit_html(*, kit: str, version: str, title: str, intro_html: str, items: list,
                  sets: dict, default_set: str, export_name: str) -> str:
    """items: [{id, sets, meta, links, image|None, width, height}] (width/height of the image in pixels)."""
    cfg = {"kit": kit, "version": version, "items": items, "sets": sets, "defaultSet": default_set,
           "exportName": export_name}
    return _fill(PAGE_HTML, title=title, intro_html=intro_html, cfg=cfg)
