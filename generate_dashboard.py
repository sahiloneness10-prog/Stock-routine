#!/usr/bin/env python3
"""
Static watchlist dashboard generator
=====================================
Fetches 3-day / 1-week / 1-month price moves, volume shifts and recent
headlines for a stock watchlist straight from Yahoo Finance's public JSON
endpoints, then writes a single self-contained, theme-aware HTML dashboard
(``watchlist_dashboard.html``) you can open in any browser.

Why not ``yfinance``?  ``yfinance`` bundles ``curl_cffi`` which ignores the
standard ``HTTPS_PROXY``/CA-bundle environment, so it fails behind an egress
proxy.  This script talks to the same endpoints with the stdlib, honouring the
proxy, so it runs anywhere including CI / scheduled jobs.

Run with:
    python3 generate_dashboard.py
"""

from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --------------------------------------------------------------------------- #
# Watchlist
# --------------------------------------------------------------------------- #
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

# Trading-day look-backs used for each window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
OUT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist_dashboard.html")

# --------------------------------------------------------------------------- #
# HTTP layer (proxy + CA aware, stdlib only)
# --------------------------------------------------------------------------- #
def _build_opener() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    ca = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
    ctx = ssl.create_default_context(cafile=ca) if os.path.exists(ca) else ssl.create_default_context()
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if proxy:
        handlers.insert(0, urllib.request.ProxyHandler({"https": proxy, "http": proxy}))
    return urllib.request.build_opener(*handlers)


_OPENER = _build_opener()


def _get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    return _OPENER.open(req, timeout=timeout).read()


# --------------------------------------------------------------------------- #
# Data fetch
# --------------------------------------------------------------------------- #
def _pct(closes: list[float], periods: int) -> float | None:
    c = [x for x in closes if x is not None]
    if len(c) <= periods or c[-1 - periods] in (0, None):
        return None
    return (c[-1] - c[-1 - periods]) / c[-1 - periods] * 100


def fetch_chart(sym: str) -> dict | None:
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?range=3mo&interval=1d"
        for attempt in range(3):
            try:
                data = json.loads(_get(url))
                res = (data.get("chart") or {}).get("result")
                if not res:
                    return None
                r = res[0]
                q = r["indicators"]["quote"][0]
                return {"meta": r.get("meta", {}), "closes": q.get("close", []), "vols": q.get("volume", [])}
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return None
            except Exception:
                time.sleep(0.8)
    return None


def fetch_news(sym: str, count: int = 4) -> list[dict]:
    url = (
        f"https://query1.finance.yahoo.com/v1/finance/search?q={urllib.parse.quote(sym)}"
        f"&newsCount={count}&quotesCount=0&enableFuzzyQuery=false"
    )
    try:
        d = json.loads(_get(url))
    except Exception:
        return []
    out = []
    for n in d.get("news", []):
        out.append({
            "title": n.get("title", ""),
            "publisher": n.get("publisher", ""),
            "url": n.get("link", ""),
            "time": n.get("providerPublishTime"),
        })
    return out


def collect(tickers: list[str]) -> dict:
    rows, failed, news = [], [], {}
    for i, t in enumerate(tickers):
        ch = fetch_chart(t)
        if not ch:
            failed.append(t)
            print(f"  fail  {t}", file=sys.stderr)
            continue
        valid = [c for c in ch["closes"] if c is not None]
        vols = [v for v in ch["vols"] if v is not None]
        if not valid:
            failed.append(t)
            continue
        meta = ch["meta"]
        volchg = None
        if len(vols) >= 6:
            base = vols[-21:-1] if len(vols) > 21 else vols[:-1]
            avg = sum(base) / len(base) if base else 0
            if avg:
                volchg = (vols[-1] - avg) / avg * 100
        rows.append({
            "ticker": t,
            "name": meta.get("shortName") or meta.get("longName") or t,
            "currency": meta.get("currency", ""),
            "price": meta.get("regularMarketPrice") or valid[-1],
            "d3": _pct(valid, WINDOWS["d3"]),
            "w1": _pct(valid, WINDOWS["w1"]),
            "m1": _pct(valid, WINDOWS["m1"]),
            "volchg": volchg,
        })
        news[t] = fetch_news(t)
        time.sleep(0.15)
        print(f"  ok    {t} ({i + 1}/{len(tickers)})", file=sys.stderr)
    return {"rows": rows, "failed": failed, "news": news, "asof": int(time.time())}


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def _num(v):
    return v if isinstance(v, (int, float)) else None


def _fmt_pct(v, dec=1):
    return f"{v:+.{dec}f}%" if _num(v) is not None else "—"


