# 📈 Stock-routine — Watchlist Momentum Dashboard

A visual Streamlit dashboard that tracks momentum and news for a custom stock
watchlist. At a glance it shows, for every ticker:

- **3-day / 1-week / 1-month % price change**
- **Volume change** vs the trailing 20-day average
- **Top gainers & losers** cards for the selected window
- **30-day sparkline** trend per ticker and a **6-month candlestick** chart
- A **% change heatmap** across all time windows
- **News, press releases and regulatory / filing updates** per ticker, plus a
  combined **market-wide news feed** across the whole watchlist with a
  "regulatory only" filter

Data comes from Yahoo Finance (via `yfinance`) and is cached for 15 minutes.

## Quick start

```bash
pip install -r requirements.txt

# Full visual dashboard
streamlit run app.py

# Or a quick command-line summary
python main.py
```

The dashboard opens in your browser (default http://localhost:8501).

## Editing the watchlist

Edit the `TICKERS` list at the top of `app.py` (and `main.py` for the CLI).
Tickers use Yahoo Finance symbols — e.g. `NVDA`, `ASML`, `HFCL.NS` (NSE India),
`FLTR.L` (London), `TIMEX.BO` (BSE India).

## Tabs

| Tab | What it shows |
| --- | --- |
| 📋 Overview | Sortable, colour-coded table with sparklines and all % windows |
| 🌡️ Heatmap | Percentage change across 3D / 1W / 1M for every ticker |
| 🔎 Ticker detail | Metrics, 6-month candlestick chart and per-ticker news |
| 📰 Market news | Aggregated headlines across the watchlist, regulatory filter |

> ℹ️ Informational only — not investment advice. Yahoo Finance data may be
> delayed and occasional tickers may fail to resolve.
