"""Intervals, spreads and splits for the question pages, from the question outputs.

The question modules report point values: medians over players, means over seasons, means over
tournaments. This module adds the uncertainty or spread that goes next to each of them, and the
splits the pages need, without changing any existing output:

  q3  the range of the peers that enter each median, and the Czech under-22 cells season by
      season, 2020/21-2025/26 (the question itself is one season)
  q4  per league, the min-max of the seasonal shares and a 95 % bootstrap interval of their
      mean, resampling seasons; the Extraliga-to-league ratios with the same resampling (paired
      by season)
  q5  the Czech median ratios per league (and per position in the NHL) with a 95 % bootstrap
      interval, resampling players (all of a player's seasons move together)
  q6  the Czech mean roster shares for 2010-2022 and 2023-2026, and without the 2018 and 2022
      Olympics (no NHL players took part in either), and the placement rule of every Czech row
  q7  the Czech goalkeepers' median save % minus the league median, per league, with a 95 %
      bootstrap interval, resampling goalkeepers

Percentile intervals, `REPS` resamples, seed `SEED`; a rebuild gives the same file.

    python -m src.analysis.intervals   -> outputs/intervals.json
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import numpy as np

from src.analysis import common, linking, q3_cohort_gaps, q5_abroad
from src.nations import HOME

LOG = logging.getLogger(__name__)

REPS = 10_000
SEED = 20260929
LEVEL = 0.95
Q3_SEASONS = range(2020, common.LAST_SEASON + 1)
Q4_LEAGUES = ("Extraliga", "Liiga", "SHL")
Q5_LEAGUES = ("NHL", "Liiga", "SHL")
Q7_LEAGUES = ("NHL", "Liiga", "SHL", "NL")
Q6_SPLIT_YEAR = 2022
Q6_NO_NHL = (("OG", 2018), ("OG", 2022))
Q6_CATS = ("1", "2", "home", "khl", "other", "unknown")


def _pct(draws: np.ndarray) -> tuple[float, float]:
    a = (1 - LEVEL) / 2
    return float(np.quantile(draws, a)), float(np.quantile(draws, 1 - a))


def cluster_median(values: dict[str, list[float]], rng: np.random.Generator) -> dict[str, Any] | None:
    """Median over all rows, with a percentile interval from resampling the clusters (players)."""
    keys = [k for k, v in values.items() if v]
    if not keys:
        return None
    rows = [np.asarray(values[k], dtype=float) for k in keys]
    point = float(np.median(np.concatenate(rows)))
    draws = np.empty(REPS)
    for i in range(REPS):
        pick = rng.integers(0, len(rows), len(rows))
        draws[i] = np.median(np.concatenate([rows[j] for j in pick]))
    lo, hi = _pct(draws)
    return {"median": point, "lo": lo, "hi": hi, "clusters": len(keys), "rows": int(sum(len(r) for r in rows))}


def _by_player(rows: list[dict[str, Any]], field: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {}
    for r in rows:
        v = r.get(field)
        if v is None or not np.isfinite(v):
            continue
        out.setdefault(r["person_id"], []).append(float(v))
    return out


def q5(q5_out: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    players = q5_out["players"]
    out: dict[str, Any] = {}
    for lg in Q5_LEAGUES:
        rows = [p for p in players if p["league"] == lg]
        out[lg] = {m: cluster_median(_by_player(rows, f), rng) for m, f in (("toi", "toi_ratio"), ("ppg", "ppg_ratio"))}
    out["NHL_by_position"] = {
        pos: {
            m: cluster_median(_by_player([p for p in players if p["league"] == "NHL" and p["position"] == pos], f), rng)
            for m, f in (("toi", "toi_ratio"), ("ppg", "ppg_ratio"))
        }
        for pos in ("F", "D")
    }
    return out


def q7(q7_out: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    players = q7_out["abroad"]["players"]
    return {
        lg: cluster_median(_by_player([p for p in players if p["league"] == lg], "save_pct_minus_median"), rng)
        for lg in Q7_LEAGUES
    }


def _season_mean(vals: np.ndarray, rng: np.random.Generator) -> dict[str, Any]:
    idx = rng.integers(0, len(vals), (REPS, len(vals)))
    lo, hi = _pct(vals[idx].mean(axis=1))
    return {"mean": float(vals.mean()), "lo": lo, "hi": hi, "min": float(vals.min()), "max": float(vals.max()), "seasons": len(vals)}


def q4(q4_out: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    lg = q4_out["leagues"]
    out: dict[str, Any] = {"leagues": {}, "ratio_to_home": {}}
    series: dict[str, dict[str, np.ndarray]] = {}
    for name in Q4_LEAGUES:
        rows = [r for r in lg[name]["seasons"] if r.get("measured")]
        series[name] = {
            "games": np.array([r["u21_games_share"] for r in rows], dtype=float),
            "toi": np.array([r["u21_toi_share"] for r in rows], dtype=float),
        }
        out["leagues"][name] = {m: _season_mean(v, rng) for m, v in series[name].items()}
        out["leagues"][name]["min_season"] = {
            m: rows[int(np.argmin(v))]["season"] for m, v in series[name].items()
        }
        out["leagues"][name]["max_season"] = {
            m: rows[int(np.argmax(v))]["season"] for m, v in series[name].items()
        }
    home = series["Extraliga"]
    for name in Q4_LEAGUES[1:]:
        other = series[name]
        n = len(home["games"])
        if len(other["games"]) != n:
            continue
        idx = rng.integers(0, n, (REPS, n))
        out["ratio_to_home"][name] = {}
        for m in ("games", "toi"):
            draws = home[m][idx].mean(axis=1) / other[m][idx].mean(axis=1)
            lo, hi = _pct(draws)
            out["ratio_to_home"][name][m] = {"ratio": float(home[m].mean() / other[m].mean()), "lo": lo, "hi": hi}
    return out


def _mean_shares(events: list[dict[str, Any]]) -> dict[str, Any]:
    shares = {c: float(np.mean([e[c] / e["players"] for e in events])) for c in Q6_CATS}
    return {"events": len(events), "first": min(e["year"] for e in events), "last": max(e["year"] for e in events), "shares": shares}


def q6(q6_out: dict[str, Any]) -> dict[str, Any]:
    ev = q6_out["home_by_event"]
    early = [e for e in ev if e["year"] <= Q6_SPLIT_YEAR]
    late = [e for e in ev if e["year"] > Q6_SPLIT_YEAR]
    with_nhl = [e for e in ev if (e["event"], e["year"]) not in Q6_NO_NHL]
    rows = q6_out["home_players"]
    return {
        "all": _mean_shares(ev),
        "to_2022": _mean_shares(early),
        "from_2023": _mean_shares(late),
        "without_2018_2022_olympics": _mean_shares(with_nhl),
        "no_nhl_events": [{"event": e, "year": y} for e, y in Q6_NO_NHL],
        "home_basis": dict(Counter(r["basis"] for r in rows).most_common()),
        "home_rows": len(rows),
        "home_unknown": sum(1 for r in rows if r["category"] == "unknown"),
    }


def q3(q3_out: dict[str, Any], lk: linking.Linked | None) -> dict[str, Any]:
    ranges = []
    for c in q3_out["cells"]:
        vals = [c["per_million"][p] for p in c["peers_in_median"]]
        ranges.append({"position": c["position"], "age_band": c["age_band"], "peers": len(vals),
                       "peer_min": float(min(vals)), "peer_max": float(max(vals)),
                       "peers_at_zero": sum(1 for v in vals if v == 0)})
    by_season = []
    if lk is not None:
        pop = common.population_table()
        for y in Q3_SEASONS:
            per = q3_cohort_gaps.cohort_table(lk.stints, y)
            for c in q3_cohort_gaps.gaps(per, pop, y):
                if c["age_band"] == "≤21" and c["position"] in ("F", "D"):
                    by_season.append({"season": common.season_label(y), "position": c["position"],
                                      "count": c["counts"][HOME], "peer_median": c["peer_median"],
                                      "peers": len(c["peers_in_median"]), "shortfall": c["shortfall"]})
    return {"peer_range": ranges, "u21_by_season": by_season}


def q5_group_sizes(lk: linking.Linked | None) -> dict[str, int]:
    """How many qualifying skaters each league-season-position median in q5 is taken over."""
    if lk is None:
        return {}
    s = q5_abroad.with_ratios(lk.stints)
    s = s[s["season_start"].between(q5_abroad.FIRST, q5_abroad.LAST)]
    return {
        f"{lg}|{common.season_label(int(y))}|{p}": int(len(g))
        for (lg, y, p), g in s.groupby(["league", "season_start", "position"])
    }


def run(outputs: dict[str, dict[str, Any]], lk: linking.Linked | None) -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    return {
        "definitions": {
            "bootstrap": f"{LEVEL:.0%} percentile interval, {REPS} resamples, seed {SEED}",
            "reps": REPS,
            "seed": SEED,
            "q3": "peer range: min and max per million over the peers in each median; "
            "u21_by_season: the Czech ≤21 cells for each season, computed as q3_cohort_gaps",
            "q4": "mean of the measured seasonal shares; interval from resampling seasons; "
            "ratio_to_home resamples the same seasons for both leagues",
            "q5": "median of Czech player-season ratios; interval from resampling players",
            "q6": "mean over tournaments of the roster share; to_2022 is 2010-2022, from_2023 is 2023-2026",
            "q7": "median of Czech goalkeeper-season save % minus the league-season median; "
            "interval from resampling goalkeepers",
        },
        "q3": q3(outputs["q3_cohort_gaps"], lk),
        "q4": q4(outputs["q4_youth_ice_time"], rng),
        "q5": q5(outputs["q5_abroad"], rng),
        "q5_group_n": q5_group_sizes(lk),
        "q6": q6(outputs["q6_national_team"]),
        "q7": q7(outputs["q7_goalkeepers"], rng),
    }


def main() -> None:
    names = ("q3_cohort_gaps", "q4_youth_ice_time", "q5_abroad", "q6_national_team", "q7_goalkeepers")
    outputs = {n: common.read_output(f"{n}.json") for n in names}
    out = run(outputs, linking.linked())
    path = common.write_output(
        "intervals.json", out, [*linking.SNAPSHOT_FILES, "population.parquet"]
    )
    LOG.info("wrote %s", path)


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
