"""Fetch Czech Tipsport Extraliga player stats from hokej.cz.

Architecture:
  1. Parse /tipsport-extraliga/table to extract the 14 Extraliga team IDs from
     the overall standings table.
  2. For each team, GET /klub/{slug}/{id}/statistiky and parse the team-season
     stats table (columns: POŘ, JMÉNO, TÝM, POZ, GP, G, A, P, +/-, +, -, PIM).
  3. Each row is one player-team-season; combine across all 14 teams.
  4. Nationality filter is deferred to crosswalk.py — most Extraliga players
     are Czech-eligible, but ~10-15% are imports (Slovak / Finn / Canadian)
     and need to be screened out via a separate metadata pass.

Writes:
  data/raw/extraliga_skaters_{season}.parquet  (all players, all positions)
  data/raw/extraliga_team_meta.parquet         (team_id, slug, name)

Notes:
  - hokej.cz is SSR'd, so plain requests + BeautifulSoup is sufficient
    (no Playwright).
  - Site returns HTTP 404 with a 160KB fallback page for unknown URLs;
    must check the HTTP status, not the response size.
  - 1. liga ("Maxa liga") would use the same shape via /maxa-liga; deferred
    to next session.

This module is SEASON-AGNOSTIC at the URL level: hokej.cz only exposes the
current season on /statistiky pages. Historical season fetches would require
a different URL pattern (TBD) and are deferred.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

import pandas as pd
from bs4 import BeautifulSoup

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import http_get, write_parquet

LOG = logging.getLogger(__name__)

HOKEJCZ_BASE = "https://www.hokej.cz"
TABLE_URL = f"{HOKEJCZ_BASE}/tipsport-extraliga/table"

# Common header politeness
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
}

POLITE_SLEEP_S = 1.5

# Standings table header signature — used to identify the right table on
# the multi-table /table page (others on the page are play-off bracket etc).
_STANDINGS_HEADER_SIGNATURE = ("Tým", "Z", "V", "P", "Skóre", "B")


# --- Team list discovery ----------------------------------------------------


def extract_extraliga_teams(html: str) -> pd.DataFrame:
    """Parse /tipsport-extraliga/table and return one row per Extraliga team.

    The standings table itself doesn't link team names — they're plain text
    with the slug in `<td data-sort-value="hc-dynamo-pardubice">`. The
    team_id we need (for /klub/{slug}/{id}/ URLs) comes from `<a href>` links
    elsewhere on the page (team logo links, etc.). Strategy:
      1. Build a slug → team_id map from ALL /klub/ links on the page.
      2. Scan standings tables; the team slug is in the `data-sort-value`
         attribute of the team cell (the 2nd td).
      3. Cross-reference: keep teams whose slug appears in standings.

    Returns DataFrame with columns: team_id, team_slug, team_name.
    """
    soup = BeautifulSoup(html, "lxml")

    # Step 1: slug -> (team_id, name) from all /klub/ links on the page
    slug_to_id: dict[str, int] = {}
    slug_to_name: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = re.match(r"/klub/([a-z0-9-]+)/(\d+)", a["href"])
        if not m:
            continue
        slug, tid = m.group(1), int(m.group(2))
        slug_to_id.setdefault(slug, tid)
        # Prefer the longest text occurrence as the canonical name
        text = a.get_text(strip=True)
        if text and len(text) > len(slug_to_name.get(slug, "")):
            slug_to_name[slug] = text

    # Step 2: standings tables — extract slugs from data-sort-value
    standings_slugs: list[str] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if not all(h in headers for h in _STANDINGS_HEADER_SIGNATURE):
            continue
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            slug = tds[1].get("data-sort-value")
            if not slug or slug in seen:
                continue
            seen.add(slug)
            standings_slugs.append(slug)

    # Step 3: build output (only standings slugs that we can resolve to a team_id)
    out_rows: list[dict] = []
    for slug in standings_slugs:
        tid = slug_to_id.get(slug)
        if tid is None:
            LOG.warning("standings slug %r has no team_id link on page", slug)
            continue
        out_rows.append({
            "team_id": tid,
            "team_slug": slug,
            "team_name": slug_to_name.get(slug, slug),
        })
    return pd.DataFrame(out_rows)


def get_team_list() -> pd.DataFrame:
    """Fetch /table page and extract Extraliga team list."""
    LOG.info("fetching Extraliga standings: %s", TABLE_URL)
    resp = http_get(TABLE_URL, headers=BROWSER_HEADERS, sleep_after=POLITE_SLEEP_S)
    return extract_extraliga_teams(resp.text)


# --- Per-team stats parsing -------------------------------------------------


# The team /statistiky page lists this column header set (in order).
# Confirmed via probe on /klub/hc-sparta-praha/8/statistiky.
_TEAM_STATS_HEADER_SIGNATURE = ("JMÉNO", "TÝM", "POZ.", "GP", "G", "A", "P")


def parse_team_stats(html: str, team_id: int, team_slug: str) -> pd.DataFrame:
    """Parse /klub/{slug}/{id}/statistiky → DataFrame of player-team-season rows."""
    soup = BeautifulSoup(html, "lxml")
    chosen_table = None
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if all(h in headers for h in _TEAM_STATS_HEADER_SIGNATURE):
            chosen_table = table
            break
    if chosen_table is None:
        LOG.warning("no stats table found for team %s (id=%s)", team_slug, team_id)
        return pd.DataFrame()

    header_cells = [th.get_text(strip=True) for th in chosen_table.find_all("th")]
    rows: list[dict] = []
    for tr in chosen_table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < len(header_cells):
            continue
        row: dict = {h: tds[i].get_text(" ", strip=True) for i, h in enumerate(header_cells)}
        # Extract player_id + slug from the JMÉNO cell's link
        jmeno_idx = header_cells.index("JMÉNO")
        link = tds[jmeno_idx].find("a")
        if link and link.get("href"):
            m = re.match(r"/hrac/([a-z0-9-]+)/(\d+)", link["href"])
            if m:
                row["player_slug"] = m.group(1)
                row["player_id"] = int(m.group(2))
        row["source_team_id"] = team_id
        row["source_team_slug"] = team_slug
        rows.append(row)
    return pd.DataFrame(rows)


def fetch_team_stats(team_id: int, team_slug: str) -> pd.DataFrame:
    """Fetch one team's /statistiky page and parse player rows."""
    url = f"{HOKEJCZ_BASE}/klub/{team_slug}/{team_id}/statistiky"
    LOG.info("  fetching %s", url)
    resp = http_get(url, headers=BROWSER_HEADERS, sleep_after=POLITE_SLEEP_S)
    return parse_team_stats(resp.text, team_id, team_slug)


