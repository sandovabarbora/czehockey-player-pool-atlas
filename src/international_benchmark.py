"""International peer benchmarking — Czech NHL cohort vs FIN/SWE/CAN/USA peers.

Reads all 1183 cached NHL player landings (not just Czech-filtered) and joins
with MoneyPuck per-60 production data to compute cohort-level comparisons:

    For each (country, position, age_cohort):
        - n_players
        - median P/GP (raw, 5v5 + special teams from MoneyPuck "all" situation)
        - mean P/GP
        - top performer P/GP

This is the "what the federation doesn't have" deliverable. Czech hockey
experts know their own players individually; they don't have a quantified
view of where Czech NHL pool sits structurally vs Finnish/Swedish/Canadian
peers at each age cohort.

Inputs:
    data/raw/.cache/nhl_landing/{id}.json   (1183 player landings, all countries)
    data/raw/moneypuck_skaters_2025.parquet (per-player production)
    data/raw/moneypuck_skaters_2024.parquet

Outputs:
    data/processed/international_cohort.parquet  — one row per (country × position × cohort × season)
    outputs/intl_cohort_heatmap.svg              — visual: countries × cohorts heatmap
    outputs/intl_cohort_summary.md               — Czech-language analysis paragraphs
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet, write_parquet

# Palette aligned with templates/style.css and src/render.py.
NAVY        = "#1f3a5f"
NAVY_DEEP   = "#162a44"
OXBLOOD     = "#9c3a2a"
INK         = "#2a261f"
MUTED       = "#8a857b"
RULE        = "#c8c2b7"
CREAM       = "#fdfbf6"
CREAM_TINT  = "#efe9dc"

# Sequential ramp cream → navy. Reads as "more production = more visual weight"
# without the YlGnBu green-teal SaaS-dashboard vocabulary.
CMAP_NAVY = LinearSegmentedColormap.from_list(
    "cream_to_navy",
    [
        (0.00, CREAM_TINT),
        (0.30, "#c4c3bc"),
        (0.55, "#7e8eaa"),
        (0.80, NAVY),
        (1.00, NAVY_DEEP),
    ],
    N=256,
)

# Matplotlib font defaults — share render.py's chain.
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = [
    "Spectral", "Cambria", "Georgia", "Times New Roman", "DejaVu Serif",
]
plt.rcParams["font.sans-serif"] = [
    "Bricolage Grotesque", "Helvetica Neue", "Arial", "DejaVu Sans",
]
plt.rcParams["text.color"] = INK

LOG = logging.getLogger(__name__)

LANDING_CACHE_DIR = config.RAW_DIR / ".cache" / "nhl_landing"

# Top hockey nations to include in benchmark. Russia excluded (political /
# data quality, per locked decision). Slovakia included as direct CZ peer.
COUNTRIES = ["CAN", "USA", "SWE", "FIN", "CZE", "SVK"]

# Population (millions, ~2024). For per-capita normalization talking points.
POPULATION_M = {
    "CAN": 40.1,
    "USA": 335.0,
    "SWE": 10.6,
    "FIN": 5.6,
    "CZE": 10.9,
    "SVK": 5.4,
}

# Age cohort buckets. Edges in birth year for season's calendar year minus age.
# For season starting 2025 (i.e. 2025-26): age = 2025 - birth_year.
COHORTS = [
    ("U22", 18, 21),   # prospects / rookies
    ("23-25", 22, 25), # establishing
    ("26-29", 26, 29), # prime
    ("30+", 30, 99),   # veterans
]

# Position normalization (NHL landing 'position' field)
POS_F = {"C", "L", "R"}
POS_D = {"D"}


# --- Load landing metadata for ALL nationalities ---


def load_all_landings() -> pd.DataFrame:
    """Read every cached NHL landing into a DataFrame (no country filter)."""
    rows: list[dict] = []
    for f in LANDING_CACHE_DIR.iterdir():
        if not f.name.endswith(".json"):
            continue
        try:
            with f.open(encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        pid = d.get("playerId")
        bc = d.get("birthCountry")
        pos = d.get("position")
        bd = d.get("birthDate")
        if not (pid and bc and pos and bd):
            continue
        # birthDate is ISO YYYY-MM-DD
        try:
            birth_year = int(bd[:4])
        except (ValueError, TypeError):
            continue
        rows.append({
            "player_id": int(pid),
            "birth_country": bc,
            "birth_year": birth_year,
            "position_raw": pos,
            "position": "F" if pos in POS_F else ("D" if pos in POS_D else "G"),
            "first_name": d.get("firstName", {}).get("default"),
            "last_name": d.get("lastName", {}).get("default"),
        })
    return pd.DataFrame(rows)


# --- Cohort assignment ---


def assign_cohort(birth_year: int, season: int) -> str | None:
    """Return cohort label for a player given (birth_year, season starting year)."""
    age = season - birth_year
    for label, lo, hi in COHORTS:
        if lo <= age <= hi:
            return label
    return None


# --- Build cohort aggregate ---


def build_cohort_table(season: int) -> pd.DataFrame:
    """For one season, compute (country × position × cohort) → aggregate stats."""
    landings = load_all_landings()
    landings = landings[landings["birth_country"].isin(COUNTRIES)]
    landings["cohort"] = landings["birth_year"].apply(lambda y: assign_cohort(int(y), season))
    landings = landings.dropna(subset=["cohort"])

    # MoneyPuck for production stats (per-game, "all" situation)
    mp_path = config.RAW_DIR / f"moneypuck_skaters_{season}.parquet"
    if not mp_path.exists():
        LOG.error("MoneyPuck parquet missing for season %s: %s", season, mp_path)
        return pd.DataFrame()
    mp = read_parquet(mp_path)
    mp = mp[mp["situation"] == "all"].copy()
    mp["P_per_GP"] = (mp["I_F_points"] / mp["games_played"]).astype(float)

    joined = landings.merge(
        mp[["playerId", "games_played", "P_per_GP", "I_F_goals", "I_F_primaryAssists"]],
        left_on="player_id", right_on="playerId", how="inner",
    )
    # Filter to players with meaningful GP — drop 1-game callups
    joined = joined[joined["games_played"] >= 10]

    LOG.info("season %d: %d players after country+GP filter", season, len(joined))

    # Aggregate
    rows: list[dict] = []
    for (country, pos, cohort), grp in joined.groupby(["birth_country", "position", "cohort"]):
        if pos == "G":  # goalies not in this analysis
            continue
        rows.append({
            "season": season,
            "country": country,
            "position": pos,
            "cohort": cohort,
            "n_players": int(len(grp)),
            "n_per_capita_per_M": round(len(grp) / POPULATION_M[country], 2),
            "median_P_per_GP": round(float(grp["P_per_GP"].median()), 3),
            "mean_P_per_GP": round(float(grp["P_per_GP"].mean()), 3),
            "top_P_per_GP": round(float(grp["P_per_GP"].max()), 3),
            "total_GP": int(grp["games_played"].sum()),
        })
    return pd.DataFrame(rows)


# --- Visualization ---


def render_cohort_heatmap(table: pd.DataFrame, out_path: Path) -> None:
    """Two-panel heatmap: forwards + defensemen. Rows = countries, cols = cohorts.
    Cell color = median P/GP (cream → navy ramp); cell annotation = n_players
    over median P/GP. The CZE row is highlighted with an oxblood outline so it
    pops against the navy-tone heatmap."""
    latest_season = int(table["season"].max())
    sub = table[table["season"] == latest_season]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), sharey=True)
    fig.patch.set_facecolor(CREAM)

    cohort_order = [c[0] for c in COHORTS]
    country_order = COUNTRIES
    n_countries = len(country_order)
    n_cohorts = len(cohort_order)

    for ax, position, title in (
        (axes[0], "F", "Útočníci"),
        (axes[1], "D", "Obránci"),
    ):
        sub_pos = sub[sub["position"] == position]
        matrix = np.full((n_countries, n_cohorts), np.nan)
        n_matrix = np.zeros((n_countries, n_cohorts), dtype=int)
        for i, country in enumerate(country_order):
            for j, cohort in enumerate(cohort_order):
                row = sub_pos[(sub_pos["country"] == country) & (sub_pos["cohort"] == cohort)]
                if not row.empty:
                    matrix[i, j] = row.iloc[0]["median_P_per_GP"]
                    n_matrix[i, j] = int(row.iloc[0]["n_players"])

        ax.imshow(matrix, cmap=CMAP_NAVY, aspect="auto", vmin=0.0, vmax=1.0)
        ax.set_xticks(range(n_cohorts))
        ax.set_xticklabels(cohort_order, fontsize=9.5, fontfamily="sans-serif",
                           color=INK)
        ax.set_yticks(range(n_countries))
        ax.set_yticklabels(country_order, fontsize=9.5, fontfamily="sans-serif",
                           color=INK, weight="medium")
        ax.set_title(f"{title}  ·  medián bodů na zápas",
                     fontsize=11.5, fontfamily="serif", color=INK,
                     pad=12, loc="left", weight="normal")

        # Thin tick marks, no rectangular outline
        ax.tick_params(axis="both", which="both", length=0,
                       colors=INK, pad=6)
        for spine in ax.spines.values():
            spine.set_visible(False)

        # Annotate each cell — n on top, value beneath
        for i in range(n_countries):
            for j in range(n_cohorts):
                n = n_matrix[i, j]
                if n == 0:
                    ax.text(j, i, "—", ha="center", va="center",
                            fontsize=10, color=MUTED, fontfamily="serif")
                else:
                    val = matrix[i, j]
                    # Text color threshold for legibility on cream→navy ramp:
                    # midpoint of ramp sits around 0.45–0.55 — switch above 0.55
                    text_color = CREAM if val > 0.55 else INK
                    ax.text(j, i - 0.10, f"n={n}", ha="center", va="center",
                            fontsize=8.5, color=text_color,
                            fontfamily="sans-serif", weight="medium")
                    ax.text(j, i + 0.20, f"{val:.2f}", ha="center", va="center",
                            fontsize=9, color=text_color,
                            fontfamily="serif", weight="normal")

        # Highlight Czech row with an oxblood outline
        cz_idx = country_order.index("CZE")
        ax.add_patch(plt.Rectangle(
            (-0.5, cz_idx - 0.5), n_cohorts, 1,
            fill=False, edgecolor=OXBLOOD, lw=2.2, zorder=8,
        ))

    # Materialize tick labels and repaint the CZE row label in oxblood
    # (post-loop so sharedY does not leave the right axis with empty labels).
    cz_idx = country_order.index("CZE")
    fig.canvas.draw()
    for ax in axes:
        labels = ax.get_yticklabels()
        if cz_idx < len(labels):
            labels[cz_idx].set_color(OXBLOOD)
            labels[cz_idx].set_weight("bold")

    fig.suptitle(
        f"Mezinárodní cohort benchmark  ·  NHL {latest_season}/{latest_season+1 - 2000:02d}",
        fontsize=14, fontfamily="serif", color=INK,
        x=0.02, ha="left", y=1.04, weight="normal",
    )
    fig.text(
        0.02, 0.985,
        "Buňka: počet hráčů a medián bodů na zápas. Vyznačená řada = Česko.",
        ha="left", fontsize=9, color=MUTED, fontfamily="sans-serif",
    )
    plt.subplots_adjust(top=0.88, wspace=0.06)
    plt.savefig(out_path, bbox_inches="tight", format="svg",
                facecolor=CREAM, edgecolor="none")
    plt.close(fig)
    LOG.info("wrote %s", out_path)


# --- Czech-language narrative ---


def build_narrative(table: pd.DataFrame) -> str:
    """Generate Czech analytical paragraphs from the cohort table."""
    latest_season = int(table["season"].max())
    sub = table[table["season"] == latest_season]
    lines = [
        f"# Mezinárodní cohort benchmark — NHL {latest_season}-{latest_season+1}",
        "",
        "## Strukturální pohled na český fond v NHL napříč peer-zeměmi",
        "",
        "Tato analýza není o tom kdo je nejlepší český hokejista. Je o tom **kde "
        "v rámci věkových skupin je český fond v NHL strukturálně tenčí nebo "
        "silnější než peer-země (Finsko, Švédsko, Slovensko, Kanada, USA).** To "
        "je otázka která nezávisí na hokejové intuici — vyžaduje datovou "
        "agregaci kterou jedinec v hlavě nedokáže.",
        "",
        "## Headline čísla (sezóna 2025-26)",
        "",
    ]

    # Total counts by country
    total_by_country = sub.groupby("country")["n_players"].sum().to_dict()
    lines.append("### Celkový počet NHL hráčů (forwards + defensemen, ≥10 GP)")
    lines.append("")
    lines.append("| Země | NHL hráči | Populace (M) | Hráči per M |")
    lines.append("|---|---:|---:|---:|")
    for c in COUNTRIES:
        n = int(total_by_country.get(c, 0))
        pop = POPULATION_M[c]
        per_m = round(n / pop, 2)
        lines.append(f"| {c} | {n} | {pop} | {per_m} |")
    lines.append("")

    # Czech vs peers per-cohort gap
    lines.append("## Specifické gapy v cohortech (vs FIN/SWE)")
    lines.append("")
    for position, pname in (("F", "Útočníci"), ("D", "Obránci")):
        sub_pos = sub[sub["position"] == position]
        cz = sub_pos[sub_pos["country"] == "CZE"]
        if cz.empty:
            continue
        lines.append(f"### {pname}")
        lines.append("")
        for cohort_label, _, _ in COHORTS:
            cz_row = cz[cz["cohort"] == cohort_label]
            if cz_row.empty:
                lines.append(f"- **{cohort_label}**: Čeští hráči v této cohorte v NHL nepřítomni.")
                continue
            cz_n = int(cz_row.iloc[0]["n_players"])
            cz_med = float(cz_row.iloc[0]["median_P_per_GP"])
            comparators = []
            for peer in ("FIN", "SWE", "SVK"):
                peer_row = sub_pos[(sub_pos["country"] == peer) & (sub_pos["cohort"] == cohort_label)]
                if peer_row.empty:
                    continue
                peer_n = int(peer_row.iloc[0]["n_players"])
                peer_med = float(peer_row.iloc[0]["median_P_per_GP"])
                comparators.append(f"{peer} {peer_n} hráčů (medián {peer_med:.2f})")
            line = (
                f"- **{cohort_label}**: ČR {cz_n} hráčů (medián {cz_med:.2f} P/GP). "
                + ("Srovnání: " + ", ".join(comparators) if comparators else "")
            )
            lines.append(line)
        lines.append("")

    lines.append("## Limitations této analýzy")
    lines.append("")
    lines.append(
        "- Pouze NHL. AHL / EU ligy nejsou v této verzi zahrnuty (sledováno "
        "samostatně v hlavním Atlasu)."
    )
    lines.append(
        "- Produkční metrika = points/game ze všech situací. Nezohledňuje "
        "role (top-line vs energy line) ani pozici v rámci forwardů (C vs LW/RW)."
    )
    lines.append(
        "- Cohort buckets jsou pevné (U22/23-25/26-29/30+). Tranzice mezi "
        "cohorty mezi sezónami je očekávaná, ne signál."
    )
    lines.append(
        "- N hráčů je z aktivních NHL rosterů 2025-26 s ≥10 GP. Krátké callupy "
        "vyloučeny."
    )
    lines.append(
        "- Populační normalizace (hráči per milion) je hrubý proxy talent "
        "pipeline; nezohledňuje hokejovou infrastrukturu (počet ledů, mládežnické "
        "úrovně), historický kontext, ani imigrační patterns."
    )
    lines.append("")
    lines.append(
        "Toto NENÍ doporučení pro výběr hráčů ani prognóza. Je to popis "
        "strukturálního stavu fondu napříč peer-zeměmi pro účely plánování "
        "v rámci 4-letého cyklu (MS 2027, ZOH 2030)."
    )
    return "\n".join(lines)


# --- Main ---


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    seasons = config.leagues()["leagues"]["nhl"]["season_window"]
    LOG.info("building international cohort benchmark for seasons %s", seasons)

    all_frames = []
    for season in seasons:
        df = build_cohort_table(season)
        if not df.empty:
            all_frames.append(df)
    if not all_frames:
        LOG.error("no cohort data built")
        return
    table = pd.concat(all_frames, ignore_index=True)
    out_parquet = config.PROCESSED_DIR / "international_cohort.parquet"
    write_parquet(table, out_parquet)

    # Visualization
    heatmap_path = config.OUTPUTS_DIR / "intl_cohort_heatmap.svg"
    render_cohort_heatmap(table, heatmap_path)

    # Narrative
    narrative = build_narrative(table)
    narrative_path = config.OUTPUTS_DIR / "intl_cohort_summary.md"
    narrative_path.write_text(narrative, encoding="utf-8")
    LOG.info("wrote %s", narrative_path)

    # Headline print to console
    latest = int(table["season"].max())
    sub = table[table["season"] == latest]
    LOG.info("=== headline (season %d) ===", latest)
    total = sub.groupby("country")["n_players"].sum().to_dict()
    for c in COUNTRIES:
        n = int(total.get(c, 0))
        per_m = round(n / POPULATION_M[c], 2)
        LOG.info("  %s: %d hráčů, %.2f/M pop", c, n, per_m)


if __name__ == "__main__":
    main()
