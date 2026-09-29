"""National-team rosters: IIHF World Championship 2010-2026 and Olympics 2010-2026, from Wikipedia.

Source: the English Wikipedia roster articles, e.g.

    "2025 IIHF World Championship rosters"
    "Ice hockey at the 2014 Winter Olympics – Men's team rosters"

Access: Wikipedia's robots.txt disallows /w/ (which includes the MediaWiki API,
/w/api.php, apart from action=mobileview) and /api/ for general user agents,
and welcomes "friendly, low-speed bots ... viewing article pages". So the
fetcher reads the rendered article pages, /wiki/<title>, one request per second,
and takes the revision id from the page's own configuration (`wgRevisionId`).
The tables are the same ones the API's action=parse would return.

Wikipedia text is CC BY-SA 4.0: every page used is recorded with its title,
URL, revision id, retrieval date and licence in rosters_sources.json, which the
site cites.

Each table row gives the player's name (and article link), position, club at
the time of the tournament and, on most pages, the birth date. Where the table
has no birth date (the 2010-2014 World Championship pages), it is
read from the player's own article (the infobox `bday`), for players of the ten
compared nations only; `birth_date_source` says which, and those articles are
listed in the sources file too. Height, weight, birthplace and statistics
columns are not kept.

The 2020 World Championship was cancelled and has no page. Every team on each
page is kept; `team_iso3` maps the team to ISO alpha-3.

Writes data/processed/rosters.parquet, rosters_sources.json and
rosters_coverage.json, then publishes them to data/snapshot/.

    python -m src.fetch.rosters [--first 2010] [--last 2026]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import pandas as pd
from bs4 import BeautifulSoup, Tag

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.fetch._names import fold_name, iso3_from_country
from src.logging_setup import setup as logging_setup
from src.nations import ISO3

LOG = logging.getLogger(__name__)

WIKI = "https://en.wikipedia.org/wiki/"
LICENSE = "CC BY-SA 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
FIRST_YEAR = 2010
LAST_YEAR = 2026
CANCELLED_WC = frozenset({2020})
OLYMPIC_YEARS = (2010, 2014, 2018, 2022, 2026)

RAW_DIR = config.RAW_DIR / "rosters"
OUT_ROSTERS = "rosters.parquet"
OUT_SOURCES = "rosters_sources.json"
OUT_COVERAGE = "rosters_coverage.json"

COLUMNS = [
    "event",
    "year",
    "page_title",
    "revid",
    "team",
    "team_iso3",
    "number",
    "position",
    "player",
    "name_key",
    "wiki_title",
    "birth_date",
    "birth_date_source",
    "club",
    "club_country",
    "club_league",
    "captaincy",
]

# Headings between a team's heading and its tables, and page furniture.
GENERIC_HEADING = re.compile(
    r"^(skaters|goaltenders|goalies|goalkeepers|roster|squad|players|team staff|staff|legend|"
    r"notes|references|see also|external links|group [a-z]|preliminary round.*|contents)$",
    re.I,
)
POSITIONS = {
    "G": "G",
    "GK": "G",
    "D": "D",
    "F": "F",
    "C": "F",
    "LW": "F",
    "RW": "F",
    "W": "F",
    "Goaltender": "G",
    "Defenceman": "D",
    "Defenseman": "D",
    "Forward": "F",
}
CAPTAINCY_RE = re.compile(r"\s*(?:–|-|\()\s*(C|A)\)?\s*$")
ISO_DATE_RE = re.compile(r"(1[89]\d\d|20\d\d)-(\d\d)-(\d\d)")
TEXT_DATE_RE = re.compile(r"\d{1,2} [A-Z][a-z]+ \d{4}|[A-Z][a-z]+ \d{1,2},? \d{4}")


def events(first: int = FIRST_YEAR, last: int = LAST_YEAR) -> list[dict[str, Any]]:
    out = [
        {"event": "WC", "year": y, "title": f"{y} IIHF World Championship rosters"}
        for y in range(first, last + 1)
        if y not in CANCELLED_WC
    ]
    out += [
        {
            "event": "OG",
            "year": y,
            "title": f"Ice hockey at the {y} Winter Olympics – Men's team rosters",
        }
        for y in OLYMPIC_YEARS
        if first <= y <= last
    ]
    return sorted(out, key=lambda e: (e["year"], e["event"]))


def page_url(title: str) -> str:
    return WIKI + quote(title.replace(" ", "_"), safe="()',")


def page_meta(html: str) -> dict[str, Any]:
    """Title and revision id from the page's mw.config (wgTitle, wgRevisionId)."""
    rev = re.search(r'"wgRevisionId":(\d+)', html)
    title = re.search(r'"wgTitle":("(?:[^"\\]|\\.)*")', html)
    if not rev or not title:
        raise ValueError("page has no wgRevisionId/wgTitle")
    return {"title": json.loads(title.group(1)), "revid": int(rev.group(1))}


