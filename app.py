"""
Watchlist Momentum Dashboard
============================
A visual, interactive Streamlit dashboard showing momentum (3-day / 1-week /
1-month price moves), volume shifts and categorised news / regulatory headlines
for a custom stock watchlist.

Run with:
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

# Map a ticker suffix to a friendly market / region label.
SUFFIX_REGION = {
    ".NS": "🇮🇳 India (NSE)",
    ".BO": "🇮🇳 India (BSE)",
    ".L": "🇬🇧 UK (LSE)",
    ".IL": "🇬🇧 UK (IOB)",
}

# --------------------------------------------------------------------------- #
# Theme
# --------------------------------------------------------------------------- #
GREEN = "#22c55e"
RED = "#ef4444"
PLOT_BG = "#0e1117"

st.set_page_config(
    page_title="Watchlist Momentum Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


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


def _region(ticker: str) -> str:
    for suffix, label in SUFFIX_REGION.items():
        if ticker.endswith(suffix):
            return label
    return "🇺🇸 US / Global"


@st.cache_data(ttl=900, show_spinner=False)
def build_metrics(tickers: tuple[str, ...]) -> pd.DataFrame:
    data = load_prices(tickers)
    rows = []
    for t in tickers:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            continue
        # 30-session spark line of closes for the overview mini-charts.
        spark = close.iloc[-30:].tolist()
        row = {
            "Ticker": t,
            "Region": _region(t),
            "Price": close.iloc[-1],
            "Volume Δ%": _volume_change(volume),
            "Trend": spark,
            "_last_vol": volume.iloc[-1] if not volume.empty else np.nan,
        }
        for label, periods in WINDOWS.items():
            row[label] = _pct_change(close, periods)
        rows.append(row)
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(period="6mo", auto_adjust=True)


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


# Keyword buckets used to tag each headline.
NEWS_CATEGORIES = [
    ("Regulatory", "⚖️", "#a855f7", (
        "regulat", "sec ", "fda", "approv", "lawsuit", "court", "antitrust",
        "settle", "fine", "investigat", "compliance", "ruling", "sanction",
        "tariff", "probe", "patent", "ftc", "doj",
    )),
    ("Earnings", "💰", "#f59e0b", (
        "earning", "revenue", "guidance", "profit", "loss", "quarter",
        "results", "eps", "dividend", "forecast", "outlook", "sales",
    )),
    ("Analyst", "🎯", "#3b82f6", (
        "upgrade", "downgrade", "price target", "rating", "analyst",
        "buy", "sell", "overweight", "underweight", "initiat",
    )),
    ("Deal / M&A", "🤝", "#14b8a6", (
        "acqui", "merger", "buyout", "stake", "partnership", "contract",
        "deal", "agreement", "joint venture", "ipo", "spinoff",
    )),
]


def _categorise(title: str, summary: str) -> tuple[str, str, str]:
    """Return (label, emoji, colour) for a headline based on keywords."""
    text = f"{title} {summary}".lower()
    for label, emoji, colour, keywords in NEWS_CATEGORIES:
        if any(k in text for k in keywords):
            return label, emoji, colour
    return "News", "📰", "#64748b"


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
        label, emoji, colour = _categorise(title, summary)
        items.append(
            {
                "title": title,
                "summary": summary,
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
                "category": label,
                "emoji": emoji,
                "colour": colour,
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
        return ts.strftime("%b %d, %Y · %H:%M UTC")
    except (ValueError, AttributeError):
        return str(value)


def style_table(df: pd.DataFrame):
    pct_cols = list(WINDOWS) + ["Volume Δ%"]

    def colour(val):
        if pd.isna(val):
            return "color:#64748b"
        if val > 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(34,197,94,{0.12 + 0.5 * shade});color:#eafff2"
        if val < 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(239,68,68,{0.12 + 0.5 * shade});color:#ffecec"
        return "color:#cbd5e1"

    return (
        df.style.map(colour, subset=pct_cols)
        .format({"Price": "{:,.2f}", **{c: "{:+.2f}%" for c in pct_cols}}, na_rep="—")
    )


def price_chart(ticker: str) -> go.Figure | None:
    hist = load_history(ticker)
    if hist.empty:
        return None

    fig = go.Figure(
        go.Candlestick(
            x=hist.index,
            open=hist["Open"],
            high=hist["High"],
            low=hist["Low"],
            close=hist["Close"],
            increasing_line_color=GREEN,
            decreasing_line_color=RED,
            name=ticker,
        )
    )
    # Light 20-day moving average overlay.
    if len(hist) >= 20:
        ma = hist["Close"].rolling(20).mean()
        fig.add_trace(
            go.Scatter(
                x=hist.index, y=ma, mode="lines", name="20-day MA",
                line=dict(color="#fbbf24", width=1.5),
            )
        )
    fig.update_layout(
        template="plotly_dark",
        height=440,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        title=f"{ticker} — 6 month price",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def treemap(df: pd.DataFrame, metric: str) -> go.Figure:
    """A heat-treemap: tile size = magnitude of move, colour = direction,
    grouped by listing region."""
    d = df.dropna(subset=[metric]).copy()
    d["abs"] = d[metric].abs().clip(lower=0.1)

    region_names = list(d["Region"].unique())
    # Region "parent" tiles first, then individual ticker tiles.
    labels = region_names + list(d["Ticker"])
    parents = [""] * len(region_names) + list(d["Region"])
    values = (
        [d.loc[d["Region"] == r, "abs"].sum() for r in region_names]
        + list(d["abs"])
    )
    colors = [0.0] * len(region_names) + list(d[metric])
    text = [""] * len(region_names) + [f"{v:+.1f}%" for v in d[metric]]

    fig = go.Figure(
        go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colors=colors,
                colorscale=[[0, RED], [0.5, "#1e293b"], [1, GREEN]],
                cmid=0,
                colorbar=dict(title="% chg"),
                line=dict(width=1, color=PLOT_BG),
            ),
            text=text,
            texttemplate="<b>%{label}</b><br>%{text}",
            hovertemplate="<b>%{label}</b><br>%{text}<extra></extra>",
            tiling=dict(pad=2),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=620,
        margin=dict(l=8, r=8, t=40, b=8),
        title=f"Watchlist map — tile size = magnitude of move · colour = {metric}",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# --------------------------------------------------------------------------- #
# Global styling
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; max-width: 1500px;}
      h1, h2, h3 {letter-spacing: .2px;}
      [data-testid="stMetricValue"] {font-size: 1.45rem;}
      /* hero banner */
      .hero {
        background: linear-gradient(110deg, #1e3a8a 0%, #6d28d9 55%, #0f766e 100%);
        padding: 1.6rem 1.8rem; border-radius: 16px; margin-bottom: 1.2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,.35);
      }
      .hero h1 {color:#fff; margin:0; font-size: 2.0rem;}
      .hero p {color:#dbeafe; margin:.35rem 0 0; font-size:.95rem;}
      /* KPI cards */
      .kpi {
        background: #161b27; border:1px solid #232a39; border-radius:14px;
        padding: 1rem 1.1rem; height: 100%;
      }
      .kpi .label {color:#94a3b8; font-size:.8rem; text-transform:uppercase;
        letter-spacing:.6px;}
      .kpi .value {font-size:1.7rem; font-weight:700; margin-top:.2rem;}
      .kpi .sub {font-size:.85rem; margin-top:.15rem;}
      .pos {color:#22c55e;} .neg {color:#ef4444;} .neu {color:#cbd5e1;}
      /* news card */
      .news-card {
        background:#141925; border:1px solid #232a39; border-left-width:4px;
        border-radius:10px; padding:.85rem 1rem; margin-bottom:.7rem;
      }
      .news-card a {color:#e2e8f0; text-decoration:none; font-weight:600;
        font-size:1.02rem;}
      .news-card a:hover {color:#60a5fa;}
      .news-meta {color:#94a3b8; font-size:.8rem; margin:.3rem 0;}
      .news-summary {color:#cbd5e1; font-size:.9rem;}
      .chip {display:inline-block; padding:.12rem .55rem; border-radius:999px;
        font-size:.72rem; font-weight:700; color:#fff;}
    </style>
    """,
    unsafe_allow_html=True,
)


