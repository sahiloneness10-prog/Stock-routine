"""
Watchlist Momentum Dashboard
============================
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
from plotly.subplots import make_subplots

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

# Map a ticker's Yahoo suffix to a readable market / region label.
MARKETS = {
    ".NS": "🇮🇳 NSE",
    ".BO": "🇮🇳 BSE",
    ".L": "🇬🇧 LSE",
    ".IL": "🌐 IOB",
    ".DE": "🇩🇪 XETRA",
    ".PA": "🇫🇷 EPA",
    ".TO": "🇨🇦 TSX",
    ".HK": "🇭🇰 HKEX",
}

# Keyword buckets used to tag news headlines by what likely moved the price.
NEWS_TAGS = [
    ("🏛️ Regulatory", "#8e44ad", (
        "fda", "sec ", "regulat", "approval", "antitrust", "lawsuit", "court",
        "investigation", "fine", "sanction", "compliance", "patent", "ruling",
        "probe", "subpoena", "settlement", "recall", "ftc", "doj", "tariff",
    )),
    ("📊 Earnings", "#2980b9", (
        "earnings", "revenue", "profit", "guidance", "quarter", "results",
        "eps", "forecast", "outlook", "margin", "sales", "loss",
    )),
    ("🤝 M&A", "#16a085", (
        "acqui", "merger", "buyout", "takeover", "stake", "deal", "spin-off",
        "divest", "bid for",
    )),
    ("🎯 Analyst", "#d35400", (
        "upgrade", "downgrade", "rating", "price target", "analyst",
        "initiat", "overweight", "underweight", "buy rating", "sell rating",
    )),
]


def market_of(ticker: str) -> str:
    for suffix, label in MARKETS.items():
        if ticker.endswith(suffix):
            return label
    return "🇺🇸 US"


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
            "Market": market_of(t),
            "Price": close.iloc[-1],
            "Volume Δ%": _volume_change(volume),
            # Last ~30 closes power the inline sparkline.
            "Trend": close.tail(30).tolist(),
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


def _tag_news(title: str, summary: str) -> tuple[str, str]:
    """Return (label, colour) for a headline based on keyword matching."""
    blob = f"{title} {summary}".lower()
    for label, colour, keywords in NEWS_TAGS:
        if any(kw in blob for kw in keywords):
            return label, colour
    return "📰 General", "#566573"


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
        title = c.get("title", "Untitled")
        summary = _clean_html(c.get("summary") or c.get("description") or "")
        tag, colour = _tag_news(title, summary)
        items.append(
            {
                "title": title,
                "summary": summary,
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
                "type": c.get("contentType", ""),
                "tag": tag,
                "tag_colour": colour,
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


def sparkline(values: list[float], up: bool) -> go.Figure:
    colour = "#26d07c" if up else "#ff5c5c"
    fig = go.Figure(go.Scatter(y=values, mode="lines", line=dict(color=colour, width=2)))
    fig.add_trace(
        go.Scatter(
            y=values, mode="lines", fill="tozeroy", line=dict(width=0),
            fillcolor=f"rgba({'38,208,124' if up else '255,92,92'},0.12)",
        )
    )
    fig.update_layout(
        height=70, margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def mover_card(col, row: pd.Series, window: str) -> None:
    val = row[window]
    up = val >= 0
    arrow = "▲" if up else "▼"
    colour = "#26d07c" if up else "#ff5c5c"
    with col:
        st.markdown(
            f"""
            <div class="mover-card">
              <div class="mover-top">
                <span class="mover-ticker">{row['Ticker']}</span>
                <span class="mover-market">{row['Market']}</span>
              </div>
              <div class="mover-pct" style="color:{colour}">{arrow} {val:+.2f}%</div>
              <div class="mover-price">Last {row['Price']:,.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if isinstance(row["Trend"], list) and len(row["Trend"]) > 1:
            st.plotly_chart(
                sparkline(row["Trend"], up),
                width="stretch",
                config={"displayModeBar": False},
            )


def style_table(df: pd.DataFrame):
    def colour(val):
        if pd.isna(val):
            return "color:#666"
        if val > 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(38,208,124,{0.15 + 0.45 * shade});color:#eafff2"
        if val < 0:
            shade = min(abs(val) / 12, 1)
            return f"background-color:rgba(255,92,92,{0.15 + 0.45 * shade});color:#ffecec"
        return "color:#ccc"

    return (
        df.style.map(colour, subset=PCT_COLS)
        .format({"Price": "{:,.2f}", **{c: "{:+.2f}%" for c in PCT_COLS}}, na_rep="—")
    )


def detail_chart(ticker: str) -> go.Figure | None:
    hist = load_history(ticker)
    if hist.empty:
        return None
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )
    fig.add_trace(
        go.Candlestick(
            x=hist.index, open=hist["Open"], high=hist["High"],
            low=hist["Low"], close=hist["Close"],
            increasing_line_color="#26d07c", decreasing_line_color="#ff5c5c",
            name="Price",
        ),
        row=1, col=1,
    )
    vol_colours = np.where(hist["Close"] >= hist["Open"], "#26d07c", "#ff5c5c")
    fig.add_trace(
        go.Bar(x=hist.index, y=hist["Volume"], marker_color=vol_colours, name="Volume"),
        row=2, col=1,
    )
    fig.update_layout(
        template="plotly_dark", height=520,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False, showlegend=False,
        title=f"{ticker} — 6 month price & volume",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Watchlist Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; max-width: 1500px;}
      h1, h2, h3 {letter-spacing: .3px;}
      [data-testid="stMetricValue"] {font-size: 1.4rem;}
      .hero {
        background: linear-gradient(135deg, #1b2735 0%, #283e51 55%, #0f2027 100%);
        border-radius: 16px; padding: 1.6rem 2rem; margin-bottom: 1.2rem;
        border: 1px solid rgba(255,255,255,0.06);
      }
      .hero h1 {margin: 0; font-size: 2.1rem; color: #f5f7fa;}
      .hero p {margin: .4rem 0 0; color: #aab7c4; font-size: .95rem;}
      .mover-card {
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07);
        border-radius: 12px; padding: .8rem 1rem .2rem; margin-bottom: -.4rem;
      }
      .mover-top {display:flex; justify-content:space-between; align-items:center;}
      .mover-ticker {font-weight: 700; font-size: 1.05rem; color:#f5f7fa;}
      .mover-market {font-size: .72rem; color:#8fa3b8;}
      .mover-pct {font-size: 1.5rem; font-weight: 700; margin-top: .2rem;}
      .mover-price {font-size: .8rem; color:#8fa3b8;}
      .news-tag {
        display:inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: .72rem; font-weight:600; color:#fff; margin-bottom:.3rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>📈 Watchlist Momentum Dashboard</h1>
      <p>3-day, 1-week and 1-month price moves, volume shifts and the latest
      news, releases &amp; regulatory updates for your watchlist.
      Data via Yahoo Finance · cached for 15 minutes.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    sort_by = st.selectbox("Sort by", PCT_COLS + ["Ticker"], index=1)
    ascending = st.toggle("Ascending", value=False)
    st.markdown("---")
    market_filter: list[str] = []  # populated after metrics load
    st.caption(f"Tracking **{len(TICKERS)}** tickers.")

with st.spinner("Fetching market data…"):
    metrics = build_metrics(tuple(TICKERS))

if metrics.empty:
    st.error("No price data could be loaded. Try refreshing in a moment.")
    st.stop()

failed = sorted(set(TICKERS) - set(metrics["Ticker"]))

# ---- Sidebar market filter (needs loaded data) --------------------------- #
with st.sidebar:
    all_markets = sorted(metrics["Market"].unique())
    market_filter = st.multiselect("Markets", all_markets, default=all_markets)

view = metrics[metrics["Market"].isin(market_filter)] if market_filter else metrics
if view.empty:
    st.warning("No tickers match the selected markets.")
    st.stop()

# ---- KPI strip ----------------------------------------------------------- #
primary = "1W %"
gainers = view[view[primary] > 0]
losers = view[view[primary] < 0]
best = view.loc[view[primary].idxmax()] if view[primary].notna().any() else None
worst = view.loc[view[primary].idxmin()] if view[primary].notna().any() else None
breadth = (len(gainers) / max(len(gainers) + len(losers), 1)) * 100

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Tickers loaded", f"{len(view)}/{len(TICKERS)}")
k2.metric("Gainers (1W)", len(gainers), f"{breadth:.0f}% breadth")
k3.metric("Losers (1W)", len(losers))
if best is not None:
    k4.metric("Top mover (1W)", best["Ticker"], f"{best[primary]:+.2f}%")
if worst is not None:
    k5.metric("Worst mover (1W)", worst["Ticker"], f"{worst[primary]:+.2f}%")

st.markdown("")

tab_movers, tab_overview, tab_heatmap, tab_detail = st.tabs(
    ["🚀 Movers", "📋 Overview", "🌡️ Heatmap", "🔎 Ticker detail & news"]
)

# ---- Movers -------------------------------------------------------------- #
with tab_movers:
    mover_window = st.radio(
        "Ranking window", list(WINDOWS), index=1, horizontal=True, key="mover_win"
    )
    ranked = view.dropna(subset=[mover_window]).sort_values(mover_window, ascending=False)

    st.markdown("#### 🟢 Top gainers")
    top = ranked.head(5)
    if top.empty:
        st.info("No gainers in the selected window.")
    else:
        for col, (_, r) in zip(st.columns(len(top)), top.iterrows()):
            mover_card(col, r, mover_window)

    st.markdown("#### 🔴 Top losers")
    bottom = ranked.tail(5).iloc[::-1]
    if bottom.empty:
        st.info("No losers in the selected window.")
    else:
        for col, (_, r) in zip(st.columns(len(bottom)), bottom.iterrows()):
            mover_card(col, r, mover_window)

# ---- Overview table ------------------------------------------------------ #
with tab_overview:
    table = view.drop(columns=["Trend"]).sort_values(
        sort_by, ascending=ascending, na_position="last"
    )
    table = table[["Ticker", "Market", "Price"] + PCT_COLS]
    st.dataframe(
        style_table(table),
        width="stretch",
        hide_index=True,
        height=min(60 + 35 * len(table), 900),
    )
    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download as CSV", csv, "watchlist.csv", "text/csv"
    )
    if failed:
        st.caption("⚠️ No data returned for: " + ", ".join(failed))

# ---- Heatmap ------------------------------------------------------------- #
with tab_heatmap:
    hm = view.set_index("Ticker")[list(WINDOWS)].sort_values("1W %", ascending=True)
    fig = go.Figure(
        go.Heatmap(
            z=hm.values, x=list(WINDOWS), y=hm.index,
            colorscale=[[0, "#ff5c5c"], [0.5, "#1c1c24"], [1, "#26d07c"]],
            zmid=0, text=np.round(hm.values, 1), texttemplate="%{text}%",
            colorbar=dict(title="% change"),
        )
    )
    fig.update_layout(
        template="plotly_dark", height=max(400, 22 * len(hm)),
        margin=dict(l=10, r=10, t=30, b=10),
        title="Percentage change by time window",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, width="stretch")

# ---- Ticker detail + news ------------------------------------------------ #
with tab_detail:
    choice = st.selectbox("Select a ticker", view["Ticker"].tolist())
    row = view[view["Ticker"] == choice].iloc[0]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Market", row["Market"])
    c2.metric("Price", f"{row['Price']:,.2f}")
    c3.metric("3-day", f"{row['3D %']:+.2f}%" if pd.notna(row["3D %"]) else "—")
    c4.metric("1-week", f"{row['1W %']:+.2f}%" if pd.notna(row["1W %"]) else "—")
    c5.metric("1-month", f"{row['1M %']:+.2f}%" if pd.notna(row["1M %"]) else "—")
    c6.metric("Volume Δ", f"{row['Volume Δ%']:+.1f}%" if pd.notna(row["Volume Δ%"]) else "—")

    fig = detail_chart(choice)
    if fig is not None:
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("No chart data available for this ticker.")

    st.subheader("📰 Latest news, releases & regulatory updates")
    news = load_news(choice)
    if not news:
        st.info("No recent news found for this ticker.")
    for item in news:
        st.markdown(
            f"<span class='news-tag' style='background:{item['tag_colour']}'>"
            f"{item['tag']}</span>",
            unsafe_allow_html=True,
        )
        if item["url"]:
            st.markdown(f"**[{item['title']}]({item['url']})**")
        else:
            st.markdown(f"**{item['title']}**")
        meta = " · ".join(
            x for x in [item["publisher"], _fmt_published(item["published"]), item["type"]] if x
        )
        if meta:
            st.caption(meta)
        if item["summary"]:
            st.write(item["summary"])
        st.markdown("---")

st.caption(
    "ℹ️ Informational only — not investment advice. Yahoo Finance data may be "
    "delayed and occasional tickers may fail to resolve."
)
