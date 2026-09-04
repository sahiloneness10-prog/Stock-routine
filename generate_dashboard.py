"""
Watchlist dashboard generator
==============================
Fetches 3-day / 1-week / 1-month price moves, a volume shift versus the trailing
20-day average, and the latest headlines for every ticker in the watchlist, then
writes a single self-contained ``dashboard.html`` you can open in any browser.

Unlike ``app.py`` (which needs a running Streamlit server), this produces a static
file with the data baked in - handy for scheduled runs, e-mailing, or hosting.

Data comes straight from Yahoo Finance's public chart/search JSON endpoints via
``requests`` (which honours HTTPS_PROXY / REQUESTS_CA_BUNDLE), so it works in
sandboxes where the ``yfinance`` curl backend cannot reach the network.

Usage:
    python generate_dashboard.py            # writes dashboard.html
    python generate_dashboard.py out.html   # custom output path
"""
from __future__ import annotations

import datetime as dt
import html
import json
import sys
import time

import requests

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

BASE = "https://query1.finance.yahoo.com"
SESSION = requests.Session()
SESSION.headers.update(
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
)


# --------------------------------------------------------------------------- #
# Fetch layer
# --------------------------------------------------------------------------- #
def _get(url: str, params: dict, tries: int = 6):
    for i in range(tries):
        try:
            r = SESSION.get(url, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 999, 401, 403):
                time.sleep(1.5 * (i + 1))
                continue
            return None
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def _pct(series: list, periods: int):
    vals = [x for x in series if x is not None]
    if len(vals) <= periods:
        return None
    prev = vals[-1 - periods]
    if not prev:
        return None
    return (vals[-1] - prev) / prev * 100.0


def _volume_change(vols: list):
    v = [x for x in vols if x is not None]
    if len(v) < 6:
        return None
    latest = v[-1]
    base = [x for x in (v[-21:-1] if len(v) > 21 else v[:-1]) if x is not None]
    if not base:
        return None
    avg = sum(base) / len(base)
    if not avg:
        return None
    return (latest - avg) / avg * 100.0


def fetch_chart(ticker: str):
    j = _get(f"{BASE}/v8/finance/chart/{ticker}", {"range": "3mo", "interval": "1d"})
    if not j or not j.get("chart", {}).get("result"):
        return None
    res = j["chart"]["result"][0]
    meta = res.get("meta", {})
    quote = res["indicators"]["quote"][0]
    closes = quote.get("close", [])
    adj_block = res["indicators"].get("adjclose")
    series = adj_block[0].get("adjclose") if adj_block else None
    series = series or closes
    vols = quote.get("volume", [])
    price = next((x for x in reversed(series) if x is not None), None)
    return {
        "ticker": ticker,
        "name": meta.get("shortName") or meta.get("longName") or ticker,
        "currency": meta.get("currency", ""),
        "exchange": meta.get("fullExchangeName", ""),
        "price": price,
        "d3": _pct(series, 3),
        "w1": _pct(series, 5),
        "m1": _pct(series, 21),
        "vol": _volume_change(vols),
    }


def fetch_news(ticker: str, n: int = 6):
    j = _get(
        f"{BASE}/v1/finance/search",
        {"q": ticker, "newsCount": n, "quotesCount": 0, "enableFuzzyQuery": "false"},
    )
    if not j:
        return []
    out = []
    for item in j.get("news", [])[:n]:
        ts = item.get("providerPublishTime")
        when = (
            dt.datetime.utcfromtimestamp(ts).strftime("%b %d, %Y · %H:%M UTC")
            if ts
            else ""
        )
        out.append(
            {
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "url": item.get("link", ""),
                "published": when,
                "ts": ts or 0,
            }
        )
    out.sort(key=lambda x: x["ts"], reverse=True)
    return out


def collect():
    rows, news = [], {}
    for i, t in enumerate(TICKERS, 1):
        row = fetch_chart(t)
        if row:
            rows.append(row)
            news[t] = fetch_news(t)
            print(f"[{i}/{len(TICKERS)}] {t} ok", file=sys.stderr)
        else:
            print(f"[{i}/{len(TICKERS)}] {t} FAILED", file=sys.stderr)
        time.sleep(0.4)
    failed = [t for t in TICKERS if t not in {r["ticker"] for r in rows}]
    return {
        "generated": dt.datetime.utcnow().strftime("%A %d %B %Y · %H:%M UTC"),
        "rows": rows,
        "news": news,
        "failed": failed,
    }


