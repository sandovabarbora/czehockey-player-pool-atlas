"""LLM scouting brief generator — Claude Opus 4.7 over structured Atlas data.

Per locked decision this session (LLM-over-structured-data, not video AI):
  - Input: canonical player table + features + coords + trajectory + IIHF
  - Pipeline: per-player context block → Claude → 1-page Czech scouting brief
  - Output: outputs/briefs/{player_slug}.md per Czech-confirmed player

Methodology rigor preserved:
  - System prompt enforces stance discipline (no recommendations, no
    predictions, no selection language). Quotes are forbidden if they
    cross the brief's locked critique-pass red lines.
  - All numbers are pre-computed and supplied in the context block;
    the LLM does NOT compute statistics, only describes them.
  - Comparable players are pre-computed from the corpus (nearest in same
    cluster by feature distance); the LLM does not invent comparisons.

API design (per claude-api skill best practices):
  - Model: claude-opus-4-7 (latest, best Czech writing quality).
  - Adaptive thinking enabled; effort=high (matters more on 4.7).
  - Prompt caching on the stable methodology+style+format prompt
    (~3K tokens); per-player data goes after the cache breakpoint
    so each player after the first reads from cache (~90% cost cut).
  - Cost estimate (per player): ~3K cached read + ~500 uncached user +
    ~1500 output. Per-player marginal cost ~$0.04. Full pool (78 Czech)
    ~$3-5 total for a one-time run.
"""

from __future__ import annotations

import logging
import os
import re
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet

LOG = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
BRIEFS_DIR = config.OUTPUTS_DIR / "briefs"


# =============================================================================
# System prompt — CACHED (~2K tokens of stable methodology + style guide)
# =============================================================================

SYSTEM_PROMPT_STABLE = """\
Jste statistický poradce pro hokejovou analytiku, který píše krátké česky-psané \
profily hráčů na základě integrovaného datového setu Atlas (Český hokej — Atlas \
fondu hráčů). Vaše role je popisovat, ne doporučovat.

## METODOLOGIE (kontext pro vaše interpretace)

**Datový set:**
- 385 kanonických hráčů, integrovaných napříč NHL, Liiga, Tipsport Extraliga
- 78 potvrzeně Czech-eligible (birth_country = CZE nebo IIHF účast MS 2024/2025)
- Per-game metriky: G/GP, A/GP, P/GP, shots/GP, PIM/GP
- Bayesovský shrinkage (K=10 fantomových zápasů) pro hráče s malým vzorkem

**Dvě projekce (PCA z 4D feature vektoru):**
- Style mapa: bez ligových násobiček — hráči podle herního profilu nezávisle na lize
- Kvalitou upravená mapa: s násobičkami (NHL=1.00, Liiga=0.42, Extraliga=0.35)
- PC1 = produkční osa (G/A loadings ~0.66); PC2 = fyzicalita + věk

**Clustery (K vybraný silhouette skórem):**
- Forwards style K=4: Top-six skórující / Mladí prospekti / Fyzičtí role-players / Veteránští two-way
- Forwards quality K=5
- Defense style K=6, quality K=5

**Sensitivity:** ±20% perturbace ligových násobiček způsobuje 0-1 hráčů churn v top-10. NHL elita je v top čtyřce ve všech scénářích.

## STANCE DISCIPLINE (závazná pravidla)

ZAKÁZÁNO:
- Výběrová doporučení ("hráč X by měl být v sestavě", "doporučuji vyřadit Y")
- Predikce konkrétních hráčů ("hráč Z bude příští rok v cluster W")
- Komentář na trenérská rozhodnutí, sestavení lajn, special teams personnel
- Hodnocení brankářů nad rámec agregovaných statistik
- Komentář na výsledek MS 2025 nebo specifické turnaje
- Slovo "kandidát" (implikuje výběr) — používejte "profil odpovídající"

POVOLENO (a vyžadováno):
- Popis: "hráč X má profil C0, P/GP 0.85 quality-adjusted"
- Strukturální observace: "hráči v jeho clusteru typicky plateau-ují kolem 30 let"
- Trajektorie: "Δ +0.20 P/GP mezi 2024-25 a 2025-26" (pouze pokud GP ≥30 obě sezóny)
- Honest uncertainty: "po Bayesovském shrinkage s K=10 prior, true talent estimate je..."
- Srovnání: "podobný profil k hráčům X, Y, Z v rámci current corpus"

## OUTPUT FORMAT

Vraťte jen markdown brief, žádné meta-komentáře. Struktura (cca 300-400 slov):

```markdown
# {Jméno} ({pozice}, {ročník})

## Statistický profil
[2-3 věty: cluster, projekce, top metriky. Použijte čísla z kontextu.]

## Trajektorie
[Pokud má multi-season data: 2-3 věty o Δ. Pokud ne: "Trajektorie nedostupná —
single-season data". Nemyslete predikci.]

## Reprezentační kontext
[1-2 věty: IIHF účast, pozice v Czech NT pool.]

## Srovnatelné profily (in-corpus)
[1-2 věty: 3 nejbližší hráči v stejném clusteru. Jen popis, žádné hodnocení.]

## Caveats
[1-2 věty: známé limitace dat pro tohoto hráče — small sample, missing shots,
nemá IIHF flag atd.]
```

Píšete pro datově gramotného hokejového analytika (Jan Morkes, Český hokej). \
Nezaplňujte vatou; každá věta musí přidat informaci. Slovník: kombinujte české \
hokejové termíny ("útočník", "obránce", "reprezentace") s anglickými statistickými \
("P/GP", "cluster", "shrinkage") — to je natural jazyk analytického prostředí.
"""


