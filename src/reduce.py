"""Dimensionality reduction: PCA + UMAP for both projections (style + quality).

Inputs:
    data/processed/features_forwards.parquet
    data/processed/features_defense.parquet

Outputs:
    data/processed/coords_forwards.parquet
        Columns: canonical_player_id, pca_x_style, pca_y_style, umap_x_style,
                 umap_y_style, pca_x_quality, pca_y_quality, umap_x_quality,
                 umap_y_quality
    data/processed/coords_defense.parquet  (same shape)
    data/processed/pca_loadings.parquet
        Per-position PCA loadings for the methodology section.

Locked decisions:
    - Random seed: RANDOM_SEED from src.config (=42)
    - UMAP params: n_neighbors=15, min_dist=0.3
    - Build BOTH style + quality projections (no choice between them)

Phase 1b Day 7 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

UMAP_N_NEIGHBORS: int = 15
UMAP_MIN_DIST: float = 0.3


def reduce_all() -> None:
    raise NotImplementedError("Phase 1b Day 7")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Reducing feature vectors with PCA + UMAP (seed=%d)", config.RANDOM_SEED)
    reduce_all()


if __name__ == "__main__":
    main()