# --------------------------------------------------------------------------- #
# Render layer
# --------------------------------------------------------------------------- #
def render(payload: dict) -> str:
    data_json = json.dumps(payload)
    return TEMPLATE.replace("/*__DATA__*/null", data_json).replace(
        "__GENERATED__", html.escape(payload["generated"])
    )


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Pulse</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#f6f7f9; --panel:#ffffff; --panel-2:#eef0f4; --line:#dfe3ea;
  --ink:#161a20; --ink-2:#4b5563; --ink-3:#8a93a3;
  --accent:#c07d18; --accent-soft:#f4e3c6;
  --up:#1f8f5f; --up-bg:rgba(31,143,95,.14);
  --down:#cf4a43; --down-bg:rgba(207,74,67,.13);
  --flat:#8a93a3;
  --shadow:0 1px 2px rgba(16,20,30,.06),0 8px 24px rgba(16,20,30,.06);
  --mono:'IBM Plex Mono',ui-monospace,SFMono-Regular,Menlo,monospace;
  --sans:'IBM Plex Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --disp:'Archivo','IBM Plex Sans',system-ui,sans-serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0e1116; --panel:#161b22; --panel-2:#1c2230; --line:#262d3a;
  --ink:#e8ecf2; --ink-2:#a8b2c1; --ink-3:#6b7686;
  --accent:#e0a13c; --accent-soft:#3a2f18;
  --up:#3fb783; --up-bg:rgba(63,183,131,.16);
  --down:#e0655d; --down-bg:rgba(224,101,93,.16);
  --flat:#6b7686;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  --bg:#0e1116; --panel:#161b22; --panel-2:#1c2230; --line:#262d3a;
  --ink:#e8ecf2; --ink-2:#a8b2c1; --ink-3:#6b7686;
  --accent:#e0a13c; --accent-soft:#3a2f18;
  --up:#3fb783; --up-bg:rgba(63,183,131,.16);
  --down:#e0655d; --down-bg:rgba(224,101,93,.16);
  --flat:#6b7686;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto;padding:0 20px 64px}
a{color:inherit}

/* header */
header{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 88%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.head-in{max-width:1240px;margin:0 auto;padding:14px 20px;display:flex;
  align-items:center;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:11px;margin-right:auto}
.tick{font-family:var(--mono);font-weight:600;font-size:11px;letter-spacing:.5px;
  color:var(--accent);border:1px solid var(--accent);border-radius:5px;padding:3px 7px}
h1{font-family:var(--disp);font-weight:800;font-size:20px;letter-spacing:-.3px;margin:0}
.sub{color:var(--ink-3);font-size:12px;margin-top:1px}
.gen{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);text-align:right}
.gen b{color:var(--ink);font-weight:600}
.theme-btn{font-family:var(--sans);font-size:12px;color:var(--ink-2);background:var(--panel);
  border:1px solid var(--line);border-radius:7px;padding:6px 11px;cursor:pointer}
.theme-btn:hover{border-color:var(--accent);color:var(--ink)}

/* KPI strip */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:22px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:13px 15px;box-shadow:var(--shadow)}
.kpi .lab{font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--ink-3)}
.kpi .val{font-family:var(--mono);font-weight:600;font-size:22px;margin-top:6px;
  letter-spacing:-.5px;font-variant-numeric:tabular-nums}
.kpi .foot{font-family:var(--mono);font-size:12px;margin-top:3px;color:var(--ink-2)}
.kpi.hl{position:relative;overflow:hidden}
.kpi.hl::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--accent)}

/* controls */
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:6px 0 14px}
.controls input,.controls select{font-family:var(--sans);font-size:13px;color:var(--ink);
  background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 11px}
.controls input{min-width:210px}
.controls input:focus,.controls select:focus{outline:2px solid var(--accent);outline-offset:1px}
.seg{display:inline-flex;background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden}
.seg button{font-family:var(--sans);font-size:12.5px;color:var(--ink-2);background:transparent;
  border:0;padding:8px 13px;cursor:pointer;border-right:1px solid var(--line)}
