"""Czech Extraliga regular-season player tables, 1995/96-2025/26, from hokej.cz HTML.

hokej.cz's robots.txt allows everything (`Allow: /`). Pages, all under
/tipsport-extraliga/player-stats/detailni (the URL keeps its old name for every
season; the league's sponsor name changes):

- ?stats-filter-season=Y (Y = start year) redirects to that season's default
  competition, usually the play-offs; the page's competition list gives the
  regular-season id, which every other request names.
- &stats-menu-section=info: every skater, one row per player (G, A, P, +/-, PIM).
- &stats-menu-section=time: time on ice, shifts, PP and SH time, from 2013/14.
- &stats-menu-section=goalkeeper: goalkeepers (minutes, GA, saves, W/L, SO).
- &stats-playerFilter-stranger=1: only foreigners (the league's licence status).
  Used as a flag, `is_foreign`; the league gives no citizenship (spec §4 treats
  the flag as eligibility). A season whose foreigner list is empty has no flag
  (`is_foreign` missing), which is the case in the earliest seasons.
- &stats-playerFilter-age=20: only under-20 players, shown with a two-digit
  birth year; kept as `is_u20` and `birth_year`.
- &stats-view-pager-all=1: the whole table on one page.
- /hrac/{slug}/{id}: the player's profile, with the birth date ("narozen").
  Fetched only for players who are needed: everyone in a season from 2013/14
  (the time-on-ice and youth window of spec §3.4), each profile once, cached.

Requests go at most one every two seconds (the site answers 503 to faster
ones). Only public statistics fields are kept: names, birth date, position,
foreigner flag and statistics. Profiles' height, weight, handedness and photos
are not kept.

Writes data/processed/extraliga_skaters.parquet, extraliga_goalies.parquet,
extraliga_profiles.parquet and extraliga_coverage.json, then publishes them to
data/snapshot/.

    python -m src.fetch.extraliga [--first 1995] [--last 2025] [--profiles-from 2013]
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
from src.fetch._names import fold_name
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

BASE = "https://www.hokej.cz"
STATS_URL = f"{BASE}/tipsport-extraliga/player-stats/detailni"
FIRST_SEASON = 1995  # 1995/96
LAST_SEASON = 2025  # 2025/26
TOI_FROM = 2013  # 2013/14, the first season with time on ice
PROFILES_FROM = 2013  # birth dates are fetched for players of 2013/14 onwards
MIN_INTERVAL_S = 2.0

RAW_DIR = config.RAW_DIR / "extraliga"
OUT_SKATERS = "extraliga_skaters.parquet"
OUT_GOALIES = "extraliga_goalies.parquet"
OUT_PROFILES = "extraliga_profiles.parquet"
OUT_COVERAGE = "extraliga_coverage.json"

POSITION = {"Ú": "F", "O": "D", "B": "G"}
# Competition labels that are not the regular season.
NOT_REGULAR = re.compile(
    r"play.?off|playoff|baráž|kvalifikace|předkolo|nadstavba|o umístění|skupina|finále|semifinále|\bcup\b|pohár|\bsk\.",
    re.I,
)

PLAYER_HREF = re.compile(r"/hrac/([^/?#]+)/(\d+)")
SHORT_YEAR = re.compile(r"\(\s*'(\d{2})\s*\)")

COMMON_COLUMNS = [
    "season",
    "season_start",
    "competition_id",
    "player_id",
    "full_name",
    "name_key",
    "profile_path",
    "birth_date",
    "birth_year",
    "team",
    "position",
    "position_raw",
    "is_u20",
    "is_foreign",
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
    "shifts",
    "pp_toi_s",
    "sh_toi_s",
]
GOALIE_COLUMNS = COMMON_COLUMNS + [
    "games_played",
    "toi_s",
    "goals_against",
    "saves",
    "shots_against",
    "wins",
    "losses",
    "gaa",
    "save_pct",
    "shutouts",
]
PROFILE_COLUMNS = ["player_id", "full_name", "profile_path", "birth_date"]

INT_COLUMNS = {
    "season_start",
    "competition_id",
    "player_id",
    "birth_year",
    "games_played",
    "goals",
    "assists",
    "points",
    "plus_minus",
    "pim",
    "toi_s",
    "shifts",
    "pp_toi_s",
    "sh_toi_s",
    "goals_against",
    "saves",
    "shots_against",
    "wins",
    "losses",
    "shutouts",
}
FLOAT_COLUMNS = {"toi_per_game_s", "gaa", "save_pct"}
BOOL_COLUMNS = {"is_u20", "is_foreign"}


def season_label(start: int) -> str:
    """1995 -> '1995/96'."""
    return f"{start}/{str(start + 1)[-2:]}"


def seasons(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list[int]:
    return list(range(first, last + 1))


# -- small parsers ----------------------------------------------------------------


def _int(text: Any) -> int | None:
    t = str(text or "").strip().replace("\xa0", "").replace(" ", "")
    return int(t) if re.fullmatch(r"[+-]?\d+", t) else None


def _float(text: Any) -> float | None:
    t = str(text or "").strip().replace(",", ".").rstrip("%")
    try:
        return float(t)
    except ValueError:
        return None


def clock_to_s(text: Any) -> int | None:
    """'1215:17' -> 72917 (m:s); '23:50' -> 1430; '' -> None."""
    parts = str(text or "").strip().split(":")
    if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
        return None
    secs = 0
    for p in parts:
        secs = secs * 60 + int(p)
    return secs


def birth_year_from_short(yy: int, season_start: int) -> int:
    """Two-digit birth year of an under-20 player in `season_start`: '06 in 2024 -> 2006."""
    year = 2000 + yy
    return year if year <= season_start else 1900 + yy


