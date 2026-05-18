"""Tests for fetch_iihf: Wikipedia squad table parsing + crosswalk annotation."""

from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.fetch_iihf import (
    _clean_name,
    _normalize_name,
    _parse_birthdate,
    parse_squad_page,
)

IIHF_PATH = config.RAW_DIR / "iihf_participation.parquet"


# --- Helper parsers ---------------------------------------------------------


def test_parse_birthdate_extracts_iso_from_template():
    """Wikipedia uses {{birth date and age}} which renders as
    '( 2000-06-22 ) 22 June 2000 (age 24)'."""
    assert _parse_birthdate("( 2000-06-22 ) 22 June 2000 (age 24)") == ("2000-06-22", 2000)


def test_parse_birthdate_handles_padding():
    assert _parse_birthdate("( 1990-6-5 ) 5 June 1990") == ("1990-06-05", 1990)


def test_parse_birthdate_returns_none_on_garbage():
    assert _parse_birthdate("") == (None, None)
    assert _parse_birthdate("just a name") == (None, None)


def test_clean_name_strips_captain_markers():
    assert _clean_name("Radko Gudas – A") == "Radko Gudas"
    assert _clean_name("Roman Červenka – C") == "Roman Červenka"
    assert _clean_name("David Pastrňák") == "David Pastrňák"  # untouched


def test_normalize_name_matches_crosswalk_behavior():
    """fetch_iihf must use the same normalization as src.crosswalk so the
    annotate-by-name join works."""
    from src.crosswalk import normalize_name as cw_normalize
    for n in ("David Pastrňák", "Roman Červenka", "Markus Hännikäinen", "Tomáš Mazura"):
        assert _normalize_name(n) == cw_normalize(n), f"divergence on {n!r}"


# --- parse_squad_page schema flexibility ------------------------------------


def test_parse_squad_page_ms_schema():
    """MS pages have headers: No. / Pos. / Name / Height / Weight / Birthdate / Team."""
    html = """
    <html><body>
      <h3>Czechia</h3>
      <table class="wikitable">
        <tr><th>No.</th><th>Pos.</th><th>Name</th><th>Height</th><th>Weight</th><th>Birthdate</th><th>Team</th></tr>
        <tr><td>1</td><td>G</td><td>Lukáš Dostál</td><td>1.85 m</td><td>72 kg</td>
            <td>( 2000-06-22 ) 22 June 2000 (age 24)</td><td>Anaheim Ducks</td></tr>
        <tr><td>3</td><td>D</td><td>Radko Gudas – A</td><td>1.83 m</td><td>94 kg</td>
            <td>( 1990-06-05 ) 5 June 1990 (age 34)</td><td>Anaheim Ducks</td></tr>
      </table>
    </body></html>
    """
    df = parse_squad_page(html, "ms", 2024)
    assert len(df) == 2
    assert df.iloc[0]["name"] == "Lukáš Dostál"
    assert df.iloc[0]["birth_date"] == "2000-06-22"
    assert df.iloc[1]["name"] == "Radko Gudas"  # captain marker stripped
    assert df.iloc[1]["birth_year"] == 1990


def test_parse_squad_page_wjc_schema():
    """WJC pages have headers: Pos. / No. / Player / Team / League / NHL Rights
    — no Name or Birthdate column."""
    html = """
    <html><body>
      <h3>Czechia</h3>
      <table class="wikitable">
        <tr><th>Pos.</th><th>No.</th><th>Player</th><th>Team</th><th>League</th><th>NHL Rights</th></tr>
        <tr><td>G</td><td>1</td><td>Jakub Vondraš</td><td>Sudbury Wolves</td><td>OHL</td><td>Carolina Hurricanes</td></tr>
      </table>
    </body></html>
    """
    df = parse_squad_page(html, "wjc", 2024)
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Jakub Vondraš"
    assert df.iloc[0]["position"] == "G"
    assert df.iloc[0]["birth_date"] is None  # WJC pages don't have birthdate
    assert df.iloc[0]["club_at_tournament"] == "Sudbury Wolves"


# --- Crosswalk annotation sanity (skip when no parquet) ---------------------


@pytest.mark.skipif(not IIHF_PATH.exists(), reason="iihf parquet not built")
def test_iihf_parquet_has_expected_tournaments():
    df = pd.read_parquet(IIHF_PATH)
    by_t = df.groupby(["tournament", "year"]).size().to_dict()
    assert ("ms", 2024) in by_t
    assert ("ms", 2025) in by_t
    assert ("wjc", 2024) in by_t
    assert ("wjc", 2025) in by_t
    # MS rosters should be ~25 players each
    assert by_t[("ms", 2024)] >= 20
    assert by_t[("ms", 2025)] >= 20


@pytest.mark.skipif(not IIHF_PATH.exists(), reason="iihf parquet not built")
def test_well_known_czech_stars_in_iihf():
    """Pastrnak and Cervenka have publicly played MS for Czechia in 2024+2025."""
    df = pd.read_parquet(IIHF_PATH)
    names = set(df["name_normalized"])
    assert "david pastrnak" in names
    assert "roman cervenka" in names
