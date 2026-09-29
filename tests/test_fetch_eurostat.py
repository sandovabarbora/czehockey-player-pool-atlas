"""Eurostat demo_gind: JSON-stat parsing on a saved response, and the fetch path with a fake client."""

from __future__ import annotations

import json

import pandas as pd

from src import config, snapshot
from src.fetch import eurostat
from src.nations import NATIONS


def payload(fixtures_dir):
    return json.loads((fixtures_dir / "eurostat" / "demo_gind_jan.json").read_text())


def test_parse_jsonstat_is_complete(fixtures_dir):
    df = eurostat.parse_jsonstat(payload(fixtures_dir))
    assert list(df.columns) == eurostat.COLUMNS
    assert len(df) == 10 * 32
    assert set(df["iso3"]) == {n.iso3 for n in NATIONS}
    assert df["population"].notna().all()
    assert df.groupby("iso3")["year"].agg(["min", "max", "size"]).eq([1995, 2026, 32]).all().all()


def test_parse_jsonstat_maps_positions_to_the_right_cells(fixtures_dir):
    p = payload(fixtures_dir)
    df = eurostat.parse_jsonstat(p).set_index(["geo", "year"])
    # value index = geo_position * n_years + year_position (freq and indic_de have size 1)
    geo_pos = p["dimension"]["geo"]["category"]["index"]
    year_pos = p["dimension"]["time"]["category"]["index"]
    n_years = len(year_pos)
    for geo in ("CZ", "LV", "CH"):
        for year in ("1995", "2025"):
            key = str(geo_pos[geo] * n_years + year_pos[year])
            assert df.loc[(geo, int(year)), "population"] == p["value"][key]
    assert df.loc[("CZ", 2021), "flag"] == "b"  # census break


def test_czech_population_is_plausible(fixtures_dir):
    df = eurostat.parse_jsonstat(payload(fixtures_dir))
    cze = df[df["iso3"] == "CZE"].set_index("year")["population"]
    assert 10_000_000 < cze[1995] < 10_500_000
    assert 10_700_000 < cze[2025] < 11_100_000


class FixtureClient:
    def __init__(self, data):
        self.data = data
        self.keys = []

    def get_json(self, url, key, params=None):
        self.keys.append((url, key, params))
        return self.data


def test_run_writes_and_publishes(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path / "snapshot")
    client = FixtureClient(payload(fixtures_dir))
    written = eurostat.run(client=client)
    assert {p.name for p in written} == {"population.parquet", "population.json"}
    url, _, params = client.keys[0]
    assert url == eurostat.URL
    assert ("indic_de", "JAN") in params
    assert sum(1 for k, _ in params if k == "geo") == 10
    df = pd.read_parquet(tmp_path / "snapshot" / "population.parquet")
    assert len(df) == 320
    doc = json.loads((tmp_path / "snapshot" / "population.json").read_text())
    assert len(doc["rows"]) == 320
    assert snapshot.verify(tmp_path / "snapshot") == []