def czech_date(text: str) -> str | None:
    """'17.2.1997' -> '1997-02-17'."""
    m = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", text or "")
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


# -- page parsing -----------------------------------------------------------------


def competitions(html: str) -> list[tuple[int, str]]:
    """(id, label) of every competition in the page's competition list."""
    soup = BeautifulSoup(html, "lxml")
    sel = soup.find("select", attrs={"name": "competition"})
    if sel is None:
        return []
    out = []
    for o in sel.find_all("option"):
        v = (o.get("value") or "").strip()
        if v.isdigit():
            out.append((int(v), o.get_text(" ", strip=True)))
    return out


def regular_competition(options: list[tuple[int, str]], start: int) -> int:
    """The single competition whose label is not a play-off, relegation or qualifier round."""
    regular = [(cid, label) for cid, label in options if not NOT_REGULAR.search(label)]
    if len(regular) > 1:  # e.g. 2020/21 also lists a pre-season cup
        regular = [(cid, label) for cid, label in regular if "extralig" in label.lower()]
    if len(regular) != 1:
        raise ValueError(f"extraliga {start}: cannot pick the regular season from {options}")
    return regular[0][0]


def parse_table(html: str) -> list[dict[str, Any]]:
    """Rows of the `table-stats` table: header -> cell text, plus the player link and short year."""
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="table-stats")
    if table is None:
        return []
    header = [th.get_text(" ", strip=True) for th in table.find_all("th")]
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != len(header):
            continue
        cells = dict(zip(header, tds, strict=True))
        name_cell: Tag = cells.get("JMÉNO")
        link = name_cell.find("a", href=PLAYER_HREF) if name_cell else None
        if link is None:
            continue
        m = PLAYER_HREF.search(link["href"])
        short = SHORT_YEAR.search(name_cell.get_text(" ", strip=True))
        row = {h: c.get_text(" ", strip=True) for h, c in cells.items()}
        row["_name"] = link.get_text(" ", strip=True)
        row["_id"] = int(m.group(2))
        row["_path"] = f"/hrac/{m.group(1)}/{m.group(2)}"
        row["_yy"] = int(short.group(1)) if short else None
        team_link = cells["TÝM"].find("a") if "TÝM" in cells else None
        row["_team"] = (
            (team_link or cells.get("TÝM")).get_text(" ", strip=True) if cells.get("TÝM") else None
        )
        rows.append(row)
    return rows


def parse_profile(html: str) -> str | None:
    """Birth date (ISO) from a player profile's "narozen" box."""
    soup = BeautifulSoup(html, "lxml")
    for h in soup.find_all(["h2", "h3"], class_="person-info-title"):
        if h.get_text(strip=True).lower().startswith("narozen"):
            span = h.find_next_sibling("span")
            return czech_date(span.get_text(" ", strip=True) if span else "")
    return None


# -- fetching ---------------------------------------------------------------------


def table_params(
    start: int, competition: int, section: str, *, foreign: bool = False, u20: bool = False
) -> dict[str, Any]:
    p: dict[str, Any] = {
        "stats-filter-season": start,
        "stats-filter-competition": competition,
        "stats-menu-section": section,
        "stats-view-pager-all": 1,
    }
    if foreign:
        p["stats-playerFilter-stranger"] = 1
    if u20:
        p["stats-playerFilter-age"] = 20
    return p


def fetch_competition(client: PoliteClient, start: int) -> int:
    html = client.get_text(STATS_URL, f"season_{start}.html", params={"stats-filter-season": start})
    return regular_competition(competitions(html), start)


