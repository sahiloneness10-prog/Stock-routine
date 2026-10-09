# Stock-routine

A visual watchlist dashboard tracking momentum, volume and news across a
66-ticker global watchlist (US, London, India and Tel Aviv listings).

For each ticker it reports:

- **3-day, 1-week and 1-month price % change**
- **Volume change** — latest session vs. the trailing 20-day average
- **A 21-day price sparkline**
- **News, releases and regulatory headlines** that may have moved the stock

Price data comes from Yahoo Finance (via `yfinance`); headlines from Yahoo's
public search endpoint. Informational only — not investment advice.

## Two ways to view it

### 1. Static HTML dashboard (`dashboard.html`)

A single, self-contained file — no server, no network — built from a point-in-time
snapshot. This is what the scheduled routine regenerates and publishes. Open
`dashboard.html` in any browser, or regenerate it:

```bash
pip install -r requirements.txt
python fetch_data.py        # pulls fresh data -> data.json
python build_dashboard.py   # data.json -> dashboard.html
```

It has a sortable/filterable momentum table (diverging red→green cells),
per-region filters, a KPI summary strip and a time-sorted headline feed, and
adapts to light/dark themes and phone widths.

### 2. Interactive Streamlit app (`app.py`)

A live, always-fresh dashboard with candlestick charts and a per-ticker news
drill-down:

```bash
pip install -r requirements.txt
streamlit run app.py
```

A plain-text command-line summary is also available via `python main.py`.

## Files

| File | Purpose |
|------|---------|
| `fetch_data.py` | Fetch prices + headlines → `data.json` |
| `build_dashboard.py` | Render `data.json` → self-contained `dashboard.html` |
| `dashboard.html` | Latest generated static dashboard |
| `data.json` | Latest market snapshot |
| `app.py` | Interactive Streamlit dashboard |
| `main.py` | Command-line watchlist summary |

To change the watchlist, edit the `TICKERS` list in `fetch_data.py` (and
`app.py` / `main.py` to match).
