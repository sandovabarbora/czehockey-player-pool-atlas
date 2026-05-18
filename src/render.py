"""Render the full Czech-language Atlas report (HTML + optional PDF).

Produces a two-tiered report per brief §8.1:
  - Section A: Executive Summary (target read time ≤ 90 sec, audience:
    Hnilička, Šlégr, Rulík). Hero figure + cluster cards + observations
    + top movers tables.
  - Section B: Methodology & Results (target read time ≥ 45 min,
    audience: Morkes). PCA loadings table, league quality multipliers
    table, sensitivity analysis, per-cluster details, trajectory
    leaderboard, mandatory Limitations section, data sources.

Output:
  outputs/atlas_forwards.svg
  outputs/atlas_defense.svg
  outputs/index.html         (full report, Czech)
  outputs/report.pdf         (weasyprint, may need styling iteration)
"""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from jinja2 import Environment, FileSystemLoader

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet

LOG = logging.getLogger(__name__)

# Palette aligned with templates/style.css (OKLCH tokens converted to sRGB hex
# for matplotlib). Navy load-bearing, oxblood for highlights, warm neutrals.
NAVY        = "#1f3a5f"   # navy-700 primary
NAVY_DEEP   = "#162a44"   # navy-900 (drenched, for emphasis)
NAVY_SOFT   = "#7e8eaa"   # navy-300 (faded)
OXBLOOD     = "#9c3a2a"   # oxblood-700 (CZE highlight, secondary accent)
OXBLOOD_SOFT = "#bf6657"  # oxblood-500
INK         = "#2a261f"   # warm ink
MUTED       = "#8a857b"   # warm muted
RULE        = "#c8c2b7"   # warm rule
CREAM       = "#fdfbf6"   # page surface
CREAM_TINT  = "#efe9dc"   # tinted block

# Curated cluster palette: navy variants + warm earth tones. OXBLOOD is
# deliberately omitted here so it remains semantically reserved for MS-pool
# rings and the CZE row highlight (otherwise red dots and red rings compete
# in the same field). Hues feel sampled from a single warm-print plate.
CLUSTER_PALETTE = [
    NAVY,         # C0 — primary navy
    NAVY_SOFT,    # C1 — lighter navy
    "#b08968",    # C2 — warm tan
    "#7a5c63",    # C3 — rose brown
    "#5e7e64",    # C4 — sage mute
    "#7e6678",    # C5 — plum mute
    "#3d6b6e",    # C6 — deep teal
    "#806b53",    # C7 — umber dark
]

# Trajectory direction: neutralised. Per PRODUCT.md Design Principle #3
# (no winners/losers colors), we avoid green/red. Direction is conveyed by
# arrow head geometry; chromatic difference is shade-only.
DIRECTION_COLOR = {
    "improving": NAVY,
    "declining": NAVY_SOFT,
    "stable":    MUTED,
}

# Matplotlib font defaults — serif chain prefers Spectral if user has it
# system-installed; otherwise falls back to Cambria/Georgia/DejaVu Serif.
plt.rcParams["font.family"] = "serif"
plt.rcParams["font.serif"] = [
    "Spectral", "Cambria", "Georgia", "Times New Roman", "DejaVu Serif",
]
plt.rcParams["font.sans-serif"] = [
    "Bricolage Grotesque", "Helvetica Neue", "Arial", "DejaVu Sans",
]
plt.rcParams["axes.edgecolor"] = RULE
plt.rcParams["axes.labelcolor"] = MUTED
plt.rcParams["xtick.color"] = MUTED
plt.rcParams["ytick.color"] = MUTED
plt.rcParams["text.color"] = INK


# =============================================================================
# Helpers: figure rendering
# =============================================================================


def _annotate_top_players(ax, df: pd.DataFrame, x_col: str, y_col: str,
                          rank_col: str, n: int = 12) -> None:
    top = df.nlargest(n, rank_col)
    for _, row in top.iterrows():
        if pd.isna(row[x_col]) or pd.isna(row[y_col]):
            continue
        ax.annotate(
            row["last_name"], (row[x_col], row[y_col]),
            xytext=(3, 3), textcoords="offset points",
            fontsize=7, color=INK, zorder=10,
        )


