"""The data the interactive charts draw: docs/charts/report.json and docs/atlas/pool.json.

Both are cut down from outputs/*.json (no recomputation beyond regrouping), with short keys
where a file is large, so the pages load quickly.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.nations import BY_ISO3, HOME, ISO3
from src.web.context import AGE_BANDS

RUNG_ORDER = {"1": 0, "2": 1, "home": 2, "other": 3}


def _r(x: float | None, d: int = 4) -> float | None:
    return None if x is None else round(float(x), d)


def report_data(o: dict[str, Any]) -> dict[str, Any]:
    q1, q2, q3, q4, q5, q6, q7 = (
        o[k]
        for k in (
            "q1_per_million",
            "q2_break_model",
            "q3_cohort_gaps",
            "q4_youth_ice_time",
            "q5_abroad",
            "q6_national_team",
            "q7_goalkeepers",
        )
    )
    nations = [{"iso3": c, "name": BY_ISO3[c].name} for c in ISO3]

    def series(block: dict) -> dict:
        return {
            "seasons": block["seasons"],
            "nations": {
                c: {"n": v["n"], "pm": [_r(x) for x in v["per_million"]]} for c, v in block["nations"].items()
            },
        }

    def bars(rows: list[dict]) -> list[dict]:
        return [
            {
                "iso3": n["iso3"],
                "name": n["name"],
                "nhl": n["nhl"],
                "nhl_pm": _r(n["nhl_per_million"]),
                "top5": n["top5"],
                "top5_pm": _r(n["top5_per_million"]),
            }
            for n in rows
        ]

    top5 = series(q1["top5_series"])
    top5["complete"] = [c["complete"] for c in q1["top5_series"]["coverage"]]

    q2_out = {"seasons": q2["seasons"], "nations": {}}
    for c, nat in q2["nations"].items():
        q2_out["nations"][c] = {
            "name": BY_ISO3[c].name,
            "n": nat["n"],
            "median": [_r(x, 2) for x in nat["fitted"]["median"]],
            "lo": [_r(x, 2) for x in nat["fitted"]["lo"]],
            "hi": [_r(x, 2) for x in nat["fitted"]["hi"]],
            "steps": [
                {
                    "order": s["order"],
                    "direction": s["direction"],
                    "marginal": [_r(x) for x in s["marginal"]],
                    "modal": s["modal"],
                    "factor": s["delta_factor"],
                    "p_down": s["p_down"],
                }
                # a fit that fails the convergence rule dates nothing
                for s in (nat["break"]["steps"] if nat["diagnostics"].get("pass", True) else [])
            ],
        }

    q3_rows = []
    for c in q3["cells"]:
        if c["position"] not in ("F", "D", "G") or c["age_band"] not in AGE_BANDS:
            continue
        q3_rows.append(
            {
                "position": c["position"],
                "band": c["age_band"],
                "pm": {k: _r(v) for k, v in c["per_million"].items()},
                "counts": c["counts"],
                "median": _r(c["peer_median"]),
                "in_median": c["peers_in_median"],
                "shortfall": _r(c["shortfall"], 2),
            }
        )
    pos_order = {"F": 0, "D": 1, "G": 2}
    q3_rows.sort(key=lambda r: (pos_order[r["position"]], AGE_BANDS.index(r["band"])))

    seasons4 = [s["season"] for s in q4["leagues"]["Extraliga"]["seasons"]]
    q4_out = {"seasons": seasons4, "leagues": {}}
    for lg, v in q4["leagues"].items():
        by = {s["season"]: s for s in v["seasons"]}
        q4_out["leagues"][lg] = {
            "games": [_r(by[s]["u21_games_share"]) if s in by else None for s in seasons4],
            "toi": [_r(by[s].get("u21_toi_share")) if s in by else None for s in seasons4],
            "measured": [bool(by[s]["measured"]) if s in by else False for s in seasons4],
            "known": [_r(by[s]["age_known_games_share"]) if s in by else None for s in seasons4],
        }

    q5_out = {
        "window": q5["definitions"]["window"],
        "leagues": {
            lg: {
                c: {
                    "toi": _r(v["median_toi_ratio"]),
                    "ppg": _r(v["median_ppg_ratio"]),
                    "n": v["player_seasons"],
                    "players": v["players"],
                }
                for c, v in per.items()
            }
            for lg, per in q5["summary"].items()
        },
        "home_by_position": q5["home_by_position"],
    }

    cats = ["1", "2", "home", "khl", "other", "unknown"]
    q6_out = {
        "categories": cats,
        "mean_shares": {c: {k: _r(v.get(k, 0)) for k in cats} for c, v in q6["mean_shares"].items()},
        "home_by_event": [{**{k: e.get(k, 0) for k in cats}, "event": e["event"], "year": e["year"], "players": e["players"]} for e in q6["home_by_event"]],
    }

    q7_out = {
        "season": q7["per_million"]["season"],
        "bars": [
            {
                "iso3": n["iso3"],
                "name": n["name"],
                "nhl": n["nhl"],
                "nhl_pm": _r(n["nhl_per_million"]),
                "top5": n["top5"],
                "top5_pm": _r(n["top5_per_million"]),
            }
            for n in q7["per_million"]["nations"]
        ],
        "peer_median": q7["per_million"]["peer_median"],
        "nhl_series": series(q7["nhl_series"]),
    }

    return {
        "home": HOME,
        "nations": nations,
        "q1": {
            "season": q1["headline"]["season"],
            "bars": bars(q1["headline"]["nations"]),
            "peer_median": q1["headline"]["peer_median"],
            "nhl_series": series(q1["nhl_series"]),
            "top5_series": top5,
        },
        "q2": q2_out,
        "q3": {"rows": q3_rows},
        "q4": q4_out,
        "q5": q5_out,
        "q6": q6_out,
        "q7": q7_out,
    }


def pool_data(pool: dict[str, Any]) -> dict[str, Any]:
    """The pool list, compact: one row per player, one entry per season and league."""
    counts = pool["counts"]
    seasons = sorted(counts["seasons"])
    by_season_rung: dict[str, dict[str, int]] = {s: defaultdict(int) for s in seasons}
    players = []
    for p in pool["players"]:
        rows = []
        best_by_season: dict[str, str] = {}
        for s in p["seasons"]:
            goalie = "save_pct" in s
            rows.append(
                [
                    s["season"],
                    s["league"],
                    s["rung"],
                    s.get("team") or "",
                    int(s["games"] or 0),
                    (_r(s.get("save_pct"), 4) if goalie else int(s.get("goals") or 0)),
                    (int(s.get("goals_against") or 0) if goalie else int(s.get("assists") or 0)),
                    (None if goalie else int(s.get("points") or 0)),
                    _r(s.get("toi_per_game_s"), 1),
                    1 if s.get("qualifies") else 0,
                ]
            )
            prev = best_by_season.get(s["season"])
            if prev is None or RUNG_ORDER[s["rung"]] < RUNG_ORDER[prev]:
                best_by_season[s["season"]] = s["rung"]
        for season, r in best_by_season.items():
            if season in by_season_rung:
                by_season_rung[season][r] += 1
        players.append(
            {
                "id": p["person_id"],
                "n": p["name"],
                "b": p.get("birth_year"),
                "bd": p.get("birth_date"),
                "p": p.get("position"),
                "nb": p["nat_basis"],
                "r": p["best_rung"],
                "l": p["latest"],
                "g": int(p.get("games") or 0),
                "s": rows,
            }
        )
    return {
        "latest": counts["latest_season"],
        "seasons": seasons,
        "by_season_rung": {s: dict(v) for s, v in by_season_rung.items()},
        "fields": ["season", "league", "rung", "team", "games", "goals|save_pct", "assists|goals_against", "points", "toi_per_game_s", "qualifies"],
        "players": players,
    }
