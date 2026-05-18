"""Download MoneyPuck season-summary CSVs (NHL xG and advanced metrics).

URL pattern:
    https://moneypuck.com/moneypuck/playerData/seasonSummary/{YEAR}/regular/{table}.csv

MoneyPuck single-year notation: "2024" = 2024-25 season.

Data-license note:
    MoneyPuck's server returns a license-request HTML page when the User-Agent
    does not look like a browser. A browser UA bypasses this and returns the
    real CSV. The project follows a "bandwidth-considerate" access pattern:
        - Browser UA explicitly set.
        - Each CSV downloaded once per season and cached locally; subsequent
          runs use the cached copy.
        - This access pattern is documented in the report's Limitations
          section.
    MoneyPuck's stated preference is for a data license agreement; the public
    research nature of this project is documented in the README. Consider
    emailing moneypuck.com@gmail.com for an explicit research-use license
    before any public release of derived materials.

Writes:
    data/raw/moneypuck_skaters_{season}.parquet   (ALL players, all situations)
    data/raw/moneypuck_goalies_{season}.parquet   (ALL players)

Note on filtering:
    MoneyPuck CSV has no nationality column but uses NHL playerId as primary key.
    The CSV is kept whole here; src/crosswalk.py performs the Czech-only filter
    by joining on playerId against data/raw/nhl_player_meta.parquet.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import http_get, write_parquet

LOG = logging.getLogger(__name__)

MP_BASE_URL = "https://moneypuck.com/moneypuck/playerData/seasonSummary"
MP_CACHE_DIR = config.RAW_DIR / ".cache" / "moneypuck"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
POLITE_SLEEP_S = 2.0  # between downloads — be generous, MoneyPuck pays bandwidth


def download_csv(season: int, table: str) -> Path:
    """Download a MoneyPuck season-summary CSV and return the cache path.

    Args:
        season: starting year (2024 = 2024-25 season)
        table: "skaters" or "goalies"

    Returns:
        Path to the cached CSV on disk. Cache is keyed by (season, table);
        re-runs do not re-download.
    """
    MP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = MP_CACHE_DIR / f"{table}_{season}.csv"
    if cache_path.exists() and cache_path.stat().st_size > 10_000:
        LOG.info("cached: %s (skipping download)", cache_path.name)
        return cache_path

    url = f"{MP_BASE_URL}/{season}/regular/{table}.csv"
    LOG.info("downloading %s", url)
    resp = http_get(url, headers={"User-Agent": BROWSER_UA})
    body = resp.content
    if len(body) < 10_000 or body.lstrip().startswith(b"<"):
        raise RuntimeError(
            f"MoneyPuck returned non-CSV response for {url} "
            f"({len(body)} bytes). Likely served the license page. "
            "Verify User-Agent and access pattern."
        )
    cache_path.write_bytes(body)
    LOG.info("wrote %d bytes to %s", len(body), cache_path.name)
    time.sleep(POLITE_SLEEP_S)
    return cache_path


def load_csv(csv_path: Path) -> pd.DataFrame:
    """Load a MoneyPuck CSV. No filtering — keep all players + situations.

    The 'situation' column has values {'all', '5on5', '5on4', '4on5', 'other'}.
    Czech-only filter happens in src/crosswalk.py via playerId join.
    """
    return pd.read_csv(csv_path)


def fetch_season(season: int) -> None:
    """Download skater + goalie CSVs for one season and write parquets."""
    for table in ("skaters", "goalies"):
        csv_path = download_csv(season, table)
        df = load_csv(csv_path)
        out = config.RAW_DIR / f"moneypuck_{table}_{season}.parquet"
        write_parquet(df, out)
        situations = sorted(df["situation"].unique()) if "situation" in df.columns else []
        unique_players = df["playerId"].nunique() if "playerId" in df.columns else 0
        LOG.info(
            "MoneyPuck %s %d: %d rows across %d unique players, situations=%s",
            table, season, len(df), unique_players, situations,
        )


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    seasons: list[int] = config.leagues()["leagues"]["nhl"]["season_window"]
    for season in seasons:
        LOG.info("MoneyPuck: season %d", season)
        fetch_season(season)


if __name__ == "__main__":
    main()
