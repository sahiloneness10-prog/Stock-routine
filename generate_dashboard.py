"""
generate_dashboard.py
=====================
Fetches Yahoo Finance price + news data for the watchlist and renders a single,
self-contained, theme-aware ``dashboard.html`` — no server, no third-party
dependencies (standard library only). Ideal for a scheduled job that publishes a
static snapshot.

Usage:
    python generate_dashboard.py            # writes dashboard.html
    python generate_dashboard.py out.html   # custom output path

Metrics per ticker:
    * 3-day / 1-week / 1-month price % change (trading-day look-backs)
    * Volume change vs the trailing 20-day average
    * 30-day price sparkline
    * Recent news / releases / regulatory headlines for the biggest movers
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import sys
import time
import urllib.parse
import urllib.request

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

# Trading-day look-backs for each window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_CHART = "https://query2.finance.yahoo.com/v8/finance/chart/{}?range=3mo&interval=1d"
_NEWS = ("https://query2.finance.yahoo.com/v1/finance/search"
         "?q={}&newsCount=4&quotesCount=0&enableFuzzyQuery=false")


# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
def _get(url: str, tries: int = 4) -> dict:
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as exc:  # noqa: BLE001 - network is best-effort
            if i == tries - 1:
                return {"__error__": str(exc)}
            time.sleep(1.5 * (i + 1))
    return {"__error__": "unknown"}


def _pct(cur, prev):
    if prev in (None, 0) or cur is None:
        return None
    try:
        if math.isnan(prev) or math.isnan(cur):
            return None
    except TypeError:
        return None
    return (cur - prev) / prev * 100.0


def _nth_last_valid(vals, n):
    clean = [v for v in vals if v is not None]
    if len(clean) <= n:
        return None
    return clean[-1 - n]


def fetch() -> dict:
    """Return {"results": [...per ticker...], "news": {ticker: [...]}}."""
    results = []
    for idx, t in enumerate(TICKERS):
        d = _get(_CHART.format(urllib.parse.quote(t)))
        rec = {"ticker": t}
        try:
            res = d["chart"]["result"][0]
            meta = res["meta"]
            quote = res["indicators"]["quote"][0]
            adj_block = res["indicators"].get("adjclose")
            adj = adj_block[0].get("adjclose") if adj_block else None
            series = adj if adj else quote.get("close", [])
            vols = quote.get("volume", [])
            clean = [v for v in series if v is not None]
            last = clean[-1] if clean else meta.get("regularMarketPrice")
            rec.update(
                name=meta.get("longName") or meta.get("shortName") or t,
                currency=meta.get("currency"),
                exchange=meta.get("fullExchangeName"),
                price=meta.get("regularMarketPrice", last),
                spark=[round(v, 4) for v in clean[-30:]],
            )
            for key, periods in WINDOWS.items():
                rec[key] = _pct(last, _nth_last_valid(series, periods))
            cv = [v for v in vols if v]
            if len(cv) >= 6:
                base = cv[-21:-1] if len(cv) > 21 else cv[:-1]
                avg = sum(base) / len(base) if base else None
                rec["vol_chg"] = _pct(cv[-1], avg)
            else:
                rec["vol_chg"] = None
        except Exception as exc:  # noqa: BLE001
            rec["error"] = str(exc)
        results.append(rec)
        time.sleep(0.4)

    # News for the biggest absolute movers only (keeps request volume sane).
    def mover_key(r):
        return max((abs(r.get(k) or 0) for k in WINDOWS), default=0)

    ranked = sorted((r for r in results if "error" not in r),
                    key=mover_key, reverse=True)
    news = {}
    for r in ranked[:24]:
        t = r["ticker"]
        d = _get(_NEWS.format(urllib.parse.quote(t)), tries=3)
        news[t] = [
            {
                "title": n.get("title"),
                "publisher": n.get("publisher"),
                "link": n.get("link"),
                "time": n.get("providerPublishTime"),
            }
            for n in (d.get("news") or [])[:4]
        ]
        time.sleep(0.35)
    return {"results": results, "news": news}


# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
def _num(x):
    return x if isinstance(x, (int, float)) else None


def _fmt_pct(x):
    x = _num(x)
    return f"{x:+.1f}%" if x is not None else "—"


def _arrow(x):
    x = _num(x)
    if x is None:
        return ""
    return "▲" if x > 0 else ("▼" if x < 0 else "•")


def _cls(x):
    x = _num(x)
    if x is None:
        return "na"
    return "up" if x > 0 else ("down" if x < 0 else "flat")


def _tint(x, cap):
    x = _num(x)
    if x is None:
        return 0.0
    return min(abs(x) / cap, 1.0) * 0.85


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _sparkline(vals, up):
    if not vals or len(vals) < 2:
        return ""
    w, h, pad = 120, 30, 3
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + (w - 2 * pad) * i / (n - 1)
        y = pad + (h - 2 * pad) * (1 - (v - lo) / rng)
        pts.append(f"{x:.1f},{y:.1f}")
    color = "var(--good)" if up else "var(--bad)"
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'aria-hidden="true"><polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="1.6" stroke-linejoin="round" '
            f'stroke-linecap="round"/></svg>')


def _ts_fmt(t):
    if not t:
        return ""
    try:
        return dt.datetime.utcfromtimestamp(int(t)).strftime("%b %d, %Y")
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #
def render(data: dict, as_of: str | None = None) -> str:
    as_of = as_of or dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    results = data["results"]
    news = data["news"]
    rows = [r for r in results if "error" not in r and r.get("price") is not None]
    failed = [r["ticker"] for r in results if r not in rows]

    def w1(r):
        return _num(r.get("w1"))

    have = [r for r in rows if w1(r) is not None]
    gainers = [r for r in have if w1(r) > 0]
    losers = [r for r in have if w1(r) < 0]
    best = max(have, key=w1) if have else None
    worst = min(have, key=w1) if have else None
    vol_spikes = sorted((r for r in rows if _num(r.get("vol_chg")) is not None),
                        key=lambda r: r["vol_chg"], reverse=True)

    sorted_rows = sorted(rows, key=lambda r: (w1(r) is not None, w1(r) or 0),
                         reverse=True)

    trs = []
    for r in sorted_rows:
        spark = _sparkline(r.get("spark", []), (w1(r) or 0) >= 0)
        cells = []
        for key in ("d3", "w1", "m1", "vol_chg"):
            v = _num(r.get(key))
            c = _cls(v)
            bg = ""
            if v is not None and c != "flat":
                rgb = "12,163,12" if c == "up" else "208,59,59"
                a = _tint(v, 20.0 if key == "vol_chg" else 15.0)
                bg = f'style="background:rgba({rgb},{a:.2f})"'
            cells.append(f'<td class="pct {c}" {bg}>{_arrow(v)} {_fmt_pct(v)}</td>')
        price = r.get("price")
        price_s = f"{price:,.2f}" if isinstance(price, (int, float)) else "—"
        trs.append(
            f'<tr><td class="tk"><span class="sym">{_esc(r["ticker"])}</span>'
            f'<span class="nm">{_esc(r.get("name"))}</span></td>'
            f'<td class="price">{price_s}<span class="cur">{_esc(r.get("currency"))}</span></td>'
            + "".join(cells)
            + f'<td class="sparkcell">{spark}</td></tr>'
        )

    def chip(r, metric):
        v = _num(r.get(metric))
        return (f'<div class="chip {_cls(v)}"><span class="csym">{_esc(r["ticker"])}</span>'
                f'<span class="cval">{_arrow(v)} {_fmt_pct(v)}</span></div>')

    top_g = "".join(chip(r, "w1") for r in sorted(have, key=w1, reverse=True)[:6])
    top_l = "".join(chip(r, "w1") for r in sorted(have, key=w1)[:6])
    top_v = "".join(chip(r, "vol_chg") for r in vol_spikes[:6])
    best_s = f'{best["ticker"]} {_fmt_pct(w1(best))}' if best else "—"
    worst_s = f'{worst["ticker"]} {_fmt_pct(w1(worst))}' if worst else "—"

    by_ticker = {r["ticker"]: r for r in rows}
    news_order = sorted(news.keys(),
                        key=lambda t: abs(w1(by_ticker.get(t, {})) or 0), reverse=True)
    news_cards = []
    for t in news_order:
        items = [n for n in news[t] if n.get("title")]
        if not items:
            continue
        r = by_ticker.get(t, {})
        bcls = _cls(w1(r))
        lis = []
        for n in items[:3]:
            meta = " · ".join(x for x in [_esc(n.get("publisher")), _ts_fmt(n.get("time"))] if x)
            title, link = _esc(n.get("title")), _esc(n.get("link"))
            if link:
                lis.append(f'<li><a href="{link}" target="_blank" rel="noopener">{title}</a>'
                           f'<span class="nmeta">{meta}</span></li>')
            else:
                lis.append(f'<li>{title}<span class="nmeta">{meta}</span></li>')
        news_cards.append(
            f'<div class="ncard"><div class="nhead"><span class="nsym">{_esc(t)}</span>'
            f'<span class="nbadge {bcls}">{_arrow(w1(r))} {_fmt_pct(w1(r))} <em>1W</em></span></div>'
            f'<ul>{"".join(lis)}</ul></div>'
        )

    failed_note = (f'<p class="failnote">No data resolved for: {_esc(", ".join(failed))}</p>'
                   if failed else "")

    return _TEMPLATE.format(
        as_of=_esc(as_of), n_rows=len(rows), n_total=len(results),
        n_gain=len(gainers), n_loss=len(losers), best=_esc(best_s), worst=_esc(worst_s),
        top_g=top_g, top_l=top_l, top_v=top_v, rows="".join(trs),
        news="".join(news_cards) or '<p class="failnote">No recent news retrieved.</p>',
        failed_note=failed_note,
    )


_TEMPLATE = """<title>Watchlist Pulse</title>
<style>
:root {{
  color-scheme: light;
  --plane:#f4f4f1; --surface:#fcfcfb; --card:#ffffff;
  --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e6e5df; --line:#c3c2b7;
  --good:#0ca30c; --bad:#d03b3b;
  --good-bg:rgba(12,163,12,.10); --bad-bg:rgba(208,59,59,.10);
  --accent:#2a78d6;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.06);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    color-scheme: dark;
    --plane:#0d0d0d; --surface:#161615; --card:#1c1c1a;
    --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88;
    --grid:#2a2a28; --line:#3a3a37;
    --good:#3cc43c; --bad:#e46b6b;
    --good-bg:rgba(60,196,60,.12); --bad-bg:rgba(228,107,107,.12);
    --accent:#3987e5;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 22px rgba(0,0,0,.35);
  }}
}}
:root[data-theme="dark"] {{
  color-scheme: dark;
  --plane:#0d0d0d; --surface:#161615; --card:#1c1c1a;
  --ink:#f4f4f2; --ink2:#c3c2b7; --muted:#8f8e88;
  --grid:#2a2a28; --line:#3a3a37;
  --good:#3cc43c; --bad:#e46b6b;
  --good-bg:rgba(60,196,60,.12); --bad-bg:rgba(228,107,107,.12);
  --accent:#3987e5;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 22px rgba(0,0,0,.35);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--plane); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-feature-settings:"tnum" 1; line-height:1.45;
}}
.wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 64px; }}
header.top {{ margin-bottom:22px; }}
.eyebrow {{ font-size:12px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--muted); font-weight:600; }}
h1 {{ font-size:clamp(26px,4vw,38px); margin:.15em 0 .1em; letter-spacing:-.02em; }}
.sub {{ color:var(--ink2); font-size:15px; margin:0; }}
.sub b {{ color:var(--ink); }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:12px; margin:22px 0 8px; }}
.kpi {{ background:var(--card); border:1px solid var(--grid); border-radius:14px;
  padding:14px 16px; box-shadow:var(--shadow); }}
