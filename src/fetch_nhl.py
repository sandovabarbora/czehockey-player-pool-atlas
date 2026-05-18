"""Fetch NHL player stats from the official NHL Stats API.

API base: https://api-web.nhle.com/v1/  (no auth)

Strategy:
  1. List all 32 teams via /standings/now
  2. For each team in each season, call /club-stats/{TEAM}/{YYYYZZZZ}/{gameType}
     to enumerate every skater + goalie who appeared in that season.
  3. For each unique player_id, call /player/{id}/landing to get birthCountry
     (the only place nationality is exposed). Cache landing responses to disk
     so re-runs are instant.
  4. Filter to birthCountry == "CZE" and write per-season parquets.

Writes:
  data/raw/nhl_skaters_{season}.parquet  - Czech skaters' all-situations stats
  data/raw/nhl_goalies_{season}.parquet  - Czech goalies' all-situations stats
  data/raw/nhl_player_meta.parquet       - Czech player metadata (one row per player)

Note on situations: club-stats returns ALL-situations totals only. 5v5 splits
are sourced from MoneyPuck in fetch_moneypuck.py.

Note on nhlpy: nhlpy 0.3.0 targets the deprecated statsapi.web.nhl.com base URL
and is not used here.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import http_get, write_parquet

LOG = logging.getLogger(__name__)

API_BASE = "https://api-web.nhle.com/v1"
GAME_TYPE_REGULAR = 2
LANDING_CACHE_DIR = config.RAW_DIR / ".cache" / "nhl_landing"
POLITE_SLEEP_S = 0.3  # between API calls


def _season_str(season: int) -> str:
    """Convert 2024 -> '20242025' (NHL season-id format)."""
    return f"{season}{season + 1}"


def list_teams() -> list[str]:
    """Return all 32 NHL team abbreviations."""
    resp = http_get(f"{API_BASE}/standings/now", sleep_after=POLITE_SLEEP_S)
    data = resp.json()
    return sorted({t["teamAbbrev"]["default"] for t in data["standings"]})


def fetch_team_club_stats(team: str, season: int) -> dict[str, Any]:
    """Fetch one team's regular-season club-stats for one season."""
    url = f"{API_BASE}/club-stats/{team}/{_season_str(season)}/{GAME_TYPE_REGULAR}"
    resp = http_get(url, sleep_after=POLITE_SLEEP_S)
    return resp.json()


def collect_player_ids(season: int) -> tuple[pd.DataFrame, pd.DataFrame, set[int]]:
    """Walk all 32 teams' club-stats and return (skaters_df, goalies_df, all_player_ids)."""
    teams = list_teams()
    LOG.info("NHL %d: fetching club-stats for %d teams", season, len(teams))
    skater_rows: list[dict[str, Any]] = []
    goalie_rows: list[dict[str, Any]] = []
    for i, team in enumerate(teams, 1):
        data = fetch_team_club_stats(team, season)
        for s in data.get("skaters", []):
            s["team"] = team
            s["season"] = season
            skater_rows.append(s)
        for g in data.get("goalies", []):
            g["team"] = team
            g["season"] = season
            goalie_rows.append(g)
        if i % 8 == 0:
            LOG.info("  %d/%d teams done (last=%s)", i, len(teams), team)
    skaters = pd.json_normalize(skater_rows)
    goalies = pd.json_normalize(goalie_rows)
    all_ids = set(skaters["playerId"].tolist() if not skaters.empty else []) | set(
        goalies["playerId"].tolist() if not goalies.empty else []
    )
    LOG.info("NHL %d: %d skaters, %d goalies, %d unique players",
             season, len(skaters), len(goalies), len(all_ids))
    return skaters, goalies, all_ids


def fetch_player_landing(player_id: int) -> dict[str, Any]:
    """Fetch /player/{id}/landing with on-disk JSON cache.

    Cache lives at data/raw/.cache/nhl_landing/{id}.json. Once populated,
    subsequent runs are instant (no API calls).
    """
    LANDING_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = LANDING_CACHE_DIR / f"{player_id}.json"
    if cache_path.exists():
        with cache_path.open(encoding="utf-8") as f:
            return json.load(f)
    resp = http_get(f"{API_BASE}/player/{player_id}/landing", sleep_after=POLITE_SLEEP_S)
    data = resp.json()
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def czech_player_metadata(player_ids: set[int]) -> pd.DataFrame:
    """Call /player/{id}/landing for every id, filter to birthCountry=='CZE'."""
    LOG.info("Fetching landing for %d unique playerIds (cached after first run)", len(player_ids))
    czech_rows: list[dict[str, Any]] = []
    started = time.time()
    for i, pid in enumerate(sorted(player_ids), 1):
        try:
            d = fetch_player_landing(pid)
        except Exception as e:  # noqa: BLE001
            LOG.warning("landing failed for %s: %s", pid, e)
            continue
        if d.get("birthCountry") != "CZE":
            continue
        czech_rows.append({
            "player_id": pid,
            "first_name": d.get("firstName", {}).get("default"),
            "last_name": d.get("lastName", {}).get("default"),
            "birth_date": d.get("birthDate"),
            "birth_city": d.get("birthCity", {}).get("cs") or d.get("birthCity", {}).get("default"),
            "birth_country": d.get("birthCountry"),
            "position": d.get("position"),
            "shoots_catches": d.get("shootsCatches"),
            "current_team_abbrev": d.get("currentTeamAbbrev"),
            "height_in": d.get("heightInInches"),
            "weight_lb": d.get("weightInPounds"),
            "is_active": d.get("isActive"),
        })
        if i % 100 == 0:
            LOG.info("  %d/%d landings checked (%d Czech so far, %.1fs)",
                     i, len(player_ids), len(czech_rows), time.time() - started)
    df = pd.DataFrame(czech_rows)
    LOG.info("Found %d Czech NHL players (across all seasons in window)", len(df))
    return df


def fetch_season(season: int) -> tuple[pd.DataFrame, pd.DataFrame, set[int]]:
    """Pull one season's raw club-stats and return data + collected playerIds."""
    skaters, goalies, all_ids = collect_player_ids(season)
    return skaters, goalies, all_ids


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons: list[int] = config.leagues()["leagues"]["nhl"]["season_window"]

    all_player_ids: set[int] = set()
    season_skaters: dict[int, pd.DataFrame] = {}
    season_goalies: dict[int, pd.DataFrame] = {}
    for season in seasons:
        skaters, goalies, ids = fetch_season(season)
        season_skaters[season] = skaters
        season_goalies[season] = goalies
        all_player_ids |= ids

    LOG.info("Total unique playerIds across %s: %d", seasons, len(all_player_ids))

    czech_meta = czech_player_metadata(all_player_ids)
    write_parquet(czech_meta, config.RAW_DIR / "nhl_player_meta.parquet")
    czech_ids: set[int] = set(czech_meta["player_id"].tolist())

    for season in seasons:
        czech_skaters = season_skaters[season][season_skaters[season]["playerId"].isin(czech_ids)]
        czech_goalies = season_goalies[season][season_goalies[season]["playerId"].isin(czech_ids)]
        write_parquet(czech_skaters, config.RAW_DIR / f"nhl_skaters_{season}.parquet")
        write_parquet(czech_goalies, config.RAW_DIR / f"nhl_goalies_{season}.parquet")
        LOG.info("Season %d: kept %d Czech skaters, %d Czech goalies",
                 season, len(czech_skaters), len(czech_goalies))


if __name__ == "__main__":
    main()
