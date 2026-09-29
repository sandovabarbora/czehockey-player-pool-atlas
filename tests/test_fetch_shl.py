"""SHL fetcher on saved responses (no network)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.fetch import shl


def load(fixtures_dir, name):
    return json.loads((fixtures_dir / "shl" / name).read_text())


def block(fixtures_dir, name):
    payload = load(fixtures_dir, name)
    return payload[0] if payload else {"stats": [], "players": {}}


@pytest.fixture
def season_2009(fixtures_dir):
    return {
        "summary": block(fixtures_dir, "players_summary_2009.json"),
        "goalies": block(fixtures_dir, "goalkeepers_summary_2009.json"),
        "toi": block(fixtures_dir, "players_timeOnIce_2009.json"),
    }


def test_small_parsers():
    assert shl.clock_to_s("19:02") == 1142
    assert shl.clock_to_s("21:26:54") == 77214
    assert shl.clock_to_s(None) is None and shl.clock_to_s("-") is None
    assert shl.iso3("SE") == "SWE" and shl.iso3("CZ") == "CZE" and shl.iso3("CH") == "CHE"
    assert shl.iso3("N/A") is None and shl.iso3("") is None
    assert shl.season_label(2009) == "2009/10"
    assert shl.stats_url("players_summary", "abc").endswith("?ssgtUuid=abc&count=1000")


def test_regular_ssgts_pick_the_shl_regular_season(fixtures_dir):
    ssgts = shl.regular_ssgts(load(fixtures_dir, "layout_info.json"))
    assert set(ssgts) == {2024, 2025}
    layout = load(fixtures_dir, "layout_info.json")[0]["seasonSeriesGameTypeTeams"]
    regular = {
        int(s["season"]["code"]): s["ssgtUuid"]
        for s in layout
        if s["series"]["code"] == "SHL" and s["gameType"]["code"] == "regular"
    }
    assert ssgts == regular


def test_build_season(season_2009):
    sk, go = shl.build_season(season_2009, 2009)
    assert list(sk.columns) == shl.SKATER_COLUMNS
    assert list(go.columns) == shl.GOALIE_COLUMNS
    summary = season_2009["summary"]["stats"]
    assert len(sk) + len(go) == len(summary)
    assert (go["position"] == "G").all() and (go["source"] == "goalkeepers_summary").all()
    assert "G" not in set(sk["position"].dropna())
    # rows without a uuid carry no personal data
    no_uuid = sk[sk["player_id"].isna()]
    assert len(no_uuid) >= 1 and no_uuid["birth_date"].isna().all()
    # the legacy id is set only when the name is unique within the season
    dup = sk[sk["full_name"] == "Niklas Andersson"]
    assert len(dup) == 2 and dup["legacy_id"].isna().all()
    # time on ice: the total joins from players_timeOnIce, per game from it
    assert sk["toi_s"].notna().all()
    assert (sk["toi_per_game_s"] == sk["toi_s"] / sk["games_played"]).all()
    assert go["toi_s"].notna().all()


def test_goalie_fallback_when_goalkeeper_table_is_empty(fixtures_dir):
    payload = {
        "summary": block(fixtures_dir, "players_summary_1995.json"),
        "goalies": block(fixtures_dir, "goalkeepers_summary_1995.json"),
    }
    sk, go = shl.build_season(payload, 1995)
    assert len(go) == 2 and (go["source"] == "players_summary").all()
    assert go["games_played"].notna().all() and go["toi_s"].isna().all()
    assert len(sk) == 1 and sk["toi_s"].isna().all()


def test_backfill_by_uuid():
    def row(season, pid, nat, pos, bd=None):
        return {
            "player_id": pid,
            "season_start": season,
            "nationality": nat,
            "nationality_source": "season" if nat else None,
            "birth_date": bd,
            "birth_date_source": "season" if bd else None,
            "position": pos,
            "position_source": "season" if pos else None,
        }

    sk = pd.DataFrame(
        [
            row(2010, "u1", None, None),
            row(2011, "u1", "CZE", "D", "1990-01-01"),
            row(2012, "u1", "CZE", "D", "1990-01-01"),
            row(2012, None, None, None),
        ]
    )
    go = pd.DataFrame([row(2013, "u1", None, "G")])
    sk2, go2 = shl.backfill(sk, go)
    first = sk2.iloc[0]
    assert (first["nationality"], first["position"], first["birth_date"]) == (
        "CZE",
        "D",
        "1990-01-01",
    )
    assert first["nationality_source"] == first["position_source"] == "backfill"
    assert pd.isna(sk2.iloc[3]["nationality"])
    # a goalkeeper row gets nationality but keeps its own position
    assert go2.iloc[0]["nationality"] == "CZE" and go2.iloc[0]["position"] == "G"


def test_only_public_fields(season_2009):
    sk, go = shl.build_season(season_2009, 2009)
    banned = {"height", "weight", "shoots", "playerMedia", "portrait"}
    assert not banned & (set(sk.columns) | set(go.columns))
