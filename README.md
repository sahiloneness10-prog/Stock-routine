# Stock-routine — Watchlist Pulse

A visual dashboard of momentum, volume shifts and news catalysts across a custom
stock watchlist. It tracks, for every ticker:

- **3-day / 1-week / 1-month price change** (3, 5 and 21 trading-day look-backs)
- **Volume change** — latest session vs. its trailing 20-day average
- **News, releases & regulatory headlines** for the notable movers

The watchlist spans US, UK (`.L`), India (`.NS` / `.BO`) and other listings.

## Two ways to view it

### 1. Static snapshot — `snapshot.py`
Generates a single self-contained `dashboard.html` (heat-mapped table, sparklines,
mover spotlight, sortable/filterable, light + dark). No server, no `yfinance` —
just `requests` hitting Yahoo Finance's public JSON endpoints, so it runs cleanly
in headless / CI / proxied environments and produces a shareable file.

```bash
pip install requests
python3 snapshot.py            # writes dashboard.html
open dashboard.html            # or host it anywhere
```

Behind a TLS-intercepting proxy, point requests at the CA bundle:

```bash
REQUESTS_CA_BUNDLE=/path/to/ca.crt python3 snapshot.py
```

### 2. Interactive app — `app.py`
A live [Streamlit](https://streamlit.io) dashboard with candlestick charts, a
heatmap tab and a per-ticker news feed (via `yfinance`).

```bash
pip install -r requirements.txt
streamlit run app.py
```

### CLI summary — `main.py`
Prints the same momentum + volume figures to the terminal.

## Editing the watchlist
Change the `TICKERS` list at the top of `snapshot.py`, `app.py` and `main.py`.

---
_Data via Yahoo Finance and may be delayed. Informational only — not investment advice._
