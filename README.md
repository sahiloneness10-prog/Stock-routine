# 📈 Stock-routine — Watchlist Momentum Dashboard

A visual, interactive [Streamlit](https://streamlit.io) dashboard that tracks
price momentum, volume shifts and the latest news for a custom stock watchlist.
Data is pulled from Yahoo Finance via [`yfinance`](https://github.com/ranaroussi/yfinance)
and cached for 15 minutes.

## What it shows

For every ticker in your watchlist:

| Metric | Description |
| --- | --- |
| **3D %** | Price change over the last 3 trading days |
| **1W %** | Price change over the last week (~5 trading days) |
| **1M %** | Price change over the last month (~21 trading days) |
| **Volume Δ%** | Latest session volume vs. the trailing 20-day average |
| **Trend** | A 30-day sparkline coloured by direction |
| **News** | Recent headlines, press releases & **regulatory / filing flags** |

### Views

- **🗂️ Cards** — a responsive grid of colour-accented ticker cards with sparklines,
  3D/1W/1M chips and volume change. Filterable and sortable from the sidebar.
- **📋 Table** — a heat-mapped table of every metric.
- **📊 Movers** — the biggest gainers and losers for the chosen window.
- **🌳 Treemap** — all tickers grouped by market (US / UK / India), coloured by % move.
- **🔎 Detail & news** — a 6-month candlestick + volume chart and a categorised news
  feed (regulatory / filing items are flagged separately from general news).

The sidebar adds a focus-window selector, sort controls, a ticker search filter,
a minimum-move filter and a one-click data refresh.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (default <http://localhost:8501>).

Prefer the terminal? `python main.py` prints a plain-text momentum summary.

## Customising the watchlist

Edit the `TICKERS` list at the top of `app.py` (and `main.py`). Use the Yahoo
Finance symbol convention, e.g. `.NS` for NSE India, `.L` for London, `.BO` for
BSE India. A handful of symbols may occasionally fail to resolve on Yahoo —
these are listed under "unresolved" in the dashboard.

## Notes

- Regulatory flags are keyword heuristics over the headline/summary, not an
  exhaustive regulatory feed.
- Informational only — **not investment advice**. Yahoo Finance data may be delayed.
