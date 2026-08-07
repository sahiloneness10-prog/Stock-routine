"""
Static watchlist dashboard generator.
=====================================
Fetches live daily price/volume history from Yahoo Finance's public chart API
(stdlib only, browser User-Agent to avoid throttling), computes 3-day / 1-week /
1-month price moves and a volume shift, and renders a self-contained, theme-aware
``dashboard.html`` that can be opened anywhere or published as an artifact.

Unlike ``app.py`` (an interactive Streamlit app that needs a running server),
this produces a single static file — ideal for a scheduled/automated routine.

Usage:
    python generate_dashboard.py            # writes dashboard.html
"""
from __future__ import annotations

import datetime as dt
import html
import json
import time
import urllib.parse
import urllib.request

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

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(ticker: str, tries: int = 4) -> dict:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(ticker)}?range=3mo&interval=1d")
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
            if e.code == 429:
                time.sleep(1.5 * (i + 1))
                continue
            return {"_err": f"HTTP {e.code}"}
        except Exception as e:  # noqa: BLE001
            time.sleep(1.0)
            if i == tries - 1:
                return {"_err": str(e)[:80]}
    return {"_err": "rate-limited"}


def pct(closes: list, periods: int):
    c = [x for x in closes if x is not None]
    if len(c) <= periods or not c[-1 - periods]:
        return None
    return (c[-1] - c[-1 - periods]) / c[-1 - periods] * 100


def vol_change(vols: list):
    v = [x for x in vols if x is not None]
    if len(v) < 6:
        return None
    latest = v[-1]
    base = [x for x in (v[-21:-1] if len(v) > 21 else v[:-1]) if x]
    if not base:
        return None
    avg = sum(base) / len(base)
    return (latest - avg) / avg * 100 if avg else None


def collect() -> list[dict]:
    rows = []
    for t in TICKERS:
        d = fetch(t)
        if "_err" in d:
            rows.append({"ticker": t, "error": d["_err"]})
            time.sleep(0.15)
            continue
        try:
            res = d["chart"]["result"][0]
            meta = res.get("meta", {})
            q = res["indicators"]["quote"][0]
            pairs = [(c, v) for c, v in zip(q.get("close", []), q.get("volume", []))
                     if c is not None]
            closes = [c for c, _ in pairs]
            vols = [v for _, v in pairs]
            if not closes:
                rows.append({"ticker": t, "error": "no data"})
                continue
            rows.append({
                "ticker": t,
                "name": meta.get("shortName") or meta.get("longName") or "",
                "price": round(closes[-1], 4),
                "currency": meta.get("currency", ""),
                "d3": pct(closes, 3),
                "w1": pct(closes, 5),
                "m1": pct(closes, 21),
                "vol": vol_change(vols),
            })
        except Exception as e:  # noqa: BLE001
            rows.append({"ticker": t, "error": f"parse: {str(e)[:60]}"})
        time.sleep(0.15)
    return rows