def _fmt_price(v):
    if _num(v) is None:
        return "—"
    return f"{v:,.0f}" if v >= 1000 else f"{v:,.2f}"


def _cell(v, cap=15.0):
    """Return (inline-style, css-class) for a diverging % cell."""
    if _num(v) is None:
        return "", "muted"
    alpha = 0.10 + 0.42 * min(abs(v) / cap, 1.0)
    if v > 0:
        return f"background:rgba(12,163,12,{alpha:.3f})", "up"
    if v < 0:
        return f"background:rgba(208,59,59,{alpha:.3f})", "down"
    return "", "flat"


def _esc(s):
    return _html.escape(s or "")


def _news_date(ts):
    try:
        return dt.datetime.utcfromtimestamp(int(ts)).strftime("%b %d")
    except Exception:
        return ""


CSS = """<style>
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--border:rgba(11,11,11,0.10);--up:#0ca30c;--down:#d03b3b;--upt:#006300;
--downt:#b32626;--volc:#256abf;--shadow:0 1px 2px rgba(11,11,11,.04),0 8px 24px rgba(11,11,11,.06);}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){--page:#0d0d0d;
--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;
--border:rgba(255,255,255,0.10);--upt:#3ecb3e;--downt:#ef6a6a;--volc:#5598e7;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 28px rgba(0,0,0,.45);}}
:root[data-theme="dark"]{--page:#0d0d0d;--surface:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
--grid:#2c2c2a;--border:rgba(255,255,255,0.10);--upt:#3ecb3e;--downt:#ef6a6a;--volc:#5598e7;
--shadow:0 1px 2px rgba(0,0,0,.3),0 8px 28px rgba(0,0,0,.45);}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased;line-height:1.4}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 60px}
.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.2px;font-weight:700}
.sub{margin:0;color:var(--ink2);font-size:13.5px}
.hero-r{display:flex;gap:8px}
.pill{font-size:13px;font-weight:600;padding:6px 12px;border-radius:999px;border:1px solid var(--border)}
.up-pill{color:var(--upt);background:rgba(12,163,12,.10)}
.down-pill{color:var(--downt);background:rgba(208,59,59,.10)}
.movers{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
.mover{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 16px 14px;box-shadow:var(--shadow);position:relative;overflow:hidden}
.mover::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px}
.mover.up::before{background:var(--up)}.mover.down::before{background:var(--down)}
.mover.vol::before{background:var(--volc)}.mover.neutral::before{background:var(--muted)}
.mv-label{font-size:11.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:600}
.mv-sym{font-size:26px;font-weight:700;margin:6px 0 2px;letter-spacing:-.3px}
.mv-sym .of{font-size:15px;color:var(--muted);font-weight:500}
.mv-pct{font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.mv-pct.up{color:var(--upt)}.mv-pct.down{color:var(--downt)}.mv-pct.vol{color:var(--volc)}.mv-pct.neutral{color:var(--ink2)}
.mv-name{font-size:12px;color:var(--ink2);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:6px 4px 8px;margin-bottom:24px}
.panel-head{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap;padding:14px 18px 8px}
.panel-head h2{font-size:16px;margin:0;font-weight:700}
.hint{font-size:12px;color:var(--muted)}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px}
thead th{position:sticky;top:0;background:var(--surface);text-align:right;padding:9px 14px;font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:600;border-bottom:1px solid var(--grid);white-space:nowrap;user-select:none}
thead th.l{text-align:left}
thead th.active{color:var(--ink)}
thead th.sortable:hover{color:var(--ink)}
tbody td{padding:8px 14px;border-bottom:1px solid var(--grid);text-align:right;font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:rgba(120,120,120,.06)}
td.tk{text-align:left}
td.tk .sym{font-weight:700;font-size:13.5px;display:block}
td.tk .nm{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:230px;display:block}
td.price{font-weight:600}
.cur{font-size:10px;color:var(--muted);margin-left:4px}
td.num.up{color:var(--upt);font-weight:600}td.num.down{color:var(--downt);font-weight:600}
td.num.muted{color:var(--muted)}
.failnote{font-size:12px;color:var(--muted);padding:10px 18px 6px}
.news-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px;padding:6px 14px 14px}
.news-card{border:1px solid var(--border);border-radius:12px;padding:13px 14px;background:var(--page)}
.nc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:9px;padding-bottom:8px;border-bottom:1px solid var(--grid)}
.nc-sym{font-weight:700;font-size:15px}
.nc-pct{font-size:13px;font-weight:700;font-variant-numeric:tabular-nums}
.nc-pct.up{color:var(--upt)}.nc-pct.down{color:var(--downt)}
.nc-w{font-size:9.5px;color:var(--muted);font-weight:600;letter-spacing:.5px}
.nc-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.nc-list li{display:flex;flex-direction:column;gap:2px}
.ni-title{font-size:12.5px;line-height:1.35}
.ni-title a{color:var(--ink);text-decoration:none;border-bottom:1px solid transparent}
.ni-title a:hover{border-bottom-color:var(--ink2)}
.ni-meta{font-size:10.5px;color:var(--muted)}
.empty{color:var(--muted);font-size:13px;padding:0 4px}
.foot{font-size:11.5px;color:var(--muted);text-align:center;margin-top:8px;line-height:1.5}
@media (max-width:820px){.movers{grid-template-columns:repeat(2,1fr)}}
@media (max-width:520px){.movers{grid-template-columns:1fr}h1{font-size:22px}}
</style>"""

