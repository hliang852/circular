# HKEX Disclosure of Interests Tracker — Project Plan

> **For Claude Code:** This document is the complete specification for the HKEX DI Tracker project. Build it top-down: scraper → data pipeline → GitHub Actions → frontend. All design decisions are documented here. Ask clarifying questions only when something is genuinely ambiguous.

---

## Project Overview

A GitHub Pages web app that scrapes HKEX's Disclosure of Interests (DI) portal for all stocks with market cap >$100M USD, stores the data as static JSON files in the repo, and serves an interactive frontend for exploring substantial shareholding data.

**No backend server required.** GitHub Actions handles scheduled scraping; GitHub Pages serves the static frontend; all data lives as committed JSON files.

---

## Repo Structure

```
circular/
├── .github/
│   └── workflows/
│       ├── scrape_nightly.yml       # Scrapes stocks with recent DI filings
│       └── update_universe.yml      # Weekly: refresh stock universe by market cap
├── scripts/
│   ├── build_universe.py            # Builds data/universe.json via yfinance
│   ├── scrape_di.py                 # Scrapes DI portal → data/di/{code}.json
│   └── build_index.py               # Builds data/shareholders_index.json
├── data/
│   ├── universe.json                # Master list of stocks above $100M USD mktcap
│   ├── shareholders_index.json      # Inverted index: shareholder → list of stocks
│   ├── last_run.json                # Metadata: timestamps, counts, errors
│   └── di/
│       ├── 00700.json               # Tencent DI data
│       ├── 09988.json               # Alibaba DI data
│       └── ...                      # One file per stock code
├── docs/                            # GitHub Pages root
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── requirements.txt
└── README.md
```

---

## Data Schemas

### `data/universe.json`
```json
[
  {
    "code": "00700",
    "name": "TENCENT HOLDINGS LTD",
    "mktcap_usd": 412000000000,
    "mktcap_hkd": 3213600000000,
    "last_updated": "2026-05-15"
  }
]
```
- `code` is always zero-padded to 5 digits (e.g. `"00700"`, not `"700"`)
- Sorted descending by `mktcap_usd`
- Refreshed weekly by `update_universe.yml`

---

### `data/di/{code}.json`
```json
{
  "code": "00700",
  "name": "TENCENT HOLDINGS LTD",
  "last_scraped": "2026-05-15T14:32:00Z",
  "shareholders": [
    {
      "name": "Naspers Limited / Prosus N.V.",
      "capacity": "Beneficial Owner",
      "entity_type": "corporate",
      "long_position_shares": 2387000000,
      "long_position_pct": 24.90,
      "short_position_shares": 0,
      "short_position_pct": 0.0,
      "relevant_event_date": "2026-03-12",
      "filing_date": "2026-03-15",
      "form_type": "Form 2",
      "notice_type": "Change"
    }
  ],
  "history": [
    {
      "name": "BlackRock Inc.",
      "long_position_pct": 6.10,
      "relevant_event_date": "2026-05-10",
      "filing_date": "2026-05-13",
      "form_type": "Form 2",
      "notice_type": "Change"
    }
  ]
}
```
- `shareholders` = current substantial shareholders only (≥5%)
- `history` = all historical filings, newest first, for timeline view
- `entity_type`: one of `"individual"`, `"corporate"`, `"fund"`
- `form_type`: `"Form 1"` (individual), `"Form 2"` (corporate/trust), `"Form 3"` (manager), `"Form 3A"` (associated entity)

---

### `data/shareholders_index.json`
Inverted index for "By Shareholder" tab — built by `build_index.py` after scraping.
```json
{
  "BlackRock Inc.": ["00700", "09988", "01299", "00005"],
  "Vanguard Group": ["00700", "09988"],
  "Naspers Limited / Prosus N.V.": ["00700"]
}
```

---

## Scripts

### `scripts/build_universe.py`

**Purpose:** Fetch all HKEX-listed stocks, filter by market cap >$100M USD, output `data/universe.json`.

**Approach:**
1. Use `yfinance` to get market cap data. HKEX stock tickers on Yahoo Finance use the format `0700.HK` (no leading zero padding beyond what Yahoo expects).
2. Pull the full list of HKEX stock codes from the HKEX website or a maintained CSV — there are ~2,686 listed stocks as of end-2025.
3. Filter to market cap > $100,000,000 USD. Expect ~600–900 stocks to pass.
4. Zero-pad codes to 5 digits for DI portal compatibility.
5. Save to `data/universe.json`.