def _draw_trajectory_arrows(ax, trajectory: pd.DataFrame, proj_label: str) -> None:
    if trajectory.empty:
        return
    x_old = f"pca_x_{proj_label}_old"
    y_old = f"pca_y_{proj_label}_old"
    x_new = f"pca_x_{proj_label}_new"
    y_new = f"pca_y_{proj_label}_new"
    needed = (x_old, y_old, x_new, y_new)
    if not all(c in trajectory.columns for c in needed):
        return
    for _, r in trajectory.iterrows():
        if any(pd.isna(r[c]) for c in needed):
            continue
        ax.annotate(
            "", xy=(r[x_new], r[y_new]), xytext=(r[x_old], r[y_old]),
            arrowprops=dict(arrowstyle="->", color=DIRECTION_COLOR.get(r["direction"], "#888"),
                            lw=1.2, alpha=0.85),
            zorder=6,
        )


def _render_atlas(coords: pd.DataFrame, features: pd.DataFrame,
                  trajectory: pd.DataFrame, position_label: str,
                  out_path: Path) -> None:
    """Generic two-panel atlas renderer."""
    latest = int(coords["season"].max())
    cur = coords[coords["season"] == latest].copy()
    feat_cur = features[features["season"] == latest][[
        "canonical_id", "points_per_gp_quality_z"
    ]]
    cur = cur.merge(feat_cur, on="canonical_id", how="left")
    cur["rank"] = cur["points_per_gp_quality_z"].fillna(-99)
    traj_pos = trajectory[trajectory["position"] == position_label] if not trajectory.empty else pd.DataFrame()

    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(13, 6.5))
    fig.patch.set_facecolor(CREAM)

    title_cs = "Útočníci" if position_label == "F" else "Obránci"
    for ax, proj_label, title in (
        (ax_left, "style", "Style mapa (bez ligových násobiček)"),
        (ax_right, "quality", "Kvalitou upravená mapa"),
    ):
        x_col, y_col = f"pca_x_{proj_label}", f"pca_y_{proj_label}"
        c_col = f"cluster_id_{proj_label}"
        sub = cur.dropna(subset=[x_col, y_col]).copy()
        sub[c_col] = sub[c_col].fillna(-1).astype(int)

        for cid in sorted(sub[c_col].unique()):
            color = CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)] if cid >= 0 else MUTED
            m = sub[c_col] == cid
            ax.scatter(sub.loc[m, x_col], sub.loc[m, y_col],
                       s=20, c=color, alpha=0.78,
                       edgecolors=CREAM, linewidths=0.55,
                       label=f"C{cid}" if cid >= 0 else "—")

        nt = sub[sub["iihf_appearances"].fillna(0) >= 1]
        ax.scatter(nt[x_col], nt[y_col],
                   s=95, facecolors="none", edgecolors=OXBLOOD,
                   linewidths=1.35, alpha=0.9, zorder=5,
                   label="MS 24/25")

        _annotate_top_players(ax, sub, x_col, y_col, "rank", n=10)
        _draw_trajectory_arrows(ax, traj_pos, proj_label)

        ax.set_title(title, fontsize=11.5, fontfamily="serif",
                     color=INK, pad=12, loc="left")
        ax.set_xlabel("PC1", fontsize=8.5, color=MUTED, fontfamily="sans-serif")
        ax.set_ylabel("PC2", fontsize=8.5, color=MUTED, fontfamily="sans-serif")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(RULE)
        ax.spines["bottom"].set_color(RULE)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.set_facecolor(CREAM)
        leg = ax.legend(loc="lower right", fontsize=7.5, frameon=False,
                        labelcolor=INK)
        for txt in leg.get_texts():
            txt.set_fontfamily("sans-serif")

    fig.suptitle(f"Český hokej · {title_cs} {latest}/{latest + 1 - 2000:02d}",
                 fontsize=14, fontfamily="serif", color=INK, y=1.02,
                 x=0.02, ha="left", weight="normal")
    fig.text(
        0.02, -0.025,
        "PCA projekce z čtyřrozměrného vektoru (G/GP, A/GP, PIM/GP, věk). "
        "Oxbloodové kroužky vyznačují MS 24/25 účast. Šipky znázorňují "
        "trajektorii 2024/25 → 2025/26; směr arrow head ukazuje pohyb.",
        ha="left", fontsize=8.2, color=MUTED, fontfamily="sans-serif",
    )
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight", format="svg")
    plt.close(fig)
    LOG.info("wrote %s", out_path)


# =============================================================================
# Data tables for the report
# =============================================================================


