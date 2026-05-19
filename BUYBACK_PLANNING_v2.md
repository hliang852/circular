# Share Buyback Tracker — Planning Document (v2)

> Add-on module for the Circular project. Scrapes HKEX Monthly Return filings, AGM repurchase mandate circulars, and equity issuance announcements to surface a complete capital activity picture alongside Disclosure of Interests data.

---

## What This Module Does

Three data types are scraped and combined into a single "By Stock" view:

1. **Monthly Return filings** — share repurchase activity per month (price, volume, consideration)
2. **Repurchase mandate** — the AGM-approved authority to buy back up to N% of issued capital, including headroom remaining
3. **Equity issuances** — placings, rights issues, open offers, convertible bonds — events that expand share capital and directly offset or interact with buyback activity

---

## Why This Matters for DI Analysis

- **Mechanical % changes:** Buybacks reduce issued capital → DI holders' % rises without any trade. Equity issuances do the opposite. Both drive "phantom" DI threshold crossings.
- **Signal layering:** A company buying back aggressively while simultaneously running a CB offering is a tension worth surfacing immediately.
- **Mandate headroom:** Knowing how much mandate a company has left determines whether a buyback programme can continue at the current pace.

---

## Data Source 1: Monthly Return Filings

**Portal:** HKEXnews Title Search  
**URL:** `https://www1.hkexnews.hk/search/titlesearch.xhtml`  
**Headline category:** `"Announcement pursuant to Code on Share Buy-backs"` / `"Document issued pursuant to Code on Share Buy-backs"`  
**Also look for:** `"Monthly Return of Equity Issuer on Movements in Securities"` (captures the aggregate monthly filing)

The portal exposes a JSON API used by its own search UI — no VIEWSTATE required:
```
GET https://www1.hkexnews.hk/search/titlesearch.xhtml
    ?lang=EN&stockcode=00700
    &category=0&documenttype=-2
    &fromdate=20240101&todate=20241231
```

Each Monthly Return PDF contains a table with:
- Date of each repurchase within the month
- Shares repurchased on that date
- Highest and lowest price paid (HK$)
- Total consideration paid

Aggregate fields at the bottom of each PDF:
- Total shares repurchased in the month
- Cumulative YTD shares since 1 January
- Cumulative YTD % of issued share capital

### PDF Parsing
Monthly Return PDFs are structured (not scanned) — `pdfplumber` extracts the tables reliably:

```python
import pdfplumber, io, requests

def parse_monthly_return(pdf_url):
    r = requests.get(pdf_url, timeout=20)
    rows = []
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if row and is_date_row(row[0]):
                        rows.append({
                            "date":    row[0].strip(),
                            "shares":  clean_int(row[1]),
                            "high":    clean_float(row[2]),
                            "low":     clean_float(row[3]),
                            "consid":  clean_float(row[4]),
                        })
    return rows
```

**Fallback:** If PDF parsing fails (image PDF), store filing metadata only (date, URL). Log to `data/last_run.json`.

---

## Data Source 2: Repurchase Mandate (AGM Circulars)

**What to scrape:** Each year companies seek fresh shareholder approval at their AGM to repurchase up to 10% of issued share capital (standard Listing Rule 10.06 mandate). The mandate document is filed as a circular ahead of the AGM.

**Portal:** Same HKEXnews Title Search  
**Headline categories to filter:**
- `"General Mandate"` (under Circulars section — covers the annual repurchase mandate approval)
- `"Explanatory Statement for Repurchase of Shares"` (standalone circular filed under Listing Rules when a company first establishes a programme, or renews it outside the AGM)
- `"Document issued pursuant to Code on Share Buy-backs"` (sometimes used for mandate-related notices)

**Search strategy:**
```python
# Step 1: Fetch all circulars for the stock in the last 15 months
circulars = fetch_filings(code, doc_type="circular", months=15)

# Step 2: Filter to those containing mandate keywords
mandate_docs = [
    c for c in circulars
    if any(kw in c["title"].upper() for kw in [
        "REPURCHASE MANDATE",
        "GENERAL MANDATE TO REPURCHASE",
        "EXPLANATORY STATEMENT",
        "REPURCHASE OF SHARES"
    ])
]

# Step 3: Parse the most recent one for mandate size and approval date
if mandate_docs:
    latest = mandate_docs[0]
    mandate = parse_mandate_circular(latest["pdf_url"])
```