# =============================================================================
# Per-player context block — NOT cached (varies per request)
# =============================================================================


def find_comparable_players(
    player_canonical_id: str,
    features: pd.DataFrame,
    coords: pd.DataFrame,
    n: int = 3,
) -> list[dict]:
    """Find n nearest players in same cluster (style projection) by feature distance.

    Uses the 4D feature vector (G/GP, A/GP, PIM/GP, birth_year) z-scored within
    position to compute Euclidean distance. Returns at most n; may return fewer
    if cluster is small.
    """
    feat_cols = [
        "goals_per_gp_shrunk_z",
        "assists_per_gp_shrunk_z",
        "pim_per_gp_shrunk_z",
    ]
    latest = int(features["season"].max())
    cur = features[features["season"] == latest].copy()

    target_rows = coords[
        (coords["canonical_id"] == player_canonical_id)
        & (coords["season"] == latest)
    ]
    if target_rows.empty:
        return []
    target_cluster = target_rows.iloc[0].get("cluster_id_style")
    if pd.isna(target_cluster):
        return []

    cluster_members = coords[
        (coords["season"] == latest)
        & (coords["cluster_id_style"] == target_cluster)
        & (coords["canonical_id"] != player_canonical_id)
    ]["canonical_id"].tolist()

    target_features = cur[cur["canonical_id"] == player_canonical_id]
    if target_features.empty or not all(c in cur.columns for c in feat_cols):
        return []
    target_vec = target_features[feat_cols].astype(float).iloc[0].values

    distances: list[tuple[str, float]] = []
    for cid in cluster_members:
        cand = cur[cur["canonical_id"] == cid]
        if cand.empty or cand[feat_cols].isna().any(axis=None):
            continue
        cand_vec = cand[feat_cols].astype(float).iloc[0].values
        d = float(np.linalg.norm(target_vec - cand_vec))
        distances.append((cid, d))
    distances.sort(key=lambda t: t[1])

    out: list[dict] = []
    for cid, d in distances[:n]:
        row = cur[cur["canonical_id"] == cid].iloc[0]
        out.append({
            "name": f"{row.get('first_name','')} {row.get('last_name','')}".strip(),
            "league": row.get("league"),
            "P_per_GP_shrunk": float(row.get("points_per_gp_shrunk", float("nan"))),
            "P_per_GP_quality": float(row.get("points_per_gp_quality", float("nan"))),
            "distance": round(d, 3),
        })
    return out


