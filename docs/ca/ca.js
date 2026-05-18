'use strict';

const BASE = window.CIRC_BASE || '../data';

/* ── Helpers ── */
const fmtB   = n => n>=1e9?`${(n/1e9).toFixed(1)}B`:n>=1e6?`${(n/1e6).toFixed(0)}M`:n.toLocaleString();
const fmtHKD = n => n>=1e9?`HK$${(n/1e9).toFixed(1)}B`:n>=1e6?`HK$${(n/1e6).toFixed(0)}M`:`HK$${n.toLocaleString()}`;
const pLabel = p => { const[y,m]=p.split('-'); return new Date(+y,+m-1,1).toLocaleString('en-GB',{month:'short',year:'2-digit'}); };
const fmtCode= c => `${parseInt(c,10)} HK`;

const csClamp= s => Math.min(Math.max(Math.round(s),0),5);
const csClass= s => `cs-${csClamp(s)}`;
const csStars= s => { const c=csClamp(s); return '★'.repeat(c)+'☆'.repeat(5-c); };

/* ── Cache ── */
const _cache = {};
async function fetchJSON(key, url) {
  if (_cache[key]) return _cache[key];
  try { const r=await fetch(url); if(!r.ok) return null; _cache[key]=await r.json(); return _cache[key]; }
  catch { return null; }
}

/* ── Map ca_index row → internal format ── */
function mapRow(r) {
  const ls = r.last_session;
  return {
    c: r.code, n: r.name,
    cn: r.cumulative_notional || 0,
    sh: r.shares_bought || 0,
    pc: r.pct_issued || 0,
    mc: r.mandate_consumed_pct || 0,
    act: r.programme_active || false,
    lf: r.last_filing_date || '',
    ff: r.free_float_pct || 35,
    cs: r.consistency_score || 0,
    vwap: r.vwap_hkd || 0,
    curPx: r.current_price_hkd || 0,
    bbYld: r.pct_issued || 0,
    agm: r.agm_date || '',
    renewProb: r.renew_probability || 0,
    ld: ls ? {
      date: ls.date,
      sh: ls.shares || 0,
      hi: ls.avg_price_hkd || 0,
      lo: ls.avg_price_hkd || 0,
      cn: Math.round((ls.shares||0)*(ls.avg_price_hkd||0)),
    } : null,
  };
}

/* ── Map per-stock monthly array ── */
function mapMonthly(stockData) {
  return (stockData.monthly || []).map(m => ({
    p:  m.period,
    sh: m.shares || 0,
    lo: m.lo || m.month_close || 0,
    hi: m.hi || m.month_close || 0,
    cn: m.notional || 0,
    cum: m.cum_pct || 0,
    d:  m.trading_days || 0,
    price: m.month_close || 0,
    mv: m.month_volume || 0,
    blackout: m.blackout || false,
    filing_date: m.filing_date || null,
  }));
}

/* ── State ── */
let league = [];
let gMonthly = [], gEvents = [], gVwap = 0, gStockData = null;

/* ── Calendar events (real 2026 schedule) ── */
const calEvents = [
  {date:"2026-05-20",type:"agm",     name:"Tencent Holdings",  note:"2026 Annual General Meeting"},
  {date:"2026-05-21",type:"agm",     name:"China Mobile",      note:"2026 Annual General Meeting"},
  {date:"2026-05-26",type:"agm",     name:"Sunny Optical",     note:"2026 Annual General Meeting"},
  {date:"2026-05-27",type:"agm",     name:"Meituan",           note:"2026 Annual General Meeting"},
  {date:"2026-06-03",type:"agm",     name:"Ping An Insurance", note:"2026 Annual General Meeting"},
  {date:"2026-06-10",type:"agm",     name:"China Const. Bank", note:"2026 Annual General Meeting"},
  {date:"2026-06-12",type:"agm",     name:"Haidilao",          note:"2026 Annual General Meeting"},
  {date:"2026-06-17",type:"agm",     name:"ICBC",              note:"2026 Annual General Meeting"},
  {date:"2026-06-19",type:"agm",     name:"Budweiser APAC",    note:"2026 Annual General Meeting"},
  {date:"2026-07-15",type:"blackout",name:"Tencent Holdings",  note:"Estimated blackout start (30d before interim results)"},
  {date:"2026-07-29",type:"results", name:"HSBC Holdings",     note:"2026 Interim Results"},
  {date:"2026-08-12",type:"results", name:"Tencent Holdings",  note:"2026 Interim Results"},
  {date:"2026-08-27",type:"results", name:"AIA Group",         note:"2026 Interim Results"},
];

