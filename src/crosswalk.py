"""Deduplicate players across leagues into one canonical record.

Anchor: NHL player metadata (has clean ISO birth_date, robust nationality flag).
Other sources are matched against the NHL anchor by:
  - Liiga: normalized name + birth year (Liiga exposes both)
  - Extraliga: fuzzy name match only (the /statistiky table has no birthdate;
    fetching /hrac/{slug}/{id} per player to enrich is deferred to a future
    "extraliga metadata pass")

Unmatched players from Liiga/Extraliga become new canonical entries.

Inputs:
    data/raw/nhl_player_meta.parquet
    data/raw/liiga_players_meta.parquet
    data/raw/extraliga_skaters_{season}.parquet  (uses latest available)

Output:
    data/processed/players.parquet
        One row per CANONICAL player. Columns:
            canonical_id (str)     — "nhl-{id}" / "liiga-{id}" / "extraliga-{id}"
            first_name (str)
            last_name (str)
            birth_date (str|NA)    — YYYY-MM-DD when available
            birth_year (int|NA)
            position_normalized (str) — F/D/G
            nhl_id (Int64|NA)
            liiga_id (Int64|NA)
            extraliga_id (Int64|NA)
            nhl_team (str|NA)      — current_team_abbrev from NHL meta (may be NA
                                     if player is not on an NHL roster right now)
            liiga_team (str|NA)
            extraliga_team_id (Int64|NA)
            sources (list[str])    — leagues where this player appears
            n_sources (int)
            czech_eligible_flag (str) — "yes" | "unknown" | "no" (Extraliga
                                        imports flagged "unknown" without birth_country)
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import write_parquet

LOG = logging.getLogger(__name__)

# Score threshold for fuzzy name matching (Extraliga ↔ NHL/Liiga without birthdate).
NAME_MATCH_THRESHOLD = 92


# --- Name normalization -----------------------------------------------------


def normalize_name(name: str | None) -> str:
    """Lowercase, strip diacritics, normalize whitespace.

    'David Pastrňák' -> 'david pastrnak'
    'Lukáš Sedlák'   -> 'lukas sedlak'
    'Markus Hännikäinen' -> 'markus hannikainen'
    """
    if not isinstance(name, str) or not name.strip():
        return ""
    # NFD splits letters from combining marks; we drop the marks.
    nfd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfd if not unicodedata.combining(c))
    # Collapse whitespace, remove junior markers like ' *'
    stripped = re.sub(r"\s*\*\s*$", "", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip().lower()
    return stripped


# --- Date normalization -----------------------------------------------------


def parse_birth_date(s: str | None) -> tuple[str | None, int | None]:
    """Parse various birth-date formats. Return (ISO_str_or_None, year_or_None).

    Handles:
      'YYYY-MM-DD'   (NHL)            -> as-is
      'D.M.YYYY'     (Liiga, Czech)   -> '0YYYY-0M-0D'
      'DD.M.YYYY' or other variants
    """
    if not isinstance(s, str) or not s.strip():
        return None, None
    s = s.strip()
    # ISO
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", int(y)
    # D.M.YYYY (Czech / Finnish)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}", int(y)
    LOG.debug("unparseable birth date: %r", s)
    return None, None


# --- Position normalization -------------------------------------------------


_NHL_POS_MAP = {
    "C": "F", "L": "F", "R": "F", "F": "F",
    "D": "D",
    "G": "G",
}

_LIIGA_POS_MAP = {
    # Finnish position codes observed in Liiga players list
    "MV": "G",
    "VP": "D", "PP": "D", "OP": "D",
    "KH": "F", "VL": "F", "OL": "F", "LP": "F", "KP": "F",
}

_EXTRALIGA_POS_MAP = {
    "Ú": "F",  # Útočník
    "O": "D",  # Obránce
    # Goalies (B = Brankář) would be here if /statistiky exposed them
    "B": "G",
}


def normalize_position(code: str | None, source: str) -> str | None:
    """Map source-specific position codes to F / D / G."""
    if not isinstance(code, str):
        return None
    code = code.strip()
    if source == "nhl":
        return _NHL_POS_MAP.get(code, None)
    if source == "liiga":
        return _LIIGA_POS_MAP.get(code, None)
    if source == "extraliga":
        return _EXTRALIGA_POS_MAP.get(code, None)
    return None


# --- Source loaders ---------------------------------------------------------


def load_nhl_meta() -> pd.DataFrame:
    path = config.RAW_DIR / "nhl_player_meta.parquet"
    df = pd.read_parquet(path)
    parsed = df["birth_date"].apply(parse_birth_date)
    df["birth_date_iso"] = parsed.map(lambda t: t[0])
    df["birth_year"] = parsed.map(lambda t: t[1]).astype("Int64")
    df["position_normalized"] = df["position"].apply(lambda p: normalize_position(p, "nhl"))
    df["full_name"] = (df["first_name"].fillna("") + " " + df["last_name"].fillna("")).str.strip()
    df["name_normalized"] = df["full_name"].apply(normalize_name)
    return df


def load_liiga_meta() -> pd.DataFrame:
    path = config.RAW_DIR / "liiga_players_meta.parquet"
    df = pd.read_parquet(path)
    parsed = df["date_of_birth"].apply(parse_birth_date)
    df["birth_date_iso"] = parsed.map(lambda t: t[0])
    df["birth_year"] = parsed.map(lambda t: t[1]).astype("Int64")
    df["position_normalized"] = df["role_code"].apply(lambda p: normalize_position(p, "liiga"))
    df["name_normalized"] = df["name"].apply(normalize_name)
    return df


def load_iihf_participation() -> pd.DataFrame:
    """Load IIHF Czech participation rows (one row per player-tournament)."""
    path = config.RAW_DIR / "iihf_participation.parquet"
    if not path.exists():
        LOG.info("IIHF: no participation parquet found (run fetch_iihf first)")
        return pd.DataFrame()
    return pd.read_parquet(path)


def annotate_with_iihf(canonical: pd.DataFrame, iihf: pd.DataFrame) -> pd.DataFrame:
    """For each canonical player, check IIHF appearances and flag eligibility.

    Match key: name_normalized. When IIHF has a birth_year and canonical also
    does, require year ±1 as a hard gate. When canonical lacks birth_year
    (some Extraliga players might), name-only is acceptable since IIHF is a
    Czech-only roster — any name match is a strong eligibility signal.
    """
    if iihf.empty:
        canonical["iihf_appearances"] = 0
        canonical["iihf_tournaments"] = [[] for _ in range(len(canonical))]
        return canonical

    # Build a (name, year_set) index from IIHF
    iihf_by_name: dict[str, list[tuple[int | None, str, int]]] = {}
    for _, r in iihf.iterrows():
        key = r["name_normalized"]
        if not key:
            continue
        year = int(r["birth_year"]) if pd.notna(r.get("birth_year")) else None
        iihf_by_name.setdefault(key, []).append((year, r["tournament"], int(r["year"])))

    appearances: list[int] = []
    tournaments_seen: list[list[str]] = []
    new_flags: list[str] = []
    for _, p in canonical.iterrows():
        name = normalize_name(f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip())
        matches = iihf_by_name.get(name, [])
        # Filter by birth_year gate when both have it
        canonical_year = int(p["birth_year"]) if pd.notna(p.get("birth_year")) else None
        kept = []
        for iihf_year, t, ty in matches:
            if canonical_year is not None and iihf_year is not None:
                if abs(iihf_year - canonical_year) > 1:
                    continue
            kept.append(f"{t}-{ty}")
        appearances.append(len(kept))
        tournaments_seen.append(kept)
        # Upgrade "unknown" to "yes" when we have an IIHF hit
        cur = p.get("czech_eligible_flag")
        if kept and cur == "unknown":
            new_flags.append("yes")
        else:
            new_flags.append(cur)
    canonical["iihf_appearances"] = appearances
    canonical["iihf_tournaments"] = tournaments_seen
    canonical["czech_eligible_flag"] = new_flags
    return canonical


def load_extraliga_players() -> pd.DataFrame:
    """Aggregate one row per Extraliga player_id (across mid-season trades).

    If extraliga_player_meta.parquet exists (from the birth-date enrichment
    pass), merge in birth_date and birth_year. Without it, those columns are
    NA and downstream matching falls back to name-only fuzzy.
    """
    # Find the latest season parquet present
    seasons = sorted(config.RAW_DIR.glob("extraliga_skaters_*.parquet"))
    if not seasons:
        return pd.DataFrame()
    df = pd.read_parquet(seasons[-1])
    agg = (
        df.groupby("player_id", as_index=False)
        .agg({
            "JMÉNO": "first",
            "POZ.": "first",
            "player_slug": "first",
            "source_team_id": "first",
            "source_team_slug": "first",
            "GP": "sum",
        })
    )
    agg["position_normalized"] = agg["POZ."].apply(lambda p: normalize_position(p, "extraliga"))
    agg["name_normalized"] = agg["JMÉNO"].apply(normalize_name)

    # Optional birth-date enrichment from extraliga_player_meta.parquet
    meta_path = config.RAW_DIR / "extraliga_player_meta.parquet"
    if meta_path.exists():
        meta = pd.read_parquet(meta_path)
        parsed = meta["birth_date"].apply(parse_birth_date)
        meta["birth_date_iso"] = parsed.map(lambda t: t[0])
        meta["birth_year"] = parsed.map(lambda t: t[1]).astype("Int64")
        agg = agg.merge(meta[["player_id", "birth_date_iso", "birth_year"]],
                        on="player_id", how="left")
        n_with_bd = agg["birth_date_iso"].notna().sum()
        LOG.info("Extraliga enriched: %d/%d players have birth_date", n_with_bd, len(agg))
    else:
        agg["birth_date_iso"] = pd.NA
        agg["birth_year"] = pd.array([pd.NA] * len(agg), dtype="Int64")
        LOG.info("Extraliga: no birth-date enrichment found (run enrich_birth_dates first)")

    return agg


# --- Matching ---------------------------------------------------------------


def _best_name_match(
    target_name_norm: str,
    target_birth_year: int | None,
    candidates: pd.DataFrame,
    *,
    require_birth_year_within: int = 1,
    threshold: int = NAME_MATCH_THRESHOLD,
) -> int | None:
    """Return index of best matching candidate row, or None if no good match.

    Args:
        target_name_norm: name to look up (already normalized).
        target_birth_year: birth year to require (None = no constraint).
        candidates: DataFrame with columns 'name_normalized' (and 'birth_year'
            if target_birth_year is given).
        require_birth_year_within: max year difference allowed when both have one.
        threshold: minimum rapidfuzz token_set_ratio for a match.
    """
    if candidates.empty or not target_name_norm:
        return None
    best_idx: int | None = None
    best_score = 0
    for idx, row in candidates.iterrows():
        cand_name = row.get("name_normalized") or ""
        cand_year = row.get("birth_year")
        # If we have years on both sides, enforce closeness as a hard gate
        if target_birth_year is not None and pd.notna(cand_year):
            if abs(int(cand_year) - target_birth_year) > require_birth_year_within:
                continue
        score = fuzz.token_set_ratio(target_name_norm, cand_name)
        if score > best_score:
            best_score = score
            best_idx = idx
    if best_score >= threshold:
        return best_idx
    return None


# --- Build canonical table --------------------------------------------------


def build_canonical_table() -> pd.DataFrame:
    nhl = load_nhl_meta()
    liiga = load_liiga_meta()
    extraliga = load_extraliga_players()

    LOG.info("inputs: NHL=%d, Liiga=%d, Extraliga(unique)=%d",
             len(nhl), len(liiga), len(extraliga))

    # ---- Initialize canonical from NHL ----
    rows: list[dict[str, Any]] = []
    for _, p in nhl.iterrows():
        rows.append({
            "canonical_id": f"nhl-{int(p['player_id'])}",
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "birth_date": p["birth_date_iso"],
            "birth_year": p["birth_year"],
            "position_normalized": p["position_normalized"],
            "nhl_id": int(p["player_id"]),
            "liiga_id": pd.NA,
            "extraliga_id": pd.NA,
            "nhl_team": p["current_team_abbrev"],
            "liiga_team": pd.NA,
            "extraliga_team_id": pd.NA,
            "sources": ["nhl"],
            "czech_eligible_flag": "yes" if p["birth_country"] == "CZE" else "no",
            "_name_norm": normalize_name(p["full_name"]),
        })
    canonical = pd.DataFrame(rows)
    LOG.info("anchored canonical table at %d NHL players", len(canonical))

    # ---- Merge Liiga: match on normalized name + birth year ----
    matched_liiga = 0
    new_liiga = 0
    for _, p in liiga.iterrows():
        # Build a candidate frame from the *current* canonical state
        cand_df = pd.DataFrame({
            "name_normalized": canonical["_name_norm"].values,
            "birth_year": canonical["birth_year"].values,
        })
        target_name = p["name_normalized"]
        target_year = int(p["birth_year"]) if pd.notna(p["birth_year"]) else None
        match_idx = _best_name_match(target_name, target_year, cand_df)

        if match_idx is not None:
            canonical.at[match_idx, "liiga_id"] = int(p["player_id"])
            canonical.at[match_idx, "liiga_team"] = p["team_short"]
            canonical.at[match_idx, "sources"] = canonical.at[match_idx, "sources"] + ["liiga"]
            matched_liiga += 1
        else:
            canonical = pd.concat([canonical, pd.DataFrame([{
                "canonical_id": f"liiga-{int(p['player_id'])}",
                "first_name": (p["name"].split()[0] if isinstance(p["name"], str) else None),
                "last_name": (" ".join(p["name"].split()[1:]) if isinstance(p["name"], str) else None),
                "birth_date": p["birth_date_iso"],
                "birth_year": p["birth_year"],
                "position_normalized": p["position_normalized"],
                "nhl_id": pd.NA,
                "liiga_id": int(p["player_id"]),
                "extraliga_id": pd.NA,
                "nhl_team": pd.NA,
                "liiga_team": p["team_short"],
                "extraliga_team_id": pd.NA,
                "sources": ["liiga"],
                "czech_eligible_flag": "yes" if p["nationality"] == "CZE" else "no",
                "_name_norm": target_name,
            }])], ignore_index=True)
            new_liiga += 1
    LOG.info("Liiga merged: %d matched to NHL, %d new canonical entries", matched_liiga, new_liiga)

    # ---- Merge Extraliga: match against existing NHL/Liiga canonical rows.
    # If the Extraliga player has an enriched birth_year (from
    # extraliga_player_meta.parquet), use birth_year ±1 as a hard gate
    # (much stronger). Otherwise fall back to name-only fuzzy.
    # Don't fuzzy-match Extraliga against other Extraliga — same name from a
    # different player_id is a different person (Extraliga's player_id is
    # authoritative within the league). ----
    matched_ext = 0
    new_ext = 0
    for _, p in extraliga.iterrows():
        eligible_mask = canonical["extraliga_id"].isna() & (
            canonical["nhl_id"].notna() | canonical["liiga_id"].notna()
        )
        cand_df = pd.DataFrame({
            "name_normalized": canonical.loc[eligible_mask, "_name_norm"].values,
            "birth_year": canonical.loc[eligible_mask, "birth_year"].values,
        }, index=canonical.index[eligible_mask])
        target_name = p["name_normalized"]
        target_year = int(p["birth_year"]) if pd.notna(p.get("birth_year")) else None
        match_idx = _best_name_match(
            target_name, target_year, cand_df,
            require_birth_year_within=1,
            threshold=NAME_MATCH_THRESHOLD,
        )
        if match_idx is not None:
            canonical.at[match_idx, "extraliga_id"] = int(p["player_id"])
            canonical.at[match_idx, "extraliga_team_id"] = p["source_team_id"]
            canonical.at[match_idx, "sources"] = canonical.at[match_idx, "sources"] + ["extraliga"]
            matched_ext += 1
        else:
            # Best-effort first/last split for Extraliga names
            parts = (p["JMÉNO"] or "").split() if isinstance(p["JMÉNO"], str) else []
            first = parts[0] if parts else None
            last = " ".join(parts[1:]) if len(parts) > 1 else None
            canonical = pd.concat([canonical, pd.DataFrame([{
                "canonical_id": f"extraliga-{int(p['player_id'])}",
                "first_name": first,
                "last_name": last,
                "birth_date": p.get("birth_date_iso") if pd.notna(p.get("birth_date_iso")) else pd.NA,
                "birth_year": p.get("birth_year") if pd.notna(p.get("birth_year")) else pd.NA,
                "position_normalized": p["position_normalized"],
                "nhl_id": pd.NA,
                "liiga_id": pd.NA,
                "extraliga_id": int(p["player_id"]),
                "nhl_team": pd.NA,
                "liiga_team": pd.NA,
                "extraliga_team_id": p["source_team_id"],
                "sources": ["extraliga"],
                # hokej.cz profiles don't expose birthCountry — eligibility
                # for Extraliga players stays "unknown" without an alternate
                # nationality source. Most are Czech, ~10-15% are imports.
                "czech_eligible_flag": "unknown",
                "_name_norm": target_name,
            }])], ignore_index=True)
            new_ext += 1
    LOG.info("Extraliga merged: %d matched to existing, %d new canonical entries", matched_ext, new_ext)

    canonical["n_sources"] = canonical["sources"].apply(len)

    # IIHF eligibility annotation
    iihf = load_iihf_participation()
    if not iihf.empty:
        canonical = annotate_with_iihf(canonical, iihf)
        n_upgraded = (canonical["iihf_appearances"] > 0).sum()
        LOG.info("IIHF annotation: %d canonical players have IIHF appearances", n_upgraded)

    canonical = canonical.drop(columns=["_name_norm"])
    return canonical


def main() -> None:
    logging_setup()
    config.ensure_dirs()
    canonical = build_canonical_table()
    out = config.PROCESSED_DIR / "players.parquet"
    write_parquet(canonical, out)
    LOG.info("=== canonical summary ===")
    LOG.info("total canonical players: %d", len(canonical))
    LOG.info("by n_sources: %s", canonical["n_sources"].value_counts().to_dict())
    LOG.info("by czech_eligible_flag: %s", canonical["czech_eligible_flag"].value_counts().to_dict())
    LOG.info("by position: %s", canonical["position_normalized"].value_counts().to_dict())
    # Highlight all multi-source matches
    multi = canonical[canonical["n_sources"] >= 2]
    LOG.info("multi-source player matches: %d", len(multi))
    if not multi.empty:
        for _, p in multi.iterrows():
            LOG.info("  %s %s (NHL %s | Liiga %s | Extraliga %s)",
                     p["first_name"], p["last_name"],
                     int(p["nhl_id"]) if pd.notna(p["nhl_id"]) else "-",
                     int(p["liiga_id"]) if pd.notna(p["liiga_id"]) else "-",
                     int(p["extraliga_id"]) if pd.notna(p["extraliga_id"]) else "-")


if __name__ == "__main__":
    main()
