"""Swiss National League regular-season player tables, 2008/09-2025/26, from data.sihf.ch.

The SIHF game centre reads its tables from one JSON endpoint
(data.sihf.ch has no robots.txt disallowing it; the terms page is blank):

    https://data.sihf.ch/Statistic/api/cms/cache300
      ?alias=player|goalkeeper&searchQuery=1//1&language=de
      &filterBy=Season,Phase[,Licence]&filterQuery=<season>/<phase>[/1]

`searchQuery=1//1` selects the National League. Past seasons unlock through the
site's own filter parameters (its game-centre script builds them the same way):
`filterBy` names the filters and `filterQuery` gives their values, joined by
"/". A filter given in `filterQuery` alone is ignored, which is why earlier
attempts returned only the running season. The season value is the end year
(2026 = 2025/26); the season list goes back to 2008/09. The regular-season
phase id differs per season, so it is read first from the phase filter the API
returns for `filterBy=Season,Phase&filterQuery=<season>/`.

Per season four requests: the phase list, skaters, skaters with a foreign
licence, goalies. The licence filter is accepted for goalies but returns no one
in any season (Kloten's Finnish import Juha Metsola, 2023/24, included), so it
is not used there and goalies' licence is left unknown.

What the source gives and what it does not:

- games, goals, assists, points, penalty minutes and +/- for skaters; games,
  goals against, saves and time played for goalies. No time on ice for skaters
  (spec §3.4 measures NL by games only).
- No player id, birth date or nationality. The only nationality signal is the
  licence: Swiss licence or foreign licence (`licence` = "CH" / "foreign";
  skaters only),
  which is eligibility, not citizenship (spec §4). Swiss-licensed players
  include naturalised and dual nationals; Czech players in the NL can only be
  found by linking names to the other sources.
- Position is "Stürmer" or "Verteidiger"; a handful of short-stint players
  have "-" (unknown), kept as null.
- Names are "Last First" without a comma. `name_key` assumes the last token is
  the first name; `name_tokens` (sorted folded tokens) is order-free for linking.

Writes data/processed/nl_skaters.parquet, nl_goalies.parquet and
nl_coverage.json, then publishes them to data/snapshot/.

    python -m src.fetch.nl [--first 2008] [--last 2025]
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
from src.fetch._names import fold_name
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

URL = "https://data.sihf.ch/Statistic/api/cms/cache300"
LEAGUE_QUERY = "1//1"  # National League
FIRST_SEASON = 2008  # 2008/09, the first season the API lists
LAST_SEASON = 2025  # 2025/26

RAW_DIR = config.RAW_DIR / "nl"
OUT_SKATERS = "nl_skaters.parquet"
OUT_GOALIES = "nl_goalies.parquet"
OUT_COVERAGE = "nl_coverage.json"

POSITION = {"Stürmer": "F", "Verteidiger": "D", "Torhüter": "G"}
REGULAR_RE = re.compile(r"regular|qualifikation", re.I)

SKATER_COLUMNS = [
    "season",
    "season_start",
    "phase_id",
    "name_raw",
    "full_name",
    "name_key",
    "name_tokens",
    "team_id",
    "team",
    "position",
    "licence",
    "games_played",
    "goals",
    "assists",
    "points",
    "pim",
    "plus_minus",
]
GOALIE_COLUMNS = [
    "season",
    "season_start",
    "phase_id",
    "name_raw",
    "full_name",
    "name_key",
    "name_tokens",
    "team_id",
    "team",
    "position",
    "licence",
    "games_played",
    "games_started",
    "toi_s",
    "goals_against",
    "shots_against",
    "saves",
    "pim",
    "goals",
    "assists",
]


def season_label(start: int) -> str:
    return f"{start}/{str(start + 1)[-2:]}"


def season_alias(start: int) -> str:
    """The API's season value is the end year: 2025/26 -> '2026'."""
    return str(start + 1)


def params(alias: str, start: int, phase: str = "", foreign: bool = False) -> dict[str, str]:
    by, query = ["Season", "Phase"], [season_alias(start), phase]
    if foreign:
        by.append("Licence")
        query.append("1")
    return {
        "alias": alias,
        "searchQuery": LEAGUE_QUERY,
        "filterBy": ",".join(by),
        "filterQuery": "/".join(query),
        "language": "de",
    }