/* ── Init ── */
document.addEventListener('DOMContentLoaded', async () => {
  renderHeader('ca');
  switchView('home', document.querySelector('.vtog .vb'));

  const raw = await fetchJSON('idx', `${BASE}/ca_index.json`);
  if (raw && raw.length) {
    league = raw.map(mapRow);
    const active = league.filter(r=>r.act).length;
    const conviction = league.filter(r=>r.act && r.curPx>0 && r.vwap>0 && r.curPx<r.vwap && r.cs>=2).length;
    const totalCN = league.reduce((s,r)=>s+r.cn,0);
    document.getElementById('hs-active').textContent = active;
    document.getElementById('hs-total').textContent = league.length;
    document.getElementById('hs-conviction').textContent = conviction;
    document.getElementById('hs-notional').textContent = fmtHKD(totalCN);
  }

  renderLeague();
  renderLastSession();
  renderConvictionBuys();
  renderMandateRenewers();
  renderCalendar();
  wireSearch();

  const code = new URLSearchParams(location.search).get('code');
  if (code) {
    const s = league.find(r=>r.c===code);
    if (s) goToStock(s.c, s.n);
  }
});

/* ── Search ── */
function wireSearch() {
  const si=document.getElementById('searchInput'), dd=document.getElementById('searchDropdown');
  if(!si||!dd) return;
  let t;
  si.addEventListener('input',()=>{
    clearTimeout(t);
    t=setTimeout(()=>{
      const q=si.value.trim().toLowerCase();
      if(!q){dd.style.display='none';return;}
      const m=league.filter(r=>r.n.toLowerCase().includes(q)||r.c.includes(q)||String(parseInt(r.c,10)).includes(q)).slice(0,10);
      if(!m.length){dd.style.display='none';return;}
      dd.innerHTML=m.map(r=>`<div class="dropdown-item" onmousedown="event.preventDefault();goToStock('${r.c}','${r.n.replace(/'/g,"\\'")}');document.getElementById('searchInput').value='${fmtCode(r.c)} — ${r.n.replace(/'/g,"\\'")}';document.getElementById('searchDropdown').style.display='none'"><span class="di-code">${fmtCode(r.c)}</span><span class="di-name">${r.n}</span><span class="di-code" style="margin-left:auto;color:${r.act?'var(--green)':'var(--tx3)'}">${r.act?'Active':'Inactive'}</span></div>`).join('');
      dd.style.display='block';
    },120);
  });
  si.addEventListener('blur',()=>setTimeout(()=>{dd.style.display='none';},200));
}

/* ── Chart ── */
let chartInst = null;
function buildChart(monthly, events, vwap) {
  const barColors = monthly.map(d=>{
    if(!d.cn) return 'rgba(88,166,255,0.08)';
    return (d.cn/Math.max(d.sh,1))<vwap?'rgba(63,185,80,0.55)':'rgba(88,166,255,0.45)';
  });
  const vwapPlugin={id:'vwap',afterDraw(chart){if(!vwap)return;const{ctx,chartArea,scales}=chart;const y=scales.yp.getPixelForValue(vwap);if(y<chartArea.top||y>chartArea.bottom)return;ctx.save();ctx.strokeStyle='rgba(248,81,73,0.45)';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(chartArea.left,y);ctx.lineTo(chartArea.right,y);ctx.stroke();ctx.fillStyle='rgba(248,81,73,0.65)';ctx.font='9px monospace';ctx.textAlign='left';ctx.fillText(`VWAP $${vwap}`,chartArea.left+4,y-3);ctx.restore();}};
  if(chartInst) chartInst.destroy();
  const canvas=document.getElementById('mainChart');
  if(!canvas) return;
  chartInst=new Chart(canvas.getContext('2d'),{
    data:{
      labels:monthly.map(d=>pLabel(d.p)),
      datasets:[
        {type:'line',data:monthly.map(d=>d.price||0),yAxisID:'yp',borderColor:'#58a6ff',borderWidth:2,pointRadius:2,pointBackgroundColor:'#58a6ff',tension:0.3,fill:false,order:1},
        {type:'bar',data:monthly.map(d=>+((d.cn||0)/1e9).toFixed(2)),yAxisID:'yb',backgroundColor:barColors,borderColor:barColors.map(c=>c.replace(/[\d.]+\)$/,'0.9)')),borderWidth:1,borderRadius:3,order:2}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      interaction:{mode:'index',intersect:false},
      plugins:{legend:{display:false},tooltip:{backgroundColor:'#1c2330',borderColor:'#2a3140',borderWidth:1,titleColor:'#e6edf3',bodyColor:'#8b949e',padding:10,callbacks:{label(c){if(c.datasetIndex===0)return` Price: HK$${c.raw}`;return c.raw>0?` Buyback: HK$${c.raw.toFixed(1)}B`:' No repurchase';}}}},
      scales:{x:{grid:{color:'rgba(255,255,255,.04)'},ticks:{color:'#6e7681',font:{size:11},maxRotation:0}},yp:{position:'left',grid:{color:'rgba(255,255,255,.06)'},ticks:{color:'#58a6ff',font:{size:11},callback:v=>`$${v}`},border:{display:false}},yb:{position:'right',grid:{drawOnChartArea:false},ticks:{color:'#3fb950',font:{size:11},callback:v=>`$${v}B`},border:{display:false}}}
    },
    plugins:[vwapPlugin]
  });
}

