"""SHL (Sweden) regular-season player tables, 1995/96-2025/26, from shl.se statistics-v2 JSON.

shl.se serves its single-page app for /robots.txt (no robots rules) and no
terms page was found. Endpoints:

- /api/statistics-v2/layout-info?statisticsType=player: every season/series/game
  type ("ssgt") the site knows; the SHL regular season of each season code
  (code = start year, 2024 = 2024/25) gives the `ssgtUuid` for the rest.
- /api/statistics-v2/stats-info/players_summary?ssgtUuid=...&count=1000:
  every player of the season, one row each (goalkeepers included, with games
  only; a skater listed with no game is dropped): GP, G, A, TP, PIM, +/-, TOI_GP, and an `info` record (uuid, name,
  birth date, nationality as ISO alpha-2, position).
- .../players_timeOnIce: total time on ice (TOI) per skater, from 2009/10.
- .../goalkeepers_summary: goalkeepers (GPI, minutes, saves, GA, W/T/L, SO).

Gaps, measured on the fetched data and reported in shl_coverage.json:

- Before about 2010 most players carry no uuid, no birth date and nationality
  "N/A". The response's `players` map gives those players a legacy numeric id
  (joined on first + last name when that is unique within the season) but no
  personal data either.
- Nationality is "N/A" for some players who do have a uuid; it is back-filled
  from the same uuid's other seasons (spec §4), as are birth date and position.
  `nationality_source` says which value came from where. In practice the site
  holds one record per uuid, so the back-fill rarely finds a value the season
  lacked; the uuid-less rows before 2010 cannot be back-filled at all.
- Position is missing for many rows in every season. After the back-fill the
  rest stays missing here; linking to other leagues can fill it later.
- goalkeepers_summary is empty in the earliest seasons; there the goalie table
  falls back to players_summary's goalkeeper rows (games only,
  `source = "players_summary"`).

Nationality is mapped to ISO alpha-3. Only public statistics fields are kept:
names, birth date, nationality, position and statistics.

Writes data/processed/shl_skaters.parquet, shl_goalies.parquet and
shl_coverage.json, then publishes them to data/snapshot/.

    python -m src.fetch.shl [--first 1995] [--last 2025]
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.fetch._names import fold_name
from src.logging_setup import setup as logging_setup
from src.nations import ISO3

LOG = logging.getLogger(__name__)

BASE = "https://www.shl.se/api/statistics-v2"
LAYOUT_URL = f"{BASE}/layout-info?statisticsType=player"
FIRST_SEASON = 1995  # 1995/96
LAST_SEASON = 2025  # 2025/26
TOI_FROM = 2009  # 2009/10, the first season with time on ice
PAGE_SIZE = 1000

RAW_DIR = config.RAW_DIR / "shl"
OUT_SKATERS = "shl_skaters.parquet"
OUT_GOALIES = "shl_goalies.parquet"
OUT_COVERAGE = "shl_coverage.json"

MISSING = {"", "N/A", "-", "NA"}

POSITION = {
    "F": "F",
    "CE": "F",
    "C": "F",
    "LW": "F",
    "RW": "F",
    "D": "D",
    "LD": "D",
    "RD": "D",
    "G": "G",
    "GK": "G",
}

# SHL nationality is ISO 3166 alpha-2.
ISO2_TO_ISO3: dict[str, str] = {
    "AT": "AUT",
    "AU": "AUS",
    "BE": "BEL",
    "BG": "BGR",
    "BY": "BLR",
    "CA": "CAN",
    "CH": "CHE",
    "CN": "CHN",
    "CZ": "CZE",
    "DE": "DEU",
    "DK": "DNK",
    "EE": "EST",
    "ES": "ESP",
    "FI": "FIN",
    "FR": "FRA",
    "GB": "GBR",
    "HR": "HRV",
    "HU": "HUN",
    "IE": "IRL",
    "IS": "ISL",
    "IT": "ITA",
    "JP": "JPN",
    "KR": "KOR",
    "KZ": "KAZ",
    "LT": "LTU",
    "LV": "LVA",
    "NL": "NLD",
    "NO": "NOR",
    "NZ": "NZL",
    "PL": "POL",
    "RO": "ROU",
    "RS": "SRB",
    "RU": "RUS",
    "SE": "SWE",
    "SI": "SVN",
    "SK": "SVK",
    "UA": "UKR",
    "US": "USA",
    "ZA": "ZAF",
}

COMMON_COLUMNS = [
    "season",
    "season_start",
    "player_id",
    "legacy_id",
    "full_name",
    "first_name",
    "last_name",
    "name_key",
    "birth_date",
    "birth_date_source",
    "nat_raw",
    "nationality",
    "nationality_source",
    "team",
    "team_code",
    "position",
    "position_raw",
    "position_source",
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
    "source",
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
    "legacy_id",
    "games_played",
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


def season_label(start: int) -> str:
    """1995 -> '1995/96'."""
    return f"{start}/{str(start + 1)[-2:]}"


def seasons(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list[int]:
    return list(range(first, last + 1))


def clock_to_s(text: Any) -> int | None:
    """'19:02' -> 1142 (m:s); '21:26:54' -> 77214 (h:m:s); None or '' -> None."""
    if text is None:
        return None
    parts = str(text).strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs


def _clean(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.upper() in MISSING else s


def iso3(code: Any) -> str | None:
    c = _clean(code)
    return ISO2_TO_ISO3.get(c.upper()) if c else None


# -- fetching -----------------------------------------------------------------


def regular_ssgts(layout: list[dict[str, Any]]) -> dict[int, str]:
    """Season start year -> ssgtUuid of the SHL regular season."""
    out: dict[int, str] = {}
    for block in layout:
        for key in ("seasonSeriesGameTypeTeams", "originalSeasonSeriesGameTypeTeams"):
            for s in block.get(key) or []:
                if (s.get("series") or {}).get("code") != "SHL":
                    continue
                if (s.get("gameType") or {}).get("code") != "regular":
                    continue
                code = (s.get("season") or {}).get("code")
                if code and str(code).isdigit() and s.get("ssgtUuid"):
                    out.setdefault(int(code), s["ssgtUuid"])
    return out


def stats_url(subset: str, ssgt: str) -> str:
    return f"{BASE}/stats-info/{subset}?ssgtUuid={ssgt}&count={PAGE_SIZE}"


def _stats(client: PoliteClient, subset: str, ssgt: str, start: int) -> dict[str, Any]:
    payload = client.get_json(stats_url(subset, ssgt), f"{subset}_{start}.json")
    block = payload[0] if payload else {"stats": [], "players": {}, "totalCount": 0}
    n, total = len(block.get("stats") or []), block.get("totalCount")
    if total is not None and n != total:
        raise ValueError(f"shl {subset} {start}: totalCount={total} but {n} rows")
    return block


def fetch_season(client: PoliteClient, ssgt: str, start: int) -> dict[str, dict[str, Any]]:
    out = {
        "summary": _stats(client, "players_summary", ssgt, start),
        "goalies": _stats(client, "goalkeepers_summary", ssgt, start),
    }
    if start >= TOI_FROM:
        out["toi"] = _stats(client, "players_timeOnIce", ssgt, start)
    return out


# -- parsing ------------------------------------------------------------------


def _name_key(first: Any, last: Any) -> tuple[str, str]:
    return ((first or "").strip().lower(), (last or "").strip().lower())


def legacy_index(players: dict[str, dict[str, Any]]) -> dict[tuple[str, str], int | None]:
    """(first, last) lower-cased -> legacy numeric id; None when the name is not unique."""
    count = Counter(_name_key(p.get("firstName"), p.get("lastName")) for p in players.values())
    out: dict[tuple[str, str], int | None] = {}
    for p in players.values():
        k = _name_key(p.get("firstName"), p.get("lastName"))
        out[k] = int(p["id"]) if count[k] == 1 and p.get("id") is not None else None
    return out


def _row_key(r: dict[str, Any]) -> tuple[Any, ...]:
    """Join key between two stats subsets of the same season."""
    info = r.get("info") or {}
    if info.get("uuid"):
        return ("uuid", info["uuid"])
    return ("name", info.get("fullName"), info.get("teamCode"), r.get("GP"))


def _common(
    r: dict[str, Any], start: int, legacy: dict[tuple[str, str], int | None]
) -> dict[str, Any]:
    info = r.get("info") or {}
    first, last = _clean(info.get("firstName")), _clean(info.get("lastName"))
    full = _clean(info.get("fullName")) or " ".join(p for p in (first, last) if p)
    nat_raw = _clean(info.get("nationality"))
    birth = _clean(info.get("birthDate"))
    pos_raw = _clean(info.get("position"))
    pos = POSITION.get(pos_raw.upper()) if pos_raw else None
    team = info.get("team") or {}
    return {
        "season": season_label(start),
        "season_start": start,
        "player_id": _clean(info.get("uuid")),
        "legacy_id": legacy.get(_name_key(first, last)),
        "full_name": full,
        "first_name": first,
        "last_name": last,
        "name_key": fold_name(full),
        "birth_date": birth,
        "birth_date_source": "season" if birth else None,
        "nat_raw": nat_raw,
        "nationality": iso3(nat_raw),
        "nationality_source": "season" if iso3(nat_raw) else None,
        "team": team.get("name") or team.get("siteDisplayName"),
        "team_code": _clean(info.get("teamCode")) or _clean(team.get("code")),
        "position": pos,
        "position_raw": pos_raw,
        "position_source": "season" if pos else None,
    }


def build_season(
    payload: dict[str, dict[str, Any]], start: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary, gk = payload["summary"], payload["goalies"]
    legacy = legacy_index({**(summary.get("players") or {}), **(gk.get("players") or {})})
    toi_total = {
        _row_key(r): clock_to_s(r.get("TOI")) for r in (payload.get("toi") or {}).get("stats") or []
    }

    goalie_rows = gk.get("stats") or []
    goalie_keys = {_row_key(r) for r in goalie_rows}
    goalie_names = {
        ((r.get("info") or {}).get("fullName"), (r.get("info") or {}).get("teamCode"))
        for r in goalie_rows
    }

    skaters, fallback_goalies = [], []
    for r in summary.get("stats") or []:
        rec = _common(r, start, legacy)
        info = r.get("info") or {}
        is_goalie = (
            rec["position"] == "G"
            or _row_key(r) in goalie_keys
            or (info.get("fullName"), info.get("teamCode")) in goalie_names
        )
        if is_goalie:
            rec["position"], rec["position_source"] = "G", rec["position_source"] or "goalie_table"
            fallback_goalies.append(
                {**rec, "source": "players_summary", "games_played": r.get("GP")}
            )
            continue
        gp = r.get("GP")
        if not gp:  # listed without a game played
            continue
        per_game = clock_to_s(r.get("TOI_GP")) if start >= TOI_FROM else None
        total = toi_total.get(_row_key(r)) if start >= TOI_FROM else None
        rec.update(
            {
                "games_played": gp,
                "goals": r.get("G"),
                "assists": r.get("A"),
                "points": r.get("TP"),
                "plus_minus": r.get("PlusMinus"),
                "pim": r.get("PIM"),
                "toi_s": total,
                "toi_per_game_s": total / gp if total is not None and gp else per_game,
            }
        )
        skaters.append(rec)

    goalies = []
    for r in goalie_rows:
        rec = _common(r, start, legacy)
        rec["position"] = "G"
        rec["position_source"] = rec["position_source"] or "goalie_table"
        rec.update(
            {
                "source": "goalkeepers_summary",
                "games_played": r.get("GPI"),
                "toi_s": clock_to_s(r.get("MIP")),
                "wins": r.get("W"),
                "losses": r.get("L"),
                "ties": r.get("T"),
                "goals_against": r.get("GA"),
                "saves": r.get("SVS"),
                "save_pct": _float(r.get("SVSPerc")),
                "gaa": _float(r.get("GAA")),
                "shutouts": r.get("SO"),
            }
        )
        goalies.append(rec)
    if not goalies:
        goalies = fallback_goalies
    return (
        pd.DataFrame(skaters, columns=SKATER_COLUMNS),
        pd.DataFrame(goalies, columns=GOALIE_COLUMNS),
    )


def _float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def backfill(skaters: pd.DataFrame, goalies: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fill nationality, birth date and position from the same uuid's other seasons.

    The most frequent known value wins (ties: the latest season's). Filled cells
    get `<field>_source = "backfill"`. Position is back-filled among skaters only.
    """
    both = pd.concat([skaters, goalies], ignore_index=True)
    both = both[both["player_id"].notna()].sort_values("season_start")

    def mode(col: str, frame: pd.DataFrame) -> dict[str, Any]:
        known = frame[frame[col].notna()]
        out = {}
        for pid, vals in known.groupby("player_id")[col]:
            c = Counter(vals.tolist()[::-1])  # latest first, so ties go to the latest
            out[pid] = c.most_common(1)[0][0]
        return out

    fills = {
        "nationality": mode("nationality", both),
        "birth_date": mode("birth_date", both),
    }
    pos = mode("position", skaters[skaters["player_id"].notna()])

    def apply(df: pd.DataFrame, cols: dict[str, dict[str, Any]]) -> pd.DataFrame:
        df = df.copy()
        for col, table in cols.items():
            need = df[col].isna() & df["player_id"].notna() & df["player_id"].isin(table.keys())
            df.loc[need, col] = df.loc[need, "player_id"].map(table)
            df.loc[need, f"{col}_source"] = "backfill"
        return df

    return apply(skaters, {**fills, "position": pos}), apply(goalies, fills)


