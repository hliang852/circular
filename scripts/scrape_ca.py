#!/usr/bin/env python3
"""
CA scraper — Monthly Returns + Next Day Disclosure Returns from HKEXnews.

Sources:
  Monthly Returns (t1=51500): FF301 form — issued share movements per month
  Next Day Disclosure Returns (t1=50000, t2=50100): FF305 form — daily buyback events

Output:
  docs/data/ca/<code>.json   per-stock detail
  docs/data/ca_index.json    league table summary
  docs/data/last_run.json    updated ca block
"""

import json, re, time, os, sys, io
from datetime import datetime, date, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
except ImportError:
    os.system(f"{sys.executable} -m pip install pdfplumber -q")
    import pdfplumber

try:
    import yfinance as yf
except ImportError:
    os.system(f"{sys.executable} -m pip install yfinance -q")
    import yfinance as yf

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
CA_DIR = DATA_DIR / "ca"
CA_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ───────────────────────────────────────────────────────────────────
HKEX_BASE = "https://www1.hkexnews.hk"
SEARCH_URL = f"{HKEX_BASE}/search/titlesearch.xhtml"
T1_MONTHLY = "51500"    # Monthly Returns
T1_NDDR    = "50000"    # Next Day Disclosure Returns
T2_BUYBACK = "50100"    # Share Buyback (under NDDR)
LOOKBACK_MONTHS = 24    # how many months of history to fetch
REQUEST_DELAY = 1.5     # seconds between requests (be polite)
MAX_NDDR_DAYS = 90      # days back for NDDR scan

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})


# ── Stock universe with internal HKEX IDs ───────────────────────────────────
def load_stock_index():
    """Load the HKEX active stock list to get internal IDs (i field)."""
    resp = SESSION.get(f"{HKEX_BASE}/ncms/script/eds/activestock_sehk_e.json")
    resp.raise_for_status()
    return {s["c"]: s["i"] for s in resp.json()}  # code -> internal_id


def load_universe():
    upath = DATA_DIR / "universe.json"
    if upath.exists():
        return json.loads(upath.read_text())
    return []


# ── HKEXnews filing list ─────────────────────────────────────────────────────
def get_filing_list(internal_id, t1code, t2code, from_date, to_date):
    """Return list of {date, href, title} dicts for a stock's filings."""
    url = (
        f"{SEARCH_URL}?lang=en&category=0&market=SEHK&searchType=1"
        f"&t1code={t1code}&t2Gcode=-2&t2code={t2code}"
        f"&stockId={internal_id}"
        f"&from={from_date.strftime('%Y%m%d')}&to={to_date.strftime('%Y%m%d')}"
    )
    resp = SESSION.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        return []
    filings = []
    for row in table.find_all("tr")[1:]:  # skip header
        cols = row.find_all(["td", "th"])
        if len(cols) < 4:
            continue
        date_text = cols[0].get_text(strip=True).replace("Release Time:", "").strip()
        a = cols[3].find("a")
        if not a:
            continue
        href = a.get("href", "")
        title = a.get_text(strip=True)
        # Parse date "DD/MM/YYYY HH:MM"
        try:
            filing_date = datetime.strptime(date_text[:10], "%d/%m/%Y").date()
        except Exception:
            continue
        filings.append({"date": filing_date, "href": href, "title": title})
    return filings


# ── PDF download + parse ─────────────────────────────────────────────────────
def download_pdf(href):
    """Download a PDF and return bytes, or None on failure."""
    url = f"{HKEX_BASE}{href}" if href.startswith("/") else href
    try:
        resp = SESSION.get(url, timeout=20)
        if resp.status_code == 200 and resp.content[:4] == b"%PDF":
            return resp.content
    except Exception:
        pass
    return None


def extract_text_from_pdf(pdf_bytes):
    """Extract all page texts as a list."""
    pages = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages.append(t)
    except Exception:
        pass
    return pages


