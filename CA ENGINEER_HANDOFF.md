# Circular — Corporate Actions Module
## Engineer Handoff Document

> **Status:** Prototype v10 · Last updated: May 2026  
> **Purpose:** Full handoff to engineering team for production implementation

---

## 1. What This Module Is

Circular is a GitHub Pages–hosted tracker for HKEX corporate actions — specifically share repurchase programmes. It scrapes public data from HKEXnews and the HKEX portal, stores it as static JSON, and serves a clean frontend that answers three questions analysts care about most:

1. **Is this company aggressively buying back shares, and at what price?**
2. **Is it still buying when the stock is below its own cost basis?**
3. **Which companies are about to exhaust their mandate — or likely to renew it?**

The prototype is fully interactive HTML/JS with mock data. No backend. No auth. No database. Static JSON on GitHub Pages.

---

## 2. Current Feature Inventory

### 2a. Implemented & Working in Prototype

| Feature | Status | Notes |
|---|---|---|
| Corporate Actions home page (philosophy) | ✅ Done | Static content, entry point for new users |
| By Stock view — full buyback detail | ✅ Done | Demo stock: Tencent 700 HK |
| Stock hero card (name, code, active badge, consistency score, signal) | ✅ Done | Signal badge computes from DI + VWAP criteria |
| Mandate progress bar (% of mandate used) | ✅ Done | Collapsed by default, progress bar visible |
| Mandate expanded stats (3 groups: issued capital / authority / float-adj.) | ✅ Done | |
| Free float adjustment | ✅ Done | float-adj. repurchased = issued% ÷ free_float |
| Probability of mandate renewal gauge | ✅ Done | Purple gradient, distinct from mandate green |
| YTD VWAP paid card with underwater flag | ✅ Done | Shows "still buying" when active month = true |
| 12-month price + buyback chart | ✅ Done | Dual axis, blackout bands, VWAP dashed line |
| Equity event markers (placing ▼, CB ◆) | ✅ Done | PDF links on event pills |
| Blackout period visualisation | ✅ Done | Grey bands + ⛔ marker, "Next blackout" note |
| Monthly return filings table | ✅ Done | 9 cols incl. % of monthly volume |
| Capital return summary + DI context | ✅ Done | Merged into one insight box below chart |
| Buyback economics strip (yield, dividend, total return, net capital return) | ✅ Done | Always visible in hero card |
| League Table with sort + filter | ✅ Done | Sort: YTD / % Issued / Mandate Used / Last Filing |
| Last Session Buyback view | ✅ Done | Sort: Consideration / Shares / % Vol; column header highlight |
| Ideas tab — Conviction Buys strategy 🎯 | ✅ Done | Screens: price < VWAP, CS ≥ 4, active 30d |
| Ideas tab — Mandate Renewers strategy 🔄 | ✅ Done | Screens: AGM ≤ 90d, prob ≥ 65%, CS ≥ 3 |
| Signal grades (Strong / Moderate) | ✅ Done | Strong = company + DI buying; Moderate = company only |
| Clickable tickers → By Stock navigation | ✅ Done | All tables; flashes hero card on arrival |
| Consistency score badge (1–5 stars) | ✅ Done | Colour-coded: green=4-5, amber=3, red=1-2 |
| Calendar view — results & AGM dates | ✅ Done | Month grid, event dots, click to expand |
| AI chatbot (Anthropic API) | ✅ Done | Interprets questions, auto-navigates to section |
| Info tooltips on key metrics | ✅ Done | JS-wired (not CSS :hover — works inside `<details>`) |
| Responsive layout | ✅ Done | 2-col cards on mobile, horizontal scroll on tables |

### 2b. Stubbed / Prototype-Only

