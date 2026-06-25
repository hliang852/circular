"""Build docs/data/sg/ca_index.json from all docs/data/sg/corp_actions/{code}.json.

Also back-fills mandate.pct_used_of_mandate into each per-stock JSON so the
per-stock CA page can render the mandate headroom bar without extra fetches.

Output schema consumed by docs/sg/ca/index.html:
  [
    {
      "code":                  "D05",
      "name":                  "DBS",
      "security_type":         "share",
      "shares_bought":         1234567,
      "ytd_consideration_sgd": 98765432.0,
      "pct_issued":            0.52,
      "mandate_consumed_pct":  5.2,
      "programme_active":      true,
      "last_filing_date":      "2026-06-01",
      "consistency_score":     0.8
    },
    ...
  ]

Sorted by shares_bought descending (league table order).

Run after every CA scraping run:
    python scripts/build_sg_ca_index.py
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CA_DIR   = Path("docs/data/sg/corp_actions")
OUT_PATH = Path("docs/data/sg/ca_index.json")

# A programme is "active" if there's been at least one buyback in the last N days.
ACTIVE_WINDOW_DAYS = 30
# Weeks of data to include in YTD (calendar year start is ideal but 52w is safe).
YTD_CUTOFF_DAYS = 365


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19]).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _consistency_score(daily_returns: list[dict], lookback_days: int = 90) -> float:
    """Fraction of trading weeks in the lookback window that had at least one buyback.

    Returns a value in [0.0, 1.0].  Returns 0 if no data.
    """
    if not daily_returns:
        return 0.0
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    # Collect ISO week strings for weeks that had a buyback.
    active_weeks: set[str] = set()
    for r in daily_returns:
        dt = _parse_date(r.get("filing_date") or r.get("date"))
        if dt and dt >= cutoff and not r.get("parse_failed"):
            active_weeks.add(dt.strftime("%G-W%V"))
    # Total trading weeks in window (approx 5/7 of calendar weeks).
    total_weeks = max(1, lookback_days // 7)
    return round(min(len(active_weeks) / total_weeks, 1.0), 3)


def build_stock_summary(data: dict, now: datetime) -> dict | None:
    """Return a ca_index row for one stock, or None if no buyback data."""
    daily = data.get("daily_returns", [])
    if not daily:
        return None

    ytd_cutoff = now - timedelta(days=YTD_CUTOFF_DAYS)
    active_cutoff = now - timedelta(days=ACTIVE_WINDOW_DAYS)

    ytd_shares = 0
    ytd_consideration = 0.0
    latest_cum_pct: float | None = None
    last_filing: str = ""

    for r in daily:
        dt = _parse_date(r.get("filing_date") or r.get("date"))
        if not dt or dt < ytd_cutoff:
            continue
        if r.get("parse_failed"):
            continue
        ytd_shares       += r.get("shares_repurchased") or 0
        ytd_consideration += r.get("consideration_sgd") or 0.0
        fd = r.get("filing_date") or r.get("date") or ""
        if fd > last_filing:
            last_filing = fd
        # Use the latest non-null cumulative YTD pct as pct_issued.
        if r.get("cum_ytd_pct") is not None:
            latest_cum_pct = r["cum_ytd_pct"]

    programme_active = any(
        _parse_date(r.get("filing_date") or r.get("date"))
        and _parse_date(r.get("filing_date") or r.get("date")) >= active_cutoff
        and not r.get("parse_failed")
        for r in daily
    )

    # pct_issued: prefer cum_ytd_pct from the most recent daily return;
    # fall back to ytd_shares / (implied total shares) if available.
    pct_issued = latest_cum_pct

    # Mandate headroom.
    mandate        = data.get("mandate") or {}
    mandate_cap    = mandate.get("pct") or 10.0   # SGX default cap is 10%
    mandate_used   = pct_issued if pct_issued is not None else 0.0
    mandate_consumed_pct = round(mandate_used / mandate_cap * 100, 2) if mandate_cap else 0.0

    return {
        "code":                  data["code"],
        "name":                  data.get("name") or data["code"],
        "security_type":         data.get("security_type", "share"),
        "shares_bought":         ytd_shares,
        "ytd_consideration_sgd": round(ytd_consideration, 2),
        "pct_issued":            round(pct_issued, 4) if pct_issued is not None else 0.0,
        "mandate_consumed_pct":  mandate_consumed_pct,
        "programme_active":      programme_active,
        "last_filing_date":      last_filing[:10] if last_filing else "",
        "consistency_score":     _consistency_score(daily),
    }


def main() -> None:
    ca_files = sorted(CA_DIR.glob("*.json"))
    if not ca_files:
        print(f"No CA files in {CA_DIR}. Run scrape_sg_corp_actions.py first.")
        OUT_PATH.write_text("[]", encoding="utf-8")
        return

    print(f"Reading {len(ca_files)} CA files…")
    now = datetime.now(timezone.utc)

    index: list[dict] = []
    skipped = 0

    for path in ca_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  Skipping {path.name}: {exc}")
            skipped += 1
            continue

        row = build_stock_summary(data, now)
        if row is None:
            skipped += 1
            continue

        index.append(row)

        # Back-fill mandate.pct_used_of_mandate into the per-stock JSON.
        mandate = data.get("mandate") or {}
        if mandate.get("pct") and row["pct_issued"] > 0:
            mandate["pct_used_of_mandate"] = row["mandate_consumed_pct"]
            data["mandate"] = mandate
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    index.sort(key=lambda r: r["shares_bought"], reverse=True)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Done. {len(index)} stocks in league table ({skipped} skipped/no buybacks).")
    print(f"  Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
