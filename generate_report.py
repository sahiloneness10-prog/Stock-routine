"""
Standalone HTML dashboard generator
====================================
Renders a self-contained, visually styled watchlist report (no server needed)
to ``watchlist_report.html``. Mirrors the metrics shown in ``app.py``:
3-day / 1-week / 1-month price % change, volume change vs 20-day average, and
the latest headlines for the notable movers.

Run with:
    python generate_report.py
"""

from __future__ import annotations

import datetime as dt
import html

import pandas as pd

from routine import (
    MOVE_THRESHOLD,
    VOLUME_THRESHOLD,
    TICKERS,
    build_metrics,
    load_news,
)

PCT_COLS = ["3D", "1W", "1M", "Volume"]


def _cell(val: float) -> str:
    if pd.isna(val):
        return '<td class="na">—</td>'
    shade = min(abs(val) / 15, 1.0)
    if val > 0:
        bg = f"rgba(38,166,91,{0.12 + 0.5 * shade})"
        cls = "pos"
    elif val < 0:
        bg = f"rgba(231,76,60,{0.12 + 0.5 * shade})"
        cls = "neg"
    else:
        bg, cls = "transparent", ""
    return f'<td class="{cls}" style="background:{bg}">{val:+.1f}%</td>'


def _news_html(ticker: str) -> str:
    items = load_news(ticker, limit=2)
    if not items:
        return '<div class="news-empty">No recent headlines.</div>'
    out = []
    for n in items:
        meta = " · ".join(x for x in [n["publisher"], n["published"][:10]] if x)
        title = html.escape(n["title"])
        if n["url"]:
            title = f'<a href="{html.escape(n["url"])}" target="_blank">{title}</a>'
        out.append(f'<div class="news"><span class="news-t">{title}</span>'
                    f'<span class="news-m">{html.escape(meta)}</span></div>')
    return "".join(out)


def build_html() -> str:
    df, failed = build_metrics()
    if df.empty:
        return "<html><body><h1>No data could be loaded.</h1></body></html>"

    df = df.sort_values("1W", ascending=False, na_position="last")
    now = dt.datetime.utcnow().strftime("%b %d, %Y %H:%M UTC")

    gainers = int((df["1W"] > 0).sum())
    losers = int((df["1W"] < 0).sum())
    best = df.loc[df["1W"].idxmax()] if df["1W"].notna().any() else None
    worst = df.loc[df["1W"].idxmin()] if df["1W"].notna().any() else None

    # notable movers
    def notable(r) -> bool:
        if any(pd.notna(r[w]) and abs(r[w]) >= MOVE_THRESHOLD for w in ["3D", "1W", "1M"]):
            return True
        return pd.notna(r["Volume"]) and r["Volume"] >= VOLUME_THRESHOLD

    movers = df[df.apply(notable, axis=1)].copy()
    movers["_mag"] = movers[["3D", "1W", "1M"]].abs().max(axis=1)
    movers = movers.sort_values("_mag", ascending=False).head(12)

    rows = "".join(
        f"<tr><td class='tk'>{html.escape(r['Ticker'])}</td>"
        f"<td class='px'>{r['Price']:,.2f}</td>"
        f"{_cell(r['3D'])}{_cell(r['1W'])}{_cell(r['1M'])}{_cell(r['Volume'])}</tr>"
        for _, r in df.iterrows()
    )

    mover_cards = "".join(
        f"<div class='card'><div class='card-h'><span class='tk'>{html.escape(r['Ticker'])}</span>"
        f"<span class='card-px'>{r['Price']:,.2f}</span></div>"
        f"<div class='chips'>"
        f"<span class='chip {'up' if r['1W'] >= 0 else 'down'}'>1W {r['1W']:+.1f}%</span>"
        f"<span class='chip {'up' if (pd.notna(r['1M']) and r['1M']) >= 0 else 'down'}'>1M "
        f"{r['1M']:+.1f}%</span>"
        f"<span class='chip vol'>Vol {r['Volume']:+.0f}%</span></div>"
        f"{_news_html(r['Ticker'])}</div>"
        for _, r in movers.iterrows()
    )

    kpi = lambda label, val: f"<div class='kpi'><div class='kpi-v'>{val}</div><div class='kpi-l'>{label}</div></div>"
    kpis = "".join([
        kpi("Tickers loaded", f"{len(df)}/{len(TICKERS)}"),
        kpi("Gainers (1W)", gainers),
        kpi("Losers (1W)", losers),
        kpi("Top 1W", f"{best['Ticker']} {best['1W']:+.1f}%" if best is not None else "—"),
        kpi("Worst 1W", f"{worst['Ticker']} {worst['1W']:+.1f}%" if worst is not None else "—"),
    ])

    failed_note = (f"<p class='failed'>No data returned for: {html.escape(', '.join(failed))}</p>"
                   if failed else "")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Dashboard</title>
