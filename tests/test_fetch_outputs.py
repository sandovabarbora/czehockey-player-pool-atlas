"""Light sanity tests for Day 1 fetcher outputs.

These tests skip if the parquet files are not present (fresh clone before
`make fetch`). They are NOT a replacement for unit tests on the fetchers
themselves — they just verify that, when the data IS present, it has the
expected shape and content.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src import config

NHL_META = config.RAW_DIR / "nhl_player_meta.parquet"
NHL_SKATERS_2024 = config.RAW_DIR / "nhl_skaters_2024.parquet"
MP_SKATERS_2024 = config.RAW_DIR / "moneypuck_skaters_2024.parquet"


@pytest.mark.skipif(not NHL_META.exists(), reason="NHL meta parquet not present")
def test_nhl_meta_has_czech_players():
    """All rows in nhl_player_meta must be Czech (birthCountry='CZE')."""
    df = pd.read_parquet(NHL_META)
    assert len(df) >= 20, f"too few Czech NHL players found: {len(df)}"
    assert (df["birth_country"] == "CZE").all()
    # Sanity: well-known names should be present
    last_names = set(df["last_name"])
    assert "Pastrnak" in last_names, "Pastrnak missing from Czech NHL meta"


@pytest.mark.skipif(not NHL_SKATERS_2024.exists(), reason="NHL skaters parquet not present")
def test_nhl_skaters_only_czech():
    """Every row in nhl_skaters_2024 must have a playerId present in the meta."""
    meta = pd.read_parquet(NHL_META)
    skaters = pd.read_parquet(NHL_SKATERS_2024)
    assert set(skaters["playerId"]).issubset(set(meta["player_id"]))


@pytest.mark.skipif(not MP_SKATERS_2024.exists(), reason="MoneyPuck parquet not present")
def test_moneypuck_has_expected_situations():
    """MoneyPuck data must include 5on5 split (load-bearing for features)."""
    df = pd.read_parquet(MP_SKATERS_2024)
    situations = set(df["situation"].unique())
    assert "5on5" in situations
    assert "5on4" in situations  # PP for us
    assert "4on5" in situations  # PK for us


@pytest.mark.skipif(
    not (NHL_META.exists() and MP_SKATERS_2024.exists()),
    reason="parquets not present",
)
def test_meta_joinable_to_moneypuck():
    """Sanity: NHL meta playerIds should join to MoneyPuck on playerId."""
    meta = pd.read_parquet(NHL_META)
    mp = pd.read_parquet(MP_SKATERS_2024)
    cz_ids = set(meta["player_id"])
    cz_in_mp = mp[mp["playerId"].isin(cz_ids)]
    # Not all 34 Czech players are in MoneyPuck (AHL/fringe excluded), but a
    # majority should be.
    assert cz_in_mp["playerId"].nunique() >= 15, (
        f"only {cz_in_mp['playerId'].nunique()} Czech players in MoneyPuck join — "
        "expected at least 15"
    )
