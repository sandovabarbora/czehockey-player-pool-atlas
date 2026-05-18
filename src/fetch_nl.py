"""Fetch Swiss National League (NL) player stats via Playwright.

Swiss NL on sihf.ch is a SPA; the correct stats route still needs to be located
during Phase 1a Day 2. Probable path: https://www.sihf.ch/de/game-center/national-league/...

Writes:
    data/raw/nl_skaters_{season}.parquet
    data/raw/nl_goalies_{season}.parquet

Phase 1a Day 2 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

NL_BASE_URL = "https://www.sihf.ch"


def fetch_season(season: int) -> None:
    """Render Swiss NL player stats SPA for one season."""
    raise NotImplementedError("Phase 1a Day 2")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        LOG.info("Swiss NL: rendering SPA for season %s", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
