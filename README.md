# Stock-routine

A visual watchlist dashboard tracking **3-day, 1-week and 1-month price moves,
volume shifts and the latest news / regulatory headlines** for a custom set of
tickers.

## Two ways to view it

### 1. Static HTML dashboard (no dependencies) — `generate_dashboard.py`

Fetches data straight from Yahoo Finance's public JSON endpoints using only the
Python standard library (honours `HTTPS_PROXY` / CA bundles, so it runs in CI and
scheduled jobs where `yfinance` fails), then writes a single self-contained,
theme-aware `watchlist_dashboard.html` you can open in any browser or commit as a
snapshot.

```bash
python3 generate_dashboard.py   # writes watchlist_dashboard.html
```

The dashboard shows:

- A summary strip — top weekly gainer, top decliner, biggest volume spike, coverage
- A sortable table of every ticker with **3-day / 1-week / 1-month % change** and
  **volume vs its 20-day average**, cells colour-graded green ▲ / red ▼ by magnitude
- Headlines (news, releases, regulatory items) behind the largest weekly movers

### 2. Interactive Streamlit app — `app.py`

A richer, live version with candlestick charts, a heatmap and per-ticker news.

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Command-line summary — `main.py`

Prints the same momentum / volume numbers to the terminal.

## Editing the watchlist

Update the `TICKERS` list in `generate_dashboard.py` (and `app.py` / `main.py`).

---
*Informational only — not investment advice. Yahoo Finance data may be delayed and
occasional foreign listings may fail to resolve.*
