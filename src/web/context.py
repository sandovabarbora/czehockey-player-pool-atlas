"""The template context: every number the two pages state, read from outputs/*.json.

Nothing here is a constant about the data. Words that depend on a number (ranks,
"above"/"below", a rise or a fall) are chosen from the number, so a rebuilt output
cannot leave a sentence saying the opposite of its figure.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import unicodedata
from pathlib import Path
from statistics import median
from typing import Any

from src import config
from src.nations import BY_ISO3, HOME, ISO3
from src.web import fmt, references

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
    "intervals",
)

HOME_NAME = BY_ISO3[HOME].name
WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
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
        for st in brk["steps"]:
            df = st["delta_factor"]
            st["reading"] = "rise" if df["lo"] > 1 else ("fall" if df["hi"] < 1 else "direction not resolved")
            st["p_up"] = 1 - st["p_down"]
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
            "top_pair": brk["top_candidates"][0],
            "n_breaks": brk["n_breaks"],
            "n_obs": sum(1 for v in nat["n"] if v is not None),
            "n_seasons": len(nat["n"]),
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
    steps = [st for c in q2["nations"].values() for st in c["break"]["steps"]]
    out["n_steps"] = len(steps)
    out["n_resolved"] = sum(1 for st in steps if st["reading"] != "direction not resolved")
    return out


def _q3(q3: dict, population_m: float) -> dict:
    cells = [c for c in q3["cells"] if c["position"] in POSITION_WORD and c["age_band"] in AGE_BANDS]
    u21 = [c for c in cells if c["age_band"] == "≤21" and c["position"] in ("F", "D")]
    u21_home = sum(c["counts"][HOME] for c in u21)
    shortfalls = [s for s in q3["largest_shortfalls"] if round(s["shortfall"], 1) > 0]
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
        "n_peers": len(cells[0]["peers_in_median"]) if cells else 0,
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


def _fold(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)).casefold()


def _autumn(news: dict | None, pool: dict, q5: dict) -> dict:
    """"This autumn" (#autumn): dated news from `config/news/cze.yaml` beside the atlas's own numbers.

    The news gives only dated facts and their sources. The captain's numbers come from here: his
    latest-season row in `pool` (by `person_id`, whose name must match the news) and his row in
    `q5_abroad` for the same season, league and team, which carries the league-season median at his
    position. Footnotes are numbered in order of first citation, in the page's order: coach, then captain. Empty dict without a news file.
    """
    if not news:
        return {}
    by_key = {s["key"]: s for s in news["sources"]}
    order: list[str] = []

    def cite(keys: list[str]) -> list[int]:
        for k in keys:
            if k not in by_key:
                raise KeyError(f"news source {k!r} is cited but not listed")
            if k not in order:
                order.append(k)
        return sorted(order.index(k) + 1 for k in keys)

    k = news["coach"]
    coach = {
        **k,
        "approved": fmt.long_date(k["approved"]),
        "contract_years": {2: "two", 3: "three", 4: "four"}.get(k["contract_years"], str(k["contract_years"])),
        "notes_approved": cite(k["sources_approved"]),
        "notes_staff": cite(k["sources_staff"]),
        "first_game": {**k["first_game"], "date": fmt.long_date(k["first_game"]["date"]),
                       "notes": cite(k["first_game"]["sources"])},
    }
    words = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh"}
    c = news["captain"]
    player = next((p for p in pool["players"] if p["person_id"] == c["person_id"]), None)
    if player is None or _fold(player["name"]) != _fold(c["name"]):
        raise ValueError(f"news captain {c['name']!r} is not {c['person_id']} in outputs/pool.json")
    last = player["seasons"][-1]
    q5_row = next(
        (r for r in q5["players"] if r["person_id"] == c["person_id"] and r["season"] == last["season"]
         and r["league"] == last["league"] and r["team"] == last["team"]),
        None,
    )
    captain = {
        **c,
        "named": fmt.long_date(c["named"]),
        "nth": fmt.ordinal(c["nth"]),
        "czech_nth": words.get(c["czech_nth"], fmt.ordinal(c["czech_nth"])),
        "notes_named": cite(c["sources_named"]),
        "notes_previous": cite(c["sources_previous"]),
        "notes_czech_nth": cite(c["sources_czech_nth"]),
        "season": last,
        "position_word": POSITION_WORD[player["position"]],
        "position": player["position"],
        "abroad": q5_row,
    }
    sources = [
        {**by_key[key], "n": i + 1, "date": fmt.long_date(by_key[key]["date"]) if by_key[key].get("date") else None,
         "accessed": fmt.long_date(by_key[key]["accessed"])}
        for i, key in enumerate(order)
    ]
    return {
        "data_as_of": fmt.long_date(news["data_as_of"]),
        "news_as_of": fmt.long_date(news["news_as_of"]),
        "captain": captain,
        "coach": coach,
        "sources": sources,
    }


def _population_m(q1: dict) -> float:
    home = next(n for n in q1["headline"]["nations"] if n["iso3"] == HOME)
    return home["population"] / 1e6


def _ci(d: dict | None, key: str = "median", f=fmt.f2) -> str:
    """'0.98 (95 % bootstrap interval 0.90–1.11)' style: the value and its interval, formatted."""
    if not d:
        return "–"
    return f"{f(d[key])} ({f(d['lo'])}–{f(d['hi'])})"


def _takeaways(c: dict) -> list[dict]:
    """The summary's findings, one per question, each with its interval or its count label."""
    q1, q2, q3, q4, q5, q6, q7, iv = (c[k] for k in ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "iv"))
    h = q1["home"]
    pm = q1["peer_median"]
    leaders = q1["leaders_nhl"]
    cze = q2[HOME]
    fall = cze["fall"]
    out = []
    ratio = min(leaders[0]["nhl_per_million"], leaders[1]["nhl_per_million"]) / h["nhl_per_million"]
    out.append({
        "head": (
            f"In {q1['season']}, {h['nhl']} Czech players reached the games threshold in the NHL, "
            f"{fmt.f2(h['nhl_per_million'])} per million inhabitants, which ranks Czechia {fmt.ordinal(h['rank_nhl'])} of "
            f"{q1['n_nations']} nations and {q1['nhl_vs_median_word']} the median of the nine peers ({fmt.f2(pm['nhl_per_million'])})."
        ),
        "body": [
            f"With the four rung-2 leagues added, the count is {h['top5']} players, {fmt.f2(h['top5_per_million'])} per million, "
            f"{fmt.ordinal(h['rank_top5'])} of {q1['n_nations']} (peer median {fmt.f2(pm['top5_per_million'])}). "
            f"{leaders[0]['name']} ({fmt.f2(leaders[0]['nhl_per_million'])}) and {leaders[1]['name']} "
            f"({fmt.f2(leaders[1]['nhl_per_million'])}) have about {round(ratio)} times the Czech NHL rate. "
            f"These are administrative counts; the Czech ranks are the same under all three games thresholds.",
        ],
    })
    fall_txt = (
        f"The break model places a downward step most likely in {fall['modal']['season']} (posterior probability "
        f"{fmt.f2(fall['modal']['prob'])}), with a factor of {fmt.times(fall['delta_factor']['median'])} "
        f"(90 % HDI {fmt.f2(fall['delta_factor']['lo'])}–{fmt.f2(fall['delta_factor']['hi'])}; "
        f"P(level falls) = {fmt.f2(fall['p_down'])}). The model describes timing, not cause."
        if fall
        else "The break model finds no downward step."
    )
    out.append({
        "head": (
            f"The observed Czech NHL count was {q1['peak']['n']} players in {q1['peak']['season']} and "
            f"{q1['peak']['latest']['n']} in {q1['peak']['latest']['season']} (administrative counts)."
        ),
        "body": [
            fall_txt
            + f" Conditional on the most probable pair of step seasons, the model level in {cze['fitted']['latest']['season']} "
            f"is {fmt.pct0(cze['fitted']['latest_to_peak'])} of its {cze['fitted']['peak']['season']} peak."
        ],
    })
    top = q3["top_shortfall"]
    second = q3["second_shortfall"]
    fw = [r for r in iv["q3"]["u21_by_season"] if r["position"] == "F"]
    q3_gap = (
        f"Expressed in players at the Czech population, the difference from the median of {WORDS.get(q3['n_peers'], q3['n_peers'])} peers is "
        f"{fmt.f1(top['shortfall'])} for {POSITION_WORD[top['position']]} aged {BAND_WORD[top['age_band']]}"
        + (f" and {fmt.f1(second['shortfall'])} for {POSITION_WORD[second['position']]} aged {BAND_WORD[second['age_band']]}" if second else "")
        + "."
    ) if top else ""
    q3_noise = (
        "One season is a noisy cross-section: Czech forwards aged 21 or under who reached the threshold numbered "
        + ", ".join(str(r["count"]) for r in fw) + f" in the seasons {fw[0]['season']} to {fw[-1]['season']}."
    ) if fw else ""
    out.append({
        "head": (
            f"In {q3['season']} no Czech forward or defenceman aged 21 or under reached the games threshold in the NHL or rung 2."
            if q3["u21_home"] == 0
            else f"In {q3['season']}, {q3['u21_home']} Czech forwards and defencemen aged 21 or under reached the games threshold in the NHL or rung 2."
        ),
        "body": [" ".join(x for x in (q3_gap, q3_noise) if x)],
    })
    g = iv["q4"]["leagues"]
    out.append({
        "head": (
            f"Skaters aged 20 or under played {fmt.pct(g['Extraliga']['games']['mean'])} of Extraliga skater games, "
            f"against {fmt.pct(g['Liiga']['games']['mean'])} in the Liiga and {fmt.pct(g['SHL']['games']['mean'])} in the SHL "
            f"(means of {g['Extraliga']['games']['seasons']} seasons, {q4['window']})."
        ),
        "body": [
            f"The 95 % bootstrap intervals, resampling seasons, are {fmt.pct(g['Extraliga']['games']['lo'])}–{fmt.pct(g['Extraliga']['games']['hi'])}, "
            f"{fmt.pct(g['Liiga']['games']['lo'])}–{fmt.pct(g['Liiga']['games']['hi'])} and {fmt.pct(g['SHL']['games']['lo'])}–{fmt.pct(g['SHL']['games']['hi'])}. "
            f"The shares cover players of every nationality and compare leagues, not the chances given to any one player."
        ],
    })
    b = iv["q5"]
    hn = q5["home"]["NHL"]
    out.append({
        "head": (
            f"Over {q5['window']}, the median Czech NHL skater played {fmt.f2(hn['median_toi_ratio'])} times the median ice time "
            f"of his league, season and position and scored {fmt.f2(hn['median_ppg_ratio'])} times its points per game "
            f"({hn['players']} players, {hn['player_seasons']} player-seasons)."
        ),
        "body": [
            f"The 95 % bootstrap intervals, resampling players, are {fmt.f2(b['NHL']['toi']['lo'])}–{fmt.f2(b['NHL']['toi']['hi'])} and "
            f"{fmt.f2(b['NHL']['ppg']['lo'])}–{fmt.f2(b['NHL']['ppg']['hi'])}, so both include 1. In the Liiga the ratios are "
            f"{_ci(b['Liiga']['toi'])} and {_ci(b['Liiga']['ppg'])}, in the SHL {_ci(b['SHL']['toi'])} and {_ci(b['SHL']['ppg'])}; "
            f"they compare imported players with each league's own depth and are not comparable across leagues."
        ],
    })
    s6 = iv["q6"]
    a, e, l6 = s6["all"]["shares"], s6["to_2022"]["shares"], s6["from_2023"]["shares"]
    out.append({
        "head": (
            f"Across {s6['all']['events']} World Championship and Olympic rosters, {s6['all']['first']}–{s6['all']['last']}, "
            f"Czech roster spots came on average {fmt.pct0(a['1'])} from the NHL, {fmt.pct0(a['home'])} from the Extraliga, "
            f"{fmt.pct0(a['khl'])} from the KHL and {fmt.pct0(a['2'])} from rung 2."
        ),
        "body": [
            f"The KHL share was {fmt.pct0(e['khl'])} over {s6['to_2022']['first']}–{s6['to_2022']['last']} and "
            f"{fmt.pct0(l6['khl'])} over {s6['from_2023']['first']}–{s6['from_2023']['last']}, when the Extraliga share was {fmt.pct0(l6['home'])}. "
            f"Without the 2018 and 2022 Olympics, which NHL players did not attend, the NHL share is {fmt.pct0(s6['without_2018_2022_olympics']['shares']['1'])}. "
            f"Roster composition reflects nomination as well as the pool."
        ],
    })
    k = q7["home"]
    out.append({
        "head": (
            f"In {q7['season']}, {k['top5']} Czech goalkeepers reached the games threshold in the NHL or rung 2, "
            f"{fmt.f2(k['top5_per_million'])} per million, {fmt.ordinal(k['rank_top5'])} of {q7['n_nations']} "
            f"(peer median {fmt.f2(q7['peer_median']['top5_per_million'])})."
        ),
        "body": [
            f"In the NHL alone there were {k['nhl']}, {fmt.f2(k['nhl_per_million'])} per million, {fmt.ordinal(q7['rank_nhl'])} "
            f"(peer median {fmt.f2(q7['peer_median']['nhl_per_million'])}). These are administrative counts of a few players each."
        ],
    })
    for t in out:
        t["body"] = [x for x in t["body"] if x]
    return out


