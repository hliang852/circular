"""SGXNet fetcher — single-pipe architecture for Singapore scrapers.

Per SG_SCHEMA_MAPPING.md Stage 2: build ONE fetcher that hits api.sgx.com
once per nightly window and dispatches announcements to typed handlers by
category. Do NOT replicate HK's split between DI scraper and CA scraper.

Used by:
    scripts/scrape_sg_di.py            (--market sg)
    scripts/scrape_sg_corp_actions.py  (--market sg)

VERIFIED 2026-05-25:
  - Endpoint: api.sgx.com/announcements/v1.1/company  (v1.1, not v1.0)
  - Auth:     authorizationToken header (short-lived token, ROT-13 encoded
              in CMS; see config.sgx_categories for URL)
  - Field map: see _parse() docstring
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator, Optional

import requests

from config.sgx_categories import (
    API_COMPANY_ENDPOINT,
    CMS_API_URL,
    CMS_VERSION,
    MATCH_FIELD,
    MATCH_MODE,
    ROUTING,
)

log = logging.getLogger(__name__)

# Polite rate limit — matches HK scrapers per CONTEXT.md.
MIN_DELAY_S = 1.5
MAX_DELAY_S = 3.0

# 429 backoff schedule, in seconds.
BACKOFF_SCHEDULE = [10, 30, 90, 300]

# Default page size for api.sgx.com.
PAGE_SIZE = 100

# CMS token endpoint (qrValidator is ROT-13 encoded; decoded value is the header value).
_TOKEN_URL = f"{CMS_API_URL}/?queryId={CMS_VERSION}:we_chat_qr_validator"


def _rot13(s: str) -> str:
    """ROT-13 decoder for the SGX CMS auth token."""
    result = []
    for c in s:
        if c.isalpha():
            base = ord("A") if c <= "Z" else ord("a")
            result.append(chr((ord(c) - base + 13) % 26 + base))
        else:
            result.append(c)
    return "".join(result)


@dataclass
class Announcement:
    """One row from the api.sgx.com announcements feed.

    Field sources (verified against live v1.1 response 2026-05-25):
        announcement_id  ← item["id"]
        stock_code       ← item["issuers"][0]["stock_code"]  (first issuer)
        issuer_name      ← item["issuer_name"]
        headline         ← item["title"]
        category         ← item["sub"]   (subcategory code, e.g. "ANNC13")
        cat              ← item["cat"]   (top-level code, e.g. "ANNC")
        filing_datetime  ← item["broadcast_date_time"]  (Unix milliseconds)
        pdf_url          ← item["url"]
    """
    announcement_id: str
    stock_code: str
    issuer_name: str
    headline: str
    category: str          # sub code  ("ANNC13", "CACT18", …)
    cat: str               # top-level ("ANNC", "CACT", …)
    filing_datetime: datetime
    pdf_url: Optional[str]
    raw: dict = field(repr=False, default_factory=dict)


# A handler takes an Announcement and returns nothing — it writes JSON to disk.
Handler = Callable[[Announcement], None]


class SGXNetFetcher:
    """Pulls announcements from api.sgx.com/v1.1 and dispatches to handlers.

    Usage:
        fetcher = SGXNetFetcher()
        fetcher.register("di", handle_di_filing)
        fetcher.register("corp_actions", handle_ca_filing)
        fetcher.run(start=yesterday, end=today)
    """

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": "https://www.sgx.com/securities/company-announcements",
            "Origin": "https://www.sgx.com",
        })
        self._auth_token: Optional[str] = None
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

        The SGX API caps results at 100 items per request regardless of date
        range.  For windows longer than ~1 week we chunk into CHUNK_DAYS-day
        slices and filter by the sub codes relevant to registered handlers.

        Returns a stats dict suitable for last_run.json.
        """
        self._refresh_token()
        log.info("SGXNetFetcher run: %s -> %s", start.isoformat(), end.isoformat())

        sub_codes = self._active_sub_codes()

        for chunk_start, chunk_end in _week_chunks(start, end):
            for ann in self._iter_announcements(chunk_start, chunk_end, sub_codes):
                self.stats["fetched"] += 1
                self._dispatch(ann)
                self._polite_sleep()

        log.info("SGXNetFetcher done: %s", self.stats)
        return self.stats

    def _active_sub_codes(self) -> list[str]:
        """Return the sub codes for all registered handler sections."""
        codes: list[str] = []
        for _key, (section, sub) in ROUTING.items():
            if self.handlers.get(section):
                codes.append(sub)
        return codes

    # -- auth ----------------------------------------------------------------

    def _refresh_token(self) -> None:
        """Fetch a fresh authorizationToken from the SGX CMS and apply it."""
        try:
            resp = self.session.get(_TOKEN_URL, timeout=30)
            resp.raise_for_status()
            raw_token = resp.json()["data"]["qrValidator"]
            self._auth_token = _rot13(raw_token)
            self.session.headers.update({"authorizationToken": self._auth_token})
            log.debug("SGX auth token refreshed (len=%d)", len(self._auth_token))
        except Exception as exc:
            raise RuntimeError(f"Failed to obtain SGX auth token: {exc}") from exc

    # -- pagination + HTTP ---------------------------------------------------

    def _iter_announcements(
        self, start: datetime, end: datetime, sub_codes: list[str] | None = None
    ) -> Iterator[Announcement]:
        """Yield Announcements from the API for one time chunk.

        sub_codes: if provided, make one request per code (avoids the 100-item
        cap hiding items from minority categories).  If empty/None, fetches
        all categories — safe only for short windows.
        """
        targets = sub_codes if sub_codes else [None]
        seen: set[str] = set()

        for sub in targets:
            params: dict = {
                "periodstart": start.strftime("%Y%m%d_%H%M%S"),
                "periodend":   end.strftime("%Y%m%d_%H%M%S"),
                "pagestart":   0,
                "pagesize":    PAGE_SIZE,
            }
            if sub:
                params["sub"] = sub

            try:
                payload = self._get(API_COMPANY_ENDPOINT, params)
            except Exception as exc:
                log.error("Fetch failed (sub=%s, window %s): %s", sub, start.date(), exc)
                self.stats["errors"] += 1
                continue

            items = payload.get("data") or []
            for item in items:
                ann_id = str(item.get("id") or "")
                if ann_id in seen:
                    continue
                seen.add(ann_id)
                try:
                    yield self._parse(item)
                except Exception as exc:
                    log.warning("Parse failed for item %s: %s", ann_id, exc)
                    self.stats["errors"] += 1

    def _get(self, url: str, params: dict) -> dict:
        for attempt, wait in enumerate([0, *BACKOFF_SCHEDULE]):
            if wait:
                log.warning("Backing off %ds before retry %d", wait, attempt)
                time.sleep(wait)
            resp = self.session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                continue
            if resp.status_code == 401:
                # Token expired mid-run; refresh once and retry.
                log.warning("401 received, refreshing auth token")
                self._refresh_token()
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Exhausted backoff schedule for {url}")

    def _parse(self, item: dict) -> Announcement:
        """Normalise a raw api.sgx.com v1.1 item into an Announcement.

        Verified field names (2026-05-25 against live data):
            item["id"]                       → announcement_id
            item["issuers"][0]["stock_code"] → stock_code  (first issuer)
            item["issuer_name"]              → issuer_name
            item["title"]                    → headline
            item["sub"]                      → category  (subcategory code)
            item["cat"]                      → cat       (top-level code)
            item["broadcast_date_time"]      → filing_datetime (Unix ms int)
            item["url"]                      → pdf_url
        """
        issuers = item.get("issuers") or []
        stock_code = (
            issuers[0].get("stock_code", "") if issuers else ""
        ).strip()

        return Announcement(
            announcement_id=str(item.get("id") or ""),
            stock_code=stock_code,
            issuer_name=(item.get("issuer_name") or "").strip(),
            headline=(item.get("title") or "").strip(),
            category=(item.get("sub") or "").strip(),    # subcategory code
            cat=(item.get("cat") or "").strip(),         # top-level code
            filing_datetime=self._parse_dt(item.get("broadcast_date_time")),
            pdf_url=item.get("url") or None,
            raw=item,
        )

    @staticmethod
    def _parse_dt(value) -> datetime:
        """Parse a broadcast_date_time value.

        The api.sgx.com v1.1 field is a Unix millisecond integer
        (e.g. 1779717976000).  Fallback paths handle legacy string formats.
        """
        if isinstance(value, datetime):
            return value
        if not value:
            return datetime.now(timezone.utc)
        # Unix milliseconds (the normal v1.1 case)
        if isinstance(value, (int, float)) and value > 1_000_000_000_000:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        # Unix seconds
        if isinstance(value, (int, float)) and value > 1_000_000_000:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        # String formats
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d_%H%M%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value)[:19], fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        log.warning("Could not parse datetime value: %r", value)
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
        """Return the section name for this announcement, or None to skip.

        With MATCH_MODE='exact' and MATCH_FIELD='sub', this is a simple
        dict lookup against the verified sub codes in ROUTING.
        """
        target = (ann.category if MATCH_FIELD == "sub" else
                  ann.headline  if MATCH_FIELD == "headline" else
                  ann.cat).lower()
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


# Module-level helpers ---------------------------------------------------------

# The SGX API returns at most 100 items per request regardless of date range.
# Chunking into ~7-day windows keeps each chunk safely under that limit.
_CHUNK_DAYS = 7


def _week_chunks(
    start: datetime, end: datetime
) -> Iterator[tuple[datetime, datetime]]:
    """Yield non-overlapping (chunk_start, chunk_end) pairs spanning [start, end]."""
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=_CHUNK_DAYS), end)
        yield cursor, chunk_end
        cursor = chunk_end


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