.kpi .lab {{ font-size:12px; color:var(--muted); text-transform:uppercase;
  letter-spacing:.06em; font-weight:600; }}
.kpi .val {{ font-size:24px; font-weight:700; margin-top:4px; letter-spacing:-.01em; }}
.kpi .val small {{ font-size:14px; font-weight:600; color:var(--ink2); }}
.up {{ color:var(--good); }} .down {{ color:var(--bad); }}
.flat, .na {{ color:var(--muted); }}
section {{ margin-top:34px; }}
h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.08em;
  color:var(--ink2); margin:0 0 14px; font-weight:700; }}
.chiprow {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:8px; }}
.chipgroup {{ margin-bottom:18px; }}
.chipgroup .glab {{ font-size:12px; color:var(--muted); font-weight:600;
  margin-bottom:8px; letter-spacing:.04em; }}
.chip {{ display:flex; flex-direction:column; gap:2px; padding:8px 13px;
  border-radius:11px; background:var(--card); border:1px solid var(--grid);
  min-width:96px; box-shadow:var(--shadow); }}
.chip .csym {{ font-weight:700; font-size:13px; color:var(--ink); }}
.chip .cval {{ font-size:13px; font-weight:600; }}
.chip.up {{ border-color:color-mix(in srgb,var(--good) 40%,var(--grid)); background:var(--good-bg); }}
.chip.down {{ border-color:color-mix(in srgb,var(--bad) 40%,var(--grid)); background:var(--bad-bg); }}
.tablecard {{ background:var(--card); border:1px solid var(--grid);
  border-radius:16px; box-shadow:var(--shadow); overflow:hidden; }}
