"""
Watchlist Dashboard
====================
A visual Streamlit dashboard showing momentum (3-day / 1-week / 1-month price
moves), volume shifts and the latest news / regulatory headlines for a custom
stock watchlist.

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

# --------------------------------------------------------------------------- #
# Data layer (cached)
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=900, show_spinner=False)
def load_prices(tickers: tuple[str, ...]) -> pd.DataFrame:
    """Batch-download ~3 months of OHLCV for every ticker."""
    data = yf.download(
        list(tickers),
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    return data


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


@st.cache_data(ttl=900, show_spinner=False)
def build_metrics(tickers: tuple[str, ...]) -> pd.DataFrame:
    data = load_prices(tickers)
    rows = []
    for t in tickers:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            continue
        row = {
            "Ticker": t,
            "Price": close.iloc[-1],
            "Volume Δ%": _volume_change(volume),
        }
        for label, periods in WINDOWS.items():
            row[label] = _pct_change(close, periods)
        rows.append(row)
    df = pd.DataFrame(rows)
    return df


@st.cache_data(ttl=900, show_spinner=False)
def load_history(ticker: str) -> pd.DataFrame:
    return yf.Ticker(ticker).history(period="6mo", auto_adjust=True)


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


@st.cache_data(ttl=900, show_spinner=False)
def load_news(ticker: str) -> list[dict]:
    """Return a normalised list of recent news items for a ticker."""
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
        link = (c.get("clickThroughUrl") or c.get("canonicalUrl") or {})
        items.append(
            {
                "title": c.get("title", "Untitled"),
                "summary": _clean_html(c.get("summary") or c.get("description") or ""),
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
                "type": c.get("contentType", ""),
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


def style_table(df: pd.DataFrame):
    pct_cols = list(WINDOWS) + ["Volume Δ%"]

    def colour(val):
        if pd.isna(val):
            return "color:#666"
        if val > 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(38,166,91,{0.15 + 0.45 * shade});color:#eafff2"
        if val < 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(231,76,60,{0.15 + 0.45 * shade});color:#ffecec"
        return "color:#ccc"

    styler = (
        df.style.map(colour, subset=pct_cols)
        .format({"Price": "{:,.2f}", **{c: "{:+.2f}%" for c in pct_cols}}, na_rep="—")
    )
    return styler


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
            increasing_line_color="#26a65b",
            decreasing_line_color="#e74c3c",
            name=ticker,
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        title=f"{ticker} — 6 month price",
    )
    return fig


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Watchlist Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem;}
      h1, h2, h3 {letter-spacing: .3px;}
      [data-testid="stMetricValue"] {font-size: 1.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 Watchlist Momentum Dashboard")
st.caption(
    "3-day, 1-week and 1-month price moves, volume shifts and the latest "
    "headlines for your watchlist. Data via Yahoo Finance · cached for 15 min."
)

with st.sidebar:
    st.header("Controls")
    if st.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    sort_by = st.selectbox("Sort by", list(WINDOWS) + ["Volume Δ%", "Ticker"], index=1)
    ascending = st.toggle("Ascending", value=False)
    st.markdown("---")
    st.caption(f"Tracking **{len(TICKERS)}** tickers.")

with st.spinner("Fetching market data…"):
    metrics = build_metrics(tuple(TICKERS))

if metrics.empty:
    st.error("No price data could be loaded. Try refreshing in a moment.")
    st.stop()

failed = sorted(set(TICKERS) - set(metrics["Ticker"]))

# ---- KPI strip ------------------------------------------------------------ #
primary = "1W %"
gainers = metrics[metrics[primary] > 0]
losers = metrics[metrics[primary] < 0]
best = metrics.loc[metrics[primary].idxmax()] if metrics[primary].notna().any() else None
worst = metrics.loc[metrics[primary].idxmin()] if metrics[primary].notna().any() else None

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Tickers loaded", f"{len(metrics)}/{len(TICKERS)}")
k2.metric("Gainers (1W)", len(gainers))
k3.metric("Losers (1W)", len(losers))
if best is not None:
    k4.metric("Top mover (1W)", best["Ticker"], f"{best[primary]:+.2f}%")
if worst is not None:
    k5.metric("Worst mover (1W)", worst["Ticker"], f"{worst[primary]:+.2f}%")

st.markdown("")

tab_overview, tab_heatmap, tab_detail = st.tabs(
    ["📋 Overview", "🌡️ Heatmap", "🔎 Ticker detail & news"]
)

# ---- Overview table ------------------------------------------------------- #
with tab_overview:
    table = metrics.sort_values(sort_by, ascending=ascending, na_position="last")
    st.dataframe(
        style_table(table),
        width="stretch",
        hide_index=True,
        height=min(60 + 35 * len(table), 900),
    )
    if failed:
        st.caption("⚠️ No data returned for: " + ", ".join(failed))

# ---- Heatmap -------------------------------------------------------------- #
with tab_heatmap:
    hm = metrics.set_index("Ticker")[list(WINDOWS)]
    fig = go.Figure(
        go.Heatmap(
            z=hm.values,
            x=list(WINDOWS),
            y=hm.index,
            colorscale=[[0, "#e74c3c"], [0.5, "#1c1c24"], [1, "#26a65b"]],
            zmid=0,
            text=np.round(hm.values, 1),
            texttemplate="%{text}%",
            colorbar=dict(title="% change"),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=max(400, 22 * len(hm)),
        margin=dict(l=10, r=10, t=30, b=10),
        title="Percentage change by time window",
    )
    st.plotly_chart(fig, width="stretch")

# ---- Ticker detail + news ------------------------------------------------- #
with tab_detail:
    choice = st.selectbox("Select a ticker", metrics["Ticker"].tolist())
    row = metrics[metrics["Ticker"] == choice].iloc[0]

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

    st.subheader("📰 Latest news, releases & regulatory updates")
    news = load_news(choice)
    if not news:
        st.info("No recent news found for this ticker.")
    for item in news:
        meta = " · ".join(
            x for x in [item["publisher"], _fmt_published(item["published"]), item["type"]] if x
        )
        if item["url"]:
            st.markdown(f"**[{item['title']}]({item['url']})**")
        else:
            st.markdown(f"**{item['title']}**")
        if meta:
            st.caption(meta)
        if item["summary"]:
            st.write(item["summary"])
        st.markdown("---")

st.caption(
    "ℹ️ Informational only — not investment advice. Yahoo Finance data may be "
    "delayed and occasional tickers may fail to resolve."
)
