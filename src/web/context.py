"""The template context: every number the two pages state, read from outputs/*.json.

Nothing here is a constant about the data. Words that depend on a number (ranks,
"above"/"below", a rise or a fall) are chosen from the number, so a rebuilt output
cannot leave a sentence saying the opposite of its figure.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path
from statistics import median
from typing import Any

from src import config
from src.nations import BY_ISO3, HOME, ISO3
from src.web import fmt

OUTPUT_FILES = (
    "linking",
    "q1_per_million",
    "q2_break_model",
    "q3_cohort_gaps",
    "q4_youth_ice_time",
    "q5_abroad",
    "q6_national_team",
    "q7_goalkeepers",
    "pool",
)

HOME_NAME = BY_ISO3[HOME].name
PEERS = [c for c in ISO3 if c != HOME]
AGE_BANDS = ("≤21", "22–25", "26–29", "30+")
BAND_WORD = {"≤21": "21 or under", "22–25": "22–25", "26–29": "26–29", "30+": "30 or over"}
POSITION_WORD = {"F": "forwards", "D": "defencemen", "G": "goalkeepers"}
CATEGORY_LABEL = {
    "1": "NHL",
    "2": "rung 2 (SHL, Liiga, NL, DEL)",
    "home": "Czech Extraliga",
    "khl": "KHL",
    "other": "other league",
    "unknown": "not placed",
}
LEAGUE_NAME = {
    "NHL": "NHL",
    "SHL": "SHL",
    "Liiga": "Liiga",
    "NL": "National League",
    "DEL": "DEL",
    "Extraliga": "Extraliga",
}


def load_outputs(outputs_dir: Path | None = None) -> dict[str, Any]:
    root = outputs_dir or config.OUTPUTS_DIR
    return {name: json.loads((root / f"{name}.json").read_text(encoding="utf-8")) for name in OUTPUT_FILES}


def access_date(path: Path) -> str:
    """The day a snapshot file was written: its last commit, else its modification time."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cs", "--", str(path)],
            cwd=config.ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
    except OSError:
        out = ""
    if out:
        return out
    if path.exists():
        return dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    return "unknown"


# --- per question ---------------------------------------------------------------------


def _q1(q1: dict) -> dict:
    head = q1["headline"]
    nations = head["nations"]
    home = head["home"]
    by_nhl = sorted(nations, key=lambda n: n["rank_nhl"])
    top_nhl = by_nhl[0]
    series = q1["nhl_series"]
    peak = q1["nhl_home_peak"]
    cov = q1["top5_series"]
    complete = cov["complete_seasons"]
    sens = head["sensitivity"]
    return {
        "season": head["season"],
        "n_nations": len(nations),
        "home": home,
        "peer_median": head["peer_median"],
        "top_nhl": top_nhl,
        "leaders_nhl": by_nhl[:2],
        "peak": peak,
        "peak_ratio": peak["latest"]["n"] / peak["n"],
        "first_season": series["seasons"][0],
        "first_n": series["nations"][HOME]["n"][0],
        "top5_first_season": cov["seasons"][0],
        "complete_first": complete[0] if complete else None,
        "complete_last": complete[-1] if complete else None,
        "n_complete": len(complete),
        "sens_any": sens["any_game"],
        "sens_fixed": sens["fixed_20_games"],
        "threshold_def": q1["definitions"]["threshold"],
        "coverage": head["coverage"]["leagues"],
        "table": sorted(nations, key=lambda n: n["rank_top5"]),
        "home_series": [
            {"season": se, "n": n, "pm": pm}
            for se, n, pm in zip(series["seasons"], series["nations"][HOME]["n"], series["nations"][HOME]["per_million"], strict=True)
        ],
        "nhl_vs_median_word": "above" if home["nhl_per_million"] > head["peer_median"]["nhl_per_million"] else "below",
        "top5_vs_median_word": "above" if home["top5_per_million"] > head["peer_median"]["top5_per_million"] else "below",
    }