.scroll {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; min-width:720px; }}
thead th {{ position:sticky; top:0; background:var(--surface); text-align:right;
  padding:13px 14px; font-size:11px; text-transform:uppercase; letter-spacing:.05em;
  color:var(--muted); font-weight:700; border-bottom:1px solid var(--line);
  white-space:nowrap; }}
thead th:first-child, td.tk {{ text-align:left; }}
tbody td {{ padding:11px 14px; text-align:right; border-bottom:1px solid var(--grid);
  white-space:nowrap; }}
tbody tr:last-child td {{ border-bottom:none; }}
tbody tr:hover td {{ background:color-mix(in srgb,var(--accent) 6%,transparent); }}
td.tk {{ display:flex; flex-direction:column; gap:1px; }}
td.tk .sym {{ font-weight:700; font-size:14px; }}
td.tk .nm {{ font-size:11.5px; color:var(--muted); max-width:200px;
  overflow:hidden; text-overflow:ellipsis; }}
td.price {{ font-weight:600; }}
td.price .cur {{ font-size:10px; color:var(--muted); margin-left:4px; }}
td.pct {{ font-weight:600; font-variant-numeric:tabular-nums; }}
td.pct.na {{ font-weight:400; }}
.sparkcell {{ width:130px; }}
svg.spark {{ width:110px; height:28px; display:block; margin-left:auto; }}
.newsgrid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
  gap:14px; }}
