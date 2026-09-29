"""NHL regular-season player tables, 1995/96-2025/26, from the NHL stats REST API.

Endpoints (no auth, no robots.txt on either host):

- api.nhle.com/stats/rest/en/{skater,goalie}/{bios,summary}
  ?limit=-1&cayenneExp=seasonId=YYYYYYYY and gameTypeId=2
  One row per player and season (a traded player's teams are joined in
  `teamAbbrevs`). `bios` carries nationalityCode, birthDate, birthCountryCode,
  position and draft; `summary` carries the season statistics.
- api-web.nhle.com/v1/player/{id}/landing -> seasonTotals: the player's whole
  career in every league (juniors, Extraliga, AHL, ...). Fetched only for NHL
  players of the ten compared nations, since the analysis uses careers only for
  them (the AHL view through NHL careers, spec §2, which is survivor-biased).

Nationality is the NHL `nationalityCode` (citizenship, spec §4). The NHL
recodes Czechoslovak-era births to the present-day state. Skater time on ice
is null in 1995/96 and 1996/97 (the league did not publish it); goalie time on
ice is present in every season. 2004/05 was cancelled (lockout) and has no rows.

Only public statistics fields are kept: names, birth date, birth country,
nationality, position, handedness, draft and statistics. Height, weight, birth
city and images are dropped.

Writes data/processed/nhl_skaters.parquet, nhl_goalies.parquet,
nhl_careers.parquet and nhl_coverage.json, then publishes them to
data/snapshot/ (src.snapshot).

    python -m src.fetch.nhl [--first 1995] [--last 2025] [--no-careers]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.logging_setup import setup as logging_setup
from src.nations import ISO3

LOG = logging.getLogger(__name__)

STATS_BASE = "https://api.nhle.com/stats/rest/en"
WEB_BASE = "https://api-web.nhle.com/v1"
GAME_TYPE_REGULAR = 2
FIRST_SEASON = 1995  # 1995/96
LAST_SEASON = 2025  # 2025/26
CANCELLED_SEASONS = frozenset({2004})  # 2004/05 lockout
SKATER_TOI_FROM = 1997  # 1997/98
MIN_GAMES = 20  # the "NHL player" threshold of spec §3.1

RAW_DIR = config.RAW_DIR / "nhl"
OUT_SKATERS = "nhl_skaters.parquet"
OUT_GOALIES = "nhl_goalies.parquet"
OUT_CAREERS = "nhl_careers.parquet"
OUT_COVERAGE = "nhl_coverage.json"

# bios field -> column. Shared by skaters and goalies.
BIO_FIELDS: dict[str, str] = {
    "playerId": "player_id",
    "lastName": "last_name",
    "birthDate": "birth_date",
    "birthCountryCode": "birth_country",
    "nationalityCode": "nationality",
    "shootsCatches": "shoots_catches",
    "draftYear": "draft_year",
    "draftRound": "draft_round",
    "draftOverall": "draft_overall",
    "firstSeasonForGameType": "first_nhl_season_id",
}

SKATER_SUMMARY_FIELDS: dict[str, str] = {
    "playerId": "player_id",
    "skaterFullName": "full_name",
    "positionCode": "position",
    "teamAbbrevs": "teams",
    "gamesPlayed": "games_played",
    "goals": "goals",
    "assists": "assists",
    "points": "points",
    "pointsPerGame": "points_per_game",
    "plusMinus": "plus_minus",
    "penaltyMinutes": "pim",
    "shots": "shots",
    "ppPoints": "pp_points",
    "shPoints": "sh_points",
    "evPoints": "ev_points",
    "timeOnIcePerGame": "toi_per_game_s",
}

GOALIE_SUMMARY_FIELDS: dict[str, str] = {
    "playerId": "player_id",
    "goalieFullName": "full_name",
    "teamAbbrevs": "teams",
    "gamesPlayed": "games_played",
    "gamesStarted": "games_started",
    "wins": "wins",
    "losses": "losses",
    "otLosses": "ot_losses",
    "ties": "ties",
    "shutouts": "shutouts",
    "shotsAgainst": "shots_against",
    "saves": "saves",
    "goalsAgainst": "goals_against",
    "savePct": "save_pct",
    "goalsAgainstAverage": "gaa",
    "timeOnIce": "toi_s",
}

SEASON_COLUMNS = ["season", "season_id", "season_start"]
SKATER_COLUMNS = (
    SEASON_COLUMNS
    + [
        "player_id",
        "full_name",
        "last_name",
        "birth_date",
        "birth_country",
        "nationality",
        "position",
    ]
    + [
        "shoots_catches",
        "draft_year",
        "draft_round",
        "draft_overall",
        "first_nhl_season_id",
        "teams",
    ]
    + [
        c
        for c in SKATER_SUMMARY_FIELDS.values()
        if c not in {"player_id", "full_name", "position", "teams"}
    ]
)
GOALIE_COLUMNS = (
    SEASON_COLUMNS
    + [
        "player_id",
        "full_name",
        "last_name",
        "birth_date",
        "birth_country",
        "nationality",
        "position",
    ]
    + [
        "shoots_catches",
        "draft_year",
        "draft_round",
        "draft_overall",
        "first_nhl_season_id",
        "teams",
    ]
    + [c for c in GOALIE_SUMMARY_FIELDS.values() if c not in {"player_id", "full_name", "teams"}]
)
CAREER_COLUMNS = [
    "player_id",
    "season",
    "season_id",
    "season_start",
    "sequence",
    "league",
    "team",
    "games_played",
    "goals",
    "assists",
    "points",
    "pim",
    "wins",
    "losses",
    "gaa",
    "save_pct",
]


def season_id(start: int) -> int:
    """1995 -> 19951996."""
    return start * 10000 + start + 1


def season_label(start: int) -> str:
    """1995 -> '1995/96'."""
    return f"{start}/{str(start + 1)[-2:]}"


def seasons(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list[int]:
    return [s for s in range(first, last + 1) if s not in CANCELLED_SEASONS]


# -- fetching -----------------------------------------------------------------


def stats_url(kind: str, report: str) -> str:
    return f"{STATS_BASE}/{kind}/{report}"


def stats_params(start: int) -> dict[str, Any]:
    return {
        "limit": -1,
        "cayenneExp": f"seasonId={season_id(start)} and gameTypeId={GAME_TYPE_REGULAR}",
    }


def fetch_report(client: PoliteClient, kind: str, report: str, start: int) -> list[dict[str, Any]]:
    """One stats REST report for one season; checks that `total` rows came back."""
    payload = client.get_json(
        stats_url(kind, report),
        f"{kind}_{report}_{season_id(start)}.json",
        params=stats_params(start),
    )
    rows = payload["data"]
    if payload.get("total") != len(rows):
        raise ValueError(
            f"{kind}/{report} {start}: total={payload.get('total')} but {len(rows)} rows"
        )
    return rows


def fetch_landing(client: PoliteClient, player_id: int) -> dict[str, Any]:
    return client.get_json(f"{WEB_BASE}/player/{player_id}/landing", f"landing/{player_id}.json")


# -- parsing ------------------------------------------------------------------


def _pick(rows: list[dict[str, Any]], fields: dict[str, str]) -> pd.DataFrame:
    return pd.DataFrame(
        [{col: r.get(src) for src, col in fields.items()} for r in rows],
        columns=list(fields.values()),
    )


def build_season(
    kind: str, bios: list[dict[str, Any]], summary: list[dict[str, Any]], start: int
) -> pd.DataFrame:
    """Join one season's bios and summary rows on player id (one row per player)."""
    summary_fields = SKATER_SUMMARY_FIELDS if kind == "skater" else GOALIE_SUMMARY_FIELDS
    columns = SKATER_COLUMNS if kind == "skater" else GOALIE_COLUMNS
    s = _pick(summary, summary_fields)
    b = _pick(bios, BIO_FIELDS)
    for name, df in (("summary", s), ("bios", b)):
        dup = df["player_id"].duplicated()
        if dup.any():
            raise ValueError(
                f"{kind} {name} {start}: duplicated player ids {df.loc[dup, 'player_id'].tolist()}"
            )
    missing = set(s["player_id"]) ^ set(b["player_id"])
    if missing:
        raise ValueError(f"{kind} {start}: bios and summary disagree on {sorted(missing)[:10]}")
    df = s.merge(b, on="player_id", how="inner", validate="one_to_one")
    if kind == "goalie":
        df["position"] = "G"
    df["season"] = season_label(start)
    df["season_id"] = season_id(start)
    df["season_start"] = start
    return df[columns]