def _selected(payload: dict[str, Any], alias: str) -> str | None:
    return next(
        (f.get("selected") for f in payload.get("filters", []) if f.get("alias") == alias), None
    )


def regular_phase(payload: dict[str, Any]) -> str:
    """The regular-season phase id from the phase filter of a season response."""
    phase = next((f for f in payload.get("filters", []) if f.get("alias") == "Phase"), None)
    if phase is None:
        raise ValueError("response has no Phase filter")
    hits = [e["alias"] for e in phase["entries"] if REGULAR_RE.search(e.get("name") or "")]
    if len(hits) != 1:
        raise ValueError(f"expected one regular-season phase, got {phase['entries']}")
    return hits[0]


def check_response(payload: dict[str, Any], start: int, phase: str, foreign: bool) -> None:
    """The API falls back to its default season silently; refuse anything else than asked."""
    if _selected(payload, "Season") != season_alias(start):
        raise ValueError(
            f"asked for season {season_alias(start)}, got {_selected(payload, 'Season')}"
        )
    if _selected(payload, "Phase") != phase:
        raise ValueError(f"asked for phase {phase}, got {_selected(payload, 'Phase')}")
    if foreign and _selected(payload, "foreigner") != "1":
        raise ValueError("licence filter not applied")


def clock_to_s(text: str | None) -> int | None:
    parts = (text or "").strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    return int(parts[0]) * 60 + int(parts[1])


def _int(v: Any) -> int | None:
    t = str(v).strip() if v is not None else ""
    return int(t) if re.fullmatch(r"-?\d+", t) else None


def _names(raw: str) -> dict[str, Any]:
    tokens = raw.split()
    full = " ".join(tokens[-1:] + tokens[:-1]) if len(tokens) > 1 else raw
    folded = fold_name(raw) or ""
    return {
        "name_raw": raw,
        "full_name": full,
        "name_key": fold_name(full),
        "name_tokens": " ".join(sorted(folded.split())),
    }


def parse_rows(payload: dict[str, Any], kind: str) -> pd.DataFrame:
    """One API response -> one row per player and team (kind: 'skaters' or 'goalies')."""
    head = [h["alias"] for h in payload["header"]]
    need = {"player", "team", "gamesPlayed"} | (
        {"position", "goals", "assists", "points", "pimTotal", "plusMinus"}
        if kind == "skaters"
        else {"firstKeeper", "goalsAgainst", "shotsAgainst", "saves", "secondsPlayed"}
    )
    if missing := need - set(head):
        raise ValueError(f"NL {kind} header changed, missing {sorted(missing)}: {head}")
    i = {a: n for n, a in enumerate(head)}
    rows = []
    for r in payload["data"]:
        if len(r) < len(head):
            continue  # the empty-result marker, [["Keine Spieler gefunden!"]]
        team = r[i["team"]] or {}
        row = {
            **_names(str(r[i["player"]]).strip()),
            "team_id": team.get("id"),
            "team": team.get("name"),
        }
        row["games_played"] = _int(r[i["gamesPlayed"]])
        if kind == "skaters":
            row.update(
                position=POSITION.get(r[i["position"]]),
                goals=_int(r[i["goals"]]),
                assists=_int(r[i["assists"]]),
                points=_int(r[i["points"]]),
                pim=_int(r[i["pimTotal"]]),
                plus_minus=_int(r[i["plusMinus"]]),
            )
        else:
            row.update(
                position="G",
                games_started=_int(r[i["firstKeeper"]]),
                toi_s=clock_to_s(r[i["secondsPlayed"]]),
                goals_against=_int(r[i["goalsAgainst"]]),
                shots_against=_int(r[i["shotsAgainst"]]),
                saves=_int(r[i["saves"]]),
                pim=_int(r[i["penaltyInMinutes"]]) if "penaltyInMinutes" in i else None,
                goals=_int(r[i["goals"]]) if "goals" in i else None,
                assists=_int(r[i["assists"]]) if "assists" in i else None,
            )
        rows.append(row)
    return pd.DataFrame(rows)