| Feature | What's Stubbed | Production Approach |
|---|---|---|
| Stock data | Only Tencent has full data; all other stocks use league array | Fetch `data/buybacks/{code}.json` on stock selection |
| Chatbot knowledge | Claude receives mock descriptions of data | In production, inject real fetched JSON into context |
| PDF links | Point to HKEXnews title search | Should deep-link to specific filing document URL from scraper |
| DI link | `href="#"` placeholder | Link to `data/di/{code}.json` viewer in main DI tab |
| Blackout dates | Hardcoded estimate (~30 days before results) | Parse actual results announcement dates from HKEXnews |
| Next results date | Estimated | Scrape from HKEXnews; fall back to "— unavailable yet —" |
| Free float data | Hardcoded (58% for Tencent) | Source from HKEX listed company info or Bloomberg fallback |
| Calendar events | Mock data for May–July 2025 | Pull from `data/buybacks_index.json` + HKEXnews AGM filings |
| Signal on By Stock | Hardcoded "Strong" for Tencent | Compute dynamically from `league` data on stock load |

---

## 3. Data Architecture

### File structure (production)

```
circular/
├── .github/workflows/
│   ├── scrape_nightly.yml          # Mon–Fri 22:00 UTC — DI incremental
│   ├── scrape_buybacks.yml         # Mon–Fri 23:30 UTC — buyback incremental
│   └── update_universe.yml         # Sun 02:00 UTC — universe refresh
├── scripts/
│   ├── build_universe.py           # yfinance → data/universe.json
│   ├── scrape_di.py                # DI portal → data/di/*.json
│   ├── scrape_buybacks.py          # HKEXnews → data/buybacks/*.json
│   ├── build_index.py              # DI inverted index
│   └── build_buybacks_index.py     # Buyback league table index
├── data/
│   ├── universe.json               # ~700 stocks > $100M USD mktcap
│   ├── shareholders_index.json     # DI inverted index
│   ├── buybacks_index.json         # League table index
│   ├── last_run.json               # Scrape metadata
│   ├── di/{code}.json              # Per-stock DI data
│   └── buybacks/{code}.json        # Per-stock buyback data (schema below)
└── docs/
    ├── index.html                   # DI tracker (existing)
    ├── corporate-actions.html       # This module (v10)
    ├── app.js
    └── styles.css
```

### `data/buybacks/{code}.json` schema

```json
{
  "code": "00700",
  "name": "Tencent Holdings Ltd.",
  "exchange_code": "700 HK",
  "last_updated": "2025-05-17",
  "free_float_pct": 58.0,
  "consistency_score": 4,
  "signal": "strong",
  "mandate": {
    "pct": 10.0,
    "shares_authorised": 956_600_000,
    "shares_used_ytd": 156_200_000,
    "pct_used_of_issued": 1.63,
    "pct_used_of_mandate": 16.3,
    "pct_remaining_of_issued": 8.37,
    "pct_remaining_of_mandate": 83.7,
    "agm_date": "2025-05-14",
    "expiry_note": "Earlier of 2026 AGM or 12 months from approval",
    "circular_url": "https://www1.hkexnews.hk/...",
    "renewal_probability": 82
  },
  "summary": {
    "ytd_shares": 156_200_000,
    "ytd_consideration_hkd": 52_340_000_000,
    "ytd_pct_of_issued": 1.63,
    "ytd_pct_of_float": 2.81,
    "ytd_vwap_hkd": 335.1,
    "current_price_hkd": 321.0,
    "vwap_underwater": true,
    "still_active": true,
    "buyback_yield_annualised": 4.9,
    "dividend_yield": 1.1,
    "total_return_yield": 6.0,
    "net_capital_return_ytd_hkd": 27_100_000_000,
    "programme_active": true
  },
  "monthly_returns": [
    {
      "period": "2025-05",
      "filing_date": "2025-06-06",
      "filing_url": "https://www1.hkexnews.hk/...",
      "shares_repurchased": 16_600_000,
      "consideration_hkd": 5_380_000_000,
      "price_high": 328.6,
      "price_low": 309.8,
      "monthly_traded_volume": 398_000_000,
      "cum_ytd_pct_of_issued": 1.00,
      "days_active": 9,
      "is_blackout": false
    }
  ],
  "issuances": [
    {
      "date": "2024-07-08",
      "type": "placing",
      "label": "Top-up Placing",
      "shares": 50_000_000,
      "consideration_hkd": 16_400_000_000,
      "price_per_share": 328.0,
      "filing_url": "https://www1.hkexnews.hk/..."
    }
  ],
  "results_dates": [
    { "type": "interim", "date": "2025-08-14", "filing_url": null }
  ]
}
```

### `data/buybacks_index.json` (league table + ideas screening)

