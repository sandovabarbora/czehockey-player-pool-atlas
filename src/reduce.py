"""Dimensionality reduction: PCA + UMAP for forwards + defensemen.

Two projection variants per position (locked critique decision):
  - STYLE   — z-scored features without league multipliers
  - QUALITY — z-scored features with league multipliers applied

Two reduction methods per variant:
  - PCA(n_components=2)  — interpretable; loadings published in methodology
  - UMAP(n_neighbors=15, min_dist=0.3)  — better local structure

All operations use src.config.RANDOM_SEED (=42).

Feature vector (honest about what we have across all 3 leagues):
  - goals_per_gp_shrunk        (production)
  - assists_per_gp_shrunk      (playmaking)
  - pim_per_gp_shrunk          (penalty behavior, single-sided proxy)
  - birth_year_norm            (z-scored age signal; lower = older)

Shots per game is INTENTIONALLY DROPPED from the cross-league projection
because hokej.cz doesn't expose shots in the Extraliga team /statistiky
table. Including shots would force either dropping all 217 Extraliga
forwards or imputing with cohort medians (which creates phantom signal
and was rejected for xG via the same reasoning). The NHL/MoneyPuck
enrichment table contains per-60 5v5 shots for tooltip use.

Inputs:
  data/processed/features_forwards.parquet
  data/processed/features_defense.parquet

Outputs:
  data/processed/coords_forwards.parquet
      canonical_id, season, league, name, birth_year, position_normalized,
      czech_eligible_flag, iihf_appearances,
      pca_x_style, pca_y_style, umap_x_style, umap_y_style,
      pca_x_quality, pca_y_quality, umap_x_quality, umap_y_quality
  data/processed/coords_defense.parquet  (same schema)
  data/processed/pca_loadings.parquet
      One row per (position, projection, principal_component, feature)
      with loading values for the methodology section.
"""

from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import pandas as pd
import umap
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet, write_parquet

LOG = logging.getLogger(__name__)

UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST = 0.3

# Cross-league feature columns we use (suffixes appended below per projection)
PROJECTION_METRICS: tuple[str, ...] = ("goals_per_gp", "assists_per_gp", "pim_per_gp")


def _build_matrix(df: pd.DataFrame, suffix: str) -> tuple[np.ndarray, pd.Series, list[str]]:
    """Build feature matrix for one projection variant.

    Args:
        df: features parquet (forwards or defense)
        suffix: '_shrunk' for style, '_quality' for quality

    Returns:
        (X, kept_mask, feature_names)
        X is the standardized matrix; kept_mask aligns rows with the input
        DataFrame (True = row included in projection).
    """
    cols = [f"{m}{suffix}" for m in PROJECTION_METRICS]
    if "birth_year" in df.columns:
        cols_with_age = cols + ["birth_year"]
    else:
        cols_with_age = cols

    sub = df[cols_with_age].copy()
    # Mask: drop rows with any NaN across the feature columns
    kept_mask = sub.notna().all(axis=1)
    sub_clean = sub[kept_mask].astype(float)

    # Standardize (mean=0, std=1) across the kept rows
    scaler = StandardScaler()
    X = scaler.fit_transform(sub_clean.values)
    return X, kept_mask, cols_with_age


