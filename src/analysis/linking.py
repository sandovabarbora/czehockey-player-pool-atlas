"""One player-season table across the six covered leagues, linked into persons, with one
nationality per person (spec §4).

Sources and what each gives:

    league     id            birth date                 nationality (basis)
    NHL        player_id     always                     nationalityCode (citizenship)
    Liiga      player_id     always                     nationality (citizenship)
    SHL        uuid          from about 2010            nationality where not N/A (citizenship)
    Extraliga  player_id     from 2013/14 (profiles)    foreigner flag: not foreign -> CZE (eligibility)
    DEL        player_id     never                      'Nat' from 2022/23 (licence, eligibility)
    NL         name only     never                      Swiss licence -> CHE (eligibility); goalies none
    rosters    -             always                     national team (IIHF eligibility)

Linking. Each source identity (league + id; NL by name) is one record. Records are joined
into persons in two steps:

1. name + birth date: the name key (`common.link_key`: diacritics folded, tokens sorted)
   and the full birth date agree. This is the spec's linking rule.
2. name only, for records with no birth date (DEL, NL, SHL before about 2010, Extraliga
   before 2013/14): the record joins the one person with the same name key whose seasons
   lie within `NAME_ONLY_WINDOW` seasons of its own and whose birth year does not
   contradict it. With two or more such persons the record is ambiguous and stays on its
   own; with none it is unmatched. Remaining records of the same league with the same
   name key and seasons that touch are then joined (DEL's archive and current ids).

Nationality. A person's nationality is taken, in this order, from:

1. citizenship: the NHL code when the person has an NHL record, else the most frequent
   code among Liiga and SHL rows;
2. national team: the team on a World Championship or Olympic roster;
3. eligibility or licence: DEL 'Nat', Extraliga (not a foreigner -> CZE), NL (Swiss
   licence -> CHE).

The NHL recodes Czechoslovak-era births to the present-day state (CZE or SVK) and the
report takes that code. Every row carries the basis its nationality came from; a row
whose nationality did not come from its own source (the source gave nothing, or a
higher-ranked source of the same person overrode it) carries 'linked: <basis>'.

    python -m src.analysis.linking   -> outputs/linking.json
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import common
from src.fetch._names import iso3_from_code

LOG = logging.getLogger(__name__)

NAME_ONLY_WINDOW = 4
"""Seasons of slack when a record without a birth date is matched on name alone."""

BASIS_RANK = {"citizenship": 0, "national_team": 1, "eligibility": 2}

STINT_COLUMNS = [
    "league",
    "source_id",
    "season",
    "season_start",
    "full_name",
    "key",
    "key_initial",
    "birth_date",
    "birth_year",
    "position",
    "team",
    "games_played",
    "toi_s",
    "goals",
    "assists",
    "points",
    "saves",
    "shots_against",
    "goals_against",
    "shutouts",
    "nat_value",
    "nat_basis",
    "is_foreign",
]

SNAPSHOT_FILES = [
    "nhl_skaters.parquet",
    "nhl_goalies.parquet",
    "liiga_skaters.parquet",
    "liiga_goalies.parquet",
    "shl_skaters.parquet",
    "shl_goalies.parquet",
    "extraliga_skaters.parquet",
    "extraliga_goalies.parquet",
    "del_skaters.parquet",
    "del_goalies.parquet",
    "nl_skaters.parquet",
    "nl_goalies.parquet",
    "rosters.parquet",
]

NUMERIC = [
    "games_played",
    "toi_s",
    "goals",
    "assists",
    "points",
    "saves",
    "shots_against",
    "goals_against",
    "shutouts",
]


# =====================================================================================
# Standardising each source
# =====================================================================================


def _col(df: pd.DataFrame, name: str, default: Any = np.nan) -> pd.Series:
    return df[name] if name in df.columns else pd.Series(default, index=df.index)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _frame(
    df: pd.DataFrame,
    league: str,
    source_id: pd.Series,
    position: pd.Series,
    nat_value: pd.Series,
    nat_basis: str | pd.Series | None,
    toi_s: pd.Series,
    is_foreign: pd.Series | None = None,
) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["league"] = league
    out["source_id"] = source_id.astype("string")
    out["season"] = df["season"].astype("string")
    out["season_start"] = df["season_start"].astype("int64")
    out["full_name"] = df["full_name"].astype("string")
    out["key"] = df["full_name"].map(common.link_key).astype("string")
    out["key_initial"] = df["full_name"].map(common.initial_key).astype("string")
    bd = _col(df, "birth_date", pd.NA).astype("string")
    out["birth_date"] = bd.where(bd.str.fullmatch(r"\d{4}-\d{2}-\d{2}").fillna(False), pd.NA)
    by = _num(_col(df, "birth_year"))
    by_from_date = _num(out["birth_date"].str[:4])
    out["birth_year"] = by_from_date.fillna(by)
    out["position"] = position.astype("string")
    out["team"] = _col(df, "team", pd.NA).astype("string")
    out["games_played"] = _num(_col(df, "games_played"))
    out["toi_s"] = _num(toi_s)
    for c in ("goals", "assists", "points", "saves", "shots_against", "goals_against", "shutouts"):
        out[c] = _num(_col(df, c))
    out["nat_value"] = nat_value.astype("string")
    if isinstance(nat_basis, pd.Series):
        out["nat_basis"] = nat_basis.astype("string")
    else:
        out["nat_basis"] = pd.Series(nat_basis, index=df.index, dtype="string")
    out.loc[out["nat_value"].isna(), "nat_basis"] = pd.NA
    out["is_foreign"] = (
        is_foreign if is_foreign is not None else pd.Series(pd.NA, index=df.index)
    ).astype("boolean")
    return out[STINT_COLUMNS]


def _pos_fdg(pos: pd.Series) -> pd.Series:
    m = {"C": "F", "L": "F", "R": "F", "LW": "F", "RW": "F", "F": "F", "D": "D", "G": "G"}
    return pos.astype("string").str.upper().map(m).astype("string")


def standardise_nhl(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    sk = sk.assign(team=_col(sk, "teams", pd.NA))
    go = go.assign(team=_col(go, "teams", pd.NA))
    sk_toi = _num(sk["toi_per_game_s"]) * _num(sk["games_played"])
    a = _frame(
        sk,
        "NHL",
        sk["player_id"],
        _pos_fdg(sk["position"]),
        sk["nationality"],
        "citizenship",
        sk_toi,
    )
    b = _frame(
        go,
        "NHL",
        go["player_id"],
        pd.Series("G", index=go.index),
        go["nationality"],
        "citizenship",
        go["toi_s"],
    )
    return pd.concat([a, b], ignore_index=True)


def standardise_liiga(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    a = _frame(
        sk,
        "Liiga",
        sk["player_id"],
        _pos_fdg(sk["position"]),
        sk["nationality"],
        "citizenship",
        sk["toi_s"],
    )
    b = _frame(
        go,
        "Liiga",
        go["player_id"],
        pd.Series("G", index=go.index),
        go["nationality"],
        "citizenship",
        go["toi_s"],
    )
    return pd.concat([a, b], ignore_index=True)


def _shl_id(df: pd.DataFrame) -> pd.Series:
    uuid = _col(df, "player_id", pd.NA).astype("string")
    legacy = _col(df, "legacy_id", pd.NA).astype("string")
    fallback = (
        "N:"
        + df["full_name"].map(common.link_key).astype("string")
        + "|"
        + df["season"].astype("string")
        + "|"
        + _col(df, "team", "").astype("string")
    )
    return uuid.fillna("L:" + legacy).fillna(fallback)


def standardise_shl(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    a = _frame(
        sk,
        "SHL",
        _shl_id(sk),
        _pos_fdg(sk["position"]),
        sk["nationality"],
        "citizenship",
        sk["toi_s"],
    )
    b = _frame(
        go,
        "SHL",
        _shl_id(go),
        pd.Series("G", index=go.index),
        go["nationality"],
        "citizenship",
        go["toi_s"],
    )
    return pd.concat([a, b], ignore_index=True)


def _extraliga_nat(df: pd.DataFrame) -> pd.Series:
    foreign = df["is_foreign"].astype("boolean")
    return pd.Series(np.where(foreign.fillna(True), None, "CZE"), index=df.index, dtype="string")


def standardise_extraliga(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    a = _frame(
        sk,
        "Extraliga",
        sk["player_id"],
        _pos_fdg(sk["position"]),
        _extraliga_nat(sk),
        "eligibility",
        sk["toi_s"],
        sk["is_foreign"],
    )
    b = _frame(
        go,
        "Extraliga",
        go["player_id"],
        pd.Series("G", index=go.index),
        _extraliga_nat(go),
        "eligibility",
        go["toi_s"],
        go["is_foreign"],
    )
    return pd.concat([a, b], ignore_index=True)


def standardise_del(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for df, pos in ((sk, None), (go, "G")):
        df = df[df["phase"] == "hauptrunde"] if "phase" in df.columns else df
        sid = df["id_scheme"].astype("string") + ":" + df["player_id"].astype("string")
        p = _pos_fdg(df["position"]) if pos is None else pd.Series(pos, index=df.index)
        nat = _col(df, "nationality", pd.NA).astype("string")
        nat = nat.fillna(_col(df, "nat_raw", pd.NA).map(iso3_from_code).astype("string"))
        frames.append(_frame(df, "DEL", sid, p, nat, "eligibility", _col(df, "toi_s")))
    return pd.concat(frames, ignore_index=True)


def standardise_nl(sk: pd.DataFrame, go: pd.DataFrame) -> pd.DataFrame:
    go = go[go["full_name"].map(common.link_key) != "durchschnitt"]
    go = go[_col(go, "team_id", 0).astype("float64") != 100000]
    sk_nat = pd.Series(
        np.where(sk["licence"].astype("string") == "CH", "CHE", None),
        index=sk.index,
        dtype="string",
    )
    a = _frame(
        sk,
        "NL",
        sk["full_name"].map(common.link_key),
        _pos_fdg(sk["position"]),
        sk_nat,
        "eligibility",
        pd.Series(np.nan, index=sk.index),
    )
    b = _frame(
        go,
        "NL",
        go["full_name"].map(common.link_key),
        pd.Series("G", index=go.index),
        pd.Series(pd.NA, index=go.index, dtype="string"),
        None,
        go["toi_s"],
    )
    return pd.concat([a, b], ignore_index=True)


def _collapse(df: pd.DataFrame) -> pd.DataFrame:
    """One row per league, identity and season: traded players' rows summed, teams joined."""
    keys = ["league", "source_id", "season"]
    dup = df.duplicated(keys, keep=False)
    if not dup.any():
        return df.reset_index(drop=True)
    single, multi = df[~dup], df[dup]
    agg: dict[str, Any] = {c: "first" for c in STINT_COLUMNS if c not in keys}
    for c in NUMERIC:
        agg[c] = lambda s: s.sum(min_count=1)
    agg["team"] = lambda s: ",".join(sorted({str(t) for t in s.dropna()})) or pd.NA
    agg["nat_value"] = lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA
    agg["nat_basis"] = lambda s: s.dropna().iloc[0] if s.notna().any() else pd.NA
    merged = multi.groupby(keys, as_index=False, sort=False).agg(agg)
    out = pd.concat([single, merged[STINT_COLUMNS]], ignore_index=True)
    for c in NUMERIC + ["birth_year"]:
        out[c] = out[c].astype("float64")
    return out


