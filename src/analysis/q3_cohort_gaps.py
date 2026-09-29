"""Question 3: where is it thin? Cohort gaps by position and age band in rung 1 + 2, 2025/26,
Czechia against the peer median.

Each qualifying rung 1 + 2 player of 2025/26 is counted once (as in `q1_per_million`) in a
position (F, D, G) and an age band (`common.AGE_BANDS`; age = 2025 - birth year). Each
cell is turned into players per million inhabitants; the peer median is the median over
the nine peers. `shortfall` is how many players Czechia would need to add to reach the
peer median in that cell (negative: above the median).

Positions and birth years come from the player's own row or, where the source lacks them
(SHL positions, DEL and NL birth dates), from the linked person. Players with neither are
counted under 'unknown' and reported.

    python -m src.analysis.q3_cohort_gaps   -> outputs/q3_cohort_gaps.json
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common, linking, q1_per_million
from src.nations import HOME, ISO3

LOG = logging.getLogger(__name__)

SEASON = 2025
MAX_UNKNOWN_SHARE = 0.25
"""A peer enters the median of a cell split by age (or position) only when at most this
share of its players has that attribute unknown. In 2025/26 this leaves out Switzerland and
Germany from the age medians: the NL and the DEL publish no birth dates."""


def cohort_table(stints: pd.DataFrame, season: int = SEASON) -> pd.DataFrame:
    rows = stints[
        stints["league"].isin(common.TOP5)
        & stints["qualifies"]
        & (stints["season_start"] == season)
    ]
    per = q1_per_million.best_rung_per_person(rows)
    per = per[per["nationality"].isin(ISO3)].copy()
    per["position"] = per["position"].fillna("unknown")
    per["age"] = [common.season_age(season, b) for b in per["birth_year"]]
    per["age_band"] = per["age"].map(common.age_band)
    return per


def eligible_peers(per: pd.DataFrame, dims: tuple[str, ...]) -> list[str]:
    """Peers whose share of unknown values in every split dimension is small enough."""
    out = []
    for c in ISO3:
        if c == HOME:
            continue
        mine = per[per["nationality"] == c]
        if mine.empty:
            out.append(c)
            continue
        if all((mine[d] == "unknown").mean() <= MAX_UNKNOWN_SHARE for d in dims):
            out.append(c)
    return out


def gaps(
    per: pd.DataFrame,
    pop: pd.DataFrame,
    season: int = SEASON,
    dims: tuple[str, ...] = ("position", "age_band"),
) -> list[dict[str, Any]]:
    peer_codes = eligible_peers(per, dims)
    tab = per.groupby([*dims, "nationality"]).size().unstack(fill_value=0)
    tab = tab.reindex(columns=list(ISO3), fill_value=0)
    popn = {c: common.population_for_season(pop, c, season) for c in ISO3}
    out = []
    for cell, row in tab.iterrows():
        cell = cell if isinstance(cell, tuple) else (cell,)
        pm = {c: common.per_million(row[c], popn[c]) for c in ISO3}
        peers = [pm[c] for c in peer_codes]
        med = float(np.median(peers))
        out.append(
            {
                **dict(zip(dims, cell, strict=True)),
                "counts": {c: int(row[c]) for c in ISO3},
                "per_million": pm,
                "peer_median": med,
                "home_minus_median": pm[HOME] - med,
                "home_to_median": pm[HOME] / med if med else None,
                "home_rank": 1 + sum(v > pm[HOME] for v in peers),
                "peers_in_median": peer_codes,
                "shortfall": (med - pm[HOME]) * popn[HOME] / 1e6,
            }
        )
    return out


def run(lk: linking.Linked, pop: pd.DataFrame) -> dict[str, Any]:
    per = cohort_table(lk.stints)
    unknown = {
        c: {
            "players": int((per["nationality"] == c).sum()),
            "position_unknown": int(
                ((per["nationality"] == c) & (per["position"] == "unknown")).sum()
            ),
            "age_unknown": int(((per["nationality"] == c) & (per["age_band"] == "unknown")).sum()),
        }
        for c in ISO3
    }
    cells = gaps(per, pop)
    known = [c for c in cells if c["position"] != "unknown" and c["age_band"] != "unknown"]
    largest = sorted(known, key=lambda c: -c["shortfall"])[:5]
    return {
        "definitions": {
            "season": common.season_label(SEASON),
            "players": "qualifying rung 1 + 2 players (q1_per_million), once per person",
            "age": "season start year minus birth year",
            "age_bands": [b[0] for b in common.AGE_BANDS],
            "peer_median": "median of players per million over the peers in `peers_in_median`: "
            f"peers with more than {MAX_UNKNOWN_SHARE:.0%} of players unknown in a split "
            "dimension are left out of that split",
            "shortfall": "(peer median - Czechia) per million x Czech population: players needed to reach the median",
        },
        "unknown": unknown,
        "cells": cells,
        "by_position": gaps(per, pop, dims=("position",)),
        "by_age_band": gaps(per, pop, dims=("age_band",)),
        "largest_shortfalls": [
            {k: c[k] for k in ("position", "age_band", "shortfall", "home_to_median")}
            for c in largest
        ],
    }


def main() -> None:
    out = run(linking.linked(), common.population_table())
    path = common.write_output(
        "q3_cohort_gaps.json", out, [*linking.SNAPSHOT_FILES, "population.parquet"]
    )
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