def coerce(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if c in INT_COLUMNS:
            df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
        elif c in FLOAT_COLUMNS:
            df[c] = pd.to_numeric(df[c]).astype("float64")
        else:
            df[c] = df[c].astype("string")
    return df.sort_values(
        ["season_start", "team_code", "full_name"], kind="stable", na_position="last"
    ).reset_index(drop=True)


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
                "goalie_source": sorted(set(go["source"].dropna())),
                "uuid_share": _share(pl["player_id"].notna()),
                "birth_date_share": _share(pl["birth_date"].notna()),
                "nationality_share": _share(pl["nationality"].notna()),
                "nationality_backfilled": int((pl["nationality_source"] == "backfill").sum()),
                "skater_position_share": _share(sk["position"].notna()),
                "skater_toi_share": _share(sk["toi_s"].notna()),
                "goalie_toi_share": _share(go["toi_s"].notna()),
                "nations": {iso: int((pl["nationality"] == iso).sum()) for iso in ISO3},
            }
        )
    both = pd.concat([skaters, goalies], ignore_index=True)
    return {
        "source": "shl.se statistics-v2 JSON, SHL regular season",
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
    ssgts = regular_ssgts(client.get_json(LAYOUT_URL, "layout_info.json"))
    starts = seasons(first, last)
    missing = [s for s in starts if s not in ssgts]
    if missing:
        raise ValueError(f"no SHL regular-season ssgt for {missing}")
    sk_frames, go_frames = [], []
    for start in starts:
        sk, go = build_season(fetch_season(client, ssgts[start], start), start)
        LOG.info("shl %s: %d skaters, %d goalies", season_label(start), len(sk), len(go))
        sk_frames.append(sk)
        go_frames.append(go)
    skaters, goalies = backfill(
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
