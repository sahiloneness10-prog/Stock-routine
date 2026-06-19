"""
Watchlist routine digest
=========================
Headless companion to ``app.py``. Pulls prices, volume and headlines for the
watchlist, ranks the notable movers (3-day / 1-week / 1-month price moves and
volume shifts) and prints a digest plus a short, notification-ready summary.

Run with:
    python routine.py
"""

from __future__ import annotations

import html
import os
import re
import sys
import tempfile

import numpy as np
import pandas as pd
import yfinance as yf

# Keep yfinance's sqlite cache off the (sometimes read-only / contended)
# working tree so concurrent downloads don't trip "database is locked".
try:
    yf.set_tz_cache_location(os.path.join(tempfile.gettempdir(), "yf_tz_cache"))
except Exception:
    pass

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

WINDOWS = {"3D": 3, "1W": 5, "1M": 21}

# How big a move has to be to count as "notable" for the notification.
MOVE_THRESHOLD = 7.0       # % price move in any window
VOLUME_THRESHOLD = 75.0    # % spike vs 20-day average volume


def _pct_change(series: pd.Series, periods: int) -> float:
    s = series.dropna()
    if len(s) <= periods:
        return np.nan
    prev = s.iloc[-1 - periods]
    if prev == 0:
        return np.nan
    return (s.iloc[-1] - prev) / prev * 100


def _volume_change(volume: pd.Series) -> float:
    v = volume.dropna()
    if len(v) < 6:
        return np.nan
    latest = v.iloc[-1]
    baseline = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not baseline or np.isnan(baseline):
        return np.nan
    return (latest - baseline) / baseline * 100


def _series(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    try:
        if isinstance(data.columns, pd.MultiIndex):
            s = data[ticker][field]
        else:
            s = data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def build_metrics() -> tuple[pd.DataFrame, list[str]]:
    data = yf.download(
        TICKERS,
        period="3mo",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        progress=False,
        threads=False,  # avoid sqlite "database is locked" under concurrency
    )
    rows = []
    for t in TICKERS:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            continue
        row = {
            "Ticker": t,
            "Price": close.iloc[-1],
            "Volume": _volume_change(volume),
        }
        for label, periods in WINDOWS.items():
            row[label] = _pct_change(close, periods)
        rows.append(row)
    df = pd.DataFrame(rows)
    failed = sorted(set(TICKERS) - (set(df["Ticker"]) if not df.empty else set()))
    return df, failed


def _clean_html(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


def load_news(ticker: str, limit: int = 3) -> list[dict]:
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []
    items = []
    for entry in raw[: limit * 2]:
        c = entry.get("content", entry) if isinstance(entry, dict) else {}
        if not c:
            continue
        link = c.get("clickThroughUrl") or c.get("canonicalUrl") or {}
        provider = c.get("provider") or {}
        items.append(
            {
                "title": c.get("title", "Untitled"),
                "publisher": provider.get("displayName", "") if isinstance(provider, dict) else "",
                "url": link.get("url", "") if isinstance(link, dict) else "",
                "published": c.get("pubDate") or c.get("displayTime") or "",
            }
        )
        if len(items) >= limit:
            break
    return items


def _fmt(val) -> str:
    return "    —" if pd.isna(val) else f"{val:+6.1f}%"


def main() -> int:
    df, failed = build_metrics()
    if df.empty:
        print("No price data could be loaded.")
        return 1

    df = df.sort_values("1W", ascending=False, na_position="last")

    print("\n=== Watchlist digest ===")
    print(f"{'Ticker':<12}{'Price':>12}   {'3D':>7}{'1W':>8}{'1M':>8}{'Vol':>9}")
    print("-" * 70)
    for _, r in df.iterrows():
        print(
            f"{r['Ticker']:<12}{r['Price']:>12,.2f}   "
            f"{_fmt(r['3D'])}{_fmt(r['1W'])}{_fmt(r['1M'])}{_fmt(r['Volume'])}"
        )
    if failed:
        print(f"\nNo data for: {', '.join(failed)}")

    # ---- notable movers ---------------------------------------------------- #
    def notable(r) -> bool:
        moves = [r["3D"], r["1W"], r["1M"]]
        if any(pd.notna(m) and abs(m) >= MOVE_THRESHOLD for m in moves):
            return True
        return pd.notna(r["Volume"]) and r["Volume"] >= VOLUME_THRESHOLD

    movers = df[df.apply(notable, axis=1)].copy()
    movers["_mag"] = movers[["3D", "1W", "1M"]].abs().max(axis=1)
    movers = movers.sort_values("_mag", ascending=False)

    print("\n=== Notable movers ===")
    if movers.empty:
        print("Nothing crossed the thresholds.")
    for _, r in movers.iterrows():
        print(f"\n{r['Ticker']}  ({r['Price']:,.2f})  "
              f"3D {_fmt(r['3D']).strip()} | 1W {_fmt(r['1W']).strip()} | "
              f"1M {_fmt(r['1M']).strip()} | Vol {_fmt(r['Volume']).strip()}")
        for n in load_news(r["Ticker"], limit=2):
            meta = " · ".join(x for x in [n["publisher"], n["published"]] if x)
            print(f"   • {n['title']}  ({meta})")
            if n["url"]:
                print(f"     {n['url']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
