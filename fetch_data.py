"""Fetch price/volume data for the watchlist from Yahoo's chart API and
compute momentum + volume metrics. Writes data.json for the dashboard."""
import json, os, time, random
from concurrent.futures import ThreadPoolExecutor
import requests

os.environ.setdefault("REQUESTS_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")

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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def pct(cur, prev):
    if prev in (None, 0) or cur is None:
        return None
    return (cur - prev) / prev * 100.0


def fetch(ticker):
    url_path = f"/v8/finance/chart/{ticker}?range=3mo&interval=1d"
    last_err = None
    for attempt in range(4):
        host = HOSTS[attempt % 2]
        try:
            r = requests.get(f"https://{host}{url_path}",
                             headers={"User-Agent": UA}, timeout=25)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1) + random.random())
                last_err = "429"
                continue
            r.raise_for_status()
            j = r.json()
            res = (j.get("chart", {}).get("result") or [None])[0]
            if not res:
                return {"ticker": ticker, "error": "no data"}
            meta = res.get("meta", {})
            quote = (res.get("indicators", {}).get("quote") or [{}])[0]
            closes = [c for c in (quote.get("close") or []) if c is not None]
            vols_raw = quote.get("volume") or []
            adj = res.get("indicators", {}).get("adjclose")
            if adj:
                ac = [c for c in adj[0].get("adjclose", []) if c is not None]
                if len(ac) >= len(closes):
                    closes = ac
            if len(closes) < 4:
                return {"ticker": ticker, "error": "insufficient history"}
            vols = [v for v in vols_raw if v is not None]

            def back(n):
                return closes[-1 - n] if len(closes) > n else None

            vol_chg = None
            if len(vols) > 6:
                base = vols[-21:-1] if len(vols) > 21 else vols[:-1]
                base = [v for v in base if v]
                if base:
                    avg = sum(base) / len(base)
                    if avg:
                        vol_chg = (vols[-1] - avg) / avg * 100.0
            return {
                "ticker": ticker,
                "name": meta.get("shortName") or meta.get("longName") or ticker,
                "currency": meta.get("currency", ""),
                "exchange": meta.get("fullExchangeName", ""),
                "price": closes[-1],
                "d1": pct(closes[-1], back(1)),
                "d3": pct(closes[-1], back(3)),
                "w1": pct(closes[-1], back(5)),
                "m1": pct(closes[-1], back(21)),
                "vol_chg": vol_chg,
                "vol_latest": vols[-1] if vols else None,
                "spark": [round(c, 4) for c in closes[-22:]],
            }
        except Exception as e:
            last_err = repr(e)[:120]
            time.sleep(0.6 * (attempt + 1))
    return {"ticker": ticker, "error": last_err or "failed"}


def main():
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for row in ex.map(fetch, TICKERS):
            results.append(row)
            tag = "OK " if "error" not in row else "ERR"
            print(f"{tag} {row['ticker']:<14} "
                  + (f"{row.get('w1'):+.2f}% 1W" if row.get("w1") is not None
                     else row.get("error", "")))
    ok = [r for r in results if "error" not in r]
    err = [r for r in results if "error" in r]
    out = {"generated_utc": None, "rows": results, "n_ok": len(ok),
           "n_err": len(err)}
    with open("data.json", "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"\n{len(ok)}/{len(results)} tickers OK, {len(err)} failed")
    if err:
        print("Failed:", ", ".join(r["ticker"] for r in err))


if __name__ == "__main__":
    main()
