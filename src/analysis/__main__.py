"""Run every analysis module in order: python -m src.analysis [--skip-model]

`--skip-model` leaves outputs/q2_break_model.json as it is (the PyMC fits take a few
minutes); everything else is rebuilt from the snapshot in well under a minute.
"""

from __future__ import annotations

import logging
import sys

from src.analysis import (
    intervals,
    linking,
    pool,
    q1_per_million,
    q2_break_model,
    q3_cohort_gaps,
    q4_youth_ice_time,
    q5_abroad,
    q6_national_team,
    q7_goalkeepers,
)
from src.logging_setup import setup

LOG = logging.getLogger(__name__)


def main(argv: list[str]) -> int:
    setup()
    steps = [
        linking,
        q1_per_million,
        q3_cohort_gaps,
        q4_youth_ice_time,
        q5_abroad,
        q6_national_team,
        q7_goalkeepers,
        pool,
        intervals,
    ]
    if "--skip-model" not in argv:
        steps.insert(2, q2_break_model)
    for mod in steps:
        LOG.info("running %s", mod.__name__)
        mod.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
