"""DEL (Germany) regular-season player tables, 1995/96-2025/26, from penny-del.org HTML.

penny-del.org has no robots.txt (404) and no published terms for its statistics
pages. Two page families, one per era:

- Current statistics, 2022/23 onward:
  /statistik/saison-YYYY-YY/hauptrunde/playerstats/basis   (Nat, POS, GP, G, A, P, PIM, +/-)
  /statistik/saison-YYYY-YY/hauptrunde/playerstats/toi     (TOI total, shifts)
  /statistik/saison-YYYY-YY/hauptrunde/goaliestats/basis   (Nat, GP, minutes, W, L, SO, GA, SV)
  /statistik/saison-YYYY-YY/hauptrunde/tabelle              (standings: team logo -> name)
  The statistics tables show the team only as a logo; the standings page names it.
- The archive, 1994/95-2024/25:
  /statistik/archiv/saison_YYYY-YYYY_hauptrunde/topscorer   (every skater: team, Pos, GP, G, A, P)
  /statistik/archiv/saison_YYYY-YYYY_hauptrunde/topgoalies  (every goalie: team, GP, minutes)
  No nationality; the archive's time-on-ice columns are all zero, so TOI is not kept.

The archive is used for 1995/96-2021/22 and the current pages from 2022/23. One
request per page: 2 per archive season (plus 4 for the split 1996/97 and 1997/98
seasons, whose Meisterrunde and Qualifikationsrunde are kept as their own
`phase`), 4 per current season.

Nationality is DEL "Nat", which is the player's licence (sporting) nationality,
not citizenship: spec §4 treats it as eligibility. It is kept raw (`nat_raw`)
and mapped to ISO alpha-3 (`nationality`, GER -> DEU). No page gives a birth
date (profiles show age and birthplace only), so DEL rows link to other sources
by name and season, not by birth date. Players are keyed by the site's numeric
id; the archive and the current pages use different id schemes (`id_scheme`).

Writes data/processed/del_skaters.parquet, del_goalies.parquet and
del_coverage.json, then publishes them to data/snapshot/.

    python -m src.fetch.del_ [--first 1995] [--last 2025]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup, Tag

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.fetch._names import fold_name, iso3_from_code
from src.logging_setup import setup as logging_setup
from src.nations import ISO3

LOG = logging.getLogger(__name__)

BASE = "https://www.penny-del.org"
FIRST_SEASON = 1995  # 1995/96
LAST_SEASON = 2025  # 2025/26
CURRENT_FROM = 2022  # 2022/23: Nat and TOI
# 1996/97 and 1997/98 split the regular season: a first round (Hauptrunde, 30
# games) then a Meisterrunde for the top clubs and a Qualifikationsrunde for the
# rest. Both second rounds are regular-season games, kept as their own phase.
EXTRA_PHASES: dict[int, tuple[str, ...]] = {
    1996: ("meisterrunde", "qualifikationsrunde"),
    1997: ("meisterrunde", "qualifikationsrunde"),
}
TEAM_RE = re.compile(r"team_(\d+)[_.]")

RAW_DIR = config.RAW_DIR / "del"
OUT_SKATERS = "del_skaters.parquet"
OUT_GOALIES = "del_goalies.parquet"
OUT_COVERAGE = "del_coverage.json"

POSITION = {"S": "F", "V": "D", "T": "G", "Stürmer": "F", "Verteidiger": "D", "Torhüter": "G"}

SKATER_COLUMNS = [
    "season",
    "season_start",
    "phase",
    "source",
    "id_scheme",
    "player_id",
    "full_name",
    "last_name",
    "name_key",
    "team",
    "position",
    "nat_raw",
    "nationality",
    "games_played",
    "goals",
    "assists",
    "points",
    "pim",
    "plus_minus",
    "toi_s",
    "toi_per_game_s",
    "shifts",
]
GOALIE_COLUMNS = [
    "season",
    "season_start",
    "phase",
    "source",
    "id_scheme",
    "player_id",
    "full_name",
    "last_name",
    "name_key",
    "team",
    "position",
    "nat_raw",
    "nationality",
    "games_played",
    "toi_s",
    "wins",
    "losses",
    "shutouts",
    "goals_against",
    "saves",
]


def season_label(start: int) -> str:
    return f"{start}/{str(start + 1)[-2:]}"


def current_url(start: int, page: str) -> str:
    """page: 'playerstats/basis', 'playerstats/toi', 'goaliestats/basis' or 'tabelle'."""
    return f"{BASE}/statistik/saison-{start}-{str(start + 1)[-2:]}/hauptrunde/{page}"


def archive_url(start: int, page: str, phase: str = "hauptrunde") -> str:
    """page: 'topscorer' or 'topgoalies'."""
    return f"{BASE}/statistik/archiv/saison_{start}-{start + 1}_{phase}/{page}"


# -- parsing helpers ------------------------------------------------------------


def _int(text: str | None) -> int | None:
    t = (text or "").strip().replace(".", "")
    return int(t) if re.fullmatch(r"-?\d+", t) else None


def clock_to_s(text: str | None) -> int | None:
    """'2448:39' -> 146919; '21:23:48' -> 77028 (h:m:s); '' -> None."""
    parts = (text or "").strip().split(":")
    if not all(p.isdigit() for p in parts) or len(parts) not in (2, 3):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs


def _header(table: Tag) -> list[str]:
    first = table.find("tr")
    return [c.get_text(" ", strip=True) for c in first.find_all(["th", "td"])]


def _rows(table: Tag) -> list[list[Tag]]:
    return [tr.find_all("td") for tr in table.find_all("tr")[1:] if tr.find_all("td")]


def _stats_table(html: str) -> Tag:
    tables = BeautifulSoup(html, "lxml").find_all("table")
    if len(tables) != 1:
        raise ValueError(f"expected one statistics table, found {len(tables)}")
    return tables[0]


def team_names(html: str) -> dict[str, str]:
    """Team key ('team_11') -> name, from every logo <img> with alt text on the page.

    Logos are .../teams/2023/team_11.svg or .../csm_team_62_<hash>.png.
    """
    out: dict[str, str] = {}
    for img in BeautifulSoup(html, "lxml").find_all("img", src=TEAM_RE):
        alt = (img.get("alt") or "").strip()
        if alt:
            out.setdefault(f"team_{TEAM_RE.search(img['src']).group(1)}", alt)
    return out


# -- current pages (2022/23 on) --------------------------------------------------

CURRENT_ID_RE = re.compile(r"/statistik/spielerdetails/[^/]+/(?:[^/]*-)?(\d+)/")


def _current_player(cell: Tag) -> dict[str, Any]:
    a = cell.find("a", href=True)
    m = CURRENT_ID_RE.search(a["href"]) if a else None
    if m is None:
        raise ValueError(f"no player link in {cell}")
    last_first = a.get_text(" ", strip=True)  # "Ronning, Ty"
    last, _, first = (p.strip() for p in last_first.partition(","))
    return {
        "player_id": int(m.group(1)),
        "full_name": f"{first} {last}".strip(),
        "last_name": last,
    }


def _current_team(cell: Tag) -> str | None:
    """The logo's team key ('team_3'); resolved to a name by `team_names` later."""
    img = cell.find("img", src=True)
    m = TEAM_RE.search(img["src"]) if img else None
    return f"team_{m.group(1)}" if m else None


