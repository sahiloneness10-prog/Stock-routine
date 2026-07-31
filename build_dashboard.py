"""Generate the watchlist dashboard HTML from data.json + catalysts.json.
Emits dashboard.html (standalone) and artifact_body.html (body-only, for the
Claude artifact wrapper)."""
import json, datetime as dt

data = json.load(open("data.json"))
catalysts = json.load(open("catalysts.json"))
rows = data["rows"]
ok = [r for r in rows if "error" not in r]
err = [r for r in rows if "error" in r]

now = dt.datetime.now(dt.timezone.utc)
stamp = now.strftime("%b %d, %Y · %H:%M UTC")

payload = {
    "rows": ok,
    "failed": [r["ticker"] for r in err],
    "catalysts": catalysts,
    "generated": stamp,
    "total": len(rows),
}
blob = json.dumps(payload, separators=(",", ":"))

STYLE = r"""
:root{
  --ground:#f5f6f8; --surface:#ffffff; --surface-2:#fbfcfd; --line:#e6e9ef;
  --ink:#191d24; --ink-2:#5a6472; --ink-3:#8a94a3;
  --accent:#3a5bd9; --accent-soft:#eaeefc;
  --up:#0f9d58; --up-bg:rgba(15,157,88,.12); --up-ink:#0b7a44;
  --down:#dc3545; --down-bg:rgba(220,53,69,.12); --down-ink:#b3172a;
  --flat:#8a94a3;
  --chip:#eef1f6; --shadow:0 1px 2px rgba(20,30,50,.06),0 4px 16px rgba(20,30,50,.05);
  --mono:ui-monospace,"SF Mono",SFMono-Regular,"Cascadia Mono",Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0c0f14; --surface:#141922; --surface-2:#111620; --line:#232b38;
    --ink:#e7ecf3; --ink-2:#9aa6b6; --ink-3:#6b7688;
    --accent:#6f8dff; --accent-soft:#1a2236;
    --up:#2ec77d; --up-bg:rgba(46,199,125,.14); --up-ink:#57d996;
    --down:#ff6b7a; --down-bg:rgba(255,107,122,.15); --down-ink:#ff8a96;
    --flat:#6b7688;
    --chip:#1b2230; --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 24px rgba(0,0,0,.28);
  }
}
:root[data-theme="light"]{
  --ground:#f5f6f8; --surface:#ffffff; --surface-2:#fbfcfd; --line:#e6e9ef;
  --ink:#191d24; --ink-2:#5a6472; --ink-3:#8a94a3;
  --accent:#3a5bd9; --accent-soft:#eaeefc;
  --up:#0f9d58; --up-bg:rgba(15,157,88,.12); --up-ink:#0b7a44;
  --down:#dc3545; --down-bg:rgba(220,53,69,.12); --down-ink:#b3172a;
  --flat:#8a94a3; --chip:#eef1f6; --shadow:0 1px 2px rgba(20,30,50,.06),0 4px 16px rgba(20,30,50,.05);
}
:root[data-theme="dark"]{
  --ground:#0c0f14; --surface:#141922; --surface-2:#111620; --line:#232b38;
  --ink:#e7ecf3; --ink-2:#9aa6b6; --ink-3:#6b7688;
  --accent:#6f8dff; --accent-soft:#1a2236;
  --up:#2ec77d; --up-bg:rgba(46,199,125,.14); --up-ink:#57d996;
  --down:#ff6b7a; --down-bg:rgba(255,107,122,.15); --down-ink:#ff8a96;
  --flat:#6b7688; --chip:#1b2230; --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 24px rgba(0,0,0,.28);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  line-height:1.5;-webkit-font-smoothing:antialiased;}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 72px;}
.tnum{font-variant-numeric:tabular-nums;font-family:var(--mono);}

/* Header */
header.top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:16px;
  padding-bottom:20px;border-bottom:1px solid var(--line);margin-bottom:24px;}
.brand{display:flex;flex-direction:column;gap:6px;}
.eyebrow{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);font-weight:700;
  display:flex;align-items:center;gap:8px;}
.eyebrow::before{content:"";width:22px;height:2px;background:var(--accent);display:inline-block;}
h1{font-size:clamp(24px,3.4vw,34px);margin:0;font-weight:750;letter-spacing:-.02em;text-wrap:balance;}
.sub{color:var(--ink-2);font-size:14px;margin:0;}
.meta{text-align:right;font-size:12.5px;color:var(--ink-3);display:flex;flex-direction:column;gap:3px;}
.meta b{color:var(--ink-2);font-weight:600;}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--up);
  box-shadow:0 0 0 3px var(--up-bg);margin-right:6px;vertical-align:middle;}

/* KPI strip */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:30px;}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 16px;
  box-shadow:var(--shadow);display:flex;flex-direction:column;gap:5px;position:relative;overflow:hidden;}
.kpi .lab{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);font-weight:600;}
.kpi .val{font-size:26px;font-weight:700;letter-spacing:-.01em;}
.kpi .val small{font-size:14px;color:var(--ink-3);font-weight:600;}
.kpi .tag{font-size:12.5px;color:var(--ink-2);}
.kpi.up .val,.up-ink{color:var(--up-ink);}
.kpi.down .val,.down-ink{color:var(--down-ink);}

/* Section heads */
.sec{margin:38px 0 16px;display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;}
.sec h2{font-size:18px;margin:0;font-weight:700;letter-spacing:-.01em;}
.sec p{margin:0;color:var(--ink-3);font-size:13px;}

/* Movers */
.movers{display:grid;grid-template-columns:1fr 1fr;gap:16px;}
@media(max-width:720px){.movers{grid-template-columns:1fr;}}
.mcol{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:6px;box-shadow:var(--shadow);}
.mcol h3{font-size:12px;text-transform:uppercase;letter-spacing:.07em;margin:10px 12px 6px;
  color:var(--ink-2);display:flex;align-items:center;gap:7px;}
.mrow{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:10px;text-decoration:none;color:inherit;}
.mrow:hover{background:var(--surface-2);}
.mrow .tk{font-weight:700;font-size:14px;min-width:74px;}
.mrow .nm{color:var(--ink-3);font-size:12px;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.mrow .pc{font-weight:700;font-size:14.5px;min-width:78px;text-align:right;}
.spark{flex-shrink:0;}

/* Controls */
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px;}
.search{flex:1;min-width:180px;position:relative;}
.search input{width:100%;padding:9px 12px 9px 34px;border-radius:10px;border:1px solid var(--line);
  background:var(--surface);color:var(--ink);font-size:14px;font-family:var(--sans);}
.search input:focus{outline:2px solid var(--accent);outline-offset:1px;border-color:transparent;}
.search svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);color:var(--ink-3);}
.seg{display:flex;gap:2px;background:var(--chip);border-radius:10px;padding:3px;}
.seg button{border:0;background:transparent;color:var(--ink-2);font-size:12.5px;font-weight:600;
  padding:6px 11px;border-radius:8px;cursor:pointer;font-family:var(--sans);}
.seg button.on{background:var(--surface);color:var(--ink);box-shadow:var(--shadow);}

/* Table */
.tblwrap{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden;box-shadow:var(--shadow);}
.scroll{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:13.5px;min-width:720px;}
thead th{position:sticky;top:0;background:var(--surface-2);text-align:right;padding:12px 14px;
  font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-3);font-weight:700;
  border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none;}
thead th:first-child,tbody td:first-child{text-align:left;}
thead th.sortable:hover{color:var(--ink);}
thead th .ar{opacity:.4;font-size:9px;margin-left:3px;}
thead th.act .ar{opacity:1;color:var(--accent);}
tbody td{padding:10px 14px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap;}
tbody tr:last-child td{border-bottom:0;}
tbody tr:hover{background:var(--surface-2);}
.tkcell{display:flex;flex-direction:column;gap:1px;}
.tkcell b{font-size:13.5px;font-weight:700;}
.tkcell span{font-size:11px;color:var(--ink-3);max-width:220px;overflow:hidden;text-overflow:ellipsis;}
.pill{display:inline-block;min-width:64px;padding:4px 8px;border-radius:7px;font-weight:700;
  font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:12.5px;}
.pill.u{background:var(--up-bg);color:var(--up-ink);}
.pill.d{background:var(--down-bg);color:var(--down-ink);}
.pill.f{color:var(--flat);}
td.price{font-family:var(--mono);font-variant-numeric:tabular-nums;color:var(--ink-2);}
.vol{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:600;}
.vol.hi{color:var(--accent);}

/* Catalysts */
.cats{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px;
  box-shadow:var(--shadow);display:flex;flex-direction:column;gap:9px;border-left:3px solid var(--line);}
.card.g{border-left-color:var(--up);}
.card.b{border-left-color:var(--down);}
.card .ch{display:flex;align-items:center;gap:9px;flex-wrap:wrap;}
.card .ct{font-weight:800;font-size:15px;letter-spacing:-.01em;}
.card .cm{font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:700;font-size:13px;}
.chip{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:700;padding:3px 8px;
  border-radius:20px;background:var(--chip);color:var(--ink-2);}
.card h4{margin:0;font-size:13.5px;font-weight:650;line-height:1.35;}
.card p{margin:0;font-size:12.5px;color:var(--ink-2);line-height:1.5;}
.card .src{margin-top:auto;font-size:11.5px;color:var(--ink-3);display:flex;justify-content:space-between;gap:8px;padding-top:4px;}
.card .src a{color:var(--accent);text-decoration:none;}
.card .src a:hover{text-decoration:underline;}

footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);color:var(--ink-3);font-size:12px;
  display:flex;flex-direction:column;gap:6px;}
.legend{display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:12px;color:var(--ink-2);}
.legend i{width:11px;height:11px;border-radius:3px;display:inline-block;margin-right:5px;vertical-align:-1px;}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

BODY = """
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="eyebrow">Watchlist Intelligence</div>
      <h1>Momentum &amp; Catalyst Dashboard</h1>
      <p class="sub">Multi-window price momentum, volume shifts and the news behind the moves.</p>
    </div>
    <div class="meta">
      <div><span class="dot"></span><b id="mstat"></b></div>
      <div>Updated <b id="mstamp"></b></div>
      <div>Source: Yahoo Finance · daily close</div>
    </div>
  </header>

  <div class="kpis" id="kpis"></div>

  <div class="sec"><div><h2>Standout movers</h2><p>Largest 1-week swings in the list</p></div></div>
  <div class="movers" id="movers"></div>

  <div class="sec"><div><h2>Full watchlist</h2><p>Click any column to sort · search to filter</p></div></div>
  <div class="controls">
    <div class="search">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input id="q" placeholder="Filter by ticker or name…" autocomplete="off">
    </div>
    <div class="seg" id="filt">
      <button data-f="all" class="on">All</button>
      <button data-f="up">Gainers</button>
      <button data-f="down">Losers</button>
      <button data-f="vol">Volume spikes</button>
    </div>
  </div>
  <div class="tblwrap"><div class="scroll"><table>
    <thead><tr>
      <th class="sortable" data-k="ticker">Ticker</th>
      <th class="sortable" data-k="price">Price</th>
      <th class="sortable act" data-k="d3">3-Day <span class="ar">▼</span></th>
      <th class="sortable" data-k="w1">1-Week <span class="ar"></span></th>
      <th class="sortable" data-k="m1">1-Month <span class="ar"></span></th>
      <th class="sortable" data-k="vol_chg">Vol vs 20d <span class="ar"></span></th>
      <th>30-Day trend</th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table></div></div>

  <div class="sec"><div><h2>Catalysts &amp; news</h2><p>Why the notable names moved — earnings, guidance, regulatory &amp; sector drivers</p></div></div>
  <div class="cats" id="cats"></div>

  <footer>
    <div class="legend">
      <span><i style="background:var(--up)"></i>Gain</span>
      <span><i style="background:var(--down)"></i>Loss</span>
      <span><i style="background:var(--accent)"></i>Elevated volume</span>
      <span id="failnote"></span>
    </div>
    <div>% changes use trading-day look-backs (3D ≈ 3 sessions, 1W ≈ 5, 1M ≈ 21). Volume compares the latest session to its trailing 20-day average.</div>
    <div>Informational only — not investment advice. Data may be delayed and some tickers can fail to resolve.</div>
  </footer>
