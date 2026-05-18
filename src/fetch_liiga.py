"""Fetch Liiga player stats via Playwright headless browser.

Liiga's API v2 is locked at the application layer (403 on direct requests, even
with Origin/Referer headers). The website is a SPA, so HTML scraping with
requests returns only the shell. Playwright renders the SPA and lets us read
the rendered DOM.

Writes:
    data/raw/liiga_skaters_{season}.parquet
    data/raw/liiga_goalies_{season}.parquet

Phase 1a Day 2 implementation target.

Tactical notes for the implementer:
    - Use Playwright sync_playwright() context for simplicity.
    - Headless chromium. No need for full browser features.
    - Wait for a stable selector (e.g. table body row count > 0) before reading DOM.
    - Filter Czech-eligible players downstream in crosswalk.py — do NOT filter
      here, because the seed list of Czech-eligible names may not cover all
      relevant Liiga players.
    - Be polite. One season at a time, sleep 3s between page loads.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

LIIGA_BASE_URL = "https://liiga.fi/fi"


def fetch_season(season: int) -> None:
    """Render Liiga player stats SPA for one season and extract to parquet."""
    raise NotImplementedError("Phase 1a Day 2")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]  # shared window
    for season in seasons:
        LOG.info("Liiga: rendering SPA for season %s", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
