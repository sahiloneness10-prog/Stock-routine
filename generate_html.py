"""
Generate a self-contained HTML dashboard snapshot.
All data is fetched once, Plotly charts are embedded inline.
Run with:  python3 generate_html.py
Output:    dashboard.html
"""
from __future__ import annotations

import datetime as dt
import html as html_lib
import json
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import yfinance as yf

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
WINDOWS = {"3D %": 3, "1W %": 5, "1M %": 21}


def _series(data, ticker, field):
    try:
        if isinstance(data.columns, pd.MultiIndex):
            s = data[ticker][field]
        else:
            s = data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def _pct(series, periods):
    s = series.dropna()
    if len(s) <= periods or s.iloc[-1 - periods] == 0:
        return float("nan")
    return (s.iloc[-1] - s.iloc[-1 - periods]) / s.iloc[-1 - periods] * 100


def _vol_chg(volume):
    v = volume.dropna()
    if len(v) < 6:
        return float("nan")
    baseline = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not baseline or np.isnan(baseline):
        return float("nan")
    return (v.iloc[-1] - baseline) / baseline * 100


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html_lib.unescape(text).strip()


def _fmt_date(value):
    if not value:
        return ""
    try:
        ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ts.strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, AttributeError):
        return str(value)


# ---- Fetch data ------------------------------------------------------------
print("Downloading price data…", flush=True)
raw = yf.download(
    TICKERS, period="3mo", interval="1d",
    group_by="ticker", auto_adjust=True, progress=True, threads=True,
)

rows = []
for t in TICKERS:
    close = _series(raw, t, "Close")
    volume = _series(raw, t, "Volume")
    if close.empty:
        continue
    row = {"Ticker": t, "Price": close.iloc[-1], "Volume Δ%": _vol_chg(volume)}
    for label, periods in WINDOWS.items():
        row[label] = _pct(close, periods)
    rows.append(row)

metrics = pd.DataFrame(rows)
print(f"  {len(metrics)}/{len(TICKERS)} tickers loaded.")

# ---- Heatmap ---------------------------------------------------------------
print("Building heatmap…", flush=True)
hm = metrics.set_index("Ticker")[list(WINDOWS)]
heatmap_fig = go.Figure(go.Heatmap(
    z=hm.values,
    x=list(WINDOWS),
    y=hm.index.tolist(),
    colorscale=[[0, "#e74c3c"], [0.5, "#1c1c2e"], [1, "#26a65b"]],
    zmid=0,
    text=np.round(hm.values, 1),
    texttemplate="%{text}%",
    colorbar=dict(title="% chg"),
))
heatmap_fig.update_layout(
    template="plotly_dark",
    height=max(500, 22 * len(hm)),
    margin=dict(l=10, r=10, t=40, b=10),
    title="Percentage change heatmap",
)
heatmap_html = pio.to_html(heatmap_fig, full_html=False, include_plotlyjs=False)

# ---- News (top ~5 per ticker but only render on click) --------------------
print("Fetching news for all tickers…", flush=True)
all_news: dict[str, list[dict]] = {}
for i, t in enumerate(metrics["Ticker"].tolist(), 1):
    try:
        raw_news = yf.Ticker(t).news or []
        items = []
        for entry in raw_news:
            c = entry.get("content", entry) if isinstance(entry, dict) else {}
            if not c:
                continue
            provider = c.get("provider") or {}
            link = c.get("clickThroughUrl") or c.get("canonicalUrl") or {}
            items.append({
                "title": c.get("title", "Untitled"),
                "summary": _clean(c.get("summary") or c.get("description") or ""),
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": _fmt_date(c.get("pubDate") or c.get("displayTime") or ""),
                "type": c.get("contentType", ""),
            })
        all_news[t] = items
        print(f"  [{i}/{len(metrics)}] {t}: {len(items)} news items", flush=True)
    except Exception as exc:
        print(f"  [{i}/{len(metrics)}] {t}: news error ({exc})", flush=True)
        all_news[t] = []

# ---- Table HTML ------------------------------------------------------------
def colour_cell(val, col):
    pct_cols = list(WINDOWS) + ["Volume Δ%"]
    if col not in pct_cols:
        return ""
    if pd.isna(val):
        return 'style="color:#666"'
    shade = min(abs(float(val)) / 12, 1)
    if val > 0:
        alpha = 0.2 + 0.5 * shade
        return f'style="background:rgba(38,166,91,{alpha:.2f});color:#e0ffe8;font-weight:600"'
    if val < 0:
        alpha = 0.2 + 0.5 * shade
        return f'style="background:rgba(231,76,60,{alpha:.2f});color:#ffe8e8;font-weight:600"'
    return ""


