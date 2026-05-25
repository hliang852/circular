"""SGXNet fetcher — single-pipe architecture for Singapore scrapers.

Per SG_SCHEMA_MAPPING.md Stage 2: build ONE fetcher that hits api.sgx.com
once per nightly window and dispatches announcements to typed handlers by
category. Do NOT replicate HK's split between DI scraper and CA scraper.

Used by:
    scripts/scrape_sg_di.py            (--market sg)
    scripts/scrape_sg_corp_actions.py  (--market sg)
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Optional

import requests

from config.sgx_categories import API_BASE, MATCH_FIELD, MATCH_MODE, ROUTING

log = logging.getLogger(__name__)

# Polite rate limit -- matches HK scrapers per CONTEXT.md.
MIN_DELAY_S = 1.5
MAX_DELAY_S = 3.0

# 429 backoff schedule, in seconds.
BACKOFF_SCHEDULE = [10, 30, 90, 300]

# Default page size for api.sgx.com.
PAGE_SIZE = 50


@dataclass
class Announcement:
    """One row from the api.sgx.com announcements feed."""
    announcement_id: str
    stock_code: str
    issuer_name: str
    headline: str
    category: str
    filing_datetime: datetime
    pdf_url: Optional[str]
    raw: dict = field(repr=False, default_factory=dict)


# A handler takes an Announcement and returns nothing — it writes JSON to disk.
Handler = Callable[[Announcement], None]


class SGXNetFetcher:
    """Pulls announcements from api.sgx.com and dispatches to handlers.

    Usage:
        fetcher = SGXNetFetcher()
        fetcher.register("di", handle_di_filing)
        fetcher.register("corp_actions", handle_ca_filing)
        fetcher.run(start=yesterday, end=today)
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Circular/0.1 (HKEX disclosure tracker; +github.com/.../circular)",
            "Accept": "application/json",
        })
        self.handlers: dict[str, list[Handler]] = {"di": [], "corp_actions": []}
        self.stats = {"fetched": 0, "dispatched": 0, "errors": 0, "skipped": 0}

    # -- registration --------------------------------------------------------

    def register(self, section: str, handler: Handler) -> None:
        if section not in self.handlers:
            raise ValueError(f"Unknown section: {section}")
        self.handlers[section].append(handler)

    # -- main loop -----------------------------------------------------------

    def run(self, start: datetime, end: datetime) -> dict:
        """Fetch all announcements in [start, end] and dispatch them.

        Returns a stats dict suitable for last_run.json.
        """
        log.info("SGXNetFetcher run: %s -> %s", start.isoformat(), end.isoformat())
        for ann in self._iter_announcements(start, end):
            self.stats["fetched"] += 1
            self._dispatch(ann)
            self._polite_sleep()
        log.info("SGXNetFetcher done: %s", self.stats)
        return self.stats

    # -- pagination + HTTP ---------------------------------------------------

    def _iter_announcements(self, start: datetime, end: datetime) -> Iterator[Announcement]:
        page = 0
        while True:
            params = {
                "periodstart": start.strftime("%Y%m%d_000000"),
                "periodend":   end.strftime("%Y%m%d_235959"),
                "pagestart":   page * PAGE_SIZE,
                "pagesize":    PAGE_SIZE,
                # "cat": "GE",  # uncomment once category code confirmed
            }
            try:
                payload = self._get(API_BASE, params)
            except Exception as exc:
                log.error("Page %d failed: %s", page, exc)
                self.stats["errors"] += 1
                break

            items = payload.get("data", []) or payload.get("items", [])
            if not items:
                break

            for item in items:
                try:
                    yield self._parse(item)
                except Exception as exc:
                    log.warning("Parse failed for item %s: %s", item.get("id"), exc)
                    self.stats["errors"] += 1
                    continue

            if len(items) < PAGE_SIZE:
                break
            page += 1

    def _get(self, url: str, params: dict) -> dict:
        for attempt, wait in enumerate([0, *BACKOFF_SCHEDULE]):
            if wait:
                log.warning("Backing off %ds before retry %d", wait, attempt)
                time.sleep(wait)
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Exhausted backoff schedule for {url}")

    def _parse(self, item: dict) -> Announcement:
        """Normalise the raw api.sgx.com record into an Announcement.

        Field names below are the OBSERVED shape from public scrapers; verify
        against a live response and adjust if needed.
        """
        return Announcement(
            announcement_id=str(item.get("id") or item.get("announcement_id") or ""),
            stock_code=(item.get("stock_code") or item.get("symbol") or "").strip(),
            issuer_name=(item.get("issuer_name") or item.get("company_name") or "").strip(),
            headline=(item.get("headline") or item.get("title") or "").strip(),
            category=(item.get("category") or "").strip(),
            filing_datetime=self._parse_dt(item.get("broadcast_date_time") or item.get("date")),
            pdf_url=item.get("url") or item.get("attachment_url"),
            raw=item,
        )

    @staticmethod
    def _parse_dt(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if not value:
            return datetime.now(timezone.utc)
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value)[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    # -- dispatch ------------------------------------------------------------

    def _dispatch(self, ann: Announcement) -> None:
        section = self._classify(ann)
        if section is None:
            self.stats["skipped"] += 1
            return
        for handler in self.handlers.get(section, []):
            try:
                handler(ann)
                self.stats["dispatched"] += 1
            except Exception as exc:
                log.exception("Handler failed for %s: %s", ann.announcement_id, exc)
                self.stats["errors"] += 1

    def _classify(self, ann: Announcement) -> Optional[str]:
        """Return the section name for this announcement, or None to skip."""
        target = (ann.headline if MATCH_FIELD == "headline" else ann.category).lower()
        for _key, (section, code) in ROUTING.items():
            if MATCH_MODE == "exact" and target == code.lower():
                return section
            if MATCH_MODE == "substring" and code.lower() in target:
                return section
        return None

    # -- rate limiting -------------------------------------------------------

    @staticmethod
    def _polite_sleep() -> None:
        time.sleep(random.uniform(MIN_DELAY_S, MAX_DELAY_S))


# Convenience for CLI use ------------------------------------------------------

def default_window(mode: str) -> tuple[datetime, datetime]:
    """Date window for the two scrape modes.

    incremental: yesterday 00:00 -> today 23:59 (UTC). Catches anything filed
                 since the last nightly run.
    full:        52 weeks back -> today.
    """
    now = datetime.now(timezone.utc)
    if mode == "incremental":
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0), now
    if mode == "full":
        return now - timedelta(weeks=52), now
    raise ValueError(f"Unknown mode: {mode}")