</div>
<script id="payload" type="application/json">__BLOB__</script>
<script>
const D = JSON.parse(document.getElementById('payload').textContent);
const $ = s => document.querySelector(s);
const fmtPc = v => v==null? '—' : (v>=0?'+':'')+v.toFixed(2)+'%';
const fmtPr = v => v==null? '—' : v>=1000? v.toLocaleString(undefined,{maximumFractionDigits:0}) : v.toFixed(2);
const cls = v => v==null?'f':v>0?'u':v<0?'d':'f';
const arrow = v => v==null?'':v>0?'▲':v<0?'▼':'';

document.getElementById('mstamp').textContent = D.generated;
document.getElementById('mstat').textContent = D.rows.length+' of '+D.total+' tickers live';

/* ---- sparkline ---- */
function spark(vals,w=88,h=26){
  if(!vals||vals.length<2) return '';
  const mn=Math.min(...vals),mx=Math.max(...vals),rng=(mx-mn)||1,p=2;
  const up=vals[vals.length-1]>=vals[0];
  const col=up?'var(--up)':'var(--down)';
  const pts=vals.map((v,i)=>[p+i/(vals.length-1)*(w-2*p), h-p-((v-mn)/rng)*(h-2*p)]);
  const line=pts.map((q,i)=>(i?'L':'M')+q[0].toFixed(1)+' '+q[1].toFixed(1)).join(' ');
  const area=line+` L${(w-p).toFixed(1)} ${h-p} L${p} ${h-p} Z`;
  const id='g'+Math.floor(vals[0]*1000%9999)+vals.length;
  const e=pts[pts.length-1];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1">
      <stop offset="0" stop-color="${col}" stop-opacity=".22"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#${id})"/><path d="${line}" fill="none" stroke="${col}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${e[0].toFixed(1)}" cy="${e[1].toFixed(1)}" r="2.3" fill="${col}"/></svg>`;
}