def kpi_card(label: str, value: str, sub: str = "", tone: str = "neu") -> str:
    sub_html = f'<div class="sub {tone}">{sub}</div>' if sub else ""
    return (
        f'<div class="kpi"><div class="label">{label}</div>'
        f'<div class="value {tone}">{value}</div>{sub_html}</div>'
    )


# --------------------------------------------------------------------------- #
# App body
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="hero">
      <h1>📈 Watchlist Momentum Dashboard</h1>
      <p>3-day, 1-week &amp; 1-month price moves · volume shifts · categorised
      news, regulatory updates &amp; market-moving headlines — refreshed every 15&nbsp;min.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh data", width="stretch", type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    sort_by = st.selectbox("Sort table by", list(WINDOWS) + ["Volume Δ%", "Ticker"], index=1)
    ascending = st.toggle("Ascending order", value=False)
    map_metric = st.selectbox("Heat-map / treemap window", list(WINDOWS), index=1)
    st.markdown("---")

with st.spinner("Fetching market data…"):
    metrics = build_metrics(tuple(TICKERS))

if metrics.empty:
    st.error("No price data could be loaded. Try refreshing in a moment.")
    st.stop()

# Region filter (built now that we have data and know the regions present).
regions = sorted(metrics["Region"].unique())
with st.sidebar:
    chosen_regions = st.multiselect("Filter by region", regions, default=regions)
    st.caption(f"Tracking **{len(TICKERS)}** tickers via Yahoo Finance.")