/* ── Monthly table ── */
function buildMonthlyTable(monthly, vwap) {
  const maxCn=Math.max(...monthly.map(d=>d.cn||0),1);
  const mtb=document.getElementById('mtbody');
  if(!mtb) return;
  mtb.innerHTML='';
  [...monthly].reverse().forEach(row=>{
    const cn=row.cn||0, sh=row.sh||0, px=row.price||0, mv=row.mv||0;
    const pct=maxCn>0?(cn/maxCn)*70:0;
    const vw=sh>0?cn/sh:0;
    const vs=vwap>0&&vw>0?((vw/vwap-1)*100):null;
    const vsClass=vs===null?'':(vs<0?'style="color:var(--green)"':'style="color:var(--red)"');
    const vsTxt=vs===null?'—':`${vs>=0?'+':''}${vs.toFixed(1)}%`;
    const volPct=(sh>0&&mv>0)?(sh/mv*100):null;
    const volTxt=volPct===null?'<span style="color:var(--tx3)">—</span>':`<span style="color:${volPct>=5?'var(--amber)':volPct>=3?'var(--tx)':'var(--tx2)'}">${volPct.toFixed(1)}%</span>`;
    const hiTxt=row.hi>0?`<span class="hi">H ${row.hi.toFixed(1)}</span>`:null;
    const loTxt=row.lo>0?`<span class="lo">L ${row.lo.toFixed(1)}</span>`:null;
    const pxRange=(hiTxt&&loTxt)?`<span style="font-family:var(--mono);font-size:12px">${hiTxt}  ${loTxt}</span>`:'<span style="color:var(--tx3)">—</span>';
    const tr=document.createElement('tr');
    if(row.blackout) tr.style.background='rgba(110,118,129,.06)';
    tr.innerHTML=`<td class="bold">${pLabel(row.p)}${row.blackout?'<span style="font-size:9px;color:var(--tx3);margin-left:4px">⛔</span>':''}</td>
      <td class="num">${row.d||'—'}</td>
      <td class="num">${sh>0?fmtB(sh):'—'}</td>
      <td class="num">${sh>0?pxRange:'—'}</td>
      <td class="num"><div class="bc">${cn>0?`<div class="ib2 ${pct>40?'hi2':''}" style="width:${pct}px"></div>`:''}${cn>0?fmtHKD(cn):`<span style="color:var(--tx3)">${row.blackout?'Blackout period':'No repurchase'}</span>`}</div></td>
      <td class="num" style="color:var(--tx)">${(row.cum||0).toFixed(2)}%</td>
      <td class="num">${volTxt}</td>
      <td class="num" ${vsClass}>${vsTxt}</td>
      <td>${cn>0&&row.filing_date?`<a class="fl" href="https://www1.hkexnews.hk/search/titlesearch.xhtml" target="_blank">PDF <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 10L10 2M5 2h5v5" stroke-linecap="round" stroke-linejoin="round"/></svg></a>`:'<span style="color:var(--tx3);font-size:11px">—</span>'}</td>`;
    mtb.appendChild(tr);
  });
}

