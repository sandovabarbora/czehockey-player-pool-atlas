"""Build per-60 feature vectors for defensemen.

Mirrors features_forwards.py but with the defenseman feature set.
See config/feature_definitions.yaml for column definitions.

Phase 1b Day 5 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)


def build_features() -> None:
    raise NotImplementedError("Phase 1b Day 5")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Building defenseman feature vectors (style + quality)")
    build_features()


if __name__ == "__main__":
    main()
