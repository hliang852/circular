# To-Do

## When happy with the prototype

- [v] **Trigger full universe build** — run `python scripts/build_universe.py` (or trigger `update_universe.yml` via GitHub Actions workflow_dispatch). This expands from 10 seed stocks to ~600–900 stocks above $100M USD market cap.

- [ ] **Incorporate Action Plan for Buyback** - Ask Claude to generate action plan for the prototype and implement it here. This can be done before the full DI scrape (step 2)

- [ ] **Trigger full DI scrape** — run `python scripts/scrape_di.py --mode full` (or trigger `scrape_nightly.yml` via workflow_dispatch with mode = `full`). Takes ~30–45 min. Populates `docs/data/di/` for all stocks.

- [ ] **Rebuild shareholder index** — run `python scripts/build_index.py` after the full scrape completes.

- [ ] **Enable GitHub Pages** — Repo Settings → Pages → Source: branch `main`, folder `/docs`.

- [ ] **Set Actions write permissions** — Repo Settings → Actions → General → Workflow permissions → Read and write permissions. Required for nightly data commits.

