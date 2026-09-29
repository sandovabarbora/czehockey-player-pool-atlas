"""Name folding and country codes shared by the DEL, NL and roster fetchers.

`fold_name` is the linking key's name half (spec §4: normalised name, diacritics
folded, plus birth date). Country codes are mapped to ISO 3166 alpha-3, the code
`src.nations` and the NHL use; a code or name that is not in the tables passes
through unchanged (upper-cased codes) or maps to None (names).
"""

from __future__ import annotations

import re
import unicodedata

# Letters NFKD does not decompose into base letter + combining mark.
_EXTRA = str.maketrans(
    {
        "ø": "o",
        "Ø": "O",
        "æ": "ae",
        "Æ": "AE",
        "ß": "ss",
        "ł": "l",
        "Ł": "L",
        "đ": "d",
        "Đ": "D",
        "þ": "th",
        "Þ": "Th",
        "ð": "d",
        "Ð": "D",
        "œ": "oe",
        "Œ": "OE",
        "ı": "i",
    }
)


def fold_name(name: object) -> str | None:
    """'Jaromír Jágr' -> 'jaromir jagr'; 'Jágr, Jaromír' -> 'jaromir jagr'.

    Diacritics folded, lower case, punctuation other than hyphen dropped,
    whitespace collapsed. A "Last, First" form is turned round first.
    """
    if name is None or (isinstance(name, float) and name != name):
        return None
    s = str(name).strip()
    if not s:
        return None
    if s.count(",") == 1:
        last, first = (p.strip() for p in s.split(","))
        s = f"{first} {last}"
    s = unicodedata.normalize("NFKD", s.translate(_EXTRA))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z\- ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip() or None


# IOC / IIHF three-letter codes that differ from ISO alpha-3 (DEL "Nat").
IOC_TO_ISO3: dict[str, str] = {
    "GER": "DEU",
    "SUI": "CHE",
    "LAT": "LVA",
    "DEN": "DNK",
    "NED": "NLD",
    "SLO": "SVN",
    "CRO": "HRV",
    "BUL": "BGR",
    "GRE": "GRC",
    "POR": "PRT",
    "RSA": "ZAF",
}


def iso3_from_code(code: object) -> str | None:
    """Map an IOC-style code to ISO alpha-3 ('GER' -> 'DEU'); others pass through."""
    if code is None or (isinstance(code, float) and code != code):
        return None
    c = str(code).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", c):
        return None
    return IOC_TO_ISO3.get(c, c)


# National-team names as Wikipedia roster pages spell them (section headings).
COUNTRY_TO_ISO3: dict[str, str] = {
    "Czechia": "CZE",
    "Czech Republic": "CZE",
    "Finland": "FIN",
    "Sweden": "SWE",
    "Switzerland": "CHE",
    "Slovakia": "SVK",
    "Germany": "DEU",
    "Latvia": "LVA",
    "Denmark": "DNK",
    "Norway": "NOR",
    "Austria": "AUT",
    "Canada": "CAN",
    "United States": "USA",
    "Russia": "RUS",
    "Belarus": "BLR",
    "Kazakhstan": "KAZ",
    "France": "FRA",
    "Italy": "ITA",
    "Slovenia": "SVN",
    "Hungary": "HUN",
    "Poland": "POL",
    "Great Britain": "GBR",
    "Ukraine": "UKR",
    "Japan": "JPN",
    "South Korea": "KOR",
    "Korea": "KOR",
    "China": "CHN",
    "Netherlands": "NLD",
    "Romania": "ROU",
    "Olympic Athletes from Russia": "RUS",
    "ROC": "RUS",
}


def iso3_from_country(name: object) -> str | None:
    if name is None:
        return None
    return COUNTRY_TO_ISO3.get(str(name).strip())
