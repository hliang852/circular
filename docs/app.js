'use strict';

const BASE = window.DATA_BASE || 'data';

// ── Data cache ──────────────────────────────────────────────────────────────

const cache = {};

async function fetchUniverse() {
  if (cache.universe) return cache.universe;
  const res = await fetch(`${BASE}/universe.json`);
  cache.universe = await res.json();
  return cache.universe;
}

async function fetchIndex() {
  if (cache.index) return cache.index;
  const res = await fetch(`${BASE}/shareholders_index.json`);
  cache.index = await res.json();
  return cache.index;
}

async function fetchDI(code) {
  if (cache[code]) return cache[code];
  try {
    const res = await fetch(`${BASE}/di/${code}.json`);
    if (!res.ok) return null;
    cache[code] = await res.json();
    return cache[code];
  } catch {
    return null;
  }
}

async function fetchLatest() {
  if (cache.latest) return cache.latest;
  try {
    const res = await fetch(`${BASE}/latest_filings.json`);
    if (res.ok) {
      cache.latest = await res.json();
      return cache.latest;
    }
  } catch {}
  // Fallback: aggregate from all available DI files
  const universe = await fetchUniverse();
  const allDI = await Promise.all(universe.map(s => fetchDI(s.code)));
  const entries = [];
  allDI.forEach((di, i) => {
    if (!di) return;
    const code = universe[i].code;
    const stockName = universe[i].name || di.name;
    (di.history || []).forEach(h => {
      entries.push({
        filing_date: h.filing_date,
        code,
        stock_name: stockName,
        shareholder: h.name,
        notice_type: h.notice_type,
        long_position_pct: h.long_position_pct,
        form_type: h.form_type,
        relevant_event_date: h.relevant_event_date,
      });
    });
  });
  // Sort: filing_date desc, code asc within same date
  entries.sort((a, b) => a.code.localeCompare(b.code));
  entries.sort((a, b) => (b.filing_date || '').localeCompare(a.filing_date || ''));
  cache.latest = entries.slice(0, 30);
  return cache.latest;
}

// ── Formatting helpers ───────────────────────────────────────────────────────

function fmtShares(n) {
  if (!n) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return n.toLocaleString();
}

function fmtMktcap(usd) {
  if (!usd) return '';
  if (usd >= 1e12) return '$' + (usd / 1e12).toFixed(1) + 'T';
  if (usd >= 1e9) return '$' + (usd / 1e9).toFixed(0) + 'B';
  return '$' + (usd / 1e6).toFixed(0) + 'M';
}

function fmtPct(n) {
  if (n == null || n === 0) return '—';
  return n.toFixed(2) + '%';
}

function noticeBadge(type) {
  const cls = (type || 'change').toLowerCase();
  const arrow = cls === 'increase' ? '↑' : cls === 'decrease' ? '↓' : '';
  return `<span class="notice-badge ${cls}">${arrow ? arrow + ' ' : ''}${type || 'Change'}</span>`;
}

function noticeTag(type) {
  const cls = (type || 'change').toLowerCase();
  const arrow = cls === 'increase' ? '↑' : cls === 'decrease' ? '↓' : '';
  return `<span class="notice-tag ${cls}">${arrow ? arrow + ' ' : ''}${type || 'Change'}</span>`;
}

function fmtDateLong(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}

function heatClass(pct) {
  if (!pct) return 'heat-0';
  if (pct < 5)  return 'heat-1';
  if (pct < 10) return 'heat-2';
  if (pct < 20) return 'heat-3';
  if (pct < 30) return 'heat-4';
  return 'heat-5';
}

// ── Shared state ─────────────────────────────────────────────────────────────

let lastSelectedStock = null;

// ── Tab switching ────────────────────────────────────────────────────────────

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => {
      p.classList.remove('active');
      p.hidden = true;
    });
    btn.classList.add('active');
    const panel = document.getElementById(`tab-${btn.dataset.tab}`);
    panel.hidden = false;
    panel.classList.add('active');

    if (btn.dataset.tab === 'latest') {
      initLatest();
    }
  });
});

