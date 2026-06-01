"""
Watchlist Momentum Dashboard
============================
A visual, single-page Streamlit dashboard for a custom stock watchlist. It
surfaces, at a glance:

* 3-day / 1-week / 1-month price moves (% change)
* Volume change vs the trailing 20-day average
* Top gainers & losers
* A per-ticker candlestick chart with sparklines in the table
* The latest news, press releases and regulatory / filing headlines, plus a
  combined market-wide news feed across the whole watchlist.

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
PCT_COLS = list(WINDOWS) + ["Volume Δ%"]

# Keywords used to flag regulatory / filing / corporate-action headlines.
REGULATORY_KEYWORDS = (
    "sec", "fda", "regulator", "regulatory", "lawsuit", "settlement",
    "antitrust", "investigation", "subpoena", "filing", "8-k", "10-k", "10-q",
    "merger", "acquisition", "acquire", "approval", "approved", "guidance",
    "earnings", "dividend", "buyback", "recall", "fine", "patent", "tariff",
    "delisting", "compliance", "ftc", "doj", "court", "ruling",
)

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
            "Trend": close.iloc[-30:].tolist(),  # sparkline data
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
        title = c.get("title", "Untitled")
        summary = _clean_html(c.get("summary") or c.get("description") or "")
        items.append(
            {
                "ticker": ticker,
                "title": title,
                "summary": summary,
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
                "type": c.get("contentType", ""),
                "regulatory": _is_regulatory(f"{title} {summary}"),
            }
        )
    return items


def _is_regulatory(text: str) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in REGULATORY_KEYWORDS)


# --------------------------------------------------------------------------- #
# Presentation helpers
# --------------------------------------------------------------------------- #
def _fmt_published(value: str) -> str:
    if not value:
        return ""
    try:
        ts = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return ts.strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, AttributeError):
        return str(value)


def _published_ts(value: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def colour(val):
    if pd.isna(val):
        return "color:#6b7280"
    if val > 0:
        shade = min(abs(val) / 12, 1)
        return f"background-color:rgba(34,197,94,{0.12 + 0.5 * shade});color:#eafff2"
    if val < 0:
        shade = min(abs(val) / 12, 1)
        return f"background-color:rgba(239,68,68,{0.12 + 0.5 * shade});color:#ffecec"
    return "color:#cbd5e1"


def style_table(df: pd.DataFrame):
    styler = (
        df.style.map(colour, subset=PCT_COLS)
        .format({"Price": "{:,.2f}", **{c: "{:+.2f}%" for c in PCT_COLS}}, na_rep="—")
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
            increasing_line_color="#22c55e",
            decreasing_line_color="#ef4444",
            name=ticker,
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=420,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_rangeslider_visible=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title=f"{ticker} — 6 month price",
    )
    return fig


def render_news_card(item: dict, show_ticker: bool) -> None:
    """Render a single news item as a styled card."""
    pills = ""
    if show_ticker and item.get("ticker"):
        pills += f'<span class="pill pill-tkr">{html.escape(str(item["ticker"]))}</span>'
    if item.get("regulatory"):
        pills += '<span class="pill pill-reg">⚖ REGULATORY</span>'

    title = html.escape(item["title"])
    if item["url"]:
        title_html = f'<a href="{html.escape(item["url"])}" target="_blank">{title}</a>'
    else:
        title_html = f'<span style="color:#f8fafc;font-weight:600">{title}</span>'

    meta = " · ".join(
        x for x in [item["publisher"], _fmt_published(item["published"]), item["type"]] if x
    )
    summary = html.escape(item["summary"])
    st.markdown(
        f"""
        <div class="news-card">
          {pills}{title_html}
          <div class="news-meta">{html.escape(meta)}</div>
          <div class="news-summary">{summary}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mover_card(label: str, row: pd.Series, window: str, positive: bool) -> str:
    val = row[window]
    arrow = "▲" if positive else "▼"
    accent = "#22c55e" if positive else "#ef4444"
    return f"""
    <div class="mover-card" style="border-left:4px solid {accent}">
      <div class="mover-label">{label}</div>
      <div class="mover-ticker">{html.escape(str(row['Ticker']))}</div>
      <div class="mover-change" style="color:{accent}">{arrow} {val:+.2f}%</div>
      <div class="mover-price">{row['Price']:,.2f}</div>
    </div>
    """


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Watchlist Dashboard", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; max-width: 1500px;}
      h1, h2, h3 {letter-spacing: .3px;}
      [data-testid="stMetricValue"] {font-size: 1.5rem;}

      /* hero banner */
      .hero {
        background: linear-gradient(120deg,#0f172a 0%,#1e293b 55%,#312e81 100%);
        padding: 1.4rem 1.8rem; border-radius: 16px; margin-bottom: 1rem;
        border: 1px solid rgba(255,255,255,.06);
      }
      .hero h1 {margin:0; font-size:1.9rem;}
      .hero p {margin:.35rem 0 0; color:#cbd5e1; font-size:.95rem;}

      /* mover cards */
      .mover-grid {display:flex; gap:.7rem; flex-wrap:wrap;}
      .mover-card {
        flex:1 1 150px; background:#111827; border-radius:12px;
        padding:.8rem 1rem; border:1px solid rgba(255,255,255,.05);
      }
      .mover-label {font-size:.7rem; text-transform:uppercase;
        letter-spacing:.6px; color:#94a3b8;}
      .mover-ticker {font-size:1.15rem; font-weight:700; color:#f8fafc; margin-top:.1rem;}
      .mover-change {font-size:1.25rem; font-weight:700; margin-top:.15rem;}
      .mover-price {font-size:.8rem; color:#94a3b8; margin-top:.1rem;}

      /* news cards */
      .news-card {
        background:#111827; border-radius:12px; padding:1rem 1.2rem;
        margin-bottom:.8rem; border:1px solid rgba(255,255,255,.05);
      }
      .news-card a {color:#93c5fd; text-decoration:none; font-weight:600; font-size:1.02rem;}
      .news-card a:hover {text-decoration:underline;}
      .news-meta {color:#94a3b8; font-size:.78rem; margin:.35rem 0;}
      .news-summary {color:#cbd5e1; font-size:.9rem; line-height:1.45;}
      .pill {display:inline-block; padding:.1rem .55rem; border-radius:999px;
        font-size:.68rem; font-weight:700; margin-right:.4rem; vertical-align:middle;}
      .pill-reg {background:rgba(245,158,11,.18); color:#fbbf24; border:1px solid rgba(245,158,11,.4);}
      .pill-tkr {background:rgba(99,102,241,.18); color:#a5b4fc; border:1px solid rgba(99,102,241,.4);}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>📈 Watchlist Momentum Dashboard</h1>
      <p>3-day · 1-week · 1-month price moves, volume shifts and the latest news,
         press releases &amp; regulatory headlines for your watchlist.
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
    primary = st.selectbox(
        "Primary window (for movers / KPIs)", list(WINDOWS), index=1
    )
    sort_by = st.selectbox("Sort table by", PCT_COLS + ["Ticker"], index=1)
    ascending = st.toggle("Ascending", value=False)
    only_movers = st.slider(
        "Hide |% change| below", 0.0, 20.0, 0.0, 0.5,
        help="Filter the overview table to meaningful movers only.",
    )
    st.markdown("---")
    st.caption(f"Tracking **{len(TICKERS)}** tickers.")
    st.caption(f"Updated {dt.datetime.utcnow():%b %d, %Y %H:%M} UTC")

with st.spinner("Fetching market data…"):
    metrics = build_metrics(tuple(TICKERS))

if metrics.empty:
    st.error("No price data could be loaded. Try refreshing in a moment.")
    st.stop()

failed = sorted(set(TICKERS) - set(metrics["Ticker"]))

# ---- KPI strip ------------------------------------------------------------ #
gainers = metrics[metrics[primary] > 0]
losers = metrics[metrics[primary] < 0]
valid = metrics[primary].notna().any()
best = metrics.loc[metrics[primary].idxmax()] if valid else None
worst = metrics.loc[metrics[primary].idxmin()] if valid else None
avg_move = metrics[primary].mean()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Tickers loaded", f"{len(metrics)}/{len(TICKERS)}")
k2.metric(f"Gainers ({primary.strip(' %')})", len(gainers))
k3.metric(f"Losers ({primary.strip(' %')})", len(losers))
k4.metric("Avg move", f"{avg_move:+.2f}%" if pd.notna(avg_move) else "—")
breadth = (len(gainers) / max(len(gainers) + len(losers), 1)) * 100
k5.metric("Breadth (% up)", f"{breadth:.0f}%")

# ---- Top movers cards ----------------------------------------------------- #
if valid:
    top_up = gainers.nlargest(3, primary)
    top_dn = losers.nsmallest(3, primary)
    cards = "".join(mover_card("Top gainer", r, primary, True) for _, r in top_up.iterrows())
    cards += "".join(mover_card("Top loser", r, primary, False) for _, r in top_dn.iterrows())
    st.markdown(f'<div class="mover-grid">{cards}</div>', unsafe_allow_html=True)

st.markdown("")

tab_overview, tab_heatmap, tab_detail, tab_news = st.tabs(
    ["📋 Overview", "🌡️ Heatmap", "🔎 Ticker detail", "📰 Market news"]
)

# ---- Overview table ------------------------------------------------------- #
with tab_overview:
    table = metrics.copy()
    if only_movers > 0:
        mask = (table[list(WINDOWS)].abs() >= only_movers).any(axis=1)
        table = table[mask]
    table = table.sort_values(sort_by, ascending=ascending, na_position="last")
    display_cols = ["Ticker", "Price", "Trend"] + PCT_COLS
    st.dataframe(
        style_table(table[display_cols]),
        width="stretch",
        hide_index=True,
        height=min(60 + 35 * len(table), 900),
        column_config={
            "Trend": st.column_config.LineChartColumn("30d trend", width="small"),
            "Volume Δ%": st.column_config.NumberColumn(
                "Volume Δ%", help="Latest volume vs trailing 20-day average"
            ),
        },
    )
    st.caption(
        "Green = up, red = down · colour intensity scales with the size of the move. "
        "Volume Δ% compares the latest session against the trailing 20-day average."
    )
    if failed:
        st.caption("⚠️ No data returned for: " + ", ".join(failed))

# ---- Heatmap -------------------------------------------------------------- #
with tab_heatmap:
    hm = metrics.set_index("Ticker")[list(WINDOWS)].sort_values(primary, ascending=False)
    fig = go.Figure(
        go.Heatmap(
            z=hm.values,
            x=list(WINDOWS),
            y=hm.index,
            colorscale=[[0, "#ef4444"], [0.5, "#1c1c24"], [1, "#22c55e"]],
            zmid=0,
            text=np.round(hm.values, 1),
            texttemplate="%{text}%",
            colorbar=dict(title="% change"),
            hovertemplate="%{y} · %{x}: %{z:.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        template="plotly_dark",
        height=max(400, 22 * len(hm)),
        margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title="Percentage change by time window (sorted by primary window)",
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
        render_news_card(item, show_ticker=False)

# ---- Combined market news feed -------------------------------------------- #
with tab_news:
    st.caption(
        "Latest headlines aggregated across the whole watchlist — news, press "
        "releases and regulatory / filing updates that may move share prices."
    )
    colf1, colf2 = st.columns([1, 3])
    reg_only = colf1.toggle("Regulatory only", value=False)
    universe = colf2.multiselect(
        "Filter by ticker (empty = all)", metrics["Ticker"].tolist(), default=[]
    )

    selected = universe or metrics["Ticker"].tolist()[:25]
    if not universe:
        st.caption(
            "Showing the first 25 tickers by default — pick specific tickers above "
            "to widen or narrow the feed."
        )

    with st.spinner("Gathering headlines…"):
        feed: list[dict] = []
        for t in selected:
            feed.extend(load_news(t))
    if reg_only:
        feed = [n for n in feed if n["regulatory"]]
    feed.sort(key=lambda n: _published_ts(n["published"]), reverse=True)

    if not feed:
        st.info("No headlines found for the current selection.")
    for item in feed[:60]:
        render_news_card(item, show_ticker=True)

st.caption(
    "ℹ️ Informational only — not investment advice. Yahoo Finance data may be "
    "delayed and occasional tickers may fail to resolve."
)
