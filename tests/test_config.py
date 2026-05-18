"""Tests for the config loader. These run on a fresh clone (no data needed)."""

from __future__ import annotations

import pytest

from src import config


def test_paths_exist():
    """Static directories that ship with the repo must exist."""
    assert config.CONFIG_DIR.is_dir()
    assert config.TEMPLATES_DIR.is_dir()


def test_leagues_yaml_loads():
    cfg = config.leagues()
    assert "leagues" in cfg
    assert "nhl" in cfg["leagues"]
    assert "khl" in cfg["excluded"]  # KHL must be in excluded, not leagues
    assert "khl" not in cfg["leagues"]


def test_league_quality_yaml_loads():
    cfg = config.league_quality()
    multipliers = cfg["multipliers"]
    assert multipliers["nhl"] == 1.00
    assert "khl" not in multipliers  # KHL must NOT appear here either
    assert all(0.0 < v <= 1.0 for v in multipliers.values())


def test_features_config_loads():
    cfg = config.features_config()
    for pos in ("forwards", "defensemen", "goalies"):
        assert pos in cfg
        assert cfg[pos]["dims"] == len(cfg[pos]["features"])
    # xG policy must be set
    assert cfg["xg_policy"]["impute"] is False
    assert cfg["xg_policy"]["in_main_projection"] is False


def test_random_seed_set():
    assert config.RANDOM_SEED == 42
