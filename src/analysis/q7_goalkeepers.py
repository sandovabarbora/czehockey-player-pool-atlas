"""Question 7: goalkeepers, in a separate section.

- Goalkeepers per million inhabitants in 2025/26: NHL, and rung 1 + 2.
- The NHL goalkeeper series from 1995/96 per nation.
- Czech goalkeepers abroad (NHL, Liiga, SHL, NL, DEL), 2020/21-2025/26: save percentage
  against the league-season median of qualifying goalkeepers.
- Young goalkeepers at home: the share of goalkeeper games played by goalkeepers aged 23 or
  less (and 20 or less) in the Extraliga, Liiga and SHL, 2014/15-2025/26.
- Who plays in goal in the Extraliga: the share of goalkeeper games played by Czech
  goalkeepers, per season.

A goalkeeper qualifies with the same pro-rated games threshold as a skater (20 of 82
games). Save percentage = saves / (saves + goals against).

    python -m src.analysis.q7_goalkeepers   -> outputs/q7_goalkeepers.json
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
ABROAD = ("NHL", "Liiga", "SHL", "NL", "DEL")
FIRST = 2020
YOUTH_FIRST = 2014
YOUTH_LEAGUES = ("Extraliga", "Liiga", "SHL")
YOUNG_MAX_AGE = 23


def goalies(stints: pd.DataFrame) -> pd.DataFrame:
    g = stints[stints["position"] == "G"].copy()
    shots = g["saves"] + g["goals_against"]
    g["save_pct"] = np.where(shots > 0, g["saves"] / shots, np.nan)
    g["age"] = [
        common.season_age(y, b) for y, b in zip(g["season_start"], g["birth_year"], strict=True)
    ]
    return g


def per_million_block(g: pd.DataFrame, pop: pd.DataFrame) -> dict[str, Any]:
    nhl = q1_per_million.counts(g, common.RUNG_1, SEASON, SEASON).loc[SEASON]
    top5 = q1_per_million.counts(g, common.TOP5, SEASON, SEASON).loc[SEASON]
    names = common.nation_names()
    rows = []
    for c in ISO3:
        p = common.population_for_season(pop, c, SEASON)
        rows.append(
            {
                "iso3": c,
                "name": names[c],
                "nhl": int(nhl[c]),
                "nhl_per_million": common.per_million(nhl[c], p),
                "top5": int(top5[c]),
                "top5_per_million": common.per_million(top5[c], p),
            }
        )
    rows.sort(key=lambda r: -r["top5_per_million"])
    for i, r in enumerate(rows, 1):
        r["rank_top5"] = i
    peers = [r for r in rows if r["iso3"] != HOME]
    return {
        "season": common.season_label(SEASON),
        "nations": rows,
        "peer_median": {
            k: float(np.median([r[k] for r in peers]))
            for k in ("nhl_per_million", "top5_per_million")
        },
    }


def abroad(g: pd.DataFrame) -> dict[str, Any]:
    q = g[g["league"].isin(ABROAD) & g["qualifies"] & g["save_pct"].notna()].copy()
    q["median_save_pct"] = q.groupby(["league", "season_start"])["save_pct"].transform("median")
    q["save_pct_minus_median"] = q["save_pct"] - q["median_save_pct"]
    w = q[q["season_start"].between(FIRST, common.LAST_SEASON) & (q["nationality"] == HOME)]
    summary = {}
    for lg in ABROAD:
        x = w[w["league"] == lg]
        summary[lg] = {
            "goalie_seasons": len(x),
            "goalies": int(x["person_id"].nunique()),
            "median_save_pct_minus_median": float(x["save_pct_minus_median"].median())
            if len(x)
            else None,
            "share_above_median": float((x["save_pct_minus_median"] > 0).mean())
            if len(x)
            else None,
        }
    players = [
        {
            "person_id": r.person_id,
            "name": r.full_name,
            "league": r.league,
            "season": r.season,
            "team": r.team,
            "games": r.games_played,
            "save_pct": r.save_pct,
            "median_save_pct": r.median_save_pct,
            "save_pct_minus_median": r.save_pct_minus_median,
        }
        for r in w.sort_values(["league", "season_start", "full_name"]).itertuples()
    ]
    return {"summary": summary, "players": players}


def youth(g: pd.DataFrame) -> dict[str, Any]:
    out = {}
    for lg in YOUTH_LEAGUES:
        rows = []
        for y in range(YOUTH_FIRST, common.LAST_SEASON + 1):
            x = g[(g["league"] == lg) & (g["season_start"] == y)]
            gp = x["games_played"].fillna(0)
            known = x["age"].notna()
            kg = float(gp[known].sum())
            rows.append(
                {
                    "season": common.season_label(y),
                    "games": float(gp.sum()),
                    "age_known_games_share": kg / float(gp.sum()) if gp.sum() else None,
                    "u24_games_share": float(gp[known & (x["age"] <= YOUNG_MAX_AGE)].sum()) / kg
                    if kg
                    else None,
                    "u21_games_share": float(gp[known & (x["age"] <= common.U21_MAX_AGE)].sum())
                    / kg
                    if kg
                    else None,
                }
            )
        vals = [r["u24_games_share"] for r in rows if r["u24_games_share"] is not None]
        out[lg] = {"seasons": rows, "mean_u24_games_share": float(np.mean(vals)) if vals else None}
    return out


def home_league_goal(g: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    for y in range(common.FIRST_SEASON, common.LAST_SEASON + 1):
        x = g[(g["league"] == "Extraliga") & (g["season_start"] == y)]
        gp = x["games_played"].fillna(0)
        if not gp.sum():
            continue
        out.append(
            {
                "season": common.season_label(y),
                "goalies": len(x),
                "home_games_share": float(gp[x["nationality"] == HOME].sum() / gp.sum()),
                "unidentified_games_share": float(gp[x["nationality"].isna()].sum() / gp.sum()),
            }
        )
    return out


def national_team_goalies(q6: dict[str, Any] | None) -> dict[str, Any] | None:
    if not q6:
        return None
    gk = [p for p in q6["home_players"] if p["position"] == "G"]
    counts: dict[str, int] = {}
    for p in gk:
        counts[p["category"]] = counts.get(p["category"], 0) + 1
    return {
        "roster_spots": len(gk),
        "by_category": counts,
        "players": [
            {k: p[k] for k in ("event", "year", "name", "club", "league", "category")} for p in gk
        ],
    }


def run(lk: linking.Linked, pop: pd.DataFrame, q6: dict[str, Any] | None = None) -> dict[str, Any]:
    g = goalies(lk.stints)
    tab = q1_per_million.counts(g, common.RUNG_1, common.FIRST_SEASON, common.LAST_SEASON)
    series = q1_per_million.series_block(
        tab, q1_per_million.per_million_table(tab, pop), common.LOCKOUT_SEASONS
    )
    return {
        "definitions": {
            "qualifying": "the pro-rated games threshold (20 of 82 games), as for skaters",
            "save_pct": "saves / (saves + goals against)",
            "young": f"age (season start - birth year) of {YOUNG_MAX_AGE} or less; u21 = 20 or less",
            "window_abroad": f"{common.season_label(FIRST)}–{common.season_label(common.LAST_SEASON)}",
        },
        "per_million": per_million_block(g, pop),
        "nhl_series": series,
        "abroad": abroad(g),
        "youth": youth(g),
        "extraliga_goal": home_league_goal(g),
        "national_team": national_team_goalies(q6),
    }


def main() -> None:
    q6_path = common.OUTPUTS_DIR / "q6_national_team.json"
    q6 = common.read_output("q6_national_team.json") if q6_path.exists() else None
    out = run(linking.linked(), common.population_table(), q6)
    path = common.write_output(
        "q7_goalkeepers.json",
        out,
        [*linking.SNAPSHOT_FILES, "population.parquet", "nhl_careers.parquet"],
    )
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
