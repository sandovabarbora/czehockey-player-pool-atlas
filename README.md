# Czech hockey atlas: the player pool

An exploratory, descriptive atlas of Czech professional hockey players per head against nine
peer nations (Finland, Sweden, Switzerland, Slovakia, Germany, Latvia, Denmark, Norway, Austria),
1995/96–2025/26. Published at <https://hockey.bsandova.com/>.

Status: exploratory; not pre-registered; no external review. The atlas identifies no cause, makes
no forecast and gives no selection or policy advice.

## Questions

1. NHL and rung-2 players per million inhabitants (`src/analysis/q1_per_million.py`)
2. Timing of changes in the Czech NHL count, a Poisson local-level break model (`q2_break_model.py`)
3. Players by position and age against the peer median (`q3_cohort_gaps.py`)
4. Share of league games and ice time played by skaters aged 20 or under (`q4_youth_ice_time.py`)
5. Ice time and points per game of Czech skaters against the league median (`q5_abroad.py`)
6. League composition of national-team rosters (`q6_national_team.py`)
7. Goalkeepers (`q7_goalkeepers.py`)

Bootstrap intervals, spreads and period splits for the pages are in `src/analysis/intervals.py`.

## Data

NHL stats API, liiga.fi, shl.se, hokej.cz (Extraliga), penny-del.org (DEL), data.sihf.ch
(National League), Eurostat `demo_gind`, and English Wikipedia roster articles at fixed revisions.
The processed tables are committed in `data/snapshot/` (snapshot 29 September 2026) with
`data/snapshot/SHA256SUMS`. The KHL, the AHL, the Slovak Extraliga and Elite Prospects are not
covered; the methodology page lists them and what that leaves out.

## Reproduce

```bash
make install            # .venv from uv.lock (Python 3.13)
make restore-snapshot   # data/snapshot/ -> data/processed/
make verify-snapshot    # check SHA256SUMS
make analysis           # outputs/*.json (about six minutes; break model seed 42)
make pages              # docs/ from outputs/ and templates/site/
make test
```

`make analysis-fast` skips the break model. Every number on the pages is read from `outputs/`;
`tests/test_site_render.py` fails when `docs/` is stale.

## Layout

- `src/fetch/` fetchers (one per source), `src/snapshot.py` snapshot handling
- `src/analysis/` linking, the pool list and one module per question
- `src/web/` the site render; `templates/site/` its templates and static assets
- `docs/` the published site (GitHub Pages)

Legacy code from the first version (the 2026 style map: `src/render.py`, `src/features_*.py`,
`src/reduce.py`, `src/cluster.py`, `site/source/`, `make render`) is kept for the record and is
not part of the published atlas.

## Licence

Code MIT (see [LICENSE](LICENSE)). Text and figures CC BY 4.0. Roster data derived from
Wikipedia (`data/snapshot/rosters.parquet` and tables built from it) CC BY-SA 4.0. Tables derived
from the league sites are shared for reproducing the atlas only; reuse them under each site's terms.

## Cite

Šandová, B. (2026). *Czech hockey atlas: the player pool*. hockey.bsandova.com, version 3.
<https://github.com/sandovabarbora/czehockey-player-pool-atlas>

## Contact

Barbora Šandová · hello@bsandova.com