// ── Generic dropdown helper ──────────────────────────────────────────────────

function makeDropdown(inputEl, dropdownEl, getItems, onSelect) {
  let debounceTimer;

  inputEl.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      const q = inputEl.value.trim().toLowerCase();
      if (!q) { dropdownEl.hidden = true; return; }
      const items = await getItems(q);
      if (!items.length) { dropdownEl.hidden = true; return; }

      dropdownEl.innerHTML = '';
      items.slice(0, 20).forEach(item => {
        const div = document.createElement('div');
        div.className = 'dropdown-item';
        div.innerHTML = item.html;
        div.addEventListener('mousedown', e => {
          e.preventDefault();
          onSelect(item);
          inputEl.value = item.label;
          dropdownEl.hidden = true;
        });
        dropdownEl.appendChild(div);
      });
      dropdownEl.hidden = false;
    }, 150);
  });

  inputEl.addEventListener('blur', () => setTimeout(() => { dropdownEl.hidden = true; }, 200));
  inputEl.addEventListener('focus', () => { if (inputEl.value) inputEl.dispatchEvent(new Event('input')); });
}

// ── TAB 1: Latest ────────────────────────────────────────────────────────────

let latestData = null;
let latestLoaded = false;

async function initLatest() {
  if (latestLoaded) return;
  latestLoaded = true;

  document.getElementById('latest-loading').hidden = false;
  document.getElementById('latest-result').hidden = true;
  document.getElementById('latest-empty').hidden = true;

  latestData = await fetchLatest();

  document.getElementById('latest-loading').hidden = true;

  if (!latestData || !latestData.length) {
    document.getElementById('latest-empty').hidden = false;
    document.getElementById('latest-empty').textContent = 'No filings available yet.';
    return;
  }

  document.getElementById('latest-meta').textContent =
    `${latestData.length} most recent filings across all tracked stocks`;

  renderLatest('');

  document.getElementById('latest-filter').addEventListener('input', function () {
    renderLatest(this.value.toLowerCase().trim());
  });
}

function renderLatest(filter) {
  const rows = filter
    ? latestData.filter(f =>
        f.shareholder.toLowerCase().includes(filter) ||
        f.code.toLowerCase().includes(filter) ||
        (f.stock_name || '').toLowerCase().includes(filter)
      )
    : latestData;

  const tbody = document.getElementById('latest-tbody');
  const resultEl = document.getElementById('latest-result');
  const emptyEl = document.getElementById('latest-empty');

  if (!rows.length) {
    resultEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.textContent = 'No filings match your filter.';
    return;
  }

  emptyEl.hidden = true;
  resultEl.hidden = false;

  // Group consecutive rows by (code, filing_date) for rowspan display
  const groups = [];
  rows.forEach(f => {
    const key = `${f.code}|${f.filing_date}`;
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.filings.push(f);
    } else {
      groups.push({ key, code: f.code, stock_name: f.stock_name, filing_date: f.filing_date, filings: [f] });
    }
  });

  tbody.innerHTML = groups.map((g, gi) => {
    const span = g.filings.length;
    return g.filings.map((f, i) => `
      <tr class="${i === 0 && gi > 0 ? 'group-start' : ''}">
        ${i === 0 ? `
          <td rowspan="${span}" class="group-date">${fmtDateLong(g.filing_date)}</td>
          <td rowspan="${span}" class="group-stock">
            <span class="stock-code-badge" onclick="jumpToStock('${g.code}')">${g.code}</span>
            <span class="latest-stock-name">${g.stock_name || ''}</span>
          </td>
        ` : ''}
        <td class="latest-sh-cell" title="${f.shareholder}">${f.shareholder}</td>
        <td>${noticeTag(f.notice_type)}</td>
        <td class="num-col">${fmtPct(f.long_position_pct)}</td>
        <td class="muted-date">${fmtDateLong(f.relevant_event_date)}</td>
      </tr>
    `).join('');
  }).join('');
}