def parse_current(html: str, kind: str) -> pd.DataFrame:
    """One current-era page -> one row per player (kind: 'basis', 'toi' or 'goalies')."""
    table = _stats_table(html)
    head = _header(table)
    expected = {
        "basis": ["#", "Team", "#", "Spieler", "Nat", "POS", "GP", "G", "A", "P", "PIM"],
        "toi": ["#", "Team", "#", "Spieler", "Nat", "POS", "TOI", "Shifts"],
        "goalies": [
            "#",
            "Team",
            "#",
            "Spieler",
            "Nat",
            "POS",
            "GP",
            "Min.",
            "S",
            "N",
            "SO",
            "GT",
            "GTS",
            "SV",
        ],
    }[kind]
    if head[: len(expected)] != expected:
        raise ValueError(f"DEL {kind} header changed: {head}")
    idx = {h: i for i, h in reversed(list(enumerate(head)))}  # first occurrence wins
    rows = []
    for cells in _rows(table):
        text = [c.get_text(" ", strip=True) for c in cells]
        row = _current_player(cells[3])
        row["team"] = _current_team(cells[1])
        row["nat_raw"] = text[4] or None
        row["position"] = POSITION.get(text[5])
        if kind == "basis":
            row.update(
                games_played=_int(text[idx["GP"]]),
                goals=_int(text[idx["G"]]),
                assists=_int(text[idx["A"]]),
                points=_int(text[idx["P"]]),
                pim=_int(text[idx["PIM"]]),
                plus_minus=_int(text[idx["+/-"]]) if "+/-" in idx else None,
            )
        elif kind == "toi":
            order = cells[idx["TOI"]].get("data-order")
            row.update(
                toi_s=int(order) if order and order.isdigit() else clock_to_s(text[idx["TOI"]]),
                shifts=_int(text[idx["Shifts"]]),
            )
        else:
            row.update(
                games_played=_int(text[idx["GP"]]),
                toi_s=clock_to_s(text[idx["Min."]]),
                wins=_int(text[idx["S"]]),
                losses=_int(text[idx["N"]]),
                shutouts=_int(text[idx["SO"]]),
                goals_against=_int(text[idx["GT"]]),
                saves=_int(text[idx["SV"]]),
            )
        rows.append(row)
    return pd.DataFrame(rows)


