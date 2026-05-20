'use strict';

// ── Init ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  renderHeader('di');
  initTabs();
});

// ── Tab switching ────────────────────────────────────────────────────
function switchDITab(tabName) {
  const btn = document.querySelector(`.di-vb[data-tab="${tabName}"]`);
  if (btn) btn.click();
}

function discoverShareholder(name) {
  switchDITab('by-shareholder');
  setTimeout(() => {
    const inp = document.getElementById('sh-search');
    if (inp) {
      inp.value = name;
      inp.dispatchEvent(new Event('input'));
    }
  }, 60);
}

function initTabs() {
  document.querySelectorAll('.di-vb').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.di-vb').forEach(b => b.classList.remove('on'));
      document.querySelectorAll('.tab-panel').forEach(p => { p.classList.remove('active'); p.hidden = true; });
      btn.classList.add('on');
      const panel = document.getElementById(`tab-${btn.dataset.tab}`);
      if (panel) { panel.hidden = false; panel.classList.add('active'); }
      // Show filter input only on Latest tab
      const navRight = document.getElementById('diSubnavRight');
      if (navRight) navRight.hidden = btn.dataset.tab !== 'latest';
      if (btn.dataset.tab === 'latest') initLatest();
    });
  });
}

// ── TAB 1: Latest ────────────────────────────────────────────────────
let latestData = null;
let latestLoaded = false;

async function initLatest() {
  if (latestLoaded) return;
  latestLoaded = true;
  document.getElementById('latest-loading').hidden = false;
  document.getElementById('latest-result').hidden = true;
  document.getElementById('latest-empty').hidden = true;

  latestData = await fetchLatestFilings();

  // Fallback: aggregate from all DI files
  if (!latestData || !latestData.length) {
    const universe = await fetchUniverse();
    if (universe) {
      const allDI = await Promise.all(universe.slice(0, 50).map(s => fetchDI(s.code)));
      const entries = [];
      allDI.forEach((di, i) => {
        if (!di) return;
        const code = universe[i].code;
        const stockName = universe[i].name || di.name;
        (di.history || []).forEach(h => {
          entries.push({ filing_date: h.filing_date, code, stock_name: stockName, shareholder: h.name, notice_type: h.notice_type, long_position_pct: h.long_position_pct, form_type: h.form_type, relevant_event_date: h.relevant_event_date });
        });
      });
      entries.sort((a, b) => a.code.localeCompare(b.code));
      entries.sort((a, b) => (b.filing_date || '').localeCompare(a.filing_date || ''));
      latestData = entries.slice(0, 30);
    }
  }

  document.getElementById('latest-loading').hidden = true;

  if (!latestData || !latestData.length) {
    document.getElementById('latest-empty').hidden = false;
    document.getElementById('latest-empty').textContent = 'No filings available yet.';
    return;
  }

  const metaEl = document.getElementById('latest-meta');
  if (metaEl) metaEl.textContent = `${latestData.length} most recent filings across all tracked stocks`;

  renderLatest('');

  const filterEl = document.getElementById('latest-filter');
  if (filterEl) filterEl.addEventListener('input', function() { renderLatest(this.value.toLowerCase().trim()); });
}

function renderLatest(filter) {
  const rows = filter
    ? latestData.filter(f => f.shareholder.toLowerCase().includes(filter) || f.code.toLowerCase().includes(filter) || (f.stock_name||'').toLowerCase().includes(filter))
    : latestData;

  const tbody = document.getElementById('latest-tbody');
  const resultEl = document.getElementById('latest-result');
  const emptyEl = document.getElementById('latest-empty');

  if (!rows.length) { resultEl.hidden = true; emptyEl.hidden = false; return; }
  emptyEl.hidden = true; resultEl.hidden = false;

  // Group by (code, filing_date) with rowspan
  const groups = [];
  rows.forEach(f => {
    const key = `${f.code}|${f.filing_date}`;
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.filings.push(f);
    else groups.push({ key, code: f.code, stock_name: f.stock_name, filing_date: f.filing_date, filings: [f] });
  });

  tbody.innerHTML = groups.map((g, gi) => {
    const span = g.filings.length;
    return g.filings.map((f, i) => `
      <tr>
        ${i === 0 ? `
          <td rowspan="${span}" style="color:var(--tx2);font-family:var(--mono);font-size:12px;vertical-align:top">${fmtDateLong(g.filing_date)}</td>
          <td rowspan="${span}" style="vertical-align:top">
            <div class="scell-link" onclick="jumpToStock('${g.code}')" tabindex="0" role="button" style="display:inline-flex;flex-direction:column;gap:1px">
              <span class="nm" style="font-size:12px;font-family:var(--mono)">${parseInt(g.code,10)} HK</span>
              <span style="font-size:11px;color:var(--tx3)">${g.stock_name||''}</span>
            </div>
          </td>
        ` : ''}
        <td style="color:var(--tx2);font-size:13px;max-width:200px;overflow:hidden;text-overflow:ellipsis" title="${f.shareholder}">${f.shareholder}</td>
        <td>${noticeBadge(f.notice_type)}</td>
        <td class="num" style="font-family:var(--mono)">${fmtPct(f.long_position_pct)}</td>
        <td style="color:var(--tx3);font-family:var(--mono);font-size:12px">${fmtDateLong(f.relevant_event_date)}</td>
      </tr>
    `).join('');
  }).join('');
}