# --- Numeric coercion -------------------------------------------------------


_NUMERIC_COLS = ("GP", "G", "A", "P", "+/-", "+", "-", "PIM")


# --- Per-player profile enrichment ------------------------------------------


PROFILE_CACHE_DIR = config.RAW_DIR / ".cache" / "extraliga_profiles"


def parse_birth_date_from_profile(html: str) -> str | None:
    """Extract 'narozen' field from a player profile page.

    The bio card has the structure:
        <h2 class="...person-info-title...">narozen</h2>
        <span>22.2.1991</span>
    """
    soup = BeautifulSoup(html, "lxml")
    for h2 in soup.find_all("h2", class_=re.compile("person-info-title")):
        if h2.get_text(strip=True).lower() == "narozen":
            span = h2.find_next_sibling("span")
            if span:
                return span.get_text(strip=True)
    return None


def fetch_player_profile(player_id: int, slug: str) -> dict:
    """Fetch one /hrac/{slug}/{id} profile, cache the HTML, return parsed bio.

    The hokej.cz profile page does NOT expose nationality / birthCountry —
    only birth_date is reliably extractable.
    """
    PROFILE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PROFILE_CACHE_DIR / f"{player_id}.html"
    if cache_path.exists() and cache_path.stat().st_size > 5_000:
        html = cache_path.read_text(encoding="utf-8")
    else:
        url = f"{HOKEJCZ_BASE}/hrac/{slug}/{player_id}"
        resp = http_get(url, headers=BROWSER_HEADERS, sleep_after=POLITE_SLEEP_S)
        html = resp.text
        cache_path.write_text(html, encoding="utf-8")
    return {
        "player_id": player_id,
        "birth_date": parse_birth_date_from_profile(html),
    }


