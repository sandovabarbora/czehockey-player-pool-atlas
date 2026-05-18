"""Unit + integration tests for src.features_forwards."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import config
from src.features_forwards import (
    PHANTOM_GAMES,
    bayesian_shrink,
    compute_per_game_rates,
    z_score_within_position,
)

FEATURES_PATH = config.PROCESSED_DIR / "features_forwards.parquet"
NHL_EXTRAS_PATH = config.PROCESSED_DIR / "features_forwards_nhl_extras.parquet"


# --- compute_per_game_rates -------------------------------------------------


def test_compute_per_game_rates_basic():
    df = pd.DataFrame([
        {"GP": 80, "G": 40, "A": 30, "P": 70, "PIM": 20, "shots": 240, "league": "nhl"},
        {"GP": 50, "G": 10, "A": 15, "P": 25, "PIM": 30, "shots": 100, "league": "extraliga"},
    ])
    out = compute_per_game_rates(df)
    assert out.iloc[0]["goals_per_gp"] == 0.5
    assert out.iloc[0]["points_per_gp"] == pytest.approx(70 / 80)
    assert out.iloc[1]["shots_per_gp"] == 2.0


def test_compute_per_game_rates_drops_zero_gp():
    df = pd.DataFrame([
        {"GP": 0, "G": 0, "A": 0, "P": 0, "PIM": 0, "shots": 0, "league": "nhl"},
        {"GP": 10, "G": 1, "A": 1, "P": 2, "PIM": 0, "shots": 5, "league": "nhl"},
    ])
    out = compute_per_game_rates(df)
    assert len(out) == 1


# --- bayesian_shrink --------------------------------------------------------


def test_shrinkage_pulls_small_sample_toward_cohort_median():
    """A player with GP=1 + 1 goal should shrink toward cohort median, not stay at 1.0."""
    df = pd.DataFrame([
        # 5 "well-measured" players to establish cohort median
        {"GP": 50, "G": 10, "A": 10, "P": 20, "PIM": 5, "shots": 100, "league": "extraliga"},
        {"GP": 50, "G": 12, "A": 12, "P": 24, "PIM": 5, "shots": 100, "league": "extraliga"},
        {"GP": 50, "G": 14, "A": 14, "P": 28, "PIM": 5, "shots": 100, "league": "extraliga"},
        {"GP": 50, "G": 8,  "A": 8,  "P": 16, "PIM": 5, "shots": 100, "league": "extraliga"},
        {"GP": 50, "G": 10, "A": 10, "P": 20, "PIM": 5, "shots": 100, "league": "extraliga"},
        # Outlier: 1 GP, 1 goal -> raw rate 1.0 g/gp
        {"GP": 1, "G": 1, "A": 0, "P": 1, "PIM": 0, "shots": 5, "league": "extraliga"},
    ])
    df = compute_per_game_rates(df)
    shrunk = bayesian_shrink(df, k=PHANTOM_GAMES)
    outlier = shrunk.iloc[-1]
    assert outlier["goals_per_gp"] == 1.0  # raw stays
    assert outlier["goals_per_gp_shrunk"] < 0.5, (
        f"shrunk rate {outlier['goals_per_gp_shrunk']} should be << raw 1.0"
    )
    # Well-measured players should barely shift
    well = shrunk.iloc[0]
    assert abs(well["goals_per_gp_shrunk"] - well["goals_per_gp"]) < 0.05


def test_shrinkage_preserves_large_sample_rates():
    """A player with GP=82 + 40 goals should shrink only slightly."""
    df = pd.DataFrame([
        {"GP": 82, "G": 40, "A": 30, "P": 70, "PIM": 20, "shots": 240, "league": "nhl"},
        {"GP": 82, "G": 35, "A": 30, "P": 65, "PIM": 20, "shots": 240, "league": "nhl"},
        {"GP": 82, "G": 30, "A": 30, "P": 60, "PIM": 20, "shots": 240, "league": "nhl"},
    ])
    df = compute_per_game_rates(df)
    shrunk = bayesian_shrink(df, k=PHANTOM_GAMES)
    raw_top = shrunk.iloc[0]["goals_per_gp"]
    shrunk_top = shrunk.iloc[0]["goals_per_gp_shrunk"]
    assert abs(raw_top - shrunk_top) < 0.05, (
        f"large-sample raw {raw_top} should barely shrink, got {shrunk_top}"
    )


# --- z-score ----------------------------------------------------------------


def test_z_score_within_position():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0]})
    out = z_score_within_position(df, ["x"])
    assert out["x_z"].mean() == pytest.approx(0.0)
    assert out["x_z"].std() == pytest.approx(1.0)


def test_z_score_handles_zero_variance():
    """All-equal column shouldn't blow up — should produce all zeros."""
    df = pd.DataFrame({"x": [5.0, 5.0, 5.0]})
    out = z_score_within_position(df, ["x"])
    assert (out["x_z"] == 0.0).all()


# --- Integration: parquet sanity --------------------------------------------


@pytest.mark.skipif(not FEATURES_PATH.exists(), reason="features parquet not built")
def test_features_parquet_has_expected_columns():
    df = pd.read_parquet(FEATURES_PATH)
    required = {"canonical_id", "season", "league", "GP",
                "goals_per_gp", "goals_per_gp_shrunk", "goals_per_gp_quality",
                "points_per_gp_quality_z",
                "first_name", "last_name", "iihf_appearances"}
    missing = required - set(df.columns)
    assert not missing, f"missing required columns: {missing}"


@pytest.mark.skipif(not FEATURES_PATH.exists(), reason="features parquet not built")
def test_nhl_stars_are_top_in_quality_projection():
    """Pastrnak + Necas should rank highest by quality-adjusted z-score."""
    df = pd.read_parquet(FEATURES_PATH)
    s25 = df[df["season"] == 2025].copy()
    top5 = set(s25.nlargest(5, "points_per_gp_quality_z")["last_name"])
    assert "Pastrnak" in top5 or "Necas" in top5, (
        "expected at least one of Pastrnak/Necas in cross-league top 5"
    )
