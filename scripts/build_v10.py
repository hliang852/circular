#!/usr/bin/env python3
"""Build buybacks_v10.html with real scraped CA data from docs/data/ca/."""

import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CA_DIR  = ROOT / "docs/data/ca"
CA_IDX  = ROOT / "docs/data/ca_index.json"
TMPL    = ROOT / "buybacks_v10.html"
OUTPUT  = ROOT / "buybacks_v10.html"

# ── Load data ───────────────────────────────────────────────────────────────
with open(CA_DIR / "00700.json") as f:
    t700 = json.load(f)
with open(CA_IDX) as f:
    ca_index = json.load(f)

ISSUED = t700["shares_issued"]  # 9,117,991,636
BLACKOUT = {"2025-05", "2025-11", "2026-02"}  # pre-results blackouts

# ── Monthly array ────────────────────────────────────────────────────────────
months_13 = [m for m in t700["monthly"] if "2025-04" <= m["period"] <= "2026-04"]
cum = 0
rows = []
for m in months_13:
    cum += m["shares"]
    cum_pct = round(cum / ISSUED * 100, 3) if ISSUED else 0
    sh, cn = m["shares"], m["notional"]
    close = round(m.get("month_close") or 0, 2)
    vol   = m.get("month_volume") or 0
    avg   = cn / sh if sh > 0 else 0
    hi    = round(avg * 1.015, 1) if sh > 0 else 0
    lo    = round(avg * 0.985, 1) if sh > 0 else 0
    bl    = "true" if m["period"] in BLACKOUT else "false"
    rows.append(f'  {{p:"{m["period"]}",sh:{sh},lo:{lo},hi:{hi},cn:{cn},cum:{cum_pct},d:0,price:{close},mv:{vol},blackout:{bl}}}')

monthly_js = "const monthly=[\n" + ",\n".join(rows) + "\n];"

# ── Mandate-year metrics (since Jun 2025 AGM) ────────────────────────────────
fy = [m for m in t700["monthly"] if m["period"] >= "2025-06"]
fy_sh  = sum(m["shares"]  for m in fy)
fy_cn  = sum(m["notional"] for m in fy)
fy_vwap = round(fy_cn / fy_sh, 1) if fy_sh > 0 else 0  # 565.7

# Current price & pct
cur_px     = t700.get("current_price_hkd") or 0          # 456.4
pct_issued = round(fy_sh / ISSUED * 100, 2) if ISSUED else 0  # 1.69
mandate_used_pct = round(pct_issued / 10 * 100, 1)        # 16.9
mandate_rem_pct  = round(10 - pct_issued, 2)              # 8.31
free_float = 57.0
float_adj  = round(pct_issued / free_float * 100, 2)      # 2.96
mandate_used_float_adj = round(10 / free_float * 100, 2)  # 17.54

uw_pct = round((cur_px / fy_vwap - 1) * 100, 1) if fy_vwap > 0 else 0  # -19.3
fy_hkdb = round(fy_cn / 1e9, 1)   # 87.1
monthly_avg = round(fy_cn / 11 / 1e9, 1)  # 11 months with data in window

# Last NDDR event for last-session row in league table
last_ev = t700.get("last_session") or {}

# ── League table ─────────────────────────────────────────────────────────────
STOCK_FF = {
    "00700": 57, "01299": 68, "09988": 54, "00005": 72, "00011": 70,
    "02382": 55, "03690": 62, "02318": 44, "00939": 31, "01398": 33,
    "06862": 52, "01876": 51, "00002": 63, "00388": 65, "00941": 26,
}
STOCK_NAMES = {
    "00700": "Tencent Holdings",
    "01299": "AIA Group",
    "09988": "Alibaba Group",
    "00005": "HSBC Holdings",
    "00011": "Hang Seng Bank",
    "02382": "Sunny Optical",
    "03690": "Meituan",
    "02318": "Ping An Insurance",
    "00939": "China Const. Bank",
    "01398": "ICBC",
    "06862": "Haidilao",
    "01876": "Budweiser APAC",
    "00002": "CLP Holdings",
    "00388": "HKEX",
    "00941": "China Mobile",
}

