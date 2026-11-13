# Stock Watchlist Dashboard

A visual dashboard tracking price momentum, volume changes and news catalysts
across a personal watchlist of ~66 global tickers (US, LSE, NSE/BSE, OTC ADRs).

## Two ways to view it

### 1. Static dashboard — `index.html` (recommended for the scheduled routine)
A single self-contained HTML file with:
- **3-day, 1-week and 1-month % price moves** per ticker
- **Volume change** vs the 20-day average
- **Sparklines** (~1 month of closes) and a **sortable table**
- **News & catalysts** section — earnings, regulatory and flow events behind the biggest moves
- Summary stat tiles (gainers/decliners, average move, top mover, biggest volume spike)
- Light & dark mode, mobile friendly, no server required

Regenerate with live data:

```bash
python3 generate_dashboard.py   # writes index.html + data.json
```

Then open `index.html` in any browser. Data is pulled from Yahoo Finance (delayed).

### 2. Interactive app — `app.py` (Streamlit)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- `FLTR.L` is shown as **FLUT** — Flutter Entertainment moved its primary listing from the LSE to the NYSE.
- `0HAO.IL` is not available on the data source and is flagged as such.
- % changes use trading-day closes (3-day ≈ 3 sessions, 1-week ≈ 5, 1-month ≈ 21).
- The `NEWS[]` list in `generate_dashboard.py` is curated from public reporting and should be refreshed periodically.
- Informational snapshot only — **not investment advice**.