# -- archive pages (to 2021/22) -------------------------------------------------

ARCHIVE_ID_RE = re.compile(r"/statistik/archiv/portrait/(\d+)")
NUMBER_RE = re.compile(r"\s*\(#\d*\)\s*$")


def _archive_player(cell: Tag) -> dict[str, Any]:
    a = cell.find("a", href=True)
    m = ARCHIVE_ID_RE.search(a["href"]) if a else None
    if m is None:
        raise ValueError(f"no archive player link in {cell}")
    return {
        "player_id": int(m.group(1)),
        "full_name": NUMBER_RE.sub("", a.get_text(" ", strip=True)),
    }


def _archive_team(cell: Tag) -> str | None:
    img = cell.find("img")
    name = (img.get("title") or img.get("alt") or "").strip() if img else ""
    return name or cell.get_text(" ", strip=True) or None


def parse_archive(html: str, kind: str) -> pd.DataFrame:
    """One archive page -> one row per player and team (kind: 'skaters' or 'goalies')."""
    table = _stats_table(html)
    head = _header(table)
    expected = {
        "skaters": ["#", "Spieler", "Team", "Pos", "Sp.", "T", "A", "GP"],
        "goalies": ["#", "Spieler", "Team", "Sp.", "Min.", "S", "U", "N", "SO", "GT"],
    }[kind]
    if head[: len(expected)] != expected:
        raise ValueError(f"DEL archive {kind} header changed: {head}")
    idx = {h: i for i, h in enumerate(head)}
    rows = []
    for cells in _rows(table):
        text = [c.get_text(" ", strip=True) for c in cells]
        row = _archive_player(cells[idx["Spieler"]])
        row["team"] = _archive_team(cells[idx["Team"]])
        if kind == "skaters":
            # In the archive "GP" is points (Gesamtpunkte) and "Sp." games (Spiele).
            row.update(
                position=POSITION.get(text[idx["Pos"]]),
                games_played=_int(text[idx["Sp."]]),
                goals=_int(text[idx["T"]]),
                assists=_int(text[idx["A"]]),
                points=_int(text[idx["GP"]]),
                pim=_int(text[idx["Str."]]) if "Str." in idx else None,
                plus_minus=None,
            )
        else:
            # The archive's other goalie columns (W, L, SO, GA, SV) are
            # zero-filled in early seasons, so only games and minutes are kept.
            row.update(
                position="G",
                games_played=_int(text[idx["Sp."]]),
                toi_s=clock_to_s(text[idx["Min."]]),
            )
        rows.append(row)
    return pd.DataFrame(rows)


# -- building ---------------------------------------------------------------------


def _finish(
    df: pd.DataFrame, start: int, source: str, columns: list[str], phase: str = "hauptrunde"
) -> pd.DataFrame:
    df = df.copy()
    df["season"] = season_label(start)
    df["season_start"] = start
    df["phase"] = phase
    df["source"] = source
    df["id_scheme"] = "current" if source == "current" else "archive"
    df["name_key"] = df["full_name"].map(fold_name)
    if "nat_raw" not in df:
        df["nat_raw"] = None
    df["nationality"] = df["nat_raw"].map(iso3_from_code)
    for c in columns:
        if c not in df:
            df[c] = None
    return df[columns]


