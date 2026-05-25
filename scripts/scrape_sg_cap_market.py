"""Capital Market scraper (Singapore).

Unlike DI and Corporate Actions, this scraper does NOT use the SGXNET API.
Sources:
  - SGX Daily Short Sell Report (CSV download per trading day)
  - yfinance daily OHLC/volume (fallback for turnover value)
  - CDP Securities Borrowing & Lending eligibility list (weekly)

connect_flows[] is stored as null per SG_SCHEMA_MAPPING.md -- Singapore
has no mainland-China connect equivalent.

Schema reference: SG_SCHEMA_MAPPING.md § Section 3.

Usage:
    python scripts/scrape_sg_cap_market.py --market sg --mode incremental
    python scripts/scrape_sg_cap_market.py --market sg --mode full
    python scripts/scrape_sg_cap_market.py --market sg --code D05
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
import yfinance as yf

from config.sgx_categories import CM_SOURCES

log = logging.getLogger(__name__)

DATA_DIR = Path("docs/data/sg/cap_market")
UNIVERSE_PATH = Path("docs/data/sg/universe.json")
LOOKBACK_WEEKS = 52


# --- short-sell report -------------------------------------------------------

def fetch_short_sell_report(date: datetime) -> dict[str, dict]:
    """Pull the SGX daily short sell report for a given trading date.

    Returns a dict keyed by stock code. Empty dict on failure (e.g. weekend).

    NOTE: the actual download URL pattern needs verification -- the SGX
    research-education page links to a daily file but the URL format varies.
    Placeholder logic below; replace with the verified URL once confirmed.
    """
    base = CM_SOURCES["daily_short_sell_url"]
    # TODO_VERIFY: real URL pattern. Likely something like:
    #   https://links.sgx.com/.../ShortSale_YYYYMMDD.csv
    # Inspect the SGX short selling page in DevTools to confirm.
    url = f"{base}?date={date.strftime('%Y%m%d')}"

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Short sell fetch failed for %s: %s", date.date(), exc)
        return {}

    # Parser assumes CSV with columns: Security, Code, ShortVolume, ShortValue,
    # TotalVolume. Adjust once real file structure is confirmed.
    out: dict[str, dict] = {}
    for line in resp.text.splitlines()[1:]:  # skip header
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 5:
            continue
        try:
            code = cols[1]
            short_vol = int(cols[2].replace(",", "") or 0)
            short_val = float(cols[3].replace(",", "") or 0)
            total_vol = int(cols[4].replace(",", "") or 0) or 1
        except (ValueError, IndexError):
            continue
        out[code] = {
            "date": date.date().isoformat(),
            "volume": short_vol,
            "value_sgd": short_val,
            "pct_of_turnover": round(short_vol / total_vol * 100, 2),
        }
    return out


# --- yfinance turnover -------------------------------------------------------

def fetch_yfinance_volume(code: str, start: datetime, end: datetime) -> list[dict]:
    """Daily volume + turnover value for a stock via yfinance.

    SGX tickers use the .SI suffix.
    """
    ticker = yf.Ticker(f"{code}.SI")
    try:
        hist = ticker.history(start=start, end=end, auto_adjust=False)
    except Exception as exc:
        log.warning("yfinance failed for %s: %s", code, exc)
        return []
    out = []
    for date, row in hist.iterrows():
        try:
            vol = int(row["Volume"])
            close = float(row["Close"])
        except (KeyError, ValueError):
            continue
        out.append({
            "date": date.date().isoformat(),
            "volume": vol,
            "value_sgd": round(vol * close, 2),
        })
    return out


# --- SBL eligibility (weekly) ------------------------------------------------

def fetch_sbl_eligible() -> set[str]:
    """Return the set of stock codes eligible for SBL.

    Placeholder -- requires real URL.
    """
    url = CM_SOURCES.get("sbl_eligibility_url")
    if not url:
        log.warning("SBL eligibility URL not configured; returning empty set")
        return set()
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        # Parse CSV/PDF as needed once format confirmed.
        return set()
    except Exception as exc:
        log.warning("SBL fetch failed: %s", exc)
        return set()


# --- per-stock JSON I/O ------------------------------------------------------

def load_stock(code: str) -> dict:
    path = DATA_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "code": code,
        "security_type": "share",
        "currency": "SGD",
        "last_updated": None,
        "short_history": [],
        "connect_flows": None,         # always null for SG
        "daily_turnover": [],
        "short_selling_eligible": False,
    }


def save_stock(code: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=LOOKBACK_WEEKS)).date().isoformat()
    for arr_key in ("short_history", "daily_turnover"):
        data[arr_key] = [r for r in data.get(arr_key, []) if r.get("date", "") >= cutoff]
    path = DATA_DIR / f"{code}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --- main loop ---------------------------------------------------------------

def run(mode: str, single_code: Optional[str] = None) -> dict:
    """Iterate codes in universe, fetch short + turnover, write per-stock JSON."""
    stats = {"stocks_touched": 0, "errors": 0, "short_days_fetched": 0}

    # Load universe (or use single code).
    if single_code:
        codes = [single_code]
    elif UNIVERSE_PATH.exists():
        universe = json.loads(UNIVERSE_PATH.read_text())
        codes = [u["code"] for u in universe.get("stocks", [])]
    else:
        log.error("No universe file at %s and no --code given", UNIVERSE_PATH)
        return stats

    # Date window
    end = datetime.now(timezone.utc)
    start = end - (timedelta(days=2) if mode == "incremental" else timedelta(weeks=LOOKBACK_WEEKS))

    # Short-sell report is per-day, so fetch all days in window once then merge.
    short_by_date_code: dict[str, dict] = {}
    d = start
    while d <= end:
        if d.weekday() < 5:  # skip Sat/Sun
            short_by_date_code[d.date().isoformat()] = fetch_short_sell_report(d)
            stats["short_days_fetched"] += 1
        d += timedelta(days=1)

    sbl_eligible = fetch_sbl_eligible()

    for code in codes:
        try:
            stock = load_stock(code)
            stock["short_selling_eligible"] = code in sbl_eligible

            # Append short history rows for this code.
            for date_iso, by_code in short_by_date_code.items():
                if code in by_code:
                    stock["short_history"].append(by_code[code])

            # Daily turnover from yfinance.
            stock["daily_turnover"].extend(fetch_yfinance_volume(code, start, end))

            # Deduplicate by date (last write wins).
            stock["short_history"] = _dedup_by_date(stock["short_history"])
            stock["daily_turnover"] = _dedup_by_date(stock["daily_turnover"])

            save_stock(code, stock)
            stats["stocks_touched"] += 1
        except Exception as exc:
            log.exception("Failed for %s: %s", code, exc)
            stats["errors"] += 1

    return stats


def _dedup_by_date(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for r in rows:
        seen[r.get("date", "")] = r
    return sorted(seen.values(), key=lambda r: r.get("date", ""))


# --- CLI ---------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, choices=["sg"])
    parser.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    parser.add_argument("--code", help="Single stock code (for testing).")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    stats = run(args.mode, args.code)

    last_run_path = Path("docs/data/sg/last_run.json")
    last_run_path.parent.mkdir(parents=True, exist_ok=True)
    last_run = json.loads(last_run_path.read_text()) if last_run_path.exists() else {}
    last_run["cap_market"] = {
        "last_scrape": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "stats": stats,
    }
    last_run_path.write_text(json.dumps(last_run, indent=2))

    log.info("Done. Stats: %s", stats)
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
