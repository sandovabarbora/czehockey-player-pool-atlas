"""Data contracts on the committed snapshot (data/snapshot/): fields, types, row counts per
season, nationality coverage. These run on a clean clone without fetching."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import snapshot
from src.fetch import eurostat, nhl
from src.nations import ISO3

SNAP = snapshot.SNAPSHOT_DIR


def _read(name: str) -> pd.DataFrame:
    path = SNAP / name
    if not path.exists():
        pytest.skip(f"{name} not in the snapshot yet")
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def skaters() -> pd.DataFrame:
    return _read(nhl.OUT_SKATERS)


@pytest.fixture(scope="module")
def goalies() -> pd.DataFrame:
    return _read(nhl.OUT_GOALIES)


@pytest.fixture(scope="module")
def careers() -> pd.DataFrame:
    return _read(nhl.OUT_CAREERS)


@pytest.fixture(scope="module")
def population() -> pd.DataFrame:
    return _read(eurostat.OUT_PARQUET)


# -- NHL ------------------------------------------------------------------------


def test_nhl_columns(skaters, goalies):
    assert list(skaters.columns) == nhl.SKATER_COLUMNS
    assert list(goalies.columns) == nhl.GOALIE_COLUMNS
    for df in (skaters, goalies):
        assert pd.api.types.is_integer_dtype(df["player_id"])
        assert pd.api.types.is_integer_dtype(df["games_played"])
        assert pd.api.types.is_string_dtype(df["nationality"])


def test_nhl_seasons_are_complete(skaters, goalies):
    expected = nhl.seasons()
    for df in (skaters, goalies):
        assert sorted(df["season_start"].unique()) == expected
        assert 2004 not in set(df["season_start"])


@pytest.mark.parametrize(("kind", "lo", "hi"), [("skaters", 700, 1100), ("goalies", 60, 130)])
def test_nhl_rows_per_season(request, kind, lo, hi):
    df = request.getfixturevalue(kind)
    counts = df.groupby("season_start").size()
    assert counts.between(lo, hi).all(), counts[~counts.between(lo, hi)].to_dict()


def test_nhl_one_row_per_player_and_season(skaters, goalies):
    for df in (skaters, goalies):
        assert not df.duplicated(["season_id", "player_id"]).any()
        assert (df["games_played"] > 0).all()


def test_nhl_positions(skaters, goalies):
    assert set(skaters["position"]) <= {"C", "L", "R", "D"}
    assert set(goalies["position"]) == {"G"}


def test_nhl_nationality_and_birth_date_coverage(skaters, goalies):
    for df in (skaters, goalies):
        assert df["nationality"].notna().mean() >= 0.99
        assert df["birth_date"].notna().mean() >= 0.99
        assert pd.to_datetime(df["birth_date"], errors="coerce").notna().mean() >= 0.99
    # present-day codes only: the NHL recodes Czechoslovak births
    assert "TCH" not in set(skaters["nationality"]) | set(goalies["nationality"])


def test_nhl_skater_toi_published_from_1997(skaters):
    share = skaters.groupby("season_start")["toi_per_game_s"].apply(lambda s: s.notna().mean())
    assert (share[share.index < nhl.SKATER_TOI_FROM] == 0).all()
    assert (share[share.index >= nhl.SKATER_TOI_FROM] >= 0.99).all()


def test_nhl_goalie_toi_every_season(goalies):
    assert goalies["toi_s"].notna().mean() >= 0.99


def test_nhl_compared_nations_are_present(skaters, goalies):
    players = pd.concat([skaters, goalies])
    per = (
        players[players["nationality"].isin(ISO3)]
        .groupby(["season_start", "nationality"])
        .size()
        .unstack(fill_value=0)
    )
    assert set(per.columns) == set(ISO3)
    assert (per["CZE"] >= 15).all()
    assert (per["FIN"] >= 10).all()
    assert (per["SWE"] >= 10).all()


def test_nhl_careers(careers, skaters, goalies):
    assert list(careers.columns) == nhl.CAREER_COLUMNS
    wanted = set(nhl.career_player_ids(skaters, goalies))
    have = set(careers["player_id"].astype(int))
    assert have <= wanted
    assert len(have) / len(wanted) >= 0.99
    # every fetched career contains the NHL seasons it was selected for
    nhl_rows = careers[careers["league"] == "NHL"]
    assert nhl_rows["player_id"].nunique() / len(have) >= 0.99
    assert not careers.duplicated(["player_id", "season_id", "sequence", "league", "team"]).any()


def test_nhl_coverage_report():
    path = SNAP / nhl.OUT_COVERAGE
    if not path.exists():
        pytest.skip("coverage not in the snapshot yet")
    cov = json.loads(path.read_text())
    seasons = [s["season"] for s in cov["seasons"]]
    assert seasons[0] == "1995/96" and seasons[-1] == "2025/26" and len(seasons) == 31
    assert [s for s in cov["seasons"] if s["cancelled"]] == [
        next(s for s in cov["seasons"] if s["season"] == "2004/05")
    ]


# -- Eurostat -------------------------------------------------------------------


def test_population_contract(population):
    assert list(population.columns) == eurostat.COLUMNS
    assert set(population["iso3"]) == set(ISO3)
    assert population["population"].notna().all()
    counts = population.groupby("iso3")["year"].agg(["min", "max", "size"])
    assert (
        (counts["min"] == 1995).all()
        and (counts["max"] == 2026).all()
        and (counts["size"] == 32).all()
    )
    assert not population.duplicated(["iso3", "year"]).any()
    assert (population["population"] > 1_000_000).all()