// ── TAB 2: By Stock ──────────────────────────────────────────────────────────

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
    if (!byName[h.name] || (h.filing_date || '') > (byName[h.name].filing_date || '')) {
      byName[h.name] = h;
    }
  });
  return Object.values(byName)
    .filter(h => (h.long_position_pct || 0) > 0)
    .map(h => ({
      name: h.name,
      long_position_pct: h.long_position_pct,
      long_position_shares: h.long_position_shares,
      filing_date: h.filing_date,
      entity_type: h.entity_type || 'corporate',
    }))
    .sort((a, b) => (b.long_position_pct || 0) - (a.long_position_pct || 0));
}

// View toggle
document.querySelectorAll('.view-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentView = btn.dataset.view;
    document.getElementById('view-shareholders').hidden = currentView !== 'shareholders';
    document.getElementById('view-timeline').hidden = currentView !== 'timeline';
    if (currentView === 'timeline' && currentStockData) {
      initStockTimeline();
    }
  });
});

async function stockItems(q) {
  const universe = await fetchUniverse();
  return universe
    .filter(s => s.code.includes(q) || s.name.toLowerCase().includes(q))
    .map(s => ({
      label: s.code,
      html: `<span class="item-code">${s.code}</span><span class="item-name">${s.name}</span><span class="item-mktcap">${fmtMktcap(s.mktcap_usd)}</span>`,
      code: s.code,
      name: s.name,
    }));
}

async function loadStock(code, name) {
  lastSelectedStock = { code, name };
  const data = await fetchDI(code);
  if (!data) {
    document.getElementById('stock-empty').hidden = false;
    document.getElementById('stock-result').hidden = true;
    document.getElementById('stock-empty').textContent = `No disclosure data available for ${code}. This stock has not been scraped yet.`;
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

  document.getElementById('stock-empty').hidden = true;
  document.getElementById('stock-result').hidden = false;

  // Stat cards + subheader always update
  document.getElementById('sh-code').textContent = data.code + ' · ';
  document.getElementById('sh-name').textContent = data.name;
  const totalPct = shareholders.reduce((s, sh) => s + (sh.long_position_pct || 0), 0);
  const latestDate = shareholders.reduce((d, sh) => (sh.filing_date || '') > d ? (sh.filing_date || '') : d, '');
  document.getElementById('sh-count-val').textContent = shareholders.length || '—';
  document.getElementById('sh-sum-val').textContent = shareholders.length ? totalPct.toFixed(1) + '%' : '—';
  document.getElementById('sh-date-val').textContent = fmtDateLong(latestDate) || '—';

  if (currentView === 'timeline') {
    initStockTimeline();
  } else {
    renderShareholdersList(shareholders);
  }
}


function renderShareholdersList(shareholders) {
  let rows = shareholders.filter(sh =>
    currentFilter === 'all' || sh.entity_type === currentFilter
  );

  if (currentSort === 'pct') rows.sort((a, b) => (b.long_position_pct || 0) - (a.long_position_pct || 0));
  else if (currentSort === 'name') rows.sort((a, b) => a.name.localeCompare(b.name));
  else if (currentSort === 'date') rows.sort((a, b) => (b.filing_date || '').localeCompare(a.filing_date || ''));

  const list = document.getElementById('shareholders-list');

  // Build latest-history lookup for notice badges
  const latestHistoryByName = {};
  (currentStockData?.history || []).forEach(h => {
    if (!latestHistoryByName[h.name] || (h.filing_date || '') > (latestHistoryByName[h.name].filing_date || '')) {
      latestHistoryByName[h.name] = h;
    }
  });

  if (!rows.length) {
    list.innerHTML = '<div style="text-align:center;color:var(--color-text-muted);padding:40px">No shareholders match the current filter.</div>';
    return;
  }

  const maxPct = Math.max(...rows.map(sh => sh.long_position_pct || 0), 1);

  const note = isHistoricalFallback
    ? `<div class="historical-note">No current substantial shareholders on record. Showing last reported holdings derived from filing history.</div>`
    : '';

  list.innerHTML = note + rows.map(sh => {
    const pct = sh.long_position_pct || 0;
    const barW = ((pct / maxPct) * 100).toFixed(1);
    const histEntry = latestHistoryByName[sh.name];
    const badge = histEntry ? noticeBadge(histEntry.notice_type) : '';

    return `<div class="sh-row">
      <div class="sh-name" title="${sh.name}">${sh.name}</div>
      <div class="sh-bar-wrap"><div class="sh-bar" style="width:${barW}%"></div></div>
      <div class="sh-pct">${fmtPct(pct)}</div>
      <div class="sh-shares">${fmtShares(sh.long_position_shares)} sh</div>
      ${badge}
      <div class="sh-date">${fmtDateLong(sh.filing_date)}</div>
    </div>`;
  }).join('');
}

makeDropdown(
  document.getElementById('stock-search'),
  document.getElementById('stock-dropdown'),
  stockItems,
  item => loadStock(item.code, item.name)
);

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    if (currentStockData) renderShareholdersList(currentShareholders);
  });
});