# ── FF301 Monthly Return parser ──────────────────────────────────────────────
def parse_monthly_return(pages):
    """
    Parse FF301 Monthly Return PDF.
    Returns dict with:
      period        str  "YYYY-MM"
      issued_shares int  balance at close of month (excl. treasury)
      repurchase_cancelled int  shares repurchased and cancelled in the month
    """
    full = "\n".join(pages)
    result = {}

    # Period: "For the month ended: DD Month YYYY"
    m = re.search(r"For the month ended:\s*(\d{1,2}\s+\w+\s+\d{4})", full)
    if m:
        try:
            d = datetime.strptime(m.group(1).strip(), "%d %B %Y")
            result["period"] = d.strftime("%Y-%m")
        except Exception:
            pass
    if "period" not in result:
        # Fallback: look for "month ended" date in other formats
        m2 = re.search(r"month ended[:\s]+(\d{1,2})\s+(\w+)\s+(\d{4})", full, re.I)
        if m2:
            try:
                d = datetime.strptime(f"{m2.group(1)} {m2.group(2)} {m2.group(3)}", "%d %B %Y")
                result["period"] = d.strftime("%Y-%m")
            except Exception:
                pass

    # Issued shares at close of month (Section II, "Balance at close of the month")
    # Pattern: lines with the balance numbers
    m = re.search(
        r"Balance at close of the month\s+([\d,]+)\s+[\d,]*\s+([\d,]+)",
        full
    )
    if m:
        result["issued_shares"] = int(m.group(2).replace(",", ""))

    # Section E: Repurchase of shares (shares repurchased and cancelled)
    # "Repurchase of shares (shares repurchased and cancelled)" followed by date and amount
    # EE1 total
    m = re.search(
        r"Increase/\s*decrease.*?in issued shares.*?:\s*(-?[\d,]+)\s+Ordinary shares\s*\(EE1\)",
        full, re.I | re.S
    )
    if m:
        result["repurchase_cancelled"] = abs(int(m.group(1).replace(",", "")))

    # Alternative: look for the negative number before EE1
    if "repurchase_cancelled" not in result:
        m = re.search(r"(-[\d,]+)\s+Ordinary shares\s*\(EE1\)", full)
        if m:
            result["repurchase_cancelled"] = abs(int(m.group(1).replace(",", "")))

    if "repurchase_cancelled" not in result:
        result["repurchase_cancelled"] = 0

    return result


# ── FF305 Next Day Disclosure Return parser ───────────────────────────────────
def parse_nddr(pages):
    """
    Parse FF305 NDDR PDF.
    Returns list of dicts: {date, shares, avg_price_hkd}
    for each repurchase event found in Section B.
    """
    full = "\n".join(pages)
    events = []

    # Section B: "Shares repurchased for cancellation but not yet cancelled"
    # Each entry: shares, %, price HKD xxx.xxx, Date of changes DD Month YYYY
    # Also look at Section II for same-day repurchase events in Section A
    # Pattern in Section B:
    #   N). Shares repurchased for cancellation but not yet cancelled  SHARES  PCT%  HKD PRICE
    #   Date of changes  DD Month YYYY

    # Try to find daily repurchase entries
    # Each entry looks like:
    # "N). Shares repurchased...  610,000  0.00668 %  HKD 493.0139\nDate of changes 27 March 2026"
    b_section = re.search(r"Section B\b|B\.\s*Shares redeemed", full, re.I)

    # Scan for repurchase blocks
    pattern = re.compile(
        r"Shares repurchased for cancellation but not yet cancelled\s+([\d,]+)\s+"
        r"([\d.]+)\s*%\s+HKD\s+([\d.]+)\s+"
        r"Date of changes\s+(\d{1,2})\s+(\w+)\s+(\d{4})",
        re.I
    )
    for m in pattern.finditer(full):
        shares = int(m.group(1).replace(",", ""))
        price = float(m.group(3))
        try:
            ev_date = datetime.strptime(f"{m.group(4)} {m.group(5)} {m.group(6)}", "%d %B %Y").date()
        except Exception:
            continue
        events.append({"date": ev_date.isoformat(), "shares": shares, "avg_price_hkd": price})

    # Section A: same-day repurchases (the main body)
    # "Repurchase of shares (shares repurchased for cancellation)"
    # Number of issued shares ... Date of changes DD Month YYYY  SHARES  PRICE
    a_pattern = re.compile(
        r"Repurchase of shares.*?cancellation\).*?"
        r"Date of changes\s+(\d{1,2})\s+(\w+)\s+(\d{4})\s+"
        r"(-[\d,]+|[\d,]+)\s+([\d.]+)\s*%\s+([\d.]+)",
        re.I | re.S
    )
    for m in a_pattern.finditer(full):
        try:
            ev_date = datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
            shares = abs(int(m.group(4).replace(",", "")))
            price = float(m.group(6))
            events.append({"date": ev_date.isoformat(), "shares": shares, "avg_price_hkd": price})
        except Exception:
            continue

    # Deduplicate by date (keep highest shares if duplicate)
    by_date = {}
    for ev in events:
        d = ev["date"]
        if d not in by_date or ev["shares"] > by_date[d]["shares"]:
            by_date[d] = ev
    return sorted(by_date.values(), key=lambda x: x["date"])


