"""The pool list for the atlas page: every Czech player seen in 2020/21-2025/26 in a covered
league (NHL, SHL, Liiga, NL, DEL, Extraliga), with his rung, games and minutes per season.

A player is Czech when his person-level nationality (see `linking`) is CZE. For a player
seen only in the Extraliga that rests on the foreigner flag (eligibility), which the row's
`nat_basis` says. One entry per person; one season row per league played in, with the
rung ('1' NHL, '2' SHL/Liiga/NL/DEL, 'home' Extraliga), games, time on ice (seconds, where
the league publishes it), and points or, for goalkeepers, save percentage.

    python -m src.analysis.pool   -> outputs/pool.json
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common, linking
from src.nations import HOME

LOG = logging.getLogger(__name__)

FIRST = 2020
LAST = common.LAST_SEASON


def display_name(names: pd.Series, roster_name: str | None = None) -> str:
    """The spelling with diacritics when any source has one (Wikipedia rosters, hokej.cz,
    Liiga), else the most common one."""
    vals = [n for n in names.dropna().tolist()] + ([roster_name] if roster_name else [])
    accented = [n for n in vals if any(ord(ch) > 127 for ch in n)]
    pool = accented or vals
    return Counter(pool).most_common(1)[0][0]


def season_row(r: Any) -> dict[str, Any]:
    gp = r.games_played
    row: dict[str, Any] = {
        "season": r.season,
        "league": r.league,
        "rung": common.rung(r.league, HOME),
        "team": r.team,
        "games": gp,
        "qualifies": bool(r.qualifies),
        "toi_s": None if pd.isna(r.toi_s) else round(float(r.toi_s)),
        "toi_per_game_s": round(float(r.toi_s) / gp, 1) if gp and not pd.isna(r.toi_s) else None,
    }
    if str(r.position) == "G":
        shots = (
            (r.saves or 0) + (r.goals_against or 0)
            if not (pd.isna(r.saves) or pd.isna(r.goals_against))
            else None
        )
        row["save_pct"] = (r.saves / shots) if shots else None
        row["goals_against"] = r.goals_against
    else:
        row.update({"goals": r.goals, "assists": r.assists, "points": r.points})
    return row


def roster_names(lk: linking.Linked) -> dict[str, str]:
    """person_id -> the roster spelling of the name (Wikipedia keeps the diacritics)."""
    if lk.rosters is None:
        return {}
    r = lk.rosters.dropna(subset=["birth_date"])
    sid = r["player"].map(common.link_key) + "|" + r["birth_date"].astype("string")
    ids = lk.identities[lk.identities["league"] == "roster"].set_index("source_id")["person_idx"]
    pid = dict(zip(lk.persons["person_idx"], lk.persons["person_id"], strict=True))
    out: dict[str, str] = {}
    for s_id, name in zip(sid, r["player"], strict=True):
        if s_id in ids.index:
            out.setdefault(pid[int(ids[s_id])], name)
    return out


def build_pool(stints: pd.DataFrame, names: dict[str, str] | None = None) -> list[dict[str, Any]]:
    names = names or {}
    s = stints[
        (stints["nationality"] == HOME)
        & stints["season_start"].between(FIRST, LAST)
        & stints["league"].isin(common.LEAGUES)
    ]
    s = s.assign(_rung=s["league"].map(lambda lg: common.RUNG_ORDER[common.rung(lg, HOME)]))
    out = []
    for pid, g in s.groupby("person_id", sort=False):
        g = g.sort_values(["season_start", "_rung"])
        latest = g[g["season_start"] == g["season_start"].max()]
        latest_best = latest.sort_values(["_rung", "games_played"], ascending=[True, False]).iloc[0]
        by = g["birth_year"].dropna()
        pos = g["position"].dropna()
        out.append(
            {
                "person_id": pid,
                "name": display_name(g["full_name"], names.get(pid)),
                "birth_date": g["birth_date"].dropna().iloc[0]
                if g["birth_date"].notna().any()
                else None,
                "birth_year": int(by.iloc[0]) if len(by) else None,
                "position": Counter(pos).most_common(1)[0][0] if len(pos) else None,
                "nat_basis": g["person_nat_basis"].dropna().iloc[0]
                if "person_nat_basis" in g and g["person_nat_basis"].notna().any()
                else None,
                "leagues": sorted(set(g["league"]), key=lambda lg: common.LEAGUES.index(lg)),
                "latest": {
                    "season": latest_best["season"],
                    "league": latest_best["league"],
                    "rung": common.rung(latest_best["league"], HOME),
                    "team": latest_best["team"],
                },
                "best_rung": common.rung(g.sort_values("_rung").iloc[0]["league"], HOME),
                "games": float(g["games_played"].fillna(0).sum()),
                "seasons": [season_row(r) for r in g.itertuples()],
            }
        )
    order = {"1": 0, "2": 1, "home": 2, "other": 3}
    out.sort(
        key=lambda p: (
            -int(p["latest"]["season"][:4]),
            order[p["latest"]["rung"]],
            -p["games"],
            p["name"],
        )
    )
    return out


def run(lk: linking.Linked) -> dict[str, Any]:
    players = build_pool(lk.stints, roster_names(lk))
    latest_season = common.season_label(LAST)
    current = [p for p in players if p["latest"]["season"] == latest_season]
    return {
        "definitions": {
            "window": f"{common.season_label(FIRST)}–{common.season_label(LAST)}",
            "czech": "person-level nationality CZE (outputs/linking.json); `nat_basis` gives the source",
            "rungs": {
                "1": "NHL",
                "2": "SHL, Liiga, National League, DEL",
                "home": "Czech Extraliga",
            },
            "not_covered": "KHL (excluded by design), AHL (terms), Czech 1st league and every other league",
            "toi": "seconds; NHL skaters from 1997/98, Extraliga from 2013/14, Liiga from 2014/15, "
            "SHL from 2009/10, DEL skaters from 2022/23; NL goalkeepers only",
        },
        "counts": {
            "players": len(players),
            "in_latest_season": len(current),
            "latest_season": latest_season,
            "latest_by_rung": dict(Counter(p["latest"]["rung"] for p in current)),
            "latest_by_position": dict(Counter(p["position"] for p in current)),
            "by_nat_basis": dict(Counter(p["nat_basis"] for p in players)),
            "by_best_rung": dict(Counter(p["best_rung"] for p in players)),
            "seasons": {
                common.season_label(y): int(
                    np.sum(
                        [
                            any(r["season"] == common.season_label(y) for r in p["seasons"])
                            for p in players
                        ]
                    )
                )
                for y in range(FIRST, LAST + 1)
            },
        },
        "players": players,
    }


def main() -> None:
    out = run(linking.linked())
    path = common.write_output("pool.json", out, linking.SNAPSHOT_FILES)
    LOG.info("wrote %s (%d players)", path, out["counts"]["players"])


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