document.getElementById('stock-sort').addEventListener('change', e => {
  currentSort = e.target.value;
  if (currentStockData) renderShareholdersList(currentShareholders);
});

// ── Timeline (embedded in By Stock) ──────────────────────────────────────────

function initStockTimeline() {
  if (!currentStockData) return;
  const history = currentStockData.history || [];
  if (history.length) {
    const dates = history.map(h => h.relevant_event_date).filter(Boolean).sort();
    document.getElementById('tl-date-from').value = dates[0] || '';
    document.getElementById('tl-date-to').value = dates[dates.length - 1] || '';
  }
  renderTimeline();
}

function renderTimeline() {
  if (!currentStockData) return;
  const history = currentStockData.history || [];
  const shFilter = document.getElementById('tl-sh-filter').value.toLowerCase().trim();
  const dateFrom = document.getElementById('tl-date-from').value;
  const dateTo = document.getElementById('tl-date-to').value;

  let rows = history.filter(h => {
    if (shFilter && !h.name.toLowerCase().includes(shFilter)) return false;
    if (dateFrom && h.relevant_event_date < dateFrom) return false;
    if (dateTo && h.relevant_event_date > dateTo) return false;
    return true;
  });

  const tbody = document.getElementById('tl-tbody');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--color-text-muted);padding:30px">No filings match the current filters.</td></tr>';
    return;
  }

  tbody.innerHTML = rows.map(h => `
    <tr>
      <td>${h.relevant_event_date || '—'}</td>
      <td>${h.name}</td>
      <td>${noticeTag(h.notice_type)}</td>
      <td class="num-col">${fmtPct(h.long_position_pct)}</td>
      <td>${h.form_type || '—'}</td>
      <td>${h.filing_date || '—'}</td>
    </tr>
  `).join('');
}

['tl-sh-filter', 'tl-date-from', 'tl-date-to'].forEach(id => {
  document.getElementById(id).addEventListener('input', renderTimeline);
});

// ── TAB 3: By Shareholder ────────────────────────────────────────────────────

async function shareholderItems(q) {
  const idx = await fetchIndex();
  return Object.keys(idx)
    .filter(name => name.toLowerCase().includes(q))
    .map(name => ({
      label: name,
      html: `<span class="item-name">${name}</span><span class="item-mktcap">${idx[name].length} stock${idx[name].length !== 1 ? 's' : ''}</span>`,
      name,
      codes: idx[name],
    }));
}

async function loadShareholder(name, codes) {
  document.getElementById('sh-result').hidden = false;
  document.getElementById('sh-empty').hidden = true;
  document.getElementById('sh-result-name').textContent = name;

  const tbody = document.getElementById('sh-holdings-tbody');
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--color-text-muted);padding:20px">Loading…</td></tr>';

  const universe = await fetchUniverse();
  const uMap = Object.fromEntries(universe.map(s => [s.code, s]));

  const rows = await Promise.all(codes.map(async code => {
    const di = await fetchDI(code);
    if (!di) return null;
    const sh = (di.shareholders || []).find(s => s.name === name);
    if (!sh) return null;
    return { code, stockName: uMap[code]?.name || di.name, sh };
  }));

  const valid = rows.filter(Boolean).sort((a, b) => (b.sh.long_position_pct || 0) - (a.sh.long_position_pct || 0));

  if (!valid.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--color-text-muted);padding:20px">No current holdings found.</td></tr>';
    return;
  }

  tbody.innerHTML = valid.map(({ code, stockName, sh }) => `
    <tr>
      <td><span class="stock-code-badge" style="cursor:pointer" onclick="jumpToStock('${code}')">${code}</span></td>
      <td>${stockName}</td>
      <td class="num-col">${fmtPct(sh.long_position_pct)}</td>
      <td class="num-col">${fmtShares(sh.long_position_shares)}</td>
      <td>${sh.filing_date || '—'}</td>
    </tr>
  `).join('');
}

