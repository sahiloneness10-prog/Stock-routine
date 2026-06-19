# Stock-routine

A visual watchlist dashboard plus a headless digest for tracking momentum,
volume shifts and news across a custom stock watchlist.

## Metrics tracked

- **3-day / 1-week / 1-month price % change**
- **Volume change** vs the trailing 20-day average
- **News, releases & regulatory headlines** per ticker (via Yahoo Finance)

## Components

| File | What it does |
|------|--------------|
| `app.py` | Interactive Streamlit dashboard — sortable overview table, % heatmap, per-ticker candlestick chart and news feed. |
| `routine.py` | Headless digest — prints the full watchlist table and ranks the notable movers (price moves ≥ 7% or volume spikes ≥ 75%) with their latest headlines. Ideal for scheduled runs / notifications. |
| `main.py` | Minimal CLI summary of price moves and volume per ticker. |

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py   # visual dashboard
python routine.py      # headless digest (notable movers + news)
python main.py         # quick per-ticker CLI summary
```

Data is sourced from Yahoo Finance and may be delayed. Informational only —
not investment advice.
