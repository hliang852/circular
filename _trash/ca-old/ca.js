'use strict';

/* ── League index — loaded from ca_index.json at startup ── */
let league = [];

function mapIndexRow(r) {
  // Map ca_index.json field names to the shorthand used throughout this file
  const ls = r.last_session;
  return {
    c:        r.code,
    n:        r.name,
    cn:       r.cumulative_notional   || 0,
    sh:       r.shares_bought         || 0,
    pc:       r.pct_issued            || 0,
    mc:       r.mandate_consumed_pct  || 0,
    act:      r.programme_active      || false,
    lf:       r.last_filing_date      || '',
    ff:       r.free_float_pct        || 35,
    cs:       r.consistency_score     || 0,
    vwap:     r.vwap_hkd              || 0,
    curPx:    r.current_price_hkd     || 0,
    bbYld:    r.pct_issued            || 0,
    agm:      r.agm_date              || '',
    renewProb:r.renew_probability     || 0,
    ld: ls ? {
      date: ls.date,
      sh:   ls.shares        || 0,
      dv:   ls.shares * 20,  // rough estimate: buyback ≈ 5% of daily vol
      hi:   ls.avg_price_hkd || 0,
      lo:   ls.avg_price_hkd || 0,
      cn:   Math.round((ls.shares || 0) * (ls.avg_price_hkd || 0)),
    } : null,
  };
}

const calEvents = [
  {date:"2026-05-20",type:"agm",     name:"Tencent Holdings",   note:"2026 Annual General Meeting"},
  {date:"2026-05-21",type:"agm",     name:"China Mobile",       note:"2026 Annual General Meeting"},
  {date:"2026-05-26",type:"agm",     name:"Sunny Optical",      note:"2026 Annual General Meeting"},
  {date:"2026-05-27",type:"agm",     name:"Meituan",            note:"2026 Annual General Meeting"},
  {date:"2026-06-03",type:"agm",     name:"Ping An Insurance",  note:"2026 Annual General Meeting"},
  {date:"2026-06-10",type:"agm",     name:"China Const. Bank",  note:"2026 Annual General Meeting"},
  {date:"2026-06-12",type:"agm",     name:"Haidilao",           note:"2026 Annual General Meeting"},
  {date:"2026-06-17",type:"agm",     name:"ICBC",               note:"2026 Annual General Meeting"},
  {date:"2026-06-19",type:"agm",     name:"Budweiser APAC",     note:"2026 Annual General Meeting"},
  {date:"2026-07-15",type:"blackout",name:"Tencent Holdings",   note:"Estimated blackout start (30d before interim results)"},
  {date:"2026-07-29",type:"results", name:"HSBC Holdings",      note:"2026 Interim Results"},
  {date:"2026-08-12",type:"results", name:"Tencent Holdings",   note:"2026 Interim Results"},
  {date:"2026-08-27",type:"results", name:"AIA Group",          note:"2026 Interim Results"},
];

/* ── Per-stock dynamic data (loaded on demand) ── */
let gMonthly = [];
let gEvents  = [];
let gVwap    = 0;
let gStockData = null;

/* ── Helpers ── */
const fmtB    = n => n >= 1e9 ? `${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `${(n/1e6).toFixed(0)}M` : n.toLocaleString();
const fmtHKD  = n => n >= 1e9 ? `HK$${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `HK$${(n/1e6).toFixed(0)}M` : `HK$${n.toLocaleString()}`;
const pLabel  = p => { const[y,m]=p.split('-'); return new Date(+y,+m-1,1).toLocaleString('en-GB',{month:'short',year:'2-digit'}); };
const fmtCode = c => `${parseInt(c,10)} HK`;
const csClamp = s => Math.min(Math.max(Math.round(s), 0), 5);
const csClass = s => `cs-${csClamp(s)}`;
const csStars = s => { const c = csClamp(s); return '★'.repeat(c) + '☆'.repeat(5-c); };

/* ── Init ── */
document.addEventListener('DOMContentLoaded', async () => {
  renderHeader('ca');

  // Set initial view: show only CA home, hide all others
  switchView('ca', document.querySelector('.vtog .vb'));

  // Load league index from ca_index.json
  try {
    const raw = await fetchCAIndex();
    if (raw && raw.length) {
      league = raw.map(mapIndexRow);
    }
  } catch (e) {
    console.warn('ca_index.json load failed, league empty', e);
  }

  renderLeague();
  renderLastSession();
  renderConvictionBuys();
  renderMandateRenewers();
  renderCalendar();
  wireSearch();

  // Route from URL param
  const code = new URLSearchParams(location.search).get('code');
  if (code) {
    const stock = league.find(r => r.c === code) || league[0];
    if (stock) goToStock(stock.c, stock.n);
  }

  document.getElementById('chatInput').addEventListener('keydown', e => { if (e.key === 'Enter') sendChat(); });
});

/* ── Search autocomplete ── */
function wireSearch() {
  const si = document.getElementById('searchInput');
  const dd = document.getElementById('searchDropdown');
  if (!si || !dd) return;

  let timer;
  si.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      const q = si.value.trim().toLowerCase();
      if (!q) { dd.style.display = 'none'; return; }
      const matches = league.filter(r =>
        r.n.toLowerCase().includes(q) ||
        r.c.includes(q) ||
        String(parseInt(r.c, 10)).includes(q)
      ).slice(0, 10);
      if (!matches.length) { dd.style.display = 'none'; return; }
      dd.innerHTML = matches.map(r => `
        <div class="dropdown-item" onmousedown="event.preventDefault();goToStock('${r.c}','${r.n.replace(/'/g,"\\'")}');document.getElementById('searchInput').value='${fmtCode(r.c)} — ${r.n.replace(/'/g,"\\'")}';document.getElementById('searchDropdown').style.display='none'">
          <span class="di-code">${fmtCode(r.c)}</span>
          <span class="di-name">${r.n}</span>
          <span class="di-code" style="margin-left:auto;color:${r.act?'var(--green)':'var(--tx3)'}">${r.act?'Active':'Inactive'}</span>
        </div>`).join('');
      dd.style.display = 'block';
    }, 120);
  });
  si.addEventListener('blur', () => setTimeout(() => { dd.style.display = 'none'; }, 200));
  si.addEventListener('focus', () => { if (si.value) si.dispatchEvent(new Event('input')); });
  si.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const q = si.value.trim().toLowerCase();
      const match = league.find(r => r.n.toLowerCase().includes(q) || String(parseInt(r.c,10)).includes(q));
      if (match) { goToStock(match.c, match.n); si.value = `${fmtCode(match.c)} — ${match.n}`; dd.style.display = 'none'; }
    }
  });
}

