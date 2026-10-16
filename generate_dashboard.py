"""
Static watchlist dashboard generator
=====================================
Fetches live prices for the watchlist, computes 3-day / 1-week / 1-month price
moves and a volume shift, and renders a single self-contained ``dashboard.html``
snapshot: KPI tiles, a "biggest movers" strip, dated news/context cards and a
sortable, colour-coded table with 21-day sparklines. Light/dark aware.

Designed to be run on a schedule (it writes a fresh snapshot each time):

    python3 generate_dashboard.py --out dashboard.html [--context context.json]

The optional ``--context`` JSON carries curated, dated news notes keyed by
ticker (see the repo's example). Price/volume metrics are always live.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = [
    "VENU", "DUKR", "LNZA", "SIDU", "STLTECH.NS", "HFCL.NS", "TEJASNET.NS",
    "HLIT", "NBIS", "PENG", "NOK", "SLOIF", "TE", "FLNC", "MITK", "HUMA",
    "AAOI", "BE", "SWMR", "AMPX", "KRKNF", "AXTI", "COHR", "VYX", "NATL",
    "FLTR.L", "LODE", "SATL", "SNDK", "MOH", "HAL", "PFE", "EWZ", "MELI",
    "DUOL", "KLAR", "FIG", "ASML", "TATE.L", "HAIN", "XIACY", "VWSYF", "ZETA",
    "GYM.L", "GNC.L", "BYDDY", "BYND", "DKS", "OTLY", "SNOW", "SAP", "WDAY",
    "MKS.L", "JD.L", "TRN.L", "NTPCGREEN.NS", "HMC", "GSK.L", "TSM",
    "TIMEX.BO", "0HAO.IL", "NVDA", "BT-A.L", "JDW.L", "SBRY.L", "ADTN",
]

# Trading-day look-backs for each window.
WINDOWS = {"d3": 3, "w1": 5, "m1": 21}

# Friendly names so the dashboard reads as more than tickers.
NAMES = {
    "VENU": "Venu Holding", "DUKR": "DRIVEKRM / Dukr", "LNZA": "LanzaTech Global",
    "SIDU": "Sidus Space", "STLTECH.NS": "Sterlite Technologies", "HFCL.NS": "HFCL",
    "TEJASNET.NS": "Tejas Networks", "HLIT": "Harmonic", "NBIS": "Nebius Group",
    "PENG": "Penguin Solutions", "NOK": "Nokia", "SLOIF": "Sunlands / Solo",
    "TE": "Tele Columbus / TE", "FLNC": "Fluence Energy", "MITK": "Mitek Systems",
    "HUMA": "Humacyte", "AAOI": "Applied Optoelectronics", "BE": "Bloom Energy",
    "SWMR": "Swarmer", "AMPX": "Amprius Technologies", "KRKNF": "Kraken Robotics",
    "AXTI": "AXT Inc", "COHR": "Coherent", "VYX": "NCR Voyix", "NATL": "NCR Atleos",
    "FLTR.L": "Flutter Entertainment", "LODE": "Comstock", "SATL": "Satellogic",
    "SNDK": "SanDisk", "MOH": "Molina Healthcare", "HAL": "Halliburton",
    "PFE": "Pfizer", "EWZ": "iShares MSCI Brazil ETF", "MELI": "MercadoLibre",
    "DUOL": "Duolingo", "KLAR": "Klarna", "FIG": "Figma", "ASML": "ASML Holding",
    "TATE.L": "Tate & Lyle", "HAIN": "Hain Celestial", "XIACY": "Xiaomi (ADR)",
    "VWSYF": "Vestas Wind Systems", "ZETA": "Zeta Global", "GYM.L": "The Gym Group",
    "GNC.L": "Greencore Group", "BYDDY": "BYD Co (ADR)", "BYND": "Beyond Meat",
    "DKS": "Dick's Sporting Goods", "OTLY": "Oatly Group", "SNOW": "Snowflake",
    "SAP": "SAP SE", "WDAY": "Workday", "MKS.L": "Marks & Spencer",
    "JD.L": "JD Sports Fashion", "TRN.L": "Trainline", "NTPCGREEN.NS": "NTPC Green Energy",
    "HMC": "Honda Motor", "GSK.L": "GSK plc", "TSM": "Taiwan Semiconductor",
    "TIMEX.BO": "Timex Group India", "0HAO.IL": "0HAO.IL", "NVDA": "NVIDIA",
    "BT-A.L": "BT Group", "JDW.L": "JD Wetherspoon", "SBRY.L": "Sainsbury's",
    "ADTN": "Adtran",
}

# Exchange / region tag derived from the ticker suffix.
SUFFIX_MARKET = {
    ".NS": "India (NSE)", ".BO": "India (BSE)", ".L": "UK (LSE)",
    ".IL": "Israel (TASE)",
}


# --------------------------------------------------------------------------- #
# Data layer
# --------------------------------------------------------------------------- #
def market_of(ticker: str) -> str:
    for sfx, mkt in SUFFIX_MARKET.items():
        if ticker.endswith(sfx):
            return mkt
    return "US / OTC"


def _series(data: pd.DataFrame, ticker: str, field: str) -> pd.Series:
    try:
        s = data[ticker][field] if isinstance(data.columns, pd.MultiIndex) else data[field]
    except (KeyError, TypeError):
        return pd.Series(dtype="float64")
    return pd.to_numeric(s, errors="coerce").dropna()


def _pct(series: pd.Series, periods: int):
    s = series.dropna()
    if len(s) <= periods:
        return None
    prev = s.iloc[-1 - periods]
    if prev == 0 or pd.isna(prev):
        return None
    return round((s.iloc[-1] - prev) / prev * 100, 2)


def _volume_change(volume: pd.Series):
    v = volume.dropna()
    if len(v) < 6:
        return None
    latest = v.iloc[-1]
    base = v.iloc[-21:-1].mean() if len(v) > 21 else v.iloc[:-1].mean()
    if not base or pd.isna(base):
        return None
    return round((latest - base) / base * 100, 1)


def fetch_rows(tickers: list[str]) -> list[dict]:
    data = yf.download(
        tickers, period="3mo", interval="1d", group_by="ticker",
        auto_adjust=True, progress=False, threads=True,
    )
    rows = []
    for t in tickers:
        close = _series(data, t, "Close")
        volume = _series(data, t, "Volume")
        if close.empty:
            rows.append({"ticker": t, "name": NAMES.get(t, t),
                         "market": market_of(t), "ok": False})
            continue
        rows.append({
            "ticker": t, "name": NAMES.get(t, t), "market": market_of(t), "ok": True,
            "price": round(float(close.iloc[-1]), 4),
            "d3": _pct(close, 3), "w1": _pct(close, 5), "m1": _pct(close, 21),
            "vol": _volume_change(volume),
            "last_date": str(close.index[-1].date()),
            "spark": [round(float(x), 4) for x in close.iloc[-21:].tolist()],
        })
    return rows


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #
def e(x) -> str:
    return html.escape(str(x), quote=True)


def diverging_style(val, cap: float = 15.0) -> str:
    """Green (up) / red (down) diverging tint, intensity scaled by magnitude."""
    if val is None:
        return ""
    t = min(abs(val) / cap, 1.0)
    alpha = 0.10 + 0.70 * t
    if val > 0:
        return f"background:color-mix(in srgb, var(--up) {int(alpha*100)}%, transparent);"
    if val < 0:
        return f"background:color-mix(in srgb, var(--down) {int(alpha*100)}%, transparent);"
    return ""


def fmt_pct(val) -> str:
    return f"{val:+.2f}%" if val is not None else "—"


def fmt_vol(val) -> str:
    return f"{val:+.0f}%" if val is not None else "—"


def sparkline(values, up: bool, w: int = 120, h: int = 30) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = [
        (i / (n - 1) * (w - 2) + 1, h - 1 - (v - lo) / rng * (h - 2))
        for i, v in enumerate(vals)
    ]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    colour = "var(--up)" if up else "var(--down)"
    lx, ly = pts[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.2" fill="{colour}"/></svg>'
    )


def kpi_tile(label: str, value: str, sub: str = "", tone: str = "") -> str:
    tone_cls = f" tile--{tone}" if tone else ""
    sub_html = f'<div class="tile__sub">{sub}</div>' if sub else ""
    return (
        f'<div class="tile{tone_cls}"><div class="tile__label">{e(label)}</div>'
        f'<div class="tile__value">{value}</div>{sub_html}</div>'
    )


def mover_card(r: dict) -> str:
    up = (r.get("w1") or 0) >= 0
    cls = "mv--up" if up else "mv--down"
    arrow = "▲" if up else "▼"
    return (
        f'<div class="mv {cls}"><div class="mv__top"><span class="mv__tkr">{e(r["ticker"])}</span>'
        f'<span class="mv__chg">{arrow} {fmt_pct(r.get("w1"))}</span></div>'
        f'<div class="mv__name">{e(r["name"])}</div>'
        f'<div class="mv__meta">3D {fmt_pct(r.get("d3"))} &middot; 1M {fmt_pct(r.get("m1"))} '
        f'&middot; Vol {fmt_vol(r.get("vol"))}</div></div>'
    )


def news_card(ticker: str, name: str, notes: list[dict]) -> str:
    items = ""
    for note in notes:
        src = note.get("source", "")
        url = note.get("url", "")
        src_html = f' &middot; <a href="{e(url)}" target="_blank" rel="noopener">{e(src)}</a>' if url else (f" &middot; {e(src)}" if src else "")
        items += f'<p class="news__text">{e(note["text"])}<span class="news__src">{src_html}</span></p>'
    return (
        f'<div class="news"><div class="news__head"><span class="news__tkr">{e(ticker)}</span>'
        f'<span class="news__name">{e(name)}</span></div>{items}</div>'
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
def render(rows: list[dict], context: dict, generated: str) -> str:
    ok = [r for r in rows if r.get("ok")]
    failed = [r["ticker"] for r in rows if not r.get("ok")]

    def by(key, rev=True, absval=False):
        xs = [r for r in ok if r.get(key) is not None]
        xs.sort(key=lambda r: (abs(r[key]) if absval else r[key]), reverse=rev)
        return xs

    w1_sorted = by("w1")
    gainers = [r for r in ok if (r.get("w1") or 0) > 0]
    losers = [r for r in ok if (r.get("w1") or 0) < 0]
    vol_sorted = by("vol")
    best = w1_sorted[0] if w1_sorted else None
    worst = w1_sorted[-1] if w1_sorted else None
    top_vol = vol_sorted[0] if vol_sorted else None
    avg_w1 = np.nanmean([r["w1"] for r in ok if r.get("w1") is not None]) if ok else float("nan")

    # KPI strip
    tiles = [
        kpi_tile("Tickers loaded", f"{len(ok)}<span class='tile__unit'>/{len(rows)}</span>"),
        kpi_tile("Gainers · 1W", str(len(gainers)),
                 f"vs {len(losers)} losers", tone="up" if len(gainers) >= len(losers) else "down"),
        kpi_tile("Avg move · 1W",
                 f"<span class='{'pos' if avg_w1 >= 0 else 'neg'}'>{avg_w1:+.2f}%</span>" if not np.isnan(avg_w1) else "—"),
    ]
    if best is not None:
        tiles.append(kpi_tile("Top mover · 1W",
                              f"{e(best['ticker'])} <span class='pos'>{fmt_pct(best['w1'])}</span>",
                              e(best["name"]), tone="up"))
    if worst is not None:
        tiles.append(kpi_tile("Worst mover · 1W",
                              f"{e(worst['ticker'])} <span class='neg'>{fmt_pct(worst['w1'])}</span>",
                              e(worst["name"]), tone="down"))
    if top_vol is not None:
        tiles.append(kpi_tile("Biggest volume spike",
                              f"{e(top_vol['ticker'])} {fmt_vol(top_vol['vol'])}",
                              "vs 20-day average"))
    kpi_html = "\n".join(tiles)

    # Movers strips
    up_cards = "".join(mover_card(r) for r in w1_sorted[:5])
    down_cards = "".join(mover_card(r) for r in w1_sorted[::-1][:5])

    # News / context
    notes_map = context.get("notes", {})
    news_order = [r["ticker"] for r in by("w1", absval=True) if r["ticker"] in notes_map]
    for t in notes_map:
        if t not in news_order:
            news_order.append(t)
    news_html = "".join(
        news_card(t, NAMES.get(t, t), notes_map[t]) for t in news_order
    ) or '<p class="muted">No curated context notes for this run.</p>'
    caveat = context.get("caveat", "")

    # Table rows
    trs = []
    for r in w1_sorted:
        up = (r.get("m1") or r.get("w1") or 0) >= 0
        spark = sparkline(r.get("spark", []), up)
        price = f"{r['price']:,.2f}" if r.get("price") is not None else "—"
        trs.append(
            f'<tr>'
            f'<td class="t-tkr"><span class="t-sym">{e(r["ticker"])}</span>'
            f'<span class="t-name">{e(r["name"])}</span></td>'
            f'<td class="t-mkt">{e(r["market"])}</td>'
            f'<td class="num" data-v="{r.get("price") or ""}">{price}</td>'
            f'<td class="num pct" data-v="{r.get("d3") if r.get("d3") is not None else ""}" style="{diverging_style(r.get("d3"))}">{fmt_pct(r.get("d3"))}</td>'
            f'<td class="num pct" data-v="{r.get("w1") if r.get("w1") is not None else ""}" style="{diverging_style(r.get("w1"))}">{fmt_pct(r.get("w1"))}</td>'
            f'<td class="num pct" data-v="{r.get("m1") if r.get("m1") is not None else ""}" style="{diverging_style(r.get("m1"))}">{fmt_pct(r.get("m1"))}</td>'
            f'<td class="num pct" data-v="{r.get("vol") if r.get("vol") is not None else ""}" style="{diverging_style(r.get("vol"), cap=200)}">{fmt_vol(r.get("vol"))}</td>'
            f'<td class="t-spark">{spark}</td>'
            f'</tr>'
        )
    table_rows = "\n".join(trs)
    failed_html = (
        f'<p class="muted failed">No price data returned this run for: {e(", ".join(failed))}</p>'
        if failed else ""
    )

    return TEMPLATE.format(
        generated=e(generated),
        count=len(ok),
        total=len(rows),
        kpis=kpi_html,
        up_cards=up_cards,
        down_cards=down_cards,
        news=news_html,
        caveat=e(caveat),
        table_rows=table_rows,
        failed=failed_html,
    )


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Pulse</title>
<style>
  :root {{
    color-scheme: light;
    --plane:#f4f5f3; --surface:#ffffff; --surface-2:#fafbf9;
    --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
    --line:#e5e6e1; --ring:rgba(11,11,11,.08);
    --up:#0ca30c; --down:#d03b3b; --accent:#2a78d6;
    --pos:#067406; --neg:#bc2f2f;
    --shadow:0 1px 2px rgba(11,11,11,.05),0 8px 24px rgba(11,11,11,.06);
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --plane:#0d0d0d; --surface:#1a1a19; --surface-2:#201f1d;
    --ink:#f0efec; --ink-2:#c3c2b7; --muted:#8f8d86;
    --line:#2c2c2a; --ring:rgba(255,255,255,.08);
    --up:#1fbf4a; --down:#e05656; --accent:#3987e5;
    --pos:#2fd05a; --neg:#f07070;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.45);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --plane:#0d0d0d; --surface:#1a1a19; --surface-2:#201f1d;
      --ink:#f0efec; --ink-2:#c3c2b7; --muted:#8f8d86;
      --line:#2c2c2a; --ring:rgba(255,255,255,.08);
      --up:#1fbf4a; --down:#e05656; --accent:#3987e5;
      --pos:#2fd05a; --neg:#f07070;
      --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.45);
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{
    margin:0; background:var(--plane); color:var(--ink);
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
    line-height:1.5; -webkit-font-smoothing:antialiased;
  }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 16px 64px; }}
  a {{ color:var(--accent); text-decoration:none; }}
  a:hover {{ text-decoration:underline; }}
  .muted {{ color:var(--muted); font-size:13px; }}
  .pos {{ color:var(--pos); }}  .neg {{ color:var(--neg); }}

  header.top {{ display:flex; flex-wrap:wrap; align-items:flex-start; gap:16px; justify-content:space-between; margin-bottom:8px; }}
  .title h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:.2px; }}
  .title p {{ margin:0; color:var(--ink-2); font-size:14px; max-width:60ch; }}
  .stamp {{ text-align:right; font-size:12.5px; color:var(--muted); white-space:nowrap; }}
  .stamp b {{ color:var(--ink-2); font-weight:600; }}
  .theme-btn {{
    margin-top:8px; border:1px solid var(--line); background:var(--surface);
    color:var(--ink-2); border-radius:999px; padding:5px 12px; font-size:12.5px;
    cursor:pointer; font-family:inherit;
  }}
  .theme-btn:hover {{ border-color:var(--muted); }}

  h2.sec {{ font-size:13px; text-transform:uppercase; letter-spacing:.09em; color:var(--muted); margin:34px 0 14px; font-weight:700; }}

  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:12px; margin-top:18px; }}
  .tile {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; padding:14px 16px; box-shadow:var(--shadow); position:relative; overflow:hidden; }}
  .tile::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--accent); opacity:.0; }}
  .tile--up::before {{ background:var(--up); opacity:1; }}
  .tile--down::before {{ background:var(--down); opacity:1; }}
  .tile__label {{ font-size:11.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); font-weight:600; }}
  .tile__value {{ font-size:23px; font-weight:650; margin-top:6px; }}
  .tile__unit {{ font-size:14px; color:var(--muted); font-weight:500; }}
  .tile__sub {{ font-size:12px; color:var(--ink-2); margin-top:3px; }}

  .movers {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .mcol h3 {{ font-size:13px; margin:0 0 10px; color:var(--ink-2); display:flex; align-items:center; gap:7px; }}
  .dot {{ width:9px; height:9px; border-radius:50%; display:inline-block; }}
  .dot.up {{ background:var(--up); }}  .dot.down {{ background:var(--down); }}
  .mv {{ background:var(--surface); border:1px solid var(--line); border-left-width:3px; border-radius:10px; padding:9px 12px; margin-bottom:8px; box-shadow:var(--shadow); }}
  .mv--up {{ border-left-color:var(--up); }}
  .mv--down {{ border-left-color:var(--down); }}
  .mv__top {{ display:flex; justify-content:space-between; align-items:baseline; gap:8px; }}
  .mv__tkr {{ font-weight:700; font-size:14.5px; }}
  .mv__chg {{ font-weight:650; font-size:14px; font-variant-numeric:tabular-nums; }}
  .mv--up .mv__chg {{ color:var(--pos); }}
  .mv--down .mv__chg {{ color:var(--neg); }}
  .mv__name {{ font-size:12.5px; color:var(--ink-2); margin-top:1px; }}
  .mv__meta {{ font-size:11.5px; color:var(--muted); margin-top:3px; font-variant-numeric:tabular-nums; }}

  .news-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px; }}
  .news {{ background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:14px 16px; box-shadow:var(--shadow); }}
  .news__head {{ display:flex; align-items:baseline; gap:8px; margin-bottom:7px; }}
  .news__tkr {{ font-weight:700; background:var(--surface-2); border:1px solid var(--line); padding:1px 8px; border-radius:6px; font-size:13px; }}
  .news__name {{ color:var(--ink-2); font-size:13px; }}
  .news__text {{ font-size:13px; margin:0 0 8px; color:var(--ink); }}
  .news__src {{ color:var(--muted); font-size:11.5px; }}
  .caveat {{ background:var(--surface-2); border:1px solid var(--line); border-radius:10px; padding:11px 14px; font-size:12.5px; color:var(--ink-2); margin-bottom:14px; }}

  .tbl-wrap {{ background:var(--surface); border:1px solid var(--line); border-radius:14px; box-shadow:var(--shadow); overflow:hidden; }}
  table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  thead th {{
    position:sticky; top:0; background:var(--surface-2); color:var(--ink-2);
    font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; font-weight:700;
    text-align:right; padding:11px 12px; border-bottom:1px solid var(--line);
    cursor:pointer; user-select:none; white-space:nowrap;
  }}
  thead th:first-child, thead th.l {{ text-align:left; }}
  thead th:hover {{ color:var(--ink); }}
  thead th .arr {{ opacity:.35; font-size:10px; margin-left:3px; }}
  thead th.sorted .arr {{ opacity:1; color:var(--accent); }}
  tbody td {{ padding:9px 12px; border-bottom:1px solid var(--line); text-align:right; vertical-align:middle; }}
  tbody tr:last-child td {{ border-bottom:0; }}
  tbody tr:hover td {{ background:var(--surface-2); }}
  .num {{ font-variant-numeric:tabular-nums; }}
  .pct {{ font-weight:600; border-radius:0; }}
  .t-tkr {{ text-align:left; min-width:150px; }}
  .t-sym {{ font-weight:700; }}
  .t-name {{ display:block; color:var(--muted); font-size:11.5px; font-weight:400; }}
  .t-mkt {{ text-align:left; color:var(--ink-2); font-size:12px; white-space:nowrap; }}
  .t-spark {{ text-align:right; width:130px; }}
  .spark {{ display:inline-block; vertical-align:middle; }}

  .legend {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin:12px 2px 0; font-size:12px; color:var(--muted); }}
  .legend .scale {{ display:inline-flex; align-items:center; gap:0; border-radius:4px; overflow:hidden; border:1px solid var(--line); }}
  .legend .scale span {{ width:22px; height:12px; display:block; }}

  footer {{ margin-top:30px; font-size:12px; color:var(--muted); border-top:1px solid var(--line); padding-top:14px; }}
  .failed {{ margin-top:12px; }}

  @media (max-width:720px) {{
    .movers {{ grid-template-columns:1fr; }}
    .stamp {{ text-align:left; }}
    header.top {{ flex-direction:column; }}
    .t-mkt {{ display:none; }}
    thead th.mkt-col {{ display:none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="title">
      <h1>📈 Watchlist Pulse</h1>
      <p>Momentum, volume and news context across your {total}-name watchlist &mdash; 3-day, 1-week and 1-month price moves with 21-day trend sparklines. Live prices via Yahoo Finance.</p>
    </div>
    <div>
      <div class="stamp">Snapshot generated<br><b>{generated}</b><br>{count}/{total} tickers loaded</div>
      <button class="theme-btn" id="themeBtn" type="button">◐ Theme</button>
    </div>
  </header>

  <div class="tiles">
    {kpis}
  </div>

  <h2 class="sec">Biggest movers &middot; past week</h2>
  <div class="movers">
    <div class="mcol"><h3><span class="dot up"></span>Top gainers (1W)</h3>{up_cards}</div>
    <div class="mcol"><h3><span class="dot down"></span>Top decliners (1W)</h3>{down_cards}</div>
  </div>

  <h2 class="sec">News &amp; catalysts &middot; context for the big movers</h2>
  <div class="caveat">⚠️ {caveat}</div>
  <div class="news-grid">
    {news}
  </div>

  <h2 class="sec">Full watchlist &middot; click a column to sort</h2>
  <div class="tbl-wrap">
    <table id="tbl">
      <thead><tr>
        <th class="l" data-k="sym" data-t="s">Ticker <span class="arr">↕</span></th>
        <th class="l mkt-col" data-k="mkt" data-t="s">Market <span class="arr">↕</span></th>
        <th data-k="price" data-t="n">Price <span class="arr">↕</span></th>
        <th data-k="d3" data-t="n" class="sorted">3D % <span class="arr">↕</span></th>
        <th data-k="w1" data-t="n">1W % <span class="arr">↕</span></th>
        <th data-k="m1" data-t="n">1M % <span class="arr">↕</span></th>
        <th data-k="vol" data-t="n">Vol Δ <span class="arr">↕</span></th>
        <th class="l">21-day</th>
      </tr></thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>
  <div class="legend">
    <span>% change scale:</span>
    <span class="scale">
      <span style="background:color-mix(in srgb,var(--down) 70%,transparent)"></span>
      <span style="background:color-mix(in srgb,var(--down) 35%,transparent)"></span>
      <span style="background:var(--surface)"></span>
      <span style="background:color-mix(in srgb,var(--up) 35%,transparent)"></span>
      <span style="background:color-mix(in srgb,var(--up) 70%,transparent)"></span>
    </span>
    <span>decline &larr; flat &rarr; gain &middot; Vol Δ = latest session vs 20-day average</span>
  </div>
  {failed}

  <footer>
    ℹ️ Informational only &mdash; not investment advice. Prices are from Yahoo Finance and may be delayed; % windows use trading-day look-backs (3D ≈ 3 sessions, 1W ≈ 5, 1M ≈ 21). News/context notes are the most recent background found and may not reflect intraday events. Verify against official filings before acting.
  </footer>
</div>

<script>
(function() {{
  // Theme toggle (persists per browser; falls back gracefully).
  var root = document.documentElement, btn = document.getElementById('themeBtn');
  try {{ var s = localStorage.getItem('wp-theme'); if (s) root.setAttribute('data-theme', s); }} catch (e) {{}}
  btn.addEventListener('click', function() {{
    var cur = root.getAttribute('data-theme');
    var isDark = cur ? cur === 'dark'
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
    var next = isDark ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try {{ localStorage.setItem('wp-theme', next); }} catch (e) {{}}
  }});

  // Column sort.
  var tbl = document.getElementById('tbl');
  var tbody = tbl.tBodies[0];
  var headers = tbl.tHead.rows[0].cells;
  var colOf = {{sym:0, mkt:1, price:2, d3:3, w1:4, m1:5, vol:6}};
  var state = {{key:'d3', dir:-1}};
  function val(tr, idx, type) {{
    var td = tr.cells[idx];
    if (type === 'n') {{
      var v = td.getAttribute('data-v');
      return v === '' || v === null ? -Infinity : parseFloat(v);
    }}
    return td.textContent.trim().toLowerCase();
  }}
  function sort(key, type, dir) {{
    var idx = colOf[key];
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function(a, b) {{
      var va = val(a, idx, type), vb = val(b, idx, type);
      if (va < vb) return -1 * dir;
      if (va > vb) return 1 * dir;
      return 0;
    }});
    rows.forEach(function(r) {{ tbody.appendChild(r); }});
    for (var i = 0; i < headers.length; i++) headers[i].classList.remove('sorted');
    for (var j = 0; j < headers.length; j++) {{
      if (headers[j].getAttribute('data-k') === key) headers[j].classList.add('sorted');
    }}
  }}
  for (var i = 0; i < headers.length; i++) {{
    (function(th) {{
      var key = th.getAttribute('data-k');
      if (!key) return;
      th.addEventListener('click', function() {{
        var type = th.getAttribute('data-t');
        state.dir = (state.key === key) ? -state.dir : (type === 'n' ? -1 : 1);
        state.key = key;
        sort(key, type, state.dir);
      }});
    }})(headers[i]);
  }}
}})();
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate the watchlist dashboard snapshot.")
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--context", default="context.json",
                    help="Optional JSON of curated news notes keyed by ticker.")
    ap.add_argument("--data-out", default="", help="Optional path to also dump raw metrics JSON.")
    args = ap.parse_args()

    context = {}
    try:
        with open(args.context) as f:
            context = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        context = {}

    rows = fetch_rows(TICKERS)
    generated = dt.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")
    html_out = render(rows, context, generated)

    with open(args.out, "w") as f:
        f.write(html_out)

    if args.data_out:
        with open(args.data_out, "w") as f:
            json.dump({"generated": generated, "rows": rows}, f, indent=2)

    ok = sum(1 for r in rows if r.get("ok"))
    print(f"Wrote {args.out} ({ok}/{len(rows)} tickers, {len(html_out):,} bytes)")


if __name__ == "__main__":
    main()
