"""Liiga (Finland) regular-season player tables, 1995/96-2025/26, from the liiga.fi JSON API.

liiga.fi's robots.txt is blank and no terms page was found. Endpoints, one
request each per season (Y = the season's end year, 1996 = 1995/96):

- /api/v2/players/stats/summed/Y/Y/runkosarja/false?dataType=basicStats&splitTeams=true
  skaters, one row per player and team: games, goals, assists, points, PIM,
  plus/minus, time on ice (seconds), `nationality` (IOC-style code) and `isU20`.
- the same with dataType=basicStatsGk: goalkeepers, including time on ice in
  every season.
- /api/v2/players/info?tournament=runkosarja&fromSeason=Y&toSeason=Y
  roster records: `dateOfBirth`, `nationality`, `countryOfBirth`. Joined on the
  player id; a player with two teams has two records.

Skater time on ice is published from 2014/15; earlier seasons carry zeros,
which are stored as missing. Nationality is Liiga's `nationality`
(citizenship, spec §4), from the stats row or else the roster record, mapped to
ISO alpha-3 (FIN, CZE, SUI -> CHE, GER -> DEU); where a season has none it is
back-filled from the same player id's other seasons (`nationality_source`). Only public statistics fields
are kept: names, birth date, nationality, birth country, position and
statistics; height, weight, birthplace and pictures are dropped.

Writes data/processed/liiga_skaters.parquet, liiga_goalies.parquet and
liiga_coverage.json, then publishes them to data/snapshot/.

    python -m src.fetch.liiga [--first 1995] [--last 2025]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.fetch._names import fold_name, iso3_from_code
from src.logging_setup import setup as logging_setup
from src.nations import ISO3

LOG = logging.getLogger(__name__)

BASE = "https://liiga.fi/api/v2"
FIRST_SEASON = 1995  # 1995/96
LAST_SEASON = 2025  # 2025/26
TOI_FROM = 2014  # 2014/15, the first season with skater time on ice

RAW_DIR = config.RAW_DIR / "liiga"
OUT_SKATERS = "liiga_skaters.parquet"
OUT_GOALIES = "liiga_goalies.parquet"
OUT_COVERAGE = "liiga_coverage.json"

# Liiga role codes: H forward, KH centre, VL/OL or VH/OH left/right wing,
# P defence, VP/OP left/right defence, MV goalkeeper. A numbered code such as
# "7. P" (seventh defenceman) or "13. H" drops its number first.
POSITION = {
    "H": "F",
    "KH": "F",
    "VL": "F",
    "OL": "F",
    "VH": "F",
    "OH": "F",
    "P": "D",
    "VP": "D",
    "OP": "D",
    "MV": "G",
}


def position(role: str | None) -> str | None:
    """Liiga role code -> F, D or G ('KH' -> 'F', '7. P' -> 'D', '-' -> None)."""
    code = re.sub(r"^\d+\.\s*", "", (role or "").strip()).upper()
    return POSITION.get(code)


COMMON_COLUMNS = [
    "season",
    "season_start",
    "player_id",
    "full_name",
    "first_name",
    "last_name",
    "name_key",
    "birth_date",
    "nat_raw",
    "nationality",
    "birth_country",
    "team",
    "team_id",
    "position",
    "position_raw",
    "is_u20",
    "nationality_source",
]
SKATER_COLUMNS = COMMON_COLUMNS + [
    "games_played",
    "goals",
    "assists",
    "points",
    "plus_minus",
    "pim",
    "toi_s",
    "toi_per_game_s",
]
GOALIE_COLUMNS = COMMON_COLUMNS + [
    "games_dressed",
    "games_played",
    "toi_s",
    "wins",
    "losses",
    "ties",
    "goals_against",
    "saves",
    "save_pct",
    "gaa",
    "shutouts",
]

INT_COLUMNS = {
    "season_start",
    "player_id",
    "team_id",
    "games_played",
    "games_dressed",
    "goals",
    "assists",
    "points",
    "plus_minus",
    "pim",
    "toi_s",
    "wins",
    "losses",
    "ties",
    "goals_against",
    "saves",
    "shutouts",
}
FLOAT_COLUMNS = {"toi_per_game_s", "save_pct", "gaa"}
BOOL_COLUMNS = {"is_u20"}


def season_label(start: int) -> str:
    """1995 -> '1995/96'."""
    return f"{start}/{str(start + 1)[-2:]}"


def seasons(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list[int]:
    return list(range(first, last + 1))


def api_year(start: int) -> int:
    """Liiga names a season by its end year: 1995/96 -> 1996."""
    return start + 1


# -- fetching -----------------------------------------------------------------


def stats_url(start: int, goalies: bool) -> str:
    y = api_year(start)
    kind = "basicStatsGk" if goalies else "basicStats"
    return f"{BASE}/players/stats/summed/{y}/{y}/runkosarja/false?dataType={kind}&splitTeams=true"


def info_url(start: int) -> str:
    y = api_year(start)
    return f"{BASE}/players/info?tournament=runkosarja&fromSeason={y}&toSeason={y}"


def fetch_season(client: PoliteClient, start: int) -> dict[str, list[dict[str, Any]]]:
    y = api_year(start)
    return {
        "skaters": client.get_json(stats_url(start, False), f"stats_{y}.json"),
        "goalies": client.get_json(stats_url(start, True), f"stats_gk_{y}.json"),
        "info": client.get_json(info_url(start), f"info_{y}.json"),
    }


# -- parsing ------------------------------------------------------------------


def _blank(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def roster_index(info: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Player id -> the first non-blank birth date, nationality and birth country."""
    out: dict[int, dict[str, Any]] = {}
    for r in info:
        rec = out.setdefault(
            int(r["id"]), {"birth_date": None, "nationality": None, "birth_country": None}
        )
        for src, col in (
            ("dateOfBirth", "birth_date"),
            ("nationality", "nationality"),
            ("countryOfBirth", "birth_country"),
        ):
            if rec[col] is None and not _blank(r.get(src)):
                rec[col] = str(r[src]).strip()
    return out


