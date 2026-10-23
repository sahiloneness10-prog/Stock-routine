"""
Static watchlist dashboard generator.
=====================================
Fetches ~3 months of OHLCV for the watchlist, computes 3-day / 1-week /
1-month price moves and a volume shift, then renders a single self-contained,
visually styled ``dashboard.html`` snapshot plus a ``metrics.json`` file.

Unlike ``app.py`` (the interactive Streamlit app), this produces a static file
that can be generated on a schedule, shared, or viewed without a running
server.  An optional ``news.json`` ({ticker: [ {title, source, url, date,
summary}, ... ]}) is embedded into a "catalysts" section when present.

Run with:
    python3 generate_dashboard.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))

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
WINDOWS = {"3D %": 3, "1W %": 5, "1M %": 21}

# Rough currency hint by Yahoo suffix (for display only).
SUFFIX_CCY = {".NS": "₹", ".BO": "₹", ".L": "p", ".IL": "p"}


# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
def download(tickers: list[str]) -> pd.DataFrame:
    return yf.download(
        tickers,
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )


def series(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    try:
        if isinstance(data.columns, pd.MultiIndex):
            s = data[ticker][field]
        else:
            s = data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def pct_change(s: pd.Series, periods: int) -> float:
    s = s.dropna()
    if len(s) <= periods:
        return math.nan
    prev = s.iloc[-1 - periods]
    if prev == 0:
        return math.nan
    return (s.iloc[-1] - prev) / prev * 100


def volume_change(v: pd.Series) -> float:
    v = v.dropna()
    if len(v) < 6:
        return math.nan
    latest = v.iloc[-1]
    baseline = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not baseline or math.isnan(baseline):
        return math.nan
    return (latest - baseline) / baseline * 100


def currency(ticker: str) -> str:
    for suf, sym in SUFFIX_CCY.items():
        if ticker.endswith(suf):
            return sym
    return "$"


def build_metrics(data: pd.DataFrame) -> list[dict]:
    rows = []
    for t in TICKERS:
        close = series(data, t, "Close")
        vol = series(data, t, "Volume")
        if close.empty:
            continue
        spark = close.iloc[-21:].tolist()
        rows.append(
            {
                "ticker": t,
                "ccy": currency(t),
                "price": float(close.iloc[-1]),
                "d3": pct_change(close, 3),
                "w1": pct_change(close, 5),
                "m1": pct_change(close, 21),
                "vol": volume_change(vol),
                "spark": [float(x) for x in spark],
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def nan_to_none(x):
    return None if (x is None or (isinstance(x, float) and math.isnan(x))) else x


def clean_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        for k in ("d3", "w1", "m1", "vol"):
            r[k] = nan_to_none(r[k])
        out.append(r)
    return out


def sparkline_svg(vals: list[float], up: bool) -> str:
    if not vals or len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    w, h = 120, 32
    pts = []
    for i, v in enumerate(vals):
        x = i / (len(vals) - 1) * (w - 2) + 1
        y = h - 2 - (v - lo) / rng * (h - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    color = "#3fb950" if up else "#f85149"
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
        f'<polyline fill="none" stroke="{color}" stroke-width="1.5" points="{" ".join(pts)}"/>'
        f"</svg>"
    )


def pct_cell(v) -> str:
    if v is None:
        return '<td class="num muted">—</td>'
    cls = "pos" if v > 0 else "neg" if v < 0 else "flat"
    shade = min(abs(v) / 12, 1)
    alpha = 0.10 + 0.40 * shade
    rgb = "63,185,80" if v > 0 else "248,81,73" if v < 0 else "139,148,158"
    return (
        f'<td class="num {cls}" style="background:rgba({rgb},{alpha:.2f})">'
        f"{v:+.2f}%</td>"
    )


def vol_cell(v) -> str:
    if v is None:
        return '<td class="num muted">—</td>'
    cls = "pos" if v > 0 else "neg"
    return f'<td class="num {cls}">{v:+.0f}%</td>'


def render_html(rows: list[dict], news: dict, failed: list[str]) -> str:
    rows = clean_rows(rows)
    generated = dt.datetime.now(dt.timezone.utc).strftime("%b %d, %Y · %H:%M UTC")

    have_w1 = [r for r in rows if r["w1"] is not None]
    gainers = sum(1 for r in have_w1 if r["w1"] > 0)
    losers = sum(1 for r in have_w1 if r["w1"] < 0)
    best = max(have_w1, key=lambda r: r["w1"]) if have_w1 else None
    worst = min(have_w1, key=lambda r: r["w1"]) if have_w1 else None
    have_vol = [r for r in rows if r["vol"] is not None]
    vol_spike = max(have_vol, key=lambda r: r["vol"]) if have_vol else None

    # Table rows, sorted by 1-week move (desc, None last).
    srows = sorted(
        rows, key=lambda r: (r["w1"] is None, -(r["w1"] or 0))
    )
    body = []
    for r in srows:
        sp = r["spark"]
        up = (sp[-1] >= sp[0]) if len(sp) >= 2 else (r["w1"] or 0) >= 0
        body.append(
            "<tr>"
            f'<td class="tk">{html.escape(r["ticker"])}</td>'
            f'<td class="num price">{r["ccy"]}{r["price"]:,.2f}</td>'
            f"{pct_cell(r['d3'])}{pct_cell(r['w1'])}{pct_cell(r['m1'])}"
            f"{vol_cell(r['vol'])}"
            f'<td class="sp">{sparkline_svg(r["spark"], up)}</td>'
            "</tr>"
        )
    table_body = "\n".join(body)

    # Catalysts / news section.
    news_html = []
    for tk in sorted(news):
        items = news[tk]
        if not items:
            continue
        cards = []
        for it in items:
            title = html.escape(it.get("title", "")).strip()
            url = html.escape(it.get("url", "")).strip()
            src = html.escape(it.get("source", "")).strip()
            date = html.escape(it.get("date", "")).strip()
            summary = html.escape(it.get("summary", "")).strip()
            meta = " · ".join(x for x in [src, date] if x)
            head = f'<a href="{url}" target="_blank" rel="noopener">{title}</a>' if url else title
            cards.append(
                '<div class="news-item">'
                f'<div class="news-title">{head}</div>'
                + (f'<div class="news-meta">{meta}</div>' if meta else "")
                + (f'<div class="news-sum">{summary}</div>' if summary else "")
                + "</div>"
            )
        news_html.append(
            '<div class="news-block">'
            f'<div class="news-tk">{html.escape(tk)}</div>'
            + "".join(cards)
            + "</div>"
        )
    news_section = (
        "\n".join(news_html)
        if news_html
        else '<p class="muted">No catalyst headlines were attached for this run.</p>'
    )

    failed_note = (
        f'<p class="muted small">No price data resolved for: {html.escape(", ".join(failed))}.</p>'
        if failed
        else ""
    )

    def kpi(label, value, sub="", tone=""):
        return (
            f'<div class="kpi {tone}"><div class="kpi-l">{label}</div>'
            f'<div class="kpi-v">{value}</div>'
            + (f'<div class="kpi-s">{sub}</div>' if sub else "")
            + "</div>"
        )

    kpis = "".join(
        [
            kpi("Tickers loaded", f"{len(rows)}<span class='of'>/{len(TICKERS)}</span>"),
            kpi("Gainers (1W)", str(gainers), tone="pos"),
            kpi("Losers (1W)", str(losers), tone="neg"),
            kpi(
                "Top mover (1W)",
                html.escape(best["ticker"]) if best else "—",
                f"{best['w1']:+.2f}%" if best else "",
                tone="pos",
            ),
            kpi(
                "Worst mover (1W)",
                html.escape(worst["ticker"]) if worst else "—",
                f"{worst['w1']:+.2f}%" if worst else "",
                tone="neg",
            ),
            kpi(
                "Volume spike",
                html.escape(vol_spike["ticker"]) if vol_spike else "—",
                f"{vol_spike['vol']:+.0f}% vs 20d" if vol_spike else "",
            ),
        ]
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Dashboard</title>
<style>
  :root {{
    --bg:#0d1117; --panel:#161b22; --panel2:#1c2230; --border:#30363d;
    --text:#e6edf3; --muted:#8b949e; --pos:#3fb950; --neg:#f85149;
    --accent:#58a6ff;
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    padding:28px 20px 60px;
  }}
  .wrap {{ max-width:1100px; margin:0 auto; }}
  header h1 {{ margin:0 0 4px; font-size:1.7rem; letter-spacing:.3px; }}
  header h1 .em {{ filter:saturate(1.2); }}
  .sub {{ color:var(--muted); font-size:.9rem; margin:0 0 22px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:26px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:14px 16px; }}
  .kpi-l {{ color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.6px; }}
  .kpi-v {{ font-size:1.5rem; font-weight:650; margin-top:4px; }}
  .kpi-v .of {{ color:var(--muted); font-size:1rem; font-weight:400; }}
  .kpi-s {{ font-size:.85rem; margin-top:2px; color:var(--muted); }}
  .kpi.pos .kpi-s {{ color:var(--pos); }}
  .kpi.neg .kpi-s {{ color:var(--neg); }}
  h2 {{ font-size:1.05rem; margin:30px 0 12px; letter-spacing:.3px; }}
  .panel {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; overflow:hidden; }}
  table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
  thead th {{ background:var(--panel2); color:var(--muted); text-align:right; padding:11px 14px;
    font-weight:600; font-size:.74rem; text-transform:uppercase; letter-spacing:.5px;
    position:sticky; top:0; }}
  thead th:first-child {{ text-align:left; }}
  tbody td {{ padding:9px 14px; border-top:1px solid var(--border); }}
  tbody tr:hover td {{ background:rgba(88,166,255,.06); }}
  .tk {{ font-weight:650; letter-spacing:.3px; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .price {{ color:var(--text); }}
  .pos {{ color:var(--pos); }}
  .neg {{ color:var(--neg); }}
  .flat, .muted {{ color:var(--muted); }}
  .sp {{ text-align:right; width:130px; }}
  svg.spark {{ width:120px; height:32px; vertical-align:middle; }}
  .news-block {{ border-top:1px solid var(--border); padding:14px 16px; }}
  .news-block:first-child {{ border-top:none; }}
  .news-tk {{ font-weight:700; color:var(--accent); margin-bottom:8px; letter-spacing:.3px; }}
  .news-item {{ margin:0 0 10px; }}
  .news-title a {{ color:var(--text); text-decoration:none; border-bottom:1px solid transparent; }}
  .news-title a:hover {{ border-bottom-color:var(--accent); color:var(--accent); }}
  .news-meta {{ color:var(--muted); font-size:.78rem; margin-top:2px; }}
  .news-sum {{ font-size:.86rem; color:#c9d1d9; margin-top:4px; line-height:1.45; }}
  .small {{ font-size:.8rem; }}
  footer {{ color:var(--muted); font-size:.78rem; margin-top:30px; line-height:1.5; }}
  @media (max-width:820px) {{
    .kpis {{ grid-template-columns:repeat(2,1fr); }}
    .sp {{ display:none; }}
    thead th.sp {{ display:none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="em">📈</span> Watchlist Momentum Dashboard</h1>
    <p class="sub">Price moves, volume shifts & catalyst headlines across {len(TICKERS)} tickers · generated {generated} · data via Yahoo Finance</p>
  </header>

  <div class="kpis">{kpis}</div>

  <h2>📋 Momentum &amp; volume</h2>
  <div class="panel">
    <table>
      <thead><tr>
        <th>Ticker</th><th>Price</th><th>3-Day</th><th>1-Week</th>
        <th>1-Month</th><th>Vol vs 20d</th><th class="sp">1-Mo trend</th>
      </tr></thead>
      <tbody>
{table_body}
      </tbody>
    </table>
  </div>
  {failed_note}

  <h2>📰 Catalysts — news, releases &amp; regulatory updates</h2>
  <div class="panel" style="padding:4px 0;">
    {news_section}
  </div>

  <footer>
    ℹ️ Informational only — not investment advice. Yahoo Finance prices may be delayed,
    may be split/dividend-adjusted, and some tickers may fail to resolve. % changes use
    trading-day look-backs (3 / 5 / 21 sessions). Volume is the latest session vs the
    trailing 20-day average.
  </footer>
</div>
</body>
</html>"""


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    news_path = os.path.join(HERE, "news.json")
    news: dict = {}
    if os.path.exists(news_path):
        try:
            with open(news_path, encoding="utf-8") as fh:
                news = json.load(fh)
        except (OSError, json.JSONDecodeError):
            news = {}

    data = download(TICKERS)
    rows = build_metrics(data)
    loaded = {r["ticker"] for r in rows}
    failed = [t for t in TICKERS if t not in loaded]

    with open(os.path.join(HERE, "metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(
            {
                "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "rows": clean_rows(rows),
                "failed": failed,
            },
            fh,
            indent=2,
        )

    out_html = render_html(rows, news, failed)
    with open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8") as fh:
        fh.write(out_html)

    print(f"Loaded {len(rows)}/{len(TICKERS)} tickers. Failed: {failed}")
    print("Wrote dashboard.html and metrics.json")


if __name__ == "__main__":
    main()