**Parsing the mandate circular PDF:**

The Explanatory Statement (required by HKEX Code on Share Buy-backs) contains a standardised paragraph stating the maximum number of shares authorisable for repurchase (typically "not exceeding 10% of the total number of issued shares of the Company as at the date of passing of the relevant ordinary resolution").

Key fields to extract:
- `mandate_pct` — percentage of issued capital authorised (typically 10%)
- `mandate_shares` — absolute share count at approval date (issued_shares × mandate_pct)
- `agm_date` — date the ordinary resolution was passed
- `expiry` — typically "the earlier of: (i) the conclusion of the next AGM; (ii) the expiry of 12 months from the AGM; (iii) revocation"
- `circular_url` — link to the source PDF

**Regex patterns that reliably extract the mandate %:**
```python
import re

MANDATE_PCT_PATTERNS = [
    r"not exceed(?:ing)?\s+(\d+(?:\.\d+)?)\s*(?:per\s*cent|%)\s+of.*?issued",
    r"authoris\w+.*?repurchase.*?(\d+(?:\.\d+)?)\s*(?:per\s*cent|%)",
    r"maximum.*?(\d+(?:\.\d+)?)\s*%.*?repurchas",
]

def extract_mandate_pct(text):
    for pattern in MANDATE_PCT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return float(m.group(1))
    return 10.0  # standard default — flag for manual review
```

---

## Data Source 3: Equity Issuances

Equity issuance events expand share capital, diluting existing holders and offsetting buyback activity. They are mandatory announcements under the Listing Rules with specific headline categories.

**Portal:** HKEXnews Title Search  
**Official HKEX headline categories to scrape (Appendix 24 to Listing Rules):**

| Headline Category | What it covers | Dilutive? |
|---|---|---|
| `Placing` | Top-up placings, general/specific mandate placings | Yes — new shares to placees |
| `Issue of Shares under a General Mandate` | New shares issued without separate shareholder approval | Yes |
| `Issue of Shares under a Specific Mandate` | New shares requiring separate EGM approval | Yes |
| `Rights Issue` | Pro-rata entitlement issue to all shareholders | Yes |
| `Open Offer` | Similar to rights, but non-renounceable | Yes |
| `Issue of Convertible Securities` | CB, mandatory CB, convertible preference shares | Potentially dilutive |
| `Issue of Debt Securities` | Straight bonds (non-dilutive) | No — exclude from chart |
| `Issue of Warrants` | Warrants over new shares | Potentially dilutive |

**Key fields to extract per event:**

```python
{
    "date":          "2024-07-08",
    "type":          "placing",           # placing | rights | open_offer | convertible | warrant
    "subtype":       "top_up_placing",    # top_up_placing | general_mandate | specific_mandate
    "headline":      "Issue of Shares under a General Mandate",
    "shares":        50_000_000,          # new shares issued (None for CB until conversion)
    "consideration_hkd": 17_200_000_000, # gross proceeds
    "price_per_share":   344.0,          # placing price (None if N/A)
    "discount_pct":  4.2,                # discount to last close at announcement
    "pct_of_issued": 0.52,               # dilution as % of enlarged issued capital
    "cb_conversion_price": None,         # for convertible securities
    "cb_principal_hkd":    None,         # face value of CB
    "filing_url":    "https://www1.hkexnews.hk/...",
    "announcement_title": "Placing of New Shares under General Mandate"
}
```

**Scraping strategy:**
```python
ISSUANCE_HEADLINE_CODES = [
    "Placing",
    "Issue of Shares under a General Mandate",
    "Issue of Shares under a Specific Mandate",
    "Rights Issue",
    "Open Offer",
    "Issue of Convertible Securities",
    "Issue of Warrants",
]

def scrape_issuances(code, months=13):
    events = []
    for headline in ISSUANCE_HEADLINE_CODES:
        filings = fetch_filings(code, headline=headline, months=months)
        for f in filings:
            event = parse_issuance_announcement(f["pdf_url"], headline)
            if event:
                events.append(event)
    # Sort by date desc, deduplicate on (date, type, shares)
    return deduplicate(sorted(events, key=lambda x: x["date"], reverse=True))
```

