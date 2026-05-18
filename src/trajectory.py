"""Compute season-over-season deltas for trajectory arrows.

Locked decision: players must have ≥ 30 GP in BOTH seasons to be included.
Below that threshold, two data points cannot distinguish trend from regression
to mean.

Output:
    data/processed/trajectory.parquet
        Columns: canonical_player_id, points_per_60_2024, points_per_60_2025,
                 delta, ci_low, ci_high, included_in_map

Phase 1b Day 6 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

MIN_GP_PER_SEASON: int = 30


def compute_trajectories() -> None:
    raise NotImplementedError("Phase 1b Day 6")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Computing season-over-season trajectories (min %d GP per season)", MIN_GP_PER_SEASON)
    compute_trajectories()


if __name__ == "__main__":
    main()
