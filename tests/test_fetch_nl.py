"""Swiss NL fetcher: parsers on trimmed saved API responses (no network) and the snapshot contract."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import config, snapshot
from src.fetch import nl


def load(fixtures_dir, name: str) -> dict:
    return json.loads((fixtures_dir / "nl" / name).read_text(encoding="utf-8"))


def test_params_name_every_filter_they_set():
    p = nl.params("player", 2009, "153", foreign=True)
    assert p["searchQuery"] == "1//1"
    assert p["filterBy"] == "Season,Phase,Licence"
    assert p["filterQuery"] == "2010/153/1"  # season value is the end year
    probe = nl.params("goalkeeper", 2025)
    assert (probe["filterBy"], probe["filterQuery"]) == ("Season,Phase", "2026/")


def test_regular_phase_is_read_from_the_phase_filter(fixtures_dir):
    assert nl.regular_phase(load(fixtures_dir, "phases_2010.json")) == "153"
    with pytest.raises(ValueError):
        nl.regular_phase(
            {"filters": [{"alias": "Phase", "entries": [{"name": "Playoff Final", "alias": "1"}]}]}
        )


def test_check_response_refuses_the_default_season(fixtures_dir):
    payload = load(fixtures_dir, "player_2010.json")
    nl.check_response(payload, 2009, "153", foreign=False)
    with pytest.raises(ValueError, match="season"):
        nl.check_response(payload, 2024, "153", foreign=False)
    with pytest.raises(ValueError, match="licence"):
        nl.check_response(payload, 2009, "153", foreign=True)


def test_names_are_turned_round():
    n = nl._names("Du Bois Félicien")
    assert n["full_name"] == "Félicien Du Bois"
    assert n["name_key"] == "felicien du bois"
    assert n["name_tokens"] == "bois du felicien"


def test_build_season_skaters_marks_foreign_licences(fixtures_dir):
    df = nl.build_season(
        load(fixtures_dir, "player_2010.json"),
        load(fixtures_dir, "player_foreign_2010.json"),
        "skaters",
        2009,
        "153",
    )
    assert list(df.columns) == nl.SKATER_COLUMNS
    assert (df["licence"] == "foreign").sum() == 2
    assert set(df["licence"]) == {"CH", "foreign"}
    assert set(df["position"]) <= {"F", "D"}
    assert (df["season"] == "2009/10").all()
    assert df["team"].notna().all() and df["team_id"].notna().all()


def test_empty_result_marker_parses_to_no_rows(fixtures_dir):
    assert nl.parse_rows(load(fixtures_dir, "goalkeeper_foreign_empty.json"), "goalies").empty


def test_build_season_goalies_licence_unknown(fixtures_dir):
    df = nl.build_season(load(fixtures_dir, "goalkeeper_2010.json"), None, "goalies", 2009, "153")
    assert list(df.columns) == nl.GOALIE_COLUMNS
    assert df["licence"].isna().all() and (df["position"] == "G").all()
    assert df["toi_s"].notna().all() and (df["toi_s"] > 0).all()
    # 2009/10 publishes shots against and saves as 0 for everyone: unknown
    assert df["shots_against"].isna().all() and df["saves"].isna().all()


def test_foreign_rows_missing_from_the_full_list_are_an_error(fixtures_dir):
    everyone = load(fixtures_dir, "player_2010.json")
    everyone["data"] = everyone["data"][:1]
    with pytest.raises(ValueError, match="not in the full list"):
        nl.build_season(
            everyone, load(fixtures_dir, "player_foreign_2010.json"), "skaters", 2009, "153"
        )


class FixtureClient:
    def __init__(self, fixtures_dir):
        self.dir = fixtures_dir / "nl"
        self.network_calls = 0

    def get_json(self, url, key, params=None):
        name = {
            "2010_phases.json": "phases_2010.json",
            "2010_153_player.json": "player_2010.json",
            "2010_153_player_foreign.json": "player_foreign_2010.json",
            "2010_153_goalkeeper.json": "goalkeeper_2010.json",
        }[key]
        return json.loads((self.dir / name).read_text(encoding="utf-8"))


def test_run_writes_contract_tables(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshot")
    written = nl.run(2009, 2009, client=FixtureClient(fixtures_dir))
    assert {p.name for p in written} == {nl.OUT_SKATERS, nl.OUT_GOALIES, nl.OUT_COVERAGE}
    cov = json.loads((tmp_path / "snapshot" / nl.OUT_COVERAGE).read_text())
    assert cov["seasons"][0]["season"] == "2009/10" and cov["seasons"][0]["foreign_licence"] == 2
    assert snapshot.verify(tmp_path / "snapshot") == []


# -- contract on the committed snapshot --------------------------------------------------


def _snap(name: str) -> pd.DataFrame:
    path = snapshot.SNAPSHOT_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not in the snapshot yet")
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def nl_skaters() -> pd.DataFrame:
    return _snap(nl.OUT_SKATERS)


@pytest.fixture(scope="module")
def nl_goalies() -> pd.DataFrame:
    return _snap(nl.OUT_GOALIES)


def test_snapshot_columns_and_types(nl_skaters, nl_goalies):
    assert list(nl_skaters.columns) == nl.SKATER_COLUMNS
    assert list(nl_goalies.columns) == nl.GOALIE_COLUMNS
    for df in (nl_skaters, nl_goalies):
        for c in ("season_start", "team_id", "games_played"):
            assert pd.api.types.is_integer_dtype(df[c]), c
        assert df["name_key"].notna().all() and df["team"].notna().all()
    assert set(nl_skaters["licence"]) == {"CH", "foreign"}
    assert nl_goalies["licence"].isna().all()


def test_snapshot_seasons_and_rows(nl_skaters, nl_goalies):
    seasons = list(range(nl.FIRST_SEASON, nl.LAST_SEASON + 1))
    for df in (nl_skaters, nl_goalies):
        assert sorted(df["season_start"].unique()) == seasons
    sk = nl_skaters.groupby("season_start").size()
    assert sk.between(300, 460).all(), sk.to_dict()
    go = nl_goalies.groupby("season_start").size()
    assert go.between(20, 55).all(), go.to_dict()
    teams = nl_skaters.groupby("season_start")["team_id"].nunique()
    assert teams.between(12, 14).all(), teams.to_dict()


def test_snapshot_is_regular_season_only(nl_skaters):
    # a regular season is 50 or 52 games; playoffs or all phases would exceed it
    assert nl_skaters.groupby("season_start")["games_played"].max().between(44, 52).all()


def test_snapshot_keys_and_licences(nl_skaters, nl_goalies):
    for df in (nl_skaters, nl_goalies):
        assert not df.duplicated(["season_start", "name_raw", "team_id"]).any()
    share = nl_skaters.groupby("season_start")["licence"].apply(lambda s: (s == "foreign").mean())
    assert share.between(0.1, 0.35).all(), share.to_dict()
    assert set(nl_skaters["position"].dropna()) == {"F", "D"}
    assert nl_skaters["position"].isna().mean() < 0.01
    assert set(nl_goalies["position"]) == {"G"}
