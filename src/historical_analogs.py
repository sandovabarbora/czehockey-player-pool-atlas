"""Historical career-trajectory analog finder.

For a target Czech player at age X, find the k-nearest analogs (any
nationality, any era) whose stats AT AGE X most resemble the target's,
and show how those analogs' careers continued at ages X+1, X+2, ...

This is descriptive analog lookup, not prediction:
    "Kulich at 21 statisticky nejvíc připomíná Hejduka@21, Plekance@21,
     Voráčka@21. Hejduk @22 měl 41g; Plekanec @22 měl 14g; Voráček @22
     měl 14g." → reader interprets the range, the method does not predict.

This addresses a federation gap: hockey people know individual analogs,
but don't systematize the search across thousands of seasons of public
NHL data.

Data source: cached NHL landings (1183 players, mostly current rosters).
This is a limited reference set (no pre-2000 retirees). For a production
version we would supplement with hockey-reference scraping of historical
Czech NHL players (Jágr, Reichel, Hašek, Elias, Hejduk, Sýkora, etc.).
This PoC uses the current cache.

Output: data/processed/historical_analogs.parquet
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import write_parquet

LOG = logging.getLogger(__name__)

LANDING_CACHE = config.RAW_DIR / ".cache" / "nhl_landing"

# League quality multipliers — shared with main pipeline.
LEAGUE_QUALITY = {
    "NHL": 1.00, "AHL": 0.55, "SHL": 0.45, "Liiga": 0.42,
    "NL": 0.40, "Czechia": 0.35, "KHL": 0.55,
    # League IDs sometimes appear as abbrev; defaults below
}

# Target players (current Czech) to find analogs for.
# Selected to span positions and career stages.
TARGETS = [
    ("8483468", "Jiří Kulich",    "F"),
    ("8483460", "David Jiříček",  "D"),
    ("8478401", "Pavel Zacha",    "F"),
    ("8479425", "Filip Hronek",   "D"),
    ("8477956", "David Pastrňák", "F"),
]

# Window of ages to compare. We compare the target's "current age" against
# every other player's stats AT THE SAME AGE.
TRAJECTORY_FUTURE_AGES = 4  # show analogs' careers up to 4 years past comparison age


# -----------------------------------------------------------------------------
# Per-player career table from landing JSON
# -----------------------------------------------------------------------------


def _load_career(player_id: str) -> dict | None:
    p = LANDING_CACHE / f"{player_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _per_age_table(landing: dict) -> pd.DataFrame:
    """Build a per-age regular-season table for one player.

    Columns: age, league, GP, P, P_per_GP, P_per_GP_quality
    Filters: regular season, league with known quality multiplier, GP >= 5.
    """
    if not landing:
        return pd.DataFrame()
    birth = landing.get("birthDate")
    if not birth:
        return pd.DataFrame()
    try:
        birth_year = int(birth[:4])
    except ValueError:
        return pd.DataFrame()

    rows = []
    for s in (landing.get("seasonTotals") or []):
        if s.get("gameTypeId") != 2:  # regular season only
            continue
        league = s.get("leagueAbbrev")
        if league not in LEAGUE_QUALITY:
            continue
        season = s.get("season")
        if not season:
            continue
        # season e.g. 20242025 → start year 2024
        season_start = int(str(season)[:4])
        age = season_start - birth_year
        gp = s.get("gamesPlayed", 0)
        p  = s.get("points", 0) or 0
        if gp < 5 or p is None:
            continue
        p_per_gp = p / gp
        quality_mult = LEAGUE_QUALITY[league]
        rows.append({
            "player_id":         landing.get("playerId"),
            "first_name":        landing.get("firstName", {}).get("default"),
            "last_name":         landing.get("lastName",  {}).get("default"),
            "birth_country":     landing.get("birthCountry"),
            "position":          landing.get("position"),
            "season":            season_start,
            "age":               age,
            "league":            league,
            "GP":                gp,
            "P":                 p,
            "P_per_GP":          round(p_per_gp, 3),
            "P_per_GP_quality":  round(p_per_gp * quality_mult, 3),
            "league_quality":    quality_mult,
        })
    return pd.DataFrame(rows)


def _build_full_corpus() -> pd.DataFrame:
    """Load every cached landing → per-age career table."""
    frames: list[pd.DataFrame] = []
    n = 0
    for p in LANDING_CACHE.iterdir():
        if not p.name.endswith(".json"):
            continue
        landing = _load_career(p.stem)
        if landing is None:
            continue
        df = _per_age_table(landing)
        if not df.empty:
            frames.append(df)
        n += 1
    LOG.info("scanned %d cached landings, %d had usable career data", n, len(frames))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# -----------------------------------------------------------------------------
# Analog lookup
# -----------------------------------------------------------------------------


def _position_normalised(pos: str) -> str:
    """Map NHL position codes (or already-normalized labels) to F/D/G."""
    if pos in {"C", "L", "R", "F"}:
        return "F"
    if pos == "D":
        return "D"
    return "G"


def find_analogs(target_id: str, target_name: str, target_pos: str,
                 corpus: pd.DataFrame, k: int = 5) -> dict | None:
    """Find k nearest historical analogs to target at target's current age.

    Returns dict with target metadata + list of analogs (each with their
    subsequent trajectory up to TRAJECTORY_FUTURE_AGES years).
    """
    tgt_landing = _load_career(target_id)
    if tgt_landing is None:
        return None
    tgt_career = _per_age_table(tgt_landing)
    if tgt_career.empty:
        LOG.warning("no usable career data for target %s", target_name)
        return None

    # Use most-recent age as comparison point
    cmp_row = tgt_career.sort_values("age").iloc[-1]
    cmp_age = int(cmp_row["age"])
    tgt_norm_pos = _position_normalised(target_pos)

    # Build cohort: every player with a season at age cmp_age, same position,
    # excluding the target himself.
    cohort = corpus[
        (corpus["age"] == cmp_age) &
        (corpus["player_id"] != int(target_id))
    ].copy()
    cohort["pos_norm"] = cohort["position"].apply(_position_normalised)
    cohort = cohort[cohort["pos_norm"] == tgt_norm_pos]

    if cohort.empty:
        LOG.warning("no cohort for %s at age %d", target_name, cmp_age)
        return None

    # If a player has multiple rows at same age (multiple leagues), keep highest
    # GP row — typical for callups split between AHL and NHL.
    cohort = cohort.sort_values("GP", ascending=False).drop_duplicates(
        subset=["player_id"], keep="first"
    )

    # Distance: weighted on (P_per_GP_quality, GP, league_quality).
    # Use z-scores within cohort so units are comparable.
    feats = ["P_per_GP_quality", "GP", "league_quality"]
    cz = cohort[feats].copy()
    means = cz.mean()
    stds = cz.std().replace(0, 1)
    cz_z = (cz - means) / stds

    tgt_vec = pd.Series({
        "P_per_GP_quality": cmp_row["P_per_GP_quality"],
        "GP":               cmp_row["GP"],
        "league_quality":   cmp_row["league_quality"],
    })
    tgt_z = (tgt_vec - means) / stds

    cohort["distance"] = np.sqrt(((cz_z - tgt_z) ** 2).sum(axis=1))
    nearest = cohort.nsmallest(k, "distance")

    # For each analog, build subsequent trajectory
    analogs = []
    for _, a in nearest.iterrows():
        future = corpus[
            (corpus["player_id"] == a["player_id"]) &
            (corpus["age"] > cmp_age) &
            (corpus["age"] <= cmp_age + TRAJECTORY_FUTURE_AGES)
        ].copy()
        future = future.sort_values("GP", ascending=False).drop_duplicates(
            subset=["age"], keep="first"
        ).sort_values("age")

        trajectory_rows = [
            {
                "age": int(r["age"]),
                "league": r["league"],
                "GP": int(r["GP"]),
                "P": int(r["P"]),
                "P_per_GP": float(r["P_per_GP"]),
            }
            for _, r in future.iterrows()
        ]
        analogs.append({
            "player_id":     int(a["player_id"]),
            "name":          f"{a['first_name']} {a['last_name']}",
            "country":       a["birth_country"],
            "position":      a["position"],
            "league":        a["league"],
            "GP":            int(a["GP"]),
            "P":             int(a["P"]),
            "P_per_GP":      float(a["P_per_GP"]),
            "P_per_GP_quality": float(a["P_per_GP_quality"]),
            "distance":      round(float(a["distance"]), 3),
            "trajectory":    trajectory_rows,
        })

    return {
        "target_id":          target_id,
        "target_name":        target_name,
        "target_position":    target_pos,
        "comparison_age":     cmp_age,
        "target_league":      cmp_row["league"],
        "target_GP":          int(cmp_row["GP"]),
        "target_P":           int(cmp_row["P"]),
        "target_P_per_GP":    float(cmp_row["P_per_GP"]),
        "target_P_per_GP_quality": float(cmp_row["P_per_GP_quality"]),
        "n_cohort":           int(len(cohort)),
        "analogs":            analogs,
    }


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    corpus = _build_full_corpus()
    if corpus.empty:
        LOG.error("empty corpus, abort")
        return

    out_path = config.PROCESSED_DIR / "historical_analogs.json"
    results = []
    for pid, name, pos in TARGETS:
        r = find_analogs(pid, name, pos, corpus, k=5)
        if r:
            LOG.info("%s @%d: %d analogs, cohort N=%d",
                     name, r["comparison_age"], len(r["analogs"]), r["n_cohort"])
            for a in r["analogs"]:
                LOG.info("    %s (%s) — d=%.3f, %s, %d GP, %d P",
                         a["name"], a["country"], a["distance"],
                         a["league"], a["GP"], a["P"])
            results.append(r)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    LOG.info("wrote %s (%d targets)", out_path, len(results))


if __name__ == "__main__":
    main()
