#!/usr/bin/env python3
"""Build a self-contained, static HTML watchlist dashboard from data.json.

Usage:  python3 build_dashboard.py data.json dashboard.html
The output is a single .html file with the market snapshot inlined as JSON,
so it renders anywhere with no server, no network and no build step.
"""
import json, sys, html as _html

def region(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith(".NS") or t.endswith(".BO"):
        return "India"
    if t.endswith(".L"):
        return "London"
    if t.endswith(".IL"):
        return "Tel Aviv"
    return "US / Other"

def main(src, dst):
    with open(src) as f:
        d = json.load(f)

    # enrich rows with region
    for r in d["rows"]:
        r["region"] = region(r["ticker"])

    # flat, time-sorted news list
    flat = []
    for tk, items in d.get("news", {}).items():
        for n in items:
            n = dict(n)
            n["ticker"] = tk
            flat.append(n)
    flat.sort(key=lambda n: n.get("ts", 0), reverse=True)
    d["newsflat"] = flat

    payload = json.dumps(d, separators=(",", ":"))
    html = TEMPLATE.replace("/*__DATA__*/null", payload)
    with open(dst, "w") as f:
        f.write(html)
    print(f"wrote {dst} ({len(html)} bytes); rows={len(d['rows'])} news={len(flat)}")

TEMPLATE = r"""<title>Watchlist Pulse</title>
<meta name="description" content="Momentum, volume and news snapshot across a 66-ticker global watchlist.">
<style>
/* Layout: sticky summary header over a scannable momentum table + news rail.
   Diverging red->surface->green encoding for every % cell (polarity data). */
:root{
  --bg:#f4f5f8; --surface:#ffffff; --surface-2:#eef0f5; --line:#dfe3ec;
  --ink:#141821; --ink-2:#4a5160; --ink-3:#848c9c;
  --accent:#3457d5; --accent-soft:#e6ebfc;
  --up:#1a8f5a; --up-bg:#1a8f5a; --down:#d5483a; --down-bg:#d5483a;
  --warn:#b5842b;
  --mono:"DM Mono",ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --sans:"Inter",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0c0f16; --surface:#141922; --surface-2:#1b2230; --line:#28303f;
  --ink:#eef1f7; --ink-2:#a9b2c3; --ink-3:#6b7486;
  --accent:#6f8dff; --accent-soft:#1e2740;
  --up:#39c07d; --up-bg:#2aa368; --down:#ff6f61; --down-bg:#e0554a;
  --warn:#e0b25a;
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0c0f16; --surface:#141922; --surface-2:#1b2230; --line:#28303f;
  --ink:#eef1f7; --ink-2:#a9b2c3; --ink-3:#6b7486;
  --accent:#6f8dff; --accent-soft:#1e2740;
  --up:#39c07d; --up-bg:#2aa368; --down:#ff6f61; --down-bg:#e0554a;
  --warn:#e0b25a;
  color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.45;
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.wrap{max-width:1160px;margin:0 auto;padding-block:0 48px;padding-left:16px;padding-right:16px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}

header.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;background:var(--bg);
  border-bottom:1px solid var(--line);padding-block:14px;margin-bottom:18px}
.brand{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.brand h1{font-size:clamp(1.35rem,3.4vw,1.9rem);margin:0;letter-spacing:-.02em;font-weight:700;text-wrap:balance}
.brand .dot{width:10px;height:10px;border-radius:50%;background:var(--up);box-shadow:0 0 0 4px var(--accent-soft);align-self:center}
.sub{color:var(--ink-2);font-size:.82rem;margin-top:2px}
.sub b{color:var(--ink);font-weight:600}

.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:18px 0 22px}
@media(max-width:860px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:13px 14px;min-width:0}
.kpi .lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-3);font-weight:600}
.kpi .val{font-size:1.5rem;font-weight:700;margin-top:4px;letter-spacing:-.02em}
.kpi .val small{font-size:.9rem;font-weight:600}
.kpi .meta{font-size:.74rem;color:var(--ink-2);margin-top:2px}
.pos{color:var(--up)} .neg{color:var(--down)}

.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.controls input[type=search]{flex:1;min-width:180px;background:var(--surface);color:var(--ink);
  border:1px solid var(--line);border-radius:9px;padding:9px 12px;font-size:.9rem;font-family:var(--sans)}
.controls input[type=search]:focus{outline:2px solid var(--accent);outline-offset:1px}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{background:var(--surface);border:1px solid var(--line);color:var(--ink-2);border-radius:999px;
  padding:6px 12px;font-size:.78rem;cursor:pointer;font-weight:600}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}

.tablewrap{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:.86rem;min-width:620px}
thead th{position:sticky;top:0;background:var(--surface-2);color:var(--ink-2);text-align:right;
  font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;padding:11px 12px;
  cursor:pointer;white-space:nowrap;border-bottom:1px solid var(--line);user-select:none}
thead th:first-child,tbody td:first-child{text-align:left}
thead th.spark,tbody td.spark{text-align:center;cursor:default}
thead th .ar{opacity:.5;font-size:.7em}
tbody td{padding:9px 12px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--surface-2)}
.tk{font-weight:700;font-family:var(--mono);font-size:.84rem}
.tk .rg{display:block;font-family:var(--sans);font-weight:500;font-size:.68rem;color:var(--ink-3);letter-spacing:.02em}
td.num{font-family:var(--mono);font-size:.82rem}
.cell{display:inline-block;min-width:62px;padding:3px 7px;border-radius:6px;font-weight:600;font-family:var(--mono);font-size:.8rem}
.na{color:var(--ink-3)}
svg.spk{display:block;margin:0 auto}

section.news{margin-top:30px}
section.news h2{font-size:1.1rem;margin:0 0 4px;letter-spacing:-.01em}
.news .hint{color:var(--ink-2);font-size:.82rem;margin:0 0 14px}
.newsgrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
@media(max-width:760px){.newsgrid{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:12px 14px;min-width:0}
.card .ttl{font-weight:600;font-size:.9rem;line-height:1.3;display:block;color:var(--ink)}
.card .ttl:hover{color:var(--accent)}
.card .row{display:flex;gap:8px;align-items:center;margin-bottom:7px;flex-wrap:wrap}
.ntk{font-family:var(--mono);font-weight:700;font-size:.72rem;background:var(--accent-soft);color:var(--accent);
  padding:2px 7px;border-radius:5px}
.card .mv{font-family:var(--mono);font-size:.72rem;font-weight:600}
.card .met{color:var(--ink-3);font-size:.72rem;margin-top:6px}
.loadmore{display:block;margin:16px auto 0;background:var(--surface);border:1px solid var(--line);
  color:var(--ink);border-radius:9px;padding:9px 18px;font-size:.84rem;font-weight:600;cursor:pointer}

.foot{margin-top:30px;color:var(--ink-3);font-size:.76rem;border-top:1px solid var(--line);padding-top:14px}
.themebtn{position:absolute;right:16px;top:14px;background:var(--surface);border:1px solid var(--line);
  color:var(--ink-2);border-radius:8px;width:34px;height:34px;cursor:pointer;font-size:1rem}
.empty{padding:26px;text-align:center;color:var(--ink-3)}
</style>

<div class="wrap">
  <header class="top">
    <button class="themebtn" id="themeBtn" title="Toggle theme" aria-label="Toggle light/dark">◑</button>
    <div class="brand"><span class="dot"></span><h1>Watchlist Pulse</h1></div>
    <div class="sub" id="subline"></div>
  </header>

  <div class="kpis" id="kpis"></div>

  <div class="controls">
    <input type="search" id="search" placeholder="Filter tickers…" aria-label="Filter tickers">
    <div class="chips" id="regionChips"></div>
  </div>

  <div class="tablewrap">
    <table id="tbl">
      <thead><tr>
        <th data-k="ticker">Ticker <span class="ar"></span></th>
        <th data-k="price">Price <span class="ar"></span></th>
        <th data-k="d3">3-Day <span class="ar"></span></th>
        <th data-k="w1">1-Week <span class="ar"></span></th>
        <th data-k="m1">1-Month <span class="ar"></span></th>
        <th data-k="vol">Vol vs 20d <span class="ar"></span></th>
        <th class="spark">21-Day</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <section class="news">
    <h2>📰 News, releases &amp; regulatory headlines</h2>
    <p class="hint">Latest items across the watchlist, newest first — context for the moves above.</p>
    <div class="newsgrid" id="newsgrid"></div>
    <button class="loadmore" id="loadmore" hidden>Show more headlines</button>
  </section>

  <p class="foot" id="foot"></p>
</div>

<script>
const DATA = /*__DATA__*/null;

/* ---------- theme toggle (per-viewer convenience) ---------- */
const root=document.documentElement, tb=document.getElementById('themeBtn');
try{const s=localStorage.getItem('wp-theme'); if(s)root.setAttribute('data-theme',s);}catch(e){}
tb.onclick=()=>{
  const cur=root.getAttribute('data-theme');
  const dark=cur?cur==='dark':matchMedia('(prefers-color-scheme:dark)').matches;
  const next=dark?'light':'dark'; root.setAttribute('data-theme',next);
  try{localStorage.setItem('wp-theme',next);}catch(e){}
};

/* ---------- helpers ---------- */
const $=s=>document.querySelector(s);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmtPct=v=>v==null?'—':(v>=0?'+':'')+v.toFixed(1)+'%';
const fmtPrice=v=>v==null?'—':v.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
function mix(a,b,t){const p=x=>parseInt(x,16);return '#'+[0,2,4].map(i=>{
  const v=Math.round(p(a.slice(1+i,3+i))+(p(b.slice(1+i,3+i))-p(a.slice(1+i,3+i)))*t);
  return v.toString(16).padStart(2,'0');}).join('');}
function cvar(n){return getComputedStyle(root).getPropertyValue(n).trim();}
/* diverging fill: clamp magnitude then blend surface->pole */
function cellBg(v,cap){ if(v==null) return 'transparent';
  const t=Math.min(Math.abs(v)/cap,1)*0.82+ (v===0?0:0.08);
  const surf=cvar('--surface'); const pole=cvar(v>=0?'--up-bg':'--down-bg');
  return mix(surf,pole,Math.min(t,0.9));}
function cellFg(v){ if(v==null) return 'var(--ink-3)';
  return Math.abs(v)>=6 ? '#fff' : (v>=0?'var(--up)':'var(--down)');}

function spark(vals){ if(!vals||vals.length<2) return '';
  const w=86,h=26,p=2; const mn=Math.min(...vals),mx=Math.max(...vals),rng=(mx-mn)||1;
  const x=i=>p+i*(w-2*p)/(vals.length-1), y=v=>h-p-((v-mn)/rng)*(h-2*p);
  const up=vals[vals.length-1]>=vals[0]; const col=up?'var(--up)':'var(--down)';
  const d=vals.map((v,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1)).join(' ');
  const lx=x(vals.length-1).toFixed(1),ly=y(vals[vals.length-1]).toFixed(1);
  return `<svg class="spk" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true">
    <path d="${d}" fill="none" stroke="${col}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${lx}" cy="${ly}" r="2.3" fill="${col}"/></svg>`;}

/* ---------- state ---------- */
let sortKey='w1', sortDir=-1, region='All', query='';
const regions=['All',...Array.from(new Set(DATA.rows.map(r=>r.region)))];

/* ---------- KPI strip ---------- */
function renderKpis(){
  const rows=DATA.rows, withW=rows.filter(r=>r.w1!=null);
  const gain=withW.filter(r=>r.w1>0).length, lose=withW.filter(r=>r.w1<0).length;
  const best=withW.reduce((a,b)=>b.w1>a.w1?b:a,withW[0]);
  const worst=withW.reduce((a,b)=>b.w1<a.w1?b:a,withW[0]);
  const withV=rows.filter(r=>r.vol!=null);
  const spike=withV.reduce((a,b)=>b.vol>a.vol?b:a,withV[0]);
  const k=[
    ['Coverage',`${rows.length}<small>/${DATA.total}</small>`,'tickers with data',''],
    ['Gainers · 1W',`<span class="pos">${gain}</span>`,`${lose} declining`,''],
    ['Top mover · 1W',esc(best.ticker),fmtPct(best.w1),'pos'],
    ['Worst · 1W',esc(worst.ticker),fmtPct(worst.w1),'neg'],
    ['Volume spike',esc(spike.ticker),fmtPct(spike.vol)+' vs 20d avg','pos'],
  ];
  $('#kpis').innerHTML=k.map(([l,v,m,c])=>`<div class="kpi"><div class="lab">${l}</div>
    <div class="val">${v}</div><div class="meta ${c}">${m}</div></div>`).join('');
}

/* ---------- table ---------- */
function renderTable(){
  let rows=DATA.rows.slice();
  if(region!=='All') rows=rows.filter(r=>r.region===region);
  if(query) rows=rows.filter(r=>r.ticker.toLowerCase().includes(query));
  rows.sort((a,b)=>{
    let x=a[sortKey],y=b[sortKey];
    if(sortKey==='ticker') return a.ticker<b.ticker?-1*sortDir:a.ticker>b.ticker?sortDir:0;
    if(x==null)return 1; if(y==null)return -1; return (x-y)*sortDir;});
  const caps={d3:12,w1:15,m1:25,vol:120};
  const body=rows.map(r=>{
    const cell=(k)=>{const v=r[k];
      return `<td class="num"><span class="cell" style="background:${cellBg(v,caps[k])};color:${cellFg(v)}">${fmtPct(v)}</span></td>`;};
    return `<tr>
      <td><span class="tk">${esc(r.ticker)}<span class="rg">${esc(r.region)}</span></span></td>
      <td class="num">${fmtPrice(r.price)}</td>
      ${cell('d3')}${cell('w1')}${cell('m1')}${cell('vol')}
      <td class="spark">${spark(r.spark)}</td></tr>`;}).join('');
  $('#tbody').innerHTML=body||`<tr><td colspan="7" class="empty">No tickers match “${esc(query)}”.</td></tr>`;
  document.querySelectorAll('thead th[data-k]').forEach(th=>{
    const ar=th.querySelector('.ar'); ar.textContent=th.dataset.k===sortKey?(sortDir<0?'▼':'▲'):'';});
}

/* ---------- news ---------- */
let newsShown=0; const NEWS_STEP=12;
function renderNews(reset){
  if(reset)newsShown=0;
  newsShown=Math.min(newsShown+NEWS_STEP,DATA.newsflat.length);
  const byT=Object.fromEntries(DATA.rows.map(r=>[r.ticker,r]));
  const items=DATA.newsflat.slice(0,newsShown).map(n=>{
    const r=byT[n.ticker]; const mv=r&&r.w1!=null?`<span class="mv ${r.w1>=0?'pos':'neg'}">${fmtPct(r.w1)} 1W</span>`:'';
    const met=[esc(n.publisher),esc(n.published)].filter(Boolean).join(' · ');
    const ttl=n.url?`<a class="ttl" href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>`
                    :`<span class="ttl">${esc(n.title)}</span>`;
    return `<div class="card"><div class="row"><span class="ntk">${esc(n.ticker)}</span>${mv}</div>
      ${ttl}<div class="met">${met}</div></div>`;}).join('');
  $('#newsgrid').innerHTML=items||`<div class="empty">No recent headlines returned.</div>`;
  $('#loadmore').hidden=newsShown>=DATA.newsflat.length;
}

/* ---------- wire up ---------- */
function init(){
  $('#subline').innerHTML=`Snapshot <b>${esc(DATA.generated)}</b> · `+
    `<b>${DATA.rows.length}</b> of ${DATA.total} tickers · 3-day, 1-week &amp; 1-month price moves, `+
    `volume vs 20-day average, and live headlines. Data via Yahoo Finance.`;
  renderKpis();
  $('#regionChips').innerHTML=regions.map(r=>
    `<button class="chip" data-r="${esc(r)}" aria-pressed="${r==='All'}">${esc(r)}</button>`).join('');
  $('#regionChips').onclick=e=>{const b=e.target.closest('.chip'); if(!b)return;
    region=b.dataset.r; document.querySelectorAll('.chip').forEach(c=>c.setAttribute('aria-pressed',c===b));
    renderTable();};
  $('#search').oninput=e=>{query=e.target.value.trim().toLowerCase();renderTable();};
  document.querySelectorAll('thead th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===sortKey)sortDir*=-1; else{sortKey=k;sortDir=k==='ticker'?1:-1;}
    renderTable();});
  $('#loadmore').onclick=()=>renderNews(false);
  renderTable(); renderNews(true);
  const failed=DATA.failed&&DATA.failed.length?` Could not resolve: ${DATA.failed.map(esc).join(', ')}.`:'';
  $('#foot').innerHTML=`Informational only — not investment advice. Prices shown in each listing's native `+
    `currency and may be delayed. Volume compares the latest session with the trailing 20-day average.${failed}`;
}
init();
</script>
"""

if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    o = sys.argv[2] if len(sys.argv) > 2 else "dashboard.html"
    main(s, o)
