# HKEX DI Tracker

A GitHub Pages web app that scrapes HKEX's [Disclosure of Interests portal](https://di.hkex.com.hk) for all stocks with market cap > $100M USD and serves an interactive frontend for exploring substantial shareholding data.

No backend required. GitHub Actions handles scheduled scraping; GitHub Pages serves the static frontend; all data lives as committed JSON files.

**Live site:** `https://{username}.github.io/circular/`

---

## Features

- **By Stock** — search any HKEX stock, see its current substantial shareholders with visual % bars, filter by entity type, sort by holding / name / date
- **By Shareholder** — search any fund or institution, see every stock they disclose a position in
- **Compare** — select up to 5 stocks, get a side-by-side matrix with heatmap colouring
- **Timeline** — full filing history for any stock, filterable by shareholder name and date range

---

## Setup

### 1. Enable GitHub Pages

Repo **Settings → Pages → Source**: deploy from branch `main`, folder `/docs`.

### 2. Allow Actions to push data commits

Repo **Settings → Actions → General → Workflow permissions**: set to **Read and write permissions**.

### 3. Seed initial data

Trigger the workflows manually (Actions tab → select workflow → **Run workflow**):

1. Run **Weekly Universe Update** — builds `docs/data/universe.json` (~600–900 stocks)
2. Run **Nightly DI Scrape** with mode = `full` — populates `docs/data/di/` for all stocks (~30–45 min)

After that, nightly and weekly schedules take over automatically.

---

## Schedules

| Workflow | Schedule | What it does |
|---|---|---|
| `scrape_nightly.yml` | Weekdays 22:00 UTC | Scrapes stocks with same-day DI filings; rebuilds shareholder index |
| `update_universe.yml` | Sundays 02:00 UTC | Refreshes the full stock universe by market cap |

Both workflows can also be triggered manually via **workflow_dispatch**, with the nightly scrape accepting a `mode` input (`incremental` or `full`).

---

## Running locally

```bash
pip install -r requirements.txt

# Rebuild universe (full run, ~30 min; or --test for 10 stocks)
python scripts/build_universe.py [--test]

# Scrape a single stock
python scripts/scrape_di.py --code 00700

# Scrape today's filings only
python scripts/scrape_di.py --mode incremental

# Scrape all stocks in universe.json (~30–45 min)
python scripts/scrape_di.py --mode full

# Rebuild shareholder index (run after any scrape)
python scripts/build_index.py

# Serve the frontend
cd docs && python -m http.server 8080
# → open http://localhost:8080
```

---

## Repo structure

```
circular/
├── .github/workflows/
│   ├── scrape_nightly.yml
│   └── update_universe.yml
├── scripts/
│   ├── build_universe.py   # Builds universe.json via yfinance
│   ├── scrape_di.py        # Scrapes DI portal → docs/data/di/{code}.json
│   └── build_index.py      # Builds shareholders_index.json
├── docs/                   # GitHub Pages root
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── data/
│       ├── universe.json
│       ├── shareholders_index.json
│       ├── last_run.json
│       └── di/
│           ├── 00700.json
│           └── ...
├── requirements.txt
└── PLANNING.md
```

---

## Data notes

- **Universe**: ~600–900 stocks above $100M USD market cap, refreshed weekly
- **DI data**: one JSON file per stock; `shareholders[]` = current substantial holders (≥5%), `history[]` = all historical filings newest-first
- **Stock codes**: always 5-digit zero-padded (`00700`, not `700`)
- **Rate limiting**: scraper uses 1.5–3s random delay between requests; a full run takes ~30–45 min within GitHub Actions' 6-hour limit
- **Scraper target**: `di.hkex.com.hk` (notices filed through DION system since July 2017)

---

## Gotchas

- The HKEX DI portal is ASP.NET; the scraper primes a session cookie before fetching data pages
- Yahoo Finance rate-limits aggressive polling — `build_universe.py` batches in groups of 50 with a 1s delay; requires `yfinance >= 1.0.0`
- `data/` at repo root is unused; all live data is in `docs/data/` so GitHub Pages can serve it