def fmt_val(val, col):
    if col == "Price":
        return f"{val:,.2f}" if pd.notna(val) else "—"
    if col in list(WINDOWS) + ["Volume Δ%"]:
        return f"{val:+.2f}%" if pd.notna(val) else "—"
    return str(val)


cols = ["Ticker", "Price"] + list(WINDOWS) + ["Volume Δ%"]
table_rows_html = []
for _, row in metrics.iterrows():
    ticker = row["Ticker"]
    cells = ""
    for col in cols:
        val = row[col]
        c = colour_cell(val, col)
        if col == "Ticker":
            cells += f'<td><button class="ticker-btn" onclick="showDetail(\'{ticker}\')">{ticker}</button></td>'
        else:
            cells += f"<td {c}>{fmt_val(val, col)}</td>"
    table_rows_html.append(f"<tr>{cells}</tr>")

table_html = "\n".join(table_rows_html)

# KPI
gainers = int((metrics["1W %"] > 0).sum())
losers = int((metrics["1W %"] < 0).sum())
best_idx = metrics["1W %"].idxmax() if metrics["1W %"].notna().any() else None
worst_idx = metrics["1W %"].idxmin() if metrics["1W %"].notna().any() else None
best_ticker = metrics.loc[best_idx, "Ticker"] if best_idx is not None else "—"
best_val = f"{metrics.loc[best_idx, '1W %']:+.2f}%" if best_idx is not None else ""
worst_ticker = metrics.loc[worst_idx, "Ticker"] if worst_idx is not None else "—"
worst_val = f"{metrics.loc[worst_idx, '1W %']:+.2f}%" if worst_idx is not None else ""

# ---- Per-ticker detail data for JS ----------------------------------------
detail_data: dict[str, dict] = {}
print("Building per-ticker charts…", flush=True)
for i, t in enumerate(metrics["Ticker"].tolist(), 1):
    try:
        hist = yf.Ticker(t).history(period="6mo", auto_adjust=True)
        if not hist.empty:
            fig = go.Figure(go.Candlestick(
                x=hist.index.strftime("%Y-%m-%d").tolist(),
                open=hist["Open"].tolist(),
                high=hist["High"].tolist(),
                low=hist["Low"].tolist(),
                close=hist["Close"].tolist(),
                increasing_line_color="#26a65b",
                decreasing_line_color="#e74c3c",
                name=t,
            ))
            fig.update_layout(
                template="plotly_dark",
                height=400,
                margin=dict(l=10, r=10, t=35, b=10),
                xaxis_rangeslider_visible=False,
                title=f"{t} — 6-month price",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
            )
            chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)
        else:
            chart_html = "<p style='color:#888'>No chart data available.</p>"
        print(f"  [{i}/{len(metrics)}] {t} chart OK", flush=True)
    except Exception as exc:
        chart_html = f"<p style='color:#888'>Chart error: {exc}</p>"
        print(f"  [{i}/{len(metrics)}] {t} chart error: {exc}", flush=True)

    row = metrics[metrics["Ticker"] == t].iloc[0]
    detail_data[t] = {
        "chart": chart_html,
        "news": all_news.get(t, []),
        "price": fmt_val(row["Price"], "Price"),
        "3d": fmt_val(row["3D %"], "3D %"),
        "1w": fmt_val(row["1W %"], "1W %"),
        "1m": fmt_val(row["1M %"], "1M %"),
        "vol": fmt_val(row["Volume Δ%"], "Volume Δ%"),
    }

detail_json = json.dumps(detail_data, ensure_ascii=False)

