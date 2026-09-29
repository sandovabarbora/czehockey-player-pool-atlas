"""Shared definitions for the analysis modules: the league ladder, seasons, the games
threshold, population, age, and the JSON writer.

Every number the report states is read from a JSON file written through `write_output`,
which records the SHA-256 of each snapshot file the module read, so a reader can tell
which data a figure came from.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import config
from src.fetch._names import fold_name
from src.nations import HOME, ISO3, NATIONS

SNAPSHOT_DIR: Path = config.DATA_DIR / "snapshot"
OUTPUTS_DIR: Path = config.OUTPUTS_DIR

# --- League ladder (spec §2) ----------------------------------------------------------

LEAGUES: tuple[str, ...] = ("NHL", "SHL", "Liiga", "NL", "DEL", "Extraliga")
RUNG_1: frozenset[str] = frozenset({"NHL"})
RUNG_2: frozenset[str] = frozenset({"SHL", "Liiga", "NL", "DEL"})
TOP5: frozenset[str] = RUNG_1 | RUNG_2
HOME_LEAGUE: dict[str, str] = {
    "CZE": "Extraliga",
    "FIN": "Liiga",
    "SWE": "SHL",
    "CHE": "NL",
    "DEU": "DEL",
}
"""Each nation's own top league where it is covered. SVK, LVA, DNK, NOR and AUT have no
covered home league. For FIN, SWE, CHE and DEU the home league is also rung 2, and rung 2
takes precedence."""

RUNG_ORDER: dict[str, int] = {"1": 0, "2": 1, "home": 2, "other": 3}


def rung(league: str, nation: str | None = HOME) -> str:
    """'1' (NHL), '2' (SHL, Liiga, NL, DEL), 'home' (the nation's own covered top league
    when it is not rung 2, i.e. the Extraliga for Czechia) or 'other'."""
    if league in RUNG_1:
        return "1"
    if league in RUNG_2:
        return "2"
    if nation is not None and HOME_LEAGUE.get(nation) == league:
        return "home"
    return "other"


# --- Seasons -------------------------------------------------------------------------

FIRST_SEASON = 1995
LAST_SEASON = 2025
LOCKOUT_SEASONS: frozenset[int] = frozenset({2004})
"""NHL seasons that were not played (2004/05, lockout)."""


def season_label(start: int) -> str:
    """1995 -> '1995/96'."""
    return f"{start}/{(start + 1) % 100:02d}"


def season_start(label: str) -> int:
    """'1995/96' -> 1995."""
    m = re.fullmatch(r"(\d{4})/\d{2}", str(label))
    if not m:
        raise ValueError(f"not a season label: {label!r}")
    return int(m.group(1))


def seasons(first: int = FIRST_SEASON, last: int = LAST_SEASON) -> list[int]:
    return list(range(first, last + 1))


# --- Games threshold -----------------------------------------------------------------

THRESHOLD_GAMES = 20
FULL_NHL_SCHEDULE = 82
THRESHOLD_SHARE = THRESHOLD_GAMES / FULL_NHL_SCHEDULE
"""A player counts for a league-season with at least 20 games of an 82-game NHL schedule,
pro-rated to the league-season's schedule length: 20 in a full NHL season, 12 in the
48-game 2012/13 season, 13 in a 52-game league."""


def schedule_length(games_played: Iterable[float]) -> int:
    """The league-season's schedule length, read off the data as the 95th percentile of
    skater games played (robust to a few traded players who played more than a team)."""
    gp = pd.Series(list(games_played), dtype="float64").dropna()
    if gp.empty:
        return 0
    return int(round(float(np.percentile(gp, 95))))


def games_threshold(schedule: int) -> int:
    """At least one game; otherwise the pro-rated share of 20 of 82."""
    return max(1, int(round(THRESHOLD_SHARE * schedule)))


# --- Age -----------------------------------------------------------------------------

U21_MAX_AGE = 20
"""Under 21: aged 20 or younger in the calendar year the season starts, i.e. born in or
after (season start year - 20). The same year-based age is used everywhere, so a birth
year is enough."""

AGE_BANDS: tuple[tuple[str, int, int], ...] = (
    ("≤21", 0, 21),
    ("22–25", 22, 25),
    ("26–29", 26, 29),
    ("30+", 30, 99),
)


def season_age(season_start_year: int, birth_year: float | int | None) -> float:
    """Age reached in the calendar year the season starts (season start - birth year)."""
    if birth_year is None or (isinstance(birth_year, float) and math.isnan(birth_year)):
        return float("nan")
    return float(season_start_year - int(birth_year))


def age_band(age: float) -> str:
    if age is None or (isinstance(age, float) and math.isnan(age)):
        return "unknown"
    for label, lo, hi in AGE_BANDS:
        if lo <= age <= hi:
            return label
    return "unknown"


# --- Names ---------------------------------------------------------------------------


def link_key(name: object) -> str | None:
    """The name half of the linking key: diacritics folded, lower case, hyphens as spaces,
    tokens sorted, so 'Voráček Jakub', 'Jakub Voracek' and 'Voracek, Jakub' agree."""
    folded = fold_name(name)
    if not folded:
        return None
    tokens = sorted(t for t in folded.replace("-", " ").split() if t)
    return " ".join(tokens) or None


def initial_key(name: object) -> str | None:
    """First-name initial plus the sorted surname tokens: 'Dan Vladař' and 'Daniel Vladař'
    both give 'd vladar'. Used only together with a full birth date."""
    folded = fold_name(name)
    if not folded:
        return None
    tokens = [t for t in folded.replace("-", " ").split() if t]
    if len(tokens) < 2:
        return None
    return f"{tokens[0][0]} {' '.join(sorted(tokens[1:]))}"


# --- Population ----------------------------------------------------------------------


def population_table() -> pd.DataFrame:
    """iso3, year, population (Eurostat, 1 January)."""
    df = load("population.parquet")
    df = df[df["iso3"].isin(ISO3)].copy()
    df["population"] = df["population"].astype("float64")
    return df[["iso3", "year", "population"]]


def population_for_season(pop: pd.DataFrame, iso3: str, start: int) -> float:
    """Population on 1 January of the season's second year (mid-season). Falls back to
    the latest earlier year when that year is missing."""
    sub = pop[(pop["iso3"] == iso3) & (pop["year"] <= start + 1)].sort_values("year")
    if sub.empty:
        return float("nan")
    return float(sub["population"].iloc[-1])


def per_million(count: float, population: float) -> float:
    if not population or math.isnan(population):
        return float("nan")
    return count / population * 1e6


def nation_names() -> dict[str, str]:
    return {n.iso3: n.name for n in NATIONS}


# --- IO ------------------------------------------------------------------------------


def _path(name: str) -> Path:
    processed = config.PROCESSED_DIR / name
    return processed if processed.exists() else SNAPSHOT_DIR / name


def load(name: str) -> pd.DataFrame:
    """A processed table, from data/processed/ when present, else the committed snapshot."""
    return pd.read_parquet(_path(name))


def snapshot_hashes(names: Iterable[str]) -> dict[str, str]:
    sums = SNAPSHOT_DIR / "SHA256SUMS"
    listed: dict[str, str] = {}
    if sums.exists():
        for line in sums.read_text(encoding="utf-8").splitlines():
            if line.strip():
                digest, rel = line.split("  ", 1)
                listed[rel] = digest
    return {n: listed.get(n, "unlisted") for n in sorted(set(names))}


def clean(obj: Any) -> Any:
    """JSON-safe copy: NaN/NA -> None, numpy scalars -> Python, floats rounded to 6 places (enough for a one-decimal percentage)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    return obj


def write_output(
    name: str, payload: dict[str, Any], inputs: Iterable[str] = (), out_dir: Path | None = None
) -> Path:
    """Write outputs/<name> with a `meta.inputs` block of snapshot hashes. No timestamps,
    so a rebuild on unchanged data gives a byte-identical file."""
    out_dir = out_dir or OUTPUTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {"meta": {"inputs": snapshot_hashes(inputs)}, **payload}
    path = out_dir / name
    path.write_text(json.dumps(clean(body), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def read_output(name: str, out_dir: Path | None = None) -> dict[str, Any]:
    return json.loads(((out_dir or OUTPUTS_DIR) / name).read_text(encoding="utf-8"))