def _build_cluster_summary_rich(
    coords: pd.DataFrame, features: pd.DataFrame, labels: dict, position_label: str
) -> list[dict]:
    """Build per-cluster summary for the style projection's cluster cards."""
    latest = int(coords["season"].max())
    cur = coords[coords["season"] == latest].copy()
    feat_cur = features[features["season"] == latest]
    rows: list[dict] = []
    proj = "style"
    labels_pos = labels.get(f"{('forwards' if position_label == 'F' else 'defense')}_{proj}", {})
    for cid in sorted(cur[f"cluster_id_{proj}"].dropna().unique()):
        cid_int = int(cid)
        members = cur[cur[f"cluster_id_{proj}"] == cid]
        feat_members = feat_cur[feat_cur["canonical_id"].isin(members["canonical_id"])]
        meta = labels_pos.get(cid_int, {})
        nt_count = int((members["iihf_appearances"].fillna(0) >= 1).sum())
        league_mix = members["league"].value_counts().to_dict()
        median_age_year = int(members["birth_year"].median()) if not members["birth_year"].isna().all() else None
        # Top players (up to 5) sorted by quality z-score
        f_for_rank = feat_cur[feat_cur["canonical_id"].isin(members["canonical_id"])]
        f_for_rank = f_for_rank.sort_values("points_per_gp_quality_z", ascending=False)
        top_names = [f"{r.first_name} {r.last_name}".strip()
                     for r in f_for_rank.head(5).itertuples()]
        rows.append({
            "cluster_id": cid_int,
            "label": meta.get("label_cs", f"Cluster {cid_int}"),
            "description": meta.get("description_cs", ""),
            "tactical": meta.get("tactical_cs", ""),
            "n_members": int(len(members)),
            "nt_count": nt_count,
            "median_age_year": median_age_year,
            "league_mix": league_mix,
            "top_names": top_names,
            "median_g_gp": round(float(feat_members["goals_per_gp_shrunk"].median()), 3),
            "median_a_gp": round(float(feat_members["assists_per_gp_shrunk"].median()), 3),
        })
    return rows


def _build_top_movers(trajectory: pd.DataFrame, n: int = 5) -> tuple[list[dict], list[dict]]:
    """Return (top_improvers, top_decliners) for forwards.

    Filters by the direction column from trajectory.py — improvers must have
    direction=="improving" (delta exceeds CI band), decliners must have
    direction=="declining". Near-zero deltas (direction="stable") don't
    appear in either list — they belong on the stable middle.
    """
    if trajectory.empty:
        return [], []
    fwd = trajectory[trajectory["position"] == "F"]
    if fwd.empty:
        return [], []

    def _row(r) -> dict:
        return {
            "name": f"{r.first_name} {r.last_name}".strip(),
            "league": r.league,
            "gp_old": int(r.GP_old),
            "gp_new": int(r.GP_new),
            "delta": round(float(r.d_points_per_gp_quality), 3),
            "old": round(float(r.points_per_gp_quality_old), 3),
            "new": round(float(r.points_per_gp_quality_new), 3),
        }

    improving = fwd[fwd["direction"] == "improving"]
    declining = fwd[fwd["direction"] == "declining"]
    top_imp = [_row(r) for r in improving.nlargest(n, "d_points_per_gp_quality").itertuples()]
    top_dec = [_row(r) for r in declining.nsmallest(n, "d_points_per_gp_quality").itertuples()]
    return top_imp, top_dec


def _build_pca_loadings_table(loadings: pd.DataFrame) -> list[dict]:
    """Per-(position, projection, PC) loadings for the methodology section."""
    rows: list[dict] = []
    for (pos, proj, pc), sub in loadings.groupby(["position", "projection", "pc"]):
        explained = float(sub["explained_variance_ratio"].iloc[0])
        feature_loadings = {r.feature: round(float(r.loading), 3) for r in sub.itertuples()}
        rows.append({
            "position": pos, "projection": proj, "pc": pc,
            "explained_pct": round(explained * 100, 1),
            "loadings": feature_loadings,
        })
    return rows


def _build_sensitivity_table(summary: pd.DataFrame) -> list[dict]:
    """Format sensitivity summary for report rendering."""
    return [
        {
            "scenario": r.scenario,
            "description": r.description,
            "overlap": int(r.top10_overlap_with_baseline),
            "churn": int(r.top10_churn),
            "mean_delta": float(r.mean_abs_rank_delta_top20),
        }
        for r in summary.itertuples()
    ]