def assemble_player_context(
    player_canonical_id: str,
    canonical: pd.DataFrame,
    features: pd.DataFrame,
    coords: pd.DataFrame,
    trajectory: pd.DataFrame,
    cluster_labels: dict,
) -> str:
    """Build the per-player context block for the LLM."""
    p = canonical[canonical["canonical_id"] == player_canonical_id].iloc[0]
    latest = int(features["season"].max())
    feat_row = features[
        (features["canonical_id"] == player_canonical_id)
        & (features["season"] == latest)
    ]
    coord_row = coords[
        (coords["canonical_id"] == player_canonical_id)
        & (coords["season"] == latest)
    ]

    if feat_row.empty:
        return ""  # no current-season data; skip
    f = feat_row.iloc[0]
    c = coord_row.iloc[0] if not coord_row.empty else None

    # Trajectory (if present)
    traj_block = "Trajektorie: nedostupná (jediná dostupná sezóna)."
    if not trajectory.empty:
        tr = trajectory[trajectory["canonical_id"] == player_canonical_id]
        if not tr.empty:
            t = tr.iloc[0]
            traj_block = (
                f"Trajektorie {int(t['season_old'])}-{int(t['season_old'])+1} → "
                f"{int(t['season_new'])}-{int(t['season_new'])+1}: "
                f"P/GP {float(t['points_per_gp_quality_old']):.3f} → "
                f"{float(t['points_per_gp_quality_new']):.3f} "
                f"(Δ {float(t['d_points_per_gp_quality']):+.3f}, "
                f"GP {int(t['GP_old'])} → {int(t['GP_new'])}, "
                f"směr: {t['direction']})."
            )

    # Cluster labels
    pos_key = "forwards" if p["position_normalized"] == "F" else "defense"
    style_cid = int(c["cluster_id_style"]) if c is not None and pd.notna(c.get("cluster_id_style")) else None
    quality_cid = int(c["cluster_id_quality"]) if c is not None and pd.notna(c.get("cluster_id_quality")) else None
    style_label = cluster_labels.get(f"{pos_key}_style", {}).get(style_cid, {}).get("label_cs") if style_cid is not None else None
    quality_label = cluster_labels.get(f"{pos_key}_quality", {}).get(quality_cid, {}).get("label_cs") if quality_cid is not None else None

    iihf_tournaments_raw = p.get("iihf_tournaments")
    if iihf_tournaments_raw is None or (hasattr(iihf_tournaments_raw, "__len__") and len(iihf_tournaments_raw) == 0):
        iihf_list_str = ""
    else:
        iihf_list_str = " (" + ", ".join(list(iihf_tournaments_raw)) + ")"
    iihf_block = f"IIHF účast: {int(p.get('iihf_appearances', 0))} turnaj(e/ů){iihf_list_str}"

    comparables = find_comparable_players(player_canonical_id, features, coords, n=3)
    comp_block = (
        "\n".join(
            f"- {c['name']} ({c['league']}, P/GP quality {c['P_per_GP_quality']:.3f}, distance {c['distance']})"
            for c in comparables
        )
        if comparables
        else "(žádní srovnatelní hráči v stejném clusteru s computable feature vektorem)"
    )

    return textwrap.dedent(f"""\
        # Hráč: {p['first_name']} {p['last_name']}

        ## Identita
        - Ročník: {int(p['birth_year']) if pd.notna(p.get('birth_year')) else 'neznámý'}
        - Pozice: {p['position_normalized']}
        - Eligibility flag: {p.get('czech_eligible_flag', '?')}
        - Zdroje dat: {p.get('sources', [])}
        - Aktuální liga (season {latest}-{latest+1}): {f.get('league')}
        - {iihf_block}

        ## Statistický profil (sezona {latest}-{latest+1})
        - GP: {int(f['GP'])}
        - Cluster style: C{style_cid} ({style_label or 'unlabeled'})
        - Cluster quality: C{quality_cid} ({quality_label or 'unlabeled'})
        - PCA souřadnice style: ({float(c['pca_x_style']):.2f}, {float(c['pca_y_style']):.2f}) [pokud dostupné]
        - PCA souřadnice quality: ({float(c['pca_x_quality']):.2f}, {float(c['pca_y_quality']):.2f}) [pokud dostupné]

        ## Per-game metriky (raw → shrunk → quality-adjusted)
        - G/GP: raw {float(f.get('goals_per_gp', 0)):.3f} → shrunk {float(f.get('goals_per_gp_shrunk', 0)):.3f} → quality {float(f.get('goals_per_gp_quality', 0)):.3f}
        - A/GP: raw {float(f.get('assists_per_gp', 0)):.3f} → shrunk {float(f.get('assists_per_gp_shrunk', 0)):.3f} → quality {float(f.get('assists_per_gp_quality', 0)):.3f}
        - P/GP: raw {float(f.get('points_per_gp', 0)):.3f} → shrunk {float(f.get('points_per_gp_shrunk', 0)):.3f} → quality {float(f.get('points_per_gp_quality', 0)):.3f}
        - PIM/GP: raw {float(f.get('pim_per_gp', 0)):.3f} → shrunk {float(f.get('pim_per_gp_shrunk', 0)):.3f}
        - Cross-league quality z-score (P/GP): {float(f.get('points_per_gp_quality_z', 0)):+.3f}

        ## Trajektorie
        {traj_block}

        ## Srovnatelné profily (3 nejbližší v stejném style clusteru)
        {comp_block}

        ---

        Napište scouting brief pro tohoto hráče podle output formátu specifikovaného v system prompt.
    """)


# =============================================================================
# Main generation loop
# =============================================================================


def _slugify(name: str) -> str:
    import unicodedata
    nfd = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in nfd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")


