# Stock-routine

A visual watchlist dashboard tracking price momentum, volume shifts and news
headlines across a custom list of ~66 global tickers.

## Two ways to view it

### 1. Static snapshot — `generate_dashboard.py` (no dependencies)

Fetches live data from Yahoo Finance and renders a single, self-contained,
theme-aware `dashboard.html` you can open in any browser, email, or host
anywhere. Standard library only — nothing to `pip install`. Ideal for a
scheduled job that publishes a snapshot.

```bash
python generate_dashboard.py            # writes ./dashboard.html
python generate_dashboard.py out.html   # custom output path
```

The committed `dashboard.html` is the most recent generated snapshot.

### 2. Interactive app — `app.py` (Streamlit)

A live, filterable dashboard with sortable tables, a heatmap and per-ticker
candlestick charts plus news.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What it shows

For every ticker in the watchlist:

- **3-day / 1-week / 1-month price % change** (trading-day look-backs)
- **Volume change** vs the trailing 20-day average
- **30-day price sparkline**
- **News, releases and regulatory headlines** for the biggest movers

Gains are green with a ▲, losses red with a ▼ — colour is never the only cue,
and cell shading scales with the size of the move.

## Watchlist

Edit the `TICKERS` list at the top of `generate_dashboard.py` (or `app.py`) to
change what's tracked. Suffixes follow Yahoo Finance conventions — `.NS` (NSE
India), `.L` (London), `.BO` (BSE), `.IL` (London IOB), etc.

---

_Informational only — not investment advice. Prices may be delayed and some
foreign or thinly-traded tickers may fail to resolve._
