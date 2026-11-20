#!/usr/bin/env python3
"""
Watchlist dashboard generator
=============================
Fetches live price + news data for the watchlist straight from Yahoo Finance's
JSON API and renders a self-contained, visually rich ``dashboard.html`` that can
be opened on any device or published as an artifact. No server required.

Usage:
    python3 generate.py            # fetch live data and write dashboard.html
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import time
import urllib.parse
import urllib.request

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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124"


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                return {"__error__": str(e)}
            time.sleep(1.2 * (attempt + 1))


def _pct(series, periods):
    s = [x for x in series if x is not None]
    if len(s) <= periods:
        return None
    prev = s[-1 - periods]
    if not prev:
        return None
    return (s[-1] - prev) / prev * 100


def _region(ticker: str) -> str:
    if ticker.endswith((".NS", ".BO")):
        return "India"
    if ticker.endswith(".L"):
        return "UK"
    if ticker.endswith(".IL"):
        return "UK"
    return "US / Global"


def fetch_one(ticker: str) -> dict:
    out = {"ticker": ticker, "region": _region(ticker)}
    enc = urllib.parse.quote(ticker)
    data = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range=3mo&interval=1d")
    try:
        res = data["chart"]["result"][0]
        meta = res["meta"]
        quote = res["indicators"]["quote"][0]
        closes = [c for c in (quote.get("close") or [])]
        vols = quote.get("volume") or []
        out.update({
            "name": meta.get("longName") or meta.get("shortName") or ticker,
            "currency": meta.get("currency", ""),
            "exchange": meta.get("fullExchangeName", ""),
            "price": meta.get("regularMarketPrice"),
            "dayChangePct": meta.get("regularMarketChangePercent"),
            "w52high": meta.get("fiftyTwoWeekHigh"),
            "w52low": meta.get("fiftyTwoWeekLow"),
            "d3": _pct(closes, 3),
            "w1": _pct(closes, 5),
            "m1": _pct(closes, 21),
        })
        if out["dayChangePct"] is None:
            out["dayChangePct"] = _pct(closes, 1)
        v = [x for x in vols if x is not None]
        if len(v) >= 6:
            latest = v[-1]
            window = v[-21:-1] if len(v) > 21 else v[:-1]
            base = sum(window) / len(window) if window else 0
            out["volChange"] = ((latest - base) / base * 100) if base else None
        out["spark"] = [round(c, 4) for c in closes[-30:] if c is not None]
    except Exception as e:  # noqa: BLE001
        out["__error__"] = (data.get("__error__") if isinstance(data, dict) else None) or str(e)

    news_data = _get(f"https://query1.finance.yahoo.com/v1/finance/search?q={enc}&newsCount=6&quotesCount=0")
    items = []
    try:
        for n in (news_data.get("news") or [])[:6]:
            if not n.get("title"):
                continue
            items.append({
                "title": n.get("title", ""),
                "publisher": n.get("publisher", ""),
                "link": n.get("link", ""),
                "ts": n.get("providerPublishTime"),
                "type": n.get("type", ""),
            })
    except Exception:  # noqa: BLE001
        pass
    out["news"] = items
    return out


def fetch_all() -> dict:
    results: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, t): t for t in TICKERS}
        for f in cf.as_completed(futs):
            r = f.result()
            results[r["ticker"]] = r
    ordered = [results[t] for t in TICKERS]
    now = dt.datetime.utcnow()
    return {
        "generated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "generatedTs": int(time.time()),
        "count": len(TICKERS),
        "rows": ordered,
    }


def render(payload: dict) -> str:
    blob = json.dumps(payload, separators=(",", ":"))
    return HTML_TEMPLATE.replace("/*__DATA__*/", blob)


# The HTML template lives in a sibling file so the generator stays readable.
import os  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "template.html"), encoding="utf-8") as _fh:
    HTML_TEMPLATE = _fh.read()


def main() -> None:
    print("Fetching live market data for", len(TICKERS), "tickers ...")
    payload = fetch_all()
    ok = [r for r in payload["rows"] if r.get("price") is not None]
    failed = [r["ticker"] for r in payload["rows"] if r.get("price") is None]
    print(f"  loaded {len(ok)}/{len(TICKERS)}; failed: {failed or 'none'}")
    out_path = os.path.join(_HERE, "dashboard.html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(render(payload))
    # Also drop the raw payload next to it for debugging / reuse.
    with open(os.path.join(_HERE, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print("Wrote", out_path)


if __name__ == "__main__":
    main()