.seg button:last-child{border-right:0}
.seg button[aria-pressed="true"]{background:var(--accent);color:#1a1205;font-weight:600}
.count{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--ink-3)}

/* table */
.tablecard{background:var(--panel);border:1px solid var(--line);border-radius:14px;
  box-shadow:var(--shadow);overflow:hidden}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;min-width:760px}
thead th{position:sticky;top:0;background:var(--panel-2);z-index:2;text-align:right;
  font-size:11px;letter-spacing:.4px;text-transform:uppercase;color:var(--ink-2);
  font-weight:600;padding:11px 14px;white-space:nowrap;cursor:pointer;user-select:none;
  border-bottom:1px solid var(--line)}
thead th:first-child,thead th:nth-child(2){text-align:left}
thead th .ar{color:var(--accent);font-family:var(--mono)}
tbody td{padding:10px 14px;border-bottom:1px solid var(--line);text-align:right;
  font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr{cursor:pointer}
tbody tr:hover{background:var(--panel-2)}
.tk{text-align:left;font-weight:600;font-size:14px}
.nm{text-align:left;font-family:var(--sans);color:var(--ink-2);font-size:12.5px;
  max-width:230px;overflow:hidden;text-overflow:ellipsis}
.rgn{display:inline-block;font-family:var(--mono);font-size:9.5px;letter-spacing:.4px;
  color:var(--ink-3);border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-left:7px}
.pill{display:inline-block;min-width:74px;padding:3px 8px;border-radius:6px;font-weight:500;font-size:12.5px}
.up{color:var(--up);background:var(--up-bg)}
.down{color:var(--down);background:var(--down-bg)}
.flat{color:var(--flat)}
.na{color:var(--ink-3)}
.newsdot{font-family:var(--sans);font-size:11px;color:var(--ink-3)}
.warn{color:var(--accent);font-size:11px;margin-left:4px}

/* section titles */
.sec{font-family:var(--disp);font-weight:700;font-size:15px;letter-spacing:-.2px;
  margin:34px 0 4px;display:flex;align-items:center;gap:9px}
.sec .rule{height:1px;background:var(--line);flex:1}
.sec-note{color:var(--ink-3);font-size:12px;margin:0 0 14px}

/* heatmap */
.heat{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px}
.cell{border-radius:9px;padding:9px 10px;border:1px solid var(--line);cursor:pointer;
  display:flex;flex-direction:column;gap:2px;min-height:56px;justify-content:space-between}
.cell .ct{font-family:var(--mono);font-weight:600;font-size:12.5px}
.cell .cv{font-family:var(--mono);font-size:12px;font-variant-numeric:tabular-nums}

/* movers */
.movers{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.mcol h3{font-family:var(--disp);font-size:13px;margin:0 0 10px;display:flex;align-items:center;gap:7px}
.mcard{background:var(--panel);border:1px solid var(--line);border-radius:11px;
  padding:12px 14px;margin-bottom:10px;box-shadow:var(--shadow)}
.mcard .top{display:flex;align-items:baseline;gap:9px;margin-bottom:3px}
.mcard .top .t{font-family:var(--mono);font-weight:600;font-size:14px}
.mcard .top .n{font-size:12px;color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mcard .top .m{margin-left:auto;font-family:var(--mono);font-weight:600}
.mcard .subrow{font-family:var(--mono);font-size:11.5px;color:var(--ink-3);margin-bottom:7px}
.mcard .hl{font-size:12.5px;line-height:1.45;color:var(--ink)}
.mcard .hl a{text-decoration:none;border-bottom:1px solid var(--line)}
.mcard .hl a:hover{border-color:var(--accent)}
.mcard .hlmeta{font-family:var(--mono);font-size:10.5px;color:var(--ink-3);margin-top:2px}
.nonews{font-size:12px;color:var(--ink-3)}

/* drawer */
.scrim{position:fixed;inset:0;background:rgba(6,9,14,.5);opacity:0;pointer-events:none;
  transition:opacity .18s;z-index:40}
.scrim.open{opacity:1;pointer-events:auto}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(460px,92vw);background:var(--panel);
  border-left:1px solid var(--line);transform:translateX(100%);transition:transform .22s ease;
  z-index:50;display:flex;flex-direction:column;box-shadow:-16px 0 40px rgba(0,0,0,.25)}
.drawer.open{transform:none}
.dhead{padding:18px 20px 14px;border-bottom:1px solid var(--line)}
.dhead .row1{display:flex;align-items:center;gap:10px}
.dhead .t{font-family:var(--mono);font-weight:600;font-size:20px}
.dhead .close{margin-left:auto;background:var(--panel-2);border:1px solid var(--line);
  color:var(--ink);border-radius:7px;width:30px;height:30px;cursor:pointer;font-size:15px}
.dhead .nm2{color:var(--ink-2);font-size:13px;margin-top:3px}
.dmetrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:16px 20px}
.dmetrics .m{background:var(--panel-2);border:1px solid var(--line);border-radius:9px;padding:9px 10px}
.dmetrics .m .l{font-size:10px;letter-spacing:.3px;text-transform:uppercase;color:var(--ink-3)}
.dmetrics .m .v{font-family:var(--mono);font-weight:600;font-size:15px;margin-top:3px}
.dnews{padding:2px 20px 24px;overflow-y:auto}
.dnews h4{font-family:var(--disp);font-size:12px;text-transform:uppercase;letter-spacing:.4px;
  color:var(--ink-3);margin:12px 0 6px}
.ni{padding:11px 0;border-bottom:1px solid var(--line)}
.ni a{font-weight:600;font-size:13.5px;line-height:1.4;text-decoration:none}
.ni a:hover{color:var(--accent)}
.ni .meta{font-family:var(--mono);font-size:10.5px;color:var(--ink-3);margin-top:4px}

.disc{color:var(--ink-3);font-size:11.5px;margin-top:30px;line-height:1.6;border-top:1px solid var(--line);padding-top:16px}
.failed{color:var(--ink-3);font-size:11.5px;margin-top:6px}

@media (max-width:820px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .movers{grid-template-columns:1fr}
  .gen{text-align:left}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<header>
  <div class="head-in">
    <div class="brand">
      <span class="tick">WATCHLIST</span>
      <div>
        <h1>Watchlist Pulse</h1>
        <div class="sub">Momentum, volume &amp; headlines across your holdings</div>
      </div>
    </div>
    <div class="gen">Snapshot<br><b>__GENERATED__</b></div>
    <button class="theme-btn" id="themeBtn" type="button">◑ Theme</button>
  </div>
</header>

<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="controls">
    <input id="search" type="search" placeholder="Filter ticker or name…" autocomplete="off">
    <div class="seg" id="regionSeg" role="group" aria-label="Region">
      <button data-region="all" aria-pressed="true">All</button>
      <button data-region="US">US</button>
      <button data-region="UK">UK</button>
      <button data-region="IN">India</button>
      <button data-region="OTC">Other</button>
    </div>
    <div class="seg" id="dirSeg" role="group" aria-label="Direction (1W)">
      <button data-dir="all" aria-pressed="true">All moves</button>
      <button data-dir="up">Gainers</button>
      <button data-dir="down">Losers</button>
    </div>
    <span class="count" id="count"></span>
  </div>

  <div class="tablecard">
    <div class="scroll">
      <table id="tbl">
        <thead><tr>
          <th data-k="ticker">Ticker</th>
          <th data-k="name">Company</th>
          <th data-k="price">Price</th>
          <th data-k="d3">3-Day</th>
          <th data-k="w1">1-Week</th>
          <th data-k="m1">1-Month</th>
          <th data-k="vol">Vol vs 20d</th>
          <th data-k="nnews">News</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <div class="sec">1-Week heatmap<span class="rule"></span></div>
  <p class="sec-note">Every tracked name shaded by its 5-session move. Click any cell for detail &amp; news.</p>
  <div class="heat" id="heat"></div>

  <div class="sec">Biggest movers &amp; why<span class="rule"></span></div>
  <p class="sec-note">The sharpest 1-week moves paired with their most recent headline — a quick read on what drove the price.</p>
  <div class="movers" id="movers"></div>

  <p class="failed" id="failed"></p>
  <p class="disc">Informational only — not investment advice. Prices &amp; headlines via Yahoo Finance public data and may be delayed; percentage windows use trailing trading sessions (3 / 5 / 21). Multi-currency: US &amp; ADRs in USD, London (.L) in GBp/pence, India (.NS/.BO) in INR. Very large one-month figures usually indicate a stock split, spin-off or thin history rather than a true move.</p>
</div>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" aria-hidden="true">
  <div class="dhead">
    <div class="row1">
      <span class="t" id="dTk"></span>
      <button class="close" id="dClose" type="button" aria-label="Close">✕</button>
    </div>
    <div class="nm2" id="dNm"></div>
  </div>
  <div class="dmetrics" id="dMetrics"></div>
  <div class="dnews" id="dNews"></div>
</aside>

<script>
const DATA = /*__DATA__*/null;
const rows = DATA.rows, news = DATA.news;

function region(t){
  if(t.endsWith(".NS")||t.endsWith(".BO")) return "IN";
  if(t.endsWith(".L")||t.endsWith(".IL")) return "UK";
  const otc=["SLOIF","XIACY","VWSYF","BYDDY","KRKNF"];
  if(otc.includes(t)) return "OTC";
  return "US";
}
rows.forEach(r=>{ r.region=region(r.ticker); r.nnews=(news[r.ticker]||[]).length; });

const CCY={USD:"$",GBp:"",INR:"₹",EUR:"€",GBP:"£"};
function fmtPrice(r){
  if(r.price==null) return "—";
  const v=r.price;
  const s=v>=1000?v.toLocaleString(undefined,{maximumFractionDigits:0})
    :v.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2});
  if(r.currency==="GBp") return s+"p";
  return (CCY[r.currency]||"")+s+(CCY[r.currency]?"":" "+r.currency);
}
function pctCell(v,{big=false}={}){
  if(v==null) return '<span class="na">—</span>';
  const cls=v>0?"up":v<0?"down":"flat";
  const arrow=v>0?"▲":v<0?"▼":"·";
  const flag=(big&&Math.abs(v)>500)?'<span class="warn" title="Likely split / thin history">⚠</span>':"";
  const num=(v>0?"+":"")+v.toFixed(2)+"%";
  return `<span class="pill ${cls}">${arrow} ${num}</span>${flag}`;
}

