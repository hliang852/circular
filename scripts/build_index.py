#!/usr/bin/env python3
"""
Build data/shareholders_index.json from all data/di/*.json files.

Inverted index: shareholder name → [stock codes sorted by % holding desc]

Run after every scraping run:
    python scripts/build_index.py
"""

import json
import re
from pathlib import Path

DI_DIR = Path("docs/data/di")
OUTPUT_PATH = Path("docs/data/shareholders_index.json")


def normalise_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    return name


def main() -> None:
    di_files = sorted(DI_DIR.glob("*.json"))
    if not di_files:
        print(f"No files found in {DI_DIR}. Run scrape_di.py first.")
        return

    print(f"Reading {len(di_files)} DI files…")

    # name → {code: max_long_pct}
    index: dict[str, dict[str, float]] = {}

    for path in di_files:
        try:
            data = json.loads(path.read_text())
        except Exception as e:
            print(f"  Skipping {path.name}: {e}")
            continue

        code = data.get("code", path.stem)
        for sh in data.get("shareholders", []):
            name = normalise_name(sh.get("name", ""))
            if not name:
                continue
            pct = sh.get("long_position_pct", 0.0)
            if name not in index:
                index[name] = {}
            # Keep highest pct seen for this shareholder × stock pair
            if pct > index[name].get(code, 0.0):
                index[name][code] = pct

    # Build final structure: name → [codes sorted by pct desc]
    result: dict[str, list[str]] = {}
    for name, holdings in sorted(index.items()):
        result[name] = [
            code for code, _ in sorted(holdings.items(), key=lambda x: x[1], reverse=True)
        ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    total_names = len(result)
    total_holdings = sum(len(v) for v in result.values())
    print(f"Done. {total_names} shareholders, {total_holdings} total holdings.")
    print(f"  Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
