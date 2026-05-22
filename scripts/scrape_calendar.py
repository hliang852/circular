#!/usr/bin/env python3
"""
Calendar builder — generates calendar.json from:
  1. AGM dates already scraped into ca_index.json
  2. Annual/Interim report filing dates fetched from HKEXnews (t1=40000)
     as a proxy for results dates

Output:
  docs/data/calendar.json   list of {date, type, code, name, note, url}
"""

import json, re, time
from datetime import datetime, date, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

ROOT     = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

HKEX_BASE  = "https://www1.hkexnews.hk"
SEARCH_URL = f"{HKEX_BASE}/search/titlesearch.xhtml"

DATE_FROM = (date.today() - timedelta(days=18 * 30)).strftime("%Y%m%d")
DATE_TO   = (date.today() + timedelta(days=365)).strftime("%Y%m%d")

REQUEST_DELAY = 1.0

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})


def load_ca_index():
    path = DATA_DIR / "ca_index.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_stock_index():
    resp = SESSION.get(f"{HKEX_BASE}/ncms/script/eds/activestock_sehk_e.json")
    resp.raise_for_status()
    return {s["c"]: s["i"] for s in resp.json()}


def fetch_financial_statements(internal_id):
    """Fetch Annual Report and Interim Report filing dates (t1=40000)."""
    url = (
        f"{SEARCH_URL}?lang=en&category=0&market=SEHK&searchType=1"
        f"&t1code=40000&t2Gcode=-2&t2code=-2"
        f"&stockId={internal_id}"
        f"&from={DATE_FROM}&to={DATE_TO}"
    )
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    results = []
    for row in table.find_all("tr")[1:]:
        cols = row.find_all(["td", "th"])
        if len(cols) < 4:
            continue
        date_text = cols[0].get_text(strip=True).replace("Release Time:", "").strip()
        a = cols[3].find("a")
        if not a:
            continue
        title = a.get_text(strip=True)
        href  = a.get("href", "")
        try:
            filing_date = datetime.strptime(date_text[:10], "%d/%m/%Y").date()
        except Exception:
            continue

        t = title.lower()
        if "annual report" in t:
            results.append({"date": filing_date, "kind": "annual_report", "title": title, "href": href})
        elif "interim" in t or "half-year" in t or "half year" in t:
            results.append({"date": filing_date, "kind": "interim_report", "title": title, "href": href})

    return results


def main():
    print("Loading ca_index.json…")
    ca_stocks = load_ca_index()
    if not ca_stocks:
        print("No ca_index.json found. Run scrape_ca.py first.")
        return

    print("Loading HKEX stock index for internal IDs…")
    try:
        stock_index = load_stock_index()
    except Exception as e:
        print(f"Failed: {e}")
        return

    all_events = []

    # ── Part 1: AGM events from ca_index.json ──────────────────────────
    print("\n[1/2] Building AGM events from ca_index.json…")
    for stock in ca_stocks:
        agm_date = stock.get("agm_date")
        code = stock.get("code", "")
        name = stock.get("name", code)
        if not agm_date:
            continue
        try:
            d = datetime.strptime(agm_date, "%Y-%m-%d").date()
        except Exception:
            continue
        all_events.append({
            "date": agm_date,
            "type": "agm",
            "code": code,
            "name": name,
            "note": f"Annual General Meeting — repurchase mandate renewal vote",
            "url": "",
        })
    print(f"  {sum(1 for e in all_events if e['type']=='agm')} AGM events from {len(ca_stocks)} stocks")

    # ── Part 2: Results dates from Financial Statements filings ────────
    print("\n[2/2] Fetching Annual/Interim Report filing dates from HKEXnews…")
    total = len(ca_stocks)
    results_count = 0

    for i, stock in enumerate(ca_stocks):
        code = stock.get("code", "")
        name = stock.get("name", code)
        internal_id = stock_index.get(code)
        if not internal_id:
            continue

        print(f"  [{i+1}/{total}] {code} — {name[:30]}", end="", flush=True)
        filings = fetch_financial_statements(internal_id)
        time.sleep(REQUEST_DELAY)

        if not filings:
            print(" — 0 reports")
            continue

        print(f" — {len(filings)} reports")
        for f in filings:
            if f["kind"] == "annual_report":
                # Annual report published ≈ 3-4 months after year-end
                # Use filing date as "Annual Report published" event
                note = "Annual Report published"
                etype = "results"
            else:
                note = "Interim/Half-Year Report published"
                etype = "results"

            filing_iso = f["date"].isoformat()
            all_events.append({
                "date": filing_iso,
                "type": etype,
                "code": code,
                "name": name,
                "note": note,
                "url": HKEX_BASE + f["href"] if f["href"].startswith("/") else f["href"],
            })
            # Estimated blackout starts 30 days before filing date
            blackout_date = (f["date"] - timedelta(days=30)).isoformat()
            all_events.append({
                "date": blackout_date,
                "type": "blackout",
                "code": code,
                "name": name,
                "note": f"Estimated blackout start (30d before {note})",
                "url": "",
            })
            results_count += 1

    print(f"\n  {results_count} results/report events added")

    # ── Deduplicate and sort ───────────────────────────────────────────
    seen = set()
    unique = []
    for e in all_events:
        key = (e["date"], e["type"], e["code"])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    unique.sort(key=lambda e: e["date"])

    out_path = DATA_DIR / "calendar.json"
    out_path.write_text(json.dumps(unique, ensure_ascii=False, indent=2))
    print(f"\nDone. {len(unique)} events → {out_path}")


if __name__ == "__main__":
    main()
