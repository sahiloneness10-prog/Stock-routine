#!/usr/bin/env python3
"""Watchlist Pulse — fetch live price/volume data from Yahoo Finance and render a
self-contained, static HTML dashboard (index.html) with 3-day / 1-week / 1-month
% moves, volume changes, sparklines and a news/catalysts section.

Run:  python3 generate_dashboard.py
Output: index.html + data.json in the same directory.
News/catalyst blurbs in NEWS[] are curated and should be refreshed periodically.
"""
import urllib.request, json, concurrent.futures, time

TICKERS = ["VENU","DUKR","LNZA","SIDU","STLTECH.NS","HFCL.NS","TEJASNET.NS","HLIT","NBIS","PENG","NOK","SLOIF","TE","FLNC","MITK","HUMA","AAOI","BE","SWMR","AMPX","KRKNF","AXTI","COHR","VYX","NATL","FLTR.L","LODE","SATL","SNDK","MOH","HAL","PFE","EWZ","MELI","DUOL","KLAR","FIG","ASML","TATE.L","HAIN","XIACY","VWSYF","ZETA","GYM.L","GNC.L","BYDDY","BYND","DKS","OTLY","SNOW","SAP","WDAY","MKS.L","JD.L","TRN.L","NTPCGREEN.NS","HMC","GSK.L","TSM","TIMEX.BO","0HAO.IL","NVDA","BT-A.L","JDW.L","SBRY.L","ADTN"]

HDRS = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def pct(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100.0

def fetch(sym):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d'
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HDRS)
            d = json.load(urllib.request.urlopen(req, timeout=25))
            r = d['chart']['result'][0]
            meta = r['meta']
            q = r['indicators']['quote'][0]
            closes = q['close']
            vols = q['volume']
            ts = r['timestamp']
            # clean: keep indices where close not None
            data = [(ts[i], closes[i], vols[i]) for i in range(len(ts)) if closes[i] is not None]
            if len(data) < 5:
                return sym, {'error':'insufficient data'}
            price = meta.get('regularMarketPrice') or data[-1][1]
            cur = price
            c = [x[1] for x in data]
            v = [x[2] if x[2] is not None else 0 for x in data]
            n = len(c)
            def close_ago(k):
                idx = n-1-k
                return c[idx] if idx >= 0 else None
            d3 = pct(cur, close_ago(3))
            d5 = pct(cur, close_ago(5))
            d21 = pct(cur, close_ago(21))
            # volume change: latest vol vs 20-day avg (excluding latest)
            lastvol = v[-1]
            prior = [x for x in v[-21:-1] if x] or [x for x in v[-6:-1] if x]
            avgvol = sum(prior)/len(prior) if prior else None
            volchg = pct(lastvol, avgvol)
            return sym, {
                'price': round(cur,4),
                'currency': meta.get('currency'),
                'exch': meta.get('fullExchangeName'),
                'name': meta.get('shortName') or meta.get('longName') or sym,
                'd3': d3, 'd5': d5, 'd21': d21,
                'volchg': volchg,
                'lastvol': lastvol, 'avgvol': avgvol,
                'spark': c[-22:] if n>=22 else c,
            }
        except Exception as e:
            if attempt == 2:
                return sym, {'error': f'{type(e).__name__}: {e}'}
            time.sleep(1.5*(attempt+1))



import json, datetime, html

import os
SP=os.path.dirname(os.path.abspath(__file__))+os.sep
# fetch live data for all tickers
import concurrent.futures as _cf
data={}
with _cf.ThreadPoolExecutor(max_workers=8) as _ex:
    for _s,_r in _ex.map(fetch,TICKERS):
        data[_s]=_r
# substitute FLUT for Flutter (delisted from LSE) and mark unavailable symbols
if 'error' in data.get('FLTR.L',{'error':1}):
    _s,_r=fetch('FLUT'); _r['note']='Flutter Entertainment (moved from LSE to NYSE; shown as FLUT)'; data['FLTR.L']=_r
json.dump(data,open(SP+'data.json','w'))

