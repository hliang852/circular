# Circular — Merge Plan: DI + Corporate Actions

> **Status:** Spec ready for implementation · Last updated: May 2026
> **Audience:** Claude Code (executing the migration) and engineering reviewers
> **Companion docs:** `PLANNING.md` (DI build spec), `CONTEXT.md` (DI rationale), `ENGINEER_HANDOFF.md` (CA spec), `DI_Handoff.md` (DI current state)

---

## 1. What This Document Is

Circular today has two modules built or designed in isolation:

- **DI (Disclosure of Interests)** — built, working, 27 of 1,359 stocks scraped, serving from `docs/hkex/`. Uses a lighter table-driven aesthetic.
- **CA (Corporate Actions / Buybacks)** — v10 HTML prototype at `docs/corporate-actions.html`. Polished dark theme with JS-wired tooltips, AI chatbot, 6 views. Not yet wired to live data.

This document is the spec for merging them into a single coherent product where **DI and CA are co-equal sub-branches under a Main hub**, sharing one design language (CA's), one data substrate, and one navigation shell.

**The CA design is the source of truth for visual style.** DI gets restyled to match CA, not the other way around.

---

## 2. The Merger Model

```
                 Circular (Main hub: docs/index.html)
                            │
              ┌─────────────┴─────────────┐
              │                           │
        DI module                   CA module
      (docs/di/...)              (docs/ca/...)
              │                           │
              └──────── shared ───────────┘
                  (docs/assets/...)
                  (docs/data/...)
```

Three things bind the two modules together:

1. **Shared design system** in `docs/assets/` — tokens, components, utilities, chatbot.
2. **Shared data substrate** in `docs/data/` — single `universe.json`, single `last_run.json`, parallel `di/` and `ca/` per-stock JSON trees.
3. **Shared navigation shell** — persistent header with module switcher and global search, present on every page.

Each module retains its own data fetch logic, its own view-specific JS, and its own per-module CSS overrides. Everything else is hoisted into the shared layer.

---

## 3. Target File Structure

```
circular/
├── .github/workflows/
│   ├── scrape_nightly.yml         # DI incremental — Mon–Fri 22:00 UTC
│   ├── scrape_ca.yml              # CA incremental — Mon–Fri 23:30 UTC (renamed from scrape_buybacks.yml)
│   └── update_universe.yml        # Universe refresh — Sun 02:00 UTC
│
├── scripts/
│   ├── build_universe.py          # SHARED — both modules read universe.json
│   ├── scrape_di.py               # DI scraper (unchanged)
│   ├── scrape_ca.py               # CA scraper (renamed from scrape_buybacks.py)
│   ├── build_di_index.py          # Renamed from build_index.py
│   └── build_ca_index.py          # Renamed from build_buybacks_index.py
│
├── docs/
│   ├── index.html                 # Circular hub — landing, global search, module cards
│   │
│   ├── assets/                    # SHARED LAYER
│   │   ├── tokens.css             # Design tokens lifted from CA prototype
│   │   ├── shared.css             # Header, card, table, badge, chip, search, modal
│   │   ├── shared.js              # Cache, formatters, URL routing, universe loader
│   │   └── chatbot.js             # Global Circular assistant (knows DI + CA)
│   │
│   ├── di/
│   │   ├── index.html             # Was docs/hkex/index.html — restyled
│   │   ├── di.js                  # 4 tabs: Latest, By Stock, By Shareholder, Compare
│   │   └── di.css                 # Overrides only (compare matrix heat, timeline rows)
│   │
│   ├── ca/
│   │   ├── index.html             # Was docs/corporate-actions.html — split out
│   │   ├── ca.js                  # 6 views: Home, By Stock, League, Last Session, Ideas, Calendar
│   │   └── ca.css                 # Overrides only (mandate card, signal gradients)
│   │
│   ├── hkex/                      # DEPRECATED — kept temporarily with meta-refresh redirect
│   │   └── index.html             # <meta http-equiv="refresh" content="0;url=/circular/di/">
│   │
│   └── data/
│       ├── universe.json          # SHARED — ~700–1,359 stocks > $100M USD
│       ├── last_run.json          # SHARED — { "di": {...}, "ca": {...}, "universe": {...} }
│       ├── shareholders_index.json
│       ├── latest_filings.json
│       ├── ca_index.json          # Renamed from buybacks_index.json
│       ├── di/{code}.json
│       └── ca/{code}.json         # Renamed from buybacks/{code}.json
│
├── PLANNING.md                    # DI build spec (existing)
├── CONTEXT.md                     # DI rationale (existing)
├── ENGINEER_HANDOFF.md            # CA spec (existing)
├── DI_Handoff.md                  # DI current state (existing)
├── MERGE_PLAN.md                  # THIS DOCUMENT
├── requirements.txt
└── README.md
```

**Why rename `buybacks/` → `ca/`:** Symmetry with `di/`, and CA will grow beyond just buybacks per the data-sources roadmap (CCASS, placings, CBs, insider dealings, results dates all belong here eventually).

---

## 4. Design System Unification

### 4.1 Tokens to extract from `corporate-actions.html` into `assets/tokens.css`

Lift these from the CA prototype's `<style>` block verbatim:

- Backgrounds: `--bg`, `--sf`, `--sf2`
- Borders & lines: `--line`, `--line-strong`
- Text: `--text`, `--muted`, `--text-dim`
- Accents: `--accent`, `--accent-2`
- Signal colors: green (strong), amber (moderate), red (weak/decrease)
- Gradients: mandate green→blue, probability purple→blue (these must remain distinct — see §9)
- Typography: font stack, size scale, weight scale
- Spacing: padding/margin scale
- Radii and shadows for cards

### 4.2 Shared components in `assets/shared.css`

These primitives exist in CA today and must be lifted out so DI can use them too:

| Component | Used by | Notes |
|---|---|---|
| Persistent header / nav bar | All pages | Wordmark + module tabs + global search + chatbot trigger |
| Hero card (stock detail) | DI By-Stock, CA By-Stock | Same shape; different content inside |
| Sortable data table | DI Latest, DI Compare, CA League, CA Last Session | Sort indicators, hover row, horizontal scroll on mobile |
| Filter chip group | DI Latest filters, CA League filters | Pill-style toggle group |
| Badge (entity / signal / status) | DI entity-type, CA signal grade, CA active flag | Same shape; color via modifier class |
| Search input with suggestions | Global header, DI tabs, CA tabs | Autocomplete from universe.json |
| Loading / error states | Both modules | "Loading…" spinner, "Data unavailable" banner |
| Modal / drawer | Chatbot, calendar event detail | Reusable shell |

### 4.3 What stays in module-specific CSS

`di.css`:
- Heat coloring scale for the Compare matrix cells
- Timeline row format (date pill + arrow + percentage delta)
- Shareholder list horizontal bars (% width fill)
- "Historical data" yellow banner

`ca.css`:
- Mandate `<details>` card with the always-visible progress bar
- Probability gauge (purple→blue gradient)
- Equity event markers on the 12-month chart (▼ placing, ◆ CB)
- Blackout band overlay style
- Buyback economics strip layout

### 4.4 Hard constraints from CA prototype that must survive

From `ENGINEER_HANDOFF.md` §5–6 — these were learned the hard way and must not regress:

- **JS-wired tooltips, not CSS `:hover`** on `<summary>` elements (browser event interception issue)
- **No `overflow:hidden` on `<details>` elements** (clips tooltips that extend above the card)
- **Mandate bar shows "% of mandate used" not "% of issued capital"** (avoids "why isn't it 100%?" confusion)
- **Probability bar is purple→blue, never green→blue** (adjacent identical gradients are indistinguishable)
- **Stock code displays as "700 HK" not "00700"** throughout the frontend (storage stays 5-digit padded)
- **`overflow-x: auto` on tables** instead of column hiding (analyst convention)

---

## 5. Main Hub Redesign

`docs/index.html` becomes the spine of the product, not a tool directory.

### Layout

```
┌──────────────────────────────────────────────────────────────┐
│  Circular        DI · Corporate Actions       [search]  💬   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   Circular                                                   │
│   HKEX market intelligence                                   │
│                                                              │
│   [ Global stock search — ticker or company name        ]    │
│                                                              │
│   ┌───────────────────────┐    ┌───────────────────────┐    │
│   │ Disclosure of         │    │ Corporate Actions     │    │
│   │ Interests             │    │                       │    │
│   │                       │    │                       │    │
│   │ 1,359 stocks tracked  │    │ 6 active buyback      │    │
│   │ 14 filings today      │    │ programmes            │    │
│   │ Last updated: 06:00   │    │ 3 Conviction Buys     │    │
│   │                       │    │ Last updated: 07:30   │    │
│   │ [ Open DI tracker →]  │    │ [ Open CA tracker →]  │    │
│   └───────────────────────┘    └───────────────────────┘    │
│                                                              │
│   Last scrape: 17 May 2026 06:00 UTC · all systems green     │
└──────────────────────────────────────────────────────────────┘
```

### Behavior

- **Global stock search** — types into `universe.json`, returns suggestions. Selecting a stock asks which module to open (or remembers last choice per session).
- **Module cards** — live counts pulled from `latest_filings.json` (DI) and `ca_index.json` (CA). If the count fetch fails, show "—" not zero.
- **Status banner** — single source of truth from `last_run.json`. Green if both scrapes succeeded in the last 24h; amber if one failed; red if both failed.
- **Aesthetic:** CA dark theme, the same hero-card pattern used inside both modules.

---

## 6. Persistent Navigation

The header bar (in `assets/shared.css` + `shared.js`) is identical across hub, DI, and CA:

```
┌─────────────────────────────────────────────────────────────────┐
│  [Circular]    DI · Corporate Actions    [🔍 Search]    [💬]   │
└─────────────────────────────────────────────────────────────────┘
```

- **Wordmark** — link to `/circular/`
- **Module tabs** — active state highlighted; clicking switches module while preserving the current stock context if possible (e.g. on DI's By-Stock for `00700`, clicking "Corporate Actions" lands on CA's By-Stock for `00700`)
- **Global search** — context-aware. From the hub, prompts module choice. From DI, lands in DI. From CA, lands in CA.
- **Chatbot trigger** — opens the modal from `assets/chatbot.js`

---

## 7. Cross-Linking By-Stock Views

The single highest-value integration. Resolves the placeholder `href="#"` flagged in `ENGINEER_HANDOFF.md` §8.7.

### URL contract

- DI: `/circular/di/?code=00700` → loads By-Stock for Tencent
- CA: `/circular/ca/?code=00700` → loads By-Stock for Tencent
- On page load, each module checks `?code=` and routes accordingly

### Cross-link surfaces

- **DI By-Stock page** — under the shareholder table, a card: "**View buybacks for 700 HK →**" linking to `/circular/ca/?code=00700`. Only show if CA data exists for that stock (check `ca_index.json` codes).
- **CA By-Stock page** — under the hero card, a card: "**View DI filings for 700 HK →**" linking to `/circular/di/?code=00700`. Only show if DI data exists for that stock.

### Compound signal hint

When viewing a stock in CA and that stock also has DI accumulation activity in the same period, surface this inline on the CA page:

> 🎯 **Compound signal:** BlackRock accumulating + buyback active. View DI filings →

The signal computation already exists in `build_ca_index.py` (`signal: "strong"` requires this). Surfacing it on the page is one extra fetch of `data/di/{code}.json`.

---

## 8. Data Architecture Changes

Minimal — mostly renames for symmetry.

### Renames

| Old path | New path |
|---|---|
| `data/buybacks/{code}.json` | `data/ca/{code}.json` |
| `data/buybacks_index.json` | `data/ca_index.json` |
| `scripts/scrape_buybacks.py` | `scripts/scrape_ca.py` |
| `scripts/build_buybacks_index.py` | `scripts/build_ca_index.py` |
| `scripts/build_index.py` | `scripts/build_di_index.py` |
| `.github/workflows/scrape_buybacks.yml` | `.github/workflows/scrape_ca.yml` |

### `last_run.json` becomes structured

```json
{
  "di": {
    "last_run": "2026-05-17T06:00:12Z",
    "mode": "incremental",
    "stocks_scraped": 14,
    "errors": []
  },
  "ca": {
    "last_run": "2026-05-17T07:30:08Z",
    "mode": "incremental",
    "stocks_scraped": 3,
    "errors": []
  },
  "universe": {
    "last_run": "2026-05-12T02:00:04Z",
    "stocks_total": 1359
  }
}
```

Lets the hub's status banner display per-module health without a flat blob.

### What does not change

- `universe.json` shape and location — both modules already read it.
- `di/{code}.json` schema — exactly as documented in `DI_Handoff.md`.
- `ca/{code}.json` schema — exactly as documented in `ENGINEER_HANDOFF.md` §3.
- `shareholders_index.json` and `latest_filings.json` — DI-specific, unchanged.

---

## 9. Migration Order (Testable Steps)

Each step has a verification command or visual check. Do not proceed to the next step until the current one passes.

### Step 1 — Extract shared design system

**Files created:** `docs/assets/tokens.css`, `docs/assets/shared.css`

1. Open `docs/corporate-actions.html`. Lift the entire `:root { ... }` block and any CSS custom-property definitions into `docs/assets/tokens.css`.
2. Identify the component CSS classes used in CA (header, card, table, badge, chip, search, modal) and lift their styles into `docs/assets/shared.css`.
3. In `corporate-actions.html`, replace those styles with `<link rel="stylesheet" href="../assets/tokens.css">` and `<link rel="stylesheet" href="../assets/shared.css">`.

**Verify:** Open `corporate-actions.html` in a local server (`python -m http.server 8765 --directory docs`). The page must render identically to before. Diff against a screenshot baseline if possible.

### Step 2 — Split CA into its own folder

**Files created:** `docs/ca/index.html`, `docs/ca/ca.js`, `docs/ca/ca.css`

1. `mv docs/corporate-actions.html docs/ca/index.html`
2. Extract the inline `<script>` blocks into `docs/ca/ca.js`. Reference as `<script src="ca.js" defer></script>`.
3. Extract remaining inline `<style>` blocks (after Step 1 already moved most out) into `docs/ca/ca.css`. Reference as `<link rel="stylesheet" href="ca.css">`.
4. Update fetch paths: `data/buybacks_index.json` → `../data/buybacks_index.json` (rename comes in Step 5).
5. Update the asset paths: `../assets/tokens.css`, `../assets/shared.css`.

**Verify:** `http://localhost:8765/ca/` renders identically to old `corporate-actions.html`. All 6 views work. Chatbot still loads. Mandate card still collapsed-by-default with progress bar visible.

### Step 3 — Move DI to its own folder (no restyling yet)

**Files moved:** `docs/hkex/` → `docs/di/`; `docs/app.js` → `docs/di/di.js`; `docs/styles.css` → `docs/di/di.css`

1. `mv docs/hkex docs/di`
2. `mv docs/app.js docs/di/di.js`
3. `mv docs/styles.css docs/di/di.css`
4. Update `docs/di/index.html` to reference `di.js` and `di.css` locally, and set `window.DATA_BASE = '../data'`.
5. Create stub `docs/hkex/index.html` with `<meta http-equiv="refresh" content="0;url=/circular/di/">` so any bookmarks redirect.

**Verify:** `http://localhost:8765/di/` works identically to the old `/hkex/` URL. All 4 tabs functional. `/hkex/` redirects to `/di/`.

### Step 4 — Restyle DI to match CA

**Files modified:** `docs/di/index.html`, `docs/di/di.css`

This is the largest visual step. Work tab by tab; verify after each.

1. Add `<link rel="stylesheet" href="../assets/tokens.css">` and `<link rel="stylesheet" href="../assets/shared.css">` to `docs/di/index.html` *before* `di.css`.
2. Refactor `di.css` to remove anything now provided by the shared layer. What remains: Compare matrix heat colors, timeline rows, shareholder bars, historical-data banner.
3. Replace DI's existing search box, tabs, badges, and tables with the shared component classes.
4. Tab-by-tab verification:
   - **Latest tab** — table uses shared sortable-table styles; entity badges use shared badge with green/amber/red color modifiers.
   - **By Stock tab** — shareholder list uses shared hero card; bars styled via `di.css` only.
   - **By Shareholder tab** — same table primitive as Latest.
   - **Compare tab** — matrix heat coloring stays in `di.css`; table shell from shared.

**Verify:** Visual parity check between DI's By-Stock view and CA's By-Stock view — they should feel like the same product. Functionality unchanged: search still works, sort still works, Compare still accepts up to 5 stocks.

### Step 5 — Rename CA data paths

**Files modified:** `docs/ca/ca.js`, `scripts/scrape_buybacks.py`, `scripts/build_buybacks_index.py`, GitHub workflow

1. In `ca.js`: `data/buybacks_index.json` → `data/ca_index.json`; `data/buybacks/${code}.json` → `data/ca/${code}.json`.
2. Rename data files in-place: `mv docs/data/buybacks docs/data/ca`; `mv docs/data/buybacks_index.json docs/data/ca_index.json`.
3. Rename scripts: `mv scripts/scrape_buybacks.py scripts/scrape_ca.py`; `mv scripts/build_buybacks_index.py scripts/build_ca_index.py`. Update their internal output paths to write to `docs/data/ca/`.
4. Rename `scripts/build_index.py` → `scripts/build_di_index.py` for symmetry.
5. Rename workflow: `mv .github/workflows/scrape_buybacks.yml .github/workflows/scrape_ca.yml`. Update step commands inside.

**Verify:** `http://localhost:8765/ca/` still loads all data. Run `python scripts/scrape_ca.py --code 00700 --mode full` and confirm output appears at `docs/data/ca/00700.json`.

### Step 6 — Build the Main hub

**Files modified:** `docs/index.html`

1. Replace existing thin tool-directory layout with the design from §5.
2. Reference `../assets/tokens.css`, `../assets/shared.css`, `../assets/shared.js`.
3. On page load: fetch `data/universe.json`, `data/latest_filings.json`, `data/ca_index.json`, `data/last_run.json` in parallel.
4. Populate module card stats from the fetched data.
5. Wire the global search to filter `universe.json` and route to the chosen module's By-Stock view.

**Verify:** `http://localhost:8765/` shows live counts, module cards link correctly, global search returns suggestions and routes.

### Step 7 — Persistent navigation across all pages

**Files modified:** `assets/shared.js`, all three `index.html` files

1. In `shared.js`, export a `renderHeader()` function that writes the nav HTML into a `<div id="circular-header"></div>` placeholder on each page.
2. Add the placeholder to `docs/index.html`, `docs/di/index.html`, `docs/ca/index.html`.
3. The function reads `window.CIRCULAR_MODULE` (set per page) to highlight the active tab.
4. Wire module-switcher tabs to preserve `?code=` if present in the current URL.

**Verify:** Header appears identically on all three pages. Module tabs highlight correctly. Switching from DI's `/di/?code=00700` to CA's tab lands on `/ca/?code=00700`.

### Step 8 — Cross-linking By-Stock views

**Files modified:** `docs/di/di.js`, `docs/ca/ca.js`

1. **DI side:** in `di.js`, when rendering By-Stock for a `code`, fetch `data/ca_index.json` (cached) and check if `code` is present. If yes, render the "View buybacks for {code} HK →" card. Link to `/circular/ca/?code={code}`.
2. **CA side:** in `ca.js`, when rendering By-Stock for a `code`, fetch `data/shareholders_index.json` or check if `data/di/{code}.json` exists (HEAD request). If yes, render the "View DI filings for {code} HK →" card. Link to `/circular/di/?code={code}`.
3. **Compound signal hint:** on CA's By-Stock page, if the stock's `signal === "strong"`, also fetch `data/di/{code}.json` and find the most recent `history[]` entry with `notice_type === "Increase"`. If within the last 90 days, render the compound signal banner from §7.
4. Both modules: on load, check `URLSearchParams` for `code` and route accordingly.

**Verify:** From DI's `/di/?code=00700`, the "View buybacks" link appears and lands correctly on `/ca/?code=00700`. Same in reverse. Compound signal banner appears for Tencent when both signals are present.

### Step 9 — Promote the chatbot

**Files created:** `docs/assets/chatbot.js`

1. Extract chatbot logic from `ca.js` into `assets/chatbot.js`.
2. Expand the system prompt to know about both modules:

```js
const systemPrompt = `
You are Circular's assistant for HKEX market intelligence.
Today is ${new Date().toLocaleDateString()}.

You can answer questions about and navigate to:
- DI (Disclosure of Interests): substantial shareholders ≥5% per stock
  Tabs: Latest, By Stock, By Shareholder, Compare
- CA (Corporate Actions): share buybacks, mandate headroom, equity issuances
  Views: By Stock, League, Last Session, Ideas, Calendar

Available stocks: ${universeData.length} total
Latest DI filings: ${latestFilings.slice(0, 5).map(f => f.stock_name).join(', ')}
Active buybacks: ${caIndex.filter(s => s.programme_active).map(s => s.name).join(', ')}
Conviction Buys today: ${convictionBuys.map(s => s.name).join(', ')}

When the user asks something, decide which module + view answers it, navigate there
via navigateTo(module, view, params), and give a brief 1-2 sentence answer.
`;
```

3. Add the chatbot trigger to the persistent header so it's available from every page.
4. In `navigateTo`, support cross-module navigation: `navigateTo('di', 'by-stock', { code: '00700' })`.

**Verify:** Open chatbot from any page. Ask "Who's the biggest holder of Tencent?" — should navigate to DI's By-Stock view. Ask "Is anyone buying back aggressively?" — should navigate to CA's League Table sorted by % issued.

### Step 10 — Final integration test

1. Run a local server: `python -m http.server 8765 --directory docs`
2. Walk through this user journey:
   - Land on `/circular/` — see module cards with live counts
   - Click "Open DI tracker" — see DI Latest tab, restyled
   - Search for Tencent — land on DI By-Stock for 00700
   - Click "View buybacks for 700 HK →" — land on CA By-Stock for 00700
   - Click "View DI filings →" on CA — back to DI By-Stock
   - Open chatbot, ask "Conviction Buys?" — chatbot navigates to CA Ideas
   - Click "Corporate Actions" tab in header from DI — preserves stock context
3. Run a Lighthouse pass on each page. No regressions vs. pre-merge.

---

## 10. Design Constraints to Preserve

From `ENGINEER_HANDOFF.md` §5–6 (do not regress during migration):

- JS-wired tooltips on `<summary>` elements (not CSS `:hover`)
- No `overflow:hidden` on `<details>` (clips tooltips)
- Mandate bar framing: "% of mandate used" not "% of issued capital"
- Probability gradient: purple→blue (never green→blue)
- Stock code display: "700 HK" not "00700" (storage stays 5-digit padded)
- `overflow-x: auto` on tables (no column hiding)
- Mandate card collapsed by default, progress bar visible in collapsed state
- Signal badge styles: green = strong, amber = moderate, red = weak

From `DI_Handoff.md`:

- All fetched files cached in memory per session (`cache` object)
- `renderShareholdersList()` falls back to `history[]` if `shareholders[]` empty + shows yellow banner
- Latest tab uses `rowspan` to group `(code, filing_date)` rows
- `window.DATA_BASE` pattern allows depth-flexible data paths

---

## 11. Tradeoffs Worth Knowing

- **Vanilla JS stays.** Both modules already use it; GitHub Pages serves it free; no build step to maintain. Resist introducing React/Vite as part of this merger — it's a separate decision.
- **Don't merge per-stock JSONs.** Keeping `di/{code}.json` and `ca/{code}.json` separate preserves git diff clarity. The nightly DI bot commit shouldn't churn buyback data and vice versa.
- **Chatbot key exposure is a real risk.** Per the prototype it works in-browser via the claude.ai artifact environment. In production on GitHub Pages there's no place to hide a key without a proxy. Cloudflare Worker or Vercel Edge Function is non-optional once this goes live — see `ENGINEER_HANDOFF.md` §7.
- **The Sunday universe refresh should happen first** in any cold start. Both modules depend on `universe.json`. If you're seeding from scratch: universe → DI scrape → CA scrape, in that order.
- **Don't restyle DI before splitting it.** Step 3 (move) before Step 4 (restyle) — otherwise the restyling work happens against a moving target.

---

## 12. Future Modules (Designed-For Extensibility)

The `/di/` and `/ca/` split is designed to extend. Per the data-sources roadmap PDF, future modules slot in as siblings:

- `/ccass/` — daily broker/custodian shareholding breakdowns (sub-5% ownership)
- `/insiders/` — directors' and officers' dealings
- `/flows/` — Stock Connect Northbound flows, short-selling turnover
- `/results/` — earnings calendar with DI/CA event overlay

Each new module would follow the same pattern: own folder under `docs/`, own scripts, own data folder, inherits everything from `assets/`. The Main hub adds another module card. The chatbot system prompt is extended to know the new module.

---

## 13. Open Questions for Human Review

Flag these to the user before or during implementation:

1. **Hub stock-search routing default.** When a user searches a stock from the hub, should it default to DI (the more mature module) or always prompt? Suggest: default to DI for now, with a small "Open in CA instead" link in the result row.

2. **Compound signal threshold.** The CA "strong" signal currently requires *any* DI accumulation in the same period. Should "same period" mean 30, 60, or 90 days? Suggest 90 days based on typical buyback cycle length.

3. **`/hkex/` redirect lifetime.** How long to keep the meta-refresh stub before removing? Suggest 90 days, then drop.

4. **CA prototype's hardcoded Tencent data.** During Step 5, all hardcoded league/stock data in `ca.js` should be removed. Verify the user has run the CA scrape against the 5 seed stocks first (`00700`, `00005`, `00388`, `09988`, `03690` per `Corporate_Actions.md` Step 4) so the migration doesn't leave a blank UI.

5. **Module switcher: preserve view, or preserve stock?** When switching from DI's By-Shareholder view to CA, should it land on CA's By-Stock for the currently-highlighted stock (preserves stock), CA's home (preserves nothing), or CA's most-similar view (there isn't one)? Suggest: preserve stock if there's one in scope, else land on CA home.
