# Stock-routine — Watchlist Pulse

A visual watchlist dashboard tracking **3-day / 1-week / 1-month price moves**,
**volume vs. the trailing 20-day average**, and the **latest news, releases and
regulatory headlines** for a custom list of tickers spanning US, London (`.L`),
India (`.NS` / `.BO`) and OTC markets.

## Two ways to run it

### 1. Static HTML snapshot (no server) — `generate_dashboard.py`
Fetches the data straight from Yahoo Finance's public JSON endpoints via
`requests` and writes a single self-contained `dashboard.html` with everything
baked in — sortable/filterable table, colour-coded momentum cells, a 1-week
heatmap, a click-to-open detail drawer with per-ticker news, and a
"biggest movers & why" section. Ideal for scheduled runs, e-mailing or hosting.

```bash
pip install requests
python generate_dashboard.py            # writes dashboard.html
python generate_dashboard.py out.html   # custom output path
```

Because it uses `requests`, it honours `HTTPS_PROXY` / `REQUESTS_CA_BUNDLE` and
works in sandboxed environments where the `yfinance` curl backend cannot reach
the network.

### 2. Interactive Streamlit app — `app.py`
The full live dashboard with candlestick charts and an in-app refresh.

```bash
pip install -r requirements.txt
streamlit run app.py
```

`main.py` is a quick command-line summary of the same metrics.

## Editing the watchlist
The ticker list lives at the top of `generate_dashboard.py`, `app.py` and
`main.py` — edit it in place.

---
*Informational only — not investment advice. Data via Yahoo Finance may be delayed.*
