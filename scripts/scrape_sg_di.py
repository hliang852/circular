"""Disclosure of Interests scraper (Singapore).

Reads SGXNET announcements via api.sgx.com, parses MAS Form 1/3/4 PDF
attachments, writes per-stock JSON to docs/data/sg/di/{code}.json.

Schema reference: SG_SCHEMA_MAPPING.md § Section 1.

Usage:
    python scripts/scrape_sg_di.py --market sg --mode incremental
    python scripts/scrape_sg_di.py --market sg --mode full
    python scripts/scrape_sg_di.py --market sg --code D05      # single stock test
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

DATA_DIR = Path("docs/data/sg/di")
LOOKBACK_WEEKS = 52


# --- MAS form parsing --------------------------------------------------------

# Form 1 = initial, Form 3 = change, Form 4 = cessation.
FORM_PATTERN = re.compile(r"Form\s+([134])\b", re.IGNORECASE)

# Capacity field on the MAS form -- maps to schema field `role`.
CAPACITY_PATTERNS = {
    "substantial_shareholder": re.compile(r"substantial\s+shareholder", re.I),
    "director":                re.compile(r"\bdirector\b", re.I),
    "ceo":                     re.compile(r"chief\s+executive\s+officer|\bCEO\b", re.I),
}

# Long position figures. MAS forms are standardised so a single regex works.
NUM_SHARES_PATTERN = re.compile(r"Number\s+of\s+(?:voting\s+)?shares[^\d]{0,40}([\d,]+)", re.I)
PCT_PATTERN = re.compile(r"%\s*of\s+issued.{0,40}?([\d.]+)", re.I)


def parse_pdf(pdf_path: Path) -> dict:
    """Extract structured DI fields from a MAS Form 1/3/4 PDF.

    Returns a dict matching the `shareholders[]` entry shape in
    SG_SCHEMA_MAPPING.md. On parse failure, returns a partial dict with
    `parse_failed: True` so the filing metadata is still preserved.
    """
    out: dict = {"parse_failed": False}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages[:3])
    except Exception as exc:
        log.warning("pdfplumber failed on %s: %s", pdf_path, exc)
        return {"parse_failed": True, "reason": str(exc)}

    # Form type -> event_type
    m = FORM_PATTERN.search(text)
    form_num = m.group(1) if m else None
    out["filing_form_type"] = f"Form {form_num}" if form_num else "Unknown"
    out["event_type"] = {"1": "Initial", "3": "Change", "4": "Ceased"}.get(form_num, "Unknown")

    # Capacity -> role
    out["role"] = "unknown"
    for role_key, pat in CAPACITY_PATTERNS.items():
        if pat.search(text):
            out["role"] = role_key
            break

    # Numbers
    m = NUM_SHARES_PATTERN.search(text)
    out["long_position_shares"] = int(m.group(1).replace(",", "")) if m else None
    m = PCT_PATTERN.search(text)
    out["long_position_pct"] = float(m.group(1)) if m else None

    out["deemed_interest"] = "deemed interest" in text.lower()
    # SG does not require granular short positions at SS level.
    out["short_position_shares"] = None
    out["short_position_pct"] = None

    if out["long_position_shares"] is None and out["long_position_pct"] is None:
        out["parse_failed"] = True
        out["reason"] = "no numeric fields extracted"

    return out


# --- per-stock JSON I/O ------------------------------------------------------

def load_stock(code: str) -> dict:
    """Load existing docs/data/sg/di/{code}.json, or return a fresh skeleton."""
    path = DATA_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "code": code,
        "name": None,
        "security_type": "share",  # default; corrected by build_universe
        "currency": "SGD",
        "name_translated": False,
        "last_updated": None,
        "shareholders": [],
        "history": [],
    }


def save_stock(code: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    # Trim history[] to 52 weeks at write time.
    cutoff = datetime.now(timezone.utc).timestamp() - LOOKBACK_WEEKS * 7 * 86400
    data["history"] = [
        h for h in data.get("history", [])
        if datetime.fromisoformat(h["filing_date"]).timestamp() >= cutoff
    ]
    path = DATA_DIR / f"{code}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# --- handler -----------------------------------------------------------------

def handle_di_filing(ann: Announcement) -> None:
    """Handler registered with SGXNetFetcher for DI announcements."""
    if not ann.stock_code:
        log.warning("Skipping announcement %s: no stock code", ann.announcement_id)
        return

    pdf_data: dict = {}
    if ann.pdf_url:
        pdf_path = _download_pdf(ann.pdf_url, ann.announcement_id)
        if pdf_path:
            pdf_data = parse_pdf(pdf_path)

    record = {
        "name": None,  # filled from form free-text in a fuller implementation
        "type": "Corporate",  # default; refine via NRIC/UEN inspection
        "long_position_shares": pdf_data.get("long_position_shares"),
        "long_position_pct": pdf_data.get("long_position_pct"),
        "short_position_shares": None,
        "short_position_pct": None,
        "deemed_interest": pdf_data.get("deemed_interest", False),
        "filing_date": ann.filing_datetime.isoformat(),
        "filing_form_type": pdf_data.get("filing_form_type", "Unknown"),
        "event_type": pdf_data.get("event_type", "Unknown"),
        "threshold_crossed": None,  # computed in build_index
        "role": pdf_data.get("role", "unknown"),
        "notes": ann.headline[:500],
        "filing_url": ann.pdf_url,
        "parse_failed": pdf_data.get("parse_failed", False),
    }

    stock = load_stock(ann.stock_code)
    stock["name"] = stock["name"] or ann.issuer_name
    stock["history"].append(record)

    # Rebuild shareholders[] as the latest-event-per-shareholder view.
    # In a full implementation we'd group by name; for v0 we just append.
    save_stock(ann.stock_code, stock)


def _download_pdf(url: str, ann_id: str) -> Optional[Path]:
    """Download the MAS form PDF for a DI announcement.

    links.sgx.com URLs (the 'url' field in the API) return an HTML viewer
    page, not the PDF directly.  The actual PDF links appear in the HTML as:
        <a href="/1.0.0/corporate-announcements/{ID}/{filename}.pdf"
           class="announcement-attachment">
    We follow one level of indirection to extract and download the first
    matching attachment.  The result is cached by announcement ID.
    """
    cache_dir = Path("docs/data/sg/_pdf_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{ann_id}.pdf"
    if target.exists():
        return target
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type or resp.content[:5] in (b"<html", b"<!DOC", b"\r\n\r\n<", b"\r\n<!"):
            # It's the HTML viewer page — extract attachment links.
            pdf_url = _extract_first_pdf_link(resp.text, url)
            if pdf_url is None:
                log.warning("No PDF attachment found in viewer page (%s)", url)
                return None
            resp = requests.get(pdf_url, timeout=30)
            resp.raise_for_status()

        target.write_bytes(resp.content)
        return target
    except Exception as exc:
        log.warning("PDF download failed (%s): %s", url, exc)
        return None


def _extract_first_pdf_link(html: str, page_url: str) -> Optional[str]:
    """Pull the first announcement-attachment PDF href from the viewer page HTML."""
    import re
    from urllib.parse import urljoin
    # Pattern: <a href="...pdf" ... class="announcement-attachment">
    pat = re.compile(
        r'<a\s+href="(/[^"]+\.pdf)"[^>]*class="announcement-attachment"',
        re.IGNORECASE,
    )
    m = pat.search(html)
    if m:
        # href is relative to links.sgx.com
        return "https://links.sgx.com" + m.group(1)
    # Fallback: any .pdf href under /1.0.0/corporate-announcements/
    pat2 = re.compile(r'href="(/1\.0\.0/corporate-announcements/[^"]+\.pdf)"', re.IGNORECASE)
    m2 = pat2.search(html)
    if m2:
        return "https://links.sgx.com" + m2.group(1)
    return None


# --- CLI ---------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market", required=True, choices=["sg"],
                        help="Only 'sg' supported by this script.")
    parser.add_argument("--mode", choices=["incremental", "full"], default="incremental")
    parser.add_argument("--code", help="Single stock code (for testing).")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    fetcher = SGXNetFetcher()
    fetcher.register("di", handle_di_filing)

    start, end = default_window(args.mode)
    stats = fetcher.run(start, end)

    # Write last_run.json fragment for this section.
    last_run_path = Path("docs/data/sg/last_run.json")
    last_run_path.parent.mkdir(parents=True, exist_ok=True)
    last_run = json.loads(last_run_path.read_text()) if last_run_path.exists() else {}
    last_run["di"] = {
        "last_scrape": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "stats": stats,
    }
    last_run_path.write_text(json.dumps(last_run, indent=2))

    log.info("Done. Stats: %s", stats)
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
