#!/usr/bin/env python3
"""
Build data/universe.json: all HKEX-listed stocks with market cap > $100M USD.

Usage:
    python scripts/build_universe.py          # Full run
    python scripts/build_universe.py --test   # 5 stocks only (for development)
"""

import argparse
import io
import json
import time
import random
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

HKEX_LIST_URL = (
    "https://www.hkex.com.hk/eng/services/trading/securities/"
    "securitieslists/ListOfSecurities.xlsx"
)
MKTCAP_THRESHOLD_USD = 100_000_000
BATCH_SIZE = 50
BATCH_DELAY = 1.0
OUTPUT_PATH = Path("docs/data/universe.json")
ERRORS_PATH = Path("docs/data/last_run.json")

# Well-known codes for --test mode (numeric, formatted below)
TEST_CODES = [700, 9988, 5, 1299, 2318, 939, 1398, 941, 3690, 388]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def yahoo_ticker(code: int) -> str:
    """700 → '0700.HK'"""
    return f"{code:04d}.HK"


def di_code(code: int) -> str:
    """700 → '00700'"""
    return f"{code:05d}"


def fetch_hkex_stock_codes() -> list[int]:
    """Download HKEX listed securities Excel and return numeric codes for equity stocks."""
    print("Fetching HKEX listed securities list…")
    resp = requests.get(HKEX_LIST_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()

    # Excel has a 2-row header preamble; actual column headers are on row index 2
    df = pd.read_excel(io.BytesIO(resp.content), header=2, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    code_col = next(c for c in df.columns if "Stock Code" in c or "股份代號" in c)
    cat_col = next(
        (c for c in df.columns if "Category" in c or "類別" in c),
        None,
    )

    if cat_col:
        df = df[df[cat_col].astype(str).str.contains("Equity", case=False, na=False)]

    codes = pd.to_numeric(df[code_col], errors="coerce").dropna().astype(int).tolist()
    codes = [c for c in codes if 1 <= c <= 99999]
    print(f"  Found {len(codes)} equity stock codes")
    return sorted(set(codes))


def fetch_market_caps(codes: list[int], errors: list) -> list[dict]:
    """
    Query yfinance in batches. Returns list of universe dicts for stocks
    that pass the $100M USD market cap threshold.
    """
    results = []
    today = date.today().isoformat()
    tickers = [yahoo_ticker(c) for c in codes]

    total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx, batch_start in enumerate(range(0, len(tickers), BATCH_SIZE)):
        batch_tickers = tickers[batch_start : batch_start + BATCH_SIZE]
        batch_codes = codes[batch_start : batch_start + BATCH_SIZE]
        print(f"  Batch {batch_idx + 1}/{total_batches} ({len(batch_tickers)} tickers)…")

        try:
            data = yf.Tickers(" ".join(batch_tickers))
        except Exception as e:
            for code in batch_codes:
                errors.append({"code": di_code(code), "reason": f"batch init error: {e}"})
            continue

        for ticker_str, code in zip(batch_tickers, batch_codes):
            try:
                info = data.tickers[ticker_str].info
                mktcap = info.get("marketCap")
                if not mktcap:
                    errors.append({"code": di_code(code), "reason": "no marketCap"})
                    continue

                currency = info.get("currency", "HKD")
                if currency == "HKD":
                    mktcap_hkd = mktcap
                    mktcap_usd = mktcap / 7.8
                elif currency == "USD":
                    mktcap_usd = mktcap
                    mktcap_hkd = mktcap * 7.8
                else:
                    errors.append(
                        {"code": di_code(code), "reason": f"unexpected currency {currency}"}
                    )
                    continue

                if mktcap_usd < MKTCAP_THRESHOLD_USD:
                    continue

                name = (
                    info.get("longName") or info.get("shortName") or ticker_str
                ).upper()

                results.append(
                    {
                        "code": di_code(code),
                        "name": name,
                        "mktcap_usd": int(mktcap_usd),
                        "mktcap_hkd": int(mktcap_hkd),
                        "last_updated": today,
                    }
                )
            except Exception as e:
                errors.append({"code": di_code(code), "reason": str(e)})

        if batch_start + BATCH_SIZE < len(tickers):
            time.sleep(BATCH_DELAY + random.uniform(0, 0.5))

    return results


def save_errors(errors: list) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if ERRORS_PATH.exists():
        try:
            existing = json.loads(ERRORS_PATH.read_text())
        except Exception:
            pass
    existing["build_universe_errors"] = errors
    existing["build_universe_run"] = date.today().isoformat()
    ERRORS_PATH.write_text(json.dumps(existing, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build HKEX universe JSON")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run with 5 hardcoded stocks for quick testing",
    )
    args = parser.parse_args()

    errors: list = []

    if args.test:
        print(f"TEST MODE: using {len(TEST_CODES)} hardcoded stock codes")
        codes = TEST_CODES
    else:
        codes = fetch_hkex_stock_codes()

    print(f"Fetching market caps for {len(codes)} stocks…")
    stocks = fetch_market_caps(codes, errors)

    stocks.sort(key=lambda x: x["mktcap_usd"], reverse=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(stocks, indent=2))

    print(f"\nDone. {len(stocks)} stocks passed $100M USD threshold.")
    if errors:
        print(f"  {len(errors)} errors logged to {ERRORS_PATH}")
    print(f"  Output: {OUTPUT_PATH}")
    save_errors(errors)


if __name__ == "__main__":
    main()