```json
[
  {
    "code": "00700",
    "name": "Tencent Holdings Ltd.",
    "exchange_code": "700 HK",
    "ytd_consideration_hkd": 52_340_000_000,
    "ytd_pct_of_issued": 1.63,
    "mandate_pct_used": 16.3,
    "last_filing": "2025-05-15",
    "programme_active": true,
    "free_float_pct": 58,
    "consistency_score": 4,
    "signal": "strong",
    "vwap_hkd": 335.1,
    "current_price_hkd": 321.0,
    "buyback_yield": 4.9,
    "agm_date": "2025-05-14",
    "renewal_probability": 82,
    "last_session": {
      "date": "2025-05-15",
      "shares": 840_000,
      "daily_volume": 26_200_000,
      "price_high": 322.4,
      "price_low": 318.8,
      "consideration_hkd": 271_000_000
    }
  }
]
```

---

## 4. Scraping Architecture

### Data Source 1 — Monthly Return Filings
- **URL:** `https://www1.hkexnews.hk/search/titlesearch.xhtml`
- **Method:** GET JSON API (no VIEWSTATE unlike DI portal)
- **Filter:** Headline category = "Announcement pursuant to Code on Share Buy-backs"
- **Parse:** `pdfplumber` to extract daily breakdown table from PDF
- **Frequency:** Nightly incremental (check for new filings today)

### Data Source 2 — Mandate Circulars (AGM)
- **URL:** Same HKEXnews title search
- **Filter:** Titles containing "REPURCHASE MANDATE" or "EXPLANATORY STATEMENT"
- **Parse:** Regex on PDF text for mandate % (see PLANNING doc)
- **Frequency:** Monthly full refresh (AGM season: April–June)

### Data Source 3 — Equity Issuances
- **URL:** Same HKEXnews title search
- **Filter:** Headline categories: Placing, Issue of Shares under General/Specific Mandate, Rights Issue, Open Offer, Issue of Convertible Securities
- **Parse:** pdfplumber — shares, price, gross proceeds from first 2 pages
- **Frequency:** Nightly (event-driven)

### Data Source 4 — Trading Volume
- **Primary:** HKEX Securities Statistics Archive (downloadable CSV/Excel)
- **Fallback:** `yfinance` daily volume
- **Used for:** "% of daily vol" column in Last Session; monthly vol column in monthly table
- **Frequency:** Daily

### Rate limiting
- Randomised 1.5–3s delay between requests
- Extra 2s after each PDF download
- Exponential backoff on 429; failures logged to `data/last_run.json`

---

## 5. Key Design Decisions & Rationale

### Why `details`/`summary` for mandate card
The mandate stats are analytically important but not the first thing a user needs. Collapsed by default forces the page to lead with the chart (visual context) before the numbers (detail). Progress bar always visible in collapsed state ensures the user isn't missing the headline signal.

### Why the mandate bar shows % of mandate used (not % of issued capital)
Early versions showed "1.63% used" which confused users — it looked like the bar should fill to 100% of issued capital. Changed to "16.3% of mandate used" so bar and label are on the same scale. The issued-capital figures live in the expanded section.

### Why `overflow:hidden` was removed from the mandate `<details>` element
CSS `:hover` tooltips don't work inside `<summary>` elements reliably. JS-wired tooltips were added instead, but they also failed when `overflow:hidden` was clipping the popup (which renders above the card). Removed `overflow:hidden`; border-radius still applies correctly.

### Why the probability bar is purple → blue (not green → blue)
The mandate bar is green → blue. Two identical gradients adjacent to each other were visually indistinguishable. Purple → blue is in-palette (matches the DI accumulation flag colour) and clearly distinct.

### Why sort controls appear below filter chips in League Table
User mental model: first choose the universe (All / Active / >HK$5B), then decide how to rank within it. Filter chips read as "what am I looking at", sort as "how do I order it". Swapping their order matched this hierarchy.

### Why the chatbot auto-navigates rather than just answering
The primary UX goal is getting users to the right data fast. Text answers alone duplicate what the tables already show. Auto-navigation + brief answer is more efficient for an analyst audience.

