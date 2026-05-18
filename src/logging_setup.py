"""Logging configuration. Import and call setup() at the top of any module
that runs as a script."""

from __future__ import annotations

import logging
import sys


def setup(level: int = logging.INFO) -> None:
    """Configure root logger for pipeline scripts.

    INFO for pipeline progress, DEBUG for per-player / per-team detail.
    No third-party noise (urllib3, playwright) above WARNING.
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    for noisy in ("urllib3", "playwright", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