// ── TAB 2: By Stock ──────────────────────────────────────────────────
let currentStockData = null;
let currentShareholders = [];
let isHistoricalFallback = false;
let currentFilter = 'all';
let currentSort = 'pct';
let currentView = 'shareholders';

function deriveLastKnownShareholders(history) {
  const byName = {};
  history.forEach(h => {
    if (!h.name) return;
    if (!byName[h.name] || (h.filing_date||'') > (byName[h.name].filing_date||'')) byName[h.name] = h;
  });
  return Object.values(byName)
    .filter(h => (h.long_position_pct||0) > 0)
    .map(h => ({ name: h.name, long_position_pct: h.long_position_pct, long_position_shares: h.long_position_shares, filing_date: h.filing_date, entity_type: h.entity_type||'corporate' }))
    .sort((a,b) => (b.long_position_pct||0) - (a.long_position_pct||0));
}

async function stockItems(q) {
  const universe = await fetchUniverse();
  if (!universe) return [];
  return universe
    .filter(s => s.code.includes(q) || s.name.toLowerCase().includes(q) || `${parseInt(s.code,10)}`.includes(q))
    .map(s => ({
      label: s.code,
      html: `<span class="di-code">${parseInt(s.code,10)} HK</span> <span class="di-name">${s.name}</span>`,
      code: s.code, name: s.name
    }));
}

async function loadStock(code, name) {
  lastSelectedStock = { code, name };
  const data = await fetchDI(code);

  const emptyEl = document.getElementById('stock-empty');
  const resultEl = document.getElementById('stock-result');

  if (!data) {
    if (emptyEl) { emptyEl.hidden = false; emptyEl.textContent = `No disclosure data available for ${code}. This stock has not been scraped yet.`; }
    if (resultEl) resultEl.hidden = true;
    return;
  }
  currentStockData = data;

  let shareholders = data.shareholders || [];
  isHistoricalFallback = false;
  if (!shareholders.length && data.history?.length) {
    shareholders = deriveLastKnownShareholders(data.history);
    isHistoricalFallback = true;
  }
  currentShareholders = shareholders;

  if (emptyEl) emptyEl.hidden = true;
  if (resultEl) resultEl.hidden = false;

  const codeEl = document.getElementById('sh-code');
  const nameEl = document.getElementById('sh-name');
  if (codeEl) codeEl.textContent = '';
  if (nameEl) nameEl.textContent = `${data.name} · ${parseInt(data.code,10)} HK`;

  const totalPct = shareholders.reduce((s,sh) => s + (sh.long_position_pct||0), 0);
  const latestDate = shareholders.reduce((d,sh) => (sh.filing_date||'') > d ? (sh.filing_date||'') : d, '');
  const countEl = document.getElementById('sh-count-val');
  const sumEl = document.getElementById('sh-sum-val');
  const dateEl = document.getElementById('sh-date-val');
  if (countEl) countEl.textContent = shareholders.length || '—';
  if (sumEl) sumEl.textContent = shareholders.length ? totalPct.toFixed(1) + '%' : '—';
  if (dateEl) dateEl.textContent = fmtDateLong(latestDate) || '—';

  // Historical banner
  const banner = document.getElementById('historical-banner');
  if (banner) banner.hidden = !isHistoricalFallback;

  // CA cross-link: always show if we have the code
  const caLink = document.getElementById('di-to-ca-link');
  const caHref = document.getElementById('di-to-ca-href');
  if (caLink && caHref) {
    caLink.style.display = 'flex';
    caHref.href = `../ca/?code=${data.code}`;
    caHref.textContent = `View Corporate Actions for ${parseInt(data.code,10)} HK →`;
  }

  if (currentView === 'timeline') initStockTimeline();
  else renderShareholdersList(shareholders);
}

