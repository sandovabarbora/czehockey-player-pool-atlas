"""Content freeze check for the page split: the visible text of the new pages against the old report.

    uv run python site/text_freeze.py [REF]      (REF: the commit with the one-page report, default origin/main)

The old side is docs/index.html and docs/atlas/index.html at REF; the new side is every index.html
under docs/ now. Text is compared block by block (paragraphs, list items, headings, table cells,
captions, summaries), whitespace-normalised, as two sets. It prints the old blocks missing from the
new pages (must be none) and the new blocks the old report did not have (navigation labels only).
Exit status 1 when an old block is missing.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BLOCKS = ("p", "li", "h1", "h2", "h3", "h4", "dt", "dd", "td", "th", "figcaption", "summary", "a", "span", "strong", "em", "code")


def blocks(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "head", "noscript"]):
        t.decompose()
    out = set()
    for el in soup.find_all(BLOCKS):
        text = re.sub(r"\s+", " ", el.get_text(" ")).strip()
        text = re.sub(r"Built \d{4}-\d{2}-\d{2}", "Built", text)
        if text:
            out.add(text)
    return out


def main(ref: str) -> int:
    old: set[str] = set()
    for rel in ("docs/index.html", "docs/atlas/index.html"):
        old |= blocks(subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout)
    pages = sorted(DOCS.rglob("index.html"))
    new: set[str] = set()
    for p in pages:
        new |= blocks(p.read_text(encoding="utf-8"))
    missing = sorted(old - new)
    added = sorted(new - old)
    print(f"old report ({ref}): {len(old)} text blocks; new pages ({len(pages)}): {len(new)} text blocks")
    print(f"old blocks missing from the new pages: {len(missing)}")
    for t in missing:
        print("  -", t[:160])
    print(f"new blocks not in the old report: {len(added)}")
    for t in added:
        print("  +", t[:160])
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))
