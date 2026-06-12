"""
Watchlist Momentum Dashboard
============================
A visual, interactive Streamlit dashboard for a custom stock watchlist.

It surfaces, for every ticker:

* 3-day / 1-week / 1-month price moves
* Volume shift versus the trailing 20-day average
* A trend sparkline
* The latest news, press releases and (heuristically flagged) regulatory items

Run with::

    streamlit run app.py
"""

from __future__ import annotations

import datetime as dt
import html
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

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
WINDOWS = {"3D %": 3, "1W %": 5, "1M %": 21}
PCT_COLS = list(WINDOWS) + ["Volume Δ%"]

# Map an exchange suffix to a readable market + flag.
REGION_MAP = {
    ".NS": ("India", "🇮🇳"),
    ".BO": ("India", "🇮🇳"),
    ".L": ("United Kingdom", "🇬🇧"),
    ".IL": ("UK (Intl)", "🇬🇧"),
}
DEFAULT_REGION = ("United States", "🇺🇸")

# Keywords used to flag regulatory / filing related headlines.
REGULATORY_KEYWORDS = (
    "sec ", "fda", "regulat", "lawsuit", "antitrust", "filing", "10-k", "10-q",
    "8-k", "court", "ruling", "approval", "approve", "investigation", "probe",
    "settlement", "compliance", "subpoena", "fine", "sanction", "tariff",
    "patent", "merger", "acquisition", "acquire", "ftc", "doj", "cma", "sebi",
    "license", "recall", "guidance", "delist", "bankruptc",
)

# Theme colours
GREEN = "#22c55e"
RED = "#ef4444"
FLAT = "#9ca3af"


