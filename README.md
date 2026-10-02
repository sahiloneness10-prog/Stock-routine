# Watchlist Pulse

A visual dashboard for a global stock watchlist: 3-day / 1-week / 1-month price
moves, volume shifts vs the 20-day average, and recent headlines, releases and
regulatory news per ticker.

## Three ways to use it

| Command | What it does |
|---|---|
| `python generate_snapshot.py` | Writes a self-contained **`watchlist_pulse.html`** dashboard you can open in any browser or host anywhere. No server. Ideal for a scheduled job. |
| `streamlit run app.py` | Interactive dashboard (sortable table, heatmap, candlestick charts, per-ticker news) in your browser. |
| `python main.py` | Quick text summary in the terminal. |

## Setup

```bash
pip install -r requirements.txt
```

## The watchlist

Edit the `TICKERS` list (kept in sync across `generate_snapshot.py`, `app.py`
and `main.py`). Suffixes pick the exchange: `.NS` / `.BO` (India), `.L`
(London), `.IL` (Tel Aviv); bare symbols are US-listed. Prices show in each
listing's local currency.

## Notes

- Data comes from Yahoo Finance and may be delayed; occasional tickers won't
  resolve (they're listed as such in the dashboard).
- Percentages are trading-day look-backs: 3, 5 and 21 sessions.
- Informational only — not investment advice.