view = metrics[metrics["Region"].isin(chosen_regions)] if chosen_regions else metrics

failed = sorted(set(TICKERS) - set(metrics["Ticker"]))

# ---- KPI strip ------------------------------------------------------------ #
primary = "1W %"
gainers = view[view[primary] > 0]
losers = view[view[primary] < 0]
best = view.loc[view[primary].idxmax()] if view[primary].notna().any() else None
worst = view.loc[view[primary].idxmin()] if view[primary].notna().any() else None
avg_move = view[primary].mean()

cols = st.columns(5)
cols[0].markdown(
    kpi_card("Tickers loaded", f"{len(metrics)}/{len(TICKERS)}",
             f"{len(failed)} unresolved" if failed else "all resolved",
             "neg" if failed else "pos"),
    unsafe_allow_html=True,
)
cols[1].markdown(
    kpi_card("Gainers · Losers (1W)", f"{len(gainers)} / {len(losers)}",
             f"avg {avg_move:+.2f}%" if pd.notna(avg_move) else "",
             "pos" if (avg_move or 0) >= 0 else "neg"),
    unsafe_allow_html=True,
)
if best is not None:
    cols[2].markdown(
        kpi_card("🚀 Top mover (1W)", best["Ticker"], f"{best[primary]:+.2f}%", "pos"),
        unsafe_allow_html=True,
    )
if worst is not None:
    cols[3].markdown(
        kpi_card("🔻 Worst mover (1W)", worst["Ticker"], f"{worst[primary]:+.2f}%", "neg"),
        unsafe_allow_html=True,
    )
if view["Volume Δ%"].notna().any():
    vspike = view.loc[view["Volume Δ%"].idxmax()]
    cols[4].markdown(
        kpi_card("📊 Volume spike", vspike["Ticker"], f"{vspike['Volume Δ%']:+.0f}% vs 20d",
                 "pos" if vspike["Volume Δ%"] >= 0 else "neg"),
        unsafe_allow_html=True,
    )

st.markdown("")

tab_overview, tab_map, tab_heatmap, tab_detail = st.tabs(
    ["📋 Overview", "🗺️ Treemap", "🌡️ Heatmap", "🔎 Ticker detail & news"]
)