/* ── Tooltip wiring (JS, not CSS :hover — required for <summary> elements) ── */
function wireTooltip(btnId, popupId) {
  const btn = document.getElementById(btnId);
  const popup = document.getElementById(popupId);
  if (!btn || !popup) return;
  let open = false;
  const show = () => { popup.style.display = 'block'; open = true; };
  const hide = () => { popup.style.display = 'none'; open = false; };
  btn.addEventListener('mouseenter', show);
  btn.addEventListener('mouseleave', e => { if (!popup.matches(':hover')) hide(); });
  popup.addEventListener('mouseleave', hide);
  btn.addEventListener('focus', show);
  btn.addEventListener('blur', () => setTimeout(hide, 100));
  btn.addEventListener('click', e => { e.stopPropagation(); open ? hide() : show(); });
}

function wireVolTooltip() {
  const viW = document.getElementById('volInfoWrap');
  if (!viW) return;
  viW.style.cssText = 'position:relative;display:inline-flex;align-items:center;margin-left:3px;vertical-align:middle';
  viW.innerHTML = `<span tabindex="0" style="width:13px;height:13px;border-radius:50%;background:var(--sf);border:1px solid var(--bd2);color:var(--tx3);font-size:9px;font-weight:600;font-family:var(--mono);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;line-height:1">?</span><div style="display:none;position:absolute;bottom:calc(100% + 8px);right:-10px;width:230px;background:#1c2330;border:1px solid #384152;border-radius:7px;padding:11px 13px;z-index:300;font-size:11px;color:var(--tx2);line-height:1.6;box-shadow:0 6px 20px rgba(0,0,0,.5)"><strong style="display:block;color:var(--tx);margin-bottom:4px">% of monthly traded volume</strong>Shares repurchased ÷ total shares traded that month. Above ~5% = company was a meaningful price support factor.<span style="display:block;color:var(--tx3);margin-top:4px">Source: HKEX Securities Statistics / Yahoo Finance</span></div>`;
  const vBtn = viW.querySelector('span'), vTip = viW.querySelector('div');
  vBtn.addEventListener('mouseenter', () => vTip.style.display = 'block');
  vBtn.addEventListener('mouseleave', () => vTip.style.display = 'none');
  vBtn.addEventListener('focus', () => vTip.style.display = 'block');
  vBtn.addEventListener('blur', () => vTip.style.display = 'none');
}

/* ── Event pills ── */
function buildEventPills(events) {
  const el = document.getElementById('eventPills');
  if (!el) return;
  el.innerHTML = '';
  (events || []).forEach(ev => {
    const p = document.createElement('span');
    p.className = `ep ep-${ev.type}`;
    const marker = ev.type === 'placing' ? '▼' : '◆';
    const color  = ev.type === 'placing' ? '#f85149' : '#d29922';
    p.innerHTML = `<span style="font-size:13px">${marker}</span> ${pLabel(ev.period || ev.p)} — ${ev.label}: ${ev.detail}<a href="${ev.pdf_url || ev.pdfUrl || '#'}" target="_blank" class="ep-link" onclick="event.stopPropagation()">PDF ↗</a>`;
    el.appendChild(p);
  });
}