/* ---- KPIs ---- */
(function(){
  const withW=rows.filter(r=>r.w1!=null);
  const gain=withW.filter(r=>r.w1>0), lose=withW.filter(r=>r.w1<0);
  const best=withW.reduce((a,b)=>b.w1>(a?.w1??-1e9)?b:a,null);
  const worst=withW.reduce((a,b)=>b.w1<(a?.w1??1e9)?b:a,null);
  const withV=rows.filter(r=>r.vol!=null);
  const volSpike=withV.reduce((a,b)=>b.vol>(a?.vol??-1e9)?b:a,null);
  const k=[
    {lab:"Tracked",val:rows.length,foot:DATA.failed.length?DATA.failed.length+" unavailable":"all resolved"},
    {lab:"Gainers · 1W",val:gain.length,foot:"of "+withW.length+" with data",cls:"up"},
    {lab:"Losers · 1W",val:lose.length,foot:"of "+withW.length+" with data",cls:"down"},
    {lab:"Top mover · 1W",val:best?best.ticker:"—",foot:best?(best.w1>0?"+":"")+best.w1.toFixed(1)+"%":"",cls:best&&best.w1>0?"up":"down",hl:true},
    {lab:"Worst mover · 1W",val:worst?worst.ticker:"—",foot:worst?worst.w1.toFixed(1)+"%":"",cls:"down",hl:true},
    {lab:"Volume spike",val:volSpike?volSpike.ticker:"—",foot:volSpike?"+"+volSpike.vol.toFixed(0)+"% vs 20d":"",cls:"up",hl:true},
  ];
  document.getElementById("kpis").innerHTML=k.map(x=>`
    <div class="kpi ${x.hl?'hl':''}">
      <div class="lab">${x.lab}</div>
      <div class="val">${x.val}</div>
      <div class="foot ${x.cls||''}" style="color:${x.cls==='up'?'var(--up)':x.cls==='down'?'var(--down)':'var(--ink-2)'}">${x.foot}</div>
    </div>`).join("");
})();

