"""python -m src.web [OUT_DIR] — render the report and the pool page from outputs/."""

from __future__ import annotations

import sys
from pathlib import Path

from src.logging_setup import setup as logging_setup
from src.web.render import render


def main(argv: list[str]) -> int:
    logging_setup()
    out = Path(argv[0]).resolve() if argv else None
    for rel, path in sorted(render(out).items()):
        print(f"wrote {rel} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