/* ---- KPIs ---- */
(function(){
  const r=D.rows, w=r.map(x=>x.w1).filter(v=>v!=null);
  const g=r.filter(x=>x.w1>0).length, l=r.filter(x=>x.w1<0).length;
  const avg=w.reduce((a,b)=>a+b,0)/w.length;
  const best=r.filter(x=>x.w1!=null).reduce((a,b)=>b.w1>a.w1?b:a);
  const worst=r.filter(x=>x.w1!=null).reduce((a,b)=>b.w1<a.w1?b:a);
  const vspike=r.filter(x=>x.vol_chg!=null&&x.vol_chg>50).length;
  const k=[
    {lab:'Median breadth (1W)',val:`${g}<small> up</small> / ${l}<small> dn</small>`,tag:'Gainers vs losers',c:g>=l?'up':'down'},
    {lab:'Avg 1-week move',val:fmtPc(avg),tag:'Across the list',c:avg>=0?'up':'down'},
    {lab:'Top gainer (1W)',val:best.ticker,tag:fmtPc(best.w1),c:'up'},
    {lab:'Top decliner (1W)',val:worst.ticker,tag:fmtPc(worst.w1),c:'down'},
    {lab:'Volume spikes',val:`${vspike}`,tag:'>50% vs 20-day avg',c:''},
  ];
  $('#kpis').innerHTML=k.map(x=>`<div class="kpi ${x.c}"><div class="lab">${x.lab}</div>
    <div class="val">${x.val}</div><div class="tag ${x.c?x.c+'-ink':''}">${x.tag}</div></div>`).join('');
})();

