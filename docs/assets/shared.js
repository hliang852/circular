'use strict';

// ── Data base path (each page sets window.CIRC_BASE before loading) ──
const CIRC_BASE = window.CIRC_BASE || '../data';

// ── Per-session cache ────────────────────────────────────────────────
const circCache = {};

async function circFetch(key, url) {
  if (circCache[key]) return circCache[key];
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    circCache[key] = await res.json();
    return circCache[key];
  } catch { return null; }
}

async function fetchUniverse() {
  return circFetch('universe', `${CIRC_BASE}/universe.json`);
}

async function fetchLastRun() {
  return circFetch('last_run', `${CIRC_BASE}/last_run.json`);
}

async function fetchLatestFilings() {
  return circFetch('latest_filings', `${CIRC_BASE}/latest_filings.json`);
}

async function fetchCAIndex() {
  return circFetch('ca_index', `${CIRC_BASE}/ca_index.json`);
}

async function fetchDI(code) {
  return circFetch(`di_${code}`, `${CIRC_BASE}/di/${code}.json`);
}

async function fetchCA(code) {
  return circFetch(`ca_${code}`, `${CIRC_BASE}/ca/${code}.json`);
}

async function fetchShareholdersIndex() {
  return circFetch('sh_index', `${CIRC_BASE}/shareholders_index.json`);
}

// ── Formatters ───────────────────────────────────────────────────────
function fmtShares(n) {
  if (!n) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return n.toLocaleString();
}

function fmtHKD(n) {
  if (!n) return '—';
  if (n >= 1e9) return `HK$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `HK$${(n / 1e6).toFixed(0)}M`;
  return `HK$${n.toLocaleString()}`;
}

function fmtPct(n) {
  if (n == null || n === 0) return '—';
  return n.toFixed(2) + '%';
}

function fmtCode(code) {
  return `${parseInt(code, 10)} HK`;
}

function fmtDateLong(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${parseInt(d)} ${months[parseInt(m) - 1]} ${y}`;
}

function noticeBadge(type) {
  const cls = (type || 'change').toLowerCase();
  const arrow = cls === 'increase' ? '↑' : cls === 'decrease' ? '↓' : '';
  return `<span class="notice-badge ${cls}">${arrow ? arrow + ' ' : ''}${type || 'Change'}</span>`;
}

function heatClass(pct) {
  if (!pct) return 'heat-0';
  if (pct < 5)  return 'heat-1';
  if (pct < 10) return 'heat-2';
  if (pct < 20) return 'heat-3';
  if (pct < 30) return 'heat-4';
  return 'heat-5';
}

// ── Header renderer ──────────────────────────────────────────────────
function renderHeader(module) {
  const base = window.CIRC_ROOT || '../';
  const code = new URLSearchParams(location.search).get('code') || '';

  const diHref  = code ? `${base}di/?code=${code}`  : `${base}di/`;
  const caHref  = code ? `${base}ca/?code=${code}`  : `${base}ca/`;
  const hubHref = base;

  const el = document.getElementById('circular-header');
  if (!el) return;

  const cmHref = `${base}capital-market/`;

  el.innerHTML = `
    <nav class="circ-header">
      <div class="circ-header-inner">
        <a href="${hubHref}" class="circ-brand">
          <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="8" cy="8" r="6.5"/>
            <path d="M8 4.5v3.5l2.5 1.5" stroke-linecap="round"/>
          </svg>
          Circular
        </a>
        <div class="circ-module-tabs">
          <a href="${caHref}" class="circ-tab ${module === 'ca' ? 'active' : ''}">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M8 2v2m0 8v2M2 8h2m8 0h2" stroke-linecap="round"/><circle cx="8" cy="8" r="3"/>
            </svg>
            Corporate Actions
          </a>
          <a href="${diHref}" class="circ-tab ${module === 'di' ? 'active' : ''}">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="8" cy="5.5" r="2.5"/>
              <path d="M2.5 13c0-3.038 2.462-5.5 5.5-5.5s5.5 2.462 5.5 5.5" stroke-linecap="round"/>
            </svg>
            Disclosure of Interests
          </a>
          <a href="${cmHref}" class="circ-tab ${module === 'capital-market' ? 'active' : ''}">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M2 13L6 7l3 4 2.5-5 2.5 5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            Capital Market
          </a>
        </div>
        <div class="circ-header-right">
          <div class="circ-search-wrap">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="6.5" cy="6.5" r="4.5"/>
              <path d="M10.5 10.5L14 14" stroke-linecap="round"/>
            </svg>
            <input class="circ-search" id="circ-global-search" type="text" placeholder="Search stock…" autocomplete="off">
          </div>
        </div>
      </div>
    </nav>
  `;

  // Wire global search
  const si = document.getElementById('circ-global-search');
  if (si) {
    si.addEventListener('keydown', async e => {
      if (e.key !== 'Enter') return;
      const q = si.value.trim().toLowerCase();
      if (!q) return;
      const universe = await fetchUniverse();
      if (!universe) return;
      const match = universe.find(s =>
        s.code === q.padStart(5, '0') ||
        s.name.toLowerCase().includes(q) ||
        fmtCode(s.code).toLowerCase().includes(q)
      );
      if (match) {
        // Navigate to current module with code, or DI if on hub
        const dest = module === 'ca' ? caHref.split('?')[0] : diHref.split('?')[0];
        location.href = `${dest}?code=${match.code}`;
      }
    });
  }
}

// ── Generic dropdown helper ──────────────────────────────────────────
function makeDropdown(inputEl, dropdownEl, getItems, onSelect) {
  let timer;
  inputEl.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = inputEl.value.trim().toLowerCase();
      if (!q) { dropdownEl.hidden = true; return; }
      const items = await getItems(q);
      if (!items || !items.length) { dropdownEl.hidden = true; return; }
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
