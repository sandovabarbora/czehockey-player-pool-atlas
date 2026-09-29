"""Question 6: what is the national team built from? World Championship and Olympic rosters
from 2010, each player's club at the time and that club's league rung.

The tournament is played at the end of the season (season = year - 1 / year). Each roster
player's club is placed in a league by the first rule that applies:

1. `club_league`: the league Wikipedia names for the club.
2. KHL clubs: a club in Russia (by country, or by name when Wikipedia gives no country),
   or one of the KHL's clubs outside Russia in the years it played there (`KHL_CLUBS`).
3. The NHL career record of the player (linked on name + birth date), for that season, at
   the team that best matches the club name. This is how AHL and KHL spells of NHL players
   are placed.
4. The player's own row in a covered league that season, in the league of the club's
   country when that is known, else the league where he played the most games.
5. The club name against the team names of the covered leagues that season.
6. Otherwise, when the club's country is known, a league the atlas does not cover
   ('other': a second tier, the AHL or juniors in North America, the Slovak, Austrian,
   Danish, Norwegian or Latvian league).

Categories: rung '1' (NHL), '2' (SHL, Liiga, NL, DEL), 'home' (the Extraliga, for
Czechia), 'khl' (not covered: named because it removes a real destination, spec §2),
'other' (every other league, the AHL included) and 'unknown'.

    python -m src.analysis.q6_national_team   -> outputs/q6_national_team.json
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import pandas as pd

from src.analysis import common, linking
from src.fetch._names import fold_name
from src.nations import HOME, ISO3

LOG = logging.getLogger(__name__)

FIRST_YEAR = 2010
CATEGORIES = ("1", "2", "home", "khl", "other", "unknown")

CLUB_LEAGUE_TEXT = {
    "National Hockey League": "NHL",
    "Swedish Hockey League": "SHL",
    "Elitserien": "SHL",
    "Liiga": "Liiga",
    "SM-liiga": "Liiga",
    "National League A": "NL",
    "National League (ice hockey)": "NL",
    "National League": "NL",
    "Deutsche Eishockey Liga": "DEL",
    "Czech Extraliga": "Extraliga",
    "Kontinental Hockey League": "KHL",
    "American Hockey League": "AHL",
}

CAREER_LEAGUE = {
    "NHL": "NHL",
    "AHL": "AHL",
    "SHL": "SHL",
    "Sweden": "SHL",
    "Liiga": "Liiga",
    "Finland": "Liiga",
    "SM-liiga": "Liiga",
    "NL": "NL",
    "NLA": "NL",
    "Swiss": "NL",
    "DEL": "DEL",
    "Germany": "DEL",
    "CzRep": "Extraliga",
    "Czechia": "Extraliga",
    "Czech": "Extraliga",
    "KHL": "KHL",
    "Rus-KHL": "KHL",
}

LEAGUE_COUNTRY = {
    "NHL": {"United States", "Canada"},
    "SHL": {"Sweden"},
    "Liiga": {"Finland"},
    "NL": {"Switzerland"},
    "DEL": {"Germany"},
    "Extraliga": {"Czech Republic", "Czechia"},
}

KHL_CLUBS: tuple[tuple[str, int, int], ...] = (
    ("riga", 2009, 2022),
    ("minsk", 2009, 2026),
    ("barys", 2009, 2026),
    ("jokerit", 2015, 2022),
    ("slovan bratislava", 2013, 2019),
    ("lev praha", 2013, 2014),
    ("lev poprad", 2011, 2011),
    ("medvescak", 2014, 2017),
    ("kunlun", 2017, 2026),
    ("donbass", 2013, 2014),
)
"""KHL clubs outside Russia: a name fragment and the tournament years (season end) they
played in the KHL. Dinamo Riga, Dinamo Minsk and Barys since the league's first season."""

