#!/bin/zsh
# Build the published site from the analysis outputs (`make analysis`):
#   docs/index.html              the summary         templates/site/home.html.j2
#   docs/q/<slug>/index.html     one page per question   templates/site/question.html.j2
#   docs/this-autumn/, docs/methodology/, docs/players/   autumn/methodology/players.html.j2
#   docs/atlas/index.html        redirect to docs/players/
#   docs/charts/report.json      chart data          (src/web/charts.py)
#   docs/players/pool.json       the pool list
# site/text_freeze.py checks the pages' text against the one-page report they were split from.
#   docs/*.css, charts.js, atlas.app.js          templates/site/static/
# Every number on the pages is read from outputs/*.json by src/web/context.py.
# docs/CNAME and docs/img/ are left as they are.
#
# usage: site/build.sh [OUT_DIR]   (default docs/)
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}
if command -v uv >/dev/null 2>&1 && [ -f "$ROOT/pyproject.toml" ]; then PY="uv run --project $ROOT python"; fi
cd "$ROOT"
${=PY} -m src.web ${1:+"$1"}
