"""Download MoneyPuck season-summary CSVs (NHL xG and GAR-style metrics).

URLs follow the pattern:
    https://moneypuck.com/moneypuck/playerData/seasonSummary/{YEAR}/regular/{skaters|goalies|lines|teams}.csv

MoneyPuck uses single-year notation: "2024" = 2024-25 season.

Writes:
    data/raw/moneypuck_skaters_{season}.parquet
    data/raw/moneypuck_goalies_{season}.parquet

Phase 1a Day 1 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

MP_BASE_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary"


def fetch_season(season: int) -> None:
    """Download skater + goalie season summary CSVs for one season."""
    raise NotImplementedError("Phase 1a Day 1")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        LOG.info("MoneyPuck: fetching season %s", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
