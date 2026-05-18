"""Fetch SHL player stats via Playwright headless browser.

SHL website (shl.se) is a SPA with no SSR data. Same approach as fetch_liiga.

Writes:
    data/raw/shl_skaters_{season}.parquet
    data/raw/shl_goalies_{season}.parquet

Phase 1a Day 2 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

SHL_BASE_URL = "https://www.shl.se"


def fetch_season(season: int) -> None:
    """Render SHL player stats SPA for one season and extract to parquet."""
    raise NotImplementedError("Phase 1a Day 2")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        LOG.info("SHL: rendering SPA for season %s", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
