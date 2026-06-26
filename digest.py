"""
Watchlist digest (headless / CI-friendly)
=========================================
Generates a momentum + volume digest for the watchlist using Yahoo Finance's
public chart endpoint via plain ``requests``.

Why not yfinance here?  yfinance pins ``curl_cffi`` (BoringSSL), which fails TLS
through re-terminating egress proxies.  Plain ``requests`` honours the standard
``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` trust vars, so this runs anywhere —
including scheduled/CI environments where the Streamlit app (app.py) can't reach
Yahoo.  Run locally or in a routine:

    python digest.py            # pretty console digest
    python digest.py --md       # markdown (for reports / notifications)
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor

import requests

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

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "Mozilla/5.0"})


def _pct(closes: list[float], periods: int) -> float | None:
    c = [x for x in closes if x is not None]
    if len(c) <= periods or not c[-1 - periods]:
        return None
    return (c[-1] - c[-1 - periods]) / c[-1 - periods] * 100


def _volume_change(volume: list[float]) -> float | None:
    v = [x for x in volume if x is not None]
    if len(v) < 6:
        return None
    baseline = sum(v[-21:-1]) / len(v[-21:-1]) if len(v) > 21 else sum(v[:-1]) / len(v[:-1])
    if not baseline:
        return None
    return (v[-1] - baseline) / baseline * 100


def fetch(ticker: str) -> dict | None:
    """One row of metrics for a ticker, or None if no data resolved."""
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}"
        try:
            r = _SESSION.get(url, params={"range": "3mo", "interval": "1d"}, timeout=15)
            if not r.ok:
                continue
            res = r.json()["chart"]["result"][0]
            quote = res["indicators"]["quote"][0]
            closes = [x for x in quote["close"] if x is not None]
            if not closes:
                return None
            row = {
                "Ticker": ticker,
                "Price": closes[-1],
                "Currency": res["meta"].get("currency", ""),
                "Volume Δ%": _volume_change(quote["volume"]),
            }
            for label, periods in WINDOWS.items():
                row[label] = _pct(closes, periods)
            return row
        except Exception:
            continue
    return None


def load_metrics(tickers: list[str] | None = None, workers: int = 10) -> list[dict]:
    tickers = tickers or TICKERS
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows = [r for r in ex.map(fetch, tickers) if r]
    return rows


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _g(v: float | None) -> str:
    return f"{v:+.1f}%" if v is not None else "n/a"


def _key(row: dict, field: str) -> float:
    v = row.get(field)
    return v if v is not None else float("-inf")


def render_console(rows: list[dict], failed: list[str]) -> str:
    out = [f"Loaded {len(rows)}/{len(rows) + len(failed)} tickers"]
    if failed:
        out.append("Unresolved: " + ", ".join(failed))

    def line(r: dict) -> str:
        return (f"{r['Ticker']:13} {r['Price']:>11.2f} {r['Currency']:<4} "
                f"3D {_g(r['3D %']):>8}  1W {_g(r['1W %']):>8}  "
                f"1M {_g(r['1M %']):>8}  Vol {_g(r['Volume Δ%']):>8}")

    out.append("\nTOP 1W GAINERS")
    for r in sorted(rows, key=lambda r: _key(r, "1W %"), reverse=True)[:10]:
        out.append(line(r))
    out.append("\nTOP 1W LOSERS")
    for r in sorted(rows, key=lambda r: _key(r, "1W %"))[:10]:
        out.append(line(r))
    out.append("\nBIGGEST VOLUME SURGES")
    for r in sorted(rows, key=lambda r: _key(r, "Volume Δ%"), reverse=True)[:8]:
        out.append(line(r))
    return "\n".join(out)


def render_markdown(rows: list[dict], failed: list[str]) -> str:
    def table(sorted_rows: list[dict]) -> list[str]:
        lines = ["| Ticker | Price | 3D % | 1W % | 1M % | Vol Δ% |",
                 "|---|---:|---:|---:|---:|---:|"]
        for r in sorted_rows:
            lines.append(
                f"| {r['Ticker']} | {r['Price']:,.2f} {r['Currency']} | "
                f"{_g(r['3D %'])} | {_g(r['1W %'])} | {_g(r['1M %'])} | {_g(r['Volume Δ%'])} |"
            )
        return lines

    md = [f"_Loaded {len(rows)}/{len(rows) + len(failed)} tickers._", ""]
    if failed:
        md.append("Unresolved: " + ", ".join(failed) + "\n")
    md.append("### Top 1W gainers")
    md += table(sorted(rows, key=lambda r: _key(r, "1W %"), reverse=True)[:10])
    md.append("\n### Top 1W losers")
    md += table(sorted(rows, key=lambda r: _key(r, "1W %"))[:10])
    md.append("\n### Biggest volume surges")
    md += table(sorted(rows, key=lambda r: _key(r, "Volume Δ%"), reverse=True)[:8])
    return "\n".join(md)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", action="store_true", help="emit markdown instead of console text")
    args = ap.parse_args()

    rows = load_metrics()
    loaded = {r["Ticker"] for r in rows}
    failed = [t for t in TICKERS if t not in loaded]
    print(render_markdown(rows, failed) if args.md else render_console(rows, failed))


if __name__ == "__main__":
    main()