def _q2(q2: dict) -> dict:
    out: dict[str, Any] = {"seasons": q2["seasons"], "definitions": q2["definitions"]}
    for code, nat in q2["nations"].items():
        brk = nat["break"]
        fall_step = next((s for s in brk["steps"] if s["direction"] == "down"), None)
        ups = [s for s in brk["steps"] if s["direction"] == "up"]
        out[code] = {
            "name": BY_ISO3[code].name,
            "steps": brk["steps"],
            "fall": fall_step,
            "ups": ups,
            "only_up": fall_step is None,
            "fitted": nat["fitted"],
            "diag": nat["diagnostics"],
        }
    cze = out[HOME]
    if cze["fall"]:
        marg = cze["fall"]["marginal"]
        spread = [q2["seasons"][i] for i, p in enumerate(marg) if p >= 0.03]
        cze["fall_spread"] = (spread[0], spread[-1]) if spread else None
        cze["fall_mass_in_spread"] = sum(p for p in marg if p >= 0.03)
    cze["sharp"] = bool(cze["fall"] and cze["fall"]["modal"]["prob"] >= 0.5)
    out["max_rhat"] = max(n["diagnostics"]["max_rhat"] for n in q2["nations"].values())
    out["divergences"] = sum(n["diagnostics"]["n_divergences"] for n in q2["nations"].values())
    out["compared"] = [c for c in q2["nations"] if c != HOME]
    return out


def _q3(q3: dict, population_m: float) -> dict:
    cells = [c for c in q3["cells"] if c["position"] in POSITION_WORD and c["age_band"] in AGE_BANDS]
    u21 = [c for c in cells if c["age_band"] == "≤21" and c["position"] in ("F", "D")]
    u21_home = sum(c["counts"][HOME] for c in u21)
    shortfalls = [s for s in q3["largest_shortfalls"] if s["shortfall"] > 0]
    excluded_age = sorted(
        {c for band in q3["by_age_band"] for c in PEERS if c not in band["peers_in_median"]}
    )
    by_pos = {b["position"]: b for b in q3["by_position"]}
    return {
        "season": q3["definitions"]["season"],
        "cells": cells,
        "u21_home": u21_home,
        "shortfalls": shortfalls,
        "top_shortfall": shortfalls[0] if shortfalls else None,
        "second_shortfall": shortfalls[1] if len(shortfalls) > 1 else None,
        "excluded_age": [BY_ISO3[c].name for c in excluded_age],
        "by_position": by_pos,
        "unknown": q3["unknown"],
        "population_m": population_m,
    }


def _q4(q4: dict) -> dict:
    lg = q4["leagues"]
    home = lg["Extraliga"]["summary"]
    peers = {k: lg[k]["summary"] for k in ("Liiga", "SHL")}
    unmeasured = {k: lg[k] for k in ("NL", "DEL")}
    unmeasured_known = {
        k: sum(s["age_known_games_share"] for s in v["seasons"]) / len(v["seasons"]) for k, v in unmeasured.items()
    }
    lowest_peer_games = min(p["mean_u21_games_share"] for p in peers.values())
    return {
        "window": q4["definitions"]["window"],
        "home": home,
        "peers": peers,
        "comparison": q4["comparison"],
        "unmeasured_known": unmeasured_known,
        "half_or_less": home["mean_u21_games_share"] <= 0.6 * lowest_peer_games,
        "latest_season": home["latest"]["season"],
        "measured_threshold": q4["definitions"]["measured"],
        "n_seasons": len(lg["Extraliga"]["seasons"]),
    }


def _q5(q5: dict) -> dict:
    s = q5["summary"]
    home = {lg: s[lg][HOME] for lg in ("NHL", "Liiga", "SHL")}
    pos = q5["home_by_position"]
    return {
        "window": q5["definitions"]["window"],
        "home": home,
        "by_position": pos,
        "words": {lg: (fmt.ratio_words(v["median_toi_ratio"]), fmt.ratio_words(v["median_ppg_ratio"])) for lg, v in home.items()},
        "n_player_seasons": sum(v["player_seasons"] for v in home.values()),
        "unknown_position": q5["home_unknown_position"],
        "own_below_one": all(
            (s[lg][c]["median_toi_ratio"] or 1) < 1 for lg, c in (("Liiga", "FIN"), ("SHL", "SWE"))
        ),
    }


def _q6(q6: dict) -> dict:
    ms = q6["mean_shares"]
    home = ms[HOME]
    events = q6["home_by_event"]
    first = events[0]
    last = events[-1]
    n_events = len(events)
    peers_nhl = sorted(((c, ms[c]["1"]) for c in PEERS), key=lambda t: -t[1])
    return {
        "home": home,
        "n_events": n_events,
        "first_year": min(e["year"] for e in events),
        "last_event": last,
        "first_event": first,
        "last_label": f"{'Olympics' if last['event'] == 'OG' else 'World Championship'} {last['year']}",
        "basis_counts": q6["basis_counts"],
        "rules": q6["definitions"]["rules"],
        "roster_rows": len(q6["home_players"]),
        "nhl_rank": 1 + sum(1 for _, v in peers_nhl if v > home["1"]),
        "khl_note": home["khl"],
        "events": events,
        "last_khl_event": next((e for e in reversed(events) if e.get("khl", 0) > 0), None),
    }