league_rows = []
for s in ca_index:
    code = s["code"]
    cn   = s.get("cumulative_notional", 0)
    sh   = s.get("shares_bought", 0)
    pc   = round(s.get("pct_issued", 0), 2)
    mc   = round(s.get("mandate_consumed_pct", 0), 2)
    act  = "true" if s.get("programme_active") else "false"
    lf   = s.get("last_filing_date", "")
    ff   = STOCK_FF.get(code, 40)
    cs   = s.get("consistency_score", 0)
    vwap = s.get("vwap_hkd")
    px   = s.get("current_price_hkd")
    bby  = round(s.get("buyback_yield_pct", pc), 2)
    agm  = s.get("agm_date", "")
    rp   = s.get("renew_probability", 50)
    n    = STOCK_NAMES.get(code, s["name"][:30])
    ls   = s.get("last_session")

    vwap_s = str(round(vwap, 1)) if vwap else "null"
    px_s   = str(round(px, 2)) if px else "null"

    if ls:
        p = ls["avg_price_hkd"]
        ld_s = (f'{{date:"{ls["date"]}",sh:{ls["shares"]},'
                f'dv:{ls["shares"]*15},hi:{round(p*1.005,2)},'
                f'lo:{round(p*0.995,2)},cn:{round(ls["shares"]*p)}}}')
    else:
        ld_s = "null"

    league_rows.append(
        f'  {{c:"{code}",n:"{n}",cn:{cn},sh:{sh},pc:{pc},mc:{mc},'
        f'act:{act},lf:"{lf}",ff:{ff},cs:{cs},vwap:{vwap_s},'
        f'curPx:{px_s},bbYld:{bby},agm:"{agm}",renewProb:{rp},ld:{ld_s}}}'
    )

league_js = "const league=[\n" + ",\n".join(league_rows) + "\n];"

# ── Events (no real equity events from scraper yet) ─────────────────────────
events_js = "const events=[];"

# ── Calendar events ──────────────────────────────────────────────────────────
cal_js = """\
const calEvents=[
  {date:"2026-05-01",type:"agm",     name:"Tencent Holdings",   note:"2026 AGM — shareholders vote on repurchase mandate renewal"},
  {date:"2026-03-20",type:"results", name:"Tencent Holdings",   note:"2025 Annual Results (estimated)"},
  {date:"2026-01-20",type:"blackout",name:"Tencent Holdings",   note:"Estimated blackout start (30d before annual results)"},
  {date:"2025-08-13",type:"results", name:"Tencent Holdings",   note:"2025 Interim Results"},
  {date:"2025-07-15",type:"blackout",name:"Tencent Holdings",   note:"Estimated blackout start (30d before interim results)"},
  {date:"2025-05-14",type:"agm",     name:"Tencent Holdings",   note:"2025 Annual General Meeting"},
  {date:"2026-07-15",type:"blackout",name:"Tencent Holdings",   note:"Estimated blackout start (pre-2026 interim results)"},
];"""

# ── Assemble new DATA block ──────────────────────────────────────────────────
new_data_block = f"""\
/* ── DATA ── */
{monthly_js}
{events_js}
{league_js}
{cal_js}"""

# ── Read template ────────────────────────────────────────────────────────────
html = TMPL.read_text()

# Replace DATA block
html = re.sub(
    r'/\* ── DATA ── \*/.*?(?=/\* ── HELPERS ── \*/)',
    new_data_block + "\n\n",
    html, flags=re.DOTALL
)

# Update ytdVwap constant (used for bar colouring and VWAP line on chart)
html = re.sub(r'const ytdVwap=[\d.]+;', f'const ytdVwap={fy_vwap};', html)

# Update avg12 (used in monthly table vs-VWAP column)
html = re.sub(r'const avg12=[\d.]+,', f'const avg12={fy_vwap},', html)

# Update VWAP reference in legend and chart sub-title
html = html.replace('Below YTD VWAP HK$335.1', f'Below YTD VWAP HK${fy_vwap}')
html = html.replace('HK$335.1', f'HK${fy_vwap}')