/* ---- movers ---- */
(function(){
  const r=D.rows.filter(x=>x.w1!=null);
  const gain=[...r].sort((a,b)=>b.w1-a.w1).slice(0,6);
  const lose=[...r].sort((a,b)=>a.w1-b.w1).slice(0,6);
  const row=x=>`<div class="mrow"><span class="tk">${x.ticker}</span>
    <span class="nm">${x.name||''}</span>${spark(x.spark)}
    <span class="pc ${cls(x.w1)==='u'?'up-ink':'down-ink'}">${arrow(x.w1)} ${fmtPc(x.w1)}</span></div>`;
  $('#movers').innerHTML=
    `<div class="mcol"><h3>▲ Leaders</h3>${gain.map(row).join('')}</div>
     <div class="mcol"><h3>▼ Laggards</h3>${lose.map(row).join('')}</div>`;
})();

/* ---- table ---- */
let sortK='d3', sortDir=-1, filt='all', query='';
const tb=$('#tbody');
function render(){
  let r=D.rows.filter(x=>{
    if(query){const q=query.toLowerCase();
      if(!(x.ticker.toLowerCase().includes(q)||(x.name||'').toLowerCase().includes(q)))return false;}
    if(filt==='up')return x.w1>0;
    if(filt==='down')return x.w1<0;
    if(filt==='vol')return x.vol_chg!=null&&x.vol_chg>50;
    return true;
  });
  r.sort((a,b)=>{
    let x=a[sortK],y=b[sortK];
    if(sortK==='ticker')return sortDir*x.localeCompare(y);
    x=x==null?-1e9:x; y=y==null?-1e9:y; return sortDir*(x-y);
  });
  tb.innerHTML=r.map(x=>{
    const vhi=x.vol_chg!=null&&x.vol_chg>50?' hi':'';
    const pill=(v)=>`<span class="pill ${cls(v)}">${v==null?'—':(v>0?'+':'')+v.toFixed(1)+'%'}</span>`;
    return `<tr><td><div class="tkcell"><b>${x.ticker}</b><span>${x.name||''}</span></div></td>
      <td class="price">${fmtPr(x.price)}</td>
      <td>${pill(x.d3)}</td><td>${pill(x.w1)}</td><td>${pill(x.m1)}</td>
      <td class="vol${vhi}">${x.vol_chg==null?'—':(x.vol_chg>0?'+':'')+Math.round(x.vol_chg)+'%'}</td>
      <td>${spark(x.spark,96,26)}</td></tr>`;
  }).join('')|| '<tr><td colspan="7" style="text-align:center;padding:26px;color:var(--ink-3)">No matches</td></tr>';
  document.querySelectorAll('thead th').forEach(th=>{
    th.classList.toggle('act',th.dataset.k===sortK);
    const ar=th.querySelector('.ar'); if(ar&&th.dataset.k===sortK)ar.textContent=sortDir<0?'▼':'▲';
    else if(ar)ar.textContent='';
  });
}
document.querySelectorAll('thead th.sortable').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k;
  if(k===sortK)sortDir*=-1; else{sortK=k;sortDir=k==='ticker'?1:-1;}
  render();
}));
$('#q').addEventListener('input',e=>{query=e.target.value;render();});
document.querySelectorAll('#filt button').forEach(b=>b.addEventListener('click',()=>{
  document.querySelectorAll('#filt button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on'); filt=b.dataset.f; render();
}));
render();