### Why `overflow-x: auto` on tables rather than hiding columns by default
Column toggles were considered but add UI complexity. Horizontal scroll is conventional for data tables on desktop. On mobile, the most important columns (Stock, Consideration, Signal) appear first in the DOM, so they're visible before scrolling.

---

## 6. Error Log & Idea Trash Bin

### Things we tried that didn't work

| What was tried | Why it was removed / rejected |
|---|---|
| CSS `:hover` tooltips inside `<summary>` | Browsers intercept mouse events on `<summary>` differently; tooltips wouldn't show |
| Showing `overflow:hidden` on `<details>` | Clipped tooltips that extended above the card boundary |
| "16.3% authority used" + "8.37% headroom" pills in collapsed mandate summary | Redundant — same data already in the hero card one row above. Removed on user feedback. |
| Sub-tabs for Ideas inside League Table | Confused the hierarchy. Ideas is now a top-level view, not nested inside League Table |
| Dual-coloured gradient bars both green → blue | Two identical gradients adjacent to each other were visually indistinguishable |
| Signal label with explanation in table cell ("Strong — company + DI both buying") | Made the Signal column too wide; moved explanation to table footnote |
| Percentage labels showing "1.63% used" on mandate bar | Confused users — "why isn't it 100%?" Changed to mandate-authority framing (16.3% of mandate) |

### Ideas that were explored but deferred

| Idea | Status | Reason deferred |
|---|---|---|
| Daily breakdown chart (per-day volume within month) | Deferred | Requires daily data extraction from PDFs — high parsing complexity |
| Mandate headroom alert (GitHub Issue when < 2% remains) | Deferred | Needs notification infrastructure |
| CB conversion tracking | Deferred | Requires separate "Conversion of Securities" headline category monitoring |
| Placing discount analysis (price vs last close at announcement) | Deferred | Interesting but needs price data at announcement time, not just current |
| Fuse.js client-side search index | Deferred | Current linear filter on universe.json is fast enough at ~700 stocks |
| Southbound Connect flows (HK investors into mainland stocks) | Deferred | Out of scope for HK-listed tracker |
| Short selling turnover integration | Deferred | Planned for v2 after buyback module is stable in production |

---

## 7. Production Implementation Guide

### Step 1: Environment setup
```bash
git clone https://github.com/YOUR_USERNAME/circular.git
cd circular
pip install -r requirements.txt   # includes pdfplumber, yfinance, requests, beautifulsoup4
```

### Step 2: Seed initial data
```bash
# Build universe (top ~700 stocks by market cap)
python scripts/build_universe.py

# Full buyback scrape (takes 30–45 min at rate limit)
python scripts/scrape_buybacks.py --mode full

# Build league index
python scripts/build_buybacks_index.py

# Verify output
ls data/buybacks/ | wc -l   # expect ~600–700 files
cat data/buybacks/00700.json | python -m json.tool | head -40
```

### Step 3: Enable GitHub Actions
1. Repo Settings → Actions → General → Workflow permissions → **Read and write**
2. Manually trigger `update_universe.yml` via workflow_dispatch
3. Manually trigger `scrape_buybacks.yml` with `mode: full`
4. Verify data committed to `data/buybacks/` directory

### Step 4: Deploy frontend
1. Repo Settings → Pages → Source: `main` branch, `/docs` folder
2. Copy `corporate-actions.html` (v10) into `docs/`
3. Update all `data/` fetch paths to use `https://YOUR_USERNAME.github.io/circular/data/`

### Step 5: Wire live data into frontend
Replace the hardcoded `league` array in the JS with a fetch:
```javascript
async function loadLeague() {
  const res = await fetch('/data/buybacks_index.json');
  return res.json();
}

async function loadStock(code) {
  const res = await fetch(`/data/buybacks/${code}.json`);
  return res.json();
}
```

### Step 6: Chatbot API key
The chatbot uses the Anthropic API. In the prototype, the API key is handled by the claude.ai artifact environment. In production:
- Create an Anthropic API key
- Store as GitHub secret `ANTHROPIC_API_KEY`
- The frontend currently calls the API directly — for production, route through a simple serverless function (Cloudflare Worker or Vercel Edge Function) to avoid exposing the key in client JS
- Alternatively, use a public-facing Claude API proxy with rate limiting

