"""Insert the "what to take from it" block into a built page.

Runs last, per language, so each page's statements are read from its own
final markup (site/takeaways.py) -- the Czech page in Czech, the English
one in English.

usage: insert_takeaways.py PAGE [en|cs]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import takeaways  # noqa: E402

page = Path(sys.argv[1])
lang = sys.argv[2] if len(sys.argv) > 2 else "en"
html = page.read_text(encoding="utf-8")
html = re.sub(r'<section class="take" id="take">.*?</section>\n?', "", html, flags=re.S)   # idempotent
block = takeaways.render(html, lang)
if not block:
    sys.exit(f"takeaways: nothing parsed from {page}")
html, n = re.subn(r'(<section class="exec-summary")', lambda m: block + "\n" + m.group(1), html, count=1)
if n != 1:
    sys.exit(f"takeaways: no exec-summary section in {page}")
page.write_text(html, encoding="utf-8")
print(f"takeaways: {block.count('nx-take-head')} statements into {page.name} ({lang})")
