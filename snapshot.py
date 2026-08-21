"""
Static watchlist snapshot generator
====================================
Fetches 3-day / 1-week / 1-month price moves, volume shifts and recent news
for the watchlist straight from Yahoo Finance's public JSON endpoints, then
renders a single self-contained ``dashboard.html`` you can open in any browser
or host anywhere.

Unlike ``app.py`` (the interactive Streamlit view), this needs no server and
no ``yfinance`` — just ``requests`` — so it runs cleanly in headless / proxied
CI environments and produces a shareable artifact.

Usage:
    python3 snapshot.py                 # -> dashboard.html
    python3 snapshot.py --out out.html  # custom output path

Behind a proxy that intercepts TLS, point requests at the CA bundle:
    REQUESTS_CA_BUNDLE=/path/to/ca.crt python3 snapshot.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

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

# Trading-day look-backs for each window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

HOSTS = ["https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json"}
VERIFY = os.environ.get("REQUESTS_CA_BUNDLE") or True
HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
def _get(path: str, tries: int = 4) -> dict:
    """GET a Yahoo endpoint, rotating hosts and backing off on failure."""
    last = None
    for i in range(tries):
        host = HOSTS[i % len(HOSTS)]
        try:
            r = requests.get(host + path, headers=HEADERS, verify=VERIFY, timeout=25)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(0.6 * (i + 1))
    return {"__error__": last}


def _pct(seq: list, periods: int):
    s = [x for x in seq if x is not None]
    if len(s) <= periods or not s[-1 - periods]:
        return None
    return (s[-1] - s[-1 - periods]) / s[-1 - periods] * 100


def _round(x, n=2):
    return round(x, n) if isinstance(x, (int, float)) else None


def fetch_chart(ticker: str) -> dict:
    j = _get(f"/v8/finance/chart/{ticker}?range=3mo&interval=1d")
    try:
        res = j["chart"]["result"][0]
        meta = res["meta"]
        quote = res["indicators"]["quote"][0]
        closes = [c for c in quote["close"] if c is not None]
        vols = [v for v in quote["volume"] if v is not None]
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)

        vol_chg = None
        if len(vols) >= 6:
            base = vols[-21:-1] if len(vols) > 21 else vols[:-1]
            avg = sum(base) / len(base) if base else None
            if avg:
                vol_chg = (vols[-1] - avg) / avg * 100

        return {
            "t": ticker,
            "ok": True,
            "name": meta.get("longName") or meta.get("shortName") or ticker,
            "cur": meta.get("currency", ""),
            "ex": meta.get("fullExchangeName", ""),
            "p": _round(price),
            "d3": _round(_pct(closes, WINDOWS["d3"])),
            "w1": _round(_pct(closes, WINDOWS["w1"])),
            "m1": _round(_pct(closes, WINDOWS["m1"])),
            "v": _round(vol_chg, 1),
            "s": [_round(c, 4) for c in closes[-30:]],
        }
    except Exception:  # noqa: BLE001
        return {"t": ticker, "ok": False, "error": j.get("__error__", "no data")}


def fetch_news(ticker: str, n: int = 4):
    j = _get(f"/v1/finance/search?q={ticker}&newsCount={n}&quotesCount=0&enableFuzzyQuery=false")
    items = []
    for it in (j.get("news") or [])[:n]:
        items.append({
            "ti": it.get("title", ""),
            "pu": it.get("publisher", ""),
            "ln": it.get("link", ""),
            "tm": it.get("providerPublishTime"),
        })
    return ticker, items


def build_payload() -> dict:
    rows: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed({ex.submit(fetch_chart, t) for t in TICKERS}):
            r = fut.result()
            rows[r["t"]] = r
            print(("  ok  " if r.get("ok") else "  FAIL") + " " + r["t"], file=sys.stderr)

    ordered = [rows[t] for t in TICKERS]
    ok = [r for r in ordered if r.get("ok")]

    # Fetch news for the biggest movers (by |1-week move|) to stay within rate limits.
    movers = sorted(
        (r for r in ok if r.get("w1") is not None),
        key=lambda r: abs(r["w1"]), reverse=True,
    )
    targets = [r["t"] for r in movers[:24]]

    news: dict[str, list] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed({ex.submit(fetch_news, t) for t in targets}):
            t, items = fut.result()
            news[t] = items

    print(f"\nFetched {len(ok)}/{len(TICKERS)} tickers · news for {len(news)}", file=sys.stderr)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    return {"rows": ordered, "news": news, "gen": stamp}


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #
def render(payload: dict) -> str:
    tpl_path = os.path.join(HERE, "dashboard_template.html")
    with open(tpl_path, encoding="utf-8") as fh:
        tpl = fh.read()
    return tpl.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a static watchlist dashboard.")
    ap.add_argument("--out", default=os.path.join(HERE, "dashboard.html"),
                    help="output HTML path (default: dashboard.html)")
    args = ap.parse_args()

    payload = build_payload()
    html = render(payload)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Wrote {args.out} ({len(html) // 1024} KB) — open it in any browser.", file=sys.stderr)


if __name__ == "__main__":
    main()