/* ── Mandate stats ── */
function buildMandateStats(data) {
  const el=document.getElementById('mandateStats');
  if(!el||!data) return;
  const pc=data.pct_issued||0, mandPct=data.mandate_pct||10, ff=data.free_float_pct||35;
  const sh=data.shares_issued||1, available=mandPct-pc;
  const shAvail=sh*available/100, estVal=shAvail*(data.vwap_hkd||0);
  const floatAdj=(pc/ff*100).toFixed(2), floatMand=(mandPct/ff*100).toFixed(2);
  const authUsed=(pc/mandPct*100).toFixed(1);
  el.innerHTML=`
    <div class="mc-group">
      <span class="mc-group-label">As % of issued share capital</span>
      <div class="mcs-item"><span class="mcs-label">Repurchased YTD</span><span class="mcs-value ok">${pc.toFixed(2)}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">AGM mandate limit</span><span class="mcs-value dim">${mandPct.toFixed(2)}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Still available</span><span class="mcs-value ok">${available.toFixed(2)}%<span class="mcs-unit">≈ ${fmtHKD(estVal)} · ${fmtB(shAvail)} shares</span></span></div>
    </div>
    <div class="mc-vdivider"></div>
    <div class="mc-group">
      <span class="mc-group-label">Progress against mandate authority</span>
      <div class="mcs-item"><span class="mcs-label">Authority used</span><span class="mcs-value ok">${authUsed}%<span class="mcs-unit">of ${mandPct}% limit</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Mandate expires</span><span class="mcs-value dim">Next AGM<span class="mcs-unit">approx. 2027</span></span></div>
    </div>
    <div class="mc-vdivider"></div>
    <div class="mc-group">
      <span class="mc-group-label">Free float adjustment</span>
      <div class="mcs-item"><span class="mcs-label">Free float</span><span class="mcs-value dim">~${ff}%<span class="mcs-unit">of issued capital</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Bought back (float-adj.)</span><span class="mcs-value ok">${floatAdj}%<span class="mcs-unit">of free float</span></span></div>
      <div class="mcs-item"><span class="mcs-label">Mandate limit (float-adj.)</span><span class="mcs-value dim">${floatMand}%<span class="mcs-unit">of free float</span></span></div>
    </div>`;
}

/* ── Prob factors ── */
function buildProbFactors(data) {
  const cs=data.consistency_score||0, act=data.programme_active||false;
  const underwater=(data.current_price_hkd||0)<(data.vwap_hkd||0);
  const mc=data.mandate_consumed_pct||0;
  const factors=[];
  if(act) factors.push({label:'Programme active',score:25,color:'var(--green)'});
  if(cs>=4) factors.push({label:`Consistency score ${cs}/5`,score:22,color:'var(--green)'});
  else if(cs>=3) factors.push({label:`Consistency score ${cs}/5`,score:12,color:'var(--amber)'});
  if(underwater) factors.push({label:'Buying while underwater (vs VWAP)',score:20,color:'var(--amber)'});
  if(mc>=10) factors.push({label:'Mandate pace on track',score:15,color:'var(--amber)'});
  const el=document.getElementById('probFactors');
  if(!el) return;
  el.innerHTML='';
  factors.forEach(f=>{const d=document.createElement('div');d.className='pf-item';d.innerHTML=`<span class="pf-dot" style="background:${f.color}"></span>${f.label} <span style="color:var(--tx2);font-family:var(--mono);margin-left:3px">(+${f.score})</span>`;el.appendChild(d);});
}

/* ── Metric cards ── */
function buildMetricCards(data) {
  const el=document.getElementById('metricCards');
  if(!el||!data) return;
  const cn=data.cumulative_notional||0, sh=data.shares_bought||0;
  const pct=data.pct_issued||0, ff=data.free_float_pct||35;
  const vwap=data.vwap_hkd||0, curPx=data.current_price_hkd||0;
  const floatAdj=(pct/ff*100).toFixed(2);
  const pctVwap=vwap>0?((curPx/vwap-1)*100).toFixed(1):'—';
  const isUnder=curPx>0&&vwap>0&&curPx<vwap;
  const activeMths=(data.monthly||[]).filter(m=>(m.notional||0)>0).length||1;
  const avgMo=cn/activeMths, ann=avgMo*12;
  el.innerHTML=`
    <div class="mc2"><div class="ml">YTD Consideration</div><div class="mv" style="font-size:18px">${fmtHKD(cn)}</div><div class="ms2">${activeMths} active months</div></div>
    <div class="mc2"><div class="ml">Shares Bought</div><div class="mv">${fmtB(sh)}</div><div class="ms2">${pct.toFixed(2)}% issued · ${floatAdj}% float</div></div>
    <div class="mc2"><div class="ml">VWAP Paid</div><div class="mv" style="font-size:18px">HK$${vwap}</div><div class="ms2">vs current HK$${curPx}</div>${isUnder?`<div class="uw-flag">▼ Underwater ${pctVwap}% · still buying</div>`:`<div class="md up">↑ Above VWAP +${pctVwap}%</div>`}</div>
    <div class="mc2"><div class="ml">Avg Monthly Spend</div><div class="mv" style="font-size:18px">${fmtHKD(avgMo)}</div><div class="ms2">Annualised est. ${fmtHKD(ann)}</div></div>`;
}

