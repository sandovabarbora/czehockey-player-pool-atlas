"""Sensitivity analysis for league quality multipliers.

Locked critique decision: show how the quality-adjusted ranking changes when
each league multiplier is perturbed by ±20%. This is the single most
important credibility check for the methodology section — Morkes will look
for it. If the top-10 ranking is highly sensitive to a 20% multiplier swing
on (say) Liiga, that's a methodological weakness worth naming. If it's
stable, the multiplier choice is defensible despite being subjective.

Procedure:
  1. Take the canonical features parquet (forwards).
  2. For each perturbation scenario:
     - baseline (current multipliers from config/league_quality.yaml)
     - liiga × 0.8
     - liiga × 1.2
     - extraliga × 0.8
     - extraliga × 1.2
     - all leagues × 0.8 (extreme low)
     - all leagues × 1.2 (extreme high)
  3. Recompute quality-adjusted points/GP and quality-z.
  4. Track how each player's TOP-10 rank position changes vs baseline.
  5. Output sensitivity.parquet with one row per (scenario, player_rank),
     plus a sensitivity_summary.parquet with rank-change statistics.

Output:
  data/processed/sensitivity_rankings.parquet
  data/processed/sensitivity_summary.parquet
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet, write_parquet

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Scenario:
    name: str
    multiplier_overrides: dict[str, float]  # league -> new multiplier
    description: str


def _build_scenarios(baseline: dict[str, float]) -> list[Scenario]:
    out = [Scenario("baseline", dict(baseline), "current multipliers from config")]
    for league in ("liiga", "extraliga"):
        if league not in baseline:
            continue
        m_lo = dict(baseline)
        m_lo[league] = round(baseline[league] * 0.8, 4)
        out.append(Scenario(f"{league}_minus20", m_lo, f"{league} multiplier −20%"))
        m_hi = dict(baseline)
        m_hi[league] = round(baseline[league] * 1.2, 4)
        out.append(Scenario(f"{league}_plus20", m_hi, f"{league} multiplier +20%"))
    # Global extremes (informational)
    all_lo = {k: round(v * 0.8, 4) for k, v in baseline.items()}
    all_hi = {k: round(v * 1.2, 4) for k, v in baseline.items()}
    out.append(Scenario("all_minus20", all_lo, "every league multiplier −20%"))
    out.append(Scenario("all_plus20", all_hi, "every league multiplier +20%"))
    return out


def recompute_quality_rank(features: pd.DataFrame, multipliers: dict[str, float]) -> pd.DataFrame:
    """Recompute points_per_gp_quality for one scenario; return ranked frame.

    When a player has rows in multiple leagues for the same season (rare —
    a true mid-season cross-league move), keep the row with highest GP as
    the player's "primary" stint for the ranking.
    """
    df = features[features["season"] == features["season"].max()].copy()
    # Deduplicate canonical_id by keeping the highest-GP league for that season
    df = df.sort_values("GP", ascending=False).drop_duplicates("canonical_id", keep="first")
    df["scenario_multiplier"] = df["league"].map(multipliers).astype(float)
    df["points_per_gp_quality_alt"] = df["points_per_gp_shrunk"] * df["scenario_multiplier"]
    df = df.sort_values("points_per_gp_quality_alt", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    return df


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    baseline_multipliers: dict[str, float] = config.league_quality()["multipliers"]
    scenarios = _build_scenarios(baseline_multipliers)
    LOG.info("scenarios: %s", [s.name for s in scenarios])

    # Get baseline ranking
    base_df = recompute_quality_rank(features, baseline_multipliers)
    base_ranks = base_df.set_index("canonical_id")["rank"]

    all_rows: list[pd.DataFrame] = []
    summary: list[dict] = []
    for s in scenarios:
        scen_df = recompute_quality_rank(features, s.multiplier_overrides)
        scen_ranks = scen_df.set_index("canonical_id")["rank"]
        joined = pd.concat([base_ranks.rename("rank_baseline"),
                            scen_ranks.rename("rank_scenario")], axis=1, join="inner")
        joined["rank_delta"] = joined["rank_scenario"] - joined["rank_baseline"]
        joined["scenario"] = s.name
        joined["scenario_description"] = s.description
        joined = joined.reset_index()
        all_rows.append(joined)

        # Summary: how stable is top-10 across this scenario?
        top10_baseline = set(base_df.head(10)["canonical_id"])
        top10_scenario = set(scen_df.head(10)["canonical_id"])
        overlap = len(top10_baseline & top10_scenario)
        churn = 10 - overlap
        mean_abs_delta_top20 = joined.nsmallest(20, "rank_baseline")["rank_delta"].abs().mean()
        summary.append({
            "scenario": s.name,
            "description": s.description,
            "top10_overlap_with_baseline": overlap,
            "top10_churn": churn,
            "mean_abs_rank_delta_top20": round(float(mean_abs_delta_top20), 2),
        })

    rankings = pd.concat(all_rows, ignore_index=True)
    summary_df = pd.DataFrame(summary)
    write_parquet(rankings, config.PROCESSED_DIR / "sensitivity_rankings.parquet")
    write_parquet(summary_df, config.PROCESSED_DIR / "sensitivity_summary.parquet")

    LOG.info("=== sensitivity summary ===")
    LOG.info("\n%s", summary_df.to_string(index=False))


if __name__ == "__main__":
    main()