# --------------------------------------------------------------------------- #
# Data layer (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=900, show_spinner=False)
def load_prices(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Batch-download ~3 months of OHLCV for every ticker."""
    return yf.download(
        list(tickers),
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )


def _series(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    """Pull one OHLCV field for one ticker out of the multi-index frame."""
    try:
        if isinstance(data.columns, pd.MultiIndex):
            s = data[ticker][field]
        else:  # single ticker -> flat columns
            s = data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def _pct_change(series: pd.Series, periods: int) -> float:
    s = series.dropna()
    if len(s) <= periods:
        return np.nan
    prev = s.iloc[-1 - periods]
    if prev == 0:
        return np.nan
    return (s.iloc[-1] - prev) / prev * 100


def _volume_change(volume: pd.Series) -> float:
    """Latest session volume vs the trailing 20-day average."""
    v = volume.dropna()
    if len(v) < 6:
        return np.nan
    latest = v.iloc[-1]
    baseline = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not baseline or np.isnan(baseline):
        return np.nan
    return (latest - baseline) / baseline * 100


def _region(ticker: str) -> tuple[str, str]:
    for suffix, region in REGION_MAP.items():
        if ticker.endswith(suffix):
            return region
    return DEFAULT_REGION


@st.cache_data(ttl=900, show_spinner=False)
def build_metrics(tickers: tuple[str, ...]) -> pd.DataFrame:
    data = load_prices(tickers)
    rows = []
    for t in tickers:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            continue
        region, flag = _region(t)
        row = {
            "Ticker": t,
            "Flag": flag,
            "Region": region,
            "Price": float(close.iloc[-1]),
            "Volume Δ%": _volume_change(volume),
            # last ~30 closes, used to draw sparklines
            "spark": [float(x) for x in close.iloc[-30:].tolist()],
        }
        for label, periods in WINDOWS.items():
            row[label] = _pct_change(close, periods)
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(period="6mo", auto_adjust=True)


@st.cache_data(ttl=3600, show_spinner=False)
def company_name(ticker: str) -> str:
    """Best-effort company name (cached, never blocks the main view)."""
    try:
        info = yf.Ticker(ticker).get_info()
        return info.get("shortName") or info.get("longName") or ticker
    except Exception:
        return ticker


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


@st.cache_data(ttl=900, show_spinner=False)
def load_news(ticker: str) -> list[dict]:
    """Return a normalised, categorised list of recent news items."""
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []
    items = []
    for entry in raw:
        c = entry.get("content", entry) if isinstance(entry, dict) else {}
        if not c:
            continue
        provider = c.get("provider") or {}
        link = c.get("clickThroughUrl") or c.get("canonicalUrl") or {}
        title = c.get("title", "Untitled")
        summary = _clean_html(c.get("summary") or c.get("description") or "")
        blob = f"{title} {summary}".lower()
        regulatory = any(kw in blob for kw in REGULATORY_KEYWORDS)
        items.append(
            {
                "title": title,
                "summary": summary,
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
                "type": c.get("contentType", ""),
                "regulatory": regulatory,
            }
        )
    return items


# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
def _fmt_published(value: str) -> str:
    if not value:
        return ""
    try:
        ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return ts.strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, AttributeError):
        return str(value)


def _colour_for(val: float) -> str:
    if pd.isna(val) or val == 0:
        return FLAT
    return GREEN if val > 0 else RED


def sparkline_svg(values: list[float], width: int = 150, height: int = 38) -> str:
    """Render a tiny inline-SVG sparkline coloured by net direction."""
    vals = [v for v in values if v is not None and not pd.isna(v)]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pad = 3
    coords = []
    for i, v in enumerate(vals):
        x = pad + i / (n - 1) * (width - 2 * pad)
        y = pad + (1 - (v - lo) / rng) * (height - 2 * pad)
        coords.append((x, y))
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    colour = GREEN if vals[-1] >= vals[0] else RED
    area_pts = f"{pad},{height - pad} {pts} {width - pad},{height - pad}"
    gid = f"g{abs(hash(tuple(vals))) % 100000}"
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none">'
        f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1">'
        f'<stop offset="0%" stop-color="{colour}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{colour}" stop-opacity="0"/>'
        f"</linearGradient></defs>"
        f'<polygon points="{area_pts}" fill="url(#{gid})" stroke="none"/>'
        f'<polyline points="{pts}" fill="none" stroke="{colour}" '
        f'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
        f"</svg>"
    )


def _chip(label: str, val: float) -> str:
    colour = _colour_for(val)
    text = "—" if pd.isna(val) else f"{val:+.1f}%"
    return (
        f'<div class="chip"><span class="chip-l">{label}</span>'
        f'<span class="chip-v" style="color:{colour}">{text}</span></div>'
    )


def card_html(row: pd.Series) -> str:
    vol = row["Volume Δ%"]
    vol_txt = "—" if pd.isna(vol) else f"{vol:+.0f}%"
    vol_col = _colour_for(vol)
    accent = _colour_for(row["1W %"])
    # NB: emitted as a single line with no leading indentation — Streamlit's
    # markdown renderer treats indented (4+ space) HTML as a code block.
    return (
        f'<div class="card" style="border-top:3px solid {accent}">'
        f'<div class="card-head">'
        f'<span class="tk">{html.escape(row["Ticker"])}</span>'
        f'<span class="flag" title="{row["Region"]}">{row["Flag"]}</span>'
        f"</div>"
        f'<div class="price">{row["Price"]:,.2f}</div>'
        f'<div class="spark">{sparkline_svg(row["spark"])}</div>'
        f'<div class="chips">'
        f'{_chip("3D", row["3D %"])}{_chip("1W", row["1W %"])}{_chip("1M", row["1M %"])}'
        f"</div>"
        f'<div class="vol">Volume vs 20d&nbsp;avg: '
        f'<b style="color:{vol_col}">{vol_txt}</b></div>'
        f"</div>"
    )


def style_table(df: pd.DataFrame):
    def colour(val):
        if pd.isna(val):
            return "color:#666"
        if val > 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(34,197,94,{0.12 + 0.5 * shade});color:#eafff2"
        if val < 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(239,68,68,{0.12 + 0.5 * shade});color:#ffecec"
        return "color:#ccc"

    return (
        df.style.map(colour, subset=PCT_COLS)
        .format({"Price": "{:,.2f}", **{c: "{:+.2f}%" for c in PCT_COLS}}, na_rep="—")
    )


def breadth_bar(series: pd.Series) -> go.Figure:
    up = int((series > 0).sum())
    flat = int((series == 0).sum())
    down = int((series < 0).sum())
    fig = go.Figure()
    for value, colour, name in [
        (up, GREEN, "Up"),
        (flat, FLAT, "Flat"),
        (down, RED, "Down"),
    ]:
        fig.add_bar(
            y=["breadth"], x=[value], name=name, orientation="h",
            marker_color=colour, text=[value if value else ""],
            textposition="inside", insidetextanchor="middle",
            hovertemplate=f"{name}: %{{x}}<extra></extra>",
        )
    fig.update_layout(
        barmode="stack", template="plotly_dark", height=90,
        margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
        legend=dict(orientation="h", y=-0.4),
        yaxis=dict(showticklabels=False), xaxis=dict(showticklabels=False),
    )
    return fig


def movers_bar(df: pd.DataFrame, col: str, top: int = 12) -> go.Figure:
    d = df.dropna(subset=[col]).sort_values(col)
    picks = pd.concat([d.head(top), d.tail(top)]).drop_duplicates("Ticker")
    colours = [GREEN if v >= 0 else RED for v in picks[col]]
    fig = go.Figure(
        go.Bar(
            x=picks[col], y=picks["Ticker"], orientation="h",
            marker_color=colours,
            text=[f"{v:+.1f}%" for v in picks[col]], textposition="auto",
            hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_dark", height=max(380, 26 * len(picks)),
        margin=dict(l=10, r=10, t=40, b=10),
        title=f"Biggest movers · {col}",
        xaxis_title="% change", yaxis=dict(autorange="reversed"),
    )
    return fig


def treemap(df: pd.DataFrame, col: str) -> go.Figure:
    d = df.dropna(subset=[col]).copy()
    regions = sorted(d["Region"].unique())
    labels = list(regions) + d["Ticker"].tolist()
    parents = [""] * len(regions) + d["Region"].tolist()
    values = [int((d["Region"] == r).sum()) for r in regions] + [1] * len(d)
    colours = [0.0] * len(regions) + d[col].tolist()
    customdata = [""] * len(regions) + [f"{v:+.2f}%" for v in d[col]]
    cap = float(np.nanpercentile(np.abs(d[col]), 90)) or 1.0
    fig = go.Figure(
        go.Treemap(
            labels=labels, parents=parents, values=values,
            branchvalues="total",
            marker=dict(
                colors=colours, colorscale=[[0, RED], [0.5, "#1f2937"], [1, GREEN]],
                cmid=0, cmin=-cap, cmax=cap, colorbar=dict(title="% chg"),
                line=dict(width=1, color="#0e1117"),
            ),
            customdata=customdata,
            texttemplate="<b>%{label}</b><br>%{customdata}",
            hovertemplate="%{label}<br>%{customdata}<extra></extra>",
            tiling=dict(pad=2),
        )
    )
    fig.update_layout(
        template="plotly_dark", height=620,
        margin=dict(l=10, r=10, t=40, b=10),
        title=f"Watchlist treemap · coloured by {col} · grouped by market",
    )
    return fig


def price_chart(ticker: str) -> go.Figure | None:
    hist = load_history(ticker)
    if hist.empty:
        return None
    fig = go.Figure(
        go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"],
            low=hist["Low"], close=hist["Close"],
            increasing_line_color=GREEN, decreasing_line_color=RED, name=ticker,
        )
    )
    if "Volume" in hist:
        fig.add_bar(
            x=hist.index, y=hist["Volume"], name="Volume", yaxis="y2",
            marker_color="rgba(148,163,184,0.35)",
        )
    fig.update_layout(
        template="plotly_dark", height=460,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False, title=f"{ticker} — 6 month price & volume",
        yaxis=dict(domain=[0.28, 1.0], title="Price"),
        yaxis2=dict(domain=[0.0, 0.2], title="Vol", showgrid=False),
        showlegend=False,
    )
    return fig


# --------------------------------------------------------------------------- #
# Page setup & styling
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Watchlist Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; max-width: 1500px;}
      h1, h2, h3 {letter-spacing: .3px;}
      [data-testid="stMetricValue"] {font-size: 1.4rem;}

      .hero {
        background: linear-gradient(120deg,#1e3a8a 0%,#6d28d9 55%,#9333ea 100%);
        padding: 1.1rem 1.4rem; border-radius: 16px; margin-bottom: .4rem;
        box-shadow: 0 8px 30px rgba(99,102,241,.25);
      }
      .hero h1 {margin: 0; color: #fff; font-size: 1.9rem;}
      .hero p {margin: .25rem 0 0; color: #e0e7ff; font-size: .9rem;}

      /* KPI cards */
      .kpis {display:flex; gap:.75rem; flex-wrap:wrap; margin:.9rem 0 .2rem;}
      .kpi {flex:1; min-width:150px; background:#161a23; border:1px solid #232838;
            border-radius:14px; padding:.8rem 1rem;}
      .kpi .lab {color:#94a3b8; font-size:.72rem; text-transform:uppercase;
                 letter-spacing:.6px;}
      .kpi .val {font-size:1.5rem; font-weight:700; margin-top:.15rem;}
      .kpi .sub {font-size:.78rem; color:#94a3b8; margin-top:.1rem;}

      /* Ticker card grid */
      .grid {display:grid; gap:.75rem;
             grid-template-columns:repeat(auto-fill,minmax(190px,1fr));}
      .card {background:#161a23; border:1px solid #232838; border-radius:14px;
             padding:.7rem .8rem; transition:transform .12s ease, border-color .12s;}
      .card:hover {transform:translateY(-3px); border-color:#3b455e;}
      .card-head {display:flex; justify-content:space-between; align-items:center;}
      .card .tk {font-weight:700; font-size:1.02rem; color:#f8fafc;}
      .card .flag {font-size:1.05rem;}
      .card .price {font-size:1.25rem; font-weight:600; color:#e5e7eb; margin:.1rem 0;}
      .card .spark {margin:.15rem 0 .35rem;}
      .card .chips {display:flex; gap:.3rem; justify-content:space-between;}
      .chip {flex:1; background:#0f131b; border-radius:8px; padding:.25rem;
             text-align:center;}
      .chip-l {display:block; font-size:.62rem; color:#7c8499; letter-spacing:.5px;}
      .chip-v {display:block; font-size:.82rem; font-weight:700;}
      .card .vol {font-size:.72rem; color:#94a3b8; margin-top:.45rem;}

      .badge {display:inline-block; padding:.12rem .5rem; border-radius:999px;
              font-size:.68rem; font-weight:600; margin-left:.4rem;}
      .badge-reg {background:rgba(245,158,11,.18); color:#fbbf24;
                  border:1px solid rgba(245,158,11,.4);}
      .badge-news {background:rgba(59,130,246,.16); color:#93c5fd;
                   border:1px solid rgba(59,130,246,.4);}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>📈 Watchlist Momentum Dashboard</h1>
      <p>3-day · 1-week · 1-month price moves, volume shifts, trend sparklines and
      the latest news, releases & regulatory flags. Data via Yahoo Finance —
      cached for 15 minutes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    focus_window = st.selectbox(
        "Focus window", list(WINDOWS), index=1,
        help="Drives the KPIs, sorting default, treemap & movers colour.",
    )
    sort_by = st.selectbox("Sort by", list(WINDOWS) + ["Volume Δ%", "Ticker"],
                           index=list(WINDOWS).index(focus_window))
    ascending = st.toggle("Ascending", value=False)
    search = st.text_input("🔍 Filter tickers", placeholder="e.g. NVDA, ASML")
    min_abs = st.slider("Min |move| % (focus window)", 0.0, 25.0, 0.0, 0.5)
    st.markdown("---")
    st.caption(f"Tracking **{len(TICKERS)}** tickers.")

with st.spinner("Fetching market data…"):
    metrics = build_metrics(tuple(TICKERS))

if metrics.empty:
    st.error("No price data could be loaded. Try refreshing in a moment.")
    st.stop()

failed = sorted(set(TICKERS) - set(metrics["Ticker"]))

# Apply sidebar filters (used by card grid / table views)
view = metrics.copy()
if search.strip():
    terms = [t.strip().upper() for t in search.split(",") if t.strip()]
    view = view[view["Ticker"].str.upper().str.contains("|".join(map(re.escape, terms)))]
if min_abs > 0:
    view = view[view[focus_window].abs() >= min_abs]
view = view.sort_values(sort_by, ascending=ascending, na_position="last")

# --------------------------------------------------------------------------- #
# KPI strip
# --------------------------------------------------------------------------- #
series = metrics[focus_window]
gainers = int((series > 0).sum())
losers = int((series < 0).sum())
avg_move = series.mean(skipna=True)
best = metrics.loc[series.idxmax()] if series.notna().any() else None
worst = metrics.loc[series.idxmin()] if series.notna().any() else None

kpi_cards = [
    ("Tickers loaded", f"{len(metrics)}/{len(TICKERS)}", f"{len(failed)} unresolved", FLAT),
    ("Gainers", str(gainers), f"{focus_window}", GREEN),
    ("Losers", str(losers), f"{focus_window}", RED),
    ("Avg move", f"{avg_move:+.2f}%" if pd.notna(avg_move) else "—", focus_window, _colour_for(avg_move)),
]
if best is not None:
    kpi_cards.append(("Top mover", best["Ticker"], f"{best[focus_window]:+.2f}%", GREEN))
if worst is not None:
    kpi_cards.append(("Worst mover", worst["Ticker"], f"{worst[focus_window]:+.2f}%", RED))

kpi_html = "".join(
    f'<div class="kpi"><div class="lab">{lab}</div>'
    f'<div class="val" style="color:{col}">{val}</div>'
    f'<div class="sub">{sub}</div></div>'
    for lab, val, sub, col in kpi_cards
)
st.markdown(f'<div class="kpis">{kpi_html}</div>', unsafe_allow_html=True)
st.plotly_chart(breadth_bar(series), width="stretch",
                config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_cards, tab_table, tab_movers, tab_tree, tab_detail = st.tabs(
    ["🗂️ Cards", "📋 Table", "📊 Movers", "🌳 Treemap", "🔎 Detail & news"]
)

# ---- Card grid ------------------------------------------------------------ #
with tab_cards:
    st.caption(f"Showing **{len(view)}** of {len(metrics)} tickers · sorted by {sort_by}.")
    if view.empty:
        st.info("No tickers match the current filters.")
    else:
        cards = "".join(card_html(r) for _, r in view.iterrows())
        st.markdown(f'<div class="grid">{cards}</div>', unsafe_allow_html=True)
    if failed:
        st.caption("⚠️ No data returned for: " + ", ".join(failed))

# ---- Table ---------------------------------------------------------------- #
with tab_table:
    cols = ["Ticker", "Flag", "Region", "Price"] + PCT_COLS
    st.dataframe(
        style_table(view[cols]),
        width="stretch", hide_index=True,
        height=min(60 + 35 * len(view), 900),
    )

# ---- Movers --------------------------------------------------------------- #
with tab_movers:
    st.plotly_chart(movers_bar(metrics, focus_window), width="stretch")

# ---- Treemap -------------------------------------------------------------- #
with tab_tree:
    st.plotly_chart(treemap(metrics, focus_window), width="stretch")

# ---- Ticker detail + news ------------------------------------------------- #
with tab_detail:
    default_idx = view["Ticker"].tolist().index(best["Ticker"]) if (
        best is not None and best["Ticker"] in view["Ticker"].values) else 0
    options = view["Ticker"].tolist() or metrics["Ticker"].tolist()
    choice = st.selectbox("Select a ticker", options,
                          index=min(default_idx, len(options) - 1))
    row = metrics[metrics["Ticker"] == choice].iloc[0]

    st.markdown(f"### {row['Flag']} {choice} — {company_name(choice)}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Price", f"{row['Price']:,.2f}")
    c2.metric("3-day", f"{row['3D %']:+.2f}%" if pd.notna(row["3D %"]) else "—")
    c3.metric("1-week", f"{row['1W %']:+.2f}%" if pd.notna(row["1W %"]) else "—")
    c4.metric("1-month", f"{row['1M %']:+.2f}%" if pd.notna(row["1M %"]) else "—")
    c5.metric("Volume Δ", f"{row['Volume Δ%']:+.1f}%" if pd.notna(row["Volume Δ%"]) else "—")

    fig = price_chart(choice)
    if fig is not None:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No chart data available for this ticker.")

    st.subheader("📰 News, releases & regulatory updates")
    news = load_news(choice)
    if not news:
        st.info("No recent news found for this ticker.")
    else:
        only_reg = st.toggle("Show regulatory / filings only", value=False)
        reg_count = sum(1 for n in news if n["regulatory"])
        st.caption(f"{len(news)} items · {reg_count} flagged as regulatory / filings.")
        for item in news:
            if only_reg and not item["regulatory"]:
                continue
            badge = (
                '<span class="badge badge-reg">⚖️ Regulatory / filing</span>'
                if item["regulatory"]
                else '<span class="badge badge-news">📰 News</span>'
            )
            title = html.escape(item["title"])
            if item["url"]:
                head = f'<a href="{html.escape(item["url"])}" target="_blank">{title}</a>'
            else:
                head = title
            st.markdown(f"**{head}** {badge}", unsafe_allow_html=True)
            meta = " · ".join(
                x for x in [item["publisher"], _fmt_published(item["published"]), item["type"]] if x
            )
            if meta:
                st.caption(meta)
            if item["summary"]:
                st.write(item["summary"])
            st.markdown("---")

st.caption(
    "ℹ️ Informational only — not investment advice. Regulatory flags are keyword "
    "heuristics, not an exhaustive feed. Yahoo Finance data may be delayed and "
    "occasional tickers may fail to resolve."
)