ORDER=["VENU","DUKR","LNZA","SIDU","STLTECH.NS","HFCL.NS","TEJASNET.NS","HLIT","NBIS","PENG","NOK","SLOIF","TE","FLNC","MITK","HUMA","AAOI","BE","SWMR","AMPX","KRKNF","AXTI","COHR","VYX","NATL","FLTR.L","LODE","SATL","SNDK","MOH","HAL","PFE","EWZ","MELI","DUOL","KLAR","FIG","ASML","TATE.L","HAIN","XIACY","VWSYF","ZETA","GYM.L","GNC.L","BYDDY","BYND","DKS","OTLY","SNOW","SAP","WDAY","MKS.L","JD.L","TRN.L","NTPCGREEN.NS","HMC","GSK.L","TSM","TIMEX.BO","0HAO.IL","NVDA","BT-A.L","JDW.L","SBRY.L","ADTN"]

CUR_SYM={'USD':'$','GBp':'p','GBP':'£','EUR':'€','INR':'₹','TWD':'NT$','HKD':'HK$','JPY':'¥','DKK':'kr','CAD':'C$','BRL':'R$','MXN':'MX$'}

# News & catalysts (dated, sourced from research)
NEWS=[
 ("HUMA","Humacyte","gain","Q3 2026 beat + pipeline catalyst","Revenue $1.0M beat $0.8M est; Symvess now ordered by 49 hospitals with Q4 sales guided to roughly double. ATEV hemodialysis BLA filing on track for Nov 2026 (3 Phase 3 studies). StoneX reiterated Speculative Buy ($1.00 PT, Nov 12); Barclays lifted PT to $0.60 (Nov 13). <b>Risk:</b> Nasdaq sub-$1 delisting warning (180-day clock).","regulatory"),
 ("ZETA","Zeta Global","gain","21st consecutive beat-and-raise (Q3, Nov 9)","Revenue $493M, +46% YoY (+30% organic ex-Marigold/political); non-GAAP EPS $0.38 vs $0.28 est. Generated positive GAAP net income YTD. Caution: guidance implies growth cooling toward ~20% in 2027.","earnings"),
 ("ADTN","ADTRAN","mixed","Q3 2026 (Nov 2): EPS beat, revenue light","EPS $0.09 beat (~$0.03 est); revenue $281M just below est. Optical +11% YoY, with supply shortages capping shipments. Stock fell ~19% initially on soft guidance midpoint & margin pressure, then rebounded +13% over 3 days. Q4 guide $272-292M.","earnings"),
 ("TE","T1 Energy","loss","Q3 2026 report (Nov 12) amid overhang","Shares slid ~14% into/after results. Ongoing overhang from Nov-2025 DOJ grand-jury subpoena & SEC document request tied to an executive's 2023 stock sales. Advancing U.S. solar supply-chain (domestic polysilicon/wafer) strategy; consensus 'Moderate Buy', ~$7.60 PT.","regulatory"),
 ("SNDK","Sandisk","gain","AI-driven NAND shortage; +16% on the week","SanDisk reportedly raised NAND contract prices ~50%; TrendForce sees NAND +55-60% and DRAM +90-95% in early 2026. SK Hynix/Citi flag memory shortfall lasting into late 2027. Still -33% on the month — high volatility.","news"),
 ("NVDA","NVIDIA","loss","AI-sector pullback; volume surge","-7% over 3 days on heavy volume (~+350% vs avg) amid an AI/memory-crunch-driven sector de-rate. GTC Berlin (late Oct) reinforced expansion beyond GPUs; board approved a record ~$150B buyback boost (total authorization ~$235B).","news"),
 ("DUKR","Duke Robotics","loss","-21% on a ~620% volume spike","Micro-cap defense/robotics name; no single confirmed catalyst. Recent commentary cites rising competition and ongoing operating losses overshadowing contract wins. Elevated volatility — treat quotes with caution.","news"),
 ("VWSYF","Vestas Wind","news","Volume spike (~+480% vs avg)","Thinly-traded OTC line of Vestas Wind Systems; large relative-volume print with a modest price move — typically an ADR/liquidity artefact rather than fresh company news.","news"),
]

def fmt_pct(v):
    if v is None: return ('--','flat')
    cls='pos' if v>0.05 else ('neg' if v<-0.05 else 'flat')
    return (f'{v:+.1f}%', cls)

