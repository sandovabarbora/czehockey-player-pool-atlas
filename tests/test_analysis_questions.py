"""Questions 1 and 3-7 and the pool list on the hand-built fixture tables (season 2024/25)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.analysis import (
    common,
    linking,
    pool,
    q1_per_million,
    q3_cohort_gaps,
    q4_youth_ice_time,
    q5_abroad,
    q6_national_team,
    q7_goalkeepers,
)
from tests import analysis_fixtures as fx

SEASON = 2024


@pytest.fixture(scope="module")
def lk() -> linking.Linked:
    return linking.build(fx.tables())


@pytest.fixture(scope="module")
def pop() -> pd.DataFrame:
    return fx.population()


# -- common ---------------------------------------------------------------------------


def test_season_helpers() -> None:
    assert common.season_label(1999) == "1999/00"
    assert common.season_start("2025/26") == 2025
    assert common.season_age(2025, 2005) == 20
    assert common.age_band(20) == "≤21" and common.age_band(26) == "26–29"
    assert common.age_band(float("nan")) == "unknown"
    assert common.rung("NHL") == "1" and common.rung("DEL") == "2"
    assert common.rung("Extraliga", "CZE") == "home" and common.rung("Extraliga", "FIN") == "other"


def test_population_for_season_uses_second_year_and_falls_back() -> None:
    pop = pd.DataFrame({"iso3": ["CZE", "CZE"], "year": [2024, 2025], "population": [1.0, 2.0]})
    assert common.population_for_season(pop, "CZE", 2024) == 2.0
    assert common.population_for_season(pop, "CZE", 2030) == 2.0
    assert math.isnan(common.population_for_season(pop, "FIN", 2024))


def test_clean_makes_json_safe() -> None:
    assert common.clean({"a": float("nan"), "b": pd.NA, "c": 1.23456789}) == {
        "a": None,
        "b": None,
        "c": 1.234568,
    }


# -- Q1 -------------------------------------------------------------------------------


def test_q1_counts_once_per_person_with_best_rung(lk: linking.Linked) -> None:
    tab = q1_per_million.counts(lk.stints, common.TOP5, SEASON, SEASON)
    # Voráček (NHL + DEL), Novák (82 GP), Faksa, Vladař; the 10-game Novák does not qualify
    assert tab.at[SEASON, "CZE"] == 4
    assert tab.at[SEASON, "FIN"] == 3
    assert tab.at[SEASON, "CHE"] == 1
    assert tab.at[SEASON, "SVK"] == 1


def test_q1_headline_per_million_and_peer_median(lk: linking.Linked, pop: pd.DataFrame) -> None:
    h = q1_per_million.headline(lk.stints, pop, season=SEASON)
    cze = next(n for n in h["nations"] if n["iso3"] == "CZE")
    assert cze["top5_per_million"] == pytest.approx(0.4)
    assert cze["by_league"]["DEL"] == 1 and cze["by_league"]["NHL"] == 4
    # five of the nine fixture peers have nobody: the median is 0 and the ratio undefined
    assert h["peer_median"]["top5_per_million"] == 0
    assert h["home"]["top5_vs_peer_median"] is None
    assert h["home"]["rank_top5"] == 2  # behind Finland (0.6 per million)


def test_q1_coverage_flags_unidentified_rows(lk: linking.Linked) -> None:
    cov = q1_per_million.coverage(lk.stints, SEASON, SEASON)[0]
    assert cov["leagues"]["DEL"]["unidentified"] == 1  # "Nobody Known"
    assert cov["leagues"]["NL"]["unidentified"] == 1  # the ambiguous Novák
    assert cov["complete"] is False


# -- Q3 -------------------------------------------------------------------------------


def test_q3_gap_and_shortfall(lk: linking.Linked, pop: pd.DataFrame) -> None:
    per = q3_cohort_gaps.cohort_table(lk.stints, season=SEASON)
    cells = q3_cohort_gaps.gaps(per, pop, season=SEASON, dims=("position",))
    f = next(c for c in cells if c["position"] == "F")
    assert f["counts"]["CZE"] == 3  # Voráček, Novák, Faksa
    med = f["peer_median"]
    assert f["shortfall"] == pytest.approx((med - f["per_million"]["CZE"]) * 10.0)


def test_q3_peers_with_unknown_ages_leave_the_age_median(lk: linking.Linked) -> None:
    per = q3_cohort_gaps.cohort_table(lk.stints, season=SEASON)
    peers = q3_cohort_gaps.eligible_peers(per, ("age_band",))
    assert "CHE" not in peers  # the NL publishes no birth dates
    assert "FIN" in peers


def test_outputs_keep_enough_places_for_one_decimal_percent() -> None:
    # 0.079467 must read 7.9%, not 8.0% after a first rounding to 0.0795
    from src.web import fmt

    assert fmt.pct(common.clean(0.0794667)) == "7.9%"


# -- Q4 -------------------------------------------------------------------------------


def test_q4_u21_shares(lk: linking.Linked) -> None:
    s = q4_youth_ice_time.youth_rows(lk.stints)
    ex = q4_youth_ice_time.league_season(
        s[(s["league"] == "Extraliga") & (s["season_start"] == SEASON)], True
    )
    assert ex["u21_games_share"] == pytest.approx(40 / 199)
    assert ex["u21_toi_share"] == pytest.approx(24000 / (24000 + 4 * 45000))
    assert ex["measured"] is True
    de = q4_youth_ice_time.league_season(
        s[(s["league"] == "DEL") & (s["season_start"] == SEASON)], False
    )
    assert de["measured"] is False  # one of two DEL players has an age


def test_q4_keeps_skaters_without_a_position() -> None:
    stints = pd.DataFrame(
        {
            "league": ["SHL", "SHL", "SHL"],
            "position": pd.array(["F", pd.NA, "G"], dtype="string"),
            "season_start": [SEASON] * 3,
            "birth_year": [1990, SEASON - 19, 1990],
            "games_played": [50.0, 50.0, 50.0],
            "toi_s": [50000.0, 30000.0, 180000.0],
        }
    )
    s = q4_youth_ice_time.youth_rows(stints)
    assert len(s) == 2  # the goalkeeper goes, the skater with no position stays
    out = q4_youth_ice_time.league_season(s, True)
    assert out["u21_games_share"] == pytest.approx(0.5)


# -- Q5 -------------------------------------------------------------------------------


def test_q5_ratio_to_position_median(lk: linking.Linked) -> None:
    s = q5_abroad.with_ratios(lk.stints)
    fwd = s[(s["league"] == "NHL") & (s["position"] == "F")]
    ppg = sorted([30 / 70, 30 / 82, 30 / 70, 10 / 82])
    med = (ppg[1] + ppg[2]) / 2
    vor = fwd[fwd["key"] == "jakub voracek"].iloc[0]
    assert vor["median_ppg"] == pytest.approx(med)
    assert vor["ppg_ratio"] == pytest.approx((30 / 70) / med)
    assert vor["toi_ratio"] == pytest.approx(1.0)


# -- Q6 -------------------------------------------------------------------------------


EMPTY = pd.DataFrame(columns=["league", "team", "games_played"])


@pytest.mark.parametrize(
    "row,careers,stints,expected",
    [
        (
            {"club_league": "Kontinental Hockey League", "year": 2012},
            EMPTY,
            EMPTY,
            ("KHL", "club_league"),
        ),
        (
            {"club": "Avangard Omsk", "club_country": "Russia", "year": 2020},
            EMPTY,
            EMPTY,
            ("KHL", "khl_club"),
        ),
        (
            {"club": "Metallurg Magnitogorsk", "club_country": None, "year": 2011},
            EMPTY,
            EMPTY,
            ("KHL", "khl_club"),
        ),
        (
            {"club": "Jokerit", "club_country": "Finland", "year": 2012},
            EMPTY,
            EMPTY,
            ("not covered (Finland)", "club_country"),
        ),
        (
            {"club": "Toronto Marlies", "club_country": "Canada", "year": 2023},
            pd.DataFrame(
                {
                    "league": ["AHL", "NHL"],
                    "team": ["Toronto Marlies", "Toronto Maple Leafs"],
                    "games_played": [40, 10],
                }
            ),
            EMPTY,
            ("AHL", "nhl_career"),
        ),
        (
            {"club": "HC Plzeň", "club_country": "Czech Republic", "year": 2014},
            EMPTY,
            pd.DataFrame(
                {
                    "league": ["NHL", "Extraliga"],
                    "team": ["x", "HC Škoda Plzeň"],
                    "games_played": [60, 10],
                }
            ),
            ("Extraliga", "league_row"),
        ),
        ({"club": "Mystery", "club_country": None, "year": 2014}, EMPTY, EMPTY, (None, "unknown")),
    ],
)
def test_q6_classify_rules(row, careers, stints, expected) -> None:
    assert q6_national_team.classify(pd.Series(row), stints, careers, {}) == expected


def test_q6_team_name_rule() -> None:
    teams = {"Extraliga": [("HC Oceláři Třinec", q6_national_team.tokens("HC Oceláři Třinec"))]}
    row = pd.Series({"club": "Oceláři Třinec", "club_country": None, "year": 2015})
    assert q6_national_team.classify(row, EMPTY, EMPTY, teams) == ("Extraliga", "team_name")


def test_q6_run_on_fixture(lk: linking.Linked) -> None:
    careers = pd.DataFrame(columns=["player_id", "season_start", "league", "team", "games_played"])
    out = q6_national_team.run(lk, lk.rosters, careers)
    by_name = {p["name"]: p for p in out["home_players"]}
    assert by_name["Daniel Vladař"]["category"] == "1"
    assert by_name["Petr Young"]["category"] == "home"
    # a Czech club puts him in his Extraliga row, although he played more NHL games
    assert by_name["Jakub Voráček"]["category"] == "home"
    svk = next(e for e in out["events"] if e["nation"] == "SVK")
    assert svk["counts"]["khl"] == 1


# -- Q7 -------------------------------------------------------------------------------


def test_q7_save_pct_and_per_million(lk: linking.Linked) -> None:
    g = q7_goalkeepers.goalies(lk.stints)
    vl = g[g["key"] == "dan vladar"].iloc[0]
    assert vl["save_pct"] == pytest.approx(1000 / 1100)
    tab = q1_per_million.counts(g, common.TOP5, SEASON, SEASON)
    assert tab.at[SEASON, "CZE"] == 1 and tab.at[SEASON, "FIN"] == 1


# -- Pool -----------------------------------------------------------------------------


def test_pool_lists_every_czech_person_once(lk: linking.Linked) -> None:
    players = pool.build_pool(lk.stints, pool.roster_names(lk))
    names = {p["name"] for p in players}
    assert "Tomáš Hrnka" not in names and "Tomas Hrnka" not in names  # SVK by citizenship
    assert "Foreign Guy" not in names
    vor = next(p for p in players if p["name"] == "Jakub Voráček")
    assert vor["leagues"] == ["NHL", "DEL", "Extraliga"]
    assert [r["rung"] for r in vor["seasons"]] == ["1", "2", "home"]
    assert vor["latest"]["rung"] == "1"
    assert sum(p["name"].startswith("Karel Nov") for p in players) == 2
    vl = next(p for p in players if p["name"] == "Daniel Vladař")
    assert vl["seasons"][0]["save_pct"] == pytest.approx(1000 / 1100)
