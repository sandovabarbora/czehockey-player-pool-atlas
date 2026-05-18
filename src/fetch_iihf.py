"""Fetch IIHF tournament participation history for Czech-eligible players.

Scope (per critique decision): MS 2024, MS 2025, WJC 2024, WJC 2025 only.
Wider history is not needed for the report and triples scraping volume.

Source: https://www.iihf.com/en/static/5184/statistics

Writes:
    data/raw/iihf_participation.parquet
        Columns: canonical_player_id, tournament, year, gp, goals, assists, points, toi

Phase 1a Day 4 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

IIHF_BASE = "https://www.iihf.com"

# Locked tournament scope (per Phase 1 critique decision #8)
TOURNAMENTS: tuple[tuple[str, int], ...] = (
    ("ms", 2024),
    ("ms", 2025),
    ("wjc", 2024),
    ("wjc", 2025),
)


def fetch_tournament(tournament: str, year: int) -> None:
    """Scrape one IIHF tournament's per-player stats."""
    raise NotImplementedError("Phase 1a Day 4")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    for tournament, year in TOURNAMENTS:
        LOG.info("IIHF: fetching %s %s", tournament.upper(), year)
        fetch_tournament(tournament, year)


if __name__ == "__main__":
    main()
