"""Build docs/data/sg/universe.json: SGX-listed stocks with market cap > $100M USD.

Two-step approach per SG_SCHEMA_MAPPING.md open item #3:
  1. Pull the full SGX ticker list (no auth required).
  2. Enrich each with market cap via yfinance .SI suffix.
  3. Filter to > USD 100M market cap.
  4. Tag with security_type ("share" / "unit") for downstream scrapers.

Usage:
    python scripts/build_sg_universe.py --market sg
    python scripts/build_sg_universe.py --market sg --min-mcap-usd 100_000_000
    python scripts/build_sg_universe.py --market sg --limit 20    # test mode
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
import yfinance as yf

log = logging.getLogger(__name__)

OUT_PATH = Path("docs/data/sg/universe.json")

# Verified 2026-06-24 against live api.sgx.com responses:
#   /stocks  → data.prices[] (568 equities, no auth required)
#   /reits   → data.prices[] (36 REITs/trusts, no auth required)
SGX_STOCKS_URL = "https://api.sgx.com/securities/v1.1/stocks"
SGX_REITS_URL  = "https://api.sgx.com/securities/v1.1/reits"

_SGX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/json",
    "Referer": "https://www.sgx.com/",
}

# USD/SGD assumption -- refresh from a fx source in a fuller implementation.
USD_SGD = 1.35


# --- ticker list -------------------------------------------------------------

def _fetch_prices(url: str) -> list[dict]:
    """Fetch data.prices[] from an SGX securities endpoint."""
    try:
        resp = requests.get(url, headers=_SGX_HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {}).get("prices", [])
    except Exception as exc:
        log.error("SGX fetch failed (%s): %s", url, exc)
        return []


def fetch_sgx_tickers() -> list[dict]:
    """Pull the full SGX ticker list (equities + REITs).

    Returns list of {code, name, board, security_type} dicts.
    Falls back to an empty list on failure (caller handles).

    Field map (verified 2026-06-24):
        item["nc"]          → code
        item["n"]           → name
        item["m"]           → board  ("MAINBOARD" | "CATALIST" | "GLOBAL_QUOTE")
    REIT codes come from the /reits endpoint; all others default to "share".
    """
    stocks = _fetch_prices(SGX_STOCKS_URL)
    reits  = _fetch_prices(SGX_REITS_URL)
    reit_codes = {r.get("nc", "").strip() for r in reits if r.get("nc")}

    out = []
    for item in stocks:
        code = (item.get("nc") or "").strip()
        if not code:
            continue
        out.append({
            "code":          code,
            "name":          (item.get("n") or "").strip(),
            "board":         (item.get("m") or "").strip(),
            "security_type": "unit" if code in reit_codes else "share",
        })
    # Also add any REITs not already in the stocks list.
    existing = {r["code"] for r in out}
    for item in reits:
        code = (item.get("nc") or "").strip()
        if not code or code in existing:
            continue
        out.append({
            "code":          code,
            "name":          (item.get("n") or "").strip(),
            "board":         (item.get("m") or "").strip(),
            "security_type": "unit",
        })
    return out


def classify_security_type(asset_type: str, name: str) -> str:
    """Legacy shim — security_type is now set in fetch_sgx_tickers()."""
    if "reit" in asset_type or "trust" in asset_type or "reit" in name.lower():
        return "unit"
    return "share"


# --- market cap enrichment ---------------------------------------------------

def fetch_market_cap_sgd(code: str) -> Optional[float]:
    """Return market cap in SGD via yfinance .SI, or None."""
    try:
        info = yf.Ticker(f"{code}.SI").info
        mc = info.get("marketCap")
        if mc:
            return float(mc)
    except Exception as exc:
        log.debug("yfinance failed for %s: %s", code, exc)
    return None


# --- main --------------------------------------------------------------------

def build(min_mcap_usd: float, limit: Optional[int]) -> dict:
    log.info("Fetching SGX ticker list...")
    raw = fetch_sgx_tickers()
    if not raw:
        log.error("Empty ticker list; aborting.")
        return {"stocks": [], "stats": {"raw": 0, "kept": 0, "errors": 1}}

    log.info("Got %d raw tickers from SGX.", len(raw))
    if limit:
        raw = raw[:limit]
        log.info("Limited to %d for testing.", limit)

    min_mcap_sgd = min_mcap_usd * USD_SGD
    kept: list[dict] = []
    errors = 0

    for i, t in enumerate(raw, 1):
        if i % 50 == 0:
            log.info("Progress: %d/%d (kept %d so far)", i, len(raw), len(kept))
        mc = fetch_market_cap_sgd(t["code"])
        if mc is None:
            errors += 1
            continue
        if mc < min_mcap_sgd:
            continue
        kept.append({
            **t,
            "market_cap_sgd": mc,
            "market_cap_usd": round(mc / USD_SGD, 0),
        })
        time.sleep(0.2)  # be kind to yfinance

    universe = {
        "market": "sg",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_mcap_usd": min_mcap_usd,
        "stocks": sorted(kept, key=lambda s: -s["market_cap_sgd"]),
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(universe, indent=2, ensure_ascii=False))

    log.info("Wrote %s with %d stocks (errors: %d)", OUT_PATH, len(kept), errors)
    return {"stocks": kept, "stats": {"raw": len(raw), "kept": len(kept), "errors": errors}}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, choices=["sg"])
    parser.add_argument("--min-mcap-usd", type=float, default=100_000_000)
    parser.add_argument("--limit", type=int, help="Cap number of tickers (testing).")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = build(args.min_mcap_usd, args.limit)
    return 0 if result["stats"]["errors"] < result["stats"]["raw"] * 0.5 else 1


if __name__ == "__main__":
    sys.exit(main())
