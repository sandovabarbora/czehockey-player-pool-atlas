"""Fetch Liiga player stats via Playwright headless browser.

Liiga's API v2 is locked at the application layer (403 on direct requests, even
with Origin/Referer headers). The website is a SPA, so plain requests return
only the JS shell. Playwright renders the SPA and lets us read the post-JS DOM.

Two-pass scrape:
  1. List pass: paginate /fi/pelaajat?sivu={N} until exhausted; extract
     player_id, name, birthdate, nationality, position, team. Filter to CZE.
  2. Stats pass: for each Czech player, render their /tilastot page and parse
     the per-season career table (regular season only; playoffs deferred).

Writes:
  data/raw/liiga_players_meta.parquet   — all Czech-eligible Liiga players' bio
  data/raw/liiga_skaters_{season}.parquet  — one row per (player_id, season)
  data/raw/liiga_goalies_{season}.parquet
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src import config
from src.logging_setup import setup as logging_setup
from src.playwright_helper import browser_context, render_url
from src.utils import write_parquet

LOG = logging.getLogger(__name__)

LIIGA_BASE = "https://liiga.fi"
LIST_URL = f"{LIIGA_BASE}/fi/pelaajat"
MAX_LIST_PAGES = 10  # safety: Liiga has ~400 players, so ~4 pages of 100

# Liiga position codes -> our standard
POSITION_MAP = {
    "OP": "F",   # Oikea puolustaja - actually right wing? Need to verify
    "VP": "D",   # Vasen puolustaja - left back (defenseman)
    "KP": "C",   # Keskushyökkääjä - center
    "LP": "F",   # Laitahyökkääjä - winger forward
    "PP": "D",   # Puolustaja - defenseman
    "MV": "G",   # Maalivahti - goalie
    # Will be refined after we see what codes actually appear for Czech players
}


# --- List page parsing ------------------------------------------------------


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    return text.replace("\xa0", "").strip() or None


def parse_list_page(html: str) -> list[dict]:
    """Extract player rows from one listing page. Returns one dict per player."""
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []
    n = 0
    while True:
        name_div = soup.find(id=f"player-list-stat-nameAsLink-{n}")
        if not name_div:
            break
        a = name_div.find("a")
        href = a.get("href") if a else None
        # Extract player_id and current team from href
        # Pattern: /fi/pelaajat/{id}/tilastot?kausi=2025-2026&joukkue=...&...
        pid_m = re.match(r"/fi/pelaajat/(\d+)/", href or "")
        player_id = int(pid_m.group(1)) if pid_m else None
        # Full name: <a>FirstName LastName<span># </span></a>
        # Strip the # span
        name_text = a.get_text(" ", strip=True) if a else None
        if name_text:
            name_text = re.sub(r"\s*#\s*$", "", name_text).strip()

        row = {
            "player_id": player_id,
            "name": name_text,
            "profile_path": href,
            "team_short": _clean(soup.find(id=f"player-list-stat-teamName-{n}").get_text() if soup.find(id=f"player-list-stat-teamName-{n}") else None),
            "role_code": _clean(soup.find(id=f"player-list-stat-roleCode-{n}").get_text() if soup.find(id=f"player-list-stat-roleCode-{n}") else None),
            "height_cm": _clean(soup.find(id=f"player-list-stat-height-{n}").get_text() if soup.find(id=f"player-list-stat-height-{n}") else None),
            "weight_kg": _clean(soup.find(id=f"player-list-stat-weight-{n}").get_text() if soup.find(id=f"player-list-stat-weight-{n}") else None),
            "handedness": _clean(soup.find(id=f"player-list-stat-handedness-{n}").get_text() if soup.find(id=f"player-list-stat-handedness-{n}") else None),
            "birth_locality": _clean(soup.find(id=f"player-list-stat-birthLocalityString-{n}").get_text() if soup.find(id=f"player-list-stat-birthLocalityString-{n}") else None),
            "date_of_birth": _clean(soup.find(id=f"player-list-stat-dateOfBirth-{n}").get_text() if soup.find(id=f"player-list-stat-dateOfBirth-{n}") else None),
            "nationality": _clean(soup.find(id=f"player-list-stat-nationality-{n}").get_text() if soup.find(id=f"player-list-stat-nationality-{n}") else None),
        }
        rows.append(row)
        n += 1
    return rows


def scrape_all_lists(browser) -> pd.DataFrame:
    """Paginate ?sivu=1..N until exhausted; return DataFrame of all players."""
    seen: set[int] = set()
    all_rows: list[dict] = []
    for sivu in range(1, MAX_LIST_PAGES + 1):
        url = f"{LIST_URL}?sivu={sivu}"
        html = render_url(browser, url, league="liiga", cache_key=f"list_p{sivu}")
        rows = parse_list_page(html)
        if not rows:
            LOG.info("page %d empty -> done", sivu)
            break
        new = [r for r in rows if r["player_id"] not in seen]
        if not new:
            LOG.info("page %d all duplicates -> done", sivu)
            break
        seen.update(r["player_id"] for r in new)
        all_rows.extend(new)
        LOG.info("page %d: %d rows (%d new, %d total)", sivu, len(rows), len(new), len(all_rows))
        if len(rows) < 100:
            LOG.info("page %d had <100 rows -> last page", sivu)
            break
    return pd.DataFrame(all_rows)


# --- Per-player stats page parsing ------------------------------------------


def parse_stats_page(html: str, player_id: int) -> pd.DataFrame:
    """Parse one player's /tilastot page into per-season rows.

    Targets the 'Uran tilastot - Runkosarja' (career-regular-season) table.
    Each row is `grid-stat-historical-regular-stats-{N}-{field}` for fields:
        season, teamShortName, leagueName, games, goals, assists, points,
        penaltyMinutes, plus, minus, plusMinus, powerPlayGoals,
        shortHandedGoals, winningGoals, shots, shotPercentage.
    The final row is a totals row (season == "Yht.") and is skipped.
    """
    soup = BeautifulSoup(html, "lxml")
    rows: list[dict] = []

    def _txt(_id: str) -> str | None:
        el = soup.find(id=_id)
        return _clean(el.get_text()) if el else None

    n = 0
    while True:
        prefix = f"grid-stat-historical-regular-stats-{n}"
        season = _txt(f"{prefix}-season")
        if season is None:
            break
        if season == "Yht.":  # totals row — skip
            n += 1
            continue
        rows.append({
            "player_id": player_id,
            "season": season,
            "team": _txt(f"{prefix}-teamShortName"),
            "league": _txt(f"{prefix}-leagueName"),
            "gp": _txt(f"{prefix}-games"),
            "goals": _txt(f"{prefix}-goals"),
            "assists": _txt(f"{prefix}-assists"),
            "points": _txt(f"{prefix}-points"),
            "pim": _txt(f"{prefix}-penaltyMinutes"),
            "plus": _txt(f"{prefix}-plus"),
            "minus": _txt(f"{prefix}-minus"),
            "plus_minus": _txt(f"{prefix}-plusMinus"),
            "pp_goals": _txt(f"{prefix}-powerPlayGoals"),
            "sh_goals": _txt(f"{prefix}-shortHandedGoals"),
            "gw_goals": _txt(f"{prefix}-winningGoals"),
            "shots": _txt(f"{prefix}-shots"),
            "shot_pct": _txt(f"{prefix}-shotPercentage"),
        })
        n += 1
    return pd.DataFrame(rows)


def scrape_player_stats(browser, player_id: int, profile_path: str) -> pd.DataFrame:
    """Render one Czech player's /tilastot page and parse career stats."""
    url = f"{LIIGA_BASE}{profile_path}"
    html = render_url(browser, url, league="liiga", cache_key=f"player_{player_id}")
    return parse_stats_page(html, player_id)


