"""Parser-level tests for fetch_liiga. Operate on cached HTML — no network.

These tests skip when the cached fixtures aren't present (fresh clone before
`make fetch`). They're unit tests of the parsing logic, not integration tests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.fetch_liiga import coerce_numeric, parse_list_page, parse_stats_page

LIST_CACHE = config.RAW_DIR / ".cache" / "liiga" / "list_p1.html"
PLAYER_CACHE = config.RAW_DIR / ".cache" / "liiga" / "player_60760697.html"  # Michal Jordan


@pytest.mark.skipif(not LIST_CACHE.exists(), reason="Liiga list page not cached")
def test_parse_list_page_basic():
    html = LIST_CACHE.read_text(encoding="utf-8")
    rows = parse_list_page(html)
    assert len(rows) == 100, f"expected 100 rows on page 1, got {len(rows)}"
    # Required fields populated
    r = rows[0]
    assert r["player_id"] and r["name"] and r["nationality"]


@pytest.mark.skipif(not LIST_CACHE.exists(), reason="Liiga list page not cached")
def test_parse_list_page_finds_czech():
    html = LIST_CACHE.read_text(encoding="utf-8")
    rows = parse_list_page(html)
    czech = [r for r in rows if r["nationality"] == "CZE"]
    # Liiga had 3 Czech players on page 1 at last probe; can shift slightly but >= 1
    assert len(czech) >= 1, "no Czech players found on Liiga page 1"


@pytest.mark.skipif(not PLAYER_CACHE.exists(), reason="Liiga player page not cached")
def test_parse_stats_page_skips_totals():
    """The 'Yht.' (totals) row at the end of the career table must be skipped."""
    html = PLAYER_CACHE.read_text(encoding="utf-8")
    df = parse_stats_page(html, 60760697)
    assert (df["season"] != "Yht.").all()
    # Michal Jordan started in Liiga 2023-24; should have 3+ rows by 2025-26
    assert len(df) >= 3


def test_coerce_numeric_handles_comma_decimal():
    """Finnish decimal separator is ',' — must convert to '.'"""
    df = pd.DataFrame([{"shot_pct": "5,26", "gp": "56", "goals": "9"}])
    out = coerce_numeric(df)
    assert out["shot_pct"].iloc[0] == 5.26
    assert out["gp"].iloc[0] == 56
    assert out["goals"].iloc[0] == 9
