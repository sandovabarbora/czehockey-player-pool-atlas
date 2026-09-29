# Czech hockey player-pool atlas: rebuild on the football model (spec, 29 September 2026)

Approved by the owner on 29 September 2026. The feasibility audit behind it is summarised in §7.

## 1. Goal

A public, reproducible report on the Czech professional hockey player pool, measured against peer nations the way
`czefootball-player-pool-atlas` measures football. It is descriptive and exploratory: no predictions, no selection
advice, public data only. It replaces the current site at hockey.bsandova.com, which is a working version (a
style map plus an "AI & multimodal layer"). The AI and video layer is dropped.

## 2. Peers and league ladder

- **Nations:** Czechia, plus Finland, Sweden, Switzerland, Slovakia, Germany, Latvia, Denmark, Norway and Austria.
- **Rung 1:** NHL.
- **Rung 2:** SHL, Liiga, National League (SUI) and DEL. The headline "top-5 leagues" is rung 1 plus rung 2.
- **Home league:** the Czech Extraliga for Czechia. For each peer, its own top league where covered.
- **Other covered league:** everything else in the data.
- **Excluded:**
  - KHL, by design; the report says so, because it removes a real destination, especially before 2014.
  - AHL, whose terms forbid automated access. AHL seasons appear only through NHL players' career records, and the
    report says that this view is survivor-biased.
  - Slovak Extraliga: robots.txt blocks automated access. Slovakia is measured through its players in the covered
    leagues.
  - Elite Prospects, whose terms forbid scraping.

## 3. Questions, with the window for each

1. **Is the pool thin?** NHL players (at least 20 games, or a stated threshold) per million inhabitants, Czechia
   against the peers:
   - 2025/26 as the headline;
   - the season series from 1995/96 for the NHL only;
   - rung 1 + 2 from 2008/09.
2. **When did it break?** A break model on the Czech NHL series 1995/96–2025/26, a local-level model with step
   changes as in the football atlas's series model. It is compared with Finland and Sweden.
3. **Where is it thin?** Cohort gaps by position and age band in rung 1 + 2, 2025/26, Czechia against the peer
   median.
4. **Do young players get ice time at home?**
   - The under-21 share of games, and of time on ice where available, in the Czech Extraliga (TOI from 2013/14)
     against Liiga (from 2014/15) and SHL (from 2009/10).
   - NL and DEL are measured by games only.
   - The window is 2014/15–2025/26.
5. **How do they fare abroad?** Time on ice per game and points per game of Czech players in the NHL, Liiga and SHL,
   against the league median at the same position.
6. **What is the national team built from?** Rosters of the World Championship and the Olympics from 2010, with
   each player's club and league rung at the time.
7. **Goalkeepers**, in a separate section.

## 4. Nationality and linking

- **One definition of nationality**, written into the report and applied to every source:
  - citizenship where the source gives it (NHL `nationalityCode`, Liiga `nationality`, SHL `nationality` where not
    "N/A", with SHL back-filled by player id from later seasons);
  - otherwise eligibility or licence where that is all the source has (DEL "Nat", Extraliga foreigner flag);
  - the report states which source uses which.
- Czechoslovak-era births take the present-day state as the NHL recodes them, and the report says so.
- Players are linked across leagues on normalised name (diacritics folded) plus birth date. Unmatched and ambiguous
  records are reported.

## 5. Build and reproducibility

- **Fetchers**, one per source:
  - `src/fetch/nhl.py` (stats REST bios and summary per season);
  - `liiga.py`, `shl.py`, `extraliga.py` (hokej.cz HTML), `del_.py`, `nl.py` (best effort from 2008/09);
  - `eurostat.py` (`demo_gind`, 1 January population);
  - `rosters.py` (Wikipedia MediaWiki API, CC BY-SA attribution).
- **Fetching rules**: polite rate limits, a cache of raw responses, and a committed processed snapshot under
  `data/snapshot/` with SHA-256 hashes, so a clean clone rebuilds without fetching (as in the football atlas).
- **Analysis**, one module per question under `src/analysis/`, writing JSON to `outputs/`.
- **Site**:
  - The same templates, CSS, A24 register, rung palette and page structure as the football atlas.
  - Held colour: jersey blue #1F5FD6. Rungs: rung 1 NHL in the held colour, rung 2 in ink, other in #8a8a8a, home
    in #c9c9c4.
  - A report page (`docs/index.html`) and a pool page (`docs/atlas/`) with the full-width list, the expandable rows
    and the one control row.
  - Charts are interactive and drawn from the output JSON.
- **Tests**: data contracts per fetcher (fields, types, row counts per season), the linking rate, and the analysis
  on fixtures.
- **Content rules**: English only; every number in the text generated from `outputs/`; limitations and the
  exclusions in §2 stated on the page.

## 6. Out of scope for this build

- Other national editions.
- An AHL feed, unless the league grants permission.
- Any rating of individual players beyond published statistics.

## 7. Feasibility audit, summarised

The full notes are kept outside the repository.

| Source | Access | Coverage |
|---|---|---|
| NHL stats REST | `nationalityCode` and `birthDate` | 1917/18 onwards; skater TOI from 1997/98 |
| Liiga JSON | `nationality`, `dateOfBirth`, `isU20` | 1995/96 onwards; TOI from 2014/15 |
| SHL statistics-v2 JSON | birth date always; nationality mostly N/A before about 2010 | TOI from 2009/10 |
| hokej.cz | HTML; birth date on player profiles | from 1992/93; TOI from 2013/14; U20 and foreigner filters |
| DEL | HTML | archive from 1994/95; nationality and TOI from 2022/23 |
| SIHF NL | JSON | past seasons not yet unlocked |
| Eurostat `demo_gind` | JSON | complete for all ten nations from 1995 |
| Wikipedia rosters | MediaWiki API | World Championship from 1998, with clubs from 2010; Olympics 1998–2026 |

Risks:

- NHL terms allow non-commercial informational use and forbid unauthorised scraping. The project fetches once into
  a cached snapshot for a non-commercial site and cites the source.
- Endpoints without published terms may change, which is why the raw responses are cached.