def fetch_season(client: PoliteClient, start: int) -> dict[str, Any]:
    comp = fetch_competition(client, start)

    def table(section: str, suffix: str = "", **flt: bool) -> list[dict[str, Any]]:
        html = client.get_text(
            STATS_URL,
            f"{start}_{section}{suffix}.html",
            params=table_params(start, comp, section, **flt),
        )
        return parse_table(html)

    out: dict[str, Any] = {
        "competition_id": comp,
        "info": table("info"),
        "info_foreign": table("info", "_foreign", foreign=True),
        "info_u20": table("info", "_u20", u20=True),
        "goalkeeper": table("goalkeeper"),
        "goalkeeper_foreign": table("goalkeeper", "_foreign", foreign=True),
        "goalkeeper_u20": table("goalkeeper", "_u20", u20=True),
        "time": table("time") if start >= TOI_FROM else [],
    }
    if not out["info"]:
        raise ValueError(f"extraliga {start}: empty skater table (competition {comp})")
    return out


def fetch_profiles(client: PoliteClient, players: pd.DataFrame) -> pd.DataFrame:
    """One profile per player id (cached), in the order given."""
    rows = []
    todo = players.drop_duplicates("player_id")
    for i, r in enumerate(todo.itertuples(index=False), 1):
        html = client.get_text(f"{BASE}{r.profile_path}", f"profiles/{r.player_id}.html")
        rows.append(
            {
                "player_id": r.player_id,
                "full_name": r.full_name,
                "profile_path": r.profile_path,
                "birth_date": parse_profile(html),
            }
        )
        if i % 200 == 0:
            LOG.info("profiles %d/%d", i, len(todo))
    return pd.DataFrame(rows, columns=PROFILE_COLUMNS)


# -- building ---------------------------------------------------------------------


def _common(r: dict[str, Any], start: int, comp: int, flags: dict[str, Any]) -> dict[str, Any]:
    pos_raw = r.get("POZ.") or None
    pid = r["_id"]
    yy = flags["u20_years"].get(pid)
    return {
        "season": season_label(start),
        "season_start": start,
        "competition_id": comp,
        "player_id": pid,
        "full_name": r["_name"],
        "name_key": fold_name(r["_name"]),
        "profile_path": r["_path"],
        "birth_date": None,
        "birth_year": birth_year_from_short(yy, start) if yy is not None else None,
        "team": r.get("_team"),
        "position": POSITION.get(pos_raw or ""),
        "position_raw": pos_raw,
        "is_u20": pid in flags["u20"],
        "is_foreign": (pid in flags["foreign"]) if flags["has_foreign"] else None,
    }