**PDF parsing notes:**
- Placing and rights issue announcements are structured and typically state shares, price, and proceeds in the first 2 pages. `pdfplumber` extracts these reliably.
- CB announcements require extracting principal amount and conversion price — always stated prominently in the term sheet section.
- Some filings announce intent only ("proposed placing") — look for "completion announcement" or "allotment results" follow-ups to confirm execution.

---

## Data Schema (Updated)

### `data/buybacks/{code}.json`

```json
{
  "code": "00700",
  "name": "Tencent Holdings Ltd.",
  "last_updated": "2025-05-15",

  "mandate": {
    "pct": 10.0,
    "shares_authorised": 956_600_000,
    "shares_used_ytd": 156_200_000,
    "pct_used_ytd": 1.63,
    "pct_mandate_consumed": 16.3,
    "pct_remaining": 8.37,
    "agm_date": "2025-05-14",
    "expiry_note": "Earlier of 2026 AGM or 12 months from AGM",
    "circular_url": "https://www1.hkexnews.hk/listedco/listconews/sehk/..."
  },

  "summary": {
    "ytd_shares": 156_200_000,
    "ytd_consideration_hkd": 52_340_000_000,
    "ytd_pct_issued": 1.63,
    "programme_active": true,
    "vwap_hkd": 335.1
  },

  "monthly_returns": [
    {
      "period": "2025-04",
      "filing_date": "2025-05-06",
      "filing_url": "https://www1.hkexnews.hk/...",
      "shares_repurchased": 18_500_000,
      "consideration_hkd": 6_215_000_000,
      "price_high": 345.20,
      "price_low": 321.40,
      "price_avg": 336.00,
      "cum_ytd_shares": 156_200_000,
      "cum_ytd_pct_issued": 1.63,
      "days_active": 19,
      "daily_breakdown": [
        { "date": "2025-04-01", "shares": 920_000, "high": 338.4, "low": 334.2, "consid": 310_000_000 }
      ]
    }
  ],

  "issuances": [
    {
      "date": "2024-07-08",
      "type": "placing",
      "subtype": "top_up_placing",
      "shares": 50_000_000,
      "consideration_hkd": 17_200_000_000,
      "price_per_share": 344.0,
      "discount_pct": 4.2,
      "pct_of_issued": 0.52,
      "cb_conversion_price": null,
      "cb_principal_hkd": null,
      "filing_url": "https://www1.hkexnews.hk/...",
      "announcement_title": "Placing of New Shares under General Mandate"
    }
  ]
}
```

### `data/buybacks_index.json` — league table

```json
[
  {
    "code": "00700",
    "name": "Tencent Holdings Ltd.",
    "ytd_consideration_hkd": 52_340_000_000,
    "ytd_pct_issued": 1.63,
    "mandate_pct_remaining": 8.37,
    "last_filing": "2025-05-06",
    "programme_active": true,
    "net_capital_change_ytd_pct": 1.11
  }
]
```

`net_capital_change_ytd_pct` = buybacks YTD − issuances YTD (as % of issued capital). Positive = net reduction.

---

## Scraper Design

### Scripts

| Script | Purpose |
|---|---|
| `scripts/scrape_buybacks.py` | Monthly returns + mandate + issuances for a given stock or full universe |
| `scripts/build_buybacks_index.py` | Rebuilds `buybacks_index.json` from individual stock files |

### Two-mode operation

**Incremental (nightly):**
1. Check HKEXnews for new Monthly Return and issuance filings published today
2. For each affected stock, fetch and parse PDFs
3. Update individual `data/buybacks/{code}.json` files
4. Rebuild index

**Full refresh (monthly, 1st of each month):**
1. For all stocks in `universe.json`, check for any ungathered filings in the last 13 months
2. Re-parse mandate circulars (mandate may have been updated at a recent AGM)
3. Rebuild index

### Rate limiting
- Randomised 1.5–3s between requests
- Extra 2s after each PDF download (heavier payload)
- Back off exponentially on 429; log failed stocks to `data/last_run.json`

### Dependencies — add to `requirements.txt`
```
pdfplumber>=0.10.3
```

---

## GitHub Actions

### `scrape_buybacks.yml` — runs Mon–Fri 23:30 UTC (after `scrape_nightly.yml`)

