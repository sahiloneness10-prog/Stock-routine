"""
Watchlist snapshot generator
============================
Fetches 3-day / 1-week / 1-month price moves, a volume shift vs the 20-day
average, and recent headlines for every ticker, then writes a single
self-contained ``watchlist_pulse.html`` dashboard (no server needed).

This is the headless companion to the interactive ``streamlit run app.py``:
it is what a scheduled job or cron can run to regenerate the dashboard.

    python generate_snapshot.py            # -> watchlist_pulse.html
    python generate_snapshot.py out.html   # custom output path
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
import re
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".yf_cache")
os.makedirs(CACHE, exist_ok=True)
try:
    yf.set_tz_cache_location(CACHE)
except Exception:
    pass

TICKERS = [
    "VENU", "DUKR", "LNZA", "SIDU", "STLTECH.NS", "HFCL.NS", "TEJASNET.NS",
    "HLIT", "NBIS", "PENG", "NOK", "SLOIF", "TE", "FLNC", "MITK", "HUMA",
    "AAOI", "BE", "SWMR", "AMPX", "KRKNF", "AXTI", "COHR", "VYX", "NATL",
    "FLTR.L", "LODE", "SATL", "SNDK", "MOH", "HAL", "PFE", "EWZ", "MELI",
    "DUOL", "KLAR", "FIG", "ASML", "TATE.L", "HAIN", "XIACY", "VWSYF", "ZETA",
    "GYM.L", "GNC.L", "BYDDY", "BYND", "DKS", "OTLY", "SNOW", "SAP", "WDAY",
    "MKS.L", "JD.L", "TRN.L", "NTPCGREEN.NS", "HMC", "GSK.L", "TSM",
    "TIMEX.BO", "0HAO.IL", "NVDA", "BT-A.L", "JDW.L", "SBRY.L", "ADTN",
]

# Trading-day look-backs for each momentum window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

# Region / local-currency inference from the ticker suffix.
SUFFIX = {
    ".NS": ("India (NSE)", "\u20b9"), ".BO": ("India (BSE)", "\u20b9"),
    ".L": ("London (LSE)", "p"), ".IL": ("Tel Aviv", "\u20aa"),
}


def _series(data, ticker, field):
    try:
        s = data[ticker][field] if isinstance(data.columns, pd.MultiIndex) else data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def _pct(s, periods):
    s = s.dropna()
    if len(s) <= periods:
        return None
    prev = s.iloc[-1 - periods]
    if prev == 0 or pd.isna(prev):
        return None
    return float((s.iloc[-1] - prev) / prev * 100)


def _vol_change(v):
    v = v.dropna()
    if len(v) < 6:
        return None
    latest = v.iloc[-1]
    base = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not base or pd.isna(base):
        return None
    return float((latest - base) / base * 100)


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return _html.unescape(text).strip()


def _fmt_unix(ts):
    try:
        return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return ""


def get_news(ticker):
    # yfinance's Ticker.news property is currently unreliable; the Search API works.
    try:
        res = yf.Search(ticker, news_count=8, enable_fuzzy_query=False)
        raw = res.news or []
    except Exception:
        return []
    items, seen = [], set()
    for c in raw:
        if not isinstance(c, dict):
            continue
        title = (c.get("title") or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        pt = c.get("providerPublishTime")
        items.append({
            "title": title,
            "summary": _clean(c.get("summary") or "")[:400],
            "publisher": c.get("publisher", ""),
            "url": c.get("link", ""),
            "published": _fmt_unix(pt) if pt else "",
            "ts": int(pt) if pt else 0,
            "type": c.get("type", ""),
        })
    items.sort(key=lambda x: x["ts"], reverse=True)
    return items[:6]


def _region(ticker):
    for suf, (rg, cur) in SUFFIX.items():
        if ticker.endswith(suf):
            return rg, cur
    return "US", "$"


def collect():
    print("Downloading price history for %d tickers..." % len(TICKERS))
    data = yf.download(TICKERS, period="3mo", interval="1d", group_by="ticker",
                       auto_adjust=True, progress=False, threads=True)
    rows = []
    for t in TICKERS:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            continue
        region, cur = _region(t)
        rows.append({
            "ticker": t, "region": region, "cur": cur,
            "price": float(close.iloc[-1]),
            "d3": _pct(close, 3), "w1": _pct(close, 5), "m1": _pct(close, 21),
            "vol": _vol_change(volume),
        })
    loaded = {r["ticker"] for r in rows}
    failed = [t for t in TICKERS if t not in loaded]
    print("Loaded %d/%d. Failed: %s" % (len(rows), len(TICKERS), failed or "none"))

    print("Fetching headlines...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(get_news, r["ticker"]): r for r in rows}
        for f in as_completed(futs):
            r = futs[f]
            try:
                r["news"] = f.result()
            except Exception:
                r["news"] = []
    for r in rows:
        r.setdefault("news", [])

    return {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(TICKERS), "loaded": len(rows), "failed": failed, "rows": rows,
    }


HTML = r"""<title>Watchlist Pulse</title>
<meta name="description" content="Live momentum, volume shifts and headlines across a 66-ticker global watchlist.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  /* Layout: sticky terminal-style header, KPI tile strip, tabbed body
     (sortable table / movers bars / news feed). Mono figures, diverging R/G. */
  :root{
    --page:#f4f4f1; --surface:#fcfcfb; --surface-2:#f9f9f7;
    --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
    --grid:#e1e0d9; --line:#c3c2b7; --ring:rgba(11,11,11,.10);
    --accent:#2a78d6; --accent-soft:rgba(42,120,214,.12);
    --up:#0b8a34; --down:#d03b3b; --flat:#898781;
    --up-fig:#046a28; --down-fig:#c23333;
    --up-wash:rgba(12,163,12,.16); --down-wash:rgba(208,59,59,.16);
    --warn:#b4790a;
    --sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
    --mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
    color-scheme:light;
  }
  @media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
    --page:#0d0d0d; --surface:#1a1a19; --surface-2:#141413;
    --ink:#f4f3ee; --ink-2:#c3c2b7; --muted:#8f8d87;
    --grid:#2c2c2a; --line:#383835; --ring:rgba(255,255,255,.10);
    --accent:#3987e5; --accent-soft:rgba(57,135,229,.16);
    --up:#2ec16b; --down:#f06a6a; --flat:#8f8d87;
    --up-fig:#44d07d; --down-fig:#ff7f7f;
    --up-wash:rgba(46,193,107,.18); --down-wash:rgba(240,106,106,.18);
    --warn:#fab219;
    color-scheme:dark;
  }}
  :root[data-theme="dark"]{
    --page:#0d0d0d; --surface:#1a1a19; --surface-2:#141413;
    --ink:#f4f3ee; --ink-2:#c3c2b7; --muted:#8f8d87;
    --grid:#2c2c2a; --line:#383835; --ring:rgba(255,255,255,.10);
    --accent:#3987e5; --accent-soft:rgba(57,135,229,.16);
    --up:#2ec16b; --down:#f06a6a; --flat:#8f8d87;
    --up-fig:#44d07d; --down-fig:#ff7f7f;
    --up-wash:rgba(46,193,107,.18); --down-wash:rgba(240,106,106,.18);
    --warn:#fab219;
    color-scheme:dark;
  }
  *{box-sizing:border-box}
  body{background:var(--page);color:var(--ink);font-family:var(--sans);
    line-height:1.45;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:0}
  a{color:var(--accent);text-decoration:none}
  a:hover{text-decoration:underline}

  header.top{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;
    background:var(--page);border-bottom:1px solid var(--grid)}
  .top-in{max-width:1180px;margin:0 auto;padding:14px 16px;
    display:flex;flex-wrap:wrap;align-items:baseline;gap:8px 16px}
  .brand{display:flex;align-items:baseline;gap:10px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--up);
    align-self:center;box-shadow:0 0 0 3px var(--up-wash)}
  h1{font-size:1.15rem;font-weight:700;margin:0;letter-spacing:.2px}
  .sub{color:var(--muted);font-size:.78rem;font-family:var(--mono)}
  .theme-btn{margin-left:auto;font-family:var(--mono);font-size:.72rem;
    background:var(--surface);color:var(--ink-2);border:1px solid var(--line);
    border-radius:7px;padding:5px 9px;cursor:pointer}
  .theme-btn:hover{border-color:var(--accent);color:var(--accent)}

  /* KPI tiles */
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:18px 0}
  .kpi{background:var(--surface);border:1px solid var(--ring);border-radius:11px;
    padding:12px 13px;min-width:0}
  .kpi .lab{font-size:.66rem;letter-spacing:.7px;text-transform:uppercase;
    color:var(--muted);font-weight:600}
  .kpi .val{font-family:var(--mono);font-size:1.5rem;font-weight:600;
    margin-top:5px;line-height:1.1;font-variant-numeric:tabular-nums}
  .kpi .note{font-family:var(--mono);font-size:.74rem;color:var(--ink-2);margin-top:3px}
  .pos{color:var(--up-fig)} .neg{color:var(--down-fig)}

  /* tabs */
  .tabs{display:flex;gap:4px;border-bottom:1px solid var(--grid);margin-top:6px}
  .tab{background:none;border:0;border-bottom:2px solid transparent;
    color:var(--ink-2);font-family:var(--sans);font-size:.86rem;font-weight:600;
    padding:9px 12px;cursor:pointer}
  .tab[aria-selected="true"]{color:var(--ink);border-bottom-color:var(--accent)}
  .panel{padding:16px 0 28px}

  /* controls */
  .controls{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
  .controls input,.controls select{font-family:var(--mono);font-size:.78rem;
    background:var(--surface);color:var(--ink);border:1px solid var(--line);
    border-radius:7px;padding:6px 9px}
  .controls input{min-width:150px}
  .hint{color:var(--muted);font-size:.74rem;margin-left:auto;font-family:var(--mono)}

  /* table */
  .tbl-scroll{overflow-x:auto;border:1px solid var(--grid);border-radius:11px}
  table{border-collapse:collapse;width:100%;font-size:.82rem;min-width:620px}
  thead th{position:sticky;top:0;background:var(--surface-2);color:var(--ink-2);
    text-align:right;padding:9px 11px;font-size:.68rem;letter-spacing:.5px;
    text-transform:uppercase;font-weight:700;cursor:pointer;white-space:nowrap;
    border-bottom:1px solid var(--grid);user-select:none}
  thead th:first-child,thead th.l{text-align:left}
  thead th[data-sort]:hover{color:var(--accent)}
  thead th .arw{color:var(--accent);font-size:.7rem}
  tbody td{padding:8px 11px;text-align:right;font-family:var(--mono);
    font-variant-numeric:tabular-nums;border-bottom:1px solid var(--grid);white-space:nowrap}
  tbody tr{cursor:pointer}
  tbody tr:hover{background:var(--accent-soft)}
  td.tk{text-align:left;font-weight:600;color:var(--ink)}
  td.rg{text-align:left;font-family:var(--sans);color:var(--muted);font-size:.74rem}
  .cell{display:inline-block;min-width:62px;padding:2px 7px;border-radius:6px;font-weight:500}
  td.na{color:var(--muted)}
  .newscount{font-family:var(--sans);background:var(--accent-soft);color:var(--accent);
    border-radius:20px;padding:1px 8px;font-size:.7rem;font-weight:600}
  tr.detail td{background:var(--surface-2);cursor:default;text-align:left;
    font-family:var(--sans);white-space:normal;padding:0}
  .detail-in{padding:14px 16px;display:grid;gap:12px}
  .mini{display:flex;flex-wrap:wrap;gap:8px}
  .chip{font-family:var(--mono);font-size:.74rem;border:1px solid var(--ring);
    border-radius:7px;padding:5px 9px;background:var(--surface)}
  .chip b{color:var(--muted);font-weight:600;margin-right:5px;text-transform:uppercase;
    font-size:.64rem;letter-spacing:.5px}

  /* movers bars */
  .movers{display:grid;grid-template-columns:1fr 1fr;gap:22px}
  .movers h3{font-size:.82rem;text-transform:uppercase;letter-spacing:.6px;
    color:var(--ink-2);margin:0 0 10px}
  .bar-row{display:grid;grid-template-columns:78px 1fr 64px;align-items:center;
    gap:9px;margin-bottom:7px;font-family:var(--mono);font-size:.78rem}
  .bar-row .nm{font-weight:600;color:var(--ink);overflow:hidden;text-overflow:ellipsis}
  .track{height:15px;background:var(--surface-2);border-radius:4px;position:relative;overflow:hidden}
  .fill{display:block;height:100%;border-radius:4px;min-width:3px}
  .bar-row .pct{text-align:right;font-variant-numeric:tabular-nums}

  /* news */
  .news-list{display:grid;gap:10px}
  .nitem{background:var(--surface);border:1px solid var(--ring);border-radius:11px;
    padding:12px 14px;display:grid;gap:5px}
  .nitem .nh{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
  .badge{font-family:var(--mono);font-size:.68rem;font-weight:600;background:var(--accent-soft);
    color:var(--accent);border-radius:6px;padding:2px 7px}
  .badge.up{background:var(--up-wash);color:var(--up-fig)}
  .badge.dn{background:var(--down-wash);color:var(--down-fig)}
  .nitem .ttl{font-weight:600;font-size:.92rem;line-height:1.35}
  .nitem .meta{font-family:var(--mono);font-size:.72rem;color:var(--muted)}
  .nitem .sum{font-size:.84rem;color:var(--ink-2)}
  .empty{color:var(--muted);font-family:var(--mono);font-size:.82rem;padding:16px 0}
  footer{color:var(--muted);font-size:.74rem;border-top:1px solid var(--grid);
    padding:16px 0 30px;font-family:var(--mono);line-height:1.6}

  @media (max-width:860px){.kpis{grid-template-columns:repeat(3,1fr)}
    .movers{grid-template-columns:1fr}}
  @media (max-width:460px){.kpis{grid-template-columns:repeat(2,1fr)}
    h1{font-size:1.02rem}}
</style>

<header class="top">
  <div class="top-in">
    <div class="brand"><span class="dot"></span><h1>Watchlist Pulse</h1></div>
    <span class="sub" id="stamp"></span>
    <button class="theme-btn" id="theme">◐ theme</button>
  </div>
</header>

<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="tabs" role="tablist">
    <button class="tab" role="tab" aria-selected="true" data-p="overview">Overview</button>
    <button class="tab" role="tab" aria-selected="false" data-p="movers">Movers</button>
    <button class="tab" role="tab" aria-selected="false" data-p="news">News &amp; filings</button>
  </div>

  <section class="panel" id="p-overview">
    <div class="controls">
      <input id="q" placeholder="filter ticker…" aria-label="filter ticker">
      <select id="region"><option value="">all regions</option></select>
      <span class="hint" id="rowhint"></span>
    </div>
    <div class="tbl-scroll">
      <table id="tbl">
        <thead><tr>
          <th class="l" data-sort="ticker">Ticker</th>
          <th class="l" data-sort="region">Region</th>
          <th data-sort="price">Price</th>
          <th data-sort="d3">3-day %</th>
          <th data-sort="w1">1-week %</th>
          <th data-sort="m1">1-month %</th>
          <th data-sort="vol">Vol vs 20d</th>
          <th data-sort="nc">News</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </section>

  <section class="panel" id="p-movers" hidden></section>
  <section class="panel" id="p-news" hidden>
    <div class="controls">
      <select id="nfilter"><option value="">all tickers</option></select>
      <span class="hint" id="newshint"></span>
    </div>
    <div class="news-list" id="newslist"></div>
  </section>

  <footer>
    Data via Yahoo Finance · percentages are trading-day look-backs (3 / 5 / 21 sessions) ·
    volume vs trailing 20-session average · prices in each listing's local currency.<br>
    Informational only — not investment advice. Feeds may be delayed and some tickers may not resolve.
  </footer>
</div>

<script>
const DATA = __PAYLOAD__;
const rows = DATA.rows;
const fmtP = n => n==null? '—' : (Math.abs(n)>=1000? n.toLocaleString(undefined,{maximumFractionDigits:0}) : n.toFixed(2));
const fmtPct = n => n==null? '—' : (n>=0?'+':'') + n.toFixed(1) + '%';
const cls = n => n==null? 'na' : n>0.05? 'pos' : n<-0.05? 'neg' : '';

/* theme toggle */
const root=document.documentElement, tb=document.getElementById('theme');
tb.onclick=()=>{const cur=root.getAttribute('data-theme')
  || (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  root.setAttribute('data-theme', cur==='dark'?'light':'dark');};

document.getElementById('stamp').textContent = 'as of ' + DATA.generated
  + '  ·  ' + DATA.loaded + '/' + DATA.total + ' tickers';

/* ---- KPIs ---- */
const w1 = rows.filter(r=>r.w1!=null);
const byW1 = [...w1].sort((a,b)=>b.w1-a.w1);
const gain = w1.filter(r=>r.w1>0).length, lose = w1.filter(r=>r.w1<0).length;
const best = byW1[0], worst = byW1[byW1.length-1];
const volEvt = rows.filter(r=>r.vol!=null).sort((a,b)=>b.vol-a.vol)[0];
const avgW1 = w1.length? w1.reduce((s,r)=>s+r.w1,0)/w1.length : null;
function kpi(lab,val,note,klass){return `<div class="kpi"><div class="lab">${lab}</div>
  <div class="val ${klass||''}">${val}</div><div class="note">${note||''}</div></div>`;}
document.getElementById('kpis').innerHTML = [
  kpi('Breadth 1W', `${gain}<span style="color:var(--muted);font-size:1rem">/</span>${lose}`,'gainers vs losers'),
  kpi('Avg move 1W', fmtPct(avgW1), 'across loaded names', cls(avgW1)),
  kpi('Top mover 1W', best?best.ticker:'—', best?fmtPct(best.w1):'', best?cls(best.w1):''),
  kpi('Worst mover 1W', worst?worst.ticker:'—', worst?fmtPct(worst.w1):'', worst?cls(worst.w1):''),
  kpi('Volume spike', volEvt?volEvt.ticker:'—', volEvt?fmtPct(volEvt.vol)+' vs 20d':'', volEvt?'pos':''),
  kpi('Headlines', String(rows.reduce((s,r)=>s+(r.news?r.news.length:0),0)), 'in feed'),
].join('');

/* ---- diverging cell wash ---- */
function washCell(n){
  if(n==null) return `<span class="cell na">—</span>`;
  const mag = Math.min(Math.abs(n)/12,1);
  const a = (0.12 + 0.5*mag).toFixed(2);
  const bg = n>0 ? `var(--up-wash)` : n<0 ? `var(--down-wash)` : 'transparent';
  const col = n>0 ? 'var(--up-fig)' : n<0 ? 'var(--down-fig)' : 'var(--muted)';
  const style = n===0?'':`background:${bg};opacity:${0.55+0.45*mag}`;
  return `<span class="cell" style="color:${col};background:${n>0?`rgba(12,163,12,${a})`:n<0?`rgba(208,59,59,${a})`:'transparent'}">${fmtPct(n)}</span>`;
}

/* ---- table ---- */
const tbody=document.getElementById('tbody');
let sortKey='w1', sortDir=-1, open=new Set();
rows.forEach(r=>r.nc = r.news? r.news.length:0);

/* region dropdowns */
const regions=[...new Set(rows.map(r=>r.region))].sort();
const regSel=document.getElementById('region');
regions.forEach(rg=>regSel.innerHTML+=`<option>${rg}</option>`);
const nf=document.getElementById('nfilter');
[...rows].sort((a,b)=>a.ticker.localeCompare(b.ticker))
  .filter(r=>r.nc).forEach(r=>nf.innerHTML+=`<option>${r.ticker}</option>`);

function visible(){
  const q=document.getElementById('q').value.trim().toUpperCase();
  const rg=regSel.value;
  return rows.filter(r=>(!q||r.ticker.includes(q))&&(!rg||r.region===rg));
}
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function render(){
  const v=visible();
  v.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
    if(typeof x==='string') return sortDir*x.localeCompare(y);
    if(x==null) return 1; if(y==null) return -1; return sortDir*(x-y);});
  let h='';
  for(const r of v){
    h+=`<tr data-t="${r.ticker}">
      <td class="tk">${r.ticker}</td>
      <td class="rg">${r.region}</td>
      <td>${r.cur}${fmtP(r.price)}</td>
      <td>${washCell(r.d3)}</td>
      <td>${washCell(r.w1)}</td>
      <td>${washCell(r.m1)}</td>
      <td class="${cls(r.vol)}">${r.vol==null?'—':fmtPct(r.vol)}</td>
      <td>${r.nc?`<span class="newscount">${r.nc}</span>`:'<span class="na">0</span>'}</td></tr>`;
    if(open.has(r.ticker)){
      const nn=(r.news||[]).map(n=>`<div style="margin-bottom:8px">
        <a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>
        <div class="meta" style="font-family:var(--mono);font-size:.72rem;color:var(--muted)">${esc(n.publisher)}${n.published?' · '+esc(n.published):''}</div>
      </div>`).join('') || '<span class="empty">No headlines resolved for this ticker.</span>';
      h+=`<tr class="detail"><td colspan="8"><div class="detail-in">
        <div class="mini">
          <span class="chip"><b>price</b>${r.cur}${fmtP(r.price)}</span>
          <span class="chip"><b>3-day</b><span class="${cls(r.d3)}">${fmtPct(r.d3)}</span></span>
          <span class="chip"><b>1-week</b><span class="${cls(r.w1)}">${fmtPct(r.w1)}</span></span>
          <span class="chip"><b>1-month</b><span class="${cls(r.m1)}">${fmtPct(r.m1)}</span></span>
          <span class="chip"><b>vol 20d</b><span class="${cls(r.vol)}">${fmtPct(r.vol)}</span></span>
        </div>
        <div>${nn}</div></div></td></tr>`;
    }
  }
  tbody.innerHTML=h;
  document.getElementById('rowhint').textContent=`${v.length} of ${rows.length} shown · click a row for news`;
}
tbody.onclick=e=>{const tr=e.target.closest('tr[data-t]');if(!tr)return;
  const t=tr.dataset.t; open.has(t)?open.delete(t):open.add(t); render();};
document.querySelectorAll('th[data-sort]').forEach(th=>{th.onclick=()=>{
  const k=th.dataset.sort;
  if(sortKey===k) sortDir*=-1; else {sortKey=k; sortDir=(k==='ticker'||k==='region')?1:-1;}
  document.querySelectorAll('th .arw').forEach(a=>a.remove());
  th.insertAdjacentHTML('beforeend',` <span class="arw">${sortDir<0?'▼':'▲'}</span>`);
  render();};});
document.getElementById('q').oninput=render;
regSel.onchange=render;

/* ---- movers ---- */
function bars(list,dir){
  const max=Math.max(...list.map(r=>Math.abs(r.w1)),1);
  return list.map(r=>{
    const w=(Math.abs(r.w1)/max*100).toFixed(1);
    const col=dir>0?'var(--up)':'var(--down)';
    return `<div class="bar-row"><span class="nm">${r.ticker}</span>
      <span class="track"><span class="fill" style="width:${w}%;background:${col}"></span></span>
      <span class="pct ${dir>0?'pos':'neg'}">${fmtPct(r.w1)}</span></div>`;
  }).join('');
}
const topG=byW1.filter(r=>r.w1>0).slice(0,10);
const topL=byW1.filter(r=>r.w1<0).slice(-10).reverse();
const topV=rows.filter(r=>r.vol!=null).sort((a,b)=>b.vol-a.vol).slice(0,10);
document.getElementById('p-movers').innerHTML=`
  <div class="movers">
    <div><h3>▲ Top gainers · 1 week</h3>${bars(topG,1)||'<span class="empty">none</span>'}</div>
    <div><h3>▼ Top decliners · 1 week</h3>${bars(topL,-1)||'<span class="empty">none</span>'}</div>
  </div>
  <div style="margin-top:26px"><h3 style="font-size:.82rem;text-transform:uppercase;letter-spacing:.6px;color:var(--ink-2);margin:0 0 10px">⚡ Biggest volume surges vs 20-day average</h3>
    ${topV.map(r=>{const max=Math.max(...topV.map(x=>x.vol),1);
      return `<div class="bar-row"><span class="nm">${r.ticker}</span>
      <span class="track"><span class="fill" style="width:${(r.vol/max*100).toFixed(1)}%;background:var(--accent)"></span></span>
      <span class="pct">${fmtPct(r.vol)}</span></div>`;}).join('')}
  </div>`;

/* ---- news feed ---- */
const allNews=[];
rows.forEach(r=>(r.news||[]).forEach(n=>allNews.push({...n,ticker:r.ticker,w1:r.w1})));
allNews.sort((a,b)=>(b.ts||0)-(a.ts||0));
function renderNews(){
  const t=nf.value;
  const list=t?allNews.filter(n=>n.ticker===t):allNews;
  const nl=document.getElementById('newslist');
  if(!list.length){nl.innerHTML='<div class="empty">No headlines in the feed.</div>';}
  else nl.innerHTML=list.slice(0,120).map(n=>{
    const bc=n.w1>0?'up':n.w1<0?'dn':'';  /* badge tint by the stock's move */
    return `<div class="nitem"><div class="nh">
      <span class="badge ${bc}">${n.ticker} ${n.w1!=null?(n.w1>=0?'+':'')+n.w1.toFixed(1)+'%':''}</span>
      <span class="meta">${esc(n.publisher)}${n.published?' · '+esc(n.published):''}</span></div>
      <div class="ttl">${n.url?`<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.title)}</a>`:esc(n.title)}</div>
      ${n.summary?`<div class="sum">${esc(n.summary)}</div>`:''}</div>`;
  }).join('');
  document.getElementById('newshint').textContent=`${list.length} headlines`;
}
nf.onchange=renderNews;

/* ---- tabs ---- */
document.querySelectorAll('.tab').forEach(tab=>{tab.onclick=()=>{
  document.querySelectorAll('.tab').forEach(t=>t.setAttribute('aria-selected','false'));
  tab.setAttribute('aria-selected','true');
  ['overview','movers','news'].forEach(p=>document.getElementById('p-'+p).hidden=(p!==tab.dataset.p));
};});

render();
renderNews();
</script>
"""


def render(payload: dict) -> str:
    return HTML.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "watchlist_pulse.html"
    payload = collect()
    with open(out, "w") as fh:
        fh.write(render(payload))
    print("Wrote %s (%d tickers)." % (out, payload["loaded"]))


if __name__ == "__main__":
    main()