def spark(vals, w=120, h=30):
    vals=[v for v in vals if v is not None]
    if len(vals)<2: return ''
    lo,hi=min(vals),max(vals)
    rng=hi-lo or 1
    pts=[]
    for i,v in enumerate(vals):
        x=i/(len(vals)-1)*w
        y=h-2-((v-lo)/rng)*(h-4)
        pts.append(f'{x:.1f},{y:.1f}')
    up = vals[-1]>=vals[0]
    col='var(--pos)' if up else 'var(--neg)'
    return f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none"><polyline points="{" ".join(pts)}" fill="none" stroke="{col}" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>'

# build rows
rows=[]
ok=[]
for sym in ORDER:
    r=data.get(sym,{})
    if 'error' in r or not r:
        rows.append({'sym':sym,'err':True,'note':r.get('error','no data') if r else 'no data'})
        continue
    ok.append((sym,r))
    rows.append({'sym':sym,'err':False,'r':r})

# stats
gain=sum(1 for s,r in ok if (r.get('d3') or 0)>0.05)
loss=sum(1 for s,r in ok if (r.get('d3') or 0)<-0.05)
d3list=[r['d3'] for s,r in ok if r.get('d3') is not None]
avg3=sum(d3list)/len(d3list) if d3list else 0
best=max(ok,key=lambda x:x[1].get('d3') if x[1].get('d3') is not None else -999)
worst=min(ok,key=lambda x:x[1].get('d3') if x[1].get('d3') is not None else 999)
volspk=max(ok,key=lambda x:x[1].get('volchg') if x[1].get('volchg') is not None else -1e9)

now=datetime.datetime.utcnow().strftime('%a %d %b %Y, %H:%M UTC')

def pricefmt(r):
    c=r.get('currency','')
    sym=CUR_SYM.get(c,'')
    p=r.get('price')
    if p is None: return '--'
    if p<1: s=f'{p:.3f}'
    elif p<1000: s=f'{p:,.2f}'
    else: s=f'{p:,.0f}'
    return f'{sym}{s}' + ('' if sym else f' {c}')

# table body
def tr(row):
    if row['err']:
        return f'<tr class="err"><td class="tk">{html.escape(row["sym"])}</td><td colspan="7" class="muted">data unavailable — {html.escape(row["note"])}</td></tr>'
    r=row['r']; sym=row['sym']
    d3=fmt_pct(r.get('d3')); d5=fmt_pct(r.get('d5')); d21=fmt_pct(r.get('d21')); vc=fmt_pct(r.get('volchg'))
    nm=html.escape(r.get('name',sym))
    note=r.get('note')
    nmline=f'<span class="nm">{nm}</span>' + (f'<span class="subnote">{html.escape(note)}</span>' if note else '')
    hasnews=' has-news' if sym in {n[0] for n in NEWS} else ''
    def cell(t): return f'<td class="num {t[1]}" data-v="{(r.get(key) if (r.get(key) is not None) else -99999):.4f}">{t[0]}</td>'
    # manual to include data-v
    def numcell(val,t):
        dv = val if val is not None else -99999
        return f'<td class="num {t[1]}" data-v="{dv:.4f}">{t[0]}</td>'
    return (f'<tr class="datarow{hasnews}">'
      f'<td class="tk"><span class="sym">{html.escape(sym)}</span>{nmline}</td>'
      f'<td class="price">{pricefmt(r)}</td>'
      + numcell(r.get('d3'),d3) + numcell(r.get('d5'),d5) + numcell(r.get('d21'),d21) + numcell(r.get('volchg'),vc)
      + f'<td class="sk">{spark(r.get("spark",[]))}</td>'
      + f'<td class="exch">{html.escape((r.get("exch") or "").replace("NMS","Nasdaq").replace("NGM","Nasdaq"))}</td>'
      '</tr>')

tbody='\n'.join(tr(row) for row in rows)