/* ── Chart ── */
let chartInstance = null;
function buildChart(monthly, events, ytdVwap) {
  monthly  = monthly  || gMonthly;
  events   = events   || gEvents;
  ytdVwap  = ytdVwap  || gVwap;

  const barColors = monthly.map(d => {
    if (!d.notional && d.notional !== 0) return 'rgba(88,166,255,0.08)';
    const cn = d.notional || d.cn || 0;
    const sh = d.shares   || d.sh || 0;
    if (cn === 0) return 'rgba(88,166,255,0.08)';
    return (cn/sh) < ytdVwap ? 'rgba(63,185,80,0.55)' : 'rgba(88,166,255,0.45)';
  });

  const blackoutPlugin = {id:'blackout',beforeDatasetsDraw(chart){const{ctx,chartArea,scales}=chart;const tw=scales.x.getPixelForTick(1)-scales.x.getPixelForTick(0);monthly.forEach((d,i)=>{if(!d.blackout)return;const x0=scales.x.getPixelForTick(i)-tw/2,x1=x0+tw;ctx.save();ctx.fillStyle='rgba(110,118,129,0.12)';ctx.fillRect(x0,chartArea.top,x1-x0,chartArea.bottom-chartArea.top);ctx.strokeStyle='rgba(110,118,129,0.22)';ctx.lineWidth=0.5;ctx.strokeRect(x0,chartArea.top,x1-x0,chartArea.bottom-chartArea.top);ctx.font='9px sans-serif';ctx.fillStyle='rgba(110,118,129,0.6)';ctx.textAlign='center';ctx.fillText('⛔',(x0+x1)/2,chartArea.top+12);ctx.restore();});}};

  const evPeriods = (events||[]).map(ev => ev.period||ev.p);
  const eventLinesPlugin = {id:'eventLines',afterDraw(chart){const{ctx,chartArea,scales}=chart;(events||[]).forEach(ev=>{const p=ev.period||ev.p;const idx=monthly.findIndex(d=>d.period===p||d.p===p);if(idx<0)return;const x=scales.x.getPixelForTick(idx);const color=ev.type==='placing'?'#f85149':'#d29922';const marker=ev.type==='placing'?'▼':'◆';ctx.save();ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.setLineDash([5,4]);ctx.globalAlpha=0.75;ctx.beginPath();ctx.moveTo(x,chartArea.top);ctx.lineTo(x,chartArea.bottom);ctx.stroke();ctx.globalAlpha=0.06;ctx.fillStyle=color;ctx.fillRect(x-10,chartArea.top,20,chartArea.bottom-chartArea.top);ctx.globalAlpha=1;ctx.setLineDash([]);ctx.font='bold 11px sans-serif';ctx.fillStyle=color;ctx.textAlign='center';ctx.fillText(marker,x,chartArea.top+14);ctx.restore();});}};

  const vwapLinePlugin = {id:'vwapLine',afterDraw(chart){if(!ytdVwap)return;const{ctx,chartArea,scales}=chart;const y=scales.yp.getPixelForValue(ytdVwap);if(y<chartArea.top||y>chartArea.bottom)return;ctx.save();ctx.strokeStyle='rgba(248,81,73,0.45)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(chartArea.left,y);ctx.lineTo(chartArea.right,y);ctx.stroke();ctx.fillStyle='rgba(248,81,73,0.65)';ctx.font='9px monospace';ctx.textAlign='left';ctx.fillText(`VWAP $${ytdVwap}`,chartArea.left+4,y-3);ctx.restore();}};

  if (chartInstance) chartInstance.destroy();

  const canvas = document.getElementById('mainChart');
  if (!canvas) return;

  chartInstance = new Chart(canvas.getContext('2d'), {
    data: {
      labels: monthly.map(d => pLabel(d.period||d.p)),
      datasets: [
        {type:'line',data:monthly.map(d=>d.month_close||d.price||0),yAxisID:'yp',borderColor:'#58a6ff',borderWidth:2,pointRadius:3,pointBackgroundColor:'#58a6ff',pointBorderColor:'#0d1117',pointBorderWidth:1.5,tension:0.3,fill:false,order:1},
        {type:'bar',data:monthly.map(d=>+((d.notional||d.cn||0)/1e9).toFixed(2)),yAxisID:'yb',backgroundColor:barColors,borderColor:barColors.map(c=>c.replace(/[\d.]+\)$/,'0.9)')),borderWidth:1,borderRadius:3,order:2}
      ]
    },
    options: {
      responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{backgroundColor:'#1c2330',borderColor:'#2a3140',borderWidth:1,titleColor:'#e6edf3',bodyColor:'#8b949e',padding:10,callbacks:{afterTitle(items){const idx=items[0]?.dataIndex;const p=(monthly[idx]?.period||monthly[idx]?.p);const ev=(events||[]).find(e=>(e.period||e.p)===p);return ev?[`⚡ ${ev.label}: ${ev.detail}`]:[];},label(c){if(c.datasetIndex===0)return`  Price: HK$${c.raw}`;return c.raw>0?`  Buyback: HK$${c.raw.toFixed(1)}B`:'  No repurchase';}}}},
      scales:{x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#6e7681',font:{size:11},maxRotation:0}},yp:{position:'left',grid:{color:'rgba(255,255,255,.06)'},ticks:{color:'#58a6ff',font:{size:11},callback:v=>`$${v}`},border:{display:false}},yb:{position:'right',grid:{drawOnChartArea:false},ticks:{color:'#3fb950',font:{size:11},callback:v=>`$${v}B`},border:{display:false}}}
    },
    plugins: [blackoutPlugin, eventLinesPlugin, vwapLinePlugin]
  });
}

/* ── Mandate stats ── */
function buildMandateStats(data) {
  const el = document.getElementById('mandateStats');
  if (!el) return;
  if (!data) { el.innerHTML = ''; return; }
  const pctIssued  = data.pct_issued       || data.pc  || 0;
  const mandatePct = data.mandate_pct      || 10;
  const ff         = data.free_float_pct   || data.ff  || 50;
  const cn         = data.cumulative_notional || data.cn || 0;
  const sh         = data.shares_issued    || 1;
  const available  = mandatePct - pctIssued;
  const shAvailable = sh * available / 100;
  const estValue   = shAvailable * (data.vwap_hkd || 0);
  const floatAdj   = (pctIssued / ff * 100).toFixed(2);
  const floatMand  = (mandatePct / ff * 100).toFixed(2);
  const authorityUsed = (pctIssued / mandatePct * 100).toFixed(1);

  el.innerHTML = `
    <div class="mc-group">
      <span class="mc-group-label">As % of issued share capital</span>
      <div class="mcs-item"><span class="mcs-label">Repurchased YTD</span><span class="mcs-value ok">${pctIssued.toFixed(2)}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">AGM mandate limit</span><span class="mcs-value dim">${mandatePct.toFixed(2)}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Still available</span><span class="mcs-value ok">${available.toFixed(2)}%<span class="mcs-unit">≈ ${fmtHKD(estValue)} · ${fmtB(shAvailable)} shares</span></span></div>
    </div>
    <div class="mc-vdivider"></div>
    <div class="mc-group">
      <span class="mc-group-label">Progress against mandate authority</span>
      <div class="mcs-item"><span class="mcs-label">Authority used</span><span class="mcs-value ok">${authorityUsed}%<span class="mcs-unit">of ${mandatePct}% limit (= ${pctIssued.toFixed(2)} ÷ ${mandatePct})</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Mandate expires</span><span class="mcs-value dim">Next AGM<span class="mcs-unit">approx. 2026</span></span></div>
    </div>
    <div class="mc-vdivider"></div>
    <div class="mc-group">
      <span class="mc-group-label">Free float adjustment</span>
      <div class="mcs-item"><span class="mcs-label">Free float</span><span class="mcs-value dim">~${ff}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Bought back (float-adj.)</span><span class="mcs-value ok">${floatAdj}%<span class="mcs-unit">of free float</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Mandate limit (float-adj.)</span><span class="mcs-value dim">${floatMand}%<span class="mcs-unit">of free float</span></span></div>
    </div>`;
}

function buildProbFactors(data) {
  const factors = [];
  if (!data) return;
  const cs  = data.consistency_score || data.cs || 0;
  const act = data.programme_active  || data.act || false;
  const underwater = (data.current_price_hkd||0) < (data.vwap_hkd||0);
  const mc  = data.mandate_consumed_pct || data.mc || 0;

  if (act)       factors.push({label:'Programme active this month',       score:25, color:'var(--green)'});
  if (cs >= 4)   factors.push({label:`Consistency score ${cs}/5`,         score:22, color:'var(--green)'});
  else if (cs>=3) factors.push({label:`Consistency score ${cs}/5`,        score:12, color:'var(--amber)'});
  if (underwater) factors.push({label:'Buying while underwater (vs VWAP)',score:20, color:'var(--amber)'});
  if (mc >= 10)   factors.push({label:'Mandate pace on track',            score:15, color:'var(--amber)'});

  const el = document.getElementById('probFactors');
  if (!el) return;
  el.innerHTML = '';
  factors.forEach(f => {
    const d = document.createElement('div');
    d.className = 'pf-item';
    d.innerHTML = `<span class="pf-dot" style="background:${f.color}"></span>${f.label} <span style="color:var(--tx2);font-family:var(--mono);margin-left:3px">(+${f.score})</span>`;
    el.appendChild(d);
  });
}

/* ── Metric cards ── */
function buildMetricCards(data) {
  const el = document.getElementById('metricCards');
  if (!el || !data) return;
  const cn      = data.cumulative_notional || 0;
  const sh      = data.shares_bought || 0;
  const pct     = data.pct_issued || 0;
  const ff      = data.free_float_pct || 50;
  const vwap    = data.vwap_hkd || 0;
  const curPx   = data.current_price_hkd || 0;
  const floatAdj = (pct / ff * 100).toFixed(2);
  const pctVwap  = vwap > 0 ? ((curPx/vwap-1)*100).toFixed(1) : '—';
  const isUnder  = curPx < vwap;

  // Estimate avg monthly from active months in data
  const activeMths = (data.monthly||[]).filter(m=>(m.notional||m.cn||0)>0).length || 1;
  const avgMonthly = cn / activeMths;
  const annualised = avgMonthly * 12;

  el.innerHTML = `
    <div class="mc2"><div class="ml">YTD Consideration</div><div class="mv" style="font-size:18px">${fmtHKD(cn)}</div><div class="ms2">${activeMths} active months</div></div>
    <div class="mc2"><div class="ml">Shares Bought YTD</div><div class="mv">${fmtB(sh)}</div><div class="ms2">${pct.toFixed(2)}% issued · ${floatAdj}% float</div></div>
    <div class="mc2">
      <div class="ml">YTD VWAP Paid</div>
      <div class="mv" style="font-size:18px">HK$${vwap}</div>
      <div class="ms2">vs current HK$${curPx}</div>
      ${isUnder ? `<div class="uw-flag">▼ Underwater ${pctVwap}% · still buying</div>` : `<div class="md up">↑ Above VWAP +${pctVwap}%</div>`}
    </div>
    <div class="mc2"><div class="ml">Avg Monthly Spend</div><div class="mv" style="font-size:18px">${fmtHKD(avgMonthly)}</div><div class="ms2">Annualised est. ${fmtHKD(annualised)}</div></div>`;
}

/* ── Insight box ── */
function buildInsightBox(data) {
  const el = document.getElementById('insightBox');
  if (!el || !data) return;
  const name = data.name || '';
  const pct  = data.pct_issued || 0;
  const ff   = data.free_float_pct || 50;
  const vwap = data.vwap_hkd || 0;
  const curPx= data.current_price_hkd || 0;
  const bbYld= data.buyback_yield_pct || 0;
  const isUnder = curPx < vwap;
  const floatAdj = (pct / ff * 100).toFixed(2);
  const code = data.code || '';

  el.innerHTML = `
    <div class="ib-head"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1a5 5 0 0 1 2 9.5V12H6v-1.5A5 5 0 0 1 8 1z"/><path d="M6 13h4M7 15h2" stroke-linecap="round"/></svg>Capital return summary &amp; DI context</div>
    <div class="ib-points">
      ${isUnder ? `<div class="ib-point"><div class="ib-icon bear">▼</div><span class="ib-text"><strong>Buying underwater:</strong> YTD VWAP paid HK$${vwap} vs current HK$${curPx} (${((curPx/vwap-1)*100).toFixed(1)}%). Still actively buying — signalling conviction at current levels.</span></div>` : `<div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Buying above VWAP:</strong> Current price HK$${curPx} is above the YTD average cost HK$${vwap}. Programme still active.</span></div>`}
      <div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Float impact is material:</strong> ${pct.toFixed(2)}% of issued capital = <strong>${floatAdj}% of freely traded shares</strong> absorbed YTD.</span></div>
      <div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Buyback yield ${bbYld.toFixed(1)}%</strong> at current price. Higher yields suggest management sees shares as undervalued.</span></div>
      <div class="ib-point" style="padding-top:8px;margin-top:4px;border-top:1px solid var(--bd)">
        <div class="ib-icon di">DI</div>
        <span class="ib-text"><strong>Disclosure of Interests context:</strong> ${name} has repurchased <strong>${pct.toFixed(2)}% of issued capital</strong> YTD. Cross-reference with DI filings for institutional accumulation signals. <a href="../di/?code=${code}">View DI filings →</a></span>
      </div>
    </div>`;
}

/* ── Monthly table ── */
function buildMonthlyTable(monthly, events, avgVwap) {
  monthly  = monthly  || gMonthly;
  events   = events   || gEvents;
  avgVwap  = avgVwap  || gVwap;

  const maxCn = Math.max(...monthly.map(d => d.notional||d.cn||0));
  const mtb = document.getElementById('mtbody');
  if (!mtb) return;
  mtb.innerHTML = '';
  [...monthly].reverse().forEach(row => {
    const cn = row.notional || row.cn || 0;
    const sh = row.shares   || row.sh || 0;
    const px = row.month_close || row.price || 0;
    const mv = row.month_volume || row.mv || 0;
    const pct = maxCn > 0 ? (cn/maxCn)*70 : 0;
    const vw = sh > 0 ? cn/sh : 0;
    const vs = vw > 0 ? ((vw/avgVwap-1)*100) : null;
    const vsClass = vs === null ? '' : (vs < 0 ? 'style="color:var(--green)"' : 'style="color:var(--red)"');
    const vsTxt = vs === null ? '—' : `${vs>=0?'+':''}${vs.toFixed(1)}%`;
    const period = row.period || row.p;
    const ev = (events||[]).find(e => (e.period||e.p) === period);
    const volPct = (sh > 0 && mv > 0) ? (sh/mv*100) : null;
    const volC = volPct === null ? '' : (volPct >= 5 ? 'color:var(--amber)' : volPct >= 3 ? 'color:var(--tx)' : 'color:var(--tx2)');
    const volTxt = volPct === null ? '<span style="color:var(--tx3)">—</span>' : `<span style="${volC}">${volPct.toFixed(1)}%</span>`;
    const boStyle = row.blackout ? 'background:rgba(110,118,129,.07);' : '';
    const boTag = row.blackout ? '<span style="font-size:9px;color:var(--tx3);margin-left:4px">⛔</span>' : '';
    const evColor = ev ? (ev.type==='placing'?'#f85149':'#d29922') : '';
    const evMarker = ev ? (ev.type==='placing'?'▼':'◆') : '';
    const tr = document.createElement('tr');
    tr.style.cssText = boStyle;
    tr.innerHTML = `<td class="bold">${pLabel(period)}${boTag}${ev?` <span style="font-size:10px;color:${evColor}">${evMarker}</span>`:''}</td>
      <td class="num">${row.trading_days||row.d||'—'}</td><td class="num">${sh>0?fmtB(sh):'—'}</td>
      <td class="num">${sh>0?`<span style="font-family:var(--mono);font-size:12px"><span class="hi">H ${(row.hi||0).toFixed(1)}</span>  <span class="lo">L ${(row.lo||0).toFixed(1)}</span></span>`:'—'}</td>
      <td class="num"><div class="bc">${cn>0?`<div class="ib2 ${pct>40?'hi2':''}" style="width:${pct}px"></div>`:''} ${cn>0?fmtHKD(cn):`<span style="color:var(--tx3)">${row.blackout?'Blackout period':'No repurchase'}</span>`}</div></td>
      <td class="num" style="color:var(--tx)">${(row.cum_pct||row.cum||0).toFixed(2)}%</td>
      <td class="num">${volTxt}</td>
      <td class="num" ${vsClass}>${vsTxt}</td>
      <td>${cn>0?`<a class="fl" href="https://www1.hkexnews.hk/search/titlesearch.xhtml" target="_blank">PDF <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 10L10 2M5 2h5v5" stroke-linecap="round" stroke-linejoin="round"/></svg></a>`:'<span style="color:var(--tx3);font-size:11px">—</span>'}</td>`;
    mtb.appendChild(tr);
  });
}

/* ── Last Session ── */
let lastSessionSort = 'cn';
function renderLastSession() {
  const tb = document.getElementById('la-tbody');
  if (!tb) return;
  tb.innerHTML = '';
  let rows = league.filter(r => r.ld).map(r => ({...r, vp: r.ld.sh/r.ld.dv*100}));
  if (lastSessionSort === 'cn') rows.sort((a,b) => b.ld.cn - a.ld.cn);
  if (lastSessionSort === 'sh') rows.sort((a,b) => b.ld.sh - a.ld.sh);
  if (lastSessionSort === 'vp') rows.sort((a,b) => b.vp - a.vp);
  rows.forEach(r => {
    const d = r.ld, vp = r.vp, vc = vp >= 5 ? 'color:var(--amber)' : vp >= 3 ? 'color:var(--tx)' : 'color:var(--tx2)';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0" role="button"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--tx2)">${d.date}</td>
      <td class="num">${fmtB(d.sh)}</td><td class="num"><span style="${vc}">${vp.toFixed(1)}%</span></td>
      <td class="num"><span style="font-family:var(--mono);font-size:12px"><span class="hi">H ${d.hi.toFixed(2)}</span>  <span class="lo">L ${d.lo.toFixed(2)}</span></span></td>
      <td class="num">${fmtHKD(d.cn)}</td>
      <td><a class="fl" href="https://www1.hkexnews.hk/search/titlesearch.xhtml" target="_blank">PDF <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 10L10 2M5 2h5v5" stroke-linecap="round" stroke-linejoin="round"/></svg></a></td>`;
    tb.appendChild(tr);
  });
}
function sortLastSession(by, btn) {
  lastSessionSort = by;
  document.querySelectorAll('#lastsessionv .sort-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  renderLastSession();
}

/* ── League Table ── */
let leagueFilter = 'all', leagueSort = 'ytd';
const leagueTitleMap = {ytd:'YTD repurchase — ranked by consideration',pct:'YTD repurchase — ranked by % issued capital',mandate:'YTD repurchase — ranked by mandate consumed',date:'YTD repurchase — ranked by last filing date'};
const leagueActiveCol = {ytd:'lh-consideration',pct:'lh-pct',mandate:'lh-mandate',date:'lh-date'};
function renderLeague() {
  const tb = document.getElementById('ltbody');
  if (!tb) return;
  if (!league.length) { tb.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--tx3);padding:20px">Loading…</td></tr>'; return; }
  tb.innerHTML = '';
  let data = [...league];
  if (leagueFilter === 'active') data = data.filter(d => d.act);
  if (leagueFilter === 'big') data = data.filter(d => d.cn >= 5e9);
  if (leagueSort === 'ytd') data.sort((a,b) => b.cn - a.cn);
  if (leagueSort === 'pct') data.sort((a,b) => b.pc - a.pc);
  if (leagueSort === 'mandate') data.sort((a,b) => b.mc - a.mc);
  if (leagueSort === 'date') data.sort((a,b) => b.lf.localeCompare(a.lf));
  const titleEl = document.getElementById('leagueTitle');
  if (titleEl) titleEl.textContent = leagueTitleMap[leagueSort];
  ['lh-consideration','lh-pct','lh-mandate','lh-date'].forEach(id => {
    const el = document.getElementById(id); if (el) el.style.color = '';
  });
  const activeH = document.getElementById(leagueActiveCol[leagueSort]);
  if (activeH) activeH.style.color = 'var(--accent)';
  const maxC = (league[0] || {cn: 1}).cn || 1;
  data.forEach((r, i) => {
    const bw = Math.round(r.cn/maxC*80);
    const tr = document.createElement('tr');
    tr.innerHTML = `<td style="font-size:11px;font-family:var(--mono);color:var(--tx3)">${i+1}</td>
      <td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0" role="button"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td class="num"><div class="prow"><div class="pbar" style="width:${bw}px"></div>${fmtHKD(r.cn)}</div></td>
      <td class="num" style="font-family:var(--mono);font-size:12.5px">${fmtB(r.sh)}</td>
      <td class="num" style="font-family:var(--mono);font-size:12.5px">${r.pc.toFixed(2)}%</td>
      <td class="num" style="font-family:var(--mono);font-size:12.5px;color:${r.mc>30?'var(--amber)':'var(--tx2)'}">${r.mc.toFixed(1)}%</td>
      <td><span class="${r.act?'bl':'bi'}">${r.act?'Active':'Completed'}</span></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--tx3)">${r.lf}</td>`;
    tb.appendChild(tr);
  });
}
function sortLeague(by, btn) { leagueSort = by; document.querySelectorAll('#lv .sort-btn').forEach(b => b.classList.remove('on')); btn.classList.add('on'); renderLeague(); }
function filterL(f, el) { leagueFilter = f; document.querySelectorAll('.chips .chip').forEach(c => c.classList.remove('on')); el.classList.add('on'); renderLeague(); }

/* ── Ideas ── */
function renderConvictionBuys() {
  const tb = document.getElementById('cb-tbody');
  if (!tb) return;
  tb.innerHTML = '';
  const rows = league.filter(r => r.act && r.curPx < r.vwap && r.cs >= 4).sort((a,b) => (a.curPx/a.vwap) - (b.curPx/b.vwap));
  rows.forEach(r => {
    const disc = ((r.curPx/r.vwap-1)*100);
    const diActive = r.c === '00700' || r.c === '09988';
    const diHtml = diActive ? `<a href="../di/?code=${r.c}" class="di-flag">⬆ Latest DI →</a>` : `<span style="color:var(--tx3);font-size:12px">No DI signal</span>`;
    const sigScore = diActive ? (r.cs >= 4 ? 'strong' : 'med') : (r.cs >= 4 ? 'med' : 'weak');
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0" role="button"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td><span class="cs-badge ${csClass(r.cs)}" style="font-size:10px;padding:2px 7px">${csStars(r.cs)} ${r.cs}</span></td>
      <td class="num" style="color:var(--red)">HK$${r.curPx}</td><td class="num">HK$${r.vwap}</td>
      <td class="num" style="color:var(--red)">${disc.toFixed(1)}%</td>
      <td class="num" style="color:var(--green)">${r.bbYld.toFixed(1)}%</td>
      <td>${diHtml}</td>
      <td><span class="signal-dot sig-${sigScore}"></span><span style="font-size:12px;font-weight:500;color:${sigScore==='strong'?'var(--green)':'var(--amber)'}">${sigScore==='strong'?'Strong':'Moderate'}</span></td>`;
    tb.appendChild(tr);
  });
  if (!rows.length) { const tr = document.createElement('tr'); tr.innerHTML = `<td colspan="8" style="text-align:center;color:var(--tx3);padding:24px;font-size:13px">No stocks currently match all criteria</td>`; tb.appendChild(tr); }
}
function renderMandateRenewers() {
  const tb = document.getElementById('mr-tbody');
  if (!tb) return;
  tb.innerHTML = '';
  league.filter(r => r.renewProb >= 65 && r.cs >= 3 && r.mc >= 5).sort((a,b) => b.renewProb - a.renewProb).forEach(r => {
    const floatAdj = (r.pc/r.ff*100).toFixed(2);
    const oc = r.renewProb >= 80 ? 'var(--green)' : r.renewProb >= 70 ? 'var(--amber)' : 'var(--tx2)';
    const ol = r.renewProb >= 80 ? 'Strong' : r.renewProb >= 70 ? 'Moderate' : 'Watch';
    const pf = r.renewProb >= 80 ? 'linear-gradient(90deg,#3fb950,#58a6ff)' : r.renewProb >= 70 ? 'linear-gradient(90deg,#d29922,#e09c00)' : 'rgba(88,166,255,.5)';
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0" role="button"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td><span class="cs-badge ${csClass(r.cs)}" style="font-size:10px;padding:2px 7px">${csStars(r.cs)} ${r.cs}</span></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--tx2)">${r.agm}</td>
      <td class="num">${r.mc.toFixed(1)}%<span style="font-size:10px;color:var(--tx3);font-family:var(--sans)"> of mandate</span></td>
      <td class="num"><div style="display:flex;align-items:center;gap:6px;justify-content:flex-end"><div style="height:5px;width:50px;background:var(--bd);border-radius:3px;overflow:hidden"><div style="height:100%;width:${r.renewProb}%;background:${pf};border-radius:3px"></div></div><span style="font-family:var(--mono);font-size:12px;color:${oc}">${r.renewProb}%</span></div></td>
      <td class="num" style="color:var(--green)">${r.bbYld.toFixed(1)}%</td>
      <td class="num" style="color:var(--amber)">${floatAdj}%<span style="font-size:10px;color:var(--tx3);font-family:var(--sans)"> of float</span></td>
      <td><span style="font-size:11px;font-weight:500;color:${oc}">${ol}</span></td>`;
    tb.appendChild(tr);
  });
}
function switchIdeasTab(tab, btn) {
  document.querySelectorAll('.ist-btn').forEach(b => b.classList.remove('on')); btn.classList.add('on');
  document.querySelectorAll('.strat-pane').forEach(p => p.classList.remove('on'));
  document.getElementById(tab + '-pane').classList.add('on');
}

/* ── Calendar ── */
const _now = new Date();
let calYear = _now.getFullYear(), calMonth = _now.getMonth();
function renderCalendar() {
  const title = new Date(calYear, calMonth, 1).toLocaleString('en-GB', {month:'long',year:'numeric'});
  const titleEl = document.getElementById('calTitle');
  if (titleEl) titleEl.textContent = title;
  const body = document.getElementById('calBody');
  if (!body) return;
  body.innerHTML = '';
  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const offset = firstDay === 0 ? 6 : firstDay - 1;
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  for (let i = 0; i < offset; i++) { const cell = document.createElement('div'); cell.className = 'cal-cell empty'; body.appendChild(cell); }
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const dayEvents = calEvents.filter(e => e.date === dateStr);
    const today = new Date();
    const isToday = today.getFullYear() === calYear && today.getMonth() === calMonth && today.getDate() === d;
    const cell = document.createElement('div');
    cell.className = 'cal-cell' + (isToday ? ' today' : '');
    cell.innerHTML = `<div class="cal-day">${d}</div><div class="cal-events">${dayEvents.slice(0,3).map(e=>`<div class="cal-event ${e.type}"><span>●</span>${e.name.split(' ')[0]}</div>`).join('')}${dayEvents.length>3?`<div style="font-size:9px;color:var(--tx3);padding:1px 4px">+${dayEvents.length-3} more</div>`:''}</div>`;
    cell.addEventListener('click', () => showCalDay(dateStr, dayEvents));
    body.appendChild(cell);
  }
}
function showCalDay(dateStr, dayEvents) {
  const detail = document.getElementById('calDetail');
  if (!detail) return;
  const fmt = new Date(dateStr+'T00:00:00').toLocaleDateString('en-GB',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  const dateEl = document.getElementById('cdDate');
  if (dateEl) dateEl.textContent = fmt;
  const list = document.getElementById('cdList');
  if (!list) return;
  if (dayEvents.length === 0) { list.innerHTML = '<div style="color:var(--tx3);font-size:13px">No corporate events on this date</div>'; detail.style.display = 'block'; return; }
  list.innerHTML = dayEvents.map(e => `<div class="cd-item"><span class="cd-badge ${e.type}">${e.type==='agm'?'AGM':e.type==='results'?'Results':'Blackout'}</span><div><div class="cd-name">${e.name}</div><div class="cd-note">${e.note}</div></div></div>`).join('');
  detail.style.display = 'block';
}
function calNav(dir) {
  calMonth += dir;
  if (calMonth > 11) { calMonth = 0; calYear++; }
  if (calMonth < 0) { calMonth = 11; calYear--; }
  renderCalendar();
  const d = document.getElementById('calDetail');
  if (d) d.style.display = 'none';
}

/* ── View switcher ── */
const viewIds = {ca:'cav',stock:'sv',league:'lv',lastsession:'lastsessionv',ideas:'ideasv',calendar:'calendarv'};
function switchView(v, btn) {
  document.querySelectorAll('.vb').forEach(b => b.classList.remove('on'));
  if (btn) btn.classList.add('on');
  Object.keys(viewIds).forEach(k => {
    const el = document.getElementById(viewIds[k]);
    if (el) el.style.display = k === v ? 'block' : 'none';
  });
  if (v === 'stock') {
    setTimeout(() => { if (chartInstance) chartInstance.resize(); }, 50);
  }
}

/* ── Go to stock ── */
async function goToStock(code, name) {
  const si = document.getElementById('searchInput');
  if (si) si.value = `${fmtCode(code)} — ${name}`;

  switchView('stock', null);
  window.scrollTo({top: 0, behavior: 'smooth'});

  const hero = document.querySelector('.stock-hero');
  if (hero) {
    hero.style.transition = 'box-shadow .4s ease';
    hero.style.boxShadow = '0 0 0 2px rgba(88,166,255,.4)';
    setTimeout(() => { hero.style.boxShadow = ''; }, 800);
  }

  // Immediate update from league data
  const stock = league.find(r => r.c === code);
  if (stock) updateHeroForStock(stock);

  // Wire cross-links
  const diLink = document.getElementById('diCrossLink');
  const diHref = document.getElementById('diCrossLinkHref');
  if (diLink && diHref) {
    diLink.style.display = 'flex';
    diHref.href = `../di/?code=${code}`;
  }
  const cs = document.getElementById('compoundSignal');
  if (cs && stock && stock.cs >= 4 && stock.curPx < stock.vwap) {
    cs.style.display = 'flex';
    const ct = document.getElementById('compoundText');
    const cl = document.getElementById('compoundLink');
    if (ct) ct.textContent = `${name} — active programme buying below 12m VWAP. Check DI for simultaneous accumulation.`;
    if (cl) cl.href = `../di/?code=${code}`;
  } else if (cs) { cs.style.display = 'none'; }

  // Show loading state in chart/table area
  showStockLoading();

  // Fetch per-stock data
  const data = await fetchCA(code);
  if (data) {
    gMonthly   = data.monthly || [];
    gEvents    = data.events  || [];
    gVwap      = data.vwap_hkd || 0;
    gStockData = data;
    rebuildStockView(data);
  } else {
    showStockNoData(name);
  }
}

function showStockLoading() {
  const mtb = document.getElementById('mtbody');
  if (mtb) mtb.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:24px">Loading filing data…</td></tr>`;
  const mc = document.getElementById('metricCards');
  if (mc) mc.innerHTML = '';
  const ib = document.getElementById('insightBox');
  if (ib) ib.innerHTML = '';
  const ep = document.getElementById('eventPills');
  if (ep) ep.innerHTML = '';
}

function showStockNoData(name) {
  const mtb = document.getElementById('mtbody');
  if (mtb) mtb.innerHTML = `<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:24px">Detailed monthly filing data for ${name} is being compiled. Check back soon.</td></tr>`;
}

function rebuildStockView(data) {
  buildEventPills(data.events || []);
  buildChart(data.monthly || [], data.events || [], data.vwap_hkd);
  buildMonthlyTable(data.monthly || [], data.events || [], data.vwap_hkd);
  buildMandateStats(data);
  buildMetricCards(data);
  buildInsightBox(data);
  buildProbFactors(data);
  wireTooltip('mandateInfoBtn', 'mandateInfoPopup');
  wireTooltip('probInfoBtn', 'probInfoPopup');
  wireVolTooltip();
}

function updateHeroForStock(r) {
  const nameEl = document.getElementById('heroName');
  const codeEl = document.getElementById('heroCode');
  if (nameEl) nameEl.textContent = r.n || r.name;
  if (codeEl) codeEl.textContent = fmtCode(r.c || r.code);

  const csB = document.getElementById('csBadge');
  const csVal = r.cs || r.consistency_score || 0;
  if (csB) { csB.className = `cs-badge ${csClass(csVal)}`; csB.textContent = `${csStars(csVal)} ${csVal}`; }

  const sigB = document.getElementById('sigBadge');
  if (sigB) {
    const curPx = r.curPx || r.current_price_hkd || 0;
    const vwap  = r.vwap  || r.vwap_hkd || 0;
    const isStrong = curPx < vwap;
    sigB.className = isStrong ? 'sig-hero-strong' : 'sig-hero-moderate';
    sigB.textContent = isStrong ? '● Strong signal' : '● Moderate signal';
  }

  const uw = document.getElementById('uwBadge');
  if (uw) {
    const curPx = r.curPx || r.current_price_hkd || 0;
    const vwap  = r.vwap  || r.vwap_hkd || 0;
    if (curPx < vwap) {
      const diff = ((curPx/vwap-1)*100).toFixed(1);
      uw.style.display = 'inline-flex';
      uw.textContent = `▼ VWAP underwater ${diff}%`;
    } else { uw.style.display = 'none'; }
  }

  const mc = r.mc || r.mandate_consumed_pct || 0;
  const mBar = document.getElementById('mandateBarHero');
  if (mBar) mBar.style.width = mc + '%';
  const mBarE = document.getElementById('mandateBarExpanded');
  if (mBarE) mBarE.style.width = mc + '%';

  const mStat = document.getElementById('mandateStatHero');
  if (mStat) mStat.innerHTML = `<span class="ok">${mc.toFixed(1)}%</span> of mandate used · <span class="ok">${(100-mc).toFixed(1)}%</span> remaining · <span class="dim">expires 2026 AGM</span>`;

  const econ = document.getElementById('econStrip');
  if (econ) {
    const pct = r.pc || r.pct_issued || 0;
    const ff  = r.ff || r.free_float_pct || 50;
    const bbYld = r.bbYld || r.buyback_yield_pct || 0;
    const floatAdj = (pct / ff * 100).toFixed(2);
    econ.innerHTML = `
      <div class="es-item"><span class="es-label">Buyback yield</span><span class="es-val pos">${bbYld.toFixed(1)}%</span></div>
      <div class="es-sep"></div>
      <div class="es-item"><span class="es-label">Free float</span><span class="es-val neu">${ff}%</span></div>
      <div class="es-sep"></div>
      <div class="es-item"><span class="es-label">Float-adj. repurchased</span><span class="es-val pos">${floatAdj}%</span></div>
      <div class="es-sep"></div>
      <div class="es-item"><span class="es-label">Mandate used</span><span class="es-val neu">${mc.toFixed(1)}%</span></div>`;
  }

  const renewProb = r.renewProb || r.renew_probability || 0;
  const agm = r.agm || r.agm_date || '';
  const probPct = document.getElementById('probPct');
  const probBar = document.getElementById('probBar');
  const probLabel = document.getElementById('probLabel');
  if (probPct) { probPct.textContent = renewProb + '%'; probPct.style.color = 'var(--purple)'; }
  if (probBar) probBar.style.width = renewProb + '%';
  if (probLabel) probLabel.textContent = `Probability of mandate renewal at ${agm ? new Date(agm+'T00:00:00').getFullYear()+1 : '2026'} AGM`;
}

/* ── Chatbot ── */
const chatNavMap = {
  'conviction buys': {view:'ideas', subtab:'cb', label:'Open Conviction Buys →'},
  'conviction':      {view:'ideas', subtab:'cb', label:'Open Conviction Buys →'},
  'mandate renewer': {view:'ideas', subtab:'mr', label:'Open Mandate Renewers →'},
  'mandate':         {view:'ideas', subtab:'mr', label:'Open Mandate Renewers →'},
  'agm':             {view:'calendar',            label:'Open Calendar →'},
  'calendar':        {view:'calendar',            label:'Open Calendar →'},
  'results date':    {view:'calendar',            label:'Open Calendar →'},
  'last session':    {view:'lastsession',         label:'Open Last Session →'},
  'league':          {view:'league',              label:'Open League Table →'},
  'tencent':         {view:'stock',  stock:'00700', label:'View Tencent →'},
  'hsbc':            {view:'stock',  stock:'00005', label:'View HSBC →'},
  'alibaba':         {view:'stock',  stock:'09988', label:'View Alibaba →'},
  'vwap':            {view:'ideas', subtab:'cb', label:'Open Conviction Buys →'},
  'underwater':      {view:'ideas', subtab:'cb', label:'Open Conviction Buys →'},
};

async function sendChat() {
  const input = document.getElementById('chatInput');
  const q = input.value.trim();
  if (!q) return;
  const resp = document.getElementById('chatResponse');
  const loading = document.getElementById('chatLoading');
  const textEl = document.getElementById('chatText');
  const jumpBtn = document.getElementById('chatJump');
  resp.classList.add('visible');
  loading.classList.add('visible');
  textEl.textContent = '';
  jumpBtn.style.display = 'none';

  const convictionStocks = league.filter(r => r.act && r.curPx < r.vwap && r.cs >= 4).map(s => s.n);
  const renewerStocks = league.filter(r => r.renewProb >= 65 && r.cs >= 3 && r.mc >= 5).map(s => `${s.n} (AGM ${s.agm})`);

  // Chatbot vtob indices after removing "By Stock": ca=0, league=1, lastsession=2, ideas=3, calendar=4
  const vbIndex = {ca:0, league:1, lastsession:2, ideas:3, calendar:4};

  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {'Content-Type':'application/json','anthropic-version':'2023-06-01','x-api-key':''},
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514', max_tokens: 300,
        messages: [{role:'user',content:`You are a navigation assistant for Circular, an HKEX Corporate Actions tracker. Views: ca (Corporate Actions home), league (League Table), lastsession (Last Session Buyback), ideas/cb (Conviction Buys), ideas/mr (Mandate Renewers), calendar (AGM/results dates), stock (By Stock — load specific stock). Key stocks: Tencent (00700), HSBC (00005), HKEX (00388), Alibaba (09988). Conviction Buys: ${convictionStocks.join(', ')}. Mandate Renewers: ${renewerStocks.join(', ')}. User: "${q}". Reply ONLY as JSON: { answer: "1-2 sentences", view: "ca|league|lastsession|ideas|calendar|stock", subtab: "cb|mr|null", jump_label: "short text", stock_code: "00700|null" }. No markdown.`}]
      })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error.message);
    const parsed = JSON.parse(data.content[0].text.replace(/```json|```/g,'').trim());
    loading.classList.remove('visible');
    textEl.textContent = parsed.answer;
    jumpBtn.textContent = parsed.jump_label || 'Go →';
    jumpBtn.style.display = 'inline-flex';
    jumpBtn.onclick = () => {
      if (parsed.view === 'stock' && parsed.stock_code) {
        const s = league.find(r => r.c === parsed.stock_code);
        if (s) goToStock(s.c, s.n);
      } else {
        const idx = vbIndex[parsed.view];
        const btn = idx !== undefined ? document.querySelectorAll('.vtog .vb')[idx] : null;
        switchView(parsed.view, btn);
        if (parsed.view === 'ideas' && parsed.subtab) { const ib = document.querySelectorAll('.ist-btn')[parsed.subtab==='cb'?0:1]; switchIdeasTab(parsed.subtab, ib); }
      }
      window.scrollTo({top:0,behavior:'smooth'});
    };
  } catch (e) {
    loading.classList.remove('visible');
    const ql = q.toLowerCase();
    let matched = null;
    for (const k of Object.keys(chatNavMap)) { if (ql.includes(k)) { matched = chatNavMap[k]; break; } }
    textEl.textContent = matched ? `Navigating you to the most relevant section for "${q}".` : `Try asking about specific stocks, the league table, upcoming AGMs, or which stocks are buying back below their VWAP.`;
    if (matched) {
      jumpBtn.textContent = matched.label; jumpBtn.style.display = 'inline-flex';
      jumpBtn.onclick = () => {
        if (matched.view === 'stock' && matched.stock) {
          const s = league.find(r => r.c === matched.stock);
          if (s) goToStock(s.c, s.n);
        } else {
          const idx = vbIndex[matched.view];
          const btn = idx !== undefined ? document.querySelectorAll('.vtog .vb')[idx] : null;
          switchView(matched.view, btn);
          if (matched.subtab) { const ib = document.querySelectorAll('.ist-btn')[matched.subtab==='cb'?0:1]; switchIdeasTab(matched.subtab, ib); }
        }
        window.scrollTo({top:0,behavior:'smooth'});
      };
    } else { jumpBtn.style.display = 'none'; }
  }
  input.value = '';
}
