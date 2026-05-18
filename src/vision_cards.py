"""Vision-language player cards — Claude Opus 4.7 with image input.

Per session decision (multimodal addendum, May 2026):
    Combines NHL action photos with structured stats to generate Czech-language
    analytical cards. The novelty over llm_scout.py is the image modality:
    Claude sees the player in action and ties visible attributes (stance,
    body type, release point, edge work) to the statistical profile.

Federation context: scouting eye-test and stats are typically processed
separately. This pipeline fuses the two at scale, treating the photo as
an additional structured input rather than decoration.

Stance discipline (inherited from PRODUCT.md):
    - Descriptive, never prescriptive ("má kompaktní release a stats konzistentní
      s wrist-shot scoringem", NOT "měl by být v top-9")
    - No predictions, no recommendations
    - Quantified uncertainty preserved (acknowledge what photo alone can't tell)

API design:
    - Model: claude-opus-4-7 (best Czech writing, vision-capable)
    - Adaptive thinking, effort=high
    - Prompt caching on the stable system prompt (~3K tokens)
    - Photos fetched as URL references (NHL CDN, public mug shots)
    - Output cached to outputs/cards/{slug}.json — re-run safe

Cost (per card): ~3K cached read + ~1K image tokens + ~1K output ≈ $0.04
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from src import config
from src.logging_setup import setup as logging_setup
from src.utils import read_parquet

load_dotenv(config.ROOT_DIR / ".env")

LOG = logging.getLogger(__name__)

MODEL = "claude-opus-4-7"
CARDS_DIR = config.OUTPUTS_DIR / "cards"

# Sample of Czech NHL players to profile. Selected to span cluster archetypes:
# elite forwards (Pastrnak, Necas), young prospects (Kulich), defensemen
# (Hronek, Gudas), and a Liiga/Extraliga representative if data permits.
TARGET_PLAYERS = [
    ("8477956", "david-pastrnak", "David Pastrňák", "F"),
    ("8479425", "filip-hronek",   "Filip Hronek",   "D"),
    ("8480039", "martin-necas",   "Martin Nečas",   "F"),
    ("8483468", "jiri-kulich",    "Jiří Kulich",    "F"),
    ("8475462", "radko-gudas",    "Radko Gudas",    "D"),
]


SYSTEM_PROMPT_STABLE = """\
Jste statistický poradce pro hokejovou analytiku, který píše krátké česky-psané \
multimodální profily hráčů. Vaše vstupy:
1. Statistická karta hráče (strukturovaná data — sezónní totaly, cluster, \
   trajectorie, IIHF účast)
2. Akční fotografie hráče z NHL CDN (jeden snímek z reálné herní situace)

Vaše role: spojit oba vstupy a popsat hráče jako celek. Není to text o fotce \
a není to suchá statistika; je to integrace.

## STANCE DISCIPLINE (závazná pravidla)

ZAKÁZÁNO:
- Výběrová doporučení nebo predikce
- Komentář na trenérská rozhodnutí
- Hodnocení podle fotografie samotné ("vypadá unaveně") — fotka je jeden snímek
- Sport-fan superlativy ("ikona", "nejlepší")
- Komentář na výsledek MS 2025 nebo specifické turnaje

POVOLENO (a vyžadováno):
- Popisná integrace: "kompaktní release viditelný na snímku odpovídá jeho \
  poměru G/Shots 0.14, konzistentnímu napříč 8 sezónami"
- Strukturální observace o postoji, držení hole, edge work, body positioning
- Honest uncertainty: "snímek zachycuje moment, ne styl; statistická konzistence \
  je doplňující signál"
- Korelace mezi vizuálním a statistickým — co se shoduje, co je tenze

## OUTPUT FORMAT

Vraťte tři krátké odstavce v češtině, čistý text bez markdown:

**Odstavec 1 — Vizuální popis (60-80 slov):**
Co je na snímku vidět. Postoj, držení hole, fáze pohybu, viditelné fyzikální \
proporce. Bez interpretace stylu — jen co je zachyceno.

