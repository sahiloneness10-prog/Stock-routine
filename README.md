# Stock-routine

A watchlist dashboard that tracks short-term price momentum, volume shifts and
the news behind the moves for a custom list of tickers (US, India `.NS`/`.BO`,
London `.L`, and ADRs).

Two ways to view it:

## 1. Static snapshot dashboard (`dashboard.html`)

A self-contained, shareable HTML page — **"Watchlist Pulse"** — with no runtime
dependencies. It shows:

- KPI tiles (gainers/decliners, average 1-week move, top mover, biggest volume spike)
- A "market read" that auto-summarises where the watchlist is leaning and which
  names are driving it
- A sortable, filterable **movement board**: 30-day sparkline, price, and
  1-day / 3-day / 1-week / 1-month % changes plus volume vs the 20-session
  average, with each cell shaded by move size (green up, red down) and labelled
  with the signed number so meaning never rests on colour alone
- A **news / releases / regulatory** feed for the most active names

### Rebuild the snapshot

```bash
pip install -r requirements.txt
python fetch_data.py data.json        # pull prices + news from Yahoo Finance
python build_dashboard.py data.json dashboard.html
```

`fetch_data.py` writes a JSON snapshot; `build_dashboard.py` bakes it into a
standalone page (the data is embedded, so the file works offline and as a link).

## 2. Interactive Streamlit app (`app.py`)

A live dashboard with candlestick charts and a per-ticker news view:

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Watchlist

Edit the `TICKERS` list at the top of `fetch_data.py` (and `app.py`) to change
what is tracked.

---

*Informational only — not investment advice. Prices via Yahoo Finance may be
delayed, and occasional tickers may fail to resolve.*