/* ── Insight box ── */
function buildInsightBox(data) {
  const el=document.getElementById('insightBox');
  if(!el||!data) return;
  const pct=data.pct_issued||0, ff=data.free_float_pct||35;
  const vwap=data.vwap_hkd||0, curPx=data.current_price_hkd||0;
  const isUnder=curPx>0&&vwap>0&&curPx<vwap;
  const floatAdj=(pct/ff*100).toFixed(2);
  el.innerHTML=`
    <div class="ib-head"><svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1a5 5 0 0 1 2 9.5V12H6v-1.5A5 5 0 0 1 8 1z"/><path d="M6 13h4M7 15h2" stroke-linecap="round"/></svg>Capital return summary &amp; DI context</div>
    <div class="ib-points">
      ${isUnder?`<div class="ib-point"><div class="ib-icon bear">▼</div><span class="ib-text"><strong>Buying underwater:</strong> VWAP paid HK$${vwap} vs current HK$${curPx} (${((curPx/vwap-1)*100).toFixed(1)}%). Still actively buying — signalling conviction at current levels.</span></div>`:`<div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Buying above VWAP:</strong> Current price HK$${curPx} is above the average cost HK$${vwap}. Programme still active.</span></div>`}
      <div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Float impact is material:</strong> ${pct.toFixed(2)}% of issued capital = <strong>${floatAdj}% of freely traded shares</strong> absorbed.</span></div>
      <div class="ib-point"><div class="ib-icon bull">↑</div><span class="ib-text"><strong>Buyback yield ${pct.toFixed(1)}%</strong> at current price. Higher yields suggest management sees shares as undervalued.</span></div>
      <div class="ib-point" style="padding-top:8px;margin-top:4px;border-top:1px solid var(--bd)">
        <div class="ib-icon di">DI</div>
        <span class="ib-text"><strong>DI context:</strong> ${data.name} has repurchased <strong>${pct.toFixed(2)}% of issued capital</strong>. Cross-reference with DI filings for institutional accumulation signals. <a href="../di/?code=${data.code}">View DI filings →</a></span>
      </div>
    </div>`;
}

/* ── Update hero from league data ── */
function updateHero(r) {
  const el=id=>document.getElementById(id);
  if(el('heroName')) el('heroName').textContent=r.n;
  if(el('heroCode')) el('heroCode').textContent=fmtCode(r.c);
  const ab=el('activeBadge');
  if(ab){ab.className=r.act?'badge-live':'badge-inactive';ab.textContent=r.act?'Active':'Completed';}
  const csB=el('csBadge');
  if(csB){csB.className=`cs-badge ${csClass(r.cs)}`;csB.textContent=`${csStars(r.cs)} ${r.cs}`;}
  const sig=el('sigBadge');
  if(sig){const s=r.curPx>0&&r.vwap>0&&r.curPx<r.vwap;sig.className=s?'sig-hero-strong':'sig-hero-moderate';sig.textContent=s?'● Strong signal':'● Moderate signal';}
  const uw=el('uwBadge');
  if(uw){const s=r.curPx>0&&r.vwap>0&&r.curPx<r.vwap;uw.style.display=s?'inline-flex':'none';if(s)uw.textContent=`▼ VWAP underwater ${((r.curPx/r.vwap-1)*100).toFixed(1)}%`;}
  const mBar=el('mandateBarHero'), mBarE=el('mandateBarExpanded');
  if(mBar) mBar.style.width=r.mc+'%';
  if(mBarE) mBarE.style.width=r.mc+'%';
  const mStat=el('mandateStatHero');
  if(mStat) mStat.innerHTML=`<span style="color:var(--green)">${r.mc.toFixed(1)}%</span> of mandate used · <span style="color:var(--green)">${(100-r.mc).toFixed(1)}%</span> remaining`;
  const econ=el('econStrip');
  if(econ){const floatAdj=(r.pc/r.ff*100).toFixed(2);econ.innerHTML=`<div class="es-item"><span class="es-label">Buyback yield</span><span class="es-val pos">${r.bbYld.toFixed(1)}%</span></div><div class="es-sep"></div><div class="es-item"><span class="es-label">Free float</span><span class="es-val neu">${r.ff}%</span></div><div class="es-sep"></div><div class="es-item"><span class="es-label">Float-adj. repurchased</span><span class="es-val pos">${floatAdj}%</span></div><div class="es-sep"></div><div class="es-item"><span class="es-label">Mandate used</span><span class="es-val neu">${r.mc.toFixed(1)}%</span></div>`;}
  const pPct=el('probPct'),pBar=el('probBar'),pLabel2=el('probLabel');
  if(pPct){pPct.textContent=r.renewProb+'%';}
  if(pBar) pBar.style.width=r.renewProb+'%';
  if(pLabel2) pLabel2.textContent=`Probability of mandate renewal at ${r.agm?new Date(r.agm+'T00:00:00').getFullYear()+1:'next'} AGM`;
}

