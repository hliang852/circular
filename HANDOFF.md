# Circular — Project Handoff

*Last updated: 17 May 2026*

---

## What is this?

**Circular** is a static web app that makes HKEX substantial shareholder disclosures explorable. It scrapes the [HKEX Disclosure of Interests (DI) portal](https://di.hkex.com.hk) for every stock above $100M USD market cap, stores the data as JSON files committed to the repo, and serves an interactive frontend from GitHub Pages.

There is **no backend server**. GitHub Actions handles scheduled scraping; GitHub Pages serves the frontend; all data lives as JSON files in `docs/data/`.

**Local preview:** `python3 -m http.server 8765 --directory docs` → [http://localhost:8765](http://localhost:8765)

---

## Current Status

| Item | Status |
|---|---|
| Scraper (`scrape_di.py`) | Done — working, tested |
| Universe builder (`build_universe.py`) | Done — 1,359 stocks above $100M USD |
| Index builder (`build_index.py`) | Done |
| GitHub Actions workflows | Written, not yet enabled |
| Frontend (`docs/`) | Done — 4 tabs fully functional |
| Full DI scrape | **Not done** — only 27 of 1,359 stocks scraped |
| GitHub Pages | **Not enabled** |

The site works correctly today; it just has thin data coverage. Completing the full scrape and enabling GitHub Pages are the two remaining steps before it is usable in production.

---

## File Tree

```
circular/
├── .github/workflows/
│   ├── scrape_nightly.yml       # Weeknight scrape — stocks with same-day filings
│   └── update_universe.yml      # Sunday — refresh stock universe by market cap
│
├── scripts/
│   ├── build_universe.py        # Builds docs/data/universe.json via yfinance
│   ├── scrape_di.py             # Scrapes DI portal → docs/data/di/{code}.json
│   └── build_index.py           # Builds shareholders_index.json + latest_filings.json
│
├── docs/                        # GitHub Pages root (everything served from here)
│   ├── index.html               # Circular home page (tool directory)
│   ├── app.js                   # All frontend logic (~500 lines, vanilla JS)
│   ├── styles.css               # All styles (~550 lines, CSS custom properties)
│   ├── hkex/
│   │   └── index.html           # HKEX sub-page (loads app.js + styles.css from parent)
│   └── data/
│       ├── universe.json        # 1,359 stocks, sorted by market cap desc
│       ├── shareholders_index.json  # Inverted index: shareholder name → [stock codes]
│       ├── latest_filings.json  # Top 30 most recent filings across all stocks
│       ├── last_run.json        # Scrape run metadata + errors
│       └── di/
│           └── {code}.json      # One file per scraped stock (27 exist today)
│
├── requirements.txt
├── PLANNING.md                  # Original product spec (now partially superseded)
├── TO-DO.md                     # Remaining tasks checklist
└── HANDOFF.md                   # This file
```

> **Note:** `data/` at the repo root is a leftover from early dev — it is not used. All live data is in `docs/data/`.

---

## Data Schemas

### `docs/data/universe.json`
Master list of all HKEX stocks above $100M USD market cap. 1,359 entries today.

```json
[
  {
    "code": "00700",
    "name": "TENCENT HOLDINGS LIMITED",
    "mktcap_usd": 528774460127,
    "mktcap_hkd": 4124440788992,
    "last_updated": "2026-05-16"
  }
]
```

- Codes are always **5-digit zero-padded** (`"00700"` not `"700"`)
- Sorted by `mktcap_usd` descending
- Refreshed weekly by `update_universe.yml`

---

### `docs/data/di/{code}.json`
One file per scraped stock. Contains current shareholders + full filing history.

```json
{
  "code": "00700",
  "name": "TENCENT HOLDINGS LIMITED",
  "last_scraped": "2026-05-16T07:47:06Z",
  "shareholders": [
    {
      "name": "MIH TC Holdings Limited",
      "capacity": "Beneficial Owner",
      "entity_type": "corporate",
      "long_position_shares": 3800000000,
      "long_position_pct": 31.1,
      "filing_date": "2025-03-12",
      "form_type": "Form 2",
      "notice_type": "Change"
    }
  ],
  "history": [
    {
      "name": "Naspers Limited",
      "long_position_pct": 22.99,
      "relevant_event_date": "2025-07-25",
      "filing_date": "2025-07-28",
      "form_type": "Form 2",
      "notice_type": "Increase"
    }
  ]
}
```

- `shareholders[]` — current substantial holders (≥5% as listed on DI summary page)
- `history[]` — every individual filing, newest first; used for the Timeline view
- `entity_type`: `"individual"` | `"corporate"` | `"fund"`
- `notice_type`: `"Initial"` | `"Increase"` | `"Decrease"` | `"Change"`
- History date range: HKEX DI portal data starts July 2017 (when the current system launched); newer stocks start from their IPO date

---

### `docs/data/shareholders_index.json`
Inverted index used by the "By Shareholder" tab. Built by `build_index.py`.

```json
{
  "BlackRock, Inc.": ["00700", "09988", "01299"],
  "Vanguard Group": ["00700", "09988"]
}
```

Each shareholder's list is sorted by their % holding descending.

---

### `docs/data/latest_filings.json`
Top 30 most recent filing events across all stocks. Used by the "Latest" tab. Also built by `build_index.py`.

```json
[
  {
    "filing_date": "2026-05-15",
    "code": "00199",
    "stock_name": "CHINA JINMAO HOLDINGS GROUP LIMITED",
    "shareholder": "BlackRock, Inc.",
    "notice_type": "Increase",
    "long_position_pct": 6.04,
    "form_type": "Form 3",
    "relevant_event_date": "2026-05-13"
  }
]
```

Sorted: `filing_date` descending, then `code` ascending within the same date.

---

## Frontend Architecture

The frontend is **vanilla HTML + CSS + JS only**. No build step, no framework, no npm. Everything loads directly in the browser.

### Entry points

| Path | Description |
|---|---|
| `docs/index.html` | Circular home page — search box + tool cards |
| `docs/hkex/index.html` | HKEX DI tracker — the main 4-tab app |

The HKEX sub-page sets `window.DATA_BASE = '../data'` before loading `app.js`. This lets one `app.js` work from any directory depth. All fetches in `app.js` use `const BASE = window.DATA_BASE || 'data'`.

### The four tabs

| Tab | What it does | Data source |
|---|---|---|
| **Latest** | 30 most recent filings, grouped by stock + date | `latest_filings.json` |
| **By Stock** | Search a stock → see shareholders, bars, badges, filing dates | `universe.json` + `di/{code}.json` |
| **By Shareholder** | Search a name → see every stock they hold | `shareholders_index.json` + `di/{code}.json` |
| **Compare** | Pick up to 5 stocks → side-by-side shareholder matrix with heat colouring | multiple `di/{code}.json` |

The **By Stock** tab also has a **Timeline** toggle (inside the tab, not a top-level tab) showing the full filing history for the selected stock, filterable by shareholder name and date range.

### Key JS patterns

- All fetched files are **cached in memory** in a `cache` object — no double-fetching across tabs.
- `renderShareholdersList()` falls back to deriving "last known" holders from `history[]` if `shareholders[]` is empty, and shows a yellow banner to indicate the data is historical.
- The "Latest" table groups consecutive rows that share the same `(code, filing_date)` using HTML `rowspan` to reduce visual noise.
- `jumpToStock(code)` — clicking a stock badge in the Latest tab switches to the By Stock tab and loads that stock automatically.

---

## Scripts

### `python scripts/build_universe.py`
Fetches all HKEX stock codes, gets market cap via yfinance, filters to >$100M USD, saves to `docs/data/universe.json`. Takes ~30 min for the full run; add `--test` to run on 10 stocks only.

### `python scripts/scrape_di.py [--code XXXXX | --mode incremental | --mode full]`
- `--code 00700` — scrape a single stock (good for testing)
- `--mode incremental` — scrape only stocks that appear in today's HKEX DI summary (fast; used by nightly cron)
- `--mode full` — scrape all 1,359 stocks (~30–45 min; run once to seed data)

The scraper fetches data back to 01/01/2000 but HKEX only has records from July 2017 in practice. Delay between requests is randomised 1.5–3s.

### `python scripts/build_index.py`
Reads all `docs/data/di/*.json`, builds `shareholders_index.json` and `latest_filings.json`. Run this after any scrape.

---

## Remaining Steps to Go Live

Run these in order:

**1. Full DI scrape (30–45 min, one-time)**
```bash
python scripts/scrape_di.py --mode full
```

**2. Rebuild index**
```bash
python scripts/build_index.py
```

**3. Enable GitHub Pages**
Repo Settings → Pages → Source: branch `main`, folder `/docs`

**4. Enable Actions write permissions**
Repo Settings → Actions → General → Workflow permissions → **Read and write permissions**

After step 4, the nightly and weekly workflows will run automatically on schedule. They can also be triggered manually from the Actions tab via `workflow_dispatch`.

---

## Automation Schedule

| Workflow | When | What |
|---|---|---|
| `scrape_nightly.yml` | Weekdays 22:00 UTC (06:00 HKT next morning) | Incremental scrape of stocks with same-day filings → rebuilds index |
| `update_universe.yml` | Sundays 02:00 UTC | Refreshes the full stock universe by market cap |

---

## Known Gotchas

- **HKEX DI portal is ASP.NET** — the scraper primes a session and fetches ASP.NET state tokens before each data request. Do not try simple GET requests; it won't work.
- **5-digit zero-padded codes everywhere** — `"00700"` not `"700"`. Yahoo Finance uses `0700.HK` (4-digit); the scraper converts.
- **`data/` at repo root is dead** — early development artifact. All live data is in `docs/data/`.
- **Stocks with 0 shareholders + 0 history** — these are stocks the scraper visited but found no disclosures for (the DI portal returned an empty result). Not a bug; some stocks simply have no substantial shareholder filings.
- **GitHub Actions needs write permission** to push data commits back to the repo. Without it, the nightly scrape runs but silently fails to save the data.

---

## What's Planned but Not Started

From `TO-DO.md`:

- **Buyback action plan** — a new data feature tracking share buyback disclosures. Design not yet started; will be a new sub-page on the Circular home alongside HKEX DI.

---

## Quick Start for a New Developer

```bash
# Clone and install
git clone <repo-url>
cd circular
pip install -r requirements.txt

# Preview the site (data already partially seeded)
python3 -m http.server 8765 --directory docs
# → open http://localhost:8765

# Scrape a single stock to test the pipeline
python scripts/scrape_di.py --code 00700
python scripts/build_index.py

# Run the full scrape to seed all stocks (one-time, ~30–45 min)
python scripts/scrape_di.py --mode full
python scripts/build_index.py
```

The frontend has no build step. Edit `docs/app.js` or `docs/styles.css` and refresh the browser — that's it.