# news cards
def ncard(n):
    sym,name,kind,head,body,tag=n
    r=data.get(sym,{})
    badge={'gain':'▲ Gainer','loss':'▼ Decliner','mixed':'◆ Mixed','news':'● Flow'}[kind]
    tagcls={'regulatory':'t-reg','earnings':'t-earn','news':'t-news'}[tag]
    taglbl={'regulatory':'Regulatory','earnings':'Earnings','news':'News'}[tag]
    chg=''
    if 'error' not in r and r:
        d3=fmt_pct(r.get('d3'))
        chg=f'<span class="chg {d3[1]}">{d3[0]} 3d</span>'
    return (f'<article class="news {kind}">'
      f'<div class="nhead"><span class="nsym">{html.escape(sym)}</span>'
      f'<span class="nname">{html.escape(name)}</span>'
      f'<span class="badge {kind}">{badge}</span>{chg}'
      f'<span class="tag {tagcls}">{taglbl}</span></div>'
      f'<h3>{head}</h3><p>{body}</p></article>')

newshtml='\n'.join(ncard(n) for n in NEWS)

errn=sum(1 for row in rows if row['err'])

HTML=f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watchlist Pulse</title>
<meta name="description" content="Daily watchlist dashboard: 3-day, 1-week and 1-month price moves, volume changes, and news catalysts across {len(ok)} tickers.">
<style>
:root{{
  --bg:#f6f7f9; --panel:#ffffff; --panel2:#fbfcfd; --ink:#11161d; --muted:#6b7684;
  --line:#e4e8ee; --line2:#eef1f5; --accent:#3b6ef2;
  --pos:#1f9d6b; --pos-bg:#e7f6ef; --neg:#e0514e; --neg-bg:#fcebea; --flat:#8a95a3;
  --head:#0f1620; --shadow:0 1px 3px rgba(16,24,40,.06),0 1px 2px rgba(16,24,40,.04);
  --reg:#8b5cf6; --earn:#2563eb; --newsc:#0ea5a3;
}}
:root:not([data-theme="light"]) @media (prefers-color-scheme: dark){{}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{
  --bg:#0c0f14; --panel:#141922; --panel2:#11161e; --ink:#e8edf4; --muted:#8e9aab;
  --line:#242c38; --line2:#1c232e; --accent:#5b8cff;
  --pos:#35c58a; --pos-bg:#11291f; --neg:#ff6b66; --neg-bg:#2a1413; --flat:#73808f;
  --head:#f2f6fc; --shadow:0 1px 3px rgba(0,0,0,.4);
  --reg:#a78bfa; --earn:#60a5fa; --newsc:#2dd4bf;
}}}}
:root[data-theme="dark"]{{
  --bg:#0c0f14; --panel:#141922; --panel2:#11161e; --ink:#e8edf4; --muted:#8e9aab;
  --line:#242c38; --line2:#1c232e; --accent:#5b8cff;
  --pos:#35c58a; --pos-bg:#11291f; --neg:#ff6b66; --neg-bg:#2a1413; --flat:#73808f;
  --head:#f2f6fc; --shadow:0 1px 3px rgba(0,0,0,.4);
  --reg:#a78bfa; --earn:#60a5fa; --newsc:#2dd4bf;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}}
.wrap{{max-width:1180px;margin:0 auto;padding:28px 16px 64px}}
header.top{{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:22px}}
h1{{font-size:26px;letter-spacing:-.02em;margin:0;color:var(--head);font-weight:750}}
h1 .dot{{color:var(--accent)}}
.sub{{color:var(--muted);font-size:13px;margin-top:4px}}
.asof{{font-variant-numeric:tabular-nums}}
.pill{{display:inline-block;background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:12px;color:var(--muted);margin-left:6px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:26px}}
.stat{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}}
.stat .l{{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}}
.stat .v{{font-size:23px;font-weight:720;margin-top:5px;letter-spacing:-.01em;font-variant-numeric:tabular-nums}}
.stat .m{{font-size:12px;color:var(--muted);margin-top:2px}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .flat{{color:var(--flat)}}
h2{{font-size:13px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:700;margin:30px 0 13px;display:flex;align-items:center;gap:8px}}
h2::after{{content:"";flex:1;height:1px;background:var(--line)}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}}
.tablewrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;min-width:720px}}
thead th{{position:sticky;top:0;background:var(--panel2);text-align:right;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:650;padding:11px 12px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}}
thead th:first-child,thead th.exh{{text-align:left}}
thead th.sortable:hover{{color:var(--ink)}}
thead th.active{{color:var(--accent)}}
tbody td{{padding:9px 12px;border-bottom:1px solid var(--line2);text-align:right;white-space:nowrap}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr.datarow:hover{{background:var(--panel2)}}
tr.has-news .sym::after{{content:"news";font-size:9px;background:var(--accent);color:#fff;border-radius:4px;padding:1px 4px;margin-left:6px;vertical-align:middle;letter-spacing:.03em;font-weight:600;text-transform:uppercase}}
.tk{{text-align:left;max-width:280px}}
.sym{{font-weight:700;font-size:13px;letter-spacing:-.01em}}
.nm{{display:block;color:var(--muted);font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:240px}}
.subnote{{display:block;color:var(--accent);font-size:10.5px}}
.price{{font-weight:600}}
.num{{font-weight:600}}
.num.pos{{color:var(--pos)}} .num.neg{{color:var(--neg)}} .num.flat{{color:var(--flat)}}
.sk{{width:130px}} .spark{{width:120px;height:30px;display:block;margin-left:auto}}
.exch{{text-align:left!important;color:var(--muted);font-size:11px;font-weight:500}}
.exh{{}}
tr.err td{{color:var(--muted)}} .muted{{color:var(--muted)}}
.newsgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:13px}}
.news{{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--flat);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}}
.news.gain{{border-left-color:var(--pos)}} .news.loss{{border-left-color:var(--neg)}}
.news.mixed{{border-left-color:var(--earn)}} .news.news{{border-left-color:var(--newsc)}}
.nhead{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-bottom:7px}}
.nsym{{font-weight:750;font-size:14px}}
.nname{{color:var(--muted);font-size:12px}}
.badge{{font-size:10px;font-weight:650;padding:1px 7px;border-radius:999px;letter-spacing:.02em}}
.badge.gain{{background:var(--pos-bg);color:var(--pos)}} .badge.loss{{background:var(--neg-bg);color:var(--neg)}}
.badge.mixed{{background:var(--pos-bg);color:var(--earn)}} .badge.news{{background:var(--panel2);color:var(--newsc)}}
.chg{{font-size:11px;font-weight:650;font-variant-numeric:tabular-nums}}
.tag{{margin-left:auto;font-size:9.5px;text-transform:uppercase;letter-spacing:.05em;font-weight:700;padding:2px 7px;border-radius:5px}}
.t-reg{{background:color-mix(in srgb,var(--reg) 16%,transparent);color:var(--reg)}}
.t-earn{{background:color-mix(in srgb,var(--earn) 16%,transparent);color:var(--earn)}}
.t-news{{background:color-mix(in srgb,var(--newsc) 16%,transparent);color:var(--newsc)}}
.news h3{{font-size:13.5px;margin:0 0 5px;line-height:1.35;color:var(--head);font-weight:650}}
.news p{{margin:0;font-size:12.5px;color:var(--muted);line-height:1.5}}
.news p b{{color:var(--ink)}}
footer{{margin-top:34px;color:var(--muted);font-size:11.5px;line-height:1.6}}
footer a{{color:var(--accent)}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;margin:12px 2px 0;font-size:11.5px;color:var(--muted)}}
.legend span{{display:inline-flex;align-items:center;gap:5px}}
.sw{{width:10px;height:10px;border-radius:3px;display:inline-block}}
@media(max-width:560px){{h1{{font-size:21px}} .wrap{{padding:20px 16px 48px}} .stat .v{{font-size:20px}}}}
</style></head>
<body><div class="wrap">
<header class="top">
  <div>
    <h1>Watchlist <span class="dot">Pulse</span></h1>
    <div class="sub">Price momentum, volume & catalysts across your {len(ORDER)} tickers
      <span class="pill">{len(ok)} live</span>{f'<span class="pill">{errn} unavailable</span>' if errn else ''}</div>
  </div>
  <div class="sub asof">As of {now}</div>