def enrich_birth_dates() -> None:
    """For every unique Extraliga player, fetch /hrac/ profile and write
    a per-player metadata parquet (data/raw/extraliga_player_meta.parquet).
    """
    # Use the latest extraliga_skaters_{N}.parquet
    seasons = sorted(config.RAW_DIR.glob("extraliga_skaters_*.parquet"))
    if not seasons:
        LOG.error("no extraliga_skaters parquet to enrich from")
        return
    df = pd.read_parquet(seasons[-1])
    unique = df[["player_id", "player_slug"]].drop_duplicates().reset_index(drop=True)
    LOG.info("enriching birth dates for %d unique Extraliga players (cached after first run)",
             len(unique))
    rows: list[dict] = []
    for i, r in unique.iterrows():
        try:
            meta = fetch_player_profile(int(r["player_id"]), r["player_slug"])
        except Exception as e:  # noqa: BLE001
            LOG.warning("profile fetch failed for %s/%s: %s",
                        r["player_slug"], r["player_id"], e)
            continue
        rows.append(meta)
        if (i + 1) % 50 == 0:
            with_bd = sum(1 for x in rows if x.get("birth_date"))
            LOG.info("  %d/%d profiles fetched (%d with birth_date)",
                     i + 1, len(unique), with_bd)
    out = pd.DataFrame(rows)
    write_parquet(out, config.RAW_DIR / "extraliga_player_meta.parquet")
    LOG.info("wrote %d profiles (%d with birth_date)",
             len(out), out["birth_date"].notna().sum() if not out.empty else 0)


# --- Numeric coercion -------------------------------------------------------


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Convert stat columns to numeric. hokej.cz uses '.' decimal already."""
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

    teams = get_team_list()
    if teams.empty:
        LOG.error("no Extraliga teams found — check standings parsing")
        return
    LOG.info("found %d Extraliga teams", len(teams))
    write_parquet(teams, config.RAW_DIR / "extraliga_team_meta.parquet")

    per_team_frames: list[pd.DataFrame] = []
    for _, t in teams.iterrows():
        try:
            df = fetch_team_stats(int(t["team_id"]), t["team_slug"])
        except Exception as e:  # noqa: BLE001
            LOG.warning("team %s failed: %s", t["team_slug"], e)
            continue
        per_team_frames.append(df)

    if not per_team_frames:
        LOG.error("no team stats collected")
        return
    stats = pd.concat(per_team_frames, ignore_index=True)
    stats = coerce_numeric(stats)
    LOG.info("collected %d player-team-season rows across %d teams",
             len(stats), len(per_team_frames))

    # hokej.cz exposes only the current season on this endpoint. Per the
    # season_window in config/leagues.yaml, the current season is the latest
    # year (e.g. 2025 for 2025-26).
    seasons: list[int] = config.leagues()["leagues"]["nhl"]["season_window"]
    current_season = max(seasons)
    out = config.RAW_DIR / f"extraliga_skaters_{current_season}.parquet"
    write_parquet(stats, out)
    LOG.info("wrote %d rows to %s", len(stats), out.name)


if __name__ == "__main__":
    main()