### Step 7: Chatbot production prompt
The chatbot system prompt should be updated in production to inject real stock data:
```javascript
const systemPrompt = `
You are a navigation assistant for Circular, an HKEX Corporate Actions tracker.
Current data as of ${new Date().toLocaleDateString()}:

Available stocks: ${leagueData.map(s => `${s.name} (${s.exchange_code})`).join(', ')}

Conviction Buy signals today: ${convictionBuys.map(s => s.name).join(', ')}
Mandate Renewers: ${mandateRenewers.map(s => `${s.name} (AGM ${s.agm_date})`).join(', ')}

[rest of system prompt...]
`;
```

### Step 8: Free float data
Free float is not available from HKEX directly. Options in priority order:
1. **HKEX Listed Company Search** — scrape "Stock Summary" page for each stock; free float sometimes listed
2. **Annual Report** — disclosed in the corporate governance section; scrape HKEXnews annual report PDFs
3. **yfinance** — `ticker.info['floatShares'] / ticker.info['sharesOutstanding']` (not always reliable for HK)
4. **Manual seed file** — `data/free_float.json` with ~50 largest stocks manually populated; update quarterly

---

## 8. Open Questions for Engineering

1. **Chatbot API exposure:** Direct client-side Anthropic API calls work in prototype. In production, do we want a proxy to hide the key? What rate limit is acceptable per user?

2. **PDF parsing failure rate:** Some Monthly Return PDFs are image-based (scanned). What % of filings is this? Fallback is to store filing metadata only. Engineering should test on a sample of 100 filings.

3. **Daily volume data latency:** HKEX Securities Statistics are published the next trading day. The "Last Session Buyback" view will show D-1 volume data. Is this acceptable, or should we use intraday volume from a real-time source?

4. **Stock price for VWAP comparison:** Current price in the prototype is hardcoded. In production, fetch from `yfinance` at scrape time and store in `buybacks_index.json`. Refresh frequency: daily (nightly scrape) is sufficient for this use case.

5. **Calendar results dates:** Some companies announce results dates only 2–3 weeks in advance. How far forward should the calendar look? Suggest 6 months with clear "date not yet announced" state.

6. **Mandate renewal probability model:** Currently a heuristic (4 signals, each 0–25 points). Should we train a simple logistic regression on historical HK mandate renewal data? Suggest collecting 3 years of historical renewals as a backlog task.

7. **DI deep-link integration:** The "View [Stock] DI filings →" link currently points to `#`. This needs to link to the DI tracker's By Stock view with the stock pre-selected. Coordinate with DI tracker team on URL param format (e.g. `?stock=00700`).

8. **Ideas screening refresh:** Should Conviction Buys and Mandate Renewers re-run automatically when data updates (nightly), or only on page load? Suggest nightly cron to pre-compute and store in `data/ideas_cache.json` for instant load.

---

## 9. Dependency Versions

| Package | Version | Purpose |
|---|---|---|
| Python | 3.11 | Scraping runtime |
| pdfplumber | ≥0.10.3 | PDF table extraction |
| yfinance | ≥0.2.28 | Market cap + price data |
| requests | ≥2.31 | HTTP scraping |
| beautifulsoup4 | ≥4.12 | HTML parsing (DI portal) |
| Chart.js | 4.4.1 | Frontend charting (CDN) |
| Anthropic API | claude-sonnet-4-5 | Chatbot (claude.ai artifact env) |

---

## 10. Contacts & Context

- **Project context:** Personal research tool → evaluating expansion to team/client use
- **Primary analyst persona:** Hong Kong equity analyst, familiar with HKEX filings, uses Bloomberg/FactSet for price data but finds buyback tracking poor on existing platforms
- **Monetisation hypothesis:** Buyback signal layer as a paid add-on to existing DI tracker; screener (Conviction Buys + Mandate Renewers) as the core value proposition
- **Design principles:** Dark-mode GitHub-style aesthetic; data density is high but progressive disclosure (collapsed sections, tooltips) manages cognitive load; every metric explains itself on hover
- **Key competitor gap:** Bloomberg surfaces buyback data but not: mandate headroom, float-adjusted impact, VWAP floor as price support level, or DI accumulation correlation. These are Circular's differentiators.