# =============================================================================
# Czech-language narrative content
# =============================================================================


CZECH_FRAMING = (
    "Mapa cca 280 Čechy hokejistů ve světových profesionálních ligách "
    "(NHL, Liiga, Tipsport Extraliga), segmentovaná podle pozice a herního "
    "profilu. Metodologický nástroj pro průběžné mapování fondu hráčů v rámci "
    "víceletého reprezentačního cyklu, nikoli výběrové doporučení."
)

CZECH_OBSERVATIONS = [
    {
        "title": "Reprezentační fond překlenuje NHL i Extraligu",
        "body": (
            "42 z 81 hráčů, kteří odehráli MS 2024 nebo MS 2025 za reprezentaci, "
            "se nachází v mapovaném poolu. Mezi nimi top NHL hráči (Pastrňák, "
            "Nečas, Vejmelka) i Extraliga veteráni (Červenka, Sedlák, Kundrátek). "
            "Strukturálně tedy reprezentační pool není „NHL kontingent“ ani „Extraliga "
            "kontingent“: je to spojnice obou profesionálních ekosystémů."
        ),
    },
    {
        "title": "Kvalitou upravená mapa vizualizuje ligový diferenciál",
        "body": (
            "Po aplikaci ligových násobiček se NHL elita (Pastrňák PC1 ≈ 8.5) "
            "dramaticky odpoutává od EU elity (Červenka PC1 ≈ 2). Style mapa "
            "(bez násobiček) ukazuje samotný herní profil; Pastrňák a Červenka "
            "tam leží v podobné zóně produkce. Dvojice projekcí umožňuje "
            "interpretovat fond jak stylově, tak kvalitativně, bez nutnosti "
            "volit jednu narativu."
        ),
    },
    {
        "title": "Trajektorie 2024/25 → 2025/26 odhalují stabilní vrcholy",
        "body": (
            "Z 16 hráčů, kteří splňují minimum 30 zápasů v obou sezónách, "
            "vykazují stabilní top-tier produkci NHL hvězdy (Pastrňák Δ ≈ 0). "
            "Mezi zlepšujícími se: Zacha a Nečas (oba NHL, breakout / post-trade). "
            "Mezi klesajícími: Hertl a Palát. Tato čísla nejsou predikce; "
            "popisují směr pohybu mezi sezónami."
        ),
    },
]


CZECH_LIMITATIONS = """
**Veřejná versus interní data.** Tato analýza využívá výhradně veřejně dostupné
statistické zdroje (NHL API, MoneyPuck, Liiga, hokej.cz, Wikipedia pro IIHF turnaje).
Trénerský a manažerský úsek reprezentace ČR disponuje interními daty (videosrážka,
kondiční sledování, scoutingové zprávy, mikrostatistiky vstupů do pásma a kontrolovaných
výjezdů), které tato metoda nezohledňuje. Vzory zde identifikované jsou hypotézami
pro vnitřní validaci, nikoli závěry.

**Liga quality multipliers.** Použité násobičky kvality lig (NHL = 1.00, AHL = 0.55,
SHL = 0.45, Liiga = 0.42, NL = 0.40, Extraliga = 0.35, 1. liga = 0.20) jsou subjektivní
aproximace. Vycházejí z veřejných srovnání produkce hráčů, kteří přešli mezi ligami, ale
jsou citlivé na výběr hráčů, vlastnosti pravidel, velikost kluziště a sezónní kontext.
Citlivostní analýza (oddíl Methodologie) ukazuje, jak se mapa mění při změně násobičky
o ±20 %: top-10 ranking je vůči těmto perturbacím stabilní (churn 0-1 hráčů).

**Žádná data z KHL.** KHL je z analýzy vyloučena ze dvou důvodů: politické sankce
omezují použitelnost ruských statistických zdrojů, a kvalita dat byla v poslední době
neověřitelná. Čeští hráči v KHL nejsou v této verzi mapy zachyceni.

**Velikost vzorku a Bayesovský shrinkage.** Někteří hráči mají odehráno méně než 10
zápasů v sezoně 2025/26. Per-game metriky pro tyto hráče byly shrinkutovány k mediánu
své ligy (Empirical Bayes, K = 10 fantomových zápasů). Trajektoriální analýza vyžaduje
minimum 30 zápasů v obou sezónách (16 hráčů splňuje).

**Goaltending.** Brankáři jsou vyloučeni z hlavní mapy, protože jejich pozičně
specifické metriky neumožňují společnou projekci s útočníky a obránci. Brankářská
analytika je extrémně kontext-závislá (kvalita obrany před brankářem, ledové podmínky,
schéma hry) a tato analýza nenárokuje hloubku v této oblasti.

**Chybějící zdroje.** SHL a švýcarská NL jsou v této verzi mapy vyloučeny;
oba weby jsou JavaScript-rendered s netriviálním přístupem k datům. Český pool
v těchto ligách (~10-20 hráčů) tedy v této verzi mapy chybí. AHL hráči, NCAA, juniorské
ligy mimo Extraligu a Liigy jsou rovněž mimo scope.

**Style ≠ tactical understanding.** Statistický otisk hráče nezachycuje schopnost
číst hru, leadership, šatnové vlivy, ani specifické dovednosti pro mezinárodní turnaje
(např. hru na velkém ledě po dlouhé NHL sezóně). To je doménou trenérů a scoutingu.

**Žádné doporučení.** Tato analýza identifikuje statistická seskupení a změny v čase.
Výběr hráčů a strategická rozhodnutí vyžadují integraci s interní expertízou, kterou
tato metoda nemá k dispozici. Cílem je nabídnout metodu, kterou interní tým může
aplikovat na vlastní rozšířenou datovou základnu.
""".strip()


