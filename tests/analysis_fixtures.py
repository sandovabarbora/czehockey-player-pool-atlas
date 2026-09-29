"""Small hand-built source tables for the analysis tests: a few players per league, with the
same columns the snapshot tables have, so `linking.build` runs end to end in milliseconds.

Cast (2024/25 = season_start 2024 unless noted):
- Jakub Voráček (CZE, 1989-08-15): NHL (ASCII name), Extraliga (with DOB), DEL (no DOB)
- Tomáš Hrnka: Extraliga not-foreign, NHL code SVK -> SVK by citizenship
- Karel Novak: two NHL players with the same name and different DOBs -> an NL row is ambiguous
- Dan / Daniel Vladař (1997-08-20): NHL goalie 'Dan', roster 'Daniel'
- Radek Faksa: roster birth date with day and month swapped
- Mikko Koivu (FIN): Liiga
- Hans Muster (CHE): NL Swiss licence only
- Max Mustermann: DEL archive (2019) and current (2022, Nat GER) ids -> joined within the league
- Petr Young (CZE, 2006): Extraliga under-21
- Erik Svensson (SWE): SHL, position missing, filled from his NHL record
"""

from __future__ import annotations

import pandas as pd


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def nhl_skaters() -> pd.DataFrame:
    base = dict(
        season="2024/25",
        season_start=2024,
        teams="PHI",
        goals=10,
        assists=20,
        points=30,
        toi_per_game_s=1000.0,
    )
    return _df(
        [
            {
                **base,
                "player_id": 1,
                "full_name": "Jakub Voracek",
                "birth_date": "1989-08-15",
                "nationality": "CZE",
                "position": "R",
                "games_played": 70,
            },
            {
                **base,
                "player_id": 2,
                "full_name": "Tomas Hrnka",
                "birth_date": "1990-01-01",
                "nationality": "SVK",
                "position": "D",
                "games_played": 25,
            },
            {
                **base,
                "player_id": 3,
                "full_name": "Karel Novak",
                "birth_date": "1995-03-03",
                "nationality": "CZE",
                "position": "C",
                "games_played": 82,
            },
            {
                **base,
                "player_id": 4,
                "full_name": "Karel Novak",
                "birth_date": "1996-04-04",
                "nationality": "CZE",
                "position": "C",
                "games_played": 10,
            },
            {
                **base,
                "player_id": 5,
                "full_name": "Erik Svensson",
                "birth_date": "2000-02-02",
                "nationality": "SWE",
                "position": "D",
                "games_played": 82,
                "points": 50,
            },
            {
                **base,
                "player_id": 8,
                "full_name": "Radek Faksa",
                "birth_date": "1994-01-09",
                "nationality": "CZE",
                "position": "C",
                "games_played": 70,
            },
            {
                **base,
                "player_id": 6,
                "full_name": "Filler One",
                "birth_date": "1990-05-05",
                "nationality": "CAN",
                "position": "L",
                "games_played": 82,
                "points": 10,
            },
        ]
    )


def nhl_goalies() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2024/25",
                "season_start": 2024,
                "player_id": 7,
                "full_name": "Dan Vladar",
                "birth_date": "1997-08-20",
                "nationality": "CZE",
                "teams": "PHI",
                "games_played": 40,
                "toi_s": 140000.0,
                "saves": 1000,
                "goals_against": 100,
            },
        ]
    )


def liiga_skaters() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2024/25",
                "season_start": 2024,
                "player_id": 100,
                "full_name": "Mikko Koivu",
                "birth_date": "1998-03-12",
                "nationality": "FIN",
                "team": "HIFK",
                "position": "F",
                "games_played": 60,
                "goals": 20,
                "assists": 20,
                "points": 40,
                "toi_s": 60000,
            },
            {
                "season": "2024/25",
                "season_start": 2024,
                "player_id": 101,
                "full_name": "Onni Nuori",
                "birth_date": "2005-01-01",
                "nationality": "FIN",
                "team": "HIFK",
                "position": "F",
                "games_played": 30,
                "goals": 2,
                "assists": 2,
                "points": 4,
                "toi_s": 15000,
            },
        ]
    )


