"""Central path and config loading for the pipeline.

All modules read paths and YAML configs through this module. Keeps absolute
paths and YAML parsing logic out of the fetch and feature modules.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# --- Paths -------------------------------------------------------------------

ROOT_DIR: Path = Path(__file__).resolve().parent.parent
CONFIG_DIR: Path = ROOT_DIR / "config"
DATA_DIR: Path = ROOT_DIR / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
SEED_DIR: Path = DATA_DIR / "seed"
OUTPUTS_DIR: Path = ROOT_DIR / "outputs"
TEMPLATES_DIR: Path = ROOT_DIR / "templates"


def ensure_dirs() -> None:
    """Create runtime directories that may not exist on a fresh clone."""
    for d in (RAW_DIR, PROCESSED_DIR, OUTPUTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# --- Config loading ----------------------------------------------------------


@lru_cache(maxsize=None)
def load_yaml(name: str) -> dict[str, Any]:
    """Load a YAML config from the config/ directory.

    Args:
        name: filename including .yaml extension (e.g. "leagues.yaml")

    Returns:
        Parsed YAML as a dict.

    Raises:
        FileNotFoundError: if the config file is missing.
    """
    path = CONFIG_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def leagues() -> dict[str, Any]:
    """Return the leagues.yaml config dict."""
    return load_yaml("leagues.yaml")


def league_quality() -> dict[str, Any]:
    """Return the league_quality.yaml config dict."""
    return load_yaml("league_quality.yaml")


def features_config() -> dict[str, Any]:
    """Return the feature_definitions.yaml config dict."""
    return load_yaml("feature_definitions.yaml")


def nt_veterans() -> dict[str, list[str]]:
    """Return the nt_veterans.yaml config dict."""
    return load_yaml("nt_veterans.yaml")


# --- Reproducibility ---------------------------------------------------------

RANDOM_SEED: int = 42
"""Pipeline-wide random seed. Set in every stochastic operation (KMeans, UMAP,
train/test splits if any). Documented in methodology section of the report."""