</header>

<div class="stats">
  <div class="stat"><div class="l">Gainers · 3d</div><div class="v pos">{gain}</div><div class="m">of {len(ok)} with data</div></div>
  <div class="stat"><div class="l">Decliners · 3d</div><div class="v neg">{loss}</div><div class="m">of {len(ok)} with data</div></div>
  <div class="stat"><div class="l">Avg move · 3d</div><div class="v {('pos' if avg3>0 else 'neg')}">{avg3:+.1f}%</div><div class="m">watchlist mean</div></div>
  <div class="stat"><div class="l">Top gainer · 3d</div><div class="v pos">{best[1].get('d3'):+.1f}%</div><div class="m">{html.escape(best[0])} · {html.escape(best[1].get('name','')[:20])}</div></div>
  <div class="stat"><div class="l">Top decliner · 3d</div><div class="v neg">{worst[1].get('d3'):+.1f}%</div><div class="m">{html.escape(worst[0])} · {html.escape(worst[1].get('name','')[:20])}</div></div>
  <div class="stat"><div class="l">Volume spike</div><div class="v">{volspk[1].get('volchg'):+.0f}%</div><div class="m">{html.escape(volspk[0])} vs 20d avg</div></div>
</div>

<h2>News &amp; catalysts</h2>
<div class="newsgrid">
{newshtml}
</div>