/* ── Go to stock ── */
async function goToStock(code, name) {
  const si=document.getElementById('searchInput');
  if(si) si.value=`${fmtCode(code)} — ${name}`;
  switchView('stock', null);
  window.scrollTo({top:0,behavior:'smooth'});

  const r=league.find(x=>x.c===code);
  if(r) updateHero(r);

  const dl=document.getElementById('diCrossLink'), dh=document.getElementById('diCrossLinkHref');
  if(dl&&dh){dl.style.display='flex';dh.href=`../di/?code=${code}`;}

  const mtb=document.getElementById('mtbody');
  if(mtb) mtb.innerHTML=`<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:24px">Loading filing data…</td></tr>`;
  const mc=document.getElementById('metricCards'); if(mc) mc.innerHTML='';
  const ib=document.getElementById('insightBox'); if(ib) ib.innerHTML='';

  const data=await fetchJSON(`ca_${code}`,`${BASE}/ca/${code}.json`);
  if(data){
    const monthly=mapMonthly(data);
    const vwap=data.vwap_hkd||0;
    gMonthly=monthly; gVwap=vwap; gStockData=data;
    buildChart(monthly,[],vwap);
    buildMonthlyTable(monthly,vwap);
    buildMandateStats(data);
    buildMetricCards(data);
    buildInsightBox(data);
    buildProbFactors(data);
    const cs=document.getElementById('chartSub');
    if(cs&&monthly.length){cs.textContent=`${pLabel(monthly[0].p)}–${pLabel(monthly[monthly.length-1].p)} · price (left) · buyback HK$B (right)`;}
  } else {
    if(mtb) mtb.innerHTML=`<tr><td colspan="9" style="text-align:center;color:var(--tx3);padding:24px">Filing data for ${name} not yet scraped.</td></tr>`;
  }
}

/* ── View switcher ── */
const VIEWS={home:'homev',stock:'sv',league:'lv',lastsession:'lastsessionv',ideas:'ideasv',calendar:'calendarv'};
function switchView(v,btn){
  document.querySelectorAll('.vb').forEach(b=>b.classList.remove('on'));
  if(btn) btn.classList.add('on');
  Object.keys(VIEWS).forEach(k=>{const el=document.getElementById(VIEWS[k]);if(el)el.style.display=k===v?'block':'none';});
  if(v==='stock') setTimeout(()=>{if(chartInst)chartInst.resize();},50);
}