def standardise_all(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    parts = [
        standardise_nhl(tables["nhl_skaters"], tables["nhl_goalies"]),
        standardise_liiga(tables["liiga_skaters"], tables["liiga_goalies"]),
        standardise_shl(tables["shl_skaters"], tables["shl_goalies"]),
        standardise_extraliga(tables["extraliga_skaters"], tables["extraliga_goalies"]),
        standardise_del(tables["del_skaters"], tables["del_goalies"]),
        standardise_nl(tables["nl_skaters"], tables["nl_goalies"]),
    ]
    df = pd.concat(parts, ignore_index=True)
    df = df[df["key"].notna()]
    return _collapse(df)


def roster_identities(rosters: pd.DataFrame) -> pd.DataFrame:
    """One record per roster player (name key + birth date), with the national team."""
    r = rosters.copy()
    r["key"] = r["player"].map(common.link_key)
    r["key_initial"] = r["player"].map(common.initial_key)
    r = r[r["key"].notna() & r["birth_date"].notna() & r["team_iso3"].notna()]
    r["season_start"] = r["year"].astype("int64") - 1
    g = r.groupby(["key", "birth_date"], as_index=False).agg(
        key_initial=("key_initial", "first"),
        first=("season_start", "min"),
        last=("season_start", "max"),
        nat=("team_iso3", lambda s: Counter(s).most_common(1)[0][0]),
        n=("team_iso3", "size"),
    )
    return g


# =====================================================================================
# Linking
# =====================================================================================


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # the lower index (earlier league in LEAGUES order) stays the root
            if rb < ra:
                ra, rb = rb, ra
            self.parent[rb] = ra


def _mode(values: pd.Series) -> Any:
    v = values.dropna()
    if v.empty:
        return pd.NA
    counts = Counter(v.tolist())
    top = max(counts.values())
    return sorted(k for k, c in counts.items() if c == top)[0]


@dataclass
class Linked:
    stints: pd.DataFrame
    identities: pd.DataFrame
    persons: pd.DataFrame
    report: dict[str, Any] = field(default_factory=dict)
    rosters: pd.DataFrame | None = None
    """The roster table with corrected birth dates (`fix_roster_dates`)."""


def identity_table(stints: pd.DataFrame, rosters: pd.DataFrame | None) -> pd.DataFrame:
    order = {lg: i for i, lg in enumerate(common.LEAGUES)}
    g = stints.groupby(["league", "source_id"], sort=False)
    ids = g.agg(
        key=("key", _mode),
        key_initial=("key_initial", _mode),
        birth_date=("birth_date", _mode),
        birth_year=("birth_year", _mode),
        first=("season_start", "min"),
        last=("season_start", "max"),
        rows=("season", "size"),
    ).reset_index()
    ids["birth_year"] = pd.to_numeric(ids["birth_year"], errors="coerce").astype("float64")
    by_date = pd.to_numeric(ids["birth_date"].astype("string").str[:4], errors="coerce")
    ids["birth_year"] = by_date.fillna(ids["birth_year"])
    if rosters is not None and len(rosters):
        r = roster_identities(rosters)
        extra = pd.DataFrame(
            {
                "league": "roster",
                "source_id": r["key"] + "|" + r["birth_date"],
                "key": r["key"],
                "key_initial": r["key_initial"],
                "birth_date": r["birth_date"],
                "birth_year": pd.to_numeric(r["birth_date"].str[:4]),
                "first": r["first"],
                "last": r["last"],
                "rows": r["n"],
                "roster_nat": r["nat"],
            }
        )
        ids = pd.concat([ids, extra], ignore_index=True)
    if "roster_nat" not in ids.columns:
        ids["roster_nat"] = pd.NA
    ids["_order"] = ids["league"].map(order).fillna(len(order))
    ids = ids.sort_values(["_order", "source_id"], kind="stable").reset_index(drop=True)
    return ids.drop(columns="_order")


def _twins_in_one_league(grp: pd.DataFrame) -> bool:
    """Two different names with the same initial, surname and birth date playing in the
    same league in overlapping seasons are two people (twins such as Kevin and Kelly
    Klíma), not a first-name variant of one. Roster pages are left out: two spellings of
    one player there are a Wikipedia variant, not a second person."""
    for league, g in grp.groupby("league"):
        if league == "roster" or g["key"].nunique() < 2:
            continue
        rows = list(g.itertuples())
        for a in range(len(rows)):
            for b in range(a + 1, len(rows)):
                x, y = rows[a], rows[b]
                if x.key != y.key and x.first <= y.last and y.first <= x.last:
                    return True
    return False


def link(ids: pd.DataFrame) -> pd.DataFrame:
    """Adds `person_idx` and `link_basis` to the identity table (see module docstring)."""
    ids = ids.copy()
    n = len(ids)
    uf = _UnionFind(n)
    has_dob = ids["birth_date"].notna().to_numpy()

    # 1. name + birth date
    for _, idx in ids[has_dob].groupby(["key", "birth_date"]).groups.items():
        idx = list(idx)
        for j in idx[1:]:
            uf.union(idx[0], j)

    # 1b. first-name variants: initial + surname + full birth date ('Dan' / 'Daniel')
    variant = np.zeros(n, dtype=bool)
    sub = ids[has_dob & ids["key_initial"].notna()]
    for _, idx in sub.groupby(["key_initial", "birth_date"]).groups.items():
        idx = list(idx)
        if _twins_in_one_league(ids.loc[idx]):
            continue
        for j in idx[1:]:
            if uf.find(idx[0]) != uf.find(j):
                uf.union(idx[0], j)
                variant[j] = True

    roots = np.array([uf.find(i) for i in range(n)])
    # person spans and birth years over the DOB-bearing records only
    comp: dict[int, dict[str, Any]] = {}
    for i in np.flatnonzero(has_dob):
        r = roots[i]
        c = comp.setdefault(r, {"first": 10**6, "last": -1, "by": set(), "sources": set()})
        c["first"] = min(c["first"], int(ids.at[i, "first"]))
        c["last"] = max(c["last"], int(ids.at[i, "last"]))
        c["by"].add(int(ids.at[i, "birth_year"]))
        c["sources"].add(ids.at[i, "league"])
    by_key: dict[str, list[int]] = defaultdict(list)
    for r in comp:
        by_key[ids.at[r, "key"]].append(r)

    basis = np.array(["dob" if d else "" for d in has_dob], dtype=object)
    basis[variant] = "dob_name_variant"
    # 2. name only
    for i in np.flatnonzero(~has_dob):
        key = ids.at[i, "key"]
        lo, hi = int(ids.at[i, "first"]), int(ids.at[i, "last"])
        by = ids.at[i, "birth_year"]
        cands = []
        for r in by_key.get(key, []):
            c = comp[r]
            if c["first"] - NAME_ONLY_WINDOW > hi or c["last"] + NAME_ONLY_WINDOW < lo:
                continue
            if not pd.isna(by) and int(by) not in c["by"]:
                continue
            cands.append(r)
        if len(cands) == 1:
            uf.union(cands[0], i)
            basis[i] = "name_only"
        elif len(cands) > 1:
            basis[i] = "ambiguous"
        else:
            basis[i] = "unmatched"

    # 2b. same league, same name, seasons that touch (records with no birth date only)
    rest = ids[(basis == "unmatched")]
    for (_league, _key), grp in rest.groupby(["league", "key"]):
        grp = grp.sort_values("first")
        prev = None
        for i, row in grp.iterrows():
            if (
                prev is not None
                and int(row["first"]) - int(ids.at[prev, "last"]) <= NAME_ONLY_WINDOW
            ):
                uf.union(prev, i)
                basis[i] = "same_league_name"
                if basis[prev] == "unmatched":
                    basis[prev] = "same_league_name"
            prev = i

    ids["person_idx"] = [uf.find(i) for i in range(n)]
    ids["link_basis"] = basis
    return ids


def resolve_nationality(ids: pd.DataFrame, stints: pd.DataFrame) -> pd.DataFrame:
    """One row per person: nationality, its basis, conflicts, birth date/year, position."""
    ev = stints.dropna(subset=["nat_value"]).merge(
        ids[["league", "source_id", "person_idx"]], on=["league", "source_id"]
    )
    ev = ev[["person_idx", "league", "nat_value", "nat_basis"]]
    ros = ids.dropna(subset=["roster_nat"])
    ev = pd.concat(
        [
            ev,
            pd.DataFrame(
                {
                    "person_idx": ros["person_idx"],
                    "league": "roster",
                    "nat_value": ros["roster_nat"],
                    "nat_basis": "national_team",
                }
            ),
        ],
        ignore_index=True,
    )

    out: dict[int, dict[str, Any]] = {}
    for p, grp in ev.groupby("person_idx", sort=False):
        rank = grp["nat_basis"].map(BASIS_RANK)
        best = grp[rank == rank.min()]
        basis = best["nat_basis"].iloc[0]
        nhl = best[best["league"] == "NHL"]
        value = _mode(nhl["nat_value"]) if len(nhl) else _mode(best["nat_value"])
        values = set(grp["nat_value"])
        out[p] = {
            "nationality": value,
            "nat_basis": basis,
            "nat_conflict": len(values) > 1,
            "nat_values": ",".join(sorted(values)),
        }

    persons = (
        ids.groupby("person_idx")
        .agg(
            birth_date=("birth_date", _mode),
            birth_year=("birth_year", _mode),
            name_key=("key", "first"),
            n_identities=("source_id", "size"),
            leagues=("league", lambda s: ",".join(sorted(set(s)))),
        )
        .reset_index()
    )
    nat = pd.DataFrame.from_dict(out, orient="index")
    if nat.empty:
        nat = pd.DataFrame(columns=["nationality", "nat_basis", "nat_conflict", "nat_values"])
    nat.index.name = "person_idx"
    persons = persons.merge(nat.reset_index(), on="person_idx", how="left")
    persons["nat_conflict"] = persons["nat_conflict"].fillna(False).astype(bool)

    pos = stints.merge(ids[["league", "source_id", "person_idx"]], on=["league", "source_id"])
    pos = pos.dropna(subset=["position"])
    pos_mode = (
        pos.assign(w=pos["games_played"].fillna(0) + 1)
        .groupby(["person_idx", "position"])["w"]
        .sum()
        .reset_index()
        .sort_values(["person_idx", "w", "position"], ascending=[True, False, True])
        .drop_duplicates("person_idx")[["person_idx", "position"]]
        .rename(columns={"position": "person_position"})
    )
    persons = persons.merge(pos_mode, on="person_idx", how="left")
    return persons


def person_ids(ids: pd.DataFrame) -> dict[int, str]:
    """Readable, deterministic person ids: the root record's 'league:source_id'."""
    return {
        int(p): f"{ids.at[int(p), 'league']}:{ids.at[int(p), 'source_id']}"
        for p in ids["person_idx"].unique()
    }


def _swap_day_month(d: str) -> str | None:
    y, m, dd = d.split("-")
    return f"{y}-{dd}-{m}" if int(dd) <= 12 and dd != m else None


def fix_roster_dates(
    rosters: pd.DataFrame, stints: pd.DataFrame
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Some Wikipedia roster tables give a birth date with day and month swapped, or a day
    off. A roster date that matches no league record of that name is replaced when the
    league records of that name carry exactly one birth date and it is the swapped date or
    one day away, or it is in the same year and month and every other roster row of that
    player (same name, same team) gives it. Each replacement is reported."""
    if rosters is None or not len(rosters):
        return rosters, []
    dates: dict[str, set[str]] = defaultdict(set)
    for k, d in zip(stints["key"], stints["birth_date"], strict=True):
        if isinstance(d, str):
            dates[k].add(d)
    r = rosters.copy()
    fixed = []
    keys = r["player"].map(common.link_key)
    col = r.columns.get_loc("birth_date")
    team = r["team_iso3"] if "team_iso3" in r.columns else pd.Series([None] * len(r), index=r.index)
    roster_dates: dict[tuple[str, object], list[str]] = defaultdict(list)
    for k, t, d in zip(keys, team, r["birth_date"], strict=True):
        if isinstance(d, str):
            roster_dates[(k, t)].append(d)
    for i, (k, d) in enumerate(zip(keys, r["birth_date"], strict=True)):
        if not isinstance(d, str) or d in dates.get(k, ()):
            continue
        cands = dates.get(k, set())
        if len(cands) != 1:
            continue
        c = next(iter(cands))
        one_day = abs((pd.Timestamp(c) - pd.Timestamp(d)).days) == 1
        others = list(roster_dates.get((k, team.iat[i]), []))
        others.remove(d)
        rosters_agree = bool(others) and set(others) == {c} and c[:7] == d[:7]
        if c == _swap_day_month(d) or one_day or rosters_agree:
            r.iat[i, col] = c
            fixed.append(
                {
                    "event": r["event"].iat[i],
                    "year": int(r["year"].iat[i]),
                    "player": r["player"].iat[i],
                    "roster_date": d,
                    "used": c,
                    "reason": "one day" if one_day else ("day and month swapped" if c == _swap_day_month(d) else "day differs; the player's other rosters give the league date"),
                }
            )
    return r, fixed


def build(tables: dict[str, pd.DataFrame]) -> Linked:
    stints = standardise_all(tables)
    rosters, fixed_dates = fix_roster_dates(tables.get("rosters"), stints)
    ids = link(identity_table(stints, rosters))
    persons = resolve_nationality(ids, stints)
    pid = person_ids(ids)
    persons.insert(0, "person_id", persons["person_idx"].map(pid))

    s = stints.merge(
        ids[["league", "source_id", "person_idx", "link_basis"]],
        on=["league", "source_id"],
        how="left",
    )
    s = s.merge(
        persons[
            [
                "person_idx",
                "person_id",
                "nationality",
                "nat_basis",
                "nat_conflict",
                "birth_date",
                "birth_year",
                "person_position",
            ]
        ].rename(
            columns={
                "nat_basis": "person_nat_basis",
                "birth_date": "person_birth_date",
                "birth_year": "person_birth_year",
            }
        ),
        on="person_idx",
        how="left",
    )
    own = (s["nat_value"] == s["nationality"]) & (s["nat_basis"] == s["person_nat_basis"])
    s["row_nat_basis"] = s["nat_basis"].where(
        own.fillna(False),
        ("linked: " + s["person_nat_basis"].astype("string")).where(
            s["nationality"].notna(), "unknown"
        ),
    )
    s["position"] = s["position"].fillna(s["person_position"])
    s["birth_date"] = s["birth_date"].fillna(s["person_birth_date"])
    s["birth_year"] = s["birth_year"].fillna(s["person_birth_year"].astype("float64"))
    s = s.drop(columns=["person_position", "person_birth_date", "person_birth_year"])
    s["is_goalie"] = s["position"] == "G"
    s = add_thresholds(s)
    linked = Linked(stints=s, identities=ids, persons=persons, rosters=rosters)
    linked.report = linking_report(linked)
    linked.report["roster_birth_dates_swapped"] = fixed_dates
    return linked


def add_thresholds(s: pd.DataFrame) -> pd.DataFrame:
    """`schedule` and `threshold` per league-season, `qualifies` per row (common.THRESHOLD_SHARE)."""
    sched = (
        s[~(s["position"] == "G")]
        .groupby(["league", "season_start"])["games_played"]
        .apply(common.schedule_length)
        .rename("schedule")
        .reset_index()
    )
    s = s.drop(columns=[c for c in ("schedule", "threshold") if c in s.columns])
    s = s.merge(sched, on=["league", "season_start"], how="left")
    s["schedule"] = s["schedule"].fillna(0).astype(int)
    s["threshold"] = s["schedule"].map(common.games_threshold)
    s["qualifies"] = s["games_played"].fillna(0) >= s["threshold"]
    return s


# =====================================================================================
# Report
# =====================================================================================


def linking_report(linked: Linked) -> dict[str, Any]:
    ids, s, persons = linked.identities, linked.stints, linked.persons
    per_person_sources = ids.groupby("person_idx")["league"].agg(lambda x: set(x))
    ids = ids.assign(
        other_sources=[
            len(per_person_sources[p] - {lg})
            for p, lg in zip(ids["person_idx"], ids["league"], strict=True)
        ]
    )

    by_league = {}
    for lg, grp in ids.groupby("league", sort=False):
        dob = grp["birth_date"].notna()
        nodob = grp[~dob]
        by_league[lg] = {
            "records": len(grp),
            "with_birth_date": int(dob.sum()),
            "with_birth_date_share": float(dob.mean()),
            "linked_on_name_and_birth_date_to_another_source": int(
                (
                    grp["link_basis"].isin(["dob", "dob_name_variant"]) & (grp["other_sources"] > 0)
                ).sum()
            ),
            "linked_on_first_name_variant": int((grp["link_basis"] == "dob_name_variant").sum()),
            "without_birth_date": len(nodob),
            "name_only_linked": int((nodob["link_basis"] == "name_only").sum()),
            "ambiguous": int((nodob["link_basis"] == "ambiguous").sum()),
            "unmatched": int((nodob["link_basis"] == "unmatched").sum()),
            "joined_within_league_on_name": int((nodob["link_basis"] == "same_league_name").sum()),
            "name_only_link_rate": float((nodob["link_basis"] == "name_only").mean())
            if len(nodob)
            else None,
        }

    def basis_counts(frame: pd.DataFrame) -> dict[str, int]:
        return {str(k): int(v) for k, v in frame["row_nat_basis"].value_counts().items()}

    nat_by_league = {
        lg: {"all_rows": basis_counts(g), "qualifying_rows": basis_counts(g[g["qualifies"]])}
        for lg, g in s.groupby("league", sort=False)
    }

    ls = (
        s.groupby(["league", "season_start"])
        .apply(
            lambda g: pd.Series(
                {
                    "rows": len(g),
                    "qualifying": int(g["qualifies"].sum()),
                    "identified_share": float(g["nationality"].notna().mean()),
                    "qualifying_identified_share": float(
                        g.loc[g["qualifies"], "nationality"].notna().mean()
                    )
                    if g["qualifies"].any()
                    else float("nan"),
                    "birth_year_share": float(g["birth_year"].notna().mean()),
                    "position_share": float(g["position"].notna().mean()),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    league_seasons = [
        {
            "league": r.league,
            "season": common.season_label(int(r.season_start)),
            **{
                k: getattr(r, k)
                for k in (
                    "rows",
                    "qualifying",
                    "identified_share",
                    "qualifying_identified_share",
                    "birth_year_share",
                    "position_share",
                )
            },
        }
        for r in ls.itertuples()
    ]

    conflicts = persons[persons["nat_conflict"]]
    czech_elig_vs_citizenship = persons[
        persons["nat_values"].fillna("").str.contains("CZE") & (persons["nationality"] != "CZE")
    ]
    examples = []
    for r in conflicts.sort_values("person_id").head(25).itertuples():
        name = s.loc[s["person_idx"] == r.person_idx, "full_name"].iloc[0]
        examples.append(
            {
                "person_id": r.person_id,
                "name": name,
                "values": r.nat_values,
                "chosen": r.nationality,
                "basis": r.nat_basis,
            }
        )

    return {
        "definitions": {
            "link_key": "name: diacritics folded, lower case, hyphens as spaces, tokens sorted",
            "step_1": "name + full birth date",
            "step_1b": "first-name initial + surname + full birth date (first-name variants such as Dan/Daniel)",
            "step_2": f"records without a birth date: name only, when exactly one person with that "
            f"name has seasons within {NAME_ONLY_WINDOW} seasons and no contradicting birth year",
            "step_2b": f"records still unmatched: same league, same name, seasons within {NAME_ONLY_WINDOW}",
            "nationality_order": [
                "citizenship (NHL first, else most frequent Liiga/SHL code)",
                "national-team roster (IIHF eligibility)",
                "eligibility or licence (DEL Nat, Extraliga foreigner flag, NL Swiss licence)",
            ],
            "czechoslovakia": "the NHL recodes Czechoslovak-era births to CZE or SVK; that code is used",
            "sources": {
                "NHL": "nationalityCode: citizenship",
                "Liiga": "nationality: citizenship",
                "SHL": "nationality where not N/A: citizenship (N/A before about 2010)",
                "Extraliga": "foreigner flag: not a foreigner -> CZE (eligibility); foreigners have no code",
                "DEL": "Nat, 2022/23 onward: licence (eligibility)",
                "NL": "Swiss licence -> CHE (eligibility); foreign licence and goalies have no code",
                "roster": "World Championship and Olympic rosters from 2010: national team",
            },
        },
        "persons": len(persons),
        "persons_with_nationality": int(persons["nationality"].notna().sum()),
        "records_by_league": by_league,
        "nationality_basis_by_league": nat_by_league,
        "league_seasons": league_seasons,
        "conflicts": {
            "persons": len(conflicts),
            "czech_eligibility_overridden_by_citizenship": len(czech_elig_vs_citizenship),
            "examples": examples,
        },
    }


# =====================================================================================
# Entry points
# =====================================================================================


def load_tables() -> dict[str, pd.DataFrame]:
    return {f.removesuffix(".parquet"): common.load(f) for f in SNAPSHOT_FILES}


@lru_cache(maxsize=1)
def linked() -> Linked:
    """The linked table for the committed snapshot, built once per process."""
    return build(load_tables())


def main() -> None:
    lk = linked()
    path = common.write_output("linking.json", lk.report, SNAPSHOT_FILES)
    LOG.info("wrote %s (%d persons)", path, lk.report["persons"])


if __name__ == "__main__":
    from src.logging_setup import setup

    setup()
    main()