<h2>Full watchlist</h2>
<div class="panel"><div class="tablewrap">
<table id="t">
<thead><tr>
  <th class="sortable" data-k="0" data-t="s">Ticker</th>
  <th class="sortable" data-k="1" data-t="s">Price</th>
  <th class="sortable active" data-k="2" data-t="n">3-Day</th>
  <th class="sortable" data-k="3" data-t="n">1-Week</th>
  <th class="sortable" data-k="4" data-t="n">1-Month</th>
  <th class="sortable" data-k="5" data-t="n">Vol Δ</th>
  <th>Trend · 1m</th>
  <th class="exh">Exchange</th>
</tr></thead>
<tbody>
{tbody}
</tbody>
</table>
</div></div>
<div class="legend">
  <span><i class="sw" style="background:var(--pos)"></i>Up</span>
  <span><i class="sw" style="background:var(--neg)"></i>Down</span>
  <span>Vol Δ = latest session volume vs 20-day average</span>
  <span>Click any column header to sort · trend shows ~1 month of closes</span>
</div>

<footer>
  <b>Watchlist Pulse</b> — generated automatically {now}. Price &amp; volume data from Yahoo Finance (delayed);
  % changes use trading-day closes (3-day ≈ 3 sessions, 1-week ≈ 5 sessions, 1-month ≈ 21 sessions).
  FLTR.L is shown as <b>FLUT</b> (Flutter Entertainment moved its primary listing from LSE to NYSE).
  {('0HAO.IL is not available on the data source. ' if errn else '')}
  News items are summarized from public reporting and may include dates/figures that warrant verification against primary filings.
  This is an informational snapshot, <b>not investment advice</b>.
</footer>
</div>
<script>
(function(){{
 var tb=document.querySelector('#t tbody'), ths=document.querySelectorAll('#t th.sortable');
 var state={{k:2,dir:-1}};
 function rows(){{return Array.prototype.slice.call(tb.querySelectorAll('tr'));}}
 function sortBy(k,type,dir){{
   var rs=rows();
   // keep error rows at bottom
   rs.sort(function(a,b){{
     var ae=a.classList.contains('err'), be=b.classList.contains('err');
     if(ae!==be) return ae?1:-1;
     if(ae&&be) return 0;
     var av,bv;
     if(type==='n'){{ av=parseFloat(a.children[k].getAttribute('data-v')); bv=parseFloat(b.children[k].getAttribute('data-v')); }}
     else {{ av=a.children[k].textContent.trim().toLowerCase(); bv=b.children[k].textContent.trim().toLowerCase(); return av<bv?-1*dir:av>bv?1*dir:0; }}
     if(isNaN(av))av=-1e12; if(isNaN(bv))bv=-1e12;
     return (av-bv)*dir;
   }});
   rs.forEach(function(r){{tb.appendChild(r);}});
 }}
 ths.forEach(function(th){{
   th.addEventListener('click',function(){{
     var k=+th.getAttribute('data-k'), type=th.getAttribute('data-t');
     if(state.k===k){{state.dir*=-1;}} else {{state.k=k;state.dir=(type==='n')?-1:1;}}
     ths.forEach(function(x){{x.classList.remove('active');}}); th.classList.add('active');
     sortBy(k,type,state.dir);
   }});
 }});
}})();
</script>
</body></html>'''

open(SP+'index.html','w').write(HTML)
print('wrote index.html', len(HTML),'bytes;', len(ok),'live,',errn,'unavailable')