# ── Price fetch ──────────────────────────────────────────────────────────────
def _hk_ticker(code):
    """Format stock code as Yahoo Finance HK ticker (4-digit zero-padded)."""
    n = int(code)
    return f"{n:04d}.HK"


def fetch_current_price(code):
    """Fetch current HKD price via yfinance."""
    ticker = _hk_ticker(code)
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        if price:
            return round(float(price), 4)
    except Exception:
        pass
    return None


def fetch_price_history(code, months=24):
    """Fetch monthly close prices for the past N months."""
    ticker = _hk_ticker(code)
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{months}mo", interval="1mo")
        result = []
        for idx, row in hist.iterrows():
            result.append({
                "period": idx.strftime("%Y-%m"),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })
        return result
    except Exception:
        return []


# ── Per-stock scraper ─────────────────────────────────────────────────────────
def scrape_stock(code, name, internal_id):
    print(f"  Scraping {code} {name}...")

    today = date.today()
    from_date = today - timedelta(days=LOOKBACK_MONTHS * 31)
    nddr_from = today - timedelta(days=MAX_NDDR_DAYS)

    # 1. Monthly Returns
    print(f"    Monthly Returns...")
    monthly_filings = get_filing_list(internal_id, T1_MONTHLY, "-2", from_date, today)
    time.sleep(REQUEST_DELAY)

    monthly_data = []  # [{period, issued_shares, repurchase_cancelled}]
    for f in monthly_filings:
        pdf_bytes = download_pdf(f["href"])
        time.sleep(REQUEST_DELAY)
        if not pdf_bytes:
            continue
        pages = extract_text_from_pdf(pdf_bytes)
        parsed = parse_monthly_return(pages)
        if parsed.get("period"):
            parsed["filing_date"] = f["date"].isoformat()
            monthly_data.append(parsed)

    monthly_data.sort(key=lambda x: x["period"])

    # 2. Next Day Disclosure Returns (Share Buyback)
    print(f"    NDDRs...")
    nddr_filings = get_filing_list(internal_id, T1_NDDR, T2_BUYBACK, nddr_from, today)
    time.sleep(REQUEST_DELAY)

    nddr_events = []  # list of {date, shares, avg_price_hkd}
    for f in nddr_filings:
        pdf_bytes = download_pdf(f["href"])
        time.sleep(REQUEST_DELAY)
        if not pdf_bytes:
            continue
        pages = extract_text_from_pdf(pdf_bytes)
        evs = parse_nddr(pages)
        nddr_events.extend(evs)

    # Deduplicate NDDR events
    by_date = {}
    for ev in nddr_events:
        d = ev["date"]
        if d not in by_date or ev["shares"] > by_date[d]["shares"]:
            by_date[d] = ev
    nddr_events = sorted(by_date.values(), key=lambda x: x["date"])

    # 3. Current price + history
    print(f"    Price history...")
    current_price = fetch_current_price(code)
    price_history = fetch_price_history(code, months=LOOKBACK_MONTHS)
    price_by_period = {p["period"]: p for p in price_history}

    # 4. Aggregate stats
    # Total shares bought (from monthly data repurchase_cancelled)
    total_shares_cancelled = sum(m.get("repurchase_cancelled", 0) for m in monthly_data)

    # Also add current-month NDDR shares (not yet in a monthly filing)
    current_month = today.strftime("%Y-%m")
    monthly_periods = {m["period"] for m in monthly_data}
    if current_month not in monthly_periods and nddr_events:
        current_month_nddr = sum(
            ev["shares"] for ev in nddr_events
            if ev["date"].startswith(current_month)
        )
        total_shares_cancelled += current_month_nddr

    # VWAP from NDDR events
    total_notional = sum(ev["shares"] * ev["avg_price_hkd"] for ev in nddr_events if ev.get("avg_price_hkd"))
    total_nddr_shares = sum(ev["shares"] for ev in nddr_events if ev.get("avg_price_hkd"))
    vwap = round(total_notional / total_nddr_shares, 4) if total_nddr_shares > 0 else None

    # Estimate cumulative notional from monthly data (approximate: shares * vwap)
    # Better: use NDDR for recent + estimate for older months
    cumulative_notional = total_notional  # from NDDR window
    # For months before NDDR window, estimate using monthly repurchase counts and close price
    for m in monthly_data:
        period_str = m["period"]
        if period_str < nddr_from.strftime("%Y-%m"):
            shares = m.get("repurchase_cancelled", 0)
            if shares > 0:
                price_info = price_by_period.get(period_str)
                if price_info:
                    cumulative_notional += shares * price_info["close"]

    # Issued shares (latest)
    latest_monthly = monthly_data[-1] if monthly_data else {}
    issued_shares = latest_monthly.get("issued_shares", 0)

    # Mandate: HK listing rules allow up to 10% of issued shares
    MANDATE_PCT = 10.0
    mandate_shares = issued_shares * MANDATE_PCT / 100 if issued_shares else 0
    mandate_consumed = (total_shares_cancelled / mandate_shares * 100) if mandate_shares > 0 else 0
    mandate_consumed = min(mandate_consumed, 100.0)
    pct_issued = (total_shares_cancelled / issued_shares * 100) if issued_shares > 0 else 0

    # Programme active = NDDR events in last 90 days OR buybacks in last 6 monthly returns
    recent_cutoff = (today - timedelta(days=180)).strftime("%Y-%m")
    recent_monthly_buybacks = sum(
        m.get("repurchase_cancelled", 0) for m in monthly_data
        if m.get("period", "") >= recent_cutoff
    )
    programme_active = len(nddr_events) > 0 or recent_monthly_buybacks > 0

    # Last filing date
    last_filing_date = nddr_filings[0]["date"].isoformat() if nddr_filings else (
        monthly_filings[0]["date"].isoformat() if monthly_filings else None
    )

    # Consistency score: how many of the last 12 months had buybacks → mapped to 0-5 tier
    # 0 → 0 (none), 1-3 → 1 (Erratic), 4-6 → 2 (Opportunistic),
    # 7-9 → 3 (Regular), 10-11 → 4 (Systematic), 12 → 5 (Daily)
    recent_months = [m for m in monthly_data if m["period"] >= (today - timedelta(days=365)).strftime("%Y-%m")]
    months_with_buyback = sum(1 for m in recent_months if m.get("repurchase_cancelled", 0) > 0)
    if months_with_buyback == 0:   consistency_score = 0
    elif months_with_buyback <= 3: consistency_score = 1
    elif months_with_buyback <= 6: consistency_score = 2
    elif months_with_buyback <= 9: consistency_score = 3
    elif months_with_buyback <= 11: consistency_score = 4
    else:                           consistency_score = 5

    # Build monthly array for frontend
    monthly_out = []
    for m in monthly_data:
        period = m["period"]
        shares = m.get("repurchase_cancelled", 0)
        price_info = price_by_period.get(period, {})
        notional = shares * price_info.get("close", vwap or 0) if shares > 0 else 0
        monthly_out.append({
            "period": period,
            "shares": shares,
            "notional": round(notional),
            "month_close": price_info.get("close"),
            "month_volume": price_info.get("volume"),
            "issued_shares": m.get("issued_shares"),
            "filing_date": m.get("filing_date"),
        })

    # Add current month from NDDR if not yet in monthly
    if current_month not in {m["period"] for m in monthly_out} and nddr_events:
        cm_events = [ev for ev in nddr_events if ev["date"].startswith(current_month)]
        if cm_events:
            cm_shares = sum(ev["shares"] for ev in cm_events)
            cm_notional = sum(ev["shares"] * ev.get("avg_price_hkd", 0) for ev in cm_events)
            monthly_out.append({
                "period": current_month,
                "shares": cm_shares,
                "notional": round(cm_notional),
                "month_close": current_price,
                "month_volume": None,
                "issued_shares": issued_shares,
                "filing_date": None,
                "partial": True,
            })

    # AGM date estimate: March-May of current year (typical HK pattern)
    agm_year = today.year if today.month <= 6 else today.year + 1
    agm_date = f"{agm_year}-05-01"  # placeholder

    # Renew probability: high if mandate consumed > 70% or AGM coming up
    renew_prob = min(100, int(mandate_consumed * 1.2)) if mandate_consumed > 40 else int(mandate_consumed * 0.8)

    # Free float (approximate from public information — default to 30-50%)
    free_float_pct = 35.0  # conservative default; could be enriched from DI data

    # Buyback yield
    buyback_yield = pct_issued

    # Last session: most recent NDDR event
    last_session = nddr_events[-1] if nddr_events else None

    out = {
        "code": code,
        "name": name,
        "programme_active": programme_active,
        "mandate_pct": MANDATE_PCT,
        "mandate_consumed_pct": round(mandate_consumed, 2),
        "shares_issued": issued_shares,
        "shares_bought": total_shares_cancelled,
        "pct_issued": round(pct_issued, 4),
        "cumulative_notional": round(cumulative_notional),
        "vwap_hkd": vwap,
        "current_price_hkd": current_price,
        "buyback_yield_pct": round(buyback_yield, 4),
        "free_float_pct": free_float_pct,
        "consistency_score": consistency_score,
        "last_filing_date": last_filing_date,
        "agm_date": agm_date,
        "renew_probability": renew_prob,
        "monthly": monthly_out,
        "events": nddr_events,
        "last_session": last_session,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
    }

    # Save
    out_path = CA_DIR / f"{code}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"    Saved {out_path.name}: {len(monthly_out)} months, {len(nddr_events)} NDDR events")
    return out


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="CA scraper")
    parser.add_argument("--codes", nargs="*", help="Specific stock codes to scrape (default: all in universe)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of stocks")
    args = parser.parse_args()

    print("Loading stock index...")
    stock_index = load_stock_index()

    universe = load_universe()
    if not universe:
        print("ERROR: universe.json not found. Run build_universe.py first.")
        sys.exit(1)

    # Filter to requested codes or use full universe
    if args.codes:
        stocks = [s for s in universe if s["code"] in args.codes]
        # Also include codes from ca_index.json that aren't in universe
        existing_index_path = DATA_DIR / "ca_index.json"
        if existing_index_path.exists():
            ca_idx = {r["code"]: r for r in json.loads(existing_index_path.read_text())}
            universe_codes = {s["code"] for s in universe}
            for c in args.codes:
                if c not in universe_codes and c in ca_idx:
                    stocks.append({"code": c, "name": ca_idx[c].get("name", c)})
    else:
        stocks = universe

    if args.limit:
        stocks = stocks[:args.limit]

    print(f"Scraping {len(stocks)} stocks...")

    index_rows = []
    errors = []

    for stock in stocks:
        code = stock["code"]
        name = stock.get("name", code)
        internal_id = stock_index.get(code)
        if not internal_id:
            print(f"  SKIP {code}: not in HKEX active stock index")
            continue
        try:
            data = scrape_stock(code, name, internal_id)
            index_rows.append({
                "code": data["code"],
                "name": data["name"],
                "programme_active": data["programme_active"],
                "cumulative_notional": data["cumulative_notional"],
                "shares_bought": data["shares_bought"],
                "pct_issued": data["pct_issued"],
                "mandate_consumed_pct": data["mandate_consumed_pct"],
                "vwap_hkd": data["vwap_hkd"],
                "current_price_hkd": data["current_price_hkd"],
                "consistency_score": data["consistency_score"],
                "free_float_pct": data["free_float_pct"],
                "agm_date": data["agm_date"],
                "renew_probability": data["renew_probability"],
                "last_filing_date": data["last_filing_date"],
                "last_session": data.get("last_session"),
            })
        except Exception as e:
            print(f"  ERROR {code}: {e}")
            errors.append({"code": code, "error": str(e)})

    # Merge with existing index (preserve entries not scraped this run)
    existing_index_path = DATA_DIR / "ca_index.json"
    existing_index = {}
    if existing_index_path.exists():
        for row in json.loads(existing_index_path.read_text()):
            existing_index[row["code"]] = row
    for row in index_rows:
        existing_index[row["code"]] = row

    # Sort by cumulative notional desc
    final_index = sorted(existing_index.values(), key=lambda x: x.get("cumulative_notional", 0), reverse=True)
    existing_index_path.write_text(json.dumps(final_index, indent=2, default=str))
    print(f"\nca_index.json: {len(final_index)} entries")

    # Update last_run.json
    last_run_path = DATA_DIR / "last_run.json"
    last_run = {}
    if last_run_path.exists():
        try:
            last_run = json.loads(last_run_path.read_text())
        except Exception:
            pass
    last_run["ca"] = {
        "last_run": datetime.utcnow().isoformat() + "Z",
        "stocks_scraped": len(index_rows),
        "errors": len(errors),
        "mode": "full" if not args.codes else "partial",
    }
    last_run_path.write_text(json.dumps(last_run, indent=2))
    print("last_run.json updated")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  {e['code']}: {e['error']}")


if __name__ == "__main__":
    main()