def build_season(payload: dict[str, Any], start: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    comp = payload["competition_id"]
    foreign = {r["_id"] for r in payload["info_foreign"] + payload["goalkeeper_foreign"]}
    u20_rows = payload["info_u20"] + payload["goalkeeper_u20"]
    flags = {
        "foreign": foreign,
        "has_foreign": bool(foreign),
        "u20": {r["_id"] for r in u20_rows},
        "u20_years": {r["_id"]: r["_yy"] for r in u20_rows if r["_yy"] is not None},
    }
    time = {(r["_id"], r.get("_team")): r for r in payload["time"]}

    skaters = []
    for r in payload["info"]:
        rec = _common(r, start, comp, flags)
        t = time.get((r["_id"], r.get("_team")), {})
        gp = _int(r.get("GP"))
        toi = clock_to_s(t.get("TOI"))
        rec.update(
            {
                "games_played": gp,
                "goals": _int(r.get("G")),
                "assists": _int(r.get("A")),
                "points": _int(r.get("P")),
                "plus_minus": _int(r.get("+/-")),
                "pim": _int(r.get("PIM")),
                "toi_s": toi,
                "toi_per_game_s": toi / gp if toi is not None and gp else None,
                "shifts": _int(t.get("SFT")),
                "pp_toi_s": clock_to_s(t.get("PP TOI")),
                "sh_toi_s": clock_to_s(t.get("SH TOI")),
            }
        )
        skaters.append(rec)

    goalies = []
    for r in payload["goalkeeper"]:
        rec = _common(r, start, comp, flags)
        rec["position"] = "G"
        minutes = _int(r.get("TOI"))
        rec.update(
            {
                "games_played": _int(r.get("GP")),
                "toi_s": minutes * 60 if minutes is not None else clock_to_s(r.get("TOI")),
                "goals_against": _int(r.get("GA")),
                "saves": _int(r.get("Svs")),
                "shots_against": _int(r.get("SA")),
                "wins": _int(r.get("W")),
                "losses": _int(r.get("L")),
                "gaa": _float(r.get("GAA")),
                "save_pct": _float(r.get("Sv%")),
                "shutouts": _int(r.get("SO")),
            }
        )
        goalies.append(rec)
    return (
        pd.DataFrame(skaters, columns=SKATER_COLUMNS),
        pd.DataFrame(goalies, columns=GOALIE_COLUMNS),
    )


def attach_birth_dates(df: pd.DataFrame, profiles: pd.DataFrame) -> pd.DataFrame:
    """Birth date from the profiles; birth year from the date where the U20 list gave none."""
    df = df.copy()
    dates = profiles.dropna(subset=["birth_date"]).set_index("player_id")["birth_date"]
    df["birth_date"] = df["player_id"].map(dates)
    from_date = pd.to_numeric(df["birth_date"].str[:4], errors="coerce")
    df["birth_year"] = df["birth_year"].fillna(from_date)
    return df


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
    sort = [c for c in ("season_start", "player_id", "team") if c in df.columns]
    return df.sort_values(sort, kind="stable").reset_index(drop=True)


# -- coverage ---------------------------------------------------------------------


def _share(s: pd.Series) -> float | None:
    return round(float(s.mean()), 4) if len(s) else None


def coverage(
    skaters: pd.DataFrame, goalies: pd.DataFrame, profiles_from: int, starts: list[int]
) -> dict[str, Any]:
    per_season = []
    for start in starts:
        sk = skaters[skaters["season_start"] == start]
        go = goalies[goalies["season_start"] == start]
        pl = pd.concat([sk, go], ignore_index=True)
        per_season.append(
            {
                "season": season_label(start),
                "competition_id": int(pl["competition_id"].iloc[0]) if len(pl) else None,
                "skater_rows": int(len(sk)),
                "goalie_rows": int(len(go)),
                "foreign_flag": bool(pl["is_foreign"].notna().any()),
                "foreign_rows": int(pl["is_foreign"].fillna(False).sum()),
                "u20_rows": int(pl["is_u20"].fillna(False).sum()),
                "birth_date_share": _share(pl["birth_date"].notna()),
                "birth_year_share": _share(pl["birth_year"].notna()),
                "skater_toi_share": _share(sk["toi_s"].notna()),
                "goalie_toi_share": _share(go["toi_s"].notna()),
            }
        )
    return {
        "source": "hokej.cz player statistics (HTML), Extraliga regular season",
        "toi_from": season_label(TOI_FROM),
        "profiles_from": season_label(profiles_from),
        "seasons": per_season,
    }


# -- entry point ------------------------------------------------------------------


def run(
    first: int = FIRST_SEASON,
    last: int = LAST_SEASON,
    profiles_from: int = PROFILES_FROM,
    client: PoliteClient | None = None,
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR, min_interval=MIN_INTERVAL_S)
    starts = seasons(first, last)
    sk_frames, go_frames = [], []
    for start in starts:
        sk, go = build_season(fetch_season(client, start), start)
        LOG.info(
            "extraliga %s: %d skaters, %d goalies (%d foreign, %d U20)",
            season_label(start),
            len(sk),
            len(go),
            int(sk["is_foreign"].fillna(False).sum() + go["is_foreign"].fillna(False).sum()),
            int(sk["is_u20"].sum() + go["is_u20"].sum()),
        )
        sk_frames.append(sk)
        go_frames.append(go)
    skaters = pd.concat(sk_frames, ignore_index=True)
    goalies = pd.concat(go_frames, ignore_index=True)

    both = pd.concat([goalies, skaters], ignore_index=True)
    needed = both[both["season_start"] >= profiles_from].sort_values(
        "season_start", ascending=False, kind="stable"
    )
    LOG.info("profiles needed: %d players", needed["player_id"].nunique())
    profiles = fetch_profiles(client, needed)
    skaters = coerce(attach_birth_dates(skaters, profiles))
    goalies = coerce(attach_birth_dates(goalies, profiles))
    profiles = coerce(profiles)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        OUT_SKATERS: skaters,
        OUT_GOALIES: goalies,
        OUT_PROFILES: profiles,
    }
    paths = []
    for name, df in out.items():
        paths.append(config.PROCESSED_DIR / name)
        df.to_parquet(paths[-1], index=False)
    cov_path = config.PROCESSED_DIR / OUT_COVERAGE
    cov_path.write_text(
        json.dumps(coverage(skaters, goalies, profiles_from, starts), indent=1, ensure_ascii=False)
        + "\n",
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
    ap.add_argument("--profiles-from", type=int, default=PROFILES_FROM)
    a = ap.parse_args()
    for p in run(a.first, a.last, a.profiles_from):
        LOG.info("snapshot %s", p)


if __name__ == "__main__":
    main()