def _q7(q7: dict, n_nations: int) -> dict:
    pm = q7["per_million"]
    home = next(n for n in pm["nations"] if n["iso3"] == HOME)
    rank_nhl = 1 + sum(1 for n in pm["nations"] if n["nhl_per_million"] > home["nhl_per_million"])
    series = q7["nhl_series"]["nations"][HOME]["n"]
    vals = [v for v in series if v is not None]
    ab = q7["abroad"]["summary"]
    youth = q7["youth"]
    nt = q7["national_team"]
    return {
        "season": pm["season"],
        "home": home,
        "rank_nhl": rank_nhl,
        "n_nations": n_nations,
        "peer_median": pm["peer_median"],
        "series_max": max(vals),
        "series_latest": series[-1],
        "series_is_max": series[-1] == max(vals),
        "abroad": ab,
        "youth": {k: v["mean_u24_games_share"] for k, v in youth.items()},
        "nt": nt,
        "nt_khl_share": nt["by_category"].get("khl", 0) / nt["roster_spots"],
        "nt_nhl_share": nt["by_category"].get("1", 0) / nt["roster_spots"],
        "extraliga_home_share": q7["extraliga_goal"][-1]["home_games_share"],
        "table": pm["nations"],
        "window_abroad": q7["definitions"]["window_abroad"],
        "home_series": list(zip(q7["nhl_series"]["seasons"], series, strict=True)),
    }


def _linking(lk: dict) -> dict:
    rows = []
    for league, r in lk["records_by_league"].items():
        rows.append({"league": LEAGUE_NAME.get(league, "Rosters" if league == "roster" else league), **r})
    return {
        "persons": lk["persons"],
        "with_nat": lk["persons_with_nationality"],
        "rows": rows,
        "conflicts": lk["conflicts"],
        "swapped": lk["roster_birth_dates_swapped"],
        "definitions": lk["definitions"],
    }


def _pool(pool: dict) -> dict:
    c = pool["counts"]
    return {
        "players": c["players"],
        "latest": c["in_latest_season"],
        "latest_season": c["latest_season"],
        "window": pool["definitions"]["window"],
        "by_rung": c["latest_by_rung"],
        "by_basis": c["by_nat_basis"],
        "eligibility_only": c["by_nat_basis"].get("eligibility", 0),
    }


def _population_m(q1: dict) -> float:
    home = next(n for n in q1["headline"]["nations"] if n["iso3"] == HOME)
    return home["population"] / 1e6