SORT_JS = """<script>
(function(){
  var tb=document.querySelector('#grid tbody');if(!tb)return;
  var rows=Array.prototype.slice.call(tb.querySelectorAll('tr'));
  var ths=document.querySelectorAll('#grid th');var state={col:3,dir:-1};
  function val(tr,c,t){var td=tr.children[c];
    if(t==='n'){var d=td.getAttribute('data-v');return d!==null?parseFloat(d):-1e12;}
    return td.textContent.trim().toLowerCase();}
  function sort(c,t,dir){rows.sort(function(a,b){var x=val(a,c,t),y=val(b,c,t);
    return x<y?-dir:x>y?dir:0;});rows.forEach(function(r){tb.appendChild(r);});}
  ths.forEach(function(th){var c=th.getAttribute('data-c');if(c===null)return;th.style.cursor='pointer';
    th.addEventListener('click',function(){var col=+c,t=th.getAttribute('data-t');
      var dir=(state.col===col)?-state.dir:(t==='n'?-1:1);state={col:col,dir:dir};
      ths.forEach(function(o){o.classList.remove('active');o.textContent=o.textContent.replace(/[ \\u25be\\u25b4]+$/,'');});
      th.classList.add('active');th.textContent=th.textContent+(dir<0?' \\u25be':' \\u25b4');
      sort(col,t,dir);});});
})();
</script>"""


