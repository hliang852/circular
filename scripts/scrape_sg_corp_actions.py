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


# --- HTML announcement parsers -----------------------------------------------
# SGX Appendix 8D buyback notices and most other filings are served as HTML
# viewer pages at links.sgx.com, not as machine-readable PDFs.
# Verified 2026-06-25: all numerical fields are present as plain text in the
# HTML body — no PDF download needed for buyback notices.

NUM = r"([\d,]+(?:\.\d+)?)"

# SGX Appendix 8D HTML text structure (verified 2026-06-25 against live UOB filing):
#   Section A: "Total Number of shares purchased 100,000"
#              "Highest Price per share SGD 36.15"  (not "highest price paid")
#              "Lowest Price per share SGD 35.91"
#              "Total Consideration ... SGD 3,602,892.36"
#   Section B: "Purchase made by way of off-market acquisition ... Yes/No"
#   Section C: "Total 7,996,400 0.4786 #Percentage"  (no % symbol on the number)
#              "Number of treasury shares" ...
#
# on_market / off_market are not shown as daily counts in the form — Section B
# only carries a Yes/No flag.  We derive them: if off-market flag = "No",
# all shares are on-market; otherwise we cannot determine the daily split.
_BB_PATTERNS = {
    "shares_repurchased":  re.compile(rf"Total Number of shares purchased\s+{NUM}", re.I),
    "off_market_flag":     re.compile(r"off-market acquisition on equal access scheme\s+(Yes|No)", re.I),
    "price_high":          re.compile(rf"Highest Price per share\s+\w+\s+{NUM}", re.I),
    "price_low":           re.compile(rf"Lowest Price per share\s+\w+\s+{NUM}", re.I),
    # Single-price format used by some companies: "Price Paid per share SGD 0.077"
    "price_paid":          re.compile(rf"Price Paid per share\s+\w+\s+{NUM}", re.I),
    "consideration_sgd":   re.compile(rf"Total Consideration.*?SGD\s+{NUM}", re.I),
    # Section C "Total" row: "Total 7,996,400 0.4786 #Percentage"
    "cum_ytd_pct":         re.compile(rf"Total\s+{NUM}\s+([\d.]+)\s+#Percentage", re.I),
    "max_mandate_shares":  re.compile(rf"Maximum number of shares authorised for purchase\s+{NUM}", re.I),
}

_MANDATE_PCT = re.compile(
    rf"({NUM})\s*%\s*of\s+(?:the\s+)?(?:total\s+)?issued", re.I
)
_ISSUANCE_PATTERNS = {
    "shares":             re.compile(rf"number\s+of\s+new\s+shares[^\d]{{0,40}}{NUM}", re.I),
    "price_per_share":    re.compile(rf"issue\s+price[^\d]{{0,40}}{NUM}", re.I),
    "consideration_sgd":  re.compile(rf"gross\s+proceeds[^\d]{{0,40}}{NUM}", re.I),
}


def _fetch_announcement_text(url: str) -> str:
    """Fetch and clean the text content of an SGX announcement viewer page."""
    try:
        resp = requests.get(url, timeout=30,
                            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                     "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
        resp.raise_for_status()
    except Exception as exc:
        log.warning("Announcement fetch failed (%s): %s", url, exc)
        return ""
    # Strip HTML tags and decode common entities.
    text = re.sub(r"<[^>]+>", " ", resp.text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\s+", " ", text).strip()


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
    fields = _extract(text, _BB_PATTERNS)

    # cum_ytd_pct uses group(2) (the percentage decimal), not group(1) (share count).
    m_cum = _BB_PATTERNS["cum_ytd_pct"].search(text)
    if m_cum:
        try:
            fields["cum_ytd_pct"] = float(m_cum.group(2))
        except (IndexError, ValueError):
            fields["cum_ytd_pct"] = None

    # Single-price format fallback: if high/low both null, use price_paid for both.
    price_paid = fields.pop("price_paid", None)
    if fields["price_high"] is None and fields["price_low"] is None and price_paid is not None:
        fields["price_high"] = price_paid
        fields["price_low"]  = price_paid
    else:
        fields.pop("price_paid", None)

    # Derive on/off market split from Section B Yes/No flag.
    flag = fields.pop("off_market_flag", None)
    n = fields.get("shares_repurchased") or 0
    if isinstance(flag, str) and flag.strip().lower() == "no":
        fields["on_market_shares"]  = n
        fields["off_market_shares"] = 0
    else:
        fields["on_market_shares"]  = None
        fields["off_market_shares"] = None if (flag is None) else n

    fields["parse_failed"] = fields["shares_repurchased"] is None
    return fields


def parse_mandate(text: str) -> dict:
    m = _MANDATE_PCT.search(text)
    return {
        "pct": float(m.group(1)) if m else None,
        "parse_failed": m is None,
    }


def parse_issuance(text: str) -> dict:
    fields = _extract(text, _ISSUANCE_PATTERNS)
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

    text = _fetch_announcement_text(ann.pdf_url) if ann.pdf_url else ""

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
    """Download PDF for a CA announcement, following the SGX HTML viewer redirect.

    links.sgx.com URLs return an HTML viewer page, not the PDF directly.
    We follow one level of indirection (same pattern as scrape_sg_di._download_pdf).
    """
    if not url:
        return None
    cache_dir = Path("docs/data/sg/_pdf_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{ann_id}.pdf"
    if target.exists() and target.stat().st_size > 5000:
        return target
    try:
        resp = requests.get(url, timeout=30,
                            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                     "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"})
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type or resp.content[:5] in (b"<html", b"<!DOC", b"\r\n\r\n<", b"\r\n<!"):
            pdf_url = _extract_pdf_link(resp.text)
            if pdf_url is None:
                log.debug("No PDF attachment in viewer page (%s)", url)
                return None
            resp = requests.get(pdf_url, timeout=30,
                                headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()

        if resp.content[:4] != b"%PDF":
            log.debug("Response is not a PDF for %s", ann_id)
            return None

        target.write_bytes(resp.content)
        return target
    except Exception as exc:
        log.warning("PDF download failed (%s): %s", url, exc)
        return None


def _extract_pdf_link(html: str) -> Optional[str]:
    """Extract the first .pdf attachment href from an SGX viewer page."""
    import re
    for pat in [
        re.compile(r'<a\s+href="(/[^"]+\.pdf)"[^>]*class="announcement-attachment"', re.I),
        re.compile(r'href="(/1\.0\.0/corporate-announcements/[^"]+\.pdf)"', re.I),
    ]:
        m = pat.search(html)
        if m:
            return "https://links.sgx.com" + m.group(1)
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