<style>
  :root {{ --bg:#0d0f14; --panel:#161a22; --line:#262c38; --txt:#e6e9ef; --mut:#8b94a7; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--txt);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:32px 20px 60px; }}
  h1 {{ font-size:1.7rem; margin:0 0 4px; letter-spacing:.3px; }}
  .sub {{ color:var(--mut); margin:0 0 24px; font-size:.9rem; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
    gap:12px; margin-bottom:28px; }}
  .kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:14px;
    padding:16px 18px; }}
  .kpi-v {{ font-size:1.35rem; font-weight:650; }}
  .kpi-l {{ color:var(--mut); font-size:.78rem; margin-top:4px; text-transform:uppercase;
    letter-spacing:.5px; }}
  h2 {{ font-size:1.1rem; margin:32px 0 14px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--panel);
    border:1px solid var(--line); border-radius:14px; overflow:hidden; font-size:.9rem; }}
  th, td {{ padding:9px 12px; text-align:right; border-bottom:1px solid var(--line); }}
  th {{ background:#1b202a; color:var(--mut); font-weight:600; text-transform:uppercase;
    font-size:.72rem; letter-spacing:.5px; position:sticky; top:0; }}
  th:first-child, td:first-child {{ text-align:left; }}
  tr:last-child td {{ border-bottom:none; }}
  td.tk {{ font-weight:650; }}
  td.px {{ color:var(--mut); }}
  td.na {{ color:#555; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:14px; }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px; }}
  .card-h {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; }}
  .card-h .tk {{ font-size:1.15rem; font-weight:700; }}
  .card-px {{ color:var(--mut); }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }}
  .chip {{ font-size:.75rem; padding:3px 9px; border-radius:999px; font-weight:600; }}
  .chip.up {{ background:rgba(38,166,91,.18); color:#5fe39b; }}
  .chip.down {{ background:rgba(231,76,60,.18); color:#ff8a7d; }}
  .chip.vol {{ background:rgba(120,140,200,.16); color:#9fb0e0; }}
  .news {{ display:block; padding:7px 0; border-top:1px solid var(--line); }}
  .news-t {{ display:block; font-size:.86rem; line-height:1.35; }}
  .news-t a {{ color:#8fb8ff; text-decoration:none; }}
  .news-m {{ display:block; color:var(--mut); font-size:.72rem; margin-top:2px; }}
  .news-empty {{ color:var(--mut); font-size:.82rem; border-top:1px solid var(--line); padding-top:8px; }}
  .failed {{ color:var(--mut); font-size:.8rem; }}
  footer {{ color:var(--mut); font-size:.75rem; margin-top:36px; }}
</style></head>
<body><div class="wrap">
  <h1>📈 Watchlist Dashboard</h1>
  <p class="sub">3-day · 1-week · 1-month price moves, volume shifts &amp; headlines · {now} · data via Yahoo Finance</p>
  <div class="kpis">{kpis}</div>

  <h2>🔥 Notable movers &amp; news</h2>
  <div class="cards">{mover_cards}</div>

  <h2>📋 Full watchlist <span style="color:var(--mut);font-weight:400;font-size:.85rem">(sorted by 1-week move)</span></h2>
  <table><thead><tr><th>Ticker</th><th>Price</th><th>3D %</th><th>1W %</th><th>1M %</th><th>Volume Δ%</th></tr></thead>
  <tbody>{rows}</tbody></table>
  {failed_note}

  <footer>Informational only — not investment advice. Yahoo Finance data may be delayed.
  Generated by generate_report.py. For the interactive version run <code>streamlit run app.py</code>.</footer>
</div></body></html>"""


def main() -> None:
    out = "watchlist_report.html"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build_html())
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