/* ---- Table ---- */
let sortK="w1", sortDir=1, fRegion="all", fDir="all", fText="";
const tbody=document.getElementById("tbody");

function visible(){
  return rows.filter(r=>{
    if(fRegion!=="all" && r.region!==fRegion) return false;
    if(fDir==="up" && !(r.w1>0)) return false;
    if(fDir==="down" && !(r.w1<0)) return false;
    if(fText){
      const q=fText.toLowerCase();
      if(!(r.ticker.toLowerCase().includes(q)||(r.name||"").toLowerCase().includes(q))) return false;
    }
    return true;
  });
}
function sortRows(list){
  const num=["price","d3","w1","m1","vol","nnews"].includes(sortK);
  return list.slice().sort((a,b)=>{
    let x=a[sortK], y=b[sortK];
    if(num){ x=x==null?-Infinity:x; y=y==null?-Infinity:y; return (x-y)*sortDir; }
    x=(x||"").toString().toLowerCase(); y=(y||"").toString().toLowerCase();
    return x<y?-sortDir:x>y?sortDir:0;
  });
}
function draw(){
  const list=sortRows(visible());
  tbody.innerHTML=list.map(r=>`
    <tr data-t="${r.ticker}">
      <td class="tk">${r.ticker}<span class="rgn">${r.region}</span></td>
      <td class="nm" title="${(r.name||'').replace(/"/g,'&quot;')}">${r.name||''}</td>
      <td>${fmtPrice(r)}</td>
      <td>${pctCell(r.d3)}</td>
      <td>${pctCell(r.w1)}</td>
      <td>${pctCell(r.m1,{big:true})}</td>
      <td>${pctCell(r.vol)}</td>
      <td class="newsdot">${r.nnews||0}</td>
    </tr>`).join("");
  document.getElementById("count").textContent=list.length+" / "+rows.length+" shown";
  document.querySelectorAll("thead th").forEach(th=>{
    const base=th.dataset.k;
    th.innerHTML=th.textContent.replace(/[▲▼]\s*$/,"").trim()+(base===sortK?` <span class="ar">${sortDir>0?"▲":"▼"}</span>`:"");
  });
}
document.querySelectorAll("thead th").forEach(th=>{
  th.addEventListener("click",()=>{
    const k=th.dataset.k;
    if(k===sortK) sortDir*=-1; else {sortK=k; sortDir=(k==="ticker"||k==="name")?1:-1;}
    draw();
  });
});
document.getElementById("search").addEventListener("input",e=>{fText=e.target.value;draw();});
document.getElementById("regionSeg").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b)return;
  fRegion=b.dataset.region;
  [...e.currentTarget.children].forEach(x=>x.setAttribute("aria-pressed",x===b));
  draw();
});
document.getElementById("dirSeg").addEventListener("click",e=>{
  const b=e.target.closest("button"); if(!b)return;
  fDir=b.dataset.dir;
  [...e.currentTarget.children].forEach(x=>x.setAttribute("aria-pressed",x===b));
  draw();
});

