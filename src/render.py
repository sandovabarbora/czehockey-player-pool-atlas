"""Render the final report (HTML + PDF) via Jinja2.

Inputs:
    data/processed/players.parquet
    data/processed/features_*.parquet
    data/processed/coords_*.parquet
    data/processed/clusters_*.parquet
    data/processed/trajectory.parquet
    data/processed/pca_loadings.parquet
    config/nt_veterans.yaml

Outputs:
    outputs/index.html
    outputs/report.pdf

Locked decisions:
    - Two-tiered structure: Executive Summary at top, Methodology below
    - PDF promoted to critical path (not stretch)
    - Czech NT veterans visually highlighted (accent color)
    - Limitations section mandatory, in Czech, >= 200 words

Phase 1c Day 9-11 implementation target.
"""

from __future__ import annotations

import logging

from src import config
from src.logging_setup import setup as logging_setup

LOG = logging.getLogger(__name__)


def render_html() -> None:
    raise NotImplementedError("Phase 1c Day 9")


def render_pdf() -> None:
    raise NotImplementedError("Phase 1c Day 11")


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    LOG.info("Rendering HTML report")
    render_html()
    LOG.info("Rendering PDF report")
    render_pdf()


if __name__ == "__main__":
    main()