def _common(r: dict[str, Any], start: int, roster: dict[int, dict[str, Any]]) -> dict[str, Any]:
    pid = int(r["playerId"])
    info = roster.get(pid, {})
    first = (r.get("firstName") or "").strip()
    last = (r.get("lastName") or "").strip()
    full = f"{first} {last}".strip()
    nat_raw = None if _blank(r.get("nationality")) else str(r["nationality"]).strip()
    nat_raw = nat_raw or info.get("nationality")
    role = (r.get("role") or "").strip()
    return {
        "season": season_label(start),
        "season_start": start,
        "player_id": pid,
        "full_name": full,
        "first_name": first or None,
        "last_name": last or None,
        "name_key": fold_name(full),
        "birth_date": info.get("birth_date"),
        "nat_raw": nat_raw,
        "nationality": iso3_from_code(nat_raw),
        "birth_country": iso3_from_code(info.get("birth_country")),
        "team": r.get("teamName"),
        "team_id": r.get("teamId"),
        "position": "G" if r.get("goalkeeper") else position(role),
        "position_raw": role or None,
        "is_u20": r.get("isU20"),
        "nationality_source": "season" if iso3_from_code(nat_raw) else None,
    }


def parse_skaters(
    rows: list[dict[str, Any]], start: int, roster: dict[int, dict[str, Any]]
) -> pd.DataFrame:
    """One row per player and team with at least one game.

    `games` is the games-played count Liiga publishes (its per-game time on ice
    divides by it); `playedGames` can be lower and is not used for skaters.
    Time on ice before 2014/15 is zero in the API and is stored as missing.
    """
    has_toi = any((r.get("timeOnIce") or 0) > 0 for r in rows)
    out = []
    for r in rows:
        games = r.get("games") or 0
        if r.get("goalkeeper") or games <= 0:
            continue
        toi = r.get("timeOnIce") if has_toi else None
        rec = _common(r, start, roster)
        rec.update(
            {
                "games_played": games,
                "goals": r.get("goals"),
                "assists": r.get("assists"),
                "points": r.get("points"),
                "plus_minus": r.get("plusMinus"),
                "pim": r.get("penaltyMinutes"),
                "toi_s": toi,
                "toi_per_game_s": toi / games if toi is not None and games else None,
            }
        )
        out.append(rec)
    return pd.DataFrame(out, columns=SKATER_COLUMNS)


def parse_goalies(
    rows: list[dict[str, Any]], start: int, roster: dict[int, dict[str, Any]]
) -> pd.DataFrame:
    """One row per goalkeeper and team that dressed at least once.

    `games` counts games dressed (a backup included), `playedGames` games played.
    """
    out = []
    for r in rows:
        if not (r.get("games") or 0) and not (r.get("playedGames") or 0):
            continue
        rec = _common(r, start, roster)
        rec["position"] = "G"
        rec.update(
            {
                "games_dressed": r.get("games"),
                "games_played": r.get("playedGames"),
                "toi_s": r.get("timeOnIce"),
                "wins": r.get("gkWins"),
                "losses": r.get("gkLosses"),
                "ties": r.get("gkTies"),
                "goals_against": r.get("goalsAgainst"),
                "saves": r.get("blockedOrSavedShots"),
                "save_pct": r.get("savePercentage"),
                "gaa": r.get("goalsAgainstAvg"),
                "shutouts": r.get("shutOut"),
            }
        )
        out.append(rec)
    return pd.DataFrame(out, columns=GOALIE_COLUMNS)


