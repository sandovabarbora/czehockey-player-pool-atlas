"""KMeans clustering with data-driven K selection.

Locked decision (from critique #4): K is NOT pre-chosen to match the brief's
six archetype labels. Instead, silhouette score is computed on K ∈ {4..8} for
forwards and {3..6} for defensemen, and the best K wins. Labels are post-hoc.

Inputs:
    data/processed/features_forwards.parquet
    data/processed/features_defense.parquet

Outputs:
    data/processed/clusters_forwards.parquet
        Columns: canonical_player_id, cluster_id_style, cluster_id_quality
    data/processed/clusters_defense.parquet  (same shape)
    data/processed/cluster_labels.json
        Hand-edited mapping cluster_id -> archetype label, after inspection.

Phase 1b Day 7 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)

K_RANGE_FORWARDS: tuple[int, ...] = (4, 5, 6, 7, 8)
K_RANGE_DEFENSE: tuple[int, ...] = (3, 4, 5, 6)


def cluster_all() -> None:
    raise NotImplementedError("Phase 1b Day 7")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Clustering with silhouette-driven K selection")
    cluster_all()


if __name__ == "__main__":
    main()