/* ---- Heatmap ---- */
(function(){
  const list=rows.filter(r=>r.w1!=null).slice().sort((a,b)=>b.w1-a.w1);
  const shade=v=>{
    const t=Math.min(Math.abs(v)/12,1);
    if(v>0) return `background:rgba(31,143,95,${.12+.5*t});color:${t>.5?'#eafff4':'var(--ink)'}`;
    if(v<0) return `background:rgba(207,74,67,${.12+.5*t});color:${t>.5?'#fff0ef':'var(--ink)'}`;
    return "background:var(--panel-2)";
  };
  document.getElementById("heat").innerHTML=list.map(r=>`
    <div class="cell" data-t="${r.ticker}" style="${shade(r.w1)}">
      <span class="ct">${r.ticker}</span>
      <span class="cv">${(r.w1>0?"+":"")+r.w1.toFixed(1)}%</span>
    </div>`).join("");
})();

/* ---- Movers ---- */
(function(){
  const withW=rows.filter(r=>r.w1!=null);
  const gain=withW.slice().sort((a,b)=>b.w1-a.w1).slice(0,5);
  const lose=withW.slice().sort((a,b)=>a.w1-b.w1).slice(0,5);
  const card=r=>{
    const n=(news[r.ticker]||[])[0];
    const hl=n?`<div class="hl">${n.url?`<a href="${n.url}" target="_blank" rel="noopener">${esc(n.title)}</a>`:esc(n.title)}
        <div class="hlmeta">${esc(n.publisher||"")}${n.published?" · "+n.published:""}</div></div>`
      :`<div class="nonews">No recent headlines found.</div>`;
    const cls=r.w1>0?"up":"down";
    return `<div class="mcard">
      <div class="top"><span class="t">${r.ticker}</span><span class="n">${esc(r.name||"")}</span>
        <span class="m ${cls}">${(r.w1>0?"+":"")+r.w1.toFixed(1)}%</span></div>
      <div class="subrow">3D ${fmtsm(r.d3)} · 1M ${fmtsm(r.m1)} · Vol ${fmtsm(r.vol,0)}</div>
      ${hl}</div>`;
  };
  document.getElementById("movers").innerHTML=`
    <div class="mcol"><h3 style="color:var(--up)">▲ Top gainers · 1 week</h3>${gain.map(card).join("")}</div>
    <div class="mcol"><h3 style="color:var(--down)">▼ Top losers · 1 week</h3>${lose.map(card).join("")}</div>`;
})();
function fmtsm(v,d=1){return v==null?"—":(v>0?"+":"")+v.toFixed(d)+"%";}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