def build_season(
    everyone: dict[str, Any], foreign: dict[str, Any] | None, kind: str, start: int, phase: str
) -> pd.DataFrame:
    """Join a season's full list with its foreign-licence list on name and team.

    With no foreign-licence list (goalies, see the module docstring) the licence is unknown.
    """
    df = parse_rows(everyone, kind)
    if df.duplicated(["name_raw", "team_id"]).any():
        raise ValueError(f"NL {kind} {start}: duplicated player and team")
    if foreign is None:
        df["licence"] = None
    else:
        fo = parse_rows(foreign, kind).reindex(columns=["name_raw", "team_id"]).drop_duplicates()
        marked = df.merge(
            fo.assign(_f=True), on=["name_raw", "team_id"], how="left", validate="one_to_one"
        )
        is_foreign = marked["_f"].eq(True).to_numpy()
        unmatched = len(fo) - int(is_foreign.sum())
        if unmatched:
            raise ValueError(
                f"NL {kind} {start}: {unmatched} foreign-licence rows not in the full list"
            )
        df["licence"] = ["foreign" if f else "CH" for f in is_foreign]
    if kind == "goalies":
        # early seasons publish shots against and saves as 0 for everyone: unknown, not zero
        for c in ("shots_against", "saves"):
            if (df[c].fillna(0) == 0).all():
                df[c] = None
    df["season"] = season_label(start)
    df["season_start"] = start
    df["phase_id"] = phase
    columns = SKATER_COLUMNS if kind == "skaters" else GOALIE_COLUMNS
    return df[columns]


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    strings = {
        "season",
        "phase_id",
        "name_raw",
        "full_name",
        "name_key",
        "name_tokens",
        "team",
        "position",
        "licence",
    }
    for c in df.columns:
        if c in strings:
            df[c] = df[c].astype("string")
        else:
            df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
    return df.sort_values(["season_start", "team", "name_raw"], kind="stable").reset_index(
        drop=True
    )


def fetch_season(client: PoliteClient, start: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    tag = season_alias(start)
    probe = client.get_json(URL, f"{tag}_phases.json", params=params("player", start))
    phase = regular_phase(probe)
    payloads = {}
    for alias, foreign in (("player", False), ("player", True), ("goalkeeper", False)):
        key = f"{tag}_{phase}_{alias}{'_foreign' if foreign else ''}.json"
        p = client.get_json(URL, key, params=params(alias, start, phase, foreign))
        check_response(p, start, phase, foreign)
        payloads[alias, foreign] = p
    skaters = build_season(
        payloads["player", False], payloads["player", True], "skaters", start, phase
    )
    goalies = build_season(payloads["goalkeeper", False], None, "goalies", start, phase)
    return skaters, goalies


def coverage(skaters: pd.DataFrame, goalies: pd.DataFrame) -> dict[str, Any]:
    per_season = []
    for start in sorted(set(skaters["season_start"])):
        sk = skaters[skaters["season_start"] == start]
        go = goalies[goalies["season_start"] == start]
        pl = pd.concat([sk, go], ignore_index=True)
        per_season.append(
            {
                "season": season_label(int(start)),
                "phase_id": str(sk["phase_id"].iloc[0]),
                "skaters": int(len(sk)),
                "goalies": int(len(go)),
                "teams": int(pl["team_id"].nunique()),
                "foreign_licence": int((pl["licence"] == "foreign").sum()),
                "max_games": int(pl["games_played"].max()),
            }
        )
    return {
        "source": "data.sihf.ch Statistic API (cache300), National League, regular season",
        "nationality_basis": "licence only: Swiss or foreign licence (eligibility, not citizenship); skaters only, goalies unknown",
        "birth_date": "not published by the source",
        "player_id": "not published by the source; players are keyed by name and team",
        "time_on_ice": "goalies only (time played); skaters have none",
        "seasons": per_season,
    }


def run(
    first: int = FIRST_SEASON, last: int = LAST_SEASON, client: PoliteClient | None = None
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    sks, gos = [], []
    for start in range(first, last + 1):
        sk, go = fetch_season(client, start)
        LOG.info("NL %s: %d skaters, %d goalies", season_label(start), len(sk), len(go))
        sks.append(sk)
        gos.append(go)
    skaters, goalies = (
        _coerce(pd.concat(sks, ignore_index=True)),
        _coerce(pd.concat(gos, ignore_index=True)),
    )

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    paths = [config.PROCESSED_DIR / OUT_SKATERS, config.PROCESSED_DIR / OUT_GOALIES]
    skaters.to_parquet(paths[0], index=False)
    goalies.to_parquet(paths[1], index=False)
    cov = config.PROCESSED_DIR / OUT_COVERAGE
    cov.write_text(
        json.dumps(coverage(skaters, goalies), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths.append(cov)
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
