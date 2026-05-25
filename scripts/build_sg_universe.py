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

# SGX securities reference endpoint -- public, no auth.
SGX_SECURITIES_URL = "https://api.sgx.com/securities/v1.1/securities-data?type=stocks"

# USD/SGD assumption -- refresh from a fx source in a fuller implementation.
USD_SGD = 1.35


# --- ticker list -------------------------------------------------------------

def fetch_sgx_tickers() -> list[dict]:
    """Pull the full SGX ticker list.

    Returns list of {code, name, isin, board, asset_type} dicts.
    Falls back to an empty list on failure (caller handles).
    """
    try:
        resp = requests.get(SGX_SECURITIES_URL, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        log.error("SGX securities fetch failed: %s", exc)
        return []

    # Response shape varies; common pattern is {"data": [...]}.
    items = payload.get("data") or payload.get("securities") or []
    out = []
    for item in items:
        out.append({
            "code":       (item.get("nc") or item.get("code") or item.get("symbol", "")).strip(),
            "name":       (item.get("n") or item.get("name", "")).strip(),
            "isin":       item.get("isin"),
            "board":      item.get("listingBoard") or item.get("board"),
            "asset_type": (item.get("assetType") or item.get("type", "")).lower(),
        })
    return [r for r in out if r["code"]]


def classify_security_type(asset_type: str, name: str) -> str:
    """Map SGX asset_type into our two-value security_type field."""
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
            "security_type": classify_security_type(t["asset_type"], t["name"]),
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