# ---- Build the HTML --------------------------------------------------------
print("Writing dashboard.html…", flush=True)
generated_at = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Watchlist Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --bg: #0e1117; --surface: #161b22; --border: #30363d;
    --text: #e6edf3; --muted: #8b949e;
    --green: #26a65b; --red: #e74c3c; --accent: #58a6ff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
  header {{ padding: 1.5rem 2rem 0.5rem; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  header p {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }}
  .kpi-strip {{ display: flex; gap: 1rem; padding: 1.2rem 2rem; flex-wrap: wrap; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
           padding: 1rem 1.5rem; min-width: 140px; flex: 1; }}
  .kpi-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
  .kpi-value {{ font-size: 1.6rem; font-weight: 700; margin-top: 0.2rem; }}
  .kpi-sub {{ font-size: 0.8rem; margin-top: 0.1rem; }}
  .kpi-value.green {{ color: var(--green); }}
  .kpi-value.red {{ color: var(--red); }}
  .tabs {{ display: flex; gap: 0; padding: 0 2rem; border-bottom: 1px solid var(--border); margin-top: 0.5rem; }}
  .tab-btn {{ background: none; border: none; color: var(--muted); padding: 0.75rem 1.25rem;
               font-size: 0.9rem; cursor: pointer; border-bottom: 2px solid transparent; transition: all .2s; }}
  .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }}
  .tab-btn:hover {{ color: var(--text); }}
  .tab-panel {{ display: none; padding: 1.5rem 2rem; }}
  .tab-panel.active {{ display: block; }}
  /* Table */
  .table-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; }}
  thead th {{ background: var(--surface); color: var(--muted); font-weight: 600; text-align: left;
              padding: 0.75rem 1rem; font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em;
              cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 1; }}
  thead th:hover {{ color: var(--text); }}
  thead th .sort-arrow {{ opacity: 0.4; margin-left: 4px; }}
  thead th.sorted .sort-arrow {{ opacity: 1; color: var(--accent); }}
  tbody tr {{ border-top: 1px solid var(--border); transition: background .15s; }}
  tbody tr:hover {{ background: rgba(88,166,255,0.04); }}
  tbody td {{ padding: 0.6rem 1rem; white-space: nowrap; }}
  .ticker-btn {{ background: none; border: none; color: var(--accent); font-weight: 600; font-size: 0.88rem;
                  cursor: pointer; text-decoration: underline; text-decoration-color: transparent;
                  transition: text-decoration-color .15s; }}
  .ticker-btn:hover {{ text-decoration-color: var(--accent); }}
  /* Filter */
  .table-controls {{ display: flex; gap: 1rem; margin-bottom: 1rem; align-items: center; flex-wrap: wrap; }}
  .search-box {{ background: var(--surface); border: 1px solid var(--border); color: var(--text);
                  border-radius: 6px; padding: 0.45rem 0.75rem; font-size: 0.88rem; width: 200px; }}
  .search-box::placeholder {{ color: var(--muted); }}
  .filter-select {{ background: var(--surface); border: 1px solid var(--border); color: var(--text);
                     border-radius: 6px; padding: 0.45rem 0.65rem; font-size: 0.88rem; cursor: pointer; }}
  /* Detail panel */
  .detail-panel {{ display: none; position: fixed; top: 0; right: 0; width: min(680px, 100vw);
                    height: 100vh; background: var(--surface); border-left: 1px solid var(--border);
                    z-index: 100; overflow-y: auto; box-shadow: -8px 0 32px rgba(0,0,0,.5); }}
  .detail-panel.open {{ display: flex; flex-direction: column; }}
  .detail-header {{ display: flex; align-items: center; justify-content: space-between;
                     padding: 1rem 1.5rem; border-bottom: 1px solid var(--border);
                     position: sticky; top: 0; background: var(--surface); z-index: 1; }}
  .detail-header h2 {{ font-size: 1.2rem; }}
  .close-btn {{ background: none; border: none; color: var(--muted); font-size: 1.4rem; cursor: pointer; line-height: 1; }}
  .close-btn:hover {{ color: var(--text); }}
  .detail-body {{ padding: 1.25rem 1.5rem; flex: 1; }}
  .metric-row {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1.25rem; }}
  .metric-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
                   padding: 0.75rem 1rem; flex: 1; min-width: 90px; }}
  .metric-card .label {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }}
  .metric-card .value {{ font-size: 1.15rem; font-weight: 700; margin-top: 0.2rem; }}
  .metric-card .value.pos {{ color: var(--green); }}
  .metric-card .value.neg {{ color: var(--red); }}
  .news-item {{ border-top: 1px solid var(--border); padding: 1rem 0; }}
  .news-item:first-child {{ border-top: none; padding-top: 0; }}
  .news-title {{ font-weight: 600; font-size: 0.92rem; line-height: 1.4; }}
  .news-title a {{ color: var(--text); text-decoration: none; }}
  .news-title a:hover {{ color: var(--accent); }}
  .news-meta {{ font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }}
  .news-summary {{ font-size: 0.83rem; color: #c0c8d4; margin-top: 0.4rem; line-height: 1.5; }}
  .no-news {{ color: var(--muted); font-size: 0.88rem; padding: 1rem 0; }}
  .overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 99; }}
  .overlay.open {{ display: block; }}
  /* Heatmap */
  #heatmap-container {{ overflow-x: auto; }}
  /* Footer */
  footer {{ padding: 1rem 2rem; color: var(--muted); font-size: 0.78rem; border-top: 1px solid var(--border); margin-top: 2rem; }}
  @media(max-width:600px) {{
    header, .kpi-strip, .tab-panel {{ padding-left: 1rem; padding-right: 1rem; }}
    .kpi {{ min-width: 120px; padding: 0.75rem 1rem; }}
    .detail-panel {{ width: 100vw; }}
  }}
