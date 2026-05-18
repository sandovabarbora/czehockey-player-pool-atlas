"""Fetch Czech Extraliga + 1. liga player stats from hokej.cz.

hokej.cz is SSR'd, so requests + BeautifulSoup works (no Playwright needed).
Player URLs follow the pattern /hrac/{slug}/{id}.

The correct stats listing URL still needs to be discovered in Phase 1a Day 3
(some likely candidates returned 404 on initial probing).

Writes:
    data/raw/extraliga_skaters_{season}.parquet
    data/raw/extraliga_goalies_{season}.parquet
    data/raw/cz1l_skaters_{season}.parquet  (only top prospects)

Phase 1a Day 3 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

HOKEJCZ_BASE = "https://www.hokej.cz"


def fetch_season(league: str, season: int) -> None:
    """Scrape one league-season from hokej.cz.

    Args:
        league: "extraliga" or "cz1l"
        season: starting year (2024 = 2024/25 season)
    """
    raise NotImplementedError("Phase 1a Day 3")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        for league in ("extraliga", "cz1l"):
            LOG.info("hokej.cz: fetching %s season %s", league, season)
            fetch_season(league, season)


if __name__ == "__main__":
    main()