/* ---- catalysts ---- */
(function(){
  const byT={}; D.rows.forEach(x=>byT[x.ticker]=x);
  const html=D.catalysts.map(c=>{
    const m=byT[c.ticker]; const w1=m?m.w1:null;
    const good=w1!=null&&w1>=0;
    return `<div class="card ${good?'g':'b'}">
      <div class="ch"><span class="ct">${c.ticker}</span>
        <span class="cm ${good?'up-ink':'down-ink'}">${arrow(w1)} ${fmtPc(w1)} <span style="color:var(--ink-3);font-weight:600">1W</span></span>
        <span class="chip">${c.category}</span></div>
      <h4>${c.headline}</h4>
      <p>${c.detail}</p>
      <div class="src"><span>${c.source} · ${c.date}</span>${c.url?`<a href="${c.url}" target="_blank" rel="noopener">Read →</a>`:''}</div>
    </div>`;
  }).join('');
  $('#cats').innerHTML=html;
})();

if(D.failed&&D.failed.length)
  $('#failnote').innerHTML='<span style="color:var(--ink-3)">Unresolved: '+D.failed.join(', ')+'</span>';
</script>
"""

body_html = BODY.replace("__BLOB__", blob)

# artifact body-only file
with open("artifact_body.html", "w") as f:
    f.write(f"<style>\n{STYLE}\n</style>\n{body_html}")

# standalone doc for the repo
standalone = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Momentum &amp; Catalyst Dashboard</title>
<style>
*{{margin:0;padding:0}}
{STYLE}
</style>
</head>
<body>
{body_html}
</body>
</html>
"""
with open("dashboard.html", "w") as f:
    f.write(standalone)

print("wrote dashboard.html and artifact_body.html")
print("stamp:", stamp, "| ok:", len(ok), "| failed:", err and [r['ticker'] for r in err])
