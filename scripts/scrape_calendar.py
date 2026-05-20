#!/usr/bin/env python3
"""
Calendar scraper — AGM notices and results announcements from HKEXnews.

Searches for:
  - Shareholders' Meeting / AGM notices  (t1=10038)
  - Annual/Interim Results announcements (t1=10000, filtered by title)

Output:
  docs/data/calendar.json   list of {date, type, code, name, title, url}
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

# Look back 18 months, forward 12 months
DATE_FROM = (date.today() - timedelta(days=18*30)).strftime("%Y%m%d")
DATE_TO   = (date.today() + timedelta(days=365)).strftime("%Y%m%d")

REQUEST_DELAY = 1.2

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
})


def load_stock_index():
    resp = SESSION.get(f"{HKEX_BASE}/ncms/script/eds/activestock_sehk_e.json")
    resp.raise_for_status()
    return {s["c"]: {"internal_id": s["i"], "name": s.get("n", s["c"])} for s in resp.json()}


def load_universe():
    upath = DATA_DIR / "universe.json"
    if not upath.exists():
        return []
    return json.loads(upath.read_text())


def search_filings(internal_id, t1code, t2code="-2", from_date=DATE_FROM, to_date=DATE_TO):
    """Return list of {date, title, href} for a stock's filings."""
    url = (
        f"{SEARCH_URL}?lang=en&category=0&market=SEHK&searchType=1"
        f"&t1code={t1code}&t2Gcode=-2&t2code={t2code}"
        f"&stockId={internal_id}"
        f"&from={from_date}&to={to_date}"
    )
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Request error: {e}")
        return []

    try:
        data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("result", {}).get("list", []):
        d = item.get("date", "")
        # Convert YYYYMMDD to YYYY-MM-DD
        if len(d) == 8:
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        results.append({
            "date": d,
            "title": item.get("title", ""),
            "href": item.get("href", ""),
        })
    return results


def classify_filing(title):
    """Return event type or None if not relevant."""
    t = title.lower()
    if any(k in t for k in ["annual general meeting", "agm", "shareholders' meeting",
                              "shareholder's meeting", "general meeting notice"]):
        return "agm"
    if any(k in t for k in ["annual results", "final results", "full year results"]):
        return "results_annual"
    if any(k in t for k in ["interim results", "half year results", "half-year results",
                              "six months results"]):
        return "results_interim"
    return None


def scrape_stock(code, internal_id, name):
    events = []
    print(f"  Scraping {code} — {name}")

    # AGM notices (t1=10038: Shareholders' Meeting)
    filings = search_filings(internal_id, "10038")
    time.sleep(REQUEST_DELAY)
    for f in filings:
        etype = classify_filing(f["title"])
        if etype == "agm":
            events.append({
                "date": f["date"],
                "type": "agm",
                "code": code,
                "name": name,
                "title": f["title"],
                "url": HKEX_BASE + f["href"] if f["href"].startswith("/") else f["href"],
            })

    # Results announcements (t1=10000: Announcements and Notices, filter by title)
    filings = search_filings(internal_id, "10000")
    time.sleep(REQUEST_DELAY)
    for f in filings:
        etype = classify_filing(f["title"])
        if etype in ("results_annual", "results_interim"):
            rtype = "results"
            note_type = "Annual Results" if etype == "results_annual" else "Interim Results"
            events.append({
                "date": f["date"],
                "type": rtype,
                "code": code,
                "name": name,
                "note": note_type,
                "title": f["title"],
                "url": HKEX_BASE + f["href"] if f["href"].startswith("/") else f["href"],
            })
            # Add estimated blackout (30 days before)
            try:
                results_date = datetime.strptime(f["date"], "%Y-%m-%d").date()
                blackout_date = results_date - timedelta(days=30)
                events.append({
                    "date": blackout_date.strftime("%Y-%m-%d"),
                    "type": "blackout",
                    "code": code,
                    "name": name,
                    "note": f"Estimated blackout start (30d before {note_type})",
                    "title": f"Blackout period for {name}",
                    "url": "",
                })
            except Exception:
                pass

    return events


def main():
    print("Loading universe…")
    universe = load_universe()
    if not universe:
        print("No universe.json found. Run build_universe.py first.")
        return

    print("Loading HKEX stock index…")
    try:
        stock_index = load_stock_index()
    except Exception as e:
        print(f"Failed to load HKEX stock index: {e}")
        return

    all_events = []
    total = len(universe)
    for i, stock in enumerate(universe):
        code = stock["code"]
        name = stock.get("name", code)
        info = stock_index.get(code)
        if not info:
            continue
        print(f"[{i+1}/{total}] {code} — {name}")
        try:
            events = scrape_stock(code, info["internal_id"], name)
            all_events.extend(events)
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(0.5)

    # Deduplicate by (date, type, code)
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
    print(f"\nDone. {len(unique)} events written to {out_path}")


if __name__ == "__main__":
    main()