/* ── League ── */
let lFilter='all', lSort='ytd';
const lTitles={ytd:'YTD repurchase — ranked by consideration',pct:'ranked by % issued capital',mandate:'ranked by mandate consumed',date:'ranked by last filing date'};
const lCols={ytd:'lh-consideration',pct:'lh-pct',mandate:'lh-mandate',date:'lh-date'};
function renderLeague(){
  const tb=document.getElementById('ltbody');
  if(!tb) return;
  if(!league.length){tb.innerHTML='<tr><td colspan="8" style="text-align:center;color:var(--tx3);padding:20px">Loading…</td></tr>';return;}
  let data=[...league];
  if(lFilter==='active') data=data.filter(d=>d.act);
  if(lFilter==='big') data=data.filter(d=>d.cn>=5e9);
  if(lSort==='ytd') data.sort((a,b)=>b.cn-a.cn);
  if(lSort==='pct') data.sort((a,b)=>b.pc-a.pc);
  if(lSort==='mandate') data.sort((a,b)=>b.mc-a.mc);
  if(lSort==='date') data.sort((a,b)=>b.lf.localeCompare(a.lf));
  const tEl=document.getElementById('leagueTitle'); if(tEl) tEl.textContent=lTitles[lSort];
  ['lh-consideration','lh-pct','lh-mandate','lh-date'].forEach(id=>{const el=document.getElementById(id);if(el)el.style.color='';});
  const ah=document.getElementById(lCols[lSort]); if(ah) ah.style.color='var(--accent)';
  const maxC=(league[0]||{cn:1}).cn||1;
  tb.innerHTML='';
  data.forEach((r,i)=>{
    const bw=Math.round(r.cn/maxC*80);
    const tr=document.createElement('tr');
    tr.innerHTML=`<td style="font-size:11px;font-family:var(--mono);color:var(--tx3)">${i+1}</td>
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
function sortLeague(by,btn){lSort=by;document.querySelectorAll('#lv .sort-btn').forEach(b=>b.classList.remove('on'));btn.classList.add('on');renderLeague();}
function filterL(f,el){lFilter=f;document.querySelectorAll('.chips .chip').forEach(c=>c.classList.remove('on'));el.classList.add('on');renderLeague();}

/* ── Last Session ── */
let lsSort='cn';
function renderLastSession(){
  const tb=document.getElementById('la-tbody');
  if(!tb) return;
  tb.innerHTML='';
  let rows=league.filter(r=>r.ld);
  if(lsSort==='cn') rows.sort((a,b)=>b.ld.cn-a.ld.cn);
  if(lsSort==='sh') rows.sort((a,b)=>b.ld.sh-a.ld.sh);
  if(!rows.length){tb.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--tx3);padding:24px">No last-session data available yet — NDDR events require recent filing activity.</td></tr>';return;}
  rows.forEach(r=>{
    const d=r.ld;
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--tx2)">${d.date}</td>
      <td class="num">${fmtB(d.sh)}</td>
      <td class="num" style="font-family:var(--mono);font-size:12px">HK$${d.hi.toFixed(2)}</td>
      <td class="num">${fmtHKD(d.cn)}</td>
      <td><a class="fl" href="https://www1.hkexnews.hk/search/titlesearch.xhtml" target="_blank">PDF <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 10L10 2M5 2h5v5" stroke-linecap="round" stroke-linejoin="round"/></svg></a></td>`;
    tb.appendChild(tr);
  });
}
function sortLS(by,btn){lsSort=by;document.querySelectorAll('#lastsessionv .sort-btn').forEach(b=>b.classList.remove('on'));btn.classList.add('on');renderLastSession();}

/* ── Ideas ── */
function renderConvictionBuys(){
  const tb=document.getElementById('cb-tbody');
  if(!tb) return;
  tb.innerHTML='';
  const rows=league.filter(r=>r.act&&r.curPx>0&&r.vwap>0&&r.curPx<r.vwap&&r.cs>=2).sort((a,b)=>(a.curPx/a.vwap)-(b.curPx/b.vwap));
  rows.forEach(r=>{
    const disc=((r.curPx/r.vwap-1)*100);
    const sigScore=r.cs>=3?'strong':'med';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td><span class="cs-badge ${csClass(r.cs)}" style="font-size:10px;padding:2px 7px">${csStars(r.cs)} ${r.cs}</span></td>
      <td class="num" style="color:var(--red)">HK$${r.curPx}</td>
      <td class="num">HK$${r.vwap}</td>
      <td class="num" style="color:var(--red)">${disc.toFixed(1)}%</td>
      <td class="num" style="color:var(--green)">${r.bbYld.toFixed(1)}%</td>
      <td><span class="signal-dot" style="background:${sigScore==='strong'?'var(--green)':'var(--amber)'}"></span><span style="font-size:12px;font-weight:500;color:${sigScore==='strong'?'var(--green)':'var(--amber)'}">${sigScore==='strong'?'Strong':'Moderate'}</span></td>`;
    tb.appendChild(tr);
  });
  if(!rows.length){const tr=document.createElement('tr');tr.innerHTML=`<td colspan="7" style="text-align:center;color:var(--tx3);padding:24px">No stocks currently match criteria (active + below VWAP + consistency ≥ 2)</td>`;tb.appendChild(tr);}
}
function renderMandateRenewers(){
  const tb=document.getElementById('mr-tbody');
  if(!tb) return;
  tb.innerHTML='';
  const today=new Date().toISOString().slice(0,10);
  const cutoff=new Date(); cutoff.setDate(cutoff.getDate()+90);
  const cut=cutoff.toISOString().slice(0,10);
  const rows=league.filter(r=>r.renewProb>=65&&r.mc>=5&&r.agm<=cut&&r.agm>=today).sort((a,b)=>b.renewProb-a.renewProb);
  rows.forEach(r=>{
    const floatAdj=(r.pc/r.ff*100).toFixed(2);
    const oc=r.renewProb>=80?'var(--green)':r.renewProb>=70?'var(--amber)':'var(--tx2)';
    const pf=r.renewProb>=80?'linear-gradient(90deg,#3fb950,#58a6ff)':'linear-gradient(90deg,#d29922,#e09c00)';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><div class="scell-link" onclick="goToStock('${r.c}','${r.n}')" tabindex="0"><span class="nm">${r.n}</span><span class="cd">${fmtCode(r.c)}</span></div></td>
      <td><span class="cs-badge ${csClass(r.cs)}" style="font-size:10px;padding:2px 7px">${csStars(r.cs)} ${r.cs}</span></td>
      <td style="font-family:var(--mono);font-size:12px;color:var(--tx2)">${r.agm}</td>
      <td class="num">${r.mc.toFixed(1)}%<span style="font-size:10px;color:var(--tx3);font-family:var(--sans)"> of mandate</span></td>
      <td class="num"><div style="display:flex;align-items:center;gap:6px;justify-content:flex-end"><div style="height:5px;width:50px;background:var(--bd);border-radius:3px;overflow:hidden"><div style="height:100%;width:${r.renewProb}%;background:${pf};border-radius:3px"></div></div><span style="font-family:var(--mono);font-size:12px;color:${oc}">${r.renewProb}%</span></div></td>
      <td class="num" style="color:var(--green)">${r.bbYld.toFixed(1)}%</td>
      <td class="num" style="color:var(--amber)">${floatAdj}%</td>
      <td><span style="font-size:11px;font-weight:500;color:${oc}">${r.renewProb>=80?'Strong':r.renewProb>=70?'Moderate':'Watch'}</span></td>`;
    tb.appendChild(tr);
  });
  if(!rows.length){const tr=document.createElement('tr');tr.innerHTML=`<td colspan="8" style="text-align:center;color:var(--tx3);padding:24px">No mandate renewers with AGM within 90 days currently meet criteria</td>`;tb.appendChild(tr);}
}
function switchIdeasTab(tab,btn){document.querySelectorAll('.ist-btn').forEach(b=>b.classList.remove('on'));btn.classList.add('on');document.querySelectorAll('.strat-pane').forEach(p=>p.classList.remove('on'));document.getElementById(tab+'-pane').classList.add('on');}

