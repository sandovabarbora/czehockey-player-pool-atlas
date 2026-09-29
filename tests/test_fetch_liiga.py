"""Liiga fetcher on saved responses (no network)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.fetch import liiga


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "liiga" / name).read_text())


@pytest.fixture
def payload(fixtures_dir):
    return {
        "skaters": load(fixtures_dir, "stats_2026.json"),
        "goalies": load(fixtures_dir, "stats_gk_2026.json"),
        "info": load(fixtures_dir, "info_2026.json"),
    }


def test_season_helpers():
    assert liiga.api_year(1995) == 1996
    assert liiga.season_label(2025) == "2025/26"
    assert liiga.seasons()[0] == 1995 and liiga.seasons()[-1] == 2025
    assert "2026/2026/runkosarja/false?dataType=basicStats&" in liiga.stats_url(2025, False)
    assert "dataType=basicStatsGk" in liiga.stats_url(2025, True)
    assert liiga.info_url(1995).endswith("fromSeason=1996&toSeason=1996")


@pytest.mark.parametrize(
    ("role", "pos"),
    [
        ("KH", "F"),
        ("VL", "F"),
        ("OH", "F"),
        ("13. H", "F"),
        ("7. P", "D"),
        ("OP", "D"),
        ("MV", "G"),
        ("-", None),
        (None, None),
    ],
)
def test_position_codes(role, pos):
    assert liiga.position(role) == pos


def test_skaters(payload):
    sk, _ = liiga.build_season(payload, 2025)
    assert list(sk.columns) == liiga.SKATER_COLUMNS
    # the row with no games is dropped
    assert len(sk) == len(payload["skaters"]) - 1
    assert (sk["games_played"] > 0).all()
    assert (sk["season"] == "2025/26").all()
    assert set(sk["position"]) <= {"F", "D"}
    # games-played is Liiga's `games`; per-game TOI divides by it
    raw = next(r for r in payload["skaters"] if r["games"] != r["playedGames"])
    row = sk[sk["player_id"] == raw["playerId"]].iloc[0]
    assert row["games_played"] == raw["games"]
    assert row["toi_per_game_s"] == pytest.approx(raw["timeOnIceAvg"])
    # birth date and a missing stats nationality come from the roster record
    assert sk["birth_date"].notna().all()
    assert sk["nationality"].notna().all()
    assert (sk["nationality"] == "CZE").sum() >= 2
    assert set(sk["nationality_source"]) == {"season"}


def test_goalies(payload):
    _, go = liiga.build_season(payload, 2025)
    assert list(go.columns) == liiga.GOALIE_COLUMNS
    assert (go["position"] == "G").all()
    # a goalkeeper who never dressed is dropped; a backup who dressed stays
    assert len(go) == len(payload["goalies"]) - 1
    assert (go["games_dressed"] >= go["games_played"]).all()
    assert go["toi_s"].notna().all()


def test_toi_zero_season_is_missing(fixtures_dir):
    rows = load(fixtures_dir, "stats_2014.json")
    sk = liiga.parse_skaters(rows, 2013, {})
    assert sk["toi_s"].isna().all() and sk["toi_per_game_s"].isna().all()


def test_iso3_mapping_of_ioc_codes():
    rows = [
        {
            "playerId": i,
            "firstName": "A",
            "lastName": str(i),
            "nationality": code,
            "games": 1,
            "role": "H",
        }
        for i, code in enumerate(["SUI", "GER", "LAT", "DEN", "SLO", "CZE", ""], 1)
    ]
    sk = liiga.parse_skaters(rows, 2025, {})
    assert sk["nationality"].tolist()[:6] == ["CHE", "DEU", "LVA", "DNK", "SVN", "CZE"]
    assert pd.isna(sk["nationality"].iloc[6])


def test_backfill_nationality_from_other_seasons():
    base = {"team_id": 1, "nat_raw": None}
    sk = pd.DataFrame(
        [
            {
                **base,
                "player_id": 7,
                "season_start": 2020,
                "nationality": "CZE",
                "nationality_source": "season",
            },
            {
                **base,
                "player_id": 7,
                "season_start": 2021,
                "nationality": None,
                "nationality_source": None,
            },
            {
                **base,
                "player_id": 8,
                "season_start": 2021,
                "nationality": None,
                "nationality_source": None,
            },
        ]
    )
    out, _ = liiga.backfill_nationality(sk, sk.iloc[0:0])
    assert out["nationality"].tolist()[:2] == ["CZE", "CZE"]
    assert out["nationality_source"].tolist()[1] == "backfill"
    assert pd.isna(out["nationality"].iloc[2])


def test_only_public_fields(payload):
    sk, go = liiga.build_season(payload, 2025)
    banned = {"height", "weight", "placeOfBirth", "place_of_birth", "pictureUrl", "handedness"}
    assert not banned & (set(sk.columns) | set(go.columns))