def meta(outputs_dir: Path | None = None) -> dict[str, Any]:
    """The header metadata: dates, version, snapshot, code and how to cite."""
    root = outputs_dir or config.OUTPUTS_DIR
    sums = config.DATA_DIR / "snapshot" / "SHA256SUMS"
    q2 = json.loads((root / "q2_break_model.json").read_text(encoding="utf-8"))
    return {
        "published": "18 May 2026",
        "updated": "29 September 2026",
        "version": 3,
        "status": "research, exploratory; not pre-registered",
        "snapshot_date": "29 September 2026",
        "snapshot_sums": hashlib.sha256(sums.read_bytes()).hexdigest()[:12] if sums.exists() else "–",
        "repo": "https://github.com/sandovabarbora/czehockey-player-pool-atlas",
        "repo_short": "github.com/sandovabarbora/czehockey-player-pool-atlas",
        "url": "https://hockey.bsandova.com/",
        "python": (config.ROOT_DIR / ".python-version").read_text().strip() if (config.ROOT_DIR / ".python-version").exists() else "3.13",
        "seed": q2["definitions"]["sampler"]["seed"],
        "rebuild": "make install restore-snapshot verify-snapshot analysis pages",
        "title": "Czech hockey atlas: the player pool",
    }


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
        "iv": o["intervals"],
        "population_m": popm,
        "peers": [BY_ISO3[c].name for c in PEERS],
        "category_label": CATEGORY_LABEL,
        "position_word": POSITION_WORD,
        "band_word": BAND_WORD,
        "build_date": build_date or dt.date.today().isoformat(),
        "build_date_long": fmt.long_date(dt.date.fromisoformat(build_date or dt.date.today().isoformat())),
        "meta": meta(outputs_dir),
        "refs": references.listing(),
        "refnum": references.NUMBER,
        "signed": fmt.signed,
        "long_date": lambda d: fmt.long_date(dt.date.fromisoformat(d)) if isinstance(d, str) else fmt.long_date(d),
        "sources": sources(),
        "autumn": _autumn(config.news(), o["pool"], o["q5_abroad"]),
        "f1": fmt.f1,
        "f2": fmt.f2,
        "pct": fmt.pct,
        "pct0": fmt.pct0,
        "num": fmt.num,
        "ordinal": fmt.ordinal,
        "times": fmt.times,
        "mmss": fmt.mmss,
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
