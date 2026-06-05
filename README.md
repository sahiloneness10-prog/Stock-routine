# 📈 Stock-routine — Watchlist Momentum Dashboard

A visual, interactive **Streamlit** dashboard that tracks momentum, volume and
news for a custom stock watchlist — built on free Yahoo Finance data.

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Streamlit](https://img.shields.io/badge/streamlit-app-red)

## What it shows

For every ticker in your watchlist:

| Metric | Description |
| --- | --- |
| **3-day %** | Price change over the last 3 trading days |
| **1-week %** | Price change over the last 5 trading days |
| **1-month %** | Price change over the last ~21 trading days |
| **Volume Δ%** | Latest session's volume vs the trailing 20-day average |
| **30-day trend** | Inline sparkline of recent closing prices |
| **News** | Latest headlines, auto-tagged as **Regulatory ⚖️**, **Earnings 💰**, **Analyst 🎯**, **Deal/M&A 🤝** or **News 📰** |

## Views

- **📋 Overview** — sortable, region-filterable table with colour-graded
  momentum cells and inline price sparklines.
- **🗺️ Treemap** — watchlist-at-a-glance map: tile size = magnitude of the
  move, colour = direction (green up / red down), grouped by listing region.
- **🌡️ Heatmap** — % change across all three time windows, sorted by your
  chosen window.
- **🔎 Ticker detail & news** — 6-month candlestick chart with a 20-day moving
  average, key metrics, and categorised, filterable news / regulatory updates
  that may have moved the share price.

Highlights at the top: tickers loaded, gainers vs losers, top & worst movers
and the biggest volume spike. Data is cached for 15 minutes; hit **🔄 Refresh
data** in the sidebar to force an update.

## Quick start

```bash
pip install -r requirements.txt

# Full visual dashboard
streamlit run app.py

# Lightweight command-line summary
python main.py
```

## Customising the watchlist

Edit the `TICKERS` list near the top of `app.py` (and `main.py`). Use Yahoo
Finance symbols, including exchange suffixes for non-US listings, e.g.
`.NS`/`.BO` (India), `.L`/`.IL` (UK).

> ℹ️ Informational only — not investment advice. Yahoo Finance data may be
> delayed and occasional tickers may fail to resolve. News categories are
> inferred from headline keywords and are approximate.
