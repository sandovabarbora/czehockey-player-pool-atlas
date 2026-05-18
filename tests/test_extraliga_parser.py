"""Parser-level tests for fetch_extraliga. Skip when fixtures aren't cached."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.fetch_extraliga import (
    coerce_numeric,
    extract_extraliga_teams,
    parse_team_stats,
)

# Cached HTML fixtures populated by `make fetch` or by running fetch_extraliga.
# Since hokej.cz returns the same 160KB 404-fallback for bad URLs, the parquets
# (not raw HTML) are the only signal that fetch actually succeeded.
TEAM_META = config.RAW_DIR / "extraliga_team_meta.parquet"
SKATERS_2025 = config.RAW_DIR / "extraliga_skaters_2025.parquet"


@pytest.mark.skipif(not TEAM_META.exists(), reason="extraliga team meta parquet not present")
def test_team_meta_has_14_teams():
    df = pd.read_parquet(TEAM_META)
    assert len(df) == 14, f"Tipsport Extraliga must have 14 teams; found {len(df)}"
    # Required columns
    assert set(df.columns) >= {"team_id", "team_slug", "team_name"}
    # Sanity: well-known teams present
    slugs = set(df["team_slug"])
    for s in ("hc-sparta-praha", "hc-dynamo-pardubice", "hc-ocelari-trinec"):
        assert s in slugs, f"core Extraliga team {s} missing"


@pytest.mark.skipif(not SKATERS_2025.exists(), reason="extraliga skater parquet not present")
def test_extraliga_skater_data_shape():
    df = pd.read_parquet(SKATERS_2025)
    # Position split: forwards (Ú) + defensemen (O), no goalies in this table.
    positions = set(df["POZ."].dropna().unique())
    assert positions <= {"Ú", "O"}, f"unexpected positions: {positions}"
    # All rows must have a player_id and source_team_id (join keys downstream)
    assert df["player_id"].notna().all()
    assert df["source_team_id"].notna().all()
    # Numeric columns must be numeric after coerce_numeric was applied
    assert pd.api.types.is_numeric_dtype(df["GP"])
    assert pd.api.types.is_numeric_dtype(df["P"])
    # Sanity: at least 14 teams × 10 players = 140 rows
    assert len(df) >= 140, f"too few Extraliga rows: {len(df)}"


def test_coerce_numeric_handles_extraliga_columns():
    df = pd.DataFrame([{"GP": "17", "G": "14", "A": "11", "P": "25", "+/-": "5", "PIM": "4"}])
    out = coerce_numeric(df)
    assert out["GP"].iloc[0] == 17
    assert out["P"].iloc[0] == 25
    assert out["+/-"].iloc[0] == 5
