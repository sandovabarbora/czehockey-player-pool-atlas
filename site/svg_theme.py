"""Recolour the figures in a built site into the A24 register.

The atlases and the cohort heatmap were drawn with the cream-paper palette
(src/render.py's original colours). Redrawing them would need the pipeline's
data; a purely visual change is a colour map, applied here at build time, hex
for hex. The same map recolours the cluster colours in docs/atlas_meta.json
(atlas.js paints its legend chips and tooltips from them) and the inline
roadmap sketch in docs/index.html. Every value the map writes maps to itself;
the heatmap's luminance ramp is not, so it runs once per build, on the pristine
copy site/svg_labels.py has just written from site/source/figures/.

usage: site/svg_theme.py DOCS_DIR      (recolours DOCS_DIR/*.svg, atlas_meta.json, index.html)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# the A24 register (docs/modern.css, templates/style.css): white paper, ink,
# hairlines, one colour held from the hero photograph for the home nation
PAPER, PAPER_TINT = "#ffffff", "#f6f6f4"
INK, MUTED, RULE, GRID, CORPUS = "#111111", "#666666", "#d9d9d5", "#ececea", "#d9d9d5"
HELD, HELD_TINT, GREY = "#1f5fd6", "#e3ecfb", "#8a8a8a"
# categorical colours, only where more than two categories are needed (clusters)
SEQ_ORANGE, SEQ_VIOLET, SEQ_TEAL, SEQ_OCHRE = "#c8531f", "#6b4bb8", "#2a8c8c", "#b8742f"

LEGACY_TO_THEME: dict[str, str] = {
    # the cream-paper originals (src/render.py)
    "#1f3a5f": INK, "#162a44": HELD, "#9c3a2a": HELD, "#f1ddd7": HELD_TINT,
    "#5b7290": GREY, "#2a261f": INK, "#8a857b": MUTED, "#7e7e78": MUTED, "#d4cfc3": CORPUS,
    "#c8c2b7": RULE, "#ece6d8": GRID, "#fdfbf6": PAPER, "#efe9dc": PAPER_TINT,
    "#ffffff": PAPER, "#000000": INK,
    # the cluster palette of the atlases: ink, grey, then the categorical colours
    "#7e8eaa": GREY, "#b08968": SEQ_ORANGE, "#7a5c63": SEQ_VIOLET, "#5e7e64": SEQ_TEAL,
    "#7e6678": SEQ_OCHRE, "#3d6b6e": "#444444", "#806b53": SEQ_OCHRE,
    "#c4c3bc": RULE,
    # the dark "concrete" register (2026-09-21) this one replaces, should a
    # figure already recoloured into it come through
    "#161616": PAPER, "#1f1f1f": PAPER_TINT, "#dcdcd6": INK, "#8b8b85": MUTED, "#3a3a36": RULE,
    "#262624": GRID, "#d6ff3a": HELD, "#3f4a12": HELD_TINT, "#f2f2ee": INK,
    "#ff6a3d": SEQ_ORANGE, "#7ed9a6": SEQ_TEAL, "#b78cff": SEQ_VIOLET, "#e3a0ff": SEQ_OCHRE,
    "#7ed9d9": "#444444", "#ffb07a": SEQ_OCHRE, "#6e6e68": "#a3a39e",
}
_HEX = re.compile("|".join(re.escape(k) for k in LEGACY_TO_THEME), re.IGNORECASE)


def recolour(svg: str) -> tuple[str, int]:
    """The SVG text with every legacy colour replaced; and how many were."""
    n = 0

    def swap(m: re.Match) -> str:
        nonlocal n
        n += 1
        return LEGACY_TO_THEME[m.group(0).lower()]

    return _HEX.sub(swap, svg), n


# The cohort heatmap's cells come from a cream-to-navy matplotlib ramp, not
# from the palette above: dozens of interpolated hexes no map can list. They
# are remapped by luminance onto a neutral paper ramp (paper tint -> a mid
# grey), so a cell keeps its value ordering and the ink text on it stays
# legible at every step (6:1 on the darkest cell); the held-colour outline on
# the home row carries the accent.
RAMP_LO, RAMP_HI = (0xF6, 0xF6, 0xF4), (0xA3, 0xA3, 0x9E)
_ANY_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _lum(hexcolour: str) -> float:
    r, g, b = (int(hexcolour[i:i + 2], 16) for i in (1, 3, 5))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def ramp(svg: str) -> tuple[str, int]:
    """Remap every colour the explicit map left behind onto the dark ramp."""
    left = {h.lower() for h in _ANY_HEX.findall(svg)} - set(LEGACY_TO_THEME.values()) - {v.lower() for v in LEGACY_TO_THEME.values()}
    if not left:
        return svg, 0
    lums = {h: _lum(h) for h in left}
    lo, hi = min(lums.values()), max(lums.values())
    span = (hi - lo) or 1.0
    out = svg
    for h, l in lums.items():
        t = 1.0 - (l - lo) / span          # the legacy ramp runs light -> dark; t = 0 is the lightest
        mixed = "#%02X%02X%02X" % tuple(round(a + (b - a) * t) for a, b in zip(RAMP_LO, RAMP_HI))
        out = re.sub(re.escape(h), mixed, out, flags=re.IGNORECASE)
    return out, len(lums)


# matplotlib rasterises `imshow` into an embedded PNG, so the heatmap's cell
# grid is an image, not paths: its pixels are remapped the same way.
_IMG = re.compile(r'((?:xlink:)?href="data:image/png;base64,)([A-Za-z0-9+/=\s]+?)(")')


def ramp_images(svg: str) -> tuple[str, int]:
    import base64
    import io

    from PIL import Image

    n = 0

    def swap(m: re.Match) -> str:
        nonlocal n
        raw = base64.b64decode("".join(m.group(2).split()))
        im = Image.open(io.BytesIO(raw)).convert("RGBA")
        px = im.load()
        w, h = im.size
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                t = 1.0 - (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
                px[x, y] = tuple(round(lo + (hi - lo) * t) for lo, hi in zip(RAMP_LO, RAMP_HI)) + (a,)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        n += 1
        return m.group(1) + base64.b64encode(buf.getvalue()).decode() + m.group(3)

    return _IMG.sub(swap, svg), n


def recolour_meta(meta: dict) -> int:
    """Recolour the cluster colours atlas_meta.py read from the legacy figures."""
    n = 0
    for fig in meta.values():
        for panel in fig.get("panels", []):
            for c in panel.get("clusters", []):
                new = LEGACY_TO_THEME.get(str(c.get("color", "")).lower())
                if new and new != c["color"]:
                    c["color"] = new
                    n += 1
    return n


# the roadmap sketch is an inline SVG written by the report template in the
# legacy palette and fonts; it gets the same colours, and the register's type
_INLINE_SVG = re.compile(r"<svg\b.*?</svg>", re.S)
_FONTS = (('font-family="Bricolage Grotesque, sans-serif"', 'font-family="JetBrains Mono, monospace"'),
          ('font-family="Spectral, serif" font-style="italic"', 'font-family="Inter Tight, sans-serif"'))


def recolour_inline(html: str) -> tuple[str, int]:
    n = 0

    def swap(m: re.Match) -> str:
        nonlocal n
        svg, k = recolour(m.group(0))
        for a, b in _FONTS:
            svg = svg.replace(a, b)
        n += k
        return svg

    return _INLINE_SVG.sub(swap, html), n


def main(docs: Path) -> None:
    files = sorted(docs.glob("*.svg"))
    total = 0
    for f in files:
        out, n = recolour(f.read_text(encoding="utf-8"))
        if "heatmap" in f.name:
            # the legacy ramp ran dark enough for cream text on its top cells;
            # on the paper ramp every cell takes ink text (the glyph groups)
            out, k = re.subn(r'(<g style="fill: )' + re.escape(PAPER) + r'(" transform=)', r"\g<1>" + INK + r"\g<2>", out)
            n += k
            out, extra = ramp(out)
            out, imgs = ramp_images(out)
            n += extra + imgs
        if n:
            f.write_text(out, encoding="utf-8")
            total += n
    meta_path = docs / "atlas_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        n = recolour_meta(meta)
        if n:
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            total += n
    index = docs / "index.html"
    if index.exists():
        out, n = recolour_inline(index.read_text(encoding="utf-8"))
        if n:
            index.write_text(out, encoding="utf-8")
            total += n
    print(f"svg_theme: {len(files)} figures, {total} colours mapped")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
