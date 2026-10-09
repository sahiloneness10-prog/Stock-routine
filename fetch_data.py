"""Fetch watchlist metrics + headlines and write a snapshot to data.json.

Pipeline:  python fetch_data.py  ->  data.json  ->  build_dashboard.py

Pulls ~3 months of daily OHLCV for every ticker, computes 3-day / 1-week /
1-month price moves and the latest-session volume vs its trailing 20-day
average, grabs recent headlines per ticker, and dumps everything to JSON.
Prices come from Yahoo Finance via yfinance; headlines from Yahoo's public
search endpoint (yfinance's own `.news` is currently unreliable).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time

import numpy as np
import pandas as pd
import requests
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

# Trading-day look-backs for each momentum window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _pct(series: pd.Series, periods: int) -> float | None:
    s = series.dropna()
    if len(s) <= periods:
        return None
    prev = s.iloc[-1 - periods]
    if prev == 0 or pd.isna(prev):
        return None
    return float((s.iloc[-1] - prev) / prev * 100)


def _volume_change(volume: pd.Series) -> float | None:
    v = volume.dropna()
    if len(v) < 6:
        return None
    latest = v.iloc[-1]
    baseline = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not baseline or np.isnan(baseline):
        return None
    return float((latest - baseline) / baseline * 100)


def _field(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    try:
        s = data[ticker][field] if isinstance(data.columns, pd.MultiIndex) else data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def _row(ticker: str, close: pd.Series, volume: pd.Series) -> dict:
    row = {
        "ticker": ticker,
        "price": float(close.iloc[-1]),
        "vol": _volume_change(volume),
        "spark": [round(float(x), 4) for x in close.iloc[-21:].tolist()],
    }
    for label, periods in WINDOWS.items():
        row[label] = _pct(close, periods)
    return row


def load_metrics() -> tuple[list[dict], list[str]]:
    print("Downloading prices…", file=sys.stderr)
    data = yf.download(
        TICKERS, period="3mo", interval="1d", group_by="ticker",
        auto_adjust=True, progress=False, threads=True,
    )
    rows, failed = [], []
    for t in TICKERS:
        close = _field(data, t, "Close")
        if close.empty:
            failed.append(t)
            continue
        rows.append(_row(t, close, _field(data, t, "Volume")))

    # Retry failures individually (batch download occasionally races the cache).
    for t in list(failed):
        try:
            hist = yf.Ticker(t).history(period="3mo", auto_adjust=True)
            if hist.empty:
                continue
            close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
            rows.append(_row(t, close, pd.to_numeric(hist["Volume"], errors="coerce").dropna()))
            failed.remove(t)
            print(f"recovered {t}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"still failed {t}: {exc}", file=sys.stderr)
    return rows, failed


def _fmt_time(epoch: int) -> str:
    try:
        return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, OSError, OverflowError):
        return ""


def load_news(tickers: list[str]) -> dict[str, list[dict]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    news: dict[str, list[dict]] = {}
    for t in tickers:
        try:
            resp = session.get(
                SEARCH_URL, params={"q": t, "newsCount": 6, "quotesCount": 0}, timeout=20
            )
            arr = resp.json().get("news", []) if resp.status_code == 200 else []
        except Exception:  # noqa: BLE001
            arr = []
        items = [
            {
                "title": n.get("title", "Untitled"),
                "publisher": n.get("publisher", ""),
                "url": n.get("link", ""),
                "published": _fmt_time(n.get("providerPublishTime", 0)),
                "ts": n.get("providerPublishTime", 0),
                "type": n.get("type", ""),
            }
            for n in arr[:6]
        ]
        if items:
            news[t] = items
        time.sleep(0.15)
    return news


def main() -> None:
    rows, failed = load_metrics()
    loaded = sorted(r["ticker"] for r in rows)
    print(f"Loaded {len(rows)}/{len(TICKERS)}; failed: {failed}", file=sys.stderr)

    news = load_news(loaded)
    print(f"News for {len(news)} tickers", file=sys.stderr)

    snapshot = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(TICKERS),
        "rows": rows,
        "failed": sorted(failed),
        "news": news,
    }
    with open("data.json", "w") as f:
        json.dump(snapshot, f)
    print("Wrote data.json", file=sys.stderr)


if __name__ == "__main__":
    main()
