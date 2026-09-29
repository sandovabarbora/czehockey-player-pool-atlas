"""Linking and nationality (spec §4) on the hand-built fixture tables."""

from __future__ import annotations

import pandas as pd
import pytest

from src.analysis import common, linking
from tests import analysis_fixtures as fx


@pytest.fixture(scope="module")
def lk() -> linking.Linked:
    return linking.build(fx.tables())


def _rows(lk: linking.Linked, name_key: str, league: str | None = None) -> pd.DataFrame:
    s = lk.stints[lk.stints["key"] == name_key]
    return s if league is None else s[s["league"] == league]


def test_link_key_folds_diacritics_and_order() -> None:
    assert common.link_key("Jakub Voráček") == common.link_key("Voracek Jakub")
    assert common.link_key("Voráček, Jakub") == "jakub voracek"
    assert common.link_key("Jean-Pierre Dumont") == common.link_key("Jean Pierre Dumont")
    assert common.initial_key("Dan Vladař") == common.initial_key("Daniel Vladar") == "d vladar"


def test_name_and_birth_date_link_across_leagues(lk: linking.Linked) -> None:
    rows = _rows(lk, "jakub voracek")
    assert set(rows["league"]) == {"NHL", "Extraliga", "DEL"}
    assert rows["person_id"].nunique() == 1


def test_citizenship_outranks_eligibility(lk: linking.Linked) -> None:
    rows = _rows(lk, "hrnka tomas")
    assert set(rows["nationality"]) == {"SVK"}
    ex = rows[rows["league"] == "Extraliga"].iloc[0]
    assert ex["nat_value"] == "CZE"  # the Extraliga flag says not a foreigner
    assert ex["row_nat_basis"] == "linked: citizenship"
    person = lk.persons[lk.persons["person_id"] == ex["person_id"]].iloc[0]
    assert person["nat_conflict"]


def test_record_without_birth_date_links_on_unique_name(lk: linking.Linked) -> None:
    row = _rows(lk, "jakub voracek", "DEL").iloc[0]
    assert row["link_basis"] == "name_only"
    assert row["nationality"] == "CZE"
    assert row["row_nat_basis"] == "linked: citizenship"
    assert row["birth_year"] == 1989  # taken from the person


def test_name_shared_by_two_persons_is_ambiguous(lk: linking.Linked) -> None:
    row = _rows(lk, "karel novak", "NL").iloc[0]
    assert row["link_basis"] == "ambiguous"
    assert pd.isna(row["nationality"])


def test_unmatched_and_same_league_name(lk: linking.Linked) -> None:
    assert _rows(lk, "known nobody", "DEL").iloc[0]["link_basis"] == "unmatched"
    mm = _rows(lk, "max mustermann", "DEL")
    assert set(mm["link_basis"]) == {"same_league_name"}
    assert mm["person_id"].nunique() == 1
    assert set(mm["nationality"]) == {"DEU"}  # the 2022/23 licence carries back to 2019/20


def test_nl_licence_is_eligibility(lk: linking.Linked) -> None:
    row = _rows(lk, "hans muster", "NL").iloc[0]
    assert row["nationality"] == "CHE"
    assert row["row_nat_basis"] == "eligibility"


def test_extraliga_foreigner_has_no_code(lk: linking.Linked) -> None:
    assert pd.isna(_rows(lk, "foreign guy").iloc[0]["nationality"])


def test_first_name_variant_links_roster(lk: linking.Linked) -> None:
    ids = lk.identities
    roster = ids[(ids["league"] == "roster") & (ids["key"] == "daniel vladar")].iloc[0]
    nhl = ids[(ids["league"] == "NHL") & (ids["key"] == "dan vladar")].iloc[0]
    assert roster["person_idx"] == nhl["person_idx"]
    assert roster["link_basis"] == "dob_name_variant"


def test_roster_birth_date_swap_is_repaired_and_reported(lk: linking.Linked) -> None:
    swapped = lk.report["roster_birth_dates_swapped"]
    assert [s["player"] for s in swapped] == ["Radek Faksa"]
    ids = lk.identities
    faksa = ids[ids["key"] == "faksa radek"]
    assert faksa["person_idx"].nunique() == 1


def test_position_filled_from_person(lk: linking.Linked) -> None:
    row = _rows(lk, "erik svensson", "SHL").iloc[0]
    assert row["position"] == "D"


def test_del_regular_season_only_and_nl_average_row_dropped(lk: linking.Linked) -> None:
    assert _rows(lk, "only playoff").empty
    assert _rows(lk, "durchschnitt").empty


def test_thresholds_are_pro_rated(lk: linking.Linked) -> None:
    nhl = lk.stints[lk.stints["league"] == "NHL"]
    assert set(nhl["threshold"]) == {20}
    novak_10gp = nhl[(nhl["key"] == "karel novak") & (nhl["games_played"] == 10)].iloc[0]
    assert not novak_10gp["qualifies"]


def test_report_counts(lk: linking.Linked) -> None:
    rep = lk.report["records_by_league"]
    assert rep["DEL"]["without_birth_date"] == 4
    assert rep["DEL"]["name_only_linked"] == 1
    assert rep["NL"]["ambiguous"] == 1
    assert rep["roster"]["linked_on_first_name_variant"] == 1


@pytest.mark.parametrize(
    "schedule,expected", [(82, 20), (48, 12), (52, 13), (56, 14), (70, 17), (0, 1)]
)
def test_games_threshold(schedule: int, expected: int) -> None:
    assert common.games_threshold(schedule) == expected


def test_twins_in_one_league_are_not_merged_as_name_variants() -> None:
    ids = pd.DataFrame(
        {
            "league": ["Extraliga", "Extraliga", "NHL", "Liiga"],
            "source_id": ["1", "2", "3", "4"],
            "key": ["kevin klima", "kelly klima", "dan vladar", "daniel vladar"],
            "key_initial": ["k klima", "k klima", "d vladar", "d vladar"],
            "birth_date": ["1997-06-05", "1997-06-05", "1997-08-20", "1997-08-20"],
            "birth_year": [1997.0, 1997.0, 1997.0, 1997.0],
            "first": [2018, 2019, 2020, 2016],
            "last": [2025, 2025, 2025, 2018],
            "rows": [8, 7, 6, 3],
            "roster_nat": [pd.NA] * 4,
        }
    )
    out = linking.link(ids)
    assert out.at[0, "person_idx"] != out.at[1, "person_idx"]  # twins, both in the Extraliga
    assert out.at[2, "person_idx"] == out.at[3, "person_idx"]  # Dan / Daniel still link
    assert out.at[3, "link_basis"] == "dob_name_variant"
