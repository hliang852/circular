# Circular — Project Status & Action Plan
**Date: 2026-05-30**

---

## Overview

Two core HK modules are built and scraping nightly (DI + CA). Singapore scrapers are implemented but hold zero data. The frontend hub exists but DI and CA are not yet merged into the unified hub per `MERGE_PLAN.md`. GitHub Pages live status is unconfirmed.

---

## Region: Hong Kong (HKEX)

### Home Page
**Status: Built (hub exists, but DI+CA not yet merged into it)**

- `Circular_Homepage.html` is complete: dark theme, region selector (HK/SG), module cards, global search
- Navigation wires to `/di/` and `/ca/` correctly
- Cross-module deep linking (DI ↔ CA) is `href="#"` placeholders — not wired
- Chatbot is CA-module-scoped; not yet promoted to site-wide

### Corporate Actions (CA) — `/ca/`
**Status: v10 prototype complete; live data wired for most stocks, Tencent still partly hardcoded**

What's built:
- 6 views: Home, By Stock, League Table, Last Session, Ideas, Calendar
- By Stock: mandate progress bar, hero card (signal + consistency score), 12-month Chart.js buyback bars with equity event overlays (placings ▼, CBs ◆), blackout bands, monthly returns table
- League Table: sortable by YTD, % issued, mandate used, last filing; active/inactive filter
- Ideas tab: "Conviction Buys" and "Mandate Renewers" screener logic
- Calendar: month grid with results + AGM dots
- AI Chatbot: Anthropic API wired with auto-navigation
- **Data coverage: 122 stocks** scraped; `ca_index.json` has 123 entries

What's still prototype/hardcoded:
- Blackout dates: estimated as ~30 days before results (not pulled from data)
- Free float: hardcoded 58% for Tencent; not in JSON schema for other stocks
- Next results date: estimated, not scraped
- Signal ("Strong Buy"): hardcoded for Tencent; logic not generalized
- Calendar mock data covers May–July 2025 (stale)
- PDF links point to search UI, not specific documents
- CA scrape last ran **2026-05-17** (2 weeks stale)

### Disclosure of Interests (DI) — `/di/`
**Status: Feature-complete; scraping nightly; not yet published to GitHub Pages**

What's built:
- 5 views: Latest (30 most recent), By Stock, By Shareholder, Compare (5-stock heatmap), Timeline
- ASP.NET VIEWSTATE session priming handled correctly
- Nightly scrape running weekdays 22:00 UTC
- **Data coverage: 343 of 1,359 stocks** (25%) — full scrape not yet triggered
- Last scrape: **2026-05-29** (current)

Gaps:
- GitHub Pages not yet enabled (still pending repo settings)
- Full scrape (30–45 min) needed to seed remaining ~1,016 stocks
- Shareholder index must be rebuilt after full scrape
- Actions write permissions may need enabling

### ECM
**Status: Not yet built for HK**

No dedicated ECM page exists under `/ca/` or elsewhere for HK. Equity issuances appear as overlay markers (◆ CB, ▼ placing) on the CA By Stock chart, but there is no standalone ECM deal tracker, league table, or issuance screener for HK.

---

## Region: Singapore (SGX)

### Home Page — `/sg/`
**Status: Stubbed — template shell only, no data**

Regional selector exists, routes to `/sg/di/` and `/sg/ca/`. No content.

### Corporate Actions — `/sg/ca/`
**Status: Scraper implemented; frontend template exists; zero data**

- `scrape_sg_corp_actions.py` is written (placings, rights, buybacks from SGXNet)
- `docs/data/sg/ca/` directory is empty
- Frontend is a template copy, no live binding

### Disclosure of Interests — `/sg/di/`
**Status: Scraper implemented; frontend template exists; zero data**

- `scrape_sg_di.py` written (MAS Form 1/3/4 via SGXNET)
- `build_sg_universe.py` written
- `docs/data/sg/universe.json` is 90 bytes (empty array)
- `docs/data/sg/di/` directory is empty

### ECM — Singapore
**Status: Scraper stubbed (`scrape_sg_cap_market.py`); minimal/no data; no frontend page**

---

## Region: Japan
**Status: Not started**

No scrapers, no data, no frontend pages for Japan. Not referenced in any planning document.

---

## Next Steps by Priority

### Tier 1 — Unlock live product (HK)
1. **Enable GitHub Pages** (Settings → Pages → `/docs` branch) — DI is fully built but inaccessible
2. **Set Actions write permissions** (Settings → Actions → Read and write) — blocks nightly auto-commit
3. **Run full DI scrape** (~30–45 min) to seed remaining 1,016 stocks; rebuild `shareholders_index.json` and `latest_filings.json` after
4. **Re-run CA scrape** — last ran May 17, now 2 weeks stale

### Tier 2 — Complete CA prototype wiring
5. Wire **blackout dates** from actual results dates in `calendar.json` instead of hardcoded -30d estimate
6. Generalize **signal logic** (currently hardcoded "Strong" for Tencent) using consistency score + VWAP
7. Add **free float** field to CA JSON schema and scraper; remove hardcoded 58%
8. Fix **calendar data** — currently May–July 2025; needs to pull from live `calendar.json`
9. Fix **PDF deep links** to point at specific HKEXnews document URLs rather than search UI

### Tier 3 — Execute MERGE_PLAN.md (hub unification)
10. Extract shared design tokens → `docs/assets/tokens.css`
11. Wire DI ↔ CA cross-module deep links (`href="#"` → `?code=` routing)
12. Promote chatbot to site-wide level
13. Retire `/hkex/` legacy redirect after 90 days

### Tier 4 — Seed Singapore
14. Run `build_sg_universe.py` to seed SGX universe
15. Run initial full SG DI + CA scrape
16. Set up SGX nightly GitHub Action (equivalent to HK's `scrape_nightly.yml`)

### Tier 5 — HK ECM standalone page
17. Build dedicated ECM page for HK (deal log, issuer/bookrunner league tables) — currently only visible as overlay markers on CA chart

---

## Action Items (Decisions / Patches Required)

| # | Item | Decision needed |
|---|---|---|
| 1 | **CA scrape cadence** | CA last ran May 17 — is the `scrape_ca.yml` GitHub Action actually running? Check Action logs; it may have failed silently or the workflow trigger condition is off. |
| 2 | **Free float data source** | Currently hardcoded. Options: (a) scrape from HKEX monthly return (FF301 field), (b) pull from yfinance `info["floatShares"]`, (c) keep hardcoded per-stock. Pick one before scaling. |
| 3 | **Signal logic generalization** | "Strong Buy" is hardcoded for Tencent. Need to define the formula (consistency score threshold + VWAP floor + active 30d) and apply it across all 122 CA stocks. |
| 4 | **Japan scope** | No planning document references Japan. Is this on the roadmap or not in scope? If it is, it needs a data source decision (TSE filing format is very different from HKEX/SGX). |
| 5 | **Chatbot API key exposure** | `CA ENGINEER_HANDOFF.md` flags this as an open question — Anthropic API key is currently client-side. Needs either a backend proxy or a rate-limited public key with spend cap before any public launch. |
| 6 | **SG universe seed** | `build_sg_universe.py` is written but never run. SGX has ~700 listed companies — need to decide market cap cutoff (same $100M USD as HK?) and confirm SGXNet API access still works. |
| 7 | **DI GitHub Pages path** | Currently DI is at `/di/` but the legacy path `/hkex/` has a redirect. Confirm the canonical URL before promoting externally to avoid link rot. |