/* ── Calendar ── */
const _n=new Date();
let calYear=_n.getFullYear(), calMonth=_n.getMonth();
function renderCalendar(){
  const title=new Date(calYear,calMonth,1).toLocaleString('en-GB',{month:'long',year:'numeric'});
  const tEl=document.getElementById('calTitle'); if(tEl) tEl.textContent=title;
  const body=document.getElementById('calBody'); if(!body) return;
  body.innerHTML='';
  const fd=new Date(calYear,calMonth,1).getDay(), off=fd===0?6:fd-1;
  const dim=new Date(calYear,calMonth+1,0).getDate();
  for(let i=0;i<off;i++){const c=document.createElement('div');c.className='cal-cell empty';body.appendChild(c);}
  for(let d=1;d<=dim;d++){
    const ds=`${calYear}-${String(calMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const evs=calEvents.filter(e=>e.date===ds);
    const tod=new Date(), isToday=tod.getFullYear()===calYear&&tod.getMonth()===calMonth&&tod.getDate()===d;
    const cell=document.createElement('div');
    cell.className='cal-cell'+(isToday?' today':'');
    cell.innerHTML=`<div class="cal-day">${d}</div><div class="cal-events">${evs.slice(0,3).map(e=>`<div class="cal-event ${e.type}"><span>●</span>${e.name.split(' ')[0]}</div>`).join('')}${evs.length>3?`<div style="font-size:9px;color:var(--tx3);padding:1px 4px">+${evs.length-3}</div>`:''}</div>`;
    cell.addEventListener('click',()=>showCalDay(ds,evs));
    body.appendChild(cell);
  }
}
function showCalDay(ds,evs){
  const det=document.getElementById('calDetail'); if(!det) return;
  const fmt=new Date(ds+'T00:00:00').toLocaleDateString('en-GB',{weekday:'long',year:'numeric',month:'long',day:'numeric'});
  const dEl=document.getElementById('cdDate'); if(dEl) dEl.textContent=fmt;
  const list=document.getElementById('cdList'); if(!list) return;
  if(!evs.length){list.innerHTML='<div style="color:var(--tx3);font-size:13px">No corporate events on this date</div>';det.style.display='block';return;}
  list.innerHTML=evs.map(e=>`<div class="cd-item"><span class="cd-badge ${e.type}">${e.type==='agm'?'AGM':e.type==='results'?'Results':'Blackout'}</span><div><div class="cd-name">${e.name}</div><div class="cd-note">${e.note}</div></div></div>`).join('');
  det.style.display='block';
}
function calNav(dir){calMonth+=dir;if(calMonth>11){calMonth=0;calYear++;}if(calMonth<0){calMonth=11;calYear--;}renderCalendar();const d=document.getElementById('calDetail');if(d)d.style.display='none';}