.ncard {{ background:var(--card); border:1px solid var(--grid); border-radius:14px;
  padding:15px 16px; box-shadow:var(--shadow); }}
.nhead {{ display:flex; justify-content:space-between; align-items:center;
  margin-bottom:10px; gap:10px; }}
.nsym {{ font-weight:700; font-size:15px; }}
.nbadge {{ font-size:12px; font-weight:700; padding:3px 9px; border-radius:20px; }}
.nbadge em {{ font-style:normal; opacity:.6; font-weight:600; font-size:10px; }}
.nbadge.up {{ background:var(--good-bg); color:var(--good); }}
.nbadge.down {{ background:var(--bad-bg); color:var(--bad); }}
.nbadge.na {{ background:var(--grid); color:var(--muted); }}
.ncard ul {{ list-style:none; margin:0; padding:0; }}
.ncard li {{ padding:8px 0; border-top:1px solid var(--grid); font-size:13.5px;
  line-height:1.4; }}
.ncard li:first-child {{ border-top:none; }}
.ncard a {{ color:var(--ink); text-decoration:none; font-weight:500; }}
.ncard a:hover {{ color:var(--accent); text-decoration:underline; }}
.nmeta {{ display:block; font-size:11px; color:var(--muted); margin-top:3px; }}
.legend {{ display:flex; gap:18px; flex-wrap:wrap; font-size:12px; color:var(--ink2);
  margin:10px 0 0; }}
