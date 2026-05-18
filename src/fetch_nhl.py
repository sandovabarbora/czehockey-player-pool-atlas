"""Fetch NHL player stats from the official NHL Stats API.

API: https://api-web.nhle.com/v1/  (no auth, polite rate limit ~1 req/sec)

Writes:
    data/raw/nhl_players_{season}.parquet  (one per season in window)

Coverage: all skaters and goalies who appeared in NHL in the season.
Filtering to Czech-eligible happens in crosswalk.py.

Phase 1a Day 1 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)


def fetch_season(season: int) -> None:
    """Fetch a single NHL season's player stats and write to raw/.

    Args:
        season: starting year (e.g. 2024 for the 2024-25 season).
    """
    raise NotImplementedError("Phase 1a Day 1")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        LOG.info("NHL: fetching season %s", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
