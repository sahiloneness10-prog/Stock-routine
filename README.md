# Stock-routine

Watchlist momentum tracker — 3-day / 1-week / 1-month price moves, volume shifts,
and the news / regulatory catalysts behind the biggest moves.

## Two ways to view it

| File | Use |
|---|---|
| `app.py` | Full visual **Streamlit** dashboard (tables, heatmap, candlestick charts, per-ticker news). Run locally: `streamlit run app.py` |
| `digest.py` | Headless **markdown / console digest** — runs anywhere (CI, scheduled routines) with no `curl_cffi`/TLS-proxy issues. `python digest.py` or `python digest.py --md` |
| `main.py` | Minimal console summary loop. |
| `reports/` | Dated digest snapshots (movers + catalysts), e.g. `reports/2026-06-26.md`. |

## Notes

- `app.py` uses `yfinance`; in proxied/CI environments `yfinance`'s bundled
  `curl_cffi` can fail TLS, so `digest.py` talks to Yahoo's chart endpoint via plain
  `requests` (honours `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`).
- `0HAO.IL` does not currently resolve on Yahoo and is reported as unresolved.

Install: `pip install -r requirements.txt`

_Informational only — not investment advice. Data may be delayed._
