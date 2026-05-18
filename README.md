# Czech Hockey — Player Pool Atlas

A position-normalized 2D map of ~140–200 Czech-eligible professional hockey players
from NHL, AHL, Liiga, SHL, Swiss NL, Czech Extraliga, and Czech 1. Liga.

**This is a methodology showcase, not a selection recommendation.** The deliverable
is a replicable mapping method intended as a planning tool over the multi-year
international cycle. It is not a roster suggestion, and it does not commentate on
tournament results, line combinations, or individual coaching choices.

The Czech version of this README is at [`README.cs.md`](README.cs.md).

---

## What the project produces

Two map projections, side by side:

1. **Style map** — position-normalized per-60 z-scores, no league quality multipliers.
   Players are grouped by performance fingerprint independent of league strength.
2. **Quality-adjusted map** — same features, with league quality multipliers applied
   to production rates. Players from different leagues become directly comparable
   on a single quality axis. The multipliers are subjective; sensitivity analysis
   (±20% perturbation) is included.

Plus:

- **Trajectory arrows** — season-over-season delta (2024/25 → 2025/26), shown only
  for players with sufficient sample size in both seasons.
- **Cluster archetypes** — KMeans with K selected by silhouette score, post-hoc
  labelled by inspection.
- **Goaltender mini-section** — separate small table; goalie analytics are too
  context-dependent for the main map.
- **Limitations section** — explicit, mandatory, in Czech in the report.

## Architecture

```
data sources → unified player records → per-60 features
   → standardize within position → PCA + UMAP + KMeans
   → Jinja2 → HTML + PDF report
```

See `src/` for the module layout. Each fetcher is independent and writes to
`data/raw/`. The crosswalk module deduplicates player IDs across sources.

## Data sources

| Source | Access pattern | Coverage |
|---|---|---|
| NHL Stats API (`api-web.nhle.com/v1`) | HTTP JSON | NHL standard + advanced |
| MoneyPuck | CSV download | NHL xG, GAR-style metrics |
| Liiga | Playwright SPA render | Finnish top league |
| SHL | Playwright SPA render | Swedish top league |
| Swiss NL | Playwright SPA render | Swiss top league |
| hokej.cz | HTTP + BeautifulSoup | Czech Extraliga + 1. Liga |
| IIHF | HTTP + BeautifulSoup | MS / WJC tournament history |

KHL is explicitly excluded — both for political reasons (sanctions affecting Russian
data sources) and data quality. The exclusion is documented in the report's
Limitations section.

## Methodology — key choices

- **Position-specific features.** Forwards, defensemen, and goaltenders have
  separate 10-dim (or 6-dim for goalies) feature vectors. No mixed-position
  projection.
- **League quality multipliers are subjective.** A sensitivity notebook shows how
  the map changes when multipliers shift by ±20%. The multipliers themselves are
  in `config/league_quality.yaml` with source citations.
- **K (cluster count) is data-driven.** Selected by silhouette score and elbow
  method on K ∈ {4..8} for forwards and {3..6} for defensemen. Archetype labels
  are post-hoc, applied after inspection.
- **No xG in cross-league feature vector.** xG models do not exist publicly for
  Liiga / SHL / NL / Extraliga. xG is shown as NHL/AHL-only enrichment in player
  tooltips and the technical section; it is not imputed.
- **Trajectory minimum sample.** Players must have ≥ 30 GP in both seasons to
  appear in the trajectory analysis. Below that threshold, two data points are
  not enough to distinguish trend from regression to mean.

## Running the pipeline

```bash
make install            # uv venv + deps
make install-browsers   # playwright chromium
make all                # fetch -> features -> reduce -> render
```

Output at `outputs/index.html` and `outputs/report.pdf`.

## What this project is not

- It is not a selection recommendation.
- It is not a critique of coaching, line combinations, or specific tournament results.
- It is not a goaltending evaluation tool beyond aggregate stats.
- It does not use any private scouting, video, wellness, or tracking data.
- It does not cover KHL players.

## License

MIT. See [LICENSE](LICENSE).

## Contact

Barbora Šandová · barbora@datasimply.eu · [linkedin.com/in/barborasandova](https://linkedin.com/in/barborasandova)
