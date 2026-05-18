"""KMeans clustering with silhouette-driven K selection.

Locked critique decision: K is NOT pre-chosen to match the brief's six
archetype labels. Silhouette score is computed across a candidate K range
and the best K wins. Labels are post-hoc, applied after manual inspection
of cluster members.

Clusters are computed on the full feature matrix (same 4 features as
reduce.py: G/GP, A/GP, PIM/GP, birth_year, all z-scored). Cluster IDs are
attached to coords_forwards.parquet / coords_defense.parquet for direct
plotting downstream.

Inputs:
  data/processed/features_forwards.parquet
  data/processed/features_defense.parquet
  data/processed/coords_forwards.parquet
  data/processed/coords_defense.parquet

Outputs (overwrites coords parquets with added cluster_id columns):
  data/processed/coords_forwards.parquet  + cluster_id_style, cluster_id_quality
  data/processed/coords_defense.parquet   + cluster_id_style, cluster_id_quality
  data/processed/cluster_summary.parquet  — per-cluster aggregates for the
      methodology section.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from src import config
from src.logging_setup import setup as logging_setup
from src.reduce import PROJECTION_METRICS
from src.utils import read_parquet, write_parquet

LOG = logging.getLogger(__name__)

K_RANGE_FORWARDS: tuple[int, ...] = (4, 5, 6, 7, 8)
K_RANGE_DEFENSE: tuple[int, ...] = (3, 4, 5, 6)


def _build_matrix(df: pd.DataFrame, suffix: str) -> tuple[np.ndarray, pd.Series, list[str]]:
    """Mirror reduce._build_matrix to ensure clusters use the same features."""
    cols = [f"{m}{suffix}" for m in PROJECTION_METRICS]
    if "birth_year" in df.columns:
        cols = cols + ["birth_year"]
    sub = df[cols].copy()
    kept_mask = sub.notna().all(axis=1)
    X = StandardScaler().fit_transform(sub[kept_mask].astype(float).values)
    return X, kept_mask, cols


def select_k(X: np.ndarray, k_range: tuple[int, ...]) -> tuple[int, dict[int, float]]:
    """Pick K by silhouette score. Returns (best_k, scores_by_k)."""
    if len(X) < max(k_range) + 1:
        # Not enough rows for the upper K's — clamp range
        max_safe = max(2, len(X) - 1)
        k_range = tuple(k for k in k_range if k <= max_safe)
        if not k_range:
            return 2, {}
    scores: dict[int, float] = {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=10, random_state=config.RANDOM_SEED)
        labels = km.fit_predict(X)
        if len(set(labels)) < 2:
            continue
        scores[k] = float(silhouette_score(X, labels))
    if not scores:
        return min(k_range), {}
    best_k = max(scores, key=scores.get)
    return best_k, scores


def cluster_position(
    features_df: pd.DataFrame,
    coords_df: pd.DataFrame,
    k_range: tuple[int, ...],
    position_label: str,
) -> tuple[pd.DataFrame, list[dict]]:
    """Run KMeans for both style + quality projections; attach to coords.

    Returns (coords_with_clusters, summary_rows).
    """
    summary: list[dict] = []
    out = coords_df.copy()
    for suffix, label in (("_shrunk", "style"), ("_quality", "quality")):
        X, kept_mask, feature_cols = _build_matrix(features_df, suffix)
        if len(X) < 4:
            LOG.warning("%s %s: too few rows (%d) to cluster", position_label, label, len(X))
            continue

        best_k, scores = select_k(X, k_range)
        LOG.info("%s %s: silhouette scores %s, best K=%d",
                 position_label, label,
                 {k: round(v, 3) for k, v in scores.items()}, best_k)

        km = KMeans(n_clusters=best_k, n_init=10, random_state=config.RANDOM_SEED)
        cluster_ids = km.fit_predict(X)

        col = f"cluster_id_{label}"
        out[col] = pd.NA
        # The features_df index aligns with coords_df row order (both built
        # in the same order from the same source). Use kept_mask positionally.
        kept_idx = kept_mask[kept_mask].index
        # coords_df was built from features_df in the same order with the
        # same index reset, so the index alignment works directly.
        # Defensive: if coords_df was reset_index'd, align by row position
        # rather than label.
        positions = np.where(kept_mask.values)[0]
        col_idx = out.columns.get_loc(col)
        for pos, cid in zip(positions, cluster_ids):
            out.iat[pos, col_idx] = int(cid)
        out[col] = out[col].astype("Int64")

        # Build per-cluster summary
        for cid in sorted(set(cluster_ids)):
            mask = out[col] == cid
            members = out[mask]
            summary.append({
                "position": position_label,
                "projection": label,
                "cluster_id": int(cid),
                "k": int(best_k),
                "silhouette": float(scores.get(best_k, 0.0)),
                "n_members": int(len(members)),
                "median_age_birth_year": float(members["birth_year"].median()) if not members.empty else None,
                "example_players": "; ".join(
                    f"{r.first_name} {r.last_name} ({r.league})"
                    for r in members.head(5).itertuples()
                ),
            })
    return out, summary


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    fwd_features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    fwd_coords = read_parquet(config.PROCESSED_DIR / "coords_forwards.parquet")
    def_features = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")
    def_coords = read_parquet(config.PROCESSED_DIR / "coords_defense.parquet")

    fwd_out, fwd_summary = cluster_position(fwd_features, fwd_coords, K_RANGE_FORWARDS, "F")
    def_out, def_summary = cluster_position(def_features, def_coords, K_RANGE_DEFENSE, "D")

    write_parquet(fwd_out, config.PROCESSED_DIR / "coords_forwards.parquet")
    write_parquet(def_out, config.PROCESSED_DIR / "coords_defense.parquet")

    summary_df = pd.DataFrame(fwd_summary + def_summary)
    write_parquet(summary_df, config.PROCESSED_DIR / "cluster_summary.parquet")

    LOG.info("=== forward style clusters ===")
    fs = summary_df[(summary_df["position"] == "F") & (summary_df["projection"] == "style")]
    LOG.info("\n%s", fs[["cluster_id", "n_members", "median_age_birth_year", "example_players"]].to_string(index=False))


if __name__ == "__main__":
    main()
