"""Contracts on the committed analysis outputs (outputs/*.json): they exist, carry the fields
the report reads, were built from the snapshot now committed, and the linking rates stay
above floors. `make analysis` rebuilds them."""

from __future__ import annotations

import json

import pytest

from src.analysis import common
from src.nations import ISO3

OUTPUTS = [
    "linking.json",
    "q1_per_million.json",
    "q2_break_model.json",
    "q3_cohort_gaps.json",
    "q4_youth_ice_time.json",
    "q5_abroad.json",
    "q6_national_team.json",
    "q7_goalkeepers.json",
    "pool.json",
]


def _read(name: str) -> dict:
    path = common.OUTPUTS_DIR / name
    if not path.exists():
        pytest.skip(f"{name} not built yet (make analysis)")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", OUTPUTS)
def test_output_built_from_current_snapshot(name: str) -> None:
    meta = _read(name)["meta"]["inputs"]
    assert meta, name
    current = common.snapshot_hashes(meta)
    stale = [f for f, h in meta.items() if current[f] != h]
    assert not stale, f"{name} was built from an older snapshot of {stale}; run make analysis"


def test_linking_rates() -> None:
    rep = _read("linking.json")
    by = rep["records_by_league"]
    # every NHL and Liiga record has a birth date; the Czech NHL pool links to the Extraliga
    assert by["NHL"]["with_birth_date_share"] == 1.0
    assert by["Liiga"]["with_birth_date_share"] == 1.0
    assert (
        by["roster"]["linked_on_name_and_birth_date_to_another_source"] / by["roster"]["records"]
        > 0.6
    )
    for lg in ("DEL", "NL"):
        assert by[lg]["name_only_link_rate"] > 0.25, lg
        assert by[lg]["ambiguous"] / by[lg]["without_birth_date"] < 0.05, lg
    assert rep["persons_with_nationality"] / rep["persons"] > 0.75


def test_q1_headline_shape() -> None:
    q1 = _read("q1_per_million.json")
    head = q1["headline"]
    assert head["season"] == "2025/26"
    assert {n["iso3"] for n in head["nations"]} == set(ISO3)
    assert len(q1["nhl_series"]["seasons"]) == 31
    assert q1["nhl_series"]["nations"]["CZE"]["n"][9] is None  # 2004/05
    assert q1["top5_series"]["seasons"][0] == "2008/09"
    home = head["home"]
    assert home["top5"] >= home["nhl"] > 0


def test_q2_model_converged() -> None:
    q2 = _read("q2_break_model.json")
    for code in ("CZE", "FIN", "SWE"):
        d = q2["nations"][code]["diagnostics"]
        assert d["max_rhat"] < 1.02, code
        assert d["min_ess_bulk"] > 400, code
        assert len(q2["nations"][code]["fitted"]["median"]) == 31


def test_q4_home_league_measured_whole_window() -> None:
    q4 = _read("q4_youth_ice_time.json")
    for lg in ("Extraliga", "Liiga", "SHL"):
        assert q4["leagues"][lg]["summary"]["measured_seasons"] == 12, lg


def test_q6_every_compared_nation_has_rosters() -> None:
    q6 = _read("q6_national_team.json")
    assert {e["nation"] for e in q6["events"]} == set(ISO3)
    home = [e for e in q6["events"] if e["nation"] == "CZE"]
    assert sum(e["counts"]["unknown"] for e in home) / sum(e["players"] for e in home) < 0.05


def test_pool_has_the_known_names() -> None:
    p = _read("pool.json")
    by_name = {x["name"]: x for x in p["players"]}
    assert by_name["David Pastrňák"]["latest"]["rung"] == "1"
    assert "Roman Červenka" in by_name
    assert p["counts"]["players"] > 600
    for x in p["players"]:
        assert x["seasons"], x["name"]
        assert all(r["rung"] in ("1", "2", "home") for r in x["seasons"])