def _coerce(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    ints = ["season_id", "season_start", "player_id", "games_played"]
    ints += (
        [
            "goals",
            "assists",
            "points",
            "pim",
            "shots",
            "pp_points",
            "sh_points",
            "ev_points",
            "plus_minus",
        ]
        if kind == "skater"
        else [
            "games_started",
            "wins",
            "losses",
            "ot_losses",
            "ties",
            "shutouts",
            "shots_against",
            "saves",
            "goals_against",
        ]
    )
    ints += ["draft_year", "draft_round", "draft_overall", "first_nhl_season_id"]
    for c in ints:
        df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
    floats = (
        ["points_per_game", "toi_per_game_s"] if kind == "skater" else ["save_pct", "gaa", "toi_s"]
    )
    for c in floats:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    for c in [
        "season",
        "full_name",
        "last_name",
        "birth_date",
        "birth_country",
        "nationality",
        "position",
        "shoots_catches",
        "teams",
    ]:
        df[c] = df[c].astype("string")
    return df.sort_values(["season_start", "player_id"], kind="stable").reset_index(drop=True)


def build_table(client: PoliteClient, kind: str, starts: list[int]) -> pd.DataFrame:
    frames = []
    for start in starts:
        bios = fetch_report(client, kind, "bios", start)
        summary = fetch_report(client, kind, "summary", start)
        frames.append(build_season(kind, bios, summary, start))
        LOG.info("%s %s: %d rows", kind, season_label(start), len(frames[-1]))
    return _coerce(pd.concat(frames, ignore_index=True), kind)


def career_rows(landing: dict[str, Any]) -> list[dict[str, Any]]:
    """Regular-season career rows (every league) from one landing payload."""
    out = []
    for r in landing.get("seasonTotals", []):
        if r.get("gameTypeId") != GAME_TYPE_REGULAR:
            continue
        sid = int(r["season"])
        out.append(
            {
                "player_id": int(landing["playerId"]),
                "season": season_label(sid // 10000),
                "season_id": sid,
                "season_start": sid // 10000,
                "sequence": r.get("sequence"),
                "league": r.get("leagueAbbrev"),
                "team": (r.get("teamName") or {}).get("default"),
                "games_played": r.get("gamesPlayed"),
                "goals": r.get("goals"),
                "assists": r.get("assists"),
                "points": r.get("points"),
                "pim": r.get("pim"),
                "wins": r.get("wins"),
                "losses": r.get("losses"),
                "gaa": r.get("goalsAgainstAvg"),
                "save_pct": r.get("savePctg"),
            }
        )
    return out


def build_careers(client: PoliteClient, player_ids: list[int]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, pid in enumerate(player_ids, 1):
        rows += career_rows(fetch_landing(client, pid))
        if i % 100 == 0:
            LOG.info("landing %d/%d", i, len(player_ids))
    df = pd.DataFrame(rows, columns=CAREER_COLUMNS)
    for c in [
        "player_id",
        "season_id",
        "season_start",
        "sequence",
        "games_played",
        "goals",
        "assists",
        "points",
        "pim",
        "wins",
        "losses",
    ]:
        df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
    for c in ["gaa", "save_pct"]:
        df[c] = pd.to_numeric(df[c]).astype("float64")
    for c in ["season", "league", "team"]:
        df[c] = df[c].astype("string")
    # The landing feed repeats a few junior rows verbatim (same season, sequence, team, stats).
    dup = df.duplicated()
    if dup.any():
        LOG.info("dropped %d verbatim duplicate career rows", int(dup.sum()))
        df = df[~dup]
    return df.sort_values(["player_id", "season_id", "sequence"], kind="stable").reset_index(
        drop=True
    )


def career_player_ids(skaters: pd.DataFrame, goalies: pd.DataFrame) -> list[int]:
    """NHL players of the ten compared nations: the only ones whose careers are fetched."""
    both = pd.concat([skaters[["player_id", "nationality"]], goalies[["player_id", "nationality"]]])
    return sorted(int(p) for p in both.loc[both["nationality"].isin(ISO3), "player_id"].unique())


# -- coverage -----------------------------------------------------------------


def coverage(
    skaters: pd.DataFrame, goalies: pd.DataFrame, careers: pd.DataFrame | None, starts: list[int]
) -> dict[str, Any]:
    """Rows, field completeness and per-nation counts for every season."""
    players = pd.concat(
        [skaters.assign(kind="skater"), goalies.assign(kind="goalie")], ignore_index=True
    )
    per_season = []
    for start in sorted(set(starts) | CANCELLED_SEASONS & set(range(min(starts), max(starts) + 1))):
        sk = skaters[skaters["season_start"] == start]
        go = goalies[goalies["season_start"] == start]
        pl = players[players["season_start"] == start]
        by_nation = {}
        for iso in ISO3:
            n = pl[pl["nationality"] == iso]
            by_nation[iso] = {
                "players": int(len(n)),
                "gp20": int((n["games_played"] >= MIN_GAMES).sum()),
            }
        per_season.append(
            {
                "season": season_label(start),
                "cancelled": start in CANCELLED_SEASONS,
                "skaters": int(len(sk)),
                "goalies": int(len(go)),
                "nationality_share": round(float(pl["nationality"].notna().mean()), 4)
                if len(pl)
                else None,
                "birth_date_share": round(float(pl["birth_date"].notna().mean()), 4)
                if len(pl)
                else None,
                "skater_toi_share": round(float(sk["toi_per_game_s"].notna().mean()), 4)
                if len(sk)
                else None,
                "goalie_toi_share": round(float(go["toi_s"].notna().mean()), 4)
                if len(go)
                else None,
                "nations": by_nation,
            }
        )
    out: dict[str, Any] = {
        "source": "NHL stats REST (api.nhle.com/stats/rest), regular season",
        "min_games": MIN_GAMES,
        "seasons": per_season,
        "missing_nationality": int(players["nationality"].isna().sum()),
    }
    if careers is not None:
        ids = set(career_player_ids(skaters, goalies))
        with_rows = set(careers["player_id"].dropna().astype(int))
        out["careers"] = {
            "players_requested": len(ids),
            "players_with_rows": len(ids & with_rows),
            "rows": int(len(careers)),
            "leagues": int(careers["league"].nunique()),
        }
    return out


# -- entry point --------------------------------------------------------------


def run(
    first: int = FIRST_SEASON,
    last: int = LAST_SEASON,
    careers: bool = True,
    client: PoliteClient | None = None,
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    starts = seasons(first, last)
    skaters = build_table(client, "skater", starts)
    goalies = build_table(client, "goalie", starts)
    career_df = build_careers(client, career_player_ids(skaters, goalies)) if careers else None

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paths = [config.PROCESSED_DIR / OUT_SKATERS, config.PROCESSED_DIR / OUT_GOALIES]
    skaters.to_parquet(paths[0], index=False)
    goalies.to_parquet(paths[1], index=False)
    if career_df is not None:
        paths.append(config.PROCESSED_DIR / OUT_CAREERS)
        career_df.to_parquet(paths[-1], index=False)
    cov_path = config.PROCESSED_DIR / OUT_COVERAGE
    cov_path.write_text(
        json.dumps(coverage(skaters, goalies, career_df, starts), indent=1) + "\n", encoding="utf-8"
    )
    paths.append(cov_path)
    LOG.info("network calls: %d", client.network_calls)
    return snapshot.publish(paths)


def main() -> None:
    logging_setup()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--first", type=int, default=FIRST_SEASON)
    ap.add_argument("--last", type=int, default=LAST_SEASON)
    ap.add_argument("--no-careers", action="store_true")
    a = ap.parse_args()
    for p in run(a.first, a.last, careers=not a.no_careers):
        LOG.info("snapshot %s", p)


if __name__ == "__main__":
    main()
