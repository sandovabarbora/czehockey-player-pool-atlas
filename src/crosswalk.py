"""Deduplicate players across source leagues into one canonical record.

EliteProspects was originally planned as the meta-crosswalk source, but EP
returns 403 on league listing pages and free-tier scraping is unreliable at
corpus volume. Instead, we use a seed CSV of Czech-eligible players
(data/seed/czech_eligible_players.csv) combined with fuzzy matching on
(name + birthdate + position) across the per-league raw parquets.

Inputs (one or more per league):
    data/raw/nhl_players_{season}.parquet
    data/raw/moneypuck_skaters_{season}.parquet
    data/raw/liiga_skaters_{season}.parquet
    data/raw/shl_skaters_{season}.parquet
    data/raw/nl_skaters_{season}.parquet
    data/raw/extraliga_skaters_{season}.parquet
    data/raw/cz1l_skaters_{season}.parquet
    data/raw/iihf_participation.parquet
    data/seed/czech_eligible_players.csv

Writes:
    data/processed/players.parquet
        One row per canonical player, columns include source league records
        joined on canonical_player_id.

Phase 1a Day 4 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

# Fuzzy match acceptance threshold; tune in Phase 1a Day 4.
NAME_MATCH_THRESHOLD: int = 92


def build_canonical_table() -> None:
    """Combine seed list + per-league raw parquets into one canonical table."""
    raise NotImplementedError("Phase 1a Day 4")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Building canonical player table")
    build_canonical_table()


if __name__ == "__main__":
    main()