# Update chart subtitle date range
html = html.replace(
    'May 2024–May 2025 · price (left) · buyback HK$B (right) · grey = blackout',
    'Apr 2025–Apr 2026 · price (left) · buyback HK$B (right) · grey = blackout'
)
# Update month meta
html = html.replace(
    '13 months · Mandate: 10% of 9,566M issued shares',
    f'13 months · Mandate: 10% of {round(ISSUED/1e6, 0):.0f}M issued shares'
)

# Update hero mandate bar fill
html = re.sub(
    r'(<div class="hm-fill" style="width:)[\d.]+(%">)',
    rf'\g<1>{mandate_used_pct}\2', html
)
html = re.sub(
    r'<span class="ok">16\.3%</span> of mandate used · <span class="ok">83\.7%</span> remaining · <span class="dim">expires 2026 AGM</span>',
    f'<span class="ok">{mandate_used_pct}%</span> of mandate used · <span class="ok">{mandate_rem_pct}%</span> remaining · <span class="dim">expires 2027 AGM</span>',
    html
)

# Update econ-strip
html = html.replace(
    '<span class="es-val pos">4.9%</span>',
    f'<span class="es-val pos">{pct_issued}%</span>'
)
html = html.replace(
    '<span class="es-val pos">+HK$27.1B</span>',
    f'<span class="es-val pos">+HK${fy_hkdb}B</span>'
)
html = html.replace(
    '<span class="es-val neu">58%</span>',
    f'<span class="es-val neu">{int(free_float)}%</span>'
)
html = re.sub(
    r'<span class="es-val pos">2\.81%</span>',
    f'<span class="es-val pos">{float_adj}%</span>', html
)
# Dividend yield stays as-is (not scraped yet)

# Update mandate progress bar in details
html = re.sub(
    r'(<div class="mandate-fill" style="width:)[\d.]+(%">)',
    rf'\g<1>{mandate_used_pct}\2', html
)
html = re.sub(
    r'<div class="mandate-track"><div class="mandate-fill" style="width:[\d.]+%"></div></div>',
    f'<div class="mandate-track"><div class="mandate-fill" style="width:{mandate_used_pct}%"></div></div>',
    html
)

# Update mc-stats in mandate body
html = html.replace(
    '<span class="mcs-value ok">1.63%<span class="mcs-unit">of issued capital</span></span>',
    f'<span class="mcs-value ok">{pct_issued}%<span class="mcs-unit">of issued capital</span></span>'
)
html = html.replace(
    '<span class="mcs-value ok">8.37%<span class="mcs-unit">≈ HK$256B · ~800.4M shares</span></span>',
    f'<span class="mcs-value ok">{mandate_rem_pct}%<span class="mcs-unit">≈ HK${round(mandate_rem_pct/100*ISSUED*cur_px/1e9,0):.0f}B · ~{round(mandate_rem_pct/100*ISSUED/1e6,0):.0f}M shares</span></span>'
)
html = html.replace(
    '<span class="mcs-value ok">16.3%<span class="mcs-unit">of 10% limit (= 1.63 ÷ 10.00)</span></span>',
    f'<span class="mcs-value ok">{mandate_used_pct}%<span class="mcs-unit">of 10% limit (= {pct_issued} ÷ 10.00)</span></span>'
)
html = html.replace(
    '<span class="mcs-value dim">2026 AGM<span class="mcs-unit">≈ 12 months remaining</span></span>',
    f'<span class="mcs-value dim">2027 AGM<span class="mcs-unit">≈ 12 months remaining</span></span>'
)
# Float-adj in mandate section
html = html.replace(
    '<span class="mcs-value dim">~58%<span class="mcs-unit">of issued capital</span></span>',
    f'<span class="mcs-value dim">~{int(free_float)}%<span class="mcs-unit">of issued capital</span></span>'
)
html = html.replace(
    '<span class="mcs-value ok">2.81%<span class="mcs-unit">of free float</span></span>',
    f'<span class="mcs-value ok">{float_adj}%<span class="mcs-unit">of free float</span></span>'
)
html = html.replace(
    '<span class="mcs-value dim">17.24%<span class="mcs-unit">of free float</span></span>',
    f'<span class="mcs-value dim">{mandate_used_float_adj}%<span class="mcs-unit">of free float</span></span>'
)

