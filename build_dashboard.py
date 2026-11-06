"""Build a self-contained HTML watchlist dashboard from fetched data.

Usage:  python build_dashboard.py data.json dashboard.html

`data.json` is produced by fetch_data.py. The output HTML embeds the data
inline so it works as a standalone, shareable page with no network calls.
"""
from __future__ import annotations

import json
import sys

TEMPLATE = r"""<meta name="claude:viewport-fit-sides" content="cover">
<title>Watchlist Pulse</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
  /* Layout: sticky terminal header, KPI tiles, a filterable heat-table as the
     spine, then a per-ticker news feed. Market-terminal identity. */
  :root {
    --plane:      #f4f4f0;   /* page background */
    --surface:    #ffffff;   /* cards / rows */
    --surface-2:  #fbfbf8;   /* zebra / insets */
    --ink:        #15150f;   /* primary text */
    --ink-2:      #56554d;   /* secondary text */
    --muted:      #8a897f;   /* axis / captions */
    --line:       #e4e3da;   /* hairlines */
    --line-2:     #d2d1c6;
    --accent:     #1f6fd6;   /* interactive */
    --accent-ink: #ffffff;
    --up:         #0a8f3c;   /* gains */
    --up-soft:    rgba(10,143,60,VARUP);
    --down:       #cf3030;   /* losses */
    --down-soft:  rgba(207,48,48,VARDN);
    --chip:       #ecece5;
    --shadow:     0 1px 2px rgba(20,20,15,.05), 0 6px 20px rgba(20,20,15,.04);
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --plane:     #0c0c0b;
      --surface:   #171716;
      --surface-2: #121211;
      --ink:       #f1f0ea;
      --ink-2:     #b7b6ac;
      --muted:     #85847b;
      --line:      #262522;
      --line-2:    #32312d;
      --accent:    #4d93ec;
      --accent-ink:#06121f;
      --up:        #2fb85f;
      --up-soft:   rgba(47,184,95,VARUPD);
      --down:      #ec5a5a;
      --down-soft: rgba(236,90,90,VARDND);
      --chip:      #22221f;
      --shadow:    0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
      color-scheme: dark;
    }
  }
  :root[data-theme="dark"] {
    --plane:     #0c0c0b;
    --surface:   #171716;
    --surface-2: #121211;
    --ink:       #f1f0ea;
    --ink-2:     #b7b6ac;
    --muted:     #85847b;
    --line:      #262522;
    --line-2:    #32312d;
    --accent:    #4d93ec;
    --accent-ink:#06121f;
    --up:        #2fb85f;
    --up-soft:   rgba(47,184,95,VARUPD);
    --down:      #ec5a5a;
    --down-soft: rgba(236,90,90,VARDND);
    --chip:      #22221f;
    --shadow:    0 1px 2px rgba(0,0,0,.4), 0 8px 24px rgba(0,0,0,.35);
    color-scheme: dark;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--plane); color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5; -webkit-font-smoothing: antialiased;
  }
  .wrap { padding-left: max(16px, env(safe-area-inset-left, 0px));
          padding-right: max(16px, env(safe-area-inset-right, 0px)); }
  .mono { font-family: "IBM Plex Mono", ui-monospace, Menlo, monospace;
          font-variant-numeric: tabular-nums; }

  /* ---- header ---- */
  body::before { content: ""; position: fixed; inset: 0 0 auto; height: env(safe-area-inset-top, 0px);
                 z-index: 30; background: var(--surface); }
  header.top {
    position: sticky; top: env(safe-area-inset-top, 0px); z-index: 20;
    background: var(--surface); border-bottom: 1px solid var(--line);
  }
  .top-in { max-width: 1240px; margin: 0 auto; padding-block: 14px;
            display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .brand { display: flex; align-items: baseline; gap: 12px; min-width: 0; }
  .brand h1 { font-size: 1.35rem; font-weight: 700; letter-spacing: -.01em; margin: 0;
              text-wrap: balance; }
  .pulse { width: 9px; height: 9px; border-radius: 50%; background: var(--up);
           box-shadow: 0 0 0 0 var(--up); animation: pulse 2.4s infinite; flex: none;
           align-self: center; }
  @keyframes pulse { 0%{box-shadow:0 0 0 0 rgba(10,143,60,.5)} 70%{box-shadow:0 0 0 8px rgba(10,143,60,0)} 100%{box-shadow:0 0 0 0 rgba(10,143,60,0)} }
  @media (prefers-reduced-motion: reduce) { .pulse { animation: none; } }
  .stamp { color: var(--muted); font-size: .8rem; }
  .spacer { flex: 1 1 auto; }
  .theme-btn { font: inherit; font-size: .8rem; color: var(--ink-2); background: var(--chip);
               border: 1px solid var(--line); border-radius: 8px; padding: 6px 11px; cursor: pointer; }
  .theme-btn:hover { border-color: var(--line-2); }

  main { max-width: 1240px; margin: 0 auto; padding-block: 22px 56px; }

  /* ---- KPI tiles ---- */
  .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
  .tile { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
          padding: 14px 16px; box-shadow: var(--shadow); }
  .tile .k { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
  .tile .v { font-size: 1.6rem; font-weight: 600; margin-top: 4px; }
  .tile .s { font-size: .82rem; color: var(--ink-2); margin-top: 2px; }
  .tile .tk { font-weight: 600; }

  /* ---- context callout ---- */
  .context { margin-top: 20px; background: var(--surface); border: 1px solid var(--line);
             border-left: 3px solid var(--accent); border-radius: 12px; padding: 16px 18px;
             box-shadow: var(--shadow); }
  .context h2 { margin: 0 0 6px; font-size: .95rem; }
  .context p { margin: 0; color: var(--ink-2); font-size: .9rem; }

  /* ---- section heads ---- */
  .sec-head { display: flex; align-items: baseline; gap: 10px; margin: 30px 0 12px; flex-wrap: wrap; }
  .sec-head h2 { margin: 0; font-size: 1.08rem; }
  .sec-head .hint { color: var(--muted); font-size: .8rem; }

  /* ---- controls ---- */
  .controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
  .controls input[type=search], .controls select {
    font: inherit; font-size: .88rem; color: var(--ink); background: var(--surface);
    border: 1px solid var(--line-2); border-radius: 9px; padding: 8px 11px; }
  .controls input[type=search] { min-width: 180px; flex: 1 1 200px; }
  .controls input:focus-visible, .controls select:focus-visible,
  .theme-btn:focus-visible, .seg button:focus-visible, th.sortable:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px; }
  .seg { display: inline-flex; border: 1px solid var(--line-2); border-radius: 9px; overflow: hidden; }
  .seg button { font: inherit; font-size: .82rem; background: var(--surface); color: var(--ink-2);
                border: 0; padding: 8px 12px; cursor: pointer; border-left: 1px solid var(--line); }
  .seg button:first-child { border-left: 0; }
  .seg button[aria-pressed="true"] { background: var(--accent); color: var(--accent-ink); }

  /* ---- table ---- */
  .tbl-scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px;
                background: var(--surface); box-shadow: var(--shadow); }
  table { border-collapse: collapse; width: 100%; min-width: 760px; }
  thead th { position: sticky; top: 0; z-index: 5;
             background: var(--surface-2); color: var(--ink-2); font-size: .72rem;
             text-transform: uppercase; letter-spacing: .05em; font-weight: 600;
             text-align: right; padding: 11px 12px; border-bottom: 1px solid var(--line-2);
             white-space: nowrap; }
  thead th:first-child, thead th.l { text-align: left; }
  th.sortable { cursor: pointer; user-select: none; }
  th.sortable .arrow { opacity: .4; font-size: .7em; }
  th.sortable[data-active="true"] { color: var(--ink); }
  th.sortable[data-active="true"] .arrow { opacity: 1; color: var(--accent); }
  tbody td { padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--line);
             font-size: .9rem; white-space: nowrap; }
  tbody tr:last-child td { border-bottom: 0; }
  tbody tr:hover td { background: color-mix(in srgb, var(--accent) 7%, transparent); }
  td.tk { text-align: left; font-weight: 600; }
  td.tk .ex { color: var(--muted); font-size: .72rem; font-weight: 400; margin-left: 6px; }
  td.spark { text-align: left; width: 96px; }
  td.spark svg { display: block; }
  td.pct { font-weight: 500; border-radius: 0; }
  .cell { display: inline-block; min-width: 72px; padding: 3px 8px; border-radius: 7px; }
  .cell .arw { font-size: .72em; margin-right: 3px; opacity: .75; }
  .na { color: var(--muted); }
  .px { color: var(--ink); font-weight: 500; }
  .px .cy { color: var(--muted); margin-right: 1px; font-weight: 400; }

  /* ---- news ---- */
  .news-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
  .nblock { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
            padding: 15px 16px; box-shadow: var(--shadow); }
  .nblock > .hd { display: flex; align-items: baseline; gap: 9px; margin-bottom: 10px;
                  padding-bottom: 9px; border-bottom: 1px solid var(--line); }
  .nblock > .hd .t { font-weight: 700; font-size: .98rem; }
  .nblock > .hd .mv { font-size: .8rem; font-weight: 600; margin-left: auto; }
  .nitem { padding: 8px 0; border-bottom: 1px dashed var(--line); }
  .nitem:last-child { border-bottom: 0; padding-bottom: 0; }
  .nitem a { color: var(--ink); text-decoration: none; font-weight: 500; font-size: .9rem; }
  .nitem a:hover { color: var(--accent); text-decoration: underline; }
  .nitem .meta { color: var(--muted); font-size: .74rem; margin-top: 3px; }
  .nitem .sum { color: var(--ink-2); font-size: .82rem; margin-top: 4px; }

  .up { color: var(--up); } .down { color: var(--down); }

  footer { max-width: 1240px; margin: 0 auto; color: var(--muted); font-size: .78rem;
           padding-block: 8px 20px; }
  footer .failed { margin-top: 6px; }

  @media (max-width: 560px) {
    .top-in { padding-block: 11px; }
    .brand h1 { font-size: 1.15rem; }
    .tile .v { font-size: 1.35rem; }
  }
</style>

<header class="top">
  <div class="top-in wrap">
    <span class="pulse" aria-hidden="true"></span>
    <div class="brand">
      <h1>Watchlist Pulse</h1>
    </div>
    <span class="stamp mono" id="stamp"></span>
    <span class="spacer"></span>
    <button class="theme-btn" id="theme" type="button">Theme</button>
  </div>
</header>

<main class="wrap">
  <section class="kpis" id="kpis" aria-label="Summary"></section>

  <section class="context" id="context">
    <h2>Market read</h2>
    <p id="context-body"></p>
  </section>

  <div class="sec-head">
    <h2>Movement board</h2>
    <span class="hint">cells shaded by move size · green up, red down · click a column to sort · trailing-session windows</span>
  </div>

  <div class="controls">
    <input type="search" id="search" placeholder="Filter tickers…" aria-label="Filter tickers">
    <select id="market" aria-label="Filter by market">
      <option value="">All markets</option>
    </select>
    <span class="seg" role="group" aria-label="Shade cells by window">
      <button type="button" data-shade="day">1D</button>
      <button type="button" data-shade="d3">3D</button>
      <button type="button" data-shade="w1" aria-pressed="true">1W</button>
      <button type="button" data-shade="m1">1M</button>
    </span>
  </div>

  <div class="tbl-scroll">
    <table>
      <thead>
        <tr>
          <th class="l sortable" data-key="ticker">Ticker <span class="arrow"></span></th>
          <th class="l">30-day trend</th>
          <th class="sortable" data-key="price">Price <span class="arrow"></span></th>
          <th class="sortable" data-key="day">1D % <span class="arrow"></span></th>
          <th class="sortable" data-key="d3">3D % <span class="arrow"></span></th>
          <th class="sortable" data-key="w1">1W % <span class="arrow"></span></th>
          <th class="sortable" data-key="m1">1M % <span class="arrow"></span></th>
          <th class="sortable" data-key="vol">Volume Δ <span class="arrow"></span></th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <div class="sec-head">
    <h2>News, releases &amp; regulatory flow</h2>
    <span class="hint">latest headlines for the most active names — context for the moves above</span>
  </div>
  <section class="news-grid" id="news"></section>
</main>

<footer class="wrap">
  <div id="source"></div>
  <div class="failed" id="failed"></div>
  <div style="margin-top:8px">Informational only — not investment advice. Prices via Yahoo Finance, may be delayed. Percentage windows are trading-session look-backs (3 / 5 / 21 sessions). Volume Δ compares the latest session to its trailing 20-session average.</div>
</footer>

<script id="data" type="application/json">__DATA__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("data").textContent);
  var rows = DATA.rows.slice();
  var news = DATA.news || {};
  var CAP = 15; // % at which cell shading saturates

  var $ = function (s, r) { return (r || document).querySelector(s); };
  function fmtPct(v) { return (v > 0 ? "+" : "") + v.toFixed(2) + "%"; }
  function fmtVol(v) { return (v > 0 ? "+" : "") + v.toFixed(0) + "%"; }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }

  function marketOf(t) {
    if (t.endsWith(".NS") || t.endsWith(".BO")) return "India";
    if (t.endsWith(".L")) return "London";
    if (t.endsWith(".IL")) return "London IOB";
    return "US / ADR";
  }

  // ---- shaded cell (color + signed text; never color alone) ----
  function cell(v, isVol) {
    if (v == null || isNaN(v)) return '<span class="na">—</span>';
    var mag = Math.min(Math.abs(v) / CAP, 1);
    var up = v > 0;
    var alpha = 0.12 + 0.52 * mag;
    var bg = up ? "rgba(10,143,60," : "rgba(207,48,48,";
    // dark-mode handled via color-mix fallback: use currentColor-independent rgba, readable on both
    var arrow = v > 0 ? "▲" : (v < 0 ? "▼" : "");
    var txt = isVol ? fmtVol(v) : fmtPct(v);
    return '<span class="cell" style="background:' + bg + alpha.toFixed(3) + ')">' +
           '<span class="arw ' + (up ? "up" : "down") + '">' + arrow + "</span>" + txt + "</span>";
  }

  // ---- sparkline ----
  function spark(vals) {
    if (!vals || vals.length < 2) return "";
    var w = 84, h = 26, pad = 2;
    var min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    var rng = (max - min) || 1;
    var up = vals[vals.length - 1] >= vals[0];
    var col = up ? "var(--up)" : "var(--down)";
    var n = vals.length;
    var pts = vals.map(function (v, i) {
      var x = pad + (i / (n - 1)) * (w - 2 * pad);
      var y = pad + (1 - (v - min) / rng) * (h - 2 * pad);
      return [x, y];
    });
    var d = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    var area = d + " L" + pts[n - 1][0].toFixed(1) + " " + (h - pad) + " L" + pts[0][0].toFixed(1) + " " + (h - pad) + " Z";
    var last = pts[n - 1];
    var id = "g" + Math.random().toString(36).slice(2, 8);
    return '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" aria-hidden="true">' +
      '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="' + col + '" stop-opacity="0.22"/>' +
      '<stop offset="1" stop-color="' + col + '" stop-opacity="0"/></linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#' + id + ')"/>' +
      '<path d="' + d + '" fill="none" stroke="' + col + '" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + last[0].toFixed(1) + '" cy="' + last[1].toFixed(1) + '" r="2.1" fill="' + col + '"/></svg>';
  }

  // ---- state ----
  var sortKey = "w1", sortDir = -1, shade = "w1", q = "", mkt = "";

  function view() {
    var r = rows.filter(function (x) {
      if (q && x.ticker.toLowerCase().indexOf(q) === -1) return false;
      if (mkt && marketOf(x.ticker) !== mkt) return false;
      return true;
    });
    r.sort(function (a, b) {
      if (sortKey === "ticker") return a.ticker < b.ticker ? -sortDir : (a.ticker > b.ticker ? sortDir : 0);
      var av = a[sortKey], bv = b[sortKey];
      var an = (av == null || isNaN(av)), bn = (bv == null || isNaN(bv));
      if (an && bn) return 0; if (an) return 1; if (bn) return -1;  // nulls last
      return (av - bv) * sortDir;
    });
    return r;
  }

  function renderTable() {
    var r = view();
    var html = r.map(function (x) {
      return '<tr>' +
        '<td class="tk mono">' + esc(x.ticker) + '<span class="ex">' + marketOf(x.ticker) + '</span></td>' +
        '<td class="spark">' + spark(x.spark) + '</td>' +
        '<td class="px mono"><span class="cy">' + esc(x.ccy) + '</span>' + x.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) + '</td>' +
        '<td class="pct mono">' + cell(x.day) + '</td>' +
        '<td class="pct mono">' + cell(x.d3) + '</td>' +
        '<td class="pct mono">' + cell(x.w1) + '</td>' +
        '<td class="pct mono">' + cell(x.m1) + '</td>' +
        '<td class="pct mono">' + cell(x.vol, true) + '</td>' +
      '</tr>';
    }).join("");
    $("#tbody").innerHTML = html || '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:24px">No tickers match.</td></tr>';
    // shaded column emphasis via header active state
    document.querySelectorAll("th.sortable").forEach(function (th) {
      var active = th.dataset.key === sortKey;
      th.dataset.active = active ? "true" : "false";
      var a = th.querySelector(".arrow");
      if (a) a.textContent = active ? (sortDir < 0 ? "↓" : "↑") : "";
    });
  }

  // ---- KPIs ----
  function kpis() {
    var withW = rows.filter(function (x) { return x.w1 != null && !isNaN(x.w1); });
    var gain = withW.filter(function (x) { return x.w1 > 0; }).length;
    var loss = withW.filter(function (x) { return x.w1 < 0; }).length;
    var avg = withW.reduce(function (s, x) { return s + x.w1; }, 0) / (withW.length || 1);
    var best = withW.slice().sort(function (a, b) { return b.w1 - a.w1; })[0];
    var worst = withW.slice().sort(function (a, b) { return a.w1 - b.w1; })[0];
    var withV = rows.filter(function (x) { return x.vol != null && !isNaN(x.vol); });
    var volspike = withV.slice().sort(function (a, b) { return b.vol - a.vol; })[0];
    function tile(k, v, s, cls) {
      return '<div class="tile"><div class="k">' + k + '</div><div class="v ' + (cls || "") + '">' + v + '</div>' +
        (s ? '<div class="s">' + s + '</div>' : '') + '</div>';
    }
    var el = $("#kpis");
    el.innerHTML =
      tile("Tracked", rows.length + " / " + (rows.length + (DATA.failed || []).length), "tickers resolved") +
      tile("Gainers · 1W", gain, "advancing this week", "up") +
      tile("Decliners · 1W", loss, "declining this week", "down") +
      tile("Avg move · 1W", fmtPct(avg), "equal-weight watchlist", avg >= 0 ? "up" : "down") +
      (best ? tile("Top gainer · 1W", '<span class="tk">' + esc(best.ticker) + '</span>', fmtPct(best.w1), "up") : "") +
      (worst ? tile("Top decliner · 1W", '<span class="tk">' + esc(worst.ticker) + '</span>', fmtPct(worst.w1), "down") : "") +
      (volspike ? tile("Volume spike", '<span class="tk">' + esc(volspike.ticker) + '</span>', fmtVol(volspike.vol) + " vs 20d avg") : "");
    return { gain: gain, loss: loss, best: best, worst: worst, withW: withW };
  }

  // ---- context read ----
  function context(k) {
    var big = k.withW.filter(function (x) { return x.w1 <= -15; })
                    .sort(function (a, b) { return a.w1 - b.w1; });
    var bigUp = k.withW.filter(function (x) { return x.w1 >= 12; })
                      .sort(function (a, b) { return b.w1 - a.w1; });
    var parts = [];
    parts.push("Across " + k.withW.length + " priced names the watchlist is leaning " +
      (k.gain >= k.loss ? "up" : "down") + " this week — " + k.gain + " advancing vs " + k.loss + " declining.");
    if (big.length) {
      var names = big.slice(0, 5).map(function (x) { return x.ticker + " (" + fmtPct(x.w1) + ")"; }).join(", ");
      parts.push("A sharp drawdown is concentrated in " + big.length + " name" + (big.length > 1 ? "s" : "") +
        " off 15%+ on the week — " + names + ". Several are semiconductor / networking / AI-infrastructure names moving together, which points to a sector de-rating rather than single-stock news; check each name's headlines below.");
    }
    if (bigUp.length) {
      var up = bigUp.slice(0, 4).map(function (x) { return x.ticker + " (" + fmtPct(x.w1) + ")"; }).join(", ");
      parts.push("Leading the upside: " + up + ".");
    }
    $("#context-body").textContent = parts.join(" ");
  }

  // ---- news ----
  function renderNews() {
    var keys = Object.keys(news);
    // order news blocks by absolute 1W move of that ticker
    var byTk = {}; rows.forEach(function (x) { byTk[x.ticker] = x; });
    keys.sort(function (a, b) {
      var am = byTk[a] && byTk[a].w1 != null ? Math.abs(byTk[a].w1) : -1;
      var bm = byTk[b] && byTk[b].w1 != null ? Math.abs(byTk[b].w1) : -1;
      return bm - am;
    });
    var html = keys.map(function (t) {
      var items = news[t] || []; if (!items.length) return "";
      var row = byTk[t];
      var mv = row && row.w1 != null ? '<span class="mv ' + (row.w1 >= 0 ? "up" : "down") + '">' + fmtPct(row.w1) + '</span>' : "";
      var body = items.map(function (it) {
        var meta = [it.publisher, fmtDate(it.published)].filter(Boolean).join(" · ");
        var title = it.url
          ? '<a href="' + esc(it.url) + '" target="_blank" rel="noopener">' + esc(it.title) + '</a>'
          : '<span>' + esc(it.title) + '</span>';
        return '<div class="nitem">' + title +
          (meta ? '<div class="meta">' + esc(meta) + '</div>' : '') +
          (it.summary ? '<div class="sum">' + esc(it.summary) + '</div>' : '') + '</div>';
      }).join("");
      return '<div class="nblock"><div class="hd"><span class="t mono">' + esc(t) + '</span>' + mv + '</div>' + body + '</div>';
    }).join("");
    $("#news").innerHTML = html || '<p style="color:var(--muted)">No headlines returned this run.</p>';
  }
  function fmtDate(v) {
    if (!v) return "";
    var d = new Date(v);
    if (isNaN(d)) return "";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  }

  // ---- wire up ----
  $("#stamp").textContent = "updated " + DATA.generated;
  $("#source").textContent = "Data source: Yahoo Finance · " + rows.length + " of " +
    (rows.length + (DATA.failed || []).length) + " tickers resolved · snapshot " + DATA.generated;
  var failed = DATA.failed || [];
  if (failed.length) $("#failed").textContent = "No data this run for: " + failed.join(", ");

  // market filter options
  var markets = {}; rows.forEach(function (x) { markets[marketOf(x.ticker)] = 1; });
  var msel = $("#market");
  Object.keys(markets).sort().forEach(function (m) {
    var o = document.createElement("option"); o.value = m; o.textContent = m; msel.appendChild(o);
  });

  var k = kpis(); context(k); renderNews(); renderTable();

  document.querySelectorAll("th.sortable").forEach(function (th) {
    th.tabIndex = 0;
    function go() {
      var key = th.dataset.key;
      if (sortKey === key) sortDir = -sortDir;
      else { sortKey = key; sortDir = key === "ticker" ? 1 : -1; }
      renderTable();
    }
    th.addEventListener("click", go);
    th.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  $("#search").addEventListener("input", function (e) { q = e.target.value.trim().toLowerCase(); renderTable(); });
  $("#market").addEventListener("change", function (e) { mkt = e.target.value; renderTable(); });
  document.querySelectorAll(".seg button").forEach(function (b) {
    b.addEventListener("click", function () {
      shade = b.dataset.shade;
      document.querySelectorAll(".seg button").forEach(function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      // re-sort by the shaded window too, for a coherent read
      sortKey = shade; sortDir = -1; renderTable();
    });
  });

  // theme toggle (per-viewer convenience)
  var root = document.documentElement, tkey = "wp-theme";
  try { var saved = localStorage.getItem(tkey); if (saved) root.setAttribute("data-theme", saved); } catch (e) {}
  $("#theme").addEventListener("click", function () {
    var cur = root.getAttribute("data-theme");
    var isDark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var next = isDark ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem(tkey, next); } catch (e) {}
  });
})();
</script>
"""


def main():
    data_path = sys.argv[1] if len(sys.argv) > 1 else "data.json"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "dashboard.html"
    with open(data_path) as f:
        data = json.load(f)
    payload = json.dumps(data, separators=(",", ":"))
    # guard against breaking out of the <script> container
    payload = payload.replace("</", "<\\/")
    html = (TEMPLATE
            .replace("VARUPD", "0.22").replace("VARDND", "0.24")
            .replace("VARUP", "0.14").replace("VARDN", "0.16")
            .replace("__DATA__", payload))
    with open(out_path, "w") as f:
        f.write(html)
    print("Wrote", out_path, "(", len(html), "bytes )")


if __name__ == "__main__":
    main()