def _takeaways(c: dict) -> list[dict]:
    q1, q2, q3, q4, q5, q6 = (c[k] for k in ("q1", "q2", "q3", "q4", "q5", "q6"))
    h = q1["home"]
    pm = q1["peer_median"]
    leaders = q1["leaders_nhl"]
    cze = q2[HOME]
    fall = cze["fall"]
    out = []
    out.append({
        "head": (
            f"Per head, the Czech pool sits {q1['nhl_vs_median_word']} the peer median, "
            f"not at the bottom: {fmt.ordinal(h['rank_nhl'])} of {q1['n_nations']} in the NHL."
        ),
        "body": [
            f"{h['nhl']} Czech players reached the games threshold in the NHL in {q1['season']}, "
            f"{fmt.f2(h['nhl_per_million'])} per million inhabitants against a peer median of {fmt.f2(pm['nhl_per_million'])}. "
            f"Counting the four strongest European leagues as well, {h['top5']} players, {fmt.f2(h['top5_per_million'])} per million, "
            f"{fmt.ordinal(h['rank_top5'])} of {q1['n_nations']}.",
            f"{leaders[0]['name']} and {leaders[1]['name']} are in another class: "
            f"{fmt.f2(leaders[0]['nhl_per_million'])} and {fmt.f2(leaders[1]['nhl_per_million'])} NHL players per million, "
            f"about {round(min(leaders[0]['nhl_per_million'], leaders[1]['nhl_per_million']) / h['nhl_per_million'])} times the Czech rate.",
        ],
    })
    fall_txt = (
        f"The most likely season for a fall is {fall['modal']['season']}, with only {fmt.pct0(fall['modal']['prob'])} probability; "
        f"the step is {fmt.times(fall['delta_factor']['median'])} (90% interval {fmt.f2(fall['delta_factor']['lo'])}–{fmt.f2(fall['delta_factor']['hi'])})."
        if fall
        else "The model finds no downward step."
    )
    peers_up = [q2[k]["name"] for k in q2["compared"] if q2[k]["only_up"]]
    out.append({
        "head": (
            f"The Czech NHL group fell from {q1['peak']['n']} players in {q1['peak']['season']} to "
            f"{q1['peak']['latest']['n']} in {q1['peak']['latest']['season']}"
            + (" — gradually, not in one break." if not cze["sharp"] else ", in one break.")
        ),
        "body": [
            fall_txt
            + f" The fitted level is now {fmt.pct0(cze['fitted']['latest_to_peak'])} of its {cze['fitted']['peak']['season']} peak.",
            (f"{' and '.join(peers_up)} show only upward steps over the same seasons." if peers_up else ""),
        ],
    })
    top = q3["top_shortfall"]
    second = q3["second_shortfall"]
    out.append({
        "head": (
            "The gap is young: no Czech skater aged 21 or under reaches the games threshold in the NHL or rung 2."
            if q3["u21_home"] == 0
            else f"The gap is young: {q3['u21_home']} Czech skaters aged 21 or under reach the threshold in the NHL or rung 2."
        ),
        "body": [
            (
                f"The largest shortfall against the peer median is {POSITION_WORD[top['position']]} aged {BAND_WORD[top['age_band']]}: "
                f"{fmt.f1(top['shortfall'])} players"
                + (
                    f", then {POSITION_WORD[second['position']]} aged {BAND_WORD[second['age_band']]} ({fmt.f1(second['shortfall'])})."
                    if second
                    else "."
                )
            )
            if top
            else "No cohort is below the peer median."
        ],
    })
    lp = q4["peers"]
    out.append({
        "head": (
            f"At home, under-21 skaters get {fmt.pct(q4['home']['mean_u21_games_share'])} of Extraliga games; "
            f"the Liiga gives its young {fmt.pct(lp['Liiga']['mean_u21_games_share'])} and the SHL {fmt.pct(lp['SHL']['mean_u21_games_share'])}."
        ),
        "body": [
            f"On ice time the gap is wider: {fmt.pct(q4['home']['mean_u21_toi_share'])} against "
            f"{fmt.pct(lp['Liiga']['mean_u21_toi_share'])} and {fmt.pct(lp['SHL']['mean_u21_toi_share'])}, "
            f"averaged over {q4['window']}. In {q4['latest_season']} the Extraliga share was {fmt.pct(q4['home']['latest']['u21_games_share'])} of games."
        ],
    })
    hn = q5["home"]["NHL"]
    toi_w, ppg_w = q5["words"]["NHL"]
    toi_phrase = {"at": "play the median ice time", "above": "play more than the median ice time",
                  "below": "play less than the median ice time"}[toi_w]
    ppg_phrase = {"at": "score at the median rate", "above": "score above it", "below": "score below it"}[ppg_w]
    euro = [lg for lg in ("Liiga", "SHL") if q5["words"][lg] == ("above", "above")]
    euro_txt = f"; in the {' and the '.join(euro)} they are above the median on both" if euro else ""
    out.append({
        "head": f"Abroad, Czech skaters in the NHL {toi_phrase} for their position and {ppg_phrase}{euro_txt}.",
        "body": [
            f"Over {q5['window']}, Czech NHL skaters played {fmt.f2(hn['median_toi_ratio'])} times the median ice time of their position "
            f"and scored {fmt.f2(hn['median_ppg_ratio'])} times its points per game. In the Liiga the ratios are "
            f"{fmt.f2(q5['home']['Liiga']['median_toi_ratio'])} and {fmt.f2(q5['home']['Liiga']['median_ppg_ratio'])}, in the SHL "
            f"{fmt.f2(q5['home']['SHL']['median_toi_ratio'])} and {fmt.f2(q5['home']['SHL']['median_ppg_ratio'])}."
        ],
    })
    hs = q6["home"]
    three = sorted(((hs["1"], "the NHL"), (hs["home"], "the Extraliga"), (hs["khl"], "the KHL")), reverse=True)
    even = three[0][0] - three[-1][0] <= 0.08
    parts = [f"{name} ({fmt.pct0(v)})" for v, name in three]
    listed = ", ".join(parts[:-1]) + f" and {parts[-1]}"
    out.append({
        "head": (
            f"Since {q6['first_year']} the national team has drawn on {listed}"
            + (" in about equal parts" if even else "")
            + f"; rung 2 gives {fmt.pct0(hs['2'])}."
        ),
        "body": [
            f"Averaged over {q6['n_events']} World Championship and Olympic rosters."
            + (
                f" The KHL is outside the atlas's leagues, so {fmt.pct0(hs['khl'])} of the roster spots come from a league the atlas does not measure."
                if hs["khl"] >= 0.1
                else ""
            )
        ],
    })
    for t in out:
        t["body"] = [b for b in t["body"] if b]
    return out