# --------------------------------------------------------------------------- #
# Catalysts / news — curated context for the notable movers. Refresh alongside
# the price pull. `tag` drives the card colour; `dir` is "up"/"down"/"flat".
# --------------------------------------------------------------------------- #
CATALYSTS = [
    {"ticker": "AXTI", "tag": "Earnings", "dir": "up", "reg": False,
     "text": "Blowout Q2 (Jul 30): record revenue $47.6M (+164% YoY), EPS $0.19 vs "
             "$0.07 est; Q3 guide well above consensus and a Lumentum capacity deal "
             "through 2031. AI / data-center indium-phosphide demand."},
    {"ticker": "SATL", "tag": "Earnings", "dir": "up", "reg": False,
     "text": "Q2 (~Aug 5): revenue +259% to $15.9M, first-ever positive operating "
             "income and adjusted EBITDA ($2.8M); 'Merlin' constellation launch "
             "slated for Oct 2026."},
    {"ticker": "AAOI", "tag": "Regulatory", "dir": "up", "reg": True,
     "text": "Run into the Aug 6 Q2 report on a proposed U.S. ban on Chinese optical "
             "transceivers plus AI-datacenter demand for 800G / 1.6T parts. Policy "
             "tailwind for a domestic supplier."},
    {"ticker": "COHR", "tag": "Analyst", "dir": "up", "reg": True,
     "text": "AI-optics demand; JPMorgan raised its target to $435 (Overweight) ahead "
             "of Aug 12 earnings. Also a beneficiary of potential U.S. curbs on Chinese "
             "transceivers."},
    {"ticker": "TE", "tag": "Deal", "dir": "up", "reg": False,
     "text": "Aug 3: agreement to supply Clearway Energy 641MW of domestic solar "
             "modules; bounce off oversold levels. Still down over 1 month on an earlier "
             "weak Q2 loss."},
    {"ticker": "ZETA", "tag": "Earnings", "dir": "up", "reg": False,
     "text": "Q2 (Aug 4): 20th straight beat-and-raise — revenue +44% to $443M, FY guide "
             "lifted, strong Athena AI adoption."},
    {"ticker": "AMPX", "tag": "Earnings", "dir": "up", "reg": False,
     "text": "Q2: revenue +126% to $34M (beat) and FY26 guidance raised to ≥$140M on "
             "defense / drone demand."},
    {"ticker": "NVDA", "tag": "Regulatory", "dir": "up", "reg": True,
     "text": "~12% five-session rally on reports China will allow limited H200 chip "
             "purchases (Alibaba / ByteDance / DeepSeek) plus broad chip-sector strength "
             "ahead of Aug 26 earnings."},
    {"ticker": "HAIN", "tag": "Sector", "dir": "up", "reg": False,
     "text": "Sector read-through: peer Utz Brands agreed to be acquired by Intersnack, "
             "lifting packaged-food valuations. Not company-specific."},
    {"ticker": "MELI", "tag": "Earnings", "dir": "flat", "reg": False,
     "text": "Q2 (Aug 5): revenue +50% to $10.2B (beat) and EPS beat, but shares slipped "
             "on margin compression (operating margin 6.7%, −550bps) from shipping / "
             "credit spend. Volume +216%."},
    {"ticker": "DUOL", "tag": "Earnings", "dir": "down", "reg": False,
     "text": "Q2 (Aug 5): revenue +18.3% to $298.5M and an EPS beat, but fell ~10-12% on "
             "light Q3 guidance ($302M vs $304M est) and monetization concerns. Volume "
             "+262%."},
    {"ticker": "FLNC", "tag": "Earnings", "dir": "down", "reg": False,
     "text": "Q3 (Aug 5/6): cut FY26 guidance ($2.9–3.1B vs $3.2–3.6B), ~$400M of "
             "deliveries pushed to FY27, gross margin fell to 5.1% and now guiding to an "
             "EBITDA loss. Volume +268%."},
    {"ticker": "ADTN", "tag": "Earnings", "dir": "down", "reg": False,
     "text": "Cut preliminary Q2 guidance (revenue $280–282M vs $283–303M) on a "
             "delayed customer project, then an official miss ($0.04 EPS vs $0.13 est). "
             "Down 42% over the month."},
    {"ticker": "BYND", "tag": "Earnings", "dir": "down", "reg": False,
     "text": "Q2: revenue beat but adjusted EPS miss (−$0.09); U.S. retail −9.9%, "
             "foodservice −27.6%, EBITDA loss $27.7M. Early pop faded to a selloff; "
             "heavy volume (+170%) reads as turnaround speculation."},
    {"ticker": "LNZA", "tag": "Momentum", "dir": "up", "reg": False,
     "text": "No dated catalyst — Q2 due Aug 14. Volume +96% suggests momentum / "
             "speculation ahead of the print."},
]