def liiga_goalies() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2024/25",
                "season_start": 2024,
                "player_id": 102,
                "full_name": "Veikko Maali",
                "birth_date": "1995-01-01",
                "nationality": "FIN",
                "team": "HIFK",
                "position": "G",
                "games_played": 50,
                "toi_s": 180000,
                "saves": 1200,
                "goals_against": 110,
            },
        ]
    )


def shl_skaters() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2023/24",
                "season_start": 2023,
                "player_id": "uuid-5",
                "legacy_id": None,
                "full_name": "Erik Svensson",
                "birth_date": "2000-02-02",
                "nationality": "SWE",
                "team": "FBK",
                "position": None,
                "games_played": 52,
                "goals": 5,
                "assists": 10,
                "points": 15,
                "toi_s": 52 * 1100,
            },
        ]
    )


def shl_goalies() -> pd.DataFrame:
    return _df(
        [],
    ).reindex(
        columns=[
            "season",
            "season_start",
            "player_id",
            "legacy_id",
            "full_name",
            "birth_date",
            "nationality",
            "team",
            "position",
            "games_played",
            "toi_s",
            "saves",
            "goals_against",
        ]
    )


def extraliga_skaters() -> pd.DataFrame:
    base = dict(
        season="2024/25",
        season_start=2024,
        team="HC Sparta Praha",
        goals=1,
        assists=1,
        points=2,
        toi_s=50 * 900,
    )
    return _df(
        [
            {
                **base,
                "player_id": 10,
                "full_name": "Jakub Voráček",
                "birth_date": "1989-08-15",
                "birth_year": 1989,
                "position": "F",
                "is_foreign": False,
                "games_played": 5,
            },
            {
                **base,
                "player_id": 11,
                "full_name": "Tomáš Hrnka",
                "birth_date": "1990-01-01",
                "birth_year": 1990,
                "position": "D",
                "is_foreign": False,
                "games_played": 50,
            },
            {
                **base,
                "player_id": 12,
                "full_name": "Petr Young",
                "birth_date": "2006-06-06",
                "birth_year": 2006,
                "position": "F",
                "is_foreign": False,
                "games_played": 40,
                "toi_s": 40 * 600,
            },
            {
                **base,
                "player_id": 13,
                "full_name": "Old Veteran",
                "birth_date": "1985-01-01",
                "birth_year": 1985,
                "position": "F",
                "is_foreign": False,
                "games_played": 52,
            },
            {
                **base,
                "player_id": 14,
                "full_name": "Foreign Guy",
                "birth_date": "1992-01-01",
                "birth_year": 1992,
                "position": "F",
                "is_foreign": True,
                "games_played": 52,
            },
        ]
    )


def extraliga_goalies() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2024/25",
                "season_start": 2024,
                "player_id": 15,
                "full_name": "Josef Brankar",
                "birth_date": "2003-03-03",
                "birth_year": 2003,
                "team": "HC Sparta Praha",
                "position": "G",
                "is_foreign": False,
                "games_played": 30,
                "toi_s": 108000,
                "saves": 800,
                "goals_against": 80,
            },
        ]
    )


def del_skaters() -> pd.DataFrame:
    base = dict(
        phase="hauptrunde",
        team="Adler Mannheim",
        goals=1,
        assists=1,
        points=2,
        toi_s=None,
        nat_raw=None,
        nationality=None,
        position="F",
    )
    return _df(
        [
            {
                **base,
                "season": "2024/25",
                "season_start": 2024,
                "id_scheme": "current",
                "player_id": 1,
                "full_name": "Jakub Voracek",
                "games_played": 52,
            },
            {
                **base,
                "season": "2019/20",
                "season_start": 2019,
                "id_scheme": "archive",
                "player_id": 2,
                "full_name": "Max Mustermann",
                "games_played": 52,
            },
            {
                **base,
                "season": "2022/23",
                "season_start": 2022,
                "id_scheme": "current",
                "player_id": 3,
                "full_name": "Max Mustermann",
                "games_played": 52,
                "nat_raw": "GER",
                "nationality": "DEU",
            },
            {
                **base,
                "season": "2024/25",
                "season_start": 2024,
                "id_scheme": "current",
                "player_id": 4,
                "full_name": "Nobody Known",
                "games_played": 52,
            },
            {
                **base,
                "season": "2024/25",
                "season_start": 2024,
                "id_scheme": "current",
                "player_id": 5,
                "full_name": "Playoff Only",
                "games_played": 10,
                "phase": "playoffs",
            },
        ]
    )


