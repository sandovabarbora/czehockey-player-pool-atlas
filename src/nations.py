"""The ten nations the atlas compares (spec §2), with each source's code.

One table, so every fetcher and analysis module names a nation the same way.
`iso3` is the NHL stats code (`nationalityCode`); `eurostat` is the Eurostat
`geo` code. Czechoslovak-era births are recoded by the NHL to the present-day
state (CZE or SVK), so no "TCH" code is needed here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Nation:
    iso3: str
    eurostat: str
    name: str


HOME = "CZE"

NATIONS: tuple[Nation, ...] = (
    Nation("CZE", "CZ", "Czechia"),
    Nation("FIN", "FI", "Finland"),
    Nation("SWE", "SE", "Sweden"),
    Nation("CHE", "CH", "Switzerland"),
    Nation("SVK", "SK", "Slovakia"),
    Nation("DEU", "DE", "Germany"),
    Nation("LVA", "LV", "Latvia"),
    Nation("DNK", "DK", "Denmark"),
    Nation("NOR", "NO", "Norway"),
    Nation("AUT", "AT", "Austria"),
)

ISO3: tuple[str, ...] = tuple(n.iso3 for n in NATIONS)
BY_EUROSTAT: dict[str, Nation] = {n.eurostat: n for n in NATIONS}
BY_ISO3: dict[str, Nation] = {n.iso3: n for n in NATIONS}
