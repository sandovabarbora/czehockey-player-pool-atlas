"""Build per-60 feature vectors for forwards.

Input:
    data/processed/players.parquet  (canonical, all positions)

Output:
    data/processed/features_forwards.parquet
        Two feature sets:
          - *_style:   z-scored within position, NO multipliers
          - *_quality: z-scored within position, multipliers applied to scaled metrics

Locked decisions (from critique pass):
    - Two projections built side-by-side: style + quality.
    - Multiplier applied to raw rates BEFORE z-scoring. Order is explicit.
    - xG dropped from cross-league feature vector (NaN for non-NHL/AHL).

Phase 1b Day 5 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)


def build_features() -> None:
    """Build forward feature vectors and write to data/processed/."""
    raise NotImplementedError("Phase 1b Day 5")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Building forward feature vectors (style + quality)")
    build_features()


if __name__ == "__main__":
    main()