def _cache_key(prefix: str, title: str) -> str:
    return f"{prefix}/{hashlib.sha256(title.encode()).hexdigest()[:16]}.html"


# -- one roster page --------------------------------------------------------------


def _heading_text(h: Tag) -> str:
    return re.sub(r"\[edit\]$", "", h.get_text(" ", strip=True)).strip()


def table_team(table: Tag) -> tuple[str | None, str | None]:
    """(team heading, sub-heading such as 'Goaltenders') of the nearest headings above the table."""
    sub = None
    for h in table.find_all_previous(["h2", "h3", "h4"]):
        text = _heading_text(h)
        if GENERIC_HEADING.match(text):
            sub = sub or text
            continue
        return text, sub
    return None, sub


def _col(header: list[str], pattern: str) -> int | None:
    rx = re.compile(pattern, re.I)
    return next((i for i, h in enumerate(header) if rx.search(h)), None)


def parse_birth_date(cell: Tag | None) -> str | None:
    """ISO date from a birth-date cell: the hidden bday span, a sort key or the visible text."""
    if cell is None:
        return None
    bday = cell.find(class_="bday")
    if bday and ISO_DATE_RE.search(bday.get_text()):
        return ISO_DATE_RE.search(bday.get_text()).group(0)
    for el in [cell, *cell.find_all(attrs={"data-sort-value": True})]:
        m = ISO_DATE_RE.search(el.get("data-sort-value") or "")
        if m:
            return m.group(0)
    text = re.sub(r"\(.*?\)", " ", cell.get_text(" ", strip=True))
    m = TEXT_DATE_RE.search(re.sub(r"\s+", " ", text))
    if m:
        for fmt in ("%d %B %Y", "%B %d, %Y", "%B %d %Y"):
            try:
                return dt.datetime.strptime(m.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    m = ISO_DATE_RE.search(text)
    return m.group(0) if m else None


def wiki_title(a: Tag | None) -> str | None:
    """Article title a link points to; None for red links (no article) and external links."""
    if a is None or "new" in (a.get("class") or []):
        return None
    href = a.get("href") or ""
    if "redlink=1" in href:
        return None
    path = urlsplit(href).path
    for prefix in ("/wiki/", "./"):
        if path.startswith(prefix):
            return unquote(path[len(prefix) :]).replace("_", " ") or None
    return None


def parse_player(cell: Tag) -> dict[str, Any]:
    a = next((x for x in cell.find_all("a", href=True) if x.get_text(strip=True)), None)
    text = cell.get_text(" ", strip=True)
    m = CAPTAINCY_RE.search(text)
    name = a.get_text(" ", strip=True) if a is not None else CAPTAINCY_RE.sub("", text).strip()
    return {"player": name, "wiki_title": wiki_title(a), "captaincy": m.group(1) if m else None}


def parse_club(cell: Tag | None) -> dict[str, Any]:
    if cell is None:
        return {"club": None, "club_country": None, "club_league": None}
    flag = cell.find(class_="flagicon")
    flag_a = flag.find("a") if flag else None
    small = cell.find("small")
    club_a = [
        a
        for a in cell.find_all("a")
        if not a.find_parent(class_="flagicon") and not a.find_parent("small")
    ]
    club = club_a[-1].get_text(" ", strip=True) if club_a else None
    if not club:
        text = cell.get_text(" ", strip=True)
        if small:
            text = text.replace(small.get_text(" ", strip=True), "")
        club = text.strip() or None
    league = small.find("a") if small else None
    country = flag_a.get("title") if flag_a else None
    if country is None and small:
        country = small.get_text(strip=True).strip("() ") or None
    return {
        "club": club,
        "club_country": country,
        "club_league": league.get("title") if league else None,
    }


def parse_page(html: str) -> pd.DataFrame:
    """Every player row of every team table on one roster page."""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for table in soup.find_all("table", class_="wikitable"):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"])]
        i_name = _col(header, r"^(name|player)")
        if i_name is None:
            continue
        team, sub = table_team(table)
        if team is None:
            continue
        i_pos = _col(header, r"^pos")
        i_no = _col(header, r"^(no\.?|number|#)$")
        i_dob = _col(header, r"birth ?date|date of birth|^born|^age")
        i_club = _col(header, r"club|team")
        sub_pos = "G" if sub and re.match(r"goal", sub, re.I) else None
        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) != len(header):
                continue  # spanning rows (notes, staff) are not players
            player = parse_player(cells[i_name])
            if not player["player"]:
                continue
            pos_raw = cells[i_pos].get_text(" ", strip=True) if i_pos is not None else ""
            rows.append(
                {
                    "team": team,
                    "number": cells[i_no].get_text(" ", strip=True) if i_no is not None else None,
                    "position": POSITIONS.get(pos_raw, sub_pos),
                    **player,
                    "birth_date": parse_birth_date(cells[i_dob]) if i_dob is not None else None,
                    **parse_club(cells[i_club] if i_club is not None else None),
                }
            )
    return pd.DataFrame(rows)


