"""Render the player pool Atlas (minimal first-cut for sanity / preview).

This is a thin Day-9-preview, NOT the full Jinja2/PDF report from the brief
(§7 Day 9-11). It writes a single SVG: outputs/atlas_forwards.svg, a
two-panel matplotlib figure showing the forward pool projected in PCA-2D
by both the STYLE and QUALITY-ADJUSTED projections, colored by cluster,
with top players annotated.

The full HTML/PDF report (templates/report.html.j2, weasyprint) is wired
to call into helpers here as it grows.
"""

from __future__ import annotations

import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet

LOG = logging.getLogger(__name__)

ACCENT_NAVY = "#1f3a5f"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
RULE = "#d4d4d4"

CLUSTER_PALETTE = [
    "#1f3a5f",  # accent navy
    "#7f8d9d",  # muted blue-grey
    "#b08968",  # warm tan
    "#7a5c63",  # plum
    "#5e7e64",  # forest
    "#9c6a4d",  # rust
    "#806c8d",  # muted purple
    "#6b8e75",  # sage
]


def _annotate_top_players(ax, df: pd.DataFrame, x_col: str, y_col: str,
                          rank_col: str, n: int = 12) -> None:
    """Label the top-n players by `rank_col` on the scatter."""
    top = df.nlargest(n, rank_col)
    for _, row in top.iterrows():
        if pd.isna(row[x_col]) or pd.isna(row[y_col]):
            continue
        label = f"{row['last_name']}"
        ax.annotate(
            label,
            (row[x_col], row[y_col]),
            xytext=(3, 3), textcoords="offset points",
            fontsize=7, color=INK,
            zorder=10,
        )


def render_forward_atlas() -> None:
    """Two-panel SVG: forward Atlas in style + quality projections."""
    coords_path = config.PROCESSED_DIR / "coords_forwards.parquet"
    coords = read_parquet(coords_path)
    # Use latest season only for visualization clarity
    latest_season = int(coords["season"].max())
    cur = coords[coords["season"] == latest_season].copy()
    LOG.info("rendering %d forwards for season %d", len(cur), latest_season)

    # Use quality z-score (computed elsewhere) as rank for annotation prioritization
    # If absent, fall back to PCA-y of the quality projection.
    feat_path = config.PROCESSED_DIR / "features_forwards.parquet"
    feat = read_parquet(feat_path)
    feat_cur = feat[feat["season"] == latest_season][["canonical_id", "points_per_gp_quality_z"]]
    cur = cur.merge(feat_cur, on="canonical_id", how="left")
    cur["rank"] = cur["points_per_gp_quality_z"].fillna(-99)

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(12, 6))
    fig.patch.set_facecolor("white")

    for ax, proj_label, title in (
        (ax_left, "style", "Style mapa (bez ligových násobiček)"),
        (ax_right, "quality", "Kvalitou upravená mapa (s násobiči)"),
    ):
        x_col, y_col = f"pca_x_{proj_label}", f"pca_y_{proj_label}"
        c_col = f"cluster_id_{proj_label}"
        sub = cur.dropna(subset=[x_col, y_col]).copy()
        sub[c_col] = sub[c_col].fillna(-1).astype(int)

        cluster_ids = sorted(sub[c_col].unique())
        for cid in cluster_ids:
            color = CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)] if cid >= 0 else "#cccccc"
            m = sub[c_col] == cid
            ax.scatter(
                sub.loc[m, x_col], sub.loc[m, y_col],
                s=18, c=color, alpha=0.7,
                edgecolors="white", linewidths=0.5,
                label=f"Cluster {cid}" if cid >= 0 else "Unclustered",
            )

        # Highlight Czech NT regulars (IIHF appearances >= 1) with a ring
        nt = sub[sub["iihf_appearances"].fillna(0) >= 1]
        ax.scatter(
            nt[x_col], nt[y_col],
            s=80, facecolors="none", edgecolors=ACCENT_NAVY,
            linewidths=1.2, alpha=0.9, zorder=5,
            label="Reprezentace MS 2024/25",
        )

        _annotate_top_players(ax, sub, x_col, y_col, "rank", n=12)

        ax.set_title(title, fontsize=11, fontfamily="serif", color=INK)
        ax.set_xlabel("PC1", fontsize=9, color=MUTED)
        ax.set_ylabel("PC2", fontsize=9, color=MUTED)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(RULE)
        ax.spines["bottom"].set_color(RULE)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.legend(loc="lower right", fontsize=7, frameon=False)

    fig.suptitle(
        f"Český hokej — Útočníci ({latest_season}-{latest_season + 1})",
        fontsize=13, fontfamily="serif", color=INK, y=1.0,
    )
    fig.text(
        0.5, -0.02,
        "PCA projekce z 4D feature vektoru (G/GP, A/GP, PIM/GP, věk). "
        "Cluster ID z KMeans + silhouette. Modré kroužky = MS 2024/25 účastníci.",
        ha="center", fontsize=8, color=MUTED, fontfamily="sans-serif",
    )
    plt.tight_layout()
    out = config.OUTPUTS_DIR / "atlas_forwards.svg"
    plt.savefig(out, bbox_inches="tight", format="svg")
    plt.close(fig)
    LOG.info("wrote %s", out)


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    render_forward_atlas()


if __name__ == "__main__":
    main()