```yaml
name: Scrape Buybacks (Nightly)
on:
  schedule:
    - cron: '30 23 * * 1-5'
  workflow_dispatch:
    inputs:
      mode:
        description: 'full or incremental'
        default: 'incremental'
jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: python scripts/scrape_buybacks.py --mode ${{ github.event.inputs.mode || 'incremental' }}
      - run: python scripts/build_buybacks_index.py
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "data: update buyback filings [bot]"
```

### Monthly full refresh (add to `update_universe.yml` or a new workflow)
```yaml
on:
  schedule:
    - cron: '0 3 1 * *'   # 1st of each month, 03:00 UTC
```

---

## Frontend Integration

### By Stock view layout (top → bottom)

```
┌──────────────────────────────────────────────────────────┐
│  MANDATE PROGRESS BAR  ← new, always first               │
│  Approved at AGM · 10% mandate · ████░░░░ 1.63% used     │
│  8.37% headroom remaining · Expires 2026 AGM · [PDF ↗]   │
└──────────────────────────────────────────────────────────┘

  Stock name  [00700]  ● Active

┌──────────────────────────────────────────────────────────┐
│  DI cross-reference banner                                │
└──────────────────────────────────────────────────────────┘

  [Metric cards: YTD spend / Shares / Avg price / Monthly avg]

┌──────────────────────────────────────────────────────────┐
│  COMBINED 1-YEAR CHART  ← new, replaces monthly bar       │
│                                                           │
│  Price (HK$) line      ← primary y-axis                  │
│  Buyback bars          ← secondary y-axis (HK$B/month)   │
│  Equity event markers  ← vertical annotations:           │
│    ▼ Placing  ◆ CB  ○ Rights  (coloured dashed lines)    │
│                                                           │
│  Legend: [Price ──] [Buyback ▌] [Placing ▼] [CB ◆]      │
└──────────────────────────────────────────────────────────┘

  Monthly returns table (unchanged)
```

### Equity event visual encoding on chart

| Type | Shape | Colour | Label |
|---|---|---|---|
| Top-up Placing | ▼ inverted triangle | Red | P |
| Rights Issue / Open Offer | ● circle | Purple | RI |
| Convertible Bond | ◆ diamond | Amber | CB |
| Warrant | △ triangle | Pink | W |

Vertical dashed lines are drawn at the event month using a custom Chart.js plugin (no extra CDN dependency).

### Integration with DI "By Stock" tab
Add a compact "Buyback activity" summary row beneath the shareholder table showing the last 3 months' total spend, with a "View full tracker →" link.

---

## Build Order (updated)

1. Add `pdfplumber` to `requirements.txt`
2. `scripts/scrape_buybacks.py` — test with `--code 00700 --months 3`
3. `scripts/build_buybacks_index.py`
4. Seed `data/buybacks/00700.json` with 12 months of real data incl. mandate + issuances
5. Seed `data/buybacks_index.json` with top 20 stocks
6. Update `docs/buybacks.html` — mandate bar + combined chart
7. `.github/workflows/scrape_buybacks.yml`
8. Wire compact summary into existing DI stock view (`docs/app.js`)

---

## Comparison vs DI Scraper

| | DI Scraper | Buyback Scraper |
|---|---|---|
| Source portal | `di.hkex.com.hk` ASP.NET | HKEXnews JSON API |
| Auth required | VIEWSTATE tokens per request | None — clean GET |
| Primary data format | HTML tables | PDF (structured) |
| PDF parsing needed | No | Yes — `pdfplumber` |
| Filing frequency | Daily possible | Monthly returns + ad hoc issuances |
| Historical depth | 5+ years | 12–24 months practical |
| Additional scrape types | Single (DI filings) | Three: returns + mandate + issuances |

---

## Open Questions

- **Mandate headroom alert:** Could trigger a GitHub Issue (or email) when remaining mandate falls below 2% — indicating programme will need renewal soon.
- **CB conversion tracking:** CBs don't dilute until converted. Should Circular track announced conversions separately? Requires watching for `"Conversion of Securities"` headline category.
- **Net capital change:** `buybacks_index.json` will carry `net_capital_change_ytd_pct` which is a useful single-number summary. Consider surfacing this as a column in the league table.
- **Placing discount analysis:** For each placing event, the discount to last close at announcement date is extractable. Over time this becomes a dataset on how aggressively (or defensively) a company prices its dilutive issuances.