.legend span {{ display:inline-flex; align-items:center; gap:6px; }}
.dot {{ width:10px; height:10px; border-radius:3px; display:inline-block; }}
footer {{ margin-top:40px; padding-top:18px; border-top:1px solid var(--grid);
  font-size:12px; color:var(--muted); }}
.failnote {{ font-size:12px; color:var(--muted); margin-top:10px; }}
</style>

<div class="wrap">
<header class="top">
  <div class="eyebrow">Watchlist Pulse · Momentum &amp; News</div>
  <h1>Watchlist Pulse</h1>
  <p class="sub">Price momentum, volume shifts and headlines across
    <b>{n_rows}</b> tickers · as of <b>{as_of}</b> · data via Yahoo Finance</p>
</header>

<div class="kpis">
  <div class="kpi"><div class="lab">Tickers loaded</div>
    <div class="val">{n_rows}<small>/{n_total}</small></div></div>
  <div class="kpi"><div class="lab">Gainers · 1W</div>
    <div class="val up">{n_gain}</div></div>
  <div class="kpi"><div class="lab">Losers · 1W</div>
    <div class="val down">{n_loss}</div></div>
  <div class="kpi"><div class="lab">Top mover · 1W</div>
    <div class="val up">{best}</div></div>
  <div class="kpi"><div class="lab">Worst mover · 1W</div>
    <div class="val down">{worst}</div></div>
</div>

<section>
  <h2>Movers &amp; Volume Spikes</h2>
  <div class="chipgroup"><div class="glab">▲ Top gainers (1 week)</div>
    <div class="chiprow">{top_g}</div></div>
  <div class="chipgroup"><div class="glab">▼ Top losers (1 week)</div>
    <div class="chiprow">{top_l}</div></div>
  <div class="chipgroup"><div class="glab">◆ Biggest volume spikes (vs 20-day avg)</div>
    <div class="chiprow">{top_v}</div></div>
</section>

<section>
  <h2>Full Watchlist</h2>
  <div class="tablecard"><div class="scroll">
  <table>
    <thead><tr>
      <th>Ticker</th><th>Price</th><th>3-Day</th><th>1-Week</th>
      <th>1-Month</th><th>Volume &#916;</th><th>30-Day Trend</th>
    </tr></thead>
    <tbody>
    {rows}
    </tbody>
  </table>
  </div></div>
  <div class="legend">
    <span><span class="dot" style="background:var(--good)"></span> &#9650; gain</span>
    <span><span class="dot" style="background:var(--bad)"></span> &#9660; loss</span>
    <span>Volume &#916; = latest session vs trailing 20-day average</span>
  </div>
  {failed_note}
</section>

<section>
  <h2>News, Releases &amp; Regulatory Updates</h2>
  <div class="newsgrid">
  {news}
  </div>
</section>

<footer>
  Informational only — not investment advice. Prices may be delayed; some tickers
  (foreign / thinly traded) can fail to resolve. Windows use trading-day look-backs
  (3D &#8776; 3 sessions, 1W &#8776; 5, 1M &#8776; 21). Generated by an automated
  watchlist routine.
</footer>
</div>
"""


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "dashboard.html"
    data = fetch()
    page = render(data)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(page)
    ok = [r for r in data["results"] if "error" not in r and r.get("price") is not None]
    print(f"Wrote {out}: {len(ok)}/{len(TICKERS)} tickers, "
          f"{sum(1 for v in data['news'].values() if v)} with news")


if __name__ == "__main__":
    main()