</style>
</head>
<body>

<header>
  <h1>📈 Watchlist Momentum Dashboard</h1>
  <p>3-day · 1-week · 1-month price moves, volume shifts &amp; latest news &nbsp;|&nbsp; Generated {generated_at} &nbsp;|&nbsp; Data via Yahoo Finance</p>
</header>

<div class="kpi-strip">
  <div class="kpi">
    <div class="kpi-label">Tickers loaded</div>
    <div class="kpi-value">{len(metrics)}<span style="font-size:1rem;color:var(--muted)">/{len(TICKERS)}</span></div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Gainers (1W)</div>
    <div class="kpi-value green">{gainers}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Losers (1W)</div>
    <div class="kpi-value red">{losers}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Top mover (1W)</div>
    <div class="kpi-value green" style="font-size:1.15rem">{best_ticker}</div>
    <div class="kpi-sub" style="color:var(--green)">{best_val}</div>
  </div>
  <div class="kpi">
    <div class="kpi-label">Worst mover (1W)</div>
    <div class="kpi-value red" style="font-size:1.15rem">{worst_ticker}</div>
    <div class="kpi-sub" style="color:var(--red)">{worst_val}</div>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('overview',this)">📋 Overview</button>
  <button class="tab-btn" onclick="switchTab('heatmap',this)">🌡️ Heatmap</button>
</div>

<!-- OVERVIEW TAB -->
<div id="tab-overview" class="tab-panel active">
  <div class="table-controls">
    <input class="search-box" type="text" id="search" placeholder="Search ticker…" oninput="filterTable()">
    <select class="filter-select" id="filter-dir" onchange="filterTable()">
      <option value="all">All directions</option>
      <option value="gainers">Gainers (1W)</option>
      <option value="losers">Losers (1W)</option>
    </select>
    <select class="filter-select" id="sort-col" onchange="sortTable(this.value, true)">
      <option value="1">Ticker</option>
      <option value="2">Price</option>
      <option value="3" selected>3D %</option>
      <option value="4">1W %</option>
      <option value="5">1M %</option>
      <option value="6">Volume Δ%</option>
    </select>
  </div>
  <div class="table-wrap">
    <table id="main-table">
      <thead>
        <tr>
          <th onclick="sortTable(0)" data-col="0">Ticker <span class="sort-arrow">⇅</span></th>
          <th onclick="sortTable(1)" data-col="1">Price <span class="sort-arrow">⇅</span></th>
          <th onclick="sortTable(2)" data-col="2">3D % <span class="sort-arrow">⇅</span></th>
          <th onclick="sortTable(3)" data-col="3">1W % <span class="sort-arrow">⇅</span></th>
          <th onclick="sortTable(4)" data-col="4">1M % <span class="sort-arrow">⇅</span></th>
          <th onclick="sortTable(5)" data-col="5">Volume Δ% <span class="sort-arrow">⇅</span></th>
        </tr>
      </thead>
      <tbody id="table-body">
{table_html}
      </tbody>
    </table>
  </div>
</div>

<!-- HEATMAP TAB -->
<div id="tab-heatmap" class="tab-panel">
  <div id="heatmap-container">
    {heatmap_html}
  </div>
</div>

<!-- DETAIL PANEL -->
<div class="overlay" id="overlay" onclick="closeDetail()"></div>
<div class="detail-panel" id="detail-panel">
  <div class="detail-header">
    <h2 id="detail-title">—</h2>
    <button class="close-btn" onclick="closeDetail()">✕</button>
  </div>
  <div class="detail-body">
    <div class="metric-row" id="detail-metrics"></div>
    <div id="detail-chart"></div>
    <h3 style="margin:1.25rem 0 0.75rem;font-size:0.95rem">📰 Latest news &amp; regulatory updates</h3>
    <div id="detail-news"></div>
  </div>
</div>

<footer>
  ℹ️ Informational only — not investment advice. Yahoo Finance data may be delayed.
  Snapshot generated {generated_at}. Re-run <code>python3 generate_html.py</code> to refresh.