**Key dependency:** `yfinance`, `pandas`

**Rate limiting:** yfinance handles this, but batch in groups of 50 tickers with a 1s delay between batches to avoid throttling.

**Fallback:** If yfinance fails for a ticker, log it to `data/last_run.json` under `errors` and skip.

---

### `scripts/scrape_di.py`

**Purpose:** For each stock in `data/universe.json`, scrape the DI portal and write/update `data/di/{code}.json`.

**Target URL:** `https://di.hkex.com.hk/di/NSSrchCorp.aspx`

**Method:** POST request with form data. The portal uses ASP.NET WebForms — every request needs `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, and `__EVENTVALIDATION` tokens from a prior GET request. Approach:
1. GET the search page to capture ASP.NET state tokens (parse with BeautifulSoup).
2. POST with the stock code to get results.
3. Parse the results table.

**Critical headers to include:**
```python
headers = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Referer": "https://di.hkex.com.hk/di/NSSrchCorp.aspx",
    "Content-Type": "application/x-www-form-urlencoded",
}
```

**Fields to extract from the results table:**
- Shareholder name
- Capacity (column header varies: "Beneficial Owner", "Investment Manager", etc.)
- Long position: number of shares + % of class
- Short position: number of shares + % of class
- Relevant event date
- Date of filing
- Form type
- Notice type (initial disclosure / change / cease)

**Scraping mode:**
- `--mode incremental` (default): Only scrape stocks that appear in the daily DI summary at `https://di.hkex.com.hk/di/NSMSumMenu.aspx`. Check this first, extract stock codes from today's filings, scrape only those.
- `--mode full`: Scrape all stocks in `universe.json`. Used for initial population and weekly full refresh.
- `--code 00700`: Scrape a single stock (for testing).

**Output:** Merge new filings into existing `data/di/{code}.json`. Don't overwrite history — append new entries to `history[]` array. Update `shareholders[]` to reflect current state.

**Rate limiting:** 1 request per 2 seconds. Randomise delay between 1.5–3s to avoid pattern detection.

**Error handling:** On HTTP error or parse failure, log to `data/last_run.json` and continue. Don't crash the whole run.

---

### `scripts/build_index.py`

**Purpose:** Read all `data/di/*.json` files and build `data/shareholders_index.json`.

**Logic:**
- For each stock file, iterate `shareholders[]`
- Normalise shareholder names (strip extra whitespace, title-case)
- Build inverted map: `shareholder_name → [stock_codes]`
- Sort each list by the shareholder's % holding (highest first)
- Save to `data/shareholders_index.json`

Run this after every scraping run.

---

## GitHub Actions Workflows

### `.github/workflows/scrape_nightly.yml`

```yaml
name: Nightly DI Scrape
on:
  schedule:
    - cron: '0 22 * * 1-5'   # 22:00 UTC = 06:00 HKT next day (after market close filings)
  workflow_dispatch:           # Allow manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python scripts/scrape_di.py --mode incremental
      - run: python scripts/build_index.py
      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/
          git diff --staged --quiet || git commit -m "data: nightly DI scrape $(date -u +%Y-%m-%d)"
          git push
```

### `.github/workflows/update_universe.yml`

```yaml
name: Weekly Universe Update
on:
  schedule:
    - cron: '0 2 * * 0'     # Sunday 02:00 UTC
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python scripts/build_universe.py
      - name: Commit updated universe
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/universe.json
          git diff --staged --quiet || git commit -m "data: weekly universe refresh $(date -u +%Y-%m-%d)"
          git push
```

---

## Frontend (`docs/`)

Single-page app served by GitHub Pages. No build step, no framework — vanilla HTML/CSS/JS only, so it works directly from the `docs/` folder.

**Enable GitHub Pages:** Repo Settings → Pages → Source: Deploy from branch `main`, folder `/docs`.

### Four Views (tabs)

**1. By Stock**
- Search input: stock code or name (filters `universe.json` client-side)
- On selection: fetch `data/di/{code}.json`
- Display: shareholder list sorted by `long_position_pct` desc
- Each row: name, horizontal bar (width = % of float), %, share count, change tag (↑/↓/—), filing date
- Filter chips: All / Individual / Corporate / Fund
- Sort control: by %, by name, by filing date
- Summary metrics: total shareholders, sum of disclosed %, latest filing date

