# Stock-routine

A visual watchlist dashboard showing **3-day / 1-week / 1-month** price moves,
**volume shifts**, and **catalyst headlines** (news, earnings, regulatory
updates) for a custom list of tickers.

## Two ways to view it

### 1. Static snapshot — `generate_dashboard.py`
Fetches the data and renders a single self-contained, styled
**`dashboard.html`** (plus `metrics.json`). No server needed — open the HTML
anywhere. Ideal for scheduled runs, sharing, or a quick glance.

```bash
pip install -r requirements.txt
python generate_dashboard.py      # writes dashboard.html + metrics.json
```

Catalyst headlines are pulled in from an optional **`news.json`**
(`{ "TICKER": [ {title, source, date, url, summary}, ... ] }`). When present,
they render in the "Catalysts" section; the file is refreshed each run with the
notable movers' news.

### 2. Interactive app — `app.py`
A Streamlit dashboard with a sortable table, a heatmap, per-ticker candlestick
charts and a news feed.

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Command-line summary — `main.py`
A plain-text dump of the same momentum/volume metrics.

## Metrics
- **3-Day / 1-Week / 1-Month %** — close-to-close over 3 / 5 / 21 trading days.
- **Vol vs 20d** — latest session volume vs the trailing 20-day average.
- Data via Yahoo Finance (may be delayed and split/dividend-adjusted).

> ℹ️ Informational only — not investment advice.
