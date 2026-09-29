"""DEL fetcher: parsers on trimmed saved pages (no network) and the snapshot contract."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import config, snapshot
from src.fetch import del_
from src.nations import ISO3


def page(fixtures_dir, name: str) -> str:
    return (fixtures_dir / "del" / name).read_text(encoding="utf-8")


def test_urls_and_labels():
    assert del_.season_label(1999) == "1999/00"
    assert del_.current_url(2025, "playerstats/toi").endswith(
        "/statistik/saison-2025-26/hauptrunde/playerstats/toi"
    )
    assert del_.archive_url(1996, "topscorer", "meisterrunde").endswith(
        "/statistik/archiv/saison_1996-1997_meisterrunde/topscorer"
    )


@pytest.mark.parametrize(
    ("text", "secs"), [("2448:39", 146919), ("21:23:48", 77028), ("", None), ("-", None)]
)
def test_clock_to_s(text, secs):
    assert del_.clock_to_s(text) == secs


def test_current_id_pattern_takes_slugged_and_bare_links():
    for href, pid in [
        ("/statistik/spielerdetails/hauptrunde-2425/ty_ronning-2209/details", 2209),
        ("/statistik/spielerdetails/hauptrunde-2425/3541/details", 3541),
    ]:
        assert int(del_.CURRENT_ID_RE.search(href).group(1)) == pid


def test_team_names_read_svg_and_png_logos(fixtures_dir):
    teams = del_.team_names(page(fixtures_dir, "current_tabelle.html"))
    assert teams["team_11"] == "Kölner Haie"
    assert "team_1" in teams  # a .png logo (csm_team_1_<hash>.png)
    assert len(teams) == 14


def test_build_current_season(fixtures_dir):
    sk, go = del_.build_current_season(
        page(fixtures_dir, "current_basis.html"),
        page(fixtures_dir, "current_toi.html"),
        page(fixtures_dir, "current_goalies.html"),
        2025,
        page(fixtures_dir, "current_tabelle.html"),
    )
    assert list(sk.columns) == del_.SKATER_COLUMNS
    assert list(go.columns) == del_.GOALIE_COLUMNS
    # the goalie listed on the skater page is dropped there
    assert set(sk["position"]) <= {"F", "D"} and len(sk) == 3
    assert set(go["position"]) == {"G"} and len(go) == 3
    assert not sk["team"].str.startswith("team_").any()
    barratt = sk.set_index("player_id").loc[2387]
    assert barratt["full_name"] == "Evan Barratt" and barratt["last_name"] == "Barratt"
    assert barratt["name_key"] == "evan barratt"
    assert barratt["toi_s"] > 0 and barratt["toi_per_game_s"] == pytest.approx(
        barratt["toi_s"] / barratt["games_played"]
    )
    assert (sk["season"] == "2025/26").all() and (sk["phase"] == "hauptrunde").all()
    # Nat is mapped to ISO alpha-3 (GER -> DEU), raw kept
    both = pd.concat([sk, go])
    assert both["nat_raw"].notna().all()
    assert not set(both["nationality"]) & {"GER", "SUI", "LAT", "DEN"}


def test_build_current_season_refuses_unnamed_teams(fixtures_dir):
    with pytest.raises(ValueError, match="no team name"):
        del_.build_current_season(
            page(fixtures_dir, "current_basis.html"),
            page(fixtures_dir, "current_toi.html"),
            page(fixtures_dir, "current_goalies.html"),
            2025,
            "",  # without the standings page team_1 has no name
        )


def test_build_archive_season(fixtures_dir):
    sk, go = del_.build_archive_season(
        page(fixtures_dir, "archive_topscorer.html"),
        page(fixtures_dir, "archive_topgoalies.html"),
        1995,
    )
    assert len(sk) == 4 and len(go) == 3
    first = sk.iloc[0]
    assert first["full_name"] == "Robert Reichel"  # "(#26)" stripped
    assert first["team"] == "Frankfurt Lions"
    # archive columns: Sp. = games, GP = points
    assert (first["games_played"], first["goals"], first["assists"], first["points"]) == (
        46,
        47,
        54,
        101,
    )
    assert sk["nationality"].isna().all() and sk["toi_s"].isna().all()
    assert go["toi_s"].notna().all()
    assert go[["wins", "losses", "shutouts", "goals_against", "saves"]].isna().all().all()


def test_header_change_is_an_error(fixtures_dir):
    html = page(fixtures_dir, "archive_topscorer.html").replace(">Sp.<", ">Games<")
    with pytest.raises(ValueError, match="header changed"):
        del_.parse_archive(html, "skaters")


class FixtureClient:
    """Serves the trimmed 2025/26 pages for one current season."""

    def __init__(self, fixtures_dir):
        self.dir = fixtures_dir / "del"
        self.network_calls = 0

    def get_text(self, url, key, params=None):
        name = {
            "playerstats_basis": "current_basis.html",
            "playerstats_toi": "current_toi.html",
            "goaliestats_basis": "current_goalies.html",
            "tabelle": "current_tabelle.html",
        }[key.split("_", 2)[2].removesuffix(".html")]
        return (self.dir / name).read_text(encoding="utf-8")


def test_run_writes_contract_tables(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshot")
    written = del_.run(2025, 2025, client=FixtureClient(fixtures_dir))
    assert {p.name for p in written} == {del_.OUT_SKATERS, del_.OUT_GOALIES, del_.OUT_COVERAGE}
    sk = pd.read_parquet(tmp_path / "snapshot" / del_.OUT_SKATERS)
    assert pd.api.types.is_integer_dtype(sk["player_id"]) and pd.api.types.is_string_dtype(
        sk["team"]
    )
    cov = json.loads((tmp_path / "snapshot" / del_.OUT_COVERAGE).read_text())
    assert cov["seasons"][0]["season"] == "2025/26" and cov["seasons"][0]["skaters"] == 3
    assert snapshot.verify(tmp_path / "snapshot") == []


# -- contract on the committed snapshot --------------------------------------------------


def _snap(name: str) -> pd.DataFrame:
    path = snapshot.SNAPSHOT_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not in the snapshot yet")
    return pd.read_parquet(path)


@pytest.fixture(scope="module")
def del_skaters() -> pd.DataFrame:
    return _snap(del_.OUT_SKATERS)


@pytest.fixture(scope="module")
def del_goalies() -> pd.DataFrame:
    return _snap(del_.OUT_GOALIES)


def test_snapshot_columns_and_types(del_skaters, del_goalies):
    assert list(del_skaters.columns) == del_.SKATER_COLUMNS
    assert list(del_goalies.columns) == del_.GOALIE_COLUMNS
    for df in (del_skaters, del_goalies):
        for c in ("player_id", "season_start", "games_played"):
            assert pd.api.types.is_integer_dtype(df[c]), c
        assert pd.api.types.is_string_dtype(df["nationality"])
        assert df["team"].notna().all() and not df["team"].str.startswith("team_").any()
        assert df["full_name"].notna().all() and df["name_key"].notna().all()


def test_snapshot_seasons_and_rows(del_skaters, del_goalies):
    seasons = list(range(del_.FIRST_SEASON, del_.LAST_SEASON + 1))
    for df in (del_skaters, del_goalies):
        assert sorted(df["season_start"].unique()) == seasons
    main = del_skaters[del_skaters["phase"] == "hauptrunde"].groupby("season_start").size()
    assert main.between(300, 450).all(), main.to_dict()
    go = del_goalies[del_goalies["phase"] == "hauptrunde"].groupby("season_start").size()
    assert go.between(25, 60).all(), go.to_dict()
    teams = (
        del_skaters[del_skaters["phase"] == "hauptrunde"].groupby("season_start")["team"].nunique()
    )
    assert teams.between(12, 18).all(), teams.to_dict()
    split = del_skaters[del_skaters["phase"] != "hauptrunde"]
    assert set(split["season_start"]) == set(del_.EXTRA_PHASES)


def test_snapshot_keys_are_unique(del_skaters, del_goalies):
    for df in (del_skaters, del_goalies):
        assert not df.duplicated(["season_start", "phase", "id_scheme", "player_id", "team"]).any()
        assert (df["games_played"] >= 0).all()


def test_snapshot_nationality_and_toi_from_2022(del_skaters, del_goalies):
    for df in (del_skaters, del_goalies):
        current = df["season_start"] >= del_.CURRENT_FROM
        assert df.loc[current, "nationality"].notna().all()
        assert df.loc[~current, "nationality"].isna().all()
        assert df.loc[current, "nationality"].str.fullmatch(r"[A-Z]{3}").all()
    assert "DEU" in set(del_skaters["nationality"]) & set(ISO3)
    current = del_skaters["season_start"] >= del_.CURRENT_FROM
    assert del_skaters.loc[current, "toi_s"].notna().mean() >= 0.99
    assert del_skaters.loc[~current, "toi_s"].isna().all()
    assert (del_skaters.loc[current, "nationality"] == "DEU").mean() > 0.5


def test_snapshot_positions(del_skaters, del_goalies):
    assert set(del_skaters["position"]) == {"F", "D"}
    assert set(del_goalies["position"]) == {"G"}


def test_snapshot_coverage_report():
    path = snapshot.SNAPSHOT_DIR / del_.OUT_COVERAGE
    if not path.exists():
        pytest.skip("coverage not in the snapshot yet")
    cov = json.loads(path.read_text())
    seasons = [s["season"] for s in cov["seasons"]]
    assert seasons[0] == "1995/96" and seasons[-1] == "2025/26" and len(seasons) == 31