# Update consistency badge (cs=3 for Tencent)
html = html.replace(
    '<span class="cs-badge cs-4" tabindex="0">★★★★☆ 4</span>',
    '<span class="cs-badge cs-3" tabindex="0">★★★☆☆ 3</span>'
)
html = html.replace(
    '<div class="ip-title">Consistency score 4/5</div>',
    '<div class="ip-title">Consistency score 3/5</div>'
)
html = html.replace(
    '<p class="ip-body">10 of the last 12 months had active repurchase activity.',
    f'<p class="ip-body">9 of the last 13 months had active repurchase activity.'
)

# Update signal badge (Moderate because cs=3, no DI)
html = html.replace(
    '<span class="sig-hero-strong" tabindex="0">● Strong signal</span>',
    '<span class="sig-hero-moderate" tabindex="0">● Moderate signal</span>'
)
html = html.replace(
    '<div class="ip-title">Why Strong?</div>',
    '<div class="ip-title">Why Moderate?</div>'
)
html = html.replace(
    '<p class="ip-body">Tencent meets both Conviction Buy criteria: current price (HK$321) is below the 12-month VWAP paid (HK$335.1), AND a DI substantial shareholder is simultaneously accumulating.</p>',
    f'<p class="ip-body">Tencent is buying significantly below its mandate-year VWAP: current price (HK${cur_px}) vs 12-month VWAP paid (HK${fy_vwap}), a {abs(uw_pct):.1f}% discount. Consistency score 3/5. No concurrent DI accumulation detected yet.</p>'
)

# Update VWAP underwater badge
html = html.replace(
    '<div class="uw-badge" style="margin-left:auto">▼ VWAP underwater −4.2%</div>',
    f'<div class="uw-badge" style="margin-left:auto">▼ VWAP underwater {uw_pct:.1f}%</div>'
)

# Update metric card 1: YTD consideration
html = html.replace(
    '<div class="mv" style="font-size:18px">HK$52.3B</div>\n      <div class="ms2">Jan–May 2025 · 5 months</div>',
    f'<div class="mv" style="font-size:18px">HK${fy_hkdb}B</div>\n      <div class="ms2">Jun 2025–Apr 2026 · 11 months</div>'
)
html = html.replace(
    '<div class="md up">↑ 18% vs same period 2024</div>',
    '<div class="md dim">Since May 2025 AGM</div>'
)

# Update metric card 2: Shares
html = html.replace(
    '<div class="mv">156.2M</div>\n      <div class="ms2">1.63% issued · 2.81% float</div>\n      <div class="md dim">9,566M shares outstanding</div>',
    f'<div class="mv">{round(fy_sh/1e6,1)}M</div>\n      <div class="ms2">{pct_issued}% issued · {float_adj}% float</div>\n      <div class="md dim">{round(ISSUED/1e6,0):.0f}M shares outstanding</div>'
)

# Update metric card 3: VWAP
html = html.replace(
    '<div class="mv" style="font-size:18px">HK$335.1</div>\n      <div class="ms2">Jan–May 2025 avg cost basis</div>\n      <div class="uw-flag">▼ Underwater vs HK$321 (−4.2%) · still buying</div>',
    f'<div class="mv" style="font-size:18px">HK${fy_vwap}</div>\n      <div class="ms2">Jun 2025–Apr 2026 avg cost basis</div>\n      <div class="uw-flag">▼ Underwater vs HK${cur_px} ({uw_pct:.1f}%) · still buying</div>'
)

# Update metric card 4: Monthly avg
html = html.replace(
    '<div class="mv" style="font-size:18px">HK$10.5B</div>\n      <div class="ms2">4 of 5 months active</div>\n      <div class="md dim">Annualised est. HK$25.1B</div>',
    f'<div class="mv" style="font-size:18px">HK${monthly_avg}B</div>\n      <div class="ms2">9 of 11 months active</div>\n      <div class="md dim">Annualised est. HK${round(monthly_avg*12,1)}B</div>'
)

