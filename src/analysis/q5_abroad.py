"""Question 5: how do Czech players fare abroad? Time on ice per game and points per game of
Czech skaters in the NHL, Liiga and SHL, against the league median at the same position.

For every league-season and position (F, D) the medians are taken over the qualifying
skaters (the pro-rated games threshold) of every nationality. Each qualifying Czech skater
gets two ratios, his value over the median (1.0 = the median player at his position).
The same summary is given for every compared nation, for context, and the NHL has a
season series from 1997/98 (the first season with skater time on ice) for Czechia, Finland
and Sweden.

Window for the player list and the league summaries: 2020/21-2025/26, the pool window.
Skaters whose position is unknown after linking (SHL) are left out and counted.

    python -m src.analysis.q5_abroad   -> outputs/q5_abroad.json
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common, linking
from src.nations import HOME, ISO3

LOG = logging.getLogger(__name__)

LEAGUES = ("NHL", "Liiga", "SHL")
FIRST = 2020
LAST = common.LAST_SEASON
NHL_SERIES_FIRST = 1997
SERIES_NATIONS = ("CZE", "FIN", "SWE")


def with_ratios(stints: pd.DataFrame, leagues: tuple[str, ...] = LEAGUES) -> pd.DataFrame:
    s = stints[
        stints["league"].isin(leagues) & stints["qualifies"] & stints["position"].isin(["F", "D"])
    ].copy()
    gp = s["games_played"].astype("float64")
    s["toi_pg"] = s["toi_s"] / gp
    s["ppg"] = s["points"] / gp
    grp = s.groupby(["league", "season_start", "position"])
    s["median_toi_pg"] = grp["toi_pg"].transform("median")
    s["median_ppg"] = grp["ppg"].transform("median")
    s["toi_ratio"] = s["toi_pg"] / s["median_toi_pg"]
    s["ppg_ratio"] = s["ppg"] / s["median_ppg"]
    return s


def summarise(g: pd.DataFrame) -> dict[str, Any]:
    toi = g["toi_ratio"].dropna()
    ppg = g["ppg_ratio"].replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "player_seasons": len(g),
        "players": int(g["person_id"].nunique()),
        "median_toi_ratio": float(toi.median()) if len(toi) else None,
        "median_ppg_ratio": float(ppg.median()) if len(ppg) else None,
        "share_above_median_toi": float((toi > 1).mean()) if len(toi) else None,
        "share_above_median_ppg": float((ppg > 1).mean()) if len(ppg) else None,
    }


def run(lk: linking.Linked) -> dict[str, Any]:
    s = with_ratios(lk.stints)
    window = s[s["season_start"].between(FIRST, LAST)]
    unknown_pos = lk.stints[
        lk.stints["league"].isin(LEAGUES)
        & lk.stints["qualifies"]
        & lk.stints["season_start"].between(FIRST, LAST)
        & lk.stints["position"].isna()
        & (lk.stints["nationality"] == HOME)
    ]

    summary = {
        lg: {
            c: summarise(window[(window["league"] == lg) & (window["nationality"] == c)])
            for c in ISO3
        }
        for lg in LEAGUES
    }
    by_position = {
        lg: {
            p: summarise(
                window[
                    (window["league"] == lg)
                    & (window["nationality"] == HOME)
                    & (window["position"] == p)
                ]
            )
            for p in ("F", "D")
        }
        for lg in LEAGUES
    }
    by_season = {
        lg: [
            {
                "season": common.season_label(y),
                **summarise(
                    window[
                        (window["league"] == lg)
                        & (window["nationality"] == HOME)
                        & (window["season_start"] == y)
                    ]
                ),
            }
            for y in range(FIRST, LAST + 1)
        ]
        for lg in LEAGUES
    }

    home = window[window["nationality"] == HOME].sort_values(
        ["league", "season_start", "full_name"]
    )
    players = [
        {
            "person_id": r.person_id,
            "name": r.full_name,
            "league": r.league,
            "season": r.season,
            "position": r.position,
            "team": r.team,
            "games": r.games_played,
            "toi_per_game_s": r.toi_pg,
            "points_per_game": r.ppg,
            "median_toi_per_game_s": r.median_toi_pg,
            "median_points_per_game": r.median_ppg,
            "toi_ratio": r.toi_ratio,
            "ppg_ratio": r.ppg_ratio,
        }
        for r in home.itertuples()
    ]

    nhl = s[(s["league"] == "NHL") & (s["season_start"] >= NHL_SERIES_FIRST)]
    series_seasons = [
        y for y in range(NHL_SERIES_FIRST, LAST + 1) if y not in common.LOCKOUT_SEASONS
    ]
    nhl_series = {
        "seasons": [common.season_label(y) for y in series_seasons],
        "nations": {
            c: [
                summarise(nhl[(nhl["nationality"] == c) & (nhl["season_start"] == y)])
                for y in series_seasons
            ]
            for c in SERIES_NATIONS
        },
    }
    return {
        "definitions": {
            "window": f"{common.season_label(FIRST)}–{common.season_label(LAST)}",
            "players": "qualifying skaters (pro-rated games threshold)",
            "median": "median over all qualifying skaters of the league-season at the same position (F or D)",
            "ratio": "player value / league-season-position median; 1.0 = median",
            "toi": "time on ice per game in seconds; the NHL publishes it from 1997/98",
        },
        "summary": summary,
        "home_by_position": by_position,
        "home_by_season": by_season,
        "home_unknown_position": len(unknown_pos),
        "players": players,
        "nhl_series": nhl_series,
    }


def main() -> None:
    out = run(linking.linked())
    path = common.write_output("q5_abroad.json", out, linking.SNAPSHOT_FILES)
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
