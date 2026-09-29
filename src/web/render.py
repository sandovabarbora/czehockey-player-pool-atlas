"""Render the site into docs/ (or another directory, for the tests).

    docs/index.html          the report       templates/site/report.html.j2
    docs/atlas/index.html    the pool page    templates/site/atlas.html.j2
    docs/charts/report.json  chart data       src.web.charts.report_data
    docs/atlas/pool.json     the pool list    src.web.charts.pool_data
    docs/style.css, modern.css, charts.js, atlas.app.js   templates/site/static/

docs/CNAME and docs/img/ are left as they are.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from src import config
from src.web import charts, context

LOG = logging.getLogger(__name__)

TEMPLATES = config.TEMPLATES_DIR / "site"
STATIC = TEMPLATES / "static"
STATIC_FILES = ("style.css", "modern.css", "charts.js", "atlas.app.js")
DOCS = config.ROOT_DIR / "docs"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def render(out_dir: Path | None = None, outputs_dir: Path | None = None, build_date: str | None = None) -> dict[str, Path]:
    out = out_dir or DOCS
    (out / "charts").mkdir(parents=True, exist_ok=True)
    (out / "atlas").mkdir(parents=True, exist_ok=True)

    outputs = context.load_outputs(outputs_dir)
    ctx = context.build(outputs_dir, build_date=build_date)

    written: dict[str, Path] = {}
    report_json = _dump(charts.report_data(outputs))
    pool_json = _dump(charts.pool_data(outputs["pool"]))
    for rel, text in (("charts/report.json", report_json), ("atlas/pool.json", pool_json)):
        p = out / rel
        p.write_text(text, encoding="utf-8")
        written[rel] = p
    for name in STATIC_FILES:
        shutil.copyfile(STATIC / name, out / name)
        written[name] = out / name

    digest = hashlib.sha256()
    for name in (*STATIC_FILES, "charts/report.json", "atlas/pool.json"):
        digest.update((out / name).read_bytes())
    ctx["v"] = digest.hexdigest()[:10]

    env = _env()
    pages = (
        ("report.html.j2", "index.html", {"prefix": "", "page": "report"}),
        ("atlas.html.j2", "atlas/index.html", {"prefix": "../", "page": "atlas"}),
    )
    for tpl, rel, extra in pages:
        html = env.get_template(tpl).render(**ctx, **extra)
        (out / rel).write_text(html, encoding="utf-8")
        written[rel] = out / rel
    LOG.info("rendered %s", ", ".join(sorted(written)))
    return written