/* ---- Drawer ---- */
const drawer=document.getElementById("drawer"), scrim=document.getElementById("scrim");
function openDrawer(t){
  const r=rows.find(x=>x.ticker===t); if(!r)return;
  document.getElementById("dTk").textContent=r.ticker;
  document.getElementById("dNm").textContent=(r.name||"")+" · "+(r.exchange||r.region)+" · "+fmtPrice(r);
  const met=[["3-Day",r.d3],["1-Week",r.w1],["1-Month",r.m1],["Vol vs 20d",r.vol]];
  document.getElementById("dMetrics").innerHTML=met.map(([l,v])=>{
    const col=v==null?"var(--ink-3)":v>0?"var(--up)":v<0?"var(--down)":"var(--ink-2)";
    return `<div class="m"><div class="l">${l}</div><div class="v" style="color:${col}">${v==null?"—":(v>0?"+":"")+v.toFixed(2)+"%"}</div></div>`;
  }).join("");
  const items=news[r.ticker]||[];
  document.getElementById("dNews").innerHTML="<h4>Latest headlines, releases &amp; regulatory news</h4>"+
    (items.length?items.map(n=>`<div class="ni">
       ${n.url?`<a href="${n.url}" target="_blank" rel="noopener">${esc(n.title)}</a>`:`<span>${esc(n.title)}</span>`}
       <div class="meta">${esc(n.publisher||"")}${n.published?" · "+n.published:""}</div></div>`).join("")
     :'<div class="nonews">No recent headlines found for this ticker.</div>');
  drawer.classList.add("open");scrim.classList.add("open");drawer.setAttribute("aria-hidden","false");
}
function closeDrawer(){drawer.classList.remove("open");scrim.classList.remove("open");drawer.setAttribute("aria-hidden","true");}
document.getElementById("dClose").addEventListener("click",closeDrawer);
scrim.addEventListener("click",closeDrawer);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeDrawer();});
document.body.addEventListener("click",e=>{const el=e.target.closest("[data-t]");if(el)openDrawer(el.dataset.t);});

/* ---- theme toggle ---- */
document.getElementById("themeBtn").addEventListener("click",()=>{
  const cur=document.documentElement.getAttribute("data-theme");
  const dark=cur?cur==="dark":matchMedia("(prefers-color-scheme:dark)").matches;
  document.documentElement.setAttribute("data-theme",dark?"light":"dark");
});

/* ---- footer ---- */
document.getElementById("failed").textContent=DATA.failed.length?
  "Not resolved by the data source: "+DATA.failed.join(", "):"";

draw();
</script>
</body>
</html>"""


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "dashboard.html"
    payload = collect()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render(payload))
    print(f"Wrote {out_path} ({len(payload['rows'])} tickers)", file=sys.stderr)


if __name__ == "__main__":
    main()