# ---- Overview table (with sparklines) ------------------------------------- #
with tab_overview:
    table = view.sort_values(sort_by, ascending=ascending, na_position="last")
    display = table[["Ticker", "Region", "Price", "Trend",
                     "3D %", "1W %", "1M %", "Volume Δ%"]]
    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        height=min(80 + 35 * len(display), 900),
        column_config={
            "Trend": st.column_config.LineChartColumn(
                "30d trend", y_min=None, y_max=None, width="small"
            ),
            "Price": st.column_config.NumberColumn("Price", format="%.2f"),
            "3D %": st.column_config.NumberColumn("3D %", format="%+.2f%%"),
            "1W %": st.column_config.NumberColumn("1W %", format="%+.2f%%"),
            "1M %": st.column_config.NumberColumn("1M %", format="%+.2f%%"),
            "Volume Δ%": st.column_config.NumberColumn("Volume Δ%", format="%+.1f%%"),
        },
    )
    st.caption("Sparkline = last 30 trading days of closing price. "
               "Sort & filter via the sidebar.")
    if failed:
        st.caption("⚠️ No data returned for: " + ", ".join(failed))

# ---- Treemap -------------------------------------------------------------- #
with tab_map:
    st.plotly_chart(treemap(view, map_metric), width="stretch")
    st.caption("Bigger tiles = larger absolute move · green up, red down. "
               "Grouped by listing region. Change the window in the sidebar.")

# ---- Heatmap -------------------------------------------------------------- #
with tab_heatmap:
    order = view.sort_values(map_metric, ascending=False, na_position="last")
    hm = order.set_index("Ticker")[list(WINDOWS)]
    fig = go.Figure(
        go.Heatmap(
            z=hm.values,
            x=list(WINDOWS),
            y=hm.index,
            colorscale=[[0, RED], [0.5, "#161b27"], [1, GREEN]],
            zmid=0,
            text=np.round(hm.values, 1),
            texttemplate="%{text}%",
            hovertemplate="%{y} · %{x}: %{z:.2f}%<extra></extra>",
            colorbar=dict(title="% change"),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=max(450, 21 * len(hm)),
        margin=dict(l=10, r=10, t=40, b=10),
        title="Percentage change by time window (sorted by selected window)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")

# ---- Ticker detail + news ------------------------------------------------- #
with tab_detail:
    choice = st.selectbox("Select a ticker", view["Ticker"].tolist())
    row = view[view["Ticker"] == choice].iloc[0]

    c = st.columns(5)
    c[0].metric("Price", f"{row['Price']:,.2f}")
    c[1].metric("3-day", f"{row['3D %']:+.2f}%" if pd.notna(row["3D %"]) else "—")
    c[2].metric("1-week", f"{row['1W %']:+.2f}%" if pd.notna(row["1W %"]) else "—")
    c[3].metric("1-month", f"{row['1M %']:+.2f}%" if pd.notna(row["1M %"]) else "—")
    c[4].metric("Volume Δ", f"{row['Volume Δ%']:+.1f}%" if pd.notna(row["Volume Δ%"]) else "—")

    fig = price_chart(choice)
    if fig is not None:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No chart data available for this ticker.")

    st.subheader("📰 News, releases & regulatory updates")
    news = load_news(choice)
    if not news:
        st.info("No recent news found for this ticker via Yahoo Finance.")
    else:
        cats = sorted({n["category"] for n in news})
        picked = st.multiselect("Filter headlines by type", cats, default=cats)
        shown = [n for n in news if n["category"] in picked]
        if not shown:
            st.caption("No headlines match the selected filters.")
        for item in shown:
            meta = " · ".join(
                x for x in [item["publisher"], _fmt_published(item["published"])] if x
            )
            title_html = (
                f'<a href="{item["url"]}" target="_blank">{html.escape(item["title"])}</a>'
                if item["url"]
                else f'<span style="color:#e2e8f0;font-weight:600">{html.escape(item["title"])}</span>'
            )
            summary_html = (
                f'<div class="news-summary">{html.escape(item["summary"])}</div>'
                if item["summary"] else ""
            )
            st.markdown(
                f'<div class="news-card" style="border-left-color:{item["colour"]}">'
                f'<span class="chip" style="background:{item["colour"]}">'
                f'{item["emoji"]} {item["category"]}</span> {title_html}'
                f'<div class="news-meta">{html.escape(meta)}</div>'
                f'{summary_html}</div>',
                unsafe_allow_html=True,
            )

st.markdown("")
st.caption(
    "ℹ️ Informational only — not investment advice. Yahoo Finance data may be "
    "delayed and occasional tickers may fail to resolve. News categories are "
    "inferred from headline keywords and may be approximate."
)
