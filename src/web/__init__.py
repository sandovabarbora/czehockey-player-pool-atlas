"""The published site (docs/): the report page and the pool page, rendered from outputs/.

`python -m src.web` reads the analysis JSON in outputs/, writes the chart data the pages
draw from (docs/charts/report.json, docs/atlas/pool.json), renders
templates/site/*.html.j2 and copies the static assets (CSS, charts.js, atlas.app.js)
next to them. Every number on the pages comes from outputs/ through `context.build`.
"""