RUSSIAN_KHL_FRAGMENTS: tuple[str, ...] = (
    "salavat",
    "ufa",
    "magnitogorsk",
    "cherepovets",
    "severstal",
    "cska",
    "atlant",
    "avangard",
    "omsk",
    "ska saint",
    "ska st",
    "ska sankt",
    "st petersburg",
    "saint petersburg",
    "ak bars",
    "kazan",
    "lokomotiv",
    "yaroslavl",
    "dynamo moscow",
    "dinamo moscow",
    "dynamo moskva",
    "spartak",
    "torpedo nizhny",
    "nizhny novgorod",
    "traktor",
    "chelyabinsk",
    "sibir",
    "novosibirsk",
    "amur",
    "khabarovsk",
    "vityaz",
    "avtomobilist",
    "yekaterinburg",
    "neftekhimik",
    "nizhnekamsk",
    "admiral",
    "vladivostok",
    "sochi",
    "mytishchi",
    "khimik",
    "ugra",
    "novokuznetsk",
    "lada togliatti",
    "kuban",
)
"""KHL clubs in Russia by name, for roster rows where Wikipedia gives no club country
(2010-2012)."""

GENERIC_TOKENS = frozenset(
    {
        "hc",
        "hk",
        "ec",
        "sc",
        "ev",
        "if",
        "ehc",
        "ik",
        "the",
        "ice",
        "hockey",
        "club",
        "team",
        "fc",
        "ks",
        "ssk",
        "kho",
        "ek",
        "sk",
    }
)


def tokens(name: object) -> set[str]:
    f = fold_name(name) or ""
    return {t for t in f.replace("-", " ").split() if t not in GENERIC_TOKENS and len(t) > 1}


def category(league: str | None, nation: str) -> str:
    if league is None:
        return "unknown"
    if league == "KHL":
        return "khl"
    if league in common.LEAGUES:
        r = common.rung(league, nation)
        return r if r in ("1", "2", "home") else "other"
    return "other"


def is_khl_club(club: object, country: object, year: int) -> bool:
    if isinstance(country, str) and country == "Russia":
        return True
    f = fold_name(club) or ""
    if (
        not isinstance(country, str)
        and year >= 2009
        and any(frag in f for frag in RUSSIAN_KHL_FRAGMENTS)
    ):
        return True
    return any(frag in f and lo <= year <= hi for frag, lo, hi in KHL_CLUBS)


def classify(
    row: pd.Series,
    person_stints: pd.DataFrame,
    careers: pd.DataFrame,
    season_teams: dict[str, list[tuple[str, set[str]]]],
) -> tuple[str | None, str]:
    """(league, basis) for one roster row."""
    text = row.get("club_league")
    if isinstance(text, str) and text:
        return CLUB_LEAGUE_TEXT.get(text, text), "club_league"
    year = int(row["year"])
    if is_khl_club(row.get("club"), row.get("club_country"), year):
        return "KHL", "khl_club"
    club_tok = tokens(row.get("club"))
    if len(careers):
        c = careers.assign(overlap=[len(club_tok & tokens(t)) for t in careers["team"]])
        c = c[c["overlap"] > 0].sort_values(["overlap", "games_played"], ascending=False)
        if len(c):
            lg = c["league"].iloc[0]
            return CAREER_LEAGUE.get(lg, lg), "nhl_career"
    if len(person_stints):
        ps = person_stints
        country = row.get("club_country")
        if isinstance(country, str):
            ps = ps[[country in LEAGUE_COUNTRY.get(lg, set()) for lg in ps["league"]]]
        if len(ps):
            return ps.sort_values("games_played", ascending=False)["league"].iloc[0], "league_row"
    best, best_n = None, 0
    for lg, teams in season_teams.items():
        for _team, tt in teams:
            n = len(club_tok & tt)
            if n > best_n:
                best, best_n = lg, n
    if best:
        return best, "team_name"
    country = row.get("club_country")
    if isinstance(country, str) and country:
        return f"not covered ({country})", "club_country"
    return None, "unknown"