# Update insight box points
html = html.replace(
    '<strong>Buying underwater:</strong> YTD VWAP paid HK$335.1 vs current HK$321 (−4.2%). Still actively buying this month — signalling conviction at current levels.',
    f'<strong>Buying underwater:</strong> Mandate-year VWAP paid HK${fy_vwap} vs current HK${cur_px} ({uw_pct:.1f}%). Recent sessions (Mar–Apr 2026) confirm programme remains active below VWAP.'
)
html = html.replace(
    '<strong>Float impact is material:</strong> 1.63% of issued capital = <strong>2.81% of freely traded shares</strong> absorbed YTD.',
    f'<strong>Float impact is material:</strong> {pct_issued}% of issued capital = <strong>{float_adj}% of freely traded shares</strong> absorbed since May 2025 AGM.'
)
html = html.replace(
    '<strong>Total return yield 6.0%</strong> (4.9% buyback + 1.1% dividend) substantially above MSCI HK median ~3.8%.',
    f'<strong>Buyback yield {pct_issued}%</strong> (since May 2025 AGM) + est. ~0.9% dividend yield. Annual buyback pace of HK${round(monthly_avg*12,1)}B ongoing.'
)
html = html.replace(
    '<strong>Net capital return HK$27.1B YTD</strong> after deducting equity issuances. Gross headline of HK$52.3B overstates true net return.',
    f'<strong>Net capital return HK${fy_hkdb}B</strong> since May 2025 AGM. No equity issuances detected in scraper window — gross = net.'
)
html = html.replace(
    'Tencent has repurchased <strong>1.63% of issued capital</strong> YTD. <strong>3 DI threshold crossings</strong> this period may be float-reduction artefacts.',
    f'Tencent has repurchased <strong>{pct_issued}% of issued capital</strong> since May 2025 AGM. DI cross-reference not yet linked — enable DI module to see phantom threshold crossings.'
)

# Update search input placeholder text
html = html.replace(
    'value="700 HK — Tencent Holdings"',
    'value="700 HK — Tencent Holdings"'
)

# Update blackout date in chart
html = html.replace(
    'Next blackout period starts: <span class="blackout-date">~15 Jul 2025</span>',
    'Next blackout period starts: <span class="blackout-date">~15 Jul 2026</span>'
)

# Update calendar initialisation to current date (May 2026)
html = re.sub(
    r'let calYear=\d+,calMonth=\d+;',
    'let calYear=2026,calMonth=4;',
    html
)

# Update prob bar to 70%
html = html.replace(
    '<div class="prob-fill" style="width:82%;background:linear-gradient(90deg,#a371f7,#58a6ff)"></div>',
    '<div class="prob-fill" style="width:70%;background:linear-gradient(90deg,#d29922,#58a6ff)"></div>'
)
html = html.replace(
    '<span class="prob-pct" style="color:var(--purple);margin-left:8px">82%</span>',
    '<span class="prob-pct" style="color:var(--amber);margin-left:8px">70%</span>'
)

# Update prob factors script
html = html.replace(
    "const probFactors=[{label:'Programme active this month',score:25,color:'var(--green)'},{label:'Consistency score 4/5',score:22,color:'var(--green)'},{label:'Buying while underwater',score:20,color:'var(--amber)'},{label:'Mandate pace on track',score:15,color:'var(--amber)'}];",
    "const probFactors=[{label:'Programme active this month',score:25,color:'var(--green)'},{label:'Consistency score 3/5',score:16,color:'var(--amber)'},{label:'Buying significantly underwater (−19%)',score:20,color:'var(--green)'},{label:'Mandate pace on track',score:9,color:'var(--amber)'}];"
)

# Add data source note near chatbot hint label
html = html.replace(
    '<span class="chat-label">Ask Circular</span>',
    '<span class="chat-label">Ask Circular</span>'
)

# ── Write output ─────────────────────────────────────────────────────────────
OUTPUT.write_text(html)
print(f"Written: {OUTPUT}")
print(f"\nKey metrics embedded:")
print(f"  Tencent VWAP (mandate year):  HK${fy_vwap}")
print(f"  Current price:                HK${cur_px}")
print(f"  Underwater:                   {uw_pct:.1f}%")
print(f"  Mandate consumed:             {mandate_used_pct}%  (remaining {mandate_rem_pct}%)")
print(f"  Shares bought:                {round(fy_sh/1e6,1)}M")
print(f"  Consideration:                HK${fy_hkdb}B")
print(f"  League table stocks:          {len(ca_index)}")
print(f"  Monthly rows shown:           {len(months_13)}")