def build(outputs_dir: Path | None = None, build_date: str | None = None) -> dict[str, Any]:
    o = load_outputs(outputs_dir)
    q1 = _q1(o["q1_per_million"])
    popm = _population_m(o["q1_per_million"])
    ctx: dict[str, Any] = {
        "home_name": HOME_NAME,
        "q1": q1,
        "q2": _q2(o["q2_break_model"]),
        "q3": _q3(o["q3_cohort_gaps"], popm),
        "q4": _q4(o["q4_youth_ice_time"]),
        "q5": _q5(o["q5_abroad"]),
        "q6": _q6(o["q6_national_team"]),
        "q7": _q7(o["q7_goalkeepers"], q1["n_nations"]),
        "linking": _linking(o["linking"]),
        "pool": _pool(o["pool"]),
        "population_m": popm,
        "peers": [BY_ISO3[c].name for c in PEERS],
        "category_label": CATEGORY_LABEL,
        "position_word": POSITION_WORD,
        "band_word": BAND_WORD,
        "build_date": build_date or dt.date.today().isoformat(),
        "sources": sources(),
        "f1": fmt.f1,
        "f2": fmt.f2,
        "pct": fmt.pct,
        "pct0": fmt.pct0,
        "num": fmt.num,
        "ordinal": fmt.ordinal,
        "times": fmt.times,
        "median": median,
    }
    ctx["take"] = _takeaways(ctx)
    return ctx


def sources() -> list[dict[str, str]]:
    snap = config.DATA_DIR / "snapshot"

    def cov(name: str) -> dict:
        p = snap / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    rosters = cov("rosters_sources.json")
    retrieved = sorted({p.get("retrieved", "") for p in rosters.get("pages", []) if p.get("retrieved")})
    pop = cov("population.json")
    rows = [
        ("NHL", "https://api.nhle.com/stats/rest", "NHL stats REST: skater and goalie summaries and bios per season, player career records", "nhl_skaters.parquet",
         "citizenship (nationalityCode), full birth date; time on ice from 1997/98"),
        ("Liiga", "https://liiga.fi", cov("liiga_coverage.json").get("source", "liiga.fi JSON API"), "liiga_skaters.parquet",
         "citizenship, full birth date; time on ice from 2014/15"),
        ("SHL", "https://www.shl.se", cov("shl_coverage.json").get("source", "shl.se statistics"), "shl_skaters.parquet",
         "citizenship where given (mostly N/A before about 2010), birth date; time on ice from 2009/10"),
        ("Extraliga", "https://www.hokej.cz", cov("extraliga_coverage.json").get("source", "hokej.cz"), "extraliga_skaters.parquet",
         "foreigner flag (eligibility), birth date from player profiles; time on ice from 2013/14"),
        ("DEL", "https://www.penny-del.org", cov("del_coverage.json").get("source", "penny-del.org"), "del_skaters.parquet",
         "licence nationality from 2022/23; no birth dates"),
        ("National League", "https://data.sihf.ch", cov("nl_coverage.json").get("source", "data.sihf.ch"), "nl_skaters.parquet",
         "Swiss or foreign licence (eligibility); no birth dates"),
        ("Eurostat", "https://ec.europa.eu/eurostat/databrowser/view/demo_gind/default/table", pop.get("source", "Eurostat demo_gind"), "population.parquet",
         "population on 1 January" + (f"; dataset updated {pop['updated'][:10]}" if pop.get("updated") else "")),
        ("Wikipedia", "https://en.wikipedia.org", "English Wikipedia roster articles for the World Championship and the Olympics, each at a fixed revision (CC BY-SA 4.0)", "rosters.parquet",
         f"{len(rosters.get('pages', []))} roster pages, {len(rosters.get('player_articles', []))} player articles for missing birth dates"),
    ]
    out = []
    for name, url, what, file, fields in rows:
        accessed = access_date(snap / file)
        if name == "Wikipedia" and retrieved:
            accessed = retrieved[-1]
        out.append({"name": name, "url": url, "what": what, "fields": fields, "accessed": accessed})
    return out