def del_goalies() -> pd.DataFrame:
    return _df([]).reindex(
        columns=[
            "season",
            "season_start",
            "phase",
            "id_scheme",
            "player_id",
            "full_name",
            "team",
            "position",
            "nat_raw",
            "nationality",
            "games_played",
            "toi_s",
            "saves",
            "goals_against",
        ]
    )


def nl_skaters() -> pd.DataFrame:
    base = dict(
        season="2024/25",
        season_start=2024,
        team="ZSC Lions",
        position="F",
        goals=1,
        assists=1,
        points=2,
    )
    return _df(
        [
            {**base, "full_name": "Hans Muster", "licence": "CH", "games_played": 52},
            {**base, "full_name": "Karel Novak", "licence": "foreign", "games_played": 52},
        ]
    )


def nl_goalies() -> pd.DataFrame:
    return _df(
        [
            {
                "season": "2024/25",
                "season_start": 2024,
                "full_name": "Durchschnitt",
                "team_id": 100000,
                "team": "Durchschnitt",
                "position": "G",
                "games_played": 50,
                "toi_s": 1,
                "goals_against": 1,
            },
        ]
    )


def rosters() -> pd.DataFrame:
    base = dict(event="WC", year=2025, club_league=None, captaincy=None)
    return _df(
        [
            # 'Daniel' on the roster, 'Dan' in the NHL: same birth date
            {
                **base,
                "player": "Daniel Vladař",
                "birth_date": "1997-08-20",
                "team_iso3": "CZE",
                "position": "G",
                "club": "Philadelphia Flyers",
                "club_country": "United States",
            },
            {
                **base,
                "player": "Jakub Voráček",
                "birth_date": "1989-08-15",
                "team_iso3": "CZE",
                "position": "F",
                "club": "HC Sparta Praha",
                "club_country": "Czech Republic",
            },
            {
                **base,
                "player": "Tomáš Hrnka",
                "birth_date": "1990-01-01",
                "team_iso3": "SVK",
                "position": "D",
                "club": "Metallurg Magnitogorsk",
                "club_country": None,
            },
            # day and month swapped relative to the NHL record (1994-01-09)
            {
                **base,
                "player": "Radek Faksa",
                "birth_date": "1994-09-01",
                "team_iso3": "CZE",
                "position": "F",
                "club": "Dallas Stars",
                "club_country": "United States",
            },
            {
                **base,
                "player": "Petr Young",
                "birth_date": "2006-06-06",
                "team_iso3": "CZE",
                "position": "F",
                "club": "Mystery Club",
                "club_country": None,
            },
        ]
    )


def tables() -> dict[str, pd.DataFrame]:
    return {
        "nhl_skaters": nhl_skaters(),
        "nhl_goalies": nhl_goalies(),
        "liiga_skaters": liiga_skaters(),
        "liiga_goalies": liiga_goalies(),
        "shl_skaters": shl_skaters(),
        "shl_goalies": shl_goalies(),
        "extraliga_skaters": extraliga_skaters(),
        "extraliga_goalies": extraliga_goalies(),
        "del_skaters": del_skaters(),
        "del_goalies": del_goalies(),
        "nl_skaters": nl_skaters(),
        "nl_goalies": nl_goalies(),
        "rosters": rosters(),
    }


def population() -> pd.DataFrame:
    rows = []
    for iso3, pop in {
        "CZE": 10_000_000,
        "FIN": 5_000_000,
        "SWE": 10_000_000,
        "CHE": 9_000_000,
        "SVK": 5_000_000,
        "DEU": 80_000_000,
        "LVA": 2_000_000,
        "DNK": 6_000_000,
        "NOR": 5_000_000,
        "AUT": 9_000_000,
    }.items():
        for y in range(1995, 2027):
            rows.append({"iso3": iso3, "year": y, "population": float(pop)})
    return pd.DataFrame(rows)
