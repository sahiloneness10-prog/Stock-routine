"""Fetch watchlist metrics + news and dump JSON for the dashboard."""
from __future__ import annotations
import datetime as dt
import html
import json
import re
import sys
import numpy as np
import pandas as pd
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

CURRENCY = {".NS": "₹", ".BO": "₹", ".L": "p", ".IL": "₪"}
def ccy(t):
    for suf, sym in CURRENCY.items():
        if t.endswith(suf):
            return sym
    return "$"

def pct(series, periods):
    s = series.dropna()
    if len(s) <= periods:
        return None
    prev = s.iloc[-1 - periods]
    if prev == 0:
        return None
    v = (s.iloc[-1] - prev) / prev * 100
    return None if (v != v) else round(float(v), 2)

def vol_change(volume):
    v = volume.dropna()
    if len(v) < 6:
        return None
    latest = v.iloc[-1]
    base = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not base or base != base:
        return None
    return round(float((latest - base) / base * 100), 1)

def clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()

print("Downloading prices...", file=sys.stderr)
data = yf.download(TICKERS, period="3mo", interval="1d", group_by="ticker",
                   auto_adjust=True, progress=False, threads=True)

def series(t, field):
    try:
        s = data[t][field] if isinstance(data.columns, pd.MultiIndex) else data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()

rows = []
failed = []
for t in TICKERS:
    close = series(t, "Close")
    volume = series(t, "Volume")
    if close.empty:
        failed.append(t)
        continue
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) > 1 else last
    day = round((last - prev) / prev * 100, 2) if prev else None
    rows.append({
        "ticker": t, "ccy": ccy(t), "price": round(last, 2),
        "day": day, "d3": pct(close, 3), "w1": pct(close, 5),
        "m1": pct(close, 21), "vol": vol_change(volume),
        "spark": [round(float(x), 4) for x in close.iloc[-30:].tolist()],
        "last_date": str(close.index[-1].date()),
    })

print(f"Prices: {len(rows)} ok, {len(failed)} failed", file=sys.stderr)

# News for the biggest movers (by |1W%|) + a few majors, to keep it fast/reliable
def absw(r):
    return abs(r["w1"]) if r["w1"] is not None else -1
movers = sorted(rows, key=absw, reverse=True)
news_targets = [r["ticker"] for r in movers[:28]]
news = {}
for t in news_targets:
    try:
        raw = yf.Ticker(t).news or []
    except Exception:
        raw = []
    items = []
    for e in raw[:4]:
        c = e.get("content", e) if isinstance(e, dict) else {}
        if not c:
            continue
        prov = c.get("provider") or {}
        link = c.get("clickThroughUrl") or c.get("canonicalUrl") or {}
        items.append({
            "title": c.get("title", "Untitled"),
            "summary": clean(c.get("summary") or c.get("description") or "")[:260],
            "publisher": prov.get("displayName", "") if isinstance(prov, dict) else "",
            "url": link.get("url", "") if isinstance(link, dict) else "",
            "published": c.get("pubDate") or c.get("displayTime") or "",
        })
    if items:
        news[t] = items
    print(f"  news {t}: {len(items)}", file=sys.stderr)

out = {
    "generated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    "rows": rows, "failed": failed, "news": news,
}
with open(sys.argv[1] if len(sys.argv) > 1 else "data.json", "w") as f:
    json.dump(out, f, indent=1)
print("WROTE", sys.argv[1] if len(sys.argv) > 1 else "data.json", file=sys.stderr)