TAG_COLORS = {
    "Earnings": "var(--tag-earn)",
    "Regulatory": "var(--amber)",
    "Analyst": "var(--tag-analyst)",
    "Deal": "var(--tag-deal)",
    "Sector": "var(--tag-sector)",
    "Momentum": "var(--tag-mom)",
}


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def build_html(rows: list[dict], generated: str) -> str:
    ok = [r for r in rows if "price" in r]
    failed = [r for r in rows if "error" in r]

    def num(r, k):
        return r.get(k) if r.get(k) is not None else None

    w1_vals = [r["w1"] for r in ok if r.get("w1") is not None]
    gainers = sum(1 for v in w1_vals if v > 0)
    losers = sum(1 for v in w1_vals if v < 0)
    best = max((r for r in ok if r.get("w1") is not None), key=lambda r: r["w1"], default=None)
    worst = min((r for r in ok if r.get("w1") is not None), key=lambda r: r["w1"], default=None)

    payload = json.dumps(ok)
    catalysts_json = json.dumps(CATALYSTS)
    failed_str = ", ".join(r["ticker"] for r in failed) or "none"

    def kpi(label, value):
        return (f'<div class="kpi"><div class="kpi-l">{label}</div>'
                f'<div class="kpi-v">{value}</div></div>')

    best_html = (f'<span class="mono up">{esc(best["ticker"])} {best["w1"]:+.1f}%</span>'
                 if best else "—")
    worst_html = (f'<span class="mono down">{esc(worst["ticker"])} {worst["w1"]:+.1f}%</span>'
                  if worst else "—")

    kpis = "".join([
        kpi("Tickers loaded", f'{len(ok)}<span class="dim">/{len(rows)}</span>'),
        kpi("Gainers · 1W", f'<span class="up">{gainers}</span>'),
        kpi("Losers · 1W", f'<span class="down">{losers}</span>'),
        kpi("Top mover · 1W", best_html),
        kpi("Worst mover · 1W", worst_html),
    ])

    return (TEMPLATE
            .replace("__GENERATED__", esc(generated))
            .replace("__KPIS__", kpis)
            .replace("__N_OK__", str(len(ok)))
            .replace("__FAILED__", esc(failed_str))
            .replace("__PAYLOAD__", payload)
            .replace("__CATALYSTS__", catalysts_json))


