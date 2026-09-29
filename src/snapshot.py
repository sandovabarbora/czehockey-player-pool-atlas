"""The committed snapshot: data/snapshot/ plus its SHA-256 list.

Fetchers write processed tables to data/processed/ (gitignored) and call
`publish()`, which copies them into data/snapshot/ and rewrites
data/snapshot/SHA256SUMS (`sha256sum` format, sorted by path, covering every
file in the directory). A clean clone rebuilds from the snapshot without
fetching: `restore()` copies it back into data/processed/ and `verify()`
checks every hash (also run by the tests).

    python -m src.snapshot verify|restore|rehash
"""

from __future__ import annotations

import hashlib
import shutil
import sys
from collections.abc import Iterable
from pathlib import Path

from src import config

SNAPSHOT_DIR: Path = config.DATA_DIR / "snapshot"
SUMS = "SHA256SUMS"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.name != SUMS and not p.name.startswith(".")
    )


def rehash(root: Path | None = None) -> Path:
    """Rewrite root/SHA256SUMS for every file under root."""
    root = root or SNAPSHOT_DIR
    lines = [f"{sha256(p)}  {p.relative_to(root).as_posix()}" for p in _files(root)]
    out = root / SUMS
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def publish(paths: Iterable[Path], root: Path | None = None) -> list[Path]:
    """Copy processed files into the snapshot (same relative path) and rehash."""
    root = root or SNAPSHOT_DIR
    root.mkdir(parents=True, exist_ok=True)
    written = []
    for src in paths:
        rel = (
            src.relative_to(config.PROCESSED_DIR)
            if src.is_relative_to(config.PROCESSED_DIR)
            else Path(src.name)
        )
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        written.append(dst)
    rehash(root)
    return written


def verify(root: Path | None = None) -> list[str]:
    """Return a list of problems (empty when every file matches SHA256SUMS)."""
    root = root or SNAPSHOT_DIR
    sums = root / SUMS
    if not sums.exists():
        return [f"{sums} is missing"]
    listed: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            listed[rel] = digest
    problems = []
    present = {p.relative_to(root).as_posix(): p for p in _files(root)}
    for rel, digest in listed.items():
        if rel not in present:
            problems.append(f"listed but missing: {rel}")
        elif sha256(present[rel]) != digest:
            problems.append(f"hash mismatch: {rel}")
    problems += [f"not listed: {rel}" for rel in present if rel not in listed]
    return problems


def restore(root: Path | None = None, dest: Path | None = None) -> int:
    """Copy snapshot files missing from (or older in) data/processed/. Returns the count."""
    root = root or SNAPSHOT_DIR
    dest = dest or config.PROCESSED_DIR
    n = 0
    for src in _files(root):
        dst = dest / src.relative_to(root)
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "verify"
    if cmd == "rehash":
        print(rehash())
    elif cmd == "restore":
        print(f"restored {restore()} files")
    else:
        problems = verify()
        for p in problems:
            print(p)
        print("snapshot OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
