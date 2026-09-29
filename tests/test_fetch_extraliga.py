"""Extraliga (hokej.cz) fetcher on saved pages (no network)."""

from __future__ import annotations

import pandas as pd
import pytest

from src.fetch import extraliga


def page(fixtures_dir, name):
    return (fixtures_dir / "extraliga" / name).read_text(encoding="utf-8")


@pytest.fixture
def payload(fixtures_dir):
    def rows(name):
        return extraliga.parse_table(page(fixtures_dir, f"2024_{name}.html"))

    return {
        "competition_id": 7230,
        "info": rows("info"),
        "info_foreign": rows("info_foreign"),
        "info_u20": rows("info_u20"),
        "goalkeeper": rows("goalkeeper"),
        "goalkeeper_foreign": rows("goalkeeper_foreign"),
        "goalkeeper_u20": rows("goalkeeper_u20"),
        "time": rows("time"),
    }


def test_small_parsers():
    assert extraliga.clock_to_s("1215:17") == 72917
    assert extraliga.clock_to_s("23:50") == 1430
    assert extraliga.clock_to_s("") is None
    assert extraliga.czech_date("17.2.1997") == "1997-02-17"
    assert extraliga.czech_date("n/a") is None
    assert extraliga.birth_year_from_short(6, 2024) == 2006
    assert extraliga.birth_year_from_short(77, 1995) == 1977
    assert extraliga.season_label(1999) == "1999/00"


@pytest.mark.parametrize(("year", "expected"), [(2024, 7230), (2013, 1621)])
def test_regular_competition_is_picked(fixtures_dir, year, expected):
    options = extraliga.competitions(page(fixtures_dir, f"season_{year}.html"))
    assert len(options) >= 3
    assert extraliga.regular_competition(options, year) == expected


def test_regular_competition_refuses_ambiguity():
    with pytest.raises(ValueError, match="cannot pick"):
        extraliga.regular_competition([(1, "Extraliga"), (2, "Extraliga B")], 2000)
    with pytest.raises(ValueError, match="cannot pick"):
        extraliga.regular_competition([(1, "Play off")], 2000)


def test_parse_table_reads_the_stats_table_only(fixtures_dir):
    rows = extraliga.parse_table(page(fixtures_dir, "2024_info.html"))
    assert len(rows) == 3
    r = rows[0]
    assert {"GP", "G", "A", "P", "PIM", "_id", "_name", "_path", "_team"} <= set(r)
    assert r["_path"].startswith("/hrac/") and "?" not in r["_path"]
    u20 = extraliga.parse_table(page(fixtures_dir, "2024_info_u20.html"))
    assert u20[0]["_yy"] is not None and "(" not in u20[0]["_name"]


def test_parse_profile_birth_date(fixtures_dir):
    assert extraliga.parse_profile(page(fixtures_dir, "profile_5607427.html")) == "1997-02-17"
    assert extraliga.parse_profile("<html></html>") is None


def test_build_season(payload):
    sk, go = extraliga.build_season(payload, 2024)
    assert list(sk.columns) == extraliga.SKATER_COLUMNS
    assert list(go.columns) == extraliga.GOALIE_COLUMNS
    assert len(sk) == 3 and len(go) == 2
    assert set(sk["position"]) <= {"F", "D"} and (go["position"] == "G").all()
    assert (sk["competition_id"] == 7230).all()
    # the flags come from the filtered lists
    foreign = {r["_id"] for r in payload["info_foreign"]}
    u20 = {r["_id"] for r in payload["info_u20"]}
    assert set(sk.loc[sk["is_foreign"], "player_id"]) == foreign
    assert set(sk.loc[sk["is_u20"], "player_id"]) == u20
    assert sk.loc[sk["is_u20"], "birth_year"].notna().all()
    # time on ice joins on player and team
    assert sk["toi_s"].notna().all()
    assert (sk["toi_per_game_s"] == sk["toi_s"] / sk["games_played"]).all()
    # goalkeeper minutes are converted to seconds
    raw = payload["goalkeeper"][0]
    assert go.iloc[0]["toi_s"] == int(raw["TOI"]) * 60


def test_foreign_flag_missing_when_the_season_has_no_list(payload):
    payload = {**payload, "info_foreign": [], "goalkeeper_foreign": []}
    sk, go = extraliga.build_season(payload, 2024)
    assert sk["is_foreign"].isna().all() and go["is_foreign"].isna().all()


def test_no_time_before_2013(payload):
    sk, _ = extraliga.build_season({**payload, "time": []}, 2005)
    assert sk["toi_s"].isna().all()


def test_attach_birth_dates(payload):
    sk, _ = extraliga.build_season(payload, 2024)
    first = int(sk["player_id"].iloc[0])
    profiles = pd.DataFrame(
        [
            {
                "player_id": first,
                "full_name": "x",
                "profile_path": "/hrac/x/1",
                "birth_date": "1997-02-17",
            }
        ]
    )
    out = extraliga.coerce(extraliga.attach_birth_dates(sk, profiles))
    row = out[out["player_id"] == first].iloc[0]
    assert row["birth_date"] == "1997-02-17" and row["birth_year"] == 1997
    assert out["birth_date"].isna().sum() == len(out) - 1


def test_table_params():
    p = extraliga.table_params(2024, 7230, "time", foreign=True, u20=True)
    assert p["stats-filter-season"] == 2024 and p["stats-filter-competition"] == 7230
    assert p["stats-menu-section"] == "time" and p["stats-view-pager-all"] == 1
    assert p["stats-playerFilter-stranger"] == 1 and p["stats-playerFilter-age"] == 20


def test_only_public_fields(payload):
    sk, go = extraliga.build_season(payload, 2024)
    banned = {"height", "weight", "stick", "photo", "vyska", "vaha"}
    assert not banned & (set(sk.columns) | set(go.columns) | set(extraliga.PROFILE_COLUMNS))


def test_regular_competition_skips_a_preseason_cup():
    options = [
        (6689, "Generali Česká pojišťovna play off"),
        (6630, "Tipsport extraliga"),
        (6638, "Generali Česká Cup – play off"),
        (6633, "Generali Česká Cup"),
        (6634, "Generali Česká Cup – sk. A"),
    ]
    assert extraliga.regular_competition(options, 2020) == 6630
