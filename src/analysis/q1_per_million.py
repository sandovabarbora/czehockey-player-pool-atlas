"""Question 1: is the pool thin? Players per million inhabitants, Czechia against the peers.

- Headline, 2025/26: NHL players, and rung 1 + 2 ("top-5 leagues": NHL, SHL, Liiga, NL, DEL)
  players, per million.
- The NHL series from 1995/96 (2004/05 was not played).
- The rung 1 + 2 series from 2008/09, the first season the NL is covered.

A player counts in a league-season with at least the pro-rated games threshold
(`common.THRESHOLD_SHARE`: 20 of 82 NHL games). A player who qualifies in two leagues in one
season counts once. Nationality is the person's (see `linking`). Population is Eurostat's
1 January figure for the season's second year.

Rung-2 rows whose nationality could not be identified (DEL before 2022/23, NL foreign
licences, SHL before about 2010) are counted per league-season in `coverage`; a season is
`complete` only when every rung-2 league has at least `COMPLETE_SHARE` of its qualifying
rows identified. In incomplete seasons the counts are lower bounds.

    python -m src.analysis.q1_per_million   -> outputs/q1_per_million.json
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common, linking
from src.nations import HOME, ISO3

LOG = logging.getLogger(__name__)

HEADLINE_SEASON = 2025
TOP5_FIRST = 2008
COMPLETE_SHARE = 0.90


def best_rung_per_person(rows: pd.DataFrame) -> pd.DataFrame:
    """One row per (season_start, person_id): nationality and the best rung the person
    qualified in that season."""
    r = rows.assign(_rank=rows["league"].map(lambda lg: 0 if lg in common.RUNG_1 else 1))
    r = r.sort_values(["season_start", "person_id", "_rank"]).drop_duplicates(
        ["season_start", "person_id"]
    )
    r["rung"] = np.where(r["_rank"] == 0, "1", "2")
    return r[
        ["season_start", "person_id", "nationality", "rung", "league", "position", "birth_year"]
    ]


def counts(
    stints: pd.DataFrame, leagues: frozenset[str], first: int, last: int, qualify: str = "qualifies"
) -> pd.DataFrame:
    """Persons per nation and season (index: season_start, columns: ISO3)."""
    rows = stints[
        stints["league"].isin(leagues)
        & stints[qualify]
        & stints["season_start"].between(first, last)
    ]
    per = best_rung_per_person(rows)
    per = per[per["nationality"].isin(ISO3)]
    tab = per.groupby(["season_start", "nationality"]).size().unstack(fill_value=0)
    return tab.reindex(index=range(first, last + 1), columns=list(ISO3), fill_value=0)


def per_million_table(tab: pd.DataFrame, pop: pd.DataFrame) -> pd.DataFrame:
    out = tab.astype("float64").copy()
    for s in out.index:
        for c in out.columns:
            out.at[s, c] = common.per_million(tab.at[s, c], common.population_for_season(pop, c, s))
    return out


def coverage(stints: pd.DataFrame, first: int, last: int) -> list[dict[str, Any]]:
    out = []
    q = stints[stints["qualifies"] & stints["league"].isin(common.TOP5)]
    for s in range(first, last + 1):
        row: dict[str, Any] = {"season": common.season_label(s), "leagues": {}}
        shares = []
        for lg in ("NHL", *sorted(common.RUNG_2)):
            g = q[(q["league"] == lg) & (q["season_start"] == s)]
            if g.empty:
                row["leagues"][lg] = None
                continue
            share = float(g["nationality"].notna().mean())
            row["leagues"][lg] = {
                "qualifying": len(g),
                "unidentified": int(g["nationality"].isna().sum()),
                "identified_share": share,
            }
            if lg in common.RUNG_2:
                shares.append(share)
        row["complete"] = bool(shares) and min(shares) >= COMPLETE_SHARE
        out.append(row)
    return out


def _ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def headline(
    stints: pd.DataFrame,
    pop: pd.DataFrame,
    season: int = HEADLINE_SEASON,
    qualify: str = "qualifies",
) -> dict[str, Any]:
    nhl = counts(stints, common.RUNG_1, season, season, qualify).loc[season]
    top5 = counts(stints, common.TOP5, season, season, qualify).loc[season]
    rows = stints[
        stints["league"].isin(common.TOP5)
        & stints[qualify]
        & (stints["season_start"] == season)
        & stints["nationality"].isin(ISO3)
    ]
    by_league = (
        rows.drop_duplicates(["league", "person_id"])
        .groupby(["nationality", "league"])
        .size()
        .unstack(fill_value=0)
    )
    names = common.nation_names()
    nations = []
    for c in ISO3:
        p = common.population_for_season(pop, c, season)
        nations.append(
            {
                "iso3": c,
                "name": names[c],
                "population": p,
                "nhl": int(nhl[c]),
                "nhl_per_million": common.per_million(nhl[c], p),
                "top5": int(top5[c]),
                "top5_per_million": common.per_million(top5[c], p),
                "by_league": {
                    lg: int(by_league.at[c, lg])
                    if c in by_league.index and lg in by_league.columns
                    else 0
                    for lg in ("NHL", "SHL", "Liiga", "NL", "DEL")
                },
            }
        )
    for key in ("nhl_per_million", "top5_per_million"):
        order = sorted(nations, key=lambda n: -n[key])
        for i, n in enumerate(order, 1):
            n[f"rank_{key.removesuffix('_per_million')}"] = i
    peers = [n for n in nations if n["iso3"] != HOME]
    home = next(n for n in nations if n["iso3"] == HOME)
    med = {
        k: float(np.median([n[k] for n in peers])) for k in ("nhl_per_million", "top5_per_million")
    }
    return {
        "season": common.season_label(season),
        "nations": sorted(nations, key=lambda n: -n["top5_per_million"]),
        "peer_median": med,
        "home": {
            "iso3": HOME,
            **{
                k: home[k]
                for k in (
                    "nhl",
                    "nhl_per_million",
                    "top5",
                    "top5_per_million",
                    "rank_nhl",
                    "rank_top5",
                )
            },
            "nhl_vs_peer_median": _ratio(home["nhl_per_million"], med["nhl_per_million"]),
            "top5_vs_peer_median": _ratio(home["top5_per_million"], med["top5_per_million"]),
        },
    }


def series_block(
    tab: pd.DataFrame, pm: pd.DataFrame, missing: frozenset[int] = frozenset()
) -> dict[str, Any]:
    seasons = list(tab.index)
    return {
        "seasons": [common.season_label(s) for s in seasons],
        "nations": {
            c: {
                "n": [None if s in missing else int(tab.at[s, c]) for s in seasons],
                "per_million": [None if s in missing else float(pm.at[s, c]) for s in seasons],
            }
            for c in tab.columns
        },
    }


def thresholds(stints: pd.DataFrame, league: str, first: int, last: int) -> list[int | None]:
    t = stints[stints["league"] == league].groupby("season_start")["threshold"].first()
    return [int(t[s]) if s in t.index else None for s in range(first, last + 1)]


def run(lk: linking.Linked, pop: pd.DataFrame) -> dict[str, Any]:
    s = lk.stints.copy()
    s["any_game"] = s["games_played"].fillna(0) >= 1
    s["fixed_20"] = s["games_played"].fillna(0) >= common.THRESHOLD_GAMES

    nhl_tab = counts(s, common.RUNG_1, common.FIRST_SEASON, common.LAST_SEASON)
    nhl = series_block(nhl_tab, per_million_table(nhl_tab, pop), common.LOCKOUT_SEASONS)
    nhl["threshold"] = thresholds(s, "NHL", common.FIRST_SEASON, common.LAST_SEASON)

    top_tab = counts(s, common.TOP5, TOP5_FIRST, common.LAST_SEASON)
    top5 = series_block(top_tab, per_million_table(top_tab, pop))
    top5["coverage"] = coverage(s, TOP5_FIRST, common.LAST_SEASON)
    top5["complete_seasons"] = [c["season"] for c in top5["coverage"] if c["complete"]]

    head = headline(s, pop)
    head["coverage"] = coverage(s, HEADLINE_SEASON, HEADLINE_SEASON)[0]
    head["sensitivity"] = {
        "any_game": headline(s, pop, qualify="any_game")["home"],
        "fixed_20_games": headline(s, pop, qualify="fixed_20")["home"],
    }
    home_series = nhl["nations"][HOME]["n"]
    valid = [
        (common.season_label(y), n)
        for y, n in zip(
            range(common.FIRST_SEASON, common.LAST_SEASON + 1), home_series, strict=True
        )
        if n is not None
    ]
    peak = max(valid, key=lambda x: x[1])
    return {
        "definitions": {
            "threshold": "at least 20 of 82 games, pro-rated to the league-season's schedule "
            "(95th percentile of skater games played)",
            "top5": "rung 1 (NHL) + rung 2 (SHL, Liiga, National League, DEL); a player counts once per season",
            "population": "Eurostat demo_gind, 1 January of the season's second year",
            "nationality": "the person's nationality from outputs/linking.json",
            "complete_season": f"every rung-2 league has at least {COMPLETE_SHARE:.0%} of qualifying rows identified",
        },
        "headline": head,
        "nhl_series": nhl,
        "nhl_home_peak": {
            "season": peak[0],
            "n": peak[1],
            "latest": {"season": valid[-1][0], "n": valid[-1][1]},
        },
        "top5_series": top5,
    }


def main() -> None:
    out = run(linking.linked(), common.population_table())
    path = common.write_output(
        "q1_per_million.json", out, [*linking.SNAPSHOT_FILES, "population.parquet"]
    )
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