function renderShareholdersList(shareholders) {
  let rows = shareholders.filter(sh => currentFilter === 'all' || sh.entity_type === currentFilter);
  if (currentSort === 'pct') rows.sort((a,b) => (b.long_position_pct||0) - (a.long_position_pct||0));
  else if (currentSort === 'name') rows.sort((a,b) => a.name.localeCompare(b.name));
  else if (currentSort === 'date') rows.sort((a,b) => (b.filing_date||'').localeCompare(a.filing_date||''));

  const list = document.getElementById('shareholders-list');
  if (!list) return;

  const latestHistoryByName = {};
  (currentStockData?.history || []).forEach(h => {
    if (!latestHistoryByName[h.name] || (h.filing_date||'') > (latestHistoryByName[h.name].filing_date||'')) latestHistoryByName[h.name] = h;
  });

  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">No shareholders match the current filter.</div>';
    return;
  }

  const maxPct = Math.max(...rows.map(sh => sh.long_position_pct||0), 1);

  list.innerHTML = rows.map(sh => {
    const pct = sh.long_position_pct || 0;
    const barW = ((pct / maxPct) * 100).toFixed(1);
    const histEntry = latestHistoryByName[sh.name];
    const type = sh.entity_type || 'corporate';
    const badge = `<span class="entity-badge entity-${type}">${type}</span>`;
    const noticeBadgeHtml = histEntry ? noticeBadge(histEntry.notice_type) : '';
    return `<div class="sh-row">
      <div class="sh-info">
        <div class="sh-name">${sh.name} ${badge} ${noticeBadgeHtml}</div>
        <div class="sh-meta"><span>${fmtDateLong(sh.filing_date)}</span><span>${sh.form_type||''}</span></div>
      </div>
      <div class="sh-bar-wrap">
        <div class="sh-bar-track"><div class="sh-bar-fill" style="width:${barW}%"></div></div>
      </div>
      <div>
        <div class="sh-pct">${pct.toFixed(2)}%</div>
        <div class="sh-shares">${fmtShares(sh.long_position_shares)}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Timeline ─────────────────────────────────────────────────────────
function initStockTimeline() {
  if (!currentStockData) return;
  const history = currentStockData.history || [];
  if (history.length) {
    const dates = history.map(h => h.relevant_event_date).filter(Boolean).sort();
    const fromEl = document.getElementById('tl-date-from');
    const toEl = document.getElementById('tl-date-to');
    if (fromEl) fromEl.value = dates[0] || '';
    if (toEl) toEl.value = dates[dates.length-1] || '';
  }
  renderTimeline();
}

function renderTimeline() {
  if (!currentStockData) return;
  const history = currentStockData.history || [];
  const shFilter = (document.getElementById('tl-sh-filter')?.value || '').toLowerCase().trim();
  const dateFrom = document.getElementById('tl-date-from')?.value;
  const dateTo = document.getElementById('tl-date-to')?.value;

  let rows = history.filter(h => {
    if (shFilter && !h.name.toLowerCase().includes(shFilter)) return false;
    if (dateFrom && h.relevant_event_date < dateFrom) return false;
    if (dateTo && h.relevant_event_date > dateTo) return false;
    return true;
  });

  const tbody = document.getElementById('tl-tbody');
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--tx3);padding:30px">No filings match the current filters.</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(h => `<tr>
    <td style="font-family:var(--mono);font-size:12px">${h.relevant_event_date||'—'}</td>
    <td>${h.name}</td>
    <td>${noticeBadge(h.notice_type)}</td>
    <td class="num" style="font-family:var(--mono)">${fmtPct(h.long_position_pct)}</td>
    <td style="color:var(--tx3)">${h.form_type||'—'}</td>
    <td style="font-family:var(--mono);font-size:12px;color:var(--tx3)">${h.filing_date||'—'}</td>
  </tr>`).join('');
}

// ── TAB 3: By Shareholder ────────────────────────────────────────────
async function shareholderItems(q) {
  const idx = await fetchShareholdersIndex();
  if (!idx) return [];
  return Object.keys(idx)
    .filter(name => name.toLowerCase().includes(q))
    .map(name => ({
      label: name,
      html: `<span class="di-name">${name}</span> <span class="di-code">${idx[name].length} stock${idx[name].length!==1?'s':''}</span>`,
      name, codes: idx[name]
    }));
}

async function loadShareholder(name, codes) {
  const resultEl = document.getElementById('sh-result');
  const emptyEl = document.getElementById('sh-empty');
  if (resultEl) resultEl.hidden = false;
  if (emptyEl) emptyEl.hidden = true;
  const nameEl = document.getElementById('sh-result-name');
  if (nameEl) nameEl.textContent = name;

  const tbody = document.getElementById('sh-holdings-tbody');
  if (!tbody) return;
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--tx3);padding:20px">Loading…</td></tr>';

  const universe = await fetchUniverse();
  const uMap = Object.fromEntries((universe||[]).map(s => [s.code, s]));

  const rows = await Promise.all(codes.map(async code => {
    const di = await fetchDI(code);
    if (!di) return null;
    const sh = (di.shareholders||[]).find(s => s.name === name);
    if (!sh) return null;
    return { code, stockName: uMap[code]?.name || di.name, sh };
  }));

  const valid = rows.filter(Boolean).sort((a,b) => (b.sh.long_position_pct||0) - (a.sh.long_position_pct||0));

  if (!valid.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--tx3);padding:20px">No current holdings found.</td></tr>';
    return;
  }
  tbody.innerHTML = valid.map(({code, stockName, sh}) => `<tr>
    <td><div class="scell-link" onclick="jumpToStock('${code}')" tabindex="0" role="button"><span class="nm" style="font-size:12px;font-family:var(--mono)">${parseInt(code,10)} HK</span></div></td>
    <td>${stockName}</td>
    <td class="num" style="font-family:var(--mono)">${fmtPct(sh.long_position_pct)}</td>
    <td class="num" style="font-family:var(--mono)">${fmtShares(sh.long_position_shares)}</td>
    <td style="font-family:var(--mono);font-size:12px;color:var(--tx3)">${sh.filing_date||'—'}</td>
  </tr>`).join('');
}

makeDropdown(
  document.getElementById('sh-search'),
  document.getElementById('sh-dropdown'),
  shareholderItems,
  item => loadShareholder(item.name, item.codes)
);

function jumpToStock(code) {
  switchDITab('latest');
  setTimeout(() => {
    const filter = document.getElementById('latest-filter');
    if (filter) { filter.value = code; filter.dispatchEvent(new Event('input')); }
  }, 80);
}

// ── TAB 4: Compare ───────────────────────────────────────────────────
const compareSelected = [];
const MAX_COMPARE = 5;
let lastSelectedStock = null;

makeDropdown(
  document.getElementById('compare-search'),
  document.getElementById('compare-dropdown'),
  stockItems,
  item => addCompareStock(item.code, item.name)
);

function addCompareStock(code, name) {
  if (compareSelected.length >= MAX_COMPARE) return;
  if (compareSelected.find(s => s.code === code)) return;
  compareSelected.push({ code, name });
  document.getElementById('compare-search').value = '';
  renderCompareChips();
  renderCompareMatrix();
}

function removeCompareStock(code) {
  const idx = compareSelected.findIndex(s => s.code === code);
  if (idx !== -1) compareSelected.splice(idx, 1);
  renderCompareChips();
  renderCompareMatrix();
}

function renderCompareChips() {
  const el = document.getElementById('compare-chips');
  if (!el) return;
  el.innerHTML = compareSelected.map(s => `
    <div class="compare-chip">
      <span>${parseInt(s.code,10)} HK — ${s.name}</span>
      <button onclick="removeCompareStock('${s.code}')" title="Remove">×</button>
    </div>`).join('');
}

async function renderCompareMatrix() {
  const resultEl = document.getElementById('compare-result');
  const emptyEl = document.getElementById('compare-empty');
  if (!resultEl || !emptyEl) return;

  if (compareSelected.length < 2) {
    resultEl.hidden = true; emptyEl.hidden = false;
    emptyEl.textContent = compareSelected.length === 0
      ? 'Add up to 5 stocks above to compare their shareholders side by side.'
      : 'Add at least one more stock to compare.';
    return;
  }

  resultEl.hidden = false; emptyEl.hidden = true;

  const allDI = await Promise.all(compareSelected.map(s => fetchDI(s.code)));
  const allNames = new Set();
  allDI.forEach(di => (di?.shareholders||[]).forEach(sh => allNames.add(sh.name)));

  const matrix = {};
  allNames.forEach(name => { matrix[name] = {}; });
  allDI.forEach((di, i) => {
    const code = compareSelected[i].code;
    (di?.shareholders||[]).forEach(sh => { matrix[sh.name][code] = sh.long_position_pct||0; });
  });

  const sortedNames = [...allNames].sort((a,b) => Math.max(...Object.values(matrix[b])) - Math.max(...Object.values(matrix[a])));
  const codes = compareSelected.map(s => s.code);

  document.getElementById('compare-thead').innerHTML = `<tr><th>Shareholder</th>${codes.map(c => `<th class="num">${parseInt(c,10)} HK<br><span style="font-size:10px;color:var(--tx3);font-weight:400">${compareSelected.find(s=>s.code===c)?.name||''}</span></th>`).join('')}</tr>`;
  document.getElementById('compare-tbody').innerHTML = sortedNames.map(name => `<tr><td>${name}</td>${codes.map(c => { const pct = matrix[name][c]; return pct ? `<td class="num ${heatClass(pct)}">${fmtPct(pct)}</td>` : `<td class="num" style="color:var(--tx3)">—</td>`; }).join('')}</tr>`).join('');

  const totals = codes.map(c => { const di = allDI[codes.indexOf(c)]; return (di?.shareholders||[]).reduce((s,sh) => s+(sh.long_position_pct||0), 0); });
  document.getElementById('compare-tfoot').innerHTML = `<tr><td><strong>Total disclosed</strong></td>${totals.map(t => `<td class="num"><strong>${t.toFixed(1)}%</strong></td>`).join('')}</tr>`;
}

// ── DI Home search ───────────────────────────────────────────────────
(function initHomeSearch() {
  const inp = document.getElementById('diHomeSearch');
  const res = document.getElementById('diHomeSearchResults');
  if (!inp || !res) return;

  let timer;
  inp.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = inp.value.trim().toLowerCase();
      if (q.length < 2) { res.style.display = 'none'; return; }

      const [universe, idx] = await Promise.all([fetchUniverse(), fetchShareholdersIndex()]);
      const results = [];

      // Shareholders from index
      if (idx) {
        Object.keys(idx)
          .filter(n => n.toLowerCase().includes(q))
          .slice(0, 6)
          .forEach(n => results.push({ type: 'sh', label: n }));
      }

      // Stocks from universe
      if (universe) {
        universe
          .filter(s => s.code.includes(q) || s.name.toLowerCase().includes(q) || `${parseInt(s.code,10)}`.includes(q))
          .slice(0, 4)
          .forEach(s => results.push({ type: 'stock', label: s.name, code: s.code }));
      }

      if (!results.length) {
        res.innerHTML = '<div class="di-home-sr-empty">No results found</div>';
        res.style.display = 'block';
        return;
      }

      res.innerHTML = results.map(r => r.type === 'sh'
        ? `<div class="di-home-sr-item" data-type="sh" data-name="${r.label}">
            <span class="di-home-sr-icon">👤</span>
            <span class="di-home-sr-text">${r.label}</span>
            <span class="di-home-sr-hint">By Shareholder →</span>
           </div>`
        : `<div class="di-home-sr-item" data-type="stock" data-code="${r.code}">
            <span class="di-home-sr-icon">${parseInt(r.code,10)} HK</span>
            <span class="di-home-sr-text">${r.label}</span>
            <span class="di-home-sr-hint">Latest →</span>
           </div>`
      ).join('');
      res.style.display = 'block';

      res.querySelectorAll('.di-home-sr-item').forEach(item => {
        item.addEventListener('mousedown', e => {
          e.preventDefault();
          res.style.display = 'none';
          inp.value = '';
          if (item.dataset.type === 'sh') {
            discoverShareholder(item.dataset.name);
          } else {
            switchDITab('latest');
            setTimeout(() => {
              const filter = document.getElementById('latest-filter');
              if (filter) { filter.value = item.dataset.code; filter.dispatchEvent(new Event('input')); }
            }, 100);
          }
        });
      });
    }, 150);
  });

  inp.addEventListener('blur', () => setTimeout(() => { res.style.display = 'none'; }, 200));
})();