def render(data: dict) -> str:
    rows, news = data["rows"], data.get("news", {})
    asof = dt.datetime.utcfromtimestamp(data["asof"]).strftime("%b %d, %Y · %H:%M UTC")

    w1 = [r for r in rows if _num(r["w1"]) is not None]
    gainers = sorted((r for r in w1 if r["w1"] > 0), key=lambda r: r["w1"], reverse=True)
    losers = sorted((r for r in w1 if r["w1"] < 0), key=lambda r: r["w1"])
    best = gainers[0] if gainers else None
    worst = losers[0] if losers else None
    volspike = max((r for r in rows if _num(r["volchg"]) is not None),
                   key=lambda r: r["volchg"], default=None)

    # table body sorted by 1W desc
    rows_sorted = sorted(rows, key=lambda r: r["w1"] if _num(r["w1"]) is not None else -1e9, reverse=True)
    body = []
    for r in rows_sorted:
        cells = []
        for k, dec in (("d3", 1), ("w1", 1), ("m1", 1), ("volchg", 0)):
            st, cls = _cell(r[k])
            dv = _num(r[k]) if _num(r[k]) is not None else -1e12
            cells.append(f'<td class="num {cls}" style="{st}" data-v="{dv}">{_fmt_pct(r[k], dec)}</td>')
        body.append(
            '<tr>'
            f'<td class="tk"><span class="sym">{_esc(r["ticker"])}</span>'
            f'<span class="nm">{_esc((r.get("name") or "")[:34])}</span></td>'
            f'<td class="num price">{_fmt_price(r["price"])}'
            f'<span class="cur">{_esc(r.get("currency", ""))}</span></td>'
            + "".join(cells) + '</tr>'
        )

    def card(r, label):
        if not r:
            return ""
        cls = "up" if (_num(r["w1"]) or 0) >= 0 else "down"
        return (f'<div class="mover {cls}"><div class="mv-label">{label}</div>'
                f'<div class="mv-sym">{_esc(r["ticker"])}</div>'
                f'<div class="mv-pct {cls}">{_fmt_pct(r["w1"])}</div>'
                f'<div class="mv-name">{_esc((r.get("name") or "")[:28])}</div></div>')

    # news for notable movers
    seen, notable = set(), []
    for r in gainers[:5] + losers[:5]:
        if r["ticker"] not in seen:
            seen.add(r["ticker"]); notable.append(r)
    blocks = []
    for r in notable:
        items = news.get(r["ticker"], [])[:3]
        if not items:
            continue
        lis = []
        for it in items:
            title = _esc(it.get("title"))
            meta = " · ".join(x for x in [_esc(it.get("publisher")), _news_date(it.get("time"))] if x)
            url = it.get("url", "")
            th = f'<a href="{_esc(url)}" target="_blank" rel="noopener">{title}</a>' if url else title
            lis.append(f'<li><span class="ni-title">{th}</span><span class="ni-meta">{meta}</span></li>')
        cls = "up" if (_num(r["w1"]) or 0) >= 0 else "down"
        blocks.append(
            f'<div class="news-card"><div class="nc-head"><span class="nc-sym">{_esc(r["ticker"])}</span>'
            f'<span class="nc-pct {cls}">{_fmt_pct(r["w1"])} <span class="nc-w">1W</span></span></div>'
            f'<ul class="nc-list">{"".join(lis)}</ul></div>'
        )
    news_html = "\n".join(blocks) or '<p class="empty">No recent headlines retrieved for the notable movers.</p>'

    failed = data.get("failed", [])
    failnote = ("<div class='failnote'>⚠ No data resolved for: " + _esc(", ".join(failed)) + "</div>") if failed else ""

    vol_card = (
        '<div class="mover vol"><div class="mv-label">Biggest volume spike</div>'
        f'<div class="mv-sym">{_esc(volspike["ticker"]) if volspike else "—"}</div>'
        f'<div class="mv-pct vol">{_fmt_pct(volspike["volchg"], 0) if volspike else "—"}</div>'
        '<div class="mv-name">vs 20-day average</div></div>'
    )
    cover_card = (
        '<div class="mover neutral"><div class="mv-label">Coverage</div>'
        f'<div class="mv-sym">{len(rows)}<span class="of">/{len(rows) + len(failed)}</span></div>'
        '<div class="mv-pct neutral">resolved</div>'
        f'<div class="mv-name">{len(gainers)} gainers · {len(losers)} decliners</div></div>'
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Watchlist Movement Dashboard</title>
{CSS}
</head><body>
<div class="wrap">
<header class="hero">
  <div class="hero-l"><h1>Watchlist Movement Dashboard</h1>
  <p class="sub">Momentum, volume &amp; headlines across {len(rows)} tickers · data as of {asof}</p></div>
  <div class="hero-r"><div class="pill up-pill">▲ {len(gainers)} up</div>
  <div class="pill down-pill">▼ {len(losers)} down</div></div>
</header>
<section class="movers">
  {card(best, "Top gainer · 1W")}
  {card(worst, "Top decliner · 1W")}
  {vol_card}
  {cover_card}
</section>
<section class="panel">
  <div class="panel-head"><h2>Price &amp; volume changes</h2>
  <span class="hint">click a column header to sort · green ▲ / red ▼ scaled by magnitude</span></div>
  <div class="tablewrap"><table id="grid"><thead><tr>
    <th class="l" data-c="0" data-t="s">Ticker</th>
    <th class="r" data-c="1" data-t="n">Price</th>
    <th class="r sortable" data-c="2" data-t="n">3-Day</th>
    <th class="r sortable active" data-c="3" data-t="n">1-Week ▾</th>
    <th class="r sortable" data-c="4" data-t="n">1-Month</th>
    <th class="r sortable" data-c="5" data-t="n">Volume Δ</th>
  </tr></thead><tbody>
{chr(10).join(body)}
  </tbody></table></div>
  {failnote}
</section>
<section class="panel">
  <div class="panel-head"><h2>Headlines behind the notable movers</h2>
  <span class="hint">news, releases &amp; regulatory items for the largest weekly moves</span></div>
  <div class="news-grid">{news_html}</div>
</section>
<footer class="foot">Informational only — not investment advice. Prices via Yahoo Finance and may be delayed;
some foreign listings can occasionally fail to resolve. Generated automatically by generate_dashboard.py.</footer>
</div>
{SORT_JS}
</body></html>"""


def main() -> int:
    print(f"Fetching {len(TICKERS)} tickers…", file=sys.stderr)
    data = collect(TICKERS)
    if not data["rows"]:
        print("No data fetched — aborting.", file=sys.stderr)
        return 1
    with open(OUT_HTML, "w") as f:
        f.write(render(data))
    print(f"Wrote {OUT_HTML}  ({len(data['rows'])} tickers, {len(data['failed'])} failed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