def generate_brief(
    client: Any,
    player_canonical_id: str,
    canonical: pd.DataFrame,
    features: pd.DataFrame,
    coords: pd.DataFrame,
    trajectory: pd.DataFrame,
    cluster_labels: dict,
) -> tuple[str, dict]:
    """Generate a single Czech scouting brief. Returns (markdown_text, usage_dict)."""
    context = assemble_player_context(
        player_canonical_id, canonical, features, coords, trajectory, cluster_labels
    )
    if not context:
        return "", {}

    response = client.messages.create(
        model=MODEL,
        max_tokens=2500,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT_STABLE,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": context}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    usage = {
        "input_tokens": response.usage.input_tokens,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return text, usage


def main(limit: int | None = None) -> None:
    """Generate briefs for confirmed Czech players.

    Args:
        limit: if set, only generate first N briefs (use for cost-bounded test runs).
    """
    logging_setup()
    config.ensure_dirs()
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Export it: "
            "export ANTHROPIC_API_KEY=sk-ant-... "
            "(or add to .env if you use a .env loader)"
        )

    import anthropic
    client = anthropic.Anthropic()

    canonical = read_parquet(config.PROCESSED_DIR / "players.parquet")
    fwd_features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    def_features = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")
    features = pd.concat([fwd_features, def_features], ignore_index=True)
    fwd_coords = read_parquet(config.PROCESSED_DIR / "coords_forwards.parquet")
    def_coords = read_parquet(config.PROCESSED_DIR / "coords_defense.parquet")
    coords = pd.concat([fwd_coords, def_coords], ignore_index=True)
    trajectory = (
        read_parquet(config.PROCESSED_DIR / "trajectory.parquet")
        if (config.PROCESSED_DIR / "trajectory.parquet").exists()
        else pd.DataFrame()
    )
    cluster_labels = config.load_yaml("cluster_labels.yaml")

    # Target: confirmed Czech players, ordered by quality z-score for "top down" first
    cz = canonical[canonical["czech_eligible_flag"] == "yes"].copy()
    latest_season = int(features["season"].max())
    feat_latest = features[features["season"] == latest_season][[
        "canonical_id", "points_per_gp_quality_z"
    ]]
    cz = cz.merge(feat_latest, on="canonical_id", how="left")
    cz = cz.sort_values("points_per_gp_quality_z", ascending=False, na_position="last")

    targets = cz["canonical_id"].tolist()
    if limit is not None:
        targets = targets[:limit]
    LOG.info("generating briefs for %d players", len(targets))

    totals = {
        "input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "output_tokens": 0,
    }
    for i, pid in enumerate(targets, 1):
        player_row = canonical[canonical["canonical_id"] == pid].iloc[0]
        name = f"{player_row['first_name']} {player_row['last_name']}"
        slug = _slugify(name) or pid
        out_path = BRIEFS_DIR / f"{slug}.md"
        if out_path.exists():
            LOG.info("[%d/%d] cached: %s", i, len(targets), out_path.name)
            continue

        LOG.info("[%d/%d] generating: %s", i, len(targets), name)
        try:
            text, usage = generate_brief(
                client, pid, canonical, features, coords, trajectory, cluster_labels
            )
        except Exception as e:  # noqa: BLE001
            LOG.warning("  failed: %s", e)
            continue
        if not text:
            LOG.warning("  empty output, skipping")
            continue
        out_path.write_text(text, encoding="utf-8")
        for k in totals:
            totals[k] += usage.get(k, 0)
        LOG.info(
            "  wrote %s (%d chars). usage: in=%d cache_write=%d cache_read=%d out=%d",
            out_path.name, len(text),
            usage["input_tokens"], usage["cache_creation_input_tokens"],
            usage["cache_read_input_tokens"], usage["output_tokens"],
        )

    # Cost estimate (Opus 4.7 pricing: $5/1M in, $25/1M out, cache read ~$0.50/1M)
    in_cost = totals["input_tokens"] * 5e-6
    cache_write_cost = totals["cache_creation_input_tokens"] * 6.25e-6  # 1.25x write
    cache_read_cost = totals["cache_read_input_tokens"] * 0.5e-6  # ~0.1x
    out_cost = totals["output_tokens"] * 25e-6
    total_cost = in_cost + cache_write_cost + cache_read_cost + out_cost
    LOG.info("=== summary ===")
    LOG.info("totals: %s", totals)
    LOG.info(
        "estimated cost: in=$%.4f cache_write=$%.4f cache_read=$%.4f out=$%.4f = $%.3f",
        in_cost, cache_write_cost, cache_read_cost, out_cost, total_cost,
    )


if __name__ == "__main__":
    import sys
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit=lim)
