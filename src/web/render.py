"""Render the site into docs/ (or another directory, for the tests).

    docs/index.html              the summary       templates/site/home.html.j2
    docs/q/<slug>/index.html     one per question  templates/site/question.html.j2 + questions/qN.html.j2
    docs/this-autumn/index.html  dated news        templates/site/autumn.html.j2 (only with a news file)
    docs/methodology/index.html  scope, sources, limitations, change log   templates/site/methodology.html.j2
    docs/players/index.html      the pool page     templates/site/players.html.j2
    docs/atlas/index.html        redirect to players/ (GitHub Pages has no server redirects)
    docs/charts/report.json      chart data        src.web.charts.report_data
    docs/players/pool.json       the pool list     src.web.charts.pool_data
    docs/style.css, modern.css, charts.js, atlas.app.js   templates/site/static/

The report used to be one page; the summary maps its old anchors (#q1, #methodology, ...) to the new pages.

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

# (id, slug, content title (the page's h1), short label (navigation), limitations listed as "What this does not show")
QUESTIONS = (
    ("q1", "per-head", "NHL and rung-2 players per million inhabitants, ten nations, 2025/26", "Players per million",
     ("population", "nationality", "khl", "single_season")),
    ("q2", "break", "Timing of changes in the Czech NHL count, 1995/96–2025/26", "Timing of changes",
     ("descriptive", "khl", "population")),
    ("q3", "cohorts", "Czech NHL and rung-2 players by position and age against the peer median, 2025/26", "Position and age",
     ("single_season", "birth", "ages", "nationality")),
    ("q4", "youth", "Share of league games and ice time played by skaters aged 20 or under, 2014/15–2025/26", "Young skaters at home",
     ("birth", "ages", "descriptive")),
    ("q5", "abroad", "Ice time and points per game of Czech skaters against the league median, 2020/21–2025/26", "Czech skaters abroad",
     ("ahl", "khl", "descriptive")),
    ("q6", "national-team", "League composition of Czech national-team rosters, 2010–2026", "National-team rosters",
     ("khl", "descriptive")),
    ("q7", "goalkeepers", "Czech goalkeepers: counts per million, save percentage abroad and national-team spots", "Goalkeepers",
     ("ahl", "ages", "population", "descriptive")),
)
LIMIT_KEYS = ("descriptive", "khl", "ahl", "birth", "nationality", "name_links", "population", "ages", "single_season")
# the one-page report's anchors -> the page that holds that part now (relative to the site root)
METHOD_ANCHORS = ("scope", "nationality", "exclusions", "methodology", "data-sources", "linking",
                  "definitions", "reproducibility", "limitations", "changes")


def questions() -> list[dict]:
    return [
        {"id": qid, "n": i + 1, "slug": slug, "url": f"q/{slug}/", "title": title, "label": label, "limits": list(limits),
         "description": f"Question {i + 1} of the Czech hockey atlas: {title}."}
        for i, (qid, slug, title, label, limits) in enumerate(QUESTIONS)
    ]


def old_anchors(autumn: bool) -> dict[str, str]:
    m = {q["id"]: q["url"] for q in questions()}
    m.update({a: f"methodology/#{a}" for a in METHOD_ANCHORS})
    if autumn:
        m["autumn"] = "this-autumn/"
    return m


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
    qs = questions()
    for d in ("charts", "atlas", "players", "methodology", *(q["url"] for q in qs)):
        (out / d).mkdir(parents=True, exist_ok=True)

    outputs = context.load_outputs(outputs_dir)
    ctx = context.build(outputs_dir, build_date=build_date)

    written: dict[str, Path] = {}
    report_json = _dump(charts.report_data(outputs))
    pool_json = _dump(charts.pool_data(outputs["pool"]))
    for rel, text in (("charts/report.json", report_json), ("players/pool.json", pool_json)):
        p = out / rel
        p.write_text(text, encoding="utf-8")
        written[rel] = p
    for name in STATIC_FILES:
        shutil.copyfile(STATIC / name, out / name)
        written[name] = out / name

    digest = hashlib.sha256()
    for name in (*STATIC_FILES, "charts/report.json", "players/pool.json"):
        digest.update((out / name).read_bytes())
    ctx["v"] = digest.hexdigest()[:10]

    ctx["questions"] = qs
    ctx["qurl"] = {q["id"]: q["url"] for q in qs}
    ctx["limit_keys"] = LIMIT_KEYS
    ctx["old_anchors"] = old_anchors(bool(ctx.get("autumn")))

    env = _env()
    pages: list[tuple[str, str, dict]] = [
        ("home.html.j2", "index.html", {"prefix": "", "page": "home"}),
        ("methodology.html.j2", "methodology/index.html", {"prefix": "../", "page": "methodology"}),
        ("players.html.j2", "players/index.html", {"prefix": "../", "page": "players"}),
        ("redirect.html.j2", "atlas/index.html", {"prefix": "../", "to": "players/", "title": "Players"}),
    ]
    if ctx.get("autumn"):
        (out / "this-autumn").mkdir(exist_ok=True)
        pages.append(("autumn.html.j2", "this-autumn/index.html", {"prefix": "../", "page": "autumn"}))
    for i, q in enumerate(qs):
        extra = {"prefix": "../../", "page": "question", "cur": q,
                 "prev": qs[i - 1] if i else None, "next": qs[i + 1] if i + 1 < len(qs) else None}
        pages.append(("question.html.j2", f"{q['url']}index.html", extra))
    for tpl, rel, extra in pages:
        html = env.get_template(tpl).render(**ctx, **extra)
        (out / rel).write_text(html, encoding="utf-8")
        written[rel] = out / rel
    stale = out / "atlas" / "pool.json"
    if stale.exists():
        stale.unlink()
    LOG.info("rendered %s", ", ".join(sorted(written)))
    return written
