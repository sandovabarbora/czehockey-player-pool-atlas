"""Data contracts on the committed Liiga, SHL and Extraliga snapshots: fields, types, row counts
per season, and the coverage the spec relies on. These run on a clean clone without fetching."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import snapshot
from src.fetch import extraliga, liiga, shl

SNAP = snapshot.SNAPSHOT_DIR
ALL_SEASONS = list(range(1995, 2026))


def _read(name: str) -> pd.DataFrame:
    path = SNAP / name
    if not path.exists():
        pytest.skip(f"{name} not in the snapshot yet")
    return pd.read_parquet(path)


def _coverage(name: str) -> dict:
    path = SNAP / name
    if not path.exists():
        pytest.skip(f"{name} not in the snapshot yet")
    return json.loads(path.read_text(encoding="utf-8"))


def _per_season_share(df: pd.DataFrame, col: str) -> pd.Series:
    return df.groupby("season_start")[col].apply(lambda s: s.notna().mean())


def _check_types(df: pd.DataFrame, module) -> None:
    for c in df.columns:
        if c in module.INT_COLUMNS:
            assert pd.api.types.is_integer_dtype(df[c]), c
        elif c in module.FLOAT_COLUMNS:
            assert pd.api.types.is_float_dtype(df[c]), c
        elif c in getattr(module, "BOOL_COLUMNS", set()):
            assert pd.api.types.is_bool_dtype(df[c]), c
        else:
            assert pd.api.types.is_string_dtype(df[c]), c


# -- Liiga --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def liiga_sk() -> pd.DataFrame:
    return _read(liiga.OUT_SKATERS)


@pytest.fixture(scope="module")
def liiga_go() -> pd.DataFrame:
    return _read(liiga.OUT_GOALIES)


def test_liiga_columns_and_types(liiga_sk, liiga_go):
    assert list(liiga_sk.columns) == liiga.SKATER_COLUMNS
    assert list(liiga_go.columns) == liiga.GOALIE_COLUMNS
    for df in (liiga_sk, liiga_go):
        _check_types(df, liiga)


def test_liiga_rows_per_season(liiga_sk, liiga_go):
    for df, lo, hi in ((liiga_sk, 280, 600), (liiga_go, 35, 90)):
        counts = df.groupby("season_start").size()
        assert counts.index.tolist() == ALL_SEASONS
        assert counts.between(lo, hi).all(), counts[~counts.between(lo, hi)].to_dict()


def test_liiga_keys_and_games(liiga_sk, liiga_go):
    for df in (liiga_sk, liiga_go):
        assert not df.duplicated(["season_start", "player_id", "team_id"]).any()
    assert (liiga_sk["games_played"] > 0).all()
    assert (liiga_go["games_dressed"] >= liiga_go["games_played"]).all()
    assert liiga_sk["position"].isin(["F", "D"]).mean() >= 0.999
    assert (liiga_go["position"] == "G").all()


def test_liiga_birth_date_and_nationality(liiga_sk, liiga_go):
    both = pd.concat([liiga_sk, liiga_go])
    assert pd.to_datetime(both["birth_date"], errors="coerce").notna().mean() >= 0.999
    assert (_per_season_share(both, "nationality") >= 0.94).all()
    assert both["is_u20"].notna().all()


def test_liiga_toi_from_2014(liiga_sk, liiga_go):
    share = _per_season_share(liiga_sk, "toi_s")
    assert (share[share.index < liiga.TOI_FROM] == 0).all()
    assert (share[share.index >= liiga.TOI_FROM] == 1).all()
    assert liiga_go["toi_s"].notna().all()


def test_liiga_coverage_report():
    cov = _coverage(liiga.OUT_COVERAGE)
    assert [s["season"] for s in cov["seasons"]] == [liiga.season_label(y) for y in ALL_SEASONS]
    assert cov["unmapped_nationality_codes"] == []
    assert all(s["nations"]["CZE"] >= 1 for s in cov["seasons"])


# -- SHL ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def shl_sk() -> pd.DataFrame:
    return _read(shl.OUT_SKATERS)


@pytest.fixture(scope="module")
def shl_go() -> pd.DataFrame:
    return _read(shl.OUT_GOALIES)


def test_shl_columns_and_types(shl_sk, shl_go):
    assert list(shl_sk.columns) == shl.SKATER_COLUMNS
    assert list(shl_go.columns) == shl.GOALIE_COLUMNS
    for df in (shl_sk, shl_go):
        _check_types(df, shl)


def test_shl_rows_per_season(shl_sk, shl_go):
    for df, lo, hi in ((shl_sk, 250, 500), (shl_go, 25, 50)):
        counts = df.groupby("season_start").size()
        assert counts.index.tolist() == ALL_SEASONS
        assert counts.between(lo, hi).all(), counts[~counts.between(lo, hi)].to_dict()


def test_shl_keys_games_positions(shl_sk, shl_go):
    for df in (shl_sk, shl_go):
        with_id = df[df["player_id"].notna()]
        assert not with_id.duplicated(["season_start", "player_id"]).any()
    assert (shl_sk["games_played"] > 0).all()
    assert set(shl_sk["position"].dropna()) <= {"F", "D"}
    assert (shl_go["position"] == "G").all()
    assert set(shl_go["source"]) <= {"goalkeepers_summary", "players_summary"}


def test_shl_personal_fields_from_2011(shl_sk, shl_go):
    """uuid, birth date and nationality are near-complete from 2011/12 (sparse before)."""
    both = pd.concat([shl_sk, shl_go])
    recent = both[both["season_start"] >= 2011]
    for col, floor in (("player_id", 0.93), ("birth_date", 0.93), ("nationality", 0.9)):
        share = _per_season_share(recent, col)
        assert (share >= floor).all(), (col, share[share < floor].to_dict())
    dates = both["birth_date"].dropna()
    assert pd.to_datetime(dates, errors="coerce").notna().all()


def test_shl_toi_from_2009(shl_sk, shl_go):
    share = _per_season_share(shl_sk, "toi_per_game_s")
    assert (share[share.index < shl.TOI_FROM] == 0).all()
    assert (share[share.index >= shl.TOI_FROM] >= 0.94).all()
    go = shl_go[shl_go["source"] == "goalkeepers_summary"]
    assert go["toi_s"].notna().mean() >= 0.99


def test_shl_coverage_report():
    cov = _coverage(shl.OUT_COVERAGE)
    assert [s["season"] for s in cov["seasons"]] == [shl.season_label(y) for y in ALL_SEASONS]
    assert cov["unmapped_nationality_codes"] == []


# -- Extraliga ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def ext_sk() -> pd.DataFrame:
    return _read(extraliga.OUT_SKATERS)


@pytest.fixture(scope="module")
def ext_go() -> pd.DataFrame:
    return _read(extraliga.OUT_GOALIES)


@pytest.fixture(scope="module")
def ext_profiles() -> pd.DataFrame:
    return _read(extraliga.OUT_PROFILES)


def test_extraliga_columns_and_types(ext_sk, ext_go, ext_profiles):
    assert list(ext_sk.columns) == extraliga.SKATER_COLUMNS
    assert list(ext_go.columns) == extraliga.GOALIE_COLUMNS
    assert list(ext_profiles.columns) == extraliga.PROFILE_COLUMNS
    for df in (ext_sk, ext_go):
        _check_types(df, extraliga)


def test_extraliga_rows_per_season(ext_sk, ext_go):
    for df, lo, hi in ((ext_sk, 300, 560), (ext_go, 25, 60)):
        counts = df.groupby("season_start").size()
        assert counts.index.tolist() == ALL_SEASONS
        assert counts.between(lo, hi).all(), counts[~counts.between(lo, hi)].to_dict()
    # one regular-season competition per season
    assert (ext_sk.groupby("season_start")["competition_id"].nunique() == 1).all()


def test_extraliga_keys_and_positions(ext_sk, ext_go):
    for df in (ext_sk, ext_go):
        assert not df.duplicated(["season_start", "player_id", "team"]).any()
    assert set(ext_sk["position"].dropna()) <= {"F", "D"}
    assert ext_sk["position"].notna().mean() >= 0.99
    assert (ext_go["position"] == "G").all()


def test_extraliga_flags(ext_sk, ext_go):
    both = pd.concat([ext_sk, ext_go])
    per = both.groupby("season_start")
    assert (per["is_u20"].sum() > 0).all()
    assert (per["is_foreign"].sum() > 0).all()
    # an under-20 flag always carries a birth year
    assert both.loc[both["is_u20"], "birth_year"].notna().all()


def test_extraliga_birth_dates_where_needed(ext_sk, ext_go):
    both = pd.concat([ext_sk, ext_go])
    needed = both[both["season_start"] >= extraliga.PROFILES_FROM]
    # a handful of profiles (13 of 1,801) show no birth date
    assert (_per_season_share(needed, "birth_date") >= 0.98).all()
    dates = pd.to_datetime(needed["birth_date"], errors="coerce")
    assert dates.notna().mean() >= 0.99
    assert (dates.dt.year == needed["birth_year"]).all()


def test_extraliga_toi_from_2013(ext_sk, ext_go):
    share = _per_season_share(ext_sk, "toi_s")
    assert (share[share.index < extraliga.TOI_FROM] == 0).all()
    assert (share[share.index >= extraliga.TOI_FROM] >= 0.99).all()
    assert ext_go["toi_s"].notna().mean() >= 0.99


def test_extraliga_coverage_report():
    cov = _coverage(extraliga.OUT_COVERAGE)
    assert [s["season"] for s in cov["seasons"]] == [extraliga.season_label(y) for y in ALL_SEASONS]
    assert all(s["foreign_flag"] for s in cov["seasons"])
