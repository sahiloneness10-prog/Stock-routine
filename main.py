"""
Command-line watchlist summary.

Prints 3-day / 1-week / 1-month price moves and a volume shift for every
ticker. For the full visual dashboard run:  ``streamlit run app.py``
"""

import numpy as np
import yfinance as yf

# ✏️ Edit this list with whatever stocks you want to track
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


def pct_change(series, periods):
    s = series.dropna()
    if len(s) <= periods or s.iloc[-1 - periods] == 0:
        return float("nan")
    return (s.iloc[-1] - s.iloc[-1 - periods]) / s.iloc[-1 - periods] * 100


for ticker in TICKERS:
    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty:
            print(f"\n⚠️  {ticker}: no data")
            continue

        close = hist["Close"]
        volume = hist["Volume"].dropna()
        vol_baseline = volume.iloc[-21:-1].mean() if len(volume) > 21 else volume[:-1].mean()
        vol_chg = (
            (volume.iloc[-1] - vol_baseline) / vol_baseline * 100
            if vol_baseline
            else float("nan")
        )

        print(f"\n📈 {ticker}")
        print(f"  3-day change : {pct_change(close, 3):.2f}%")
        print(f"  1-week change: {pct_change(close, 5):.2f}%")
        print(f"  1-month change:{pct_change(close, 21):.2f}%")
        print(f"  volume vs 20d avg: {vol_chg:.1f}%")
    except Exception as exc:  # noqa: BLE001
        print(f"\n⚠️  {ticker}: error ({exc})")