TEMPLATE = r"""<style>
  :root{
    --bg:#f6f7f9; --surface:#ffffff; --surface-2:#eef0f4; --line:#dfe3ea;
    --ink:#141922; --ink-2:#454e5c; --ink-3:#8a93a3;
    --pos:#1f9d63; --neg:#d4353b; --pos-ink:#0a3d24; --neg-ink:#5a1114;
    --amber:#b57e12; --amber-bg:rgba(224,165,43,.12);
    --tag-earn:#2f6fed; --tag-analyst:#8a5cf6; --tag-deal:#0e9aa7;
    --tag-sector:#c25e00; --tag-mom:#6b7280;
    --shadow:0 1px 2px rgba(20,25,34,.05),0 6px 20px rgba(20,25,34,.06);
    --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
    --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  @media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
    --bg:#0f1419; --surface:#171d26; --surface-2:#1e2530; --line:#28313d;
    --ink:#eef2f7; --ink-2:#a9b3c1; --ink-3:#6b7686;
    --pos:#3ecf8e; --neg:#f0616b; --pos-ink:#c9f5e0; --neg-ink:#ffd9dc;
    --amber:#e0a52b; --amber-bg:rgba(224,165,43,.11);
    --tag-earn:#6ea0ff; --tag-analyst:#b79bff; --tag-deal:#3fc7d4;
    --tag-sector:#f0954a; --tag-mom:#9aa5b4;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 26px rgba(0,0,0,.35);
  }}
  :root[data-theme="dark"]{
    --bg:#0f1419; --surface:#171d26; --surface-2:#1e2530; --line:#28313d;
    --ink:#eef2f7; --ink-2:#a9b3c1; --ink-3:#6b7686;
    --pos:#3ecf8e; --neg:#f0616b; --pos-ink:#c9f5e0; --neg-ink:#ffd9dc;
    --amber:#e0a52b; --amber-bg:rgba(224,165,43,.11);
    --tag-earn:#6ea0ff; --tag-analyst:#b79bff; --tag-deal:#3fc7d4;
    --tag-sector:#f0954a; --tag-mom:#9aa5b4;
    --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 26px rgba(0,0,0,.35);
  }
  *{box-sizing:border-box}
  body{background:var(--bg);color:var(--ink);font-family:var(--sans);
    line-height:1.5;-webkit-font-smoothing:antialiased;margin:0}
  .wrap{max-width:1080px;margin:0 auto;padding:clamp(18px,3vw,40px)}
  .mono{font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.01em}
  .up{color:var(--pos)} .down{color:var(--neg)} .flat{color:var(--ink-3)}
  .dim{color:var(--ink-3)}

  .head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;
    margin-bottom:22px}
  h1{font-size:clamp(1.5rem,3.2vw,2.1rem);font-weight:700;margin:0;letter-spacing:-.02em;
    text-wrap:balance}
  .sub{margin:4px 0 0;color:var(--ink-2);font-size:.9rem}
  .theme-btn{background:var(--surface);border:1px solid var(--line);color:var(--ink-2);
    width:38px;height:38px;border-radius:10px;font-size:1.05rem;cursor:pointer;
    flex:none;transition:.15s}
  .theme-btn:hover{color:var(--ink);border-color:var(--ink-3)}
  .theme-btn:focus-visible{outline:2px solid var(--tag-earn);outline-offset:2px}

  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;
    margin-bottom:26px}
  .kpi{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:14px 16px;box-shadow:var(--shadow)}
  .kpi-l{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);
    font-weight:600}
  .kpi-v{font-size:1.5rem;font-weight:700;margin-top:5px;font-family:var(--mono);
    font-variant-numeric:tabular-nums}

  .panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;
    box-shadow:var(--shadow);margin-bottom:26px;overflow:hidden}
  .panel-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
    flex-wrap:wrap;padding:16px 18px;border-bottom:1px solid var(--line)}
  .panel-head h2{font-size:1.02rem;margin:0;font-weight:650;letter-spacing:-.01em}
  .hint{font-size:.75rem;color:var(--ink-3)}
  .controls{display:flex;align-items:center;gap:12px}
  #filter{background:var(--surface-2);border:1px solid var(--line);color:var(--ink);
    border-radius:8px;padding:6px 10px;font-size:.82rem;font-family:var(--mono);width:130px}
  #filter:focus-visible{outline:2px solid var(--tag-earn);outline-offset:1px}

  .table-scroll{overflow-x:auto}
  table{width:100%;border-collapse:collapse;font-size:.86rem}
  thead th{position:sticky;top:0;background:var(--surface-2);color:var(--ink-2);
    font-weight:600;text-align:left;padding:9px 14px;font-size:.72rem;
    text-transform:uppercase;letter-spacing:.05em;white-space:nowrap;
    border-bottom:1px solid var(--line)}
  th.r{text-align:right} td.r{text-align:right}
  th.sortable,th.txt{cursor:pointer;user-select:none}
  th.sortable:hover,th.txt:hover{color:var(--ink)}
  th.sorted-asc::after{content:" ▲";font-size:.65em;color:var(--tag-earn)}
  th.sorted-desc::after{content:" ▼";font-size:.65em;color:var(--tag-earn)}
  tbody td{padding:7px 14px;border-bottom:1px solid var(--line);white-space:nowrap}
  tbody tr:last-child td{border-bottom:none}
  tbody tr:hover td{background:color-mix(in srgb,var(--surface-2) 55%,transparent)}
  td.tk{font-weight:600}
  td.name{color:var(--ink-2);max-width:230px;overflow:hidden;text-overflow:ellipsis;
    white-space:nowrap;font-size:.82rem}
  .cur{color:var(--ink-3);font-size:.68rem;margin-left:4px}
  .failed{margin:0;padding:10px 18px;font-size:.74rem;color:var(--ink-3);
    background:var(--surface-2)}
  .failed .mono{color:var(--ink-2)}

  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;
    padding:18px}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
    padding:14px 15px;position:relative}
  .card.reg{border-color:color-mix(in srgb,var(--amber) 55%,var(--line));
    background:linear-gradient(0deg,var(--amber-bg),transparent)}
  .card-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .card .tk{font-weight:700;font-size:.95rem}
  .tag{font-size:.66rem;font-weight:650;text-transform:uppercase;letter-spacing:.04em;
    padding:2px 8px;border-radius:99px;color:#fff}
  .tag[data-tag="Earnings"]{background:var(--tag-earn)}
  .tag[data-tag="Regulatory"]{background:var(--amber)}
  .tag[data-tag="Analyst"]{background:var(--tag-analyst)}
  .tag[data-tag="Deal"]{background:var(--tag-deal)}
  .tag[data-tag="Sector"]{background:var(--tag-sector)}
  .tag[data-tag="Momentum"]{background:var(--tag-mom)}
  .reg-tag{background:transparent;color:var(--amber);
    border:1px solid color-mix(in srgb,var(--amber) 60%,transparent)}
  .card-move{margin-left:auto;font-weight:700;font-size:.9rem}
  .card-move em{font-style:normal;color:var(--ink-3);font-size:.65rem;font-weight:600}
  .card-name{margin:8px 0 6px;color:var(--ink-2);font-size:.78rem;font-weight:600}
  .card-text{margin:0;color:var(--ink-2);font-size:.83rem;line-height:1.5}

  .foot{color:var(--ink-3);font-size:.74rem;line-height:1.6;text-align:center;
    max-width:680px;margin:0 auto;padding:4px 0 8px}
  @media (max-width:560px){
    .head{flex-direction:row} .card-move{margin-left:0}
    td.name{max-width:120px}
  }
</style>

<div class="wrap">
<header class="head">
  <div>
    <h1>Watchlist Pulse</h1>
    <p class="sub">Momentum &amp; catalysts across __N_OK__ tickers · generated __GENERATED__</p>
  </div>
  <button id="theme" class="theme-btn" aria-label="Toggle theme" title="Toggle theme">◐</button>
</header>

<section class="kpis">__KPIS__</section>

<section class="panel">
  <div class="panel-head">
    <h2>Movement</h2>
    <div class="controls">
      <input id="filter" type="text" placeholder="Filter ticker…" aria-label="Filter ticker" />
      <span class="hint">click a column to sort</span>
    </div>
  </div>
  <div class="table-scroll">
    <table id="tbl">
      <thead>
        <tr>
          <th data-k="ticker" class="txt">Ticker</th>
          <th data-k="name" class="txt">Name</th>
          <th data-k="price" class="r">Price</th>
          <th data-k="d3" class="r sortable">3-Day</th>
          <th data-k="w1" class="r sortable sorted-desc">1-Week</th>
          <th data-k="m1" class="r sortable">1-Month</th>
          <th data-k="vol" class="r sortable">Vol &Delta;</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
  <p class="failed">No data resolved for: <span class="mono">__FAILED__</span></p>
</section>

<section class="panel">
  <div class="panel-head"><h2>What moved them</h2>
    <span class="hint">curated catalysts for the notable movers</span></div>
  <div id="cards" class="cards"></div>
</section>

<footer class="foot">
  Informational only — not investment advice. Prices from Yahoo Finance public
  data and may be delayed; % windows use trading-day look-backs (3 / 5 / 21 sessions).
  Volume &Delta; compares the latest session to its trailing 20-day average.
</footer>
</div>

<script>
const DATA = __PAYLOAD__;
const CATALYSTS = __CATALYSTS__;

const fmtPct = v => v == null ? "—" : (v >= 0 ? "+" : "") + v.toFixed(1) + "%";
const fmtPrice = v => v == null ? "—" :
  v.toLocaleString(undefined, {maximumFractionDigits: v < 10 ? 3 : 2});

// diverging magnitude -> background tint, clamped near 15%.
function tint(v){
  if (v == null) return "";
  const a = Math.min(Math.abs(v) / 15, 1);
  const alpha = (0.10 + 0.42 * a).toFixed(3);
  return v >= 0
    ? "background:rgba(34,160,107," + alpha + ");color:var(--pos-ink)"
    : "background:rgba(229,72,77," + alpha + ");color:var(--neg-ink)";
}

let sortKey = "w1", sortDir = -1, filterStr = "";

function render(){
  const tb = document.getElementById("tbody");
  const rows = DATA
    .filter(r => r.ticker.toLowerCase().includes(filterStr) ||
                 (r.name || "").toLowerCase().includes(filterStr))
    .slice()
    .sort((a, b) => {
      let x = a[sortKey], y = b[sortKey];
      if (typeof x === "string") return sortDir * x.localeCompare(y);
      if (x == null) return 1; if (y == null) return -1;
      return sortDir * (x - y);
    });
  tb.innerHTML = rows.map(r =>
    '<tr>' +
      '<td class="mono tk">' + r.ticker + '</td>' +
      '<td class="name" title="' + (r.name||'').replace(/"/g,'&quot;') + '">' + (r.name||'') + '</td>' +
      '<td class="mono r">' + fmtPrice(r.price) + '<span class="cur">' + (r.currency||'') + '</span></td>' +
      '<td class="mono r" style="' + tint(r.d3) + '">' + fmtPct(r.d3) + '</td>' +
      '<td class="mono r" style="' + tint(r.w1) + '">' + fmtPct(r.w1) + '</td>' +
      '<td class="mono r" style="' + tint(r.m1) + '">' + fmtPct(r.m1) + '</td>' +
      '<td class="mono r" style="' + tint(r.vol) + '">' + fmtPct(r.vol) + '</td>' +
    '</tr>').join("");
}

document.querySelectorAll("th.sortable, th.txt").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.dataset.k;
    if (!k) return;
    if (sortKey === k) sortDir *= -1;
    else { sortKey = k; sortDir = (k === "ticker" || k === "name") ? 1 : -1; }
    document.querySelectorAll("th").forEach(h =>
      h.classList.remove("sorted-asc", "sorted-desc"));
    th.classList.add(sortDir === 1 ? "sorted-asc" : "sorted-desc");
    render();
  });
});

document.getElementById("filter").addEventListener("input", e => {
  filterStr = e.target.value.trim().toLowerCase();
  render();
});

// catalyst cards, ordered by |1W move|
const byTicker = Object.fromEntries(DATA.map(r => [r.ticker, r]));
const cardsHtml = CATALYSTS
  .map(c => Object.assign({}, c, { r: byTicker[c.ticker] }))
  .sort((a, b) => Math.abs((b.r && b.r.w1) || 0) - Math.abs((a.r && a.r.w1) || 0))
  .map(c => {
    const w1 = c.r && c.r.w1;
    const arrow = c.dir === "up" ? "▲" : c.dir === "down" ? "▼" : "◆";
    const cls = c.dir === "up" ? "up" : c.dir === "down" ? "down" : "flat";
    return '' +
      '<article class="card ' + (c.reg ? 'reg' : '') + '">' +
        '<div class="card-top">' +
          '<span class="mono tk">' + c.ticker + '</span>' +
          '<span class="tag" data-tag="' + c.tag + '">' + c.tag + '</span>' +
          (c.reg ? '<span class="tag reg-tag">⚑ Regulatory</span>' : '') +
          '<span class="card-move mono ' + cls + '">' + arrow + ' ' + fmtPct(w1) + ' <em>1W</em></span>' +
        '</div>' +
        '<p class="card-name">' + ((c.r && c.r.name) || '') + '</p>' +
        '<p class="card-text">' + c.text + '</p>' +
      '</article>';
  }).join("");
document.getElementById("cards").innerHTML = cardsHtml;

// theme toggle
const root = document.documentElement;
document.getElementById("theme").addEventListener("click", () => {
  const cur = root.getAttribute("data-theme");
  const next = cur === "dark" ? "light" : cur === "light" ? "dark"
    : (matchMedia("(prefers-color-scheme: dark)").matches ? "light" : "dark");
  root.setAttribute("data-theme", next);
});

render();
</script>
"""


def main():
    print("Fetching…")
    rows = collect()
    ok = len([r for r in rows if "price" in r])
    print(f"Resolved {ok}/{len(rows)} tickers.")
    generated = dt.datetime.now(dt.timezone.utc).strftime("%b %d, %Y · %H:%M UTC")
    out = build_html(rows, generated)
    with open("dashboard.html", "w") as f:
        f.write(out)
    with open("data.json", "w") as f:
        json.dump(rows, f, indent=2)
    print("Wrote dashboard.html")


if __name__ == "__main__":
    main()
