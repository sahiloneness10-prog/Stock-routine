# Stock-routine — Watchlist Pulse

A visual watchlist dashboard that tracks **3-day / 1-week / 1-month price moves**,
**volume shifts**, and **news / regulatory context** for a custom list of ~66
global tickers (US, UK LSE, India NSE/BSE, OTC ADRs).

## What's here

| File | Purpose |
|------|---------|
| `generate_dashboard.py` | **Snapshot generator.** Fetches live prices, computes the metrics, and writes a single self-contained `dashboard.html` (KPI tiles, biggest-movers strip, dated news/context cards, and a sortable, colour-coded table with 21-day sparklines). Light/dark aware. |
| `dashboard.html` | The latest rendered snapshot — open it in any browser, no server needed. |
| `context.json` | Curated, dated news/context notes keyed by ticker, folded into the dashboard's "News & catalysts" section. |
| `app.py` | Interactive [Streamlit](https://streamlit.io) version (candlestick charts + per-ticker news). Run with `streamlit run app.py`. |
| `main.py` | Minimal command-line summary of the same metrics. |

## Generate a fresh snapshot

```bash
pip install -r requirements.txt
python generate_dashboard.py --out dashboard.html --context context.json
```

Optional: `--data-out data.json` also dumps the raw metrics as JSON.

The generator is designed to run on a schedule — each run overwrites
`dashboard.html` with a fresh snapshot. Price/volume metrics are always live;
the news notes in `context.json` are curated and should be refreshed when the
story changes.

## Notes

- Data comes from Yahoo Finance and may be delayed; `% ` windows use trading-day
  look-backs (3D ≈ 3 sessions, 1W ≈ 5, 1M ≈ 21).
- Occasional tickers may fail to resolve (e.g. delisted/unknown symbols) — these
  are listed at the bottom of the dashboard.
- **Informational only — not investment advice.**
