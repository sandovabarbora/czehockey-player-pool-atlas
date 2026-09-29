"""Question 4: do young players get ice time at home?

The under-21 share of skater games, and of skater time on ice where the league publishes it,
in the Czech Extraliga against Liiga and the SHL, 2014/15-2025/26. The NL and the DEL are
shown by games only (neither publishes skater time on ice for the window), and neither
publishes birth dates, so their shares rest on the players linked to a source that does;
`age_known_games_share` says how much of each league-season that covers, and a
league-season is `measured` only when it is at least `MIN_AGE_KNOWN`.

Under 21 is `common.U21_MAX_AGE` (born in or after season start - 20). Shares are taken
over the games (or seconds) of skaters whose age is known. All players count, whatever
their nationality: the question is how much a league plays its young players.

    python -m src.analysis.q4_youth_ice_time   -> outputs/q4_youth_ice_time.json
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common, linking

LOG = logging.getLogger(__name__)

FIRST = 2014
LAST = common.LAST_SEASON
LEAGUES = ("Extraliga", "Liiga", "SHL", "NL", "DEL")
TOI_LEAGUES = ("Extraliga", "Liiga", "SHL")
MIN_AGE_KNOWN = 0.9


def youth_rows(stints: pd.DataFrame) -> pd.DataFrame:
    s = stints[
        stints["league"].isin(LEAGUES)
        & (stints["position"].fillna("") != "G")  # SHL skaters without a position stay
        & stints["season_start"].between(FIRST, LAST)
    ].copy()
    s["age"] = [
        common.season_age(y, b) for y, b in zip(s["season_start"], s["birth_year"], strict=True)
    ]
    s["u21"] = s["age"] <= common.U21_MAX_AGE
    s["age_known"] = s["age"].notna()
    return s


def league_season(g: pd.DataFrame, with_toi: bool) -> dict[str, Any]:
    gp = g["games_played"].fillna(0)
    known = g["age_known"]
    total_gp = float(gp.sum())
    known_gp = float(gp[known].sum())
    out: dict[str, Any] = {
        "skaters": len(g),
        "u21_skaters": int((g["u21"] & known).sum()),
        "games": total_gp,
        "age_known_games_share": known_gp / total_gp if total_gp else None,
        "u21_games_share": float(gp[known & g["u21"]].sum()) / known_gp if known_gp else None,
    }
    out["measured"] = bool(
        out["age_known_games_share"] is not None and out["age_known_games_share"] >= MIN_AGE_KNOWN
    )
    if with_toi:
        toi = g["toi_s"]
        has = toi.notna() & known
        total = float(toi[has].sum())
        out["toi_games_share"] = float(gp[toi.notna()].sum()) / total_gp if total_gp else None
        out["u21_toi_share"] = float(toi[has & g["u21"]].sum()) / total if total else None
        u21_toi_pg = (
            (toi[has & g["u21"]].sum() / gp[has & g["u21"]].sum())
            if gp[has & g["u21"]].sum()
            else np.nan
        )
        all_toi_pg = (toi[has].sum() / gp[has].sum()) if gp[has].sum() else np.nan
        out["u21_toi_per_game_s"] = float(u21_toi_pg)
        out["all_toi_per_game_s"] = float(all_toi_pg)
    return out


def run(lk: linking.Linked) -> dict[str, Any]:
    s = youth_rows(lk.stints)
    seasons = list(range(FIRST, LAST + 1))
    leagues: dict[str, Any] = {}
    for lg in LEAGUES:
        rows = []
        for y in seasons:
            g = s[(s["league"] == lg) & (s["season_start"] == y)]
            rows.append(
                {
                    "season": common.season_label(y),
                    **(
                        league_season(g, lg in TOI_LEAGUES)
                        if len(g)
                        else {"skaters": 0, "measured": False}
                    ),
                }
            )
        measured = [r for r in rows if r.get("measured")]
        summary: dict[str, Any] = {
            "measured_seasons": len(measured),
            "mean_u21_games_share": float(np.mean([r["u21_games_share"] for r in measured]))
            if measured
            else None,
        }
        if lg in TOI_LEAGUES:
            toi_vals = [r["u21_toi_share"] for r in measured if r.get("u21_toi_share") is not None]
            summary["mean_u21_toi_share"] = float(np.mean(toi_vals)) if toi_vals else None
        last = rows[-1]
        summary["latest"] = {
            k: last.get(k)
            for k in (
                "season",
                "u21_games_share",
                "u21_toi_share",
                "age_known_games_share",
                "measured",
            )
        }
        leagues[lg] = {"seasons": rows, "summary": summary}

    home = leagues["Extraliga"]["summary"]
    comparison = {
        lg: {
            "games_share_ratio_home_to_league": (
                home["mean_u21_games_share"] / leagues[lg]["summary"]["mean_u21_games_share"]
            )
            if leagues[lg]["summary"]["mean_u21_games_share"]
            else None,
            "toi_share_ratio_home_to_league": (
                home.get("mean_u21_toi_share") / leagues[lg]["summary"]["mean_u21_toi_share"]
            )
            if lg in TOI_LEAGUES and leagues[lg]["summary"].get("mean_u21_toi_share")
            else None,
        }
        for lg in LEAGUES
        if lg != "Extraliga"
    }
    return {
        "definitions": {
            "window": f"{common.season_label(FIRST)}–{common.season_label(LAST)}",
            "u21": "age (season start year - birth year) of 20 or less",
            "players": "skaters only (goalkeepers in q7_goalkeepers), every nationality",
            "shares": "over the games (or seconds on ice) of skaters whose age is known",
            "measured": f"a league-season is measured when the age is known for at least {MIN_AGE_KNOWN:.0%} of skater games",
            "toi": "Extraliga, Liiga and SHL publish skater time on ice for the whole window; NL and DEL by games only",
        },
        "leagues": leagues,
        "comparison": comparison,
    }


def main() -> None:
    out = run(linking.linked())
    path = common.write_output("q4_youth_ice_time.json", out, linking.SNAPSHOT_FILES)
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
