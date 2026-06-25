"""Build docs/data/sg/di_index.json from all docs/data/sg/di/{code}.json files.

Inverted index: shareholder name → list of latest-position objects across stocks.

Schema consumed by docs/sg/di/index.html:
  {
    "Shareholder Name": [
      {
        "code":                "D05",
        "stock_name":          "DBS",
        "filing_date":         "2026-06-01T...",
        "event_type":          "Change",
        "role":                "substantial_shareholder",
        "long_position_pct":   5.2,
        "long_position_shares": 12345678,
        "filing_form_type":    "Form 3",
        "filing_url":          "https://..."
      },
      ...
    ],
    ...
  }

Each shareholder entry shows their LATEST filing per stock (not the full history).
The frontend "Latest Filings" tab flattens all entries and sorts by filing_date.

Run after every DI scraping run:
    python scripts/build_sg_di_index.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

DI_DIR   = Path("docs/data/sg/di")
OUT_PATH = Path("docs/data/sg/di_index.json")

# Inline copy of scrape_sg_di.extract_name_from_headline so the index builder
# can backfill existing records that have name=None but a populated notes field.
_HEADLINE_NAME = re.compile(
    r"\s+-\s+((?:[A-Z][a-zA-Z'.-]*\s*){1,7}(?:[A-Z][a-zA-Z'-]+))$"
)
_SKIP_NAMES = re.compile(
    r"^(Director|CEO|Substantial Shareholder|Unitholder|Interest|Change|Cessation|Disclosure)$",
    re.I,
)


def _extract_name(headline: str) -> str | None:
    specific = headline.split("::", 1)[-1].strip()
    m = _HEADLINE_NAME.search(specific)
    if not m:
        return None
    name = m.group(1).strip()
    if _SKIP_NAMES.match(name) or len(name) < 4:
        return None
    return name


def _normalise_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def main() -> None:
    di_files = sorted(DI_DIR.glob("*.json"))
    if not di_files:
        print(f"No DI files in {DI_DIR}. Run scrape_sg_di.py first.")
        OUT_PATH.write_text("{}", encoding="utf-8")
        return

    print(f"Reading {len(di_files)} DI files…")

    # shareholder_name → {stock_code: latest_filing_record}
    # We keep the most recent filing per (shareholder, stock) pair.
    index: dict[str, dict[str, dict]] = {}

    for path in di_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  Skipping {path.name}: {exc}")
            continue

        code       = data.get("code", path.stem)
        stock_name = data.get("name") or code

        for entry in data.get("history", []):
            raw_name = entry.get("name") or _extract_name(entry.get("notes") or "")
            sh_name = _normalise_name(raw_name or "")
            if not sh_name:
                continue
            if sh_name not in index:
                index[sh_name] = {}
            existing = index[sh_name].get(code)
            # Keep the most recent filing per (shareholder, stock).
            if existing is None or (
                entry.get("filing_date", "") > existing.get("filing_date", "")
            ):
                index[sh_name][code] = {
                    "code":                 code,
                    "stock_name":           stock_name,
                    "filing_date":          entry.get("filing_date"),
                    "event_type":           entry.get("event_type"),
                    "role":                 entry.get("role"),
                    "long_position_pct":    entry.get("long_position_pct"),
                    "long_position_shares": entry.get("long_position_shares"),
                    "filing_form_type":     entry.get("filing_form_type"),
                    "filing_url":           entry.get("filing_url"),
                    "parse_failed":         entry.get("parse_failed", False),
                }

    # Flatten: each shareholder maps to a list of per-stock records,
    # sorted by filing_date descending.
    result: dict[str, list[dict]] = {}
    for sh_name, holdings in sorted(index.items()):
        filings = sorted(
            holdings.values(),
            key=lambda r: r.get("filing_date") or "",
            reverse=True,
        )
        result[sh_name] = filings

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    total_sh      = len(result)
    total_entries = sum(len(v) for v in result.values())
    print(f"Done. {total_sh} shareholders, {total_entries} stock-positions.")
    print(f"  Output: {OUT_PATH}")


if __name__ == "__main__":
    main()