def _reduce_one(
    df: pd.DataFrame,
    suffix: str,
    label: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run PCA + UMAP for one (position, projection) pair.

    Returns:
        (coords_df, loadings_df)
        coords_df has one row per input row with NaN for rows that were
        dropped (missing features). loadings_df has one row per (PC,
        feature) for the methodology section.
    """
    X, kept_mask, feature_names = _build_matrix(df, suffix)
    n_kept = kept_mask.sum()
    LOG.info("  %s projection (suffix=%s): %d rows in feature matrix, %d features",
             label, suffix, n_kept, len(feature_names))

    if n_kept < 4:
        LOG.warning("  too few rows (%d) for reduction; skipping", n_kept)
        empty = pd.DataFrame(index=df.index, columns=[
            f"pca_x_{label}", f"pca_y_{label}",
            f"umap_x_{label}", f"umap_y_{label}",
        ], dtype=float)
        return empty, pd.DataFrame()

    pca = PCA(n_components=2, random_state=config.RANDOM_SEED)
    pca_coords = pca.fit_transform(X)

    # UMAP: n_components=2, with min n_neighbors capped by sample size
    n_neighbors = min(UMAP_N_NEIGHBORS, max(2, n_kept - 1))
    reducer = umap.UMAP(
        n_neighbors=n_neighbors,
        min_dist=UMAP_MIN_DIST,
        n_components=2,
        random_state=config.RANDOM_SEED,
    )
    umap_coords = reducer.fit_transform(X)

    out = pd.DataFrame(index=df.index, dtype=float)
    out[f"pca_x_{label}"] = np.nan
    out[f"pca_y_{label}"] = np.nan
    out[f"umap_x_{label}"] = np.nan
    out[f"umap_y_{label}"] = np.nan
    out.loc[kept_mask, f"pca_x_{label}"] = pca_coords[:, 0]
    out.loc[kept_mask, f"pca_y_{label}"] = pca_coords[:, 1]
    out.loc[kept_mask, f"umap_x_{label}"] = umap_coords[:, 0]
    out.loc[kept_mask, f"umap_y_{label}"] = umap_coords[:, 1]

    # Loadings table for methodology
    loadings_rows: list[dict] = []
    for pc_idx in range(2):
        explained = float(pca.explained_variance_ratio_[pc_idx])
        for f_idx, feature_name in enumerate(feature_names):
            loadings_rows.append({
                "projection": label,
                "pc": f"PC{pc_idx + 1}",
                "feature": feature_name,
                "loading": float(pca.components_[pc_idx, f_idx]),
                "explained_variance_ratio": explained,
            })
    loadings_df = pd.DataFrame(loadings_rows)
    return out, loadings_df


def reduce_position(df: pd.DataFrame, position_label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run both style + quality projections for one position."""
    LOG.info("reducing %s features: %d rows", position_label, len(df))
    style_coords, style_loadings = _reduce_one(df, "_shrunk", "style")
    quality_coords, quality_loadings = _reduce_one(df, "_quality", "quality")

    # Combine coords side-by-side
    coords = pd.concat([style_coords, quality_coords], axis=1)
    # Attach metadata
    meta_cols = ["canonical_id", "season", "league", "first_name", "last_name",
                 "birth_year", "position_normalized", "czech_eligible_flag",
                 "iihf_appearances", "GP"]
    meta_cols = [c for c in meta_cols if c in df.columns]
    out = pd.concat([df[meta_cols].reset_index(drop=True),
                     coords.reset_index(drop=True)], axis=1)

    # Tag loadings with position
    for ldf in (style_loadings, quality_loadings):
        if not ldf.empty:
            ldf.insert(0, "position", position_label)
    loadings_combined = pd.concat([style_loadings, quality_loadings], ignore_index=True)
    return out, loadings_combined


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    np.random.seed(config.RANDOM_SEED)

    fwd = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    df_def = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")

    fwd_coords, fwd_loadings = reduce_position(fwd, "F")
    write_parquet(fwd_coords, config.PROCESSED_DIR / "coords_forwards.parquet")

    def_coords, def_loadings = reduce_position(df_def, "D")
    write_parquet(def_coords, config.PROCESSED_DIR / "coords_defense.parquet")

    all_loadings = pd.concat([fwd_loadings, def_loadings], ignore_index=True)
    write_parquet(all_loadings, config.PROCESSED_DIR / "pca_loadings.parquet")

    LOG.info("=== PCA loadings (forwards, style) ===")
    fwd_style = all_loadings[(all_loadings["position"] == "F") & (all_loadings["projection"] == "style")]
    LOG.info("\n%s", fwd_style.to_string(index=False))


if __name__ == "__main__":
    main()
