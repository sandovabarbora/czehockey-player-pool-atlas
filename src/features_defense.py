"""Per-game features for defensemen across NHL + Liiga + Extraliga.

Mirrors features_forwards.py with the position filter set to "D". The
cross-league feature set is the same (G/GP, A/GP, P/GP, shots/GP, PIM/GP)
because Liiga + Extraliga don't expose defenseman-specific signals like
PP/PK TOI, shot attempts, xGA — those are all NHL-only.

What that means in practice: the cross-league defenseman projection
captures offensive production + penalty behavior. Defensive impact (shot
suppression, zone exits) is NOT in the cross-league vector and would
require either video tracking data or NHL-only enrichment.

Brief §4.3 defenseman feature list vs. what we deliver:
  1. Goals per 60                      → G/GP (cross-league)
  2. Primary assists per 60            → A/GP (cross-league, primary not separated)
  3. Shot attempts per 60              → shots/GP for NHL/Liiga (Extraliga NA)
  4. xGA per 60                        → NHL-only enrichment
  5. PP TOI per game                   → NHL-only enrichment
  6. PK TOI per game                   → NHL-only enrichment
  7. Penalty differential per 60       → PIM/GP (single-sided proxy)
  8. Ice time per game                 → NHL-only enrichment
  9. Age                               → birth_year
  10. League quality factor            → multiplier in quality projection

Shrinkage uses K=10 phantom games and per-(league) cohort medians,
computed across DEFENSEMEN only (so the prior reflects D production, not
forward production — much lower goal rates).

Inputs:
  data/processed/players.parquet
  data/raw/nhl_skaters_{season}.parquet (skater rows include D too)
  data/raw/liiga_skaters_{season}.parquet
  data/raw/extraliga_skaters_{season}.parquet

Outputs:
  data/processed/features_defense.parquet
"""

from __future__ import annotations

import logging

from src import config
from src.features_forwards import (
    PHANTOM_GAMES,
    PER_GAME_METRICS,
    SCALED_METRICS,
    add_quality_adjusted,
    aggregate_player_seasons,
    attach_canonical_ids,
    bayesian_shrink,
    compute_per_game_rates,
    z_score_within_position,
)
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet, write_parquet

LOG = logging.getLogger(__name__)


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    canonical = read_parquet(config.PROCESSED_DIR / "players.parquet")
    defense = canonical[
        (canonical["position_normalized"] == "D")
        & (canonical["czech_eligible_flag"] != "no")
    ].copy()
    LOG.info("defense pool: %d canonical players (eligible_flag != 'no')", len(defense))

    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    raw_stats = aggregate_player_seasons(seasons)
    joined = attach_canonical_ids(raw_stats, canonical)
    joined = joined[joined["canonical_id"].isin(set(defense["canonical_id"]))]
    LOG.info("joined to defense canonical: %d rows", len(joined))

    rates = compute_per_game_rates(joined)
    shrunk = bayesian_shrink(rates, k=PHANTOM_GAMES)
    full = add_quality_adjusted(shrunk)

    style_cols = [f"{m}_shrunk" for m in PER_GAME_METRICS]
    quality_cols = [f"{m}_quality" for m in PER_GAME_METRICS]
    full = z_score_within_position(full, style_cols + quality_cols)

    meta_cols = ["canonical_id", "first_name", "last_name", "position_normalized",
                 "birth_year", "czech_eligible_flag", "iihf_appearances", "sources"]
    meta = canonical[meta_cols].copy()
    full = full.merge(meta, on="canonical_id", how="left")

    write_parquet(full, config.PROCESSED_DIR / "features_defense.parquet")

    LOG.info("=== defense features summary ===")
    LOG.info("rows: %d (unique players: %d)", len(full), full["canonical_id"].nunique())
    LOG.info("by league: %s", full["league"].value_counts().to_dict())
    LOG.info("by season: %s", full["season"].value_counts().to_dict())


if __name__ == "__main__":
    main()
