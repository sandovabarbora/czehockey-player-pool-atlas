"""Population on 1 January for the ten compared nations, 1995-2026 (Eurostat demo_gind).

Endpoint: ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_gind
with indic_de=JAN (population on 1 January, total), one geo per nation. The
response is JSON-stat 2.0: a flat `value` map indexed by the row-major
position over the dimensions in `id` (freq, indic_de, geo, time), plus a
`status` map of flags ("b" break in series, "p" provisional, "e" estimated).
robots.txt allows /eurostat/api/.

A season's per-million rate uses the population of 1 January of the season's
start year (2025/26 -> 1 January 2025); that choice belongs to the analysis.

Writes data/processed/population.parquet (geo, iso3, nation, year,
population, flag) and population.json (the same, for the site), then
publishes them to data/snapshot/.

    python -m src.fetch.eurostat [--first 1995] [--last 2026]
"""

from __future__ import annotations

import argparse
import json
import logging
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

from src import config, snapshot
from src.fetch._http import PoliteClient
from src.logging_setup import setup as logging_setup
from src.nations import BY_EUROSTAT, NATIONS

LOG = logging.getLogger(__name__)

URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/demo_gind"
FIRST_YEAR = 1995
LAST_YEAR = 2026
RAW_DIR = config.RAW_DIR / "eurostat"
OUT_PARQUET = "population.parquet"
OUT_JSON = "population.json"
COLUMNS = ["geo", "iso3", "nation", "year", "population", "flag"]


def params(first: int, last: int) -> list[tuple[str, str]]:
    p = [("format", "JSON"), ("lang", "EN"), ("indic_de", "JAN")]
    p += [("geo", n.eurostat) for n in NATIONS]
    p += [("sinceTimePeriod", str(first)), ("untilTimePeriod", str(last))]
    return p


def parse_jsonstat(payload: dict[str, Any]) -> pd.DataFrame:
    """Flatten a JSON-stat 2.0 demo_gind payload into one row per geo and year."""
    ids: list[str] = payload["id"]
    sizes: list[int] = payload["size"]
    cats = []
    for dim in ids:
        index = payload["dimension"][dim]["category"]["index"]
        # index is {code: position}; order codes by position
        cats.append(sorted(index, key=index.get))
    values = payload["value"]
    status = payload.get("status", {})
    rows = []
    for flat, combo in enumerate(product(*cats)):
        key = str(flat)
        rec = dict(zip(ids, combo, strict=True))
        if rec.get("indic_de") != "JAN":
            continue
        nation = BY_EUROSTAT.get(rec["geo"])
        if nation is None:
            continue
        v = values.get(key)
        rows.append(
            {
                "geo": rec["geo"],
                "iso3": nation.iso3,
                "nation": nation.name,
                "year": int(rec["time"]),
                "population": None if v is None else int(v),
                "flag": status.get(key),
            }
        )
    expected = 1
    for s in sizes:
        expected *= s
    if expected != len(list(product(*cats))):
        raise ValueError("JSON-stat size does not match the category lists")
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["population"] = pd.array(df["population"], dtype="Int64")
    df["year"] = df["year"].astype("int64")
    for c in ["geo", "iso3", "nation", "flag"]:
        df[c] = df[c].astype("string")
    return df.sort_values(["iso3", "year"]).reset_index(drop=True)


def run(
    first: int = FIRST_YEAR, last: int = LAST_YEAR, client: PoliteClient | None = None
) -> list[Path]:
    client = client or PoliteClient(RAW_DIR)
    payload = client.get_json(URL, f"demo_gind_JAN_{first}_{last}.json", params=params(first, last))
    df = parse_jsonstat(payload)
    missing = df[df["population"].isna()]
    if len(missing):
        LOG.warning("missing population: %s", missing[["geo", "year"]].to_dict("records"))
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pq = config.PROCESSED_DIR / OUT_PARQUET
    js = config.PROCESSED_DIR / OUT_JSON
    df.to_parquet(pq, index=False)
    doc = {
        "source": "Eurostat demo_gind, indic_de=JAN (population on 1 January)",
        "updated": payload.get("updated"),
        "rows": [
            {
                k: (None if pd.isna(v) else (int(v) if k in {"year", "population"} else str(v)))
                for k, v in r.items()
            }
            for r in df.to_dict("records")
        ],
    }
    js.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return snapshot.publish([pq, js])


def main() -> None:
    logging_setup()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--first", type=int, default=FIRST_YEAR)
    ap.add_argument("--last", type=int, default=LAST_YEAR)
    a = ap.parse_args()
    for p in run(a.first, a.last):
        LOG.info("snapshot %s", p)


if __name__ == "__main__":
    main()