def coerce(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if c in INT_COLUMNS:
            df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
        elif c in FLOAT_COLUMNS:
            df[c] = pd.to_numeric(df[c]).astype("float64")
        elif c in BOOL_COLUMNS:
            df[c] = df[c].astype("boolean")
        else:
            df[c] = df[c].astype("string")
    return df.sort_values(["season_start", "player_id", "team_id"], kind="stable").reset_index(
        drop=True
    )


def backfill_nationality(
    skaters: pd.DataFrame, goalies: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill a missing nationality from the same player id's other seasons (most frequent value)."""
    both = pd.concat([skaters, goalies], ignore_index=True)
    known = both[both["nationality"].notna()]
    table = known.groupby("player_id")["nationality"].agg(lambda s: s.value_counts().index[0])

    def apply(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        need = df["nationality"].isna() & df["player_id"].isin(table.index)
        df.loc[need, "nationality"] = df.loc[need, "player_id"].map(table)
        df.loc[need, "nationality_source"] = "backfill"
        return df

    return apply(skaters), apply(goalies)


def build_season(
    payload: dict[str, list[dict[str, Any]]], start: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    roster = roster_index(payload["info"])
    return (
        parse_skaters(payload["skaters"], start, roster),
        parse_goalies(payload["goalies"], start, roster),
    )


# -- coverage -----------------------------------------------------------------


def _share(s: pd.Series) -> float | None:
    return round(float(s.mean()), 4) if len(s) else None


def coverage(skaters: pd.DataFrame, goalies: pd.DataFrame, starts: list[int]) -> dict[str, Any]:
    per_season = []
    for start in starts:
        sk = skaters[skaters["season_start"] == start]
        go = goalies[goalies["season_start"] == start]
        pl = pd.concat([sk, go], ignore_index=True)
        per_season.append(
            {
                "season": season_label(start),
                "skater_rows": int(len(sk)),
                "goalie_rows": int(len(go)),
                "players": int(pl["player_id"].nunique()),
                "birth_date_share": _share(pl["birth_date"].notna()),
                "nationality_share": _share(pl["nationality"].notna()),
                "nationality_backfilled": int((pl["nationality_source"] == "backfill").sum()),
                "skater_toi_share": _share(sk["toi_s"].notna()),
                "goalie_toi_share": _share(go["toi_s"].notna()),
                "u20_rows": int(pl["is_u20"].fillna(False).sum()),
                "nations": {
                    iso: int(pl.loc[pl["nationality"] == iso, "player_id"].nunique())
                    for iso in ISO3
                },
            }
        )
    both = pd.concat([skaters, goalies], ignore_index=True)
    return {
        "source": "liiga.fi JSON API (api/v2), regular season (runkosarja)",
        "toi_from": season_label(TOI_FROM),
        "seasons": per_season,
        "unmapped_nationality_codes": sorted(
            set(both.loc[both["nat_raw"].notna() & both["nationality"].isna(), "nat_raw"])
        ),
    }


# -- entry point --------------------------------------------------------------


def run(
    first: int = FIRST_SEASON, last: int = LAST_SEASON, client: PoliteClient | None = None
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    starts = seasons(first, last)
    sk_frames, go_frames = [], []
    for start in starts:
        sk, go = build_season(fetch_season(client, start), start)
        LOG.info("liiga %s: %d skater rows, %d goalie rows", season_label(start), len(sk), len(go))
        sk_frames.append(sk)
        go_frames.append(go)
    skaters, goalies = backfill_nationality(
        pd.concat(sk_frames, ignore_index=True), pd.concat(go_frames, ignore_index=True)
    )
    skaters, goalies = coerce(skaters), coerce(goalies)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paths = [config.PROCESSED_DIR / OUT_SKATERS, config.PROCESSED_DIR / OUT_GOALIES]
    skaters.to_parquet(paths[0], index=False)
    goalies.to_parquet(paths[1], index=False)
    cov_path = config.PROCESSED_DIR / OUT_COVERAGE
    cov_path.write_text(
        json.dumps(coverage(skaters, goalies, starts), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths.append(cov_path)
    LOG.info("network calls: %d", client.network_calls)
    return snapshot.publish(paths)


def main() -> None:
    logging_setup()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--first", type=int, default=FIRST_SEASON)
    ap.add_argument("--last", type=int, default=LAST_SEASON)
    a = ap.parse_args()
    for p in run(a.first, a.last):
        LOG.info("snapshot %s", p)


if __name__ == "__main__":
    main()
