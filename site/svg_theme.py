"""Recolour the figures in a built site into the concrete register.

The atlases and the cohort heatmap were drawn with the cream-paper palette
(src/figstyle.py's original colours). Redrawing them would refit nothing
but would need the pipeline's data; a purely visual change is a colour map,
applied here at build time, hex for hex. A figure already drawn in the
register contains none of the legacy hexes and passes through unchanged,
so this is idempotent and safe on every build.

usage: site/svg_theme.py DOCS_DIR      (recolours DOCS_DIR/*.svg)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# the concrete register (docs/modern.css, templates/style.css)
CREAM, CREAM_TINT = "#161616", "#1F1F1F"
INK, MUTED, RULE, GRID, CORPUS = "#DCDCD6", "#8B8B85", "#3A3A36", "#262624", "#3A3A36"
ACID, ACID_TINT, HOT, SLATE = "#D6FF3A", "#3F4A12", "#F2F2EE", "#8B8B85"
SEQ_ORANGE, SEQ_MINT, SEQ_VIOLET = "#FF6A3D", "#7ED9A6", "#B78CFF"

LEGACY_TO_THEME: dict[str, str] = {
    "#1f3a5f": HOT, "#162a44": ACID, "#9c3a2a": ACID, "#f1ddd7": ACID_TINT,
    "#5b7290": SLATE, "#2a261f": INK, "#8a857b": MUTED, "#7e7e78": MUTED, "#d4cfc3": CORPUS,
    "#c8c2b7": RULE, "#ece6d8": GRID, "#fdfbf6": CREAM, "#efe9dc": CREAM_TINT,
    "#ffffff": CREAM, "#000000": INK,
    # the cluster palette of the atlases, in sequencer colours
    "#7e8eaa": INK, "#b08968": SEQ_ORANGE, "#7a5c63": SEQ_VIOLET, "#5e7e64": SEQ_MINT,
    "#7e6678": "#E3A0FF", "#3d6b6e": "#7ED9D9", "#806b53": "#FFB07A",
    "#c4c3bc": RULE,
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
# are remapped by luminance onto a dark ramp (ground -> a light concrete
# grey), so a cell keeps its value ordering and the chalk text on it stays
# legible at every step; the acid outline on the home row carries the accent.
RAMP_LO, RAMP_HI = (0x1F, 0x1F, 0x1F), (0x6E, 0x6E, 0x68)
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
        t = 1.0 - (l - lo) / span          # the legacy ramp runs light -> dark; ours runs dark -> light
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


def main(docs: Path) -> None:
    files = sorted(docs.glob("*.svg"))
    total = 0
    for f in files:
        out, n = recolour(f.read_text(encoding="utf-8"))
        if "heatmap" in f.name:
            out, extra = ramp(out)
            out, imgs = ramp_images(out)
            n += extra + imgs
        if n:
            f.write_text(out, encoding="utf-8")
            total += n
    print(f"svg_theme: {len(files)} figures, {total} colours mapped")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