# --- Numeric coercion -------------------------------------------------------


_NUMERIC_COLS = (
    "gp", "goals", "assists", "points", "pim",
    "plus", "minus", "plus_minus",
    "pp_goals", "sh_goals", "gw_goals", "shots", "shot_pct",
)


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert numeric columns to float; Finnish decimal separator is ','."""
    out = df.copy()
    for col in _NUMERIC_COLS:
        if col in out.columns:
            out[col] = (
                out[col]
                .astype("string")
                .str.replace(",", ".", regex=False)
                .str.replace(r"[^\d.\-]", "", regex=True)
                .replace("", pd.NA)
                .astype("Float64")
            )
    return out


# --- Main -------------------------------------------------------------------


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    with browser_context() as browser:
        LOG.info("Liiga: scraping player list")
        all_players = scrape_all_lists(browser)
        LOG.info("found %d total Liiga players", len(all_players))

        czech = all_players[all_players["nationality"] == "CZE"].reset_index(drop=True)
        LOG.info("of which %d Czech-eligible", len(czech))
        write_parquet(czech, config.RAW_DIR / "liiga_players_meta.parquet")

        if czech.empty:
            LOG.warning("no Czech Liiga players found — nothing to enrich")
            return

        LOG.info("scraping per-player stats for %d Czech players", len(czech))
        per_player_frames: list[pd.DataFrame] = []
        for _, p in czech.iterrows():
            try:
                df = scrape_player_stats(browser, int(p["player_id"]), p["profile_path"])
            except Exception as e:  # noqa: BLE001
                LOG.warning("stats fetch failed for %s: %s", p["name"], e)
                continue
            if df.empty:
                LOG.warning("no stat rows for %s (pid=%s)", p["name"], p["player_id"])
            per_player_frames.append(df)

        if not per_player_frames:
            LOG.error("no stat frames collected")
            return

        stats = pd.concat(per_player_frames, ignore_index=True)
        stats = coerce_numeric(stats)
        LOG.info("collected %d total stat rows across all Czech players + all seasons", len(stats))

        # Split skaters vs goalies via the meta role_code
        meta_role = czech.set_index("player_id")["role_code"]
        stats = stats.merge(meta_role.rename("role_code"), left_on="player_id", right_index=True, how="left")

        is_goalie = stats["role_code"].fillna("").eq("MV")
        skaters = stats[~is_goalie].copy()
        goalies = stats[is_goalie].copy()

        # Restrict to the seasons in our window: brief uses 2024-25 + 2025-26
        target_seasons = {"2024-25", "2025-26"}
        for season_label in target_seasons:
            sk = skaters[skaters["season"] == season_label].copy()
            go = goalies[goalies["season"] == season_label].copy()
            # Convert season label "2024-25" -> int 2024 for filename consistency with NHL/MoneyPuck
            yr = int(season_label.split("-")[0])
            write_parquet(sk, config.RAW_DIR / f"liiga_skaters_{yr}.parquet")
            write_parquet(go, config.RAW_DIR / f"liiga_goalies_{yr}.parquet")
            LOG.info("season %s: %d skater-rows, %d goalie-rows", season_label, len(sk), len(go))


if __name__ == "__main__":
    main()