def build_current_season(
    basis: str, toi: str, goalies: str, start: int, standings: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame]:
    b = parse_current(basis, "basis")
    t = parse_current(toi, "toi")[["player_id", "toi_s", "shifts"]]
    for name, df in (("basis", b), ("toi", t)):
        if df["player_id"].duplicated().any():
            raise ValueError(f"DEL {start} {name}: duplicated player ids")
    sk = b.merge(t, on="player_id", how="left", validate="one_to_one")
    sk["toi_per_game_s"] = sk["toi_s"] / sk["games_played"].where(sk["games_played"] > 0)
    go = parse_current(goalies, "goalies")
    # The statistics tables show logos without names; the standings page names
    # every team, and the other pages name those that appear in their scoreboard.
    teams = {**team_names(goalies), **team_names(toi), **team_names(basis), **team_names(standings)}
    for df in (sk, go):
        unknown = set(df["team"].dropna()) - set(teams)
        if unknown:
            raise ValueError(f"DEL {start}: no team name for {sorted(unknown)}")
        df["team"] = df["team"].map(teams)
    # the skater pages list goalies too (POS T) with empty stats; the goalie page is theirs
    sk = sk[sk["position"] != "G"]
    return _finish(sk, start, "current", SKATER_COLUMNS), _finish(
        go, start, "current", GOALIE_COLUMNS
    )


def build_archive_season(
    skaters: str, goalies: str, start: int, phase: str = "hauptrunde"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    sk = parse_archive(skaters, "skaters")
    go = parse_archive(goalies, "goalies")
    sk = sk[sk["position"] != "G"]
    return _finish(sk, start, "archive", SKATER_COLUMNS, phase), _finish(
        go, start, "archive", GOALIE_COLUMNS, phase
    )


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    strings = [
        "season",
        "phase",
        "source",
        "id_scheme",
        "full_name",
        "last_name",
        "name_key",
        "team",
        "position",
        "nat_raw",
        "nationality",
    ]
    for c in df.columns:
        if c in strings:
            df[c] = df[c].astype("string")
        elif c == "toi_per_game_s":
            df[c] = pd.to_numeric(df[c]).astype("float64")
        else:
            df[c] = pd.array(pd.to_numeric(df[c]), dtype="Int64")
    return df.sort_values(
        ["season_start", "phase", "team", "player_id"], kind="stable"
    ).reset_index(drop=True)


def fetch_season(client: PoliteClient, start: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    tag = f"{start}-{start + 1}"
    if start >= CURRENT_FROM:
        pages = {
            p: client.get_text(current_url(start, p), f"current_{tag}_{p.replace('/', '_')}.html")
            for p in ("playerstats/basis", "playerstats/toi", "goaliestats/basis", "tabelle")
        }
        return build_current_season(
            pages["playerstats/basis"],
            pages["playerstats/toi"],
            pages["goaliestats/basis"],
            start,
            pages["tabelle"],
        )
    sks, gos = [], []
    for phase in ("hauptrunde", *EXTRA_PHASES.get(start, ())):
        name = "" if phase == "hauptrunde" else f"{phase}_"
        pages = {
            p: client.get_text(archive_url(start, p, phase), f"archive_{tag}_{name}{p}.html")
            for p in ("topscorer", "topgoalies")
        }
        sk, go = build_archive_season(pages["topscorer"], pages["topgoalies"], start, phase)
        sks.append(sk)
        gos.append(go)
    return pd.concat(sks, ignore_index=True), pd.concat(gos, ignore_index=True)


def coverage(skaters: pd.DataFrame, goalies: pd.DataFrame) -> dict[str, Any]:
    per_season = []
    for start in sorted(set(skaters["season_start"]) | set(goalies["season_start"])):
        sk = skaters[skaters["season_start"] == start]
        go = goalies[goalies["season_start"] == start]
        pl = pd.concat([sk, go], ignore_index=True)
        per_season.append(
            {
                "season": season_label(int(start)),
                "source": str(sk["source"].iloc[0]) if len(sk) else None,
                "phases": sorted(set(sk["phase"])),
                "skaters": int(len(sk)),
                "goalies": int(len(go)),
                "teams": int(pl["team"].nunique()),
                "nationality_share": round(float(pl["nationality"].notna().mean()), 4),
                "skater_toi_share": round(float(sk["toi_s"].notna().mean()), 4)
                if len(sk)
                else None,
                "nations": {iso: int((pl["nationality"] == iso).sum()) for iso in ISO3},
            }
        )
    return {
        "source": "penny-del.org statistics pages (HTML), regular season (Hauptrunde)",
        "nationality_basis": "DEL 'Nat' = licence (sporting) nationality, 2022/23 onward only",
        "birth_date": "not published by the source",
        "seasons": per_season,
    }


def run(
    first: int = FIRST_SEASON, last: int = LAST_SEASON, client: PoliteClient | None = None
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    sks, gos = [], []
    for start in range(first, last + 1):
        sk, go = fetch_season(client, start)
        LOG.info("DEL %s: %d skaters, %d goalies", season_label(start), len(sk), len(go))
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
