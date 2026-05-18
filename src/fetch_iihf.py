"""Fetch Czech IIHF tournament participation history.

Source: Wikipedia (CC-BY-SA, scraping-friendly, well-structured wikitables).
The official iihf.com is fully behind Cloudflare's "Under Attack" bot
challenge (5.5KB challenge page returned even via Playwright); the legacy
stats.iihf.com Hydra system is JS-rendered and serves stale demo data.
Wikipedia tournament squad pages are the most reliable public source.

Scope (locked per critique decision):
  - MS 2024 (Prague/Ostrava — gold for Czechia)
  - MS 2025 (Stockholm/Herning)
  - WJC 2024 (Gothenburg)
  - WJC 2025 (Ottawa)

What we extract:
  - Per-player participation: full name, position, birth date, club at
    tournament time.
  - NO per-player tournament stats (Wikipedia doesn't list them on these
    pages; stats would need a separate fetch and aren't needed for the
    eligibility-flag use case).

Writes:
    data/raw/iihf_participation.parquet
        Columns: tournament, year, name, name_normalized, position,
                 birth_date, birth_year, club_at_tournament

Downstream: crosswalk.py joins this on (name_normalized + birth_year) to
flag any canonical player as confirmed Czech-eligible.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable

import pandas as pd
from bs4 import BeautifulSoup

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import http_get, write_parquet

LOG = logging.getLogger(__name__)

WP_HEADERS = {
    "User-Agent": "czehockey-player-pool-atlas/0.1 (research; "
                   "https://github.com/barborasandova; barbora@datasimply.eu)",
}

# Locked tournament list (per critique decision #8: 4 tournaments only)
TOURNAMENTS: tuple[tuple[str, int, str], ...] = (
    ("ms", 2024,
     "https://en.wikipedia.org/wiki/2024_IIHF_World_Championship_rosters"),
    ("ms", 2025,
     "https://en.wikipedia.org/wiki/2025_IIHF_World_Championship_rosters"),
    ("wjc", 2024,
     "https://en.wikipedia.org/wiki/2024_World_Junior_Ice_Hockey_Championships_rosters"),
    ("wjc", 2025,
     "https://en.wikipedia.org/wiki/2025_World_Junior_Ice_Hockey_Championships_rosters"),
)

CACHE_DIR = config.RAW_DIR / ".cache" / "wikipedia_iihf"


# --- Normalizers ------------------------------------------------------------


def _normalize_name(name: str | None) -> str:
    """Match the same normalizer used in crosswalk: NFKD + strip combining marks."""
    if not isinstance(name, str) or not name.strip():
        return ""
    nfd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _clean_name(raw: str) -> str:
    """Remove Wikipedia captain/alternate markers (' – C', ' – A') from a name."""
    if not raw:
        return raw
    cleaned = re.sub(r"\s*[–-]\s*[CA]\b\s*$", "", raw).strip()
    return cleaned


def _parse_birthdate(cell_text: str) -> tuple[str | None, int | None]:
    """Parse 'Birthdate' cell, which contains the ISO date in parentheses.

    Wikipedia uses the {{birth date and age}} template which renders as:
        '( 2000-06-22 ) 22 June 2000 (age 24)'
    """
    m = re.search(r"\(\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*\)", cell_text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", int(y)
    return None, None


# --- Per-page parsing -------------------------------------------------------


def _find_czech_table(soup: BeautifulSoup) -> "BeautifulSoup | None":
    """Locate the 'Czechia' or 'Czech Republic' section's first wikitable.

    Wikipedia uses 'Czechia' for recent rosters; older ones may use 'Czech
    Republic'. Both should be tried.
    """
    for header_text in ("Czechia", "Czech Republic", "Česko", "Česká republika"):
        h = soup.find(["h2", "h3"], string=re.compile(rf"^{header_text}$", re.IGNORECASE))
        if h is None:
            # Wikipedia sometimes wraps the header text in <span>, check less strictly
            for candidate in soup.find_all(["h2", "h3"]):
                if header_text.lower() in candidate.get_text(strip=True).lower():
                    h = candidate
                    break
        if h is None:
            continue
        table = h.find_next("table", class_="wikitable")
        if table is not None:
            return table
    return None


def parse_squad_page(html: str, tournament: str, year: int) -> pd.DataFrame:
    """Parse one tournament rosters Wikipedia page; return Czech squad rows."""
    soup = BeautifulSoup(html, "lxml")
    table = _find_czech_table(soup)
    if table is None:
        LOG.warning("no Czech section found for %s %s", tournament, year)
        return pd.DataFrame()

    # Read header row
    header_row = table.find("tr")
    headers = [th.get_text(" ", strip=True) for th in header_row.find_all(["th"])]
    LOG.debug("%s %s headers: %s", tournament, year, headers)

    # MS pages use "Name" + "Birthdate"; WJC pages use "Player" without Birthdate.
    def _idx(*aliases: str) -> int | None:
        for a in aliases:
            if a in headers:
                return headers.index(a)
        return None

    name_idx = _idx("Name", "Player")
    pos_idx = _idx("Pos.")
    bd_idx = _idx("Birthdate", "Date of birth")
    team_idx = _idx("Team", "Club")

    rows: list[dict] = []
    for tr in table.find_all("tr")[1:]:  # skip header
        cells = tr.find_all(["td", "th"])
        if len(cells) < len(headers):
            continue
        name_raw = cells[name_idx].get_text(" ", strip=True) if name_idx is not None else ""
        name = _clean_name(name_raw)
        if not name:
            continue
        position = cells[pos_idx].get_text(" ", strip=True) if pos_idx is not None else None
        bd_iso, by_year = (None, None)
        if bd_idx is not None:
            bd_iso, by_year = _parse_birthdate(cells[bd_idx].get_text(" ", strip=True))
        team = cells[team_idx].get_text(" ", strip=True) if team_idx is not None else None

        rows.append({
            "tournament": tournament,
            "year": year,
            "name": name,
            "name_normalized": _normalize_name(name),
            "position": position,
            "birth_date": bd_iso,
            "birth_year": by_year,
            "club_at_tournament": team,
        })
    return pd.DataFrame(rows)


def fetch_tournament(tournament: str, year: int, url: str) -> pd.DataFrame:
    """Fetch + parse one tournament page (cached)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{tournament}_{year}.html"
    if cache_path.exists() and cache_path.stat().st_size > 50_000:
        LOG.info("  cached: %s", cache_path.name)
        html = cache_path.read_text(encoding="utf-8")
    else:
        LOG.info("  fetching %s", url)
        resp = http_get(url, headers=WP_HEADERS, sleep_after=1.0)
        html = resp.text
        cache_path.write_text(html, encoding="utf-8")
    return parse_squad_page(html, tournament, year)


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    LOG.info("IIHF: fetching %d tournaments", len(TOURNAMENTS))
    all_frames: list[pd.DataFrame] = []
    for tournament, year, url in TOURNAMENTS:
        LOG.info("%s %s", tournament.upper(), year)
        df = fetch_tournament(tournament, year, url)
        LOG.info("  %d Czech players", len(df))
        all_frames.append(df)

    if not all_frames:
        LOG.error("no tournament data collected")
        return
    combined = pd.concat(all_frames, ignore_index=True)
    write_parquet(combined, config.RAW_DIR / "iihf_participation.parquet")

    LOG.info("=== IIHF summary ===")
    LOG.info("total participation rows: %d", len(combined))
    LOG.info("unique Czech players: %d", combined["name_normalized"].nunique())
    LOG.info("by tournament/year: %s",
             combined.groupby(["tournament", "year"]).size().to_dict())


if __name__ == "__main__":
    main()