makeDropdown(
  document.getElementById('sh-search'),
  document.getElementById('sh-dropdown'),
  shareholderItems,
  item => loadShareholder(item.name, item.codes)
);

function jumpToStock(code) {
  document.querySelector('[data-tab="by-stock"]').click();
  const input = document.getElementById('stock-search');
  input.value = code;
  input.dispatchEvent(new Event('input'));
  setTimeout(() => {
    const first = document.querySelector('#stock-dropdown .dropdown-item');
    if (first) first.dispatchEvent(new MouseEvent('mousedown'));
  }, 300);
}

// ── TAB 4: Compare ───────────────────────────────────────────────────────────

const compareSelected = [];
const MAX_COMPARE = 5;

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
  el.innerHTML = compareSelected.map(s => `
    <div class="compare-chip">
      <span>${s.code} — ${s.name}</span>
      <button onclick="removeCompareStock('${s.code}')" title="Remove">×</button>
    </div>
  `).join('');
}

async function renderCompareMatrix() {
  const resultEl = document.getElementById('compare-result');
  const emptyEl = document.getElementById('compare-empty');

  if (compareSelected.length < 2) {
    resultEl.hidden = true;
    emptyEl.hidden = false;
    emptyEl.textContent = compareSelected.length === 0
      ? 'Add up to 5 stocks above to compare their shareholders side by side.'
      : 'Add at least one more stock to compare.';
    return;
  }

  resultEl.hidden = false;
  emptyEl.hidden = true;

  const allDI = await Promise.all(compareSelected.map(s => fetchDI(s.code)));

  const allNames = new Set();
  allDI.forEach(di => (di?.shareholders || []).forEach(sh => allNames.add(sh.name)));

  const matrix = {};
  allNames.forEach(name => { matrix[name] = {}; });
  allDI.forEach((di, i) => {
    const code = compareSelected[i].code;
    (di?.shareholders || []).forEach(sh => { matrix[sh.name][code] = sh.long_position_pct || 0; });
  });

  const sortedNames = [...allNames].sort((a, b) => {
    const maxA = Math.max(...Object.values(matrix[a]));
    const maxB = Math.max(...Object.values(matrix[b]));
    return maxB - maxA;
  });

  const codes = compareSelected.map(s => s.code);

  document.getElementById('compare-thead').innerHTML = `
    <tr>
      <th class="row-header">Shareholder</th>
      ${codes.map(c => `<th>${c}</th>`).join('')}
    </tr>`;

  document.getElementById('compare-tbody').innerHTML = sortedNames.map(name => `
    <tr>
      <td class="row-header">${name}</td>
      ${codes.map(c => {
        const pct = matrix[name][c];
        return pct
          ? `<td class="num-col ${heatClass(pct)}">${fmtPct(pct)}</td>`
          : `<td class="num-col cell-dash">—</td>`;
      }).join('')}
    </tr>
  `).join('');

  const totals = codes.map(c => {
    const di = allDI[codes.indexOf(c)];
    return (di?.shareholders || []).reduce((s, sh) => s + (sh.long_position_pct || 0), 0);
  });

  document.getElementById('compare-tfoot').innerHTML = `
    <tr>
      <td>Total disclosed</td>
      ${totals.map(t => `<td class="num-col">${t.toFixed(1)}%</td>`).join('')}
    </tr>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────

initLatest();