**Odstavec 2 — Statistický kontext (60-80 slov):**
Klíčové statistiky z karty: produkce, cluster, trajectorie, role indikátory. \
Konkrétní čísla, ne adjektiva.

**Odstavec 3 — Integrace (80-100 slov):**
Jak vizuální atributy korespondují (nebo nekorespondují) se statistickým \
profilem. Co fotografie přidává nad samotné číslo. Kde je tenze mezi tím, \
co snímek naznačuje, a co stats potvrzují.

Bez headerů, bez bullet points, bez závěrečného doporučení. Pouze tři \
odstavce oddělené prázdným řádkem.
"""


def _client():
    """Lazy import of anthropic to avoid hard dep at module import time."""
    import anthropic
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def _build_player_context(landing: dict, features_row: pd.Series | None,
                          coords_row: pd.Series | None) -> str:
    """Compact structured-data block describing the player."""
    first = landing.get("firstName", {}).get("default", "")
    last  = landing.get("lastName",  {}).get("default", "")
    pos   = landing.get("position", "?")
    birth = landing.get("birthDate", "?")
    height_cm = landing.get("heightInCentimeters")
    weight_kg = landing.get("weightInKilograms")
    shoots = landing.get("shootsCatches")
    age = 2026 - int(birth[:4]) if birth and birth != "?" else None

    # Last 3 NHL seasons from seasonTotals
    nhl_seasons = [s for s in (landing.get("seasonTotals") or [])
                   if s.get("leagueAbbrev") == "NHL" and s.get("gameTypeId") == 2]
    nhl_seasons = sorted(nhl_seasons, key=lambda s: s.get("season", 0), reverse=True)[:3]

    lines = [
        f"Jméno: {first} {last}",
        f"Pozice: {pos}",
        f"Věk: {age}" if age else f"Narozen: {birth}",
        f"Výška/váha: {height_cm} cm / {weight_kg} kg" if height_cm else "",
        f"Drží: {shoots}" if shoots else "",
        "",
        "POSLEDNÍ NHL SEZÓNY (regular season):",
    ]
    for s in nhl_seasons:
        season = s.get("season", "?")
        gp = s.get("gamesPlayed", 0)
        g  = s.get("goals", 0)
        a  = s.get("assists", 0)
        p  = s.get("points", 0)
        pim = s.get("pim", 0)
        sh = s.get("shots") or 0
        # season is YYYYYYYY format e.g. 20242025
        ss = f"{str(season)[:4]}/{str(season)[6:8]}"
        line = f"  {ss}: GP {gp}, G {g}, A {a}, P {p}, S {sh}, PIM {pim}"
        if gp:
            line += f"  ·  P/GP {p/gp:.2f}, S/GP {sh/gp:.2f}"
        lines.append(line)

    # Career totals
    ct = landing.get("careerTotals", {}).get("regularSeason", {})
    if ct.get("gamesPlayed"):
        lines.append("")
        lines.append(
            f"KARIÉRA NHL: {ct.get('gamesPlayed', 0)} GP, "
            f"{ct.get('goals', 0)} G, {ct.get('assists', 0)} A, {ct.get('points', 0)} P"
        )

    # Atlas-derived cluster + projection
    if features_row is not None and coords_row is not None:
        lines.append("")
        lines.append("ATLAS PROJEKCE (sezóna 2025-26):")
        if "cluster_id_quality" in coords_row.index:
            lines.append(f"  Cluster (quality): C{int(coords_row['cluster_id_quality'])}")
        if "cluster_id_style" in coords_row.index:
            lines.append(f"  Cluster (style):   C{int(coords_row['cluster_id_style'])}")
        if "points_per_gp_quality_z" in features_row.index:
            lines.append(f"  Quality z-score:   {features_row['points_per_gp_quality_z']:+.2f}")
        if "iihf_appearances" in features_row.index:
            n = int(features_row.get('iihf_appearances') or 0)
            if n:
                lines.append(f"  IIHF turnaje (MS 24/25): {n}")

    return "\n".join(l for l in lines if l)


def _hero_image_url(player_id: str) -> str:
    """NHL action shot CDN URL."""
    return f"https://assets.nhle.com/mugs/actionshots/1296x729/{player_id}.jpg"


def _fetch_image_b64(url: str) -> tuple[str, str]:
    """Fetch image, return (media_type, base64_data)."""
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    media_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if media_type not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        media_type = "image/jpeg"
    return media_type, base64.standard_b64encode(r.content).decode("ascii")


def generate_card(player_id: str, slug: str, name: str,
                  features: pd.DataFrame, coords: pd.DataFrame,
                  force: bool = False) -> dict:
    """Generate one vision-language card, with on-disk cache."""
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CARDS_DIR / f"{slug}.json"
    if cache_path.exists() and not force:
        LOG.info("cache hit: %s", slug)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    landing_path = config.RAW_DIR / ".cache" / "nhl_landing" / f"{player_id}.json"
    if not landing_path.exists():
        LOG.warning("no cached landing for %s (%s)", name, player_id)
        return {}
    landing = json.loads(landing_path.read_text(encoding="utf-8"))

    # Find features/coords row via canonical_id (e.g. "nhl-8476292")
    feat_row = None
    coord_row = None
    canonical = f"nhl-{player_id}"
    if "canonical_id" in features.columns:
        m = features[features["canonical_id"] == canonical]
        if not m.empty:
            feat_row = m.sort_values("season", ascending=False).iloc[0]
    if "canonical_id" in coords.columns:
        m = coords[coords["canonical_id"] == canonical]
        if not m.empty:
            coord_row = m.sort_values("season", ascending=False).iloc[0]

    ctx = _build_player_context(landing, feat_row, coord_row)
    hero_url = _hero_image_url(player_id)

    LOG.info("fetching hero image: %s", hero_url)
    try:
        media_type, b64 = _fetch_image_b64(hero_url)
    except Exception as e:
        LOG.warning("hero image fetch failed for %s: %s", name, e)
        return {"slug": slug, "name": name, "error": "no_image"}

    LOG.info("calling Claude vision for %s (Czech card)", name)
    client = _client()
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        thinking={"type": "adaptive"},
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT_STABLE,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64},
                },
                {
                    "type": "text",
                    "text": (
                        f"Statistická karta {name}:\n\n{ctx}\n\n"
                        "Vygenerujte trojodstavcový multimodální profil dle pravidel."
                    ),
                },
            ],
        }],
    )

    # Extract text from response
    text_parts = [b.text for b in msg.content if b.type == "text"]
    profile_text = "\n\n".join(text_parts).strip()

    card = {
        "slug": slug,
        "name": name,
        "player_id": player_id,
        "photo_url": hero_url,
        "profile_text": profile_text,
        "context_block": ctx,
        "model": MODEL,
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
        "cache_read_tokens": getattr(msg.usage, "cache_read_input_tokens", 0),
        "cache_creation_tokens": getattr(msg.usage, "cache_creation_input_tokens", 0),
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    cache_path.write_text(json.dumps(card, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    LOG.info("wrote %s (in=%d, out=%d, cache_read=%d)",
             cache_path.name, card["input_tokens"], card["output_tokens"],
             card["cache_read_tokens"])
    return card


def main(force: bool = False) -> list[dict]:
    logging_setup()
    config.ensure_dirs()

    features = read_parquet(config.PROCESSED_DIR / "features_forwards.parquet")
    features_d = read_parquet(config.PROCESSED_DIR / "features_defense.parquet")
    features = pd.concat([features, features_d], ignore_index=True)
    coords = read_parquet(config.PROCESSED_DIR / "coords_forwards.parquet")
    coords_d = read_parquet(config.PROCESSED_DIR / "coords_defense.parquet")
    coords = pd.concat([coords, coords_d], ignore_index=True)

    cards: list[dict] = []
    for pid, slug, name, pos in TARGET_PLAYERS:
        try:
            c = generate_card(pid, slug, name, features, coords, force=force)
            if c:
                cards.append(c)
        except Exception as e:  # noqa: BLE001
            LOG.error("card failed for %s: %s", name, e)
    LOG.info("generated %d cards", len(cards))
    return cards


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    main(force=force)