**2. By Shareholder**
- Search input: shareholder name (filters `shareholders_index.json`)
- On selection: show all stocks they hold, fetch each `data/di/{code}.json` for details
- Table: stock name, code, long %, shares, change tag, filing date

**3. Compare Stocks**
- Multi-select up to 5 stock codes
- Matrix table: shareholders (rows) × stocks (columns), cells show `long_position_pct`
- "—" for no disclosable interest
- Footer row: total disclosed %
- Optional: heatmap colour scale on cells

**4. Timeline**
- Select stock + optional shareholder filter + date range
- Chronological list of all filings from `history[]`
- Each entry: date, shareholder, action (Increase/Decrease/Initial/Ceased), from % → to %, form type
- Stretch goal: line chart of % over time using Chart.js (CDN, no install)

### Data Loading Strategy

```javascript
// Cache fetched files in memory to avoid re-fetching
const cache = {};

async function fetchDI(code) {
  if (cache[code]) return cache[code];
  const res = await fetch(`../data/di/${code}.json`);
  cache[code] = await res.json();
  return cache[code];
}

async function fetchUniverse() {
  if (cache['universe']) return cache['universe'];
  const res = await fetch('../data/universe.json');
  cache['universe'] = await res.json();
  return cache['universe'];
}
```

### Styling

- No external CSS framework. CSS custom properties for theming.
- Responsive: works on mobile (single-column) and desktop (full table layout).
- Colour coding: green (#3B6D11 on #EAF3DE) for increases, red (#A32D2D on #FCEBEB) for decreases, neutral grey for no change.

---

## `requirements.txt`

```
requests==2.31.0
beautifulsoup4==4.12.3
lxml==5.2.1
yfinance==0.2.40
pandas==2.2.2
```

---

## Key Constraints & Gotchas

1. **ASP.NET VIEWSTATE:** Every POST to the DI portal needs fresh state tokens from a prior GET. The scraper must do GET → parse tokens → POST per stock.

2. **5-digit zero-padded codes:** The DI portal expects `00700`, not `700`. Yahoo Finance uses `0700.HK`. Always normalise to 5-digit for storage and DI requests.

3. **~600–900 stocks in universe:** A full scrape run will take ~30–45 minutes at 2s/request. GitHub Actions has a 6-hour job limit — this is fine.

4. **GitHub Actions permissions:** The workflow needs write permission to push data commits. Set `permissions: contents: write` in the workflow YAML, or use a Personal Access Token stored as a repo secret.

5. **HKEX DI portal blocks:** If the scraper gets blocked (429 / redirect to CAPTCHA), increase delay and retry with exponential backoff. Consider adding a random User-Agent rotation.

6. **Initial full scrape:** On first run, trigger `update_universe.yml` first, then manually trigger `scrape_nightly.yml` with `--mode full` via `workflow_dispatch`. This will take ~30–45 mins.

7. **Data size:** At ~600 stocks × ~5KB per JSON file, `data/di/` will be ~3MB total. Well within GitHub's limits.

8. **GitHub Pages base URL:** If the repo is `username/circular`, the site will be at `https://username.github.io/circular/`. Adjust any absolute paths accordingly.

---

## Build Order for Claude Code

Build in this order:

1. `requirements.txt`
2. `scripts/build_universe.py` — test with 5 stocks first
3. `scripts/scrape_di.py` — test with `--code 00700` first, then `--mode incremental`
4. `scripts/build_index.py`
5. `.github/workflows/update_universe.yml`
6. `.github/workflows/scrape_nightly.yml`
7. `data/universe.json` — seed with 10 real stocks for frontend dev
8. `data/di/00700.json` — seed with real scraped data for frontend dev
9. `docs/index.html` + `docs/app.js` + `docs/styles.css`
10. `README.md`

---

## Success Criteria

- [ ] `build_universe.py` produces a valid `universe.json` with >500 stocks
- [ ] `scrape_di.py --code 00700` produces a valid `data/di/00700.json`
- [ ] `scrape_di.py --mode incremental` runs without crashing, commits only changed files
- [ ] GitHub Actions workflows trigger on schedule and push data commits
- [ ] Frontend loads in browser, all four tabs functional with real data
- [ ] Frontend works on mobile (responsive)
- [ ] GitHub Pages site is live at `https://{username}.github.io/circular/`