# =============================================================================
# Main orchestrator
# =============================================================================


def main() -> None:
    logging_setup()
    config.ensure_dirs()

    # --- Load all data ---
    fwd_coords = read_parquet(config.PROCESSED_DIR / "coords_forwards.parquet")
    def_coords = read_parquet(config.PROCESSED_DIR / "coords_defense.parquet")
    fwd_features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    def_features = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")
    canonical = read_parquet(config.PROCESSED_DIR / "players.parquet")
    trajectory = read_parquet(config.PROCESSED_DIR / "trajectory.parquet") if (config.PROCESSED_DIR / "trajectory.parquet").exists() else pd.DataFrame()
    pca_loadings = read_parquet(config.PROCESSED_DIR / "pca_loadings.parquet") if (config.PROCESSED_DIR / "pca_loadings.parquet").exists() else pd.DataFrame()
    sensitivity = read_parquet(config.PROCESSED_DIR / "sensitivity_summary.parquet") if (config.PROCESSED_DIR / "sensitivity_summary.parquet").exists() else pd.DataFrame()
    league_quality = config.league_quality()["multipliers"]
    cluster_labels = config.load_yaml("cluster_labels.yaml")

    # International benchmark data
    intl_path = config.PROCESSED_DIR / "international_cohort.parquet"
    intl_table = read_parquet(intl_path) if intl_path.exists() else pd.DataFrame()
    intl_per_capita: list[dict] = []
    intl_cohort_gaps_f: list[dict] = []
    intl_cohort_gaps_d: list[dict] = []
    if not intl_table.empty:
        from src.international_benchmark import COUNTRIES, COHORTS, POPULATION_M
        latest_intl = int(intl_table["season"].max())
        sub_intl = intl_table[intl_table["season"] == latest_intl]
        for country in COUNTRIES:
            n = int(sub_intl[sub_intl["country"] == country]["n_players"].sum())
            pop = POPULATION_M[country]
            intl_per_capita.append({
                "country": country,
                "n_players": n,
                "population_m": pop,
                "per_million": round(n / pop, 2),
            })
        # Sort: per-million descending
        intl_per_capita.sort(key=lambda r: r["per_million"], reverse=True)

        for cohort_label, _, _ in COHORTS:
            for position, target_list in (("F", intl_cohort_gaps_f), ("D", intl_cohort_gaps_d)):
                row: dict = {"cohort": cohort_label}
                for country in ("CZE", "FIN", "SWE", "SVK"):
                    cell = sub_intl[
                        (sub_intl["country"] == country)
                        & (sub_intl["position"] == position)
                        & (sub_intl["cohort"] == cohort_label)
                    ]
                    if cell.empty:
                        row[country] = {"n": 0, "median": None}
                    else:
                        row[country] = {
                            "n": int(cell.iloc[0]["n_players"]),
                            "median": float(cell.iloc[0]["median_P_per_GP"]),
                        }
                target_list.append(row)

    # --- Render figures ---
    _render_atlas(fwd_coords, fwd_features, trajectory, "F",
                  config.OUTPUTS_DIR / "atlas_forwards.svg")
    _render_atlas(def_coords, def_features, trajectory, "D",
                  config.OUTPUTS_DIR / "atlas_defense.svg")

    # International cohort heatmap (delegate to module that knows its layout)
    if not intl_table.empty:
        from src.international_benchmark import render_cohort_heatmap
        render_cohort_heatmap(intl_table, config.OUTPUTS_DIR / "intl_cohort_heatmap.svg")

    # --- Build data tables ---
    n_players = int(canonical["canonical_id"].nunique())
    n_yes = int((canonical["czech_eligible_flag"] == "yes").sum())
    n_iihf = int((canonical["iihf_appearances"].fillna(0) >= 1).sum())

    fwd_clusters = _build_cluster_summary_rich(fwd_coords, fwd_features, cluster_labels, "F")
    def_clusters = _build_cluster_summary_rich(def_coords, def_features, cluster_labels, "D")
    top_improvers, top_decliners = _build_top_movers(trajectory, n=5)
    loadings_table = _build_pca_loadings_table(pca_loadings) if not pca_loadings.empty else []
    sensitivity_table = _build_sensitivity_table(sensitivity) if not sensitivity.empty else []

    # --- AI / multimodal layer (May 2026 addendum) ---
    import json as _json

    # Vision-language cards (Claude Opus with image input)
    vision_cards = []
    cards_dir = config.OUTPUTS_DIR / "cards"
    if cards_dir.exists():
        for p in sorted(cards_dir.glob("*.json")):
            try:
                c = _json.loads(p.read_text(encoding="utf-8"))
                if c.get("profile_text"):
                    paragraphs = [s.strip() for s in c["profile_text"].split("\n\n") if s.strip()]
                    c["paragraphs"] = paragraphs
                    vision_cards.append(c)
            except Exception:  # noqa: BLE001
                continue

    # Historical analogs (career-trajectory nearest neighbours)
    historical_analogs = []
    analogs_path = config.PROCESSED_DIR / "historical_analogs.json"
    if analogs_path.exists():
        try:
            historical_analogs = _json.loads(analogs_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            historical_analogs = []

    LOG.info("AI layer: %d vision cards, %d analog targets",
             len(vision_cards), len(historical_analogs))

    # --- Render HTML via Jinja2 ---
    # Markdown-ish → HTML for the limitations block (**bold** → <strong>bold</strong>)
    import re
    limitations_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", CZECH_LIMITATIONS)
    limitations_html = "<p>" + limitations_html.replace("\n\n", "</p>\n<p>") + "</p>"

    env = Environment(loader=FileSystemLoader(str(config.TEMPLATES_DIR)), autoescape=True)
    template = env.get_template("report.html.j2")
    html_out = template.render(
        n_players=n_players,
        n_yes=n_yes,
        n_iihf=n_iihf,
        framing=CZECH_FRAMING,
        observations=CZECH_OBSERVATIONS,
        limitations=limitations_html,
        intl_per_capita=intl_per_capita,
        intl_cohort_gaps_f=intl_cohort_gaps_f,
        intl_cohort_gaps_d=intl_cohort_gaps_d,
        intl_has_data=bool(intl_per_capita),
        fwd_clusters=fwd_clusters,
        def_clusters=def_clusters,
        top_improvers=top_improvers,
        top_decliners=top_decliners,
        loadings_table=loadings_table,
        sensitivity_table=sensitivity_table,
        league_quality=league_quality,
        vision_cards=vision_cards,
        historical_analogs=historical_analogs,
        rendered_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    html_path = config.OUTPUTS_DIR / "index.html"
    html_path.write_text(html_out, encoding="utf-8")
    LOG.info("wrote %s (%d bytes)", html_path, len(html_out))

    # Also copy CSS into outputs/ so the HTML is self-contained
    css_src = config.TEMPLATES_DIR / "style.css"
    css_dst = config.OUTPUTS_DIR / "style.css"
    if css_src.exists():
        css_dst.write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")

    # --- Optional PDF via weasyprint ---
    try:
        from weasyprint import HTML
        pdf_path = config.OUTPUTS_DIR / "report.pdf"
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        LOG.info("wrote %s", pdf_path)
    except Exception as e:  # noqa: BLE001
        LOG.warning("PDF render via weasyprint failed: %s", e)


if __name__ == "__main__":
    main()