def run(lk: linking.Linked, rosters: pd.DataFrame, careers: pd.DataFrame) -> dict[str, Any]:
    r = rosters[(rosters["year"] >= FIRST_YEAR) & rosters["team_iso3"].isin(ISO3)].copy()
    r["key"] = r["player"].map(common.link_key)
    r["source_id"] = r["key"] + "|" + r["birth_date"].astype("string")
    ids = lk.identities
    ros_ids = ids[ids["league"] == "roster"][["source_id", "person_idx"]]
    r = r.merge(ros_ids, on="source_id", how="left")
    nhl_ids = ids[ids["league"] == "NHL"][["person_idx", "source_id"]].rename(
        columns={"source_id": "nhl_id"}
    )
    r = r.merge(nhl_ids.drop_duplicates("person_idx"), on="person_idx", how="left")

    st = lk.stints
    careers = careers.copy()
    careers["player_id"] = careers["player_id"].astype("string")
    season_teams: dict[int, dict[str, list[tuple[str, set[str]]]]] = {}
    for (y, lg), g in st[st["league"] != "NHL"].groupby(["season_start", "league"]):
        season_teams.setdefault(int(y), {})[lg] = [
            (t, tokens(t)) for t in g["team"].dropna().unique()
        ]

    leagues, bases = [], []
    for row in r.itertuples(index=False):
        rd = row._asdict()
        s0 = int(rd["year"]) - 1
        ps = (
            st[(st["person_idx"] == rd["person_idx"]) & (st["season_start"] == s0)]
            if pd.notna(rd["person_idx"])
            else st.iloc[0:0]
        )
        cr = (
            careers[(careers["player_id"] == rd["nhl_id"]) & (careers["season_start"] == s0)]
            if pd.notna(rd["nhl_id"])
            else careers.iloc[0:0]
        )
        lg, basis = classify(pd.Series(rd), ps, cr, season_teams.get(s0, {}))
        leagues.append(lg)
        bases.append(basis)
    r["league"] = leagues
    r["basis"] = bases
    r["category"] = [category(lg, n) for lg, n in zip(r["league"], r["team_iso3"], strict=True)]

    events = []
    for (ev, year, nat), g in r.groupby(["event", "year", "team_iso3"]):
        cnt = Counter(g["category"])
        n = len(g)
        events.append(
            {
                "event": ev,
                "year": int(year),
                "nation": nat,
                "players": n,
                "counts": {c: int(cnt.get(c, 0)) for c in CATEGORIES},
                "shares": {c: cnt.get(c, 0) / n for c in CATEGORIES},
            }
        )
    ev_df = pd.DataFrame(
        [{**{k: e[k] for k in ("event", "year", "nation")}, **e["shares"]} for e in events]
    )
    mean_shares = {
        c: {
            cat: float(ev_df[ev_df["nation"] == c][cat].mean())
            if (ev_df["nation"] == c).any()
            else None
            for cat in CATEGORIES
        }
        for c in ISO3
    }
    by_year_home = [
        {"event": e["event"], "year": e["year"], **e["counts"], "players": e["players"]}
        for e in sorted(events, key=lambda e: (e["year"], e["event"]))
        if e["nation"] == HOME
    ]

    home = r[r["team_iso3"] == HOME].sort_values(["year", "event", "position", "player"])
    players = [
        {
            "event": x.event,
            "year": int(x.year),
            "name": x.player,
            "position": x.position,
            "birth_date": x.birth_date,
            "club": x.club,
            "league": x.league,
            "category": x.category,
            "basis": x.basis,
        }
        for x in home.itertuples()
    ]
    return {
        "definitions": {
            "rosters": "English Wikipedia roster articles (CC BY-SA 4.0), World Championship and Olympics from 2010",
            "season": "the tournament year's season (year - 1 / year)",
            "categories": {
                "1": "NHL",
                "2": "SHL, Liiga, National League, DEL",
                "home": "Czech Extraliga (Czechia only)",
                "khl": "KHL (not covered by the atlas)",
                "other": "every other league, the AHL included",
                "unknown": "club could not be placed",
            },
            "rules": [
                "club_league",
                "khl_club",
                "nhl_career",
                "league_row",
                "team_name",
                "club_country",
            ],
        },
        "basis_counts": {k: int(v) for k, v in r["basis"].value_counts().items()},
        "linked_share": float(r["person_idx"].notna().mean()),
        "events": sorted(events, key=lambda e: (e["year"], e["event"], e["nation"])),
        "mean_shares": mean_shares,
        "home_by_event": by_year_home,
        "home_players": players,
    }


def main() -> None:
    lk = linking.linked()
    out = run(lk, lk.rosters, common.load("nhl_careers.parquet"))
    path = common.write_output(
        "q6_national_team.json", out, [*linking.SNAPSHOT_FILES, "nhl_careers.parquet"]
    )
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
