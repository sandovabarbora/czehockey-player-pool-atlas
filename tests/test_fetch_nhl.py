"""NHL fetcher on saved responses (no network)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src import config, snapshot
from src.fetch import nhl


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "nhl" / name).read_text())


def test_season_helpers():
    assert nhl.season_id(1995) == 19951996
    assert nhl.season_label(1999) == "1999/00"
    s = nhl.seasons()
    assert s[0] == 1995 and s[-1] == 2025
    assert 2004 not in s
    assert len(s) == 30


def test_stats_params_filter_regular_season():
    p = nhl.stats_params(2024)
    assert p["limit"] == -1
    assert p["cayenneExp"] == "seasonId=20242025 and gameTypeId=2"


@pytest.mark.parametrize("kind", ["skater", "goalie"])
def test_build_season_joins_bios_and_summary(fixtures_dir, kind):
    bios = load(fixtures_dir, f"{kind}_bios_20242025.json")["data"]
    summary = load(fixtures_dir, f"{kind}_summary_20242025.json")["data"]
    df = nhl.build_season(kind, bios, summary, 2024)
    cols = nhl.SKATER_COLUMNS if kind == "skater" else nhl.GOALIE_COLUMNS
    assert list(df.columns) == cols
    assert len(df) == 4
    assert df["player_id"].is_unique
    assert (df["season"] == "2024/25").all()
    assert (df["nationality"] == "CZE").sum() == 2
    if kind == "goalie":
        assert (df["position"] == "G").all()
    # personal fields beyond public statistics are not carried
    assert not {"height", "weight", "birth_city"} & set(df.columns)


def test_build_season_rejects_mismatched_reports(fixtures_dir):
    bios = load(fixtures_dir, "skater_bios_20242025.json")["data"]
    summary = load(fixtures_dir, "skater_summary_20242025.json")["data"][:-1]
    with pytest.raises(ValueError, match="disagree"):
        nhl.build_season("skater", bios, summary, 2024)


def test_career_rows_keep_regular_season_in_every_league(fixtures_dir):
    landing = load(fixtures_dir, "landing_8477956.json")
    rows = nhl.career_rows(landing)
    assert rows and all(r["player_id"] == 8477956 for r in rows)
    leagues = {r["league"] for r in rows}
    assert {"NHL", "AHL"} <= leagues
    assert any(r["league"].startswith("Czech") or r["league"].startswith("CzR") for r in rows)
    raw_regular = [r for r in landing["seasonTotals"] if r["gameTypeId"] == 2]
    assert len(rows) == len(raw_regular)


class FixtureClient:
    """Serves the 2024/25 fixtures for every stats request and the one landing."""

    def __init__(self, fixtures_dir):
        self.dir = fixtures_dir / "nhl"
        self.network_calls = 0

    def get_json(self, url, key, params=None):
        self.network_calls += 1
        if "landing" in key:
            data = json.loads((self.dir / "landing_8477956.json").read_text())
            data["playerId"] = int(key.split("/")[1].split(".")[0])
            return data
        kind, report, _ = key.split("_")
        return json.loads((self.dir / f"{kind}_{report}_20242025.json").read_text())


def test_run_writes_contract_tables(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshot")
    written = nhl.run(2024, 2024, careers=True, client=FixtureClient(fixtures_dir))
    names = {p.name for p in written}
    assert names == {
        "nhl_skaters.parquet",
        "nhl_goalies.parquet",
        "nhl_careers.parquet",
        "nhl_coverage.json",
    }
    sk = pd.read_parquet(tmp_path / "snapshot" / "nhl_skaters.parquet")
    go = pd.read_parquet(tmp_path / "snapshot" / "nhl_goalies.parquet")
    ca = pd.read_parquet(tmp_path / "snapshot" / "nhl_careers.parquet")
    assert len(sk) == 4 and len(go) == 4
    # careers only for players of the ten nations: 2 CZE skaters, 2 CZE + LVA + SWE goalies
    assert ca["player_id"].nunique() == 6
    cov = json.loads((tmp_path / "snapshot" / "nhl_coverage.json").read_text())
    (season,) = cov["seasons"]
    assert season["season"] == "2024/25"
    assert season["nations"]["CZE"]["players"] == 4
    assert cov["careers"]["players_requested"] == 6
    assert snapshot.verify(tmp_path / "snapshot") == []


def test_coverage_marks_the_lockout_season():
    empty_sk = pd.DataFrame(columns=nhl.SKATER_COLUMNS)
    empty_go = pd.DataFrame(columns=nhl.GOALIE_COLUMNS)
    cov = nhl.coverage(empty_sk, empty_go, None, [2003, 2005])
    labels = [(s["season"], s["cancelled"]) for s in cov["seasons"]]
    assert labels == [("2003/04", False), ("2004/05", True), ("2005/06", False)]


def test_build_careers_drops_verbatim_duplicates(fixtures_dir):
    landing = load(fixtures_dir, "landing_8477956.json")
    landing["seasonTotals"].append(dict(landing["seasonTotals"][0]))

    class One:
        def get_json(self, url, key, params=None):
            return landing

    df = nhl.build_careers(One(), [8477956])
    assert not df.duplicated().any()
    assert len(df) == len(nhl.career_rows(load(fixtures_dir, "landing_8477956.json")))