def article_birth_date(html: str) -> str | None:
    """Birth date from a player article's infobox (the hCard `bday`)."""
    box = BeautifulSoup(html, "lxml").find("table", class_=re.compile("infobox"))
    bday = box.find(class_="bday") if box else None
    m = ISO_DATE_RE.search(bday.get_text()) if bday else None
    return m.group(0) if m else None


# -- building ------------------------------------------------------------------------


def _source(client: PoliteClient, key: str, meta: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        **extra,
        "title": meta["title"],
        "url": page_url(meta["title"]),
        "revid": meta["revid"],
        "revision_url": f"https://en.wikipedia.org/w/index.php?oldid={meta['revid']}",
        "retrieved": dt.date.fromtimestamp((client.cache_dir / key).stat().st_mtime).isoformat(),
    }


def fetch_page(client: PoliteClient, ev: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = f"pages/{ev['event']}_{ev['year']}.html"
    html = client.get_text(page_url(ev["title"]), key)
    meta = page_meta(html)
    df = parse_page(html)
    if df.empty:
        raise ValueError(f"{ev['title']}: no roster tables")
    df["event"], df["year"] = ev["event"], ev["year"]
    df["page_title"], df["revid"] = meta["title"], meta["revid"]
    return df, _source(client, key, meta, event=ev["event"], year=ev["year"])


def fill_birth_dates(
    client: PoliteClient, df: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Birth dates missing from the tables, from the players' articles (compared nations only)."""
    df = df.copy()
    df["birth_date_source"] = df["birth_date"].notna().map({True: "wikipedia_table", False: None})
    want = df["birth_date"].isna() & df["team_iso3"].isin(ISO3) & df["wiki_title"].notna()
    titles = sorted(set(df.loc[want, "wiki_title"]))
    LOG.info("birth dates from %d player articles", len(titles))
    dob_of, sources = {}, []
    for title in titles:
        key = _cache_key("players", title)
        try:
            html = client.get_text(page_url(title), key)
        except Exception as e:  # a moved or deleted article leaves the date missing
            LOG.warning("%s: %s", title, e)
            continue
        dob = article_birth_date(html)
        if dob:
            dob_of[title] = dob
            sources.append(_source(client, key, page_meta(html), linked_from=title))
    fill = want & df["wiki_title"].isin(dob_of)
    df.loc[fill, "birth_date"] = df.loc[fill, "wiki_title"].map(dob_of)
    df.loc[fill, "birth_date_source"] = "wikipedia_article"
    return df, sources


def build(pages: list[pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat(pages, ignore_index=True)
    df["team_iso3"] = df["team"].map(iso3_from_country)
    df["name_key"] = df["player"].map(fold_name)
    return df


def finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = pd.array(df["year"], dtype="Int64")
    df["revid"] = pd.array(df["revid"], dtype="Int64")
    for c in COLUMNS:
        if c not in ("year", "revid"):
            df[c] = df[c].astype("string")
    return (
        df[COLUMNS]
        .sort_values(["year", "event", "team", "player"], kind="stable")
        .reset_index(drop=True)
    )


def coverage(df: pd.DataFrame, missing_pages: list[str]) -> dict[str, Any]:
    per_event = []
    for (year, event), g in df.groupby(["year", "event"], sort=True):
        ours = g[g["team_iso3"].isin(ISO3)]
        per_event.append(
            {
                "event": event,
                "year": int(year),
                "teams": int(g["team"].nunique()),
                "players": int(len(g)),
                "birth_date_share": round(float(g["birth_date"].notna().mean()), 4),
                "compared_birth_date_share": round(float(ours["birth_date"].notna().mean()), 4)
                if len(ours)
                else None,
                "birth_date_from_articles": int(
                    (g["birth_date_source"] == "wikipedia_article").sum()
                ),
                "club_share": round(float(g["club"].notna().mean()), 4),
                "position_share": round(float(g["position"].notna().mean()), 4),
                "compared_nations": {iso: int((ours["team_iso3"] == iso).sum()) for iso in ISO3},
            }
        )
    return {
        "source": "English Wikipedia roster articles (/wiki/ pages); missing birth dates from player articles",
        "license": LICENSE,
        "events": per_event,
        "missing_pages": missing_pages,
        "unmapped_teams": sorted(df.loc[df["team_iso3"].isna(), "team"].dropna().unique().tolist()),
    }


def run(
    first: int = FIRST_YEAR, last: int = LAST_YEAR, client: PoliteClient | None = None
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    pages, sources, missing = [], [], []
    for ev in events(first, last):
        try:
            df, src = fetch_page(client, ev)
        except Exception as e:  # a page that does not exist (404) or has no tables
            LOG.warning("%s: %s", ev["title"], e)
            missing.append(ev["title"])
            continue
        LOG.info(
            "%s %s: %d players, %d teams", ev["event"], ev["year"], len(df), df["team"].nunique()
        )
        pages.append(df)
        sources.append(src)
    roster, player_sources = fill_birth_dates(client, build(pages))
    roster = finish(roster)

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.PROCESSED_DIR / OUT_ROSTERS
    roster.to_parquet(out, index=False)
    src_path = config.PROCESSED_DIR / OUT_SOURCES
    src_path.write_text(
        json.dumps(
            {
                "license": LICENSE,
                "license_url": LICENSE_URL,
                "attribution": "Wikipedia contributors, English Wikipedia; each page at the revision listed",
                "pages": sources,
                "player_articles": player_sources,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    cov = config.PROCESSED_DIR / OUT_COVERAGE
    cov.write_text(
        json.dumps(coverage(roster, missing), indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    LOG.info("network calls: %d", client.network_calls)
    return snapshot.publish([out, src_path, cov])


def main() -> None:
    logging_setup()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--first", type=int, default=FIRST_YEAR)
    ap.add_argument("--last", type=int, default=LAST_YEAR)
    a = ap.parse_args()
    for p in run(a.first, a.last):
        LOG.info("snapshot %s", p)


if __name__ == "__main__":
    main()
