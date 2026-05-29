# 📈 Stock-routine — Watchlist Momentum Dashboard

A visual [Streamlit](https://streamlit.io/) dashboard that tracks momentum,
volume shifts and the latest news / regulatory updates for a custom stock
watchlist (US, India NSE/BSE, London LSE and more).

## What it shows

- **Momentum** — 3-day, 1-week and 1-month price % changes per ticker.
- **Volume Δ%** — latest session volume vs the trailing 20-day average.
- **🚀 Movers** — top gainers & losers as cards with inline sparklines.
- **📋 Overview** — colour-coded (heatmap) table, sortable, with CSV export.
- **🌡️ Heatmap** — % change by time window across the whole watchlist.
- **🔎 Ticker detail** — 6-month candlestick + volume chart and the latest
  news, releases & regulatory headlines, auto-tagged as
  🏛️ Regulatory / 📊 Earnings / 🤝 M&A / 🎯 Analyst / 📰 General.
- **Market filter** — slice the watchlist by exchange/region.

Data comes from Yahoo Finance and is cached for 15 minutes.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (defaults to http://localhost:8501).

### Command-line summary (optional)

For a quick text-only momentum/volume dump without the UI:

```bash
python main.py
```

## Customise the watchlist

Edit the `TICKERS` list at the top of `app.py` (and `main.py`). Use Yahoo
Finance suffixes for non-US listings, e.g. `.NS` (NSE), `.BO` (BSE),
`.L` (LSE).

---

ℹ️ Informational only — not investment advice. Yahoo Finance data may be
delayed and occasional tickers may fail to resolve.
