"""Build feature vectors for goaltenders.

Goalies are NOT included in the main Atlas map (position is too distinct).
They appear in a separate small section of the report.

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
    LOG.info("Building goalie feature vectors")
    build_features()


if __name__ == "__main__":
    main()
