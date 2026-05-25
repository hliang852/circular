"""Corporate Actions scraper (Singapore).

Handles five filing types from the SGXNET stream:
  - Daily Share Buy-Back Notice (Appendix 8D)     -> daily_returns[]
  - Buyback Mandate / AGM circular                -> mandate{}
  - Placement / Rights / Bonus / Scrip / CB       -> issuances[]
  - Financial Statements                          -> results_dates[]
  - Director dealings are NOT handled here -- they come through scrape_sg_di.py
    via the same DOI announcement stream (per SG_SCHEMA_MAPPING.md).

Schema reference: SG_SCHEMA_MAPPING.md § Section 2.

Usage:
    python scripts/scrape_sg_corp_actions.py --market sg --mode incremental
    python scripts/scrape_sg_corp_actions.py --market sg --mode full
    python scripts/scrape_sg_corp_actions.py --market sg --code D05
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pdfplumber
import requests

from scripts.sgxnet_fetcher import Announcement, SGXNetFetcher, default_window

log = logging.getLogger(__name__)

DATA_DIR = Path("docs/data/sg/corp_actions")
LOOKBACK_WEEKS = 52


# --- classifier (headline -> filing type) ------------------------------------

CA_PATTERNS = {
    "buyback":       re.compile(r"share\s+buy.?back", re.I),
    "mandate":       re.compile(r"buyback\s+mandate|repurchase\s+mandate", re.I),
    "placement":     re.compile(r"\bplacement\b|placing", re.I),
    "rights_issue":  re.compile(r"rights\s+issue", re.I),
    "bonus_issue":   re.compile(r"bonus\s+issue", re.I),
    "scrip":         re.compile(r"scrip\s+dividend", re.I),
    "convertible":   re.compile(r"convertible|exchangeable", re.I),
    "results":       re.compile(r"financial\s+statements|results", re.I),
}


def classify_ca(headline: str) -> Optional[str]:
    for kind, pat in CA_PATTERNS.items():
        if pat.search(headline):
            return kind
    return None


# --- PDF parsers (one per filing type) ---------------------------------------

NUM = r"([\d,]+(?:\.\d+)?)"

# Appendix 8D extraction. Form is standardised by SGX rule.
BUYBACK_PATTERNS = {
    "shares_repurchased": re.compile(rf"number\s+of\s+shares\s+purchased[^\d]{{0,40}}{NUM}", re.I),
    "on_market_shares":   re.compile(rf"on.?market[^\d]{{0,40}}{NUM}", re.I),
    "off_market_shares":  re.compile(rf"off.?market[^\d]{{0,40}}{NUM}", re.I),
    "price_high":         re.compile(rf"highest\s+price[^\d]{{0,40}}{NUM}", re.I),
    "price_low":          re.compile(rf"lowest\s+price[^\d]{{0,40}}{NUM}", re.I),
    "consideration_sgd":  re.compile(rf"total\s+consideration[^\d]{{0,40}}{NUM}", re.I),
    "cum_ytd_pct":        re.compile(rf"cumulative.{{0,80}}?{NUM}\s*%", re.I),
}

MANDATE_PCT_PATTERN = re.compile(rf"({NUM})\s*%\s*of\s+(?:the\s+)?(?:total\s+)?issued", re.I)
ISSUANCE_PATTERNS = {
    "shares":             re.compile(rf"number\s+of\s+new\s+shares[^\d]{{0,40}}{NUM}", re.I),
    "price_per_share":    re.compile(rf"issue\s+price[^\d]{{0,40}}{NUM}", re.I),
    "consideration_sgd":  re.compile(rf"gross\s+proceeds[^\d]{{0,40}}{NUM}", re.I),
}


def _read_pdf_text(pdf_path: Path, max_pages: int = 5) -> str:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
    except Exception as exc:
        log.warning("pdfplumber failed on %s: %s", pdf_path, exc)
        return ""


def _extract(text: str, patterns: dict[str, re.Pattern]) -> dict:
    out: dict = {}
    for key, pat in patterns.items():
        m = pat.search(text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                out[key] = float(raw) if "." in raw else int(raw)
            except ValueError:
                out[key] = raw
        else:
            out[key] = None
    return out


def parse_buyback(text: str) -> dict:
    fields = _extract(text, BUYBACK_PATTERNS)
    fields["parse_failed"] = fields["shares_repurchased"] is None
    return fields


def parse_mandate(text: str) -> dict:
    m = MANDATE_PCT_PATTERN.search(text)
    return {
        "pct": float(m.group(1)) if m else None,
        "parse_failed": m is None,
    }


def parse_issuance(text: str) -> dict:
    fields = _extract(text, ISSUANCE_PATTERNS)
    fields["parse_failed"] = fields["shares"] is None
    return fields


# --- per-stock JSON I/O ------------------------------------------------------

def load_stock(code: str) -> dict:
    path = DATA_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "code": code,
        "name": None,
        "security_type": "share",
        "currency": "SGD",
        "last_updated": None,
        "free_float_pct": None,
        "consistency_score": None,
        "signal": None,
        "mandate": {},
        "summary": {},
        "daily_returns": [],     # key SG difference: daily not monthly
        "issuances": [],
        "results_dates": [],
    }


def save_stock(code: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    cutoff = datetime.now(timezone.utc).timestamp() - LOOKBACK_WEEKS * 7 * 86400
    for arr_key in ("daily_returns", "issuances", "results_dates"):
        data[arr_key] = [
            r for r in data.get(arr_key, [])
            if datetime.fromisoformat(r["date"]).timestamp() >= cutoff
        ]
    path = DATA_DIR / f"{code}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --- handler -----------------------------------------------------------------

def handle_ca_filing(ann: Announcement) -> None:
    if not ann.stock_code:
        return
    kind = classify_ca(ann.headline)
    if kind is None:
        log.debug("Unclassified CA headline: %s", ann.headline)
        return

    pdf_path = _download_pdf(ann.pdf_url, ann.announcement_id) if ann.pdf_url else None
    text = _read_pdf_text(pdf_path) if pdf_path else ""

    stock = load_stock(ann.stock_code)
    stock["name"] = stock["name"] or ann.issuer_name
    iso_date = ann.filing_datetime.isoformat()

    if kind == "buyback":
        parsed = parse_buyback(text)
        stock["daily_returns"].append({
            "date": iso_date,
            "filing_date": iso_date,
            "filing_url": ann.pdf_url,
            **parsed,
        })
    elif kind == "mandate":
        parsed = parse_mandate(text)
        stock["mandate"] = {
            **stock.get("mandate", {}),
            "pct": parsed.get("pct"),
            "agm_date": iso_date,
            "circular_url": ann.pdf_url,
            "expiry_note": "Earlier of next AGM or 12 months from approval",
        }
    elif kind in ("placement", "rights_issue", "bonus_issue", "scrip", "convertible"):
        parsed = parse_issuance(text)
        stock["issuances"].append({
            "date": iso_date,
            "type": kind,
            "label": ann.headline[:200],
            "shares": parsed.get("shares"),
            "consideration_sgd": parsed.get("consideration_sgd"),
            "price_per_share": parsed.get("price_per_share"),
            "filing_url": ann.pdf_url,
        })
    elif kind == "results":
        results_type = "interim" if "interim" in ann.headline.lower() else (
            "annual" if "full year" in ann.headline.lower() or "annual" in ann.headline.lower()
            else "other"
        )
        stock["results_dates"].append({
            "date": iso_date,
            "type": results_type,
            "filing_url": ann.pdf_url,
        })

    save_stock(ann.stock_code, stock)


def _download_pdf(url: Optional[str], ann_id: str) -> Optional[Path]:
    if not url:
        return None
    cache_dir = Path("docs/data/sg/_pdf_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{ann_id}.pdf"
    if target.exists():
        return target
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        return target
    except Exception as exc:
        log.warning("PDF download failed (%s): %s", url, exc)
        return None


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

    fetcher = SGXNetFetcher()
    fetcher.register("corp_actions", handle_ca_filing)

    start, end = default_window(args.mode)
    stats = fetcher.run(start, end)

    last_run_path = Path("docs/data/sg/last_run.json")
    last_run_path.parent.mkdir(parents=True, exist_ok=True)
    last_run = json.loads(last_run_path.read_text()) if last_run_path.exists() else {}
    last_run["corp_actions"] = {
        "last_scrape": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "stats": stats,
    }
    last_run_path.write_text(json.dumps(last_run, indent=2))

    log.info("Done. Stats: %s", stats)
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
