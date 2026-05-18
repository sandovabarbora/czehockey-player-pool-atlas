"""Season-over-season trajectory for the player pool.

Locked critique decision (§4.7): players must have ≥ 30 GP in BOTH seasons
to appear in the trajectory analysis. Below that threshold, two data
points cannot distinguish trend from regression to mean.

Reality check: only NHL + Liiga have both 2024-25 and 2025-26 seasons in
our raw data — hokej.cz Extraliga is current-season-only on the
/statistiky endpoint. So the trajectory pool is naturally limited to
NHL + Liiga players with adequate sample.

What we compute per qualifying player:
  - Δ points_per_gp_shrunk (style projection)
  - Δ points_per_gp_quality (quality projection)
  - CI band width ∝ 1/sqrt(min(gp_2024, gp_2025)) as honest uncertainty
  - Direction flag: improving / stable / declining (based on whether the
    sign of Δ exceeds the CI band)
  - PCA coordinate Δ for each projection (arrow start = 2024, end = 2025)

Inputs:
  data/processed/features_forwards.parquet
  data/processed/features_defense.parquet
  data/processed/coords_forwards.parquet
  data/processed/coords_defense.parquet

Output:
  data/processed/trajectory.parquet
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet, write_parquet

LOG = logging.getLogger(__name__)

MIN_GP_PER_SEASON = 30


def compute_trajectory(features: pd.DataFrame, coords: pd.DataFrame,
                       position_label: str) -> pd.DataFrame:
    """Build trajectory rows for one position pool."""
    seasons = sorted(features["season"].unique())
    if len(seasons) < 2:
        LOG.warning("%s: only %d seasons in features; need 2 for trajectory",
                    position_label, len(seasons))
        return pd.DataFrame()
    s_old, s_new = seasons[-2], seasons[-1]

    f_old = features[features["season"] == s_old].copy()
    f_new = features[features["season"] == s_new].copy()
    LOG.info("%s: trajectory across %d -> %d (%d players old, %d new)",
             position_label, s_old, s_new, len(f_old), len(f_new))

    # Inner join on canonical_id; players must have rows in both seasons
    keep_cols_value = [
        "GP",
        "points_per_gp_shrunk", "points_per_gp_quality",
        "goals_per_gp_shrunk", "assists_per_gp_shrunk",
    ]
    # Suffix the value cols so we can keep both seasons
    f_old_keep = f_old[["canonical_id"] + keep_cols_value].rename(columns={c: f"{c}_old" for c in keep_cols_value})
    f_new_keep = f_new[["canonical_id"] + keep_cols_value].rename(columns={c: f"{c}_new" for c in keep_cols_value})
    joined = f_old_keep.merge(f_new_keep, on="canonical_id", how="inner")
    LOG.info("%s: %d players with both seasons", position_label, len(joined))

    # Apply minimum GP gate (locked decision: 30 GP both seasons)
    enough = joined[
        (joined["GP_old"] >= MIN_GP_PER_SEASON) & (joined["GP_new"] >= MIN_GP_PER_SEASON)
    ].copy()
    LOG.info("%s: %d players pass GP>=%d both seasons", position_label, len(enough), MIN_GP_PER_SEASON)

    if enough.empty:
        return pd.DataFrame()

    # Deltas
    for metric in ("points_per_gp_shrunk", "points_per_gp_quality",
                   "goals_per_gp_shrunk", "assists_per_gp_shrunk"):
        enough[f"d_{metric}"] = enough[f"{metric}_new"] - enough[f"{metric}_old"]

    # Sample-size-based CI band: SE ~ 1/sqrt(min(GP_old, GP_new))
    # Calibrated so a player with 30 GP has a wider band than a player with 80 GP.
    enough["min_gp"] = enough[["GP_old", "GP_new"]].min(axis=1)
    enough["ci_band"] = (1.0 / np.sqrt(enough["min_gp"])) * 0.5

    # Direction flag based on Δ points_per_gp_shrunk
    delta = enough["d_points_per_gp_shrunk"]
    band = enough["ci_band"]
    direction = np.where(delta > band, "improving",
                np.where(delta < -band, "declining", "stable"))
    enough["direction"] = direction

    # Attach PCA coord deltas from coords parquet
    coords_old = coords[coords["season"] == s_old][["canonical_id", "pca_x_style", "pca_y_style",
                                                     "pca_x_quality", "pca_y_quality"]].rename(
        columns={c: f"{c}_old" for c in ("pca_x_style", "pca_y_style", "pca_x_quality", "pca_y_quality")}
    )
    coords_new = coords[coords["season"] == s_new][["canonical_id", "pca_x_style", "pca_y_style",
                                                     "pca_x_quality", "pca_y_quality"]].rename(
        columns={c: f"{c}_new" for c in ("pca_x_style", "pca_y_style", "pca_x_quality", "pca_y_quality")}
    )
    enough = enough.merge(coords_old, on="canonical_id", how="left")
    enough = enough.merge(coords_new, on="canonical_id", how="left")

    # Attach name + position for downstream display
    name_cols = ["canonical_id", "first_name", "last_name", "league",
                 "iihf_appearances", "birth_year"]
    name_cols = [c for c in name_cols if c in features.columns]
    nm = features[features["season"] == s_new][name_cols].drop_duplicates("canonical_id")
    enough = enough.merge(nm, on="canonical_id", how="left")
    enough["position"] = position_label
    enough["season_old"] = s_old
    enough["season_new"] = s_new
    return enough


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    fwd_features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    fwd_coords = read_parquet(config.PROCESSED_DIR / "coords_forwards.parquet")
    def_features = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")
    def_coords = read_parquet(config.PROCESSED_DIR / "coords_defense.parquet")

    fwd_traj = compute_trajectory(fwd_features, fwd_coords, "F")
    def_traj = compute_trajectory(def_features, def_coords, "D")

    all_traj = pd.concat([fwd_traj, def_traj], ignore_index=True)
    write_parquet(all_traj, config.PROCESSED_DIR / "trajectory.parquet")

    LOG.info("=== trajectory summary ===")
    LOG.info("rows: %d", len(all_traj))
    if all_traj.empty:
        return
    LOG.info("by position + direction: %s",
             all_traj.groupby(["position", "direction"]).size().to_dict())
    LOG.info("\n--- top 10 improvers (forwards, by Δ quality points/GP) ---")
    top_imp = all_traj[all_traj["position"] == "F"].nlargest(10, "d_points_per_gp_quality")
    LOG.info("\n%s", top_imp[["first_name", "last_name", "league", "GP_old", "GP_new",
                               "points_per_gp_quality_old", "points_per_gp_quality_new",
                               "d_points_per_gp_quality", "direction"]].to_string(index=False))
    LOG.info("\n--- top 10 decliners (forwards) ---")
    top_dec = all_traj[all_traj["position"] == "F"].nsmallest(10, "d_points_per_gp_quality")
    LOG.info("\n%s", top_dec[["first_name", "last_name", "league", "GP_old", "GP_new",
                               "points_per_gp_quality_old", "points_per_gp_quality_new",
                               "d_points_per_gp_quality", "direction"]].to_string(index=False))


if __name__ == "__main__":
    main()
