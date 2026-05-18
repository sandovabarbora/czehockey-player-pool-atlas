"""Tests for crosswalk: name + date normalization, position mapping, build_canonical."""

from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.crosswalk import (
    NAME_MATCH_THRESHOLD,
    _best_name_match,
    normalize_name,
    normalize_position,
    parse_birth_date,
)

CANONICAL_PATH = config.PROCESSED_DIR / "players.parquet"


# --- normalize_name ---------------------------------------------------------


def test_normalize_name_strips_czech_diacritics():
    assert normalize_name("David Pastrňák") == "david pastrnak"
    assert normalize_name("Lukáš Sedlák") == "lukas sedlak"
    assert normalize_name("Tomáš Mazura") == "tomas mazura"


def test_normalize_name_strips_finnish_diacritics():
    assert normalize_name("Markus Hännikäinen") == "markus hannikainen"


def test_normalize_name_strips_junior_marker():
    assert normalize_name("Petr Vechet *") == "petr vechet"
    assert normalize_name("Jakub Frolo *") == "jakub frolo"


def test_normalize_name_empty_input():
    assert normalize_name("") == ""
    assert normalize_name(None) == ""
    assert normalize_name("   ") == ""


# --- parse_birth_date -------------------------------------------------------


def test_parse_birth_date_iso():
    assert parse_birth_date("1996-05-25") == ("1996-05-25", 1996)


def test_parse_birth_date_finnish_czech_format():
    # Liiga / Czech format is D.M.YYYY
    assert parse_birth_date("17.7.1990") == ("1990-07-17", 1990)
    assert parse_birth_date("25.6.2000") == ("2000-06-25", 2000)


def test_parse_birth_date_pads_single_digits():
    assert parse_birth_date("1.5.2007") == ("2007-05-01", 2007)


def test_parse_birth_date_unparseable():
    assert parse_birth_date("") == (None, None)
    assert parse_birth_date(None) == (None, None)
    assert parse_birth_date("garbage") == (None, None)


# --- normalize_position -----------------------------------------------------


def test_normalize_position_nhl():
    assert normalize_position("C", "nhl") == "F"
    assert normalize_position("L", "nhl") == "F"
    assert normalize_position("R", "nhl") == "F"
    assert normalize_position("D", "nhl") == "D"
    assert normalize_position("G", "nhl") == "G"


def test_normalize_position_liiga():
    assert normalize_position("MV", "liiga") == "G"
    assert normalize_position("VP", "liiga") == "D"
    assert normalize_position("KH", "liiga") == "F"


def test_normalize_position_extraliga():
    assert normalize_position("Ú", "extraliga") == "F"
    assert normalize_position("O", "extraliga") == "D"
    assert normalize_position("B", "extraliga") == "G"


# --- _best_name_match -------------------------------------------------------


def test_name_match_birth_year_gate_blocks_mismatch():
    """A perfect-name match must be rejected when birth years differ."""
    cands = pd.DataFrame({
        "name_normalized": ["david moravec"],
        "birth_year": pd.array([1985], dtype="Int64"),
    })
    # Same name, very different birth year -> should NOT match
    result = _best_name_match("david moravec", 2002, cands, require_birth_year_within=1)
    assert result is None


def test_name_match_picks_best_when_year_close():
    cands = pd.DataFrame({
        "name_normalized": ["david pastrnak", "david krejci"],
        "birth_year": pd.array([1996, 1986], dtype="Int64"),
    })
    result = _best_name_match("david pastrnak", 1996, cands, require_birth_year_within=1)
    assert result == 0


# --- canonical table sanity (skip if not built) -----------------------------


@pytest.mark.skipif(not CANONICAL_PATH.exists(), reason="canonical players.parquet not built")
def test_canonical_no_duplicate_extraliga_ids():
    """Every extraliga_id should appear at most once across canonical rows."""
    df = pd.read_parquet(CANONICAL_PATH)
    extra = df["extraliga_id"].dropna()
    assert extra.is_unique, "duplicate extraliga_id values found in canonical table"


@pytest.mark.skipif(not CANONICAL_PATH.exists(), reason="canonical players.parquet not built")
def test_canonical_extraliga_only_rows_have_no_other_ids():
    """Rows sourced only from Extraliga must have NA nhl_id and liiga_id."""
    df = pd.read_parquet(CANONICAL_PATH)
    extra_only = df[df["sources"].astype(str) == "['extraliga']"]
    assert extra_only["nhl_id"].isna().all()
    assert extra_only["liiga_id"].isna().all()


@pytest.mark.skipif(not CANONICAL_PATH.exists(), reason="canonical players.parquet not built")
def test_canonical_no_self_merge():
    """Catches the bug we fixed: a player must never have ['extraliga', 'extraliga']."""
    df = pd.read_parquet(CANONICAL_PATH)
    weird = df[df["sources"].astype(str).isin(["['extraliga' 'extraliga']", "['nhl' 'nhl']", "['liiga' 'liiga']"])]
    assert weird.empty, f"self-merge detected: {len(weird)} rows"