</footer>

<script>
const DATA = {detail_json};

// ---- tabs ------------------------------------------------------------------
function switchTab(name, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}}

// ---- sort ------------------------------------------------------------------
let sortState = {{col: 3, asc: false}};
function sortTable(colIdx, fromSelect) {{
  colIdx = parseInt(colIdx);
  if (!fromSelect) {{
    if (sortState.col === colIdx) sortState.asc = !sortState.asc;
    else {{ sortState.col = colIdx; sortState.asc = false; }}
  }} else {{
    sortState.col = colIdx; sortState.asc = false;
  }}
  document.querySelectorAll('thead th').forEach((th, i) => {{
    th.classList.toggle('sorted', i === sortState.col);
    if (i === sortState.col) th.querySelector('.sort-arrow').textContent = sortState.asc ? '↑' : '↓';
    else th.querySelector('.sort-arrow').textContent = '⇅';
  }});
  const tbody = document.getElementById('table-body');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {{
    const av = a.cells[sortState.col].textContent.replace('%','').replace('+','').trim();
    const bv = b.cells[sortState.col].textContent.replace('%','').replace('+','').trim();
    const an = parseFloat(av), bn = parseFloat(bv);
    if (isNaN(an) && isNaN(bn)) return 0;
    if (isNaN(an)) return 1; if (isNaN(bn)) return -1;
    return sortState.asc ? an - bn : bn - an;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ---- filter ----------------------------------------------------------------
function filterTable() {{
  const q = document.getElementById('search').value.toLowerCase();
  const dir = document.getElementById('filter-dir').value;
  document.querySelectorAll('#table-body tr').forEach(row => {{
    const ticker = row.cells[0].textContent.toLowerCase();
    const wVal = parseFloat(row.cells[3].textContent.replace('%','').replace('+',''));
    let show = ticker.includes(q);
    if (show && dir === 'gainers') show = wVal > 0;
    if (show && dir === 'losers') show = wVal < 0;
    row.style.display = show ? '' : 'none';
  }});
}}

// ---- detail panel ----------------------------------------------------------
function valClass(v) {{
  if (!v || v === '—') return '';
  return parseFloat(v) >= 0 ? 'pos' : 'neg';
}}

function showDetail(ticker) {{
  const d = DATA[ticker];
  if (!d) return;
  document.getElementById('detail-title').textContent = ticker;

  const mRow = document.getElementById('detail-metrics');
  mRow.innerHTML = [
    ['Price', d.price, ''],
    ['3-day', d['3d'], valClass(d['3d'])],
    ['1-week', d['1w'], valClass(d['1w'])],
    ['1-month', d['1m'], valClass(d['1m'])],
    ['Volume Δ', d.vol, valClass(d.vol)],
  ].map(([lbl, val, cls]) =>
    `<div class="metric-card"><div class="label">${{lbl}}</div><div class="value ${{cls}}">${{val}}</div></div>`
  ).join('');

  document.getElementById('detail-chart').innerHTML = d.chart;
  // Plotly needs a nudge after injecting HTML
  document.getElementById('detail-chart').querySelectorAll('.js-plotly-plot').forEach(el => {{
    try {{ Plotly.relayout(el, {{}}); }} catch(e) {{}}
  }});

  const newsEl = document.getElementById('detail-news');
  if (!d.news || d.news.length === 0) {{
    newsEl.innerHTML = '<p class="no-news">No recent news found for this ticker.</p>';
  }} else {{
    newsEl.innerHTML = d.news.map(n => {{
      const title = n.url
        ? `<a href="${{n.url}}" target="_blank" rel="noopener">${{n.title}}</a>`
        : n.title;
      const meta = [n.publisher, n.published, n.type].filter(Boolean).join(' · ');
      return `<div class="news-item">
        <div class="news-title">${{title}}</div>
        ${{meta ? `<div class="news-meta">${{meta}}</div>` : ''}}
        ${{n.summary ? `<div class="news-summary">${{n.summary}}</div>` : ''}}
      </div>`;
    }}).join('');
  }}

  document.getElementById('detail-panel').classList.add('open');
  document.getElementById('overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
}}

function closeDetail() {{
  document.getElementById('detail-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
  document.body.style.overflow = '';
}}

document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeDetail(); }});

// Initial sort by 1W %
sortTable(3, false);
</script>
</body>
</html>
"""

with open("dashboard.html", "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"\n✅  dashboard.html written ({len(HTML)//1024} KB)")
print("   Open it in any browser — no server needed.")
