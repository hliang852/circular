#!/usr/bin/env python3
"""
Scrape HKEX Disclosure of Interests portal → data/di/{code}.json

Usage:
    python scripts/scrape_di.py --code 00700          # Single stock
    python scripts/scrape_di.py --mode incremental    # Today's filings only (default)
    python scripts/scrape_di.py --mode full           # All stocks in universe.json
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote_plus

import requests
from bs4 import BeautifulSoup

BASE = "https://di.hkex.com.hk/di"
SUMMARY_URL = f"{BASE}/summary/NSMSumMenu.htm"
UNIVERSE_PATH = Path("docs/data/universe.json")
DI_DIR = Path("docs/data/di")
ERRORS_PATH = Path("docs/data/last_run.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Referer": f"{BASE}/NSSrchCorp.aspx?src=MAIN&lang=EN&g_lang=en&",
}

# Reason code → notice type (most common HKEX DI reason codes)
REASON_TO_NOTICE = {
    "1111": "Initial",
    "1112": "Initial",
    "1201": "Increase",
    "1202": "Decrease",
    "1203": "Increase",
    "1204": "Decrease",
    "1113": "Change",
    "1114": "Change",
    "1115": "Change",
    "1500": "Change",
    "1501": "Increase",
    "1502": "Decrease",
}

# Form serial prefix → (form_type, entity_type, capacity)
PREFIX_MAP = {
    "CS": ("Form 2", "corporate", "Beneficial Owner"),
    "IS": ("Form 1", "individual", "Beneficial Owner"),
    "IM": ("Form 3", "fund", "Investment Manager"),
    "DA": ("Form 3A", "corporate", "Associated Entity"),
    "IR": ("Form 1", "individual", "Beneficial Owner"),
}


def _date_from_serial(serial: str) -> str:
    """CS20250728E00461 → '2025-07-28'"""
    m = re.match(r"[A-Z]+(\d{4})(\d{2})(\d{2})", serial)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _parse_position(raw: str) -> tuple[int, int]:
    """
    '2,961,223,600(L)' → (2961223600, 0)
    '804,859,700(L)0(S)' → (804859700, 0)
    '0(L)' → (0, 0)
    """
    raw = raw.replace(",", "").replace("\xa0", "").strip()
    long_m = re.search(r"([\d]+)\(L\)", raw)
    short_m = re.search(r"([\d]+)\(S\)", raw)
    long_v = int(long_m.group(1)) if long_m else 0
    short_v = int(short_m.group(1)) if short_m else 0
    return long_v, short_v


def _parse_pct(raw: str) -> tuple[float, float]:
    """
    '31.10(L)' → (31.10, 0.0)
    '8.42(L)0.00(S)' → (8.42, 0.0)
    """
    raw = raw.replace("\xa0", "").strip()
    long_m = re.search(r"([\d.]+)\(L\)", raw)
    short_m = re.search(r"([\d.]+)\(S\)", raw)
    long_v = float(long_m.group(1)) if long_m else 0.0
    short_v = float(short_m.group(1)) if short_m else 0.0
    return long_v, short_v


def _parse_reason(raw: str) -> tuple[str, str]:
    """
    '1201(L)' → notice_type='Increase', raw_code='1201'
    '1201(L)15015(S)' → notice_type='Change', raw_code='1201'
    """
    m = re.search(r"(\d{4})", raw)
    if not m:
        return "Change", ""
    code = m.group(1)
    return REASON_TO_NOTICE.get(code, "Change"), code


def _prefix_info(serial: str) -> tuple[str, str, str]:
    """Return (form_type, entity_type, capacity) from form serial prefix."""
    for prefix, info in PREFIX_MAP.items():
        if serial.upper().startswith(prefix):
            return info
    return ("Unknown", "corporate", "Unknown")


def _find_data_table(soup: BeautifulSoup, header_keywords: list[str]) -> list[list[str]]:
    """
    Find the table whose first row contains all header_keywords, return rows
    as lists of cell text strings.
    """
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        first_text = " ".join(td.text.strip() for td in rows[0].find_all(["td", "th"]))
        if all(kw in first_text for kw in header_keywords):
            result = []
            for row in rows:
                cells = [td.text.strip() for td in row.find_all(["td", "th"])]
                result.append(cells)
            return result
    return []


def _build_url(path: str, params: dict, encoded_slash_keys: set[str]) -> str:
    """
    Build a URL where certain params have slashes encoded as %2f (HKEX quirk).
    """
    parts = []
    for k, v in params.items():
        if k in encoded_slash_keys:
            v = str(v).replace("/", "%2f")
        parts.append(f"{k}={v}")
    return f"{BASE}/{path}?" + "&".join(parts)


def _fetch_all_pages(session: requests.Session, base_url: str, header_keywords: list[str]) -> list[list[str]]:
    """
    Fetch paginated table data. Returns all data rows (excluding header row).
    Handles HKEX's ?pg=N pagination.
    """
    all_rows: list[list[str]] = []
    header_seen = False
    page = 1

    while True:
        url = base_url + (f"&pg={page}" if page > 1 else "")
        r = session.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "lxml")
        rows = _find_data_table(soup, header_keywords)

        if not rows:
            break

        # Skip the header row on each page
        data_rows = [r for r in rows[1:] if len(r) >= 4 and any(c.strip() for c in r)]

        if not data_rows:
            break

        if not header_seen:
            all_rows = data_rows
            header_seen = True
        else:
            all_rows.extend(data_rows)

        # Check pagination: look for "Total records" to know if there are more pages
        page_text = " ".join(td.text for td in soup.find_all("td"))
        total_m = re.search(r"Total records[:\s]+(\d+)", page_text)
        displayed_m = re.search(r"Displayed[:\s]+\d+\s*-\s*(\d+)", page_text)
        if total_m and displayed_m:
            total = int(total_m.group(1))
            displayed_end = int(displayed_m.group(1))
            if displayed_end >= total:
                break
        else:
            break

        page += 1
        time.sleep(0.5)

    return all_rows


def _scrape_shareholders(session: requests.Session, sid: str, corpn_enc: str,
                          numeric_code: str, start: str, end: str) -> list[dict]:
    url = _build_url(
        "NSAllSSList.aspx",
        {
            "sa2": "as", "sid": sid, "corpn": corpn_enc,
            "sd": start, "ed": end, "cid": 0,
            "sa1": "cl", "scsd": start, "sced": end,
            "sc": numeric_code, "src": "MAIN", "lang": "EN", "g_lang": "en",
        },
        encoded_slash_keys={"scsd", "sced"},
    )

    rows = _fetch_all_pages(session, url, ["Form Serial Number", "Name of substantial shareholder"])
    shareholders = []
    for row in rows:
        if len(row) < 5:
            continue
        serial, name, shares_raw, pct_raw, filing_date_raw = row[0], row[1], row[2], row[3], row[4]
        if not re.match(r"[A-Z]{2}\d{8}", serial):
            continue

        long_shares, short_shares = _parse_position(shares_raw)
        long_pct, short_pct = _parse_pct(pct_raw)
        form_type, entity_type, capacity = _prefix_info(serial)
        filing_date = _reformat_date(filing_date_raw)

        shareholders.append({
            "name": name,
            "capacity": capacity,
            "entity_type": entity_type,
            "long_position_shares": long_shares,
            "long_position_pct": long_pct,
            "short_position_shares": short_shares,
            "short_position_pct": short_pct,
            "relevant_event_date": filing_date,
            "filing_date": filing_date,
            "form_type": form_type,
            "notice_type": "Current",
        })

    shareholders.sort(key=lambda x: x["long_position_pct"], reverse=True)
    return shareholders


def _scrape_history(session: requests.Session, sid: str, corpn_enc: str,
                     numeric_code: str, start: str, end: str) -> list[dict]:
    url = _build_url(
        "NSNoticeSSList.aspx",
        {
            "sa2": "ns", "sid": sid, "corpn": corpn_enc,
            "sd": start, "ed": end, "cid": 0,
            "sa1": "cl", "scsd": start, "sced": end,
            "sc": numeric_code, "src": "MAIN", "lang": "EN", "g_lang": "en",
        },
        encoded_slash_keys={"scsd", "sced"},
    )

    rows = _fetch_all_pages(session, url, ["Form Serial Number", "Name of substantial shareholder", "Reason"])
    history = []
    for row in rows:
        # Columns: serial, name, reason, shares_bought, avg_price, shares_total, pct, event_date
        if len(row) < 8:
            continue
        serial, name, reason_raw = row[0], row[1], row[2]
        shares_total_raw, pct_raw, event_date_raw = row[5], row[6], row[7]

        if not re.match(r"[A-Z]{2}\d{8}", serial):
            continue

        notice_type, _ = _parse_reason(reason_raw)
        long_pct, _ = _parse_pct(pct_raw)
        form_type, _, _ = _prefix_info(serial)
        filing_date = _date_from_serial(serial)
        event_date = _reformat_date(event_date_raw)

        history.append({
            "name": name,
            "long_position_pct": long_pct,
            "relevant_event_date": event_date,
            "filing_date": filing_date,
            "form_type": form_type,
            "notice_type": notice_type,
        })

    return history


def _reformat_date(raw: str) -> str:
    """'25/07/2025' → '2025-07-25'"""
    raw = raw.strip().replace("\r", "").replace("\n", "").replace("\t", "")
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", raw)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return raw


def scrape_stock(session: requests.Session, code: str, errors: list) -> dict | None:
    """
    Scrape a single stock by its 5-digit code (e.g. '00700').
    Returns the di/{code}.json dict or None on failure.
    """
    numeric_code = str(int(code))
    today = date.today()
    today_str = today.strftime("%d/%m/%Y")
    start_str = "01/01/2000"

    # --- Step 1: Corp list page → extract sid and encoded corp name ---
    list_url = _build_url(
        "NSSrchCorpList.aspx",
        {
            "sa1": "cl", "scsd": start_str, "sced": today_str,
            "sc": numeric_code, "src": "MAIN", "lang": "EN", "g_lang": "en",
        },
        encoded_slash_keys={"scsd", "sced"},
    )

    try:
        r = session.get(list_url, headers=HEADERS, timeout=30)
    except Exception as e:
        errors.append({"code": code, "reason": f"corp list GET failed: {e}"})
        return None

    soup = BeautifulSoup(r.text, "lxml")

    # Find the "Complete list of substantial shareholders" link
    link = soup.find("a", href=re.compile(r"NSAllSSList\.aspx"))
    if not link:
        errors.append({"code": code, "reason": "no NSAllSSList link found"})
        return None

    href = link["href"]
    sid_m = re.search(r"sid=(\d+)", href)
    corpn_m = re.search(r"corpn=([^&]+)", href)
    if not sid_m or not corpn_m:
        errors.append({"code": code, "reason": f"could not parse sid/corpn from {href}"})
        return None

    sid = sid_m.group(1)
    corpn_enc = corpn_m.group(1)  # URL-encoded name like "Tencent+Holdings+Ltd."
    corp_name = unquote_plus(corpn_enc)

    # --- Step 2: Scrape current substantial shareholders ---
    try:
        shareholders = _scrape_shareholders(session, sid, corpn_enc, numeric_code, start_str, today_str)
        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        errors.append({"code": code, "reason": f"shareholders scrape failed: {e}"})
        shareholders = []

    # --- Step 3: Scrape filing history ---
    try:
        history = _scrape_history(session, sid, corpn_enc, numeric_code, start_str, today_str)
        time.sleep(random.uniform(0.5, 1.0))
    except Exception as e:
        errors.append({"code": code, "reason": f"history scrape failed: {e}"})
        history = []

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "code": code,
        "name": corp_name.upper(),
        "last_scraped": now_utc,
        "shareholders": shareholders,
        "history": history,
    }


def merge_and_save(code: str, new_data: dict) -> None:
    """Merge new data with existing file, preserving history, then write."""
    out_path = DI_DIR / f"{code}.json"
    DI_DIR.mkdir(parents=True, exist_ok=True)

    existing_history: list = []
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text())
            existing_history = existing.get("history", [])
        except Exception:
            pass

    # Merge history: de-duplicate by (name + filing_date + long_position_pct)
    existing_keys = {
        (e["name"], e.get("filing_date", ""), str(e.get("long_position_pct", "")))
        for e in existing_history
    }
    for entry in new_data.get("history", []):
        key = (entry["name"], entry.get("filing_date", ""), str(entry.get("long_position_pct", "")))
        if key not in existing_keys:
            existing_history.append(entry)
            existing_keys.add(key)

    # Sort newest first
    existing_history.sort(key=lambda x: x.get("relevant_event_date", ""), reverse=True)
    new_data["history"] = existing_history

    out_path.write_text(json.dumps(new_data, indent=2, ensure_ascii=False))


def get_today_changed_codes() -> list[str]:
    """Fetch the daily summary page and return 5-digit codes with filings today."""
    s = requests.Session()
    try:
        r = s.get(SUMMARY_URL, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "lxml")

        # Find today's summary link (e.g. DSM20260515C1.htm)
        today_str = date.today().strftime("%Y%m%d")
        link = soup.find("a", href=re.compile(rf"DSM{today_str}C1\.htm"))
        if not link:
            # Try yesterday as fallback (HKEX may not have updated yet)
            print("  No today's summary link found; trying most recent link")
            link = soup.find("a", href=re.compile(r"DSM\d{8}C1\.htm"))

        if not link:
            print("  No daily summary link found")
            return []

        summary_url = f"{BASE}/summary/{link['href']}"
        r2 = s.get(summary_url, headers=HEADERS, timeout=30)
        soup2 = BeautifulSoup(r2.text, "lxml")

        codes: set[str] = set()
        # The stock code column contains 5-digit codes like '01751'
        for td in soup2.find_all("td"):
            text = td.text.strip()
            if re.match(r"^\d{4,5}$", text):
                # Zero-pad to 5 digits
                codes.add(text.zfill(5))

        print(f"  Found {len(codes)} stocks in today's DI summary")
        return sorted(codes)
    except Exception as e:
        print(f"  Failed to fetch daily summary: {e}")
        return []


def save_run_metadata(errors: list, mode: str, scraped: list[str]) -> None:
    existing = {}
    if ERRORS_PATH.exists():
        try:
            existing = json.loads(ERRORS_PATH.read_text())
        except Exception:
            pass
    existing["scrape_di_errors"] = errors
    existing["scrape_di_last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing["scrape_di_mode"] = mode
    existing["scrape_di_codes_scraped"] = len(scraped)
    ERRORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERRORS_PATH.write_text(json.dumps(existing, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape HKEX DI portal")
    parser.add_argument("--code", help="Single 5-digit stock code to scrape (e.g. 00700)")
    parser.add_argument(
        "--mode",
        choices=["incremental", "full"],
        default="incremental",
        help="incremental=today's filings only, full=all stocks in universe.json",
    )
    args = parser.parse_args()

    errors: list = []
    scraped: list[str] = []

    # Build target code list
    if args.code:
        codes = [args.code.zfill(5)]
        mode = "single"
    elif args.mode == "full":
        if not UNIVERSE_PATH.exists():
            sys.exit("data/universe.json not found. Run build_universe.py first.")
        universe = json.loads(UNIVERSE_PATH.read_text())
        codes = [s["code"] for s in universe]
        mode = "full"
    else:
        print("Fetching today's DI summary…")
        codes = get_today_changed_codes()
        mode = "incremental"
        if not codes:
            print("No filings found today. Exiting.")
            save_run_metadata(errors, mode, scraped)
            return

    # Prime session cookie
    session = requests.Session()
    session.get(
        f"{BASE}/NSSrchCorp.aspx?src=MAIN&lang=EN&g_lang=en&",
        headers=HEADERS,
        timeout=30,
    )

    total = len(codes)
    print(f"Scraping {total} stock(s) in {mode!r} mode…")

    for i, code in enumerate(codes, 1):
        print(f"  [{i}/{total}] {code}…", end=" ", flush=True)
        try:
            data = scrape_stock(session, code, errors)
            if data:
                merge_and_save(code, data)
                scraped.append(code)
                sh_count = len(data["shareholders"])
                hist_count = len(data["history"])
                print(f"ok ({sh_count} shareholders, {hist_count} filings)")
            else:
                print("skipped (no data)")
        except Exception as e:
            errors.append({"code": code, "reason": str(e)})
            print(f"ERROR: {e}")

        if i < total:
            delay = random.uniform(1.5, 3.0)
            time.sleep(delay)

    print(f"\nDone. Scraped {len(scraped)}/{total} stocks.")
    if errors:
        print(f"  {len(errors)} errors logged.")
    save_run_metadata(errors, mode, scraped)


if __name__ == "__main__":
    main()
